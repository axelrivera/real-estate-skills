"""seller-cma report PDF: brand colors, page 1 from the document model, the chat checks render.py prints, and one PDF
build. Page fit for every fixture is test_layout's; any input's is test_generated_seller_cma's."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_seller_cma import AGENT, profiles, report, reprice, run, seller_render  # noqa: E402


def html(R, agent=AGENT):
    C, _ = run(R)
    return seller_render.build_html(C, agent), C


def page_one(doc):
    return doc.split('<div class="pb">')[0]


class Brand(unittest.TestCase):
    def test_colors_and_agent_fields(self):
        doc, _ = html(report())
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("License", doc)
        self.assertIn("--subject:var(--text)", doc)  # the subject home is black: one brand hue, no second color
        self.assertIn("font-bundled", doc)
        self.assertNotIn("tag prelim", doc)
        bare = html(report(), profiles.load_agent(None))[0]
        self.assertIn("--brand:#C2410C", bare)  # default seller orange
        self.assertIn("no profile", seller_render.profile_check(profiles.load_agent(None)))
        self.assertIn("profile incomplete", seller_render.profile_check({**AGENT, "brokerage": None}))
        self.assertIsNone(seller_render.profile_check(AGENT))


class PageOne(unittest.TestCase):
    def test_nets_on_the_reply_basis(self):
        """Page 1 and the pricing table show the after-holding nets the reply compares; the net sheet's total row alone
        shows the net before holding costs."""
        R = reprice()
        R["costs"]["mortgage_payoff"] = 210000
        doc, C = html(R)
        self.assertEqual(C["net_basis"], "after_holding")
        ri = C["recommended_index"]
        self.assertEqual(C["recommended_net_display"], C["strategies"][ri]["net_after_holding_display"])
        one = page_one(doc)
        for x in C["strategies"]:
            self.assertIn(x["net_after_holding_display"], one)
            self.assertNotIn(x["net_display"], one)
        self.assertIn(C["options_summary"]["net_tile"], one)
        self.assertIn(C["summary"]["launch_line"], one)
        for h, line in C["summary"]["first_steps"]:
            self.assertIn(h, one)


class Build(unittest.TestCase):
    def test_pdf_only(self):
        """The PDF build hands the agent the PDF alone: no JSON beside it."""
        C, _ = run(report())
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(C, "pdf", tmp, {"agent": profiles.load_agent(None), "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(paths, [paths[0]])
            self.assertFalse([f for f in os.listdir(tmp) if f.endswith(".json")])


if __name__ == "__main__":
    unittest.main()
