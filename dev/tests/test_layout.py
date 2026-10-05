"""Rendered layout: every fixture of every PDF skill prints with no page-1 overflow, nothing clipped and no near-empty
page (dev/layout_check.py, also `make layout-check`), and the clip detector in shared/render.py fires when content is
cut off. Needs Chromium (make setup) and pdftotext (poppler); skipped without them. About ten seconds."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "dev"))
from shared import cma, render  # noqa: E402
import layout_check  # noqa: E402


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


HAVE_TOOLS = bool(shutil.which("pdftotext")) and have_chromium()
NEEDS = unittest.skipUnless(HAVE_TOOLS, "needs Chromium (make setup) and pdftotext")


def print_html(body, css=""):
    """Print a page and return what html_to_pdf reported on stderr."""
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        render.html_to_pdf(render.page(body, css=css), os.path.join(tmp, "t.pdf"))
    return err.getvalue()


@NEEDS
class ClipDetector(unittest.TestCase):
    def test_forced_narrow_table_is_reported(self):
        rows = "".join(f"<tr><td>Row {i}</td><td class='n'>$1,234,567</td><td class='n'>Very Long Column Value {i}</td></tr>"
                       for i in range(3))
        err = print_html(f"<div class='tbl' style='width:180px'><table><thead><tr><th>Scenario With A Long Header</th>"
                         f"<th>Another Long Header</th><th>Third</th></tr></thead><tbody>{rows}</tbody></table></div>",
                         css="th{white-space:nowrap}")
        self.assertIn("Check: t.pdf: clipped: div.tbl", err)
        self.assertIn("Scenario With A Long Header", err)

    def test_ellipsis_is_reported(self):
        err = print_html("<div style='width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                         "A brokerage name far too long for its box</div>")
        self.assertIn("clipped", err)

    def test_text_wider_than_the_page(self):
        err = print_html("<p style='white-space:nowrap'>" + "Unbreakable-" * 30 + "</p>")
        self.assertIn("runs past the page's right edge", err)

    def test_long_one_line_piece_wraps_instead(self):
        """RELEASE_NOWRAP: a header piece kept on one line that would push the page wider wraps, so nothing is cut."""
        err = print_html("<header><div class='t1'>Report</div><div class='prep'><span style='white-space:nowrap'>"
                         + "Prepared for a very long trust name " * 8 + "</span></div></header>")
        self.assertNotIn("clipped", err)

    def test_fitting_content_is_quiet(self):
        err = print_html("<div class='tbl'><table><thead><tr><th>Item</th><th class='n'>Amount</th></tr></thead>"
                         "<tbody><tr><td>Title</td><td class='n'>$1,200</td></tr></tbody></table></div>"
                         "<div style='overflow:hidden;height:4px'></div>")  # an empty clipped box (a meter) is fine
        self.assertNotIn("clipped", err)
        self.assertNotIn("right edge", err)


class NearEmptyRule(unittest.TestCase):
    def test_rule(self):
        full = (0.9, "x")
        self.assertEqual(layout_check.page_problems([full, full, full], "r.pdf"), [])
        self.assertEqual(len(layout_check.page_problems([full, (0.34, "a"), full], "r.pdf")), 1)
        self.assertEqual(len(layout_check.page_problems([full, full, (0.1, "tail")], "r.pdf")), 1)
        self.assertEqual(len(layout_check.page_problems([full, (0.1, "tail")], "r.pdf")), 1)  # page 2 of 2 too
        self.assertEqual(layout_check.page_problems([full, (0.34, "a"), full], "r.pdf", allow={2}), [])
        self.assertEqual(layout_check.page_problems([(0.2, "one page")], "r.pdf"), [])  # page 1 is never near-empty

    def test_allow_list_is_documented(self):
        for key, why in layout_check.ALLOW.items():
            self.assertEqual(len(key), 3, key)
            self.assertTrue(str(why).strip(), f"{key}: give the reason")


@NEEDS
class EveryFixture(unittest.TestCase):
    """dev/layout_check.py over every fixture: no overflow or clip warning, no near-empty page."""

    def test_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = layout_check.run(out_root=tmp)
        self.assertTrue(results)
        for skill in layout_check.SKILLS:
            self.assertTrue(any(r[0].startswith(skill + "/") for r in results), f"no fixture rendered for {skill}")
            self.assertTrue(any(r[0].startswith(skill + "/stress-") for r in results), f"no stress fixture for {skill}")
        problems = [p for _, _, ps in results for p in ps]
        self.assertEqual(problems, [], "\n".join(problems))
        known = {r[0] for r in results}
        self.assertEqual([k for k in layout_check.ALLOW if k[0] not in known], [], "ALLOW entry with no fixture")


class PageFillMargins(unittest.TestCase):
    @unittest.skipUnless(HAVE_TOOLS, "needs Chromium and pdftotext")
    def test_default_and_landscape_margins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.pdf")
            render.html_to_pdf(render.page("<p>Top line</p><div style='height:500px'></div><p>Lower line</p>"), path)
            fill = cma.page_fill(path, 0.3, 0.4)[0][0]
            self.assertAlmostEqual(fill, 540 / 989, delta=0.05)
            render.html_to_pdf(render.page("<p>Top line</p><div style='height:300px'></div><p>Lower line</p>",
                                           css="@page{size:Letter landscape}"), path,
                               landscape=True)
            fill = cma.page_fill(path, 0.3, 0.4)[0][0]
            self.assertAlmostEqual(fill, 340 / 749, delta=0.06)


if __name__ == "__main__":
    unittest.main()
