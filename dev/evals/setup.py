"""Set up an eval iteration: one folder per eval with the prompt, its input files and an empty outputs folder.

    .venv/bin/python dev/evals/setup.py 12                                   # every eval of every skill
    .venv/bin/python dev/evals/setup.py 12 seller-offer-review               # one skill
    .venv/bin/python dev/evals/setup.py 12 seller-offer-review:1,4 buyer-offer-strategy:2

Writes out/evals/iteration-N/<skill>/eval-<id>/ with task.md (the prompt, always led by a "Today is" line: the eval's
`today`, else the runner's default day, so every run counts dates from the same day), inputs/ (its files; a mock package
must be built first with `make mock-contracts ARGS="--answer-key"`, and its key/ is never copied) and with_skill/outputs/.
Then start one subagent per folder with dev/evals/RUNNER.md and grade with dev/evals/GRADER.md (development.md#evals).
"""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_TODAY = "2026-09-26"  # RUNNER.md's default day: the eval files assume late September 2026


def selection(args):
    """{skill: set of ids or None for all} from the command line."""
    skills = sorted(d for d in os.listdir(os.path.join(ROOT, "dev", "evals"))
                    if os.path.isfile(os.path.join(ROOT, "dev", "evals", d, "evals.json")))
    if not args:
        return {s: None for s in skills}
    out = {}
    for a in args:
        name, _, ids = a.partition(":")
        if name not in skills:
            sys.exit(f"Unknown skill {name!r}: one of {', '.join(skills)}")
        out[name] = {int(i) for i in ids.split(",")} if ids else None
    return out


def main(argv):
    if not argv or not argv[0].isdigit():
        sys.exit(__doc__)
    base = os.path.join(ROOT, "out", "evals", f"iteration-{argv[0]}")
    n = 0
    for skill, ids in selection(argv[1:]).items():
        with open(os.path.join(ROOT, "dev", "evals", skill, "evals.json"), encoding="utf-8") as f:
            evals = json.load(f)["evals"]
        for e in evals:
            if ids is not None and e["id"] not in ids:
                continue
            folder = os.path.join(base, skill, f"eval-{e['id']}")
            os.makedirs(os.path.join(folder, "inputs"), exist_ok=True)
            os.makedirs(os.path.join(folder, "with_skill", "outputs"), exist_ok=True)
            with open(os.path.join(folder, "task.md"), "w", encoding="utf-8") as f:
                f.write(f"(Today is {e.get('today') or DEFAULT_TODAY}.)\n\n{e['prompt']}\n")
            for path in e.get("files") or []:
                src = os.path.join(ROOT, path)
                if not os.path.exists(src):
                    sys.exit(f"{skill} eval {e['id']}: {path} is missing" + (
                        " (build the mock packages first: make mock-contracts ARGS=\"--answer-key\")"
                        if path.startswith("out/mock-contracts/") else ""))
                if "/key/" in path:
                    sys.exit(f"{skill} eval {e['id']}: {path} is an answer key; never give it to a runner")
                shutil.copy(src, os.path.join(folder, "inputs"))
            n += 1
    print(f"{n} eval folder(s) in {os.path.relpath(base, ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
