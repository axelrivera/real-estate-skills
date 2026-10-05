"""Build the manual smoke-test kit in out/manual-test/ (dev only, never shipped).

    .venv/bin/python dev/manual_kit/build.py        # or: make manual-kit

Makes every file a tester uploads (mock MLS 360 reports, a listing flyer, CMA exports, seller notes, a buyer CMA
handoff, FAR/BAR contract packages and an other-state agreement), one folder per case with the prompt to paste, and
an expected.md per case whose numbers come from running the skills' own scripts at build time.

The kit is black box: a tester uploads files, pastes prompts and reads the PDFs, calendar files and chat replies, never
a data file or anything in between. Checks (CHECKS) are of three kinds: yes/no behaviors, consistency within one run
(the report against its own reply, a later case against the earlier case's report in the same chat), and fixed numbers
only where the inputs fully determine them (the timelines, the net sheet, the offer review's math on the package).
Where Claude's judgment sets a number (comp picks, the value range), expected.md gives a sanity band or a reference
run, labeled as such, never a number to match. The mock data is in
data.json (a real city, Casselberry in Seminole County; every street, name, brokerage and MLS number is made up).
See docs/manual-testing.md.

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
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "out", "manual-test")
WORK = os.path.join(ROOT, "out", "manual-kit-work")
PY = sys.executable
CSV_HEADER = ["Distance", "ML Number", "Status", "Address", "Legal Subdivision Name", "Heated Area", "Current Price",
              "Close Price", "Close Date", "Original List Price", "Contract Date", "Beds", "Full Baths", "Year Built",
              "Pool", "CDOM", "Seller Paid Buyer Costs", "Lot Size Acres", "Sold Terms", "Public Remarks"]
STARTERS = ["asis-offer-aga", "asis-fha-executed", "asis-short-sale-rent-back"]

D = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
TODAY = D["today"]
esc = html.escape


class KitError(RuntimeError):
    pass


# --- helpers -------------------------------------------------------------------

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


def pct(v, digits=1):
    return f"{v * 100:.{digits}f}%" if v is not None else "none"


def band(low, high, margin=0.03):
    """The sanity band around a script's adjusted-comp span, rounded outward to $1,000."""
    return f"{money(int(low * (1 - margin)) // 1000 * 1000)} to {money(-(-int(high * (1 + margin)) // 1000) * 1000)}"


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


def prompt_md(case, uploads, steps, today=TODAY, note=None):
    """prompt.md: what to upload and the prompts to paste, in order."""
    lines = [f"# {case}", ""]
    lines += ["## Upload", ""] + ([f"- `{u}`" for u in uploads] if uploads else ["Nothing."]) + [""]
    lines += ["## Prompts", ""]
    for i, s in enumerate(steps, 1):
        lines += [f"**{s.get('title', f'Step {i}')}**", ""]
        if s.get("upload"):
            lines += ["Upload first: " + ", ".join(f"`{u}`" for u in s["upload"]), ""]
        lines += ["```text", s["text"], "```", ""]
    if note:
        lines += [note, ""]
    if any("Today is" in s["text"] for s in steps):
        lines += [f"Date assumed: {long_date(today)}. Keep the \"Today is\" sentence in the prompt so dates line up with "
                  "expected.md."]
    else:  # a follow-up in an earlier case's chat: that prompt set the date
        lines += [f"Date assumed: {long_date(today)}, set by the earlier prompt in this chat."]
    return "\n".join(lines)


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


def loan_officer(pdf_path):
    """The loan officer who signs the package's pre-approval letter, or None."""
    m = re.search(r"(\S+ \S+)\s*\n\s*Senior Loan Officer", pdf_text(pdf_path))
    return m.group(1) if m else None


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


def timeline_md(t):
    def name(r):  # the star as the PDF shows it: critical and not done
        return r["label"] + (" ★" if r["critical"] and not r["done"] else "")

    rows = [[name(r), r["display"], r["party"], ("Done " + r["done_display"][5:]) if r["done"] else "",
             r["rule"]] for r in t["rows"]]
    out = [table(["Deadline", "When", "Who", "Status", "Rule"], rows), "", "★ = critical, as the PDF stars it."]
    if t["pending"]:
        out += ["", "Not dated yet (wait on an event):", "",
                table(["Deadline", "Rule"], [[name(r), r["rule"]] for r in t["pending"]])]
    return "\n".join(out)


# --- cases -----------------------------------------------------------------------------

def case_profile(checks):
    d = os.path.join(OUT, "01-agent-profile")
    write(os.path.join(d, "prompt.md"), prompt_md("Case 1: Agent Profile", [], [
        {"title": "Prompt", "text": "Set up my profile."}],
        note="Answer the questions with your own real details (name, brokerage, license, phone, email, brand colors "
             "or a logo). Nothing in this kit is used here; later cases use the profile this case saves."))
    write(os.path.join(d, "expected.md"), "\n".join([
        "# Case 1: Expected", "",
        "Nothing is computed for this case: the profile is your own.", "",
        "- **Cowork:** the skill asks for what it needs in at most two rounds, then saves `profile.md` "
        "in the working folder. Open it: your details, your colors, no placeholders like `[Your Name]` and nothing "
        "made up (no invented license number or slogan).",
        "- **claude.ai:** there is no working folder, so the profile is handed over in chat (or as a file to keep) and "
        "the reply says to upload it next time.", "",
        "## Checks", ""] + [f"- {c}" for c in checks]))


def case_seller_cma(pdf, checks):
    h = D["seller_home"]
    d = os.path.join(OUT, "02-seller-cma")
    os.makedirs(d, exist_ok=True)
    export = os.path.join(d, h["export_file"])
    write_csv(export, h["rows"])
    pdf.render(report_360_html(h["report_360"]), os.path.join(d, h["report_file"]), "360 Property View")
    write(os.path.join(d, h["notes_file"]), "\n".join(h["notes"]))

    cmd = ["skills/seller-cma/scripts/stats.py", rel(export), "--address", h["mls_address"], "--sqft", str(h["sqft"]),
           "--subdivision", h["subdivision"], "--state", h["state"], "--county", h["county"],
           "--split-date", h["split_date"], "--as-of", TODAY] + (["--pool"] if h["pool"] else [])  # CMA-330
    stats = run(cmd)
    if not stats.get("ok"):
        raise KitError(f"seller stats.py: {stats}")
    if stats["subject_rows"]:
        raise KitError("The seller's home has rows in the export: the skill would stop to ask whose listing it is.")

    # A reference compute run with the kit's own comp picks: the net-sheet lines and rates are deterministic
    ref = h["reference"]
    base = json.load(open(os.path.join(ROOT, "dev", "samples", "seller-cma.json"), encoding="utf-8"))
    for k in ("sample", "deck"):
        base.pop(k, None)
    base.update({
        "prepared_date": long_date(TODAY), "as_of": TODAY, "export": os.path.abspath(export), "split_date": h["split_date"],
        "subject": {**base["subject"], "address": h["address"], "mls_address": h["mls_address"], "city": h["city"],
                    "state": h["state"], "county": h["county"], "sqft": h["sqft"], "beds": h["beds"], "baths": h["baths"],
                    "year_built": h["year_built"], "pool": h["pool"], "hoa": h["hoa"], "subdivision": h["subdivision"],
                    "locality": f"{h['city']}, {h['state']} {h['zip']} · Tanager Ridge · {h['county']} County"},
        "recommendation": {**base["recommendation"], **ref["recommendation"]},
        "costs": ref["costs"], "buyer_payment": ref["buyer_payment"],
    })
    base["comps"]["cards"] = [{**c, "meta": "", "bullets": ["Reference comp."]} for c in ref["comps"]]
    base["pricing"]["strategies"] = ref["strategies"]
    base["pricing"]["recommended_index"] = 1
    base["scatter"]["callouts"] = []
    work = os.path.join(WORK, "seller-cma")
    dump(os.path.join(work, "report.json"), base)
    comp = run(["skills/seller-cma/scripts/compute.py", rel(os.path.join(work, "report.json"))])
    if not comp.get("ok"):
        raise KitError(f"seller compute.py: {comp}")

    r360 = h["report_360"]
    expired = r360["history"][1]
    net = comp["net"]
    lines = [
        "# Case 2: Expected", "",
        f"Date assumed: {long_date(TODAY)} (say \"Today is {long_date(TODAY)}\" in the prompt).", "",
        "## The Home Is Not Listed Now", "",
        f"- The 360 report's status line is **{r360['header']['status']}** ({r360['header']['pairs'][0][1]}): the "
        "2019 purchase. The home is off the market today.",
        f"- The export has **no row** for {h['mls_address']}: the skill must not stop to ask whose listing it is.",
        f"- **Old failed listing to flag:** MLS# {expired['mls']}, listed {expired['rows'][-1][0]} at "
        f"{expired['rows'][-1][3]}, cut to {expired['rows'][1][3]} on {expired['rows'][1][0]}, **expired "
        f"{expired['rows'][0][0]} after {expired['rows'][0][4]} days**.", "",
        "## Facts the Report Should Use", "",
        f"- County record (Tax tab): {h['beds']} beds, {h['baths']} baths, {h['sqft']:,} sq ft heated, built "
        f"{h['year_built']}, lot 0.24 acre (the MLS says 0.23), block and stucco, no pool, 2-car garage, flood zone X, "
        "no HOA.",
        "- Current tax bill: $3,505.61 (2025, homestead). Tax Area C1: City of Casselberry millage.",
        "- Updates come from the seller notes (roof 2021, AC 2023, floors 2022, kitchen 2024), not the 2019 remarks.",
        "- Never in a client file: owner and buyer names, mortgage history, Realtor Remarks, the AVM.", "",
        "## Market Numbers (stats.py)", "",
        "Command, exactly as SKILL.md shows it:", "",
        "```text", "python3 scripts/stats.py " + " ".join(
            f'"{a}"' if " " in a else a for a in [h["export_file"]] + cmd[2:]), "```", "",
        f"Split date {h['split_date']}. Claude may pick another split date; then only the whole-window numbers "
        "below must match.", "",
        table(["Measure", "Whole Window", "Before Split", "Since Split"], [
            ["Homes Sold", stats["sold_all"]["n"], stats["sold_early"]["n"], stats["sold_recent"]["n"]],
            ["Median Sale Price", money(stats["sold_all"]["median_price"]), money(stats["sold_early"]["median_price"]),
             money(stats["sold_recent"]["median_price"])],
            ["Median $ / Sq Ft", stats["sold_all"]["median_ppsf"], stats["sold_early"]["median_ppsf"],
             stats["sold_recent"]["median_ppsf"]],
            ["Sale vs. Original List", pct(stats["sold_all"]["median_sale_to_original_list"]),
             pct(stats["sold_early"]["median_sale_to_original_list"]),
             pct(stats["sold_recent"]["median_sale_to_original_list"])],
            ["Median Days on Market", stats["sold_all"]["median_days_on_market"],
             stats["sold_early"]["median_days_on_market"], stats["sold_recent"]["median_days_on_market"]],
            ["Share with Seller-Paid Costs", pct(stats["sold_all"]["share_with_seller_paid_costs"], 0),
             pct(stats["sold_early"]["share_with_seller_paid_costs"], 0),
             pct(stats["sold_recent"]["share_with_seller_paid_costs"], 0)],
        ]), "",
        f"- Status counts: {', '.join(f'{k.title()} {v}' for k, v in stats['status_counts'].items())}.",
        f"- Active listings: {stats['active_count']} ({pct(stats['active_share_with_price_cut'], 0)} with a price cut); "
        f"months of supply at the recent pace: {stats['months_supply_at_recent_pace']}.",
        f"- Top comp candidates: {', '.join(c['address'].title() for c in stats['sold_candidates'][:6])}.", "",
        "## Value and Price (Judgment)", "",
        "The range and list price are Claude's judgment: check they're sensible, not exact. As a sanity band, a "
        "reference compute.py run with five comps picked from the list above adjusted to "
        f"**{money(comp['adjusted_min'])} to {money(comp['adjusted_max'])}** (median {comp['median_adjusted_display']}). "
        f"A recommended list price outside about {band(comp['adjusted_min'], comp['adjusted_max'])} (that span "
        "plus or minus 3%) needs a stated reason.", "",
        "## Net Sheet Lines (compute.py)", "",
        "The labels and rates below are fixed; the dollar amounts depend on the prices Claude picks. Reference run at "
        "the kit's three prices (payoff $171,500, closing December 18, 2026):", "",
        table(["Line"] + [s["label"] for s in comp["strategies"]],
              [[r["label"]] + r["display"] for r in net["rows"]]), "",
        "- The brokerage lines show the default rates with no Assumed label (2.5% listing, 2.5% buyer's agent): a default, "
        "not an assumption. Estimates are named once, in the notes. compute.py's assumptions (the reply asks):",
    ]
    lines += [f"  - {a}" for a in comp["assumptions"]] or ["  - none"]
    pay = comp["payments"]
    lines += ["", f"- Buyer payment basis: {pay['tax_basis']}; at the reference 6.5% rate, conventional 5% down: " +
              "; ".join(f"{r['list_price_display']} → {r['payment_display']}/mo" for r in pay["rows"]) +
              ". The rate Claude finds online will differ.", "",
              "## Checks", ""] + [f"- {c}" for c in checks]
    write(os.path.join(d, "expected.md"), "\n".join(lines))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 2: Seller CMA", [h["report_file"], h["export_file"], h["notes_file"]], [
        {"title": "Step 1 (new session)", "text":
            f"Today is {long_date(TODAY)}. I have a listing appointment for {h['address']} in {h['city']}. Attached are "
            "the MLS 360 property report, my CMA export and my notes from the call with the sellers. What should we list "
            "at? I need the seller CMA report."},
        {"title": "Step 2", "text": "Now build the listing presentation for the appointment."},
        {"title": "Step 3", "text": "On the first slide, add that the home is perfect for young families."},
    ]))
    return stats, comp


def history_events(h):
    """The 360 report's history grid as buyer-cma `events` (report-data.md), newest first, as the grid lists it."""
    change = {"->ACT": "listed", "ACT->PND": "pending", "PND->SLD": "sold"}
    out = []
    for block in h["report_360"]["history"]:
        for date_, kind, move, price, dom in block["rows"]:
            m, d_, y = date_.split("/")
            out.append({"date": f"{y}-{m}-{d_}", "mls": block["mls"],
                        "change": "price" if kind == "Price Change" else change[move],
                        "price": int(price.replace("$", "").replace(",", "")), "dom": int(dom)})
    return out


def case_buyer_cma(pdf, checks):
    h = D["buyer_home"]
    d = os.path.join(OUT, "03-buyer-cma")
    os.makedirs(d, exist_ok=True)
    export = os.path.join(d, h["export_file"])
    write_csv(export, h["rows"])
    pdf.render(report_360_html(h["report_360"]), os.path.join(d, h["report_file"]), "360 Property View")
    pdf.render(flyer_html(h), os.path.join(d, h["flyer_file"]), "Listing Flyer")

    cmd = ["skills/buyer-cma/scripts/stats.py", rel(export), "--address", h["mls_address"], "--state", h["state"],
           "--county", h["county"], "--mls-number", h["mls"], "--split-date", h["split_date"],
           "--as-of", TODAY]  # CMA-330: as the skill runs it (SKILL.md step 2), so months of supply runs to today
    stats = run(cmd)
    if not stats.get("ok") or not stats.get("subject_row"):
        raise KitError(f"buyer stats.py didn't find the subject row: {stats.get('problems') or stats.get('market_notes')}")

    ref = h["reference"]
    base = json.load(open(os.path.join(ROOT, "dev", "samples", "buyer-cma.json"), encoding="utf-8"))
    base.pop("sample", None)
    base.update({"prepared_date": long_date(TODAY), "as_of": TODAY, "export": os.path.abspath(export),
                 "split_date": h["split_date"]})
    base["subject"].update({
        "address": h["address"], "mls_address": h["mls_address"], "city": h["city"], "state": h["state"],
        "county": h["county"], "list_price": h["list_price"], "sqft": h["sqft"], "beds": h["beds"], "baths": h["baths"],
        "year_built": h["year_built"], "pool": h["pool"], "subdivision": h["subdivision"], "property_type": "single_family",
        "locality": f"{h['city']}, {h['state']} {h['zip']} · Kestrel Point · {h['county']} County · MLS {h['mls']}"})
    base["bottom_line"].update(ref["bottom_line"])
    base["offer_plan"].update(ref["offer_plan"])
    base["comps"]["cards"] = [{**c, "meta": "", "bullets": ["Reference comp."]} for c in ref["comps"]]
    base["scatter"]["callouts"] = []
    base["history"] = {"heading": "Price History", "intro": "The full history:", "after": "", "events": history_events(h)}
    base["costs"]["taxes"].update(ref["taxes"])
    base["costs"]["taxes"].pop("purchase_price", None)  # CMA-315: the skill's default, taxes at the payment's price
    base["costs"]["payment"].update({**ref["payment"], "tax_jurisdiction_index": 0})
    base["costs"]["payment"].pop("price", None)  # the payment at the plan's target, as the skill figures it
    base["costs"]["credit_scenarios"].update(ref["credit_scenarios"])
    base["costs"]["credit_scenarios"].pop("buydown", None)
    work = os.path.join(WORK, "buyer-cma")
    dump(os.path.join(work, "report.json"), base)
    comp = run(["skills/buyer-cma/scripts/compute.py", rel(os.path.join(work, "report.json"))])
    if not comp.get("ok"):
        raise KitError(f"buyer compute.py: {comp}")
    if comp.get("warnings"):
        print("  buyer compute warnings:", comp["warnings"])

    row = stats["subject_row"]
    hist = h["report_360"]["history"][0]["rows"]
    adj = [c["adjusted"] for c in comp["handoff"]["comps"]]
    lines = [
        "# Case 3: Expected", "",
        f"Date assumed: {long_date(TODAY)} (say \"Today is {long_date(TODAY)}\" in the prompt).", "",
        "## The Listing", "",
        f"- Active at **{money(h['list_price'])}**, MLS# {h['mls']}, {row['days_on_market']:.0f} days on market "
        f"(listed {hist[-1][0]} at {hist[-1][3]}).",
        f"- **Two price cuts:** {hist[1][0]} to {hist[1][3]}, then {hist[0][0]} to {hist[0][3]}. Earlier sale: "
        "$262,000 in May 2015.",
        f"- **Counted by compute.py:** {comp['history']['price_cuts']} price cuts, {comp['history']['price_increases']} "
        f"increases, {money(comp['history']['price_cut_total'])} cut in all, {comp['history']['active_days']} active "
        "days (the 2015 listing that sold is in the history table but not in the counts). The report and reply must "
        "use these counts, never a hand count.",
        f"- Facts: {h['beds']} beds, {h['baths']} baths, {h['sqft']:,} sq ft, built {h['year_built']}, screened pool, "
        "lot 0.27 acre, HOA $420 a year, flood zone X, roof 2010 (a watch item: insurers ask about roofs this age).",
        "- Tax: 2025 bill $4,095.13 with the seller's homestead. Tax Area C1 (City of Casselberry). The buyer's bill "
        "resets at the purchase price.", "",
        "## Market Numbers (stats.py)", "",
        "```text", "python3 scripts/stats.py " + " ".join(
            f'"{a}"' if " " in a else a for a in [h["export_file"]] + cmd[2:]), "```", "",
        table(["Measure", "Whole Window", "Before Split", "Since Split"], [
            ["Homes Sold", stats["sold_all"]["n"], stats["sold_early"]["n"], stats["sold_recent"]["n"]],
            ["Median Sale Price", money(stats["sold_all"]["median_price"]), money(stats["sold_early"]["median_price"]),
             money(stats["sold_recent"]["median_price"])],
            ["Sale vs. Original List", pct(stats["sold_all"]["median_sale_to_original_list"]),
             pct(stats["sold_early"]["median_sale_to_original_list"]),
             pct(stats["sold_recent"]["median_sale_to_original_list"])],
            ["Median Days on Market", stats["sold_all"]["median_days_on_market"],
             stats["sold_early"]["median_days_on_market"], stats["sold_recent"]["median_days_on_market"]],
        ]), "",
        f"- Status counts: {', '.join(f'{k.title()} {v}' for k, v in stats['status_counts'].items())} (the subject is "
        "one of the actives).",
        f"- Other actives: {stats['active_count']}; months of supply at the recent pace: "
        f"{stats['months_supply_at_recent_pace']}.",
        f"- Top comp candidates: {', '.join(c['address'].title() for c in stats['sold_candidates'][:6])}.", "",
        "## Value and Offer (Judgment)", "",
        f"Range and offer plan are Claude's judgment. Sanity band from a reference compute.py run with five comps "
        f"from the list above: adjusted **{money(min(adj))} to {money(max(adj))}** (median "
        f"{comp['median_adjusted_display']}). The asking price should read as at or above the top of the supported "
        "range (the reference run puts it " + comp["range"]["asking_position"] + "), and the opening offer and "
        f"walk-away should sit inside about {band(min(adj), max(adj))} (that span plus or minus 3%).",
        "",
        "## Taxes at the Target Price (compute.py)", "",
        f"Fixed by the built-in 2025 Casselberry millage and the new owner's homestead, at the reference plan's target "
        f"({comp['payments']['price_display']}). The skill figures taxes at the payment's price, the target, so with "
        "Claude's own plan the dollars move with its target; the report's tax table names that price:", "",
        table(["Jurisdiction", "Basis", "A Year", "A Month"],
              [[t["label"], t["basis"], t["annual_display"], t["monthly_display"]] for t in comp["taxes"]]), "",
        f"The listing shows the seller's {comp['current_bill_display']} bill; the report must say the buyer's bill "
        "resets at the purchase price.", "",
    ]
    lines += ["Payments use the rate Claude finds online, so only the tax lines are fixed.", "",
              "## Checks", ""] + [f"- {c}" for c in checks]
    write(os.path.join(d, "expected.md"), "\n".join(lines))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 3: Buyer CMA", [h["flyer_file"], h["report_file"], h["export_file"]], [
        {"title": "Prompt", "text":
            f"Today is {long_date(TODAY)}. My buyer is looking at {h['address']} in {h['city']}. Here are the listing "
            "flyer, the MLS 360 property report and my CMA export. Is it priced right and what should we offer? I need "
            "the buyer CMA PDF."}],
        note="Keep this chat open: case 4 continues in it."))
    return stats, comp


def case_offer_strategy(comp, checks):
    h = D["buyer_home"]
    lim = D["buyer_limits"]
    d = os.path.join(OUT, "04-buyer-offer-strategy")
    os.makedirs(d, exist_ok=True)
    work = os.path.join(WORK, "offer-strategy")
    os.makedirs(work, exist_ok=True)
    # nothing to upload: the case runs in the case 3 chat, where the buyer CMA (and its handoff) already is; the kit
    # keeps a copy in its work folder only to compute expected.md
    handoff_src = comp["handoff_file"]
    handoff_name = os.path.basename(handoff_src)
    shutil.copy(handoff_src, os.path.join(work, handoff_name))
    run(["-c", "import sys, json; sys.path.insert(0, 'shared'); import handoff; "
         f"handoff.load({json.dumps(os.path.join(work, handoff_name))}); print(json.dumps({{'ok': True}}))"])

    buyer = {"analysis_date": TODAY,
             "property": {"address": f"{h['address']}, {h['city']}, {h['state']} {h['zip']}", "state": h["state"],
                          "county": h["county"], "list_price": h["list_price"]},
             "competition": lim["competition"], "costs": lim["costs"], "buyer": lim["buyer"],
             "worksheet": lim["worksheet"], "chosen_option": "recommended", "overrides": {}}
    dump(os.path.join(work, "buyer.json"), buyer)
    out = run(["skills/buyer-offer-strategy/scripts/strategy.py", rel(os.path.join(work, "buyer.json")),
               "--cma", rel(os.path.join(work, handoff_name))])
    if not out.get("ok", True):
        raise KitError(f"strategy.py: {out}")
    dump(os.path.join(work, "strategy-output.json"), out)
    lines = ["# Case 4: Expected", "",
             f"Date assumed: {long_date(TODAY)}. Run in the same chat as case 3: the buyer CMA from that chat is the input "
             "(nothing uploaded).", "",
             "## What to Check (Against the Case 3 Report)", "",
             "The offer builds on the value range Claude chose in case 3, so its numbers move with that range. Check them "
             "against the case 3 PDF and the buyer's limits, not against the reference run below:", "",
             "- The Offer Options report shows the same value range and comps median as the case 3 buyer CMA.",
             "- The recommended price sits inside that value range and at or below the case 3 walk-away.",
             f"- Worst-case cash is at most {money(lim['buyer']['cash_available'])}, the reserve left is at least "
             f"{money(lim['buyer']['reserve_floor'])}, the payment is at most {money(lim['buyer']['max_payment'])} a month, "
             f"and the price is at most {money(lim['buyer']['max_price'])}.",
             "- The reply, the Offer Options PDF and the worksheet give the same price, deposit, concessions and dates.", ""]
    lines += strategy_summary(out, lim, [
        "## Reference Run (Will Differ With the Case 3 Range)", "",
        "For orientation only: the offer the kit's own case 3 reference (its comp picks, not Claude's) leads to. Expect "
        "different prices and dollars in your run; the terms' shape (riders, periods, the worksheet's entries) should "
        "look alike.", ""])
    lines += ["", "## Checks", ""] + [f"- {c}" for c in checks]
    write(os.path.join(d, "expected.md"), "\n".join(lines))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 4: Buyer Offer Strategy", [], [
        {"title": "Prompt (in the case 3 chat)", "text":
            f"Now help me write the offer on {h['address']}. My buyer: {lim['prompt']} I need the offer options "
            "report and the offer package worksheet."}],
        note="Run this in the same chat as case 3, right after the buyer CMA: don't start a new chat and don't upload "
             "anything. The skill should use the CMA it just built; if it asks for a CMA file, note that as a failure. "
             "If it asks for anything else, answer from the prompt or say you don't know."))
    return out


def strategy_summary(out, lim, reference_intro=()):
    """Page-1 facts from strategy.py's output: the recommended terms, the options, cash exposure and riders, after the
    buyer's limits and `reference_intro` (the heading that marks the rest as a reference run)."""
    s, ws = out["summary"], out["worksheet"]
    lines = ["## Buyer Limits (from the prompt)", "",
             table(["Limit", "Value"], [["Max Price", money(lim["buyer"]["max_price"])],
                                        ["Cash Available", money(lim["buyer"]["cash_available"])],
                                        ["Reserve Floor", money(lim["buyer"]["reserve_floor"])],
                                        ["Max Payment", money(lim["buyer"]["max_payment"]) + " a month"],
                                        ["Loan", "Conventional, 5% down, 6.5%, first-time buyer"]]), "",
             *reference_intro,
             f"## Reference Recommended Offer: {s['outlook']}, Strength {s['strength']}/100", "",
             f"Reference value range (the kit's case 3 picks): {out['value_range']}. Competition: {s['competition']}.", "",
             table(["Term", "Offer", "Why"], [[t["term"], t["offer"].replace("**", ""), t["why"]] for t in s["terms"]]), "",
             table(["Cash and Payment", "Amount"], [[a, b] for a, b in s["exposure"]]), ""]
    notes = list(s.get("constraints") or []) + [x["text"] for x in out.get("reply_lines") or []
                                               if x["text"] not in (s.get("constraints") or [])]
    if notes:  # OFR-332 and the like: on page 1 and in the reply (the numbers in them move with the range)
        lines += ["The reference run's page 1 and reply carry these lines (yours read alike, with your run's numbers):",
                  ""] + [f"- {n}" for n in notes] + [""]
    lines += ["## Reference Options", "",
             table(["Option", "Price", "Outlook", "Seller Net", "Worst-Case Cash", "Reserve", "What Changes"],
                   [[o["option"], o["price"], o["outlook"], o["seller_net"], o["worst_cash"], o["reserve"], o["what"]]
                    for o in s["options"]]), "",
             "## Reference Outlook by Competition Level", "",
             table(["Level"] + s["option_labels"], [[b["level"]] + [v["band"] for v in b["values"]] for b in s["bands"]]),
             "", f"## Worksheet: {ws['form_name']}", "",
             "Riders, by name and CR-7 letter:", ""]
    lines += [f"- {r['rider']}: {r['inputs'].replace('**', '')}" for r in ws["riders"]]
    lines += ["", "The worksheet must not show the buyer's max price, cash or reserve.", "",
              "## Assumptions the Reply Should List", ""] + [f"- {a['what']}" for a in out["assumptions"]]
    return lines


def case_offer_review(checks):
    o = D["offer_review"]
    d = os.path.join(OUT, "05-seller-offer-review")
    aga_dir, aga_key, aga_pdfs = build_package(f"dev/mock_contracts/scenarios/{o['starter']}.json", o["starter"])
    offer_pdf = next(p for p in aga_pdfs if p.endswith("-Offer.pdf"))
    spec, same = second_offer_spec(aga_dir, offer_pdf, aga_key)
    b_dir, b_key, b_pdfs = build_package(rel(spec), "manual-kit-sable-palm-second-offer")
    side = listing_side(aga_key)
    if listing_side(b_key) != side:
        raise KitError("The two offer packages name different listing brokerages.")
    a_agent, b_agent = aga_key["offers"][0]["buyer_agent"], b_key["offers"][0]["buyer_agent"]
    if a_agent.split()[-1][:5] == b_agent.split()[-1][:5]:
        raise KitError(f"The buyer's agents' surnames read alike ({a_agent}, {b_agent}): rename one in the scenario.")
    # Both packages are for the same street, so the buyer's surname keeps the second upload from replacing the first
    for src_dir, pdfs, key, step in ((aga_dir, aga_pdfs, aga_key, "step-1"), (b_dir, b_pdfs, b_key, "step-2")):
        buyer = key["offers"][0]["buyer"].split()[-1]
        os.makedirs(os.path.join(d, step), exist_ok=True)
        for p in pdfs:
            shutil.copy(os.path.join(src_dir, p), os.path.join(d, step, p.replace(".pdf", f"-{buyer}.pdf")))
    if b_key["listing"]["address"] != aga_key["listing"]["address"]:
        raise KitError("The second offer isn't on the same listing.")
    if b_key["listing"].get("hoa_monthly") != aga_key["listing"].get("hoa_monthly"):  # OFR-345
        raise KitError("The two offer packages show different HOA fees.")

    single = {k: v for k, v in aga_key.items() if k != "mock"}
    single["analysis_date"] = o["today"]
    single["listing"]["list_price"] = o["list_price"]
    for offer, src_dir, pdfs in ((single["offers"][0], aga_dir, aga_pdfs), (b_key["offers"][0], b_dir, b_pdfs)):
        officer = loan_officer(os.path.join(src_dir, next(p for p in pdfs if p.endswith("-Offer.pdf"))))
        if officer:  # the pre-approval letter names the loan officer, so the review never asks who it is
            offer["loan_officer"] = officer
    multi = json.loads(json.dumps(single))
    second = dict(b_key["offers"][0], id="B")
    multi["offers"].append(second)
    nmob = (json.load(open(spec, encoding="utf-8")).get("disclosures") or {}).get("NMOB") or {}
    if nmob.get("deadline"):  # the second package's Notice of Multiple Offers: highest and best is already called
        multi["listing"]["highest_and_best_due"] = nmob["deadline"]
    work = os.path.join(WORK, "offer-review")
    dump(os.path.join(work, "listing-single.json"), single)
    dump(os.path.join(work, "listing-multi.json"), multi)
    r1 = run(["skills/seller-offer-review/scripts/review.py", rel(os.path.join(work, "listing-single.json"))])
    r2 = run(["skills/seller-offer-review/scripts/review.py", rel(os.path.join(work, "listing-multi.json"))])
    for r in (r1, r2):
        if not r.get("ok"):
            raise KitError(f"review.py: {r}")

    s1, s2 = r1["summary"], r2["summary"]
    a, b = aga_key["offers"][0], b_key["offers"][0]
    lines = ["# Case 5: Expected", "",
             f"Date assumed: {long_date(o['today'])} (say \"Today is {long_date(o['today'])}\"). The offers arrived "
             f"{a['received']} and {b['received']}; the first expires {a['expires']}.", "",
             "Numbers below come from review.py run on the mock packages' answer keys (the listing files the skill "
             "should build from the PDFs), with no payoff, CMA or brokerage terms given.", "",
             "## The Offers", "",
             table(["", "Offer 1 (Step 1)", "Offer 2 (Step 2)"], [
                 ["Buyer", a["buyer"], b["buyer"]],
                 ["Buyer's Agent", f"{a['buyer_agent']}, {a['buyer_brokerage']}", f"{b['buyer_agent']}, {b['buyer_brokerage']}"],
                 ["Price", money(a["price"]), money(b["price"])],
                 ["Financing", f"Conventional, {a['down_pct']:.0%} down", f"Conventional, {b['down_pct']:.0%} down"],
                 ["Deposit", money(a["deposit"]), money(b["deposit"])],
                 ["Closing", a["closing_date"], b["closing_date"]],
                 ["Special Terms", f"Appraisal Gap Addendum (AGA-1), {money(a['appraisal_gap'])} gap",
                  f"Escalation Addendum (EAC-1): {money(b['escalation']['increment'])} over competing offers, cap "
                  f"{money(b['escalation']['cap'])}"],
                 ["Riders", ", ".join(a["riders"]), ", ".join(b["riders"])]]), "",
             f"Both packages carry the same parcel ({same['tax_id']}), HOA rider contact ({same['hoa_contact']}) and HOA "
             f"fee ({same['hoa']}).", "",
             f"Both packages name {side[0]} ({side[1]}) as the listing side, not your brokerage: a flag asking you to "
             "confirm the listing side is expected (the kit can't know your profile). It's a confirmation, not an error.", "",
             "## Step 1: Single Offer (review.py)", "",
             f"- Action: **{s1['action']}**. {s1['why']}",
             f"- Respond by {s1['respond_by']}.",
             ] + [f"- {k['label']}: {k['value']}" + (f" ({k['note']})" if k.get("note") else "") for k in s1["kpis"]] + [
             f"- Counter: " + "; ".join(f"{c['term']} {c['offered']} → {c['counter']}" for c in s1["counter"]["rows"]),
             f"- Certainty: {s1['certainty']['score']}/100 ({s1['certainty']['band']}); walk-away until "
             f"{s1['certainty']['walk_away_until']}. {s1['certainty'].get('walk_away_note', '')}",
             "", "## Step 2: Both Offers (review.py)", "",
             f"- Action: **{s2['action']}**. {s2['why']}", f"- {s2.get('plan_summary', '')}",
             f"- Respond by {s2['respond_by']} ({s2['respond_by_offer']})"
             + "".join(f"; also {a['when']} ({a['what']})" for a in s2.get("respond_by_also") or ()) + ".",
             f"- Next step: {s2['next_step']}", "",
             table(["Rank", "Offer", "Price", "Net", "Downside", "Score", "Close", "Action", "Terms / Reason"],
                   [[x["rank"], x["offer"], x["price"], x["net"], x["downside"], x["score"], x["close"], x["action"],
                     x["terms"]] for x in s2["ranked"]]), "",
             "- Flags on the escalation offer: " + "; ".join(next(x for x in r2["offers"] if x["id"] == "B")["flags"]), "",
             "## Assumptions review.py lists (both steps)", ""] + [f"- {x['what']}" for x in r1["assumptions"]] + [
             "", "## Checks", ""] + [f"- {c}" for c in checks]
    write(os.path.join(d, "expected.md"), "\n".join(lines))
    up1 = sorted(os.listdir(os.path.join(d, "step-1")))
    up2 = sorted(os.listdir(os.path.join(d, "step-2")))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 5: Seller Offer Review", [f"step-1/{p}" for p in up1] +
                                                  [f"step-2/{p}" for p in up2], [
        {"title": "Step 1", "upload": [f"step-1/{p}" for p in up1], "text":
            f"Today is {long_date(o['today'])}. I'm the listing agent for {aga_key['listing']['address']}, listed at "
            f"{money(o['list_price'])}. We got this offer. Should my seller accept, and what should we counter?"},
        {"title": "Step 2 (same conversation)", "upload": [f"step-2/{p}" for p in up2], "text":
            "A second offer just came in on the same listing. Compare both offers, rank them and give me a plan. "
            "I'd like the PDF for my seller."}], today=o["today"]))
    return r1, r2


def case_timeline(folder, starter, title, prompt, checks):
    d = os.path.join(OUT, folder)
    src, key, pdfs = build_package(f"dev/mock_contracts/scenarios/{starter}.json", starter)
    os.makedirs(d, exist_ok=True)
    for p in pdfs:
        shutil.copy(os.path.join(src, p), os.path.join(d, p))
    deal = deal_from_key(key, TODAY)
    work = os.path.join(WORK, folder)
    dump(os.path.join(work, "deal.json"), deal)
    t = run(["skills/contract-timeline/scripts/timeline.py", rel(os.path.join(work, "deal.json"))])
    if not t.get("ok"):
        raise KitError(f"timeline.py {starter}: {t}")
    c = key["contract"]
    lines = [f"# {title}: Expected", "",
             f"Date assumed: {long_date(TODAY)}. Side: {key['side']} ({key['client']}). Every date below comes from "
             "contract-timeline's timeline.py run on the package's answer key.", "",
             f"- Property: {c['property']}; price {money(c['price'])}; {c['financing'].upper()}; riders: "
             f"{', '.join(c['riders'])}.",
             f"- Effective Date: **{t['effective']['display']}** ({t['effective']['source']}).",
             f"- Closing: **{t['closing']['display']}**" if t["closing"] else
             "- Closing: **no date yet** (it runs from the short sale approval).",
             f"- First deadline for the {t['side']}: {t['first_deadline']['label']}, {t['first_deadline']['display']}."
             if t["first_deadline"] else "",
             ]
    if t.get("contingencies_end"):
        lines += [f"- Contingencies end: {t['contingencies_end']['label']}, {t['contingencies_end']['display']}."]
    if t.get("contingencies_waiting"):
        lines += [f"- Waiting on the approval: {t['contingencies_waiting_text']}."]
    backup = c.get("short_sale_backup")
    if backup:  # Rider G Para. 7, as the package checks it
        lines += [f"- Rider G back-up offers: box **7({backup})** is checked: " + (
            "the seller may accept back-up contracts while this one is pending." if backup == "b" else
            "the seller may not accept back-up offers while this contract is in effect.")]
    if deal["completed"]:
        lines += [f"- Done per the package (escrow receipt, signed compensation agreement): "
                  f"{', '.join(k.replace('_', ' ') for k in deal['completed'])}. The skill may show these as done or "
                  "as due; either is fine if the date is right."]
    lines += ["", "## Deadlines", "", timeline_md(t), ""]
    if t["flags"]:
        lines += ["## Printed Checks", ""] + [f"- {f}" for f in t["flags"]] + [""]
    if t["agent_notes"]:
        lines += ["## Notes for the Agent (chat only)", ""] + [f"- {n}" for n in t["agent_notes"]] + [""]
    lines += ["## Checks", ""] + [f"- {x}" for x in checks]
    write(os.path.join(d, "expected.md"), "\n".join(l for l in lines if l is not None))
    write(os.path.join(d, "prompt.md"), prompt_md(title, pdfs, [{"title": "Prompt", "text": prompt.format(
        today=long_date(TODAY), address=c["property"].split(",")[0], city=c["property"].split(",")[1].strip())}]))
    return t


def case_other_state(pdf, checks):
    a = D["other_state"]
    d = os.path.join(OUT, "08-contract-timeline-other-state")
    os.makedirs(d, exist_ok=True)
    pdf.render(agreement_html(a), os.path.join(d, a["file"]), a["title"])
    deal = {"side": "buyer", "state": a["state"], "county": a["county"], "client": a["buyer"], "report_date": TODAY,
            "rules": a["rules"],
            "contract": {"form_family": "other", "form": a["title"], "property": a["property"], "buyer": a["buyer"],
                         "seller": a["seller"], "price": a["price"], "financing": "conventional",
                         "effective_date": a["effective_date"], "effective_date_source": "Seller's signature, "
                         + a["seller_signed"], "closing_date": a["closing_date"], "closing_time": a["closing_time"],
                         "escrow_agent": a["escrow_agent"]},
            "deadlines": a["deadlines"], "amendments": []}
    work = os.path.join(WORK, "other-state")
    dump(os.path.join(work, "deal.json"), deal)
    t = run(["skills/contract-timeline/scripts/timeline.py", rel(os.path.join(work, "deal.json"))])
    if not t.get("ok"):
        raise KitError(f"timeline.py other state: {t}")
    eff = date.fromisoformat(a["effective_date"])
    plain = [[x["label"], "By Closing" if x["basis"] == "before" and not x["days"] else
              f"{x['days']} day{'s' if x['days'] != 1 else ''} "
              f"{'after the Effective Date' if x['basis'] == 'after' else 'before Closing'}",
              (eff + timedelta(days=x["days"])).strftime("%a %b %-d") if x["basis"] == "after" else
              (date.fromisoformat(a["closing_date"]) - timedelta(days=x["days"])).strftime("%a %b %-d")]
             for x in a["deadlines"]]
    lines = ["# Case 8: Expected", "",
             f"Date assumed: {long_date(TODAY)}. A made-up two-page {a['title']} for a home in Ohio: not any real "
             "state's or association's form, so the skill works from the contract's own dates and time rules "
             "(best effort).", "",
             f"- Effective Date: **{t['effective']['display']}** (the seller's signature, {a['seller_signed']}).",
             f"- Closing: **{t['closing']['display']}**.",
             "- Time rules in Para. 10: calendar days from the day after the Effective Date, ending 11:59 PM; a period "
             "that ends on a Saturday, Sunday or federal holiday moves to the next business day.", "",
             "## Deadlines (timeline.py with the contract's rules)", "", timeline_md(t), "",
             "Plain calendar count before the weekend rule, for reference (the rollover moves the earnest money and "
             "the inspection period to Monday):", "", table(["Deadline", "Period", "Raw Day"], plain), "",
             "## Calendar File", "",
             f"- Closing is the only timed event: {t['closing']['display']}, in Eastern time (Ohio), so a calendar set to "
             "another zone shifts it by the difference.",
             "- The deadlines that end at 11:59 PM, the walk-through and the title commitment (due by Closing) are "
             "all-day items: no event at 11:59 PM and none at the closing's hour besides Closing.", "",
             "## Must Not Happen", "",
             "- No Florida rules, FAR/BAR paragraphs or Florida costs.",
             "- The best-effort disclaimer appears in chat only: not in the PDF, the calendar file or a markdown report.",
             "", "## Checks", ""] + [f"- {c}" for c in checks]
    write(os.path.join(d, "expected.md"), "\n".join(lines))
    write(os.path.join(d, "prompt.md"), prompt_md("Case 8: Contract Timeline (Other State)", [a["file"]], [
        {"title": "Prompt", "text":
            f"Today is {long_date(TODAY)}. Here's my buyer's signed purchase agreement for a home in Westerville, Ohio. "
            "Lay out every deadline for my buyer: I need the PDF timeline and a calendar file."}]))
    return t


# --- checks, README, results ---------------------------------------------------------------

# Each check: (text, where, kind). where: "both" (Cowork and claude.ai), "cowork" or "ai"; cases outside the claude.ai
# pass (1, 2 and 6) are Cowork only. kind (docs/manual-testing.md): "behavior" (yes or no: it did or didn't),
# "consistency" (two things from the same run agree: the PDF and the reply, case 4 and the case 3 report), "fixed"
# (a number the inputs fully determine, in expected.md) or "band" (Claude's judgment, inside expected.md's sanity band).
CHECKS = {
    "01-agent-profile": [("At most two rounds of questions", "both", "behavior"),
                         ("Saves profile.md in the working folder", "cowork", "behavior"),
                         ("Hands the profile over in chat or as a file to keep (no saved file)", "ai", "behavior"),
                         ("No placeholders or made-up details in the profile", "both", "behavior")],
    "02-seller-cma": [("Uses the saved profile without asking for an upload", "cowork", "behavior"),
                      ("Uses the case 1 profile when it's uploaded with the inputs", "ai", "behavior"),
                      ("Report PDF shows the profile's name, brokerage and colors", "both", "behavior"),
                      ("Treats the home as not listed now and flags the 2017 expired listing (price and days)", "both",
                       "behavior"),
                      ("Brokerage shown at the default rates with no Assumed label; estimates named once in the notes", "both",
                       "behavior"),
                      ("Facts and market numbers match expected.md", "both", "fixed"),
                      ("Recommended list price inside the sanity band, or the report says why not", "both", "band"),
                      ("Listing presentation: the PPTX opens and its prices and nets match the PDF", "both", "consistency"),
                      ("\"Perfect for young families\" is declined in one sentence with compliant wording", "both",
                       "behavior")],
    "03-buyer-cma": [("PDF has the value range, the full history (both price cuts and the 2015 listing and sale), and "
                      "the scatterplot", "cowork", "behavior"),
                     ("Facts, price-cut counts and market numbers match expected.md", "cowork", "fixed"),
                     ("The tax table names the price it's figured at, and that price is the offer plan's target", "cowork",
                      "consistency"),
                     ("Opening offer and walk-away sit inside the sanity band", "cowork", "band"),
                     ("The reply's range and offer plan match the PDF", "cowork", "consistency")],
    "04-buyer-offer-strategy": [("Uses the buyer CMA from the case 3 chat without asking for a file", "both", "behavior"),
                                ("Offer Options and Offer Package Worksheet PDFs are both delivered", "cowork", "behavior"),
                                ("Uses the case 3 report's value range and comps median", "cowork", "consistency"),
                                ("Recommended price inside the case 3 value range and at or below its walk-away", "cowork",
                                 "consistency"),
                                ("Worst-case cash at most the cash available, reserve at least the floor, payment at "
                                 "most the limit, price at most the max", "cowork", "consistency"),
                                ("Riders are named by letter (CR-7), and the worksheet shows offer terms only", "cowork",
                                 "behavior")],
    "05-seller-offer-review": [("Step 1: net sheet and a counter for the single offer", "cowork", "behavior"),
                               ("Step 1: the appraisal gap (AGA-1) is read and handled", "cowork", "behavior"),
                               ("Step 2: both offers ranked with a plan (counter one, hold the other as backup)", "cowork",
                                "behavior"),
                               ("Step 2: the backup's earlier time for acceptance is shown, with a step to ask for an "
                                "extension", "cowork", "behavior"),
                               ("Step 2: the highest-and-best deadline (NMOB-1) is shown and not offered again", "cowork",
                                "behavior"),
                               ("No question asks who the loan officer is or whether funds are verified when the "
                                "package's letters show it", "cowork", "behavior"),
                               ("No past dates in next steps", "cowork", "behavior"),
                               ("Nets, counter and ranking match expected.md", "cowork", "fixed")],
    "06-contract-timeline-fha": [("Deadlines match expected.md", "both", "fixed"),
                                 ("ICS imports into a calendar with the correct dates", "both", "behavior"),
                                 ("The FHA appraisal note appears", "both", "behavior"),
                                 ("Compensation Contingency Ends carries no star when the signed agreement shows as "
                                  "done", "both",
                                  "behavior"),
                                 ("Timeline strip: each marker sits on its own date's tick", "both", "behavior"),
                                 ("The PDF, the calendar file and the reply give the same dates", "both", "consistency")],
    "07-contract-timeline-short-sale": [("Two-phase timeline: rows read \"N days after short sale approval\"", "cowork",
                                         "behavior"),
                                        ("PDF builds with no closing date; the strip says it runs to Contract Expires",
                                         "cowork", "behavior"),
                                        ("Short sale dates match expected.md", "cowork", "fixed"),
                                        ("The reply says the seller may accept back-up contracts (Rider G box 7(b))",
                                         "cowork", "fixed")],
    "08-contract-timeline-other-state": [("Timeline uses the contract's own dates and rules; matches expected.md", "cowork",
                                          "fixed"),
                                         ("Calendar: Closing at 1:00 PM Eastern; every other item all-day", "cowork",
                                          "behavior"),
                                         ("Best-effort disclaimer in chat only, not in the PDF or ICS", "cowork",
                                          "behavior"),
                                         ("No Florida rules or forms mentioned", "cowork", "behavior")],
    "09-seller-net-sheet": [("One-page PDF with the profile's name, brokerage and colors", "cowork", "behavior"),
                            ("Nets and lines match expected.md, with no questions before the first sheet", "cowork",
                             "fixed"),
                            ("The notes say the tax bill is assumed unpaid (no label on the line) and the reply says so", "cowork",
                             "behavior"),
                            ("Step 2 answers in chat with the net in expected.md, without a new PDF", "cowork", "fixed")],
}
KINDS = {"behavior": "Behavior", "consistency": "Consistency", "fixed": "Fixed", "band": "Band"}


def check_texts(case):
    """The checks as expected.md lists them, each with its kind."""
    return [f"{c} ({KINDS[kind]})" for c, _, kind in CHECKS[case]]


def results_md():
    rows = [[case, c, KINDS[kind], "" if where != "ai" else "n/a", "" if where != "cowork" else "n/a", ""]
            for case, checks in CHECKS.items() for c, where, kind in checks]
    head = ["# Manual Test Results", "", "Version: ", "Tester: ", "Date: ", "",
            "Mark each empty cell Pass or Fail. Add a note for every Fail (what happened, which file). Type: Behavior "
            "(it did or didn't), Consistency (two parts of the same run agree), Fixed (matches expected.md exactly), "
            "Band (inside expected.md's sanity band).", ""]
    out = ["| Case | Check | Type | Cowork | claude.ai | Notes |", "|---|---|---|---|---|---|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(head + out)


def readme_md():
    return "\n".join([
        "# Manual Smoke-Test Kit", "",
        f"Built {datetime.now():%Y-%m-%d %H:%M} by `make manual-kit`. Every file here is mock data: Casselberry and the "
        "other cities are real, every street, name, brokerage, parcel and MLS number is made up. Nothing here is "
        "committed; rebuild it for each release.", "",
        "The steps and the pass checks are in `docs/manual-testing.md`.", "",
        "## How to Use It", "",
        "1. Install the plugin in the desktop app and open a fresh Cowork working folder (see the doc).",
        "2. Run the cases in order, one new session each unless a case says otherwise. Each folder has:",
        "   - `prompt.md`: what to upload and the prompt to paste.",
        "   - the files to upload (nothing else: never upload `expected.md`).",
        "   - `expected.md`: the facts to check, computed by the skills' own scripts when the kit was built.",
        "3. Case 1 builds your real profile. Every later case uses it, so don't skip it.",
        "4. Fill in `results.md` as you go and share it back.", "",
        "## Cases", "",
        table(["Folder", "Skill", "Upload"], [
            ["01-agent-profile", "agent-profile", "nothing"],
            ["02-seller-cma", "seller-cma", "360 report, CMA export, seller notes"],
            ["03-buyer-cma", "buyer-cma", "listing flyer, 360 report, CMA export"],
            ["04-buyer-offer-strategy", "buyer-offer-strategy", "nothing: continue the case 3 chat"],
            ["05-seller-offer-review", "seller-offer-review", "step-1 offer package, then step-2"],
            ["06-contract-timeline-fha", "contract-timeline", "executed FHA package"],
            ["07-contract-timeline-short-sale", "contract-timeline", "executed short sale package"],
            ["08-contract-timeline-other-state", "contract-timeline", "Ohio purchase agreement"],
            ["09-seller-net-sheet", "seller-net-sheet", "nothing"]]), "",
        "claude.ai pass (shorter): upload `dist/skills/*.zip`, then run cases 1, 2 and 6.",
    ])


NET_SHEET = {"address": "3318 Wren Hollow Ln", "city": "Casselberry", "county": "Seminole", "state": "FL",
             "prices": (425000, 410000), "credit": 6000, "chat_price": 400000, "payoff": 188000, "listing_fee_pct": 0.0275,
             "buyer_broker_fee_pct": 0.025, "annual_tax": 5400, "closing": "2026-12-04"}


def case_net_sheet(checks):
    n, d = NET_SHEET, os.path.join(OUT, "09-seller-net-sheet")
    prompt = (f"Today is {long_date(TODAY)}. Net sheet for my seller at {n['address']}, {n['city']} ({n['county']} County): "
              f"{money(n['prices'][0])} and {money(n['prices'][1])}, and {money(n['prices'][0])} with a {money(n['credit'])} "
              f"credit to the buyer. They owe about {money(n['payoff'])}. My listing agreement is 2.75% and 2.5% to the "
              f"buyer's agent. Taxes are {money(n['annual_tax'])} a year. We'd close around {long_date(n['closing'])}. "
              "I need a PDF to print.")
    chat = f"Now just tell me here in chat: what would they net at {money(n['chat_price'])}?"
    write(os.path.join(d, "prompt.md"), prompt_md("Case 9: Seller Net Sheet", [], [
        {"title": "Step 1", "text": prompt}, {"title": "Step 2 (same session)", "text": chat}]))

    def compute(scenarios):
        data = {"prepared_date": TODAY, "closing_date": n["closing"], "scenarios": scenarios,
                "property": {k: n[k] for k in ("address", "city", "county", "state")},
                "costs": {"listing_fee_pct": n["listing_fee_pct"], "buyer_broker_fee_pct": n["buyer_broker_fee_pct"],
                          "mortgage_payoff": n["payoff"], "annual_tax": n["annual_tax"]}}
        path = os.path.join(WORK, "09-net-sheet.json")
        dump(path, data)
        return run(["skills/seller-net-sheet/scripts/compute.py", path])

    pdf = compute([{"price": n["prices"][0]}, {"price": n["prices"][1]}, {"price": n["prices"][0], "seller_credit": n["credit"]}])
    chat_net = compute([{"price": n["chat_price"]}])
    rows = [[r["label"], *r["display"]] for r in pdf["rows"] if r["kind"] != "group"]
    write(os.path.join(d, "expected.md"), "\n".join([
        "# Case 9: Expected", "",
        "Computed by the skill's own script from the facts in the prompt (no HOA; the property type isn't in the "
        "prompt, which changes nothing in Seminole County).", "",
        "## Step 1: The PDF", "",
        table(["Line", *[c["label"] for c in pdf["columns"]]], rows), "",
        "- One page, in the profile's colors, with the agent's name and brokerage in the header.",
        "- The tax proration line reads \"Property Tax Proration (Jan 1 to Closing)\" with no Assumed label; the notes "
        "say the bill is assumed unpaid (a December closing), once, and the reply says so.",
        "- Title company fees show as four lines (settlement, title search, municipal lien search, recording).",
        "- The reply lists the assumptions (the unpaid tax bill, typical title fees) and offers the chat version in one line.", "",
        "## Step 2: In Chat", "",
        f"- Net at {money(n['chat_price'])}: **{chat_net['columns'][0]['net_display']}** (a markdown table, no new PDF).", "",
        "## Checks", ""] + [f"- {c}" for c in checks]))


# --- verification -----------------------------------------------------------------------

def verify():
    """Every case folder has its files; every PDF opens and holds the text it should."""
    must = {
        "02-seller-cma": {D["seller_home"]["report_file"]: ["842 TANAGER RIDGE DR", "ACT->EXP", "X4488112", "Tax Area"]},
        "03-buyer-cma": {D["buyer_home"]["report_file"]: ["2315 KESTREL POINT CT", "474900.00->464900", "Active"],
                         D["buyer_home"]["flyer_file"]: ["$464,900", "Lakeshore Crest Realty"]},
        "08-contract-timeline-other-state": {D["other_state"]["file"]: ["Residential Purchase Agreement",
                                                                        "within 3 days", "September 24, 2026"]},
    }
    problems = []
    for case in CHECKS:
        d = os.path.join(OUT, case)
        for f in ("prompt.md", "expected.md"):
            if not os.path.exists(os.path.join(d, f)):
                problems.append(f"{case}/{f} missing")
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".pdf"):
                    text = pdf_text(os.path.join(root, f))
                    if len(text) < 200:
                        problems.append(f"{case}/{f}: almost no text")
                    for needle in must.get(case, {}).get(f, []):
                        if needle not in text:
                            problems.append(f"{case}/{f}: missing {needle!r}")
                if f == "expected.md" or f == "prompt.md":
                    body = open(os.path.join(root, f), encoding="utf-8").read()
                    if "key/" in body and "Answer-Key" in body:
                        problems.append(f"{case}/{f} points at an answer key")
        if case == "05-seller-offer-review" and any("key" in dirs for _, dirs, _ in os.walk(d)):
            problems.append("an answer key folder was copied into case 5")
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
        print("01 agent-profile")
        case_profile(check_texts("01-agent-profile"))
        print("02 seller-cma")
        case_seller_cma(pdf, check_texts("02-seller-cma"))
        print("03 buyer-cma")
        _, buyer_comp = case_buyer_cma(pdf, check_texts("03-buyer-cma"))
        print("04 buyer-offer-strategy")
        case_offer_strategy(buyer_comp, check_texts("04-buyer-offer-strategy"))
        print("05 seller-offer-review")
        case_offer_review(check_texts("05-seller-offer-review"))
        print("06 contract-timeline (FHA)")
        case_timeline("06-contract-timeline-fha", "asis-fha-executed", "Case 6: Contract Timeline (FHA)",
                      "Today is {today}. Here's my buyer's executed contract package for {address}, {city}. Give me every "
                      "deadline as a PDF timeline and a calendar file.", check_texts("06-contract-timeline-fha"))
        print("07 contract-timeline (short sale)")
        case_timeline("07-contract-timeline-short-sale", "asis-short-sale-rent-back",
                      "Case 7: Contract Timeline (Short Sale)",
                      "Today is {today}. Here's my buyer's executed short sale contract for {address}, {city}. Build the "
                      "deadline timeline: PDF and calendar file.", check_texts("07-contract-timeline-short-sale"))
        print("08 contract-timeline (other state)")
        case_other_state(pdf, check_texts("08-contract-timeline-other-state"))
        print("09 seller-net-sheet")
        case_net_sheet(check_texts("09-seller-net-sheet"))
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
