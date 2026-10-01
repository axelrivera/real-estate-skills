"""Python 3.11 compatibility check for code that ships (the Cowork sandbox runs 3.11; DOC-10).

    .venv/bin/python dev/py311_check.py            # make py311

Runs `python3.11 -m compileall` on every shipped Python file with a real 3.11 interpreter: `python3.11` on the PATH,
else the one uv manages (`uv python find 3.11`; `make setup` installs it, REL-105). Without one it falls back, from
any newer Python, to the grammar (ast feature_version 3.11) and the 3.12-only f-string forms the grammar check can't
see (PEP 701): a quote inside the braces that matches the f-string's own quote, or a backslash inside the braces.
"""
import ast
import glob
import io
import os
import shutil
import subprocess
import sys
import tokenize

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def files():
    out = glob.glob(os.path.join(ROOT, "shared", "**", "*.py"), recursive=True)
    out += glob.glob(os.path.join(ROOT, "skills", "*", "scripts", "*.py"))
    return sorted(p for p in out if "__pycache__" not in p)


def _quote(tok_string):
    s = tok_string.lstrip("rRbBfFuU")
    return s[:3] if s[:3] in ('"""', "'''") else s[:1]


def _clash(inner, outer):
    """Before 3.12 a string inside an f-string's braces can't contain the f-string's own delimiter: the same quote
    character for a one-quote f-string, the same triple quote for a triple-quoted one."""
    return inner[0] == outer[0] if len(outer) == 1 else inner == outer


def fstring_problems(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    problems, stack = [], []  # stack of (quote, brace depth) for open f-strings
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        name = tokenize.tok_name[tok.type]
        if name == "FSTRING_START":
            q = _quote(tok.string)
            if stack and stack[-1][1] > 0 and _clash(q, stack[-1][0]):
                problems.append((tok.start[0], "nested f-string reuses the outer quote"))
            stack.append([q, 0])
        elif name == "FSTRING_END":
            stack.pop()
        elif stack and name == "OP" and tok.string == "{":
            stack[-1][1] += 1
        elif stack and name == "OP" and tok.string == "}":
            stack[-1][1] -= 1
        elif stack and stack[-1][1] > 0 and name == "STRING":
            if _clash(_quote(tok.string), stack[-1][0]):
                problems.append((tok.start[0], "string inside the braces reuses the f-string's quote"))
            if "\\" in tok.string:
                problems.append((tok.start[0], "backslash inside the braces"))
    return problems


def find_py311():
    """A Python 3.11 interpreter: python3.11 on the PATH, else uv's, else None."""
    found = shutil.which("python3.11")
    if not found and shutil.which("uv"):
        r = subprocess.run(["uv", "python", "find", "3.11"], capture_output=True, text=True)
        found = r.stdout.strip() if r.returncode == 0 else None
    if found:
        r = subprocess.run([found, "-c", "import sys; print(sys.version_info[:2] == (3, 11))"], capture_output=True, text=True)
        if r.stdout.strip() == "True":
            return found
    return None


def main():
    py311 = find_py311()
    if py311:
        # -f: recompile everything (a cached .pyc from a newer Python proves nothing); -q: errors only.
        # compileall writes no .pyc for sources that fail, and the ones it writes are for 3.11 and git-ignored.
        r = subprocess.run([py311, "-m", "compileall", "-f", "-q", *files()], capture_output=True, text=True)
        print(r.stdout + r.stderr or f"Python 3.11 compileall: OK ({len(files())} files, {py311})")
        return r.returncode
    bad = []
    for p in files():
        rel = os.path.relpath(p, ROOT)
        with open(p, encoding="utf-8") as f:
            try:
                ast.parse(f.read(), feature_version=(3, 11))
            except SyntaxError as e:
                bad.append(f"{rel}:{e.lineno}: {e.msg}")
        if sys.version_info >= (3, 12):
            bad += [f"{rel}:{line}: {why} (3.12+ only)" for line, why in fstring_problems(p)]
    print("\n".join(bad) if bad else f"Python 3.11 check: OK ({len(files())} files; no Python 3.11: run make setup; checked by grammar)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
