"""Manual round v5 (sources/Results_v5 case 02 seller CMA, case 03 buyer CMA): the shared CMA rules and the seller CMA.

The Tanager fixture (dev/fixtures/seller-cma/tanager) rebuilds case 02's inputs: 842 Tanager Ridge Dr, the five comps,
the September 26 as-of date, a July 1 market split and the seller's stated $171,500 payoff.
"""
import copy
import json
import os
import sys
import unittest
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, seller_render, deck = load("seller-cma", "compute", "render", "deck")
buyer = load("buyer-cma", "compute")[0]
cma, finance = compute.cma, compute.finance

TANAGER = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "tanager", "report.json")
BUYER = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")


def tanager():
    with open(TANAGER) as f:
        R = json.load(f)
    R["export"] = os.path.join(os.path.dirname(TANAGER), R["export"])
    return R


def run(R):
    market, homes = compute.load_inputs(R)
    return compute.compute(R, market, homes), homes


def stops(test, R, pattern):
    with test.assertRaisesRegex(compute.ReportError, pattern):
        run(R)


def card(R, address):
    return next(c for c in R["comps"]["cards"] if c["address"] == address)


class RangeWidth(unittest.TestCase):
    """Owner decision A: the range is about 5-6% of the value wide, never wider than the cap nor narrower than half."""

    def test_buyer_case_is_too_wide(self):
        values = [431500, 437800, 441625, 445500, 451750]  # case 03: $425,000 - $455,000 came out $30,000 wide
        out = dict(cma.range_warnings({"low": 425000, "high": 455000}, values, None))
        self.assertIn("range_wide", out)
        self.assertIn("$15,000 to $25,000 wide", out["range_wide"])
        lo, hi = cma.passing_range(values, None)
        self.assertEqual(hi - lo, 25000)
        self.assertEqual(cma.range_warnings({"low": lo, "high": hi}, values, None), [])

    def test_seller_case_is_too_wide_and_the_example_passes(self):
        values = [380200, 384000, 386800, 387500, 400100]  # case 02's $375,000 - $400,000
        out = dict(cma.range_warnings({"low": 375000, "high": 400000}, values, None))
        self.assertEqual(list(out), ["range_wide"])
        w = cma.range_width(386800)
        self.assertEqual((round(w["cap"]), w["target"]), (23208, 20000))
        lo, hi = cma.passing_range(values, None)
        self.assertEqual(cma.range_warnings({"low": lo, "high": hi}, values, None), [])

    def test_never_narrower_than_half_the_cap(self):
        values = [438000, 440000, 441000, 442000]
        self.assertEqual([k for k, _ in cma.range_warnings({"low": 435000, "high": 445000}, values, None)], ["range_narrow"])
        self.assertEqual(cma.range_warnings({"low": 430000, "high": 445000}, values, None), [])


class Payoff(unittest.TestCase):
    """Owner decision B: a stated payoff is used as given; only a balance gets a month's interest, at its own rate or 4.5%."""

    def test_stated_payoff_as_given(self):
        C, _ = run(tanager())
        row = next(r for r in C["net"]["rows"] if r["key"] == "payoff")
        self.assertEqual(row["amounts"][0], -171500)
        self.assertEqual(row["label"], "Mortgage Payoff (Your Estimate)")
        self.assertIn("payoff_seller", C["assumption_keys"])

    def test_balance_gets_a_month_at_four_and_a_half(self):
        R = tanager()
        R["costs"].pop("mortgage_payoff")
        R["costs"]["mortgage_balance"] = 171500
        C, _ = run(R)
        row = next(r for r in C["net"]["rows"] if r["key"] == "payoff")
        self.assertEqual(row["amounts"][0], -round(171500 * (1 + 0.045 / 12)))  # $172,143, never the hidden 7%
        self.assertIn("an assumed 4.5%", " ".join(C["assumptions"]))
        self.assertEqual(finance.payoff_from_balance(200000, 6), 201000)


class TimeAdjustments(unittest.TestCase):
    """Item 1: time adjustments are the script's, from the stated rate and cutoff (the market split by default)."""

    def test_rule_per_comp(self):
        C, _ = run(R := tanager())
        self.assertEqual(card(R, "907 Tanager Ridge Dr")["time_amount"], -7100)  # June 12 to Sep 26 at 1.5% a quarter
        self.assertEqual(card(R, "655 Phoebe Ln")["time_amount"], 0)  # July 18: after the July 1 split, none
        self.assertEqual((C["placeholders"]["time_rate"], C["placeholders"]["time_cutoff"]), ("1.5%", "July"))
        self.assertIn("1.5% a quarter off sales before July", C["adjustment_summary"])

    def test_typed_amount_after_the_cutoff_stops(self):
        R = tanager()  # case 02: the July 18 sale still got "minus $4,300"
        card(R, "655 Phoebe Ln")["adjustments"].append({"label": "Mid-July Sale", "amount": -4300})
        stops(self, R, r"comps\.cards\[3\]\.adjustments\[2\]: the time adjustment is −\$4,300, but it closed July 18, 2026, "
                       r"on or after the July 1, 2026 cutoff, so it gets none →")

    def test_typed_amount_that_agrees_is_kept_as_the_scripts(self):
        R = tanager()
        card(R, "907 Tanager Ridge Dr")["adjustments"].append({"label": "June Sale", "amount": -7000})
        run(R)
        adj = [a for a in card(R, "907 Tanager Ridge Dr")["adjustments"] if a.get("kind") == "time"]
        self.assertEqual([a["amount"] for a in adj], [-7100])

    def test_buyer_five_week_old_sale(self):
        cards = [{"address": "1 A St", "sold_price": 490000, "seller_concessions": 0, "close_date": "2026-08-19",
                  "adjustments": [{"label": "Market Since the Sale", "amount": -4000}]}]
        errors, _ = cma.apply_time_adjustments({"cards": cards, "time_adjustment": {"rate_per_quarter": 0.01,
                                                                                     "cutoff": "2026-09-01"}},
                                               [], "2026-09-23", None)
        self.assertEqual(len(errors), 1)
        self.assertIn("gives −$1,900", errors[0])  # 35 days at 1% a quarter on $490,000

    def test_method_month_and_rate_must_be_the_rule(self):
        R = tanager()
        R["comps"]["method_note"] = "About 1.5% per quarter off sales before August, since prices softened."
        stops(self, R, r'comps\.method_note: says "before August", but the time adjustment applies to sales before July')
        R["comps"]["method_note"] = "About 2% per quarter off older sales."
        stops(self, R, r'says "2%" a quarter, but the time adjustment applied is 1\.5%')

    def test_typed_without_a_rule_stops(self):
        R = tanager()
        R["comps"].pop("time_adjustment")
        card(R, "907 Tanager Ridge Dr")["adjustments"].append({"label": "Market Since the Sale", "amount": -7100})
        stops(self, R, r"a time adjustment \(−\$7,100\) typed by hand → state the method once in comps\.time_adjustment")

    def test_undated_comp_warns_never_stops(self):
        R = tanager()
        c = card(R, "907 Tanager Ridge Dr")
        c["address"], c["meta"] = "1 Nowhere Ln", "Sold $405,000"
        C, _ = run(R)
        self.assertIn("time_undated", C["warning_keys"])


class MethodLine(unittest.TestCase):
    """Item 2: the method line names every adjustment kind used, from the comps."""

    def test_every_kind_listed(self):
        cards = [{"adjustments": [{"label": "Primary Bath", "amount": -10000}, {"label": "Size", "amount": -1100}],
                  "seller_concessions": 0},
                 {"adjustments": [{"label": "Roof Age", "amount": 5000}], "seller_concessions": 6500}]
        text = cma.adjustment_summary(cards)
        self.assertEqual(text, "Adjusted for condition and updates ($10,000), size ($1,100), roof and systems ($5,000) "
                               "and seller credits (taken off each sale price).")

    def test_report_prints_it(self):
        R = tanager()
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, {})
        self.assertIn(C["adjustment_summary"], doc)


class CompProse(unittest.TestCase):
    """Item 3: counts, bands and the newest sale come from the comps; wording that contradicts them stops."""

    def setUp(self):
        self.cards = [{"address": a, "sold_price": p, "seller_concessions": 0, "adjusted": v, "close_date": d,
                       "adjustments": [{"label": "Roof", "amount": 5000}] if roof else []}
                      for a, p, v, d, roof in (("1 A St", 440000, 441000, "2026-07-20", True),
                                               ("2 B St", 445000, 443000, "2026-08-02", True),
                                               ("3 C St", 446000, 444500, "2026-08-30", True),
                                               ("4 D St", 452000, 451750, "2026-09-16", False),
                                               ("5 E St", 430000, 437800, "2026-05-10", False))]
        self.values, self.raw = cma.comp_facts(self.cards, [], date(2026, 7, 1))

    def check(self, text, path="comps.summary_paragraph"):
        return cma.comp_prose_errors([(path, text)], self.raw)

    def test_case_03_sentences_stop(self):
        self.assertEqual(len(self.check("The three sales that closed since July cluster tightly in the low $440,000s.")), 2)
        self.assertEqual(len(self.check("Four comps with newer roofs sold quickly.")), 1)
        out = cma.comp_prose_errors([("comps.cards[0].bullets[0]", "The most recent close match.")], self.raw)
        self.assertIn("a comp closed later", out[0])

    def test_true_sentences_pass(self):
        self.assertEqual(self.check("The four sales that closed since July sit between $441,000 and $451,750."), [])
        self.assertEqual(self.check("Three comps with newer roofs sold quickly."), [])
        self.assertEqual(self.check("We chose the five closest matches."), [])
        self.assertEqual(self.check("The four-bedroom sales on Vireo Dr are larger."), [])
        self.assertEqual(self.check("Listings in the $410,000s have sat."), [])  # listings, not comps
        self.assertEqual(cma.comp_prose_errors([("comps.cards[3].bullets[0]", "The newest sale.")], self.raw), [])

    def test_placeholders(self):
        self.assertEqual((self.values["comps_count"], self.values["comps_since_split"], self.values["comps_with_age"]),
                         ("five", "four", "three"))
        self.assertEqual((self.values["newest_comp"], self.values["newest_comp_date"]), ("4 D St", "September 16"))
        self.assertEqual(cma.fill("{comps_since_split} sales closed since July.", self.values), "Four sales closed since July.")


class SmallFormats(unittest.TestCase):
    def test_tax_pair_reconciles(self):  # item 4: "≈ $7,100/yr" beside "≈ $596/mo"
        yearly, monthly = finance.tax_pair(7152)
        self.assertEqual((yearly, monthly), (7200, 600))

    def test_buyer_median_sale_price_to_the_dollar(self):  # item 5
        rows = buyer.market_rows({"market": {"columns": ["", "A", "B"], "rows": [["Homes Sold", "7", "8"]]}},
                                 [469250, 451500])
        self.assertEqual(rows[1], ["Median Sale Price", "$469,250", "$451,500"])

    def test_header_dashes(self):  # item 6
        self.assertIn("<th>April–June</th>", cma.table(["April – June"], [["1"]]))
        self.assertEqual(cma.unspaced_range("July - Mid-Sept"), "July–Mid-Sept")

    def test_history_year_on_every_row(self):  # item 7
        dates = [date(2015, 3, 31), date(2026, 8, 14)]
        self.assertEqual(cma.history_date_labels(dates, 2026), ["Mar 31, 2015", "Aug 14, 2026"])
        self.assertEqual(cma.history_date_labels([date(2026, 8, 14)], 2026), ["Aug 14"])


class SellerCase02(unittest.TestCase):
    def test_expected_sale_note_is_plain(self):  # item 9
        C, homes = run(R := tanager())
        note = C["expected_sale_basis"]["note"]
        self.assertNotIn("97.0%", note)
        self.assertNotIn("rounded", note)
        self.assertIn("97.0%", C["expected_sale_basis"]["method"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, {})
        method = doc[doc.index("How This Was Prepared"):]
        self.assertIn("rounded to $500", method)

    def test_one_launch_date(self):  # item 10
        R = tanager()
        R["deck"]["timeline"][2] = ["Mid-October", "Go live at {list_price}"]
        stops(self, R, r'deck\.timeline\[2\]\[0\]: "Mid-October" for "Go live at \{list_price\}", but the plan goes live '
                       r"early October \(October 10")
        R["deck"]["timeline"][2] = ["{launch_when}", "Go live at {list_price}"]
        R["summary_page"]["next_step"] = "Go live within about three weeks."
        stops(self, R, r"summary_page\.next_step: says \"Go live \.\.\. within about three weeks\"")
        R["summary_page"]["next_step"] = "Go live in {launch_weeks}."
        C, _ = run(R)
        self.assertEqual((C["launch"]["when"], C["placeholders"]["launch_weeks"]), ("early October", "about two weeks"))
        R["launch_date"] = "2026-10-15"
        self.assertEqual(run(R)[0]["placeholders"]["launch_when"], "mid-October")

    def test_strongest_match_is_the_scripts(self):  # item 13
        R = tanager()  # case 02: 818 adjusted to $400,100, above the range, was called "Strongest match"
        card(R, "818 Tanager Ridge Dr")["adjustments"][0]["amount"] = 7100
        R["deck"]["comp_lines"]["818 Tanager Ridge Dr"] = "Strongest match; your street"
        stops(self, R, r'deck\.comp_lines\["818 Tanager Ridge Dr"\]: says "Strongest match", but the strongest match is '
                       r"790 Tanager Ridge Dr")
        R["deck"]["comp_lines"]["818 Tanager Ridge Dr"] = "Your street; 12 days"
        C, homes = run(R)
        D = deck.deck_data(copy.deepcopy(R), C, homes, {}, compute.labels(R), "footer")
        lines = {c["address"]: c["line"] for c in D["comps"]}
        self.assertTrue(lines["790 Tanager Ridge Dr"].startswith("Strongest match · "))
        self.assertFalse(lines["818 Tanager Ridge Dr"].startswith("Strongest"))

    def test_page_one_star_stays_on_the_price_line(self):  # item 12
        C, homes = run(R := tanager())
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, {})
        self.assertIn("$389,900&nbsp;★", doc)

    def test_deck_comps_are_the_brand(self):  # item 12: comps as on the PDF
        K = deck.design.pptx_colors(deck.design.theme(None, "seller"))
        self.assertEqual(deck.contrast_roles(K)["comp"], K["brand"])
