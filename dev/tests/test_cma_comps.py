"""shared/cma.py comp rules: the supported range width, time adjustments, comp facts the prose must agree with, the
adjustment summary and small formats (buyer-cma and seller-cma share them)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402
from test_seller_cma import card, compute, run, tanager  # noqa: E402

cma, finance = compute.cma, compute.finance


def stops(test, R, pattern):
    with test.assertRaisesRegex(compute.ReportError, pattern):
        run(R)


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

    def test_rule_per_comp(self):
        R = tanager()
        C, _ = run(R)
        self.assertEqual(card(R, "907 Tanager Ridge Dr")["time_amount"], -7100)  # June 12 to Sep 26 at 1.5% a quarter
        self.assertEqual(card(R, "655 Phoebe Ln")["time_amount"], 0)  # July 18: after the July 1 split, none
        self.assertEqual((C["placeholders"]["time_rate"], C["placeholders"]["time_cutoff"]), ("1.5%", "July"))
        R = tanager()
        c = card(R, "907 Tanager Ridge Dr")
        c["address"], c["meta"] = "1 Nowhere Ln", "Sold $405,000"
        self.assertIn("time_undated", run(R)[0]["warning_keys"])

    def test_typed_amounts(self):
        R = tanager()  # a typed amount that agrees is kept as the script's
        card(R, "907 Tanager Ridge Dr")["adjustments"].append({"label": "June Sale", "amount": -7000})
        run(R)
        self.assertEqual([a["amount"] for a in card(R, "907 Tanager Ridge Dr")["adjustments"] if a.get("kind") == "time"],
                         [-7100])
        R = tanager()  # a sale after the cutoff gets none
        card(R, "655 Phoebe Ln")["adjustments"].append({"label": "Mid-July Sale", "amount": -4300})
        stops(self, R, r"comps\.cards\[3\]\.adjustments\[2\]: .*−\$4,300")
        R = tanager()  # typed without a stated rule
        R["comps"].pop("time_adjustment")
        card(R, "907 Tanager Ridge Dr")["adjustments"].append({"label": "Market Since the Sale", "amount": -7100})
        stops(self, R, r"−\$7,100.*comps\.time_adjustment")

    def test_hand_typed_amount_is_checked(self):
        cards = [{"address": "1 A St", "sold_price": 490000, "seller_concessions": 0, "close_date": "2026-08-19",
                  "adjustments": [{"label": "Market Since the Sale", "amount": -4000}]}]
        errors, _ = cma.apply_time_adjustments({"cards": cards, "time_adjustment": {"rate_per_quarter": 0.01,
                                                                                     "cutoff": "2026-09-01"}},
                                               [], "2026-09-23", None)
        self.assertEqual(len(errors), 1)
        self.assertIn("−$1,900", errors[0])  # 35 days at 1% a quarter on $490,000

    def test_method_note_month_and_rate_must_be_the_rule(self):
        R = tanager()
        R["comps"]["method_note"] = "About 1.5% per quarter off sales before August, since prices softened."
        stops(self, R, r"comps\.method_note: .*August")
        R["comps"]["method_note"] = "About 2% per quarter off older sales."
        stops(self, R, r"comps\.method_note: .*2%")
        R = tanager()  # the cutoff's own month in the method note is fine, and isn't the market split
        R["comps"]["time_adjustment"]["cutoff"] = "2026-08-01"
        R["comps"]["method_note"] = R["comps"]["method_note"].replace("{time_cutoff}", "August")
        run(R)
        R["market"]["intro"] = "Homes sold since August took about a month to sell."
        stops(self, R, r"market\.intro")


class CompFacts(unittest.TestCase):
    """Counts, bands and the newest sale come from the comps; prose that contradicts them stops."""

    def setUp(self):
        self.cards = [{"address": a, "sold_price": p, "seller_concessions": 0, "adjusted": v, "close_date": d,
                       "adjustments": [{"label": "Roof", "amount": 5000}] if roof else []}
                      for a, p, v, d, roof in (("1 A St", 440000, 441000, "2026-07-20", True),
                                               ("2 B St", 445000, 443000, "2026-08-02", True),
                                               ("3 C St", 446000, 444500, "2026-08-30", True),
                                               ("4 D St", 452000, 451750, "2026-09-16", False),
                                               ("5 E St", 430000, 437800, "2026-05-10", False))]
        self.values, self.raw = cma.comp_facts(self.cards, [], date(2026, 7, 1))

    def errors(self, text, path="comps.summary_paragraph"):
        return cma.comp_prose_errors([(path, text)], self.raw)

    def test_contradictions_stop(self):
        self.assertEqual(len(self.errors("The three sales that closed since July cluster tightly in the low $440,000s.")), 2)
        self.assertEqual(len(self.errors("Four comps with newer roofs sold quickly.")), 1)
        self.assertEqual(len(self.errors("The most recent close match.", "comps.cards[0].bullets[0]")), 1)

    def test_true_statements_pass_and_fill(self):
        for text in ("The four sales that closed since July sit between $441,000 and $451,750.",
                     "Three comps with newer roofs sold quickly.", "We chose the five closest matches.",
                     "The four-bedroom sales on Vireo Dr are larger.",
                     "Listings in the $410,000s have sat."):  # listings, not comps
            self.assertEqual(self.errors(text), [], text)
        self.assertEqual(self.errors("The newest sale.", "comps.cards[3].bullets[0]"), [])
        self.assertEqual((self.values["comps_count"], self.values["comps_since_split"], self.values["comps_with_age"]),
                         ("five", "four", "three"))
        self.assertEqual((self.values["newest_comp"], self.values["newest_comp_date"]), ("4 D St", "September 16"))
        self.assertEqual(cma.fill("{comps_since_split} sales closed since July.", self.values), "Four sales closed since July.")


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

    def test_tables_and_dates(self):
        self.assertIn("<th>April–June</th>", cma.table(["April – June"], [["1"]]))
        self.assertEqual(cma.unspaced_range("July - Mid-Sept"), "July–Mid-Sept")
        self.assertEqual(cma.history_date_labels([date(2015, 3, 31), date(2026, 8, 14)], 2026), ["Mar 31, 2015", "Aug 14, 2026"])
        self.assertEqual(cma.history_date_labels([date(2026, 8, 14)], 2026), ["Aug 14"])


if __name__ == "__main__":
    unittest.main()
