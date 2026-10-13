"""Buying Pattern PDF: one landscape page, every closed sale on a January to December axis by sold price.

    python3 scripts/render.py market-timing.json [--profile profile.md] [--mls NAME] [--sample] [--out DIR]

compute.py builds the document model once (render.main's compute step); this file only draws it: the title and a
subtitle (area, date basis, window, sales), the scatter with the busy seasons in dotted outlines and the busiest month
in a solid one, the legend, and the takeaway line. No notes and no footer: it's the agent's conversation piece for a
listing appointment. Colors follow the agent's seller-side brand color, the latest year darkest. Prints the path
written, then the warnings for the reply.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import cma, design, fmt, layout, render  # noqa: E402

esc = html.escape
L = compute.L
t = compute.t
SIDE = "seller"
# One shape per year, all the same size (the same area as a circle of radius DOT_R), so a year is told by its shape
# and shade, never by how big its marks look: the latest a brand circle, the year before a lighter brand diamond, the
# oldest a gray triangle
YEAR_FILL = ("var(--brand)", "var(--brand-accent)", "var(--grey)")
DOT_R = 6.5


def year_mark(year, cx, cy, r=DOT_R, cls=""):
    """The mark for a sale `year` years back (0 the latest) centered on (cx, cy), at the area of a circle of radius r."""
    style = f'fill:{YEAR_FILL[min(year, 2)]};stroke:var(--bg);stroke-width:1.25'
    cls = f' class="{cls}"' if cls else ""
    if year == 0:
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" style="{style}"{cls}/>'
    if year == 1:
        d = r * 1.2533  # a square turned 45 degrees, half its diagonal: the circle's area
        pts = f"{cx:.1f},{cy - d:.1f} {cx + d:.1f},{cy:.1f} {cx:.1f},{cy + d:.1f} {cx - d:.1f},{cy:.1f}"
    else:
        a = r * 2.6935  # an equilateral triangle's side at the circle's area, centered on its centroid
        h = a * 0.8660
        pts = f"{cx:.1f},{cy - 2 * h / 3:.1f} {cx + a / 2:.1f},{cy + h / 3:.1f} {cx - a / 2:.1f},{cy + h / 3:.1f}"
    return f'<polygon points="{pts}" style="{style}"{cls}/>'


SEASON_STYLE = "fill:none;stroke:var(--brand);stroke-width:1.5;stroke-dasharray:2 4"
PEAK_STYLE = "fill:none;stroke:var(--brand-strong);stroke-width:2"
SWATCH_SEASON = f'<rect x="1.5" y="1.5" width="11" height="11" style="{SEASON_STYLE.replace("2 4", "2 2")}"/>'
SWATCH_PEAK = f'<rect x="1.5" y="1.5" width="11" height="11" style="{PEAK_STYLE}"/>'
DOT_R = 6.5


def _runs(months):
    """A season's months (0 to 11) as unbroken stretches of the axis: one that wraps (November to February) is drawn as
    two boxes, November and December at the right edge, January and February at the left."""
    out, cur = [], [months[0]]
    for m in months[1:]:
        if m == cur[-1] + 1:
            cur.append(m)
        else:
            out.append(cur)
            cur = [m]
    return out + [cur]


def draw(C, chart, size):
    """The scatter as SVG: twelve month bands, sold price up the side, the season boxes behind the dots."""
    W, H = size
    Lm, R, T, B = 78, 16, 14, 66
    pts = C["_points"]
    prices = [p["price"] for p in pts]
    ystep = cma.nice_step(max(prices) - min(prices) + 20000, 8)
    Y0 = max(0, (min(prices) - ystep / 3) // ystep * ystep)
    Y1 = -(-(max(prices) + ystep / 3) // ystep) * ystep
    band = (W - Lm - R) / 12

    def x(v):
        return Lm + v * band

    def y(v):
        return T + (Y1 - v) / (Y1 - Y0) * (H - T - B)

    axis_x = L["axis_x_contract"] if C["basis"] == "contract" else L["axis_x_close"]
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" class="scatter" aria-label="{esc(L["axis_y"])} / {esc(axis_x)}">']
    for v in cma.tick_values(Y0, Y1, ystep):
        o.append(f'<line x1="{Lm}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                 f'<text x="{Lm - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="tick">{fmt.k(v)}</text>')
    for m, row in enumerate(C["months"]):
        o.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{T}" y2="{H - B}" class="grid"/>'
                 f'<text x="{x(m + 0.5):.1f}" y="{H - B + 19}" text-anchor="middle" class="tick">{esc(row["short"])}</text>'
                 f'<text x="{x(m + 0.5):.1f}" y="{H - B + 35}" text-anchor="middle" class="tick" style="font-size:10.5px">'
                 f'{esc(L["sales_count_one"] if row["sales"] == 1 else t("sales_count", n=row["sales"]))}</text>')
    o.append(f'<line x1="{W - R}" x2="{W - R}" y1="{T}" y2="{H - B}" class="grid"/>')
    o.append(f'<text x="{(Lm + W - R) / 2}" y="{H - 6}" text-anchor="middle" class="axis">{esc(axis_x)}</text>')
    o.append(f'<text transform="translate(16,{(T + H - B) / 2}) rotate(-90)" text-anchor="middle" class="axis">'
             f'{esc(L["axis_y"])}</text>')

    # the legend in reading order: newest year first, then the boxes
    years = {}
    for p in pts:
        years[p["year"]] = years.get(p["year"], 0) + 1
    for i, yr in enumerate(C["years"]):
        if years.get(i):
            chart.mark(f"y{i}", yr["label"], year_mark(i, 7, 7.5 if i > 1 else 7, r=5), count=years[i])
    pad = 4
    for s in C["seasons"]:
        chart.mark("season", L["lg_season"], SWATCH_SEASON)
        for run in _runs([m - 1 for m in s["months"]]):
            o.append(f'<rect x="{x(run[0]) + pad:.1f}" y="{T + pad}" width="{len(run) * band - 2 * pad:.1f}" '
                     f'height="{H - T - B - 2 * pad}" style="{SEASON_STYLE}" class="season"/>')
    if C["peak_month"]:
        chart.mark("peak", L["lg_peak"], SWATCH_PEAK)
        m, inset = C["peak_month"] - 1, 2 * pad + 3
        o.append(f'<rect x="{x(m) + inset:.1f}" y="{T + inset}" width="{band - 2 * inset:.1f}" '
                 f'height="{H - T - B - 2 * inset}" style="{PEAK_STYLE}" class="peak"/>')
    for p in sorted(pts, key=lambda p: -p["year"]):  # oldest first, so the latest year sits on top
        tip = t("tip_sale", address=cma.display_address(p["address"]), price=fmt.money(p["price"]),
                when=fmt.date_short(p["date"]))
        o.append(f'<g><title>{esc(tip)}</title>{year_mark(p["year"], x(p["x"]), y(p["price"]), cls="sale")}</g>')
    o.append("</svg>")
    return "\n".join(o)


def compute_model(data, ctx):
    """render.main's compute step: the document model, once per run."""
    return compute.run(data, ctx.get("mls"), ctx.get("data_file"))


def build(C, fmt_, out_dir, ctx):
    sample = bool(ctx.get("sample") or C.get("sample"))
    chart = layout.Chart()
    svg = draw(C, chart, cma.sheet_size(subtitle=True, takeaway=C["takeaway"]))
    doc = cma.chart_sheet(svg, chart.legend(), C["title"], design.css_vars(design.theme(ctx["agent"].get("brand"), SIDE)),
                          tag=L["sample"] if sample else "", subtitle=C["subtitle"], takeaway=C["takeaway"])
    path = os.path.join(out_dir, render.filename(C["area"] or "", L["file_name"], ext="pdf"))
    info = layout.print_pdf(doc, path, cma.SHEET_FIT)
    if info["top"] > info["limit"] or (info["pages"] and len(info["pages"]) > 1):
        os.remove(path)
        raise compute.TimingError("The chart ran past one page: shorten the area name.")
    for c in info["checks"]:
        print(f"Check: {c}", file=sys.stderr)
    for w in C["warnings"]:
        print(f"Warning: {w}", file=sys.stderr)
    return [path]


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, compute=compute_model, errors=(compute.TimingError,))


if __name__ == "__main__":
    main(sys.argv[1:])
