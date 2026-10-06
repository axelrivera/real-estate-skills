"""seller-cma: the home's own listing. A live listing is a question first (ask, reprice, failed or history); the agent's
own listing is priced as a reprice (Stay at Current Price plus cuts); a listing that ended unsold caps a relist."""
import contextlib
import copy
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from test_seller_cma import (ROOT, AGENT, compute, report, reprice, run, seller_render, stats_mod,  # noqa: E402
                             texas)

SAMPLE = os.path.join(ROOT, "dev", "samples", "mls-export.csv")
EVAL_EXPORT = os.path.join(ROOT, "dev", "evals", "seller-cma", "files", "export-spring-oaks.csv")  # expired at $474,900
EVAL_ACTIVE = os.path.join(ROOT, "dev", "evals", "seller-cma", "files", "export-spring-oaks-active.csv")  # listed at $474,900


def stats_main(args):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = stats_mod.main(args)
    return code, json.loads(out.getvalue())


def stats(rows, *extra, head_extra=()):
    """stats.py on the sample export with the subject's own rows replaced by `rows`."""
    with open(SAMPLE, newline="") as f:
        data = list(csv.reader(f))
    head = data[0] + list(head_extra)
    body = [r + [""] * len(head_extra) for r in data[1:] if r[3] != "517 LARKWOOD AVE"]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "export.csv")
        with open(path, "w", newline="") as f:
            csv.writer(f).writerows([head] + body + rows)
        return stats_main([path, "--address", "517 LARKWOOD AVE", "--sqft", "1849", "--mls", "Stellar", *extra])[1]


def subject_row(status, extra=()):
    return ["0.00", "X7000001", status, "517 LARKWOOD AVE", "FERNWOOD PARK UNIT 2", "1849", "$474,900", "", "",
            "$484,900", "", "4", "2", "1972", "Private", "36", "", "0.22", "", ""] + list(extra)


FL = ("--state", "FL", "--county", "Seminole")


class ListedNow(unittest.TestCase):
    def test_live_listing_actions(self):
        for status in ("ACT", "PND"):
            r = stats([subject_row(status)], *FL)
            self.assertTrue(r["listed_now"], status)
            self.assertEqual(r["listed_now_action"], "ask")
            self.assertNotIn("relist", r)
        self.assertEqual(stats([subject_row("ACT")], *FL, "--own-listing")["listed_now_action"], "reprice")
        r = stats([subject_row("PND")], *FL, "--listed-as", "failed")
        self.assertEqual(r["listed_now_action"], "relist")
        self.assertEqual((r["relist"]["failed_price"], r["relist"]["status"], r["relist"]["original_price"]),
                         (474900, "pending", 484900))
        self.assertNotIn("reprice", r)
        r = stats([subject_row("ACT")], *FL, "--listed-as", "history")
        self.assertEqual(r["listed_now_action"], "history")
        self.assertNotIn("relist", r)
        self.assertNotIn("reprice", r)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            stats([subject_row("ACT")], "--own-listing", "--listed-as", "failed")

    def test_history_location_and_layout(self):
        sold = subject_row("SLD")
        sold[7:9] = ["$289,000", "06/14/2019"]
        self.assertFalse(stats([sold], *FL)["listed_now"])
        self.assertFalse(stats([], *FL)["listed_now"])
        self.assertFalse(stats_main([SAMPLE, "--address", "517 LARKWOOD AVE", "--sqft", "1849", *FL])[1]["listed_now"])
        r = stats([subject_row("EXP", ("Altamonte Springs", "Seminole"))], head_extra=("City", "CountyOrParish"))
        self.assertEqual(r["subject_location"], {"city": "Altamonte Springs", "county": "Seminole"})
        self.assertIsNone(stats([subject_row("EXP")])["subject_location"])
        code, out = stats_main([EVAL_EXPORT, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--state", "FL"])
        self.assertEqual(code, 1)
        self.assertIn("--mls Stellar", out["problems"][0])
        self.assertEqual(stats_mod.builtin_layout(EVAL_EXPORT), "Stellar")

    def test_failed_listings(self):
        """An undated failed listing is named; one that ended over 12 months ago sets no cap."""
        self.assertEqual(stats([subject_row("EXP")], *FL)["undated_history"], ["517 LARKWOOD AVE (expired at $474,900)"])
        self.assertEqual(stats([], *FL)["undated_history"], [])
        old = subject_row("EXP")
        old[8] = "09/30/2017"
        self.assertNotIn("relist", stats([old], *FL, "--as-of", "2026-09-26"))
        recent = subject_row("EXP")
        recent[8] = "03/15/2026"
        self.assertEqual(stats([recent], *FL, "--as-of", "2026-09-26")["relist"]["failed_price"], 474900)
        self.assertTrue(compute.mls.ended_within({"close_date": date(2026, 1, 5)}, date(2026, 9, 26)))
        self.assertFalse(compute.mls.ended_within({"close_date": date(2017, 9, 30)}, date(2026, 9, 26)))
        self.assertTrue(compute.mls.ended_within({}, date(2026, 9, 26)))  # undated counts


class Reprice(unittest.TestCase):
    def test_stay_then_cuts_only(self):
        """Stay at Current Price first, then cuts at least 1% under it; no top-of-range option, even when the current
        price sits inside the range. The agent asking to price it higher lifts the cap; when the stance's price meets
        the current one, staying is the recommendation."""
        R = reprice()
        R["reprice"].pop("days_on_market")
        with self.assertRaises(compute.ReportError):
            run(R)
        for current in (469900, 479900, 489900):
            with self.subTest(current=current):
                R = reprice(current=current)
                C, _ = run(R)
                roles = [x["role"] for x in C["strategies"]]
                self.assertEqual((roles[0], C["strategies"][0]["list_price"]), ("stay", current))
                self.assertNotIn("top", roles)
                self.assertTrue(all(x["list_price"] <= current * 0.99 for x in C["strategies"][1:]))
                self.assertLessEqual({"current_price": current, "days_on_market": 60, "stay_index": 0}.items(),
                                     C["reprice"].items())
                for stance in ("draw_offers", "premium"):  # never above the cap, whatever the stance
                    R["pricing"]["stance"] = stance
                    self.assertTrue(all(x["list_price"] <= current * 0.99 for x in run(R)[0]["strategies"][1:]))
        R = reprice(current=469900)
        R["reprice"]["allow_increase"] = True  # the market stance's price is the current one: stay is the recommendation
        C, _ = run(R)
        self.assertEqual(C["recommended_index"], 0)
        self.assertTrue(C["strategies"][0]["stay"] and C["strategies"][0]["recommended"])
        R = reprice(current=469900)
        R["price_override"] = {"list_price": 469000, "reason": "The agent's own price."}  # not a 1% cut
        with self.assertRaisesRegex(compute.ReportError, r"price_override\.list_price"):
            run(R)
        R = reprice(current=456000)  # no cut left inside the range
        with self.assertRaisesRegex(compute.ReportError, r"reprice: "):
            run(R)

    def test_output(self):
        R = reprice(current=489900)
        R["reprice"]["days_on_market"] = 74
        C, homes = run(R)
        self.assertEqual([x["role"] for x in C["strategies"]], ["stay", "recommended", "competing"])
        self.assertTrue(C["strategies"][1]["recommended"])
        self.assertEqual(C["summary"]["first_heading"], compute.word("sum_first", True))  # the reprice's own labels
        self.assertNotEqual(C["summary"]["first_heading"], run(report())[0]["summary"]["first_heading"])
        self.assertEqual(C["strategies"][0]["label"], compute.t("strategy_stay", price="$489,900"))
        self.assertIsNone(run(report())[0]["reprice"])
        R["pricing"]["options"]["competing"] = {"expected_sale": 461000}  # the competing-offer option may sell above list
        run(R)

    def test_stay_expected_sale_rule(self):
        """Current price x the ratio of sales that sat as long, or the median adjusted value if lower, plus its credit;
        a higher figure warns, a missing one is filled. Stay netting more says so in the notes, or warns on the
        agent's own figures."""
        R = reprice()
        C, _ = run(R)
        rp = C["reprice"]
        expected = min(479900 * rp["stay_ratio"], C["median_adjusted"]) + R["pricing"]["options"]["stay"]["seller_credit"]
        self.assertAlmostEqual(rp["stay_expected_sale"], expected, delta=600)
        self.assertGreaterEqual(rp["stay_ratio_sales"], 3)
        R["pricing"]["options"]["stay"]["expected_sale"] = rp["stay_expected_sale"] + 5000
        self.assertIn("stay_expected_high", run(R)[0]["warning_keys"])
        R["pricing"]["options"]["stay"].pop("expected_sale")
        C, _ = run(R)
        self.assertEqual(C["strategies"][0]["expected_sale"], rp["stay_expected_sale"])
        self.assertTrue(C["reprice"]["stay_expected_filled"])
        self.assertNotIn("stay_expected_high", C["warning_keys"])
        R = texas(reprice())  # no export: nothing to derive it from
        self.assertNotIn("stay_expected_sale", run(copy.deepcopy(R))[0]["reprice"])
        R["pricing"]["options"]["stay"].pop("expected_sale")
        with self.assertRaisesRegex(compute.ReportError, r"options\.stay\.expected_sale"):
            run(R)
        R = reprice()
        R["pricing"]["options"]["stay"].update(expected_sale=475000, time="1–2 months")
        C, _ = run(R)
        self.assertIn("stay_nets_more", C["warning_keys"])
        self.assertIn("stay_caveat", C["note_keys"])
        R["pricing"].pop("options")  # the script's own Stay figures: the notes say it, nothing to fix
        C, _ = run(R)
        nets = [x["net_after_holding"] for x in C["strategies"]]
        self.assertNotIn("stay_nets_more", C["warning_keys"])
        self.assertEqual("stay_caveat" in C["note_keys"], nets[0] > nets[C["recommended_index"]])

    def test_asks_for_the_listing_agreement(self):
        R = reprice()
        R["costs"] = {}
        C, _ = run(R)
        self.assertIn("commission_default", C["assumption_keys"])
        self.assertEqual(len(C["assumptions"]), len(C["assumption_keys"]))
        self.assertNotIn("commission_default", run(reprice())[0]["assumption_keys"])

    def test_price_history(self):
        """The original price comes from report.json or the export's own row; no cut, no history."""
        code, r = stats_main([EVAL_ACTIVE, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar",
                              *FL, "--own-listing"])
        self.assertEqual(r["reprice"], {"current_price": 474900, "days_on_market": 36, "original_price": 484900})
        R = reprice(current=474900)
        R["export"] = EVAL_ACTIVE
        R["reprice"]["days_on_market"] = 36
        C, homes = run(R)
        self.assertEqual((C["reprice"]["original_price"], C["reprice"]["original_price_display"]), (484900, "$484,900"))
        for price in ("$484,900", "$474,900"):
            self.assertIn(price, C["price_history"])
        self.assertIn(C["price_history"], seller_render.build_html(C, AGENT).replace("&#x27;", "'"))
        R = reprice(current=474900)
        R.pop("export")
        R["reprice"]["original_price"] = 484900
        self.assertEqual(run(R)[0]["reprice"]["original_price"], 484900)
        R["reprice"]["original_price"] = 474900
        C, _ = run(R)
        self.assertIsNone(C["reprice"]["original_price"])


class Relist(unittest.TestCase):
    def test_failed_price_caps_the_options(self):
        """No option above the failed price unless the agent gave a reason; a top option the cap squeezes within 1% of
        the recommended price is dropped; a failed price under the range stops for the agent's call."""
        R = report()
        R["relist"] = {"failed_price": 474900, "status": "expired", "days_on_market": 92}
        C, _ = run(R)
        listed = [x["list_price"] for x in C["strategies"]]
        self.assertEqual(max(listed), 470000)
        R["relist"]["failed_price"] = 475000  # a failed price on a step: the step under it, never the price itself
        self.assertEqual(max(x["list_price"] for x in run(R)[0]["strategies"]), 470000)
        R["relist"]["failed_price"] = 474900
        self.assertEqual((C["relist"]["source"], C["relist"]["failed_price_display"]), ("report", "$474,900"))
        self.assertIn("$474,900", C["price_history"])
        R["relist"]["reason_above"] = "The kitchen and baths were redone after that listing ended."
        self.assertGreater(max(x["list_price"] for x in run(R)[0]["strategies"]), 474900)
        R = report()
        R["relist"] = {"failed_price": 472900}  # the cap leaves no distinct option above the recommended price
        C, _ = run(R)
        self.assertEqual([x["role"] for x in C["strategies"]], ["recommended", "competing"])
        self.assertEqual(C["recommended_index"], 0)
        R["pricing"]["stance"] = "premium"  # the stance's price is capped too
        self.assertTrue(all(x["list_price"] <= 472900 for x in run(R)[0]["strategies"]))
        R = report()
        R["relist"] = {"failed_price": 455000}  # no bracket step under it inside the range: at the failed price
        self.assertEqual(run(R)[0]["recommendation"]["list_price"], 455000)
        R["relist"]["failed_price"] = 445000  # under the range: the agent decides
        with self.assertRaisesRegex(compute.ReportError, r"relist\.reason_above"):
            run(R)
        R["price_override"] = {"list_price": 444900, "reason": "The agent's own price."}
        self.assertEqual(run(R)[0]["recommendation"]["list_price"], 444900)
        R["price_override"]["list_price"] = 459900  # the agent's price above the failed one still needs the reason
        with self.assertRaisesRegex(compute.ReportError, r"relist\.reason_above"):
            run(R)
        R = reprice(current=474900)  # a reprice has its own rule
        R["relist"] = {"failed_price": 469900}
        self.assertIsNone(run(R)[0]["relist"])

    def test_found_in_the_export(self):
        R = report()
        R["export"] = EVAL_EXPORT
        C, _ = run(R)
        self.assertEqual((C["relist"]["failed_price"], C["relist"]["status"], C["relist"]["source"]),
                         (474900, "expired", "export"))
        self.assertTrue(all(x["list_price"] <= 474900 for x in C["strategies"]))
        self.assertEqual((C["relist"]["original_price"], C["relist"]["original_price_display"]), (484900, "$484,900"))
        _, r = stats_main([EVAL_EXPORT, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar", *FL])
        self.assertEqual((r["relist"]["failed_price"], r["relist"]["status"], r["mls"]), (474900, "expired", "Stellar"))
        self.assertNotIn("relist", stats([subject_row("ACT")], "--own-listing"))


if __name__ == "__main__":
    unittest.main()
