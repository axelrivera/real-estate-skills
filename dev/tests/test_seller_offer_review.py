"""Tests for skills/seller-offer-review/scripts."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, review_render, handoff = load("seller-offer-review", "review", "render", "_shared.handoff")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")
AGENT = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "brand": {"primary": "#0B6E4F"}}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = review.main(argv)
    return code, json.loads(out.getvalue())


class Analysis(unittest.TestCase):
    def test_single_summary_is_formatted(self):
        R = review.analyze(fixture("minimal-single.json"))
        out = review.result(R)
        s = out["summary"]
        self.assertEqual((out["mode"], s["action"]), ("single", "COUNTER"))
        self.assertTrue(s["preliminary"])
        self.assertEqual(s["kpis"][1]["value"], review.money(R["offers"][0]["ns"]["net_adj"]))  # net as written
        self.assertEqual(s["counter"]["rows"][-1]["term"], "Time for Acceptance")  # OFR-122
        self.assertEqual(out["value_range"], "not provided")
        self.assertTrue(out["to_confirm"])
        self.assertEqual(out["offers"][0]["net_sheet"]["columns"], ["As Offered", "Downside", "Counter"])

    def test_no_active_offers_stops(self):
        """OFR-22: only declined or expired offers is a plain stop, not a recommendation."""
        d = fixture("minimal-single.json")
        d["offers"][0]["status"] = "declined"
        with self.assertRaisesRegex(review.oe.OfferError, "No active offers"):
            review.result(review.analyze(d))
        shown = review.result(review.analyze(d), offer_id="A")
        self.assertEqual(shown["summary"]["action"], "DECLINE")

    def test_multi_plan(self):
        out = review.result(review.analyze(fixture("four-offers.json")))
        s = out["summary"]
        # the seller wants certainty: B (86) isn't risked for a 0.7% gain
        self.assertEqual(s["headline"], "ACCEPT")
        self.assertEqual([(p["key"], p["action"]) for p in s["ranked"]],
                         [("B", "Accept"), ("C", "Hold as Backup"), ("A", "Decline"), ("D", "Decline")])
        self.assertEqual(s["offer_label"], s["ranked"][0]["offer"])
        self.assertNotIn("Offer B", json.dumps(s))
        data = fixture("four-offers.json")
        data["seller"]["priority"] = "balanced"
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["headline"], "COUNTER")
        self.assertIsNone(s["preliminary"])

    def test_single_report_in_multi_context(self):
        R = review.analyze(fixture("four-offers.json"))
        out = review.result(R, mode="single", offer_id="A")
        self.assertEqual(out["summary"]["action"], "DECLINE")
        self.assertEqual(out["summary"]["compare"]["vs"], "Park · Coldwell Banker")
        data = fixture("four-offers.json")
        del data["offers"][0]["deposit"]
        out = review.result(review.analyze(data), mode="single", offer_id="A")
        self.assertIn("Morales · Keller Williams", [a["where"] for a in out["assumptions"]])  # other offers are active
        with self.assertRaises(review.oe.OfferError):
            review.result(review.analyze(fixture("minimal-single.json")), mode="multi")

    def test_labels(self):
        oe = review.oe
        self.assertEqual([oe.surname(n) for n in ("J. Morales", "Ana de la Cruz", "Tom Hill Jr.", "Cher")],
                         ["Morales", "de la Cruz", "Hill", "Cher"])
        self.assertEqual([oe.short_price(v) for v in (432000, 432500, 1250000, 1000000)], ["$432K", "$432.5K", "$1.25M", "$1M"])
        offs = [{"id": "A", "price": 400000, "financing": "fha", "buyer_agent": "Ana Ruiz", "buyer_brokerage": "Compass"},
                {"id": "B", "price": 410000, "financing": "cash", "buyer_agent": "Bo Ruiz", "buyer_brokerage": "Compass"},
                {"id": "C", "price": 400000, "financing": "fha"}, {"id": "D", "price": 400000, "financing": "fha"},
                {"id": "offer-5", "price": 390000, "financing": "va", "label": "Smith Offer"}]
        oe.label_offers(offs)
        self.assertEqual([o["label"] for o in offs], ["Ruiz · Compass, $400K FHA", "Ruiz · Compass, $410K Cash",
                                                      "$400K FHA, C", "$400K FHA, D", "Smith"])
        self.assertEqual((offs[0]["ref"], offs[4]["ref"], offs[4]["key"]),
                         ("the Ruiz (Compass, $400K FHA) offer", "the Smith offer", "E"))

    def test_single_review_shows_no_letters(self):
        out = review.result(review.analyze(fixture("texas-single.json")))
        self.assertNotRegex(json.dumps(out["summary"]) + json.dumps(out["assumptions"]), r"Offer [A-D]\b")
        doc, _, _ = review_render.build_html(review.analyze(fixture("texas-single.json")), {}, sample=False)
        self.assertNotRegex(doc, r"Offer [A-D]\b")
        self.assertIn("Offer from Whitfield · Compass", doc)  # offers go by agent and brokerage, never a letter
        self.assertIn("<td>Buyer / Agent</td>", doc)  # the buyer's name appears once, as contract identification

    def test_incomplete_contract_gets_no_recommendation(self):
        out = review.result(review.analyze(fixture("incomplete-single.json")))
        s = out["summary"]
        self.assertEqual((s["action"], s["headline"], s["counter"], s["options"]), ("INCOMPLETE", "CONTRACT INCOMPLETE", None, []))
        self.assertEqual([f["sev"] for f in s["fixes"]], ["Blocking", "High", "High", "High"])
        self.assertNotIn("recommended", json.dumps(s).replace("no recommendation", ""))
        topics = {f["topic"] for f in review.analyze(fixture("incomplete-single.json"))["offers"][0]["flags"]}
        self.assertLessEqual({"rider_E", "lead_paint", "loan_amount"}, topics)

    def test_incomplete_offer_is_listed_but_not_ranked(self):
        data = fixture("four-offers.json")
        data["offers"][2]["contract_issues"] = [{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for the complete contract."}]
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual([(r["rank"], r["offer"], r["action"]) for r in s["ranked"]][-1], ("—", "Díaz · eXp Realty", "Incomplete"))
        self.assertEqual(s["offers_active"], 4)
        self.assertEqual(review.oe.as_request("Ask for the signed rider."), "Please send the signed rider.")

    def test_cli_reports_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "listing.json")
            with open(path, "w") as f:
                json.dump({"listing": {"address": "1 Main St"}, "offers": [{"price": 1}]}, f)
            code, out = run([path])
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn("list price", out["problems"][0])

    def test_cma_handoff_in_markdown(self):
        h = handoff.build(side="seller", as_of="2026-09-20", subject={"address": "1207 Palmetto Way"},
                          value={"low": 380000, "high": 398000, "midpoint": 390000}, comps=[])
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "seller-cma.md")
            with open(md, "w") as f:
                f.write("## Seller CMA\n\nSummary.\n\n" + handoff.to_block(h) + "\n")
            code, out = run([os.path.join(FIXTURES, "minimal-single.json"), "--cma", md])
        self.assertEqual(code, 0)
        self.assertEqual(out["value_range"], "$380,000–$398,000")
        self.assertNotIn("No CMA range", json.dumps(out["assumptions"]))

    def test_texas_uses_estimates_not_florida_values(self):
        out = review.result(review.analyze(fixture("texas-single.json")))
        self.assertNotIn("transfer tax", out["summary"]["preliminary"] or "")
        self.assertIn("national estimate", json.dumps(out))
        notes = out.pop("chat_notes")  # the chat-only best-effort line names Florida on purpose
        self.assertEqual(out["support"], "best_effort")
        self.assertTrue(any("Only Florida FR/BAR contracts are fully supported" in n for n in notes))
        self.assertNotIn("Florida", json.dumps(out))

    def test_best_effort_line_never_on_the_report(self):
        data = fixture("texas-single.json")
        doc, _, _ = review_render.build_html(review.analyze(data), {}, sample=False)
        self.assertNotIn("fully supported", doc)
        self.assertNotIn("best-effort", doc)

    def test_frbar_offer_is_fully_supported(self):
        out = review.result(review.analyze(fixture("two-offers-accept.json")))
        self.assertEqual((out["support"], out["chat_notes"]), ("full", []))


class Pdf(unittest.TestCase):
    def test_html_uses_seller_theme_and_profile(self):
        R = review.analyze(fixture("two-offers-accept.json"))
        doc, mode, o = review_render.build_html(R, AGENT, sample=True)
        self.assertEqual((mode, o), ("multi", None))
        self.assertIn("ACCEPT", doc)
        self.assertIn("B (#1)", doc)  # letters only with their key (OFR-28: and rank)
        self.assertNotIn("CMA midpoint", doc)  # OFR-4: the downside appraisal is at the CMA high
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Seller Side", doc)
        self.assertIn("SAMPLE DATA", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)  # no license in the profile: nothing printed
        self.assertNotIn("#C2410C", doc)  # the default orange isn't hard-coded anywhere

    def test_comparison_is_one_row_per_offer(self):
        data = fixture("four-offers.json")
        base = data["offers"][1]
        for i in range(5):  # nine offers: rows, not columns, and no chart past six
            data["offers"].append(dict(base, id="EFGHI"[i], price=base["price"] - 1000 * (i + 1),
                                       buyer_agent=f"Agent{i} · Brokerage{i}"))
        doc, mode, _ = review_render.build_html(review.analyze(data), AGENT, sample=True)
        self.assertEqual(mode, "multi")
        self.assertEqual(doc.count('<td class="rk">'), 9)
        self.assertNotIn('class="scat"', doc)
        self.assertIn("Key Terms Side by Side", doc)
        self.assertNotIn("Certainty Scorecard", doc)  # detail lives in the single reviews
        doc, _, _ = review_render.build_html(review.analyze(fixture("four-offers.json")), AGENT, sample=True)
        self.assertIn('class="scat"', doc)
        self.assertIn("@page{size:Letter landscape}", doc)
        single, _, _ = review_render.build_html(review.analyze(fixture("minimal-single.json")), {}, sample=False)
        self.assertNotIn("@page{size:Letter landscape}", single)

    def test_packet(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = review_render.main([os.path.join(FIXTURES, "two-offers-accept.json"), "--packet", "--out", tmp])
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["2250-Oak-Hollow-Ct-Multiple-Offer-Review.pdf", "2250-Oak-Hollow-Ct-512K-Conventional-Offer-Review.pdf",
                          "2250-Oak-Hollow-Ct-519K-VA-Offer-Review.pdf"])

    def test_lender_call_is_a_step_not_a_flag(self):
        data = fixture("minimal-single.json")
        R = review.analyze(data)
        self.assertFalse(any("Lender not yet called" in f["issue"] for f in R["offers"][0]["flags"]))
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("Questions for the Loan Officer", doc)
        self.assertIn("on an FHA loan?", doc)
        self.assertIn("Loan officer called", doc)  # a checklist step
        self.assertNotIn("pill vno", doc)
        self.assertNotIn("Can the buyer increase the escrow deposit", doc)  # the counter asks it
        R = review.analyze(fixture("four-offers.json"))
        doc, _, _ = review_render.build_html(R, {}, sample=False, mode="single", offer_id="B")
        self.assertIn("None: the contract covers it.", doc)  # accepted as written: nothing to ask
        self.assertIn("on a conventional loan?", doc)

    def test_default_theme_without_profile(self):
        R = review.analyze(fixture("minimal-single.json"))
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("--brand:#C2410C", doc)  # seller default from shared/design
        self.assertIn("Single Offer Review", doc)
        self.assertIn("Prepared for", doc.split("<body")[1].split("</header>")[0])  # no agent lines without a profile
        self.assertNotIn("None", doc.split("<body")[1].split("</header>")[0])

    def test_texas_fine_print(self):
        doc, _, _ = review_render.build_html(review.analyze(fixture("texas-single.json")), {}, sample=False)
        self.assertIn("licensed in Texas", doc)
        self.assertNotIn("Florida", doc)

    def test_renders_a_pdf(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = review_render.main([os.path.join(FIXTURES, "minimal-single.json"), "--out", tmp])
            self.assertEqual([os.path.basename(p) for p in paths], ["1207-Palmetto-Way-382K-FHA-Offer-Review.pdf"])
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")



class CounterWording(unittest.TestCase):
    def test_counter_says_what_changes(self):
        """OFR-16: net and certainty in the Counter row come from the actual deltas."""
        s = review.counter_what(2500, 6000, -2, "COUNTER")
        self.assertTrue("+$2,500" in s and "-2 points" in s and "less certain" in s, s)
        s = review.counter_what(-3000, 4000, 5, "COUNTER")
        self.assertTrue("−$3,000" in s and "+$4,000" in s and "+5 points" in s and "more certain" in s, s)
        self.assertIn("strong offer", review.counter_what(800, 800, 0, "ACCEPT"))


class LapsedOffers(unittest.TestCase):
    """A lapsed offer is CONTRACT INCOMPLETE, never 'send before <a past date>', and shows what a counter could be."""

    def test_passed_deadline(self):
        s = review.result(review.analyze(fixture("expired-aga.json")))["summary"]
        self.assertTrue(s["respond_by"].startswith("Passed ("))
        self.assertNotIn("before Sep", s["next_step"])
        self.assertEqual([r["counter"] for r in s["revive"]["rows"]][0], "$497,000")
        self.assertIsNone(s["counter"])

    def test_estimated_deadline_counters_without_a_past_date(self):
        s = review.result(review.analyze(fixture("counter-chain-standard.json")))["summary"]
        self.assertTrue(s["respond_by"].startswith("Likely passed ("))
        self.assertNotIn("before", s["next_step"])
        self.assertIn("Oct 26", s["certainty"]["walk_away_until"])  # the 30 days are golden's risk_days

    def test_broken_contract_gets_no_revive(self):
        s = review.result(review.analyze(fixture("incomplete-single.json")))["summary"]
        self.assertIsNone(s["revive"])

    def test_lapsed_review_states_facts_and_labels_the_counter(self):  # FH-103, DS-106, OFR-120
        R = review.analyze(fixture("expired-aga.json"))
        s = review.result(R)["summary"]
        self.assertNotIn("can't be accepted", json.dumps(s))
        self.assertEqual(s["revive"]["rows"][-1]["term"], "Time for Acceptance")  # OFR-122
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("Counter (Reference)", doc)
        self.assertNotIn("Proposed Counter", doc)
        self.assertNotIn("No significant risks found", doc)
        data = fixture("expired-aga.json")
        data["offers"].append(dict(data["offers"][0], id="B", expires="2026-10-30 17:00", price=480000))
        data["offers"].append(dict(data["offers"][0], id="C", expires="2026-10-30 17:00", price=470000))
        R = review.analyze(data)
        out = review.result(R, mode="multi")
        lapsed = next(r for r in out["summary"]["ranked"] if r["action"] == "Incomplete")
        self.assertIn("Sep", lapsed["terms"])  # the date keeps its case
        doc, _, _ = review_render.build_html(R, {}, sample=False, mode="multi")
        self.assertIn("2 active offers, 1 incomplete", doc)

    def test_aga_window_is_a_condition(self):
        c = review.result(review.analyze(fixture("expired-aga.json")))["summary"]["certainty"]
        self.assertIn("Oct 26", c["walk_away_until"])  # risk_days 36 / 30 are pinned by golden
        self.assertIn("gap", c["walk_away_note"])


class Audit20260929(unittest.TestCase):
    """Fixes from the 2026-09-29 audit in the review and the PDF."""

    def test_blocked_other_contract_keeps_its_chat_note(self):  # OFR-114
        data = fixture("four-offers.json")
        data["offers"][0].update(contract_form="Texas TREC 20-18", inspection_walkaway=True,
                                 contract_issues=[{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for it."}])
        out = review.result(review.analyze(data), mode="multi")
        self.assertEqual(out["support"], "best_effort")

    def test_no_zero_gain_counter_option(self):  # OFR-116
        R = review.analyze(fixture("two-offers-accept.json"))
        top = R["ranked"][0]
        top["ns_counter"] = dict(top["ns_counter"], net_adj=top["ns"]["net_adj"])
        opts = review.multi_view(R)["options"]
        self.assertFalse([o for o in opts if o["option"].endswith("Anyway")])

    def test_no_deadline_is_stated_as_such(self):  # OFR-120
        data = fixture("two-offers-accept.json")
        for o in data["offers"]:
            o.pop("expires", None)
        self.assertEqual(review.first_expiry(review.analyze(data))[0], "No time stated")

    def test_rider_k_label_on_the_terms_table(self):  # ENG-11
        data = fixture("minimal-single.json")
        data["offers"][0].update(contract_form="standard", riders=["K"])
        doc, _, _ = review_render.build_html(review.analyze(data), {}, sample=False)
        self.assertIn("Standard + As Is Rider (K) · K", doc)


class AuditPlanWording(unittest.TestCase):
    """OFR-6, OFR-21: no backup request while the primary is open; disclosure needs the seller's authorization."""

    def test_backup_only_after_primary_is_signed(self):
        out = review.result(review.analyze(fixture("escalation.json")))
        text = json.dumps(out)
        self.assertIn("once that contract is fully signed", out["summary"]["next_step"] if "next_step" in out["summary"] else text)
        self.assertNotIn("request a backup contract", text)
        self.assertIn("written authorization", text)


if __name__ == "__main__":
    unittest.main()
