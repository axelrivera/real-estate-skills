"""Seller net sheet (skills/seller-net-sheet/scripts): the money math, the rules for taxes, payoffs and assumptions,
input errors, and the one-page render. Every fixture's computed facts are also pinned by dev/golden/seller-net-sheet/."""
import contextlib
import copy
import glob
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-net-sheet")
cma_compute, = load("seller-cma", "compute")  # loaded first: load() clears the other skill's modules
compute, render, handoff, finance, profiles, shared_render = load(
    "seller-net-sheet", "compute", "render", "_shared.handoff", "_shared.finance", "_shared.profiles", "_shared.render")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def all_fixtures():
    paths = sorted(glob.glob(os.path.join(FIXTURES, "*.json"))) + [os.path.join(ROOT, "dev", "samples", "seller-net-sheet.json")]
    for path in paths:
        with open(path) as f:
            yield os.path.basename(path), json.load(f)


def tax_row(C):
    return next(r for r in C["rows"] if r["key"] == "tax_proration")


def page_count(path):
    with open(path, "rb") as f:
        return len(re.findall(rb"/Type\s*/Page[^s]", f.read()))


class EveryFixture(unittest.TestCase):
    def test_columns_add_up_and_labels_carry_no_notes(self):
        """In every fixture each column's lines (payoffs included) add up to its net, and no row, column or fact label
        carries an Assumed or Estimate tag: estimates are said once, in the notes."""
        for name, data in all_fixtures():
            with self.subTest(name):
                C = compute.run(data)
                for i, c in enumerate(C["columns"]):
                    lines = [r["amounts"][i] for r in C["rows"] if r["kind"] == "line"]
                    self.assertAlmostEqual(c["price"] + sum(lines), c["net"])
                    self.assertAlmostEqual(c["net_before_payoff"] - c["payoff_total"], c["net"])
                labels = [r["label"] for r in C["rows"]] + [c["label"] for c in C["columns"]] + [f["text"] for f in C["facts"]]
                self.assertEqual([x for x in labels if re.search(r"\b(Assumed|Estimate)\b", x)], [])
                self.assertFalse([n for n in C["market_notes"] if "MLS" in n or "--columns" in n])

    def test_matches_seller_cma_net(self):
        """The same price, credit and costs give the same net as seller-cma's net sheet (one shared calculator)."""
        costs = {"listing_fee_pct": 0.025, "buyer_broker_fee_pct": 0.025, "mortgage_payoff": 301000, "annual_tax": 6900,
                 "expected_closing_date": "2026-11-20", "hoa": True}
        R = {"subject": {"address": "2250 Oak Hollow Ct", "state": "FL", "county": "Seminole", "property_type": "single_family"},
             "costs": costs, "pricing": {"strategies": [{"list_price": 515000, "expected_sale": 515000, "seller_credit": 10000}]}}
        market = profiles.load_market(state="FL", county="Seminole").with_deal(costs)
        cma_net = cma_compute.net_sheet(R, market, cma_compute.labels(R))["totals"][0]
        data = {"property": {"address": "2250 Oak Hollow Ct", "state": "FL", "county": "Seminole", "property_type": "single_family",
                             "hoa": True},
                "closing_date": "2026-11-20", "scenarios": [{"price": 515000, "seller_credit": 10000}],
                "costs": {k: v for k, v in costs.items() if k not in ("expected_closing_date", "hoa")}}
        self.assertAlmostEqual(compute.run(data)["columns"][0]["net"], cma_net)


class TaxProration(unittest.TestCase):
    def test_bill_unpaid_before_due_date(self):
        """Closing before the bill is due: a charge from Jan 1 to closing, less Florida's 4% early-payment discount."""
        C = compute.run(fixture("florida-three-prices.json"))
        self.assertTrue(C["tax_assumed_unpaid"])
        self.assertEqual(-tax_row(C)["amounts"][0], round(6200 * 0.96 * 348 / 365))  # Jan 1 to Dec 14

    def test_closing_after_due_date_assumes_bill_paid(self):
        d = fixture("georgia-short.json")
        self.assertLess(tax_row(compute.run(d))["amounts"][0], 0)  # no due date: a charge
        d["costs"]["tax_bill_due_date"] = "10-15"  # Cobb County bills are due Oct 15; closing Nov 6
        C = compute.run(d)
        self.assertEqual(tax_row(C)["amounts"][0], round(3900 * 56 / 365))  # a credit back to the seller
        self.assertEqual((C["tax_assumed_paid"], C["tax_assumed_unpaid"]), (True, False))
        d["costs"]["tax_bill_due_date"] = "mid-October"
        with self.assertRaisesRegex(compute.NetSheetError, "tax_bill_due_date"):
            compute.run(d)

    def test_no_tax_bill_leaves_proration_out(self):
        d = fixture("florida-three-prices.json")
        del d["costs"]["annual_tax"]
        C = compute.run(d)
        self.assertNotIn("tax_proration", [r["key"] for r in C["rows"]])
        self.assertFalse(C["has_tax_proration"])


class Payoff(unittest.TestCase):
    """A stated payoff is used as given; a balance gets a month's interest at the loan's rate, else 4.5%."""

    def test_payoff_from_balance(self):
        base = fixture("florida-credit-manual-v5.json")
        for costs, want in (({"mortgage_payoff": 188000}, 188000),
                            ({"mortgage_balance": 188000}, round(188000 * (1 + 4.5 / 1200))),
                            ({"mortgage_balance": 188000, "mortgage_rate": 6}, round(188000 * 1.005))):
            with self.subTest(costs):
                d = copy.deepcopy(base)
                d["costs"] = {k: v for k, v in d["costs"].items() if k != "mortgage_payoff"} | costs
                C = compute.run(d)
                self.assertEqual(-next(r for r in C["rows"] if r.get("key") == "payoff")["amounts"][0], want)

    def test_short_sale_tile_is_cash_to_bring(self):
        C = compute.run(fixture("georgia-short.json"))
        self.assertTrue(all(c["short"] for c in C["columns"]))
        self.assertTrue(C["warnings"])
        self.assertEqual(C["columns"][0]["tile_display"], finance.money(-C["columns"][0]["net"]))
        F = compute.run(fixture("florida-three-prices.json"))
        self.assertNotEqual(C["columns"][0]["tile_label"], F["columns"][0]["tile_label"])


class Assumptions(unittest.TestCase):
    def test_assumed_inputs_are_recorded(self):
        """An assumed closing date or property type is flagged and asked about in the assumptions list."""
        for name, change, flag in (("florida-three-prices.json", lambda d: d.update(closing_date_assumed=True), "closing_date_assumed"),
                                   ("miami-condo-bill-paid.json", lambda d: d["property"].update(property_type_assumed=True), None)):
            with self.subTest(name):
                d = fixture(name)
                before = compute.run(d)
                change(d)
                C = compute.run(d)
                if flag:
                    self.assertEqual((before[flag], C[flag]), (False, True))
                self.assertEqual(len(C["assumptions"]), len(before["assumptions"]) + 1)

    def test_texas_never_gets_florida_numbers(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        self.assertTrue(C["preliminary"])
        self.assertNotIn("transfer_tax", [r["key"] for r in C["rows"]])
        self.assertFalse(any("0.70%" in r["label"] for r in C["rows"]))

    def test_builtin_estoppel_fee_is_noted_once(self):
        """A built-in local fee is noted as a typical charge; the deal's own figure or a national estimate is not."""
        count = lambda name: sum("estoppel" in n for n in compute.run(fixture(name))["notes"])  # noqa: E731
        self.assertEqual(count("florida-three-prices.json"), 1)
        self.assertEqual(count("miami-condo-bill-paid.json"), 0)
        self.assertEqual(count("texas-no-payoff.json"), 0)


class Inputs(unittest.TestCase):
    def test_errors_for_the_agent(self):
        cases = (("at most 3", lambda d: d.update(scenarios=d["scenarios"] * 2), compute.NetSheetError),
                 ("address", lambda d: d["property"].pop("address"), compute.NetSheetError),
                 ("0.03 for 3%", lambda d: d["costs"].update(listing_fee_pct=3), ValueError),
                 ("sale price", lambda d: d.update(scenarios=[]), compute.NetSheetError))
        for msg, change, exc in cases:
            with self.subTest(msg):
                d = fixture("florida-three-prices.json")
                change(d)
                with self.assertRaisesRegex(exc, re.escape(msg)):
                    compute.run(d)

    def test_default_labels_unique(self):
        d = fixture("florida-three-prices.json")
        d["scenarios"] = [{"price": 450000}, {"price": 450000, "seller_credit": 5000}, {"price": 450000}]
        self.assertEqual(len({c["label"] for c in compute.run(d)["columns"]}), 3)

    def test_cma_handoff_fills_location_and_price(self):
        h = handoff.build(side="seller", as_of="2026-09-22", subject={"address": "2250 Oak Hollow Ct", "city": "Casselberry",
                                                                     "state": "FL", "county": "Seminole", "annual_tax": 6900.0},
                          value={"low": 500000, "high": 525000, "midpoint": 512500}, comps=[], recommended_list_price=515000)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.seller.cma.json")
            with open(path, "w") as f:
                json.dump(h, f)
            C = compute.run({"property": {}, "closing_date": "2026-11-20"}, cma_path=path)
            self.assertEqual(C["columns"][0]["price"], 515000)
            self.assertTrue(C["has_tax_proration"])
            with self.assertRaisesRegex(compute.NetSheetError, "9 Elm St"):
                compute.run({"property": {"address": "9 Elm St"}}, cma_path=path)
            with open(path, "w") as f:
                json.dump({**h, "side": "buyer"}, f)
            with self.assertRaisesRegex(compute.NetSheetError, "buyer"):
                compute.run({"property": {}}, cma_path=path)


class Render(unittest.TestCase):
    def test_tile_row_is_always_three_boxes(self):
        """One or two prices fill the spare tile slots (costs and payoffs, or the difference); three prices need none."""
        one = compute.run(fixture("texas-no-payoff.json"))
        two = compute.run(fixture("miami-condo-bill-paid.json"))
        self.assertEqual((len(one["summary_tiles"]), len(two["summary_tiles"])), (2, 1))
        self.assertEqual(compute.run(fixture("florida-three-prices.json"))["summary_tiles"], [])
        for C in (one, two):
            doc = render.build_html(C, {})
            self.assertEqual(doc.count('<div class="tile">') + doc.count('<div class="tile sum">'), 3)
        d = fixture("florida-three-prices.json")
        d["scenarios"] = d["scenarios"][:1]
        d["costs"]["mortgage_payoff"] = 0
        d["costs"].pop("other_payoffs", None)
        self.assertEqual(compute.run(d)["summary_tiles"][1]["display"], "$0")

    def test_no_fact_row_means_no_header_rule(self):
        C = compute.run(fixture("florida-three-prices.json"))
        self.assertIn('class="divrow factrow"', render.build_html(C, {}))
        doc = render.build_html(dict(C, facts=[]), {})
        self.assertNotIn("factrow", doc.split("<style>")[-1].split("</style>")[-1])
        self.assertIn("header:has(+ .tiles){border-bottom:none", doc)
        self.assertIn('class="short"', render.build_html(compute.run(fixture("georgia-short.json")), {}))

    def test_columns_fit_their_headers(self):
        widths = render.column_widths(["$425,000", "$410,000", "$425,000 with $6,000 Credit"])
        self.assertAlmostEqual(sum(widths), 100, delta=0.2)
        self.assertGreater(widths[3], widths[1])  # the long header gets the room it needs
        need = (len("$425,000 with $6,000 Credit") * render.HEAD_PX_PER_CHAR + 16) / render.TABLE_PX * 100
        self.assertGreaterEqual(widths[3], need - 0.1)
        self.assertGreaterEqual(widths[0], render.MIN_FIRST)
        self.assertEqual(render.column_widths(["A"] * 3)[1:], [render.MIN_COL] * 3)

    def test_every_optional_line_fits_one_page(self):
        """Three prices with every optional line print on one page; a long disclaimer drops the chart, not the page."""
        d = fixture("florida-three-prices.json")
        d["scenarios"][1].update({"home_warranty": 600, "repairs": 3500, "closing_date": "2026-11-30"})
        d["costs"]["other"] += [{"label": "Permit Closeout", "amount": 800}, {"label": "Attorney Fee", "amount": 650}]
        para = "This brokerage's disclaimer runs long, as some states and brokerages require, line after line. " * 3
        for disclaimers, chart in (("Information deemed reliable.", True), ("\n\n".join([para] * 6), False)):
            agent = {"name": "Jordan Avery", "brokerage": "Sample Realty, LLC", "disclaimers": disclaimers}
            err = io.StringIO()
            with self.subTest(chart=chart), tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(io.StringIO()):
                (path,) = render.build(d, "pdf", tmp, {"agent": agent, "sample": True})
                self.assertEqual(page_count(path), 1)
                self.assertEqual("chart was left out" not in err.getvalue(), chart)

    def test_label_that_cannot_fit_stops_the_render(self):
        """Default column labels wrap to fit; a label that still can't fit stops the render instead of printing clipped."""
        d = fixture("florida-three-prices.json")
        for x in d["scenarios"]:
            x.pop("label", None)
        with tempfile.TemporaryDirectory() as tmp:
            (path,) = render.build(d, "pdf", tmp, {"agent": {}})
            self.assertTrue(os.path.exists(path))
            d["scenarios"][2]["label"] = "Listpricewithsellercreditandhomewarranty"
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(compute.NetSheetError, "cut off"):
                render.build(d, "pdf", tmp, {"agent": {}})

    def test_chart_labels_one_line(self):
        """Every price label under the chart bars stays one line high, the longest included."""
        doc = render.build_html(compute.run(fixture("florida-credit-manual-v5.json")), {})
        seen = {}

        def measure(pg):
            seen["heights"] = pg.evaluate("() => [...document.querySelectorAll('.bars .lbl')].map(e => e.getBoundingClientRect().height)")
            return render.fit_one_page(pg)

        with tempfile.TemporaryDirectory() as tmp:
            _, no_chart, clipped = shared_render.html_to_pdf(doc, os.path.join(tmp, "x.pdf"), before_print=measure)
        self.assertFalse(no_chart)
        self.assertEqual(clipped, [])
        hs = seen["heights"]
        self.assertEqual(len(hs), 3)
        self.assertLess(max(hs) - min(hs), 2, hs)


if __name__ == "__main__":
    unittest.main()
