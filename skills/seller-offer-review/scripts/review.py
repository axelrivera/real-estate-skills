"""Analyze the offers on a listing: net sheets, downside, certainty, counter, ranking.

    python3 scripts/review.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID]

Prints JSON with every value already formatted: the page-1 summary (the same one the PDF shows), the
net sheet for each offer, and the assumptions ranked by impact. Or {"ok": false, "problems": [...]}.
See references/listing-file.md for the input.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import handoff, offer_engine as oe, profiles  # noqa: E402

money = oe.money
STATUS = {"g": "good", "a": "caution", "r": "risk"}


def signed(v):
    return ("+" if v >= 0 else "−") + money(abs(v))


def cap(text):
    return text[:1].upper() + text[1:]


def low_first(text):
    return text[:1].lower() + text[1:]


# --- inputs ------------------------------------------------------------------

def load_cma(data, cma_path=None):
    """The CMA handoff: --cma file first, else a handoff stored in the listing file under 'cma'."""
    if cma_path:
        return handoff.load(cma_path)
    if isinstance(data.get("cma"), dict):
        return handoff.validate(data["cma"])
    return None


def analyze(data, market=None, cma=None, agent=None):
    """The engine's analysis plus the review's own checks. `agent`: the profile (profiles.load_agent), for the
    listing-side check; without one, only the offers are compared with each other."""
    R = oe.analyze(data, market=market, cma=cma)
    one_target(R)
    R["highest_and_best"] = highest_and_best(data.get("listing") or {}, R["listing"])
    backup_lapses(R)
    for o in R["offers"]:
        confirm_assumed_inspection(o, R["listing"])
        counter_restatements(o)
        order_flags(o)
    label_title_fees(R)
    ask_year_built(R)
    ask_hoa_rider(R)
    ask_compensation_agreement(R)
    confirm_listing_side(R, (agent or {}).get("brokerage"))
    R["ranking_reason"] = str(data.get("ranking_reason") or "").strip() or None  # OFR-279
    return R


# --- after the engine ----------------------------------------------------------

def one_target(R):
    """One Seller's Target for every report on the listing (the comparison's chart and each single review): a clean
    offer at list closing on the recommended offer's date. Each offer's target keeps its own title terms (OFR-103) and
    commission lines; the chart's has the listing broker pay the buyer's broker only when it does on every active
    offer (OFR-339). With one offer, its own closing date, as before. R["target_close"] is that date."""
    top = R["ranked"][0] if R["ranked"] else None
    if not top:  # nothing ranked: the engine's report target stands
        return
    R["target_close"] = top["close"]
    L, S, costs = R["listing"], R["seller"], R["costs"]
    for o in R["offers"]:
        if o["close"] != top["close"]:
            o["target"] = oe.target_net(L, S, costs, top["close"], o)
    by_listing = all(o.get("bb_from_listing") for o in R["active"])
    R["target"] = (top["target"] if by_listing == bool(top.get("bb_from_listing")) else
                   oe.target_net(L, S, costs, top["close"], top, bb_from_listing=by_listing))


# Listing-side reminders (the seller's own paperwork), not risks in the offer: listed last, never a top risk (OFR-274)
# OFR-343: the HOA figure is the listing's to confirm; iteration 10 eval 5: Rider K's watch items are terms to agree,
# listed with the risk flags but never a top risk
HOUSEKEEPING = {"flood_disclosure", "hoa_conflict", "rider_K_terms"}
# Deal-specific risks first, within a severity level: a passed time for acceptance (whether there's an offer to answer),
# sale contingency, then financing, then appraisal gap, then the seller's deadline (OFR-274). Flags without a topic get one here, so the order and flag_keys use keys, not words.
RISK_ORDER = ("expired", "backup_lapses", "sale_contingency", "financing", "appraisal_gap", "past_deadline")


def risk_topic(o, f):
    if f.get("topic"):
        t = f["topic"]
        return {"approval_cap": "financing", "concessions_cap": "financing", "fha_gap_intent": "appraisal_gap",
                "escalation_cap_over_approval": "financing"}.get(t, t)
    issue = f["issue"]
    if o["sale_contingency_days"] and issue.startswith("Contingent on sale"):
        return "sale_contingency"
    if issue.startswith("Buyer has only a pre-qualification") or "can't be FHA" in issue:
        return "financing"
    if o["appraisal_risk"] and issue.startswith("Price is ") and " over " in issue:
        return "appraisal_gap"
    if issue.startswith("Closing ") and "deadline" in issue:
        return "past_deadline"
    return None


def order_flags(o):
    """Blocking, then High, Med, Low; within a level the deal-specific risks lead; listing-side reminders go last."""
    sev = {"Blocking": -1, "High": 0, "Med": 1, "Low": 2}
    for f in o["flags"]:
        f["topic"] = f.get("topic") or risk_topic(o, f)
    rank = {t: i for i, t in enumerate(RISK_ORDER)}
    o["flags"] = sorted(o["flags"], key=lambda f: (f.get("topic") in HOUSEKEEPING, sev.get(f["sev"], 1),
                                                     rank.get(risk_topic(o, f), len(RISK_ORDER))))


def expires_at(o):
    """An offer's time for acceptance as a datetime (a date alone is the end of that day), or None when it isn't a date."""
    raw = str(o.get("expires_raw") or "").strip()
    for fmt, n in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            when = datetime.strptime(raw[:n], fmt)
        except ValueError:
            continue
        return when if n == 16 else when.replace(hour=23, minute=59)
    return None


def counter_deadline(o, L):
    """When the counter to this offer stops being open: the time for acceptance it sets (offer_engine.acceptance_at)."""
    return oe.acceptance_at(o, L)


def backup_lapses(R):
    """OFR-319: the plan holds a backup until the primary contract is fully signed, but an offer whose own time for
    acceptance ends before the counter to the top offer does lapses before it can be used. The backup gets a flag
    (topic backup_lapses) and the plan asks its agent to extend the time for acceptance, or to answer it first."""
    rk = R["ranked"]
    if not rk or rk[0]["action"] != "COUNTER":
        return
    top = rk[0]
    due = counter_deadline(top, R["listing"])
    for o in rk[1:]:
        when = expires_at(o)
        if o["action"] != "BACKUP" or o.get("lapsed") or not when or when >= due:
            continue
        past = f"{due:%a %b %-d}, {due:%-I:%M %p}"
        # OFR-342: with highest and best pending, nothing is answered before the deadline, so only the extension fits
        hold = (R.get("highest_and_best") or {}).get("pending")
        o["lapses_before"] = {"until": past, "ends": f"{when:%a %b %-d}, {when:%-I:%M %p}", "offer": top["label"],
                              "ref": top["ref"]}
        o["flags"].append({
            "sev": "Med", "topic": "backup_lapses",
            "issue": f"Its time for acceptance ({o['expires']}) ends before the counter to {top['label']} does ({past}): "
                     "as a backup it lapses before it can be used.",
            "fix": f"Ask the buyer's agent to extend the time for acceptance past {past}"
                   + ("." if hold else ", or answer this offer first.")})


def highest_and_best(raw, L):
    """OFR-320: a call for highest and best already out (the NMOB-1 deadline, `listing.highest_and_best_due`): {due,
    pending}, or None. Pending until the deadline's day has passed: the analysis date has no time of day."""
    v = raw.get("highest_and_best_due")
    if not v:
        return None
    try:
        day = oe._d(v)
    except ValueError:
        return {"due": str(v), "pending": True}
    when = oe.fmt_when(v) + (", end of day" if len(str(v).strip()) == 10 else "")
    return {"due": when, "pending": day >= L["analysis_date"], "raw": str(v)}


def deal_flags(o):
    """The flags that are risks in the offer itself (no listing-side reminders)."""
    return [f for f in o["flags"] if f.get("topic") not in HOUSEKEEPING]


def confirm_assumed_inspection(o, L):
    """OFR-273: an inspection period nobody gave is never countered; the flag asks to confirm it instead."""
    if not o.get("inspection_assumed"):
        return
    for f in o["flags"]:
        if f.get("topic") == "inspection_period" and not f.get("agent_topics"):
            f["sev"] = "Low"
            f["issue"] = f"Inspection period not given: {o['inspection_days']} days assumed."
            n = L["norms"]["inspection_days"]  # iteration 10 eval 1: one number, as the Terms Review benchmark (≤n days)
            f["fix"] = f"Confirm the days in the contract; if it's over {n}, counter to {n} days."


CHANGE_ROW = {"inspection_days": "Inspection Period", "loan_approval_days": "Loan Approval Period", "deposit": "Escrow Deposit",
              "seller_concessions": "Seller Concessions", "appraisal_gap": "Appraisal Gap Coverage", "closing_date": "Closing Date"}


def counter_restatements(o):
    """Rows a counter carries so it answers everything the review raised (OFR-275, OFR-276): the loan amount and
    balance to close restated at the new price, and each term the buyer's counter changed that no seller counter
    answered (accept it or restate it). Only on a counter the engine already drafted; they change no number."""
    rows = o["counter_rows"]
    if not rows:
        return
    have = {r[0] for r in rows}
    extra = []
    for name, was, now, key in oe.buyer_changes(o):
        term = CHANGE_ROW.get(key, cap(name))
        if term not in have:
            extra.append((term, f"{now} (was {was})", f"{now} (accept), or restate {was}",
                          "The buyer's counter changed it and no seller counter answered it"))
    loan, bal, dep = o.get("loan_amount"), o.get("balance_to_close"), o["deposit"]
    if bal is not None and dep is not None and (loan or not o["financed"]):
        total = dep + (loan or 0) + bal
        price = o["counter_terms"]["price"]
        if abs(total - o["price"]) > 100:  # the engine's loan_amount issue: a counter changed the price without them
            extra.append(("Loan Amount and Balance to Close" if loan else "Balance to Close", f"Add up to {money(total)}",
                          f"Restated at {money(price)}", "They still add up to an earlier price"))
    if extra:
        last = rows[-1] if rows[-1][0] == "Time for Acceptance" else None
        o["counter_rows"] = [r for r in rows if r is not last] + extra + ([last] if last else [])


def label_title_fees(R):
    """OFR-277: title company fees from national estimates say so on the net sheet, like the owner's policy line."""
    if R["costs"].source("closing_costs.seller_title_fees") != "estimate":
        return
    sheets = [R["target"]] + [s for o in R["offers"] for s in (o["ns"], o["ns_down"], o["ns_counter"], o["target"])]
    for s in sheets:
        s["lines"] = [(k, lab + " (Estimate)" if k == "settle" and "(Estimate)" not in lab else lab, v)
                      for k, lab, v in s["lines"]]


def ask_year_built(R):
    """OFR-280: with riders read from a FAR/BAR package, the lead-based paint check needs the year built; without it
    the check can't run, so the review asks for it."""
    L = R["listing"]
    if L.get("year_built") or L.get("built_before_1978") in (True, False):  # OFR-295: the seller disclosure answers it
        return
    live = R["active"] + R["incomplete"]
    if not any(o["contract_form"] in oe.cf.FARBAR and o.get("rider_codes") for o in live):
        return
    a = {"scope": "listing", "field": "year_built", "value": None, "impact": "med",
         "why": "Year built not given: the lead-based paint check (a home built before 1978 needs the disclosure signed "
                "before accepting) can't run. Give the year built"}
    R["assumptions"].insert(0, a)
    meds = [i for i, x in enumerate(R["missing"]) if x["impact"] != "high"]
    R["missing"].insert(meds[0] if meds else len(R["missing"]), a)


def ask_compensation_agreement(R):
    """OFR-299: Rider GG puts the buyer's broker compensation in a separate compensation agreement. When the package
    doesn't give the amount, the review asks for the signed agreement (it's in ALWAYS_ASK), folding in the offer's
    assumed buyer-broker share so the question is asked once."""
    for o in R["active"] + R["incomplete"]:
        if o.get("bb_tag") == "Requested" or not any(f.get("topic") == "rider_GG" for f in o["flags"]):
            continue
        if o.get("bb_from_listing"):  # iteration 10 eval 6: the amount doesn't move the seller's net; the listing fee does
            fee = next((a for a in R["missing"] if a["field"] == "listing_fee_pct"), None)
            if fee:
                fee["ask"] = True
            continue
        sc = f"offer {o['id']}"
        old = next((a for a in R["missing"] if a["field"] == "buyer_broker_pct" and sc in oe.scopes(a)), None)
        if old:
            left = [s for s in oe.scopes(old) if s != sc]
            if left:  # still assumed for other offers: keep it for them
                old["scope"], old["also"] = left[0], left[1:]
            else:
                R["missing"].remove(old)
                if old in R["assumptions"]:
                    R["assumptions"].remove(old)
        net = ("the listing broker pays it from its fee" if o.get("bb_from_listing") else
               f"the net assumes {oe.pct(o['buyer_broker_pct'])}" if old and old["value"] else "it isn't in the net")
        a = {"scope": sc, "field": "compensation_agreement", "value": None,
             "impact": old["impact"] if old else "med",
             "why": f"Rider GG: the buyer's broker compensation is in a separate agreement that isn't in the package ({net}). "
                    "Send the signed compensation agreement (the amount)"}
        # OFR-353: the same ask on several offers is one item naming each (offer_engine.merge_assumptions), asked once
        same = next((x for x in R["missing"] if (x["field"], x["why"], x["impact"]) == (a["field"], a["why"], a["impact"])), None)
        if same:
            same.setdefault("also", []).append(sc)
            continue
        R["assumptions"].append(a)
        R["missing"].append(a)
    R["missing"].sort(key=lambda a: oe.IMPACT_ORDER[a["impact"]])


_FIRM_WORDS = {"llc", "inc", "corp", "co", "ltd", "pa", "pllc", "lp", "llp", "the", "and", "of"}


def firm_key(name):
    """A brokerage name's words for comparing names ("LPT Realty, LLC" -> {"lpt", "realty"})."""
    return set(re.findall(r"[a-z0-9]+", str(name or "").lower().replace("&", " and "))) - _FIRM_WORDS


def same_firm(a, b):
    ka, kb = firm_key(a), firm_key(b)
    return bool(ka and kb) and (ka <= kb or kb <= ka)


def confirm_listing_side(R, profile_brokerage=None):
    """The listing brokerage the contracts name (`listing_brokerage` on each offer) against the agent's profile, and
    against each other: a different name is asked once, as an item to confirm (the contract's broker block and Rider
    GG name the listing side; a wrong one is a correction before signing)."""
    live = R["active"] + R["incomplete"]
    named = []
    for o in live:
        n = str(o.get("listing_brokerage") or "").strip()
        if n and not any(same_firm(n, x) for x, _ in named):
            named.append((n, o))
    mine = str(profile_brokerage or "").strip()
    off = [(n, o) for n, o in named if mine and not same_firm(n, mine)]
    if not (off or (not mine and len(named) > 1)):
        return
    shown = off or named
    names = " and ".join(f"{n} ({o['label']})" if len(live) > 1 else n for n, o in shown)
    why = (f"Listing brokerage: the contract names {names}, but your profile says {mine}. Confirm the listing side on "
           "the contract and in any compensation agreement before signing" if mine else
           f"Listing brokerage: the contracts name {names}. Confirm the listing side on each contract before signing")
    a = {"scope": "listing", "field": "listing_brokerage", "value": shown[0][0], "impact": "med", "why": why}
    R["assumptions"].append(a)
    lows = [i for i, x in enumerate(R["missing"]) if x["impact"] == "low"]
    R["missing"].insert(lows[0] if lows else len(R["missing"]), a)


def ask_hoa_rider(R):
    """OFR-291: on an HOA or condo property, a FAR/BAR offer whose rider list wasn't read (no `riders`, or only letters its
    terms imply) gets an assumption asking about the HOA or condo rider instead of a flag, so every offer is checked the
    same way and recording a rent-back's Rider U changes nothing."""
    L = R["listing"]
    if not (L["condo"] or L.get("hoa_monthly")):
        return
    unread = [o for o in R["active"] + R["incomplete"] if o["contract_form"] in oe.cf.FARBAR and not oe.riders_known(o)]
    if not unread:
        return
    which = "condo rider (A)" if L["condo"] else "HOA or condo rider (A or B)"
    a = {"scope": f"offer {unread[0]['id']}", "field": "riders", "value": "not checked", "impact": "med",
         "why": f"Riders not listed: whether the {which} is attached wasn't checked. Confirm it's in the contract, with the "
                "HOA disclosure"}
    if len(unread) > 1:
        a["also"] = [f"offer {o['id']}" for o in unread[1:]]
    R["assumptions"].append(a)
    lows = [i for i, x in enumerate(R["missing"]) if x["impact"] == "low"]
    R["missing"].insert(lows[0] if lows else len(R["missing"]), a)


def estimated_costs(R, offers):
    """OFR-272: every cost line the net rests on that is a default or an estimate, in short
    phrases, so the quick answer can name them all in one line."""
    L, S, costs = R["listing"], R["seller"], R["costs"]
    def words(label):  # "HOA Estoppel Letter" -> "HOA estoppel letter"
        return " ".join(w if w.isupper() else w.lower() for w in label.split())

    out = []
    lines = {k: lab for o in offers for k, lab, v in o["ns"]["lines"] if v}
    shown = {f"offer {o['id']}" for o in offers}  # OFR-352: only the offers this answer covers
    bb_assumed = any(a["field"] == "buyer_broker_pct" and shown.intersection(oe.scopes(a)) for a in R["missing"])
    by_listing = [o for o in offers if o.get("bb_from_listing")]
    if S["listing_fee_assumed"] and by_listing:
        # OFR-293: the net sheet charges the market's total on one line when the listing broker pays the buyer's broker
        total = oe.pct(S["listing_fee_pct"] + (S["default_buyer_broker_pct"] or 0))
        mixed = len(by_listing) < len(offers)
        out.append(f"commission ({total} total, the listing broker pays the buyer's broker"
                   + (f"; on the other offers listing {oe.pct(S['listing_fee_pct'])}"
                      + (f" and buyer's broker {oe.pct(S['default_buyer_broker_pct'] or 0)}" if bb_assumed and "bb" in lines else "")
                      if mixed else "") + ", assumed)")
    elif S["listing_fee_assumed"] or bb_assumed:
        what = [f"listing {oe.pct(S['listing_fee_pct'])}" if S["listing_fee_assumed"] else None,
                "buyer's broker " + oe.pct(S["default_buyer_broker_pct"] or 0) if bb_assumed and "bb" in lines else None]
        out.append("commission (" + ", ".join(w for w in what if w) + ", assumed)")
    src = lambda path: costs.described(path)  # noqa: E731
    rate = costs.get("closing_costs.deed_transfer_tax_rate")
    if rate and "transfer" in lines and costs.source("closing_costs.deed_transfer_tax_rate") != "deal":
        out.append(f"{words(lines['transfer'].split(' (')[0])} {rate * 100:.2f}% ({src('closing_costs.deed_transfer_tax_rate')})")
    if "title" in lines and "(Quote)" not in lines["title"]:
        out.append(f"owner's title policy ({'promulgated rate' if 'Promulgated' in lines['title'] else 'estimate'})")
    if "settle" in lines and costs.source("closing_costs.seller_title_fees") != "deal":
        amounts = sorted({-v for o in offers for k, _, v in o["ns"]["lines"] if k == "settle"})
        out.append(f"title company fees {money(amounts[0])}" + (f" to {money(amounts[-1])}" if len(amounts) > 1 else "")
                   + f" ({src('closing_costs.seller_title_fees')})")
    tax = next((a for a in R["missing"] if a["field"] == "annual_tax" and isinstance(a["value"], (int, float))), None)
    discount = costs.get("property_tax.early_payment_discount")
    unpaid = any(o["ns"].get("tax_bill_assumed") for o in offers)  # OFR-313: local-costs.md, the reply says so
    extra = ((f", less the {discount * 100:g}% early-payment discount" if discount else "")
             + (", this year's bill assumed unpaid" if unpaid else ""))
    if tax and "tax" in lines:  # OFR-303: worded as the math is ("of list price", or the listing's own rate)
        out.append((f"tax proration at {L['tax_estimate']}" if L.get("tax_estimate") else
                    f"tax proration on an estimated {money(tax['value'])} bill") + extra)
    elif unpaid and "tax" in lines:
        out.append("tax proration with this year's bill assumed unpaid")
    if "estoppel" in lines and "(Estimate)" in lines["estoppel"]:  # iteration 9 eval 1: charged only with an HOA or a condo
        out.append(f"{words(lines['estoppel'].split(' (')[0])} (estimate)")
    if not L.get("repair_reserve_deal") and any(not o["repairs_owed"] and any(k == "repair" and v for k, _, v in o["ns_down"]["lines"])
                                                for o in offers):  # a Standard form's repair limits are contract terms
        out.append("post-inspection credit in the downside (estimate)")
    return out


def pick(R, mode="auto", offer_id=None):
    """(mode, offer) for the report. Single mode on one offer keeps the multi-offer context."""
    mode = R["mode"] if mode in (None, "auto") else mode
    if mode == "multi" and len(R["active"]) < 2:
        raise oe.OfferError("A comparison needs at least 2 active offers whose contracts can be reviewed; use single mode.")
    if mode == "multi":
        return "multi", None
    if offer_id:
        o = next((x for x in R["offers"] if x["id"] == offer_id), None)
        if o is None:
            raise oe.OfferError(f"There's no offer with id {offer_id!r} in the listing file.")
    elif R["ranked"] or R["incomplete"]:
        o = (R["ranked"] or R["incomplete"])[0]
    else:
        raise oe.OfferError("No active offers to review: every offer in the file is declined, expired or withdrawn. "
                            "To show one anyway, name it with --offer.")
    if "action" not in o:  # declined / expired offer shown on request
        o["action"], o["action_reason"] = "DECLINE", f"Offer status: {o['status']}"
    return "single", o


# --- shared pieces -----------------------------------------------------------

def price_note(o):
    """Financing, plus how an escalating offer reached its price."""
    return fin_str(o) + (f" · {o['escalation_note']}" if o.get("escalation") else "")


def target_note(o):
    """Iteration 10 evals 2, 4: each offer's target closes on that offer's date, so the tile names it (the comparison's
    target names its own), and the seller sees why the targets differ."""
    return f"list price, clean terms, closing {o['close']:%b %-d}"


def fin_str(o):
    return oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.1f}% down")


def listed_assumptions(R, multi=False, offer_id=None):
    """The assumptions a report lists: all of them in a single review; in the comparison, the listing's and seller's,
    each offer's high-impact ones and any shared by several offers (the rest are in each offer's single review).
    OFR-257: the counts in the Preliminary line and the data note come from this same list, so they match the table.
    OFR-344: `offer_id` (a single review of one of several offers) drops a listing assumption that applies only to
    other offers (`offers`: the tax bill question for an offer closing in November or December), and OFR-346 an
    assumption scoped only to other offers (their compensation agreement, their loan terms)."""
    def mine(a):
        offers = [x for x in oe.scopes(a) if x.startswith("offer ")]
        return not offers or f"offer {offer_id}" in offers
    return [a for a in R["missing"] if (not multi or not a["scope"].startswith("offer ") or a["impact"] == "high"
                                        or a.get("also")) and (offer_id is None or (offer_id in a.get("offers", [offer_id])
                                                                                    and mine(a)))]


# OFR-306: high-impact inputs that move every offer's net the same way, so they can't change the ranking (each is in the
# data note and the assumptions), and the contract form, which each offer carries as its own "form assumed" mark
SAME_FOR_EVERY_OFFER = {"payoff", "listing_fee_pct", "listing_fee_includes_buyer_broker", "state", "title_payer", "deed transfer tax", "who pays owner's title",
                        "owner's title rate", "title company fees"}
MARKED_PER_OFFER = {"contract_form"}


def ranking_deciding(a):
    return a["field"] not in SAME_FOR_EVERY_OFFER | MARKED_PER_OFFER


def form_assumed(R, o):
    """OFR-306: True when this offer's contract form was assumed (a high-impact input the comparison marks per offer)."""
    return any(a["field"] in MARKED_PER_OFFER and f"offer {o['id']}" in oe.scopes(a) for a in R["missing"])


def preliminary(R, offer_id=None, multi=False):
    """The Preliminary line, or None. OFR-306: the comparison carries it only when an input that could change the
    ranking is assumed; a single review, whenever one of its high-impact inputs is."""
    # OFR-266: an offer's missing input names the offers it's missing for
    name = lambda s: where(R, s)  # noqa: E731
    need = oe.preliminary_inputs({**R, "missing": [a for a in R["missing"] if ranking_deciding(a)]} if multi else R,
                                 None if multi else offer_id, name_offer=name)
    if not need:
        return None
    if multi:  # the hint names every input that would change the numbers (the payoff too), not only the ranking's
        need = oe.preliminary_inputs({**R, "missing": [a for a in R["missing"] if a["field"] not in MARKED_PER_OFFER]},
                                     None, name_offer=name)
    n = len(listed_assumptions(R, multi, None if multi else offer_id))
    return (f"**Preliminary: based on limited data.** Add {', '.join(need[:-1]) + ' and ' + need[-1] if len(need) > 1 else need[0]} to sharpen the numbers; "
            f"{n} input{'s are' if n != 1 else ' is'} assumed in total (listed at the end).")


def data_note(R, multi=False, offer_id=None):
    bits = []
    if not R["seller"]["payoff_known"]:
        bits.append("Nets are **before mortgage payoff**.")
    if not R["listing"]["cma_provided"]:
        bits.append("No CMA yet: appraisal risk is measured against list price.")
    shown = listed_assumptions(R, multi, offer_id)
    n, hi = len(shown), sum(a["impact"] == "high" for a in shown)
    more = " (each offer's single review lists the rest)" if multi and len(shown) < len(R["missing"]) else ""
    bits.append(f"{n} input{'s' if n != 1 else ''} assumed ({hi} high-impact); see Assumptions & Data to Confirm{more}."
                if n else "All key inputs provided.")
    return " ".join(bits)


def where(R, scope, also=()):
    """An assumption's scope for display: 'offer A' becomes the offer's label; an assumption shared by several offers
    (OFR-119) names each."""
    def one(s):
        if s.startswith("offer "):
            o = next((x for x in R["offers"] if x["id"] == s[6:]), None)
            return o["label"] if o else s.title()
        return s.title()
    return ", ".join(one(s) for s in [scope, *also])


def place(R, a, offer_id=None):
    """Where an assumption applies, for display. OFR-348: a single review names only its own offer on an assumption
    shared with others."""
    scopes = oe.scopes(a)
    if offer_id and f"offer {offer_id}" in scopes:
        scopes = [x for x in scopes if not x.startswith("offer ") or x == f"offer {offer_id}"]
    return where(R, scopes[0], scopes[1:])


def review_scope(R, mode, o):
    """OFR-352: the offer a single review of one of several offers is scoped to (its assumptions, questions and cost
    labels, as its PDF lists them), or None (one offer in the file, or the comparison)."""
    return o["id"] if mode == "single" and o is not None and R["mode"] == "multi" else None


# OFR-287: offer terms the review assumed and the counter won't touch (an assumed inspection period, a missing deposit),
# the lead-paint check and Rider GG's compensation agreement (OFR-299) are always asked after the high-impact gaps,
# even past the limit
ALWAYS_ASK = ("inspection_days", "deposit", "year_built", "compensation_agreement", "listing_brokerage")


def confirm_items(R, limit=4, offer_id=None):
    """The assumptions that would change the answer most, for the chat reply: the high-impact gaps (up to `limit`), the
    assumed offer terms in ALWAYS_ASK (and any marked `ask`, e.g. an assumed listing fee under Rider GG), then other medium-impact gaps while there's room. OFR-352: `offer_id` (a single
    review of one of several offers) asks only what its own review lists."""
    pool = listed_assumptions(R, offer_id=offer_id) if offer_id else R["missing"]
    asked = [a for a in pool if a["impact"] in ("high", "med")]
    terms = [a for a in asked if a["field"] in ALWAYS_ASK or a.get("ask")]
    high = [a for a in asked if a["impact"] == "high" and a not in terms][:limit]
    med = [a for a in asked if a["impact"] == "med" and a not in terms][:max(0, limit - len(high) - len(terms))]
    return high + terms + med


def to_confirm(R, limit=4, offer_id=None):
    out = []
    for a in confirm_items(R, limit, offer_id):
        if a["why"] not in out:  # OFR-353: one question per ask, however many offers it covers
            out.append(a["why"])
    return out


THREAT_LABEL = {"appraisal": "Appraisal", "contingency": "Contingencies", "timeline": "Closing date", "approval": "Loan approval",
                "financing": "Financing", "deposit": "Low deposit", "property": "Insurance / condition", "agent": "Buyer's agent"}
# OFR-304: a certainty criterion's score as a flag severity (4 and 5 are no threat)
THREAT_SEV = {1: "High", 2: "Med", 3: "Low"}
SEV_RANK = {"Blocking": 0, "High": 1, "Med": 2, "Low": 3}


def threat_key(o):
    """The certainty criterion that costs the most points (weight × shortfall), or None when every one scores 4+."""
    weights = {k: w for k, _, w in oe.CRITERIA}
    prio = ["appraisal", "contingency", "timeline", "approval", "financing", "deposit", "property", "agent"]
    s = o["score"]["scores"]
    worst = min(prio, key=lambda k: (-weights[k] * (5 - s[k]), prio.index(k)))
    return None if s[worst] >= 4 else worst


def threat(o):
    k = threat_key(o)
    return THREAT_LABEL[k] if k else "None major"


def biggest_risk(o):
    """OFR-304: the one biggest risk, so it never disagrees with the certainty's threat: the top deal flag (listing-side
    reminders never count), unless the threat's criterion score is a higher severity (score 1 High, 2 Med, 3 Low); then
    the threat, with the scorecard's reason. {sev, issue, key} or None: `key` is the flag's topic, or `threat:<criterion>`."""
    flag = next(iter(deal_flags(o)), None)
    k = threat_key(o)
    sev = THREAT_SEV.get(o["score"]["scores"][k]) if k else None
    if sev and (flag is None or SEV_RANK[sev] < SEV_RANK.get(flag["sev"], 2)):
        return {"sev": sev, "issue": f"{THREAT_LABEL[k]} ({o['score']['why'][k].rstrip('.')}).", "key": f"threat:{k}"}
    return {"sev": flag["sev"], "issue": flag["issue"], "key": flag.get("topic")} if flag else None


def firm_day(o, costs):
    """OFR-300: (the day the buyer's last cancel right really ends, the day it moved from or None): the last day of the
    longest window, rolled off a weekend or holiday by the market's contract rule (offer_engine.rolled), never past the
    closing (iteration 10 eval 1)."""
    return oe.rolled(o["firm_date"], costs, o["close"])


def open_after(o, wd):
    """Iteration 10 eval 2: what still lets the buyer cancel after the walk-away period, named (the loan approval, the
    appraisal, the sale of the buyer's home, each rider's window), so a later walk-away date reads as that window."""
    names = [n for n, d in (("the loan approval", o["loan_approval_days"] if o["financed"] else 0),
                            ("the appraisal terms", o["appraisal_days"]),
                            ("the sale of the buyer's home", o["sale_contingency_days"])) if d and d > wd]
    names += [f"the {what} (Rider {code})" for code, d, what in o.get("rider_windows") or () if d > wd]
    if not names:
        return "the loan, appraisal or rider terms"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def walk_away(o, costs):
    """(until, note): when the buyer's last cancel right ends, counted from acceptance (the Effective Date isn't set
    yet): the longest open window (OFR-267), AGA-1's included. AGA-1's renegotiation window only opens when the
    valuation plus the gap is below the price, so the note says the days after the other windows close are that
    condition. OFR-121: when the inspection walk-away (AS IS, Rider K or L) ends sooner, the note says until when the
    buyer may cancel for any reason. OFR-300: each date is rolled off a weekend or holiday as the contract rolls it."""
    ex = o.get("risk_days_ex_appraisal", o["risk_days"])
    notes = []
    wd = o.get("walkaway_days") or 0
    if wd and wd < o["risk_days"]:
        start = o["firm_date"] - timedelta(days=o["risk_days"])
        end, _ = oe.rolled(start + timedelta(days=wd), costs, o["close"])
        notes.append(f"For any reason until {end:%b %-d} ({wd}-day inspection period"
                     + (f", {o['contract_label']}" if o["contract_form"] in oe.cf.FARBAR else "")
                     + (", assumed" if oe.assumed(o, "inspection_days", "contract_form") else "")  # iteration 9 eval 1
                     + f"); after that only under {open_after(o, wd)}.")
    if o.get("appraisal_form") == "aga" and ex < o["risk_days"] == o["appraisal_days"]:
        first, _ = oe.rolled(o["firm_date"] - timedelta(days=o["risk_days"] - ex), costs, o["close"])
        notes.append(f"After {first:%b %-d} ({ex} days) only if the valuation plus the gap comes in below the price (Appraisal Gap Addendum).")
    until, was = firm_day(o, costs)
    moved = f"; {was:%a %b %-d} moves to the next business day" if was else ""
    return f"{until:%a %b %-d} ({o['risk_days']} days from acceptance{moved})", " ".join(notes) or None


def downside_hits(o):
    """OFR-258: what the downside case counts for this offer: 'appraisal' when a low appraisal cuts the price,
    'inspection' when there's a repair credit or repair limit."""
    return [k for k, on in (("appraisal", o["downside_price"] < o["price"]), ("inspection", bool(o["repair_reserve"]))) if on]


def downside_checked(o):
    """OFR-301: what the downside case tests for this offer, whether or not it costs anything: 'appraisal' whenever the
    offer carries appraisal risk (a financed offer, AGA-1 or Rider F), 'inspection' when there's a repair cost."""
    return [k for k, on in (("appraisal", bool(o["appraisal_risk"])), ("inspection", bool(o["repair_reserve"]))) if on]


def downside_note(o, L, short=False):
    """'if the appraisal and inspection go badly', or only the part that applies to this offer. OFR-301: an appraisal
    risk that costs nothing at the value line is named too, so the seller never reads it as no appraisal risk."""
    hits = downside_hits(o)
    if hits == ["appraisal", "inspection"]:
        return "if the appraisal and inspection go badly"
    if hits == ["appraisal"]:
        return "if the appraisal comes in low"
    free = "appraisal" in downside_checked(o) and "appraisal" not in hits and not short
    at = "at the top of the value range" if L["cma_provided"] else "at list price"
    if hits == ["inspection"]:
        return "if the inspection goes badly" + (f"; an appraisal {at} wouldn't cut the price" if free else "")
    if free:
        return f"same as offered: an appraisal {at} wouldn't cut the price, and no inspection cost applies"
    return "same as offered: no appraisal or inspection cost applies"


def backup_form(o):
    """The backup contract's one name everywhere: the FAR/BAR rider by its name and letter (contract_forms), else a
    back-up addendum."""
    return f"the {oe.cf.rider_name('W')}" if o["contract_form"] in oe.cf.FARBAR else "a back-up contract addendum"


def title(action, o):
    """OFR-265: the recommendation as a heading that names the offer, "Counter the $382K FHA Offer", never
    "Counter: $382K FHA" (which reads like a counter at the offer's price)."""
    name = o["ref"][4:-6] if o["ref"].startswith("the ") and o["ref"].endswith(" offer") else o["label"]
    return {"ACCEPT": f"Accept the {name} Offer", "COUNTER": f"Counter the {name} Offer",
            "BACKUP": f"Hold the {name} Offer as Backup", "DECLINE": f"Decline the {name} Offer",
            "INCOMPLETE": f"Contract Incomplete: the {name} Offer"}.get(action, f"{action.title()}: the {name} Offer")


def respond_by(o):
    """The time for acceptance, or that it has passed (never a past date to beat)."""
    if not o.get("expires"):
        return "No time stated"  # OFR-120: a fact, not a place to look
    return f"Passed ({o['expires']})" if o.get("lapsed") == "passed" else \
        f"Likely passed ({o['expires']})" if o.get("lapsed") == "likely" else o["expires"]


def deadline_note(S):
    """OFR-296: a seller's deadline on a weekend isn't a closing day: the last business day before it is ('' otherwise)."""
    dl = S["deadline"]
    if not dl or dl.weekday() < 5:
        return ""
    return f"a {dl:%A}: close by {oe.prior_weekday(dl):%a %b %-d}"


def certainty(o, S, costs):
    dl = S["deadline"]
    wa = walk_away(o, costs)
    return {
        "score": o["score"]["total"], "band": o["score"]["band"][1], "band_class": o["score"]["band"][0],
        "walk_away_until": wa[0], "walk_away_note": wa[1],
        "deposit": f"{money(o['deposit'])} ({o['deposit'] / o['price']:.1%})" if o["deposit"] is not None else "not provided",
        "closing": (f"{o['close']:%b %-d} vs. {dl:%b %-d} deadline" + (f" ({deadline_note(S)})" if deadline_note(S) else "") if dl else
                    f"{o['close']:%b %-d} ({o['close_days']} days)"),
        "closing_ok": (o["close"] <= dl) if dl else True,
        "threat": threat(o),
    }


def row(term, offered, counter, why):
    return {"term": term, "offered": offered, "counter": counter, "why": why}


# --- single offer ------------------------------------------------------------

def incomplete_view(R, o):
    """A contract that can't be reviewed as written: what to fix, the numbers as written, and no recommendation.

    An offer whose only Blocking issue is a passed time for acceptance can be revived by a seller counter, so the view
    also carries what that counter could look like (`revive`), labeled as reference, never as a recommendation."""
    S, L = R["seller"], R["listing"]
    issues = "; ".join(f["issue"].rstrip(".") for f in o["blocking"])
    fixes = [f for f in o["flags"] if f.get("contract") and f["sev"] in ("Blocking", "High")]
    expired_only = all(f.get("topic") == "expired" or "expired" in (f.get("agent_topics") or ()) for f in o["blocking"])
    revive = None
    if expired_only and o["counter_rows"]:
        cn = o["ns_counter"]["net_adj"]
        # FH-103: the facts (the offer's own deadline has passed), never a conclusion about whether it can be accepted
        revive = {"note": "The offer's time for acceptance has passed. A seller counter sets a new time for acceptance. "
                          "For reference only, this is what a counter could look like:",
                  "rows": [row(*r) for r in o["counter_rows"]],
                  "summary": f"net after holding {money(o['ns']['net_adj'])} as written → {money(cn)} with this counter"}
    nxt = ("ask the buyer's agent for a corrected, fully signed contract with every page and rider, then run the review again."
           if not expired_only else
           "the time for acceptance has passed. If the seller wants this buyer, approve a counter with a new time for "
           "acceptance, or I'll ask the buyer's agent to re-sign it with a new time for acceptance.")
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": "INCOMPLETE", "headline": "CONTRACT INCOMPLETE", "title": title("INCOMPLETE", o),
        "why": (f"This contract can't be reviewed as written: {issues[:1].lower() + issues[1:]}. There is no recommendation, "
                + ("counter or ranking until the buyer's agent sends a corrected, fully signed contract." if not expired_only else
                   "and it isn't ranked; a seller counter would set a new time for acceptance.")
                + " The numbers below are for reference only. For questions about whether the contract is binding, see a "
                "real estate attorney."),
        "offers_active": len(R["active"]) + len(R["incomplete"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": respond_by(o), "respond_by_offer": o["label"] if o.get("expires") else None,
        "priority": S.get("priority_note") or S["priority"].title(),
        "fixes":[{"sev": f["sev"], "issue": f["issue"], "fix": f["fix"]} for f in fixes],
        "counter": None, "compare": None, "revive": revive,
        "kpis": [{"label": "Offer Price", "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
                 {"label": "Net as Written", "value": money(o["ns"]["net_adj"]), "note": "for reference only", "tone": ""},
                 {"label": "Downside Net", "value": money(o["ns_down"]["net_adj"]), "note": downside_note(o, L), "tone": "risk"},
                 {"label": "Seller's Target Net", "value": money(o["target"]["net_adj"]), "note": target_note(o), "tone": ""}],
        "certainty": certainty(o, S, R["costs"]),
        # contract issues are in fixes; iteration 9 evals 1, 5: a listing-side reminder is never a top risk
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in deal_flags(o) if not f.get("contract")][:3],
        "terms_reason": None,  # iteration 11 eval 4: the pick's terms reason belongs to the pick, not a blocked offer
        "options": [],
        "preliminary": None,
        "next_step": cap(nxt),  # OFR-264: a sentence after "Next Step:"
        "data_note": data_note(R, offer_id=o["id"] if R["mode"] == "multi" else None),  # OFR-352: as its assumptions list
    }


def counter_what(vs_offer, vs_downside, certainty, act):
    """OFR-16: the Counter row says what actually changes: net up or down, certainty up or down."""
    net = (f"{signed(vs_offer)} net vs. as offered" if vs_offer >= 0 else
           f"{signed(vs_offer)} on paper, {signed(vs_downside)} vs. the realistic downside")
    sure = ("more certain to close" if certainty > 0 else "less certain to close" if certainty < 0 else "same certainty")
    text = f"{net}; {sure} ({'+' if certainty > 0 else '−'}{abs(certainty)} points)" if certainty else f"{net}; {sure}"  # OFR-290
    return text if act == "COUNTER" else text + ", and it risks losing a strong offer"

def single_view(R, o):
    if o["action"] == "INCOMPLETE":
        return incomplete_view(R, o)
    L, S = R["listing"], R["seller"]
    tgt = o["target"]["net_adj"]
    ao, dn, cn = o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"]
    act = o["action"]
    top = R["ranked"][0] if R["ranked"] else o
    multi_ctx = R["mode"] == "multi"

    if act == "COUNTER":
        s = []
        if o["price"] > L["list_price"] and ao < tgt:
            s.append(f"The {money(o['price'])} offer is {money(o['price'] - L['list_price'])} over list, but after costs it nets "
                     f"**{money(tgt - ao)} less** than a clean full-price offer.")
        elif ao < tgt:
            s.append(f"This offer nets **{money(tgt - ao)} less** than a clean full-price offer.")
        if any("appraisal gap" in f["issue"] for f in o["flags"]):
            s.append("It's priced above the value range without enough appraisal gap coverage.")
        if o["sale_contingency_days"]:
            s.append("It depends on the sale of the buyer's home.")
        risk = "and cuts the risk" if o["counter_score"] > o["score"]["total"] else "at about the same certainty"
        s.append(f"The counter below lifts the net by {money(cn - ao)} {risk}." if cn >= ao
                 else f"The counter below protects the price: it nets {signed(cn - dn)} vs. the downside case.")
        why = " ".join(s)
    elif act == "ACCEPT":
        sc = o["score"]["total"]  # OFR-23: the wording follows the score band
        why = (f"Strong offer: nets {money(ao)} with {sc}/100 certainty. Nothing in the terms is worth risking the deal over."
               if sc >= 80 else f"Nets {money(ao)} with {sc}/100 certainty. No counter would improve it, so accept it with its risks "
               "in view (see the risk flags).")
    else:
        why = f"{o.get('action_reason', '')}. {cap(top['ref'])} is the recommended offer; see the comparison below."

    counter = None
    if act == "COUNTER" and o["counter_rows"]:
        tail = f", {signed(cn - dn)} vs. downside" if cn < ao else ""
        counter = {"rows": [row(*r) for r in o["counter_rows"]],
                   "summary": f"{len(o['counter_rows'])} change{'s' if len(o['counter_rows']) != 1 else ''} · net after holding "
                              f"{money(ao)} → **{money(cn)}** ({signed(cn - ao)} vs. as offered{tail})"}
    compare = None
    if act in ("BACKUP", "DECLINE") and top is not o:
        compare = {"this": o["label"], "vs": top["label"], "rows": [
            ["Price", money(o["price"]), money(top["price"])],
            ["Net After Holding", money(ao), money(top["ns"]["net_adj"])],
            ["Downside Net", money(dn), money(top["ns_down"]["net_adj"])],
            ["Certainty", f"{o['score']['total']}/100", f"{top['score']['total']}/100"],
            ["Closing", f"{o['close']:%b %-d}", f"{top['close']:%b %-d}"]]}

    pre = "" if S["payoff_known"] else " (Pre-Payoff)"
    kpis = [{"label": "Offer Price", "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
            {"label": f"Net as Offered{pre}", "value": money(ao), "note": f"{signed(ao - tgt)} vs. target",
             "tone": "risk" if ao < tgt else "good"},
            {"label": "Downside Net", "value": money(dn), "note": downside_note(o, L), "tone": "risk"}]
    if act == "COUNTER":
        kpis.append({"label": "Net with Our Counter", "value": money(cn), "tone": "good",
                     "note": f"{signed(cn - ao)} vs. as offered" if cn >= ao else f"{signed(cn - dn)} vs. downside; protects the price"})
    else:
        kpis.append({"label": "Seller's Target Net", "value": money(tgt), "note": target_note(o), "tone": ""})

    score = o["score"]["total"]
    opts = [{"option": "Accept as Written", "net": money(ao), "certainty": f"{score}/100", "status": "good" if score >= 80 else "risk",
             "what": "Deal as signed" if score >= 80 else f"Realistic net closer to {money(dn)} {downside_note(o, L, short=True)}" if dn < ao
             else "Deal as signed, with its risks in view (see the risk flags)",  # OFR-258: never "closer to" the same net
             "recommended": act == "ACCEPT"}]
    if o.get("lapsed") == "likely":  # iteration 10 eval 7: signing a counter whose time has likely passed may not bind
        opts[0].update(status="risk", what=f"Its time for acceptance likely passed ({o['expires']}): confirm when it was "
                                           "delivered before signing, or counter")
    if o["counter_rows"]:
        opts.append({"option": "Counter", "net": money(cn), "certainty": f"≈{o['counter_score']}/100 if accepted",
                     "status": "good" if act == "COUNTER" else "caution", "recommended": act == "COUNTER",
                     "what": counter_what(cn - ao, cn - dn, o["counter_score"] - score, act)})
    opts.append({"option": "Decline", "net": "—", "certainty": "—", "status": "caution", "recommended": act == "DECLINE",
                 "what": f"Stay on market; each extra month costs about {money(S['holding_monthly'])} in holding costs"})
    if act == "BACKUP":
        opts.insert(0, {"option": "Hold as Backup", "net": money(ao), "certainty": f"{score}/100", "status": "caution",
                        "what": f"Steps in if {top['ref']} falls through; until then the backup buyer can cancel "
                                f"({backup_form(o)})", "recommended": True})

    expires = f" before {o['expires']}" if o.get("expires") and not o.get("lapsed") else ""
    nxt = {"COUNTER": f"approve the counter terms and I'll send the counter to the buyer's agent{expires}.",
           "ACCEPT": "sign the contract and I'll open escrow and calendar every deadline.",
           "BACKUP": "once the primary contract is fully signed, approve offering this buyer a backup position on "
                     f"{backup_form(o)}, with a short notice date: the backup buyer can cancel until the seller's notice.",
           "DECLINE": "approve, and with your written OK I'll tell the buyer's agent the seller is moving forward with another offer."}[act]
    held = next((x for x in R["ranked"][1:] if x.get("lapses_before")), None) if top is o else None
    if act == "COUNTER" and held:  # OFR-344: the plan's order, the backup's extension asked for before the counter goes out
        nxt = (f"approve the counter terms and I'll ask the buyer's agent on {held['ref']} to extend past "
               f"{held['lapses_before']['until']}, then send the counter to the buyer's agent{expires}.")
    first = []
    hb = R.get("highest_and_best")
    if hb and hb["pending"]:  # OFR-320
        first.append(f"Final offers are due {hb['due']} (highest and best); once they're in, I'll run the review again.")
    lapse = o.get("lapses_before")
    if act == "BACKUP" and lapse:  # OFR-319: the backup's own deadline ends before the counter to the top offer does
        first.append(f"Its time for acceptance ends {lapse['ends']}, before the counter to {lapse['offer']} does: I'll ask "
                     f"the buyer's agent to extend it past {lapse['until']}.")
    if first:
        nxt = " ".join(first) + " Then " + nxt
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": act, "headline": "HOLD AS BACKUP" if act == "BACKUP" else act, "title": title(act, o), "why": why,
        "offers_active": len(R["active"]) if multi_ctx else 1,
        "respond_by": respond_by(o), "respond_by_offer": o["label"] if o.get("expires") else None,
        "respond_by_also": respond_also(R, shown=o),  # OFR-320
        "priority": S.get("priority_note") or S["priority"].title(),
        "counter": counter, "compare": compare, "kpis": kpis,
        "certainty": certainty(o, S, R["costs"]),
        # OFR-274, iteration 9 evals 1, 5: a listing-side reminder (the flood disclosure) is never a top risk
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in deal_flags(o)[:3]],
        # iteration 11 eval 4: the terms reason for the pick prints on the pick's own review only
        "terms_reason": R.get("ranking_reason") if not multi_ctx or (R["ranked"] and o is R["ranked"][0]) else None,
        "options": opts,
        "preliminary": preliminary(R, o["id"] if multi_ctx else None),
        "next_step": cap(nxt),  # OFR-264
        "data_note": data_note(R, offer_id=o["id"] if multi_ctx else None),
    }


# --- multiple offers ---------------------------------------------------------

def first_expiry(R):
    """(when, offer label, offer or None) of the first deadline among the offers the plan acts on now (OFR-305: the ones
    it counters or accepts), never a declined or backup offer's, so the Respond By box can't read as "answer the
    declined offer" (respond_also lists an earlier one from another offer)."""
    acted = [o for o in R["ranked"] if o["action"] in ("ACCEPT", "COUNTER")]
    ex = [o for o in acted if o.get("expires_raw") and not o.get("lapsed")]
    if not ex:  # OFR-120: no deadline in the files is a fact to state, not a place to look
        return "No time stated", (acted[0]["label"] if acted else None), None
    def when(o):  # OFR-263: a date alone is the end of that day
        s = str(o["expires_raw"]).strip()
        return s if len(s) > 10 else f"{s} 23:59"
    o = min(ex, key=when)
    return o["expires"], o["label"], o


def respond_also(R, held=(), shown=None):
    """OFR-319, OFR-320: the other deadlines the Respond By box shows: a pending call for highest and best, and a held
    offer whose own time for acceptance ends before the counter's. Iteration 10 evals 2, 4: and the earliest live time
    for acceptance among the active offers when the box doesn't already show it (`shown` is the offer Respond By names,
    or None), so an offer that lapses first is never hidden behind "No time stated". [{when, what, key}]"""
    out = []
    hb = R.get("highest_and_best")
    if hb and hb["pending"]:
        out.append({"when": short_when(hb.get("raw")) or hb["due"], "what": "Highest & Best Due",
                    "key": "highest_and_best"})
    out += [{"when": short_when(o.get("expires_raw")) or o["expires"], "what": "Backup: Ask to Extend", "key": "backup_lapses"}
            for o in held]
    # OFR-305, iteration 11 eval 2: only an offer the plan keeps (accepted, countered or held), never a declined one
    live = [o for o in R["active"] if expires_at(o) and not o.get("lapsed") and o.get("action") != "DECLINE"]
    first = min(live, key=expires_at, default=None)
    if first and first is not shown and all(first is not o for o in held) and len(R["active"]) > 1:
        mine = expires_at(shown) if shown and not shown.get("lapsed") else None
        if mine is None or expires_at(first) < mine:
            out.append({"when": short_when(first.get("expires_raw")) or first["expires"], "what": f"{first['label']} Expires",
                        "key": "offer_expires"})
    return out


def short_when(raw):
    """A deadline in the Respond By box's short form, "Wed Sep 23, 12:00 PM" (the box is narrow; the review's year is
    on the page), or None when it isn't a date and time."""
    try:
        at = datetime.strptime(str(raw or "").strip()[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return f"{at:%a %b %-d}, {at:%-I:%M %p}"


def multi_view(R):
    S = R["seller"]
    rk = R["ranked"]
    top = rk[0]
    act = top["action"]
    backup = next((o for o in rk if o["action"] == "BACKUP"), None)
    hi_price = max(R["active"], key=lambda o: o["price"])
    lead = f"{cap(top['ref'])} has the best net once risk is counted and closes {top['close']:%b %-d}"
    lead += ", before the seller's deadline." if S["deadline"] and top["close"] <= S["deadline"] else "."
    if hi_price is not top:
        reason = hi_price["action_reason"]
        reason = (reason[:1].lower() + reason[1:]) if reason else "more risk"
        lead += f" The highest price ({hi_price['label']}, {money(hi_price['price'])}) ranks #{rk.index(hi_price) + 1}: {reason}."
    lapse = (backup or {}).get("lapses_before")
    if backup:
        lead += f" Keep {backup['ref']} as backup after the primary contract is fully signed."  # OFR-282
    if lapse:  # OFR-319: its own deadline ends before the counter's
        lead += f" Its time for acceptance ends first ({lapse['ends']}): ask its agent to extend it."
    hb = R.get("highest_and_best")
    if hb and hb["pending"]:  # OFR-320: final offers are still coming in
        lead += f" Highest and best is due {hb['due']}: nothing goes out before then."
    if R["incomplete"]:
        n = len(R["incomplete"])
        names = ", ".join(x["label"] for x in R["incomplete"])
        lead += (f" {n} more offer{'s' if n != 1 else ''} ({names}) can't be reviewed until the contract is corrected, "
                 + ("so it isn't ranked." if n == 1 else "so they aren't ranked."))
    top_net = top["ns_counter"]["net_adj"] if act == "COUNTER" else top["ns"]["net_adj"]

    terms = {}
    for o in rk:
        a = o["action"]
        if o is top and a == "COUNTER":
            t = "Counter: " + " · ".join(f"{r[0].lower()} {r[2]}" for r in o["counter_rows"][:5])
        elif o is top:
            t = "Accept as written"
        elif a == "BACKUP":
            # OFR-251: the backup keeps its own price; a counter price would read as an ask. Only an escalated price
            # differs from what the buyer wrote, and then the note says so (iteration 12: the base, increment and cap are
            # in the comparison's Escalation column, so a short note here)
            t = (f"After {top['label']}'s contract is fully signed, offer a backup position on {backup_form(o)}"
                 + (f" (at the escalated {money(o['price'])})" if o.get("escalated") else ""))
            if o.get("lapses_before"):  # OFR-319: the first step, or the backup lapses before it can be used
                t = f"First ask to extend its deadline ({o['lapses_before']['ends']}) past {o['lapses_before']['until']}. " + t
        else:
            t = o["action_reason"]
        terms[o["id"]] = t
    summary = f"Net after holding with {top['ref']} {'counter' if act == 'COUNTER' else 'as written'}: **{money(top_net)}**"
    if act == "COUNTER":
        summary += f" ({signed(top_net - top['ns']['net_adj'])} vs. as offered"
        summary += f", {signed(top_net - top['ns_down']['net_adj'])} vs. downside)" if top_net < top["ns"]["net_adj"] else ")"
    # OFR-289: every plan says it (counter-rules.md), an acceptance plan too: one counter or acceptance at a time
    note = "Only one counter or acceptance goes out at a time, so the seller can't end up with two accepted contracts. "
    note +=("With the seller's written authorization, other buyers' agents are told the seller is "
             f"{'responding to' if act == 'COUNTER' else 'moving forward with'} another offer (NAR Standard of Practice 1-15); "
             "nothing is declined until the seller approves.")

    # OFR-351: `id` is what --offer takes, for each offer's single review after the comparison
    ranked = [{"rank": i + 1, "offer": o["label"], "key": o["key"], "id": o["id"],
               "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
               "price": money(o["price"]) + (" (escalated)" if o.get("escalated") else ""), "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]),
               "score": o["score"]["total"], "band_class": o["score"]["band"][0], "risk_days": o["risk_days"],
               "close": f"{o['close']:%b %-d}", "action": "Hold as Backup" if o["action"] == "BACKUP" else o["action"].title(),
               "status": {"ACCEPT": "good", "COUNTER": "good", "BACKUP": "caution", "DECLINE": "risk"}[o["action"]],
               "terms": terms[o["id"]], "form_assumed": form_assumed(R, o),
               "escalation": oe.escalation_terms(o)} for i, o in enumerate(rk)]  # iteration 12: base, increment, cap
    ranked += [{"rank": "—", "offer": o["label"], "key": o["key"], "id": o["id"],
                "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
                "price": money(o["price"]), "net": "—", "downside": "—", "score": "—", "band_class": "na", "risk_days": "—",
                "close": f"{o['close']:%b %-d}", "action": "Incomplete", "status": "risk",
                # OFR-120: only the first letter goes lowercase, so dates and times keep their case
                "terms": "Contract can't be reviewed as written: " + low_first(o["blocking"][0]["issue"].rstrip(".")),
                "form_assumed": form_assumed(R, o), "escalation": oe.escalation_terms(o)}
               for o in R["incomplete"]]

    most_certain = max(R["active"], key=lambda o: (o["score"]["total"], o["ns_down"]["net_adj"]))
    first = f"{'Counter' if act == 'COUNTER' else 'Accept'} {top['label']}" + (f", Hold {backup['label']} as Backup" if backup else "")
    # OFR-324: `short` names offers by the key the plan table shows beside each label, for the PDF's narrow Option column
    short = f"{'Counter' if act == 'COUNTER' else 'Accept'} {top['key']}" + (f", Hold {backup['key']} as Backup" if backup else "")
    opts = [{"option": first, "short": short, "net": money(top_net), "recommended": True, "status": "good",
             "certainty": f"≈{top['counter_score']}/100" if act == "COUNTER" else f"{top['score']['total']}/100",
             "what": "Best net with manageable risk" + (f"; {backup['ref']} is a safety net" if backup else "")}]
    g = top["ns_counter"]["net_adj"] - top["ns"]["net_adj"]
    if act == "ACCEPT" and top["counter_rows"] and g > 0:  # OFR-116: never "Only +$0"
        opts.append({"option": f"Counter {top['label']} Anyway", "short": f"Counter {top['key']} Anyway",
                     "net": money(top["ns_counter"]["net_adj"]), "recommended": False,
                     "certainty": f"≈{top['counter_score']}/100", "status": "caution",
                     "what": f"Only {signed(g)}, and it risks losing the strongest offer"})
    if most_certain is not top:
        opts.append({"option": f"Accept {most_certain['label']} Now", "short": f"Accept {most_certain['key']} Now",
                     "net": money(most_certain["ns"]["net_adj"]), "recommended": False,
                     "certainty": f"{most_certain['score']['total']}/100", "status": "caution",
                     "what": f"Closes {most_certain['close']:%b %-d}, most certain, but {money(top_net - most_certain['ns']['net_adj'])} less than the plan"})
    if not hb:  # OFR-320: a call for highest and best already out isn't offered again
        opts.append({"option": "Call for Highest & Best", "net": "Unknown", "certainty": "Varies", "status": "caution",
                     "recommended": False, "what": "May lift prices, but adds ~2 days and weak terms usually stay weak"})
    verb = "send the counter to" if act == "COUNTER" else "accept"
    nxt = (f"final offers are due {hb['due']} (highest and best); once they're in, I'll run the review again. Then "
           if hb and hb["pending"] else "")
    nxt += (("a" if nxt else "A") + "pprove the plan and I'll "
            + (f"ask the buyer's agent on {backup['ref']} to extend past {lapse['until']}, then "
               if lapse else "")
            + f"{verb} {top['ref']}"
            + (f"; once that contract is fully signed, I'll offer {backup['ref']} a backup position" if backup else "") + ".")
    rb = first_expiry(R)
    also = respond_also(R, [backup] if lapse else [], shown=rb[2])
    keys = (["backup_lapses"] if lapse else []) + (
        [f"highest_and_best_{'pending' if hb['pending'] else 'done'}"] if hb else [])
    return {
        "mode": "multi", "offer": top["id"], "offer_label": top["label"], "action": act, "headline": act, "title": title(act, top), "why": lead,
        "offers_active": len(R["active"]) + len(R["incomplete"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": rb[0], "respond_by_offer": rb[1], "respond_by_also": also,
        "plan_keys": keys,  # OFR-319, OFR-320: what the plan adds, as keys
        "priority": S.get("priority_note") or S["priority"].title(),
        "plan_summary": summary, "plan_note": note, "ranked": ranked, "options": opts,
        "preliminary": preliminary(R, top["id"], multi=True), "next_step": cap(nxt), "data_note": data_note(R, multi=True),
        "target_net": money(R["target"]["net_adj"]),
        "terms_reason": R.get("ranking_reason"),  # OFR-279: the agent's terms reason for the pick, shown on the report
    }


# --- detail for the markdown template ------------------------------------------

def net_sheet_rows(cols):
    """[{label, values[]}] for columns of net sheets; rows that are zero everywhere are skipped (except price and concessions)."""
    # Rows by line key, not position: a rider money line (rent-back, seller financing, an assessment payoff) can be on
    # one column and not another (the Seller's Target never has one), and a missing line reads as 0.
    order, labels = [], {}
    for _, c in cols:
        for key, label, _ in c["lines"]:
            if key not in labels:
                labels[key] = label
                order.append(key)
    rows = []
    for key in order:
        vals = [next((amt for k, _, amt in c["lines"] if k == key), 0) for _, c in cols]
        if key not in ("price", "conc") and all(v == 0 for v in vals):
            continue
        rows.append({"key": key, "label": labels[key], "values": vals})
    return rows


def offer_detail(o, R):
    costs, L = R["costs"], R["listing"]
    br = biggest_risk(o)
    cols = [("As Offered", o["ns"]), ("Downside Case", o["ns_down"])]
    if o["counter_rows"]:  # OFR-354, DS-106: the PDF's labels; a lapsed offer's counter is for reference, never a proposal
        cols.append(("Counter (Reference)" if o.get("action") == "INCOMPLETE" else "Proposed Counter", o["ns_counter"]))
    return {
        "id": o["id"], "label": o["label"], "buyer": o["buyer"], "buyer_agent": o.get("buyer_agent") or "", "price": money(o["price"]), "financing": fin_str(o),
        "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]), "counter_net": money(o["ns_counter"]["net_adj"]),
        "downside_note": downside_note(o, L), "downside_counts": downside_hits(o),  # OFR-258
        "downside_checked": downside_checked(o),  # OFR-301
        "score": o["score"]["total"], "band": o["score"]["band"][1], "action": o.get("action"),
        "close": f"{o['close']:%a %b %-d}", "firm_date": f"{firm_day(o, costs)[0]:%a %b %-d}",
        "flags": [f"{f['sev']}: {f['issue']} {f['fix']}" for f in o["flags"]],
        "flag_keys": [f["topic"] for f in o["flags"] if f.get("topic")],
        "biggest_risk": f"{br['sev']}: {br['issue']}" if br else None,  # OFR-274, OFR-304
        "biggest_risk_key": br["key"] if br else None,
        "net_sheet": {"columns": [c for c, _ in cols],
                      "rows": [{"label": r["label"], "values": [money(v) for v in r["values"]]} for r in net_sheet_rows(cols)]
                      + [{"label": "Holding Costs Until Closing", "values": [money(c["holding"]) for _, c in cols]},
                         {"label": "Net After Holding Costs", "values": [money(c["net_adj"]) for _, c in cols]}]},
    }


def result(R, mode="auto", offer_id=None):
    mode, o = pick(R, mode, offer_id)
    view = single_view(R, o) if mode == "single" else multi_view(R)
    L = R["listing"]
    sid = review_scope(R, mode, o)
    offers = [o] if mode == "single" else R["ranked"]
    checked = offers if mode == "single" else R["ranked"] + R["incomplete"]  # OFR-114: a blocked offer still gets its chat notes
    return {
        "ok": True, "mode": mode, "property": L.get("address") or "", "list_price": money(L["list_price"]),
        "value_range": f"{money(L['cma_low'])}–{money(L['cma_high'])}" if L["cma_provided"] else "not provided",
        # OFR-288: a range the agent gave (not a --cma handoff) is confirmed in one chat line
        "value_range_confirm": (f"Using your CMA's {money(L['cma_low'])}–{money(L['cma_high'])} range."
                                if L["cma_provided"] and not L.get("cma_source") else None),
        "deadline_note": (f"The seller's {R['seller']['deadline']:%b %-d} deadline is {deadline_note(R['seller'])}."  # OFR-296
                          if deadline_note(R["seller"]) else None),
        "summary": view,
        "offers": [offer_detail(x, R) for x in offers],
        "to_confirm": to_confirm(R, offer_id=sid),  # OFR-352
        "estimated_costs": estimated_costs(R, offers),  # OFR-272: named in one line in every quick answer
        # OFR-352: the list the report shows, the one the Preliminary line and the data note count
        "assumptions": [{"impact": a["impact"], "where": place(R, a, sid), "what": a["why"], "field": a["field"]}
                        for a in listed_assumptions(R, mode == "multi", sid)],
        "cost_notes": L["cost_notes"],
        "market_notes": R["market_notes"],
        # chat only (never on the report): the best-effort line for a contract that isn't FAR/BAR, and revision notes
        **described_support(oe.cf.support([x["contract_form"] for x in checked],  # TL-201: "the footer reads" only when read from it
                                          [(x["contract_form"], x.get("form_revision"),
                                            str(x.get("form_revision_source") or "").lower() == "footer") for x in checked]),
                            checked),
    }


def described_support(sup, offers):
    """(iteration 10 eval 3: render.py uses this too, so chat and stderr carry one line) The support result with the best-effort line reworded when no best-effort offer names a contract form."""
    other = [x for x in offers if x["contract_form"] == oe.cf.OTHER]
    if other and not any(x.get("form_given") for x in other):
        sup["chat_notes"] = [oe.cf.DESCRIBED_NOTE if n == oe.cf.BEST_EFFORT_NOTE else n for n in sup["chat_notes"]]
    return sup


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("listing")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single-offer report")
    ap.add_argument("--profile", help="the agent's profile.md: its brokerage is checked against the contracts' listing side")
    a = ap.parse_args(argv)
    try:
        with open(a.listing, encoding="utf-8") as f:
            data = json.load(f)
        R = analyze(data, cma=load_cma(data, a.cma), agent=profiles.load_agent(a.profile) if a.profile else None)
        out = result(R, a.mode, a.offer)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
