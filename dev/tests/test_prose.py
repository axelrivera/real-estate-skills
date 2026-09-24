import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import prose, render  # noqa: E402


def flagged(text):
    return [why for _, why in prose.issues(text)]


class Phrases(unittest.TestCase):
    def test_red_flags(self):
        for text in ("Perfect for a growing family", "ideal for young professionals", "a kid-friendly street",
                     "quiet, safe neighborhood", "low-crime area", "great schools nearby", "A-rated schools",
                     "an up-and-coming neighborhood", "adults only", "no children", "Christian family",
                     "Hispanic neighborhood", "no wheelchairs", "English-speaking buyers"):
            self.assertTrue(flagged(text), text)

    def test_allowed_wording(self):
        """HUD's advertising guidance allows describing the property, its rooms and the area's physical facts."""
        for text in ("Family room off the kitchen", "walk-in closet", "master bedroom", "walking distance to the park",
                     "55+ community", "a white home with blue shutters", "single-family homes", "Flood Zone X",
                     "exclusive right of sale", "buyer must be able to close by Oct 3", "a good area rug",
                     "no pets", "school millage 5.249", "cul-de-sac lot, fenced yard"):
            self.assertEqual(flagged(text), [], text)

    def test_em_dash_and_paths(self):
        data = {"summary": "Priced right\u2014for now", "export": "a\u2014b.csv",
                "rows": [["Sep 2", "\u2014"], ["\u2014 / \u2014"]]}  # lone em dashes are empty values: fine
        found = prose.issues(data)
        self.assertEqual([p for p, _ in found], ["$.summary"])
        with self.assertRaises(prose.ProseError) as e:
            prose.check(data)
        self.assertIn("$.summary", str(e.exception))


class RenderStops(unittest.TestCase):
    def test_nothing_is_built(self):
        built = []
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "data.json")
            with open(src, "w") as f:
                json.dump({"findings": ["Great for young families"]}, f)
            with self.assertRaises(SystemExit) as e:
                render.main(lambda *a: built.append(a) or [], ("pdf",), [src, "--out", tmp])
        self.assertIn("$.findings[0]", str(e.exception.code))
        self.assertEqual(built, [])


if __name__ == "__main__":
    unittest.main()
