"""Tests for plugins/transactions/skills/seller-offer-review/scripts."""
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
        out = review.result(review.analyze(fixture("minimal-single.json")))
        s = out["summary"]
        self.assertEqual((out["mode"], s["action"], s["offer_label"]), ("single", "COUNTER", "$382K FHA"))
        self.assertIn("**Preliminary", s["preliminary"])
        self.assertEqual(s["kpis"][1]["value"], "$349,817")
        self.assertEqual([r["counter"] for r in s["counter"]["rows"]], ["$386,000", "7 days"])
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
        self.assertEqual((s["headline"], s["offer_label"]), ("ACCEPT", "Park · Coldwell Banker"))
        self.assertEqual([(p["offer"], p["action"]) for p in s["ranked"]],
                         [("Park · Coldwell Banker", "Accept"), ("Díaz · eXp Realty", "Hold as Backup"),
                          ("Morales · Keller Williams", "Decline"), ("Lee · Independent", "Decline")])
        self.assertTrue(s["why"].startswith("The Park (Coldwell Banker) offer has the best net"))
        self.assertNotIn("Offer B", json.dumps(s))
        self.assertIn("nothing is declined until the seller approves", s["plan_note"])
        data = fixture("four-offers.json")
        data["seller"]["priority"] = "balanced"
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["headline"], "COUNTER")
        self.assertIn("Only one counter goes out at a time", s["plan_note"])
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
        self.assertIn("Offer from Whitfield · Compass", doc)
        self.assertIn('<div class="big">COUNTER</div><div class="who">Whitfield · Compass</div>', doc)
        self.assertIn('<b>Sep 24, 2026 · 9:00 PM</b><span class="rbo">Whitfield · Compass</span>', doc)
        self.assertIn("<td>Buyer / Agent</td>", doc)  # the buyer's name appears once, as contract identification

    def test_incomplete_contract_gets_no_recommendation(self):
        out = review.result(review.analyze(fixture("incomplete-single.json")))
        s = out["summary"]
        self.assertEqual((s["action"], s["headline"], s["counter"], s["options"]), ("INCOMPLETE", "CONTRACT INCOMPLETE", None, []))
        self.assertEqual([f["sev"] for f in s["fixes"]], ["Blocking", "High", "High", "High"])
        self.assertNotIn("recommended", json.dumps(s).replace("no recommendation", ""))
        issues = [f["issue"] for f in review.analyze(fixture("incomplete-single.json"))["offers"][0]["flags"]]
        self.assertIn("FHA financing without an FHA/VA rider.", issues)
        self.assertTrue(any("lead-based paint" in i for i in issues))
        self.assertTrue(any("Loan amount $318,000" in i for i in issues))

    def test_incomplete_offer_is_listed_but_not_ranked(self):
        data = fixture("four-offers.json")
        data["offers"][2]["contract_issues"] = [{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for the complete contract."}]
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual([(r["rank"], r["offer"], r["action"]) for r in s["ranked"]][-1], ("—", "Díaz · eXp Realty", "Incomplete"))
        self.assertEqual(s["offers_active"], 4)
        self.assertIn("can't be reviewed until the contract is corrected, so it isn't ranked.", s["why"])
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

    def test_texas_is_preliminary_without_florida_values(self):
        out = review.result(review.analyze(fixture("texas-single.json")))
        self.assertIn("transfer tax", out["summary"]["preliminary"])
        self.assertNotIn("Florida", json.dumps(out))


class Pdf(unittest.TestCase):
    def test_html_uses_seller_theme_and_profile(self):
        R = review.analyze(fixture("two-offers-accept.json"))
        doc, mode, o = review_render.build_html(R, AGENT, sample=True)
        self.assertEqual((mode, o), ("multi", None))
        self.assertIn('<div class="big">ACCEPT</div><div class="who">$512K Conventional</div>', doc)
        self.assertIn('<span><b>B</b> $512K Conventional</span>', doc)  # letters only with their key
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
        self.assertIn("8 · Questions for the Loan Officer", doc)
        self.assertIn("on an FHA loan?", doc)
        self.assertIn('<span class="cb"></span></td><td>Loan officer called', doc)
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
        self.assertIn("Prepared for <b>Seller</b> · September 23, 2026</div>", doc)  # no agent lines without a profile
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


if __name__ == "__main__":
    unittest.main()


class AuditPlanWording(unittest.TestCase):
    """OFR-6, OFR-21: no backup request while the primary is open; disclosure needs the seller's authorization."""

    def test_backup_only_after_primary_is_signed(self):
        out = review.result(review.analyze(fixture("escalation.json")))
        text = json.dumps(out)
        self.assertIn("once that contract is fully signed", out["summary"]["next_step"] if "next_step" in out["summary"] else text)
        self.assertNotIn("request a backup contract", text)
        self.assertIn("written authorization", text)
