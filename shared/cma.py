"""Report pieces shared by the buyer and seller CMAs: labels, tables, charts, keep-together groups, pagination.

All visible text comes from the skill's labels file (assets/labels.json). Colors are theme variables
(shared/cma.css), never hard-coded.
"""
import html
import json
import math
import os
import re

from . import finance, mls

CMA_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cma.css")
money = finance.money
ADJ_NET_LIMIT, ADJ_GROSS_LIMIT = 0.15, 0.25  # common appraisal guidelines, as shares of the comp's sale price
esc = html.escape


# --- labels -------------------------------------------------------------------

class Labels:
    """Label lookup with {placeholders}: labels('pay_header', price='$474,900')."""

    def __init__(self, assets_dir, overrides=None):
        with open(os.path.join(assets_dir, "labels.json"), encoding="utf-8") as f:
            self.text = json.load(f)
        self.text.update(overrides or {})

    def __call__(self, key, **kw):
        t = self.text[key]
        return t.format(**kw) if kw else t


def css():
    with open(CMA_CSS, encoding="utf-8") as f:
        return f.read()


# --- html building blocks ----------------------------------------------------

def table(head, rows, num_cols=(), row_classes=None):
    th = "".join(f'<th class="n">{h}</th>' if i in num_cols else f"<th>{h}</th>" for i, h in enumerate(head))
    body = []
    for ri, r in enumerate(rows):
        cls = (row_classes or {}).get(ri, "")
        tds = "".join(f'<td class="n">{c}</td>' if i in num_cols else f"<td>{c}</td>" for i, c in enumerate(r))
        body.append(f'<tr class="{cls}">{tds}</tr>' if cls else f"<tr>{tds}</tr>")
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def ul(items, cls="plain"):
    return f'<ul class="{cls}">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def subject_heading(subject):
    """Page-1 heading: the address across the full width, a location line (city, area, MLS number), the home facts.

    `locality` is "City, ST ZIP · Subdivision · County · MLS #": the first part is the city line and a part
    starting with "MLS" goes last. Items are separated by dividers that never dangle at a line end.
    """
    parts = [x.strip() for x in str(subject.get("locality", "")).split("·") if x.strip()]
    mls_no = [x for x in parts[1:] if x.upper().startswith("MLS")]
    loc = parts[:1] + [x for x in parts[1:] if x not in mls_no] + mls_no
    facts = [x.strip() for x in str(subject.get("summary_facts", "")).split("·") if x.strip()]

    def row(cls, items):
        return f'<div class="divrow {cls}"><div>' + "".join(f"<span>{esc(x)}</span>" for x in items) + "</div></div>" if items else ""
    return f'<div class="subj-head"><h1>{esc(subject["address"])}</h1>{row("loc", loc)}</div>{row("homefacts", facts)}'


def adjustment_scope_warning(market, county, price):
    """CMA-10: the built-in adjustment rates are flat dollars from one area and price band. Outside them, say so."""
    scope = market.get("cma.calibrated_for") if market is not None else None
    if not scope or market.source("cma.adjustments") not in ("state", "mls", "mixed"):
        return None  # the agent's own rates, or none built in
    counties = {str(c).lower() for c in scope.get("counties") or []}
    lo, hi = (scope.get("price_range") or [None, None])[:2]
    outside = []
    if county and counties and str(county).lower().removesuffix(" county") not in counties:
        outside.append(f"{county} County")
    if price and lo and hi and not lo <= price <= hi:
        outside.append(f"a {money(price)} home")
    if not outside:
        return None
    return (f"The built-in adjustment rates were set from {', '.join(scope.get('counties') or [])} sales between "
            f"{money(lo)} and {money(hi)}; they don't fit {' and '.join(outside)}. Derive the rates from paired sales in the "
            "export (or use the agent's), scale flat amounts like the pool to the price, and say so in method_note.")


def k(v):
    """$455K, or $1.25M from a million up (CMA-12)."""
    if abs(v) >= 1_000_000:
        return "$" + f"{v / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    return money(v / 1000) + "K"


def nice_step(span, target=6):
    """A tick step of 1, 2, 2.5 or 5 x 10^n giving about `target` ticks across `span` (CMA-12)."""
    raw = max(span, 1) / target
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


def _ticks(lo, hi, step):
    v, out = lo, []
    while v <= hi + step / 1000:
        out.append(round(v))
        v += step
    return out


def fill(value, values):
    """Replace {median_adjusted}-style placeholders in every string of `value` (report wording), so numbers the
    scripts compute aren't typed by hand. Unknown names are left as written."""
    if isinstance(value, str):
        return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [fill(v, values) for v in value]
    if isinstance(value, dict):
        return {key: fill(v, values) for key, v in value.items()}
    return value


def page_one_values(C):
    """Placeholders every CMA page 1 can use."""
    return {"median_adjusted": C["median_adjusted_display"]}


# --- scatterplot ---------------------------------------------------------------

def _street(address):
    """Match key for an address: the part before the first comma, upper case, spaces collapsed."""
    return " ".join(str(address).split(",")[0].upper().split())


def scatter_points(homes, sc, subject_sqft, subject_address, comps=()):
    """The chart's points, shared by the PDF and the deck so they always match (CMA-24): sold homes used as comps
    (`comp`, matched by the comp cards' addresses), other sales (`sold`), and every active listing (`active`).
    Returns ({kind: [homes]}, excluded [(address, sqft, 'sale'|'listing')], others)."""
    comp_keys = {_street(a) for a in comps}
    lo, hi = subject_sqft * sc.get("min_size_ratio", 0.6), subject_sqft * sc.get("max_size_ratio", 1.4)
    others = [h for h in homes if not mls.same_address(h["address"], subject_address)]
    pts, excluded = {"comp": [], "sold": [], "active": []}, []
    for h in others:
        sold = h["status"] == "SOLD" and h.get("close_price")
        active = h["status"] == "ACTIVE" and h.get("current_price")
        if not h.get("living_area") or not (sold or active):
            continue
        if not lo <= h["living_area"] <= hi:
            excluded.append((h["address"], int(h["living_area"]), "sale" if sold else "listing"))
        elif active:
            pts["active"].append(h)
        else:
            pts["comp" if _street(h["address"]) in comp_keys else "sold"].append(h)
    excluded.sort(key=lambda e: e[2] != "sale")  # sales first, then listings
    return pts, excluded, others


def scatter(homes, sc, subject_sqft, subject_price, subject_address, band, L, comps=()):
    """Price vs. size for sold and active homes near the subject's size, with the supported range band.

    `comps`: the comp cards' addresses, drawn as comparable sales.
    `sc`: {callouts: [{address, label, side}], subject_label, subject_label_pos, min/max/fit_size_ratio}.
    Label sides: left, right, above or below.
    Returns (svg, info) where info has trend_at_subject, r2, excluded [(address, sqft, kind)], n_sold, n_active and
    counts {kind: n} for scatter_legend.
    """
    pts, excluded, others = scatter_points(homes, sc, subject_sqft, subject_address, comps)
    sold, act = pts["comp"] + pts["sold"], pts["active"]
    kind = {id(h): k for k, hs in pts.items() for h in hs}
    fit = mls.trend(others, subject_sqft, sc.get("fit_size_ratio", 1.6))

    def cat(h):
        return kind[id(h)]

    xs = [h["living_area"] for h in sold + act] + [subject_sqft]
    ys = [h["close_price"] for h in sold] + [h["current_price"] for h in act] + [subject_price, band[0], band[1]]
    X0, X1 = math.floor((min(xs) - 50) / 100) * 100, math.ceil((max(xs) + 50) / 100) * 100
    ystep = nice_step(max(ys) - min(ys) + 30000, 8)
    Y0, Y1 = math.floor((min(ys) - 15000) / ystep) * ystep, math.ceil((max(ys) + 15000) / ystep) * ystep
    W, H, Lm, R, T, B = 760, 470, 72, 20, 20, 58

    def x(v):
        return Lm + (v - X0) / (X1 - X0) * (W - Lm - R)

    def y(v):
        return T + (Y1 - v) / (Y1 - Y0) * (H - T - B)

    def shape(kind, cx, cy, hollow, tip):
        cls, r = f"m-{kind}" + (" hol" if hollow else ""), 6
        if kind in ("comp", "active"):
            g = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r + 0.5}" class="{cls}"/>'
        else:
            g = f'<rect x="{cx - r + .5:.1f}" y="{cy - r + .5:.1f}" width="{2 * r - 1}" height="{2 * r - 1}" class="{cls}"/>'
        return f"<g><title>{esc(tip)}</title>{g}</g>"

    o = [f'<svg viewBox="0 0 {W} {H}" role="img" class="scatter" aria-label="{esc(L("axis_y"))} / {esc(L("axis_x"))}">',
         f'<rect x="{Lm}" y="{y(band[1]):.1f}" width="{W - Lm - R}" height="{y(band[0]) - y(band[1]):.1f}" class="band"/>',
         f'<text x="{Lm + 8}" y="{y(band[1]) - 6:.1f}" class="lbl-band">{esc(L("band"))} {k(band[0])}–{k(band[1])}</text>']
    for v in _ticks(Y0, Y1, ystep):
        o.append(f'<line x1="{Lm}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                 f'<text x="{Lm - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="tick">{k(v)}</text>')
    step = nice_step(X1 - X0, 8)
    for v in _ticks(math.ceil(X0 / step) * step, X1, step):
        o.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{H - B}" class="grid"/>'
                 f'<text x="{x(v):.1f}" y="{H - B + 18}" text-anchor="middle" class="tick">{v:,}</text>')
    o.append(f'<text x="{(Lm + W - R) / 2}" y="{H - 12}" text-anchor="middle" class="axis">{esc(L("axis_x"))}</text>')
    o.append(f'<text transform="translate(16,{(T + H - B) / 2}) rotate(-90)" text-anchor="middle" class="axis">{esc(L("axis_y"))}</text>')
    if fit:
        xa, xb = X0 + 50, X1 - 50
        o.append(f'<line x1="{x(xa):.1f}" y1="{y(fit["intercept"] + fit["slope"] * xa):.1f}" '
                 f'x2="{x(xb):.1f}" y2="{y(fit["intercept"] + fit["slope"] * xb):.1f}" class="trend"/>')
    for h in sold:
        o.append(shape(cat(h), x(h["living_area"]), y(h["close_price"]), False,
                       f'{h["address"].title()}: {L("tip_sold")} ${int(h["close_price"]):,}, {int(h["living_area"]):,} sq ft'))
    for h in act:
        o.append(shape("active", x(h["living_area"]), y(h["current_price"]), True,
                       f'{h["address"].title()}: {L("tip_active")} ${int(h["current_price"]):,}, {int(h["living_area"]):,} sq ft'))
    sx, sy, d = x(subject_sqft), y(subject_price), 10
    o.append(f'<g><title>{esc(subject_address.title())}: {L("tip_asking")} ${int(subject_price):,}</title>'
             f'<path d="M{sx:.1f},{sy - d:.1f} L{sx + d:.1f},{sy:.1f} L{sx:.1f},{sy + d:.1f} L{sx - d:.1f},{sy:.1f} Z" class="subj"/></g>')
    o.append(_label(sx, sy, sc.get("subject_label_pos", "left"), sc.get("subject_label", subject_address.title()), "lbl-subj", 14))
    points = {}
    for h in sold:
        points[" ".join(h["address"].upper().split())] = (h["living_area"], h["close_price"])
    for h in act:
        points.setdefault(" ".join(h["address"].upper().split()), (h["living_area"], h["current_price"]))
    for co in sc.get("callouts", []):
        p = points.get(" ".join(co["address"].upper().split()))
        if not p:
            continue
        o.append(_label(x(p[0]), y(p[1]), co.get("side", "right"), co["label"], "lbl", 10))
    o.append("</svg>")
    info = {"trend_at_subject": fit["at_subject"] if fit else None, "r2": fit["r2"] if fit else None,
            "excluded": excluded, "n_sold": len(sold), "n_active": len(act),
            "counts": {**{kind: len(hs) for kind, hs in pts.items()}, "trend": 1 if fit else 0}}
    return "\n".join(o), info


def _label(px, py, side, text, cls, gap):
    """A chart label beside a point: side is left, right, above or below."""
    if side in ("above", "below"):
        ty = py - gap - 2 if side == "above" else py + gap + 10
        return f'<text x="{px:.1f}" y="{ty:.1f}" text-anchor="middle" class="{cls}">{esc(text)}</text>'
    left = side == "left"
    return (f'<text x="{px - gap if left else px + gap:.1f}" y="{py + 4:.1f}" text-anchor="{"end" if left else "start"}" '
            f'class="{cls}">{esc(text)}</text>')


def scatter_legend(L, subject, counts):
    """Only the entries with something on the chart: `counts` is scatter()'s info["counts"]."""
    entries = [
        ("comp", '<circle cx="7" cy="7" r="5.5" class="m-comp"/>'),
        ("sold", '<rect x="2" y="2" width="10" height="10" class="m-sold"/>'),
        ("active", '<circle cx="7" cy="7" r="5.5" class="m-active hol"/>'),
        ("trend", '<line x1="0" y1="7" x2="14" y2="7" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>'),
    ]
    spans = [f'<span><svg viewBox="0 0 14 14">{mark}</svg>{L("lg_" + kind)}</span>' for kind, mark in entries if counts.get(kind)]
    spans.append(f'<span><svg viewBox="0 0 14 14"><path d="M7,1 L13,7 L7,13 L1,7 Z" fill="var(--subject)"/></svg>'
                 f'{L("lg_subject", subject=esc(subject))}</span>')
    return '<div class="legend">' + "".join(spans) + "</div>"


def trend_position(price, at_subject):
    """Where the subject's price sits against the size-only line: ('above' | 'below' | 'at', gap in dollars).
    Within 1% of the price (at least $5,000) counts as at the line."""
    gap = price - at_subject
    if abs(gap) < max(5000, price * 0.01):
        return "at", 0
    return ("above" if gap > 0 else "below"), abs(gap)


_TREND_ICON_Y = {"above": 10.5, "below": 22.5, "at": 16.5}


def trend_caption(info, price, L):
    """The chart's takeaway box: a headline with where the subject sits against the size-only line (and by how much),
    what the line means, and an icon that draws the same thing. The one chart element allowed a tint (see cma.css)."""
    if not info.get("trend_at_subject"):
        return ""
    side, gap = trend_position(price, info["trend_at_subject"])
    values = {"price": finance.money(price), "gap": finance.money(gap, 1000)}
    cy = _TREND_ICON_Y[side]
    icon = ('<svg class="cr-icon" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="16" class="cr-disc"/>'
            '<line x1="6" y1="21.5" x2="26" y2="11.5" class="cr-line"/>'
            f'<path d="M16,{cy - 4} L20,{cy} L16,{cy + 4} L12,{cy} Z" class="cr-subj"/></svg>')
    body = " ".join(t for t in (L("trend_caption"), L("trend_" + side, **values)) if t)
    return (f'<div class="chart-read">{icon}<div><p class="cr-head">{L("trend_head_" + side, **values)}</p>'
            f'<p class="cr-body">{body}</p></div></div>')


def excluded_note(excluded, L):
    """One line with the count only: which homes were left off doesn't matter to the reader, just that some were."""
    if not excluded:
        return ""
    text = L("excluded_one") if len(excluded) == 1 else L("excluded_many", n=len(excluded))
    return f'<p class="note">{text}</p>'


# --- dot plot (page 1) ---------------------------------------------------------

def dotplot(cards, low, high, marker_price, marker_label, second=None):
    """Adjusted comps against the supported range, with the asking (or list) price marked."""
    cs = sorted(cards, key=lambda c: -c["adjusted"])
    vals = [c["adjusted"] for c in cs] + [low, high, marker_price] + ([second[0]] if second else [])
    step = nice_step(max(vals) - min(vals) + 16000, 6)
    lo, hi = math.floor((min(vals) - 8000) / step) * step, math.ceil((max(vals) + 8000) / step) * step
    W, Lm, R, T = 730, 190, 20, 26
    row = 21 if len(cs) <= 5 else 18  # six comps: tighter rows, same label size
    H = T + row * len(cs) + 26

    def x(v):
        return Lm + (v - lo) / (hi - lo) * (W - Lm - R)

    o = [f'<svg viewBox="0 0 {W} {H}" role="img">',
         f'<rect x="{x(low):.1f}" y="{T - 8}" width="{x(high) - x(low):.1f}" height="{row * len(cs) + 8}" class="dp-band"/>']
    for v in _ticks(lo, hi, step):
        o.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T - 8}" y2="{T + row * len(cs)}" class="dp-grid"/>'
                 f'<text x="{x(v):.1f}" y="{H - 6}" text-anchor="middle" class="dp-tick">{k(v)}</text>')
    xm = x(marker_price)
    xs = x(second[0]) if second is not None else None
    # CMA-23: labels never sit on each other or run off the chart. Two close markers put their labels on opposite
    # sides; a label near an edge anchors inward.
    if xs is not None and abs(xm - xs) < 140:
        m_pos, s_pos = ("start", "end") if xm >= xs else ("end", "start")
    else:
        m_pos = "start" if xm < Lm + 70 else "end" if xm > W - R - 70 else "middle"
        s_pos = "end" if xs is None or xs > Lm + 110 else "start"
    shift = {"start": 5, "end": -5, "middle": 0}
    o.append(f'<line x1="{xm:.1f}" x2="{xm:.1f}" y1="{T - 14}" y2="{T + row * len(cs) + 2}" class="dp-mark"/>'
             f'<text x="{xm + shift[m_pos]:.1f}" y="{T - 16}" text-anchor="{m_pos}" class="dp-mark-lbl">{esc(marker_label)}</text>')
    if xs is not None:
        o.append(f'<line x1="{xs:.1f}" x2="{xs:.1f}" y1="{T - 8}" y2="{T + row * len(cs) + 2}" class="dp-second"/>'
                 f'<text x="{xs + shift[s_pos]:.1f}" y="{T - 16}" text-anchor="{s_pos}" class="dp-second-lbl">{esc(second[1])}</text>')
    for i, c in enumerate(cs):
        cy = T + i * row + row / 2 - 4
        o.append(f'<text x="0" y="{cy + 4:.1f}" class="dp-addr">{esc(c["address"])}</text>'
                 f'<circle cx="{x(c["adjusted"]):.1f}" cy="{cy:.1f}" r="6" class="dp-dot"/>'
                 f'<text x="{x(c["adjusted"]) + 10:.1f}" y="{cy + 4:.1f}" class="dp-val">{k(c["adjusted"])}</text>')
    o.append("</svg>")
    return "".join(o)


# --- keep-together groups and pagination -------------------------------------

FIGURES = ("tbl", "chart-box", "comps2", "verdict", "facts")
_TAG = re.compile(r"\s*<(\w+)([^>]*)>")


def _tag(el):
    m = _TAG.match(el)
    if not m:
        return None, set()
    cls = re.search(r'class="([^"]*)"', m.group(2))
    return m.group(1), set(cls.group(1).split()) if cls else set()


def group_blocks(elements):
    """Wrap each heading with its intro paragraphs and following figure (and notes) in a keep-together div.

    `elements` is the report body as a list of top-level HTML strings. Mirrors the prototype's rules:
    a heading keeps up to three paragraphs and one figure; a paragraph directly before a figure stays with it.
    """
    info = [(_tag(e), e) for e in elements]

    def is_fig(i):
        (tag, cls), _ = info[i]
        return tag in ("ul", "ol", "footer") or (tag == "div" and bool(cls & set(FIGURES)))

    def is_note(i):
        (tag, cls), _ = info[i]
        return (tag == "p" and "note" in cls) or (tag == "div" and "chart-read" in cls)

    out, i = [], 0
    while i < len(info):
        (tag, _), _ = info[i]
        group, j = [i], i + 1
        if tag in ("h2", "h3"):
            while j < len(info) and info[j][0][0] == "h3":
                group.append(j); j += 1
            n = 0
            while j < len(info) and info[j][0][0] == "p" and n < 3:
                group.append(j); j += 1; n += 1
            if j < len(info) and is_fig(j):
                group.append(j); j += 1
                while j < len(info) and is_note(j):
                    group.append(j); j += 1
        elif tag == "p" and j < len(info) and is_fig(j):
            group.append(j); j += 1
            while j < len(info) and is_note(j):
                group.append(j); j += 1
        elif is_fig(i):
            while j < len(info) and is_note(j):
                group.append(j); j += 1
        html_parts = [info[g][1] for g in group]
        if len(group) > 1 or is_fig(i):
            out.append(f'<div class="kg{" sec" if tag == "h2" else ""}">' + "".join(html_parts) + "</div>")
        elif tag == "h2":
            out.append(re.sub(r"^\s*<h2", '<h2 class="sec"', html_parts[0], count=1))
        else:
            out.append(html_parts[0])
        i = j
    return "".join(out)


PAGINATE_JS = """(pageH) => {
  // Page 1 fits itself: tighten in steps (fit1 → fit3, cumulative) until it clears the page with a small margin.
  const one = document.querySelector('.onepage'); let fit = 0;
  while (one && fit < 3 && one.getBoundingClientRect().height > pageH - 16) one.classList.add('fit' + (++fit));
  const wrap = document.querySelector('.wrap');
  const base = wrap.getBoundingClientRect().top;
  let shift = 0; const moved = [];
  for (const el of Array.from(wrap.children)) {
    const r = el.getBoundingClientRect();
    const mt = parseFloat(getComputedStyle(el).marginTop) || 0;
    const t = r.top - base - mt + shift, h = r.height + mt;
    const pos = ((t % pageH) + pageH) % pageH;
    if (el.classList.contains('onepage')) window.__onepageH = h;
    if (el.classList.contains('pb')) { if (pos > 5) shift += pageH - pos; continue; }
    const isKeep = el.classList.contains('kg');
    if (isKeep && h > 0.8 * pageH) el.classList.add('big');
    const keepOK = isKeep && !el.classList.contains('big');
    if (el.classList.contains('big')) {
      const rows = {};
      el.querySelectorAll('.comp').forEach(c => { const cr = c.getBoundingClientRect(); const k = Math.round(cr.top);
        rows[k] = Math.max(rows[k] || 0, cr.height); });
      Object.keys(rows).map(Number).sort((a, b) => a - b).forEach(top => {
        const tt = top - base + shift, pp = ((tt % pageH) + pageH) % pageH;
        if (pp > 5 && pp + rows[top] > pageH) shift += pageH - pp;
      });
      continue;
    }
    let brk = false;
    if (pos > 5 && el.classList.contains('sec') && pos > 0.75 * pageH) brk = true;
    else if (pos > 5 && keepOK && pos + h > pageH) brk = true;
    if (brk) { el.classList.add('pb'); shift += pageH - pos; moved.push((el.innerText || '').split('\\n')[0].slice(0, 50)); }
  }
  return { moved, onepageH: window.__onepageH || 0, pageH, fit };
}"""

PAGE_MARGINS = {"top": "0.45in", "right": "0.45in", "bottom": "0.55in", "left": "0.45in"}
CONTENT_HEIGHT_PX = 10 * 96  # 11in − 0.45in − 0.55in


def paginate(pg):
    """Before printing: fit page 1 on one page (fit_level 0-3), then move groups so none splits
    and no section starts in the bottom quarter of a page."""
    pg.set_viewport_size({"width": 730, "height": 1000})  # 8.5in − 2 × 0.45in
    res = pg.evaluate(PAGINATE_JS, CONTENT_HEIGHT_PX)
    return {"moved": res["moved"], "summary_page": {"height_px": round(res["onepageH"]), "page_px": res["pageH"],
                                                    "fits": res["onepageH"] <= res["pageH"], "fit_level": res["fit"]}}


def derive_comps(comps):
    """Adjusted comp values from their parts, so the script does the math (CMA-2). Returns warnings.

    Itemized cards (`sold_price`, optional `seller_concessions`, `adjustments: [{label, amount}]`): the adjusted value
    is sale price minus seller concessions plus the adjustments, written to `card["adjusted"]`, and `summary_rows` is
    built from the cards (highest adjusted first). Warns when adjustments pass 15% net or 25% gross of the sale price.
    Older reports that type `adjusted` and `summary_rows` by hand must agree card by card, or it's an error.
    Raises ValueError with a message for the agent.
    """
    cards = comps.get("cards") or []
    itemized = [c for c in cards if "adjustments" in c]
    if itemized and len(itemized) != len(cards):
        raise ValueError("Give every comp card sold_price and adjustments, or none of them: "
                         + ", ".join(c.get("address", "?") for c in cards if "adjustments" not in c) + " has none.")
    warnings = []
    if not itemized:
        rows = {r[0]: r for r in comps.get("summary_rows") or []}
        for c in cards:
            r = rows.get(c.get("address"))
            if r is None:
                raise ValueError(f"Comp card {c.get('address')!r} has no summary row: add it, or itemize the comps "
                                 "(sold_price, seller_concessions, adjustments) and let the script build the rows.")
            if round(r[3]) != round(c["adjusted"]):
                raise ValueError(f"{c['address']}: the card's adjusted value {money(c['adjusted'])} and the summary row's "
                                 f"{money(r[3])} differ. Itemize the comps so the script computes one value for both.")
        if len(rows) != len(cards):
            raise ValueError("summary_rows lists a sale that has no comp card.")
        return warnings
    out = []
    for c in cards:
        where = c.get("address", "?")
        sold, conc = c.get("sold_price"), c.get("seller_concessions") or 0
        amounts = [a.get("amount") for a in c["adjustments"]]
        if not isinstance(sold, (int, float)) or sold <= 0 or not isinstance(conc, (int, float)) \
                or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in amounts):
            raise ValueError(f"{where}: sold_price, seller_concessions and every adjustment amount must be plain numbers.")
        value = round(sold - conc + sum(amounts))
        if c.get("adjusted") is not None and round(c["adjusted"]) != value:
            warnings.append(f"{where}: the typed adjusted value {money(c['adjusted'])} was replaced by the computed {money(value)}.")
        c["adjusted"] = value
        net, gross = abs(sum(amounts)) / sold, sum(abs(x) for x in amounts) / sold
        if net > ADJ_NET_LIMIT or gross > ADJ_GROSS_LIMIT:
            warnings.append(f"{where}: adjustments are {net:.0%} net and {gross:.0%} gross of the sale price (appraisal "
                            "guidelines are about 15% net and 25% gross). Check that it's a true comp, or explain it in the report.")
        out.append([where, sold, conc, value])
    comps["summary_rows"] = sorted(out, key=lambda r: -r[3])
    return warnings


def report_notices(C):
    """The CMA's fixed closing notices (CMA-16): where the sales data came from and as of when, that a CMA isn't an
    appraisal or for lending, and that payment and tax figures are estimates."""
    src = C.get("data_source") or {}
    when = src.get("as_of") or ""
    lines = [f"Sales data: {src['mls']} MLS as of {when}. Deemed reliable but not guaranteed." if src.get("mls") and src.get("export")
             else f"Sales data as of {when}, from the sources named in the report. Deemed reliable but not guaranteed."]
    lines.append("This comparative market analysis is an opinion of price, not an appraisal, and isn't for lending purposes.")
    lines.append("Payment, tax and cost figures are estimates only, not lending or tax advice.")
    return lines

