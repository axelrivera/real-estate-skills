"""Seeded random listing.json inputs for the generated tests (dev/tests/test_generated_seller_offer_review.py).

    from generators import seller_offer_review as gen
    data = gen.generate(7)            # the same input for the same seed
    agent = gen.agent(7)              # an agent profile dict (none, short, or long names and disclaimers)
    data2 = gen.step2(data, 7)        # the same listing a step later: a counter back, a new offer, a lapse

Every input is valid and realistic: one to six offers (cash, FHA, VA, USDA, conventional), escalations financed or paid
in cash, the Appraisal Gap Addendum, riders that fit the form (contract_forms' rules: K or L on the Standard form, none
of I, K, L on AS IS), backups, a call for highest and best pending or passed, offers whose time for acceptance has
lapsed, a CMA range or none, a payoff or none, the seller's priority and counter stances, long names and brokerages, and
other states on their own contracts.
Text the model would write (labels, priority notes, contract issues) is words only, as the skill requires. Mock data.
"""
import copy
import random
from datetime import date, timedelta

FL_PLACES = (("Longwood", "Seminole"), ("Miami", "Miami-Dade"), ("Fort Lauderdale", "Broward"), ("Tampa", "Hillsborough"),
             ("Orlando", "Orange"), ("Naples", "Collier"), ("Palm Beach Gardens", "Palm Beach"), ("Lakeland", "Polk"))
OTHER_PLACES = (("Austin", "Travis", "TX"), ("Marietta", "Cobb", "GA"), ("Charlotte", "Mecklenburg", "NC"),
                ("Phoenix", "Maricopa", "AZ"))
STREETS = ("Heron Lake Dr", "Sable Palm Way", "Oak Hollow Ct", "Whispering Cypress Hammock Boulevard Building 4 Unit 1204",
           "Old Cedar Creek Plantation Parkway", "Elm St", "Bayview Ter")
AGENTS = ("J. Morales", "L. Park", "Ana de la Cruz", "Tom Hill Jr.", "Kendall Castellanos-Whitfield",
          "Maximiliana Alexandra Castellanos-Whitfield-Vandersloot", "R. Diaz", "M. Lee", "Priya Natarajan", "Chen Wu")
FIRMS = ("Keller Williams", "Coldwell Banker", "eXp Realty", "Independent",
         "Tidewater Key International Realty and Relocation Partners of the Palm Beaches, LLC",
         "Sunward Homes Realty of the Palm Beaches", "Compass", "LPT Realty, LLC")
SELLERS = ("Sample Seller", "Dana Morgan",
           "Sample Seller-Hollingsworth, Trustee of the Hollingsworth-Vandermeer Family Revocable Living Trust")
LENDERS = ("Chase", "Guild Mortgage", "Local credit union", "Rocket Mortgage")
TERMS = ("Refrigerator, washer and dryer stay", "Seller to leave the pool equipment", "Occupancy at closing")
ISSUES = (("High", "The second buyer named in paragraph 1 hasn't initialed every page.",
           "Get the second buyer's initials on every page.", "terms"),
          ("Med", "The deposit receipt names a different escrow agent than the contract.",
           "Ask the buyer's agent which escrow agent holds the deposit.", "terms"),
          ("Low", "The rider checklist and the attached riders disagree on Rider B.",
           "Have both sides initial the corrected checklist.", "riders"))
ANALYSIS = date(2026, 9, 23)
STANCES = ("firm", "meet_partway", "terms_only")  # counter.stance (shared/offer_engine.COUNTER_STANCES)
STANCE_REASONS = ("The seller would rather keep this buyer than hold out on price.",
                  "Showings are steady and the seller is in no hurry, so the price holds.",
                  "The price is close enough; the inspection and deposit terms matter more to the seller.")


def _when(d, hour=17, minute=0):
    return f"{d.isoformat()} {hour:02d}:{minute:02d}"


def offer(rng, i, lp, florida, cma_high):
    o = {"id": "ABCDEF"[i], "status": "active"}
    fin = rng.choice(("cash", "conventional", "conventional", "fha", "va", "usda"))
    o["financing"] = fin
    o["price"] = int(round(lp * rng.uniform(0.92, 1.05), -3))
    if rng.random() < 0.85:
        o["buyer_agent"] = rng.choice(AGENTS)
        o["buyer_brokerage"] = rng.choice(FIRMS)
    if fin == "conventional":
        o["down_pct"] = rng.choice((0.05, 0.1, 0.2, 0.25))
    elif fin == "fha":
        o["down_pct"] = 0.035
    if fin != "cash":
        o["approval"] = rng.choice(("preapproval", "du_approved", "full_uw", "prequal"))
        o["lender"] = rng.choice(LENDERS)
        o["lender_called"] = rng.random() < 0.4
        o["loan_approval_days"] = rng.choice((21, 25, 30, 45))
        if rng.random() < 0.3:
            o["approval_max_price"] = o["price"] + rng.choice((0, 5000, -3000))
    else:
        o["approval"] = rng.choice(("pof_verified", "none"))
        if rng.random() < 0.5:
            o["proof_of_funds"] = int(o["price"] * rng.uniform(0.9, 1.3))
    if rng.random() < 0.85:
        o["deposit"] = int(round(o["price"] * rng.choice((0.005, 0.01, 0.03, 0.1)), -2))
    o["seller_concessions"] = rng.choice((0, 0, 0, 3000, 8000, 15000))
    if rng.random() < 0.7:
        o["buyer_broker_pct"] = rng.choice((0.02, 0.025, 0.03))
    if florida:
        form = rng.choice(("as_is", "as_is", "standard", None))
        if form:
            o["contract_form"] = form
        riders = []
        if form == "standard" and rng.random() < 0.5:
            riders.append(rng.choice(("K", "L")))
        if fin in ("fha", "va"):
            riders.append("E")
        if rng.random() < 0.2:
            o["sale_contingency_days"] = rng.choice((21, 30, 45))
            riders.append("V")
            if rng.random() < 0.5:
                riders.append("X")
        if rng.random() < 0.15 and o.get("buyer_broker_pct"):
            riders.append("GG")
            o["compensation_agreement"] = rng.choice(("received", "signed_by_buyer_broker"))
        if "GG" in riders or rng.random() < 0.8:  # a compensation agreement status needs Rider GG listed
            o["riders"] = riders
        if fin in ("conventional", "cash") and rng.random() < 0.25:
            o["addenda"] = ["Appraisal Gap Addendum (AGA-1)"]
            o["appraisal_gap"] = rng.choice((5000, 10000, 20000))
        if rng.random() < 0.3:
            o["title_by"] = rng.choice(("seller", "buyer"))
    else:
        o["contract_form"] = rng.choice(("TREC One to Four Family Residential Contract", "GAR Purchase and Sale Agreement"))
        o["inspection_walkaway"] = rng.random() < 0.7
    if fin == "conventional" and "appraisal_gap" not in o and rng.random() < 0.3:
        o["appraisal_gap"] = rng.choice((5000, 10000))
    if rng.random() < 0.8:
        o["inspection_days"] = rng.choice((7, 10, 15))
    if rng.random() < 0.8:
        o["closing_date"] = (ANALYSIS + timedelta(days=rng.randint(21, 70))).isoformat()
    else:
        o["closing_days"] = rng.choice((30, 35, 45))
    if rng.random() < 0.75:
        o["expires"] = _when(ANALYSIS + timedelta(days=rng.randint(-2, 3)), rng.choice((9, 12, 17, 20)))
    if rng.random() < 0.2:
        o["escalation"] = {"cap": o["price"] + rng.choice((10000, 20000, 30000)), "increment": rng.choice((1000, 2000, 5000)),
                           "proof": "redacted copy"}
        if florida and o.get("contract_form"):
            o["escalation"]["contract_form"] = o["contract_form"]
        if fin != "cash" and rng.random() < 0.5:
            o["escalation"]["paid_in_cash"] = rng.random() < 0.5
    if rng.random() < 0.15:
        o["rent_back_days"], o["rent_back_monthly"] = rng.choice((7, 14, 30)), rng.choice((0, 1500))
    if rng.random() < 0.2:
        o["other_terms"] = rng.choice(TERMS)
    if rng.random() < 0.15:
        sev, issue, fix, check = rng.choice(ISSUES)
        o["contract_issues"] = [{"sev": sev, "issue": issue, "fix": fix, "check": check}]
    if i and rng.random() < 0.1:
        o["contract_issues"] = [{"sev": "Blocking", "issue": "Page three of the contract is missing.",
                                 "fix": "Ask the buyer's agent for the complete contract.", "check": "signed"}]
    if rng.random() < 0.3:  # the agent's counter stance, with its reason (needed when it isn't the suggested one)
        o["counter"] = {"stance": rng.choice(STANCES), "stance_reason": rng.choice(STANCE_REASONS)}
    if rng.random() < 0.3:
        o["agent_track"] = rng.choice(("strong", "average", "weak"))
    if rng.random() < 0.3:
        o["insurance_quote"] = rng.choice((True, False, "planned"))
    return o


def generate(seed):
    rng = random.Random(seed)
    florida = rng.random() < 0.75
    if florida:
        city, county = rng.choice(FL_PLACES)
        state, zip_ = "FL", "32750"
    else:
        city, county, state = rng.choice(OTHER_PLACES)
        zip_ = "78701"
    lp = int(round(rng.choice((185_000, 325_000, 425_000, 689_000, 1_250_000)) * rng.uniform(0.9, 1.1), -3))
    L = {"address": f"{rng.randint(1, 19999)} {rng.choice(STREETS)}, {city}, {state} {zip_}", "state": state,
         "county": county, "list_price": lp}
    for k, v in (("beds", rng.randint(2, 5)), ("baths", rng.randint(1, 4)), ("sqft", rng.randint(900, 4200)),
                 ("year_built", rng.choice((1962, 1978, 1988, 2004, 2019))), ("roof_year", rng.choice((2005, 2012, 2021))),
                 ("flood_zone", rng.choice(("X", "AE")))):
        if rng.random() < 0.7:
            L[k] = v
    if rng.random() < 0.5:
        L["hoa_monthly"] = rng.choice((0, 85, 210, 540))
        if L["hoa_monthly"] and rng.random() < 0.2:
            L["hoa_conflict"] = [{"amount": L["hoa_monthly"], "per": "quarter"}, {"amount": L["hoa_monthly"], "per": "month"}]
    if rng.random() < 0.15:
        L["property_type"] = "condo"
    cma = rng.random() < 0.6
    if cma:
        L["cma_low"], L["cma_high"] = int(round(lp * 0.95, -3)), int(round(lp * rng.uniform(0.99, 1.04), -3))
    if rng.random() < 0.6:
        L["annual_tax"] = int(lp * rng.uniform(0.012, 0.022))
    n = rng.choice((1, 1, 2, 3, 4, 5, 6))
    if n > 1 and rng.random() < 0.3:
        L["highest_and_best_due"] = _when(ANALYSIS + timedelta(days=rng.choice((-2, 0, 1, 2))), rng.choice((12, 17)))
    S = {"name": rng.choice(SELLERS), "priority": rng.choice(("balanced", "price", "certainty", "speed"))}
    if rng.random() < 0.6:
        S["payoff"] = int(round(lp * rng.uniform(0.1, 0.8), -2))
    if rng.random() < 0.6:
        S["listing_fee_pct"] = rng.choice((0.025, 0.03))
    if rng.random() < 0.5:
        S["offered_buyer_broker_pct"] = 0.025
        if S.get("listing_fee_pct"):
            S["listing_fee_includes_buyer_broker"] = False
    if rng.random() < 0.5:
        S["deadline"] = (ANALYSIS + timedelta(days=rng.randint(30, 75))).isoformat()
    if rng.random() < 0.3:
        S["priority_note"] = rng.choice(("Close before the deadline; certainty over top dollar", "Top dollar matters most"))
    offers = [offer(rng, i, lp, florida, L.get("cma_high", lp)) for i in range(n)]
    if n > 2 and rng.random() < 0.3:
        offers[-1]["status"] = rng.choice(("backup", "declined"))
    data = {"analysis_date": ANALYSIS.isoformat(), "listing": L, "seller": S, "offers": offers}
    if rng.random() < 0.3:
        data["sample"] = True
    if n > 1 and rng.random() < 0.2:
        data["ranking_reason"] = "Strongest financing and the shortest inspection period."
    return data


def step2(data, seed):
    """The same listing a step later (a second render): the first offer counters back, a new offer arrives, or a time
    for acceptance lapses."""
    rng = random.Random(seed * 31 + 7)
    d = copy.deepcopy(data)
    what = rng.choice(("counter", "new", "lapse"))
    o = d["offers"][0]
    if what == "counter":
        o["prior_counters"] = [{"by": "seller", "price": d["listing"]["list_price"], "inspection_days": 7}]
        o["price"] = int(round((o["price"] + d["listing"]["list_price"]) / 2, -3))
    elif what == "new" and len(d["offers"]) < 6:
        d["offers"].append(offer(rng, len(d["offers"]), d["listing"]["list_price"], d["listing"]["state"] == "FL",
                                 d["listing"].get("cma_high", d["listing"]["list_price"])))
    else:
        o["expires"] = _when(ANALYSIS - timedelta(days=1))
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
