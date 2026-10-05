"""Generated contract timelines (dev/generators/contract_timeline.py): random valid deal files, every output rendered,
universal invariants only. A few deals in `make test`; more with FUZZ_N (and FUZZ_SEED for another range):

    FUZZ_N=200 .venv/bin/python -m unittest dev.tests.test_generated_contract_timeline

Invariants: the computation never changes its input; every date that rolled off a weekend or holiday lands on a business
day, and every date the deal's rules roll is one; Day N is the days after the Effective Date; the calendar's events
are the report's open rows on the same dates and times; every date, time and amount the report prints comes from the
document model; each Check line prints once, and no note reaches the report or the calendar except as a Check line;
no label carries a note; the strip's legend names exactly the colors and dots it drew; and the PDF has no overflow,
no clipped text and no near-empty page.
"""
import concurrent.futures
import copy
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev", "generators"))
import contract_timeline as gen  # noqa: E402

timeline, timeline_render = load("contract-timeline", "timeline", "render")
from _shared import dates, layout  # noqa: E402  (the skill's own copy, loaded with it)
from _shared.notes import Notes  # noqa: E402

N = int(os.environ.get("FUZZ_N", "8"))
SEED = int(os.environ.get("FUZZ_SEED", "0"))
PROFILES = os.path.join(ROOT, "dev", "fixtures", "_profiles")
RENDER = os.path.join(ROOT, "skills", "contract-timeline", "scripts", "render.py")
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
FIGURE = re.compile(rf"\b{MONTH} \d{{1,2}}(?:, \d{{4}})?|\$[\d,]+(?:\.\d\d)?|\b\d{{1,2}}:\d\d [AP]M")
WARNINGS = ("overflows by", "clipped", "doesn't fit on one page")


def profile(seed):
    return os.path.join(PROFILES, "stress.md" if seed % 3 == 0 else "profile.md")


def render_files(seed, deal, out):
    """Render the deal's PDF and calendar the way the skill does (its command line, with a fixture profile: the
    long-name one every third seed). (exit code, paths, stderr)."""
    src = os.path.join(out, f"deal-{seed}.json")
    with open(src, "w") as f:
        json.dump(deal, f)
    dest = os.path.join(out, str(seed))
    r = subprocess.run([sys.executable, RENDER, src, "--format", "all", "--out", dest, "--profile", profile(seed)],
                       capture_output=True, text=True, env=dict(os.environ, OUTPUT_DIR=dest))
    return r.returncode, r.stdout.split(), r.stderr


def text_of(doc):
    """The report's visible text, without the strip's axis ticks (a chart's scale, not a figure)."""
    doc = re.sub(r'<text[^>]*class="tk"[^>]*>[^<]*</text>', "", doc)
    doc = re.sub(r"<style>.*?</style>", "", doc, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", doc))


def ics_events(text):
    """{row key: (date, time or None)} from the calendar."""
    out = {}
    for ev in text.replace("\r\n ", "").split("BEGIN:VEVENT")[1:]:
        key = re.search(r"UID:([^\r\n]+?)-[0-9a-f]{10}@", ev).group(1)
        m = re.search(r"DTSTART(?:;VALUE=DATE|;TZID=[^:]+)?:(\d{8})(?:T(\d{4}))?", ev)
        out[key] = (datetime.strptime(m.group(1), "%Y%m%d").date(), m.group(2) and f"{m.group(2)[:2]}:{m.group(2)[2:]}")
    return out


class Generated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.deals = {s: gen.generate(s) for s in range(SEED, SEED + N)}
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            cls.files = dict(zip(cls.deals, pool.map(lambda s: render_files(s, cls.deals[s], cls.tmp.name), cls.deals)))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def results(cls):
        if not hasattr(cls, "_results"):
            cls._results = [(s, d, timeline.analyze(copy.deepcopy(d))) for s, d in cls.deals.items()]
        return cls._results

    def test_model(self):
        """The input is never changed; Day N counts from the Effective Date; rows run in date order; the first deadline
        is the earliest open contract row; the Check lines come only from the script's keys."""
        for seed, deal, t in self.results():
            with self.subTest(seed=seed):
                before = copy.deepcopy(deal)
                timeline.analyze(deal)
                self.assertEqual(deal, before)
                json.dumps(t)
                eff = date.fromisoformat(t["effective"]["date"])
                whens = [r["when"] for r in t["rows"]]
                self.assertEqual(whens, sorted(whens))
                for r in t["rows"]:
                    self.assertEqual(r["day"], (date.fromisoformat(r["when"][:10]) - eff).days)
                open_rows = [r for r in t["rows"] if not r["done"] and not r["past"] and not r["lender"]]
                self.assertEqual(t["first_deadline"], open_rows[0] if open_rows else None)
                self.assertTrue(set(k.split(":")[0] for k in t["flag_keys"]) <= timeline.FLAG_KEYS)
                self.assertEqual(len(t["flags"]), len(set(t["flags"])))
                self.assertEqual(len(t["note_keys"]), len(set(t["note_keys"])))

    def test_dates_roll_per_the_deals_rule(self):
        """A date moved off a weekend or holiday lands on a business day; under rules that roll (Florida's, or a
        contract's own next-business-day rule), every date they move is a business day."""
        for seed, deal, t in self.results():
            with self.subTest(seed=seed):
                farbar = t["form_family"] == "farbar"
                rules, _ = timeline.load_rules(copy.deepcopy(deal), farbar)
                hol = rules["_extra_holidays"]
                src = {x["key"]: x for x in deal.get("deadlines") or []}
                overrides = {k: v for a in deal.get("amendments") or [] for k, v in (a.get("date_overrides") or {}).items()}
                for r in t["rows"]:
                    d = date.fromisoformat(r["when"][:10])
                    if r["moved_from"]:
                        self.assertTrue(dates.is_business_day(d, hol), (r["key"], r["when"]))
                        self.assertFalse(dates.is_business_day(date.fromisoformat(r["moved_from"]), hol), r["key"])
                    x = src.get(r["key"], {})
                    kept = (r["lender"] or r["key"] == "possession" or x.get("rollover") is False
                            or len(str(overrides.get(r["key"], ""))) >= 16 or len(str(x.get("date", ""))) >= 16)
                    if farbar and not kept and r["key"] not in src:  # Florida: every period and date rolls (Standard F)
                        self.assertTrue(dates.is_business_day(d, hol), (r["key"], r["when"]))
                    if x and not kept and x["basis"] in ("after", "event", "date") and \
                            rules["weekend_holiday_rollover"] == "next_business_day":
                        self.assertTrue(dates.is_business_day(d, hol), (r["key"], r["when"]))

    def test_report_places_the_model(self):
        """Every date, time and amount the report prints is in the document model; each Check line prints once; agent
        and chat notes never print; no label carries a note; the legend names exactly what the strip drew."""
        for seed, deal, t in self.results():
            with self.subTest(seed=seed):
                if not t["closing"] and not t.get("short_sale"):
                    continue
                agent = gen.agent(seed)
                doc = timeline_render.build_html(t, agent, sample=bool(deal.get("sample")))
                body = doc.split("<body", 1)[1]
                text = " ".join(text_of(body).split())
                model = json.dumps(t, ensure_ascii=False) + json.dumps({k: str(v) for k, v in agent.items()})
                for fig in FIGURE.findall(text):
                    self.assertIn(fig, model, f"{fig!r} isn't in the document model")
                for day in re.findall(r"\bDay (\d+)\b", text):
                    self.assertIn(int(day), {r["day"] for r in t["rows"]})
                self.assertNotRegex(text, r"\b\d{4}-\d{2}-\d{2}\b")  # never a date in data form
                for flag in t["flags"]:
                    self.assertEqual(text.count(" ".join(flag.split())), 1, flag)
                for note in [n for n, k in zip(t["agent_notes"], t["note_keys"])] + t["chat_notes"]:
                    self.assertNotIn(" ".join(note.split()), text)
                reg = Notes()
                for k, f in zip(t["flag_keys"], t["flags"]):
                    reg.add(k, f)
                labels = [html.unescape(re.sub(r"<[^>]+>", "", x)) for x in
                          re.findall(r"<th[^>]*>(.*?)</th>", body) + re.findall(r"<h2[^>]*>(.*?)</h2>", body)
                          + re.findall(r'<span data-series="[^"]+">.*?</svg>(.*?)</span>', body)]
                labels += [r["label"] for r in t["rows"] + t["pending"]]
                self.assertEqual(reg.label_problems(labels), [])
                svg = re.search(r'<svg viewBox="[^"]+" class="strip">.*?</svg>', body).group(0)
                drawn = set(re.findall(r'class="lbl" text-anchor="middle" style="fill:([^"]+)"', svg))
                legend = re.findall(r'<span data-series="([^"]+)"><svg viewBox="0 0 14 14">(<[^>]+>)', body)
                colors = {re.search(r"fill:([^;\"]+)", mark).group(1) for key, mark in legend if key not in ("critical", "other")}
                self.assertEqual(colors, drawn)
                filled = any('fill="#fff"' not in c for c in re.findall(r"<circle [^>]+>", svg))
                hollow = any('fill="#fff"' in c for c in re.findall(r"<circle [^>]+>", svg))
                self.assertEqual(("critical" in dict(legend), "other" in dict(legend)), (filled, hollow))

    def test_files(self):
        """The PDF prints without overflow, clipping or a near-empty page; the calendar holds exactly the report's
        open rows, on the dates and times the report shows; no note reaches the calendar."""
        for seed, deal, t in self.results():
            with self.subTest(seed=seed):
                code, paths, err = self.files[seed]
                self.assertEqual(code, 0, err[-600:])
                self.assertFalse([line for line in err.splitlines() if any(w in line for w in WARNINGS)], err[-600:])
                pdfs = [p for p in paths if p.endswith(".pdf")]
                icss = [p for p in paths if p.endswith(".ics")]
                self.assertEqual((len(pdfs), len(icss)), (1, 1))
                pages = layout.page_fill(pdfs[0], 0.3, 0.4)
                if pages is not None:
                    for i, (fill, first) in enumerate(pages[1:-1], 2):
                        self.assertGreaterEqual(fill, layout.HALF_EMPTY, f"page {i} of {len(pages)}: {first}")
                    if len(pages) > 1:
                        self.assertGreaterEqual(pages[-1][0], layout.LONE_TAIL, f"last page: {pages[-1][1]}")
                with open(icss[0], encoding="utf-8") as f:
                    cal = f.read()
                events = ics_events(cal)
                # the files were rendered on the system date: a past row could differ from analyze's only by report_date,
                # which the deal sets, so the two agree
                want = timeline_render.calendar_rows(t)
                self.assertEqual(set(events), {r["key"] for r in want})
                for r in want:
                    d, tm = events[r["key"]]
                    self.assertEqual(d, date.fromisoformat(r["when"][:10]), r["key"])
                    if tm:
                        self.assertEqual(tm, r["when"][11:16], r["key"])
                    self.assertIn(timeline.fmt.date_short(d, year=False, weekday=True), r["display"])
                for note in t["agent_notes"] + t["chat_notes"] + t["flags"]:
                    self.assertNotIn(timeline_render._ics_text(note), cal.replace("\r\n ", ""))  # the whole note


if __name__ == "__main__":
    unittest.main()
