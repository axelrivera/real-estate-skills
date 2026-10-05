"""Seller net sheet PDF: one page, one to three prices side by side.

    python3 scripts/render.py net-sheet.json [--cma FILE.seller.cma.json] [--profile profile.md] [--sample] [--out DIR]

Every number comes from compute.py (the same result the markdown summary is filled from). The page holds the
header, a fact row, the net for each price, the itemized table, where the price goes, and the notes. Colors follow
the agent's seller-side brand color. Prints the path written, then the assumptions and warnings for the reply.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import design, handoff, render  # noqa: E402

esc = html.escape
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "net-sheet.css")
PAGE_LIMIT = 989  # px on one printed Letter page at the print viewport (11in minus 0.7in of margins, at 96 dpi)
FINAL_NOTE = "The title company's settlement statement gives the final figures."


def header(C, agent, sample):
    # Results_v4 case 09: no "Seller Side" pill (a seller's net sheet has only one side); the agent's name reads as a
    # signature, as the size of the other reports' agent line
    tag = '<span class="sample">SAMPLE DATA</span>' if sample else ""
    lines = [(f'Prepared for <b>{esc(C["prepared_for"])}</b> · ' if C.get("prepared_for") else "Prepared ") + esc(C["prepared_date"])]
    if agent.get("name"):
        lines.append(f'<b class="agent">{esc(agent["name"])}</b>')
        org = " · ".join(esc(str(agent[f])) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {esc(str(agent["license"]))}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return (f'<header><div><div class="t1">Seller Net Sheet{tag}</div><div class="t2">{esc(C["address_line"])}</div></div>'
            f'<div class="prep">{"<br>".join(lines)}</div></header>')


def fact_row(C):
    if not C["facts"]:  # nothing to show: no empty row between the header and the tiles
        return ""
    items = "".join(f'<span>{"<b class=rt>" + esc(f["text"]) + "</b>" if f.get("risk") else esc(f["text"])}</span>' for f in C["facts"])
    return f'<div class="divrow factrow"><div>{items}</div></div>'


def tiles(C):
    cols = C["columns"]
    out = []
    for c in cols:
        sub = f'Sale {c["price_display"]} · costs {c["total_costs_display"]} ({c["costs_pct_display"]})'
        out.append(f'<div class="tile"><span class="k">{esc(c["label"])}</span>'
                   f'<b class="{"short" if c["short"] else ""}">{c["tile_display"]}</b>'
                   f'<i>{esc(c["tile_label"])}</i><i>{esc(sub)}</i></div>')
    # one or two prices: the spare slots show figures already on the sheet, so the row stays three boxes wide
    out += [f'<div class="tile sum"><span class="k">{esc(t["label"])}</span>'
            f'<b{"" if t["display"].startswith("$") else " class=word"}>{esc(t["display"])}</b><i>{esc(t["note"])}</i></div>'
            for t in C.get("summary_tiles") or []]
    return f'<div class="tiles">{"".join(out)}</div>'


def table(C):
    cols = C["columns"]
    head = "<tr><th></th>" + "".join(f'<th class="n">{esc(c["label"])}</th>' for c in cols) + "</tr>"
    body = []
    for r in C["rows"]:
        if r["kind"] == "group":
            body.append(f'<tr class="group"><td colspan="{len(cols) + 1}">{esc(r["label"])}</td></tr>')
            continue
        cells = "".join(f'<td class="n{" empty" if v == "—" else ""}{" short" if r["kind"] == "final" and c["short"] else ""}">{v}</td>'
                        for v, c in zip(r["display"], cols))
        body.append(f'<tr class="{r["kind"]}"><td>{esc(r["label"])}</td>{cells}</tr>')
    widths = "<colgroup>" + "".join(f'<col style="width:{w:g}%">' for w in column_widths([c["label"] for c in cols])) + "</colgroup>"
    return f'<div class="tbl net"><table>{widths}<thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


TABLE_PX = 783  # the table's width: 8.5in less the 0.3in margins, at 96 dpi
HEAD_PX_PER_CHAR = 6.1  # a bold 8pt header character, about; plus 16px of cell padding
MIN_COL, MAX_COL, MIN_FIRST = 16, 27, 34  # % of the table


def column_widths(labels):
    """Results_v4 case 09: each price column wide enough for its header on one line ("$425,000 with $6,000 Credit"),
    within 16% to 27% of the table, and the row names the rest (at least 34%). [first, *price columns] in %."""
    need = [min(MAX_COL, max(MIN_COL, (len(t) * HEAD_PX_PER_CHAR + 16) / TABLE_PX * 100)) for t in labels]
    spare = 100 - MIN_FIRST
    if sum(need) > spare:  # too wide together: share the room, the longest give way first
        need = [n * spare / sum(need) for n in need]
    need = [round(n, 1) for n in need]
    return [round(100 - sum(need), 1)] + need


def bars(C):
    rows = []
    for c in C["columns"]:
        segs = "".join(f'<div class="seg {k}" style="width:{c["bar"][k] * 100:.2f}%"></div>' for k in ("costs", "payoffs", "net") if c["bar"][k] > 0)
        rows.append(f'<div class="row"><div class="lbl">{esc(c["label"])}</div><div class="track">{segs}</div>'
                    f'<div class="val">{c["net_display"]}</div></div>')
    legend = [("costs", "Seller Costs")] + ([("payoffs", "Payoffs")] if any(c["payoff_total"] for c in C["columns"]) else [])
    legend.append(("net", "Net to Seller" if C["cash_at_closing"] else "Net Before Payoff"))
    keys = "".join(f'<span><i class="{k}"></i>{t}</span>' for k, t in legend)
    return f'<div class="bars">{"".join(rows)}</div><div class="legend">{keys}</div>'


def build_html(C, agent, sample=False):
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    body = [header(C, agent, sample), fact_row(C), tiles(C)]
    if C["preliminary"]:
        body.append(f'<div class="prelim"><b>Preliminary:</b> {esc(C["preliminary_reason"][:1].upper() + C["preliminary_reason"][1:])}.</div>')
    body += ['<h2>Itemized Estimate</h2>', table(C), f'<div class="chart"><h2>Where the Sale Price Goes</h2>{bars(C)}</div>',
             '<ul class="notes">' + "".join(f"<li>{esc(n)}</li>" for n in C["notes"]) + "</ul>",
             render.notices(agent, [render.NOT_ADVICE + " " + FINAL_NOTE])]
    theme = design.theme(agent.get("brand"), "seller")
    return render.page("".join(body), css=css, title="Seller Net Sheet", theme_css=design.css_vars(theme))


def fit_one_page(pg):
    """(height, chart dropped?, clipped labels): the compact layout when the page would run onto a second one, then without the chart
    (it repeats the table's totals) when even that doesn't fit, as with a long disclaimer in the profile."""
    measure = "() => document.body.getBoundingClientRect().height"
    height = pg.evaluate(measure)
    for step in ("compact", "nochart"):
        if height <= PAGE_LIMIT:
            break
        pg.evaluate(f"() => document.body.classList.add('{step}')")
        height = pg.evaluate(measure)
    # iteration 9 eval 1: a price label too long for its column header was cut off with no warning
    clipped = pg.evaluate("() => [...document.querySelectorAll('th, .tile .k, .bars .lbl')]"
                          ".filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)")
    return height, pg.evaluate("() => document.body.classList.contains('nochart')"), clipped


def build(data, fmt, out_dir, ctx):
    C = compute.run(data, ctx.get("cma"), ctx.get("mls"))
    sample = ctx.get("sample") or bool(data.get("sample"))
    path = os.path.join(out_dir, render.filename(C["address"], "Seller Net Sheet", ext="pdf"))
    height, no_chart, clipped = render.html_to_pdf(build_html(C, ctx["agent"], sample), path, before_print=fit_one_page,
                                          footer_html=render.footer(f"Seller Net Sheet · {C['address']}", right_pages=False))
    if height > PAGE_LIMIT:
        os.remove(path)
        raise compute.NetSheetError(f"The net sheet runs {height - PAGE_LIMIT:.0f}px past one page: shorten the price "
                                    "labels or the names of other costs, or compare fewer prices.")
    if clipped:
        os.remove(path)
        raise compute.NetSheetError("These labels don't fit their column and would be cut off: "
                                    f"{', '.join(dict.fromkeys(clipped))}. Give the price a shorter label.")
    if no_chart:
        print("Layout: the Where the Sale Price Goes chart was left out to keep the sheet on one page.", file=sys.stderr)
    for a in C["assumptions"]:
        print(f"Assumed: {a}", file=sys.stderr)
    for w in C["warnings"]:
        print(f"Warning: {w}", file=sys.stderr)
    if C["preliminary"]:
        print(f"Preliminary: {C['preliminary_reason']}.", file=sys.stderr)
    return [path]


def options(ap):
    ap.add_argument("--cma", help="a seller CMA handoff (.seller.cma.json) for the same home")


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, extra_args=options,
                       errors=(compute.NetSheetError, handoff.HandoffError))


if __name__ == "__main__":
    main(sys.argv[1:])
