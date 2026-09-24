"""Checks on the text Claude writes into a data file, run before any file is rendered.

Two rules, both hard stops (the render ends and names each field to rewrite):
  - no em dashes in prose (one touching a word: "right \u2014 for now"); a lone em dash standing for an
    empty value ("\u2014", "\u2014 / \u2014") is fine;
  - no wording that the Fair Housing Act and HUD's advertising guidance treat as a preference or
    limitation (42 U.S.C. 3604(c), 24 CFR 100.75), or that steers (24 CFR 100.70(c)).

The phrase list is a backstop for the rules in references/fair-housing.md, not the rules themselves:
it only catches clear cases and never flags wording HUD allows ("family room", "walk-in closet",
"walking distance", "55+ community"). Chat replies aren't checked here; the skill's instructions cover them.
"""
import re

EM_DASH = "\u2014"
PROSE_DASH = re.compile(r"\w\s*\u2014|\u2014\s*\w")  # an em dash used as punctuation, not as an empty value
SKIP_KEYS = {"export", "path", "file", "files", "url"}  # file locations, not prose

# (pattern, why), matched case-insensitively on word boundaries.
_WHO = r"(?:famil(?:y|ies)|kids|children|couples?|singles|retirees|seniors|empty[- ]nesters|young professionals|students|bachelors?|newlyweds)"
_PEOPLE = r"(?:neighborhoods?|areas?|communit(?:y|ies)|famil(?:y|ies)|buyers?|sellers?|residents|neighbors)"
FAIR_HOUSING = [
    (rf"\b(?:perfect|ideal|great|made|suited|best|wonderful)\s+for\s+(?:a\s+|the\s+)?(?:growing\s+|young\s+|large\s+|small\s+)?{_WHO}\b",
     "says who the home suits (familial status); describe the space instead: bedrooms, yard, layout"),
    (r"\b(?:family|kid|child)[- ]friendly\b", "familial status; describe the features instead"),
    (r"\b(?:no|without)\s+(?:kids|children)\b|\badults?[- ]only\b", "limits familial status"),
    (rf"\b(?:young|older|mature|retired)\s+(?:couples?|professionals|buyers?|famil(?:y|ies)|residents|neighbors)\b",
     "describes the buyer or neighbors by age or family status"),
    (r"\b(?:un)?safe\s+(?:neighborhood|area|community|street|part of town)\b|\b(?:low|high)[- ]crime\b|\bcrime[- ](?:rate|free|stats?)\b"
     r"|\b(?:bad|good|rough|better|best)\s+(?:neighborhood|area|part of town)\b(?!\s+rugs?)|\bdangerous\s+(?:area|neighborhood)\b",
     "safety and crime claims about an area can steer; point the client to official sources instead"),
    (r"\b(?:good|great|excellent|top[- ]rated|best|bad|poor|failing|[a-f][- ]rated)\s+schools?\b|\bschool\s+(?:ratings?|scores?|quality)\b",
     "school quality claims can steer; name the assigned school only if asked, and point to the district"),
    (r"\b(?:up[- ]and[- ]coming|transitional|changing)\s+(?:neighborhood|area|community)\b|\bexclusive\s+(?:neighborhood|area|community)\b"
     r"|\b(?:diverse|integrated|ethnic)\s+(?:neighborhood|area|community)\b",
     "coded neighborhood description; describe the property and the market numbers instead"),
    (rf"\b(?:white|black|hispanic|latino|latina|latinx|asian|african[- ]american|caucasian|immigrant|foreign)\s+{_PEOPLE}\b",
     "race, color or national origin"),
    (rf"\b(?:christian|jewish|muslim|catholic|hindu|buddhist|mormon|protestant)\s+{_PEOPLE}\b", "religion"),
    (r"\benglish[- ](?:speaking|only)\b", "national origin"),
    (r"\bno\s+(?:wheelchairs?|disabled|handicapped)\b|\bable[- ]bodied\b|\bmentally ill\b",
     "disability; describe the home's features, not what a person must be able to do"),
    (r"\b(?:man|woman|lady|gentleman)'?s\s+(?:home|house)\b|\bgay[- ]friendly\b|\bstraight\s+(?:couples?|buyers?)\b",
     "sex, sexual orientation or gender identity"),
]
_COMPILED = [(re.compile(p, re.I), why) for p, why in FAIR_HOUSING]


class ProseError(ValueError):
    """Text in the data file breaks a writing rule; the message names each field to rewrite."""


def _strings(value, path="$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            if str(k).lower() not in SKIP_KEYS:
                yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def issues(data):
    """[(field path, problem)] for every em dash in prose and fair-housing phrase in the data's text."""
    out = []
    for path, text in _strings(data):
        if PROSE_DASH.search(text):
            out.append((path, "em dash in a sentence: use a comma, colon, parentheses or a new sentence"))
        for rx, why in _COMPILED:
            m = rx.search(text)
            if m:
                out.append((path, f'"{m.group(0)}": {why}'))
    return out


def check(data, limit=12):
    """Raise ProseError listing what to rewrite, or return quietly."""
    found = issues(data)
    if not found:
        return
    lines = [f"- {path}: {problem}" for path, problem in found[:limit]]
    if len(found) > limit:
        lines.append(f"- and {len(found) - limit} more")
    raise ProseError("Nothing was rendered. Rewrite these fields in the data file and run again "
                     "(the skill's Guardrails say how to word it):\n" + "\n".join(lines))
