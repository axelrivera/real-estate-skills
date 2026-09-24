"""Build release archives into dist/.

    .venv/bin/python dev/package.py plugin      # make package
    .venv/bin/python dev/package.py skills      # make package-skills

plugin: dist/<name>-<version>.plugin from .claude-plugin/plugin.json, with plugin.json at the
archive root (the desktop app's "Upload local plugin" format). The repo root is the plugin, so
only PLUGIN_FILES go in; docs, dev tooling and shared/ stay out.

skills: one dist/skills/<skill>.zip per skill for claude.ai upload, and the runtime check in
dist/dev/runtime-check.zip (a diagnostic, not uploaded with the skills).
"""
import glob
import json
import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST = os.path.join(ROOT, "dist")
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {".DS_Store"}
PLUGIN_FILES = (".claude-plugin/plugin.json", "skills", "LICENSE")


def zip_dir(src, dest, prefix=""):
    """Zip the contents of src into dest, under prefix inside the archive."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if name in SKIP_FILES or name.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, name)
                z.write(path, os.path.join(prefix, os.path.relpath(path, src)))
    return dest


def rel(path):
    return os.path.relpath(path, ROOT)


def package_plugin():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        plugin = json.load(f)
    dest = os.path.join(DIST, f"{plugin['name']}-{plugin['version']}.plugin")
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in PLUGIN_FILES:
            src = os.path.join(ROOT, entry)
            if os.path.isfile(src):
                z.write(src, entry)
                continue
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                for name in sorted(filenames):
                    if name not in SKIP_FILES and not name.endswith(".pyc"):
                        path = os.path.join(dirpath, name)
                        z.write(path, rel(path))
    print(f"{rel(dest)} (the release: upload this one file)")


def package_skills():
    for skill_md in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
        skill = os.path.dirname(skill_md)
        name = os.path.basename(skill)
        print(rel(zip_dir(skill, os.path.join(DIST, "skills", f"{name}.zip"), name)))
    check = os.path.join(ROOT, "dev", "runtime-check")
    path = zip_dir(check, os.path.join(DIST, "dev", "runtime-check.zip"), "runtime-check")
    print(f"{rel(path)} (a diagnostic: don't upload it with the skills)")


if __name__ == "__main__":
    modes = {"plugin": package_plugin, "skills": package_skills}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(modes)}}}")
    modes[sys.argv[1]]()
