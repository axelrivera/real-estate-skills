"""Build the release smoke-test kit in out/manual-test/ (dev only, never shipped).

    .venv/bin/python dev/manual_kit/build.py        # or: make manual-kit

One pass per release, about ten yes/no checks (CHECKS) in about twenty minutes: only what a person on the real
platform can see. The plugin installs, the profile is saved and found, uploads are read, files are delivered and open
(the PowerPoint, the calendar file), a buyer CMA carries into the offer in the same chat, and the best-effort line stays
in chat. Content, numbers and layout are never checked here: golden snapshots, the generated tests and the evals cover
them. See docs/manual-testing.md.

Makes every file a tester uploads (mock MLS 360 reports, a listing flyer, CMA exports, seller notes, FAR/BAR contract
packages and an other-state agreement), one folder per case with the prompt to paste, and an expected.md per case with
the checks and only the reference facts needed to answer them. The evals that mirror a case (`manual_case`) upload the
same files. The mock data is in data.json (a real city, Casselberry in Seminole County; every street, name, brokerage
and MLS number is made up).

The FAR/BAR packages come from dev/mock_contracts/build.py (local only: it needs the FAR/BAR PDFs in sources/).
Scratch work goes to out/manual-kit-work/; both folders are removed and rebuilt on every run.
"""
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "out", "manual-test")
WORK = os.path.join(ROOT, "out", "manual-kit-work")
PY = sys.executable
CSV_HEADER = ["Distance", "ML Number", "Status", "Address", "Legal Subdivision Name", "Heated Area", "Current Price",
              "Close Price", "Close Date", "Original List Price", "Contract Date", "Beds", "Full Baths", "Year Built",
              "Pool", "CDOM", "Seller Paid Buyer Costs", "Lot Size Acres", "Sold Terms", "Public Remarks"]

D = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
TODAY = D["today"]
esc = html.escape


class KitError(RuntimeError):
    pass


# --- helpers -------------------------------------------------------------------


def signed_stamp(text):
    """'09/24/2026 11:45 AM' -> '2026-09-24 11:45' (a deal file's effective_date_signed)."""
    return datetime.strptime(text, "%m/%d/%Y %I:%M %p").strftime("%Y-%m-%d %H:%M")

def rel(path):
    return os.path.relpath(path, ROOT)


def run(args, parse=True):
    """Run a skill script (or the mock-contract builder) with this interpreter; JSON output parsed."""
    p = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise KitError(f"{' '.join(args)} failed ({p.returncode}):\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return json.loads(p.stdout) if parse else p.stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def money(v):
    return f"${v:,.0f}" if v is not None else "none"


def long_date(iso):
    return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%B %-d, %Y")


def table(columns, rows):
    out = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    out += ["| " + " | ".join(str(c) if c not in (None, "") else "—" for c in r) + " |" for r in rows]
    return "\n".join(out)


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in rows:
            if len(r) != len(CSV_HEADER):
                raise KitError(f"CSV row has {len(r)} cells, expected {len(CSV_HEADER)}: {r[:4]}")
            w.writerow(r)


def prompt_md(case, uploads, steps, today=TODAY, note=None, upload_note=None):
    """prompt.md: what to upload and the prompts to paste, in order."""
    lines = [f"# {case}", ""]
    lines += ["## Upload", ""] + ([f"- `{u}`" for u in uploads] if uploads else ["Nothing."]) + [""]
    if upload_note:
        lines += [upload_note, ""]
    lines += ["## Prompts", ""]
    for i, s in enumerate(steps, 1):
        lines += [f"**{s.get('title', f'Step {i}')}**", ""]
        if s.get("upload"):
            lines += ["Upload first: " + ", ".join(f"`{u}`" for u in s["upload"]), ""]
        lines += ["```text", s["text"], "```", ""]
    if note:
        lines += [note, ""]
    return "\n".join(lines).rstrip() + "\n"


# --- PDF rendering (Playwright, the dev Chromium from make setup) --------------------

class Pdf:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch()
        self.css = open(os.path.join(HERE, "kit.css"), encoding="utf-8").read()

    def render(self, body, path, title):
        doc = (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>"
               f"<style>{self.css}</style></head><body>{body}</body></html>")
        page = self.browser.new_page()
        page.set_content(doc, wait_until="load")
        footer = (f"<div style='font-size:6.5pt;color:#777;width:100%;padding:0 0.45in;display:flex;"
                  f"justify-content:space-between;font-family:Arial'><span>{esc(D['footer'])}</span>"
                  "<span>Page <span class='pageNumber'></span> of <span class='totalPages'></span></span></div>")
        page.pdf(path=path, format="Letter", print_background=True, display_header_footer=True,
                 header_template="<span></span>", footer_template=footer, prefer_css_page_size=True)
        page.close()

    def close(self):
        self.browser.close()
        self._pw.stop()


def kv(pairs, cls="kv"):
    return f"<div class='{cls}'>" + "".join(f"<div><b>{esc(k)}:</b><span>{esc(v)}</span></div>" for k, v in pairs) + "</div>"


def grid(columns, rows):
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table class='grid'><tr>{head}</tr>{body}</table>"


def report_360_html(r):
    """A Stellar-style Cross Property 360 Property View: listing, public record, history, flood, photos."""
    h = r["header"]
    parts = [
        f"<div class='brandbar'><div><div class='mls'>{esc(r['title'])}</div>"
        f"<div class='small'>Stellar MLS · Generated {long_date(TODAY)}</div></div>"
        f"<div class='small'>MLS# {esc(h['mls'])}</div></div>",
        "<div class='head'>",
        f"<div class='photo main'>Photo 1 of {len(r['photos'])}<br>{esc(r['photos'][0])}</div>",
        f"<div><div class='addr'>{esc(h['address'])}</div><div>{esc(h['city_line'])}</div>"
        f"<div style='margin:5px 0'><span class='status'>{esc(h['status'])}</span>"
        f"<span>{esc(h['price_label'])}: </span><span class='price'>{esc(h['price'])}</span></div>"
        f"{kv(h['pairs'])}</div>",
        "</div>",
        "<h2>Public Remarks</h2>", f"<div class='remarks'>{esc(r['remarks'])}</div>",
    ]
    for s in r["sections"]:
        parts += [f"<h2>{esc(s['title'])}</h2>", kv(s["pairs"])]
    parts += ["<div class='tabhead pagebreak'>Tax</div>"]
    for s in r["tax_sections"]:
        parts += [f"<h2>{esc(s['title'])}</h2>", kv(s["pairs"])]
    a = r["assessments"]
    parts += ["<h2>Assessment and Taxes</h2>", grid(a["columns"], a["rows"])]
    v = r["avm"]
    parts += ["<h2>Estimated Value (RealAVM)</h2>",
              kv([["Estimated Value", v["value"]], ["Value Range", f"{v['low']} to {v['high']}"],
                  ["Confidence Score", v["confidence"]]])]
    parts += ["<div class='tabhead pagebreak'>History</div>", "<h2>Listing History from MLS</h2>"]
    for b in r["history"]:
        parts += [f"<div class='block'><div class='blockhead'>MLS# {esc(b['mls'])} · Status: {esc(b['status'])}</div>",
                  grid(["Eff Date", "Change Type", "Change Info", "Current Price", "DOM"], b["rows"]), "</div>"]
    parts += ["<h2>Sale History from Public Records</h2>", grid(r["sales"]["columns"], r["sales"]["rows"]),
              "<h2>Mortgage History</h2>", grid(r["mortgages"]["columns"], r["mortgages"]["rows"])]
    f = r["flood"]
    parts += ["<h2>Flood Map</h2>",
              kv([["Flood Zone", f["zone"]], ["Panel", f["panel"]], ["Panel Date", f["panel_date"]]]),
              f"<p>{esc(f['note'])}</p>",
              "<h2>Foreclosure</h2>", f"<p>{esc(r['foreclosure'])}</p>"]
    parts += ["<div class='tabhead pagebreak'>Photos</div>", "<div class='photos' style='margin-top:8px'>"]
    parts += [f"<div class='photo'>Photo {i} of {len(r['photos'])}<br>{esc(p)}</div>" for i, p in enumerate(r["photos"], 1)]
    parts += ["</div>"]
    return "\n".join(parts)


def flyer_html(home):
    f = home["flyer"]
    facts = "".join(f"<div><b>{esc(v)}</b>{esc(k)}</div>" for k, v in f["facts"])
    feats = "".join(f"<li>{esc(x)}</li>" for x in f["features"])
    return (f"<div class='flyer'><div class='top'><div class='h'>{esc(f['headline'])}</div>"
            f"<div>{esc(home['address'])}, {esc(home['city'])}, {home['state']} {home['zip']}</div>"
            f"<div class='p'>{esc(f['price'])}</div></div>"
            "<div class='photo hero'>Listing photo: front exterior (placeholder)</div>"
            f"<div class='facts'>{facts}</div><p>{esc(f['remarks'])}</p><ul>{feats}</ul>"
            f"<div class='agent'><div><b>{esc(f['agent'])}</b><br>{esc(f['brokerage'])}<br>{esc(f['phone'])}</div>"
            f"<div style='text-align:right'>{esc(f['mls'])}<br>Information deemed reliable but not guaranteed.</div></div></div>")


def agreement_html(a):
    def fill(v):
        return f"<span class='fill'>{esc(str(v))}</span>"
    eff = long_date(a["effective_date"])
    close = long_date(a["closing_date"])
    loan = round(a["price"] * 0.8)
    paras = [
        ("1. Parties and Property.", f"{fill(a['seller'])} (\"Seller\") agrees to sell, and {fill(a['buyer'])} (\"Buyer\") "
         f"agrees to buy, the real property at {fill(a['property'])}, {fill(a['county'])} County, Ohio, with all fixtures "
         "and the range, refrigerator, dishwasher and window coverings (the \"Property\")."),
        ("2. Purchase Price.", f"The purchase price is {fill(money(a['price']))}, paid as follows: earnest money of "
         f"{fill(money(a['earnest_money']))} (Paragraph 3); a conventional mortgage loan of {fill(money(loan))} "
         "(Paragraph 4); and the balance in good funds at Closing."),
        ("3. Earnest Money.", f"Buyer shall deliver the earnest money to {fill(a['escrow_agent'])} (\"Escrow Agent\") "
         f"within {fill(3)} days after the Effective Date. If Buyer does not, Seller may terminate this Agreement by "
         "written notice to Buyer."),
        ("4. Financing.", f"This Agreement is contingent on Buyer obtaining a conventional loan of {fill(money(loan))}. "
         f"Buyer shall apply for the loan within {fill(5)} days after the Effective Date. If Buyer has not delivered "
         f"a written loan commitment to Seller within {fill(21)} days after the Effective Date, Buyer may terminate this "
         "Agreement by written notice delivered before that period ends, and the earnest money shall be returned to "
         "Buyer. After that period ends, this financing contingency no longer applies."),
        ("5. Appraisal.", "If the Property appraises below the purchase price, Buyer may terminate this Agreement by "
         f"written notice delivered within {fill(14)} days after the Effective Date, and the earnest money shall be "
         "returned to Buyer."),
        ("6. Inspections.", f"Buyer may have the Property inspected at Buyer's expense. Within {fill(10)} days after "
         "the Effective Date, Buyer may deliver written notice terminating this Agreement or requesting repairs. If Buyer "
         "delivers no notice within that period, Buyer accepts the Property in its present condition."),
        ("7. Title.", "Seller shall convey marketable title by general warranty deed, free of liens other than those "
         "Buyer assumes. Escrow Agent shall provide a title commitment to Buyer before Closing."),
        ("8. Closing and Possession.", f"Closing shall take place on or before {fill(close)} at {fill('1:00 p.m.')} at "
         "the office of Escrow Agent. Seller shall deliver possession and keys at Closing."),
        ("9. Final Walk-Through.", "Buyer may walk through the Property on the day before Closing to confirm its "
         "condition."),
        ("10. Time Periods.", "\"Days\" means calendar days. A period measured from the Effective Date begins on the day "
         "after the Effective Date and ends at 11:59 p.m. local time on its last day. If the last day of a period falls "
         "on a Saturday, Sunday or federal legal holiday, the period ends on the next day that is not a Saturday, Sunday "
         "or federal legal holiday. Time is of the essence."),
        ("11. Effective Date.", "The Effective Date is the date on which the last party signs this Agreement, as written "
         "on the signature page."),
        ("12. Entire Agreement.", "This Agreement is the entire agreement of the parties. Any change must be in writing "
         "and signed by Buyer and Seller. Notices must be in writing and may be delivered by email to the parties' "
         "agents."),
    ]
    body = [f"<div class='rpa'><h1>{esc(a['title'])}</h1><div class='sub'>{esc(a['form_note'])}</div>"]
    body += [f"<p><b>{esc(h)}</b> {t}</p>" for h, t in paras]
    body += ["<p style='page-break-before:always'><b>Signatures.</b> Buyer offers to buy the Property on these terms. "
             "Seller accepts.</p>",
             "<table class='sig'><tr>"
             f"<td><span class='name'>{esc(a['buyer'])}</span></td><td><span class='name'>{esc(a['seller'])}</span></td></tr>"
             f"<tr class='label'><td>Buyer: {esc(a['buyer'])} · Signed {esc(a['buyer_signed'])}</td>"
             f"<td>Seller: {esc(a['seller'])} · Signed {esc(a['seller_signed'])}</td></tr></table>",
             f"<p style='margin-top:14px'><b>Effective Date</b> (date of the last signature): {fill(eff)}</p>",
             "<table class='sig'><tr>"
             f"<td>Buyer's brokerage: {esc(a['buyer_brokerage'])}<br>Agent: {esc(a['buyer_agent'])}</td>"
             f"<td>Seller's brokerage: {esc(a['seller_brokerage'])}<br>Agent: {esc(a['seller_agent'])}</td></tr></table>",
             f"<p style='margin-top:14px'>Escrow Agent: {esc(a['escrow_agent'])}, Westerville, Ohio.</p></div>"]
    return "\n".join(body)


# --- mock contract packages ------------------------------------------------------------

def build_package(spec_path, name):
    """Build a mock FAR/BAR package with its answer key into WORK/pkg/<name>/ (deterministic: seeded by the name)."""
    out = os.path.join(WORK, "pkg", name)
    run(["dev/mock_contracts/build.py", spec_path, "--answer-key", "--out", out], parse=False)
    key = next(os.path.join(out, "key", f) for f in os.listdir(os.path.join(out, "key")) if f.endswith("-Answer-Key.json"))
    pdfs = sorted(f for f in os.listdir(out) if f.endswith(".pdf") and "Scanned" not in f)
    return out, json.load(open(key, encoding="utf-8")), pdfs


def pdf_text(path, pages=None):
    import pymupdf
    with pymupdf.open(path) as d:
        return "\n".join(d[i].get_text() for i in (pages or range(len(d))))


def listing_side(key):
    """(listing broker, listing associate) from a package's answer key: the compensation agreement's payer."""
    payer = ((key.get("mock") or {}).get("compensation_agreement") or {}).get("payer") or ""
    m = re.fullmatch(r"(.+) \(signed by (.+)\)", payer)
    return (m.group(1), m.group(2)) if m else (None, None)


def second_offer_spec(aga_dir, aga_pdf, aga_key):
    """The kit's second offer on the asis-offer-aga listing: same parcel, legal description, HOA contact and listing
    brokerage as the first offer's package, so both read as the same listing."""
    spec = json.load(open(os.path.join(HERE, D["offer_review"]["second_offer_spec"]), encoding="utf-8"))
    broker, associate = listing_side(aga_key)
    if not broker:
        raise KitError("Couldn't read the listing brokerage from the asis-offer-aga answer key.")
    spec["brokers"].update(listing_broker=broker, listing_associate=associate)
    text = subprocess.run(["pdftotext", "-layout", os.path.join(aga_dir, aga_pdf), "-"], capture_output=True,
                          text=True).stdout if shutil.which("pdftotext") else pdf_text(os.path.join(aga_dir, aga_pdf))
    tax = re.search(r"Property Tax ID #:\s*(\S+)", text)
    legal = re.search(r"legal description is (.+?)\n\s*12\s", text, re.S)
    contact = re.search(r"Contact Person_+\s*\n\s*(\S+ \S+)", text)
    phone = re.search(r"Phone (\(\d{3}\) \d{3}-\d{4})", text)
    if not (tax and legal and contact and phone):
        raise KitError("Couldn't read the tax ID, legal description or HOA contact from the asis-offer-aga package.")
    # OFR-345: the HOA's fee, period and names come from the first package too, or the scenario re-seeds them and the
    # two packages disagree ($95 a quarter vs. $95 a month)
    fee = re.search(r"CURRENT AMOUNT IS\s+([\d,]+\.\d{2})\s*\n\s*\$_*\s*PER\s+(\w+)", text)
    assoc = re.search(r"is/are:\s*\n[\s_]*\n\s*(\S.*?Association, Inc\.)\s.*\n\s*(\S[^\n_]*?)\s*\n", text)
    email = re.search(r"Email (\S+@\S+)", text)
    if not (fee and assoc):
        raise KitError("Couldn't read the HOA fee or association from the asis-offer-aga package.")
    hoa_fee, hoa_period = float(fee.group(1).replace(",", "")), fee.group(2).lower()
    if round(hoa_fee / {"quarter": 3, "year": 12}.get(hoa_period, 1), 2) != aga_key["listing"].get("hoa_monthly"):
        raise KitError(f"The HOA fee read from the package ({hoa_fee:g} per {hoa_period}) doesn't match its answer key.")
    legal_text = " ".join(re.sub(r"^\s*\d+\s", " ", ln).strip() for ln in legal.group(1).splitlines()).strip()
    legal_text = re.sub(r"\s+", " ", legal_text)
    spec["property"]["tax_id"] = tax.group(1)
    spec["property"]["legal_description"] = legal_text
    rider = {"code": "B", "contact": contact.group(1), "phone": phone.group(1), "fee": round(hoa_fee, 2),
             "fee_period": hoa_period, "association": assoc.group(1), "management_company": assoc.group(2)}
    if email:
        rider["email"] = email.group(1)
    spec["riders"] = [rider]
    path = os.path.join(WORK, "sable-palm-second-offer.json")
    dump(path, spec)
    return path, {"tax_id": tax.group(1), "legal": legal_text, "hoa_contact": contact.group(1),
                  "hoa": f"${hoa_fee:,.0f} per {hoa_period}"}


def deal_from_key(key, today):
    """The answer key as a contract-timeline deal file, with what the package shows as done and the report date."""
    deal = {k: v for k, v in key.items() if k != "mock"}
    done = {}
    for dep in key["mock"].get("deposits_received") or []:
        if "initial" in dep["label"].lower():
            done["deposit"] = datetime.strptime(dep["date"][:10], "%m/%d/%Y").strftime("%Y-%m-%d")
    ca = key["mock"].get("compensation_agreement") or {}
    if ca.get("executed") and ca.get("payer_signed"):
        done["compensation_agreement"] = datetime.strptime(ca["payer_signed"][:10], "%m/%d/%Y").strftime("%Y-%m-%d")
    deal["completed"] = {k: v for k, v in done.items() if v <= today}
    deal["report_date"] = today
    return deal



# --- cases -----------------------------------------------------------------------------
# Each case writes its uploads, prompt.md and an expected.md holding only the reference facts its checks need.

def expected_md(case, title, facts, intro=None):
    lines = [f"# {title}: Expected", ""]
    if intro:
        lines += [intro, ""]
    if facts:
        lines += ["## Reference Facts", ""] + [f"- {f}" for f in facts] + [""]
    lines += ["## Checks (Yes or No)", ""] + [f"- {c}" for c in check_texts(case)]
    write(os.path.join(OUT, case, "expected.md"), "\n".join(lines))


def case_profile():
    case = "01-agent-profile"
    write(os.path.join(OUT, case, "prompt.md"), prompt_md("Case 1: Agent Profile", [], [
        {"title": "Prompt", "text": "Set up my profile."}],
        note="Answer the questions with your own details (name, brokerage, license, phone, email, brand colors or a "
             "logo). Later cases use the profile this case saves."))
    expected_md(case, "Case 1", [
        f"The plugin lists {len(SKILLS)} skills: {', '.join(SKILLS)}.",
        "Cowork: `profile.md` lands directly in the working folder (open it: your details, no placeholders).",
        "claude.ai: there is no working folder, so the profile comes back as a file to keep."])


def case_seller_cma(pdf):
    case, h = "02-seller-cma", D["seller_home"]
    d = os.path.join(OUT, case)
    os.makedirs(d, exist_ok=True)
    export = os.path.join(d, h["export_file"])
    write_csv(export, h["rows"])
    pdf.render(report_360_html(h["report_360"]), os.path.join(d, h["report_file"]), "360 Property View")
    write(os.path.join(d, h["notes_file"]), "\n".join(h["notes"]))
    stats = run(["skills/seller-cma/scripts/stats.py", rel(export), "--address", h["mls_address"], "--sqft",
                 str(h["sqft"]), "--subdivision", h["subdivision"], "--state", h["state"], "--county", h["county"],
                 "--split-date", h["split_date"], "--as-of", TODAY] + (["--pool"] if h["pool"] else []))
    if not stats.get("ok"):
        raise KitError(f"seller stats.py: {stats}")
    if stats["subject_rows"]:  # the skill would stop to ask whose listing it is
        raise KitError("The seller's home has rows in the export: the case would stop on a question.")
    expired = h["report_360"]["history"][1]
    expected_md(case, "Case 2", [
        f"From the 360 report (PDF): the expired listing MLS# {expired['mls']}, listed at {expired['rows'][-1][3]}, "
        f"expired after {expired['rows'][0][4]} days.",
        f"From the export (CSV): {stats['sold_all']['n']} homes sold in the window.",
        "Files delivered: the report PDF, the PowerPoint and a PDF copy of the slides."])
    write(os.path.join(d, "prompt.md"), prompt_md("Case 2: Seller CMA", [h["report_file"], h["export_file"],
                                                                          h["notes_file"]], [
        {"title": "Step 1 (new session)", "text":
            f"Today is {long_date(TODAY)}. I have a listing appointment for {h['address']} in {h['city']}. Attached are "
            "the MLS 360 property report, my CMA export and my notes from the call with the sellers. What should we list "
            "at? I need the seller CMA report."},
        {"title": "Step 2 (same chat)", "text": "Now build the listing presentation for the appointment."}],
        upload_note="claude.ai only: also upload the `profile.md` case 1 gave you (Cowork finds it in the working folder)."))


def case_buyer_cma(pdf):
    case, h = "03-buyer-cma", D["buyer_home"]
    d = os.path.join(OUT, case)
    os.makedirs(d, exist_ok=True)
    export = os.path.join(d, h["export_file"])
    write_csv(export, h["rows"])
    pdf.render(report_360_html(h["report_360"]), os.path.join(d, h["report_file"]), "360 Property View")
    pdf.render(flyer_html(h), os.path.join(d, h["flyer_file"]), "Listing Flyer")
    stats = run(["skills/buyer-cma/scripts/stats.py", rel(export), "--address", h["mls_address"], "--state", h["state"],
                 "--county", h["county"], "--mls-number", h["mls"], "--split-date", h["split_date"], "--as-of", TODAY])
    if not stats.get("ok") or not stats.get("subject_row"):
        raise KitError(f"buyer stats.py didn't find the subject row: {stats.get('problems') or stats.get('market_notes')}")
    expected_md(case, "Case 3", [
        "File delivered: the buyer CMA PDF."])
    write(os.path.join(d, "prompt.md"), prompt_md("Case 3: Buyer CMA", [h["flyer_file"], h["report_file"],
                                                                         h["export_file"]], [
        {"title": "Prompt", "text":
            f"Today is {long_date(TODAY)}. My buyer is looking at {h['address']} in {h['city']}. Here are the listing "
            "flyer, the MLS 360 property report and my CMA export. Is it priced right and what should we offer? I need "
            "the buyer CMA PDF."}],
        note="Keep this chat open: case 4 continues in it."))


def case_offer_strategy():
    case, h, lim = "04-buyer-offer-strategy", D["buyer_home"], D["buyer_limits"]
    expected_md(case, "Case 4", ["Files delivered: Offer Options and Offer Package Worksheet (two PDFs)."],
                intro="Run in the case 3 chat: nothing is uploaded. Asking for a CMA file or an upload is a failure.")
    write(os.path.join(OUT, case, "prompt.md"), prompt_md("Case 4: Buyer Offer Strategy", [], [
        {"title": "Prompt (in the case 3 chat)", "text":
            f"Now help me write the offer on {h['address']}. My buyer: {lim['prompt']} I need the offer options "
            "report and the offer package worksheet."}],
        note="Run this in the same chat as case 3, right after the buyer CMA: don't start a new chat and don't upload "
             "anything. If it asks for anything else, answer from the prompt or say you don't know."))


def case_offer_review():
    """Two offers on one listing: step 1 uploads the first, step 2 the second in the same chat (as the mirroring eval,
    seller-offer-review eval 8, does)."""
    case, o = "05-seller-offer-review", D["offer_review"]
    d = os.path.join(OUT, case)
    aga_dir, aga_key, aga_pdfs = build_package(f"dev/mock_contracts/scenarios/{o['starter']}.json", o["starter"])
    offer_pdf = next(p for p in aga_pdfs if p.endswith("-Offer.pdf"))
    spec, _ = second_offer_spec(aga_dir, offer_pdf, aga_key)
    b_dir, b_key, b_pdfs = build_package(rel(spec), "manual-kit-sable-palm-second-offer")
    if listing_side(b_key) != listing_side(aga_key):
        raise KitError("The two offer packages name different listing brokerages.")
    if b_key["listing"]["address"] != aga_key["listing"]["address"]:
        raise KitError("The second offer isn't on the same listing.")
    if b_key["listing"].get("hoa_monthly") != aga_key["listing"].get("hoa_monthly"):
        raise KitError("The two offer packages show different HOA fees.")
    a_agent, b_agent = aga_key["offers"][0]["buyer_agent"], b_key["offers"][0]["buyer_agent"]
    if a_agent.split()[-1][:5] == b_agent.split()[-1][:5]:
        raise KitError(f"The buyer's agents' surnames read alike ({a_agent}, {b_agent}): rename one in the scenario.")
    # Both packages are for the same street, so the buyer's surname keeps the second upload from replacing the first
    for src_dir, pdfs, key, step in ((aga_dir, aga_pdfs, aga_key, "step-1"), (b_dir, b_pdfs, b_key, "step-2")):
        buyer = key["offers"][0]["buyer"].split()[-1]
        os.makedirs(os.path.join(d, step), exist_ok=True)
        for p in pdfs:
            shutil.copy(os.path.join(src_dir, p), os.path.join(d, step, p.replace(".pdf", f"-{buyer}.pdf")))
    a, b = aga_key["offers"][0], b_key["offers"][0]
    who = lambda x: f"{money(x['price'])} from {x['buyer']} (buyer's agent {x['buyer_agent']}, {x['buyer_brokerage']})"
    expected_md(case, "Case 5", [
        f"Step 1, the first offer: {who(a)}. File delivered: the offer review PDF.",
        f"Step 2, the second offer: {who(b)}. Files delivered: the comparison PDF and a review PDF for each offer."])
    up1, up2 = ([f"{st}/{p}" for p in sorted(os.listdir(os.path.join(d, st)))] for st in ("step-1", "step-2"))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 5: Seller Offer Review", up1 + up2, [
        {"title": "Step 1 (new session)", "upload": up1, "text":
            f"Today is {long_date(o['today'])}. I'm the listing agent for {aga_key['listing']['address']}, listed at "
            f"{money(o['list_price'])}. We got this offer. Should my seller accept, and what should we counter?"},
        {"title": "Step 2 (same chat)", "upload": up2, "text":
            "A second offer just came in on the same listing. Compare both offers, rank them and give me a plan. I'd "
            "like the PDF for my seller."}],
        today=o["today"]))


def case_timeline():
    case, starter = "06-contract-timeline-fha", "asis-fha-executed"
    d = os.path.join(OUT, case)
    src, key, pdfs = build_package(f"dev/mock_contracts/scenarios/{starter}.json", starter)
    os.makedirs(d, exist_ok=True)
    for p in pdfs:
        shutil.copy(os.path.join(src, p), os.path.join(d, p))
    work = os.path.join(WORK, case)
    dump(os.path.join(work, "deal.json"), deal_from_key(key, TODAY))
    t = run(["skills/contract-timeline/scripts/timeline.py", rel(os.path.join(work, "deal.json"))])
    if not t.get("ok") or not t.get("closing"):
        raise KitError(f"timeline.py {starter}: {t}")
    c = key["contract"]
    expected_md(case, "Case 6", [
        f"Closing: {t['closing']['display']}; the calendar shows it on that date.",
        f"First deadline: {t['first_deadline']['label']}, {t['first_deadline']['display']}.",
        "Files delivered: the timeline PDF and a calendar file (.ics)."])
    address, city = c["property"].split(",")[0], c["property"].split(",")[1].strip()
    write(os.path.join(d, "prompt.md"), prompt_md("Case 6: Contract Timeline", pdfs, [{"title": "Prompt", "text":
        f"Today is {long_date(TODAY)}. Here's my buyer's executed contract package for {address}, {city}. Give me every "
        "deadline as a PDF timeline and a calendar file."}]))


def case_other_state(pdf):
    case, a = "07-contract-timeline-other-state", D["other_state"]
    d = os.path.join(OUT, case)
    os.makedirs(d, exist_ok=True)
    pdf.render(agreement_html(a), os.path.join(d, a["file"]), a["title"])
    deal = {"side": "buyer", "state": a["state"], "county": a["county"], "client": a["buyer"], "report_date": TODAY,
            "rules": a["rules"],
            "contract": {"form_family": "other", "form": a["title"], "property": a["property"], "buyer": a["buyer"],
                         "seller": a["seller"], "price": a["price"], "financing": "conventional",
                         "effective_date": a["effective_date"], "effective_date_source": "Seller's signature",
                         "effective_date_signed": signed_stamp(a["seller_signed"]), "closing_date": a["closing_date"],
                         "closing_time": a["closing_time"], "escrow_agent": a["escrow_agent"]},
            "deadlines": a["deadlines"], "amendments": []}
    work = os.path.join(WORK, case)
    dump(os.path.join(work, "deal.json"), deal)
    t = run(["skills/contract-timeline/scripts/timeline.py", rel(os.path.join(work, "deal.json"))])
    if not t.get("ok") or t.get("support") != "best_effort" or not t.get("chat_notes"):
        raise KitError(f"timeline.py other state: no best-effort chat line: {t}")
    expected_md(case, "Case 7", [
        f"A made-up {a['title']} for a home in Ohio: not a FAR/BAR contract, so the reply says once that it was "
        "read on a best-effort basis (only Florida FAR/BAR contracts are fully supported).",
        "The PDF and the calendar file say nothing about support: search them for \"best effort\" and \"supported\"."])
    write(os.path.join(d, "prompt.md"), prompt_md("Case 7: Contract Timeline (Other State)", [a["file"]], [
        {"title": "Prompt", "text":
            f"Today is {long_date(TODAY)}. Here's my buyer's signed purchase agreement for a home in Westerville, Ohio. "
            "Lay out every deadline for my buyer: I need the PDF timeline and a calendar file."}]))


NET_SHEET = {"address": "3318 Wren Hollow Ln", "city": "Casselberry", "county": "Seminole", "prices": (425000, 410000),
             "credit": 6000, "payoff": 188000, "annual_tax": 5400, "closing": "2026-12-04"}


def case_net_sheet():
    case, n = "08-seller-net-sheet", NET_SHEET
    write(os.path.join(OUT, case, "prompt.md"), prompt_md("Case 8: Seller Net Sheet", [], [{"title": "Prompt", "text":
        f"Today is {long_date(TODAY)}. Net sheet for my seller at {n['address']}, {n['city']} ({n['county']} County): "
        f"{money(n['prices'][0])} and {money(n['prices'][1])}, and {money(n['prices'][0])} with a {money(n['credit'])} "
        f"credit to the buyer. They owe about {money(n['payoff'])}. My listing agreement is 2.75% and 2.5% to the "
        f"buyer's agent. Taxes are {money(n['annual_tax'])} a year. We'd close around {long_date(n['closing'])}. "
        "I need a PDF to print."}]))
    expected_md(case, "Case 8", ["File delivered: one PDF, one page, three price columns."])


# --- checks, README, results ---------------------------------------------------------------

SKILLS = sorted(s for s in os.listdir(os.path.join(ROOT, "skills"))
                if os.path.isfile(os.path.join(ROOT, "skills", s, "SKILL.md")))

# The smoke checks, yes or no: what only a person on the real platform can see. Content, numbers and layout are never
# checked here (golden, the generated tests and the evals cover them). Each: (text, where), where "both" (Cowork and
# claude.ai), "cowork" or "ai". The claude.ai pass runs cases 1, 2 and 6.
CHECKS = {
    "01-agent-profile": [("The plugin installs and every skill is listed", "both"),
                         ("profile.md is saved in the working folder", "cowork"),
                         ("The profile comes back as a file to keep", "ai")],
    "02-seller-cma": [("A new session uses the saved profile without an upload (name and colors on the PDF)", "cowork"),
                      ("The uploaded profile is used (name and colors on the PDF)", "ai"),
                      ("The uploads are read: the 360 PDF's expired listing and the CSV export's sales count appear",
                       "both"),
                      ("The listing presentation is delivered and opens in PowerPoint or Keynote", "both")],
    "03-buyer-cma": [("The buyer CMA PDF is delivered and opens", "cowork")],
    "04-buyer-offer-strategy": [("In the same chat, the offer uses the buyer CMA without asking for an upload, and "
                                 "both PDFs are delivered", "cowork")],
    "05-seller-offer-review": [("Step 1: the offer package is read and the offer review PDF is delivered", "cowork"),
                               ("Step 2: the same chat keeps the first offer, compares both and delivers the comparison "
                                "PDF", "cowork")],
    "06-contract-timeline-fha": [("The calendar file imports into a calendar app with closing on the right date",
                                  "both")],
    "07-contract-timeline-other-state": [("The best-effort line is in the chat reply only, never in the PDF or the "
                                          "calendar file", "cowork")],
    "08-seller-net-sheet": [("The net sheet PDF is delivered on one page", "cowork")],
}
WHERE = {"both": "Cowork and claude.ai", "cowork": "Cowork", "ai": "claude.ai"}


def check_texts(case):
    """The checks as expected.md lists them, each with where it runs."""
    return [f"{c} ({WHERE[where]})" for c, where in CHECKS[case]]


def results_md():
    rows = [[case, c, "" if where != "ai" else "n/a", "" if where != "cowork" else "n/a", ""]
            for case, checks in CHECKS.items() for c, where in checks]
    head = ["# Smoke Test Results", "", "Version: ", "Tester: ", "Date: ", "",
            "Mark each empty cell Yes or No. Add a note for every No (what happened, which file).", ""]
    out = ["| Case | Check | Cowork | claude.ai | Notes |", "|---|---|---|---|---|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(head + out)


def readme_md():
    return "\n".join([
        "# Smoke Test Kit", "",
        f"Built {datetime.now():%Y-%m-%d %H:%M} by `make manual-kit`. Every file here is mock data: Casselberry and the "
        "other cities are real, every street, name, brokerage, parcel and MLS number is made up. Nothing here is "
        "committed; rebuild it for each release.", "",
        "The steps are in `docs/manual-testing.md`. Each folder has `prompt.md` (what to upload, the prompt to paste), "
        "the files to upload and `expected.md` (the yes/no checks and the facts to answer them; never upload it). "
        "Fill in `results.md` as you go.", "",
        table(["Folder", "Skill", "Upload"], [
            ["01-agent-profile", "agent-profile", "nothing"],
            ["02-seller-cma", "seller-cma", "360 report, CMA export, seller notes"],
            ["03-buyer-cma", "buyer-cma", "listing flyer, 360 report, CMA export"],
            ["04-buyer-offer-strategy", "buyer-offer-strategy", "nothing: continue the case 3 chat"],
            ["05-seller-offer-review", "seller-offer-review", "the step-1 offer, then the step-2 offer in the same chat"],
            ["06-contract-timeline-fha", "contract-timeline", "executed FHA package"],
            ["07-contract-timeline-other-state", "contract-timeline", "Ohio purchase agreement"],
            ["08-seller-net-sheet", "seller-net-sheet", "nothing"]]), "",
        "claude.ai pass: upload `dist/skills/*.zip`, then run cases 1, 2 (with the case 1 `profile.md`) and 6.",
    ])


# --- verification -----------------------------------------------------------------------

def verify():
    """Every case folder has its files; every PDF opens and holds the text it should."""
    must = {
        "02-seller-cma": {D["seller_home"]["report_file"]: ["842 TANAGER RIDGE DR", "ACT->EXP", "X4488112", "Tax Area"]},
        "03-buyer-cma": {D["buyer_home"]["report_file"]: ["2315 KESTREL POINT CT", "474900.00->464900", "Active"],
                         D["buyer_home"]["flyer_file"]: ["$464,900", "Lakeshore Crest Realty"]},
        "07-contract-timeline-other-state": {D["other_state"]["file"]: ["Residential Purchase Agreement",
                                                                        "within 3 days", "September 24, 2026"]},
    }
    problems = []
    for case in CHECKS:
        d = os.path.join(OUT, case)
        for f in ("prompt.md", "expected.md"):
            if not os.path.exists(os.path.join(d, f)):
                problems.append(f"{case}/{f} missing")
        for root, dirs, files in os.walk(d):
            if "key" in dirs:
                problems.append(f"{case}: an answer key folder was copied")
            for f in files:
                if f.endswith(".pdf"):
                    text = pdf_text(os.path.join(root, f))
                    if len(text) < 200:
                        problems.append(f"{case}/{f}: almost no text")
                    for needle in must.get(case, {}).get(f, []):
                        if needle not in text:
                            problems.append(f"{case}/{f}: missing {needle!r}")
                if f in ("expected.md", "prompt.md"):
                    body = open(os.path.join(root, f), encoding="utf-8").read()
                    if "key/" in body and "Answer-Key" in body:
                        problems.append(f"{case}/{f} points at an answer key")
    for f in ("README.md", "results.md"):
        if not os.path.exists(os.path.join(OUT, f)):
            problems.append(f"{f} missing")
    if problems:
        raise KitError("Verification failed:\n  " + "\n  ".join(problems))


def main():
    for p in (OUT, WORK):
        shutil.rmtree(p, ignore_errors=True)
        os.makedirs(p)
    pdf = Pdf()
    try:
        for name, build in (("01 agent-profile", case_profile), ("02 seller-cma", lambda: case_seller_cma(pdf)),
                            ("03 buyer-cma", lambda: case_buyer_cma(pdf)), ("04 buyer-offer-strategy", case_offer_strategy),
                            ("05 seller-offer-review", case_offer_review), ("06 contract-timeline", case_timeline),
                            ("07 contract-timeline (other state)", lambda: case_other_state(pdf)),
                            ("08 seller-net-sheet", case_net_sheet)):
            print(name)
            build()
    finally:
        pdf.close()
    write(os.path.join(OUT, "README.md"), readme_md())
    write(os.path.join(OUT, "results.md"), results_md())
    verify()
    print(f"Kit ready: {rel(OUT)}/")


if __name__ == "__main__":
    try:
        main()
    except KitError as e:
        print(f"manual-kit: {e}", file=sys.stderr)
        sys.exit(1)
