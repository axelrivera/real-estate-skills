"""Tests for skills/contract-timeline/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCRIPTS = os.path.join(ROOT, "skills", "contract-timeline", "scripts")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

timeline, timeline_render, dates = load("contract-timeline", "timeline", "render", "_shared.dates")


def fixture(name):
    """A fixture deal, prepared on the day the fixtures assume (dev/golden.py) unless it sets its own report_date, so
    deadlines before the real today don't read as past (TL-104)."""
    with open(os.path.join(FIXTURES, name)) as f:
        deal = json.load(f)
    deal.setdefault("report_date", "2026-09-26")
    return deal


def by_key(result):
    return {r["key"]: r for r in result["rows"] + result["pending"]}


class Holidays(unittest.TestCase):
    def test_observed_and_moving_holidays(self):
        self.assertEqual(dates.holiday_name(date(2026, 7, 3)), "Independence Day (observed)")  # July 4 2026 is a Saturday
        self.assertEqual(dates.holiday_name(date(2026, 11, 26)), "Thanksgiving Day")
        self.assertEqual(dates.holiday_name(date(2027, 12, 24)), "Christmas Day (observed)")
        self.assertFalse(dates.is_business_day(date(2026, 9, 7)))  # Labor Day

    def test_saturday_new_years_observed_friday(self):
        """TL-5: Jan 1, 2028 and Jan 1, 2033 are Saturdays, observed Fri Dec 31 of the year before."""
        for d in (date(2027, 12, 31), date(2032, 12, 31)):
            self.assertEqual(dates.holiday_name(d), "New Year's Day (observed)")
            self.assertFalse(dates.is_business_day(d))
        self.assertTrue(dates.is_business_day(date(2026, 12, 31)))

    def test_business_day_counting(self):
        self.assertEqual(dates.add_business_days(date(2026, 9, 25), 3), date(2026, 9, 30))
        self.assertEqual(dates.add_business_days(date(2026, 10, 30), -3), date(2026, 10, 27))


class FrbarDates(unittest.TestCase):
    """Buyer FHA sample, AS IS, effective Fri 2026-09-25, closing Fri 2026-10-30. Hand-checked against ASIS-7x
    Rev. 2/26: calendar days, no short-period rule, a period ending on a weekend or holiday runs to the end of
    the next business day (Standard F), title evidence 15 days before closing when blank (Para. 9(c))."""
    EXPECTED = {
        "deposit": "2026-09-28 23:59", "loan_app": "2026-09-30 23:59", "inspection": "2026-10-05 23:59",
        "insurance": "2026-10-05 23:59", "title": "2026-10-15 23:59", "insurance_bound": "2026-10-23 23:59",
        "loan_approval": "2026-10-26 23:59", "survey": "2026-10-26 23:59", "clear_to_close": "2026-10-27 23:59",
        "seller_terminate": "2026-10-29 23:59", "walkthrough": "2026-10-29 23:59", "closing": "2026-10-30 10:00",
    }

    def test_blank_association_approval_box_assumes_required(self):
        d = fixture("buyer-fha.json")
        d["contract"]["association_approval"] = "unknown"
        d["contract"]["preapproval_expires"] = "2026-10-20"
        r = timeline.analyze(d)
        rows = by_key(r)
        self.assertIn("assoc_apply", rows)
        self.assertIn("assoc_approval", rows)
        self.assertTrue(any("approval box is blank" in f for f in r["flags"]))
        self.assertTrue(any("pre-approval expires" in n for n in r["agent_notes"]))

    def test_first_deadline_prefers_the_clients_own_rows(self):
        """TL-104: a compensation agreement the brokers sign isn't the buyer's first step while the buyer has one; a row
        both sides owe is the first deadline only when the client's side has none left."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"].get("riders") or []) + ["GG"]
        d["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(d)
        self.assertEqual((r["first_deadline"]["key"], r["first_deadline"]["party"]), ("loan_app", "Buyer"))
        o = fixture("other-contract.json")
        o["side"] = "seller"
        o["deadlines"][3]["party"] = "both"  # no seller row: the first row both sides owe
        self.assertEqual(timeline.analyze(o)["first_deadline"]["key"], "title_commitment")

    def test_past_deadlines_are_to_confirm(self):
        """TL-104: a deadline before the report date and not done is "Past, Confirm", never the first deadline, and
        stays out of the calendar; the agent note lists it."""
        d = fixture("buyer-fha.json")
        d["report_date"] = "2026-10-01"
        r = timeline.analyze(d)
        rows = by_key(r)
        self.assertTrue(rows["deposit"]["past"])
        self.assertEqual(rows["deposit"]["past_display"], "Past, Confirm")
        self.assertFalse(rows["inspection"]["past"])
        self.assertEqual(r["first_deadline"]["key"], "inspection")
        self.assertTrue(any("not recorded as done" in n and "Initial Escrow Deposit Due" in n for n in r["agent_notes"]))
        self.assertNotIn("UID:deposit-", timeline_render.ics(r))
        self.assertIn("Past, Confirm", timeline_render.build_html(r, {}, sample=True))
        d["completed"] = {"deposit": "2026-09-27"}
        self.assertFalse(by_key(timeline.analyze(d))["deposit"]["past"])

    def test_every_date(self):
        r = timeline.analyze(fixture("buyer-fha.json"))
        rows = by_key(r)
        self.assertEqual({k: rows[k]["when"] for k in self.EXPECTED}, self.EXPECTED)
        self.assertEqual(rows["deposit"]["day"], 3)
        self.assertNotIn("appraisal", rows)  # TL-3: the FHA/VA rider has no appraisal period
        self.assertTrue(any(f.startswith("FHA/VA rider") for f in r["flags"]))
        self.assertEqual(r["contingencies_end"]["key"], "loan_approval")
        self.assertEqual(r["first_deadline"]["key"], "deposit")
        self.assertTrue(any("Loan approval deadline is within 5 days of closing" in f for f in r["flags"]))
        self.assertTrue(any("Title evidence deadline blank" in n for n in r["agent_notes"]))
        self.assertEqual(rows["closing"]["source"], "Para. 4 · possession Para. 6")
        # TL-120: the FHA/VA election to proceed waits for the appraisal
        self.assertEqual({x["key"] for x in r["pending"]}, {"title_exam", "survey_notice", "fha_va_election"})

    def test_rider_words_and_agent_notes(self):
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c["riders"] = ["Private Well and Septic", "Vacant Land"]
        c["financing"] = "conventional"
        c.pop("closing_time", None)
        r = timeline.analyze(deal)
        self.assertNotIn("appraisal", by_key(r))  # "va" is a whole word, not part of "private"
        self.assertFalse(any(f.startswith("FHA/VA") for f in r["flags"]))
        self.assertTrue(any("Closing time isn't stated" in n for n in r["agent_notes"]))
        self.assertFalse(any("Closing time" in f for f in r["flags"]))
        self.assertFalse(any("MLS" in n for n in r["agent_notes"]))
        c["riders"] = ["Appraisal Contingency"]
        self.assertIn("appraisal", by_key(timeline.analyze(deal)))

    def test_cash_title_default_is_5_days(self):
        """TL-2: 15 days before closing, or 5 when the deal is cash."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["financing"] = "cash"
        self.assertEqual(by_key(timeline.analyze(deal))["title"]["when"], "2026-10-26 23:59")  # Sun Oct 25 extends

    def test_weekend_closing_extends(self):
        """TL-6, TL-8: a Saturday closing extends to Monday, and dates counted back from closing follow it."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-10-31"
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["closing"]["when"], "2026-11-02 10:00")
        self.assertIn("closing extends to Mon Nov 2", rows["closing"]["note"])
        self.assertEqual(rows["walkthrough"]["when"], "2026-11-02 10:00")  # Sun extends to closing day, before closing
        deal["contract"]["closing_date"] = "2026-10-30"
        deal["contract"]["date_overrides"] = {"closing": "2026-11-06"}
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["closing"]["when"], "2026-11-06 10:00")
        self.assertEqual(rows["walkthrough"]["when"], "2026-11-05 23:59")

    def test_date_only_override_rolls_forward(self):
        """TL-7: a date-only override on a Saturday extends; one with a time is kept."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["date_overrides"] = {"inspection": "2026-10-10", "deposit": "2026-09-27 15:00"}
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["inspection"]["when"], "2026-10-13 23:59")  # Sat, Sun, Columbus Day Mon
        self.assertEqual(rows["deposit"]["when"], "2026-09-27 15:00")

    def test_bad_inputs(self):
        """TL-9: closing before the Effective Date, or a negative period, is a plain error."""
        for change in ({"closing_date": "2026-09-20"}, {"inspection_days": -3}):
            deal = fixture("buyer-fha.json")
            deal["contract"].update(change)
            with self.assertRaises(timeline.DealError):
                timeline.analyze(deal)

    def test_contingency_after_closing_is_flagged(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["inspection_days"] = 40
        r = timeline.analyze(deal)
        self.assertTrue(any("Inspection Period Ends (Right to Cancel) ends after closing" in f for f in r["flags"]))
        deal["contract"]["inspection_days"] = 10
        deal["contract"]["loan_approval_days"] = 40
        self.assertTrue(any("Loan approval period ends after closing" in f for f in timeline.analyze(deal)["flags"]))

    def test_association_rights_are_the_buyers(self):
        """TL-11: condo 7 business days (capped at closing), HOA 3 calendar days; both buyer contingencies."""
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c.update(riders=["Condominium Rider"], condo_docs_received="2026-10-22")
        row = by_key(timeline.analyze(deal))["condo_docs"]
        self.assertEqual((row["party"], row["contingency"], row["when"]), ("Buyer", True, "2026-10-30 10:00"))  # 7 bus. days > closing
        c["condo_docs_received"] = "2026-10-01"
        self.assertEqual(by_key(timeline.analyze(deal))["condo_docs"]["when"], "2026-10-13 23:59")  # skips Columbus Day
        c.update(riders=["Homeowners' Association"], condo_docs_received=None, hoa_docs_received="2026-10-01")
        row = by_key(timeline.analyze(deal))["hoa_docs"]
        self.assertEqual((row["party"], row["contingency"], row["when"]), ("Buyer", True, "2026-10-05 23:59"))  # Sun → Mon
        c["hoa_disclosure_before_contract"] = True
        self.assertNotIn("hoa_docs", by_key(timeline.analyze(deal)))

    def test_new_frbar_rows(self):
        """TL-12, TL-13, TL-23: survey and title notices from receipt, flood elevation, waived lead paint."""
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c.update(title_commitment_received="2026-10-14", survey_received="2026-10-27", flood_zone="AE",
                 seller_has_survey=True, year_built=1970, lbp_waived=True)
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["title_exam"]["when"], "2026-10-19 23:59")
        self.assertEqual(rows["survey_notice"]["when"], "2026-10-30 10:00")  # 5 days after receipt, capped at closing
        self.assertEqual(rows["flood_elevation"]["when"], "2026-10-15 23:59")
        self.assertEqual(rows["seller_survey"]["when"], "2026-09-30 23:59")
        self.assertEqual(rows["survey"]["label"], "Survey Deadline")
        self.assertNotIn("lead_paint", rows)

    def test_cash_drops_loan_deadlines(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["financing"] = "cash"
        keys = set(by_key(timeline.analyze(deal)))
        self.assertFalse(keys & {"loan_app", "loan_approval", "appraisal", "insurance_bound", "clear_to_close"})

    def test_standard_contract_has_repair_notices_not_a_cancel_right(self):
        """Standard (CRSP 7x): the inspection period is for repair notices; no right to cancel; seller windows."""
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c.update(contract_form="standard", repair_notice_delivered="2026-10-05", repair_estimates_received="2026-10-12",
                 open_permits=True)
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["inspection"]["label"], "Inspection Period Ends (Repair Notices Due)")
        self.assertFalse(rows["inspection"]["contingency"])
        self.assertEqual(rows["repair_estimates"]["when"], "2026-10-15 23:59")
        self.assertEqual(rows["repair_election"]["when"], "2026-10-19 23:59")  # Sat Oct 17 extends
        self.assertEqual(rows["permits_closed"]["when"], "2026-10-26 23:59")  # Sun Oct 25 extends
        self.assertEqual(rows["walkthrough"]["source"], "Para. 12(e)")


class Amendments(unittest.TestCase):
    def test_moved_dates_show_was(self):
        r = timeline.analyze(fixture("seller-amended.json"))
        rows = by_key(r)
        self.assertEqual(rows["closing"]["when"], "2026-12-18 10:00")
        self.assertEqual(rows["closing"]["was"], "Fri Dec 11 · 10:00 AM")
        self.assertEqual(rows["appraisal"]["when"], "2026-11-25 17:00")
        self.assertIsNone(rows["deposit"]["was"])
        # TL-21: a blank the form fills reads as its value, and dates read as dates
        self.assertIn("loan approval days: 30 (form default) → 38", r["history"][0]["summary"])
        self.assertIn("closing date: Dec 11, 2026 → Dec 18, 2026", r["history"][0]["summary"])
        self.assertIsNone(rows["hoa_docs"]["when"])  # on event until received
        self.assertIn("lead_paint", rows)  # built 1972

    def test_hoa_received_starts_review_window(self):
        deal = fixture("seller-amended.json")
        deal["contract"]["hoa_docs_received"] = "2026-11-06"
        self.assertEqual(by_key(timeline.analyze(deal))["hoa_docs"]["when"], "2026-11-09 23:59")  # 3 calendar days


class OtherContracts(unittest.TestCase):
    def test_other_contract_uses_its_own_rules_and_deadlines(self):
        r = timeline.analyze(fixture("other-contract.json"))
        rows = by_key(r)
        # TL-15: a deadline with its own time and no rollover ends at 5 PM on day 7 even on a holiday the contract lists,
        # and the earnest money date runs to the end of its day, not 5 PM.
        self.assertEqual(rows["walkaway_period"]["when"], "2026-11-27 17:00")
        self.assertEqual(rows["earnest_money"]["when"], "2026-11-23 23:59")  # 3 calendar days: Mon
        self.assertEqual(rows["title_commitment"]["when"], "2026-12-10 23:59")  # 20 days after the title company's receipt
        self.assertIn("title company's receipt", rows["title_commitment"]["rule"])
        self.assertEqual(r["contingencies_end"]["key"], "financing")
        self.assertNotIn("deposit", rows)  # no FR/BAR deadlines
        self.assertEqual(r["rules"]["family"], "the contract's definitions")

    def test_best_effort_note_is_chat_only(self):
        r = timeline.analyze(fixture("other-contract.json"))
        self.assertEqual(r["support"], "best_effort")
        self.assertTrue(any("fully supported" in n for n in r["chat_notes"]))
        self.assertFalse(any("fully supported" in n for n in r["agent_notes"]))  # TL-107: agent_notes can reach a template
        doc = timeline_render.build_html(r, {}, sample=True)
        self.assertNotIn("fully supported", doc)
        self.assertNotIn("best-effort", doc)
        self.assertNotIn("fully supported", timeline_render.ics(r))

    def test_frbar_revision_note_is_chat_only(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["form_revision"] = "FloridaRealtors/FloridaBar-ASIS-8 Rev. 1/27"
        r = timeline.analyze(deal)
        self.assertEqual(r["support"], "full")
        self.assertTrue(any("checked against" in n for n in r["chat_notes"]))
        self.assertFalse(any("checked against" in n for n in r["agent_notes"]))
        self.assertNotIn("checked against", timeline_render.build_html(r, {}, sample=True))

    def test_other_state_without_rules_is_refused(self):
        deal = fixture("other-contract.json")
        del deal["rules"]
        with self.assertRaises(timeline.DealError) as e:
            timeline.analyze(deal)
        self.assertIn("time rules are missing", str(e.exception))

    def test_other_contract_needs_deadlines(self):
        deal = fixture("other-contract.json")
        del deal["deadlines"]
        with self.assertRaises(timeline.DealError):
            timeline.analyze(deal)


class Required(unittest.TestCase):
    def test_state_required(self):
        """TL-4: no state is a question for the agent, never Florida by default."""
        deal = fixture("buyer-fha.json")
        del deal["state"]
        with self.assertRaisesRegex(timeline.DealError, "state"):
            timeline.analyze(deal)

    def test_florida_builder_contract_gets_no_frbar_rules(self):
        """TL-4: a Florida contract that isn't FR/BAR uses only the rules in the deal file."""
        deal = fixture("other-contract.json")
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
        deal = fixture("other-contract.json")
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



class Riders(unittest.TestCase):
    """CR-7 rider rows, each checked against the rider's own "if left blank" text (shared/references/frbar-riders.md)."""

    def deal(self, riders, form="standard", **contract):
        d = fixture("buyer-fha.json")  # Effective Date Fri Sep 25 2026, closing Fri Oct 30 2026
        d["contract"].update(contract_form=form, riders=riders, financing="conventional")
        d["contract"].pop("insurance_days", None)
        d["contract"].update(contract)
        return d

    def test_rider_k_turns_standard_into_a_walkaway(self):
        rows = by_key(timeline.analyze(self.deal(["As Is"])))
        self.assertEqual(rows["inspection"]["label"], "Inspection Period Ends (Right to Cancel)")
        self.assertTrue(rows["inspection"]["contingency"])
        self.assertIn("Rider (K)", rows["inspection"]["source"])
        self.assertNotIn("repair_estimates", rows)
        self.assertIn("Rider (K)", rows["walkthrough"]["source"])

    def test_rider_l_keeps_repairs_and_adds_a_walkaway(self):
        r = timeline.analyze(self.deal(["L"]))
        rows = by_key(r)
        self.assertTrue(rows["inspection"]["contingency"])
        self.assertIn("Right to Inspect", rows["inspection"]["label"])
        self.assertIn("repair_estimates", rows)
        self.assertIn("repair_election", rows)
        self.assertIn("Right to Inspect Rider (L)", r["contract_label"])

    def test_reserved_rider_on_as_is_is_refused(self):
        with self.assertRaisesRegex(timeline.DealError, "RESERVED"):
            timeline.analyze(self.deal(["K"], form="as_is"))

    def test_rider_f_blank_date_is_ten_days_before_closing(self):
        rows = by_key(timeline.analyze(self.deal(["Appraisal Contingency"])))
        self.assertTrue(rows["appraisal_due"]["when"].startswith("2026-10-20"))  # Closing Oct 30 - 10
        self.assertTrue(rows["appraisal"]["when"].startswith("2026-10-23"))  # + 3 days for the buyer's notice
        self.assertTrue(rows["appraisal"]["contingency"])

    def test_rider_f_written_date(self):
        rows = by_key(timeline.analyze(self.deal(["F"], appraisal_date="2026-10-14")))
        self.assertTrue(rows["appraisal_due"]["when"].startswith("2026-10-14"))
        self.assertTrue(rows["appraisal"]["when"].startswith("2026-10-19"))

    def test_rider_h_blank_is_the_earlier_date(self):
        rows = by_key(timeline.analyze(self.deal(["Homeowners'/Flood Ins"])))
        self.assertTrue(rows["insurance"]["when"].startswith("2026-10-20"))  # Closing - 10 is before ED + 30
        self.assertIn("Earlier of", rows["insurance"]["rule"])

    def test_rider_v_date_blank_waits_for_the_agent(self):
        r = timeline.analyze(self.deal(["Sale of Buyer's Property"]))
        pending = {x["key"] for x in r["pending"]}
        self.assertIn("buyer_sale_closes", pending)
        rows = by_key(timeline.analyze(self.deal(["V"], sale_contingency_date="2026-10-15")))
        self.assertTrue(rows["sale_contingency"]["when"].startswith("2026-10-19"))  # Oct 18 is a Sunday

    def test_short_sale_rows(self):
        rows = by_key(timeline.analyze(self.deal(["Short Sale"])))
        self.assertTrue(rows["short_sale_application"]["when"].startswith("2026-10-05"))  # ED + 10
        self.assertTrue(rows["short_sale_approval"]["when"].startswith("2026-12-24"))  # ED + 90
        self.assertTrue(rows["short_sale_expires"]["when"].startswith("2027-01-25"))  # + 30 = Sat Jan 23, rolled

    def test_post_closing_occupancy(self):
        rows = by_key(timeline.analyze(self.deal(["U"], seller_occupancy_days=14)))
        self.assertTrue(rows["post_closing_agreement"]["when"].startswith("2026-10-20"))
        self.assertTrue(rows["seller_moves_out"]["when"].startswith("2026-11-13"))

    def test_attorney_approval_dates(self):
        r = timeline.analyze(self.deal(["Y", "Z"], buyer_attorney_date="2026-10-02"))
        rows = by_key(r)
        self.assertTrue(rows["buyer_attorney"]["when"].startswith("2026-10-02"))
        self.assertTrue(rows["buyer_attorney"]["contingency"])
        self.assertIn("seller_attorney", {x["key"] for x in r["pending"]})  # its date is blank

    def test_mold_and_gg(self):
        rows = by_key(timeline.analyze(self.deal(["Mold Inspection", "GG"])))
        self.assertTrue(rows["mold"]["when"].startswith("2026-10-15"))  # ED + 20
        self.assertTrue(rows["compensation_agreement"]["when"].startswith("2026-09-28"))  # ED + 3
        self.assertTrue(rows["compensation_cancel"]["when"].startswith("2026-10-01"))


class ContractHolidays(unittest.TestCase):
    """TL-15, TL-24: a contract that defines its own holidays replaces the federal list (holidays base "none")."""

    def test_contract_holiday_list_only(self):
        from datetime import date
        d = timeline.dates
        own = d.Holidays({date(2026, 11, 27): "Holiday (contract)"}, base="none")
        self.assertIsNone(d.holiday_name(date(2026, 10, 12), own))  # not on the contract's list
        self.assertEqual(d.holiday_name(date(2026, 11, 27), own), "Holiday (contract)")
        self.assertEqual(d.holiday_name(date(2026, 10, 12)), "Columbus Day")  # the federal list still has it

    def test_rollover_date_passes_a_contract_holiday(self):
        deal = fixture("other-contract.json")
        deal["contract"]["effective_date"] = "2026-11-24"  # + 3 days = Nov 27, a holiday the contract lists
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["earnest_money"]["when"], "2026-11-30 23:59")  # past the holiday and the weekend
        self.assertEqual(rows["walkaway_period"]["when"], "2026-12-01 17:00")
        self.assertIn("Only the holidays the contract lists.", [x["text"] for x in r["rules"]["lines"]])

    def test_unknown_calendar(self):
        deal = fixture("other-contract.json")
        deal["rules"]["holidays"] = "state"
        with self.assertRaisesRegex(timeline.DealError, "us_federal"):
            timeline.analyze(deal)


class AuditWording(unittest.TestCase):
    """TL-14 (rights that stay open), TL-17 (TRID business days), TL-25 (insurance is a lender target)."""

    def test_closing_disclosure_counts_saturdays(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-11-02"  # a Monday: 3 TRID days back are Sat, Fri, Thu
        row = by_key(timeline.analyze(deal))["clear_to_close"]
        self.assertEqual(row["when"][:10], "2026-10-29")  # Mon-Fri counting would give Wed Oct 28
        self.assertIn("TRID business days", row["rule"])

    def test_insurance_bound_is_a_target(self):
        row = by_key(timeline.analyze(fixture("buyer-fha.json")))["insurance_bound"]
        self.assertFalse(row["critical"])
        self.assertIn("Lender Target", row["label"])

    def test_open_rights_after_contingencies(self):
        r = timeline.analyze(fixture("buyer-fha.json"))  # FHA: the appraisal clause runs to closing
        self.assertIn("FHA/VA appraisal clause (to closing)", r["open_rights"])
        self.assertIn("Title Defects", r["open_rights"])
        html = timeline_render.build_html(r, {}, False)
        self.assertIn("These rights stay open after that", html)
        seller = timeline.analyze(fixture("buyer-fha.json"), side="seller")
        self.assertNotIn("After that the deal is firm", timeline_render.build_html(seller, {}, False))


class TimeZones(unittest.TestCase):
    """TL-19: FR/BAR times are local to the property."""

    def test_panhandle_prints_central(self):
        deal = fixture("buyer-fha.json")
        deal["county"] = "Escambia"
        rows = by_key(timeline.analyze(deal))
        self.assertTrue(rows["deposit"]["display"].endswith(" CT"))
        self.assertFalse(by_key(timeline.analyze(fixture("buyer-fha.json")))["deposit"]["display"].endswith("T"))

    def test_split_county_is_flagged(self):
        deal = fixture("buyer-fha.json")
        deal["county"] = "Gulf"
        r = timeline.analyze(deal)
        self.assertTrue(any("spans two time zones" in n for n in r["agent_notes"]))  # TL-108: the agent's question
        self.assertFalse(any("time zone" in f for f in r["flags"]))
        deal["time_zone"] = "CT"
        self.assertFalse(any("spans two time zones" in n for n in timeline.analyze(deal)["agent_notes"]))


class Calendar(unittest.TestCase):
    """TL-20: the closing calendar the description promises."""

    def test_ics(self):
        t = timeline.analyze(fixture("buyer-fha.json"))
        text = timeline_render.ics(t)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(text.count("BEGIN:VEVENT"), len(t["rows"]))
        self.assertIn("DTSTART;VALUE=DATE:", text)  # end-of-day deadlines are all-day events
        self.assertEqual(text.count("BEGIN:VALARM"), sum(r["critical"] for r in t["rows"]))
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))
        self.assertEqual(text.split("UID:")[1][:40], timeline_render.ics(t).split("UID:")[1][:40])  # stable across runs

    def test_render_writes_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "deal.json")
            with open(src, "w") as f:
                json.dump(fixture("buyer-fha.json"), f)
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                timeline_render.render.main(timeline_render.build, formats=("pdf", "ics"),
                                            argv=[src, "--format", "ics", "--out", tmp])
            self.assertTrue(out.getvalue().strip().endswith(".ics"))


class ShortSale(unittest.TestCase):
    """Rider G: Phase 1 counts from the Effective Date; every other period, and the closing, from the approval."""

    def test_before_approval_rows_wait(self):
        r = timeline.analyze(fixture("short-sale.json"))  # ED Tue Sep 22 2026; Para. 4 closing Dec 22 is replaced
        rows = by_key(r)
        self.assertEqual(rows["deposit"]["when"], "2026-09-25 23:59")
        self.assertEqual(rows["short_sale_application"]["when"], "2026-09-29 23:59")  # ED + 7
        self.assertEqual(rows["short_sale_forms"]["when"], "2026-10-05 23:59")  # + 5 = Sun Oct 4, extended
        self.assertEqual(rows["short_sale_approval"]["when"], "2026-11-23 23:59")  # ED + 60 = Sat Nov 21, extended
        self.assertEqual(rows["compensation_agreement"]["when"], "2026-09-25 23:59")  # GG stays on the Effective Date
        for key, rule in (("loan_app", "5 days after short sale approval"), ("inspection", "10 days after short sale approval"),
                          ("loan_approval", "30 days after short sale approval"),
                          ("closing", "45 days after short sale approval (Rider G, Para. 6)")):
            self.assertIsNone(rows[key]["when"], key)
            self.assertEqual(rows[key]["rule"], rule)
        self.assertIsNone(rows["seller_terminate"]["when"])  # counted from a pending row: pending too
        self.assertIsNone(r["closing"])
        self.assertIsNone(r["contingencies_end"])  # never the approval deadline
        self.assertFalse(rows["short_sale_approval"]["contingency"])
        self.assertEqual(r["contingencies_waiting"], ["Inspection Ends", "Loan Approval"])
        self.assertTrue(any("Para. 4 closing date (Dec 22, 2026) is replaced" in n for n in r["agent_notes"]))
        self.assertTrue(any("Rider GG is counted from the Effective Date" in n for n in r["agent_notes"]))
        self.assertTrue(any("Short sale approval not received yet" in n for n in r["agent_notes"]))
        self.assertFalse(any("No closing date given" in n for n in r["agent_notes"]))

    def test_before_approval_renders(self):
        r = timeline.analyze(fixture("short-sale.json"))
        doc = timeline_render.build_html(r, {}, sample=True)
        self.assertIn("Awaiting Approval", doc)
        self.assertIn("10 days after short sale approval", doc)
        self.assertNotIn("Your main protections run through", doc)
        text = timeline_render.ics(r)
        self.assertEqual(text.count("BEGIN:VEVENT"), len([x for x in r["rows"] if not x["done"] and not x["past"]]))
        self.assertNotIn("Loan Approval", text)

    def test_after_approval_rows_get_dates(self):
        deal = fixture("short-sale.json")
        deal["amendments"] = [{"date": "2026-11-02", "description": "Short sale approval received",
                               "changes": {"short_sale_approval_received": "2026-11-02"}}]
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["loan_app"]["when"], "2026-11-09 23:59")  # Sat Nov 7, extended
        self.assertEqual(rows["inspection"]["when"], "2026-11-12 23:59")  # Nov 12: Veterans Day Wed Nov 11 isn't the end
        self.assertEqual(rows["loan_approval"]["when"], "2026-12-02 23:59")
        self.assertEqual(rows["closing"]["when"], "2026-12-17 10:00")  # approval + 45
        self.assertEqual(rows["deposit"]["when"], "2026-09-25 23:59")  # Phase 1 doesn't move
        self.assertNotIn("short_sale_expires", rows)
        self.assertTrue(rows["short_sale_approval"]["done"])
        self.assertEqual(r["contingencies_end"]["key"], "loan_approval")
        self.assertIsNone(rows["inspection"]["was"])  # it had no date before, so nothing "moved"

    def test_amended_closing_wins(self):
        deal = fixture("short-sale.json")
        deal["contract"].update(short_sale_approval_received="2026-11-02", date_overrides={"closing": "2026-12-11"})
        self.assertEqual(by_key(timeline.analyze(deal))["closing"]["when"], "2026-12-11 10:00")


class Completed(unittest.TestCase):
    def test_done_rows(self):
        deal = fixture("buyer-fha.json")
        deal["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertTrue(rows["deposit"]["done"])
        self.assertEqual(rows["deposit"]["done_display"], "Done Sep 26")
        self.assertEqual(r["first_deadline"]["key"], "loan_app")
        self.assertIn("Done Sep 26", timeline_render.build_html(r, {}, False))
        text = timeline_render.ics(r)
        self.assertNotIn("Initial Escrow Deposit", text)
        self.assertEqual(text.count("BEGIN:VEVENT"), len(r["rows"]) - 1)

    def test_unknown_key(self):
        deal = fixture("buyer-fha.json")
        deal["completed"] = {"earnest": "2026-09-26"}
        with self.assertRaisesRegex(timeline.DealError, "not a deadline"):
            timeline.analyze(deal)


class ReportDetails(unittest.TestCase):
    def test_report_date(self):
        deal = fixture("buyer-fha.json")
        deal["report_date"] = "2026-09-26"
        self.assertIn("September 26, 2026", timeline_render.build_html(timeline.analyze(deal), {}, False))
        deal["report_date"] = "Sept 26"
        with self.assertRaises(timeline.DealError):
            timeline.analyze(deal)

    def test_ics_stamp_is_utc(self):
        text = timeline_render.ics(timeline.analyze(fixture("buyer-fha.json")))
        self.assertRegex(text, r"DTSTAMP:\d{8}T\d{6}Z")

    def test_rollover_names_the_holiday(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["inspection_days"] = 15  # Sat Oct 10; Mon Oct 12 is Columbus Day
        note = by_key(timeline.analyze(deal))["inspection"]["note"]
        self.assertIn("a Saturday (Mon Oct 12 is Columbus Day)", note)
        self.assertIn("Tue Oct 13", note)

    def test_walkthrough_has_no_time(self):
        rows = by_key(timeline.analyze(fixture("buyer-fha.json")))
        self.assertEqual(rows["walkthrough"]["display"], "Thu Oct 29")
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-10-31"  # Sat: closing Mon Nov 2, walk-through on closing day
        self.assertEqual(by_key(timeline.analyze(deal))["walkthrough"]["display"], "Mon Nov 2 · before Closing")

    def test_condo_inspection_wording(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["condo"] = True
        action = by_key(timeline.analyze(deal))["inspection"]["action"]
        self.assertIn("of the unit", action)
        self.assertNotIn("wind mitigation", action)

    def test_custom_row_by_closing(self):
        deal = fixture("buyer-fha.json")
        deal["deadlines"] = [{"key": "carpet", "label": "Seller Cleans Carpets", "short": "Carpets", "basis": "before",
                              "days": 0, "time": "closing", "party": "Seller", "source": "Para. 20"}]
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["carpet"]["when"], "2026-10-30 10:00")
        self.assertEqual(rows["carpet"]["display"], "Fri Oct 30 · by Closing")
        self.assertEqual(rows["carpet"]["rule"], "By Closing")
        keys = [x["key"] for x in r["rows"]]
        self.assertLess(keys.index("carpet"), keys.index("closing"))
        deal["deadlines"][0].update(days=2, time="17:00")
        self.assertEqual(by_key(timeline.analyze(deal))["carpet"]["when"], "2026-10-28 17:00")

    def test_title_by(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["title_by"] = "buyer"
        r = timeline.analyze(deal)
        self.assertEqual(by_key(r)["title"]["party"], "Buyer")
        self.assertFalse(any("title_by" in n for n in r["agent_notes"]))
        del deal["contract"]["title_by"]
        self.assertTrue(any("Set title_by" in n for n in timeline.analyze(deal)["agent_notes"]))
        deal["contract"]["title_by"] = "lender"
        with self.assertRaisesRegex(timeline.DealError, "title_by"):
            timeline.analyze(deal)

    def test_agent_notes_not_repeated(self):
        deal = fixture("buyer-fha.json")
        deal["agent_notes"] = ["Title Evidence Deadline blank: used the 15-day default", "Confirm the delivery date",
                               "Confirm the delivery date"]
        notes = timeline.analyze(deal)["agent_notes"]
        self.assertEqual(sum("title evidence" in n.lower() and "default" in n.lower() for n in notes), 1)
        self.assertEqual(notes.count("Confirm the delivery date"), 1)


class StripLayout(unittest.TestCase):
    def test_close_labels_never_overlap(self):
        marks = [(50, 120), (58, 100), (66, 110), (300, 90), (640, 120), (650, 100), (660, 90), (670, 130), (690, 80)]
        spots, levels = timeline_render.place_labels(marks, 740)
        boxes = [(side, lv, x0, x0 + w) for (side, lv, x0), (_, w) in zip(spots, marks)]
        for i, a in enumerate(boxes):
            self.assertTrue(a[2] >= 0 and a[3] <= 740)
            for b in boxes[i + 1:]:
                if a[:2] == b[:2]:
                    self.assertTrue(a[3] <= b[2] or b[3] <= a[2], (a, b))

    def test_dense_fixture_renders(self):
        deal = fixture("standard-riders.json")
        svg = timeline_render.strip(timeline.analyze(deal), {"Buyer": "#111", "Seller": "#222", "Both": "#333"})
        self.assertIn("<svg", svg)


class Audit0929(unittest.TestCase):
    """Findings from the 2026-09-29 audit (docs/audits/2026-09-29.md)."""

    def test_rider_names_that_dont_map_are_noted(self):
        """TL-101: "Short-Sale Rider" is Rider G; a name that isn't a CR-7 rider gets an agent note, never silence."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["riders"] = ["Short-Sale Rider", "Private Well and Septic"]
        r = timeline.analyze(deal)
        self.assertIn("short_sale_approval", by_key(r))
        self.assertTrue(any("Not read as a CR-7 rider: Private Well and Septic" in n for n in r["agent_notes"]))

    def test_condominium_association_is_rider_a(self):
        """TL-102"""
        deal = fixture("buyer-fha.json")
        deal["contract"]["riders"] = ["Condominium Association"]
        rows = by_key(timeline.analyze(deal))
        self.assertIn("condo_docs", rows)
        self.assertNotIn("hoa_docs", rows)

    def test_late_short_sale_approval_is_flagged(self):
        """TL-103: approval deadline Mon Nov 23 (ED + 60, extended), contract expiration 30 days later (Wed Dec 23)."""
        deal = fixture("short-sale.json")
        deal["contract"]["short_sale_approval_received"] = "2026-11-30"
        r = timeline.analyze(deal)
        self.assertTrue(any("after the Short Sale Approval Deadline (Nov 23, 2026)" in f for f in r["flags"]))
        deal["contract"]["short_sale_approval_received"] = "2027-01-04"
        r = timeline.analyze(deal)
        self.assertTrue(any("after the Contract Expiration Date (Dec 23, 2026)" in f for f in r["flags"]))
        deal["contract"]["short_sale_approval_received"] = "2026-11-02"
        self.assertFalse(any("short sale approval was received" in f for f in timeline.analyze(deal)["flags"]))

    def test_before_closing_row_rolled_onto_closing_day_is_due_by_closing(self):
        """TL-105: FinCEN info 1 day before a Monday closing falls on Sunday and extends to Monday; it's due by the
        10:00 AM closing, not at 11:59 PM after it, and sorts before the closing."""
        deal = fixture("buyer-fha.json")
        deal["contract"].update(closing_date="2026-11-02", fincen_report=True)
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["fincen"]["when"], rows["closing"]["when"])
        self.assertTrue(rows["fincen"]["by_closing"])
        self.assertIn("by Closing", rows["fincen"]["display"])
        keys = [x["key"] for x in r["rows"]]
        self.assertLess(keys.index("fincen"), keys.index("closing"))

    def test_custom_deadline_time_and_rollover_on_every_basis(self):
        """TL-109: an event row keeps its own time and rollover; "closing" on an after row is refused."""
        deal = fixture("buyer-fha.json")
        deal["deadlines"] = [{"key": "docs", "label": "Docs Review Ends", "basis": "event", "days": 2,
                              "received": "2026-10-01", "time": "17:00", "rollover": False, "party": "Buyer"}]
        self.assertEqual(by_key(timeline.analyze(deal))["docs"]["when"], "2026-10-03 17:00")  # a Saturday, not moved
        deal["deadlines"] = [{"key": "x", "label": "X", "basis": "after", "days": 3, "time": "closing", "party": "Buyer"}]
        with self.assertRaisesRegex(timeline.DealError, "works only with basis before"):
            timeline.analyze(deal)

    def test_bad_inputs_name_the_field(self):
        """TL-110, TL-111"""
        cases = [
            (lambda d: d.update(deadlines=[{"key": "x", "label": "X", "basis": "before", "party": "Buyer"}]), "needs days"),
            (lambda d: d.update(deadlines=[{"key": "y", "label": "Y", "basis": "after", "days": 2}]), "needs party"),
            (lambda d: d["contract"].update(closing_date="2026-11-31"), "contract.closing_date is '2026-11-31'"),
            (lambda d: d.update(deadlines=[{"key": "inspection", "label": "Dup", "basis": "after", "days": 20,
                                            "party": "Buyer"}]), "used twice"),
        ]
        for mutate, message in cases:
            deal = fixture("buyer-fha.json")
            mutate(deal)
            with self.assertRaisesRegex(timeline.DealError, message):
                timeline.analyze(deal)
        deal = fixture("buyer-fha.json")
        deal["contract"]["price"] = "$412,000"
        self.assertEqual(timeline.analyze(deal)["price"], "$412,000")

    def test_amendment_that_dates_pending_rows(self):
        """TL-113: a short sale approval recorded by amendment lists the rows it dated for the first time."""
        deal = fixture("short-sale.json")
        deal["amendments"] = [{"date": "2026-09-26", "description": "Short sale approval received",
                               "changes": {"short_sale_approval_received": "2026-09-26"}}]
        r = timeline.analyze(deal)
        self.assertEqual(r["moved"], [])
        self.assertIn("Closing", [x["label"] for x in r["newly_dated"]])

    def test_rollover_notes_read_plainly(self):
        """TL-114: a contract holiday isn't "Holiday (contract)", and the closing note doesn't repeat the date."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-10-31"
        note = by_key(timeline.analyze(deal))["closing"]["note"]
        self.assertEqual(note, "the Closing Date, Sat Oct 31, is a Saturday: closing extends to Mon Nov 2")
        r = timeline.analyze(fixture("other-contract.json"))
        self.assertNotIn("Holiday (contract)", json.dumps(r))

    def test_calendar_zone_reminders_and_sequence(self):
        """TL-115"""
        deal = fixture("buyer-fha.json")
        deal["county"] = "Escambia"  # Central time
        deal["amendments"] = [{"date": "2026-09-26", "description": "Extend", "changes": {"loan_approval_days": 25}}]
        text = timeline_render.ics(timeline.analyze(deal))
        self.assertIn("TZID:America/Chicago", text)
        self.assertIn("DTSTART;TZID=America/Chicago:20261030T100000", text)
        self.assertIn("SEQUENCE:1", text)
        self.assertIn("TRIGGER:-PT15H", text)  # all-day: 9:00 AM the day before
        self.assertIn("TRIGGER:-P1D", text)  # timed closing: 24 hours ahead
        self.assertIn("TZID:America/New_York", timeline_render.ics(timeline.analyze(fixture("buyer-fha.json"))))
        self.assertNotIn("TZID", timeline_render.ics(timeline.analyze(fixture("other-contract.json"))))

    def test_rows_checked_against_the_forms(self):
        """TL-116: Para. 9(c) seller's title evidence (5 days), Rider H (a) and (b) dates, Rider G approval copy, and the
        WDO election (12(c)(ii)) is the buyer's notice only."""
        deal = fixture("buyer-fha.json")
        deal["contract"].update(seller_has_title_evidence=True, riders=["E", "H"], insurance_flood=True,
                                flood_insurance_date="2026-10-15")
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["seller_title"]["when"], "2026-09-30 23:59")
        self.assertEqual(rows["flood_insurance"]["when"], "2026-10-15 23:59")
        self.assertEqual(rows["insurance"]["label"], "Homeowner's Insurance Contingency Ends")
        self.assertIn("(G), Para. 1", by_key(timeline.analyze(fixture("short-sale.json")))["short_sale_copy"]["source"])
        std = timeline.analyze(fixture("standard-riders.json"))
        self.assertIn("for WDO repairs only the buyer's notice counts", by_key(std)["repair_election"]["action"])

    def test_cosmetics(self):
        """TL-117: whole words in short labels, "1 amendment", no star on a done row, "Closing day" not "0 days"."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["riders"] = ["E", "GG"]
        deal["contract"]["walkthrough_days_before"] = 0
        deal["completed"] = {"deposit": "2026-09-26"}
        deal["amendments"] = [{"date": "2026-09-26", "description": "Extend", "changes": {"loan_approval_days": 25},
                               "date_overrides": {"survey": "2026-10-23 17:00"}}]
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["compensation_agreement"]["short"], "Compensation Agreement")
        self.assertEqual(rows["walkthrough"]["rule"], "Closing day")
        self.assertIn("Oct 23, 2026 5:00 PM", r["history"][0]["summary"])
        doc = timeline_render.build_html(r, {}, sample=True)
        self.assertIn("Includes 1 amendment.", doc)
        self.assertNotIn("amendment(s)", doc)
        self.assertNotIn("Initial Escrow Deposit Due</b>&nbsp;<span class=crit>", doc)

    def test_future_effective_date_and_what_if(self):
        """TL-119"""
        deal = fixture("buyer-fha.json")
        deal["report_date"] = "2026-09-20"
        deal["amendments"] = [{"date": "2026-09-28", "description": "Extend", "changes": {"loan_approval_days": 25}}]
        notes = timeline.analyze(deal)["agent_notes"]
        self.assertTrue(any("is after the report date" in n for n in notes))
        self.assertTrue(any("Amendment 1 (Extend) is dated Sep 28, 2026" in n for n in notes))
        deal["what_if"] = True
        r = timeline.analyze(deal)
        self.assertFalse(any("Effective Date (Sep 25, 2026) is after" in n for n in r["agent_notes"]))
        self.assertIn("What-If", timeline_render.build_html(r, {}, sample=False))
        self.assertIn("SUMMARY:What-If: ", timeline_render.ics(r))

    def test_fha_va_election_row(self):
        """TL-120: Rider E Para. 5, 3 days after the buyer receives the appraisal."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["appraisal_received"] = "2026-10-08"
        # Oct 11 is a Sunday and Oct 12 Columbus Day: extended to Tue Oct 13
        self.assertEqual(by_key(timeline.analyze(deal))["fha_va_election"]["when"], "2026-10-13 23:59")

    def test_other_contract_needs_only_day_count(self):
        """TL-121, TL-123: the other rules default to the neutral reading and are asked; no time of day is invented."""
        deal = fixture("other-contract.json")
        deal["rules"] = {"day_count": "calendar"}
        deal["deadlines"].append({"key": "walk", "label": "Final Walk-Through", "basis": "before", "days": 1,
                                  "party": "Buyer"})
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertTrue(rows["walk"]["no_time"])
        self.assertNotIn("PM", rows["walk"]["display"])
        self.assertNotIn("PM", rows["financing"]["display"])
        self.assertTrue(rows["walkaway_period"]["display"].endswith("5:00 PM"))  # its own stated time is kept
        self.assertTrue(any("don't say" in n and "when a day ends" in n for n in r["agent_notes"]))
        del deal["rules"]["day_count"]
        with self.assertRaisesRegex(timeline.DealError, "day_count"):
            timeline.analyze(deal)

    def test_short_sale_backup_offers_note(self):
        """TL-122: Rider G Para. 7, option (a) when neither box is checked."""
        notes = timeline.analyze(fixture("short-sale.json"))["agent_notes"]
        self.assertTrue(any("Para. 7(a)" in n and "neither box" in n for n in notes))

    def test_client_report_has_no_tool_instructions(self):
        """FH-102, TL-107: the PDF and the markdown template carry no "re-run" or agent-only notes."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["riders"] = ["E", "V"]
        r = timeline.analyze(deal)
        doc = timeline_render.build_html(r, {}, sample=True)
        self.assertNotIn("re-run", doc)
        self.assertNotIn("ask the agent", doc)
        self.assertTrue(any("Buyer's Sale Must Close" in n and "re-run" in n for n in r["agent_notes"]))
        with open(os.path.join(ROOT, "skills", "contract-timeline", "assets", "timeline-template.md")) as f:
            self.assertNotIn("agent note", f.read().lower())

    def test_key_dates_table_can_split(self):
        """TL-106"""
        doc = timeline_render.build_html(timeline.analyze(fixture("buyer-fha.json")), {}, sample=True)
        self.assertIn('<div class="tbl brk"><table class="kd">', doc)


if __name__ == "__main__":
    unittest.main()
