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


def T_texas_without_rates():
    """A Texas report with none of the agent's rates: the national ones fill them."""
    from test_seller_cma import report, texas
    R = texas(report())
    for k in ("condition_values", "lot_values", "systems_value"):
        R["comps"].pop(k, None)
    return R




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
    """Time adjustments are the script's: the rate by method.md's rule from the export (or the agent's override), the
    cutoff the market split."""

    def time_line(self, C, address):
        return [v for a, v in card(C, address)["lines"] if a == cma.TIME_LABEL]

    def test_rule_per_comp(self):
        C, _ = run(tanager())  # sale-to-original-list fell more than 3 points across the July 1 split: 2% a quarter
        self.assertEqual((C["time_adjustment"]["rate_display"], C["time_adjustment"]["cutoff_display"]), ("2%", "July"))
        self.assertEqual(self.time_line(C, "907 Tanager Ridge Dr"), ["−$9,400"])  # June 12 to Sep 26 at 2% a quarter
        self.assertEqual(self.time_line(C, "655 Phoebe Ln"), [])  # July 18: after the July 1 split, none
        R = tanager()
        c = next(x for x in R["comps"]["cards"] if x["address"] == "907 Tanager Ridge Dr")
        c["address"] = "1 Nowhere Ln"
        self.assertIn("time_undated", run(R)[0]["warning_keys"])

    def test_agents_rate_is_shown_as_theirs(self):
        R = tanager()
        R["comps"]["time_override"] = {"rate_per_quarter": 0.015, "reason": "The agent reads a gentler softening."}
        C, _ = run(R)
        self.assertEqual(self.time_line(C, "907 Tanager Ridge Dr"), ["−$7,100"])  # June 12 to Sep 26 at 1.5% a quarter
        self.assertIn("gentler softening", C["comps"]["settled"])
        R["comps"]["time_override"] = {"rate_per_quarter": 0.015}  # no reason
        stops(self, R, r"comps\.time_override")

    def test_typed_amounts(self):
        R = tanager()  # a typed amount that agrees is kept as the script's
        cards = {c["address"]: c for c in R["comps"]["cards"]}
        cards["907 Tanager Ridge Dr"]["adjustments"].append({"label": "Earlier Sale", "amount": -9300})
        self.assertEqual([v for a, v in card(run(R)[0], "907 Tanager Ridge Dr")["lines"] if a == "Earlier Sale"], ["−$9,400"])
        R = tanager()  # a sale after the cutoff gets none
        next(c for c in R["comps"]["cards"] if c["address"] == "655 Phoebe Ln")["adjustments"].append(
            {"label": "Older Sale", "amount": -4300})
        stops(self, R, r"comps\.cards\[3\]\.adjustments\[\d\]: .*−\$4,300")
        R = tanager()  # typed when the agent set no shift
        R["comps"]["time_override"] = {"rate_per_quarter": 0, "reason": "The agent reads the market as flat."}
        next(c for c in R["comps"]["cards"] if c["address"] == "907 Tanager Ridge Dr")["adjustments"].append(
            {"label": "Market Since the Sale", "amount": -7100})
        stops(self, R, r"−\$7,100.*comps\.time_override")
        R = tanager()  # the old typed method is retired
        R["comps"]["time_adjustment"] = {"rate_per_quarter": 0.015}
        stops(self, R, r"comps\.time_adjustment: no longer written by you")

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


class Outliers(unittest.TestCase):
    def test_warning_only_when_no_backup_is_left(self):
        """Eval 16: outliers replaced in different orders gave different medians; the script now sets them aside
        itself (select_comps). What's still flagged after it, with no backup left, is warned; a kept card isn't."""
        cards = [{"address": a, "adjusted": v} for a, v in
                 (("1 A St", 470000), ("2 B St", 521300), ("3 C St", 425000), ("4 D St", 484500), ("5 E St", 461600))]
        out = compute.cma.outlier_warnings(cards)
        self.assertEqual([w.split(":")[0] for w in out], ["2 B St", "3 C St"])
        self.assertTrue(all("backup" in w and "keep_reason" in w for w in out))
        cards[1]["keep_reason"] = "The agent's call."
        self.assertEqual([w.split(":")[0] for w in compute.cma.outlier_warnings(cards)], ["3 C St"])


class SplitAndRate(unittest.TestCase):
    """The market split and the shift rate are the script's, by one rule: the same export always splits the same way."""

    def test_split_is_the_first_of_the_month_two_months_back(self):
        d = compute.mls.rule_split
        for end, want in (("2026-09-26", "2026-07-01"), ("2026-09-01", "2026-07-01"), ("2026-01-15", "2025-11-01"),
                          ("2026-02-28", "2025-12-01"), ("2026-12-31", "2026-10-01")):
            with self.subTest(end=end):
                self.assertEqual(d(cma._iso(end)).isoformat(), want)
        self.assertEqual(cma.default_split({"as_of": "2026-09-26"}).isoformat(), "2026-07-01")
        self.assertEqual(cma.default_split({"as_of": "2026-09-26", "split_override": {"date": "2026-06-15", "reason": "x"}})
                         .isoformat(), "2026-06-15")
        self.assertTrue(cma.split_errors({"split_override": {"date": "2026-06-15"}}))  # no reason
        self.assertEqual(cma.split_errors({}), [])

    def test_rate_by_the_ratio_change(self):
        def st(a, b, n=6):
            return {"sold_early": {"n": n, "median_sale_to_original_list": a},
                    "sold_recent": {"n": n, "median_sale_to_original_list": b}}
        for a, b, want in ((0.98, 0.975, None), (0.98, 0.965, (0.01, "falling")), (0.98, 0.95, (0.01, "falling")),
                           (0.98, 0.9499, (0.02, "falling")), (0.95, 0.97, (0.01, "rising")), (0.95, 0.99, (0.02, "rising"))):
            with self.subTest(a=a, b=b):
                spec, info = cma.time_rule(st(a, b))
                self.assertEqual((spec["rate_per_quarter"], spec["prices"]) if spec else None, want)
                self.assertEqual(info["basis"], "rule")
        spec, info = cma.time_rule(st(0.98, 0.90, n=4))  # too few sales on a side
        self.assertEqual((spec, info["basis"]), (None, "thin"))
        spec, info = cma.time_rule(st(0.98, 0.90), {"rate_per_quarter": 0.005, "reason": "Our read."})
        self.assertEqual((spec["rate_per_quarter"], info["basis"]), (0.005, "agent"))


class SelectComps(unittest.TestCase):
    """The used comps by one rule: the first five in the ranking, an outlier set aside for the next backup."""

    @staticmethod
    def cards(*values):
        return [{"address": f"{i} A St", "adjusted": v} for i, v in enumerate(values, 1)]

    def test_outlier_replaced_by_the_next_backup(self):
        comps = {"cards": self.cards(470000, 521300, 465000, 484500, 461600, 472000, 468000)}
        info = cma.select_comps(comps)
        self.assertEqual([c["address"] for c in comps["cards"]], ["1 A St", "3 A St", "4 A St", "5 A St", "6 A St"])
        self.assertEqual([(x["address"], x["above"], x["replaced"]) for x in info["set_aside"]], [("2 A St", True, True)])
        self.assertEqual(info["backups_used"], 1)

    def test_same_cards_same_comps_whatever_the_judging_order(self):
        """The cascade from eval 17: each outlier is judged against the others again after one is set aside."""
        values = (470000, 521300, 425000, 484500, 461600, 468000, 474000, 466000)
        comps = {"cards": self.cards(*values)}
        cma.select_comps(comps)
        first = [c["address"] for c in comps["cards"]]
        for _ in range(3):
            again = {"cards": self.cards(*values)}
            cma.select_comps(again)
            self.assertEqual([c["address"] for c in again["cards"]], first)
        vals = [c["adjusted"] for c in comps["cards"]]
        self.assertEqual(cma.outlier_warnings(comps["cards"]), [])  # none left flagged
        self.assertEqual(len(vals), 5)

    def test_no_backup_and_kept_cards(self):
        comps = {"cards": self.cards(470000, 521300, 465000, 484500, 461600)}
        info = cma.select_comps(comps)  # no backup: set aside while three remain
        self.assertEqual(len(comps["cards"]), 4)
        self.assertFalse(info["set_aside"][0]["replaced"])
        comps = {"cards": self.cards(470000, 521300, 465000)}
        cma.select_comps(comps)  # three only: nothing set aside
        self.assertEqual(len(comps["cards"]), 3)
        cards = self.cards(470000, 521300, 465000, 484500, 461600, 472000)
        cards[1]["keep_reason"] = "The agent's call: the same floor plan next door."
        comps = {"cards": cards}
        info = cma.select_comps(comps)
        self.assertIn("2 A St", [c["address"] for c in comps["cards"]])
        self.assertEqual([x["address"] for x in info["kept"]], ["2 A St"])
        comps = {"cards": self.cards(470000, 471000, 465000, 484500, 461600, 472000), "count": 6}
        cma.select_comps(comps)
        self.assertEqual(len(comps["cards"]), 6)


class Roof(unittest.TestCase):
    """Roof adjustments are the script's, from roof years and the market's bands; an unknown roof on the home: none."""
    market = profiles_market = None

    @classmethod
    def setUpClass(cls):
        cls.market = compute.profiles.load_market(state="FL", county="Seminole")

    def apply(self, subject, *roofs, typed=None):
        cards = [{"address": f"{i} A St", "adjustments": list(typed or []), **r} for i, r in enumerate(roofs, 1)]
        comps = {"cards": cards}
        errors, info = cma.apply_roof_adjustments(comps, subject, self.market, "2026-09-26")
        return errors, info, [[a["amount"] for a in c["adjustments"] if a.get("kind") == "roof"] for c in cards]

    def test_bands_by_difference(self):
        # the subject's 16-year roof (-$10,000) against a 7-year one ($0): -$10,000; same band: none; older: plus
        _, info, amounts = self.apply({"roof_year": 2010}, {"roof_year": 2019}, {"roof_year": 2011}, {"roof_year": 2004})
        self.assertEqual(amounts, [[-10000], [], [5000]])
        self.assertEqual((info["subject_known"], info["subject_age"]), (True, 16))
        _, _, amounts = self.apply({"roof_year": 2010, "roof_type": "tile"}, {"roof_year": 2019})  # tile: 16 years is $0
        self.assertEqual(amounts, [[]])

    def test_unknown_home_roof_and_unknown_comp(self):
        _, info, amounts = self.apply({}, {"roof_year": 2019}, {"roof_year": 2004})
        self.assertEqual((amounts, info["subject_known"]), ([[], []], False))
        _, info, amounts = self.apply({"roof_year": 2010}, {}, {"roof_year": 2019})
        self.assertEqual(info["unknown"], ["1 A St"])
        self.assertEqual(len(cma.roof_warnings(info)), 1)

    def test_typed_roof_and_bad_inputs_stop(self):
        errors, _, _ = self.apply({"roof_year": 2010}, {"roof_year": 2019}, typed=[{"label": "Older Roof", "amount": 10000}])
        self.assertIn("roof adjustment", errors[0])
        errors, _, _ = self.apply({"roof_year": "2010"}, {"roof_year": 2019, "roof_type": "slate"})
        self.assertEqual(len(errors), 2)
        bare = cma.apply_roof_adjustments({"cards": [{"address": "x", "adjustments": [{"label": "Roof", "amount": 1}]}]},
                                          {}, compute.profiles.load_market(state="TX", county="Travis"), "2026-09-26")
        self.assertEqual(bare, ([], None))  # no bands outside the built-in market: the agent's typed rates stand

    def test_tanager_roofs(self):
        C, _ = run(tanager())  # the home's 2021 roof against three comps' 2010 roofs: each +$10,000
        older = [c for c in C["comps"]["cards"] if any(a.startswith("Roof:") for a, _ in c["lines"])]
        self.assertEqual(len(older), 3)
        self.assertTrue(all(v == "+$10,000" for c in older for a, v in c["lines"] if a.startswith("Roof:")))


class SizeAndLot(unittest.TestCase):
    """Size and lot adjustments are the script's: sq ft from the export (or the card) at the market's rate, and the lot
    by its type; a typed size, lot or water amount stops the run (iteration 18: two runs typed a corner lot apart)."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = compute.profiles.load_market(state="FL", county="Seminole")

    def lines(self, subject, *cards, given=None, homes=()):
        comps = {"cards": [{"address": f"{i} A St", "adjustments": [], **c} for i, c in enumerate(cards, 1)],
                 **(given or {})}
        size = cma.apply_size_adjustments(comps, {"sqft": 1800, **subject}, self.market, homes)
        lot = cma.apply_lot_adjustments(comps, subject, self.market)
        return size, lot, [[(a["label"], a["amount"]) for a in c["adjustments"]] for c in comps["cards"]]

    def test_size_from_the_card_or_the_export(self):
        homes = [{"status": "SOLD", "address": "2 A ST", "living_area": 1700.0}]
        (_, info), _, lines = self.lines({}, {"sqft": 1830}, {}, {}, homes=homes)
        self.assertEqual(lines, [[("Size: 30 Sq Ft Larger", -2250)], [("Size: 100 Sq Ft Smaller", 7500)], []])
        self.assertEqual(info["unknown"], ["3 A St"])
        (_, info), _, _ = self.lines({}, {"sqft": 2200})
        self.assertEqual(info["wide"], [("1 A St", 400)])
        self.assertEqual([k for k, _ in cma.size_warnings(info)], ["size_wide"])
        (_, _), _, lines = self.lines({}, {"sqft": 1700}, given={"size_per_sqft": 50})  # the agent's rate
        self.assertEqual(lines, [[("Size: 100 Sq Ft Smaller", 5000)]])

    def test_lot_by_type(self):
        _, (errors, _), lines = self.lines({}, {"lot": "canal"}, {"lot": "corner_or_oversized"}, {})
        self.assertEqual(errors, [])
        self.assertEqual([[x for x in c if x[0].startswith("Lot")] for c in lines],
                         [[("Lot: Canal", -10000)], [("Lot: Corner or Oversized", -5000)], []])
        _, _, lines = self.lines({"lot": "view"}, {"lot": "view"}, {})  # the same lot: none; the home's view: plus
        self.assertEqual([[x for x in c if x[0].startswith("Lot")] for c in lines], [[], [("Lot: Standard", 5000)]])
        _, _, lines = self.lines({}, {"lot": "other", "lot_value": -5000, "lot_reason": "backs onto a busy road"})
        self.assertEqual(lines[0][-1], ("Lot: Backs Onto a Busy Road", 5000))

    def test_typed_amounts_and_bad_inputs_stop(self):
        comps = {"cards": [{"address": "1 A St", "adjustments": [{"label": "Size", "amount": 1500},
                                                                   {"label": "Oversized Corner Lot", "amount": -5000},
                                                                   {"label": "Newer Water Heater", "amount": -2000},
                                                                   {"label": "Extra Bedroom", "amount": -8000,
                                                                    "kind": "size"}]}]}
        errors, _ = cma.apply_size_adjustments(comps, {"sqft": 1800}, self.market)
        self.assertEqual(len(errors), 1)  # the size line; a bedroom count stays the agent's
        errors, _ = cma.apply_lot_adjustments(comps, {}, self.market)
        self.assertEqual(len(errors), 1)  # the corner lot; a water heater is a system, not water
        errors, _ = cma.apply_lot_adjustments({"cards": [{"address": "1 A St", "lot": "other"}]}, {"lot": "pond"},
                                              self.market)
        self.assertEqual(len(errors), 3)  # an unknown type, and an "other" lot without its value and reason
        texas = compute.profiles.load_market(state="TX", county="Travis")
        errors, _ = cma.apply_lot_adjustments({"cards": [{"address": "1 A St", "lot": "canal"}]}, {}, texas)
        self.assertIn("comps.lot_values", errors[0])  # no built-in lot values outside Florida
        errors, _ = cma.apply_size_adjustments({"cards": [{"address": "1 A St", "sqft": 1700}]}, {"sqft": 1800}, texas)
        self.assertIn("comps.size_per_sqft", errors[0])
        errors, _ = cma.apply_size_adjustments({"cards": []}, {}, self.market)
        self.assertIn("subject.sqft", errors[0])

    def test_errors_name_the_agents_own_position(self):
        """The script's lines go in first (size, condition, lot); an error on a typed line still names where the agent
        typed it, and a typed time line is removed itself, never a script line that moved into its place."""
        cards = [{"address": "1 A St", "sold_price": 400000, "condition": "original", "sqft": 1700,
                  "adjustments": [{"label": "Pool", "amount": 25000}, {"label": "Older Roof", "amount": 5000}]}]
        R = {"as_of": "2026-09-26", "subject": {"sqft": 1800, "condition": "full_renovation", "roof_year": 2015},
             "comps": {"cards": cards}}
        errors, _, _ = cma.settle_comps(R, [], self.market, None)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("comps.cards[0].adjustments[1]:"), errors[0])
        self.assertEqual(cma.typed_adjustments({"adjustments": [{"label": "Size", "source": "script"}, {"label": "Pool"}]}),
                         [(0, {"label": "Pool"})])

    def test_recent_systems_by_difference(self):
        comps = {"cards": [{"address": "1 A St", "recent_systems": True, "adjustments": []},
                           {"address": "2 A St", "adjustments": []}]}
        errors, _ = cma.apply_systems_adjustments(comps, {}, self.market)
        self.assertEqual(errors, [])
        self.assertEqual([[(a["label"], a["amount"]) for a in c["adjustments"]] for c in comps["cards"]],
                         [[("Documented Recent Systems", -5000)], []])
        errors, _ = cma.apply_systems_adjustments(comps, {"recent_systems": True}, self.market)  # the home has them
        self.assertEqual([[(a["label"], a["amount"]) for a in c["adjustments"]] for c in comps["cards"]],
                         [[], [("No Documented Recent Systems", 5000)]])
        typed = {"cards": [{"address": "1 A St", "adjustments": [{"label": "Newer AC", "amount": -5000},
                                                                 {"label": "Older Roof", "amount": 5000}]}]}
        errors, _ = cma.apply_systems_adjustments(typed, {}, self.market)
        self.assertEqual(len(errors), 1)  # the AC; the roof is the roof step's
        R = {"as_of": "2026-09-26", "subject": {"sqft": 1800, "condition": "original", "roof_year": 2015},
             "comps": {"cards": [{"address": "1 A St", "sold_price": 400000, "condition": "original", "sqft": 1800,
                                  "roof_year": 2024, "recent_systems": True, "adjustments": []}]}}
        self.assertEqual(cma.settle_comps(R, [], self.market, None)[0], [])
        kinds = [a["label"] for a in R["comps"]["cards"][0]["adjustments"]]
        self.assertIn("Documented Recent Systems", kinds)  # kept through the roof step, which shares its kind
        self.assertTrue(any(k.startswith("Roof:") for k in kinds))

    def test_systems_year_judged_by_the_script(self):
        """Iteration 20: three runs read "2020" and "2021" systems differently against "within five years"."""
        self.assertTrue(cma.has_recent_systems({"systems_year": 2021}, "2026-09-26"))
        self.assertFalse(cma.has_recent_systems({"systems_year": 2020}, "2026-09-26"))
        self.assertTrue(cma.has_recent_systems({"recent_systems": True}, "2026-09-26"))  # undated "new"
        self.assertFalse(cma.has_recent_systems({"systems_year": 2019, "recent_systems": True}, "2026-09-26"))
        comps = {"cards": [{"address": "1 A St", "systems_year": 2021, "adjustments": []}]}
        errors, _ = cma.apply_systems_adjustments(comps, {}, self.market, "2026-09-26")
        self.assertEqual((errors, [a["kind"] for a in comps["cards"][0]["adjustments"]]), ([], ["systems"]))
        errors, _ = cma.apply_systems_adjustments({"cards": [{"address": "1 A St", "systems_year": "2021"}]}, {},
                                                  self.market, "2026-09-26")
        self.assertIn("systems_year", errors[0])

    def test_national_rates_where_none_are_built_in(self):
        """Owner decision (2026-10-13): outside a built-in market the size, condition, lot and systems rates are the
        national shares scaled to the comps' median net price, so runs agree; a given rate or a market's own wins."""
        texas = compute.profiles.load_market(state="TX", county="Travis")
        comps = {"cards": [{"address": "1 A St", "sold_price": 400000, "sqft": 2000},
                           {"address": "2 A St", "sold_price": 420000, "seller_concessions": 20000, "sqft": 2000}],
                 "lot_values": {"canal": 7000}}
        filled = cma.national_rates(comps, texas)
        self.assertEqual(filled, ["size", "condition", "systems"])  # the agent's lot values stand
        self.assertEqual(comps["size_per_sqft"], 66)  # a third of the median $200/sq ft, net of seller-paid costs
        self.assertEqual(comps["condition_values"]["full_renovation"], 40000)  # 10% of $400,000
        self.assertEqual(comps["systems_value"], 4000)
        self.assertEqual(comps["lot_values"], {"canal": 7000})
        self.assertEqual(cma.national_rates({"cards": comps["cards"]}, self.market), [])  # Florida has its own
        C, _ = run(T_texas_without_rates())
        self.assertIn("national_rates", C["note_keys"])

    def test_subject_card(self):
        """Owner decision (2026-10-13): the home's own card first, from the facts every comp is adjusted to."""
        t = compute.t
        card = cma.subject_card({"sqft": 1849, "beds": 4, "baths": 2, "pool": True, "year_built": 1972,
                                 "condition": "full_renovation", "lot": "canal", "systems_year": 2022}, {}, t, "2026-09-26")
        self.assertEqual(card["meta"], ["1,849 sq ft", "4/2", "pool", "built 1972"])
        self.assertEqual(dict(card["lines"]), {"Condition": "Full Renovation", "Lot": "Canal", "Roof": "Year not known",
                                               "Systems": "Updated 2022"})
        old = cma.subject_card({"sqft": 1849, "condition": "full_renovation", "lot": "standard", "systems_year": 2020},
                               {}, t, "2026-09-26")  # iteration 21: a year the script didn't count says so
        self.assertEqual(dict(old["lines"])["Systems"], "Updated 2020, not recent")
        C, _ = run(tanager())
        self.assertEqual(C["comps"]["subject_card"]["tag"], "Your Home")
        self.assertIn("Recommended", C["comps"]["subject_card"]["price"])

    def test_seller_report_prices_size_and_lot(self):
        C, _ = run(tanager())
        lines = [a for c in C["comps"]["cards"] for a, _ in c["lines"]]
        self.assertTrue(any(a.startswith("Size: ") for a in lines))


if __name__ == "__main__":
    unittest.main()
