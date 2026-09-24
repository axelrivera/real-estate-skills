"""Tests for skills/buyer-cma/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "skills", "buyer-cma")
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
        # CORE-17: the 2026 indexed homestead ($26,411 off non-school levies) lowers tax about $17/yr
        self.assertEqual([round(r["total"]) for r in rows], [4106, 4228, 3446])
        self.assertEqual([round(r["cash_down"]) for r in rows], [23745, 16622, 94980])
        self.assertEqual(round(self.C["payments"]["per_10k"] / 5) * 5, 80)

    def test_credit_scenarios(self):
        cols = self.C["credit"]["columns"]
        self.assertEqual([round(c["cash"], -2) for c in cols], [36400, 31800, 27200])
        # CORE-17: the 2026 indexed homestead ($26,411 off non-school levies) lowers tax about $17/yr
        self.assertEqual([round(c["payment"]) for c in cols], [3944, 3985, 4025])
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
        self.assertIn("--subject:var(--party-both-ink)", doc)  # DS-3: the neutral subject accent, never a status color

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



class Flood(unittest.TestCase):
    """CMA-6: the payment has a flood line, a quote or "Get a Quote", never $0."""

    def run_(self, **payment):
        R = report()
        R["costs"]["payment"].update(payment)
        market, homes = compute.load_inputs(R)
        return R, compute.compute(R, market, homes)

    def test_get_a_quote(self):
        R, C = self.run_()
        pay = C["payments"]
        self.assertIsNone(pay["flood"]["annual"])
        self.assertTrue(all(r["flood"] is None for r in pay["rows"]))
        self.assertIn("Citizens", pay["flood"]["note"])  # zone X from the facts, Florida, 2026
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertIn("Flood Insurance", html)
        self.assertIn("Get a Quote", html)
        self.assertNotIn("isn't required", html)

    def test_quote_counts(self):
        _, base = self.run_()
        _, C = self.run_(flood_insurance_annual=1800)
        for a, b in zip(base["payments"]["rows"], C["payments"]["rows"]):
            self.assertAlmostEqual(b["total"] - a["total"], 150)
        self.assertNotIn("Get a quote", C["payments"]["flood"]["note"])

    def test_zone_override(self):
        _, C = self.run_(flood_zone="AE")
        self.assertEqual(C["payments"]["flood"]["required"], "lender")


class LoanTaxes(unittest.TestCase):
    """CORE-16: without a lender figure, the credit scenarios add Florida's loan taxes on the loan amount."""

    def test_itemized_without_a_lender_figure(self):
        R = report()
        R["costs"]["credit_scenarios"].pop("closing_cost_pct")
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        col = C["credit"]["columns"][0]
        loan = col["loan"]
        self.assertEqual(col["loan_taxes"], round(loan * 0.0035) + round(loan * 0.002))
        self.assertAlmostEqual(col["closing_costs"], col["price"] * 0.025 + col["loan_taxes"])

    def test_lender_figure_is_left_alone(self):
        R = report()  # the fixture gives closing_cost_pct 0.03: the lender's, taxes included
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertEqual(C["credit"]["columns"][0]["loan_taxes"], 0)


class AuditMethod(unittest.TestCase):
    """CMA-10, CMA-11, CMA-14, CMA-15, CMA-17, CMA-20."""

    def run_(self, R, **kw):
        market, homes = compute.load_inputs(R, **kw)
        return compute.compute(R, market, homes)

    def test_adjustment_rates_outside_their_area_warn(self):
        C = self.run_(report())
        self.assertFalse(any("adjustment rates" in w for w in C["warnings"]))  # Seminole, $474,900: inside
        R = report()
        R["subject"]["county"] = "Hillsborough"  # Stellar, but not where the rates were set
        C = self.run_(R)
        self.assertTrue(any("don't fit Hillsborough County" in w for w in C["warnings"]))

    def test_price_minus_credit_is_not_called_the_same_net(self):
        R = report()
        R["costs"]["credit_scenarios"]["seller_pays_buyer_broker_pct"] = 0.025
        C = self.run_(R)
        self.assertEqual(C["credit"]["seller_cost_per_10k"], 320)  # 0.7% doc stamps + 2.5% buyer-broker pay
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertNotIn("Same Seller Net", html)
        self.assertIn("about $320 in transfer tax and buyer-broker pay, plus their listing fee", html)

    def test_no_homestead_label(self):
        R = report()
        R["costs"]["taxes"]["homestead"] = False
        C = self.run_(R)
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertNotIn("With Homestead", html)
        self.assertIn("Your Estimated Tax Bill, No Homestead", html)

    def test_mls_option(self):
        R = report()
        R["subject"]["county"] = "Brevard"  # not Stellar: no MLS assumed, so the export can't be read
        with self.assertRaises(compute.mls.ExportError):
            compute.load_inputs(R)
        market, homes = compute.load_inputs(R, mls_name="Stellar")
        self.assertEqual(market.mls, "Stellar")
        self.assertTrue(homes)

    def test_handoff_file_has_the_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            self.assertTrue(json.loads(out.getvalue())["handoff_file"].endswith(".buyer.cma.json"))

    def test_offer_ladder_order(self):
        R = report()
        R["offer_plan"]["opening"] = R["offer_plan"]["walk_away"] + 5000
        with self.assertRaisesRegex(compute.ReportError, "opening"):
            self.run_(R)

if __name__ == "__main__":
    unittest.main()


class AuditBuyerBrokerShortfall(unittest.TestCase):
    def test_shortfall_row_and_cash(self):
        """CMA-4: a 2.5% agreement with the seller paying 0 adds the full fee to cash to close."""
        R = report()
        market, homes = compute.load_inputs(R)
        base = compute.compute(R, market, homes)["credit"]["columns"]
        R["costs"]["credit_scenarios"].update(buyer_broker_agreement_pct=0.025, seller_pays_buyer_broker_pct=0)
        cols = compute.compute(R, market, homes)["credit"]["columns"]
        for b, c in zip(base, cols):
            self.assertEqual(c["bb_short"], round(0.025 * c["price"]))
            self.assertEqual(round(c["cash"] - b["cash"]), c["bb_short"])
        doc, _ = buyer_render.build_html(copy.deepcopy(R), compute.compute(R, market, homes), homes,
                                         {"name": None, "brokerage": None, "brand": {}})
        self.assertIn("Broker Fee (Not Paid by Seller)", doc)
