"""Seeded random buyer-cma inputs for the generated tests (dev/tests/test_generated_buyer_cma.py).

    sys.path.insert(0, "dev/generators"); import buyer_cma as gen
    R = gen.generate(7, out_dir)     # report.json as a dict; writes the MLS export it names into out_dir
    gen.agent(7)                     # an agent profile dict (none, short, or long names and disclaimers)

Each seed builds a synthetic MLS export in the Stellar CMA columns (dev/fixtures/buyer-cma's CSVs): sales over about
six months with a market split, active, pending and expired listings, the subject's own active row and sometimes its
sale years ago, prices from about $150,000 to $2,000,000, condos and single-family homes, HOA or none, flood zones from
X to VE, long street and subdivision names. From that export it picks 3 to 8 comps and adjusts them as an agent would
(size, pool, lot; a condition level for the home and each comp, with the agent's condition values now and then and
always outside Florida), sets the time adjustment by the method's rule from the export's split (none, 1% or 2% a
quarter), runs the comps-only stage for the adjusted values and the script's range (now and then the agent's own
range_override instead), an offer posture (any of the four, or left out for the suggested one; now and then the
agent's plan_override), a listing history across years (relists, cuts, increases, failed contracts, off-market
stretches), taxes, payment and credit offers (credits only: the script prices them from the opening). Every judgment field is figure-free, as the skill requires. Mock data only; nothing here
asserts anything: the test does.
"""
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
    """The buyer CMA's compute module, loaded once without clashing with another skill's compute.py."""
    if "compute" not in _MODS:
        (_MODS["compute"],) = load("buyer-cma", "compute")
    return _MODS["compute"]

COLUMNS = ["Distance", "ML Number", "Status", "Address", "Legal Subdivision Name", "Heated Area", "Current Price",
           "Close Price", "Close Date", "Original List Price", "Contract Date", "Beds", "Full Baths", "Year Built",
           "Pool", "CDOM", "Seller Paid Buyer Costs", "Lot Size Acres", "Sold Terms", "Property Style",
           "Flood Zone Code", "Public Remarks"]
FL = (("Oviedo", "Seminole"), ("Casselberry", "Seminole"), ("Orlando", "Orange"), ("Winter Park", "Orange"),
      ("Kissimmee", "Osceola"), ("Lakeland", "Polk"), ("Deland", "Volusia"))
OTHER = (("Austin", "Travis", "TX"), ("Marietta", "Cobb", "GA"), ("Phoenix", "Maricopa", "AZ"), ("Columbus", "Franklin", "OH"))
STREETS = ("Oak Hollow Ct", "Wren Hollow Ln", "Sample Heron Ln", "Bayview Ter", "Elm St", "Larkspur Way", "Tallow Ct",
           "Whispering Cypress Hammock Boulevard", "Old Cedar Creek Plantation Parkway", "Kestrel Point Ct",
           "Saint Augustine Grass Court Northeast", "Quillwood Dr", "Primrose Ln", "Birchcrest St")
SUBDIVISIONS = ("Fernwood Park", "Kestrel Point", "Cattail Crossing", "Spring Oaks Unit Two Replat at Hickorywood Estates",
                "The Reserve at Whispering Cypress Hammock Phase Three", "Elm Grove", "Bayview Terrace")
STYLES = ("Single Family Residence", "Condominium", "Townhouse")
ZONES = ("X", "X", "X", "AE", "X500", "VE", "AH", "To confirm")
WHY = ("The closest sales, adjusted to this home, center near the middle of the range.",
       "The market cooled since early in the year: homes now sell under their original asking price, and many sellers help with "
       "buyers' costs.", "Time on the market and repeated price cuts give you room to negotiate price or a seller credit.",
       "The most recent sales landed lower than the earlier ones, which supports an opening near the bottom of the range "
       "and a patient negotiation over the inspection period.")
CHECKS = (("The Roof", "Get the permit, the final inspection and any warranty"),
          ("Original Systems", "AC, water heater and pool equipment ages"),
          ("Remodel Permits", "Kitchen, baths and any plumbing or electrical work"),
          ("The Failed Contract", "Ask why it fell apart and for any inspection reports from that buyer"),
          ("Association Documents", "Budget, reserves, special assessments and the rules on leasing"))
NOTES = ("Updated kitchen, same size, no pool.", "Larger but dated. Cut once already and still sitting.",
         "Renovated and went under contract within days.", "Original condition; the price leaves room for a remodel.",
         "Remodeled, larger lot, no pool.", "Same floor plan nearby. It started higher and never sold.",
         "A light fixer on a busy road with an oversized lot that backs onto the community's retention pond.")
BULLETS = ("A close match in condition and size, sold in the same market.", "The seller paid part of the buyer's costs, "
           "which comes off the price.", "Its larger lot backs onto conservation, which buyers pay more for.",
           "Original kitchen and baths, so it's adjusted up for the updates this home has.",
           "Sold earlier in the year, when rates were lower and homes were moving faster.")
WATCH = ("<strong>The roof.</strong> Roof age is the biggest factor in insuring a Florida home, so we want the permit "
         "and date in writing.", "<strong>Original systems.</strong> If the AC and water heater are original, insurers "
         "ask about both.", "<strong>Permits for the renovation.</strong> Confirm the kitchen, bath and any electrical or "
         "plumbing work was permitted.", "<strong>As-Is doesn't mean no inspection.</strong> If the offer is written on "
         "the As-Is contract, you still get an inspection period.")
POSTURES = ("leverage", "standard", "competitive", "must_win")
POSTURE_REASONS = ("The buyer's lease ends soon, so the plan weighs winning the home over the last dollar.",
                   "The buyer can wait for the right home, so there is no reason to stretch on this one.",
                   "This is the floor plan the buyer has been waiting for, and similar homes have gone quickly.",
                   "The home has sat while similar listings sold around it, which gives the buyer room.")
OVERRIDE_REASON = "The agent set these from a conversation with the listing agent about where the seller will move."
QUESTIONS = ("When was the roof replaced, and can you share the permit?", "How old are the AC and the water heater?",
             "Were the kitchen and bath updates permitted?", "Is the seller open to contributing toward the buyer's "
             "closing costs?", "Has any buyer inspected the home, and did any report lead to the price cuts?")


def money_cell(v):
    return f"${v:,.0f}" if v else ""


def us(d):
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def home_row(rng, status, price, sqft, close=None, sub="", address=None, mls_no=None, dist=None, style=STYLES[0],
             pool=None, year=None, paid=0, original=None, dom=None, zone="X"):
    return {"Distance": f"{dist if dist is not None else rng.uniform(0.05, 1.4):.2f}",
            "ML Number": mls_no or f"O{rng.randint(6400000, 6499999)}", "Status": status,
            "Address": address or f"{rng.randint(10, 9999)} {rng.choice(STREETS).upper()}",
            "Legal Subdivision Name": sub.upper(), "Heated Area": str(sqft),
            "Current Price": money_cell(price), "Close Price": money_cell(price) if status == "SLD" else "",
            "Close Date": us(close) if close else "", "Original List Price": money_cell(original or price),
            "Contract Date": us(close - timedelta(days=30)) if close else "",
            "Beds": str(max(1, round(sqft / 550))), "Full Baths": str(max(1, round(sqft / 900))),
            "Year Built": str(year or rng.randint(1960, 2022)), "Pool": "Private" if pool else "None",
            "CDOM": str(dom if dom is not None else rng.randint(2, 120)), "Seller Paid Buyer Costs": money_cell(paid),
            "Lot Size Acres": f"{rng.uniform(0.1, 0.6):.2f}" if style != "Condominium" else "",
            "Sold Terms": rng.choice(("Conventional", "Cash", "FHA", "VA")), "Property Style": style,
            "Flood Zone Code": zone if zone != "To confirm" else "", "Public Remarks": "Mock listing."}


def export(rng, as_of, split, subject):
    """[row dicts] for the CSV: sales before and after the split (the recent ones a little lower or higher), the
    listings, the subject's own active row and sometimes its old sale."""
    ppsf, sqft, sub, style = subject["ppsf"], subject["sqft"], subject["subdivision"], subject["style"]
    drift = rng.choice((-0.04, -0.02, 0.0, 0.01, 0.03))  # the market's change at the split
    rows, used = [], {subject["mls_address"]}

    def addr():
        while True:
            a = f"{rng.randint(10, 9999)} {rng.choice(STREETS).upper()}"
            if a not in used:
                used.add(a)
                return a
    start = split - timedelta(days=rng.randint(100, 170))
    for _ in range(rng.randint(12, 40)):
        close = start + timedelta(days=rng.randint(0, (as_of - start).days - 3))
        size = max(500, round(sqft * rng.uniform(0.7, 1.3)))
        factor = (1 + drift) if close >= split else 1.0
        price = round(size * ppsf * rng.uniform(0.85, 1.15) * factor, -2)
        ratio = rng.uniform(0.93, 1.02) * (1 + drift if close >= split else 1)
        rows.append(home_row(rng, "SLD", price, size, close, sub, addr(), style=style, pool=rng.random() < 0.5,
                             paid=rng.choice((0, 0, 3000, 8000, round(price * 0.02, -2))), original=round(price / ratio, -2),
                             zone=rng.choice(ZONES[:5])))
    for status, n in (("ACT", rng.randint(2, 14)), ("PNC", rng.randint(0, 4)), ("EXP", rng.randint(0, 3))):
        for _ in range(n):
            size = max(500, round(sqft * rng.uniform(0.6, 1.5)))
            price = round(size * ppsf * rng.uniform(0.85, 1.2), -2)
            rows.append(home_row(rng, status, price, size, None, sub, addr(), style=style, pool=rng.random() < 0.5,
                                 original=round(price * rng.uniform(1.0, 1.08), -2)))
    rows.append(home_row(rng, "ACT", subject["list_price"], sqft, None, sub, subject["mls_address"], subject["mls_number"],
                         0.0, style, subject["pool"], subject["year_built"], zone=subject["zone"]))
    if rng.random() < 0.3:  # the subject's own sale years ago (left out of the market table)
        rows.append(home_row(rng, "SLD", round(subject["list_price"] * 0.6, -3), sqft, date(rng.randint(2012, 2020), 6, 14),
                             sub, subject["mls_address"], dist=0.0, style=style))
    rng.shuffle(rows)
    return rows


def history(rng, as_of, subject):
    """history.events, newest first: maybe an earlier owner's sale, then this owner's listing (relists, cuts,
    increases, off-market stretches, a failed contract)."""
    ev, price = [], subject["first_price"]
    d = as_of - timedelta(days=rng.randint(40, 330))
    mls_no = f"O{rng.randint(6300000, 6399999)}"
    if rng.random() < 0.4:
        y = rng.randint(2009, 2021)
        ev += [{"date": f"{y}-03-31", "mls": f"X{rng.randint(1000000, 9999999)}", "change": "listed", "price": round(price * 0.55, -2)},
               {"date": f"{y}-04-21", "change": "pending", "price": round(price * 0.55, -2)},
               {"date": f"{y}-05-22", "change": "sold", "price": round(price * 0.54, -2)}]
    ev.append({"date": d.isoformat(), "mls": mls_no, "change": "listed", "price": price})
    while d < as_of - timedelta(days=20):
        d += timedelta(days=rng.randint(6, 40))
        if d >= as_of:
            break
        roll = rng.random()
        if roll < 0.45:
            price = round(price * rng.uniform(0.96, 0.995), -2)
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "price", "price": price})
        elif roll < 0.55:
            price = round(price * rng.uniform(1.005, 1.03), -2)
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "price", "price": price})
        elif roll < 0.65:
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "off_market",
                       **({"note": "Taken off the market for repairs"} if rng.random() < 0.5 else {})})
            d += timedelta(days=rng.randint(3, 25))
            if d < as_of:
                ev.append({"date": d.isoformat(), "mls": mls_no, "change": "back_on"})
        elif roll < 0.73:
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "pending", "price": price})
            d += timedelta(days=rng.randint(5, 30))
            if d < as_of:
                ev.append({"date": d.isoformat(), "mls": mls_no, "change": "back_on"})
        elif roll < 0.8 and d < as_of - timedelta(days=40):  # canceled, relisted under a new number
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "canceled"})
            d += timedelta(days=rng.randint(10, 60))
            mls_no = subject["mls_number"]
            ev.append({"date": d.isoformat(), "mls": mls_no, "change": "listed", "price": price})
    subject["list_price"] = price
    for e in ev[-6:]:
        if e.get("mls") == subject["mls_number"] or e.get("mls") == mls_no:
            e["mls"] = mls_no
    subject["mls_number"] = mls_no
    if rng.random() < 0.3 and ev[-1]["change"] in ("listed", "price"):
        ev[-1]["dom"] = rng.randint(5, 200)
    return list(reversed(ev))


def time_rate(stats):
    """The method's rule (method.md, Time): the change in median sale-to-original-list across the split."""
    early = stats["sold_early"].get("median_sale_to_original_list")
    recent = stats["sold_recent"].get("median_sale_to_original_list")
    if early is None or recent is None or stats["sold_early"]["n"] < 5 or stats["sold_recent"]["n"] < 5:
        return None, None
    pts = abs(recent - early) * 100
    if pts < 1:
        return None, None
    return (0.01 if pts <= 3 else 0.02), ("rising" if recent > early else "falling")


def generate(seed, out_dir):
    compute = _compute()
    cma, finance, mls, profiles = compute.cma, compute.finance, compute.mls, compute.profiles
    rng = random.Random(seed)
    as_of = date(2026, 9, 1) + timedelta(days=rng.randint(0, 120))
    split = as_of - timedelta(days=rng.randint(60, 100))
    florida = rng.random() < 0.8
    city, county, state = (*rng.choice(FL), "FL") if florida else rng.choice(OTHER)
    price = round(math.exp(rng.uniform(math.log(150_000), math.log(2_000_000))), -3)
    ppsf = rng.uniform(150, 650) if price < 900_000 else rng.uniform(300, 700)
    sqft = max(650, round(price / ppsf))
    style = rng.choice(STYLES) if price < 900_000 else STYLES[0]
    condo = style == "Condominium"
    sub = rng.choice(SUBDIVISIONS)
    street = rng.choice(STREETS)
    number = rng.randint(10, 99999)
    unit = f" Unit {rng.randint(101, 1804)}" if condo else ""
    subject = {"ppsf": price / sqft, "sqft": sqft, "subdivision": sub, "style": style, "list_price": price,
               "first_price": round(price * rng.uniform(1.0, 1.06), -2), "pool": (not condo) and rng.random() < 0.5,
               "year_built": rng.randint(1958, 2023), "zone": rng.choice(ZONES),
               "mls_address": f"{number} {street.upper()}", "mls_number": f"O{rng.randint(6500000, 6599999)}"}
    events = history(rng, as_of, subject)
    rows = export(rng, as_of, split, subject)
    path = os.path.join(out_dir, "export.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    market = profiles.load_market(state=state, county=county, mls="Stellar")
    homes = mls.load(path, market)
    mls.fill_distances(homes, subject["mls_address"])
    st = mls.market_stats(homes, {"address": subject["mls_address"], "living_area": sqft, "private_pool": subject["pool"],
                                  "subdivision": sub}, split_date=split.isoformat(), as_of=as_of.isoformat(),
                          exclude_address=subject["mls_address"])
    rate, direction = time_rate(st)
    sold = [h for h in homes if h["status"] == "SOLD" and not mls.same_address(h["address"], subject["mls_address"])]
    sold.sort(key=lambda h: abs(h["living_area"] - sqft))
    picks = sold[:rng.randint(3, min(8, len(sold)))]
    scale = price / 450_000
    cards = []
    for h in picks:
        adj = []
        diff = sqft - h["living_area"]
        if diff:
            adj.append({"label": "Size", "amount": round(max(-0.06 * h["close_price"], min(0.06 * h["close_price"],
                                                                                          diff * 75 * scale)), -2)})
        if h["private_pool"] != subject["pool"] and not condo:
            adj.append({"label": "Pool", "amount": round((25000 if subject["pool"] else -25000) * scale, -2)})
        if rng.random() < 0.2:
            adj.append({"label": rng.choice(("Larger Corner Lot", "Pond Lot", "Documented Recent Systems")),
                        "amount": round(-rng.choice((5000, 10000)) * scale, -2)})
        cards.append({"address": cma.display_address(h["address"]) if rng.random() < 0.7 else h["address"],
                      "sold_price": h["close_price"], "seller_concessions": h.get("seller_paid") or 0,
                      "condition": rng.choice(cma.CONDITION_LEVELS[:-1] if rng.random() < 0.9 else cma.CONDITION_LEVELS),
                      "adjustments": adj, "bullets": rng.sample(BULLETS, rng.randint(1, 3))})
    R = {"prepared_date": as_of.isoformat(), "as_of": as_of.isoformat(), "export": path, "split_date": split.isoformat(),
         "subject": {"address": f"{number} {street}{unit}", "mls_address": subject["mls_address"],
                     "locality": f"{city}, {state} {rng.randint(32000, 34999)} · {sub} · {county} County · MLS "
                                 f"{subject['mls_number']}",
                     "list_price": subject["list_price"], "sqft": sqft, "beds": max(1, round(sqft / 550)),
                     "baths": rng.choice((1, 1.5, 2, 2.5, 3, 4)), "year_built": subject["year_built"],
                     "pool": subject["pool"], "subdivision": sub, "state": state, "county": county, "city": city,
                     "property_type": {"Condominium": "condo", "Townhouse": "townhouse"}.get(style, "single_family"),
                     "facts": [["Lot", "0.24 acre" if not condo else "Unit"], ["Built", f"{subject['year_built']}, block"],
                               ["Pool", "Private" if subject["pool"] else "None"], ["Garage", "2-car attached"],
                               ["HOA / CDD", "None" if rng.random() < 0.5 else "Yes"],
                               ["Flood Zone", subject["zone"]]],
                     "summary": "An updated home with a remodeled kitchen and new flooring.",
                     "condition": rng.choice(cma.CONDITION_LEVELS[:-1])},
         "history": {"events": events, "takeaway": "The market has had a long look at this home, and the price has "
                                                   "come down; we need to know why before writing an offer."},
         "comps": {"cards": cards, "intro": "The closest matches in size and condition, including the ones that argue "
                                            "against a lower price.",
                   "method_note": "Condition adjustments are based on listing descriptions, so they are judgment calls.",
                   "lean": "We lean toward the most recent sales and the best condition matches."}}
    if rate:
        R["comps"]["time_adjustment"] = {"rate_per_quarter": rate, "prices": direction}
    # the condition ladder's dollars: the market's (Florida), else the agent's or paired sales', scaled to the price
    if not florida or rng.random() < 0.3:
        R["comps"]["condition_values"] = {lv: round(v * scale, -2) for lv, v in
                                          profiles.load_market(state="FL", county="Seminole").get(
                                              "cma.adjustments.condition_levels").items()}
    if rng.random() < 0.3:
        R.pop("history")
    if not florida:
        R["mls"] = "Stellar"
    # the comps-only stage, as the skill runs it before setting the range: the adjusted values
    m2 = compute.copy.deepcopy(R)
    compute.prepare_comps(m2, homes, lambda *a: None, market)
    values = [c["adjusted"] for c in m2["comps"]["cards"]]
    low, high = cma.choose_range(values, market)
    if rng.random() < 0.1:  # now and then the agent sets the range: a step lower, shown as their choice
        low, high = low - 5000, high - 5000
        R["range_override"] = {"low": low, "high": high, "reason": "The agent leans toward the most recent sales, "
                                                                   "which sit lower than the rest."}
    median = statistics.median(values)
    R["bottom_line"] = {"why": "The recent sales and the best condition matches set the range; the earlier sales sit "
                               "higher."}
    R["offer_plan"] = {"conditions": "the inspection finds nothing major and no other offers are competing"}
    if rng.random() < 0.8:  # the model's pick, with its reason (left out: the suggested posture, no reason needed)
        R["offer_plan"].update(posture=rng.choice(POSTURES), posture_reason=rng.choice(POSTURE_REASONS))
    roll = rng.random()
    if roll < 0.06:  # the agent's own numbers, in the plan's order by construction
        R["offer_plan"]["plan_override"] = {"opening": low - 2000, "walk_away": high + 3000, "reason": OVERRIDE_REASON}
    elif roll < 0.11:
        R["offer_plan"]["plan_override"] = {"opening": low - 2000, "target_low": low, "target_high": low + 4000,
                                            "walk_away": high, "reason": OVERRIDE_REASON}
    elif roll < 0.15:
        R["offer_plan"]["plan_override"] = {"walk_away": high, "reason": OVERRIDE_REASON}
    R["offer"] = {"bullets": ["<strong>There is room to negotiate.</strong> The home has sat, and sellers nearby are "
                              "helping with buyers' costs."]}
    R["summary_page"] = {"headline": "Open at the bottom of what recent sales support.", "why": rng.sample(WHY, 3),
                         "check_first": [list(x) for x in rng.sample(CHECKS, 3)],
                         "next_step": "Get the listing agent's answers on the roof, then write the offer."}
    actives = [h for h in homes if h["status"] in ("ACTIVE", "PENDING", "EXPIRED")
               and not mls.same_address(h["address"], subject["mls_address"])]
    comp_rows = []
    for h in rng.sample(actives, min(len(actives), rng.randint(3, 9))):
        comp_rows.append([cma.display_address(h["address"]), {"ACTIVE": "For sale", "PENDING": "Under contract"}.get(
            h["status"], "Expired"), h["current_price"], int(h["living_area"]), "Yes" if h["private_pool"] else "No",
                          h.get("days_on_market") or rng.randint(1, 200), rng.choice(NOTES)])
    R["competition"] = {"intro": "The homes this seller is competing with right now.", "rows": comp_rows}
    if comp_rows and rng.random() < 0.3:
        R["competition"]["adjustments"] = {comp_rows[0][0]: [{"label": "Pool", "amount": round(25000 * scale, -2)}]}
    plotted = [c["address"] for c in cards] + [r[0] for r in comp_rows if r[1] == "For sale"]
    R["scatter"] = {"subject_label_pos": rng.choice(("left", "right", "above", "below")),
                    "callouts": [{"address": a, "side": rng.choice(("left", "right", "above", "below"))}
                                 for a in rng.sample(plotted, min(len(plotted), rng.randint(0, 3)))],
                    "takeaway": "The renovated sales sit above the line, and the dated ones below it."}
    R["market"] = {"bullets": ["<strong>Sellers expect to negotiate</strong> after the market cooled.",
                               "<strong>Mortgage rates are up</strong> from the earlier sales."]}
    if florida and rng.random() < 0.5:
        rows = finance.millage(market, county=county)
        juris = [{"label": f"in {r['district']}", "short": "City" if i else "County", "district": r["district"]}
                 for i, r in enumerate(rng.sample(rows, min(len(rows), rng.choice((1, 2)))))]
    else:
        juris = [{"label": "in the County", "short": "County", "school_mills": round(rng.uniform(4, 7), 3),
                  "total_mills": round(rng.uniform(11, 21), 4)}]
        if rng.random() < 0.3:
            juris.append({"label": "Inside City Limits", "short": "City", "school_mills": juris[0]["school_mills"],
                          "total_mills": round(juris[0]["total_mills"] + rng.uniform(1, 4), 4)})
        if not florida and rng.random() < 0.5:
            juris = [{"label": "in the County", "short": ""}]  # no millage: the market's fallback rate
    taxes = {"homestead": rng.random() < 0.8, "jurisdictions": juris}
    if rng.random() < 0.85:
        taxes.update(current_bill=round(price * rng.uniform(0.005, 0.02), 2), current_year=as_of.year - 1)
    programs = [("conventional", 0.05), ("fha", 0.035), ("conventional", 0.2), ("conventional", 0.03), ("va", 0.0),
                ("usda", 0.0), ("conventional", 0.1)]
    scen = [{"type": t, "down_pct": d, **({"assumed": True} if rng.random() < 0.3 else {})}
            for t, d in rng.sample(programs, rng.randint(1, 3))]
    pay = {"rate": round(rng.uniform(5.5, 7.8), 2), "scenarios": scen}
    if rng.random() < 0.5:
        pay["rate_week"] = (as_of - timedelta(days=5)).isoformat()
    if rng.random() < 0.3:
        pay["insurance_annual"] = round(price * rng.uniform(0.006, 0.012), -2)
    if rng.random() < 0.3 or condo:
        pay["hoa_cdd_monthly"] = rng.choice((35, 120, 420, 875))
    if rng.random() < 0.2:
        pay["flood_insurance_annual"] = rng.choice((650, 1800, 4200))
    if rng.random() < 0.4:  # left out, the plan's target
        pay["price"] = rng.choice((price, low, max(low, min(high, math.floor(median / 1000) * 1000))))
    loan, down = scen[0]["type"], scen[0]["down_pct"]
    step = max(1000, round(price * 0.01, -3))
    credits = {"loan_type": loan, "down_pct": down,
               "scenarios": [{"credit": i * step} for i in range(rng.randint(2, 4))]}
    if rng.random() < 0.2:  # left out: the opening with no credit, then $5,000 and $10,000
        credits.pop("scenarios")
    if rng.random() < 0.4:
        credits["closing_cost_pct"] = rng.choice((0.025, 0.03, 0.035))
    elif rng.random() < 0.2:
        credits["closing_costs"] = round(price * 0.03, -2)
    if rng.random() < 0.3:
        credits["buydown"] = {"credit": (credits.get("scenarios") or [{"credit": 10000}])[-1]["credit"]}
    if rng.random() < 0.2:
        credits.update(buyer_broker_agreement_pct=0.03, seller_pays_buyer_broker_pct=rng.choice((0, 0.02, 0.025)))
    credits["takeaway"] = "A credit helps when cash is tight; a lower price helps the monthly payment."
    if rng.random() < 0.25:
        R["offer_plan"]["credit_alt"] = {"credit": (credits.get("scenarios") or [{"credit": 10000}])[-1]["credit"]}
    costs = {"taxes": taxes, "insurance": {"drivers": "The roof's age, the wiring and plumbing era and the flood zone."},
             "payment": pay, "credit_scenarios": credits}
    if rng.random() < 0.4:
        costs["buyer_cash"] = round(price * rng.uniform(0.04, 0.3), -3)
    R["costs"] = costs
    R["watch"] = {"items": rng.sample(WATCH, rng.randint(2, 4)), "questions": rng.sample(QUESTIONS, rng.randint(3, 5))}
    if rng.random() < 0.6:
        R["sources"] = ["the MLS listing and its full price history", "the county property appraiser's millage rates"]
    if rng.random() < 0.3:
        R["sample"] = True
    return R


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
            "license": "SL1234567", "phone": "(407) 555-0142", "email": "agent@example.com",
            "disclaimers": "\n\n".join([para] * rng.randint(1, 3))}
