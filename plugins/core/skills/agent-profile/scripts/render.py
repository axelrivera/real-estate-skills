"""Write agent-profile.md from the profile data.

    python3 scripts/render.py profile.json [--out DIR]

profile.json holds only what the agent gave (name and brokerage are required):
    {"name": "...", "brokerage": "...", "team": "...", "license": "...", "phone": "...",
     "email": "...", "website": "...",
     "brand": {"primary": "#1F3A5F", "buyer_primary": "...", "seller_primary": "..."},
     "voice": "...", "disclaimers": "..."}

Prints the file path, then any warnings (plain language) on stderr.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import design, profiles, render  # noqa: E402

FIELDS = ("name", "team", "brokerage", "license", "phone", "email", "website")
BRAND_KEYS = ("primary", "buyer_primary", "seller_primary")
FILENAME = "agent-profile.md"


def _scalar(value):
    return json.dumps(str(value).strip(), ensure_ascii=False)  # JSON strings are valid YAML scalars


def to_markdown(data):
    missing = [f for f in profiles.AGENT_REQUIRED if not str(data.get(f) or "").strip()]
    if missing:
        raise ValueError(f"The agent profile needs {' and '.join(missing)}.")

    lines = ["---", "profile: agent", f"schema: {profiles.SCHEMA}"]
    lines += [f"{f}: {_scalar(data[f])}" for f in FIELDS if str(data.get(f) or "").strip()]
    brand = {k: design.parse_hex(v) for k, v in (data.get("brand") or {}).items() if k in BRAND_KEYS and v}
    bad = [k for k, v in brand.items() if not v]
    if bad:
        raise ValueError(f"These brand colors aren't valid hex codes: {', '.join(bad)}.")
    if brand:
        lines.append("brand:")
        lines += [f'  {k}: "{brand[k]}"  # {design.color_name(brand[k])}' for k in BRAND_KEYS if k in brand]
    lines.append("---")

    title = data["name"].strip()
    org = " · ".join(str(data[f]).strip() for f in ("team", "brokerage") if str(data.get(f) or "").strip())
    body = ["", f"# Agent profile: {title}", "", org, ""]
    body += ["Used as context by the real estate skills. Keep it in your Project files so every chat can use it.", ""]
    if brand:
        buyer, seller = (design.resolve(brand, s)[0] for s in ("buyer", "seller"))
        colors = (f"{design.color_name(buyer)} for all reports" if buyer == seller else
                  f"{design.color_name(buyer)} for buyer reports, {design.color_name(seller)} for seller reports")
        body += ["## Brand colors", "", colors + ".", ""]
    for section in ("voice", "disclaimers"):
        text = str(data.get(section) or "").strip()
        if text:
            body += [f"## {section.title()}", "", text, ""]
    return "\n".join(lines + body).rstrip() + "\n"


def build(data, fmt, out_dir):
    path = render.write_text(to_markdown(data), os.path.join(out_dir, FILENAME))
    check = profiles.load_agent(path)  # read back through the same reader every skill uses
    for w in check["warnings"] + _light_warnings(check["brand"]):
        print(w, file=sys.stderr)
    return [path]


def _light_warnings(brand):
    out = []
    for key in BRAND_KEYS:
        hx = design.parse_hex(brand.get(key)) if brand.get(key) else None
        if hx and design.is_light(hx):
            out.append(f"{design.color_name(hx)} is too light to read as text, so reports use a darker shade "
                       f"for text and {design.color_name(hx)} for accents.")
    return list(dict.fromkeys(out))


if __name__ == "__main__":
    try:
        render.main(build, formats=("md",))
    except ValueError as e:
        sys.exit(str(e))
