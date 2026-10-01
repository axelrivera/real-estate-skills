"""Tests for dev/py311_check.py (REL-105)."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import py311_check as c  # noqa: E402

PEP701 = 'names = ["a"]\nprint(f"{", ".join(names)}")\n'  # 3.12+ only: the same quote inside the braces


class Py311(unittest.TestCase):
    def test_finds_only_a_real_311(self):
        """A python3.11 that isn't 3.11 is refused; without uv or python3.11 there is none."""
        with mock.patch.object(c.shutil, "which", return_value=None):
            self.assertIsNone(c.find_py311())
        with mock.patch.object(c.shutil, "which", side_effect=lambda n: sys.executable if n == "python3.11" else None):
            if sys.version_info[:2] != (3, 11):
                self.assertIsNone(c.find_py311())

    def test_grammar_fallback_catches_pep701(self):
        if sys.version_info < (3, 12):
            self.skipTest("the tokenizer only reports f-string parts on 3.12+")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(PEP701)
        try:
            self.assertTrue(c.fstring_problems(f.name))
        finally:
            os.remove(f.name)

    def test_real_311_rejects_pep701(self):
        py311 = c.find_py311()
        if not py311:
            self.skipTest("no Python 3.11 (make setup installs one with uv)")
        r = subprocess.run([py311, "-c", f"compile({PEP701!r}, 'x.py', 'exec')"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SyntaxError", r.stderr)


if __name__ == "__main__":
    unittest.main()
