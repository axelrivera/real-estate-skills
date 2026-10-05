"""shared/fmt.py: properties of every formatter over generated values, and agreement with the formatters it replaces
(so moving a skill onto fmt is mechanical: the same text, except that ties now round half-up)."""
import os
import random
import re
import sys
import unittest
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
from shared import cma, finance, fmt  # noqa: E402
from shared import offer_engine as oe  # noqa: E402
from skill_import import load  # noqa: E402

N = 2000
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
MONEY = re.compile(r"^[−+]?\(?\$\d{1,3}(,\d{3})*(\.\d\d)?\)?$")


def value(text):
    """The number a money text prints."""
    neg = text.startswith(fmt.MINUS) or text.startswith("(")
    v = float(re.sub(r"[^\d.]", "", text))
    return -v if neg else v


def amounts(rng, n=N, top=3_000_000):
    """Dollar amounts: whole, cents, exact half-dollar ties and negatives."""
    out = []
    for _ in range(n):
        v = rng.choice([rng.randint(0, top), rng.randint(0, top) + rng.randint(0, 99) / 100, rng.randint(0, 9999) + 0.5])
        out.append(-v if rng.random() < 0.3 else v)
    return out


class HalfUp(unittest.TestCase):
    def test_ties_round_away_from_zero(self):
        for n in range(-50, 50):
            self.assertEqual(fmt.half_up(n + 0.5), n + 1 if n >= 0 else n)
            self.assertEqual(fmt.half_up(-(abs(n) + 0.5)), -(abs(n) + 1))

    def test_matches_decimal_reference_and_is_symmetric(self):
        rng = random.Random(1)
        for v in amounts(rng):
            ref = int(Decimal(repr(v)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            self.assertEqual(fmt.half_up(v), ref)
            self.assertEqual(fmt.half_up(-v), -fmt.half_up(v))

    def test_units(self):
        rng = random.Random(2)
        for v in amounts(rng, 500):
            for unit in (1000, 5000, 100):
                r = fmt.half_up(v, unit)
                self.assertEqual(r % unit, 0)
                self.assertLessEqual(abs(r - v), unit / 2)


class Money(unittest.TestCase):
    def test_round_trip_and_shape(self):
        rng = random.Random(3)
        for v in amounts(rng):
            for style in ("minus", "accounting", "signed"):
                t = fmt.money(v, style=style)
                self.assertRegex(t, MONEY)
                self.assertEqual(value(t), fmt.half_up(v))

    def test_signs(self):
        rng = random.Random(4)
        for v in amounts(rng):
            a = abs(v)
            if fmt.half_up(a) == 0:
                continue
            self.assertEqual(fmt.money(-a), fmt.MINUS + fmt.money(a))
            self.assertEqual(fmt.money(-a, style="accounting"), f"({fmt.money(a)})")
            self.assertEqual(fmt.money(a, style="signed"), "+" + fmt.money(a))
            self.assertEqual(fmt.money(-a, style="signed"), fmt.money(-a))
            self.assertNotIn("-", fmt.money(-a))  # a true minus sign, never a hyphen

    def test_zero_never_negative(self):
        for v in (0, -0.0, -0.4, 0.4):
            self.assertEqual(fmt.money(v), "$0")

    def test_empty(self):
        self.assertEqual(fmt.money(None), fmt.EMPTY)

    def test_agrees_with_finance_money_off_ties(self):
        rng = random.Random(5)
        for v in amounts(rng):
            if abs(v) % 1 != 0.5:
                self.assertEqual(fmt.money(v), finance.money(v))


class Short(unittest.TestCase):
    def test_k_round_trip(self):
        rng = random.Random(6)
        for _ in range(N):
            v = rng.randint(1_000, 5_000_000)
            for digits in (0, 1):
                t = fmt.k(v, digits)
                self.assertRegex(t, r"^\$[\d,.]+[KM]$")
                self.assertNotIn("1,000K", t)
                n = float(t[1:-1].replace(",", "")) * (1e6 if t.endswith("M") else 1e3)
                self.assertLessEqual(abs(n - v), 5000 if t.endswith("M") else (500 if digits == 0 else 50) + 1e-6)
                self.assertEqual(fmt.k(-v, digits), fmt.MINUS + t)

    def test_k_agrees_with_short_price(self):
        rng = random.Random(7)
        for _ in range(N):
            v = rng.randint(1_000, 3_000_000)
            if v % 1000 == 500 or v % 100 == 50 or 999_000 <= v < 1_000_000:
                continue  # ties (now half-up) and the band that now reads $1M instead of $1,000K
            self.assertEqual(fmt.k(v, 1), oe.short_price(v))


class Percent(unittest.TestCase):
    def test_round_trip(self):
        rng = random.Random(8)
        for _ in range(N):
            f = rng.randint(-5000, 20000) / 100000
            for digits in (0, 1, 2):
                t = fmt.pct(f, digits)
                self.assertTrue(t.endswith("%"))
                self.assertAlmostEqual(float(t[:-1].replace(fmt.MINUS, "-")), f * 100, delta=0.5 * 10 ** -digits + 1e-9)
                fixed = fmt.pct(f, digits, fixed=True)
                self.assertEqual(len(fixed[:-1].split(".")[1]) if digits else 0, digits)

    def test_agrees_with_the_skill_forms(self):
        rng = random.Random(9)
        for _ in range(N):
            f = rng.randint(0, 10000) / 100000  # three decimals of a percent, like the rates the skills print
            if round(f * 1e4) % 10 != 5:
                self.assertEqual(fmt.pct(f), oe.pct(f))

    def test_months(self):
        self.assertEqual(fmt.months(1), "1 month")
        self.assertEqual(fmt.months(1.04), "1 month")
        rng = random.Random(10)
        for _ in range(500):
            m = rng.randint(1, 240) / 10  # one decimal, as stats.py gives it
            self.assertTrue(fmt.months(m).endswith(" month" if m == 1 else " months"))


class Dates(unittest.TestCase):
    def days(self, n=800):
        rng = random.Random(11)
        start = date(2020, 1, 1)
        return [start + timedelta(days=rng.randint(0, 365 * 15)) for _ in range(n)]

    def test_never_iso(self):
        rng = random.Random(12)
        for d in self.days():
            stamp = f"{d.isoformat()} {rng.randint(0, 23):02d}:{rng.choice([0, 15, 30, 59]):02d}"
            outs = [fmt.date_long(d), fmt.date_short(d), fmt.date_short(d, False, True), fmt.date_short(d.isoformat())]
            outs += [fmt.when(x, s) for x in (stamp, d.isoformat(), d) for s in ("short", "dot", "deadline", "long", "row")]
            for o in outs:
                self.assertNotRegex(o, ISO)

    def test_forms(self):
        rng = random.Random(13)
        for d in self.days(300):
            h, m = rng.randint(0, 23), rng.choice([0, 30])
            dt = datetime(d.year, d.month, d.day, h, m)
            self.assertEqual(fmt.date_long(d), f"{d:%B} {d.day}, {d.year}")
            self.assertEqual(fmt.when(dt), f"{d:%a %b} {d.day}, {(h % 12) or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}")
            self.assertRegex(fmt.when(f"{d} {h:02d}:{m:02d}"), r"^[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d\d [AP]M$")

    def test_agrees_with_the_when_forms_it_replaces(self):
        rng = random.Random(14)
        for d in self.days(300):
            stamp = f"{d} {rng.randint(0, 23):02d}:{rng.choice([0, 5, 30]):02d}"
            for v in (stamp, d.isoformat()):
                self.assertEqual(fmt.when(v), oe.fmt_when_short(v))
                self.assertEqual(fmt.when(v, "dot"), oe.fmt_when(v))

    def test_text_passes_through(self):
        for f in (fmt.date_long, fmt.date_short, fmt.when):
            self.assertEqual(f("upon acceptance"), "upon acceptance")
            self.assertEqual(f(None), "")



class Ranges(unittest.TestCase):
    def test_never_spaced(self):
        rng = random.Random(16)
        for _ in range(N):
            lo = rng.randint(50_000, 2_000_000)
            hi = lo + rng.choice([0, rng.randint(1, 400_000)])
            for f in (fmt.money, fmt.k, lambda v: fmt.k(v, 1), lambda v: fmt.pct(v / 1e7)):
                t = fmt.range(lo, hi, f)
                self.assertNotRegex(t, r"\s[–-]|[–-]\s")
                self.assertEqual(t.count(fmt.EN_DASH), 0 if f(lo) == f(hi) else 1)

    def test_unspaced(self):
        for text in ("April – June", "April - June", "$420,000 – $450,000", "April–June"):
            self.assertNotRegex(fmt.unspaced(text), r"\s[–-]\s")
        self.assertEqual(fmt.unspaced("April – June"), "April–June")


class Templates(unittest.TestCase):
    def test_optional_part_drops_with_its_placeholder(self):
        rng = random.Random(17)
        template = "Taxes[ in {county} County] are estimated[ ({basis})], at {rate}."
        for _ in range(N):
            kw = {"county": rng.choice(["Orange", "", None, " "]), "basis": rng.choice(["the average", "", None]),
                  "rate": rng.choice(["1.8%", "", None])}
            text = fmt.fill(template, **kw)
            self.assertNotRegex(text, r" {2,}| [,.;:)]|\(\s*\)|\{|\[|\]|None")
            self.assertEqual("County" in text, not fmt.blank(kw["county"]))
            self.assertEqual("(" in text, not fmt.blank(kw["basis"]))

    def test_plain_and_missing(self):
        self.assertEqual(fmt.fill("No {fields} here"), "No {fields} here")  # no kw: as is, for a later step
        self.assertEqual(fmt.fill("{n:,} homes", n=1200), "1,200 homes")
        with self.assertRaises(KeyError):
            fmt.fill("[ in {county}] x {y}", y=1)


if __name__ == "__main__":
    unittest.main()
