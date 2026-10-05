"""Seller CMA files: the report PDF (page 1 summary, then the full analysis) and the listing presentation PPTX
(with a PDF copy of the slides when LibreOffice is available).

    python3 scripts/render.py report.json [--format pdf|pptx|all] [--profile profile.md] [--sample] [--out DIR]

compute.py builds the document model once (render.main's compute step); this file only places it with the shared
layout kit (the header, tiles, the comps dot plot and the scatter with its legend built from the series drawn, the
tables, the one notes block), and deck.py lays the same model out as slides. Every figure and sentence either prints
comes from the model. Prints the paths written, then layout notes and the warnings to fix on stderr.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
import deck  # noqa: E402
from _shared import cma, design, fmt, layout, render  # noqa: E402

ASSETS = compute.ASSETS
L, t = compute.L, compute.t
Raw, Col = layout.Raw, layout.Col
esc = html.escape
# Page 1 fits itself (PAGINATE_JS's .onepage steps); the later pages keep each heading with its figure and let long
# tables run on. CMA margins (cma.PAGE_MARGINS).
FIT = layout.Fit(end=None, paginate=True, margins=cma.PAGE_MARGINS, tail_hint=L["tail_hint"])
SCATTER_SHRINK = 0.4  # the scatter may shrink by up to this share of its height to finish a page


def raw(text):
    """Model text (judgment, with <strong> and <em> allowed), placed as written."""
    return Raw(text or "")


def ul(items, cls="plain"):
    return f'<ul class="{cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>" if items else ""


def p(text, cls=""):
    return f'<p class="{cls}">{text}</p>' if cls else f"<p>{text}</p>"


def agent_block(agent):
    """Wordmark (left) with only the fields the profile has."""
    name = agent.get("name")
    if not name:
        return ""
    org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
    return f'<div class="wm-name">{esc(name)}</div><div class="wm-sub">{esc(org or L["wordmark_sub"])}</div>'


def footer_block(agent, C):
    if not agent.get("name"):
        return f'<footer>{esc(L["prepared"])} {esc(C["prepared_date"])}</footer>'
    lines = [f'<b>{esc(agent["name"])}</b>' + "".join(
        f" · {esc(str(agent[f]))}" for f in ("team", "brokerage") if agent.get(f)) +
        (f' · {esc(L["lic"])} {esc(str(agent["license"]))}' if agent.get("license") else "")]
    contact = " · ".join(esc(str(agent[f])) for f in ("phone", "email", "website") if agent.get(f))
    if contact:
        lines.append(contact)
    lines.append(f'{esc(L["prepared"])} {esc(C["prepared_date"])}')
    return "<footer>" + "<br>".join(lines) + "</footer>"


# --- page 1 -----------------------------------------------------------------------------------------------------------

def page_one(C, agent):
    sm, s, rec = C["summary"], C["subject"], C["recommendation"]
    history = C["price_history"] or (C["history_line"] and t("line_history", text=C["history_line"]))
    tag = f'<span class="tag prelim">{esc(L["preliminary"])}</span><br>' if C["preliminary"] else ""
    o = ['<div class="onepage">',
         f'<header class="top"><div>{agent_block(agent)}</div><div class="prep">{tag}'
         f'{esc(sm["label"])}<br>{esc(L["prepared"])} {esc(C["prepared_date"])}</div></header>',
         cma.subject_heading({"address": s["address"], "locality": s["locality"],
                              "summary_facts": " · ".join(s["summary_facts"])}),
         '<div class="sp-hero"><div class="sp-rec">'
         f'<div class="lbl">{esc(sm["rec_label"])}</div><div class="price">{esc(rec["list_price_display"])}</div>'
         f'<div class="line">{esc(L["sum_range_line"])} <b>{esc(rec["range_display"])}</b></div>'
         f'<div class="line">{esc(L["sum_expected"])} <b>{esc(rec["expected_sale_display"])}</b></div>'
         + (f'<div class="line hist">{esc(history)}</div>' if history else "")
         + (f'<div class="line headline">{sm["headline"]}</div>' if sm["headline"] else "") + "</div>"
         '<div class="sp-stats">' + "".join(layout.tiles([(lbl, v) for v, lbl in sm["tiles"][i:i + 2]], n=2, cls="sp-tiles")
                                            for i in (0, 2)) + "</div></div>",
         f'<div class="sp-h">{esc(L["sum_comps_h"])} <span class="sp-sub">· {esc(L["sum_shaded"])}</span></div>',
         '<div class="sp-dot">' + cma.dotplot(sm["comps"], rec["low"], rec["high"], rec["list_price"], sm["dot_label"],
                                             kfmt=fmt.k) + "</div>"]
    opts = C["options_summary"]
    ri = C["recommended_index"]
    rows = [[x["label"] + (" ★" if x["recommended"] else ""), x["time"], x["expected_sale_display"],
             x["net_after_holding_display"]] for x in C["strategies"]]
    table = layout.table([Col(0, L["th_list_at"], wrap="nowrap"), Col(1, L["th_time_short"]),
                          Col(2, L["th_expected"], align="num"), Col(3, opts["net_header"], align="num")],
                         rows, keep="whole", cls="sp-table", row_classes={ri: "rec"})
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{esc(L["sum_why"])}</div>{ul(sm["why"], "")}</div>'
             f'<div><div class="sp-h">{esc(L["sum_options"])}</div>{table}<div class="note">{esc(opts["note"])}</div></div></div>')
    if sm["first_steps"]:
        o.append(f'<div class="sp-h">{esc(sm["first_heading"])}</div><div class="sp-steps">' +
                 "".join(f'<div class="sp-step"><b>{esc(h)}</b>{d}</div>' for h, d in sm["first_steps"]) + "</div>")
    nxt = " ".join(x for x in (sm["next_step"], esc(sm["launch_line"])) if x)
    o.append(f'<div class="sp-next"><span><b>{esc(L["sum_next"])}</b> {nxt}</span></div>')
    note = L["line_details"] + (" " + t("sum_preliminary", reason=C["preliminary_reason"]) if C["preliminary"] else "")
    o.append(f'<div class="note details">{esc(note)}</div></div>')
    return "".join(o)


# --- the analysis -----------------------------------------------------------------------------------------------------

def home(C):
    s = C["subject"]
    out = [f'<h2>{esc(L["h_home"])}</h2>',
           '<div class="facts">' + "".join(f"<div><span>{esc(a)}</span><b>{esc(v)}</b></div>" for a, v in s["facts"]) + "</div>"]
    if s["summary"]:
        out.append(p(s["summary"]))
    return out


def bottom_line(C):
    rec = C["recommendation"]
    hist = [x for x in (C["price_history"], C["history_line"] and t("line_history", text=C["history_line"])) if x]
    body = " ".join([esc(rec["line"]), esc(C["stance"]["line"])] + [esc(h) for h in hist])
    out = [f'<h2>{esc(L["h_bottom"])}</h2>',
           f'<div class="verdict"><div class="range">{esc(rec["verdict"])}</div>'
           f'<div class="mid">{esc(rec["caption"])}</div><p>{body}</p>'
           + (f'<p class="why">{rec["why"]}</p>' if rec["why"] else "") + "</div>"]
    if C["means"]:
        out += [f'<h3>{esc(L["h_means"])}</h3>', ul(C["means"])]
    return out


def comps(C):
    c = C["comps"]
    intro = " ".join(x for x in (c["intro"], esc(c["count_line"])) if x)
    cards = [
        f'<div class="comp{" best" if cd["strongest"] else ""}"><div class="comp-h"><b>{esc(cd["address"])}</b>'
        f'<span class="adj">{esc(L["adjusted"])} {esc(cd["adjusted_display"])}</span></div>'
        + (f'<div class="best-tag">{esc(L["strongest_tag"])}</div>' if cd["strongest"] else "")
        + f'<div class="meta">{esc(" · ".join(cd["meta"]))}</div>'
        '<div class="adj-lines">' + "".join(f'<span><i>{esc(a)}</i> {esc(v)}</span>' for a, v in cd["lines"][1:]) + "</div>"
        + ul(cd["bullets"], "") + "</div>" for cd in c["cards"]]
    rows = c["table"] + [c["subject_row"]]
    method = " ".join(x for x in (esc(c["method"]), c["method_note"]) if x)
    summary = " ".join(esc(x) for x in (c["summary_line"], c["strongest"]["line"], c["highest_line"]))
    out = [f'<h2>{esc(L["h_compared"])}</h2>', p(intro), p(method, "note") if method else "",
           *[f'<div class="comps2">{"".join(cards[i:i + 2])}</div>' for i in range(0, len(cards), 2)],
           layout.table([Col(0, L["th_sale"]), Col(1, L["th_sold_for"], align="num"), Col(2, L["th_seller_paid"], align="num"),
                         Col(3, L["th_adjusted"], align="num")], rows, row_classes={len(rows) - 1: "subj"}, keep="whole"),
           p(summary + (" " + c["lean"] if c["lean"] else ""))]
    return [x for x in out if x]


def scatter(C, notes_out):
    sc = C["scatter"]
    if not sc:
        return []
    s, rec = C["subject"], C["recommendation"]
    chart = layout.Chart()
    svg, info = cma.scatter(C["_homes"], {**sc["ratios"], "callouts": sc["callouts"], "subject_label": sc["subject_label"],
                                          "subject_label_pos": sc["subject_label_pos"]},
                            s["sqft"], rec["list_price"], s["mls_address"], (rec["low"], rec["high"]),
                            compute.labeler(C["reprice_words"]), [cd["address"] for cd in C["comps"]["cards"]],
                            drop_crowded=True, points=C["_points"], chart=chart, band_label=sc["band_label"], kfmt=fmt.k)
    notes_out["scatter_labels"] = {"moved": info["labels_moved"], "overlapping": info["labels_overlapping"] + info["crowded_labels"],
                                   "leader": info["labels_leader"], "dropped": info["labels_dropped"]}
    notes_out["callout_checks"] = cma.callout_checks(info)
    notes_out["legend"] = chart.drawn()
    svg = svg.replace('class="scatter"', f'class="scatter" data-shrink="{SCATTER_SHRINK}"', 1)
    out = [f'<h3>{esc(sc["heading"])}</h3>', p(esc(sc["intro"])), layout.chart_frame(svg, chart.legend())]
    if sc["excluded"]:
        out.append(p(esc(sc["excluded"]), "note"))
    if sc["trend"]:
        tr = sc["trend"]
        cy = {"above": 10.5, "below": 22.5, "at": 16.5}[tr["side"]]
        icon = ('<svg class="cr-icon" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="16" class="cr-disc"/>'
                '<line x1="6" y1="21.5" x2="26" y2="11.5" class="cr-line"/>'
                f'<path d="M16,{cy - 4} L20,{cy} L16,{cy + 4} L12,{cy} Z" class="cr-subj"/></svg>')
        out.append(f'<div class="chart-read">{icon}<div><p class="cr-head">{esc(tr["head"])}</p>'
                   f'<p class="cr-body">{esc(tr["body"])}</p></div></div>')
    after = " ".join(x for x in (esc(sc["r2_line"]), sc["takeaway"]) if x)
    if after:
        out.append(p(after))
    return out


def competition(C):
    cp = C["competition"]
    if not cp["rows"]:
        return []
    cols = [Col(0, L["th_address"], min="10.5em"), Col(1, L["th_status"]), Col(2, L["th_price"], align="num"),
            Col(3, L["th_sqft"], align="num"), Col(4, L["th_pool"]), Col(5, L["th_days"], align="num"), Col(6, L["th_notes"])]
    out = [f'<h2>{esc(L["h_competition"])}</h2>']
    if cp["intro"]:
        out.append(p(cp["intro"]))
    out.append(layout.table(cols, [[*r[:6], raw(r[6])] for r in cp["rows"]]))
    return out


def market(C):
    m = C["market"]
    if not m:
        return []
    out = [f'<h2>{esc(L["h_market"])}</h2>']
    if m["intro"]:
        out.append(p(esc(m["intro"])))
    if m["rows"]:
        cols = [Col(0, m["columns"][0])] + [Col(i, label, align="num") for i, label in enumerate(m["columns"][1:], 1)]
        out.append(layout.table(cols, m["rows"]))
    out.append(ul(m["bullets"]))
    return [x for x in out if x]


def pricing(C, intro):
    opts, strats, net, rw = C["options_summary"], C["strategies"], C["net"], compute.labeler(C["reprice_words"])
    lead = " ".join(x for x in (intro, esc(opts["spread_line"])) if x)
    out = [f'<h2>{esc(rw("h_pricing"))}</h2>']
    if lead:
        out.append(p(lead))
    out.append(layout.table([Col(0, L["th_strategy"], wrap="nowrap"), Col(1, L["th_time"]),
                             Col(2, L["th_expected"], align="num"), Col(3, opts["net_header_long"], align="num"),
                             Col(4, L["th_expect"])],
                            [[x["label"], x["time"], x["expected_sale_display"], x["net_after_holding_display"], raw(x["note"])]
                             for x in strats], row_classes={C["recommended_index"]: "total"}))
    out.append(p(esc(opts["note"]) + (" " + C["pricing_note"] if C["pricing_note"] else ""), "note"))
    n = len(strats)
    cols = [Col(0, L["th_at_closing"])] + [Col(i, net["header"][i - 1], align="num") for i in range(1, n + 1)]
    rows = [[r["label"], *r["display"]] for r in net["rows"]]
    classes = {i: "total" for i, r in enumerate(net["rows"]) if r["kind"] == "total"}
    classes.update({i: "info" for i, r in enumerate(net["rows"]) if r["kind"] == "info"})
    out += [f'<h3>{esc(L["h_net"])}</h3>', p(esc(L["net_intro"])), layout.table(cols, rows, row_classes=classes)]
    return out


def payments(C):
    pay = C["payments"]
    if not pay:
        return []
    return [f'<h3>{esc(L["h_payments"])}</h3>',
            p(esc(pay["intro"])),
            layout.table([Col(0, L["th_list_price"], align="num"), Col(1, t("th_down", down=pay["down_display"]), align="num"),
                          Col(2, L["th_payment"], align="num")],
                         [[r["list_price_display"], r["down_display"], r["payment_display"]] for r in pay["rows"]],
                         row_classes={C["recommended_index"]: "total"})]


def prep(C):
    pr = C["prep"]
    out = [f'<h2>{esc(pr["heading"])}</h2>']
    if pr["intro"]:
        out.append(p(pr["intro"]))
    out.append(ul([f'<strong>{esc(it["step"].rstrip("."))}.</strong> {it["detail"]}' for it in pr["items"]], "plain watch"))
    if C["needs"]:
        out += [f'<h3>{esc(L["h_needs"])}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in C["needs"]) + "</ol>"]
    return out


def closing(C, agent):
    """How This Was Prepared, the footer and the closing notices kept together (CMA-276). The seller CMA is the listing
    presentation's leave-behind, a marketing piece: the Equal Housing Opportunity statement, as on the deck."""
    return ('<div class="kg sec runon">' + f'<h2>{esc(L["h_method"])}</h2>' + "".join(p(esc(x)) for x in C["method"]["lines"])
            + "<div>" + footer_block(agent, C) + render.notices(agent, C["notices"], marketing=True) + "</div></div>")


def build_html(C, agent, notes_out=None, intro=None):
    """The report's HTML from the document model. `notes_out` (a dict) receives the chart's label placement notes."""
    notes_out = {} if notes_out is None else notes_out
    with open(os.path.join(ASSETS, "seller-cma.css"), encoding="utf-8") as f:
        css = cma.css() + f.read()
    body = (home(C) + bottom_line(C) + comps(C) + scatter(C, notes_out) + competition(C) + market(C)
            + pricing(C, C["pricing_intro"]) + payments(C)
            + [layout.notes_block(C["notes"], title=L["h_notes"], cls="cma-notes")] + prep(C))
    content = ('<div class="wrap">' + page_one(C, agent) + '<div class="pb"></div>' + layout.group_blocks(body)
               + closing(C, agent) + "</div>")
    theme = design.theme(agent.get("brand"), "seller")  # the subject home is black (cma.css), never a second hue
    extra = ".prep .tag.prelim{color:var(--caution-strong);border-color:var(--caution-strong)}"
    doc = render.page(content, css=css, title=f'{L["doc_label"]}: {C["subject"]["address"]}',
                      theme_css=design.css_vars(theme) + extra, body_class="font-bundled scma")
    return doc.replace("<html>", '<html lang="en">', 1)


def footer_label(C, agent, doc_label, sample):
    label = " · ".join(x for x in (C["subject"]["address"], doc_label,
                                   ", ".join(str(agent[f]) for f in ("name", "brokerage") if agent.get(f))) if x)
    if C["preliminary"]:
        label = L["preliminary"].upper() + " · " + label
    if sample:
        label = "SAMPLE DATA · " + label
    return label


def profile_check(agent):
    """CMA-263: a chat reminder when the name or brokerage is missing, or None. Never printed in the files."""
    gaps = [w for w, f in (("agent name", "name"), ("brokerage", "brokerage")) if not agent.get(f)]
    if not gaps:
        return None
    return (f"{'no profile' if len(gaps) == 2 else 'profile incomplete'}: {' and '.join(gaps)} missing, so the files "
            "carry none. Ask the agent for them (or use their saved profile with --profile) and render again.")


def print_chart_notes(chart_notes):
    labels = chart_notes.get("scatter_labels") or {}
    for text, asked, used in labels.get("moved", []):
        where = f"still {used}" if used.split(",")[0] == asked else f"placed {used}, not {asked},"
        print(f"Chart label {text!r}: {where} to clear the markers (information).", file=sys.stderr)
    for text, side in labels.get("leader", []):
        print(f"Chart label {text!r}: no clear spot beside its point, so it sits farther off to the {side} with a thin "
              "line to it (information).", file=sys.stderr)
    for text in labels.get("dropped", []):
        print(f"Chart label {text!r} left off: no clear spot, and the legend names the home (information).", file=sys.stderr)
    for text in dict.fromkeys(labels.get("overlapping", [])):
        print(f"Check: chart label {text!r} still overlaps a marker or another label: drop that callout or pick another "
              "side.", file=sys.stderr)
    for c in chart_notes.get("callout_checks", []):
        print(f"Check: {c}", file=sys.stderr)


def compute_model(data, ctx):
    """render.main's compute step: the document model, once per run, with the checks every format needs."""
    C = compute.run(data, ctx.get("mls"), ctx.get("data_file"))
    if C.get("stage") != "full":
        raise compute.ReportError("report.json has only the comps: add pricing (its stance), costs and buyer_payment "
                                  "for the report.")
    if C["payments"] is None:
        raise compute.ReportError("Buyer payments need a property tax rate: " + "; ".join(C["warnings"]))
    if C["net"]["incomplete"]:
        raise compute.ReportError("The net sheet needs brokerage terms: ask the agent for the listing fee and the buyer's "
                                  "agent compensation (0 is fine) and put them in costs. Without them every net "
                                  "overstates the seller's proceeds.")
    agent = ctx["agent"]
    for w in C["warnings"]:
        print(f"Check: {w}", file=sys.stderr)
    if profile_check(agent):
        print(f"Check: {profile_check(agent)}", file=sys.stderr)
    return C


def build(C, fmt_, out_dir, ctx):
    agent, sample = ctx["agent"], bool(ctx.get("sample") or C.get("sample"))
    if fmt_ == "pdf":
        chart_notes = {}
        doc = build_html(C, agent, chart_notes)
        path = os.path.join(out_dir, render.filename(C["subject"]["address"], "Seller CMA", ext="pdf"))
        info = layout.print_pdf(doc, path, FIT, footer_html=render.footer(footer_label(C, agent, L["doc_label"], sample)))
        pg = info.get("paginate") or {}
        if pg.get("page1_px", 0) > FIT.content_px()[1]:
            print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
        elif pg.get("fit_level"):
            print(f"Page 1 ran long and was tightened (step {pg['fit_level']} of 3) to fit.", file=sys.stderr)
        for c in info["checks"]:
            print(f"Check: {c}", file=sys.stderr)
        print_chart_notes(chart_notes)
        return [path]
    path = os.path.join(out_dir, render.filename(C["subject"]["address"], "Listing Presentation", ext="pptx"))
    D = deck.deck_data(C, agent, footer_label(C, agent, "", sample))
    for c in deck.build_pptx(D, path):  # a DeckError keeps the PDF and names the problem (render.main)
        print(f"Check: {c}", file=sys.stderr)
    written = [path]
    pdf = deck.pptx_to_pdf(path, os.path.join(out_dir, render.filename(C["subject"]["address"], "Listing Presentation",
                                                                       ext="pdf")))
    if pdf:
        written.append(pdf)
    else:
        print("Check: the presentation PDF couldn't be made here (no LibreOffice); the PPTX is unaffected.", file=sys.stderr)
    return written


# Label fields the model types, put in Title Case before the build (shared/prose.py title_labels)
LABEL_FIELDS = ("**.heading", "summary_page.label", "comps.cards[].adjustments[].label", "subject.facts[][0]")


def deck_file(data, args):
    """For render.main(linked=...): the deck wording when report.json's `deck` names a file, so it gets the same wording
    check as report.json. A missing or broken file is left to deck.py, which says why."""
    if not isinstance(data.get("deck"), str):
        return []
    content = compute.deck_content(data, args.get("data"))
    return [("deck", content)] if content is not None else []


def main(argv=None):
    return render.main(build, formats=("pdf", "pptx"), argv=argv, default="pdf",  # the deck only when asked for
                       compute=compute_model, errors=(compute.ReportError, deck.DeckError, compute.mls.ExportError),
                       labels=LABEL_FIELDS, linked=deck_file)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyError as e:
        sys.exit(f"report.json is missing {e}")
