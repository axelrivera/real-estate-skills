import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import design, render  # noqa: E402


class Filenames(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(render.filename("517 Hickorywood Dr", "Buyer CMA", ext="pdf"), "517-Hickorywood-Dr-Buyer-CMA.pdf")
        self.assertEqual(render.filename("12 Peña Ct, #4", "Timeline", ext=".md"), "12-Pena-Ct-4-Timeline.md")
        self.assertEqual(render.filename("", None, ext="pdf"), "output.pdf")


class OutputDir(unittest.TestCase):
    def test_precedence(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with mock.patch.dict(os.environ, {"OUTPUT_DIR": b}):
                self.assertEqual(render.output_dir(a), os.path.abspath(a))
                self.assertEqual(render.output_dir(), os.path.abspath(b))

    def test_creates_missing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "x", "y")
            self.assertEqual(render.output_dir(target), target)
            self.assertTrue(os.path.isdir(target))

    def test_falls_back_to_cwd_without_sandbox(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("os.path.isdir", return_value=False):
            self.assertEqual(render.output_dir(), os.getcwd())


class Main(unittest.TestCase):
    def test_contract(self):
        calls = []

        def build(data, fmt, out_dir):
            calls.append(fmt)
            return [render.write_text(data["title"], os.path.join(out_dir, render.filename(data["title"], ext=fmt)))]

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "data.json")
            with open(src, "w") as f:
                json.dump({"title": "Test Doc"}, f)
            out = os.path.join(tmp, "out")
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                written = render.main(build, ("md", "txt"), [src, "--out", out])
                self.assertEqual(calls, ["md", "txt"])
                self.assertEqual([os.path.basename(p) for p in written], ["Test-Doc.md", "Test-Doc.txt"])
                render.main(build, ("md", "txt"), [src, "--format", "md", "--out", out])
                self.assertEqual(calls[-1], "md")
                with self.assertRaises(SystemExit):
                    render.main(build, ("md",), [src, "--format", "pdf"])
            self.assertIn("Test-Doc.md", quiet.getvalue())


class Pdf(unittest.TestCase):
    def test_html_to_pdf(self):
        theme = design.theme(None, "seller")
        html = render.page("<h1 style='color:var(--brand-strong)'>Hello</h1>", theme_css=design.css_vars(theme))
        with tempfile.TemporaryDirectory() as tmp:
            path = render.html_to_pdf(html, os.path.join(tmp, "t.pdf"),
                                      before_print=lambda pg: pg.evaluate("document.title = 'x'"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")


if __name__ == "__main__":
    unittest.main()
