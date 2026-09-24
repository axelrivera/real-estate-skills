"""Tests for plugins/transactions/skills/buyer-cma/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "plugins", "transactions", "skills", "buyer-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, buyer_render, handoff, profiles = load(
    "buyer-cma", "compute", "render", "_shared.handoff", "_shared.profiles")

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")


def report():
    with open(FIXTURE) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    return R


class MatchesPrototype(unittest.TestCase):
    """Figures printed in the prototype's 517-Hickorywood-Buyer-CMA.pdf."""

    @classmethod
    def setUpClass(cls):
        R = report()
        market, homes = compute.load_inputs(R)
        cls.C = compute.compute(R, market, homes)

    def test_taxes(self):
        self.assertEqual([t["annual_display"] for t in self.C["taxes"]], ["$5,900", "$7,600"])

    def test_payments(self):
        rows = self.C["payments"]["rows"]
        self.assertEqual([round(r["total"]) for r in rows], [4107, 4230, 3448])
        self.assertEqual([round(r["cash_down"]) for r in rows], [23745, 16622, 94980])
        self.assertEqual(round(self.C["payments"]["per_10k"] / 5) * 5, 80)

    def test_credit_scenarios(self):
        cols = self.C["credit"]["columns"]
        self.assertEqual([round(c["cash"], -2) for c in cols], [36400, 31800, 27200])
        self.assertEqual([round(c["payment"]) for c in cols], [3945, 3986, 4027])
        self.assertEqual([round(c["payback_years"]) if c["payback_years"] else None for c in cols], [None, 9, 9])
        self.assertFalse(any(c["over_cap"] or c["over_costs"] for c in cols))
        self.assertFalse(self.C["credit"]["buydown"]["covered"])
        self.assertEqual(round(self.C["credit"]["buydown"]["cost"], -2), 10300)

    def test_no_warnings_and_handoff(self):
        self.assertEqual(self.C["warnings"], [])
        h = handoff.parse_text("reply\n" + self.C["handoff_block"])
        self.assertEqual(h["value"]["median_adjusted"], 469800)
        self.assertEqual(h["offer_plan"]["opening"], 455000)
        self.assertEqual(h["market_profile"], {"state": "FL", "mls": "Stellar"})
        self.assertIn("months_supply", h["market"])


class Warnings(unittest.TestCase):
    def test_credit_over_program_limit(self):
        R = report()
        R["costs"]["credit_scenarios"]["scenarios"].append({"price": 480000, "credit": 25000})
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertTrue(any("over the loan program's limit" in w for w in C["warnings"]))

    def test_walk_away_above_range_and_credit_alt_mismatch(self):
        R = report()
        R["offer_plan"]["walk_away"] = 490000
        R["offer_plan"]["credit_alt"] = {"price": 470000, "credit": 7000}
        market, homes = compute.load_inputs(R)
        w = compute.compute(R, market, homes)["warnings"]
        self.assertTrue(any("walk-away" in x for x in w))
        self.assertTrue(any("credit_alt" in x for x in w))

    def test_missing_field(self):
        R = report()
        del R["bottom_line"]["low"]
        market, homes = compute.load_inputs(R)
        with self.assertRaises(compute.ReportError):
            compute.compute(R, market, homes)


    def test_input_checks(self):
        """CMA-19, CMA-21: formatted numbers, no comps and a scenario without down_pct are plain errors."""
        for change in (lambda R: R["competition"]["rows"][0].__setitem__(2, "$474,500"),
                       lambda R: R["comps"].__setitem__("cards", []),
                       lambda R: R["costs"]["payment"]["scenarios"][0].pop("down_pct")):
            R = report()
            change(R)
            market, homes = compute.load_inputs(R)
            with self.assertRaises(compute.ReportError):
                compute.compute(R, market, homes)

    def test_thin_comps_warn(self):
        R = report()
        R["comps"]["cards"] = R["comps"]["cards"][:2]
        market, homes = compute.load_inputs(R)
        self.assertTrue(any("Only 2 comps" in w for w in compute.compute(R, market, homes)["warnings"]))

    def test_no_current_bill(self):
        """CMA-13: new construction has no tax bill; the report renders "Not available"."""
        R = report()
        del R["costs"]["taxes"]["current_bill"]
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, homes, {"name": None, "brokerage": None, "brand": {}})
        self.assertIn("Not available", doc)

class OtherMarkets(unittest.TestCase):
    def test_texas_without_millage_has_no_payment_table(self):
        R = report()
        R["subject"].update(state="TX", county="Travis")
        R.pop("export")
        for j in R["costs"]["taxes"]["jurisdictions"]:
            j.pop("school_mills", None), j.pop("total_mills", None)
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertIsNone(C["payments"])
        self.assertTrue(any("No millage or tax rate" in w for w in C["warnings"]))

    def test_explicit_millage_works_anywhere(self):
        R = report()
        R["subject"].update(state="TX", county="Travis")
        R.pop("export")
        R["costs"]["taxes"]["jurisdictions"] = [{"label": "in Austin", "short": "Austin", "school_mills": 9.5, "total_mills": 19.0}]
        R["costs"]["payment"]["tax_jurisdiction_index"] = 0
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertAlmostEqual(C["taxes"][0]["annual"], 474900 * 19.0 / 1000)  # no Florida homestead in Texas
        self.assertIsNotNone(C["payments"])


class Pdf(unittest.TestCase):
    def test_brand_side_and_agent_fields(self):
        R = report()
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        agent = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
                 "email": None, "website": None, "brand": {"buyer_primary": "#0B6E4F"}}
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, homes, agent)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Buyer Summary", doc)  # the side shows in the page-1 label; no separate pill
        self.assertNotIn('class="tag', doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)
        self.assertIn("--subject:#B3261E", doc)  # subject accent stays the fixed risk red, not the brand

    def test_full_pdf(self):
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            import io
            with contextlib.redirect_stderr(io.StringIO()):
                paths = buyer_render.build(R, "pdf", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(handoff.load(paths[1])["side"], "buyer")


if __name__ == "__main__":
    unittest.main()
