"""Market numbers from an MLS CMA export, for choosing comps and writing the market section.

    python3 scripts/stats.py export.csv --address "517 HICKORYWOOD AVE" [--state FL --county Seminole]
        [--market market-profile.md] [--split-date 2026-07-01]

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
    ap.add_argument("--state")
    ap.add_argument("--county")
    ap.add_argument("--market", help="market profile (MLS column names); Stellar is built in")
    ap.add_argument("--split-date", help="YYYY-MM-DD: sales on or after it are 'recent' (default: 90 days before the last sale)")
    a = ap.parse_args(argv)
    try:
        market = profiles.load_market(a.market, state=a.state, county=a.county)
        homes = mls.load(a.export, market)
        row = next((h for h in homes if mls.same_address(h["address"], a.address)), None)
        subject = {"address": a.address}
        if row:
            subject.update(living_area=row.get("living_area"), private_pool=row["private_pool"], subdivision=row.get("subdivision"))
        out = mls.market_stats(homes, subject, split_date=a.split_date)
        out["subject_row"] = mls._summary(row) if row else None
        out["market_notes"] = market.notes
        if not row:
            out["market_notes"].append("The subject isn't in the export: comp candidates are unranked. Check the address spelling.")
        out["ok"] = True
    except (profiles.ProfileError, mls.ExportError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
