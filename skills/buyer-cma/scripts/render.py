"""Buyer CMA PDF: page 1 summary, then the full analysis in a fixed section order.

    python3 scripts/render.py report.json [--profile profile.md] [--sample] [--out DIR]

compute.py builds the document model once (render.main's compute step); this file only places it with the shared
layout kit: the header, tiles, the comps dot plot and the scatter (their legend built from the series drawn), the
tables, the notes block. Every figure and sentence it prints comes from the model. Prints the PDF path, then layout
notes and the warnings to fix on stderr.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import cma, design, fmt, layout, render  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
L, t = compute.L, compute.t
Raw, Col = layout.Raw, layout.Col
esc = html.escape
# Page 1 fits itself (PAGINATE_JS's .onepage steps); the later pages keep each heading with its figure and let long
# tables run on. CMA margins (cma.PAGE_MARGINS).
FIT = layout.Fit(end=None, paginate=True, margins=cma.PAGE_MARGINS, tail_hint=L["tail_hint"])


def raw(text):
    """Model text (judgment, with <strong> and <em> allowed), placed as written."""
    return Raw(text or "")


def ul(items, cls="plain"):
    return f'<ul class="{cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>" if items else ""


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


def flagged(value, flag):
    """A figure with its cash flag under it, when it's over the buyer's cash."""
    return Raw(esc(value) + (f'<br><span class="flag">{esc(flag)}</span>' if flag else "")) if flag else value


# --- page 1 -----------------------------------------------------------------------------------------------------------

def page_one(C, agent):
    sm, s, op, rng = C["summary"], C["subject"], C["offer_plan"], C["range"]
    o = ['<div class="onepage">',
         f'<header class="top"><div>{agent_block(agent)}</div><div class="prep">'
         f'{esc(sm["label"])}<br>{esc(L["prepared"])} {esc(C["prepared_date"])}</div></header>',
         cma.subject_heading({"address": s["address"], "locality": s["locality"],
                              "summary_facts": " · ".join(s["summary_facts"])}),
         '<div class="sp-hero"><div class="sp-rec">'
         f'<div class="lbl">{esc(L["sum_opening"])}</div><div class="price">{esc(op["opening_display"])}</div>'
         f'<div class="line">{esc(sm["ladder_line"])}</div>'
         f'<div class="line">{esc(L["sum_range_line"])} <b>{esc(rng["display_k"])}</b> · {esc(L["sum_asking"])} '
         f'<b>{esc(s["list_price_display"])}</b></div>'
         f'<div class="line headline">{sm["headline"]}</div></div>'
         '<div class="sp-stats">' + "".join(layout.tiles([(lbl, v) for v, lbl in sm["tiles"][i:i + 2]], n=2, cls="sp-tiles")
                                            for i in (0, 2)) + "</div></div>",
         f'<div class="sp-h">{esc(L["sum_comps_h"])} <span class="sp-sub">· {esc(L["sum_shaded"])}</span></div>',
         '<div class="sp-dot">' + cma.dotplot(sm["comps"], rng["low"], rng["high"], s["list_price"], sm["dot_asking"],
                                             (op["opening"], sm["dot_offer"]), kfmt=fmt.k) + "</div>"]
    cost = layout.table([Col(0, L["sum_costs"]), Col(1, "", align="num")],
                        [[r[0], flagged(r[1], r[2])] for r in sm["cost_rows"]], keep="whole", cls="sp-table",
                        row_classes={1: "rec"})
    fit = f'<div class="note fitline">{esc(sm["cash_fit_line"])}</div>' if sm["cash_fit_line"] else ""
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{esc(L["sum_why"])}</div>{ul(sm["why"], "")}</div>'
             f'<div>{cost}{fit}<div class="note">{esc(sm["cost_note"])}</div></div></div>')
    o.append(f'<div class="sp-h">{esc(L["sum_check"])}</div><div class="sp-steps">' +
             "".join(f'<div class="sp-step"><b>{h}</b>{d}</div>' for h, d in sm["check_first"]) + "</div>")
    o.append(f'<div class="sp-next"><span><b>{esc(L["sum_next"])}</b> {sm["next_step"]}</span></div>')
    o.append(f'<div class="note details">{esc(L["line_details"])}</div></div>')
    return "".join(o)


# --- the analysis -----------------------------------------------------------------------------------------------------

def p(text, cls=""):
    return f'<p class="{cls}">{text}</p>' if cls else f"<p>{text}</p>"


def home(C):
    s = C["subject"]
    out = [f'<h2>{esc(L["h_home"])}</h2>',
           '<div class="facts">' + "".join(f"<div><span>{esc(a)}</span><b>{esc(v)}</b></div>" for a, v in s["facts"]) + "</div>"]
    if s["summary"]:
        out.append(p(s["summary"]))
    return out


def bottom_line(C):
    rng, bl = C["range"], C["bottom_line"]
    why = f'<p>{bl["why"]}</p>' if bl["why"] else ""
    return [f'<h2>{esc(L["h_bottom"])}</h2>',
            f'<div class="verdict"><div class="range">{esc(rng["display"])}</div>'
            f'<div class="mid">{esc(t("range_caption", mid=rng["midpoint_display"]))}</div>'
            f'<p>{esc(bl["line"])}</p>{why}</div>']


def history(C):
    h = C["history_section"]
    if not h:
        return []
    out = [f'<h3>{esc(h["heading"])}</h3>', p(esc(" ".join(h["lines"]))),
           layout.table([Col(0, L["th_date"], wrap="nowrap"), Col(1, L["th_event"]), Col(2, L["th_price"], align="num")],
                        [[r[0], raw(r[1]), r[2]] for r in h["rows"]])]
    if h["takeaway"]:
        out.append(p(h["takeaway"]))
    return out


def offer_plan(C):
    op, off = C["offer_plan"], C["offer"]
    out = [f'<h3>{esc(L["h_offer_plan"])}</h3>', p(esc(op["intro"])),
           p(f'<strong>{esc(op["posture_label"])}</strong> {op["posture_line"]}'),
           layout.table([Col(0, L["th_step"], wrap="nowrap"), Col(1, L["th_amount"], align="num"), Col(2, L["th_why"])],
                        [[r[0], r[1], raw(r[2])] for r in op["ladder"]], row_classes={0: "total"})]
    if op["credit_alt"]:
        out.append(p(esc(op["credit_alt"])))
    if op["conditions"]:
        out.append(p(f'<strong>{esc(L["line_conditions"])}</strong> {op["conditions"]}', "note"))
    if off["bullets"]:
        out += [f'<h3>{esc(off["heading"])}</h3>', ul(off["bullets"])]
    return out


def comps(C):
    c = C["comps"]
    intro = " ".join(x for x in (c["intro"], esc(c["count_line"])) if x)
    cards = [
        f'<div class="comp"><div class="comp-h"><b>{esc(cd["address"])}</b>'
        f'<span class="adj">{esc(L["adjusted"])} {esc(cd["adjusted_display"])}</span></div>'
        f'<div class="meta">{esc(" · ".join(cd["meta"]))}</div>'
        '<div class="adj-lines">' + "".join(f'<span><i>{esc(a)}</i> {esc(v)}</span>' for a, v in cd["lines"][1:]) + "</div>"
        + ul(cd["bullets"], "") + "</div>" for cd in c["cards"]]
    rows = c["table"] + [c["subject_row"]]
    method = " ".join(x for x in (esc(c["method"]), c["method_note"]) if x)
    out = [f'<h2>{esc(L["h_compared"])}</h2>', p(intro), p(method, "note") if method else "",
           # two cards a row, each row its own block: the first stays with the heading, the rest flow page to page
           *[f'<div class="comps2">{"".join(cards[i:i + 2])}</div>' for i in range(0, len(cards), 2)],
           layout.table([Col(0, L["th_sale"]), Col(1, L["th_sold_for"], align="num"), Col(2, L["th_seller_paid"], align="num"),
                         Col(3, L["th_adjusted"], align="num")], rows, row_classes={len(rows) - 1: "subj"})]
    if c["lean"]:
        out.append(p(c["lean"]))
    return [x for x in out if x]


def scatter(C, notes_out):
    sc = C["scatter"]
    if not sc:
        return []
    s, rng = C["subject"], C["range"]
    chart = layout.Chart()
    svg, info = cma.scatter(C["_homes"], {**sc["ratios"], "callouts": sc["callouts"], "subject_label": sc["subject_label"],
                                          "subject_label_pos": sc["subject_label_pos"]},
                            s["sqft"], s["list_price"], s["mls_address"], (rng["low"], rng["high"]), compute.labels,
                            [cd["address"] for cd in C["comps"]["cards"]], points=C["_points"], chart=chart,
                            band_label=sc["band_label"], kfmt=fmt.k)
    notes_out["scatter_labels"] = {"moved": info["labels_moved"], "overlapping": info["labels_overlapping"],
                                   "leader": info["labels_leader"], "dropped": info["labels_dropped"]}
    notes_out["callout_checks"] = cma.callout_checks(info)
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
    cols = [Col(0, L["th_address"]), Col(1, L["th_status"]), Col(2, L["th_price"], align="num"),
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


def costs(C):
    k = C["costs"]
    tx, pm, cr = k["taxes"], k["payment"], k["credit"]
    out = [f'<h2>{esc(L["h_costs"])}</h2>', f'<h3>{esc(tx["heading"])}</h3>', p(esc(tx["intro"])),
           layout.table([Col(0, tx["header"]), Col(1, L["th_yearly"], align="num"), Col(2, L["th_monthly"], align="num")],
                        tx["rows"], row_classes={i: "tax-jump" for i in range(1, len(tx["rows"]))}),
           p(f'<strong>{esc(tx["escrow_lead"])}</strong> {esc(tx["escrow"])}')]
    if k["insurance"]:
        out += [f'<h3>{esc(L["h_insurance"])}</h3>', p(k["insurance"])]
    n = len(pm["header"]) - 1
    rows = [list(r) for r in pm["rows"]]
    rows[pm["cash_row"]] = [rows[pm["cash_row"]][0]] + [flagged(v, f) for v, f in zip(rows[pm["cash_row"]][1:], pm["cash_flags"])]
    classes = {pm["total_row"]: "total"}
    if pm["alt_row"] is not None:
        classes[pm["alt_row"]] = "alt"
    cols = [Col(0, pm["header"][0])] + [Col(i, pm["header"][i], align="num") for i in range(1, n + 1)]
    out += [f'<h3>{esc(L["h_payment"])}</h3>', p(esc(pm["intro"])),
            layout.table(cols, rows, row_classes=classes, caption=pm["per_10k"])]
    if cr:
        rows = [list(r) for r in cr["rows"]]
        rows[1] = [rows[1][0]] + [Raw(esc(v) + (f' <span class="flag">({esc(f)})</span>' if f else "")) if f else v
                                  for v, f in zip(rows[1][1:], cr["credit_flags"])]
        rows[cr["cash_row"]] = [rows[cr["cash_row"]][0]] + [flagged(v, f) for v, f in zip(rows[cr["cash_row"]][1:], cr["cash_flags"])]
        cols = [Col(0, cr["header"][0])] + [Col(i, cr["header"][i], align="num") for i in range(1, len(cr["header"]))]
        out += [f'<h3>{esc(L["h_credit"])}</h3>', p(esc(cr["intro"])),
                layout.table(cols, rows, row_classes={cr["cash_row"]: "total"})]  # runs on with its header repeated
        after = " ".join(x for x in (esc(cr["per_5k"]), cr["takeaway"]) if x)
        if after:
            out.append(p(after))
        if cr["buydown"]:
            out.append(p(esc(cr["buydown"])))
    out.append(layout.notes_block(C["notes"], title=L["h_notes"], cls="cost-notes"))
    return out


def watch(C):
    w = C["watch"]
    out = []
    if w["items"]:
        out += [f'<h2>{esc(L["h_watch"])}</h2>', ul(w["items"], "plain watch")]
    if w["questions"]:
        out += [f'<h3>{esc(L["h_questions"])}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in w["questions"]) + "</ol>"]
    return out


def closing(C, agent):
    """How This Was Prepared, the footer and the closing notices kept together, so the notices never sit alone on a
    last page (CMA-276)."""
    return ('<div class="kg sec">' + f'<h2>{esc(L["h_method"])}</h2>' + "".join(p(esc(x)) for x in C["method"]["lines"])
            + footer_block(agent, C) + render.notices(agent, C["notices"]) + "</div>")


def build_html(C, agent, sample=False, notes_out=None):
    """The report's HTML from the document model. `notes_out` (a dict) receives the chart's label placement notes."""
    notes_out = {} if notes_out is None else notes_out
    with open(os.path.join(ASSETS, "buyer-cma.css"), encoding="utf-8") as f:
        css = cma.css() + f.read()
    body = (home(C) + bottom_line(C) + history(C) + offer_plan(C) + comps(C) + scatter(C, notes_out) + competition(C)
            + market(C) + costs(C) + watch(C))
    content = ('<div class="wrap">' + page_one(C, agent) + '<div class="pb"></div>' + layout.group_blocks(body)
               + closing(C, agent) + "</div>")
    theme = design.theme(agent.get("brand"), "buyer")  # the subject home is black (cma.css), never a second hue
    doc = render.page(content, css=css, title=f'{L["doc_label"]}: {C["subject"]["address"]}',
                      theme_css=design.css_vars(theme), body_class="font-bundled bcma")
    return doc.replace("<html>", '<html lang="en">', 1)


def profile_check(agent):
    """CMA-221: a chat reminder when the name or brokerage is missing, or None. Never printed in the PDF: it simply
    leaves the missing parts out."""
    gaps = [w for w, f in (("agent name", "name"), ("brokerage", "brokerage")) if not agent.get(f)]
    if not gaps:
        return None
    return (f"{'no profile' if len(gaps) == 2 else 'profile incomplete'}: {' and '.join(gaps)} missing, so the PDF "
            "carries none. Ask the agent for them (or use their saved profile with --profile) and render again.")


# Label fields the model types, put in Title Case before the build (shared/prose.py title_labels)
LABEL_FIELDS = ("**.heading", "summary_page.label", "summary_page.check_first[][0]", "comps.cards[].adjustments[].label",
                "subject.facts[][0]")


def compute_model(data, ctx):
    """render.main's compute step: the document model, once per run."""
    C = compute.run(data, ctx.get("mls"), ctx.get("data_file"))
    if C.get("stage") != "full":
        raise compute.ReportError("report.json has only the comps: add bottom_line, offer_plan and costs for the report.")
    return C


def build(C, fmt_, out_dir, ctx):
    agent = ctx["agent"]
    sample = bool(ctx.get("sample") or C.get("sample"))
    label = " · ".join(x for x in (C["subject"]["address"], L["doc_label"],
                                   ", ".join(str(agent[f]) for f in ("name", "brokerage") if agent.get(f))) if x)
    if sample:
        label = "SAMPLE DATA · " + label
    chart_notes = {}
    doc = build_html(C, agent, sample, chart_notes)
    path = os.path.join(out_dir, render.filename(C["subject"]["address"], "Buyer CMA", ext="pdf"))
    info = layout.print_pdf(doc, path, FIT, footer_html=render.footer(label))
    pg = info.get("paginate") or {}
    if pg.get("page1_px", 0) > FIT.content_px()[1]:
        print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
    elif pg.get("fit_level"):
        print(f"Page 1 ran long and was tightened (step {pg['fit_level']} of 3) to fit.", file=sys.stderr)
    for c in info["checks"]:
        print(f"Check: {c}", file=sys.stderr)
    labels = chart_notes.get("scatter_labels") or {}
    for text, asked, used in labels.get("moved", []):
        where = f"still {used}" if used.split(",")[0] == asked else f"placed {used}, not {asked},"
        print(f"Chart label {text!r}: {where} to clear the markers (information).", file=sys.stderr)
    for text, side in labels.get("leader", []):
        print(f"Chart label {text!r}: no clear spot beside its point, so it sits farther off to the {side} with a thin "
              "line to it (information).", file=sys.stderr)
    for text in labels.get("dropped", []):
        print(f"Chart label {text!r} left off: no clear spot even on a line, and the legend names the home "
              "(information).", file=sys.stderr)
    for text in labels.get("overlapping", []):
        print(f"Check: chart label {text!r} still overlaps a marker or another label: shorten it or pick another side.",
              file=sys.stderr)
    for c in chart_notes.get("callout_checks", []):
        print(f"Check: {c}", file=sys.stderr)
    for w in C["warnings"]:
        print(f"Check: {w}", file=sys.stderr)
    if profile_check(agent):
        print(f"Check: {profile_check(agent)}", file=sys.stderr)
    return [path]


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, compute=compute_model,
                       errors=(compute.ReportError, compute.mls.ExportError), labels=LABEL_FIELDS)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyError as e:
        sys.exit(f"report.json is missing {e}")
