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
        for rel, text in (("__init__.py", ""), ("design.py", "X = 1\n"), ("markets/fl.md", "---\n---\n"),
                          ("profiles.py", "from . import design\n"), ("mls.py", "Y = 1\n")):
            with open(os.path.join(self.root, "shared", rel), "w") as f:
                f.write(text)
        os.makedirs(os.path.join(self.root, "shared", "__pycache__"))
        self.with_scripts = os.path.join(self.root, "skills", "a", "scripts")
        self.without = os.path.join(self.root, "skills", "b")
        os.makedirs(self.with_scripts)
        os.makedirs(self.without)
        with open(os.path.join(self.with_scripts, "check.py"), "w") as f:
            f.write("from _shared import profiles  # noqa\n")
        self.dest = os.path.join(self.with_scripts, "_shared")

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_sync(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ok = s.sync(self.root, check)
        return ok, out.getvalue()

    def test_copies_only_into_skills_with_scripts(self):
        """DOC-11: only what the skill's scripts import (profiles), what that imports (design) and its data (markets)."""
        self.assertTrue(self.run_sync()[0])
        self.assertEqual(s.source_files(self.dest), {"__init__.py", "profiles.py", "design.py", "markets/fl.md"})
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
        with open(os.path.join(self.with_scripts, "check.py"), "w") as f:  # a new import is a missing file
            f.write("from _shared import mls, profiles  # noqa\n")
        ok, out = self.run_sync(check=True)
        self.assertIn("missing mls.py", out)

    def test_references_go_only_to_skills_that_point_to_them(self):
        os.makedirs(os.path.join(self.root, "shared", "references"))
        with open(os.path.join(self.root, "shared", "references", "rules.md"), "w") as f:
            f.write("# Rules\n")
        with open(os.path.join(self.without, "SKILL.md"), "w") as f:
            f.write("Read `references/rules.md` first.\n")
        with open(os.path.join(os.path.dirname(self.with_scripts), "SKILL.md"), "w") as f:
            f.write("No shared references.\n")
        self.run_sync()
        copy = os.path.join(self.without, "references", "rules.md")
        self.assertTrue(os.path.exists(copy))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.with_scripts), "references")))
        self.assertNotIn("references/rules.md", s.source_files(self.dest))  # not copied as code
        with open(copy, "w") as f:
            f.write("edited\n")
        ok, out = self.run_sync(check=True)
        self.assertFalse(ok)
        self.assertIn("references/rules.md: edited", out)


    def test_staged_copies_must_match(self):
        """DOC-8: the hook compares what's staged, so staging shared/ without its copies is refused."""
        import subprocess
        git = lambda *a: subprocess.run(["git", *a], cwd=self.root, capture_output=True, check=True)  # noqa: E731
        git("init", "-q")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        self.run_sync()
        git("add", "-A")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(s.check_staged(self.root))
        with open(os.path.join(self.root, "shared", "design.py"), "w") as f:
            f.write("X = 3\n")
        self.run_sync()  # the working tree is in sync...
        git("add", "shared/design.py")  # ...but only shared/ is staged
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(s.check_staged(self.root))
        self.assertIn("_shared/design.py", out.getvalue())


class SkillPaths(unittest.TestCase):
    def test_no_sandbox_paths_in_skills(self):
        """CORE-21: skills say "the outputs folder" and let the runtime decide; no /mnt paths."""
        root = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("_shared", "__pycache__")]
            for name in files:
                if name.endswith(".md"):
                    with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                        self.assertNotIn("/mnt/", f.read(), os.path.join(dirpath, name))


if __name__ == "__main__":
    unittest.main()
