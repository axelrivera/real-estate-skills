"""Fixes for seller-offer-review's markdown path (the full review in chat and the fallback when the PDF can't render),
OFR-351 to OFR-354: with two or more offers the markdown gives the comparison and each offer's single review, as the
PDFs do (OFR-318), and a single review of one of several offers lists only its own items.
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render = load("seller-offer-review", "review", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")
SAMPLE = os.path.join(ROOT, "dev", "samples", "seller-offer-review.json")
TEMPLATE = os.path.join(ROOT, "skills", "seller-offer-review", "assets", "offer-review-template.md")


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fixture(name):
    return read(os.path.join(FIXTURES, name))


def fields(items):
    return sorted(a["field"] for a in items)


class SingleReviewScope(unittest.TestCase):  # OFR-352
    """Offer B closes Oct 30 with its compensation stated; C (VA) assumes its down payment, buyer-broker share and loan
    period, and closes in December (the tax bill question)."""

    def setUp(self):
        self.R = review.analyze(read(SAMPLE))
        self.out = review.result(self.R, "single", "B")

    def test_assumptions_are_the_offers_own(self):
        own = review.listed_assumptions(self.R, offer_id="B")  # what B's PDF lists (render.assumptions_table)
        self.assertEqual(fields(self.out["assumptions"]), fields(own))
        self.assertNotIn("buyer_broker_pct", fields(self.out["assumptions"]))
        self.assertNotIn("current_tax_bill_paid", fields(self.out["assumptions"]))

    def test_counts_match_the_list(self):
        n = len(self.out["assumptions"])
        self.assertIn(f"{n} input", self.out["summary"]["data_note"])

    def test_questions_are_the_offers_own(self):
        own = {a["why"] for a in review.listed_assumptions(self.R, offer_id="B")}
        self.assertTrue(self.out["to_confirm"])
        self.assertTrue(set(self.out["to_confirm"]) <= own)

    def test_where_names_only_this_offer(self):
        b = next(o for o in self.R["offers"] if o["id"] == "B")
        shared = [a for a in self.out["assumptions"] if a["field"] == "title_by"]
        self.assertEqual([a["where"] for a in shared], [b["label"]])

    def test_buyer_broker_estimate_follows_the_offer(self):
        # B's share is Requested on its net sheet: no default buyer's broker share named for it
        self.assertFalse(any("commission" in c for c in self.out["estimated_costs"]))
        c = review.result(self.R, "single", "C")
        self.assertTrue(any(x.startswith("default commission") and "buyer's broker" in x for x in c["estimated_costs"]))
        self.assertFalse(any("assumed" in x for x in c["estimated_costs"] if "commission" in x))  # a default, not an assumption

    def test_comparison_lists_its_own_scope(self):
        m = review.result(self.R, "multi")
        self.assertEqual(fields(m["assumptions"]), fields(review.listed_assumptions(self.R, multi=True)))
        self.assertIn(f"{len(m['assumptions'])} input", m["summary"]["data_note"])

    def test_incomplete_offer_in_a_multi_listing(self):
        d = fixture("four-offers.json")
        d["offers"][2]["contract_issues"] = [{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for the complete contract."}]
        R = review.analyze(d)
        oid = R["incomplete"][0]["id"]
        out = review.result(R, "single", oid)
        self.assertEqual(out["summary"]["action"], "INCOMPLETE")
        self.assertEqual(fields(out["assumptions"]), fields(review.listed_assumptions(R, offer_id=oid)))
        self.assertIn(f"{len(out['assumptions'])} input", out["summary"]["data_note"])


class SharedAsk(unittest.TestCase):  # OFR-353
    def test_rider_gg_agreement_is_one_item(self):
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        gg = [a for a in R["missing"] if a["field"] == "compensation_agreement"]
        # iteration 10 eval 6: the listing broker pays the buyer's broker on both offers, so the agreement's amount
        # doesn't move the seller's net and isn't asked (the flag still says to get the signed agreement)
        self.assertEqual(gg, [])
        asks = review.to_confirm(R)
        self.assertEqual(len(asks), len(set(asks)))


class MarkdownPath(unittest.TestCase):  # OFR-351, OFR-354
    def test_ranked_rows_carry_the_id_for_each_single_review(self):
        R = review.analyze(read(SAMPLE))
        ranked = review.result(R, "multi")["summary"]["ranked"]
        self.assertEqual([r["id"] for r in ranked if r["rank"] != "—"], [o["id"] for o in R["ranked"]])
        for r in ranked:
            self.assertEqual(review.result(R, "single", r["id"])["summary"]["offer"], r["id"])

    def test_net_sheet_columns_match_the_pdf(self):
        out = review.result(review.analyze(fixture("minimal-single.json")))
        self.assertEqual(out["offers"][0]["net_sheet"]["columns"], ["As Offered", "Downside Case", "Proposed Counter"])
        lapsed = review.result(review.analyze(fixture("expired-aga.json")))
        self.assertEqual(lapsed["summary"]["action"], "INCOMPLETE")
        self.assertEqual(lapsed["offers"][0]["net_sheet"]["columns"][-1], "Counter (Reference)")

    def test_template_paths_exist(self):
        """Every summary.<key> and offers[].<key> the template names is in some review.py output."""
        with open(TEMPLATE, encoding="utf-8") as f:
            text = f.read()
        summary_keys = set(re.findall(r"summary\.(\w+)", text))
        seen = set()
        outs = []
        for name in ("minimal-single.json", "expired-aga.json", "escalation.json", "listing-pays-buyer-broker.json"):
            R = review.analyze(fixture(name))
            outs.append(review.result(R))
            if R["mode"] == "multi":
                outs += [review.result(R, "single", o["id"]) for o in R["ranked"]]
        for out in outs:
            seen |= set(out["summary"])
            for k in ("property", "list_price", "offers", "to_confirm", "estimated_costs", "assumptions"):
                self.assertIn(k, out)
        self.assertEqual(sorted(summary_keys - seen), [])
        for out in outs:
            for o in out["offers"]:
                for k in ("label", "biggest_risk", "downside_note", "net_sheet"):
                    self.assertIn(k, o)


if __name__ == "__main__":
    unittest.main()
