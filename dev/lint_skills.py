"""Check every SKILL.md before packaging (DOC-9).

    .venv/bin/python dev/lint_skills.py            # make lint-skills

Checks: frontmatter with `name` (lowercase, hyphens, same as the folder, no output format like "-pdf") and
`description` (1,024 characters or fewer, no angle brackets); a `## Guardrails` section as the first section;
every `references/...`, `assets/...` or `scripts/...` path the SKILL.md names exists in the skill.
"""
import glob
import os
import re
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def lint(path):
    skill = os.path.dirname(path)
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return [f"{rel}: no frontmatter"]
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:  # a ": " in an unquoted description breaks the frontmatter
        return [f"{rel}: frontmatter isn't valid YAML ({str(e).splitlines()[0]}); quote the description or drop the colon"]
    out = []
    name, desc = str(meta.get("name") or ""), str(meta.get("description") or "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        out.append(f"{rel}: name {name!r} should be lowercase words joined by hyphens")
    if name != os.path.basename(skill):
        out.append(f"{rel}: name {name!r} doesn't match the folder {os.path.basename(skill)!r}")
    if re.search(r"-(pdf|pptx|docx|xlsx|md)$", name):
        out.append(f"{rel}: the name carries an output format")
    if not desc:
        out.append(f"{rel}: no description")
    elif len(desc) > 1024:
        out.append(f"{rel}: description is {len(desc)} characters (limit 1,024)")
    if "<" in desc or ">" in desc:
        out.append(f"{rel}: angle brackets in the description")
    sections = re.findall(r"^## (.+)$", text[m.end():], re.M)
    if not sections or sections[0].strip() != "Guardrails":
        out.append(f"{rel}: the first section should be ## Guardrails")
    for ref in sorted(set(re.findall(r"`((?:references|assets|scripts)/[\w./-]+\.\w+)`", text))):
        if not os.path.exists(os.path.join(skill, ref)):
            out.append(f"{rel}: names {ref}, which isn't in the skill")
    return out


def main():
    problems = [p for path in sorted(glob.glob(os.path.join(ROOT, "plugins", "*", "skills", "*", "SKILL.md"))) for p in lint(path)]
    print("\n".join(problems) if problems else "lint-skills: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
