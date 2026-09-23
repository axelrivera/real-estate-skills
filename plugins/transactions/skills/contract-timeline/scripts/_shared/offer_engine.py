"""Offer engine shared by seller-offer-review (listing side) and buyer-offer-strategy (buyer side).

    from _shared import offer_engine as oe
    R = oe.analyze(listing_file)              # dict: listing, seller, offers, ranked, mode, assumptions, ...
    R = oe.analyze(listing_file, market=path_or_Market, cma=handoff_dict)

For every offer: seller net sheet (as offered, downside, counter, fallback), certainty score, risk flags,
proposed counter; with 2+ active offers, a ranking and a response plan.

Rule: the engine never stops on missing data. Every missing input gets a conservative default and is
recorded as an assumption with an impact level (high / med / low), so the report can say what to confirm
and mark itself Preliminary. Market costs (transfer tax, title, fees, brokerage defaults, property tax,
holding costs, inspection credit reserve) come from the market profile via shared.finance; outside a
built-in market a missing value is left out and labeled, never filled with another state's number.
"""
import copy
import math
import re
from datetime import date, datetime, timedelta

from . import finance, profiles

FIN_LABEL = {k: v["label"] for k, v in finance.LOAN_PROGRAMS.items()}
APPROVAL_LABEL = {"pof_verified": "Proof of funds verified", "full_uw": "Full underwritten approval",
                  "du_approved": "Pre-approval (DU/LP approved)", "preapproval": "Pre-approval letter",
                  "prequal": "Pre-qualification only", "none": "No approval provided"}
CRITERIA = [  # key, label, weight
    ("financing", "Financing type & down payment", 20),
    ("approval", "Approval / funds verified", 10),
    ("appraisal", "Appraisal risk", 20),
    ("contingency", "Contingency exposure", 15),
    ("deposit", "Deposit strength", 10),
    ("timeline", "Fit with seller's timeline", 10),
    ("property", "Property-condition / insurance risk", 10),
    ("agent", "Buyer agent track record", 5),
]
# Share of list price per 100 points of missing certainty, by the seller's priority.
RISK_PENALTY = {"price": 0.05, "balanced": 0.10, "speed": 0.12, "certainty": 0.15}
PAYOFF_INTEREST = 0.045  # seller's mortgage interest for holding-cost estimates (national planning figure)
IMPACT_ORDER = {"high": 0, "med": 1, "low": 2}
ACTIVE = ("active", "backup")


class OfferError(ValueError):
    """Something the analysis can't run without; the message is written for the agent."""


# --- small helpers -----------------------------------------------------------

def _d(v):
    if v in (None, "") or isinstance(v, date):
        return v or None
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def rnd(v, step=1000, how="round"):
    f = {"round": round, "up": math.ceil, "down": math.floor}[how]
    return int(f(v / step) * step)


money = finance.money


def pct(v, digits=1):
    """0.025 -> '2.5%'; trailing zeros dropped (0.03 -> '3%')."""
    s = f"{v * 100:.{digits}f}".rstrip("0").rstrip(".")
    return f"{s}%"


def fmt_when(v):
    """'2026-09-25 17:00' -> 'Sep 25, 2026 · 5:00 PM'; a date alone -> 'Sep 25, 2026'; other text passes through."""
    if not v:
        return None
    for fmt, out in (("%Y-%m-%d %H:%M", "%b %-d, %Y · %-I:%M %p"), ("%Y-%m-%d", "%b %-d, %Y")):
        try:
            return datetime.strptime(str(v)[:16 if "H" in fmt else 10], fmt).strftime(out)
        except ValueError:
            continue
    return str(v)


def prior_weekday(d):
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


class Assume:
    """Collects assumptions. impact high|med|low drives the Preliminary banner and the 'what to provide next' list."""

    def __init__(self):
        self.items = []

    def add(self, scope, field, value, why, impact="med"):
        self.items.append({"scope": scope, "field": field, "value": value, "why": why, "impact": impact})
        return value


def given(obj, key, default, A, scope, why, impact="med"):
    v = obj.get(key)
    if v is None or v == "":
        return A.add(scope, key, default, why, impact)
    return v


# --- market ------------------------------------------------------------------

_STATE_IN_ADDRESS = re.compile(r",\s*([A-Z]{2})\s+\d{5}")


def state_of(listing):
    """The property's state: `state`, else the 'FL 32750' part of the address."""
    if listing.get("state"):
        return listing["state"]
    m = _STATE_IN_ADDRESS.search(listing.get("address") or "")
    return m.group(1) if m and m.group(1) in profiles.STATES else None


# Deal-specific cost overrides in the listing file's `costs` block, mapped to market paths.
COST_KEYS = {
    "transfer_tax_rate": "closing_costs.deed_transfer_tax_rate",
    "transfer_tax_payer": "closing_costs.deed_transfer_tax_payer",
    "title_payer": "closing_costs.owner_title.payer",
    "title_estimate_pct": "closing_costs.owner_title.estimate_pct",
    "title_fees": "closing_costs.seller_title_fees",
    "hoa_estoppel_fee": "closing_costs.hoa_estoppel_fee",
    "tax_paid": "property_tax.paid",
    "insurance_rate": "holding_costs.insurance_rate",
    "utilities_monthly": "holding_costs.utilities_monthly",
    "inspection_credit_reserve_pct": "contract.inspection_credit_reserve_pct",
}


class Costs:
    """Market values with this deal's own numbers on top (a title company quote, a county's transfer tax).

    Behaves like profiles.Market for finance.seller_net (get / source / state).
    """

    def __init__(self, market, deal_costs=None):
        self.market = market
        self.over = {}
        for key, value in (deal_costs or {}).items():
            path = COST_KEYS.get(key)
            if path is None or value is None:
                continue
            if key == "title_fees" and isinstance(value, (int, float)):
                value = {"title company quote": value}
            self.over[path] = value
        if "closing_costs.owner_title.estimate_pct" in self.over:  # a deal estimate replaces the rate table
            self.over["closing_costs.owner_title.rate_tiers"] = None

    @property
    def state(self):
        return self.market.state

    @property
    def notes(self):
        return self.market.notes

    def get(self, path, default=None):
        if path in self.over:
            return self.over[path]
        return self.market.get(path, default)

    def source(self, path):
        return "deal" if path in self.over else self.market.source(path)

    def described(self, path):
        """Plain words for where a value came from: 'Florida default', 'your market profile', 'this listing'."""
        src = self.source(path)
        state = profiles.STATES.get(self.state or "", self.state or "market")
        return {"deal": "this listing", "profile": "your market profile", "state": f"{state} default",
                "county": "county default", "mls": "MLS default"}.get(src, "market default")


def load_costs(listing, market=None):
    """Costs for a listing: `market` may be a profiles.Market, a market profile path, or None."""
    if market is None or isinstance(market, str):
        market = profiles.load_market(market, state=state_of(listing), county=listing.get("county"))
    return Costs(market, listing.get("costs"))


# --- CMA handoff -------------------------------------------------------------

def apply_cma(data, h):
    """Fill the listing from a cma-handoff v1 record (value range as the appraisal range; subject facts).

    Only fills what the listing file doesn't already say, so the agent's numbers win.
    """
    data = copy.deepcopy(data)
    L = data.setdefault("listing", {})
    v, s = h["value"], h.get("subject") or {}
    L.setdefault("cma_low", v["low"])
    L.setdefault("cma_high", v["high"])
    L.setdefault("cma_mid", v["midpoint"])
    L.setdefault("cma_source", f"{h.get('source') or 'CMA'} {h.get('as_of') or ''}".strip())
    for key in ("address", "state", "county", "beds", "baths", "sqft", "year_built", "roof_year", "hoa_monthly",
                "flood_zone", "list_price", "annual_tax"):
        if s.get(key) not in (None, "") and L.get(key) in (None, ""):
            L[key] = s[key]
    mp = h.get("market_profile") or {}
    if mp.get("state") and not L.get("state"):
        L["state"] = mp["state"]
    return data


# --- listing / seller ----------------------------------------------------------

def prepare_listing(data, A, costs):
    L, S = dict(data.get("listing") or {}), dict(data.get("seller") or {})
    if not L.get("list_price"):
        raise OfferError("The list price is needed (listing.list_price).")
    lp = L["list_price"]
    today = _d(data.get("analysis_date")) or date.today()
    L["analysis_date"] = today
    L["state"] = costs.state
    L["cma_provided"] = bool(L.get("cma_low") and L.get("cma_high"))
    if not L["cma_provided"]:
        A.add("listing", "cma_low / cma_high", "list price", "No CMA range: appraisal risk is measured against list price", "high")
        L["cma_low"] = L.get("cma_low") or lp
        L["cma_high"] = L.get("cma_high") or lp
    L["cma_mid"] = L.get("cma_mid") or (L["cma_low"] + L["cma_high"]) / 2

    if L.get("annual_tax") in (None, ""):
        tax = finance.property_tax(lp, costs)
        if tax["annual"] is not None:
            L["annual_tax"] = round(tax["annual"])
            A.add("listing", "annual_tax", L["annual_tax"],
                  f"Tax bill not provided: estimated at {tax['basis'].removeprefix('about ')} ({costs.described('property_tax.fallback_rate')})", "low")
        else:
            L["annual_tax"] = None
            A.add("listing", "annual_tax", "not included", "No tax bill and no tax rate for this market: the tax proration is left out of the net", "med")
    paid = costs.get("property_tax.paid")
    L["tax_in_arrears"] = paid != "advance"
    if paid is None and L["annual_tax"]:
        A.add("listing", "tax_paid", "arrears", "How property tax is paid here wasn't given: assumed in arrears (seller credits the buyer from Jan 1)", "low")
    L["hoa_monthly"] = L.get("hoa_monthly")
    L["title_customary_payer"] = costs.get("closing_costs.owner_title.payer")
    if L["title_customary_payer"] is None:
        A.add("listing", "title_payer", "unknown", "Who customarily pays the owner's title policy wasn't given: left out of the net", "med")
    L["contract_form_default"] = "as_is" if "FR/BAR AS IS" in (costs.get("contract.forms") or []) else None
    L["reports"] = "4-point and wind-mit reports" if costs.state == "FL" else "existing inspection and insurance reports"

    S["payoff_known"] = S.get("payoff") is not None
    if not S["payoff_known"]:
        A.add("seller", "payoff", "not included", "Mortgage payoff not provided: report shows proceeds before payoff", "high")
        S["payoff"] = 0
    if S.get("listing_fee_pct") is None:
        lf = costs.get("brokerage.listing_fee_pct")
        if lf is None:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", 0,
                                         "Listing brokerage fee not provided and no market default: left out of the net", "high")
        else:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", lf,
                                         f"Listing brokerage fee not provided: assumed {pct(lf)} ({costs.described('brokerage.listing_fee_pct')})", "high")
    S["offered_buyer_broker_pct"] = S.get("offered_buyer_broker_pct")
    S["default_buyer_broker_pct"] = (S["offered_buyer_broker_pct"] if S["offered_buyer_broker_pct"] is not None
                                     else costs.get("brokerage.buyer_broker_fee_pct"))
    if S.get("holding_monthly") is None:
        ins_rate, utilities = costs.get("holding_costs.insurance_rate"), costs.get("holding_costs.utilities_monthly")
        parts = [(L["annual_tax"] or 0) / 12, (L["hoa_monthly"] or 0), S["payoff"] * PAYOFF_INTEREST / 12]
        left_out = []
        if ins_rate is None:
            left_out.append("insurance")
        else:
            parts.append(lp * ins_rate / 12)
        if utilities is None:
            left_out.append("utilities")
        else:
            parts.append(utilities)
        S["holding_monthly"] = rnd(sum(parts), 50)
        note = "Holding cost estimated from tax, insurance, HOA, utilities and loan interest"
        if left_out:
            note = f"Holding cost estimated from tax, HOA and loan interest ({' and '.join(left_out)} unknown for this market)"
        A.add("seller", "holding_monthly", f"{money(S['holding_monthly'])}/mo", note, "low")
    S["deadline"] = _d(S.get("deadline"))
    if not S["deadline"]:
        A.add("seller", "deadline", "none", "No closing deadline: timeline scored on speed alone", "med")
    S["priority"] = S.get("priority") if S.get("priority") in RISK_PENALTY else "balanced"

    rr = costs.get("contract.inspection_credit_reserve_pct")
    L["repair_reserve_pct"] = rr or 0
    if rr is None:
        A.add("listing", "inspection_credit_reserve_pct", 0,
              "No typical inspection credit for this market: the downside case leaves out post-inspection credits", "med")
    L["cost_notes"] = cost_notes(costs, L)
    return L, S


def cost_notes(costs, L):
    """Where each market cost came from, in plain words, for the fine print and the markdown summary."""
    notes = []
    rate = costs.get("closing_costs.deed_transfer_tax_rate")
    name = costs.get("closing_costs.deed_transfer_tax_label") or "Deed transfer tax"
    if rate:
        payer = costs.get("closing_costs.deed_transfer_tax_payer") or "seller"
        notes.append(f"{name} {rate * 100:.2f}%, {payer} pays ({costs.described('closing_costs.deed_transfer_tax_rate')})")
    else:
        notes.append("Deed transfer tax: not known for this market, left out")
    payer = L["title_customary_payer"]
    if payer == "seller":
        how = "promulgated rate" if costs.get("closing_costs.owner_title.rate_tiers") else "estimate"
        notes.append(f"Owner's title policy paid by the seller ({how}, {costs.described('closing_costs.owner_title.payer')})")
    elif payer:
        notes.append(f"Owner's title policy customarily paid by the {payer} ({costs.described('closing_costs.owner_title.payer')})")
    fees = costs.get("closing_costs.seller_title_fees")
    if fees:
        notes.append(f"Title company fees {money(sum(fees.values()))} ({costs.described('closing_costs.seller_title_fees')}; "
                     "the title company's quote wins)")
    return notes


# --- offers ------------------------------------------------------------------

def prepare_offer(o, L, S, A):
    o = dict(o)
    k = o.get("id", "A")
    o["id"] = k
    sc = f"offer {k}"
    if not o.get("price"):
        raise OfferError(f"Offer {k} needs a price.")
    fin = (o.get("financing") or "").lower()
    fin = finance.ALIASES.get(fin, fin)
    if fin not in FIN_LABEL:
        fin = A.add(sc, "financing", "conventional", "Financing type not provided: assumed conventional", "high")
    o["financing"] = fin
    o["financed"] = fin != "cash"
    o["status"] = o.get("status", "active")
    o["expires_raw"] = o.get("expires")
    o["expires"] = fmt_when(o.get("expires"))
    o["buyer"] = o.get("buyer") or f"Buyer {k}"
    dflt_down = {"cash": 1.0, "fha": 0.035, "va": 0.0, "usda": 0.0, "conventional": 0.10}[fin]
    o["down_pct"] = 1.0 if fin == "cash" else given(
        o, "down_pct", dflt_down, A, sc, f"Down payment not provided: assumed {dflt_down * 100:g}% for {FIN_LABEL[fin]}", "med")
    o["approval"] = given(o, "approval", "preapproval" if o["financed"] else "none", A, sc, "Approval level not provided", "med")
    o["deposit"] = o.get("deposit")
    if o["deposit"] is None:
        A.add(sc, "deposit", "unknown", "Escrow deposit not provided", "med")
    o["seller_concessions"] = given(o, "seller_concessions", 0, A, sc, "Seller concessions not provided: assumed $0", "high")
    if o.get("buyer_broker_pct") is None and o.get("buyer_broker_amount") is None:
        bb = S["default_buyer_broker_pct"]
        if bb is None:
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", 0,
                                          "Buyer-broker compensation not stated and no market default: left out of the net", "high")
        else:
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", bb, f"Buyer-broker compensation not stated: assumed {pct(bb)}", "high")
    elif o.get("buyer_broker_pct") is None:
        o["buyer_broker_pct"] = o["buyer_broker_amount"] / o["price"]
    o["home_warranty"] = o.get("home_warranty") or 0
    o["contract_form"] = o.get("contract_form") or L["contract_form_default"]
    o["inspection_days"] = given(o, "inspection_days", 10, A, sc, "Inspection period not provided: assumed 10 days", "med")
    o["loan_approval_days"] = 0 if not o["financed"] else given(
        o, "loan_approval_days", 30, A, sc, "Loan approval period not provided: assumed 30 days", "low")
    ac = o.get("appraisal_contingency")
    if ac is None and o["financed"]:
        A.add(sc, "appraisal_contingency", "21 days", "Appraisal terms not provided: assumed a 21-day contingency (conservative)", "med")
        ac = 21
    if not ac or not o["financed"]:
        o["appraisal_days"] = 0
    else:
        o["appraisal_days"] = ac if isinstance(ac, int) and ac is not True else 21
    o["appraisal_gap"] = o.get("appraisal_gap") or 0
    o["sale_contingency_days"] = o.get("sale_contingency_days") or 0
    o["kickout"] = bool(o.get("kickout"))
    eff = L["analysis_date"]
    if o.get("closing_date"):
        o["close"] = _d(o["closing_date"])
    else:
        days = o.get("closing_days") or A.add(sc, "closing_days", 45 if o["financed"] else 30, "Closing date not provided", "med")
        o["close"] = eff + timedelta(days=days)
    o["close_days"] = (o["close"] - eff).days
    o["title_by"] = o.get("title_by") or L["title_customary_payer"]
    o["risk_days"] = max(o["inspection_days"], o["loan_approval_days"], o["appraisal_days"], o["sale_contingency_days"])
    o["firm_date"] = eff + timedelta(days=o["risk_days"])
    return o


# --- money -------------------------------------------------------------------

_LINE_KEYS = {"listing_fee": "listing", "buyer_broker_fee": "bb", "transfer_tax": "transfer", "owner_title": "title",
              "title_fees": "settle", "estoppel": "estoppel"}


def net_sheet(price, conc, bb_pct, warranty, close, L, S, costs, repair=0):
    """Seller net at `price`, itemized with stable keys. Market costs come from finance.seller_net."""
    has_hoa = L["hoa_monthly"] is None or L["hoa_monthly"] > 0  # unknown HOA: charge the estoppel (conservative)
    base = finance.seller_net(price, costs, listing_fee_pct=S["listing_fee_pct"], buyer_broker_fee_pct=bb_pct, has_hoa=has_hoa)
    found = {}
    for ln in base["lines"]:
        key = _LINE_KEYS.get(ln["key"])
        if key:
            found[key] = (ln["label"], round(ln["amount"]))
    transfer = found.get("transfer", ("",))[0] or "Deed transfer tax"  # the market's own name (e.g. documentary stamp tax)
    labels = {
        "listing": f"Listing brokerage ({pct(S['listing_fee_pct'])})" if S["listing_fee_pct"] else "Listing brokerage (not provided)",
        "bb": f"Buyer-broker compensation ({pct(bb_pct, 2)})" if bb_pct else "Buyer-broker compensation",
        "transfer": transfer,
        "title": "Owner's title policy" + (" (promulgated rate)" if costs.get("closing_costs.owner_title.rate_tiers") else " (estimate)"),
        "settle": "Title company fees",
        "estoppel": "HOA estoppel",
    }
    days = (close - date(close.year, 1, 1)).days
    tax = round(L["annual_tax"] * days / 365) if L["annual_tax"] and L["tax_in_arrears"] else 0
    lines = [("price", "Offer price", price), ("conc", "Seller-paid closing costs / concessions", -conc),
             ("repair", "Post-inspection repair credit (est.)", -repair)]
    for key in ("listing", "bb", "transfer", "title", "settle", "estoppel"):
        lines.append((key, labels[key], -found.get(key, ("", 0))[1]))
    lines += [("warranty", "Home warranty", -warranty),
              ("tax", "Property-tax proration (Jan 1 → closing)", -tax),
              ("payoff", "Mortgage payoff (est.)", -S["payoff"])]
    net = sum(v for _, _, v in lines)
    months = max(0, (close - L["analysis_date"]).days) / 30
    holding = -round(S["holding_monthly"] * months)
    return {"lines": lines, "net": net, "holding": holding, "net_adj": net + holding, "close": close, "price": price,
            "missing": base["missing"]}


def downside_price(o, L):
    """Price the deal realistically closes at if the appraisal lands at the CMA midpoint."""
    if not o["financed"] or not o["appraisal_days"]:
        return o["price"]
    return min(o["price"], rnd(L["cma_mid"] + o["appraisal_gap"], 500, "down"))


# --- scoring -----------------------------------------------------------------

def auto_scores(o, L, S):
    s, why = {}, {}
    fin, down = o["financing"], o["down_pct"]
    if fin == "cash":
        s["financing"], why["financing"] = 5, "Cash: no loan contingency"
    elif fin == "conventional":
        s["financing"] = 4 if down >= .20 else (3 if down >= .05 else 2)
        why["financing"] = f"Conventional, {down:.0%} down"
    elif fin == "va":
        s["financing"], why["financing"] = 3, "VA: strong buyer profile, stricter appraisal/condition rules"
    else:
        s["financing"], why["financing"] = 2, f"{FIN_LABEL[fin]} at {down:.1%} down: thin cash cushion, stricter appraisal & condition rules"

    ap = o["approval"]
    s["approval"] = {"pof_verified": 5, "full_uw": 5, "du_approved": 4, "preapproval": 3, "prequal": 2, "none": 1}.get(ap, 3)
    why["approval"] = APPROVAL_LABEL.get(ap, ap)
    if o["financed"] and not o.get("lender_called") and s["approval"] > 3:
        s["approval"] = 3
        why["approval"] += "; not yet verified by phone"
    elif o.get("lender_called"):
        why["approval"] += "; confirmed with lender"

    if not o["financed"] or not o["appraisal_days"]:
        s["appraisal"], why["appraisal"] = 5, "No appraisal contingency"
    else:
        exposure = o["price"] - (L["cma_mid"] + o["appraisal_gap"])
        over_hi = o["price"] - L["cma_high"]
        if o["price"] <= L["cma_mid"]:
            s["appraisal"] = 5
        elif exposure <= 0:
            s["appraisal"] = 4
        elif exposure <= .01 * o["price"]:
            s["appraisal"] = 3
        elif exposure <= .025 * o["price"]:
            s["appraisal"] = 2
        else:
            s["appraisal"] = 1
        ref = "CMA high" if L["cma_provided"] else "list price"
        gap = f"{money(o['appraisal_gap'])} gap coverage" if o["appraisal_gap"] else "no gap coverage"
        why["appraisal"] = f"{money(over_hi)} over {ref}, {gap}" if over_hi > 0 else f"At/under {ref}, {gap}"

    rd = o["risk_days"]
    if o["sale_contingency_days"]:
        s["contingency"], why["contingency"] = 1, f"Contingent on sale of buyer's home ({o['sale_contingency_days']} days)"
    else:
        by_days = 5 if rd <= 7 else 4 if rd <= 14 else 3 if rd <= 30 else 2 if rd <= 45 else 1
        ins = o["inspection_days"]
        by_insp = 5 if ins <= 7 else 4 if ins <= 10 else 3 if ins <= 14 else 2  # walk-away-for-any-reason window weighs most
        s["contingency"] = min(by_days, by_insp)
        why["contingency"] = f"{rd} days until firm; {ins}-day inspection"

    if o["deposit"] is None:
        s["deposit"], why["deposit"] = 3, "Deposit not provided (assumed average)"
    else:
        p = o["deposit"] / o["price"]
        s["deposit"] = 5 if p >= .10 else 4 if p >= .03 else 3 if p >= .02 else 2 if p >= .01 else 1
        why["deposit"] = f"{money(o['deposit'])} = {p:.1%} of price"

    dl = S["deadline"]
    if dl:
        margin = (dl - o["close"]).days
        s["timeline"] = 5 if margin >= 7 else 4 if margin >= 0 else 2 if margin >= -7 else 1
        why["timeline"] = (f"{o['close']:%b %-d} close, {margin} days before {dl:%b %-d} deadline" if margin >= 0
                           else f"{o['close']:%b %-d} close is {-margin} days after {dl:%b %-d} deadline")
    else:
        cd = o["close_days"]
        s["timeline"] = 5 if cd <= 30 else 4 if cd <= 45 else 3 if cd <= 60 else 2
        why["timeline"] = f"Closes in {cd} days (no seller deadline given)"

    if not o["financed"]:
        s["property"], why["property"] = 5, "Cash: no lender insurance or condition requirements"
    else:
        v, notes = 4, []
        roof = L.get("roof_year")
        if roof:
            age = L["analysis_date"].year - roof
            if age >= 20:
                v -= 2
                notes.append(f"{age}-yr roof")
            elif age >= 14:
                v -= 1
                notes.append(f"{age}-yr roof")
        if o["financing"] in ("fha", "va", "usda"):
            v -= 1
            notes.append(f"{FIN_LABEL[o['financing']]} condition standards")
        fz = (L.get("flood_zone") or "").upper()
        if fz[:1] in ("A", "V"):
            v -= 1
            notes.append(f"flood zone {fz}")
        if o.get("insurance_quote"):
            v += 1
            notes.append("buyer has insurance quote")
        s["property"] = max(1, min(5, v))
        why["property"] = "; ".join(notes) or "No known condition or insurance issues"

    tr = (o.get("agent_track") or "").lower()
    s["agent"] = {"strong": 5, "average": 3, "weak": 2}.get(tr, 3)
    why["agent"] = o.get("agent_note") or {"strong": "Experienced, responsive",
                                           "weak": "Limited track record / slow to respond"}.get(tr, "Not assessed yet")
    return s, why


def band(score):
    return ("hi", "Strong") if score >= 80 else (("mid", "Workable") if score >= 60 else ("lo", "Weak"))


def score_offer(o, L, S):
    s, why = auto_scores(o, L, S)
    src = {k: "auto" for k in s}
    for k, v in (o.get("scores") or {}).items():
        if k not in s:
            continue
        if isinstance(v, dict):
            s[k] = v.get("score", s[k])
            why[k] = v.get("why", why[k])
            src[k] = "agent"
        elif v is not None:
            s[k] = v
            src[k] = "agent"
    total = round(sum(w * s[k] / 5 for k, _, w in CRITERIA))
    return {"scores": s, "why": why, "src": src, "total": total, "band": band(total)}


# --- flags -------------------------------------------------------------------

def flags_for(o, L, S):
    F = []

    def add(sev, issue, fix):
        F.append({"sev": sev, "issue": issue, "fix": fix})

    ref = "CMA high" if L["cma_provided"] else "list price"
    if o["financed"] and o["appraisal_days"]:
        exp = o["price"] - (L["cma_mid"] + o["appraisal_gap"])
        if o["price"] > L["cma_high"] and exp > 0:
            cover = "only " + money(o["appraisal_gap"]) if o["appraisal_gap"] else "no"
            add("High" if exp > .01 * o["price"] else "Med",
                f"Price is {money(o['price'] - L['cma_high'])} over {ref} with {cover} appraisal gap coverage.",
                "Counter with an appraisal gap clause, or treat the appraised value as the real price.")
    extras = o["seller_concessions"] + o["home_warranty"]
    if o["price"] > L["list_price"] and extras >= (o["price"] - L["list_price"]):
        add("Med", f"Concessions + warranty ({money(extras)}) cancel out the {money(o['price'] - L['list_price'])} over list.",
            "Compare on the net line, not the headline price.")
    if o["sale_contingency_days"]:
        add("High", f"Contingent on sale of buyer's home ({o['sale_contingency_days']} days)"
                    f"{'' if o['kickout'] else ' with no kick-out clause'}.",
            "Only accept with a 72-hour kick-out and a short contingency window.")
    if o["financed"] and o["approval"] in ("prequal", "none"):
        add("High" if o["approval"] == "none" else "Med", "Buyer has only a pre-qualification (or no approval).",
            "Require a full pre-approval within 3 days.")
    if o["financed"] and not o.get("lender_called"):
        add("Med", "Lender not yet called to confirm approval and closing capacity.", "Call the loan officer before responding.")
    if o["deposit"] is not None and o["deposit"] / o["price"] < .015:
        add("Med", f"Deposit is {o['deposit'] / o['price']:.1%} of price.", "Counter for 3% or a larger additional deposit.")
    roof = L.get("roof_year")
    if o["financed"] and roof and L["analysis_date"].year - roof >= 14:
        add("Med", f"{L['analysis_date'].year - roof}-yr roof: buyer's insurer may require roof work or decline coverage.",
            f"Provide a roof certification and the {L['reports']} up front.")
    fz = (L.get("flood_zone") or "").upper()
    if o["financed"] and fz[:1] in ("A", "V"):
        add("Med", f"Flood zone {fz}: lender will require flood insurance.", "Confirm the buyer has a flood quote.")
    if S["deadline"] and o["close"] > S["deadline"]:
        add("High", f"Closing {o['close']:%b %-d} is after the seller's {S['deadline']:%b %-d} deadline.", "Counter the closing date.")
    if o["close"].weekday() >= 5:
        add("Low", f"{o['close']:%b %-d} is a {o['close']:%A}.", "Move closing to the prior Friday.")
    if o["inspection_days"] >= 15:
        add("Med", f"{o['inspection_days']}-day inspection period.", "Counter to 7–10 days.")
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9:
        add("Med", f"Buyer-broker request ({o['buyer_broker_pct']:.1%}) exceeds the {ob:.1%} the seller agreed to offer.",
            "Counter to the agreed amount.")
    if any(t in o["buyer"].upper() for t in (" LLC", " INC", " TRUST", " CORP")):
        add("Low", "Entity buyer.", "Confirm signer authority and that funds are in the entity's name.")
    if o.get("escalation"):
        add("Med", "Escalation clause.", "Verify the cap, increment and proof-of-competing-offer terms; pair with gap coverage.")
    if L.get("hoa_approval_required"):
        add("Low", "HOA approval required.", "Confirm the association's approval timeline fits the closing date.")
    if o["financed"] and o.get("insurance_quote") is False:
        add("Low", "Buyer has no insurance quote yet.", "Ask for a quote before countering.")
    for f in o.get("flags") or []:
        F.append({"sev": f.get("sev", "Med"), "issue": f["issue"], "fix": f.get("fix", "")})
    order = {"High": 0, "Med": 1, "Low": 2}
    return sorted(F, key=lambda f: order.get(f["sev"], 1))


# --- counters ----------------------------------------------------------------

def propose_counter(o, L, S):
    """(terms, rows of (term, offered, counter, why)). Agent overrides in o['counter'] win."""
    t = {"price": o["price"], "seller_concessions": o["seller_concessions"], "appraisal_gap": o["appraisal_gap"],
         "deposit": o["deposit"], "inspection_days": o["inspection_days"], "home_warranty": o["home_warranty"],
         "close": o["close"], "buyer_broker_pct": o["buyer_broker_pct"], "sale_contingency_days": o["sale_contingency_days"]}
    rows = []
    lp, hi, mid = L["list_price"], L["cma_high"], L["cma_mid"]
    if o["financed"] and o["appraisal_days"] and o["price"] > hi and o["appraisal_gap"] < o["price"] - hi:
        t["price"] = rnd(hi, 1000, "down")
        rows.append(("Price", money(o["price"]), money(t["price"]), "Top of the value range, so the appraisal can support it"))
    elif o["price"] < lp:
        low_ball = L["cma_provided"] and o["price"] < L["cma_low"]
        t["price"] = lp if low_ball else rnd((o["price"] + lp) / 2, 1000, "up")
        rows.append(("Price", money(o["price"]), money(t["price"]), "Under the value range: counter at list" if low_ball else "Below list: meet partway"))
    if o["financed"] and o["appraisal_days"]:
        need = t["price"] - mid
        if need > o["appraisal_gap"] and need > 0:
            t["appraisal_gap"] = rnd(need, 1000, "up")
            rows.append(("Appraisal gap coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None", money(t["appraisal_gap"]),
                         f"Deal holds if the appraisal lands near {money(rnd(mid, 1000))}"))
    if o["seller_concessions"] > .015 * o["price"]:
        t["seller_concessions"] = rnd(o["seller_concessions"] / 2, 500)
        rows.append(("Seller concessions", money(o["seller_concessions"]), money(t["seller_concessions"]), "Biggest controllable drain on net"))
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9:
        t["buyer_broker_pct"] = ob
        rows.append(("Buyer-broker compensation", f"{o['buyer_broker_pct']:.1%}", f"{ob:.1%}", "Matches what the seller agreed to offer"))
    if o["deposit"] is not None and o["deposit"] / o["price"] < .03:
        t["deposit"] = rnd(.03 * t["price"], 1000, "up") if o["financed"] else max(o["deposit"], rnd(.05 * t["price"], 1000, "up"))
        rows.append(("Escrow deposit", money(o["deposit"]), money(t["deposit"]), "More buyer commitment once contingencies expire"))
    if o["inspection_days"] > 7:
        t["inspection_days"] = 7
        rows.append(("Inspection period", f"{o['inspection_days']} days", "7 days", f"Shorter walk-away window; seller shares the {L['reports']}"))
    if o["sale_contingency_days"]:
        t["sale_contingency_days"] = min(21, o["sale_contingency_days"])
        rows.append(("Sale-of-home contingency", f"{o['sale_contingency_days']} days" + (" + kick-out" if o["kickout"] else ""),
                     f"{t['sale_contingency_days']} days + 72-hr kick-out", "Limits how long the seller is tied up"))
    if o["financed"] and o["approval"] in ("prequal", "none"):
        rows.append(("Loan approval", APPROVAL_LABEL[o["approval"]], "Full pre-approval in 3 days", "Proves the buyer can actually borrow"))
    if o["home_warranty"]:
        t["home_warranty"] = 0
        rows.append(("Home warranty", f"Seller pays {money(o['home_warranty'])}", "Buyer pays", "Small give-back if the buyer pushes"))
    new_close = o["close"]
    if S["deadline"] and new_close > S["deadline"]:
        new_close = S["deadline"]
    new_close = prior_weekday(new_close)
    if new_close != o["close"]:
        t["close"] = new_close
        rows.append(("Closing date", f"{o['close']:%a %b %-d}", f"{new_close:%a %b %-d}",
                     "Meets the seller's deadline" if S["deadline"] and o["close"] > S["deadline"] else "Weekend closings may not fund"))
    if L["title_customary_payer"] == "seller" and o["title_by"] != "seller":
        rows.append(("Escrow / title agent", "Buyer's title co.", "Seller's title co.", "Seller pays the owner's policy, so the seller picks title"))
    ov = o.get("counter") or {}
    if ov.get("rows"):
        rows = [tuple(r) for r in ov["rows"]]
    for key in ("price", "seller_concessions", "appraisal_gap", "deposit", "inspection_days", "home_warranty", "buyer_broker_pct"):
        if key in ov:
            t[key] = ov[key]
    if "closing_date" in ov:
        t["close"] = _d(ov["closing_date"])
    return t, rows


def fallback_counter(o, main, L):
    """Cash-constrained buyer version: no gap request, price at value, keep more of their concessions."""
    if not o["financed"] or not (o["financing"] in ("fha", "va", "usda") or o["down_pct"] < .10):
        return None
    if main["appraisal_gap"] <= o["appraisal_gap"]:
        return None
    t = dict(main)
    t["price"] = min(main["price"], rnd(L["cma_mid"], 1000, "up"))
    t["appraisal_gap"] = o["appraisal_gap"]
    t["seller_concessions"] = rnd((o["seller_concessions"] + main["seller_concessions"]) / 2, 500)
    rows = [("Price", money(o["price"]), money(t["price"]), "At the value midpoint, so no gap is needed"),
            ("Appraisal gap coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None",
             money(t["appraisal_gap"]) if t["appraisal_gap"] else "None", "Buyer likely can't fund a gap"),
            ("Seller concessions", money(o["seller_concessions"]), money(t["seller_concessions"]), "Keeps closing-cost help this buyer needs")]
    return t, rows


# --- per-offer and listing-level analysis ------------------------------------

def _sheet(t, L, S, costs, repair=0):
    return net_sheet(t["price"], t["seller_concessions"], t["buyer_broker_pct"], t["home_warranty"], t["close"], L, S, costs, repair)


def analyze_offer(o, L, S, costs):
    o["ns"] = net_sheet(o["price"], o["seller_concessions"], o["buyer_broker_pct"], o["home_warranty"], o["close"], L, S, costs)
    o["downside_price"] = downside_price(o, L)
    repair = 0
    if o["contract_form"] != "standard" and o["inspection_days"] and L["repair_reserve_pct"]:
        repair = rnd(L["repair_reserve_pct"] * o["price"], 500)
    o["repair_reserve"] = repair
    o["ns_down"] = net_sheet(o["downside_price"], o["seller_concessions"], o["buyer_broker_pct"], o["home_warranty"],
                             o["close"], L, S, costs, repair)
    o["score"] = score_offer(o, L, S)
    o["flags"] = flags_for(o, L, S)
    ct, rows = propose_counter(o, L, S)
    o["counter_terms"], o["counter_rows"] = ct, rows
    o["ns_counter"] = _sheet(ct, L, S, costs)
    fb = fallback_counter(o, ct, L)
    if fb:
        o["fallback_terms"], o["fallback_rows"] = fb
        o["ns_fallback"] = _sheet(fb[0], L, S, costs)
    oc = dict(o)
    oc.update(price=ct["price"], appraisal_gap=ct["appraisal_gap"], deposit=ct["deposit"], inspection_days=ct["inspection_days"],
              sale_contingency_days=ct["sale_contingency_days"], close=ct["close"])
    oc["risk_days"] = max(oc["inspection_days"], oc["loan_approval_days"], oc["appraisal_days"], oc["sale_contingency_days"])
    oc["close_days"] = (oc["close"] - L["analysis_date"]).days
    if o["financed"] and o["approval"] in ("prequal", "none"):
        oc["approval"] = "preapproval"
    o["counter_score"] = score_offer(oc, L, S)["total"]
    return o


def target_net(L, S, costs, close):
    """A clean offer at list: no concessions, the agreed (or market) buyer-broker fee, same closing date."""
    bb = S["default_buyer_broker_pct"] or 0
    return net_sheet(L["list_price"], 0, bb, 0, close, L, S, costs)


def single_recommendation(o, tgt):
    if o.get("recommendation"):
        return o["recommendation"].upper()
    tol = 0.01 * o["price"]
    gain = o["ns_counter"]["net_adj"] - o["ns"]["net_adj"]
    if o["score"]["total"] >= 80 and (o["ns"]["net_adj"] >= tgt["net_adj"] - tol or gain < 0.005 * o["price"]):
        return "ACCEPT"  # strong offer: don't risk it over a small gain
    if not o["counter_rows"]:
        return "ACCEPT"
    return "COUNTER"


def _missing_market(costs, sheet, A):
    """Market values seller_net couldn't find, as assumptions (once)."""
    impact = {"deed transfer tax": "high", "who pays owner's title": "med", "owner's title rate": "med",
              "title company fees": "med", "HOA estoppel fee": "low"}
    for label in sheet["missing"]:
        if label == "who pays owner's title":
            continue  # already recorded in prepare_listing
        A.add("listing", label, "not included",
              f"{label[:1].upper() + label[1:]} not known for this market: left out of the net (add it, or 0 if there is none, to the market profile)",
              impact.get(label, "med"))


def check_fractions(node, where="file"):
    """Every `*_pct` value in a listing or buyer file is a fraction (0.025 = 2.5%); refuse percents written as 2.5."""
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
    for key, value in items:
        here = f"{where}.{key}" if isinstance(key, str) else f"{where}[{key}]"
        if isinstance(key, str) and key.endswith("_pct") and value is not None:
            try:
                finance.fraction(value, here)
            except ValueError as e:
                raise OfferError(str(e)) from e
        else:
            check_fractions(value, here)


def analyze(data, market=None, cma=None):
    """Full analysis of a listing file (see the skills' listing-file / buyer-file references)."""
    check_fractions(data)
    if cma:
        data = apply_cma(data, cma)
    costs = load_costs(data.get("listing") or {}, market)
    A = Assume()
    if market is None and not state_of(data.get("listing") or {}):
        A.add("listing", "state", costs.state, "Property's state not given: Florida costs assumed", "high")
    L, S = prepare_listing(data, A, costs)
    offers = [prepare_offer(o, L, S, A) for o in data.get("offers") or []]
    if not offers:
        raise OfferError("There are no offers in the listing file.")
    for o in offers:
        analyze_offer(o, L, S, costs)
    _missing_market(costs, offers[0]["ns"], A)
    active = [o for o in offers if o["status"] in ACTIVE]
    res = {"listing": L, "seller": S, "offers": offers, "active": active, "costs": costs,
           "market_notes": list(costs.notes), "sample": bool(data.get("sample"))}
    close_ref = max((o["close"] for o in active), default=L["analysis_date"] + timedelta(days=30))
    res["target"] = target_net(L, S, costs, min(close_ref, S["deadline"] or close_ref))
    for o in offers:
        o["target"] = target_net(L, S, costs, o["close"])
    pen = RISK_PENALTY[S["priority"]]
    for o in active:
        o["rank_value"] = o["ns_down"]["net_adj"] - (100 - o["score"]["total"]) / 100 * pen * L["list_price"]
    ranked = sorted(active, key=lambda o: o["rank_value"], reverse=True)
    res["ranked"] = ranked
    res["mode"] = "multi" if len(active) >= 2 else "single"
    if res["mode"] == "single":
        for o in active:
            o["action"] = single_recommendation(o, o["target"])
            o["action_reason"] = ""
    else:
        top = ranked[0]
        top["action"] = single_recommendation(top, top["target"])
        top["action_reason"] = "Best risk-adjusted net"
        for i, o in enumerate(ranked[1:], start=2):
            if i == 2 and o["score"]["total"] >= 60:
                o["action"], o["action_reason"] = "BACKUP", f"Strong enough to hold as backup to Offer {top['id']}"
            else:
                o["action"] = "DECLINE"
                why = []
                if o["sale_contingency_days"]:
                    why.append("sale-of-home contingency")
                if o["approval"] in ("prequal", "none") and o["financed"]:
                    why.append("pre-qual only")
                if S["deadline"] and o["close"] > S["deadline"]:
                    why.append(f"closes past {S['deadline']:%b %-d} deadline")
                if not why:
                    why.append(f"nets less than Offer {top['id']} once costs and risk are counted")
                text = "; ".join(why)
                o["action_reason"] = text[:1].upper() + text[1:]
        for o in ranked:
            if o.get("recommendation"):
                o["action"] = o["recommendation"].upper()
    live = {f"offer {o['id']}" for o in active}
    res["assumptions"] = [a for a in A.items if not a["scope"].startswith("offer ") or a["scope"] in live]
    res["missing"] = sorted(res["assumptions"], key=lambda a: IMPACT_ORDER[a["impact"]])
    return res


def preliminary_inputs(R, offer_id=None):
    """High-impact inputs still assumed (for the Preliminary banner), in plain names, deduplicated.

    In multi mode only the listing, the seller and the offer in question count.
    """
    names = {"cma_low / cma_high": "CMA range", "payoff": "mortgage payoff", "listing_fee_pct": "listing fee",
             "seller_concessions": "seller concessions", "buyer_broker_pct": "buyer-broker comp.",
             "financing": "financing type", "state": "property state", "deed transfer tax": "the local transfer tax (or confirm there is none)"}
    scopes = None if offer_id is None else {"listing", "seller", f"offer {offer_id}"}
    out = []
    for a in R["missing"]:
        if a["impact"] != "high" or (scopes is not None and a["scope"] not in scopes):
            continue
        n = names.get(a["field"], a["field"].replace("_", " "))
        if n not in out:
            out.append(n)
    return out
