import os
import sys
import unittest

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
        expected = (449900 * 5.249 + 424900 * (17.5683 - 5.249)) / 1000  # first $25k all levies, second non-school
        self.assertAlmostEqual(t["annual"], expected)
        self.assertFalse(t["estimated"])

    def test_no_homestead(self):
        t = f.property_tax(400000, FL, school_mills=5.249, total_mills=13.679, homestead=False)
        self.assertAlmostEqual(t["annual"], 400000 * 13.679 / 1000)

    def test_fallback_rate_and_unknown(self):
        self.assertAlmostEqual(f.property_tax(400000, FL)["annual"], 400000 * 0.018)
        tx = profiles.load_market(state="TX")
        self.assertIsNone(f.property_tax(400000, tx)["annual"])

    def test_millage_lookup(self):
        self.assertEqual(f.millage(FL, county="Seminole County", district="Altamonte")[0]["total"], 17.5683)


class SellerSide(unittest.TestCase):
    def test_title_premium_florida(self):
        tiers = FL.get("closing_costs.owner_title.rate_tiers")
        self.assertEqual(f.title_premium(474900, tiers), round(575 + 374900 * 5 / 1000))
        self.assertEqual(f.title_premium(80000, tiers), 460)

    def test_seller_net_florida(self):
        n = f.seller_net(465000, FL, credit=10000, payoff=200000, has_hoa=True)
        labels = [a for a, _ in n["items"]]
        self.assertIn("Documentary stamp tax on the deed (0.70%)", labels)
        self.assertEqual([x["key"] for x in n["lines"]],
                         ["listing_fee", "buyer_broker_fee", "transfer_tax", "owner_title", "title_fees", "estoppel", "credit"])
        self.assertAlmostEqual(sum(x["amount"] for x in n["lines"]), n["total_costs"])
        self.assertIn("Owner's title insurance", labels)
        self.assertIn("HOA estoppel letter", labels)
        self.assertEqual(n["missing"], [])
        self.assertEqual([a["key"] for a in n["assumed"]], ["listing_fee", "buyer_broker_fee", "title_fees"])  # built-in defaults
        quoted = f.seller_net(465000, FL, title_fees=900)
        self.assertEqual(next(x["amount"] for x in quoted["lines"] if x["key"] == "title_fees"), 900)
        self.assertNotIn("title_fees", [a["key"] for a in quoted["assumed"]])
        self.assertAlmostEqual(n["net"], n["net_before_payoff"] - 200000)

    def test_buyer_pays_title_county(self):
        miami = profiles.load_market(state="FL", county="Miami-Dade")
        labels = [a for a, _ in f.seller_net(500000, miami)["items"]]
        self.assertNotIn("Owner's title insurance", labels)

    def test_other_state_reports_missing(self):
        n = f.seller_net(500000, profiles.load_market(state="TX"), listing_fee_pct=0.03, buyer_broker_fee_pct=0.025)
        self.assertIn("deed transfer tax", n["missing"])
        self.assertIsNone(n["net"])


if __name__ == "__main__":
    unittest.main()
