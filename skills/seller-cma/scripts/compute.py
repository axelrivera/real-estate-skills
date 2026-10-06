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
import math
import os
import re
import statistics
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import choices, cma, finance, fmt, handoff, mls, notes, profiles, prose  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
with open(os.path.join(ASSETS, "labels.json"), encoding="utf-8") as _f:
    L = json.load(_f)
L.pop("_prose", None)

money = fmt.money
CONTRACT_TO_CLOSE_MONTHS = 1  # a typical financed contract-to-close period, after each option's time to contract
MONTH_DAYS = 30.44
TAX_BILL_MONTH = 10  # when a market doesn't say (`property_tax.bill_month`): from October a year's bill may be out
NEAR_RECOMMENDED = 0.01  # CMA-288: options within 1% of each other aren't distinct strategies: the script drops one
OPTION_STEP_MIN, OPTION_STEP_SHARE = 5000, 0.02  # one step between options: $5,000 or 2% of the price, the larger
# The options the script builds, by role: a new listing's are the three stances (method.md, The Pricing Options); a
# reprice keeps Stay at Current Price and its cuts; a relist a step above and below the recommended price
STANDARD_ROLES = cma.STANCES
LISTING_ROLES = {"standard": STANDARD_ROLES, "reprice": ("stay", "recommended", "competing"),
                 "relist": ("top", "recommended", "competing")}
ROLES = STANDARD_ROLES + ("stay", "top", "recommended", "competing")
OPTION_KEYS = ("time", "seller_credit", "note", "expected_sale", "closing_date", "months_to_contract")
# Each option's time to contract as shares of the market's recent median days on market (its low and high end, in weeks)
TIME_SPREAD = {"stay": (1.5, 3.0), "top": (1.5, 3.0), "recommended": (0.75, 1.5), "competing": (0.25, 0.75),
               "premium": (1.5, 3.0), "market": (0.75, 1.5), "draw_offers": (0.25, 0.75)}
ASSUMED_DAYS = 30  # without an export's days on market: about a month, stated in the notes
CREDIT_STEP = 500
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
    return fmt.fill(L[key], **kw)


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
    "recommendation.low": "the script sets the range from the adjusted comps (method.md, The Range): "
                          "leave it out, or put the agent's own range in range_override {low, high, reason}",
    "recommendation.high": "the script sets the range from the adjusted comps (method.md, The Range): "
                           "leave it out, or put the agent's own range in range_override {low, high, reason}",
    "recommendation.midpoint": "the script computes the range and its midpoint",
    "recommendation.list_price": "the script sets the list price from pricing.stance (method.md, Pricing Stance): pick "
                                 "the stance, or put the agent's own price in price_override {list_price, reason}",
    "pricing.strategies": "the script builds the options (one per stance; pricing.stance picks the recommended one): "
                          "an option's time, seller_credit or note (or the agent's own expected_sale) goes in "
                          "pricing.options.<role> (draw_offers, market, premium; a reprice: stay, recommended, "
                          "competing; a relist: top, recommended, competing), and the agent's own list price in "
                          "price_override {list_price, reason}",
    "pricing.recommended_index": "the script marks the recommended option (pricing.stance, or price_override)",
    "pricing.competing_offer_upside": "the notes add the competing-offer caveat on their own when that option nets more",
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
    "scatter.callouts[].label": "the script labels each callout from its address",
}

# Judgment fields: what the model writes in words. Each is checked figure-free (prose.figures): the script prints every
# count, price, percent and date itself, so a figure typed here could disagree with the one beside it.
JUDGMENT = (
    "subject.summary", "subject.facts[][0]", "summary_page.label", "summary_page.headline", "summary_page.why[]",
    "summary_page.next_step", "recommendation.why", "range_override.reason", "means[]", "comps.intro", "comps.method_note", "comps.lean",
    "comps.cards[].bullets[]", "comps.cards[].adjustments[].label", "scatter.heading", "scatter.takeaway",
    "competition.intro", "competition.rows[][6]", "market.bullets[]", "pricing.intro", "pricing.note",
    "pricing.stance_reason", "pricing.options.*.note", "price_override.reason", "prep.intro", "prep.items[].step",
    "prep.items[].detail", "prep.items[].short",
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
                text = re.sub(r"<[^>]+>", " ", v)
                found = prose.figures(text) + re.findall(r"\{\w*\}", v)
                if found:
                    out.append(f"{path}: has {', '.join(repr(x) for x in found)} → the report prints every count, price, "
                               "percent and date itself; write this in words, without the figure.")
                who = prose.people(text)
                if who:
                    out.append(f"{path}: has {', '.join(repr(x) for x in who)} → {prose.PEOPLE_FIX}.")
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

def reprice_info(R):
    """CMA-108: the agent's own listing priced again (`reprice`), checked: {current_price, days_on_market,
    original_price?, allow_increase?}, or None when this isn't a reprice. Its options are Stay at Current Price and cuts
    (build_options)."""
    rp = R.get("reprice")
    if not rp:
        return None
    if not isinstance(rp, dict) or not all(isinstance(rp.get(k), (int, float)) for k in ("current_price", "days_on_market")):
        raise ReportError("reprice needs current_price and days_on_market as numbers (the price that hasn't sold and how "
                          "long it has been listed).")
    if rp.get("original_price") is not None and not isinstance(rp["original_price"], (int, float)):
        raise ReportError("reprice.original_price should be a number: the price the listing started at (the export's "
                          "Original List Price).")
    return rp


def own_original(R, homes, statuses, price):
    """CMA-287: the Original List Price of the home's own export row with one of `statuses` at `price`, or None."""
    address = R["subject"].get("mls_address", R["subject"]["address"])
    return next((h["original_list_price"] for h in homes if h["status"] in statuses and h.get("current_price") == price
                 and h.get("original_list_price") and mls.same_address(h["address"], address)), None)


def relist_info(R, homes, rp, as_of):
    """CMA-277: a relist after the home's own listing expired, was canceled or withdrawn: report.json's `relist`, else
    the lowest-priced failed listing of the home in the export within the last year. No option lists above its failed
    price unless the agent gave a reason (`relist.reason_above`; build_options). Returns {failed_price, status,
    days_on_market, original_price, reason_above, source} or None. A reprice has its own rule."""
    if rp is not None:
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
    original = rl.get("original_price") if isinstance(rl.get("original_price"), (int, float)) else own_original(
        R, homes, FAILED, rl["failed_price"])
    return {"failed_price": rl["failed_price"], "status": rl.get("status"), "days_on_market": rl.get("days_on_market"),
            "original_price": original if original and original > rl["failed_price"] else None,
            "reason_above": str(rl.get("reason_above") or "").strip(), "source": source}


# --- the options, by rule: the stance's price, then a step above and below ---------------------------------------------

def price_override(R):
    """The agent's own list price, `price_override` {list_price, reason}: (price, reason, problems); (None, "", [])
    when there's none. The other options are built around it, and the report shows it as the agent's."""
    over = R.get("price_override")
    if over in (None, {}, False):
        return None, "", []
    fix = ('{"list_price": ..., "reason": "why, in words"}, only when the agent chose the price; otherwise leave it out '
           "and the script sets it from pricing.stance")
    if not isinstance(over, dict):
        return None, "", [f"price_override: should be {fix}."]
    price, why = over.get("list_price"), str(over.get("reason") or "").strip()
    errors = []
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        errors.append(f"price_override.list_price: {price!r} isn't a price → a plain number (469900), in {fix}.")
    if not why:
        errors.append("price_override.reason: missing → say in words (no figures) why the agent chose this price; the "
                      "report shows it as the agent's choice.")
    return (None, "", errors) if errors else (price, why, [])


def option_step(price):
    """One step between options: $5,000 or 2% of the price, whichever is larger."""
    return max(OPTION_STEP_MIN, OPTION_STEP_SHARE * price)


def stance_price(stance, low, high):
    """The stance's list price: its share of the range's width above the low end, on a search-bracket step inside the
    range (cma.list_price_at)."""
    return cma.list_price_at(low + cma.STANCE_SHARE[stance] * (high - low), low, high)


def distinct(a, b):
    """Two list prices are distinct strategies when more than 1% apart."""
    return abs(a - b) > NEAR_RECOMMENDED * min(a, b)


def stance_prices(low, high):
    """A new listing's three stance prices, from the range alone (the stance only picks the recommended one): Market
    Price at the middle, Premium at 75% of the width and Draw Offers at 25%, each on its search-bracket step
    (stance_price). Where snapping puts Premium or Draw Offers within 1% of Market Price (search brackets are $5,000
    apart, under 1% of a price over $500,000), it moves one step at a time away from Market Price while it stays inside
    the range; a range too narrow for that leaves them close, and standard_options merges them."""
    out = {s: stance_price(s, low, high) for s in STANDARD_ROLES}
    market = out["market"]
    for role, move in (("premium", lambda p: cma.bracket_price(cma.bracket_price(p + 1, "up"), "up")),
                       ("draw_offers", lambda p: cma.bracket_price(p - 1, "down"))):
        p = out[role]
        while not distinct(p, market) and low <= move(p) <= high:
            p = move(p)
        out[role] = p
    return out


def price_cap(rp, relist, low):
    """The highest list price the options may take: a reprice's cuts stay at least 1% under the current price (unless
    the agent asked to price it higher), a relist's options at or under the failed price (unless the agent gave a
    reason to go higher). On the search-bracket step just under that limit, or at the limit when that step falls below
    the range. Returns (cap, "reprice" | "relist") or (None, None)."""
    if rp and not rp.get("allow_increase"):
        limit, kind = rp["current_price"] * (1 - NEAR_RECOMMENDED), "reprice"
        exact = math.floor(limit / 100) * 100
    elif relist and not relist["reason_above"]:
        limit = exact = relist["failed_price"]
        kind = "relist"
    else:
        return None, None
    cap = cma.bracket_price(limit, "down")
    return (cap if cap >= low else exact), kind


def listing_kind(rp, relist):
    """"reprice", "relist" or "standard" (a new listing): which options the script builds (LISTING_ROLES)."""
    return "reprice" if rp else "relist" if relist else "standard"


def standard_options(stance, low, high, own):
    """A new listing's options (method.md, The Pricing Options): one per stance (stance_prices), the stance's the
    recommended one. The agent's own price takes the place of the stance option nearest it and is the recommended one.
    An option within 1% of one already kept (a narrow range) isn't a distinct strategy: it merges into that one, the
    recommended option kept first. Returns ([(role, price)] high to low, the recommended role, [(merged role, kept
    role)])."""
    prices = stance_prices(low, high)
    rec = stance
    if own is not None:
        # the nearest; between two at the same price (a narrow range), the one on the agent's price's side, so the
        # options keep their order (and their times) from the lowest price to the highest
        side = STANDARD_ROLES if own < prices["market"] else STANDARD_ROLES[::-1]
        rec = min(side, key=lambda s: abs(prices[s] - own))
        prices[rec] = own
    kept, merged = [(rec, prices[rec])], []
    for role in sorted((s for s in STANDARD_ROLES if s != rec), key=lambda s: abs(prices[s] - prices[rec])):
        into = next((r for r, p in kept if not distinct(prices[role], p)), None)
        if into:
            merged.append((role, into))
        else:
            kept.append((role, prices[role]))
    return sorted(kept, key=lambda x: -x[1]), rec, merged


def build_options(R, stance, low, high, rp, relist):
    """The options by rule (method.md, The Pricing Options). A new listing: one per stance (standard_options). A
    reprice or relist: the recommended price is the stance's (or the agent's price_override), then one step above it
    (top of the range: capped at the range's high end and at a relist's failed price; never on a reprice) and one below
    (competing offers: never under the range's low end); a reprice adds Stay at Current Price, its cuts at least 1%
    under it. An option within 1% of one already kept isn't a distinct strategy and is dropped (Stay is kept first, then
    the recommended price: when they meet, staying is the recommendation). Returns {options: [(role, list_price)] in
    print order, index: the recommended option's, rule: the rule's price for the stance, kind, agent_role: the role
    holding the agent's own price (or None), merged: [(merged role, kept role)]}."""
    own, _, errors = price_override(R)
    if errors:
        raise ReportError(stop_message(errors))
    listing = listing_kind(rp, relist)
    if listing == "standard":
        options, rec_role, merged = standard_options(stance, low, high, own)
        return {"options": options, "index": [r for r, _ in options].index(rec_role),
                "rule": stance_prices(low, high)[stance], "kind": listing,
                "agent_role": rec_role if own is not None else None, "merged": merged}
    cap, kind = price_cap(rp, relist, low)
    rule = stance_price(stance, low, high)
    if cap is not None:
        rule = min(rule, cap)
    if own is not None:
        if rp and (kind == "reprice" and own > rp["current_price"] * (1 - NEAR_RECOMMENDED)
                   or abs(own - rp["current_price"]) <= NEAR_RECOMMENDED * min(own, rp["current_price"])):
            raise ReportError(stop_message([
                f"price_override.list_price: {money(own)} isn't a cut from the current {money(rp['current_price'])} → a "
                "reprice offers Stay at Current Price and price changes of at least 1%: give a lower price (or leave "
                "price_override out to recommend by the stance), or set reprice.allow_increase if the agent asked to "
                "price it higher."]))
        if kind == "relist" and own > relist["failed_price"]:
            raise ReportError(stop_message([
                f"price_override.list_price: {money(own)} is above {money(relist['failed_price'])}, where this home's "
                "earlier listing ended unsold → no option lists above a price the market already turned down: give a "
                "price at or under it, or the agent's reason to go higher in relist.reason_above (method.md, A Relist)."]))
    elif rule < low:
        rng = fmt.range(low, high)
        raise ReportError(stop_message([
            f"reprice: the current {money(rp['current_price'])} leaves no cut inside the supported range {rng} → give the "
            "agent's own price in price_override {list_price, reason}, or set reprice.allow_increase if the agent asked "
            "to price it higher." if kind == "reprice" else
            f"relist: this home's earlier listing ended unsold at {money(relist['failed_price'])}, under the supported "
            f"range {rng} → if the market or the home changed since, give the agent's reason in relist.reason_above "
            "(method.md, A Relist), or the agent's own price in price_override {list_price, reason}."]))
    rec = own if own is not None else rule
    step = option_step(rec)
    top = min(cma.bracket_price(rec + step), cma.bracket_price(high, "down"), cap if kind == "relist" else math.inf)
    competing = max(cma.bracket_price(rec - step), cma.bracket_price(low, "up"))
    wanted = ([("stay", rp["current_price"])] if rp else []) + [("recommended", rec)] + (
        [("top", top)] if not rp and top > rec else []) + ([("competing", competing)] if competing < rec else [])
    kept = []
    for role, price in wanted:
        if all(abs(price - p) > NEAR_RECOMMENDED * min(price, p) for _, p in kept):
            kept.append((role, price))
    options = [x for x in kept if x[0] == "stay"] + sorted((x for x in kept if x[0] != "stay"), key=lambda x: -x[1])
    roles = [r for r, _ in options]
    return {"options": options, "index": roles.index("recommended" if "recommended" in roles else "stay"),
            "rule": rule, "kind": listing, "agent_role": "recommended" if own is not None else None, "merged": []}


def role_problems(given, kind):
    """pricing.options keys that belong to another kind of listing (a new listing's options are the stances; a
    reprice's stay, recommended and competing; a relist's top, recommended and competing). A role of this kind the
    script didn't build this time (merged in a narrow range) is simply not used."""
    roles = LISTING_ROLES[kind]
    words = {"standard": "a new listing", "reprice": "a reprice", "relist": "a relist"}[kind]
    return [f"pricing.options.{role}: isn't an option of {words} → use {', '.join(roles[:-1])} or {roles[-1]}."
            for role in given
            if role in ROLES and role not in roles]


def option_inputs(R):
    """The model's per-option values, pricing.options.<role> (time, seller_credit, note, or the agent's own
    expected_sale, closing_date, months_to_contract): (options, problems). Roles of another kind of listing are caught
    once the script knows which kind this is (role_problems)."""
    opts = (R.get("pricing") or {}).get("options")
    if opts in (None, {}):
        return {}, []
    if not isinstance(opts, dict):
        return {}, ["pricing.options: should be {role: {time, seller_credit, note}} → keyed by draw_offers, market or "
                    "premium (a reprice: stay, recommended, competing; a relist: top, recommended, competing); leave it "
                    "out for the script's values."]
    errors = []
    for role, v in opts.items():
        if role not in ROLES:
            errors.append(f"pricing.options.{role}: isn't an option the script builds → use draw_offers, market or "
                          "premium (a reprice: stay, recommended, competing; a relist: top, recommended, competing).")
            continue
        if not isinstance(v, dict):
            errors.append(f"pricing.options.{role}: should be an object → {{time, seller_credit, note}}.")
            continue
        for k in v:
            if k not in OPTION_KEYS:
                errors.append(f"pricing.options.{role}.{k}: isn't read → give only {', '.join(OPTION_KEYS)} (the list "
                              "price is the script's: the agent's own goes in price_override).")
        for k in ("seller_credit", "expected_sale", "months_to_contract"):
            if v.get(k) is not None and (not isinstance(v[k], (int, float)) or isinstance(v[k], bool)):
                errors.append(f"pricing.options.{role}.{k}: {v[k]!r} isn't a number → a plain number, or leave it out "
                              "for the script's.")
    return opts, errors


def option_defaults(stats, cards):
    """The script's time to contract and seller credit for the options: the time from the market's recent median days
    on market (Premium, top of range and Stay slower, Draw Offers and competing faster), as a range of weeks; the credit is the recent share of
    sales with seller-paid costs times their median amount, to $500 (the comps' without an export). Returns {time:
    {role: text}, credit, days, days_assumed}."""
    days = stats.get("median_days_recent")
    assumed = days is None
    days = ASSUMED_DAYS if assumed else days
    times = {}
    for role, (a, b) in TIME_SPREAD.items():
        lo = max(1, fmt.half_up(days * a / 7))
        times[role] = t("opt_time_weeks", lo=fmt.num(lo), hi=fmt.num(max(lo + 1, fmt.half_up(days * b / 7))))
    share, amount = stats.get("share_with_seller_paid_costs_recent"), stats.get("median_seller_paid_recent")
    if share is None:
        paid = [c.get("seller_concessions") for c in cards if c.get("seller_concessions")]
        share, amount = (len(paid) / len(cards) if cards else 0), (statistics.median(paid) if paid else 0)
    return {"time": times, "credit": fmt.half_up(share * (amount or 0), CREDIT_STEP), "days": days,
            "days_assumed": assumed}


def option_values(built, given, defaults):
    """Each option as the net sheet reads it, {role, name, list_price, time, seller_credit, note, agent}: the script's
    defaults, with the model's pricing.options.<role> in place of any value it gives (and the agent's own expected_sale,
    closing_date or months_to_contract when given). A new listing's options are named for their stance (the agent's own
    price: Our Price); a reprice's and a relist's by their price alone."""
    out = []
    for role, price in built["options"]:
        g = given.get(role) or {}
        agent = role == built["agent_role"]
        name = (L["option_agent"] if agent else L["stance_" + role]) if built["kind"] == "standard" else ""
        x = {"role": role, "name": name, "agent": agent, "list_price": price, "time": defaults["time"][role],
             "seller_credit": defaults["credit"], "note": L["opt_note_agent" if agent and name else "opt_note_" + role],
             "time_source": "rule"}
        for k in OPTION_KEYS:
            if g.get(k) not in (None, ""):
                x[k] = g[k]
        if g.get("time") not in (None, "") or g.get("months_to_contract") is not None:
            x["time_source"] = "agent"
        out.append(x)
    return out


def market_numbers(R, homes):
    """The export's market stats for the report (mls.market_stats, without the home's own rows) and the few the
    options, the expected sales and the handoff use: ({key: value}, the full stats or None without other homes)."""
    s = R["subject"]
    address = s.get("mls_address", s["address"])
    if not any(not mls.same_address(h["address"], address) for h in homes):
        return {}, None
    st = mls.market_stats(homes, {**mls.subject_facts(homes, address), "address": address, "living_area": s["sqft"],
                                  "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision"),
                                  **({"property_type": s["property_type"]} if s.get("property_type") else {})},
                          split_date=R.get("split_date"), exclude_address=address, as_of=R.get("as_of"))
    recent = st["sold_recent"]
    return {k: v for k, v in {
        "split_date": st["window"]["split_date"],
        "sale_to_original_list_recent": recent.get("median_sale_to_original_list"),
        "sale_to_final_list_recent": recent.get("median_sale_to_final_list"),
        "median_days_recent": recent.get("median_days_on_market"),
        "share_with_seller_paid_costs_recent": recent.get("share_with_seller_paid_costs"),
        "median_seller_paid_recent": recent.get("median_seller_paid_when_paid"),
        "months_supply": st["months_supply_at_recent_pace"],
        "active_count": st["active_count"],
        "active_share_with_price_cut": st["active_share_with_price_cut"] if st["active_count"] else None}.items()
        if v is not None}, st


def pick_stance(R, stats, failed, own):
    """The pricing stance: the model's pricing.stance (choices.pick), the market data's suggestion when it's left out.
    Returns (stance, suggested, signals, reason, problems): a stance that differs from the suggestion needs
    pricing.stance_reason (unless the agent set the price: price_override's reason says why)."""
    p = R.get("pricing") or {}
    suggested, signals = cma.suggest_stance(stats, failed)
    stance, problems = choices.pick(p.get("stance"), cma.STANCES, "pricing.stance", default=suggested)
    reason = str(p.get("stance_reason") or "").strip()
    if stance != suggested and not reason and own is None:
        problems.append(f"pricing.stance_reason: missing → the market data suggests {suggested}: say in words (no figures) "
                        f"why this home takes {stance} instead, or leave pricing.stance out.")
    return stance, suggested, signals, reason, problems


def stance_facts(stats):
    """Each market number in words, by the signal it can show ({signal: words}): supply for supply_high and
    supply_low, the price-cut share for price_cuts, and the sale-to-list ratio for sale_below_list and sale_at_list
    (against the final asking price when the export carries it, else the original one, the only ratio then known)."""
    words = {}
    if stats.get("months_supply") is not None:
        words["supply_high"] = words["supply_low"] = t("stance_fact_supply", months=fmt.months(stats["months_supply"]))
    if stats.get("active_share_with_price_cut") is not None:
        words["price_cuts"] = t("stance_fact_cuts", share=fmt.pct(stats["active_share_with_price_cut"], 0))
    if stats.get("sale_to_final_list_recent") is not None:
        words["sale_below_list"] = words["sale_at_list"] = t(
            "stance_fact_ratio", ratio=fmt.pct(stats["sale_to_final_list_recent"], 1, fixed=True))
    elif stats.get("sale_to_original_list_recent") is not None:
        words["sale_at_list"] = t("stance_fact_ratio_original",
                                  ratio=fmt.pct(stats["sale_to_original_list_recent"], 1, fixed=True))
    return words


def stance_data_line(suggested, signals, stats, failed):
    """The sentence on the market numbers behind the suggestion, true for any data: a suggested Draw Offers or Premium
    names only the signals that suggested it (and, for Draw Offers, any premium signal that also shows: low supply
    beside widespread price cuts); a suggested Market Price lists the numbers known, which by the thresholds call for
    neither, or says a reprice or relist set Premium aside."""
    words, shown = stance_facts(stats), cma.stance_signals(stats)
    to = L["stance_" + suggested]
    if signals:
        facts = cma._and(list(dict.fromkeys(words[k] for k in signals)))
        against = [words[k] for k in cma.PREMIUM_SIGNALS if k in shown] if suggested == "draw_offers" else []
        if against:
            return t("line_stance_data_despite", facts=facts, suggested=to, against=cma._and(against))
        return t("line_stance_data", facts=facts, suggested=to)
    if failed and all(k in shown for k in cma.PREMIUM_SIGNALS):
        return t("line_stance_failed", facts=cma._and([words[k] for k in cma.PREMIUM_SIGNALS]), suggested=to,
                 premium=L["stance_premium"])
    known = list(dict.fromkeys(words.values()))
    if known:
        return t("line_stance_neither", facts=cma._and(known), suggested=to, draw=L["stance_draw_offers"],
                 premium=L["stance_premium"])
    return t("line_stance_no_data", suggested=to)


def stance_model(stance, suggested, signals, reason, stats, rule, own, own_reason, failed=False):
    """The stance as the report shows it: its name as a plain label, the script's sentence for it, the market numbers
    behind the suggestion (stance_data_line), the model's reason, and an agent's own price said beside the method's."""
    name = L["stance_" + stance]
    parts = [t("line_stance", name=name, what=L["stance_line_" + stance]),
             stance_data_line(suggested, signals, stats, failed)]
    if reason:
        parts.append(end_sentence(reason[0].upper() + reason[1:]))
    if own is not None:
        parts.append(t("line_price_override", rule=money(rule), name=name,
                       reason=end_sentence(own_reason)))
    return {"value": stance, "suggested": suggested, "signals": signals, "reason": reason, "name": name,
            "differs": stance != suggested, "rule_price": rule, "rule_price_display": money(rule),
            "agent_price": own is not None, "line": " ".join(parts)}


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
    """Each option's expected sale by one rule, so options that differ in price differ in expected sale: its list
    price times ONE ratio, plus its own seller credit, to the nearest $500.

    The ratio is the recent sale-to-FINAL-list (net of seller-paid costs): the export's when it carries final list
    prices; else `market.sale_to_list`; else, with an export, its sale-to-original-list when that's at least the 97%
    assumption (a final price is never above the original one, so the final ratio is at least that); else 97%
    assumed. When that ratio would put an option listed inside the supported range under the range, the ratio is
    raised for every option to the one that puts it at the range's low end: the comps (already net of seller credits)
    say the home is worth at least that, and one ratio keeps every option's place, where clamping each option to the
    floor would give two prices the same sale. Never above its list price (except the competing-offer option, the
    last) or the top of the range. Then by list price a higher price expects at least $500 more than a lower one (for
    an agent's own figure or credit in between), and a lower one at least $500 less than a higher one's rule figure (a
    market selling over list). An expected_sale in pricing.options is the agent's figure and is kept. Fills the
    strategies in place; returns the basis for the note."""
    m = R.get("market") or {}
    original = stats.get("sale_to_original_list_recent")
    if stats.get("sale_to_final_list_recent"):
        ratio, source = stats["sale_to_final_list_recent"], "export"
    elif isinstance(m.get("sale_to_list"), (int, float)) and 0.5 < m["sale_to_list"] <= 1.2:
        ratio, source = m["sale_to_list"], "report"
    elif original is not None and original >= ASSUMED_SALE_TO_LIST:
        ratio, source = original, "export_original"
    else:
        ratio, source = ASSUMED_SALE_TO_LIST, "assumed"
    low, high, last = R["recommendation"]["low"], R["recommendation"]["high"], len(strategies) - 1
    filled = [i for i, x in enumerate(strategies) if i != stay and x.get("expected_sale") is None]
    agent = [i for i, x in enumerate(strategies) if i != stay and i not in filled]
    cap = {i: high if competing and i == last else min(high, strategies[i]["list_price"]) for i in filled}
    credit = {i: strategies[i].get("seller_credit") or 0 for i in filled}
    # the ratio each option inside the range needs to sell at the range's low end; the highest need sets the one ratio
    need = {i: (low - credit[i]) / strategies[i]["list_price"] for i in filled if cap[i] >= low}
    neediest = max(need, key=need.get, default=None)
    raised_by = neediest if neediest is not None and need[neediest] > ratio else None
    used = need[raised_by] if raised_by is not None else ratio
    capped = False
    for i in filled:
        x = strategies[i]
        v = fmt.half_up(x["list_price"] * used + credit[i], EXPECTED_STEP)
        if i in need:
            v = max(v, low)  # the $500 rounding never takes the raised option back under the range
        capped |= v > cap[i]
        x["expected_sale"], x["expected_sale_source"] = min(v, cap[i]), "rule"
    order = sorted((i for i in range(len(strategies)) if i != stay), key=lambda i: strategies[i]["list_price"])
    floor = -math.inf  # low to high: a higher price expects more than a lower one, by at least a rounding step
    for i in order:
        x = strategies[i]
        if i in filled and x["expected_sale"] < floor + EXPECTED_STEP:
            x["expected_sale"] = min(floor + EXPECTED_STEP, cap[i])
        floor = max(floor, x["expected_sale"])
    # and high to low: a lower price expects less than a higher one's rule figure (a market selling over list); the
    # agent's own figures are kept as given, and warned on when out of order
    ceiling = math.inf
    for i in reversed([i for i in order if i in filled]):
        x = strategies[i]
        x["expected_sale"] = min(x["expected_sale"], ceiling - EXPECTED_STEP)
        ceiling = x["expected_sale"]
    for i in agent:
        strategies[i]["expected_sale_source"] = "agent"
    return {"ratio": used, "ratio_display": fmt.pct(used, 1, fixed=True), "market_ratio": ratio,
            "market_ratio_display": fmt.pct(ratio, 1, fixed=True), "source": source, "filled": filled,
            "agent": agent, "capped": capped, "raised_by": raised_by}


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


def goal_misses(R, closings):
    """The options (indexes) whose closing falls after the seller's goal, costs.expected_closing_date; none without
    one."""
    goal = _date((R.get("costs") or {}).get("expected_closing_date"), "expected_closing_date")
    return [i for i, c in enumerate(closings) if goal and c["date"] and c["date"] > goal]


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


def net_sheet(R, market, strategies, closings, as_of, ri):
    """Each option's money as a finance.Ledger at its expected sale: the costs (finance.seller_net), this year's whole
    tax bill when an option closes next year, the payoff, then the holding costs from the report date to that option's
    closing. Every line is rounded once; every total is a sum of the printed lines. The monthly holding cost is one
    figure for every option, on one basis: the recommended option's (`ri`) list price for the part that depends on a
    price (insurance), the deal's own facts for the rest (payoff, rate, HOA, utilities), so the options' order never
    changes it."""
    costs, s = R.get("costs") or {}, R["subject"]
    lf, bf = _frac(costs, "listing_fee_pct", "costs"), _frac(costs, "buyer_broker_fee_pct", "costs")
    others = costs.get("other") or []
    payoff, payoff_est = payoff_of(costs)
    has_hoa = bool(costs.get("hoa", s.get("hoa", False)))
    annual_tax, bill_paid = costs.get("annual_tax"), costs.get("current_tax_bill_paid")
    loan_rate = costs["mortgage_rate"] / 100 if costs.get("mortgage_rate") else finance.PAYOFF_INTEREST
    basis_price = strategies[ri]["list_price"]
    monthly, left_out = finance.holding_monthly(basis_price, market, payoff, costs.get("hoa_monthly"), loan_rate)
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
            "left_out": left_out, "holding": holding, "loan_rate": loan_rate, "basis_price": basis_price,
            "next_year": next_year, "cash": payoff is not None, "no_mortgage": payoff == 0}


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
    alt = net_sheet(R, other, strategies, closings, as_of, ri)
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

def add_notes(N, R, market, net, strategies, closings, basis, pay, as_of, stay, competing_caveat, reprice, defaults,
              stay_caveat=False):
    """Every assumption, estimate and caveat behind the figures, each once (notes.Notes)."""
    costs = R.get("costs") or {}
    leds, raw = net["ledgers"], net["raw"]
    first = raw[0]
    assumed = {a["key"]: a for a in first["assumed"]}
    # the options' times and seller credit, when they're the script's: what they rest on, once
    if any(x["time_source"] == "rule" for x in strategies):
        if defaults["days_assumed"]:
            N.add("option_time", L["note_option_time_assumed"], "assumption")
        else:
            N.add("option_time", t("note_option_time", days=fmt.num(defaults["days"])), "estimate")
    if any("seller_credit" not in (((R.get("pricing") or {}).get("options") or {}).get(x["role"]) or {}) for x in strategies):
        N.add("option_credit", t("note_option_credit", credit=money(defaults["credit"])) if defaults["credit"]
              else L["note_option_credit_none"], "estimate")
    # what the expected sales rest on: once, here (never also under the pricing table or in the method)
    if basis["filled"]:
        parts = [t("note_expected_" + basis["source"], ratio=basis["market_ratio_display"],
                   since=cma.day_words(fmt.to_date(basis["split"])) if basis.get("split") else "")]
        if basis["raised_by"] is not None:
            parts.append(t("note_expected_raised", price=money(strategies[basis["raised_by"]]["list_price"]),
                           ratio=basis["ratio_display"]))
        if basis["capped"]:
            parts.append(L["note_expected_limits_competing" if strategies[-1]["role"] == "competing"
                           else "note_expected_limits"])
        N.add("expected_sale", " ".join(parts), "assumption" if basis["source"] == "assumed" else "estimate")
    if basis["agent"]:
        prices = cma._and([money(strategies[i]["list_price"]) for i in basis["agent"]])
        N.add("expected_agent", t("note_expected_agent" if len(basis["agent"]) == 1 else "note_expected_agent_many",
                                  prices=prices), "info")
    if stay is not None and strategies[stay].get("expected_sale_source") == "stay_rule":
        N.add("expected_stay", L["note_expected_stay"], "estimate")
    if competing_caveat is not None:
        N.add("competing", t("note_competing", price=money(strategies[competing_caveat]["list_price"])), "info")
    if stay_caveat:
        N.add("stay_caveat", t("note_stay_caveat", price=money(strategies[stay]["list_price"])), "info")
    if net["holding"]:
        parts = []
        if net["payoff"]:
            parts.append(t("note_holding_loan_rate" if costs.get("mortgage_rate") else "note_holding_loan_assumed",
                           rate=fmt.pct(net["loan_rate"], 2), payoff=money(net["payoff"])))
        if costs.get("hoa_monthly"):
            parts.append(L["note_holding_hoa"])
        parts += [t("note_holding_" + p, price=money(net["basis_price"])) for p in ("insurance", "utilities")
                  if p not in net["left_out"]]
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
    late = goal_misses(R, closings)  # the seller's closing goal, said once for every option that closes after it
    if late:
        goal = fmt.date_short(_date(costs["expected_closing_date"], "expected_closing_date"))
        N.add("closing_goal", t("note_goal_after" if len(late) == 1 else "note_goal_after_many",
                                options=cma._and([money(strategies[i]["list_price"]) for i in late]),
                                dates=cma._and([fmt.date_short(closings[i]["date"]) for i in late]), goal=goal), "info")
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

def prepare_comps(R, homes, warn, market):
    """Condition adjustments (the condition ladder) and time adjustments by the shared rules, then each adjusted value
    from its parts (cma.derive_comps). Returns (the market split, time info, condition info)."""
    for i, c in enumerate(R["comps"]["cards"]):
        if not isinstance(c, dict) or not c.get("address") or not isinstance(c.get("adjustments"), list):
            raise ReportError(f"comps.cards[{i}] needs address, sold_price, seller_concessions, condition and adjustments "
                              "([{label, amount}], empty when there are none): the script adds them up.")
    if not R["comps"]["cards"]:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    split = cma.default_split(R, homes)
    cond_errors, cond_info = cma.apply_condition_adjustments(R["comps"], R["subject"], market)
    time_errors, time_info = cma.apply_time_adjustments(R["comps"], homes, R.get("as_of"), split)
    errors = cma.adjustment_kind_errors(R["comps"]["cards"]) + cond_errors + time_errors
    if errors:
        raise ReportError(stop_message(errors))
    try:
        warn("derive_comps", *cma.derive_comps(R["comps"]))
    except ValueError as e:
        raise ReportError(str(e)) from e
    return split, time_info, cond_info


def supported_range(R, values, market):
    """The range by the shared rule (cma.choose_range), or the agent's range_override, written into the working copy's
    recommendation so every figure after it uses the one range. Returns resolve_range's dict."""
    rng, errors = cma.resolve_range(values, market, R.get("range_override"))
    if errors:
        raise ReportError(stop_message(errors))
    rec = R.setdefault("recommendation", {})
    rec["low"], rec["high"] = rng["low"], rng["high"]
    return rng


def end_sentence(text):
    """A final period for wording that completes a sentence, when it has none."""
    s = str(text or "").rstrip()
    return s if not s or re.search(r"[.!?][\"')\]]*$", re.sub(r"<[^>]+>", "", s)) else s + "."


def comps_first(R, market, homes=()):
    """The adjusted comps and the supported range alone, before any pricing exists: the median, the spread, the range
    the list price and the options are chosen inside, and the outlier and adjustment warnings. Writes no handoff."""
    R = copy.deepcopy(R)
    _require(R, "subject.address", "comps.cards")
    errors = schema_errors({k: v for k, v in R.items() if k != "deck"})
    if errors:
        raise ReportError(stop_message(errors))
    warnings, warning_keys, warn = _warner()
    prepare_comps(R, homes, warn, market)
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))
    values = [c["adjusted"] for c in R["comps"]["cards"]]
    median_adjusted = statistics.median(values)
    rng = supported_range(R, values, market)
    for key, text in cma.range_warnings(rng, values, market):
        warn(key, text)
    # the stance the market data suggests, and the list price each stance sets here (the options are built from it)
    stats, _ = market_numbers(R, homes)
    as_of = _date(R.get("as_of"), "as_of") or date.today()
    rp = reprice_info(R)
    relist = relist_info(R, homes, rp, as_of)
    suggested, signals = cma.suggest_stance(stats, rp is not None or relist is not None)
    prices = {}
    for stance in cma.STANCES:
        try:
            built = build_options({k: v for k, v in R.items() if k != "price_override"}, stance, rng["low"],
                                  rng["high"], rp, relist)
            price = built["options"][built["index"]][1]
            prices[stance] = {"list_price": price, "list_price_display": money(price),
                              "options": [money(p) for _, p in built["options"]]}
        except ReportError as e:
            prices[stance] = {"problem": str(e)}
    return {
        "ok": True, "stage": "comps",
        "next": "Pick pricing.stance (or leave it out for the suggestion; a different one needs pricing.stance_reason), "
                "add costs and buyer_payment, then run compute.py again for the options, the nets, the payments and "
                "the handoff.",
        "stance": {"suggested": suggested, "signals": signals, "prices": prices},
        "subject": {"address": R["subject"]["address"]},
        "median_adjusted": median_adjusted,
        "median_adjusted_display": money(median_rounded(median_adjusted, len(values))),
        "adjusted_min": min(values), "adjusted_max": max(values),
        "range": {"low": rng["low"], "high": rng["high"], "display": fmt.range(rng["low"], rng["high"]),
                  "override": rng["override"]},
        "comps_table": [{"address": cma.display_address(r[0]), "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in R["comps"].get("summary_rows", [])],
        "warnings": warnings, "warning_keys": warning_keys, "market_notes": market.notes,
    }


def compute(R, market, homes, data_file=None):
    """The document model from report.json (never changed), the market and the export's homes."""
    R = copy.deepcopy(R)
    content = deck_content(R, data_file)
    if R.get("deck") is not None:
        R["deck"] = content if content is not None else R["deck"]
    errors = schema_errors(R if content is not None else {k: v for k, v in R.items() if k != "deck"})
    if errors:
        raise ReportError(stop_message(errors))
    _require(R, "subject.address", "subject.sqft", "comps.cards", "buyer_payment.rate")
    for block in ("costs", "buyer_payment"):  # units before any math: fractions stay fractions, interest stays a percent
        try:
            finance.check_units(R.get(block) or {}, block)
        except ValueError as e:
            raise ReportError(str(e)) from e
    market = market.with_deal(R.get("costs"))  # this listing's own numbers (a title quote, the state's transfer tax)
    if R.get("pricing") is not None and not isinstance(R["pricing"], dict):
        raise ReportError("pricing: should be an object → {stance, stance_reason, intro, note, options}.")
    p = R.setdefault("pricing", {})
    s = R["subject"]
    given, option_errors = option_inputs(R)
    items = (R.get("prep") or {}).get("items") or []
    for i, it in enumerate(items):
        if not (isinstance(it, dict) and str(it.get("step") or "").strip()):
            raise ReportError(f"prep.items[{i}] needs step (a few words), detail and short.")
    as_of = _date(R.get("as_of"), "as_of") or date.today()
    rp = reprice_info(R)
    relist = relist_info(R, homes, rp, as_of)  # CMA-277
    warnings, warning_keys, warn = _warner()

    # comps: the script's condition and time adjustments, then each adjusted value from its parts, then the range
    split, time_info, cond_info = prepare_comps(R, homes, warn, market)
    history, history_errors = listing_history(R, homes, relist)
    if history_errors:
        raise ReportError(stop_message(history_errors))
    warn("outlier", *cma.outlier_warnings(R["comps"]["cards"]))  # CMA-110
    warn("time_undated", *cma.time_warnings(time_info))
    cards = R["comps"]["cards"]
    values = [c["adjusted"] for c in cards]
    median_adjusted = statistics.median(values)
    range_info = supported_range(R, values, market)
    rec = R["recommendation"]
    address = s.get("mls_address", s["address"])

    # the export: market stats and the chart's points and trend (drawn once, by render and the deck alike)
    stats, st = market_numbers(R, homes)
    others = [h for h in homes if not mls.same_address(h["address"], address)]
    pts = cma.scatter_points(homes, R.get("scatter") or {}, s["sqft"], address, [c["address"] for c in cards]) if st else None
    fit = pts[2] if pts else None

    # the stance the model picked (or the data's suggestion), and the options it sets, by rule
    agent_price, agent_reason, _ = price_override(R)
    stance, suggested, signals, stance_reason, problems = pick_stance(R, stats, rp is not None or relist is not None,
                                                                      agent_price)
    option_errors += role_problems(given, listing_kind(rp, relist))
    if problems or option_errors:
        raise ReportError(stop_message(problems + option_errors))
    built = build_options(R, stance, rec["low"], rec["high"], rp, relist)
    ri, rule_price = built["index"], built["rule"]
    defaults = option_defaults(stats, cards)
    strategies = option_values(built, given, defaults)
    p["strategies"] = strategies  # the working copy: what the payments and the net sheet read
    rec["list_price"] = strategies[ri]["list_price"]
    roles = [x["role"] for x in strategies]
    stay = roles.index("stay") if "stay" in roles else None
    insurance = insurance_line(R, market)

    # expected sales: Stay's by its rule, the others by the one rule
    split_iso = (st or {}).get("window", {}).get("split_date")
    rule = stay_rule(R, homes, strategies[stay], median_adjusted, _date(split_iso, "split_date")) if stay is not None else None
    stay_filled = stay is not None and strategies[stay].get("expected_sale") is None
    if stay_filled:
        if not rule:
            raise ReportError("pricing.options.stay.expected_sale: missing → without an MLS export there are no sales to "
                              "apply the rule to, so apply it to the sales you were given (method.md, A Reprice).")
        strategies[stay]["expected_sale"], strategies[stay]["expected_sale_source"] = rule["gross"], "stay_rule"
    competing = roles[-1] == "competing"
    basis = fill_expected_sales(R, strategies, stats, stay, competing)
    basis["split"] = split_iso
    for x in strategies[:-1] if competing else strategies:  # CMA-20
        if x["expected_sale"] > x["list_price"]:
            raise ReportError(f"pricing.options.{x['role']}.expected_sale: {money(x['expected_sale'])} is above its "
                              f"{money(x['list_price'])} list price → only the competing-offer option can sell above "
                              "its list price.")

    scope = cma.adjustment_scope_warning(market, s.get("county"), rec["list_price"])  # CMA-10
    if scope:
        warn("adjustment_scope", scope)
    if len(cards) < 3:
        warn("thin_comps", f"Only {len(cards)} comp{'s' if len(cards) > 1 else ''}: the range rests on thin support. Widen "
                           "the search if you can, and say so in the report.")
    if not rec["low"] <= rec["list_price"] <= rec["high"]:  # only the agent's own price can sit outside it
        warn("list_outside_range", f"The agent's list price {money(rec['list_price'])} is outside the supported range "
                                   f"{fmt.range(rec['low'], rec['high'])}: confirm it with the agent, and say why in "
                                   "price_override.reason.")
    for x in strategies:
        if x["expected_sale"] > rec["high"]:
            warn("expected_above_range", f"The expected sale {money(x['expected_sale'])} is above the supported range: "
                                         "an appraisal risk to explain, or lower it.")
    for i, hi in enumerate(strategies):  # CMA-323: a higher list price never expects less than a lower one
        for j, lo in enumerate(strategies):
            if stay not in (i, j) and hi["list_price"] > lo["list_price"] and hi["expected_sale"] < lo["expected_sale"]:
                warn("expected_sale_order", f"The {money(hi['list_price'])} option expects {money(hi['expected_sale'])}, "
                     f"below the {money(lo['list_price'])} option's {money(lo['expected_sale'])}. A higher list price "
                     f"sells at least as high, only slower: give it at least {money(lo['expected_sale'])}.")
    for key, text in cma.range_warnings(rec, values, market):  # CMA-296
        warn(key, text)

    # one closing per option, then the net sheet and the payments
    launch = launch_info(R, as_of)
    closings = option_closings(R, strategies, as_of, launch)
    if ri in goal_misses(R, closings):
        goal = fmt.date_short(_date(R["costs"]["expected_closing_date"], "expected_closing_date"))
        warn("recommended_after_goal", f"The recommended {money(strategies[ri]['list_price'])} option would likely "
             f"close {fmt.date_short(closings[ri]['date'])}, after the seller's {goal} goal (the notes say so): say in "
             "pricing.note how the plan meets the goal or why it's still the better choice, and raise it in the reply.")
    net = net_sheet(R, market, strategies, closings, as_of, ri)
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
        row = {"label": t("strategy_named", name=x["name"], price=money(x["list_price"])) if x["name"] else
               t("strategy_stay" if i == stay else "strategy_label", price=money(x["list_price"])),
               "name": x["name"], "agent": x["agent"], "role": x["role"], "time_source": x["time_source"],
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
        if i == stay:  # the script's own Stay values say so in the notes (stay_caveat); the agent's get checked
            if given.get("stay"):
                warn("stay_nets_more", f"Stay at Current Price nets {about(nets[i] - nets[ri])} more than the recommended "
                     "cut after holding costs, with the agent's own values in pricing.options.stay. Check them; if it "
                     "still nets more, say in pricing.note that the cut buys time and certainty, not a higher net.")
        elif stay is None and x["list_price"] > strat[ri]["list_price"]:
            own = {k for k, v in (given.get(x["role"]) or {}).items() if v not in (None, "")} & {
                "expected_sale", "seller_credit", "time", "months_to_contract", "closing_date"}
            if own:  # by the rule a higher price nets more, slower (method.md); an agent's figure gets checked
                warn("top_nets_more", f"The {x['list_price_display']} option nets {about(nets[i] - nets[ri])} more than "
                     "the recommended one after holding costs, with the agent's own "
                     f"{', '.join(sorted(own))} in pricing.options.{x['role']}. Check them; if it still nets more, "
                     "say in pricing.note why the recommended price is the better choice.")
    # CMA-319: a competing-offer option that nets more says, once in the notes, that its net depends on those offers
    caveat = len(strat) - 1 if competing and nets[-1] > nets[ri] else None
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
        "midpoint": (rec["low"] + rec["high"]) / 2,
        "expected_sale": expected_rec, "expected_sale_display": t("sum_expected_value", amount=money(expected_rec)),
        "expected_sub": L["deck_expected_sub" if expected_rec < rec["list_price"] else "deck_expected_sub_at"],
        "position": L[pos_key],
        "line": t("line_recommendation", low=money(rec["low"]), high=money(rec["high"]), median=money(shown),
                  price=money(rec["list_price"]), position=L[pos_key], vs=vs_median(rec["list_price"], shown)),
        "verdict": rw("verdict_price", price=money(rec["list_price"])),
        "caption": rw("verdict_caption", range=fmt.range(rec["low"], rec["high"])),
        "why": rec.get("why", ""), "override": range_info["override"], "price_override": agent_price is not None}
    C["stance"] = stance_model(stance, suggested, signals, stance_reason, stats, rule_price, agent_price, agent_reason,
                               failed=rp is not None or relist is not None)
    if range_info["override"]:  # the agent's own range, said once beside it, with the method's for comparison
        C["recommendation"]["line"] += " " + t("line_range_override", rule=fmt.range(range_info["rule_low"],
                                               range_info["rule_high"]), reason=end_sentence(range_info["reason"]))
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
        "method": cma.adjustment_summary(cards, time_info, money, cond_info), "method_note": comps.get("method_note", ""),
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
    C["condition"] = cond_info
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
    C["listing_kind"], C["options_merged"] = built["kind"], [list(m) for m in built["merged"]]
    C["launch"] = launch
    C["expected_sale_basis"] = {k: basis[k] for k in ("ratio", "ratio_display", "market_ratio", "source", "filled",
                                                       "agent", "capped", "raised_by")}
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
    add_notes(N, R, market, net, strategies, closings, basis, pay, as_of, stay, caveat, bool(reprice_out), defaults,
              stay_caveat=stay is not None and stay != ri and nets[stay] > nets[ri])
    merged = {}  # a narrow range: the stance options that came within 1% of a kept one, said once, by the kept one
    for role, into in built["merged"]:
        merged.setdefault(into, []).append(role)
    if merged:
        names = {x["role"]: x["name"] for x in strategies}
        N.add("options_merged", " ".join(t("note_options_merged", merged=cma._and([L["stance_" + r] for r in gone]),
                                           kept=names[into], verb="lists" if len(gone) == 1 else "list")
                                         for into, gone in merged.items()), "info")
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
        value={"low": rec["low"], "high": rec["high"], "midpoint": (rec["low"] + rec["high"]) / 2,
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


def comps_only(R):
    """Only the subject and the comps so far (no pricing or buyer payment yet): compute.py prints the adjusted comps,
    the range and the stance the market data suggests."""
    return not R.get("pricing") and not R.get("buyer_payment")


def run(R, mls_name=None, data_file=None):
    """The document model (or, with only the comps, the comps stage) from a report dict: render.py's compute step."""
    market, homes = load_inputs(R, mls_name, data_file)
    return comps_first(R, market, homes) if comps_only(R) else compute(R, market, homes, data_file)


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
        if result.get("stage") == "full":
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
