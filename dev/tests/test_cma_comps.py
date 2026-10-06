"""shared/cma.py comp rules: the supported range width, time adjustments and the adjustment summary (buyer-cma and
seller-cma share them)."""
import os
import random
import statistics
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402
from test_seller_cma import card, compute, run, stops, tanager  # noqa: E402

cma, finance = compute.cma, compute.finance




class RangeWidth(unittest.TestCase):
    """The range is about 6% of the median wide at most, never narrower than half that, ends rounded to $5,000."""

    def test_bounds_and_width(self):
        values = [384000, 385200, 386825, 387500, 395100]
        fl = {"cma.range_width_pct": 0.06}
        self.assertEqual(cma.range_bounds(values, fl), (375000, 400000, 20000))
        self.assertEqual(cma.range_bounds(values, None), (375000, 400000, 20000))  # 6% where none is built in
        spread = [431000, 452000, 466000, 478800, 496000]  # comps that disagree: the second-highest still caps the top
        self.assertEqual(cma.range_bounds(spread, fl)[1], 480000)
        self.assertEqual(cma.range_width(440000)["target"], 25000)  # $26,400 cap: $25,000 at $440,000
        w = cma.range_width(386800)
        self.assertEqual((round(w["cap"]), w["target"]), (23208, 20000))

    def test_warnings(self):
        values = [384000, 385200, 386825, 387500, 395100]
        fl = {"cma.range_width_pct": 0.06}
        keys = lambda low, high, v=values, f=fl: [k for k, _ in cma.range_warnings({"low": low, "high": high}, v, f)]
        self.assertEqual(keys(380000, 400000), [])
        self.assertEqual(keys(380000, 395000), [])
        self.assertEqual(keys(385000, 390000), ["range_narrow"])
        self.assertEqual(keys(365000, 410000), ["range_wide", "range_one_comp", "range_one_comp"])
        self.assertEqual(keys(375000, 400000), ["range_wide"])  # $25,000 is past the cap
        self.assertEqual(keys(435000, 445000, [438000, 440000, 441000, 442000], None), ["range_narrow"])
        self.assertEqual(keys(430000, 445000, [438000, 440000, 441000, 442000], None), [])
        for values, width in (([431500, 437800, 441625, 445500, 451750], 25000),
                              ([380200, 384000, 386800, 387500, 400100], 20000)):
            lo, hi = cma.passing_range(values, None)  # every warning names a range that passes
            self.assertEqual(cma.range_warnings({"low": lo, "high": hi}, values, None), [])
            self.assertEqual(hi - lo, width)


class RangeRule(unittest.TestCase):
    """The range is the script's, by one rule, for any comps (generated): the same comps give the same range; it is
    the normal width, ends on $5,000, centered on the median within a rounding step unless pulled in, and it passes
    every range check."""

    def test_rule_properties(self):
        rng = random.Random(11)
        for _ in range(400):
            base = rng.uniform(150_000, 2_500_000)
            values = [round(base * rng.uniform(0.85, 1.15)) for _ in range(rng.randint(3, 8))]
            market = {"cma.range_width_pct": rng.choice((0.05, 0.06, 0.08))} if rng.random() < 0.5 else None
            lo, hi = cma.choose_range(values, market)
            self.assertEqual((lo, hi), cma.choose_range(list(reversed(values)), market))  # order never matters
            median = statistics.median(values)
            low_ok, high_ok, target = cma.range_bounds(values, market)
            self.assertEqual(hi - lo, target)
            self.assertEqual((lo % cma.RANGE_STEP, hi % cma.RANGE_STEP), (0, 0))
            self.assertTrue(low_ok <= lo and hi <= high_ok, (values, lo, hi))
            if low_ok < lo and hi < high_ok:  # not pulled in: centered within half a step
                self.assertLessEqual(abs((lo + hi) / 2 - median), cma.RANGE_STEP / 2)
            self.assertEqual(cma.range_warnings({"low": lo, "high": hi}, values, market), [])

    def test_half_up_never_banker(self):
        """A median exactly between two $5,000 steps rounds up, the same way every time ($445,000 at $25,000 wide)."""
        self.assertEqual(cma.choose_range([430000, 440000, 445000, 450000, 460000], None), (435000, 460000))

    def test_override(self):
        values = [431500, 437800, 441625, 445500, 451750]
        rule = cma.choose_range(values, None)
        got, errors = cma.resolve_range(values, None, None)
        self.assertEqual(((got["low"], got["high"]), got["override"], errors), (rule, False, []))
        got, errors = cma.resolve_range(values, None, {"low": 425000, "high": 450000, "reason": "The agent's call."})
        self.assertEqual((got["low"], got["high"], got["override"], got["rule_low"], errors),
                         (425000, 450000, True, rule[0], []))
        for bad in ({"low": 450000, "high": 425000, "reason": "x"}, {"low": 425000, "high": 450000},
                    {"low": "425000", "high": 450000, "reason": "x"}, [425000, 450000]):
            got, errors = cma.resolve_range(values, None, bad)
            self.assertTrue(errors, bad)
            self.assertEqual((got["low"], got["high"]), rule)  # an override that fails never sets the range


class ConditionLadder(unittest.TestCase):
    """Condition is one level per home; the script adjusts each comp by the levels' difference, for any levels."""
    VALUES = {"original": 0, "cosmetic": 5000, "baths_only": 10000, "kitchen_only": 15000, "kitchen_and_baths": 25000,
              "full_renovation": 45000, "new": 50000}

    def comps(self, levels, **extra):
        return {"cards": [{"address": f"{i} A St", "sold_price": 400000, "seller_concessions": 0, "condition": lv,
                           "adjustments": [{"label": "Size", "amount": 1000}]} for i, lv in enumerate(levels)], **extra}

    def test_amount_is_the_difference(self):
        market = compute.profiles.load_market(state="FL", county="Seminole")
        self.assertEqual(cma.condition_values(market), self.VALUES)  # the market file's ladder, in ladder order
        rng = random.Random(3)
        for _ in range(200):
            mine = rng.choice(cma.CONDITION_LEVELS)
            comps = self.comps([rng.choice(cma.CONDITION_LEVELS) for _ in range(rng.randint(3, 6))])
            errors, info = cma.apply_condition_adjustments(comps, {"condition": mine}, market)
            self.assertEqual(errors, [])
            self.assertEqual(info["subject"], mine)
            for c in comps["cards"]:
                cond = [a for a in c["adjustments"] if a.get("kind") == "condition"]
                diff = self.VALUES[mine] - self.VALUES[c["condition"]]
                self.assertEqual([a["amount"] for a in cond], [diff] if diff else [])
                self.assertEqual(c["adjustments"][-1], {"label": "Size", "amount": 1000})  # typed lines kept
            again = cma.apply_condition_adjustments(comps, {"condition": mine}, market)  # never doubles up
            self.assertEqual(again[0], [])
            self.assertEqual(sum(a.get("kind") == "condition" for c in comps["cards"] for a in c["adjustments"]),
                             sum(c["condition"] != mine and self.VALUES[c["condition"]] != self.VALUES[mine]
                                 for c in comps["cards"]))

    def test_typed_condition_and_missing_levels_stop(self):
        market = compute.profiles.load_market(state="FL", county="Seminole")
        for label, kind in (("Renovation", None), ("Updated Kitchen", "other"), ("Primary Bath", "age"),
                            ("Partial Update vs. Full Renovation", None), ("Dated Finishes", "lot")):
            comps = self.comps(["original", "full_renovation", "kitchen_only"])
            comps["cards"][1]["adjustments"].append({"label": label, "amount": 15000, **({"kind": kind} if kind else {})})
            errors, _ = cma.apply_condition_adjustments(comps, {"condition": "kitchen_only"}, market)
            self.assertEqual(len(errors), 1, label)
            self.assertIn("cards[1].adjustments[1]", errors[0])
        for label in ("Older Roof", "New Windows", "Larger Corner Lot", "Pool"):  # not condition: kept as typed
            comps = self.comps(["original"])
            comps["cards"][0]["adjustments"].append({"label": label, "amount": 5000})
            self.assertEqual(cma.apply_condition_adjustments(comps, {"condition": "original"}, market)[0], [])
        errors, _ = cma.apply_condition_adjustments(self.comps(["original", None, "renovated"]), {}, market)
        self.assertEqual(len(errors), 3)  # the home's level and both comps' bad levels, all at once

    def test_values_outside_the_built_in_market(self):
        texas = compute.profiles.load_market(state="TX", county="Travis")
        errors, _ = cma.apply_condition_adjustments(self.comps(["original", "full_renovation"]),
                                                    {"condition": "kitchen_only"}, texas)
        self.assertIn("comps.condition_values", errors[0])
        same = self.comps(["kitchen_only", "kitchen_only"])  # every comp at the home's level: nothing to price
        self.assertEqual(cma.apply_condition_adjustments(same, {"condition": "kitchen_only"}, texas)[0], [])
        given = self.comps(["original", "full_renovation"], condition_values={"original": 0, "kitchen_only": 20000,
                                                                             "full_renovation": 60000})
        errors, info = cma.apply_condition_adjustments(given, {"condition": "kitchen_only"}, texas)
        self.assertEqual(errors, [])
        self.assertEqual([a["amount"] for c in given["cards"] for a in c["adjustments"] if a.get("kind") == "condition"],
                         [20000, -40000])
        upside = self.comps(["original"], condition_values={"original": 0, "kitchen_only": 30000, "full_renovation": 20000})
        self.assertTrue(cma.apply_condition_adjustments(upside, {"condition": "kitchen_only"}, texas)[0])

    def test_method_line_names_the_homes_level(self):
        market = compute.profiles.load_market(state="FL", county="Seminole")
        comps = self.comps(["original", "full_renovation"])
        _, info = cma.apply_condition_adjustments(comps, {"condition": "kitchen_only"}, market)
        text = cma.adjustment_summary(comps["cards"], None, None, info)
        self.assertIn("condition and updates ($15,000 to $30,000, against this home's updated kitchen)", text)


class TimeAdjustments(unittest.TestCase):
    """Time adjustments are the script's, from the stated rate and cutoff (the market split by default)."""

    def time_line(self, C, address):
        return [v for a, v in card(C, address)["lines"] if a == cma.TIME_LABEL]

    def test_rule_per_comp(self):
        C, _ = run(tanager())
        self.assertEqual(self.time_line(C, "907 Tanager Ridge Dr"), ["−$7,100"])  # June 12 to Sep 26 at 1.5% a quarter
        self.assertEqual(self.time_line(C, "655 Phoebe Ln"), [])  # July 18: after the July 1 split, none
        self.assertEqual((C["time_adjustment"]["rate_display"], C["time_adjustment"]["cutoff_display"]), ("1.5%", "July"))
        R = tanager()
        c = next(x for x in R["comps"]["cards"] if x["address"] == "907 Tanager Ridge Dr")
        c["address"] = "1 Nowhere Ln"
        self.assertIn("time_undated", run(R)[0]["warning_keys"])

    def test_typed_amounts(self):
        R = tanager()  # a typed amount that agrees is kept as the script's
        cards = {c["address"]: c for c in R["comps"]["cards"]}
        cards["907 Tanager Ridge Dr"]["adjustments"].append({"label": "Earlier Sale", "amount": -7000})
        self.assertEqual([v for a, v in card(run(R)[0], "907 Tanager Ridge Dr")["lines"] if a == "Earlier Sale"], ["−$7,100"])
        R = tanager()  # a sale after the cutoff gets none
        next(c for c in R["comps"]["cards"] if c["address"] == "655 Phoebe Ln")["adjustments"].append(
            {"label": "Older Sale", "amount": -4300})
        stops(self, R, r"comps\.cards\[3\]\.adjustments\[2\]: .*−\$4,300")
        R = tanager()  # typed without a stated rule
        R["comps"].pop("time_adjustment")
        next(c for c in R["comps"]["cards"] if c["address"] == "907 Tanager Ridge Dr")["adjustments"].append(
            {"label": "Market Since the Sale", "amount": -7100})
        stops(self, R, r"−\$7,100.*comps\.time_adjustment")

    def test_hand_typed_amount_is_checked(self):
        cards = [{"address": "1 A St", "sold_price": 490000, "seller_concessions": 0, "close_date": "2026-08-19",
                  "adjustments": [{"label": "Market Since the Sale", "amount": -4000}]}]
        errors, _ = cma.apply_time_adjustments({"cards": cards, "time_adjustment": {"rate_per_quarter": 0.01,
                                                                                     "cutoff": "2026-09-01"}},
                                               [], "2026-09-23", None)
        self.assertEqual(len(errors), 1)
        self.assertIn("−$1,900", errors[0])  # 35 days at 1% a quarter on $490,000


class Formats(unittest.TestCase):
    def test_summaries(self):
        cards = [{"adjustments": [{"label": "Primary Bath", "amount": -10000}, {"label": "Size", "amount": -1100}],
                  "seller_concessions": 0},
                 {"adjustments": [{"label": "Roof Age", "amount": 5000}], "seller_concessions": 6500}]
        text = cma.adjustment_summary(cards)
        at = [text.index(s) for s in ("$10,000", "$1,100", "$5,000")]
        self.assertEqual(at, sorted(at))
        self.assertEqual(text.count("$"), 3)
        self.assertEqual(finance.tax_pair(7152), (7200, 600))  # "$7,200/yr" beside "$600/mo"


if __name__ == "__main__":
    unittest.main()
