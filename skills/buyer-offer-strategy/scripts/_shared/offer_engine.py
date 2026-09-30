"""Offer engine shared by seller-offer-review (listing side) and buyer-offer-strategy (buyer side).

    from _shared import offer_engine as oe
    R = oe.analyze(listing_file)              # dict: listing, seller, offers, ranked, mode, assumptions, ...
    R = oe.analyze(listing_file, market=path_or_Market, cma=handoff_dict)

For every offer: seller net sheet (as offered, downside, counter), certainty score, risk flags,
proposed counter; with 2+ active offers, a ranking and a response plan.

Rule: the engine never stops on missing data. Every missing input gets a conservative default and is
recorded as an assumption with an impact level (high / med / low), so the report can say what to confirm
and mark itself Preliminary. Market costs (transfer tax, title, fees, commission, property tax, holding costs,
inspection credit reserve) come from the built-in layers via shared.finance: local defaults where there are any
(Florida), national estimates labeled Estimate otherwise, never another state's number. The listing file's
`costs` block (a title quote, the transfer tax the skill looked up) wins over both.
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
COST_KEYS = profiles.DEAL_COSTS


class Costs:
    """Market values with this deal's own numbers on top (a title company quote, a county's transfer tax).

    Behaves like profiles.Market for finance.seller_net (get / source / state).
    """

    def __init__(self, market, deal_costs=None):
        self.market = market
        self.over = {}
        self.box = {}  # an offer's contract terms over the market's values, keeping the market's source (offer_costs)
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
        if path in self.box:
            return self.box[path]
        return self.market.get(path, default)

    def source(self, path):
        return "deal" if path in self.over else self.market.source(path)

    def described(self, path):
        """Plain words for where a value came from: 'Florida default', 'national estimate', 'this listing'."""
        src = self.source(path)
        state = profiles.STATES.get(self.state or "", self.state or "market")
        return {"deal": "this listing", "estimate": "national estimate", "state": f"{state} default",
                "county": "county default", "mls": "MLS default",
                "national": f"none in {state}; confirm local taxes with the title company"}.get(src, "market default")


def load_costs(listing, market=None):
    """Costs for a listing: `market` is a profiles.Market, or None to load the listing's state and county."""
    if market is None:
        market = profiles.load_market(state=state_of(listing), county=listing.get("county"))
    return Costs(market, listing.get("costs"))


# --- CMA handoff -------------------------------------------------------------

def side_note(h, want):
    """OFR-24: a sentence when a handoff was made for the other side (a buyer CMA in a listing review), else None."""
    side = h.get("side")
    if side and side != want:
        return (f"The CMA handoff is from the {side} side ({h.get('source') or 'CMA'}), not the {want} side: its value range "
                "was built for the other party. Confirm it before relying on it, or use a CMA for this side")
    return None


_STREET_WORDS = {"street": "st", "avenue": "ave", "av": "ave", "drive": "dr", "road": "rd", "boulevard": "blvd",
                 "lane": "ln", "court": "ct", "circle": "cir", "place": "pl", "terrace": "ter", "parkway": "pkwy",
                 "highway": "hwy", "trail": "trl", "cove": "cv", "point": "pt", "square": "sq", "north": "n", "south": "s",
                 "east": "e", "west": "w", "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
                 "unit": "#", "apt": "#", "suite": "#", "ste": "#"}


def street_key(address):
    """'517 Hickorywood Avenue, Altamonte Springs, FL' -> '517 hickorywood ave': the street line, compared loosely."""
    line = str(address or "").split(",")[0].lower().replace("#", " # ")
    words = re.sub(r"[^a-z0-9# ]+", " ", line).split()
    return " ".join(_STREET_WORDS.get(w, w) for w in words)


def address_note(h, address):
    """CMA-102: a sentence when the handoff is for another property than the file's, else None."""
    theirs = (h.get("subject") or {}).get("address")
    if not theirs or not address or street_key(theirs) == street_key(address):
        return None
    return (f"The CMA handoff is for {theirs}, not {str(address).split(',')[0]}: its value range may be another home's. "
            "Confirm it's the same property, or run a CMA for this one")


def apply_cma(data, h):
    """Fill the listing from a cma-handoff v1 record (value range as the appraisal range; subject facts).

    Only fills what the listing file doesn't already say, so the agent's numbers win.
    """
    data = copy.deepcopy(data)
    L = data.setdefault("listing", {})
    data["_cma_address_note"] = address_note(h, L.get("address"))
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
                  f"Tax bill not provided: estimated at {tax['basis'].removeprefix('about ')} ({costs.described('property_tax.fallback_rate')}); "
                  "the proration moves the net by thousands, so get the bill", "med")  # OFR-128
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
    L["title_payer_deal"] = costs.source("closing_costs.owner_title.payer") == "deal"  # the agent's title_payer wins
    if L["title_customary_payer"] is None:
        A.add("listing", "title_payer", "unknown", "Who customarily pays the owner's title policy wasn't given: left out of the net "
              "(often about 0.5% of price)", "high")
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
              "30 days)", "med")
    L["deposit_norm"] = L["norms"]["deposit_pct"]

    S["payoff_known"] = S.get("payoff") is not None
    if not S["payoff_known"]:
        A.add("seller", "payoff", "not included", "Mortgage payoff not provided: report shows proceeds before payoff", "high")
        S["payoff"] = 0
    S["listing_fee_assumed"] = S.get("listing_fee_pct") is None
    if S["listing_fee_assumed"]:
        lf = costs.get("brokerage.listing_fee_pct")
        if lf is None:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", 0,
                                         "Listing brokerage fee not provided: left out of the net", "high")
        else:
            S["listing_fee_pct"] = A.add("seller", "listing_fee_pct", lf,
                                         f"Listing brokerage fee not provided: assumed {pct(lf)} ({costs.described('brokerage.listing_fee_pct')}; "
                                         "5% total with the buyer's agent)", "med")
    S["offered_buyer_broker_pct"] = S.get("offered_buyer_broker_pct")
    S["default_buyer_broker_pct"] = (S["offered_buyer_broker_pct"] if S["offered_buyer_broker_pct"] is not None
                                     else costs.get("brokerage.buyer_broker_fee_pct"))  # 2.5% national estimate
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
    L["repair_reserve_deal"] = costs.source("contract.inspection_credit_reserve_pct") == "deal"  # the agent's own figure
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
        notes.append(f"Owner's title policy customarily paid by the {payer} ({costs.described('closing_costs.owner_title.payer')}; "
                     "an offer's contract terms govern it, as noted per offer)")
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
    are the other offers' base prices, never the same buyer's alternatives (`same_buyer`). Everything after this (net,
    score, rank, counter) uses the effective price."""
    live = [o for o in offers if o["status"] in ACTIVE]
    base = {id(o): o["price"] for o in live}
    for o in live:
        e = o.get("escalation")
        if not e:
            continue
        inc, cap, issues = e.get("increment"), e.get("cap"), []
        if not cap:
            issues.append(("High", "Escalation clause with no cap.", "Ask for the cap in writing before relying on the clause.",
                           "escalation_cap"))
        if not inc:
            issues.append(("Med", "Escalation clause with no increment.", "Ask for the increment over a competing offer.",
                           "escalation_increment"))
        if e.get("proof") is None:
            issues.append(("Med", "The escalation clause doesn't say how a competing offer is proven.",
                           "Require a redacted copy of the competing offer's signature page and price terms.", "escalation_proof"))
        # OFR-101: offers with the same `same_buyer` key are one buyer's alternatives, never each other's competition
        others = [base[id(x)] for x in live if x is not o and not (o.get("same_buyer") and x.get("same_buyer") == o["same_buyer"])]
        o["price_base"] = p0 = o["price"]
        eff = p0
        if cap and inc and others and max(others) + inc > p0:
            eff = max(p0, min(cap, max(others) + inc))  # ENG-1: a cap below the price never lowers it
        if cap and cap <= p0:
            issues.append(("Med", f"The escalation cap ({money(cap)}) is at or below the offer's own price ({money(p0)}): "
                                  "the clause can't raise the price.",
                           "Ask the buyer's agent which figure was meant; until then the offer stands at its price.",
                           "escalation_cap_at_price"))
        o["price"], o["escalated"] = eff, eff > p0
        o["escalation_note"] = (f"Escalates to {money(eff)} from {money(p0)} (cap {money(cap)})" if eff > p0 else
                                f"Escalation cap {money(cap)} is at or below the price, so the clause does nothing" if cap and cap <= p0 else
                                f"Escalation to {money(cap)} not triggered by the other offers" if cap else "Escalation clause")
        if o.get("buyer_broker_amount"):
            o["buyer_broker_pct"] = o["buyer_broker_amount"] / eff
        if o["repairs_owed"]:
            o["repair_limits"] = cf.repair_limits(eff, o)
        if cap and o["appraisal_risk"] and cap > appraisal_line(L) + o["gap_cover"]:
            issues.append(("Med", f"The cap ({money(cap)}) is above what the value range and gap coverage support "
                                  f"({money(appraisal_line(L) + o['gap_cover'])}).",
                           "Ask for gap coverage that rises with the escalated price, or treat the appraisal as the ceiling.",
                           "escalation_cap_over_value"))
        o["escalation_issues"] = issues  # (sev, issue, fix, topic)


def label_offers(offers):
    """Set label ('Morales · Palmetto Coast Realty'), ref ('the Morales (Palmetto Coast Realty) offer') and key ('A') on each offer.

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

def lapsed(o, today):
    """'passed' when the time for acceptance (`expires`) is before the analysis date, 'likely' when it's only an
    estimate (`expires_estimated`: counted from the signature date because the delivery date isn't known), else None."""
    try:
        when = _d(o.get("expires_raw", o.get("expires")))
    except ValueError:
        return None  # free text ("see contract"): nothing to compare
    if not when or when >= today:
        return None
    return "likely" if o.get("expires_estimated") else "passed"


def expires_today(o, today):
    """ENG-18: True when the time for acceptance falls on the analysis date. The analysis date has no time of day, so
    an offer that lapses this evening can't be caught as passed: it's flagged instead."""
    try:
        return _d(o.get("expires_raw", o.get("expires"))) == today
    except ValueError:
        return False


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
    o["lapsed"] = lapsed(o, L["analysis_date"])
    o["expires_today"] = expires_today(o, L["analysis_date"])
    o["buyer"] = (o.get("buyer") or "").strip()
    if o.get("approval_expires") not in (None, ""):  # ENG-5: a letter's "30 days from issue" isn't a date to compare
        try:
            o["approval_expires"] = _d(o["approval_expires"])
        except ValueError:
            A.add(sc, "approval_expires", o["approval_expires"], f"Pre-approval expiry \"{o['approval_expires']}\" isn't a "
                  "date: not checked against the closing date. Read the date off the letter", "low")
            o["approval_expires"] = None
    dflt_down = {"cash": 1.0, "fha": 0.035, "va": 0.0, "usda": 0.0, "conventional": 0.10}[fin]
    loan = o.get("loan_amount")
    if fin != "cash" and o.get("down_pct") is None and loan and 0 < loan <= o["price"]:
        o["down_pct"] = round(1 - loan / o["price"], 4)  # the contract's loan amount gives the down payment
    o["down_pct"] = 1.0 if fin == "cash" else given(
        o, "down_pct", dflt_down, A, sc, f"Down payment not provided: assumed {dflt_down * 100:g}% for {FIN_LABEL[fin]}", "med")
    o["approval"] = given(o, "approval", "preapproval" if o["financed"] else "none", A, sc, "Approval level not provided", "med")
    o["deposit"] = o.get("deposit")
    if o["deposit"] is None:
        A.add(sc, "deposit", "unknown", "Escrow deposit not provided", "med")
    o["seller_concessions"] = given(o, "seller_concessions", 0, A, sc, "Seller concessions not provided: assumed $0", "high")
    # Rider GG signed broker to broker: the listing broker pays the buyer's broker from its own fee (listing agreement)
    o["bb_from_listing"] = str(o.get("buyer_broker_paid_by") or "").lower().replace("_", " ") in ("listing broker", "listing")
    if o["bb_from_listing"] and o.get("buyer_broker_pct") is None and o.get("buyer_broker_amount") is None:
        # Not a cost to the seller, so not an assumption: the default share only sizes an assumed listing fee.
        o["buyer_broker_pct"], o["bb_tag"] = S["default_buyer_broker_pct"] or 0, None
    elif o.get("buyer_broker_pct") is None and o.get("buyer_broker_amount") is None:
        bb = S["default_buyer_broker_pct"]
        o["bb_tag"] = "Assumed"
        if bb is None:
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", 0,
                                          "Buyer-broker compensation not stated: left out of the net", "high")
        else:
            offered = S["offered_buyer_broker_pct"] is not None
            src = "what the seller offered" if offered else "national estimate"
            o["buyer_broker_pct"] = A.add(sc, "buyer_broker_pct", bb, f"Buyer-broker compensation not stated: assumed {pct(bb)} ({src})",
                                          "high" if offered else "med")
    else:
        o["bb_tag"] = "Requested"
        if o.get("buyer_broker_pct") is None:
            o["buyer_broker_pct"] = o["buyer_broker_amount"] / o["price"]
    o["home_warranty"] = o.get("home_warranty") or 0
    # One form per offer, and only that form's rules (contract_forms): AS IS and Standard math never mix.
    raw_form = o.get("contract_form")
    try:
        form = cf.normalize(raw_form)
    except cf.FormError as e:
        raise OfferError(f"Offer {k}: {e}") from e
    if form is None:
        form = A.add(sc, "contract_form", cf.AS_IS,
                     "Contract form not given: assumed FR/BAR AS IS. The Standard form has no inspection walk-away and makes "
                     "the seller pay repairs up to its repair limits, so confirm which form was used", "high") \
            if L["frbar_market"] else cf.OTHER
    if form == cf.OTHER and raw_form and not o.get("contract_name"):  # OFR-113: keep the form's own name for the label
        o["contract_name"] = str(raw_form)
    o["contract_form"] = form
    try:  # the form and its riders together: Rider K or L on the Standard form changes the inspection terms
        t = cf.terms(form, o)
        if t["repairs_owed"]:
            o["repair_limits"] = cf.repair_limits(o["price"], o)
    except cf.FormError as e:
        raise OfferError(f"Offer {o.get('id', '?')}: {e}") from e
    o["contract_label"], o["contract_title"] = t["label"], t["title"]
    o["repairs_owed"], o["rider_codes"] = t["repairs_owed"], t["riders"]
    o["inspection_walkaway"] = t["walkaway"]
    if o["inspection_walkaway"] is None:  # another contract that doesn't say: the cautious reading for the seller
        o["inspection_walkaway"] = A.add(sc, "inspection_walkaway", True,
                                         "Whether this contract's inspection period lets the buyer cancel for any reason "
                                         "wasn't given: assumed it does. Confirm it in the contract", "high")
    o["inspection_assumed"] = o.get("inspection_days") in (None, "")
    blank = cf.inspection_days_default(form)  # ENG-7: the form's own blank (15 on FR/BAR), else the national 10 days
    o["inspection_days"] = given(o, "inspection_days", blank or NATIONAL_NORMS["inspection_days"], A, sc,
                                 f"Inspection period not provided: {blank} days, the form's default when blank" if blank else
                                 f"Inspection period not provided: assumed {NATIONAL_NORMS['inspection_days']} days", "med")
    o["loan_approval_days"] = 0 if not o["financed"] else given(
        o, "loan_approval_days", 30, A, sc, "Loan approval period not provided: assumed 30 days", "low")
    ac = o.get("appraisal_contingency")
    fin = o["financing"]
    o["aga_named"] = cf.aga_named(o) and form in cf.FRBAR  # read before appraisal_form below replaces the file's value
    o["appraisal_form"] = aform = cf.appraisal_form(form, o, fin)  # FR/BAR: AGA-1 (where it fits the loan), F, E or none
    o["appraisal_in_loan"] = o["financed"] and cf.appraisal_in_loan_approval(form, o, fin)
    aga = aform == "aga"  # AGA-1 on FHA, VA or USDA is flagged, not modeled (ENG-10)
    o["_appraisal_basis"] = None  # how the window is counted, so a counter that moves closing recounts it (ENG-14)
    if aga:
        ac, o["_appraisal_basis"] = True, "aga"  # the window comes from AGA-1's own periods once the closing is known
    elif ac is None and aform == "F":  # ENG-3: Rider F applies with or without financing
        A.add(sc, "appraisal_contingency", "rider default", "Appraisal date not given: used the Appraisal Contingency Rider's "
              "default (appraisal 10 days before closing, then 3 days for the buyer's notice)", "low")
        ac, o["_appraisal_basis"] = True, "F"
    elif ac is None and o["appraisal_in_loan"]:
        ac = o["loan_approval_days"] or True  # FR/BAR Para. 8(b)(2): the lender's appraisal is part of Loan Approval
    elif ac is None and o["financed"]:
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
    o["appraised"] = o["financed"] or aga or aform == "F"  # a cash offer carries appraisal risk only under AGA-1 or Rider F
    if not ac or not o["appraised"]:
        o["appraisal_days"] = 0
    else:
        o["appraisal_days"] = ac if isinstance(ac, int) and ac is not True else 21
    o["appraisal_gap"] = o.get("appraisal_gap") or 0
    o["gap_intent_only"] = o["aga_named"] and not cf.aga_fits(fin) and not o["appraisal_protected"]  # USDA on AGA-1
    if o["appraisal_protected"] or o["gap_intent_only"]:
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
    o["kickout"] = bool(o.get("kickout")) or "X" in o["rider_codes"]
    eff = L["analysis_date"]
    if o.get("closing_date"):
        o["close"] = _d(o["closing_date"])
    else:
        days = o.get("closing_days") or A.add(sc, "closing_days", 45 if o["financed"] else 30, "Closing date not provided", "med")
        o["close"] = eff + timedelta(days=days)
    o["close_days"] = (o["close"] - eff).days
    # FR/BAR Para. 9(c): the party who designates the Closing Agent pays the owner's policy, so the contract's box sets
    # who pays it on this offer; a title_payer the agent put in the listing's costs still wins
    by_contract = cf.owner_title_payer(form, o)
    if by_contract is None and form in cf.FRBAR and L["title_customary_payer"] in ("seller", "buyer") \
            and not L["title_payer_deal"]:  # ENG-9: the box decides who pays the owner's policy
        A.add(sc, "title_by", L["title_customary_payer"], f"Para. 9(c) box not given: the owner's title policy is "
              f"charged to the {L['title_customary_payer']} by local custom. Check which box is marked; the party who "
              "designates the Closing Agent pays it", "med")
    o["title_by"] = o.get("title_by") or L["title_customary_payer"]
    o["title_payer"] = L["title_customary_payer"] if L["title_payer_deal"] or not by_contract else by_contract
    o["title_payer_by_contract"] = bool(by_contract) and o["title_payer"] != L["title_customary_payer"]
    if o["appraisal_protected"]:
        o["_appraisal_basis"] = "E"  # protection runs to closing
    rider_money(o, A, sc)
    set_windows(o)
    o["firm_date"] = eff + timedelta(days=o["risk_days"])
    return o


def set_windows(o):
    """The windows that depend on the closing date (Rider F's blank date, AGA-1 capped at closing, FHA/VA to closing,
    Rider H and U), then risk_days. Run again when a counter moves closing (ENG-14)."""
    basis = o.get("_appraisal_basis")
    if basis in ("E", "F", "aga"):
        o["appraisal_days"] = cf.appraisal_window(basis, o["close_days"], o)
    if basis == "aga":  # OFR-106: AGA-1's own periods can run past closing; the window stops there, and it's flagged
        o["aga_window_full"] = cf.appraisal_window("aga", o["close_days"], o, cap=False)
    o["appraisal_risk"] = o["appraised"] and bool(o["appraisal_days"] or o["appraisal_waived"])
    o["rider_windows"], _ = cf.rider_windows(o["contract_form"], o, o["close_days"])
    o["risk_days"] = risk_days(o)
    o["risk_days_ex_appraisal"] = risk_days({**o, "appraisal_days": 0})  # AGA-1's window applies only on a low valuation
    o["walkaway_days"] = o["inspection_days"] if o["inspection_walkaway"] else 0  # OFR-121: cancel for any reason


def rider_money(o, A, sc):
    """Net-sheet lines and certainty days from CR-7 riders (shared/references/frbar-riders.md), from the offer's fields.

    U: the rent-back rent the seller pays the buyer. C: the seller-financed note is paid over time, not cash at closing.
    EE and the CDD addendum: an assessment balance the seller agrees to pay off. Z and Y: an attorney-approval date is a
    walk-away window (Z for the buyer counts toward risk_days). G: a short sale isn't firm until the lender approves."""
    codes, lines = o.get("rider_codes") or [], []
    if "U" in codes or o.get("rent_back_days"):
        days, rent = o.get("rent_back_days"), o.get("rent_back_monthly")
        if days and rent is not None:  # OFR-118: a free ($0) rent-back is a known term, not missing data
            lines.append(("rentback", f"Rent-Back Rent to Buyer ({days} Days, Est.)", -round(rent * days / 30)))
        else:
            A.add(sc, "rent_back", "not counted", "Post-closing occupancy (Rider U) without its days and monthly rent: the "
                  "rent the seller pays the buyer isn't in the net", "med")
    if o.get("seller_financing"):
        lines.append(("note", "Seller-Financed Note (Paid Over Time)", -o["seller_financing"]))
    if o.get("assessment_payoff"):
        lines.append(("assessment", "Assessment Payoff (Qualifying Improvement or CDD)", -o["assessment_payoff"]))
    o["rider_lines"] = lines
    o["short_sale"] = "G" in codes
    # Cancel windows the riders add (insurance, mold, drywall, occupancy and compensation agreements, attorney approval):
    # they count toward "days until firm" like the inspection period (contract_forms.rider_windows)
    _, missing = cf.rider_windows(o["contract_form"], o, o["close_days"])  # the windows themselves: set_windows()
    for code in missing:
        A.add(sc, f"rider_{code}", "not counted", f"{cf.rider_name(code)} attached without its date: its cancel window isn't "
              "counted, so the offer may be less firm than it scores. Get the date from the rider", "med")
    o["bb_credit"] = cf.buyer_broker_as_credit(o["contract_form"], o)


def _window_note(o, rd):
    """'; set by the insurance rider' when a rider's cancel window is what keeps the offer from being firm."""
    top = max(o.get("rider_windows") or (), key=lambda w: w[1], default=None)
    return f"; set by the {top[2]}" if top and top[1] == rd and top[1] > o["inspection_days"] else ""


def risk_days(o):
    """Days until the buyer can no longer get the deposit back under a contingency.

    When the Standard form's repairs are owed (no rider, or Rider L), either party may terminate when repairs exceed a
    limit, which runs at least to the repair election (notice + 10 + 5 days). Otherwise an inspection walk-away (AS IS,
    Standard + Rider K, another contract's walk-away period) counts in full. Another contract without a walk-away
    doesn't count the inspection period."""
    if o.get("repairs_owed") and o["inspection_days"]:
        insp = o["inspection_days"] + cf.STANDARD_REPAIR_WINDOW_DAYS
    elif o["inspection_walkaway"]:
        insp = o["inspection_days"]
    else:
        insp = 0
    return max(insp, o["loan_approval_days"], o["appraisal_days"], o["sale_contingency_days"],
               *(days for _, days, _ in o.get("rider_windows") or ()))


def repair_reserve(o, L):
    """The downside case's repair cost to the seller, by form.

    AS IS (and Standard + Rider K, which deletes the repair limits): the market's typical post-inspection credit.
    Standard (alone or with Rider L): the General Repair Limit the seller owes. Another contract: the market's figure
    only when the market's rules aren't FR/BAR, or when the agent gave this listing's own figure (OFR-113); a built-in
    Florida AS IS figure never applies to another form."""
    if not o["inspection_days"]:
        return 0, None
    if o["repairs_owed"]:  # the contract's cap, never rounded above it
        return o["repair_limits"]["general"], "Repairs up to the General Repair Limit (Standard)"
    if o["contract_form"] in cf.FRBAR or not L["frbar_market"] or L.get("repair_reserve_deal"):
        if L["repair_reserve_pct"]:
            return rnd(L["repair_reserve_pct"] * o["price"], 500), "Post-Inspection Repair Credit (Est.)"
    return 0, None


# --- money -------------------------------------------------------------------

_LINE_KEYS = {"listing_fee": "listing", "buyer_broker_fee": "bb", "transfer_tax": "transfer", "transfer_surtax": "surtax",
              "owner_title": "title", "title_fees": "settle", "estoppel": "estoppel"}


def net_sheet(price, conc, bb_pct, warranty, close, L, S, costs, repair=0, repair_label=None, bb_tag=None, extra=(),
              bb_from_listing=False):
    """Seller net at `price`, itemized with stable keys. Market costs and the tax proration come from finance.
    `extra` are the offer's rider money lines, (key, label, amount), placed before the payoff (rider_money).
    `bb_from_listing`: the listing broker pays the buyer's broker from its fee, so the seller pays only the listing fee
    (an assumed listing fee then covers both sides, the market's total)."""
    has_hoa = L["hoa_monthly"] is None or L["hoa_monthly"] > 0  # unknown HOA: charge the estoppel (conservative)
    listing_pct = S["listing_fee_pct"]
    if bb_from_listing:  # OFR-116: an assumed fee becomes the agreed (or market) total, never the listing fee + this ask
        listing_pct += (S.get("default_buyer_broker_pct") or 0) if S.get("listing_fee_assumed") else 0
        bb_pct = 0
    base = finance.seller_net(price, costs, listing_fee_pct=listing_pct, buyer_broker_fee_pct=bb_pct, has_hoa=has_hoa,
                              annual_tax=L["annual_tax"] if L["tax_in_arrears"] else None, closing=close,
                              bill_paid=L["bill_paid"], prop_type=L["property_type"])
    found = {}
    for ln in base["lines"]:
        key = _LINE_KEYS.get(ln["key"])
        if key:
            found[key] = (ln["label"], round(ln["amount"]))
    transfer = found.get("transfer", ("",))[0] or "Deed Transfer Tax"  # the market's own name (e.g. documentary stamp tax)
    labels = {
        "listing": (f"Listing Brokerage ({pct(listing_pct)}" + (", Pays the Buyer's Broker)" if bb_from_listing else ")"))
                   if listing_pct else "Listing Brokerage (Not Provided)",
        "bb": (f"Buyer-Broker Compensation ({pct(bb_pct, 2)}" + (f", {bb_tag})" if bb_tag else ")")) if bb_pct
              else "Buyer-Broker Compensation (Paid by the Listing Broker)" if bb_from_listing else "Buyer-Broker Compensation",
        "transfer": transfer,
        "title": "Owner's Title Policy" + (" (Quote)" if "(Quote)" in found.get("title", ("",))[0] else
                                           " (Promulgated Rate)" if costs.get("closing_costs.owner_title.rate_tiers") else " (Estimate)"),
        "settle": "Title Company Fees",
        # CMA-109: the market's own name (Florida "HOA Estoppel Letter", elsewhere "HOA Status Letter")
        "estoppel": costs.get("closing_costs.hoa_estoppel_label") or "HOA Status Letter",
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
              ("tax", tax_label, -tax), *extra,
              ("payoff", "Mortgage Payoff (Est.)", -S["payoff"])]
    net = sum(v for _, _, v in lines)
    months = max(0, (close - L["analysis_date"]).days) / 30
    holding = -round(S["holding_monthly"] * months)
    return {"lines": lines, "net": net, "holding": holding, "net_adj": net + holding, "close": close, "price": price,
            "missing": base["missing"], "assumed": base["assumed"]}


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
        elif o.get("gap_intent_only") and o["appraisal_gap"]:
            gap = f"{money(o['appraisal_gap'])} gap on AGA-1, which doesn't fit {FIN_LABEL[o['financing']]}: intent only"
        elif o["appraisal_waived"]:
            gap = f"waived, {money(o['gap_cover'])} documented to cover a low appraisal"
        else:
            gap = (f"{money(o['appraisal_gap'])} gap coverage" + (" (AGA-1)" if o.get("appraisal_form") == "aga" else "")
                   if o["appraisal_gap"] else "no gap coverage")
        why["appraisal"] = f"{money(over_hi)} over {ref}, {gap}" if over_hi > 0 else f"At/under {ref}, {gap}"

    rd = o["risk_days"]
    if o["sale_contingency_days"] and o["kickout"]:  # the seller keeps marketing; a back-up forces a waive-or-walk in 3 days
        s["contingency"] = 2
        why["contingency"] = f"Contingent on sale of buyer's home ({o['sale_contingency_days']} days), with a kick-out clause"
    elif o["sale_contingency_days"]:
        s["contingency"], why["contingency"] = 1, f"Contingent on sale of buyer's home ({o['sale_contingency_days']} days)"
    else:
        by_days = 5 if rd <= 7 else 4 if rd <= 14 else 3 if rd <= 30 else 2 if rd <= 45 else 1
        ins = o["inspection_days"]
        if o["inspection_walkaway"]:
            by_insp = 5 if ins <= 7 else 4 if ins <= 10 else 3 if ins <= 14 else 2  # walk-away-for-any-reason window weighs most
            s["contingency"] = min(by_days, by_insp)
            why["contingency"] = f"{rd} days until firm; {ins}-day inspection" + _window_note(o, rd)
        else:  # repair notices only (Standard): risk_days already runs through the repair election
            s["contingency"] = by_days
            why["contingency"] = f"{rd} days until firm; {ins}-day repair-notice period, no walk-away" + _window_note(o, rd)

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


def _has_rider(riders, *codes):
    """True when any of these CR-7 letters is attached (names are matched by contract_forms, never by substring)."""
    return any(c in cf.rider_codes(riders)[0] for c in codes)


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

    def add(sev, issue, fix, check, request=None, topic=None):
        """`request` is what to ask the buyer's agent for; None when the fix is on the listing side. `topic` lets an
        issue the agent wrote about the same thing replace this one (dedupe_flags)."""
        F.append({"sev": sev, "issue": issue, "fix": fix, "check": check, "contract": True, "request": request, "topic": topic})

    if o.get("lapsed") == "passed":  # FH-103: the facts (Para. 3's deadline has passed), no legal conclusion
        add("Blocking", f"The time for acceptance ({o['expires']}) has passed.",
            "Signing it now doesn't meet the deadline the offer set (Para. 3). A seller counter with a new time for "
            "acceptance, or the buyer re-signing with a new one, sets a live deadline.", "signed",
            "The time for acceptance has passed: does the buyer want to re-sign with a new time for acceptance, or "
            "should we expect the seller's counter?", "expired")
    elif o.get("lapsed") == "likely":
        add("High", f"The time for acceptance likely passed ({o['expires']}, counted from the signature date because the "
                    "delivery date isn't known).",
            "Confirm when it was delivered. If the window has closed, answer with a seller counter instead of signing it.",
            "signed", "Please confirm the date and time the offer was delivered to the listing side.", "expired")
    elif o.get("expires_today"):  # ENG-18: the analysis date has no time of day, so "today" is the warning
        add("High", f"The time for acceptance ends today ({o['expires']}).",
            "Respond before then: after that time the offer's own deadline has passed.", "signed", None, "expired")
    cap_price, cap_loan = o.get("approval_max_price"), o.get("approval_max_loan")
    loan = o.get("loan_amount") or (finance.loan_amount(o["price"], o["financing"], o["down_pct"]) if o["financed"] else 0)
    if o["financed"] and cap_price and o["price"] > cap_price:
        add("High", f"The pre-approval letter caps the price at {money(cap_price)}, below the {money(o['price'])} price.",
            "Get an updated pre-approval at the contract price, and proof of funds for any added cash, before accepting.",
            "terms", f"Please send an updated pre-approval at {money(o['price'])} and proof of funds for the balance to close.",
            "approval_cap")
    elif o["financed"] and cap_loan and loan > cap_loan + 1:
        add("High", f"The loan amount ({money(loan)}) is above the {money(cap_loan)} the pre-approval letter allows.",
            "Get an updated pre-approval for the loan amount before accepting.", "terms",
            f"Please send an updated pre-approval for a {money(loan)} loan.", "approval_cap")
    exp = o.get("approval_expires")  # a date, or None (prepare_offer records free text as an assumption)
    if o["financed"] and exp and o.get("close") and exp < o["close"]:
        e, c = exp, o["close"]
        add("Med", f"The pre-approval letter expires {e:%b} {e.day}, {e.year}, before the {c:%b} {c.day} closing.", "Ask for the lender to extend or update it; it's routine, but confirm before relying on the date.",
            "terms", "Please confirm the pre-approval will be extended or updated through closing.", "approval_expires")
    funds = o.get("proof_of_funds")
    if funds:  # verified cash: the down payment (price less the loan; deposits are part of it) plus an appraisal gap
        # ENG-6: the gap is cash on top only when a loan is capped by the appraisal (a cash buyer pays the price anyway)
        gap = (o.get("appraisal_gap") or 0) if o["financed"] and not o["appraisal_protected"] else 0
        need = o["price"] - (loan or 0) + gap
        if funds < need:
            add("High", f"Proof of funds ({money(funds)}) is below the {money(need)} this offer needs in cash (down payment and "
                        "deposits" + (f", plus the {money(gap)} appraisal gap" if gap else "") + "), before closing costs.",
                "Get proof of funds that covers it before accepting.", "terms",
                f"Please send proof of funds of at least {money(need)} plus closing costs.", "proof_of_funds")
    missed = chain_gaps(o)
    if missed:
        add("High", "The live offer doesn't carry these terms from the seller's last counter: " + "; ".join(
                f"{name} {was} (this offer: {now})" for name, was, now, _ in missed) + ". Signing it as is gives the buyer "
                "this offer's terms.",
            "Restate them in the seller's response (the counter below does).", "terms", None, "counter_chain")

    riders = o.get("riders") or []
    if riders:
        if o["financing"] in ("fha", "va") and not _has_rider(riders, "E"):
            add("High", f"{FIN_LABEL[o['financing']]} financing without an FHA/VA rider.", "Ask for the signed FHA/VA financing rider.", "riders",
                "Please send the signed FHA/VA financing rider.", "rider_E")
        if o["sale_contingency_days"] and not _has_rider(riders, "V"):
            add("High", "Sale-of-home contingency without its rider.", "Ask for the signed Sale of Buyer's Property rider.", "riders",
                "Please send the signed Sale of Buyer's Property rider.", "rider_V")
        stated = o.get("appraisal_contingency")
        in_loan = o["appraisal_in_loan"] and stated in (True, o["loan_approval_days"])  # Para. 8(b): no rider needed
        if o["financing"] == "conventional" and o["appraisal_days"] and stated not in (None, "") and not in_loan \
                and not _has_rider(riders, "F"):
            add("Med", "Appraisal period stated without an appraisal rider.", "Ask which appraisal terms apply, and for the rider.", "riders",
                "Which appraisal terms apply? Please send the appraisal rider.", "rider_F")
        if L["condo"] and not _has_rider(riders, "A"):
            add("High", "The property is a condo but no condo rider is attached.",
                "Ask for the signed condo rider, and deliver the association documents as soon as it's signed.", "riders",
                "Please attach the signed condominium rider.", "rider_A")
        elif L.get("hoa_monthly") and not _has_rider(riders, "A", "B"):
            add("High", "The property has an HOA but no HOA or condo rider is attached.",
                "Add the HOA or condo rider, and give the buyer the required HOA disclosure, before accepting.", "riders",
                topic="rider_B")
        codes = o.get("rider_codes") or []
        if "G" in codes:
            add("High", "Short sale (Rider G): the contract isn't firm until the seller's lender approves it (90 days after the "
                        "Effective Date if blank), and most deadlines restart when the buyer receives the approval.",
                "Set the seller's expectations on timing; the lender sets the final net.", "terms")
        for code, who in (("Z", "buyer"), ("Y", "seller")):
            if code in codes:
                add("Med", f"{who.title()}'s attorney approval (Rider {code}): the {who} may cancel for any reason until the "
                           "rider's date.", "Keep the date short and confirm it's filled in.", "terms",
                    "Please confirm the attorney approval date in the rider." if code == "Z" else None)
        if "V" in codes and "X" not in codes:
            add("Med", "Sale-of-home contingency (Rider V) without a kick-out clause (Rider X): the seller can't keep marketing.",
                "Counter with the Kick-Out Clause Rider.", "riders", "Would the buyer accept the Kick-Out Clause Rider (X)?")
        if "D" in codes:
            add("Med", "Mortgage assumption (Rider D): the rider sets no deadline for the lender's approval.",
                "Add an approval deadline in Additional Terms.", "terms")
        if "EE" in codes and not o.get("assessment_payoff"):
            add("Med", "Qualifying improvement assessment (Rider EE): the rider doesn't say who pays the unpaid balance.",
                "Agree in Additional Terms whether the seller pays it off at closing or the buyer assumes it; check the "
                "buyer's lender allows it.", "terms")
        if "GG" in codes:
            add("Med", "Rider GG: the buyer's broker compensation amount is in a separate compensation agreement, not the rider.",
                "Get the signed agreement (due 3 days after the Effective Date if blank); the listing broker pays it from its "
                "fee, so it isn't in the seller's net." if o.get("bb_from_listing") else
                "Get the signed agreement (due 3 days after the Effective Date if blank) and put its amount in the net.", "terms",
                "Please send the compensation agreement for the seller's review.", "rider_GG")
        yb = L.get("year_built")
        if yb and yb < 1978 and not _has_rider(riders, "P"):
            add("High", f"Built {yb}: no lead-based paint disclosure attached (federally required before 1978).",
                "Complete the lead-based paint disclosure with the seller and have the buyer sign it before accepting.", "riders",
                topic="lead_paint")
    if o.get("aga_named"):  # AGA-1's name and the loans it fits are contract_forms' rules (ENG-15)
        if "F" in (o.get("rider_codes") or []):
            add("Med", "Appraisal Gap Addendum (AGA-1) with the Appraisal Contingency Rider (F): AGA-1 says not to use them together.",
                "Ask which governs a low appraisal; counter with one of them.", "riders",
                "Which appraisal terms govern: the Appraisal Gap Addendum or the Appraisal Contingency Rider?", "aga_with_rider_F")
        if not cf.aga_fits(o["financing"]):  # ENG-10: FHA, VA and USDA
            add("Med", f"Appraisal Gap Addendum (AGA-1) on a {FIN_LABEL[o['financing']]} offer: AGA-1 is for conventional or "
                       "cash offers" + (", and the FHA/VA rider's protection runs to closing anyway." if o["appraisal_protected"]
                                        else ", so the gap it states isn't counted."),
                "Treat the gap as stated intent only." if o["appraisal_protected"] else
                "Ask for the gap terms in Additional Terms or a form that fits the loan; until then it isn't counted.",
                "terms", None if o["appraisal_protected"] else "Please restate the appraisal gap terms on a form that fits "
                "the loan type (AGA-1 is for conventional or cash offers).", "aga_loan_type")
        if not o["appraisal_gap"]:
            add("Med", "Appraisal Gap Addendum (AGA-1) without a Gap Amount.", "Ask for the Gap Amount.", "terms",
                "Please fill in the Gap Amount on the Appraisal Gap Addendum.")
        full = o.get("aga_window_full")
        if full and full > o["close_days"]:  # OFR-106
            add("Med", f"AGA-1's valuation and renegotiation periods ({full} days) run past the {o['close_days']}-day closing.",
                "Fill the valuation days so the periods end before closing (and before loan approval on a financed offer).",
                "terms", "Can the Appraisal Gap Addendum's valuation period be shortened so it ends before closing?",
                "aga_window_past_closing")
    if L["condo"] and o["financing"] in ("fha", "va"):
        fin = FIN_LABEL[o["financing"]]
        add("High", f"{fin} loan on a condo: the project must be {fin}-approved.",
            "Confirm the project's approval before accepting; an unapproved project can't close with this loan.", "terms",
            f"Please confirm the lender has verified the condo project's {fin} approval.", "condo_project_approval")
    loan = o.get("loan_amount")
    if loan and o["financed"] and abs(loan - o["price"] * (1 - o["down_pct"])) > max(1000, .01 * o["price"]):
        add("Med", f"Loan amount {money(loan)} doesn't match {pct(o['down_pct'])} down on {money(o['price'])}.",
            "Ask the buyer's agent to correct the financing figures.", "terms",
            "Please correct the loan amount or down payment in the financing section.", "loan_amount")
    if o["financed"] and o["loan_approval_days"] and o["loan_approval_days"] > o["close_days"]:
        add("Med", f"Loan approval period ({o['loan_approval_days']} days) ends after closing ({o['close_days']} days).",
            "Ask for a loan approval date before closing.", "terms", "Can the loan approval date move before closing?")
    for c in o.get("contract_issues") or []:
        sev = c.get("sev", "High")
        sev = sev if sev in CONTRACT_SEV else "High"
        add(sev, c["issue"], c.get("fix", ""), c.get("check", "signed" if sev == "Blocking" else "terms"),
            c.get("request") or (as_request(c.get("fix", "")) if sev in ("Blocking", "High") else None))
        F[-1]["agent_topics"] = issue_topics(c)
    return F


# What the engine raises on its own, by topic (contract-check.md lists them). An issue the agent wrote in
# `contract_issues` about the same topic (its `topic`, or these words in its text) replaces the engine's flag, at the
# more severe of the two levels, so the report never shows the same problem twice.
TOPIC_WORDS = {
    "expired": r"time for acceptance|acceptance (deadline|date|time|period)|\b(expired|lapsed?)\b",
    "approval_cap": r"pre-?approval",
    # Only phrases that say an earlier counter's term was dropped ("doesn't restate Counter 1's 10 days"), never a
    # suggestion to restate something in the next counter.
    "counter_chain": r"(doesn't|does not|didn't|did not|without) restat|(doesn't|does not|didn't|did not|won't|don't) carr(y|ies) (over|forward)|earlier counter|prior counter",
    "rider_GG": r"\bGG\b|compensation agreement",
    "inspection_period": r"inspection period",
    "lead_paint": r"lead[- ](based )?paint",
    "loan_amount": r"loan amount",
    "flood_disclosure": r"flood disclosure|FD-2|689\.302",
}


def issue_topics(c):
    """The topics an agent-written contract issue covers: its `topic` (a name or a list), else the words in its text."""
    t = c.get("topic")
    if t:
        return set([t] if isinstance(t, str) else t)
    text = f"{c.get('issue', '')} {c.get('fix', '')}"
    return {k for k, rx in TOPIC_WORDS.items() if re.search(rx, text, re.I)}


def dedupe_flags(F):
    """Drop an engine flag when the agent's own contract issue covers its topic; the agent's issue keeps the higher
    severity of the two."""
    order = {"Blocking": -1, "High": 0, "Med": 1, "Low": 2}
    mine = [f for f in F if f.get("agent_topics")]
    out = []
    for f in F:
        cover = [m for m in mine if f.get("topic") and f["topic"] in m["agent_topics"] and not f.get("agent_topics")]
        if not cover:
            out.append(f)
            continue
        for m in cover:
            m["topic"] = m.get("topic") or f["topic"]  # the agent's issue carries the engine's topic it replaces (TEST-2)
            if order.get(f["sev"], 1) < order.get(m["sev"], 1):
                m["sev"] = f["sev"]
                if f["sev"] in ("Blocking", "High") and not m.get("request") and f.get("request"):
                    m["request"] = f["request"]
    return out


CHAIN_TERMS = (  # (key, name, stronger for the seller: 'lower', 'higher', or 'same' for a date the seller set)
    ("inspection_days", "inspection period", "lower"), ("loan_approval_days", "loan approval period", "lower"),
    ("deposit", "deposit", "higher"), ("seller_concessions", "seller concessions", "lower"),
    ("appraisal_gap", "appraisal gap coverage", "higher"), ("closing_date", "closing date", "same"))  # OFR-108


def last_seller_counter(o):
    """The seller's most recent counter in `prior_counters` (listed in order), or None."""
    return next((c for c in reversed(o.get("prior_counters") or []) if (c.get("by") or "seller") == "seller"), None)


def _term_text(key, v):
    if key == "closing_date":
        d = _d(v)
        return f"{d:%b} {d.day}, {d.year}"
    return f"{v} days" if key.endswith("_days") else money(v)


def chain_gaps(o):
    """Terms the seller's last counter asked for that the live offer is weaker on: (name, seller's, offer's, key).
    Under a counter form that carries only what it restates (FR/BAR CO-3), a buyer's counter that doesn't restate them
    leaves the original offer's terms, which the live offer's fields record."""
    last = last_seller_counter(o)
    if not last:
        return []
    out = []
    for key, name, better in CHAIN_TERMS:
        want, now = last.get(key), (o.get("close") if key == "closing_date" else o.get(key))
        if want is None or now is None:
            continue
        if better == "same":
            want = _d(want)
        if (now != want) if better == "same" else (now > want) if better == "lower" else (now < want):
            out.append((name, _term_text(key, want), _term_text(key, now), key))
    return out


def flags_for(o, L, S):
    F = []

    def add(sev, issue, fix, topic=None):
        F.append({"sev": sev, "issue": issue, "fix": fix, "topic": topic})

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
            "Ask for proof of funds for the gap; don't count it in the net.", "fha_gap_intent")
    cap = finance.concession_cap(o["financing"], o["down_pct"])  # OFR-12
    credit = round(o["buyer_broker_pct"] * o["price"]) if o.get("bb_credit") else 0  # Rider FF: a seller credit to the buyer
    if cap is not None and o["seller_concessions"] + credit > cap * o["price"] + 1:
        over = o["seller_concessions"] + credit - cap * o["price"]
        what = (f"Concessions ({money(o['seller_concessions'])}) plus the Rider FF broker credit ({money(credit)})" if credit
                else f"Concessions ({money(o['seller_concessions'])})")
        add("High", f"{what} exceed the {FIN_LABEL[o['financing']]} limit of "
                    f"{pct(cap)} at {pct(o['down_pct'])} down ({money(cap * o['price'])}): {money(over)} can't be used.",
            "Counter the concessions down to the limit, or the price down by the excess." if not credit else
            "Pay the buyer's broker under Rider GG (a separate compensation agreement) instead of a credit, or counter the "
            "concessions down; confirm with the buyer's lender how it counts the credit.", "concessions_cap")
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
            "Have the seller complete it (" + rule.get("asks", "flood history") + ") and give it to the buyer at or before signing.",
            "flood_disclosure")
    if L["condo"]:
        cr = L["condo_rules"]
        if cr.get("rescission"):
            add("Med", "Condo: " + cr["rescission"].rstrip(".") + ".",
                "Deliver the association documents" + (", the milestone summary and the SIRS" if cr.get("sirs_milestone") else "")
                + " right after acceptance: the deal isn't firm until the buyer's windows pass.", "condo_rescission")
    if S["deadline"] and o["close"] > S["deadline"]:
        add("High", f"Closing {o['close']:%b %-d} is after the seller's {S['deadline']:%b %-d} deadline.", "Counter the closing date.")
    if o["close"].weekday() >= 5:
        add("Low", f"{o['close']:%b %-d} is a {o['close']:%A}.", "Move closing to the prior Friday.")
    if o["inspection_days"] >= 15 and "inspection_days" not in [g[3] for g in chain_gaps(o)]:  # else the chain issue says it
        add("Med", f"{o['inspection_days']}-day inspection period.", "Counter to 7–10 days.", "inspection_period")
    if o["repairs_owed"]:
        lim = o["repair_limits"]
        add("Med", f"{o['contract_title']}: the seller pays repairs up to {money(lim['general'])} general, {money(lim['wdo'])} WDO "
                   f"and {money(lim['permit'])} permits (Para. 9(a)).", "Price that in, or counter on the AS IS form.")
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9 and not o.get("bb_from_listing"):
        add("Med", f"Buyer-broker request ({o['buyer_broker_pct']:.1%}) exceeds the {ob:.1%} the seller agreed to offer.",
            "Counter to the agreed amount.")
    if any(t in o["buyer"].upper() for t in (" LLC", " INC", " TRUST", " CORP")):
        add("Low", "Entity buyer.", "Confirm signer authority and that funds are in the entity's name.")
    if o.get("escalation"):
        for sev, issue, fix, topic in o.get("escalation_issues") or []:
            add(sev, issue, fix, topic)
        add("Low", o["escalation_note"] + ".", "Confirm the competing offer's price terms before signing.")
    if L.get("hoa_approval_required"):
        add("Low", "HOA approval required.", "Confirm the association's approval timeline fits the closing date.")
    if o["financed"] and o.get("insurance_quote") is False:
        add("Low", "Buyer has no insurance quote yet.", "Ask for a quote before countering.")
    for f in o.get("flags") or []:
        F.append({"sev": f.get("sev", "Med"), "issue": f["issue"], "fix": f.get("fix", "")})
    F = dedupe_flags(F + contract_checks(o, L))
    order = {"Blocking": -1, "High": 0, "Med": 1, "Low": 2}
    return sorted(F, key=lambda f: order.get(f["sev"], 1))


# --- counters ----------------------------------------------------------------

RESTATE = "Restates the seller's last counter"

def propose_counter(o, L, S):
    """(terms, rows of (term, offered, counter, why)). Agent overrides in o['counter'] win."""
    t = {"price": o["price"], "seller_concessions": o["seller_concessions"], "appraisal_gap": o["appraisal_gap"],
         "deposit": o["deposit"], "inspection_days": o["inspection_days"], "home_warranty": o["home_warranty"],
         "close": o["close"], "buyer_broker_pct": o["buyer_broker_pct"], "sale_contingency_days": o["sale_contingency_days"],
         "loan_approval_days": o["loan_approval_days"]}
    rows = []
    lp, hi, mid = L["list_price"], L["cma_high"], L["cma_mid"]
    last = last_seller_counter(o) or {}  # negotiation history: never above the seller's last price, never weaker terms
    # ENG-2: with history, the seller's own last counter is the ceiling (even above list); list only without history
    ceiling = last["price"] if last.get("price") else lp
    uncovered = o["appraisal_risk"] and o["price"] > hi and o["gap_cover"] < o["price"] - hi
    # OFR-110: without a CMA the price is never countered down (list only stands in for the value)
    if uncovered and L["cma_provided"] and (not last.get("price") or o["price"] > ceiling):
        # ENG-2: with history the seller has named a price, so an offer above it is countered back to it, never below it
        t["price"] = last["price"] if last.get("price") else rnd(hi, 1000, "down")
        rows.append(("Price", money(o["price"]), money(t["price"]),
                     "Top of the value range, so the appraisal can support it" if not last.get("price") else
                     RESTATE + ("; the gap coverage below covers the part above the value range" if t["price"] > hi else "")))
    elif o["price"] < ceiling:
        low_ball = L["cma_provided"] and o["price"] < L["cma_low"] and not last.get("price")
        t["price"] = ceiling if low_ball else min(rnd((o["price"] + ceiling) / 2, 1000, "up"), ceiling)
        why = ("Under the value range: counter at list" if low_ball else
               f"Meets partway between this offer and the seller's last counter ({money(ceiling)})" if last.get("price") else
               "Below list: meet partway")
        rows.append(("Price", money(o["price"]), money(t["price"]), why))
    if o["appraisal_risk"] and not o["appraisal_protected"]:  # an FHA/VA gap clause wouldn't bind the buyer
        need = t["price"] - hi
        if need > o["gap_cover"] and need > 0:
            t["appraisal_gap"] = rnd(need, 1000, "up")
            rows.append(("Appraisal Gap Coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None", money(t["appraisal_gap"]),
                         f"Deal holds if the appraisal lands at {money(rnd(hi, 1000))}" if L["cma_provided"] else
                         # OFR-110: without a CMA the price stands; list is only a stand-in for the value
                         "Covers the price above list; no CMA yet, so list stands in for the value (a CMA would firm it up)"))
    if last.get("appraisal_gap") and o["appraisal_gap"] < last["appraisal_gap"] and t["appraisal_gap"] < last["appraisal_gap"] \
            and not o["appraisal_protected"]:
        t["appraisal_gap"] = last["appraisal_gap"]
        rows = [r for r in rows if r[0] != "Appraisal Gap Coverage"]
        rows.append(("Appraisal Gap Coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None", money(t["appraisal_gap"]),
                     RESTATE))
    N = L["norms"]
    if last.get("seller_concessions") is not None:  # the seller already answered the concessions ask (ENG-4: null = not)
        if o["seller_concessions"] > last["seller_concessions"]:
            t["seller_concessions"] = last["seller_concessions"]
            rows.append(("Seller Concessions", money(o["seller_concessions"]), money(t["seller_concessions"]), RESTATE))
    elif o["seller_concessions"] > N["concessions_pct"] * o["price"] + 1:
        t["seller_concessions"] = rnd(o["seller_concessions"] / 2, 500)
        rows.append(("Seller Concessions", money(o["seller_concessions"]), money(t["seller_concessions"]), "Biggest controllable drain on net"))
    ob = S["offered_buyer_broker_pct"]
    if ob is not None and o["buyer_broker_pct"] > ob + 1e-9 and not o.get("bb_from_listing"):
        t["buyer_broker_pct"] = ob
        rows.append(("Buyer-Broker Compensation", f"{o['buyer_broker_pct']:.1%}", f"{ob:.1%}", "Matches what the seller agreed to offer"))
    if o["deposit"] is not None and last.get("deposit"):
        if o["deposit"] < last["deposit"]:
            t["deposit"] = last["deposit"]
            rows.append(("Escrow Deposit", money(o["deposit"]), money(t["deposit"]), RESTATE))
    elif o["deposit"] is not None and o["deposit"] / o["price"] < L["deposit_norm"] - 1e-9:
        norm = L["deposit_norm"] if o["financed"] else max(L["deposit_norm"], 0.05)
        t["deposit"] = max(o["deposit"], rnd(norm * t["price"], 1000, "up"))
        rows.append(("Escrow Deposit", money(o["deposit"]), money(t["deposit"]), "More buyer commitment once contingencies expire"))
    if last.get("inspection_days"):  # restate the seller's own ask rather than going back on it
        if o["inspection_days"] > last["inspection_days"]:
            t["inspection_days"] = last["inspection_days"]
            rows.append(("Inspection Period", f"{o['inspection_days']} days", f"{last['inspection_days']} days", RESTATE))
    elif o["inspection_days"] > N["inspection_days"]:
        t["inspection_days"] = N["inspection_days"]
        rows.append(("Inspection Period", f"{o['inspection_days']} days" + (" (assumed)" if o.get("inspection_assumed") else ""),
                     f"{N['inspection_days']} days",
                     (f"Shorter walk-away window; seller shares the {L['reports']}" if o["inspection_walkaway"] else
                      f"Repair notices sooner; seller shares the {L['reports']}")))
    if o["financed"] and last.get("loan_approval_days") and o["loan_approval_days"] > last["loan_approval_days"]:
        t["loan_approval_days"] = last["loan_approval_days"]  # OFR-108: the counter's net and score use it too
        rows.append(("Loan Approval Period", f"{o['loan_approval_days']} days", f"{last['loan_approval_days']} days", RESTATE))
    if o["sale_contingency_days"]:
        t["sale_contingency_days"] = min(21, o["sale_contingency_days"])
        rows.append(("Sale-of-Home Contingency", f"{o['sale_contingency_days']} days" + (" + kick-out" if o["kickout"] else ""),
                     f"{t['sale_contingency_days']} days + 72-hr kick-out", "Limits how long the seller is tied up"))
    if o["financed"] and o["approval"] in ("prequal", "none"):
        rows.append(("Loan Approval", APPROVAL_LABEL[o["approval"]], "Full pre-approval in 3 days", "Proves the buyer can actually borrow"))
    elif o["financed"] and o.get("approval_max_price") and t["price"] > o["approval_max_price"]:
        rows.append(("Pre-Approval", f"Letter to {money(o['approval_max_price'])}", f"Updated letter at {money(t['price'])} in 3 days",
                     "The buyer's current letter is below the countered price" if o["price"] <= o["approval_max_price"]
                     else "The buyer's current letter is below the price"))
    if o["home_warranty"]:
        t["home_warranty"] = 0
        rows.append(("Home Warranty", f"Seller pays {money(o['home_warranty'])}", "Buyer pays", "Small give-back if the buyer pushes"))
    new_close = _d(last["closing_date"]) if last.get("closing_date") else o["close"]  # OFR-108: the seller's own date
    if S["deadline"] and new_close > S["deadline"]:
        new_close = S["deadline"]
    new_close = prior_weekday(new_close)
    if new_close != o["close"]:
        t["close"] = new_close
        rows.append(("Closing Date", f"{o['close']:%a %b %-d}", f"{new_close:%a %b %-d}",
                     "Meets the seller's deadline" if S["deadline"] and o["close"] > S["deadline"] else
                     RESTATE if last.get("closing_date") and new_close == _d(last["closing_date"]) else "Weekend closings may not fund"))
    # rule 12 only where choosing title and paying for it are separate: under FR/BAR Para. 9(c) the buyer who
    # designates the Closing Agent also pays the owner's policy, so there's nothing to counter
    if L["title_customary_payer"] == "seller" and o["title_by"] != "seller" and o.get("title_payer") == "seller":
        rows.append(("Escrow / Title Agent", "Buyer's title co.", "Seller's title co.", "Seller pays the owner's policy, so the seller picks title"))
    if rows or o.get("lapsed"):  # OFR-122: every counter sets its own time for acceptance (a lapsed offer's reviving term)
        rows.append(acceptance_row(o, L))
    ov = o.get("counter") or {}
    if ov.get("rows"):
        rows = [tuple(r) for r in ov["rows"]]
    for key in ("price", "seller_concessions", "appraisal_gap", "deposit", "inspection_days", "home_warranty", "buyer_broker_pct",
                "loan_approval_days"):
        if key in ov:
            t[key] = ov[key]
    if "closing_date" in ov:
        t["close"] = _d(ov["closing_date"])
    return t, rows


ACCEPTANCE_DAYS = 2  # a counter's time for acceptance: two days after the review, on a weekday, 5:00 PM


def acceptance_row(o, L):
    """The Time for Acceptance row every counter carries (OFR-122): the buyer's deadline to sign the counter."""
    due = L["analysis_date"] + timedelta(days=ACCEPTANCE_DAYS)
    while due.weekday() >= 5:
        due += timedelta(days=1)
    was = o.get("expires") or "Not stated"
    why = ("The offer's own deadline has passed: this sets a new one" if o.get("lapsed") else
           "A firm deadline for the buyer to answer the counter")
    return ("Time for Acceptance", f"Passed ({was})" if o.get("lapsed") == "passed" else was,
            f"{due:%a %b %-d}, 5:00 PM", why)


# --- per-offer and listing-level analysis ------------------------------------

def offer_costs(o, costs):
    """The market's costs with this offer's Para. 9(c) box (FR/BAR) where the contract differs from local custom: who
    pays the owner's policy, and which title searches the seller pays (OFR-102). A title quote in the listing's costs
    always wins over both."""
    over = {}
    if o.get("title_payer") not in (None, costs.get("closing_costs.owner_title.payer")):
        over["closing_costs.owner_title.payer"] = o["title_payer"]
    fees = box_title_fees(o, costs)
    if not over and fees is None:
        return costs
    c = copy.copy(costs)
    c.over = {**costs.over, **over}
    # the box picks which of the market's fees apply; they stay the market's (labeled estimates, not a quote)
    c.box = {**costs.box, **({"closing_costs.seller_title_fees": fees} if fees is not None else {})}
    return c


def box_title_fees(o, costs):
    """The seller's title company fees under the offer's Para. 9(c) box, or None to keep the market's (no box, a title
    quote, or a box that matches the county's custom). The amounts are the state's itemized defaults; the box decides
    which searches are the seller's: (i) title and lien searches, (ii) neither, (iii) the title search up to its cap."""
    path = "closing_costs.seller_title_fees"
    items = cf.seller_title_searches(o["contract_form"], o)
    if items is None or costs.source(path) == "deal":
        return None
    box = cf.title_box(o["contract_form"], o)
    custom = costs.get("closing_costs.owner_title.payer")
    if box != "iii" and cf.owner_title_payer(o["contract_form"], o) == custom:
        return None  # the county's own fees already follow its custom (Broward's "buyer" is its regional provision)
    # the state's itemized list, before any county custom removed or capped a search (Collier, Miami-Dade)
    base = profiles.load_market(state=costs.state).get(path) if costs.state else costs.get(path)
    if not isinstance(base, dict):
        return None
    fees = dict(base)
    search = items["title_search"]  # True (all of it), False (none) or a cap in dollars
    if "title_search" in fees and search is not True:
        fees["title_search"] = min(fees["title_search"], search or 0)
    if "municipal_lien_search" in fees and not items["municipal_lien_search"]:
        fees["municipal_lien_search"] = 0
    return {k: v for k, v in fees.items() if v}


def _sheet(t, o, L, S, costs, repair=0):
    """An offer's net sheet at terms `t` (the offer's own, or the counter's). Every column of one offer shares the
    repair line's label, so the net sheet reads the same across As Offered, Downside and Counter."""
    return net_sheet(t["price"], t["seller_concessions"], t["buyer_broker_pct"], t["home_warranty"], t["close"], L, S,
                     offer_costs(o, costs), repair, o.get("repair_label"), o.get("bb_tag"), o.get("rider_lines") or (),
                     o.get("bb_from_listing", False))


def analyze_offer(o, L, S, costs):
    repair, o["repair_label"] = repair_reserve(o, L)
    o["repair_reserve"] = repair
    o["ns"] = _sheet(o, o, L, S, costs)
    o["downside_price"] = downside_price(o, L)
    o["ns_down"] = _sheet({**o, "price": o["downside_price"]}, o, L, S, costs, repair)
    o["score"] = score_offer(o, L, S)
    o["flags"] = flags_for(o, L, S)
    o["blocking"] = [f for f in o["flags"] if f["sev"] == "Blocking"]
    ct, rows = propose_counter(o, L, S)
    o["counter_terms"], o["counter_rows"] = ct, rows
    o["ns_counter"] = _sheet(ct, o, L, S, costs)
    oc = dict(o)
    if not (o["appraisal_protected"] or o["appraisal_waived"] or o.get("gap_intent_only")):
        oc["gap_cover"] = ct["appraisal_gap"]
    oc.update(price=ct["price"], appraisal_gap=ct["appraisal_gap"], deposit=ct["deposit"], inspection_days=ct["inspection_days"],
              sale_contingency_days=ct["sale_contingency_days"], close=ct["close"], loan_approval_days=ct["loan_approval_days"])
    oc["close_days"] = (oc["close"] - L["analysis_date"]).days
    set_windows(oc)  # ENG-14: windows tied to the closing date follow the counter's closing
    if o["financed"] and o["approval"] in ("prequal", "none"):
        oc["approval"] = "preapproval"
    o["counter_score"], o["counter_risk_days"] = score_offer(oc, L, S)["total"], oc["risk_days"]
    if ct["price"] != o["price"]:  # OFR-116: ask for the letter at the price the counter sets, as its row does
        for f in o["flags"]:
            if f.get("topic") == "approval_cap" and f.get("request") and "pre-approval at" in f["request"]:
                f["request"] = (f"Please send an updated pre-approval at {money(ct['price'])} (the countered price) and "
                                "proof of funds for the balance to close.")
    return o


def target_net(L, S, costs, close, o=None):
    """A clean offer at list: no concessions, the agreed (or market) buyer-broker fee, same closing date. With an offer,
    on that offer's title terms (its Para. 9(c) box), so "vs. target" compares like with like (OFR-103)."""
    bb = S["default_buyer_broker_pct"] or 0
    return net_sheet(L["list_price"], 0, bb, 0, close, L, S, offer_costs(o, costs) if o else costs)


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
    impact = {"deed transfer tax": "high", "who pays owner's title": "high", "owner's title rate": "high",  # OFR-31: ~0.5% of price
              "title company fees": "med", "HOA estoppel fee": "low"}
    for label in sheet["missing"]:
        if label == "who pays owner's title":
            continue  # already recorded in prepare_listing
        A.add("listing", label, "not included",
              f"{label[:1].upper() + label[1:]} not known for this market: left out of the net (add it, or 0 if there is none, to the listing's costs)",
              impact.get(label, "med"))
    what = {"transfer_tax": ("transfer_tax_rate", "Transfer tax", "the state's rate"),
            "owner_title": ("title_estimate_pct", "Owner's title policy", "a title quote"),
            "title_fees": ("title_fees", "Title company fees", "a title quote")}
    for a in sheet["assumed"]:
        if a.get("estimate") and a["key"] in what:
            field, name, fix = what[a["key"]]
            shown = f"{a['value'] * 100:g}% of price" if a["key"] != "title_fees" else money(a["value"])
            A.add("listing", field, a["value"], f"{name}: national estimate of {shown} (Estimate; {fix} replaces it)", "med")


def check_fractions(node, where="file"):
    """Every unit in a listing or buyer file (finance.check_units): `*_pct` and the rates that are shares of price
    (`transfer_tax_rate`, `tax_rate`, `insurance_rate`) are fractions (0.025 = 2.5%), an interest rate is a percent
    (6.5). OFR-112: a rate not named `*_pct` is checked too, instead of printing 70% for 0.7."""
    try:
        finance.check_units(node, where)
    except ValueError as e:
        raise OfferError(str(e)) from e


def analyze(data, market=None, cma=None):
    """Full analysis of a listing file (see the skills' listing-file / buyer-file references)."""
    check_fractions(data)
    if cma:
        data = apply_cma(data, cma)
    costs = load_costs(data.get("listing") or {}, market)
    A = Assume()
    if data.get("_cma_side_note"):
        A.add("listing", "cma_side", "other side", data["_cma_side_note"], "high")
    if data.get("_cma_address_note"):  # CMA-102
        A.add("listing", "cma_address", "another property", data["_cma_address_note"], "high")
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
    for o in offers:
        if o["title_payer_by_contract"] and o["status"] in ACTIVE:
            L["cost_notes"].append(f"{o['label']}: owner's title policy paid by the {o['title_payer']}, who chooses the closing "
                                   "agent under the contract")
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
        o["target"] = target_net(L, S, costs, o["close"], o)
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
    if S["listing_fee_assumed"] and any(o.get("bb_from_listing") for o in active + res["incomplete"]):
        for a in A.items:  # OFR-127: one commission wording next to the net sheet's total fee
            if a["field"] == "listing_fee_pct" and a["value"]:
                a["why"] += (f". Where the listing broker pays the buyer's broker, the net sheet shows the total fee "
                             f"({pct(a['value'] + (S['default_buyer_broker_pct'] or 0))})")
    items = [a for a in A.items if not a["scope"].startswith("offer ") or a["scope"] in live]
    res["assumptions"] = merge_assumptions(items)
    res["missing"] = sorted(res["assumptions"], key=lambda a: IMPACT_ORDER[a["impact"]])
    return res


def merge_assumptions(items):
    """OFR-119: the same assumption on several offers (the contract form, the inspection period) is one item, its
    scope the first offer's and `also` the others', so a report lists it once."""
    out, seen = [], {}
    for a in items:
        key = (a["field"], a["why"], a["impact"])
        if a["scope"].startswith("offer ") and key in seen:
            seen[key].setdefault("also", []).append(a["scope"])
            continue
        if a["scope"].startswith("offer "):
            seen[key] = a
        out.append(a)
    return out


def scopes(a):
    """Every scope an assumption covers (merge_assumptions)."""
    return [a["scope"], *(a.get("also") or [])]


def preliminary_inputs(R, offer_id=None):
    """High-impact inputs still assumed (for the Preliminary banner), in plain names, deduplicated.

    In multi mode only the listing, the seller and the offer in question count.
    """
    names = {"cma_low / cma_high": "CMA range", "payoff": "mortgage payoff", "listing_fee_pct": "listing fee",
             "seller_concessions": "seller concessions", "buyer_broker_pct": "buyer-broker comp.",
             "financing": "financing type", "state": "property state", "deed transfer tax": "the local transfer tax (or confirm there is none)",
             "cma_side": "a CMA from the seller's side", "cma_address": "a CMA for this property"}  # CMA-101
    want = None if offer_id is None else {"listing", "seller", f"offer {offer_id}"}
    out = []
    for a in R["missing"]:
        if a["impact"] != "high" or (want is not None and not want.intersection(scopes(a))):
            continue
        n = names.get(a["field"], a["field"].replace("_", " "))
        if n not in out:
            out.append(n)
    return out
