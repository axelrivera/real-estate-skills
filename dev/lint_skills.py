"""Check every SKILL.md before packaging (DOC-9).

    .venv/bin/python dev/lint_skills.py            # make lint-skills

Checks: frontmatter with `name` (lowercase, hyphens, same as the folder, no output format like "-pdf") and
`description` (1,024 characters or fewer, no angle brackets); a `## Guardrails` section as the first section;
every `references/...`, `assets/...` or `scripts/...` path the SKILL.md names exists in the skill. Also checks that
no shipped Python (skills/, shared/) imports a dev-only library the sandbox doesn't have (dev/requirements-tools.txt),
and that no shipped markdown names a repo path under shared/ (a skill can't see it; FH-104).
"""
import glob
import os
import re
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEV_ONLY = re.compile(r"^\s*(?:import|from)\s+(fitz|pymupdf)\b", re.M)  # dev/requirements-tools.txt: local only
REPO_PATH = re.compile(r"(?<![\w/])shared/[\w./-]+")  # scripts/_shared/ is the skill's own copy, not a repo path


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


def dev_only_imports(root=ROOT):
    """Shipped Python that imports a dev-only library (PyMuPDF): it would pass locally and fail in the sandbox."""
    out = []
    for path in sorted(glob.glob(os.path.join(root, "skills", "**", "*.py"), recursive=True)
                       + glob.glob(os.path.join(root, "shared", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            m = DEV_ONLY.search(f.read())
        if m:
            out.append(f"{os.path.relpath(path, root)}: imports {m.group(1)}, a dev-only library (dev/requirements-tools.txt)")
    return out


def repo_paths(root=ROOT):
    """Shipped markdown (SKILL.md, references/, assets/) that names a repo path like shared/contract_forms.py: Claude
    reads it in the sandbox, where only the skill's own folder exists."""
    out = []
    for path in sorted(glob.glob(os.path.join(root, "skills", "*", "**", "*.md"), recursive=True)):
        if f"{os.sep}_shared{os.sep}" in path:
            continue
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                for m in REPO_PATH.finditer(line):
                    out.append(f"{os.path.relpath(path, root)}:{n}: names {m.group(0)}, a repo path the skill can't see")
    return out


def main():
    problems = [p for path in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))) for p in lint(path)]
    problems += dev_only_imports()
    problems += repo_paths()
    print("\n".join(problems) if problems else "lint-skills: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
