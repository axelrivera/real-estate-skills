"""Seeded random net-sheet.json inputs for the generated tests (dev/tests/test_generated_seller_net_sheet.py).

    from generators import seller_net_sheet as gen
    data = gen.generate(7)            # the same input for the same seed
    agent = gen.agent(7)              # an agent profile dict (short or long names, a disclaimer or none)

Every input is valid and realistic: one to three prices from starter homes to estates, Florida counties (built-in
costs) and other states (national estimates, a deal's own transfer tax), long names and labels, closings at the edges
of the year, payoffs from none to more than the price (a short sale), statement balances, several other payoffs and
costs, assumed dates and property types, and optional fields left out. Labels are names, never figures (the skill
refuses a figure in a label). Mock data only.
"""
import random
from datetime import date, timedelta

FL_PLACES = (("Oviedo", "Seminole"), ("Casselberry", "Seminole"), ("Miami", "Miami-Dade"), ("Lakeland", "Polk"),
             ("Palm Beach Gardens", "Palm Beach"), ("Tampa", "Hillsborough"), ("Orlando", "Orange"),
             ("Naples", "Collier"), ("Jacksonville", "Duval"), ("Sarasota", "Sarasota"))
OTHER_PLACES = (("Austin", "Travis", "TX"), ("Marietta", "Cobb", "GA"), ("Charlotte", "Mecklenburg", "NC"),
                ("Phoenix", "Maricopa", "AZ"), ("Denver", "Denver", "CO"), ("Columbus", "Franklin", "OH"),
                ("Nashville", "Davidson", "TN"), ("Boise", "Ada", "ID"))
STREETS = ("Oak Hollow Ct", "Wren Hollow Ln", "Pine Hollow Rd", "Sample Heron Ln", "Bayview Ter",
           "Whispering Cypress Hammock Boulevard Building 4", "Old Cedar Creek Plantation Parkway", "Elm St")
SCENARIO_LABELS = ("Current List Price", "After a Price Cut", "List Price with Credit", "Planned List Price",
                   "Lower Price", "Full Price with a Seller Credit and Home Warranty",
                   "Current List Price, As Is with No Seller Help", "After the Planned Fall Price Reduction",
                   "Aggressive Price", "Quick Sale", "Recommended List Price")
COST_LABELS = ("Survey", "Permit Closeout", "Attorney Fee", "Final Water and Sewer Bill Holdback",
               "Condominium Association Estoppel Certificate and Rush Fee", "Pest Inspection",
               "Wind Mitigation Report", "Code Violation Lien Release")
PAYOFF_LABELS = ("Home Equity Line", "Solar Lease Buyout", "Second Mortgage",
                 "Home Equity Line of Credit with Second Lender", "Property Tax Lien", "Solar Panel Loan")
NAMES = ("Dana Morgan", "Robin Example", "Sample Seller",
         "Sample Seller-Hollingsworth and Sample Co-Seller-Vandermeer, Trustees")
TYPES = ("single_family", "condo", "townhouse", "multifamily", "land", None)


def _maybe(rng, p, value):
    return value if rng.random() < p else None


def _closing(rng):
    """Any day of 2026 or 2027, weighted to the year's edges (late-year bills, New Year rollovers)."""
    if rng.random() < 0.4:
        return rng.choice((date(2026, 12, 31), date(2027, 1, 2), date(2026, 11, 30), date(2026, 10, 15),
                           date(2026, 3, 31), date(2026, 1, 2)))
    return date(2026, 1, 1) + timedelta(days=rng.randint(0, 729))


def generate(seed):
    rng = random.Random(seed)
    florida = rng.random() < 0.6
    if florida:
        city, county = rng.choice(FL_PLACES)
        state = "FL"
    else:
        city, county, state = rng.choice(OTHER_PLACES)
    base = rng.choice((95_000, 180_000, 315_000, 450_000, 689_000, 1_250_000, 3_400_000))
    base = round(base * rng.uniform(0.8, 1.2), -3)
    kind = rng.choice(TYPES)
    prop = {"address": f"{rng.randint(1, 99999)} {rng.choice(STREETS)}" + (" #1204" if kind == "condo" and rng.random() < 0.5 else ""),
            "city": city, "county": county, "state": state}
    if kind:
        prop["property_type"] = kind
        if rng.random() < 0.2:
            prop["property_type_assumed"] = True
    hoa = rng.choice((None, True, False))
    if hoa is not None:
        prop["hoa"] = hoa
    if hoa or (kind == "condo" and rng.random() < 0.7):
        prop["hoa_monthly"] = rng.choice((0, 45, 85, 240, 740, 1_925))

    n = rng.choice((1, 2, 3, 3))
    labels = rng.sample(SCENARIO_LABELS, n)
    scenarios = []
    for i in range(n):
        x = {"price": base if i == 0 else round(base * rng.uniform(0.9, 1.05), -3)}
        if rng.random() < 0.6:
            x["label"] = labels[i]
        if rng.random() < 0.3:
            x["seller_credit"] = rng.choice((1_500, 4_000, 9_000, 12_000, 25_000))
        if rng.random() < 0.2:
            x["home_warranty"] = rng.choice((450, 550, 650))
        if rng.random() < 0.2:
            x["repairs"] = rng.choice((800, 1_500, 3_500, 12_750))
        if rng.random() < 0.15:
            x["closing_date"] = _closing(rng).isoformat()
            x["closing_date_assumed"] = rng.random() < 0.5
        scenarios.append(x)

    costs = {}
    if rng.random() < 0.7:
        costs["listing_fee_pct"] = rng.choice((0.02, 0.025, 0.0275, 0.03, 0.035))
        costs["buyer_broker_fee_pct"] = rng.choice((0, 0.02, 0.025, 0.03))
    payoff = rng.random()
    if payoff < 0.45:
        costs["mortgage_payoff"] = round(base * rng.uniform(0.1, 1.15), -2)  # a short sale now and then
    elif payoff < 0.6:
        costs["mortgage_balance"] = round(base * rng.uniform(0.2, 0.9), -2)
        if rng.random() < 0.5:
            costs["mortgage_rate"] = rng.choice((3.25, 4.5, 6.25, 7.125))
    elif payoff < 0.7:
        costs["mortgage_payoff"] = 0
    if rng.random() < 0.3:
        costs["other_payoffs"] = [{"label": lbl, "amount": rng.choice((7_300, 14_000, 18_000, 28_000))}
                                  for lbl in rng.sample(PAYOFF_LABELS, rng.randint(1, 2))]
    if rng.random() < 0.75:
        costs["annual_tax"] = round(base * rng.uniform(0.008, 0.024), -1)
    if rng.random() < 0.2:
        costs["current_tax_bill_paid"] = rng.random() < 0.5
    if rng.random() < 0.15:
        costs["tax_bill_due_date"] = rng.choice(("10-15", "11-15", "2026-12-01"))
    if rng.random() < 0.35:
        costs["other"] = [{"label": lbl, "amount": rng.choice((300, 375, 450, 549, 800, 1_250))}
                          for lbl in rng.sample(COST_LABELS, rng.randint(1, 3))]
    if not florida and rng.random() < 0.5:
        costs["transfer_tax_rate"] = rng.choice((0.001, 0.002, 0.004))
        costs["transfer_tax_label"] = "State Transfer Tax"

    data = {"property": prop, "scenarios": scenarios, "costs": costs}
    if rng.random() < 0.8:
        data["prepared_date"] = rng.choice(("2026-09-26", "2026-10-01", "2026-12-31", "2027-01-02"))
    if rng.random() < 0.6:
        data["prepared_for"] = rng.choice(NAMES)
    closing = _maybe(rng, 0.85, _closing(rng))
    if closing:
        data["closing_date"] = closing.isoformat()
        data["closing_date_assumed"] = rng.random() < 0.3
    if rng.random() < 0.1:
        data["foreign_seller"] = True
    if rng.random() < 0.3:
        data["sample"] = True
    return data


def agent(seed):
    """An agent profile as profiles.load_agent returns it: none, a short one, or a long one with a long disclaimer."""
    rng = random.Random(seed * 7919 + 1)
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
            "license": "SL1234567", "disclaimers": "\n\n".join([para] * rng.randint(1, 4))}
