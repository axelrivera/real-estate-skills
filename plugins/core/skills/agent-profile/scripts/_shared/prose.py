"""Checks on the text Claude writes into a data file, run before any file is rendered.

Two rules, both hard stops (the render ends and names each field to rewrite):
  - no em dashes in prose (one touching a word: "right \u2014 for now"); a lone em dash standing for an
    empty value ("\u2014", "\u2014 / \u2014") is fine;
  - no wording that the Fair Housing Act and HUD's advertising guidance treat as a preference or
    limitation (42 U.S.C. 3604(c), 24 CFR 100.75), or that steers (24 CFR 100.70(c)).

The phrase list is a backstop for the rules in references/fair-housing.md, not the rules themselves:
it only catches clear cases and never flags wording HUD allows ("family room", "walk-in closet",
"walking distance", "55+ community"). Chat replies aren't checked here; the skill's instructions cover them.

Not flagged:
  - a pointer to an official source: a bare topic ("school ratings", "crime rate") in a sentence that also names
    the district, sheriff, police or another official source ("School ratings are available from the district.");
    claims ("great schools", "low crime") are flagged either way;
  - place names in address, subdivision, city, county and school fields (SKIP_KEYS);
  - a proper name listed in the data's `fair_housing_allow`: [{"phrase": "Asian Community Center", "reason":
    "name of the community center 0.3 miles away"}]. Each entry needs a reason; check() returns the entries used
    so the run can log them.
"""
import re

EM_DASH = "\u2014"
PROSE_DASH = re.compile(r"\w\s*\u2014|\u2014\s*\w")  # an em dash used as punctuation, not as an empty value
SKIP_KEYS = {"export", "path", "file", "files", "url",  # file locations, not prose
             "address", "mls_address", "street", "subdivision", "city", "county", "zip",  # place names
             "school", "schools", "assigned_school", "fair_housing_allow"}
ALLOW_KEY = "fair_housing_allow"
# An official source named in the same sentence turns a bare topic into a pointer, not a claim.
OFFICIAL = re.compile(r"\b(?:district|school board|sheriff|police|department|official|FDLE|FBI|county records?)\b", re.I)
SENTENCE = re.compile(r"[^.!?;]+[.!?;]?")

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
    (r"\b(?:un)?safe\s+(?:neighborhood|area|community|street|part of town)\b|\b(?:low|high)[- ]crime\b|\bcrime[- ]free\b"
     r"|\b(?:bad|good|rough|better|best)\s+(?:neighborhood|area|part of town)\b(?!\s+rugs?)|\bdangerous\s+(?:area|neighborhood)\b",
     "safety and crime claims about an area can steer; point the client to official sources instead"),
    (r"\b(?:good|great|excellent|top[- ]rated|best|bad|poor|failing|[a-f][- ]rated)\s+schools?\b",
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
    (r"\bbuyer\s+profile\b|\b(?:va|fha|usda|voucher|section 8)\s+buyers?\s+(?:need not|not welcome|welcome)\b",
     "describes the buyer through a loan or income type; describe the terms (appraisal rules, down payment, timeline)"),
]
# Bare topics: fine when the sentence points to an official source, a claim otherwise.
TOPICS = [
    (r"\bcrime[- ](?:rates?|stats?|statistics|data)\b",
     "crime figures can steer; point the client to the police or sheriff's public data instead"),
    (r"\bschool\s+(?:ratings?|scores?|quality|grades?)\b",
     "school ratings can steer; point the client to the school district to verify"),
]
_COMPILED = [(re.compile(p, re.I), why) for p, why in FAIR_HOUSING]
_TOPICS = [(re.compile(p, re.I), why) for p, why in TOPICS]


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


def allow_list(data):
    """The data's `fair_housing_allow` entries as [(phrase, reason)]; an entry without a reason is refused."""
    entries = data.get(ALLOW_KEY) if isinstance(data, dict) else None
    out, bad = [], []
    for i, e in enumerate(entries or []):
        phrase, reason = (e.get("phrase"), e.get("reason")) if isinstance(e, dict) else (None, None)
        if not (isinstance(phrase, str) and phrase.strip() and isinstance(reason, str) and reason.strip()):
            bad.append(f"- $.{ALLOW_KEY}[{i}]: needs a \"phrase\" and the \"reason\" it is a proper name, not a description")
        else:
            out.append((phrase.strip(), reason.strip()))
    if bad:
        raise ProseError("Nothing was rendered. Fix the fair-housing allow list:\n" + "\n".join(bad))
    return out


def _allowed(text, m, allow):
    """The allow-list phrase covering match `m` in `text`, if any."""
    for phrase, reason in allow:
        for a in re.finditer(re.escape(phrase), text, re.I):
            if a.start() <= m.start() and m.end() <= a.end():
                return phrase, reason
    return None


def issues(data, used=None):
    """[(field path, problem)] for every em dash in prose and fair-housing phrase in the data's text.

    Allow-list entries that excused a match are added to `used` (a list) when given."""
    allow = allow_list(data)
    out = []
    for path, text in _strings(data):
        if PROSE_DASH.search(text):
            out.append((path, "em dash in a sentence: use a comma, colon, parentheses or a new sentence"))
        hits = [(m, why) for rx, why in _COMPILED for m in rx.finditer(text)]
        for sent in SENTENCE.finditer(text):
            if not OFFICIAL.search(sent.group(0)):
                hits += [(m, why) for rx, why in _TOPICS for m in rx.finditer(sent.group(0))]
        seen = set()
        for m, why in hits:
            ok = _allowed(m.string, m, allow)  # m.string: the field, or the sentence for a topic match
            if ok:
                if used is not None and ok not in used:
                    used.append(ok)
                continue
            if why not in seen:  # one line per rule and field
                seen.add(why)
                out.append((path, f'"{m.group(0)}": {why}'))
    return out


def check(data, limit=12):
    """Raise ProseError listing what to rewrite; otherwise return the allow-list entries that were used."""
    used = []
    found = issues(data, used)
    if not found:
        return used
    lines = [f"- {path}: {problem}" for path, problem in found[:limit]]
    if len(found) > limit:
        lines.append(f"- and {len(found) - limit} more")
    raise ProseError("Nothing was rendered. Rewrite these fields in the data file and run again "
                     "(the skill's Guardrails say how to word it):\n" + "\n".join(lines))
