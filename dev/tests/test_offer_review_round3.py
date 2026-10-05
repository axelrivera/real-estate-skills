"""Seller-offer-review: manual round v5, case 05 (2604 Sable Palm Way, sources/Results_v5).

The case-5 listing inputs are replayed from the fixture listing-pays-buyer-broker.json (the kit's two packages: the
Castellanos offer with AGA-1, the Ostrander offer with EAC-1 paid in cash, NMOB-1 calling highest and best by Sep 23,
12:00 PM), with what the packages show that the fixture leaves out: both contracts name Greenleaf Realty Partners as the
listing side and both pre-approval letters say the lender reviewed the credit report, income and asset documentation.
The tests assert keys, numbers and structure, not whole sentences.
"""
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
PROFILE = {"brokerage": "LPT Realty, LLC"}


def case05(a=None, b=None, listing=None):
    with open(os.path.join(FIXTURES, "listing-pays-buyer-broker.json")) as f:
        d = json.load(f)
    for o in d["offers"]:
        o.update(listing_brokerage="Greenleaf Realty Partners", approval_documented=True,
                 compensation_agreement="signed_by_buyer_broker")
    d["offers"][0].update(a or {})
    d["offers"][1].update(b or {})
    d["listing"].update(listing or {})
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def views(d, agent=PROFILE):
    """(R, multi summary, single summary of A, single summary of B)."""
    R = review.analyze(d, agent=agent)
    return R, review.multi_view(R), review.single_view(R, offer(R, "A")), review.single_view(R, offer(R, "B"))


class WaitForFinalOffers(unittest.TestCase):
    """Item 1: with highest and best pending, the plan is to wait for the final offers, then decide; the counter is the
    fallback only."""

    def setUp(self):
        self.R, self.m, self.a, self.b = views(case05())

    def test_comparison_plan_is_to_wait(self):
        m = self.m
        self.assertEqual((m["headline"], m["title"]), (review.WAIT_HEADLINE, review.WAIT_TITLE))
        self.assertTrue(m["why"].startswith("Highest and best is due"))
        self.assertIn("If its final offer doesn't improve: counter at $504,000", m["why"])
        self.assertEqual(m["wait"]["due"], "Wed Sep 23, 12:00 PM")
        self.assertIn("doesn't improve: counter at $504,000", m["wait"]["fallback"])
        top = m["ranked"][0]
        self.assertEqual(top["action"], "Wait")
        self.assertTrue(top["terms"].startswith("If its final offer doesn't improve, counter: price $504,000"))
        self.assertTrue(m["plan_summary"].startswith("If the final offer doesn't improve"))

    def test_options_recommend_waiting(self):
        opts = self.m["options"]
        self.assertEqual((opts[0]["option"], opts[0]["recommended"]), ("Wait for Final Offers", True))
        self.assertEqual([o["recommended"] for o in opts[1:]], [False] * (len(opts) - 1))
        self.assertTrue(opts[1]["what"].startswith("The fallback if the final offers don't improve"))

    def test_respond_by_is_the_deadline(self):
        m = self.m
        self.assertEqual((m["respond_by"], m["respond_by_offer"]), ("Wed Sep 23, 12:00 PM", "Highest & Best Due"))
        self.assertEqual([(x["when"], x["what"]) for x in m["respond_by_also"]],
                         [("Thu Sep 24, 5:00 PM", "Ostrander Offer Expires"),
                          ("Wed Sep 23, 5:00 PM", "Backup: Ask to Extend")])

    def test_next_step_waits_then_falls_back(self):
        nxt = self.m["next_step"]
        self.assertTrue(nxt.startswith("Final offers are due"))
        self.assertIn("If the final Ostrander (Tidewater Key Realty) offer doesn't improve: approve the plan", nxt)
        self.assertNotIn("Then approve", nxt)

    def test_single_review_of_the_lead_offer(self):
        b = self.b
        self.assertEqual(b["headline"], review.WAIT_HEADLINE)
        self.assertIn("counter at $504,000 (below)", b["why"])
        self.assertEqual(b["respond_by_offer"], "Highest & Best Due")
        self.assertEqual(b["options"][0]["option"], "Wait for Final Offers")
        self.assertFalse(next(o for o in b["options"] if o["option"] == "Counter")["recommended"])
        self.assertIn("doesn't improve: approve the counter terms", b["next_step"])
        self.assertNotIn("::", b["next_step"].replace(" ", ""))
        self.assertEqual(b["counter"]["rows"][0]["counter"], "$504,000")  # the fallback's terms are still all there

    def test_pdf_names_the_counter_a_fallback(self):
        html = render.single_html(self.R, offer(self.R, "B"), self.b)[2]
        self.assertIn("FALLBACK COUNTER", html)
        self.assertNotIn("OUR COUNTER", html)
        self.assertIn("Fallback Counter to", render.multi_html(self.R, self.m)[2])

    def test_backup_review_keeps_its_plan(self):
        self.assertEqual(self.a["headline"], "HOLD AS BACKUP")
        self.assertIsNone(self.a["wait"])
        self.assertEqual(self.a["respond_by_offer"], "Backup: Ask to Extend")

    def test_passed_call_is_the_normal_plan(self):
        R, m, _, b = views(case05(listing={"highest_and_best_due": "2026-09-21 12:00"}))
        self.assertEqual((m["headline"], b["headline"]), ("COUNTER", "COUNTER"))
        self.assertIsNone(m["wait"])
        self.assertEqual(m["ranked"][0]["action"], "Counter")
        self.assertTrue(m["options"][0]["recommended"])
        self.assertIn("OUR COUNTER", render.single_html(R, offer(R, "B"), b)[2])


class TargetCaption(unittest.TestCase):
    def test_backup_tile_names_the_targets_closing_date(self):
        """Item 2: the backup's Seller's Target tile is on the recommended offer's closing date, as its number is."""
        R, _, a, _ = views(case05())
        tile = next(k for k in a["kpis"] if k["label"] == "Seller's Target Net")
        self.assertEqual(R["target_close"].isoformat(), "2026-10-28")
        self.assertTrue(tile["note"].endswith("closing Oct 28"), tile["note"])
        self.assertEqual(tile["value"], review.money(offer(R, "A")["target"]["net_adj"]))


class ListingSide(unittest.TestCase):
    """Item 3: the listing-brokerage confirmation never pins one offer's firm on another."""

    def item(self, d, sid=None, agent=PROFILE, mode=None):
        R = review.analyze(d, agent=agent)
        out = review.result(R, mode or ("single" if sid else "multi"), sid)
        found = [a["what"] for a in out["assumptions"] if a["field"] == "listing_brokerage"]
        return found, out["to_confirm"]

    def test_one_firm_on_both_contracts(self):
        found, ask = self.item(case05())
        self.assertEqual(len(found), 1)
        self.assertIn("both contracts name Greenleaf Realty Partners, but your profile says LPT Realty, LLC", found[0])
        self.assertNotIn("(", found[0].split("profile")[0])
        self.assertIn(found[0], ask)

    def test_single_review_cites_its_own_contract(self):
        for sid in ("A", "B"):
            found, ask = self.item(case05(), sid)
            self.assertEqual(len(found), 1, sid)
            self.assertTrue(found[0].startswith("Listing brokerage: the contract names Greenleaf Realty Partners, but"))
            for label in ("Castellanos", "Ostrander"):
                self.assertNotIn(label, found[0])
            self.assertIn(found[0], ask)

    def test_different_firms_name_each_offer(self):
        d = case05(a={"listing_brokerage": "Harborview Realty Group"})
        found, _ = self.item(d)
        self.assertIn("Harborview Realty Group (Castellanos · Sunward Homes Realty)", found[0])
        self.assertIn("Greenleaf Realty Partners (Ostrander · Tidewater Key Realty)", found[0])
        a, _ = self.item(d, "A")
        b, _ = self.item(d, "B")
        self.assertIn("Harborview", a[0])
        self.assertNotIn("Greenleaf", a[0])
        self.assertIn("Greenleaf", b[0])
        self.assertNotIn("Harborview", b[0])

    def test_offer_matching_the_profile_isnt_asked_in_its_review(self):
        d = case05(a={"listing_brokerage": "LPT Realty"})
        a, _ = self.item(d, "A")
        b, _ = self.item(d, "B")
        self.assertEqual(a, [])
        self.assertEqual(len(b), 1)

    def test_one_offer_says_the_contract(self):
        d = case05()
        d["offers"] = d["offers"][:1]
        d["listing"].pop("highest_and_best_due")
        found, _ = self.item(d, mode="single")
        self.assertTrue(found[0].startswith("Listing brokerage: the contract names Greenleaf Realty Partners"))


class EscalationFunding(unittest.TestCase):
    """Item 4: EAC-1 (a) pays the escalation in cash with proof of funds, so the pre-approval letter isn't its limit."""

    def topics(self, **b):
        return {f.get("topic"): f for f in offer(review.analyze(case05(b=b)), "B")["flags"]}

    def test_contract_forms_reads_how_it_is_paid(self):
        eac = {"addenda": ["Escalation Addendum to Contract (EAC-1)"], "escalation": {"cap": 1}}
        self.assertTrue(cf.escalation_paid_in_cash(cf.AS_IS, eac))  # neither box recorded: EAC-1's default, cash
        self.assertFalse(cf.escalation_paid_in_cash(cf.AS_IS, {**eac, "escalation": {"paid_in_cash": False}}))
        self.assertIsNone(cf.escalation_paid_in_cash("other", eac))
        self.assertIsNone(cf.escalation_paid_in_cash(cf.STANDARD, {"escalation": {"cap": 1}}))
        self.assertTrue(cf.escalation_proof_stated(cf.STANDARD, eac))
        self.assertFalse(cf.escalation_proof_stated("other", {"escalation": {"cap": 1}}))

    def test_cash_escalation_covered_by_the_proof_of_funds(self):
        t = self.topics()  # $88,000 verified; $506,000 less the $444,600 loan is $61,400
        self.assertNotIn("escalation_cap_over_approval", t)
        self.assertNotIn("escalation_cash_short", t)
        self.assertNotIn("escalation_cash_short", self.topics(escalation={"cap": 506000, "increment": 2000,
                                                                          "paid_in_cash": True}))

    def test_cash_escalation_short_of_funds(self):
        f = self.topics(proof_of_funds=50000)["escalation_cash_short"]
        self.assertEqual(f["sev"], "Med")
        self.assertIn("$61,400", f["issue"])
        self.assertNotIn("loan may not", f["issue"])

    def test_cash_escalation_with_its_own_proof(self):
        esc = {"cap": 506000, "increment": 2000, "paid_in_cash": True, "proof_of_funds": 70000}
        self.assertNotIn("escalation_cash_short", self.topics(proof_of_funds=None, escalation=esc))

    def test_cash_escalation_without_proof(self):
        f = self.topics(proof_of_funds=None)["escalation_cash_short"]
        self.assertIn("no proof of funds is in the package", f["issue"])

    def test_financed_escalation_never_asks_for_a_document_already_there(self):
        esc = {"cap": 506000, "increment": 2000, "paid_in_cash": False}
        f = self.topics(escalation=esc)["escalation_cap_over_approval"]
        self.assertIn("loan may not", f["issue"])
        self.assertNotIn("or proof of the added cash", f["fix"])
        self.assertIn("proof of funds in the package ($88,000)", f["fix"])
        f = self.topics(escalation=esc, proof_of_funds=None)["escalation_cap_over_approval"]
        self.assertIn("or proof of the added cash", f["fix"])

    def test_bad_fields_stop_the_review(self):
        for esc, field in (({"cap": 506000, "paid_in_cash": "yes"}, "escalation.paid_in_cash"),
                           ({"cap": 506000, "proof_of_funds": "88k"}, "escalation.proof_of_funds")):
            with self.assertRaises(oe.OfferError) as e:
                review.analyze(case05(b={"escalation": esc}))
            self.assertIn(f"offers[B].{field}:", str(e.exception))


class Questions(unittest.TestCase):
    def test_eac1_states_the_competing_offer_proof(self):
        """Item 5: EAC-1 says the seller supplies a redacted copy, so the buyer's agent isn't asked."""
        R = review.analyze(case05(b={"escalation": {"cap": 506000, "increment": 2000}}))
        self.assertNotIn("What proof of a competing offer does the escalation clause require?",
                         render.questions(offer(R, "B"), R))

    def test_unstated_proof_is_still_asked(self):
        d = case05(b={"escalation": {"cap": 506000, "increment": 2000}, "addenda": [], "contract_form": "other",
                      "riders": [], "compensation_agreement": None})
        R = review.analyze(d)
        self.assertIn("What proof of a competing offer does the escalation clause require?",
                      render.questions(offer(R, "B"), R))

    def test_documented_letter_asks_only_about_underwriting(self):
        """Item 6: the letter already says credit, income and assets were reviewed with documents."""
        R = review.analyze(case05())
        self.assertEqual(render.lender_questions(offer(R, "B"), R)[0],
                         "Has the file been through automated underwriting (DU or LP)?")
        R = review.analyze(case05(b={"approval_documented": False}))
        self.assertIn("verified with documents", render.lender_questions(offer(R, "B"), R)[0])


class Layout(unittest.TestCase):
    """Item 7: one short deadline format, kept on one line; one label for the backup's deadline."""

    def test_acceptance_row_uses_one_short_format(self):
        R = review.analyze(case05(listing={"highest_and_best_due": None}))
        row = next(r for r in offer(R, "A")["counter_rows"] if r[0] == "Time for Acceptance")
        self.assertEqual(row[1:3], ("Wed Sep 23, 5:00 PM", "Thu Sep 24, 5:00 PM"))
        self.assertEqual(oe.fmt_when_short("2026-09-24"), "Thu Sep 24")

    def test_deadline_cells_and_side_lines_do_not_wrap(self):
        R, m, _, b = views(case05())
        html = render.single_html(R, offer(R, "B"), b)[2]
        self.assertEqual(html.count('class="was oneline"'), 1)
        self.assertEqual(html.count('class="now oneline"'), 1)
        self.assertIn('class="hr stack"', render.hero(b))
        self.assertNotIn("stack", render.hero(m))
        self.assertIn('<td class="good oneline">', render.multi_html(R, m)[2])

    def test_backup_deadline_has_one_label(self):
        _, m, a, b = views(case05())
        labels = {x["what"] for v in (m, b) for x in v["respond_by_also"] if x["key"] == "backup_lapses"}
        self.assertEqual(labels | {a["respond_by_offer"]}, {"Backup: Ask to Extend"})

    def test_short_name_keeps_offers_apart(self):
        R = review.analyze(case05(a={"buyer_agent": "Emery Ostrander"}))
        self.assertNotEqual(review.short_name(offer(R, "A"), R), review.short_name(offer(R, "B"), R))


class ShortLastPage(unittest.TestCase):
    """Item 7: a last page under SHORT_TAIL full prints denser, kept only when that saves the page."""

    def run_write(self, fills):
        calls, it = [], iter(fills)

        class Page:
            def evaluate(self, js):
                calls[-1] = "dense" if "dense" in js else calls[-1]

        def to_pdf(doc, path, footer_html=None, landscape=False, before_print=None):
            calls.append("normal")
            return before_print(Page())

        saved = (render.render.html_to_pdf, render.pages, render.fit_page_one)
        render.render.html_to_pdf, render.pages = to_pdf, lambda path: next(it)
        render.fit_page_one = lambda pg, fit: (0, [])
        try:
            R = review.analyze(case05())
            render.write_pdf(R, {}, False, "single", "B", "/tmp")
        finally:
            render.render.html_to_pdf, render.pages, render.fit_page_one = saved
        return calls

    def test_denser_print_kept_when_it_saves_a_page(self):
        four = [(0.93, ""), (0.9, "Detailed Analysis"), (0.95, ""), (0.28, "")]
        three = [(0.93, ""), (0.9, "Detailed Analysis"), (0.98, "")]
        self.assertEqual(self.run_write([four, four, three]), ["normal", "dense"])

    def test_denser_print_dropped_when_it_saves_nothing(self):
        four = [(0.93, ""), (0.9, "Detailed Analysis"), (0.95, ""), (0.30, "")]
        self.assertEqual(self.run_write([four, four, four]), ["normal", "dense", "normal"])

    def test_fuller_last_page_is_left_alone(self):
        four = [(0.93, ""), (0.9, "Detailed Analysis"), (0.95, ""), (0.5, "")]
        self.assertEqual(self.run_write([four, four]), ["normal"])


if __name__ == "__main__":
    unittest.main()
