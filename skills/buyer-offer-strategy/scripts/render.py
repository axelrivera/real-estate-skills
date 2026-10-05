"""Buyer offer PDFs: the Offer Options report (for the buyer) and the Offer Package Worksheet (for the agent).

    python3 scripts/render.py buyer.json [--format options|worksheet|all] [--cma file.cma.json] [--option recommended|stronger|lower_cost]
                              [--profile profile.md] [--sample] [--out DIR]

strategy.py builds the document model once (render.main's compute step): every figure, label and note is already in
it. This file only places it with the shared layout kit. Options report, page 1: the recommended offer with a reason
for every term, the key numbers, the alternatives, the outlook at four competition levels and the buyer's cash
exposure; the pages after it hold the detail, the assumptions and the notes. Worksheet: contract entries, riders with
suggested inputs, draft additional terms and the package checklist for the chosen option; it prints offer terms only,
never the buyer's max, cash or reserve. Colors follow the agent's buyer-side brand color.
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as ST  # noqa: E402
from _shared import design, fmt, handoff, layout, offer_engine as oe, render  # noqa: E402

Raw, Col = layout.Raw, layout.Col
L_ = ST.L_
HERE = os.path.dirname(os.path.abspath(__file__))
CSS = {"options": os.path.join(HERE, "..", "assets", "offer-options.css"),
       "worksheet": os.path.join(HERE, "..", "assets", "worksheet.css")}
BAND_TEXT = {"hi": "hit", "mid": "midt", "lo": "lot"}
STATUS_TEXT = {"risk": "rt", "caution": "ct", "": ""}

# page 1's blocks that grow with the data, named in the overflow warning (the tallest ones first)
PAGE1_BLOCKS = ((".p1 .hero", "the recommendation and its side panel"), (".p1 .ctr", "the recommended terms and reasons"),
                (".p1 .opts", "the options table"), (".p1 .absent", "the missing-option lines"),
                (".p1 .two", "the outlook and exposure row"), (".p1 .limit", "the Limit lines"),
                (".p1 .prelim", "the Preliminary line"))
# Page 1 fits by these steps, in order, until it fits: the compact layout; the outlook and exposure row to the top of
# page 2 (the options table above it keeps each option's outlook and cash); a tighter layout.
STEPS = ("compact",
         "() => { const t = document.querySelector('.p1 .two'), s = document.querySelector('.two-slot');"
         " if (t && s) s.appendChild(t); }",
         "tight")
OPTIONS_FIT = layout.Fit(end=".dh", steps=STEPS, tail=("tail",), blocks=PAGE1_BLOCKS,
                         tail_hint="the assumptions and notes")
WORKSHEET_FIT = layout.Fit(end=None, tail=("dense",), tail_hint="the checklist and the documents to request")


def esc(text):
    """Escaped text; a minus sign stays joined to its figure."""
    return html.escape(str(text)).replace("−$", "−⁠$")


def md(text):
    """Escape, then **bold** -> <b> and [blank] -> red fill-in."""
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text or ""))
    return Raw(re.sub(r"\[([^\]]+)\]", r'<span class="fill">[\1]</span>', out))


def css(kind):
    with open(CSS[kind], encoding="utf-8") as f:
        return f.read()


def prepared(lead, M, agent, who=True):
    lines = [Raw(f'{esc(lead)} ' + (f'<b>{esc(M["prepared_for"])}</b> · ' if who else "")
                 + f'<span class="nw">{esc(M["date"])}</span>')]
    if agent.get("name"):
        lines.append(Raw(f'<b>{esc(agent["name"])}</b>'))
        org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {agent["license"]}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return lines


def pill(cls, text):
    return Raw(f'<span class="pill b-{esc(cls)}">{esc(text)}</span>')


def h2(title, sub=""):
    return f'<h2>{esc(title)}' + (f' <span class="h2s">{esc(sub)}</span>' if sub else "") + "</h2>"


def sec(head, body, whole=True):
    """A section: its heading kept with what follows, and (whole) the section kept on one page."""
    return f'<section class="sec{" whole" if whole else ""}">{head}{body}</section>'


# --- Offer Options report --------------------------------------------------------

def snapshot(M):
    """Home facts in a divider row, then the market and deadline strip: one value per cell."""
    sn = M["snapshot"]
    row = layout.fact_row(sn["facts"]) if sn["facts"] else ""
    if not sn["cells"]:
        return row
    cols = " ".join("1.6fr" if c["label"] == L_["snap_due"] else "1fr" for c in sn["cells"])
    return (row + f'<div class="snap" style="grid-template-columns:{cols}">'
            + "".join(f'<div><span>{esc(c["label"])}</span><b>{esc(c["value"])}</b></div>' for c in sn["cells"]) + "</div>")


def hero(s):
    side = "".join(f"<dt>{esc(L_[k])}</dt><dd>{esc(v)}</dd>" for k, v in
                   (("k_competition", s["signal"]), ("k_financing", s["financing"]), ("k_limits", s["limits"])))
    why = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(s["why"]))
    return (f'<div class="hero"><div class="hl"><span class="k">{esc(s["kicker"])}</span>'
            f'<div class="big2">{esc(s["outlook"].upper())}</div><div class="why">{why}</div></div>'
            f'<div class="hr"><span class="k">{esc(L_["k_submit_by"])}</span><b>{esc(s["submit_by"])}</b><dl>{side}</dl></div></div>')


def tiles(s):
    items = [(x["label"], x["value"], x["sub"], "t-" + (x.get("status") or "plain")) for x in s["tiles"]]
    return layout.tiles(items, n=4, cls="p1tiles")


def terms_box(s):
    cols = [Col("term", L_["th_term"], cls="term"), Col("offer", L_["th_offer"], cls="val"), Col("why", L_["th_why"], cls="why2")]
    agent = f' <span class="pill vyes">{esc(L_["lbl_agent"])}</span>'
    rows = [{"term": Raw(f'<b>{esc(x["term"])}</b>'),
             "offer": Raw(esc(x["offer"]) + (f'<small>{esc(s["price_note"])}</small>' if x["key"] == "price" else "")),
             "why": Raw(esc(x["why"]) + (agent if x["agent"] else ""))} for x in s["terms"]]
    return (f'<div class="ctr"><div class="ctrh"><span>{esc(L_["h_offer_box"])}</span></div>'
            + layout.table(cols, rows, keep="whole", cls="ctrt") + "</div>")


def options_table(s):
    cols = [Col("option", L_["th_option"], cls="opt"), Col("price", L_["th_price"], align="num"),
            Col("outlook", L_["th_outlook"], cls="c"), Col("net", L_["th_seller_net"], align="num"),
            Col("worst", L_["th_worst"], align="num"), Col("reserve", L_["th_reserve"], align="num"),
            Col("what", L_["th_what_changes"], cls="what")]
    rows = [{"option": Raw(f'<b>{esc(x["option"])}</b>'), "price": x["price"], "outlook": pill(x["outlook_class"], x["outlook"]),
             "net": x["seller_net"], "worst": x["worst_cash"], "reserve": x["reserve"], "what": x["what"]} for x in s["options"]]
    classes = {i: " ".join(c for c in ("recrow" if x["key"] == "recommended" else "", f'st-{x["status"]}' if x["status"] else "") if c)
               for i, x in enumerate(s["options"])}
    absent = "".join(f'<div class="absent"><b>{esc(a["label"])}</b> {esc(a["why"])}</div>' for a in s["absent"])
    if s.get("higher_price"):  # what a higher price inside the buyer's limits would do to the outlook
        absent += f'<div class="absent"><b>{esc(L_["hp_label"])}</b> {esc(s["higher_price"])}</div>'
    return (h2(s["options_title"], s["options_sub"]) + layout.table(cols, rows, keep="whole", cls="opts", row_classes=classes)
            + absent)


def stack_and_exposure(s):
    cols = [Col("level", L_["th_if_seller_has"], cls="lvl")] + [Col(i, lab, cls="c") for i, lab in enumerate(s["option_labels"])]
    rows = [{"level": Raw(f'<b>{esc(b["level"])}</b>') if b["expected"] else b["level"],
             **{i: pill(v["class"], v["band"]) for i, v in enumerate(b["values"])}} for b in s["bands"]]
    stack = (h2(L_["h_stack"], L_["h_stack_sub"]) + layout.table(cols, rows, keep="whole", cls="bandt")
             + f'<div class="legend"><span>{esc(L_["lg_bands"])}</span></div>')
    ex = layout.table([Col("label", "", cls="exl"), Col("value", "", align="num", wrap="wrap", cls="exv")],
                      [{"label": e["label"], "value": Raw(f"<b>{esc(e['value'])}</b>")} for e in s["exposure"]],
                      keep="whole", cls="exp", head=False)
    return f'<div class="two"><div>{stack}</div><div>{h2(L_["h_exposure"], L_["h_exposure_sub"])}{ex}</div></div>'


def page1(M):
    s = M["summary"]
    limits = "".join(f'<div class="limit"><b>{esc(L_["lbl_limit"])}</b> {esc(c)}</div>' for c in s["constraints"])
    limits += "".join(f'<div class="cnote">{esc(c)}</div>' for c in s["cautions"])  # OFR-338: inside the limits
    pre = f'<div class="prelim">{md(s["preliminary"])}</div>' if s["preliminary"] else ""
    return (hero(s) + tiles(s) + terms_box(s) + options_table(s) + stack_and_exposure(s) + limits + pre
            + f'<div class="nextstep"><b>{esc(L_["lbl_next_step"])}</b> {esc(s["next_step"])}</div>'
            + f'<div class="fine">{esc(L_["fine_p1"])}</div>')


def money_cells(cells, cls_of=None):
    out = {}
    for i, c in enumerate(cells):
        cls = cls_of(c) if cls_of else ""
        out[i] = Raw(f'<span class="{cls}">{esc(c["text"])}</span>') if cls else c["text"]
    return out


def side_table(d, labels):
    one = d["one_option"]
    cols = [Col("term", L_["th_term"], cls="term")] + [Col(i, lab) for i, lab in enumerate(labels)]
    rows = []
    for r in d["side_by_side"]:
        row = {"term": r["term"]}
        for i, v in enumerate(r["values"]):
            row[i] = Raw(f'<span class="dif">{esc(v)}</span>') if r["differs"][i] else v
        rows.append(row)
    title = h2(L_["h_side_one"]) if one else h2(L_["h_side"], L_["h_side_sub"])
    return sec(title, layout.table(cols, rows, keep="whole", cls="side"))


def net_table(ns):
    cols = [Col("label", L_["th_line_item"], cls="lbl")] + [Col(i, c, align="num") for i, c in enumerate(ns["columns"])]
    neg = lambda c: "neg" if (c["amount"] or 0) < 0 else ""  # noqa: E731
    rows = [{"label": r["label"], **money_cells(r["cells"], neg)} for r in ns["rows"]]
    rows += [{"label": ns[k]["label"], **money_cells(ns[k]["cells"])} for k in ("net", "holding", "net_adj", "downside")]
    n = len(ns["rows"])
    return sec(h2(L_["h_net"], L_["h_net_sub"]),
               layout.table(cols, rows, keep="whole", cls="netsheet", row_classes={n: "total", n + 2: "total2", n + 3: "alt"}))


def score_table(sc, labels):
    cols = ([Col("label", L_["th_criterion"], cls="crit2"), Col("weight", L_["th_weight"], align="num")]
            + [Col(i, lab, cls="c sc") for i, lab in enumerate(labels)] + [Col("why", L_["th_rec_why"], cls="sm")])
    rows = [{"label": r["label"], "weight": r["weight"], "why": r["why"],
             **{i: fmt.EMPTY if v is None else Raw(f'<span class="s{v}">{v}</span>') for i, v in enumerate(r["scores"])}}
            for r in sc["rows"]]
    tt = sc["total"]
    total = {"label": tt["label"], "weight": tt["weight"],
             **{i: Raw(f'<b class="{BAND_TEXT.get(b, "")}">{v}</b>') for i, (v, b) in enumerate(zip(tt["scores"], tt["bands"]))}}
    return sec(h2(L_["h_scorecard"], L_["h_scorecard_sub"]), layout.table(cols, rows, total=total, keep="whole", cls="score"))


def cash_table(ct):
    cols = [Col("label", L_["th_item"], cls="lbl")] + [Col(i, c, align="num") for i, c in enumerate(ct["columns"])]
    rows = [{"label": r["label"], **money_cells(r["cells"])} for r in ct["rows"]]
    classes = {}
    for k in ("to_close", "gap", "worst"):
        if k != "gap":
            classes[len(rows)] = "total"
        rows.append({"label": ct[k]["label"], **money_cells(ct[k]["cells"])})
    classes[len(rows)] = "total2"
    rows.append({"label": ct["reserve"]["label"],
                 **money_cells(ct["reserve"]["cells"], lambda c: STATUS_TEXT.get(c.get("status") or "", ""))})
    for k in ("risk_after", "protection"):
        if k in ct:
            rows.append({"label": ct[k]["label"], **{i: Raw(f'<span class="wrapc">{esc(c)}</span>') for i, c in enumerate(ct[k]["cells"])}})
    return sec(h2(L_["h_cash"]), layout.table(cols, rows, keep="whole", cls="cash", row_classes=classes))


def market_table(mc):
    cols = [Col("label", "", cls="mlbl"), Col("value", "")]
    rows = [{"label": m["label"], "value": Raw(f"<b>{esc(m['value'])}</b>" + (f"<small>{esc(m['note'])}</small>" if m["note"] else ""))}
            for m in mc]
    return sec(h2(L_["h_market"]), layout.table(cols, rows, keep="whole", cls="mkt", head=False))


def pushback_table(d):
    cols = [Col("term", L_["th_term"], cls="pterm"), Col("yours", L_["th_yours"], cls="pval"), Col("ask", L_["th_ask"], cls="pval ask"),
            Col("response", L_["th_response"])]
    rows = [{**p, "response": Raw(f'<span class="{"hold" if p["breaks"] else ""}">{esc(p["response"])}</span>')}
            for p in d["pushback"]] or [{"term": d["pushback_none"]}]
    return sec(h2(L_["h_pushback"], L_["h_pushback_sub"]), layout.table(cols, rows, keep="whole", cls="pbk"))


def confirm_table(M):
    if not M["assumptions"]:
        return sec(h2(L_["h_confirm"]), f'<p class="sm">{esc(L_["confirm_none"])}</p>')
    cols = [Col("impact", L_["th_impact"], cls="c imp"), Col("where", L_["th_where"], cls="where"), Col("what", L_["th_what"])]
    rows = [{"impact": Raw(f'<span class="pill {a["impact"]}">{esc(a["impact_label"])}</span>'), "where": a["where"],
             "what": a["what"]} for a in M["assumptions"]]
    return sec(h2(L_["h_confirm"]), layout.table(cols, rows, keep="brk", cls="confirm"), whole=False)


def details(M, agent):
    d, labels = M["detail"], M["summary"]["option_labels"]
    return (f'<div class="dh pb">{esc(L_["dh_options"])}</div><div class="two-slot"></div><div class="det">'
            + side_table(d, labels) + net_table(d["net_sheet"]) + score_table(d["scorecard"], labels) + cash_table(d["cash"])
            + f'<div class="two det2"><div>{market_table(d["market_check"])}</div><div>{pushback_table(d)}</div></div>'
            + confirm_table(M) + layout.notes_block(M["notes"], title=L_["h_notes"]) + "</div>" + render.notices(agent))


def options_html(M, agent, sample=False):
    sub = ST.t("sub_options", address=M["property"], price=M["list_price"], financing=M["financing_label"])
    head = layout.header(L_["doc_options"], sub, prepared(L_["prepared_for"], M, agent), tag=L_["tag"], sample=sample)
    body = head + snapshot(M) + f'<div class="p1">{page1(M)}</div>' + details(M, agent)
    theme = design.theme(agent.get("brand"), "buyer")
    return render.page(body, css=css("options"), title=L_["doc_options"], theme_css=design.css_vars(theme), body_class="font-bundled")


# --- Offer Package Worksheet -----------------------------------------------------

def worksheet_html(M, agent, sample=False):
    W = M["worksheet"]
    cols = [Col("para", L_["th_para"], cls="c para"), Col("field", L_["th_field"], cls="fld"), Col("entry", L_["th_enter"], cls="ent"),
            Col("note", L_["th_note"], cls="src")] if W["farbar"] else \
        [Col("field", L_["th_field"], cls="fld"), Col("entry", L_["th_enter"], cls="ent"), Col("note", L_["th_note"], cls="src")]
    rows = [{**x, "entry": md(x["entry"])} for x in W["rows"]]
    rcols = [Col("rider", L_["th_rider"], cls="rider"), Col("inputs", L_["th_inputs"], cls="inputs"), Col("why", L_["th_why"], cls="src")]
    riders = [{"rider": Raw(f'<b>{esc(x["rider"])}</b>'), "inputs": md(x["inputs"]), "why": x["why"]} for x in W["riders"]] \
        or [{"rider": L_["no_riders"]}]
    clauses = "".join(f'<div class="clause"><b class="t">{esc(x["title"])}</b>{esc(x["text"])}</div>' for x in W["clauses"])
    done = ("yes", "done", "true", "✓")

    def box(status):  # OFR-206: "Never" (a thing to leave out) is a cross, never a tick
        if str(status).lower() == "never":
            return Raw('<b class="never">✕</b>')
        return Raw(f'<span class="cb{" on" if str(status).lower() in done else ""}"></span>')
    pcols = [Col("box", L_["th_check"], cls="c cbc"), Col("group", L_["th_group"], cls="src grp"), Col("item", L_["th_item"], cls="item"),
             Col("date", L_["th_date"], cls="write"), Col("notes", L_["th_notes"], cls="write")]
    pk = [{"box": box(x["status"]), "group": x["group"],
           "item": Raw(esc(x["item"]) + (f'<span class="hint">{esc(x["note"])}</span>' if x["note"] else ""))} for x in W["package"]]
    boxes = [Raw(f'<span class="cb"></span> {esc(d)}') for d in W["docs"]]
    half = (len(boxes) + 1) // 2  # two columns, read down the first, then the second
    docs = layout.table([Col(0, ""), Col(1, "")], [[boxes[i], boxes[i + half] if i + half < len(boxes) else ""]
                                                   for i in range(half)], keep="whole", cls="docs", head=False)
    draft = ST.t("ws_draft_farbar" if W["farbar"] else "ws_draft_other", software=W["software"])
    sub = ST.t("sub_worksheet", address=M["property"], financing=M["financing_label"], price=W["price"], option=W["option"].lower())
    body = (layout.header(L_["doc_worksheet"], sub, prepared(L_["draft_prepared"], M, agent, who=False), tag=L_["tag"], sample=sample)
            + f'<div class="draftbar"><b>{esc(L_["ws_draft"])}</b> {esc(draft)}</div>'
            + f'<div class="goal"><b>{esc(L_["lbl_contract_form"])}</b> {esc(W["form_name"])}. {esc(W["form_why"])}</div>'
            + sec(h2(L_["h_entries"]), layout.table(cols, rows, keep="brk", cls="ws entries"), whole=False)
            + sec(h2(L_["h_riders"], L_["h_riders_sub"]), layout.table(rcols, riders, keep="brk", cls="ws riders"), whole=False)
            + sec(h2(L_["h_terms"], L_["h_terms_sub"]), clauses, whole=False)
            + sec(h2(L_["h_checklist"]), layout.table(pcols, pk, keep="brk", cls="ws pk"), whole=False)
            + sec(h2(L_["h_request"]), docs)
            + f'<div class="fine">{esc(ST.t("ws_fine", farbar=L_["ws_fine_farbar"] if W["farbar"] else ""))}</div>'
            + render.notices(agent))
    theme = design.theme(agent.get("brand"), "buyer")
    return render.page(body, css=css("worksheet"), title=L_["doc_worksheet"], theme_css=design.css_vars(theme),
                       body_class="font-bundled")


# --- files -----------------------------------------------------------------------

def write_options(M, agent, sample, out_dir):
    path = os.path.join(out_dir, render.filename(M["street"], L_["file_options"], ext="pdf"))
    footer = ST.t("footer_options", name=M["prepared_for"] if M["prepared_for"] != L_["buyer_word"] else L_["footer_buyer"],
                  street=M["street"])  # OFR-32
    info = layout.print_pdf(options_html(M, agent, sample), path, OPTIONS_FIT, footer_html=render.footer(footer))
    for line in info["checks"]:
        print(line, file=sys.stderr)
    return path


def write_worksheet(M, agent, sample, out_dir):
    W = M["worksheet"]
    path = os.path.join(out_dir, render.filename(M["street"], L_["file_worksheet"], ext="pdf"))
    info = layout.print_pdf(worksheet_html(M, agent, sample), path, WORKSHEET_FIT,
                            footer_html=render.footer(ST.t("footer_worksheet", street=M["street"])))
    for line in info["checks"]:
        print(line, file=sys.stderr)
    print(f"Worksheet ({W['option'].lower()} offer): {len(W['riders'])} rider(s), {len(W['clauses'])} clause draft(s), "
          f"{W['blanks']} blank(s) to fill", file=sys.stderr)
    return path


def build(C, fmt, out_dir, ctx):
    M = C["model"]
    sample = bool(ctx.get("sample") or C["sample"])
    path = (write_options if fmt == "options" else write_worksheet)(M, ctx["agent"], sample, out_dir)
    if not ctx.get("chat_noted"):  # OFR-203: once per run, not once per file
        ctx["chat_noted"] = True
        for line in C["agent_lines"]:
            print(line, file=sys.stderr)
        if profile_check(ctx["agent"]):  # the same reminder the CMA renders print
            print(f"Check: {profile_check(ctx['agent'])}", file=sys.stderr)
    return [path]


def profile_check(agent):
    """A chat reminder when the agent's name or brokerage is missing, or None. Never printed in the PDFs: they simply
    leave the missing parts out."""
    gaps = [w for w, f in (("agent name", "name"), ("brokerage", "brokerage")) if not agent.get(f)]
    if not gaps:
        return None
    return (f"{'no profile' if len(gaps) == 2 else 'profile incomplete'}: {' and '.join(gaps)} missing, so the PDFs "
            "carry none. Ask the agent for them (or use their saved profile with --profile) and render again.")


def options(ap):
    ap.add_argument("--cma", help="cma-handoff v1 file (.cma.json or markdown with the block)")
    ap.add_argument("--option", choices=list(ST.OPTIONS), help="option for the worksheet (default: the file's chosen_option)")


def main(argv=None):
    return render.main(build, formats=("options", "worksheet"), argv=argv, extra_args=options, compute=ST.compute,
                       errors=(oe.OfferError, handoff.HandoffError, ST.notes.NotesError), agent_only=("worksheet",), linked=handoff.linked)


if __name__ == "__main__":
    main(sys.argv[1:])
