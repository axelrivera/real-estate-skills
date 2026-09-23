"""Find brand colors in an image (logo, business card, flyer) or on a website.

    python3 scripts/extract_colors.py logo.png
    python3 scripts/extract_colors.py https://janedoerealty.com

Prints JSON: the candidate colors (hex, plain name, how light), a suggested primary, a suggested
buyer/seller split when there are two strong colors, and plain-language notes for the user.
Black, white and greys are skipped; the image is only read, never stored.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import design  # noqa: E402

MERGE_DISTANCE = 0.06  # colors closer than this are one brand color
SPLIT_MIN_SHARE = 0.15  # second color must cover this share of the colored area to offer a split
USER_AGENT = "Mozilla/5.0 (compatible; brand-color-check)"
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
_VAR_RE = re.compile(r"--[\w-]*(primary|brand|accent|main|theme|secondary)[\w-]*\s*:\s*([^;}\n]+)", re.I)


# --- shared ranking ---------------------------------------------------------

def _merge(weighted, members=False):
    """[(hex, weight)] -> [(hex, weight)] with near-identical colors merged, heaviest first.

    With `members`, each group also lists the hex values merged into it: [(hex, weight, [hex, ...])].
    """
    groups = []
    for hx, w in sorted(weighted, key=lambda x: -x[1]):
        for g in groups:
            if design.distance(g[0], hx) < MERGE_DISTANCE:
                g[1] += w
                g[2].append(hx)
                break
        else:
            groups.append([hx, w, [hx]])
    return [tuple(g) if members else (g[0], g[1]) for g in groups]


def _describe(hx, share=None, evidence=None):
    item = {"hex": hx, "name": design.color_name(hx), "light": design.is_light(hx)}
    if share is not None:
        item["share"] = round(share, 3)
    if evidence:
        item["evidence"] = evidence
    return item


def summarize(candidates, neutral_share=0.0):
    """Build the result from ranked chromatic candidates [(hex, share, evidence)]."""
    colors = [_describe(hx, share, ev) for hx, share, ev in candidates[:4]]
    notes, suggestion = [], {}
    if not colors:
        notes.append("No clear brand color was found (only black, white or grey)."
                     " Charcoal or Navy work well for reports; or share another image or the hex codes.")
        suggestion["alternatives"] = [_describe(design.NAMED["Charcoal"]), _describe(design.NAMED["Navy"])]
        return {"colors": [], "suggestion": suggestion, "notes": notes}

    primary = colors[0]
    suggestion["primary"] = primary["hex"]
    if len(colors) > 1:
        second = colors[1]
        strong = second.get("share", 1.0) >= SPLIT_MIN_SHARE
        if strong and design.distance(primary["hex"], second["hex"]) >= design.PARTY_MIN_DISTANCE:
            suggestion["split"] = {"buyer_primary": primary["hex"], "seller_primary": second["hex"]}
            light = next((c for c in (primary, second) if c["light"]), None)
            if light:
                other = second if light is primary else primary
                notes.append(f"{light['name']} is light, so {other['name']} for all reports is also a good choice.")
    for c in colors[:2]:
        if c["light"]:
            notes.append(f"{c['name']} is too light to read as text, so reports would use a darker shade"
                         f" for text and {c['name']} for accents.")
    if neutral_share > 0.6:
        notes.append("Most of the image is black, white or grey; the colors listed are the accents.")
    return {"colors": colors, "suggestion": suggestion, "notes": notes}


# --- images -----------------------------------------------------------------

def from_image(path):
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGBA")
        im.thumbnail((200, 200), Image.NEAREST)  # nearest keeps the logo's real colors (no blended edge pixels)
        raw = im.tobytes()  # RGBA bytes; works across Pillow versions
    pixels = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 4) if raw[i + 3] >= 128]  # skip transparent
    if not pixels:
        return summarize([])
    counts, inside = Counter(), {}
    for rgb, n in Counter(pixels).items():  # bucket to 32 levels to group shades, but remember the real pixels
        bucket = "#%02X%02X%02X" % tuple(c // 8 * 8 + 4 for c in rgb)
        counts[bucket] += n
        inside.setdefault(bucket, Counter())["#%02X%02X%02X" % rgb] += n
    total = sum(counts.values())
    chromatic = [(hx, n) for hx, n in counts.items() if not design.is_neutral(hx)]
    neutral_share = 1 - sum(n for _, n in chromatic) / total
    colored = sum(n for _, n in chromatic) or 1
    ranked = []
    for _, n, buckets in _merge(chromatic, members=True):
        if n / colored < 0.02:
            continue
        real = sum((inside[b] for b in buckets), Counter()).most_common(1)[0][0]  # the most common real pixel
        ranked.append((real, n / colored, "image"))
    result = summarize(ranked, neutral_share)
    result["source"] = os.path.basename(path)
    return result


# --- websites ---------------------------------------------------------------

def _colors_in(text):
    for m in _HEX_RE.finditer(text):
        hx = design.parse_hex(m.group(0))
        if hx:
            yield hx
    for m in _RGB_RE.finditer(text):
        r, g, b = (min(255, int(v)) for v in m.groups())
        yield "#%02X%02X%02X" % (r, g, b)


def _fetch(url, limit=600_000):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(limit).decode(resp.headers.get_content_charset() or "utf-8", "replace")


def from_html(html, base_url, fetch=_fetch):
    """Rank colors from a page: theme-color meta, brand-named CSS variables, then frequency in CSS."""
    scores = Counter()
    evidence = {}

    def add(hx, weight, why):
        if hx and not design.is_neutral(hx):
            scores[hx] += weight
            evidence.setdefault(hx, why)

    for m in re.finditer(r'<meta[^>]+name=["\'](theme-color|msapplication-TileColor)["\'][^>]*>', html, re.I):
        content = re.search(r'content=["\']([^"\']+)', m.group(0), re.I)
        if content:
            for hx in _colors_in(content.group(1)):
                add(hx, 50, "site theme color")

    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S))
    css += "\n".join(re.findall(r'style=["\']([^"\']+)["\']', html, re.I))
    host = urllib.parse.urlparse(base_url).netloc
    sheets = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', html, re.I)
    for tag in sheets[:6]:
        href = re.search(r'href=["\']([^"\']+)', tag, re.I)
        if not href:
            continue
        url = urllib.parse.urljoin(base_url, href.group(1))
        if urllib.parse.urlparse(url).netloc != host:
            continue  # skip third-party CSS (fonts, widgets)
        try:
            css += "\n" + fetch(url)
        except Exception:  # noqa: BLE001 - a missing stylesheet shouldn't stop the check
            continue

    for m in _VAR_RE.finditer(css):
        for hx in _colors_in(m.group(2)):
            add(hx, 20, f"site CSS ({m.group(0).split(':')[0].strip()})")
    for hx in _colors_in(css):
        add(hx, 1, "site CSS")

    merged = _merge(list(scores.items()))
    total = sum(w for _, w in merged) or 1
    ranked = []
    for hx, w in merged:
        ev = next((evidence[h] for h in evidence if design.distance(h, hx) < MERGE_DISTANCE and
                   evidence[h] != "site CSS"), evidence.get(hx, "site CSS"))
        ranked.append((hx, w / total, ev))
    return summarize(ranked)


def from_url(url):
    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url
    try:
        html = _fetch(url)
    except Exception as e:  # noqa: BLE001
        return {"colors": [], "suggestion": {}, "source": url,
                "notes": [f"Couldn't open the website ({e.__class__.__name__}). "
                          "An image of the logo or a business card works instead."]}
    result = from_html(html, url)
    result["source"] = url
    return result


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__)
    target = argv[0]
    result = from_url(target) if re.match(r"^(https?://|www\.)|^[\w-]+(\.[\w-]+)+(/|$)", target) \
        and not os.path.exists(target) else from_image(target)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
