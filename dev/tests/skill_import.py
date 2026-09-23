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
PLUGINS = os.path.join(ROOT, "plugins")


def scripts_dir(skill):
    for plugin in os.listdir(PLUGINS):
        path = os.path.join(PLUGINS, plugin, "skills", skill, "scripts")
        if os.path.isdir(path):
            return path
    raise FileNotFoundError(skill)


def load(skill, *names):
    path = scripts_dir(skill)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if f.startswith(PLUGINS) and os.sep + "scripts" + os.sep in f:
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if not (os.path.abspath(p).startswith(PLUGINS) and p.rstrip(os.sep).endswith("scripts"))]
    sys.path.insert(0, path)
    return tuple(importlib.import_module(n) for n in names)
