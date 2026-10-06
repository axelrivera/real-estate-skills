"""Golden snapshots of what each skill computes, so an engine change that moves a number, a date or a flag fails
`make test` until someone approves it with `make golden`.

Each case runs a skill's compute step (the same call its scripts/render.py makes) on a fixture from dev/fixtures/
or dev/samples/ with the clock frozen, then keeps only the structured facts: numbers, dates, booleans and short
keys (a row key, a severity, a rider letter). Prose, labels and file paths are dropped, and a list of sentences
becomes its count, so rewording a note never fails the check, while adding or losing one does.

    python dev/golden.py            # compare with dev/golden/, print the differences, exit 1 when any
    python dev/golden.py --update   # rewrite dev/golden/ from the current code (review the git diff)
"""
import copy
import datetime as _dt
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOLDEN = os.path.join(ROOT, "dev", "golden")
TODAY = _dt.date(2026, 9, 26)  # the day the fixtures and evals assume
sys.path.insert(0, os.path.join(ROOT, "dev", "tests"))
from skill_import import load  # noqa: E402

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")
KEY = re.compile(r"^[A-Za-z0-9_.:+%$-]{1,40}$")


class FrozenDate(_dt.date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


_REAL_DATE = _dt.date


def freeze_clock():
    """Point every loaded module's `date` (from `from datetime import date`) at FrozenDate, leaving the datetime
    module itself alone so later lookups still find the real class."""
    for mod in list(sys.modules.values()):
        if mod is not _dt and getattr(mod, "date", None) is _REAL_DATE:
            mod.date = FrozenDate


def _read(path):
    with open(path) as f:
        return json.load(f)


def timeline(path):
    (tl,) = load("contract-timeline", "timeline")
    freeze_clock()
    return tl.analyze(_read(path))


def offer_review(path):
    (rv,) = load("seller-offer-review", "review")
    freeze_clock()
    data = _read(path)
    return rv.analyze(data, cma=rv.load_cma(data))


def offer_strategy(path):
    (st,) = load("buyer-offer-strategy", "strategy")
    freeze_clock()
    data = _read(path)
    return st.analyze(data, cma=st.load_cma(data))


def net_sheet(path):
    (compute,) = load("seller-net-sheet", "compute")
    freeze_clock()
    return compute.run(_read(path))


def cma(skill):
    def run(path):
        (compute,) = load(skill, "compute")
        freeze_clock()
        R = _read(path)
        cwd = os.getcwd()
        os.chdir(ROOT)  # export paths in fixtures are relative to the repo root
        try:
            market, homes = compute.load_inputs(R, None, path)
            C = compute.compute(R, market, homes)
            return compute.public(C) if hasattr(compute, "public") else C  # without the export's homes (render's own)
        finally:
            os.chdir(cwd)
    return run


# skill -> (compute step, fixture globs). seller-cma-deck.json is slide copy for the deck, not a report.
CASES = {
    "contract-timeline": (timeline, ["dev/fixtures/contract-timeline/*.json", "dev/samples/contract-timeline.json"]),
    "seller-offer-review": (offer_review, ["dev/fixtures/seller-offer-review/*.json", "dev/samples/seller-offer-review*.json"]),
    "buyer-offer-strategy": (offer_strategy, ["dev/fixtures/buyer-offer-strategy/*.json", "dev/samples/buyer-offer-strategy.json"]),
    "buyer-cma": (cma("buyer-cma"), ["dev/fixtures/buyer-cma/*.json", "dev/samples/buyer-cma.json"]),
    "seller-cma": (cma("seller-cma"), ["dev/fixtures/seller-cma/*.json", "dev/samples/seller-cma.json"]),
    "seller-net-sheet": (net_sheet, ["dev/fixtures/seller-net-sheet/*.json", "dev/samples/seller-net-sheet.json"]),
}

_DROP = object()


def facts(v):
    """The structured facts in a compute result (see the module docstring)."""
    if isinstance(v, dict):
        out = {}
        for k in sorted(v, key=str):
            f = facts(v[k])
            if f is not _DROP and f != {} and f != []:
                out[str(k)] = f
        return out
    if isinstance(v, (list, tuple)):
        items = [facts(x) for x in v]
        kept = [i for i in items if i is not _DROP]
        if not kept:  # sentences (notes, flags, reasons): keep how many
            return {"count": len(items)}
        if isinstance(v, tuple) or len(kept) < len(items) and not all(isinstance(i, (dict, list)) for i in kept):
            return kept  # a mixed record like (key, label, amount): keep its key and number
        return items if len(kept) == len(items) else {"count": len(items), "facts": kept}
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return round(v, 4) if abs(v) < 1 else round(v, 2)  # rates and fractions keep their precision
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, str):
        if DATE.match(v) or (KEY.match(v) and "/" not in v):
            return v
        return _DROP
    return _DROP


def snapshot(skill, path):
    fn, _ = CASES[skill]
    return facts(fn(os.path.join(ROOT, path)))


def cases():
    for skill, (_, globs) in CASES.items():
        for g in globs:
            for path in sorted(glob.glob(os.path.join(ROOT, g))):
                rel = os.path.relpath(path, ROOT)
                name = ("sample-" if rel.startswith("dev/samples/") else "") + os.path.splitext(os.path.basename(path))[0]
                yield skill, rel, os.path.join(GOLDEN, skill, name + ".json")


def diff(old, new, path="", out=None):
    """Field-by-field differences, as 'path: old -> new' lines."""
    out = [] if out is None else out
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            p = f"{path}.{k}" if path else k
            if k not in old:
                out.append(f"{p}: (new) {json.dumps(new[k])[:120]}")
            elif k not in new:
                out.append(f"{p}: {json.dumps(old[k])[:120]} -> (gone)")
            else:
                diff(old[k], new[k], p, out)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new)):
            diff(a, b, f"{path}[{i}]", out)
    elif old != new:
        out.append(f"{path}: {json.dumps(old)[:120]} -> {json.dumps(new)[:120]}")
    return out


def main(argv=None):
    update = "--update" in (argv if argv is not None else sys.argv[1:])
    failed = 0
    seen = set()
    for skill, rel, gold in cases():
        seen.add(gold)
        new = snapshot(skill, rel)
        if update:
            os.makedirs(os.path.dirname(gold), exist_ok=True)
            with open(gold, "w") as f:
                json.dump(new, f, indent=1, sort_keys=True)
                f.write("\n")
            continue
        if not os.path.exists(gold):
            print(f"{rel}: no snapshot (run make golden)")
            failed += 1
            continue
        lines = diff(_read(gold), new)
        if lines:
            failed += 1
            print(f"{rel} ({len(lines)} change(s)):")
            for line in lines[:40]:
                print("  " + line)
    stale = [g for g in glob.glob(os.path.join(GOLDEN, "*", "*.json")) if g not in seen]
    for g in stale:
        if update:
            os.remove(g)
        else:
            print(f"{os.path.relpath(g, ROOT)}: snapshot with no fixture (run make golden)")
            failed += 1
    if update:
        print(f"Wrote {len(seen)} snapshots to {os.path.relpath(GOLDEN, ROOT)}/")
        return 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
