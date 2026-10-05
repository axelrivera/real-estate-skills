"""Iteration 12 fixes: seller-offer-review eval 8 and seller-net-sheet eval 6.

Offer review (the case 05 listing, two offers on 2604 Sable Palm Way): Rider GG's compensation agreement status, an
Escalation Addendum checking the other contract form, a call for highest and best already out, the counter to an
escalating offer, the escalation column, and the no-CMA wording. Net sheet (3318 Wren Hollow Ln): the tax-unpaid
assumption said once, the markdown sheet's shorter notes, and "No HOA assumed".
"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render, oe, cf = load("seller-offer-review", "review", "render", "_shared.offer_engine", "_shared.contract_forms")

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")


def case05(a=None, b=None, listing=None):
    with open(os.path.join(FIXTURES, "listing-pays-buyer-broker.json")) as f:
        d = json.load(f)
    d["offers"][0].update(a or {})
    d["offers"][1].update(b or {})
    d["listing"].update(listing or {})
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def flag(o, topic):
    return next((f for f in o["flags"] if f.get("topic") == topic), None)


def rows(o):
    return {r[0]: r for r in o["counter_rows"]}


class RiderGGAgreement(unittest.TestCase):
    """1: an offer field records the compensation agreement; the flag names the real problem."""

    def test_signed_by_buyer_broker_names_the_listing_broker(self):
        R = review.analyze(case05(b={"compensation_agreement": "signed_by_buyer_broker", "buyer_broker_pct": 0.025}))
        f = flag(offer(R, "B"), "rider_GG")
        self.assertIn("not yet by the listing broker", f["issue"])
        self.assertIn("2.5%", f["issue"])
        self.assertNotIn("Get the signed agreement", f["fix"])
        self.assertIsNone(f.get("request"))  # the listing side's own signature: nothing to ask the buyer's agent

    def test_received_raises_nothing_and_ends_the_window(self):
        R = review.analyze(case05(b={"compensation_agreement": "received", "buyer_broker_pct": 0.025}))
        b = offer(R, "B")
        self.assertIsNone(flag(b, "rider_GG"))
        self.assertNotIn("GG", [w[0] for w in b["rider_windows"]])
        self.assertIsNotNone(flag(offer(R, "A"), "rider_GG"))  # A's agreement still isn't recorded

    def test_buyer_side_unsigned_asks_the_buyer_agent(self):
        R = review.analyze(case05(b={"compensation_agreement": "signed_by_listing_broker"}))
        f = flag(offer(R, "B"), "rider_GG")
        self.assertIn("not yet by the buyer's broker", f["issue"])
        self.assertTrue(f.get("request"))

    def test_seller_pays_and_signed_by_buyer_broker(self):
        R = review.analyze(case05(b={"buyer_broker_paid_by": None, "compensation_agreement": "signed_by_buyer_broker",
                                     "buyer_broker_pct": 0.025}))
        f = flag(offer(R, "B"), "rider_GG")
        self.assertIn("not yet by the seller", f["issue"])
        self.assertIn("its amount is in the net", f["fix"])

    def test_wrong_status_stops_with_every_problem(self):
        d = case05(a={"compensation_agreement": "maybe"},
                   b={"compensation_agreement": "signed_by_seller", "riders": ["B"]})
        with self.assertRaises(oe.OfferError) as e:
            review.analyze(d)
        msg = str(e.exception)
        self.assertIn("offers[A].compensation_agreement: 'maybe' isn't a status →", msg)
        self.assertIn("offers[B].compensation_agreement: set, but Rider GG isn't in riders →", msg)
        self.assertIn("offers[B].compensation_agreement: 'signed_by_seller', but buyer_broker_paid_by", msg)

    def test_seller_pays_received_needs_the_amount(self):
        probs = cf.compensation_agreement_problems({"riders": ["GG"], "compensation_agreement": "received"}, False)
        self.assertTrue(any("amount isn't recorded" in p for p in probs))
        self.assertEqual(cf.compensation_agreement_problems({"riders": ["GG"], "compensation_agreement": "signed both",
                                                              "buyer_broker_pct": 0.02}, False), [])


class EscalationForm(unittest.TestCase):
    """2: an Escalation Addendum whose box names the other contract form is a High issue (contract_forms' rule)."""

    def esc(self, form):
        return {"escalation": {"cap": 506000, "increment": 2000, "proof": True, "contract_form": form}}

    def test_standard_box_on_as_is_offer(self):
        R = review.analyze(case05(b=self.esc("Residential Contract for Sale and Purchase (FR/BAR)")))  # legacy name on the form, still read
        f = flag(offer(R, "B"), "escalation_form")
        self.assertEqual(f["sev"], "High")
        self.assertIn("Standard contract", f["issue"])
        self.assertIn("AS IS contract", f["issue"])
        self.assertTrue(f.get("request"))

    def test_matching_box_raises_nothing(self):
        R = review.analyze(case05(b=self.esc("as_is")))
        self.assertIsNone(flag(offer(R, "B"), "escalation_form"))

    def test_other_contract_box(self):
        self.assertIn('"CRSP"', cf.addendum_form_conflict(cf.STANDARD, "CRSP")[0])
        self.assertIsNone(cf.addendum_form_conflict(cf.OTHER, "standard"))

    def test_ambiguous_box_stops(self):
        with self.assertRaises(oe.OfferError) as e:
            review.analyze(case05(b=self.esc("FAR/BAR")))
        self.assertIn("offers[B].escalation.contract_form:", str(e.exception))


class HighestAndBest(unittest.TestCase):
    """3: with a call for highest and best out, nothing goes out before it: the counter's time ends at least a day after it."""

    def test_counter_time_counts_from_the_deadline(self):
        d = case05(listing={"highest_and_best_due": "2026-09-28 12:00"})
        b = offer(review.analyze(d), "B")
        self.assertEqual(rows(b)["Time for Acceptance"][2], "Tue Sep 29, 5:00 PM")
        d = case05(listing={"highest_and_best_due": None})
        b = offer(review.analyze(d), "B")
        self.assertEqual(rows(b)["Time for Acceptance"][2], "Fri Sep 25, 5:00 PM")  # Sep 24 is the offer's own deadline


class EscalationCounter(unittest.TestCase):
    """4: the counter to an escalating offer goes up to the cap, never past list; the comparison shows the clause."""

    def test_cap_above_list_counters_at_list(self):
        b = offer(review.analyze(case05()), "B")
        price = rows(b)["Price"]
        self.assertEqual(price[2], "$504,000")
        self.assertIn("escalation cap ($506,000)", price[3])

    def test_cap_between_partway_and_list_counters_at_the_cap(self):
        b = offer(review.analyze(case05(b={"escalation": {"cap": 501500, "increment": 1000, "proof": True}})), "B")
        self.assertEqual(rows(b)["Price"][2], "$501,500")
        self.assertIn("the most the buyer has said it will pay", rows(b)["Price"][3])

    def test_cap_below_partway_keeps_partway(self):
        b = offer(review.analyze(case05(b={"escalation": {"cap": 496000, "increment": 1000, "proof": True}})), "B")
        self.assertEqual(rows(b)["Price"][2:], ("$499,000", "Below list: meet partway"))

    def test_escalation_column(self):
        R = review.analyze(case05())
        v = review.multi_view(R)
        b = next(r for r in v["ranked"] if r["id"] == "B")
        self.assertEqual(b["escalation"], "Base $494,000 · +$2,000 · cap $506,000")
        self.assertIsNone(next(r for r in v["ranked"] if r["id"] == "A")["escalation"])
        doc, _, _ = render.build_html(R, {}, mode="multi")
        self.assertIn("<th>Escalation</th>", doc)
        self.assertIn("cap $506,000", doc)

    def test_no_escalation_no_column(self):
        R = review.analyze(case05(b={"escalation": None}))
        doc, _, _ = render.build_html(R, {}, mode="multi")
        self.assertNotIn("<th>Escalation</th>", doc)


class NoCmaWording(unittest.TestCase):
    """5: with no CMA, the escalation cap is measured against list price, never called a value range."""

    def test_list_price_not_value_range(self):
        b = offer(review.analyze(case05()), "B")
        f = flag(b, "escalation_cap_over_value")
        self.assertIn("above what list price and gap coverage support", f["issue"])
        d = case05(listing={"cma_low": 480000, "cma_high": 500000})
        f = flag(offer(review.analyze(d), "B"), "escalation_cap_over_value")
        self.assertIn("the value range", f["issue"])


(compute,) = load("seller-net-sheet", "compute")

WREN = {"prepared_date": "2026-09-26", "closing_date": "2026-12-04",
        "property": {"address": "3318 Wren Hollow Ln", "city": "Casselberry", "county": "Seminole", "state": "FL"},
        "scenarios": [{"price": 425000}, {"price": 410000}],
        "costs": {"listing_fee_pct": 0.0275, "buyer_broker_fee_pct": 0.025, "mortgage_payoff": 188000, "annual_tax": 5400}}


class NetSheetNotes(unittest.TestCase):
    """7, 9: the tax-unpaid assumption is said once; chat_notes leave out what the assumptions say; No HOA assumed."""

    def test_tax_unpaid_once(self):
        C = compute.run(copy.deepcopy(WREN))
        self.assertEqual(len([n for n in C["notes"] if "unpaid" in n]), 1)
        self.assertEqual(len([n for n in C["notes"] if n.startswith("Property tax")]), 1)
        self.assertFalse([n for n in C["chat_notes"] if "unpaid" in n or "title company's quote" in n])
        self.assertTrue(any(n.startswith("Property tax prorated from Jan 1") for n in C["chat_notes"]))
        self.assertTrue(any("assumed unpaid" in a for a in C["assumptions"]))

    def test_no_hoa_assumed(self):
        C = compute.run(copy.deepcopy(WREN))
        self.assertTrue(any(a.startswith("No HOA assumed") for a in C["assumptions"]))
        for prop in ({"hoa": False}, {"hoa_monthly": 120}, {"property_type": "condo"}):
            d = copy.deepcopy(WREN)
            d["property"].update(prop)
            self.assertFalse(any(a.startswith("No HOA assumed") for a in compute.run(d)["assumptions"]), prop)


if __name__ == "__main__":
    unittest.main()
