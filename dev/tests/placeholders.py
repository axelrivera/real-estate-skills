"""Shared check for the generated tests: no sentence a skill writes (the PDF's text, the document model's strings, the
Check lines and notes for the chat) shows a template placeholder left empty or unfilled. General shapes only, never
a sentence: a doubled space, a space before punctuation, empty parentheses, two prepositions in a row ("for in"), a
brace or a Python None.
"""
import html
import re

SHAPES = (
    ("doubled space", re.compile(r"\S {2,}\S")),
    ("space before punctuation", re.compile(r"\w +[,.;:](?:\s|$)")),
    ("empty parentheses", re.compile(r"\(\s*\)")),
    # a preposition followed by another, or "the" by a stop: "Tax for in the County", "in the ."
    ("empty placeholder between words", re.compile(r"\b(?:for|of|from|by|with) (?:for|in|of|on|from|by|with|than|"
                                                   r"and|or)\b|\bthe *[,.;:]", re.I)),
    ("unfilled placeholder", re.compile(r"\{\w*\}")),
    ("Python None", re.compile(r"(?<=[a-z,] )None\b")),  # mid-sentence ("None" alone is a fine table value)
)


def strings(v):
    """Every string in a model (dict keys starting with "_" are internal and skipped)."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            if not str(k).startswith("_"):
                yield from strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from strings(x)


def page_text(doc):
    """An HTML document's visible text, one line per block (styles, scripts and SVG left out)."""
    body = re.sub(r"<(style|script|svg)\b.*?</\1>", " ", doc, flags=re.S)
    body = re.sub(r"<(?:br|/?p|/?li|/?h\d|/?div|/?td|/?th|/?tr|/?span)\b[^>]*>", "\n", body)
    lines = (html.unescape(re.sub(r"<[^>]+>", "", ln)).replace("\xa0", " ").strip() for ln in body.split("\n"))
    return [ln for ln in lines if ln]


def problems(texts):
    """[(shape, text)] for each text showing an empty or unfilled placeholder."""
    out = []
    for text in texts:
        for name, rx in SHAPES:
            if rx.search(text):
                out.append((name, text))
    return out
