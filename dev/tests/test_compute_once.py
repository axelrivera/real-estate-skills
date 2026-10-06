"""render.main with compute(): the document model is computed once per run and every format gets the same result;
without it, build gets the data as before (skills not yet migrated)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import render  # noqa: E402


class ComputeOnce(unittest.TestCase):
    def run_main(self, data, formats, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "data.json")
            with open(src, "w") as f:
                json.dump(data, f)
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                return render.main(formats=formats, argv=[src, "--out", os.path.join(tmp, "out")], **kw), quiet.getvalue()

    def test_one_compute_for_every_format(self):
        computed, seen = [], []

        def compute(data, ctx):
            computed.append(ctx["formats"])
            return {"title": data["title"], "figure": 1250}

        def build(result, fmt, out_dir, ctx):
            seen.append((fmt, id(result), result["figure"]))
            return [render.write_text(str(result["figure"]), os.path.join(out_dir, f"x.{fmt}"))]

        written, _ = self.run_main({"title": "Doc"}, ("pdf", "md", "ics"), build=build, compute=compute)
        self.assertEqual(len(computed), 1)
        self.assertEqual(computed[0], ["pdf", "md", "ics"])
        self.assertEqual([f for f, _, _ in seen], ["pdf", "md", "ics"])
        self.assertEqual(len({i for _, i, _ in seen}), 1)  # the same object, not a recomputation
        self.assertEqual(len(written), 3)

    def test_compute_error_stops_the_run_with_its_message(self):
        class BadInput(Exception):
            pass

        def compute(data, ctx):
            raise BadInput("The data needs a price.")

        def build(result, fmt, out_dir, ctx):  # pragma: no cover - never reached
            raise AssertionError("built after a failed compute")

        with self.assertRaises(SystemExit) as e:
            self.run_main({"title": "Doc"}, ("pdf",), build=build, compute=compute, errors=(BadInput,))
        self.assertEqual(str(e.exception), "The data needs a price.")

    def test_without_compute_build_gets_the_data(self):
        got = []

        def build(data, fmt, out_dir, ctx):
            got.append(data)
            return []

        self.run_main({"title": "Doc"}, ("pdf", "md"), build=build)
        self.assertEqual(got, [{"title": "Doc"}, {"title": "Doc"}])


if __name__ == "__main__":
    unittest.main()
