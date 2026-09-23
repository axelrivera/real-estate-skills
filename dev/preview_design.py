"""Render shared/design palettes for a set of brand scenarios to HTML and PDF.

    make preview-design   ->  out/design/palettes.html, out/design/palettes.pdf
"""
import html
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from shared import design as d  # noqa: E402

SCENARIOS = [
    ("Defaults (no brand colors)", None),
    ("One color: green", {"primary": "#0B6E4F"}),
    ("Split: green buyer, burgundy seller", {"buyer_primary": "#0B6E4F", "seller_primary": "#8C1D40"}),
    ("Pale gold (too light for text)", {"primary": "#F2C94C"}),
    ("Black", {"primary": "#111111"}),
    ("Same green as 'good' status", {"primary": "#2E7D5B"}),
]

CSS = """
*{box-sizing:border-box} body{font:10pt/1.4 -apple-system,Helvetica,Arial,sans-serif;color:#1A1A1A;margin:0}
.scn{break-inside:avoid;margin:0 0 18px} .scn>h2{font-size:12pt;margin:0 0 6px}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.doc{border:1px solid #ddd;border-radius:6px;overflow:hidden}
.bar{background:var(--brand-ink);color:var(--on-brand);padding:6px 10px;font-weight:700;display:flex;justify-content:space-between}
.body{padding:8px 10px}
h3{color:var(--brand-strong);margin:0 0 4px;font-size:11pt}
.muted{color:var(--muted);font-size:8.5pt}
.callout{background:var(--brand-callout);border-left:4px solid var(--brand);padding:5px 8px;margin:6px 0}
.panel{background:var(--brand-panel);border:1px solid var(--brand-rule);padding:5px 8px;margin:6px 0}
.bars{display:flex;align-items:flex-end;gap:4px;height:44px;margin:6px 0}
.bars i{display:block;width:22px}
.chips span{display:inline-block;padding:1px 6px;border-radius:9px;font-size:8pt;margin-right:4px;border:1px solid}
.dots span{margin-right:10px;font-size:8.5pt} .dots i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:-1px}
.sw{display:flex;gap:2px;margin-top:6px} .sw i{flex:1;height:14px}
.warn{color:#8A5A12;font-size:8.5pt;margin-top:4px}
"""


def side_html(brand, side):
    t = d.theme(brand, side)
    v = d.flat(t)
    chips = "".join(
        f'<span style="color:{v[f"{n}_strong"]};background:{v[f"{n}_bg"]};border-color:{v[f"{n}_border"]}">{n}</span>'
        for n in ("good", "caution", "risk"))
    dots = "".join(f'<span><i style="background:{v[f"party_{p}"]}"></i>{p.title()}</span>' for p in ("buyer", "seller", "both"))
    bars = "".join(f'<i style="height:{h}%;background:{v[k]}"></i>' for k, h in
                   (("brand", 100), ("brand_accent", 75), ("brand_soft", 55), ("grey", 65), ("grey_light", 40)))
    swatches = "".join(f'<i title="{k} {v[k]}" style="background:{v[k]}"></i>' for k in
                       ("brand_deep", "brand_strong", "brand_ink", "brand", "brand_accent", "brand_soft",
                        "brand_rule", "brand_callout", "brand_panel"))
    notes = "".join(f'<div class="warn">{html.escape(w)}</div>' for w in t["warnings"] + t["adjustments"])
    return f"""<div class="doc">
<div style="{d.css_vars(t)[6:-1]}">
<div class="bar"><span>123 Oak St</span><span>{side.title()}</span></div>
<div class="body">
<h3>Recommended price</h3><div class="muted">brand {t['brand']} · source: {t['source']}</div>
<div class="callout">Callout text on the brand callout tint.</div>
<div class="panel">Panel with a brand rule border.</div>
<div class="bars">{bars}</div>
<div class="chips">{chips}</div>
<div class="dots" style="margin-top:6px">{dots}</div>
<div class="sw">{swatches}</div>{notes}
</div></div></div>"""


def main():
    out_dir = os.path.join(ROOT, os.environ.get("OUT", "out"), "design")
    os.makedirs(out_dir, exist_ok=True)
    sections = "".join(
        f'<div class="scn"><h2>{html.escape(name)}</h2><div class="sides">'
        f'{side_html(brand, "buyer")}{side_html(brand, "seller")}</div></div>'
        for name, brand in SCENARIOS)
    page = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{sections}</body></html>"
    html_path = os.path.join(out_dir, "palettes.html")
    with open(html_path, "w") as f:
        f.write(page)

    from playwright.sync_api import sync_playwright
    pdf_path = os.path.join(out_dir, "palettes.pdf")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(page)
        pg.pdf(path=pdf_path, format="Letter", margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
               print_background=True)
        browser.close()
    print(html_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
