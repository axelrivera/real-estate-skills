"""Seller net sheet (skills/seller-net-sheet/scripts): the money rules (taxes, payoffs), which notes a sheet carries
(by key), input errors, and the page's structure. Every fixture's computed facts are pinned by
dev/golden/seller-net-sheet/; properties that hold for any input (columns add up, each note once, one page, nothing
clipped, figures from the model) are in test_generated_seller_net_sheet.py."""
import copy
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
compute, render, handoff, finance, fmt, profiles = load(
    "seller-net-sheet", "compute", "render", "_shared.handoff", "_shared.finance", "_shared.fmt", "_shared.profiles")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def tax_row(C):
    return next(r for r in C["rows"] if r["key"] == "tax_proration")


class SharedMath(unittest.TestCase):
    def test_matches_seller_cma_net(self):
        """The same price, credit and costs give seller-cma's lines, each rounded once: one shared calculator."""
        costs = {"listing_fee_pct": 0.025, "buyer_broker_fee_pct": 0.025, "mortgage_payoff": 301000, "annual_tax": 6900,
                 "expected_closing_date": "2026-11-20", "hoa": True}
        R = {"subject": {"address": "2250 Oak Hollow Ct", "state": "FL", "county": "Seminole", "property_type": "single_family"},
             "costs": costs, "pricing": {"strategies": [{"list_price": 515000, "expected_sale": 515000, "seller_credit": 10000}]}}
        market = profiles.load_market(state="FL", county="Seminole").with_deal(costs)
        closing = [{"date": cma_compute.fmt.to_date("2026-11-20"), "hold_months": None, "months_to_contract": None}]
        net = cma_compute.net_sheet(R, market, R["pricing"]["strategies"], closing, cma_compute.fmt.to_date("2026-09-26"))
        want = net["ledgers"][0].total()
        data = {"property": {"address": "2250 Oak Hollow Ct", "state": "FL", "county": "Seminole", "property_type": "single_family",
                             "hoa": True},
                "closing_date": "2026-11-20", "scenarios": [{"price": 515000, "seller_credit": 10000}],
                "costs": {k: v for k, v in costs.items() if k not in ("expected_closing_date", "hoa")}}
        self.assertEqual(compute.run(data)["columns"][0]["net"], want)

    def test_no_mls_notes(self):
        """A net sheet reads no MLS export: the market's MLS notes never reach it."""
        for name in ("florida-three-prices.json", "texas-no-payoff.json"):
            self.assertFalse([n for n in compute.run(fixture(name))["market_notes"] if "MLS" in n])


class TaxProration(unittest.TestCase):
    def test_bill_unpaid_before_due_date(self):
        """Closing before the bill is due: a charge from Jan 1 to closing, less Florida's 4% early-payment discount."""
        C = compute.run(fixture("florida-three-prices.json"))
        self.assertTrue(C["tax_assumed_unpaid"])
        self.assertEqual(-tax_row(C)["amounts"][0], fmt.half_up(6200 * 0.96 * 348 / 365))  # Jan 1 to Dec 14

    def test_closing_after_due_date_assumes_bill_paid(self):
        d = fixture("georgia-short.json")
        self.assertLess(tax_row(compute.run(d))["amounts"][0], 0)  # no due date: a charge
        d["costs"]["tax_bill_due_date"] = "10-15"  # Cobb County bills are due Oct 15; closing Nov 6
        C = compute.run(d)
        self.assertEqual(tax_row(C)["amounts"][0], fmt.half_up(3900 * 56 / 365))  # a credit back to the seller
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

    def test_one_proration_note_whichever_way_the_bill_falls(self):
        """One "tax" note on every sheet with a proration; closings on both sides of the due date share one row and
        add the unpaid-bill assumption once."""
        d = fixture("georgia-short.json")
        d["costs"]["tax_bill_due_date"] = "11-01"
        d["scenarios"][1]["closing_date"] = "2026-10-20"  # before the due date (the other closes Nov 6)
        C = compute.run(d)
        self.assertEqual([k for k in C["note_keys"] if k.startswith("tax")], ["tax", "tax_bill_unpaid"])
        self.assertEqual(len([r for r in C["rows"] if r["key"] == "tax_proration"]), 1)
        amounts = tax_row(C)["amounts"]
        self.assertTrue(amounts[0] > 0 > amounts[1])  # a credit back at one closing, a charge at the other
        for name in ("florida-three-prices.json", "miami-condo-bill-paid.json"):
            keys = compute.run(fixture(name))["note_keys"]
            self.assertEqual([k for k in keys if k.startswith("tax")], ["tax"])


class Payoff(unittest.TestCase):
    """A stated payoff is used as given; a balance gets a month's interest at the loan's rate, else 4.5%."""

    def test_payoff_from_balance(self):
        base = fixture("florida-credit-manual-v5.json")
        for costs, want, est in (({"mortgage_payoff": 188000}, 188000, False),
                                 ({"mortgage_balance": 188000}, fmt.half_up(188000 * (1 + 4.5 / 1200)), True),
                                 ({"mortgage_balance": 188000, "mortgage_rate": 6}, fmt.half_up(188000 * 1.005), True)):
            with self.subTest(costs):
                d = copy.deepcopy(base)
                d["costs"] = {k: v for k, v in d["costs"].items() if k != "mortgage_payoff"} | costs
                C = compute.run(d)
                self.assertEqual(-next(r for r in C["rows"] if r.get("key") == "payoff")["amounts"][0], want)
                self.assertIn("payoff", C["note_keys"])
                self.assertEqual("payoff" in C["assumption_keys"], est)  # an estimate from a balance is an assumption

    def test_short_sale_tile_is_cash_to_bring(self):
        C = compute.run(fixture("georgia-short.json"))
        self.assertTrue(all(c["short"] for c in C["columns"]))
        self.assertTrue(C["warnings"])
        self.assertEqual(C["columns"][0]["tile_display"], fmt.money(-C["columns"][0]["net"]))
        F = compute.run(fixture("florida-three-prices.json"))
        self.assertNotEqual(C["columns"][0]["tile_label"], F["columns"][0]["tile_label"])

    def test_unknown_payoff_makes_it_preliminary(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        self.assertTrue(C["preliminary"])
        self.assertFalse(C["cash_at_closing"])
        self.assertEqual(C["summary_tiles"], [])  # no payoff tile to show: the slot stays empty


class Assumptions(unittest.TestCase):
    def test_assumed_inputs_are_noted_once(self):
        """An assumed closing date or property type adds its note (by key) to the reply's assumption lines."""
        for name, change, key in (("florida-three-prices.json", lambda d: d.update(closing_date_assumed=True), "closing_date"),
                                  ("miami-condo-bill-paid.json", lambda d: d["property"].update(property_type_assumed=True),
                                   "property_type")):
            with self.subTest(name):
                d = fixture(name)
                before = compute.run(d)
                change(d)
                C = compute.run(d)
                self.assertNotIn(key, before["note_keys"])
                self.assertIn(key, C["note_keys"])
                self.assertEqual(len(C["assumptions"]), len(before["assumptions"]) + 1)

    def test_no_hoa_assumed_only_when_nobody_said(self):
        """No HOA mentioned (and not a condo): assumed none, said once in the reply, never on the page."""
        d = fixture("texas-no-payoff.json")
        C = compute.run(d)
        self.assertIn("no_hoa", C["note_keys"])
        self.assertEqual(len(C["assumptions"]) - len(set(C["assumptions"]) & set(C["notes"])), 2)  # with the commission
        for prop in ({"hoa": False}, {"hoa": True}, {"hoa_monthly": 120}, {"property_type": "condo"}):
            with self.subTest(prop):
                e = copy.deepcopy(d)
                e["property"].update(prop)
                self.assertNotIn("no_hoa", compute.run(e)["note_keys"])

    def test_texas_never_gets_florida_numbers(self):
        C = compute.run(fixture("texas-no-payoff.json"))
        self.assertNotIn("transfer_tax", [r["key"] for r in C["rows"]])
        self.assertFalse(any("0.70%" in r["label"] for r in C["rows"]))
        self.assertIn("transfer_tax", C["note_keys"])  # says why there's no line
        self.assertIn("national", C["note_keys"])

    def test_builtin_estoppel_fee_is_noted(self):
        """A built-in local fee is noted as a typical charge; the deal's own figure or a national estimate is not."""
        for name, noted in (("florida-three-prices.json", True), ("miami-condo-bill-paid.json", False),
                            ("texas-no-payoff.json", False)):
            self.assertEqual("estoppel" in compute.run(fixture(name))["note_keys"], noted, name)


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

    def test_labels_are_names_never_figures(self):
        """The sheet prints every price, amount and date itself; a label with a figure is refused."""
        for change in (lambda d: d["scenarios"][0].update(label="At $450,000"),
                       lambda d: d["scenarios"][1].update(label="Price Cut of 2%"),
                       lambda d: d["scenarios"][2].update(label="December Closing"),
                       lambda d: d["costs"]["other"].append({"label": "Survey 2026", "amount": 100}),
                       lambda d: d["costs"]["other_payoffs"].append({"label": "HELOC #2", "amount": 100})):
            d = fixture("florida-three-prices.json")
            change(d)
            with self.assertRaisesRegex(compute.NetSheetError, "figure"):
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
            data = {"property": {}, "closing_date": "2026-11-20"}
            C = compute.run(data, cma_path=path)
            self.assertEqual(data, {"property": {}, "closing_date": "2026-11-20"})  # the input is never changed
            self.assertEqual(C["columns"][0]["price"], 515000)
            self.assertTrue(C["has_tax_proration"])
            with self.assertRaisesRegex(compute.NetSheetError, "9 Elm St"):
                compute.run({"property": {"address": "9 Elm St"}}, cma_path=path)
            with open(path, "w") as f:
                json.dump({**h, "side": "buyer"}, f)
            with self.assertRaisesRegex(compute.NetSheetError, "buyer"):
                compute.run({"property": {}}, cma_path=path)


class Page(unittest.TestCase):
    def test_tile_row_is_always_three_slots(self):
        """One or two prices fill spare slots with figures already on the sheet (payoffs, the difference) or leave
        them empty; the row is three slots wide either way."""
        for name, spare in (("texas-no-payoff.json", 0), ("miami-condo-bill-paid.json", 1),
                            ("florida-one-price.json", 1), ("florida-three-prices.json", 0)):
            with self.subTest(name):
                C = compute.run(fixture(name))
                self.assertEqual(len(C["summary_tiles"]), spare)
                doc = render.build_html(C, {})
                self.assertEqual(len(re.findall(r'class="kit-tile[ "]', doc)), compute.MAX_SCENARIOS)

    def test_no_fact_row_means_no_header_rule(self):
        C = compute.run(fixture("florida-three-prices.json"))
        self.assertIn("factrow", render.build_html(C, {}).split("</style>")[-1])
        doc = render.build_html(dict(C, facts=[]), {})
        self.assertNotIn("factrow", doc.split("</style>")[-1])
        self.assertIn("header:has(+ .net-tiles){border-bottom:none", doc)

    def test_bundled_font(self):
        self.assertIn("<body class='font-bundled'>", render.build_html(compute.run(fixture("florida-two-prices.json")), {}))


if __name__ == "__main__":
    unittest.main()
