"""Compute every number in the buyer CMA from report.json and the MLS export.

    python3 scripts/compute.py report.json [--out DIR]

Prints JSON: taxes, payment scenarios, price-vs-credit scenarios, buydown, scatter trend, the
offer plan and range, the listing history's counts, formatted for the markdown template, plus `warnings` to fix.
With only `subject`, `comps` (and `history`) in report.json (no bottom_line, offer_plan or costs yet), it prints the
adjusted comps alone: the median, the spread, the outlier warnings and a rough plan, to set the range from or answer a
gut check. Also writes <address>.buyer.cma.json (the CMA handoff the
offer skills read) next to report.json, in the working folder, never the outputs. render.py uses the same numbers for the PDF.
"""
import argparse
import json
import math
import os
import re
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, handoff, mls, profiles  # noqa: E402

money = finance.money


class ReportError(ValueError):
    """Something report.json needs; the message is written for the agent."""


def _frac(block, key, where, default=None):
    """A `*_pct` value from report.json as a fraction (0.05 = 5%), or `default` when not given."""
    try:
        return finance.fraction(block.get(key), f"{where}.{key}", default)
    except ValueError as e:
        raise ReportError(str(e)) from e


def _require(R, *paths):
    for path in paths:
        node = R
        for part in path.split("."):
            if not isinstance(node, dict) or node.get(part) in (None, ""):
                raise ReportError(f"report.json is missing {path}.")
            node = node[part]


def taxes(R, market):
    """Buyer's estimated bill for each jurisdiction, at the purchase price in costs.taxes."""
    t = R["costs"]["taxes"]
    county = R["subject"].get("county")
    out = []
    for j in t["jurisdictions"]:
        school, total, problem = j.get("school_mills"), j.get("total_mills"), None
        if total is None and j.get("district"):
            row, problem = finance.millage_row(market, county, j["district"])
            if row:
                school, total = row["school"], row["total"]
        est = finance.property_tax(t["purchase_price"], market, school, total, t.get("homestead", True))
        out.append({"label": j["label"], "short": j.get("short", ""), "school_mills": school, "total_mills": total,
                    "annual": est["annual"], "estimated": est["estimated"], "basis": est["basis"], "problem": problem})
    return out


def payments(R, market, tax_rows):
    pay = R["costs"]["payment"]
    ji = pay.get("tax_jurisdiction_index", 0)
    price, cash = pay["price"], R["costs"].get("buyer_cash")

    def tax_at(p, index=ji):
        j = tax_rows[index]
        est = finance.property_tax(p, market, j["school_mills"], j["total_mills"], R["costs"]["taxes"].get("homestead", True))
        return est["annual"] or 0

    flood = flood_line(R, market)
    rows = []
    for i, sc in enumerate(pay["scenarios"]):
        if sc.get("type") is None or sc.get("down_pct") is None:
            raise ReportError(f"costs.payment.scenarios[{i}] needs a type and a down_pct (0.05 for 5%).")
        sc["down_pct"] = _frac(sc, "down_pct", f"costs.payment.scenarios[{i}]")
        r = finance.monthly_payment(price, sc["type"], sc["down_pct"], pay["rate"], tax_at(price),
                                    pay["insurance_annual"], pay.get("hoa_cdd_monthly", 0), flood_annual=flood["annual"])
        rows.append({"label": sc["label"], **r, "total_display": money(r["total"]), "cash_down_display": money(r["cash_down"]),
                     "cash_short": _short(r["cash_down"], cash)})
    first = pay["scenarios"][0]
    lower = finance.monthly_payment(price - 10000, first["type"], first["down_pct"], pay["rate"], tax_at(price - 10000),
                                    pay["insurance_annual"], pay.get("hoa_cdd_monthly", 0), flood_annual=flood["annual"])
    alt = None
    if len(tax_rows) == 2 and tax_rows[1 - ji]["annual"] is not None:
        alt = {"short": tax_rows[1 - ji]["short"], "delta_monthly": (tax_at(price, 1 - ji) - tax_at(price)) / 12}
    tj = tax_rows[ji]
    # CMA-204: which tax the payment uses. Two jurisdictions mean the district isn't confirmed: the payment uses the
    # one at tax_jurisdiction_index (the higher bill by default), labeled Estimate, as is a fallback-rate estimate.
    tax_basis = {"short": tj["short"], "unconfirmed": len(tax_rows) == 2, "estimated": bool(tj["estimated"]),
                 "basis": tj["basis"], "higher": len(tax_rows) == 2 and (tj["annual"] or 0) >= (tax_rows[1 - ji]["annual"] or 0)}
    tax_basis["label_estimate"] = tax_basis["unconfirmed"] or tax_basis["estimated"]
    return {"price": price, "price_display": money(price), "price_basis": price_basis(price, R), "rate": pay["rate"],
            "insurance_annual": pay["insurance_annual"], "rows": rows, "flood": flood,
            "per_10k": rows[0]["total"] - lower["total"], "alt_jurisdiction": alt, "tax_index": ji, "tax_basis": tax_basis,
            "buyer_cash": cash, "buyer_cash_display": money(cash) if cash else None}


def _short(need, have):
    """How much more cash `need` takes than the buyer has (CMA-204), or None when it fits or `have` isn't given."""
    return round(need - have) if isinstance(have, (int, float)) and have and need > have + 1 else None


def flood_line(R, market):
    """CMA-6: the payment's flood insurance line. A quote (`costs.payment.flood_insurance_annual`) is counted; without
    one the row reads "get a quote" and the total leaves it out, never $0. The zone is `costs.payment.flood_zone`,
    else the Flood Zone fact."""
    pay, s = R["costs"]["payment"], R["subject"]
    zone = pay.get("flood_zone") or next((v for lbl, v in s.get("facts") or [] if str(lbl).lower() == "flood zone"), None)
    return finance.flood_insurance(zone, pay.get("flood_insurance_annual"), market,
                                   date.fromisoformat(R["as_of"]) if R.get("as_of") else None,
                                   condo_unit=finance.property_type(s.get("property_type")) == "condo")


def credit_scenarios(R, market, tax_rows, median_adjusted):
    cs = R["costs"].get("credit_scenarios")
    if not cs:
        return None
    pay = R["costs"]["payment"]
    ji = pay.get("tax_jurisdiction_index", 0)
    program = finance.program(cs.get("loan_type", "conventional"))
    down = _frac(cs, "down_pct", "costs.credit_scenarios", 0.05)
    closing_pct = _frac(cs, "closing_cost_pct", "costs.credit_scenarios")
    # CORE-16: with no lender figure, the market's share of price plus its loan taxes, itemized on the loan amount
    itemize = closing_pct is None and not cs.get("closing_costs") and program != "cash"
    if closing_pct is None:
        closing_pct = market.get("closing_costs.buyer_closing_cost_pct") or 0.03
    cap = finance.concession_cap(program, down)
    agreement = _frac(cs, "buyer_broker_agreement_pct", "costs.credit_scenarios")  # CMA-4: the buyer's own agreement
    seller_pays = _frac(cs, "seller_pays_buyer_broker_pct", "costs.credit_scenarios", 0)
    cols, base = [], None
    for x in cs["scenarios"]:
        price, credit = x["price"], x["credit"]
        j = tax_rows[ji]
        tax = finance.property_tax(price, market, j["school_mills"], j["total_mills"], R["costs"]["taxes"].get("homestead", True))["annual"] or 0
        p = finance.monthly_payment(price, program, down, pay["rate"], tax, pay["insurance_annual"], pay.get("hoa_cdd_monthly", 0),
                                    flood_annual=flood_line(R, market)["annual"])
        taxes = finance.loan_taxes(p["loan"], market) if itemize else []
        cc = cs["closing_costs"] if cs.get("closing_costs") else price * closing_pct + sum(t["amount"] for t in taxes)
        bb_short = finance.buyer_broker_shortfall(price, agreement, seller_pays) or 0
        col = {"price": price, "credit": credit, "net": price - credit, "loan": p["loan"], "bb_short": bb_short,
               "cash": p["cash_down"] + cc - min(credit, cc) + bb_short, "payment": p["total"], "pi": p["pi"],
               "cap": price * cap if cap is not None else None,
               "over_cap": cap is not None and credit > price * cap + 1, "over_costs": credit > cc + 1,
               "appraisal_room": median_adjusted - price, "closing_costs": cc, "loan_taxes": sum(t["amount"] for t in taxes)}
        col["cash_short"] = _short(col["cash"], R["costs"].get("buyer_cash"))  # CMA-204
        base = base or col
        col["extra"] = col["payment"] - base["payment"]
        saved = base["cash"] - col["cash"]
        col["payback_years"] = saved / (col["extra"] * 12) if col["extra"] > 0 and saved > 0 else None
        cols.append(col)
    # CMA-11: a higher price raises the seller's percentage costs, so "price minus credit" isn't quite their net
    transfer = market.get("closing_costs.deed_transfer_tax_rate") if market.get("closing_costs.deed_transfer_tax_payer") \
        in (None, "seller") else 0
    seller_cost_pct = (transfer or 0) + (seller_pays or 0)
    out = {"program": program, "down_pct": down, "columns": cols, "seller_cost_per_10k": round(10000 * seller_cost_pct),
           "seller_cost_parts": [x for x, v in (("transfer tax", transfer), ("buyer-broker pay", seller_pays)) if v],
           "closing_costs_given": bool(cs.get("closing_costs")), "closing_cost_pct": closing_pct,
           "loan_tax_labels": [t["label"] for t in finance.loan_taxes(1, market)] if itemize else []}
    bd = cs.get("buydown")
    if bd:
        col = next((c for c in cols if c["price"] == bd.get("price")), cols[-1])
        b = finance.buydown_2_1(col["loan"], pay["rate"])
        other = col["payment"] - col["pi"]
        credit = bd.get("credit", col["credit"])
        out["buydown"] = {"price": col["price"], "credit": credit, "cost": b["cost"], "covered": credit >= b["cost"],
                          "year1": b["year1"] + other, "year2": b["year2"] + other, "full": b["full"] + other}
    return out


# CMA-201: history.events, one per row of the MLS history grid. `change` is a plain word or the MLS's code (Stellar's
# NEW, DECR, INCR, TOM, BOM, PNC, SLD, CANC, EXP, WDN); what each does to the listing's status.
HISTORY_CHANGES = {
    "listed": "active", "new": "active", "price": None, "decr": None, "incr": None,
    "off_market": "off", "tom": "off", "back_on": "active", "bom": "active",
    "pending": "pending", "pnc": "pending", "sold": "sold", "sld": "sold",
    "canceled": "ended", "canc": "ended", "expired": "ended", "exp": "ended", "withdrawn": "ended", "wdn": "ended",
}
HISTORY_NEW = ("listed", "new")
HISTORY_KIND = {"new": "listed", "decr": "price", "incr": "price", "tom": "off_market", "bom": "back_on", "pnc": "pending",
                "sld": "sold", "canc": "canceled", "exp": "expired", "wdn": "withdrawn"}


def _plural(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s") if n else f"no {word}s"


def history_stats(R, as_of):
    """CMA-201, CMA-208: the listing history counted from `history.events` instead of by hand: price cuts and
    increases, the total cut in dollars and as a share of the first list price, failed contracts, and the days the
    home was actively for sale across every MLS number. Returns (stats or None, [(warning key, text)]).

    Each event is {date: YYYY-MM-DD, mls, change, price (the asking price after it, when the row shows one), dom (the
    grid's days on market at that row, when it shows one), note (optional wording for the report's row)}, in the
    grid's order. `timeline` is the same events oldest first, for the report's table. A price that differs from the asking
    price before it is a cut or an increase, whatever the row's code. A listing's active days are its latest `dom`
    (plus the days since, while it's still for sale), else counted by the calendar from its status changes; the
    current listing runs to `as_of`. Rows out of date order in the grid and an MLS number that doesn't match the
    subject's are warned, never silently fixed."""
    h = R.get("history") or {}
    events, notes = h.get("events"), []
    if not events:
        if h.get("rows"):
            notes.append(("history_no_events", "history.rows has no history.events: add one event per row of the MLS "
                          "history grid so the script counts the price changes and active days (report-data.md)."))
        return None, notes
    rows = []
    for i, e in enumerate(events):
        change = str(e.get("change", "")).strip().lower().replace(" ", "_")
        if change not in HISTORY_CHANGES:
            raise ReportError(f"history.events[{i}].change is {e.get('change')!r}: use listed, price, off_market, back_on, "
                              "pending, sold, canceled, expired or withdrawn (or the MLS code, such as DECR).")
        try:
            when = date.fromisoformat(str(e.get("date")))
        except ValueError:
            raise ReportError(f"history.events[{i}].date is {e.get('date')!r}: write it as YYYY-MM-DD.") from None
        price = e.get("price")
        if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool)):
            raise ReportError(f"history.events[{i}].price must be a plain number (474900), not {price!r}.")
        rows.append({"i": i, "date": when, "mls": str(e.get("mls") or "").strip().upper() or None, "change": change,
                     "price": price, "dom": e.get("dom")})
    # the grid's order: newest first normally; any row that breaks the direction is out of date order
    newest_first = rows[0]["date"] >= rows[-1]["date"]
    for a, b in zip(rows, rows[1:]):
        if (b["date"] > a["date"]) if newest_first else (b["date"] < a["date"]):
            notes.append(("history_order", f"history.events[{b['i']}] ({b['date']:%b %-d, %Y}) is out of date order in the "
                          f"grid, next to {a['date']:%b %-d, %Y}. Check that row's date with the MLS before quoting it; it "
                          "was counted by its date."))
    rows.sort(key=lambda r: (r["date"], -r["i"] if newest_first else r["i"]))
    subject_mls = subject_mls_number(R["subject"])
    newest_mls = next((r["mls"] for r in reversed(rows) if r["mls"]), None)
    if subject_mls and newest_mls and newest_mls != subject_mls:
        notes.append(("history_mls_mismatch", f"The newest history row is MLS {newest_mls}, but the listing is MLS "
                      f"{subject_mls}: check that the history is this home's current listing."))
    # the price changes: any row whose price differs from the asking price before it (a new listing restarts it)
    cuts, increases, asking, first_price, first_listed = [], [], None, None, None
    for r in rows:
        r["delta"] = 0
        if r["change"] in HISTORY_NEW:
            asking = r["price"] if r["price"] is not None else asking
            first_price, first_listed = first_price or r["price"], first_listed or r["date"]
            continue
        if r["price"] is None or HISTORY_CHANGES[r["change"]] == "sold":  # a sale price isn't an asking price
            continue
        if asking is not None and r["price"] != asking:
            r["delta"] = r["price"] - asking
            (cuts if r["delta"] < 0 else increases).append(abs(r["delta"]))
        asking = r["price"]
    # active days and failed contracts, listing by listing
    listings, current = [], None
    for r in rows:
        if r["change"] in HISTORY_NEW or current is None or (r["mls"] and current["mls"] and r["mls"] != current["mls"]):
            current = {"mls": r["mls"], "rows": []}
            listings.append(current)
        current["mls"] = current["mls"] or r["mls"]
        current["rows"].append(r)
    end = date.fromisoformat(as_of)
    active_days, failed = 0, 0
    for n, lst in enumerate(listings):
        status, since, days, stop = None, None, 0, listings[n + 1]["rows"][0]["date"] if n + 1 < len(listings) else end
        for r in lst["rows"]:
            new = HISTORY_CHANGES[r["change"]]
            if status == "pending" and new not in (None, "pending", "sold"):
                failed += 1
            if new is None:
                continue
            if status == "active" and since:
                days += (r["date"] - since).days
            status, since = new, r["date"] if new == "active" else None
        if status == "active" and since:
            days += max((stop - since).days, 0)
        with_dom = [r for r in lst["rows"] if isinstance(r.get("dom"), (int, float))]
        if with_dom:  # the MLS's own count wins, plus the days since while it's still for sale
            last = with_dom[-1]
            days = last["dom"] + (max((stop - last["date"]).days, 0) if status == "active" else 0)
        active_days += days
    total_cut, first_listed = sum(cuts), first_listed or rows[0]["date"]
    timeline = []
    for r in rows:  # oldest first, for the report's table (render.py words each kind from labels.json)
        kind = HISTORY_KIND.get(r["change"], r["change"])
        if kind == "price":
            kind = "price_cut" if r["delta"] < 0 else "price_increase" if r["delta"] > 0 else "price"
        timeline.append({"date": r["date"].isoformat(), "kind": kind, "price": r["price"], "delta": r["delta"],
                         "mls": r["mls"], "note": events[r["i"]].get("note")})
    stats = {
        "events": len(rows), "first_listed": first_listed.isoformat(),
        "listings": sum(1 for lst in listings if any(HISTORY_CHANGES[r["change"]] == "active" for r in lst["rows"])),
        "first_list_price": first_price, "current_price": asking,
        "price_cuts": len(cuts), "price_increases": len(increases), "price_cut_total": total_cut,
        "price_cut_pct": round(total_cut / first_price, 4) if first_price and total_cut else 0,
        "price_increase_total": sum(increases), "failed_contracts": failed, "active_days": active_days,
        "timeline": timeline,
    }
    stats["display"] = {
        "price_cuts": _plural(len(cuts), "price cut"), "price_cut_count": str(len(cuts)),
        "price_increases": _plural(len(increases), "price increase"),
        "price_cut_total": money(total_cut), "price_cut_pct": f"{stats['price_cut_pct'] * 100:.1f}%",
        "failed_contracts": _plural(failed, "failed contract"), "active_days": _plural(active_days, "day"),
        "first_listed": f"{first_listed:%B %-d, %Y}",
    }
    return stats, notes


def subject_mls_number(s):
    """The listing's MLS number: `subject.mls_number`, else the "MLS #" part of `subject.locality`."""
    if s.get("mls_number"):
        return str(s["mls_number"]).strip().upper()
    m = re.search(r"\bMLS\s*#?\s*([A-Z]{0,3}\d{5,})", str(s.get("locality") or ""), re.I)
    return m.group(1).upper() if m else None


def export_mls_warning(R, homes):
    """CMA-208: the export's current (active or pending) row for the subject carries a different MLS number than the
    listing. An old sale or expired listing of the same home has its own number, so only a current row counts."""
    s, number = R["subject"], subject_mls_number(R["subject"])
    row = next((h for h in homes if h["status"] in ("ACTIVE", "PENDING")
                and mls.same_address(h["address"], s.get("mls_address", s["address"]))), None)
    theirs = str((row or {}).get("mls_number") or "").strip().upper()
    if number and theirs and theirs != number:
        return [f"The export's row for {s.get('mls_address', s['address'])} is MLS {theirs}, but the listing is MLS {number}: "
                "the export may predate the relist. Check its days on market and price against the listing before quoting them."]
    return []


def rough_plan(R, market, median, lo, hi):
    """CMA-202: the gut check's rough numbers, before any range or offer plan exists. Rough range: the adjusted comps'
    span. Rough walk-away: the median adjusted value, rounded down to $1,000 (offer-plan.md: at or below the median).
    Rough opening: the median minus half the market's typical range width (5% of the median where none is built in),
    rounded down to $1,000: the bottom of a typical range centered on the median, where offer-plan.md opens. Rough
    target: halfway between, to the nearest $1,000. None goes above the asking price."""
    ask = R["subject"]["list_price"]
    width = market.get("cma.typical_range_width") or 0.05 * median
    walk = min(math.floor(median / 1000) * 1000, ask)
    opening = min(math.floor((median - width / 2) / 1000) * 1000, walk)
    target = min(max(round((opening + walk) / 2000) * 1000, opening), walk)
    return {"range": {"low": lo, "high": hi, "display": f"{money(lo)} – {money(hi)}"},
            "opening": opening, "target": target, "walk_away": walk, "typical_width": width,
            "capped_at_asking": walk == ask and math.floor(median / 1000) * 1000 > ask,
            "display": {"opening": money(opening), "target": money(target), "walk_away": money(walk)},
            "label": "Rough: from the adjusted comps alone, before the full analysis"}


PLACEHOLDER = re.compile(r"\{(\w+)\}")
RENDER_PLACEHOLDERS = ("trend_at_subject", "r2_share")  # filled by render.py from the chart


def placeholder_values(median_adjusted, hist, credit=None):
    """CMA-203: every {name} report wording may use, filled in every field (not just page 1). With price-vs-credit
    scenarios, {credit_cash_per_5k} and {credit_monthly_per_5k}: what each $5,000 of credit saves at closing and adds
    to the monthly payment, from the first two scenarios with different credits."""
    values = {"median_adjusted": money(median_adjusted), **((hist or {}).get("display") or {})}
    cols = (credit or {}).get("columns") or []
    step = next((c for c in cols[1:] if c["credit"] != cols[0]["credit"]), None)
    if step:
        scale = 5000 / (step["credit"] - cols[0]["credit"])
        values.update(credit_cash_per_5k=money(round((cols[0]["cash"] - step["cash"]) * scale, -2)),
                      credit_monthly_per_5k=money(round((step["payment"] - cols[0]["payment"]) * scale)))
    return values


def unfilled_placeholders(R, known, path="$"):
    """(path, {name}) for every placeholder in the report's wording that no script fills: it would print as typed."""
    out = []
    if isinstance(R, str):
        out += [(path, m.group(0)) for m in PLACEHOLDER.finditer(R) if m.group(1) not in known]
    elif isinstance(R, list):
        for i, v in enumerate(R):
            out += unfilled_placeholders(v, known, f"{path}[{i}]")
    elif isinstance(R, dict):
        for key, v in R.items():
            if key not in ("labels", "export_columns"):
                out += unfilled_placeholders(v, known, f"{path}.{key}")
    return out


def placeholder_warnings(R, values, extra=()):
    return [f"{p} has {name}, which no script fills: it would print as typed. Use one of "
            f"{', '.join('{' + k + '}' for k in sorted(set(values) | set(extra)))}, or write the words."
            for p, name in unfilled_placeholders(R, set(values) | set(extra))]


def comp_count_warnings(cards):
    """No comps is an error; fewer than 3 is thin support and a warning."""
    if not cards:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    return [f"Only {len(cards)} comp{'s' if len(cards) > 1 else ''}: the range rests on thin support. Widen the search if you can, "
            "and say so in the report."] if len(cards) < 3 else []


def _warner():
    """(warnings, keys, warn): warn(key, *texts) adds each text with a stable key, so a test can tell which warning
    fired without matching its sentence (TEST-2); `warning_keys` runs parallel to `warnings`."""
    texts, keys = [], []

    def warn(key, *items):
        texts.extend(items)
        keys.extend([key] * len(items))
    return texts, keys, warn


def comps_first(R, market, homes=()):
    """CMA-110: the adjusted comps alone, before the range and offer plan exist, for a gut check or to set the range
    from: the median adjusted value, the spread and the outlier and adjustment warnings. Writes no handoff. With
    `history.events` it also counts the history (CMA-201), and `rough` holds the gut check's rough range, opening,
    target and walk-away (CMA-202)."""
    _require(R, "subject.address", "subject.list_price", "comps.cards")
    warnings, warning_keys, warn = _warner()
    warn("thin_comps", *comp_count_warnings(R["comps"]["cards"]))
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))
    except ValueError as e:
        raise ReportError(str(e)) from e
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))
    s, values = R["subject"], [c["adjusted"] for c in R["comps"]["cards"]]
    median_adjusted = statistics.median(values)
    hist, notes = history_stats(R, R.get("as_of") or date.today().isoformat())  # CMA-201, CMA-208
    for key, text in notes:
        warn(key, text)
    warn("export_mls_mismatch", *export_mls_warning(R, homes))
    fills = placeholder_values(median_adjusted, hist)  # CMA-203
    warn("unfilled_placeholder", *placeholder_warnings(R, fills, RENDER_PLACEHOLDERS))
    return {
        "ok": True, "stage": "comps",
        "next": "Set bottom_line (the range around the median) and offer_plan, add costs, then run compute.py again "
                "for the payments, the credit scenarios and the handoff.",
        "subject": {"address": s["address"], "list_price": s["list_price"], "list_price_display": money(s["list_price"])},
        "median_adjusted": median_adjusted, "median_adjusted_display": money(median_adjusted),
        "adjusted_min": min(values), "adjusted_max": max(values),
        "asking_vs_median": s["list_price"] - median_adjusted,
        "asking_vs_median_display": money(abs(s["list_price"] - median_adjusted)),
        "rough": rough_plan(R, market, median_adjusted, min(values), max(values)),  # CMA-202: the gut check's numbers
        "history": hist,
        "placeholders": fills,
        "comps_table": [{"address": r[0], "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in R["comps"].get("summary_rows", [])],
        "warnings": warnings,
        "warning_keys": warning_keys,
        "market_notes": market.notes,
    }


def target_price(op):
    """The offer plan's target: the middle of target_low to target_high, else the one given, else the opening."""
    lo, hi = op.get("target_low"), op.get("target_high")
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    return lo if lo is not None else hi if hi is not None else op.get("opening")


def price_basis(price, R):
    """CMA-204: which of the plan's prices the payment is figured at, so page 1 can say so."""
    op, ask = R.get("offer_plan") or {}, R["subject"]["list_price"]
    lo, hi = op.get("target_low"), op.get("target_high")
    if price == ask:
        return "asking"
    if lo is not None and (hi or lo) >= price >= lo or price == target_price(op):
        return "target"
    return {op.get("opening"): "opening", op.get("walk_away"): "walk_away"}.get(price)


def default_prices(R):
    """CMA-204: without `costs.payment.price` the payment is figured at the offer plan's target, not the asking price;
    without `costs.taxes.purchase_price` the tax estimate uses the payment's price, so page 1's numbers agree."""
    costs = R.get("costs") or {}
    pay, t = costs.get("payment"), costs.get("taxes")
    if isinstance(pay, dict) and pay.get("price") in (None, "") and R.get("offer_plan", {}).get("opening") is not None:
        pay["price"] = target_price(R["offer_plan"])
    if isinstance(t, dict) and t.get("purchase_price") in (None, "") and isinstance(pay, dict) and pay.get("price"):
        t["purchase_price"] = pay["price"]


def compute(R, market, homes):
    default_prices(R)
    _require(R, "subject.address", "subject.list_price", "subject.sqft", "bottom_line.low", "bottom_line.high",
             "offer_plan.opening", "offer_plan.walk_away", "comps.cards", "costs.taxes.purchase_price",
             "costs.payment.price", "costs.payment.rate", "costs.payment.insurance_annual")
    for block in ("costs",):  # units before any math: fractions stay fractions, interest stays a percent
        try:
            finance.check_units(R.get(block) or {}, block)
        except ValueError as e:
            raise ReportError(str(e)) from e
    market = market.with_deal(R.get("costs"))  # this home's own numbers (the state's transfer tax, a tax rate)
    n_juris, ji = len(R["costs"]["taxes"].get("jurisdictions") or []), R["costs"]["payment"].get("tax_jurisdiction_index")
    if not n_juris:
        raise ReportError("costs.taxes.jurisdictions needs at least one entry.")
    if ji is not None and (not isinstance(ji, int) or isinstance(ji, bool) or not 0 <= ji < n_juris):
        raise ReportError(f"costs.payment.tax_jurisdiction_index is {ji!r}: it must be 0 to {n_juris - 1}, the "
                          "position of the jurisdiction the payment uses in costs.taxes.jurisdictions.")
    s, bl, op = R["subject"], R["bottom_line"], R["offer_plan"]
    ladder = [("opening", op["opening"]), ("target_low", op.get("target_low")), ("target_high", op.get("target_high")),
              ("walk_away", op["walk_away"])]
    ladder = [(k, v) for k, v in ladder if v is not None]
    for (k1, v1), (k2, v2) in zip(ladder, ladder[1:]):  # CMA-20
        if v1 > v2:
            raise ReportError(f"offer_plan.{k1} ({money(v1)}) is above offer_plan.{k2} ({money(v2)}): the plan runs "
                              "opening, then target, then walk-away, from low to high.")
    if bl["low"] > bl["high"]:
        raise ReportError("bottom_line.low is above bottom_line.high.")
    warnings, warning_keys, warn = _warner()
    warn("thin_comps", *comp_count_warnings(R["comps"]["cards"]))
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))  # adjusted values and summary rows computed from their parts
    except ValueError as e:
        raise ReportError(str(e)) from e
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))
    for i, r in enumerate((R.get("competition") or {}).get("rows", [])):
        if len(r) < 7 or not all(isinstance(r[j], (int, float)) and not isinstance(r[j], bool) for j in (2, 3)):
            raise ReportError(f"competition.rows[{i}] should be [address, status, price, sqft, pool, days, notes], "
                              "with price and sqft as plain numbers (474500, not \"$474,500\").")
    median_adjusted = statistics.median(c["adjusted"] for c in R["comps"]["cards"])
    scope = cma.adjustment_scope_warning(market, (R.get("subject") or {}).get("county"), s["list_price"])  # CMA-10
    if scope:
        warn("adjustment_scope", scope)
    tax_rows = taxes(R, market)
    if ji is None:  # CMA-204: with the district unconfirmed, the payment uses the higher bill (the conservative one)
        ji = max(range(n_juris), key=lambda i: (tax_rows[i]["annual"] or 0, -i))
        R["costs"]["payment"]["tax_jurisdiction_index"] = ji
    for j in tax_rows:
        if j["problem"]:
            warn("tax_problem", j["problem"])
        if j["annual"] is None:
            warn("tax_no_rate", f"No millage or tax rate for {j['label']}: add school_mills and total_mills.")
        elif j["estimated"]:
            warn("tax_estimated", f"Tax for {j['label']} is estimated at {j['basis']}; find the millage if you can.")
    pay = payments(R, market, tax_rows) if all(j["annual"] is not None for j in tax_rows) else None
    credit = credit_scenarios(R, market, tax_rows, median_adjusted) if pay else None
    for c in (credit or {}).get("columns", []):
        if c["over_cap"]:
            warn("credit_over_cap", f"The {money(c['credit'])} credit at {money(c['price'])} is over the loan program's limit: fix the scenario.")
        elif c["over_costs"]:
            warn("credit_over_costs", f"The {money(c['credit'])} credit at {money(c['price'])} exceeds the closing costs: fix the scenario.")
    ca = op.get("credit_alt")
    if ca and credit and not any(c["price"] == ca["price"] and c["credit"] == ca["credit"] for c in credit["columns"]):
        warn("credit_alt_mismatch", "offer_plan.credit_alt doesn't match any price-vs-credit scenario.")
    if op["walk_away"] > bl["high"]:
        warn("walk_away_above_range", "The walk-away price is above the supported range: only if the buyer accepts appraisal-gap risk, and say so.")
    cash = R["costs"].get("buyer_cash")  # CMA-204: what the buyer has for down payment and closing
    for c in (credit or {}).get("columns", []):
        if c.get("cash_short"):
            warn("cash_short", f"Cash to close at {money(c['price'])} with a {money(c['credit'])} credit is about "
                 f"{money(c['cash'])}, {money(c['cash_short'])} more than the buyer's {money(cash)}: say so, and show a "
                 "scenario that fits (a larger credit, a lower price or another loan program).")
    first = ((pay or {}).get("rows") or [{}])[0]  # the buyer's own program; the other columns are comparisons, flagged only
    if first.get("cash_short"):
        warn("cash_short", f"The {first['label']} down payment alone ({money(first['cash_down'])}) is more than the "
             f"buyer's {money(cash)}.")
    hist, notes = history_stats(R, R.get("as_of") or date.today().isoformat())  # CMA-201, CMA-208
    for key, text in notes:
        warn(key, text)
    warn("export_mls_mismatch", *export_mls_warning(R, homes))
    values = placeholder_values(median_adjusted, hist, credit)  # CMA-203
    warn("unfilled_placeholder", *placeholder_warnings(R, values, RENDER_PLACEHOLDERS))

    fit = mls.trend([h for h in homes if not mls.same_address(h["address"], s.get("mls_address", s["address"]))],
                    s["sqft"], (R.get("scatter") or {}).get("fit_size_ratio", 1.6)) if homes else None

    stats = {}
    if homes:
        address = s.get("mls_address", s["address"])
        st = mls.market_stats(homes, {**mls.subject_facts(homes, address), "address": address, "living_area": s["sqft"],
                                      "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision"),
                                      **({"property_type": s["property_type"]} if s.get("property_type") else {})},
                              split_date=R.get("split_date"), as_of=R.get("as_of"))
        recent = st["sold_recent"]
        stats = {k: v for k, v in {
            "split_date": st["window"]["split_date"],
            "sale_to_original_list_recent": recent.get("median_sale_to_original_list"),
            "median_days_recent": recent.get("median_days_on_market"),
            "share_with_seller_paid_costs_recent": recent.get("share_with_seller_paid_costs"),
            "median_seller_paid_recent": recent.get("median_seller_paid_when_paid"),
            "months_supply": st["months_supply_at_recent_pace"],
            "active_count": st["active_count"]}.items() if v is not None}
    as_of = R.get("as_of") or date.today().isoformat()
    tj, pay_in = tax_rows[ji], R["costs"]["payment"]
    h = handoff.build(
        side="buyer", as_of=as_of, source="buyer-cma",
        subject={**{k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                      "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"), "baths": s.get("baths"),
                                      "year_built": s.get("year_built"), "pool": s.get("pool"), "list_price": s["list_price"]}.items()
                    if v is not None},
                 # CMA-111: the tax this report computed for the buyer, so the offer's payment matches it
                 **handoff.subject_facts(annual_tax=R["costs"]["taxes"].get("current_bill"), school_mills=tj["school_mills"],
                                         total_mills=tj["total_mills"], homestead=R["costs"]["taxes"].get("homestead", True),
                                         flood_zone=pay_in.get("flood_zone") or next((v for lbl, v in s.get("facts") or []
                                                                                      if str(lbl).lower() == "flood zone"), None),
                                         hoa_monthly=s.get("hoa_monthly"), roof_year=s.get("roof_year"))},
        value={"low": bl["low"], "high": bl["high"], "midpoint": bl.get("midpoint", (bl["low"] + bl["high"]) / 2),
               "median_adjusted": median_adjusted},
        comps=[{"address": r[0], "sold_price": r[1], "seller_paid": r[2], "adjusted": r[3]} for r in R["comps"].get("summary_rows", [])],
        market=stats,
        offer_plan={k: op[k] for k in ("opening", "target_low", "target_high", "walk_away") if k in op},
        market_profile={"state": market.state, "mls": market.mls},
    )
    data_source = {"mls": market.mls, "as_of": as_of, "export": bool(homes)}
    return {
        "data_source": data_source,
        "ok": True,
        "subject": {"address": s["address"], "list_price": s["list_price"], "list_price_display": money(s["list_price"])},
        "range": {"low": bl["low"], "high": bl["high"], "display": f"{money(bl['low'])} – {money(bl['high'])}",
                  "asking_position": "above the range" if s["list_price"] > bl["high"] else
                  "below the range" if s["list_price"] < bl["low"] else "inside the range"},
        "median_adjusted": median_adjusted, "median_adjusted_display": money(median_adjusted),
        "adjusted_min": min(c["adjusted"] for c in R["comps"]["cards"]),  # CMA-112: the spread, as seller-cma gives it
        "adjusted_max": max(c["adjusted"] for c in R["comps"]["cards"]),
        "offer_plan": {"opening": money(op["opening"]), "walk_away": money(op["walk_away"]),
                       "target": money(op.get("target_low", op["opening"])) + (
                           f" – {money(op['target_high'])}" if op.get("target_high") and op["target_high"] != op.get("target_low") else "")},
        "taxes": [{**j, "annual_display": money(j["annual"], 100) if j["annual"] is not None else None,
                   "monthly_display": money(j["annual"] / 12) if j["annual"] is not None else None} for j in tax_rows],
        "current_bill": R["costs"]["taxes"].get("current_bill"),
        "current_bill_display": money(R["costs"]["taxes"]["current_bill"]) if R["costs"]["taxes"].get("current_bill") else None,
        "payments": pay,
        "credit": credit,
        "trend": {"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
                  "r2_key": mls.r2_key(fit["r2"])} if fit else None,
        "handoff": h,
        "history": hist,
        "placeholders": values,
        # the chat template's wording, with every {placeholder} filled as the PDF fills it
        "summary_page": cma.fill(R.get("summary_page") or {}, values),
        "bottom_line_paragraph": cma.fill(bl.get("paragraph", ""), values),
        "comps_table": [{"address": r[0], "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in R["comps"].get("summary_rows", [])],  # the chat template's comp rows
        "warnings": warnings,
        "warning_keys": warning_keys,
        "market_notes": market.notes,
    }


def load_inputs(R, mls_name=None, data_file=None):
    """Market and MLS records for a report.json (`export` is the path to the MLS export CSV, `export_columns` its
    header map for an MLS that isn't built in). The MLS is `--mls`, else the report's `mls`, else the one built-in MLS
    covering the county (CMA-15)."""
    s = R.get("subject") or {}
    market = profiles.load_market(state=s.get("state"), county=s.get("county"), mls=mls_name or R.get("mls"))
    if R.get("export"):
        R["export"] = mls.resolve_export(R["export"], data_file)  # beside report.json when not found from here
    homes = mls.load(R["export"], market, R.get("export_columns")) if R.get("export") else []
    mls.fill_distances(homes, s.get("mls_address", s.get("address")),
                       (s["latitude"], s["longitude"]) if s.get("latitude") and s.get("longitude") else None)
    return market, homes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--out", help="where to write the .cma.json handoff (default: next to report.json, the working folder; never the outputs)")
    ap.add_argument("--mls", help="MLS name, as with stats.py (Stellar is built in)")
    a = ap.parse_args(argv)
    with open(a.report, encoding="utf-8") as f:
        R = json.load(f)
    try:
        market, homes = load_inputs(R, a.mls, a.report)
        if not any(R.get(k) for k in ("bottom_line", "offer_plan", "costs")):  # CMA-110: comps only, no range yet
            result = comps_first(R, market, homes)
        else:
            result = compute(R, market, homes)
            path = os.path.join(a.out or os.path.dirname(os.path.abspath(a.report)), handoff.filename(R["subject"]["address"], "buyer"))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result["handoff"], f, indent=2)
            result["handoff_file"] = path
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
