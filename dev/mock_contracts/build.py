"""Build a mock FR/BAR contract package (one PDF) from a scenario spec. Local dev only, never shipped.

    .venv/bin/python dev/mock_contracts/build.py SPEC.json                  # out/mock-contracts/<id>/<Street>-Contract.pdf
    .venv/bin/python dev/mock_contracts/build.py SPEC.json --answer-key     # + key/<Street>-Answer-Key.json (deal-file schema)
    .venv/bin/python dev/mock_contracts/build.py SPEC.json --scanned        # + <Street>-Contract-Scanned.pdf (image only, 150 dpi)
    .venv/bin/python dev/mock_contracts/build.py SPEC.json --defects missing-initials,blank-default
    .venv/bin/python dev/mock_contracts/build.py --list-defects

The spec format, stages, defects and outputs are documented in docs/mock-contracts.md.
"""
import argparse
import io
import json
import os
import random
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import pymupdf  # noqa: E402

import answers  # noqa: E402
import letters  # noqa: E402
import scenario as sc  # noqa: E402
import stamp  # noqa: E402
from fields import MapError, auto_roles, form_blanks, resolve  # noqa: E402

OUT = os.path.join(ROOT, "out", "mock-contracts")
HELPERS = {"money": sc.money, "mdy": sc.mdy, "when": sc.when, "clock": sc.clock, "str": str, "len": len, "bool": bool, "any": any, "all": all,
           "round": round, "isinstance": isinstance, "min": min, "max": max, "int": int, "float": float}


class BuildError(Exception):
    pass


def _eval(expr, env, family, name):
    try:
        return eval(expr, {"__builtins__": {}}, env)  # noqa: S307 - dev tool, expressions come from committed maps
    except Exception as e:  # noqa: BLE001
        raise BuildError(f"fields/{family}.json {name}: {expr!r} failed: {e}") from e


def _signers(events, idx, skip):
    return [(p, k, dt) for p, k, dt in events.get(idx, []) if (idx, p, k, "sign") not in skip]


def render_document(doc, idx, S, skip):
    """One form, filled and signed per the scenario, as an in-memory PDF. Returns (pdf, filled blank count)."""
    family = doc["family"]
    if doc["role"] == "letter":  # a generated third-party document (letters.py), not a form
        return letters.render(family, S["ctx"], doc["values"], S["name"]), len(doc["values"])
    path, found, fmap = form_blanks(family)
    pdf = pymupdf.open(path)
    for page in pdf:
        stamp.redact_license(page)
    ctx = S["ctx"]
    env = dict(HELPERS)
    env.update(ctx)
    env["v"] = sc.Ctx(doc["values"])
    env["doc"] = sc.Ctx(doc)
    used, filled = set(), 0

    def put(blanks_, value, check=False):
        nonlocal filled
        if not blanks_:
            return
        for b in blanks_:
            used.add(b["id"])
        if check:
            if value:
                stamp.check(pdf[blanks_[0]["page"] - 1], blanks_[0]["rect"])
                filled += 1
            return
        if value in (None, "", False):
            return
        if len(blanks_) == 1 and blanks_[0]["kind"] == "area":
            stamp.area(pdf[blanks_[0]["page"] - 1], blanks_[0]["rect"], value)
        elif len(blanks_) > 1:
            ordered = sorted(blanks_, key=lambda b: (b["page"], b["rect"][1], b["rect"][0]))
            stamp.flow([(pdf[b["page"] - 1], b["rect"]) for b in ordered], value)
        else:
            b = blanks_[0]
            stamp.text(pdf[b["page"] - 1], b["rect"], value)
        filled += 1

    roles = auto_roles(found)
    fields = (fmap or {}).get("fields", {})
    for role, ids in (fmap or {}).get("roles", {}).items():
        roles[role] = resolve(found, ids if isinstance(ids, list) else [ids])
    overrides = doc.get("fill") or {}
    # A seller's counter on the contract: changed blanks get the struck value and the new one (step 1), and every change
    # gets the seller's and, once accepted, the buyer's initials in the margin beside it (step 5).
    marks = S.get("change_marks", []) if doc["role"] == "contract" else []
    changed = {m["field"]: m for m in marks if "text" not in m}
    # 1. Mapped fields (an override by field name wins over the map's expression).
    for name, f in fields.items():
        bl = resolve(found, f["at"])
        if not bl:
            raise BuildError(f"fields/{family}.json {name}: no blank matches {f['at']!r}. Check it with "
                             f"locate.py {family} --debug.")
        if "rows" in f:  # one value per blank, in order (CO-3 line numbers and terms)
            vals = overrides.get(name) or _eval(f["rows"], env, family, name) or []
            if len(vals) > len(bl):
                raise BuildError(f"{family} {name}: {len(vals)} rows given, the form has room for {len(bl)}.")
            for b, val in zip(bl, vals):
                put([b], val)
            continue
        if name in changed:
            b = bl[0]
            stamp.change(pdf[b["page"] - 1], b["rect"], changed[name]["old"], changed[name]["new"])
            changed[name]["at"] = b
            used.add(b["id"])
            filled += 1
            continue
        if name in overrides:
            val = overrides[name]
        elif "check" in f:
            val = _eval(f["check"], env, family, name)
        else:
            val = _eval(f["value"], env, family, name)
        put(bl, val, check="check" in f)
    # 2. The blanks every form shares, unless the map already placed them.
    common = {"seller_names": ctx["seller_names"], "buyer_names": ctx["buyer_names"],
              "property": ctx["property_address"],
              "effective_date": sc.mdy(ctx["effective_date"]) if ctx["effective_date"] else None}
    for role, value in common.items():
        bl = [b for b in roles.get(role, []) if b["id"] not in used]
        if role == "property" and len(bl) > 1:
            bl = bl[:1]  # one line is enough for an address; the continuation stays blank
        put(bl, value)
    # 3. Raw overrides by blank id (any form, mapped or not): "L141": "Survey", "P1.7": true (a checkbox).
    by_id = {b["id"]: b for b in found}
    for key, value in overrides.items():
        if key in fields:
            continue
        if key not in by_id:
            raise BuildError(f"{family}: fill key {key!r} is neither a field in fields/{family}.json nor a blank id. "
                             f"List the blanks with locate.py {family}.")
        b = by_id[key]
        put([b], value, check=b["kind"] == "check" or isinstance(value, bool))
    # 4. A seller disclosure's yes/no questions: plausible defaults, overridden by question text (answers.py).
    if doc["role"] == "disclosure":
        words = {i + 1: [w[:5] for w in p.get_text("words")] for i, p in enumerate(pdf)}
        pool = [b for b in found if b["id"] not in used]
        for box, _question, _answer in answers.choose(pool, words, doc["values"].get("answers"), doc["values"].get("default_answer")):
            stamp.check(pdf[box["page"] - 1], box["rect"])
            filled += 1
    # 5. Signatures, their dates and the initials on every page, per the signing timeline.
    for party, k, dt in _signers(S["events"], idx, skip):
        names = ctx["buyers"] if party == "buyer" else ctx["sellers"]
        name = names[k]
        font = {("buyer", 0): 0, ("seller", 0): 1, ("buyer", 1): 2, ("seller", 1): 0}.get((party, k), k % 3)
        tzs = sc.tz(dt)
        seed = f"{S['name']}|{family}|{party}|{k}"
        signs, dates_ = roles.get(f"sign:{party}", []), roles.get(f"date:{party}", [])
        if k < len(signs):
            stamp.signature(pdf[signs[k]["page"] - 1], signs[k]["rect"], name, dt, font, tzs, seed)
        if k < len(dates_):
            stamp.text(pdf[dates_[k]["page"] - 1], dates_[k]["rect"], sc.mdy(dt))
        prints = roles.get(f"print:{party}", [])
        if k < len(prints):
            stamp.text(pdf[prints[k]["page"] - 1], prints[k]["rect"], name)
        # Licensees sign next to their clients where the form has a line for them (Riders E and P).
        agent = "buyer_agent" if party == "buyer" else "listing_agent"
        agent_name = ctx["cooperating_associate" if party == "buyer" else "listing_associate"]
        if k == 0:
            for b in roles.get(f"sign:{agent}", [])[:1]:
                stamp.signature(pdf[b["page"] - 1], b["rect"], agent_name, dt + timedelta(minutes=9), 2, tzs, seed + "|agent")
            for d in roles.get(f"date:{agent}", [])[:1]:
                stamp.text(pdf[d["page"] - 1], d["rect"], sc.mdy(dt + timedelta(minutes=9)))
            for b in roles.get(f"initials:{agent}", []):
                stamp.initials(pdf[b["page"] - 1], b["rect"], sc.initials_of(agent_name), dt + timedelta(minutes=9), 2,
                               tzs, seed + "|agent")
        # Initials inside the form's body (Rider P's disclosure lines): one box per line for each signer.
        for b in roles.get(f"initials:{party}:{k + 1}", []):
            stamp.initials(pdf[b["page"] - 1], b["rect"], sc.initials_of(name), dt, font, tzs, seed)
        slot = f"{'B' if party == 'buyer' else 'S'}I{k + 1}"
        for b in roles.get(f"initials:{party}", []):
            if b["id"].endswith("." + slot) and (idx, party, k, f"p{b['page']}") not in skip:
                stamp.initials(pdf[b["page"] - 1], b["rect"], sc.initials_of(name), dt, font, tzs, seed)
    _change_initials(pdf, marks, found, fields, ctx, S["name"])
    return pdf, filled


def _change_initials(pdf, marks, found, fields, ctx, seed):
    """Initials beside each counter-offer change, in the right margin of its line: the first seller's when the seller
    made the counter, and below them the first buyer's on acceptance. Free-text terms flow onto Para. 20's empty lines
    after the buyer's own terms and are initialed beside their first line."""
    slots = {}

    def margin(page_no, y0, y1):
        """Two initials boxes side by side in the right margin of the changed line (seller, then buyer)."""
        page = pdf[page_no - 1]
        y = y0 - 1.5
        while any(abs(y - u) < 13 for u in slots.get(page_no, [])):
            y += 13
        slots.setdefault(page_no, []).append(y)
        w, h = page.rect.width, max(12, y1 - y0 + 3)
        return page, {"seller": pymupdf.Rect(w - 32, y, w - 17.5, y + h), "buyer": pymupdf.Rect(w - 16.5, y, w - 2, y + h)}

    for m in marks:
        if "text" in m:
            lines = sorted(resolve(found, fields[m["field"]]["at"]), key=lambda b: (b["page"], b["rect"][1]))
            empty = [b for b in lines if not any(w[4].strip("_") for w in pdf[b["page"] - 1].get_text("words", clip=pymupdf.Rect(b["rect"])))]
            if not empty:
                raise BuildError("Para. 20 has no empty line left for the seller's counter terms: shorten additional_terms.")
            stamp.flow([(pdf[b["page"] - 1], b["rect"]) for b in empty], m["text"])
            b = empty[0]
        else:
            b = m["at"]
        page, boxes = margin(b["page"], b["rect"][1], b["rect"][3])
        for party, at in (("seller", m["seller_at"]), ("buyer", m["buyer_at"])):
            if at is None:
                continue
            name = ctx["sellers" if party == "seller" else "buyers"][0]
            stamp.initials(page, boxes[party], sc.initials_of(name), at, 1 if party == "seller" else 0, sc.tz(at), f"{seed}|change|{party}")


def render_compensation(S):
    """The CASSB-1 compensation agreement for Rider GG, as its own PDF: filled from the map, then signed and initialed
    by the payer (the sellers, or the listing broker's associate) and the buyer's broker's associate."""
    C, ctx = S["compensation"], S["ctx"]
    path, found, fmap = form_blanks("CASSB")
    pdf = pymupdf.open(path)
    for page in pdf:
        stamp.redact_license(page)
    env = dict(HELPERS)
    env.update(ctx)
    env["v"] = sc.Ctx(C["values"])
    for name, f in fmap["fields"].items():
        bl = resolve(found, f["at"])
        val = _eval(f.get("check") or f["value"], env, "CASSB", name)
        if "check" in f:
            if val:
                stamp.check(pdf[bl[0]["page"] - 1], bl[0]["rect"])
        elif val not in (None, ""):
            stamp.text(pdf[bl[0]["page"] - 1], bl[0]["rect"], val)
    roles = {r: resolve(found, a if isinstance(a, list) else [a]) for r, a in fmap["roles"].items()}
    signers = [("buyer_agent", ctx["cooperating_associate"], C["buyers_broker_signed"], 2)]
    if C["payer_signed"]:
        if C["payer_party"] == "seller":
            signers += [("seller", n, C["payer_signed"] + timedelta(minutes=4 * k), 1) for k, n in enumerate(ctx["sellers"])]
        else:
            signers.append(("listing_agent", ctx["listing_associate"], C["payer_signed"], 0))
    seller_k = 0
    for party, name, dt, font in signers:
        tzs, seed = sc.tz(dt), f"{S['name']}|CASSB|{name}"
        if party == "seller":
            sign_at, date_at, initials_at = roles["sign:payer"][seller_k:seller_k + 1], roles["date:payer"][seller_k:seller_k + 1], \
                roles[f"initials:seller:{seller_k + 1}"]
            seller_k += 1
        elif party == "listing_agent":
            sign_at, date_at, initials_at = roles["sign:payer"][:1], roles["date:payer"][:1], roles["initials:listing_agent"]
        else:
            sign_at, date_at, initials_at = roles["sign:buyer_agent"], roles["date:buyer_agent"], roles["initials:buyer_agent"]
        for b in sign_at:
            stamp.signature(pdf[b["page"] - 1], b["rect"], name, dt, font, tzs, seed)
        for b in date_at:
            stamp.text(pdf[b["page"] - 1], b["rect"], dt.strftime("%m/%d/%y"))
        for b in initials_at:
            stamp.initials(pdf[b["page"] - 1], b["rect"], sc.initials_of(name), dt, font, tzs, seed)
    return pdf


def _skips(S):
    """Blanks the defects leave empty: {(doc index, party, signer, 'sign' | 'p<page>')}. scenario.build() fills in
    each defect's party, signer, document and page."""
    skip = set()
    for d in S["defects"]:
        if d["type"] == "missing-initials":
            skip.add((d["doc_index"], d["party"], d["signer"], f"p{d['page']}"))
        elif d["type"] == "missing-signature":
            skip.add((d["doc_index"], d["party"], d["signer"], "sign"))
    return skip


def scanned(src, dest, seed):
    """An image-only copy: every page rasterized in grayscale at 150 dpi, slightly rotated, on off-white paper with
    light speckle, saved as JPEG pages with no text layer (what a skill sees when an agent uploads a scan)."""
    from PIL import Image, ImageChops, ImageFilter
    rng = random.Random(seed)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        img = img.rotate(rng.uniform(-0.6, 0.6), resample=Image.BICUBIC, expand=False, fillcolor=255)
        img = img.point(lambda v: 18 + v * 225 // 255)  # toner isn't pure black, paper isn't pure white
        speckle = Image.effect_noise(img.size, 50).point(lambda v: 160 if v > 252 else 255)
        img = ImageChops.darker(img, speckle).filter(ImageFilter.GaussianBlur(0.45))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=62)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=buf.getvalue())
    out.save(dest, garbage=4, deflate=True)


def build(spec, out_dir=None, answer_key=False, scan=False, extra_defects=()):
    """Build the package. Returns {'pdf', 'answer_key', 'scanned', 'documents', 'notes', 'pages'}."""
    spec = dict(spec)
    if extra_defects:
        spec["defects"] = list(spec.get("defects") or []) + [d for d in extra_defects if d]
    S = sc.build(spec)
    out_dir = out_dir or os.path.join(OUT, S["name"])
    os.makedirs(out_dir, exist_ok=True)
    package = pymupdf.open()
    skip = _skips(S)
    listing = []
    for i, doc in enumerate(S["documents"]):
        pdf, filled = render_document(doc, i, S, skip)
        package.insert_pdf(pdf)
        listing.append(f"{doc['family']} ({doc['role']}, {len(pdf)} p, {filled} fields)")
    package.set_metadata({"title": f"{S['ctx']['property_address']} contract package", "author": "", "subject": "",
                          "keywords": "", "creator": "", "producer": ""})
    # The spec and the answer key go in key/, apart from the package: copying the package's files into an eval run
    # never brings the answers along, and names from the address keep keys from different packages apart.
    os.makedirs(os.path.join(out_dir, "key"), exist_ok=True)
    with open(os.path.join(out_dir, S["files"]["spec"]), "w") as f:  # what built this package
        json.dump(spec, f, indent=2, default=str)
    pdf_path = os.path.join(out_dir, S["files"]["package"])
    package.save(pdf_path, garbage=4, deflate=True)
    result = {"pdf": pdf_path, "documents": listing, "notes": S["notes"], "pages": len(package),
              "stage": S["ctx"]["stage"], "defects": [d["type"] for d in S["defects"]]}
    if S.get("compensation"):  # Rider GG's compensation agreement travels on its own, not in the package
        result["compensation_agreement"] = os.path.join(out_dir, S["files"]["compensation"])
        render_compensation(S).save(result["compensation_agreement"], garbage=4, deflate=True)
    officer = S["ctx"].get("pre_approval_officer")  # drawn while the letter rendered, so it's added to the key here
    if officer and isinstance(S["key"].get("offers"), list):
        for offer in S["key"]["offers"]:
            if offer.get("approval_max_price"):  # the offer this package's pre-approval letter backs
                offer.setdefault("loan_officer", officer)
    if answer_key:
        result["answer_key"] = os.path.join(out_dir, S["files"]["key"])
        with open(result["answer_key"], "w") as f:
            json.dump(S["key"], f, indent=2, default=str)
    if scan:
        result["scanned"] = os.path.join(out_dir, S["files"]["scanned"])
        scanned(package, result["scanned"], S["name"])
    return result


def parser():
    ap = argparse.ArgumentParser(description="Build a mock FR/BAR contract package (one PDF) from a scenario spec.")
    ap.add_argument("spec", nargs="?", help="scenario spec JSON (docs/mock-contracts.md#scenario-spec)")
    ap.add_argument("--out", help="output folder (default out/mock-contracts/<id>/: the spec's name, or street-stage-hash)")
    ap.add_argument("--answer-key", action="store_true", help="also write key/<Street>-Answer-Key.json: the ground truth in "
                    "contract-timeline's deal-file schema, plus the stage, documents and defects")
    ap.add_argument("--scanned", action="store_true", help="also write <Street>-<Contract|Offer>-Scanned.pdf: an image-only copy "
                    "(grayscale, slight skew and noise, no text layer)")
    ap.add_argument("--defects", default="", help="comma-separated defects to inject on top of the spec's "
                    "(see --list-defects)")
    ap.add_argument("--list-defects", action="store_true", help="print the defect names and what each one does")
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    if a.list_defects:
        for k, v in sc.DEFECTS.items():
            print(f"{k:20} {v}")
        return 0
    if not a.spec:
        parser().error("give a scenario spec JSON")
    with open(a.spec) as f:
        spec = json.load(f)
    try:
        r = build(spec, a.out, a.answer_key, a.scanned, [d.strip() for d in a.defects.split(",")])
    except (sc.ScenarioError, BuildError, MapError) as e:
        print(f"Can't build {spec.get('name') or os.path.basename(a.spec)}: {e}", file=sys.stderr)
        return 2
    print(f"{r['pdf']} ({r['pages']} pages, stage {r['stage']})")
    for d in r["documents"]:
        print(f"  {d}")
    for n in r["notes"]:
        print(f"  note: {n}")
    if r["defects"]:
        print(f"  defects: {', '.join(r['defects'])}")
    for k in ("compensation_agreement", "answer_key", "scanned"):
        if r.get(k):
            print(r[k])
    return 0


if __name__ == "__main__":
    sys.exit(main())
