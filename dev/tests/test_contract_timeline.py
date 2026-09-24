"""Tests for plugins/transactions/skills/contract-timeline/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCRIPTS = os.path.join(ROOT, "plugins", "transactions", "skills", "contract-timeline", "scripts")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

timeline, timeline_render, dates = load("contract-timeline", "timeline", "render", "_shared.dates")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def by_key(result):
    return {r["key"]: r for r in result["rows"] + result["pending"]}


class Holidays(unittest.TestCase):
    def test_observed_and_moving_holidays(self):
        self.assertEqual(dates.holiday_name(date(2026, 7, 3)), "Independence Day (observed)")  # July 4 2026 is a Saturday
        self.assertEqual(dates.holiday_name(date(2026, 11, 26)), "Thanksgiving Day")
        self.assertEqual(dates.holiday_name(date(2027, 12, 24)), "Christmas Day (observed)")
        self.assertFalse(dates.is_business_day(date(2026, 9, 7)))  # Labor Day

    def test_business_day_counting(self):
        self.assertEqual(dates.add_business_days(date(2026, 9, 25), 3), date(2026, 9, 30))
        self.assertEqual(dates.add_business_days(date(2026, 10, 30), -3), date(2026, 10, 27))


class FrbarMatchesPrototype(unittest.TestCase):
    """Dates from the prototype's buyer sample PDF (FHA, AS IS, effective 2026-09-25)."""
    EXPECTED = {
        "deposit": "2026-09-30 23:59", "loan_app": "2026-10-02 23:59", "inspection": "2026-10-05 23:59",
        "insurance": "2026-10-05 23:59", "appraisal": "2026-10-16 23:59", "title": "2026-10-23 17:00",
        "survey": "2026-10-23 17:00", "insurance_bound": "2026-10-23 17:00", "loan_approval": "2026-10-26 17:00",
        "clear_to_close": "2026-10-27 17:00", "walkthrough": "2026-10-29 17:00", "closing": "2026-10-30 10:00",
    }

    def test_every_date(self):
        r = timeline.analyze(fixture("buyer-fha.json"))
        rows = by_key(r)
        self.assertEqual({k: rows[k]["when"] for k in self.EXPECTED}, self.EXPECTED)
        self.assertEqual(rows["deposit"]["day"], 5)
        self.assertEqual(r["contingencies_end"]["key"], "loan_approval")
        self.assertEqual(r["first_deadline"]["key"], "deposit")
        self.assertIn("Loan approval deadline is within 5 days of closing", r["flags"][0])
        self.assertEqual(rows["closing"]["source"], "Para. 4 · possession Para. 6")

    def test_rider_words_and_agent_notes(self):
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c.pop("appraisal_days", None)
        c["riders"] = ["Private Well and Septic", "Vacant Land"]
        c["financing"] = "conventional"
        c.pop("closing_time", None)
        r = timeline.analyze(deal)
        self.assertNotIn("appraisal", by_key(r))  # "va" is a whole word, not part of "private"
        self.assertTrue(any("Closing time isn't stated" in n for n in r["agent_notes"]))
        self.assertFalse(any("Closing time" in f for f in r["flags"]))
        self.assertFalse(any("MLS" in n for n in r["agent_notes"]))
        c["riders"] = ["FHA/VA Financing"]
        self.assertIn("appraisal", by_key(timeline.analyze(deal)))

    def test_cash_drops_loan_deadlines(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["financing"] = "cash"
        keys = set(by_key(timeline.analyze(deal)))
        self.assertFalse(keys & {"loan_app", "loan_approval", "appraisal", "insurance_bound", "clear_to_close"})

    def test_standard_contract_adds_repair_notice(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["contract_form"] = "standard"
        rows = by_key(timeline.analyze(deal))
        self.assertIn("repair_notice", rows)
        self.assertEqual(rows["inspection"]["label"], "Inspection Period Ends")


class Amendments(unittest.TestCase):
    def test_moved_dates_show_was(self):
        r = timeline.analyze(fixture("seller-amended.json"))
        rows = by_key(r)
        self.assertEqual(rows["closing"]["when"], "2026-12-18 10:00")
        self.assertEqual(rows["closing"]["was"], "Fri Dec 11 · 10:00 AM")
        self.assertEqual(rows["appraisal"]["when"], "2026-11-25 17:00")
        self.assertIsNone(rows["deposit"]["was"])
        self.assertIn("loan approval days: blank → 38", r["history"][0]["summary"])
        self.assertIsNone(rows["hoa_docs"]["when"])  # on event until received
        self.assertIn("lead_paint", rows)  # built 1972

    def test_hoa_received_starts_review_window(self):
        deal = fixture("seller-amended.json")
        deal["contract"]["hoa_docs_received"] = "2026-11-06"
        self.assertEqual(by_key(timeline.analyze(deal))["hoa_docs"]["when"], "2026-11-12 23:59")  # Mon, Tue, (Veterans Day), Thu


class OtherContracts(unittest.TestCase):
    def test_texas_uses_its_own_rules_and_deadlines(self):
        r = timeline.analyze(fixture("texas-trec.json"))
        rows = by_key(r)
        self.assertEqual(rows["option_period"]["when"], "2026-11-27 17:00")  # 7 calendar days, 5 PM
        self.assertEqual(rows["earnest_money"]["when"], "2026-11-23 17:00")  # 3 calendar days: Mon (no short-period rule)
        self.assertEqual(r["contingencies_end"]["key"], "financing")
        self.assertNotIn("deposit", rows)  # no FR/BAR deadlines
        self.assertEqual(r["rules"]["family"], "the contract's definitions")

    def test_other_state_without_rules_is_refused(self):
        deal = fixture("texas-trec.json")
        del deal["rules"]
        with self.assertRaises(timeline.DealError) as e:
            timeline.analyze(deal)
        self.assertIn("time rules are missing", str(e.exception))

    def test_other_contract_needs_deadlines(self):
        deal = fixture("texas-trec.json")
        del deal["deadlines"]
        with self.assertRaises(timeline.DealError):
            timeline.analyze(deal)

    def test_market_profile_rules(self):
        deal = fixture("texas-trec.json")
        rules = deal.pop("rules")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tx.md")
            with open(path, "w") as f:
                f.write("---\nprofile: market\nstate: TX\ncontract:\n" +
                        "".join(f"  {k}: {json.dumps(v)}\n" for k, v in rules.items()) + "---\n")
            r = timeline.analyze(deal, market_path=path)
        self.assertEqual(by_key(r)["option_period"]["when"], "2026-11-27 17:00")


class Required(unittest.TestCase):
    def test_state_required(self):
        """TL-4: no state is a question for the agent, never Florida by default."""
        deal = fixture("buyer-fha.json")
        del deal["state"]
        with self.assertRaisesRegex(timeline.DealError, "state"):
            timeline.analyze(deal)

    def test_florida_builder_contract_gets_no_frbar_rules(self):
        """TL-4: a Florida contract that isn't FR/BAR uses only the rules in the deal file."""
        deal = fixture("texas-trec.json")
        deal.update(state="FL", county="Orange")
        deal["contract"]["form"] = "Builder Purchase Agreement"
        deal.pop("rules")
        with self.assertRaisesRegex(timeline.DealError, "time rules are missing"):
            timeline.analyze(deal)

    def test_effective_date_required(self):
        deal = fixture("buyer-fha.json")
        del deal["contract"]["effective_date"]
        with self.assertRaises(timeline.DealError):
            timeline.analyze(deal)

    def test_quick_question_without_closing_date(self):
        deal = fixture("buyer-fha.json")
        del deal["contract"]["closing_date"]
        r = timeline.analyze(deal)
        self.assertIsNone(r["closing"])
        self.assertIn("walkthrough", {x["key"] for x in r["pending"]})  # counted back from closing: waits for the date
        self.assertIn("deposit", {x["key"] for x in r["rows"]})

    def test_per_deadline_time_and_no_rollover(self):
        deal = fixture("texas-trec.json")
        deal["contract"]["effective_date"] = "2026-11-21"
        deal["deadlines"] = [{"key": "option", "label": "Option Period Ends", "basis": "after", "days": 7, "party": "Buyer",
                              "time": "17:00", "rollover": False}]
        deal["contract"].pop("date_overrides", None)
        row = by_key(timeline.analyze(deal))["option"]
        self.assertEqual(row["when"], "2026-11-28 17:00")  # a Saturday: this deadline isn't extended

    def test_cli_reports_problems_as_json(self):
        deal = fixture("buyer-fha.json")
        del deal["contract"]["effective_date"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deal.json")
            with open(path, "w") as f:
                json.dump(deal, f)
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = timeline.main([path])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.getvalue())["ok"])


class Pdf(unittest.TestCase):
    def test_render_uses_brand_and_side(self):
        agent = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None,
                 "brand": {"primary": "#0B6E4F"}}
        t = timeline.analyze(fixture("seller-amended.json"))
        doc = timeline_render.build_html(t, agent, sample=True)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Seller View", doc)
        self.assertIn("SAMPLE DATA", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)  # no license in the profile: nothing printed
        self.assertIn("was Fri Dec 11", doc)


if __name__ == "__main__":
    unittest.main()
