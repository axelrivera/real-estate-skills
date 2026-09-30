"""Market numbers from an MLS CMA export for pricing a listing (the subject is left out).

    python3 scripts/stats.py export.csv --address "517 HICKORYWOOD AVE" --sqft 1849 [--pool]
        [--subdivision "SPRING OAKS"] [--type single_family] [--lat 28.67 --lon -81.40]
        [--state FL --county Seminole] [--columns columns.json]
        [--split-date 2026-07-01] [--as-of 2026-09-26] [--own-listing]

Every row with the seller's address (old listings, prior sales, a current listing) is dropped
before anything is counted, and its size, pool and subdivision come from the seller, not the export.
When one of those rows is active or pending, `listed_now` is true: confirm whose listing it is first
(`--own-listing` when the agent already said it's theirs: `listed_now_action` is then "reprice", else "ask"). Prints JSON: sold stats for the whole window and
for an earlier and a recent period, inventory and months of supply, the subdivision's median $/sq ft,
ranked comp candidates with remarks, and the competition. Numbers only: picking and adjusting comps
is a judgment made from this output.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import finance, mls, profiles  # noqa: E402

money = finance.money
NEEDED = ("address", "status", "living_area", "close_price", "current_price")  # the columns mls.load requires


def builtin_layout(path):
    """The built-in MLS (its short name, "Stellar") whose export columns this CSV has, or None."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            headers = set(next(csv.reader(f), []))
    except (OSError, UnicodeDecodeError):
        return None
    for layer in profiles._layers("mls").values():
        cols = (layer.get("mls_format") or {}).get("cma_export_columns") or {}
        names = {k: [v] if isinstance(v, str) else list(v or []) for k, v in cols.items()}
        if cols and all(any(h in headers for h in names.get(k, [])) for k in NEEDED):
            return layer["mls"]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export")
    ap.add_argument("--address", required=True, help="the seller's address as it appears in the export (rows with it are dropped)")
    ap.add_argument("--sqft", type=float, required=True, help="heated living area, from the seller or public record")
    ap.add_argument("--pool", action="store_true", help="the home has a private pool")
    ap.add_argument("--subdivision", help="subdivision name as the export writes it (improves comp ranking)")
    ap.add_argument("--type", help="single_family, townhouse, condo, ... (ranks the same type first; default: the export's row)")
    ap.add_argument("--lat", type=float, help="the home's latitude, for distances when the export has no Distance column")
    ap.add_argument("--lon", type=float, help="the home's longitude")
    ap.add_argument("--state")
    ap.add_argument("--county")
    ap.add_argument("--columns", help="JSON file (or inline JSON) mapping field names to the export's headers, for an MLS that isn't built in")
    ap.add_argument("--mls", help="MLS name (Stellar is built in; assumed from the county when it's the only one)")
    ap.add_argument("--split-date", help="YYYY-MM-DD: sales on or after it are 'recent' (default: 90 days before the last sale)")
    ap.add_argument("--as-of", help="YYYY-MM-DD the export was pulled (default: the last sale); months of supply runs to it")
    ap.add_argument("--limit", type=int, default=15, help="how many ranked comp candidates to list (default 15)")
    ap.add_argument("--own-listing", action="store_true",
                    help="the agent already said the home is their own current listing (a reprice)")
    a = ap.parse_args(argv)
    market = None
    try:
        market = profiles.load_market(state=a.state, county=a.county, mls=a.mls)
        homes = mls.load(a.export, market, mls.columns_arg(a.columns))
        mls.fill_distances(homes, a.address, (a.lat, a.lon) if a.lat and a.lon else None)
        own = [h for h in homes if mls.same_address(h["address"], a.address)]
        subject = {**mls.subject_facts(homes, a.address), "address": a.address, "living_area": a.sqft,
                   "private_pool": a.pool, "subdivision": a.subdivision, **({"property_type": a.type} if a.type else {})}
        out = mls.market_stats(homes, subject, split_date=a.split_date, as_of=a.as_of, limit=a.limit, exclude_address=a.address)
        out["market_notes"] = list(market.notes) + list(homes.notes)
        out["mls"] = market.mls  # CMA-279: copy to report.json's `mls`, so compute.py reads the same MLS
        out["subject_rows"] = [mls._summary(h) for h in own]  # the home's own history: a current listing needs a word with the agent
        # CMA-257: the home's city and county from its own row, when the export has them and none were given
        where = {k: next((str(h[k]).strip() for h in own if str(h.get(k) or "").strip()), None) for k in ("city", "county", "zip")}
        out["subject_location"] = {k: v for k, v in where.items() if v} or None
        if not a.county:
            out["market_notes"].append(
                f"No county given: the export's own row for the home says {', '.join(out['subject_location'].values())}. "
                "Use it (re-run with --county and --state) and say so in your reply." if where["county"] else
                "No county given, and the export has no county for the home: ask the agent for the city and county "
                "(they set the closing costs and taxes); never infer them from subdivision names.")
        # CMA-108: a current listing is a question for the agent before any pricing, never a go-ahead
        listed = [h for h in own if h["status"] in ("ACTIVE", "PENDING")]
        out["listed_now"] = bool(listed)
        if listed:
            h = listed[0]
            out["market_notes"].append(
                f"The home is listed right now ({h['status'].lower()}"
                + (f" at {money(h['current_price'])}" if h.get("current_price") else "")
                + (f", {h['days_on_market']:g} days on market" if h.get("days_on_market") is not None else "")
                + ("). The agent says it's their own listing: confirm, then reprice (set reprice in report.json with "
                   "this price and days on market)." if a.own_listing else
                   "). Confirm whose listing it is before pricing: stop and ask the agent, unless they already said "
                   "it's their own (then re-run with --own-listing). Only their own listing is priced, as a reprice; "
                   "never another brokerage's."))
            out["listed_now_action"] = "reprice" if a.own_listing else "ask"  # CMA-251
        elif own:
            out["market_notes"].append(f"Left out {len(own)} row(s) for the seller's own address (see subject_rows): "
                                       "past sales or listings, not a current one. An expired, withdrawn or canceled "
                                       "listing is a failed price to name in the report.")
        # CMA-277: the home's own listing that ended unsold caps the pricing options (method.md, A Relist): copy to
        # report.json's `relist`. The lowest such price when there are several.
        failed = [h for h in own if h["status"] in ("EXPIRED", "CANCELED", "WITHDRAWN") and h.get("current_price")]
        if failed and not listed:
            h = min(failed, key=lambda h: h["current_price"])
            out["relist"] = {k: v for k, v in {"failed_price": h["current_price"], "status": h["status"].lower(),
                                                "days_on_market": h.get("days_on_market"),
                                                "original_price": h.get("original_list_price")}.items() if v is not None}
            out["market_notes"].append(
                f"The home's earlier listing ended unsold at {money(h['current_price'])} ({h['status'].lower()}): a relist. "
                "No pricing option goes above that price unless the agent gives a reason (method.md, A Relist); set "
                "relist in report.json from this output.")
        # CMA-260: a failed listing with no dates can't be placed in time: say so, and ask rather than guess
        undated = [h for h in own if h["status"] in ("EXPIRED", "CANCELED", "WITHDRAWN")
                   and not any(h.get(k) for k in ("contract_date", "close_date"))]
        out["undated_history"] = [mls._summary(h)["address"] + f" ({h['status'].lower()}"
                                  + (f" at {money(h['current_price'])}" if h.get("current_price") else "") + ")" for h in undated]
        if undated:
            out["market_notes"].append(
                "The export has no dates for the home's earlier " + " and ".join(sorted({h["status"].lower() for h in undated}))
                + " listing. Name it in the report as a failed price without dates, and ask for its dates in your "
                "reply (when it was listed and when it ended; the property report's history shows them). Don't say whether "
                "it came before or after the seller's updates.")
        out["ok"] = True
    except mls.ExportError as e:
        # CMA-268: no MLS given (none assumed without a county), but the headers are a built-in MLS's export
        unmapped = market is not None and not market.get("mls_format.cma_export_columns")
        known = builtin_layout(a.export) if unmapped and not (a.mls or a.columns) else None
        out = {"ok": False, "problems": [
            f"No MLS was given{' for ' + a.county if a.county else ''}, and none is assumed without a county, but this "
            f"export has {known}'s columns. If it's a {known} export, re-run with --mls {known} (and --state and "
            "--county from the listing)." if known else str(e)]}
    except (profiles.ProfileError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
