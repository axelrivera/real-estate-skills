"""The buyer CMA and the offer strategy agree: one closing-cost rule, one insurance estimate and one buyer-broker
shortfall (shared/finance.py), so the two reports give the same payment and cash to close at the same price, and the
CMA's handoff carries its premium and the property's legal description to the offer. The seller CMA uses the same
insurance estimate."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

cma_compute, handoff = load("buyer-cma", "compute", "_shared.handoff")
(seller_compute,) = load("seller-cma", "compute")
(strategy,) = load("buyer-offer-strategy", "strategy")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def cma_report(estimate_insurance=False):
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    R["costs"]["credit_scenarios"].pop("closing_cost_pct")  # the market's estimate, not the agent's share
    if estimate_insurance:
        R["costs"]["payment"].pop("insurance_annual")
    return R


def run_cma(R):
    market, homes = cma_compute.load_inputs(R)
    return cma_compute.compute(R, market, homes)


def offer_fixture(name):
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy", name)) as f:
        return json.load(f)


def offer(R, h, financing="conventional", down=0.05, **costs):
    """The offer strategy on the CMA's home, with the CMA's handoff."""
    B = {"analysis_date": "2026-09-26",
         "property": {"address": R["subject"]["address"] + ", Oviedo, FL", "county": "Seminole",
                      "list_price": R["subject"]["list_price"], "mls": "Stellar"},
         "buyer": {"financing": financing, "down_pct": down, "cash_available": 200000},
         "costs": {"rate": R["costs"]["payment"]["rate"], **costs}}
    return strategy.analyze(B, cma=h)


class SameCashToClose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = cma_report()
        cls.C = run_cma(cls.R)

    def test_same_closing_costs_at_the_same_price(self):
        pay = self.C["payments"]
        for label, financing, down in (("Conventional", "conventional", 0.05), ("FHA", "fha", 0.035)):
            with self.subTest(label):
                row = next(x for x in pay["rows"] if x["label"].startswith(label))
                r = offer(self.R, self.C["handoff"], financing, down)
                self.assertEqual(strategy.closing_costs(r["B"], pay["price"]), row["closing_costs"])
        r = offer(self.R, self.C["handoff"])
        for col in self.C["credit"]["columns"]:  # the credit table's columns are on the same rule
            self.assertEqual(col["closing_costs"], strategy.closing_costs(r["B"], col["price"]))

    def test_agent_share_wins(self):
        R = cma_report()
        R["costs"]["credit_scenarios"]["closing_cost_pct"] = 0.04
        C = run_cma(R)
        self.assertEqual(C["payments"]["rows"][0]["closing_costs"], round(C["payments"]["price"] * 0.04))
        self.assertIn("closing_costs", C["note_keys"])  # the agent's share: a note, not an estimate to confirm
        self.assertNotIn("closing_costs", C["assumption_keys"])


class SameInsurance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = cma_report(estimate_insurance=True)
        cls.C = run_cma(cls.R)

    def test_same_insurance_payment_tax_and_cash_at_the_same_price(self):
        """The handoff carries the CMA's premium and its price; the offer uses it (a buyer-file premium still wins)."""
        s, pay = self.C["handoff"]["subject"], self.C["payments"]
        self.assertEqual((s["insurance_annual"], s["insurance_price"]), (pay["insurance_annual"], pay["price"]))
        self.assertTrue(s["insurance_estimated"])
        handoff.validate(self.C["handoff"])
        r = offer(self.R, self.C["handoff"])
        B, costs = r["B"], r["costs"]
        self.assertEqual(B["costs"]["insurance_annual"], pay["insurance_annual"])
        row = pay["rows"][0]  # Conventional, 5% Down
        self.assertEqual(strategy.monthly_payment(B, costs, pay["price"]), round(row["total"]))
        self.assertEqual(round(pay["price"] * 0.05) + strategy.closing_costs(B, pay["price"]), round(row["cash_to_close"]))
        tax = next(t for t in self.C["taxes"] if t.get("total_mills") == self.C["handoff"]["subject"]["total_mills"])
        self.assertAlmostEqual(strategy.property_tax(B, costs, pay["price"])["annual"], tax["annual_exact"], places=2)
        self.assertEqual(tax["annual"], round(tax["annual_exact"]))  # the CMA prints it to the dollar
        self.assertIsNone(B["buyer"].get("insurance_quote"))  # an estimate carried over is never a quote in hand
        self.assertEqual(offer(self.R, self.C["handoff"], insurance_annual=4100)["B"]["costs"]["insurance_annual"], 4100)

    def test_older_handoff_estimates_at_the_cma_target(self):
        R = cma_report(estimate_insurance=True)
        R["costs"]["payment"].pop("price", None)  # figured at the offer plan's target, as the CMA does by default
        C = run_cma(R)
        h = copy.deepcopy(C["handoff"])
        for k in ("insurance_annual", "insurance_price", "insurance_estimated"):
            h["subject"].pop(k)
        r = offer(R, h)
        est = strategy.finance.insurance_estimate(strategy.target_price(h["offer_plan"]), r["costs"],
                                                  h["subject"].get("year_built"))["annual"]
        self.assertEqual(r["B"]["costs"]["insurance_annual"], est)
        self.assertEqual(est, C["payments"]["insurance_annual"])

    def test_cma_estimate_and_the_agents_rate(self):
        R = cma_report(estimate_insurance=True)
        R["subject"]["year_built"] = 1972
        market, homes = cma_compute.load_inputs(R)
        C = cma_compute.compute(R, market, homes)
        price = C["payments"]["price"]
        self.assertEqual(C["payments"]["insurance_annual"], cma_compute.finance.insurance_estimate(price, market, 1972)["annual"])
        self.assertTrue(C["payments"]["insurance"]["estimated"])
        self.assertTrue(any(cma_compute.money(C["payments"]["insurance_annual"]) in n for n in C["notes"]))  # said once
        R = cma_report(estimate_insurance=True)
        R["costs"]["insurance_rate"] = 0.012  # the agent's rate still sets the buyer's estimate
        C = run_cma(R)
        self.assertEqual(C["payments"]["insurance_annual"], round(C["payments"]["price"] * 0.012, -2))
        self.assertEqual(C["payments"]["insurance"]["source"], "agent")

    def test_seller_cma_uses_the_shared_estimate(self):
        with open(os.path.join(ROOT, "dev", "fixtures", "seller-cma", "hickorywood.json")) as f:
            R = json.load(f)
        R["export"] = os.path.join(ROOT, R["export"])
        R["deck"] = os.path.join(ROOT, R["deck"])
        R["buyer_payment"].pop("insurance_annual")
        market, homes = seller_compute.load_inputs(R)
        C = seller_compute.compute(R, market, homes)
        est = seller_compute.finance.insurance_estimate(C["recommendation"]["list_price"], market,
                                                        R["subject"].get("year_built"))["annual"]
        self.assertEqual(C["payments"]["insurance_annual"], est)
        self.assertTrue(C["payments"]["insurance_estimated"])
        self.assertIn("payment", C["assumption_keys"])


class BuyerBrokerShortfall(unittest.TestCase):
    """An agreement above what the seller pays adds the difference to the buyer's cash to close, in both skills."""

    def test_cma_credit_table_and_offer_cash_to_close(self):
        R = cma_report()
        base = run_cma(copy.deepcopy(R))["credit"]["columns"]
        R["costs"]["credit_scenarios"].update(buyer_broker_agreement_pct=0.025, seller_pays_buyer_broker_pct=0)
        for b, c in zip(base, run_cma(R)["credit"]["columns"]):
            self.assertEqual(c["bb_short"], round(0.025 * c["price"]))
            self.assertEqual(round(c["cash"] - b["cash"]), c["bb_short"])
        d = offer_fixture("fha-competitive.json")
        d["buyer"]["buyer_broker_agreement_pct"] = 0.03  # the seller pays 2.5%
        r = strategy.analyze(d)
        c = r["cash"]["recommended"]
        self.assertEqual(c["bb_short"], round(0.005 * r["terms"]["recommended"]["price"]))
        self.assertEqual(c["to_close"], c["down"] + c["cc"] + c["conc"] + c["bb_short"])
        self.assertNotIn("buyer_broker_agreement_pct", [a["field"] for a in r["missing"]])


class LegalDescriptionHandoff(unittest.TestCase):
    def test_handoff_to_worksheet(self):
        R = cma_report()
        R["subject"]["legal_description"] = "LOT 87 SAMPLE KESTREL POINT PB 52 PGS 41-45"
        R["subject"]["parcel_id"] = "22-21-30-8KP-0000-0870"
        h = run_cma(R)["handoff"]
        self.assertEqual(h["subject"]["parcel_id"], "22-21-30-8KP-0000-0870")
        d = offer_fixture("one-competing-reach.json")
        d["cma"]["subject"].update(legal_description=h["subject"]["legal_description"], parcel_id=h["subject"]["parcel_id"])
        out = strategy.result(strategy.analyze(d, cma=strategy.load_cma(d)))
        row = next(r for r in out["worksheet"]["rows"] if r["field"] == "Legal Description / Parcel ID")
        self.assertIn("LOT 87 SAMPLE KESTREL POINT", row["entry"])
        self.assertIn("22-21-30-8KP-0000-0870", row["entry"])
        self.assertNotIn("22-21-30", row["note"])

    def test_missing_parts_and_the_buyer_file_wins(self):
        self.assertTrue(strategy.legal_entry({}).startswith("["))  # a blank to fill
        entry = strategy.legal_entry({"parcel_id": "1-2-3"})
        self.assertTrue(entry.startswith("[") and entry.endswith("1-2-3"))
        self.assertNotIn("parcel_id", handoff.subject_facts(parcel_id="  "))
        d = offer_fixture("one-competing-reach.json")
        d["worksheet"]["parcel_id"] = "AGENT-ID"
        d["cma"]["subject"]["parcel_id"] = "CMA-ID"
        self.assertEqual(strategy.analyze(d, cma=strategy.load_cma(d))["B"]["worksheet"]["parcel_id"], "AGENT-ID")


if __name__ == "__main__":
    unittest.main()
