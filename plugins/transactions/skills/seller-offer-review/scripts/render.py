"""Offer review PDF for the seller (listing side): one offer, or every active offer compared.

    python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer B]
                              [--agent agent-profile.md] [--market market-profile.md] [--sample] [--out DIR]

Page 1 is a self-contained executive summary (the recommendation, the counter or the plan, key
numbers, certainty and the seller's options). The pages after it hold the net sheets, contingency
timeline, terms review, scorecard, risk flags, checklist, questions and assumptions.
Colors follow the agent's seller-side brand color.
"""
import html
import math
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review  # noqa: E402
from _shared import design, handoff, offer_engine as oe, profiles, render  # noqa: E402

esc = html.escape
money, signed = oe.money, review.signed
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "offer-review.css")
PAGE1_LIMIT = 989  # px available on page 1 at the print viewport
PILL = {"good": "low", "caution": "med", "risk": "high"}
RATING = {"good": "Favorable", "caution": "Watch", "risk": "Weak"}


def md(text):
    """Escape, then turn the summary's **bold** into <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text or ""))


def acct(v):
    """Net-sheet style: costs in parentheses."""
    return money(v) if v >= 0 else f"({money(-v)})"


def pctx(v, d=1):
    return f"{v * 100:.{d}f}%"


# --- shared blocks -------------------------------------------------------------

def prepared_block(R, agent):
    lines = [f'Prepared for <b>{esc(R["seller"].get("name") or "Seller")}</b> · {R["listing"]["analysis_date"]:%B %-d, %Y}']
    if agent.get("name"):
        lines.append(f'<b>{esc(agent["name"])}</b>')
        org = " · ".join(esc(str(agent[f])) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {esc(str(agent["license"]))}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return "<br>".join(lines)


def header(R, title, sub, agent, sample):
    tag = '<span class="viewtag">Seller side</span>' + ('<span class="sample">SAMPLE DATA</span>' if sample else "")
    return (f'<header><div><div class="t1">{title}{tag}</div><div class="t2">{sub}</div></div>'
            f'<div class="prep">{prepared_block(R, agent)}</div></header>')


def snapshot(R, last_label, last_value):
    L, S = R["listing"], R["seller"]
    bb = f"{L['beds']} / {L['baths']}" if L.get("beds") else "—"
    yr = f"{L.get('year_built') or '—'} / {L.get('roof_year') or '—'}"
    hoa = f"${L['hoa_monthly']:,}/mo" if L.get("hoa_monthly") else ("None" if L.get("hoa_monthly") == 0 else "—")
    cma = f"{money(L['cma_low'])}–{L['cma_high'] // 1000:,.0f}K" if L["cma_provided"] else '<span class="rt">not provided</span>'
    payoff = money(S["payoff"]) if S["payoff_known"] else '<span class="rt">not provided</span>'
    cells = [("Beds / Baths", bb), ("Heated sq ft", f"{L['sqft']:,}" if L.get("sqft") else "—"), ("Year / Roof", yr), ("HOA", hoa),
             ("Flood zone", esc(L.get("flood_zone") or "—")), ("CMA range", cma), ("Payoff (est.)", payoff), (last_label, last_value)]
    return ('<div class="snap" style="grid-template-columns:.8fr .8fr .9fr .7fr .8fr 1.3fr 1fr 1.2fr">'
            + "".join(f"<div><span>{a}</span><b>{b}</b></div>" for a, b in cells) + "</div>")


def state_name(R):
    st = R["listing"].get("state")
    return profiles.STATES.get(st or "", "your state")


def fine(R):
    L, S = R["listing"], R["seller"]
    costs = "; ".join(L["cost_notes"])
    tax = f"tax proration assumes {money(L['annual_tax'])}/yr paid in arrears" if L["annual_tax"] else "no tax proration included"
    ref = "CMA midpoint" if L["cma_provided"] else "list price"
    credit = (f" and an inspection credit of about {L['repair_reserve_pct'] * 100:.1f}% of price when the buyer has an inspection period"
              if L["repair_reserve_pct"] else "")
    return (f'<div class="fine">All figures are estimates for discussion only. {esc(costs)}. The {tax}; holding costs assume '
            f'{money(S["holding_monthly"])}/mo. The downside case assumes the appraisal lands at the {ref}{credit}. Actual costs come '
            "from the title company's settlement statement. Certainty scores reflect the listing agent's professional judgment, not a "
            f"guarantee of performance. This report is not legal or financial advice; consult a real estate attorney licensed in "
            f"{esc(state_name(R))} about contract terms.</div>")


def certainty_panel(c, subtitle="as offered"):
    b = c["band_class"]
    t = {"hi": "hit", "mid": "midt", "lo": "lot"}[b]
    return f'''<div><h2>How likely is it to close? <span class="h2s">{subtitle}</span></h2><div class="panel">
  <div class="gauge"><b class="{t}">{c["score"]}</b><span>/100 · <b class="{t}" style="font-size:inherit">{c["band"]}</b> certainty</span></div>
  <div class="meter"><div class="bar {b}" style="width:{c["score"]}%"></div></div>
  <table class="facts2">
   <tr><td>Buyer can walk away until</td><td class="n"><b>{esc(c["walk_away_until"])}</b></td></tr>
   <tr><td>Deposit at risk after that</td><td class="n">{esc(c["deposit"]) if c["deposit"] != "not provided" else '<span class="rt">not provided</span>'}</td></tr>
   <tr><td>Closing</td><td class="n"><b class="{"" if c["closing_ok"] else "rt"}">{esc(c["closing"])}</b></td></tr>
   <tr><td>Biggest threat</td><td class="n"><b class="rt">{esc(c["threat"])}</b></td></tr>
  </table></div></div>'''


def options_table(opts, widths=(24, 13, 15)):
    rows = "".join(
        f'<tr class="{"recrow" if x["recommended"] else ""}"><td><b>{esc(x["option"])}</b>'
        f'{" <span class=sm>(recommended)</span>" if x["recommended"] else ""}</td><td class="n">{esc(x["net"])}</td>'
        f'<td class="c">{esc(x["certainty"])}</td><td class="{x["status"]}">{esc(x["what"])}</td></tr>' for x in opts)
    cols = "".join(f'<col style="width:{w}%">' for w in widths)
    return (f'<h2>Your options</h2><div class="tbl"><table><colgroup>{cols}</colgroup>'
            f'<thead><tr><th>Option</th><th class="n">Net after holding</th><th class="c">Certainty</th><th>What happens</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def closing_block(v):
    pre = f'<div class="prelim">{md(v["preliminary"])}</div>' if v["preliminary"] else ""
    return (f'{pre}<div class="nextstep"><b>Next step:</b> {esc(v["next_step"])} The detail follows on the next pages.</div>'
            f'<div class="fine" style="margin-top:4px">{md(v["data_note"])} Estimates only; not legal or financial advice.</div>')


def hero(v):
    cls = {"DECLINE": "decline", "BACKUP": "backup"}.get(v["action"], "")
    ctx = f' · {v["offers_active"]} offers active' if v["offers_active"] > 1 else ""
    return (f'<div class="hero"><div class="hl {cls}"><span class="k">Recommended response{ctx}</span><div class="big">{esc(v["headline"])}</div>'
            f'<div class="why">{md(v["why"])}</div></div>'
            f'<div class="hr"><span class="k">Respond by</span><b>{esc(v["respond_by"])}</b>'
            f'<span class="k" style="margin-top:6px">Seller\'s priority</span><div>{esc(v["priority"])}</div></div></div>')


# --- detail tables -------------------------------------------------------------

def term_rows(o, R):
    """(label, offered, benchmark, status, note)"""
    L, S = R["listing"], R["seller"]
    rows = []
    ref = f"CMA {money(L['cma_low'])}–{money(L['cma_high'])}" if L["cma_provided"] else f"List {money(L['list_price'])}"
    exposed = o["financed"] and o["appraisal_days"] and o["price"] - (L["cma_mid"] + o["appraisal_gap"]) > 0
    st = "risk" if o["price"] < L["cma_low"] else ("caution" if exposed or o["price"] < L["list_price"] else "good")
    rows.append(("Price", money(o["price"]), ref, st, "Above value range; appraisal may cut it" if exposed and o["price"] > L["cma_high"] else ""))
    f = o["financing"]
    st = "good" if f == "cash" or (f == "conventional" and o["down_pct"] >= .20) else ("caution" if f in ("conventional", "va") else "risk")
    rows.append(("Financing", review.fin_str(o), "Cash or conv. ≥20% down", st, ""))
    if o["financed"]:
        ap = o["approval"]
        st = "good" if ap == "full_uw" else ("caution" if ap in ("du_approved", "preapproval") else "risk")
        rows.append(("Approval", oe.APPROVAL_LABEL.get(ap, ap), "Full underwriting", st,
                     "Verified with lender" if o.get("lender_called") else "Not yet verified by phone"))
    else:
        ok = o["approval"] == "pof_verified"
        rows.append(("Proof of funds", "Verified" if ok else "Not verified", "Verified with bank", "good" if ok else "risk", ""))
    if o["deposit"] is None:
        rows.append(("Escrow deposit", "Not provided", "≥3% of price", "caution", "Confirm amount and due date"))
    else:
        p = o["deposit"] / o["price"]
        rows.append(("Escrow deposit", f"{money(o['deposit'])} ({pctx(p)})", f"≥3% ({money(round(.03 * o['price']))})",
                     "good" if p >= .03 else ("caution" if p >= .015 else "risk"), ""))
    c = o["seller_concessions"]
    rows.append(("Seller concessions", f"{money(c)} ({pctx(c / o['price'])})" if c else "$0", "≤1.5% of price",
                 "good" if not c else ("caution" if c <= .015 * o["price"] else "risk"), ""))
    ob = S["offered_buyer_broker_pct"]
    rows.append(("Buyer-broker comp.", f"{oe.pct(o['buyer_broker_pct'], 2)} ({money(round(o['price'] * o['buyer_broker_pct']))})",
                 f"{oe.pct(ob)} per listing agmt." if ob is not None else "Not set",
                 "caution" if ob is None else ("good" if o["buyer_broker_pct"] <= ob + 1e-9 else "risk"), ""))
    if o["home_warranty"]:
        rows.append(("Home warranty", f"Seller pays {money(o['home_warranty'])}", "Buyer pays", "caution", ""))
    as_is = o["contract_form"] == "as_is"
    rows.append(("Inspection period", f"{o['inspection_days']} days" + (" (AS IS)" if as_is else ""), "≤7 days",
                 "good" if o["inspection_days"] <= 7 else ("caution" if o["inspection_days"] <= 14 else "risk"),
                 "Buyer may cancel for any reason" if as_is else ""))
    if o["financed"]:
        rows.append(("Loan approval period", f"{o['loan_approval_days']} days", "≤21 days",
                     "good" if o["loan_approval_days"] <= 21 else ("caution" if o["loan_approval_days"] <= 30 else "risk"), ""))
        if o["appraisal_days"]:
            rows.append(("Appraisal gap coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None",
                         "Covers price above value", "risk" if exposed else "good", ""))
        else:
            rows.append(("Appraisal contingency", "Waived", "—", "good", ""))
    sc = o["sale_contingency_days"]
    rows.append(("Sale-of-home contingency", (f"{sc} days" + (" (kick-out)" if o["kickout"] else "")) if sc else "None", "None",
                 "risk" if sc else "good", ""))
    dl = S["deadline"]
    st = "risk" if dl and o["close"] > dl else ("caution" if o["close"].weekday() >= 5 else "good")
    rows.append(("Closing date", f"{o['close']:%a %b %-d} ({o['close_days']} days)", f"On/before {dl:%b %-d}" if dl else "—", st,
                 "Weekend date; confirm funding" if o["close"].weekday() >= 5 else ""))
    tb, cust = o["title_by"], L["title_customary_payer"]
    if tb or cust:
        name = {"seller": "Seller's title co.", "buyer": "Buyer's title co."}
        rows.append(("Escrow / title agent", name.get(tb, "—"), name.get(cust, "—"), "good" if tb == cust else "caution", ""))
    for key, lab in (("personal_property", "Personal property"), ("occupancy", "Occupancy"), ("other_terms", "Other terms")):
        if o.get(key):
            rows.append((lab, esc(o[key]), "—", "caution", ""))
    if o.get("riders"):
        form = {"as_is": "AS IS · ", "standard": "Standard · "}.get(o["contract_form"], "")
        rows.append(("Contract / riders", form + esc(", ".join(o["riders"])), "—", "good", ""))
    return rows


def questions(o, R):
    Q, L = [], R["listing"]
    if o["financed"] and o.get("insurance_quote") is not True:
        roof = f", given the {L['roof_year']} roof?" if L.get("roof_year") else "?"
        Q.append("Has the buyer obtained a homeowners insurance quote for this address" + roof)
    if o["financed"] and o["counter_terms"]["appraisal_gap"] > o["appraisal_gap"]:
        Q.append("Can the buyer cover an appraisal gap? How much cash do they have beyond closing costs?")
    if o["seller_concessions"] > .015 * o["price"]:
        Q.append(f"How firm are the {money(o['seller_concessions'])} in concessions: needed to close, or a negotiating ask?")
    if o["inspection_days"] > 7:
        Q.append(f"Would the buyer shorten inspection to 7 days if the seller provides the {L['reports']}?")
    if o["close"].weekday() >= 5:
        Q.append(f"Can the lender close on {oe.prior_weekday(o['close']):%a %b %-d} instead?")
    if o["financed"] and o["approval"] in ("prequal", "none"):
        Q.append("When can the buyer provide a full pre-approval?")
    if o["financed"] and not o.get("lender_called"):
        Q.append("Who is the loan officer, so we can verify the approval directly?")
    if o["sale_contingency_days"]:
        Q.append("Is the buyer's current home listed or under contract? At what price?")
    if o["deposit"] is None or o["deposit"] / o["price"] < .03:
        Q.append("Can the buyer increase the escrow deposit?")
    if o.get("escalation"):
        Q.append("What proof of a competing offer does the escalation clause require?")
    return Q[:6]


def checklist(o):
    C = o.get("checklist") or {}
    fin = o["financed"]
    items = [("signed", "All parties signed & initialed; dates filled", "Pending"),
             ("lender", "Lender called / proof of funds confirmed with bank",
              "Yes" if o.get("lender_called") or (not fin and o["approval"] == "pof_verified") else "No"),
             ("deposit", "Deposit amount, due date & escrow agent confirmed", "Pending"),
             ("riders", "All riders attached and consistent", "Pending"),
             ("insurance", "Buyer has insurance quote on this address", "N/A" if not fin else ({True: "Yes", False: "No"}.get(o.get("insurance_quote"), "Unknown"))),
             ("bb", "Buyer-broker compensation request reviewed with seller", "Pending"),
             ("net", "Seller's net sheet reviewed with seller", "Pending")]
    out = []
    for k, lab, dflt in items:
        v = C.get(k, dflt)
        v, note = (v.get("status", dflt), v.get("note", "")) if isinstance(v, dict) else (v, "")
        out.append((lab, v, note))
    return out


def pill_status(v):
    return f'<span class="pill v{v.lower().replace("/", "")}">{esc(v)}</span>'


def assumptions_table(R):
    if not R["assumptions"]:
        return '<p class="sm">No assumptions: every key input was provided.</p>'
    lab = {"high": "High", "med": "Med", "low": "Low"}
    rows = "".join(f'<tr><td class="c"><span class="pill {a["impact"]}">{lab[a["impact"]]}</span></td><td>{esc(a["scope"].title())}</td>'
                   f'<td>{esc(a["why"])}</td></tr>' for a in R["missing"])
    return ('<div class="tbl"><table><colgroup><col style="width:9%"><col style="width:12%"></colgroup><thead><tr><th class="c">Impact</th>'
            f'<th>Where</th><th>What was assumed: provide the real value to sharpen the analysis</th></tr></thead><tbody>{rows}</tbody></table></div>')


def gantt(o, R):
    S, L = R["seller"], R["listing"]
    dl = (S["deadline"] - L["analysis_date"]).days if S["deadline"] else 0
    span = max(o["close_days"], dl, o["risk_days"]) + 5
    step = max(1, math.ceil(span / 56))
    ncell = math.ceil(span / step)
    per_wk = max(1, 7 // step)
    hdr = '<tr><th style="width:22%">Contingency</th><th class="n" style="width:6%">Days</th><th class="n" style="width:9%">Ends</th>'
    for i in range(0, ncell, per_wk):
        hdr += f'<th colspan="{min(per_wk, ncell - i)}" class="c">{(L["analysis_date"] + timedelta(days=i * step)):%b %-d}</th>'
    hdr += "</tr>"

    def gx(i):
        c = "wk " if i % per_wk == 0 else ""
        if dl and i == (dl - 1) // step:
            c += "dl"
        return c

    def line(name, d, kind):
        if not d:
            return f'<tr><td>{name}</td><td class="n">—</td><td class="n">—</td>' + "".join(f'<td class="gantt {gx(i)}"></td>' for i in range(ncell)) + "</tr>"
        cells = "".join(f'<td class="gantt {gx(i)} {"on-" + kind if i * step < d else ""}"><div></div></td>' for i in range(ncell))
        return f'<tr><td>{name}</td><td class="n">{d}</td><td class="n">{(L["analysis_date"] + timedelta(days=d)):%b %-d}</td>{cells}</tr>'

    body = line("Inspection (right to cancel)" if o["contract_form"] == "as_is" else "Inspection", o["inspection_days"], "hot")
    if o["financed"]:
        body += line("Appraisal", o["appraisal_days"], "warm") + line("Loan approval", o["loan_approval_days"], "warm")
    body += line("Sale of buyer's home", o["sale_contingency_days"], "hot")
    ci = (o["close_days"] - 1) // step
    dtxt = f" <span class=sm>(deadline {S['deadline']:%b %-d})</span>" if S["deadline"] else ""
    body += (f'<tr><td><b>Closing</b>{dtxt}</td><td class="n">{o["close_days"]}</td><td class="n">{o["close"]:%b %-d}</td>'
             + "".join(f'<td class="gantt {gx(i)} {"on-close" if i == ci else ""}"><div></div></td>' for i in range(ncell)) + "</tr>")
    legend = ('<div class="legend"><span><i class="hot"></i>Cancel for any reason</span><span><i class="warm"></i>Cancel if financing/appraisal fails</span>'
              '<span><i class="closei"></i>Closing</span>' + ('<span><i class="dl"></i>Seller deadline</span>' if dl else "")
              + f'<span>Firm after day <b>{o["risk_days"]}</b> ({o["firm_date"]:%b %-d}).</span></div>')
    return f'<div class="tbl"><table style="table-layout:fixed"><thead>{hdr}</thead><tbody>{body}</tbody></table></div>{legend}'


def scorecard_single(o):
    rows = ""
    for k, lab, w in oe.CRITERIA:
        s = o["score"]["scores"][k]
        src = "" if o["score"]["src"][k] == "auto" else ' <span class="pill vyes">agent</span>'
        rows += f'<tr><td>{lab}</td><td class="n">{w}%</td><td class="c s{s}">{s}</td><td>{esc(o["score"]["why"][k])}{src}</td></tr>'
    b = o["score"]["band"]
    t = {"hi": "hit", "mid": "midt", "lo": "lot"}[b[0]]
    rows += (f'<tr class="total"><td>Certainty score</td><td class="n">100%</td><td class="c {t}"><b>{o["score"]["total"]}</b></td>'
             f'<td class="{t}"><b>{b[1]}</b> · 80+ strong · 60–79 workable · under 60 weak</td></tr>')
    return ('<div class="tbl"><table><colgroup><col style="width:28%"><col style="width:8%"><col style="width:7%"></colgroup>'
            f'<thead><tr><th>Criterion</th><th class="n">Weight</th><th class="c">Score</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<div class="legend"><span>Scores are drafted automatically from the contract; <span class="pill vyes">agent</span> marks scores the agent set.</span></div>')


def netsheet_body(cols, hl=0):
    body = ""
    for r in review.net_sheet_rows(cols):
        body += f"<tr><td>{esc(r['label'])}</td>" + "".join(
            f'<td class="n {"hl" if j == hl else ""} {"neg" if v < 0 else ""}">{acct(v)}</td>' for j, v in enumerate(r["values"])) + "</tr>"
    body += '<tr class="total"><td>Estimated net proceeds</td>' + "".join(f'<td class="n">{acct(c["net"])}</td>' for _, c in cols) + "</tr>"
    body += '<tr><td>Holding costs until closing</td>' + "".join(f'<td class="n neg">{acct(c["holding"])}</td>' for _, c in cols) + "</tr>"
    return body


# --- single offer --------------------------------------------------------------

def single_html(R, o, v):
    L = R["listing"]
    tgt = o["target"]["net_adj"]
    act = v["action"]
    if v["counter"]:
        ck = "".join(f'<tr><td><b>{esc(r["term"])}</b></td><td class="was">{esc(r["offered"])}</td><td class="arr">→</td>'
                     f'<td class="now">{esc(r["counter"])}</td><td class="why2">{esc(r["why"])}</td></tr>' for r in v["counter"]["rows"])
        fb = f'<div class="note">{md(v["fallback"])}</div>' if v["fallback"] else ""
        box = (f'<div class="ctr"><div class="ctrh"><span>OUR COUNTER</span><em>{md(v["counter"]["summary"])}</em></div>'
               '<table><colgroup><col style="width:18%"><col style="width:15%"><col style="width:3%"><col style="width:17%"><col></colgroup>'
               f'<thead><tr><th>Term</th><th>Buyer offered</th><th></th><th>We counter</th><th>Why</th></tr></thead><tbody>{ck}</tbody></table>{fb}</div>')
    elif act == "ACCEPT":
        keys = [r for r in term_rows(o, R) if r[0] in ("Price", "Financing", "Escrow deposit", "Seller concessions", "Inspection period", "Closing date")]
        rows = "".join(f'<tr><td><b>{t}</b></td><td class="now">{val}</td><td class="why2">{b}</td></tr>' for t, val, b, _, _ in keys)
        box = (f'<div class="ctr"><div class="ctrh"><span>ACCEPT AS WRITTEN</span><em>Net after holding <b>{money(o["ns"]["net_adj"])}</b></em></div>'
               f'<table><tbody>{rows}</tbody></table></div>')
    elif v["compare"]:
        c = v["compare"]
        rows = "".join(f'<tr><td><b>{a}</b></td><td>{b}</td><td class="now">{d}</td></tr>' for a, b, d in c["rows"])
        box = (f'<div class="ctr cmp"><div class="ctrh"><span>HOW IT COMPARES</span><em>vs. Offer {esc(c["vs"])} (recommended)</em></div>'
               f'<table><thead><tr><th>Measure</th><th>Offer {esc(o["id"])}</th><th>Offer {esc(c["vs"])}</th></tr></thead><tbody>{rows}</tbody></table></div>')
    else:
        box = ""
    kp = "".join(f'<div class="{"kgood" if k["tone"] == "good" and "counter" in k["label"] else ""}"><span>{esc(k["label"])}</span>'
                 f'<b class="{k["tone"] if k["tone"] in ("brand", "good") and k is not v["kpis"][1] else ""}">{esc(k["value"])}</b>'
                 f'<i class="{k["tone"] if k["tone"] in ("good", "risk") else ""}">{esc(k["note"])}</i></div>' for k in v["kpis"])
    risks = "".join(f'<tr><td class="c"><span class="pill {r["sev"].lower()}">{r["sev"]}</span></td><td>{esc(r["issue"])}</td></tr>'
                    for r in v["risks"]) or "<tr><td>No significant risks found.</td></tr>"
    page1 = (f'{hero(v)}{box}<div class="kpis">{kp}</div>'
             f'<div class="two">{certainty_panel(v["certainty"])}<div><h2>Top risks in the offer as written</h2>'
             f'<div class="tbl"><table><colgroup><col style="width:17%"></colgroup><tbody>{risks}</tbody></table></div></div></div>'
             f'{options_table(v["options"])}{closing_block(v)}')

    cols = [("As offered", o["ns"]), ("Downside case", o["ns_down"])]
    if o["counter_rows"]:
        cols.append(("Proposed counter", o["ns_counter"]))
    if o.get("fallback_rows"):
        cols.append(("Fallback counter", o["ns_fallback"]))
    target_label = "Seller's target"
    cols.append((target_label, o["target"]))
    ns = netsheet_body(cols)
    ns += '<tr class="total2"><td>Net after holding costs</td>' + "".join(
        f'<td class="n {"best" if c["net_adj"] >= tgt else ("worst" if c["net_adj"] < tgt - 5000 else "")}">{acct(c["net_adj"])}</td>' for _, c in cols) + "</tr>"
    ns += "<tr class=\"alt\"><td>vs. seller's target net</td>" + "".join(
        f'<td class="n">{"—" if n == target_label else signed(c["net_adj"] - tgt)}</td>' for n, c in cols) + "</tr>"
    ref = f"the CMA midpoint ({money(round(L['cma_mid']))})" if L["cma_provided"] else "list price"
    tr = "".join(f'<tr><td>{t}</td><td class="{st}">{val}</td><td>{b}</td><td class="c"><span class="pill {PILL[st]}">{RATING[st]}</span></td>'
                 f'<td class="sm" style="color:var(--text)">{esc(n)}</td></tr>' for t, val, b, st, n in term_rows(o, R))
    fl = "".join(f'<tr><td class="c"><span class="pill {f["sev"].lower()}">{f["sev"]}</span></td><td>{esc(f["issue"])}</td><td>{esc(f["fix"])}</td></tr>'
                 for f in o["flags"]) or '<tr><td colspan="3">No significant risks found.</td></tr>'
    vf = "".join(f'<tr><td>{esc(a)}</td><td class="c">{pill_status(b)}</td><td class="sm" style="color:var(--text)">{esc(c)}</td></tr>'
                 for a, b, c in checklist(o))
    qs = "".join(f"<tr><td>{i + 1}</td><td>{esc(q)}</td></tr>" for i, q in enumerate(questions(o, R))) or "<tr><td></td><td>None: the offer is complete.</td></tr>"
    gap = f" with {money(o['appraisal_gap'])} gap coverage" if o["appraisal_gap"] else ""
    credit = f" + {money(o['repair_reserve'])} inspection credit" if o["repair_reserve"] else ""
    heads = "".join(f'<th class="n {"hl" if i == 0 else ""}">{n}</th>' for i, (n, _) in enumerate(cols))
    details = f'''<div class="pb"></div><div class="dh">Detailed analysis</div>
<h2>1 · Seller net sheet <span class="h2s">as offered vs. downside{", counter" if o["counter_rows"] else ""} and the seller's target terms</span></h2>
<div class="tbl"><table><colgroup><col style="width:{36 if len(cols) <= 4 else 30}%"></colgroup><thead><tr><th>Line item</th>{heads}</tr></thead><tbody>{ns}</tbody></table></div>
<div class="legend"><span><b>Downside</b>: appraisal at {ref}{gap}{credit}.</span>
<span><b>Seller's target</b>: list price, no concessions, agreed buyer-broker comp., same closing date.</span></div>
<h2>2 · Contingency timeline <span class="h2s">shaded = buyer can still cancel · days from {L["analysis_date"]:%b %-d}</span></h2>{gantt(o, R)}
<h2 class="pb">3 · Terms review <span class="h2s">each term against the seller's preference or local norm</span></h2>
<div class="tbl"><table><colgroup><col style="width:17%"><col style="width:23%"><col style="width:20%"><col style="width:9%"></colgroup>
<thead><tr><th>Term</th><th>Offered</th><th>Benchmark</th><th class="c">Rating</th><th>Note</th></tr></thead><tbody>{tr}</tbody></table></div>
<h2>4 · Certainty scorecard <span class="h2s">1 = weak · 5 = strong · weighted</span></h2>{scorecard_single(o)}
<h2 class="pb">5 · Risk flags</h2><div class="tbl"><table><colgroup><col style="width:8%"><col style="width:50%"></colgroup>
<thead><tr><th class="c">Level</th><th>Issue</th><th>Mitigation</th></tr></thead><tbody>{fl}</tbody></table></div>
<div class="two" style="margin-top:0">
 <div><h2>6 · Verification checklist</h2><div class="tbl"><table><colgroup><col style="width:52%"><col style="width:14%"></colgroup>
 <thead><tr><th>Item</th><th class="c">Status</th><th>Notes</th></tr></thead><tbody>{vf}</tbody></table></div></div>
 <div><h2>7 · Questions for the buyer's agent</h2><div class="tbl"><table class="qs"><colgroup><col style="width:7%"></colgroup>
 <thead><tr><th class="c">#</th><th>Question</th></tr></thead><tbody>{qs}</tbody></table></div></div></div>
<h2>8 · Assumptions &amp; data to confirm</h2>{assumptions_table(R)}
{fine(R)}'''
    sub = f"{esc(L.get('address') or '')} · List {money(L['list_price'])} · Offer {esc(o['id'])} from {esc(o['buyer'])}"
    snap = snapshot(R, "Response due", esc(o.get("expires") or "—"))
    return "Single Offer Review", sub, snap + f'<div class="p1">{page1}</div>' + details


# --- multiple offers -----------------------------------------------------------

def scatter(R):
    offs = R["active"]
    vals = [x for o in offs for x in (o["ns"]["net_adj"], o["ns_down"]["net_adj"])] + [R["target"]["net_adj"]]
    lo, hi = min(vals), max(vals)
    pad = max(2000, (hi - lo) * .12)
    step = 5000 if hi - lo < 40000 else 10000 if hi - lo < 90000 else 25000
    y0, y1 = math.floor((lo - pad) / step) * step, math.ceil((hi + pad) / step) * step
    xmin = max(0, min(40, (min(o["score"]["total"] for o in offs) // 10) * 10))
    W, H, Lm, Rm, T, B = 300, 230, 42, 10, 10, 28

    def xs(val):
        return Lm + (val - xmin) / (100 - xmin) * (W - Lm - Rm)

    def ys(val):
        return T + (1 - (val - y0) / (y1 - y0)) * (H - T - B)

    tgt = R["target"]["net_adj"]
    col = {"ACCEPT": "var(--good-base)", "COUNTER": "var(--good-base)", "BACKUP": "var(--caution-base)", "DECLINE": "var(--risk-base)"}
    svg = [f'<svg viewBox="0 0 {W} {H}" class="scat">',
           f'<rect x="{xs(70)}" y="{ys(y1)}" width="{xs(100) - xs(70)}" height="{max(0, ys(tgt - (y1 - y0) * .1) - ys(y1))}" fill="var(--good-base)" opacity=".07"/>',
           f'<text x="{xs(99)}" y="{ys(y1) + 10}" text-anchor="end" class="q">sweet spot</text>']
    val = y0
    while val <= y1:
        svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{ys(val)}" y2="{ys(val)}" class="gl"/>'
                   f'<text x="{Lm - 4}" y="{ys(val) + 3}" text-anchor="end" class="ax">${val // 1000:,.0f}K</text>')
        val += step
    for x in range(int(xmin), 101, 10):
        svg.append(f'<text x="{xs(x)}" y="{H - B + 12}" text-anchor="middle" class="ax">{x}</text>')
    svg.append(f'<text x="{(Lm + W - Rm) / 2}" y="{H - 3}" text-anchor="middle" class="ax">Certainty score →</text>')
    svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{ys(tgt)}" y2="{ys(tgt)}" stroke="var(--good-base)" stroke-dasharray="4 3"/>'
               f'<text x="{Lm + 3}" y="{ys(tgt) - 3}" class="ax" style="fill:var(--good-strong)">target {money(tgt)} (clean offer at list)</text>')
    for o in offs:
        c = col[o["action"]]
        x, a, b = xs(o["score"]["total"]), ys(o["ns"]["net_adj"]), ys(o["ns_down"]["net_adj"])
        right = o["score"]["total"] > 90
        svg.append(f'<line x1="{x}" x2="{x}" y1="{a}" y2="{b}" stroke="{c}" stroke-width="2" opacity=".5"/>'
                   f'<circle cx="{x}" cy="{a}" r="5" fill="#fff" stroke="{c}" stroke-width="2"/><circle cx="{x}" cy="{b}" r="5" fill="{c}"/>'
                   f'<text x="{x - 9 if right else x + 9}" y="{(a + b) / 2 + 4}" text-anchor="{"end" if right else "start"}" class="pl" style="fill:{c}">{esc(o["id"])}</text>')
    svg.append("</svg>")
    return "".join(svg)


def multi_html(R, v):
    L = R["listing"]
    rk = R["ranked"]
    top = rk[0]
    act = v["action"]
    plan = "".join(f'<tr><td class="c"><b>{esc(p["offer"])}</b></td><td class="act {p["status"]}">{esc(p["action"])}</td><td>{esc(p["terms"])}</td></tr>'
                   for p in v["plan"])
    pill = {"Accept": "rec", "Counter": "rec", "Backup": "med", "Decline": "high"}
    rank = "".join(
        f'<tr class="{"top" if r["rank"] == 1 else ""}"><td class="rk">{r["rank"]}</td><td><b>Offer {esc(r["offer"])}</b><br>'
        f'<span class="sm">{esc(r["financing"])}</span></td><td class="n">{r["price"]}</td><td class="n">{r["net"]}</td>'
        f'<td class="n"><b>{r["downside"]}</b></td><td class="c {({"hi": "hit", "mid": "midt", "lo": "lot"})[r["band_class"]]}"><b>{r["score"]}</b></td>'
        f'<td class="n">{r["risk_days"]} d</td><td class="n">{r["close"]}</td><td class="c"><span class="pill {pill[r["action"]]}">{r["action"]}</span></td></tr>'
        for r in v["ranked"])
    page1 = f'''{hero(v)}
<div class="ctr"><div class="ctrh"><span>OUR PLAN</span><em>{md(v["plan_summary"])}</em></div>
 <table class="plan"><colgroup><col style="width:7%"><col style="width:16%"></colgroup><thead><tr><th class="c">Offer</th><th>Action</th><th>Terms / reason</th></tr></thead><tbody>{plan}</tbody></table>
 <div class="note">{esc(v["plan_note"])}</div></div>
<div class="two" style="grid-template-columns:1.45fr 1fr">
 <div><h2>Offers ranked <span class="h2s">by downside net and certainty</span></h2><div class="tbl"><table class="rank"><colgroup><col style="width:7%"><col style="width:22%"></colgroup>
 <thead><tr><th></th><th>Offer</th><th class="n">Price</th><th class="n">Net</th><th class="n">Downside</th><th class="c">Cert.</th><th class="n">Risk</th><th class="n">Close</th><th class="c">Action</th></tr></thead><tbody>{rank}</tbody></table></div>
 <div class="legend"><span><b>Net</b> = after all costs &amp; holding, as offered. <b>Downside</b> = if the appraisal and inspection go badly. <b>Risk</b> = days the buyer can walk away.</span></div></div>
 <div><h2>Net vs. certainty</h2><div class="panel">{scatter(R)}<div class="legend" style="margin:0"><span><i style="background:#fff;border:1.5px solid var(--grey);border-radius:50%"></i>as offered</span><span><i style="background:var(--grey);border-radius:50%"></i>downside</span></div></div></div></div>
{options_table(v["options"], (28, 12, 10))}{closing_block(v)}'''

    offs = rk
    K = [o["id"] for o in offs]

    def hr(first=""):
        return "<tr><th>" + first + "</th>" + "".join(f'<th class="n">Offer {esc(k)}</th>' for k in K) + "</tr>"

    def cls(vals):
        return ["best" if x == max(vals) else ("worst" if x == min(vals) else "") for x in vals]

    cols = [(k, o["ns"]) for k, o in zip(K, offs)]
    ns = netsheet_body(cols, hl=-1)
    adj = [o["ns"]["net_adj"] for o in offs]
    ns += '<tr class="total2"><td>Net after holding costs</td>' + "".join(f'<td class="n {c}">{acct(x)}</td>' for x, c in zip(adj, cls(adj))) + "</tr>"
    down = [o["ns_down"]["net_adj"] for o in offs]
    ref = f"CMA midpoint ({money(round(L['cma_mid']))})" if L["cma_provided"] else "list price"
    ap = ("<tr><td>Offer price</td>" + "".join(f'<td class="n">{money(o["price"])}</td>' for o in offs) + "</tr>"
          + f"<tr><td>vs. {'CMA high' if L['cma_provided'] else 'list price'} ({money(L['cma_high'])})</td>" + "".join(
              f'<td class="n"><span class="{"rt" if o["price"] > L["cma_high"] else "gt"}">{signed(o["price"] - L["cma_high"])}</span></td>' for o in offs) + "</tr>"
          + "<tr><td>Appraisal gap buyer covers</td>" + "".join(
              f'<td class="n">{"Not needed" if not o["financed"] or not o["appraisal_days"] else (money(o["appraisal_gap"]) if o["appraisal_gap"] else "None")}</td>' for o in offs) + "</tr>"
          + f"<tr><td>Price if appraised at {ref}</td>" + "".join(f'<td class="n">{money(o["downside_price"])}</td>' for o in offs) + "</tr>"
          + "<tr><td>Inspection credit reserve</td>" + "".join(f'<td class="n neg">{acct(-o["repair_reserve"])}</td>' for o in offs) + "</tr>"
          + '<tr class="total2"><td>Downside net after holding</td>' + "".join(f'<td class="n {c}">{acct(x)}</td>' for x, c in zip(down, cls(down))) + "</tr>")
    weeks = min(12, max(math.ceil(max(o["close_days"] for o in offs) / 7) + 1, 6))
    tl = "<tr><th>Offer</th>" + "".join(f'<th class="c">Wk {w + 1}<br><span class="sm2">{(L["analysis_date"] + timedelta(days=7 * w)):%-m/%-d}</span></th>'
                                         for w in range(weeks)) + '<th class="n">At risk</th></tr>'
    for o in offs:
        tl += f"<tr><td><b>{esc(o['id'])}</b></td>"
        for w in range(weeks):
            d0, d1 = 7 * w + 1, 7 * w + 7
            if d0 <= o["close_days"] <= d1:
                tl += '<td class="tc close">CLOSE</td>'
            elif d0 > o["close_days"]:
                tl += '<td class="tc"></td>'
            else:
                open_ = [n for n, d in (("Insp", o["inspection_days"]), ("Sale", o["sale_contingency_days"]),
                                        ("Appr", o["appraisal_days"]), ("Loan", o["loan_approval_days"])) if d >= d0]
                c = "hot" if ("Sale" in open_ or "Insp" in open_) else ("warm" if open_ else "safe")
                tl += f'<td class="tc {c}">{" · ".join(open_) if open_ else "firm"}</td>'
        tl += f'<td class="n"><b>{o["risk_days"]} d</b></td></tr>'
    tmap = [{r[0]: r for r in term_rows(o, R)} for o in offs]
    labels = []
    for t in tmap:
        for k in t:
            if k not in labels:
                labels.append(k)
    terms = '<tr><td>Buyer / agent</td>' + "".join(f'<td>{esc(o["buyer"])}<br><span class="sm">{esc(o.get("buyer_agent") or "")}</span></td>' for o in offs) + "</tr>"
    for lab in labels:
        terms += f"<tr><td>{lab}</td>" + "".join(f'<td class="{t[lab][3] if lab in t else ""}">{t[lab][1] if lab in t else "—"}</td>' for t in tmap) + "</tr>"
    sc = ""
    for k, lab, w in oe.CRITERIA:
        sc += f'<tr><td>{lab}</td><td class="n">{w}%</td>' + "".join(
            f'<td class="c s{o["score"]["scores"][k]}">{o["score"]["scores"][k]}{"*" if o["score"]["src"][k] == "agent" else ""}</td>' for o in offs) + "</tr>"
    sc += '<tr class="total"><td>Certainty score (weighted, 0–100)</td><td class="n">100%</td>' + "".join(
        f'<td class="c {({"hi": "hit", "mid": "midt", "lo": "lot"})[o["score"]["band"][0]]}"><b>{o["score"]["total"]}</b></td>' for o in offs) + "</tr>"
    fl = "".join(f'<tr><td class="c"><b>{esc(o["id"])}</b></td><td class="c"><span class="pill {f["sev"].lower()}">{f["sev"]}</span></td>'
                 f'<td>{esc(f["issue"])}</td><td>{esc(f["fix"])}</td></tr>' for o in offs for f in o["flags"])
    cl = [checklist(o) for o in offs]
    vf = "".join(f"<tr><td>{esc(cl[0][i][0])}</td>" + "".join(f'<td class="c">{pill_status(c[i][1])}</td>' for c in cl) + "</tr>" for i in range(len(cl[0])))
    ctr = ""
    if act == "COUNTER" and top["counter_rows"]:
        ctr = (f'<h2>8 · Counter to Offer {esc(top["id"])} <span class="h2s">full terms</span></h2><div class="tbl"><table><colgroup><col style="width:20%"><col style="width:17%"><col style="width:17%"></colgroup>'
               '<thead><tr><th>Term</th><th>Offered</th><th>Counter</th><th>Why</th></tr></thead><tbody>'
               + "".join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td><td class="good"><b>{esc(c)}</b></td><td>{esc(d)}</td></tr>' for a, b, c, d in top["counter_rows"])
               + "</tbody></table></div>")
    details = f'''<div class="pb"></div><div class="dh">Detailed comparison</div>
<h2>1 · Seller net sheet <span class="h2s">as offered · green = best, red = weakest</span></h2>
<div class="tbl"><table><colgroup><col style="width:30%"></colgroup><thead>{hr("Line item")}</thead><tbody>{ns}</tbody></table></div>
<h2>2 · Appraisal &amp; inspection exposure <span class="h2s">what each offer is worth if the appraisal and inspection go badly</span></h2>
<div class="tbl"><table><colgroup><col style="width:30%"></colgroup><thead>{hr()}</thead><tbody>{ap}</tbody></table></div>
<h2>3 · Contingency timeline <span class="h2s">weeks from {L["analysis_date"]:%b %-d} · when each buyer can still walk away</span></h2>
<div class="tbl"><table style="table-layout:fixed"><colgroup><col style="width:6%">{"".join(f'<col style="width:{86 / weeks:.1f}%">' for _ in range(weeks))}<col style="width:8%"></colgroup><thead>{tl}</thead></table></div>
<div class="legend"><span><i class="hot"></i>Inspection / sale-of-home</span><span><i class="warm"></i>Financing / appraisal open</span><span><i class="safe"></i>Firm</span><span><i class="closei"></i>Closing</span></div>
<h2 class="pb">4 · Terms comparison <span class="h2s">green = favorable · amber = watch · red = weak</span></h2>
<div class="tbl"><table><colgroup><col style="width:16%"></colgroup><thead><tr><th>Term</th>{"".join(f"<th>Offer {esc(k)}</th>" for k in K)}</tr></thead><tbody>{terms}</tbody></table></div>
<h2>5 · Certainty scorecard <span class="h2s">1 = weak · 5 = strong · * = set by agent</span></h2>
<div class="tbl"><table><colgroup><col style="width:34%"><col style="width:10%"></colgroup><thead><tr><th>Criterion</th><th class="n">Weight</th>{"".join(f'<th class="c">Offer {esc(k)}</th>' for k in K)}</tr></thead><tbody>{sc}</tbody></table></div>
<h2 class="pb">6 · Risk flags</h2><div class="tbl"><table><colgroup><col style="width:6%"><col style="width:8%"><col style="width:48%"></colgroup>
<thead><tr><th class="c">Offer</th><th class="c">Level</th><th>Issue</th><th>Mitigation</th></tr></thead><tbody>{fl or "<tr><td colspan=4>No significant risks found.</td></tr>"}</tbody></table></div>
<h2>7 · Verification checklist</h2><div class="tbl"><table><colgroup><col style="width:40%"></colgroup><thead><tr><th>Item</th>{"".join(f'<th class="c">Offer {esc(k)}</th>' for k in K)}</tr></thead><tbody>{vf}</tbody></table></div>
{ctr}
<h2>{"9" if ctr else "8"} · Assumptions &amp; data to confirm</h2>{assumptions_table(R)}
{fine(R)}'''
    sub = f"{esc(L.get('address') or '')} · List {money(L['list_price'])} · {len(R['active'])} active offers"
    return "Multiple Offer Review", sub, snapshot(R, "Offers", str(len(R["active"]))) + f'<div class="p1">{page1}</div>' + details


# --- document ------------------------------------------------------------------

def build_html(R, agent, sample=False, mode="auto", offer_id=None):
    mode, o = review.pick(R, mode, offer_id)
    v = review.single_view(R, o) if mode == "single" else review.multi_view(R)
    title, sub, body = single_html(R, o, v) if mode == "single" else multi_html(R, v)
    theme = design.theme(agent.get("brand"), "seller")
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    doc = render.page(header(R, title, sub, agent, sample) + body, css=css, title=title, theme_css=design.css_vars(theme))
    return doc, mode, o


def fit_page_one(pg):
    """Measure page 1; switch to the compact layout when it would spill onto page 2."""
    top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > PAGE1_LIMIT:
        pg.evaluate("() => document.body.classList.add('compact')")
        top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    return top


def build(data, fmt, out_dir, ctx):
    R = review.analyze(data, ctx.get("market"), review.load_cma(data, ctx.get("cma")))
    doc, mode, o = build_html(R, ctx["agent"], ctx.get("sample") or R["sample"], ctx.get("mode") or "auto", ctx.get("offer"))
    street = (R["listing"].get("address") or "Listing").split(",")[0]
    name = render.filename(street, f"Offer {o['id']} Review" if mode == "single" else "Multiple Offer Review", ext="pdf")
    path = os.path.join(out_dir, name)
    label = f"{'Single' if mode == 'single' else 'Multiple'} Offer Review · Seller side · {street}"
    top = render.html_to_pdf(doc, path, footer_html=render.footer(label), before_print=fit_page_one)
    if top > PAGE1_LIMIT:
        print(f"Page 1 overflows by {top - PAGE1_LIMIT:.0f}px; shorten the counter notes or custom flags.", file=sys.stderr)
    for a in R["missing"][:6]:
        print(f"Assumed [{a['impact']}] {a['why']}", file=sys.stderr)
    return [path]


def options(ap):
    ap.add_argument("--cma", help="cma-handoff v1 file (.cma.json or markdown with the block)")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single review while others are active")


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, extra_args=options, errors=(oe.OfferError, handoff.HandoffError))


if __name__ == "__main__":
    main(sys.argv[1:])
