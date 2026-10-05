"""Seller net sheet PDF: one page, one to three prices side by side.

    python3 scripts/render.py net-sheet.json [--cma FILE.seller.cma.json] [--profile profile.md] [--sample] [--out DIR]

compute.py builds the document model once (render.main's compute step); this file only places it with the shared
layout kit: the header, a fact row, the net for each price, the itemized table, where the price goes, and the notes
block. Colors follow the agent's seller-side brand color. Prints the path written, then the assumptions and
warnings for the reply.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import design, handoff, layout, render  # noqa: E402

esc = html.escape
L = compute.L
Raw = layout.Raw
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "net-sheet.css")
# One page, always: tighter spacing first, then without the chart (it repeats the table's totals), then tighter type
FIT = layout.Fit(one_page=True, steps=("compact", "nochart", "tight"))
SERIES = (("costs", "lg_costs"), ("payoffs", "lg_payoffs"), ("net", None))


def header(C, agent, sample):
    """The title and address, and on the right who it's for and the agent's name, which reads as a signature."""
    lines = [Raw((f'Prepared for <b>{esc(C["prepared_for"])}</b> · ' if C.get("prepared_for") else "Prepared ")
                 + f'<span class="nw">{esc(C["prepared_date"])}</span>')]
    if agent.get("name"):
        lines.append(Raw(f'<b class="agent">{esc(agent["name"])}</b>'))
        org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {agent["license"]}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return layout.header(L["doc_title"], C["address_line"], prepared=lines, sample=sample)


def tiles(C):
    """The net for each price, then (with one or two prices) summary figures already on the sheet; always three slots
    wide, so a tile never stretches."""
    items = []
    for c in C["columns"]:
        sub = Raw(esc(c["tile_label"]) + "<br>" + esc(compute.t("tile_sub", price=c["price_display"],
                                                                 costs=c["total_costs_display"], pct=c["costs_pct_display"])))
        items.append((c["label"], c["tile_display"], sub, "price short" if c["short"] else "price"))
    items += [(s["label"], s["display"], s["note"], "sum") for s in C["summary_tiles"]]
    return layout.tiles(items, n=compute.MAX_SCENARIOS, cls="net-tiles")


def table(C):
    cols = [layout.Col(0, "", cls="lbl-col")] + [layout.Col(i + 1, c["label"], align="num", cls="price-col")
                                                 for i, c in enumerate(C["columns"])]
    rows, classes = [], {}
    for r in C["rows"]:
        classes[len(rows)] = r["kind"]
        if r["kind"] == "group":
            rows.append([r["label"]] + [""] * len(C["columns"]))
            continue
        cells = []
        for v, c in zip(r["display"], C["columns"]):
            if v == "—":
                v = Raw('<span class="empty">—</span>')
            elif r["kind"] == "final" and c["short"]:
                v = Raw(f'<span class="short">{esc(v)}</span>')
            cells.append(v)
        rows.append([r["label"]] + cells)
    return layout.table(cols, rows, keep="whole", cls="net", row_classes=classes)


def bars(C):
    """One stacked bar per price; the legend names only the series drawn."""
    chart = layout.Chart()
    names = {"costs": L["lg_costs"], "payoffs": L["lg_payoffs"],
             "net": L["lg_net"] if C["cash_at_closing"] else L["lg_net_before"]}
    rows = []
    for c in C["columns"]:
        segs = []
        for k, _ in SERIES:
            if c["bar"][k] > 0:
                chart.mark(k, names[k], "bar", color=f"var(--bar-{k})")
                segs.append(f'<div class="seg {k}" style="width:{c["bar"][k] * 100:.2f}%"></div>')
        rows.append(f'<div class="lbl">{esc(c["label"])}</div><div class="track">{"".join(segs)}</div>'
                    f'<div class="val">{esc(c["net_display"])}</div>')
    return layout.chart_frame(f'<div class="bars">{"".join(rows)}</div>', chart.legend(), title=L["h_chart"], cls="chart")


def build_html(C, agent, sample=False):
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    body = [header(C, agent, sample), layout.fact_row(C["facts"]) if C["facts"] else "", tiles(C)]
    if C["preliminary"]:
        reason = C["preliminary_reason"]
        body.append(f'<div class="prelim"><b>{esc(L["preliminary"])}:</b> {esc(reason[:1].upper() + reason[1:])}.</div>')
    body += [f'<h2>{esc(L["h_itemized"])}</h2>', table(C), bars(C), layout.notes_block(C["notes"], title=None),
             render.notices(agent, [render.NOT_ADVICE + " " + L["final_figures"]])]
    theme = design.theme(agent.get("brand"), "seller")
    return render.page("".join(body), css=css, title=L["doc_title"], theme_css=design.css_vars(theme),
                       body_class="font-bundled")


def compute_model(data, ctx):
    """render.main's compute step: the document model, once per run."""
    return compute.run(data, ctx.get("cma"), ctx.get("mls"))


def build(C, fmt, out_dir, ctx):
    sample = bool(ctx.get("sample") or C.get("sample"))
    path = os.path.join(out_dir, render.filename(C["address"], L["doc_title"], ext="pdf"))
    info = layout.print_pdf(build_html(C, ctx["agent"], sample), path, FIT,
                            footer_html=render.footer(f"{L['doc_title']} · {C['address']}", right_pages=False))
    if info["top"] > info["limit"] or (info["pages"] and len(info["pages"]) > 1):
        os.remove(path)
        raise compute.NetSheetError(f"The net sheet runs {max(info['top'] - info['limit'], 0):.0f}px past one page: "
                                    "shorten the price labels or the names of other costs, or compare fewer prices.")
    if "nochart" in info["steps"]:
        print(f"Layout: the {L['h_chart']} chart was left out to keep the sheet on one page.", file=sys.stderr)
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
    return render.main(build, formats=("pdf",), argv=argv, extra_args=options, compute=compute_model,
                       errors=(compute.NetSheetError, handoff.HandoffError),
                       labels=("scenarios[].label", "costs.other[].label", "costs.other_payoffs[].label"), linked=handoff.linked)


if __name__ == "__main__":
    main(sys.argv[1:])
