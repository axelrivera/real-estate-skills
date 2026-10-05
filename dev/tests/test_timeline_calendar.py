"""Contract timeline outputs: the ICS calendar's structure, the timeline strip's geometry, and render wiring (HTML,
CLI, markdown template)."""
import contextlib
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

timeline, timeline_render = load("contract-timeline", "timeline", "render")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")
COLORS = {"Buyer": "#111", "Seller": "#222", "Both": "#333"}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        deal = json.load(f)
    deal.setdefault("report_date", "2026-09-26")
    return deal


def by_key(result):
    return {r["key"]: r for r in result["rows"] + result["pending"]}


def event(text, uid):
    """One VEVENT's lines, unfolded."""
    return text.split(f"UID:{uid}")[1].split("END:VEVENT")[0].replace("\r\n ", "")


class Calendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fha = timeline.analyze(fixture("buyer-fha.json"))

    def test_structure(self):
        """One event per contract row (lender targets left out), all-day events for end-of-day deadlines, an alarm per
        critical row, folded lines, a UTC stamp and UIDs stable across runs."""
        t = self.fha
        text = timeline_render.ics(t)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n"))
        contract = [r for r in t["rows"] if not r["lender"]]
        self.assertEqual(text.count("BEGIN:VEVENT"), len(contract))
        self.assertIn("DTSTART;VALUE=DATE:", text)
        self.assertEqual(text.count("BEGIN:VALARM"), sum(r["critical"] for r in contract))
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))
        self.assertRegex(text, r"DTSTAMP:\d{8}T\d{6}Z")
        self.assertEqual(re.findall(r"UID:[^\r]+", text), re.findall(r"UID:[^\r]+", timeline_render.ics(t)))
        deal = fixture("buyer-fha.json")
        deal["what_if"] = True  # every event of a what-if run says so
        text = timeline_render.ics(timeline.analyze(deal))
        self.assertEqual(text.count("SUMMARY:What-If: "), text.count("BEGIN:VEVENT"))

    def test_done_past_and_undated_rows_stay_out(self):
        d = fixture("buyer-fha.json")
        d["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(d)
        self.assertNotIn("UID:deposit-", timeline_render.ics(r))
        self.assertEqual(timeline_render.ics(r).count("BEGIN:VEVENT"), len([x for x in r["rows"] if not x["lender"]]) - 1)
        d = fixture("buyer-fha.json")
        d["report_date"] = "2026-10-01"  # the deposit is past and not done
        self.assertNotIn("UID:deposit-", timeline_render.ics(timeline.analyze(d)))
        r = timeline.analyze(fixture("short-sale.json"))  # before the approval most rows have no date
        text = timeline_render.ics(r)
        self.assertEqual(text.count("BEGIN:VEVENT"), len([x for x in r["rows"] if not x["done"] and not x["past"]]))
        self.assertNotIn("UID:loan_approval-", text)

    def test_lender_targets_only_when_asked(self):
        t = self.fha
        left = timeline_render.calendar_lender_rows(t)
        self.assertEqual({r["key"] for r in left}, {r["key"] for r in t["rows"] if r["lender"]})
        self.assertEqual(timeline_render.calendar_lender_rows(t, lender_dates=True), [])
        text = timeline_render.ics(t, lender_dates=True)
        self.assertEqual(text.count("BEGIN:VEVENT"), len(t["rows"]))
        self.assertIn("SUMMARY:Lender Target: ", text)
        self.assertEqual(text.count("BEGIN:VALARM"), sum(r["critical"] for r in t["rows"]))  # lender rows add no alarm
        note = timeline_render.lender_calendar_note(left)
        for lender_dates, printed in ((False, True), (True, False)):
            err = io.StringIO()
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
                timeline_render.build(t, "ics", tmp, {"agent": {}, "formats": ["ics"], "lender_dates": lender_dates})
            self.assertEqual(note in err.getvalue(), printed)

    def test_zone_reminders_and_sequence(self):
        deal = fixture("buyer-fha.json")
        deal["county"] = "Escambia"  # Central time
        deal["amendments"] = [{"date": "2026-09-26", "description": "Extend", "changes": {"loan_approval_days": 25}}]
        text = timeline_render.ics(timeline.analyze(deal))
        self.assertIn("TZID:America/Chicago", text)
        self.assertIn("DTSTART;TZID=America/Chicago:20261030T100000", text)
        self.assertIn("SEQUENCE:1", text)
        self.assertIn("TRIGGER:-PT15H", text)  # all-day: 9:00 AM the day before
        self.assertIn("TRIGGER:-P1D", text)  # timed closing: 24 hours ahead
        self.assertIn("TZID:America/New_York", timeline_render.ics(self.fha))
        gulf = fixture("buyer-fha.json")
        gulf["county"] = "Gulf"  # split county: the state's main zone until the agent confirms
        self.assertIn("DTSTART;TZID=America/New_York:20261030T100000", timeline_render.ics(timeline.analyze(gulf)))
        # another state's contract: the zone comes from the state, so timed events still carry it
        self.assertIn("DTSTART;TZID=America/New_York:20261222T140000",
                      timeline_render.ics(timeline.analyze(fixture("other-contract.json"))))
        az = fixture("other-contract.json")
        az["state"] = "AZ"  # no daylight saving: standard time only
        text = timeline_render.ics(timeline.analyze(az))
        self.assertIn("TZID:America/Phoenix", text)
        self.assertNotIn("BEGIN:DAYLIGHT", text)
        self.assertIn("DTSTART;TZID=America/Phoenix:20261222T140000", text)

    def test_untimed_rows_are_all_day(self):
        """A row due by closing and a walk-through are all-day items, never a second event at the closing's hour."""
        deal = fixture("other-contract.json")
        deal["deadlines"] += [{"key": "title_by_closing", "label": "Title Commitment Provided", "basis": "before", "days": 0,
                               "time": "closing", "party": "Seller", "critical": False},
                              {"key": "walkthrough", "label": "Final Walk-Through", "basis": "before", "days": 1,
                               "party": "Buyer", "critical": False}]
        r = timeline.analyze(deal)
        self.assertTrue(by_key(r)["title_by_closing"]["by_closing"])
        text = timeline_render.ics(r)
        self.assertIn("DTSTART;VALUE=DATE:20261222", event(text, "title_by_closing"))
        self.assertIn("DTSTART;VALUE=DATE:20261221", event(text, "walkthrough"))


class Strip(unittest.TestCase):
    """The page-one timeline strip: label placement, tick labels and mark positions."""

    def test_close_labels_never_overlap(self):
        marks = [(50, 120), (58, 100), (66, 110), (300, 90), (640, 120), (650, 100), (660, 90), (670, 130), (690, 80)]
        spots, _ = timeline_render.place_labels(marks, 740)
        boxes = [(side, lv, x0, x0 + w) for (side, lv, x0), (_, w) in zip(spots, marks)]
        for i, a in enumerate(boxes):
            self.assertTrue(a[2] >= 0 and a[3] <= 740)
            for b in boxes[i + 1:]:
                if a[:2] == b[:2]:
                    self.assertTrue(a[3] <= b[2] or b[3] <= a[2], (a, b))

    def test_tick_labels_clear_the_leaders(self):
        """No tick label sits on a leader running down to a label below the line."""
        for name in ("standard-riders.json", "seller-amended.json", "buyer-fha.json"):
            svg = timeline_render.strip(timeline.analyze(fixture(name)), COLORS)
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

    def test_marks_sit_on_their_own_day(self):
        """An 11:59 PM deadline is plotted on its own day's tick, never next to the next day's."""
        t = timeline.analyze(fixture("buyer-fha.json"))
        svg = timeline_render.strip(t, COLORS)
        eff = datetime.strptime(t["effective"]["date"], "%Y-%m-%d")
        days = (max(timeline_render._day(r) for r in t["rows"]) + timedelta(days=1) - eff).days
        step = (740 - 30 - 40) / days
        xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"', svg)]
        self.assertTrue(xs)
        for x in xs:
            self.assertAlmostEqual((x - 30) / step, round((x - 30) / step), delta=0.06)
        deposit = by_key(t)["deposit"]
        x = 30 + (timeline_render._day(deposit) - eff).days * step
        self.assertIn(f'cx="{x:.1f}"', svg)

    def test_label_color_follows_the_parties(self):
        """A label takes the color of the open deadline it names; deadlines owed by different parties on one day read
        neutral; a done row is labeled done."""
        colors = {"Buyer": "#b", "Seller": "#s", "Both": "#both"}
        t = timeline.analyze(fixture("buyer-fha.json"))
        loan_app = by_key(t)["loan_app"]
        done_both = dict(loan_app, key="signed", label="Agreement Signed", short="Agreement", party="Both", done=True,
                         done_display="Done Sep 26")
        self.assertIn('style="fill:#b">Loan App · Sep 30', timeline_render.strip(dict(t, rows=t["rows"] + [done_both]), colors))
        seller = dict(loan_app, key="seller_thing", label="Seller Thing", short="Seller Thing", party="Seller")
        mixed = dict(t, rows=t["rows"] + [seller])
        self.assertIn(f'style="fill:{timeline_render.MIXED}">', timeline_render.strip(mixed, colors))
        self.assertTrue(timeline_render.strip_mixed(mixed))
        self.assertFalse(timeline_render.strip_mixed(timeline.analyze(fixture("other-contract.json"))))
        d = fixture("buyer-fha.json")
        d["completed"] = {"deposit": "2026-09-26"}
        svg = timeline_render.strip(timeline.analyze(d), COLORS)
        self.assertIn("Deposit · Done", svg)
        self.assertNotIn("Deposit · Sep 28", svg)


class Render(unittest.TestCase):
    def test_html_smoke(self):
        """The report takes the profile's brand color and brokerage, prints no license line without one, and shows a
        moved date's old value."""
        agent = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None,
                 "brand": {"primary": "#0B6E4F"}}
        doc = timeline_render.build_html(timeline.analyze(fixture("seller-amended.json")), agent, sample=True)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Seller View", doc)
        self.assertIn("SAMPLE DATA", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)
        self.assertIn("was Fri Dec 11", doc)
        for label, want in (("Inspection Ends", "inspection"), ("Due Diligence", "due diligence"),
                            ("HOA Review Period Ends", "HOA review")):  # period names in the waiting-periods line
            self.assertEqual(timeline_render.period_name(label), want)

    def test_cli_writes_the_calendar_and_prints_warnings(self):
        deal = fixture("buyer-fha.json")
        deal["contract"]["inspection_dayz"] = 7
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "deal.json")
            with open(src, "w") as f:
                json.dump(deal, f)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                timeline_render.main([src, "--format", "ics", "--out", tmp])
        self.assertTrue(out.getvalue().strip().endswith(".ics"))
        self.assertEqual(err.getvalue().count("'inspection_dayz'"), 1)

    def test_markdown_template_reads_the_result(self):
        """The markdown template uses the fields the PDF prints, and those fields exist on the result."""
        with open(os.path.join(ROOT, "skills", "contract-timeline", "assets", "timeline-template.md")) as f:
            tpl = f.read()
        for path in ("rules.lines", '{{" ★" when critical}} ({{party}})', "history", "row.note", "report_date.long",
                     "closing.long", "when flags has items", "brokerage_license", "first_deadline.day"):
            self.assertIn(path, tpl)
        self.assertNotIn("rules_unknown", tpl)
        r = timeline.analyze(fixture("seller-amended.json"))
        self.assertTrue(r["history"] and all({"name", "description", "date_display", "summary"} <= set(h) for h in r["history"]))
        self.assertIn("long", r["report_date"])
        self.assertIn("long", r["closing"])


if __name__ == "__main__":
    unittest.main()
