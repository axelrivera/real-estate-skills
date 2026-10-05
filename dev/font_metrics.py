"""Write shared/fonts/metrics.json: the bundled font's advance width for every character it draws, regular and bold,
in thousandths of an em, so shared/layout.text_width can measure chart labels and table cells without a browser.

    .venv/bin/python dev/font_metrics.py           # rewrite the file (after changing the font files)
    .venv/bin/python dev/font_metrics.py --check   # exit 1 when the committed file is stale

Measured in Chromium (Playwright), the engine that prints the PDFs: each character drawn alone on a canvas at
1000px. A character the font doesn't have is left out (the browser would draw it in a fallback font: measured once
with a serif and once with a monospace fallback, the two widths differ).

The font files are Inter 4.1 (rsms/inter, SIL Open Font License 1.1, shared/fonts/LICENSE.txt), subset to Latin
with pyftsubset (fonttools, run once with uvx, not a project dependency):

    uvx --from "fonttools[woff]" pyftsubset Inter-Regular.ttf --unicodes="$UNICODES" \\
        --layout-features="kern,tnum,liga,calt,case,ccmp,locl,mark,mkmk" --flavor=woff2 --output-file=Inter-Regular.woff2

with UNICODES below (the same for Inter-Bold.ttf).
"""
import argparse
import base64
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONTS = os.path.join(ROOT, "shared", "fonts")
OUT = os.path.join(FONTS, "metrics.json")
FILES = {"regular": "Inter-Regular.woff2", "bold": "Inter-Bold.woff2"}
UNICODES = ("U+0020-007E,U+00A0-017F,U+0192,U+02C6,U+02C7,U+02D8-02DD,U+2000-206F,U+20AC,U+2116,U+2122,U+2190-2199,"
            "U+2212,U+2248,U+2260,U+2264,U+2265,U+25A0-25FF,U+2605,U+2713,U+2715")

MEASURE = """async ([fonts, chars]) => {
  const out = {};
  for (const [weight, data] of Object.entries(fonts)) {
    const face = new FontFace('Metrics Font', `url(data:font/woff2;base64,${data})`, {weight: weight === 'bold' ? '700' : '400'});
    document.fonts.add(await face.load());
  }
  const ctx = document.createElement('canvas').getContext('2d');
  for (const weight of Object.keys(fonts)) {
    const w = weight === 'bold' ? '700' : '400', widths = {};
    for (const ch of chars) {
      ctx.font = `${w} 1000px "Metrics Font", serif`; const a = ctx.measureText(ch).width;
      ctx.font = `${w} 1000px "Metrics Font", monospace`; const b = ctx.measureText(ch).width;
      if (Math.abs(a - b) < 0.01) widths[ch] = Math.round(a);
    }
    out[weight] = widths;
    // tables print digits tabular (report.css font-variant-numeric: tabular-nums): their widths, from the DOM
    const span = document.createElement('span');
    span.style.cssText = `font: ${w} 1000px "Metrics Font"; font-variant-numeric: tabular-nums; white-space: pre`;
    document.body.appendChild(span); const tnum = {};
    for (const ch of '0123456789') { span.textContent = ch; tnum[ch] = Math.round(span.getBoundingClientRect().width); }
    span.remove(); out[weight + '_tnum'] = tnum;
  }
  return out;
}"""


def codepoints(spec=UNICODES):
    """The characters the subset covers, less the zero-width and format characters (they have no width to measure)."""
    out = []
    for part in spec.split(","):
        a, _, b = part.removeprefix("U+").partition("-")
        out += list(range(int(a, 16), int(b or a, 16) + 1))
    zero = set(range(0x200B, 0x2010)) | set(range(0x2028, 0x202F)) | set(range(0x2060, 0x2070))
    return [chr(c) for c in out if c not in zero]


def measure():
    from playwright.sync_api import sync_playwright
    fonts = {}
    for weight, name in FILES.items():
        with open(os.path.join(FONTS, name), "rb") as f:
            fonts[weight] = base64.b64encode(f.read()).decode("ascii")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            widths = page.evaluate(MEASURE, [fonts, codepoints()])
        finally:
            browser.close()
    return {"family": "Inter", "files": FILES, "units_per_em": 1000,
            "regular": widths["regular"], "bold": widths["bold"],
            "tnum": {"regular": widths["regular_tnum"], "bold": widths["bold_tnum"]}}


def dump(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail when the committed metrics are stale")
    args = ap.parse_args(argv)
    text = dump(measure())
    if args.check:
        with open(OUT, encoding="utf-8") as f:
            ok = f.read() == text
        print("shared/fonts/metrics.json is " + ("current" if ok else "stale: run dev/font_metrics.py"))
        return 0 if ok else 1
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
