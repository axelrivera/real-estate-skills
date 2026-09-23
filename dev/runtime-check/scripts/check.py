"""Report which dependencies the marketplace skills can use in this runtime.

Every check is real: modules are imported, Chromium prints a PDF, pptxgenjs
writes a deck. Nothing is installed permanently; install checks use a temp dir.
"""
import importlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="rt-check-")
rows = []


def add(area, item, ok, detail=""):
    rows.append((area, item, "yes" if ok else "NO", detail.replace("\n", " ")[:120]))


def run(cmd, timeout=60, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except Exception as e:  # noqa: BLE001 - report any failure
        return False, str(e)


# Python packages
for mod, dist in [("pandas", "pandas"), ("numpy", "numpy"), ("bs4", "beautifulsoup4"),
                  ("PIL", "pillow"), ("playwright", "playwright"), ("yaml", "PyYAML")]:
    try:
        importlib.import_module(mod)
        add("python", dist, True, importlib.metadata.version(dist))
    except Exception as e:  # noqa: BLE001
        add("python", mod, False, str(e))

# Chromium via Playwright: launch and print a real PDF
try:
    from playwright.sync_api import sync_playwright

    pdf = os.path.join(TMP, "test.pdf")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content("<h1 style='color:#1A74AD'>Runtime check</h1>")
        pg.pdf(path=pdf, format="Letter")
        b.close()
    add("render", "playwright chromium -> PDF", os.path.getsize(pdf) > 0, f"{os.path.getsize(pdf)} bytes")
except Exception as e:  # noqa: BLE001
    add("render", "playwright chromium -> PDF", False, str(e))

# Command-line tools
for tool, args in [("node", ["--version"]), ("npm", ["--version"]), ("pdftotext", ["-v"]),
                   ("soffice", ["--version"]), ("libreoffice", ["--version"])]:
    path = shutil.which(tool)
    if not path:
        add("cli", tool, False, "not on PATH")
        continue
    ok, out = run([tool, *args], timeout=30)
    add("cli", tool, True, out.splitlines()[0] if out else path)

# Node modules: resolvable from the default global paths, then a real deck
if shutil.which("node"):
    for mod in ["pptxgenjs", "react", "react-dom", "react-icons", "sharp"]:
        gp = run(["npm", "root", "-g"])[1] if shutil.which("npm") else ""
        # Resolve the entry point, then walk up to the package's own package.json
        # (packages with an "exports" map block requiring package.json directly).
        js = (f"const fs=require('fs'),path=require('path');"
              f"let d=path.dirname(require.resolve('{mod}',{{paths:[...module.paths,...(process.env.NODE_PATH||'').split(':'),'{gp}']}}));"
              f"while(true){{const f=path.join(d,'package.json');"
              f"if(fs.existsSync(f)&&JSON.parse(fs.readFileSync(f)).name==='{mod}'){{console.log(JSON.parse(fs.readFileSync(f)).version);break}}"
              f"if(d===path.dirname(d))throw new Error('no package.json');d=path.dirname(d)}}")
        ok, out = run(["node", "-e", js])
        add("node", mod, ok, out if ok else "not resolvable")
    js = (f"const p=require(require.resolve('pptxgenjs',{{paths:[...module.paths,...(process.env.NODE_PATH||'').split(':'),'{gp}']}}));"
          "const d=new p();d.addSlide().addText('Runtime check',{x:1,y:1});"
          f"d.writeFile({{fileName:'{TMP}/test.pptx'}}).then(()=>console.log('ok'))")
    ok, out = run(["node", "-e", js])
    add("render", "pptxgenjs -> PPTX", ok and os.path.exists(f"{TMP}/test.pptx"), out[:80])

# Can packages be installed at run time? (temp dirs only)
if shutil.which("pip3") or shutil.which("pip"):
    ok, out = run([sys.executable, "-m", "pip", "download", "--no-deps", "-q", "-d", TMP, "six"], timeout=60)
    add("install", "pip download (PyPI reachable)", ok, "" if ok else out[-100:])
if shutil.which("npm"):
    ok, out = run(["npm", "view", "pptxgenjs", "version"], timeout=60)
    add("install", "npm registry reachable", ok, out[-100:])

# Output locations
add("output", "/mnt/user-data/outputs exists", os.path.isdir("/mnt/user-data/outputs"))
add("output", "working dir writable", os.access(os.getcwd(), os.W_OK), os.getcwd())

print("# Runtime check\n")
print(f"- Python {platform.python_version()} on {platform.system()} {platform.machine()}")
print(f"- Executable: {sys.executable}\n")
print("| Area | Item | Available | Detail |\n|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(r) + " |")
shutil.rmtree(TMP, ignore_errors=True)
