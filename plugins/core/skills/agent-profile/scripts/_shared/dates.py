"""Business days and US federal holidays (5 U.S.C. 6103), for contract deadlines.

    from _shared import dates
    dates.is_business_day(d)          # weekday and not a federal holiday (or an extra holiday)
    dates.holiday_name(d)             # "Labor Day", "Christmas Day (observed)", or None
"""
from datetime import date, timedelta

# The contract-date rules a market must set (market profile `contract.*`); the timeline and the market check both
# use this list (CORE-12).
RULE_KEYS = ("day_count", "short_period_days", "end_time", "weekend_holiday_rollover", "before_closing_rollover", "holidays")

_CACHE = {}


def _nth(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last(year, month, weekday):
    d = (date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def federal_holidays(year):
    """{date: name} including observed Friday/Monday for fixed holidays on a weekend."""
    if year in _CACHE:
        return _CACHE[year]
    fixed = {"New Year's Day": date(year, 1, 1), "Juneteenth": date(year, 6, 19),
             "Independence Day": date(year, 7, 4), "Veterans Day": date(year, 11, 11),
             "Christmas Day": date(year, 12, 25)}
    moving = {"Martin Luther King Jr. Day": _nth(year, 1, 0, 3), "Washington's Birthday": _nth(year, 2, 0, 3),
              "Memorial Day": _last(year, 5, 0), "Labor Day": _nth(year, 9, 0, 1),
              "Columbus Day": _nth(year, 10, 0, 2), "Thanksgiving Day": _nth(year, 11, 3, 4)}
    out = {}
    for name, d in {**fixed, **moving}.items():
        out[d] = name
        if name in fixed and d.weekday() == 5 and d.year == (d - timedelta(days=1)).year:
            out[d - timedelta(days=1)] = f"{name} (observed)"
        if name in fixed and d.weekday() == 6:
            out[d + timedelta(days=1)] = f"{name} (observed)"
    if date(year + 1, 1, 1).weekday() == 5:  # a Saturday New Year's Day is observed on Friday Dec 31 of this year
        out[date(year, 12, 31)] = "New Year's Day (observed)"
    _CACHE[year] = out
    return out


def holiday_name(d, extra=None):
    """Name of the holiday on `d`, from the federal list or `extra` ({date: name}), else None."""
    return (extra or {}).get(d) or federal_holidays(d.year).get(d)


def is_business_day(d, extra=None):
    return d.weekday() < 5 and not holiday_name(d, extra)


def next_business_day(d, extra=None):
    d += timedelta(days=1)
    while not is_business_day(d, extra):
        d += timedelta(days=1)
    return d


def previous_business_day(d, extra=None):
    """`d` itself if it's a business day, else the closest earlier one."""
    while not is_business_day(d, extra):
        d -= timedelta(days=1)
    return d


def add_business_days(d, n, extra=None):
    """Count n business days forward (n > 0) or back (n < 0) from d, not counting d."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if is_business_day(d, extra):
            remaining -= 1
    return d
