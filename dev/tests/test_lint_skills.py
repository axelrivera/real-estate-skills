"""Tests for dev/lint_skills.py (DOC-9)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lint_skills as ls  # noqa: E402


def skill(tmp, name, text, files=()):
    d = os.path.join(tmp, name)
    os.makedirs(os.path.join(d, "references"))
    for f in files:
        open(os.path.join(d, f), "w").close()
    with open(os.path.join(d, "SKILL.md"), "w") as f:
        f.write(text)
    return os.path.join(d, "SKILL.md")


class Lint(unittest.TestCase):
    def test_every_shipped_skill_passes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ls.main(), 0)

    def test_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = skill(tmp, "buyer-cma", "---\nname: buyer-cma\ndescription: Does a thing.\n---\n\nIntro.\n\n## Guardrails\n\n"
                       "Read `references/method.md`.\n", ["references/method.md"])
            self.assertEqual(ls.lint(ok), [])
            colon = skill(tmp, "a", "---\nname: a\ndescription: Builds an offer: the strongest one.\n---\n")
            self.assertIn("isn't valid YAML", ls.lint(colon)[0])
            bad = skill(tmp, "seller-cma-pdf", "---\nname: seller-cma-pdf\ndescription: x\n---\n\n## Steps\n\nSee `references/nope.md`.\n")
            text = " ".join(ls.lint(bad))
            for word in ("output format", "Guardrails", "references/nope.md"):
                self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
