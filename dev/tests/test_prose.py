import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import offer_engine, prose, render  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


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

    def test_phrase_table(self):
        """Audit 2026-09-23 FH-1, FH-2: (text, flagged?). Pointers to an official source pass; claims never do."""
        table = [
            # FH-1: fair-housing.md's own redirect wording must render.
            ("School ratings are available from the district.", False),
            ("For school ratings, check with the school board.", False),
            ("Check the crime rate at the sheriff's site.", False),
            ("Crime statistics are published by the police department.", False),
            ("The assigned school is Lakeview Elementary; verify it with the district.", False),
            # The same topics with no official source, and claims even with one, stay flagged.
            ("School ratings are high here.", True),
            ("Low crime rate.", True),
            ("Great schools, per the district.", True),
            ("Low-crime area according to police.", True),
            ("The district says it's a safe neighborhood.", True),
            # A pointer in one sentence doesn't excuse a claim in the next.
            ("Crime data is on the sheriff's site. School ratings are excellent.", True),
            # FH-2: loan type stands for terms, never for the buyer.
            ("VA: strong buyer profile", True),
            ("VA buyers need not apply", True),
            ("VA financing: Tidewater notice before a low appraisal is final", False),
            ("FHA, 3.5% down: appraisal protection to closing", False),
        ]
        for text, bad in table:
            self.assertEqual(bool(flagged(text)), bad, text)

    def test_offer_reasons_describe_terms(self):
        """FH-2: the engine's own score reasons pass the check for every loan type."""
        with open(os.path.join(FIXTURES, "seller-offer-review", "four-offers.json")) as f:
            base = json.load(f)
        for fin in ("cash", "conventional", "fha", "va", "usda"):
            data = json.loads(json.dumps(base))
            for o in data["offers"]:
                o["financing"] = fin
                o.pop("down_pct", None)
            R = offer_engine.analyze(data)
            self.assertEqual(prose.issues(R), [], fin)
            reasons = " ".join(o["score"]["why"]["financing"] for o in R["offers"])
            self.assertNotIn("profile", reasons)
            self.assertNotIn("cushion", reasons)

    def test_em_dash_and_paths(self):
        data = {"summary": "Priced right\u2014for now", "export": "a\u2014b.csv",
                "rows": [["Sep 2", "\u2014"], ["\u2014 / \u2014"]]}  # lone em dashes are empty values: fine
        found = prose.issues(data)
        self.assertEqual([p for p, _ in found], ["$.summary"])
        with self.assertRaises(prose.ProseError) as e:
            prose.check(data)
        self.assertIn("$.summary", str(e.exception))


class PlaceNamesAndAllowList(unittest.TestCase):
    """FH-3: proper names don't block a render; the allow list needs a reason and is reported."""

    def test_place_keys_skipped(self):
        data = {"subject": {"address": "12 Christian Way", "subdivision": "Great Schools Estates", "city": "Safe Harbor",
                            "school": "Top-Rated Academy"},
                "comps": [{"address": "4 Hispanic Neighborhood Rd", "mls_address": "4 Hispanic Neighborhood Rd"}]}
        self.assertEqual(prose.issues(data), [])
        data["summary"] = "Great schools nearby."  # prose is still checked
        self.assertEqual([p for p, _ in prose.issues(data)], ["$.summary"])

    def test_allow_list(self):
        data = {"amenities": ["Asian Community Center, 0.3 miles", "Asian neighborhood"]}
        self.assertTrue(prose.issues(data))
        data["fair_housing_allow"] = [{"phrase": "Asian Community Center",
                                       "reason": "name of the community center 0.3 miles away"}]
        found = prose.issues(data)
        self.assertEqual([p for p, _ in found], ["$.amenities[1]"])  # only the exact proper name is excused
        data["amenities"].pop()
        self.assertEqual(prose.check(data), [("Asian Community Center", "name of the community center 0.3 miles away")])

    def test_allow_entry_needs_reason(self):
        with self.assertRaises(prose.ProseError) as e:
            prose.check({"fair_housing_allow": [{"phrase": "Asian Community Center"}]})
        self.assertIn("$.fair_housing_allow[0]", str(e.exception))


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

    def test_allow_list_is_logged(self):
        import contextlib
        import io
        built, err = [], io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "data.json")
            with open(src, "w") as f:
                json.dump({"findings": ["0.3 miles to the Asian Community Center"],
                           "fair_housing_allow": [{"phrase": "Asian Community Center", "reason": "a place name"}]}, f)
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                render.main(lambda *a: built.append(a) or [], ("pdf",), [src, "--out", tmp])
        self.assertEqual(len(built), 1)
        self.assertIn('Fair-housing allow list: "Asian Community Center" (a place name)', err.getvalue())


if __name__ == "__main__":
    unittest.main()
