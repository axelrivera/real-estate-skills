"""Read an existing agent profile back into the data format render.py takes, to update it.

    python3 scripts/read_profile.py agent-profile.md

Prints JSON: {"data": {...}, "missing_required": [...], "warnings": [...], "colors": {...}}.
"colors" names each brand color in plain words for confirming changes with the agent.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import design, profiles  # noqa: E402


def read(path):
    agent = profiles.load_agent(path)
    data = {f: agent[f] for f in profiles.AGENT_FIELDS if agent.get(f) not in (None, "")}
    if agent["brand"]:
        data["brand"] = dict(agent["brand"])
    for section in ("voice", "disclaimers"):
        if agent[section]:
            data[section] = agent[section]
    colors = {k: {"hex": h, "name": design.color_name(h)}
              for k, v in agent["brand"].items() if (h := design.parse_hex(v))}
    return {"data": data, "missing_required": agent["errors"], "warnings": agent["warnings"], "colors": colors}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        print(json.dumps(read(sys.argv[1]), indent=2, ensure_ascii=False))
    except profiles.ProfileError as e:
        sys.exit(str(e))
