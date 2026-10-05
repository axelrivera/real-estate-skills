"""Tests for dev/package.py and dev/manual.py."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import manual  # noqa: E402
import package  # noqa: E402

STATUS = """# Status

## Done

| Area | What |

## This pass (2026-10-02): Something New and Version 0.13.0

- New thing.

## This pass (2026-09-30): Dev Tooling (No Version Bump)

- Tooling.

## This pass (2026-09-29): Fixes and Version 0.12.0

- Fix A.

## This pass (2026-09-29): Contracts and Version 0.11.0

- Contracts.

## This pass (2026-09-26): Trend Line and Version 0.10.2

- Old.

## Open items

- Later.
"""


def git(root, *args):
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)


class Tracked(unittest.TestCase):
    def test_untracked_and_ignored_files_never_ship(self):
        """Archives come from git ls-files, not the file system."""
        with tempfile.TemporaryDirectory() as tmp:
            files = {".claude-plugin/plugin.json": "{}", "LICENSE": "MIT", "skills/a/SKILL.md": "x",
                     "skills/a/scripts/run.py": "", "skills/a/notes-untracked.md": "draft",
                     "skills/a/scripts/__pycache__/run.cpython-312.pyc": "", "skills/a/.DS_Store": ""}
            for path, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(tmp, path)) or tmp, exist_ok=True)
                with open(os.path.join(tmp, path), "w") as f:
                    f.write(text)
            git(tmp, "init", "-q")
            git(tmp, "add", ".claude-plugin/plugin.json", "LICENSE", "skills/a/SKILL.md", "skills/a/scripts/run.py")
            expected = [".claude-plugin/plugin.json", "LICENSE", "skills/a/SKILL.md", "skills/a/scripts/run.py"]
            self.assertEqual(package.tracked(package.PLUGIN_FILES, tmp), expected)
            dest = package.build_plugin(os.path.join(tmp, "dist", "p.plugin"), tmp)
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(sorted(z.namelist()), expected)
            dest = package.zip_dir(os.path.join(tmp, "skills", "a"), os.path.join(tmp, "dist", "a.zip"), "a", tmp)
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(sorted(z.namelist()), ["a/SKILL.md", "a/scripts/run.py"])

    def test_plugin_holds_exactly_the_tracked_plugin_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = package.build_plugin(os.path.join(tmp, "x.plugin"))
            with zipfile.ZipFile(dest) as z:
                names = sorted(z.namelist())
        self.assertEqual(names, package.tracked(package.PLUGIN_FILES))
        self.assertIn(".claude-plugin/plugin.json", names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".DS_Store")])


class Skills(unittest.TestCase):
    def test_stale_skill_zips_are_removed(self):
        """A removed skill's zip (market-profile.zip) must not survive a rebuild."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "skills"))
            open(os.path.join(tmp, "skills", "market-profile.zip"), "w").close()
            with mock.patch.object(package, "DIST", tmp), contextlib.redirect_stdout(io.StringIO()):
                package.package_skills()
            zips = sorted(os.listdir(os.path.join(tmp, "skills")))
            self.assertEqual(os.listdir(os.path.join(tmp, "dev")), ["runtime-check.zip"])
        skills = sorted(d for d in os.listdir(os.path.join(package.ROOT, "skills"))
                        if os.path.isfile(os.path.join(package.ROOT, "skills", d, "SKILL.md")))
        self.assertEqual(zips, [f"{s}.zip" for s in skills])


class Notes(unittest.TestCase):
    def test_sections_since_the_last_release(self):
        """Notes come from status.md; an unreleased version ships with the next one."""
        notes = package.release_notes(STATUS, "0.12.0", "0.10.2")
        self.assertEqual([line for line in notes.splitlines() if line.startswith("## ")],
                         ["## Fixes and Version 0.12.0", "## Contracts and Version 0.11.0"])
        self.assertIn("- Fix A.", notes)
        self.assertNotIn("Old.", notes)
        self.assertNotIn("New thing.", notes)
        self.assertNotIn("Tooling.", notes)
        self.assertEqual(package.release_notes(STATUS, "0.12.0", "0.11.0").count("## "), 1)

    def test_no_section_for_the_version(self):
        self.assertIsNone(package.release_notes(STATUS, "0.14.0", "0.13.0"))


class Guide(unittest.TestCase):
    def test_guide_names_every_file_in_the_zip(self):
        """The guide lists the four files the release zip holds, and ships without manual-only lines."""
        text = package.guide_text("9.9.9", "real-estate-9.9.9.plugin")
        for name in ("real-estate-9.9.9.plugin", "README.md", os.path.basename(manual.PDF), "LICENSE"):
            self.assertIn(f"`{name}`", text)
        self.assertIn("holds four files", text)
        self.assertNotIn("<!--", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("\n\n\n", text)

    def test_manual_is_up_to_date(self):
        """The committed PDF matches the guide, its images and the styles (make manual)."""
        self.assertIsNone(manual.stale())
        with open(manual.GUIDE, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(manual.missing_images(text), [])
        self.assertGreater(len(manual.figures(text)), 20)


class Markdown(unittest.TestCase):
    def test_lists_keep_figures_and_nested_items(self):
        md = ("1. First.\n\n   <!-- figure: images/a.png | Cap A. -->\n   <!-- figure: images/b.png | Cap B. -->\n\n"
              "2. Second:\n   - Nested **bold**.\n\nAfter `code`.\n")
        out = manual.blocks(md.splitlines())
        self.assertEqual(out.count("<ol>"), 1)
        self.assertIn('<div class="figures n2">', out)
        self.assertLess(out.index("figures"), out.index("Second"))
        self.assertIn("<ul><li>Nested <strong>bold</strong>.</li></ul>", out)
        self.assertTrue(out.endswith("<p>After <code>code</code>.</p>"))

    def test_table_and_strip(self):
        out = manual.blocks(["| Field | Used For |", "|---|---|", "| Zip | **Required.** Location |"])
        self.assertIn("<th>Field</th>", out)
        self.assertIn("<td><strong>Required.</strong> Location</td>", out)
        self.assertNotIn("---", out)
        text = "Intro.\n\n   <!-- figure: images/a.png | Cap. -->\n\nNext.\n"
        self.assertEqual(manual.strip_figures(text), "Intro.\n\nNext.\n")


if __name__ == "__main__":
    unittest.main()
