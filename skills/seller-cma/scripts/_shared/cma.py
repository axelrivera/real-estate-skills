"""Report pieces shared by the buyer and seller CMAs: the page-1 heading, charts (scatter, dot plot), comps math (adjusted
values, time adjustments, the range rules) and the closing notices. The page fit lives in layout.py.

All visible text comes from the skill's labels file (assets/labels.json), passed in as a label lookup. Colors are theme
variables (shared/cma.css), never hard-coded. Figures print through fmt.
"""
import html
import math
import os
import re
import statistics
from datetime import date, timedelta

from . import finance, fmt, layout, mls, render

CMA_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cma.css")
money = finance.money
ADJ_NET_LIMIT, ADJ_GROSS_LIMIT = 0.15, 0.25  # common appraisal guidelines, as shares of the comp's sale price
OUTLIER_SHARE = 0.10  # CMA-110: an adjusted value this far from the other comps' median is an outlier (method.md)
LABEL_GAP = 3  # px kept clear between two chart labels on the seller CMA's scatter, so stacked labels never touch
esc = html.escape


def css():
    with open(CMA_CSS, encoding="utf-8") as f:
        return f.read()


# --- page 1 -------------------------------------------------------------------

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


# --- scatterplot ---------------------------------------------------------------

_KEEP_UPPER = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "US", "SR", "CR", "PO"}
_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)([,.]?)$")


def display_address(address):
    """CMA-233: an address as the report prints it. An all-caps export address ("436 SUMMIT DR") reads in title case
    ("436 Summit Dr"), with directions and road prefixes kept upper case (NE, SR), ordinals as "1st", unit codes with a
    digit ("#4A", "12B") and state codes after a comma as typed. An address with any lower-case letter was written for
    display and is left alone. Matching to the export (scatter, comp cards) uses _street(), which ignores case."""
    text = str(address)
    if any(ch.islower() for ch in text):
        return text
    out, after_comma = [], False
    for word in text.split(" "):
        bare = word.rstrip(",.")
        m = _ORDINAL.match(word)
        if m:
            word = m.group(1) + m.group(2).lower() + m.group(3)
        elif bare in _KEEP_UPPER or any(ch.isdigit() for ch in bare) or (after_comma and len(bare) == 2 and bare.isalpha()):
            pass
        else:
            word = re.sub(r"[A-Z]+", lambda p: p.group(0).capitalize(), word)
        after_comma = after_comma or word.endswith(",")
        out.append(word)
    return " ".join(out)


def _street(address):
    """Match key for an address: the part before the first comma, upper case, spaces collapsed."""
    return " ".join(str(address).split(",")[0].upper().split())


def scatter_points(homes, sc, subject_sqft, subject_address, comps=()):
    """The chart's points and trend line, shared by the PDF and the deck so they always match (CMA-24): sold homes used
    as comps (`comp`, matched by the comp cards' addresses), other sales (`sold`), and every active listing (`active`).
    Homes far larger or smaller than the subject, and sales or listings priced far off the trend (mls.price_outlier;
    listings only when wildly off), are left off; comps always stay. Returns ({kind: [homes]}, excluded [(address, sqft, 'sale'|'listing',
    'size'|'price')], trend fit or None)."""
    comp_keys = {_street(a) for a in comps}
    lo, hi = subject_sqft * sc.get("min_size_ratio", 0.6), subject_sqft * sc.get("max_size_ratio", 1.4)
    others = [h for h in homes if not mls.same_address(h["address"], subject_address)]
    fit = mls.trend(others, subject_sqft, sc.get("fit_size_ratio", 1.6))
    pts, excluded = {"comp": [], "sold": [], "active": []}, []
    for h in others:
        sold = h["status"] == "SOLD" and h.get("close_price")
        active = h["status"] == "ACTIVE" and h.get("current_price")
        if not h.get("living_area") or not (sold or active):
            continue
        kind = "active" if active else "comp" if _street(h["address"]) in comp_keys else "sold"
        price = h["current_price"] if active else h["close_price"]
        if not lo <= h["living_area"] <= hi:
            reason = "size"
        elif kind != "comp" and mls.price_outlier(fit, h["living_area"], price, listing=bool(active)):
            reason = "price"
        else:
            pts[kind].append(h)
            continue
        excluded.append((h["address"], int(h["living_area"]), "listing" if active else "sale", reason))
    excluded.sort(key=lambda e: e[2] != "sale")  # sales first, then listings
    return pts, excluded, fit


def scatter(homes, sc, subject_sqft, subject_price, subject_address, band, L, comps=(), drop_crowded=False, points=None,
            chart=None, band_label=None, kfmt=None, size=(760, 470), activity=False):
    """Price vs. size for sold and active homes near the subject's size, with the supported range band.

    `comps`: the comp cards' addresses, drawn as comparable sales. `drop_crowded` (the seller CMA): labels stay
    LABEL_GAP apart, and a callout with no clear spot, even on a leader line, is left off (listed in `labels_dropped`)
    instead of printed over a marker or another label.
    `sc`: {callouts: [{address, label, side}], subject_label, subject_label_pos, min/max/fit_size_ratio}.
    Label sides: left, right, above or below.
    Returns (svg, info) where info has trend_at_subject, r2, excluded [(address, sqft, kind, reason)], n_sold, n_active,
    counts {kind: n} of what was drawn, and callouts_dropped for callouts whose home isn't on the chart.
    `points`: scatter_points' result, computed once by the caller's document model (the trend it states is the one
    drawn). `chart`: a layout.Chart, marked with each series as it's drawn, so its legend names only what's on the chart.
    `band_label`: the range band's text as the caller formats it; `kfmt`: the tick formatter (cma.k by default).
    `size`: the drawing's (width, height) in px; text and markers keep their size, only the plot area grows.
    `activity` (the Pricing Activity sheet, shown before the value conversation): the area's sales and listings only.
    No price for the home, no range band, no comp highlights and no callouts; the home appears only as a line at its
    size (labeled L("lg_size_line")), and the price axis is scaled to the other homes alone.
    """
    kf = kfmt or fmt.k
    pts, excluded, fit = points or scatter_points(homes, sc, subject_sqft, subject_address, comps)
    if activity:  # comps are drawn as ordinary sales: highlighting them would preview the CMA
        pts = {"comp": [], "sold": pts["comp"] + pts["sold"], "active": pts["active"]}
    sold, act = pts["comp"] + pts["sold"], pts["active"]
    kind = {id(h): k for k, hs in pts.items() for h in hs}

    def cat(h):
        return kind[id(h)]

    xs = [h["living_area"] for h in sold + act] + [subject_sqft]
    ys = [h["close_price"] for h in sold] + [h["current_price"] for h in act]
    if not activity:
        ys += [subject_price, band[0], band[1]]
    W, H = size
    Lm, R, T, B = 72, 20, 20, 58
    ticks = 8 if W <= 760 else 10  # a wider drawing keeps its grid as dense
    X0, X1 = math.floor((min(xs) - 50) / 100) * 100, math.ceil((max(xs) + 50) / 100) * 100
    ystep = nice_step(max(ys) - min(ys) + 30000, ticks)
    Y0, Y1 = math.floor((min(ys) - 15000) / ystep) * ystep, math.ceil((max(ys) + 15000) / ystep) * ystep

    def x(v):
        return Lm + (v - X0) / (X1 - X0) * (W - Lm - R)

    def y(v):
        return T + (Y1 - v) / (Y1 - Y0) * (H - T - B)

    def shape(kind, cx, cy, hollow, tip):
        # other sales are the background: small, see-through dots, so overlapping sales read as a denser patch
        cls, r = f"m-{kind}" + (" hol" if hollow else ""), {"sold": 4, "sales": 5}.get(kind, 6.5)
        return f'<g><title>{esc(tip)}</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" class="{cls}"/></g>'

    o = [f'<svg viewBox="0 0 {W} {H}" role="img" class="scatter" aria-label="{esc(L("axis_y"))} / {esc(L("axis_x"))}">']
    if not activity:
        o.append(f'<rect x="{Lm}" y="{y(band[1]):.1f}" width="{W - Lm - R}" height="{y(band[0]) - y(band[1]):.1f}" class="band"/>')
    for v in _ticks(Y0, Y1, ystep):
        o.append(f'<line x1="{Lm}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                 f'<text x="{Lm - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="tick">{kf(v)}</text>')
    step = nice_step(X1 - X0, ticks)
    for v in _ticks(math.ceil(X0 / step) * step, X1, step):
        o.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{H - B}" class="grid"/>'
                 f'<text x="{x(v):.1f}" y="{H - B + 18}" text-anchor="middle" class="tick">{v:,}</text>')
    o.append(f'<text x="{(Lm + W - R) / 2}" y="{H - 12}" text-anchor="middle" class="axis">{esc(L("axis_x"))}</text>')
    o.append(f'<text transform="translate(16,{(T + H - B) / 2}) rotate(-90)" text-anchor="middle" class="axis">{esc(L("axis_y"))}</text>')
    if fit:
        xa, xb = X0 + 50, X1 - 50
        o.append(f'<line x1="{x(xa):.1f}" y1="{y(fit["intercept"] + fit["slope"] * xa):.1f}" '
                 f'x2="{x(xb):.1f}" y2="{y(fit["intercept"] + fit["slope"] * xb):.1f}" class="trend"/>')
        _mark(chart, "trend", L)
    def sale(h):
        kind = "sales" if activity else cat(h)  # on the activity sheet the sales are the subject: darker, larger dots
        _mark(chart, kind, L)
        o.append(shape(kind, x(h["living_area"]), y(h["close_price"]), False,
                       f'{display_address(h["address"])}: {L("tip_sold")} ${int(h["close_price"]):,}, {int(h["living_area"]):,} sq ft'))

    under = len(o)  # the activity sheet's size line goes here, under the markers
    for h in pts["sold"]:  # background first, comps and the subject on top
        sale(h)
    for h in act:
        _mark(chart, "active", L)
        o.append(shape("active", x(h["living_area"]), y(h["current_price"]), True,
                       f'{display_address(h["address"])}: {L("tip_active")} ${int(h["current_price"]):,}, {int(h["living_area"]):,} sq ft'))
    for h in pts["comp"]:
        sale(h)
    if activity:
        info = _size_line(o, under, chart, L, x(subject_sqft), subject_sqft, (Lm, T, W - R, H - B), sold, act, x, y)
    else:
        info = _priced(o, chart, L, homes, sc, subject_sqft, subject_price, subject_address, band, band_label, excluded,
                       sold, act, cat, x, y, (Lm, T, W - R, H - B), drop_crowded)
    o.append("</svg>")
    placer, dropped_callouts = info
    info = {"trend_at_subject": fit["at_subject"] if fit else None, "r2": fit["r2"] if fit else None,
            "excluded": excluded, "n_sold": len(sold), "n_active": len(act),
            "counts": {**{kind: len(hs) for kind, hs in pts.items()}, "trend": 1 if fit else 0},
            "labels_moved": placer.moved, "labels_overlapping": placer.overlapping,
            "labels_leader": placer.leaders, "labels_dropped": placer.dropped,  # CMA-218
            "crowded_labels": placer.clashing, "callouts_dropped": dropped_callouts}  # CMA-299
    return "\n".join(o), info


def _priced(o, chart, L, homes, sc, subject_sqft, subject_price, subject_address, band, band_label, excluded, sold, act,
            cat, x, y, bounds, drop_crowded):
    """The report's marks on top of the activity: the home at its price, the range band's label and the callouts.
    Returns (label placer, callouts whose home isn't on the chart)."""
    sx, sy, d = x(subject_sqft), y(subject_price), 10
    o.append(f'<g><title>{esc(display_address(subject_address))}: {L("tip_asking")} ${int(subject_price):,}</title>'
             f'<path d="M{sx:.1f},{sy - d:.1f} L{sx + d:.1f},{sy:.1f} L{sx:.1f},{sy + d:.1f} L{sx - d:.1f},{sy:.1f} Z" class="subj"/></g>')
    if chart is not None:
        chart.mark("subject", L("lg_subject", subject=sc.get("subject_label", display_address(subject_address))),
                   LEGEND_SWATCHES["subject"])
    # CMA-205, CMA-253: labels step aside from the markers (and each other) instead of printing over them; the band's
    # label goes in the first corner clear of markers
    marks = [(x(h["living_area"]), y(h["close_price"]), 4 if cat(h) == "sold" else 6.5) for h in sold]
    marks += [(x(h["living_area"]), y(h["current_price"]), 6.5) for h in act] + [(sx, sy, d)]
    placer = _LabelPlacer(marks, bounds, gap=LABEL_GAP if drop_crowded else 0)
    band_text = band_label or f'{L("band")} {fmt.range(band[0], band[1], fmt.k)}'
    band_w = _text_w(band_text, 12, bold=True)
    spots = [(bx, by, anchor, (bx if anchor == "start" else bx - band_w, by - 10, (bx if anchor == "start" else bx - band_w) + band_w, by + 3))
             for by in (y(band[1]) - 6, y(band[0]) + 15) for bx, anchor in ((bounds[0] + 8, "start"), (bounds[2] - 8, "end"))]
    bx, by, anchor, box = next((sp for sp in spots if not _hits(sp[3], marks, [])), spots[0])
    placer.boxes.append(box)
    o.append(_halo(f'<text x="{bx:.1f}" y="{by:.1f}" text-anchor="{anchor}" class="lbl-band">{esc(band_text)}</text>'))
    o.append(placer.place(sx, sy, sc.get("subject_label_pos", "left"), sc.get("subject_label", display_address(subject_address)),
                          "lbl-subj", 14, 13, bold=True, droppable=True))
    points = {}
    for h in sold:
        points[" ".join(h["address"].upper().split())] = (h["living_area"], h["close_price"])
    for h in act:
        points.setdefault(" ".join(h["address"].upper().split()), (h["living_area"], h["current_price"]))
    # CMA-299: a callout whose home isn't on the chart is reported with why, never dropped silently
    off = {" ".join(e[0].upper().split()): e[3] for e in excluded}  # left off for size or price
    status = {}
    for h in homes:
        status.setdefault(" ".join(str(h["address"]).upper().split()), str(h.get("status") or "").lower())
    dropped_callouts = []
    for co in sc.get("callouts", []):
        key = " ".join(co["address"].upper().split())
        p = points.get(key)
        if not p:  # (label, address, reason: size, price, the home's status such as pending, or not_in_export)
            dropped_callouts.append((co.get("label") or co["address"], co["address"],
                                     off.get(key) or status.get(key) or "not_in_export"))
            continue
        o.append(placer.place(x(p[0]), y(p[1]), co.get("side", "right"), co["label"], "lbl", 10, 12, droppable=drop_crowded))
    return placer, dropped_callouts


def _size_line(o, under, chart, L, sx, sqft, bounds, sold, act, x, y):
    """The Pricing Activity sheet's only mark for the home: a line at its size, no price. Its label sits at the top,
    stepped aside from the markers. Returns (label placer, no dropped callouts)."""
    marks = [(x(h["living_area"]), y(h["close_price"]), 5) for h in sold]
    marks += [(x(h["living_area"]), y(h["current_price"]), 6.5) for h in act]
    o.insert(under, f'<line x1="{sx:.1f}" x2="{sx:.1f}" y1="{bounds[1]}" y2="{bounds[3]}" class="size-line"/>')
    text = L("lg_size_line", sqft=f"{int(sqft):,}")
    if chart is not None:
        chart.mark("size_line", text, LEGEND_SWATCHES["size_line"])
    placer = _LabelPlacer(marks, bounds)
    side = "right" if sx < (bounds[0] + bounds[2]) / 2 else "left"
    o.append(placer.place(sx, bounds[1] + 12, side, text, "lbl-subj", 6, 13, bold=True, droppable=True))
    return placer, []


def _text_w(text, size, bold=False):
    """How wide a chart label draws: measured with the bundled font's metrics (layout.text_width), plus room for the
    wider fallback fonts a report that hasn't switched the bundled font on may print with (Results_v5: a band label
    measured for Helvetica ran into a marker). Every label box on a chart is measured here."""
    return layout.text_width(text, size, bold) * FONT_SLACK


FONT_SLACK = 1.15


def _halo(svg_text):
    """A label drawn twice: first a background-colored copy with a thick outline, then the label itself with no outline.
    One outlined copy (paint-order: stroke) smeared in viewers that ignore paint-order or draw the outline in the text's
    color (Results_v5 case 02); a separate copy whose fill and outline are both the background reads in every viewer."""
    under = svg_text.replace('class="', 'aria-hidden="true" class="halo ', 1)
    return under + svg_text


def _hits(box, marks, boxes, count=False):
    """Whether `box` covers a marker (cx, cy, r) or overlaps another label's box; with `count`, how many it does
    (a label counts as three markers)."""
    x0, y0, x1, y1 = box
    n = sum((min(max(cx, x0), x1) - cx) ** 2 + (min(max(cy, y0), y1) - cy) ** 2 < r * r for cx, cy, r in marks)
    n += 3 * sum(x0 < b[2] and b[0] < x1 and y0 < b[3] and b[1] < y1 for b in boxes)
    return n if count else n > 0


SIDES = ("left", "right", "above", "below")


class _LabelPlacer:
    """CMA-205: puts each chart label on the requested side of its point unless the label's box would cover a marker,
    another label or the plot's edge; then on the side (nudged up or down a line beside the point) that covers the
    least. Covering a comp, a listing, the subject or another label counts; grazing a small background sale dot
    counts less and isn't reported. `moved` lists (label, asked, used) and `overlapping` the labels that still cover
    something that counts, so the render can say so, and `clashing` the ones that overlap another label."""

    NUDGES = (0, -10, 10)  # a left or right label may sit a line higher or lower beside its point
    # CMA-218: when no side beside the point is clear, the label may sit farther off with a thin line back to it
    LEADER_STEPS = (28, 42, 58)
    LEADER_DIRS = ((1, 0), (-1, 0), (0, -1), (0, 1), (1, -1), (-1, -1), (1, 1), (-1, 1))

    def __init__(self, marks, bounds, gap=0):
        self.marks, self.bounds, self.boxes, self.moved, self.overlapping, self.clashing = marks, bounds, [], [], [], []
        self.leaders, self.dropped = [], []
        self.gap = gap  # px kept clear between two labels (the seller CMA: 3, so stacked labels never touch)

    @staticmethod
    def box(px, py, side, text, gap, size, bold=False):
        w, h = _text_w(text, size, bold), size  # the same measure as every other chart label (FONT_SLACK included)
        if side in ("above", "below"):
            base = py - gap - 2 if side == "above" else py + gap + 10
            return px - w / 2, base - 0.8 * h, px + w / 2, base + 0.2 * h
        x0 = px - gap - w if side == "left" else px + gap
        return x0, py + 4 - 0.8 * h, x0 + w, py + 4 + 0.2 * h

    def touch(self, b, o):
        """Whether two label boxes overlap or come closer than the placer's gap."""
        g = self.gap
        return b[0] - g < o[2] and o[0] < b[2] + g and b[1] - g < o[3] and o[1] < b[3] + g

    def hits(self, b, own):
        """(what the box covers that counts, background dots it grazes)."""
        x0, y0, x1, y1 = b
        covered = [r for cx, cy, r in self.marks if (cx, cy) != own and
                   (max(x0, min(cx, x1)) - cx) ** 2 + (max(y0, min(cy, y1)) - cy) ** 2 < r * r]
        big = sum(1 for r in covered if r >= 6) + sum(1 for o in self.boxes if self.touch(b, o))
        bx0, by0, bx1, by1 = self.bounds
        big += 2 * (x0 < bx0 - 4 or x1 > bx1 + 4 or y0 < by0 - 4 or y1 > by1 + 4)
        return big, len(covered) - sum(1 for r in covered if r >= 6)

    def _line_hits(self, px, py, ax, ay):
        """Markers that count (comps, listings, the subject) the leader line from (px, py) to (ax, ay) runs through."""
        vx, vy = ax - px, ay - py
        n = 0
        for cx, cy, r in self.marks:
            if r < 6 or (cx, cy) == (px, py):
                continue
            t = max(0.0, min(1.0, ((cx - px) * vx + (cy - py) * vy) / (vx * vx + vy * vy)))
            n += (px + t * vx - cx) ** 2 + (py + t * vy - cy) ** 2 < r * r
        return n

    def leader(self, px, py, text, gap, size, bold=False):
        """(anchor x, anchor y, side, box) for a label set farther off its point, clear of everything that counts, or
        None. The nearest clear spot wins, then the one grazing the fewest background dots."""
        best = None
        for step, dist in enumerate(self.LEADER_STEPS):
            for i, (dx, dy) in enumerate(self.LEADER_DIRS):
                k = dist / math.hypot(dx, dy)
                ax, ay = px + dx * k, py + dy * k
                side = "right" if dx > 0 else "left" if dx < 0 else "above" if dy < 0 else "below"
                b = self.box(ax, ay, side, text, 3, size, bold)
                big, small = self.hits(b, (px, py))
                big += self._line_hits(px, py, ax, ay)
                if not big and (best is None or (step, small, i) < best[0]):
                    best = ((step, small, i), (ax, ay, side, b))
            if best:
                return best[1]
        return None

    def place(self, px, py, side, text, cls, gap, size, bold=False, droppable=False):
        """The label's SVG. With `droppable` (the subject, which the legend names), a label with no clear spot even
        on a leader line is left off and listed in `dropped`, rather than printed over a marker."""
        side = side if side in SIDES else "right"
        order = [side] + [s for s in SIDES if s != side]
        options = [(s, dy) for dy in self.NUDGES for s in order if dy == 0 or s in ("left", "right")]
        scored = []
        for i, (s, dy) in enumerate(options):
            big, small = self.hits(self.box(px, py + dy, s, text, gap, size, bold), (px, py))
            scored.append((big, small, i, s, dy))
        big, _, _, best, dy = min(scored)
        if big:  # CMA-218: nothing beside the point is clear; try farther off with a leader line, then drop the subject's
            lead = self.leader(px, py, text, gap, size, bold)
            if lead:
                ax, ay, lside, b = lead
                self.leaders.append((text, lside))
                self.boxes.append(b)
                d = math.hypot(ax - px, ay - py)
                ux, uy = (ax - px) / d, (ay - py) / d
                return (f'<line x1="{px + ux * 9:.1f}" y1="{py + uy * 9:.1f}" x2="{ax - ux * 2:.1f}" y2="{ay - uy * 2:.1f}" '
                        f'class="leader"/>' + _label(ax, ay, lside, text, cls, 3))
            if droppable:
                self.dropped.append(text)
                return ""
        if (best, dy) != (side, 0):
            self.moved.append((text, side, best + ("" if not dy else ", a line higher" if dy < 0 else ", a line lower")))
        if big:
            self.overlapping.append(text)
        b = self.box(px, py + dy, best, text, gap, size, bold)
        if any(self.touch(b, o) for o in self.boxes):
            self.clashing.append(text)
        self.boxes.append(b)
        return _label(px, py + dy, best, text, cls, gap)


def _label(px, py, side, text, cls, gap):
    """A chart label beside a point: side is left, right, above or below."""
    if side in ("above", "below"):
        ty = py - gap - 2 if side == "above" else py + gap + 10
        return _halo(f'<text x="{px:.1f}" y="{ty:.1f}" text-anchor="middle" class="{cls}">{esc(text)}</text>')
    left = side == "left"
    return _halo(f'<text x="{px - gap if left else px + gap:.1f}" y="{py + 4:.1f}" text-anchor="{"end" if left else "start"}" '
                 f'class="{cls}">{esc(text)}</text>')


LEGEND_SWATCHES = {
    "comp": '<circle cx="7" cy="7" r="5.5" class="m-comp"/>',
    "sold": '<circle cx="7" cy="7" r="4" class="m-sold"/>',
    "active": '<circle cx="7" cy="7" r="5.5" class="m-active hol"/>',
    "trend": '<line x1="0" y1="7" x2="14" y2="7" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>',
    "subject": '<path d="M7,1 L13,7 L7,13 L1,7 Z" fill="var(--subject)"/>',
    "sales": '<circle cx="7" cy="7" r="5" class="m-sales"/>',
    "size_line": '<line x1="7" y1="0" x2="7" y2="14" stroke="var(--subject)" stroke-width="1.5"/>',
}


def _mark(chart, kind, L):
    """Record one drawn mark of a series on a layout.Chart (its legend names only the series drawn)."""
    if chart is not None:
        chart.mark(kind, L("lg_" + kind), LEGEND_SWATCHES[kind])


def trend_position(price, at_subject):
    """Where the subject's price sits against the size-only line: ('above' | 'below' | 'at', gap in dollars).
    Within 1% of the price (at least $5,000) counts as at the line."""
    gap = price - at_subject
    if abs(gap) < max(5000, price * 0.01):
        return "at", 0
    return ("above" if gap > 0 else "below"), abs(gap)


# --- dot plot (page 1) ---------------------------------------------------------

DOT_ADDR_PX, DOT_ADDR_MIN, DOT_ADDR_MAX = 11.5, 190, 300  # the address column: its font size and width bounds


def dotplot(cards, low, high, marker_price, marker_label, second=None, kfmt=None):
    """Adjusted comps against the supported range, with the asking (or list) price marked. The address column is as
    wide as its longest address, measured (DOT_ADDR_MIN to DOT_ADDR_MAX); an address wider still is fitted to it.
    `kfmt` formats the values and ticks (cma.k by default)."""
    k_ = kfmt or fmt.k
    cs = sorted(cards, key=lambda c: -c["adjusted"])
    vals = [c["adjusted"] for c in cs] + [low, high, marker_price] + ([second[0]] if second else [])
    step = nice_step(max(vals) - min(vals) + 16000, 6)
    lo, hi = math.floor((min(vals) - 8000) / step) * step, math.ceil((max(vals) + 8000) / step) * step
    widths = [_text_w(display_address(c["address"]), DOT_ADDR_PX) for c in cs]
    W, R, T = 730, 20, 26
    Lm = min(max(DOT_ADDR_MIN, max(widths, default=0) + 14), DOT_ADDR_MAX)
    row = 21 if len(cs) <= 5 else 18  # six comps: tighter rows, same label size
    H = T + row * len(cs) + 26

    def x(v):
        return Lm + (v - lo) / (hi - lo) * (W - Lm - R)

    o = [f'<svg viewBox="0 0 {W} {H}" role="img">',
         f'<rect x="{x(low):.1f}" y="{T - 8}" width="{x(high) - x(low):.1f}" height="{row * len(cs) + 8}" class="dp-band"/>']
    for v in _ticks(lo, hi, step):
        o.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T - 8}" y2="{T + row * len(cs)}" class="dp-grid"/>'
                 f'<text x="{x(v):.1f}" y="{H - 6}" text-anchor="middle" class="dp-tick">{k_(v)}</text>')
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
    lines = [v for v in (xm, xs) if v is not None]
    for i, c in enumerate(cs):
        cy, cx, val = T + i * row + row / 2 - 4, x(c["adjusted"]), k_(c["adjusted"])
        w = _text_w(val, 12)
        squeeze = f' textLength="{Lm - 14:.0f}" lengthAdjust="spacingAndGlyphs"' if widths[i] > Lm - 14 else ""
        # CMA-253: a value label that a price line would strike through goes on the dot's left, when that side is clear
        left = (any(cx + 8 <= v <= cx + 12 + w for v in lines) and cx - 12 - w > Lm
                and not any(cx - 12 - w <= v <= cx - 8 for v in lines))
        anchor = ' text-anchor="end"' if left else ""
        o.append(f'<text x="0" y="{cy + 4:.1f}"{squeeze} class="dp-addr">{esc(display_address(c["address"]))}</text>'
                 f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" class="dp-dot"/>'
                 f'<text x="{cx - 10 if left else cx + 10:.1f}" y="{cy + 4:.1f}"{anchor} class="dp-val">{val}</text>')
    o.append("</svg>")
    return "".join(o)


# --- the page and the comps ------------------------------------------------------

# Keep-together groups live in layout.py (the one page-fit pipeline); the name stays here for older callers
group_blocks = layout.group_blocks
PAGE_MARGINS = {"top": "0.45in", "right": "0.45in", "bottom": "0.55in", "left": "0.45in"}  # every CMA's printed page

# --- the one-page chart sheet (Pricing Activity) ------------------------------------
# The scatter alone on a landscape Letter page: the title, the drawing as large as the page allows, the legend. No
# footer, so the bottom margin matches the others.
SHEET_FIT = layout.Fit(one_page=True, landscape=True, margins={k: "0.45in" for k in ("top", "right", "bottom", "left")})
SHEET_TITLE_PX, SHEET_LEGEND_PX = 46, 32  # the title line and the legend under the drawing, with their spacing
SHEET_SIZE = (SHEET_FIT.content_px()[0],
              SHEET_FIT.content_px()[1] - SHEET_TITLE_PX - SHEET_LEGEND_PX)


def chart_sheet(svg, legend, title, theme_css, tag="", body_class=""):
    """The one-page landscape chart sheet: `title`, the drawing (cma.scatter at SHEET_SIZE) at full width, `legend`
    (a layout.Chart legend). Nothing else: no intro, takeaway, notes or footer. `tag`: a small outlined tag after the
    title (the sample label)."""
    tag = f'<span class="sheet-tag">{esc(tag)}</span>' if tag else ""
    body = f'<div class="chart-sheet"><h1>{esc(title)}{tag}</h1>{svg}{legend}</div>'
    return render.page(body, css=css() + "@page{size:Letter landscape;margin:0.45in}", title=title,
                       theme_css=theme_css, body_class=layout.classes("font-bundled", body_class)
                       ).replace("<html>", '<html lang="en">', 1)


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


def outlier_warnings(cards, share=OUTLIER_SHARE):
    """CMA-110: comps whose adjusted value is more than `share` away from the median of the other comps, so the same
    comp set is always judged the same way (method.md, Outliers). Needs at least three comps."""
    values = [c.get("adjusted") for c in cards]
    if len(values) < 3 or not all(isinstance(v, (int, float)) for v in values):
        return []
    out = []
    for i, c in enumerate(cards):
        others = statistics.median(values[:i] + values[i + 1:])
        if abs(values[i] - others) > share * others:
            out.append(f"{c.get('address', '?')}: adjusted to {money(values[i])}, more than {share:.0%} "
                       f"{'above' if values[i] > others else 'below'} the other comps' median {money(others)}. Replace it with "
                       "the next candidate, or keep it only if it's one of the closest matches and say why in method_note "
                       "(method.md, Outliers).")
    return out


RANGE_WIDTH_SHARE = 0.06  # Results_v5: the supported range is at most about 6% of the value wide (method.md)
RANGE_STEP = 5000  # each end of the range is rounded to $5,000


def range_width(median, market=None):
    """Results_v5 (owner decision A): how wide the supported range may be, as {cap, floor, target}. `cap` is about 6%
    of the median adjusted value (`cma.range_width_pct` in the market overrides the share; an agent's older dollar
    `cma.typical_range_width` is still honored as the cap); `floor` is half of it; `target` is the widest $5,000 step
    under the cap (at least the floor), the width a range normally has. $440,000 gives a cap of $26,400 and a $25,000
    target; $386,800 a cap of $23,208 and a $20,000 target."""
    pct = market.get("cma.range_width_pct") if market is not None else None
    dollars = market.get("cma.typical_range_width") if market is not None and not pct else None
    cap = dollars or (pct or RANGE_WIDTH_SHARE) * median
    floor = cap / 2
    target = max(math.floor(cap / RANGE_STEP) * RANGE_STEP, math.ceil(floor / RANGE_STEP) * RANGE_STEP)
    return {"cap": cap, "floor": floor, "target": target}


def range_bounds(values, market):
    """CMA-296, iteration 12: the widest span the comps support without one sale setting an end, as (low, high, target
    width). Each end may reach the second-lowest / second-highest adjusted value (the lowest / highest with 3 comps or
    fewer), rounded outward to $5,000, or half the target width from the median, rounded outward to $5,000, whichever
    is farther: tightly clustered comps never force a range narrower than the method's normal width. A range must
    also stay within range_width's cap (Results_v5): the bounds say where its ends may sit, not how wide it may be."""
    v = sorted(values)
    median = statistics.median(v)
    target = range_width(median, market)["target"]
    lo, hi = (v[1], v[-2]) if len(v) >= 4 else (v[0], v[-1])
    low = min(math.floor(lo / RANGE_STEP) * RANGE_STEP, math.floor((median - target / 2) / RANGE_STEP) * RANGE_STEP)
    high = max(math.ceil(hi / RANGE_STEP) * RANGE_STEP, math.ceil((median + target / 2) / RANGE_STEP) * RANGE_STEP)
    return low, high, target


def choose_range(values, market):
    """The supported range, by one rule, so the same comps always give the same range (method.md, The Range): the
    normal width (range_width's `target`, the widest $5,000 step under the cap) centered on the median adjusted value,
    the low end rounded half up to $5,000 and the high end the low end plus the width, then moved inside range_bounds
    when the rounding put an end past what the comps support (one comp never sets an end). Returns (low, high).
    The model never types a range; `range_override` (resolve_range) is the agent's own choice, shown as theirs."""
    median = statistics.median(values)
    low_ok, high_ok, target = range_bounds(values, market)
    lo = fmt.half_up((median - target / 2) / RANGE_STEP) * RANGE_STEP
    lo = min(max(lo, low_ok), high_ok - target)
    return lo, lo + target


passing_range = choose_range  # every range warning names the rule's range as one that passes


def resolve_range(values, market, override=None):
    """The report's range: the rule's (choose_range), or the agent's `range_override` {low, high, reason} when given.
    Returns ({low, high, rule_low, rule_high, override (bool), reason}, errors as `field: problem → fix`). An override
    still gets the range checks (range_warnings), so a range one comp sets or one wider than the cap warns."""
    rule_lo, rule_hi = choose_range(values, market)
    out = {"low": rule_lo, "high": rule_hi, "rule_low": rule_lo, "rule_high": rule_hi, "override": False, "reason": ""}
    if override in (None, {}, False):
        return out, []
    fix = ('{"low": ..., "high": ..., "reason": "why, in words"}, only when the agent chose the range; otherwise leave '
           f"it out and the script sets it ({money(rule_lo)} – {money(rule_hi)} here)")
    if not isinstance(override, dict):
        return out, [f"range_override: should be {fix}."]
    lo, hi, why = override.get("low"), override.get("high"), str(override.get("reason") or "").strip()
    errors = []
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 for x in (lo, hi)) or lo >= hi:
        errors.append(f"range_override: low and high must be plain numbers, low under high (got {lo!r}, {hi!r}) → {fix}.")
    if not why:
        errors.append("range_override.reason: missing → say in words (no figures) why the agent set the range instead "
                      "of the rule; the report shows it as the agent's choice.")
    if errors:
        return out, errors
    out.update(low=lo, high=hi, override=True, reason=why)
    return out, []


def range_warnings(bl, values, market):
    """CMA-296, Results_v5: the supported range against the adjusted comps (method.md), for the buyer and seller CMAs
    alike. `bl` has `low` and `high`. Returns [(key, text)], each saying what passes and naming a range that does, which
    is never wider than the cap nor narrower than the floor. `range_wide`: wider than about 6% of the median (the cap).
    `range_one_comp`: an end past `range_bounds`, so a single comp sets it. `range_narrow`: under half the cap, narrower
    than the comps can promise."""
    if not values:
        return []
    median = statistics.median(values)
    low_ok, high_ok, _ = range_bounds(values, market)
    w = range_width(median, market)
    widest = math.floor(w["cap"] / RANGE_STEP) * RANGE_STEP
    narrowest = math.ceil(w["floor"] / RANGE_STEP) * RANGE_STEP
    ex_lo, ex_hi = passing_range(values, market)
    example = f"{money(ex_lo)} – {money(ex_hi)}"
    sizes = (f"{money(narrowest)} to {money(widest)} wide" if widest > narrowest else f"{money(widest)} wide")
    passes = (f"A range passes when both ends sit inside {money(low_ok)} – {money(high_ok)} and it's {sizes} "
              f"(about {w['floor'] / median:.0%} to {w['cap'] / median:.0%} of the median adjusted value, {money(median)}); "
              f"for example {example}.")
    out = []
    width = bl["high"] - bl["low"]
    if width > w["cap"] + 1:
        out.append(("range_wide", f"The range is {money(width)} wide, more than about {w['cap'] / median:.0%} of the median adjusted value "
                    f"({money(w['cap'], 100)}): wider than the comps support, and it pulls the price ends apart. Narrow it "
                    "around the best matches; if the comps truly disagree, replace the weakest match (the largest "
                    "adjustments, the farthest or oldest sale) and re-run. " + passes))
    if bl["high"] > high_ok:
        out.append(("range_one_comp", f"The top of the range ({money(bl['high'])}) is above {money(high_ok)}: only one sale "
                    f"supports it. Bring it to {money(high_ok)} or below. " + passes))
    if bl["low"] < low_ok:
        out.append(("range_one_comp", f"The bottom of the range ({money(bl['low'])}) is below {money(low_ok)}: only one sale "
                    f"supports it. Bring it to {money(low_ok)} or above. " + passes))
    if width < w["floor"] - 1:
        out.append(("range_narrow", f"The range is {money(width)} wide, under half the widest a range may be "
                    f"({money(w['floor'], 100)}): adjusted comps can't promise a value that precise, even when they agree. "
                    f"Widen it around the median adjusted value ({money(median)}). " + passes))
    return out


# --- the buyer's offer posture -------------------------------------------------------

# Strategy categories (plan: model picks, script prices): the buyer CMA's offer plan is set by a posture. The script
# suggests one from the listing's history and the market; the model keeps it or picks another with a reason. must_win
# is the buyer's situation (the agent's call), never suggested from data.
POSTURES = ("leverage", "standard", "competitive", "must_win")
LEVERAGE_CUTS = 2  # price cuts since the last sale that give the buyer leverage
LEVERAGE_DOM_TIMES = 2  # days on market at least this many times the market's recent median
COMPETITIVE_DOM = 14  # a listing this new...
COMPETITIVE_SUPPLY = 3  # ...in a market under this many months of supply draws competing offers


def suggest_posture(history, stats):
    """The offer posture the data suggests: `leverage` when the history since the last sale has a failed contract, 2
    or more price cuts, or days on market at least twice the market's recent median; `competitive` when the listing
    has been on the market 14 days or fewer and the market has under 3 months of supply; else `standard`.
    `history` is the buyer CMA's history counts (failed_contracts, price_cuts, active_days) or None; `stats` the
    market numbers (median_days_recent, months_supply), any of them missing. A signal that's missing never fires."""
    h, s = history or {}, stats or {}
    dom, median_days, supply = h.get("active_days"), s.get("median_days_recent"), s.get("months_supply")
    if (h.get("failed_contracts") or 0) >= 1 or (h.get("price_cuts") or 0) >= LEVERAGE_CUTS \
            or (dom is not None and median_days and dom >= LEVERAGE_DOM_TIMES * median_days):
        return "leverage"
    if dom is not None and dom <= COMPETITIVE_DOM and supply is not None and supply < COMPETITIVE_SUPPLY:
        return "competitive"
    return "standard"


# --- the seller's pricing stance and the list price it sets ----------------------

# A seller CMA's pricing stance (method.md, Pricing Stance): the model picks one, the script turns it into the price.
# Each stance sets the list price at a share of the supported range's width.
STANCES = ("draw_offers", "market", "premium")
STANCE_SHARE = {"draw_offers": 0.25, "market": 0.5, "premium": 0.75}
DRAW_SUPPLY, DRAW_CUT_SHARE, DRAW_SALE_TO_LIST = 6, 0.40, 0.97  # any one suggests drawing offers
PREMIUM_SUPPLY, PREMIUM_SALE_TO_LIST = 3, 1.00  # both together suggest a premium
DRAW_SIGNALS = ("supply_high", "price_cuts", "sale_below_list")
PREMIUM_SIGNALS = ("supply_low", "sale_at_list")


def stance_signals(stats):
    """The market signals the numbers show, as a set. `stats` has the seller CMA's market numbers (`months_supply`,
    `active_share_with_price_cut`, `sale_to_final_list_recent`, `sale_to_original_list_recent`; any may be missing, and
    a missing number shows no signal). Draw-offers signals: supply_high (6 or more months of supply), price_cuts (40%
    or more of the active listings cut their price), sale_below_list (recent sales under 97% of their FINAL asking
    price). Premium signals: supply_low (under 3 months) and sale_at_list (recent sales at or above their asking
    price). Without final list prices only the original-list ratio is known: a sale at or above its original price was
    at or above its final one too (a final price is never above the original), so that shows sale_at_list, but a sale
    under its original price may have closed at its final one, so it never shows sale_below_list."""
    supply = stats.get("months_supply")
    cuts = stats.get("active_share_with_price_cut")
    final = stats.get("sale_to_final_list_recent")
    at_least = final if final is not None else stats.get("sale_to_original_list_recent")
    return {k for k, hit in (("supply_high", supply is not None and supply >= DRAW_SUPPLY),
                             ("price_cuts", cuts is not None and cuts >= DRAW_CUT_SHARE),
                             ("sale_below_list", final is not None and final < DRAW_SALE_TO_LIST),
                             ("supply_low", supply is not None and supply < PREMIUM_SUPPLY),
                             ("sale_at_list", at_least is not None and at_least >= PREMIUM_SALE_TO_LIST)) if hit}


def suggest_stance(stats, failed=False):
    """(stance, signals): the pricing stance the market data suggests (`stats` as in stance_signals) and the signals
    that suggested it, so a sentence built from them names only those: draw_offers when any draw-offers signal shows;
    premium when both premium signals show; else market, with none. A reprice or relist (`failed`: the market already
    turned a price down) never suggests premium."""
    shown = stance_signals(stats)
    draw = [k for k in DRAW_SIGNALS if k in shown]
    if draw:
        return "draw_offers", draw
    if not failed and all(k in shown for k in PREMIUM_SIGNALS):
        return "premium", list(PREMIUM_SIGNALS)
    return "market", []


def _bracket(value):
    """The portal search-bracket step at a price: $5,000 under $1M, $10,000 above."""
    return 10000 if value >= 1_000_000 else 5000


def bracket_price(value, way="nearest"):
    """A list price on a search-bracket step, a round number ($470,000; $1,250,000 above $1M): the nearest step to
    `value`, or the highest step at or under it (`down`), or the lowest at or over it (`up`). Portal price filters
    include their bounds, so a price on the step shows up in the searches on both sides of it ("up to $470,000" and
    "$470,000 and up"), where $469,900 shows up only in the lower one."""
    step = _bracket(value)
    if way == "nearest":
        return fmt.half_up(value / step) * step
    k = value / step
    return (math.floor(k) if way == "down" else math.ceil(k)) * step


def list_price_at(point, low, high):
    """The list price for a point inside the supported range (low + the stance's share of the width): the nearest
    search-bracket step to it (bracket_price), and when that falls outside the range, the next step inward. A range
    narrower than one step (an agent's own) takes the point itself, to the nearest $100."""
    price = bracket_price(point)
    step = _bracket(point)
    if price < low:
        price += step
    elif price > high:
        price -= step
    if not low <= price <= high:
        price = min(max(fmt.half_up(point, 100), low), high)
    return price


# --- adjustment kinds ------------------------------------------------------------

# A comp adjustment's category (`kind`), so text that lists what was adjusted uses fixed plain words, never the
# model's label wording ("hall bath (not in its listing)"). The card keeps its own label.
ADJUSTMENT_KINDS = ("size", "pool", "garage", "condition", "age", "lot", "view", "location", "time", "credits", "other")
# Kind inferred from a label when none is given: the first kind with a matching word, in this order
_KIND_WORDS = (
    ("time", r"market|since the sale|time|months?|quarter|rates?|sold in|appreciation|softening|slowdown|sale date|"
             r"(?:earlier|older|spring|summer|fall|winter|january|february|march|april|may|june|july|august|september|"
             r"october|november|december) sale"),
    ("credits", r"credit|concession|seller[- ]paid|seller help"),
    ("pool", r"pool|spa"),
    ("garage", r"garage|carport|parking"),
    ("age", r"roof|\bac\b|a/c|hvac|systems?|water heater|windows?|\bage\b|year built|older|newer|effective age"),
    ("view", r"view|water|pond|lake|golf|conservation|preserve|canal|river|ocean|bay"),
    ("lot", r"\blot\b|acre|yard|corner|cul-de-sac|frontage"),
    ("location", r"location|street|road|traffic|neighborhood|subdivision|busy|commercial"),
    ("size", r"size|sq\.? ?ft|square|living area|larger|smaller|bedroom|room count|stories"),
    ("condition", r"kitchen|bath|renovat|remodel|update|condition|floor|dated|finish|paint|repair|cabinet|counter"),
)


def adjustment_kind(adj):
    """The adjustment's `kind` when given, else the one its label points to ('other' when none does)."""
    if isinstance(adj, dict) and adj.get("kind") in ADJUSTMENT_KINDS:
        return adj["kind"]
    label = str((adj or {}).get("label", "") if isinstance(adj, dict) else adj).lower()
    return next((k for k, words in _KIND_WORDS if re.search(words, label)), "other")


def adjustment_kind_errors(cards):
    """`kind` values that aren't one of ADJUSTMENT_KINDS, as `field: problem → fix` lines."""
    out = []
    for i, c in enumerate(cards or []):
        for j, a in enumerate(c.get("adjustments") or []):
            if isinstance(a, dict) and a.get("kind") not in (None, "") and a["kind"] not in ADJUSTMENT_KINDS:
                out.append(f"comps.cards[{i}].adjustments[{j}].kind: {a['kind']!r} isn't a kind → use one of "
                           f"{', '.join(ADJUSTMENT_KINDS)}, or leave it out to take it from the label.")
    return out


# The plain words for each adjustment kind, the same in every report and deck
ADJ_KIND_WORDS = {"size": "size", "pool": "pool", "garage": "garage", "condition": "condition and updates",
                  "age": "roof and systems", "lot": "lot", "view": "view or water", "location": "location",
                  "time": "market changes since each sale", "credits": "seller credits", "other": "other differences"}


def _and(items):
    return fmt.and_list(items)


def adjustment_kinds_used(cards):
    """Each adjustment kind the comps use (an adjustment with an amount), once, in the order first used, plus
    `credits` when any sale had seller-paid costs (they come off its price)."""
    seen = []
    for c in cards or []:
        for a in c.get("adjustments") or []:
            if isinstance(a, dict) and not a.get("amount"):
                continue
            kind = adjustment_kind(a)
            if kind not in seen:
                seen.append(kind)
    if any(c.get("seller_concessions") for c in cards or []) and "credits" not in seen:
        seen.append("credits")
    return seen


def adjustment_summary(cards, time_info=None, f=None, condition_info=None):
    """Results_v5 case 02: the method line's list of what was adjusted, generated from the comps so it names every kind
    actually used, each with its amounts: 'Adjusted for size (plus or minus up to $7,500), condition and updates
    ($5,000 to $25,000), market changes since each sale (1.5% a quarter for sales before July) and seller credits (taken
    off each sale price).' `time_info` is apply_time_adjustments' info, for the rate and cutoff; `condition_info`
    apply_condition_adjustments', for the subject's level ("against this home's updated kitchen"). '' with none.
    `f` formats the amounts (finance.money by default; a skill on the report kit passes fmt.money)."""
    f = f or money
    parts = []
    for kind in adjustment_kinds_used(cards):
        amounts = sorted({abs(a["amount"]) for c in cards for a in c.get("adjustments") or []
                          if isinstance(a, dict) and isinstance(a.get("amount"), (int, float)) and a["amount"]
                          and adjustment_kind(a) == kind})
        if kind == "time" and time_info:
            detail = (f"{time_info['rate_display']} a quarter {'off' if time_info['falling'] else 'added to'} sales "
                      f"before {time_info['cutoff_display']}")
        elif kind == "credits" and not amounts:
            detail = "taken off each sale price"
        elif not amounts:
            detail = ""
        elif len(amounts) == 1:
            detail = f(amounts[0])
        else:
            detail = f"{f(amounts[0])} to {f(amounts[-1])}"
        if kind == "condition" and condition_info and detail:
            detail += f", against this home's {condition_info['subject_phrase'].removeprefix('an ').removeprefix('a ')}"
        parts.append(ADJ_KIND_WORDS[kind] + (f" ({detail})" if detail else ""))
    return f"Adjusted for {_and(parts)}." if parts else ""


# --- condition adjustments: script-owned, from one ladder -------------------------------

# The condition ladder (references/condition-ladder.md): each comp and the subject get one level, from listing evidence
# (the comp's remarks; the seller's description of their home), and the script adjusts each comp by the difference in
# the levels' dollar values. In ladder order, lowest first.
CONDITION_LEVELS = ("original", "cosmetic", "baths_only", "kitchen_only", "kitchen_and_baths", "full_renovation", "new")
CONDITION_WORDS = {  # (card label, phrase in a sentence)
    "original": ("Original", "original condition"),
    "cosmetic": ("Cosmetic Updates", "cosmetic updates"),
    "baths_only": ("Updated Baths", "updated baths"),
    "kitchen_only": ("Updated Kitchen", "an updated kitchen"),
    "kitchen_and_baths": ("Updated Kitchen and Baths", "an updated kitchen and baths"),
    "full_renovation": ("Full Renovation", "a full renovation"),
    "new": ("New or Like New", "new or like-new condition"),
}
CONDITION_LABEL = "Condition: {level}"  # the card label of a condition adjustment the script adds
# A typed adjustment whose label names the kitchen, baths or a renovation is a condition adjustment, whatever its kind
_CONDITION_TYPED = re.compile(r"kitchen|bath|renovat|remodel|condition|dated|finishes|cosmetic", re.I)


def condition_values(market, given=None):
    """{level: dollars over an original home}: report.json's `comps.condition_values` (paired sales or the agent's
    rates) over the market's `cma.adjustments.condition_levels`. {} when neither has any."""
    base = (market.get("cma.adjustments.condition_levels") if market is not None else None) or {}
    return {**{k: v for k, v in base.items() if k in CONDITION_LEVELS}, **(given if isinstance(given, dict) else {})}


def _level_errors(where, level):
    if level in CONDITION_LEVELS:
        return []
    got = "missing" if level in (None, "") else f"{level!r} isn't a level"
    return [f"{where}: {got} → one of {', '.join(CONDITION_LEVELS)} (references/condition-ladder.md: pick it from the "
            "listing's own words; a partly updated kitchen or baths counts as the level below)."]


def apply_condition_adjustments(comps, subject, market):
    """Condition adjustments are the script's, by one ladder: `subject.condition` and each card's `condition` name a
    level (CONDITION_LEVELS); each comp gets the subject's level value minus its own (condition_values), added to its
    adjustments as kind "condition" (none when the levels match). A condition amount typed on a card is an error: the
    level carries it. Returns (errors as `field: problem → fix`, info {subject, subject_phrase, values} or None)."""
    cards = comps.get("cards") or []
    errors = _level_errors("subject.condition", subject.get("condition"))
    for i, c in enumerate(cards):
        errors += _level_errors(f"comps.cards[{i}].condition", c.get("condition"))
        for j, a in enumerate(c.get("adjustments") or []):
            if not isinstance(a, dict) or a.get("source") == "script":
                continue
            if adjustment_kind(a) == "condition" or _CONDITION_TYPED.search(str(a.get("label") or "")):
                errors.append(f"comps.cards[{i}].adjustments[{j}]: a condition adjustment ({a.get('label')!r}) typed by "
                              "hand → delete it and set the card's `condition` level (and subject.condition): the script "
                              "adjusts each comp by the difference between the levels.")
    given = comps.get("condition_values")
    if given is not None and (not isinstance(given, dict) or any(
            k not in CONDITION_LEVELS or isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0
            for k, v in given.items())):
        errors.append("comps.condition_values: should be {level: dollars over an original home} with levels from "
                      f"{', '.join(CONDITION_LEVELS)} and plain non-negative numbers.")
        given = None
    values = condition_values(market, given)
    if errors:
        return errors, None
    used = [subject["condition"]] + [c["condition"] for c in cards]
    if len(set(used)) == 1:  # every comp at the home's level: nothing to adjust, so no dollars needed
        values = {used[0]: values.get(used[0], 0)}
    missing = [lv for lv in dict.fromkeys(used) if lv not in values]
    if missing:
        return [f"comps.condition_values: no dollar value for {', '.join(missing)} in this market → give "
                "comps.condition_values {level: dollars over an original home} for every level used, from paired sales "
                "in the export or the agent's rates, scaled to the price (method.md)."], None
    ordered = [values[lv] for lv in CONDITION_LEVELS if lv in values]
    if ordered != sorted(ordered):
        return ["comps.condition_values: a higher level is worth less than a lower one → each level's value is at least "
                "the one below it (" + " ≤ ".join(CONDITION_LEVELS) + ")."], None
    mine = values[subject["condition"]]
    for c in cards:
        c["adjustments"] = [a for a in c.get("adjustments") or [] if not (isinstance(a, dict) and a.get("source") == "script"
                                                                          and a.get("kind") == "condition")]
        amount = fmt.half_up(mine - values[c["condition"]])
        if amount:
            c["adjustments"].insert(0, {"label": CONDITION_LABEL.format(level=CONDITION_WORDS[c["condition"]][0]),
                                     "amount": amount, "kind": "condition", "source": "script"})
    info = {"subject": subject["condition"], "subject_phrase": CONDITION_WORDS[subject["condition"]][1],
            "values": {lv: values[lv] for lv in CONDITION_LEVELS if lv in values}}
    return [], info


# --- time adjustments: script-owned (Results_v5) ------------------------------------

QUARTER_DAYS = 365.25 / 4
TIME_LABEL = "Market Change Since the Sale"  # the card label of a time adjustment the script adds
_LONG_DATE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                        r"(\d{1,2}),\s+(\d{4})\b")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value not in (None, "") else None
    except ValueError:
        return None


def comp_close_date(card, homes=()):
    """A comp's close date: the card's `close_date` (YYYY-MM-DD), else the export's sold row for its address, else
    the date written in its `meta` line ("Sold $384,000 · September 19, 2026 · ..."). None when there's none."""
    d = _iso(card.get("close_date"))
    if d:
        return d
    row = next((h for h in homes or () if h.get("status") == "SOLD" and h.get("close_date")
                and mls.same_address(_street(h["address"]), _street(card.get("address", "")))), None)
    if row:
        return row["close_date"] if isinstance(row["close_date"], date) else _iso(row["close_date"])
    m = _LONG_DATE.search(str(card.get("meta", "")))
    if m:
        return date(int(m.group(3)), MONTH_NAMES.index(m.group(1)) + 1, int(m.group(2)))
    return None


def default_split(R, homes=()):
    """The market split date: report.json's `split_date`, else stats.py's default (90 days before the last sale)."""
    d = _iso(R.get("split_date"))
    if d:
        return d
    sold = [h["close_date"] for h in homes or () if h.get("status") == "SOLD" and isinstance(h.get("close_date"), date)]
    return max(sold) - timedelta(days=90) if sold else None


def day_words(d):
    """'July' for the 1st of a month, 'August 15' otherwise: a cutoff or split as the report writes it."""
    return MONTH_NAMES[d.month - 1] + ("" if d.day == 1 else f" {d.day}")


def _pct(rate):
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".") + "%"


def apply_time_adjustments(comps, homes, as_of, split):
    """Results_v5: time adjustments are the script's, by one rule. `comps.time_adjustment` states the method:
    {rate_per_quarter (a fraction, 0.015 for 1.5%), prices ("falling", the default, or "rising"), cutoff (YYYY-MM-DD,
    default the market split)}. Each comp that closed before the cutoff gets the rate times the quarters from its close
    date to the as-of date, on its price net of seller-paid costs, to $100 (minus when prices are falling); a sale on or
    after the cutoff gets none. The script adds the adjustment (kind "time"), or checks one typed on the card: a typed
    amount that disagrees, or a time adjustment on a sale after the cutoff, is an error. Each card's bullets may say
    `{time_amount}`. Returns (errors as `field: problem → fix`, info for the method line and placeholders or None)."""
    cards = comps.get("cards") or []
    spec = comps.get("time_adjustment")
    typed = [(i, j, a) for i, c in enumerate(cards) for j, a in enumerate(c.get("adjustments") or [])
             if isinstance(a, dict) and adjustment_kind(a) == "time"]
    if spec in (None, {}, False):
        return [f"comps.cards[{i}].adjustments[{j}]: a time adjustment ({money(a['amount']) if isinstance(a.get('amount'), (int, float)) else a.get('amount')}) "
                "typed by hand → state the method once in comps.time_adjustment ({\"rate_per_quarter\": 0.015} for 1.5% a "
                "quarter, plus \"cutoff\" when it isn't the market split) and leave the amount out: the script figures each "
                "sale's from its close date." for i, j, a in typed if a.get("source") != "script"], None
    errors = []
    if not isinstance(spec, dict):
        return ["comps.time_adjustment: should be {rate_per_quarter, prices, cutoff} → for example "
                "{\"rate_per_quarter\": 0.015}."], None
    rate = spec.get("rate_per_quarter")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= 0.05:
        errors.append(f"comps.time_adjustment.rate_per_quarter: {rate!r} → a fraction per quarter between 0 and 0.05 "
                      "(0.015 for 1.5%); with no change in prices, leave comps.time_adjustment out.")
    prices = spec.get("prices", "falling")
    if prices not in ("falling", "rising"):
        errors.append(f"comps.time_adjustment.prices: {prices!r} → \"falling\" (older sales come down) or \"rising\".")
    cutoff = _iso(spec.get("cutoff")) if spec.get("cutoff") else split
    if spec.get("cutoff") and not cutoff:
        errors.append(f"comps.time_adjustment.cutoff: {spec['cutoff']!r} → a date like 2026-07-01, or leave it out for "
                      "the market split.")
    elif cutoff is None:
        errors.append("comps.time_adjustment.cutoff: no cutoff and no market split → give split_date (or the cutoff).")
    end = _iso(as_of) or date.today()
    if errors:
        return errors, None
    falling = prices == "falling"
    by_card, undated = {}, []
    for i, j, a in typed:
        by_card.setdefault(i, []).append((j, a))
    for i, c in enumerate(cards):
        closed = comp_close_date(c, homes)
        where = f"comps.cards[{i}]"
        if closed is None:  # missing data never stops a render: no date, no time adjustment (the caller warns)
            undated.append(c.get("address", "?"))
            continue
        sold, conc = c.get("sold_price"), c.get("seller_concessions") or 0
        if not isinstance(sold, (int, float)) or not isinstance(conc, (int, float)):
            continue  # derive_comps names it
        amount = 0
        if closed < cutoff:
            amount = round((sold - conc) * rate * max((end - closed).days, 0) / QUARTER_DAYS / 100) * 100
            amount = -amount if falling else amount
        mine = by_card.get(i, [])
        if len(mine) > 1:
            errors.append(f"{where}.adjustments: {len(mine)} time adjustments → keep one, or leave them out and the "
                          "script adds it.")
            continue
        if mine:
            j, a = mine[0]
            got = a.get("amount")
            off = not isinstance(got, (int, float)) or abs(got - amount) > max(300, 0.05 * abs(amount))
            if off and a.get("source") != "script":
                why = (f"it closed {fmt.date_long(closed.isoformat())}, on or after the {fmt.date_long(cutoff.isoformat())} cutoff, so it "
                       "gets none" if not amount else
                       f"{_pct(rate)} a quarter from its {fmt.date_long(closed.isoformat())} close to {fmt.date_long(end.isoformat())} "
                       f"gives {money(amount)}")
                errors.append(f"{where}.adjustments[{j}]: the time adjustment is {money(got) if isinstance(got, (int, float)) else repr(got)}, "
                              f"but {why} → leave the amount out (delete the line) and the script adds it.")
                continue
            if amount:
                a.update(amount=amount, kind="time", source="script")
            else:
                c["adjustments"].pop(j)
        elif amount:
            c.setdefault("adjustments", []).append({"label": TIME_LABEL, "amount": amount, "kind": "time", "source": "script"})
        c["time_amount"] = amount
        bullets = c.get("bullets") or []
        if any("{time_amount}" in str(b) for b in bullets):
            if not amount:
                errors.append(f"{where}.bullets: says {{time_amount}}, but this sale closed on or after the cutoff and "
                              "gets no time adjustment → drop that sentence.")
            else:
                c["bullets"] = [str(b).replace("{time_amount}", money(abs(amount))) for b in bullets]
    info = {"rate": rate, "rate_display": _pct(rate), "falling": falling, "cutoff": cutoff.isoformat(),
            "cutoff_display": day_words(cutoff), "undated": undated}
    return errors, info


def time_warnings(info):
    """A comp with no close date gets no time adjustment: say which, so the agent can add close_date."""
    return [f"{a}: no close date (card close_date, the export or its meta line), so it has no time adjustment. Add "
            "close_date (YYYY-MM-DD) to the card and re-run." for a in (info or {}).get("undated") or []]


NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")


def number_word(n):
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else f"{n:,}"


# --- closing notices ------------------------------------------------------------------

def report_notices(C):
    """The CMA's fixed closing notices (CMA-16): where the sales data came from and as of when, that a CMA isn't an
    appraisal or for lending, and that payment and tax figures are estimates."""
    src = C.get("data_source") or {}
    when = fmt.date_long(src.get("as_of"))  # CMA-311: "September 26, 2026" in a client PDF, never 2026-09-26
    lines = [f"Sales data: {src['mls']} MLS as of {when}. Deemed reliable but not guaranteed." if src.get("mls") and src.get("export")
             else f"Sales data as of {when}, from the sources named in the report. Deemed reliable but not guaranteed."]
    lines.append("This comparative market analysis is an opinion of price, not an appraisal, and isn't for lending purposes.")
    lines.append("Payment, tax and cost figures are estimates only, not lending or tax advice.")
    return lines


# CMA-274, CMA-276: reading the printed pages back lives in layout.py
HALF_EMPTY, LONE_TAIL, page_fill, _squash = layout.HALF_EMPTY, layout.LONE_TAIL, layout.page_fill, layout.squash


CALLOUT_REASONS = {"size": "left off the chart for its size (scatter.min_size_ratio / max_size_ratio)",
                   "price": "left off the chart as priced far off the trend",
                   "not_in_export": "not found in the export (use the export's spelling of the address)"}


def callout_checks(info):
    """CMA-299: one Check per scatter callout whose home isn't on the chart, naming it and why (the chart plots sales
    and active listings only, within the size range and near the trend)."""
    out = []
    for label, address, reason in info.get("callouts_dropped") or []:
        why = CALLOUT_REASONS.get(reason) or (
            f"{reason}, and the chart plots only sales and active listings" if reason not in ("sold", "active")
            else "missing its size or price in the export")
        out.append(f"The scatter callout {label!r} ({address}) isn't on the chart: {why}. Drop the callout or point it at "
                   "a plotted home, then render again.")
    return out


