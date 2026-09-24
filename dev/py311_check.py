"""Python 3.11 compatibility check for code that ships (the Cowork sandbox runs 3.11; DOC-10).

    .venv/bin/python dev/py311_check.py            # make py311

Runs `python3.11 -m compileall` when a 3.11 interpreter is on the PATH. Without one it checks, from any newer
Python: the grammar (ast feature_version 3.11) and the 3.12-only f-string forms the grammar check can't see (PEP 701):
a quote inside the braces that matches the f-string's own quote, or a backslash inside the braces.
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
    out += glob.glob(os.path.join(ROOT, "plugins", "*", "skills", "*", "scripts", "*.py"))
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


def main():
    py311 = shutil.which("python3.11")
    if py311:
        r = subprocess.run([py311, "-m", "compileall", "-q", *files()], capture_output=True, text=True)
        print(r.stdout + r.stderr or "python3.11 compileall: OK")
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
    print("\n".join(bad) if bad else f"Python 3.11 check: OK ({len(files())} files; no python3.11 on PATH, so checked by grammar)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
