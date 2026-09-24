"""Import a skill's scripts in tests without name clashes between skills.

Several skills have a scripts/render.py (and their own compute.py, timeline.py…). Python caches
modules by name, so `import render` in one test file would return another skill's module. load()
clears every module that came from a skill's scripts folder, puts this skill's folder first on
sys.path, imports the requested modules, and returns them. Call it at module level.
"""
import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKILLS = os.path.join(ROOT, "skills")


def scripts_dir(skill):
    path = os.path.join(SKILLS, skill, "scripts")
    if not os.path.isdir(path):
        raise FileNotFoundError(skill)
    return path


def load(skill, *names):
    path = scripts_dir(skill)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if f.startswith(SKILLS) and os.sep + "scripts" + os.sep in f:
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if not (os.path.abspath(p).startswith(SKILLS) and p.rstrip(os.sep).endswith("scripts"))]
    sys.path.insert(0, path)
    return tuple(importlib.import_module(n) for n in names)
