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

        def build(data, fmt, out_dir, ctx):
            self.assertEqual(ctx["agent"]["errors"], ["name", "brokerage"])  # no --agent: empty profile
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

    def test_extra_args_and_partial_success(self):
        class BadInput(Exception):
            pass

        seen = {}

        def build(data, fmt, out_dir, ctx):
            seen.update(ctx)
            if fmt == "b":
                raise BadInput("no deck without Node")
            return [render.write_text("x", os.path.join(out_dir, f"doc.{fmt}"))]

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "data.json")
            with open(src, "w") as f:
                json.dump({}, f)
            out, quiet = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(quiet):
                with self.assertRaises(SystemExit) as stop:
                    render.main(build, ("a", "b"), [src, "--out", tmp, "--mode", "multi"], errors=(BadInput,),
                                extra_args=lambda ap: ap.add_argument("--mode"))
            self.assertEqual(seen["mode"], "multi")
            self.assertEqual(seen["formats"], ["a", "b"])
            self.assertIn("doc.a", out.getvalue())  # the file that worked is still listed
            self.assertIn("The b file wasn't built: no deck without Node", str(stop.exception.code))
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
                render.main(build, ("a", "b"), [src, "--out", tmp, "--format", "b"], errors=(BadInput,))
            self.assertEqual(stop.exception.code, "no deck without Node")


class Pdf(unittest.TestCase):
    def test_html_to_pdf(self):
        theme = design.theme(None, "seller")
        doc = render.page("<header><div class='t1'>Hello</div></header>", theme_css=design.css_vars(theme))
        self.assertIn("--brand-rule", doc)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.pdf")
            h = render.html_to_pdf(doc, path, footer_html=render.footer("Test"),
                                   before_print=lambda pg: pg.evaluate("document.querySelector('.t1').offsetHeight"))
            self.assertGreater(h, 0)
            with open(path, "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")


if __name__ == "__main__":
    unittest.main()
