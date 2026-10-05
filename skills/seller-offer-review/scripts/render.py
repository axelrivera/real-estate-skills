"""Offer review PDF for the seller (listing side): one offer, or every active offer compared.

    python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID]
                              [--profile profile.md] [--sample] [--out DIR]

review.py builds the document model once (render.main's compute step): every figure, label and note is already in
it. This file only places it with the shared layout kit. Single review: page 1 is a self-contained executive summary
(the recommendation, the counter, key numbers, certainty and the seller's options); the pages after it hold the net
sheet, contingency timeline, terms review, scorecard, risk flags, checklist, questions, what to confirm and the notes.
Comparison: a two-page landscape decision summary, one row per offer. A comparison always comes with a single review of
every active offer, each its own PDF (OFR-318). Colors follow the agent's seller-side brand color.
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review  # noqa: E402
from _shared import design, fmt, handoff, layout, offer_engine as oe, render  # noqa: E402



def esc(text):
    """Escaped text; a minus sign stays joined to its figure (no line break between − and $)."""
    return html.escape(str(text)).replace("−$", "−⁠$")


Raw, Col = layout.Raw, layout.Col
L_ = review.L_
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "offer-review.css")
PILL = {"good": "low", "caution": "med", "risk": "high"}
BAND_TEXT = {"hi": "hit", "mid": "midt", "lo": "lot", "na": ""}

# OFR-292: page 1's blocks that grow with the data, named in the overflow warning (the tallest ones first)
PAGE1_BLOCKS = ((".p1 .hero .why", "the recommendation text"), (".p1 .ctr", "the counter or plan table"),
                (".p1 .kpis", "the key numbers"), (".p1 .two", "the certainty, risks and chart row"),
                (".p1 .opts", "the options table"), (".p1 .prelim", "the Preliminary line"),
                (".p1 .treason", "the Terms Reason"))
# Page 1 fits by these steps, in order, until it fits: the compact layout; (OFR-292) the Terms Reason to the top of
# page 2; in the comparison, the chart to page 2 (the options table then takes the full width); a tighter layout; in a
# single review, the options table to the top of page 2; last, the data note (the fine print under the next step) to
# the top of page 2. The detail pages print denser when that saves a short last page.
STEPS = (
    "compact",
    "() => { const r = document.querySelector('.p1 .treason'), s = document.querySelector('.treason-slot');"
    " if (r && s) s.appendChild(r); }",
    "() => { const c = document.querySelector('.p1 .chartbox'), s = document.querySelector('.chart-slot');"
    " if (c && s) { s.appendChild(c); document.querySelector('.p1 .lower').classList.add('solo'); } }",
    "tight",
    "() => { const o = document.querySelector('.p1 .optsbox'), s = document.querySelector('.opts-slot');"
    " if (o && s) s.appendChild(o); }",
    "() => { const n = document.querySelector('.p1 .datanote'), s = document.querySelector('.datanote-slot');"
    " if (n && s) s.appendChild(n); }",
)


def fit(multi):
    return layout.Fit(end=".dh", steps=STEPS, tail=("dense",), tail_below=0.35, blocks=PAGE1_BLOCKS, landscape=multi,
                      tail_hint="the detail sections")


def md(text):
    """Escape, then turn the summary's **bold** into <b>."""
    return Raw(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text or "")))


def pill(sev, text=None):
    return Raw(f'<span class="pill {esc(sev.lower())}">{esc(text or sev)}</span>')


# --- shared blocks -------------------------------------------------------------

def header(M, agent, sample):
    d = M["doc"]
    # DS-103: the date never wraps; a name too long for the block wraps between words (report.css caps its width)
    lines = [Raw(f'Prepared for <b>{esc(d["prepared_for"])}</b> · <span class="nw">{esc(d["date"])}</span>')]
    if agent.get("name"):
        lines.append(Raw(f'<b>{esc(agent["name"])}</b>'))
        org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {agent["license"]}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return layout.header(d["title"], d["subtitle"], prepared=lines, tag=d["tag"], sample=sample)


def facts(M):
    """The divider row: the home, then the inputs the numbers rest on; a missing one in the risk color."""
    return layout.fact_row([Raw(f'<b class="rt">{esc(f["text"])}</b>') if f["risk"] else f["text"] for f in M["doc"]["facts"]])


def hero(v):
    cls = {"DECLINE": "decline", "BACKUP": "backup", "INCOMPLETE": "decline"}.get(v["action"], "")
    n = v["offers_active"]
    ctx = review.t("kicker_active", n=n) if n > 1 else ""
    kicker = L_["kicker_status"] if v["action"] == "INCOMPLETE" else L_["kicker_response"]
    also = "".join(f'<span class="rba"><b>{esc(a["when"])}</b><span class="sep"> · </span><span class="rbw">{esc(a["what"])}</span></span>'
                   for a in v.get("respond_by_also") or ())  # OFR-319, OFR-320
    return (f'<div class="hero"><div class="hl {cls}"><span class="k">{esc(kicker + ctx)}</span><div class="big">{esc(v["headline"])}</div>'
            f'<div class="who">{esc(v.get("who") or v["offer_label"])}</div><div class="why">{md(v["why"])}</div></div>'
            f'<div class="hr{" stack" if v["mode"] == "single" else ""}"><span class="k">{esc(L_["k_respond_by"])}</span>'
            f'<b>{esc(v["respond_by"])}</b>'
            + (f'<span class="rbo">{esc(v["respond_by_offer"])}</span>' if v.get("respond_by_offer") else "") + also
            + f'<span class="k" style="margin-top:6px">{esc(L_["k_priority"])}</span><div>{esc(v["priority"])}</div></div></div>')


def box(kind, head, sub, inner, cls=""):
    """The outlined box under the answer (our counter, fix before review, accept, how it compares, our plan)."""
    return (f'<div class="ctr {kind} {cls}"><div class="ctrh"><span>{esc(head)}</span><em>{md(sub)}</em></div>{inner}</div>')


def counter_table(cols, rows):
    """Term, offered, arrow, counter, why; the time for acceptance stays on one line (fmt.when)."""
    spec = [Col("term", cols[0], cls="term"), Col("offered", cols[1], cls="was"), Col("arr", cols[2], cls="arr"),
            Col("counter", cols[3], cls="now"), Col("why", cols[4], cls="why2")]
    body = [{**r, "term": Raw(f"<b>{esc(r['term'])}</b>"), "arr": "→"} for r in rows]
    return layout.table(spec, body, keep="whole", cls="ctrt", row_classes={i: "oneline" for i, r in enumerate(rows) if r.get("oneline")})


def options_table(opts, short=False):
    """short: name offers by their key (OFR-324), where the plan table above shows each key beside its label."""
    if not opts:
        return ""
    rec = esc(L_["lbl_recommended"])
    rows = [{"option": Raw(f'<b>{esc(x.get("short") if short and x.get("short") else x["option"])}</b>'
                           + (f' <span class="sm">{rec}</span>' if x["recommended"] else "")),
             "net": x["net"], "certainty": x["certainty"], "what": x["what"]} for x in opts]
    classes = {i: f'st-{x["status"]}' + (" recrow" if x["recommended"] else "") for i, x in enumerate(opts)}
    cols = [Col("option", L_["th_option"], cls="opt"), Col("net", L_["th_net_holding"], align="num"),
            Col("certainty", L_["th_certainty"], cls="c"), Col("what", L_["th_what_happens"], cls="what")]
    return (f'<div class="optsbox"><h2>{esc(L_["h_options"])}</h2>'
            + layout.table(cols, rows, keep="whole", cls="opts", row_classes=classes) + "</div>")


def closing_block(v, follow):
    pre = f'<div class="prelim">{md(v["preliminary"])}</div>' if v["preliminary"] else ""
    if v.get("terms_reason"):  # OFR-279; OFR-292: moves to page 2 when page 1 is full
        pre = f'<div class="nextstep treason"><b>{esc(L_["lbl_terms_reason"])}</b> {esc(v["terms_reason"])}</div>' + pre
    return (f'{pre}<div class="nextstep"><b>{esc(L_["lbl_next_step"])}</b> {esc(v["next_step"])} {esc(follow)}</div>'
            f'<div class="fine datanote">{md(v["data_note"])}</div>')


def certainty_panel(c):
    note = f'<div class="legend"><span>{esc(c["walk_away_note"])}</span></div>' if c.get("walk_away_note") else ""
    b = c["band_class"]
    tc = BAND_TEXT[b]
    dep = esc(c["deposit"]) if c["deposit_known"] else f'<span class="rt">{esc(c["deposit"])}</span>'
    return (f'<div><h2>{esc(L_["h_certainty"])} <span class="h2s">{esc(L_["h_certainty_sub"])}</span></h2><div class="panel">'
            f'<div class="gauge"><b class="{tc}">{c["score"]}</b><span>/100 · <b class="{tc}" style="font-size:inherit">'
            f'{esc(c["band"])}</b> {esc(L_["certainty_word"])}</span></div>'
            f'<div class="meter"><div class="bar {b}" style="width:{c["score"]}%"></div></div><table class="facts2">'
            f'<tr><td>{esc(L_["cert_walk"])}</td><td class="n"><b>{esc(c["walk_away_until"])}</b></td></tr>'
            f'<tr><td>{esc(L_["cert_deposit"])}</td><td class="n">{dep}</td></tr>'
            f'<tr><td>{esc(L_["cert_closing"])}</td><td class="n"><b class="{"" if c["closing_ok"] else "rt"}">{esc(c["closing"])}</b></td></tr>'
            f'<tr><td>{esc(L_["cert_threat"])}</td><td class="n"><b class="rt">{esc(c["threat"])}</b></td></tr>'
            f'</table>{note}</div></div>')


def confirm_table(d):
    """What to Confirm: every assumption the report rests on (OFR-257: the data note counts this same list)."""
    if not d["confirm"]:
        return f'<h2>{esc(d["h_confirm"])}</h2><p class="sm">{esc(d["confirm_none"])}</p>'
    cols = [Col("impact", d["confirm_cols"][0], cls="c imp"), Col("where", d["confirm_cols"][1], cls="where"),
            Col("what", d["confirm_cols"][2])]
    rows = [{"impact": Raw(f'<span class="pill {a["impact"]}">{esc(a["impact_label"])}</span>'), "where": a["where"],
             "what": a["what"]} for a in d["confirm"]]
    return f'<h2>{esc(d["h_confirm"])}</h2>' + layout.table(cols, rows, keep="brk", cls="confirm")


def closing_notes(M, agent):
    return (layout.notes_block(M["notes"], title=L_["h_notes"])
            + render.notices(agent, [render.NOT_ADVICE]))


# --- single review ------------------------------------------------------------

def page_box(v, d):
    b = d["box"]
    if not b:
        return ""
    if b["kind"] == "counter":
        note = f'<div class="note">{esc(b["note"])}</div>' if b.get("note") else ""
        return box("", b["head"], b["sub"], counter_table(b["cols"], b["rows"]) + note)
    if b["kind"] == "fixes":
        cols = [Col("cb", b["cols"][0], cls="c cbc"), Col("issue", b["cols"][1], cls="issue"), Col("fix", b["cols"][2], cls="why2")]
        rows = [{"cb": Raw('<span class="cb"></span>'), "issue": Raw(f'{pill(f["sev"])} <b>{esc(f["issue"])}</b>'),
                 "fix": f["fix"]} for f in b["rows"]]
        return box("stop", b["head"], b["sub"], layout.table(cols, rows, keep="whole", cls="ctrt"))
    if b["kind"] == "accept":
        cols = [Col("term", "", cls="term"), Col("value", "", cls="now"), Col("bench", "", cls="why2")]
        rows = [{"term": Raw(f"<b>{esc(r['term'])}</b>"), "value": r["value"], "bench": r["bench"]} for r in b["rows"]]
        return box("", b["head"], b["sub"], layout.table(cols, rows, keep="whole", cls="ctrt", head=False))
    cols = [Col(0, b["cols"][0], cls="term"), Col(1, b["cols"][1]), Col(2, b["cols"][2], cls="now")]
    rows = [[Raw(f"<b>{esc(r[0])}</b>"), r[1], r[2]] for r in b["rows"]]
    return box("cmp", b["head"], b["sub"], layout.table(cols, rows, keep="whole", cls="ctrt"))


def kpis(v):
    items = []
    for i, k in enumerate(v["kpis"]):
        cls = f't-{k["tone"] or "plain"}' + (" vnote" if i == 1 else "")
        items.append((k["label"], k["value"], k.get("note") or "", cls))
    return layout.tiles(items, n=4, cls="kpis")


def risks_table(v):
    none = L_["risks_see_fixes"] if v["action"] == "INCOMPLETE" else L_["no_risks"]  # DS-106
    if not v["risks"]:
        return layout.table([Col(0, "")], [[none]], keep="whole", head=False)
    cols = [Col("sev", "", cls="c lvl"), Col("issue", "")]
    return layout.table(cols, [{"sev": pill(r["sev"]), "issue": r["issue"]} for r in v["risks"]], keep="whole", head=False, cls="risks")


def net_sheet_table(ns):
    cols = [Col("label", L_["th_line_item"], cls="lbl")] + [Col(i, c, align="num", cls="hl" if i == 0 else "")
                                                            for i, c in enumerate(ns["columns"])]

    def cells(r, best=False):
        out = {"label": r["label"]}
        for i, c in enumerate(r["cells"]):
            cls = " ".join(x for x in ("neg" if c.get("neg") and not best else "", c.get("cls", "")) if x)
            out[i] = Raw(f'<span class="{cls}">{esc(c["text"])}</span>') if cls else c["text"]
        return out
    rows = [cells(r) for r in ns["rows"]] + [cells(ns["net"]), cells(ns["holding"]), cells(ns["net_adj"], True),
                                             cells(ns["vs_target"])]
    n = len(ns["rows"])
    classes = {n: "total", n + 2: "total2", n + 3: "alt"}
    caps = "".join(f'<span><b>{esc(c["term"])}</b>: {esc(c["text"])}</span>' for c in ns["captions"])
    return (f'<h2>{esc(ns["head"])} <span class="h2s">{esc(ns["sub"])}</span></h2>'
            + layout.table(cols, rows, keep="whole", cls="netsheet", row_classes=classes)
            + f'<div class="legend caps">{caps}</div>')


TH_PX = 8 * 96 / 72  # a table header's 8pt type (report.css th), in px
SWATCH = {"hot": "color-mix(in srgb,var(--risk-base) 55%,#fff)", "warm": "var(--caution-border)", "rider": "color-mix(in srgb,var(--brand-strong) 40%,#fff)",
          "close": "var(--brand-deep)", "deadline": "var(--risk-base)"}


def timeline_table(tl):
    """The contingency timeline: one shaded row per window, the closing's cell and the seller's deadline; the legend
    names only what's drawn (layout.Chart)."""
    chart = layout.Chart()
    ncell, per = tl["ncell"], tl["per_week"]

    def gx(i):
        c = "wk " if i % per == 0 else ""
        return c + ("dl" if tl["deadline_cell"] is not None and i == tl["deadline_cell"] else "")
    # A week's date prints only where it fits its columns (measured with the bundled font): the day cells share what
    # the name, days and end columns (37%) leave of the page width
    cell_px = layout.Fit().content_px()[0] * 0.63 / ncell
    head = (f'<tr><th class="tlname">{esc(tl["head"][0])}</th><th class="n tld">{esc(tl["head"][1])}</th>'
            f'<th class="n tle">{esc(tl["head"][2])}</th>'
            + "".join(f'<th colspan="{w["span"]}" class="c nw">'
                      + (esc(w["label"]) if layout.text_width(w["label"], TH_PX, bold=True) <= w["span"] * cell_px - 12 else "")
                      + "</th>" for w in tl["weeks"]) + "</tr>")
    body = ""
    for r in tl["rows"]:
        if r["on"]:
            chart.mark(r["kind"], tl["legend"][r["kind"]], "bar", SWATCH[r["kind"]])
        cells = "".join(f'<td class="gantt {gx(i)} {"on-" + r["kind"] if i < r["on"] else ""}"><div></div></td>' for i in range(ncell))
        body += f'<tr><td>{esc(r["name"])}</td><td class="n">{esc(r["days"])}</td><td class="n">{esc(r["end"])}</td>{cells}</tr>'
    c = tl["closing"]
    chart.mark("close", tl["legend"]["close"], "bar", SWATCH["close"])
    if tl["deadline_cell"] is not None and tl["deadline_cell"] < ncell:
        chart.mark("deadline", tl["legend"]["deadline"], "line", SWATCH["deadline"])
    sub = f' <span class="sm">{esc(c["sub"])}</span>' if c["sub"] else ""
    body += (f'<tr><td><b>{esc(c["name"])}</b>{sub}</td><td class="n">{esc(c["days"])}</td><td class="n">{esc(c["end"])}</td>'
             + "".join(f'<td class="gantt {gx(i)} {"on-close" if i == c["cell"] else ""}"><div></div></td>' for i in range(ncell))
             + "</tr>")
    return (f'<h2>{esc(tl["h"])} <span class="h2s">{esc(tl["subtitle"])}</span></h2>'
            f'<div class="tbl gantt-tbl"><table style="table-layout:fixed"><thead>{head}</thead><tbody>{body}</tbody></table></div>'
            f'<div class="tlfoot">{chart.legend()}<span class="firm">{esc(tl["firm"])}</span></div>')


def terms_table(tm):
    cols = [Col("term", tm["cols"][0], cls="term"), Col("offered", tm["cols"][1], cls="offered"),
            Col("benchmark", tm["cols"][2], cls="bench"), Col("rating", tm["cols"][3], cls="c rating"),
            Col("note", tm["cols"][4], cls="sm2 note")]
    rows, classes = [], {}
    if tm["who"]:
        rows.append({"term": tm["who_label"], "offered": tm["who"]})
        classes[0] = "who"
    for r in tm["rows"]:
        classes[len(rows)] = f'st-{r["status"]}'
        rows.append({**r, "rating": Raw(f'<span class="pill {PILL[r["status"]]}">{esc(r["rating"])}</span>')})
    return (f'<h2>{esc(tm["h"])} <span class="h2s">{esc(tm["sub"])}</span></h2>'
            + layout.table(cols, rows, keep="brk", cls="terms", row_classes=classes))


def scorecard_table(sc):
    cols = [Col("label", sc["cols"][0]), Col("weight", sc["cols"][1], align="num"),
            Col("score", sc["cols"][2], cls="c"), Col("why", sc["cols"][3])]
    rows = [{"label": r["label"], "weight": r["weight"], "why": r["why"],
             "score": fmt.EMPTY if r["score"] is None else Raw(f'<span class="s{r["score"]}">{r["score"]}</span>')}
            for r in sc["rows"]]
    tt = sc["total"]
    tc = BAND_TEXT[tt["cls"]]
    total = {"label": tt["label"], "weight": tt["weight"], "score": Raw(f'<b class="{tc}">{tt["score"]}</b>'),
             "why": Raw(f'<span class="{tc}"><b>{esc(tt["band"])}</b> · {esc(tt["scale"])}</span>')}
    return (f'<h2>{esc(sc["h"])} <span class="h2s">{esc(sc["sub"])}</span></h2>'
            + layout.table(cols, rows, total=total, keep="whole", cls="score")
            + f'<div class="legend"><span>{esc(sc["legend"])}</span></div>')


def flags_table(fl):
    cols = [Col("sev", fl["cols"][0], cls="c lvl"), Col("issue", fl["cols"][1], cls="issue"), Col("fix", fl["cols"][2])]
    rows = [{"sev": pill(f["sev"]), "issue": f["issue"], "fix": f["fix"]} for f in fl["rows"]]
    if not rows:
        rows = [{"issue": fl["none"]}]
    return f'<h2>{esc(fl["h"])}</h2>' + layout.table(cols, rows, keep="brk", cls="flags")


def checklist_table(ck):
    cols = [Col("done", ck["cols"][0], cls="c cbc"), Col("item", ck["cols"][1], cls="item"), Col("note", ck["cols"][2], cls="sm2")]
    rows = [{"done": Raw('<span class="cb on">✓</span>' if r["done"] else '<span class="cb"></span>'), "item": r["item"],
             "note": r["note"]} for r in ck["rows"]]  # printed once: a box to tick by hand
    return f'<h2>{esc(ck["h"])}</h2>' + layout.table(cols, rows, keep="whole", cls="ck")


def questions_table(q, none=None):
    cols = [Col("n", q["cols"][0], cls="c qn"), Col("q", q["cols"][1])]
    rows = [{"n": str(i + 1), "q": x} for i, x in enumerate(q["rows"])] or [{"n": "", "q": none or ""}]
    return f'<h2>{esc(q["h"])}</h2>' + layout.table(cols, rows, keep="whole", cls="qs")


def single_body(M, agent):
    v, d = M["summary"], M["doc"]
    two = (f'<div class="two">{certainty_panel(v["certainty"])}<div><h2>{esc(L_["h_risks"])}</h2>'
           f'{risks_table(v)}</div></div>')
    page1 = f'{hero(v)}{page_box(v, d)}{kpis(v)}{two}{options_table(v["options"])}{closing_block(v, d["follow"])}'
    rv = d["revive"]
    revive = box("cmp", rv["head"], rv["sub"], counter_table(rv["cols"], rv["rows"])) if rv else ""
    details = (f'<div class="dh pb">{esc(d["dh"])}</div><div class="treason-slot"></div><div class="opts-slot"></div><div class="datanote-slot"></div>'
               + net_sheet_table(d["net_sheet"]) + revive + timeline_table(d["timeline"]) + terms_table(d["terms"])
               + scorecard_table(d["scorecard"]) + flags_table(d["flags"]) + checklist_table(d["checklist"])
               + questions_table(d["questions"], d["questions"]["none"]) + questions_table(d["lender"])
               + confirm_table(d) + closing_notes(M, agent))
    return facts(M) + f'<div class="p1">{page1}</div>' + details


# --- comparison ---------------------------------------------------------------

def plan_box(v, d):
    p = d["plan"]
    pills = {"Accept": "rec", "Counter": "rec", "Wait": "rec", "Hold as Backup": "med", "Decline": "high", "Incomplete": "blocking"}
    cols = [Col("rk", p["cols"][0], cls="rk"), Col("offer", p["cols"][1], cls="nw2"), Col("financing", p["cols"][2], wrap="nowrap"),
            Col("action", p["cols"][3], cls="c"), Col("price", p["cols"][4], align="num"),
            Col("net", p["cols"][5], align="num"), Col("downside", p["cols"][6], align="num"),
            Col("score", p["cols"][7], cls="c"), Col("walk", p["cols"][8], align="num"),
            Col("close", p["cols"][9], align="num"), Col("terms", p["cols"][10], cls="why2")]
    rows = []
    for r in v["ranked"]:
        rows.append({"rk": str(r["rank"]), "offer": Raw(f'<b>{esc(r["key"])}</b> · <b>{esc(r["offer"])}</b>'),
                     "financing": r["financing"],
                     "action": Raw(f'<span class="pill {pills.get(r["action"], "med")}">{esc(r["action"])}</span>'),
                     "price": Raw(esc(r["price_display"]) + (f'<br><span class="sm">{esc(p["escalated"])}</span>'
                                                              if r["escalated"] else "")),
                     "net": r["net"], "downside": Raw(f'<b>{esc(r["downside"])}</b>'),
                     "score": Raw(f'<b class="{BAND_TEXT[r["band_class"]]}">{esc(str(r["score"]))}</b>'),
                     "walk": r["walk"], "close": r["close"], "terms": r["terms"]})
    inner = (layout.table(cols, rows, keep="whole", cls="rank", row_classes={0: "top"})
             + f'<div class="note">{esc(p["note"])}</div>')
    return box("", p["head"], p["sub"], inner)


ACTION_COLOR = {"ACCEPT": "good", "COUNTER": "good", "BACKUP": "caution", "DECLINE": "risk"}


def place_label(text, x, ya, yb, size, boxes, left, right, top, bottom):
    """(tx, ty, anchor) for a point's label: beside its marks, right then left, at the middle, then level with the as
    offered or downside mark, whichever covers the fewest marks and labels already placed (text measured with the
    bundled font, layout.text_width)."""
    w = layout.text_width(text, size, bold=True)
    mid = (ya + yb) / 2 + size * 0.35
    spots = []
    for ty in (mid, min(ya, yb) - 2, max(ya, yb) + size):
        for anchor, tx in (("start", x + 9), ("end", x - 9)):
            x0 = tx if anchor == "start" else tx - w
            spots.append((tx, ty, anchor, (x0, ty - size, x0 + w, ty + 2)))

    def cost(s):
        x0, y0, x1, y1 = s[3]
        out = max(0, left - x0) + max(0, x1 - right) + max(0, top - y0) + max(0, y1 - bottom)
        return out * 1000 + sum(max(0, min(x1, c[2]) - max(x0, c[0])) * max(0, min(y1, c[3]) - max(y0, c[1])) for c in boxes)
    best = min(spots, key=cost)  # min keeps the first of equals
    boxes.append(best[3])
    return best[:3]


def target_label_spot(label, y, left, right, boxes, size=10):
    """(x, y, anchor) for the Target line's label: above or below the line, at the left or right end, whichever covers
    the fewest chart marks and point labels (the first free spot in that order)."""
    w = layout.text_width(label, size)

    def overlap(b):
        x0, y0, x1, y1 = b
        return sum(max(0, min(x1, c[2]) - max(x0, c[0])) * max(0, min(y1, c[3]) - max(y0, c[1])) for c in boxes)
    spots = [(left, y - 3, "start", (left, y - 12, left + w, y - 1)), (right, y - 3, "end", (right - w, y - 12, right, y - 1)),
             (left, y + 11, "start", (left, y + 2, left + w, y + 13)), (right, y + 11, "end", (right - w, y + 2, right, y + 13))]
    x, ty, anchor, _ = min(spots, key=lambda s: overlap(s[3]))
    return x, ty, anchor


def scatter(ch, W=420, H=200):
    """Net vs. certainty: every position from the model's numbers, every label from the model's text."""
    xmin, y0, y1 = ch["x_min"], ch["y0"], ch["y1"]
    Lm, Rm, T, B = 46, 10, 10, 28
    legend = layout.Chart()

    def xs(val):
        return Lm + (val - xmin) / (100 - xmin) * (W - Lm - Rm)

    def ys(val):
        return T + (1 - (val - y0) / (y1 - y0)) * (H - T - B)
    tgt = ch["target"]
    svg = [f'<svg viewBox="0 0 {W} {H}" class="scat">',
           f'<rect x="{xs(70):.1f}" y="{ys(y1):.1f}" width="{xs(100) - xs(70):.1f}" '
           f'height="{max(0, ys(tgt - (y1 - y0) * .1) - ys(y1)):.1f}" fill="var(--good-base)" opacity=".07"/>',
           f'<text x="{xs(99):.1f}" y="{ys(y1) + 10:.1f}" text-anchor="end" class="q">{esc(ch["sweet"])}</text>']
    for tk in ch["y_ticks"]:
        y = ys(tk["value"])
        svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{y:.1f}" y2="{y:.1f}" class="gl"/>'
                   f'<text x="{Lm - 4}" y="{y + 3:.1f}" text-anchor="end" class="ax">{esc(tk["label"])}</text>')
    for tk in ch["x_ticks"]:
        svg.append(f'<text x="{xs(tk["value"]):.1f}" y="{H - B + 12}" text-anchor="middle" class="ax">{esc(tk["label"])}</text>')
    svg.append(f'<text x="{(Lm + W - Rm) / 2:.1f}" y="{H - 3}" text-anchor="middle" class="ax">{esc(ch["x_title"])}</text>')
    wsweet = layout.text_width(ch["sweet"], 8.5)
    boxes = [(xs(99) - wsweet, ys(y1) + 2, xs(99), ys(y1) + 12)]
    pts = []
    for p in ch["points"]:
        x, a, b = xs(p["score"]), ys(p["net"]), ys(p["down"])
        boxes.append((x - 6, min(a, b) - 6, x + 6, max(a, b) + 6))
        pts.append((p, x, a, b))
    marks = []
    for p, x, a, b in pts:
        c = f'var(--{ACTION_COLOR.get(p["action"], "caution")}-base)'
        ink = c.replace("-base)", "-strong)")  # DS-4: the base colors are for marks, never text
        tx, ty, anchor = place_label(p["label"], x, a, b, 11, boxes, Lm, W - Rm, T, H - B)
        legend.mark("offered", ch["legend"]["offered"], "ring", "var(--grey)")
        legend.mark("down", ch["legend"]["down"], "dot", "var(--grey)")
        marks.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{a:.1f}" y2="{b:.1f}" stroke="{c}" stroke-width="2" opacity=".5"/>'
                     f'<circle cx="{x:.1f}" cy="{a:.1f}" r="5" fill="#fff" stroke="{c}" stroke-width="2"/>'
                     f'<circle cx="{x:.1f}" cy="{b:.1f}" r="5" fill="{c}"/>'
                     f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}" class="pl" style="fill:{ink}">{esc(p["label"])}</text>')
    lx, ly, anchor = target_label_spot(ch["target_label"], ys(tgt), Lm + 3, W - Rm - 3, boxes)  # OFR-296
    svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{ys(tgt):.1f}" y2="{ys(tgt):.1f}" stroke="var(--good-base)" stroke-dasharray="4 3"/>'
               f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" class="ax" style="fill:var(--good-strong)">'
               f'{esc(ch["target_label"])}</text>')
    svg += marks + ["</svg>"]
    keys = ('<div class="legend okey">' + "".join(f'<span><b>{esc(k["key"])}</b> {esc(k["label"])}</span>' for k in ch["keys"])
            + "</div>")
    return (f'<div class="chartbox">' + layout.chart_frame("".join(svg), legend.legend() + keys, title=ch["h"]) + "</div>")


def key_terms_table(kt):
    STATUS = {"good": "good", "caution": "caution", "risk": "risk"}
    cols = [Col("offer", kt["offer"], cls="ktoffer")] + [Col(i, h, cls="ktc") for i, h in enumerate(kt["head"])]
    if kt["escalation"]:
        cols.append(Col("esc", kt["escalation"], cls="ktc"))
    cols.append(Col("risk", kt["risk"], cls="sm2 ktrisk"))
    rows = []
    for r in kt["rows"]:
        out = {"offer": Raw(f'<b>{esc(r["key"])}</b> · <b>{esc(r["label"])}</b>')}
        for i, c in enumerate(r["cells"]):
            word = f' <span class="sm">({esc(c["word"])})</span>' if c["word"] else ""
            st = STATUS.get(c["status"], "")
            out[i] = Raw(f'<span class="stc {st}">{esc(c["text"])}{word}</span>')
        if r["escalation"] is not None:
            out["esc"] = Raw("<br>".join(esc(p) for p in r["escalation"]))
        out["risk"] = (Raw(f'{pill(r["risk"]["sev"])} {esc(r["risk"]["issue"])}') if r["risk"] else kt["risk_none"])
        rows.append(out)
    return (f'<h2>{esc(kt["h"])} <span class="h2s">{esc(kt["sub"])}</span></h2>'
            + layout.table(cols, rows, keep="brk", cls="kt") + f'<div class="legend"><span>{esc(kt["note"])}</span></div>')


def multi_body(M, agent):
    v, d = M["summary"], M["doc"]
    lower = options_table(v["options"], short=True)
    if d["chart"]:
        lower = f'<div class="two lower"><div>{lower}</div>{scatter(d["chart"])}</div>'
    page1 = f"{hero(v)}{plan_box(v, d)}{lower}{closing_block(v, d['follow'])}"
    ctr = ""
    c = d["counter"]
    if c:
        cols = [Col("term", c["cols"][0]), Col("offered", c["cols"][1], cls="was2"), Col("counter", c["cols"][2], cls="now2"),
                Col("why", c["cols"][3])]
        rows = [{**r, "counter": Raw(f"<b>{esc(r['counter'])}</b>")} for r in c["rows"]]
        ctr = (f'<h2>{esc(c["h"])} <span class="h2s">{esc(c["sub"])}</span></h2>'
               + layout.table(cols, rows, keep="whole", cls="mctr", row_classes={i: "oneline" for i, r in enumerate(c["rows"]) if r["oneline"]})
               + (f'<p class="sm">{esc(c["note"])}</p>' if c.get("note") else ""))
    details = (f'<div class="dh pb">{esc(d["dh"])}</div>' + facts(M) + '<div class="treason-slot"></div><div class="chart-slot"></div><div class="opts-slot"></div><div class="datanote-slot"></div>'
               + key_terms_table(d["key_terms"]) + ctr + confirm_table(d) + closing_notes(M, agent))
    return f'<div class="p1">{page1}</div>' + details


# --- document ------------------------------------------------------------------

def build_html(M, agent, sample=False):
    """The report's HTML from one document model (review.result)."""
    multi = M["mode"] == "multi"
    body = multi_body(M, agent) if multi else single_body(M, agent)
    theme = design.theme(agent.get("brand"), "seller")
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    if multi:
        css += "@page{size:Letter landscape}"  # the comparison is two wide tables; after report.css's portrait rule
    return render.page(header(M, agent, sample) + body, css=css, title=M["doc"]["title"], theme_css=design.css_vars(theme),
                       body_class="font-bundled" + (" wide" if multi else ""))


def file_name(M):
    return render.filename(M["doc"]["street"], M["doc"]["file_title"], ext="pdf")


def write_pdf(M, agent, sample, out_dir):
    path = os.path.join(out_dir, file_name(M))
    info = layout.print_pdf(build_html(M, agent, sample), path, fit(M["mode"] == "multi"),
                            footer_html=render.footer(M["doc"]["footer"]))
    for line in info["checks"]:
        print(line, file=sys.stderr)
    return path


def compute_model(data, ctx):
    """render.main's compute step: every document this run prints, once."""
    return review.compute(data, ctx)


def build(C, fmt_, out_dir, ctx):
    """A single review; or with 2+ active offers, the comparison plus a single review of each active offer, in rank
    order (OFR-318)."""
    sample = bool(ctx.get("sample") or C["sample"])
    paths = [write_pdf(M, ctx["agent"], sample, out_dir) for M in C["reports"]]
    for line in C["agent_lines"]:
        print(line, file=sys.stderr)
    return paths


def options(ap):
    ap.add_argument("--cma", help="cma-handoff v1 file (.cma.json or markdown with the block)")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single review while others are active")


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, extra_args=options, compute=compute_model,
                       errors=(oe.OfferError, handoff.HandoffError), labels=("offers[].label",), linked=handoff.linked)


if __name__ == "__main__":
    main(sys.argv[1:])
