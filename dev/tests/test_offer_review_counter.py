"""Counter rules: the counter price against the negotiation history, the agent's counter.changes, which terms are
countered or restated, and the counter's time for acceptance."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, oe = load("seller-offer-review", "review", "_shared.offer_engine")

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")

BASE = {"analysis_date": "2026-09-23",
        "listing": {"address": "1 Test St, Longwood, FL 32750", "state": "FL", "county": "Seminole", "list_price": 400000,
                    "cma_low": 390000, "cma_high": 410000, "annual_tax": 5000, "hoa_monthly": 0, "flood_disclosure": True},
        "seller": {"payoff": 200000, "listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.025}}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def hand(**k):
    """A hand-built FAR/BAR AS IS offer on BASE."""
    o = {"id": "A", "contract_form": "as_is", "price": 400000, "financing": "conventional", "down_pct": 0.2, "deposit": 10000,
         "seller_concessions": 0, "inspection_days": 10, "loan_approval_days": 30, "closing_date": "2026-11-06",
         "title_by": "seller"}
    o.update(k)
    return o


def first(*offers, listing=None, seller=None):
    d = copy.deepcopy(BASE)
    d["offers"] = list(offers)
    d["listing"].update(listing or {})
    d["seller"].update(seller or {})
    return oe.analyze(d)["offers"][0]


def case05(**changes):
    """Two offers on 2604 Sable Palm Way, with `changes` merged into offer B (escalation, ranked first, countered)."""
    d = fixture("listing-pays-buyer-broker.json")
    d["offers"][1].update(changes)
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def rows(o):
    return {r[0]: r for r in o["counter_rows"]}


class CounterPrice(unittest.TestCase):
    def test_negotiation_history_bounds_the_price(self):
        for prior, price, want in ((405000, 420000, 405000),  # the seller's counter above list is the ceiling
                                   (408000, 402000, 405000),  # meet partway up to the seller's counter
                                   (415000, 420000, 415000)):  # appraisal branch: never below the seller's counter
            with self.subTest(prior=prior, price=price):
                o = first(hand(price=price, prior_counters=[{"by": "seller", "price": prior}]))
                self.assertEqual(o["counter_terms"]["price"], want)
        o = first(hand(price=420000, prior_counters=[{"by": "seller", "price": 415000}]))
        self.assertEqual(o["counter_terms"]["appraisal_gap"], 5000)

    def test_over_list_without_a_cma_keeps_its_price_and_asks_for_gap(self):
        d = copy.deepcopy(BASE)
        d["listing"].pop("cma_low"), d["listing"].pop("cma_high")
        d["offers"] = [hand(price=410000)]
        o = oe.analyze(d)["offers"][0]
        self.assertEqual((o["counter_terms"]["price"], o["counter_terms"]["appraisal_gap"]), (410000, 10000))
        self.assertNotIn("Price", rows(o))

    def test_counter_never_asks_fha_for_gap_money(self):
        """An FHA/VA gap clause doesn't bind the buyer: a price over the range is countered to its top, no gap row."""
        fha = offer(oe.analyze(fixture("four-offers.json")), "A")
        self.assertNotIn("Appraisal Gap Coverage", rows(fha))

    def test_counter_respects_the_sellers_last_counter(self):
        o = oe.analyze(fixture("counter-chain-standard.json"))["offers"][0]
        self.assertEqual(rows(o)["Inspection Period"][3], oe.RESTATE)
        d = fixture("counter-chain-standard.json")
        d["offers"][0]["price"] = 600000
        self.assertLessEqual(oe.analyze(d)["offers"][0]["counter_terms"]["price"], 629000)


class CounterTerms(unittest.TestCase):
    def test_restated_terms_from_the_chain(self):
        o = first(hand(seller_concessions=20000, prior_counters=[{"by": "seller", "price": 398000, "seller_concessions": None}]))
        self.assertIn("Seller Concessions", rows(o))  # a null in a counter isn't "no change"
        o = first(hand(closing_date="2026-11-13", loan_approval_days=30,
                       prior_counters=[{"by": "seller", "closing_date": "2026-11-06", "loan_approval_days": 21}]))
        self.assertIn("closing_date", [g[3] for g in oe.chain_gaps(o)])
        self.assertEqual((str(o["counter_terms"]["close"]), o["counter_terms"]["loan_approval_days"]), ("2026-11-06", 21))

    def test_loan_amount_and_buyer_changes(self):
        data = fixture("counter-chain-standard.json")
        o = data["offers"][0]
        o["balance_to_close"] = 128500  # left at the $610,000 original: 24,000 + 457,500 + 128,500
        o["prior_counters"].insert(0, {"by": "buyer", "note": "Original offer", "price": 610000, "closing_date": "2026-10-27"})
        a = review.analyze(data)["offers"][0]
        self.assertLessEqual({"loan_amount", "buyer_changes"}, {f.get("topic") for f in a["flags"]})
        terms = [r[0] for r in a["counter_rows"]]
        self.assertIn("Loan Amount and Balance to Close", terms)
        self.assertIn("Closing Date", terms)
        self.assertEqual(terms[-1], "Time for Acceptance")
        o["balance_to_close"] = 619500 - 24000 - 457500
        o["prior_counters"][0]["closing_date"] = "2026-11-16"
        topics = {f.get("topic") for f in review.analyze(data)["offers"][0]["flags"]}
        self.assertFalse({"loan_amount", "buyer_changes"} & topics)

    def test_assumed_inspection_period_is_confirmed_not_countered(self):
        o = review.analyze(fixture("minimal-single.json"))["offers"][0]
        self.assertNotIn("Inspection Period", rows(o))
        data = fixture("minimal-single.json")
        data["offers"][0]["inspection_days"] = 20  # given: countered to the market norm
        R = review.analyze(data)
        self.assertIn("Inspection Period", rows(R["offers"][0]))
        self.assertEqual(R["offers"][0]["counter_terms"]["inspection_days"], R["listing"]["norms"]["inspection_days"])

    def test_aga_valuation_period_counter(self):
        o = review.analyze(fixture("expired-aga.json"))["offers"][0]
        self.assertEqual(rows(o)["Appraisal Gap Valuation Period"][1:3], ("30 days (blank)", "24 days"))
        flag = next(f for f in o["flags"] if f["topic"] == "aga_window_at_closing")
        self.assertIsNone(flag["request"])  # the counter asks it

    def test_closing_given_as_days_is_shown_as_written(self):
        data = fixture("minimal-single.json")
        data["analysis_date"] = "2026-09-26"  # "close in 35 days": about Sat Oct 31, a date the buyer never wrote
        o = review.analyze(data)["offers"][0]
        self.assertEqual(rows(o)["Closing Date"][1], o["close_terms"])
        self.assertTrue(o["close_terms"].startswith("35 days after acceptance"))

    def test_preapproval_letter_asked_at_the_countered_price(self):
        o = first(hand(price=380000, approval_max_price=370000))
        req = [f["request"] for f in o["flags"] if f.get("topic") == "approval_cap"][0]
        self.assertIn(oe.money(o["counter_terms"]["price"]), req)
        for name in ("counter-chain-standard.json", "expired-aga.json"):  # at the cap: the counter above it asks for one
            self.assertIn("Pre-Approval", rows(oe.analyze(fixture(name))["offers"][0]), name)


class CounterChanges(unittest.TestCase):
    """The agent's counter terms go in counter.changes; the engine writes every row, so rows, nets and the package
    agree."""

    def test_pinned_price_moves_every_dependent_row_and_the_net(self):
        b = offer(review.analyze(case05(counter={"changes": {"price": 502000}})), "B")
        r = rows(b)
        self.assertEqual(r["Price"][1:], ("$494,000", "$502,000", oe.AGENT_WHY))
        self.assertIn("$502,000", r["Pre-Approval"][2])
        self.assertEqual((b["counter_terms"]["price"], b["ns_counter"]["lines"][0][2]), (502000, 502000))

    def test_engine_value_keeps_the_rule_why(self):
        b = offer(review.analyze(case05(counter={"changes": {"price": 504000}})), "B")
        self.assertNotEqual(rows(b)["Price"][3], oe.AGENT_WHY)
        b = offer(review.analyze(case05(escalation=None, counter={"changes": {"price": 499000}})), "B")
        self.assertEqual(rows(b)["Price"][3], "Below list: meet partway")
        b = offer(review.analyze(case05(counter={"changes": {"inspection_days": 10}})), "B")
        self.assertNotIn("Inspection Period", rows(b))
        self.assertEqual(b["counter_terms"]["inspection_days"], 10)

    def test_new_terms_alias_and_closing(self):
        b = offer(review.analyze(case05(counter={"changes": {"seller_credit": 3000, "closing_date": "2026-10-30",
                                                              "time_for_acceptance": "2026-09-25 12:00"}})), "B")
        r = rows(b)
        self.assertEqual(r["Seller Concessions"][1:3], ("$0", "$3,000"))
        self.assertEqual(r["Closing Date"][2], "Fri Oct 30")
        self.assertEqual(r["Time for Acceptance"][2], "Fri Sep 25, 12:00 PM")
        self.assertEqual(str(b["counter_terms"]["close"]), "2026-10-30")
        self.assertEqual(b["ns_counter"]["lines"][1][2], -3000)

    def test_every_problem_listed_at_once(self):
        d = case05(counter={"rows": [["Price", "$494,000", "$499,000", "x"]],
                            "changes": {"prise": 1, "deposit": "lots", "closing_date": "2026-09-01", "inspection_days": 7.5}})
        d["offers"][0]["counter"] = {"price": 495000}
        with self.assertRaises(oe.OfferError) as e:
            review.analyze(d)
        msg = str(e.exception).splitlines()
        self.assertEqual(len(msg), 6, msg)
        joined = "\n".join(msg)
        for field in ("offers[B].counter.rows", "offers[B].counter.changes.prise", "offers[B].counter.changes.deposit",
                      "offers[B].counter.changes.closing_date", "offers[B].counter.changes.inspection_days",
                      "offers[A].counter.price"):
            self.assertIn(field + ":", joined)
        with tempfile.TemporaryDirectory() as tmp:  # the CLI reports them as problems
            path = os.path.join(tmp, "l.json")
            with open(path, "w") as f:
                json.dump(case05(counter={"changes": {"price": -5}}), f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = review.main([path])
        res = json.loads(out.getvalue())
        self.assertEqual((code, res["ok"]), (1, False))
        self.assertIn("offers[B].counter.changes.price", res["problems"][0])


class TimeForAcceptance(unittest.TestCase):
    def test_every_counter_sets_one(self):
        o = first(hand(expires="2026-09-20 17:00", inspection_days=15))  # lapsed
        self.assertEqual(o["counter_rows"][-1][0], "Time for Acceptance")
        self.assertEqual(first(hand(price=395000))["counter_rows"][-1][0], "Time for Acceptance")
        self.assertEqual(first(hand(inspection_days=7, deposit=40000))["counter_rows"], [])  # nothing to counter: no row

    def test_never_the_offers_own_deadline(self):
        d = case05()
        d["listing"]["highest_and_best_due"] = None
        R = review.analyze(d)
        a, b = offer(R, "A"), offer(R, "B")  # B expires Thu Sep 24 5:00 PM, the same as the rule's two days
        self.assertEqual(str(oe.acceptance_due(b, R["listing"])), "2026-09-25")
        self.assertEqual(str(oe.acceptance_due(a, R["listing"])), "2026-09-24")  # other deadlines keep the rule
        self.assertEqual(rows(a)["Time for Acceptance"][1:3], ("Wed Sep 23, 5:00 PM", "Thu Sep 24, 5:00 PM"))
        self.assertEqual(rows(b)["Time for Acceptance"][2], "Fri Sep 25, 5:00 PM")
        self.assertEqual(oe.fmt_when_short("2026-09-24"), "Thu Sep 24")
        d["listing"]["highest_and_best_due"] = "2026-09-28 12:00"  # nothing goes out before a pending call
        self.assertEqual(rows(offer(review.analyze(d), "B"))["Time for Acceptance"][2], "Tue Sep 29, 5:00 PM")


if __name__ == "__main__":
    unittest.main()
