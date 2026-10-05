"""Fixes from eval iteration 12 (buyer-cma eval 4, buyer-offer-strategy eval 5: 2315 Kestrel Point Ct, the CMA then the
offer in one chat): the same insurance in both reports, the legal description and parcel ID carried to the worksheet,
the credit table kept whole, history years, built-in partial-update and roof-age rates, appraisal gap pushback only above
the value range, the tax-bill question, a seller flexible on closing, and the offer render's no-profile check."""
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, cma_render, cma, handoff, profiles = load("buyer-cma", "compute", "render", "_shared.cma", "_shared.handoff",
                                                    "_shared.profiles")
strategy, offer_render = load("buyer-offer-strategy", "strategy", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def cma_report():
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    R["costs"]["payment"].pop("insurance_annual")  # the CMA estimates it, as in the eval
    R["costs"]["credit_scenarios"].pop("closing_cost_pct")  # the market's estimate, not the agent's share
    return R


def run_cma(R):
    market, homes = compute.load_inputs(R)
    return compute.compute(R, market, homes)


def kestrel(**changes):
    """The eval's buyer: conventional 5%, $42,000 cash, $5,000 reserve, $4,000 payment, one competing offer, no insurance
    figure (one-competing-reach.json without its premium)."""
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy", "one-competing-reach.json")) as f:
        d = json.load(f)
    d["costs"].pop("insurance_annual")
    d["buyer"].pop("insurance_quote")
    for k, v in changes.items():
        d[k] = v
    return d


class SameInsuranceInBothReports(unittest.TestCase):
    """The CMA estimated $5,000 at its $442,000 target; the offer estimated $5,200 at list. The handoff now carries the
    CMA's premium and its price, and the offer uses it."""

    def setUp(self):
        self.R = cma_report()
        self.C = run_cma(self.R)

    def offer(self, h, **costs):
        B = {"analysis_date": "2026-09-26",
             "property": {"address": self.R["subject"]["address"] + ", Oviedo, FL", "county": "Seminole",
                          "list_price": self.R["subject"]["list_price"], "mls": "Stellar"},
             "buyer": {"financing": "conventional", "down_pct": 0.05, "cash_available": 200000},
             "costs": {"rate": self.R["costs"]["payment"]["rate"], **costs}}
        return strategy.analyze(B, cma=h)

    def test_handoff_carries_the_premium_and_its_price(self):
        s, pay = self.C["handoff"]["subject"], self.C["payments"]
        self.assertEqual(s["insurance_annual"], pay["insurance_annual"])
        self.assertEqual(s["insurance_price"], pay["price"])
        self.assertTrue(s["insurance_estimated"])
        handoff.validate(self.C["handoff"])

    def test_same_insurance_payment_and_cash_at_the_same_price(self):
        pay = self.C["payments"]
        r = self.offer(self.C["handoff"])
        B, costs = r["B"], r["costs"]
        self.assertEqual(B["costs"]["insurance_annual"], pay["insurance_annual"])
        row = pay["rows"][0]  # Conventional, 5% Down
        self.assertEqual(strategy.monthly_payment(B, costs, pay["price"]), round(row["total"]))
        self.assertEqual(round(pay["price"] * 0.05) + strategy.closing_costs(B, pay["price"]), round(row["cash_to_close"]))
        tax = next(t for t in self.C["taxes"] if t.get("total_mills") == self.C["handoff"]["subject"]["total_mills"])
        self.assertAlmostEqual(strategy.property_tax(B, costs, pay["price"])["annual"], tax["annual"], places=2)
        why = next(a["why"] for a in r["assumptions"] if a["field"] == "insurance_annual")
        self.assertIn("the buyer CMA's estimate at", why)
        self.assertIsNone(B["buyer"].get("insurance_quote"))  # an estimate carried over is never a quote in hand

    def test_buyer_file_premium_wins(self):
        r = self.offer(self.C["handoff"], insurance_annual=4100)
        self.assertEqual(r["B"]["costs"]["insurance_annual"], 4100)

    def test_older_handoff_estimates_at_the_cma_target(self):
        R = cma_report()
        R["costs"]["payment"].pop("price", None)  # figured at the offer plan's target, as the CMA does by default
        C = run_cma(R)
        h = copy.deepcopy(C["handoff"])
        for k in ("insurance_annual", "insurance_price", "insurance_estimated"):
            h["subject"].pop(k)
        r = self.offer(h)
        target = strategy.target_price(h["offer_plan"])
        est = strategy.finance.insurance_estimate(target, r["costs"], h["subject"].get("year_built"))["annual"]
        self.assertEqual(r["B"]["costs"]["insurance_annual"], est)
        self.assertEqual(est, C["payments"]["insurance_annual"])

    def test_eval_numbers(self):
        """The eval's figures: 0.9% x 1.25 (1998) at $442,000 is $5,000; at list $464,900 it was $5,200."""
        d = kestrel()
        d["cma"]["subject"].update(insurance_annual=5000, insurance_price=442000, insurance_estimated=True)
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertEqual(r["B"]["costs"]["insurance_annual"], 5000)


class LegalDescriptionAndParcel(unittest.TestCase):
    def test_handoff_to_worksheet_both_under_enter(self):
        R = cma_report()
        R["subject"]["legal_description"] = "LOT 87 SAMPLE KESTREL POINT PB 52 PGS 41-45"
        R["subject"]["parcel_id"] = "22-21-30-8KP-0000-0870"
        h = run_cma(R)["handoff"]
        self.assertEqual(h["subject"]["parcel_id"], "22-21-30-8KP-0000-0870")
        d = kestrel()
        d["cma"]["subject"].update(legal_description=h["subject"]["legal_description"], parcel_id=h["subject"]["parcel_id"])
        out = strategy.result(strategy.analyze(d, cma=strategy.load_cma(d)))
        row = next(r for r in out["worksheet"]["rows"] if r["field"] == "Legal Description / Parcel ID")
        self.assertIn("LOT 87 SAMPLE KESTREL POINT", row["entry"])
        self.assertIn("Parcel ID 22-21-30-8KP-0000-0870", row["entry"])
        self.assertNotIn("22-21-30", row["note"])

    def test_missing_part_is_a_blank(self):
        self.assertEqual(strategy.legal_entry({}), "[from the county property appraiser]")
        self.assertEqual(strategy.legal_entry({"parcel_id": "1-2-3"}), "[legal description] · Parcel ID 1-2-3")

    def test_buyer_file_wins_and_blank_strings_are_left_out(self):
        self.assertNotIn("parcel_id", handoff.subject_facts(parcel_id="  "))
        d = kestrel()
        d["worksheet"]["parcel_id"] = "AGENT-ID"
        d["cma"]["subject"]["parcel_id"] = "CMA-ID"
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertEqual(r["B"]["worksheet"]["parcel_id"], "AGENT-ID")


class CmaLayout(unittest.TestCase):
    L = staticmethod(lambda key, **kw: key)

    def test_history_year_shown_when_not_this_year(self):
        hist = {"timeline": [{"date": d, "kind": "listed", "price": 1, "delta": 0} for d in
                             ("2015-03-31", "2015-04-21", "2015-05-22", "2026-07-10", "2026-08-14")]}
        rows = [r[0] for r in cma_render.history_rows({}, hist, self.L, "2026-09-26")]
        # Results_v5: the year on every row once the rows span more than one year
        self.assertEqual(rows, ["Mar 31, 2015", "Apr 21, 2015", "May 22, 2015", "Jul 10, 2026", "Aug 14, 2026"])

    def test_credit_table_never_runs_on(self):
        R = cma_report()
        C = run_cma(R)
        L = cma.Labels(cma_render.ASSETS, R.get("labels"))
        html = "".join(cma_render.credit_section(R, C, L))
        self.assertIn('class="tbl wrap-head whole"', html)
        self.assertIn("!el.querySelector('.tbl.whole')", cma.PAGINATE_JS)


class AdjustmentRates(unittest.TestCase):
    def test_florida_partial_update_and_roof_rates(self):
        m = profiles.load_market(state="FL", county="Seminole")
        self.assertEqual(m.get("cma.adjustments.kitchen_only_vs_dated"), 15000)
        self.assertEqual(m.get("cma.adjustments.baths_only_vs_dated"), 10000)
        bands = m.get("cma.adjustments.roof_age")
        self.assertEqual([b["value"] for b in bands], [0, -5000, -10000, -15000])
        self.assertEqual(bands[2]["years"], [15, 19])
        self.assertIsNone(cma.adjustment_scope_warning(m, "Seminole", 450000))
        self.assertIn("don't fit", cma.adjustment_scope_warning(m, "Miami-Dade", 450000))

    def test_method_references_agree(self):
        texts = []
        for skill in ("buyer-cma", "seller-cma"):
            with open(os.path.join(ROOT, "skills", skill, "references", "method.md")) as f:
                texts.append(f.read())
        for t in texts:
            self.assertIn("closest 5 sales when 5 or more qualify (4 or 6 only with a reason", t)
            self.assertIn("$15,000 for a kitchen only and $10,000 for baths only", t)
            self.assertIn("15–19 years –$10,000", t)


class GapPushbackOnlyAboveTheRange(unittest.TestCase):
    def test_no_gap_row_on_a_price_inside_the_range(self):
        d = kestrel()
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        out = strategy.result(r)
        t = r["terms"]["recommended"]
        self.assertLessEqual(t["price"], r["B"]["value"]["cma_high"])
        self.assertNotIn("Appraisal Gap Coverage", [p["term"] for p in out["pushback"]])

    def test_gap_row_kept_above_the_range(self):
        d = kestrel()
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertIn("Appraisal Gap Coverage", [x[0] for x in r["O"]["recommended"].get("counter_rows") or []])
        r["B"]["value"]["cma_high"] = r["terms"]["recommended"]["price"] - 5000  # the offer now sits above the range
        self.assertIn("Appraisal Gap Coverage", [p["term"] for p in strategy.pushback(r)])


class TaxBillQuestion(unittest.TestCase):
    def test_not_asked_before_the_bills_go_out(self):
        out = strategy.result(strategy.analyze(kestrel(), cma=strategy.load_cma(kestrel())))
        self.assertFalse([q for q in out["to_confirm"] if "tax bill" in q])
        note = next(a for a in out["assumptions"] if "tax bills go out" in a["what"])
        self.assertEqual(note["impact"], "low")

    def test_asked_once_the_bills_are_out(self):
        d = kestrel(analysis_date="2026-11-20")
        out = strategy.result(strategy.analyze(d, cma=strategy.load_cma(d)))
        self.assertTrue([a for a in out["assumptions"] if "has paid this year's tax bill" in a["what"]
                         and a["impact"] == "med"])


class SellerFlexibleClose(unittest.TestCase):
    def test_reply_line_chat_only(self):
        d = kestrel()
        d["property"]["seller_flexible_close"] = True
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertIn("seller_timeline", [x["key"] for x in r["reply_lines"]])
        self.assertNotIn("flexible", json.dumps(strategy.result(r)["summary"]))

    def test_none_without_it(self):
        r = strategy.analyze(kestrel(), cma=strategy.load_cma(kestrel()))
        self.assertNotIn("seller_timeline", [x["key"] for x in r["reply_lines"]])


class OfferRenderProfileCheck(unittest.TestCase):
    def test_no_profile_is_named(self):
        self.assertIn("no profile", offer_render.profile_check({}))
        self.assertIn("profile incomplete", offer_render.profile_check({"name": "A"}))
        self.assertIsNone(offer_render.profile_check({"name": "A", "brokerage": "B"}))

    def test_printed_once_per_run(self):
        d = kestrel()
        err = io.StringIO()
        with mock.patch.object(offer_render.render, "html_to_pdf", return_value=0), redirect_stderr(err), \
                tempfile.TemporaryDirectory() as out:
            ctx = {"agent": {}}
            offer_render.build(d, "options", out, ctx)
            offer_render.build(d, "worksheet", out, ctx)
        self.assertEqual(len(re.findall("no profile", err.getvalue())), 1)


if __name__ == "__main__":
    unittest.main()
