"""Escalation clauses: the effective price, the counter to an escalating offer, the addendum's contract-form box, how
the escalation is funded, and the comparison's escalation column."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render, oe = load("seller-offer-review", "review", "render", "_shared.offer_engine")
cf = oe.cf

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")
EAC = {"cap": 506000, "increment": 2000, "proof": True}
FINANCED = dict(EAC, paid_in_cash=False)  # EAC-1 (b): the loan grows

BASE = {"analysis_date": "2026-09-23",
        "listing": {"address": "1 Test St, Longwood, FL 32750", "state": "FL", "county": "Seminole", "list_price": 400000,
                    "cma_low": 390000, "cma_high": 410000, "annual_tax": 5000, "hoa_monthly": 0, "flood_disclosure": True},
        "seller": {"payoff": 200000, "listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.025}}

def page(R, agent=None, sample=False, mode="auto", offer_id=None):
    """The report's HTML, from the one document model (review.result)."""
    return render.build_html(review.result(R, mode, offer_id), agent or {}, sample)



def hand(**k):
    o = {"id": "A", "contract_form": "as_is", "price": 400000, "financing": "conventional", "down_pct": 0.2, "deposit": 10000,
         "seller_concessions": 0, "inspection_days": 10, "loan_approval_days": 30, "closing_date": "2026-11-06",
         "title_by": "seller"}
    o.update(k)
    return o


def run(*offers):
    d = copy.deepcopy(BASE)
    d["offers"] = list(offers)
    return oe.analyze(d)


def case05(**b):
    """Two offers on 2604 Sable Palm Way; B ($494,000, escalating by $2,000 to $506,000, $444,600 loan, $88,000 proof
    of funds) is ranked first and countered. `b` is merged into offer B."""
    with open(os.path.join(FIXTURES, "listing-pays-buyer-broker.json")) as f:
        d = json.load(f)
    d["offers"][1].update(b)
    return d


def offer_b(**b):
    """Offer B on the meet-partway stance (counter-rules.md rule 2: the cap between partway and list)."""
    b.setdefault("counter", {"stance": "meet_partway", "stance_reason": "Testing the meet-partway rules."})
    return next(o for o in review.analyze(case05(**b))["offers"] if o["id"] == "B")


def topics(o):
    return {f.get("topic"): f for f in o["flags"]}


def rows(o):
    return {r[0]: r for r in o["counter_rows"]}


class EffectivePrice(unittest.TestCase):
    def test_cap_below_price_never_lowers_it(self):
        R = run(hand(price=405000, escalation={"increment": 2000, "cap": 402000, "proof": "copy"}), hand(id="B", price=404000))
        a = R["offers"][0]
        self.assertEqual((a["price_base"], a["price"], a["escalated"]), (405000, 405000, False))
        self.assertTrue(a["escalation_issues"])

    def test_same_buyer_variants_dont_escalate_against_each_other(self):
        esc = {"increment": 1000, "cap": 420000, "proof": "copy"}
        alone = run(hand(price=400000, escalation=esc, same_buyer="b"))["offers"][0]
        both = run(hand(price=400000, escalation=esc, same_buyer="b"), hand(id="B", price=405000, same_buyer="b"))["offers"][0]
        self.assertEqual((both["price"], both["score"]["total"]), (alone["price"], alone["score"]["total"]))

    def test_missing_terms_are_flagged(self):
        with open(os.path.join(FIXTURES, "escalation.json")) as f:
            data = json.load(f)
        data["offers"][0]["escalation"] = {"increment": 1000}
        a = next(o for o in oe.analyze(data)["offers"] if o["id"] == "A")
        self.assertLessEqual({"escalation_cap", "escalation_proof"}, set(topics(a)))


class EscalationCounter(unittest.TestCase):
    """The counter goes up to the cap, never past list."""

    def test_counter_price_by_cap(self):
        b = offer_b()  # cap $506,000 reaches list ($504,000): counter at list
        self.assertEqual(rows(b)["Price"][2], "$504,000")
        self.assertIn("$506,000", rows(b)["Price"][3])
        self.assertIn("$504,000", rows(b)["Pre-Approval"][2])
        b = offer_b(escalation={"cap": 501500, "increment": 1000, "proof": True})  # between partway and list: the cap
        self.assertEqual(rows(b)["Price"][2], "$501,500")
        b = offer_b(escalation={"cap": 496000, "increment": 1000, "proof": True})  # below partway: partway
        self.assertEqual(rows(b)["Price"][2:], ("$499,000", "Below list: meet partway"))

    def test_comparison_column(self):
        R = review.analyze(case05())
        ranked = {r["id"]: r for r in review.multi_view(R)["ranked"]}
        self.assertEqual(ranked["B"]["escalation"], "Base $494,000 · +$2,000 · cap $506,000")
        self.assertIsNone(ranked["A"]["escalation"])
        self.assertIn(">Escalation</th>", page(R, {}, mode="multi"))
        self.assertNotIn(">Escalation</th>", page(review.analyze(case05(escalation=None)), {}, mode="multi"))


class EscalationForm(unittest.TestCase):
    """An Escalation Addendum whose box names the other contract form is a High issue (contract_forms' rule)."""

    def test_box_against_the_offers_form(self):
        legacy = "Residential Contract for Sale and Purchase (FR/BAR)"  # the legacy name is still read
        f = topics(offer_b(escalation=dict(EAC, contract_form=legacy)))
        self.assertEqual(f["escalation_form"]["sev"], "High")  # the Standard box on an AS IS offer
        self.assertTrue(f["escalation_form"].get("request"))
        self.assertNotIn("escalation_form", topics(offer_b(escalation=dict(EAC, contract_form="as_is"))))
        self.assertTrue(cf.addendum_form_conflict(cf.STANDARD, "CRSP"))
        self.assertIsNone(cf.addendum_form_conflict(cf.OTHER, "standard"))

    def test_ambiguous_box_stops(self):
        with self.assertRaises(oe.OfferError) as e:
            review.analyze(case05(escalation=dict(EAC, contract_form="FAR/BAR")))
        self.assertIn("offers[B].escalation.contract_form:", str(e.exception))


class EscalationFunding(unittest.TestCase):
    """EAC-1 (a) pays the escalation in cash with proof of funds, so the pre-approval letter isn't its limit; (b)
    finances it, so the letter is."""

    def test_contract_forms_reads_how_it_is_paid(self):
        eac = {"addenda": ["Escalation Addendum to Contract (EAC-1)"], "escalation": {"cap": 1}}
        self.assertTrue(cf.escalation_paid_in_cash(cf.AS_IS, eac))  # neither box recorded: EAC-1's default, cash
        self.assertFalse(cf.escalation_paid_in_cash(cf.AS_IS, {**eac, "escalation": {"paid_in_cash": False}}))
        self.assertIsNone(cf.escalation_paid_in_cash("other", eac))
        self.assertIsNone(cf.escalation_paid_in_cash(cf.STANDARD, {"escalation": {"cap": 1}}))
        self.assertTrue(cf.escalation_proof_stated(cf.STANDARD, eac))
        self.assertFalse(cf.escalation_proof_stated("other", {"escalation": {"cap": 1}}))

    def test_cash_escalation_against_the_proof_of_funds(self):
        t = topics(offer_b())  # $88,000 verified; $506,000 less the $444,600 loan is $61,400
        self.assertFalse({"escalation_cap_over_approval", "escalation_cash_short"} & set(t))
        self.assertNotIn("escalation_cash_short", topics(offer_b(escalation=dict(EAC, paid_in_cash=True))))
        self.assertNotIn("escalation_cash_short",  # the escalation's own proof of funds
                         topics(offer_b(proof_of_funds=None, escalation=dict(EAC, paid_in_cash=True, proof_of_funds=70000))))
        short = topics(offer_b(proof_of_funds=50000))["escalation_cash_short"]
        self.assertEqual(short["sev"], "Med")
        self.assertIn("$61,400", short["issue"])
        self.assertIn("escalation_cash_short", topics(offer_b(proof_of_funds=None)))  # no proof in the package

    def test_financed_escalation_against_the_approval(self):
        f = topics(offer_b(escalation=FINANCED))["escalation_cap_over_approval"]  # letter to $494,000, cap $506,000
        self.assertEqual(f["sev"], "Med")
        self.assertIn("$506,000", f["issue"])
        self.assertNotIn("escalation_cap_over_approval",
                         topics(offer_b(approval_max_price=510000, approval_max_loan=460000, escalation=FINANCED)))
        self.assertIn("escalation_cap_over_approval",  # the $444,600 loan cap is below the loan at the cap
                      topics(offer_b(approval_max_price=None, escalation=FINANCED)))

    def test_bad_fields_stop_the_review(self):
        for esc, field in (({"cap": 506000, "paid_in_cash": "yes"}, "escalation.paid_in_cash"),
                           ({"cap": 506000, "proof_of_funds": "88k"}, "escalation.proof_of_funds")):
            with self.subTest(field), self.assertRaises(oe.OfferError) as e:
                review.analyze(case05(escalation=esc))
            self.assertIn(f"offers[B].{field}:", str(e.exception))


if __name__ == "__main__":
    unittest.main()
