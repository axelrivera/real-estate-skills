"""Answers for the yes/no questions on seller disclosures (SPDR-4x, SPDC-2, MISIRS-2, FD-2 and the like).

A question row is two or three checkboxes on one line: either in right-hand columns (Yes, No, Don't Know) or inline,
each followed by its word ("Yes", "No", "has", "has no", "has not"). The question is the text to the left, back to
the previous row. Each row gets a plausible default: "yes" for questions about good condition ("structurally sound",
"in working condition"), "no" for everything else (no known problems, no claims, no assessments). The scenario
overrides answers by question text: {"water intrusion": "yes", "flood insurance": "dont_know"}. Local dev only.
"""
import re

GOOD = re.compile(r"structurally sound|free of leaks|working condition|designed to operate|good (?:working )?condition", re.I)
YES_WORD = re.compile(r"^(yes\b|has\b(?!\s+(no|not)\b))", re.I)
NO_WORD = re.compile(r"^(no\b|has\s+(no|not)\b)", re.I)
DK_WORD = re.compile(r"^don['’]?t\s+know|^unknown", re.I)


def _rows(found, words_by_page):
    """[(page, [check blanks left to right], question text)] for every yes/no row on the form."""
    rows = []
    by_page = {}
    for b in found:
        if b["kind"] == "check":
            by_page.setdefault(b["page"], []).append(b)
    for page, checks in by_page.items():
        checks.sort(key=lambda b: (b["rect"][1], b["rect"][0]))
        groups = []
        for b in checks:
            if groups and abs(groups[-1][-1]["rect"][1] - b["rect"][1]) < 3:
                groups[-1].append(b)
            else:
                groups.append([b])
        prev_y = 0
        for g in groups:
            g.sort(key=lambda b: b["rect"][0])
            y = g[0]["rect"][3]
            kinds = [_kind(b) for b in g]
            columns = 2 <= len(g) <= 3 and g[0]["rect"][0] > 380 and all(k is None for k in kinds)
            inline = 2 <= len(g) <= 3 and all(k is not None for k in kinds) and "yes" in kinds and "no" in kinds
            if columns or inline:
                x_end = g[0]["rect"][0] - 2
                words = [w for w in words_by_page.get(page, []) if prev_y - 1 <= (w[1] + w[3]) / 2 <= y + 2 and w[2] <= x_end]
                question = " ".join(w[4] for w in sorted(words, key=lambda w: (round(w[1]), w[0])))
                if columns:
                    kinds = ["yes", "no", "dont_know"][:len(g)]
                rows.append((page, list(zip(kinds, g)), question))
            prev_y = y
    return rows


def _kind(b):
    after = b["after"].strip()
    if DK_WORD.match(after):
        return "dont_know"
    if NO_WORD.match(after):
        return "no"
    if YES_WORD.match(after):
        return "yes"
    return None


def choose(found, words_by_page, overrides=None, default=None):
    """[(check blank, question, answer)] for every yes/no row: the box to check on each."""
    overrides = {k.lower(): v for k, v in (overrides or {}).items()}
    out = []
    for page, boxes, question in _rows(found, words_by_page):
        q = question.lower()
        answer = next((v for k, v in overrides.items() if k in q), None) or default or ("yes" if GOOD.search(q) else "no")
        answer = {"don't know": "dont_know", "unknown": "dont_know"}.get(str(answer).lower(), str(answer).lower())
        box = next((b for k, b in boxes if k == answer), None)
        if box is not None:
            out.append((box, question, answer))
    return out
