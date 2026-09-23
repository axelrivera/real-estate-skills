"""Color palette for file-mode outputs, derived from the agent's brand color.

Usage in a skill:
    from _shared import design
    t = design.theme(profile.get("brand"), side="buyer")
    html_head = f"<style>{design.css_vars(t)}</style>"

Every renderer takes colors from theme()/party_colors(); none hard-codes brand hex values.
See docs/architecture.md#brand-colors for the rules implemented here.
"""
import colorsys
import math
import re

DEFAULTS = {"buyer": "#1A74AD", "seller": "#C2410C"}
# "Both" marker: navy by default; the others are fallbacks when navy is too close to a party color.
BOTH_CANDIDATES = ["#1F3A5F", "#5A6672", "#6B4A3A", "#0F766E", "#6B21A8", "#9A6B00"]

NEUTRALS = {
    "text": "#1A1A1A",
    "muted": "#5A6672",
    "bg": "#FFFFFF",
    "grey": "#A3ADB6",
    "grey_light": "#B8C2CC",
}

# Status colors never follow the brand. Each has a base, a darker text shade, a background and a border.
STATUS = {
    "good": {"base": "#2E7D5B", "strong": "#1D5C41", "bg": "#E6F4EC", "border": "#CDEBDA"},
    "caution": {"base": "#B7791F", "strong": "#8A5A12", "bg": "#FDF3DC", "border": "#E9B95C"},
    "risk": {"base": "#B3261E", "strong": "#8C1D17", "bg": "#FBE9E7", "border": "#F1C4BC"},
}

# Share of white mixed into the brand color for each tint (calibrated on the prototype buyer theme).
TINTS = {"accent": 0.44, "soft": 0.76, "rule": 0.88, "callout": 0.93, "panel": 0.96}

# Share of white mixed into each party color: soft for text on dark party fills, bg for row and panel backgrounds.
PARTY_TINTS = {"soft": 0.80, "bg": 0.88}

# WCAG contrast targets against white.
AA, AAA, DEEP = 4.5, 7.0, 10.0

STATUS_MIN_DISTANCE = 0.05  # OKLab distance below which a status color is shifted away from the brand
PARTY_MIN_DISTANCE = 0.12  # OKLab distance below which two party colors count as "the same"

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# --- color math -------------------------------------------------------------

def parse_hex(value):
    """Return '#RRGGBB' for a hex string (with or without '#', 3 or 6 digits), else None."""
    if not isinstance(value, str):
        return None
    m = _HEX.match(value.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def _rgb(hex_):
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(hex_):
    r, g, b = (_lin(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b="#FFFFFF"):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def to_oklab(hex_):
    r, g, b = (_lin(c) for c in _rgb(hex_))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _oklab_to_linear(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def to_oklch(hex_):
    L, a, b = to_oklab(hex_)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_oklch(L, C, H):
    """OKLCH to hex, reducing chroma until the color fits in sRGB."""
    L = max(0.0, min(1.0, L))
    cos_h, sin_h = math.cos(math.radians(H)), math.sin(math.radians(H))

    def linear(c):
        return _oklab_to_linear(L, c * cos_h, c * sin_h)

    def fits(c):
        return all(-1e-6 <= v <= 1 + 1e-6 for v in linear(c))

    if not fits(C):
        lo, hi = 0.0, C
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if fits(mid) else (lo, mid)
        C = lo
    return _hex(_unlin(max(0.0, min(1.0, v))) for v in linear(C))


def distance(a, b):
    """Perceptual distance (OKLab). About 0.02 is barely visible; 0.1+ reads as a different color."""
    return math.dist(to_oklab(a), to_oklab(b))


def mix_white(hex_, t):
    """Tint: mix t (0..1) of white into the color, in sRGB like CSS color-mix()."""
    return _hex(c + (1 - c) * t for c in _rgb(hex_))


def darken_to(hex_, target, against="#FFFFFF"):
    """Darken (keeping hue) until contrast against `against` reaches target. Unchanged if already there."""
    if contrast(hex_, against) >= target:
        return hex_
    L, C, H = to_oklch(hex_)
    lo, hi = 0.0, L
    best = from_oklch(0.0, C, H)
    for _ in range(30):
        mid = (lo + hi) / 2
        cand = from_oklch(mid, C, H)
        if contrast(cand, against) >= target:
            best, lo = cand, mid
        else:
            hi = mid
    return best


def rotate(hex_, degrees):
    L, C, H = to_oklch(hex_)
    return from_oklch(L, C, (H + degrees) % 360)


def is_light(hex_):
    return contrast(hex_) < AA


def is_neutral(hex_):
    """True for black, white and greys (no clear hue)."""
    return to_oklch(hex_)[1] < 0.03


def hue_name(hex_):
    """Rough plain-language family for messages ('blue', 'orange', ...)."""
    if is_neutral(hex_):
        L = to_oklab(hex_)[0]
        return "black" if L < 0.3 else "white" if L > 0.95 else "grey"
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_))
    deg = h * 360
    for limit, name in [(15, "red"), (45, "orange"), (70, "gold"), (160, "green"),
                        (200, "teal"), (255, "blue"), (290, "purple"), (335, "pink"), (360, "red")]:
        if deg < limit:
            return name
    return "red"


# Names a non-technical user would recognise, for confirming colors in plain words.
NAMED = {
    "Black": "#111111", "Charcoal": "#36454F", "Slate Gray": "#5A6672", "Gray": "#8A8F96",
    "Silver": "#C0C4C8", "White": "#FFFFFF", "Ivory": "#F8F4E6", "Cream": "#F3E9D2",
    "Beige": "#D9C7A7", "Tan": "#C19A6B", "Brown": "#6B4A3A", "Chocolate": "#4A2C20",
    "Navy": "#1F3A5F", "Midnight Blue": "#172554", "Royal Blue": "#2451B7", "Cobalt": "#0047AB",
    "Blue": "#1A74AD", "Steel Blue": "#4682B4", "Sky Blue": "#7FB8E6", "Light Blue": "#BCD9F0",
    "Teal": "#0F766E", "Turquoise": "#2EC4B6", "Aqua": "#7FDBDA", "Mint": "#A8E6CF",
    "Forest Green": "#1E5631", "Dark Green": "#0B6E4F", "Emerald": "#0B8457", "Green": "#2E7D32",
    "Sage": "#9CAF88", "Olive": "#6B6B2A", "Lime": "#9BCB3B", "Gold": "#D4AF37",
    "Mustard": "#B8860B", "Yellow": "#F2C94C", "Champagne": "#E8D7B0", "Orange": "#E8751A",
    "Burnt Orange": "#C2410C", "Rust": "#A0461F", "Terracotta": "#C8634A", "Coral": "#F2765F",
    "Peach": "#F6B99A", "Red": "#C62828", "Crimson": "#A51C30", "Brick Red": "#8E2B1F",
    "Burgundy": "#8C1D40", "Maroon": "#6D1A2A", "Pink": "#E88AA8", "Blush": "#F2C4CE",
    "Magenta": "#C2185B", "Plum": "#6A2C5E", "Purple": "#6B21A8", "Lavender": "#B8A6D9",
}


def color_name(hex_):
    """Closest plain-language name ('Navy', 'Burnt Orange') for confirming a color with the user."""
    return min(NAMED, key=lambda name: distance(hex_, NAMED[name]))


# --- brand resolution -------------------------------------------------------

def resolve(brand, side):
    """Pick the brand color for a side: side override, then primary, then default.

    Returns (hex, source, warnings) where source is 'side', 'primary' or 'default'.
    """
    if side not in DEFAULTS:
        raise ValueError(f"side must be 'buyer' or 'seller', got {side!r}")
    brand = brand or {}
    warnings = []
    for key, source in ((f"{side}_primary", "side"), ("primary", "primary")):
        raw = brand.get(key)
        if raw in (None, ""):
            continue
        value = parse_hex(raw)
        if value:
            return value, source, warnings
        warnings.append(f"Couldn't read {raw!r} as a color, so it was ignored.")
    return DEFAULTS[side], "default", warnings


def _shift_status(brand_hex):
    """Status sets, with any set too close to the brand rotated away from it."""
    out, notes = {}, []
    b_hue = to_oklch(brand_hex)[2]
    for name, tokens in STATUS.items():
        if distance(brand_hex, tokens["base"]) >= STATUS_MIN_DISTANCE:
            out[name] = dict(tokens)
            continue
        s_hue = to_oklch(tokens["base"])[2]
        direction = 1 if ((s_hue - b_hue + 540) % 360 - 180) >= 0 else -1
        step = 0
        while step < 40 and distance(brand_hex, rotate(tokens["base"], direction * step)) < STATUS_MIN_DISTANCE:
            step += 5
        out[name] = {k: rotate(v, direction * step) for k, v in tokens.items()}
        notes.append(f"{name} shifted {direction * step} degrees away from the brand color")
    return out, notes


def theme(brand=None, side="buyer"):
    """All color tokens for one document side.

    `brand` is the agent profile's `brand` mapping (or None). Returns a JSON-serialisable dict:
    brand tokens, neutrals, status sets, party colors, and `warnings` in plain language
    (for agent-profile to relay) plus `adjustments` (internal notes, for debugging).
    """
    primary, source, warnings = resolve(brand, side)
    status, adjustments = _shift_status(primary)
    tokens = {
        "side": side,
        "source": source,
        "brand": primary,                      # accents, rules, chart marks, borders
        "brand_ink": darken_to(primary, AA),   # brand-colored text on white, fills behind white text
        "brand_strong": darken_to(primary, AAA),  # headings, emphasis
        "brand_deep": darken_to(primary, DEEP),   # darkest brand shade
        "on_brand": "#FFFFFF",
        **{f"brand_{k}": mix_white(primary, t) for k, t in TINTS.items()},
        **NEUTRALS,
        "status": status,
        "party": party_colors(brand),
        "warnings": warnings,
        "adjustments": adjustments,
    }
    tokens["party_tints"] = {p: {k: mix_white(c, t) for k, t in PARTY_TINTS.items()} for p, c in tokens["party"].items()}
    if tokens["brand_ink"] != primary:
        warnings.append(
            f"This {hue_name(primary)} is too light to read as text, "
            f"so text uses a darker shade and the original is used for accents."
        )
    return tokens


def party_colors(brand=None):
    """Colors for Buyer / Seller / Both markers in documents that show both parties.

    Keeps the three clearly distinguishable even when the agent uses one color for both sides.
    """
    buyer = resolve(brand, "buyer")[0]
    seller = resolve(brand, "seller")[0]
    if distance(buyer, seller) < PARTY_MIN_DISTANCE:
        L, C, H = to_oklch(seller)
        seller = from_oklch(L - 0.22 if L > 0.45 else L + 0.25, C, H)
    def gap(c):
        return min(distance(c, buyer), distance(c, seller))

    both = next((c for c in BOTH_CANDIDATES if gap(c) >= PARTY_MIN_DISTANCE), None)
    if both is None:
        both = max(BOTH_CANDIDATES, key=gap)
    return {"buyer": buyer, "seller": seller, "both": both}


# --- output formats ---------------------------------------------------------

def flat(tokens):
    """Flatten nested tokens to {name: hex}: status.good.bg -> good_bg, party.buyer -> party_buyer,
    party_tints.both.bg -> party_both_bg."""
    out = {k: v for k, v in tokens.items() if isinstance(v, str) and v.startswith("#")}
    for name, group in tokens["status"].items():
        out.update({f"{name}_{k}": v for k, v in group.items()})
    out.update({f"party_{k}": v for k, v in tokens["party"].items()})
    for party, tints in tokens.get("party_tints", {}).items():
        out.update({f"party_{party}_{k}": v for k, v in tints.items()})
    return out


def css_vars(tokens):
    """':root{--brand:#...;--good-bg:#...}' for HTML renderers."""
    body = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in flat(tokens).items())
    return f":root{{{body}}}"


def pptx_colors(tokens):
    """{name: 'RRGGBB'} for pptxgenjs, which takes hex without '#'."""
    return {k: v.lstrip("#") for k, v in flat(tokens).items()}
