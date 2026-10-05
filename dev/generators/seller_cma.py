"""Seeded random seller-cma inputs for the generated tests (dev/tests/test_generated_seller_cma.py).

    sys.path.insert(0, "dev/generators"); import seller_cma as gen
    R = gen.generate(7, out_dir)     # report.json as a dict; writes the MLS export it names into out_dir
    gen.agent(7)                     # an agent profile dict (none, short, or long names and disclaimers)

Each seed builds a synthetic MLS export in the Stellar CMA columns: sales over about six months with a market split
(the recent ones a little lower or higher), active, pending and expired listings, prices from about $180,000 to
$1,800,000, long street and subdivision names. From that export it picks 3 to 6 comps and adjusts them as an agent
would (size, condition, pool, lot), sets the time adjustment by the method's rule from the export's split, and a range
the shared range rule accepts. The pricing options are standard (top of range, recommended, competing offer), a reprice
(Stay at Current Price, then cuts) or a relist (the failed price caps the options, two or three of them). The costs vary:
a stated payoff, a loan balance, no mortgage or none given; a tax bill with closings across the year end; an HOA or
none; Florida or another state. About half carry the deck's wording. Every judgment field is figure-free, as the skill
requires. Mock data only; nothing here asserts anything: the test does.
"""
import copy
import csv
import math
import os
import random
import statistics
import sys
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "dev", "tests"))
from skill_import import load  # noqa: E402

_MODS = {}


def _compute():
    """The seller CMA's compute module, loaded once without clashing with another skill's compute.py."""
    if "compute" not in _MODS:
        (_MODS["compute"],) = load("seller-cma", "compute")
    return _MODS["compute"]


COLUMNS = ["Distance", "ML Number", "Status", "Address", "Legal Subdivision Name", "Heated Area", "Current Price",
           "Close Price", "Close Date", "Original List Price", "Contract Date", "Beds", "Full Baths", "Year Built",
           "Pool", "CDOM", "Seller Paid Buyer Costs", "Lot Size Acres", "Sold Terms", "Property Style",
           "Flood Zone Code", "Public Remarks"]
FL = (("Oviedo", "Seminole", "Oviedo"), ("Casselberry", "Seminole", "Casselberry"),
      ("Altamonte Springs", "Seminole", "Altamonte Springs"), ("Orlando", "Orange", None), ("Kissimmee", "Osceola", None))
OTHER = (("Austin", "Travis", "TX"), ("Marietta", "Cobb", "GA"), ("Phoenix", "Maricopa", "AZ"))
STREETS = ("Oak Hollow Ct", "Wren Hollow Ln", "Sample Heron Ln", "Bayview Ter", "Elm St", "Larkspur Way", "Tallow Ct",
           "Whispering Cypress Hammock Boulevard", "Old Cedar Creek Plantation Parkway", "Kestrel Point Ct",
           "Saint Augustine Grass Court Northeast", "Quillwood Dr", "Primrose Ln", "Birchcrest St")
SUBDIVISIONS = ("Fernwood Park", "Kestrel Point", "Cattail Crossing", "Spring Oaks Unit Two Replat at Hickorywood Estates",
                "The Reserve at Whispering Cypress Hammock Phase Three", "Elm Grove", "Bayview Terrace")
ZONES = ("X", "X", "X (lower risk)", "AE", "X500", "To confirm")
WHY = ("The closest sales nearby, adjusted to your home, center near where we recommend listing.",
       "The market cooled since spring: buyers negotiate again, and many sellers help with buyer costs.",
       "Well-priced homes nearby are going under contract fast; overpriced ones are sitting and cutting their price.",
       "The most recent sales landed lower than the spring ones, so a price near the middle of the range gives the "
       "home its best first weeks and keeps the appraisal in reach.")
MEANS = ("<strong>Expect to negotiate.</strong> Recent buyers paid less than the original asking price and many asked the "
         "seller to cover part of their closing costs.",
         "<strong>The first three weeks matter most.</strong> A new listing gets its biggest wave of showings right away.",
         "<strong>Watch the appraisal.</strong> A contract well above the supported range invites a low appraisal.",
         "<strong>Documentation is worth money.</strong> Permits and dates turn updates from claims into value.")
BULLETS = ("A close match in condition and size, sold in the same market.", "The seller paid part of the buyer's costs, "
           "which comes off the price.", "Its larger lot backs onto conservation, which buyers pay more for.",
           "Original kitchen and baths, so it's adjusted up for the updates this home has.",
           "Sold in the spring, when rates were lower and homes were moving faster.")
NOTES = ("Updated kitchen, same size, no pool.", "Larger but dated. Cut once already and still sitting.",
         "Renovated and went under contract within days.", "Original condition; the price leaves room for a remodel.",
         "A light fixer on a busy road with an oversized lot that backs onto the community's retention pond and trail.")
PREP = (("Document the roof", "Roof age decides whether a buyer can insure the home.", "Permit and date, ready to share", "roof"),
        ("Get the inspections", "A pre-listing inspection plus four-point and wind-mitigation reports.",
         "Pre-listing, four-point and wind-mitigation reports", "inspection"),
        ("Gather the permits", "Kitchen, bath, electrical and plumbing work.", "Kitchen, baths, electrical, plumbing", "permit"),
        ("Check the public record", "The county record matches the bedrooms and baths we advertise.",
         "The county record matches what we advertise", "document"),
        ("Decide on a seller-credit budget", "Most recent sales included one.", "Decide it now, before offers arrive", "money"),
        ("Agree on a review point", "Steady showings but no offer means we revisit the price.",
         "Steady showings but no offer? Revisit the price", "calendar"),
        ("Make it easy to show and keep the home ready for short-notice showings in the first weeks",
         "Short-notice showings bring the most buyers through early.", "Short-notice showings in the first weeks", "showings"))
NEEDS = ("The roof permit and replacement date, plus any wind-mitigation report.",
         "The age of the AC, water heater and pool equipment.", "Copies of any permits for the remodel work.",
         "Anything you know that affects the home's value or condition, such as past leaks, insurance claims or repairs.",
         "Your mortgage payoff statement, so we can turn the net estimates into cash at closing.",
         "When you would like to close, and whether the home will be occupied or vacant during showings.")


def money_cell(v):
    return f"${v:,.0f}" if v else ""


def us(d):
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def home_row(rng, status, price, sqft, close=None, sub="", address=None, pool=None, paid=0, original=None):
    return {"Distance": f"{rng.uniform(0.05, 1.4):.2f}", "ML Number": f"O{rng.randint(6400000, 6499999)}",
            "Status": status, "Address": address, "Legal Subdivision Name": sub.upper(), "Heated Area": str(sqft),
            "Current Price": money_cell(price), "Close Price": money_cell(price) if status == "SLD" else "",
            "Close Date": us(close) if close else "", "Original List Price": money_cell(original or price),
            "Contract Date": us(close - timedelta(days=30)) if close else "",
            "Beds": str(max(1, round(sqft / 550))), "Full Baths": str(max(1, round(sqft / 900))),
            "Year Built": str(rng.randint(1960, 2022)), "Pool": "Private" if pool else "None",
            "CDOM": str(rng.randint(2, 120)), "Seller Paid Buyer Costs": money_cell(paid),
            "Lot Size Acres": f"{rng.uniform(0.1, 0.6):.2f}", "Sold Terms": rng.choice(("Conventional", "Cash", "FHA")),
            "Property Style": "Single Family Residence", "Flood Zone Code": "X", "Public Remarks": "Mock listing."}


def export(rng, as_of, split, subject):
    ppsf, sqft, sub = subject["ppsf"], subject["sqft"], subject["subdivision"]
    drift = rng.choice((-0.04, -0.02, 0.0, 0.02))
    rows, used = [], {subject["mls_address"]}

    def addr():
        while True:
            a = f"{rng.randint(10, 9999)} {rng.choice(STREETS).upper()}"
            if a not in used:
                used.add(a)
                return a
    start = split - timedelta(days=rng.randint(100, 170))
    for _ in range(rng.randint(12, 36)):
        close = start + timedelta(days=rng.randint(0, (as_of - start).days - 3))
        size = max(600, round(sqft * rng.uniform(0.75, 1.25)))
        factor = (1 + drift) if close >= split else 1.0
        price = round(size * ppsf * rng.uniform(0.88, 1.12) * factor, -2)
        ratio = rng.uniform(0.93, 1.01) * (1 + drift if close >= split else 1)
        rows.append(home_row(rng, "SLD", price, size, close, sub, addr(), pool=rng.random() < 0.5,
                             paid=rng.choice((0, 0, 3000, 8000, round(price * 0.02, -2))), original=round(price / ratio, -2)))
    for status, n in (("ACT", rng.randint(2, 12)), ("PNC", rng.randint(0, 4)), ("EXP", rng.randint(0, 3))):
        for _ in range(n):
            size = max(600, round(sqft * rng.uniform(0.65, 1.4)))
            price = round(size * ppsf * rng.uniform(0.88, 1.15), -2)
            rows.append(home_row(rng, status, price, size, None, sub, addr(), pool=rng.random() < 0.5,
                                 original=round(price * rng.uniform(1.0, 1.08), -2)))
    rng.shuffle(rows)
    return rows


def time_rate(st):
    early = st["sold_early"].get("median_sale_to_original_list")
    recent = st["sold_recent"].get("median_sale_to_original_list")
    if early is None or recent is None or st["sold_early"]["n"] < 5 or st["sold_recent"]["n"] < 5:
        return None, None
    pts = abs(recent - early) * 100
    if pts < 1:
        return None, None
    return (0.01 if pts <= 3 else 0.02), ("rising" if recent > early else "falling")


def generate(seed, out_dir):
    compute = _compute()
    cma, mls, profiles = compute.cma, compute.mls, compute.profiles
    rng = random.Random(seed)
    as_of = date(2026, 8, 20) + timedelta(days=rng.randint(0, 120))  # late summer to mid-December: year-end closings
    split = as_of - timedelta(days=rng.randint(60, 100))
    florida = rng.random() < 0.75
    if florida:
        city, county, district = rng.choice(FL)
        state = "FL"
    else:
        (city, county, state), district = rng.choice(OTHER), None
    price = int(round(math.exp(rng.uniform(math.log(180_000), math.log(1_800_000))), -3))
    ppsf = rng.uniform(170, 600)
    sqft = max(800, round(price / ppsf))
    sub = rng.choice(SUBDIVISIONS)
    number, street = rng.randint(10, 99999), rng.choice(STREETS)
    pool = rng.random() < 0.5
    subject = {"ppsf": price / sqft, "sqft": sqft, "subdivision": sub, "mls_address": f"{number} {street.upper()}"}
    rows = export(rng, as_of, split, subject)
    path = os.path.join(out_dir, "export.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    market = profiles.load_market(state=state, county=county, mls="Stellar")
    homes = mls.load(path, market)
    mls.fill_distances(homes, subject["mls_address"])
    st = mls.market_stats(homes, {"address": subject["mls_address"], "living_area": sqft, "private_pool": pool,
                                  "subdivision": sub}, split_date=split.isoformat(), as_of=as_of.isoformat(),
                          exclude_address=subject["mls_address"])
    rate, direction = time_rate(st)
    sold = sorted((h for h in homes if h["status"] == "SOLD"), key=lambda h: abs(h["living_area"] - sqft))
    picks = sold[:rng.randint(3, min(6, len(sold)))]
    scale = price / 450_000
    cards = []
    for h in picks:
        adj = []
        diff = sqft - h["living_area"]
        if diff:
            adj.append({"label": "Size", "amount": round(max(-0.05 * h["close_price"], min(0.05 * h["close_price"],
                                                                                          diff * 75 * scale)), -2)})
        if h["private_pool"] != pool:
            adj.append({"label": "Pool", "amount": round((25000 if pool else -25000) * scale, -2)})
        if rng.random() < 0.5:
            adj.append({"label": rng.choice(("Renovation", "Partial Update vs. Full Renovation", "Kitchen Only")),
                        "amount": round(rng.choice((15000, 30000, -15000, 40000)) * scale, -2)})
        if rng.random() < 0.2:
            adj.append({"label": rng.choice(("Larger Corner Lot", "Pond Lot", "Documented Recent Systems")),
                        "amount": round(-rng.choice((5000, 10000)) * scale, -2)})
        cards.append({"address": cma.display_address(h["address"]), "sold_price": h["close_price"],
                      "seller_concessions": h.get("seller_paid") or 0, "adjustments": adj,
                      "bullets": rng.sample(BULLETS, rng.randint(1, 3))})
    comps = {"cards": cards, "intro": "The closest matches in size and condition, including the ones that argue for a "
                                      "lower price.",
             "method_note": "Condition adjustments are based on listing descriptions, so they are judgment calls.",
             "lean": "The range leans on the most recent sales and the best condition matches."}
    if rate:
        comps["time_adjustment"] = {"rate_per_quarter": rate, "prices": direction}
    # the adjusted values, as the skill sees them before setting the range
    tmp = copy.deepcopy(comps)
    cma.apply_time_adjustments(tmp, homes, as_of.isoformat(), split)
    cma.derive_comps(tmp)
    values = [c["adjusted"] for c in tmp["cards"]]
    low, high = cma.passing_range(values, market)
    median = statistics.median(values)
    rec = min(max(math.floor(median / 5000) * 5000 - 100, low + 100 if low + 100 <= high else low), high)
    step = max(5000, int(round(price * 0.02, -3)))
    kind = rng.choice(("standard", "standard", "reprice", "relist"))
    credit = lambda: rng.choice((0, 3000, 5000, 10000))  # noqa: E731
    times = ("2–4 months", "45–90 days", "3–6 weeks", "1–3 weeks", "6–10 weeks")
    strategies = [{"list_price": rec + step, "time": rng.choice(times[:2]), "seller_credit": credit(),
                   "note": "Tests the top of the range; likely needs a price cut before an offer"},
                  {"list_price": rec, "time": times[2], "seller_credit": credit(),
                   "note": "Priced near the middle of recent adjusted sales; room to negotiate"},
                  {"list_price": rec - step, "time": times[3], "seller_credit": credit(),
                   "note": "Aims for competing offers; depends on them showing up"}]
    R = {"prepared_date": as_of.isoformat(), "as_of": as_of.isoformat(), "export": path, "split_date": split.isoformat(),
         "subject": {"address": f"{number} {street}", "mls_address": subject["mls_address"], "city": city, "state": state,
                     "county": county, "locality": f"{city}, {state} {rng.randint(32000, 34999)} · {sub} · {county} County",
                     "sqft": sqft, "beds": max(2, round(sqft / 550)), "baths": rng.choice((2, 2.5, 3)),
                     "year_built": rng.randint(1958, 2020), "pool": pool, "subdivision": sub.upper(),
                     "property_type": "single_family",
                     "facts": [["Lot", "0.24 acre"], ["Built", "Block"], ["Pool", "Private" if pool else "None"],
                               ["Garage", "Two-car attached"], ["Flood Zone", rng.choice(ZONES)],
                               ["Recent Updates", "Kitchen, baths, floors"]],
                     "summary": "An updated home with a remodeled kitchen and new flooring, as described by you."},
         "summary_page": {"headline": "Priced where recent sales support, for the strongest first weeks on the market.",
                          "why": rng.sample(WHY, 3), "next_step": "Review this plan together, sign the listing "
                                                                  "agreement, and get the home ready to go live."},
         "recommendation": {"list_price": rec, "low": low, "high": high,
                            "why": "It leaves room for the negotiating that is normal now and looks fairly priced in its "
                                   "first weeks on the market."},
         "means": rng.sample(MEANS, rng.randint(2, 4)), "comps": comps,
         "competition": {"intro": "The homes buyers will tour alongside yours.", "rows": []},
         "market": {"bullets": ["<strong>Buyers are negotiating again.</strong> Homes take longer to go under contract.",
                                "<strong>Timing.</strong> Fewer buyers shop over the holidays."]},
         "pricing": {"intro": "Realistic options, each an estimate from recent sales.", "recommended_index": 1,
                     "competing_offer_upside": True, "strategies": strategies,
                     "note": "The competing-offer option depends on competing offers showing up."},
         "costs": {}, "buyer_payment": {"rate": round(rng.uniform(5.6, 7.6), 2), "loan_type": rng.choice(("conventional", "fha")),
                                        "down_pct": rng.choice((0.035, 0.05, 0.1, 0.2))},
         "prep": {"intro": "These steps cost little and remove the questions that slow buyers down.",
                  "items": [dict(zip(("step", "detail", "short", "icon"), p)) for p in rng.sample(PREP, rng.randint(5, 7))]},
         "needs": rng.sample(NEEDS, rng.randint(4, 6))}
    if kind == "reprice":  # the agent's own listing: Stay at Current Price, then cuts
        current = rec + step
        strategies[0].update(note="Has sat without an offer at this price", time=rng.choice(("2–4 months", "6–10 weeks")))
        R["reprice"] = {"current_price": current, "days_on_market": rng.randint(30, 120)}
        if rng.random() < 0.5:
            R["reprice"]["original_price"] = current + step
    elif kind == "relist":  # the failed price caps the options: two or three of them
        days = rng.randint(40, 200)
        if rng.random() < 0.5:
            R["relist"] = {"failed_price": rec + step, "status": "expired", "days_on_market": days}
        else:
            strategies.pop(0)
            R["pricing"]["recommended_index"] = 0
            R["relist"] = {"failed_price": rec + rng.choice((0, 1000)), "status": rng.choice(("expired", "withdrawn")),
                           "days_on_market": days}
        if rng.random() < 0.5:
            R["relist"]["original_price"] = R["relist"]["failed_price"] + step
    if rng.random() < 0.3:
        R["listing_history"] = [{"status": "expired", "price": round(price * 0.6, -3), "original_price": round(price * 0.63, -3),
                                 "ended": f"{rng.randint(2012, 2020)}-0{rng.randint(1, 9)}", "days_on_market": rng.randint(60, 200)}]
    if rng.random() < 0.3:
        R["launch_date"] = (as_of + timedelta(days=rng.randint(5, 40))).isoformat()
    costs = R["costs"]
    if rng.random() < 0.6:
        costs.update(listing_fee_pct=rng.choice((0.025, 0.0275, 0.03)), buyer_broker_fee_pct=rng.choice((0.02, 0.025, 0)))
    payoff = rng.choice(("payoff", "balance", "none", "free"))
    if payoff == "payoff":
        costs["mortgage_payoff"] = round(price * rng.uniform(0.2, 0.7), -2)
    elif payoff == "balance":
        costs["mortgage_balance"] = round(price * rng.uniform(0.2, 0.7), -2)
        if rng.random() < 0.5:
            costs["mortgage_rate"] = round(rng.uniform(2.75, 7.5), 2)
    elif payoff == "free":
        costs["mortgage_balance"] = 0
    if rng.random() < 0.7:
        costs["annual_tax"] = round(price * rng.uniform(0.008, 0.02), 2)
        if rng.random() < 0.6:
            costs["expected_closing_date"] = (as_of + timedelta(days=rng.randint(45, 140))).isoformat()
        if rng.random() < 0.15:
            costs["current_tax_bill_paid"] = True
    if rng.random() < 0.35:
        costs.update(hoa=True, hoa_monthly=rng.choice((35, 120, 420)))
    if rng.random() < 0.2:
        costs["other"] = [{"label": "Home Warranty", "amount": 600}]
    bp = R["buyer_payment"]
    if florida and district and rng.random() < 0.6:
        bp["district"] = district
    else:
        bp.update(school_mills=round(rng.uniform(4, 7), 3), total_mills=round(rng.uniform(11, 21), 4))
    if rng.random() < 0.5:
        bp["insurance_annual"] = round(price * rng.uniform(0.006, 0.012), -2)
    if rng.random() < 0.5:
        bp["rate_week"] = (as_of - timedelta(days=5)).isoformat()
    actives = [h for h in homes if h["status"] in ("ACTIVE", "PENDING", "EXPIRED")]
    for h in rng.sample(actives, min(len(actives), rng.randint(3, 8))):
        R["competition"]["rows"].append([cma.display_address(h["address"]), {"ACTIVE": "For sale", "PENDING": "Under contract"}
                                         .get(h["status"], "Expired"), h["current_price"], int(h["living_area"]),
                                         "Yes" if h["private_pool"] else "No", h.get("days_on_market") or rng.randint(1, 200),
                                         rng.choice(NOTES)])
    plotted = [c["address"] for c in cards] + [r[0] for r in R["competition"]["rows"] if r[1] == "For sale"]
    R["scatter"] = {"subject_label_pos": rng.choice(("left", "right", "above", "below")),
                    "callouts": [{"address": a, "side": rng.choice(("left", "right", "above", "below"))}
                                 for a in rng.sample(plotted, min(len(plotted), rng.randint(0, 2)))],
                    "takeaway": "The renovated sales sit above the line, and the dated ones below it."}
    if not florida:
        R["mls"] = "Stellar"
    if rng.random() < 0.5:
        R["deck"] = deck_content(rng, R)
    if rng.random() < 0.3:
        R["sample"] = True
    return R


def deck_content(rng, R):
    rows = R["competition"]["rows"]
    return {
        "recommendation_why": "It sits where recent sales support and gives you the strongest launch.",
        "value_drivers": [["Updated Kitchen and Baths", "The biggest adjustment against the dated sales.", "kitchen"],
                          ["Two-Car Garage", "Storage buyers compare closely.", "garage"],
                          ["No Monthly Association Costs", "A lower payment for a buyer.", "home"]][:rng.randint(2, 3)],
        "document_items": [["The Roof", "Permit and date. Roof age decides whether a buyer can insure the home.", "roof"]]
        if rng.random() < 0.6 else [],
        "comp_lines": {c["address"]: rng.choice(("Same street; updated", "Larger lot; older roof", "")) for c in R["comps"]["cards"]},
        "comps_basis": "size, pool, age and neighborhood",
        "comps_takeaway": "The recent sales point to the middle of the range.",
        "scatter_takeaway": "The updated sales sit above the trend, and yours sits among them.",
        "market_takeaway": "Buyers are negotiating again. Price for the market we have now.",
        "competition": [[r[0], "A home buyers will tour alongside yours."] for r in rows[:rng.randint(1, min(3, len(rows)))]],
        "competition_takeaway": "Well-priced homes are moving. Overpriced ones sit.",
        "strategy_takeaway": "The nets are close. The real choice is time and risk.",
        "payment_takeaway": "Buyers shop by payment.",
        "needs_short": ["Roof permit and date", "Ages of the AC and water heater", "Your mortgage payoff statement"],
        "timeline": [["now", "Sign the listing agreement; order the inspections"],
                     ["before", "Photos, documents and a final pricing review"],
                     ["after", "Price review if steady showings bring no offer"]][:rng.randint(1, 3)],
        "notes": {"recommendation": "Lead with the answer.", "nets": "The appendix has every line."},
    }


def agent(seed):
    """An agent profile as profiles.load_agent returns it: none, a short one, or a long one with a long disclaimer."""
    rng = random.Random(seed * 7919 + 5)
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
            "license": "SL1234567", "phone": "(407) 555-0142", "email": "agent@example.com",
            "disclaimers": "\n\n".join([para] * rng.randint(1, 3))}
