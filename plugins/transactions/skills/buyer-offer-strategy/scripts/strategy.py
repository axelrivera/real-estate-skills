"""Build the buyer's offer: a recommended offer inside the buyer's limits, up to two alternatives, outlook bands.

    python3 scripts/strategy.py buyer.json [--cma file.cma.json] [--market market-profile.md] [--option recommended|stronger|lower_cost]

Every option is scored by the shared offer engine the listing side uses (seller net, appraisal downside,
certainty score, likely counter), so "best" means best as a listing agent would judge it.
Prints JSON with every value already formatted: the page-1 summary, the options side by side, the
buyer's cash, and the offer package worksheet for the chosen option. Or {"ok": false, "problems": [...]}.
See references/buyer-file.md for the input.
"""
import argparse
import copy
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import finance, handoff, offer_engine as oe, profiles  # noqa: E402

money, rnd = oe.money, oe.rnd
COMP_LABEL = {0: "Only offer", 1: "1 competing offer", 2: "2–3 competing", 3: "Cash or 4+ competing"}
# Competitiveness thresholds (strong / competitive / at risk) per competition level. Starting judgments.
BANDS = {0: (55, 40, 30), 1: (65, 55, 45), 2: (75, 60, 50), 3: (85, 72, 60)}
OPTION_LABEL = {"recommended": "Recommended", "stronger": "Stronger", "lower_cost": "Lower-cost"}
# National planning estimates, used only when neither the buyer file nor the market profile has a number.
DEFAULT_RATE = 6.5
NATIONAL_INSURANCE_RATE = 0.009
NATIONAL_CLOSING_PCT = {"financed": 0.035, "cash": 0.015}
PREPAIDS_PCT = 0.005  # prepaid interest, insurance and escrows on top of the market's closing costs (financed)


def _d(v):
    return v if isinstance(v, date) or v is None else datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


# --- inputs ------------------------------------------------------------------

def load_cma(data, cma_path=None):
    """The CMA handoff: --cma file first, else a handoff stored in the buyer file under 'cma'."""
    if cma_path:
        return handoff.load(cma_path)
    if isinstance(data.get("cma"), dict):
        return handoff.validate(data["cma"])
    return None


def apply_cma(B, h):
    """Fill the buyer file from a cma-handoff v1 record. Only fills what the file doesn't already say."""
    B = copy.deepcopy(B)
    P, V, M = B.setdefault("property", {}), B.setdefault("value", {}), B.setdefault("market", {})
    s, v, mk = h.get("subject") or {}, h["value"], h.get("market") or {}
    for key in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                "hoa_monthly", "flood_zone", "dom"):
        if s.get(key) not in (None, "") and P.get(key) in (None, ""):
            P[key] = s[key]
    if (h.get("market_profile") or {}).get("state") and not P.get("state"):
        P["state"] = h["market_profile"]["state"]
    V.setdefault("cma_low", v["low"])
    V.setdefault("cma_high", v["high"])
    V.setdefault("midpoint", v["midpoint"])
    if v.get("median_adjusted") is not None:
        V.setdefault("median_adjusted", v["median_adjusted"])
    V.setdefault("source", f"buyer CMA {h.get('as_of') or ''}".strip())
    for ours, theirs in (("sale_to_list", ("sale_to_list", "sale_to_list_recent", "sale_to_original_list_recent")),
                         ("median_dom", ("median_dom", "median_days_recent", "median_days")),
                         ("months_supply", ("months_supply",)),
                         ("share_with_seller_costs", ("share_with_seller_costs",)),
                         ("typical_seller_paid", ("typical_seller_paid",))):
        val = next((mk[k] for k in theirs if mk.get(k) is not None), None)
        if val is not None and M.get(ours) is None:
            M[ours] = val
    if h.get("offer_plan") and not B.get("cma_offer_plan"):
        B["cma_offer_plan"] = h["offer_plan"]
    return B


def prepare(B, A, market=None):
    """Defaults for everything missing, each one logged. Returns (B, costs)."""
    B = copy.deepcopy(B)
    today = _d(B.get("analysis_date")) or date.today()
    P, V, K = B.setdefault("property", {}), B.setdefault("value", {}), B.setdefault("costs", {})
    M, C, LS, BU = B.setdefault("market", {}), B.setdefault("competition", {}), B.setdefault("listing_side", {}), B.setdefault("buyer", {})
    if not P.get("list_price"):
        raise oe.OfferError("The list price is needed (property.list_price).")
    costs = oe.load_costs(P, market)
    if market is None and not oe.state_of(P):
        A.add("property", "state", costs.state, "Property's state not given: Florida costs assumed", "high")
    lp = P["list_price"]
    if not (V.get("cma_low") and V.get("cma_high")):
        A.add("value", "cma_low / cma_high", "list price", "No value range: run the buyer CMA or enter one; list price used as value", "high")
        V["cma_low"], V["cma_high"] = V.get("cma_low") or lp, V.get("cma_high") or lp
        V["assumed"] = True
    V["mid"] = V.get("midpoint") or (V["cma_low"] + V["cma_high"]) / 2
    V["point"] = V.get("median_adjusted") or V["mid"]  # best single value estimate, for the price anchor

    lux_at = BU.get("luxury_threshold") or (B.get("settings") or {}).get("luxury_threshold", 1_000_000)
    if lp >= lux_at:
        conv_down, why_down = 0.20, f"luxury price point (≥ {money(lux_at)})"
    elif BU.get("first_time_buyer"):
        conv_down, why_down = 0.03, "first-time buyer"
    else:
        conv_down, why_down = 0.05, "standard default"
    fin = finance.ALIASES.get(str(BU.get("financing") or "").lower(), str(BU.get("financing") or "").lower())
    BU["financing_source"] = "input"
    if fin not in finance.LOAN_PROGRAMS:
        if BU.get("financing"):
            A.add("buyer", "financing", "conventional",
                  f"Unrecognized loan type '{BU['financing']}': treated as conventional. Use cash, conventional, fha, va or usda", "high")
        fin = "conventional"
        BU["financing_source"] = "assumed"
        dp = BU.get("down_pct") if BU.get("down_pct") is not None else conv_down
        A.add("buyer", "financing", f"conventional {dp:.0%}", f"Loan type not provided: assumed conventional, {dp:.0%} down"
              + ("" if BU.get("down_pct") is not None else f" ({why_down})") + ". Confirm with the buyer's lender", "high")
    BU["financing"] = fin
    dflt_down = conv_down if fin == "conventional" else finance.LOAN_PROGRAMS[fin]["min_down"]
    if fin == "cash":
        BU["down_pct"] = 1.0
    elif BU.get("down_pct") is None:
        BU["down_pct"] = dflt_down
        if BU["financing_source"] == "input":
            A.add("buyer", "down_pct", dflt_down, f"Down payment not provided: assumed {dflt_down:.1%}"
                  + (f" ({why_down})" if fin == "conventional" else " (program minimum)") + ". Confirm with the lender", "med")
    if fin == "conventional" and BU["down_pct"] < 0.05 and not BU.get("first_time_buyer"):
        A.add("buyer", "down_pct", BU["down_pct"], "Conventional under 5% down usually requires a first-time-buyer program "
              "(income limits may apply). Confirm eligibility with the lender", "med")
    BU["max_price"] = oe.given(BU, "max_price", max(lp, V["cma_high"]), A, "buyer",
                               "Max price not provided: capped at the higher of list and value range", "high")
    if BU.get("cash_available") is None:
        est = round(lp * (BU["down_pct"] + 0.04))
        BU["cash_available"] = A.add("buyer", "cash_available", est, f"Cash available not provided: assumed down payment + 4% ({money(est)})", "high")
    BU["reserve_floor"] = oe.given(BU, "reserve_floor", 2000, A, "buyer", "Reserve floor not provided: assumed $2,000 kept after closing", "med")
    if BU.get("closing_cost_pct") is None:
        mpct = costs.get("closing_costs.buyer_closing_cost_pct")
        kind = "cash" if fin == "cash" else "financed"
        if mpct is not None:
            BU["closing_cost_pct"] = round(mpct / 2 if fin == "cash" else mpct + PREPAIDS_PCT, 4)
            src = f"{costs.described('closing_costs.buyer_closing_cost_pct')}" + ("" if fin == "cash" else " plus prepaids")
        else:
            BU["closing_cost_pct"] = NATIONAL_CLOSING_PCT[kind]
            src = "national planning estimate"
        A.add("buyer", "closing_cost_pct", BU["closing_cost_pct"],
              f"Closing costs estimated at {BU['closing_cost_pct']:.1%} of price ({src}; the lender's Loan Estimate governs)", "low")
    BU["approval"] = BU.get("approval") or ("pof_verified" if fin == "cash" else "preapproval")
    BU["lender_min_close_days"] = BU.get("lender_min_close_days") or (21 if fin == "cash" else 35)
    BU.setdefault("agent_track", "average")
    K["rate"] = oe.given(K, "rate", DEFAULT_RATE, A, "costs", f"Interest rate not provided: assumed {DEFAULT_RATE}% (use the lender's quote)", "low")
    if K.get("insurance_annual") is None:
        rate = costs.get("buyer_costs.insurance_rate")
        src = costs.described("buyer_costs.insurance_rate") if rate is not None else "national planning estimate"
        K["insurance_annual"] = round(max(2500, (rate if rate is not None else NATIONAL_INSURANCE_RATE) * lp), -2)
        A.add("costs", "insurance_annual", K["insurance_annual"], f"Insurance not provided: estimated at {money(K['insurance_annual'])}/yr ({src})", "low")
    P["hoa_monthly"] = P.get("hoa_monthly") or 0
    tax = finance.property_tax(lp, costs, school_mills=K.get("school_mills"), total_mills=K.get("total_mills"),
                               homestead=K.get("homestead", True))
    if tax["annual"] is None:
        A.add("costs", "property_tax", "not included", "No millage or tax rate for this market: the payment leaves out property tax",
              "high" if BU.get("max_payment") else "med")
    elif tax["estimated"]:
        A.add("costs", "property_tax", tax["basis"], f"No millage given: property tax estimated at {tax['basis'].removeprefix('about ')} "
              f"({costs.described('property_tax.fallback_rate')})", "low")

    lvl = C.get("level")
    heat = "normal"
    dom, med = P.get("dom"), M.get("median_dom")
    if (dom is not None and med and dom < 0.5 * med) or (M.get("sale_to_list") or 0) >= 0.99:
        heat = "hot"
    if (dom is not None and med and dom > 1.5 * med) or P.get("price_cuts"):
        heat = "soft"
    if lvl is None:
        lvl = {"hot": 2, "normal": 1, "soft": 0}[heat]
        A.add("competition", "level", COMP_LABEL[lvl],
              f"Competition unknown: inferred '{COMP_LABEL[lvl]}' from market signals ({heat}). Ask the listing agent", "med")
    C["level"], C["heat"] = lvl, heat
    LS["buyer_broker_offered_pct"] = LS.get("buyer_broker_offered_pct")
    LS["listing_fee_pct"] = LS.get("listing_fee_pct")
    B["analysis_date"] = today
    return B, costs


# --- money for the buyer -----------------------------------------------------

def buyer_cash(B, t):
    BU, fin = B["buyer"], B["buyer"]["financing"]
    down = round(t["price"] * BU["down_pct"])
    cc = round(t["price"] * BU["closing_cost_pct"])
    conc = min(t.get("seller_concessions", 0), cc)
    to_close = down + cc - conc
    gap = t.get("appraisal_gap", 0) if fin != "cash" else 0
    worst = to_close + gap
    return {"down": down, "cc": cc, "conc": -conc, "to_close": to_close, "gap": gap, "worst": worst,
            "reserve": BU["cash_available"] - worst, "wasted_conc": max(0, t.get("seller_concessions", 0) - cc)}


def monthly_payment(B, costs, price):
    BU, K, P = B["buyer"], B["costs"], B["property"]
    tax = finance.property_tax(price, costs, school_mills=K.get("school_mills"), total_mills=K.get("total_mills"),
                               homestead=K.get("homestead", True))["annual"] or 0
    p = finance.monthly_payment(price, BU["financing"], BU["down_pct"], K["rate"], tax, K["insurance_annual"], P["hoa_monthly"])
    return round(p["total"])


def concession_cap(B, price):
    return (finance.concession_cap(B["buyer"]["financing"], B["buyer"]["down_pct"]) or 0) * price


# --- engine bridge -------------------------------------------------------------

def engine_data(B, variants):
    P, V, LS, BU = B["property"], B["value"], B["listing_side"], B["buyer"]
    listing = {k: P.get(k) for k in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                                     "hoa_monthly", "flood_zone", "annual_tax", "costs")}
    if not V.get("assumed"):  # without a value range the engine measures appraisal risk against list price
        listing.update(cma_low=V["cma_low"], cma_high=V["cma_high"], cma_mid=V["mid"])
    seller = {"listing_fee_pct": LS["listing_fee_pct"], "offered_buyer_broker_pct": LS["buyer_broker_offered_pct"]}
    if P.get("seller_deadline"):
        seller["deadline"] = P["seller_deadline"]
    offers = []
    for vid, t in variants:
        o = {"id": vid, "price": t["price"], "financing": BU["financing"], "down_pct": BU["down_pct"], "approval": BU["approval"],
             "lender_called": BU.get("lender_called", False), "insurance_quote": t.get("insurance_quote", BU.get("insurance_quote")),
             "agent_track": BU.get("agent_track"), "buyer": "Buyer"}
        for k in ("deposit", "seller_concessions", "buyer_broker_pct", "home_warranty", "inspection_days", "loan_approval_days",
                  "appraisal_gap", "closing_days", "sale_contingency_days", "kickout", "escalation", "contract_form"):
            if t.get(k) is not None:
                o[k] = t[k]
        if BU["financing"] != "cash":
            o["appraisal_contingency"] = t.get("appraisal_days", 21)
        offers.append(o)
    return {"analysis_date": str(B["analysis_date"]), "listing": listing, "seller": seller, "offers": offers}


def run_engine(B, costs, variants):
    R = oe.analyze(engine_data(B, variants), market=costs.market)
    return R, {o["id"]: o for o in R["offers"]}


def ci(o, target_net, lp):
    """Competitiveness index = strength score + 5 points per 1% of list price the seller nets above a clean offer at list."""
    return o["score"]["total"] + 5 * (o["ns"]["net_adj"] - target_net) / (0.01 * lp)


def band_of(v, level):
    s, c, r = BANDS[level]
    return ("strong", "Strong") if v >= s else ("comp", "Competitive") if v >= c else ("risk", "At risk") if v >= r else ("unl", "Unlikely")


# --- offer builder -------------------------------------------------------------

def build_offer(B, costs):
    """Rule-based best offer inside the buyer's limits (references/offer-rules.md). Returns (terms, reasons)."""
    P, V, BU, C, LS = B["property"], B["value"], B["buyer"], B["competition"], B["listing_side"]
    lp, lvl, fin = P["list_price"], C["level"], BU["financing"]
    why = {}
    anchor = min(lp, V["point"])
    price = {0: max(V["cma_low"], anchor * 0.98), 1: anchor, 2: min(max(lp, V["mid"]), V["cma_high"]), 3: V["cma_high"]}[lvl]
    why["price"] = {0: "Room to negotiate: little competition", 1: "At value, not above it",
                    2: "At list, inside the value range, to compete", 3: "Top of the value range to compete"}[lvl]
    if price > BU["max_price"]:
        price, why["price"] = BU["max_price"], "Capped at your max price"
    price = lp if abs(price - lp) < 1000 else rnd(price, 1000, "down" if price > lp else "round")
    if BU.get("max_payment") and monthly_payment(B, costs, price) > BU["max_payment"]:
        while price > 1000 and monthly_payment(B, costs, price) > BU["max_payment"]:
            price -= 1000
        why["price"] = f"Capped so the payment stays under ${BU['max_payment']:,}/mo" + (" (below the value range)" if price < V["cma_low"] else "")
    t = {"price": price}
    cc = round(price * BU["closing_cost_pct"])
    down = round(price * BU["down_pct"])
    spare = BU["cash_available"] - BU["reserve_floor"] - down - cc
    cap = concession_cap(B, price)
    need = max(0, -spare)
    want = {0: cc, 1: max(need, cc * 0.5), 2: need, 3: need}[lvl]
    conc = min(rnd(min(cap, want), 500, "up"), int(cc // 100 * 100), int(cap // 100 * 100)) if want > 0 else 0
    t["seller_concessions"] = conc
    why["seller_concessions"] = ("Covers your closing costs; sellers here often pay them" if lvl == 0 else
                                 "Only what your cash can't cover" if conc else "None needed: keeps the offer clean")
    if need > cap:
        why["seller_concessions"] += f" (program cap {money(round(cap))} reached)"
    spare_after = BU["cash_available"] - BU["reserve_floor"] - (down + cc - min(conc, cc))
    gap = 0
    if fin != "cash" and price > V["mid"]:
        gap = min(rnd(price - V["mid"], 1000, "up"), max(0, rnd(spare_after, 500, "down")))
    t["appraisal_gap"] = gap
    if fin == "cash":
        why["appraisal_gap"] = "Cash: no appraisal contingency"
    elif price <= V["mid"]:
        why["appraisal_gap"] = "Not needed: price is at or below value midpoint"
    elif gap >= price - V["mid"]:
        why["appraisal_gap"] = "Covers the price above value midpoint"
    elif gap:
        why["appraisal_gap"] = "As much as your reserve allows"
    else:
        why["appraisal_gap"] = f"No room: your cash after the {money(BU['reserve_floor'])} reserve is fully used"
    dep_pct = {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.03}[lvl] if fin != "cash" else {0: 0.03, 1: 0.05, 2: 0.10, 3: 0.10}[lvl]
    t["deposit"] = int(min(rnd(price * dep_pct, 500, "up"), max(1000, down + cc - conc)))
    why["deposit"] = f"{dep_pct:.0%} shows commitment; refundable during inspection; counts toward cash to close"
    old = (B["analysis_date"].year - (P.get("year_built") or 2000)) > 25
    t["inspection_days"] = 7 if (lvl >= 2 and not old) else 10
    reports = " + 4-point" if costs.state == "FL" else ""
    why["inspection_days"] = (f"Room for a full inspection{reports}" + (" on an older home" if old else "")
                              if t["inspection_days"] == 10 else "Short window to compete; newer home")
    if fin != "cash":
        t["loan_approval_days"] = 21 if (fin == "conventional" and lvl >= 2) else 30
        why["loan_approval_days"] = "Lender standard" if t["loan_approval_days"] == 30 else "Faster approval to compete"
        t["appraisal_days"] = 21
    t["closing_days"] = BU["lender_min_close_days"] + (0 if lvl >= 1 else 10)
    why["closing_days"] = "Fastest your lender can reliably close" if lvl >= 1 else "Comfortable timeline"
    t["home_warranty"] = 0
    why["home_warranty"] = "Not asked of the seller; keeps the net clean"
    if LS["buyer_broker_offered_pct"] is not None:
        t["buyer_broker_pct"], why["buyer_broker_pct"] = LS["buyer_broker_offered_pct"], "What the seller is offering"
    else:
        t["buyer_broker_pct"] = BU.get("buyer_broker_agreement_pct")
        if t["buyer_broker_pct"] is None:
            t["buyer_broker_pct"] = costs.get("brokerage.buyer_broker_fee_pct") or 0
        why["buyer_broker_pct"] = "Per your buyer-broker agreement (confirm with listing agent)"
    t["contract_form"] = "as_is" if "FR/BAR AS IS" in (costs.get("contract.forms") or []) else None
    t["insurance_quote"] = True
    why["insurance_quote"] = "Get the quote before submitting; listing agents weigh it on older roofs"
    if lvl >= 2 and fin in ("cash", "conventional") and BU["down_pct"] >= 0.10:
        capv = min(BU["max_price"], rnd(V["cma_high"] + (gap if fin != "cash" else 0), 1000, "down"))
        if BU.get("max_payment"):
            while capv > price and monthly_payment(B, costs, capv) > BU["max_payment"]:
                capv -= 1000
        while capv > price and buyer_cash(B, {"price": capv, "seller_concessions": conc, "appraisal_gap": gap})["reserve"] < BU["reserve_floor"]:
            capv -= 1000
        if capv > price:
            t["escalation"] = {"increment": 1000, "cap": capv}
            why["escalation"] = f"+$1,000 over the best offer, cap {money(capv)}: the appraisal can support it and your reserve holds"
        else:
            why["escalation"] = "Not used: no room in your cash or payment to go higher"
    elif lvl >= 2:
        why["escalation"] = "Not used: with low down payment, price above value gets cut by the appraisal"
    return t, why


def stronger(B, t):
    """Next step up: more gap coverage and a 3% deposit, never beyond the buyer's actual cash (may dip below the reserve)."""
    s = dict(t)
    if buyer_cash(B, t)["reserve"] < 0:
        return None  # can't afford the base offer: a stronger one is meaningless
    if B["buyer"]["financing"] != "cash":
        c = buyer_cash(B, t)
        room = max(0, rnd(B["buyer"]["cash_available"] - c["worst"], 500, "down"))
        s["appraisal_gap"] = t.get("appraisal_gap", 0) + min(rnd(0.0055 * t["price"], 1000, "up"), room)
    s["deposit"] = max(t.get("deposit", 0), rnd(0.03 * t["price"], 500, "up"))
    return None if s == t else s


def lower_cost(B, costs, rec):
    """Write for one competition level lower, without escalation. None if it's the same offer."""
    lvl = B["competition"]["level"]
    if lvl == 0:
        return None, {}
    B2 = copy.deepcopy(B)
    B2["competition"]["level"] = lvl - 1
    t, why = build_offer(B2, costs)
    t = {**{k: v for k, v in rec.items() if k not in t}, **t}
    t.pop("escalation", None)
    return (None, {}) if t == rec else (t, why)


# --- top level -----------------------------------------------------------------

def analyze(B_in, market=None, cma=None):
    B0 = apply_cma(B_in, cma) if cma else copy.deepcopy(B_in)
    A = oe.Assume()
    B, costs = prepare(B0, A, market)
    lvl = B["competition"]["level"]
    rec, why = build_offer(B, costs)
    ov = B.get("overrides") or {}
    for k, v in ov.items():  # the agent's judgment wins; the report marks it
        rec[k] = v
        why[k] = "Agent's choice"
    variants = [("recommended", rec)]
    st = stronger(B, rec)
    if st:
        variants.append(("stronger", st))
    lc, lc_why = lower_cost(B, costs, rec)
    if lc:
        variants.append(("lower_cost", lc))
    R, O = run_engine(B, costs, variants)
    lp = B["property"]["list_price"]
    tgt = O["recommended"]["target"]["net_adj"]
    engine_assumed = [a for a in R["assumptions"] if not a["scope"].startswith("offer") and a["scope"] != "seller"
                      and a["field"] not in ("cma_low / cma_high", "state")]
    res = {"B": B, "R": R, "O": O, "why": why, "lc_why": lc_why, "terms": dict(variants), "target": tgt, "overrides": list(ov),
           "assumptions": A.items + engine_assumed, "costs": costs, "sample": bool(B_in.get("sample"))}
    res["cash"] = {k: buyer_cash(B, t) for k, t in variants}
    res["payment"] = {k: monthly_payment(B, costs, t["price"]) for k, t in variants}
    esc_ = rec.get("escalation")
    res["cash_at_cap"] = buyer_cash(B, dict(rec, price=esc_["cap"])) if esc_ else None
    res["ci"] = {k: ci(O[k], tgt, lp) for k, _ in variants}
    res["bands"] = {k: {lv: band_of(res["ci"][k], lv) for lv in range(4)} for k, _ in variants}
    if "lower_cost" in res["terms"] and lvl >= 2 and res["bands"]["lower_cost"][lvl][0] == "unl":
        for d in (res["terms"], res["cash"], res["payment"], res["ci"], res["bands"], O):
            d.pop("lower_cost", None)
        res["lower_cost_dropped"] = True
    lim = {}
    BU, V = B["buyer"], B["value"]
    for k, t in res["terms"].items():
        c, issues = res["cash"][k], []
        if t["price"] > BU["max_price"]:
            issues.append("over max price")
        if c["reserve"] < 0:
            issues.append("not enough cash")
        elif c["reserve"] < BU["reserve_floor"]:
            issues.append(f"reserve {money(c['reserve'])} below {money(BU['reserve_floor'])} floor")
        if BU.get("max_payment") and res["payment"][k] > BU["max_payment"]:
            issues.append("over max payment")
        cap = concession_cap(B, t["price"])
        if t.get("seller_concessions", 0) > cap + 1:
            issues.append(f"concessions over program cap ({money(round(cap))})")
        if c["wasted_conc"]:
            issues.append(f"{money(c['wasted_conc'])} of concessions exceed closing costs")
        lim[k] = issues
    res["limits"] = lim
    cons = []
    rc = res["cash"]["recommended"]
    if rc["reserve"] < 0:
        cons.append(f"Not enough cash: this offer needs {money(rc['worst'])} but you have {money(BU['cash_available'])} "
                    f"({money(-rc['reserve'])} short). Options: seller concessions up to the program cap, down-payment assistance or "
                    "gift funds, a lower price range, or a conversation with the lender about loan options.")
    elif rc["reserve"] < BU["reserve_floor"]:
        cons.append(f"Tight on cash: even the recommended offer leaves {money(rc['reserve'])}, below your {money(BU['reserve_floor'])} reserve floor.")
    if rec["price"] < V["cma_low"] and "payment" in why.get("price", ""):
        cons.append(f"Your ${BU['max_payment']:,}/mo payment limit caps the price at {money(rec['price'])}, below the "
                    f"{money(V['cma_low'])}–{money(V['cma_high'])} value range. Expect this offer to be passed over unless the seller has no other interest.")
    elif rec["price"] < V["cma_low"] and "max price" in why.get("price", ""):
        cons.append(f"Your max price ({money(BU['max_price'])}) is below the value range: expect this offer to be passed over.")
    res["constraints"] = cons
    res["missing"] = sorted(res["assumptions"], key=lambda a: oe.IMPACT_ORDER[a["impact"]])
    res["chosen"] = B.get("chosen_option") if B.get("chosen_option") in res["terms"] else "recommended"
    return res


# --- formatted views (shared by the markdown template and the PDF) ---------------

TERM_KEYS = [("price", "Price"), ("seller_concessions", "Seller concessions"), ("deposit", "Escrow deposit"),
             ("inspection_days", "Inspection period"), ("loan_approval_days", "Loan approval period"), ("appraisal_gap", "Appraisal gap"),
             ("closing_days", "Closing"), ("buyer_broker_pct", "Buyer-broker comp."), ("home_warranty", "Home warranty"),
             ("escalation", "Escalation")]


def term_val(k, t, B):
    v = t.get(k)
    if k == "price":
        return money(v)
    if k == "seller_concessions":
        return money(v) if v else "None"
    if k == "deposit":
        return f"{money(v)} ({v / t['price']:.1%})"
    if k in ("inspection_days", "loan_approval_days"):
        return f"{v} days" if v else "—"
    if k == "appraisal_gap":
        return (money(v) if v else "None") if B["buyer"]["financing"] != "cash" else "—"
    if k == "closing_days":
        return f"{v} days ({(B['analysis_date'] + timedelta(days=v)):%b %-d})"
    if k == "buyer_broker_pct":
        return f"{v:.1%} from seller" if v else "Not requested"
    if k == "home_warranty":
        return "Not requested" if not v else f"Seller pays {money(v)}"
    if k == "escalation":
        return f"+{money(v['increment'])}, cap {money(v['cap'])}" if v else "None"
    return str(v)


def diff_text(r, k):
    """Short 'what's different from the recommended offer' text."""
    B = r["B"]
    a, b = r["terms"]["recommended"], r["terms"][k]
    out = [f"{labl.lower()} {term_val(key, b, B)}" for key, labl in TERM_KEYS if a.get(key) != b.get(key)]
    txt = "; ".join(out) or "Same terms"
    return txt[:1].upper() + txt[1:]


def fin_line(B):
    BU, f = B["buyer"], B["buyer"]["financing"]
    txt = "Cash" if f == "cash" else f"{oe.FIN_LABEL[f]} · {oe.pct(BU['down_pct'])} down"
    return txt + (" (assumed; confirm with lender)" if BU.get("financing_source") == "assumed" else " (per buyer and lender)")


def preliminary(r):
    hi = [a for a in r["missing"] if a["impact"] == "high"]
    if not hi:
        return None
    names = {"cma_low / cma_high": "value range (buyer CMA)", "state": "property state", "property_tax": "property tax"}
    need = list(dict.fromkeys(names.get(a["field"], a["field"].replace("_", " ")) for a in hi))
    n = len(r["missing"])
    return (f"**Preliminary: based on limited data.** Add {', '.join(need)} to sharpen the recommendation; "
            f"{n} input{'s' if n != 1 else ''} assumed in total (listed at the end).")


def summary(r):
    """Page 1 of the Offer Options report, formatted. The markdown template uses the same values."""
    B, O, lvl = r["B"], r["O"], r["B"]["competition"]["level"]
    BU, P, C = B["buyer"], B["property"], B["competition"]
    rec, rc = O["recommended"], r["cash"]["recommended"]
    br = r["bands"]["recommended"][lvl]
    dn = rec["ns"]["net_adj"] - r["target"]
    why = (f"The strongest offer inside your limits. A listing agent would score it **{rec['score']['total']}/100**, and it nets the seller "
           + ("about the same as a clean offer at list." if abs(dn) < 500 else f"{money(abs(dn))} {'less' if dn < 0 else 'more'} than a clean offer at list."))
    if rc["reserve"] < 0:
        why = f"**Not affordable as structured:** {money(-rc['reserve'])} short on cash. " + why
    if "stronger" in O:
        bs, cs = r["bands"]["stronger"][lvl], r["cash"]["stronger"]
        if bs != br:
            why += f" Reaching **{bs[1]}** takes {money(cs['worst'] - rc['worst'])} more worst-case cash" + (
                f", below your {money(BU['reserve_floor'])} reserve floor." if cs["reserve"] < BU["reserve_floor"] else ".")
        else:
            why += " Adding more cash wouldn't change the outlook."
    if "lower_cost" in O:
        bl, cl = r["bands"]["lower_cost"][lvl], r["cash"]["lower_cost"]
        why += f" Writing softer saves {money(rc['worst'] - cl['worst'])}" + (f" but drops to **{bl[1]}**." if bl != br else " with the same outlook.")
    if BU["financing"] in ("fha", "va", "usda") and lvl >= 2:
        why += f" {BU['financing'].upper()} financing caps the score, so certainty and net do the work, not escalation."

    t, w = r["terms"]["recommended"], r["why"]
    terms = []
    for key, labl in TERM_KEYS:
        if key in ("loan_approval_days", "appraisal_gap") and BU["financing"] == "cash":
            continue
        if key == "escalation" and not t.get("escalation") and not w.get("escalation"):
            continue
        terms.append({"term": labl, "offer": term_val(key, t, B), "why": w.get(key) or "", "agent": key in r["overrides"]})

    options = []
    for k in O:
        o, c = O[k], r["cash"][k]
        if k == "recommended":
            what = "Strongest offer inside your limits" if not r["limits"][k] else "Best structure available; " + r["limits"][k][0]
            status = "good" if not r["limits"][k] else "risk"
        elif k == "stronger":
            same = r["bands"][k][lvl] == br
            what = diff_text(r, k) + (". Same outlook for more cash" if same else f". Reaches {r['bands'][k][lvl][1]}") + (
                f"; {r['limits'][k][0]}" if r["limits"][k] else "")
            status = "caution"
        else:
            what = diff_text(r, k) + f". Saves {money(rc['worst'] - c['worst'])}" + (
                "" if r["bands"][k][lvl] == br else f"; outlook {r['bands'][k][lvl][1]}")
            status = "caution"
        options.append({"key": k, "option": OPTION_LABEL[k], "price": money(o["price"]), "outlook": r["bands"][k][lvl][1],
                        "outlook_class": r["bands"][k][lvl][0], "seller_net": money(o["ns"]["net_adj"]), "worst_cash": money(c["worst"]),
                        "reserve": money(c["reserve"]), "what": what, "status": status})
    bands = [{"level": COMP_LABEL[lv] + (" (expected)" if lv == lvl else ""),
              "values": [{"band": r["bands"][k][lv][1], "class": r["bands"][k][lv][0]} for k in O]} for lv in range(4)]
    exposure = [["Cash to close (deposit counts toward it)", money(rc["to_close"])],
                ["+ appraisal gap if the appraisal is low", money(rc["gap"])],
                ["Worst-case cash needed", f"{money(rc['worst'])} of {money(BU['cash_available'])}"],
                ["Left in reserve", f"{money(rc['reserve'])} (floor {money(BU['reserve_floor'])})"],
                ["Est. monthly payment", f"${r['payment']['recommended']:,}" + (f" of ${BU['max_payment']:,}" if BU.get("max_payment") else "")],
                ["Deposit at risk after", f"{rec['firm_date']:%a %b %-d} ({money(rec['deposit'])})"]]
    if r.get("cash_at_cap"):
        cc = r["cash_at_cap"]
        exposure.append([f"At the {money(t['escalation']['cap'])} cap", f"{money(cc['worst'])} · reserve {money(cc['reserve'])}"])
    signal = C.get("note") or f"None given; market reads {C['heat']}"
    if P.get("dom") is not None and B["market"].get("median_dom"):
        signal += f"; {P['dom']} DOM vs. {B['market']['median_dom']} median"
    deadline = f" before {C['deadline']}" if C.get("deadline") else ""
    return {
        "outlook": br[1], "outlook_class": br[0], "competition": COMP_LABEL[lvl] + ("" if C.get("note") else " (inferred)"),
        "why": why, "submit_by": C.get("deadline") or "Before the listing agent's deadline", "signal": signal,
        "financing": fin_line(B), "financing_assumed": BU.get("financing_source") == "assumed",
        "limits": f"Max {money(BU['max_price'])} · cash {money(BU['cash_available'])} · keep {money(BU['reserve_floor'])}"
                  + (f" · ≤ ${BU['max_payment']:,}/mo" if BU.get("max_payment") else ""),
        "strength": rec["score"]["total"], "seller_net": money(rec["ns"]["net_adj"]), "worst_cash": money(rc["worst"]),
        "reserve_short": rc["reserve"] < BU["reserve_floor"],
        "terms": terms, "options": options, "bands": bands, "option_labels": [OPTION_LABEL[k] for k in O],
        "exposure": exposure, "constraints": r["constraints"], "preliminary": preliminary(r),
        "next_step": ("pick an option, get the insurance quote and a pre-approval letter at the offer price (not your max, so it doesn't "
                      f"reveal your ceiling), and I'll prepare the offer package{deadline}."),
    }


# --- offer package worksheet -------------------------------------------------------

FRBAR_RIDERS = {"fha_va": "FHA/VA Financing", "appraisal": "Appraisal Contingency", "hoa": "Homeowners' Association / Community Disclosure",
                "condo": "Condominium", "lead": "Lead-Based Paint Disclosure (federal)", "insurance": "Homeowners' / Flood Insurance (if in your form set)",
                "sale": "Sale of Buyer's Property", "kickout": "Kick-out clause", "backup": "Back-up Contract", "escalation": "Escalation addendum",
                "cdd": "CDD disclosure", "short_sale": "Short Sale"}
GENERIC_RIDERS = {"fha_va": "FHA/VA financing addendum", "appraisal": "Appraisal contingency addendum", "hoa": "HOA / community addendum",
                  "condo": "Condominium addendum", "lead": "Lead-Based Paint Disclosure (federal)", "insurance": "Insurance contingency (if your forms have one)",
                  "sale": "Sale of buyer's property addendum", "kickout": "Kick-out clause", "backup": "Back-up contract addendum",
                  "escalation": "Escalation addendum", "cdd": "Special district / assessment disclosure", "short_sale": "Short sale addendum"}


def blank(x):
    """A blank the agent must fill in (rendered red in the PDF)."""
    return f"[{x}]"


def worksheet(r, variant=None):
    """Contract entries, riders, additional terms, documents to request and the package checklist for one option.

    Only offer terms: never the buyer's max price, cash or reserve.
    """
    variant = variant or r["chosen"]
    if variant not in r["terms"]:
        raise oe.OfferError(f"The {OPTION_LABEL.get(variant, variant)} option isn't available here ({', '.join(r['terms'])}).")
    B, costs = r["B"], r["costs"]
    P, BU, C, W = B["property"], B["buyer"], B["competition"], B.get("worksheet") or {}
    t, o = r["terms"][variant], r["O"][variant]
    frbar = "FR/BAR AS IS" in (costs.get("contract.forms") or [])
    fin = BU["financing"]
    financed = fin != "cash"
    price = t["price"]
    loan = round(price * (1 - BU["down_pct"])) if financed else 0
    close = oe.prior_weekday(B["analysis_date"] + timedelta(days=t["closing_days"]) if t.get("closing_days") else o["close"])
    form = W.get("contract_form") or t.get("contract_form") or ("as_is" if frbar else None)
    if frbar:
        form_name = ("FR/BAR AS IS Residential Contract for Sale and Purchase" if form == "as_is"
                     else "FR/BAR Residential Contract for Sale and Purchase (Standard)")
        form_why = ("Buyer may cancel for any reason during the inspection period; no seller repair obligation. Usual choice for competitive offers."
                    if form == "as_is" else "Seller repair obligations up to a repair limit; set the limit per the form version.")
    else:
        form_name = W.get("contract_name") or "Your state's standard residential purchase contract"
        form_why = "Paragraph numbers vary by form, so find each entry by its name and confirm the form version."
    deadline = W.get("acceptance_deadline") or C.get("deadline")
    para = (lambda p: p) if frbar else (lambda p: "")
    title_payer = costs.get("closing_costs.owner_title.payer")
    title_src = costs.described("closing_costs.owner_title.payer")
    reports = "4-point, wind-mitigation" if costs.state == "FL" else "insurance"
    rows = [  # (paragraph, field, entry, note)
        (para("1"), "Buyer(s)", W.get("buyer_names") or blank("buyer names exactly as on pre-approval"), "Match the pre-approval letter"),
        (para("1"), "Seller(s)", blank("from listing / tax record"), ""),
        (para("1"), "Property address", P.get("address") or blank("address"), ""),
        (para("1"), "Legal description / parcel ID", W.get("legal_description") or blank("from the county property appraiser"), W.get("parcel_id") or ""),
        (para("1"), "Personal property included", W.get("personal_property") or blank("items in MLS (range, refrigerator, washer/dryer…)"),
         "List anything the buyer expects to stay"),
        (para("2"), "Purchase price", f"**{money(price)}**", ""),
        (para("2(a)"), "Initial deposit", f"**{money(t['deposit'])}** within 3 days of Effective Date" if frbar else f"**{money(t['deposit'])}**",
         "" if frbar else "Due date per the contract"),
        (para("2(a)"), "Escrow agent", W.get("escrow_agent") or blank("title company name, address, phone"), ""),
        (para("2(b)"), "Additional deposit", "None", "Keep the full deposit up front: it scores better"),
    ]
    if financed:
        rows.append((para("2(c) / 8"), "Financing", f"**{oe.FIN_LABEL[fin]}** · loan {money(loan)} ({1 - BU['down_pct']:.1%} LTV)",
                     "As chosen by the buyer and lender" + (" (ASSUMED: confirm before entering)" if BU.get("financing_source") == "assumed" else "")))
        rows.append((para("8(b)"), "Loan approval period", f"**{t.get('loan_approval_days', 30)} days**",
                     "Loan application within 5 days (form default)" if frbar else ""))
    else:
        rows.append((para("8"), "Financing", "**Cash** (no financing contingency)", "Attach proof of funds"))
    rows += [
        (para("2(d)"), "Balance to close", f"{money(price - t['deposit'] - loan)} before prorations and costs", "Buyer's funds at closing"),
        (para("3"), "Time for acceptance", deadline or blank("date and time"), "Match the listing agent's highest-and-best deadline"),
        (para("4"), "Closing date", f"**{close:%B %-d, %Y}**", "Weekday; lender confirmed"),
        (para("6"), "Occupancy / possession", "At closing, vacant", ""),
    ]
    if title_payer == "seller":
        rows.append((para("9"), "Title evidence / owner's policy", "Seller designates title agent and pays owner's policy", f"Local custom ({title_src}); verify"))
    elif title_payer == "buyer":
        rows.append((para("9"), "Title evidence / owner's policy", "Buyer designates title agent and pays owner's policy", f"Local custom ({title_src}); verify"))
    else:
        rows.append((para("9"), "Title evidence / owner's policy", blank("who pays per local custom"), "Ask the title company"))
    rows += [
        (para("9"), "Seller-paid closing costs", f"**{money(t['seller_concessions'])}** toward buyer's costs, prepaids and escrows"
         if t.get("seller_concessions") else "None", "Use the form's seller-contribution line if present, else Additional Terms"),
        (para("9"), "Home warranty", "None (buyer may purchase separately)" if not t.get("home_warranty") else f"Seller pays up to {money(t['home_warranty'])}", ""),
        (para("9"), "Survey", "Buyer's expense (recommended)", "Lender may require"),
        (para("12"), "Inspection period", f"**{t['inspection_days']} days**", f"Book the inspector{' and 4-point' if costs.state == 'FL' else ''} before submitting"),
    ]

    names = FRBAR_RIDERS if frbar else GENERIC_RIDERS
    riders = []  # (name, inputs, why)
    yb, roof, fz = P.get("year_built"), P.get("roof_year"), (P.get("flood_zone") or "").upper()
    if fin in ("fha", "va"):
        riders.append((names["fha_va"], f"Loan type: {fin.upper()} · appraised-value threshold: **{money(price)}**",
                       "Required with FHA/VA loans (amendatory / escape clause)"))
    if fin in ("conventional", "usda"):
        riders.append((names["appraisal"], f"Value threshold: **{money(price)}** · appraisal period: **{t.get('appraisal_days', 21)} days**",
                       "Protects the buyer if the appraisal is low" + ("; pair with gap language below" if t.get("appraisal_gap") else "")))
    if (P.get("hoa_monthly") or 0) > 0 or W.get("hoa_name"):
        riders.append((names["hoa"], f"Association: {W.get('hoa_name') or blank('name')} · dues: {money(P['hoa_monthly'])}/mo · "
                                     f"approval required: {blank('yes/no')} · special assessments: {blank('ask')}", "Required when the property is in an HOA"))
    if P.get("type") == "condo":
        riders.append((names["condo"], f"Association: {blank('name')} · request reserve study and milestone inspection status", "Required for condos"))
    if yb and yb < 1978:
        riders.append((names["lead"], "Seller disclosure + buyer acknowledgment; 10-day risk assessment (buyer may waive)", f"Required: built {yb}"))
    ins_reason = []
    if roof and B["analysis_date"].year - roof >= 15:
        ins_reason.append(f"{B['analysis_date'].year - roof}-year roof")
    if fz[:1] in ("A", "V"):
        ins_reason.append(f"flood zone {fz}")
    if not BU.get("insurance_quote"):
        ins_reason.append("no insurance quote yet")
    if ins_reason and financed:
        riders.append((names["insurance"], f"Days to obtain coverage: {blank('e.g. within inspection period')} · max acceptable premium: {blank('$/yr')}",
                       "Recommended: " + ", ".join(ins_reason) + ". Weakens the offer slightly; skip if a quote is already in hand"))
    if BU.get("needs_sale"):
        riders.append((names["sale"], f"Buyer's property: {blank('address')} · days: {blank('21 or fewer')}", "Weakens the offer; pair with a kick-out clause"))
        riders.append((names["kickout"], "Notice: 72 hours", "Lets the seller keep marketing"))
    if C.get("backup"):
        riders.append((names["backup"], "—", "Seller already has an accepted contract"))
    if t.get("escalation"):
        e = t["escalation"]
        riders.append((names["escalation"], f"Increment: **{money(e['increment'])}** · cap: **{money(e['cap'])}** · proof of competing offer required",
                       "Only because the appraisal can support the cap and the buyer's reserve holds"))
    if P.get("cdd"):
        riders.append((names["cdd"], f"Annual amount: {blank('amount')} · outstanding debt: {blank('amount')}", "Property is in a special district"))
    if P.get("short_sale"):
        riders.append((names["short_sale"], f"Lender approval period: {blank('days')}", "Listed as a short sale"))

    clauses = []
    if t.get("seller_concessions"):
        clauses.append(("Seller-paid closing costs",
                        f"Seller shall pay up to {money(t['seller_concessions'])} toward Buyer's closing costs, prepaid items and escrows, as allowed by "
                        "Buyer's lender. Any amount not used shall not be paid to Buyer."))
    if financed and t.get("appraisal_gap"):
        rider = names["fha_va"] if fin in ("fha", "va") else names["appraisal"]
        clauses.append(("Appraisal gap",
                        f"If the appraised value is less than the Purchase Price, Buyer shall pay in cash up to {money(t['appraisal_gap'])} of the "
                        f"difference between the appraised value and the Purchase Price. If the difference exceeds {money(t['appraisal_gap'])}, "
                        f"Buyer's rights under the {rider} shall apply."))
    clauses.append(("Seller-provided reports",
                    f"Within 2 days after the Effective Date, Seller shall provide copies of any existing {reports} and inspection reports, "
                    "permits, and insurance claims history for the Property in Seller's possession."))
    if t.get("escalation") and not any(x[0] == names["escalation"] for x in riders):
        e = t["escalation"]
        clauses.append(("Escalation", f"Buyer will pay {money(e['increment'])} more than any bona fide competing offer, up to {money(e['cap'])}, "
                                      "upon receipt of a copy of that offer."))

    docs = ["Seller's property disclosure", "Permits and open-permit search", f"Existing inspection{', 4-point and wind-mit' if costs.state == 'FL' else ''} reports",
            "Survey, if available"]
    if (P.get("hoa_monthly") or 0) > 0:
        docs.insert(1, "HOA documents, rules and estoppel")
    if yb and yb < 1978:
        docs.append("Lead-based paint records")
    if P.get("cdd"):
        docs.append("Special district information")

    CK = BU.get("checklist") or {}
    fl = costs.state == "FL"
    rider_list = ", ".join(x[0].split(" (")[0] for x in riders) or "none"
    package = [  # (group, item, status, note)
        ("Contract", f"{'AS IS contract' if form == 'as_is' else 'Contract'} completed and initialed on every page", CK.get("contract", "Pending"), ""),
        ("Contract", f"Riders attached and signed: {rider_list}", CK.get("riders", "Pending"), ""),
        ("Contract", "Additional terms reviewed by broker", CK.get("terms", "Pending"), ""),
        ("Buyer docs", "Pre-approval letter at the offer price, not the max" if financed else "Proof of funds (recent statement in the buyer's name)",
         CK.get("pre_approval", "Pending"), f"Letter at {money(price)}" if financed else ""),
        ("Buyer docs", "Proof of funds for deposit, closing costs and appraisal gap" if financed else "Source-of-funds note if the account is new",
         CK.get("funds", "Pending"), f"At least {money(r['cash'][variant]['worst'])} available" if financed else ""),
        ("Buyer docs", "Homeowners insurance quote for this address", CK.get("insurance", "Yes" if BU.get("insurance_quote") else "Pending"), "Before submitting"),
        ("Disclosures", "Brokerage relationship disclosure signed (transaction broker / single agent)" if fl else "Agency disclosure signed",
         CK.get("agency", "Pending"), "Florida requirement" if fl else "Per your state's rules"),
        ("Disclosures", "Buyer-broker agreement signed; compensation request matches", CK.get("bb", "Pending"),
         f"{t['buyer_broker_pct']:.1%} requested from seller" if t.get("buyer_broker_pct") else "No compensation requested from seller"),
        ("Disclosures", "Wire-fraud advisory acknowledged by buyer", CK.get("wire", "Pending"), "Deposit wiring instructions only by phone from the escrow agent"),
    ]
    if yb and yb < 1978:
        package.append(("Disclosures", "Lead-based paint disclosure", CK.get("lead", "Pending"), f"Required: built {yb}"))
    package += [
        ("Timing", f"Inspector{' and 4-point' if fl else ''} booked inside the {t['inspection_days']}-day inspection period", CK.get("inspector", "Pending"), ""),
        ("Timing", f"Lender confirms a {(close - B['analysis_date']).days}-day close" if financed else "Funds available by closing",
         CK.get("lender_close", "Yes" if BU.get("lender_called") else "Pending"), f"Closing {close:%b %-d}"),
        ("Do not include", "Personal letter, photos or buyer background", "Yes", "Fair housing"),
    ]
    return {"variant": variant, "option": OPTION_LABEL[variant], "price": money(price), "frbar": frbar, "form_name": form_name, "form_why": form_why,
            "software": "Form Simplicity" if frbar else "your contract software",
            "rows": [{"para": a, "field": b, "entry": c, "note": d} for a, b, c, d in rows],
            "riders": [{"rider": a, "inputs": b, "why": c} for a, b, c in riders],
            "clauses": [{"title": a, "text": b} for a, b in clauses], "docs": docs,
            "package": [{"group": a, "item": b, "status": c, "note": d} for a, b, c, d in package],
            "blanks": sum(x.count("[") for x in [c for _, _, c, _ in rows] + [b for _, b, _ in riders])}


def result(r, variant=None):
    s = summary(r)
    B = r["B"]
    V, M = B["value"], B["market"]
    return {
        "ok": True, "property": B["property"].get("address") or "", "list_price": money(B["property"]["list_price"]),
        "value_range": f"{money(V['cma_low'])}–{money(V['cma_high'])}", "summary": s,
        "side_by_side": [{"term": labl, "values": [term_val(key, r["terms"][k], B) for k in r["O"]]} for key, labl in TERM_KEYS
                         if not (key == "escalation" and not any(r["terms"][k].get("escalation") for k in r["O"]))
                         and not (key in ("loan_approval_days", "appraisal_gap") and B["buyer"]["financing"] == "cash")],
        "market": {"sale_to_list": f"{M['sale_to_list'] * 100:.1f}%" if M.get("sale_to_list") else None,
                   "months_supply": M.get("months_supply"), "median_dom": M.get("median_dom"),
                   "median_adjusted": money(V["median_adjusted"]) if V.get("median_adjusted") else None, "read": B["competition"]["heat"]},
        "worksheet": worksheet(r, variant),
        "to_confirm": [a["why"] for a in r["missing"] if a["impact"] in ("high", "med")][:4],
        "assumptions": [{"impact": a["impact"], "where": a["scope"].title(), "what": a["why"]} for a in r["missing"]],
        "market_notes": list(r["costs"].notes),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("buyer")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--market", help="market profile (built in for Florida)")
    ap.add_argument("--option", choices=list(OPTION_LABEL), help="option for the worksheet (default: the file's chosen_option)")
    a = ap.parse_args(argv)
    try:
        with open(a.buyer, encoding="utf-8") as f:
            data = json.load(f)
        r = analyze(data, a.market, load_cma(data, a.cma))
        out = result(r, a.option)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
