"""shared/cma.py comp rules: the supported range width, time adjustments and the adjustment summary (buyer-cma and
seller-cma share them)."""
import os
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
        cards["907 Tanager Ridge Dr"]["adjustments"].append({"label": "Spring Sale", "amount": -7000})
        self.assertEqual([v for a, v in card(run(R)[0], "907 Tanager Ridge Dr")["lines"] if a == "Spring Sale"], ["−$7,100"])
        R = tanager()  # a sale after the cutoff gets none
        next(c for c in R["comps"]["cards"] if c["address"] == "655 Phoebe Ln")["adjustments"].append(
            {"label": "Summer Sale", "amount": -4300})
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
