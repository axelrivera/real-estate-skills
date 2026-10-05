"""Random valid contract-timeline deal files, for the generated tests (dev/tests/test_generated_contract_timeline.py).

    sys.path.insert(0, "dev/generators"); import contract_timeline as gen
    gen.generate(7)      # one deal file (a dict); the same seed always gives the same deal
    gen.agent(7)         # an agent profile dict (none, short, or long names and disclaimers)

Each seed picks one of: a FAR/BAR AS IS or Standard contract with random riders (only combinations
shared/contract_forms.py accepts), a short sale still waiting on the approval or with it received, or another state's
contract with its own deadlines and time rules (some rules left out, so the script's open-rule reading runs). Effective
and closing dates land near weekends and federal holidays on purpose; names run long; optional fields are left out at
random (the form defaults fill them); amendments move the closing and lengthen periods; completed rows, a report date
before or after the deadlines and what-if runs vary. Nothing here asserts anything: the test does.
"""
import os
import random
import sys
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from shared import contract_forms as cf  # noqa: E402

# days a deadline likes to land on: holidays, the days around them, and weekends
ANCHORS = [date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 11), date(2026, 11, 26), date(2026, 12, 25),
           date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 5, 31), date(2027, 6, 18),
           date(2027, 7, 5)]
STREETS = ["Cypress Bend Dr", "Whispering Cypress Hammock Boulevard Building 4 Unit 1204", "Oak St", "Larchmere Trace",
           "Saint Augustine Grass Court Northeast", "Pelican Point Way", "Hickorywood Dr"]
CITIES = {"FL": ["Orlando, FL 32801", "Palm Beach Gardens, FL 33418", "Pensacola, FL 32501", "Lakeland, FL 33803"],
          "TX": ["Austin, TX 78701", "El Paso, TX 79901"], "OH": ["Westerville, OH 43081"], "GA": ["Savannah, GA 31401"],
          "AZ": ["Tucson, AZ 85701"], "CA": ["Fresno, CA 93721"], "NC": ["Raleigh, NC 27601"], "CO": ["Denver, CO 80202"],
          "IL": ["Naperville, IL 60540"], "TN": ["Knoxville, TN 37902"]}
FL_COUNTIES = ["Orange", "Palm Beach", "Escambia", "Polk", "Gulf", "Seminole", "Miami-Dade"]
OTHER_COUNTIES = {"TX": ["Travis", "El Paso"], "TN": ["Knox", "Davidson"], "IL": ["DuPage"]}
FIRST = ["Avery", "Jordan", "Maximiliana Alexandra", "Lee", "Quinn", "Rosalind-Beatrix", "Sam"]
LAST = ["Montgomery-Vandersloot", "Ashdown", "Pennington", "Lee", "Hollingsworth", "Delacroix", "Okafor"]
TITLE_COS = ["Sample Title Co.", "Coldwater Bay Title Insurance Agency of the Palm Beaches, LLC", "Olentangy Crossing Title"]
# riders the generator attaches (the ones that set dates or change the rows); RESERVED ones on AS IS are dropped by
# contract_forms' own rule, never by a list here
RIDER_POOL = ["A", "B", "E", "F", "G", "H", "I", "K", "L", "M", "N", "P", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
              "DD", "GG"]
LABELS = [("Due Diligence Period Ends", "Due Diligence"), ("Earnest Money Delivered", "Earnest Money"),
          ("Seller's Disclosure Delivered", "Disclosure"), ("Appraisal Objection Deadline", "Appraisal"),
          ("HOA Resale Certificate Review Ends", "HOA Review"), ("Final Walk-Through", "Walk-Through"),
          ("Buyer's Condominium Document Review and Rescission Period Ends", "Condo Review"),
          ("Boundary and Elevation Survey with Flood Elevation Certificate Delivered", "Survey"),
          ("Title Commitment Objection Deadline", "Title Objections"), ("Loan Commitment Deadline", "Loan Commitment")]
AMENDMENT_NAMES = ["Extension Addendum (EA-4)", "Addendum No. 1", "Amendment to Extend Closing and Loan Approval Dates",
                   ""]


def _iso(d):
    return d.isoformat()


def _near(rng, lo, hi):
    """A date between lo and hi, often on or next to a holiday or a weekend."""
    span = (hi - lo).days
    d = lo + timedelta(days=rng.randrange(max(span, 1)))
    if rng.random() < 0.5:
        anchors = [a for a in ANCHORS if lo <= a <= hi]
        if anchors:
            d = rng.choice(anchors) + timedelta(days=rng.choice([-3, -1, 0, 0, 1, 2]))
    elif rng.random() < 0.3:
        d += timedelta(days=(5 - d.weekday()) % 7)  # a Saturday
    return min(max(d, lo), hi)


def _name(rng, long=False):
    n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return n + f" and {rng.choice(FIRST)} {rng.choice(LAST)}" if long or rng.random() < 0.3 else n


def _riders(rng, form):
    """Random riders the form accepts (contract_forms.terms decides; an invalid pick is dropped, not special-cased)."""
    picked = []
    for code in rng.sample(RIDER_POOL, rng.randint(0, 7)):
        trial = picked + [code]
        try:
            cf.terms(form, {"riders": trial})
        except cf.FormError:
            continue
        picked = trial
    return picked


def _custom(rng, i, closing, eff):
    label, short = rng.choice(LABELS)
    basis = rng.choice(["after", "after", "before", "date", "event"])
    x = {"key": f"x_{i}", "label": label if rng.random() < 0.8 else f"{label} and Related Notices Under Para. {i + 2}",
         "short": short, "basis": basis, "party": rng.choice(["Buyer", "Seller", "Both"]),
         "critical": rng.random() < 0.5, "contingency": rng.random() < 0.3, "source": f"Para. {rng.randint(2, 20)}",
         "action": "Deliver written notice to the other party before the deadline",
         "if_missed": rng.choice(["The right ends", "The agreement states no specific remedy", ""])}
    if basis in ("after", "before", "event"):
        x["days"] = rng.choice([0, 1, 3, 5, 7, 10, 14, 21])
    if basis == "before" and closing is None:
        x["basis"], x["days"] = "after", rng.choice([3, 10])
    if basis == "date":
        x["date"] = _iso(_near(rng, eff + timedelta(days=1), (closing or eff + timedelta(days=60))))
        if rng.random() < 0.3:
            x["date"] += " 17:00"
    if basis == "event" and rng.random() < 0.6:
        x["received"] = _iso(eff + timedelta(days=rng.randint(0, 12)))
    if rng.random() < 0.2:
        x["time"] = "17:00"
    if rng.random() < 0.15:
        x["rollover"] = False
    if rng.random() < 0.15 and x["basis"] in ("after", "event"):
        x["business"] = True
    return x


def _people(rng, state):
    city = rng.choice(CITIES[state])
    long = rng.random() < 0.25
    return {"property": f"{rng.randint(10, 19999)} {rng.choice(STREETS)}, {city}", "buyer": _name(rng, long),
            "seller": _name(rng, long) + (", Trustee of the Hollingsworth-Vandermeer Family Trust" if long else ""),
            "escrow_agent": rng.choice(TITLE_COS)}


def _money(rng, c, financing):
    price = rng.randrange(150_000, 3_000_000, 500)
    c["price"] = price
    dep = rng.choice([1000, 5000, 10_000, 25_000, round(price * 0.03)])
    if rng.random() < 0.5:
        c["deposit_amount"] = dep
    else:
        c["deposit_amount_str"] = f"${dep:,}"
    if rng.random() < 0.4:
        c["additional_deposit_amount"] = rng.choice([5000, 20_000, 40_000])
    if financing != "cash" and rng.random() < 0.6:
        loan = round(price * rng.choice([0.8, 0.9, 0.965]))
        c["loan_amount"] = loan
        if rng.random() < 0.7:
            c["balance_to_close"] = price - loan - dep - c.get("additional_deposit_amount", 0) + rng.choice([0, 0, 0, 1500])


def farbar(rng, seed):
    eff = _near(rng, date(2026, 9, 1), date(2027, 6, 30))
    form = rng.choice(cf.FARBAR)
    riders = _riders(rng, form)
    financing = rng.choice(["cash", "conventional", "conventional", "fha", "va", "usda"])
    closing = _near(rng, eff + timedelta(days=21), eff + timedelta(days=80))
    c = {"form_family": "farbar", "contract_form": form, "effective_date": _iso(eff), "financing": financing,
         "riders": [cf.RIDERS[r] if rng.random() < 0.3 else r for r in riders], **_people(rng, "FL"),
         "title_by": rng.choice(["seller", "buyer", None])}
    if rng.random() < 0.8:
        c["effective_date_source"] = rng.choice(["Seller's initials on Counteroffer #1", "Buyer's signature on the "
                                                 "acceptance", "Second seller's signature on the contract (Para. 3(b))"])
        c["effective_date_signed"] = f"{_iso(eff - timedelta(days=rng.choice([0, 0, 1])))} {rng.randint(8, 20):02d}:12"
    if rng.random() < 0.3:
        c["effective_date_delivered"] = rng.choice([True, False])
    _money(rng, c, financing)
    c["closing_date"] = _iso(closing)
    if rng.random() < 0.6:
        c["closing_time"] = rng.choice(["10:00", "14:30", "09:00"])
    for field, choices in (("deposit_days", [0, 1, 3, 5]), ("inspection_days", [5, 7, 10, 15, 21]),
                           ("loan_application_days", [3, 5]), ("loan_approval_days", [21, 25, 30, 45]),
                           ("title_evidence_days_before", [5, 15]), ("additional_deposit_days", [10, 14])):
        if rng.random() < 0.6:
            c[field] = rng.choice(choices)
    if rng.random() < 0.3:
        c["blanks"] = rng.sample(["deposit_days", "inspection_days", "loan_approval_days", "title_evidence_days_before"],
                                 rng.randint(1, 2))
        for b in c["blanks"]:
            c.pop(b, None)
    codes = set(riders)
    if "A" in codes or rng.random() < 0.15:
        c["condo"] = True
        if rng.random() < 0.5:
            c["condo_docs_received"] = _iso(eff + timedelta(days=rng.randint(0, 6)))
    if "B" in codes or rng.random() < 0.15:
        c["hoa"] = True
    if ("A" in codes or "B" in codes) and rng.random() < 0.5:
        c["association_approval"] = rng.choice([True, "unknown"])
    if rng.random() < 0.5:
        c["flood_zone"] = rng.choice(["X", "AE", "VE", "A"])
    if rng.random() < 0.6:
        c["year_built"] = rng.choice([1962, 1977, 1978, 1995, 2018])
    if "H" in codes and rng.random() < 0.6:
        c["insurance_coverage"] = rng.choice(["homeowners", "flood", "both"])
    if "F" in codes and rng.random() < 0.5:
        c["appraisal_days"] = rng.choice([14, 21])
    if "G" in codes:
        c["short_sale_approval_days"] = rng.choice([30, 60, 90])
        if rng.random() < 0.5:
            c["short_sale_approval_received"] = _iso(eff + timedelta(days=rng.randint(10, 70)))
        c["short_sale_backup"] = rng.choice(["a", "b", None])
    if "R" in codes and rng.random() < 0.5:
        c["rezoning_date"] = _iso(eff + timedelta(days=rng.randint(20, 60)))
    if "V" in codes and rng.random() < 0.6:
        c["sale_contingency_date"] = _iso(_near(rng, eff + timedelta(days=10), closing))
    if "U" in codes:
        c["seller_occupancy_days"] = rng.choice([3, 7, 14])
        c["occupancy"] = rng.choice(["owner", "vacant", None])
    if "W" in codes and rng.random() < 0.5:
        c["backup_notice_date"] = _iso(eff + timedelta(days=rng.randint(5, 20)))
    if "Y" in codes and rng.random() < 0.5:
        c["seller_attorney_date"] = _iso(eff + timedelta(days=rng.randint(3, 10)))
    if "Z" in codes and rng.random() < 0.5:
        c["buyer_attorney_date"] = _iso(eff + timedelta(days=rng.randint(3, 10)))
    if rng.random() < 0.2:
        c["tenants"] = True
    if rng.random() < 0.2:
        c["title_commitment_received"] = _iso(eff + timedelta(days=rng.randint(5, 20)))
    if rng.random() < 0.15:
        c["possession_date"] = _iso(closing + timedelta(days=rng.choice([0, 2])))
        c["possession_time"] = "17:00"
    c = {k: v for k, v in c.items() if v is not None}
    deal = {"side": rng.choice(["buyer", "seller"]), "state": "FL", "county": rng.choice(FL_COUNTIES),
            "client": c["buyer"] if rng.random() < 0.7 else c["seller"], "contract": c}
    extra = [_custom(rng, i, closing, eff) for i in range(rng.choice([0, 0, 0, 1, 3, 8]))]
    if extra:
        deal["deadlines"] = extra
    return deal, eff, closing


def other(rng, seed):
    state = rng.choice([s for s in CITIES if s != "FL"])
    eff = _near(rng, date(2026, 9, 1), date(2027, 6, 30))
    closing = _near(rng, eff + timedelta(days=21), eff + timedelta(days=75))
    rules = {"day_count": rng.choice(["calendar", "business"])}
    for key, choices in (("short_period_days", [0, 5]), ("end_time", ["23:59", "17:00"]),
                         ("weekend_holiday_rollover", ["next_business_day", "none"]),
                         ("before_closing_rollover", ["previous_business_day", "next_business_day", "none"]),
                         ("holidays", ["us_federal", [_iso(eff + timedelta(days=20))]])):
        if rng.random() < 0.7:
            rules[key] = rng.choice(choices)
    financing = rng.choice(["cash", "conventional", "fha"])
    c = {"form_family": "other", "form": rng.choice(["Residential Purchase Agreement (Sample Form RPA-1)",
                                                      "One to Four Family Residential Contract (Resale)"]),
         "effective_date": _iso(eff), "closing_date": _iso(closing), "financing": financing, **_people(rng, state),
         "effective_date_source": "Seller's signature on the agreement"}
    if rng.random() < 0.5:
        c["closing_time"] = "13:00"
    if rng.random() < 0.5:
        c["closing_if_missed"] = "Either party may terminate after written notice"
    _money(rng, c, financing)
    deadlines = [_custom(rng, i, closing, eff) for i in range(rng.randint(2, 14))]
    deal = {"side": rng.choice(["buyer", "seller"]), "state": state, "client": c["buyer"], "rules": rules,
            "contract": c, "deadlines": deadlines}
    county = OTHER_COUNTIES.get(state)
    if county and rng.random() < 0.7:
        deal["county"] = rng.choice(county)
    return deal, eff, closing


def generate(seed):
    """One random valid deal file for `seed`."""
    rng = random.Random(seed)
    d, eff, closing = (farbar if rng.random() < 0.7 else other)(rng, seed)
    c = d["contract"]
    # the report's date: before the first deadlines, mid-deal (some rows past) or near closing
    d["report_date"] = _iso(eff + timedelta(days=rng.choice([0, 0, 2, 9, 20, (closing - eff).days - 3])))
    if rng.random() < 0.1:
        d["report_date"], d["what_if"] = _iso(eff - timedelta(days=rng.randint(1, 20))), True
    if rng.random() < 0.5:
        d["sample"] = True
    amendments = []
    for i in range(rng.choice([0, 0, 0, 1, 2, 3])):
        changes = {}
        if rng.random() < 0.6:
            closing = closing + timedelta(days=rng.choice([3, 7, 14]))
            changes["closing_date"] = _iso(closing)
        if d["contract"]["form_family"] == "farbar" and rng.random() < 0.5:
            field = rng.choice(["inspection_days", "loan_approval_days"])
            base = changes.get(field) or c.get(field) or {"inspection_days": 15, "loan_approval_days": 30}[field]
            changes[field] = base + rng.choice([3, 5, 10])
        amendments.append({"date": _iso(eff + timedelta(days=rng.randint(1, 30))), "name": rng.choice(AMENDMENT_NAMES),
                           "description": rng.choice(["Extend closing", "Extend the inspection period",
                                                      "Credit and repairs", "Extend closing and loan approval"]),
                           "changes": changes})
    if amendments:
        d["amendments"] = amendments
    if c["form_family"] == "farbar" and rng.random() < 0.4:
        dep_day = eff + timedelta(days=rng.randint(0, 3))
        if _iso(dep_day) <= d["report_date"]:
            d["completed"] = {"deposit": _iso(dep_day)}
    if rng.random() < 0.3:
        d["agent_notes"] = [rng.choice(["The seller asked to leave the patio furniture.",
                                        {"key": "deposit", "text": "No escrow receipt in the package yet."},
                                        {"key": "money_mismatch", "text": "Which Para. 2 figures are current?"}])]
    return d


def agent(seed):
    """An agent profile as profiles.load_agent returns it: none, a short one, or a long one with a long disclaimer (the
    closing notices that most often push a last page over)."""
    rng = random.Random(seed * 7919 + 3)
    pick = rng.random()
    if pick < 0.2:
        return {}
    if pick < 0.6:
        return {"name": "Jordan Avery", "brokerage": "Sample Realty, LLC", "license": "SL0000001",
                "brand": {"primary": rng.choice(["#1A74AD", "#0B6E4F", "#7A1F5C"])},
                "disclaimers": "Information deemed reliable but not guaranteed."}
    para = ("Information deemed reliable but not guaranteed. All measurements and figures should be independently "
            "verified. Each office is independently owned and operated. ")
    return {"name": "Maximiliana Alexandra Montgomery-Vandersloot, REALTOR, GRI, ABR, SRS",
            "team": "The Montgomery-Vandersloot Luxury Waterfront and Golf Community Team",
            "brokerage": "Coldwater Bay International Realty and Relocation Partners of Central Florida, LLC",
            "license": "SL1234567", "disclaimers": "\n\n".join([para] * rng.randint(1, 4))}
