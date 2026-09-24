"""Offer engine shared by seller-offer-review (listing side) and buyer-offer-strategy (buyer side).

    from _shared import offer_engine as oe
    R = oe.analyze(listing_file)              # dict: listing, seller, offers, ranked, mode, assumptions, ...
    R = oe.analyze(listing_file, market=path_or_Market, cma=handoff_dict)

For every offer: seller net sheet (as offered, downside, counter), certainty score, risk flags,
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

from . import contract_forms as cf, finance, profiles

FIN_LABEL = {k: v["label"] for k, v in finance.LOAN_PROGRAMS.items()}
APPROVAL_LABEL = {"pof_verified": "Proof of funds verified", "full_uw": "Full underwritten approval",
                  "du_approved": "Pre-approval (DU/LP approved)", "preapproval": "Pre-approval letter",
                  "prequal": "Pre-qualification only", "none": "No approval provided"}
CRITERIA = [  # key, label, weight
    ("financing", "Financing Type & Down Payment", 20),
    ("approval", "Approval / Funds Verified", 10),
    ("appraisal", "Appraisal Risk", 20),
    ("contingency", "Contingency Exposure", 15),
    ("deposit", "Deposit Strength", 10),
    ("timeline", "Fit with Seller's Timeline", 10),
    ("property", "Property-Condition / Insurance Risk", 10),
    ("agent", "Buyer Agent Track Record", 5),
]
# Share of list price per 100 points of missing certainty, by the seller's priority.
RISK_PENALTY = {"price": 0.05, "balanced": 0.10, "speed": 0.12, "certainty": 0.15}
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

_STATE_IN_ADDRESS = re.compile(r",\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*(?:,\s*USA?)?\s*$|,\s*([A-Z]{2})\s+\d{5}")


def state_of(listing):
    """The property's state: `state`, else the 'FL 32750' part of the address."""
    if listing.get("state"):
        return listing["state"]
    m = _STATE_IN_ADDRESS.search((listing.get("address") or "").strip())  # "…, FL 32708" or "…, Winter Springs, FL"
    st = m and (m.group(1) or m.group(2))
    return st if st in profiles.STATES else None


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

def side_note(h, want):
    """OFR-24: a sentence when a handoff was made for the other side (a buyer CMA in a listing review), else None."""
    side = h.get("side")
    if side and side != want:
        return (f"The CMA handoff is from the {side} side ({h.get('source') or 'CMA'}), not the {want} side: its value range "
                "was built for the other party. Confirm it before relying on it, or use a CMA for this side")
    return None


def apply_cma(data, h):
    """Fill the listing from a cma-handoff v1 record (value range as the appraisal range; subject facts).

    Only fills what the listing file doesn't already say, so the agent's numbers win.
    """
    data = copy.deepcopy(data)
    L = data.setdefault("listing", {})
    v, s = h["value"], h.get("subject") or {}
    for key, val in (("cma_low", v["low"]), ("cma_high", v["high"]), ("cma_mid", v["midpoint"]),
                     ("cma_source", f"{h.get('source') or 'CMA'} {h.get('as_of') or ''}".strip())):
        if L.get(key) is None:  # OFR-24: an explicit null in the file counts as missing
            L[key] = val
    data["_cma_side_note"] = side_note(h, "seller")
    for key in ("address", "state", "county", "beds", "baths", "sqft", "year_built", "roof_year", "hoa_monthly",
                "flood_zone", "list_price", "annual_tax"):
        if s.get(key) not in (None, "") and L.get(key) in (None, ""):
            L[key] = s[key]
    mp = h.get("market_profile") or {}
    if mp.get("state") and not L.get("state"):
        L["state"] = mp["state"]
    return data


# --- listing / seller ----------------------------------------------------------

NATIONAL_NORMS = {"deposit_pct": 0.01, "concessions_pct": 0.03, "inspection_days": 10, "loan_approval_days": 30}


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
            arrears = costs.get("property_tax.paid") != "advance"
            A.add("listing", "annual_tax", "not included", "No tax bill and no tax rate for this market: the tax proration is left out of the net"
                  + (" (paid in arrears, so the seller's credit to the buyer can be large)" if arrears else ""), "high" if arrears else "med")
    paid = costs.get("property_tax.paid")
    L["tax_in_arrears"] = paid != "advance"
    if paid is None and L["annual_tax"]:
        A.add("listing", "tax_paid", "arrears", "How property tax is paid here wasn't given: assumed in arrears (seller credits the buyer from Jan 1)", "low")
    L["bill_paid"] = L.get("current_tax_bill_paid")  # this year's bill already paid by the seller (Florida: from November)
    L["property_type"] = L.get("property_type")
    L["condo"] = finance.property_type(L["property_type"]) == "condo"  # CMA-5: condo rider, project approval, rescission
    L["condo_rules"] = costs.get("condo") or {}
    L["flood_disclosure_rule"] = costs.get("flood.seller_disclosure")  # CMA-6: Florida s. 689.302
    L["flood_disclosure"] = L.get("flood_disclosure")  # true once the seller's disclosure has been given to the buyer
    L["hoa_monthly"] = L.get("hoa_monthly")
    L["title_customary_payer"] = costs.get("closing_costs.owner_title.payer")
    if L["title_customary_payer"] is None:
        A.add("listing", "title_payer", "unknown", "Who customarily pays the owner's title policy wasn't given: left out of the net", "med")
    for w in finance.seller_net(lp, costs)["warnings"]:  # CORE-9: a title quote below the published rate
        A.add("listing", "owner_title.quote", "check", w, "med")
    L["loan_limits"] = profiles.loan_limits()
    L["frbar_market"] = cf.frbar_market(costs.get("contract.forms"))
    L["reports"] = "4-point and wind-mit reports" if costs.state == "FL" else "existing inspection and insurance reports"
    # OFR-15: one set of benchmarks for the review and the counter, from the market; national planning norms otherwise
    L["norms"] = {**NATIONAL_NORMS, **{k: v for k, v in (costs.get("offer_norms") or {}).items() if v is not None}}
    if costs.get("offer_norms.deposit_pct") is None and costs.get("contract.typical_deposit_pct") is not None:
        L["norms"]["deposit_pct"] = costs.get("contract.typical_deposit_pct")
    L["norms_source"] = "market" if costs.get("offer_norms") else "national"
    if L["norms_source"] == "national":
        A.add("listing", "offer_norms", "national estimates", "No offer benchmarks for this market: deposit, concessions, "
              "inspection and loan approval are compared with national planning norms (1% deposit, 3% concessions, 10 and "
              "30 days). Add the local norms to the market profile", "med")
    L["deposit_norm"] = L["norms"]["deposit_pct"]

    S["payoff_known"] = S.get("payoff") is not None
    if not S["payoff_known"]:
        A.add("seller", "payoff", "not included", "Mortgage payoff not provided: report shows proceeds before payoff", "high")
        S["payoff"] = 0
    if S.get("listing_fee_pct") is None:
        lf = costs.get("brokerage.listing_fee_pct")
        if lf is None:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", 0,
                                         "Listing brokerage fee not provided (nothing is built in; commissions are negotiable): "
                                         "left out of the net. Ask for the listing agreement's fee", "high")
        else:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", lf,
                                         f"Listing brokerage fee not provided: assumed {pct(lf)}, the agent's standard terms ({costs.described('brokerage.listing_fee_pct')})", "high")
    S["offered_buyer_broker_pct"] = S.get("offered_buyer_broker_pct")
    S["default_buyer_broker_pct"] = (S["offered_buyer_broker_pct"] if S["offered_buyer_broker_pct"] is not None
                                     else costs.get("brokerage.buyer_broker_fee_pct"))  # the agent's own terms; none built in
    if S.get("holding_monthly") is None:
        monthly, left_out = finance.holding_monthly(lp, costs, S["payoff"], L["hoa_monthly"])
        S["holding_monthly"] = rnd(monthly, 50)
        note = "Holding cost estimated from insurance, HOA, utilities and loan interest (tax is in the proration)"
        if left_out:
            note = f"Holding cost estimated from HOA and loan interest ({' and '.join(left_out)} unknown for this market; tax is in the proration)"
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
    elif rate == 0:
        notes.append(f"No deed transfer tax in this market ({costs.described('closing_costs.deed_transfer_tax_rate')})")
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


# --- offer labels --------------------------------------------------------------
# Offers are named the way listing agents talk about them: by the buyer's agent and brokerage, never by the
# buyer (fair housing). The id stays an internal key; a one- or two-character id doubles as the chart key.

NAME_PARTICLES = {"de", "del", "della", "da", "di", "do", "dos", "du", "la", "le", "van", "von", "der", "den", "st.", "st"}
NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def surname(name):
    """'J. Morales' -> 'Morales'; 'Ana de la Cruz' -> 'de la Cruz'; 'Tom Hill Jr.' -> 'Hill'."""
    toks = [t.strip(",") for t in name.split() if t.strip(",")]
    while len(toks) > 1 and toks[-1].lower() in NAME_SUFFIXES:
        toks.pop()
    i = len(toks) - 1
    while i > 1 and toks[i - 1].lower() in NAME_PARTICLES:
        i -= 1
    return " ".join(toks[i:])


def short_price(v):
    """$432K, $432.5K, $1.25M."""
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    k = round(v / 100) / 10
    return f"${k:,.0f}K" if k == int(k) else f"${k:,.1f}K"


def apply_escalations(offers, L):
    """Price each escalating offer at what it would actually reach (OFR-2): the lower of its cap and the best competing
    active offer's base price plus its increment, never below its own base. Escalations don't chain: competing prices
    are the other offers' base prices. Everything after this (net, score, rank, counter) uses the effective price."""
    live = [o for o in offers if o["status"] in ACTIVE]
    base = {id(o): o["price"] for o in live}
    for o in live:
        e = o.get("escalation")
        if not e:
            continue
        inc, cap, issues = e.get("increment"), e.get("cap"), []
        if not cap:
            issues.append(("High", "Escalation clause with no cap.", "Ask for the cap in writing before relying on the clause."))
        if not inc:
            issues.append(("Med", "Escalation clause with no increment.", "Ask for the increment over a competing offer."))
        if e.get("proof") is None:
            issues.append(("Med", "The escalation clause doesn't say how a competing offer is proven.",
                           "Require a redacted copy of the competing offer's signature page and price terms."))
        others = [base[id(x)] for x in live if x is not o]
        o["price_base"] = p0 = o["price"]
        eff = p0
        if cap and inc and others and max(others) + inc > p0:
            eff = min(cap, max(others) + inc)
        o["price"], o["escalated"] = eff, eff > p0
        o["escalation_note"] = (f"Escalates to {money(eff)} from {money(p0)} (cap {money(cap)})" if eff > p0 else
                                f"Escalation to {money(cap)} not triggered by the other offers" if cap else "Escalation clause")
        if o.get("buyer_broker_amount"):
            o["buyer_broker_pct"] = o["buyer_broker_amount"] / eff
        if o["contract_form"] == cf.STANDARD:
            o["repair_limits"] = cf.repair_limits(eff, o)
        if cap and o["appraisal_risk"] and cap > appraisal_line(L) + o["gap_cover"]:
            issues.append(("Med", f"The cap ({money(cap)}) is above what the value range and gap coverage support "
                                  f"({money(appraisal_line(L) + o['gap_cover'])}).",
                           "Ask for gap coverage that rises with the escalated price, or treat the appraisal as the ceiling."))
        o["escalation_issues"] = issues


def label_offers(offers):
    """Set label ('Morales · Keller Williams'), ref ('the Morales (Keller Williams) offer') and key ('A') on each offer.

    Label order: the agent's `label`; else the buyer's agent's surname and brokerage; else price and financing
    ('$432K FHA'). Offers that would share a label get the price and financing added, then the key.
    """
    for i, o in enumerate(offers):
        k = str(o["id"])
        o["key"] = k if len(k) <= 2 else chr(65 + i % 26)
        agent, firm = (o.get("buyer_agent") or "").strip(), (o.get("buyer_brokerage") or "").strip()
        if agent and not firm and " · " in agent:
            agent, firm = (x.strip() for x in agent.split(" · ", 1))
        who = surname(agent) if agent else ""
        tag = f"{short_price(o['price'])} {FIN_LABEL[o['financing']]}"
        custom = re.sub(r"\s+offer$", "", (o.get("label") or "").strip(), flags=re.I)
        o["_name"] = {"custom": custom, "who": who, "firm": firm, "tag": tag, "extra": []}
    def base(n):
        return n["custom"] or " · ".join(x for x in (n["who"], n["firm"]) if x) or n["tag"]
    for step in ("tag", "key"):
        seen = {}
        for o in offers:
            seen.setdefault(base(o["_name"]) + "|" + "|".join(o["_name"]["extra"]), []).append(o)
        for group in seen.values():
            if len(group) > 1:
                for o in group:
                    n = o["_name"]
                    if step == "key" or base(n) != n["tag"]:
                        n["extra"].append(n["tag"] if step == "tag" else o["key"])
    for o in offers:
        n = o.pop("_name")
        extra = [x for x in n["extra"] if x != base(n)]
        o["label"] = base(n) + (f", {', '.join(extra)}" if extra else "")
        if not n["custom"] and n["who"] and n["firm"]:
            o["ref"] = f"the {n['who']} ({', '.join([n['firm']] + extra)}) offer"
        else:
            o["ref"] = f"the {o['label']} offer"


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
    o["buyer"] = (o.get("buyer") or "").strip()
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
        o["bb_tag"] = "Assumed"
        if bb is None:
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", 0,
                                          "Buyer-broker compensation not stated, and nothing offered by the seller or set in the "
                                          "agent's market profile: left out of the net. Commissions are negotiable: ask", "high")
        else:
            src = "what the seller offered" if S["offered_buyer_broker_pct"] is not None else "the agent's standard terms"
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", bb, f"Buyer-broker compensation not stated: assumed {pct(bb)} ({src})", "high")
    else:
        o["bb_tag"] = "Requested"
        if o.get("buyer_broker_pct") is None:
            o["buyer_broker_pct"] = o["buyer_broker_amount"] / o["price"]
    o["home_warranty"] = o.get("home_warranty") or 0
    # One form per offer, and only that form's rules (contract_forms): AS IS and Standard math never mix.
    form = cf.normalize(o.get("contract_form"))
    if form is None:
        form = A.add(sc, "contract_form", cf.AS_IS,
                     "Contract form not given: assumed FR/BAR AS IS. The Standard form has no inspection walk-away and makes "
                     "the seller pay repairs up to its repair limits, so confirm which form was used", "high") \
            if L["frbar_market"] else cf.OTHER
    o["contract_form"] = form
    o["inspection_walkaway"] = cf.inspection_walkaway(form, o)
    if form == cf.STANDARD:
        try:
            o["repair_limits"] = cf.repair_limits(o["price"], o)
        except cf.FormError as e:
            raise OfferError(f"Offer {o.get('id', '?')}: {e}") from e
    o["inspection_assumed"] = o.get("inspection_days") in (None, "")
    o["inspection_days"] = given(o, "inspection_days", 10, A, sc, "Inspection period not provided: assumed 10 days", "med")
    o["loan_approval_days"] = 0 if not o["financed"] else given(
        o, "loan_approval_days", 30, A, sc, "Loan approval period not provided: assumed 30 days", "low")
    ac = o.get("appraisal_contingency")
    if ac is None and o["financed"]:
        A.add(sc, "appraisal_contingency", "21 days", "Appraisal terms not provided: assumed a 21-day contingency (conservative)", "med")
        ac = 21
    # FHA and VA: the amendatory clause / escape clause can't be waived; the buyer may walk if the appraisal is low
    # up to closing, so a waiver is ignored and a gap clause is stated intent only (OFR-3, OFR-17).
    o["appraisal_protected"] = o["financed"] and o["financing"] in ("fha", "va")
    if o["appraisal_protected"] and ac is False:
        A.add(sc, "appraisal_contingency", "protected to closing",
              f"{FIN_LABEL[o['financing']]} appraisal protection can't be waived (amendatory clause): treated as protected to closing",
              "med")
    o["appraisal_waived"] = o["financed"] and not o["appraisal_protected"] and ac is False
    if not ac or not o["financed"]:
        o["appraisal_days"] = 0
    else:
        o["appraisal_days"] = ac if isinstance(ac, int) and ac is not True else 21
    o["appraisal_gap"] = o.get("appraisal_gap") or 0
    if o["appraisal_protected"]:
        o["gap_cover"] = 0
    elif o["appraisal_waived"]:  # credited only up to the buyer's documented cash beyond down payment and closing costs
        funds = o.get("gap_funds")
        if funds is None:
            funds = A.add(sc, "gap_funds", 0, "Appraisal waived on a financed offer, but the buyer's cash beyond the down payment "
                          "and closing costs isn't documented: the waiver covers a low appraisal only up to documented funds",
                          "med")
        o["gap_cover"] = funds
    else:
        o["gap_cover"] = o["appraisal_gap"]
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
    if o["appraisal_protected"]:
        o["appraisal_days"] = o["close_days"]  # protection runs to closing
    o["appraisal_risk"] = o["financed"] and bool(o["appraisal_days"] or o["appraisal_waived"])
    o["risk_days"] = risk_days(o)
    o["firm_date"] = eff + timedelta(days=o["risk_days"])
    return o


def risk_days(o):
    """Days until the buyer can no longer get the deposit back under a contingency.

    An inspection walk-away (AS IS, an option period) counts in full. The Standard form has none, but either party
    may terminate when repairs exceed a limit, which runs at least to the repair election (notice + 10 + 5 days).
    Another contract without a walk-away doesn't count the inspection period."""
    if o["inspection_walkaway"]:
        insp = o["inspection_days"]
    elif o["contract_form"] == cf.STANDARD and o["inspection_days"]:
        insp = o["inspection_days"] + cf.STANDARD_REPAIR_WINDOW_DAYS
    else:
        insp = 0
    return max(insp, o["loan_approval_days"], o["appraisal_days"], o["sale_contingency_days"])


def repair_reserve(o, L):
    """The downside case's repair cost to the seller, by form.

    AS IS: the market's typical post-inspection credit. Standard: the General Repair Limit the seller owes. Another
    contract: the market's figure only when the market's rules aren't FR/BAR (the agent's own number for their
    contract); a Florida AS IS figure never applies to a Standard or another form."""
    if not o["inspection_days"]:
        return 0, None
    if o["contract_form"] == cf.STANDARD:
        return rnd(o["repair_limits"]["general"], 500), "Repairs up to the General Repair Limit (Standard)"
    if o["contract_form"] == cf.AS_IS or not L["frbar_market"]:
        if L["repair_reserve_pct"]:
            return rnd(L["repair_reserve_pct"] * o["price"], 500), "Post-Inspection Repair Credit (Est.)"
    return 0, None


# --- money -------------------------------------------------------------------

_LINE_KEYS = {"listing_fee": "listing", "buyer_broker_fee": "bb", "transfer_tax": "transfer", "transfer_surtax": "surtax",
              "owner_title": "title", "title_fees": "settle", "estoppel": "estoppel"}


def net_sheet(price, conc, bb_pct, warranty, close, L, S, costs, repair=0, repair_label=None, bb_tag=None):
    """Seller net at `price`, itemized with stable keys. Market costs and the tax proration come from finance."""
    has_hoa = L["hoa_monthly"] is None or L["hoa_monthly"] > 0  # unknown HOA: charge the estoppel (conservative)
    base = finance.seller_net(price, costs, listing_fee_pct=S["listing_fee_pct"], buyer_broker_fee_pct=bb_pct, has_hoa=has_hoa,
                              annual_tax=L["annual_tax"] if L["tax_in_arrears"] else None, closing=close,
                              bill_paid=L["bill_paid"], prop_type=L["property_type"])
    found = {}
    for ln in base["lines"]:
        key = _LINE_KEYS.get(ln["key"])
        if key:
            found[key] = (ln["label"], round(ln["amount"]))
    transfer = found.get("transfer", ("",))[0] or "Deed Transfer Tax"  # the market's own name (e.g. documentary stamp tax)
    labels = {
        "listing": f"Listing Brokerage ({pct(S['listing_fee_pct'])})" if S["listing_fee_pct"] else "Listing Brokerage (Not Provided)",
        "bb": (f"Buyer-Broker Compensation ({pct(bb_pct, 2)}" + (f", {bb_tag})" if bb_tag else ")")) if bb_pct
              else "Buyer-Broker Compensation",
        "transfer": transfer,
        "title": "Owner's Title Policy" + (" (Quote)" if "(Quote)" in found.get("title", ("",))[0] else
                                           " (Promulgated Rate)" if costs.get("closing_costs.owner_title.rate_tiers") else " (Estimate)"),
        "settle": "Title Company Fees",
        "estoppel": "HOA Estoppel",
    }
    tax_label = next((ln["label"] for ln in base["lines"] if ln["key"] == "tax_proration"), "Property Tax Proration")
    tax = next((round(ln["amount"]) for ln in base["lines"] if ln["key"] == "tax_proration"), 0)
    lines = [("price", "Offer Price", price), ("conc", "Seller-Paid Closing Costs / Concessions", -conc),
             ("repair", repair_label or "Post-Inspection Repair Credit (Est.)", -repair)]
    for key in ("listing", "bb", "transfer", "surtax", "title", "settle", "estoppel"):
        if key == "surtax" and key not in found:
            continue
        lines.append((key, labels.get(key) or found[key][0], -found.get(key, ("", 0))[1]))
    lines += [("warranty", "Home Warranty", -warranty),
              ("tax", tax_label, -tax),
              ("payoff", "Mortgage Payoff (Est.)", -S["payoff"])]
    net = sum(v for _, _, v in lines)
    months = max(0, (close - L["analysis_date"]).days) / 30
    holding = -round(S["holding_monthly"] * months)
    return {"lines": lines, "net": net, "holding": holding, "net_adj": net + holding, "close": close, "price": price,
            "missing": base["missing"]}


def appraisal_line(L):
    """Where appraisal risk starts: the top of the supported value range (OFR-4). A price at or under it is expected
    to appraise; above it, the part the buyer doesn't cover is at risk. Both offer skills use this one line."""
    return L["cma_high"]


def downside_price(o, L):
    """Price the deal realistically closes at if the appraisal lands at the top of the value range."""
    if not o["appraisal_risk"]:
        return o["price"]
    return min(o["price"], rnd(appraisal_line(L) + o["gap_cover"], 500, "down"))


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
        s["financing"], why["financing"] = 3, ("VA financing: Tidewater notice before a low appraisal is final; "
                                               "stricter appraisal and condition rules")
    else:
        s["financing"], why["financing"] = 2, (f"{FIN_LABEL[fin]}, {down:.1%} down" + (": appraisal protection to closing" if fin == "fha" else "")
                                  + ", stricter appraisal and condition rules")

    ap = o["approval"]
    s["approval"] = {"pof_verified": 5, "full_uw": 5, "du_approved": 4, "preapproval": 3, "prequal": 2, "none": 1}.get(ap, 3)
    why["approval"] = APPROVAL_LABEL.get(ap, ap)
    if o["financed"] and not o.get("lender_called") and s["approval"] > 3:
        s["approval"] = 3
        why["approval"] += "; not yet verified by phone"
    elif o.get("lender_called"):
        why["approval"] += "; confirmed with lender"

    if not o["appraisal_risk"]:
        s["appraisal"], why["appraisal"] = 5, "No appraisal contingency"
    else:
        exposure = o["price"] - (appraisal_line(L) + o["gap_cover"])
        over_hi = o["price"] - appraisal_line(L)
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
        if o["appraisal_protected"]:
            gap = "protected to closing; gap clause is intent only" if o["appraisal_gap"] else "protected to closing"
        elif o["appraisal_waived"]:
            gap = f"waived, {money(o['gap_cover'])} documented to cover a low appraisal"
        else:
            gap = f"{money(o['appraisal_gap'])} gap coverage" if o["appraisal_gap"] else "no gap coverage"
        why["appraisal"] = f"{money(over_hi)} over {ref}, {gap}" if over_hi > 0 else f"At/under {ref}, {gap}"

    rd = o["risk_days"]
    if o["sale_contingency_days"]:
        s["contingency"], why["contingency"] = 1, f"Contingent on sale of buyer's home ({o['sale_contingency_days']} days)"
    else:
        by_days = 5 if rd <= 7 else 4 if rd <= 14 else 3 if rd <= 30 else 2 if rd <= 45 else 1
        ins = o["inspection_days"]
        if o["inspection_walkaway"]:
            by_insp = 5 if ins <= 7 else 4 if ins <= 10 else 3 if ins <= 14 else 2  # walk-away-for-any-reason window weighs most
            s["contingency"] = min(by_days, by_insp)
            why["contingency"] = f"{rd} days until firm; {ins}-day inspection"
        else:  # repair notices only (Standard): risk_days already runs through the repair election
            s["contingency"] = by_days
            why["contingency"] = f"{rd} days until firm; {ins}-day repair-notice period, no walk-away"

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
        if o.get("insurance_quote") is True:  # OFR-18: a planned quote isn't scored until it's in hand
            v += 1
            notes.append("buyer has insurance quote")
        elif o.get("insurance_quote") == "planned":
            notes.append("insurance quote planned before submitting (scored once in hand)")
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

# --- contract completeness ------------------------------------------------------
# Blocking = the contract can't be reviewed as written (unsigned, missing pages, price blank...). A blocked
# offer gets no recommendation, counter or ranking: only the list of what to fix. Whether a contract is
# legally valid is for an attorney; the skill only says it can't review it as written.

CONTRACT_SEV = ("Blocking", "High", "Med", "Low")


def _has_rider(riders, *words):
    text = " | ".join(riders).lower()
    return any(w in text for w in words)


def as_request(fix):
    """'Ask the buyer's agent to fill in 2(b).' -> 'Please fill in 2(b).' for the buyer's agent list."""
    fix = fix.strip()
    m = re.match(r"^Ask (?:the buyer's agent |the buyer )?(to|for) (.+)", fix)
    if not m:
        return fix or None
    return ("Please " if m.group(1) == "to" else "Please send ") + m.group(2)


def contract_checks(o, L):
    """Rider and consistency checks the extracted fields can prove, plus the agent's `contract_issues` from reading
    the document. Rider checks run only when the offer lists its riders (a chat summary may not)."""
    F = []

    def add(sev, issue, fix, check, request=None):
        """`request` is what to ask the buyer's agent for; None when the fix is on the listing side."""
        F.append({"sev": sev, "issue": issue, "fix": fix, "check": check, "contract": True, "request": request})

    riders = o.get("riders") or []
    if riders:
        if o["financing"] in ("fha", "va") and not _has_rider(riders, "fha", "va "):
            add("High", f"{FIN_LABEL[o['financing']]} financing without an FHA/VA rider.", "Ask for the signed FHA/VA financing rider.", "riders",
                "Please send the signed FHA/VA financing rider.")
        if o["sale_contingency_days"] and not _has_rider(riders, "sale of buyer", "sale of other", "contingent on sale"):
            add("High", "Sale-of-home contingency without its rider.", "Ask for the signed Sale of Buyer's Property rider.", "riders",
                "Please send the signed Sale of Buyer's Property rider.")
        if o["financing"] == "conventional" and o["appraisal_days"] and o.get("appraisal_contingency") not in (None, "") \
                and not _has_rider(riders, "apprais"):
            add("Med", "Appraisal period stated without an appraisal rider.", "Ask which appraisal terms apply, and for the rider.", "riders",
                "Which appraisal terms apply? Please send the appraisal rider.")
        if L["condo"] and not _has_rider(riders, "condo"):
            add("High", "The property is a condo but no condo rider is attached.",
                "Ask for the signed condo rider, and deliver the association documents as soon as it's signed.", "riders",
                "Please attach the signed condominium rider.")
        elif L.get("hoa_monthly") and not _has_rider(riders, "hoa", "homeowner", "condo", "community"):
            add("High", "The property has an HOA but no HOA or condo rider is attached.",
                "Add the HOA or condo rider, and give the buyer the required HOA disclosure, before accepting.", "riders")
        yb = L.get("year_built")
        if yb and yb < 1978 and not _has_rider(riders, "lead"):
            add("High", f"Built {yb}: no lead-based paint disclosure attached (federally required before 1978).",
                "Complete the lead-based paint disclosure with the seller and have the buyer sign it before accepting.", "riders")
    if L["condo"] and o["financing"] in ("fha", "va"):
        fin = FIN_LABEL[o["financing"]]
        add("High", f"{fin} loan on a condo: the project must be {fin}-approved.",
            "Confirm the project's approval before accepting; an unapproved project can't close with this loan.", "terms",
            f"Please confirm the lender has verified the condo project's {fin} approval.")
    loan = o.get("loan_amount")
    if loan and o["financed"] and abs(loan - o["price"] * (1 - o["down_pct"])) > max(1000, .01 * o["price"]):
        add("Med", f"Loan amount {money(loan)} doesn't match {pct(o['down_pct'])} down on {money(o['price'])}.",
            "Ask the buyer's agent to correct the financing figures.", "terms",
            "Please correct the loan amount or down payment in the financing section.")
    if o["financed"] and o["loan_approval_days"] and o["loan_approval_days"] > o["close_days"]:
        add("Med", f"Loan approval period ({o['loan_approval_days']} days) ends after closing ({o['close_days']} days).",
            "Ask for a loan approval date before closing.", "terms", "Can the loan approval date move before closing?")
    for c in o.get("contract_issues") or []:
        sev = c.get("sev", "High")
        sev = sev if sev in CONTRACT_SEV else "High"
        add(sev, c["issue"], c.get("fix", ""), c.get("check", "signed" if sev == "Blocking" else "terms"),
            c.get("request") or (as_request(c.get("fix", "")) if sev in ("Blocking", "High") else None))
    return F


def flags_for(o, L, S):
    F = []

    def add(sev, issue, fix):
        F.append({"sev": sev, "issue": issue, "fix": fix})

    ref = "CMA high" if L["cma_provided"] else "list price"
    if o["appraisal_risk"]:
        exp = o["price"] - (appraisal_line(L) + o["gap_cover"])
        if exp > 0:
            cover = "only " + money(o["gap_cover"]) if o["gap_cover"] else "no"
            what = ("documented cash behind the appraisal waiver" if o["appraisal_waived"] else
                    "appraisal gap coverage the buyer is bound to" if o["appraisal_protected"] else "appraisal gap coverage")
            add("High" if exp > .01 * o["price"] else "Med",
                f"Price is {money(o['price'] - appraisal_line(L))} over {ref} with {cover} {what}.",
                "Counter with an appraisal gap clause, or treat the appraised value as the real price." if not o["appraisal_protected"]
                else "Treat the appraised value as the real price: the FHA/VA rider lets the buyer walk if it comes in low.")
    if o["appraisal_protected"] and o["appraisal_gap"]:
        add("Med", f"{FIN_LABEL[o['financing']]} appraisal gap clause ({money(o['appraisal_gap'])}): the buyer can still cancel "
                   "if the appraisal is low (amendatory clause), so it shows intent only.",
            "Ask for proof of funds for the gap; don't count it in the net.")
    cap = finance.concession_cap(o["financing"], o["down_pct"])  # OFR-12
    if cap is not None and o["seller_concessions"] > cap * o["price"] + 1:
        over = o["seller_concessions"] - cap * o["price"]
        add("High", f"Concessions ({money(o['seller_concessions'])}) exceed the {FIN_LABEL[o['financing']]} limit of "
                    f"{pct(cap)} at {pct(o['down_pct'])} down ({money(cap * o['price'])}): {money(over)} can't be used.",
            "Counter the concessions down to the limit, or the price down by the excess.")
    if o["financed"]:
        note = finance.loan_limit_note(o.get("loan_amount") or finance.loan_amount(o["price"], o["financing"], o["down_pct"]),
                                       o["financing"], L["loan_limits"], L.get("state"), L.get("county"))
        if note:  # OFR-11
            add("High" if "can't be FHA" in note else "Med", note, "Ask the buyer's agent for the lender's confirmation.")
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
    if o["deposit"] is not None and o["deposit"] / o["price"] < L["deposit_norm"] / 2:
        add("Med", f"Deposit is {o['deposit'] / o['price']:.1%} of price.", f"Counter for {pct(L['deposit_norm'])} or a larger additional deposit.")
    roof = L.get("roof_year")
    if o["financed"] and roof and L["analysis_date"].year - roof >= 14:
        if o.get("insurance_quote") is True:
            add("Low", f"{L['analysis_date'].year - roof}-yr roof: the buyer has a quote; confirm it covers the roof as is.",
                "Ask the buyer's agent for the quote's roof conditions.")
        else:
            add("Med", f"{L['analysis_date'].year - roof}-yr roof: buyer's insurer may require roof work or decline coverage.",
                f"Provide a roof certification and the {L['reports']} up front.")
    fz = (L.get("flood_zone") or "").upper()
    if o["financed"] and fz[:1] in ("A", "V"):
        add("Med", f"Flood zone {fz}: lender will require flood insurance.", "Confirm the buyer has a flood quote.")
    rule = L["flood_disclosure_rule"]
    if rule and L["flood_disclosure"] is not True:  # the listing side's job: no request to the buyer's agent
        add("Med", f"The seller's flood disclosure ({rule.get('statute', 'state law')}) isn't confirmed as given.",
            "Have the seller complete it (" + rule.get("asks", "flood history") + ") and give it to the buyer at or before signing.")
    if L["condo"]:
        cr = L["condo_rules"]
        if cr.get("rescission"):
            add("Med", "Condo: " + cr["rescission"].rstrip(".") + ".",
                "Deliver the association documents" + (", the milestone summary and the SIRS" if cr.get("sirs_milestone") else "")
                + " right after acceptance: the deal isn't firm until the buyer's windows pass.")
    if S["deadline"] and o["close"] > S["deadline"]:
        add("High", f"Closing {o['close']:%b %-d} is after the seller's {S['deadline']:%b %-d} deadline.", "Counter the closing date.")
    if o["close"].weekday() >= 5:
        add("Low", f"{o['close']:%b %-d} is a {o['close']:%A}.", "Move closing to the prior Friday.")
    if o["inspection_days"] >= 15:
        add("Med", f"{o['inspection_days']}-day inspection period.", "Counter to 7–10 days.")
    if o["contract_form"] == cf.STANDARD:
        lim = o["repair_limits"]
        add("Med", f"Standard contract: the seller pays repairs up to {money(lim['general'])} general, {money(lim['wdo'])} WDO "
                   f"and {money(lim['permit'])} permits (Para. 9(a)).", "Price that in, or counter on the AS IS form.")
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9:
        add("Med", f"Buyer-broker request ({o['buyer_broker_pct']:.1%}) exceeds the {ob:.1%} the seller agreed to offer.",
            "Counter to the agreed amount.")
    if any(t in o["buyer"].upper() for t in (" LLC", " INC", " TRUST", " CORP")):
        add("Low", "Entity buyer.", "Confirm signer authority and that funds are in the entity's name.")
    if o.get("escalation"):
        for sev, issue, fix in o.get("escalation_issues") or []:
            add(sev, issue, fix)
        add("Low", o["escalation_note"] + ".", "Confirm the competing offer's price terms before signing.")
    if L.get("hoa_approval_required"):
        add("Low", "HOA approval required.", "Confirm the association's approval timeline fits the closing date.")
    if o["financed"] and o.get("insurance_quote") is False:
        add("Low", "Buyer has no insurance quote yet.", "Ask for a quote before countering.")
    for f in o.get("flags") or []:
        F.append({"sev": f.get("sev", "Med"), "issue": f["issue"], "fix": f.get("fix", "")})
    F += contract_checks(o, L)
    order = {"Blocking": -1, "High": 0, "Med": 1, "Low": 2}
    return sorted(F, key=lambda f: order.get(f["sev"], 1))


# --- counters ----------------------------------------------------------------

def propose_counter(o, L, S):
    """(terms, rows of (term, offered, counter, why)). Agent overrides in o['counter'] win."""
    t = {"price": o["price"], "seller_concessions": o["seller_concessions"], "appraisal_gap": o["appraisal_gap"],
         "deposit": o["deposit"], "inspection_days": o["inspection_days"], "home_warranty": o["home_warranty"],
         "close": o["close"], "buyer_broker_pct": o["buyer_broker_pct"], "sale_contingency_days": o["sale_contingency_days"]}
    rows = []
    lp, hi, mid = L["list_price"], L["cma_high"], L["cma_mid"]
    if o["appraisal_risk"] and o["price"] > hi and o["gap_cover"] < o["price"] - hi:
        t["price"] = rnd(hi, 1000, "down")
        rows.append(("Price", money(o["price"]), money(t["price"]), "Top of the value range, so the appraisal can support it"))
    elif o["price"] < lp:
        low_ball = L["cma_provided"] and o["price"] < L["cma_low"]
        t["price"] = lp if low_ball else rnd((o["price"] + lp) / 2, 1000, "up")
        rows.append(("Price", money(o["price"]), money(t["price"]), "Under the value range: counter at list" if low_ball else "Below list: meet partway"))
    if o["appraisal_risk"] and not o["appraisal_protected"]:  # an FHA/VA gap clause wouldn't bind the buyer
        need = t["price"] - hi
        if need > o["gap_cover"] and need > 0:
            t["appraisal_gap"] = rnd(need, 1000, "up")
            rows.append(("Appraisal Gap Coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None", money(t["appraisal_gap"]),
                         f"Deal holds if the appraisal lands at {money(rnd(hi, 1000))}"))
    N = L["norms"]
    if o["seller_concessions"] > N["concessions_pct"] * o["price"] + 1:
        t["seller_concessions"] = rnd(o["seller_concessions"] / 2, 500)
        rows.append(("Seller Concessions", money(o["seller_concessions"]), money(t["seller_concessions"]), "Biggest controllable drain on net"))
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9:
        t["buyer_broker_pct"] = ob
        rows.append(("Buyer-Broker Compensation", f"{o['buyer_broker_pct']:.1%}", f"{ob:.1%}", "Matches what the seller agreed to offer"))
    if o["deposit"] is not None and o["deposit"] / o["price"] < L["deposit_norm"] - 1e-9:
        norm = L["deposit_norm"] if o["financed"] else max(L["deposit_norm"], 0.05)
        t["deposit"] = max(o["deposit"], rnd(norm * t["price"], 1000, "up"))
        rows.append(("Escrow Deposit", money(o["deposit"]), money(t["deposit"]), "More buyer commitment once contingencies expire"))
    if o["inspection_days"] > N["inspection_days"]:
        t["inspection_days"] = N["inspection_days"]
        rows.append(("Inspection Period", f"{o['inspection_days']} days" + (" (assumed)" if o.get("inspection_assumed") else ""),
                     f"{N['inspection_days']} days",
                     (f"Shorter walk-away window; seller shares the {L['reports']}" if o["inspection_walkaway"] else
                      f"Repair notices sooner; seller shares the {L['reports']}")))
    if o["sale_contingency_days"]:
        t["sale_contingency_days"] = min(21, o["sale_contingency_days"])
        rows.append(("Sale-of-Home Contingency", f"{o['sale_contingency_days']} days" + (" + kick-out" if o["kickout"] else ""),
                     f"{t['sale_contingency_days']} days + 72-hr kick-out", "Limits how long the seller is tied up"))
    if o["financed"] and o["approval"] in ("prequal", "none"):
        rows.append(("Loan Approval", APPROVAL_LABEL[o["approval"]], "Full pre-approval in 3 days", "Proves the buyer can actually borrow"))
    if o["home_warranty"]:
        t["home_warranty"] = 0
        rows.append(("Home Warranty", f"Seller pays {money(o['home_warranty'])}", "Buyer pays", "Small give-back if the buyer pushes"))
    new_close = o["close"]
    if S["deadline"] and new_close > S["deadline"]:
        new_close = S["deadline"]
    new_close = prior_weekday(new_close)
    if new_close != o["close"]:
        t["close"] = new_close
        rows.append(("Closing Date", f"{o['close']:%a %b %-d}", f"{new_close:%a %b %-d}",
                     "Meets the seller's deadline" if S["deadline"] and o["close"] > S["deadline"] else "Weekend closings may not fund"))
    if L["title_customary_payer"] == "seller" and o["title_by"] != "seller":
        rows.append(("Escrow / Title Agent", "Buyer's title co.", "Seller's title co.", "Seller pays the owner's policy, so the seller picks title"))
    ov = o.get("counter") or {}
    if ov.get("rows"):
        rows = [tuple(r) for r in ov["rows"]]
    for key in ("price", "seller_concessions", "appraisal_gap", "deposit", "inspection_days", "home_warranty", "buyer_broker_pct"):
        if key in ov:
            t[key] = ov[key]
    if "closing_date" in ov:
        t["close"] = _d(ov["closing_date"])
    return t, rows


# --- per-offer and listing-level analysis ------------------------------------

def _sheet(t, L, S, costs, repair=0, bb_tag=None):
    return net_sheet(t["price"], t["seller_concessions"], t["buyer_broker_pct"], t["home_warranty"], t["close"], L, S, costs, repair,
                     bb_tag=bb_tag)


def analyze_offer(o, L, S, costs):
    o["ns"] = net_sheet(o["price"], o["seller_concessions"], o["buyer_broker_pct"], o["home_warranty"], o["close"], L, S, costs,
                        bb_tag=o.get("bb_tag"))
    o["downside_price"] = downside_price(o, L)
    repair, repair_label = repair_reserve(o, L)
    o["repair_reserve"] = repair
    o["ns_down"] = net_sheet(o["downside_price"], o["seller_concessions"], o["buyer_broker_pct"], o["home_warranty"],
                             o["close"], L, S, costs, repair, repair_label, o.get("bb_tag"))
    o["score"] = score_offer(o, L, S)
    o["flags"] = flags_for(o, L, S)
    o["blocking"] = [f for f in o["flags"] if f["sev"] == "Blocking"]
    ct, rows = propose_counter(o, L, S)
    o["counter_terms"], o["counter_rows"] = ct, rows
    o["ns_counter"] = _sheet(ct, L, S, costs, bb_tag=o.get("bb_tag"))
    oc = dict(o)
    if not (o["appraisal_protected"] or o["appraisal_waived"]):
        oc["gap_cover"] = ct["appraisal_gap"]
    oc.update(price=ct["price"], appraisal_gap=ct["appraisal_gap"], deposit=ct["deposit"], inspection_days=ct["inspection_days"],
              sale_contingency_days=ct["sale_contingency_days"], close=ct["close"])
    oc["risk_days"] = risk_days(oc)
    oc["close_days"] = (oc["close"] - L["analysis_date"]).days
    if o["financed"] and o["approval"] in ("prequal", "none"):
        oc["approval"] = "preapproval"
    o["counter_score"] = score_offer(oc, L, S)["total"]
    return o


def target_net(L, S, costs, close):
    """A clean offer at list: no concessions, the agreed (or market) buyer-broker fee, same closing date."""
    bb = S["default_buyer_broker_pct"] or 0
    return net_sheet(L["list_price"], 0, bb, 0, close, L, S, costs)


def single_recommendation(o, tgt, priority="balanced"):
    if o.get("recommendation"):
        return o["recommendation"].upper()
    tol = 0.01 * o["price"]
    gain = o["ns_counter"]["net_adj"] - o["ns"]["net_adj"]
    small = {"certainty": 0.01, "price": 0.0025}.get(priority, 0.005)  # a seller who wants certainty won't risk it for less
    if o["score"]["total"] >= 80 and (o["ns"]["net_adj"] >= tgt["net_adj"] - tol or gain < small * o["price"]):
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
                finance.fraction(value, here, whole=key == "down_pct")
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
    if data.get("_cma_side_note"):
        A.add("listing", "cma side", "other side", data["_cma_side_note"], "high")
    if market is None and not state_of(data.get("listing") or {}):
        A.add("listing", "state", costs.state, "Property's state not given: Florida costs assumed", "high")
    L, S = prepare_listing(data, A, costs)
    offers = [prepare_offer(o, L, S, A) for o in data.get("offers") or []]
    if not offers:
        raise OfferError("There are no offers in the listing file.")
    apply_escalations(offers, L)
    label_offers(offers)
    for o in offers:
        analyze_offer(o, L, S, costs)
    if L["bill_paid"] is None and L["annual_tax"] and L["tax_in_arrears"] \
            and any(o["close"].month >= 11 for o in offers if o["status"] in ACTIVE):
        A.add("listing", "current_tax_bill_paid", False,
              "Closing in November or December: whether the seller has paid this year's tax bill wasn't given. Assumed not "
              "paid (the seller credits the buyer from Jan 1); if it's paid, the buyer credits the seller instead", "med")
    _missing_market(costs, offers[0]["ns"], A)
    live_offers = [o for o in offers if o["status"] in ACTIVE]
    active = [o for o in live_offers if not o["blocking"]]
    for o in live_offers:
        if o["blocking"]:  # no recommendation on a contract that can't be reviewed as written
            o["action"], o["action_reason"] = "INCOMPLETE", "Contract can't be reviewed as written"
    res = {"listing": L, "seller": S, "offers": offers, "active": active, "costs": costs,
           "incomplete": [o for o in live_offers if o["blocking"]],
           "market_notes": [n for n in costs.notes if "MLS" not in n],  # offers don't use MLS files
           "sample": bool(data.get("sample"))}
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
            o["action"] = single_recommendation(o, o["target"], S["priority"])
            o["action_reason"] = ""
    else:
        top = ranked[0]
        top["action"] = single_recommendation(top, top["target"], S["priority"])
        top["action_reason"] = "Best risk-adjusted net"
        for i, o in enumerate(ranked[1:], start=2):
            if i == 2 and o["score"]["total"] >= 60:
                o["action"], o["action_reason"] = "BACKUP", f"Strong enough to hold as backup to {top['ref']}"
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
                    why.append("nets less than the recommended offer after costs and risk")
                text = "; ".join(why)
                o["action_reason"] = text[:1].upper() + text[1:]
        for o in ranked:
            if o.get("recommendation"):
                o["action"] = o["recommendation"].upper()
    live = {f"offer {o['id']}" for o in active + res["incomplete"]}
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
