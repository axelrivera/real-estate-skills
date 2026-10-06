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

    def test_filename_length_capped(self):
        name = render.filename("1234 " + "Very Long Street Name " * 8, "Offer From " + "Buyer Name " * 10, "Offer Review", ext="pdf")
        self.assertLessEqual(len(name), render.MAX_NAME + 4)
        self.assertTrue(name.endswith("-Offer-Review.pdf"))
        self.assertTrue(name.startswith("1234-Very-Long"))


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
                render.main(build, ("md", "txt"), [src, "--out", out], on_request=("txt",))  # all skips on-request
                self.assertEqual(calls[-1], "md")
                render.main(build, ("md", "txt"), [src, "--format", "txt", "--out", out], on_request=("txt",))
                self.assertEqual(calls[-1], "txt")
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
            self.assertIn("no deck without Node", str(stop.exception.code))
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

    def test_long_tables_may_break(self):  # a long table runs on across pages; a short one stays whole
        def tbl(rows, cls):
            body = "".join(f"<tr><td>Row {i}</td><td>Value</td></tr>" for i in range(rows))
            return f"<div class='tbl {cls}'><table><thead><tr><th>Item</th><th>Amount</th></tr></thead><tbody>{body}</tbody></table></div>"

        theme = design.theme(None, "buyer")
        doc = render.page(tbl(3, "short") + tbl(40, "long"), theme_css=design.css_vars(theme))
        with tempfile.TemporaryDirectory() as tmp:
            got = render.html_to_pdf(doc, os.path.join(tmp, "t.pdf"), before_print=lambda pg: pg.evaluate(
                "() => [...document.querySelectorAll('.tbl')].map(t => [t.classList.contains('brk'), getComputedStyle(t).breakInside])"))
        self.assertEqual(got, [[False, "avoid"], [True, "auto"]])

class Notices(unittest.TestCase):
    """The agent block needs a brokerage with a name; disclaimers print as written, Equal Housing once."""

    def test_name_without_brokerage_is_refused(self):
        from shared import profiles
        with self.assertRaises(profiles.ProfileError):
            render.check_agent({"name": "Jane Doe", "brokerage": ""})
        render.check_agent({"name": "Jane Doe", "brokerage": "Sunshine Realty"})
        render.check_agent({"name": None, "brokerage": None})  # no agent block at all is fine

    def test_notices_print_disclaimers_verbatim(self):
        agent = {"disclaimers": "Each office independently owned and operated.\n\nEqual Housing Opportunity."}
        html_block = render.notices(agent, ["Sales data: Stellar MLS as of 2026-09-22."])
        self.assertIn("Sales data: Stellar MLS", html_block)
        self.assertIn("Each office independently owned and operated.", html_block)
        self.assertEqual(render.notice_lines(agent, marketing=True).count("Equal Housing Opportunity."), 1)
        self.assertEqual(render.notice_lines({}, marketing=True), ["Equal Housing Opportunity."])
        self.assertEqual(render.notices({}), "")


if __name__ == "__main__":
    unittest.main()
