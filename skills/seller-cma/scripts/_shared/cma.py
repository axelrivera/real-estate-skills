"""Report pieces shared by the buyer and seller CMAs: labels, tables, charts, keep-together groups, pagination.

All visible text comes from the skill's labels file (assets/labels.json). Colors are theme variables
(shared/cma.css), never hard-coded.
"""
import html
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from datetime import date, timedelta

from . import finance, mls

CMA_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cma.css")
money = finance.money
ADJ_NET_LIMIT, ADJ_GROSS_LIMIT = 0.15, 0.25  # common appraisal guidelines, as shares of the comp's sale price
OUTLIER_SHARE = 0.10  # CMA-110: an adjusted value this far from the other comps' median is an outlier (method.md)
LABEL_GAP = 3  # px kept clear between two chart labels on the seller CMA's scatter, so stacked labels never touch
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
    head = [unspaced_range(h) for h in head]  # Results_v5: "April – June" reads "April–June" in a header
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
        def one(m):
            v = values.get(m.group(1), m.group(0))
            # a value that opens a sentence ("{comps_since_split} sales closed..."): its first letter upper case
            if v[:1].islower() and re.search(r"(^|[.!?]\s+|<strong>)$", value[:m.start()]):
                return v[0].upper() + v[1:]
            return v
        return re.sub(r"\{(\w+)\}", one, value)
    if isinstance(value, list):
        return [fill(v, values) for v in value]
    if isinstance(value, dict):
        return {key: fill(v, values) for key, v in value.items()}
    return value


def page_one_values(C):
    """Placeholders every CMA page 1 can use."""
    return {"median_adjusted": C["median_adjusted_display"]}


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


def scatter(homes, sc, subject_sqft, subject_price, subject_address, band, L, comps=(), drop_crowded=False):
    """Price vs. size for sold and active homes near the subject's size, with the supported range band.

    `comps`: the comp cards' addresses, drawn as comparable sales. `drop_crowded` (the seller CMA): labels stay
    LABEL_GAP apart, and a callout with no clear spot, even on a leader line, is left off (listed in `labels_dropped`)
    instead of printed over a marker or another label.
    `sc`: {callouts: [{address, label, side}], subject_label, subject_label_pos, min/max/fit_size_ratio}.
    Label sides: left, right, above or below.
    Returns (svg, info) where info has trend_at_subject, r2, excluded [(address, sqft, kind, reason)], n_sold, n_active,
    counts {kind: n} for scatter_legend, and callouts_dropped for callouts whose home isn't on the chart.
    """
    pts, excluded, fit = scatter_points(homes, sc, subject_sqft, subject_address, comps)
    sold, act = pts["comp"] + pts["sold"], pts["active"]
    kind = {id(h): k for k, hs in pts.items() for h in hs}

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
        # other sales are the background: small, see-through dots, so overlapping sales read as a denser patch
        cls, r = f"m-{kind}" + (" hol" if hollow else ""), 4 if kind == "sold" else 6.5
        return f'<g><title>{esc(tip)}</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" class="{cls}"/></g>'

    o = [f'<svg viewBox="0 0 {W} {H}" role="img" class="scatter" aria-label="{esc(L("axis_y"))} / {esc(L("axis_x"))}">',
         f'<rect x="{Lm}" y="{y(band[1]):.1f}" width="{W - Lm - R}" height="{y(band[0]) - y(band[1]):.1f}" class="band"/>',
         ]
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
    def sale(h):
        o.append(shape(cat(h), x(h["living_area"]), y(h["close_price"]), False,
                       f'{display_address(h["address"])}: {L("tip_sold")} ${int(h["close_price"]):,}, {int(h["living_area"]):,} sq ft'))

    for h in pts["sold"]:  # background first, comps and the subject on top
        sale(h)
    for h in act:
        o.append(shape("active", x(h["living_area"]), y(h["current_price"]), True,
                       f'{display_address(h["address"])}: {L("tip_active")} ${int(h["current_price"]):,}, {int(h["living_area"]):,} sq ft'))
    for h in pts["comp"]:
        sale(h)
    sx, sy, d = x(subject_sqft), y(subject_price), 10
    o.append(f'<g><title>{esc(display_address(subject_address))}: {L("tip_asking")} ${int(subject_price):,}</title>'
             f'<path d="M{sx:.1f},{sy - d:.1f} L{sx + d:.1f},{sy:.1f} L{sx:.1f},{sy + d:.1f} L{sx - d:.1f},{sy:.1f} Z" class="subj"/></g>')
    # CMA-205, CMA-253: labels step aside from the markers (and each other) instead of printing over them; the band's
    # label goes in the first corner clear of markers
    marks = [(x(h["living_area"]), y(h["close_price"]), 4 if cat(h) == "sold" else 6.5) for h in sold]
    marks += [(x(h["living_area"]), y(h["current_price"]), 6.5) for h in act] + [(sx, sy, d)]
    placer = _LabelPlacer(marks, (Lm, T, W - R, H - B), gap=LABEL_GAP if drop_crowded else 0)
    band_text = f'{L("band")} {k(band[0])}–{k(band[1])}'
    band_w = _text_w(band_text, 12, bold=True)
    spots = [(bx, by, anchor, (bx if anchor == "start" else bx - band_w, by - 10, (bx if anchor == "start" else bx - band_w) + band_w, by + 3))
             for by in (y(band[1]) - 6, y(band[0]) + 15) for bx, anchor in ((Lm + 8, "start"), (W - R - 8, "end"))]
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
    o.append("</svg>")
    info = {"trend_at_subject": fit["at_subject"] if fit else None, "r2": fit["r2"] if fit else None,
            "excluded": excluded, "n_sold": len(sold), "n_active": len(act),
            "counts": {**{kind: len(hs) for kind, hs in pts.items()}, "trend": 1 if fit else 0},
            "labels_moved": placer.moved, "labels_overlapping": placer.overlapping,
            "labels_leader": placer.leaders, "labels_dropped": placer.dropped,  # CMA-218
            "crowded_labels": placer.clashing, "callouts_dropped": dropped_callouts}  # CMA-299
    return "\n".join(o), info


def _text_w(text, size, bold=False):
    """About how wide a chart label draws (sans-serif letters and digits average ~0.56 em, bold ~0.6), plus room for the
    wider fallback fonts some sandboxes print with (Results_v5: a band label measured for Helvetica ran into a marker)."""
    return len(text) * size * (0.6 if bold else 0.56) * FONT_SLACK


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
        w, h = len(text) * size * (0.6 if bold else 0.55), size
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


def scatter_legend(L, subject, counts):
    """Only the entries with something on the chart: `counts` is scatter()'s info["counts"]."""
    entries = [
        ("comp", '<circle cx="7" cy="7" r="5.5" class="m-comp"/>'),
        ("sold", '<circle cx="7" cy="7" r="4" class="m-sold"/>'),
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
    """One line with the counts only: which homes were left off doesn't matter to the reader, just that some were
    and why (size, or a price far off the line)."""
    parts = []
    for reason in ("size", "price"):
        n = sum(e[3] == reason for e in excluded)
        if n:
            parts.append(L(f"excluded_{reason}_one") if n == 1 else L(f"excluded_{reason}_many", n=n))
    return f'<p class="note">{" ".join(parts)}</p>' if parts else ""


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
    lines = [v for v in (xm, xs) if v is not None]
    for i, c in enumerate(cs):
        cy, cx, val = T + i * row + row / 2 - 4, x(c["adjusted"]), k(c["adjusted"])
        w = _text_w(val, 12)
        # CMA-253: a value label that a price line would strike through goes on the dot's left, when that side is clear
        left = (any(cx + 8 <= v <= cx + 12 + w for v in lines) and cx - 12 - w > Lm
                and not any(cx - 12 - w <= v <= cx - 8 for v in lines))
        anchor = ' text-anchor="end"' if left else ""
        o.append(f'<text x="0" y="{cy + 4:.1f}" class="dp-addr">{esc(display_address(c["address"]))}</text>'
                 f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" class="dp-dot"/>'
                 f'<text x="{cx - 10 if left else cx + 10:.1f}" y="{cy + 4:.1f}"{anchor} class="dp-val">{val}</text>')
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


PAGINATE_JS = """([pageH, starts]) => {
  // Page 1 fits itself: tighten in steps (fit1 → fit3, cumulative) until it clears the page with a small margin.
  const one = document.querySelector('.onepage'); let fit = 0;
  while (one && fit < 3 && one.getBoundingClientRect().height > pageH - 16) one.classList.add('fit' + (++fit));
  const wrap = document.querySelector('.wrap');
  const base = wrap.getBoundingClientRect().top;
  let shift = 0; const moved = [];
  // Print layout runs a few pixels taller than this screen estimate, so a block must fit with room to spare;
  // otherwise it splits or moves at print time and leaves a gap the shrink rule never saw (CMA-274).
  // Results_v5: a table or list runs on once a fifth of the page is left (it was a third: whole pages went 35-60% empty)
  const SAFE = 16, FLOW_ROOM = 0.2;
  const squash = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  for (const el of Array.from(wrap.children)) {
    const r = el.getBoundingClientRect();
    const mt = parseFloat(getComputedStyle(el).marginTop) || 0;
    let t = r.top - base - mt + shift; const h = r.height + mt;
    let pos = ((t % pageH) + pageH) % pageH;
    // A block the print read-back saw starting a page that this estimate put lower on the page before (drift from an
    // earlier block that printed taller): it starts the next page here too, so what follows is placed as it prints
    const text = squash(el.innerText);
    if (pos > 5 && text && (starts || []).some(s => text.startsWith(s))) { shift += pageH - pos; t += pageH - pos; pos = 0; }
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
        if (pp > 5 && pp + rows[top] > pageH - SAFE) shift += pageH - pp;
      });
      continue;
    }
    let brk = false;
    // A group that opts in (.runon: the seller CMA's How This Was Prepared) runs on to the next page block by block
    // instead of moving whole and leaving the page before part empty (Results_v4 case 02), once its heading and first
    // block fit here.
    // Results_v5: so does a group of headings and paragraphs only (no table, chart or list to keep whole), from a fifth
    const textOnly = isKeep && Array.from(el.children).every(c => /^(H2|H3|P)$/.test(c.tagName));
    const runon = el.classList.contains('runon') || textOnly;
    if (pos > 5 && isKeep && runon && pos + h > pageH - SAFE && pageH - pos >= (textOnly ? FLOW_ROOM : 0.25) * pageH) {
      const units = Array.from(el.children).slice(1);
      if (units.length && pos + units[0].getBoundingClientRect().bottom - r.top + mt <= pageH - SAFE) {
        el.classList.add('split');
        for (const u of units) {
          const ur = u.getBoundingClientRect(), tt = ur.top - base + shift, pp = ((tt % pageH) + pageH) % pageH;
          if (pp > 5 && pp + ur.height > pageH - SAFE) shift += pageH - pp;
        }
        continue;
      }
    }
    // a section never starts in the bottom quarter of a page, unless all of it fits there (Results_v5: a short section
    // that fits stays, rather than leave the page a quarter empty)
    if (pos > 5 && el.classList.contains('sec') && pos > 0.75 * pageH && !(keepOK && pos + h <= pageH - SAFE)) brk = true;
    else if (pos > 5 && keepOK && pos + h > pageH - SAFE) {
      // CMA-252: a scatter that almost fits the rest of a page shrinks (to 80% at most) rather than move and leave
      // half the page empty; it moves only when less than 40% of the page is left or it would need to shrink more.
      const svg = el.querySelector('svg.scatter'), over = pos + h - pageH + SAFE;
      const sr = svg ? svg.getBoundingClientRect() : null;
      if (sr && pageH - pos >= 0.4 * pageH && over <= 0.2 * sr.height) {
        svg.style.width = (sr.width * (sr.height - over) / sr.height) + 'px';
        el.classList.add('shrunk');
      } else if (!svg && !el.querySelector('.tbl.whole') && pageH - pos >= FLOW_ROOM * pageH) {
        // A table or list block that would leave this much of the page empty runs on instead, whole rows or items
        // only, once its heading, intro and first few rows fit here (the table's header row repeats on the next page).
        // A table marked .whole (the buyer CMA's Price vs. Seller Credit: its columns read across every row) never
        // runs on: its block moves whole (iteration 12)
        const tb = el.querySelector('.tbl'), rows = tb ? tb.querySelectorAll('tbody tr') : [];
        const items = tb ? [] : el.querySelectorAll(':scope > ul > li, :scope > ol > li');
        const parts = tb ? rows : items, keep = tb ? 3 : 2;
        if (parts.length >= keep + 2 && pos + parts[keep - 1].getBoundingClientRect().bottom - r.top + mt <= pageH - SAFE) {
          el.classList.add('flow');
          if (tb) tb.classList.add('brk');
          const th = tb ? tb.querySelector('thead') : null;
          // the gap left at the break and the repeated header row, roughly
          shift += (th ? th.getBoundingClientRect().height : 0) + parts[keep].getBoundingClientRect().height;
        } else brk = true;
      } else brk = true;
    }
    if (brk) { el.classList.add('pb'); shift += pageH - pos; moved.push((el.innerText || '').split('\\n')[0].slice(0, 50)); }
  }
  return { moved, onepageH: window.__onepageH || 0, pageH, fit };
}"""

PAGE_MARGINS = {"top": "0.45in", "right": "0.45in", "bottom": "0.55in", "left": "0.45in"}
CONTENT_HEIGHT_PX = 10 * 96  # 11in − 0.45in − 0.55in


def paginate(pg, starts=()):
    """Before printing: fit page 1 on one page (fit_level 0-3), then move groups so none splits
    and no section starts in the bottom quarter of a page. `starts`: the first words of blocks a print read-back saw
    starting a page (print_report)."""
    pg.set_viewport_size({"width": 730, "height": 1000})  # 8.5in − 2 × 0.45in
    res = pg.evaluate(PAGINATE_JS, [CONTENT_HEIGHT_PX, list(starts)])
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


def passing_range(values, market):
    """One range that passes every range check: the target width centered on the median (ends to $5,000), moved inside
    the bounds when the rounding put an end outside them."""
    median = statistics.median(values)
    low_ok, high_ok, target = range_bounds(values, market)
    lo = round((median - target / 2) / RANGE_STEP) * RANGE_STEP
    lo = min(max(lo, low_ok), high_ok - target)
    return lo, lo + target


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
    ("age", r"roof|\bac\b|a/c|hvac|systems?|water heater|\bage\b|year built|older|newer|effective age"),
    ("view", r"view|water|pond|lake|golf|conservation|preserve|canal|river|ocean|bay"),
    ("lot", r"\blot\b|acre|yard|corner|cul-de-sac|frontage"),
    ("location", r"location|street|road|traffic|neighborhood|subdivision|busy|commercial"),
    ("size", r"size|sq\.? ?ft|square|living area|larger|smaller|bedroom|room count|stories"),
    ("condition", r"kitchen|bath|renovat|remodel|update|condition|floor|dated|finish|paint|repair|cabinet|counter|window"),
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
    items = [i for i in items if i]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else "".join(items)


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


def adjustment_words(cards):
    """'size, condition and updates, market changes since each sale and seller credits' (CMA-26): what was adjusted,
    each kind once, in fixed plain words, never the label's own wording."""
    return _and([ADJ_KIND_WORDS[k] for k in adjustment_kinds_used(cards)])


def adjustment_summary(cards, time_info=None):
    """Results_v5 case 02: the method line's list of what was adjusted, generated from the comps so it names every kind
    actually used, each with its amounts: 'Adjusted for size (plus or minus up to $7,500), condition and updates
    ($5,000 to $25,000), market changes since each sale (1.5% a quarter for sales before July) and seller credits (taken
    off each sale price).' `time_info` is apply_time_adjustments' info, for the rate and cutoff. '' with no adjustments."""
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
            detail = money(amounts[0])
        else:
            detail = f"{money(amounts[0])} to {money(amounts[-1])}"
        parts.append(ADJ_KIND_WORDS[kind] + (f" ({detail})" if detail else ""))
    return f"Adjusted for {_and(parts)}." if parts else ""


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
                why = (f"it closed {long_date(closed.isoformat())}, on or after the {long_date(cutoff.isoformat())} cutoff, so it "
                       "gets none" if not amount else
                       f"{_pct(rate)} a quarter from its {long_date(closed.isoformat())} close to {long_date(end.isoformat())} "
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


def time_values(info):
    """{time_rate} ('1.5%') and {time_cutoff} ('July', 'August 15') for the method wording."""
    return {"time_rate": info["rate_display"], "time_cutoff": info["cutoff_display"]} if info else {}


_TIME_SENTENCE = re.compile(r"\bper quarter\b|\ba quarter\b|\btime adjust", re.I)
_BEFORE_MONTH = re.compile(r"\b(?:before|prior to|until)\s+(?:early\s+|late\s+|mid-?\s*)?(" + "|".join(MONTH_NAMES) + r")\b")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def time_method_errors(fields, info):
    """Results_v5: the method's stated time adjustment must be the one applied: in a sentence about the quarterly
    adjustment, a typed percent other than the rate, or 'before <Month>' at another month than the cutoff, is an
    error (write {time_rate} and {time_cutoff}). `fields`: [(path, text)]."""
    if not info:
        return []
    out = []
    for path, text in fields:
        for sentence in re.split(r"(?<=[.!?;])\s+", re.sub(r"<[^>]+>", "", str(text))):
            if not _TIME_SENTENCE.search(sentence):
                continue
            pcts = [float(p) for p in _PERCENT.findall(sentence)]
            if pcts and not any(abs(p - info["rate"] * 100) < 0.01 for p in pcts):
                out.append(f'{path}: says "{_PERCENT.search(sentence).group(0)}" a quarter, but the time adjustment applied '
                           f"is {info['rate_display']} → write {{time_rate}}.")
            cut = info["cutoff_display"].split()[0]
            for m in _BEFORE_MONTH.finditer(sentence):
                if m.group(1) != cut:
                    out.append(f'{path}: says "{m.group(0)}", but the time adjustment applies to sales before '
                               f"{info['cutoff_display']} → write \"before {{time_cutoff}}\".")
    return out


# --- comp facts for the wording, and the light check of comp prose (Results_v5) ------------------

NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")


def number_word(n):
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else f"{n:,}"


def comp_facts(cards, homes, split, as_of=None, fmt=money):
    """Results_v5: the facts comp wording usually states, as placeholders: {comps_count}, {comps_since_split} (closed on
    or after the market split), {comps_with_<kind>} (comps with an adjustment of that kind, e.g. {comps_with_age}:
    roof and systems; credits also counts seller-paid costs), {newest_comp} and {newest_comp_date}, {adjusted_min},
    {adjusted_max}, {adjusted_median} (with `fmt`). Counts are words ('four'). Returns (values, raw) where raw holds
    the numbers the prose check compares against."""
    dated = [(c, comp_close_date(c, homes)) for c in cards]
    since = [c for c, d in dated if d and split and d >= split]
    kinds = {k: sum(1 for c in cards if any(isinstance(a, dict) and a.get("amount") and adjustment_kind(a) == k
                                              for a in c.get("adjustments") or [])
                     or (k == "credits" and c.get("seller_concessions")))
             for k in ADJUSTMENT_KINDS}
    values = {"comps_count": number_word(len(cards)), "comps_since_split": number_word(len(since)),
              **{f"comps_with_{k}": number_word(n) for k, n in kinds.items()}}
    adjusted = [c["adjusted"] for c in cards if isinstance(c.get("adjusted"), (int, float))]
    if adjusted:
        values.update(adjusted_min=fmt(min(adjusted)), adjusted_max=fmt(max(adjusted)),
                      adjusted_median=fmt(statistics.median(adjusted)))
    known = [(c, d) for c, d in dated if d]
    newest = max(d for _, d in known) if known else None
    if newest:
        top = next(c for c, d in known if d == newest)
        values.update(newest_comp=display_address(top["address"]), newest_comp_date=f"{MONTH_NAMES[newest.month - 1]} {newest.day}")
    raw = {"n": len(cards), "n_since": len(since), "kinds": kinds, "dates": [d for _, d in dated], "newest": newest,
           "adjusted": adjusted, "sold": [c.get("sold_price") for c in cards],
           "adjusted_since": [c["adjusted"] for c in since if isinstance(c.get("adjusted"), (int, float))],
           "sold_since": [c.get("sold_price") for c in since],
           "split_month": MONTH_NAMES[split.month - 1] if split else None, "addresses": [c.get("address", "") for c in cards]}
    return values, raw


_COUNT = re.compile(r"\b(?P<n>" + "|".join(NUMBER_WORDS[2:11]) + r")\s+(?:of\s+(?:the|these|our)\s+)?"
                    r"(?P<mid>(?:[A-Za-z][\w'-]*\s+){0,3}?)(?P<noun>sales|comps|comparables|comparable sales|matches|homes)\b",
                    re.I)
_COMP_WORDS = re.compile(r"\b(closest|best|nearest|comparable|comps?|matches)\b", re.I)
_SINCE = re.compile(r"\b(?:since|after|from)\s+(?:early\s+|mid-?\s*|late\s+)?(" + "|".join(MONTH_NAMES) + r")\b")
_WITH = re.compile(r"^\s+with\s+(?:an?\s+|the\s+)?((?:[\w-]+\s*){1,4})", re.I)
_BAND = re.compile(r"(?:\b(?P<q1>low|lower|mid|middle|high|upper)(?:[- ]to[- ](?P<q2>mid|middle|high|upper))?[- ]?)?"
                   r"\$(?P<d>\d{1,3}),?(?P<z>0)00s\b", re.I)
_NEWEST = re.compile(r"\b(newest|most recent|latest)\b(?:\s+[\w-]+){0,2}?\s+(sale|sales|close|closing|comp|sold|match)\b", re.I)
_LISTING_WORDS = re.compile(r"\b(listings?|for sale|asking|listed|active)\b", re.I)


def _band(m):
    """(low, high) of a '$440,000s' band ('$400,000s' spans $100,000), narrowed by low / mid / high, $1,000 loose."""
    d = int(m.group("d"))
    base, span = d * 1000, 100000 if d % 100 == 0 else 10000 if d % 10 == 0 else 1000
    q1, q2 = (m.group("q1") or "").lower(), (m.group("q2") or "").lower()
    part = {"low": (0, 0.5), "lower": (0, 0.5), "mid": (0.25, 0.75), "middle": (0.25, 0.75), "high": (0.5, 1),
            "upper": (0.5, 1)}
    lo, hi = part.get(q1, (0, 1))
    if q2:
        hi = part[q2][1]
    return base + lo * span - 1000, base + hi * span + 1000


def comp_prose_errors(fields, raw, extra_counts=()):
    """Results_v5: a light check of comp and scatter wording against the comps, kept conservative. A number-word count
    of comps ("the three sales that closed since July", "four comps with newer roofs", "the five closest matches") that
    isn't the comps' own count; a "$440,000s" band the comps it names don't sit in; "the newest sale" for a comp that
    isn't the newest. `fields`: [(path, text)]; `raw` from comp_facts; `extra_counts`: other counts a "since <split>"
    sentence may mean (the export's sales since the split). Each as `field: problem → fix`."""
    out = []
    since_ok = {raw["n_since"], *extra_counts}
    for item in fields:
        path, text = item[:2]
        card = re.match(r"^comps\.cards\[(\d+)\]", path)
        card_index = item[2] if len(item) > 2 else int(card.group(1)) if card else None
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"<[^>]+>", "", str(text))):
            since_split = any(m.group(1) == raw["split_month"] for m in _SINCE.finditer(sentence))
            for m in _COUNT.finditer(sentence):
                n, noun = NUMBER_WORDS.index(m.group("n").lower()), m.group("noun").lower()
                w = _WITH.match(sentence[m.end():])
                kind = adjustment_kind({"label": w.group(1)}) if w else None
                if kind and kind != "other":
                    if n != raw["kinds"].get(kind, n):
                        out.append(f'{path}: says "{m.group(0)} with {w.group(1).strip()}", but {number_word(raw["kinds"][kind])} '
                                   f"of the comps have a {ADJ_KIND_WORDS[kind]} adjustment → write {{comps_with_{kind}}}.")
                elif since_split:
                    if n not in since_ok:
                        out.append(f'{path}: says "{m.group(0)}" since {raw["split_month"]}, but '
                                   f"{number_word(raw['n_since'])} of the comps closed since then → write {{comps_since_split}}.")
                elif noun != "homes" and (noun in ("comps", "comparables", "comparable sales", "matches")
                                          or _COMP_WORDS.search(m.group("mid") or "")):
                    if n not in (raw["n"], raw["n_since"]):
                        out.append(f'{path}: says "{m.group(0)}", but the report has {number_word(raw["n"])} comps → '
                                   "write {comps_count}.")
            named = _COMP_WORDS.search(sentence) or _COUNT.search(sentence) or re.search(r"\badjust", sentence, re.I)
            if named and not _LISTING_WORDS.search(sentence):
                group = (raw["adjusted_since"], raw["sold_since"]) if since_split else (raw["adjusted"], raw["sold"])
                for m in _BAND.finditer(sentence):
                    lo, hi = _band(m)
                    if group[0] and not any(vals and all(lo <= v <= hi for v in vals if isinstance(v, (int, float)))
                                            for vals in group):
                        out.append(f'{path}: says "{m.group(0)}", but the comps it names run from {money(min(group[0]))} '
                                   f"to {money(max(group[0]))} adjusted → write {{adjusted_min}} to {{adjusted_max}}.")
            if raw["newest"] and _NEWEST.search(sentence):
                if card_index is not None:
                    i = card_index
                    d = raw["dates"][i] if i < len(raw["dates"]) else None
                    if d and d < raw["newest"]:
                        out.append(f'{path}: calls this sale "{_NEWEST.search(sentence).group(0)}", but a comp closed later '
                                   f"({long_date(raw['newest'].isoformat())}) → say {{newest_comp}} ({{newest_comp_date}}) is "
                                   "the newest, or drop it.")
                else:
                    hit = [i for i, a in enumerate(raw["addresses"]) if a and _street(a).split(" ")[0] in sentence.split()
                           and _street(a).split(" ")[1:2] and _street(a).split(" ")[1].lower() in sentence.lower()]
                    if len(hit) == 1 and raw["dates"][hit[0]] and raw["dates"][hit[0]] < raw["newest"]:
                        out.append(f'{path}: calls {display_address(raw["addresses"][hit[0]])} '
                                   f'"{_NEWEST.search(sentence).group(0)}", but a comp closed later → write {{newest_comp}}.')
    return out


# --- dates in history tables, and column headers -------------------------------------

def history_date_labels(dates, this_year=None):
    """Results_v5 case 03: 'Jul 10, 2026' on every row when the rows span more than one year (or their one year isn't
    `this_year`), so a bare 'Aug 14' never reads as another row's year; 'Jul 10' on every row when all are this year."""
    years = {d.year for d in dates}
    short = len(years) == 1 and (this_year is None or years == {this_year})
    return [f"{d:%b} {d.day}" if short else f"{d:%b} {d.day}, {d.year}" for d in dates]


_SPACED_RANGE = re.compile(r"(?<=\w)\s+[–-]\s+(?=\w)")


def unspaced_range(text):
    """Results_v5: 'April – June' in a column header reads 'April–June' (an en dash, no spaces)."""
    return _SPACED_RANGE.sub("–", str(text))


def long_date(value):
    """A YYYY-MM-DD date written out ("September 26, 2026"); anything else as given."""
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        return value or ""
    return f"{d:%B} {d.day}, {d.year}"


def report_notices(C):
    """The CMA's fixed closing notices (CMA-16): where the sales data came from and as of when, that a CMA isn't an
    appraisal or for lending, and that payment and tax figures are estimates."""
    src = C.get("data_source") or {}
    when = long_date(src.get("as_of"))  # CMA-311: "September 26, 2026" in a client PDF, never 2026-09-26
    lines = [f"Sales data: {src['mls']} MLS as of {when}. Deemed reliable but not guaranteed." if src.get("mls") and src.get("export")
             else f"Sales data as of {when}, from the sources named in the report. Deemed reliable but not guaranteed."]
    lines.append("This comparative market analysis is an opinion of price, not an appraisal, and isn't for lending purposes.")
    lines.append("Payment, tax and cost figures are estimates only, not lending or tax advice.")
    return lines


# CMA-274, CMA-276: how full each printed page is, read back from the PDF (the layout measured before printing can
# drift a few pixels from Chromium's print layout, enough to push a block to the next page)
HALF_EMPTY = 0.5  # a page before a kept-together block that ends above half the page leaves a gap worth fixing
LONE_TAIL = 0.15  # a last page this empty holds only a few closing lines
_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">([^<]*)</word>')
_PAGE = re.compile(r'width="[\d.]+" height="([\d.]+)"')


def page_fill(pdf, top_in=0.45, bottom_in=0.55):
    """[(fill, first line)] per page: how far down the content area the text reaches (0 to 1) and the page's first
    line, from pdftotext -bbox. None when pdftotext isn't available. The content area is the page less the top and
    bottom margins in inches (cma.PAGE_MARGINS by default; 0.3 and 0.4 for render.html_to_pdf's default), on a page of
    any height (a landscape page too)."""
    tool = shutil.which("pdftotext")
    if not tool:
        return None
    try:
        out = subprocess.run([tool, "-bbox", pdf, "-"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    pages = []
    for chunk in out.split("<page ")[1:]:
        height = _PAGE.match(chunk)
        top_pt, bottom_pt = top_in * 72, (float(height.group(1)) if height else 792) - bottom_in * 72
        words = [(float(x), float(y0), float(y1), html.unescape(t)) for x, y0, y1, t in _WORD.findall(chunk)
                 if float(y1) <= bottom_pt + 1]  # the running footer sits below the content area
        if not words:
            pages.append((0.0, ""))
            continue
        bottom = max(w[2] for w in words)
        top = min(w[1] for w in words)
        first = " ".join(w[3] for w in sorted((w for w in words if w[1] - top < 3), key=lambda w: w[0]))
        pages.append((max(0.0, (bottom - top_pt) / (bottom_pt - top_pt)), first[:60]))
    return pages


def _squash(text):
    return " ".join(str(text).split()).lower()


def print_report(doc, path, footer_html, tail_hint="the last sections"):
    """Print a CMA report (paginate, then the PDF), read the pages back (page_fill) and, when a page before the last
    is under half full because the block starting it printed lower than paginate estimated (CMA-274 drift: an earlier
    block printed taller), print it again with that block starting its page in the estimate, so the blocks after it
    are placed (and a scatter shrunk to fit) as they print. The second print is kept only when it has fewer page checks.
    Returns (paginate's info, pages or None)."""
    from . import render
    info = render.html_to_pdf(doc, path, margins=PAGE_MARGINS, footer_html=footer_html, before_print=paginate)
    pages = page_fill(path)
    if not pages:
        return info, pages
    starts = [_squash(pages[i][1])[:30] for i in range(1, len(pages) - 1) if pages[i][0] < HALF_EMPTY and pages[i][1].strip()]
    checks = page_checks(pages, tail_hint)
    if not starts or not checks:
        return info, pages
    with tempfile.TemporaryDirectory() as tmp:
        second = os.path.join(tmp, os.path.basename(path))
        retry = render.html_to_pdf(doc, second, margins=PAGE_MARGINS, footer_html=footer_html,
                                   before_print=lambda pg: paginate(pg, starts))
        again = page_fill(second)
        if again is not None and len(page_checks(again, tail_hint)) < len(checks):
            shutil.move(second, path)
            return retry, again
    return info, pages


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


def page_checks(pages, tail_hint="the last sections"):
    """Checks for pages 2 onward: one that ends above half the page before a block that moved on, and a last page
    holding only a few closing lines."""
    checks = []
    for i in range(1, len(pages) - 1):
        fill, _ = pages[i]
        if fill < HALF_EMPTY:
            checks.append(f"Page {i + 1} is only {fill:.0%} full: the next block (\"{pages[i + 1][1]}\") didn't fit and "
                          f"starts page {i + 2}. Shorten the wording before it on page {i + 1} or in that block (its intro, "
                          "a comp bullet, a note) so it fits, then render again.")
    if len(pages) > 2 and pages[-1][0] < LONE_TAIL:
        checks.append(f"The last page (page {len(pages)}) holds only a few closing lines (\"{pages[-1][1]}\"): shorten "
                      f"{tail_hint} so they fit on the page before, then render again.")
    return checks
