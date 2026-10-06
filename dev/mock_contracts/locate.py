"""Find every blank on a FAR/BAR form and give it a stable id, so a field map only has to name ids.

    python dev/mock_contracts/locate.py FARBAR-ASIS                 # list every blank: id, kind, label, context
    python dev/mock_contracts/locate.py CR-7_K --pages 1           # one page only
    python dev/mock_contracts/locate.py FARBAR-ASIS --debug out.pdf # the form with every blank boxed and labeled
    python dev/mock_contracts/locate.py EA --draft                 # every blank with its context, to name in a map

A blank is a drawn rule (the forms draw most blanks as lines), a run of underscores in the text, a small square
(a checkbox) or a larger box (a signature or initials slot). Ids come from the printed line number in the margin
("L27", and "L30.2" for the second blank on line 30), so they survive small layout changes. Blanks on lines with no
number get "P<page>.<n>" in reading order (footers, signature blocks on unnumbered forms). Local dev only.
"""
import argparse
import json
import os
import re
import sys

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FORMS_DIR = os.path.join(ROOT, "sources", "Contracts", "FARBAR")
MANIFEST = os.path.join(ROOT, "dev", "forms", "farbar-forms.json")
FIELDS_DIR = os.path.join(HERE, "fields")

MARGIN_X = 50  # printed line numbers sit left of this
UNDERSCORES = re.compile(r"_{3,}")
BOX_GLYPHS = {"\uf06f", "\uf0a3", "\uf071", "\uf0a8", "\u25a1", "\u2610", "\u274f", "\u2751"}
INITIALS = re.compile(r"(Buyer|Se[lI]{2}er)['’]?s?\s+Initials\s*$", re.I)  # Riders FF and GG print "SeIIer's"


def manifest():
    with open(MANIFEST) as f:
        return json.load(f)["forms"]


def form_path(family):
    forms = manifest()
    if family not in forms:
        raise SystemExit(f"{family}: not in dev/forms/farbar-forms.json. Known: {', '.join(sorted(forms))}")
    path = os.path.join(FORMS_DIR, forms[family]["file"])
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing. The FAR/BAR PDFs live in the git-ignored sources/Contracts/FARBAR/.")
    return path


def _line_numbers(words):
    """{number: (y0, y1)} from the margin: digit words left of MARGIN_X (the asterisk is its own word)."""
    out = {}
    for x0, y0, x1, y1, text, *_ in words:
        if x1 < MARGIN_X and text.rstrip("*").isdigit():
            out[int(text.rstrip("*"))] = (y0, y1)
    return out


def _rules(page):
    """Horizontal rules and boxes drawn on the page: (segments [(x0, x1, y)], boxes [Rect])."""
    segs, boxes = [], []
    for d in page.get_drawings():
        for item in d["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.y - b.y) < 0.8 and abs(b.x - a.x) > 8:
                    segs.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
            elif item[0] == "re":
                r = item[1]
                if r.height < 1.6 and r.width > 8:
                    segs.append((r.x0, r.x1, r.y1))
                elif 4 < r.width < 19 and 4 < r.height < 19 and abs(r.width - r.height) < 3:
                    boxes.append(pymupdf.Rect(r))
                elif r.width >= 14 and 9 <= r.height <= 40 and r.width < page.rect.width - 20:
                    boxes.append(pymupdf.Rect(r))
                elif r.width > 150 and 40 < r.height < page.rect.height * 0.7 and r.width < page.rect.width - 20 \
                        and d.get("color") is None and d.get("fill") in (None, (1.0, 1.0, 1.0)):
                    boxes.append(pymupdf.Rect(r))  # a multi-line text area (ACSP-4 terms)
    return segs, boxes


def _merge_segments(segs):
    """Drawn blanks are often doubled (a line and a thin rect): keep one per overlapping pair."""
    out = []
    for x0, x1, y in sorted(segs, key=lambda s: (round(s[2]), s[0])):
        for i, (a0, a1, ay) in enumerate(out):
            overlap = min(x1, a1) - max(x0, a0)
            if abs(ay - y) < 2 and overlap > 0.5 * min(x1 - x0, a1 - a0):
                out[i] = (min(a0, x0), max(a1, x1), max(ay, y))
                break
        else:
            out.append((x0, x1, y))
    return out


def _dedupe_boxes(boxes):
    out = []
    for r in boxes:
        if not any(abs(r.x0 - o.x0) < 2 and abs(r.y0 - o.y0) < 2 and abs(r.x1 - o.x1) < 2 for o in out):
            out.append(r)
    return out


def _nearest_line(lines, y, tol):
    best, dist = None, tol
    for n, (y0, y1) in lines.items():
        d = abs(y1 - y) if y > y1 - 1 else (0 if y0 - 1 <= y <= y1 + 1 else abs(y - y1))
        if d < dist:
            best, dist = n, d
    return best


def _visible(words):
    """Words with glued underscore runs trimmed off ("as_______" -> "as"), bounding boxes adjusted."""
    out = []
    for x0, y0, x1, y1, text, *_ in words:
        if len(text) > 1 and text[0] in BOX_GLYPHS:
            x0, text = x0 + (x1 - x0) / len(text), text[1:]
        if any(c in BOX_GLYPHS for c in text):  # "Inspection:\uf0a3Yes": keep the text before the glyph as this word
            text = text[:min(text.index(c) for c in BOX_GLYPHS if c in text)]
            if not text:
                continue
        parts = [p for p in UNDERSCORES.split(text) if p.strip(".,:;()$ ")]
        if not parts:
            continue
        if parts[0] != text:
            cw = (x1 - x0) / max(len(text), 1)
            start = text.index(parts[0])
            x0, x1, text = x0 + cw * start, x0 + cw * (start + len(parts[0])), parts[0]
        out.append((x0, y0, x1, y1, text))
    return out


def _context(words, rect, kind):
    """(label, after): the text just left of the blank on its row, and just right of it."""
    if kind == "line":
        lo, hi = rect.y1 - 9, rect.y1 + 1
    else:
        lo, hi = rect.y0 - 1, rect.y1 + 1
    row = sorted((w for w in words if lo <= (w[1] + w[3]) / 2 <= hi and w[2] > MARGIN_X), key=lambda w: w[0])
    left = [w[4] for w in row if w[2] <= rect.x0 + 2][-6:]
    right = [w[4] for w in row if w[0] >= rect.x1 - 2][:5]
    return " ".join(left), " ".join(right)


def _below(words, rect):
    """Words printed just under the blank, within its width ("BUYER ... Date" under a signature line): [[x0, text]]."""
    top = rect.y0 + rect.height * 0.5 if rect.height > 18 else rect.y1 - 1
    under = [w for w in words if top <= (w[1] + w[3]) / 2 <= rect.y1 + 12 and rect.x0 - 6 <= w[0] < rect.x1 - 2]
    return [[round(w[0], 1), w[4]] for w in sorted(under, key=lambda w: w[0])][:8]


def blanks(path, pages=None):
    """Every blank in the form, in reading order: dicts with id, page (1-based), line, kind, rect [x0, y0, x1, y1],
    label, after and below. kind: 'line' (a printed rule), 'field' (a Dotloop field box: text, signature or
    initials), 'area' (a multi-line text box), 'check'."""
    doc = pymupdf.open(path)
    out = []
    for pno, page in enumerate(doc, start=1):
        if pages and pno not in pages:
            continue
        words = page.get_text("words")
        lines = _line_numbers(words)
        visible = _visible(words)
        segs, boxes = _rules(page)
        # Underscore runs in the text are blanks too (initials lines, "______________ County").
        for x0, y0, x1, y1, text, *_ in words:
            if text in BOX_GLYPHS:  # checkboxes printed as a font glyph (CO-3) rather than drawn
                side = min(x1 - x0, y1 - y0) * 0.8
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                boxes.append(pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2))
                continue
            if len(text) > 1 and any(c in BOX_GLYPHS for c in text):
                # A glyph glued to its label: "\uf0a3owner" (SPDR-4x), "Inspection:\uf0a3Yes" (MISIRS-2).
                cw, side, cy = (x1 - x0) / len(text), (y1 - y0) * 0.55, (y0 + y1) / 2
                for i, c in enumerate(text):
                    if c in BOX_GLYPHS:
                        gx = x0 + cw * i + 0.5
                        boxes.append(pymupdf.Rect(gx, cy - side / 2, gx + side, cy + side / 2))
            m = UNDERSCORES.search(text)
            if m:
                cw = (x1 - x0) / max(len(text), 1)
                segs.append((x0 + cw * m.start(), x0 + cw * m.end(), y1 - 1.5))
        # Checkboxes placed as small square images (CR-7x Rev. 05/2026 draws some no other way). Most images sit on a
        # box already found; only one no box overlaps is new.
        for info in page.get_image_info():
            r = pymupdf.Rect(info["bbox"])
            if 5 < r.width < 19 and abs(r.width - r.height) < 3 and not any(r.intersects(b) for b in boxes):
                boxes.append(r)
        segs = _merge_segments(segs)
        boxes = _dedupe_boxes(boxes)
        found = []
        for r in boxes:
            kind = "check" if r.width < 19 and abs(r.width - r.height) < 3 else "area" if r.height > 40 else "field"
            # Dotloop field outlines sit over the printed rule: drop the rules they cover.
            segs = [s for s in segs if not (min(s[1], r.x1) - max(s[0], r.x0) > 0.5 * (s[1] - s[0])
                                            and r.y0 - 3 <= s[2] <= r.y1 + 3)]
            found.append((kind, r))
        for x0, x1, y in segs:
            found.append(("line", pymupdf.Rect(x0, y - 11, x1, y)))
        for kind, r in found:
            y = (r.y0 + r.y1) / 2 if kind != "line" else r.y1
            line = _nearest_line(lines, y, 5 if kind == "line" else 4) if lines else None
            label, after = _context(visible, r, kind)
            out.append({"page": pno, "line": line, "kind": kind, "rect": [round(v, 1) for v in r],
                        "label": label, "after": after, "below": _below(visible, r)})
    # The Dotloop export's "Licensed to dotloop, Inc. and <member>" line isn't a blank of the form (stamp.redact_license).
    out = [b for b in out if "licensed to dotloop" not in b["label"].lower()]
    out.sort(key=lambda b: (b["page"], b["line"] if b["line"] is not None else 10**6,
                            round(b["rect"][3] / 4) if b["line"] is None else 0, b["rect"][0]))
    counts, seen = {}, {}
    for b in out:
        if b["line"] is not None:
            counts[b["line"]] = counts.get(b["line"], 0) + 1
    for b in out:
        if b["line"] is not None:
            n = seen[b["line"]] = seen.get(b["line"], 0) + 1
            b["id"] = f"L{b['line']}" + (f".{n}" if counts[b["line"]] > 1 else "")
            continue
        # Footer initials slots get named ids: P3.BI1, P3.BI2 (buyers), P3.SI1, P3.SI2 (sellers). Disclosures print
        # "Seller [ ][ ] and Buyer [ ][ ] acknowledge receipt of a copy of this page" instead.
        m = INITIALS.search(b["label"]) if b["kind"] == "field" else None
        party = (m.group(1)[0].upper() + "I") if m else ""
        if not party and b["kind"] == "field" and b["rect"][2] - b["rect"][0] < 60:
            lab, aft = b["label"].strip().lower(), b["after"].strip().lower()
            if lab.endswith("seller") and aft.startswith("and buyer"):
                party = "SI"
            elif lab.endswith("and buyer") and aft.startswith("acknowledge"):
                party = "BI"
        key = (b["page"], party)
        n = seen[key] = seen.get(key, 0) + 1
        b["id"] = f"P{b['page']}.{key[1]}{n}"
    return out


def debug_pdf(path, dest, pages=None, fields=None):
    """The form with every blank outlined and its id printed, plus the field name when a map is given."""
    doc = pymupdf.open(path)
    names = {}
    for name, spec in (fields or {}).items():
        for bid in spec.get("blanks", [spec.get("blank")]):
            if bid:
                names[bid] = name
    for b in blanks(path, pages):
        page = doc[b["page"] - 1]
        r = pymupdf.Rect(b["rect"])
        color = (0.85, 0.1, 0.1) if b["id"] in names else (0.1, 0.35, 0.85)
        page.draw_rect(r, color=color, width=0.6)
        tag = b["id"] + (f" {names[b['id']]}" if b["id"] in names else "")
        page.insert_text((r.x0 + 1, r.y0 + 5), tag, fontsize=4.5, color=color)
    if pages:
        doc.select([p - 1 for p in sorted(pages)])
    doc.save(dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("family", help="form family key from dev/forms/farbar-forms.json (FARBAR-ASIS, CR-7_K, CO, EA...)")
    ap.add_argument("--pages", help="comma-separated 1-based pages")
    ap.add_argument("--debug", metavar="PDF", help="write the form with every blank outlined and its id printed")
    ap.add_argument("--draft", action="store_true", help="write every blank with its label, following text and caption to "
                    "out/mock-contracts/_drafts/<FAMILY>.json, the starting point for fields/<FAMILY>.json")
    ap.add_argument("--json", action="store_true", help="print the blanks as JSON")
    a = ap.parse_args()
    path = form_path(a.family)
    pages = {int(p) for p in a.pages.split(",")} if a.pages else None
    found = blanks(path, pages)
    if a.debug:
        fields = None
        mp = os.path.join(FIELDS_DIR, f"{a.family}.json")
        if os.path.exists(mp):
            with open(mp) as f:
                fields = json.load(f).get("fields")
        debug_pdf(path, a.debug, pages, fields)
        print(f"wrote {a.debug}")
    if a.draft:
        drafts = os.path.join(ROOT, "out", "mock-contracts", "_drafts")
        os.makedirs(drafts, exist_ok=True)
        dest = os.path.join(drafts, f"{a.family}.json")
        draft = {"family": a.family, "revision": manifest()[a.family]["revision"],
                 "blanks": {b["id"]: {"kind": b["kind"], "page": b["page"], "rect": b["rect"], "label": b["label"],
                                      "after": b["after"], "below": " ".join(t for _, t in b["below"])} for b in found}}
        with open(dest, "w") as f:
            json.dump(draft, f, indent=1)
        print(f"wrote {dest}: {len(found)} blanks. Name the ones the scenario needs in fields/{a.family}.json.")
    if a.json:
        print(json.dumps(found, indent=1))
    elif not a.draft:
        for b in found:
            print(f"{b['id']:>8}  p{b['page']:<2} {b['kind']:<5} {b['label'][-38:]:>38} [____] {b['after'][:30]}")


if __name__ == "__main__":
    sys.exit(main())
