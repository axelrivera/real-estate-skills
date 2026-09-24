"""Compute every number in the seller CMA (PDF, deck and chat summary) from report.json.

    python3 scripts/compute.py report.json [--out DIR]

Prints JSON: the net sheet for each pricing strategy (brokerage, transfer tax, title, title company
fees, estoppel, seller credit, optional payoff), a buyer's payment at each list price, the effect of
$10,000 in price, the scatter trend, all formatted for the markdown template, plus `warnings` to fix,
`assumptions` to confirm with the agent, `preliminary` (true when the market is missing a cost) and
the `handoff_block` to end a markdown reply with. Also writes <address>.seller.cma.json (the handoff the
seller-offer-review skill reads). render.py uses the same numbers for the PDF and the deck.
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, handoff, mls, profiles, render  # noqa: E402

# The order finance.seller_net adds its lines in.
NET_LINE_ORDER = ("listing_fee", "buyer_broker_fee", "transfer_tax", "transfer_surtax", "owner_title", "title_fees", "estoppel",
                  "credit", "other", "tax_proration")

PAYOFF_CUSHION = 500  # payoff and recording fees on top of a statement balance (an estimate; the payoff letter governs)
CONTRACT_TO_CLOSE_MONTHS = 1  # a typical financed contract-to-close period, added to each option's time to contract
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
money = finance.money


class ReportError(ValueError):
    """Something report.json needs; the message is written for the agent."""


def _date(v, name):
    """A YYYY-MM-DD date from report.json, or None."""
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ReportError(f"{name} should be a date like 2026-11-20, not {v!r}.") from None


def _require(R, *paths):
    for path in paths:
        node = R
        for part in path.split("."):
            if not isinstance(node, dict) or node.get(part) in (None, ""):
                raise ReportError(f"report.json is missing {path}.")
            node = node[part]


def _frac(block, key, where, default=None):
    """A `*_pct` value from report.json as a fraction (0.025 = 2.5%), or `default` when not given."""
    try:
        return finance.fraction(block.get(key), f"{where}.{key}", default)
    except ValueError as e:
        raise ReportError(str(e)) from e


def pct_text(fraction):
    return f"{fraction * 100:g}"


# --- net sheet ---------------------------------------------------------------

# Plain words for costs the market doesn't have, in a note a homeowner reads (not every state has each one).
MISSING_WORDS = {"deed transfer tax": "transfer tax (or confirmation there is none)", "HOA estoppel fee": "HOA status letter fee",
                 "who pays owner's title": "who customarily pays the owner's title policy", "listing fee": "listing brokerage fee",
                 "buyer's agent fee": "buyer's agent compensation"}


def net_sheet(R, market, L):
    """Seller net for each strategy (at its expected sale price) via finance.seller_net, plus table rows."""
    costs, s = R.get("costs") or {}, R["subject"]
    strategies = R["pricing"]["strategies"]
    lf, bf = _frac(costs, "listing_fee_pct", "costs"), _frac(costs, "buyer_broker_fee_pct", "costs")
    others = costs.get("other") or []
    payoff, payoff_est = costs.get("mortgage_payoff"), False
    if payoff is None and costs.get("mortgage_balance"):  # CMA-29: a balance isn't a payoff; add a month's interest + fees
        payoff = round(costs["mortgage_balance"] * (1 + (costs.get("mortgage_rate") or 7) / 100 / 12) + PAYOFF_CUSHION)
        payoff_est = True
    has_hoa = bool(costs.get("hoa", s.get("hoa", False)))
    title_fees = costs.get("title_fees")  # the title company's quote: a total or {name: amount}
    annual_tax, bill_paid = costs.get("annual_tax"), costs.get("current_tax_bill_paid")
    cols = []
    for x in strategies:
        closing = _date(x.get("closing_date") or costs.get("expected_closing_date"), "expected_closing_date")
        n = finance.seller_net(x["expected_sale"], market, credit=x.get("seller_credit", 0) or 0, payoff=payoff,
                               listing_fee_pct=lf, buyer_broker_fee_pct=bf, has_hoa=has_hoa,
                               other_costs=sum(o["amount"] for o in others), title_fees=title_fees,
                               annual_tax=annual_tax, closing=closing, bill_paid=bill_paid, prop_type=s.get("property_type"))
        cols.append(n)
    first = cols[0]
    assumed_keys = {a["key"] for a in first["assumed"]}

    def label(line):
        key, rate = line["key"], line["rate"]
        if key in ("listing_fee", "buyer_broker_fee"):
            return L(f"net_{key}" + ("_assumed" if key in assumed_keys else ""), pct=pct_text(rate))
        if key == "transfer_tax":
            return line["label"]  # the market's own name and rate ("Documentary stamp tax on the deed (0.70%)")
        if key == "owner_title":
            return L("net_owner_title_est" if rate else "net_owner_title")
        return L(f"net_{key}") if f"net_{key}" in L.text else line["label"]

    # Rows by line key, not position: a line such as the seller credit exists only in the options that have one.
    keys = [k for k in NET_LINE_ORDER if any(l["key"] == k for c in cols for l in c["lines"])]
    keys += [l["key"] for c in cols for l in c["lines"] if l["key"] not in keys and l["key"] not in NET_LINE_ORDER]
    rows = [{"key": "sale", "label": L("net_sale"), "amounts": [x["expected_sale"] for x in strategies]}]
    for key in dict.fromkeys(keys):
        if key == "other":
            for o in others:
                rows.append({"key": "other", "label": o["label"], "amounts": [-o["amount"] for _ in cols]})
            continue
        line = next(l for c in cols for l in c["lines"] if l["key"] == key)
        rows.append({"key": key, "label": label(line),
                     "amounts": [-next((l["amount"] for l in c["lines"] if l["key"] == key), 0) for c in cols]})
    if payoff:
        rows.append({"key": "payoff", "label": L("net_payoff_est" if payoff_est else "net_payoff"), "amounts": [-payoff for _ in cols]})
    totals = [c["net"] if payoff else c["net_before_payoff"] for c in cols]
    rows.append({"key": "total", "label": L("net_total_cash" if payoff else "net_total"), "amounts": totals})
    # CMA-7: a slower option costs more to hold (loan interest, HOA, insurance, utilities; tax is in the proration)
    monthly, left_out = finance.holding_monthly(strategies[0]["list_price"], market, payoff, costs.get("hoa_monthly"))
    months = [x.get("months_to_contract") if x.get("months_to_contract") is not None else finance.months_in(x.get("time"))
              for x in strategies]
    holding = None
    if monthly and all(m is not None for m in months):
        holding = [round(monthly * (m + CONTRACT_TO_CLOSE_MONTHS)) for m in months]
        rows.append({"key": "holding", "label": L("net_holding"), "amounts": [-h for h in holding]})
        rows.append({"key": "after_holding", "label": L("net_after_holding"), "amounts": [t - h for t, h in zip(totals, holding)]})
    for r in rows:
        r["display"] = [money(a) for a in r["amounts"]]

    notes = []
    if holding:
        notes.append(L("net_holding_note", monthly=money(monthly, 10), close=f"{CONTRACT_TO_CLOSE_MONTHS:g}")
                     + (" " + L("net_holding_left_out", items=" and ".join(left_out)) if left_out else ""))
    standard_terms = bool(assumed_keys & {"listing_fee", "buyer_broker_fee"})
    if standard_terms:
        total_pct = sum(l["rate"] for l in first["lines"] if l["key"] in ("listing_fee", "buyer_broker_fee"))
        notes.append(L("net_placeholder_note", pct=pct_text(total_pct)))
    if any(l["key"] in ("listing_fee", "buyer_broker_fee") for c in cols for l in c["lines"]):
        notes.append(finance.COMMISSION_NOTE)
    has_tax = any(l["key"] == "tax_proration" for c in cols for l in c["lines"])
    if not has_tax and market.get("property_tax.paid") == "arrears":
        notes.append(L("net_tax_note"))
    fees = market.get("closing_costs.seller_title_fees")
    if "title_fees" in assumed_keys and market.source("closing_costs.seller_title_fees") != "estimate":
        items = ", ".join(f"{k.replace('_', ' ')} {money(v)}" for k, v in fees.items())
        notes.append(L("net_title_fees_note", items=items))
    estimates = [a["text"] for a in first["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimates:
        notes.append(L("net_estimates_note", items=", ".join(estimates)))
    shown = [MISSING_WORDS.get(m, m) for m in first["missing"]]
    if first["missing"]:
        notes.append(L("net_missing", items=", ".join(shown)))
    return {"columns": [{"net_before_payoff": c["net_before_payoff"], "net": c["net"], "total_costs": c["total_costs"]} for c in cols],
            "totals": totals, "rows": rows, "holding": holding,
            "after_holding": [t - h for t, h in zip(totals, holding)] if holding else None, "notes": notes, "missing": shown, "assumed": first["assumed"],
            "incomplete": bool({"listing fee", "buyer's agent fee"} & set(first["missing"])),
            "payoff": payoff, "cash_at_closing": bool(payoff), "standard_terms": standard_terms, "has_tax": has_tax,
            "warnings": list(dict.fromkeys(w for c in cols for w in c["warnings"]))}


# --- buyer payments ----------------------------------------------------------

def buyer_tax_rates(R, market):
    """(school_mills, total_mills, homestead) for the buyer-payment estimate: explicit mills, or a district lookup."""
    bp = R["buyer_payment"]
    school, total = bp.get("school_mills"), bp.get("total_mills")
    if total is None and bp.get("district"):
        found = finance.millage(market, county=R["subject"].get("county"), district=bp["district"])
        if found:
            school, total = found[0]["school"], found[0]["total"]
    return school, total, bp.get("homestead", True)


def payments(R, market):
    bp = R["buyer_payment"]
    school, total, homestead = buyer_tax_rates(R, market)
    loan_type = finance.program(bp.get("loan_type", "conventional"))
    down = _frac(bp, "down_pct", "buyer_payment", 0.05)
    s = R["subject"]
    zone = bp.get("flood_zone") or next((v for lbl, v in s.get("facts") or [] if str(lbl).lower() == "flood zone"), None)
    flood = finance.flood_insurance(zone, bp.get("flood_insurance_annual"), market,  # CMA-6: a quote, or "get a quote"
                                    _date(R.get("as_of"), "as_of"), condo_unit=finance.property_type(s.get("property_type")) == "condo")

    def at(price):
        tax = finance.property_tax(price, market, school, total, homestead)
        if tax["annual"] is None:
            return None, tax
        return finance.monthly_payment(price, loan_type, down, bp["rate"], tax["annual"], bp["insurance_annual"],
                                       bp.get("hoa_monthly", 0), flood_annual=flood["annual"]), tax

    rows, tax_info = [], None
    for x in R["pricing"]["strategies"]:
        p, tax_info = at(x["list_price"])
        if p is None:
            return None, tax_info
        rows.append({"list_price": x["list_price"], "payment": p["total"], "down": p["cash_down"], "tax_monthly": p["tax"],
                     "list_price_display": money(x["list_price"]), "payment_display": money(p["total"]),
                     "down_display": money(p["cash_down"])})
    rec = R["recommendation"]["list_price"]
    per_10k = at(rec)[0]["total"] - at(rec - 10000)[0]["total"]
    return {"rows": rows, "per_10k": per_10k, "per_10k_display": money(per_10k, 5),
            "down_per_10k": 10000 * down, "down_per_10k_display": money(10000 * down),
            "loan_type": loan_type, "down_pct": down, "rate": bp["rate"],
            "insurance_annual": bp["insurance_annual"], "flood": flood, "school_mills": school, "total_mills": total,
            "homestead": homestead, "tax_basis": tax_info["basis"], "tax_estimated": tax_info["estimated"]}, tax_info


# --- everything ----------------------------------------------------------------

def compute(R, market, homes):
    _require(R, "subject.address", "subject.sqft", "recommendation.list_price", "recommendation.low", "recommendation.high",
             "comps.cards", "pricing.strategies", "buyer_payment.rate", "buyer_payment.insurance_annual")
    L = cma.Labels(ASSETS, R.get("labels"))
    market = market.with_deal(R.get("costs"))  # this listing's own numbers (a title quote, the state's transfer tax)
    s, rec, p = R["subject"], R["recommendation"], R["pricing"]
    strategies = p["strategies"]
    if not 1 <= len(strategies) <= 4:
        raise ReportError("pricing.strategies should have 3 options (top of range, recommended, competing-offer price).")
    for x in strategies:
        for k in ("list_price", "expected_sale"):
            if not isinstance(x.get(k), (int, float)):
                raise ReportError(f"Every pricing strategy needs {k} as a number.")
    ri = p.get("recommended_index", 1)
    if not 0 <= ri < len(strategies):
        raise ReportError("pricing.recommended_index doesn't point at a strategy.")
    if not R["comps"]["cards"]:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    try:
        warnings, assumptions = cma.derive_comps(R["comps"]), []  # adjusted values and summary rows from their parts
    except ValueError as e:
        raise ReportError(str(e)) from e
    median_adjusted = statistics.median(c["adjusted"] for c in R["comps"]["cards"])
    scope = cma.adjustment_scope_warning(market, (R.get("subject") or {}).get("county"), rec["list_price"])  # CMA-10
    if scope:
        warnings.append(scope)
    n = len(R["comps"]["cards"])
    if n < 3:
        warnings.append(f"Only {n} comp{'s' if n > 1 else ''}: the range rests on thin support. Widen the search if you can, "
                        "and say so in the report.")

    if not rec["low"] <= rec["list_price"] <= rec["high"]:
        warnings.append(f"The recommended list price {money(rec['list_price'])} is outside the supported range "
                        f"{money(rec['low'])} – {money(rec['high'])}: move it inside, or widen the range and say why.")
    if strategies[ri]["list_price"] != rec["list_price"]:
        warnings.append("The recommended strategy's list price doesn't match recommendation.list_price.")
    for i, x in enumerate(strategies[:-1] if len(strategies) == 3 else strategies):  # CMA-20
        if x["expected_sale"] > x["list_price"]:  # only the competing-offer option (the last of three) may sell above list
            raise ReportError(f"pricing.strategies[{i}] expects to sell at {money(x['expected_sale'])}, above its "
                              f"{money(x['list_price'])} list price. Only the competing-offer option (the third) can.")
    if rec["low"] > rec["high"]:
        raise ReportError("recommendation.low is above recommendation.high.")
    for x in strategies:
        if x["expected_sale"] > rec["high"]:
            warnings.append(f"The expected sale {money(x['expected_sale'])} is above the supported range: "
                            "an appraisal risk to explain, or lower it.")

    net = net_sheet(R, market, L)
    warnings += net["warnings"]  # CORE-9: a title quote below the published rate
    if net["incomplete"]:
        warnings.append("No brokerage terms: the nets leave out the commission, so they'd overstate what the seller walks away with. "
                        "Ask the agent for the listing fee and buyer's agent compensation (0 is fine) in costs, then re-run. "
                        "render.py won't build the files until then.")
    if net["missing"]:
        warnings.append("Preliminary: the market has no value for " + ", ".join(net["missing"]) +
                        ". Ask the agent and re-run; the report is marked Preliminary until then.")
    brokerage = [a["text"] for a in net["assumed"] if a["key"] in ("listing_fee", "buyer_broker_fee")]
    if brokerage:
        assumptions.append("Brokerage is assumed (" + ", ".join(brokerage) + "), marked on every page and slide that shows "
                           "a net. The agent can give the listing agreement's terms to update it.")
    estimated = [a["text"] for a in net["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimated:
        assumptions.append("National estimates, labeled Estimate on the net sheet: " + ", ".join(estimated) + ". Look up the "
                           "state's transfer tax from an official source (costs.transfer_tax_rate, and transfer_tax_payer if "
                           "the buyer pays or it's split); a title quote (costs.title_fees, title_estimate_pct) replaces the rest.")
    costs_in = R.get("costs") or {}
    if costs_in.get("annual_tax") and not net["has_tax"]:
        warnings.append("costs.annual_tax is set but there's no closing date: add costs.expected_closing_date (or a "
                        "closing_date per pricing option) to include the tax proration.")
    if any(a["key"] == "title_fees" and not a.get("estimate") for a in net["assumed"]):
        assumptions.append("Title company fees are the built-in typical charges; use the title company's quote when there is one.")

    pay, tax_info = payments(R, market)
    if pay is None:
        warnings.append("No millage or tax rate for the buyer-payment estimate: give buyer_payment.school_mills and total_mills "
                        "(or a district in the built-in millage).")
    elif pay["homestead"] and not market.get("property_tax.primary_residence_exemptions"):
        warnings.append("Buyer taxes assume a homestead, but this market has no exemptions on file, so none are applied: "
                        "set buyer_payment.homestead to false and say so, or give the tax with the exemption applied.")
    if pay and pay["tax_estimated"]:
        warnings.append(f"Buyer taxes are estimated at {pay['tax_basis']}; find the millage for the home's taxing district if you can.")

    address = s.get("mls_address", s["address"])
    others = [h for h in homes if not mls.same_address(h["address"], address)]
    fit = mls.trend(others, s["sqft"], (R.get("scatter") or {}).get("fit_size_ratio", 1.6)) if others else None

    stats = {}
    if others:
        st = mls.market_stats(homes, {"address": address, "living_area": s["sqft"], "private_pool": bool(s.get("pool")),
                                      "subdivision": s.get("subdivision")}, split_date=R.get("split_date"),
                              exclude_address=address, as_of=R.get("as_of"))
        recent = st["sold_recent"]
        stats = {k: v for k, v in {
            "split_date": st["window"]["split_date"],
            "sale_to_original_list_recent": recent.get("median_sale_to_original_list"),
            "median_days_recent": recent.get("median_days_on_market"),
            "share_with_seller_paid_costs_recent": recent.get("share_with_seller_paid_costs"),
            "median_seller_paid_recent": recent.get("median_seller_paid_when_paid"),
            "months_supply": st["months_supply_at_recent_pace"],
            "active_count": st["active_count"]}.items() if v is not None}
        window = st["window"]
        n_sold = st["sold_all"]["n"]
        max_dist = max((h["distance"] for h in others if h["status"] == "SOLD" and h.get("distance") is not None), default=None)
    else:
        window, n_sold, max_dist = None, None, None

    preliminary = bool(net["missing"]) or bool(R.get("preliminary"))
    as_of = R.get("as_of") or date.today().isoformat()
    h = handoff.build(
        side="seller", as_of=as_of, source="seller-cma",
        subject={k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                   "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"), "baths": s.get("baths"),
                                   "year_built": s.get("year_built"), "pool": s.get("pool")}.items() if v is not None},
        value={"low": rec["low"], "high": rec["high"], "midpoint": rec.get("midpoint", (rec["low"] + rec["high"]) / 2),
               "median_adjusted": median_adjusted},
        comps=[{"address": r[0], "sold_price": r[1], "seller_paid": r[2], "adjusted": r[3]} for r in R["comps"].get("summary_rows", [])],
        market=stats,
        recommended_list_price=rec["list_price"],
        market_profile={"state": market.state, "mls": market.mls},
    )

    strat_out = []
    for i, x in enumerate(strategies):
        row = {"label": x.get("label") or L("strategy_label", price=money(x["list_price"])),
               "list_price": x["list_price"], "list_price_display": money(x["list_price"]),
               "expected_sale": x["expected_sale"], "expected_sale_display": money(x["expected_sale"]),
               "time": x.get("time", ""), "seller_credit": x.get("seller_credit", 0) or 0,
               "seller_credit_display": money(x.get("seller_credit", 0) or 0), "note": x.get("note", ""),
               "net": net["totals"][i], "net_display": money(net["totals"][i]), "recommended": i == ri,
               "net_after_holding": (net["after_holding"] or net["totals"])[i],
               "net_after_holding_display": money((net["after_holding"] or net["totals"])[i])}
        if pay:
            row.update(payment=pay["rows"][i]["payment"], payment_display=pay["rows"][i]["payment_display"],
                       down=pay["rows"][i]["down"], down_display=pay["rows"][i]["down_display"])
        strat_out.append(row)
    nets = net["after_holding"] or [x["net"] for x in strat_out]  # CMA-7: compare options after holding costs
    data_source = {"mls": market.mls, "as_of": as_of, "export": bool(homes)}
    return {
        "data_source": data_source,
        "ok": True,
        "preliminary": preliminary,
        "subject": {"address": s["address"]},
        "recommendation": {"list_price": rec["list_price"], "list_price_display": money(rec["list_price"]),
                           "low": rec["low"], "high": rec["high"],
                           "range_display": f"{money(rec['low'])} – {money(rec['high'])}",
                           "expected_sale": (R.get("summary_page") or {}).get("expected_sale", "")},
        "median_adjusted": median_adjusted, "median_adjusted_display": money(median_adjusted),
        "adjusted_min": min(c["adjusted"] for c in R["comps"]["cards"]),
        "adjusted_max": max(c["adjusted"] for c in R["comps"]["cards"]),
        "n_comps": len(R["comps"]["cards"]),
        "strategies": strat_out, "recommended_index": ri,
        "recommended_net_display": strat_out[ri]["net_display"],
        "net_spread": max(nets) - min(nets), "net_spread_display": money(max(nets) - min(nets)),
        "net": net,
        "payments": pay,
        "trend": {"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
                  "r2_key": mls.r2_key(fit["r2"])} if fit else None,
        "window": window, "n_sold": n_sold, "max_distance": max_dist,
        "handoff": h,
        "handoff_block": handoff.to_block(h),
        "warnings": warnings,
        "assumptions": assumptions,
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
        path = os.path.join(render.output_dir(a.out), handoff.filename(R["subject"]["address"], "seller"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result["handoff"], f, indent=2)
        result["handoff_file"] = path
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
