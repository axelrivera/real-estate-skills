"""Compute every number in the buyer CMA from report.json and the MLS export.

    python3 scripts/compute.py report.json [--out DIR]

Prints JSON: taxes, payment scenarios, price-vs-credit scenarios, buydown, scatter trend, the
offer plan and range, formatted for the markdown template, plus `warnings` to fix and the
`handoff_block` to end a markdown reply with. Also writes <address>.buyer.cma.json (the CMA handoff the
offer skills read) to the outputs folder. render.py uses the same numbers for the PDF.
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, handoff, mls, profiles, render  # noqa: E402

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
        school, total = j.get("school_mills"), j.get("total_mills")
        if total is None and j.get("district"):
            found = finance.millage(market, county=county, district=j["district"])
            if found:
                school, total = found[0]["school"], found[0]["total"]
        est = finance.property_tax(t["purchase_price"], market, school, total, t.get("homestead", True))
        out.append({"label": j["label"], "short": j.get("short", ""), "school_mills": school, "total_mills": total,
                    "annual": est["annual"], "estimated": est["estimated"], "basis": est["basis"]})
    return out


def payments(R, market, tax_rows):
    pay = R["costs"]["payment"]
    ji = pay.get("tax_jurisdiction_index", 0)
    price = pay["price"]

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
        rows.append({"label": sc["label"], **r, "total_display": money(r["total"]), "cash_down_display": money(r["cash_down"])})
    first = pay["scenarios"][0]
    lower = finance.monthly_payment(price - 10000, first["type"], first["down_pct"], pay["rate"], tax_at(price - 10000),
                                    pay["insurance_annual"], pay.get("hoa_cdd_monthly", 0), flood_annual=flood["annual"])
    alt = None
    if len(tax_rows) == 2 and tax_rows[1 - ji]["annual"] is not None:
        alt = {"short": tax_rows[1 - ji]["short"], "delta_monthly": (tax_at(price, 1 - ji) - tax_at(price)) / 12}
    return {"price": price, "rate": pay["rate"], "insurance_annual": pay["insurance_annual"], "rows": rows, "flood": flood,
            "per_10k": rows[0]["total"] - lower["total"], "alt_jurisdiction": alt, "tax_index": ji}


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


def comp_count_warnings(cards):
    """No comps is an error; fewer than 3 is thin support and a warning."""
    if not cards:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    return [f"Only {len(cards)} comp{'s' if len(cards) > 1 else ''}: the range rests on thin support. Widen the search if you can, "
            "and say so in the report."] if len(cards) < 3 else []


def compute(R, market, homes):
    _require(R, "subject.address", "subject.list_price", "subject.sqft", "bottom_line.low", "bottom_line.high",
             "offer_plan.opening", "offer_plan.walk_away", "comps.cards", "costs.taxes.purchase_price",
             "costs.payment.price", "costs.payment.rate", "costs.payment.insurance_annual")
    market = market.with_deal(R.get("costs"))  # this home's own numbers (the state's transfer tax, a tax rate)
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
    warnings = comp_count_warnings(R["comps"]["cards"])
    try:
        warnings += cma.derive_comps(R["comps"])  # adjusted values and summary rows computed from their parts
    except ValueError as e:
        raise ReportError(str(e)) from e
    for i, r in enumerate((R.get("competition") or {}).get("rows", [])):
        if len(r) < 7 or not all(isinstance(r[j], (int, float)) and not isinstance(r[j], bool) for j in (2, 3)):
            raise ReportError(f"competition.rows[{i}] should be [address, status, price, sqft, pool, days, notes], "
                              "with price and sqft as plain numbers (474500, not \"$474,500\").")
    median_adjusted = statistics.median(c["adjusted"] for c in R["comps"]["cards"])
    scope = cma.adjustment_scope_warning(market, (R.get("subject") or {}).get("county"), s["list_price"])  # CMA-10
    if scope:
        warnings.append(scope)
    tax_rows = taxes(R, market)
    for j in tax_rows:
        if j["annual"] is None:
            warnings.append(f"No millage or tax rate for {j['label']}: add school_mills and total_mills.")
        elif j["estimated"]:
            warnings.append(f"Tax for {j['label']} is estimated at {j['basis']}; find the millage if you can.")
    pay = payments(R, market, tax_rows) if all(j["annual"] is not None for j in tax_rows) else None
    credit = credit_scenarios(R, market, tax_rows, median_adjusted) if pay else None
    for c in (credit or {}).get("columns", []):
        if c["over_cap"]:
            warnings.append(f"The {money(c['credit'])} credit at {money(c['price'])} is over the loan program's limit: fix the scenario.")
        elif c["over_costs"]:
            warnings.append(f"The {money(c['credit'])} credit at {money(c['price'])} exceeds the closing costs: fix the scenario.")
    ca = op.get("credit_alt")
    if ca and credit and not any(c["price"] == ca["price"] and c["credit"] == ca["credit"] for c in credit["columns"]):
        warnings.append("offer_plan.credit_alt doesn't match any price-vs-credit scenario.")
    if op["walk_away"] > bl["high"]:
        warnings.append("The walk-away price is above the supported range: only if the buyer accepts appraisal-gap risk, and say so.")

    fit = mls.trend([h for h in homes if not mls.same_address(h["address"], s.get("mls_address", s["address"]))],
                    s["sqft"], (R.get("scatter") or {}).get("fit_size_ratio", 1.6)) if homes else None

    stats = {}
    if homes:
        st = mls.market_stats(homes, {"address": s.get("mls_address", s["address"]), "living_area": s["sqft"],
                                      "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision")},
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
    h = handoff.build(
        side="buyer", as_of=as_of, source="buyer-cma",
        subject={k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                   "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"), "baths": s.get("baths"),
                                   "year_built": s.get("year_built"), "pool": s.get("pool"), "list_price": s["list_price"]}.items()
                 if v is not None},
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
        "handoff_block": handoff.to_block(h),
        "warnings": warnings,
        "market_notes": market.notes,
    }


def load_inputs(R, mls_name=None):
    """Market and MLS records for a report.json (`export` is the path to the MLS export CSV, `export_columns` its
    header map for an MLS that isn't built in). The MLS is `--mls`, else the report's `mls`, else the one built-in MLS
    covering the county (CMA-15)."""
    s = R.get("subject") or {}
    market = profiles.load_market(state=s.get("state"), county=s.get("county"), mls=mls_name or R.get("mls"))
    homes = mls.load(R["export"], market, R.get("export_columns")) if R.get("export") else []
    return market, homes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--out", help="where to write the .cma.json handoff (default: outputs folder)")
    ap.add_argument("--mls", help="MLS name, as with stats.py (Stellar is built in)")
    a = ap.parse_args(argv)
    with open(a.report, encoding="utf-8") as f:
        R = json.load(f)
    try:
        market, homes = load_inputs(R, a.mls)
        result = compute(R, market, homes)
        path = os.path.join(render.output_dir(a.out), handoff.filename(R["subject"]["address"], "buyer"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result["handoff"], f, indent=2)
        result["handoff_file"] = path
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
