"""The buyer CMA and the offer strategy use one closing-cost rule and one insurance estimate (shared/finance.py), so
the two reports give the same cash to close at the same price."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

(cma_compute,) = load("buyer-cma", "compute")
(seller_compute,) = load("seller-cma", "compute")
(strategy,) = load("buyer-offer-strategy", "strategy")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def cma_report():
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    R["costs"]["credit_scenarios"].pop("closing_cost_pct")  # the market's estimate, not the agent's share
    return R


class SameCashToClose(unittest.TestCase):
    def setUp(self):
        R = cma_report()
        market, homes = cma_compute.load_inputs(R)
        self.R, self.C = R, cma_compute.compute(R, market, homes)

    def offer(self, financing="conventional", down=0.05):
        B = {"analysis_date": "2026-09-26",
             "property": {"address": self.R["subject"]["address"] + ", Oviedo, FL", "county": "Seminole",
                          "list_price": self.R["subject"]["list_price"], "mls": "Stellar"},
             "buyer": {"financing": financing, "down_pct": down, "cash_available": 200000}}
        return strategy.analyze(B, cma=self.C["handoff"])

    def test_same_closing_costs_and_cash_at_the_same_price(self):
        pay = self.C["payments"]
        row = pay["rows"][0]  # Conventional, 5% Down
        r = self.offer()
        self.assertEqual(strategy.closing_costs(r["B"], pay["price"]), row["closing_costs"])
        self.assertEqual(round(pay["price"] * 0.05) + strategy.closing_costs(r["B"], pay["price"]), round(row["cash_to_close"]))
        # the credit table's columns are on the same rule
        for col in self.C["credit"]["columns"]:
            self.assertEqual(col["closing_costs"], strategy.closing_costs(r["B"], col["price"]))

    def test_fha_too(self):
        pay = self.C["payments"]
        row = next(x for x in pay["rows"] if x["label"].startswith("FHA"))
        r = self.offer("fha", 0.035)
        self.assertEqual(strategy.closing_costs(r["B"], pay["price"]), row["closing_costs"])

    def test_agent_share_wins_in_both(self):
        R = cma_report()
        R["costs"]["credit_scenarios"]["closing_cost_pct"] = 0.04
        market, homes = cma_compute.load_inputs(R)
        C = cma_compute.compute(R, market, homes)
        self.assertEqual(C["payments"]["rows"][0]["closing_costs"], round(C["payments"]["price"] * 0.04))
        self.assertTrue(C["payments"]["closing"]["given"])


class SameInsuranceEstimate(unittest.TestCase):
    def test_cma_estimates_when_left_out(self):
        R = cma_report()
        R["costs"]["payment"].pop("insurance_annual")
        R["subject"]["year_built"] = 1972
        market, homes = cma_compute.load_inputs(R)
        C = cma_compute.compute(R, market, homes)
        price = C["payments"]["price"]
        # Florida 0.9% x 1.5 for a 1972 home, to the $100: the same rule the offer strategy uses
        self.assertEqual(C["payments"]["insurance_annual"], round(price * 0.009 * 1.5, -2))
        self.assertTrue(C["payments"]["insurance"]["estimated"])
        self.assertEqual(C["placeholders"]["insurance_annual"], cma_compute.money(round(price * 0.009 * 1.5, -2)))

    def test_cma_uses_the_agents_insurance_rate(self):
        """profiles.with_deal maps costs.insurance_rate to the seller's holding costs; the buyer's estimate still uses it."""
        R = cma_report()
        R["costs"]["payment"].pop("insurance_annual")
        R["costs"]["insurance_rate"] = 0.012
        market, homes = cma_compute.load_inputs(R)
        C = cma_compute.compute(R, market, homes)
        self.assertEqual(C["payments"]["insurance_annual"], round(C["payments"]["price"] * 0.012, -2))
        self.assertEqual(C["payments"]["insurance"]["source"], "agent")

    def test_given_premium_is_kept(self):
        R = cma_report()
        market, homes = cma_compute.load_inputs(R)
        C = cma_compute.compute(R, market, homes)
        self.assertEqual(C["payments"]["insurance_annual"], 3600)
        self.assertFalse(C["payments"]["insurance"]["estimated"])


class SellerCmaInsurance(unittest.TestCase):
    def test_left_out_is_the_shared_estimate(self):
        with open(os.path.join(ROOT, "dev", "fixtures", "seller-cma", "hickorywood.json")) as f:
            R = json.load(f)
        R["export"] = os.path.join(ROOT, R["export"])
        R["deck"] = os.path.join(ROOT, R["deck"])
        R["buyer_payment"].pop("insurance_annual")
        market, homes = seller_compute.load_inputs(R)
        C = seller_compute.compute(R, market, homes)
        price = R["recommendation"]["list_price"]
        est = seller_compute.finance.insurance_estimate(price, market, R["subject"].get("year_built"))["annual"]
        self.assertEqual(C["payments"]["insurance_annual"], est)
        self.assertIn("insurance_estimated", C["assumption_keys"])
        self.assertNotIn("placeholder", " ".join(C["assumptions"]).lower())


if __name__ == "__main__":
    unittest.main()
