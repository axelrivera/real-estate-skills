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
from datetime import date, timedelta

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
ADJUSTED_STEP = 100  # CMA-289: adjusted values show to $100 (a comp's odd seller credit gives $433,729); math stays exact
NEAR_RECOMMENDED = 0.01  # CMA-288: a higher option within 1% of the recommended price isn't a distinct strategy


def adjusted_money(v):
    """CMA-289: an adjusted comp value (or the median, span or placeholder built from them) for display: $433,700."""
    return money(v, ADJUSTED_STEP)


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
    if rp.get("original_price") is not None and not isinstance(rp["original_price"], (int, float)):
        raise ReportError("reprice.original_price should be a number: the price the listing started at (the export's "
                          "Original List Price).")
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


FAILED = ("EXPIRED", "CANCELED", "WITHDRAWN")  # a listing that ended without a sale: its price is a failed price


def check_relist(R, strategies, homes, stay):
    """CMA-277: a relist after the home's own listing expired, was canceled or withdrawn. The market has already said no
    at that price, so no option lists above it unless the agent gave a reason (`relist.reason_above`). The failed
    listing is report.json's `relist`, else the lowest-priced failed listing of the home in the export. Returns
    {failed_price, status, days_on_market, source} or None. A reprice has its own rule (check_reprice)."""
    if stay is not None:
        return None
    rl, source = R.get("relist"), "report"
    if rl is not None and not (isinstance(rl, dict) and isinstance(rl.get("failed_price"), (int, float))):
        raise ReportError("relist needs failed_price as a number (the last price of the home's listing that expired, was "
                          "canceled or withdrawn), with optional status and days_on_market.")
    if not rl:
        address = R["subject"].get("mls_address", R["subject"]["address"])
        as_of = mls._as_date(R.get("as_of"), "as_of") or date.today()
        failed = [h for h in homes if h["status"] in FAILED and h.get("current_price")
                  and mls.same_address(h["address"], address) and mls.ended_within(h, as_of)]  # CMA-303
        if not failed:
            return None
        h = min(failed, key=lambda h: h["current_price"])
        rl, source = {"failed_price": h["current_price"], "status": h["status"].lower(),
                      "days_on_market": h.get("days_on_market"), "original_price": h.get("original_list_price")}, "export"
    up = [x for x in strategies if x["list_price"] > rl["failed_price"]]
    if up and not str(rl.get("reason_above") or "").strip():
        raise ReportError(
            f"This home's earlier listing ended unsold at {money(rl['failed_price'])}"
            + (" (from the export)" if source == "export" else "") + f", and {money(up[0]['list_price'])} is above it. "
            "No option lists above a price the market already turned down: cap the top-of-range option at "
            f"{money(rl['failed_price'])} or drop it (method.md, A Relist). If the agent gave a reason to go higher, put "
            "it in relist.reason_above.")
    original = rl.get("original_price") if isinstance(rl.get("original_price"), (int, float)) else own_original(
        R, homes, FAILED, rl["failed_price"])  # CMA-287: the listing's first price, for its price history
    return {"failed_price": rl["failed_price"], "status": rl.get("status"), "days_on_market": rl.get("days_on_market"),
            "original_price": original if original and original > rl["failed_price"] else None, "source": source}


def own_original(R, homes, statuses, price):
    """CMA-287: the Original List Price of the home's own export row with one of `statuses` at `price`, or None."""
    address = R["subject"].get("mls_address", R["subject"]["address"])
    return next((h["original_list_price"] for h in homes if h["status"] in statuses and h.get("current_price") == price
                 and h.get("original_list_price") and mls.same_address(h["address"], address)), None)


def price_history(L, reprice=None, relist=None):
    """CMA-287: the listing's price history in one sentence (first price, the cut, the price now or when it ended, and
    days on market), for the report's Bottom Line and the reply."""
    if reprice:
        cut = reprice.get("original_price")
        return L("history_reprice_cut" if cut else "history_reprice", original=money(cut or 0),
                 current=money(reprice["current_price"]), days=f'{reprice["days_on_market"]:g}')
    after = L("history_after_days", days=f'{relist["days_on_market"]:g}') if relist.get("days_on_market") is not None else ""
    status = str(relist.get("status") or "").lower()
    if status in ("active", "pending"):  # CMA-303: a live listing the agent treats as failed; a pending one went under contract
        key = "history_pending" if status == "pending" else "history_listed"
        return L(key + "_cut" if relist.get("original_price") else key,
                 original=money(relist.get("original_price") or 0), failed=money(relist["failed_price"]), after=after)
    return L("history_relist_cut" if relist.get("original_price") else "history_relist",
             original=money(relist.get("original_price") or 0), failed=money(relist["failed_price"]), after=after)


def stay_expected(R, homes, rp, median_adjusted, split_date):
    """CMA-280: the Stay at Current Price option's expected sale, net of seller-paid costs: the current price times the
    recent sale-to-original-list ratio of sales that sat at least as long as this listing has (the days-on-market
    adjustment; all recent sales when fewer than 3 did), or the median adjusted value if lower. None without an export.
    Returns (value, ratio, n)."""
    address = R["subject"].get("mls_address", R["subject"]["address"])
    split = _date(split_date, "split_date")
    sold = [h for h in homes if h["status"] == "SOLD" and h.get("original_list_price") and h.get("close_price")
            and not mls.same_address(h["address"], address) and (not split or (h.get("close_date") and h["close_date"] >= split))]
    slow = [h for h in sold if (h.get("days_on_market") or 0) >= rp["days_on_market"]]
    pool = slow if len(slow) >= 3 else sold
    if not pool:
        return None, None, 0
    ratio = statistics.median((h["close_price"] - (h.get("seller_paid") or 0)) / h["original_list_price"] for h in pool)
    return min(rp["current_price"] * ratio, median_adjusted), round(ratio, 4), len(pool)


def stay_rule(R, homes, x, median_adjusted, split_date):
    """CMA-280, CMA-300: the Stay option `x`'s expected sale by the rule, with its own seller credit added back (the ratio
    is net of seller-paid costs, and the net sheet takes the credit off), to the nearest $1,000. Returns
    {gross, ratio, n}, or None without an export."""
    value, ratio, n = stay_expected(R, homes, R["reprice"], median_adjusted, split_date)
    if value is None:
        return None
    return {"gross": round((value + (x.get("seller_credit") or 0)) / 1000) * 1000, "ratio": ratio, "n": n}


ASSUMED_SALE_TO_LIST = 0.97  # without an export or market.sale_to_list: a balanced market, after seller-paid costs
EXPECTED_STEP = 500


def fill_expected_sales(R, strategies, stats, stay, competing):
    """Results_v4 case 02: each option's expected sale by one rule, so two runs agree: its list price times the recent
    sale-to-original-list ratio (net of seller-paid costs: stats.py's, else `market.sale_to_list`, else 97% assumed),
    plus its own seller credit (the net sheet takes it off), to the nearest $500. Then capped: never above the list
    price (except the competing-offer option, the last), never above the supported range, and a higher list price
    never expects less than a lower one. An expected_sale in report.json is the agent's figure and is kept. A reprice's
    Stay has its own rule (stay_rule). Fills the strategies in place; returns the basis for the report's note."""
    m = R.get("market") or {}
    if stats.get("sale_to_original_list_recent"):
        ratio, source = stats["sale_to_original_list_recent"], "export"
    elif isinstance(m.get("sale_to_list"), (int, float)) and 0.5 < m["sale_to_list"] <= 1.2:
        ratio, source = m["sale_to_list"], "report"
    else:
        ratio, source = ASSUMED_SALE_TO_LIST, "assumed"
    high, last = R["recommendation"]["high"], len(strategies) - 1
    filled = [i for i, x in enumerate(strategies) if i != stay and x.get("expected_sale") is None]
    agent = [i for i, x in enumerate(strategies) if i != stay and i not in filled]
    capped = False
    for i in filled:
        x = strategies[i]
        v = round((x["list_price"] * ratio + (x.get("seller_credit") or 0)) / EXPECTED_STEP) * EXPECTED_STEP
        cap = min(high, x["list_price"]) if not (competing and i == last) else high
        capped |= v > cap
        x["expected_sale"], x["expected_sale_source"] = min(v, cap), "rule"
    # An option above the recommended price sells near the middle anyway (method.md, the top of the range): it expects
    # the recommended option's sale, and its price costs time and holding costs, not price
    ri = (R.get("pricing") or {}).get("recommended_index", 1)
    top = [i for i in filled if i != ri and strategies[i]["list_price"] > strategies[ri]["list_price"]]
    for i in top:
        strategies[i]["expected_sale"] = min(strategies[i]["expected_sale"], strategies[ri]["expected_sale"])
    floor = 0  # by list price, low to high: a higher price expects at least what a lower one does
    for i in sorted((i for i in range(len(strategies)) if i != stay), key=lambda i: strategies[i]["list_price"]):
        x = strategies[i]
        if i in filled and x["expected_sale"] < floor:
            x["expected_sale"] = min(floor, x["list_price"])
        floor = max(floor, x["expected_sale"])
    for i in agent:
        strategies[i]["expected_sale_source"] = "agent"
    return {"ratio": ratio, "ratio_display": f"{ratio * 100:.1f}%", "source": source, "filled": filled, "agent": agent,
            "capped": capped, "top": top}


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
    """CMA-272: a difference rounded for a chat reply, which quotes it instead of rounding by hand. CMA-318: fine
    enough that it never contradicts the exact figure printed beside it ("within about $3,500" next to $3,678): to
    the nearest $100 under $10,000 ('about $6,800' for $6,796), $500 under $50,000, $1,000 above."""
    step = 100 if abs(amount) < 10000 else 500 if abs(amount) < 50000 else 1000
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
    as_of = _date(R.get("as_of"), "as_of") or date.today()
    closings = [option_closing(R, x, as_of) for x in strategies]  # Results_v4: each option's own closing
    cols, next_year = [], []
    for x, closing in zip(strategies, closings):
        later = bool(closing and closing.year > as_of.year)
        n = finance.seller_net(x["expected_sale"], market, credit=x.get("seller_credit", 0) or 0, payoff=payoff,
                               listing_fee_pct=lf, buyer_broker_fee_pct=bf, has_hoa=has_hoa,
                               other_costs=sum(o["amount"] for o in others), title_fees=title_fees,
                               annual_tax=annual_tax, closing=closing, bill_paid=None if later else bill_paid,
                               prop_type=s.get("property_type"))
        extra = prior_year_bill(annual_tax, market, bill_paid, as_of) if later else 0
        if extra:  # a closing next year: this year's whole bill (assumed unpaid), plus next year's share to closing
            _add_to_line(n, "tax_proration", extra)
            next_year.append(x)
        cols.append(n)
    # CMA-254: one rule for a closing after this year's bill is out: unless the agent says the seller paid it, the bill
    # is assumed unpaid, so the seller's share (Jan 1 to closing) is charged, and the line says it's assumed
    bill_month = market.get("property_tax.bill_month") or TAX_BILL_MONTH
    tax_assumed = bool(annual_tax) and bill_paid is None and (bool(next_year) or any(  # past the due date: assumed paid
        c and c.year == as_of.year and c.month >= bill_month and not finance.tax_bill_assumed_paid(c, market, bill_paid)
        for c in closings))
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
    total_pct = sum(l["rate"] or 0 for l in first["lines"] if l["key"] in ("listing_fee", "buyer_broker_fee"))
    if standard_terms:
        notes.append(L("net_placeholder_note", pct=pct_text(total_pct)))
        key_notes.append(notes[-1])
    if any(l["key"] in ("listing_fee", "buyer_broker_fee") for c in cols for l in c["lines"]):
        notes.append(finance.COMMISSION_NOTE)
        key_notes.append(notes[-1])
    if not has_tax and market.get("property_tax.paid") == "arrears":
        notes.append(L("net_tax_note"))
    if tax_assumed and has_tax:
        notes.append(L("net_tax_assumed_note"))
    if next_year and has_tax:
        notes.append(L("net_tax_next_year_note" + ("" if len(next_year) == 1 else "_many"),
                       options=_and([money(x["list_price"]) for x in next_year]), year=str(as_of.year),
                       next=str(as_of.year + 1)))
    if has_tax and len({c for c in closings if c}) > 1:
        notes.append(L("net_tax_closings_note", dates="; ".join(
            f"{money(x['list_price'])}: {cma.long_date(c.isoformat())}" for x, c in zip(strategies, closings) if c)))
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
            # Results_v4: beside every net when the brokerage is assumed ("5% Brokerage Assumed")
            "assumed_brokerage": L("th_assumed_sub", pct=pct_text(total_pct)) if standard_terms else None,
            "assumed_brokerage_pct": pct_text(total_pct) if standard_terms else None,
            "tax_assumed": tax_assumed and has_tax,
            "closings": [c.isoformat() if c else None for c in closings],
            "warnings": list(dict.fromkeys(w for c in cols for w in c["warnings"]))}


def option_closing(R, x, as_of):
    """Results_v4 case 02: an option's closing date, for its tax proration. Its own `closing_date`; else the later of
    costs.expected_closing_date (the seller's goal) and when its time to contract plus a month to close puts it (a
    slower price can't close by the goal); None with neither."""
    own = _date(x.get("closing_date"), "closing_date")
    if own:
        return own
    target = _date((R.get("costs") or {}).get("expected_closing_date"), "expected_closing_date")
    months = x.get("months_to_contract") if x.get("months_to_contract") is not None else finance.months_in(x.get("time"))
    est = as_of + timedelta(days=round((months + CONTRACT_TO_CLOSE_MONTHS) * 30.44)) if months is not None else None
    return max(d for d in (target, est) if d) if target or est else None


def prior_year_bill(annual_tax, market, bill_paid, as_of):
    """This year's whole tax bill, owed at a closing early next year when it's still unpaid: taxes paid in arrears,
    the agent hasn't said it's paid, and the bill isn't due before the year ends (Florida's run to March). 0 otherwise.
    At the early-payment discount, like the proration."""
    if not annual_tax or bill_paid or market.get("property_tax.paid") == "advance":
        return 0
    if finance.tax_due_date(date(as_of.year, 12, 31), market) is not None:  # due within the year: paid by then
        return 0
    return round(annual_tax * (1 - (market.get("property_tax.early_payment_discount") or 0)))


def _add_to_line(n, key, extra):
    """Add `extra` to the seller_net result's `key` line and its totals."""
    for line in n["lines"]:
        if line["key"] == key:
            line["amount"] += extra
    n["items"] = [(l["label"], l["amount"]) for l in n["lines"]]
    n["total_costs"] += extra
    n["net_before_payoff"] -= extra
    if n["net"] is not None:
        n["net"] -= extra


def state_hint(R, market, L, ri, net):
    """CMA-282: with no state for the home but an MLS built in for exactly one built-in state (Stellar: Florida), what
    that state's costs would change: its transfer tax line against the estimate, and the recommended option's net.
    None otherwise (a known state, no MLS, or an MLS spanning several built-in states)."""
    if market.state or not market.mls:
        return None
    states = [st for st in (market.get("coverage") or {}) if st in profiles._layers("state")]
    if len(states) != 1:
        return None
    other = profiles.load_market(state=states[0], mls=market.mls).with_deal(R.get("costs"))
    alt = net_sheet(R, other, L)
    line = lambda n: next((r["label"] for r in n["rows"] if r["key"] == "transfer_tax"), L("hint_no_transfer_tax"))
    diff = (alt["after_holding"] or alt["totals"])[ri] - (net["after_holding"] or net["totals"])[ri]
    return {"state": states[0], "state_name": profiles.STATES.get(states[0], states[0]), "transfer_tax_label": line(alt),
            "estimate_label": line(net), "net_difference": diff, "net_difference_about": about(diff)}


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


def payment_basis(R, pay, L):
    """CMA-338: what the buyer payments assume (program, down, rate, tax basis, insurance, mortgage insurance), the
    note under the report's payment table without its flood sentence, and the chat template's basis line."""
    bp = R["buyer_payment"]
    mi_rate = finance.annual_mi_rate(pay["loan_type"], pay["down_pct"])  # OFR-25: PMI by down payment
    mi = L("pay_note_mi", mi=f"{mi_rate * 100:g}") if mi_rate and not (pay["loan_type"] == "conventional" and pay["down_pct"] >= 0.20) else ""
    note = bp.get("note") or L("pay_note", program=L("prog_" + pay["loan_type"]), down=f'{pay["down_pct"] * 100:g}', rate=f'{pay["rate"]:.2f}',
                               basis=pay["tax_basis"], ins=money(pay["insurance_annual"]), mi=mi)
    if pay["tax_estimated"]:
        note += " " + L("tax_estimated", basis=pay["tax_basis"])
    elif not pay["homestead_applied"] and not bp.get("note"):  # CMA-270: say the taxes carry no homestead exemption (Texas isn't built in)
        note += " " + L("pay_no_homestead_built_in" if pay["homestead"] else "pay_no_homestead")
    return note


def options_summary(C, L):
    """CMA-336: page 1's options table header for the net column and its footnote, worded as the PDF prints them, for
    the PDF and the chat template alike."""
    net, strats = C["net"], C["strategies"]
    cash, free = net["cash_at_closing"], net["no_mortgage"]
    held = "_holding" if C["net_basis"] == "after_holding" else ""  # CMA-298: nets after holding costs, as the reply quotes them
    note = L(("sum_options_note_free" if free else "sum_options_note_cash" if cash else "sum_options_note") + held)
    co = C.get("competing_offer_caveat")  # CMA-319: the competing-offer option nets more only if those offers show up
    if co is not None:
        note += " " + L("sum_options_note_competing", price=strats[co]["list_price_display"])
    if net["standard_terms"]:  # Results_v4: the assumed brokerage is named beside the nets, not only on the tile
        note += " " + L("sum_options_note_assumed", pct=net["assumed_brokerage_pct"])
    # CMA-317: "cash" names the net sheet's cash-at-closing row; after holding costs the column is a net
    return {"net_header": L("th_est_cash" if cash and not held else "th_est_net"), "note": note,
            "net_header_sub": net["assumed_brokerage"]}


# --- placeholders ----------------------------------------------------------------

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def months_text(months):
    """CMA-320: months of supply as the report reads it, '1.3 months' or '1 month', from stats.py's recent pace."""
    return f"{months:g} month{'' if months == 1 else 's'}"


SUPPLY_WORDS = re.compile(r"\bof (?:\w+ )?(?:supply|inventory)\b", re.I)


def _strings(R, path=""):
    """(path, text) for every string in the report's wording (labels and the export's column map left out)."""
    if isinstance(R, str):
        yield path, R
    elif isinstance(R, list):
        for i, v in enumerate(R):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(R, dict):
        for key, v in R.items():
            if key not in ("labels", "export_columns"):
                yield from _strings(v, f"{path}.{key}" if path else key)


def typed_supply_errors(R, months):
    """CMA-320: wording that states months of supply ("about a month and a half of supply") without
    {months_supply}: a figure typed by hand, not stats.py's. Results_v4: it stops the render, like any typed stat."""
    out = []
    for path, text in _strings(R):
        if SUPPLY_WORDS.search(text) and re.search(r"\bmonths?\b", text, re.I) and "{months_supply}" not in text:
            out.append(f"{path}: states months of supply in its own words → write {{months_supply}} (stats.py's recent "
                       f"pace, {months_text(months)})." if months is not None else
                       f"{path}: states months of supply, but there's no export to compute it from → leave it out.")
    return out


# --- market numbers: typed stats come from the export ------------------------------

# (placeholder stem, period_stats key, how it prints): {sale_to_list_recent} and the rest, from stats.py's periods
MARKET_METRICS = (("sold", "n", lambda v: f"{v:,.0f}"),
                  ("median_price", "median_price", lambda v: money(v)),
                  ("sale_to_list", "median_sale_to_original_list", lambda v: f"{v * 100:.1f}%"),
                  ("days", "median_days_on_market", lambda v: f"{v:.0f}"),
                  ("credit_share", "share_with_seller_paid_costs", lambda v: f"{v * 100:.0f}%"),
                  ("credit_amount", "median_seller_paid_when_paid", lambda v: money(v)))
METRIC_WORDS = {"sold": "number of sales", "median_price": "typical sale price",
                "sale_to_list": "sale-to-original-list ratio (after seller-paid costs)", "days": "typical days to contract",
                "credit_share": "share of sales with seller-paid costs", "credit_amount": "typical seller-paid amount"}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def split_words(window):
    """'July', or 'July 15' for a split mid-month: where the recent period starts."""
    d = date.fromisoformat(window["split_date"])
    return MONTHS[d.month - 1] + ("" if d.day == 1 else f" {d.day}")


def market_numbers(st):
    """({placeholder: display}, {metric: {period: value}}) for the earlier and recent periods, from stats.py's
    market_stats; ({}, {}) without an export."""
    if not st:
        return {}, {}
    values, raw = {}, {}
    # an export with no seller-paid column reads as no credits at all: then the credit numbers are unknown, not 0%
    no_credits = not (st["sold_all"].get("share_with_seller_paid_costs") or 0)
    for stem, key, show in MARKET_METRICS:
        if no_credits and stem in ("credit_share", "credit_amount"):
            continue
        for period, block in (("early", st["sold_early"]), ("recent", st["sold_recent"])):
            v = block.get(key)
            if v is None:
                continue
            values[f"{stem}_{period}"] = show(v)
            raw.setdefault(stem, {})[period] = v * 100 if stem in ("sale_to_list", "credit_share") else v
    values["split_month"] = split_words(st["window"])
    values["window_start_month"] = MONTHS[date.fromisoformat(st["window"]["first_close"]).month - 1]
    return values, raw


def stat_metric(label):
    """Which market number a typed stat's label names ('Sale Price vs. Original Asking Price' → sale_to_list), or
    None (a mortgage rate, the median adjusted value: not a market-period number)."""
    t = str(label).lower()
    if re.search(r"adjust|\bcomps?\b|per sq|/sq|square f|supply|rate\b", t):
        return None
    if re.search(r"\bvs\.?\b|asking|to[- ]list|original", t) and re.search(r"sale|sold|price", t):
        return "sale_to_list"
    if re.search(r"sales with|share|percent|% of", t) and re.search(r"seller|credit|concession|help", t):
        return "credit_share"
    if re.search(r"seller|credit|concession|help", t):
        return "credit_amount"
    if re.search(r"\bdays?\b|time to|under contract", t):
        return "days"
    if re.search(r"price", t):
        return "median_price"
    if re.search(r"homes sold|\bsales\b|\bsold\b", t):
        return "sold"
    return None


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _agrees(metric, typed, value):
    """Whether a typed figure ('95.2%', '$6,500', '28 days') is the export's value as it would be rounded."""
    m = _NUM.search(str(typed))
    if not m:
        return True  # words only ("Up"): nothing typed to check
    n = float(m.group(0).replace(",", ""))
    if metric in ("sale_to_list", "credit_share"):
        return abs(n - value) <= (0.051 if "." in m.group(0) else 0.51)
    if metric == "days":
        return abs(n - value) <= 0.51
    if metric == "sold":
        return abs(n - value) < 0.01
    if metric == "credit_amount":
        return abs(n - value) <= max(250, 0.025 * value)
    return abs(n - value) <= max(1000, 0.005 * value)  # median_price


def typed_stat_errors(R, deck_content, raw, values):
    """Results_v4: a market number typed into key_stats, market.rows or deck.market_stats must be the export's own
    (to its rounding); one that disagrees stops the render, naming the placeholder that fills it. Values already
    written as placeholders agree by construction."""
    if not raw:
        return []
    out = []

    def check(path, label, typed, periods):
        metric = stat_metric(label)
        if not metric or metric not in raw:
            return
        typed = cma.fill(str(typed), values)
        got = {p: raw[metric][p] for p in periods if p in raw[metric]}
        if not got or any(_agrees(metric, typed, v) for v in got.values()):
            return
        p = "recent" if "recent" in got else next(iter(got))
        out.append(f'{path}: "{typed}" isn\'t the export\'s {p} {METRIC_WORDS[metric]} ({values[f"{metric}_{p}"]}) → '
                   f"write {{{metric}_{p}}}, or leave the stat out and the report fills it from the export.")

    for i, st in enumerate((R.get("summary_page") or {}).get("key_stats") or []):
        if isinstance(st, list) and len(st) >= 2:
            check(f"summary_page.key_stats[{i}][0]", st[1], st[0], ("recent", "early"))
    m = R.get("market") or {}
    two = len(m.get("columns") or []) == 3
    for i, r in enumerate(m.get("rows") or []):
        if isinstance(r, list) and len(r) >= 2:
            for j, cell in enumerate(r[1:3], start=1):
                check(f"market.rows[{i}][{j}]", r[0], cell, (("early", "recent")[j - 1],) if two else ("early", "recent"))
    for i, st in enumerate((deck_content or {}).get("market_stats") or []):
        if isinstance(st, list) and len(st) >= 3:
            for j, period in ((1, "early"), (2, "recent")):
                check(f"deck.market_stats[{i}][{j}]", st[0], st[j], (period,))
    return out


MONTH_PHRASE = re.compile(r"\b(before|since|after)\s+(?:early\s+|late\s+|mid-?\s*)?(" + "|".join(MONTHS) + r")\b(?!\s+\d)")
MONTH_FIELDS = ("comps", "market", "means", "summary_page.why", "summary_page.key_stats", "scatter")
SALES_WORDS = re.compile(r"\b(sales?|sold|homes|prices|market|quarter|adjust\w*|closed)\b", re.I)


def split_month_errors(R, values):
    """Results_v4 case 02: "sales from before August" when the recent period starts in July. A market or comp sentence
    that puts a period boundary at a month (a sales word within a few words of "before/since/after <Month>") must use
    the split's month ({split_month}) or the window's first month. "The home has sat since January" isn't one."""
    if "split_month" not in values:
        return []
    allowed = {values["split_month"].split()[0], values["window_start_month"]}
    out = []
    for key in MONTH_FIELDS:
        node = R
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        for path, text in _strings(node, key):
            for m in MONTH_PHRASE.finditer(text):
                near = " ".join(text[:m.start()].split()[-6:] + text[m.end():].split()[:5])
                if m.group(2) not in allowed and SALES_WORDS.search(near):
                    out.append(f'{path}: says "{m.group(0)}", but the recent period starts {values["split_month"]} → '
                               f'write "{m.group(1)} {{split_month}}" (filled as "{values["split_month"]}").')
    return out


GENERIC_WORDS = {"home", "house", "list", "listing", "launch", "price", "ready", "plan", "step", "steps", "your", "with",
                 "from", "that", "this", "before", "after", "week", "weeks", "make", "keep", "time", "early", "first"}


def _words(text):
    return {w for w in re.findall(r"[a-z]+", re.sub(r"<[^>]+>", " ", str(text).lower())) if len(w) >= 4} - GENERIC_WORDS


def _same_word(a, b):
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short) or a[:5] == b[:5]


def launch_plan_errors(R, deck_content):
    """Results_v4 case 02: a launch-plan card the agent never gave ("Easy Showings: lockbox access"). Each card's
    heading must name one of the report's Before We List steps (prep.items' bold leads, or page 1's first steps)."""
    plan = (deck_content or {}).get("launch_plan") or []
    leads = [re.search(r"<strong>(.*?)</strong>", str(i)) for i in (R.get("prep") or {}).get("items") or []]
    sources = [_words(m.group(1)) for m in leads if m]
    sources += [_words(s[0]) for s in (R.get("summary_page") or {}).get("first_steps") or [] if isinstance(s, list) and s]
    if not plan or not sources:
        return []
    out = []
    for i, item in enumerate(plan):
        heading = item[0] if isinstance(item, list) and item else ""
        words = _words(heading)
        if words and not any(_same_word(a, b) for src in sources for a in words for b in src):
            out.append(f'deck.launch_plan[{i}]: "{heading}" isn\'t one of the report\'s Before We List steps → use a step '
                       "from prep.items (its bold lead), or add it there first if the agent asked for it.")
    return out


# --- listing history ----------------------------------------------------------------

HISTORY_STATUSES = {"expired": "expired", "withdrawn": "withdrawn", "canceled": "canceled", "cancelled": "canceled"}


def _when(value):
    """'March 2017' from 2017-03-15 or 2017-03, '2017' from 2017; None when there's none."""
    v = str(value or "").strip()
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", v)
    if not m:
        return None
    return f"{MONTHS[int(m.group(2)) - 1]} {m.group(1)}" if m.group(2) and 1 <= int(m.group(2)) <= 12 else m.group(1)


def listing_history(R, homes, relist, L):
    """Results_v4 case 02: the home's own listings that ended unsold (expired, withdrawn, canceled), however long ago,
    each with its price, first price and date, for page 1, the deck and the reply. report.json's `listing_history`
    (from the property report), else the export's own rows, plus a relist's failed listing. Returns (events, errors)."""
    given, errors, events = R.get("listing_history"), [], []
    if given is not None and not isinstance(given, list):
        return [], ["listing_history: should be a list of {status, price, original_price, ended, days_on_market} → "
                    "one item per listing that ended unsold."]
    for i, e in enumerate(given or []):
        status = HISTORY_STATUSES.get(str((e or {}).get("status", "")).lower()) if isinstance(e, dict) else None
        if not status or not isinstance(e.get("price"), (int, float)):
            errors.append(f"listing_history[{i}]: needs status (expired, withdrawn or canceled) and price as a number → "
                          "take them from the property report's history.")
            continue
        events.append({"status": status, "price": e["price"], "original_price": e.get("original_price"),
                       "when": _when(e.get("ended") or e.get("listed")), "days": e.get("days_on_market")})
    if given is None:
        address = R["subject"].get("mls_address", R["subject"]["address"])
        for h in homes:
            if h["status"] in FAILED and h.get("current_price") and mls.same_address(h["address"], address):
                d = h.get("close_date") or h.get("contract_date")
                events.append({"status": h["status"].lower(), "price": h["current_price"],
                               "original_price": h.get("original_list_price"), "when": _when(d.isoformat() if d else None),
                               "days": h.get("days_on_market")})
    if relist and str(relist.get("status") or "expired").lower() in HISTORY_STATUSES \
            and not any(e["price"] == relist["failed_price"] for e in events):
        events.append({"status": HISTORY_STATUSES[str(relist.get("status") or "expired").lower()],
                       "price": relist["failed_price"], "original_price": relist.get("original_price"), "when": None,
                       "days": relist.get("days_on_market")})
    for e in events:
        first = e["original_price"] if isinstance(e["original_price"], (int, float)) and e["original_price"] > e["price"] else None
        e["text"] = (L("hist_" + e["status"]) + (L("hist_in", when=e["when"]) if e["when"] else "")
                     + (L("hist_after", days=f'{e["days"]:g}') if isinstance(e["days"], (int, float)) else "")
                     + L("hist_at", price=money(e["price"])) + (L("hist_first", price=money(first)) if first else "")
                     + ("" if e["when"] else L("hist_undated")) + ".")
        e["price_display"], e["original_price_display"] = money(e["price"]), money(first) if first else None
    return events, errors


def placeholder_values(R, median_display, recommended_net, spread, spread_about, pay, trend, L, relist=None, reprice=None,
                       months_supply=None):
    """CMA-265: every {name} the report and deck wording may use, filled in every field (not just page 1). The
    chart's two ({trend_at_subject}, {r2_share}) only with an export. CMA-278: the rounded spread, the adjusted span,
    a reprice's {current_price} and a relist's {failed_price}, each only when there is one. CMA-287: {original_price},
    the price a reprice's or relist's listing started at, when it was cut since. CMA-289: adjusted values to $100."""
    rec, cards = R["recommendation"], R["comps"]["cards"]
    values = {"median_adjusted": median_display, "list_price": money(rec["list_price"]), "low": money(rec["low"]),
              "high": money(rec["high"]), "net_spread": spread, "net_spread_about": spread_about,
              "recommended_net": recommended_net, "adjusted_min": adjusted_money(min(c["adjusted"] for c in cards)),
              "adjusted_max": adjusted_money(max(c["adjusted"] for c in cards))}
    if pay:
        values["per_10k"] = pay["per_10k_display"]
    if months_supply is not None:  # CMA-320: with an export
        values["months_supply"] = months_text(months_supply)
    if trend:
        values.update(trend_at_subject=trend["at_subject_display"], r2_share=L(trend["r2_key"]))
    if R.get("reprice"):
        values["current_price"] = money(R["reprice"]["current_price"])
    if relist:
        values["failed_price"] = money(relist["failed_price"])
    original = (reprice or {}).get("original_price") or (relist or {}).get("original_price")
    if original:
        values["original_price"] = money(original)
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


DOLLARS = re.compile(r"\$\s?(\d[\d,]*)(?:\.\d+)?\s*([kK]\b)?")


def deck_content(R):
    """report.json's `deck` wording (an object, or a path to a JSON file), or None (render.py names a missing or
    broken deck file)."""
    content = R.get("deck")
    if isinstance(content, str):
        try:
            with open(content, encoding="utf-8") as f:
                content = json.load(f)
        except (OSError, ValueError):
            return None
    return content if isinstance(content, dict) else None


def expected_basis(basis, strategies, values, L):
    """Results_v4: the sentence under the pricing table that says where each expected sale comes from, naming any
    option whose figure is the agent's own."""
    parts = []
    if basis["filled"]:
        key = {"export": "expected_basis_export", "report": "expected_basis_report"}.get(basis["source"], "expected_basis_assumed")
        parts.append(L(key, ratio=basis["ratio_display"], since=values.get("split_month", ""))
                     + (L("expected_basis_capped") if basis["capped"] else "") + ".")
        if basis["top"]:  # a higher price buys time on the market, not a higher sale
            parts.append(L("expected_basis_top", prices=_and([money(strategies[i]["list_price"]) for i in basis["top"]])))
    if basis["agent"]:
        prices = _and([money(strategies[i]["list_price"]) for i in basis["agent"]])
        parts.append(L("expected_basis_agent" if len(basis["agent"]) == 1 else "expected_basis_agent_many", prices=prices))
    return " ".join(parts)


def page_one_stats(R, values, median_display, L, n, lo, hi):
    """Page 1's three key stats: report.json's (placeholders filled), else from the export (the median adjusted value,
    the recent sale-to-list ratio, days to contract now), else from the comps (CMA-261). Never typed figures."""
    given = [list(x) for x in cma.fill((R.get("summary_page") or {}).get("key_stats") or [], values)][:3]
    if "sale_to_list_recent" in values and "days_recent" in values:
        auto = [[median_display, L("sum_stat_median", n=n)],
                [values["sale_to_list_recent"], L("sum_stat_ratio", since=values["split_month"])],
                [L("sum_stat_days_value", days=values["days_recent"]), L("sum_stat_days", since=values["split_month"])]]
    else:
        auto = [[median_display, L("sum_stat_median", n=n)], [f"{cma.k(lo)}–{cma.k(hi)}", L("sum_stat_span")],
                [str(n), L("sum_stat_comps")]]
    return given + [a for a in auto if a[1] not in {g[1] for g in given if len(g) > 1}][:3 - len(given)]


MARKET_ROWS = ("sold", "median_price", "sale_to_list", "days", "credit_share", "credit_amount")


def market_rows(R, numbers, window, L):
    """The market table: report.json's `market.columns` and `rows` (placeholders filled) when given, else built from
    the export's two periods (Results_v4: never typed). None without either."""
    m = R.get("market") or {}
    if m.get("rows"):
        return {"columns": cma.fill(m.get("columns") or [], numbers), "rows": cma.fill(m["rows"], numbers)}
    if not numbers or not window:
        return None
    rows = [[L("mk_" + stem), numbers.get(f"{stem}_early", "—"), numbers.get(f"{stem}_recent", "—")]
            for stem in MARKET_ROWS if f"{stem}_recent" in numbers]
    return {"columns": [""] + period_labels(window), "rows": rows}


def period_labels(window):
    """CMA-25: labels from the actual bounds. A split on the 1st reads as whole months ("April–June", "July–September");
    a mid-month split shows the day, so no days are dropped ("April–July 14", "July 15–September")."""
    split = date.fromisoformat(window["split_date"])
    before = split - timedelta(days=1)
    y = window["first_close"][:4] != window["last_close"][:4]  # across New Year: name the years
    month = lambda iso: (lambda d: MONTHS[d.month - 1] + (f" {d.year}" if y else ""))(date.fromisoformat(iso))
    first, last = month(window["first_close"]), month(window["last_close"])
    if split.day == 1:
        b, a = MONTHS[before.month - 1] + (f" {before.year}" if y else ""), MONTHS[split.month - 1] + (f" {split.year}" if y else "")
    else:
        b = f"{MONTHS[before.month - 1]} {before.day}" + (f", {before.year}" if y else "")
        a = f"{MONTHS[split.month - 1]} {split.day}" + (f", {split.year}" if y else "")
    return [f"{first}–{b}", f"{a}–{last}"]


def driver_amount_warnings(R):
    """CMA-284: a dollar figure in a deck value driver ("worth about $25,000") must be one of the report's comp
    adjustments (to within 2% or $500), or nothing in the report supports it."""
    content = deck_content(R)
    if not content:
        return []
    amounts = [abs(a["amount"]) for c in R["comps"]["cards"] for a in c.get("adjustments") or []
               if isinstance(a, dict) and isinstance(a.get("amount"), (int, float)) and a["amount"]]
    out = []
    for i, item in enumerate(content.get("value_drivers") or []):
        for text in (item[:2] if isinstance(item, list) else []):
            for m in DOLLARS.finditer(str(text)):
                v = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
                if not any(abs(v - a) <= max(500, 0.02 * a) for a in amounts):
                    out.append(f"$.deck.value_drivers[{i}] says {m.group(0).strip()}, but no comp adjustment in the report is "
                               "that amount. A value driver's dollar figure must come from a comp adjustment (deck-content.md): "
                               "use that amount, or say what the feature does without a number.")
    return out


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
             "comps.cards", "pricing.strategies", "buyer_payment.rate")
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
        if not isinstance(x.get("list_price"), (int, float)):
            raise ReportError("Every pricing strategy needs list_price as a number.")
    stay = check_reprice(R, strategies)
    for i, x in enumerate(strategies):  # Results_v4: expected_sale is the script's unless the agent gave one
        if x.get("expected_sale_source") in ("rule", "stay_rule"):  # filled by an earlier run on this same data
            x.pop("expected_sale", None)
        if x.get("expected_sale") is not None and not isinstance(x["expected_sale"], (int, float)):
            raise ReportError(f"pricing.strategies[{i}].expected_sale: {x['expected_sale']!r} isn't a number → give the "
                              "agent's figure as a plain number, or leave it out and compute.py fills it by the rule.")
    relist = check_relist(R, strategies, homes, stay)  # CMA-277
    ri = p.get("recommended_index", 1)
    if not 0 <= ri < len(strategies):
        raise ReportError("pricing.recommended_index doesn't point at a strategy.")
    if not R["comps"]["cards"]:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    warnings, warning_keys, warn = _warner()
    assumptions, assumption_keys, assume = _warner()  # CMA-286: keyed like the warnings
    bp = R["buyer_payment"]
    if bp.get("insurance_annual") in (None, ""):  # the shared estimate at the recommended price, labeled an estimate
        bp["insurance_annual"] = finance.insurance_estimate(rec["list_price"], market, s.get("year_built"))["annual"]
        assume("insurance_estimated", f"Buyer payments use an estimated {money(bp['insurance_annual'])} a year for "
               "homeowner's insurance (the market's rate for this price and the home's age); give a quote if the seller has one.")
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))  # adjusted values and summary rows from their parts
    except ValueError as e:
        raise ReportError(str(e)) from e
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))  # CMA-110
    median_adjusted = statistics.median(c["adjusted"] for c in R["comps"]["cards"])
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
        window, n_sold, max_dist, st = None, None, None, None
    errors = cma.adjustment_kind_errors(R["comps"]["cards"])  # Results_v4: data the model wrote that's wrong stops the render
    # CMA-300: Stay at Current Price's expected sale by the one rule (method.md, A Reprice). Left out of report.json, it's
    # filled from the rule, so the first run never guesses it
    rule = stay_rule(R, homes, strategies[stay], median_adjusted, (window or {}).get("split_date")) if stay is not None else None
    stay_filled = stay is not None and strategies[stay].get("expected_sale") is None
    if stay_filled:
        if not rule:
            raise ReportError("Stay at Current Price needs expected_sale as a number: without an MLS export there are no sales "
                              "to apply the rule to, so apply it to the sales you were given (method.md, A Reprice).")
        strategies[stay]["expected_sale"] = rule["gross"]
        strategies[stay]["expected_sale_source"] = "stay_rule"
    if rec["low"] > rec["high"]:
        raise ReportError("recommendation.low is above recommendation.high.")
    # the last option is the competing-offer price: of three strategies, or of a reprice's Stay plus two or three cuts
    # CMA-288: or of two, once a relist drops the top option: the last one when it's below the recommended one
    competing = len(strategies) - 1 != ri and strategies[-1]["list_price"] < strategies[ri]["list_price"]
    basis = fill_expected_sales(R, strategies, stats, stay, competing)  # Results_v4: the rule, not a typed guess
    if ri in basis["filled"] and strategies[ri]["expected_sale"] < rec["low"]:
        assume("expected_below_range", f"The recommended option's expected sale ({money(strategies[ri]['expected_sale'])}) is "
               f"below the supported range ({money(rec['low'])} – {money(rec['high'])}): it's the list price times the "
               f"recent {basis['ratio_display']} sale-to-original-list ratio, which includes overpriced listings. Say so in "
               "the reply; if the agent expects more, their own figure goes in that option's expected_sale.")
    if basis["source"] == "assumed" and basis["filled"]:
        assume("expected_sale_ratio", f"Expected sales assume {basis['ratio_display']} of list after seller-paid costs "
               "(no MLS export to measure it from). The recent sale-to-original-list ratio of the sales reviewed "
               "(market.sale_to_list, a fraction) replaces it.")

    scope =cma.adjustment_scope_warning(market, (R.get("subject") or {}).get("county"), rec["list_price"])  # CMA-10
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
    for i, x in enumerate(strategies[:-1] if competing else strategies):  # CMA-20
        if x["expected_sale"] > x["list_price"]:  # only the competing-offer option (the last of three) may sell above list
            raise ReportError(f"pricing.strategies[{i}] expects to sell at {money(x['expected_sale'])}, above its "
                              f"{money(x['list_price'])} list price. Only the competing-offer option (the last) can.")
    for x in strategies:
        if x["expected_sale"] > rec["high"]:
            warn("expected_above_range", f"The expected sale {money(x['expected_sale'])} is above the supported range: "
                            "an appraisal risk to explain, or lower it.")
    # CMA-323: a higher list price expected to sell below a lower one's reads as a mistake to a seller. A reprice's Stay
    # (the rule's figure for a listing that sat) and a competing-offer option that rests on those offers are exempt
    for i, hi in enumerate(strategies):
        for j, lo in enumerate(strategies):
            if (stay not in (i, j) and hi["list_price"] > lo["list_price"] and hi["expected_sale"] < lo["expected_sale"]
                    and not (competing and j == len(strategies) - 1 and p.get("competing_offer_upside"))):
                warn("expected_sale_order", f"The {money(hi['list_price'])} option expects {money(hi['expected_sale'])}, "
                     f"below the {money(lo['list_price'])} option's {money(lo['expected_sale'])}. A higher list price "
                     f"sells at least as high, only slower: give it at least {money(lo['expected_sale'])} (its longer time "
                     "and holding costs already make it net less).")
    for key, text in cma.range_warnings(rec, [c["adjusted"] for c in R["comps"]["cards"]], market):  # CMA-296, as buyer-cma
        warn(key, text)

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
    if brokerage and stay is not None:
        # CMA-286: the agent's own listing already has a listing agreement: its commission replaces the assumption
        assume("brokerage_listing_agreement",
               "Brokerage is assumed (" + ", ".join(brokerage) + "), labeled Assumed on every net. This is the agent's own "
               "listing, so the listing agreement already sets the commission: ask for it in the reply (costs.listing_fee_pct "
               "and buyer_broker_fee_pct) and re-run.")
    elif brokerage:
        assume("brokerage_assumed", "Brokerage is assumed (" + ", ".join(brokerage) + "), marked on every page and slide "
               "that shows a net. The agent can give the listing agreement's terms to update it.")
    estimated = [a["text"] for a in net["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimated:
        # CMA-109: the transfer tax lookup only when the net used the estimate (never in a no-transfer-tax state)
        lookup = ("Look up the state's transfer tax from an official source (costs.transfer_tax_rate, and transfer_tax_payer "
                  "if the buyer pays or it's split); a title quote (costs.title_fees, title_estimate_pct) replaces the rest."
                  if any(a["key"] == "transfer_tax" and a.get("estimate") for a in net["assumed"]) else
                  "A title quote (costs.title_fees, title_estimate_pct) replaces them.")
        assume("estimates", "National estimates, labeled Estimate on the net sheet: " + ", ".join(estimated) + ". " + lookup)
    costs_in = R.get("costs") or {}
    if costs_in.get("annual_tax") and not net["has_tax"]:
        warn("tax_no_closing_date", "costs.annual_tax is set but there's no closing date: add costs.expected_closing_date (or a "
                        "closing_date per pricing option) to include the tax proration.")
    if net["tax_assumed"]:  # CMA-254
        assume("tax_bill_unpaid", "This year's property tax bill is assumed unpaid at closing, so the net charges the seller's share "
               "(Jan 1 to closing). If the seller has already paid it, set costs.current_tax_bill_paid to true: the "
               "buyer then credits back the rest of the year.")
    if any(a["key"] == "title_fees" and not a.get("estimate") for a in net["assumed"]):
        assume("title_fees_built_in", "Title company fees are the built-in typical charges; use the title company's quote when there is one.")
    # CMA-269: the payoff and the holding interest rate are assumptions too, not only lines in the net notes
    if net["payoff"] and net["payoff_estimated"]:
        assume("payoff_estimated", f"The mortgage payoff ({money(net['payoff'])}) is estimated from the loan balance, plus a "
               "month's interest and fees. The lender's payoff statement (costs.mortgage_payoff) replaces it.")
    elif net["payoff"]:
        assume("payoff_seller", f"The mortgage payoff ({money(net['payoff'])}) is the seller's estimate, labeled Your "
               "Estimate. The lender's payoff statement replaces it.")
    if net["holding_rate_assumed"]:
        assume("holding_rate", f"Holding costs charge loan interest at an assumed {net['holding_rate'] * 100:g}% a year on "
               "the payoff. The seller's own rate (costs.mortgage_rate) replaces it.")
    # CMA-268: a state with county rules (Florida: who pays the owner's title policy, the Miami-Dade surtax) needs the county
    if market.get("county_overrides") and not s.get("county"):
        warn("no_county", f"No county for this {market.state} home: closing costs here depend on the county (who pays the "
                          "owner's title policy, surtaxes), so the state's defaults were used. Take subject.county from the "
                          "listing or ask the agent, then re-run.")
    # CMA-282: no state, but the MLS is built in for one: the nets stay on national estimates (Preliminary), and the
    # reply says what that state's costs would change, so the agent sees why the county matters
    hint = state_hint(R, market, L, ri, net)
    if hint:
        assume("state_unknown", f"No state or county for this home, so the nets use national estimates and the report is "
               f"Preliminary. The export is {market.mls} MLS, built in for {hint['state_name']}: if this is "
               f"{hint['state_name']}, the net sheet uses {hint['transfer_tax_label']} instead of {hint['estimate_label']}, "
               f"and the recommended option nets {hint['net_difference_about']} {'more' if hint['net_difference'] > 0 else 'less'}. "
               "Say so in the reply and ask for the city and county.")

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
        assume("no_homestead", "Buyer payments assume no homestead exemption" + (
            f": none is built in for {market.state or 'this state'}, so they may run high for a buyer who files one. "
            "The payment note says so; mention it in the reply."
            if pay["homestead"] else " (buyer_payment.homestead is false)."))
    if pay and pay["tax_estimated"]:
        warn("tax_estimated", f"Buyer taxes are estimated at {pay['tax_basis']}; find the millage for the home's taxing district if you can.")

    no_state = not market.state  # CMA-282: costs are national estimates until the state and county are known
    preliminary = bool(net["missing"]) or bool(R.get("preliminary")) or no_state
    # CMA-258: the reason comes from the data: costs the market is missing, and/or the reason report.json gives
    own = R.get("preliminary")
    reasons = ([L("prelim_no_state")] if no_state else []) + (
        [L("prelim_costs", items=", ".join(net["missing"]))] if net["missing"] else []) + (
        [own.strip()] if isinstance(own, str) and own.strip() else
        [L("prelim_inputs")] if own and not net["missing"] and not no_state else [])
    preliminary_reason = " ".join(r[0].upper() + r[1:] for r in reasons)
    preliminary_short = L("prelim_short_no_state" if no_state else "prelim_short_costs" if net["missing"]
                          else "prelim_short_inputs") if preliminary else ""
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
               "expected_sale_source": x.get("expected_sale_source"),  # rule, agent, or a reprice's stay_rule
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
    # CMA-280: a slower, higher option shouldn't come out ahead of the recommended one on its own assumptions
    for i, x in enumerate(strat_out):
        if i == ri or nets[i] <= nets[ri]:
            continue
        if i == stay:
            warn("stay_nets_more", f"Stay at Current Price nets {about(nets[i] - nets[ri])} more than the recommended cut after "
                 "holding costs. Check its expected sale against reprice.stay_expected_sale (method.md, A Reprice) and its "
                 "time; if it still nets more, say in pricing.note that the cut buys time and certainty, not a higher net.")
        elif stay is None and x["list_price"] > strat_out[ri]["list_price"]:
            warn("top_nets_more", f"The {x['list_price_display']} option nets {about(nets[i] - nets[ri])} more than the "
                 "recommended one after holding costs. A top-of-range price takes longer and usually sells near the middle "
                 "of the range anyway (method.md): lower its expected sale or lengthen its time, or explain in pricing.note.")
        elif x["list_price"] < strat_out[ri]["list_price"] and not p.get("competing_offer_upside"):
            # CMA-290: the lower, competing-offer option coming out ahead makes it the better choice on paper, unless
            # pricing.note says that net rests on competing offers (`competing_offer_upside`)
            warn("bottom_nets_more", f"The {x['list_price_display']} option nets {about(nets[i] - nets[ri])} more than the "
                 "recommended one after holding costs, though it only works if competing offers show up (method.md, The "
                 "Three Pricing Strategies). Check its expected sale and seller credit against the recent sale-to-list and "
                 "seller-paid data. If it still nets more, recommend it, or say in pricing.note that its net depends on "
                 "competing offers and set pricing.competing_offer_upside to true.")
    # CMA-319: the competing-offer option netting more than the recommended one gets its caveat on page 1 too, not only
    # in pricing.note: that net rests on competing offers showing up
    caveat = len(strat_out) - 1 if competing and nets[-1] > nets[ri] else None
    # CMA-288: a higher option within about 1% of the recommended price (a relist cap just above it) isn't a distinct
    # strategy: drop it, leaving the recommended and competing-offer options
    for i, x in enumerate(strat_out):
        if i != ri and i != stay and 0 < x["list_price"] - strat_out[ri]["list_price"] <= NEAR_RECOMMENDED * strat_out[ri]["list_price"]:
            warn("top_near_recommended", f"The {x['list_price_display']} option is within 1% of the recommended "
                 f"{strat_out[ri]['list_price_display']}, so it isn't a distinct strategy"
                 + (f" (the relist cap at {money(relist['failed_price'])} leaves no room above it)" if relist else "")
                 + ". Drop it and set pricing.recommended_index to 0, leaving the recommended and competing-offer options "
                 "(method.md, A Relist).")
    reprice_out = None
    if stay is not None:
        rp = R["reprice"]
        # CMA-287: the price the listing started at (report.json, else the export's own row), shown when it was cut
        original = rp.get("original_price") or own_original(R, homes, ("ACTIVE", "PENDING"), rp["current_price"])
        original = original if original and original > rp["current_price"] else None
        reprice_out = {"current_price": rp["current_price"], "current_price_display": money(rp["current_price"]),
                       "days_on_market": rp["days_on_market"], "stay_index": stay, "original_price": original,
                       "original_price_display": money(original) if original else None}
        reprice_out["price_history"] = price_history(L, reprice=reprice_out)
        # CMA-280: Stay's expected sale by one rule (method.md), with the Stay option's own seller credit added back
        if rule:  # CMA-300: the rule was applied above, and fills Stay's expected_sale when report.json leaves it out
            x, gross, ratio = strategies[stay], rule["gross"], rule["ratio"]
            reprice_out.update(stay_expected_sale=gross, stay_expected_sale_display=money(gross), stay_ratio=ratio,
                               stay_ratio_sales=rule["n"], stay_expected_filled=stay_filled)
            if x["expected_sale"] > gross:
                warn("stay_expected_high", f"Stay at Current Price expects {money(x['expected_sale'])}, above "
                     f"{money(gross)} from the rule (the current price times the {ratio:.1%} recent sale-to-original-list "
                     "ratio of sales that sat as long, or the median adjusted value if lower, with Stay's seller credit "
                     f"already added back). Use {money(gross)} as Stay's expected_sale without adding the credit "
                     "again, or say in pricing.note why this listing would do better.")
    # CMA-265: an even number of comps has a midpoint median ($468,437.50): shown to the nearest $100
    # CMA-289: and like every adjusted value, to $100 with an odd number too ($433,729 reads as falsely precise)
    median_display = adjusted_money(median_adjusted)
    trend = {"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
             "r2_key": mls.r2_key(fit["r2"])} if fit else None
    # CMA-298: the recommended net, like every option compare, after holding costs (page 1, the reply and the deck agree)
    values = placeholder_values(R, median_display, strat_out[ri]["net_after_holding_display"], money(max(nets) - min(nets)),
                                about(max(nets) - min(nets)), pay, trend, L, relist, reprice_out, stats.get("months_supply"))
    numbers, raw = market_numbers(st)  # Results_v4: every market-period number, as {sale_to_list_recent} and the rest
    values.update(numbers)
    warn("unfilled_placeholder", *placeholder_warnings(R, values))
    warn("driver_amount", *driver_amount_warnings(R))  # CMA-284
    # Results_v4: wrong data the model wrote stops the render, every problem at once (field: problem → fix)
    content = deck_content(R)
    history, history_errors = listing_history(R, homes, relist, L)
    errors += (typed_supply_errors(R, stats.get("months_supply")) + typed_stat_errors(R, content, raw, values)  # CMA-320
               + split_month_errors(R, values) + launch_plan_errors(R, content) + history_errors)
    if errors:
        raise ReportError(f"report.json has {len(errors)} thing{'s' if len(errors) > 1 else ''} to fix before the "
                          "files are built:\n" + "\n".join("- " + e for e in errors))
    expected_rec = strategies[ri]["expected_sale"]
    expected_note = expected_basis(basis, strategies, values, L)
    key_stats = page_one_stats(R, values, median_display, L, len(R["comps"]["cards"]),
                               min(c["adjusted"] for c in R["comps"]["cards"]), max(c["adjusted"] for c in R["comps"]["cards"]))
    market_table = market_rows(R, numbers, window, L)
    # CMA-325: the chat template's date written out ("September 26, 2026"), never the ISO form
    data_source = {"mls": market.mls, "as_of": as_of, "as_of_display": cma.long_date(as_of), "export": bool(homes)}
    # CMA-279: an export read with the MLS's own built-in columns shows which MLS it is: "assumed" is noise then
    known_layout = bool(homes) and not R.get("export_columns") and bool(market.get("mls_format.cma_export_columns"))
    market_notes = [(n, c) for n, c in zip(market.notes, market.note_codes)
                    if (homes or c not in ("mls_assumed", "mls_not_built_in", "mls_not_given"))
                    and not (known_layout and c == "mls_assumed")]
    out = {
        "data_source": data_source,
        "ok": True,
        "preliminary": preliminary,
        "preliminary_reason": preliminary_reason,
        "preliminary_short": preliminary_short,
        "subject": {"address": s["address"]},
        "recommendation": {"list_price": rec["list_price"], "list_price_display": money(rec["list_price"]),
                           "low": rec["low"], "high": rec["high"],
                           "range_display": f"{money(rec['low'])} – {money(rec['high'])}",
                           # Results_v4: from the recommended option's number, never a typed phrase
                           "expected_sale": L("sum_expected_value", amount=money(expected_rec)),
                           "expected_sale_value": expected_rec},
        "expected_sale_basis": {**basis, "note": expected_note},
        "listing_history": history,
        "key_stats": key_stats,
        "market_table": market_table,
        "market_numbers": numbers,
        "median_adjusted": median_adjusted, "median_adjusted_display": median_display,
        "adjusted_min": min(c["adjusted"] for c in R["comps"]["cards"]),
        "adjusted_max": max(c["adjusted"] for c in R["comps"]["cards"]),
        "n_comps": len(R["comps"]["cards"]),
        "strategies": strat_out, "recommended_index": ri,
        "reprice": reprice_out,
        # CMA-277: the home's earlier listing that ended unsold: no option lists above it without a reason
        "relist": {**relist, "failed_price_display": money(relist["failed_price"]),
                   "original_price_display": money(relist["original_price"]) if relist["original_price"] else None,
                   "price_history": price_history(L, relist=relist)} if relist else None,  # CMA-287
        "first_steps_heading": L("sum_first"),  # "Before We List", or "Before We Reprice"
        "recommended_net_display": strat_out[ri]["net_after_holding_display"],  # CMA-298: page 1's tile
        "net_spread": max(nets) - min(nets), "net_spread_display": money(max(nets) - min(nets)),
        "net_spread_about": about(max(nets) - min(nets)),  # CMA-272: the reply's rounded figure
        # CMA-264: which net the spread (and the deck's net chart) compares: after holding costs when they're counted
        "net_basis": "after_holding" if net["after_holding"] else "net",
        "net": net,
        "payments": pay,
        "trend": trend,
        "placeholders": values,
        # the chat template's wording, with every {placeholder} filled as the PDF fills it
        "summary_page": {**cma.fill(R.get("summary_page") or {}, values), "key_stats": key_stats,
                         "expected_sale": L("sum_expected_value", amount=money(expected_rec))},
        "recommendation_paragraph": cma.fill(rec.get("paragraph", ""), values),
        "window": window, "n_sold": n_sold, "max_distance": max_dist,
        "handoff": h,
        # the chat template's comp rows, with the report's Seller Paid column (CMA-339)
        "comps_table": [{"address": r[0], "sold_display": money(r[1]), "seller_paid_display": money(r[2]),
                         "adjusted_display": adjusted_money(r[3])} for r in R["comps"].get("summary_rows", [])],
        "warnings": warnings,
        "warning_keys": warning_keys,
        "assumptions": assumptions,
        "assumption_keys": assumption_keys,
        "state_hint": hint,  # CMA-282
        "competing_offer_caveat": caveat,  # CMA-319: the strategy index whose net rests on competing offers, or None
        # CMA-259: without an export nothing reads the MLS, so notes about which MLS (assumed, not built in) are noise
        "market_notes": [n for n, c in market_notes],
        "market_note_keys": [c for n, c in market_notes],
    }
    out["options_summary"] = options_summary(out, L)  # CMA-336: page 1's net column header and footnote
    if pay:  # CMA-338: the payment basis, filled as the PDF fills report.json's wording
        pay["basis_note"] = cma.fill(payment_basis(R, pay, L), values)
    return out


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
