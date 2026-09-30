"""Compute every number in the seller CMA (PDF, deck and chat summary) from report.json.

    python3 scripts/compute.py report.json [--out DIR]

Prints JSON: the net sheet for each pricing strategy (brokerage, transfer tax, title, title company
fees, estoppel, seller credit, optional payoff), a buyer's payment at each list price, the effect of
$10,000 in price, the scatter trend, all formatted for the markdown template, plus `warnings` to fix,
`assumptions` to confirm with the agent, `preliminary` (true when the market is missing a cost). Also writes <address>.seller.cma.json (the handoff the
seller-offer-review skill reads) next to report.json, in the working folder, never the outputs. render.py uses the same numbers for the PDF and the deck.
"""
import argparse
import json
import os
import re
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, handoff, mls, profiles  # noqa: E402

# The order finance.seller_net adds its lines in.
NET_LINE_ORDER = ("listing_fee", "buyer_broker_fee", "transfer_tax", "transfer_surtax", "owner_title", "title_fees", "estoppel",
                  "credit", "other", "tax_proration")

PAYOFF_CUSHION = 500  # payoff and recording fees on top of a statement balance (an estimate; the payoff letter governs)
CONTRACT_TO_CLOSE_MONTHS = 1  # a typical financed contract-to-close period, added to each option's time to contract
TAX_BILL_MONTH = 10  # when a market doesn't say (`property_tax.bill_month`): from October a year's bill may be out
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


# CMA-108: the agent's own current listing, priced again. Its wording, unless report.json's `labels` says otherwise.
# CMA-251: the price it recommends is a new list price, never a first one.
REPRICE_LABELS = {"sum_first": "Before We Reprice", "h_prep": "Before We Reprice", "deck_launch_title": "Relaunch Plan",
                  "sum_rec": "NEW LIST PRICE", "verdict_price": "Reprice to {price}",
                  "verdict_caption": "New List Price · Supported Value Range {low} – {high}",
                  "dot_rec": "New Price {price}", "deck_dot_rec": "New Price {price}", "subject_row": "Your Home (New List Price)",
                  "lg_subject": "{subject}, New List Price", "tip_asking": "new list price", "deck_series_subject": "Your Home, New Price",
                  "h_pricing": "Choosing the New Price", "deck_rec_title": "Our Recommendation: A New Price",
                  "deck_rec_label": "New List Price", "deck_step_rec": "new list price"}


def labels(R):
    """The report's wording: labels.json, the reprice wording when `reprice` is set, then report.json's `labels`."""
    return cma.Labels(ASSETS, {**(REPRICE_LABELS if R.get("reprice") else {}), **(R.get("labels") or {})})


def check_reprice(R, strategies):
    """CMA-108: a reprice names the failed price and its days on market, and keeps staying at that price as an option.
    Returns the index of the Stay at Current Price option, or None when this isn't a reprice."""
    rp = R.get("reprice")
    if not rp:
        return None
    if not isinstance(rp, dict) or not all(isinstance(rp.get(k), (int, float)) for k in ("current_price", "days_on_market")):
        raise ReportError("reprice needs current_price and days_on_market as numbers (the price that hasn't sold and how "
                          "long it has been listed).")
    stay = next((i for i, x in enumerate(strategies) if x["list_price"] == rp["current_price"]), None)
    if stay is None:
        raise ReportError(f"A reprice keeps staying at the current {money(rp['current_price'])} as an option: add a "
                          "\"Stay at Current Price\" strategy at that list price, before the others.")
    # CMA-251: the other options are price cuts. A higher price only when the agent asked for one (`allow_increase`).
    up = [x for x in strategies if x["list_price"] > rp["current_price"]]
    if up and not rp.get("allow_increase"):
        raise ReportError(f"A reprice offers Stay at Current Price and price cuts only: {money(up[0]['list_price'])} is above "
                          f"the current {money(rp['current_price'])}. Replace it with a cut (a top-of-range option doesn't "
                          "apply to a reprice), or set reprice.allow_increase if the agent asked to price it higher.")
    return stay


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


def _and(items):
    """'a', 'a and b', 'a, b and c'."""
    items = [i for i in items if i]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else "".join(items)


def about(amount):
    """CMA-272: a difference rounded for a chat reply, to the nearest $500 under $5,000 and $1,000 above: 'about
    $7,000' for $6,796. The reply quotes it instead of rounding by hand."""
    step = 500 if abs(amount) < 5000 else 1000
    return "about " + money(abs(amount), step)


# --- net sheet ---------------------------------------------------------------

# Plain words for costs the market doesn't have, in a note a homeowner reads (not every state has each one).
MISSING_WORDS = {"deed transfer tax": "transfer tax (or confirmation there is none)", "HOA estoppel fee": "HOA documents fee",
                 "who pays owner's title": "who customarily pays the owner's title policy", "listing fee": "listing brokerage fee",
                 "buyer's agent fee": "buyer's agent compensation"}


def net_sheet(R, market, L):
    """Seller net for each strategy (at its expected sale price) via finance.seller_net, plus table rows."""
    costs, s = R.get("costs") or {}, R["subject"]
    strategies = R["pricing"]["strategies"]
    lf, bf = _frac(costs, "listing_fee_pct", "costs"), _frac(costs, "buyer_broker_fee_pct", "costs")
    others = costs.get("other") or []
    payoff, payoff_est = costs.get("mortgage_payoff"), False
    if payoff is None and costs.get("mortgage_balance") == 0:  # owned free and clear: the net is the cash at closing
        payoff = 0
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
    # CMA-254: one rule for a closing after this year's bill is out: unless the agent says the seller paid it, the bill
    # is assumed unpaid, so the seller's share (Jan 1 to closing) is charged, and the line says it's assumed
    bill_month = market.get("property_tax.bill_month") or TAX_BILL_MONTH
    closings = [_date(x.get("closing_date") or costs.get("expected_closing_date"), "expected_closing_date") for x in strategies]
    tax_assumed = bool(annual_tax) and bill_paid is None and any(c and c.month >= bill_month for c in closings)
    first = cols[0]
    assumed_keys = {a["key"] for a in first["assumed"]}

    def label(line):
        key, rate = line["key"], line["rate"]
        if key in ("listing_fee", "buyer_broker_fee"):
            return L(f"net_{key}" + ("_assumed" if key in assumed_keys else ""), pct=pct_text(rate))
        if key in ("transfer_tax", "estoppel"):  # CMA-109: the market's own name ("HOA Estoppel Letter" in Florida)
            return line["label"]  # the market's own name and rate ("Documentary stamp tax on the deed (0.70%)")
        if key == "owner_title":
            return L("net_owner_title_est" if rate else "net_owner_title")
        if key == "tax_proration" and tax_assumed:
            return L("net_tax_proration_assumed")
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
    cash = payoff is not None  # a payoff, or none to make (0): either way the total is the seller's cash at closing
    totals = [c["net"] if cash else c["net_before_payoff"] for c in cols]
    rows.append({"key": "total", "label": L("net_total_cash" if cash else "net_total"), "amounts": totals})
    # CMA-7: a slower option costs more to hold (loan interest, HOA, insurance, utilities; tax is in the proration)
    # CMA-255: interest at the seller's rate when given, else the planning rate, stated in the note either way
    loan_rate = costs["mortgage_rate"] / 100 if costs.get("mortgage_rate") else finance.PAYOFF_INTEREST
    monthly, left_out = finance.holding_monthly(strategies[0]["list_price"], market, payoff, costs.get("hoa_monthly"), loan_rate)
    months = [x.get("months_to_contract") if x.get("months_to_contract") is not None else finance.months_in(x.get("time"))
              for x in strategies]
    holding = None
    if monthly and all(m is not None for m in months):
        holding = [round(monthly * (m + CONTRACT_TO_CLOSE_MONTHS)) for m in months]
        rows.append({"key": "holding", "label": L("net_holding"), "amounts": [-h for h in holding]})
        rows.append({"key": "after_holding", "label": L("net_after_holding"), "amounts": [t - h for t, h in zip(totals, holding)]})
    for r in rows:
        r["display"] = [money(a) for a in r["amounts"]]

    notes, key_notes = [], []  # key_notes: the ones a slide must still show (the deck keeps the rest for speaker notes)
    has_tax = any(l["key"] == "tax_proration" for c in cols for l in c["lines"])
    if holding:
        # CMA-255: say what the loan interest rests on, and whether property tax is anywhere in the table
        # CMA-266: name only the costs actually counted (no HOA line for a home without one)
        parts = [L(f"net_holding_part_{p}") for p, used in (("hoa", bool(costs.get("hoa_monthly"))),
                                                             ("insurance", "insurance" not in left_out),
                                                             ("utilities", "utilities" not in left_out)) if used]
        if payoff:
            parts.insert(0, L("net_holding_loan_rate" if costs.get("mortgage_rate") else "net_holding_loan_assumed",
                              rate=f"{loan_rate * 100:g}", payoff=money(payoff)))
        loan = _and(parts) + ("" if payoff else "; " + L("net_holding_loan_none" if payoff == 0 else "net_holding_loan_unknown"))
        notes.append(L("net_holding_note", monthly=money(monthly, 10), close=f"{CONTRACT_TO_CLOSE_MONTHS:g}", loan=loan,
                       tax=L("net_holding_tax_in" if has_tax else "net_holding_tax_out"))
                     + (" " + L("net_holding_left_out", items=" and ".join(left_out)) if left_out else ""))
    standard_terms = bool(assumed_keys & {"listing_fee", "buyer_broker_fee"})
    if standard_terms:
        total_pct = sum(l["rate"] for l in first["lines"] if l["key"] in ("listing_fee", "buyer_broker_fee"))
        notes.append(L("net_placeholder_note", pct=pct_text(total_pct)))
        key_notes.append(notes[-1])
    if any(l["key"] in ("listing_fee", "buyer_broker_fee") for c in cols for l in c["lines"]):
        notes.append(finance.COMMISSION_NOTE)
        key_notes.append(notes[-1])
    if not has_tax and market.get("property_tax.paid") == "arrears":
        notes.append(L("net_tax_note"))
    if tax_assumed and has_tax:
        notes.append(L("net_tax_assumed_note"))
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
        key_notes.append(notes[-1])
    return {"columns": [{"net_before_payoff": c["net_before_payoff"], "net": c["net"], "total_costs": c["total_costs"]} for c in cols],
            "totals": totals, "rows": rows, "holding": holding,
            "after_holding": [t - h for t, h in zip(totals, holding)] if holding else None, "notes": notes, "key_notes": key_notes, "missing": shown, "assumed": first["assumed"],
            "incomplete": bool({"listing fee", "buyer's agent fee"} & set(first["missing"])),
            "payoff": payoff, "payoff_estimated": payoff_est, "cash_at_closing": cash,
            "holding_rate_assumed": bool(holding and payoff and not costs.get("mortgage_rate")), "holding_rate": loan_rate, "no_mortgage": payoff == 0, "standard_terms": standard_terms, "has_tax": has_tax,
            "tax_assumed": tax_assumed and has_tax,
            "warnings": list(dict.fromkeys(w for c in cols for w in c["warnings"]))}


# --- buyer payments ----------------------------------------------------------

def buyer_tax_rates(R, market):
    """(school_mills, total_mills, homestead) for the buyer-payment estimate: explicit mills, or a district lookup."""
    bp = R["buyer_payment"]
    school, total = bp.get("school_mills"), bp.get("total_mills")
    if total is None and bp.get("district"):
        row, _ = finance.millage_row(market, R["subject"].get("county"), bp["district"])
        if row:
            school, total = row["school"], row["total"]
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
            "homestead": homestead, "tax_basis": tax_info["basis"], "tax_estimated": tax_info["estimated"],
            # CMA-270: a homestead exemption lowers the tax only where the market has one built in (not Texas yet)
            "homestead_applied": bool(homestead and total is not None
                                      and market.get("property_tax.primary_residence_exemptions"))}, tax_info


# --- placeholders ----------------------------------------------------------------

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholder_values(R, median_display, recommended_net, spread, pay, trend, L):
    """CMA-265: every {name} the report and deck wording may use, filled in every field (not just page 1). The
    chart's two ({trend_at_subject}, {r2_share}) only with an export."""
    rec = R["recommendation"]
    values = {"median_adjusted": median_display, "list_price": money(rec["list_price"]), "low": money(rec["low"]),
              "high": money(rec["high"]), "net_spread": spread, "recommended_net": recommended_net}
    if pay:
        values["per_10k"] = pay["per_10k_display"]
    if trend:
        values.update(trend_at_subject=trend["at_subject_display"], r2_share=L(trend["r2_key"]))
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


def placeholder_warnings(R, values):
    names = ", ".join("{" + k + "}" for k in values)
    return [f"{p} has {name}, which no script fills here, so it would print as typed. Use one of {names}, or write the words."
            for p, name in unfilled_placeholders(R, set(values))]


# --- everything ----------------------------------------------------------------

def _warner():
    """(warnings, keys, warn): warn(key, *texts) adds each text with a stable key, so a test can tell which warning
    fired without matching its sentence (TEST-2); `warning_keys` runs parallel to `warnings`."""
    texts, keys = [], []

    def warn(key, *items):
        texts.extend(items)
        keys.extend([key] * len(items))
    return texts, keys, warn


def compute(R, market, homes):
    _require(R, "subject.address", "subject.sqft", "recommendation.list_price", "recommendation.low", "recommendation.high",
             "comps.cards", "pricing.strategies", "buyer_payment.rate", "buyer_payment.insurance_annual")
    L = labels(R)
    for block in ("costs", "buyer_payment"):  # units before any math: fractions stay fractions, interest stays a percent
        try:
            finance.check_units(R.get(block) or {}, block)
        except ValueError as e:
            raise ReportError(str(e)) from e
    market = market.with_deal(R.get("costs"))  # this listing's own numbers (a title quote, the state's transfer tax)
    s, rec, p = R["subject"], R["recommendation"], R["pricing"]
    strategies = p["strategies"]
    if not 1 <= len(strategies) <= 4:
        raise ReportError("pricing.strategies should have 3 options (top of range, recommended, competing-offer price), "
                          "or for a reprice Stay at Current Price first, then the recommended cut and the competing-offer price.")
    for x in strategies:
        for k in ("list_price", "expected_sale"):
            if not isinstance(x.get(k), (int, float)):
                raise ReportError(f"Every pricing strategy needs {k} as a number.")
    stay = check_reprice(R, strategies)
    ri = p.get("recommended_index", 1)
    if not 0 <= ri < len(strategies):
        raise ReportError("pricing.recommended_index doesn't point at a strategy.")
    if not R["comps"]["cards"]:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    warnings, warning_keys, warn = _warner()
    assumptions = []
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))  # adjusted values and summary rows from their parts
    except ValueError as e:
        raise ReportError(str(e)) from e
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))  # CMA-110
    median_adjusted = statistics.median(c["adjusted"] for c in R["comps"]["cards"])
    scope = cma.adjustment_scope_warning(market, (R.get("subject") or {}).get("county"), rec["list_price"])  # CMA-10
    if scope:
        warn("adjustment_scope", scope)
    n = len(R["comps"]["cards"])
    if n < 3:
        warn("thin_comps", f"Only {n} comp{'s' if n > 1 else ''}: the range rests on thin support. Widen the search if you can, "
                        "and say so in the report.")

    if not rec["low"] <= rec["list_price"] <= rec["high"]:
        warn("list_outside_range", f"The recommended list price {money(rec['list_price'])} is outside the supported range "
                        f"{money(rec['low'])} – {money(rec['high'])}: move it inside, or widen the range and say why.")
    if strategies[ri]["list_price"] != rec["list_price"]:
        warn("list_mismatch", "The recommended strategy's list price doesn't match recommendation.list_price.")
    # the last option is the competing-offer price: of three strategies, or of a reprice's Stay plus two or three cuts
    competing = len(strategies) == 3 if stay is None else len(strategies) >= 3
    for i, x in enumerate(strategies[:-1] if competing else strategies):  # CMA-20
        if x["expected_sale"] > x["list_price"]:  # only the competing-offer option (the last of three) may sell above list
            raise ReportError(f"pricing.strategies[{i}] expects to sell at {money(x['expected_sale'])}, above its "
                              f"{money(x['list_price'])} list price. Only the competing-offer option (the last) can.")
    if rec["low"] > rec["high"]:
        raise ReportError("recommendation.low is above recommendation.high.")
    for x in strategies:
        if x["expected_sale"] > rec["high"]:
            warn("expected_above_range", f"The expected sale {money(x['expected_sale'])} is above the supported range: "
                            "an appraisal risk to explain, or lower it.")

    net = net_sheet(R, market, L)
    warn("title_quote", *net["warnings"])  # CORE-9: a title quote below the published rate
    if net["incomplete"]:
        warn("no_brokerage", "No brokerage terms: the nets leave out the commission, so they'd overstate what the seller walks away with. "
                        "Ask the agent for the listing fee and buyer's agent compensation (0 is fine) in costs, then re-run. "
                        "render.py won't build the files until then.")
    if net["missing"]:
        warn("preliminary", "Preliminary: the market has no value for " + ", ".join(net["missing"]) +
                        ". Ask the agent and re-run; the report is marked Preliminary until then.")
    brokerage = [a["text"] for a in net["assumed"] if a["key"] in ("listing_fee", "buyer_broker_fee")]
    if brokerage:
        assumptions.append("Brokerage is assumed (" + ", ".join(brokerage) + "), marked on every page and slide that shows "
                           "a net. The agent can give the listing agreement's terms to update it.")
    estimated = [a["text"] for a in net["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimated:
        # CMA-109: the transfer tax lookup only when the net used the estimate (never in a no-transfer-tax state)
        lookup = ("Look up the state's transfer tax from an official source (costs.transfer_tax_rate, and transfer_tax_payer "
                  "if the buyer pays or it's split); a title quote (costs.title_fees, title_estimate_pct) replaces the rest."
                  if any(a["key"] == "transfer_tax" and a.get("estimate") for a in net["assumed"]) else
                  "A title quote (costs.title_fees, title_estimate_pct) replaces them.")
        assumptions.append("National estimates, labeled Estimate on the net sheet: " + ", ".join(estimated) + ". " + lookup)
    costs_in = R.get("costs") or {}
    if costs_in.get("annual_tax") and not net["has_tax"]:
        warn("tax_no_closing_date", "costs.annual_tax is set but there's no closing date: add costs.expected_closing_date (or a "
                        "closing_date per pricing option) to include the tax proration.")
    if net["tax_assumed"]:  # CMA-254
        assumptions.append("This year's property tax bill is assumed unpaid at closing, so the net charges the seller's share "
                           "(Jan 1 to closing). If the seller has already paid it, set costs.current_tax_bill_paid to true: the "
                           "buyer then credits back the rest of the year.")
    if any(a["key"] == "title_fees" and not a.get("estimate") for a in net["assumed"]):
        assumptions.append("Title company fees are the built-in typical charges; use the title company's quote when there is one.")
    # CMA-269: the payoff and the holding interest rate are assumptions too, not only lines in the net notes
    if net["payoff"] and net["payoff_estimated"]:
        assumptions.append(f"The mortgage payoff ({money(net['payoff'])}) is estimated from the loan balance, plus a month's "
                           "interest and fees. The lender's payoff statement (costs.mortgage_payoff) replaces it.")
    elif net["payoff"]:
        assumptions.append(f"The mortgage payoff ({money(net['payoff'])}) is the seller's estimate, labeled Your Estimate. "
                           "The lender's payoff statement replaces it.")
    if net["holding_rate_assumed"]:
        assumptions.append(f"Holding costs charge loan interest at an assumed {net['holding_rate'] * 100:g}% a year on the "
                           "payoff. The seller's own rate (costs.mortgage_rate) replaces it.")
    # CMA-268: a state with county rules (Florida: who pays the owner's title policy, the Miami-Dade surtax) needs the county
    if market.get("county_overrides") and not s.get("county"):
        warn("no_county", f"No county for this {market.state} home: closing costs here depend on the county (who pays the "
                          "owner's title policy, surtaxes), so the state's defaults were used. Take subject.county from the "
                          "listing or ask the agent, then re-run.")

    pay, tax_info = payments(R, market)
    bp = R["buyer_payment"]
    if bp.get("total_mills") is None and bp.get("district"):
        problem = finance.millage_row(market, s.get("county"), bp["district"])[1]
        if problem:
            warn("tax_problem", problem)
    if pay is None:
        warn("tax_no_rate", "No millage or tax rate for the buyer-payment estimate: give buyer_payment.school_mills and total_mills "
                        "(or a district in the built-in millage).")
    elif not pay["homestead_applied"] and not pay["tax_estimated"]:
        # CMA-270: the payment note says the taxes assume no homestead exemption; tell the agent why payments may run high
        assumptions.append("Buyer payments assume no homestead exemption" + (
            f": none is built in for {market.state or 'this state'}, so they may run high for a buyer who files one. "
            "The payment note says so; mention it in the reply."
            if pay["homestead"] else " (buyer_payment.homestead is false)."))
    if pay and pay["tax_estimated"]:
        warn("tax_estimated", f"Buyer taxes are estimated at {pay['tax_basis']}; find the millage for the home's taxing district if you can.")

    address = s.get("mls_address", s["address"])
    others = [h for h in homes if not mls.same_address(h["address"], address)]
    fit = mls.trend(others, s["sqft"], (R.get("scatter") or {}).get("fit_size_ratio", 1.6)) if others else None

    stats = {}
    if others:
        st = mls.market_stats(homes, {**mls.subject_facts(homes, address), "address": address, "living_area": s["sqft"],
                                      "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision"),
                                      **({"property_type": s["property_type"]} if s.get("property_type") else {})},
                              split_date=R.get("split_date"),
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
    # CMA-258: the reason comes from the data: costs the market is missing, and/or the reason report.json gives
    own = R.get("preliminary")
    reasons = ([L("prelim_costs", items=", ".join(net["missing"]))] if net["missing"] else []) + (
        [own.strip()] if isinstance(own, str) and own.strip() else [L("prelim_inputs")] if own and not net["missing"] else [])
    preliminary_reason = " ".join(r[0].upper() + r[1:] for r in reasons)
    preliminary_short = L("prelim_short_costs" if net["missing"] else "prelim_short_inputs") if preliminary else ""
    as_of = R.get("as_of") or date.today().isoformat()
    c_in, bp_in = R.get("costs") or {}, R.get("buyer_payment") or {}
    school_m, total_m, homestead = buyer_tax_rates(R, market) if bp_in else (None, None, None)
    hoa_flag = c_in.get("hoa", s.get("hoa"))
    h = handoff.build(
        side="seller", as_of=as_of, source="seller-cma",
        subject={**{k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                      "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"), "baths": s.get("baths"),
                                      "year_built": s.get("year_built"), "pool": s.get("pool")}.items() if v is not None},
                 # CMA-111: the seller's tax bill (the offer review's proration), the buyer-payment millage, flood, HOA, roof
                 **handoff.subject_facts(annual_tax=c_in.get("annual_tax"), school_mills=school_m, total_mills=total_m,
                                         homestead=homestead, hoa_monthly=c_in.get("hoa_monthly", 0 if hoa_flag is False else None),
                                         flood_zone=bp_in.get("flood_zone") or next((v for lbl, v in s.get("facts") or []
                                                                                     if str(lbl).lower() == "flood zone"), None),
                                         roof_year=s.get("roof_year"))},
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
    for x, v in zip(strat_out, nets):  # CMA-272: each option against the recommended one, rounded for the reply
        d = v - nets[ri]
        x["net_vs_recommended"] = d
        x["net_vs_recommended_about"] = "" if x["recommended"] else (
            L("about_same") if abs(d) < 250 else L("about_more" if d > 0 else "about_less", amount=about(d)))
    # CMA-265: an even number of comps has a midpoint median ($468,437.50): shown to the nearest $100
    median_display = money(median_adjusted, 1 if len(R["comps"]["cards"]) % 2 else 100)
    trend = {"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
             "r2_key": mls.r2_key(fit["r2"])} if fit else None
    values = placeholder_values(R, median_display, strat_out[ri]["net_display"], money(max(nets) - min(nets)), pay, trend, L)
    warn("unfilled_placeholder", *placeholder_warnings(R, values))
    data_source = {"mls": market.mls, "as_of": as_of, "export": bool(homes)}
    market_notes = [(n, c) for n, c in zip(market.notes, market.note_codes)
                    if homes or c not in ("mls_assumed", "mls_not_built_in", "mls_not_given")]
    return {
        "data_source": data_source,
        "ok": True,
        "preliminary": preliminary,
        "preliminary_reason": preliminary_reason,
        "preliminary_short": preliminary_short,
        "subject": {"address": s["address"]},
        "recommendation": {"list_price": rec["list_price"], "list_price_display": money(rec["list_price"]),
                           "low": rec["low"], "high": rec["high"],
                           "range_display": f"{money(rec['low'])} – {money(rec['high'])}",
                           "expected_sale": (R.get("summary_page") or {}).get("expected_sale", "")},
        "median_adjusted": median_adjusted, "median_adjusted_display": median_display,
        "adjusted_min": min(c["adjusted"] for c in R["comps"]["cards"]),
        "adjusted_max": max(c["adjusted"] for c in R["comps"]["cards"]),
        "n_comps": len(R["comps"]["cards"]),
        "strategies": strat_out, "recommended_index": ri,
        "reprice": {"current_price": R["reprice"]["current_price"], "current_price_display": money(R["reprice"]["current_price"]),
                    "days_on_market": R["reprice"]["days_on_market"], "stay_index": stay} if stay is not None else None,
        "first_steps_heading": L("sum_first"),  # "Before We List", or "Before We Reprice"
        "recommended_net_display": strat_out[ri]["net_display"],
        "net_spread": max(nets) - min(nets), "net_spread_display": money(max(nets) - min(nets)),
        "net_spread_about": about(max(nets) - min(nets)),  # CMA-272: the reply's rounded figure
        # CMA-264: which net the spread (and the deck's net chart) compares: after holding costs when they're counted
        "net_basis": "after_holding" if net["after_holding"] else "net",
        "net": net,
        "payments": pay,
        "trend": trend,
        "placeholders": values,
        # the chat template's wording, with every {placeholder} filled as the PDF fills it
        "summary_page": cma.fill(R.get("summary_page") or {}, values),
        "recommendation_paragraph": cma.fill(rec.get("paragraph", ""), values),
        "window": window, "n_sold": n_sold, "max_distance": max_dist,
        "handoff": h,
        "comps_table": [{"address": r[0], "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in R["comps"].get("summary_rows", [])],  # the chat template's comp rows
        "warnings": warnings,
        "warning_keys": warning_keys,
        "assumptions": assumptions,
        # CMA-259: without an export nothing reads the MLS, so notes about which MLS (assumed, not built in) are noise
        "market_notes": [n for n, c in market_notes],
        "market_note_keys": [c for n, c in market_notes],
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
        result = compute(R, market, homes)
        path = os.path.join(a.out or os.path.dirname(os.path.abspath(a.report)), handoff.filename(R["subject"]["address"], "seller"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result["handoff"], f, indent=2)
        result["handoff_file"] = path
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
