"""Build the buyer's offer: a recommended offer inside the buyer's limits, up to two alternatives, outlook bands.

    python3 scripts/strategy.py buyer.json [--cma file.cma.json] [--option recommended|stronger|lower_cost]

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
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import contract_forms as cf, dates, finance, handoff, offer_engine as oe, profiles  # noqa: E402

money, rnd = oe.money, oe.rnd
COMP_LABEL = {0: "Only Offer", 1: "1 Competing Offer", 2: "2–3 Competing", 3: "Cash or 4+ Competing"}
# Competitiveness thresholds (strong / competitive / at risk) per competition level. Starting judgments.
BANDS = {0: (55, 40, 30), 1: (65, 55, 45), 2: (75, 60, 50), 3: (85, 72, 60)}
OPTION_LABEL = {"recommended": "Recommended", "stronger": "Stronger", "lower_cost": "Lower-Cost"}
# National planning estimates, used only when neither the buyer file nor the market has a number.
DEFAULT_RATE = 6.5
OFFER_QUESTIONS = ("contract_name", "escalation_accepted")  # OFR-222: shape the offer itself, so asked first in to_confirm
# OFR-239: a listing agent's highest-and-best call, as the agent words it in competition.note
HIGHEST_AND_BEST = re.compile(r"highest\s*(?:and|&)\s*best", re.I)
# OFR-327: a costs.rate_source that names the buyer's lender or a quote ("Lender quote") is the lender's rate, not a
# looked-up weekly average
TIGHT_SUPPLY_MONTHS = 3  # OFR-331: under this a price cut alone doesn't read soft
SOFT_SUPPLY_MONTHS = 6  # manual v5: over this the area's market reads soft (3 to 6 months reads balanced)
MIN_CONCESSION_ASK = 1000  # a smaller seller-concession ask isn't worth asking for: it drops to $0 or rounds up
LENDER_QUOTE = re.compile(r"lender|quot|loan officer|loan estimate|pre-?approv", re.I)
CONVENTIONAL_AVERAGE = re.compile(r"freddie|pmms", re.I)  # iteration 9 eval 1: the weekly survey is conventional loans


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
    K = B.setdefault("costs", {})
    s, v, mk = h.get("subject") or {}, h["value"], h.get("market") or {}
    B["_cma_address_note"] = oe.address_note(h, P.get("address"))  # CMA-102
    for key in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                "hoa_monthly", "hoa_frequency", "flood_zone", "dom", "price_cuts", "annual_tax"):  # OFR-335: the subject's DOM and cuts
        if s.get(key) not in (None, "") and P.get(key) in (None, ""):
            P[key] = s[key]
            if key == "dom":  # OFR-242: the handoff's days on market were counted on its as_of date, so age them
                B["_dom_aged"] = age_dom(P, s["dom"], h.get("as_of"), _d(B.get("analysis_date")) or date.today())
    # CMA-111: the tax the CMA computed for the buyer (millage and homestead), so both reports show the same payment
    if K.get("tax_rate") is None and K.get("total_mills") is None and s.get("total_mills") is not None:
        for key in ("school_mills", "total_mills", "homestead"):
            if s.get(key) is not None and K.get(key) is None:
                K[key] = s[key]
    # iteration 12: the premium the buyer CMA's payment used, so the two reports show the same insurance and payment at
    # the same price; the buyer file's own premium or rate wins. An older handoff without it: the estimate is figured at
    # the CMA's target price, the price its payment used, not at list
    if K.get("insurance_annual") is None and K.get("insurance_rate") is None:
        if isinstance(s.get("insurance_annual"), (int, float)):
            K["insurance_annual"] = s["insurance_annual"]
            B["_cma_insurance"] = {"annual": s["insurance_annual"], "price": s.get("insurance_price"),
                                   "estimated": s.get("insurance_estimated", True)}
        elif (h.get("offer_plan") or {}).get("opening") is not None:
            B["_insurance_price"] = target_price(h["offer_plan"])
    W = B.setdefault("worksheet", {})  # iteration 12: the property report's legal description and tax ID, for paragraph 1
    for key in ("legal_description", "parcel_id"):
        if s.get(key) and not W.get(key):
            W[key] = s[key]
    mp = h.get("market_profile") or {}
    if mp.get("state") and not P.get("state"):
        P["state"] = mp["state"]
    if mp.get("mls") and not P.get("mls"):  # OFR-211: the MLS the CMA was built from
        P["mls"] = mp["mls"]
    for key, val in (("cma_low", v["low"]), ("cma_high", v["high"]), ("midpoint", v["midpoint"]),
                     ("median_adjusted", v.get("median_adjusted")), ("source", cma_source(h))):
        if V.get(key) is None and val is not None:  # OFR-24: an explicit null in the file counts as missing
            V[key] = val
    B["_cma_side_note"] = oe.side_note(h, "buyer")
    for ours, theirs in (("sale_to_list", ("sale_to_list", "sale_to_list_recent", "sale_to_original_list_recent")),
                         ("median_dom", ("median_dom", "median_days_recent", "median_days")),
                         ("months_supply", ("months_supply",)),
                         ("share_with_seller_costs", ("share_with_seller_costs", "share_with_seller_paid_costs_recent")),
                         ("typical_seller_paid", ("typical_seller_paid", "median_seller_paid_recent"))):
        src = next((k for k in theirs if mk.get(k) is not None), None)
        val = mk[src] if src else None
        if val is not None and M.get(ours) is None:  # the CMA's raw numbers read like the buyer file's text ("44%", "$6,500")
            if src == "sale_to_original_list_recent":  # the ratio is against the original list price: labeled so
                M["sale_to_list_basis"] = "original"
            if ours == "share_with_seller_costs" and isinstance(val, (int, float)):
                val = f"{val * 100:.0f}%"
            elif ours == "typical_seller_paid" and isinstance(val, (int, float)):
                val = f"${val:,.0f}" if val else None
            M[ours] = val
    if h.get("offer_plan") and not B.get("cma_offer_plan"):
        B["cma_offer_plan"] = h["offer_plan"]
    return B


def target_price(op):
    """The CMA offer plan's target, as the buyer CMA figures its payment: the middle of target_low to target_high, else
    the one given, else the opening."""
    lo, hi = op.get("target_low"), op.get("target_high")
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    return lo if lo is not None else hi if hi is not None else op.get("opening")


def cma_source(h):
    """Where the value range came from: "buyer CMA, Sep 26, 2026" (the handoff's as_of in the report's date style)."""
    name = f"{h.get('side') or 'buyer'} CMA"
    try:
        d = _d(h.get("as_of"))
    except ValueError:
        d = None
    return f"{name}, {d:%b} {d.day}, {d.year}" if d else name


def age_dom(P, dom, as_of, today):
    """OFR-242: days on market from a CMA handoff, moved forward by the days since its as_of date. Sets P['dom'] and
    returns (the handoff's figure, its date, days added) when it moved, else None."""
    try:
        since = (today - _d(as_of)).days if as_of else 0
    except ValueError:
        return None
    if since <= 0 or not isinstance(dom, (int, float)):
        return None
    P["dom"] = dom + since
    return dom, _d(as_of), since


def prepare(B, A, market=None):
    """Defaults for everything missing, each one logged. Returns (B, costs)."""
    B = copy.deepcopy(B)
    today = _d(B.get("analysis_date")) or date.today()
    P, V, K = B.setdefault("property", {}), B.setdefault("value", {}), B.setdefault("costs", {})
    M, C, LS, BU = B.setdefault("market", {}), B.setdefault("competition", {}), B.setdefault("listing_side", {}), B.setdefault("buyer", {})
    if not P.get("list_price"):
        raise oe.OfferError("The list price is needed (property.list_price).")
    for D, key in ((M, "median_dom"), (P, "dom")):  # OFR-336: whole days, from a CMA handoff or the file ("23", never "23.0")
        if isinstance(D.get(key), float):
            D[key] = round(D[key])
    given_market = market
    city = city_of(P.get("address"))
    if market is None and not P.get("county") and city:  # OFR-213: the built-in tax districts name the city's county
        county = profiles.county_for_city(oe.state_of(P), city)
        if county:
            P["county"] = A.add("property", "county", county, f"County not given: {county} County, from the city ({city}). "
                                "Confirm it", "low")
    if market is None and P.get("mls"):  # OFR-211: the MLS from the buyer file or the CMA handoff
        market = profiles.load_market(state=oe.state_of(P), county=P.get("county"), mls=P["mls"])
    costs = oe.load_costs(P, market)
    if given_market is None and not oe.state_of(P):
        A.add("property", "state", None, "Property's state not given: no built-in costs or contract rules were used. "
              "Ask for the state", "high")
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
        # One rule with the buyer CMA (finance.buyer_closing_costs): the market's share plus prepaids, plus its loan
        # taxes on the loan (CORE-16); half the market's share for cash
        cash = fin == "cash"
        BU["closing_cost_pct"] = finance.buyer_closing_pct(costs, cash)
        B["loan_taxes"] = [] if cash else finance.loan_taxes(1, costs)
        src = costs.described("closing_costs.buyer_closing_cost_pct") + (", half for a cash purchase" if cash else " plus prepaids")
        if B["loan_taxes"]:
            src += ", plus " + " and ".join(f"{t['label'].lower()} ({t['rate'] * 100:g}% of the loan)" for t in B["loan_taxes"])
        A.add("buyer", "closing_cost_pct", BU["closing_cost_pct"],
              f"Closing costs estimated at {closing_cost_basis(B)} ({src}; the lender's Loan Estimate governs)", "low")
    BU["approval"] = BU.get("approval") or ("pof_verified" if fin == "cash" else "preapproval")
    BU["lender_min_close_days"] = BU.get("lender_min_close_days") or (21 if fin == "cash" else 35)
    BU.setdefault("agent_track", "average")
    B["payment_assumed"] = []  # OFR-228: the payment inputs that are estimates, named when the payment limit sets the price
    # OFR-241: the skill looks up the latest Freddie Mac weekly 30-year rate when the agent gives none (costs.rate with
    # costs.rate_source naming the week); the built-in rate is only the offline fallback, said in the assumptions
    if K.get("rate") is None:
        B["payment_assumed"].append(f"an assumed {DEFAULT_RATE:g}% rate")
    elif K.get("rate_source") and not LENDER_QUOTE.search(str(K["rate_source"])):  # OFR-327: a quote isn't assumed
        # iteration 9 eval 1: the Freddie Mac average is a conventional rate; an FHA, VA or USDA quote replaces it
        prog = fin.upper() if fin in ("fha", "va", "usda") and CONVENTIONAL_AVERAGE.search(str(K["rate_source"])) else None
        B["payment_assumed"].append(f"a {K['rate']:g}% rate ({K['rate_source']}" + (", a conventional-loan average)" if prog else ")"))
        A.add("costs", "rate_source", K["rate"], f"Interest rate: {K['rate']:g}%, the {K['rate_source']}, not a lender's "
              + (f"quote: it's a conventional-loan average, so the lender's {prog} rate quote replaces it" if prog else
                 "quote: use the buyer's quote when there is one"), "low")
    K["rate"] = oe.given(K, "rate", DEFAULT_RATE, A, "costs", f"Interest rate not given and not looked up: Assumed "
                         f"{DEFAULT_RATE:g}%, the offline fallback (use the lender's quote, else the latest Freddie Mac "
                         "weekly 30-year rate)", "low")
    if not 1 <= K["rate"] < 20:
        raise oe.OfferError(f"costs.rate is {K['rate']}: write the interest rate as a percent, 6.5 for 6.5%.")
    cma_ins = B.get("_cma_insurance")
    if K.get("insurance_annual") is not None and BU.get("insurance_quote") is None and not cma_ins:
        BU["insurance_quote"] = True  # OFR-217: a premium given for this address is a quote in hand
    if cma_ins and cma_ins["estimated"] and not quote_in_hand(BU):  # iteration 12: the buyer CMA's estimate, carried over
        at = f" at {money(cma_ins['price'])}" if cma_ins.get("price") else ""
        B["payment_assumed"].append(f"estimated {money(K['insurance_annual'])}/yr insurance")
        A.add("costs", "insurance_annual", K["insurance_annual"], f"Insurance not provided: {money(K['insurance_annual'])}/yr, "
              f"the buyer CMA's estimate{at}, so both reports use the same premium. Get a quote for this address", "low")
    elif K.get("insurance_annual") is None:
        yb = P.get("year_built")
        basis = B.get("_insurance_price") or lp  # iteration 12: an older CMA handoff's target price, as its payment used
        est = finance.insurance_estimate(basis, costs, yb, K.get("insurance_rate"))
        src = ("your rate for this home" if est["source"] == "agent" else
               costs.described("buyer_costs.insurance_rate") if est["source"] == "market" else "national planning estimate")
        K["insurance_annual"] = est["annual"]
        B["payment_assumed"].append(f"estimated {money(K['insurance_annual'])}/yr insurance")
        A.add("costs", "insurance_annual", K["insurance_annual"], f"Insurance not provided: estimated at {money(K['insurance_annual'])}/yr "
              f"({src}" + (f", x{est['age_factor']:g} for a {yb} home" if est["age_factor"] > 1 else "")
              + (f", at the buyer CMA's {money(basis)} target price" if basis != lp else "") + "). Get a quote "
              "for this address", "low")
    elif not quote_in_hand(BU):  # OFR-328: a premium typed in with no quote in hand (false or planned) is an estimate
        B["payment_assumed"].append(f"estimated {money(K['insurance_annual'])}/yr insurance")
        A.add("costs", "insurance_annual", K["insurance_annual"], f"Insurance: {money(K['insurance_annual'])}/yr is an "
              "estimate, not a quote for this address: get a quote", "low")
    P["hoa_monthly"] = P.get("hoa_monthly") or 0
    # OFR-26, CMA-6: flood insurance and CDD assessments are payment lines; a missing amount is left out and flagged, never 0
    B["flood"] = finance.flood_insurance(P.get("flood_zone"), K.get("flood_insurance_annual"), costs, today,
                                         condo_unit=finance.property_type(P.get("type")) == "condo")
    if B["flood"]["annual"] is None:
        A.add("costs", "flood_insurance_annual", "not included", "No flood insurance quote: the payment leaves it out. "
              + B["flood"]["note"].replace(" Get a quote; the total leaves it out until then.", ""),
              "med" if B["flood"]["required"] in ("lender", "citizens") else "low")
    if P.get("cdd") and P.get("cdd_annual") is None:
        A.add("property", "cdd_annual", "not included", "The property is in a CDD but the yearly assessment wasn't given: the "
              "payment leaves it out (it's on the tax bill as a non-ad valorem assessment)", "med")
    why_no_millage = find_millage(B, costs, A)
    tax = property_tax(B, costs, lp)
    if tax["annual"] is None:
        A.add("costs", "property_tax", "not included", "No millage or tax rate for this market: the payment leaves out property tax",
              "high" if BU.get("max_payment") else "med")
    elif tax["estimated"]:
        A.add("costs", "property_tax", tax["basis"], f"No millage given: property tax estimated at {tax['basis'].removeprefix('about ')} "
              f"({costs.described('property_tax.fallback_rate')})" + (f". {why_no_millage}" if why_no_millage else ""), "low")
    elif P.get("annual_tax") in (None, ""):
        # OFR-201: the seller's proration uses the same rate as the buyer's payment, never a second (fallback) rate
        B["seller_annual_tax"] = round(tax["annual"])
        # OFR-243: an estimate from the buyer's rate at the list price, labeled so on the net sheet, not the seller's bill
        A.add("property", "annual_tax", B["seller_annual_tax"], f"Seller's tax bill not given: the seller's proration is "
              f"an estimate, the buyer's tax rate ({tax['basis']}) applied to the list price ({money(B['seller_annual_tax'])}/yr), "
              "not the seller's actual bill, which can differ (another exemption or assessed value). Get the bill: the "
              "proration moves the seller's net", "med")
    if K.get("tax_rate") is None and tax["annual"] is not None and K.get("homestead") is None:  # OFR-124
        A.add("costs", "homestead", True, "Property tax assumes the buyer files for the homestead exemption (a primary "
              "residence). For a second home or rental the tax is higher: say so", "low")
    elif K.get("tax_rate") is not None:  # OFR-237: a given rate is used as is; no exemption is taken off it
        A.add("costs", "homestead", "as given", f"Property tax uses the given {K['tax_rate'] * 100:g}% rate as is: the payment "
              "assumes no homestead exemption unless that rate already includes one", "low")

    lvl = C.get("level")
    heat, basis = market_heat(P, M)
    if lvl is None:
        lvl = {"hot": 2, "normal": 1, "soft": 0, "stale": 0}[heat]
        signals = P.get("dom") is not None or M.get("sale_to_list") or P.get("price_cuts")
        A.add("competition", "level", COMP_LABEL[lvl],
              (f"Competition unknown: inferred '{COMP_LABEL[lvl].lower()}' from market signals ({heat_words(heat, basis)})" if signals else
               f"Competition unknown and no market data: assumed '{COMP_LABEL[lvl].lower()}' (typical)") + ". Ask the listing agent", "med")
    C["level"], C["heat"], C["heat_basis"] = lvl, heat, basis
    LS["buyer_broker_offered_pct"] = LS.get("buyer_broker_offered_pct")
    LS["listing_fee_pct"] = LS.get("listing_fee_pct")
    B["analysis_date"] = today
    weekday_deadlines(B, today, A)  # OFR-244: "Friday 5 PM" to a date, before any date counts from it
    B["effective_date"] = effective_date(B, today, A)  # OFR-123: dates count from the expected acceptance
    # One contract form for the options, the listing-side scoring and the worksheet: AS IS and Standard math never mix.
    W = B.get("worksheet") or {}
    try:
        form = cf.normalize(W.get("contract_form") or BU.get("contract_form"))
    except cf.FormError as e:
        raise oe.OfferError(str(e)) from e
    if form is None:  # ENG-12: a missing form is a high-impact assumption (CLAUDE.md); OFR-126: plain words
        form = A.add("buyer", "contract_form", cf.AS_IS,
                     "Contract form not chosen: planned on the FAR/BAR AS IS, the usual form for a competitive offer. If the "
                     "buyer will use the Standard form, say so: its repair limits and inspection rules change the numbers",
                     "high") \
            if cf.farbar_market(costs.get("contract.forms")) else cf.OTHER
    B["contract_form"] = form
    B["words"] = cf.term_words(form)  # OFR-234: FAR/BAR's names on FAR/BAR, generic ones on any other contract
    B["repair_limits"] = W.get("repair_limits") or BU.get("repair_limits")
    # Buyer's broker pay requested from the seller, and how it's paid on a FAR/BAR offer: Rider GG (a separate
    # compensation agreement, the default) or Rider FF (a seller credit to the buyer, which uses the loan program's
    # concession room). contract_forms.buyer_broker_as_credit is the rule.
    B["bb_request"] = bb_request(B, costs)
    route = str(W.get("buyer_broker_form") or BU.get("buyer_broker_form") or "GG").upper()
    B["buyer_broker_form"] = route if form in cf.FARBAR and B["bb_request"][0] else None
    if BU.get("needs_sale") and not BU.get("sale_contingency_days"):
        A.add("buyer", "sale_contingency_days", 21, "Buyer needs to sell first, no sale deadline given: planned on 21 days with a "
              "kick-out clause. Set the date the buyer's sale can close", "med")
    if BU.get("buyer_broker_agreement_pct") is None:
        A.add("buyer", "buyer_broker_agreement_pct", "not given",
              "Buyer-broker agreement not given: cash to close leaves out any fee the seller doesn't pay. Enter the "
              "agreement's rate so the shortfall is counted", "med")
    return B, costs


def stl_label(M):
    """The sale-price ratio's name, as the number is measured: against the original list price (a buyer CMA's
    figure) or the list price at sale."""
    return "Sale to Original List" if M.get("sale_to_list_basis") == "original" else "Sale to List"


def tight_supply(M):
    sup = M.get("months_supply")
    return isinstance(sup, (int, float)) and not isinstance(sup, bool) and sup < TIGHT_SUPPLY_MONTHS


def market_heat(P, M):
    """OFR-226: (heat, the signals that decide it, in plain words), for inferring the competition. Hot when days on market
    are under half the median or the sale-price ratio is 99%+; soft when days on market are over 1.5x the median or the
    price was cut (soft wins). With under 3 months of supply the market isn't soft (manual v5): a cut reads normal
    (OFR-331), and long days on market read "stale", this listing's own read (no competition on it, like soft), never
    the market's. The words name only the deciding signals ("78 days on market vs. a 23-day median"); market_read()
    gives the whole picture for the Market Check."""
    dom, med, stl = P.get("dom"), M.get("median_dom"), M.get("sale_to_list")
    tight = tight_supply(M)
    reads = []  # (the signal in words, what it reads)
    if dom is not None and med:
        reads.append((f"{dom} days on market vs. a {med}-day median",
                      "hot" if dom < 0.5 * med else ("stale" if tight else "soft") if dom > 1.5 * med else "normal"))
    if stl:
        reads.append((f"sales at {stl * 100:.1f}% of {'original ' if M.get('sale_to_list_basis') == 'original' else ''}list price",
                      "hot" if stl >= 0.99 else "normal"))
    if P.get("price_cuts"):
        # OFR-331: with under 3 months of supply a cut says this listing was priced high, not that the market is soft
        reads.append((cuts_words(P["price_cuts"]), "normal" if tight else "soft"))
    got = {rd for _, rd in reads}
    heat = next((h for h in ("soft", "stale", "hot") if h in got), "normal")
    if not reads:
        return heat, "no market data"
    return heat, " and ".join(sig for sig, rd in reads if rd == heat)


def heat_words(heat, basis):
    """The inferred read in words: "market reads soft (…)", or for a stale listing in a tight market "this home reads
    stale (…)", so a tight market is never called soft."""
    return f"{'this home' if heat == 'stale' else 'market'} reads {heat} ({basis})"


def area_read(M):
    """Manual v5: the area's market on its own (tight, balanced, soft, hot), from the months of supply the CMA measured,
    else a 99%+ sale-price ratio (hot); None with neither."""
    sup = M.get("months_supply")
    if isinstance(sup, (int, float)) and not isinstance(sup, bool):
        return "tight" if sup < TIGHT_SUPPLY_MONTHS else "soft" if sup > SOFT_SUPPLY_MONTHS else "balanced"
    return "hot" if M.get("sale_to_list") and M["sale_to_list"] >= 0.99 else None


def listing_read(P, M):
    """Manual v5: this listing on its own: "stale" (days on market over 1.5x the median, or a price cut), "fast"
    (under half the median), "on pace", or None with no days on market or cuts."""
    dom, med = P.get("dom"), M.get("median_dom")
    if (dom is not None and med and dom > 1.5 * med) or P.get("price_cuts"):
        return "stale"
    if dom is not None and med:
        return "fast" if dom < 0.5 * med else "on pace"
    return None


def cuts_words(n):
    return f"{n} price cut{'s' if n != 1 else ''}" if isinstance(n, int) and not isinstance(n, bool) else "a price cut"


LISTING_WORDS = {"stale": "stale", "fast": "moving fast", "on pace": "on pace"}


def market_read(B):
    """The Market Check's Market Read as (value, note). Manual v5: the market and this listing are read apart, so a stale
    listing never makes a tight market read soft: "Tight market, stale listing" with one plain sentence, the market
    first (months of supply, the sale-price ratio), then this home (days on market, price cuts) and, when they
    disagree, where the leverage is."""
    P, M = B["property"], B["market"]
    area, home = area_read(M), listing_read(P, M)
    area_sig = []
    if isinstance(M.get("months_supply"), (int, float)):
        area_sig.append(f"{M['months_supply']:g} months of supply")
    if M.get("sale_to_list"):
        area_sig.append(f"sales at {M['sale_to_list'] * 100:.1f}% of "
                        f"{'original ' if M.get('sale_to_list_basis') == 'original' else ''}list price")
    home_sig = []
    if P.get("dom") is not None and M.get("median_dom"):
        home_sig.append(f"{P['dom']} days on market vs. a {M['median_dom']}-day median")
    if P.get("price_cuts"):
        home_sig.append(cuts_words(P["price_cuts"]))
    parts = []
    if area:
        parts.append(f"market {area}" + (f" ({', '.join(area_sig)})" if area_sig else ""))
    elif area_sig:
        parts.append(f"nearby {' and '.join(area_sig)}")
    if home:
        parts.append(f"this home {LISTING_WORDS[home]}" + (f" ({', '.join(home_sig)})" if home_sig else ""))
    if not parts:
        return "—", None
    note = "; ".join(parts)
    if area in ("tight", "hot") and home == "stale":
        note += ", so the leverage comes from this home's price, not the market"
    elif area == "soft" and home == "stale":
        note += ", so the market and this home both favor the buyer"
    elif area in ("tight", "hot") and home == "fast":
        note += ", so expect competition"
    note = note[:1].upper() + note[1:] + "."
    value = ", ".join(w for w in ((f"{area} market" if area else None),
                                  (f"{'stale' if home == 'stale' else 'fast-moving' if home == 'fast' else 'on-pace'} listing"
                                   if home else None)) if w)
    return (value[:1].upper() + value[1:]) if value else "—", note


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def deadline_date(text, today):
    """The date in an offer deadline as the listing agent gave it ("2026-09-25 17:00", "Fri Sep 25 · 5 PM"), or None."""
    s = str(text or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", s, re.I)
    if not m:
        return None
    try:
        d = date(today.year, _MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None
    return d if d >= today - timedelta(days=31) else date(today.year + 1, d.month, d.day)  # a January deadline in December


_WEEKDAY = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)(?:day|s|sday|nesday|rsday|urday|r|rs)?\b\.?", re.I)
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\b\.?", re.I)


def weekday_date(text, today):
    """OFR-244: a deadline given only as a weekday ("Friday 5pm", "Fri 6 PM") as (date, (hour, minute) or None): the
    next such day from `today` (today counts). None when the text has a full date, or no weekday."""
    s = str(text or "")
    if deadline_date(s, today) or not _WEEKDAY.search(s):
        return None
    wd = _WEEKDAYS.index(_WEEKDAY.search(s).group(1).lower())
    d = today + timedelta(days=(wd - today.weekday()) % 7)
    m = _TIME.search(s)
    if m:
        return d, (int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0), int(m.group(2) or 0))
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", s)  # "Friday 17:00"
    return d, ((int(m.group(1)), int(m.group(2))) if m else None)


def weekday_deadlines(B, today, A):
    """OFR-244: a weekday-only offer deadline or Time for Acceptance becomes "YYYY-MM-DD HH:MM". When the day it resolves
    to is more than 5 days out (so today is the day after that weekday), the agent may have meant the one just passed:
    the resolved date is recorded as an assumption to confirm."""
    for scope, holder, key, name in (("competition", B.get("competition") or {}, "deadline", "Offer deadline"),
                                     ("worksheet", B.get("worksheet") or {}, "acceptance_deadline", "Time for Acceptance")):
        hit = weekday_date(holder.get(key), today)
        if not hit:
            continue
        (d, t), given_ = hit, holder[key]
        holder[key] = f"{d}" + (f" {t[0]:02d}:{t[1]:02d}" if t else "")
        ahead = (d - today).days
        if ahead > 5:
            last = d - timedelta(days=7)
            A.add(scope, "deadline", holder[key], f"{name} \"{given_}\" read as {d:%a %b} {d.day}, {ahead} days out. If the "
                  f"listing agent meant {last:%a %b} {last.day}, it has already passed: confirm the date", "med")


_ISO_WHEN = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}):(\d{2}))?")


def _clock(h, m, full=False):
    """18, 0 -> '6 PM' ('6:00 PM' when `full`); 17, 30 -> '5:30 PM'."""
    return f"{(h % 12) or 12}" + (f":{m:02d}" if m or full else "") + (" PM" if h >= 12 else " AM")


def deadline_label(text, long=False):
    """OFR-202: a deadline given as "2026-10-02 18:00" in the report's words: "Fri Oct 2 · 6 PM", or with `long`
    "October 2, 2026, 6:00 PM" (the worksheet's Time for Acceptance). Any other text prints as given."""
    s = str(text or "").strip()
    m = _ISO_WHEN.fullmatch(s)
    if not m:
        return s
    d = date.fromisoformat(m.group(1))
    t = (int(m.group(2)), int(m.group(3))) if m.group(2) else None
    if long:
        return f"{d:%B} {d.day}, {d.year}" + (f", {_clock(*t, full=True)}" if t else "")
    return f"{d:%a %b} {d.day}" + (f" · {_clock(*t)}" if t else "")


def effective_date(B, today, A):
    """OFR-123: the expected Effective Date the closing and deposit dates count from: `expected_effective_date`, else the
    day after the offer deadline, else the day after the analysis date (recorded as an assumption)."""
    given_ = B.get("expected_effective_date")
    if given_:
        return _d(given_)
    due = deadline_date((B.get("worksheet") or {}).get("acceptance_deadline") or (B.get("competition") or {}).get("deadline"), today)
    eff = (due or today) + timedelta(days=1)
    # manual v5: the worksheet's Time for Acceptance is a business day at 5:00 PM, so the dates count from that same day,
    # never from a weekend or holiday before it
    moved = not dates.is_business_day(eff)
    if moved:
        eff = dates.next_business_day(eff)
    after = "the offer deadline" if due else "today"
    A.add("buyer", "expected_effective_date", str(eff), f"Expected acceptance not given: dates count from {eff:%a %b} {eff.day}, "
          + (f"the first business day after {after}" if moved else f"the day after {after}") + ". Give the expected "
          "acceptance date if it's different", "low")
    return eff


def city_of(address):
    """The city in a one-line address ("…, Casselberry, FL 32707" -> "Casselberry"), or None."""
    parts = [x.strip() for x in str(address or "").split(",")]
    return (parts[-2] or None) if len(parts) >= 3 else None


def find_millage(B, costs, A):
    """OFR-124: the built-in millage for the property's taxing district, as the CMA skills do: `costs.district` (a name
    or the appraiser's tax-area code), else the address's city. Returns why no district was used (it goes in the
    fallback rate's assumption), or None."""
    K, P = B["costs"], B["property"]
    if K.get("tax_rate") is not None or K.get("total_mills") is not None:
        return None
    district = K.get("district")
    by_city = not district
    district = district or city_of(P.get("address"))
    if not district or not costs.get("property_tax.millage"):
        return None
    if not P.get("county"):  # OFR-213: prepare() fills the county from the city when a built-in district names it
        return f"The county wasn't given and {district} isn't a built-in tax district, so no millage was matched: give the county"
    rows = finance.millage(costs, county=P["county"], district=district)
    if not rows:
        return f"{district} isn't a built-in tax district in {P['county']} County: give the tax area from the property record"
    names = [str(r.get("district")) for r in rows]
    if len({n.split(" (")[0] for n in names}) > 1:  # different places: never a guess
        return finance.millage_row(costs, P["county"], district)[1]
    # One place in several districts (Orlando spans two water-management districts): the higher millage, so the payment
    # isn't understated, flagged with both names
    row = max(rows, key=lambda x: x["total"])
    K["school_mills"], K["total_mills"] = row["school"], row["total"]
    A.add("costs", "total_mills", row["total"], f"Millage from the built-in {row['district']} district ({row.get('year', '')} "
          "rates)" + (" by the address's city: confirm the parcel is inside city limits, or give the tax area from the "
                      "property record" if by_city else "")
          + (f". {district} spans {len(rows)} built-in districts, {' and '.join(names)}: the higher one was used"
             if len(rows) > 1 else ""),
          "med" if by_city or len(rows) > 1 else "low")
    return None


# --- money for the buyer -----------------------------------------------------

def closing_cost_basis(B):
    """OFR-215: how the closing costs are figured, in words that match the math ("3.0% of price plus loan taxes")."""
    return f"{B['buyer']['closing_cost_pct']:.1%} of price" + (" plus loan taxes" if B.get("loan_taxes") else "")


def quote_in_hand(BU):
    """An insurance quote the buyer has (True, or a premium in costs.insurance_annual: OFR-217); "planned" isn't one."""
    q = BU.get("insurance_quote")
    return bool(q) and q != "planned"


def closing_costs(B, price):
    """The buyer's closing costs at `price`, by the shared rule (finance.buyer_closing_costs): the share of price, plus
    the market's loan taxes when that share is the market's own (a given share already includes them)."""
    BU = B["buyer"]
    loan = finance.loan_amount(price, BU["financing"], BU["down_pct"], bool(BU.get("va_later_use")), bool(BU.get("va_exempt")))
    rates = B.get("loan_taxes") or []
    return round(price * BU["closing_cost_pct"] + sum(round(loan * t["rate"]) for t in rates))


def buyer_cash(B, t):
    BU, fin = B["buyer"], B["buyer"]["financing"]
    down = round(t["price"] * BU["down_pct"])
    cc = closing_costs(B, t["price"])
    conc = min(t.get("seller_concessions", 0), cc)
    # CMA-4: what the buyer's own broker agreement charges beyond what the seller pays is the buyer's cost
    bb_short = finance.buyer_broker_shortfall(t["price"], BU.get("buyer_broker_agreement_pct"), t.get("buyer_broker_pct")) or 0
    to_close = down + cc - conc + bb_short
    gap = t.get("appraisal_gap", 0) if fin != "cash" else 0
    worst = to_close + gap
    return {"down": down, "cc": cc, "conc": -conc, "bb_short": bb_short, "to_close": to_close, "gap": gap, "worst": worst,
            "reserve": BU["cash_available"] - worst, "wasted_conc": max(0, t.get("seller_concessions", 0) - cc)}


def property_tax(B, costs, price):
    """The buyer's tax at `price`: a plain `costs.tax_rate` (share of price) when given, else millage or the market's rate."""
    K = B["costs"]
    if K.get("tax_rate") is not None:
        return {"annual": price * K["tax_rate"], "basis": f"{K['tax_rate'] * 100:g}% of price", "estimated": False}
    return finance.property_tax(price, costs, school_mills=K.get("school_mills"), total_mills=K.get("total_mills"),
                                homestead=K.get("homestead", True))


def monthly_payment(B, costs, price):
    BU, K, P = B["buyer"], B["costs"], B["property"]
    tax = property_tax(B, costs, price)["annual"] or 0
    p = finance.monthly_payment(price, BU["financing"], BU["down_pct"], K["rate"], tax, K["insurance_annual"],
                                P["hoa_monthly"] + (P.get("cdd_annual") or 0) / 12, flood_annual=B["flood"]["annual"],
                                va_later_use=bool(BU.get("va_later_use")), va_exempt=bool(BU.get("va_exempt")))
    return round(p["total"])


def bb_as_credit(B):
    """True when the buyer's broker is paid as a seller credit (Rider FF): contract_forms decides (ENG-11)."""
    return cf.buyer_broker_as_credit(B.get("contract_form"), {"buyer_broker_form": B.get("buyer_broker_form")})


def concession_cap(B, price):
    """What the loan program lets the seller pay toward the buyer's costs. A buyer's broker credit under Rider FF uses the
    same room, so it comes off the top (contract_forms.buyer_broker_as_credit)."""
    cap = (finance.concession_cap(B["buyer"]["financing"], B["buyer"]["down_pct"]) or 0) * price
    if bb_as_credit(B):
        cap = max(0, cap - (B.get("bb_request") or (0,))[0] * price)
    return cap


def bb_request(B, costs):
    """(share of price, why) the buyer asks the seller to pay toward the buyer's broker."""
    LS, BU = B["listing_side"], B["buyer"]
    if LS.get("buyer_broker_offered_pct") is not None:
        return LS["buyer_broker_offered_pct"], "What the seller is offering"
    if BU.get("buyer_broker_agreement_pct") is not None:
        return BU["buyer_broker_agreement_pct"], "Per your buyer-broker agreement (confirm with listing agent)"
    if costs.get("brokerage.buyer_broker_fee_pct") is not None:
        pct_ = costs.get("brokerage.buyer_broker_fee_pct")
        return pct_, f"The default {pct_ * 100:g}% (5% total); your buyer-broker agreement sets it"
    return 0, "Not known for this market: none requested from the seller; set it from your buyer-broker agreement"


# --- engine bridge -------------------------------------------------------------

def engine_data(B, variants):
    P, V, LS, BU = B["property"], B["value"], B["listing_side"], B["buyer"]
    listing = {k: P.get(k) for k in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                                     "hoa_monthly", "flood_zone", "annual_tax", "costs")}
    listing["property_type"] = P.get("type")  # CMA-5: the engine's condo checks
    if listing.get("annual_tax") in (None, "") and B.get("seller_annual_tax"):
        listing["annual_tax"] = B["seller_annual_tax"]  # OFR-201: one tax rate for the payment and the proration
    if not V.get("assumed"):  # without a value range the engine measures appraisal risk against list price
        listing.update(cma_low=V["cma_low"], cma_high=V["cma_high"], cma_mid=V["mid"])
    seller = {"listing_fee_pct": LS["listing_fee_pct"], "offered_buyer_broker_pct": LS["buyer_broker_offered_pct"]}
    if P.get("seller_deadline"):
        seller["deadline"] = P["seller_deadline"]
    offers = []
    for vid, t in variants:
        o = {"id": vid, "price": t["price"], "financing": BU["financing"], "down_pct": BU["down_pct"], "approval": BU["approval"],
             "lender_called": BU.get("lender_called", False), "insurance_quote": t.get("insurance_quote", BU.get("insurance_quote")),
             "agent_track": BU.get("agent_track"), "buyer": "Buyer",
             "same_buyer": "buyer"}  # OFR-101: the options are one buyer's alternatives, never each other's competition
        for k in ("deposit", "seller_concessions", "buyer_broker_pct", "home_warranty", "inspection_days", "loan_approval_days",
                  "appraisal_gap", "closing_days", "sale_contingency_days", "kickout", "escalation", "contract_form"):
            if t.get(k) is not None:
                o[k] = t[k]
        if B.get("repair_limits"):
            o["repair_limits"] = B["repair_limits"]
        fin = BU["financing"]
        riders = [B["buyer_broker_form"]] if B.get("buyer_broker_form") and t.get("buyer_broker_pct") else []
        kind = appraisal_kind(B, t)
        if kind == "aga":
            o["appraisal_form"] = "aga"
            o["aga_valuation_days"] = aga_valuation(t, fin)
        elif kind == "F":
            riders.append("F")
        elif fin != "cash":
            o["appraisal_contingency"] = t.get("appraisal_days", 21)
        if riders:
            o["riders"] = riders
        offers.append(o)
    # OFR-123: the engine counts closing and "days until firm" from the expected Effective Date
    return {"analysis_date": str(B["effective_date"]), "listing": listing, "seller": seller, "offers": offers}


def appraisal_kind(B, t):
    """How a FAR/BAR option protects the appraisal: 'aga' (a gap offer on the Appraisal Gap Addendum, only where AGA-1
    fits the loan: contract_forms.aga_fits), 'F' (the Appraisal Contingency Rider, conventional or USDA), or None
    (FHA/VA's own rider, cash, or another contract). ENG-10: a USDA gap is written in Additional Terms with Rider F."""
    fin = B["buyer"]["financing"]
    if B["contract_form"] not in cf.FARBAR:
        return None
    if t.get("appraisal_gap") and cf.aga_fits(fin):
        return "aga"
    return "F" if fin in ("conventional", "usda") else None


def aga_valuation(t, fin):
    """OFR-106: AGA-1's valuation blank, filled so its whole window ends with the Loan Approval Period (financed) or by
    closing (cash)."""
    limit = t.get("loan_approval_days") if fin != "cash" else t.get("closing_days")
    return cf.aga_valuation_days(limit or cf.AGA_VALUATION_DAYS + cf.AGA_DELIVERY_DAYS + cf.AGA_RENEGOTIATE_DAYS)


def run_engine(B, costs, variants):
    # OFR-243: with no seller's bill the proration is an estimate: the engine's assumption (annual_tax) says so once, in
    # the assumptions, never on the net sheet's line (local-costs.md)
    R = oe.analyze(engine_data(B, variants), market=costs.market)
    return R, {o["id"]: o for o in R["offers"]}


def ci(o, target_net, lp):
    """Competitiveness index = strength score + 5 points per 1% of list price the seller nets above a clean offer at list."""
    return o["score"]["total"] + 5 * (o["ns"]["net_adj"] - target_net) / (0.01 * lp)


def band_of(v, level):
    s, c, r = BANDS[level]
    return ("strong", "Strong") if v >= s else ("comp", "Competitive") if v >= c else ("risk", "At Risk") if v >= r else ("unl", "Unlikely")


# --- offer builder -------------------------------------------------------------

def build_offer(B, costs):
    """Rule-based best offer inside the buyer's limits (references/offer-rules.md). Returns (terms, reasons)."""
    P, V, BU, C, LS = B["property"], B["value"], B["buyer"], B["competition"], B["listing_side"]
    lp, lvl, fin = P["list_price"], C["level"], BU["financing"]
    why = {}
    anchor = min(lp, V["point"])
    # OFR-7: with little competition the offer never goes above list, even when the value range starts above it
    price = {0: min(lp, max(V["cma_low"], anchor * 0.98)), 1: anchor, 2: min(max(lp, V["mid"]), V["cma_high"]),
             3: V["cma_high"]}[lvl]
    why["price"] = {0: "Room to negotiate: little competition", 1: "At value, not above it",
                    2: "At list, inside the value range, to compete", 3: "Top of the value range to compete"}[lvl]
    if lvl == 0 and V["cma_low"] > lp:
        why["price"] = "At list: the value range starts above it, and with little competition there's no reason to pay more"
    low_down = fin in ("fha", "va", "usda") or (fin == "conventional" and BU["down_pct"] < 0.05)
    if low_down and lvl >= 2 and price > V["mid"]:  # OFR-10: low down payment competes on terms, not price
        price = rnd(V["mid"], 1000, "down")
        why["price"] = (f"Value midpoint: with {BU['down_pct']:.1%} down the appraisal sets the loan, so this offer competes "
                        "on terms (deposit, inspection, closing date) rather than price")
    if price > BU["max_price"]:
        price, why["price"] = BU["max_price"], "Capped at your max price"
    price = lp if abs(price - lp) < 1000 and not (low_down and lvl >= 2 and lp > V["mid"]) \
        else rnd(price, 1000, "down" if price > lp else "round")
    if V.get("assumed") and price == lp:  # OFR-212: with no CMA the price stays at list, never called "at value"
        why["price"] = "At list: no value range yet, so list stands in for value (a buyer CMA would test it)"
    if BU.get("max_payment") and monthly_payment(B, costs, price) > BU["max_payment"]:
        while price > 1000 and monthly_payment(B, costs, price) > BU["max_payment"]:
            price -= 1000
        est = B.get("payment_assumed") or []  # OFR-228: a cap that rests on an assumed rate or insurance says so
        why["price"] = (f"Capped so the payment stays under ${BU['max_payment']:,}/mo" + (f" at {' and '.join(est)}" if est else "")
                        + (" (below the value range)" if price < V["cma_low"] else ""))
    t = {"price": price}
    cc = closing_costs(B, price)
    down = round(price * BU["down_pct"])
    spare = BU["cash_available"] - BU["reserve_floor"] - down - cc
    cap = concession_cap(B, price)
    need = max(0, -spare)
    want = {0: cc, 1: max(need, cc * 0.5), 2: need, 3: need}[lvl]
    conc = min(rnd(min(cap, want), 500, "up"), int(cc // 100 * 100), int(cap // 100 * 100)) if want > 0 else 0
    conc = meaningful_ask(B, costs, t, conc)
    t["seller_concessions"] = conc
    why["seller_concessions"] = ("Covers your closing costs; sellers here often pay them" if lvl == 0 else
                                 "About half your closing costs: a modest ask with one other offer" if lvl == 1 and conc > need else
                                 "Only what your cash can't cover" if conc else "None needed: keeps the offer clean")
    if need > cap:
        why["seller_concessions"] += f" (program cap {money(round(cap))} reached)"
    spare_after = BU["cash_available"] - BU["reserve_floor"] - (down + cc - min(conc, cc))
    line = V["cma_high"]  # appraisal risk starts at the top of the value range, as on the listing side (oe.appraisal_line)
    gap = 0
    if fin != "cash" and price > line:
        gap = min(rnd(price - line, 1000, "up"), max(0, rnd(spare_after, 500, "down")))
    t["appraisal_gap"] = gap
    if fin == "cash":
        why["appraisal_gap"] = "Cash: no appraisal contingency"
    elif V.get("assumed") and not gap:  # OFR-212: with no value range the gap can't be sized, so it's a question for the buyer
        why["appraisal_gap"] = ("Unknown without a value range: ask the buyer how much of a low appraisal they could "
                                "cover in cash")
    elif price < V["cma_low"]:  # iteration 9 eval 1: a price under the range isn't "inside" it
        why["appraisal_gap"] = "Not needed: price is below the value range"
    elif price <= line:
        why["appraisal_gap"] = "Not needed: price is inside the value range"
    elif gap >= price - line:
        why["appraisal_gap"] = "Covers the price above the value range"
    elif gap:
        why["appraisal_gap"] = "As much as your reserve allows"
    else:
        why["appraisal_gap"] = f"No room: your cash after the {money(BU['reserve_floor'])} reserve is fully used"
    if gap and fin in ("fha", "va"):
        why["appraisal_gap"] += ("; the FHA/VA rider still lets you walk if the appraisal is low, so the clause shows intent: "
                                 "send proof of funds with it")
    dep_pct = {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.03}[lvl] if fin != "cash" else {0: 0.03, 1: 0.05, 2: 0.10, 3: 0.10}[lvl]
    t["deposit"] = int(min(rnd(price * dep_pct, 500, "up"), max(1000, down + cc - conc)))
    why["deposit"] = f"{dep_pct:.0%} shows commitment; {B['words']['deposit_refund']}; counts toward cash to close"
    yb = P.get("year_built")
    old = yb is None or (B["analysis_date"].year - yb) > 25  # unknown age: allow the full window
    t["inspection_days"] = 7 if (lvl >= 2 and not old) else 10
    reports = " + 4-point" if costs.state == "FL" else ""
    why["inspection_days"] = (f"Room for a full inspection{reports}" + (" on an older home" if yb and old else " (year built unknown)" if not yb else "")
                              if t["inspection_days"] == 10 else "Short window to compete; newer home")
    if B["contract_form"] not in cf.FARBAR:  # OFR-315: no other state's periods are built in, so the length is assumed
        why["inspection_days"] += "; a generic default: confirm what's usual locally for this contract"
    if fin != "cash":
        t["loan_approval_days"] = 21 if (fin == "conventional" and lvl >= 2) else 30
        why["loan_approval_days"] = "Lender standard" if t["loan_approval_days"] == 30 else "Faster approval to compete"
        t["appraisal_days"] = 21
    t["closing_days"] = BU["lender_min_close_days"] + (0 if lvl >= 1 else 10)
    while not dates.is_business_day(B["effective_date"] + timedelta(days=t["closing_days"])):
        t["closing_days"] += 1  # OFR-219: a business day (no weekend or federal holiday), never before the lender's minimum
    why["closing_days"] = ("Quick close; no lender to wait on" if fin == "cash" else "Fastest your lender can reliably close") \
        if lvl >= 1 else "Comfortable timeline"
    t["home_warranty"] = 0
    why["home_warranty"] = "Not asked of the seller; keeps the net clean"
    t["buyer_broker_pct"], why["buyer_broker_pct"] = B["bb_request"]
    if bb_as_credit(B):
        why["buyer_broker_pct"] += "; paid as a credit (Rider FF), which counts toward the loan's concession limit"
    if BU.get("needs_sale"):  # Rider V with a kick-out (Rider X): the listing side scores it that way too
        t["sale_contingency_days"], t["kickout"] = BU.get("sale_contingency_days") or 21, True
        why["sale_contingency_days"] = "Your sale has to close first; the kick-out clause lets the seller keep marketing"
    t["contract_form"] = B["contract_form"]
    # OFR-18: only a quote in hand is scored. OFR-216: "planned" only when the agent said so; otherwise no quote yet
    t["insurance_quote"] = True if quote_in_hand(BU) else "planned" if BU.get("insurance_quote") == "planned" else None
    why["insurance_quote"] = ("Quote in hand: include it with the offer" if quote_in_hand(BU) else
                              "Get the quote before submitting; listing agents weigh it on older roofs")
    if lvl >= 2 and fin in ("cash", "conventional") and BU["down_pct"] >= 0.10:
        # Cap = the lowest of the buyer's max, the CMA's walk-away, and the price whose appraisal gap (above the same
        # risk line the listing side uses) the buyer can still fund with the reserve intact (OFR-5).
        walk = (B.get("cma_offer_plan") or {}).get("walk_away")
        capv = rnd(min(BU["max_price"], walk or BU["max_price"]), 1000, "down")
        by_walk = bool(walk) and walk < BU["max_price"]

        def gap_at(p):
            return max(gap, rnd(p - line, 1000, "up")) if fin != "cash" and p > line else gap

        if BU.get("max_payment"):
            while capv > price and monthly_payment(B, costs, capv) > BU["max_payment"]:
                capv, by_walk = capv - 1000, False
        while capv > price and buyer_cash(B, {"price": capv, "seller_concessions": conc,
                                              "appraisal_gap": gap_at(capv)})["reserve"] < BU["reserve_floor"]:
            capv, by_walk = capv - 1000, False
        if capv > price:
            t["escalation"] = {"increment": 1000, "cap": capv, "gap_at_cap": gap_at(capv)}
            if gap_at(capv) > gap:  # OFR-105: the package's gap coverage is written at the cap's gap, and scored that way
                t["appraisal_gap"] = gap = gap_at(capv)
                why["appraisal_gap"] = (f"Covers the gap at the {money(capv)} escalation cap, so the offer holds wherever "
                                        "it escalates")
            support = ("inside the value range, so the appraisal can support it" if capv <= line or fin == "cash" else
                       f"{money(capv - line)} above the value range: the appraisal gap coverage is written at the cap's "
                       "gap, and your cash covers it")
            why["escalation"] = (f"+$1,000 over the best offer, cap {money(capv)}: {support}; your reserve holds"
                                 + (" (held at your CMA's walk-away price)" if by_walk else ""))
        elif price >= BU["max_price"]:
            why["escalation"] = f"Not used: the offer is already at your max price ({money(BU['max_price'])})"
        elif by_walk:  # OFR-205: what going on to the buyer's max would cost, not only where the walk-away stopped it
            above = BU["max_price"] - line
            why["escalation"] = (f"Not used: the offer is already at your CMA's walk-away price ({money(walk)}). Your max is "
                                 f"{money(BU['max_price'])}" + (f", but a price there is {money(above)} above the top of the "
                                 f"value range ({money(line)}): cash you'd have to cover if the appraisal comes in low"
                                 if above > 0 and fin != "cash" else "; the walk-away is the CMA's ceiling for this home"))
        else:
            why["escalation"] = "Not used: no room in your cash or payment to go higher"
    elif lvl >= 2:
        why["escalation"] = "Not used: with low down payment, price above value gets cut by the appraisal"
    return t, why


def stronger(B, t):
    """Next step up: a 3% deposit, plus gap coverage where the listing side credits it (never beyond the buyer's actual cash;
    may dip below the reserve)."""
    s = dict(t)
    if buyer_cash(B, t)["reserve"] < 0:
        return None  # can't afford the base offer: a stronger one is meaningless
    uncovered = t["price"] - B["value"]["cma_high"] - t.get("appraisal_gap", 0)  # above the listing side's risk line
    if B["buyer"]["financing"] not in ("cash", "fha", "va") and uncovered > 0:  # an FHA/VA gap clause earns no credit
        c = buyer_cash(B, t)
        room = max(0, rnd(B["buyer"]["cash_available"] - c["worst"], 500, "down"))
        s["appraisal_gap"] = t.get("appraisal_gap", 0) + min(rnd(uncovered, 1000, "up"), room)
    s["deposit"] = max(t.get("deposit", 0), rnd(0.03 * t["price"], 500, "up"))
    return None if s == t else s


def price_ceiling(B, t):
    """Manual v5: the highest price a Stronger option may go to, with what sets it: the lowest of the top of the value
    range (above it the appraisal needs gap coverage), the CMA's walk-away, the buyer's max and, with one competing offer
    or fewer, list. Returns (price, words)."""
    P, V, BU, lvl = B["property"], B["value"], B["buyer"], B["competition"]["level"]
    walk = (B.get("cma_offer_plan") or {}).get("walk_away")
    caps = [(V["cma_high"], f"the top of the value range ({money(V['cma_high'])})"),
            (walk, f"your CMA's walk-away ({money(walk)})" if walk else ""),
            (BU["max_price"], f"your max price ({money(BU['max_price'])})"),
            (P["list_price"] if lvl <= 1 else None, f"the list price ({money(P['list_price'])})")]
    p, words = min(((x, w) for x, w in caps if x), key=lambda c: c[0])
    return rnd(p, 1000, "down"), words


def smallest_ask(B, costs, t, p):
    """The smallest seller-concession ask at price `p` that keeps every limit of the offer `t`, or None."""
    cc = closing_costs(B, p)
    most = int(min(cc, concession_cap(B, p)) // 100 * 100)
    for c in [0] + list(range(MIN_CONCESSION_ASK, most + 1, 500)) + [most]:
        if within_limits(B, costs, dict(t, price=p, seller_concessions=c)):
            return c
    return None


def stronger_net(B, costs, t):
    """Manual v5: when stronger() has nothing to add (the deposit is at 3% and no appraisal gap needs covering), the
    terms inside every limit the listing agent would rank highest: a higher price up to price_ceiling() with the smallest
    concession ask the buyer's cash allows at it, scored by the engine (a higher price can lower the appraisal score, so
    more net isn't always stronger). None when nothing ranks higher. An escalating offer, one with no value range or one
    already past the reserve floor is left as is."""
    V, BU = B["value"], B["buyer"]
    if t.get("escalation") or V.get("assumed") or buyer_cash(B, t)["reserve"] < BU["reserve_floor"]:
        return None
    top = max(price_ceiling(B, t)[0], t["price"])
    tries = []
    for p in range(int(t["price"]), int(top) + 1, 1000):
        c = smallest_ask(B, costs, t, p)
        if c is not None and p - c > t["price"] - t.get("seller_concessions", 0):
            tries.append((f"try{len(tries)}", dict(t, price=p, seller_concessions=c)))
    if not tries:
        return None
    _, O = run_engine(B, costs, [("recommended", t)] + tries)
    lp, tgt = B["property"]["list_price"], O["recommended"]["target"]["net_adj"]
    k, s = max(tries, key=lambda kt: (ci(O[kt[0]], tgt, lp), -kt[1]["price"]))
    return s if ci(O[k], tgt, lp) > ci(O["recommended"], tgt, lp) else None


def no_stronger_limits(B, costs, t):
    """Manual v5: why no higher price or smaller concession ask fits, in words ("a higher price would break your $5,000
    reserve floor (leaves $4,893)")."""
    top, top_words = price_ceiling(B, t)
    out = []
    if t["price"] >= top:
        out.append(f"the price is already at {top_words}")
    else:
        broken = limits_broken(B, costs, dict(t, price=t["price"] + 1000))
        out.append("a higher price would break " + " and ".join(w for _, w in broken) if broken else
                   "a higher price wouldn't rank higher with the listing agent")
    conc = t.get("seller_concessions", 0)
    if conc:
        less = conc - 500 if conc - 500 >= MIN_CONCESSION_ASK else 0
        broken = limits_broken(B, costs, dict(t, seller_concessions=less))
        out.append("a smaller concession ask would break " + " and ".join(w for _, w in broken) if broken else
                   "a smaller concession ask wouldn't rank higher with the listing agent")
    return out


def no_stronger_reason(B, t, costs=None):
    """OFR-205, OFR-208: why stronger() has nothing to add to the offer `t`. Manual v5: two plain sentences, no colon
    (the report prints it after "No Stronger Option:"), and the second says which limit stops a higher price or a
    smaller concession ask, never that nothing more would make the offer stronger."""
    if buyer_cash(B, t)["reserve"] < 0:
        return "The recommended offer already needs more cash than the buyer has."
    fin = B["buyer"]["financing"]
    uncovered = t["price"] - B["value"]["cma_high"] - t.get("appraisal_gap", 0)
    gap = ("cash needs no appraisal gap coverage" if fin == "cash" else
           f"an {fin.upper()} gap clause earns no credit with the listing side (the rider lets the buyer walk if the "
           "appraisal is low)" if fin in ("fha", "va") else
           ("the price is inside the value range, so there's no appraisal gap to cover" if t["price"] >= B["value"]["cma_low"]
            else "the price is below the value range, so there's no appraisal gap to cover")
           if t["price"] <= B["value"]["cma_high"] else
           "the appraisal gap coverage already covers the price above the value range" if uncovered <= 0 else
           "no cash is left for more appraisal gap coverage")
    # OFR-231: the deposit as the report prints it ("$11,000 (3.1%)"), never a rounder percent beside it
    first = f"The deposit is already {term_val('deposit', t, B)} and {gap}."
    if costs is None or B["value"].get("assumed") or t.get("escalation"):
        return first
    return f"{first} Nothing stronger fits within your limits, since {' and '.join(no_stronger_limits(B, costs, t))}."


COMP_WORDS = {0: "no competing offers", 1: "one competing offer", 2: "two or three competing offers",
              3: "cash or four or more competing offers"}


def lower_cost(B, costs, rec):
    """The recommended offer (with the agent's overrides) softened toward one competition level lower: never a higher
    price, deposit or gap, no escalation (OFR-8). None if nothing changes."""
    lvl = B["competition"]["level"]
    if lvl == 0:
        return None, {}
    B2 = copy.deepcopy(B)
    B2["competition"]["level"] = lvl - 1
    soft, why = build_offer(B2, costs)
    t = dict(rec)
    t.pop("escalation", None)
    for k in ("price", "deposit", "appraisal_gap"):
        t[k] = min(rec.get(k, 0), soft.get(k, 0))
    for k in ("inspection_days", "loan_approval_days", "closing_days"):
        if k in rec and k in soft:
            t[k] = max(rec[k], soft[k])
    cc = closing_costs(B, t["price"])
    t["seller_concessions"] = min(max(rec.get("seller_concessions", 0), soft.get("seller_concessions", 0)),
                                  int(cc // 100 * 100), int(concession_cap(B, t["price"]) // 100 * 100))
    why = {k: v for k, v in why.items() if t.get(k) != rec.get(k)}
    # OFR-326: build_offer worded the price and concessions for one competition level lower; the deal has the expected
    # level, so these reasons say what the softer terms are written for instead of calling the competition "little"
    written = f"written for {COMP_WORDS[lvl - 1]}, not the {COMP_WORDS[lvl]} expected"
    if t["price"] < rec["price"]:
        why["price"] = f"{money(rec['price'] - t['price'])} under the fuller offer: {written}"
    if t["seller_concessions"] > rec.get("seller_concessions", 0):
        why["seller_concessions"] = ("Covers your closing costs" if t["seller_concessions"] >= int(cc // 100 * 100) else
                                     "More of your closing costs") + f": a bigger ask, {written}"
    return (None, {}) if t == rec else (t, why)


def meaningful_ask(B, costs, t, conc):
    """A seller-concession ask of at least MIN_CONCESSION_ASK: a smaller one drops to $0 when every buyer limit still
    holds without it (the offer is cleaner), otherwise it rounds up to the minimum (never past the closing costs or the
    loan program's cap)."""
    if not 0 < conc < MIN_CONCESSION_ASK:
        return conc
    if within_limits(B, costs, dict(t, seller_concessions=0)):
        return 0
    most = min(closing_costs(B, t["price"]), concession_cap(B, t["price"]))
    return MIN_CONCESSION_ASK if most >= MIN_CONCESSION_ASK else conc


def conc_need(B, price):
    """The seller concessions the buyer's cash can't do without at `price`: what closing takes beyond cash after the
    reserve."""
    BU = B["buyer"]
    return max(0, round(price * BU["down_pct"]) + closing_costs(B, price) - (BU["cash_available"] - BU["reserve_floor"]))


def reach_band(B, costs, rec):
    """OFR-325: when the rule-built offer reads At Risk or Unlikely, the lowest-cost offer inside every limit that reaches
    a better band, with that band and the same-band offer that keeps the most cash (OFR-332); else (None, None, None). It tries a price anywhere in the value range up to its top (never
    past the CMA's walk-away, the buyer's max or, with little competition, list), smaller concessions down to what the
    buyer's cash can't cover with the reserve kept, a 3% deposit and the lender's fastest close. Lowest cost: the price
    net of concessions, then the smaller deposit, then the longer close. An escalating offer is left as built."""
    P, V, BU, lvl = B["property"], B["value"], B["buyer"], B["competition"]["level"]
    if rec.get("escalation") or V.get("assumed"):
        return None, None, None
    walk = (B.get("cma_offer_plan") or {}).get("walk_away")
    top = rnd(min(x for x in (V["cma_high"], walk, BU["max_price"], P["list_price"] if lvl <= 1 else None) if x),
              1000, "down")
    low = min(rnd(V["cma_low"], 1000, "up"), top)
    fast = BU["lender_min_close_days"]
    while not dates.is_business_day(B["effective_date"] + timedelta(days=fast)):
        fast += 1  # OFR-219: a business day, as build_offer counts it
    closes = sorted({rec["closing_days"], min(fast, rec["closing_days"])})
    tries = []
    step = max(1000, int(rnd((top - low) / 30, 1000, "up")))  # at most about 30 prices and 20 concession amounts
    for p in sorted(set(range(int(low), int(top) + 1, step)) | {int(top)} | ({rec["price"]} if rec["price"] <= top else set())):
        cc, need = closing_costs(B, p), conc_need(B, p)
        most = min(rec.get("seller_concessions", 0), int(cc // 100 * 100), int(concession_cap(B, p) // 100 * 100))
        room = round(p * BU["down_pct"]) + cc  # build_offer's rule: the deposit never exceeds the cash to close
        first = int(rnd(need, 500, "up")) if need else 0
        cstep = max(500, int(rnd((most - first) / 20, 500, "up"))) if most > first else 500
        asks = {meaningful_ask(B, costs, {"price": p}, c) for c in set(range(first, most + 1, cstep)) | {most}}
        for conc in sorted(a for a in asks if a <= max(most, MIN_CONCESSION_ASK if most else 0)):
            deps = {rec["deposit"], int(min(max(rec["deposit"], rnd(0.03 * p, 500, "up")), max(1000, room - conc)))}
            for dep in sorted(deps):
                for days in closes:
                    # every price tried is inside the value range, so no appraisal gap is needed
                    t = dict(rec, price=p, seller_concessions=conc, deposit=dep, closing_days=days, appraisal_gap=0)
                    if conc >= need and t != rec and within_limits(B, costs, t):
                        tries.append((f"try{len(tries)}", t))
    if not tries:
        return None, None, None
    _, O = run_engine(B, costs, [("recommended", rec)] + tries)
    # each offer against its own clean offer at list (the same closing date), as it's scored once recommended
    bands = {k: band_of(ci(O[k], O[k]["target"]["net_adj"], P["list_price"]), lvl) for k in O}
    best = max(BAND_RANK[b[0]] for b in bands.values())
    if bands["recommended"][0] not in ("risk", "unl") or best <= BAND_RANK[bands["recommended"][0]]:
        return None, None, None
    same = [(k, t) for k, t in tries if BAND_RANK[bands[k][0]] == best]
    k, t = min(same, key=lambda kt: (kt[1]["price"] - kt[1]["seller_concessions"], kt[1]["deposit"], -kt[1]["closing_days"]))
    # OFR-332: the same-band offer that keeps the most cash, for when the cheapest one leaves a thin cushion
    roomy = max((t2 for _, t2 in same), key=lambda t2: buyer_cash(B, t2)["reserve"])
    return t, bands[k], roomy


def smaller_than(B, t, was):
    """Manual v5: what a smaller concession ask is smaller than, in words the report shows: the area's typical
    seller-paid amount when the ask is under it ("the area's typical $6,000"), else the first draft's ask."""
    typ = B["market"].get("typical_seller_paid")
    if isinstance(typ, (int, float)) and not isinstance(typ, bool):
        n = typ
    else:
        digits = re.sub(r"[^\d.]", "", str(typ or ""))
        n = float(digits) if re.fullmatch(r"\d+(\.\d+)?", digits) else None
    if n and t["seller_concessions"] < n:
        return f"the area's typical {money(n)}"
    return money(was.get("seller_concessions", 0))


def reach_why(B, why, t, was, band):
    """OFR-325: the reasons for the terms reach_band changed, against the competition the deal expects."""
    why = dict(why)
    BU, V, lvl = B["buyer"], B["value"], B["competition"]["level"]
    vs = f"{band[1]} against {COMP_WORDS[lvl]}" if lvl else f"{band[1]} as the only offer"
    walk = (B.get("cma_offer_plan") or {}).get("walk_away")
    if t["price"] != was["price"]:
        where = ("at the top of the value range" if t["price"] >= V["cma_high"] else
                 "at your CMA's walk-away" if walk and t["price"] >= walk else "inside the value range")
        why["price"] = f"The lowest price that reaches {vs}: {where}, within your limits"
    if t["seller_concessions"] < was.get("seller_concessions", 0):
        keep = f"{money(BU['reserve_floor'])} reserve kept"
        why["seller_concessions"] = (
            f"None: a clean offer nets the seller more, and your cash covers closing with the {keep}"
            if not t["seller_concessions"] else
            f"A smaller ask nets the seller more: only what your cash can't cover with the {keep}"
            if t["seller_concessions"] < conc_need(B, t["price"]) + 500 else
            f"A smaller ask than {smaller_than(B, t, was)}: it nets the seller more and lifts the outlook")
    if t["deposit"] > was.get("deposit", 0):
        why["deposit"] = (f"{t['deposit'] / t['price']:.0%} shows commitment; {B['words']['deposit_refund']}; counts "
                          "toward cash to close")
    if t["closing_days"] < was.get("closing_days", 0):
        why["closing_days"] = "Fastest your lender can reliably close: a quicker close lifts the outlook"
    if was.get("appraisal_gap") and not t.get("appraisal_gap"):
        why["appraisal_gap"] = "Not needed: price is inside the value range"
    return why


def option_set(B, costs, rec):
    """The options to score: (variants, the lower-cost reasons, whether the Stronger option is stronger_net()'s)."""
    variants = [("recommended", rec)]
    st, by_net = stronger(B, rec), False
    if not st:  # manual v5: a higher price or a smaller concession ask, inside every limit
        st = stronger_net(B, costs, rec)
        by_net = bool(st)
    if st:
        variants.append(("stronger", st))
    lc, lc_why = lower_cost(B, costs, rec)
    if lc:
        variants.append(("lower_cost", lc))
    return variants, lc_why, by_net


BAND_RANK = {"strong": 3, "comp": 2, "risk": 1, "unl": 0}


def within_limits(B, costs, t):
    BU = B["buyer"]
    c = buyer_cash(B, t)
    return (t["price"] <= BU["max_price"] and c["reserve"] >= BU["reserve_floor"] and not c["wasted_conc"]
            and not (BU.get("max_payment") and monthly_payment(B, costs, t["price"]) > BU["max_payment"])
            and t.get("seller_concessions", 0) <= concession_cap(B, t["price"]) + 1)


def better_option(B, costs, terms, O, lvl, promote_stronger=True):
    """The option to recommend instead, if the rule-built offer isn't the best by the skill's own rule, else None.
    Manual v5: a Stronger option that only pays more (stronger_net) stays the buyer's choice, never promoted: the
    search for the lowest-cost offer that reaches a better band is reach_band's."""
    if B.get("overrides"):
        return None  # the agent decided the terms
    lp = B["property"]["list_price"]
    tgt = O["recommended"]["target"]["net_adj"]
    # the outlook at every competition level, as "How It Stacks Up" prints it
    ranks = {k: [BAND_RANK[band_of(ci(O[k], tgt, lp), lv)[0]] for lv in range(4)] for k in terms}
    rank = {k: r[lvl] for k, r in ranks.items()}
    if promote_stronger and "stronger" in terms and rank["stronger"] > rank["recommended"] \
            and within_limits(B, costs, terms["stronger"]):
        return "stronger"
    # OFR-9: "best" is the strongest outlook at the lowest cost that reaches it, so a cheaper option in the same band wins.
    # iteration 9 eval 1: never an option the lower-cost rule drops (Unlikely against the expected competition at
    # level 2+, offer-rules.md)
    if "lower_cost" in terms and rank["lower_cost"] >= rank["recommended"] \
            and not (lvl >= 2 and rank["lower_cost"] == BAND_RANK["unl"]) and within_limits(B, costs, terms["lower_cost"]) \
            and buyer_cash(B, terms["lower_cost"])["worst"] < buyer_cash(B, terms["recommended"])["worst"]:
        return "lower_cost"
    return None


def promote_why(why, lc_why, pick, t, was=None, words=None):
    """The reasons for a promoted option. CMA-103: the Stronger option names only what it actually raised."""
    why = dict(why)
    was = was or {}
    if pick == "lower_cost":
        why.update(lc_why)
        why.pop("escalation", None)
        # OFR-326: worded for the competition the deal expects, never the softer level the option was built for
        why["price"] = (f"{money(was['price'] - t['price'])} under the fuller offer: the same outlook, for less"
                        if was.get("price", 0) > t["price"] else why.get("price", ""))
        if lc_why.get("seller_concessions"):
            ask = lc_why["seller_concessions"].split(":")[0]
            why["seller_concessions"] = f"{ask}: a bigger ask that keeps the same outlook"
    if pick == "stronger":
        if t.get("appraisal_gap", 0) > was.get("appraisal_gap", 0):
            why["appraisal_gap"] = "Covers more of an appraisal shortfall: lifts the outlook and stays inside your limits"
        if t.get("deposit", 0) > was.get("deposit", 0):
            refund = (words or cf.term_words(None))["deposit_refund"]
            why["deposit"] = f"{t['deposit'] / t['price']:.0%} shows commitment; {refund}; counts toward cash to close"
    return why


def net_no_gain(rec, st):
    """Manual v5: why the strongest terms inside the buyer's limits aren't offered: the terms they take, what the seller
    would net, and that the outlook and score stay the same."""
    parts = []
    if st["price"] > rec["price"]:
        parts.append(f"offering {money(st['price'])}")
    c0, c1 = rec.get("seller_concessions", 0), st.get("seller_concessions", 0)
    if c1 != c0:
        parts.append(f"asking {f'{money(c1)} in' if c1 else 'no'} seller concessions instead of {money(c0)}")
    gain = (st["price"] - c1) - (rec["price"] - c0)
    what = " and ".join(parts)
    return (f"{what[:1].upper()}{what[1:]}, the strongest terms your limits allow, would net the seller {money(gain)} more "
            "but wouldn't change the outlook or the listing agent's score, so it isn't worth the extra cost.")


def raised(t, was):
    """What the Stronger option raised over the offer it replaced, in words ('appraisal-gap coverage and deposit')."""
    parts = [name for key, name in (("appraisal_gap", "appraisal-gap coverage"), ("deposit", "deposit"))
             if t.get(key, 0) > (was or {}).get(key, 0)]
    return " and ".join(parts)


# --- top level -----------------------------------------------------------------

def analyze(B_in, market=None, cma=None):
    oe.check_fractions(B_in)
    B0 = apply_cma(B_in, cma) if cma else copy.deepcopy(B_in)
    A = oe.Assume()
    if B0.get("_cma_side_note"):
        A.add("value", "cma_side", "other side", B0["_cma_side_note"], "high")
    if B0.get("_cma_address_note"):  # CMA-102
        A.add("value", "cma_address", "another property", B0["_cma_address_note"], "high")
    if B0.get("_dom_aged"):  # OFR-242
        was, as_of, since = B0["_dom_aged"]
        A.add("property", "dom", B0["property"]["dom"], f"Days on market: {B0['property']['dom']}, the CMA's {was} as of "
              f"{as_of:%b} {as_of.day} plus the {since} day{'s' if since != 1 else ''} since", "low")
    B, costs = prepare(B0, A, market)
    lvl = B["competition"]["level"]
    rec, why = build_offer(B, costs)
    ov = B.get("overrides") or {}
    for k, v in ov.items():  # the agent's judgment wins; the report marks it
        rec[k] = v
        why[k] = "Agent's choice"
    if B["contract_form"] not in cf.FARBAR:  # OFR-222: a best-effort contract's own questions, asked before cost details
        if not (B.get("worksheet") or {}).get("contract_name"):
            A.add("worksheet", "contract_name", None, "Contract form not named: ask which form (and version) the offer goes "
                  "on; the worksheet finds each entry by its name", "med")
        if "inspection_days" not in ov:  # OFR-315: the chat carries it as a reply line; the report lists it here
            A.add("worksheet", "inspection_days", rec["inspection_days"], f"Inspection or option period: "
                  f"{rec['inspection_days']} days is a generic default, not a local rule. Confirm what's usual for this "
                  "contract in this market", "low")
        # OFR-316: the deposit's risk date is counted from this offer's own periods, never from another form's rules
        A.add("worksheet", "deposit_risk", None, "Deposit at Risk After is counted from this offer's inspection or option, "
              "loan approval and appraisal periods: confirm when your contract makes the deposit nonrefundable", "low")
    if "payment" in why.get("price", ""):  # the payment limit sets the price, so its inputs matter most
        for a in A.items:
            if a["field"] == "property_tax" and a["impact"] == "low":
                a["impact"] = "med"
            if a["field"] in ("rate", "rate_source", "insurance_annual"):  # iteration 9 eval 1: asked right after the deadline
                a["caps_price"] = True
                # iteration 10 eval 1: an estimated rate or premium moves the price itself, so it's high impact (the
                # report reads Preliminary and its page-1 line names them first), whether assumed or looked up
                a["impact"] = "high"
    reached = None
    if not ov:  # OFR-325: the rule-built offer is a first draft; the strongest outlook inside the limits wins
        t, band, roomy = reach_band(B, costs, rec)
        if t:
            why, reached = reach_why(B, why, t, rec, band), {"from": rec, "band": band[1], "roomy": roomy}
            rec = t
    promoted = fuller = None
    for _ in range(2):  # "best" = strongest outlook inside the limits at the lowest cost that reaches it
        variants, lc_why, by_net = option_set(B, costs, rec)
        R, O = run_engine(B, costs, variants)
        pick = better_option(B, costs, dict(variants), O, lvl, promote_stronger=not by_net)
        if not pick or promoted:
            break
        promoted, fuller = pick, rec
        rec = dict(variants)[pick]
        why = promote_why(why, lc_why, pick, rec, fuller, B["words"])
        if pick == "lower_cost":  # OFR-9: the fuller offer stays on the table as the stronger alternative
            variants, lc_why, by_net = [("recommended", rec), ("stronger", fuller)], {}, False
            R, O = run_engine(B, costs, variants)
            break
    # OFR-240: the escalation question only when the offer escalates; with one flat number it would contradict the advice
    if B["contract_form"] not in cf.FARBAR and rec.get("escalation"):
        A.add("competition", "escalation_accepted", None, "Ask the listing agent whether they accept an escalation "
              "clause or want one flat number; not every contract has an escalation form", "med")
    lp = B["property"]["list_price"]
    tgt = O["recommended"]["target"]["net_adj"]
    limits = profiles.loan_limits()  # OFR-11: jumbo and FHA limits
    BU0, P0 = B["buyer"], B["property"]
    loan_notes = {k: finance.loan_limit_note(finance.loan_amount(t["price"], BU0["financing"], BU0["down_pct"]),
                                             BU0["financing"], limits, P0.get("state"), P0.get("county")) for k, t in variants}
    if loan_notes.get("recommended"):
        A.add("buyer", "loan_limit", "check", loan_notes["recommended"], "high")
    engine_assumed = [tax_bill_note(B, costs, O, a) for a in R["assumptions"] if not a["scope"].startswith("offer")
                      and a["scope"] != "seller" and a["field"] not in ("cma_low / cma_high", "state")]
    res = {"B": B, "R": R, "O": O, "why": why, "lc_why": lc_why, "terms": dict(variants), "target": tgt, "overrides": list(ov),
           "promoted": promoted, "promoted_from": fuller if promoted else None, "reached": reached,
           "assumptions": A.items + engine_assumed, "costs": costs, "sample": bool(B_in.get("sample"))}
    res["cash"] = {k: buyer_cash(B, t) for k, t in variants}
    res["payment"] = {k: monthly_payment(B, costs, t["price"]) for k, t in variants}
    esc_ = rec.get("escalation")
    res["cash_at_cap"] = buyer_cash(B, dict(rec, price=esc_["cap"], appraisal_gap=esc_.get("gap_at_cap", rec.get("appraisal_gap", 0)))) \
        if esc_ else None
    res["ci"] = {k: ci(O[k], tgt, lp) for k, _ in variants}
    res["bands"] = {k: {lv: band_of(res["ci"][k], lv) for lv in range(4)} for k, _ in variants}
    saves_nothing = "lower_cost" in res["terms"] and res["cash"]["lower_cost"]["worst"] >= res["cash"]["recommended"]["worst"]
    unlikely = "lower_cost" in res["terms"] and lvl >= 2 and res["bands"]["lower_cost"][lvl][0] == "unl"
    already_unlikely = res["bands"]["recommended"][lvl][0] == "unl"  # iteration 10 eval 1: nothing lower to drop to
    if saves_nothing or unlikely:  # OFR-30
        for d in (res["terms"], res["cash"], res["payment"], res["ci"], res["bands"], O):
            d.pop("lower_cost", None)
        res["lower_cost_dropped"] = True
    # OFR-218: a Stronger option that gains nothing (same outlook, no higher score) isn't worth offering
    no_gain = "stronger" in res["terms"] and res["bands"]["stronger"][lvl] == res["bands"]["recommended"][lvl] \
        and O["stronger"]["score"]["total"] <= O["recommended"]["score"]["total"]
    if no_gain:
        what = raised(res["terms"]["stronger"], rec)
        net_terms = res["terms"]["stronger"] if by_net else None
        for d in (res["terms"], res["cash"], res["payment"], res["ci"], res["bands"], O):
            d.pop("stronger", None)
        res["stronger_dropped"] = True
    for k in O:  # OFR-216: the scorecard says what's known about the quote, never that one is planned when it isn't
        if res["terms"][k].get("insurance_quote") is None:
            w = O[k]["score"]["why"]
            w["property"] = ("No known condition issues" if w["property"] == "No known condition or insurance issues"
                             else w["property"]) + "; no insurance quote yet (scored once in hand)"
    # OFR-205, OFR-208: every option that isn't on the page says why
    absent = {}
    if "stronger" not in res["terms"]:
        absent["stronger"] = ("The recommended offer already includes the stronger terms." if promoted == "stronger" else
                              net_no_gain(rec, net_terms) if no_gain and net_terms else
                              f"{'More ' + what if what else 'The fuller terms'} wouldn't change the outlook or the listing "
                              "agent's score, so it isn't worth the extra cash at risk." if no_gain else
                              no_stronger_reason(B, rec, costs))
    if "lower_cost" not in res["terms"]:
        absent["lower_cost"] = (
            "The recommended offer is already the lower-cost version: it reaches the same outlook for less cash."
            if promoted == "lower_cost" else
            "With no competing offers expected, the recommended offer is already written for the softest market."
            if lvl == 0 else
            "Writing it softer wouldn't save any cash." if saves_nothing else
            "Writing it softer would still read Unlikely against the expected competition." if unlikely and already_unlikely else
            "Writing it softer would drop the outlook to Unlikely against the expected competition." if unlikely else
            "Writing it for one less competing offer wouldn't change any term.")
    res["absent"] = absent
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
        if loan_notes.get(k):
            issues.append("loan over the program limit" if "can't be FHA" in loan_notes[k] else "check the loan limit")
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
    # OFR-332; OFR-338: a caution inside the limits, so it isn't one of the constraints (page 1's red Limit lines)
    res["reserve_tight"] = tight_reserve(B, costs, res, rc)
    if rec["price"] < V["cma_low"] and "payment" in why.get("price", ""):
        # iteration 9 eval 1: say what would change it. Iteration 11 eval 1: the rate and insurance quotes are named by
        # the Preliminary line (high impact when the payment sets the price), so this line only gives the payment
        cons.append(f"Your ${BU['max_payment']:,}/mo payment limit caps the price at {money(rec['price'])}, below the "
                    f"{money(V['cma_low'])}–{money(V['cma_high'])} value range. Expect this offer to be passed over unless the seller has no other interest. "
                    f"What would change it: a payment limit of about "
                    f"${monthly_payment(B, costs, V['cma_low']):,}/mo reaches the bottom of the range.")
    elif rec["price"] < V["cma_low"] and "max price" in why.get("price", ""):
        cons.append(f"Your max price ({money(BU['max_price'])}) is below the value range: expect this offer to be passed over. "
                    f"What would change it: a max price of at least {money(V['cma_low'])}, the bottom of the range.")
    res["constraints"] = cons
    res["missing"] = sorted(res["assumptions"], key=lambda a: oe.IMPACT_ORDER[a["impact"]])
    res["chosen"] = B.get("chosen_option") if B.get("chosen_option") in res["terms"] else "recommended"
    res["reply_lines"] = reply_lines(B, rec) + ([{"key": "tight_reserve", "text": res["reserve_tight"]}]
                                                 if res["reserve_tight"] else [])
    return res


def tax_bill_note(B, costs, O, a):
    """Iteration 12: the engine asks whether the seller has paid this year's tax bill when the closing falls after the
    bills go out (Florida: Nov 1). Before the bills are out nobody can have paid one, so the question can't be answered
    yet: it becomes a low-impact note (not asked), saying what the proration assumes and what changes it."""
    if a["field"] != "current_tax_bill_paid":
        return a
    today = _d(B.get("analysis_date")) or date.today()
    closes = [O[k]["close"] for k in O if O[k].get("close")]
    month = costs.get("property_tax.bill_month") or oe.TAX_BILL_MONTH
    if not closes or today >= date(min(closes).year, month, 1):
        return a  # the bills are out: the seller may have paid, so ask
    close = min(closes)
    return {**a, "impact": "low", "why": f"Closing on {close:%b} {close.day}, after this year's tax bills go out "
            f"({date(close.year, month, 1):%B} 1): the proration assumes the seller hasn't paid the bill by then (the seller "
            "credits the buyer from Jan 1). If the seller pays it before closing, the buyer credits the seller instead"}


def highest_and_best(C):
    """OFR-239: the listing agent called for highest and best (`competition.highest_and_best`, or said so in the note)."""
    hb = C.get("highest_and_best")
    return bool(hb) if hb is not None else bool(HIGHEST_AND_BEST.search(str(C.get("note") or "")))


TIGHT_RESERVE = (1000, 0.10)  # OFR-332: a cushion under $1,000 or 10% of the floor, whichever is more, is thin


def reserve_status(B, reserve):
    """The status mark on a Left in Reserve figure, agreeing with the page's warnings: "risk" below the reserve floor,
    "caution" for a thin cushion above it (tight_reserve's test), else "" (no status color)."""
    floor = B["buyer"]["reserve_floor"]
    if reserve < floor:
        return "risk"
    return "caution" if reserve - floor < max(TIGHT_RESERVE[0], TIGHT_RESERVE[1] * floor) else ""


def tight_reserve(B, costs, res, rc):
    """OFR-332: one line when the recommended offer keeps the reserve floor with a thin cushion, naming the same-outlook
    offer that keeps more cash when the search found one; else None. OFR-334: the line is neutral and carries the
    trade-off (payment difference and cash kept), so the chat quotes it and never computes or picks between them."""
    floor = B["buyer"]["reserve_floor"]
    over = rc["reserve"] - floor
    if not 0 <= over < max(TIGHT_RESERVE[0], TIGHT_RESERVE[1] * floor):
        return None
    line = (f"Thin cushion: this offer leaves {money(rc['reserve'])}, only {money(over)} above your {money(floor)} reserve "
            "floor, so closing costs that come in high would cut into it.")
    roomy = (res.get("reached") or {}).get("roomy")
    if roomy:
        keep = buyer_cash(B, roomy)["reserve"]
        if keep - rc["reserve"] >= TIGHT_RESERVE[0]:
            rec = res["terms"]["recommended"]
            dpay = monthly_payment(B, costs, roomy["price"]) - monthly_payment(B, costs, rec["price"])
            res["reserve_alt"] = {"price": roomy["price"], "seller_concessions": roomy["seller_concessions"],
                                  "payment_more": dpay, "cash_kept": keep - rc["reserve"]}
            pay = (f"costs {money(abs(dpay))} a month {'more' if dpay > 0 else 'less'}" if dpay else
                   "has the same payment")
            line += (f" Both are within your limits, and the choice is yours: {money(roomy['price'])} with "
                     f"{money(roomy['seller_concessions']) if roomy['seller_concessions'] else 'no'} seller concessions "
                     f"reaches the same outlook, {pay} and keeps {money(keep - rc['reserve'])} more cash "
                     f"({money(keep)} left).")
    return line


def reply_lines(B, rec):
    """OFR-239: lines the chat reply must carry outside its length cap, as [{key, text}]: `flat_number` (a
    highest-and-best round with no escalation: why one flat number), `contract_terms` (a contract that isn't FAR/BAR:
    the form-specific terms come from the agent's contract, never from Florida's rules) and `inspection_period` (the
    same contract with the period's length not set by the agent: it's a generic default to check locally, OFR-315) and
    `seller_timeline` (`property.seller_flexible_close`: ask whether another closing date helps the seller)."""
    out = []
    P = B["property"]
    if P.get("seller_flexible_close") and not P.get("seller_deadline"):
        # iteration 12: from the listing agent or the Realtor Remarks, so chat only, never in the report
        out.append({"key": "seller_timeline", "text": "The seller is flexible on the closing date, so this offer's "
                    "closing fits. Ask the listing agent whether a different date would help the seller: it costs the "
                    "buyer nothing and can set this offer apart."})
    if highest_and_best(B["competition"]) and not rec.get("escalation"):
        out.append({"key": "flat_number", "text": "In a highest-and-best round many listing agents want one flat number, so "
                    f"{money(rec['price'])} goes in as the single price, with no escalation clause."})
    if B["contract_form"] not in cf.FARBAR:
        out.append({"key": "contract_terms", "text": "Any option fee, and the appraisal terms of the financing addendum, "
                    "come from your contract: fill them from your forms, not from this analysis."})
        if "inspection_days" not in (B.get("overrides") or {}) and rec.get("inspection_days"):
            out.append({"key": "inspection_period", "text": f"The {rec['inspection_days']}-day inspection or option period "
                        "is a generic default, not a local rule: confirm what's usual for this contract in this market "
                        "(some markets expect a short option period in multiple offers) before the offer goes out."})
    return out


# --- formatted views (shared by the markdown template and the PDF) ---------------

TERM_KEYS = [("price", "Price"), ("seller_concessions", "Seller Concessions"), ("deposit", "Escrow Deposit"),
             ("inspection_days", "Inspection Period"), ("loan_approval_days", "Loan Approval Period"), ("appraisal_gap", "Appraisal Gap"),
             ("closing_days", "Closing"), ("buyer_broker_pct", "Buyer-Broker Comp."), ("home_warranty", "Home Warranty"),
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
        return f"{v} days ({(B['effective_date'] + timedelta(days=v)):%b %-d})"
    if k == "buyer_broker_pct":
        return f"{v:.1%} from seller" if v else "Not requested"
    if k == "home_warranty":
        return "Not requested" if not v else f"Seller pays {money(v)}"
    if k == "escalation":
        return f"+{money(v['increment'])}, cap {money(v['cap'])}" if v else "None"
    return str(v)


def term_keys(B):
    """TERM_KEYS with the inspection period named as the contract names it (OFR-234: contract_forms.term_words)."""
    named = {"inspection_days": B["words"]["inspection_label"], "deposit": deposit_label(B)}
    return [(k, named.get(k, labl)) for k, labl in TERM_KEYS]


def deposit_label(B):
    """iteration 9 eval 3: the deposit named as the contract names it (contract_forms.term_words' deposit_label when the
    shared routing has it); "Escrow Deposit" is FAR/BAR's name."""
    return B["words"].get("deposit_label") or "Escrow Deposit"


def diff_text(r, k):
    """Short 'what's different from the recommended offer' text."""
    B = r["B"]
    a, b = r["terms"]["recommended"], r["terms"][k]
    out = [f"{labl.lower()} {term_val(key, b, B)}" for key, labl in term_keys(B) if a.get(key) != b.get(key)]
    txt = "; ".join(out) or "Same terms"
    return txt[:1].upper() + txt[1:]


def deposit_risk(o):
    """OFR-210: (the date the deposit is at risk for anything but a low appraisal, the date the appraisal protection
    runs to or None). The engine's windows already follow the form and riders (contract_forms): the later of the
    inspection, loan approval and rider windows, then the appraisal window on its own (FHA/VA: to closing)."""
    ex = o.get("risk_days_ex_appraisal", o["risk_days"])
    first = o["firm_date"] - timedelta(days=o["risk_days"] - ex)
    return first, (o["firm_date"] if o["risk_days"] > ex else None)


rolled = oe.rolled  # OFR-219: the contract's weekend and holiday rule, shared with seller-offer-review (OFR-300)


def risk_after(o, costs):
    """OFR-219: (the date the deposit is at risk after, rolled per the contract rule; a short note or None). OFR-316: on
    a contract that isn't FAR/BAR the date is counted from the offer's own periods, so the note asks the agent to confirm
    when the contract releases the deposit (contract_forms.term_words)."""
    d, was = rolled(deposit_risk(o)[0], costs)
    notes = [cf.term_words(o["contract_form"])["deposit_risk_confirm"]]
    if was:
        notes.append(f"rolled from {was:%a %b} {was.day}")
    elif not dates.is_business_day(d):
        notes.append(f"a {dates.holiday_name(d) or f'{d:%A}'}: check whether the contract extends it")
    notes = [n for n in notes if n]
    return d, "; ".join(notes) or None


def risk_after_text(o, B, costs):
    d, note = risk_after(o, costs)
    return f"{d:%a %b} {d.day} ({money(o['deposit'])}" + (f"; {note}" if note else "") + ")"


def appraisal_until(o, B, costs):
    """'To closing (FHA rider)' or 'Until Mon Nov 2': how long a low appraisal alone still protects the deposit."""
    _, until = deposit_risk(o)
    if until is None:
        return None
    if o.get("appraisal_protected"):
        return f"To closing ({B['buyer']['financing'].upper()} rider)"
    until = rolled(until, costs)[0]
    return f"Until {until:%a %b} {until.day}"


def appraisal_protection(o, B, costs):
    """The cash table's Low-Appraisal Protection cell: appraisal_until's date when a low appraisal alone protects the
    deposit longer, else, when the offer has an appraisal contingency (Rider F, AGA-1) whose window ends inside the
    deposit-at-risk window, that date marked "before the deposit is at risk"; None without one."""
    longer = appraisal_until(o, B, costs)
    if longer or not (o.get("appraisal_risk") and o.get("appraisal_days")):
        return longer
    eff = o["firm_date"] - timedelta(days=o["risk_days"])
    d = rolled(eff + timedelta(days=o["appraisal_days"]), costs)[0]
    return f"Until {d:%a %b} {d.day} (before the deposit is at risk)"


def downside_label(O):
    """iteration 10 eval 1: the net sheet's downside row named from what actually applies: the appraisal only for an
    option priced above the value range (its downside price is lower), the repair cost only when there is one."""
    appraisal = any(o["downside_price"] < o["price"] for o in O.values())
    repairs = [o for o in O.values() if o.get("repair_reserve")]
    owed = any(o.get("repairs_owed") for o in repairs)
    repair = "Repairs up to the General Repair Limit" if owed else "Typical Repair Credit"
    if appraisal and repairs:
        return f"If the Appraisal and Inspection Go Badly (Appraisal at the Top of the Value Range, {repair})"
    if appraisal:
        return "If the Appraisal Comes In Low (Appraisal at the Top of the Value Range)"
    if repairs:
        return f"If the Inspection Goes Badly ({repair})"
    return "If the Appraisal and Inspection Go Badly (No Appraisal Shortfall or Repair Credit Expected)"


def fin_line(B):
    BU, f = B["buyer"], B["buyer"]["financing"]
    if f == "cash":
        return "Cash"
    txt = f"{oe.FIN_LABEL[f]} · {oe.pct(BU['down_pct'])} down"
    return txt + ("" if BU.get("financing_source") == "assumed" else " (per buyer and lender)")  # assumed: in the assumptions


def preliminary(r):
    hi = [a for a in r["missing"] if a["impact"] == "high"]
    if not hi:
        return None
    names = {"cma_low / cma_high": "value range (buyer CMA)", "state": "property state", "property_tax": "property tax",
             "cma_side": "a buyer-side CMA", "cma_address": "a CMA for this property",  # CMA-101: never a raw field name
             # iteration 10 eval 2: the same name to_confirm uses ("Loan type not provided"), so the two can be matched
             "financing": "loan type",
             # iteration 10 eval 1: the payment inputs that set the price, named as what to get
             "rate": "a lender rate quote", "rate_source": "a lender rate quote", "insurance_annual": "an insurance quote"}
    hi.sort(key=lambda a: not a.get("caps_price"))  # iteration 10 eval 1: what moves the price comes first
    B = r["B"]
    if B["buyer"].get("max_price") is not None and any(a["field"] == "max_price" for a in hi):
        # OFR-233: say what the max was assumed to be, so the reply never has to infer it
        mx, lp = B["buyer"]["max_price"], B["property"]["list_price"]
        names["max_price"] = f"max price (assumed {money(mx)}, " + ("the list price)" if mx == lp else "the top of the value range)")
    need = list(dict.fromkeys(names.get(a["field"], a["field"].replace("_", " ")) for a in hi))
    n = len(r["missing"])
    return (f"**Preliminary: based on limited data.** Add {', '.join(need)} to sharpen the recommendation; "
            f"{n} input{'s' if n != 1 else ''} assumed in total (listed at the end).")


def stronger_fits(r):
    """iteration 9 eval 1: the Stronger option is inside every limit (reserve floor kept) and the listing agent would
    score it higher, so the recommended offer can't be called the strongest inside the limits."""
    if "stronger" not in r["O"] or r["limits"].get("stronger"):
        return False
    return (r["cash"]["stronger"]["reserve"] >= r["B"]["buyer"]["reserve_floor"]
            and r["O"]["stronger"]["score"]["total"] > r["O"]["recommended"]["score"]["total"])


def summary(r):
    """Page 1 of the Offer Options report, formatted. The markdown template uses the same values."""
    B, O, lvl = r["B"], r["O"], r["B"]["competition"]["level"]
    BU, P, C = B["buyer"], B["property"], B["competition"]
    rec, rc = O["recommended"], r["cash"]["recommended"]
    br = r["bands"]["recommended"][lvl]
    dn = rec["ns"]["net_adj"] - r["target"]
    broken = r["limits"]["recommended"]
    # OFR-221: an agent override past a limit is never called "inside your limits": the limit it breaks is named
    # iteration 9 eval 1: a Stronger option inside every limit that scores higher (same outlook) means this one isn't
    # "the strongest": it's the best outlook with the least cash at risk
    best = "The strongest offer inside your limits." if not stronger_fits(r) else \
        "The best outlook inside your limits, with the least cash at risk."
    lead = (best if not broken else
            ("Your terms, but they break your limits: " if r["overrides"] else "The best structure available, but it breaks "
             "your limits: ") + "; ".join(broken) + ".")
    why = (f"{lead} A listing agent would score it **{rec['score']['total']}/100**, and it nets the seller "
           + ("about the same as a clean offer at list." if abs(dn) < 500 else f"{money(abs(dn))} {'less' if dn < 0 else 'more'} than a clean offer at list."))
    if r.get("promoted") == "stronger":  # CMA-103: only what the stronger terms actually raised
        what = raised(r["terms"]["recommended"], r.get("promoted_from"))
        why += (f" It includes the stronger terms (more {what}): they lift the outlook and stay inside your limits." if what else
                " It includes the stronger terms: they lift the outlook and stay inside your limits.")
    if rc["reserve"] < 0:
        why = f"**Not affordable as structured:** {money(-rc['reserve'])} short on cash. " + why
    if "stronger" in O:
        bs, cs = r["bands"]["stronger"][lvl], r["cash"]["stronger"]
        if bs != br:
            why += f" Reaching **{bs[1]}** takes {money(cs['worst'] - rc['worst'])} more worst-case cash" + (
                f", below your {money(BU['reserve_floor'])} reserve floor." if cs["reserve"] < BU["reserve_floor"] else ".")
        else:
            why += " The stronger terms wouldn't change the outlook."
    if "lower_cost" in O:
        bl, cl = r["bands"]["lower_cost"][lvl], r["cash"]["lower_cost"]
        # iteration 10 eval 3: the saving is worst-case cash to close, not price, so it says so
        why += f" Writing softer saves {money(rc['worst'] - cl['worst'])} in worst-case cash" + (
            f" but drops to **{bl[1]}**." if bl != br else " with the same outlook.")
    if BU["financing"] in ("fha", "va", "usda") and lvl >= 2:  # iteration 11 eval 1: not when a limit caps the price
        why += (f" {BU['financing'].upper()} financing caps the score, and no escalation." if r.get("constraints") else
                f" {BU['financing'].upper()} financing caps the score, so certainty and net do the work, not escalation.")

    t, w = r["terms"]["recommended"], r["why"]
    terms = []
    for key, labl in term_keys(B):
        if key in ("loan_approval_days", "appraisal_gap") and BU["financing"] == "cash":
            continue
        if key == "escalation" and not t.get("escalation") and not w.get("escalation"):
            continue
        terms.append({"term": labl, "offer": term_val(key, t, B), "why": w.get(key) or "", "agent": key in r["overrides"]})

    options = []
    for k in O:
        o, c = O[k], r["cash"][k]
        if k == "recommended":
            what = ("Best outlook inside your limits, least cash at risk" if stronger_fits(r) else "Strongest offer inside your limits") \
                if not r["limits"][k] else "Best structure available; " + r["limits"][k][0]
            status = "" if not r["limits"][k] else "risk"  # no green beside an At Risk outlook: status only on a break
        elif k == "stronger":
            same = r["bands"][k][lvl] == br
            extra = c["worst"] - rc["worst"]
            # OFR-218: the deposit is part of cash to close, so a bigger one is more cash at risk early, not more cash
            gain = (f". Reaches {r['bands'][k][lvl][1]}" if not same else
                    f". Same outlook, score {o['score']['total']} vs. {rec['score']['total']}"
                    + (f", for {money(extra)} more worst-case cash" if extra > 0 else ", with more of your cash at risk as deposit"))
            what = diff_text(r, k) + gain + (f"; {r['limits'][k][0]}" if r["limits"][k] else "")
            status = "caution"
        else:
            what = diff_text(r, k) + f". Saves {money(rc['worst'] - c['worst'])} in worst-case cash" + (  # iteration 10 eval 3
                "" if r["bands"][k][lvl] == br else f"; outlook {r['bands'][k][lvl][1]}")
            status = "caution"
        options.append({"key": k, "option": OPTION_LABEL[k], "price": money(o["price"]), "outlook": r["bands"][k][lvl][1],
                        "outlook_class": r["bands"][k][lvl][0], "seller_net": money(o["ns"]["net_adj"]), "worst_cash": money(c["worst"]),
                        "reserve": money(c["reserve"]), "what": what, "status": status})
    bands = [{"level": COMP_LABEL[lv] + (" (Expected)" if lv == lvl else ""),
              "values": [{"band": r["bands"][k][lv][1], "class": r["bands"][k][lv][0]} for k in O]} for lv in range(4)]
    exposure = [["Cash to Close (Deposit Counts Toward It)", money(rc["to_close"])],
                ["+ Appraisal Gap if the Appraisal Is Low", money(rc["gap"])],
                ["Worst-Case Cash Needed", f"{money(rc['worst'])} of {money(BU['cash_available'])}"],
                ["Left in Reserve", f"{money(rc['reserve'])} (floor {money(BU['reserve_floor'])})"],
                ["Est. Monthly Payment", f"${r['payment']['recommended']:,}" + (f" of ${BU['max_payment']:,}" if BU.get("max_payment") else "")],
                ["Deposit at Risk After", risk_after_text(rec, B, r["costs"])]]
    if appraisal_until(rec, B, r["costs"]):  # OFR-210: a low appraisal alone protects the deposit longer, on its own line
        exposure.append(["Low-Appraisal Protection", appraisal_until(rec, B, r["costs"])])
    if r.get("cash_at_cap"):
        cc = r["cash_at_cap"]
        exposure.append([f"At the {money(t['escalation']['cap'])} cap", f"{money(cc['worst'])} · reserve {money(cc['reserve'])}"])
    # OFR-226: an inferred read names the signals it rests on
    signal = C.get("note") or (f"None given; {heat_words(C['heat'], C['heat_basis'])}" if C["heat_basis"] != "no market data"
                               else "None given; no market data")
    if C.get("note") and P.get("dom") is not None and B["market"].get("median_dom"):
        signal += f"; {P['dom']} days on market vs. a {B['market']['median_dom']}-day median"
    due = deadline_label(C.get("deadline"))  # OFR-202: an ISO deadline reads like the report's other dates
    deadline = f" before {due}" if due else ""
    return {
        "outlook": br[1], "outlook_class": br[0], "competition": COMP_LABEL[lvl] + ("" if C.get("note") else " (Inferred)"),
        "why": why, "submit_by": due or "Before the listing agent's deadline", "signal": signal,
        "financing": fin_line(B), "financing_assumed": BU.get("financing_source") == "assumed",
        "limits": f"Max {money(BU['max_price'])} · cash {money(BU['cash_available'])} · keep {money(BU['reserve_floor'])}"
                  + (f" · ≤ ${BU['max_payment']:,}/mo" if BU.get("max_payment") else ""),
        "strength": rec["score"]["total"], "seller_net": money(rec["ns"]["net_adj"]), "worst_cash": money(rc["worst"]),
        "reserve_short": rc["reserve"] < BU["reserve_floor"],
        "reserve_status": reserve_status(B, rc["reserve"]),
        "terms": terms, "options": options, "bands": bands, "option_labels": [OPTION_LABEL[k] for k in O],
        # OFR-208: one option is "Your Offer", and each option that isn't offered says why
        "options_title": "Your Options" if len(O) > 1 else "Your Offer",
        "absent": [{"key": k, "option": OPTION_LABEL[k], "why": why_} for k, why_ in (r.get("absent") or {}).items()],
        "exposure": exposure, "constraints": r["constraints"], "preliminary": preliminary(r),
        "cautions": [r["reserve_tight"]] if r.get("reserve_tight") else [],  # OFR-338: within the limits, not a Limit line
        "breaks_limits": broken,
        "next_step": next_step(B, deadline, len(O)),
    }


def limits_broken(B, costs, t):
    """OFR-214: the buyer's limits the terms `t` would break, as [(key, words)]: max price, max payment, cash, reserve."""
    BU, c = B["buyer"], buyer_cash(B, t)
    out = []
    if t["price"] > BU["max_price"]:
        out.append(("max_price", f"your {money(BU['max_price'])} max price"))
    if BU.get("max_payment"):
        pay = monthly_payment(B, costs, t["price"])
        if pay > BU["max_payment"]:
            out.append(("max_payment", f"your ${BU['max_payment']:,}/mo payment limit (about ${pay:,}/mo)"))
    if c["reserve"] < 0:
        out.append(("cash", f"your {money(BU['cash_available'])} cash ({money(-c['reserve'])} short)"))
    elif c["reserve"] < BU["reserve_floor"]:
        out.append(("reserve_floor", f"your {money(BU['reserve_floor'])} reserve floor (leaves {money(c['reserve'])})"))
    return out


# The listing agent's likely counter, term by term, and the buyer's answer when it stays inside the buyer's limits
PUSHBACK_KEYS = {"Price": "price", "Seller Concessions": "seller_concessions", "Appraisal Gap Coverage": "appraisal_gap",
                 "Escrow Deposit": "deposit"}
RESP = {"Price": "Inside the value range; the appraisal won't support much more",
        "Seller Concessions": "These cover closing costs your cash can't; could trade part of them for price",
        "Escrow Deposit": "Can go higher: {deposit_refund} and adds no cost",
        "Inspection Period": "Needed for a full inspection; offer to share reports quickly",
        "Appraisal Gap Coverage": "Limited by your reserve; any more is your call",
        "Loan Approval": "Provide the full pre-approval letter", "Closing Date": "Match it if the lender confirms",
        "Buyer-Broker Compensation": "Per the buyer-broker agreement; discuss before submitting",
        "Home Warranty": "Already not requested", "Escrow / Title Agent": "Fine: seller's title company"}


def pushback(r):
    """OFR-214: the Likely Pushback rows on the recommended offer: [{term, yours, ask, response, breaks}]. An ask that
    would break one of the buyer's limits (price, payment, cash, reserve) is answered with that limit, by key."""
    B, costs, V = r["B"], r["costs"], r["B"]["value"]
    o, t = r["O"]["recommended"], r["terms"]["recommended"]
    ct = o.get("counter_terms") or {}
    # iteration 12: appraisal gap coverage is asked only for a price above the value range: the offer's own, or the
    # countered price when the buyer could take it (one that breaks a limit is held, so its gap never comes up)
    price_held = "price" in ct and bool(limits_broken(B, costs, dict(t, price=ct["price"])))
    final = t["price"] if price_held else ct.get("price", t["price"])
    no_gap = not V.get("assumed") and V.get("cma_high") is not None and final <= V["cma_high"]
    rows = []
    for term, yours, ask, _ in o.get("counter_rows") or []:
        if term == "Time for Acceptance" or term == "Appraisal Gap Coverage" and no_gap:
            continue
        key = PUSHBACK_KEYS.get(term)
        broken = limits_broken(B, costs, dict(t, **{key: ct[key]})) if key and key in ct else []
        if broken:
            resp = f"Hold at {yours}: {ask} would break " + " and ".join(w for _, w in broken)
        elif term == "Price" and V.get("assumed"):
            resp = "No value range yet: a buyer CMA would show whether more is supported"
        elif term == "Price" and t["price"] < V["cma_low"]:
            resp = f"Your call: {ask} is below the value range and inside your limits"
        else:
            resp = RESP.get(term, "Discuss with the buyer").format(**B["words"])
        if term == "Inspection Period":  # OFR-234: the engine's row, named as the contract names it
            term = B["words"]["inspection_label"]
        elif term == "Escrow Deposit":  # iteration 9 eval 3: likewise the deposit
            term = deposit_label(B)
        rows.append({"term": term, "yours": yours, "ask": ask, "response": resp, "breaks": [k for k, _ in broken]})
    return rows


def next_step(B, deadline, n_options=2):
    BU = B["buyer"]
    letter = "a pre-approval letter at the offer price (not your max, so it doesn't reveal your ceiling)"
    if BU["financing"] == "cash":
        todo = ("get the insurance quote and " if not quote_in_hand(BU) else "") + "have a current proof-of-funds statement ready"
    else:  # OFR-225: one "get", not two
        todo = "get " + ("the insurance quote and " if not quote_in_hand(BU) else "") + letter
    pick = "pick an option, " if n_options > 1 else ""
    txt = f"{pick}{todo}, and I'll prepare the offer package{deadline}."
    return txt[:1].upper() + txt[1:]  # OFR-225: a sentence after "Next Step:"


# --- offer package worksheet -------------------------------------------------------

# CR-7 riders by letter and the Florida Realtors addenda by form number (shared/references/farbar-riders.md, farbar-addenda.md)
FARBAR_RIDERS = {"fha_va": "FHA/VA Financing Rider (E)", "appraisal": "Appraisal Contingency Rider (F)",
                "hoa": "Homeowners' Association/Community Disclosure Rider (B)", "condo": "Condominium Rider (A)",
                "lead": "Lead-Based Paint Disclosure Rider (P)", "insurance": "Homeowner's/Flood Insurance Rider (H)",
                "sale": "Sale of Buyer's Property Rider (V)", "kickout": "Kick-Out Clause Rider (X)", "backup": "Back-Up Contract Rider (W)",
                "escalation": "Escalation Addendum (EAC-1)", "cdd": "Community Development District Addendum (CDDA-2)",
                "short_sale": "Short Sale Approval Contingency Rider (G)", "gap": "Appraisal Gap Addendum (AGA-1)",
                "bb_GG": "Seller's Agreement with Respect to Buyer's Broker Compensation Rider (GG)",
                "bb_FF": "Credit Related to Buyer's Broker Compensation Rider (FF)"}
# Any other contract: generic names; the appraisal protection's name comes from contract_forms.term_words (OFR-234)
GENERIC_RIDERS = {"fha_va": "FHA/VA Financing Addendum", "hoa": "HOA / Community Addendum",
                  "condo": "Condominium Addendum", "lead": "Lead-Based Paint Disclosure (Federal)", "insurance": "Insurance Contingency (if Your Forms Have One)",
                  "sale": "Sale of Buyer's Property Addendum", "kickout": "Kick-Out Clause", "backup": "Back-Up Contract Addendum",
                  "escalation": "Escalation Clause (Special Provisions, if Your Forms and the Listing Agent Allow It)",
                  "cdd": "Special District / Assessment Disclosure", "short_sale": "Short Sale Addendum"}
def blank(x):
    """A blank the agent must fill in (rendered red in the PDF)."""
    return f"[{x}]"


HOA_PERIODS = {"monthly": (1, "month"), "quarterly": (3, "quarter"), "semiannual": (6, "half-year"),
               "semi-annual": (6, "half-year"), "annual": (12, "year"), "annually": (12, "year"), "yearly": (12, "year")}


def hoa_dues(P):
    """Rider B's dues as the association bills them ("$105 per quarter"): `hoa_monthly` times the billing period in
    `hoa_frequency`; without a frequency, a blank for the billed amount beside the monthly figure."""
    m = P.get("hoa_monthly") or 0
    period = HOA_PERIODS.get(str(P.get("hoa_frequency") or "").strip().lower())
    if period:
        return f"{money(round(m * period[0]))} per {period[1]}"
    return f"{blank('amount and how often, as billed')} (about {money(m)}/mo)"


def para_key(row):
    """Contract entries in paragraph order: 1, 2, 2(a)…2(d), 3, 4… ("2(c) / 8" sorts as 2(c)); a row with no paragraph
    (another state's contract) keeps its place."""
    m = re.match(r"(\d+)(?:\(([a-z])\))?", str(row[0]))
    return (int(m.group(1)), m.group(2) or "") if m else (0, "")


def legal_entry(W):
    """Iteration 12: the worksheet's Legal Description / Parcel ID entry, both in the Enter column ("LOT 87 ... · Parcel
    ID 22-21-30-..."); a missing part prints as a red blank, never invented."""
    legal, pid = W.get("legal_description"), W.get("parcel_id")
    if not legal and not pid:
        return blank("from the county property appraiser")
    return f"{legal or blank('legal description')} · Parcel ID {pid or blank('from the county property appraiser')}"


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
    form = B["contract_form"]  # resolved once in prepare(), the same form the options were scored on
    farbar = form in cf.FARBAR
    terms = cf.terms(form, {"riders": [], "contract_name": W.get("contract_name")})  # ENG-11: the form's rules, one place
    fin = BU["financing"]
    financed = fin != "cash"
    price = t["price"]
    loan = round(price * (1 - BU["down_pct"])) if financed else 0
    eff = B["effective_date"]  # OFR-123: every date counts from the expected Effective Date
    close = oe.prior_weekday(eff + timedelta(days=t["closing_days"]) if t.get("closing_days") else o["close"])
    if farbar:
        form_name = cf.FORM_TITLES[form]
        form_why = ("Buyer may cancel for any reason during the inspection period; no seller repair obligation. Usual choice for competitive offers."
                    if terms["walkaway"] else "No inspection walk-away; the seller pays repairs up to the General Repair, WDO and "
                    "Permit Limits (Para. 9(a), 1.5% of price each if blank).")
    else:
        form_name = W.get("contract_name") or "Your state's standard residential purchase contract"
        form_why = "Paragraph numbers vary by form, so find each entry by its name and confirm the form version."
    offer_due = deadline_date(W.get("acceptance_deadline") or C.get("deadline"), B["analysis_date"])
    # OFR-123: the offer stays open past the listing agent's deadline, so the seller can answer (the Effective Date)
    accept = eff if dates.is_business_day(eff) else dates.next_business_day(eff)  # never a weekend or holiday 5:00 PM
    deadline = deadline_label(W.get("acceptance_deadline"), long=True) or (
        f"{accept:%B} {accept.day}, {accept.year}, 5:00 PM" if offer_due or not C.get("deadline") else None)
    para = (lambda p: p) if farbar else (lambda p: "")
    title_payer = costs.get("closing_costs.owner_title.payer")
    title_src = costs.described("closing_costs.owner_title.payer")
    reports = "4-point, wind mitigation" if costs.state == "FL" else "insurance"
    rows = [  # (paragraph, field, entry, note)
        (para("1"), "Buyer(s)", W.get("buyer_names") or blank("buyer names exactly as on pre-approval"), "Match the pre-approval letter"),
        (para("1"), "Seller(s)", blank("from listing / tax record"), ""),
        (para("1"), "Property Address", P.get("address") or blank("address"), ""),
        (para("1"), "Legal Description / Parcel ID", legal_entry(W), "Check against the county property appraiser's record"
         if W.get("legal_description") or W.get("parcel_id") else ""),
        (para("1"), "Personal Property Included", W.get("personal_property") or blank("items in MLS (range, refrigerator, washer/dryer…)"),
         "List anything the buyer expects to stay"),
        (para("2"), "Purchase Price", f"**{money(price)}**", ""),
        (para("2(a)"), "Initial Deposit",
         f"**{money(t['deposit'])}** within 3 days of Effective Date" if farbar else f"**{money(t['deposit'])}**",
         "" if farbar else "Due date per the contract"),
        (para("2(a)"), "Escrow Agent", W.get("escrow_agent") or blank("title company name, address, phone"), ""),
        (para("2(b)"), "Additional Deposit", "None", "Keep the full deposit up front: it scores better"),
    ]
    if financed:
        rows.append((para("2(c) / 8"), "Financing", f"**{oe.FIN_LABEL[fin]}** · loan {money(loan)} ({1 - BU['down_pct']:.1%} LTV)",
                     "As chosen by the buyer and lender" + (": confirm the loan type before entering" if BU.get("financing_source") == "assumed" else "")))
        rows.append((para("8(b)"), "Loan Approval Period", f"**{t.get('loan_approval_days', 30)} days**",
                     "Loan application within 5 days (form default)" if farbar else ""))
    else:
        rows.append((para("8"), "Financing", "**Cash** (no financing contingency)", "Attach proof of funds"))
    rows += [
        (para("2(d)"), "Balance to Close", f"{money(price - t['deposit'] - loan)} before prorations and costs", "Buyer's funds at closing"),
        (para("3"), "Time for Acceptance", deadline or blank("date and time"),
         "Past the offers-due deadline, so the seller has time to answer" if C.get("deadline") and not W.get("acceptance_deadline")
         else "The seller's deadline to accept"),
        # OFR-227: a lender who confirmed the financing (lender_called) hasn't confirmed this date; only
        # lender_confirmed_timeline does, and it ticks the checklist's closing box too
        (para("4"), "Closing Date", f"**{close:%B %-d, %Y}**",
         "Weekday; no lender to wait on" if not financed else "Weekday; lender confirmed this closing date"
         if BU.get("lender_confirmed_timeline") else "Weekday; lender confirmed the financing, not yet this date: confirm "
         "they can close by then" if BU.get("lender_called") else "Weekday; confirm the lender can close by then"),
        (para("6"), "Occupancy / Possession", "At closing, vacant", ""),
    ]
    if title_payer == "seller":
        rows.append((para("9"), "Title Evidence / Owner's Policy", "Seller designates title agent and pays owner's policy", f"Local custom ({title_src}); verify"))
    elif title_payer == "buyer":
        rows.append((para("9"), "Title Evidence / Owner's Policy", "Buyer designates title agent and pays owner's policy", f"Local custom ({title_src}); verify"))
    else:
        rows.append((para("9"), "Title Evidence / Owner's Policy", blank("who pays per local custom"), "Ask the title company"))
    rows += [
        (para("9"), "Seller-Paid Closing Costs", f"**{money(t['seller_concessions'])}** toward buyer's costs, prepaids and escrows"
         if t.get("seller_concessions") else "None", "Use the form's seller-contribution line if present, else Additional Terms"),
        (para("9"), "Home Warranty", "None (buyer may purchase separately)" if not t.get("home_warranty") else f"Seller pays up to {money(t['home_warranty'])}", ""),
        (para("9"), "Survey", "Buyer's expense (recommended)", "Lender may require"),
    ]
    rows.append((para("12"), B["words"]["inspection_label"], f"**{t['inspection_days']} days**",
                 f"Book the inspector{' and 4-point' if costs.state == 'FL' else ''} before submitting" if farbar else
                 "Book the inspector before submitting; find the contract's inspection or walk-away period and its notice rules"
                 + ("" if "inspection_days" in (B.get("overrides") or {}) else
                    "; the length is a generic default: confirm local practice")))  # OFR-315
    if terms["repairs_owed"]:
        lim = cf.repair_limits(price, {"repair_limits": B.get("repair_limits")})
        rows.append((para("9"), "Repair Limits", f"General **{money(lim['general'])}** · WDO **{money(lim['wdo'])}** · "
                     f"Permits **{money(lim['permit'])}**", "Para. 9(a); 1.5% of price each when left blank"))

    names = FARBAR_RIDERS if farbar else dict(GENERIC_RIDERS, appraisal=B["words"]["appraisal_addendum"])
    riders = []  # (name, inputs, why)
    yb, roof, fz = P.get("year_built"), P.get("roof_year"), (P.get("flood_zone") or "").upper()
    if fin in ("fha", "va"):
        # OFR-209: the Para. 2 cap on seller-paid appraisal repairs has no default (farbar-riders.md, Rider E)
        repair_cap = (f" · Para. 2 seller's cap for lender-required appraisal repairs: {blank('$ amount, no default')}"
                      if farbar else f" · seller's cap for lender-required repairs: {blank('$ amount')}")
        cap_note = ("; fill the repair cap on purpose: a blank is ambiguous, and "
                    + ("the contract owes no other repairs, so it's new exposure for the seller: tell the listing agent"
                       if not terms["repairs_owed"] else "it's in addition to the Para. 9(a) repair limits") if farbar else "")
        riders.append((names["fha_va"], f"Loan type: {fin.upper()} · appraised-value threshold: **{money(price)}**{repair_cap}",
                       "Required with FHA/VA loans (amendatory / escape clause)" + cap_note))
    # FAR/BAR: the Appraisal Gap Addendum is for conventional or cash offers and isn't used with the Appraisal Contingency
    # Rider (AGA-1's own instructions), so a gap offer uses AGA-1 and no rider F (appraisal_kind, the same rule scored).
    aga = appraisal_kind(B, t) == "aga"
    if aga:
        vd = aga_valuation(t, fin)  # OFR-106: filled so AGA-1's periods end with loan approval (cash: by closing)
        riders.append((names["gap"], f"Gap Amount: **{money(t['appraisal_gap'])}** · valuation within **{vd} days**"
                                     + (" (form default)" if vd == cf.AGA_VALUATION_DAYS else
                                        ", so it ends with loan approval" if financed else ", so it ends before closing")
                                     + " · 3 days to agree on new terms if the gap isn't enough",
                       "The buyer covers a low appraisal up to the gap; beyond it the contract ends unless both agree to new terms"))
    elif fin in ("conventional", "usda"):
        due = ("appraisal due: blank = **10 days before Closing**, buyer's notice within 3 days after" if farbar
               else f"appraisal period: **{t.get('appraisal_days', 21)} days**")
        riders.append((names["appraisal"], f"Value threshold: **{money(price)}** · {due}",
                       "Protects the buyer if the appraisal is low" + ("; pair with gap language below" if t.get("appraisal_gap") else "")))
    if (P.get("hoa_monthly") or 0) > 0 or W.get("hoa_name"):
        riders.append((names["hoa"], f"Association: {W.get('hoa_name') or blank('name')} · dues: {hoa_dues(P)} · "
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
    if not quote_in_hand(BU):
        ins_reason.append("no insurance quote yet")
    if ins_reason and financed:
        # iteration 11 eval 1: Rider H asks for a date with a form default, not an example (farbar-riders.md H)
        due = ("deadline date: blank = **the earlier of 30 days after the Effective Date or 10 days before Closing**"
               if farbar else f"days to obtain coverage: {blank('per your form')}")
        riders.append((names["insurance"], f"{due[:1].upper()}{due[1:]} · max acceptable premium: {blank('$/yr')}",
                       "Recommended: " + ", ".join(ins_reason) + ". Weakens the offer slightly; skip if a quote is already in hand"))
    if BU.get("needs_sale"):
        riders.append((names["sale"], f"Buyer's property: {blank('address')} · days: {blank('21 or fewer')}", "Weakens the offer; pair with a kick-out clause"))
        riders.append((names["kickout"], "Notice: 72 hours", "Lets the seller keep marketing"))
    if C.get("backup"):
        riders.append((names["backup"], "—", "Seller already has an accepted contract"))
    if t.get("escalation"):
        e = t["escalation"]
        # OFR-105: no promise of rising gap coverage; the package's gap is written at the cap's gap (build_offer)
        riders.append((names["escalation"], f"Increment: **{money(e['increment'])}** · cap: **{money(e['cap'])}** · "
                       f"redacted copy of the competing offer's price terms required",
                       "The cap is inside the value range, so the appraisal can support it" if e["cap"] <= B["value"]["cma_high"]
                       else f"Above the value range: the appraisal gap coverage ({money(t.get('appraisal_gap') or 0)}) is "
                            "written at the cap's gap, and the buyer's cash covers it with the reserve intact"))
    if P.get("cdd"):
        riders.append((names["cdd"], f"Annual amount: {blank('amount')} · outstanding debt: {blank('amount')}", "Property is in a special district"))
    if P.get("short_sale"):
        riders.append((names["short_sale"], f"Lender approval period: {blank('days')}", "Listed as a short sale"))
    if farbar and B.get("buyer_broker_form") and t.get("buyer_broker_pct"):
        bb = money(round(t["buyer_broker_pct"] * price))
        if bb_as_credit(B):
            riders.append((names["bb_FF"], f"Credit: **{t['buyer_broker_pct']:.2%}** of price ({bb}) · if over the lender's limit: "
                                           "balance paid by the seller directly to your brokerage (form default)",
                           "Counts toward the loan program's concession limit together with any closing-cost credit"))
        else:
            riders.append((names["bb_GG"], f"Compensation agreement ({bb}) signed by: {blank('seller or listing broker')} · "
                                           "within **3 days** (form default)",
                           "Paid as a commission, so it doesn't use the loan's concession room; have the agreement ready "
                           "to sign with the offer"))

    if farbar:  # numeric paragraph order (2(c), 2(d), 3, ... 8(b)), stable within a paragraph
        rows.sort(key=para_key)
    order = cf.rider_order([x[0] for x in riders])  # the forms' letter order: B, F, H, then GG; addenda after
    riders.sort(key=lambda x: order.index(x[0]))

    clauses = []
    if t.get("seller_concessions"):
        clauses.append(("Seller-Paid Closing Costs",
                        f"Seller shall pay up to {money(t['seller_concessions'])} toward Buyer's closing costs, prepaid items and escrows, as allowed by "
                        "Buyer's lender. Any amount not used shall not be paid to Buyer."))
    if financed and t.get("appraisal_gap") and not aga:
        rider = names["fha_va"] if fin in ("fha", "va") else names["appraisal"]
        # OFR-234: another contract's appraisal right lives in its own addendum, so the clause points to it generically
        rights = (f"Buyer's rights under the {rider}" if farbar or fin in ("fha", "va")
                  else "Buyer's appraisal rights under the contract and its addenda")
        clauses.append(("Appraisal Gap",
                        f"If the appraised value is less than the Purchase Price, Buyer shall pay in cash up to {money(t['appraisal_gap'])} of the "
                        f"difference between the appraised value and the Purchase Price. If the difference exceeds {money(t['appraisal_gap'])}, "
                        f"{rights} shall apply."))
    clauses.append(("Seller-Provided Reports",
                    f"Within 2 days after the Effective Date, Seller shall provide copies of any existing {reports} and inspection reports, "
                    "permits, and insurance claims history for the Property in Seller's possession."))
    if t.get("escalation") and not any(x[0] == names["escalation"] for x in riders):
        e = t["escalation"]
        clauses.append(("Escalation", f"Buyer will pay {money(e['increment'])} more than any bona fide competing offer, up to {money(e['cap'])}, "
                                      "upon receipt of a redacted copy of the competing offer's signature page and price terms, "
                                      "provided with the seller's authorization."))

    docs = ["Seller's property disclosure", "Permits and open-permit search", f"Existing inspection{', 4-point and wind mitigation' if costs.state == 'FL' else ''} reports",
            "Survey, if available"]
    fd = costs.get("flood.seller_disclosure")
    if fd:  # CMA-6: given at or before signing
        docs.insert(1, f"Seller's flood disclosure ({fd.get('statute', 'state form')}) and any flood claims")
    if finance.property_type(P.get("type")) == "condo":  # CMA-5
        docs.insert(1, "Condo documents: declaration, budget, financials, milestone inspection summary and SIRS, and "
                       "any special assessments")
    elif (P.get("hoa_monthly") or 0) > 0:
        docs.insert(1, "HOA documents, rules and estoppel")
    if yb and yb < 1978:
        docs.append("Lead-based paint records")
    if P.get("cdd"):
        docs.append("Special district information")

    CK = BU.get("checklist") or {}
    esc = t.get("escalation")  # letters and proof of funds cover the price the offer can reach (OFR-27)
    worst = (buyer_cash(B, dict(t, price=esc["cap"], appraisal_gap=esc.get("gap_at_cap", t.get("appraisal_gap", 0))))["worst"]
             if esc else r["cash"][variant]["worst"])
    fl = costs.state == "FL"
    # manual v5: FAR/BAR riders keep their CR-7 letter or form code ("Appraisal Contingency Rider (F)"), as in section 2;
    # another contract's generic names drop their parenthetical hints
    rider_list = ", ".join(x[0] if farbar else x[0].split(" (")[0] for x in riders) or "none"
    package = [  # (group, item, status, note)
        ("Contract", f"{terms['title'] if farbar else 'Contract'} completed and initialed on every page", CK.get("contract", "Pending"), ""),
        ("Contract", f"Riders attached and signed: {rider_list}", CK.get("riders", "Pending"), ""),
        ("Contract", "Additional terms reviewed by broker", CK.get("terms", "Pending"), ""),
        ("Buyer Docs", "Pre-approval letter at the offer price, not the max" if financed else "Proof of funds (recent statement in the buyer's name)",
         CK.get("pre_approval", "Pending"), (f"Letter at up to {money(esc['cap'])}, the escalation cap" if esc else
                                             f"Letter at {money(price)}") if financed else ""),
        ("Buyer Docs", ("Proof of funds for deposit, closing costs and appraisal gap" if t.get("appraisal_gap") else  # OFR-206
                        "Proof of funds for deposit and closing costs") if financed else "Source-of-funds note if the account is new",
         CK.get("funds", "Pending"), f"At least {money(worst)} available" + (" (at the escalation cap)" if esc else "")
         if financed else ""),
        ("Buyer Docs", "Homeowners insurance quote for this address", CK.get("insurance", "Yes" if quote_in_hand(BU) else "Pending"), "Before submitting"),
        ("Disclosures", "Brokerage relationship disclosure signed (transaction broker / single agent)" if fl else "Agency disclosure signed",
         CK.get("agency", "Pending"), "Florida requirement" if fl else "Per your state's rules"),
        ("Disclosures", "Buyer-broker agreement signed; compensation request matches", CK.get("bb", "Pending"),
         f"{t['buyer_broker_pct']:.1%} requested from seller" if t.get("buyer_broker_pct") else "No compensation requested from seller"),
        ("Disclosures", "Wire-fraud advisory acknowledged by buyer", CK.get("wire", "Pending"), "Deposit wiring instructions only by phone from the escrow agent"),
    ]
    if yb and yb < 1978:
        package.append(("Disclosures", "Lead-based paint disclosure", CK.get("lead", "Pending"), f"Required: built {yb}"))
    package += [
        ("Timing", f"Inspector{' and 4-point' if fl else ''} booked inside the {t['inspection_days']}-day {B['words']['inspection']}",
         CK.get("inspector", "Pending"), ""),
        # OFR-126: a call to the lender isn't a confirmed closing date: the box is the agent's to tick, or ticked when the
        # agent says the lender confirmed the timeline (OFR-227), matching the Closing Date note
        ("Timing", f"Lender confirms a {(close - eff).days}-day close" if financed else "Funds available by closing",
         CK.get("lender_close", "Yes" if financed and BU.get("lender_confirmed_timeline") else "Pending"), f"Closing {close:%b %-d}"),
        # OFR-206: a thing to leave out, so its box is never ticked (the renderer prints a cross, not a check)
        ("Do Not Include", "Personal letter, photos or buyer background", "Never", "Fair housing"),
    ]
    return {"variant": variant, "option": OPTION_LABEL[variant], "price": money(price), "farbar": farbar, "form_name": form_name, "form_why": form_why,
            "software": "Form Simplicity" if farbar else "your contract software",
            "rows": [{"para": a, "field": b, "entry": c, "note": d} for a, b, c, d in rows],
            "riders": [{"rider": a, "inputs": b, "why": c} for a, b, c in riders],
            "clauses": [{"title": a, "text": b} for a, b in clauses], "docs": docs,
            "package": [{"group": a, "item": b, "status": c, "note": d} for a, b, c, d in package],
            "blanks": sum(x.count("[") for x in [c for _, _, c, _ in rows] + [b for _, b, _ in riders])}


def side_by_side(r):
    """The options side by side, one row per term ({key, term, values}), then the payment row (key "payment", OFR-360):
    it follows from the terms, so the PDF never marks it amber as a term that differs."""
    B, O = r["B"], r["O"]
    rows = [{"key": key, "term": labl, "values": [term_val(key, r["terms"][k], B) for k in O]} for key, labl in term_keys(B)
            if not (key == "escalation" and not any(r["terms"][k].get("escalation") for k in O))
            and not (key in ("loan_approval_days", "appraisal_gap") and B["buyer"]["financing"] == "cash")]
    pay = "Est. Monthly Payment" + (" (Before Flood Insurance)" if B["flood"]["annual"] is None else "")
    return rows + [{"key": "payment", "term": pay, "values": [f"${r['payment'][k]:,}" for k in O]}]


def market_check(B):
    """OFR-359: the Market Check rows as [{label, value, note}], the same for the PDF and the markdown answer."""
    M, V = B["market"], B["value"]
    rows = [("Value Range", f'{money(V["cma_low"])}–{money(V["cma_high"])}' if not V.get("assumed") else "Not provided",
             V.get("source") if not V.get("assumed") else None),  # the source on its own line, so the range never wraps
            (stl_label(M), f'{M["sale_to_list"] * 100:.1f}%' if M.get("sale_to_list") else "—"),
            ("Months of Supply", M.get("months_supply") or "—"), ("Median Days on Market", M.get("median_dom") or "—"),
            ("Sales with Seller-Paid Buyer Costs", M.get("share_with_seller_costs") or "—"),
            ("Typical Seller-Paid Amount", M.get("typical_seller_paid") or "—"),
            ("Market Read", *market_read(B))]  # OFR-226: and why, in one sentence; manual v5: the market and this home apart
    if V.get("median_adjusted"):
        rows.insert(1, ("Median Adjusted Comp", money(V["median_adjusted"])))
    plan = B.get("cma_offer_plan") or {}
    if plan.get("target_low") and plan.get("target_high"):
        rows.append(("CMA Offer Plan", f'target {money(plan["target_low"])}–{money(plan["target_high"])}'
                     + (f' · walk away {money(plan["walk_away"])}' if plan.get("walk_away") else "")))
    return [{"label": m[0], "value": str(m[1]), "note": str(m[2]) if len(m) > 2 and m[2] else None} for m in rows]


def result(r, variant=None):
    s = summary(r)
    B = r["B"]
    V, M = B["value"], B["market"]
    to_confirm = [a for a in sorted(r["missing"], key=lambda a: (confirm_tier(a), oe.IMPACT_ORDER[a["impact"]],
                                                                 a["field"] not in OFFER_QUESTIONS))
                  if a["impact"] in ("high", "med")][:4]
    assumed = assumed_line(r, asked=to_confirm[:2])
    return {
        "ok": True, "property": B["property"].get("address") or "", "list_price": money(B["property"]["list_price"]),
        # OFR-356: null when no CMA gave a range (list price stands in for value), never "$429,000–$429,000"
        "value_range": None if V.get("assumed") else f"{money(V['cma_low'])}–{money(V['cma_high'])}", "summary": s,
        "side_by_side": side_by_side(r),
        "market_check": market_check(B),
        "market": {"sale_to_list": f"{M['sale_to_list'] * 100:.1f}%" if M.get("sale_to_list") else None,
                   "months_supply": M.get("months_supply"), "median_dom": M.get("median_dom"),
                   "median_adjusted": money(V["median_adjusted"]) if V.get("median_adjusted") else None, "read": market_read(B)[0],
                   "read_basis": market_read(B)[1]},
        "pushback": pushback(r),
        "worksheet": worksheet(r, variant),
        # OFR-212: what to ask first, in the order the chat's one question uses: the listing agent's competition read (the
        # most valuable input, offer-rules.md) when it was inferred, then the rest by impact. OFR-222: within an impact,
        # the questions that shape the offer itself (the contract form, escalation) come before cost details. OFR-244: a
        # weekday deadline that may already have passed comes right after the competition read
        "to_confirm": [a["why"] for a in to_confirm],
        # OFR-239: lines the chat reply carries outside its length cap ([{key, text}]); manual v5: `assumptions`, the
        # assumptions behind the numbers that the reply's question doesn't ask about, in one line
        "reply_lines": (r.get("reply_lines") or []) + ([{"key": "assumptions", "text": assumed}] if assumed else []),
        "assumptions": [{"impact": a["impact"], "where": a["scope"].title(), "what": a["why"]} for a in r["missing"]],
        "market_notes": list(r["costs"].notes),
        # chat only: the best-effort line for a contract that isn't FAR/BAR, worded for an offer being written (OFR-314)
        **cf.support([B["contract_form"]], drafting=True),
    }


def assumed_line(r, asked=()):
    """Manual v5: one line for the chat naming the assumptions the numbers rest on (closing costs, rate, insurance,
    flood, the acceptance date, the tax proration, the tax estimate), so the reply never leaves them out. The ones the
    reply's question already asks (`asked`, the first two of to_confirm) aren't repeated. None when nothing applies."""
    B, K = r["B"], r["costs"]
    skip = {(a["scope"], a["field"]) for a in asked}
    words = {
        "closing_cost_pct": lambda a: f"closing costs at {closing_cost_basis(B)}",
        "rate": lambda a: f"a {B['costs']['rate']:g}% rate (no lender quote)",
        "rate_source": lambda a: f"a {B['costs']['rate']:g}% rate (no lender quote)",
        "insurance_annual": lambda a: f"insurance at {money(B['costs']['insurance_annual'])}/yr (an estimate, not a quote)"
        if B["costs"].get("insurance_annual") else "an insurance estimate",
        "flood_insurance_annual": lambda a: "no flood insurance in the payment",
        "property_tax": lambda a: "an estimated property tax",
        "expected_effective_date": lambda a: f"acceptance on {B['effective_date']:%a %b} {B['effective_date'].day}",
        "current_tax_bill_paid": lambda a: "a tax proration that assumes the seller hasn't paid this year's bill",
    }
    out = []
    for a in r["missing"]:
        f = a["field"]
        if f in words and (a["scope"], f) not in skip:
            w = words[f](a)
            if w not in out:
                out.append(w)
    if not out:
        return None
    items = out[0] if len(out) == 1 else ", ".join(out[:-1]) + f"{',' if len(out) > 2 else ''} and {out[-1]}"
    return f"Assumed in these numbers: {items}."


def confirm_tier(a):
    """to_confirm's first sort key: the inferred competition read (0), a weekday deadline to confirm (1), the payment
    inputs when the payment limit sets the price (2), the rest (3)."""
    if (a["scope"], a["field"]) == ("competition", "level"):
        return 0
    # iteration 9 eval 1: when the payment limit sets the price, its rate and insurance come next: they move the cap
    return 1 if a["field"] == "deadline" else 2 if a.get("caps_price") else 3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("buyer")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--option", choices=list(OPTION_LABEL), help="option for the worksheet (default: the file's chosen_option)")
    a = ap.parse_args(argv)
    try:
        with open(a.buyer, encoding="utf-8") as f:
            data = json.load(f)
        r = analyze(data, cma=load_cma(data, a.cma))
        out = result(r, a.option)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
