"""Read an MLS CMA export and compute the market numbers both CMAs use.

    from _shared import mls
    homes = mls.load("export.csv", market)          # column names from the MLS layer, or columns={...}
    mls.fill_distances(homes, "517 HICKORYWOOD AVE")  # from Latitude/Longitude when there's no Distance column
    stats = mls.market_stats(homes, subject, split_date="2026-07-01")
    fit = mls.trend(homes, subject_sqft=1849)

Records use the skills' field names (address, status, living_area, close_price, …), whatever the
MLS calls its columns. Statuses are normalized to SOLD, ACTIVE, PENDING, EXPIRED, CANCELED, WITHDRAWN.
Numbers only: choosing comps and judging condition is Claude's job.
"""
import csv
import json
import math
import os
import re
import statistics
from datetime import date, datetime, timedelta

NUMERIC = ("living_area", "current_price", "close_price", "original_list_price", "seller_paid_buyer_costs",
           "days_on_market", "lot_acres", "year_built", "beds", "full_baths", "half_baths", "garage_spaces",
           "floor_number", "distance", "latitude", "longitude", "total_annual_fees", "annual_cdd_fee")
FLAGS = ("waterfront", "water_view", "new_construction", "senior_community", "land_lease")  # Y/N columns: True, False or None
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


def columns_arg(value):
    """--columns: a JSON file path or inline JSON object, or None."""
    if not value:
        return None
    if os.path.exists(value):
        with open(value, encoding="utf-8") as f:
            return json.load(f)
    try:
        return json.loads(value)
    except ValueError:
        raise ExportError("--columns should be a JSON file or a JSON object mapping field names to headers.") from None


class Homes(list):
    """The loaded records, plus `notes` for the agent (duplicates dropped, values ignored)."""
    notes = ()


def _flag(v):
    s = str(v or "").strip().lower()
    return True if s in ("true", "yes", "y", "1") else False if s in ("false", "no", "n", "0") else None


FLOOD_RISK = ("VE", "V", "AE", "AH", "AO", "A", "D", "X500", "X")  # riskiest first


def resolve_export(path, data_file=None):
    """The export path from a data file: as written when it exists (absolute, or relative to where the script runs),
    else relative to the data file's own folder, where report.json and the export usually sit together."""
    if not path or not data_file or os.path.isabs(path) or os.path.exists(path):
        return path
    beside = os.path.join(os.path.dirname(os.path.abspath(data_file)), path)
    return beside if os.path.exists(beside) else path


def flood_zone(v):
    """The riskiest FEMA zone named in a free-typed flood field ('X*', 'Yes (X, X500, Ae)'), or None ('xx', 'n')."""
    found = set(re.findall(r"\b(VE|V|AE|AH|AO|A|D|X500|X)\b", str(v or "").upper().replace("*", " ")))
    return next((z for z in FLOOD_RISK if z in found), None)


def type_key(v):
    """'single_family', 'townhouse', 'condo', 'villa', 'manufactured', 'multifamily' or the lowercased value."""
    s = str(v or "").lower().replace("_", " ")
    for key, words in (("single_family", ("single family", "detached", "sfr")), ("townhouse", ("townh",)),
                       ("condo", ("condo",)), ("villa", ("villa", "half duplex")), ("manufactured", ("manufactured", "mobile")),
                       ("multifamily", ("duplex", "triplex", "quad", "multi"))):
        if any(w in s for w in words):
            return key
    return s.strip() or None


NEAR_TYPES = {"single_family", "townhouse", "villa"}  # overlap in size and price often enough to compare


def stories_key(v):
    s = str(v or "").strip().lower()
    return {"one": 1, "1": 1, "two": 2, "2": 2, "three or more": 3, "three": 3, "3": 3}.get(s, "split" if s else None)


def _headers(columns):
    """Accepted header names per field: a layer value may list several (standard names first, Matrix labels after)."""
    return {k: [v] if isinstance(v, str) else list(v or []) for k, v in columns.items()}


def load(path, market, columns=None):
    """Records from a CSV export. `columns` maps the skills' field names to the export's headers (a header or a list of
    accepted headers); without it, the built-in MLS layer's `mls_format.cma_export_columns` (Stellar) is used.

    Sold duplicates (one closing entered twice, e.g. a 'Sold Data Entry Only' copy) are dropped and counted in `notes`.
    """
    columns = columns or market.get("mls_format.cma_export_columns")
    if not columns:
        raise ExportError("This MLS isn't built in: map the export's column headers to the field names "
                          "(address, status, living_area, close_price, current_price, ...) and pass them as columns.")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        cols = {k: next((h for h in names if h in headers), None) for k, names in _headers(columns).items()}
        needed = ("address", "status", "living_area", "close_price", "current_price")
        missing = [_headers(columns)[k][0] for k in needed if not cols.get(k)]
        if missing:
            raise ExportError(f"The export is missing these columns: {', '.join(missing)}.")
        homes = Homes()
        for row in reader:
            rec = {key: row.get(col, "") for key, col in cols.items() if col}
            for k in NUMERIC:
                if k in rec:
                    rec[k] = _num(rec[k])
            for k in DATES:
                if k in rec:
                    rec[k] = _date(rec[k])
            for k in FLAGS:
                if k in rec:
                    rec[k] = _flag(rec[k])
            rec["address"] = str(rec.get("address", "")).strip()
            token = str(rec.get("status", "")).split()[0].upper() if rec.get("status") else ""
            rec["status_raw"] = rec.get("status", "")
            rec["status"] = STATUS.get(token, token or "UNKNOWN")
            pool = _flag(rec.get("pool"))
            rec["private_pool"] = pool if pool is not None else "private" in str(rec.get("pool", "")).lower()
            rec["seller_paid"] = rec.pop("seller_paid_buyer_costs", None) or 0.0
            rec["type_key"] = type_key(rec.get("property_type"))
            if "flood_zone" in rec:
                rec["flood_zone_raw"], rec["flood_zone"] = rec["flood_zone"], flood_zone(rec["flood_zone"])
            if rec.get("lot_acres") is not None and (rec["type_key"] == "condo" or rec["lot_acres"] > 100):
                rec["lot_acres"] = None  # condo lots and typos (711 acres) mean nothing for a comp
            if rec.get("days_on_market") is not None and rec["days_on_market"] < 0:
                rec["days_on_market"] = None
            if rec.get("contract_date") and rec.get("close_date") and rec["contract_date"] > rec["close_date"]:
                rec["contract_date"] = None  # a typo: the contract can't come after the closing
            homes.append(rec)
    return _drop_duplicate_sales(homes)


def _filled(h):
    return sum(v not in (None, "", 0) for v in h.values()) + len(str(h.get("remarks") or "")) / 100


def _drop_duplicate_sales(homes):
    """One closing entered twice: same address and price, closed within about a month. Keeps the fuller record."""
    keep, dropped = Homes(), 0
    for h in homes:
        twin = next((k for k in keep if h["status"] == k["status"] == "SOLD" and h.get("close_price")
                     and h["close_price"] == k.get("close_price") and same_address(h["address"], k["address"])
                     and h.get("close_date") and k.get("close_date") and abs((h["close_date"] - k["close_date"]).days) <= 31), None)
        if twin is None:
            keep.append(h)
            continue
        dropped += 1
        if _filled(h) > _filled(twin):
            keep[keep.index(twin)] = h
    keep.notes = [f"Dropped {dropped} duplicate sale record(s): the same closing entered twice (same address and price)."] if dropped else []
    return keep


def _miles(a, b):
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def fill_distances(homes, address=None, coords=None):
    """Miles from the subject, from Latitude/Longitude, for exports without a Distance column (a zip or subdivision
    search). The subject's point is `coords` (lat, lon) or its own row in the export. Returns True when filled."""
    if any(h.get("distance") is not None for h in homes):
        return False
    if not coords and address:
        row = next((h for h in homes if same_address(h["address"], address) and h.get("latitude") and h.get("longitude")), None)
        coords = (row["latitude"], row["longitude"]) if row else None
    if not coords or None in coords:
        return False
    for h in homes:
        if h.get("latitude") and h.get("longitude"):
            h["distance"] = round(_miles(coords, (h["latitude"], h["longitude"])), 2)
    return True


def subject_facts(homes, address):
    """Type, stories, water and community facts from the subject's own row, for ranking comps against it."""
    row = next((h for h in homes if same_address(h["address"], address)), None) or {}
    return {k: row.get(k) for k in ("property_type", "stories", "waterfront", "senior_community", "land_lease") if row.get(k) is not None}


def same_address(a, b):
    return " ".join(str(a).upper().split()) == " ".join(str(b).upper().split())


def _median(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def period_stats(sold):
    if not sold:
        return {"n": 0}
    paid = [h["seller_paid"] or 0 for h in sold]
    # CMA-22: net of seller-paid buyer costs, so a $10k credit on a list-price sale reads as 98%, not 100%
    ratios = [(h["close_price"] - (h["seller_paid"] or 0)) / h["original_list_price"] for h in sold if h.get("original_list_price")]
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


DISTRESSED = re.compile(r"\b(reo|bank[- ]owned|foreclos\w*|short sale|auction|hud home|lender[- ]owned|third party approval)\b", re.I)
NEW_BUILD = re.compile(r"\b(new construction|builder|to be built|under construction|never lived in|spec home)\b", re.I)


def sale_flags(h):
    """CMA-8: 'distressed' (REO, short sale, auction) and 'new_construction' sales, from the special sale conditions,
    new-construction flag, terms and remarks."""
    text = f'{h.get("sale_provisions") or ""} {h.get("sale_terms") or ""} {h.get("remarks") or ""} {h.get("sold_remarks") or ""}'
    flags = []
    if DISTRESSED.search(text):
        flags.append("distressed")
    built, closed = h.get("year_built"), h.get("close_date")
    if h.get("new_construction") or NEW_BUILD.search(text) or (built and closed and built >= closed.year - 1):
        flags.append("new_construction")
    return flags


def _as_date(value, name):
    if value in (None, "") or isinstance(value, date):
        return value or None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ExportError(f"{name} should be a date like 2026-07-01, not {value!r}.") from None


def market_stats(homes, subject, split_date=None, exclude_address=None, as_of=None, limit=15):
    """Sold stats (all, earlier, recent), inventory, months of supply, subdivision stats, comp candidates, competition.

    `subject`: {address, living_area, private_pool, subdivision, distressed} and, when known, property_type, stories,
    waterfront, senior_community, land_lease (see `subject_facts`). The export holds the property types the agent chose;
    other types still rank, just lower (single-family, townhouse and villa sit close). `exclude_address` drops every row for
    that address first (the seller CMA ignores the subject's own listings). `as_of` (default: the last sale) is where
    the recent period and months of supply are measured to. `limit` caps the ranked comp candidates; the count of the
    rest is `more_candidates`.
    """
    if exclude_address:
        homes = [h for h in homes if not same_address(h["address"], exclude_address)]
    sold = [h for h in homes if h["status"] == "SOLD" and h.get("close_price") and h.get("close_date")]
    if not sold:
        raise ExportError("The export has no sold homes with a close price and date.")
    last, first = max(h["close_date"] for h in sold), min(h["close_date"] for h in sold)
    end = max(_as_date(as_of, "as_of") or last, last)
    split = _as_date(split_date, "--split-date") or last - timedelta(days=90)
    early = [h for h in sold if h["close_date"] < split]
    recent = [h for h in sold if h["close_date"] >= split]
    months_recent = max((end - split).days / 30.44, 0.5)
    pendings = [h for h in homes if h["status"] == "PENDING"]
    actives = [h for h in homes if h["status"] == "ACTIVE" and not same_address(h["address"], subject.get("address", ""))]
    cuts = [h for h in actives if h.get("current_price") and h.get("original_list_price")]
    counts = {}
    for h in homes:
        counts[h["status"]] = counts.get(h["status"], 0) + 1

    out = {
        "window": {"first_close": str(first), "last_close": str(last), "split_date": str(split), "as_of": str(end)},
        "sold_all": period_stats(sold), "sold_early": period_stats(early), "sold_recent": period_stats(recent),
        "active_count": len(actives),
        "active_share_with_price_cut": round(sum(h["current_price"] < h["original_list_price"] for h in cuts) / len(cuts), 3) if cuts else 0,
        # CMA-22: pendings count as sales in progress, and the pace runs to the as-of date, not the last close
        "months_supply_at_recent_pace": round(len(actives) / ((len(recent) + len(pendings)) / months_recent), 1)
        if recent or pendings else None,
        "status_counts": counts,
    }
    types = {}
    for h in sold:
        types[h["type_key"] or "unknown"] = types.get(h["type_key"] or "unknown", 0) + 1
    if len(types) > 1:
        out["sold_by_type"] = types

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
            months = (end - h["close_date"]).days / 30.44
            flags = sale_flags(h)
            score = (same_sub * 3 + pool_match * 2 + (abs(size_diff) <= 0.2) * 2 - abs(size_diff) * 5
                     - 0.25 * months  # CMA-9: newer sales first
                     - (min(h["distance"], 5) * 0.8 if h.get("distance") is not None else 0)  # and closer ones
                     - 3 * ("distressed" in flags and not subject.get("distressed"))  # CMA-8
                     - 2 * ("new_construction" in flags)
                     - _mismatch(subject, h))
            scored.append((score, round(size_diff, 3), h))
        scored.sort(key=lambda x: -x[0])
        out["sold_candidates"] = [_summary(h, size_diff=d) for _, d, h in scored[:limit]]
        out["more_candidates"] = max(0, len(scored) - limit)
    others = [h for h in homes if h["status"] != "SOLD" and not same_address(h["address"], subject.get("address", ""))]
    sold_at = {" ".join(h["address"].upper().split()) for h in sold}
    out["competition"] = _one_per_address(others, sold_at)
    return out


LISTING_ORDER = ("ACTIVE", "PENDING", "EXPIRED", "WITHDRAWN", "CANCELED")


def _one_per_address(others, sold_at=()):
    """A relisted home once: its live listing if any, else its lowest last price, with `listings` counting the rest.
    A canceled or expired listing of a home that later sold isn't competition (the sale is already in the stats)."""
    by = {}
    for h in others:
        if h["status"] not in ("ACTIVE", "PENDING") and " ".join(h["address"].upper().split()) in sold_at:
            continue
        by.setdefault(" ".join(h["address"].upper().split()), []).append(h)
    rows = []
    for group in by.values():
        group.sort(key=lambda h: (LISTING_ORDER.index(h["status"]) if h["status"] in LISTING_ORDER else 9,
                                  h.get("current_price") or 0))
        s = _summary(group[0])
        if len(group) > 1:
            s["listings"] = len(group)
            s["earlier_prices"] = sorted({h["current_price"] for h in group[1:] if h.get("current_price")}, reverse=True)
        rows.append((group[0].get("distance"), s))
    rows.sort(key=lambda r: r[0] if r[0] is not None else 99)
    return [s for _, s in rows]


def _mismatch(subject, h):
    """Ranking penalty for a comp that differs from the subject in type, community rules, water or stories."""
    p = 0.0
    st, ht = type_key(subject.get("property_type")), h.get("type_key")
    if st and ht and st != ht:
        p += 1.5 if {st, ht} <= NEAR_TYPES else 4
    for k in ("senior_community", "land_lease"):  # 55+ and leased land price differently
        if subject.get(k) is not None and h.get(k) is not None and bool(subject[k]) != bool(h[k]):
            p += 4
    if subject.get("waterfront") is not None and h.get("waterfront") is not None and bool(subject["waterfront"]) != bool(h["waterfront"]):
        p += 2
    ss, hs = stories_key(subject.get("stories")), stories_key(h.get("stories"))
    if ss and hs and ss != hs:
        p += 1
    return p


def _summary(h, size_diff=None):
    keys = ("address", "status", "subdivision", "distance", "close_date", "close_price", "current_price",
            "original_list_price", "seller_paid", "living_area", "beds", "full_baths", "year_built", "pool",
            "lot_acres", "days_on_market", "sale_terms")
    extra = ("property_type", "half_baths", "stories", "floor_number", "construction", "garage_spaces", "waterfront",
             "water_frontage", "water_access", "water_view", "flood_zone", "senior_community", "land_lease",
             "total_annual_fees", "annual_cdd_fee", "furnished", "sale_provisions")  # only when the export has them
    s = {k: (str(h[k]) if isinstance(h.get(k), date) else h.get(k)) for k in keys if k in h}
    s.update({k: h[k] for k in extra if h.get(k) not in (None, "")})
    s["remarks"] = str(h.get("remarks", ""))[:700]
    if h.get("sold_remarks"):
        s["sold_remarks"] = str(h["sold_remarks"])[:300]
    s["flags"] = sale_flags(h)
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
