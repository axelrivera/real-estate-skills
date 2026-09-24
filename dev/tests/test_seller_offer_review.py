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
        self.assertEqual((out["mode"], s["action"], s["offer"]), ("single", "COUNTER", "A"))
        self.assertIn("**Preliminary", s["preliminary"])
        self.assertEqual(s["kpis"][1]["value"], "$349,817")
        self.assertEqual([r["counter"] for r in s["counter"]["rows"]], ["$386,000", "7 days"])
        self.assertEqual(out["value_range"], "not provided")
        self.assertTrue(out["to_confirm"])
        self.assertEqual(out["offers"][0]["net_sheet"]["columns"], ["As Offered", "Downside", "Counter"])

    def test_multi_plan(self):
        out = review.result(review.analyze(fixture("four-offers.json")))
        s = out["summary"]
        self.assertEqual(s["headline"], "ACCEPT OFFER B")  # the seller wants certainty: B (86) isn't risked for a 0.7% gain
        self.assertEqual([(p["offer"], p["action"]) for p in s["plan"]],
                         [("B", "Accept"), ("C", "Hold as backup"), ("A", "Decline"), ("D", "Decline")])
        self.assertIn("nothing is declined until the seller approves", s["plan_note"])
        data = fixture("four-offers.json")
        data["seller"]["priority"] = "balanced"
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["headline"], "COUNTER OFFER B")
        self.assertIn("Only one counter goes out at a time", s["plan_note"])
        self.assertIsNone(s["preliminary"])

    def test_single_report_in_multi_context(self):
        R = review.analyze(fixture("four-offers.json"))
        out = review.result(R, mode="single", offer_id="A")
        self.assertEqual(out["summary"]["action"], "DECLINE")
        self.assertEqual(out["summary"]["compare"]["vs"], "B")
        with self.assertRaises(review.oe.OfferError):
            review.result(review.analyze(fixture("minimal-single.json")), mode="multi")

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
        self.assertIn("ACCEPT OFFER B", doc)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Seller Side", doc)
        self.assertIn("SAMPLE DATA", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)  # no license in the profile: nothing printed
        self.assertNotIn("#C2410C", doc)  # the default orange isn't hard-coded anywhere

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
            self.assertEqual([os.path.basename(p) for p in paths], ["1207-Palmetto-Way-Offer-A-Review.pdf"])
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")


if __name__ == "__main__":
    unittest.main()
