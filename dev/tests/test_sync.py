import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sync_shared as s  # noqa: E402


class Sync(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "shared", "markets"))
        for rel, text in (("__init__.py", ""), ("design.py", "X = 1\n"), ("markets/fl.md", "---\n---\n")):
            with open(os.path.join(self.root, "shared", rel), "w") as f:
                f.write(text)
        os.makedirs(os.path.join(self.root, "shared", "__pycache__"))
        self.with_scripts = os.path.join(self.root, "plugins", "core", "skills", "a", "scripts")
        self.without = os.path.join(self.root, "plugins", "core", "skills", "b")
        os.makedirs(self.with_scripts)
        os.makedirs(self.without)
        self.dest = os.path.join(self.with_scripts, "_shared")

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_sync(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ok = s.sync(self.root, check)
        return ok, out.getvalue()

    def test_copies_only_into_skills_with_scripts(self):
        self.assertTrue(self.run_sync()[0])
        self.assertEqual(s.source_files(self.dest), {"__init__.py", "design.py", "markets/fl.md"})
        self.assertFalse(os.path.exists(os.path.join(self.without, "scripts")))
        self.assertEqual(self.run_sync(check=True), (True, ""))

    def test_check_reports_each_kind_of_drift(self):
        ok, out = self.run_sync(check=True)
        self.assertFalse(ok)
        self.assertIn("missing", out)
        self.run_sync()
        with open(os.path.join(self.dest, "design.py"), "w") as f:
            f.write("X = 2\n")
        with open(os.path.join(self.dest, "stray.py"), "w") as f:
            f.write("")
        os.remove(os.path.join(self.dest, "markets", "fl.md"))
        ok, out = self.run_sync(check=True)
        self.assertFalse(ok)
        for word in ("edited design.py", "extra stray.py", "missing markets/fl.md"):
            self.assertIn(word, out)
        self.run_sync()
        self.assertTrue(self.run_sync(check=True)[0])


if __name__ == "__main__":
    unittest.main()
