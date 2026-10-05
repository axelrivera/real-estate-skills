"""choices.pick: a missing category takes the default, a typed one is normalized, an unknown one is one problem."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import choices  # noqa: E402

ALLOWED = ("draw_offers", "market", "premium")


class Pick(unittest.TestCase):
    def test_missing_takes_the_default(self):
        for v in (None, "", "  "):
            self.assertEqual(choices.pick(v, ALLOWED, "f", default="market"), ("market", []))

    def test_typed_forms_normalize(self):
        for v in ("draw_offers", "Draw offers", "draw-offers", " DRAW_OFFERS "):
            self.assertEqual(choices.pick(v, ALLOWED, "f"), ("draw_offers", []))

    def test_unknown_is_one_problem_naming_every_choice(self):
        value, problems = choices.pick("aggressive", ALLOWED, "pricing.stance", default="market")
        self.assertEqual(value, "market")
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("pricing.stance:"))
        for a in ALLOWED:
            self.assertIn(a, problems[0])

    def test_integer_choices(self):
        self.assertEqual(choices.pick(2, (0, 1, 2, 3), "f"), (2, []))
        for bad in (5, "2", True, 1.5):
            self.assertEqual(len(choices.pick(bad, (0, 1, 2, 3), "f", default=1)[1]), 1, bad)


if __name__ == "__main__":
    unittest.main()
