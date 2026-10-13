"""Iteration 16: what the seller's report states as a term. Terms nobody gave read "Not provided" with no rating, free
text is neutral, the net sheet carries a counter column only when countering, the timeline has no empty rows, the
biggest risk skips an escalation that doesn't trigger, and the quick answer names every estimate with its figure."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render = load("seller-offer-review", "review", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def single(listing, offer, seller=None):
    return {"analysis_date": "2026-09-26", "listing": listing, "seller": seller or {}, "offers": [dict(id="A", **offer)]}


def rows(data):
    R = review.analyze(data)
    o = (R["ranked"] or R["incomplete"])[0]
    return {r[0]: r for r in review.term_rows(o, R)}, R, o


class TermsReview(unittest.TestCase):
    def test_terms_nobody_gave_are_not_rated(self):
        """Evals 1, 3, 5: approval, inspection period, concessions and the title box weren't given: no stand-in is
        printed as the offer's term and none is rated, as the scorecard leaves them unscored."""
        tr, R, o = rows(fixture("minimal-single.json"))
        for term in ("Approval", "Escrow Deposit", "Seller Concessions", "Inspection Period", "Escrow / Title Agent"):
            self.assertEqual(tr[term][1], "Not provided", term)
            self.assertEqual(tr[term][3], "none", term)
        self.assertNotIn("Pre-approval", json.dumps([r[1] for r in tr.values()]))
        self.assertIsNone(o["score"]["scores"]["approval"])
        doc = review.result(R)["doc"]["terms"]["rows"]
        self.assertEqual({r["term"]: r["rating"] for r in doc}["Approval"], "—")
        html = render.build_html(review.result(R), {}, False)
        self.assertNotIn('class="pill none"', html)

    def test_texas_title_company_not_given(self):
        """Eval 3: nobody said who chose the title company; Texas custom isn't printed as the offer's term."""
        tr, _, _ = rows(single({"address": "8104 Shoal Creek Blvd, Austin, TX", "state": "TX", "list_price": 610000},
                               {"price": 598000, "financing": "conventional", "down_pct": 0.2, "deposit": 6000,
                                "inspection_days": 7, "closing_days": 35}))
        self.assertEqual(tr["Escrow / Title Agent"][1:4:2], ("Not provided", "none"))

    def test_free_text_and_the_sellers_own_title_pick_are_not_cautions(self):
        """Evals 6, 7: personal property and the buyer's own inspections cost the seller nothing the script measures;
        the seller choosing the closing agent is never a Watch."""
        offer = {"price": 619500, "financing": "conventional", "down_pct": 0.25, "deposit": 24000, "approval": "preapproval",
                 "seller_concessions": 0, "inspection_days": 10, "loan_approval_days": 30, "closing_date": "2026-11-16",
                 "contract_form": "as_is", "title_by": "seller",
                 "personal_property": "Seller to leave the pool cleaning robot and the patio furniture.",
                 "other_terms": "Buyer's inspections to include a four-point and wind mitigation inspection."}
        tr, R, _ = rows(single({"address": "10 Gulf Shore Blvd, Naples, FL 34102", "county": "Collier", "list_price": 639000},
                               offer))
        self.assertEqual(R["listing"]["title_customary_payer"], "buyer")
        self.assertEqual(tr["Escrow / Title Agent"][1], "Seller's title co.")
        self.assertEqual(tr["Escrow / Title Agent"][3], "good")
        self.assertEqual((tr["Personal Property"][3], tr["Other Terms"][3]), ("neutral", "neutral"))
        ratings = {r["term"]: r["rating"] for r in review.result(R)["doc"]["terms"]["rows"]}
        self.assertEqual(ratings["Personal Property"], "Neutral")

    def test_assumed_form_isnt_printed_in_key_terms(self):
        """Evals 2, 4: the comparison's Key Terms never prints "(AS IS)" for an offer whose form was assumed."""
        data = fixture("four-offers.json")
        for o in data["offers"][1:]:
            o.pop("contract_form", None)
        R = review.analyze(data)
        kt = {r["key"]: r for r in review.key_terms(R)["rows"]}
        col = [k for k, _ in review.KEY_TERMS].index("inspection")
        self.assertIn("(AS IS)", kt["A"]["cells"][col]["text"])
        for k in ("B", "C", "D"):
            self.assertNotIn("AS IS", kt[k]["cells"][col]["text"])


class NetSheetAndTimeline(unittest.TestCase):
    def test_no_counter_column_when_accepting(self):
        """Eval 5: Accept as Written has no Proposed Counter column on its net sheet."""
        data = single({"address": "1207 Palmetto Way", "list_price": 389000},
                      {"price": 385000, "financing": "conventional", "down_pct": 0.2, "deposit": 10000, "closing_days": 40,
                       "contract_form": "standard", "riders": ["K"], "inspection_days": 10})
        R = review.analyze(data)
        o = R["offers"][0]
        self.assertEqual(o["action"], "ACCEPT")
        self.assertTrue(o["counter_rows"])  # the counter still exists as an option
        ns = review.result(R)["doc"]["net_sheet"]
        self.assertNotIn("Proposed Counter", ns["columns"])
        self.assertNotIn("Counter", ns["sub"])
        countered = review.analyze(fixture("minimal-single.json"))
        self.assertEqual(countered["offers"][0]["action"], "COUNTER")
        self.assertIn("Proposed Counter", review.result(countered)["doc"]["net_sheet"]["columns"])

    def test_target_on_an_incomplete_review(self):
        """Eval 6: with no recommended offer, the target closes on the offer's own date, never "the recommended
        offer's date"."""
        data = fixture("incomplete-single.json")
        R = review.analyze(data)
        self.assertFalse(R["ranked"])
        o = R["incomplete"][0]
        self.assertEqual(R["target_close"], o["close"])
        text = json.dumps(review.result(R)["doc"]["net_sheet"]["captions"])
        self.assertNotIn("recommended offer", text)

    def test_no_empty_sale_row(self):
        """Evals 7, 8: no "Sale of Buyer's Home" row for an offer without that contingency."""
        R = review.analyze(fixture("four-offers.json"))
        sale = review.L_["tl_sale"]
        names = {o["id"]: [r["name"] for r in review.timeline(o, R)["rows"]] for o in R["offers"]}
        self.assertNotIn(sale, names["B"])
        self.assertIn(sale, names["D"])  # Lee's offer has one


class BiggestRisk(unittest.TestCase):
    def test_untriggered_escalation_isnt_the_biggest_risk(self):
        """Eval 8: a cap above value matters only if the clause triggers; while it doesn't, the threat leads."""
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        b = next(o for o in R["offers"] if o["id"] == "B")
        self.assertFalse(b["escalated"])
        self.assertEqual(review.deal_flags(b)[0]["topic"], "escalation_cap_over_value")
        self.assertFalse(review.biggest_risk(b)["key"].startswith("escalation"))


class AppraisalWording(unittest.TestCase):
    def test_where_the_price_sits(self):
        """Buyer-offer-strategy eval 1: below the range bottom never reads "At or under the top of the value range"."""
        def why(price, cma=True):
            listing = {"address": "1 Oak St, Winter Springs, FL 32708", "list_price": 400000}
            if cma:
                listing.update(cma_low=390000, cma_high=410000)
            R = review.analyze(single(listing, {"price": price, "financing": "conventional", "down_pct": 0.2,
                                                "deposit": 8000, "closing_days": 30, "appraisal_contingency": 21}))
            return R["offers"][0]["score"]["why"]["appraisal"]
        self.assertTrue(why(380000).startswith("Below the value range, "))
        self.assertTrue(why(395000).startswith("In the lower half of the value range, "))
        self.assertTrue(why(405000).startswith("In the upper half of the value range, "))  # scores lower: said why
        self.assertTrue(why(415000).startswith("$5,000 over the top of the value range, "))
        self.assertTrue(why(380000, cma=False).startswith("Below list price, "))
        self.assertTrue(why(400000, cma=False).startswith("At list price, "))
        self.assertTrue(why(405000, cma=False).startswith("$5,000 over list price, "))


class QuickAnswer(unittest.TestCase):
    def test_estimated_costs_have_figures_and_the_tax(self):
        """Eval 3: every estimate named with its figure, the tax estimate included even when to_confirm asks for the bill."""
        out = review.result(review.analyze(single(
            {"address": "8104 Shoal Creek Blvd, Austin, TX", "state": "TX", "list_price": 610000},
            {"price": 598000, "financing": "conventional", "down_pct": 0.2, "deposit": 6000, "inspection_days": 7,
             "closing_days": 35}, {"payoff": 214000, "listing_fee_pct": 0.03, "offered_buyer_broker_pct": 0.025})))
        est = out["estimated_costs"]
        self.assertIn("owner's title policy $2,990 (0.5% of price, national estimate)", est)
        self.assertTrue(any(e.startswith("tax proration at 1.4% of list price (Texas average effective rate)") for e in est))

    def test_rider_gg_paid_by_the_listing_broker_asks_for_the_agreement(self):
        """Eval 6: with no compensation agreement in the package, the chat asks for it with the listing-agreement
        check; never on the seller's report."""
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        out = review.result(R)
        self.assertTrue(any("separate compensation agreement" in q for q in out["to_confirm"]))
        self.assertFalse(any("separate compensation agreement" in a["what"] for a in out["assumptions"]))
        data = fixture("listing-pays-buyer-broker.json")
        for o in data["offers"]:
            o["compensation_agreement"] = "signed_by_buyer_broker"
        out = review.result(review.analyze(data))
        self.assertTrue(any("Your brokerage still signs" in q for q in out["to_confirm"]))


if __name__ == "__main__":
    unittest.main()
