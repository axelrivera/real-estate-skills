"""Tests for skills/contract-timeline/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

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
    the next business day (Standard F), title evidence 15 days before closing when blank (Para. 9(c)). Every date on
    the unmodified fixture is pinned by golden."""

    def test_blank_association_approval_box_assumes_required(self):
        d = fixture("buyer-fha.json")
        d["contract"]["association_approval"] = "unknown"
        d["contract"]["preapproval_expires"] = "2026-10-20"
        r = timeline.analyze(d)
        rows = by_key(r)
        self.assertIn("assoc_apply", rows)
        self.assertIn("assoc_approval", rows)
        self.assertIn("assoc_box_blank", r["flag_keys"])
        self.assertIn("assoc_box_blank", r["note_keys"])
        self.assertIn("preapproval_expires", r["note_keys"])
        self.assertEqual(len(r["flags"]), len(r["flag_keys"]))  # every flag the script adds has a key

    def test_first_deadline_is_the_earliest_open_critical_contract_deadline(self):
        """TL-204: the earliest open critical contract deadline, whoever owes it (a critical Both row counts, the
        non-critical Loan Application doesn't); never a lender target; with no critical row left, the earliest
        contract deadline."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"].get("riders") or []) + ["GG"]
        d["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(d)
        # TL-246: Rider GG's cancel window (Thu Oct 1) is a broker matter, never the client's first deadline
        self.assertEqual((r["first_deadline"]["key"], r["first_deadline"]["critical"]), ("inspection", True))
        self.assertTrue(by_key(r)["compensation_cancel"]["broker"])
        d["contract"]["riders"] = ["E", "H"]
        self.assertEqual(timeline.analyze(d)["first_deadline"]["key"], "inspection")  # not loan_app (Sep 30)
        o = fixture("other-contract.json")
        o["side"] = "seller"
        o["deadlines"][0]["party"] = "both"
        self.assertEqual(timeline.analyze(o)["first_deadline"]["key"], "earnest_money")  # a Both row isn't skipped
        # the lender's critical Closing Disclosure (Oct 27) is never it: the closing is
        late = fixture("buyer-fha.json")
        late["report_date"] = "2026-10-27"
        # TL-264: a contingency window is done only once its date has come (loan approval ends Oct 26)
        late["completed"] = {k: "2026-10-26" for k in ("deposit", "inspection", "insurance", "loan_approval")}
        r = timeline.analyze(late)
        self.assertFalse(r["first_deadline"]["lender"])
        self.assertEqual(r["first_deadline"]["key"], "closing")
        # no critical row open: the earliest open contract deadline, still not a lender target
        late["completed"]["closing"] = "2026-10-01"
        self.assertEqual(timeline.analyze(late)["first_deadline"]["key"], "seller_terminate")

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
        self.assertIn("past_not_done", r["note_keys"])
        self.assertTrue(any(rows["deposit"]["label"] in n for n in r["agent_notes"]))  # the note names the row
        self.assertNotIn("UID:deposit-", timeline_render.ics(r))
        self.assertIn("Past, Confirm", timeline_render.build_html(r, {}, sample=True))
        d["completed"] = {"deposit": "2026-09-27"}
        self.assertFalse(by_key(timeline.analyze(d))["deposit"]["past"])

    def test_fha_rider_has_no_appraisal_period(self):
        """TL-3: the FHA/VA rider has no appraisal period; its protection runs to closing (a flag). The dates, flag and
        note keys and pending rows of this fixture are pinned by golden (dev/golden/contract-timeline/buyer-fha.json)."""
        r = timeline.analyze(fixture("buyer-fha.json"))
        self.assertNotIn("appraisal", by_key(r))
        self.assertIn("fha_va_appraisal", r["flag_keys"])

    def test_rider_words_and_agent_notes(self):
        deal = fixture("buyer-fha.json")
        c = deal["contract"]
        c["riders"] = ["Private Well and Septic", "Vacant Land"]
        c["financing"] = "conventional"
        c.pop("closing_time", None)
        r = timeline.analyze(deal)
        self.assertNotIn("appraisal", by_key(r))  # "va" is a whole word, not part of "private"
        self.assertNotIn("fha_va_appraisal", r["flag_keys"])
        self.assertIn("closing_time_assumed", r["note_keys"])
        self.assertNotIn("closing_time_assumed", r["flag_keys"])
        self.assertFalse(any("MLS" in n for n in r["agent_notes"]))  # the market's MLS note doesn't matter here
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
        rows = by_key(r)
        self.assertGreater(rows["inspection"]["when"], rows["closing"]["when"])
        self.assertIn("after_closing", r["flag_keys"])
        self.assertTrue(any(rows["inspection"]["label"] in f for f in r["flags"]))  # the flag names the row
        deal["contract"]["inspection_days"] = 10
        deal["contract"]["loan_approval_days"] = 40
        self.assertIn("loan_approval_after_closing", timeline.analyze(deal)["flag_keys"])

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
    def test_amendment_summary_reads_values(self):
        """TL-21: a blank the form fills reads as its value, and dates read as dates. The moved dates and `was` of
        seller-amended.json are pinned by golden."""
        summary = timeline.analyze(fixture("seller-amended.json"))["history"][0]["summary"]
        self.assertIn("30 days (form default)", summary)
        self.assertIn("Dec 11, 2026", summary)
        # TL-215: the fields read as the report's labels, not the deal file's names
        self.assertIn("Loan Approval Period: 30 days (form default) → 38 days", summary)
        self.assertIn("Closing Date:", summary)
        self.assertNotIn("_", summary)
        self.assertNotIn("loan approval days", summary)
        self.assertEqual(timeline._field_label("rofr_days"), "ROFR")
        self.assertEqual(timeline._field_value("price", 412000), "$412,000")

    def test_hoa_received_starts_review_window(self):
        deal = fixture("seller-amended.json")
        deal["contract"]["hoa_docs_received"] = "2026-11-06"
        self.assertEqual(by_key(timeline.analyze(deal))["hoa_docs"]["when"], "2026-11-09 23:59")  # 3 calendar days


class OtherContracts(unittest.TestCase):
    def test_other_contract_period_counts_from_its_receipt(self):
        """TL-15: the title commitment counts from the title company's receipt, not the Effective Date, so moving the
        receipt moves the deadline. The fixture's own dates are pinned by golden."""
        deal = fixture("other-contract.json")
        base = by_key(timeline.analyze(deal))["title_commitment"]["when"]
        row = next(x for x in deal["deadlines"] if x["key"] == "title_commitment")
        row["receipt_date"] = str(date.fromisoformat(row["receipt_date"]) + timedelta(days=7))
        moved = by_key(timeline.analyze(deal))["title_commitment"]["when"]
        self.assertEqual((datetime.fromisoformat(moved) - datetime.fromisoformat(base)).days, 7)

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
        """A missing Effective Date is a DealError, which the CLI prints as JSON with ok false."""
        deal = fixture("buyer-fha.json")
        del deal["contract"]["effective_date"]
        with self.assertRaises(timeline.DealError):
            timeline.analyze(deal)
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
        self.assertIn("Holidays", [x["label"] for x in r["rules"]["lines"]])

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
        self.assertIn("FHA appraisal clause (to closing)", r["open_rights"])  # TL-233: the loan type
        self.assertIn("Title Defects", r["open_rights"])
        # both views name the rights that stay open, so neither reads as firm once the main contingencies end
        tr = timeline_render
        still = tr.esc(tr.join_words([tr.sentence_case(x) for x in r["open_rights"]]))
        self.assertIn(still, tr.build_html(r, {}, False))
        seller = timeline.analyze(fixture("buyer-fha.json"), side="seller")
        self.assertEqual(seller["open_rights"], r["open_rights"])
        self.assertIn(still, tr.build_html(seller, {}, False))


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
        self.assertIn("time_zone_split", r["note_keys"])  # TL-108: the agent's question, never a client flag
        self.assertNotIn("time_zone_split", r["flag_keys"])
        deal["time_zone"] = "CT"
        self.assertNotIn("time_zone_split", timeline.analyze(deal)["note_keys"])

    def test_market_notes_reach_the_agent(self):
        deal = fixture("buyer-fha.json")
        deal["county"] = "Semnole"  # a misspelled county: the market's note is passed on
        r = timeline.analyze(deal)
        self.assertIn("market", r["note_keys"])
        self.assertTrue(any("Semnole" in n for n in r["agent_notes"]))


class Calendar(unittest.TestCase):
    """TL-20: the closing calendar the description promises."""

    def test_ics(self):
        t = timeline.analyze(fixture("buyer-fha.json"))
        text = timeline_render.ics(t)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n"))
        contract = [r for r in t["rows"] if not r["lender"]]  # TL-252: lender targets stay out by default
        self.assertEqual(text.count("BEGIN:VEVENT"), len(contract))
        self.assertIn("DTSTART;VALUE=DATE:", text)  # end-of-day deadlines are all-day events
        self.assertEqual(text.count("BEGIN:VALARM"), sum(r["critical"] for r in contract))
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
        """Every date on short-sale.json (ED Tue Sep 22 2026; Para. 4 closing Dec 22 is replaced) is pinned by golden;
        this checks which rows wait on the approval and the notes that say why."""
        r = timeline.analyze(fixture("short-sale.json"))
        rows = by_key(r)
        for key in ("loan_app", "inspection", "loan_approval"):
            self.assertTrue(rows[key]["waits_on_approval"], key)
        self.assertFalse(rows["deposit"]["waits_on_approval"])  # Phase 1 counts from the Effective Date
        for key in ("short_sale_closing_replaced", "short_sale_gg", "short_sale_waiting"):
            self.assertIn(key, r["note_keys"])
        self.assertNotIn("no_closing_date", r["note_keys"])

    def test_before_approval_renders(self):
        r = timeline.analyze(fixture("short-sale.json"))
        doc = timeline_render.build_html(r, {}, sample=True)
        for x in r["pending"]:  # the pending rows render with their rule, since they have no date yet
            self.assertIn(timeline_render.esc(x["rule"]), doc)
        self.assertIsNone(r["contingencies_end"])  # no "main protections run through" date before the approval
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
        self.assertEqual(r["first_deadline"]["key"], "inspection")  # TL-204: the next critical row, not the Loan Application
        self.assertIn("Done Sep 26", timeline_render.build_html(r, {}, False))
        text = timeline_render.ics(r)
        self.assertNotIn("Initial Escrow Deposit", text)
        self.assertEqual(text.count("BEGIN:VEVENT"), len([x for x in r["rows"] if not x["lender"]]) - 1)

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
        self.assertIn("Columbus Day", note)
        self.assertIn("Tue Oct 13", note)

    def test_walkthrough_has_no_time(self):
        rows = by_key(timeline.analyze(fixture("buyer-fha.json")))
        self.assertTrue(rows["walkthrough"]["no_time"])
        self.assertNotIn("PM", rows["walkthrough"]["display"])
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-10-31"  # Sat: closing Mon Nov 2, walk-through on closing day
        rows = by_key(timeline.analyze(deal))
        self.assertTrue(rows["walkthrough"]["no_time"])  # on closing day it reads "before Closing", still no time
        self.assertEqual(rows["walkthrough"]["when"][:10], rows["closing"]["when"][:10])
        self.assertEqual(rows["closing"]["when"][:10], "2026-11-02")

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
        self.assertTrue(rows["carpet"]["by_closing"])
        keys = [x["key"] for x in r["rows"]]
        self.assertLess(keys.index("carpet"), keys.index("closing"))
        deal["deadlines"][0].update(days=2, time="17:00")
        self.assertEqual(by_key(timeline.analyze(deal))["carpet"]["when"], "2026-10-28 17:00")

    def test_title_by(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["title_by"] = "buyer"
        r = timeline.analyze(deal)
        self.assertEqual(by_key(r)["title"]["party"], "Buyer")
        self.assertNotIn("title_by_unknown", r["note_keys"])
        del deal["contract"]["title_by"]
        self.assertIn("title_by_unknown", timeline.analyze(deal)["note_keys"])
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
        self.assertIn("rider_not_read", r["note_keys"])
        self.assertTrue(any("Private Well and Septic" in n for n in r["agent_notes"]))  # names the rider

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
        self.assertIn("short_sale_after_deadline", r["flag_keys"])
        self.assertTrue(any("Nov 23, 2026" in f for f in r["flags"]))
        deal["contract"]["short_sale_approval_received"] = "2027-01-04"
        r = timeline.analyze(deal)
        self.assertIn("short_sale_after_expiration", r["flag_keys"])
        self.assertTrue(any("Dec 23, 2026" in f for f in r["flags"]))
        deal["contract"]["short_sale_approval_received"] = "2026-11-02"
        keys = timeline.analyze(deal)["flag_keys"]
        self.assertFalse({"short_sale_after_deadline", "short_sale_after_expiration"} & set(keys))

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
        keys = timeline.analyze(deal)["note_keys"]
        self.assertIn("effective_after_report", keys)
        self.assertIn("amendment_after_report", keys)
        deal["what_if"] = True
        r = timeline.analyze(deal)
        self.assertNotIn("effective_after_report", r["note_keys"])
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
        self.assertIn("rules_unknown", r["note_keys"])
        del deal["rules"]["day_count"]
        with self.assertRaisesRegex(timeline.DealError, "day_count"):
            timeline.analyze(deal)

    def test_short_sale_backup_offers_note(self):
        """TL-122: Rider G Para. 7, option (a) when neither box is checked."""
        r = timeline.analyze(fixture("short-sale.json"))
        self.assertIn("short_sale_backup", r["note_keys"])
        self.assertTrue(any("7(a)" in n for n in r["agent_notes"]))  # option (a), the one that applies

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


class SecondPass(unittest.TestCase):
    """TL-201 to TL-221 (audit 2026-09-29, second pass)."""

    def test_revision_note_quotes_the_footer_only_when_read_from_it(self):
        """TL-201"""
        d = fixture("buyer-fha.json")
        d["contract"]["form_revision"] = "Rev. 6/24"
        notes = timeline.analyze(d)["chat_notes"]
        self.assertTrue(any("revision given" in n for n in notes))
        self.assertFalse(any("footer reads" in n for n in notes))
        d["contract"]["form_revision_source"] = "footer"
        self.assertTrue(any("footer reads" in n for n in timeline.analyze(d)["chat_notes"]))

    def test_summary_says_after_that_once(self):
        """TL-202"""
        for side in ("buyer", "seller"):
            d = fixture("buyer-fha.json")
            d["side"] = side
            r = timeline.analyze(d)
            self.assertTrue(r["open_rights"])
            doc = timeline_render.build_html(r, {}, sample=True)
            lead = doc.split('<div class="why">')[1].split("</div>")[0]
            self.assertNotIn("after that", lead)
            self.assertEqual(lead.count("After that"), 1)
            self.assertIn("rights that stay open:", lead)

    def test_financing_consistency_notes(self):
        """TL-203: Rider F fields with only Rider E are named, not dropped silently; the cash title default on a
        financed deal is questioned."""
        d = fixture("buyer-fha.json")
        d["contract"]["appraisal_days"] = 21
        d["contract"]["title_evidence_days_before"] = 5
        r = timeline.analyze(d)
        self.assertIn("appraisal_without_rider_f", r["note_keys"])
        self.assertIn("title_days_financing", r["note_keys"])
        self.assertNotIn("appraisal_due", by_key(r))
        d["contract"]["title_evidence_days_before"] = 15
        del d["contract"]["appraisal_days"]
        r = timeline.analyze(d)
        self.assertNotIn("title_days_financing", r["note_keys"])
        self.assertNotIn("appraisal_without_rider_f", r["note_keys"])

    def test_amendment_note_uses_the_brand_color(self):
        """TL-205"""
        doc = timeline_render.build_html(timeline.analyze(fixture("seller-amended.json")), {}, sample=True)
        self.assertIn('class="note-brand"', doc)
        self.assertNotIn('class="note-good"', doc)

    def test_money_check(self):
        """TL-208: deposits + loan + balance vs. price, and the pre-approval vs. the loan."""
        d = fixture("buyer-fha.json")  # $365,000; $11,000 deposit from deposit_amount_str
        d["contract"].update(loan_amount=348000, balance_to_close=6000, preapproval_amount=350000)
        r = timeline.analyze(d)
        self.assertNotIn("money_mismatch", r["note_keys"])
        self.assertNotIn("preapproval_below_loan", r["note_keys"])
        d["contract"].update(price=372000, preapproval_amount=340000)  # a counter moved the price, not the loan
        r = timeline.analyze(d)
        self.assertIn("money_mismatch", r["note_keys"])
        self.assertIn("preapproval_below_loan", r["note_keys"])
        d["contract"].pop("balance_to_close")
        d["contract"]["loan_amount"] = 362000  # no balance given: $11,000 + $362,000 passes the $372,000 price
        self.assertIn("money_mismatch", timeline.analyze(d)["note_keys"])
        with self.assertRaisesRegex(timeline.DealError, "loan_amount"):
            timeline.money_check({"loan_amount": "a lot"}, 365000)

    def test_rider_u_and_para_6b(self):
        """TL-209: Rider U alone says why Para. 6(b)'s windows aren't dated; a tenant dates them."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = ["E", "U"]
        self.assertIn("rider_u_6b", timeline.analyze(d)["note_keys"])
        d["contract"]["tenants"] = True
        r = timeline.analyze(d)
        self.assertNotIn("rider_u_6b", r["note_keys"])
        rows = by_key(r)
        self.assertEqual(rows["lease_disclosure"]["when"], "2026-09-30 23:59")  # 5 days after Fri Sep 25
        self.assertIsNone(rows["lease_review"]["when"])  # runs from the receipt of the leases

    def test_rider_gg_rolled_start_note(self):
        """TL-210: day 3 on a Sunday rolls to Monday; the cancel window counts from Monday, and the note gives the
        reading from Sunday."""
        d = fixture("buyer-fha.json")
        d["contract"].update(effective_date="2026-09-24", riders=["E", "GG"])
        r = timeline.analyze(d)
        rows = by_key(r)
        self.assertEqual(rows["compensation_agreement"]["when"][:10], "2026-09-28")
        self.assertEqual(rows["compensation_cancel"]["when"][:10], "2026-10-01")
        self.assertIn("gg_rolled_start", r["note_keys"])
        self.assertTrue(any("Wed Sep 30" in n for n in r["agent_notes"]))
        d["contract"]["effective_date"] = "2026-09-25"  # day 3 is a Monday: nothing to read two ways
        self.assertNotIn("gg_rolled_start", timeline.analyze(d)["note_keys"])

    def test_small_fixes(self):
        """TL-211: Check lines end with a period and aren't repeated; an agent note that restates a script note is
        dropped; the short sale copy row reads once as a receipt; the Prepared date doesn't wrap."""
        d = fixture("buyer-fha.json")
        d["flags"] = ["Loan approval deadline is within 5 days of closing: little room if financing slips"]
        d["contract"]["preapproval_expires"] = "2026-10-20"
        d["agent_notes"] = ["The buyer's pre-approval expires Oct 20, 2026, before closing: ask the lender to update it"]
        r = timeline.analyze(d)
        self.assertTrue(all(f.endswith(".") for f in r["flags"]))
        self.assertEqual(len(r["flags"]), len({f.lower() for f in r["flags"]}))
        self.assertEqual(sum("pre-approval" in n for n in r["agent_notes"]), 1)
        s = timeline.analyze(fixture("short-sale.json"))
        self.assertEqual(by_key(s)["short_sale_copy"]["rule"], "Runs from the seller's receipt of the short sale approval")
        self.assertIn('<span class="nw">', timeline_render.build_html(r, {}, sample=True))

    def test_preapproval_expiry_on_a_pending_short_sale(self):
        """TL-212: no closing date yet, so the expiry is compared with the approval deadline plus the closing days."""
        d = fixture("short-sale.json")
        d["contract"]["preapproval_expires"] = "2026-12-16"
        r = timeline.analyze(d)
        self.assertIn("preapproval_expires", r["note_keys"])
        self.assertTrue(any("Nov 1, 2026" in n for n in r["agent_notes"]))  # Dec 16 minus 45 days
        d["contract"]["preapproval_expires"] = "2027-02-01"
        self.assertNotIn("preapproval_expires", timeline.analyze(d)["note_keys"])

    def test_extension_gives_both_readings(self):
        """TL-214: 8 days from Fri Sep 25 is Sat Oct 3, rolled to Mon Oct 5. An amendment to 13 days: Thu Oct 8 (safe,
        used); 5 days added to Mon Oct 5 is Sat Oct 10, rolled past Columbus Day to Tue Oct 13 (the note)."""
        d = fixture("buyer-fha.json")
        d["contract"]["inspection_days"] = 8
        d["amendments"] = [{"date": "2026-09-26", "description": "EA-4", "changes": {"inspection_days": 13}}]
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["inspection"]["when"][:10], "2026-10-08")
        self.assertIn("extension_reading:inspection", r["note_keys"])
        self.assertTrue(any("Tue Oct 13" in n and "Thu Oct 8" in n for n in r["agent_notes"]))
        d["contract"]["inspection_days"] = 10  # Mon Oct 5 didn't roll: one reading
        d["amendments"][0]["changes"]["inspection_days"] = 15
        self.assertNotIn("extension_reading:inspection", timeline.analyze(d)["note_keys"])

    def test_header_chip_lists_riders_on_both_forms(self):
        """TL-216, TL-217"""
        self.assertEqual(timeline.analyze(fixture("buyer-fha.json"))["contract_label"], "AS IS · Riders E, H")
        s = fixture("standard-riders.json")
        r = timeline.analyze(s)
        self.assertTrue(r["contract_label"].startswith("Standard"))
        self.assertIn("Rider", r["contract_label"])
        self.assertFalse(any("STANDARD" in x["source"] for x in r["rows"] + r["pending"]))

    def test_strip_tick_labels_clear_the_leaders(self):
        """TL-218: no tick label sits on a leader running down to a label below the line."""
        import re
        for name in ("standard-riders.json", "seller-amended.json", "buyer-fha.json"):
            t = timeline.analyze(fixture(name))
            svg = timeline_render.strip(t, {"Buyer": "#111", "Seller": "#222", "Both": "#333"})
            mid = float(re.search(r'y1="([\d.]+)"', svg).group(1))
            inside = []  # points of every leader inside the tick labels' row (mid + 5 to mid + 15)
            for pts in re.findall(r'<polyline points="([^"]+)"', svg):
                xy = [tuple(map(float, p.split(","))) for p in pts.split()]
                for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
                    for i in range(101):
                        px, py = x1 + (x2 - x1) * i / 100, y1 + (y2 - y1) * i / 100
                        if mid + 5 <= py <= mid + 15:
                            inside.append(px)
            ticks = list(map(float, re.findall(r'<text x="([\d.]+)"[^>]*class="tk"', svg)))
            self.assertTrue(ticks)
            for x in ticks:
                self.assertFalse(any(abs(px - x) <= 12 for px in inside), (name, x))


class AdditionalDeposit(unittest.TestCase):
    """The Additional Deposit row comes from the number, the words or the period: a deal file with only the numeric
    amount used to lose this critical deadline without a word."""

    def test_numeric_amount_alone_makes_the_row(self):
        deal = fixture("standard-riders.json")
        c = deal["contract"]
        for k in ("additional_deposit_amount_str", "additional_deposit_amount", "additional_deposit_days"):
            c.pop(k, None)
        self.assertNotIn("add_deposit", by_key(timeline.analyze(deal)))
        c["additional_deposit_amount"] = 10000
        row = by_key(timeline.analyze(deal))["add_deposit"]
        self.assertTrue(row["critical"])
        self.assertIn("$10,000", row["action"])


class ThirdPass(unittest.TestCase):
    """Eval iteration 4 findings (TL-223 to TL-238)."""

    COLORS = {"Buyer": "#111", "Seller": "#222", "Both": "#333"}

    def test_pending_rows_say_pending_in_the_date_cell(self):
        """TL-224: the date column reads "Pending"; the rule moves under the deadline's name."""
        r = timeline.analyze(fixture("buyer-fha.json"))
        self.assertTrue(r["pending"])
        doc = timeline_render.build_html(r, {}, sample=True)
        self.assertIn('<td class="n"><i>Pending</i></td>', doc)
        self.assertIn("· Runs from receipt of", doc)

    def test_before_closing_roll_toward_closing_is_flagged(self):
        """TL-226: survey 5 days before a Fri Oct 30 closing is Sun Oct 25, extended to Mon Oct 26 (Standard F); the
        Check line gives Fri Oct 23 as the safe date. An override clears it."""
        d = fixture("buyer-fha.json")
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["survey"]["when"][:10], "2026-10-26")
        self.assertIn("before_closing_rolled", r["flag_keys"])
        self.assertIn("Fri Oct 23", r["flags"][r["flag_keys"].index("before_closing_rolled")])
        d["contract"]["date_overrides"] = {"survey": "2026-10-23"}
        self.assertNotIn("before_closing_rolled", timeline.analyze(d)["flag_keys"])

    def test_end_of_day_question_only_when_a_date_shows_no_time(self):
        """TL-227: a deadline that sets its own time (5:00 PM) doesn't need the contract's end of day."""
        d = {"side": "buyer", "state": "OH", "report_date": "2026-11-01",
             "contract": {"form_family": "other", "form": "Purchase Agreement", "effective_date": "2026-11-20"},
             "rules": {"day_count": "calendar"},
             "deadlines": [{"key": "dd", "label": "Due Diligence Ends", "basis": "after", "days": 7, "party": "Buyer",
                            "time": "17:00"}]}
        r = timeline.analyze(d)
        note = r["agent_notes"][r["note_keys"].index("rules_unknown")]
        self.assertNotIn("when a day ends", note)
        d["deadlines"].append({"key": "x", "label": "Other Deadline", "basis": "after", "days": 3, "party": "Buyer"})
        r = timeline.analyze(d)
        self.assertIn("when a day ends", r["agent_notes"][r["note_keys"].index("rules_unknown")])

    def test_blank_periods_get_default_notes(self):
        """TL-229: deposit, loan application, loan approval and inspection (or Rider L) blanks each get a note."""
        d = fixture("buyer-fha.json")
        for k in ("deposit_days", "loan_application_days", "loan_approval_days", "inspection_days"):
            d["contract"].pop(k)
        keys = timeline.analyze(d)["note_keys"]
        for k in ("default:deposit", "default:loan_app", "default:loan_approval", "default:inspection"):
            self.assertIn(k, keys)
        self.assertNotIn("default:inspection", timeline.analyze(fixture("buyer-fha.json"))["note_keys"])
        d = fixture("standard-riders.json")
        d["contract"]["riders"] = ["L"]
        d["contract"].pop("inspection_days", None)
        r = timeline.analyze(d)
        note = r["agent_notes"][r["note_keys"].index("default:inspection")]
        self.assertIn("(L)", note)

    def test_unknown_contract_keys_warn(self):
        """TL-230: a misspelled field comes back as a warning, in the contract and in an amendment's changes."""
        d = fixture("buyer-fha.json")
        self.assertEqual(timeline.analyze(d)["warnings"], [])
        d["contract"]["inspection_dayz"] = 7
        d["amendments"] = [{"date": "2026-09-28", "changes": {"closing_dat": "2026-11-06"}}]
        r = timeline.analyze(d)
        self.assertEqual(r["warning_keys"], ["unknown_key", "unknown_key"])
        self.assertIn("inspection_dayz", r["warnings"][0])
        self.assertIn("closing_dat", r["warnings"][1])

    def test_amendment_named_by_its_form(self):
        """TL-231: never "Amendment 1"; the name when given, else its place in signing order."""
        d = fixture("buyer-fha.json")
        d["amendments"] = [{"date": "2026-12-01", "description": "Extend", "changes": {}}]
        r = timeline.analyze(d)
        note = r["agent_notes"][r["note_keys"].index("amendment_after_report")]
        self.assertTrue(note.startswith("The first amendment"))
        d["amendments"][0]["name"] = "Extension Addendum (EA-4)"
        r = timeline.analyze(d)
        self.assertTrue(r["agent_notes"][r["note_keys"].index("amendment_after_report")].startswith(
            "The Extension Addendum (EA-4)"))
        self.assertEqual(r["history"][0]["name"], "Extension Addendum (EA-4)")

    def test_rider_wording(self):
        """TL-232: Rider A approval missed ends the contract; TL-233: a VA deal says VA, not FHA/VA."""
        d = fixture("buyer-fha.json")
        d["contract"].update(riders=["A", "E"], association_approval=True, financing="va")
        rows = by_key(timeline.analyze(d))
        self.assertIn("terminates automatically", rows["assoc_approval"]["if_missed"])
        self.assertTrue(rows["fha_va_election"]["label"].startswith("VA "))
        d["contract"].update(riders=["B", "E"], hoa=True)
        self.assertIn("not automatic", by_key(timeline.analyze(d))["assoc_approval"]["if_missed"])

    def test_money_note_asks_the_agent(self):
        """TL-234: the note is a question the agent can answer, not an instruction to Claude."""
        d = fixture("buyer-fha.json")
        d["contract"].update(loan_amount=350000, balance_to_close=1000)
        r = timeline.analyze(d)
        note = r["agent_notes"][r["note_keys"].index("money_mismatch")]
        self.assertTrue(note.endswith("?"))
        self.assertNotIn("ask the agent", note)

    def test_gg_rolled_note_gives_one_reading_and_the_safe_date(self):
        """TL-235: Juniper Hollow: GG's agreement day Sun Sep 27 rolls to Mon Sep 28; the window used ends Thu Oct 1 and
        the buyer's safe date is Wed Sep 30; the seller view treats the right as open through Oct 1."""
        d = fixture("buyer-fha.json")
        d["contract"].update(effective_date="2026-09-24", riders=["E", "H", "GG"])
        r = timeline.analyze(d)
        note = r["agent_notes"][r["note_keys"].index("gg_rolled_start")]
        self.assertIn("ends Thu Oct 1", note)
        self.assertIn("by Wed Sep 30", note)
        r = timeline.analyze(d, "seller")
        self.assertIn("open through Thu Oct 1", r["agent_notes"][r["note_keys"].index("gg_rolled_start")])

    def test_deposit_action_from_number(self):
        """TL-236: the initial deposit's amount comes from the number when the words aren't given."""
        d = fixture("buyer-fha.json")
        d["contract"].pop("deposit_amount_str")
        d["contract"]["deposit_amount"] = 11000
        self.assertIn("$11,000", by_key(timeline.analyze(d))["deposit"]["action"])

    def test_moved_lists_closing_first(self):
        """TL-238: the closing leads the moved list; the rest stay in date order."""
        d = fixture("buyer-fha.json")
        d["amendments"] = [{"date": "2026-09-28", "changes": {"closing_date": "2026-11-06", "loan_approval_days": 37}}]
        moved = timeline.analyze(d)["moved"]
        self.assertEqual(moved[0]["label"], "Closing")
        self.assertGreater(len(moved), 2)

    def test_strip_done_rows_read_as_done(self):
        """TL-228: a done deposit isn't labeled like an open deadline on the strip."""
        d = fixture("buyer-fha.json")
        d["completed"] = {"deposit": "2026-09-26"}
        svg = timeline_render.strip(timeline.analyze(d), self.COLORS)
        self.assertIn("Deposit · Done", svg)
        self.assertNotIn("Deposit · 9/28", svg)


class FourthPass(unittest.TestCase):
    """Eval iteration 5 friction and grading (TL-239 to TL-255)."""

    def quick(self, **rules):
        """A one-deadline quick question on another state's contract (eval 3), no closing date."""
        return {"side": "buyer", "state": "OH", "report_date": "2026-11-20",
                "rules": {"day_count": "calendar", **rules},
                "contract": {"form_family": "other", "effective_date": "2026-11-20"},
                "deadlines": [{"key": "due_diligence", "label": "Due Diligence Period Ends", "basis": "after", "days": 7,
                               "party": "Buyer", "time": "17:00"}]}

    def test_rider_h_box_a_only(self):
        """TL-239: `insurance_coverage` records box (a) alone; the row is the homeowner's one, not "as checked"."""
        d = fixture("buyer-fha.json")
        r = timeline.analyze(d)
        self.assertIn("rider_h_boxes", r["note_keys"])  # not recorded: asked
        self.assertIn("as checked", by_key(r)["insurance"]["action"])
        for coverage in ("homeowners", "Homeowner's"):
            d["contract"]["insurance_coverage"] = coverage
            r = timeline.analyze(d)
            rows = by_key(r)
            self.assertEqual(rows["insurance"]["label"], "Homeowner's Insurance Contingency Ends")
            self.assertNotIn("as checked", rows["insurance"]["action"])
            self.assertNotIn("flood_insurance", rows)
            self.assertNotIn("rider_h_boxes", r["note_keys"])
            self.assertEqual(r["warning_keys"], [])
        d["contract"]["insurance_coverage"] = "flood"  # (b) only: the one date the rider has may sit in insurance_days
        rows = by_key(timeline.analyze(d))
        self.assertNotIn("insurance", rows)
        self.assertEqual(rows["flood_insurance"]["when"][:10], "2026-10-05")
        d["contract"]["insurance_coverage"] = "both"
        self.assertTrue({"insurance", "flood_insurance"} <= set(by_key(timeline.analyze(d))))
        d["contract"]["insurance_coverage"] = "wind"
        with self.assertRaisesRegex(timeline.DealError, "insurance_coverage"):
            timeline.analyze(d)

    def test_flood_zone_unknown_note_with_date(self):
        """TL-240, TL-241: an unrecorded flood zone is asked, with the date the window would have."""
        d = fixture("buyer-fha.json")
        r = timeline.analyze(d)
        self.assertIn("flood_zone_unknown", r["note_keys"])
        alt = next(x for x in r["if_changed"] if x["note_key"] == "flood_zone_unknown")
        self.assertEqual([(x["key"], x["date_display"]) for x in alt["rows"]], [("flood_elevation", "Thu Oct 15")])
        self.assertIn("Thu Oct 15", r["agent_notes"][r["note_keys"].index("flood_zone_unknown")])
        for zone in ("none", "X"):
            d["contract"]["flood_zone"] = zone
            self.assertNotIn("flood_zone_unknown", timeline.analyze(d)["note_keys"])

    def test_questioned_fields_give_the_other_date(self):
        """TL-241: appraisal_days without Rider F and a title evidence period that's the other financing's default
        come with the dates that apply if the answer changes."""
        d = fixture("buyer-fha.json")
        d["contract"].update(appraisal_days=21, title_evidence_days_before=5)
        r = timeline.analyze(d)
        alts = {x["note_key"]: x for x in r["if_changed"]}
        self.assertEqual([x["key"] for x in alts["appraisal_without_rider_f"]["rows"]], ["appraisal_due", "appraisal"])
        self.assertEqual(alts["title_days_financing"]["rows"][0]["date_display"], "Thu Oct 15")  # 15 days before closing
        self.assertNotIn("appraisal_due", by_key(r))  # the run itself is unchanged

    def test_year_built_and_rider_p(self):
        """TL-242: year_built before 1978 without Rider P, and Rider P without year_built, are both asked; Rider P
        dates the 10-day risk assessment unless it was waived."""
        d = fixture("buyer-fha.json")
        d["contract"]["year_built"] = 1965
        r = timeline.analyze(d)
        self.assertIn("year_built_without_rider_p", r["note_keys"])
        self.assertIn("lead_paint", by_key(r))
        d["contract"].pop("year_built")
        d["contract"]["riders"] = ["E", "H", "P"]
        r = timeline.analyze(d)
        self.assertIn("rider_p_year_built", r["note_keys"])
        self.assertIn("lead_paint", by_key(r))
        d["contract"]["lbp_waived"] = True
        self.assertNotIn("lead_paint", by_key(timeline.analyze(d)))
        d["contract"].update(year_built=1994, riders=["E", "H"], lbp_waived=False)
        r = timeline.analyze(d)
        self.assertFalse({"rider_p_year_built", "year_built_without_rider_p"} & set(r["note_keys"]))

    def test_quick_question_notes(self):
        """TL-243: a business-day count doesn't ask the short-period rule; no closing-date note when nothing counts
        back from closing; a future Effective Date without a closing isn't told to set what_if."""
        r = timeline.analyze(self.quick(day_count="business"))
        note = r["agent_notes"][r["note_keys"].index("rules_unknown")]
        self.assertNotIn("calendar days", note)
        self.assertNotIn("no_closing_date", r["note_keys"])
        cal = timeline.analyze(self.quick())
        self.assertIn("calendar days", cal["agent_notes"][cal["note_keys"].index("rules_unknown")])
        early = self.quick()
        early["report_date"] = "2026-11-10"
        r = timeline.analyze(early)
        self.assertNotIn("what_if", r["agent_notes"][r["note_keys"].index("effective_after_report")])
        before = self.quick()
        before["deadlines"].append({"key": "walk", "label": "Walk-Through", "basis": "before", "days": 1, "party": "Buyer"})
        self.assertIn("no_closing_date", timeline.analyze(before)["note_keys"])

    def test_low_appraisal_label_matches(self):
        """TL-244: the strip's short name for the low-appraisal notice matches its label."""
        d = fixture("standard-riders.json")
        d["contract"]["riders"] = ["F", "L"]
        row = by_key(timeline.analyze(d))["appraisal"]
        self.assertTrue(row["label"].startswith(row["short"]))

    def test_repair_limits_in_dollars(self):
        """TL-245: the Standard form's repair limits come from the script (contract_forms), never by hand; none on AS IS
        or with Rider K."""
        d = fixture("standard-riders.json")
        d["contract"]["price"] = 445000
        r = timeline.analyze(d)
        self.assertEqual((r["repair_limits"]["general"], r["repair_limits"]["blank"]), (6675, ["general", "wdo", "permit"]))
        self.assertIn("repair_limits_blank", r["note_keys"])
        self.assertIn("$6,675", r["agent_notes"][r["note_keys"].index("repair_limits_blank")])
        d["contract"]["repair_limits"] = {"general": 5000, "wdo": 0.01, "permit": 2000}
        r = timeline.analyze(d)
        self.assertEqual((r["repair_limits"]["wdo"], r["repair_limits"]["blank"]), (4450, []))
        self.assertNotIn("repair_limits_blank", r["note_keys"])
        d["contract"]["riders"] = ["K"]
        self.assertIsNone(timeline.analyze(d)["repair_limits"])
        self.assertIsNone(timeline.analyze(fixture("buyer-fha.json"))["repair_limits"])

    def test_agent_note_keyed_to_a_script_note_is_merged(self):
        """TL-247: an agent note keyed to a script note (or to a deadline one covers) is dropped; script notes with the
        same key are one line."""
        d = fixture("buyer-fha.json")
        d["contract"].update(loan_amount=358000, balance_to_close=1000)  # doesn't add up: money_mismatch
        d["report_date"] = "2026-10-02"  # the deposit is past and not done
        d["agent_notes"] = [{"key": "money_mismatch", "text": "Para. 2's balance wasn't updated by the counter; which figures stand?"},
                            {"key": "deposit", "text": "No escrow receipt in the package: was the deposit delivered?"},
                            {"key": "other", "text": "The seller asked to keep the curtains."}, "A plain note."]
        r = timeline.analyze(d)
        self.assertEqual(sorted(r["merged_agent_notes"]), ["deposit", "money_mismatch"])
        self.assertIn("The seller asked to keep the curtains.", r["agent_notes"])
        self.assertIn("A plain note.", r["agent_notes"])
        self.assertFalse(any("balance wasn't updated" in n for n in r["agent_notes"]))
        self.assertEqual(len(r["note_keys"]), len(set(r["note_keys"])))

    def test_extension_reading_open_is_flagged(self):
        """TL-248: when the reading used has ended but the later one is still open on the report date, it's a Check
        line on the report too (eval 6: Oct 8 used, Oct 13 on the other reading, report Oct 12)."""
        d = fixture("buyer-fha.json")
        d["contract"].update(effective_date="2026-09-23", inspection_days=10, financing="cash", closing_date="2026-11-06")
        d["amendments"] = [{"date": "2026-10-01", "name": "Extension Addendum (EA-4)",
                            "changes": {"inspection_days": 15}}]
        d["report_date"] = "2026-10-12"
        r = timeline.analyze(d)
        self.assertIn("extension_reading_open:inspection", r["flag_keys"])
        self.assertIn("Tue Oct 13", r["flags"][r["flag_keys"].index("extension_reading_open:inspection")])
        d["report_date"] = "2026-10-14"  # both readings have ended
        self.assertNotIn("extension_reading_open:inspection", timeline.analyze(d)["flag_keys"])
        d["report_date"] = "2026-10-12"
        d["completed"] = {"inspection": "2026-10-08"}
        self.assertNotIn("extension_reading_open:inspection", timeline.analyze(d)["flag_keys"])

    def test_occupancy_agreements_are_critical(self):
        """TL-249: Riders T and U let either party cancel when the agreement isn't delivered."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = ["E", "H", "T", "U"]
        d["contract"]["seller_occupancy_days"] = 5
        rows = by_key(timeline.analyze(d))
        self.assertTrue(rows["pre_closing_agreement"]["critical"])
        self.assertTrue(rows["post_closing_agreement"]["critical"])

    def test_ics_leaves_lender_targets_out_unless_asked(self):
        """TL-252: the calendar has contract dates only; --lender-dates adds the lender's, titled Lender Target."""
        t = timeline.analyze(fixture("buyer-fha.json"))
        self.assertTrue(any(r["lender"] for r in t["rows"]))
        self.assertNotIn("Closing Disclosure", timeline_render.ics(t))
        text = timeline_render.ics(t, lender_dates=True)
        self.assertIn("SUMMARY:Lender Target: Clear to Close / Closing Disclosure", text)
        self.assertEqual(text.count("BEGIN:VEVENT"), len(t["rows"]))


class FifthPass(unittest.TestCase):
    """Eval iteration 6 fixes (TL-256 to TL-259)."""

    def test_lender_rows_are_never_critical(self):
        """TL-256: the Closing Disclosure is a lender's target: no star on the client's table, no calendar reminder."""
        t = timeline.analyze(fixture("buyer-fha.json"))
        rows = by_key(t)
        self.assertTrue(rows["clear_to_close"]["lender"])
        self.assertFalse(rows["clear_to_close"]["critical"])
        self.assertFalse(any(r["critical"] for r in t["rows"] if r["lender"]))
        self.assertNotIn("Closing Disclosure ★", timeline_render.ics(t, lender_dates=True))

    def test_default_note_says_not_given_unless_known_blank(self):
        """TL-257: a term missing from the deal file is "not given"; "blank" only when `blanks` says the copy showed it."""
        d = fixture("buyer-fha.json")
        d["contract"].pop("deposit_days")
        r = timeline.analyze(d)
        title = by_key(r)["title"]
        self.assertIn("default:title", r["note_keys"])
        notes = {k: r["agent_notes"][i] for i, k in enumerate(r["note_keys"])}
        self.assertIn("not given", notes["default:title"])
        self.assertIn("not given", notes["default:deposit"])
        self.assertEqual(title["date_display"], "Thu Oct 15")
        d["contract"]["blanks"] = ["title_evidence_days_before"]
        r = timeline.analyze(d)
        notes = {k: r["agent_notes"][i] for i, k in enumerate(r["note_keys"])}
        self.assertIn("deadline blank", notes["default:title"])
        self.assertIn("not given", notes["default:deposit"])
        self.assertEqual(r["warning_keys"], [])  # `blanks` is a known field

    def test_rider_h_days_note_gives_both_readings(self):
        """TL-258: days written in Rider H's date blank don't say which way they count: the note and if_changed give
        the date counted back from closing too; `insurance_days_before` records that reading."""
        d = fixture("buyer-fha.json")  # insurance_days 10: Mon Oct 5 after the Effective Date, Tue Oct 20 before closing
        r = timeline.analyze(d)
        self.assertIn("insurance_days_reading", r["note_keys"])
        alt = next(x for x in r["if_changed"] if x["note_key"] == "insurance_days_reading")
        self.assertEqual([(x["key"], x["date_display"]) for x in alt["rows"]], [("insurance", "Tue Oct 20")])
        self.assertEqual(by_key(r)["insurance"]["date_display"], "Mon Oct 5")
        d["contract"]["insurance_days_before"] = d["contract"].pop("insurance_days")
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["insurance"]["date_display"], "Tue Oct 20")
        self.assertNotIn("insurance_days_reading", r["note_keys"])
        self.assertEqual(r["warning_keys"], [])

    def test_agent_note_keyed_to_a_row_joins_it(self):
        """TL-259: an agent note keyed to a deadline no script note covers merges with the row: one line with its date."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"]["riders"]) + ["GG"]
        d["agent_notes"] = [{"key": "compensation_agreement", "text": "It isn't in the package. Has it been signed?"},
                            {"key": "compensation_agreement", "text": "Ask the listing agent."}]
        r = timeline.analyze(d)
        self.assertEqual(r["joined_agent_notes"], ["compensation_agreement"])
        lines = [n for n in r["agent_notes"] if "Has it been signed" in n]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("Buyer's Broker Compensation Agreement Signed (Mon Sep 28): "))
        self.assertIn("Ask the listing agent.", lines[0])
        self.assertFalse(any(n == "Ask the listing agent." for n in r["agent_notes"]))


class ManualSmoke(unittest.TestCase):
    """The owner's manual smoke test, cases 6 to 8 (TL-261 to TL-265)."""

    def test_open_time_rule_reads_plain_on_the_report(self):
        """TL-261: an open time rule prints as "Not stated in the contract"; the question stays in the chat note."""
        deal = fixture("other-contract.json")
        deal["rules"] = {"day_count": "calendar", "end_time": "23:59", "weekend_holiday_rollover": "next_business_day"}
        r = timeline.analyze(deal)
        self.assertIn("rules_unknown", r["note_keys"])
        lines = {x["label"]: x["text"] for x in r["rules"]["lines"]}
        self.assertTrue(lines["Before-Closing Dates"].startswith("Not stated in the contract: "))
        self.assertNotIn("to confirm", timeline_render.build_html(r, {}, sample=True))

    def test_lender_line_only_with_lender_rows(self):
        """TL-262: the footer's lender-estimate line prints only when the report has a lender's target."""
        other = timeline.analyze(fixture("other-contract.json"))
        self.assertFalse(any(x["lender"] for x in other["rows"] + other["pending"]))
        self.assertNotIn("Lender dates are estimates", timeline_render.build_html(other, {}, sample=True))
        fha = timeline.analyze(fixture("buyer-fha.json"))
        self.assertTrue(any(x["lender"] for x in fha["rows"]))
        self.assertIn("Lender dates are estimates", timeline_render.build_html(fha, {}, sample=True))

    def test_contingency_window_is_never_done_before_its_date(self):
        """TL-264: the signed compensation agreement is done; Compensation Contingency Ends stays open (and critical)
        until its date, the same on every deal, and a done date before it is refused."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"]["riders"]) + ["GG"]
        d["completed"] = {"deposit": "2026-09-26", "compensation_agreement": "2026-09-26"}
        rows = by_key(timeline.analyze(d))
        self.assertTrue(rows["compensation_agreement"]["done"])
        self.assertFalse(rows["compensation_cancel"]["done"])
        self.assertTrue(rows["compensation_cancel"]["critical"])
        d["completed"]["compensation_cancel"] = "2026-09-26"  # Thu Oct 1 is still ahead
        with self.assertRaisesRegex(timeline.DealError, "compensation_cancel"):
            timeline.analyze(d)
        d["completed"]["compensation_cancel"] = "2026-10-01"  # on its date the window has run: fine
        self.assertTrue(by_key(timeline.analyze(d))["compensation_cancel"]["done"])

    def test_header_pieces_never_break_inside(self):
        """TL-265: the Prepared line is one unbroken piece, the parties line breaks only before a separator, and a
        fact row that wraps tightens to one line."""
        doc = timeline_render.build_html(timeline.analyze(fixture("buyer-fha.json")), {}, sample=True)
        self.assertIn('<span class="nw">Prepared for <b>', doc)
        self.assertRegex(doc, r'<div class="t2"><span class="nw">[^<]+</span> <span class="nw">· [^<]+</span> '
                              r'<span class="nw">/ [^<]+</span></div>')
        with open(os.path.join(ROOT, "skills", "contract-timeline", "assets", "timeline.css")) as f:
            css = f.read()
        self.assertIn(".factrow span{white-space:nowrap}", css.replace(".prep .nw,.t2 .nw,", ""))
        self.assertIn(".tightfacts .factrow", css)


if __name__ == "__main__":
    unittest.main()
