"""Copy shared/ into every skill that has a scripts/ folder, as scripts/_shared/, and shared reference files
into the skills that use them.

    python3 dev/sync_shared.py           # sync (make sync)
    python3 dev/sync_shared.py --check   # exit 1 if any copy differs (make check-sync, pre-commit)

The copies are committed so each skill works on its own in claude.ai and Cowork.
Never edit scripts/_shared/ by hand; edit shared/ and sync.

Each skill gets only the shared modules its scripts import (and what those import, plus the data they read:
markets/ for profiles, the CSS for render and cma), so a markdown-only profile skill doesn't ship the offer engine.

shared/references/<name>.md is not code: it is copied to references/<name>.md of every skill whose SKILL.md
mentions `references/<name>.md` (so a skill opts in by pointing to the file). Edit it in shared/references/ only.
"""
import argparse
import ast
import filecmp
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REFERENCES = "references"  # shared/references/ goes to each skill's references/, not scripts/_shared/


# Data files a shared module reads at run time, copied along with it.
DATA_FOR = {"profiles": ("markets/",), "cma": ("cma.css",), "render": ("report.css",)}


def _imports(path, package_level):
    """Shared module names imported by one file: `from _shared import x` in a skill script (package_level=False),
    `from . import x` / `from .x import y` inside shared/ (package_level=True)."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if package_level and node.level == 1:
                out |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
            elif not package_level and node.module and node.module.split(".")[0] == "_shared":
                out |= {node.module.split(".")[1]} if "." in node.module else {a.name for a in node.names}
        elif isinstance(node, ast.Import) and not package_level:
            out |= {a.name.split(".")[1] for a in node.names if a.name.startswith("_shared.")}
    return out


def wanted(src, skill):
    """DOC-11: the files of shared/ this skill needs: the modules its scripts import, what those import in turn, and
    the data they read. A skill whose scripts import nothing from shared gets nothing."""
    scripts = os.path.join(skill, "scripts")
    todo = set()
    for name in os.listdir(scripts) if os.path.isdir(scripts) else []:
        if name.endswith(".py"):
            todo |= _imports(os.path.join(scripts, name), False)
    mods = set()
    while todo:
        m = todo.pop()
        if m in mods or not os.path.exists(os.path.join(src, m + ".py")):
            continue
        mods.add(m)
        todo |= _imports(os.path.join(src, m + ".py"), True)
    if not mods:
        return set()
    files = {"__init__.py"} | {m + ".py" for m in mods}
    everything = source_files(src)
    for m in mods:
        for data in DATA_FOR.get(m, ()):
            files |= {f for f in everything if f == data or (data.endswith("/") and f.startswith(data))}
    return files & everything


def source_files(src):
    out = set()
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (dirpath == src and d == REFERENCES)]
        for f in filenames:
            if not (f.endswith(".pyc") or f == ".DS_Store"):
                out.add(os.path.relpath(os.path.join(dirpath, f), src))
    return out


def skills(root, need_scripts=True):
    base = os.path.join(root, "plugins")
    return sorted(
        os.path.join(base, plugin, "skills", name)
        for plugin in os.listdir(base) if os.path.isdir(os.path.join(base, plugin, "skills"))
        for name in os.listdir(os.path.join(base, plugin, "skills"))
        if os.path.isdir(os.path.join(base, plugin, "skills", name, "scripts" if need_scripts else ""))
    ) if os.path.isdir(base) else []


def reference_copies(root):
    """[(source, dest)] for each shared reference a skill's SKILL.md points to."""
    src_dir = os.path.join(root, "shared", REFERENCES)
    names = sorted(f for f in os.listdir(src_dir) if f.endswith(".md")) if os.path.isdir(src_dir) else []
    out = []
    for skill in skills(root, need_scripts=False):
        try:
            with open(os.path.join(skill, "SKILL.md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        out += [(os.path.join(src_dir, n), os.path.join(skill, REFERENCES, n)) for n in names if f"{REFERENCES}/{n}" in text]
    return out


def drift(src, dest, want):
    """Problems with one copy, as readable strings. Empty when in sync."""
    if not want:
        return [] if not os.path.isdir(dest) else ["extra (this skill's scripts import nothing from shared/)"]
    if not os.path.isdir(dest):
        return ["missing"]
    have = source_files(dest)
    problems = [f"missing {f}" for f in sorted(want - have)]
    problems += [f"extra {f}" for f in sorted(have - want)]
    problems += [f"edited {f}" for f in sorted(want & have)
                 if not filecmp.cmp(os.path.join(src, f), os.path.join(dest, f), shallow=False)]
    return problems


def sync(root, check=False):
    src = os.path.join(root, "shared")
    failed = False
    for skill in skills(root):
        dest = os.path.join(skill, "scripts", "_shared")
        rel = os.path.relpath(dest, root)
        want = wanted(src, skill)
        problems = drift(src, dest, want)
        if not problems:
            continue
        if check:
            failed = True
            print(f"{rel}: " + "; ".join(problems))
        else:
            shutil.rmtree(dest, ignore_errors=True)
            for f in sorted(want):
                os.makedirs(os.path.dirname(os.path.join(dest, f)), exist_ok=True)
                shutil.copyfile(os.path.join(src, f), os.path.join(dest, f))
            print(f"synced {rel}")
    for ref, dest in reference_copies(root):
        rel = os.path.relpath(dest, root)
        if os.path.exists(dest) and filecmp.cmp(ref, dest, shallow=False):
            continue
        if check:
            failed = True
            print(f"{rel}: {'edited' if os.path.exists(dest) else 'missing'}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(ref, dest)
            print(f"synced {rel}")
    if check and failed:
        print("shared/ copies are out of date. Run `make sync` (and edit shared/, never the copies).")
    return not failed


def _staged(root, rel):
    """A file's content in the git index (what the commit will contain), or None when it isn't there."""
    r = subprocess.run(["git", "show", f":{rel}"], cwd=root, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def check_staged(root):
    """DOC-8: the pre-commit check. Compares the staged copies with the staged shared/ files, so a commit can't carry a
    stale copy even when the working tree is in sync."""
    src = os.path.join(root, "shared")
    bad = []
    pairs = [(os.path.join("shared", f), os.path.join(os.path.relpath(skill, root), "scripts", "_shared", f))
             for skill in skills(root) for f in sorted(wanted(src, skill))]
    pairs += [(os.path.relpath(ref, root), os.path.relpath(dest, root)) for ref, dest in reference_copies(root)]
    for a, b in pairs:
        if _staged(root, a) != _staged(root, b):
            bad.append(b)
    for line in bad:
        print(f"{line}: the staged copy differs from the staged shared/ file")
    if bad:
        print("Run `make sync`, then stage the shared/ change and its copies together.")
    return not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report drift without changing anything")
    ap.add_argument("--staged", action="store_true", help="with --check: compare what's staged for the next commit")
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.check and args.staged:
        return 0 if sync(args.root, True) and check_staged(args.root) else 1
    return 0 if sync(args.root, args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
