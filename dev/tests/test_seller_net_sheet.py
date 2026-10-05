"""Tests for skills/seller-net-sheet/scripts."""
import contextlib
import copy
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
compute, render, handoff, finance, profiles = load("seller-net-sheet", "compute", "render", "_shared.handoff",
                                                   "_shared.finance", "_shared.profiles")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def row(C, label):
    return next(r for r in C["rows"] if r["label"] == label)


class Florida(unittest.TestCase):
    def setUp(self):
        self.C = compute.run(fixture("florida-three-prices.json"))

    def test_three_columns_add_up(self):
        C = self.C
        self.assertEqual([c["label"] for c in C["columns"]], ["Current List Price", "After a Price Cut", "List Price with Credit"])
        for i, c in enumerate(C["columns"]):
            lines = [r["amounts"][i] for r in C["rows"] if r["kind"] == "line"]
            self.assertAlmostEqual(c["price"] + sum(lines), c["net"])  # every line, the payoffs included, adds up to the net
            self.assertAlmostEqual(c["net_before_payoff"] - c["payoff_total"], c["net"])
        self.assertEqual(C["final_label"], "Estimated Net to Seller")
        self.assertFalse(C["preliminary"])

    def test_title_fees_itemized(self):
        """Florida's title company fees show as their four charges, and they add up to the shared line."""
        names = [r["label"] for r in self.C["rows"] if r["key"] == "title_fees"]
        self.assertEqual(names, ["Settlement Fee", "Title Search", "Municipal Lien Search", "Recording"])
        total = sum(-r["amounts"][0] for r in self.C["rows"] if r["key"] == "title_fees")
        self.assertEqual(total, 1145)

    def test_scenario_lines_only_where_given(self):
        credit, warranty = row(self.C, "Seller Credit to Buyer"), row(self.C, "Home Warranty")
        self.assertEqual(credit["display"], ["—", "—", "−$9,000"])
        self.assertEqual(warranty["amounts"], [0, 0, -550])
        self.assertEqual(row(self.C, "Home Equity Line")["amounts"], [-18000] * 3)

    def test_tax_after_bill_month_assumed_unpaid(self):
        r = next(r for r in self.C["rows"] if r["key"] == "tax_proration")
        self.assertIn("Bill Assumed Unpaid", r["label"])
        self.assertTrue(self.C["tax_assumed_unpaid"])
        self.assertEqual(-r["amounts"][0], round(6200 * 0.96 * 348 / 365))  # Jan 1 to Dec 14, less the 4% discount

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


class OtherMarkets(unittest.TestCase):
    def test_texas_minimal_is_preliminary(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        self.assertTrue(C["preliminary"])
        self.assertIn("payoff", C["preliminary_reason"])
        self.assertEqual(C["final_label"], "Estimated Net Before Mortgage Payoff")
        self.assertNotIn("transfer_tax", [r["key"] for r in C["rows"]])  # Texas has no state transfer tax
        self.assertIn("Listing Brokerage (2.5%, Assumed)", [r["label"] for r in C["rows"]])
        self.assertTrue(any("No state transfer tax in Texas" in n for n in C["notes"]))
        self.assertTrue(any(f["text"] == "Payoff Not Provided" and f.get("risk") for f in C["facts"]))
        self.assertFalse(any("0.70%" in r["label"] for r in C["rows"]))  # never Florida's numbers

    def test_miami_condo_paid_bill(self):
        C = compute.run(fixture("miami-condo-bill-paid.json"))
        keys = [r["key"] for r in C["rows"]]
        self.assertIn("transfer_surtax", keys)  # a condo owes Miami-Dade's surtax
        self.assertNotIn("owner_title", keys)  # the buyer pays the owner's policy there
        self.assertTrue(any("buyer customarily pays the owner's title" in n for n in C["notes"]))
        tax = next(r for r in C["rows"] if r["key"] == "tax_proration")
        self.assertGreater(tax["amounts"][0], 0)  # paid bill: a credit back to the seller
        self.assertEqual(C["final_label"], "Estimated Net to Seller")  # owned free and clear: cash at closing
        self.assertTrue(any("FIRPTA" in n for n in C["notes"]))
        self.assertEqual([r["label"] for r in C["rows"] if r["key"] == "title_fees"][0], "Settlement Fee")  # the quote, itemized

    def test_short_sale_warns(self):
        C = compute.run(fixture("georgia-short.json"))
        self.assertTrue(all(c["short"] for c in C["columns"]))
        self.assertTrue(C["warnings"] and "bring about" in C["warnings"][0])
        self.assertIn("bring about", C["notes"][0])
        payoff = next(r for r in C["rows"] if r["label"].startswith("Mortgage Payoff"))
        self.assertEqual(-payoff["amounts"][0], round(309000 * (1 + 6.25 / 1200)))  # a month of interest, no hidden fees (round 5)
        self.assertEqual(row(C, "Solar Panel Loan")["amounts"][0], -14000)


class Iteration9(unittest.TestCase):
    """Iteration 9 evals: the tax due date, a missing proration, an assumed closing date, shortfalls, market notes."""

    def test_closing_after_due_date_assumes_bill_paid(self):
        d = fixture("georgia-short.json")
        d["costs"]["tax_bill_due_date"] = "10-15"  # Cobb County bills are due Oct 15; closing Nov 6
        C = compute.run(d)
        tax = next(r for r in C["rows"] if r["key"] == "tax_proration")
        self.assertIn("Bill Assumed Paid", tax["label"])
        self.assertEqual(tax["amounts"][0], round(3900 * 56 / 365))  # a credit back to the seller
        self.assertTrue(C["tax_assumed_paid"])
        self.assertFalse(C["tax_assumed_unpaid"])
        self.assertTrue(any("assumed paid" in a and "Oct 15" in a for a in C["assumptions"]))
        before = compute.run(fixture("georgia-short.json"))  # no due date: today's rule, a charge
        self.assertLess(next(r for r in before["rows"] if r["key"] == "tax_proration")["amounts"][0], 0)
        d["costs"]["tax_bill_due_date"] = "mid-October"
        with self.assertRaisesRegex(compute.NetSheetError, "tax_bill_due_date"):
            compute.run(d)

    def test_no_tax_bill_is_preliminary(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        self.assertIn("property tax proration isn't included", C["preliminary_reason"])

    def test_vague_closing_date_marked_assumed(self):
        d = fixture("florida-three-prices.json")
        d["closing_date_assumed"] = True
        C = compute.run(d)
        self.assertTrue(C["closing_date_assumed"])
        self.assertTrue(any(f["text"].startswith("Closing ") and f["text"].endswith("(Assumed)") for f in C["facts"]))
        self.assertTrue(any(a.startswith("Closing on") and "assumed" in a for a in C["assumptions"]))
        self.assertFalse(compute.run(fixture("florida-three-prices.json"))["closing_date_assumed"])

    def test_shortfalls_in_column_order_and_tile_label(self):
        C = compute.run(fixture("georgia-short.json"))
        prices = [c["price_display"] for c in C["columns"]]
        notes = [n for n in C["notes"] if "bring about" in n]
        self.assertEqual([next(p for p in prices if f"At {p} " in n) for n in notes], prices)
        self.assertEqual(C["columns"][0]["tile_label"], "Cash to Bring to Closing")
        self.assertEqual(C["columns"][0]["tile_display"], finance.money(-C["columns"][0]["net"]))
        doc = render.build_html(C, {})
        self.assertIn("Cash to Bring to Closing", doc)
        F = compute.run(fixture("florida-three-prices.json"))
        self.assertEqual(F["columns"][0]["tile_label"], "Estimated Net to Seller")

    def test_property_type_assumed(self):
        d = fixture("miami-condo-bill-paid.json")
        d["property"]["property_type_assumed"] = True
        C = compute.run(d)
        self.assertIn("Condo (Assumed)", [f["text"] for f in C["facts"]])
        self.assertTrue(any("assumed condo from the unit number" in a for a in C["assumptions"]))

    def test_market_notes_drop_mls(self):
        for name in ("texas-no-payoff.json", "florida-three-prices.json", "miami-condo-bill-paid.json"):
            self.assertFalse([n for n in compute.run(fixture(name))["market_notes"] if "MLS" in n or "--columns" in n])

    def test_builtin_estoppel_fee_is_noted(self):  # iteration 11: a built-in local fee says it's typical, like title fees
        r = compute.run(fixture("florida-three-prices.json"))
        self.assertTrue(any("estoppel fee is a typical Florida charge" in n for n in r["notes"]))
        # the deal's own figure (Miami fixture) and a national estimate (Texas, labeled on its line) need no note
        self.assertFalse(any("estoppel" in n for n in compute.run(fixture("miami-condo-bill-paid.json"))["notes"]))
        self.assertFalse(any("estoppel" in n for n in compute.run(fixture("texas-no-payoff.json"))["notes"]))


class Inputs(unittest.TestCase):
    def base(self):
        return copy.deepcopy(fixture("florida-three-prices.json"))

    def test_errors_for_the_agent(self):
        d = self.base()
        d["scenarios"] *= 2
        with self.assertRaisesRegex(compute.NetSheetError, "at most 3"):
            compute.run(d)
        d = self.base()
        del d["property"]["address"]
        with self.assertRaisesRegex(compute.NetSheetError, "address"):
            compute.run(d)
        d = self.base()
        d["costs"]["listing_fee_pct"] = 3
        with self.assertRaisesRegex(ValueError, "0.03 for 3%"):
            compute.run(d)
        d = self.base()
        d["scenarios"] = []
        with self.assertRaisesRegex(compute.NetSheetError, "at least one sale price"):
            compute.run(d)

    def test_default_labels_unique(self):
        d = self.base()
        d["scenarios"] = [{"price": 450000}, {"price": 450000, "seller_credit": 5000}, {"price": 450000}]
        self.assertEqual([c["label"] for c in compute.run(d)["columns"]],
                         ["$450,000 (Option 1)", "$450,000 with $5,000 Credit", "$450,000 (Option 3)"])

    def test_no_tax_bill_leaves_proration_out(self):
        d = self.base()
        del d["costs"]["annual_tax"]
        C = compute.run(d)
        self.assertNotIn("tax_proration", [r["key"] for r in C["rows"]])
        self.assertTrue(any(n.startswith("Not included: this year's property tax proration") for n in C["notes"]))

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
            self.assertEqual(C["columns"][0]["label"], "Recommended List Price")
            self.assertTrue(C["has_tax_proration"])
            with self.assertRaisesRegex(compute.NetSheetError, "not 9 Elm St"):
                compute.run({"property": {"address": "9 Elm St"}}, cma_path=path)
            with open(path, "w") as f:
                json.dump({**h, "side": "buyer"}, f)
            with self.assertRaisesRegex(compute.NetSheetError, "buyer"):
                compute.run({"property": {}}, cma_path=path)


class Render(unittest.TestCase):
    def test_tile_row_is_always_three_boxes(self):
        """One or two prices no longer stretch: the spare slots show seller costs and payoffs, or the difference."""
        one = compute.run(fixture("texas-no-payoff.json"))
        self.assertEqual([t["label"] for t in one["summary_tiles"]], ["Seller Costs", "Payoffs"])
        self.assertEqual(one["summary_tiles"][1]["display"], "Not Provided")  # the price tile already shows the net before payoff
        two = compute.run(fixture("miami-condo-bill-paid.json"))
        self.assertEqual(two["summary_tiles"][0]["label"], "Difference")
        self.assertTrue(two["summary_tiles"][0]["note"].startswith("More with"))
        short = compute.run(fixture("georgia-short.json"))  # the seller brings cash at both prices
        self.assertTrue(short["summary_tiles"][0]["note"].startswith("Less to bring with"))
        self.assertEqual(compute.run(fixture("florida-three-prices.json"))["summary_tiles"], [])
        for C in (one, two):
            doc = render.build_html(C, {}); self.assertEqual(doc.count('<div class="tile">') + doc.count('<div class="tile sum">'), 3)
        d = fixture("florida-three-prices.json")
        d["scenarios"] = d["scenarios"][:1]
        d.setdefault("costs", {})["mortgage_payoff"] = 0
        d["costs"].pop("other_payoffs", None)
        self.assertEqual(compute.run(d)["summary_tiles"][1]["display"], "$0")

    def test_no_fact_row_means_no_header_rule(self):
        """With no facts under the header the tiles sit right under it, and the header's rule is dropped (as in the
        other reports), so it doesn't collide with the tiles' border."""
        C = compute.run(fixture("florida-three-prices.json"))
        self.assertIn('class="divrow factrow"', render.build_html(C, {}))
        doc = render.build_html(dict(C, facts=[]), {})
        self.assertNotIn("factrow", doc.split("<style>")[-1].split("</style>")[-1])
        self.assertIn("header:has(+ .tiles){border-bottom:none", doc)

    def test_one_page_pdf(self):
        """Three prices with every optional line still print on one page."""
        d = fixture("florida-three-prices.json")
        d["scenarios"][1].update({"home_warranty": 600, "repairs": 3500, "closing_date": "2026-11-30"})
        d["costs"]["other"] += [{"label": "Permit Closeout", "amount": 800}, {"label": "Attorney Fee", "amount": 650}]
        agent = {"name": "Jordan Avery", "brokerage": "Sample Realty, LLC", "disclaimers": "Information deemed reliable."}
        with tempfile.TemporaryDirectory() as tmp:
            (path,) = render.build(d, "pdf", tmp, {"agent": agent, "sample": True})
            with open(path, "rb") as f:
                pdf = f.read()
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf)), 1)

    def test_long_disclaimer_drops_the_chart_not_the_page(self):
        d = fixture("florida-three-prices.json")
        d["scenarios"][1].update({"home_warranty": 600, "repairs": 3500, "closing_date": "2026-11-30"})
        para = "This brokerage's disclaimer runs long, as some states and brokerages require, line after line. " * 3
        agent = {"name": "Jordan Avery", "brokerage": "Sample Realty, LLC", "disclaimers": "\n\n".join([para] * 6)}
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            (path,) = render.build(d, "pdf", tmp, {"agent": agent})
            with open(path, "rb") as f:
                self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", f.read())), 1)
        self.assertIn("chart was left out", err.getvalue())

    def test_long_default_label_never_clips(self):
        """Iteration 9 eval 1: the default "$450,000 with $9,000 Credit" was cut off in the table header. It wraps now,
        and a label that still can't fit stops the render."""
        d = fixture("florida-three-prices.json")
        for x in d["scenarios"]:
            x.pop("label", None)
        with tempfile.TemporaryDirectory() as tmp:
            (path,) = render.build(d, "pdf", tmp, {"agent": {}})
            self.assertTrue(os.path.exists(path))
            d["scenarios"][2]["label"] = "Listpricewithsellercreditandhomewarranty"
            with self.assertRaisesRegex(compute.NetSheetError, "cut off"):
                render.build(d, "pdf", tmp, {"agent": {}})

    def test_html_marks_preliminary_and_short(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        doc = render.build_html(C, {})
        self.assertIn("Preliminary:", doc)
        self.assertIn("Payoff Not Provided", doc)
        doc = render.build_html(compute.run(fixture("georgia-short.json")), {})
        self.assertIn('class="short"', doc)


if __name__ == "__main__":
    unittest.main()


class ResultsV4(unittest.TestCase):
    """Results_v4 case 09: no "Seller Side" pill, the agent's name as a signature, headers that fit one line."""

    def test_header(self):
        doc = render.build_html(compute.run(fixture("florida-three-prices.json")), {"name": "Axel Rivera", "brokerage": "LPT Realty"})
        self.assertNotIn("Seller Side", doc)
        self.assertIn('<b class="agent">Axel Rivera</b>', doc)

    def test_columns_fit_their_headers(self):
        widths = render.column_widths(["$425,000", "$410,000", "$425,000 with $6,000 Credit"])
        self.assertAlmostEqual(sum(widths), 100, delta=0.2)
        self.assertGreater(widths[3], widths[1])  # the long header gets the room it needs
        need = (len("$425,000 with $6,000 Credit") * render.HEAD_PX_PER_CHAR + 16) / render.TABLE_PX * 100
        self.assertGreaterEqual(widths[3], need - 0.1)
        self.assertGreaterEqual(widths[0], render.MIN_FIRST)
        self.assertEqual(render.column_widths(["A"] * 3)[1:], [render.MIN_COL] * 3)
