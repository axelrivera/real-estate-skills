"""Build release archives into dist/.

    .venv/bin/python dev/package.py plugin      # make package
    .venv/bin/python dev/package.py skills      # make package-skills
    .venv/bin/python dev/package.py notes       # make release: dist/release-notes-<version>.md from docs/status.md

Every archive is built from `git ls-files`, so an untracked or ignored file in skills/ never ships (REL-103).

plugin: dist/<name>-<version>.plugin from .claude-plugin/plugin.json, with plugin.json at the
archive root (the desktop app's "Upload local plugin" format). The repo root is the plugin, so
only PLUGIN_FILES go in; docs, dev tooling and shared/ stay out. Then the release zip,
dist/<marketplace>-<version>.zip: the .plugin, dev/package/README.md (the agent guide, without its manual-only
figure lines), the PDF manual (stops when it's older than the guide: make manual) and LICENSE, in a
<marketplace>-<version>/ folder, for sharing.

skills: one dist/skills/<skill>.zip per skill for claude.ai upload (the folder is cleared first, so a removed skill's
zip never lingers), and the runtime check in dist/dev/runtime-check.zip (a diagnostic, not uploaded with the skills).

notes: the release notes for GitHub, from the status.md sections whose heading names a version after the last
release tag, up to this one ("## This pass (2026-09-29): ... and Version 0.12.0"). Stops when this version has none.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manual  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST = os.path.join(ROOT, "dist")
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {".DS_Store"}
PLUGIN_FILES = (".claude-plugin/plugin.json", "skills", "LICENSE")
RELEASE_DIR = os.path.join(ROOT, "dev", "package")
RELEASE_README = os.path.join(RELEASE_DIR, "README.md")
STATUS = os.path.join(ROOT, "docs", "status.md")


def tracked(paths, root=ROOT):
    """The files git tracks under each path (relative to root, sorted), skipping any deleted in the working tree."""
    out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", *paths], capture_output=True, text=True, check=True)
    files = []
    for rel_path in out.stdout.split("\0"):
        parts = rel_path.split("/")
        if (rel_path and os.path.isfile(os.path.join(root, rel_path)) and parts[-1] not in SKIP_FILES
                and not SKIP_DIRS & set(parts) and not rel_path.endswith(".pyc")):
            files.append(rel_path)
    return sorted(files)


def zip_dir(src, dest, prefix="", root=ROOT):
    """Zip the tracked files under src into dest, under prefix inside the archive."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    base = os.path.relpath(src, root)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for path in tracked([base], root):
            z.write(os.path.join(root, path), os.path.join(prefix, os.path.relpath(path, base)))
    return dest


def rel(path):
    return os.path.relpath(path, ROOT)


def read_manifest(name):
    with open(os.path.join(ROOT, ".claude-plugin", name), encoding="utf-8") as f:
        return json.load(f)


def build_plugin(dest, root=ROOT):
    """The .plugin archive: the tracked PLUGIN_FILES at their repo paths."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for path in tracked(PLUGIN_FILES, root):
            z.write(os.path.join(root, path), path)
    return dest


def package_plugin():
    plugin = read_manifest("plugin.json")
    why = manual.stale()  # before building anything, so a stale manual never ships
    if why:
        sys.exit(f"The PDF manual is out of date ({why}): run make manual and commit the PDF.")
    dest = build_plugin(os.path.join(DIST, f"{plugin['name']}-{plugin['version']}.plugin"))
    print(f"{rel(dest)} (upload this one file)")
    package_release(plugin, dest)


def guide_text(version, plugin_file):
    """The agent guide as it ships in the release zip: version and file name filled in, manual-only lines out."""
    with open(RELEASE_README, encoding="utf-8") as f:
        text = f.read()
    return manual.strip_figures(text.replace("{{VERSION}}", version).replace("{{PLUGIN_FILE}}", plugin_file))


def package_release(plugin, plugin_path):
    folder = f"{read_manifest('marketplace.json')['name']}-{plugin['version']}"
    dest = os.path.join(DIST, f"{folder}.zip")
    if os.path.exists(dest):
        os.remove(dest)
    plugin_file = os.path.basename(plugin_path)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(plugin_path, f"{folder}/{plugin_file}")
        z.writestr(f"{folder}/README.md", guide_text(plugin["version"], plugin_file))
        z.write(os.path.join(ROOT, "LICENSE"), f"{folder}/LICENSE")  # also inside the .plugin; here so it's seen on unzip
        z.write(manual.PDF, f"{folder}/{os.path.basename(manual.PDF)}")
    print(f"{rel(dest)} (the release: the .plugin, the agent guide, the manual and the license, for sharing)")


def package_skills():
    for sub in ("skills", "dev"):  # a removed skill's zip must not linger for anyone who uploads "every zip"
        shutil.rmtree(os.path.join(DIST, sub), ignore_errors=True)
    for path in tracked(["skills"]):
        parts = path.split("/")
        if len(parts) == 3 and parts[2] == "SKILL.md":
            name = parts[1]
            print(rel(zip_dir(os.path.join(ROOT, "skills", name), os.path.join(DIST, "skills", f"{name}.zip"), name)))
    check = os.path.join(ROOT, "dev", "runtime-check")
    path = zip_dir(check, os.path.join(DIST, "dev", "runtime-check.zip"), "runtime-check")
    print(f"{rel(path)} (a diagnostic: don't upload it with the skills)")


def _version(text):
    return tuple(int(n) for n in text.split("."))


VERSION_HEADING = re.compile(r"^## .*\bVersion (\d+\.\d+\.\d+)\b.*$", re.M)


def release_notes(status_text, version, last=None):
    """The status.md sections for every version after `last` (the previous release) up to `version`, newest first,
    each under its own heading. None when `version` has no section."""
    heads = list(VERSION_HEADING.finditer(status_text))
    sections = []
    for i, m in enumerate(heads):
        v = _version(m.group(1))
        if v > _version(version) or (last and v <= _version(last)):
            continue
        start = m.end()
        nxt = re.compile(r"^## ", re.M).search(status_text, start)
        body = status_text[start:nxt.start() if nxt else len(status_text)].strip()
        title = re.sub(r"^## This pass \([\d-]+\):\s*", "", m.group(0)).strip()
        sections.append((v, f"## {title}\n\n{body}\n"))
    if not any(v == _version(version) for v, _ in sections):
        return None
    return "\n".join(text for _, text in sorted(sections, reverse=True))


def last_release(version, root=ROOT):
    """The newest v<x.y.z> tag below `version`, or None."""
    out = subprocess.run(["git", "-C", root, "tag", "--list", "v*"], capture_output=True, text=True, check=True).stdout
    tags = [t[1:] for t in out.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t) and _version(t[1:]) < _version(version)]
    return max(tags, key=_version) if tags else None


def write_notes():
    version = read_manifest("plugin.json")["version"]
    with open(STATUS, encoding="utf-8") as f:
        notes = release_notes(f.read(), version, last_release(version))
    if not notes:
        sys.exit(f"No release notes for {version}: add a docs/status.md section whose heading ends in "
                 f"\"Version {version}\".")
    dest = os.path.join(DIST, f"release-notes-{version}.md")
    os.makedirs(DIST, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(notes)
    print(rel(dest))


if __name__ == "__main__":
    modes = {"plugin": package_plugin, "skills": package_skills, "notes": write_notes}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(modes)}}}")
    modes[sys.argv[1]]()
