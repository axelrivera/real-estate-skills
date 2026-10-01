"""Third-party documents that travel with a contract package but aren't Florida Realtors forms: the lender's
pre-approval letter, a bank's proof of funds, and the escrow agent's deposit receipt. Every institution, officer,
account and ID is made up, and each page carries a small footer marking it as a mock document for software testing,
so a realistic letter can't pass as a real one outside this repo. Local dev only.
"""
import random

import pymupdf

import scenario as sc
import stamp

LENDERS, BANKS = sc.LENDERS, sc.BANKS
FOOTER = "Mock document for software testing. Not issued by a real lender, bank or escrow agent."
CSS = """
* { font-family: sans-serif; font-size: 10pt; color: #1a1a1a; }
h1 { font-size: 15pt; margin: 0; color: #0f2a4a; }
.sub { font-size: 8.5pt; color: #555; margin: 0 0 14pt 0; }
h2 { font-size: 11.5pt; margin: 14pt 0 6pt 0; }
p { margin: 0 0 7pt 0; line-height: 1.3; }
table { border-collapse: collapse; margin: 4pt 0 10pt 0; }
td { padding: 2.5pt 10pt 2.5pt 0; vertical-align: top; }
td.k { color: #555; }
.small { font-size: 8.5pt; color: #444; }
"""


def _page(doc, header, sub, body_html):
    page = doc.new_page(width=612, height=792)
    page.draw_line((54, 96), (558, 96), color=(0.06, 0.16, 0.29), width=1.2)
    page.insert_htmlbox(pymupdf.Rect(54, 44, 558, 96), f"<h1>{header}</h1><p class='sub'>{sub}</p>", css=CSS)
    page.insert_htmlbox(pymupdf.Rect(54, 112, 558, 700), body_html, css=CSS)
    page.insert_text((54, 764), FOOTER, fontname="helv", fontsize=6.5, color=(0.45, 0.45, 0.45))
    return page


def _sign(page, name, title, y, font_index=1):
    fontfile = stamp.os.path.join(stamp.FONTS, stamp.SIGNATURE_FONTS[font_index % len(stamp.SIGNATURE_FONTS)])
    page.insert_font(fontname="sigL", fontfile=fontfile)
    page.insert_text((56, y), name, fontname="sigL", fontsize=20, color=stamp.SIG_INK)
    page.draw_line((54, y + 10), (250, y + 10), color=(0.3, 0.3, 0.3), width=0.5)
    page.insert_text((54, y + 22), name, fontname="helv", fontsize=9)
    page.insert_text((54, y + 34), title, fontname="helv", fontsize=8.5, color=(0.35, 0.35, 0.35))


def _table(rows):
    return "<table>" + "".join(f"<tr><td class='k'>{k}</td><td>{v}</td></tr>" for k, v in rows if v not in (None, "")) + "</table>"


def _phone(ctx, rng):
    return f"({ctx['area_code']}) 555-{rng.randint(300, 399):04d}"


def pre_approval(ctx, v, rng):
    lender, street = v.get("lender") or rng.choice(LENDERS), None
    if isinstance(lender, (list, tuple)):
        lender, street = lender
    street = street or f"{rng.randint(100, 999)} Commerce Center Dr"
    officer = v.get("loan_officer") or sc.fresh_name(rng, ctx["used_names"])
    ctx["pre_approval_officer"] = officer  # the answer key records who signed the letter (offers[].loan_officer)
    issued = sc._dt(v["date"])
    program = {"fha": "FHA", "va": "VA", "usda": "USDA", "conventional": "Conventional", "other": "Portfolio"}.get(ctx["financing"], "Conventional")
    term = ctx["term_years"] or 30
    rate = {"fixed": "fixed rate", "adjustable": "adjustable rate", "either": "fixed or adjustable rate"}.get(ctx["rate_type"] or "fixed")
    price_cap = v.get("price_cap") or ctx["price"]
    loan_cap = v.get("loan_cap") or ctx["loan_amount"]
    doc = pymupdf.open()
    body = (f"<p>{sc.mdy(issued)}</p><p>{ctx['buyer_names']}<br>c/o {ctx['cooperating_associate']}, {ctx['cooperating_broker']}</p>"
            f"<h2>Mortgage Pre-Approval</h2>"
            f"<p>Congratulations. Based on our review of your credit report, income and asset documentation, you are pre-approved "
            f"for a mortgage loan on the following terms:</p>"
            + _table([("Borrower(s)", ctx["buyer_names"]), ("Property", ctx["property_address"] if v.get("property_specific", True) else "To be determined"),
                      ("Loan program", f"{program} {term}-year {rate}"), ("Purchase price up to", f"${price_cap:,.0f}"),
                      ("Loan amount up to", f"${loan_cap:,.0f}"), ("Occupancy", "Primary residence"),
                      ("Expires", sc.mdy(issued.date() + sc.timedelta(days=90)))])
            + "<p>Final loan approval is subject to a satisfactory appraisal, clear title, no material change in your credit, "
            "income or assets before closing, verification of the funds needed to close, and the property meeting the "
            f"{program} program's requirements. This letter is not a commitment to lend.</p>"
            f"<p>Please contact me with any questions.</p>")
    page = _page(doc, lender, f"{street}, {ctx['escrow_city_line']} &middot; {_phone(ctx, rng)} &middot; NMLS #MOCK-{rng.randint(1000, 9999)}", body)
    _sign(page, officer, f"Senior Loan Officer, NMLS #MOCK-{rng.randint(10000, 99999)}", 560)
    return doc


def proof_of_funds(ctx, v, rng):
    bank = v.get("bank") or rng.choice(BANKS)
    officer = v.get("officer") or sc.fresh_name(rng, ctx["used_names"])
    issued = sc._dt(v["date"])
    needed = v.get("needed") or ctx["funds_needed"]
    balance = v.get("balance") or int(round(needed * rng.uniform(1.12, 1.4), -3))
    doc = pymupdf.open()
    body = (f"<p>{sc.mdy(issued)}</p><p>To whom it may concern:</p><h2>Verification of Funds</h2>"
            f"<p>At the request of our customer(s), we confirm the following account held at {bank}:</p>"
            + _table([("Account holder(s)", ctx["buyer_names"]), ("Account type", v.get("account_type") or "Personal money market"),
                      ("Account number", f"XXXXXX{rng.randint(1000, 9999)}"), ("Available balance", f"${balance:,.2f}"),
                      ("As of", sc.mdy(issued))])
            + "<p>The account is in good standing. This letter confirms the balance on the date shown only; it is not a guarantee "
            "of future balances or a commitment of funds.</p>")
    page = _page(doc, bank, f"Private Client Services &middot; {ctx['escrow_city_line']} &middot; {_phone(ctx, rng)}", body)
    _sign(page, officer, "Relationship Manager", 520, 0)
    return doc


def escrow_receipt(ctx, v, rng):
    received = sc._dt(v["date"])
    file_no = v.get("file_number") or f"{received.year % 100:02d}-{rng.randint(1000, 9999)}"
    officer = v.get("officer") or sc.fresh_name(rng, ctx["used_names"])
    amount = v["amount"]
    doc = pymupdf.open()
    body = (f"<p>{sc.mdy(received)}</p><p>{ctx['cooperating_associate']}, {ctx['cooperating_broker']}<br>"
            f"{ctx['listing_associate']}, {ctx['listing_broker']}</p><h2>Escrow Deposit Receipt</h2>"
            + _table([("Escrow file", file_no), ("Property", ctx["property_address"]), ("Buyer(s)", ctx["buyer_names"]),
                      ("Seller(s)", ctx["seller_names"]), ("Deposit", v.get("label") or "Initial deposit"),
                      ("Amount received", f"${amount:,.2f}"), ("Received", sc.when(received)),
                      ("Method", v.get("method") or "Wire transfer")])
            + f"<p>{ctx['escrow_name']} confirms receipt of the deposit above, held in its escrow trust account under the "
            "terms of the Contract. Funds received by wire are Collected on receipt; checks are subject to collection.</p>")
    page = _page(doc, ctx["escrow_name"], f"{ctx['escrow_address']} &middot; {ctx['escrow_phone']}", body)
    _sign(page, officer, "Escrow Officer", 520, 2)
    return doc


RENDER = {"pre_approval": pre_approval, "proof_of_funds": proof_of_funds, "escrow_receipt": escrow_receipt}
TITLES = {"pre_approval": "Lender pre-approval letter", "proof_of_funds": "Proof of funds", "escrow_receipt": "Escrow deposit receipt"}


def render(kind, ctx, values, seed):
    return RENDER[kind](ctx, values, random.Random(f"{seed}|{kind}|{values.get('label', '')}"))
