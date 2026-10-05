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
    def test_validation(self):
        R = reprice()
        R["pricing"]["strategies"].pop(0)
        R["pricing"]["recommended_index"] = 0
        with self.assertRaises(compute.ReportError):
            run(R)
        R = reprice()
        R["reprice"].pop("days_on_market")
        with self.assertRaises(compute.ReportError):
            run(R)
        R = reprice(current=469900)  # inside the range: a top-of-range option would be a raise
        R["pricing"]["strategies"] = [R["pricing"]["strategies"][0]] + report()["pricing"]["strategies"]
        R["pricing"]["recommended_index"] = 2
        R["pricing"]["strategies"][2]["list_price"] = 464900
        R["recommendation"]["list_price"] = 464900
        with self.assertRaisesRegex(compute.ReportError, "cuts only"):
            run(R)
        R["reprice"]["allow_increase"] = True
        run(R)

    def test_output(self):
        R = report()
        stay = {"label": "Stay at $489,900", "list_price": 489900, "expected_sale": 462000, "time": "60–120 days",
                "seller_credit": 10000, "note": "Has sat 74 days at this price"}
        R["pricing"]["strategies"].insert(0, stay)
        R["pricing"]["recommended_index"] = 2
        R["reprice"] = {"current_price": 489900, "days_on_market": 74}
        C, homes = run(R)
        self.assertLessEqual({"current_price": 489900, "days_on_market": 74, "stay_index": 0}.items(), C["reprice"].items())
        self.assertEqual(len(C["strategies"]), 4)
        self.assertTrue(C["strategies"][2]["recommended"])
        self.assertEqual(C["first_steps_heading"], compute.labels(R)("sum_first"))  # the reprice's own labels
        self.assertNotEqual(C["first_steps_heading"], run(report())[0]["first_steps_heading"])
        self.assertIsNone(run(report())[0]["reprice"])
        R["pricing"]["strategies"][3]["expected_sale"] = 461000  # the competing-offer option (last) may sell above list
        run(R)

    def test_stay_expected_sale_rule(self):
        """Current price x the ratio of sales that sat as long, or the median adjusted value if lower, plus its credit;
        a higher figure warns, a missing one is filled."""
        R = reprice()
        C, _ = run(R)
        rp = C["reprice"]
        expected = min(479900 * rp["stay_ratio"], C["median_adjusted"]) + R["pricing"]["strategies"][0]["seller_credit"]
        self.assertAlmostEqual(rp["stay_expected_sale"], expected, delta=600)
        self.assertGreaterEqual(rp["stay_ratio_sales"], 3)
        R["pricing"]["strategies"][0]["expected_sale"] = rp["stay_expected_sale"] + 5000
        self.assertIn("stay_expected_high", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"][0].pop("expected_sale")
        C, _ = run(R)
        self.assertEqual(C["strategies"][0]["expected_sale"], rp["stay_expected_sale"])
        self.assertTrue(C["reprice"]["stay_expected_filled"])
        self.assertNotIn("stay_expected_high", C["warning_keys"])
        R = texas(reprice())  # no export: nothing to derive it from
        self.assertNotIn("stay_expected_sale", run(copy.deepcopy(R))[0]["reprice"])
        R["pricing"]["strategies"][0].pop("expected_sale")
        with self.assertRaises(compute.ReportError):
            run(R)
        R = reprice()
        R["pricing"]["strategies"][0].update(expected_sale=475000, time="1–2 months")
        self.assertIn("stay_nets_more", run(R)[0]["warning_keys"])

    def test_asks_for_the_listing_agreement(self):
        R = reprice()
        R["costs"] = {}
        C, _ = run(R)
        self.assertIn("brokerage_listing_agreement", C["assumption_keys"])
        self.assertNotIn("brokerage_assumed", C["assumption_keys"])
        self.assertEqual(len(C["assumptions"]), len(C["assumption_keys"]))
        self.assertFalse({"brokerage_listing_agreement", "brokerage_assumed"} & set(run(reprice())[0]["assumption_keys"]))

    def test_price_history(self):
        """The original price comes from report.json or the export's own row; no cut, no history."""
        code, r = stats_main([EVAL_ACTIVE, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar",
                              *FL, "--own-listing"])
        self.assertEqual(r["reprice"], {"current_price": 474900, "days_on_market": 36, "original_price": 484900})
        R = reprice(current=474900)
        R["export"] = EVAL_ACTIVE
        R["reprice"]["days_on_market"] = 36
        R["means"] = ["It started at {original_price}."]
        C, homes = run(R)
        self.assertEqual((C["reprice"]["original_price"], C["placeholders"]["original_price"]), (484900, "$484,900"))
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        for price in ("$484,900", "$474,900"):
            self.assertIn(price, C["reprice"]["price_history"])
        doc, _ = seller_render.build_html(R, C, homes, AGENT)
        self.assertIn(C["reprice"]["price_history"], doc)
        R = reprice(current=474900)
        R.pop("export")
        R["reprice"]["original_price"] = 484900
        self.assertEqual(run(R)[0]["reprice"]["original_price"], 484900)
        R["reprice"]["original_price"] = 474900
        C, _ = run(R)
        self.assertIsNone(C["reprice"]["original_price"])
        self.assertNotIn("original_price", C["placeholders"])


class Relist(unittest.TestCase):
    def test_failed_price_caps_the_options(self):
        R = report()
        R["relist"] = {"failed_price": 474900, "status": "expired", "days_on_market": 92}
        with self.assertRaisesRegex(compute.ReportError, "relist.reason_above"):
            run(R)  # the fixture's top-of-range option is $479,900
        R["relist"]["reason_above"] = "The kitchen and baths were redone after that listing ended."
        self.assertEqual(run(R)[0]["relist"]["failed_price"], 474900)
        R = report()
        R["relist"] = {"failed_price": 474900}
        R["pricing"]["strategies"][0]["list_price"] = 474900
        C, _ = run(R)
        self.assertEqual((C["relist"]["source"], C["placeholders"]["failed_price"]), ("report", "$474,900"))
        R = reprice(current=474900)  # a reprice has its own rule
        R["relist"] = {"failed_price": 469900}
        self.assertIsNone(run(R)[0]["relist"])
        R = report()
        R["relist"] = {"failed_price": 474900}
        R["pricing"]["strategies"][0]["list_price"] = 472900
        self.assertIn("top_near_recommended", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"][0]["list_price"] = 474900  # just over 1% above $469,900
        self.assertNotIn("top_near_recommended", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"].pop(0)
        R["pricing"]["recommended_index"] = 0
        C, _ = run(R)
        self.assertNotIn("top_near_recommended", C["warning_keys"])
        self.assertEqual(len(C["strategies"]), 2)

    def test_found_in_the_export(self):
        R = report()
        R["export"] = EVAL_EXPORT
        with self.assertRaises(compute.ReportError):
            run(R)
        R["pricing"]["strategies"][0]["list_price"] = 474900
        C, _ = run(R)
        self.assertEqual((C["relist"]["failed_price"], C["relist"]["status"], C["relist"]["source"]),
                         (474900, "expired", "export"))
        self.assertEqual((C["relist"]["original_price"], C["placeholders"]["original_price"]), (484900, "$484,900"))
        _, r = stats_main([EVAL_EXPORT, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar", *FL])
        self.assertEqual((r["relist"]["failed_price"], r["relist"]["status"], r["mls"]), (474900, "expired", "Stellar"))
        self.assertNotIn("relist", stats([subject_row("ACT")], "--own-listing"))


if __name__ == "__main__":
    unittest.main()
