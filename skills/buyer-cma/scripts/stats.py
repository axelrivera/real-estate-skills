"""Market numbers from an MLS CMA export, for choosing comps and writing the market section.

    python3 scripts/stats.py export.csv --address "517 HICKORYWOOD AVE" [--state FL --county Seminole]
        [--columns columns.json] [--split-date 2026-07-01]
        [--sqft 1849 --pool --subdivision "SPRING OAKS" --type single_family --lat 28.67 --lon -81.41]

The subject's facts come from its own row in the export. When it has none (a listing sheet or property report
without an export row), give them as flags so the comp candidates are ranked; a flag also overrides the row.

Prints JSON: the subject's row (when it's in the export), sold stats for the whole window and for an
earlier and a recent period, inventory and months of supply, the subdivision's median $/sq ft,
ranked comp candidates with remarks, and the competition. Numbers only: picking and adjusting comps
is a judgment made from this output.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import mls, profiles  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export")
    ap.add_argument("--address", required=True, help="subject address as it appears in the export")
    ap.add_argument("--sqft", type=float, help="heated living area, when the subject has no row in the export")
    ap.add_argument("--pool", action="store_true", default=None, help="the home has a private pool (no row in the export)")
    ap.add_argument("--subdivision", help="subdivision name as the export writes it")
    ap.add_argument("--type", help="single_family, townhouse, condo, ... (ranks the same type first)")
    ap.add_argument("--lat", type=float, help="the home's latitude, for distances when the export has no Distance column")
    ap.add_argument("--lon", type=float, help="the home's longitude")
    ap.add_argument("--state")
    ap.add_argument("--county")
    ap.add_argument("--columns", help="JSON file (or inline JSON) mapping field names to the export's headers, for an MLS that isn't built in")
    ap.add_argument("--mls", help="MLS name (Stellar is built in; assumed from the county when it's the only one)")
    ap.add_argument("--split-date", help="YYYY-MM-DD: sales on or after it are 'recent' (default: 90 days before the last sale)")
    ap.add_argument("--as-of", help="YYYY-MM-DD the export was pulled (default: the last sale); months of supply runs to it")
    ap.add_argument("--limit", type=int, default=15, help="how many ranked comp candidates to list (default 15)")
    a = ap.parse_args(argv)
    try:
        market = profiles.load_market(state=a.state, county=a.county, mls=a.mls)
        homes = mls.load(a.export, market, mls.columns_arg(a.columns))
        mls.fill_distances(homes, a.address, (a.lat, a.lon) if a.lat and a.lon else None)
        row = next((h for h in homes if mls.same_address(h["address"], a.address)), None)
        subject = {"address": a.address}
        if row:
            subject.update(mls.subject_facts(homes, a.address), living_area=row.get("living_area"),
                           private_pool=row["private_pool"], subdivision=row.get("subdivision"))
        given = {"living_area": a.sqft, "private_pool": a.pool, "subdivision": a.subdivision, "property_type": a.type}
        subject.update({k: v for k, v in given.items() if v is not None})
        if not row and a.pool is None and a.sqft:
            subject["private_pool"] = False  # facts given without --pool: no pool
        out = mls.market_stats(homes, subject, split_date=a.split_date, as_of=a.as_of, limit=a.limit)
        out["subject_row"] = mls._summary(row) if row else None
        out["market_notes"] = market.notes + list(homes.notes)
        if not row and not a.sqft:
            out["market_notes"].append("The subject isn't in the export: comp candidates are unranked. Check the address "
                                       "spelling, or give the home's facts (--sqft, --pool, --subdivision, --lat/--lon).")
        elif not row:
            out["market_notes"].append("The subject isn't in the export: comps are ranked from the facts given.")
        out["ok"] = True
    except (profiles.ProfileError, mls.ExportError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
