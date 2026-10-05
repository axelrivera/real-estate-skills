"""Compute the seller CMA's document model from report.json and the MLS export: every figure, sentence and row the PDF,
the listing presentation and the chat summary show.

    python3 scripts/compute.py report.json [--out DIR] [--mls NAME]

Prints JSON: the recommendation and range, the comps (each card's adjustments itemized and summed), the market table
from the export, each pricing option with its expected sale, its one closing date and its net sheet (a finance.Ledger
per option: the lines, holding costs from the report date to that closing, and every total the sum of the printed
lines), the buyer payments (a Ledger per price), page 1's tiles, the launch date, the strongest match, the notes (one
notes.Notes registry, each said once), the deck's figures, the handoff and `warnings` to fix. Every figure is formatted
once with fmt; every sentence that states a count, price, date or comparison is a template in assets/labels.json. What
report.json writes is judgment (why this price, what it means, what to prepare, conditions) and is refused when it
carries a figure (prose.figures). Also writes <address>.seller.cma.json (the handoff seller-offer-review reads) next to
report.json, in the working folder, never the outputs. render.py places this same model; it never recomputes. The
input is never changed.
"""
import argparse
import copy
import json
import os
import re
import statistics
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, fmt, handoff, mls, notes, profiles, prose  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
with open(os.path.join(ASSETS, "labels.json"), encoding="utf-8") as _f:
    L = json.load(_f)
L.pop("_prose", None)

money = fmt.money
CONTRACT_TO_CLOSE_MONTHS = 1  # a typical financed contract-to-close period, after each option's time to contract
MONTH_DAYS = 30.44
TAX_BILL_MONTH = 10  # when a market doesn't say (`property_tax.bill_month`): from October a year's bill may be out
NEAR_RECOMMENDED = 0.01  # CMA-288: a higher option within 1% of the recommended price isn't a distinct strategy
ASSUMED_SALE_TO_LIST = 0.97  # without an export or market.sale_to_list: a balanced market, after seller-paid costs
EXPECTED_STEP = 500
LAUNCH_DAYS = 14  # without the agent's launch_date: two weeks after the report, the usual prep time
REPLY_KINDS = ("assumption", "estimate", "chat_only")  # the reply's assumption lines; the rest are the sheet's notes
DECK_NOTE_KEYS = ("commission", "not_included")  # the notes the net slide must still show (the rest: speaker notes)
FAILED = ("EXPIRED", "CANCELED", "WITHDRAWN")  # a listing that ended without a sale: its price is a failed price


class ReportError(ValueError):
    """Something report.json needs; the message is written for the agent."""


def t(key, **kw):
    """A labels.json template, filled."""
    return L[key].format(**kw) if kw else L[key]


def word(key, reprice=False, **kw):
    """A label, in its reprice wording ("<key>_reprice": "New List Price", "Before We Reprice") on a reprice."""
    return t(key + "_reprice" if reprice and key + "_reprice" in L else key, **kw)


def labeler(reprice=False):
    """The label lookup as a callable (cma.py's chart and caption code), in the reprice wording on a reprice."""
    return lambda key, **kw: word(key, reprice, **kw)


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


def stop_message(errors):
    return (f"report.json has {len(errors)} thing{'s' if len(errors) > 1 else ''} to fix before the files are built:\n"
            + "\n".join("- " + e for e in errors))


def about(amount):
    """CMA-272: a difference rounded for a chat reply: to $100 under $10,000, $500 under $50,000, $1,000 above, so it
    never contradicts the exact figure printed beside it."""
    step = 100 if abs(amount) < 10000 else 500 if abs(amount) < 50000 else 1000
    return t("about", amount=money(abs(amount), step))


def _warner():
    """(warnings, keys, warn): warn(key, *texts) adds each text with a stable key, so a test can tell which warning
    fired without matching its sentence; `warning_keys` runs parallel to `warnings`."""
    texts, keys = [], []

    def warn(key, *items):
        texts.extend(items)
        keys.extend([key] * len(items))
    return texts, keys, warn


# --- what the model writes: judgment only ---------------------------------------------------------------------------

# Fields the script writes now (each a sentence or figure the report states as fact): a report that still carries one
# is told where its judgment goes instead, so nothing typed is silently dropped.
RETIRED = {
    "labels": "wording overrides are no longer read: every label and sentence the script writes is in assets/labels.json",
    "method": "the script lists the sources from the export and the rate: name any other sources in `sources`",
    "subject.summary_facts": "the script writes the facts line from beds, baths, sqft, pool and year_built",
    "summary_page.key_stats": "the script picks page 1's key numbers",
    "summary_page.first_steps": "page 1's first steps are the first three prep.items (their step and short line)",
    "summary_page.expected_sale": "the script writes the expected sale from the recommended option",
    "recommendation.paragraph": "the script states the range, the median and where the price sits: write why this "
                                "price (no figures) in recommendation.why",
    "comps.summary_paragraph": "the script states the adjusted span, the median, the strongest match and the highest "
                               "sale: write which way the range leans and why (no figures) in comps.lean",
    "scatter.intro": "the script describes what the chart plots",
    "scatter.after_paragraph": "write what the chart shows for this home (no figures) in scatter.takeaway",
    "market.intro": "the script writes the market's counts from the export",
    "market.columns": "the script builds the market table from the export",
    "market.rows": "the script builds the market table from the export",
    "pricing.net_intro": "the script introduces the net sheet",
    "pricing.net_note": "the notes block says what the net sheet leaves out, once",
    "buyer_payment.note": "the script writes the payment basis from the inputs (add rate_week for the survey's week)",
    "deck.title": "the script titles the deck from the address",
    "deck.subtitle": "the cover always reads Listing Presentation with the city and subdivision: a line of your own "
                     "goes in deck.tagline (no figures)",
    "deck.market_stats": "the market slide's cards come from the export (or the comps)",
    "deck.market_periods": "the script names the periods from the export",
    "deck.market_period_labels": "the script names the periods from the export",
    "deck.sold_line": "the script writes the sales reviewed from the export",
    "deck.expected_sub": "the script words the expected sale's line",
    "deck.expected_sale": "the slide shows the recommended option's expected sale",
    "deck.adjustments_summary": "the script lists the adjustments from the comps",
    "deck.launch_plan": "the launch plan is prep.items (each step's short line and icon)",
}
RETIRED_EACH = {
    "comps.cards[].meta": "the script writes each card's sale line from the card and the export",
    "pricing.strategies[].label": "the script names each option from its list price",
    "scatter.callouts[].label": "the script labels each callout from its address",
}

# Judgment fields: what the model writes in words. Each is checked figure-free (prose.figures): the script prints every
# count, price, percent and date itself, so a figure typed here could disagree with the one beside it.
JUDGMENT = (
    "subject.summary", "subject.facts[][0]", "summary_page.label", "summary_page.headline", "summary_page.why[]",
    "summary_page.next_step", "recommendation.why", "means[]", "comps.intro", "comps.method_note", "comps.lean",
    "comps.cards[].bullets[]", "comps.cards[].adjustments[].label", "scatter.heading", "scatter.takeaway",
    "competition.intro", "competition.rows[][6]", "market.bullets[]", "pricing.intro", "pricing.note",
    "pricing.strategies[].note", "prep.intro", "prep.items[].step", "prep.items[].detail", "prep.items[].short",
    "needs[]", "sources[]", "preliminary", "relist.reason_above",
    "deck.tagline", "deck.recommendation_why", "deck.value_drivers[][0]", "deck.value_drivers[][1]",
    "deck.document_items[][0]", "deck.document_items[][1]", "deck.comp_lines.*", "deck.comps_basis",
    "deck.comps_takeaway", "deck.scatter_takeaway", "deck.market_takeaway", "deck.competition_takeaway",
    "deck.strategy_takeaway", "deck.payment_takeaway", "deck.scatter_title", "deck.market_title",
    "deck.competition[][1]", "deck.needs_short[]", "deck.timeline[][1]", "deck.notes.*",
)


def _walk(node, parts, path):
    """(path, value) for every value a dotted pattern ('comps.cards[].bullets[]', 'rows[][6]', 'notes.*') names."""
    if not parts:
        yield path, node
        return
    head, rest = parts[0], parts[1:]
    if head == "[]":
        if isinstance(node, list):
            for i, v in enumerate(node):
                yield from _walk(v, rest, f"{path}[{i}]")
    elif head.startswith("["):
        i = int(head[1:-1])
        if isinstance(node, list) and i < len(node):
            yield from _walk(node[i], rest, f"{path}[{i}]")
    elif head == "*":
        if isinstance(node, dict):
            for k, v in node.items():
                yield from _walk(v, rest, f"{path}.{k}")
    elif isinstance(node, dict) and head in node:
        yield from _walk(node[head], rest, f"{path}.{head}" if path else head)


def _parts(pattern):
    return re.findall(r"\[\d*\]|[^.\[\]]+", pattern)


def schema_errors(R):
    """Retired fields still present, and judgment fields that carry a figure, as `field: problem → fix`."""
    out = []
    for path, why in RETIRED.items():
        if any(v not in (None, "", [], {}) for _, v in _walk(R, _parts(path), "")):
            out.append(f"{path}: no longer written by you → {why}.")
    for pattern, why in RETIRED_EACH.items():
        out += [f"{path}: no longer written by you → {why}." for path, v in _walk(R, _parts(pattern), "")
                if v not in (None, "")]
    items = (R.get("prep") or {}).get("items")
    if isinstance(items, list) and any(not isinstance(i, dict) for i in items):
        out.append("prep.items: each step is now {step, detail, short, icon} → `step` the step in a few words, `detail` "
                   "the report's sentence or two, `short` the line page 1 and the launch plan show (no figures).")
    for pattern in JUDGMENT:
        for path, v in _walk(R, _parts(pattern), ""):
            if isinstance(v, str):
                found = prose.figures(re.sub(r"<[^>]+>", " ", v)) + re.findall(r"\{\w*\}", v)
                if found:
                    out.append(f"{path}: has {', '.join(repr(x) for x in found)} → the report prints every count, price, "
                               "percent and date itself; write this in words, without the figure.")
    return out


def deck_content(R, data_file=None):
    """report.json's `deck` wording (an object, or a path to a JSON file beside report.json or from here), or None
    (no deck asked for, or a file that can't be read: deck.py names it when the deck is built)."""
    content = R.get("deck")
    if isinstance(content, str):
        for path in (content, os.path.join(os.path.dirname(os.path.abspath(data_file)), content) if data_file else None):
            if path and os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        content = json.load(f)
                except (OSError, ValueError):
                    return None
                break
        else:
            return None
    return prose.title_labels(content, DECK_LABELS) if isinstance(content, dict) else None


# Label fields in the deck wording, put in Title Case when it's read
DECK_LABELS = ("scatter_title", "market_title", "value_drivers[][0]", "document_items[][0]")


# --- a reprice, a relist, the listing history ------------------------------------------------------------------------

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
                          "Stay at Current Price strategy at that list price, before the others.")
    up = [x for x in strategies if x["list_price"] > rp["current_price"]]  # CMA-251: the other options are cuts
    if up and not rp.get("allow_increase"):
        raise ReportError(f"A reprice offers Stay at Current Price and price cuts only: {money(up[0]['list_price'])} is above "
                          f"the current {money(rp['current_price'])}. Replace it with a cut (a top-of-range option doesn't "
                          "apply to a reprice), or set reprice.allow_increase if the agent asked to price it higher.")
    return stay


def own_original(R, homes, statuses, price):
    """CMA-287: the Original List Price of the home's own export row with one of `statuses` at `price`, or None."""
    address = R["subject"].get("mls_address", R["subject"]["address"])
    return next((h["original_list_price"] for h in homes if h["status"] in statuses and h.get("current_price") == price
                 and h.get("original_list_price") and mls.same_address(h["address"], address)), None)


def check_relist(R, strategies, homes, stay, as_of):
    """CMA-277: a relist after the home's own listing expired, was canceled or withdrawn. No option lists above the
    failed price unless the agent gave a reason (`relist.reason_above`). The failed listing is report.json's `relist`,
    else the lowest-priced failed listing of the home in the export within the last year. Returns
    {failed_price, status, days_on_market, original_price, source} or None. A reprice has its own rule."""
    if stay is not None:
        return None
    rl, source = R.get("relist"), "report"
    if rl is not None and not (isinstance(rl, dict) and isinstance(rl.get("failed_price"), (int, float))):
        raise ReportError("relist needs failed_price as a number (the last price of the home's listing that expired, was "
                          "canceled or withdrawn), with optional status and days_on_market.")
    if not rl:
        address = R["subject"].get("mls_address", R["subject"]["address"])
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
        R, homes, FAILED, rl["failed_price"])
    return {"failed_price": rl["failed_price"], "status": rl.get("status"), "days_on_market": rl.get("days_on_market"),
            "original_price": original if original and original > rl["failed_price"] else None, "source": source}


def price_history(reprice=None, relist=None):
    """CMA-287: the listing's price history in one sentence (first price, the cut, the price now or when it ended, and
    days on market)."""
    if reprice:
        cut = reprice.get("original_price")
        return t("history_reprice_cut" if cut else "history_reprice", original=money(cut or 0),
                 current=money(reprice["current_price"]), days=fmt.num(reprice["days_on_market"]))
    after = t("history_after_days", days=fmt.num(relist["days_on_market"])) if relist.get("days_on_market") is not None else ""
    status = str(relist.get("status") or "").lower()
    key = ("history_pending" if status == "pending" else "history_listed" if status == "active" else "history_relist")
    return t(key + ("_cut" if relist.get("original_price") else ""), original=money(relist.get("original_price") or 0),
             failed=money(relist["failed_price"]), after=after)


HISTORY_STATUSES = {"expired": "expired", "withdrawn": "withdrawn", "canceled": "canceled", "cancelled": "canceled"}


def _when(value):
    """'March 2017' from 2017-03-15 or 2017-03, '2017' from 2017; None when there's none."""
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", str(value or "").strip())
    if not m:
        return None
    return f"{fmt.MONTHS[int(m.group(2)) - 1]} {m.group(1)}" if m.group(2) and 1 <= int(m.group(2)) <= 12 else m.group(1)


def listing_history(R, homes, relist):
    """Results_v4 case 02: the home's own listings that ended unsold (expired, withdrawn, canceled), however long ago,
    each with its price, first price and date. report.json's `listing_history` (from the property report), else the
    export's own rows, plus a relist's failed listing. Returns (events, errors)."""
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
        e["text"] = (L["hist_" + e["status"]] + (t("hist_in", when=e["when"]) if e["when"] else "")
                     + (t("hist_after", days=fmt.num(e["days"])) if isinstance(e["days"], (int, float)) else "")
                     + t("hist_at", price=money(e["price"])) + (t("hist_first", price=money(first)) if first else "")
                     + ("" if e["when"] else L["hist_undated"]) + ".")
        e["price_display"], e["original_price_display"] = money(e["price"]), money(first) if first else None
    return events, errors


# --- expected sales -----------------------------------------------------------------------------------------------------

def stay_expected(R, homes, rp, median_adjusted, split):
    """CMA-280: the Stay at Current Price option's expected sale, net of seller-paid costs: the current price times the
    recent sale-to-original-list ratio of sales that sat at least as long as this listing has (all recent sales when
    fewer than 3 did), or the median adjusted value if lower. None without an export. Returns (value, ratio, n)."""
    address = R["subject"].get("mls_address", R["subject"]["address"])
    sold = [h for h in homes if h["status"] == "SOLD" and h.get("original_list_price") and h.get("close_price")
            and not mls.same_address(h["address"], address) and (not split or (h.get("close_date") and h["close_date"] >= split))]
    slow = [h for h in sold if (h.get("days_on_market") or 0) >= rp["days_on_market"]]
    pool = slow if len(slow) >= 3 else sold
    if not pool:
        return None, None, 0
    ratio = statistics.median((h["close_price"] - (h.get("seller_paid") or 0)) / h["original_list_price"] for h in pool)
    return min(rp["current_price"] * ratio, median_adjusted), round(ratio, 4), len(pool)


def stay_rule(R, homes, x, median_adjusted, split):
    """CMA-280, CMA-300: Stay's expected sale by the rule, with its own seller credit added back, to the nearest $1,000.
    Returns {gross, ratio, n}, or None without an export."""
    value, ratio, n = stay_expected(R, homes, R["reprice"], median_adjusted, split)
    if value is None:
        return None
    # never above the price it stays at: a seller credit added back can't lift a sale past its own list price
    return {"gross": min(fmt.half_up(value + (x.get("seller_credit") or 0), 1000), x["list_price"]), "ratio": ratio,
            "n": n}


def fill_expected_sales(R, strategies, stats, stay, competing):
    """Each option's expected sale by one rule: its list price times the recent sale-to-FINAL-list ratio (net of
    seller-paid costs: the export's when it carries final list prices, else `market.sale_to_list`, else 97% assumed),
    plus its own seller credit, to the nearest $500. Kept inside the supported range, never above the list price
    (except the competing-offer option, the last), an option above the recommended price expects the recommended one's
    sale, and a higher list price never expects less than a lower one. An expected_sale in report.json is the agent's
    figure and is kept. Fills the strategies (report.json's copy) in place; returns the basis for the note."""
    m = R.get("market") or {}
    if stats.get("sale_to_final_list_recent"):
        ratio, source = stats["sale_to_final_list_recent"], "export"
    elif isinstance(m.get("sale_to_list"), (int, float)) and 0.5 < m["sale_to_list"] <= 1.2:
        ratio, source = m["sale_to_list"], "report"
    else:
        ratio, source = ASSUMED_SALE_TO_LIST, "assumed"
    low, high, last = R["recommendation"]["low"], R["recommendation"]["high"], len(strategies) - 1
    filled = [i for i, x in enumerate(strategies) if i != stay and x.get("expected_sale") is None]
    agent = [i for i, x in enumerate(strategies) if i != stay and i not in filled]
    capped = floored = False
    for i in filled:
        x = strategies[i]
        v = fmt.half_up(x["list_price"] * ratio + (x.get("seller_credit") or 0), EXPECTED_STEP)
        cap = min(high, x["list_price"]) if not (competing and i == last) else high
        floored |= v < low and cap > v
        capped |= v > cap
        x["expected_sale"], x["expected_sale_source"] = min(max(v, low), cap), "rule"
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
    return {"ratio": ratio, "ratio_display": fmt.pct(ratio, 1, fixed=True), "source": source, "filled": filled,
            "agent": agent, "capped": capped, "floored": floored, "top": top}


# --- the launch and each option's closing ---------------------------------------------------------------------------------

def launch_info(R, as_of):
    """The one go-live date: report.json's `launch_date` (the agent's), else LAUNCH_DAYS after the report date."""
    given = _date(R.get("launch_date"), "launch_date")
    d = given or as_of + timedelta(days=LAUNCH_DAYS)
    return {"date": d.isoformat(), "display": fmt.date_long(d), "short": fmt.date_short(d, year=False),
            "source": "agent" if given else "assumed", "line": t("line_launch", date=fmt.date_long(d))}


def months_to_contract(x):
    return x.get("months_to_contract") if x.get("months_to_contract") is not None else finance.months_in(x.get("time"))


def option_closings(R, strategies, as_of, launch):
    """One closing date per option, for its tax proration and its holding costs alike: its own `closing_date`; else the
    later of costs.expected_closing_date (the seller's goal) and the launch date plus its time to contract plus a month
    to close (a slower price can't close by the goal); None with neither. Holding runs from the report date to it."""
    target = _date((R.get("costs") or {}).get("expected_closing_date"), "expected_closing_date")
    go = date.fromisoformat(launch["date"])
    out = []
    for i, x in enumerate(strategies):
        own = _date(x.get("closing_date"), f"pricing.strategies[{i}].closing_date")
        months = months_to_contract(x)
        est = go + timedelta(days=fmt.half_up((months + CONTRACT_TO_CLOSE_MONTHS) * MONTH_DAYS)) if months is not None else None
        closing = own or (max(d for d in (target, est) if d) if target or est else None)
        out.append({"date": closing, "months_to_contract": months,
                    "hold_months": round(max((closing - as_of).days, 0) / MONTH_DAYS, 2) if closing else None})
    return out


# --- the net sheet: a Ledger per option -------------------------------------------------------------------------------

# The order the net sheet's lines print in (finance.seller_net's keys, then the script's own)
NET_LINE_ORDER = ("listing_fee", "buyer_broker_fee", "transfer_tax", "transfer_surtax", "owner_title", "title_fees",
                  "estoppel", "credit", "other", "tax_proration", "tax_prior_year", "payoff")


def prior_year_bill(annual_tax, market, bill_paid, as_of):
    """This year's whole tax bill, owed at a closing early next year when it's still unpaid: taxes paid in arrears,
    the agent hasn't said it's paid, and the bill isn't due before the year ends. 0 otherwise. At the early-payment
    discount, like the proration."""
    if not annual_tax or bill_paid or market.get("property_tax.paid") == "advance":
        return 0
    if finance.tax_due_date(date(as_of.year, 12, 31), market) is not None:  # due within the year: paid by then
        return 0
    return annual_tax * (1 - (market.get("property_tax.early_payment_discount") or 0))


def payoff_of(costs):
    """(payoff or None, estimated): a stated payoff as given, 0 for no mortgage, a balance plus a month's interest."""
    if costs.get("mortgage_payoff") is not None:
        return costs["mortgage_payoff"], False
    if costs.get("mortgage_balance") == 0:
        return 0, False
    if costs.get("mortgage_balance"):  # CMA-29: a balance isn't a payoff; a month's interest on top
        return finance.payoff_from_balance(costs["mortgage_balance"], costs.get("mortgage_rate")), True
    return None, False


def net_sheet(R, market, strategies, closings, as_of):
    """Each option's money as a finance.Ledger at its expected sale: the costs (finance.seller_net), this year's whole
    tax bill when an option closes next year, the payoff, then the holding costs from the report date to that option's
    closing. Every line is rounded once; every total is a sum of the printed lines."""
    costs, s = R.get("costs") or {}, R["subject"]
    lf, bf = _frac(costs, "listing_fee_pct", "costs"), _frac(costs, "buyer_broker_fee_pct", "costs")
    others = costs.get("other") or []
    payoff, payoff_est = payoff_of(costs)
    has_hoa = bool(costs.get("hoa", s.get("hoa", False)))
    annual_tax, bill_paid = costs.get("annual_tax"), costs.get("current_tax_bill_paid")
    loan_rate = costs["mortgage_rate"] / 100 if costs.get("mortgage_rate") else finance.PAYOFF_INTEREST
    monthly, left_out = finance.holding_monthly(strategies[0]["list_price"], market, payoff, costs.get("hoa_monthly"), loan_rate)
    holding = bool(monthly) and all(c["hold_months"] is not None for c in closings)
    raw, ledgers, next_year = [], [], []
    for i, (x, c) in enumerate(zip(strategies, closings)):
        closing = c["date"]
        later = bool(closing and closing.year > as_of.year)
        n = finance.seller_net(x["expected_sale"], market, credit=x.get("seller_credit", 0) or 0, payoff=None,
                               listing_fee_pct=lf, buyer_broker_fee_pct=bf, has_hoa=has_hoa,
                               other_costs=[o for o in others if o.get("amount")], title_fees=costs.get("title_fees"),
                               annual_tax=annual_tax, closing=closing, bill_paid=None if later else bill_paid,
                               prop_type=s.get("property_type"))
        raw.append(n)
        led = finance.Ledger()
        led.add("sale", L["net_sale"], x["expected_sale"])
        for ln in n["lines"]:
            led.cost(ln["key"], ln["label"], ln["amount"], rate=ln.get("rate"))
        extra = prior_year_bill(annual_tax, market, bill_paid, as_of) if later else 0
        if extra:  # a closing next year: this year's whole bill (assumed unpaid), plus next year's share to closing
            led.cost("tax_prior_year", t("net_tax_prior_year", year=str(as_of.year)), extra)
            next_year.append(i)
        if payoff:
            led.cost("payoff", L["net_payoff"], payoff)
        if holding:
            led.cost("holding", L["net_holding"], monthly * c["hold_months"])
        ledgers.append(led)
    return {"ledgers": ledgers, "raw": raw, "payoff": payoff, "payoff_estimated": payoff_est, "monthly": monthly,
            "left_out": left_out, "holding": holding, "loan_rate": loan_rate, "next_year": next_year,
            "cash": payoff is not None, "no_mortgage": payoff == 0}


def net_rows(net, strategies, closings):
    """The net sheet's rows across the options: the sale, each line by (key, label) in NET_LINE_ORDER (a line such as a
    seller credit exists only in some options), the total (cash at closing, or the net before payoff), the holding
    costs and the net after them, with the expected closing as an info row. `display` is every amount as printed."""
    leds = net["ledgers"]

    def amounts(key, label=None):
        return [sum(ln["amount"] for ln in led if ln["key"] == key and (label is None or ln["label"] == label)) for led in leds]

    def label(ln):
        key, rate = ln["key"], ln.get("rate")
        if key in ("listing_fee", "buyer_broker_fee"):  # a default commission is a default: no label, no note
            return t("net_" + key, pct=fmt.pct(rate, 2))
        return L.get("net_" + key, ln["label"]) if key in ("owner_title", "title_fees", "credit") else ln["label"]

    rows = [{"kind": "line", "key": "sale", "label": L["net_sale"], "amounts": amounts("sale")}]
    keys = [k for k in NET_LINE_ORDER if any(led.has(k) for led in leds)]
    keys += [ln["key"] for led in leds for ln in led if ln["key"] not in keys and ln["key"] not in ("sale", "holding")]
    for key in dict.fromkeys(keys):
        names = list(dict.fromkeys(ln["label"] for led in leds for ln in led if ln["key"] == key))
        if key != "other" and len(names) > 1:  # one line worded two ways (a proration charged in one option, credited
            # in another): one row, so each option's amount sits on the same line
            rows.append({"kind": "line", "key": key, "label": L.get(f"net_{key}_mixed", names[0]), "amounts": amounts(key),
                         "present": [led.has(key) for led in leds]})
            continue
        for name in names:
            sample = next(ln for led in leds for ln in led if ln["key"] == key and ln["label"] == name)
            rows.append({"kind": "line", "key": key, "label": label(sample), "amounts": amounts(key, name),
                         "present": [any(ln["key"] == key and ln["label"] == name for ln in led) for led in leds]})
    total_key = "net_total_cash" if net["cash"] else "net_total"
    totals = [led.total(where=lambda ln: ln["key"] != "holding") for led in leds]
    rows.append({"kind": "total", "key": "total", "label": L[total_key], "amounts": totals})
    after = None
    if net["holding"]:
        rows.append({"kind": "line", "key": "holding", "label": L["net_holding"], "amounts": amounts("holding")})
        after = [led.total() for led in leds]
        rows.append({"kind": "total", "key": "after_holding", "label": L["net_after_holding"], "amounts": after})
    for r in rows:  # a line an option doesn't have (a seller credit, next year's bill) prints as the empty-value dash
        r["display"] = [money(a) if has else fmt.EMPTY for a, has in zip(r["amounts"], r.pop("present", [True] * len(leds)))]
    if any(c["date"] for c in closings):  # one closing per option: the date its proration and holding run to
        rows.insert(1, {"kind": "info", "key": "closing", "label": L["net_closing"], "amounts": None,
                        "display": [fmt.date_short(c["date"]) if c["date"] else fmt.EMPTY for c in closings]})
    return rows, totals, after


def state_hint(R, market, strategies, closings, as_of, ri, base):
    """CMA-282: with no state for the home but an MLS built in for exactly one built-in state (Stellar: Florida), what
    that state's costs would change: its transfer tax line against the estimate, and the recommended option's net."""
    if market.state or not market.mls:
        return None
    states = [st for st in (market.get("coverage") or {}) if st in profiles._layers("state")]
    if len(states) != 1:
        return None
    other = profiles.load_market(state=states[0], mls=market.mls).with_deal(R.get("costs"))
    alt = net_sheet(R, other, strategies, closings, as_of)
    line = lambda n: next((ln["label"] for ln in n["ledgers"][ri] if ln["key"] == "transfer_tax"), L["hint_no_transfer_tax"])
    diff = alt["ledgers"][ri].total() - base["ledgers"][ri].total()
    return {"state": states[0], "state_name": profiles.STATES.get(states[0], states[0]), "transfer_tax_label": line(alt),
            "estimate_label": line(base), "net_difference": diff, "net_difference_about": about(diff)}


# --- buyer payments: a Ledger per price --------------------------------------------------------------------------------

def buyer_tax_rates(R, market):
    """(school_mills, total_mills, homestead) for the buyer-payment estimate: explicit mills, or a district lookup."""
    bp = R["buyer_payment"]
    school, total = bp.get("school_mills"), bp.get("total_mills")
    if total is None and bp.get("district"):
        row, _ = finance.millage_row(market, R["subject"].get("county"), bp["district"])
        if row:
            school, total = row["school"], row["total"]
    return school, total, bp.get("homestead", True)


def payment_ledger(price, market, loan_type, down, rate, school, total, homestead, ins, hoa, flood):
    """One price's buyer payment as a finance.Ledger (principal and interest, tax, insurance, flood when quoted,
    mortgage insurance, HOA): each line rounded once, the total the sum of the printed lines. None without a tax rate."""
    tax = finance.property_tax(price, market, school, total, homestead)
    if tax["annual"] is None:
        return None, tax, None
    p = finance.monthly_payment(price, loan_type, down, rate, tax["annual"], ins, hoa, flood_annual=flood)
    led = finance.Ledger()
    led.add("pi", L["pay_pi"], p["pi"])
    led.add("tax", L["pay_tax"], p["tax"])
    led.add("ins", L["pay_ins"], p["ins"])
    if p["flood"] is not None:
        led.add("flood", L["pay_flood"], p["flood"])
    led.add("mi", L["pay_mi"], p["mi"])
    led.add("hoa", L["pay_hoa"], p["hoa"] or 0)
    return led, tax, p


def payments(R, market, insurance):
    """The buyer's payment at each list price (a Ledger each), the per-$10,000 effect and the basis, or None without a
    tax rate."""
    bp = R["buyer_payment"]
    school, total, homestead = buyer_tax_rates(R, market)
    try:
        loan_type = finance.program(bp.get("loan_type", "conventional"))
    except ValueError as e:
        raise ReportError(f"buyer_payment.loan_type: {e}") from None
    down = _frac(bp, "down_pct", "buyer_payment", 0.05)
    s = R["subject"]
    zone = bp.get("flood_zone") or next((v for lbl, v in s.get("facts") or [] if str(lbl).lower() == "flood zone"), None)
    flood = finance.flood_insurance(zone, bp.get("flood_insurance_annual"), market, _date(R.get("as_of"), "as_of"),
                                    condo_unit=finance.property_type(s.get("property_type")) == "condo")
    args = (market, loan_type, down, bp["rate"], school, total, homestead, insurance["annual"], bp.get("hoa_monthly", 0),
            flood["annual"])
    rows, tax = [], None
    for x in R["pricing"]["strategies"]:
        led, tax, p = payment_ledger(x["list_price"], *args)
        if led is None:
            return None, tax
        down_amt = fmt.half_up(p["cash_down"])
        rows.append({"list_price": x["list_price"], "lines": led.tuples(), "payment": led.total(), "down": down_amt,
                     "list_price_display": money(x["list_price"]), "payment_display": money(led.total()),
                     "down_display": money(down_amt)})
    rec = R["recommendation"]["list_price"]
    per_10k = payment_ledger(rec, *args)[0].total() - payment_ledger(rec - 10000, *args)[0].total()
    return {"rows": rows, "per_10k": per_10k, "per_10k_display": money(per_10k),
            "intro": t("pay_intro", per10k=money(per_10k), down10k=money(10000 * down)),
            "down_per_10k": fmt.half_up(10000 * down), "down_per_10k_display": money(10000 * down),
            "loan_type": loan_type, "program": L["prog_" + loan_type], "down_pct": down,
            "down_display": fmt.pct(down, 2), "rate": bp["rate"], "rate_display": fmt.pct(bp["rate"] / 100, 3),
            "insurance_annual": insurance["annual"], "insurance_estimated": insurance["estimated"], "flood": flood,
            "school_mills": school, "total_mills": total, "homestead": homestead, "tax_basis": tax["basis"],
            "tax_estimated": tax["estimated"],
            # CMA-270: a homestead exemption lowers the tax only where the market has one built in
            "homestead_applied": bool(homestead and total is not None
                                      and market.get("property_tax.primary_residence_exemptions"))}, tax


def insurance_line(R, market):
    """The buyer's homeowner's insurance: the agent's figure as given, else the shared estimate at the recommended price."""
    bp = R["buyer_payment"]
    if bp.get("insurance_annual") not in (None, ""):
        return {"annual": bp["insurance_annual"], "estimated": False}
    est = finance.insurance_estimate(R["recommendation"]["list_price"], market, R["subject"].get("year_built"))
    return {"annual": fmt.half_up(est["annual"]), "estimated": True}


# --- comps, strongest match, market -------------------------------------------------------------------------------------

def median_rounded(median_adjusted, count):
    """CMA-265: an even number of comps has a midpoint median: shown to the nearest $100; an odd count's median is a
    comp's own adjusted value, kept to the dollar. Every figure quoted from the median uses this value."""
    return fmt.half_up(median_adjusted, 1 if count % 2 else 100)


def strongest_comp(cards, low, high):
    """The comp that matches the home best: the smallest adjustments (gross, as a share of its price) among comps whose
    adjusted value sits inside the supported range (all comps when none does), the newest on a tie."""
    def gross(c):
        return sum(abs(a["amount"]) for a in c.get("adjustments") or []
                   if isinstance(a, dict) and isinstance(a.get("amount"), (int, float))) / max(c.get("sold_price") or 1, 1)
    inside = [i for i, c in enumerate(cards) if low <= c["adjusted"] <= high] or list(range(len(cards)))
    return min(inside, key=lambda i: (round(gross(cards[i]), 4), -(cma.comp_close_date(cards[i]) or date.min).toordinal()))


def export_row(homes, address):
    return next((h for h in homes or () if h.get("status") == "SOLD"
                 and mls.same_address(cma._street(h["address"]), cma._street(address))), None)


def comp_cards(cards, homes, best):
    """Each card as the report places it: its sale line (from the card and the export's row), its adjustments as a
    finance.Ledger (the sale price, seller-paid costs and each adjustment add up to the adjusted value) and its
    judgment bullets."""
    out = []
    for i, c in enumerate(cards):
        row = export_row(homes, c["address"]) or {}
        closed = cma.comp_close_date(c, homes)
        led = finance.Ledger()
        led.add("sold", L["card_sold"], c["sold_price"])
        if c.get("seller_concessions"):
            led.cost("concessions", L["card_concessions"], c["seller_concessions"])
        for a in c.get("adjustments") or []:
            if a.get("amount"):
                led.add("adj", a["label"], a["amount"])
        meta = [t("meta_sold", price=money(c["sold_price"]))]
        if closed:
            meta.append(fmt.date_short(closed))
        if row.get("living_area"):
            meta.append(t("meta_sqft", n=fmt.num(row["living_area"])))
        if row.get("beds") and row.get("full_baths"):
            meta.append(t("meta_beds", beds=fmt.num(row["beds"]), baths=fmt.num(row["full_baths"])))
        if row.get("private_pool"):
            meta.append(L["meta_pool"])
        if row.get("lot_acres"):
            meta.append(t("meta_lot", n=fmt.num(row["lot_acres"], 2)))
        if row.get("distance") is not None:
            meta.append(t("meta_dist", n=fmt.num(row["distance"], 1)))
        out.append({"address": cma.display_address(c["address"]), "adjusted": led.total(),
                    "adjusted_display": money(led.total()), "adjusted_k": fmt.k(led.total()),
                    "sold_price": c["sold_price"], "close_date": closed.isoformat() if closed else None, "meta": meta,
                    "lines": [[ln["label"], money(ln["amount"], style="signed") if ln["key"] != "sold" else money(ln["amount"])]
                              for ln in led],
                    "strongest": i == best, "bullets": list(c.get("bullets") or [])})
    return out


def comps_count_line(cards, homes, split):
    dates = [d for d in (cma.comp_close_date(c, homes) for c in cards) if d]
    if not dates:
        return t("line_comps_count_undated", n=cma.number_word(len(cards)))
    since = [d for d in dates if split and d >= split]
    dists = [r["distance"] for r in (export_row(homes, c["address"]) for c in cards) if r and r.get("distance") is not None]
    within = ""
    if dists and len(dists) == len(cards):
        far = max(dists)
        within = L["line_comps_within_one"] if far <= 1 else t("line_comps_within", dist=fmt.num(-(-far * 10 // 1) / 10, 1))
    return t("line_comps_count", n=cma.number_word(len(cards)), first=fmt.date_short(min(dates)),
             last=fmt.date_short(max(dates)),
             since=t("line_comps_since", k=cma.number_word(len(since)), split=cma.day_words(split))
             if split and since and len(since) < len(dates) else "", within=within)


def range_position(value, low, high):
    """Where a value sits against the supported range, as a labels.json key: below or above it, else near the bottom,
    in the middle or near the top (by thirds)."""
    if value < low:
        return "pos_below"
    if value > high:
        return "pos_above"
    third = (high - low) / 3
    return "pos_bottom" if value <= low + third else "pos_top" if value >= high - third else "pos_middle"


def vs_median(price, median):
    d = price - median
    return t("vs_median_above" if d > 0 else "vs_median_below", amount=money(abs(d))) if d else L["vs_median_at"]


def market_section(st, R):
    """The market table (before and since the split), its counts and the deck's cards, from the export's stats; without
    an export, the deck's cards from the comps. Returns (section or None, deck cards)."""
    if not st:
        return None
    w, early, recent = st["window"], st["sold_early"], st["sold_recent"]
    periods = fmt.period_labels(w)

    def cells(field, f):
        return [f(p[field]) if p.get(field) is not None and p.get("n") else fmt.EMPTY for p in (early, recent)]
    days = lambda v: t("mk_days_value", n=fmt.num(v))  # noqa: E731
    stems = [("sold", lambda: [fmt.num(early.get("n", 0)), fmt.num(recent.get("n", 0))]),
             ("median_price", lambda: cells("median_price", money)),
             ("sale_to_list", lambda: cells("median_sale_to_original_list", lambda v: fmt.pct(v, 1, fixed=True))),
             ("days", lambda: cells("median_days_on_market", days))]
    if st["sold_all"].get("share_with_seller_paid_costs"):  # an export with no seller-paid column reads as unknown
        stems += [("credit_share", lambda: cells("share_with_seller_paid_costs", lambda v: fmt.pct(v, 0))),
                  ("credit_amount", lambda: cells("median_seller_paid_when_paid", money))]
    rows = [[L["mk_" + stem], *f()] for stem, f in stems]
    supply = st.get("months_supply_at_recent_pace")
    intro = t("line_market_intro", n=fmt.num(st["sold_all"]["n"]), first=fmt.date_short(w["first_close"]),
              last=fmt.date_short(w["last_close"]), active=fmt.num(st["active_count"]),
              supply=t("line_market_supply", months=fmt.months(supply)) if supply is not None else "")
    cards = [{"key": stem, "label": L["deck_mk_" + stem], "values": r[1:]} for (stem, _), r in zip(stems, rows)
             if stem in ("sale_to_list", "days", "credit_share", "credit_amount") and fmt.EMPTY not in r[1:]]
    return {"intro": intro, "columns": ["", *periods], "rows": rows, "periods": periods, "cards": cards,
            "bullets": list((R.get("market") or {}).get("bullets") or [])}


def comps_market_cards(R, cards):
    """Without an export the market slide's cards come from the comps (one value each): how many, how many sellers
    paid buyer costs and how much, and the sale-to-list the agent gave."""
    raw = R["comps"]["cards"]
    paid = [c.get("seller_concessions") for c in raw if c.get("seller_concessions")]
    card = lambda key, value: {"key": key, "label": L["deck_mk_" + key], "values": [value]}  # noqa: E731
    out = [card("comps", fmt.num(len(raw))), card("credit_share", fmt.pct(len(paid) / len(raw), 0))]
    if paid:
        out.append(card("credit_amount", money(statistics.median(paid))))
    m = R.get("market") or {}
    if isinstance(m.get("sale_to_list"), (int, float)):
        out.append(card("sale_to_final", fmt.pct(m["sale_to_list"], 1, fixed=True)))
    return out


def key_stats(C, stats):
    """Page 1's three key numbers: with an export the median adjusted comp, the recent sale-to-original-list and days to
    contract since the split; without one the median, the adjusted span and the number of comps."""
    out = [(C["median_adjusted_display"], t("sum_stat_median", n=fmt.num(C["n_comps"])))]
    since = cma.day_words(fmt.to_date(stats["split_date"])) if stats.get("split_date") else None
    if since and stats.get("sale_to_original_list_recent") is not None and stats.get("median_days_recent") is not None:
        out += [(fmt.pct(stats["sale_to_original_list_recent"], 1, fixed=True), t("sum_stat_ratio", since=since)),
                (t("mk_days_value", n=fmt.num(stats["median_days_recent"])), t("sum_stat_days", since=since))]
    else:
        out += [(fmt.range(C["adjusted_min"], C["adjusted_max"], fmt.k), L["sum_stat_span"]),
                (fmt.num(C["n_comps"]), L["sum_stat_comps"])]
    return [list(x) for x in out]


# --- notes -------------------------------------------------------------------------------------------------------------

def add_notes(N, R, market, net, strategies, closings, basis, pay, as_of, stay, competing_caveat, reprice):
    """Every assumption, estimate and caveat behind the figures, each once (notes.Notes)."""
    costs = R.get("costs") or {}
    leds, raw = net["ledgers"], net["raw"]
    first = raw[0]
    assumed = {a["key"]: a for a in first["assumed"]}
    # what the expected sales rest on: once, here (never also under the pricing table or in the method)
    if basis["filled"]:
        parts = [t("note_expected_" + basis["source"], ratio=basis["ratio_display"],
                   since=cma.day_words(fmt.to_date(basis["split"])) if basis.get("split") else "")]
        if basis["capped"] or basis["floored"]:
            parts.append(L["note_expected_limits"])
        if basis["top"]:
            parts.append(t("note_expected_top", prices=cma._and([money(strategies[i]["list_price"]) for i in basis["top"]])))
        N.add("expected_sale", " ".join(parts), "assumption" if basis["source"] == "assumed" else "estimate")
    if basis["agent"]:
        prices = cma._and([money(strategies[i]["list_price"]) for i in basis["agent"]])
        N.add("expected_agent", t("note_expected_agent" if len(basis["agent"]) == 1 else "note_expected_agent_many",
                                  prices=prices), "info")
    if stay is not None and strategies[stay].get("expected_sale_source") == "stay_rule":
        N.add("expected_stay", L["note_expected_stay"], "estimate")
    if competing_caveat is not None:
        N.add("competing", t("note_competing", price=money(strategies[competing_caveat]["list_price"])), "info")
    if net["holding"]:
        parts = []
        if net["payoff"]:
            parts.append(t("note_holding_loan_rate" if costs.get("mortgage_rate") else "note_holding_loan_assumed",
                           rate=fmt.pct(net["loan_rate"], 2), payoff=money(net["payoff"])))
        if costs.get("hoa_monthly"):
            parts.append(L["note_holding_hoa"])
        parts += [L["note_holding_" + p] for p in ("insurance", "utilities") if p not in net["left_out"]]
        loan = cma._and(parts) + ("" if net["payoff"] else "; " + L["note_holding_no_loan" if net["no_mortgage"]
                                                                   else "note_holding_loan_unknown"])
        text = t("note_holding", monthly=money(net["monthly"], 10), loan=loan)
        if net["left_out"]:
            text += " " + t("note_holding_left_out", items=" and ".join(net["left_out"]))
        N.add("holding", text, "assumption" if net["payoff"] and not costs.get("mortgage_rate") else "estimate")
    has_tax = any(led.has("tax_proration") or led.has("tax_prior_year") for led in leds)
    if has_tax:
        bill_paid = costs.get("current_tax_bill_paid")
        bill_month = market.get("property_tax.bill_month") or TAX_BILL_MONTH
        unpaid = bill_paid is None and any(c["date"] and c["date"].year == as_of.year and c["date"].month >= bill_month
                                           and not finance.tax_bill_assumed_paid(c["date"], market, bill_paid)
                                           for c in closings)
        parts = [L["note_tax_closing"]]
        if net["next_year"]:
            parts.append(t("note_tax_next_year" if len(net["next_year"]) == 1 else "note_tax_next_year_many",
                           options=cma._and([money(strategies[i]["list_price"]) for i in net["next_year"]]),
                           year=str(as_of.year), next=str(as_of.year + 1)))
        if unpaid:
            parts.append(L["note_tax_unpaid"])
        N.add("tax", " ".join(parts), "assumption" if unpaid or net["next_year"] else "info")
    if "title_fees" in assumed and not assumed["title_fees"].get("estimate"):
        fees = market.get("closing_costs.seller_title_fees") or {}
        N.add("title_fees", t("note_title_fees", items=", ".join(f"{k.replace('_', ' ')} {money(v)}" for k, v in fees.items())),
              "estimate")
    estimates = [a["text"] for a in first["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimates:
        N.add("national", t("note_national", items=", ".join(estimates)), "estimate")
    if net["payoff"]:
        N.add("payoff", L["note_payoff_balance"] if net["payoff_estimated"] else L["note_payoff"],
              "assumption" if net["payoff_estimated"] else "info")
    if any(led.has("listing_fee") or led.has("buyer_broker_fee") for led in leds):
        N.add("commission", finance.COMMISSION_NOTE, "info")
    brokerage = [a["text"] for a in first["assumed"] if a["key"] in ("listing_fee", "buyer_broker_fee")]
    if brokerage:  # a default commission is a default: no label on the page; the reply asks for the terms
        N.add("commission_default", t("note_commission_default_reprice" if reprice else "note_commission_default",
                                      items=", ".join(brokerage)), "chat_only")
    left = [L["not_included_payoff"]] if not net["cash"] else []
    if not has_tax and market.get("property_tax.paid") != "advance":
        left.append(L["not_included_tax"])
    left.append(L["not_included_repairs"])
    N.add("not_included", t("note_not_included", items=cma._and(left)), "info")
    if pay:
        N.add("payment", payment_note(R, pay), "estimate")
        N.add("flood", pay["flood"]["note"], "info")


def payment_note(R, pay):
    """What the buyer payments assume: program, down, rate and its week, the tax basis, insurance, mortgage insurance and
    the homestead rule, in one note."""
    mi_rate = finance.annual_mi_rate(pay["loan_type"], pay["down_pct"])
    mi = t("pay_note_mi", mi=fmt.pct(mi_rate, 2)) if mi_rate and not (
        pay["loan_type"] == "conventional" and pay["down_pct"] >= 0.20) else ""
    text = t("pay_note", program=pay["program"], down=pay["down_display"], rate=pay["rate_display"], basis=pay["tax_basis"],
             ins=money(pay["insurance_annual"]),
             ins_kind=L["pay_note_ins_est" if pay["insurance_estimated"] else "pay_note_ins_given"], mi=mi)
    if pay["tax_estimated"]:
        text += " " + t("pay_note_tax_estimated", basis=pay["tax_basis"])
    elif not pay["homestead_applied"]:  # CMA-270: taxes with no homestead exemption (none built in, or none filed)
        text += " " + L["pay_no_homestead_built_in" if pay["homestead"] else "pay_no_homestead"]
    return text


# --- the document model ------------------------------------------------------------------------------------------------

def compute(R, market, homes, data_file=None):
    """The document model from report.json (never changed), the market and the export's homes."""
    R = copy.deepcopy(R)
    content = deck_content(R, data_file)
    if R.get("deck") is not None:
        R["deck"] = content if content is not None else R["deck"]
    errors = schema_errors(R if content is not None else {k: v for k, v in R.items() if k != "deck"})
    if errors:
        raise ReportError(stop_message(errors))
    _require(R, "subject.address", "subject.sqft", "recommendation.list_price", "recommendation.low", "recommendation.high",
             "comps.cards", "pricing.strategies", "buyer_payment.rate")
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
    for i, x in enumerate(strategies):
        if not isinstance(x.get("list_price"), (int, float)) or isinstance(x.get("list_price"), bool):
            raise ReportError("Every pricing strategy needs list_price as a number.")
        if x.get("expected_sale") is not None and not isinstance(x["expected_sale"], (int, float)):
            raise ReportError(f"pricing.strategies[{i}].expected_sale: {x['expected_sale']!r} isn't a number → give the "
                              "agent's figure as a plain number, or leave it out and compute.py fills it by the rule.")
    items = (R.get("prep") or {}).get("items") or []
    for i, it in enumerate(items):
        if not (isinstance(it, dict) and str(it.get("step") or "").strip()):
            raise ReportError(f"prep.items[{i}] needs step (a few words), detail and short.")
    if rec["low"] > rec["high"]:
        raise ReportError("recommendation.low is above recommendation.high.")
    ri = p.get("recommended_index", 1)
    if not 0 <= ri < len(strategies):
        raise ReportError("pricing.recommended_index doesn't point at a strategy.")
    as_of = _date(R.get("as_of"), "as_of") or date.today()
    stay = check_reprice(R, strategies)
    relist = check_relist(R, strategies, homes, stay, as_of)  # CMA-277
    warnings, warning_keys, warn = _warner()
    insurance = insurance_line(R, market)

    # comps: the script's time adjustments, then each adjusted value from its parts
    for i, c in enumerate(R["comps"]["cards"]):
        if not isinstance(c, dict) or not c.get("address") or not isinstance(c.get("adjustments"), list):
            raise ReportError(f"comps.cards[{i}] needs address, sold_price, seller_concessions and adjustments "
                              "([{label, amount}], empty when there are none): the script adds them up.")
    if not R["comps"]["cards"]:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    split = cma.default_split(R, homes)
    time_errors, time_info = cma.apply_time_adjustments(R["comps"], homes, R.get("as_of"), split)
    errors = cma.adjustment_kind_errors(R["comps"]["cards"]) + time_errors
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))
    except ValueError as e:
        raise ReportError(str(e)) from e
    history, history_errors = listing_history(R, homes, relist)
    errors += history_errors
    if errors:
        raise ReportError(stop_message(errors))
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))  # CMA-110
    warn("time_undated", *cma.time_warnings(time_info))
    cards = R["comps"]["cards"]
    values = [c["adjusted"] for c in cards]
    median_adjusted = statistics.median(values)
    address = s.get("mls_address", s["address"])

    # the export: market stats and the chart's points and trend (drawn once, by render and the deck alike)
    stats, st, pts = {}, None, None
    others = [h for h in homes if not mls.same_address(h["address"], address)]
    if others:
        st = mls.market_stats(homes, {**mls.subject_facts(homes, address), "address": address, "living_area": s["sqft"],
                                      "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision"),
                                      **({"property_type": s["property_type"]} if s.get("property_type") else {})},
                              split_date=R.get("split_date"), exclude_address=address, as_of=R.get("as_of"))
        recent = st["sold_recent"]
        stats = {k: v for k, v in {
            "split_date": st["window"]["split_date"],
            "sale_to_original_list_recent": recent.get("median_sale_to_original_list"),
            "sale_to_final_list_recent": recent.get("median_sale_to_final_list"),
            "median_days_recent": recent.get("median_days_on_market"),
            "share_with_seller_paid_costs_recent": recent.get("share_with_seller_paid_costs"),
            "median_seller_paid_recent": recent.get("median_seller_paid_when_paid"),
            "months_supply": st["months_supply_at_recent_pace"],
            "active_count": st["active_count"]}.items() if v is not None}
        pts = cma.scatter_points(homes, R.get("scatter") or {}, s["sqft"], address, [c["address"] for c in cards])
    fit = pts[2] if pts else None

    # expected sales: Stay's by its rule, the others by the one rule
    split_iso = (st or {}).get("window", {}).get("split_date")
    rule = stay_rule(R, homes, strategies[stay], median_adjusted, _date(split_iso, "split_date")) if stay is not None else None
    stay_filled = stay is not None and strategies[stay].get("expected_sale") is None
    if stay_filled:
        if not rule:
            raise ReportError("Stay at Current Price needs expected_sale as a number: without an MLS export there are no "
                              "sales to apply the rule to, so apply it to the sales you were given (method.md, A Reprice).")
        strategies[stay]["expected_sale"], strategies[stay]["expected_sale_source"] = rule["gross"], "stay_rule"
    competing = len(strategies) - 1 != ri and strategies[-1]["list_price"] < strategies[ri]["list_price"]
    basis = fill_expected_sales(R, strategies, stats, stay, competing)
    basis["split"] = split_iso
    for i, x in enumerate(strategies[:-1] if competing else strategies):  # CMA-20
        if x["expected_sale"] > x["list_price"]:
            raise ReportError(f"pricing.strategies[{i}] expects to sell at {money(x['expected_sale'])}, above its "
                              f"{money(x['list_price'])} list price. Only the competing-offer option (the last) can.")

    scope = cma.adjustment_scope_warning(market, s.get("county"), rec["list_price"])  # CMA-10
    if scope:
        warn("adjustment_scope", scope)
    if len(cards) < 3:
        warn("thin_comps", f"Only {len(cards)} comp{'s' if len(cards) > 1 else ''}: the range rests on thin support. Widen "
                           "the search if you can, and say so in the report.")
    if not rec["low"] <= rec["list_price"] <= rec["high"]:
        warn("list_outside_range", f"The recommended list price {money(rec['list_price'])} is outside the supported range "
                                   f"{fmt.range(rec['low'], rec['high'])}: move it inside, or widen the range and say why.")
    if strategies[ri]["list_price"] != rec["list_price"]:
        warn("list_mismatch", "The recommended strategy's list price doesn't match recommendation.list_price.")
    for x in strategies:
        if x["expected_sale"] > rec["high"]:
            warn("expected_above_range", f"The expected sale {money(x['expected_sale'])} is above the supported range: "
                                         "an appraisal risk to explain, or lower it.")
    for i, hi in enumerate(strategies):  # CMA-323: a higher list price never expects less than a lower one
        for j, lo in enumerate(strategies):
            if (stay not in (i, j) and hi["list_price"] > lo["list_price"] and hi["expected_sale"] < lo["expected_sale"]
                    and not (competing and j == len(strategies) - 1 and p.get("competing_offer_upside"))):
                warn("expected_sale_order", f"The {money(hi['list_price'])} option expects {money(hi['expected_sale'])}, "
                     f"below the {money(lo['list_price'])} option's {money(lo['expected_sale'])}. A higher list price "
                     f"sells at least as high, only slower: give it at least {money(lo['expected_sale'])}.")
    for key, text in cma.range_warnings(rec, values, market):  # CMA-296
        warn(key, text)

    # one closing per option, then the net sheet and the payments
    launch = launch_info(R, as_of)
    closings = option_closings(R, strategies, as_of, launch)
    net = net_sheet(R, market, strategies, closings, as_of)
    warn("title_quote", *dict.fromkeys(w for n in net["raw"] for w in n["warnings"]))
    missing = list(dict.fromkeys(MISSING_WORDS.get(m, m) for m in net["raw"][0]["missing"]))
    incomplete = bool({"listing fee", "buyer's agent fee"} & set(net["raw"][0]["missing"]))
    if incomplete:
        warn("no_brokerage", "No brokerage terms: the nets leave out the commission, so they'd overstate what the seller "
                             "walks away with. Ask the agent for the listing fee and buyer's agent compensation (0 is "
                             "fine) in costs, then re-run. render.py won't build the files until then.")
    if missing:
        warn("preliminary", "Preliminary: the market has no value for " + ", ".join(missing) +
             ". Ask the agent and re-run; the report is marked Preliminary until then.")
    costs_in = R.get("costs") or {}
    if costs_in.get("annual_tax") and not any(c["date"] for c in closings):
        warn("tax_no_closing_date", "costs.annual_tax is set but there's no closing date: add costs.expected_closing_date "
                                    "(or a closing_date per pricing option) to include the tax proration.")
    if market.get("county_overrides") and not s.get("county"):  # CMA-268
        warn("no_county", f"No county for this {market.state} home: closing costs here depend on the county (who pays the "
                          "owner's title policy, surtaxes), so the state's defaults were used. Take subject.county from "
                          "the listing or ask the agent, then re-run.")
    rows, totals, after = net_rows(net, strategies, closings)
    nets = after or totals  # CMA-7: compare the options after holding costs
    hint = state_hint(R, market, strategies, closings, as_of, ri, net)

    pay, _ = payments(R, market, insurance)
    bp = R["buyer_payment"]
    if bp.get("total_mills") is None and bp.get("district"):
        problem = finance.millage_row(market, s.get("county"), bp["district"])[1]
        if problem:
            warn("tax_problem", problem)
    if pay is None:
        warn("tax_no_rate", "No millage or tax rate for the buyer-payment estimate: give buyer_payment.school_mills and "
                            "total_mills (or a district in the built-in millage).")
    elif pay["tax_estimated"]:
        warn("tax_estimated", f"Buyer taxes are estimated at {pay['tax_basis']}; find the millage for the home's taxing "
                              "district if you can.")

    # the options
    reprice = R.get("reprice") or None
    strat = []
    for i, (x, c) in enumerate(zip(strategies, closings)):
        row = {"label": t("strategy_stay" if i == stay else "strategy_label", price=money(x["list_price"])),
               "list_price": x["list_price"], "list_price_display": money(x["list_price"]),
               "expected_sale": x["expected_sale"], "expected_sale_display": money(x["expected_sale"]),
               "expected_sale_source": x.get("expected_sale_source"), "time": str(x.get("time") or ""),
               "months_to_contract": c["months_to_contract"],
               "closing": c["date"].isoformat() if c["date"] else None,
               "closing_display": fmt.date_short(c["date"]) if c["date"] else None, "hold_months": c["hold_months"],
               "seller_credit": x.get("seller_credit", 0) or 0, "seller_credit_display": money(x.get("seller_credit", 0) or 0),
               "note": x.get("note", ""), "recommended": i == ri, "stay": i == stay,
               "net": totals[i], "net_display": money(totals[i]),
               "net_after_holding": nets[i], "net_after_holding_display": money(nets[i])}
        if pay:
            row.update(payment=pay["rows"][i]["payment"], payment_display=pay["rows"][i]["payment_display"],
                       down=pay["rows"][i]["down"], down_display=pay["rows"][i]["down_display"])
        d = nets[i] - nets[ri]
        row["net_vs_recommended"] = d
        row["net_vs_recommended_about"] = "" if i == ri else (
            L["about_same"] if abs(d) < 250 else t("about_more" if d > 0 else "about_less", amount=about(d)))
        strat.append(row)
    for i, x in enumerate(strat):  # CMA-280, CMA-290: an option that nets more than the recommended one
        if i == ri or nets[i] <= nets[ri]:
            continue
        if i == stay:
            warn("stay_nets_more", f"Stay at Current Price nets {about(nets[i] - nets[ri])} more than the recommended cut "
                 "after holding costs. Check its expected sale and its time; if it still nets more, say in pricing.note "
                 "that the cut buys time and certainty, not a higher net.")
        elif stay is None and x["list_price"] > strat[ri]["list_price"]:
            warn("top_nets_more", f"The {x['list_price_display']} option nets {about(nets[i] - nets[ri])} more than the "
                 "recommended one after holding costs. A top-of-range price takes longer and usually sells near the "
                 "middle of the range anyway (method.md): lower its expected sale or lengthen its time, or explain in "
                 "pricing.note.")
        elif x["list_price"] < strat[ri]["list_price"] and not p.get("competing_offer_upside"):
            warn("bottom_nets_more", f"The {x['list_price_display']} option nets {about(nets[i] - nets[ri])} more than the "
                 "recommended one after holding costs, though it only works if competing offers show up. Check its "
                 "expected sale and seller credit; if it still nets more, recommend it, or say in pricing.note that its "
                 "net depends on competing offers and set pricing.competing_offer_upside to true.")
    caveat = len(strat) - 1 if competing and nets[-1] > nets[ri] else None  # CMA-319
    for i, x in enumerate(strat):  # CMA-288
        if i not in (ri, stay) and 0 < x["list_price"] - strat[ri]["list_price"] <= NEAR_RECOMMENDED * strat[ri]["list_price"]:
            warn("top_near_recommended", f"The {x['list_price_display']} option is within 1% of the recommended "
                 f"{strat[ri]['list_price_display']}, so it isn't a distinct strategy"
                 + (f" (the relist cap at {money(relist['failed_price'])} leaves no room above it)" if relist else "")
                 + ". Drop it and set pricing.recommended_index to 0 (method.md, A Relist).")
    reprice_out = None
    if stay is not None:
        rp = R["reprice"]
        original = rp.get("original_price") or own_original(R, homes, ("ACTIVE", "PENDING"), rp["current_price"])
        original = original if original and original > rp["current_price"] else None
        reprice_out = {"current_price": rp["current_price"], "current_price_display": money(rp["current_price"]),
                       "days_on_market": rp["days_on_market"], "stay_index": stay, "original_price": original,
                       "original_price_display": money(original) if original else None}
        reprice_out["price_history"] = price_history(reprice=reprice_out)
        if rule:
            reprice_out.update(stay_expected_sale=rule["gross"], stay_expected_sale_display=money(rule["gross"]),
                               stay_ratio=rule["ratio"], stay_ratio_sales=rule["n"], stay_expected_filled=stay_filled)
            if strategies[stay]["expected_sale"] > rule["gross"]:
                warn("stay_expected_high", f"Stay at Current Price expects {money(strategies[stay]['expected_sale'])}, "
                     f"above {money(rule['gross'])} from the rule (method.md, A Reprice): use {money(rule['gross'])}, "
                     "or say in pricing.note why this listing would do better.")
    relist_out = ({**relist, "failed_price_display": money(relist["failed_price"]),
                   "original_price_display": money(relist["original_price"]) if relist["original_price"] else None,
                   "price_history": price_history(relist=relist)} if relist else None)

    # Preliminary: the reason from the data (costs the market is missing, no state) and/or report.json's own
    no_state = not market.state
    own = R.get("preliminary")
    reasons = ([L["prelim_no_state"]] if no_state else []) + (
        [t("prelim_costs", items=", ".join(missing))] if missing else []) + (
        [own.strip()] if isinstance(own, str) and own.strip() else
        [L["prelim_inputs"]] if own and not missing and not no_state else [])
    preliminary = bool(reasons)
    preliminary_reason = " ".join(r[0].upper() + r[1:] for r in reasons)
    preliminary_short = (L["prelim_short_no_state"] if no_state else L["prelim_short_costs"] if missing
                         else L["prelim_short_inputs"]) if preliminary else ""

    # the model
    best = strongest_comp(cards, rec["low"], rec["high"])
    shown = median_rounded(median_adjusted, len(values))
    pos_key = range_position(rec["list_price"], rec["low"], rec["high"])
    rw = labeler(bool(reprice_out))
    C = {"ok": True, "stage": "full", "sample": bool(R.get("sample")), "reprice_words": bool(reprice_out),
         "data_source": {"mls": market.mls, "as_of": as_of.isoformat(), "as_of_display": fmt.date_long(as_of),
                         "export": bool(homes)},
         "prepared_date": prepared_date(R.get("prepared_date"), as_of),
         "preliminary": preliminary, "preliminary_reason": preliminary_reason, "preliminary_short": preliminary_short,
         "median_adjusted": median_adjusted, "median_shown": shown, "median_adjusted_display": money(shown),
         "adjusted_min": min(values), "adjusted_max": max(values), "n_comps": len(cards)}
    C["subject"] = subject_model(s, costs_in)
    expected_rec = strategies[ri]["expected_sale"]
    C["recommendation"] = {
        "list_price": rec["list_price"], "list_price_display": money(rec["list_price"]), "low": rec["low"],
        "high": rec["high"], "range_display": fmt.range(rec["low"], rec["high"]),
        "range_k": fmt.range(rec["low"], rec["high"], fmt.k),
        "midpoint": rec.get("midpoint", (rec["low"] + rec["high"]) / 2),
        "expected_sale": expected_rec, "expected_sale_display": t("sum_expected_value", amount=money(expected_rec)),
        "expected_sub": L["deck_expected_sub" if expected_rec < rec["list_price"] else "deck_expected_sub_at"],
        "position": L[pos_key],
        "line": t("line_recommendation", low=money(rec["low"]), high=money(rec["high"]), median=money(shown),
                  price=money(rec["list_price"]), position=L[pos_key], vs=vs_median(rec["list_price"], shown)),
        "verdict": rw("verdict_price", price=money(rec["list_price"])),
        "caption": rw("verdict_caption", range=fmt.range(rec["low"], rec["high"])),
        "why": rec.get("why", "")}
    C["reprice"], C["relist"], C["listing_history"] = reprice_out, relist_out, history
    C["history_line"] = " ".join(e["text"] for e in history)
    C["price_history"] = (reprice_out or relist_out or {}).get("price_history")
    C["means"] = list(R.get("means") or [])
    card_models = comp_cards(cards, homes, best)
    highest = max(range(len(cards)), key=lambda i: (cards[i]["sold_price"], i))
    hi_card = card_models[highest]
    comps = R["comps"]
    C["comps"] = {
        "intro": comps.get("intro", ""), "count_line": comps_count_line(cards, homes, split),
        "method": cma.adjustment_summary(cards, time_info, money), "method_note": comps.get("method_note", ""),
        "cards": card_models, "lean": comps.get("lean", ""),
        "table": [[cma.display_address(r[0]), money(r[1]), money(r[2]), money(r[3])] for r in comps["summary_rows"]],
        "subject_row": [rw("subject_row"), money(rec["list_price"]), fmt.EMPTY, t("range_cell", range=C["recommendation"]["range_k"])],
        "summary_line": t("line_comps_summary", lo=money(min(values)), hi=money(max(values)), median=money(shown)),
        "strongest": {"index": best, "address": card_models[best]["address"],
                      "line": t("line_strongest", address=card_models[best]["address"])},
        "highest_line": t("line_highest", price=money(hi_card["sold_price"]), address=hi_card["address"],
                          when=t("line_highest_when", date=fmt.date_long(hi_card["close_date"])) if hi_card["close_date"] else "")}
    C["comps_table"] = [{"address": cma.display_address(r[0]), "sold_display": money(r[1]), "seller_paid_display": money(r[2]),
                         "adjusted_display": money(r[3])} for r in comps["summary_rows"]]
    C["time_adjustment"] = time_info
    C["scatter"] = scatter_model(R, s, pts, fit, rec, rw) if pts else None
    C["trend"] = ({"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
                   "r2_key": mls.r2_key(fit["r2"])} if fit else None)
    cp = R.get("competition") or {}
    comp_rows = cp.get("rows") or []
    for i, r in enumerate(comp_rows):
        if not isinstance(r, list) or len(r) < 7 or not all(isinstance(r[j], (int, float)) and not isinstance(r[j], bool)
                                                            for j in (2, 3)):
            raise ReportError(f"competition.rows[{i}] should be [address, status, price, sqft, pool, days, notes], with "
                              "price and sqft as plain numbers (474500, not \"$474,500\").")
    C["competition"] = {"intro": cp.get("intro", ""), "rows": [
        [cma.display_address(r[0]), str(r[1]), money(r[2]), fmt.num(r[3]), str(r[4]),
         fmt.num(r[5]) if isinstance(r[5], (int, float)) and not isinstance(r[5], bool) else str(r[5] or ""), r[6] or ""]
        for r in comp_rows]}
    C["market"] = market_section(st, R)
    if not C["market"] and (R.get("market") or {}).get("bullets"):
        C["market"] = {"intro": "", "columns": [], "rows": [], "periods": [], "cards": [],
                       "bullets": list(R["market"]["bullets"])}
    C["market_cards"] = (C["market"] or {}).get("cards") or comps_market_cards(R, cards)
    C["market_stats"] = stats
    C["window"] = (st or {}).get("window")
    C["n_sold"] = st["sold_all"]["n"] if st else None
    C["max_distance"] = max((h["distance"] for h in others if h["status"] == "SOLD" and h.get("distance") is not None),
                            default=None)
    C["strategies"], C["recommended_index"] = strat, ri
    C["launch"] = launch
    C["expected_sale_basis"] = {k: basis[k] for k in ("ratio", "ratio_display", "source", "filled", "agent", "capped",
                                                       "floored", "top")}
    C["net"] = {"rows": rows, "totals": totals, "after_holding": after, "holding": [r["amounts"] for r in rows
                                                                                      if r["key"] == "holding"][0] if after else None,
                "monthly": fmt.half_up(net["monthly"]) if net["holding"] else None,
                "cash_at_closing": net["cash"], "no_mortgage": net["no_mortgage"], "payoff": net["payoff"],
                "payoff_estimated": net["payoff_estimated"], "incomplete": incomplete, "missing": missing,
                "basis": "after_holding" if after else "net", "header": [s_["label"] for s_ in strat]}
    C["net_basis"] = C["net"]["basis"]
    C["net_spread"] = max(nets) - min(nets)
    C["net_spread_display"] = money(C["net_spread"])
    C["net_spread_about"] = about(C["net_spread"])
    C["recommended_net_display"] = strat[ri]["net_after_holding_display"]
    held = "_holding" if after else ""
    kind = "free" if net["no_mortgage"] else "cash" if net["cash"] else "net"
    C["options_summary"] = {"net_header": L["th_est_cash" if net["cash"] and not held else "th_est_net"],
                            "net_header_long": L["th_cash" if net["cash"] and not held else "th_net"],
                            "note": L[f"options_note_{kind}{held}"],
                            "net_tile": t(f"sum_{kind}_tile{held}", price=money(rec["list_price"])),
                            "net_sub": L[f"deck_{kind}{held}_sub"],
                            "spread_line": t("line_spread", lo=money(min(nets)), hi=money(max(nets)),
                                             spread=money(C["net_spread"])) if len(strat) > 1 else ""}
    C["payments"] = pay
    C["state_hint"] = hint
    C["competing_offer_caveat"] = caveat
    N = notes.Notes()
    add_notes(N, R, market, net, strategies, closings, basis, pay, as_of, stay, caveat, bool(reprice_out))
    if hint:
        N.add("state_unknown", t("note_state_unknown", mls=market.mls, state=hint["state_name"],
                                 line=hint["transfer_tax_label"], estimate=hint["estimate_label"],
                                 amount=hint["net_difference_about"],
                                 way=L["more" if hint["net_difference"] > 0 else "less"]), "chat_only")
    reply = [it for it in N.items("chat") if it[2] in REPLY_KINDS]
    C["notes"] = N.pdf()
    C["note_keys"] = [k for k, _, _ in N.items("chat")]
    C["assumptions"] = [text for _, text, _ in reply]
    C["assumption_keys"] = [k for k, _, _ in reply]
    C["chat_notes"] = [text for _, text, k in N.items("pdf") if k not in REPLY_KINDS]
    C["deck_notes"] = [N.get(k) for k in DECK_NOTE_KEYS if N.get(k)]
    C["pricing_intro"], C["pricing_note"] = p.get("intro", ""), p.get("note", "")
    C["prep"] = {"intro": (R.get("prep") or {}).get("intro", ""), "heading": rw("h_prep"),
                 "items": [{"step": str(it["step"]).strip(), "heading": prose.title_case(str(it["step"]).strip().rstrip(".")),
                            "detail": it.get("detail", ""), "short": it.get("short", ""), "icon": it.get("icon")}
                           for it in items]}
    C["needs"] = list(R.get("needs") or [])
    C["method"] = method_model(R, st, pay)
    C["notices"] = cma.report_notices(C)
    C["summary"] = summary_model(R, C, stats, rw)
    C["deck"] = deck_model(R, C) if R.get("deck") is not None else None
    C["handoff"] = handoff_model(R, s, market, rec, median_adjusted, stats, costs_in, as_of)
    problems = N.label_problems(all_labels(C))
    if problems:
        raise ReportError("These labels carry a note (a report says that once, in its notes): "
                          + "; ".join(f"{lbl!r} {why}" for lbl, why in problems) + ". Rename them.")
    C["warnings"], C["warning_keys"] = warnings, warning_keys
    # CMA-259: without an export nothing reads the MLS, so notes about which MLS (assumed, not built in) are noise
    known_layout = bool(homes) and not R.get("export_columns") and bool(market.get("mls_format.cma_export_columns"))
    kept = [(n, c) for n, c in zip(market.notes, market.note_codes)
            if (homes or c not in ("mls_assumed", "mls_not_built_in", "mls_not_given"))
            and not (known_layout and c == "mls_assumed")]
    C["market_notes"], C["market_note_keys"] = [n for n, _ in kept], [c for _, c in kept]
    C["_homes"], C["_points"] = homes, pts
    return C


# Plain words for costs the market doesn't have (not every state has each one)
MISSING_WORDS = {"deed transfer tax": "transfer tax (or confirmation there is none)", "HOA estoppel fee": "HOA documents fee",
                 "who pays owner's title": "who customarily pays the owner's title policy", "listing fee": "listing brokerage fee",
                 "buyer's agent fee": "buyer's agent compensation"}


def prepared_date(value, as_of):
    """The date on the report: a YYYY-MM-DD date written out, a date already written out as given, else the as-of date."""
    if value in (None, ""):
        return fmt.date_long(as_of)
    return fmt.date_long(value) if fmt.to_date(value) else str(value)


def subject_model(s, costs):
    """The home's facts: the script's (beds and baths, living area, the current tax bill) then the report's own (lot,
    built, pool, garage, HOA, flood zone, updates) as written; the page-1 facts line."""
    facts = []
    if s.get("beds") is not None and s.get("baths") is not None:
        facts.append([L["fact_beds"], t("fact_beds_value", beds=fmt.num(s["beds"]), baths=fmt.num(s["baths"], 1))])
    facts.append([L["fact_area"], t("fact_area_value", sqft=fmt.num(s["sqft"]))])
    if costs.get("annual_tax"):
        facts.append([L["fact_taxes"], t("fact_taxes_value", amount=money(costs["annual_tax"]))])
    mine = {str(f[0]).lower() for f in facts} | {"beds / baths", "living area"}
    facts += [[str(a), str(v)] for a, v in (s.get("facts") or []) if str(a).lower() not in mine][:10 - len(facts)]
    line = []
    if s.get("beds") is not None:
        line.append(t("hf_beds", n=fmt.num(s["beds"])))
    if s.get("baths") is not None:
        line.append(t("hf_baths", n=fmt.num(s["baths"], 1)))
    line.append(t("hf_sqft", n=fmt.num(s["sqft"])))
    if s.get("pool"):
        line.append(L["hf_pool"])
    if s.get("year_built"):
        line.append(t("hf_built", year=s["year_built"]))
    return {"address": s["address"], "locality": s.get("locality", ""), "facts": facts, "summary_facts": line,
            "summary": s.get("summary", ""), "mls_address": s.get("mls_address", s["address"]), "sqft": s["sqft"],
            "city": s.get("city"), "subdivision": s.get("subdivision")}


def scatter_model(R, s, pts, fit, rec, rw):
    """What the chart says in words: the script's intro and captions, the model's takeaway; the chart itself is drawn
    by render.py and the deck from these same points (cma.scatter_points)."""
    sc = R.get("scatter") or {}
    lo, hi = s["sqft"] * sc.get("min_size_ratio", 0.6), s["sqft"] * sc.get("max_size_ratio", 1.4)
    excluded = pts[1]
    parts = []
    for reason in ("size", "price"):
        n = sum(e[3] == reason for e in excluded)
        if n:
            parts.append(L[f"excluded_{reason}_one"] if n == 1 else t(f"excluded_{reason}_many",
                                                                    n=cma.number_word(n).capitalize() if n < 13 else fmt.num(n)))
    active = {" ".join(h["address"].upper().split()) for h in pts[0]["active"]}
    callouts = []
    for c in sc.get("callouts") or []:
        label = cma.display_address(c["address"])
        if " ".join(str(c["address"]).upper().split()) in active:
            label = t("callout_for_sale", address=label)
        callouts.append({"address": c["address"], "label": label, "side": c.get("side", "right")})
    out = {"heading": sc.get("heading") or L["h_scatter"],
           "intro": t("line_scatter_intro", lo=fmt.num(fmt.half_up(lo, 100)), hi=fmt.num(fmt.half_up(hi, 100))),
           "excluded": " ".join(parts), "takeaway": sc.get("takeaway", ""),
           "subject_label_pos": sc.get("subject_label_pos", "right"), "callouts": callouts,
           "subject_label": L["subject_label"],
           "ratios": {k: sc[k] for k in ("min_size_ratio", "max_size_ratio", "fit_size_ratio") if k in sc},
           "band_label": t("band_label", range=fmt.range(rec["low"], rec["high"], fmt.k)), "trend": None, "r2_line": ""}
    if fit:
        side, gap = cma.trend_position(rec["list_price"], fit["at_subject"])
        vals = {"price": money(rec["list_price"]), "gap": money(gap, 1000), "trend": fmt.k(fit["at_subject"])}
        out["trend"] = {"side": side, "head": t("trend_head_" + side, **vals),
                        "body": " ".join(x for x in (L["trend_caption"], L["trend_" + side]) if x),
                        "deck": t("deck_trend_" + side, **vals)}
        if fit.get("r2") is not None:
            out["r2_line"] = t("line_r2", share=L[mls.r2_key(fit["r2"])])
    return out


def method_model(R, st, pay):
    lines = []
    if st:
        w, counts = st["window"], st.get("status_counts") or {}
        ended = sum(v for k, v in counts.items() if k not in ("SOLD", "ACTIVE", "PENDING"))
        lines.append(t("line_sources_export", n=fmt.num(st["sold_all"]["n"]), first=fmt.date_short(w["first_close"]),
                       last=fmt.date_short(w["last_close"]),
                       listings=t("line_sources_listings", active=fmt.num(counts.get("ACTIVE", 0)),
                                  pending=fmt.num(counts.get("PENDING", 0)), ended=fmt.num(ended))))
    else:
        lines.append(L["line_sources_comps"])
    if pay and R["buyer_payment"].get("rate_week"):
        lines.append(t("line_sources_rate", rate=pay["rate_display"], date=fmt.date_long(R["buyer_payment"]["rate_week"])))
    if R.get("sources"):
        lines.append(t("line_sources_other", list=cma._and([str(x) for x in R["sources"]])))
    lines.append(L["line_shelf_life"])
    return {"lines": lines}


def summary_model(R, C, stats, rw):
    """Page 1: the model's headline, reasons and next step, with the script's key numbers, options table and first
    steps (the first three of prep.items)."""
    sp = R.get("summary_page") or {}
    tiles = key_stats(C, stats) + [[C["recommended_net_display"], C["options_summary"]["net_tile"]]]
    return {"label": sp.get("label") or L["sum_label"], "headline": sp.get("headline", ""), "tiles": tiles,
            "why": list(sp.get("why") or []), "next_step": sp.get("next_step", ""), "launch_line": C["launch"]["line"],
            "first_steps": [[it["heading"], it["short"]] for it in C["prep"]["items"][:3]],
            "first_heading": rw("sum_first"), "rec_label": rw("sum_rec"),
            "dot_label": rw("dot_rec", price=C["recommendation"]["list_price_display"]),
            "comps": [{"address": c["address"], "adjusted": c["adjusted"], "adjusted_k": c["adjusted_k"]}
                      for c in C["comps"]["cards"]]}


def deck_model(R, C):
    """The deck's wording (judgment, already checked figure-free) with the facts the slides add, from this model."""
    if not isinstance(R["deck"], dict):  # a deck file that can't be read: deck.py names it when the deck is built
        return {"content": None, "path": str(R["deck"])}
    d = R["deck"]
    s, rw = C["subject"], labeler(C["reprice_words"])
    where = ", ".join(x for x in (s.get("city"), (s.get("subdivision") or "").title() or None) if x)
    window, n_sold = C["window"], C["n_sold"]
    if window:
        month = fmt.MONTHS[fmt.to_date(window["first_close"]).month - 1]
        if C["max_distance"]:
            miles = -(-C["max_distance"] * 2 // 1) / 2
            sold_line = t("deck_sold_within", month=month, miles=L["deck_mile"] if miles == 1 else
                          t("deck_miles", n=fmt.num(miles, 1)))
        else:
            sold_line = t("deck_sold_since", month=month)
    else:
        sold_line = None
    basis = str(d.get("comps_basis") or "").strip()
    pay = C["payments"]
    one = all(len(m["values"]) == 1 for m in C["market_cards"])  # without an export's two periods: one value a card
    phases = {"now": L["tl_now"], "before": L["tl_before"], "after": L["tl_after"]}
    steps = [x for x in d.get("timeline") or [] if isinstance(x, list) and len(x) == 2]
    timeline = [[phases.get(str(w).lower(), str(w)), what] for w, what in steps if str(w).lower() in ("now", "before")]
    timeline.append([C["launch"]["short"], t("tl_go_live", price=C["recommendation"]["list_price_display"])])
    timeline += [[phases["after"], what] for w, what in steps if str(w).lower() == "after"]
    return {
        "title": t("deck_title", address=s["address"]),
        "subtitle": t("deck_subtitle", where=where) if where else L["deck_subtitle_plain"],
        "tagline": str(d.get("tagline") or ""),
        "sold_line": sold_line, "n_sold": n_sold,
        "step_comps": t("deck_step_comps_basis", basis=basis) if basis else L["deck_step_comps"],
        "adjusted_range": fmt.range(C["adjusted_min"], C["adjusted_max"], fmt.k),
        "market_subtitle": L["deck_market_sub_one"] if one else t("deck_market_sub", early=C["market"]["periods"][0],
                                                                    recent=C["market"]["periods"][1]),
        "market_one_period": one,
        "pay_sub": t("deck_pay_sub" if pay and (pay["homestead_applied"] or pay["tax_estimated"]) else "deck_pay_sub_no_homestead",
                     program=pay["program"] if pay["program"].isupper() else pay["program"].lower(),
                     down=pay["down_display"]) if pay else "",
        "per_10k_line": t("deck_per_10k", amount=pay["per_10k_display"]) if pay else "",
        "timeline": timeline,
        "launch_title": rw("deck_launch_title"), "rec_title": rw("deck_rec_title"), "rec_label": rw("deck_rec_label"),
        "dot_rec": rw("deck_dot_rec", price=C["recommendation"]["list_price_display"]),
        "series_subject": rw("deck_series_subject"),
        "strat_title": L[f"deck_strat_title_{len(C['strategies'])}"],
        "content": d,
    }


def handoff_model(R, s, market, rec, median_adjusted, stats, costs_in, as_of):
    bp_in = R.get("buyer_payment") or {}
    school_m, total_m, homestead = buyer_tax_rates(R, market) if bp_in else (None, None, None)
    hoa_flag = costs_in.get("hoa", s.get("hoa"))
    return handoff.build(
        side="seller", as_of=as_of.isoformat(), source="seller-cma",
        subject={**{k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                      "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"),
                                      "baths": s.get("baths"), "year_built": s.get("year_built"),
                                      "pool": s.get("pool")}.items() if v is not None},
                 **handoff.subject_facts(annual_tax=costs_in.get("annual_tax"), school_mills=school_m, total_mills=total_m,
                                         homestead=homestead,
                                         hoa_monthly=costs_in.get("hoa_monthly", 0 if hoa_flag is False else None),
                                         flood_zone=bp_in.get("flood_zone") or next((v for lbl, v in s.get("facts") or []
                                                                                     if str(lbl).lower() == "flood zone"), None),
                                         roof_year=s.get("roof_year"))},
        value={"low": rec["low"], "high": rec["high"], "midpoint": rec.get("midpoint", (rec["low"] + rec["high"]) / 2),
               "median_adjusted": median_adjusted},
        comps=[{"address": r[0], "sold_price": r[1], "seller_paid": r[2], "adjusted": r[3]}
               for r in R["comps"].get("summary_rows", [])],
        market=stats, recommended_list_price=rec["list_price"],
        market_profile={"state": market.state, "mls": market.mls})


def all_labels(C):
    """Every label the report prints (headings, headers, row names, tiles, facts), for N.label_problems."""
    out = [r[0] for r in C["subject"]["facts"]] + [x[1] for x in C["summary"]["tiles"]]
    out += [r["label"] for r in C["net"]["rows"]] + C["net"]["header"]
    out += [x["label"] for x in C["strategies"]]
    if C["market"]:
        out += C["market"]["columns"] + [r[0] for r in C["market"]["rows"]]
    for c in C["comps"]["cards"]:
        out += [ln[0] for ln in c["lines"]]
    out += [C["options_summary"]["net_header"], C["options_summary"]["net_tile"]]
    return [x for x in out if x]


def load_inputs(R, mls_name=None, data_file=None):
    """Market and MLS records for a report.json (`export` is the path to the MLS export CSV, `export_columns` its
    header map for an MLS that isn't built in). The MLS is `--mls`, else the report's `mls`, else the one built-in MLS
    covering the county (CMA-15). The report itself is never changed."""
    s = R.get("subject") or {}
    market = profiles.load_market(state=s.get("state"), county=s.get("county"), mls=mls_name or R.get("mls"))
    homes = mls.load(mls.resolve_export(R["export"], data_file), market, R.get("export_columns")) if R.get("export") else []
    mls.fill_distances(homes, s.get("mls_address", s.get("address")),
                       (s["latitude"], s["longitude"]) if s.get("latitude") and s.get("longitude") else None)
    return market, homes


def run(R, mls_name=None, data_file=None):
    """The document model from a report dict: render.py's compute step."""
    market, homes = load_inputs(R, mls_name, data_file)
    return compute(R, market, homes, data_file)


def public(C):
    """The model as JSON prints it: without the export's homes and chart points (render.py's own)."""
    return {k: v for k, v in C.items() if not k.startswith("_")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--out", help="where to write the .cma.json handoff (default: next to report.json, the working "
                                  "folder; never the outputs)")
    ap.add_argument("--mls", help="MLS name, as with stats.py (Stellar is built in)")
    a = ap.parse_args(argv)
    with open(a.report, encoding="utf-8") as f:
        R = json.load(f)
    try:
        result = run(R, a.mls, a.report)
        path = os.path.join(a.out or os.path.dirname(os.path.abspath(a.report)),
                            handoff.filename(R["subject"]["address"], "seller"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result["handoff"], f, indent=2)
        result["handoff_file"] = path
        result = public(result)
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError, OSError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
