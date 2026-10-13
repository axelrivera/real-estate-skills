"""Compute a neighborhood's buying pattern from an MLS export of closed sales: the one document model the chart and the
markdown summary are both filled from.

    python3 scripts/compute.py market-timing.json [--mls NAME]

Prints JSON: the title and subtitle, the takeaway line, a row per calendar month (sales, median sold price, busy or
busiest), the busy seasons and the busiest month the sales show, when to list, and `warnings` for the reply. The
chart's points stay in render.py's run.

Every sale is folded onto one January to December axis, placed by its contract date (when buyers committed), or by
its close date when the export has none. The window is whole calendar months, 12, 24 or 36 of them, ending before the
current month (and before last month too when placed by contract date, since last month's contracts are still
closing), so every calendar month appears the same number of times. A month counts as busy when its sales per year
are at or above the average month's; two or more busy months in a row (December runs into January) are a busy season.
Every sentence and label is a template in assets/labels.json. The input is never changed.
"""
import argparse
import csv
import json
import os
import statistics
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import fmt, mls, profiles  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "labels.json")
with open(LABELS_PATH, encoding="utf-8") as _f:
    L = json.load(_f)

LOOKBACKS = (12, 24, 36)  # whole years, so each calendar month appears equally often
DEFAULT_LOOKBACK = 24
MIN_SALES = 20  # fewer and one sale more or less moves a month in or out of the season
PEAK_RATIO = 1.5  # the busiest month gets its own box only at 1.5 times the average month or more
PEAK_MIN = 3  # and with at least three sales
MAX_SEASON = 7  # a "season" longer than seven months is most of the year: no season
MAX_SEASONS = 2
GAP_SHARE = 0.75  # a month this close to the average between two busy months stays in the season
LIFT = 1.25  # a season holds at least 1.25 times its share of the year's sales (four months: 42% or more)
INSET = 0.17  # a month's dots keep this share of its column clear on each side, inside its boxes
CONTRACT_SHARE = 0.5  # place by contract date when at least half the sales have one
REQUIRED = ("address", "status", "close_price", "close_date")


class TimingError(ValueError):
    """Something market-timing.json or the export needs; the message is written for the agent."""


def t(key, **kw):
    return fmt.fill(L[key], **kw)


def add_months(d, n):
    """The first of the month `n` months from `d`'s month."""
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def months_between(a, b):
    """Whole months from the first of `a`'s month to the first of `b`'s month."""
    return (b.year - a.year) * 12 + b.month - a.month


def month_year(d):
    return f'{L["months_short"][d.month - 1]} {d.year}'


def window_text(start, end):
    """'Sep 2024 – Aug 2026' for the months from `start` up to (not including) `end`."""
    return t("window", start=month_year(start), end=month_year(add_months(end, -1)))


def _as_of(v):
    if v in (None, ""):
        return date.today()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise TimingError(f"as_of should be a date like 2026-10-13, not {v!r}.") from None


def _lookback(v):
    if v in (None, ""):
        return DEFAULT_LOOKBACK
    if v not in LOOKBACKS:
        raise TimingError(f"lookback_months should be 12, 24 or 36 (whole years), not {v!r}.")
    return v


def _override(v):
    """The agent's busy season: month numbers (1 to 12) in a row, December running into January."""
    if not v:
        return None
    if not isinstance(v, list) or not all(isinstance(m, int) and not isinstance(m, bool) and 1 <= m <= 12 for m in v):
        raise TimingError("season_override should be a list of month numbers 1 to 12, like [4, 5, 6, 7, 8].")
    months = [m - 1 for m in v]
    if len(set(months)) != len(months) or len(months) > 11:
        raise TimingError("season_override should name each month once, and not every month.")
    if any((b - a) % 12 != 1 for a, b in zip(months, months[1:])):
        raise TimingError("season_override should be months in a row, in order, like [11, 12, 1, 2].")
    return months


def load_inputs(R, mls_name=None, data_file=None):
    """The market (for the MLS's column names) and the export's records."""
    if not R.get("export"):
        raise TimingError("The chart needs an MLS export of closed sales (a CSV): set `export` to its path.")
    market = profiles.load_market(state=R.get("state"), county=R.get("county"), mls=mls_name or R.get("mls"))
    path = mls.resolve_export(R["export"], data_file)
    if not R.get("export_columns") and not market.get("mls_format.cma_export_columns"):
        # the place doesn't settle the MLS: the export's own headers may (only its column names are used here)
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                headers = set(next(csv.reader(f), []))
        except OSError:
            headers = set()
        name = profiles.mls_for_headers(headers, REQUIRED)
        if name:
            market = profiles.load_market(state=R.get("state"), county=R.get("county"), mls=name)
    try:
        homes = mls.load(path, market, R.get("export_columns"), required=REQUIRED)
    except mls.ExportError as e:
        raise TimingError(str(e)) from None
    return market, homes


def seasons(rate, avg):
    """Busy seasons: runs of two to MAX_SEASON busy months (a month at or above the average), wrapping from December
    to January, most sales first. One month just under the average between two busy ones (GAP_SHARE of it) doesn't
    split a season. A run counts only when it holds LIFT times its share of the year's sales, so noise in a flat
    market draws no box. [] when there's no pattern."""
    busy = [r >= avg and r > 0 for r in rate]
    busy = [b or (busy[m - 1] and busy[(m + 1) % 12] and rate[m] >= GAP_SHARE * avg) for m, b in enumerate(busy)]
    if all(busy) or not any(busy):
        return []
    runs = []
    for m in range(12):
        if busy[m] and not busy[m - 1]:
            run = [m]
            while busy[(run[-1] + 1) % 12]:
                run.append((run[-1] + 1) % 12)
            runs.append(run)
    year = sum(rate)
    runs = [r for r in runs if 2 <= len(r) <= MAX_SEASON and sum(rate[m] for m in r) >= LIFT * len(r) / 12 * year]
    return sorted(runs, key=lambda r: -sum(rate[m] for m in r))[:MAX_SEASONS]


def peak(rate, counts, avg):
    """The busiest month, when it stands out: the one top month, PEAK_RATIO times the average or more."""
    top = max(rate)
    best = [m for m in range(12) if rate[m] == top]
    if len(best) != 1 or top < PEAK_RATIO * avg or counts[best[0]] < PEAK_MIN:
        return None
    return best[0]


def span(months):
    first, last = L["months"][months[0]], L["months"][months[-1]]
    return t("season_one", first=first) if len(months) == 1 else t("season_span", first=first, last=last)


def list_by(season_start, dom):
    """When to list to be on the market as the season opens: the season's first day less the median days on market,
    as 'early March', 'mid-March' or 'late March'."""
    d = date(2025, season_start + 1, 1) - timedelta(days=round(dom))  # any year without a leap day
    part = "early" if d.day <= 10 else "mid" if d.day <= 20 else "late"
    return t(part, month=L["months"][d.month - 1])


def compute(R, homes):
    as_of = _as_of(R.get("as_of"))
    lookback = _lookback(R.get("lookback_months"))
    override = _override(R.get("season_override"))
    warnings, dropped = [], {}

    def drop(key):
        dropped[key] = dropped.get(key, 0) + 1

    sold = []
    for h in homes:
        if h["status"] != "SOLD":
            drop("drop_status")
        elif not h.get("close_price"):
            drop("drop_price")
        else:
            sold.append(h)
    with_contract = sum(1 for h in sold if h.get("contract_date"))
    by_contract = bool(sold) and with_contract >= CONTRACT_SHARE * len(sold)
    end = add_months(as_of, -1 if by_contract else 0)
    start = add_months(end, -lookback)

    sales = []
    for h in sold:
        d = (h.get("contract_date") or h.get("close_date")) if by_contract else h.get("close_date")
        if not d:
            drop("drop_date")
        elif not start <= d < end:
            drop("drop_window")
        else:
            sales.append((d, h))
    if not sales:
        raise TimingError(f"No closed sales in the export fall in {window_text(start, end)}: export closed sales from "
                          f"the last {lookback + 2} months.")
    sales.sort(key=lambda s: s[0])

    first = date(sales[0][0].year, sales[0][0].month, 1)
    covered = months_between(first, end) if months_between(start, first) > 2 else lookback
    cover_start = add_months(end, -covered)
    occurs = [0] * 12
    for i in range(covered):
        occurs[add_months(cover_start, i).month - 1] += 1
    counts, prices = [0] * 12, [[] for _ in range(12)]
    for d, h in sales:
        counts[d.month - 1] += 1
        prices[d.month - 1].append(h["close_price"])
    rate = [counts[m] / occurs[m] if occurs[m] else 0 for m in range(12)]
    total = len(sales)
    avg = total / covered

    thin = total < MIN_SALES
    if override:
        found, top = [override], None
        warnings.append(t("warn_override", span=span(override)))
    elif thin:
        found, top = [], None
        warnings.append(t("warn_thin", n=total, min=MIN_SALES))
    else:
        found, top = seasons(rate, avg), peak(rate, counts, avg)
    if covered < lookback:
        warnings.append(t("warn_short_data", start=month_year(first), months=covered, lookback=lookback,
                          need=lookback + 2))
    if covered < 24:
        warnings.append(t("warn_one_season", months=covered))
    if not by_contract:
        warnings.append(t("warn_close_basis"))
    elif with_contract < len(sold):
        n = sum(1 for _, h in sales if not h.get("contract_date"))
        if n:
            warnings.append(t("warn_mixed_basis", n=n, total=total))
    if dropped:
        reasons = [t(k, n=n) for k, n in sorted(dropped.items())]
        warnings.append(t("warn_dropped", n=sum(dropped.values()), reasons=fmt.and_list(reasons)))

    subs = {str(h.get("subdivision") or "").strip() for _, h in sales} - {""}
    area = " ".join(str(R.get("area") or "").lower().split())
    if area and subs and not any(area in " ".join(s.lower().split()) or " ".join(s.lower().split()) in area for s in subs):
        named = sorted(subs, key=lambda s: -sum(1 for _, h in sales if str(h.get("subdivision") or "").strip() == s))
        warnings.append(t("warn_area", area=R["area"], subdivisions=fmt.and_list(named[:3])))

    doms = [h["days_on_market"] for _, h in sales if h.get("days_on_market") is not None]
    dom = statistics.median(doms) if doms else None
    season_rows = [{"months": [m + 1 for m in s], "span": span(s), "sales": sum(counts[m] for m in s)} for s in found]

    take, when = [], None
    if found:
        verb = "contract" if by_contract else "close"
        if len(found) == 2:
            take.append(t(f"take_two_seasons_{verb}", n=season_rows[0]["sales"] + season_rows[1]["sales"], total=total,
                          span=season_rows[0]["span"], span2=season_rows[1]["span"]))
        else:
            take.append(t(f"take_season_{verb}", n=season_rows[0]["sales"], total=total, span=season_rows[0]["span"]))
        if by_contract and dom is not None:
            when = list_by(found[0][0], dom)
            take.append(t("take_list_by", when=when))
        elif top is not None:
            take.append(t("take_peak", month=L["months"][top]))
        if by_contract and dom is None:
            warnings.append(t("warn_no_dom"))
    elif not thin:
        take.append(t("take_flat"))

    in_season = {m for s in found for m in s}
    months = []
    for m in range(12):
        months.append({"month": m + 1, "name": L["months"][m], "short": L["months_short"][m], "sales": counts[m],
                       "per_year": round(rate[m], 2),
                       "median_price": round(statistics.median(prices[m])) if prices[m] else None,
                       "median_price_display": fmt.money(statistics.median(prices[m])) if prices[m] else "—",
                       "season": "peak" if m == top else "busy" if m in in_season else None,
                       "season_label": L["md_season_peak"] if m == top else L["md_season_busy"] if m in in_season else ""})

    years = [{"start": add_months(end, -12 * (i + 1)).isoformat(), "end": add_months(end, -12 * i).isoformat(),
              "label": t("lg_year", start=month_year(add_months(end, -12 * (i + 1))),
                         end=month_year(add_months(end, -12 * i - 1)))}
             for i in range(lookback // 12)]
    points = []
    for d, h in sales:
        days = (date(d.year + d.month // 12, d.month % 12 + 1, 1) - date(d.year, d.month, 1)).days
        points.append({"x": d.month - 1 + INSET + (1 - 2 * INSET) * (d.day - 1) / (days - 1), "price": h["close_price"],
                       "year": (months_between(d, end) - 1) // 12,
                       "address": h["address"], "date": d})

    basis = L["basis_contract"] if by_contract else L["basis_close"]
    count = L["sales_count_one"] if total == 1 else t("sales_count", n=total)
    return {
        "ok": True,
        "title": L["doc_title"],
        "area": R.get("area") or "",
        "subtitle": t("subtitle", area=R.get("area"), basis=basis, window=window_text(cover_start, end), count=count),
        "takeaway": " ".join(take),
        "basis": "contract" if by_contract else "close",
        "as_of": as_of.isoformat(),
        "window": {"start": cover_start.isoformat(), "end": end.isoformat(), "months": covered,
                   "lookback": lookback, "display": window_text(cover_start, end)},
        "sales": total,
        "average_per_month": round(avg, 2),
        "median_days_on_market": dom,
        "list_by": when,
        "months": months,
        "seasons": season_rows,
        "peak_month": top + 1 if top is not None else None,
        "season_source": "agent" if override else "sales",
        "years": years,
        "warnings": warnings,
        "sample": bool(R.get("sample")),
        "_points": points,
    }


def run(R, mls_name=None, data_file=None):
    """The document model from a market-timing.json dict: render.py's compute step."""
    _, homes = load_inputs(R, mls_name, data_file)
    return compute(R, homes)


def public(C):
    """The model as JSON prints it: without the chart's points (render.py's own)."""
    return {k: v for k, v in C.items() if not k.startswith("_")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", help="market-timing.json")
    ap.add_argument("--mls", help="MLS name (Stellar is built in)")
    a = ap.parse_args(argv)
    try:
        with open(a.data, encoding="utf-8") as f:
            R = json.load(f)
        result = public(run(R, a.mls, a.data))
    except (TimingError, profiles.ProfileError, ValueError, OSError) as e:
        result = {"ok": False, "problems": [str(e)]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
