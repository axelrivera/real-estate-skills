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
        self.assertEqual(out["offers"][0]["net_sheet"]["columns"], ["As Offered", "Downside Case", "Proposed Counter"])  # OFR-354

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
        self.assertTrue(any("Only Florida FAR/BAR contracts are fully supported" in n for n in notes))
        self.assertNotIn("Florida", json.dumps(out))

    def test_best_effort_line_never_on_the_report(self):
        data = fixture("texas-single.json")
        doc, _, _ = review_render.build_html(review.analyze(data), {}, sample=False)
        self.assertNotIn("fully supported", doc)
        self.assertNotIn("best-effort", doc)

    def test_farbar_offer_is_fully_supported(self):
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

    def test_comparison_comes_with_each_single_review(self):
        """OFR-318: a comparison always comes with a single review of every active offer, each its own PDF."""
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = review_render.main([os.path.join(FIXTURES, "two-offers-accept.json"), "--out", tmp])
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["2250-Oak-Hollow-Ct-Multiple-Offer-Review.pdf", "2250-Oak-Hollow-Ct-512K-Conventional-Offer-Review.pdf",
                          "2250-Oak-Hollow-Ct-519K-VA-Offer-Review.pdf"])
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = review_render.main([os.path.join(FIXTURES, "two-offers-accept.json"), "--mode", "single",
                                        "--offer", "B", "--out", tmp])
        self.assertEqual(len(paths), 1)  # one offer asked for: just its review

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
        self.assertIn("None: the offer covers it.", doc)  # iteration 10 eval 1; accepted as written: nothing to ask
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

    def test_contingency_chart_rolls_like_page_one(self):
        """Eval 1 (iteration 9): the chart's Ends column showed Oct 11 while page 1 said Oct 13. Day 15 from Sep 26 is
        Sun Oct 11 and Mon Oct 12 is Columbus Day, so both read Oct 13."""
        d = fixture("minimal-single.json")
        d["analysis_date"] = "2026-09-26"
        doc, _, _ = review_render.build_html(review.analyze(d), {}, sample=False)
        self.assertIn("For any reason until Oct 13", doc)
        row = doc[doc.index("Inspection (Right to Cancel)"):][:200]
        self.assertIn("Oct 13", row)
        self.assertNotIn("Oct 11", row)

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
        self.assertTrue("+$2,500" in s and "−2 points" in s and "less certain" in s, s)  # OFR-290: a true minus
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
        self.assertIn("Nov 1", c["walk_away_until"])  # OFR-267: the longest window (36 days), pinned by golden
        self.assertIn("Oct 26", c["walk_away_note"])  # the other windows end at 30 days
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
        self.assertIn("Standard + As Is Rider (K)", doc)
        self.assertNotIn("Rider (K) · K", doc)  # iteration 9 eval 5: the rider isn't listed twice


class AuditPlanWording(unittest.TestCase):
    """OFR-6, OFR-21: no backup request while the primary is open; disclosure needs the seller's authorization."""

    def test_backup_only_after_primary_is_signed(self):
        out = review.result(review.analyze(fixture("escalation.json")))
        text = json.dumps(out)
        self.assertIn("once that contract is fully signed", out["summary"]["next_step"] if "next_step" in out["summary"] else text)
        self.assertNotIn("request a backup contract", text)
        self.assertIn("written authorization", text)


def assumption_fields(R):
    return {a["field"]: a for a in R["assumptions"]}


class Audit20260929Second(unittest.TestCase):
    """Second-pass fixes (OFR-251 to OFR-268), asserted on keys and numbers rather than prose."""

    def test_backup_keeps_its_own_price(self):  # OFR-251
        R = review.analyze(fixture("four-offers.json"))
        backup = next(o for o in R["ranked"] if o["action"] == "BACKUP")
        row = next(r for r in review.multi_view(R)["ranked"] if r["key"] == backup["key"])
        self.assertNotEqual(backup["counter_terms"]["price"], backup["price"])  # the counter would ask for more
        self.assertNotIn(review.money(backup["counter_terms"]["price"]), row["terms"])
        self.assertNotIn("$", row["terms"])

    def test_decline_reason_cites_certainty_when_it_nets_more(self):  # OFR-252
        close = review.oe._d("2026-11-07")
        top = {"ns": {"net_adj": 146209}, "ns_down": {"net_adj": 143209}, "score": {"total": 84}}
        o = {"sale_contingency_days": 0, "approval": "du_approved", "financed": True, "close": close,
             "ns": {"net_adj": 146694}, "ns_down": {"net_adj": 139942}, "score": {"total": 55}}
        S = {"deadline": review.oe._d("2026-11-15")}
        keys, why = review.oe.decline_reasons(o, top, S)
        self.assertEqual(keys, ["more_net_less_certain"])
        self.assertIn("55/100", why[0])
        keys, _ = review.oe.decline_reasons(dict(o, score={"total": 90}), top, S)
        self.assertEqual(keys, ["more_net_lower_downside"])
        keys, _ = review.oe.decline_reasons(dict(o, ns={"net_adj": 140000}), top, S)
        self.assertEqual(keys, ["nets_less"])
        R = review.analyze(fixture("four-offers.json"))
        self.assertEqual(next(o for o in R["offers"] if o["id"] == "D")["action_reason_keys"],
                         ["sale_contingency", "prequal", "past_deadline"])

    def test_no_state_follows_the_contract_form(self):  # OFR-253
        data = fixture("minimal-single.json")
        data["listing"]["address"] = "1207 Palmetto Way"
        data["offers"][0]["contract_form"] = "standard"
        R = review.analyze(data)
        self.assertEqual((R["listing"]["state"], assumption_fields(R)["state"]["value"]), ("FL", "FL"))
        self.assertTrue(R["costs"].state_assumed)
        self.assertIn("transfer", [k for k, _, v in R["offers"][0]["ns"]["lines"] if v])
        self.assertTrue(any("Assumed Florida" in n for n in R["listing"]["cost_notes"]))
        self.assertFalse(R["market_notes"])  # no "don't assume Florida" note next to Florida costs
        data["offers"][0].pop("contract_form")
        R = review.analyze(data)
        self.assertIsNone(R["listing"]["state"])
        self.assertIsNone(assumption_fields(R)["state"]["value"])
        self.assertFalse(R["costs"].state_assumed)
        self.assertEqual(R["costs"].source("closing_costs.deed_transfer_tax_rate"), "estimate")

    def test_unknown_hoa_estoppel_is_an_assumption(self):  # OFR-255
        R = review.analyze(fixture("minimal-single.json"))
        self.assertEqual(assumption_fields(R)["hoa_monthly"]["impact"], "low")
        data = fixture("minimal-single.json")
        data["listing"]["hoa_monthly"] = 0
        self.assertNotIn("hoa_monthly", assumption_fields(review.analyze(data)))

    def test_multi_counts_match_the_table(self):  # OFR-257
        data = fixture("four-offers.json")
        for o in data["offers"]:
            o.pop("title_by", None)
        R = review.analyze(data)
        listed = review.listed_assumptions(R, multi=True)
        self.assertIn("title_by", [a["field"] for a in listed])  # shared by several offers, so the comparison lists it
        v = review.multi_view(R)
        self.assertTrue(v["data_note"].startswith(f"{len(listed)} input"))
        doc, _, _ = review_render.build_html(R, {}, sample=False, mode="multi")
        table = doc.split("Assumptions &amp; Data to Confirm</h2>")[-1]
        self.assertEqual(table.count('<span class="pill '), len(listed))

    def test_approval_label_by_level(self):  # OFR-256
        self.assertNotIn("Pre-approval", review.oe.APPROVAL_LABEL["du_approved"])
        self.assertIn("DU/LP", review.oe.APPROVAL_LABEL["du_approved"])

    def test_listing_broker_pays_the_buyers_broker(self):  # OFR-259
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        R = review.analyze(data)
        o = R["offers"][0]
        target = {k: v for k, _, v in o["target"]["lines"]}
        offered = {k: v for k, _, v in o["ns"]["lines"]}
        self.assertEqual(target["bb"], 0)  # one total line in every column, the Seller's Target too
        self.assertAlmostEqual(target["listing"] / 504000, offered["listing"] / 489000, places=4)
        self.assertNotIn("Buyer-Broker Comp.", [r[0] for r in review_render.term_rows(o, R)])
        A = assumption_fields(R)
        self.assertEqual(A["buyer_broker_paid_by"]["impact"], "med")
        self.assertIn("5%", A["listing_fee_pct"]["why"])
        self.assertNotIn("2.5%", A["listing_fee_pct"]["why"])
        self.assertNotIn("national", A["listing_fee_pct"]["why"])

    def test_downside_says_what_it_counts(self):  # OFR-258
        R = review.analyze(fixture("minimal-single.json"))  # no CMA, under list, AS IS: inspection only
        o = R["offers"][0]
        self.assertEqual(review.downside_hits(o), ["inspection"])
        s = review.result(R)["summary"]
        self.assertEqual(next(k for k in s["kpis"] if k["label"] == "Downside Net")["note"], review.downside_note(o, R["listing"]))
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertNotIn("<b>Downside</b>: appraisal at", doc)
        R = review.analyze(fixture("four-offers.json"))  # Lee: over the CMA high, no gap coverage
        self.assertEqual(review.downside_hits(next(o for o in R["offers"] if o["id"] == "D")), ["appraisal", "inspection"])

    def test_title_fee_note_matches_the_net_sheet(self):  # OFR-260
        for name in ("four-offers.json", "counter-chain-standard.json", "expired-aga.json"):
            R = review.analyze(fixture(name))
            note = next(n for n in R["listing"]["cost_notes"] if n.startswith("Title company fees"))
            for o in R["active"] + R["incomplete"]:
                fee = -next(v for k, _, v in o["ns"]["lines"] if k == "settle")
                self.assertIn(review.money(fee), note, name)

    def test_counter_money_and_buyer_changes(self):  # OFR-261
        data = fixture("counter-chain-standard.json")
        o = data["offers"][0]
        o["balance_to_close"] = 128500  # left at the $610,000 original: 24,000 + 457,500 + 128,500
        o["prior_counters"].insert(0, {"by": "buyer", "note": "Original offer", "price": 610000, "closing_date": "2026-10-27"})
        R = review.analyze(data)
        keys = [f.get("topic") for f in R["offers"][0]["flags"]]
        self.assertIn("loan_amount", keys)
        self.assertIn("buyer_changes", keys)
        o["balance_to_close"] = 619500 - 24000 - 457500
        o["prior_counters"][0]["closing_date"] = "2026-11-16"
        keys = [f.get("topic") for f in review.analyze(data)["offers"][0]["flags"]]
        self.assertNotIn("loan_amount", keys)
        self.assertNotIn("buyer_changes", keys)

    def test_estimated_deadline_row_says_likely(self):  # OFR-262
        R = review.analyze(fixture("counter-chain-standard.json"))
        row = R["offers"][0]["counter_rows"][-1]
        self.assertEqual(row[0], "Time for Acceptance")
        self.assertTrue(row[1].startswith("Likely passed ("))
        self.assertIn("likely passed", row[3])

    def test_date_only_expiry_is_end_of_day_and_assumed(self):  # OFR-263
        data = fixture("counter-chain-standard.json")
        data["offers"][0]["expires"] = "2026-09-25"
        R = review.analyze(data)
        self.assertTrue(R["offers"][0]["expires"].endswith("end of day"))
        self.assertEqual(R["offers"][0]["lapsed"], "likely")
        self.assertIn("expires", assumption_fields(R))

    def test_next_step_and_title(self):  # OFR-264, OFR-265
        for name in ("minimal-single.json", "four-offers.json", "expired-aga.json", "counter-chain-standard.json"):
            s = review.result(review.analyze(fixture(name)))["summary"]
            self.assertTrue(s["next_step"][:1].isupper(), name)
        s = review.result(review.analyze(fixture("minimal-single.json")))["summary"]
        self.assertEqual(s["title"], "Counter the $382K FHA Offer")

    def test_preliminary_names_the_offers(self):  # OFR-266 (OFR-306: a ranking-deciding input, not the form)
        data = fixture("four-offers.json")
        for o in data["offers"][1:]:
            o.pop("seller_concessions", None)
        R = review.analyze(data)
        text = review.preliminary(R, R["ranked"][0]["id"], multi=True)
        top = R["ranked"][0]
        self.assertIn(f"seller concessions ({top['label']}", text)
        self.assertNotIn("Morales", text)  # its concessions were given


class EvalIteration4(unittest.TestCase):
    """Fixes from eval iteration 4 (OFR-272 to OFR-282)."""

    def test_quick_answer_names_every_estimated_cost(self):  # OFR-272
        out = review.result(review.analyze(fixture("minimal-single.json")))
        est = " ".join(out["estimated_costs"])
        for word in ("commission", "documentary stamp", "owner's title", "title company fees", "tax proration at 1.8%"):
            self.assertIn(word, est)
        given = review.result(review.analyze(fixture("four-offers.json")), mode="multi")["estimated_costs"]
        self.assertFalse([e for e in given if e.startswith(("commission", "tax proration at", "tax proration on"))])  # given
        # OFR-313: a November closing with no word on this year's bill still says it's assumed unpaid
        self.assertIn("tax proration with this year's bill assumed unpaid", given)

    def test_assumed_inspection_period_is_confirmed_not_countered(self):  # OFR-273
        R = review.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        self.assertNotIn("Inspection Period", [r[0] for r in o["counter_rows"]])
        self.assertEqual(o["counter_terms"]["inspection_days"], o["inspection_days"])
        f = next(f for f in o["flags"] if f.get("topic") == "inspection_period")
        self.assertEqual(f["sev"], "Low")
        data = fixture("minimal-single.json")
        data["offers"][0]["inspection_days"] = 15  # given: still countered
        self.assertIn("Inspection Period", [r[0] for r in review.analyze(data)["offers"][0]["counter_rows"]])

    def test_deal_risks_lead_and_the_flood_reminder_goes_last(self):  # OFR-274
        out = review.result(review.analyze(fixture("minimal-single.json")))
        o = out["offers"][0]
        self.assertEqual(o["flag_keys"][-1], "flood_disclosure")
        self.assertNotIn("flood", (o["biggest_risk"] or "").lower())
        lee = next(x for x in review.result(review.analyze(fixture("four-offers.json")), mode="multi")["offers"]
                   if x["id"] == "D")
        self.assertEqual(lee["flag_keys"][0], "sale_contingency")
        self.assertTrue(lee["biggest_risk"].startswith("High: Contingent on sale"))
        doc, _, _ = review_render.build_html(review.analyze(fixture("minimal-single.json")), {}, sample=False)
        self.assertIn("flood disclosure given to the buyer", doc)  # on the checklist instead

    def test_counter_restates_loan_and_answers_the_buyers_changes(self):  # OFR-275, OFR-276
        data = fixture("counter-chain-standard.json")
        o = data["offers"][0]
        o.update(balance_to_close=128500)
        o["prior_counters"].insert(0, {"by": "buyer", "note": "Original offer", "price": 610000, "closing_date": "2026-10-27"})
        rows = review.analyze(data)["offers"][0]["counter_rows"]
        terms = [r[0] for r in rows]
        self.assertIn("Loan Amount and Balance to Close", terms)
        self.assertIn("Closing Date", terms)
        self.assertEqual(terms[-1], "Time for Acceptance")
        close = next(r for r in rows if r[0] == "Closing Date")
        self.assertIn("accept", close[2])

    def test_national_title_fees_are_an_estimate_in_the_assumptions(self):  # OFR-277, owner rule: never on the line
        out = review.result(review.analyze(fixture("texas-single.json")))
        labels = [r["label"] for r in out["offers"][0]["net_sheet"]["rows"]]
        self.assertIn("Title Company Fees", labels)
        self.assertIn("title_fees", {a["field"] for a in review.listed_assumptions(review.analyze(fixture("texas-single.json")))})
        fl = review.result(review.analyze(fixture("minimal-single.json")))
        self.assertIn("Title Company Fees", [r["label"] for r in fl["offers"][0]["net_sheet"]["rows"]])

    def test_ranking_reason_is_on_the_report(self):  # OFR-279
        data = fixture("four-offers.json")
        data["ranking_reason"] = "Park's conventional 20% down offer closes before the seller's deadline with no sale contingency."
        R = review.analyze(data)
        self.assertEqual(review.multi_view(R)["terms_reason"], data["ranking_reason"])
        doc, _, _ = review_render.build_html(R, {}, sample=False, mode="multi")
        self.assertIn("Terms Reason:", doc)

    def test_year_built_is_asked_with_farbar_riders(self):  # OFR-280
        data = fixture("counter-chain-standard.json")
        self.assertIn("year_built", [a["field"] for a in review.analyze(data)["missing"]])
        data["listing"]["year_built"] = 1995
        self.assertNotIn("year_built", [a["field"] for a in review.analyze(data)["missing"]])
        self.assertNotIn("year_built", [a["field"] for a in review.analyze(fixture("minimal-single.json"))["missing"]])

    def test_rent_back_shows_as_a_term(self):  # OFR-281
        data = fixture("four-offers.json")
        data["offers"][2].update(rent_back_days=30, rent_back_monthly=0)
        doc, _, _ = review_render.build_html(review.analyze(data), {}, sample=False, mode="multi")
        self.assertIn("30-day rent-back (free)", doc)

    def test_backup_waits_for_the_signed_primary(self):  # OFR-282
        why = review.multi_view(review.analyze(fixture("four-offers.json")))["why"]
        if "as backup" in why:
            self.assertIn("after the primary contract is fully signed", why)


def heron_lake_summary():
    """Eval 2 and 4's Heron Lake file: four offers from a summary (no riders read), the seller's Sunday deadline."""
    data = fixture("four-offers.json")
    for o in data["offers"]:
        o.pop("riders", None)
        if o["id"] != "A":
            o.pop("contract_form", None)
    data["offers"][2].update(rent_back_days=30, rent_back_monthly=0)
    return data


class EvalIteration5(unittest.TestCase):
    """Fixes from eval iteration 5 (OFR-287 to OFR-296)."""

    def test_assumed_inspection_and_deposit_are_asked(self):  # OFR-287
        R = review.analyze(fixture("minimal-single.json"))
        fields = [a["field"] for a in review.confirm_items(R)]
        self.assertIn("inspection_days", fields)
        self.assertIn("deposit", fields)
        self.assertEqual([a["field"] for a in review.confirm_items(R)[:4]],
                         [a["field"] for a in R["missing"] if a["impact"] == "high"][:4])  # the high gaps still lead
        data = fixture("minimal-single.json")
        data["offers"][0].update(inspection_days=10, deposit=10000)
        fields = [a["field"] for a in review.confirm_items(review.analyze(data))]
        self.assertNotIn("inspection_days", fields)
        self.assertNotIn("deposit", fields)

    def test_value_range_is_confirmed_in_one_line(self):  # OFR-288
        out = review.result(review.analyze(fixture("four-offers.json")))
        self.assertEqual(out["value_range_confirm"], "Using your CMA's $415,000–$428,000 range.")
        self.assertIsNone(review.result(review.analyze(fixture("minimal-single.json")))["value_range_confirm"])

    def test_every_plan_says_one_at_a_time(self):  # OFR-289
        R = review.analyze(fixture("four-offers.json"))
        s = review.multi_view(R)
        self.assertEqual(s["action"], "ACCEPT")
        self.assertIn("one counter or acceptance goes out at a time", s["plan_note"])

    def test_hoa_rider_check_ignores_rider_bookkeeping(self):  # OFR-291
        plain = heron_lake_summary()
        with_u = heron_lake_summary()
        with_u["offers"][2]["riders"] = ["U"]
        a, b = (review.result(review.analyze(d), mode="multi") for d in (plain, with_u))
        for out in (a, b):
            c = next(o for o in out["offers"] if o["id"] == "C")
            self.assertNotIn("rider_B", c["flag_keys"])
            self.assertIn("riders", [x["field"] for x in review.analyze(plain)["missing"]])
        self.assertEqual([(o["id"], o["score"]) for o in a["offers"]], [(o["id"], o["score"]) for o in b["offers"]])
        C = next(o for o in review.analyze(plain)["offers"] if o["id"] == "C")
        self.assertIn("U", [w[0] for w in C["rider_windows"]])  # the rent-back's agreement window counts without the letter
        read = heron_lake_summary()
        read["offers"][1]["riders"] = []  # the contract has no riders: the HOA rider is missing
        B = next(o for o in review.result(review.analyze(read), mode="multi")["offers"] if o["id"] == "B")
        self.assertIn("rider_B", B["flag_keys"])

    def test_terms_reason_leaves_page_one_when_full(self):  # OFR-292
        data = heron_lake_summary()
        data["ranking_reason"] = "Ranked on terms only: 20% down, full underwriting, a $10,000 gap and an Oct 26 closing."
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            path = review_render.main([self._write(tmp, data), "--out", tmp])[0]
            with open(path, "rb") as f:
                import re
                pages = len(re.findall(rb"/Type\s*/Page[^s]", f.read()))
        self.assertEqual(pages, 2, err.getvalue())
        self.assertNotIn("overflows", err.getvalue())
        msg = review_render.overflow_warning("x.pdf", 1010, 989, [(40.0, "the Terms Reason"), (120.0, "the plan")][::-1])
        self.assertIn("the plan (120px)", msg)
        self.assertNotIn("custom flags", msg)

    @staticmethod
    def _write(tmp, data):
        p = os.path.join(tmp, "listing.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_commission_line_matches_the_net_sheet(self):  # OFR-293
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        R = review.analyze(data)
        est = review.estimated_costs(R, R["offers"])
        self.assertTrue(est[0].startswith("default commission (5% total"), est)  # a default, never "assumed"
        listing = next(lab for k, lab, _ in R["offers"][0]["ns"]["lines"] if k == "listing")
        self.assertIn("5%", listing)

    def test_title_fees_wording_is_the_same_by_county(self):  # OFR-294
        for county in ("Seminole", "Collier"):
            data = fixture("minimal-single.json")
            data["listing"].update(state="FL", county=county)
            R = review.analyze(data)
            self.assertEqual(R["costs"].described("closing_costs.seller_title_fees"), "Florida default", county)

    def test_seller_disclosure_answers_the_lead_paint_check(self):  # OFR-295
        data = fixture("counter-chain-standard.json")
        data["listing"]["built_before_1978"] = False
        R = review.analyze(data)
        self.assertNotIn("year_built", [a["field"] for a in R["missing"]])
        self.assertNotIn("lead_paint", [f.get("topic") for f in R["offers"][0]["flags"]])
        data["listing"]["built_before_1978"] = True
        self.assertIn("lead_paint", [f.get("topic") for f in review.analyze(data)["offers"][0]["flags"]])

    def test_weekend_deadline_and_chart_label(self):  # OFR-296
        R = review.analyze(fixture("four-offers.json"))  # Nov 15, 2026 is a Sunday
        self.assertEqual(review.deadline_note(R["seller"]), "a Sunday: close by Fri Nov 13")
        self.assertIn("close by Fri Nov 13", review.result(R)["deadline_note"])
        data = fixture("four-offers.json")
        data["seller"]["deadline"] = "2026-11-13"
        self.assertIsNone(review.result(review.analyze(data))["deadline_note"])
        # a point label at the left end of the Target line pushes the Target label to the right end
        x, _, anchor = review_render.target_label_spot("Target $149,590 (Clean Offer at List)", 100, 45, 407,
                                                        [(40, 88, 90, 110)])
        self.assertEqual((x, anchor), (407, "end"))
        self.assertEqual(review_render.target_label_spot("Target", 100, 45, 407, [])[2], "start")


class EvalIteration6(unittest.TestCase):
    """Fixes from eval iteration 6 (OFR-299 to OFR-309)."""

    def test_rider_gg_asks_for_the_compensation_agreement(self):  # OFR-299
        R = review.analyze(fixture("expired-aga.json"))  # Rider GG, no amount in the package
        fields = [a["field"] for a in review.confirm_items(R)]
        self.assertIn("compensation_agreement", fields)
        self.assertNotIn("buyer_broker_pct", [a["field"] for a in R["missing"]])  # folded into the one ask
        self.assertTrue(any("signed compensation agreement (the amount)" in t for t in review.to_confirm(R)))
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_pct"] = 0.025  # the amount was given
        self.assertNotIn("compensation_agreement", [a["field"] for a in review.analyze(data)["missing"]])
        self.assertNotIn("compensation_agreement", [a["field"] for a in review.analyze(fixture("four-offers.json"))["missing"]])

    def test_walk_away_rolls_off_a_weekend(self):  # OFR-300
        R = review.analyze(fixture("expired-aga.json"))  # AGA-1 window ends Sun Nov 1
        o = R["offers"][0]
        self.assertEqual(review.firm_day(o, R["costs"]), (review.oe.date(2026, 11, 2), review.oe.date(2026, 11, 1)))
        self.assertTrue(review.result(R)["summary"]["certainty"]["walk_away_until"].startswith("Mon Nov 2"))
        tx = review.analyze(fixture("texas-single.json"))  # no rollover rule for another state's contract: the date stays
        self.assertEqual(review.oe.rolled(review.oe.date(2026, 11, 1), tx["costs"]), (review.oe.date(2026, 11, 1), None))

    def test_downside_names_an_appraisal_risk_that_costs_nothing(self):  # OFR-301
        out = review.result(review.analyze(fixture("expired-aga.json")))  # AGA-1, under list, no CMA
        d = out["offers"][0]
        self.assertEqual((d["downside_counts"], d["downside_checked"]), (["inspection"], ["appraisal", "inspection"]))
        self.assertIn("appraisal", d["downside_note"])
        d = review.result(review.analyze(fixture("texas-single.json")))["offers"][0]
        self.assertEqual(d["downside_checked"], ["appraisal"])

    def test_closing_given_as_days_is_shown_as_written(self):  # OFR-302
        data = fixture("minimal-single.json")
        data["analysis_date"] = "2026-09-26"  # "close in 35 days": about Sat Oct 31, a date the buyer never wrote
        o = review.analyze(data)["offers"][0]
        row = next(r for r in o["counter_rows"] if r[0] == "Closing Date")
        self.assertEqual(row[1], o["close_terms"])
        self.assertTrue(o["close_terms"].startswith("35 days after acceptance"))
        self.assertIsNone(review.analyze(fixture("expired-aga.json"))["offers"][0]["close_terms"])  # a date was given

    def test_tax_estimate_says_list_price(self):  # OFR-303
        R = review.analyze(fixture("minimal-single.json"))
        self.assertIn("of list price", R["listing"]["tax_estimate"])
        est = review.result(R)["estimated_costs"]
        self.assertTrue(any(e.startswith("tax proration at 1.8% of list price") for e in est))

    def test_biggest_risk_agrees_with_the_threat(self):  # OFR-304
        R = review.analyze(fixture("minimal-single.json"))  # only Low flags; FHA financing scores 2
        o = R["offers"][0]
        self.assertEqual(review.threat(o), "Financing")
        self.assertEqual(review.biggest_risk(o)["key"], "threat:financing")
        self.assertEqual(review.result(R)["offers"][0]["biggest_risk_key"], "threat:financing")
        R = review.analyze(fixture("four-offers.json"))
        lee = next(o for o in R["offers"] if o["id"] == "D")  # a High sale contingency outranks the threat
        self.assertEqual(review.biggest_risk(lee)["key"], "sale_contingency")

    def test_respond_by_names_the_offer_the_plan_acts_on(self):  # OFR-305
        R = review.analyze(fixture("four-offers.json"))  # only the declined Morales offer has a time for acceptance
        s = review.result(R)["summary"]
        top = R["ranked"][0]
        self.assertEqual((s["respond_by"], s["respond_by_offer"]), ("No time stated", top["label"]))
        data = fixture("four-offers.json")
        data["offers"][1]["expires"] = "2026-09-26 20:00"  # Park, the offer the plan accepts
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["respond_by_offer"], top["label"])
        self.assertIn("Sep 26", s["respond_by"])

    def test_assumed_form_is_marked_per_offer(self):  # OFR-306
        data = fixture("four-offers.json")
        for o in data["offers"][1:]:
            o.pop("contract_form", None)
        R = review.analyze(data)
        s = review.result(R, "multi")["summary"]
        self.assertIsNone(s["preliminary"])  # the form alone doesn't decide the ranking
        marks = {r["key"]: r["form_assumed"] for r in s["ranked"]}
        self.assertEqual(marks, {"A": False, "B": True, "C": True, "D": True})
        doc, _, _ = review_render.build_html(R, {}, sample=False, mode="multi")
        self.assertNotIn("form assumed", doc)  # said once, in the assumptions table (high impact: listed)
        self.assertIn("Contract form not given", doc)
        self.assertNotIn('class="prelim"', doc)
        top = R["ranked"][0]  # the offer's own review still says it's preliminary
        self.assertTrue(review.result(R, "single", top["id"])["summary"]["preliminary"])

    def test_listing_tax_rate_or_millage(self):  # OFR-307
        data = fixture("texas-single.json")
        data["listing"].pop("annual_tax")
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], round(610000 * 0.011))  # national estimate
        data["listing"]["tax_rate"] = 0.02
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], 12200)
        data["listing"].pop("tax_rate")
        data["listing"]["total_mills"] = 20.464
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], round(610000 * 20.464 / 1000))
        data["listing"]["total_mills"] = 0.020464  # a fraction, not mills
        with self.assertRaises(review.oe.OfferError):
            review.analyze(data)

    def test_hoa_fee_is_an_estimate_unless_known(self):  # OFR-309
        def estoppel(d):
            o = review.analyze(d)["offers"][0]
            return next((lab for k, lab, v in o["ns"]["lines"] if k == "estoppel" and v), None)
        data = fixture("texas-single.json")
        self.assertIsNone(estoppel(data))  # hoa_monthly 0: no HOA, no charge
        data["listing"].pop("hoa_monthly")
        self.assertIsNone(estoppel(data))  # iteration 9 eval 1: an unknown HOA isn't charged "in case"
        data["listing"]["property_type"] = "condo"  # a condo has an association: charged, as an estimate
        self.assertEqual(estoppel(data), "HOA Documents")  # an estimate: said in the assumptions, not on the line
        self.assertTrue(review.analyze(data)["offers"][0]["ns"]["estoppel_estimate"])
        self.assertEqual(estoppel(fixture("expired-aga.json")), "HOA Estoppel Letter")  # an HOA, Florida's built-in fee


class EvalIteration7(unittest.TestCase):
    """Fixes from eval iteration 7 (OFR-311 to OFR-313), on the lapsed AGA-1 offer of eval 6."""

    def test_counter_offers_reports_only_when_the_seller_has_them(self):  # OFR-311
        def why(d):
            rows = review.result(review.analyze(d))["summary"]["revive"]["rows"]
            return next(r["why"] for r in rows if r["term"] == "Inspection Period")
        data = fixture("expired-aga.json")
        self.assertNotIn("4-point", why(data))
        self.assertFalse(review.analyze(data)["listing"]["insurance_reports"])
        data["listing"]["insurance_reports"] = True
        self.assertIn("4-point", why(data))

    def test_aga_window_ending_at_closing_is_flagged(self):  # OFR-312
        o = review.analyze(fixture("expired-aga.json"))["offers"][0]
        self.assertEqual((o["aga_window_full"], o["close_days"]), (36, 37))
        self.assertIn("aga_window_at_closing", [f["topic"] for f in o["flags"]])
        self.assertNotIn("aga_window_past_closing", [f["topic"] for f in o["flags"]])
        data = fixture("expired-aga.json")
        data["offers"][0]["closing_date"] = "2026-11-20"  # 55 days: the window ends well before closing
        o = review.analyze(data)["offers"][0]
        self.assertFalse({"aga_window_at_closing", "aga_window_past_closing"} & {f["topic"] for f in o["flags"]})

    def test_november_proration_says_bill_assumed_unpaid_and_discount(self):  # OFR-313
        data = fixture("expired-aga.json")
        R = review.analyze(data)
        o = R["offers"][0]
        self.assertTrue(o["ns"]["tax_bill_assumed"])
        self.assertEqual(next(lab for k, lab, _ in o["ns"]["lines"] if k == "tax"), "Property Tax Proration (Jan 1 to Closing)")
        self.assertIn("current_tax_bill_paid", {a["field"] for a in review.listed_assumptions(R)})  # said once, there
        out = review.result(R)
        self.assertTrue(any("early-payment discount" in c and "assumed unpaid" in c for c in out["estimated_costs"]))
        self.assertTrue(any("early-payment discount" in n for n in out["cost_notes"]))
        data["listing"]["current_tax_bill_paid"] = False  # known unpaid: no assumption in the label
        self.assertFalse(review.analyze(data)["offers"][0]["ns"]["tax_bill_assumed"])
        data = fixture("expired-aga.json")
        data["offers"][0]["closing_date"] = "2026-10-30"  # before this year's bills go out
        self.assertFalse(review.analyze(data)["offers"][0]["ns"]["tax_bill_assumed"])


class RevisionSource(unittest.TestCase):
    """TL-201 carried to the seller side: "the footer reads" only for a revision read from the footer."""

    def test_footer_quoted_only_when_read_from_it(self):
        data = fixture("minimal-single.json")
        data["offers"][0].update(contract_form="as_is", form_revision="FloridaRealtors/FloridaBar-ASIS-6x Rev. 9/22")
        given = review.result(review.analyze(data))["chat_notes"]
        data["offers"][0]["form_revision_source"] = "footer"
        footer = review.result(review.analyze(data))["chat_notes"]
        self.assertTrue(any("revision given" in n for n in given) and not any("footer reads" in n for n in given))
        self.assertTrue(any("footer reads" in n for n in footer))


class EvalIteration9(unittest.TestCase):
    """Fixes from eval iteration 9 (seller-offer-review)."""

    def test_counter_price_in_the_questions(self):  # eval 7
        data = fixture("counter-chain-standard.json")
        data["offers"][0]["balance_to_close"] = 619500 - 24000 - 457500 - 10000  # adds up to an earlier price
        R = review.analyze(data)
        o = R["offers"][0]
        price = review.money(o["counter_terms"]["price"])
        self.assertNotEqual(o["counter_terms"]["price"], o["price"])
        asks = review_render.questions(o, R)
        self.assertTrue(any("balance to close at the " + price in q for q in asks))
        self.assertFalse(any("$619,500 price" in q for q in asks))
        self.assertTrue(any(f"good for {price}" in q for q in review_render.lender_questions(o, R)))

    def test_assumed_terms_are_listed_once_not_marked(self):  # evals 1, 3, 5; owner rule: said once, in the assumptions
        R = review.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        rows = {r[0]: r[1] for r in review_render.term_rows(o, R)}
        self.assertEqual(rows["Approval"], "Pre-approval letter")
        self.assertNotIn("assumed", json.dumps(list(rows.values())))
        self.assertNotIn("assumed", o["score"]["why"]["approval"])
        self.assertNotIn("assumed", review.walk_away(o, R["costs"])[1])
        listed = {a["field"] for a in review.listed_assumptions(R)}  # the one notes block still names every one
        self.assertTrue({"approval", "inspection_days", "loan_approval_days", "contract_form"} <= listed, listed)
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertNotIn("(assumed)", doc)
        self.assertNotIn("form assumed", doc)

    def test_disclosure_is_never_a_top_risk(self):  # evals 1, 5
        R = review.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        o["flags"] = [{"sev": "Med", "issue": "Seller's flood disclosure not yet given.", "fix": "Give it.",
                       "topic": "flood_disclosure"}]
        self.assertEqual(review.single_view(R, o)["risks"], [])
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("No significant risks found.", doc)

    def test_tax_rate_labeled_by_its_source(self):  # eval 3
        data = fixture("texas-single.json")
        data["listing"].pop("annual_tax")
        data["listing"]["total_mills"] = 20.36
        L = review.analyze(data)["listing"]
        self.assertIn("the adopted rate looked up", L["tax_estimate"])
        self.assertNotIn("listing's", L["tax_estimate"])
        data["listing"]["tax_rate_source"] = "agent"
        self.assertIn("the rate the agent gave", review.analyze(data)["listing"]["tax_estimate"])

    def test_reference_counter_terms_in_the_pdf(self):  # eval 6
        R = review.analyze(fixture("expired-aga.json"))
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("Counter (Reference)", doc)
        self.assertIn("COUNTER (REFERENCE)", doc)
        self.assertIn("Mon Sep 28, 5:00 PM", doc)

    def test_aga_counter_agrees_with_the_flag(self):  # eval 6
        o = review.analyze(fixture("expired-aga.json"))["offers"][0]
        row = next(r for r in o["counter_rows"] if r[0] == "Appraisal Gap Valuation Period")
        self.assertEqual(row[1:3], ("30 days (blank)", "24 days"))
        self.assertEqual(o["counter_terms"]["aga_valuation_days"], 24)
        flag = next(f for f in o["flags"] if f["topic"] == "aga_window_at_closing")
        self.assertIn("24-day", flag["fix"])
        self.assertIsNone(flag["request"])  # the counter asks it

    def test_listing_and_buyer_agent_fees_read_as_separate(self):  # eval 4, owner decision
        data = fixture("texas-single.json")
        R = review.analyze(data)
        a = next(a for a in R["missing"] if a["field"] == "listing_fee_includes_buyer_broker")
        self.assertEqual(a["impact"], "high")
        self.assertIn("5.5% total", a["why"])
        self.assertIn("whether the listing fee includes the buyer's agent", review.result(R)["summary"]["preliminary"])
        data["seller"]["listing_fee_includes_buyer_broker"] = False
        self.assertFalse(any(a["field"] == "listing_fee_includes_buyer_broker" for a in review.analyze(data)["missing"]))

    def test_best_effort_note_for_a_described_offer(self):  # eval 3
        notes = review.result(review.analyze(fixture("texas-single.json")))["chat_notes"]
        self.assertEqual(notes, [review.oe.cf.DESCRIBED_NOTE])
        data = fixture("texas-single.json")
        data["offers"][0]["contract_form"] = "TREC One to Four Family Residential Contract"
        notes = review.result(review.analyze(data))["chat_notes"]
        self.assertEqual(notes, [review.oe.cf.BEST_EFFORT_NOTE])

    def test_hoa_fee_not_charged_when_unknown(self):  # eval 1
        R = review.analyze(fixture("minimal-single.json"))
        self.assertFalse(any(k == "estoppel" and v for k, _, v in R["offers"][0]["ns"]["lines"]))
        self.assertFalse(any("HOA" in c for c in review.result(R)["estimated_costs"]))


class EvalIteration10(unittest.TestCase):
    """Fixes from eval iteration 10."""

    def test_earliest_live_deadline_shows(self):  # evals 2, 4; iteration 11 eval 2: never a declined offer's (OFR-305)
        R = review.analyze(fixture("four-offers.json"))
        a = next(o for o in R["offers"] if o["id"] == "A")
        self.assertEqual(a["action"], "DECLINE")
        for out in (review.result(R), review.result(R, "single", "B")):
            self.assertNotIn("offer_expires", {x["key"] for x in out["summary"]["respond_by_also"]})
        kept = [o for o in R["active"] if o["action"] != "DECLINE" and o is not R["ranked"][0]]
        for o in kept:  # a kept offer that lapses before the pick's deadline still shows
            o["expires_raw"], o["expires"] = "2026-09-24 09:00", "Sep 24, 2026 · 9:00 AM"
        if kept:
            keys = {x["key"] for x in review.respond_also(R, shown=R["ranked"][0])}
            self.assertTrue(keys & {"offer_expires", "backup_lapses"})

    def test_walk_away_stops_at_closing(self):  # eval 1: FHA to a Saturday closing
        data = fixture("minimal-single.json")
        data["analysis_date"] = "2026-09-26"
        R = review.analyze(data)
        c = review.result(R)["summary"]["certainty"]
        self.assertTrue(c["walk_away_until"].startswith("Sat Oct 31"), c["walk_away_until"])
        doc, _, _ = review_render.build_html(R, {}, sample=False)
        self.assertIn("(Oct 31).", doc)
        self.assertNotIn("Nov 2", doc)

    def test_walk_away_note_names_the_window(self):  # eval 2: the rent-back agreement sets the cash offer's date
        data = fixture("four-offers.json")
        data["offers"][2].update(rent_back_days=30, rent_back_monthly=0)
        note = review.result(review.analyze(data), "single", "C")["summary"]["certainty"]["walk_away_note"]
        self.assertIn("rent-back agreement (Rider U)", note)
        self.assertNotIn("loan", note)

    def test_stated_buyer_broker_fee_isnt_assumed(self):  # eval 3
        data = fixture("texas-single.json")  # the agent stated 2.5% to the buyer's agent; the offer doesn't ask
        del data["offers"][0]["buyer_broker_pct"]
        R = review.analyze(data)
        lab = next(lab for k, lab, _ in R["offers"][0]["ns"]["lines"] if k == "bb")
        self.assertNotIn("Assumed", lab)
        self.assertNotIn("buyer_broker_pct", [a["field"] for a in R["missing"] if a["impact"] == "high"])

    def test_described_note_on_render_stderr(self):  # eval 3: one line in both scripts
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            review_render.main([os.path.join(FIXTURES, "texas-single.json"), "--out", tmp])
        self.assertIn(review.oe.cf.DESCRIBED_NOTE, err.getvalue())
        self.assertNotIn(review.oe.cf.BEST_EFFORT_NOTE, err.getvalue())

    def test_deposit_rating_and_score_agree(self):  # eval 3
        R = review.analyze(fixture("texas-single.json"))
        o = R["offers"][0]
        row = next(r for r in review_render.term_rows(o, R) if r[0] == "Escrow Deposit")
        self.assertEqual(row[3], "good")
        self.assertGreaterEqual(o["score"]["scores"]["deposit"], 3)

    def test_assumed_inspection_counters_to_the_benchmark(self):  # eval 1
        R = review.analyze(fixture("minimal-single.json"))
        f = next(f for f in R["offers"][0]["flags"] if f.get("topic") == "inspection_period")
        n = R["listing"]["norms"]["inspection_days"]
        self.assertIn(f"counter to {n} days", f["fix"])
        self.assertNotIn("7–10", f["fix"])

    def test_loan_officer_questions(self):  # evals 1, 6
        data = fixture("minimal-single.json")
        data["analysis_date"] = "2026-09-26"  # closes Sat Oct 31
        R = review.analyze(data)
        qs = review_render.lender_questions(R["offers"][0], R)
        self.assertTrue(any(q.startswith("The offer closes Sat Oct 31") for q in qs))
        self.assertFalse(any("contract" in q for q in qs))
        R = review.analyze(fixture("expired-aga.json"))  # reference counter at $497K, letter capped at $391,200
        q = next(q for q in review_render.lender_questions(R["offers"][0], R) if q.startswith("Is the approval good"))
        self.assertIn("$391,200", q)
        self.assertNotIn("20.0% down", q)

    def test_accept_option_says_the_counter_likely_lapsed(self):  # eval 7
        out = review.result(review.analyze(fixture("counter-chain-standard.json")))
        acc = next(x for x in out["summary"]["options"] if x["option"] == "Accept as Written")
        self.assertEqual(acc["status"], "risk")
        self.assertIn("likely passed", acc["what"])

    def test_gg_between_brokers_asks_the_listing_fee(self):  # eval 6
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        R = review.analyze(data)
        fields = [a["field"] for a in review.confirm_items(R)]
        self.assertNotIn("compensation_agreement", fields)
        self.assertIn("listing_fee_pct", fields)
        gg = next(f for f in R["offers"][0]["flags"] if f.get("topic") == "rider_GG")
        self.assertIsNone(gg.get("request"))

    def test_rider_k_items_are_flags_not_top_risks(self):  # eval 5
        data = fixture("minimal-single.json")
        data["offers"][0].update(financing="conventional", down_pct=0.2, contract_form="standard", riders=["K"])
        R = review.analyze(data)
        self.assertIn("rider_K_terms", [f.get("topic") for f in R["offers"][0]["flags"]])
        self.assertFalse(any("Rider (K)" in r["issue"] for r in review.result(R)["summary"]["risks"]))

    def test_target_tile_names_its_closing(self):  # evals 2, 4
        R = review.analyze(fixture("four-offers.json"))
        k = next(k for k in review.result(R, "single", "C")["summary"]["kpis"] if k["label"] == "Seller's Target Net")
        self.assertIn("closing", k["note"])

    def test_terms_review_shows_loan_and_lender(self):  # eval 6
        data = fixture("expired-aga.json")
        data["offers"][0]["lender"] = "Sample Home Lending"
        R = review.analyze(data)
        rows = {r[0]: r[1] for r in review_render.term_rows(R["offers"][0], R)}
        self.assertIn("$391,200 loan", rows["Financing"])
        self.assertIn("Sample Home Lending", rows["Approval"])


if __name__ == "__main__":
    unittest.main()


class EvalIteration11(unittest.TestCase):
    def test_terms_reason_only_on_the_picks_review(self):
        """Eval 4: the agent's terms reason for the pick printed on every offer's single review."""
        d = fixture("four-offers.json")
        d["ranking_reason"] = "Best net with a strong lender."
        R = review.analyze(d)
        top, other = R["ranked"][0], R["ranked"][1]
        self.assertEqual(review.single_view(R, top)["terms_reason"], "Best net with a strong lender.")
        self.assertIsNone(review.single_view(R, other)["terms_reason"])

    def test_form_assumed_is_marked_apart_from_the_days(self):
        """Eval 2: "7 days (AS IS) (assumed)" read as if the days were assumed: the form shows plain, and the assumed form
        is listed once, in the assumptions."""
        d = fixture("minimal-single.json")
        d["offers"][0]["inspection_days"] = 7
        doc, _, _ = review_render.build_html(review.analyze(d), {}, sample=False)
        self.assertIn("7 days (AS IS)", doc)
        self.assertNotIn("form assumed", doc)
        self.assertIn("Contract form not given: assumed FAR/BAR AS IS", doc)
        self.assertNotIn("7 days (AS IS) (assumed)", doc)
