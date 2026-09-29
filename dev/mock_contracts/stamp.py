"""Drawing on a form page: typed values, checkmarks, signatures and initials that look like a Dotloop export.

Typed values go in as real text (Helvetica), so pdftotext reads them next to the form's own words, as it does on an
agent's upload. Signatures and initials use handwriting fonts with a small "dotloop verified" stamp (date, time and
a verification code) like the real ones. Local dev only.
"""
import hashlib
import os
from datetime import datetime

import pymupdf

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
SIGNATURE_FONTS = ("Allura-Regular.ttf", "MrDafoe-Regular.ttf", "HomemadeApple-Regular.ttf")
INK = (0.06, 0.08, 0.30)       # typed values: the dark navy Dotloop uses for filled fields
SIG_INK = (0.05, 0.10, 0.45)   # signatures and initials
STAMP = (0.35, 0.35, 0.40)     # "dotloop verified" lines
TYPE_FONT, TYPE_BOLD = "helv", "hebo"
MAX_SIZE, MIN_SIZE = 10.0, 5.5


def _font(page, index):
    """Register handwriting font `index` on the page (idempotent) and return its name."""
    name = f"sig{index}"
    if name not in {f[4] for f in page.get_fonts()} and name not in getattr(page, "_mock_fonts", set()):
        page.insert_font(fontname=name, fontfile=os.path.join(FONTS, SIGNATURE_FONTS[index % len(SIGNATURE_FONTS)]))
        page._mock_fonts = getattr(page, "_mock_fonts", set()) | {name}
    return name


def _fit(text, width, font=TYPE_FONT, size=MAX_SIZE, fontfile=None):
    f = pymupdf.Font(fontfile=fontfile) if fontfile else pymupdf.Font(font)
    while size > MIN_SIZE and f.text_length(text, fontsize=size) > width:
        size -= 0.25
    return size


def text(page, rect, value, align="left", bold=False):
    """Type one value into a blank, shrinking it to fit the blank's width."""
    value = str(value)
    r = pymupdf.Rect(rect)
    font = TYPE_BOLD if bold else TYPE_FONT
    size = min(MAX_SIZE, max(MIN_SIZE, r.height * 0.78)) if r.height > 4 else MAX_SIZE
    size = _fit(value, r.width - 4, font, size)
    width = pymupdf.Font(font).text_length(value, fontsize=size)
    x = r.x0 + 2 if align == "left" else r.x1 - 2 - width if align == "right" else (r.x0 + r.x1 - width) / 2
    base = r.y1 - max(1.8, (r.height - size * 0.72) / 2) if r.height > 4 else r.y1 - 1.8
    page.insert_text((x, base), value, fontname=font, fontsize=size, color=INK)


def strike(page, x0, x1, y):
    """A line through typed text, as when a counter-offer crosses out the offered value."""
    page.draw_line((x0, y), (x1, y), color=INK, width=0.9)


def change(page, rect, old, new):
    """A counter-offer change on the contract itself: the offered value struck through and the new one typed after
    it, both shrunk to share the blank. With no offered value, only the new one."""
    if old in (None, ""):
        return text(page, rect, new)
    r = pymupdf.Rect(rect)
    font = pymupdf.Font(TYPE_FONT)
    size = min(MAX_SIZE, max(MIN_SIZE, r.height * 0.78)) if r.height > 4 else MAX_SIZE
    while size > MIN_SIZE and font.text_length(f"{old}  {new}", fontsize=size) > r.width - 4:
        size -= 0.25
    base = r.y1 - max(1.8, (r.height - size * 0.72) / 2) if r.height > 4 else r.y1 - 1.8
    x_old = r.x0 + 2
    w_old = font.text_length(str(old), fontsize=size)
    page.insert_text((x_old, base), str(old), fontname=TYPE_FONT, fontsize=size, color=INK)
    strike(page, x_old - 1, x_old + w_old + 1, base - size * 0.3)
    page.insert_text((x_old + w_old + font.text_length("  ", fontsize=size), base), str(new), fontname=TYPE_FONT,
                     fontsize=size, color=INK)


def flow(page_rects, value):
    """Type a long value across several blanks in order (a legal description on lines 9-11): fills each blank
    word by word at a readable size, and shrinks the last one if the text still doesn't fit."""
    words = str(value).split()
    font = pymupdf.Font(TYPE_FONT)
    for i, (page, rect) in enumerate(page_rects):
        r = pymupdf.Rect(rect)
        size = min(9.5, max(MIN_SIZE, r.height * 0.78)) if r.height > 4 else 9.5
        line = []
        while words and font.text_length(" ".join(line + [words[0]]), fontsize=size) <= r.width - 4:
            line.append(words.pop(0))
        if i == len(page_rects) - 1 and words:
            line += words
            words = []
        if line:
            text(page, r, " ".join(line))
    return not words


def area(page, rect, value):
    """Type multi-line text into a text area (ACSP-4 terms, CO-3 items), wrapping it and shrinking to fit."""
    r = pymupdf.Rect(rect)
    inner = pymupdf.Rect(r.x0 + 3, r.y0 + 3, r.x1 - 3, r.y1 - 2)
    for size in (10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
        shape = page.new_shape()
        if shape.insert_textbox(inner, str(value), fontname=TYPE_FONT, fontsize=size, color=INK, lineheight=1.25) >= 0:
            shape.commit()
            return True
    page.insert_textbox(inner, str(value), fontname=TYPE_FONT, fontsize=6, color=INK)
    return False


def check(page, rect):
    """Check a box: a bold X centered in it (Dotloop exports print checked boxes as text)."""
    r = pymupdf.Rect(rect)
    size = max(6, min(11, r.height * 0.95))
    w = pymupdf.Font(TYPE_BOLD).text_length("X", fontsize=size)
    page.insert_text(((r.x0 + r.x1 - w) / 2, r.y1 - (r.height - size * 0.72) / 2), "X", fontname=TYPE_BOLD,
                     fontsize=size, color=INK)


def verification_code(*parts):
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest().upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def _when(dt, tz):
    return f"{dt.strftime('%m/%d/%y')} {dt.strftime('%I:%M %p').lstrip('0')} {tz}"


def signature(page, rect, name, dt, font_index=0, tz="EDT", seed=""):
    """A handwritten signature in a signature box, with Dotloop's verification stamp at its left edge."""
    r = pymupdf.Rect(rect)
    fontname = _font(page, font_index)
    fontfile = os.path.join(FONTS, SIGNATURE_FONTS[font_index % len(SIGNATURE_FONTS)])
    stamp_w = min(62, r.width * 0.3)
    sig_area = pymupdf.Rect(r.x0 + stamp_w + 2, r.y0, r.x1 - 2, r.y1)
    size = _fit(name, sig_area.width, size=min(18, r.height * 0.8), fontfile=fontfile)
    page.insert_text((sig_area.x0 + 2, r.y1 - r.height * 0.28), name, fontname=fontname, fontsize=size, color=SIG_INK)
    _stamp(page, pymupdf.Rect(r.x0 + 1.5, r.y0, r.x0 + stamp_w, r.y1), dt, tz, verification_code(seed, name, dt))


def initials(page, rect, letters, dt, font_index=0, tz="EDT", seed=""):
    """Handwritten initials in an initials box, with a tiny date line under them."""
    r = pymupdf.Rect(rect)
    fontname = _font(page, font_index)
    fontfile = os.path.join(FONTS, SIGNATURE_FONTS[font_index % len(SIGNATURE_FONTS)])
    size = _fit(letters, r.width - 6, size=min(16, r.height * 0.7), fontfile=fontfile)
    w = pymupdf.Font(fontfile=fontfile).text_length(letters, fontsize=size)
    page.insert_text(((r.x0 + r.x1 - w) / 2, r.y0 + r.height * 0.62), letters, fontname=fontname, fontsize=size,
                     color=SIG_INK)
    tiny = min(3.4, r.height * 0.14)
    page.insert_text((r.x0 + 1.5, r.y1 - 1.5), f"{dt.strftime('%m/%d/%y')} {dt.strftime('%I:%M %p').lstrip('0')} {tz}",
                     fontname=TYPE_FONT, fontsize=tiny, color=STAMP)
    page.insert_text((r.x0 + 1.5, r.y0 + tiny + 0.8), "dotloop verified", fontname=TYPE_FONT, fontsize=tiny, color=STAMP)


def _stamp(page, r, dt, tz, code):
    size = max(3.2, min(4.6, r.height * 0.2))
    lines = ["dotloop verified", _when(dt, tz), code]
    top = r.y0 + (r.height - size * 1.15 * len(lines)) / 2 + size
    for i, line in enumerate(lines):
        page.insert_text((r.x0, top + i * size * 1.15), line, fontname=TYPE_FONT, fontsize=size, color=STAMP)


def redact_license(page):
    """Remove the "Licensed to dotloop, Inc. and <member>" line: it names the real account the forms came from."""
    hits = page.search_for("Licensed to dotloop")
    for h in hits:
        page.add_redact_annot(pymupdf.Rect(h.x0 - 1, h.y0 - 1, page.rect.x1 - 10, h.y1 + 1), fill=(1, 1, 1))
    if hits:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)


def parse_dt(value):
    """'2026-09-25 16:12' or '2026-09-25' (noon) -> datetime."""
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    return datetime.strptime(s, "%Y-%m-%d %H:%M") if " " in s else datetime.strptime(s + " 12:00", "%Y-%m-%d %H:%M")
