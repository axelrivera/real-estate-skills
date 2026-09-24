"""Show what the skills will know about a market: built-in values, the agent's changes, and gaps.

    python3 scripts/check_market.py --state FL --county Seminole          # built-in only
    python3 scripts/check_market.py market-profile.md [--county Seminole]  # with the agent's profile

Prints JSON: state and MLS, plain-language notes, and for each group of settings the skills use
(closing costs, brokerage, holding and insurance, property tax, contract dates, CMA, MLS files) the values with their source
('profile' = the agent's, 'state'/'mls' = built in, 'county' = county exception) and what's missing.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import dates, finance, profiles  # noqa: E402

# What the skills read, grouped the way the agent thinks about it. A tuple means "any one of these".
GROUPS = {
    "closing costs": [
        "closing_costs.deed_transfer_tax_rate",
        "closing_costs.deed_transfer_tax_payer",
        "closing_costs.owner_title.payer",
        ("closing_costs.owner_title.rate_tiers", "closing_costs.owner_title.quote", "closing_costs.owner_title.estimate_pct"),
        "closing_costs.seller_title_fees",
        "closing_costs.hoa_estoppel_fee",
        "closing_costs.buyer_closing_cost_pct",
    ],
    "brokerage": ["brokerage.listing_fee_pct", "brokerage.buyer_broker_fee_pct"],
    "holding and insurance": ["holding_costs.insurance_rate", "holding_costs.utilities_monthly", "buyer_costs.insurance_rate"],
    "property tax": [
        "property_tax.paid",
        "property_tax.fallback_rate",
        "property_tax.primary_residence_exemptions",
    ],
    "contract dates": [f"contract.{k}" for k in dates.RULE_KEYS],  # the same list contract-timeline requires
    "cma": ["cma.radius_miles", "cma.lookback_months", "cma.adjustments"],
    "mls files": ["mls_format.cma_export_columns", "mls_format.history_codes"],
}


def _entry(market, path):
    value = market.get(path)
    return {"value": value, "source": market.source(path)}


def pct_problems(data, path=""):
    """CORE-11: every `*_pct` is a fraction (0.03 for 3%); a value of 1 or more is a percent written the other way."""
    out = []
    items = data.items() if isinstance(data, dict) else enumerate(data) if isinstance(data, list) else ()
    for k, v in items:
        where = f"{path}.{k}" if path and isinstance(k, str) else f"{path}[{k}]" if path else str(k)
        if isinstance(k, str) and k.endswith("_pct") and not isinstance(v, (dict, list)):
            try:
                finance.fraction(v, where)
            except ValueError as e:
                out.append(str(e))
        else:
            out += pct_problems(v, where)
    return out


def check(path=None, state=None, county=None, mls=None):
    problems = []
    if path:
        with open(path, encoding="utf-8") as f:
            if re.search(r"\{\{[^}]*\}\}", f.read()):
                problems.append("Template placeholders ({{...}}) are still in the file.")
    try:
        market = profiles.load_market(path, state=state, county=county, mls=mls)
    except profiles.ProfileError as e:
        return {"ok": False, "problems": problems + [str(e)]}

    # Settings that don't apply: no transfer tax means nobody pays it; a buyer-paid owner's policy needs no seller rate.
    skip = set()
    if market.get("closing_costs.deed_transfer_tax_rate") == 0:
        skip.add("closing_costs.deed_transfer_tax_payer")
    if market.get("closing_costs.owner_title.payer") == "buyer":
        skip.add(("closing_costs.owner_title.rate_tiers", "closing_costs.owner_title.quote", "closing_costs.owner_title.estimate_pct"))
    groups = {}
    for group, paths in GROUPS.items():
        values, missing = {}, []
        for p in paths:
            if p in skip:
                continue
            options = p if isinstance(p, tuple) else (p,)
            found = next((o for o in options if market.get(o) is not None), None)
            if found:
                values[found] = _entry(market, found)
            else:
                missing.append(" or ".join(options))
        groups[group] = {"complete": not missing, "values": values, "missing": missing}

    millage = market.get("property_tax.millage") or []
    if county:
        key = county.strip().lower().removesuffix(" county")
        millage = [m for m in millage if str(m.get("county", "")).lower() == key]
    # CORE-13: every setting the profile changed, not only the grouped ones (millage, fair housing, forms, county_overrides...)
    changed = sorted(p for p, src in market.sources.items() if src == "profile")
    problems += pct_problems(market.data)
    tiered = finance.transfer_tax_warning(market)  # CORE-19
    notes = market.notes + ([tiered] if tiered else [])
    return {
        "ok": not problems,
        "state": market.state,
        "mls": market.mls,
        "notes": notes,
        "from_profile": changed,
        "groups": groups,
        "millage_districts": [m.get("district") for m in millage],
        "problems": problems,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile", nargs="?", help="the agent's market profile (optional)")
    ap.add_argument("--state")
    ap.add_argument("--county")
    ap.add_argument("--mls")
    a = ap.parse_args(argv)
    result = check(a.profile, a.state, a.county, a.mls)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
