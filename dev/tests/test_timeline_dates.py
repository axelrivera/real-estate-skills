"""Contract timeline date math: holidays, business days, weekend and holiday rollover, time of day and time zones."""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

timeline, dates = load("contract-timeline", "timeline", "_shared.dates")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")


def fixture(name):
    """A fixture deal prepared on the day the fixtures assume (dev/golden.py), so its deadlines don't read as past."""
    with open(os.path.join(FIXTURES, name)) as f:
        deal = json.load(f)
    deal.setdefault("report_date", "2026-09-26")
    return deal


def by_key(result):
    return {r["key"]: r for r in result["rows"] + result["pending"]}


class Holidays(unittest.TestCase):
    def test_federal_holidays(self):
        """Observed and moving holidays; a Saturday New Year's Day is observed the Friday before (Jan 1 2028, 2033)."""
        for day, name in ((date(2026, 7, 3), "Independence Day (observed)"),  # July 4 2026 is a Saturday
                          (date(2026, 11, 26), "Thanksgiving Day"),
                          (date(2027, 12, 24), "Christmas Day (observed)"),
                          (date(2027, 12, 31), "New Year's Day (observed)"),
                          (date(2032, 12, 31), "New Year's Day (observed)"),
                          (date(2026, 10, 12), "Columbus Day"),
                          (date(2026, 12, 31), None)):
            with self.subTest(day=day):
                self.assertEqual(dates.holiday_name(day), name)
                self.assertEqual(dates.is_business_day(day), name is None)
        self.assertFalse(dates.is_business_day(date(2026, 9, 7)))  # Labor Day
        self.assertEqual(dates.add_business_days(date(2026, 9, 25), 3), date(2026, 9, 30))
        self.assertEqual(dates.add_business_days(date(2026, 10, 30), -3), date(2026, 10, 27))

    def test_contract_holiday_list_replaces_the_federal_one(self):
        """A contract that defines its own holidays (base "none") uses only its list."""
        own = dates.Holidays({date(2026, 11, 27): "Holiday (contract)"}, base="none")
        self.assertIsNone(dates.holiday_name(date(2026, 10, 12), own))
        self.assertEqual(dates.holiday_name(date(2026, 11, 27), own), "Holiday (contract)")

    def test_rollover_passes_a_contract_holiday(self):
        deal = fixture("other-contract.json")
        deal["contract"]["effective_date"] = "2026-11-24"  # + 3 days = Nov 27, a holiday the contract lists
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["earnest_money"]["when"], "2026-11-30 23:59")  # past the holiday and the weekend
        self.assertEqual(rows["walkaway_period"]["when"], "2026-12-01 17:00")
        self.assertIn("Holidays", [x["label"] for x in r["rules"]["lines"]])
        self.assertNotIn("Holiday (contract)", json.dumps(r))  # the placeholder name never reaches the report


class FarbarRollover(unittest.TestCase):
    """FAR/BAR (Standard F): calendar days; a period ending on a weekend or holiday runs to the end of the next business
    day; dates counted back from closing follow a moved closing."""

    def test_weekend_closing_extends(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-10-31"
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["closing"]["when"], "2026-11-02 10:00")
        self.assertEqual(rows["walkthrough"]["when"], "2026-11-02 10:00")  # Sun extends to closing day, before closing
        self.assertTrue(rows["walkthrough"]["no_time"])
        deal["contract"].update(closing_date="2026-10-30", date_overrides={"closing": "2026-11-06"})
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["closing"]["when"], "2026-11-06 10:00")
        self.assertEqual(rows["walkthrough"]["when"], "2026-11-05 23:59")
        self.assertTrue(rows["walkthrough"]["no_time"])

    def test_date_only_override_rolls_forward(self):
        """A date-only override on a Saturday extends; one with a time is kept."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["date_overrides"] = {"inspection": "2026-10-10", "deposit": "2026-09-27 15:00"}
        rows = by_key(timeline.analyze(deal))
        self.assertEqual(rows["inspection"]["when"], "2026-10-13 23:59")  # Sat, Sun, Columbus Day Mon
        self.assertEqual(rows["deposit"]["when"], "2026-09-27 15:00")

    def test_before_closing_row_rolled_onto_closing_day_is_due_by_closing(self):
        """FinCEN info 1 day before a Monday closing falls on Sunday and extends to Monday: due by the 10:00 AM closing,
        sorted before it. A before-closing date rolled toward closing is flagged until an override sets it."""
        deal = fixture("buyer-fha.json")
        deal["contract"].update(closing_date="2026-11-02", fincen_report=True)
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["fincen"]["when"], rows["closing"]["when"])
        self.assertTrue(rows["fincen"]["by_closing"])
        keys = [x["key"] for x in r["rows"]]
        self.assertLess(keys.index("fincen"), keys.index("closing"))
        # survey 5 days before the Fri Oct 30 closing is Sun Oct 25, extended to Mon Oct 26 (flagged); an override clears it
        d = fixture("buyer-fha.json")
        d["contract"]["date_overrides"] = {"survey": "2026-10-23"}
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["survey"]["when"][:10], "2026-10-23")
        self.assertNotIn("before_closing_rolled", r["flag_keys"])

    def test_closing_disclosure_counts_saturdays(self):
        """TRID business days count Saturdays: 3 back from a Monday closing are Sat, Fri, Thu."""
        deal = fixture("buyer-fha.json")
        deal["contract"]["closing_date"] = "2026-11-02"
        self.assertEqual(by_key(timeline.analyze(deal))["clear_to_close"]["when"][:10], "2026-10-29")


class OtherContractTimes(unittest.TestCase):
    """Another state's contract uses only its own time rules."""

    def test_deadline_time_and_rollover(self):
        """A deadline's own time and rollover win; a rolled period ends at the contract's end of day."""
        deal = fixture("other-contract.json")
        deal["contract"]["effective_date"] = "2026-11-21"
        deal["contract"].pop("date_overrides", None)
        deal["deadlines"] = [{"key": "option", "label": "Option Period Ends", "basis": "after", "days": 7, "party": "Buyer",
                              "time": "17:00", "rollover": False}]
        self.assertEqual(by_key(timeline.analyze(deal))["option"]["when"], "2026-11-28 17:00")  # a Saturday, not moved
        deal["deadlines"] = [{"key": "docs", "label": "Docs Review Ends", "basis": "event", "days": 2,
                              "received": "2026-10-01", "time": "17:00", "rollover": False, "party": "Buyer"}]
        self.assertEqual(by_key(timeline.analyze(deal))["docs"]["when"], "2026-10-03 17:00")  # event basis: same rules
        # a period moved past a weekend ends when the contract's days end, unless a rollover time is stated
        d = {"side": "buyer", "state": "OH", "report_date": "2026-09-26",
             "contract": {"form_family": "other", "form": "RPA-1", "effective_date": "2026-09-24", "closing_date": "2026-10-30"},
             "rules": {"day_count": "calendar", "end_time": "23:59", "weekend_holiday_rollover": "next_business_day"},
             "deadlines": [{"key": "em", "label": "Earnest Money Due", "basis": "after", "days": 3, "party": "Buyer"}]}
        for rules, want in (({}, "2026-09-28 23:59"), ({"end_time": "17:00"}, "2026-09-28 17:00"),
                            ({"end_time": "17:00", "rollover_time": "12:00"}, "2026-09-28 12:00")):
            d["rules"].update(rules)
            self.assertEqual(by_key(timeline.analyze(d))["em"]["when"], want, rules)

    def test_no_time_of_day_is_invented(self):
        """Only day_count is required; the other rules are asked and no time of day is made up."""
        deal = fixture("other-contract.json")
        deal["rules"] = {"day_count": "calendar"}
        deal["deadlines"].append({"key": "walk", "label": "Final Walk-Through", "basis": "before", "days": 1, "party": "Buyer"})
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertTrue(rows["walk"]["no_time"])
        self.assertNotIn("PM", rows["financing"]["display"])
        self.assertTrue(rows["walkaway_period"]["display"].endswith("5:00 PM"))  # its own stated time is kept
        self.assertIn("rules_unknown", r["note_keys"])
        # with the end of day unstated, the rules' End of Day line shows only when some dated row has no time
        deal = fixture("other-contract.json")
        deal["rules"] = {"day_count": "calendar"}
        deal["deadlines"] = [x for x in deal["deadlines"] if x["key"] == "walkaway_period"]
        deal["contract"].pop("closing_date")
        labels = lambda: [x["label"] for x in timeline.analyze(deal)["rules"]["lines"]]  # noqa: E731
        self.assertNotIn("End of Day", labels())
        deal["deadlines"].append({"key": "x", "label": "Other Deadline", "basis": "after", "days": 3, "party": "Buyer"})
        self.assertIn("End of Day", labels())

    def test_custom_walkthrough_is_a_day(self):
        """A walk-through (or any row marked `event`) shows its date alone unless the contract sets a time."""
        deal = fixture("other-contract.json")
        walk = {"key": "walkthrough", "label": "Final Walk-Through", "short": "Walk-Through", "basis": "before", "days": 1,
                "party": "Buyer", "critical": False, "source": "Para. 9"}
        deal["deadlines"].append(walk)
        row = by_key(timeline.analyze(deal))["walkthrough"]
        self.assertTrue(row["no_time"])
        self.assertEqual(row["display"], "Mon Dec 21")
        walk["time"] = "18:00"
        self.assertEqual(by_key(timeline.analyze(deal))["walkthrough"]["display"], "Mon Dec 21 · 6:00 PM")
        walk.pop("time")
        walk.update(key="final_look", label="Final Inspection Visit", event=True)
        self.assertTrue(by_key(timeline.analyze(deal))["final_look"]["no_time"])


class TimeZones(unittest.TestCase):
    """Times are local to the property: the zone comes from the state and county, asked only where it's split."""

    def test_zone_from_the_state_and_county(self):
        for state, county, zone, assumed in (("OH", None, "ET", False), ("TX", "El Paso", "MT", False),
                                             ("TX", "Travis", "CT", False), ("KY", "Warren", "CT", False),
                                             ("KY", "Fayette", "ET", True), ("TN", None, "CT", True),
                                             ("AZ", "Maricopa", "MST", False), ("Ohio", None, "ET", False),
                                             ("WA", None, "PT", False)):
            with self.subTest(state=state, county=county):
                deal = fixture("other-contract.json")
                deal.update(state=state, county=county)
                r = timeline.analyze(deal)
                self.assertEqual(r["time_zone"], zone)
                self.assertEqual("time_zone_assumed" in r["note_keys"], assumed)
        deal = fixture("other-contract.json")
        deal.update(state="TX", county="El Paso")  # another zone than the state's main one prints after the time
        self.assertTrue(by_key(timeline.analyze(deal))["walkaway_period"]["display"].endswith("5:00 PM MT"))
        deal = fixture("other-contract.json")
        for given, zone in (("Central", "CT"), ("America/Denver", "MT")):  # a zone the deal file states
            deal["time_zone"] = given
            self.assertEqual(timeline.analyze(deal)["time_zone"], zone)
        deal["time_zone"] = "GMT+5"
        with self.assertRaisesRegex(timeline.DealError, "time_zone"):
            timeline.analyze(deal)

    def test_florida_panhandle_and_split_counties(self):
        deal = fixture("buyer-fha.json")
        self.assertFalse(by_key(timeline.analyze(deal))["deposit"]["display"].endswith("T"))  # the state's zone: no suffix
        deal["county"] = "Escambia"
        r = timeline.analyze(deal)
        self.assertEqual(r["time_zone"], "CT")
        self.assertTrue(by_key(r)["deposit"]["display"].endswith(" CT"))
        deal["county"] = "Gulf"
        r = timeline.analyze(deal)
        self.assertIn("time_zone_split", r["note_keys"])  # the agent's question, never a client flag
        self.assertNotIn("time_zone_split", r["flag_keys"])
        deal["time_zone"] = "CT"
        self.assertNotIn("time_zone_split", timeline.analyze(deal)["note_keys"])


if __name__ == "__main__":
    unittest.main()
