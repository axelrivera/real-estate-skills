"""Seeded random buyer.json inputs for the generated tests (dev/tests/test_generated_buyer_offer_strategy.py).

    from generators import buyer_offer_strategy as gen
    data = gen.generate(7)            # the same buyer file for the same seed
    agent = gen.agent(7)              # an agent profile dict (none, short, or long names and disclaimers)
    data = gen.with_cma(data, h)      # the same buyer file with a buyer CMA's handoff in place of its value range

Every input is valid and realistic: cash, conventional (3% to 25% down), FHA, VA or USDA; a value range, a CMA handoff
(with an offer plan and its walk-away, market stats, insurance, millage, legal description) or neither; competition
from the only offer to cash or four or more, given or left to infer, with highest and best called or not; buyer limits
tight or loose (max price, payment, cash, reserve floor); HOA dues billed by the quarter or month, condos, CDDs, flood
zones, old roofs and pre-1978 homes (the riders contract_forms adds); the FAR/BAR AS IS or Standard form (with repair
limits), or another state's contract; overrides; the buyer's priority; weekday deadlines; long names. Text the model
would write is words only, as the skill requires. Mock data.
"""
import copy
import random
from datetime import date, timedelta

FL_PLACES = (("Casselberry", "Seminole", "32707"), ("Orlando", "Orange", "32806"), ("Miami", "Miami-Dade", "33130"),
             ("Palm Beach Gardens", "Palm Beach", "33418"), ("Tampa", "Hillsborough", "33602"), ("Oviedo", "Seminole", "32765"))
OTHER_PLACES = (("Austin", "Travis", "TX", "78757"), ("Marietta", "Cobb", "GA", "30060"), ("Phoenix", "Maricopa", "AZ", "85004"))
STREETS = ("Cypress Bend Dr", "Sample Kestrel Ct", "Heron Lake Dr", "Whispering Cypress Hammock Boulevard Building 4 Unit 1204",
           "Old Cedar Creek Plantation Parkway", "Elm St", "Bayview Ter")
BUYERS = ("Sample Buyer", "Dana Morgan and Lee Morgan",
          "Sample Buyer-Montgomery and Sample Co-Buyer-Vandersloot, as Joint Tenants with Right of Survivorship")
ESCROW = ("Sample Title Co. · (407) 555-0100",
          "Coldwater Bay Title Insurance Agency of the Palm Beaches, LLC · 4500 PGA Boulevard Suite 300 · (561) 555-0100")
DEADLINES = ("Friday 5 PM", "Mon 6pm", "2026-09-25 17:00", "Fri Sep 25 · 5 PM", None)
ANALYSIS = date(2026, 9, 23)


def _maybe(rng, p):
    return rng.random() < p


def generate(seed):
    rng = random.Random(seed)
    florida = rng.random() < 0.75
    if florida:
        city, county, zip_ = rng.choice(FL_PLACES)
        state = "FL"
    else:
        city, county, state, zip_ = rng.choice(OTHER_PLACES)
    lp = int(round(rng.choice((185_000, 329_000, 429_000, 615_000, 1_150_000)) * rng.uniform(0.9, 1.1), -3))
    P = {"address": f"{rng.randint(1, 19999)} {rng.choice(STREETS)}, {city}, {state} {zip_}", "list_price": lp}
    if _maybe(rng, 0.8):
        P.update(state=state, county=county)
    for k, v in (("beds", rng.randint(2, 5)), ("baths", rng.randint(1, 4)), ("sqft", rng.randint(900, 4200)),
                 ("year_built", rng.choice((1962, 1975, 1988, 1998, 2012, 2021))), ("roof_year", rng.choice((2004, 2010, 2016, 2023))),
                 ("dom", rng.choice((2, 9, 30, 78))), ("price_cuts", rng.choice((0, 0, 1, 2))), ("flood_zone", rng.choice(("X", "X", "AE")))):
        if _maybe(rng, 0.75):
            P[k] = v
    if _maybe(rng, 0.4):
        P["hoa_monthly"] = rng.choice((35, 120, 925))
        if _maybe(rng, 0.5):
            P["hoa_frequency"] = rng.choice(("monthly", "quarterly", "annual"))
    if _maybe(rng, 0.15):
        P["type"] = "condo"
    if florida and _maybe(rng, 0.15):
        P["cdd"] = True
        if _maybe(rng, 0.6):
            P["cdd_annual"] = rng.choice((900, 1450, 2200))
    if _maybe(rng, 0.5):
        P["annual_tax"] = int(lp * rng.uniform(0.012, 0.022))
    if _maybe(rng, 0.1):
        P["short_sale"] = True
    if _maybe(rng, 0.15):
        P["seller_flexible_close"] = True
    data = {"analysis_date": ANALYSIS.isoformat(), "property": P}
    if _maybe(rng, 0.65):
        lo = int(round(lp * rng.uniform(0.9, 1.0), -3))
        data["value"] = {"cma_low": lo, "cma_high": lo + int(round(lp * rng.uniform(0.03, 0.08), -3)),
                         "source": rng.choice(("buyer CMA", "the agent's CMA PDF"))}
        if _maybe(rng, 0.5):
            data["value"]["as_of"] = (ANALYSIS - timedelta(days=rng.randint(0, 6))).isoformat()
    if _maybe(rng, 0.6):
        data["market"] = {k: v for k, v in (("sale_to_list", rng.choice((0.95, 0.972, 0.99, 1.01))),
                                            ("months_supply", rng.choice((1.4, 2.8, 4.2, 7.5))),
                                            ("median_dom", rng.choice((12, 23, 45))),
                                            ("share_with_seller_costs", rng.choice((0.2, 0.44, 1.0))),
                                            ("typical_seller_paid", rng.choice((3000, 6500)))) if _maybe(rng, 0.7)}
    C = {}
    if _maybe(rng, 0.75):
        C["level"] = rng.choice((0, 1, 2, 3))
    if _maybe(rng, 0.5):
        C["note"] = rng.choice(("Listing agent: one other offer expected", "Listing agent: highest and best due Friday",
                                "Listing agent: no other offers yet"))
    dl = rng.choice(DEADLINES)
    if dl:
        C["deadline"] = dl
    if _maybe(rng, 0.1):
        C["backup"] = True
    data["competition"] = C
    if _maybe(rng, 0.6):
        data["listing_side"] = {"buyer_broker_offered_pct": rng.choice((0.02, 0.025, 0.03))}
        if _maybe(rng, 0.4):
            data["listing_side"]["listing_fee_pct"] = rng.choice((0.025, 0.03))
    fin = rng.choice(("cash", "conventional", "conventional", "fha", "va", "usda", None))
    BU = {"name": rng.choice(BUYERS)} if _maybe(rng, 0.7) else {}
    if fin:
        BU["financing"] = fin
        if fin == "conventional" and _maybe(rng, 0.85):
            BU["down_pct"] = rng.choice((0.03, 0.05, 0.10, 0.20, 0.25))
            BU["first_time_buyer"] = BU["down_pct"] < 0.05 or _maybe(rng, 0.3)
        elif fin == "fha":
            BU["down_pct"] = 0.035
    down = BU.get("down_pct", 1.0 if fin == "cash" else 0.05)
    tight = _maybe(rng, 0.4)
    if _maybe(rng, 0.85):
        BU["cash_available"] = int(round(lp * (down + rng.uniform(0.02, 0.06) if tight else down + rng.uniform(0.06, 0.2)), -3))
    if _maybe(rng, 0.7):
        BU["max_price"] = int(round(lp * (rng.uniform(0.94, 1.0) if tight else rng.uniform(1.0, 1.1)), -3))
    if _maybe(rng, 0.7):
        BU["reserve_floor"] = rng.choice((2000, 5000, 15000))
    if fin != "cash" and _maybe(rng, 0.5):
        BU["max_payment"] = int(round(lp * (0.0085 if tight else 0.012), -2))
    for k, v in (("approval", rng.choice(("preapproval", "du_approved", "full_uw"))), ("lender_called", True),
                 ("lender_confirmed_timeline", True), ("insurance_quote", rng.choice((True, False, "planned"))),
                 ("buyer_broker_agreement_pct", rng.choice((0.025, 0.03))),
                 ("needs_sale", True)):
        if _maybe(rng, 0.3 if k != "needs_sale" else 0.1):
            BU[k] = v
    if fin == "va" and _maybe(rng, 0.3):
        BU["va_later_use"] = True
    data["buyer"] = BU
    K = {}
    if _maybe(rng, 0.7):
        K["rate"] = rng.choice((6.1, 6.4, 6.875))
        if _maybe(rng, 0.4):
            K["rate_source"] = rng.choice(("Freddie Mac weekly 30-year average, week of Sep 17, 2026", "Lender quote"))
    if _maybe(rng, 0.5):
        K["insurance_annual"] = rng.choice((2900, 3900, 6100))
    if P.get("flood_zone") == "AE" and _maybe(rng, 0.5):
        K["flood_insurance_annual"] = rng.choice((1800, 2400))
    if not florida and _maybe(rng, 0.5):
        K["tax_rate"] = rng.choice((0.0198, 0.011))
    data["costs"] = K
    W = {}
    if florida:
        form = rng.choice(("as_is", "as_is", "standard", None))
        if form:
            W["contract_form"] = form
        if form == "standard" and _maybe(rng, 0.4):
            W["repair_limits"] = {"general": 5000}
        if _maybe(rng, 0.2):
            W["buyer_broker_form"] = "FF"
    elif _maybe(rng, 0.6):
        W["contract_name"] = rng.choice(("TREC One to Four Family Residential Contract", "GAR Purchase and Sale Agreement"))
    for k, v in (("buyer_names", BU.get("name") or rng.choice(BUYERS)), ("escrow_agent", rng.choice(ESCROW)),
                 ("legal_description", "Lot 87, Sample Oaks Unit 2, according to the plat recorded in Plat Book 12, Page 34"),
                 ("parcel_id", "22-21-30-5AB-0000-0870"), ("hoa_name", "Sample Oaks Homeowners Association, Inc."),
                 ("personal_property", "Range, refrigerator, dishwasher, washer, dryer")):
        if _maybe(rng, 0.5):
            W[k] = v
    data["worksheet"] = W
    if _maybe(rng, 0.15):
        data["overrides"] = {k: v for k, v in (("price", int(round(lp * rng.uniform(0.95, 1.02), -3))),
                                               ("inspection_days", rng.choice((7, 10, 15))),
                                               ("deposit", int(round(lp * 0.02, -2)))) if _maybe(rng, 0.6)}
    if _maybe(rng, 0.2):
        data["chosen_option"] = rng.choice(("recommended", "stronger", "lower_cost"))
    if _maybe(rng, 0.5):  # the buyer's priority (strategy.BUYER_PRIORITIES); left out, balanced
        data["buyer_priority"] = rng.choice(("win", "balanced", "protect_cash"))
    if _maybe(rng, 0.3):
        data["sample"] = True
    return data


def with_cma(data, h):
    """The buyer file for the home a buyer CMA's handoff describes: the handoff in place of the value range and market
    stats, the address and list price from it."""
    d = copy.deepcopy(data)
    d.pop("value", None)
    d.pop("market", None)
    s = h.get("subject") or {}
    d["property"] = {k: v for k, v in d["property"].items() if k in ("type", "cdd", "cdd_annual", "short_sale")}
    d["property"].update(address=f"{s.get('address')}, {s.get('city') or 'Oviedo'}, FL", list_price=s["list_price"])
    for k in ("max_price", "cash_available", "max_payment"):
        d["buyer"].pop(k, None)
    d["cma"] = h
    return d


def agent(seed):
    """An agent profile as profiles.load_agent returns it: none, a short one, or a long one with a long disclaimer."""
    rng = random.Random(seed * 7919 + 3)
    pick = rng.random()
    if pick < 0.25:
        return {}
    if pick < 0.7:
        return {"name": "Jordan Avery", "brokerage": "Sample Realty, LLC", "license": "SL0000001",
                "disclaimers": "Information deemed reliable but not guaranteed."}
    para = ("Information deemed reliable but not guaranteed. All measurements and figures should be independently "
            "verified. Each office is independently owned and operated. ")
    return {"name": "Maximiliana Alexandra Montgomery-Vandersloot, REALTOR, GRI, ABR, SRS",
            "team": "The Montgomery-Vandersloot Luxury Waterfront and Golf Community Team",
            "brokerage": "Coldwater Bay International Realty and Relocation Partners of Central Florida, LLC",
            "license": "SL1234567", "disclaimers": "\n\n".join([para] * rng.randint(1, 3))}
