"""The one place figures become text: money, short prices, percents, months of supply, dates, times and ranges.

    from _shared import fmt
    fmt.money(474900)                 # '$474,900'
    fmt.money(-1200)                  # '−$1,200' (a true minus sign)
    fmt.money(-1200, style="accounting")   # '($1,200)'
    fmt.money(1200, style="signed")   # '+$1,200'
    fmt.money(474_949, unit=1000)     # '$475,000'
    fmt.k(455_000)                    # '$455K'      fmt.k(432_500, 1) -> '$432.5K'      fmt.k(1_250_000) -> '$1.25M'
    fmt.pct(0.025)                    # '2.5%'       fmt.pct(0.03) -> '3%'     fmt.pct(0.03, 2, fixed=True) -> '3.00%'
    fmt.pct(0.07, None, symbol=False) # '7'          (the :g form a template writes as '{pct}%')
    fmt.months(1.34)                  # '1.3 months' fmt.months(1) -> '1 month'
    fmt.date_long("2026-09-26")       # 'September 26, 2026'
    fmt.date_short("2026-09-26")      # 'Sep 26, 2026'  (year=False: 'Sep 26'; weekday=True: 'Sat Sep 26')
    fmt.when("2026-09-24 17:00")      # 'Thu Sep 24, 5:00 PM'
    fmt.range(420_000, 450_000)       # '$420,000–$450,000' (an en dash, never spaced)
    fmt.fill("Taxes[ in {county} County] are estimated.", county="")   # 'Taxes are estimated.'

Rounding is half-up (half away from zero), never Python's round-half-to-even: 0.5 -> 1, 2.5 -> 3, -2.5 -> -3.
Every function takes a number (or a date) and returns text; None prints as the empty-value dash where noted.
Skills format through this module only, so the same figure reads the same everywhere (PDF, deck, ICS, markdown, chat).
"""
import re
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

MINUS = "−"  # U+2212, the minus sign every report prints
EN_DASH = "–"
EMPTY = "—"  # a lone em dash for an empty value (allowed in a table cell)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


# --- rounding ---------------------------------------------------------------

def half_up(v, unit=1):
    """`v` rounded half away from zero to a multiple of `unit` (1, 1000, 0.1, 5000...). Returns an int when `unit` is
    whole, else a float. Uses the shortest decimal form of a float, so 2.675 rounds to 2.68 as it reads."""
    if v is None:
        return None
    u = Decimal(repr(unit)) if isinstance(unit, float) else Decimal(unit)
    q = (Decimal(repr(v)) if isinstance(v, float) else Decimal(v)) / u
    r = q.quantize(Decimal(1), rounding=ROUND_HALF_UP) * u
    return int(r) if u == u.to_integral_value() else float(r)


def _dec(v):
    """A number as the Decimal it reads as (a float by its shortest form: 0.0285 is 0.0285, not 0.028499...)."""
    return v if isinstance(v, Decimal) else Decimal(repr(v)) if isinstance(v, float) else Decimal(v)


def _places(v, digits):
    """`v` half-up to `digits` decimals, as a Decimal."""
    d = _dec(v)
    return d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _strip(s):
    return s.rstrip("0").rstrip(".") if "." in s else s


def num(v, digits=0, strip=True):
    """1850 -> '1,850'; num(1.25, 1) -> '1.3'; trailing zeros dropped unless strip=False. None -> '—'."""
    if v is None:
        return EMPTY
    d = _places(v, digits)
    s = f"{abs(d) if d == 0 else d:,.{digits}f}".replace("-", MINUS)
    return _strip(s) if strip and digits else s


# --- money ------------------------------------------------------------------

def money(v, unit=1, style="minus"):
    """Dollars, half-up to `unit` (1 by default; 1000, 5000...). None -> '—'.

    style: "minus" '−$1,200' (default), "accounting" '($1,200)', "signed" '+$1,200' / '−$1,200' (zero is '+$0').
    """
    if v is None:
        return EMPTY
    r = half_up(v, unit)
    body = f"${abs(r):,.0f}" if float(r).is_integer() else f"${abs(r):,.2f}"
    if style == "accounting":
        return f"({body})" if r < 0 else body
    if style == "signed":
        return ("+" if r >= 0 else MINUS) + body
    if style != "minus":
        raise ValueError(f"unknown money style {style!r}")
    return (MINUS if r < 0 else "") + body


def k(v, digits=0):
    """A short price: '$455K' (whole thousands, the default), with digits=1 '$432.5K' (a tenth only when it isn't
    whole), and from a million up '$1.25M' (two decimals, trailing zeros dropped). A value that rounds to $1,000K
    reads '$1M'. Negative amounts take the minus sign. None -> '—'."""
    if v is None:
        return EMPTY
    sign, a = (MINUS if v < 0 else ""), abs(_dec(v))
    thousands = _places(a / 1000, digits)
    if thousands >= 1000:
        return f"{sign}${_strip(f'{_places(a / 1_000_000, 2):.2f}')}M"
    return f"{sign}${_strip(f'{thousands:,.{digits}f}') if digits else f'{thousands:,.0f}'}K"


# --- percents and months ----------------------------------------------------

def pct(fraction, digits=1, fixed=False, symbol=True):
    """A share as a percent: pct(0.025) -> '2.5%', pct(0.03) -> '3%' (trailing zeros dropped), pct(0.0325, 2) -> '3.25%',
    pct(0.03, 1, fixed=True) -> '3.0%' (zeros kept). digits=None prints what the number holds, up to four decimals
    (the ':g' form: 0.07 -> '7%', 0.0125 -> '1.25%'). symbol=False leaves off the '%'. None -> '—'."""
    if fraction is None:
        return EMPTY
    d = _places(_dec(fraction) * 100, 4 if digits is None else digits)
    d = abs(d) if d == 0 else d
    s = _strip(f"{d:f}") if digits is None else f"{d:.{digits}f}"
    if digits is not None and not fixed:
        s = _strip(s)
    s = s.replace("-", MINUS)
    return s + ("%" if symbol else "")


def months(m, digits=1):
    """Months of supply as a report reads it: '1.3 months', '1 month', '0.5 months'. None -> '—'."""
    if m is None:
        return EMPTY
    s = _strip(f"{_places(m, digits):.{digits}f}")
    return f"{s} month{'' if s == '1' else 's'}"


# --- dates and times --------------------------------------------------------

def to_date(value):
    """A date from a date, a datetime or an ISO string ('2026-09-26', '2026-09-26 17:00', '2026-09-26T17:00');
    None when it isn't one."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


_ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T](\d{1,2}):(\d{2})")


def to_time(value):
    """The time of day in a datetime or an ISO 'YYYY-MM-DD HH:MM' string; None for a date alone."""
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    m = _ISO_TIME.match(str(value or "").strip())
    return time(int(m.group(1)), int(m.group(2))) if m else None


def date_long(value):
    """'September 26, 2026'. Text that isn't a date passes through (None -> '')."""
    d = to_date(value)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}" if d else ("" if value is None else str(value))


def date_short(value, year=True, weekday=False):
    """'Sep 26, 2026'; year=False 'Sep 26'; weekday=True 'Sat Sep 26' ('Sat Sep 26, 2026' with the year).
    Text that isn't a date passes through (None -> '')."""
    d = to_date(value)
    if not d:
        return "" if value is None else str(value)
    out = f"{d:%b} {d.day}"
    if weekday:
        out = f"{d:%a} {out}"
    return f"{out}, {d.year}" if year else out


def weekday(value, short=False):
    """'Thursday' ('Thu' with short)."""
    d = to_date(value)
    return (f"{d:%a}" if short else f"{d:%A}") if d else ""


def clock(t, full=True):
    """time(17, 0) -> '5:00 PM'; with full=False '5 PM' (minutes only when they aren't zero: '5:30 PM')."""
    if t is None:
        return ""
    h, m = t.hour, t.minute
    return f"{(h % 12) or 12}" + (f":{m:02d}" if m or full else "") + (" PM" if h >= 12 else " AM")


def when(value, style="short"):
    """A deadline or appointment from a date with an optional time ('2026-09-24 17:00', a datetime, a date).

    short     'Thu Sep 24, 5:00 PM'     (date alone: 'Thu Sep 24'), the one short form a deadline takes
    dot       'Sep 24, 2026 · 5:00 PM'  (date alone: 'Sep 24, 2026')
    deadline  'Thu Sep 24 · 5 PM'       (date alone: 'Thu Sep 24')
    long      'September 24, 2026, 5:00 PM' (date alone: 'September 24, 2026')
    row       'Thu Sep 24 · 5:00 PM'    (date alone: 'Thu Sep 24'), a timeline row's date and time
    Text that isn't a date passes through; None -> ''.
    """
    d = to_date(value)
    if not d:
        return "" if value is None else str(value)
    t = to_time(value)
    if style == "short":
        return date_short(d, year=False, weekday=True) + (f", {clock(t)}" if t else "")
    if style == "dot":
        return date_short(d) + (f" · {clock(t)}" if t else "")
    if style == "deadline":
        return date_short(d, year=False, weekday=True) + (f" · {clock(t, full=False)}" if t else "")
    if style == "long":
        return date_long(d) + (f", {clock(t)}" if t else "")
    if style == "row":
        return date_short(d, year=False, weekday=True) + (f" · {clock(t)}" if t else "")
    raise ValueError(f"unknown when style {style!r}")


def period_labels(window):
    """Labels for a split time window {first_close, split_date, last_close} (ISO dates), from the actual bounds.
    A split on the 1st reads as whole months ('April–June', 'July–September'); a mid-month split shows the day, so no
    days are dropped ('April–July 14', 'July 15–September'); a window across New Year names the years."""
    split = date.fromisoformat(window["split_date"])
    before = date.fromordinal(split.toordinal() - 1)
    y = window["first_close"][:4] != window["last_close"][:4]

    def month(d, day=False):
        return MONTHS[d.month - 1] + (f" {d.day}" if day else "") + ((", " if day else " ") + str(d.year) if y else "")

    first, last = month(date.fromisoformat(window["first_close"])), month(date.fromisoformat(window["last_close"]))
    mid = split.day != 1
    return [f"{first}{EN_DASH}{month(before, mid)}", f"{month(split, mid)}{EN_DASH}{last}"]


# --- ranges -----------------------------------------------------------------

_SPACED = re.compile(r"(?<=\S)\s+[–-]\s+(?=\S)")


def unspaced(text):
    """'April – June' -> 'April–June': a range written with a spaced hyphen or en dash reads with a bare en dash."""
    return _SPACED.sub(EN_DASH, str(text))


def range(lo, hi, f=money):
    """Two values joined by an unspaced en dash: '$420,000–$450,000', or with f=k '$420K–$450K'. Equal ends print once.
    `f` formats each end (any function here, or `lambda s: s` for text)."""
    a, b = f(lo), f(hi)
    return a if a == b else f"{a}{EN_DASH}{b}"


# --- templates --------------------------------------------------------------

_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")
_FIELD = re.compile(r"\{(\w+)[^{}]*\}")
_SPACES = re.compile(r" {2,}")
_BEFORE_PUNCT = re.compile(r" +(?=[,.;:)])")


def blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def fill(template, **kw):
    """A labels.json template, filled. A part in [brackets] is printed only when every placeholder in it has a value
    (not None, not blank), so a template names an optional field inside one ("Taxes[ in {county} County]") and reads
    whole without it. A placeholder outside brackets prints as given; one missing from `kw` is a KeyError, as in
    str.format. With no `kw` the template comes back as is. The result never carries a doubled space or a space before
    punctuation."""
    if not kw:
        return template  # a label, or a template another step fills

    def part(m):
        return "" if any(blank(kw[f]) for f in _FIELD.findall(m.group(1))) else m.group(1)
    text = _OPTIONAL.sub(part, template).format(**{k: ("" if v is None else v) for k, v in kw.items()})
    return _BEFORE_PUNCT.sub("", _SPACES.sub(" ", text))


__all__ = ["half_up", "num", "money", "k", "pct", "months", "to_date", "to_time", "date_long", "date_short",
           "weekday", "clock", "when", "period_labels", "unspaced", "range", "fill", "blank"]
