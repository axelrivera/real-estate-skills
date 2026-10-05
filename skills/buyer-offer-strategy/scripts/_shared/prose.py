"""Checks on the text Claude writes into a data file, run before any file is rendered.

Hard stops (the render ends and lists every field to rewrite at once, as `field: problem \u2192 fix`):
  - no em dashes in prose (one touching a word: "right \u2014 for now"); a lone em dash standing for an
    empty value ("\u2014", "\u2014 / \u2014") is fine;
  - no wording that the Fair Housing Act and HUD's advertising guidance treat as a preference or
    limitation (42 U.S.C. 3604(c), 24 CFR 100.75), or that steers (24 CFR 100.70(c));
  - client wording (references/client-wording.md): no tool words (placeholder, JSON, data file, re-run, script,
    schema, null, undefined, NaN, TODO, TBD, a {placeholder} no script fills), no data keys (insurance_annual), no
    ISO dates inside a sentence (2026-09-26: write Sep 26, 2026) and no jargon from JARGON (DOM: days on market).
    Names, identifiers, form and rider names, file names, URLs and emails are exempt; a one-word value
    ("as_is", "2026-09-26") is data, not prose. Jargon isn't checked in text only the agent sees (`agent_only`).

Missing data never stops a render; only wrong wording does. Labels the model types (scenario, strategy and option
names, headings) aren't checked: title_labels() puts them in Title Case before anything is built.

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
# A house of worship, not when it is part of a street or place name ("Church Street", "Temple Terrace")
_WORSHIP = (r"(?:church|synagogue|mosque|temple|parish|chapel|congregation)(?![- ](?:st|street|rd|road|ave|avenue|ln|lane"
            r"|dr|drive|blvd|boulevard|way|ct|court|pl|place|cir|circle|hill|lake|park|pkwy|parkway|terrace)\b)")
FAIR_HOUSING = [
    (rf"\b(?:perfect|ideal|great|made|suited|best|wonderful)\s+for\s+(?:a\s+|the\s+)?(?:growing\s+|young\s+|large\s+|small\s+)?{_WHO}\b",
     "says who the home suits (familial status); describe the space instead: bedrooms, yard, layout"),
    (rf"\b(?:areas?|neighborhoods?|communit(?:y|ies)|streets?|homes?|house)\s+for\s+(?:a\s+|the\s+)?(?:growing\s+|young\s+)?{_WHO}\b",
     "says who the area or home suits (familial status, age); describe the features instead"),
    (r"\b(?:family|kid|child)[- ]friendly\b", "familial status; describe the features instead"),
    (r"\b(?:no|without)\s+(?:kids|children)\b|\badults?[- ]only\b", "limits familial status"),
    (rf"\b(?:young|older|mature|retired)\s+(?:couples?|professionals|buyers?|famil(?:y|ies)|residents|neighbors)\b",
     "describes the buyer or neighbors by age or family status"),
    (r"\b(?:un)?safe\s+(?:neighborhoods?|areas?|communit(?:y|ies)|streets?|part of town)\b|\b(?:low|high)[- ]crime\b"
     r"|\bcrime[- ]free\b|\b(?:dangerous|rough)\s+(?:areas?|neighborhoods?|part of town)\b",
     "safety and crime claims about an area can steer; point the client to official sources instead"),
    # FH-5: judging an area (not a safety claim). "a good area rug" and "a good area for a garden" describe things, not places
    (r"\b(?:bad|good|great|better|best|desirable|undesirable)\s+(?:neighborhoods?|areas?|part of town)\b(?!\s+(?:rugs?|for)\b)",
     "judging an area's quality can steer; describe the property and the market numbers instead"),
    (r"(?<!single[- ])\bfamily[- ](?:oriented|neighborhoods?|communit(?:y|ies)|areas?)\b|\badult\s+communit(?:y|ies)\b"
     r"|\bbachelor(?:ette)?\s+pads?\b",
     "describes who the area or home suits (familial status, sex); describe the features, or 55+ only when it qualifies"),
    (r"\bno\s+(?:section\s*8|(?:housing\s+)?vouchers?|government\s+assistance)\b|\bsection\s*8\s+not\s+accepted\b",
     "source of income is protected in several places (Miami-Dade and Orange County among them); describe terms, not buyers"),
    (r"\b(?:good|great|excellent|top[- ]rated|best|bad|poor|failing|[a-f][- ]rated)\s+schools?\b",
     "school quality claims can steer; name the assigned school only if asked, and point to the district"),
    (r"\b(?:up[- ]and[- ]coming|transitional|changing)\s+(?:neighborhood|area|community)\b|\bexclusive\s+(?:neighborhood|area|community)\b"
     r"|\b(?:diverse|integrated|ethnic)\s+(?:neighborhood|area|community)\b",
     "coded neighborhood description; describe the property and the market numbers instead"),
    (rf"\b(?:white|black|hispanic|latino|latina|latinx|asian|african[- ]american|caucasian|immigrant|foreign)\s+{_PEOPLE}\b",
     "race, color or national origin"),
    (rf"\b(?:christian|jewish|muslim|catholic|hindu|buddhist|mormon|protestant|religious|devout|observant)\s+"
     rf"(?:{_PEOPLE}|homes?|house|households?|couples?|people|folks)\b", "religion"),
    # FH-106: a house of worship tied to people (attending it, its community, whose it is). The building as a
    # landmark ("near a church", "across from the church", "0.3 miles to the church") and street names
    # ("Church Street") describe the place and pass.
    (rf"\b(?:attend(?:s|ed|ing)?|worship(?:s|ped|ping)?\s+at|members?\s+of|belong(?:s|ing)?\s+to)\s+"
     rf"(?:the\s+|a\s+|their\s+|our\s+|his\s+|her\s+|your\s+)?(?:[\w'-]+\s+){{0,2}}?{_WORSHIP}\b"
     rf"|\battend(?:s|ed|ing)?\s+(?:religious\s+)?(?:services|mass|worship)\b"
     rf"|\b(?:their|our|his|her|your|buyers?'s?|sellers?'s?)\s+(?:own\s+|home\s+|local\s+)?(?:{_WORSHIP}|faith|religion)\b"
     rf"|\b(?:{_WORSHIP}|faith|religious)[- ](?:communit(?:y|ies)|famil(?:y|ies)|members?|groups?|neighbors|folks|going|goers?)\b"
     rf"|\b(?:go(?:es)?|walk(?:s)?|drive(?:s)?)\s+to\s+(?:church|mass|services|synagogue|temple|mosque)\b|\bchurchgo(?:ing|ers?)\b"
     rf"|\bparishioners?\b|\bhouse\s+of\s+worship\s+(?:they|she|he|the buyers?|the sellers?)\b",
     "religion: says what people practice or who belongs; name the place only as a landmark, with its distance"),
    # FH-106: familial status covers pregnancy; marital status is protected in several counties (Miami-Dade among them)
    (r"\bexpecting\s+(?:a|an|their|her|his|our|your)\s+(?:(?:first|second|third|fourth|next|new)\s+)?"
     r"(?:baby|babies|child|kid|little one|son|daughter|twins)\b|\bbab(?:y|ies)\s+on\s+the\s+way\b"
     r"|\bpregnan(?:t|cy)\b|\bexpectant\s+(?:mothers?|moms?|parents?|couples?)\b|\b(?:new|first)\s+baby\b|\bnewborns?\b"
     r"|\bgrowing\s+famil(?:y|ies)\b"
     r"|\b(?:buyers?|sellers?|couples?|famil(?:y|ies)|parents|they|who)\s+(?:with|have|has)\s+"
     r"(?:(?:a|an|two|three|four|five|young|small|little|\d+)\s+)?(?:kids|children|bab(?:y|ies)|toddlers?|teens?|teenagers?|infants?)\b",
     "familial status (children, pregnancy); describe the home and the terms, not who will live there"),
    (r"\b(?:married|unmarried|single|divorced|widowed|engaged)\s+(?:couples?|buyers?|sellers?|m[ae]n|wom[ae]n|mothers?|moms?"
     r"|fathers?|dads?|parents?|persons?|people|professionals?|residents)\b|\bhusband\s+and\s+wife\b|\bwife\s+and\s+husband\b"
     r"|\b(?:buyers?|sellers?|they|she|he)\s+(?:is|are)\s+(?:a\s+)?(?:recently\s+|newly\s+)?(?:married|divorced|divorcing|widowed)\b",
     "marital status; describe the terms, not the people"),
    (r"\b(?:english|spanish|french|creole|haitian|portuguese|chinese|mandarin|cantonese|korean|vietnamese|russian|arabic|hindi"
     r"|tagalog|german|italian|japanese|polish|hebrew)[- ](?:speaking|only)\b", "national origin"),
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



# --- client wording (references/client-wording.md) ------------------------------------------------------------------
# Words from the tools, not the client's world: (pattern, flags, problem, fix). Case-sensitive where the word has a
# plain-English use ("null and void" is contract wording; "None" is a fine table value, so it isn't listed).
TOOL_WORDS = [
    (r"\bplaceholders?\b", re.I, "a tool word", "write the number, or label it Estimate or Assumed"),
    (r"\bJSON\b|\bdata[- ]files?\b|\bschemas?\b|\bscripts?\b", re.I, "a tool word",
     "say what it is in the client's words (the report, the numbers, the listing)"),
    (r"\bre-?run(?:s|ning)?\b", re.I, "a tool word", 'say what happens in the client\'s words ("we\'ll update the report")'),
    (r"\bnull\b(?!\s+and\s+void)|\bundefined\b", re.I, "an empty value printed as text",
     "leave the field out (the report shows its default)"),
    (r"\bNaN\b", 0, "an empty value printed as text", "leave the field out (the report shows its default)"),
    (r"\bTODO\b|\bTBD\b", 0, "unfinished text", "write the value, or leave the field out (the report shows its default)"),
]
# Jargon a client may not know, each with the plain words to use. Kept short: only terms that showed up in reports.
# HOA, MLS and CMA are allowed: clients use them too. LTV and DTI are fine in text only the agent sees (agent_only).
JARGON = [
    (r"\bCDOM\b", 0, "cumulative days on market"),
    (r"\bDOM\b", 0, "days on market"),
    (r"\bwind[- ]?mits?\b", re.I, "wind mitigation"),
    (r"\bCASSB(?:-1)?\b", re.I, "the compensation agreement with the buyer's broker"),
    (r"\bLTV\b", 0, "loan-to-value"),
    (r"\bDTI\b", 0, "debt-to-income"),
    (r"\bCOE\b", 0, "closing"),
    (r"\bEMD\b", 0, "escrow deposit, or earnest money as the contract calls it"),
]
SNAKE_KEY = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")  # a data key: insurance_annual
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?\b")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# Not prose: links, emails and file names keep their own spelling.
EXEMPT_TEXT = re.compile(r"https?://\S+|\bwww\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+"
                         r"|[\w./\\-]+\.(?:json|csv|pdf|pptx|md|ics|txt|xlsx?|png|jpe?g)\b", re.I)
# Keys whose text is a name or an identifier (a person, company, form, rider or key), not prose: the wording rules skip
# them when they hold text (a key holding an object, like a buyer file's `buyer`, is still read).
NAME_KEYS = {"id", "key", "name", "names", "email", "phone", "website", "license", "license_number", "mls", "mls_number",
             "mls_id", "buyer", "seller", "buyers", "sellers", "client", "prepared_for", "lender", "buyer_agent",
             "listing_agent", "escrow_agent", "closing_agent", "title_company", "brokerage", "buyer_names",
             "seller_names", "contract_name", "form", "forms", "contract_form", "form_family", "rider", "riders",
             "addenda", "handoff", "source_file"}
WORDING_SKIP = {"export_columns"}  # an export's own column names
RULES = frozenset({"dash", "fair", "tool", "keys", "dates", "jargon"})
PROFILE_RULES = frozenset({"dash", "fair", "tool"})  # the profile's voice and disclaimers are the agent's own words
_TOOL = [(re.compile(p, f), problem, fix) for p, f, problem, fix in TOOL_WORDS]
_JARGON = [(re.compile(p, f), plain) for p, f, plain in JARGON]
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


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


def _text_only(v):
    return isinstance(v, str) or isinstance(v, list) and all(isinstance(x, str) for x in v)


def _wording_paths(value, path="$", top=None):
    """Paths whose text the wording rules read, with the top-level key each sits under."""
    if isinstance(value, dict):
        for k, v in value.items():
            key = str(k).lower()
            if key in SKIP_KEYS or key in WORDING_SKIP or (key in NAME_KEYS and _text_only(v)):
                continue
            yield from _wording_paths(v, f"{path}.{k}", top if top is not None else key)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _wording_paths(v, f"{path}[{i}]", top)
    elif isinstance(value, str):
        yield path, top


def _date_text(m):
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{MONTHS[mo - 1]} {d}, {y}" if 1 <= mo <= 12 and 1 <= d <= 31 else "the date in words"


def wording_issues(text, placeholders=False, jargon=True, rules=RULES):
    """[problem] for one string: tool words, unfilled {placeholders}, data keys, ISO dates in a sentence and jargon,
    each as `"word": problem → fix`. `placeholders`: the skill fills {name} itself (and names any it can't)."""
    out, seen = [], set()

    def add(line):
        if line not in seen:
            seen.add(line)
            out.append(line)

    bare = EXEMPT_TEXT.sub(" ", text)
    if "tool" in rules:
        for rx, problem, fix in _TOOL:
            for m in rx.finditer(bare):
                add(f'"{m.group(0)}": {problem} → {fix}')
        if not placeholders:
            for m in PLACEHOLDER.finditer(bare):
                add(f'"{m.group(0)}": a placeholder no script fills here → write the words or the number')
    words = PLACEHOLDER.sub(" ", bare)
    if "keys" in rules and len(words.split()) > 1:  # one word ("as_is") is a value, not prose
        for m in SNAKE_KEY.finditer(words):
            add(f'"{m.group(0)}": a data key in the text → say it in words ("{m.group(0).replace("_", " ")}")')
    if "dates" in rules and re.search(r"[A-Za-z]{2,}", ISO_DATE.sub(" ", words)):  # a date with words around it
        for m in ISO_DATE.finditer(words):
            add(f'"{m.group(0)}": a date in data form → write "{_date_text(m)}"')
    if "jargon" in rules and jargon:
        for rx, plain in _JARGON:
            for m in rx.finditer(words):
                add(f'"{m.group(0)}": jargon a client may not know → write "{plain}"')
    return out


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


def issues(data, used=None, *, root="$", rules=RULES, placeholders=False, agent_only=(), allow=None):
    """[(field path, problem)] for every em dash in prose, fair-housing phrase and client-wording problem in the data's
    text. `root` names the file in the paths ("$" for the data file, "deck" for a deck file). `placeholders`: the skill
    fills {name} placeholders itself. `agent_only`: top-level keys whose text only the agent sees (no jargon check).

    Allow-list entries that excused a match are added to `used` (a list) when given."""
    allow = allow_list(data) if allow is None else allow
    out = []
    by_path = {}
    for path, text in _strings(data, root):
        found = by_path.setdefault(path, [])
        if "dash" in rules and PROSE_DASH.search(text):
            found.append("em dash in a sentence → use a comma, colon, parentheses or a new sentence")
        if "fair" not in rules:
            continue
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
                found.append(f'"{m.group(0)}": {why}')
    if rules & {"tool", "keys", "dates", "jargon"}:
        texts = dict(_strings(data, root))
        for path, top in _wording_paths(data, root):
            by_path.setdefault(path, []).extend(
                wording_issues(texts[path], placeholders, jargon=top not in agent_only, rules=rules))
    for path, found in by_path.items():
        out += [(path, p) for p in found]
    return out


def report(found):
    """Raise ProseError listing every problem at once (`field: problem → fix`), so one rewrite fixes them all."""
    if not found:
        return
    lines = [f"- {path.removeprefix('$.')}: {problem}" for path, problem in found]
    raise ProseError(f"Nothing was rendered. Rewrite {'this field' if len(found) == 1 else f'these {len(found)} things'} "
                     "and run again (the skill's Guardrails and references/client-wording.md say how to word it):\n"
                     + "\n".join(lines))


def check(data, **kw):
    """Raise ProseError listing what to rewrite; otherwise return the allow-list entries that were used."""
    used = []
    report(issues(data, used, **kw))
    return used


# --- labels ---------------------------------------------------------------------------------------------------------
MINOR_WORDS = {"a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet", "as", "at", "by", "in", "of", "off",
               "on", "per", "to", "up", "via", "vs", "vs.", "from", "into", "with", "than", "if"}


def _cap(part):
    m = re.match(r"^([^A-Za-z]*)([a-z])(.*)$", part, re.S)
    if m and not any(c.isupper() for c in m.group(3)):  # "iPhone", "eXp": a brand, kept as written
        return m.group(1) + m.group(2).upper() + m.group(3)
    return part


def title_case(text):
    """A label in Title Case (CLAUDE.md): each word capitalized, and each part of a hyphenated word, except short joining
    words inside it; words that already carry a capital ("HOA", "iPhone"), {placeholders}, tags, links and file names
    are kept as written."""
    words = str(text).split(" ")
    out = []
    for i, w in enumerate(words):
        inner = 0 < i < len(words) - 1 and w.lower().strip(",:;()") in MINOR_WORDS
        if not inner and w and not w.startswith(("{", "<")) and not EXEMPT_TEXT.fullmatch(w):
            w = "-".join(_cap(p) for p in w.split("-"))
        out.append(w)
    return " ".join(out)


def _apply(node, toks, fn):
    if not toks:
        return fn(node) if isinstance(node, str) else node
    t, rest = toks[0], toks[1:]
    if t == "**":  # any depth, this level included
        node = _apply(node, rest, fn)
        if isinstance(node, dict):
            return {k: _apply(v, toks, fn) for k, v in node.items()}
        if isinstance(node, list):
            return [_apply(v, toks, fn) for v in node]
        return node
    if t == "[]":
        return [_apply(v, rest, fn) for v in node] if isinstance(node, list) else node
    if t.startswith("["):
        i = int(t[1:-1])
        if isinstance(node, list) and i < len(node):
            node = [*node[:i], _apply(node[i], rest, fn), *node[i + 1:]]
        return node
    if isinstance(node, dict) and t in node:
        return {**node, t: _apply(node[t], rest, fn)}
    return node


def title_labels(data, patterns):
    """The data with every label field the patterns name put in Title Case (a copy; the rest is unchanged).
    Patterns are dotted paths: "pricing.strategies[].label" (each item), "summary_page.key_stats[][1]" (an index),
    "**.heading" (a `heading` at any depth). Labels are fixed, never a reason to stop: convention over a retry."""
    for p in patterns:
        data = _apply(data, re.findall(r"\*\*|\[\d*\]|[^.\[\]]+", p), title_case)
    return data
