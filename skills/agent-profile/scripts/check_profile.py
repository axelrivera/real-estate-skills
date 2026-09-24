"""Check the agent's profile the way every other skill will read it.

    python3 scripts/check_profile.py profile.md

Prints JSON: ok, the fields that are set, the brand colors each side will use (by name),
and problems (things to fix before handing the file over) and warnings (things to tell the agent).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import design, profiles  # noqa: E402


def check(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return {"ok": False, "problems": [f"The profile can't be opened: {e.strerror or e}."]}
    problems = []
    if re.search(r"\{\{[^}]*\}\}", text):
        problems.append("Template placeholders ({{...}}) are still in the file.")
    try:
        agent = profiles.load_agent(path)
    except profiles.ProfileError as e:
        return {"ok": False, "problems": problems + [str(e)]}

    problems += [f"Missing {f}." for f in agent["errors"]]
    problems += agent["warnings"]  # invalid color codes, numbers written without quotes
    colors, warnings = {}, []
    # CORE-27: the agent's own word for a color ("Gold"), from the comment beside it in the profile
    own = {m.group(1).upper(): m.group(2).strip() for m in re.finditer(r'"(#[0-9A-Fa-f]{6})"\s*#\s*([^\n]+)', text)}
    for side in ("buyer", "seller"):
        hx, source, _ = design.resolve(agent["brand"], side)
        name = own.get(str(hx).upper()) or design.color_name(hx)
        colors[side] = {"hex": hx, "name": name, "default": source == "default"}
        if source != "default" and design.is_light(hx):
            warnings.append(f"{name} is too light to read as text, so reports use a darker shade for text and {name} for accents.")
    return {
        "ok": not problems,
        "fields": [f for f, _ in profiles.agent_lines(agent)],
        "sections": [s for s in ("voice", "disclaimers") if agent[s]],
        "colors": colors,
        "problems": problems,
        "warnings": list(dict.fromkeys(warnings)),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result = check(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)
