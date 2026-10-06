"""Analyze the offers on a listing: net sheets, downside, certainty, counter, ranking, and the one document model every
output reads.

    python3 scripts/review.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID] [--profile profile.md]

Prints JSON with every value already formatted (shared/fmt): the page-1 summary (`summary`, the same one the PDF shows),
each offer's net sheet, the assumptions ranked by impact, the notes, and `doc`, everything else the PDF places. Or
{"ok": false, "problems": [...]}. render.py places this same result (render.main's compute step), so chat, markdown and
PDF agree. See references/listing-file.md for the input.

Every label and sentence this script writes is a template in assets/labels.json. Notes go through one notes.Notes
registry per document, keyed like the assumption that says the same thing, so each is said once and no label carries
one. Text the model writes (the terms reason, the priority note, names, checklist notes, the issues it
read in a contract) is checked for figures (prose.figures): the script prints every figure itself. The input is never
changed.
"""
import argparse
import copy
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import fmt, handoff, notes, offer_engine as oe, profiles, prose  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "labels.json")
with open(LABELS_PATH, encoding="utf-8") as _f:
    L_ = json.load(_f)

money = fmt.money
STATUS = {"g": "good", "a": "caution", "r": "risk"}


def t(_key, **kw):
    """A labels.json template, filled."""
    return fmt.fill(L_[_key], **kw)


def signed(v):
    return fmt.money(v, style="signed")


def acct(v):
    """A net sheet amount: costs in parentheses."""
    return fmt.money(v, style="accounting")


def cap(text):
    return text[:1].upper() + text[1:]


def low_first(text):
    return text[:1].lower() + text[1:]


def day(d):
    """'Nov 13' (fmt.date_short without the year: the review's year is on the page)."""
    return fmt.date_short(d, year=False)


def wday(d):
    """'Fri Nov 13'."""
    return fmt.when(d)


# --- inputs ------------------------------------------------------------------

def load_cma(data, cma_path=None):
    """The CMA handoff: --cma file first, else a handoff stored in the listing file under 'cma'."""
    if cma_path:
        return handoff.load(cma_path)
    if isinstance(data.get("cma"), dict):
        return handoff.validate(data["cma"])
    return None


# A contract reference keeps its digits ("paragraph 1", "Para. 9(c)", "Rider GG", "line 145", "AGA-1"): it names where
# something is, not a figure the report prints
_REFERENCE = re.compile(r"\b(?:para(?:graph)?s?\.?|section|lines?|pages?|riders?|counter(?:\s+offer)?|co|addendum|item|"
                        r"box|s\.)\s*#?\s*\d+[\w().-]*|\b[A-Z]{1,6}-\d+[A-Z]?\b", re.I)


def figures(text, references=False):
    """The figures in model-written text (prose.figures); with `references`, a contract reference keeps its digits."""
    s = str(text or "")
    return prose.figures(_REFERENCE.sub(" ", s) if references else s)


def text_problems(data):
    """Model-written text that states a figure, as `field: problem → fix` lines (every one at once). The report prints
    every price, amount, date and count itself, so judgment and names are words only, and an issue read in a contract
    says what's wrong without restating its numbers (the terms tables show them)."""
    probs = []

    def check(where, text, what, references=False):
        found = figures(text, references)
        if found:
            probs.append(f"{where}: {text!r} has a figure in it ({', '.join(found)}) → {what}")
        who = [] if references else prose.people(text)  # a contract reference's field quotes the contract: data
        if who:
            probs.append(f"{where}: {text!r} describes the people ({', '.join(who)}) → {prose.PEOPLE_FIX}")

    words = "say it in words; the report prints every price, amount and date itself"
    if data.get("ranking_reason"):
        check("ranking_reason", data["ranking_reason"], "give the terms reason in words (price, terms, financing, "
              "timing), never a figure; the ranking table prints them")
    seller = data.get("seller") or {}
    if seller.get("priority_note"):
        check("seller.priority_note", seller["priority_note"], "the priority in words (\"close before the deadline; "
              "certainty over top dollar\"); the deadline date goes in seller.deadline")
    hoa = (data.get("listing") or {}).get("hoa_conflict")
    if isinstance(hoa, str):
        check("listing.hoa_conflict", hoa, 'give the amounts as a list, [{"amount": 95, "per": "quarter"}, '
              '{"amount": 95, "per": "month"}], or true')
    for o in data.get("offers") or []:
        w = f"offers[{o.get('id', '?')}]"
        if o.get("label"):
            check(f"{w}.label", o["label"], "name the offer in words (the buyer's agent and brokerage); the report adds "
                  "the price itself")
        stance_reason = (o.get("counter") or {}).get("stance_reason") if isinstance(o.get("counter"), dict) else None
        if isinstance(stance_reason, str) and stance_reason.strip():
            check(f"{w}.counter.stance_reason", stance_reason, "say why this stance in words (the market, the seller's "
                  "goal, the buyer's terms); the counter table prints every price and amount")
        for k, v in (o.get("checklist") or {}).items():
            if isinstance(v, dict) and v.get("note"):
                check(f"{w}.checklist.{k}.note", v["note"], words)
        for i, f in enumerate(o.get("flags") or []):
            for part in ("issue", "fix"):
                check(f"{w}.flags[{i}].{part}", f.get(part), words + "; a contract reference (Para. 9(c)) is fine", True)
        for i, c in enumerate(o.get("contract_issues") or []):
            for part in ("issue", "fix", "request"):
                check(f"{w}.contract_issues[{i}].{part}", c.get(part),
                      "say what's wrong in words; the terms tables print the contract's amounts and dates, and a "
                      "contract reference (paragraph 1, Para. 9(c), Rider GG) is fine", True)
    return probs


def hoa_conflict(listing):
    """listing.hoa_conflict for the engine: true, or the amounts as words the script wrote ("$95 per quarter in one
    package, $95 per month in another"); a figure-free string passes as it is."""
    v = listing.get("hoa_conflict")
    if isinstance(v, list):
        parts = [t("hoa_amount", amount=money(x.get("amount") or 0), per=x.get("per") or "month") for x in v
                 if isinstance(x, dict)]
        if len(parts) >= 2:
            return t("hoa_conflict_two", a=parts[0], b=parts[1]) if len(parts) == 2 else "; ".join(parts)
        return True
    return v


def analyze(data, market=None, cma=None, agent=None):
    """The engine's analysis plus the review's own checks. `agent`: the profile (profiles.load_agent), for the
    listing-side check; without one, only the offers are compared with each other. Never changes `data`."""
    probs = text_problems(data)
    if probs:
        raise oe.OfferError("\n".join(probs))
    data = copy.deepcopy(data)
    if (data.get("listing") or {}).get("hoa_conflict") is not None:
        data["listing"]["hoa_conflict"] = hoa_conflict(data["listing"])
    R = oe.analyze(data, market=market, cma=cma)
    one_target(R)
    R["highest_and_best"] = highest_and_best(data.get("listing") or {}, R["listing"])
    backup_lapses(R)
    for o in R["offers"]:
        confirm_assumed_inspection(o, R["listing"])
        counter_restatements(o)
        order_flags(o)
    ask_year_built(R)
    ask_hoa_rider(R)
    ask_compensation_agreement(R)
    confirm_listing_side(R, (agent or {}).get("brokerage"))
    R["ranking_reason"] = str(data.get("ranking_reason") or "").strip() or None  # OFR-279
    return R


# --- after the engine ----------------------------------------------------------

def one_target(R):
    """One Seller's Target for every report on the listing (the comparison's chart and each single review): a clean
    offer at list closing on the engine's report_target_close (the recommended offer's date). Each offer's target keeps
    its own title terms (OFR-103) and commission lines; the chart's has the listing broker pay the buyer's broker only
    when it does on every active offer (OFR-339)."""
    top = R["ranked"][0] if R["ranked"] else None
    if not top:  # nothing ranked: the engine's report target stands
        return
    close = R["target_close"]
    L, S, costs = R["listing"], R["seller"], R["costs"]
    for o in R["offers"]:
        if o["close"] != close:
            o["target"] = oe.target_net(L, S, costs, close, o)
    by_listing = all(o.get("bb_from_listing") for o in R["active"])
    R["target"] = (top["target"] if by_listing == bool(top.get("bb_from_listing")) else
                   oe.target_net(L, S, costs, close, top, bb_from_listing=by_listing))


# Listing-side reminders (the seller's own paperwork), not risks in the offer: listed last, never a top risk (OFR-274)
# OFR-343: the HOA figure is the listing's to confirm; iteration 10 eval 5: Rider K's watch items are terms to agree,
# listed with the risk flags but never a top risk
HOUSEKEEPING = {"flood_disclosure", "hoa_conflict", "rider_K_terms"}
# Deal-specific risks first, within a severity level: a passed time for acceptance (whether there's an offer to answer),
# sale contingency, then financing, then appraisal gap, then the seller's deadline (OFR-274). Every flag has a topic
# (offer_engine), so the order uses keys, never words.
RISK_ORDER = ("expired", "backup_lapses", "sale_contingency", "financing", "appraisal_gap", "past_deadline")
RISK_GROUP = {"approval_cap": "financing", "concessions_cap": "financing", "fha_gap_intent": "appraisal_gap",
              "escalation_cap_over_approval": "financing", "escalation_cash_short": "financing",
              "prequal": "financing", "loan_limit_fha": "financing"}


def risk_topic(f):
    t_ = f.get("topic")
    return RISK_GROUP.get(t_, t_)


def order_flags(o):
    """Blocking, then High, Med, Low; within a level the deal-specific risks lead; listing-side reminders go last."""
    sev = {"Blocking": -1, "High": 0, "Med": 1, "Low": 2}
    rank = {t_: i for i, t_ in enumerate(RISK_ORDER)}
    o["flags"] = sorted(o["flags"], key=lambda f: (f.get("topic") in HOUSEKEEPING, sev.get(f["sev"], 1),
                                                     rank.get(risk_topic(f), len(RISK_ORDER))))


def expires_at(o):
    """An offer's time for acceptance as a datetime (a date alone is the end of that day), or None when it isn't a date."""
    return time_of(o.get("expires_raw"))


def time_of(raw):
    """A deadline's 'YYYY-MM-DD HH:MM' (or date alone: the end of that day) as a datetime, or None."""
    raw = str(raw or "").strip()
    for f, n in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            when = datetime.strptime(raw[:n], f)
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
        past = fmt.when(due)
        # OFR-342: with highest and best pending, nothing is answered before the deadline, so only the extension fits
        hold = (R.get("highest_and_best") or {}).get("pending")
        o["lapses_before"] = {"until": past, "ends": fmt.when(when), "offer": top["label"], "ref": top["ref"]}
        o["flags"].append({"sev": "Med", "topic": "backup_lapses",
                           "issue": t("flag_backup_lapses", expires=o["expires"], offer=top["label"], until=past),
                           "fix": t("fix_backup_extend" if hold else "fix_backup_extend_or_answer", until=past)})


def highest_and_best(raw, L):
    """OFR-320: a call for highest and best already out (the NMOB-1 deadline, `listing.highest_and_best_due`): {due,
    pending}, or None. Pending until the deadline's day has passed: the analysis date has no time of day."""
    v = raw.get("highest_and_best_due")
    if not v:
        return None
    try:
        d = oe._d(v)
    except ValueError:
        return {"due": str(v), "pending": True}
    when = oe.fmt_when(v) + (t("end_of_day") if len(str(v).strip()) == 10 else "")
    return {"due": when, "pending": d >= L["analysis_date"], "raw": str(v)}


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
            n = L["norms"]["inspection_days"]  # iteration 10 eval 1: one number, as the Terms Review benchmark (≤n days)
            f["issue"] = t("flag_inspection_assumed", days=o["inspection_days"])
            f["fix"] = t("fix_inspection_assumed", norm=n)


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
        term = L_["change_rows"].get(key, cap(name))
        if term not in have:
            extra.append((term, t("row_changed_offered", now=now, was=was), t("row_changed_counter", now=now, was=was),
                          L_["why_changed"]))
    loan, bal, dep = o.get("loan_amount"), o.get("balance_to_close"), o["deposit"]
    if bal is not None and dep is not None and (loan or not o["financed"]):
        total = dep + (loan or 0) + bal
        price = o["counter_terms"]["price"]
        if abs(total - o["price"]) > 100:  # the engine's loan_amount issue: a counter changed the price without them
            extra.append((L_["row_loan_balance"] if loan else L_["row_balance"], t("row_add_up", total=money(total)),
                          t("row_restated", price=money(price)), L_["why_add_up"]))
    if extra:
        last = rows[-1] if rows[-1][0] == "Time for Acceptance" else None
        o["counter_rows"] = [r for r in rows if r is not last] + extra + ([last] if last else [])


def ask_year_built(R):
    """OFR-280: with riders read from a FAR/BAR package, the lead-based paint check needs the year built; without it
    the check can't run, so the review asks for it."""
    L = R["listing"]
    if L.get("year_built") or L.get("built_before_1978") in (True, False):  # OFR-295: the seller disclosure answers it
        return
    live = R["active"] + R["incomplete"]
    if not any(o["contract_form"] in oe.cf.FARBAR and o.get("rider_codes") for o in live):
        return
    a = {"scope": "listing", "field": "year_built", "value": None, "impact": "med", "why": L_["ask_year_built"]}
    R["assumptions"].insert(0, a)
    meds = [i for i, x in enumerate(R["missing"]) if x["impact"] != "high"]
    R["missing"].insert(meds[0] if meds else len(R["missing"]), a)


def ask_compensation_agreement(R):
    """OFR-299: Rider GG puts the buyer's broker compensation in a separate compensation agreement. When the package
    doesn't give the amount, the review asks for the signed agreement (it's in ALWAYS_ASK), folding in the offer's
    assumed buyer-broker share so the question is asked once."""
    for o in R["active"] + R["incomplete"]:
        if o.get("bb_tag") == "Requested" or not o.get("gg_open"):
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
        net = (t("gg_net_assumes", pct=oe.pct(o["buyer_broker_pct"])) if old and old["value"] else L_["gg_net_not_in"])
        a = {"scope": sc, "field": "compensation_agreement", "value": None,
             "impact": old["impact"] if old else "med", "why": t("ask_compensation_agreement", net=net)}
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
    given = [(str(o.get("listing_brokerage") or "").strip(), o) for o in live]
    given = [(n, o) for n, o in given if n]
    named = []  # one entry per firm, with every offer that names it
    for n, o in given:
        hit = next((x for x in named if same_firm(n, x[0])), None)
        if hit:
            hit[1].append(o)
        else:
            named.append((n, [o]))
    mine = str(profile_brokerage or "").strip()
    off = [(n, os_) for n, os_ in named if mine and not same_firm(n, mine)]
    if not (off or (not mine and len(named) > 1)):
        return
    shown = off or named
    # Round 3 case 05: one firm on every contract is named once ("both contracts name"), never with one offer's name in
    # brackets; different firms name each offer that carries them
    if len(named) == 1:
        count = len(named[0][1])
        whose = L_["lb_one"] if count == 1 else L_["lb_both"] if count == 2 else t("lb_all", n=count)
        names = f"{whose} {named[0][0]}"
    else:
        names = L_["lb_contracts"] + " " + " and ".join(f"{n} ({', '.join(o['label'] for o in os_)})" for n, os_ in shown)
    tail = t("lb_tail_profile", mine=mine) if mine else L_["lb_tail_each"]
    why = t("lb_why", names=names, tail=tail)
    one = tail if mine else L_["lb_tail_disagree"]  # a single review cites only its own contract
    single = {o["id"]: t("lb_why_single", name=n, tail=one) for n, os_ in shown for o in os_}
    # the agent's own brokerage and profile: asked in chat (`agent`), never on the seller's report
    a = {"scope": "listing", "field": "listing_brokerage", "value": shown[0][0], "impact": "med", "why": why,
         "why_single": single, "offers": list(single), "agent": True}
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
    a = {"scope": f"offer {unread[0]['id']}", "field": "riders", "value": "not checked", "impact": "med",
         "why": t("ask_hoa_rider", which=L_["condo_rider"] if L["condo"] else L_["hoa_rider"])}
    if len(unread) > 1:
        a["also"] = [f"offer {o['id']}" for o in unread[1:]]
    R["assumptions"].append(a)
    lows = [i for i, x in enumerate(R["missing"]) if x["impact"] == "low"]
    R["missing"].insert(lows[0] if lows else len(R["missing"]), a)


# --- assumptions, notes and what to confirm ----------------------------------------

def akey(a):
    """An assumption's note key: its field, and the offers it's scoped to (one key per fact, whichever way it falls)."""
    offers = sorted(s[6:] for s in oe.scopes(a) if s.startswith("offer "))
    return a["field"] + (":" + ",".join(offers) if offers else "")


def estimated_costs(R, offers, skip=()):
    """OFR-272: every cost line the net rests on that is a default or an estimate, in short phrases, so the quick answer
    can name them all in one line. Keyed like the assumptions; `skip`: keys the reply already asks about (to_confirm),
    so nothing is said twice."""
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
        rest = ""
        if mixed:
            rest = t("est_commission_rest", listing=oe.pct(S["listing_fee_pct"])) + (
                t("est_commission_rest_bb", bb=oe.pct(S["default_buyer_broker_pct"] or 0))
                if bb_assumed and "bb" in lines else "")
        out.append(("listing_fee_pct", t("est_commission_total", total=total, rest=rest)))
    elif S["listing_fee_assumed"] or bb_assumed:
        what = [t("est_listing", pct=oe.pct(S["listing_fee_pct"])) if S["listing_fee_assumed"] else None,
                t("est_bb", pct=oe.pct(S["default_buyer_broker_pct"] or 0)) if bb_assumed and "bb" in lines else None]
        out.append(("listing_fee_pct", t("est_commission", what=", ".join(w for w in what if w))))
    src = costs.described
    rate = costs.get("closing_costs.deed_transfer_tax_rate")
    if rate and "transfer" in lines and costs.source("closing_costs.deed_transfer_tax_rate") != "deal":
        out.append(("transfer_tax_rate", t("est_transfer", name=words(lines["transfer"].split(" (")[0]),
                                           rate=fmt.pct(rate, 2, fixed=True), src=src("closing_costs.deed_transfer_tax_rate"))))
    if "title" in lines and "(Quote)" not in lines["title"]:
        out.append(("title_estimate_pct", t("est_title", how=L_["est_promulgated"] if "Promulgated" in lines["title"]
                                            else L_["est_estimate"])))
    if "settle" in lines and costs.source("closing_costs.seller_title_fees") != "deal":
        amounts = sorted({-v for o in offers for k, _, v in o["ns"]["lines"] if k == "settle"})
        out.append(("title_fees", t("est_title_fees", amount=fmt.range(amounts[0], amounts[-1]),
                                    src=src("closing_costs.seller_title_fees"))))
    tax = next((a for a in R["missing"] if a["field"] == "annual_tax" and isinstance(a["value"], (int, float))), None)
    discount = costs.get("property_tax.early_payment_discount")
    unpaid = any(o["ns"].get("tax_bill_assumed") for o in offers)  # OFR-313: local-costs.md, the reply says so
    extra = ((t("est_tax_discount", pct=fmt.pct(discount, None)) if discount else "")
             + (L_["est_tax_unpaid"] if unpaid else ""))
    if tax and "tax" in lines:  # OFR-303: worded as the math is ("of list price", or the listing's own rate)
        out.append(("annual_tax", (t("est_tax_rate", basis=L["tax_estimate"]) if L.get("tax_estimate") else
                                   t("est_tax_bill", amount=money(tax["value"]))) + extra))
    elif unpaid and "tax" in lines:
        out.append(("current_tax_bill_paid", L_["est_tax_unpaid_only"]))
    if "estoppel" in lines and any(o["ns"].get("estoppel_estimate") for o in offers):  # iteration 9 eval 1: HOA or condo only
        out.append(("hoa_estoppel_fee", t("est_estoppel", name=words(lines["estoppel"]))))
    if not L.get("repair_reserve_deal") and any(not o["repairs_owed"] and any(k == "repair" and v for k, _, v in o["ns_down"]["lines"])
                                                for o in offers):  # a Standard form's repair limits are contract terms
        out.append(("inspection_credit_reserve_pct", L_["est_repair"]))
    return [text for key, text in out if key not in skip]


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
        o["action"], o["action_reason"] = "DECLINE", t("status_reason", status=o["status"])
    return "single", o


def price_note(o):
    """Financing, plus how an escalating offer reached its price."""
    return fin_str(o) + (f" · {o['escalation_note']}" if o.get("escalation") else "")


def target_note(o, R=None):
    """The Seller's Target tile's caption, on the date its number closes on: one target per listing (R["target_close"],
    the engine's report_target_close)."""
    close = (R or {}).get("target_close") or o["close"]
    return t("target_note", close=day(close))


def fin_str(o):
    return oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else
                                            " · " + t("down", pct=fmt.pct(o["down_pct"], 1, fixed=True)))


def listed_assumptions(R, multi=False, offer_id=None, defaults=False):
    """The assumptions a report lists: all of them in a single review; in the comparison, the listing's and seller's,
    each offer's high-impact ones and any shared by several offers (the rest are in each offer's single review).
    OFR-257: the count in the data note comes from this same list, so it matches the table.
    OFR-344: `offer_id` (a single review of one of several offers) drops a listing assumption that applies only to
    other offers (`offers`: the tax bill question for an offer closing in November or December), and OFR-346 an
    assumption scoped only to other offers (their compensation agreement, their loan terms). A default commission
    (`default`) is a default, not an assumption, and an item about the listing agent's own business (`agent`: their
    listing agreement, their brokerage against their profile) is theirs to confirm: neither is listed or counted on the
    seller's report, unless `defaults` (the chat's questions)."""
    def mine(a):
        offers = [x for x in oe.scopes(a) if x.startswith("offer ")]
        return not offers or f"offer {offer_id}" in offers
    return [a for a in R["missing"] if (not multi or not a["scope"].startswith("offer ") or a["impact"] == "high"
                                        or a.get("also")) and (offer_id is None or (offer_id in a.get("offers", [offer_id])
                                                                                    and mine(a)))
            and (defaults or not (a.get("default") or a.get("agent")))]


# OFR-306: high-impact inputs that move every offer's net the same way, so they can't change the ranking (each is in
# the assumptions), and the contract form, one offer's own input (listed in the assumptions, never marked in the
# ranking: local-costs.md, estimates and assumptions are said once, in the notes)
SAME_FOR_EVERY_OFFER = {"payoff", "listing_fee_pct", "listing_fee_includes_buyer_broker", "state", "title_payer",
                        "deed transfer tax", "who pays owner's title", "owner's title rate", "title company fees"}
MARKED_PER_OFFER = {"contract_form"}


def ranking_deciding(a):
    return a["field"] not in SAME_FOR_EVERY_OFFER | MARKED_PER_OFFER


def form_assumed(R, o):
    """OFR-306: True when this offer's contract form was assumed (a high-impact input, listed in the assumptions)."""
    return any(a["field"] in MARKED_PER_OFFER and f"offer {o['id']}" in oe.scopes(a) for a in R["missing"])


def preliminary(R, offer_id=None, multi=False):
    """The Preliminary line, or None. OFR-306: the comparison carries it only when an input that could change the
    ranking is assumed; a single review, whenever one of its high-impact inputs is. It names what to add; the count of
    assumed inputs is the data note's (said once)."""
    name = lambda s: where(R, s)  # noqa: E731  OFR-266: an offer's missing input names the offers it's missing for
    need = oe.preliminary_inputs({**R, "missing": [a for a in R["missing"] if ranking_deciding(a)]} if multi else R,
                                 None if multi else offer_id, name_offer=name)
    if not need:
        return None
    if multi:  # the hint names every input that would change the numbers (the payoff too), not only the ranking's
        need = oe.preliminary_inputs({**R, "missing": [a for a in R["missing"] if a["field"] not in MARKED_PER_OFFER]},
                                     None, name_offer=name)
    return t("preliminary", what=", ".join(need[:-1]) + " and " + need[-1] if len(need) > 1 else need[0])


def data_note(R, multi=False, offer_id=None):
    """How many inputs the report assumed (the What to Confirm table lists them). The missing payoff and CMA are in the
    fact row and the table, so they aren't said again here."""
    shown = listed_assumptions(R, multi, offer_id)
    n, hi = len(shown), sum(a["impact"] == "high" for a in shown)
    if not n:
        return L_["data_all_given"]
    more = L_["data_more"] if multi and len(shown) < len(R["missing"]) else ""
    return t("data_note_one" if n == 1 else "data_note", n=n, hi=hi, more=more)


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
    assumed offer terms in ALWAYS_ASK (and any marked `ask`, e.g. an assumed listing fee under Rider GG), then other
    medium-impact gaps while there's room. OFR-352: `offer_id` (a single review of one of several offers) asks only
    what its own review lists."""
    pool = listed_assumptions(R, offer_id=offer_id, defaults=True) if offer_id else R["missing"]
    asked = [a for a in pool if a["impact"] in ("high", "med")]
    terms = [a for a in asked if a["field"] in ALWAYS_ASK or a.get("ask")]
    high = [a for a in asked if a["impact"] == "high" and a not in terms][:limit]
    med = [a for a in asked if a["impact"] == "med" and a not in terms][:max(0, limit - len(high) - len(terms))]
    return high + terms + med


def why_for(a, offer_id=None):
    """An assumption's wording for this report: a single review of one of several offers gets its own (`why_single`,
    round 3 case 05: it never cites another offer's contract), else the shared wording."""
    return (a.get("why_single") or {}).get(offer_id) or a["why"]


def to_confirm(R, limit=4, offer_id=None):
    out = []
    for a in confirm_items(R, limit, offer_id):
        why = why_for(a, offer_id)
        if why not in out:  # OFR-353: one question per ask, however many offers it covers
            out.append(why)
    return out


THREAT_KEYS = ("appraisal", "contingency", "timeline", "approval", "financing", "deposit", "property")
# OFR-304: a certainty criterion's score as a flag severity (4 and 5 are no threat)
THREAT_SEV = {1: "High", 2: "Med", 3: "Low"}
SEV_RANK = {"Blocking": 0, "High": 1, "Med": 2, "Low": 3}


def threat_key(o):
    """The scored certainty criterion that costs the most points (weight × shortfall), or None when every one scores
    4+ (a criterion that isn't scored is never the threat)."""
    weights = {k: w for k, _, w in oe.CRITERIA}
    s = o["score"]["scores"]
    scored = [k for k in THREAT_KEYS if s[k] is not None]
    worst = min(scored, key=lambda k: (-weights[k] * (5 - s[k]), THREAT_KEYS.index(k)))
    return None if s[worst] >= 4 else worst


def threat(o):
    k = threat_key(o)
    return L_["threat"][k] if k else L_["threat_none"]


def biggest_risk(o):
    """OFR-304: the one biggest risk, so it never disagrees with the certainty's threat: the top deal flag (listing-side
    reminders never count), unless the threat's criterion score is a higher severity (score 1 High, 2 Med, 3 Low); then
    the threat, with the scorecard's reason. {sev, issue, key} or None: `key` is the flag's topic, or `threat:<criterion>`."""
    flag = next(iter(deal_flags(o)), None)
    k = threat_key(o)
    sev = THREAT_SEV.get(o["score"]["scores"][k]) if k else None
    if sev and (flag is None or SEV_RANK[sev] < SEV_RANK.get(flag["sev"], 2)):
        return {"sev": sev, "issue": t("threat_issue", threat=L_["threat"][k], why=o["score"]["why"][k].rstrip(".")),
                "key": f"threat:{k}"}
    return {"sev": flag["sev"], "issue": flag["issue"], "key": flag.get("topic")} if flag else None


def firm_day(o, costs):
    """OFR-300: (the day the buyer's last cancel right really ends, the day it moved from or None): the last day of the
    longest window, rolled off a weekend or holiday by the market's contract rule (offer_engine.rolled), never past the
    closing (iteration 10 eval 1)."""
    return oe.rolled(o["firm_date"], costs, o["close"])


def open_after(o, wd):
    """Iteration 10 eval 2: what still lets the buyer cancel after the walk-away period, named (the loan approval, the
    appraisal, the sale of the buyer's home, each rider's window), so a later walk-away date reads as that window."""
    names = [L_[n] for n, d in (("open_loan", o["loan_approval_days"] if o["financed"] else 0),
                                ("open_appraisal", o["appraisal_days"]),
                                ("open_sale", o["sale_contingency_days"])) if d and d > wd]
    names += [t("open_rider", what=what, code=code) for code, d, what in o.get("rider_windows") or () if d > wd]
    if not names:
        return L_["open_default"]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def walk_away(o, costs):
    """(until, note): when the buyer's last cancel right ends, counted from acceptance (the Effective Date isn't set
    yet): the longest open window (OFR-267), AGA-1's included. AGA-1's renegotiation window only opens when the
    valuation plus the gap is below the price, so the note says the days after the other windows close are that
    condition. OFR-121: when the inspection walk-away (AS IS, Rider K or L) ends sooner, the note says until when the
    buyer may cancel for any reason. OFR-300: each date is rolled off a weekend or holiday as the contract rolls it."""
    ex = o.get("risk_days_ex_appraisal", o["risk_days"])
    found = []
    wd = o.get("walkaway_days") or 0
    if wd and wd < o["risk_days"]:
        start = o["firm_date"] - timedelta(days=o["risk_days"])
        end, _ = oe.rolled(start + timedelta(days=wd), costs, o["close"])
        form = f", {o['contract_label']}" if o["contract_form"] in oe.cf.FARBAR else ""
        found.append(t("walk_any_reason", end=day(end), days=wd, form=form, after=open_after(o, wd)))
    if o.get("appraisal_form") == "aga" and ex < o["risk_days"] == o["appraisal_days"]:
        first, _ = oe.rolled(o["firm_date"] - timedelta(days=o["risk_days"] - ex), costs, o["close"])
        found.append(t("walk_aga", first=day(first), days=ex))
    until, was = firm_day(o, costs)
    moved = t("walk_moved", was=wday(was)) if was else ""
    return t("walk_until", until=wday(until), days=o["risk_days"], moved=moved), " ".join(found) or None


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
        return L_["dn_both"]
    if hits == ["appraisal"]:
        return L_["dn_appraisal"]
    free = "appraisal" in downside_checked(o) and "appraisal" not in hits and not short
    at = L_["dn_at_top"] if L["cma_provided"] else L_["dn_at_list"]
    if hits == ["inspection"]:
        return L_["dn_inspection"] + (t("dn_free_tail", at=at) if free else "")
    if free:
        return t("dn_same_free", at=at)
    return L_["dn_same"]


def backup_form(o):
    """The backup contract's one name everywhere: the FAR/BAR rider by its name and letter (contract_forms), else a
    back-up addendum."""
    return t("backup_rider", name=oe.cf.rider_name("W")) if o["contract_form"] in oe.cf.FARBAR else L_["backup_addendum"]


def offer_name(o):
    """The offer's name inside a heading: 'the Morales (Palmetto Coast Realty) offer' -> 'Morales (Palmetto Coast
    Realty)'."""
    return o["ref"][4:-6] if o["ref"].startswith("the ") and o["ref"].endswith(" offer") else o["label"]


def title(action, o):
    """OFR-265: the recommendation as a heading that names the offer, "Counter the $382K FHA Offer", never
    "Counter: $382K FHA" (which reads like a counter at the offer's price)."""
    key = {"ACCEPT": "title_accept", "COUNTER": "title_counter", "BACKUP": "title_backup", "DECLINE": "title_decline",
           "INCOMPLETE": "title_incomplete"}.get(action)
    return t(key, name=offer_name(o)) if key else f"{action.title()}: the {offer_name(o)} Offer"


def respond_by(o):
    """The time for acceptance, or that it has passed (never a past date to beat)."""
    if not o.get("expires"):
        return L_["no_time"]  # OFR-120: a fact, not a place to look
    if o.get("lapsed") == "passed":
        return t("rb_passed", when=o["expires"])
    if o.get("lapsed") == "likely":
        return t("rb_likely", when=o["expires"])
    return short_when(o.get("expires_raw")) or o["expires"]


# Round 3 case 05: with a call for highest and best still out, the plan is to wait for the final offers and then decide;
# the counter (or acceptance) the review works out is only the fallback if the final offer doesn't improve
WAIT_HEADLINE, WAIT_TITLE = L_["wait_headline"], L_["wait_title"]


def waiting(R):
    hb = R.get("highest_and_best")
    return bool(hb and hb["pending"])


def fallback(o, where_=None, its=False):
    """'If the final Ostrander (Tidewater Key Realty) offer doesn't improve: counter at $504,000' (`where_`: where its
    full terms are, "below" or "the plan"; `its`: "If its final offer", right after a sentence that names it)."""
    name = L_["fb_its"] if its else t("fb_final", ref=o["ref"][4:] if o["ref"].startswith("the ") else o["ref"])
    if o["action"] != "COUNTER":
        return t("fb_accept", name=name)
    price = o["counter_terms"]["price"]
    what = t("fb_counter_at", price=money(price)) if price != o["price"] else L_["fb_counter"]
    return t("fb_if", name=name, what=what) + (f" ({where_})" if where_ else "")


def wait_option(hb):
    return {"option": L_["opt_wait"], "short": L_["opt_wait"], "net": fmt.EMPTY, "certainty": fmt.EMPTY,
            "status": "good", "recommended": True, "what": t("opt_wait_what", due=short_when(hb.get("raw")) or hb["due"])}


def wait_note(hb, o):
    """For the chat reply: the deadline to wait for and the fallback, in words."""
    return {"due": short_when(hb.get("raw")) or hb["due"], "fallback": fallback(o)}


def short_name(o, R):
    """An offer's name where space is tight (the Respond By box): the label's first part (the buyer's agent's surname),
    or the whole label when another offer's starts the same way."""
    first = o["label"].split(" · ")[0]
    if any(x is not o and x["label"].split(" · ")[0] == first for x in R["offers"]):
        return o["label"]
    return first


def wait_respond_by(R, hb, o, also):
    """(respond_by, respond_by_offer, respond_by_also) while waiting for final offers: the deadline first, then the
    fallback offer's own time for acceptance (the fallback has to go out before it) and the other deadlines."""
    out = []
    if expires_at(o) and not o.get("lapsed"):
        out.append({"when": short_when(o.get("expires_raw")) or o["expires"],
                    "what": t("rb_offer_expires", name=short_name(o, R)), "key": "offer_expires", "at": expires_at(o)})
    out += [a for a in also if a["key"] != "highest_and_best"]
    return short_when(hb.get("raw")) or hb["due"], L_["rb_hb_due"], out


def deadline_note(S):
    """OFR-296: a seller's deadline on a weekend isn't a closing day: the last business day before it is ('' otherwise)."""
    dl = S["deadline"]
    if not dl or dl.weekday() < 5:
        return ""
    return t("deadline_weekend", weekday=fmt.weekday(dl), close=wday(oe.prior_weekday(dl)))


def certainty(o, S, costs):
    dl = S["deadline"]
    wa = walk_away(o, costs)
    note = deadline_note(S)
    closing = (t("cert_closing_deadline", close=day(o["close"]), deadline=day(dl)) + (f" ({note})" if note else "")
               if dl else t("cert_closing_days", close=day(o["close"]), days=o["close_days"]))
    return {
        "score": o["score"]["total"], "band": o["score"]["band"][1], "band_class": o["score"]["band"][0],
        "score_text": t("score", n=o["score"]["total"]),
        "walk_away_until": wa[0], "walk_away_note": wa[1],
        "deposit": (t("deposit_share", amount=money(o["deposit"]), pct=fmt.pct(o["deposit"] / o["price"], 1, fixed=True))
                    if o["deposit"] is not None else L_["not_provided"]),
        "deposit_known": o["deposit"] is not None,
        "closing": closing, "closing_ok": (o["close"] <= dl) if dl else True,
        "threat": threat(o),
    }


ACCEPTANCE_TERM = "Time for Acceptance"  # the engine's acceptance_row: its times stay on one line


def row(term, offered, counter, why):
    return {"term": term, "offered": offered, "counter": counter, "why": why, "oneline": term == ACCEPTANCE_TERM}


def score_text(n):
    return t("score", n=n)


def stance_view(o):
    """The counter's stance for the report: its name (a label), the script's sentence for it, the suggestion, and the
    agent's reason (words only) when the stance differs from the suggestion."""
    st = o["counter_stance"]
    differs = st["stance"] != st["suggested"]
    return {"key": st["stance"], "name": L_["stance"][st["stance"]], "suggested": st["suggested"],
            "suggested_name": L_["stance"][st["suggested"]], "differs": differs,
            "line": L_["stance_line"][st["stance"]], "reason": st["reason"] if differs else None,
            "note": " ".join(x for x in (L_["stance_line"][st["stance"]], st["reason"] if differs else None) if x)}


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
        revive = {"note": L_["revive_note"], "rows": [row(*r) for r in o["counter_rows"]],
                  "summary": t("revive_summary", net=money(o["ns"]["net_adj"]), counter=money(cn))}
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": "INCOMPLETE", "headline": L_["headline_incomplete"], "title": title("INCOMPLETE", o),
        "why": t("why_incomplete" if not expired_only else "why_incomplete_expired", issues=low_first(issues)),
        "offers_active": len(R["active"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": respond_by(o), "respond_by_offer": o["label"] if o.get("expires") else None,
        "respond_by_also": [],
        "priority": S.get("priority_note") or S["priority"].title(),
        "fixes": [{"sev": f["sev"], "issue": f["issue"], "fix": f["fix"], "key": f.get("topic")} for f in fixes],
        "counter": None, "compare": None, "revive": revive,
        "kpis": [{"label": L_["kpi_price"], "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
                 {"label": L_["kpi_net_written"], "value": money(o["ns"]["net_adj"]), "note": L_["kpi_reference"], "tone": ""},
                 {"label": L_["kpi_downside"], "value": money(o["ns_down"]["net_adj"]), "note": downside_note(o, L), "tone": "risk"},
                 {"label": L_["kpi_target"], "value": money(o["target"]["net_adj"]), "note": target_note(o, R), "tone": ""}],
        "certainty": certainty(o, S, R["costs"]),
        # contract issues are in fixes; iteration 9 evals 1, 5: a listing-side reminder is never a top risk
        "risks": [{"sev": f["sev"], "issue": f["issue"], "key": f.get("topic")}
                  for f in deal_flags(o) if not f.get("contract")][:3],
        "terms_reason": None,  # iteration 11 eval 4: the pick's terms reason belongs to the pick, not a blocked offer
        "options": [],
        "preliminary": None,
        "next_step": cap(L_["next_incomplete"] if not expired_only else L_["next_incomplete_expired"]),
        "data_note": data_note(R, offer_id=o["id"] if R["mode"] == "multi" else None),
    }


CERTAINTY_GAP = 5  # points: a smaller difference in certainty scores is "about the same", never more or most certain


def certainty_side(diff):
    """1, -1 or 0: whether a difference in certainty points is big enough to call one side more certain (CERTAINTY_GAP).
    Every comparative certainty word the script writes goes through it."""
    return 0 if abs(diff) < CERTAINTY_GAP else (1 if diff > 0 else -1)


def counter_what(vs_offer, vs_downside, certainty_, act):
    """OFR-16: the Counter row says what actually changes: net up or down, certainty up or down."""
    net = (t("cw_net_up", d=signed(vs_offer)) if vs_offer >= 0 else
           t("cw_net_down", d=signed(vs_offer), dn=signed(vs_downside)))
    sure = {1: L_["cw_more"], -1: L_["cw_less"], 0: L_["cw_same"]}[certainty_side(certainty_)]
    pts = ("+" if certainty_ > 0 else fmt.MINUS) + str(abs(certainty_))
    text = (t("cw_points" if abs(certainty_) != 1 else "cw_point", net=net, sure=sure, pts=pts)
            if certainty_ else f"{net}; {sure}")  # OFR-290
    return text if act == "COUNTER" else text + L_["cw_risks"]


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
            s.append(t("why_over_list", price=money(o["price"]), over=money(o["price"] - L["list_price"]), less=money(tgt - ao)))
        elif ao < tgt:
            s.append(t("why_less", less=money(tgt - ao)))
        if any(f.get("topic") == "appraisal_gap" and not o["appraisal_protected"] for f in o["flags"]):
            s.append(L_["why_gap"])
        if o["sale_contingency_days"]:
            s.append(L_["why_sale"])
        risk = L_["why_cuts_risk"] if certainty_side(o["counter_score"] - o["score"]["total"]) > 0 else L_["why_same_risk"]
        s.append(t("why_lifts", lift=money(cn - ao), risk=risk) if cn >= ao else t("why_protects", d=signed(cn - dn)))
        why = " ".join(s)
    elif act == "ACCEPT":
        sc = o["score"]["total"]  # OFR-23: the wording follows the score band
        why = t("why_accept_strong" if sc >= 80 else "why_accept", net=money(ao), score=score_text(sc))
    else:
        why = t("why_other", reason=o.get("action_reason", ""), top=cap(top["ref"]))

    counter = None
    if act == "COUNTER" and o["counter_rows"]:
        n = len(o["counter_rows"])
        counter = {"rows": [row(*r) for r in o["counter_rows"]], "stance": stance_view(o),
                   "summary": t("counter_summary_one" if n == 1 else "counter_summary", n=n, net=money(ao), counter=money(cn),
                                d=signed(cn - ao), tail=t("counter_tail", d=signed(cn - dn)) if cn < ao else "")}

    compare = None
    if act in ("BACKUP", "DECLINE") and top is not o:
        compare = {"this": o["label"], "vs": top["label"], "rows": [
            [L_["cmp_price"], money(o["price"]), money(top["price"])],
            [L_["cmp_net"], money(ao), money(top["ns"]["net_adj"])],
            [L_["cmp_downside"], money(dn), money(top["ns_down"]["net_adj"])],
            [L_["cmp_certainty"], score_text(o["score"]["total"]), score_text(top["score"]["total"])],
            [L_["cmp_closing"], day(o["close"]), day(top["close"])]]}

    kpis = [{"label": L_["kpi_price"], "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
            {"label": L_["kpi_net"] if S["payoff_known"] else L_["kpi_net_pre"], "value": money(ao),
             "note": t("vs_target", d=signed(ao - tgt)), "tone": "risk" if ao < tgt else "good"},
            {"label": L_["kpi_downside"], "value": money(dn), "note": downside_note(o, L), "tone": "risk"}]
    if act == "COUNTER":
        kpis.append({"label": L_["kpi_counter"], "value": money(cn), "tone": "good",
                     "note": t("vs_offered", d=signed(cn - ao)) if cn >= ao else t("vs_downside_protects", d=signed(cn - dn))})
    else:
        kpis.append({"label": L_["kpi_target"], "value": money(tgt), "note": target_note(o, R), "tone": ""})

    score = o["score"]["total"]
    opts = [{"option": L_["opt_accept"], "net": money(ao), "certainty": score_text(score), "status": "good" if score >= 80 else "risk",
             "what": (L_["opt_accept_what"] if score >= 80 else
                      t("opt_accept_closer", net=money(dn), when=downside_note(o, L, short=True)) if dn < ao
                      else L_["opt_accept_risks"]),  # OFR-258: never "closer to" the same net
             "recommended": act == "ACCEPT"}]
    if o.get("lapsed") == "likely":  # iteration 10 eval 7: signing a counter whose time has likely passed may not bind
        opts[0].update(status="risk", what=t("opt_accept_likely", expires=o["expires"]))
    if o["counter_rows"]:
        opts.append({"option": L_["opt_counter"], "net": money(cn), "certainty": t("score_if", n=o["counter_score"]),
                     "status": "good" if act == "COUNTER" else "caution", "recommended": act == "COUNTER",
                     "what": counter_what(cn - ao, cn - dn, o["counter_score"] - score, act)})
    opts.append({"option": L_["opt_decline"], "net": fmt.EMPTY, "certainty": fmt.EMPTY, "status": "caution",
                 "recommended": act == "DECLINE", "what": t("opt_decline_what", holding=money(S["holding_monthly"]))})
    if act == "BACKUP":
        opts.insert(0, {"option": L_["opt_backup"], "net": money(ao), "certainty": score_text(score), "status": "caution",
                        "what": t("opt_backup_what", top=top["ref"], form=backup_form(o)), "recommended": True})

    expires = t("before", when=o["expires"]) if o.get("expires") and not o.get("lapsed") else ""
    nxt = {"COUNTER": t("next_counter", expires=expires), "ACCEPT": L_["next_accept"],
           "BACKUP": t("next_backup", form=backup_form(o)), "DECLINE": L_["next_decline"]}[act]
    held = next((x for x in R["ranked"][1:] if x.get("lapses_before")), None) if top is o else None
    if act == "COUNTER" and held:  # OFR-344: the plan's order, the backup's extension asked for before the counter goes out
        nxt = t("next_counter_extend", ref=held["ref"], until=held["lapses_before"]["until"], expires=expires)
    first = []
    hb = R.get("highest_and_best")
    if hb and hb["pending"]:  # OFR-320
        first.append(t("next_hb", due=hb["due"]))
    lapse = o.get("lapses_before")
    if act == "BACKUP" and lapse:  # OFR-319: the backup's own deadline ends before the counter to the top offer does
        first.append(t("next_backup_lapse", ends=lapse["ends"], offer=lapse["offer"], until=lapse["until"]))
    wait = waiting(R) and act in ("COUNTER", "ACCEPT")
    if first:
        nxt = " ".join(first) + (" " + fallback(o).split(":")[0] + ": " if wait else " " + L_["then"] + " ") + nxt
    headline, heading = (L_["headline_backup"] if act == "BACKUP" else act), title(act, o)
    rb, rb_offer, also = respond_by(o), (o["label"] if o.get("expires") else None), respond_also(R, shown=o)  # OFR-320
    if act == "BACKUP" and lapse:  # round 3 case 05: the comparison's label for this deadline, in every report
        rb_offer = L_["rb_backup"]
    if wait:  # round 3 case 05: the plan is to wait for the final offers; the counter is the fallback
        headline, heading = WAIT_HEADLINE, WAIT_TITLE
        why = t("why_wait", due=hb["due"], fallback=fallback(o, L_["below"])) + " " + why
        for x in opts:
            x["recommended"] = False
        opts.insert(0, wait_option(hb))
        rb, rb_offer, also = wait_respond_by(R, hb, o, also)
    own = expires_at(o) if not wait and o.get("expires") and not o.get("lapsed") else None
    held_back = act == "BACKUP" and lapse
    rb, rb_offer, also = time_ordered(rb, rb_offer, also, own, {
        "when": rb, "what": rb_offer if held_back else t("rb_offer_expires", name=short_name(o, R)),
        "key": "backup_lapses" if held_back else "offer_expires"})
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": act, "headline": headline, "title": heading, "why": why, "wait": wait_note(hb, o) if wait else None,
        "offers_active": len(R["active"]) if multi_ctx else 1, "offers_incomplete": len(R["incomplete"]) if multi_ctx else 0,
        "respond_by": rb, "respond_by_offer": rb_offer,
        "respond_by_also": also,
        "priority": S.get("priority_note") or S["priority"].title(),
        "counter": counter, "compare": compare, "kpis": kpis,
        "certainty": certainty(o, S, R["costs"]),
        # OFR-274, iteration 9 evals 1, 5: a listing-side reminder (the flood disclosure) is never a top risk
        "risks": [{"sev": f["sev"], "issue": f["issue"], "key": f.get("topic")} for f in deal_flags(o)[:3]],
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
        return L_["no_time"], (acted[0]["label"] if acted else None), None

    def when(o):  # OFR-263: a date alone is the end of that day
        s = str(o["expires_raw"]).strip()
        return s if len(s) > 10 else f"{s} 23:59"
    o = min(ex, key=when)
    return short_when(o.get("expires_raw")) or o["expires"], o["label"], o


def respond_also(R, held=(), shown=None):
    """OFR-319, OFR-320: the other deadlines the Respond By box shows: a pending call for highest and best, and a held
    offer whose own time for acceptance ends before the counter's. Iteration 10 evals 2, 4: and the earliest live time
    for acceptance among the active offers when the box doesn't already show it (`shown` is the offer Respond By names,
    or None), so an offer that lapses first is never hidden behind "No time stated". [{when, what, key}]"""
    out = []
    hb = R.get("highest_and_best")
    if hb and hb["pending"]:
        out.append({"when": short_when(hb.get("raw")) or hb["due"], "what": L_["rb_hb_due"], "key": "highest_and_best",
                    "at": time_of(hb.get("raw"))})
    out += [{"when": short_when(o.get("expires_raw")) or o["expires"], "what": L_["rb_backup"], "key": "backup_lapses",
             "at": expires_at(o)} for o in held]
    # OFR-305, iteration 11 eval 2: only an offer the plan keeps (accepted, countered or held), never a declined one
    live = [o for o in R["active"] if expires_at(o) and not o.get("lapsed") and o.get("action") != "DECLINE"]
    first = min(live, key=expires_at, default=None)
    if first and first is not shown and all(first is not o for o in held) and len(R["active"]) > 1:
        mine = expires_at(shown) if shown and not shown.get("lapsed") else None
        if mine is None or expires_at(first) < mine:
            # round 3 case 05: the plan's backup that lapses first carries the comparison's label in every report
            lapse = bool(first.get("lapses_before"))
            out.append({"when": short_when(first.get("expires_raw")) or first["expires"],
                        "what": L_["rb_backup"] if lapse else t("rb_offer_expires", name=short_name(first, R)),
                        "key": "backup_lapses" if lapse else "offer_expires", "at": expires_at(first)})
    return out


def time_ordered(rb, rb_offer, also, mine=None, mine_also=None):
    """Iteration 14: the Respond By box reads in time order. The other deadlines (`also`) are sorted by time; when one
    comes before this report's own deadline (`mine`, a datetime, with `mine_also` its entry once it moves), the
    earliest leads the box and this report's own deadline joins the rest. The working "at" key is dropped."""
    def key(a):
        return (a.get("at") is None, a.get("at") or datetime.max)
    also = sorted(also, key=key)
    if mine and also and also[0].get("at") and also[0]["at"] < mine:
        lead = also.pop(0)
        rb, rb_offer = lead["when"], lead["what"]
        also = sorted(also + [dict(mine_also, at=mine)], key=key)
    return rb, rb_offer, [{k: v for k, v in a.items() if k != "at"} for a in also]


def short_when(raw):
    """A deadline in the Respond By box's short form, "Wed Sep 23, 12:00 PM" (fmt.when; the box is narrow and the
    review's year is on the page), or None when it isn't a date and time."""
    return fmt.when(str(raw).strip()) if fmt.to_time(str(raw or "").strip()) else None


def ranked_financing(o):
    if not o["financed"]:
        return oe.FIN_LABEL[o["financing"]]
    return f"{oe.FIN_LABEL[o['financing']]} · {fmt.pct(o['down_pct'], 0 if o['down_pct'] >= .1 else 1)}"


def multi_view(R):
    S = R["seller"]
    rk = R["ranked"]
    top = rk[0]
    act = top["action"]
    backup = next((o for o in rk if o["action"] == "BACKUP"), None)
    hi_price = max(R["active"], key=lambda o: o["price"])
    lead = t("lead", top=cap(top["ref"]), close=day(top["close"]))
    lead += L_["lead_before_deadline"] if S["deadline"] and top["close"] <= S["deadline"] else "."
    if hi_price is not top:
        reason = hi_price["action_reason"]
        reason = (reason[:1].lower() + reason[1:]) if reason else L_["more_risk"]
        lead += " " + t("lead_high_price", label=hi_price["label"], price=money(hi_price["price"]),
                        rank=rk.index(hi_price) + 1, reason=reason)
    lapse = (backup or {}).get("lapses_before")
    if backup:
        lead += " " + t("lead_backup", ref=backup["ref"])  # OFR-282
    if lapse:  # OFR-319: its own deadline ends before the counter's
        lead += " " + t("lead_backup_lapse", ends=lapse["ends"])
    hb = R.get("highest_and_best")
    wait = waiting(R)  # round 3 case 05: wait for the final offers, then decide; the plan below is the fallback
    if wait:  # OFR-320: final offers are still coming in
        # iteration 14: "its" only when the sentence before names the top offer alone (no backup or higher price after it)
        its = backup is None and hi_price is top
        lead = t("lead_wait", due=hb["due"], lead=lead[:1].lower() + lead[1:], fallback=fallback(top, L_["the_plan"], its=its))
    if R["incomplete"]:
        n = len(R["incomplete"])
        names = ", ".join(x["label"] for x in R["incomplete"])
        lead += " " + t("lead_incomplete_one" if n == 1 else "lead_incomplete", n=n, names=names)
    top_net = top["ns_counter"]["net_adj"] if act == "COUNTER" else top["ns"]["net_adj"]

    terms = {}
    for o in rk:
        a = o["action"]
        if o is top and a == "COUNTER":
            t_ = (L_["terms_wait_counter"] if wait else L_["terms_counter"]) + \
                " · ".join(f"{r[0].lower()} {r[2]}" for r in o["counter_rows"][:5])
        elif o is top:
            t_ = L_["terms_wait_accept"] if wait else L_["terms_accept"]
        elif a == "BACKUP":
            # OFR-251: the backup keeps its own price; a counter price would read as an ask. Only an escalated price
            # differs from what the buyer wrote, and then the note says so
            t_ = t("terms_backup", top=top["label"], form=backup_form(o)) + (
                t("terms_escalated", price=money(o["price"])) if o.get("escalated") else "")
            if o.get("lapses_before"):  # OFR-319: the first step, or the backup lapses before it can be used
                t_ = t("terms_extend_first", ends=o["lapses_before"]["ends"], until=o["lapses_before"]["until"]) + " " + t_
        else:
            t_ = o["action_reason"]
        terms[o["id"]] = t_
    how = L_["counter_word"] if act == "COUNTER" else L_["as_written"]
    summary = t("plan_summary", ref=top["ref"], how=how, net=money(top_net))
    if wait:
        summary = t("plan_summary_wait", how=L_["counter_word"] if act == "COUNTER" else L_["offer_as_written"],
                    net=money(top_net))
    if act == "COUNTER":
        summary += " (" + t("vs_offered", d=signed(top_net - top["ns"]["net_adj"]))
        summary += (", " + t("vs_downside", d=signed(top_net - top["ns_down"]["net_adj"])) + ")"
                    if top_net < top["ns"]["net_adj"] else ")")
    # OFR-289: every plan says it (counter-rules.md), an acceptance plan too: one counter or acceptance at a time
    note = t("plan_note", doing=L_["responding_to"] if act == "COUNTER" else L_["moving_forward"])

    # OFR-351: `id` is what --offer takes, for each offer's single review after the comparison
    ranked = [{"rank": i + 1, "offer": o["label"], "key": o["key"], "id": o["id"], "financing": ranked_financing(o),
               "price": money(o["price"]) + (L_["escalated_tag"] if o.get("escalated") else ""),
               "price_display": money(o["price"]), "escalated": bool(o.get("escalated")),
               "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]),
               "score": o["score"]["total"], "band_class": o["score"]["band"][0], "risk_days": o["risk_days"],
               "walk": t("walk_days", n=o["risk_days"]),
               "close": day(o["close"]), "action": L_["act_backup"] if o["action"] == "BACKUP" else
               L_["act_wait"] if wait and o is top else o["action"].title(),
               "status": {"ACCEPT": "good", "COUNTER": "good", "BACKUP": "caution", "DECLINE": "risk"}[o["action"]],
               "terms": terms[o["id"]], "form_assumed": form_assumed(R, o),
               "escalation": oe.escalation_terms(o)} for i, o in enumerate(rk)]  # iteration 12: base, increment, cap
    ranked += [{"rank": fmt.EMPTY, "offer": o["label"], "key": o["key"], "id": o["id"], "financing": ranked_financing(o),
                "price": money(o["price"]), "price_display": money(o["price"]), "escalated": False,
                "net": fmt.EMPTY, "downside": fmt.EMPTY, "score": fmt.EMPTY, "band_class": "na", "risk_days": fmt.EMPTY,
                "walk": fmt.EMPTY, "close": day(o["close"]), "action": L_["act_incomplete"], "status": "risk",
                # OFR-120: only the first letter goes lowercase, so dates and times keep their case
                "terms": t("terms_incomplete", issue=low_first(o["blocking"][0]["issue"].rstrip("."))),
                "form_assumed": form_assumed(R, o), "escalation": oe.escalation_terms(o)}
               for o in R["incomplete"]]

    most_certain = max(R["active"], key=lambda o: (o["score"]["total"], o["ns_down"]["net_adj"]))
    verb = L_["counter_verb"] if act == "COUNTER" else L_["accept_verb"]
    first = f"{verb} {top['label']}" + (t("opt_hold", label=backup["label"]) if backup else "")
    # OFR-324: `short` names offers by the key the plan table shows beside each label, for the PDF's narrow Option column
    short = f"{verb} {top['key']}" + (t("opt_hold", label=backup["key"]) if backup else "")
    opts = [{"option": first, "short": short, "net": money(top_net), "recommended": True, "status": "good",
             "certainty": t("score_approx", n=top["counter_score"]) if act == "COUNTER" else score_text(top["score"]["total"]),
             "what": L_["opt_plan_what"] + (t("opt_plan_safety", ref=backup["ref"]) if backup else "")}]
    g = top["ns_counter"]["net_adj"] - top["ns"]["net_adj"]
    if act == "ACCEPT" and top["counter_rows"] and g > 0:  # OFR-116: never "Only +$0"
        opts.append({"option": t("opt_counter_anyway", label=top["label"]), "short": t("opt_counter_anyway", label=top["key"]),
                     "net": money(top["ns_counter"]["net_adj"]), "recommended": False,
                     "certainty": t("score_approx", n=top["counter_score"]), "status": "caution",
                     "what": t("opt_counter_anyway_what", gain=signed(g))})
    if most_certain is not top:
        plan_score = top["counter_score"] if act == "COUNTER" else top["score"]["total"]
        opts.append({"option": t("opt_accept_now", label=most_certain["label"]),
                     "short": t("opt_accept_now", label=most_certain["key"]),
                     "net": money(most_certain["ns"]["net_adj"]), "recommended": False,
                     "certainty": score_text(most_certain["score"]["total"]), "status": "caution",
                     "what": t("opt_accept_now_what", close=day(most_certain["close"]),
                               sure=L_["now_most" if certainty_side(most_certain["score"]["total"] - plan_score) > 0
                                       else "now_same"],
                               less=money(top_net - most_certain["ns"]["net_adj"]))})
    if not hb:  # OFR-320: a call for highest and best already out isn't offered again
        opts.append({"option": L_["opt_hb"], "net": L_["unknown"], "certainty": L_["varies"], "status": "caution",
                     "recommended": False, "what": L_["opt_hb_what"]})
    if wait:  # the plan's response is the fallback once the final offers are in
        opts[0].update(recommended=False, what=L_["opt_fallback_what"])
        opts.insert(0, wait_option(hb))
    verb2 = L_["send_counter_to"] if act == "COUNTER" else L_["accept_lower"]
    nxt = (t("next_hb", due=hb["due"]) + " " + fallback(top).split(":")[0] + ": " if wait else "")
    body = t("next_plan", extend=t("next_plan_extend", ref=backup["ref"], until=lapse["until"]) if lapse else "",
             verb=verb2, ref=top["ref"], backup=t("next_plan_backup", ref=backup["ref"]) if backup else "")
    nxt += body if nxt else cap(body)
    rb = first_expiry(R)
    also = respond_also(R, [backup] if lapse else [], shown=rb[2])
    if wait:
        when, what, also = wait_respond_by(R, hb, top, also)
        rb = (when, what, top)
    _, _, also = time_ordered(rb[0], rb[1], also)  # the comparison's box leads with the plan's deadline; the rest by time
    keys =(["backup_lapses"] if lapse else []) + (
        [f"highest_and_best_{'pending' if hb['pending'] else 'done'}"] if hb else [])
    return {
        "mode": "multi", "offer": top["id"], "offer_label": top["label"], "action": act,
        "headline": WAIT_HEADLINE if wait else act, "title": WAIT_TITLE if wait else title(act, top), "why": lead,
        "wait": wait_note(hb, top) if wait else None, "who": t("leading_now", label=top["label"]) if wait else None,
        "offers_active": len(R["active"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": rb[0], "respond_by_offer": rb[1], "respond_by_also": also,
        "plan_keys": keys,  # OFR-319, OFR-320: what the plan adds, as keys
        "priority": S.get("priority_note") or S["priority"].title(),
        "plan_summary": summary, "plan_note": note, "ranked": ranked, "options": opts,
        "counter_stance": stance_view(top) if act == "COUNTER" and top["counter_rows"] else None,
        "preliminary": preliminary(R, top["id"], multi=True), "next_step": cap(nxt), "data_note": data_note(R, multi=True),
        "target_net": money(R["target"]["net_adj"]),
        "terms_reason": R.get("ranking_reason"),  # OFR-279: the agent's terms reason for the pick, shown on the report
    }


# --- detail: net sheet, terms, timeline, scorecard, questions ----------------------------

def net_sheet_rows(cols):
    """[{key, label, values[]}] for columns of net sheets; rows that are zero everywhere are skipped (except price and
    concessions)."""
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


def sheet_columns(o, with_target=False):
    cols = [(L_["col_offered"], o["ns"]), (L_["col_downside"], o["ns_down"])]
    if o["counter_rows"]:  # OFR-354, DS-106: a lapsed offer's counter is for reference, never a proposal
        cols.append((L_["col_counter_ref"] if o.get("action") == "INCOMPLETE" else L_["col_counter"], o["ns_counter"]))
    if with_target:
        cols.append((L_["col_target"], o["target"]))
    return cols


def net_sheet(o, R, with_target=True):
    """The net sheet as the report shows it: one column per case, every row a ledger line (offer_engine.net_sheet), so
    each column's lines add to its net; then holding costs, the net after holding and the gap to the target. Each cell
    carries its amount and its text (fmt, accounting style)."""
    cols = sheet_columns(o, with_target)
    tgt = o["target"]["net_adj"]

    def cells(vals, cls=None):
        return [{"amount": v, "text": acct(v), "neg": v < 0, **({"cls": cls(v)} if cls else {})} for v in vals]
    rows = [{"key": r["key"], "label": r["label"], "cells": cells(r["values"])} for r in net_sheet_rows(cols)]
    return {
        "columns": [c for c, _ in cols], "rows": rows,
        "net": {"label": L_["row_net"], "cells": cells([c["net"] for _, c in cols])},
        "holding": {"label": L_["row_holding"], "cells": cells([c["holding"] for _, c in cols])},
        "net_adj": {"label": L_["row_net_adj"], "cells": cells([c["net_adj"] for _, c in cols],
                                                               lambda v: "best" if v >= tgt else "worst" if v < tgt - 5000 else "")},
        "vs_target": {"label": L_["row_vs_target"],
                      "cells": [{"amount": None, "text": fmt.EMPTY if n == L_["col_target"] else signed(c["net_adj"] - tgt)}
                                for n, c in cols]},
    }


def downside_caption(o, R):
    """What the Downside Case column assumes for this offer (OFR-258: the appraisal part only when a low appraisal cuts
    this price; OFR-127: why the columns match when nothing does)."""
    L = R["listing"]
    ref = t("ref_top_value", value=money(oe.appraisal_line(L))) if L["cma_provided"] else L_["ref_list"]
    gap = t("cap_gap", gap=money(o["appraisal_gap"])) if o["appraisal_gap"] else ""
    repairs = ("" if not o["repair_reserve"] else t("cap_repairs_limit", amount=money(o["repair_reserve"]))
               if o["repairs_owed"] else t("cap_credit", amount=money(o["repair_reserve"])))
    if "appraisal" in downside_hits(o):
        return t("cap_appraisal", ref=ref, gap=gap) + (f" + {repairs}" if repairs else "")
    if repairs:
        return f"{repairs}; " + (t("cap_not_cut", ref=ref) if o["appraisal_risk"] else L_["cap_no_contingency"])
    return (t("cap_matches", ref=ref) if o["appraisal_risk"] else L_["cap_matches_none"]) + L_["cap_no_repair"]


def target_basis(R, o):
    """The target's closing basis in words: one target per listing, on the recommended offer's closing date."""
    close = R.get("target_close") or o["close"]
    return L_["tb_same"] if close == o["close"] else t("tb_other", close=day(close))


def term_rows(o, R):
    """[(label, offered, benchmark, status, note)]: each term against the seller's preference or the local norm (one
    set of norms for the review and the counter: L["norms"])."""
    L, S = R["listing"], R["seller"]
    rows = []
    T = L_["term"]
    ref = t("bench_cma", range=fmt.range(L["cma_low"], L["cma_high"])) if L["cma_provided"] else \
        t("bench_list", price=money(L["list_price"]))
    exposed = o["appraisal_risk"] and o["price"] - (oe.appraisal_line(L) + o["gap_cover"]) > 0  # same line as the engine
    st = "risk" if o["price"] < L["cma_low"] else ("caution" if exposed or o["price"] < L["list_price"] else "good")
    nts = [o["escalation_note"]] if o.get("escalation") else []
    if exposed:
        nts.append(L_["note_above_value"])
    rows.append((T["price"], money(o["price"]), ref, st, "; ".join(nts)))
    f = o["financing"]
    st = "good" if f == "cash" or (f == "conventional" and o["down_pct"] >= .20) else ("caution" if f in ("conventional", "va") else "risk")
    # iteration 10 eval 6: the loan amount and the lender from the package, when the listing file has them
    loan = " · " + t("loan", amount=money(o["loan_amount"])) if o["financed"] and o.get("loan_amount") else ""
    rows.append((T["financing"], fin_str(o) + loan, L_["bench_financing"], st, ""))
    if o["financed"]:
        ap = o["approval"]
        st = "good" if ap == "full_uw" else ("caution" if ap in ("du_approved", "preapproval") else "risk")
        lender = f" · {o['lender']}" if o.get("lender") else ""
        rows.append((T["approval"], oe.APPROVAL_LABEL.get(ap, ap) + lender, L_["bench_approval"], st,
                     L_["note_verified"] if o.get("lender_called") else  # OFR-321: by name when the letter gives one
                     t("note_call_named", name=o["loan_officer"]) if o.get("loan_officer") else L_["note_call"]))
    else:
        ok = o["approval"] == "pof_verified"
        rows.append((T["pof"], L_["verified"] if ok else L_["not_verified"], L_["bench_pof"], "good" if ok else "risk", ""))
    N = L["norms"]  # OFR-15: same norms as the counter; national norms are said once, in the assumptions
    dep = oe.deposit_benchmark(o, L)  # iteration 10 eval 3: the scorecard rates against the same benchmark
    if o["deposit"] is None:
        rows.append((T["deposit"], L_["not_provided_cap"], t("bench_deposit_pct", pct=fmt.pct(dep, 1, fixed=True)),
                     "caution", L_["note_confirm_deposit"]))
    else:
        p = o["deposit"] / o["price"]
        rows.append((T["deposit"], t("deposit_share", amount=money(o["deposit"]), pct=fmt.pct(p, 1, fixed=True)),
                     t("bench_deposit", pct=fmt.pct(dep, 1, fixed=True), amount=money(dep * o["price"])),
                     oe.deposit_status(o, L), ""))
    c, cn = o["seller_concessions"], N["concessions_pct"]
    rows.append((T["concessions"], t("deposit_share", amount=money(c), pct=fmt.pct(c / o["price"], 1, fixed=True)) if c
                 else money(0), t("bench_concessions", pct=fmt.pct(cn, 1, fixed=True)),
                 "good" if not c else ("caution" if c <= cn * o["price"] + 1 else "risk"), ""))
    ob = S["offered_buyer_broker_pct"]
    if not o.get("bb_from_listing"):  # OFR-259: paid by the listing broker from its fee, it isn't a seller cost to rate
        rows.append((T["bb"], t("pct_amount", pct=fmt.pct(o["buyer_broker_pct"], 2),
                                amount=money(o["price"] * o["buyer_broker_pct"])),
                     t("bench_bb", pct=oe.pct(ob)) if ob is not None else L_["not_set"],
                     "caution" if ob is None else ("good" if o["buyer_broker_pct"] <= ob + 1e-9 else "risk"), ""))
    if o["home_warranty"]:
        rows.append((T["warranty"], t("seller_pays", amount=money(o["home_warranty"])), L_["buyer_pays"], "caution", ""))
    form = f" ({o['contract_label']})" if o["contract_form"] in oe.cf.FARBAR else ""  # an assumed form is in the assumptions
    note = (L_["note_walk_repairs"] if o["inspection_walkaway"] and o["repairs_owed"] else
            L_["note_walk"] if o["inspection_walkaway"] else L_["note_repairs"] if o["repairs_owed"] else "")
    rows.append((T["inspection"], t("days", n=o["inspection_days"]) + form, t("bench_days", n=N["inspection_days"]),
                 "good" if o["inspection_days"] <= N["inspection_days"] else ("caution" if o["inspection_days"] <= 14 else "risk"),
                 note))
    if o["financed"]:
        la = N["loan_approval_days"]
        rows.append((T["loan_approval"], t("days", n=o["loan_approval_days"]), t("bench_days", n=la),
                     "good" if o["loan_approval_days"] <= la else ("caution" if o["loan_approval_days"] <= max(30, la) else "risk"), ""))
        if o["appraisal_days"]:
            rows.append((T["gap"], money(o["appraisal_gap"]) if o["appraisal_gap"] else L_["none"],
                         L_["bench_gap"], "risk" if exposed else "good", ""))
        else:
            rows.append((T["appraisal"], L_["waived"], fmt.EMPTY, "good", ""))
    sc = o["sale_contingency_days"]
    rows.append((T["sale"], (t("days", n=sc) + (L_["kickout_tag"] if o["kickout"] else "")) if sc else L_["none"],
                 L_["none"], "risk" if sc else "good", ""))
    dl = S["deadline"]
    st = "risk" if dl and o["close"] > dl else ("caution" if o["close"].weekday() >= 5 else "good")
    rb, rent = o.get("rent_back_days"), o.get("rent_back_monthly")  # OFR-281: a rent-back is a closing term
    rb = (t("rent_back", n=rb) + (L_["rent_free"] if rent == 0 else t("rent_monthly", amount=money(rent)) if rent else "")) if rb else ""
    rows.append((T["closing"], t("close_days", close=wday(o["close"]), n=o["close_days"]) + rb,
                 t("bench_closing", close=day(oe.prior_weekday(dl))) if dl else fmt.EMPTY, st,
                 L_["note_weekend"] if o["close"].weekday() >= 5 else ""))
    tb, cust = o["title_by"], L["title_customary_payer"]
    if tb or cust:
        name = {"seller": L_["title_seller"], "buyer": L_["title_buyer"]}
        rows.append((T["title"], name.get(tb, fmt.EMPTY), name.get(cust, fmt.EMPTY), "good" if tb == cust else "caution", ""))
    for key in ("personal_property", "occupancy", "other_terms"):  # terms read from the contract, as written
        if o.get(key):
            rows.append((T[key], str(o[key]), fmt.EMPTY, "caution", ""))
    if o.get("riders") or o.get("addenda"):
        # ENG-11: the form and rider label from contract_forms ("Standard + As Is Rider (K)"); riders are listed after it
        label = o["contract_label"] if o["contract_form"] in oe.cf.FARBAR else ""
        # iteration 9 eval 5: a rider the label already names ("Standard + As Is Rider (K)") isn't listed again
        rest = [r for r in o.get("riders") or [] if not (label and (c := oe.cf.rider_codes([r])[0]) and f"({c[0]})" in label)]
        # iteration 14: the attached addenda are part of the contract too, listed after the riders
        text = " · ".join(x for x in (label, ", ".join(rest), ", ".join(map(str, o.get("addenda") or []))) if x)
        rows.append((T["contract"], text, fmt.EMPTY, "good", ""))
    return rows


def questions(o, R):
    """Only what the contract, the counter and the loan officer can't answer. Terms the counter sets (price, gap,
    concessions, deposit, inspection, closing) aren't asked: sending the counter asks them."""
    L = R["listing"]
    Q = [f["request"] for f in o["flags"] if f.get("contract") and f.get("request")]  # contract fixes come first
    if o.get("lapses_before"):  # OFR-319: the backup's own deadline ends before the counter to the top offer does
        Q.append(t("q_extend", until=o["lapses_before"]["until"]))
    if o["financed"] and o.get("insurance_quote") is not True:
        Q.append(t("q_insurance_roof", year=L["roof_year"]) if L.get("roof_year") else L_["q_insurance"])
    if o["sale_contingency_days"]:
        Q.append(L_["q_sale"])
    if o["financed"] and o["approval"] in ("prequal", "none"):
        Q.append(L_["q_preapproval"])
    if o["financed"] and not o.get("lender_called") and not o.get("loan_officer"):  # OFR-321: the letter names one
        Q.append(L_["q_loan_officer"])
    if o.get("escalation") and not oe.cf.escalation_proof_stated(o["contract_form"], o):  # EAC-1 says it: a redacted copy
        Q.append(L_["q_escalation_proof"])
    return Q


def funds_shown(o, gap=0):
    """OFR-321: True when the package's proof of funds covers the down payment (price less the loan) plus the appraisal
    gap the buyer may owe, the same cash the engine's proof-of-funds check counts."""
    funds = o.get("proof_of_funds")
    price = max(o["price"], o["counter_terms"]["price"] if o.get("action") == "COUNTER" else 0)  # the counter's, when higher
    return bool(funds) and funds >= price - (o.get("loan_amount") or o["price"] * (1 - o["down_pct"])) + gap


def lender_questions(o, R):
    """The call before responding: what the letter can't show. At most five, asked the same way of every buyer's lender or bank."""
    L = R["listing"]
    if not o["financed"]:
        return [L_["qb_account"], t("qb_funds", price=money(o["price"])), L_["qb_confirm"]]
    fin = oe.FIN_LABEL[o["financing"]]
    fin = fin if fin.isupper() else fin.lower()  # "an FHA loan", "a conventional loan"
    pof = o.get("proof_of_funds")  # the package's proof of funds already shows the assets: never asked again
    # round 3 case 05: a letter that says the lender reviewed the credit report, income and asset documentation
    # (`approval_documented`) already answers the documents half
    Q = [L_["ql_conditions"] if o["approval"] == "full_uw" else L_["ql_du"] if o.get("approval_documented") else
         t("ql_du_docs", what=L_["ql_income_credit"] if pof else L_["ql_income_assets"])]
    conc = t("ql_conc", amount=money(o["seller_concessions"])) if o["seller_concessions"] else ""
    # iteration 9 eval 7: when the seller counters (or a lapsed offer's reference counter) changes the price, ask at it
    price = o["counter_terms"]["price"] if o.get("action") in ("COUNTER", "INCOMPLETE") and o["counter_rows"] else o["price"]
    a_loan = t("ql_a_loan", a="an" if fin[0] in "AEFHILMNORSX" else "a", fin=fin)
    capped = o.get("approval_max_loan")
    if capped and price * (1 - o["down_pct"]) > capped + 1:  # iteration 10 eval 6: never imply a loan above the letter's cap
        Q.append(t("ql_good_cap", price=money(price), loan=a_loan, cap=money(capped), conc=conc))
    else:
        Q.append(t("ql_good", price=money(price), down=fmt.pct(o["down_pct"], 1, fixed=True), loan=a_loan, conc=conc))
    gap = max(o["appraisal_gap"], o["counter_terms"]["appraisal_gap"] if o.get("action") == "COUNTER" else 0)
    if not funds_shown(o, gap):  # OFR-321: a verification of funds in the package already answers it
        price = max(o["price"], o["counter_terms"]["price"] if o.get("action") == "COUNTER" else 0)
        Q.append((t("ql_pof_shows", pof=money(pof), price=money(price)) if pof else L_["ql_funds"])
                 + (t("ql_gap", gap=money(gap)) if gap else "?"))
    if o["financing"] in ("fha", "va", "usda"):
        Q.append(t("ql_rules", fin=fin, roof=t("ql_roof", year=L["roof_year"]) if L.get("roof_year") else ""))
    if o["close"].weekday() >= 5:
        # iteration 10 eval 1: "the offer", since an offer described in chat isn't a contract anyone has seen
        Q.append(t("ql_weekend", close=wday(o["close"]), before=wday(oe.prior_weekday(o["close"]))))
    else:
        Q.append(t("ql_close", close=wday(o["close"])))
    return Q


CHECK_ITEMS = ("signed", "lender", "deposit", "riders", "insurance", "bb", "net")


def checklist(o, R):
    """[(item, status, note)]: the verification checklist, with the contract problems noted on their line."""
    C = o.get("checklist") or {}
    found = {}  # contract problems noted on the matching line ("signed", "riders", "terms")
    for f in o["flags"]:
        if f.get("contract"):
            found.setdefault(f["check"], []).append(f["issue"].rstrip("."))
    fin = o["financed"]
    lender = ((t("ck_lender_named", name=o["loan_officer"]) if o.get("loan_officer") else L_["ck_lender"]) if fin
              else L_["ck_bank"])
    items = [("signed", L_["ck_signed"], "Pending"),
             ("lender", lender, "Yes" if o.get("lender_called") or (not fin and o["approval"] == "pof_verified") else "No"),
             ("deposit", L_["ck_deposit"], "Pending"), ("riders", L_["ck_riders"], "Pending"),
             ("insurance", L_["ck_insurance"], "N/A" if not fin else ({True: "Yes", False: "No"}.get(o.get("insurance_quote"), "Unknown"))),
             # iteration 14: the listing broker pays the buyer's broker from its own fee: nothing for the seller to review
             ("bb", L_["ck_bb"], "N/A" if oe.listing_pays_buyer_broker(o) else "Pending"), ("net", L_["ck_net"], "Pending")]
    L = R["listing"]
    if L.get("flood_disclosure_rule"):  # OFR-274: the listing side's reminder lives here, not among the offer's risks
        items.append(("flood", L_["ck_flood"], "Yes" if L.get("flood_disclosure") else "Pending"))
    out = []
    for k, lab, dflt in items:
        v = C.get(k, dflt)
        v, note = (v.get("status", dflt), v.get("note", "")) if isinstance(v, dict) else (v, "")
        note = "; ".join([note] * bool(note) + found.get(k, []))
        if v != "N/A":
            out.append((lab, v, note))
    return out


def timeline(o, R):
    """The contingency timeline (days from the analysis date, the Effective Date if accepted today): one row per window
    with its days, end date (rolled as page 1 rolls it) and how many cells it shades, the closing's cell and the
    seller's deadline cell. Render only shades cells."""
    S, L = R["seller"], R["listing"]
    dl = (S["deadline"] - L["analysis_date"]).days if S["deadline"] else 0
    span = max(o["close_days"], dl, o["risk_days"]) + 5
    step = max(1, math.ceil(span / 56))
    ncell = math.ceil(span / step)
    per_wk = max(1, 7 // step)
    weeks = []
    for i in range(0, ncell, per_wk):
        n = min(per_wk, ncell - i)  # a short last week gets no date: too narrow for one, it would wrap ("Nov / 3")
        weeks.append({"span": n, "label": day(L["analysis_date"] + timedelta(days=i * step)) if n >= min(3, per_wk) else ""})
    start = o["firm_date"] - timedelta(days=o["risk_days"])  # acceptance, as page 1 counts (walk_away)

    def line(name, d, kind):
        if not d:
            return {"name": name, "days": fmt.EMPTY, "end": fmt.EMPTY, "kind": kind, "on": 0}
        d = min(d, o["close_days"]) if o["close_days"] else d  # iteration 10 eval 1: no window runs past closing
        end, _ = oe.rolled(start + timedelta(days=d), R["costs"], o["close"])  # off a weekend or holiday, as page 1 rolls it
        return {"name": name, "days": str(d), "end": day(end), "kind": kind, "on": sum(1 for i in range(ncell) if i * step < d)}

    rows = [line(L_["tl_inspection_walk"] if o["inspection_walkaway"] else L_["tl_inspection_repair"], o["inspection_days"],
                 "hot" if o["inspection_walkaway"] else "warm")]
    if o["financed"]:
        rows.append(line(L_["tl_appraisal_loan"] if o.get("appraisal_in_loan") and not o["appraisal_protected"]
                         else L_["tl_appraisal"], o["appraisal_days"], "warm"))
        rows.append(line(L_["tl_loan"], o["loan_approval_days"], "warm"))
    rows.append(line(L_["tl_sale"], o["sale_contingency_days"], "hot"))
    # each rider's own window (Rider GG's compensation agreement, the insurance rider, attorney approval...): a
    # contingency, with its own cancel right, never a risk flag
    for code, d, what in o.get("rider_windows") or ():
        rows.append(line(t("tl_rider", what=prose.title_case(what), code=code), d, "rider"))
    return {"subtitle": t("tl_sub", date=day(L["analysis_date"])), "head": L_["tl_head"], "weeks": weeks, "ncell": ncell,
            "per_week": per_wk, "rows": rows,
            "closing": {"name": L_["tl_closing"], "sub": t("tl_deadline", date=day(S["deadline"])) if S["deadline"] else "",
                        "days": str(o["close_days"]), "end": day(o["close"]), "cell": (o["close_days"] - 1) // step},
            "deadline_cell": (dl - 1) // step if dl else None,
            "legend": {"hot": L_["lg_cancel_any"], "warm": L_["lg_cancel_fin"], "rider": L_["lg_cancel_rider"],
                       "close": L_["lg_closing"],
                       "deadline": L_["lg_deadline"]},
            "firm": t("tl_firm", n=o["risk_days"], date=day(firm_day(o, R["costs"])[0]))}


def scorecard(o):
    """Every criterion with its weight; one without the fact it reads shows "Not scored" and no number (the notes say
    which fact was missing), and the total row's weight is the scored weight the total is scaled over."""
    sc, rows = o["score"], []
    for k, lab, w in oe.CRITERIA:
        v = sc["scores"][k]
        rows.append({"key": k, "label": lab, "weight": fmt.pct(w / 100, 0), "score": v,
                     "why": sc["why"][k] if v is not None else L_["sc_not_scored"]})
    b = sc["band"]
    return {"rows": rows, "total": {"label": L_["sc_total"], "weight": fmt.pct(sc["weight"] / 100, 0), "score": sc["total"],
                                    "band": b[1], "cls": b[0], "scale": L_["sc_scale"]},
            "legend": L_["sc_legend"]}


# --- the comparison's chart ----------------------------------------------------------

def chart(R):
    """The comparison's Net vs. Certainty chart as data: each active offer's certainty (x) against its net as offered
    and downside (y), the target line and every label the chart prints (axis ticks, the target, the key), formatted
    here; render only places them."""
    offs = R["active"]
    vals = [x for o in offs for x in (o["ns"]["net_adj"], o["ns_down"]["net_adj"])] + [R["target"]["net_adj"]]
    lo, hi = min(vals), max(vals)
    pad = max(2000, (hi - lo) * .12)
    step = 5000 if hi - lo < 40000 else 10000 if hi - lo < 90000 else 25000
    y0, y1 = math.floor((lo - pad) / step) * step, math.ceil((hi + pad) / step) * step
    xmin = max(0, min(40, (min(o["score"]["total"] for o in offs) // 10) * 10))
    rank = {r["id"]: i + 1 for i, r in enumerate(R["ranked"])}
    close = R.get("target_close")
    tgt = R["target"]["net_adj"]
    return {
        "x_min": xmin, "y0": y0, "y1": y1, "target": tgt,
        "y_ticks": [{"value": v, "label": fmt.k(v)} for v in range(int(y0), int(y1) + 1, step)],
        "x_ticks": [{"value": x, "label": str(x)} for x in range(int(xmin), 101, 10)],
        "x_title": L_["ch_x"], "sweet": L_["ch_sweet"],
        "target_label": t("ch_target_close" if close else "ch_target", net=money(tgt), close=day(close) if close else ""),
        "points": [{"id": o["id"], "label": t("ch_point", key=o["key"], rank=rank.get(o["id"], "")), "score": o["score"]["total"],
                    "net": o["ns"]["net_adj"], "down": o["ns_down"]["net_adj"], "action": o["action"]} for o in offs],
        "legend": {"offered": L_["lg_offered"], "down": L_["lg_downside"]},
        "keys": [{"key": o["key"] + (t("ch_rank", n=i + 1) if len(R["ranked"]) > 1 else ""), "label": o["label"]}
                 for i, o in enumerate(R["ranked"])],
    }


KEY_TERMS = (("financing", ("financing",)), ("approval_funds", ("approval", "pof")), ("deposit", ("deposit",)),
             ("concessions", ("concessions",)), ("inspection", ("inspection",)), ("gap", ("gap", "appraisal")),
             ("sale", ("sale",)), ("closing", ("closing",)))
CHART_MAX = 6  # past this many offers the chart crowds; the decision table stands alone


def key_terms(R):
    """The comparison's Key Terms Side by Side: one row per offer (ranked, then incomplete), each key term with its
    rating word, the escalation clause when any offer has one, and the biggest risk."""
    T = L_["term"]
    offs = R["ranked"] + R["incomplete"]
    has_esc = any(o.get("escalation") for o in offs)
    rows = []
    for o in offs:
        tr = {r[0]: r for r in term_rows(o, R)}
        cells = []
        for _, keys in KEY_TERMS:
            hit = next((tr[T[k]] for k in keys if T[k] in tr), None)
            cells.append({"text": hit[1], "status": hit[3], "word": L_["status_word"].get(hit[3], "")} if hit
                         else {"text": fmt.EMPTY, "status": "", "word": ""})
        risk = biggest_risk(o)  # OFR-274, OFR-304: the same answer as the review's biggest_risk
        et = oe.escalation_terms(o)
        rows.append({"key": o["key"], "label": o["label"], "cells": cells,
                     "escalation": (et.split(" · ") if et else [L_["none"]]) if has_esc else None,
                     "risk": {"sev": risk["sev"], "issue": risk["issue"]} if risk else None})
    return {"head": [L_["kt"][k] for k, _ in KEY_TERMS], "escalation": L_["kt_escalation"] if has_esc else None,
            "rows": rows, "risk_none": L_["threat_none"]}


# --- facts, notes --------------------------------------------------------------------

def fact_row(R):
    """The divider row under the header: the home, then the inputs the numbers rest on. A missing input that makes the
    review Preliminary stays, in the risk color ({text, risk})."""
    L, S = R["listing"], R["seller"]
    hoa = (t("fact_hoa", amount=money(L["hoa_monthly"])) if L.get("hoa_monthly") else
           L_["fact_no_hoa"] if L.get("hoa_monthly") == 0 else None)
    if hoa and L.get("hoa_conflict"):  # OFR-343: the risk flags dispute the figure, so the chip doesn't state it
        hoa = L_["fact_hoa_confirm"]
    facts = [t("fact_beds", n=L["beds"]) if L.get("beds") else None, t("fact_baths", n=L["baths"]) if L.get("baths") else None,
             t("fact_sqft", n=fmt.num(L["sqft"])) if L.get("sqft") else None,
             t("fact_built", year=L["year_built"]) if L.get("year_built") else None,
             t("fact_roof", year=L["roof_year"]) if L.get("roof_year") else None, hoa,
             t("fact_flood", zone=L["flood_zone"]) if L.get("flood_zone") else None]
    out = [{"text": x, "risk": False} for x in facts if x]
    out.append({"text": t("fact_cma", range=fmt.range(L["cma_low"], L["cma_high"], fmt.k)), "risk": False}
               if L["cma_provided"] else {"text": L_["fact_no_cma"], "risk": True})
    out.append({"text": t("fact_payoff", amount=money(S["payoff"])), "risk": False} if S["payoff_known"]
               else {"text": L_["fact_no_payoff"], "risk": True})
    if S["deadline"]:
        note = deadline_note(S)  # OFR-296: a weekend deadline names the last business day
        out.append({"text": t("fact_deadline", date=wday(S["deadline"])) + (f" ({note})" if note else ""), "risk": False})
    return out


def report_notes(R, mode, sid, offers, confirm):
    """The document's one notes registry (shared/notes.py). The assumptions the report lists come first (the What to
    Confirm table), keyed like the market notes that say the same thing (`annual_tax`, `title_fees`, `deed transfer
    tax`...), so a note an assumption already says is never added again; then the cost notes, the tax, holding and
    downside basis, and the fixed lines, each once. A default commission is the reply's only (chat_only)."""
    L, S = R["listing"], R["seller"]
    N = notes.Notes()
    for a in confirm:
        N.add(akey(a), why_for(a, sid), "assumption")
    for a in R["missing"]:
        if a.get("default") or a.get("agent"):
            N.add(akey(a), a["why"], "chat_only")
    ids = {o["id"] for o in offers}
    for n in L["cost_notes"]:
        key = getattr(n, "key", None) or n
        if key.startswith("title_payer:") and key.split(":", 1)[1] not in ids:
            continue  # another offer's title terms: its own review says them
        N.add(key, str(n), "estimate")
    N.add("annual_tax", t("note_tax", amount=money(L["annual_tax"])) if L["annual_tax"] else L_["note_no_tax"], "estimate")
    N.add("holding_monthly", t("note_holding", amount=money(S["holding_monthly"])), "estimate")
    if mode == "multi":  # a single review's net sheet says what its Downside Case assumes, beside the column
        ref = L_["dn_ref_cma"] if L["cma_provided"] else L_["ref_list"]
        credit = t("note_credit", pct=fmt.pct(L["repair_reserve_pct"], 1, fixed=True)) if L["repair_reserve_pct"] else ""
        if any(o["repairs_owed"] and o["repair_reserve"] for o in R["offers"]):
            credit += L_["note_standard_instead"] if credit else L_["note_standard"]
        N.add("downside", t("note_downside", ref=ref, credit=credit), "info")
    N.add("final", L_["note_final"], "info")
    N.add("certainty", L_["note_certainty"], "info")
    N.add("legal", t("note_legal", state=profiles.STATES.get(L.get("state") or "", L_["your_state"])), "info")
    return N


def confirm_rows(R, confirm, sid):
    return [{"key": akey(a), "impact": a["impact"], "impact_label": L_["impact"][a["impact"]], "where": place(R, a, sid),
             "what": why_for(a, sid), "field": a["field"]} for a in confirm]


# --- the document model ----------------------------------------------------------------

def offer_detail(o, R):
    costs, L = R["costs"], R["listing"]
    br = biggest_risk(o)
    ns = net_sheet(o, R, with_target=False)
    return {
        "id": o["id"], "label": o["label"], "buyer": o["buyer"], "buyer_agent": o.get("buyer_agent") or "",
        "price": money(o["price"]), "financing": fin_str(o),
        "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]), "counter_net": money(o["ns_counter"]["net_adj"]),
        "downside_note": downside_note(o, L), "downside_counts": downside_hits(o),  # OFR-258
        "downside_checked": downside_checked(o),  # OFR-301
        "score": o["score"]["total"], "band": o["score"]["band"][1], "action": o.get("action"),
        "close": wday(o["close"]), "firm_date": wday(firm_day(o, costs)[0]),
        "flags": [f"{f['sev']}: {f['issue']} {f['fix']}" for f in o["flags"]],
        "flag_keys": [f["topic"] for f in o["flags"]],
        "biggest_risk": f"{br['sev']}: {br['issue']}" if br else None,  # OFR-274, OFR-304
        "biggest_risk_key": br["key"] if br else None,
        "net_sheet": {"columns": ns["columns"],
                      "rows": [{"label": r["label"], "values": [c["text"] for c in r["cells"]]} for r in ns["rows"]]
                      + [{"label": x["label"], "values": [c["text"] for c in x["cells"]]} for x in (ns["holding"], ns["net_adj"])]},
    }


def single_doc(R, o, v, sid):
    """Everything the single review's PDF places beyond the summary: the box under the answer, the detail sections."""
    L = R["listing"]
    act = v["action"]
    box = None
    if v["counter"]:
        st = v["counter"]["stance"]
        box = {"kind": "counter", "head": t("box_fallback" if v.get("wait") else "box_counter", stance=st["name"].upper()),
               "sub": v["counter"]["summary"], "note": st["note"],
               "cols": [L_["th_term"], L_["th_offered"], "", L_["th_counter"], L_["th_why"]], "rows": v["counter"]["rows"]}
    elif act == "INCOMPLETE":
        box = {"kind": "fixes", "head": L_["box_fix"], "sub": L_["box_fix_sub"],
               "cols": ["", L_["th_issue"], L_["th_how_fix"]], "rows": v["fixes"]}
    elif act == "ACCEPT":
        keys = [L_["term"][k] for k in ("price", "financing", "deposit", "concessions", "inspection", "closing")]
        rows = [{"term": r[0], "value": r[1], "bench": r[2]} for r in term_rows(o, R) if r[0] in keys]
        box = {"kind": "accept", "head": L_["box_accept"], "sub": t("box_accept_sub", net=money(o["ns"]["net_adj"])), "rows": rows}
    elif v["compare"]:
        c = v["compare"]
        box = {"kind": "compare", "head": L_["box_compare"], "sub": t("box_compare_sub", vs=c["vs"]),
               "cols": [L_["th_measure"], c["this"], c["vs"]], "rows": c["rows"]}
    who = " · ".join(x for x in (o["buyer"], o.get("buyer_agent")) if x)
    return {
        "kind": "single", "title": L_["doc_single"], "tag": L_["tag"],
        "subtitle": t("sub_single", address=L.get("address") or "", price=money(L["list_price"]), label=o["label"]),
        "file_title": t("file_single", label=o["label"]), "footer": t("footer_single", street=street(R), label=o["label"]),
        "box": box,
        "follow": L_["follow_single"],
        "net_sheet": {**net_sheet(o, R), "head": L_["h_net"],
                      "sub": L_["h_net_sub_counter"] if o["counter_rows"] else L_["h_net_sub"],
                      "captions": [{"term": L_["cap_downside"], "text": downside_caption(o, R)},
                                   {"term": L_["cap_target"], "text": t("cap_target_text", basis=target_basis(R, o))}]},
        "revive": ({"head": L_["box_revive"], "sub": L_["box_revive_sub"],
                    "cols": [L_["th_term"], L_["th_offered"], "", L_["th_could"], L_["th_why"]], "rows": v["revive"]["rows"]}
                   if v.get("revive") else None),
        "timeline": {**timeline(o, R), "h": L_["h_timeline"]},
        "terms": {"h": L_["h_terms"], "sub": L_["h_terms_sub"], "who_label": L_["th_buyer_agent"], "who": who,
                  "cols": [L_["th_term"], L_["th_offered_term"], L_["th_benchmark"], L_["th_rating"], L_["th_note"]],
                  "rows": [{"term": a, "offered": b, "benchmark": c, "status": st, "rating": L_["rating"][st], "note": n}
                           for a, b, c, st, n in term_rows(o, R)]},
        "scorecard": {**scorecard(o), "h": L_["h_scorecard"], "sub": L_["h_scorecard_sub"],
                      "cols": [L_["th_criterion"], L_["th_weight"], L_["th_score"], L_["th_why"]]},
        "flags": {"h": L_["h_flags"], "cols": [L_["th_level"], L_["th_issue"], L_["th_mitigation"]],
                  "rows": [{"sev": f["sev"], "issue": f["issue"], "fix": f["fix"], "key": f["topic"]} for f in o["flags"]],
                  "none": L_["no_risks"]},
        "checklist": {"h": L_["h_checklist"], "cols": [L_["th_done"], L_["th_item"], L_["th_notes"]],
                      "rows": [{"item": a, "done": b == "Yes", "note": c} for a, b, c in checklist(o, R)]},
        "questions": {"h": L_["h_questions"], "cols": [L_["th_num"], L_["th_question"]], "rows": questions(o, R),
                      "none": L_["q_none_counter"] if v["counter"] else L_["q_none"]},
        "lender": {"h": L_["h_lender_loan"] if o["financed"] else L_["h_lender_bank"],
                   "cols": [L_["th_num"], L_["th_question"]], "rows": lender_questions(o, R)},
    }


def multi_doc(R, v):
    L = R["listing"]
    top = R["ranked"][0]
    n_inc = v["offers_incomplete"]
    ctr = None
    if v["action"] == "COUNTER" and top["counter_rows"]:
        st = stance_view(top)
        ctr = {"h": t("h_counter_fallback" if v.get("wait") else "h_counter", label=top["label"]),
               "sub": t("h_counter_sub_wait" if v.get("wait") else "h_counter_sub", stance=st["name"]),
               "stance": st, "note": st["note"],
               "cols": [L_["th_term"], L_["th_offered_term"], L_["th_counter_short"], L_["th_why"]],
               "rows": [row(*r) for r in top["counter_rows"]]}
    return {
        "kind": "multi", "title": L_["doc_multi"], "tag": L_["tag"],
        "subtitle": t("sub_multi", address=L.get("address") or "", price=money(L["list_price"]), n=v["offers_active"])
        + (t("sub_incomplete", n=n_inc) if n_inc else ""),
        "file_title": L_["doc_multi"], "footer": t("footer_multi", street=street(R)),
        "follow": L_["follow_multi"],
        "plan": {"head": L_["box_plan"], "sub": v["plan_summary"],
                 "cols": ["", L_["th_offer"], L_["th_financing"], L_["th_action"], L_["th_price"], L_["th_net"],
                          L_["th_downside"], L_["th_cert"], L_["th_walk"], L_["th_close"], L_["th_terms"]],
                 "note": t("plan_definitions", payoff="" if R["seller"]["payoff_known"] else L_["before_payoff"])
                 + " " + v["plan_note"], "escalated": L_["escalated_word"]},
        "chart": {**chart(R), "h": L_["h_chart"]} if len(R["active"]) <= CHART_MAX else None,
        "key_terms": {**key_terms(R), "h": L_["h_key_terms"], "sub": L_["h_key_terms_sub"], "offer": L_["th_offer"],
                      "risk": L_["th_biggest_risk"], "note": L_["kt_note"]},
        "counter": ctr,
        "details": L_["dh_multi"],
    }


def street(R):
    return (R["listing"].get("address") or L_["listing_word"]).split(",")[0]


def result(R, mode="auto", offer_id=None):
    """The document model for one report (a single review or the comparison): the summary the chat and page 1 read,
    each offer's detail, the assumptions (What to Confirm), the notes (said once), the chat-only lines, and `doc`, the
    rest of what the PDF places. Every figure is formatted here, once."""
    mode, o = pick(R, mode, offer_id)
    view = single_view(R, o) if mode == "single" else multi_view(R)
    L, S = R["listing"], R["seller"]
    sid = review_scope(R, mode, o)
    offers = [o] if mode == "single" else R["ranked"]
    checked = offers if mode == "single" else R["ranked"] + R["incomplete"]  # OFR-114: a blocked offer still gets its chat notes
    listed = listed_assumptions(R, mode == "multi", sid)
    asks = confirm_items(R, offer_id=sid)
    N = report_notes(R, mode, sid, offers, listed)
    doc = single_doc(R, o, view, sid) if mode == "single" else multi_doc(R, view)
    doc.update({"facts": fact_row(R), "street": street(R), "prepared_for": S.get("name") or L_["seller_word"],
                "date": fmt.date_long(L["analysis_date"]), "confirm": confirm_rows(R, listed, sid),
                "h_confirm": L_["h_confirm"], "confirm_cols": [L_["th_impact"], L_["th_where"], L_["th_what"]],
                "confirm_none": L_["confirm_none"], "dh": L_["dh_single"] if mode == "single" else L_["dh_multi"]})
    out = {
        "ok": True, "mode": mode, "property": L.get("address") or "", "list_price": money(L["list_price"]),
        "value_range": fmt.range(L["cma_low"], L["cma_high"]) if L["cma_provided"] else L_["not_provided"],
        # OFR-288: a range the agent gave (not a --cma handoff) is confirmed in one chat line
        "value_range_confirm": (t("range_confirm", range=fmt.range(L["cma_low"], L["cma_high"]))
                                if L["cma_provided"] and not L.get("cma_source") else None),
        "deadline_note": (t("deadline_sentence", date=day(S["deadline"]), note=deadline_note(S))  # OFR-296
                          if deadline_note(S) else None),
        "summary": view,
        "offers": [offer_detail(x, R) for x in offers],
        "to_confirm": to_confirm(R, offer_id=sid),  # OFR-352
        # OFR-272: named in one line in every quick answer; what to_confirm already asks isn't repeated
        "estimated_costs": estimated_costs(R, offers, skip={a["field"] for a in asks}),
        # OFR-352: the list the report shows, the one the data note counts
        "assumptions": [{"impact": a["impact"], "where": place(R, a, sid), "what": why_for(a, sid), "field": a["field"]}
                        for a in listed],
        # iteration 14: the agent's own items (a default commission, their listing agreement), chat only; render.py's
        # stderr reads these two lists, so both scripts print the same assumptions for the same file
        "chat_assumptions": [{"impact": a["impact"], "what": why_for(a, sid), "field": a["field"]}
                             for a in listed_assumptions(R, mode == "multi", sid, defaults=True) if a not in listed],
        "notes": N.texts("estimate") + N.texts("info"),  # the PDF's notes block (the assumptions are the table)
        "note_keys": [k for k, _, _ in N.items("chat", grouped=False)],
        "cost_notes": [str(n) for n in L["cost_notes"]],
        "market_notes": R["market_notes"],
        "doc": doc,
        "sample": bool(R.get("sample")),
        # chat only (never on the report): the best-effort line for a contract that isn't FAR/BAR, and revision notes
        **described_support(oe.cf.support([x["contract_form"] for x in checked],  # TL-201: "the footer reads" only when read from it
                                          [(x["contract_form"], x.get("form_revision"),
                                            str(x.get("form_revision_source") or "").lower() == "footer") for x in checked]),
                            checked),
    }
    N.check_labels(labels_of(out))
    return out


def labels_of(out):
    """Every label the report prints (headings, column headers, row names, tiles), for notes.check_labels."""
    d, s = out["doc"], out["summary"]
    found = [k["label"] for k in s.get("kpis") or []]
    for part in ("net_sheet",):
        ns = d.get(part)
        if ns:
            found += ns["columns"] + [r["label"] for r in ns["rows"]]
    for v in d.values():
        if isinstance(v, dict):
            found += [c for c in v.get("cols") or [] if c] + ([v["h"]] if v.get("h") else [])
    return found


def described_support(sup, offers):
    """(iteration 10 eval 3: render.py uses this too, so chat and stderr carry one line) The support result with the
    best-effort line reworded when no best-effort offer names a contract form."""
    other = [x for x in offers if x["contract_form"] == oe.cf.OTHER]
    if other and not any(x.get("form_given") for x in other):
        sup["chat_notes"] = [oe.cf.DESCRIBED_NOTE if n == oe.cf.BEST_EFFORT_NOTE else n for n in sup["chat_notes"]]
    return sup


def reports(R, mode="auto", offer_id=None):
    """The documents one run renders: a single review; or with 2+ active offers, the comparison plus a single review of
    each active offer, in rank order (OFR-318)."""
    mode_, _ = pick(R, mode, offer_id)
    if mode_ == "multi" and len(R["active"]) >= 2:
        return [result(R, "multi")] + [result(R, "single", o["id"]) for o in R["ranked"]]
    return [result(R, mode, offer_id)]


def compute(data, ctx):
    """render.main's compute step: the engine once, then every document the run prints, each a result() model, and the
    lines for the agent (stderr)."""
    R = analyze(data, cma=load_cma(data, ctx.get("cma")), agent=ctx.get("agent"))
    docs = reports(R, ctx.get("mode") or "auto", ctx.get("offer"))
    first = docs[0]  # the same lists review.py prints for this file: the report's, then the agent's own (chat only)
    lines = [f"Assumed [{a['impact']}] {a['what']}" for a in first["assumptions"]]
    lines += [f"For the agent (chat only, never on the report): Assumed [{a['impact']}] {a['what']}"
              for a in first["chat_assumptions"]]
    lines += [f"For the agent (chat only, never on the report): {n}" for n in docs[0]["chat_notes"]]  # iteration 10 eval 3
    return {"reports": docs, "agent_lines": lines, "sample": bool(R["sample"])}


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
