"""Field maps: which blank on a form holds which value.

A map (fields/<FAMILY>.json) names blanks found by locate.py and says what goes in each:

    {"family": "FARBAR-ASIS", "revision": "FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26",
     "fields": {
       "price":            {"at": "L27", "value": "money(price)"},
       "deposit_with_offer": {"at": "L30.1", "check": "deposit_with_offer"},
       "legal_description": {"at": ["L9", "L10", "L11"], "value": "legal_description"},
       "rider_E":          {"at": {"after": "E. FHA/VA"}, "check": "'E' in riders"}}}

`at` is a blank id ("L27", "P1.7"), a list of anchors for text that flows across lines, or an anchor object:
  {"label": "Seller up to a maximum of"}  the blank whose text to the left ends with this
  {"after": "E. FHA/VA"}                  the blank whose text to the right starts with this
  {"above": "BUYER"}                      the blank whose caption underneath starts with this
  {"within": [x0, y0, x1, y1]}            blanks centered in this page area (points), in reading order
narrowed with "page", "kind" (line | field | area | check), "nth" (0-based) and "all": true (every match, not
the first), and "part": [0, 0.6] (the left 60% of the blank). {"at": "P2.1", "part": [...]} narrows an id.
Prefer text anchors: ids on forms without printed line numbers ("P1.7") shift when detection changes. `value` and `check` are Python
expressions over the scenario context (see context.py); a value that is None or "" leaves the blank empty.

Forms without a map still get the common blanks through auto_roles(): parties, property, the Effective Date of
an addendum, signature and date boxes, and the footer initials. Local dev only.
"""
import json
import os
import re

from locate import FIELDS_DIR, blanks, form_path, manifest


class MapError(Exception):
    pass


def load_map(family):
    """The field map for a form, or None when there isn't one. Refuses a map built for another revision."""
    path = os.path.join(FIELDS_DIR, f"{family}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        m = json.load(f)
    want = manifest()[family]["revision"]
    if m.get("revision") != want:
        raise MapError(f"fields/{family}.json was built for \"{m.get('revision')}\" but dev/forms/farbar-forms.json has "
                       f"\"{want}\". Re-anchor the map (docs/mock-contracts.md#when-a-form-is-revised).")
    return m


V_KEY = re.compile(r"\bv\.([A-Za-z_]\w*)")


def map_value_keys(family):
    """The spec keys a form's map prints: every `v.<key>` its value, check and rows expressions read. Empty when
    the form has no map (only the automatic blanks)."""
    m = load_map(family)
    if not m:
        return set()
    exprs = [f.get(k) for f in m["fields"].values() for k in ("value", "check", "rows")]
    return {k for e in exprs if e for k in V_KEY.findall(e)} - {"get"}


def _norm(s):
    return " ".join(str(s).replace("’", "'").replace("“", '"').replace("”", '"').lower().split())


def _part(b, part):
    """A copy of blank b narrowed to a fraction of its width: part [0, 0.6] is its left 60%."""
    x0, y0, x1, y1 = b["rect"]
    w = x1 - x0
    return {**b, "rect": [x0 + w * part[0], y0, x0 + w * part[1], y1], "id": f"{b['id']}[{part[0]}:{part[1]}]"}


def caption(b):
    """The short caption printed under a blank ("BUYER Date", "Listing Licensee Date"), or "" when the text under
    it is a sentence rather than a caption."""
    words = [t for _, t in b.get("below") or []]
    return _norm(" ".join(words)) if 0 < len(words) <= 4 else ""


def resolve(found, at):
    """The blank(s) an `at` anchor names: a list of blank dicts (empty when nothing matches)."""
    by_id = {b["id"]: b for b in found}
    if isinstance(at, str):
        return [by_id[at]] if at in by_id else []
    if isinstance(at, list):  # every element must match: a silently skipped line would leave a gap in flowed text
        parts = [resolve(found, a) for a in at]
        return [x for p in parts for x in p] if all(parts) else []
    if "at" in at:  # {"at": "P2.1", "part": [0, 0.6]}
        return [_part(b, at["part"]) if at.get("part") else b for b in resolve(found, at["at"])]
    page = at.get("page")
    pool = [b for b in found if page is None or b["page"] == page]
    if "kind" in at:
        pool = [b for b in pool if b["kind"] == at["kind"]]
    if "after" in at:
        want = _norm(at["after"])
        pool = [b for b in pool if _norm(b["after"]).startswith(want)]
    if "label" in at:
        want = _norm(at["label"])
        pool = [b for b in pool if _norm(b["label"]).endswith(want)]
    if "above" in at:  # the blank whose printed caption underneath starts with this ("BUYER", "Date")
        want = _norm(at["above"])
        pool = [b for b in pool if caption(b).startswith(want)]
    if "within" in at:  # blanks whose center is inside [x0, y0, x1, y1] on the page, in reading order
        x0, y0, x1, y1 = at["within"]
        pool = sorted((b for b in pool if x0 <= (b["rect"][0] + b["rect"][2]) / 2 <= x1
                       and y0 <= (b["rect"][1] + b["rect"][3]) / 2 <= y1), key=lambda b: (b["rect"][1], b["rect"][0]))
    if "nth" in at:
        pool = pool[at["nth"]:at["nth"] + 1]
    if "part" in at:
        pool = [_part(b, at["part"]) for b in pool]
    return pool[:1] if not at.get("all") else pool


SELLER_AFTER = re.compile(r'^\(?["“]?seller', re.I)
BUYER_AFTER = re.compile(r'^\(?["“]?buyer', re.I)
PROPERTY_LABEL = re.compile(r"(described as:?|located at:?|street address, city, zip:|property address:?)$", re.I)
EFFECTIVE_LABEL = re.compile(r"effective date of:?$", re.I)
SIGN_LABEL = re.compile(r"(buyer|seller):$", re.I)
DATE_LABEL = re.compile(r"(buyer|seller):\s*(?:/\s*)?date:$", re.I)  # "Buyer: Date:" or "Seller: / Date:"
PRINT_LABEL = re.compile(r"(buyer|seller):\s*/$", re.I)  # "Seller: [signature] / [printed name] Date:"


def auto_roles(found):
    """{role: [blank, ...]} for blanks every FAR/BAR form shares, found by their printed labels:
    'seller_names', 'buyer_names', 'property', 'effective_date', 'sign:buyer', 'sign:seller', 'date:buyer',
    'date:seller', 'print:buyer', 'print:seller' (a printed name next to the signature), 'initials:buyer',
    'initials:seller' (the footer or header initials slots, in order)."""
    roles = {}

    def add(role, b):
        roles.setdefault(role, []).append(b)

    for b in found:
        label, after = b["label"].strip(), b["after"].strip()
        if b["kind"] == "check":
            continue
        m = re.search(r"\.(BI|SI)\d+$", b["id"])
        if m:
            add("initials:buyer" if m.group(1) == "BI" else "initials:seller", b)
        elif DATE_LABEL.search(label):
            add(f"date:{DATE_LABEL.search(label).group(1).lower()}", b)
        elif SIGN_LABEL.search(label) and b["kind"] == "field" and after.lower().startswith(("date", "/")):
            add(f"sign:{SIGN_LABEL.search(label).group(1).lower()}", b)
        elif PRINT_LABEL.search(label) and b["kind"] == "field":
            add(f"print:{PRINT_LABEL.search(label).group(1).lower()}", b)
        elif SELLER_AFTER.match(after) and "seller_names" not in roles:
            add("seller_names", b)
        elif BUYER_AFTER.match(after) and "buyer_names" not in roles:
            add("buyer_names", b)
        elif PROPERTY_LABEL.search(label) and "property" not in roles:
            add("property", b)
        elif EFFECTIVE_LABEL.search(label) and "effective_date" not in roles:
            add("effective_date", b)
    # Signature lines captioned underneath ("BUYER", "SELLER"), with the "Date" line to their right, or one box
    # captioned "Buyer ... Date" that holds both (AGA-1).
    if not any(k.startswith("sign:") for k in roles):
        for b in found:
            if b["kind"] == "check" or not caption(b) or b["rect"][2] - b["rect"][0] < 100:
                continue
            first = caption(b)
            party = "buyer" if first.startswith("buyer") else "seller" if first.startswith("seller") else None
            if not party:
                continue
            date_x = next((x for x, t in b["below"][1:] if _norm(t).startswith("date")), None)
            if date_x and date_x < b["rect"][2] - 20:
                x0 = b["rect"][0]
                split = (date_x - 6 - x0) / (b["rect"][2] - x0)
                add(f"sign:{party}", _part(b, [0, split]))
                add(f"date:{party}", _part(b, [split + 0.01, 1]))
                continue
            add(f"sign:{party}", b)
            right = [d for d in found if d["page"] == b["page"] and d is not b and caption(d).startswith("date") and abs(d["rect"][3] - b["rect"][3]) < 4
                     and d["rect"][0] > b["rect"][2] - 2]
            if right:
                add(f"date:{party}", min(right, key=lambda d: d["rect"][0]))
    # A signature box with no label of its own, just left of a "Buyer: / [printed name]" field on the same row (SOD-2).
    for party in ("buyer", "seller"):
        if roles.get(f"print:{party}") and len(roles.get(f"sign:{party}", [])) < len(roles[f"print:{party}"]):
            signs = []
            for p in roles[f"print:{party}"]:
                left = [b for b in found if b["page"] == p["page"] and b["kind"] == "field" and b is not p
                        and b["rect"][2] <= p["rect"][0] + 2 and abs(b["rect"][3] - p["rect"][3]) < 5 and b["rect"][2] - b["rect"][0] > 100]
                if left:
                    signs.append(max(left, key=lambda b: b["rect"][2]))
            if len(signs) == len(roles[f"print:{party}"]):
                roles[f"sign:{party}"] = signs
    # Headers where the ("Seller") / ("Buyer") text sits outside the field box: the "and ____" blank is the buyer,
    # and the blank just above it the seller.
    if "buyer_names" not in roles:
        ands = [b for b in found if b["kind"] != "check" and b["page"] == 1 and _norm(b["label"]).split()[-1:] == ["and"]]
        if ands:
            roles["buyer_names"] = ands[:1]
            if "seller_names" not in roles:
                above = [b for b in found if b["page"] == 1 and b["kind"] != "check" and b is not ands[0]
                         and 0 < ands[0]["rect"][1] - b["rect"][1] < 24 and b["rect"][2] - b["rect"][0] > 200]
                if above:
                    roles["seller_names"] = above[-1:]
    for bs in roles.values():
        bs.sort(key=lambda b: (b["page"], round(b["rect"][1]), b["rect"][0]))
    # The property line often continues on an unlabeled blank right below it (riders, CO-3, ACSP-4).
    if "property" in roles:
        p = roles["property"][0]
        nxt = [b for b in found if b["page"] == p["page"] and b["kind"] != "check" and not b["label"].strip()
               and 0 < b["rect"][1] - p["rect"][1] < 20 and b["rect"][2] - b["rect"][0] > 200]
        roles["property"] += sorted(nxt, key=lambda b: b["rect"][1])[:1]
    return roles


def form_blanks(family):
    """(path, blanks, map or None) for a form family."""
    path = form_path(family)
    return path, blanks(path), load_map(family)
