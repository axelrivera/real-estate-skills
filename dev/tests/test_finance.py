import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import finance as f, profiles  # noqa: E402

FL = profiles.load_market(state="FL", county="Seminole")


class Payments(unittest.TestCase):
    def test_pi_payment(self):
        self.assertAlmostEqual(f.pi_payment(300000, 7.0), 1995.91, places=2)
        self.assertAlmostEqual(f.pi_payment(360000, 0), 1000.0)

    def test_conventional_mi_below_20_percent(self):
        p5 = f.monthly_payment(474900, "conv", 0.05, 6.95, 7596, 3600)
        p20 = f.monthly_payment(474900, "conventional", 0.20, 6.95, 7596, 3600)
        self.assertAlmostEqual(p5["mi"], 474900 * 0.95 * 0.005 / 12)
        self.assertEqual(p20["mi"], 0)
        self.assertAlmostEqual(p5["cash_down"], 23745)

    def test_fha_upfront_premium_in_loan(self):
        p = f.monthly_payment(400000, "fha", 0.035, 6.5, 6000, 3000)
        self.assertAlmostEqual(p["loan"], 400000 * 0.965 * 1.0175)

    def test_fraction(self):
        self.assertEqual(f.fraction(0.025, "x"), 0.025)
        self.assertEqual(f.fraction(None, "x", 0.05), 0.05)
        with self.assertRaisesRegex(ValueError, "0.025 for 2.5%"):
            f.fraction(2.5, "listing_fee_pct")

    def test_concession_caps(self):
        self.assertEqual(f.concession_cap("conv", 0.05), 0.03)
        self.assertEqual(f.concession_cap("conventional", 0.10), 0.06)
        self.assertEqual(f.concession_cap("conventional", 0.25), 0.09)
        self.assertEqual(f.concession_cap("fha", 0.035), 0.06)
        self.assertEqual(f.concession_cap("va", 0), 0.04)
        with self.assertRaises(ValueError):
            f.program("jumbo-ish")

    def test_buydown(self):
        b = f.buydown_2_1(441750, 6.95)
        self.assertLess(b["year1"], b["year2"])
        self.assertAlmostEqual(b["cost"], 12 * (b["full"] - b["year1"]) + 12 * (b["full"] - b["year2"]))


class Taxes(unittest.TestCase):
    def test_florida_homestead_matches_prototype(self):
        t = f.property_tax(474900, FL, school_mills=5.249, total_mills=17.5683)
        # First $25k off all levies; CORE-17: the second, indexed to $26,411 for 2026, off non-school levies
        expected = (449900 * 5.249 + (474900 - 25000 - 26411) * (17.5683 - 5.249)) / 1000
        self.assertAlmostEqual(t["annual"], expected)
        self.assertFalse(t["estimated"])

    def test_no_homestead(self):
        t = f.property_tax(400000, FL, school_mills=5.249, total_mills=13.679, homestead=False)
        self.assertAlmostEqual(t["annual"], 400000 * 13.679 / 1000)

    def test_fallback_rate_and_unknown(self):
        self.assertAlmostEqual(f.property_tax(400000, FL)["annual"], 400000 * 0.018)
        tx = profiles.load_market(state="TX")
        self.assertAlmostEqual(f.property_tax(400000, tx)["annual"], 400000 * 0.011)  # national estimate

    def test_texas_style_exemptions(self):
        class M:
            def __init__(self, d):
                self.d = d

            def get(self, path, default=None):
                return self.d.get(path, default)

        tx = M({"property_tax.primary_residence_exemptions": [{"amount": 100000, "levies": "school"},
                                                              {"percent": 0.20, "levies": "non_school"}]})
        # rate per $100 of 2.0 total, 1.0 school -> 20 and 10 mills
        t = f.property_tax(400000, tx, school_mills=10, total_mills=20)["annual"]
        self.assertAlmostEqual(t, (300000 * 10 + 320000 * 10) / 1000)

    def test_owner_title_quote(self):
        class M(dict):
            def get(self, path, default=None):
                return dict.get(self, path, default)

            def source(self, path):
                return "profile"

        m = M({"closing_costs.owner_title.payer": "seller",
               "closing_costs.owner_title.quote": {"price": 400000, "premium": 2400},
               "closing_costs.owner_title.estimate_pct": 0.01})
        n = f.seller_net(500000, m, listing_fee_pct=0, buyer_broker_fee_pct=0)
        self.assertEqual(next(x["amount"] for x in n["lines"] if x["key"] == "owner_title"), 3000)  # quote wins

    def test_millage_lookup(self):
        self.assertEqual(f.millage(FL, county="Seminole County", district="Altamonte")[0]["total"], 17.5683)


class SellerSide(unittest.TestCase):
    def test_title_premium_florida(self):
        tiers = FL.get("closing_costs.owner_title.rate_tiers")
        self.assertEqual(f.title_premium(474900, tiers), round(575 + 374900 * 5 / 1000))
        self.assertEqual(f.title_premium(80000, tiers), 460)

    def test_seller_net_florida(self):
        n = f.seller_net(465000, FL, credit=10000, payoff=200000, has_hoa=True, listing_fee_pct=0.025, buyer_broker_fee_pct=0.025)
        labels = [a for a, _ in n["items"]]
        self.assertIn("Documentary Stamp Tax on the Deed (0.70%)", labels)
        self.assertEqual([x["key"] for x in n["lines"]],
                         ["listing_fee", "buyer_broker_fee", "transfer_tax", "owner_title", "title_fees", "estoppel", "credit"])
        self.assertAlmostEqual(sum(x["amount"] for x in n["lines"]), n["total_costs"])
        self.assertIn("Owner's Title Insurance", labels)
        self.assertIn("HOA Estoppel Letter", labels)
        self.assertEqual(n["missing"], [])
        self.assertEqual([a["key"] for a in n["assumed"]], ["title_fees"])  # built-in local title fees
        default = f.seller_net(465000, FL)
        self.assertEqual(default["missing"], [])
        self.assertEqual([(a["key"], a["value"], a["estimate"]) for a in default["assumed"][:2]],
                         [("listing_fee", 0.025, True), ("buyer_broker_fee", 0.025, True)])  # 5% total assumed
        quoted = f.seller_net(465000, FL, title_fees=900)
        self.assertEqual(next(x["amount"] for x in quoted["lines"] if x["key"] == "title_fees"), 900)
        self.assertNotIn("title_fees", [a["key"] for a in quoted["assumed"]])
        self.assertAlmostEqual(n["net"], n["net_before_payoff"] - 200000)

    def test_buyer_pays_title_county(self):
        miami = profiles.load_market(state="FL", county="Miami-Dade")
        labels = [a for a, _ in f.seller_net(500000, miami)["items"]]
        self.assertNotIn("Owner's Title Insurance", labels)

    def test_other_state_uses_labeled_estimates(self):
        n = f.seller_net(500000, profiles.load_market(state="TX"), listing_fee_pct=0.03, buyer_broker_fee_pct=0.025)
        self.assertEqual(n["missing"], [])
        labels = {x["key"]: x["label"] for x in n["lines"]}
        self.assertEqual(labels["transfer_tax"], "Transfer Tax (Estimate, 0.40%)")
        self.assertEqual(labels["owner_title"], "Owner's Title Insurance (Estimate)")
        self.assertEqual(labels["title_fees"], "Title Company Fees (Estimate)")
        self.assertEqual({a["key"] for a in n["assumed"] if a["estimate"]}, {"transfer_tax", "owner_title", "title_fees"})
        deal = f.seller_net(500000, profiles.load_market(state="TX").with_deal({"transfer_tax_rate": 0}),
                            listing_fee_pct=0.03, buyer_broker_fee_pct=0.025)
        self.assertNotIn("transfer_tax", [x["key"] for x in deal["lines"]])  # Texas has none: the looked-up 0 wins



class FloodInsurance(unittest.TestCase):
    """CMA-6 (verified: s. 627.351(6)(aa) Citizens schedule; see docs/audits/2026-09-23-verification.md)."""

    FL = profiles.load_market(state="FL")

    def test_special_flood_hazard_area(self):
        for zone in ("AE", "VE", "A", "AO", "Zone AE"):
            r = f.flood_insurance(zone, None, self.FL, date(2026, 9, 24))
            self.assertEqual((r["sfha"], r["required"], r["annual"]), (True, "lender", None), zone)
            self.assertIn("lender will require", r["note"])

    def test_citizens_phase_in(self):
        r = f.flood_insurance("X (lower risk)", None, self.FL, date(2026, 9, 24))
        self.assertEqual(r["required"], "citizens_value")
        self.assertIn("$400,000", r["note"])
        self.assertIn("January 1, 2027", r["note"])
        self.assertNotIn("isn't required", r["note"])
        self.assertIn("$500,000", f.flood_insurance("X", None, self.FL, date(2025, 6, 1))["note"])
        self.assertEqual(f.flood_insurance("X", None, self.FL, date(2027, 1, 1))["required"], "citizens")

    def test_condo_unit_policy_is_exempt(self):
        r = f.flood_insurance("X", None, self.FL, date(2026, 9, 24), condo_unit=True)
        self.assertIsNone(r["required"])
        self.assertIn("HO-6", r["note"])

    def test_no_florida_rule_elsewhere(self):
        r = f.flood_insurance("X", None, None, date(2026, 9, 24))
        self.assertIsNone(r["required"])
        self.assertNotIn("Citizens", r["note"])

    def test_quote_is_counted_and_never_zero(self):
        self.assertIsNone(f.flood_insurance("AE", 0, self.FL)["annual"])  # 0 is not a quote
        self.assertIn("Get a quote", f.flood_insurance("AE", None, self.FL)["note"])
        base = f.monthly_payment(400000, "conventional", 0.2, 6.5, 6000, 3000)
        quoted = f.monthly_payment(400000, "conventional", 0.2, 6.5, 6000, 3000, flood_annual=1200)
        self.assertIsNone(base["flood"])
        self.assertAlmostEqual(quoted["total"] - base["total"], 100)


class AuditMarketMoney(unittest.TestCase):
    """CORE-9, CORE-16, CORE-17, CORE-19."""

    def test_quote_beats_promulgated_table_and_warns_below_it(self):
        m = profiles.load_market(state="FL", county="Seminole")
        m.data["closing_costs"]["owner_title"]["quote"] = {"price": 400000, "premium": 2000}
        n = f.seller_net(400000, m, listing_fee_pct=0, buyer_broker_fee_pct=0)
        line = next(x for x in n["lines"] if x["key"] == "owner_title")
        self.assertEqual((line["label"], line["amount"]), ("Owner's Title Insurance (Quote)", 2000))
        self.assertTrue(any("below the published rate ($2,075)" in w for w in n["warnings"]))

    def test_loan_taxes(self):
        self.assertEqual([t["amount"] for t in f.loan_taxes(300000, FL)], [1050, 600])  # 0.35% and 0.2% of the loan
        self.assertEqual(f.loan_taxes(0, FL), [])
        self.assertEqual(f.loan_taxes(300000, None), [])

    def test_second_homestead_exemption_starts_above_50000(self):
        low = f.property_tax(60000, FL, school_mills=5, total_mills=15)
        self.assertAlmostEqual(low["annual"], (35000 * 5 + (60000 - 25000 - 10000) * 10) / 1000)  # only $10,000 of it

    def test_layered_transfer_tax_warning(self):
        ny = profiles.load_market(state="NY")
        self.assertIn("mansion tax", f.transfer_tax_warning(ny))
        self.assertIsNone(f.transfer_tax_warning(FL))
        self.assertTrue(f.seller_net(900000, ny)["warnings"])


class AuditLoanPrograms(unittest.TestCase):
    """OFR-11 (loan limits, 2026 verified), OFR-25 (VA funding fee table, PMI by loan-to-value)."""

    def test_va_funding_fee(self):
        self.assertEqual(f.upfront_fee("va", 0), 0.0215)
        self.assertEqual(f.upfront_fee("va", 0, va_later_use=True), 0.033)
        self.assertEqual((f.upfront_fee("va", 0.05), f.upfront_fee("va", 0.10)), (0.015, 0.0125))
        self.assertEqual(f.upfront_fee("va", 0, va_exempt=True), 0.0)
        self.assertAlmostEqual(f.loan_amount(400000, "va", 0, va_exempt=True), 400000)

    def test_pmi_by_loan_to_value(self):
        self.assertEqual([f.annual_mi_rate("conventional", d) for d in (0.03, 0.05, 0.10, 0.15, 0.20)],
                         [0.0075, 0.005, 0.0035, 0.002, 0.0])
        self.assertEqual(f.annual_mi_rate("fha", 0.035), 0.0055)

    def test_loan_limits(self):
        lim = profiles.loan_limits()
        self.assertEqual((lim["year"], lim["conforming"]["baseline"], lim["fha"]["floor"]), (2026, 832750, 541287))
        self.assertIsNone(f.loan_limit_note(800000, "conventional", lim, "FL", "Orange"))
        self.assertIn("jumbo", f.loan_limit_note(900000, "conventional", lim, "FL", "Orange"))
        self.assertIsNone(f.loan_limit_note(900000, "conventional", lim, "FL", "Monroe"))  # $990,150 in Monroe
        self.assertIn("high-cost", f.loan_limit_note(900000, "conventional", lim, "CA", "Alameda"))
        self.assertIn("confirm the county", f.loan_limit_note(600000, "fha", lim, "FL", "Orange"))
        self.assertIn("can't be FHA", f.loan_limit_note(1300000, "fha", lim, "FL", "Orange"))
        self.assertIsNone(f.loan_limit_note(900000, "va", lim, "FL", "Orange"))

if __name__ == "__main__":
    unittest.main()


class AuditMoneyLines(unittest.TestCase):
    """CMA-3, OFR-14 (proration), CORE-6 (Miami-Dade surtax), CORE-18 (search fees), CMA-4 (buyer-broker shortfall)."""

    def test_proration_arrears_with_discount(self):
        p = f.tax_proration(6000, date(2026, 10, 1), FL)
        self.assertEqual(p["amount"], round(6000 * 0.96 * 273 / 365))  # Jan 1 through Sep 30, 4% discount allowed
        self.assertIn("Jan 1 to Closing", p["label"])
        paid = f.tax_proration(6000, date(2026, 12, 1), FL, bill_paid=True)
        self.assertEqual(paid["amount"], -round(6000 * 0.96 * 31 / 365))  # buyer credits the seller for December
        self.assertIsNone(f.tax_proration(None, date(2026, 12, 1), FL))
        n = f.seller_net(400000, FL, listing_fee_pct=0.025, buyer_broker_fee_pct=0, annual_tax=6000, closing=date(2026, 10, 1))
        self.assertEqual(next(x["amount"] for x in n["lines"] if x["key"] == "tax_proration"), p["amount"])

    def test_miami_dade_surtax_by_property_type(self):
        md = profiles.load_market(state="FL", county="Miami-Dade")
        keys = lambda **k: {x["key"]: x["amount"] for x in f.seller_net(600000, md, listing_fee_pct=0, buyer_broker_fee_pct=0, **k)["lines"]}  # noqa: E731
        self.assertEqual(round(keys(prop_type="Condo")["transfer_surtax"]), 2700)
        self.assertNotIn("transfer_surtax", keys(prop_type="single family"))
        self.assertIn("property type", " ".join(f.seller_net(600000, md, listing_fee_pct=0, buyer_broker_fee_pct=0)["missing"]))
        seminole = profiles.load_market(state="FL", county="Seminole")
        self.assertNotIn("transfer_surtax", {x["key"] for x in f.seller_net(600000, seminole, listing_fee_pct=0,
                                                                              buyer_broker_fee_pct=0, prop_type="condo")["lines"]})

    def test_buyer_pays_counties_move_the_search_fees(self):
        self.assertEqual(profiles.load_market(state="FL", county="Sarasota").get("closing_costs.seller_title_fees"),
                         {"settlement_fee": 700, "title_search": 0, "municipal_lien_search": 0, "recording": 70})
        self.assertEqual(profiles.load_market(state="FL", county="Broward").get("closing_costs.seller_title_fees.title_search"), 200)
        self.assertEqual(profiles.load_market(state="FL", county="Collier").get("closing_costs.owner_title.payer"), "buyer")

    def test_buyer_broker_shortfall(self):
        self.assertEqual(f.buyer_broker_shortfall(400000, 0.025, 0), 10000)
        self.assertEqual(f.buyer_broker_shortfall(400000, 0.025, 0.03), 0)
        self.assertIsNone(f.buyer_broker_shortfall(400000, None, 0.02))

    def test_property_type(self):
        self.assertEqual([f.property_type(v) for v in ("Single Family Residence", "Condominium", "Townhome", None)],
                         ["single_family", "condo", "townhouse", None])

