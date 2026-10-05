"""Seller-offer-review: counter terms the engine owns (counter.changes) and the case 05 manual-round fixes.

Case 05 of the manual round (sources/Results_v4): two offers on 2604 Sable Palm Way, the fixture
listing-pays-buyer-broker.json. The tests assert keys, numbers and structure, not whole sentences.
"""
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

review, render, oe = load("seller-offer-review", "review", "render", "_shared.offer_engine")

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def case05(**changes):
    """The case 05 listing, with `changes` merged into offer B (Ostrander, ranked first and countered)."""
    d = fixture("listing-pays-buyer-broker.json")
    d["offers"][1].update(changes)
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def rows(o):
    return {r[0]: r for r in o["counter_rows"]}


class CounterChanges(unittest.TestCase):
    """A: the agent's counter terms go in counter.changes; the engine writes every row, so rows, nets and the package
    agree."""

    def test_engine_counter_unchanged_without_changes(self):
        b = offer(review.analyze(case05()), "B")
        # iteration 12: B's escalation cap ($506,000) reaches list, so the engine counters at list, not partway
        self.assertEqual(rows(b)["Price"][2], "$504,000")
        self.assertEqual(rows(b)["Pre-Approval"][2], "Updated letter at $504,000 in 3 days")  # engine wording, never "New letter"

    def test_pinned_price_moves_every_dependent_row_and_the_net(self):
        b = offer(review.analyze(case05(counter={"changes": {"price": 502000}})), "B")
        r = rows(b)
        self.assertEqual(r["Price"][1:], ("$494,000", "$502,000", oe.AGENT_WHY))
        self.assertEqual(r["Pre-Approval"][2], "Updated letter at $502,000 in 3 days")
        self.assertEqual((b["counter_terms"]["price"], b["ns_counter"]["lines"][0][2]), (502000, 502000))
        self.assertEqual(r["Time for Acceptance"][0], b["counter_rows"][-1][0])

    def test_engine_value_keeps_the_rule_why(self):
        b = offer(review.analyze(case05(counter={"changes": {"price": 504000}})), "B")
        self.assertIn("escalation cap ($506,000)", rows(b)["Price"][3])
        b = offer(review.analyze(case05(escalation=None, counter={"changes": {"price": 499000}})), "B")
        self.assertEqual(rows(b)["Price"][3], "Below list: meet partway")

    def test_change_equal_to_the_offer_drops_the_row(self):
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
        self.assertTrue(all(":" in m and "→" in m for m in msg), msg)
        joined = "\n".join(msg)
        for field in ("offers[B].counter.rows", "offers[B].counter.changes.prise", "offers[B].counter.changes.deposit",
                      "offers[B].counter.changes.closing_date", "offers[B].counter.changes.inspection_days",
                      "offers[A].counter.price"):
            self.assertIn(field + ":", joined)
        self.assertIn("counter.changes", joined)

    def test_review_cli_reports_the_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "l.json")
            with open(path, "w") as f:
                json.dump(case05(counter={"changes": {"price": -5}}), f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = review.main([path])
        res = json.loads(out.getvalue())
        self.assertEqual((code, res["ok"]), (1, False))
        self.assertIn("offers[B].counter.changes.price", res["problems"][0])


class OneTarget(unittest.TestCase):
    """F: one Seller's Target per listing: the chart's equals every single review's (the recommended offer's closing)."""

    def test_chart_and_single_reviews_share_one_target(self):
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        top = R["ranked"][0]
        self.assertEqual(R["target_close"], top["close"])
        for o in R["offers"]:
            self.assertEqual(o["target"]["net_adj"], R["target"]["net_adj"], o["id"])
        doc, _, _ = render.build_html(R, {}, mode="single", offer_id="A")
        self.assertIn(oe.money(R["target"]["net_adj"]), doc)
        self.assertIn("the recommended offer's date", doc)

    def test_four_offers_one_target(self):
        R = review.analyze(fixture("four-offers.json"))  # title terms may differ by offer (OFR-103); the closing never does
        self.assertEqual({o["target"]["close"] for o in R["offers"]}, {R["target_close"]})
        self.assertIs(R["target"], R["ranked"][0]["target"])


class ListingSide(unittest.TestCase):
    """F: the listing brokerage the contracts name is checked against the profile's, once."""

    def item(self, R):
        return [a for a in R["missing"] if a["field"] == "listing_brokerage"]

    def test_profile_mismatch_asked_once(self):
        d = case05()
        for o in d["offers"]:
            o["listing_brokerage"] = "Greenleaf Realty Partners"
        R = review.analyze(d, agent={"brokerage": "LPT Realty, LLC"})
        found = self.item(R)
        self.assertEqual(len(found), 1)
        self.assertIn("Greenleaf Realty Partners", found[0]["why"])
        self.assertIn("LPT Realty, LLC", found[0]["why"])
        self.assertIn(found[0]["why"], review.to_confirm(R))

    def test_same_firm_not_asked(self):
        d = case05(listing_brokerage="LPT Realty")
        self.assertEqual(self.item(review.analyze(d, agent={"brokerage": "LPT Realty, LLC"})), [])

    def test_offers_disagree_without_a_profile(self):
        d = case05(listing_brokerage="Greenleaf Realty Partners")
        d["offers"][0]["listing_brokerage"] = "LPT Realty"
        self.assertEqual(len(self.item(review.analyze(d))), 1)
        self.assertEqual(self.item(review.analyze(case05(listing_brokerage="Greenleaf Realty Partners"))), [])


class FinancingChecks(unittest.TestCase):
    def test_pre_approval_below_the_escalation_cap_is_a_risk(self):
        b = offer(review.analyze(case05()), "B")  # letter to $494,000, cap $506,000
        f = next(f for f in b["flags"] if f.get("topic") == "escalation_cap_over_approval")
        self.assertEqual(f["sev"], "Med")
        self.assertIn("$506,000", f["issue"])

    def test_letter_covering_the_cap_is_not_flagged(self):
        b = offer(review.analyze(case05(approval_max_price=510000, approval_max_loan=460000)), "B")
        self.assertNotIn("escalation_cap_over_approval", [f.get("topic") for f in b["flags"]])

    def test_loan_cap_below_the_loan_at_the_cap(self):
        b = offer(review.analyze(case05(approval_max_price=None)), "B")  # $444,600 loan cap; at $506,000 the loan is higher
        self.assertIn("escalation_cap_over_approval", [f.get("topic") for f in b["flags"]])

    def test_proof_of_funds_answers_the_funds_question(self):
        R = review.analyze(case05())
        qs = " ".join(render.lender_questions(offer(R, "B"), R))
        self.assertNotIn("assets", qs)
        self.assertNotIn("Are funds verified", qs)
        R = review.analyze(case05(proof_of_funds=None))
        qs = " ".join(render.lender_questions(offer(R, "B"), R))
        self.assertIn("assets", qs)


class Wording(unittest.TestCase):
    def test_multi_preliminary_names_every_missing_input(self):
        s = review.multi_view(review.analyze(fixture("listing-pays-buyer-broker.json")))
        self.assertIn("CMA range", s["preliminary"])
        self.assertIn("mortgage payoff", s["preliminary"])

    def test_backup_rider_has_one_name(self):
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        name = oe.cf.rider_name("W")
        texts = [review.single_view(R, offer(R, "A"))["next_step"], review.single_view(R, offer(R, "A"))["options"][0]["what"],
                 review.multi_view(R)["ranked"][1]["terms"]]
        for t in texts:
            self.assertIn(name, t)
            self.assertNotIn("Back-Up Contract rider", t)

    def test_no_bare_form_codes_in_engine_text(self):
        for name in ("listing-pays-buyer-broker.json", "expired-aga.json", "six-offers.json"):
            R = review.analyze(fixture(name))
            for o in R["offers"]:
                text = " ".join([f["issue"] + " " + f["fix"] for f in o["flags"]] + list(o["score"]["why"].values())
                                + [r[0] for r in o["counter_rows"]])
                for code in ("AGA-1's", "(AGA-1)", "on AGA-1", "CASSB", "AGA-1 Valuation"):
                    self.assertNotIn(code, text.replace("Appraisal Gap Addendum (AGA-1)", ""), (name, o["id"], code))

    def test_respond_by_lines_are_short(self):
        s = review.single_view(*(lambda R: (R, offer(R, "B")))(review.analyze(fixture("listing-pays-buyer-broker.json"))))
        self.assertEqual(s["respond_by_also"][0]["when"], "Wed Sep 23, 12:00 PM")
        self.assertEqual(review.short_when("2026-09-23"), None)

    def test_gantt_short_last_week_has_no_date(self):
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        html = render.gantt(offer(R, "A"), R)
        heads = html.split("</thead>")[0].split("<th ")[4:]  # the date columns
        self.assertTrue(heads)
        for th in heads:
            span = int(th.split('colspan="')[1].split('"')[0])
            self.assertIn("white-space:nowrap", th)  # a date never wraps ("Nov / 3")
            if span < 3:
                self.assertIn("></th>", th)  # too narrow for a date: none


@unittest.skipUnless(render.shutil.which("pdftotext"), "pdftotext not installed")
class Layout(unittest.TestCase):
    """F: page 1 fits with 5 and 6 offers (CHART_MAX), and no printed page is near-empty."""

    def render(self, data, mode="multi"):
        R = review.analyze(data)
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                path = render.write_pdf(R, {"name": "Axel Rivera", "brokerage": "LPT Realty, LLC"}, False, mode,
                                        None if mode == "multi" else R["ranked"][0]["id"], tmp)
            return render.pages(path), err.getvalue()

    def check(self, data, mode="multi"):
        found, err = self.render(data, mode)
        self.assertNotIn("overflows", err)
        self.assertEqual(render.page_problems(found), [], found)
        self.assertTrue(found[1][1].startswith(render.DETAIL_HEADS), found[1][1])
        for i, (fill, first) in enumerate(found[1:-1], start=2):
            self.assertGreater(fill, 0.5, f"page {i} ({first})")

    def test_six_offers(self):
        d = fixture("six-offers.json")
        self.assertEqual(len(d["offers"]), render.CHART_MAX)
        self.check(d)

    def test_five_offers(self):
        d = fixture("six-offers.json")
        d["offers"] = d["offers"][:5]
        self.check(d)

    def test_case05_multi_and_single(self):
        d = fixture("listing-pays-buyer-broker.json")
        self.check(copy.deepcopy(d))
        self.check(d, "single")


if __name__ == "__main__":
    unittest.main()
