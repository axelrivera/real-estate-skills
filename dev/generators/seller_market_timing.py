"""Seeded random market-timing.json inputs and their MLS exports for the generated tests
(dev/tests/test_generated_seller_market_timing.py), the fixtures and the sample.

    from generators import seller_market_timing as gen
    data, csv_text = gen.generate(7)                       # the same input for the same seed
    csv_text = gen.export(rng, as_of, months=24, shape="spring", per_month=3.0)   # one export, for a fixture

Every input is valid and realistic: 12, 24 or 36 months of closed sales shaped like a market (a spring season, a
Florida winter season, two seasons, no season, a thin neighborhood), an export with or without contract dates, cut
short or not, with a few listings, pending sales and rows without a price mixed in, and long or missing area names.
Streets and MLS numbers are made up. Mock data only.
"""
import csv
import io
import random
from datetime import date, timedelta

HEADERS = ("ML Number", "Status", "Address", "Legal Subdivision Name", "Heated Area", "Current Price", "Close Price",
           "Close Date", "Original List Price", "Contract Date", "CDOM")
STREETS = ("Sample Oak Ct", "Wren Hollow Ln", "Pine Hollow Rd", "Sample Heron Ln", "Bayview Ter", "Mock Cypress Way",
           "Example Ridge Dr", "Test Meadow Cir", "Sample Gull Pl", "Fernwood Sample Blvd")
AREAS = ("Sample Ridge", "Oak Hollow Estates", "Example Lakes", None,
         "Whispering Cypress Hammock at Old Cedar Creek Plantation Phase Two")
PLACES = (("FL", "Seminole"), ("FL", "Orange"), ("FL", "Polk"), ("FL", "Hillsborough"))
# Relative sales by calendar month (January first)
SHAPES = {
    "spring": (0.3, 0.5, 1.0, 1.6, 1.8, 1.7, 1.5, 1.1, 0.6, 0.5, 0.3, 0.2),
    "winter": (1.6, 1.8, 1.7, 1.3, 0.8, 0.5, 0.4, 0.4, 0.4, 0.6, 0.9, 1.3),
    "two": (0.4, 0.5, 1.4, 1.7, 1.6, 0.6, 0.4, 0.5, 1.3, 1.5, 0.6, 0.3),
    "flat": (1.0,) * 12,
}


def add_months(d, n):
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def _money(v):
    return f"${v:,.0f}"


def export(rng, as_of, months=24, shape="spring", per_month=3.0, contract=True, extra_rows=True, base_price=None,
           subdivision="SAMPLE RIDGE"):
    """CSV text: about `per_month` sales a month (shaped by SHAPES[shape]) under contract in the `months` before
    `as_of`'s previous month, each closing 20 to 55 days later; without `contract`, no Contract Date column."""
    weights = SHAPES[shape]
    base_price = base_price or rng.choice((240000, 385000, 520000, 910000))
    rows, n = [], 0
    end = add_months(as_of, -1)
    for i in range(months):
        first = add_months(end, -months + i)
        k = sum(1 for _ in range(40) if rng.random() < per_month * weights[first.month - 1] / 40)
        for _ in range(k):
            n += 1
            days = (add_months(first, 1) - first).days
            signed = first + timedelta(days=rng.randrange(days))
            closed = signed + timedelta(days=rng.randint(20, 55))
            if closed >= as_of:
                continue
            years_ago = (end - signed).days / 365
            sqft = rng.randint(1100, 3200)
            price = round(base_price * (sqft / 2000) ** 0.7 * (1.04 ** -years_ago) * rng.uniform(0.85, 1.15), -2)
            listed = round(price * rng.uniform(0.98, 1.08), -2)
            rows.append({"ML Number": f"X{9100000 + n}", "Status": "SLD",
                         "Address": f"{rng.randint(100, 9899)} {rng.choice(STREETS).upper()}",
                         "Legal Subdivision Name": subdivision, "Heated Area": sqft, "Current Price": _money(price),
                         "Close Price": _money(price), "Close Date": closed.strftime("%m/%d/%Y"),
                         "Original List Price": _money(listed), "Contract Date": signed.strftime("%m/%d/%Y"),
                         "CDOM": rng.choice((2, 4, 6, 9, 12, 18, 25, 33, 47, 61, 88))})
    if extra_rows:
        for status in ("ACT", "PND", "SLD"):
            n += 1
            rows.append({"ML Number": f"X{9100000 + n}", "Status": status,
                         "Address": f"{rng.randint(100, 9899)} {rng.choice(STREETS).upper()}",
                         "Legal Subdivision Name": subdivision, "Heated Area": 1800,
                         "Current Price": _money(base_price), "Close Price": "", "Close Date": "",
                         "Original List Price": _money(base_price), "Contract Date": "", "CDOM": 12})
    rng.shuffle(rows)
    headers = [h for h in HEADERS if contract or h != "Contract Date"]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def generate(seed):
    """(market-timing.json dict, export CSV text). The data's `export` is "export.csv": write the text beside it."""
    rng = random.Random(seed)
    as_of = date(2026, rng.randint(1, 12), rng.randint(1, 28))
    lookback = rng.choice((12, 24, 24, 24, 36))
    shape = rng.choice(tuple(SHAPES))
    per_month = rng.choice((0.8, 2.0, 3.5, 6.0))
    short = rng.random() < 0.2
    months = lookback - rng.randint(4, 10) if short and lookback > 12 else lookback
    text = export(rng, as_of, months=months, shape=shape, per_month=per_month, contract=rng.random() < 0.8,
                  extra_rows=rng.random() < 0.7)
    state, county = rng.choice(PLACES)
    data = {"export": "export.csv", "state": state, "county": county, "as_of": as_of.isoformat(),
            "lookback_months": lookback}
    area = rng.choice(AREAS)
    if area:
        data["area"] = area
    if rng.random() < 0.15:
        start = rng.randint(1, 12)
        data["season_override"] = [(start - 1 + i) % 12 + 1 for i in range(rng.randint(2, 6))]
    return data, text
