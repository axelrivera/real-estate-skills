"""Read an MLS CMA export and compute the market numbers both CMAs use.

    from _shared import mls
    homes = mls.load("export.csv", market)          # column names from the market profile's mls_format
    stats = mls.market_stats(homes, subject, split_date="2026-07-01")
    fit = mls.trend(homes, subject_sqft=1849)

Records use the skills' field names (address, status, living_area, close_price, …), whatever the
MLS calls its columns. Statuses are normalized to SOLD, ACTIVE, PENDING, EXPIRED, CANCELED, WITHDRAWN.
Numbers only: choosing comps and judging condition is Claude's job.
"""
import csv
import statistics
from datetime import date, datetime, timedelta

NUMERIC = ("living_area", "current_price", "close_price", "original_list_price", "seller_paid_buyer_costs",
           "days_on_market", "lot_acres", "year_built", "beds", "full_baths", "distance")
DATES = ("close_date", "contract_date")
STATUS = {"SLD": "SOLD", "SOLD": "SOLD", "CLOSED": "SOLD", "ACT": "ACTIVE", "ACTIVE": "ACTIVE",
          "PND": "PENDING", "PNC": "PENDING", "PENDING": "PENDING", "UNDER": "PENDING", "CTG": "PENDING", "AWC": "PENDING", "EXP": "EXPIRED", "EXPIRED": "EXPIRED",
          "CAN": "CANCELED", "CANC": "CANCELED", "CANCELED": "CANCELED", "CANCELLED": "CANCELED",
          "WDN": "WITHDRAWN", "WITHDRAWN": "WITHDRAWN"}
STATUS_LABEL = {"SOLD": "Sold", "ACTIVE": "For sale", "PENDING": "Under contract", "EXPIRED": "Expired",
                "CANCELED": "Canceled", "WITHDRAWN": "Withdrawn"}


class ExportError(ValueError):
    """The export can't be read; the message is written for the agent."""


def _num(v):
    s = str(v or "").replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _date(v):
    s = str(v or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def load(path, market):
    """Records from a CSV export, using the market profile's `mls_format.cma_export_columns`."""
    columns = market.get("mls_format.cma_export_columns")
    if not columns:
        raise ExportError("The market profile has no MLS export columns. For an MLS that isn't built in, "
                          "map its column headers in the market profile first.")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        needed = ("address", "status", "living_area", "close_price", "current_price")
        missing = [columns[k] for k in needed if columns.get(k) not in headers]
        if missing:
            raise ExportError(f"The export is missing these columns: {', '.join(missing)}.")
        homes = []
        for row in reader:
            rec = {key: row.get(col, "") for key, col in columns.items()}
            for k in NUMERIC:
                if k in rec:
                    rec[k] = _num(rec[k])
            for k in DATES:
                if k in rec:
                    rec[k] = _date(rec[k])
            rec["address"] = str(rec.get("address", "")).strip()
            token = str(rec.get("status", "")).split()[0].upper() if rec.get("status") else ""
            rec["status_raw"] = rec.get("status", "")
            rec["status"] = STATUS.get(token, token or "UNKNOWN")
            rec["private_pool"] = "private" in str(rec.get("pool", "")).lower()
            rec["seller_paid"] = rec.pop("seller_paid_buyer_costs", None) or 0.0
            homes.append(rec)
    return homes


def same_address(a, b):
    return " ".join(str(a).upper().split()) == " ".join(str(b).upper().split())


def _median(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def period_stats(sold):
    if not sold:
        return {"n": 0}
    paid = [h["seller_paid"] or 0 for h in sold]
    ratios = [h["close_price"] / h["original_list_price"] for h in sold if h.get("original_list_price")]
    ppsf = [h["close_price"] / h["living_area"] for h in sold if h.get("living_area")]
    return {
        "n": len(sold),
        "median_price": _median(h["close_price"] for h in sold),
        "median_ppsf": round(_median(ppsf), 1) if ppsf else None,
        "median_sale_to_original_list": round(_median(ratios), 4) if ratios else None,
        "median_days_on_market": _median(h.get("days_on_market") for h in sold),
        "share_with_seller_paid_costs": round(sum(p > 0 for p in paid) / len(paid), 3),
        "median_seller_paid_when_paid": _median(p for p in paid if p > 0) or 0.0,
    }


def _subdivision_key(name):
    return str(name or "").upper().split(" UNIT")[0].split(" SEC")[0].strip()


def market_stats(homes, subject, split_date=None, exclude_address=None):
    """Sold stats (all, earlier, recent), inventory, months of supply, subdivision stats, comp candidates, competition.

    `subject`: {address, living_area, private_pool, subdivision}. `exclude_address` drops every row for
    that address first (the seller CMA ignores the subject's own listings).
    """
    if exclude_address:
        homes = [h for h in homes if not same_address(h["address"], exclude_address)]
    sold = [h for h in homes if h["status"] == "SOLD" and h.get("close_price") and h.get("close_date")]
    if not sold:
        raise ExportError("The export has no sold homes with a close price and date.")
    last, first = max(h["close_date"] for h in sold), min(h["close_date"] for h in sold)
    split = datetime.strptime(split_date, "%Y-%m-%d").date() if split_date else last - timedelta(days=90)
    early = [h for h in sold if h["close_date"] < split]
    recent = [h for h in sold if h["close_date"] >= split]
    months_recent = max((last - split).days / 30.44, 0.5)
    actives = [h for h in homes if h["status"] == "ACTIVE" and not same_address(h["address"], subject.get("address", ""))]
    cuts = [h for h in actives if h.get("current_price") and h.get("original_list_price")]
    counts = {}
    for h in homes:
        counts[h["status"]] = counts.get(h["status"], 0) + 1

    out = {
        "window": {"first_close": str(first), "last_close": str(last), "split_date": str(split)},
        "sold_all": period_stats(sold), "sold_early": period_stats(early), "sold_recent": period_stats(recent),
        "active_count": len(actives),
        "active_share_with_price_cut": round(sum(h["current_price"] < h["original_list_price"] for h in cuts) / len(cuts), 3) if cuts else 0,
        "months_supply_at_recent_pace": round(len(actives) / (len(recent) / months_recent), 1) if recent else None,
        "status_counts": counts,
    }

    sub_key = _subdivision_key(subject.get("subdivision"))
    if sub_key:
        out["subdivision"] = {"name_match": sub_key,
                              **period_stats([h for h in sold if sub_key in str(h.get("subdivision", "")).upper()])}
    sqft = subject.get("living_area")
    if sqft:
        scored = []
        for h in sold:
            size_diff = (h["living_area"] / sqft - 1) if h.get("living_area") else 1.0
            same_sub = bool(sub_key) and sub_key in str(h.get("subdivision", "")).upper()
            pool_match = h["private_pool"] == bool(subject.get("private_pool"))
            score = same_sub * 3 + pool_match * 2 + (abs(size_diff) <= 0.2) * 2 - abs(size_diff) * 5
            scored.append((score, round(size_diff, 3), h))
        scored.sort(key=lambda x: -x[0])
        out["sold_candidates"] = [_summary(h, size_diff=d) for _, d, h in scored[:15]]
    others = [h for h in homes if h["status"] != "SOLD" and not same_address(h["address"], subject.get("address", ""))]
    others.sort(key=lambda h: h.get("distance") if h.get("distance") is not None else 99)
    out["competition"] = [_summary(h) for h in others]
    return out


def _summary(h, size_diff=None):
    keys = ("address", "status", "subdivision", "distance", "close_date", "close_price", "current_price",
            "original_list_price", "seller_paid", "living_area", "beds", "full_baths", "year_built", "pool",
            "lot_acres", "days_on_market", "sale_terms")
    s = {k: (str(h[k]) if isinstance(h.get(k), date) else h.get(k)) for k in keys if k in h}
    s["remarks"] = str(h.get("remarks", ""))[:700]
    if size_diff is not None:
        s["size_diff_pct"] = size_diff
    return s


def trend(homes, subject_sqft, fit_size_ratio=1.6, exclude_address=None):
    """Least-squares price-vs-size line over sold homes up to `fit_size_ratio` × the subject's size.

    Returns {'slope', 'intercept', 'at_subject', 'r2', 'n'}; None with fewer than 3 sales.
    """
    pts = [(h["living_area"], h["close_price"]) for h in homes
           if h["status"] == "SOLD" and h.get("living_area") and h.get("close_price")
           and h["living_area"] <= subject_sqft * fit_size_ratio
           and not (exclude_address and same_address(h["address"], exclude_address))]
    if len(pts) < 3:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    r2 = (sxy * sxy) / (sxx * syy) if sxx and syy else 0.0
    return {"slope": slope, "intercept": intercept, "at_subject": intercept + slope * subject_sqft, "r2": r2, "n": len(pts)}


def r2_key(r2):
    """Label key for how much of the price differences size explains (translated in the skill's labels)."""
    return "r2_small" if r2 < 0.2 else "r2_third" if r2 < 0.45 else "r2_half" if r2 < 0.6 else "r2_most"
