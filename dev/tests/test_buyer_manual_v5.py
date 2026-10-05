"""Fixes from the fifth manual round (sources/Results_v5, case 4: 2315 Kestrel Point Ct offer from the case 3 buyer CMA).
The fixture kestrel-v5.json replays the case: range $425K-$455K, median $441,625, target $435K-$439K, walk-away
$441K, cash $42,000, reserve floor $5,000, payment limit $4,000, max $460,000, one competing offer, AS IS."""
import copy
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

strategy, offer_render = load("buyer-offer-strategy", "strategy", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def fixture(name="kestrel-v5.json"):
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy", name)) as f:
        return json.load(f)


def run(d):
    return strategy.analyze(d, cma=strategy.load_cma(d))


class Case4Consistency(unittest.TestCase):
    """The case's own checks: the offer sits inside the CMA's range and walk-away, and inside every buyer limit."""

    def test_offer_inside_the_cma_and_the_limits(self):
        r = run(fixture())
        res = strategy.result(r)
        self.assertEqual(res["value_range"], "$425,000–$455,000")
        t, c = r["terms"]["recommended"], r["cash"]["recommended"]
        self.assertTrue(425000 <= t["price"] <= 441000)
        self.assertLessEqual(c["worst"], 42000)
        self.assertGreaterEqual(c["reserve"], 5000)
        self.assertLessEqual(r["payment"]["recommended"], 4000)


class NoStrongerOption(unittest.TestCase):
    def test_never_claims_nothing_more_would_help(self):
        """p1 said "nothing more would make the offer stronger" while a smaller concession ask inside the limits nets
        the seller more: the reason now names those terms and why they aren't offered, with no colon (it prints after
        "No Stronger Option:")."""
        r = run(fixture())
        why = r["absent"]["stronger"]
        self.assertNotIn("nothing more would make", why)
        self.assertNotIn(":", why)
        self.assertIn("$1,000 in seller concessions instead of $1,500", why)
        self.assertIn("wouldn't change the outlook", why)

    def test_stronger_net_stays_inside_every_limit_and_ranks_higher(self):
        d = fixture()
        r = run(d)
        B, costs, rec = r["B"], r["costs"], r["terms"]["recommended"]
        st = strategy.stronger_net(B, costs, rec)
        self.assertIsNotNone(st)
        self.assertTrue(strategy.within_limits(B, costs, st))
        self.assertLessEqual(st["price"], 441000)  # never past the CMA's walk-away
        self.assertGreater(st["price"] - st["seller_concessions"], rec["price"] - rec["seller_concessions"])

    def test_a_stronger_option_that_ranks_higher_is_shown_not_promoted(self):
        """With the price below the range's top and room in the limits, Stronger is a real option the buyer can pick;
        it never replaces the recommended offer."""
        d = fixture()
        d["overrides"] = {"price": 436000, "seller_concessions": 5000, "deposit": 13500}  # the deposit already 3%
        r = run(d)
        lvl = r["B"]["competition"]["level"]
        self.assertEqual(r["terms"]["recommended"]["price"], 436000)
        st = r["terms"]["stronger"]
        self.assertEqual((st["price"], st["seller_concessions"]), (440000, 1000))
        self.assertTrue(strategy.within_limits(r["B"], r["costs"], st))
        self.assertEqual(r["bands"]["stronger"][lvl][1], "At Risk")
        self.assertEqual(r["bands"]["recommended"][lvl][1], "Unlikely")
        # never promoted: better_option leaves a stronger_net option to the buyer
        d.pop("overrides")
        B = r["B"]
        B["overrides"] = {}
        rec = r["terms"]["recommended"]
        variants, _, by_net = strategy.option_set(B, r["costs"], rec)
        self.assertTrue(by_net)
        _, O = strategy.run_engine(B, r["costs"], variants)
        self.assertNotEqual(strategy.better_option(B, r["costs"], dict(variants), O, lvl, promote_stronger=False), "stronger")
        self.assertEqual(strategy.better_option(B, r["costs"], dict(variants), O, lvl), "stronger")

    def test_when_nothing_fits_the_limit_is_named(self):
        r = run(fixture("fha-competitive.json"))
        why = r["absent"]["stronger"]
        self.assertIn("Nothing stronger fits within your limits, since", why)
        self.assertIn("reserve floor", why)
        self.assertNotIn("nothing more would make", why)
        self.assertEqual(why.count(":"), 0)


class MarketRead(unittest.TestCase):
    def test_tight_market_is_never_soft(self):
        """The CMA said inventory is tight (1.4 months) and the leverage is the home's price; the offer report said
        Market Read: Soft. The market and the listing are read apart now."""
        r = run(fixture())
        read = next(m for m in strategy.market_check(r["B"]) if m["label"] == "Market Read")
        self.assertEqual(read["value"], "Tight market, stale listing")
        self.assertIn("Market tight (1.4 months of supply", read["note"])
        self.assertIn("this home stale (78 days on market vs. a 23-day median, 2 price cuts)", read["note"])
        self.assertIn("leverage comes from this home's price, not the market", read["note"])
        self.assertNotIn("soft", read["note"].lower())
        self.assertNotEqual(strategy.market_heat({"dom": 78, "price_cuts": 2}, {"months_supply": 1.4, "median_dom": 23})[0],
                            "soft")

    def test_inferred_competition_names_the_listing_not_the_market(self):
        d = fixture()
        d["competition"] = {}
        r = run(d)
        self.assertEqual(r["B"]["competition"]["level"], 0)  # a stale listing still reads as no competing offers
        s = strategy.summary(r)
        self.assertIn("this home reads stale", s["signal"])
        self.assertNotIn("market reads soft", s["signal"])

    def test_area_reads(self):
        self.assertEqual(strategy.area_read({"months_supply": 4.2}), "balanced")
        self.assertEqual(strategy.area_read({"months_supply": 7.5}), "soft")
        self.assertEqual(strategy.area_read({"sale_to_list": 0.995}), "hot")
        self.assertIsNone(strategy.area_read({}))
        self.assertEqual(strategy.market_read({"property": {}, "market": {}}), ("—", None))


class Wording(unittest.TestCase):
    def setUp(self):
        self.r = run(fixture())
        self.doc = offer_render.options_html(self.r, {}, False)
        self.text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", self.doc))

    def test_smaller_ask_says_smaller_than_what(self):
        self.assertEqual(self.r["why"]["seller_concessions"],
                         "A smaller ask than the area's typical $6,000: it nets the seller more and lifts the outlook")

    def test_closing_cost_estimate_said_once(self):
        self.assertEqual(self.text.count("3.0% of price plus loan taxes"), 1)
        d = fixture()
        d["buyer"]["closing_cost_pct"] = 0.035  # given, so not an assumption: the footer says it instead
        r = run(d)
        text = re.sub(r"<[^>]+>", " ", offer_render.options_html(r, {}, False))
        self.assertEqual(text.count("3.5% of price"), 1)

    def test_one_worst_case_cash_label(self):
        self.assertNotIn("Worst Cash", self.text)
        self.assertIn("Worst-Case Cash", self.text)


class AcceptanceDate(unittest.TestCase):
    def test_dates_count_from_the_time_for_acceptance_day(self):
        """Today Sat Sep 26: the Time for Acceptance is Mon Sep 28, 5:00 PM, so the dates count from Mon Sep 28, not
        from Sun Sep 27."""
        r = run(fixture())
        self.assertEqual(r["B"]["effective_date"], strategy.date(2026, 9, 28))
        rows = {x["field"]: x["entry"] for x in strategy.worksheet(r)["rows"]}
        self.assertEqual(rows["Time for Acceptance"], "September 28, 2026, 5:00 PM")
        a = next(x for x in r["missing"] if x["field"] == "expected_effective_date")
        self.assertIn("Mon Sep 28, the first business day after today", a["why"])
        close = r["B"]["effective_date"] + strategy.timedelta(days=r["terms"]["recommended"]["closing_days"])
        self.assertTrue(strategy.dates.is_business_day(close))

    def test_a_weekday_day_after_stays(self):
        d = fixture()
        d["analysis_date"] = "2026-09-29"
        r = run(d)
        self.assertEqual(r["B"]["effective_date"], strategy.date(2026, 9, 30))


class Checklist(unittest.TestCase):
    def test_riders_carry_their_letters(self):
        r = run(fixture())
        item = next(p["item"] for p in strategy.worksheet(r)["package"] if p["item"].startswith("Riders attached"))
        for code in ("(B)", "(F)", "(H)", "(GG)"):
            self.assertIn(code, item)


class ReplyAssumptions(unittest.TestCase):
    def test_reply_names_the_assumptions_in_one_line(self):
        res = strategy.result(run(fixture()))
        line = next(x["text"] for x in res["reply_lines"] if x["key"] == "assumptions")
        self.assertTrue(line.startswith("Assumed in these numbers: "))
        for words in ("closing costs at 3.0% of price plus loan taxes", "no flood insurance in the payment",
                      "acceptance on Mon Sep 28", "tax proration"):
            self.assertIn(words, line)
        self.assertNotIn("\n", line)
        self.assertNotIn("buyer-broker", line.lower())  # asked by the reply's question instead

    def test_nothing_assumed_no_line(self):
        r = run(fixture())
        r = copy.copy(r)
        r["missing"] = []
        self.assertIsNone(strategy.assumed_line(r))


if __name__ == "__main__":
    unittest.main()
