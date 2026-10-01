"""Every fixture's computed facts match its snapshot in dev/golden/ (dev/golden.py). A failure lists the fields that
moved; when the change is intended, run `make golden` and explain the diff in the commit."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import golden  # noqa: E402


class Golden(unittest.TestCase):
    def test_snapshots_match(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = golden.main([])
        self.assertEqual(code, 0, "Computed results moved (run `make golden` if intended):\n" + out.getvalue())

    def test_facts_drop_prose_and_keep_numbers(self):
        f = golden.facts({"label": "Inspection Period", "when": "2026-10-05 23:59", "key": "inspection",
                          "amount": 1234.567, "notes": ["One sentence.", "Another one."], "ok": True})
        self.assertEqual(f, {"when": "2026-10-05 23:59", "key": "inspection", "amount": 1234.57,
                             "notes": {"count": 2}, "ok": True})


if __name__ == "__main__":
    unittest.main()
