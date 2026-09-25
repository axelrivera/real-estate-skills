"""Market numbers from an MLS CMA export for pricing a listing (the subject is left out).

    python3 scripts/stats.py export.csv --address "517 HICKORYWOOD AVE" --sqft 1849 [--pool]
        [--subdivision "SPRING OAKS"] [--type single_family] [--lat 28.67 --lon -81.40]
        [--state FL --county Seminole] [--columns columns.json]
        [--split-date 2026-07-01]

The seller's home is treated as a first-time listing: every row with its address (old listings,
prior sales, a current listing) is dropped before anything is counted, and its size, pool and
subdivision come from the seller, not the export. Prints JSON: sold stats for the whole window and
for an earlier and a recent period, inventory and months of supply, the subdivision's median $/sq ft,
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
    a = ap.parse_args(argv)
    try:
        market = profiles.load_market(state=a.state, county=a.county, mls=a.mls)
        homes = mls.load(a.export, market, mls.columns_arg(a.columns))
        mls.fill_distances(homes, a.address, (a.lat, a.lon) if a.lat and a.lon else None)
        own = [h for h in homes if mls.same_address(h["address"], a.address)]
        subject = {**mls.subject_facts(homes, a.address), "address": a.address, "living_area": a.sqft,
                   "private_pool": a.pool, "subdivision": a.subdivision, **({"property_type": a.type} if a.type else {})}
        out = mls.market_stats(homes, subject, split_date=a.split_date, as_of=a.as_of, limit=a.limit, exclude_address=a.address)
        out["market_notes"] = list(market.notes) + list(homes.notes)
        out["subject_rows"] = [mls._summary(h) for h in own]  # the home's own history: a current listing needs a word with the agent
        if own:
            out["market_notes"].append(f"Left out {len(own)} row(s) for the seller's own address (see subject_rows): "
                                       "the report treats the home as a new listing.")
        out["ok"] = True
    except (profiles.ProfileError, mls.ExportError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
