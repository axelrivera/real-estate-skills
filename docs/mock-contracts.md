# Mock Contracts

A development tool that builds realistic FR/BAR contract packages as one PDF: everything the buyer's and seller's sides exchange. That's the contract, riders, addenda, the seller's disclosures, the buyer's pre-approval or proof of funds, counter offers, escrow deposit receipts and amendments. All of it is filled in and signed Dotloop-style at any stage from a buyer-signed offer to an amended contract. Use them to test the contract-reading skills (contract-timeline, seller-offer-review, buyer-offer-strategy) on the kind of upload agents actually send.

- **Claude Code only, never shipped.** The skill lives in `.claude/skills/mock-contract/` and the code in `dev/mock_contracts/`. `make package` includes neither.
- **Local only.** It fills the real FR/BAR PDFs in the git-ignored `sources/Contracts/FARBAR/` and uses PyMuPDF, which the sandbox doesn't have.
- **Outputs go to `out/mock-contracts/<id>/`** (git-ignored, removed by `make clean`). The PDFs contain Florida Realtors' form text, so they are never committed. The same goes for `samples/` and `dev/evals/`: copy a package into an eval run folder under `out/` instead.
- **Fictional data only.** Every person, brokerage, street, tax ID and legal description the tool makes up is fictional, and no two made-up people share a first name or surname (a shared surname reads as a relative). Use the same rule for anything you type into a spec. Cities, ZIP codes and counties are real (the rules need the county); with a made-up street, no address is real. The builder removes the "Licensed to dotloop, Inc. and ..." line from the source PDFs, which names the real account the forms came from.
- **Every value in the answer key is on the PDF.** A value the spec gives a rider, addendum, disclosure, counter or amendment must have a blank that prints it, or the build stops ([The Value Guard](#the-value-guard)). A skill that reads the package correctly always matches its key.

## Contents

- Setup
- Using the Skill
- Command Line
- Starters
- Package Contents
- Scenario Spec
- Stages and Signatures
- Defects
- Outputs
- Field Maps
- When a Form Is Revised
- Troubleshooting

## Setup

1. Run `make setup`. Besides the sandbox mirror, it installs `dev/requirements-tools.txt` (PyMuPDF). For an existing `.venv`, run `.venv/bin/python -m pip install -r dev/requirements-tools.txt`.
2. Put the FR/BAR PDFs in `sources/Contracts/FARBAR/`, laid out as `dev/forms/frbar-forms.json` lists them. Run `make forms-check` to confirm they match.

`make lint-skills` fails if anything in `skills/` or `shared/` imports PyMuPDF.

## Using the Skill

In Claude Code, from the repo root, describe the deal in plain words, or point to a file. The skill reads the scenario, asks only about what matters and isn't given, writes a spec, builds the package, looks at the filled pages, and reports what it made. It asks about the contract form first, since that is never defaulted, then the stage when it isn't clear. Everything else gets a mock default.

Examples:

- "Make a mock executed AS IS contract, FHA, 1972 house, with an inspection extension."
- "Standard contract with Rider L and an appraisal contingency, seller countered at $552,000, not accepted yet."
- "Buyer-signed offer on a condo with an appraisal gap addendum. Include the answer key and a scanned copy."
- "Use `dev/fixtures/contract-timeline/standard-riders.json` as the deal and build the executed package."
- "Same as asis-fha-executed but leave the seller's initials off page 4 and don't attach the FHA rider."
- "Three counters: the seller at $439k, the buyer at $432.5k with a 25-day loan approval, then the seller accepts restating both."

The skill can use any form in `dev/forms/frbar-forms.json`: both contracts, the 33 CR-7 riders and the 35 addenda and disclosures. For a form without a field map it fills the common blanks automatically (parties, property, signatures, dates, initials). When the scenario needs that form's other blanks, it drafts a map (see [Field Maps](#field-maps)).

To keep a scenario as a starter, ask the skill to save it. It goes to `dev/mock_contracts/scenarios/` and `make mock-contracts` builds it from then on.

## Command Line

```bash
.venv/bin/python dev/mock_contracts/build.py SPEC.json [--answer-key] [--scanned] [--defects a,b] [--out DIR]
.venv/bin/python dev/mock_contracts/build.py --list-defects
make mock-contracts                          # every spec in dev/mock_contracts/scenarios/
make mock-contracts ARGS="--answer-key --scanned"
```

| Flag | What it does |
|---|---|
| `--answer-key` | Also writes `key/<Street>-Answer-Key.json`, the ground truth: a contract-timeline deal file once the contract is executed, a seller-offer-review listing file before (see [Outputs](#outputs)) |
| `--scanned` | Also writes `<Street>-<Contract|Offer>-Scanned.pdf`: an image-only copy at 150 dpi in grayscale, slightly rotated with light speckle and no text layer, like a scanned upload |
| `--defects` | Comma-separated [defects](#defects) to add on top of the spec's own `defects` |
| `--out` | Output folder (default `out/mock-contracts/<id>/`) |
| `--list-defects` | Prints every defect name and what it does |

By default the outputs are the package PDF, the compensation agreement with Rider GG, and a copy of the spec in `key/`.

**Names.**

- **Folder (`<id>`):** the spec's `name` when it has one (the starters, and specs kept in `dev/mock_contracts/scenarios/`). Otherwise the street, the stage and a 6-character hash of the spec: `1532-cypress-bend-dr-executed-3fa9c2`. Two different scenarios never share a folder, and rebuilding the same spec reuses its own.
- **Files:** named after the property, as an agent's files are:
  - `1532-Cypress-Bend-Dr-Offer.pdf` before acceptance, and `1532-Cypress-Bend-Dr-Contract.pdf` once accepted.
  - `1532-Cypress-Bend-Dr-Compensation-Agreement.pdf`.
  - `...-Scanned.pdf`.
- **Seed:** the id also seeds every mock default, so the same spec always builds the same package.

`dev/mock_contracts/locate.py` inspects a form's blanks (see [Field Maps](#field-maps)):

| Flag | What it does |
|---|---|
| `locate.py FAMILY` | Lists every blank on the form: its id, page, kind, the text to its left and the text to its right |
| `--pages` | Only these pages (`--pages 1,13`) |
| `--debug` | Writes a copy of the form with every blank outlined and labeled with its id, and with its field name when a map exists (red) |
| `--draft` | Writes every blank with its label, following text and caption to `out/mock-contracts/_drafts/<FAMILY>.json`, the starting point for a new map |
| `--json` | Prints the blanks as JSON |

## Starters

`make mock-contracts` builds every spec in `dev/mock_contracts/scenarios/`. All of them are fictional deals in real cities.

| Starter | Stage | What it covers |
|---|---|---|
| `asis-fha-executed` | executed | AS IS, FHA (Rider E), Rider H with its date, a seller-paid home warranty |
| `asis-offer-aga` | offer | A buyer-signed offer with an appraisal gap (AGA-1), an HOA (Rider B), the seller's disclosures and a pre-approval |
| `condo-asis-amended` | amended | A 1974 condo, cash (Riders A and P, MISIRS-2, RCD-8), one CO-3 counter, an EA-4 extension and an ACSP-4 |
| `standard-counter-chain` | executed | Three CO-3 counters, VA (Rider E), a 5-day rent-back (Rider U) |
| `standard-l-countered` | countered | Standard with Riders L and F, repair limits, a seller counter pending |
| `asis-ff-credit` | executed | The buyer's broker paid as a seller credit to the buyer (Rider FF), 95% conventional |
| `standard-seller-paid-comp` | executed | Rider GG with a seller-to-broker compensation agreement (CASSB-1) |
| `asis-late-comp-agreement` | executed | Defects: the compensation agreement signed after GG's window, and the seller's initials missing on page 6 |
| `asis-multiple-offers` | offer | NMOB-1 (highest and best), an escalation addendum (EAC-1), a pre-approval and proof of funds |
| `standard-buyer-counter-pending` | countered | Seller's CO-3 #1, then the buyer's CO-3 #2, pending |
| `asis-counter-on-contract` | executed | The seller counters on the contract itself (`method: contract`), accepted by the buyer's initials |
| `asis-short-sale-rent-back` | executed | Short sale (Rider G) with a 14-day rent-back (Rider U), FHA |

`ARGS="--scanned"` adds a scanned copy of each; an eval that wants a scan names the starter and builds it with the flag.

## Package Contents

Only what passes between the buyer's side and the seller's side. Brokerage relationship notices, the buyer's brokerage agreement and each side's own paperwork with its broker are left out. So are inspection and appraisal reports, which come later. The one exception is Rider GG's compensation agreement (CASSB-1): it goes in a separate file, `<Street>-Compensation-Agreement.pdf`, because it isn't part of the contract. See [Compensation Agreement](#compensation-agreement).

| Stage | The package adds |
|---|---|
| `offer` | The contract, riders and addenda signed by the buyer. The seller's disclosures, signed by the seller at listing and acknowledged by the buyer at the offer. The buyer's proof: a pre-approval letter when financing; proof of funds for cash, and alongside the pre-approval when AGA-1 or EAC-1 commits cash beyond the loan |
| `countered` | The counter offers (CO-3) |
| `executed` | The seller's signatures (or the accepted counter), the buyer's receipt of the condo documents (RCD-8) for a condo, and the escrow agent's receipt for the initial deposit |
| `amended` | The amendments, and the receipt for the additional deposit when there is one |

**Disclosures by default:**

| When | Forms |
|---|---|
| Always | SPDR-4x (SPDC-2 for a condo), FD-2 (statutory flood disclosure) |
| Condo | MISIRS-2 (milestone inspection and SIRS), and RCD-8 once the contract is accepted |
| The property facts above | CDDA-2, SD-2, CCCLA-3, MDSTS-2, FIN-2 |
| `multiple_offers: true` | NMOB-1 (the seller's call for highest and best, before the offer) |
| Only when included | SOD-2, HID-2, WFPN-3, TRID-1, EDRV-1, SPDU-1, SUP-1 and any other form in the manifest (informational notices, or forms between a broker and their own client) |

**Changing the package.** `package` takes three keys:

- `include`: a list of form codes or generated documents to add, such as `["WFPN", "proof_of_funds"]`.
- `exclude`: a list to remove, such as `["SPDR", "escrow_receipt"]`.
- `proof`: `pre_approval`, `proof_of_funds`, `both` or `none`.

**Disclosure answers.** `disclosures` sets values per form: `{"SPDR": {"occupancy": "tenant", "answers": {"water intrusion": "yes", "roof": "dont_know"}, "fill": {...}}}`.

- Every yes/no question gets a plausible default (`answers.py`). A follow-up ("If yes, was the claim paid?") is left blank unless the question before it was answered that way. Questions about good condition ("structurally sound", "in working condition") get Yes; everything else gets No. The property's facts come first, so a disclosure never contradicts a rider: with `hoa` the SPDR's association question is Yes, and with `sinkhole_claim` so is its claim question.
- MISIRS-2 has its own defaults: not exempt, Phase 1 done, Phase 2 not required, SIRS done.
- An answer matches any question containing its text: `yes`, `no` or `dont_know`. `default_answer` changes the default for every question on the form.
- Other keys:
  - SPDR and SPDC: `occupancy` (`owner`, `tenant`, `unoccupied`) and `vacant_since`.
  - FD: `copy_date`.
  - RCD: `received` (default the day after the Effective Date) and `condo_name`.
  - MISIRS: `association`.
  - NMOB: `deadline` (default 9:00 PM on the offer's day, or noon the next day for an offer signed after 8:00 PM) and `other`.

**Generated documents.** These are letterhead pages, not Florida Realtors forms. Every lender, bank, officer and account is made up, IDs read `NMLS #MOCK-...`, and each page carries a small "Mock document for software testing" footer. `letters` overrides their values by type:

| Type | When | Keys |
|---|---|---|
| `pre_approval` | 4 days before the offer | `lender`, `loan_officer`, `price_cap`, `loan_cap`, `property_specific` (false: "To be determined") |
| `proof_of_funds` | 2 days before the offer | `bank`, `officer`, `balance` (default 12% to 40% over the cash needed: down payment, about 3% in costs, any gap or escalation), `account_type` |
| `escrow_receipt` | The initial deposit: with the offer, or within its days after the Effective Date | Set by the deposit; excluded by name |

### Compensation Agreement

Every package with Rider GG also gets `<Street>-Compensation-Agreement.pdf`: CASSB-1, filled in and signed on its own, never merged into the package.

| `buyer_broker.between` | Paid by (CASSB-1 Para. 1) | Signed by |
|---|---|---|
| `brokers` (default) | Seller's Broker: the listing brokerage | The listing associate for the listing brokerage, and the buyer's associate for the buyer's brokerage |
| `seller` | Seller, with the property checked as listed by the listing brokerage | Every seller, and the buyer's associate |

- **Timing on an accepted contract:**
  - The buyer's broker signs 1 to 2 hours after the Effective Date.
  - The payer signs on a day inside Rider GG's window, 1 to `compensation_agreement_days` days after the Effective Date (default 3).
  - So the agreement is executed after the contract and before the buyer's cancel right opens.
- **Offer not yet accepted:** a draft signed only by the buyer's broker, since GG's window hasn't started.
- **Amount:** `percent` (default 2.5% of the purchase price) and/or `amount` (a flat fee, or dollars added to the percent).
- **Other keys:**
  - `term_days` (default 30; CASSB-1's Term runs through closing once the contract is executed).
  - `other_terms`.
- **`late-compensation-agreement` defect:** the payer signs 1 or 2 days after the window, so the buyer's right to cancel under GG opens.

The answer key's `mock.compensation_agreement` records who pays and who signed when, the window's end and whether the agreement landed inside it. contract-timeline itself only reads `compensation_agreement_days`.

**Order in the PDF**, the order the documents change hands:

1. Contract, riders, offer addenda.
2. Disclosures, then the proof letters.
3. Counters.
4. The condo document receipt, then the escrow receipts.
5. Amendments.

## Scenario Spec

A JSON file. Only `form` is required. A value that is missing gets a realistic mock default; a value set to `null` leaves the blank empty so the form's printed default applies. Dates are `YYYY-MM-DD`, and times `YYYY-MM-DD HH:MM` in Eastern time.

```json
{
  "name": "asis-fha-executed",
  "form": "as_is",
  "stage": "executed",
  "buyers": ["Jordan Avery"],
  "sellers": ["Morgan Whitfield", "Casey Whitfield"],
  "property": {"address": "1532 Cypress Bend Dr, Casselberry, FL 32707", "county": "Seminole", "year_built": 1994},
  "price": 365000,
  "financing": {"type": "fha", "approval_days": 30, "application_days": 5},
  "deposit": {"initial": 11000, "days": 3},
  "inspection_days": 10,
  "dates": {"offer": "2026-09-23 19:10", "effective": "2026-09-25 16:12", "closing": "2026-10-30"},
  "riders": ["E", {"code": "H", "insurance_date": "2026-10-05"}],
  "home_warranty": {"paid_by": "seller", "provider": "Sunward Home Shield", "max": 550}
}
```

### The Deal

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | text | street, stage and spec hash | The output folder's name and the seed for mock values. Give one to keep a scenario under a fixed name |
| `form` | text | **required** | `as_is` or `standard` (also "AS IS", "ASIS-7", "Standard"). Another contract is refused: only FR/BAR PDFs exist |
| `stage` | text | from the rest | `offer`, `countered`, `executed` or `amended`. Without it: `amended` when there are amendments, `countered` when there are counters, else `executed` |
| `side` | text | `buyer` | The answer key's `side` |
| `buyers`, `sellers` | list or text | one fictional name each | Up to two of each get their own signature and initials slots |
| `price` | number | random | The offer's price. A counter changes it on the counter |
| `list_price` | number | the price, or up to 5% above it | Only in an unaccepted package's answer key (seller-offer-review needs it) |
| `inspection_days` | number | AS IS 10, Standard 15 | Para. 12(a). `null` leaves it blank (15 by the form) |
| `title_evidence_days`, `flood_elevation_days` | number | blank | Para. 9(c) and 10(d) |
| `additional_terms` | text | none | Para. 20, flowed across its lines |
| `personal_property_included`, `excluded_items` | text | none | Para. 1(d) and 1(e) |
| `tenants` | true/false | false | Para. 6(b) |
| `assignability` | text | `no` | `no`, `released` or `not_released` (Para. 7) |
| `title_by` | text | `seller` | `seller`, `buyer` or `miami_dade` (Para. 9(c)), with `title_search_cap` for Miami-Dade |
| `home_warranty` | object | `paid_by: na` | `paid_by` (`buyer`, `seller`, `na`), `provider`, `max` |
| `special_assessments` | text | `a` | Para. 9(e) option `a` or `b` |
| `seller_costs_other`, `buyer_costs_other` | text | none | The "Other:" lines in Para. 9(a) and 9(b) |
| `repair_limits` | object | blank (1.5%) | Standard only: `general`, `wdo`, `permit`, each in dollars (`5000`) or as a share of price (`0.02`) |
| `other_amount`, `other_label` | number, text | none | Para. 2(d) |
| `buyer_broker` | text or object | `GG` | How the buyer's broker is paid; every package carries it unless this is `none`. `GG` (default): Rider GG with `between` `brokers` (the default: a compensation agreement between the listing and buyer's brokers) or `seller`, and `compensation_agreement_days` (default 3), plus the agreement's `percent`, `amount`, `term_days` and `other_terms` ([Compensation Agreement](#compensation-agreement)). `FF`: Rider FF, a seller credit to the buyer, with `percent` (default 2.5), `amount`, `buyer_brokerage` (default the cooperating broker) and `excess` (`broker` or `reduce`). `none`: no compensation document, to test a package without one. A GG or FF already in `riders` takes these values instead of a second rider |
| `sale_of_buyers_property` | true/false | false | Adds Rider V |
| `buyer_notice_address`, `seller_notice_address` | text | none | The notice lines by the signatures |
| `brokers` | object | fictional | `listing_associate`, `listing_broker`, `cooperating_associate`, `cooperating_broker` |
| `fill` | object | none | Raw blank values for the contract by form family: `{"FRBAR-ASIS": {"L141": "Survey"}}` (see [Field Maps](#field-maps)) |

### Property

| Key | Default | Notes |
|---|---|---|
| `property.address` | a fictional street in a real city of the county | Include the unit for a condo. Write it as "street, city, FL ZIP": the escrow agent's office goes in the same city |
| `property.county` | `Seminole` (or top-level `county`) | Real Florida county. Cities are built in for 22 counties (Orlando, Tampa, South Florida, both coasts, Jacksonville, Tallahassee, Gainesville, Pensacola); for another county, give the address |
| `property.tax_id`, `property.legal_description` | fictional | A lot and block, or a condominium unit when `type` is `condo` |
| `property.type` | `single_family` (`condo` when `unit` is set) | `single_family`, `condo`, `townhouse` |
| `property.unit` | none | Makes the property a condo |
| `property.year_built` | random, 1986 to 2016 | Before 1978 adds Rider P |
| `property.hoa` | false | A mandatory HOA adds Rider B |
| `property.cdd` | false | In a community development district: adds CDDA-2 |
| `property.sinkhole_claim` | false | A paid sinkhole claim: adds SD-2 |
| `property.coastal` | false | Seaward of the Coastal Construction Control Line: adds CCCLA-3 (the seller's affidavit, left out when Rider N waives it) and answers the SPDR's CCCL question Yes. Add Rider N in `riders` |
| `property.septic` | false | With a Miami-Dade county property: adds MDSTS-2 |
| `property.flood_zone` | none | A zone starting with A or V adds FIN-2 |

### Money and Financing

| Key | Default | Notes |
|---|---|---|
| `financing` | `conventional` | A type, or an object: `type` (`cash`, `conventional`, `fha`, `va`, `usda`, `other`), `ltv` (percent: FHA 96.5, VA and USDA 100, others 80), `loan_amount`, `approval_days` (30), `application_days` (5), `rate_type` (`fixed`, `adjustable`, `either`), `max_rate`, `term_years`, `other_description` |
| `deposit.initial` | 1% (FHA, VA, USDA) or 2% of price | |
| `deposit.with_offer` | false | Checks 2(a)(i) instead of (ii) |
| `deposit.days` | 3 | 2(a)(ii). `null` leaves it blank |
| `deposit.additional`, `deposit.additional_days` | 2% and 10 days for conventional or cash over $400,000, else none | 2(b) |
| `escrow_agent` | a fictional title company | `name`, `address`, `phone`, `email`, `fax` |

A loan is never larger than the price less the deposits, so a 100% loan leaves a zero balance to close rather than a negative one. When deposits plus the loan exceed the price, the build stops.

### Dates

| Key | Default |
|---|---|
| `dates.offer` | `2026-09-21 19:05` (the buyer signs the offer) |
| `dates.acceptance_deadline` | 2 days after the offer, 5:00 PM (Para. 3(a)) |
| `dates.effective` | The day after the last counter (or the offer), during the day: when the last party signs |
| `dates.closing` | 36 days after the Effective Date (or the offer), moved to a business day. With AGA-1, at least 5 days after its renegotiation period ends, so no contingency outlives closing |

Riders and addenda take dates in their own objects (`insurance_date`, `appraisal_date`). Amendment dates default to within the period they extend.

### Riders

`riders` is a list of CR-7 letters (`"E"`), names (`"FHA/VA Financing"`) or objects (`{"code": "H", "insurance_date": "2026-10-05"}`). Riders the property's facts require are added with a note: P when built before 1978, A for a condo, B for an HOA, E for FHA or VA, and V for the sale of the buyer's home. Buyer's broker compensation is added the same way: Rider GG, broker to broker, unless `buyer_broker` says otherwise. The rules come from `shared/contract_forms.py`: Riders I, K or L on AS IS, or K and L together on Standard, stop the build with the reason unless the `rider-conflict` defect is set.

Values the mapped riders read:

| Rider | Keys |
|---|---|
| A (Condominium) | `approval_required` ("is" or "is not required"), `rofr`, `rofr_members` (the association's and the members' right of first refusal, default none), `condo_docs_before_contract` (Para. 5(a) when true, else 5(b): the documents come after the contract), `association`, `management_company`, `contact`, `phone`, `email`, `website`, `management_contact`, `management_phone`, `management_email`, `fee`, `fee_period` (`monthly`, `quarterly`, `semi-annually`, `annually`), `approval_days`, `approval_initiate_days` |
| B (HOA) | `community`, `association`, `management_company`, `contact`, `phone`, `email`, `website`, `fee`, `fee_period` (free text: `month`), `approval_required` (checks "is" or "is not required"), `approval_days`, `approval_initiate_days` |
| GG (Broker Compensation) | `between` (`brokers` or `seller`), `compensation_agreement_days` |
| FF (Broker Credit) | `buyer_brokerage`, `percent`, `amount`, `excess` (`broker` or `reduce`) |
| E (FHA/VA) | `repair_cap` (default 1.5% of price, rounded to $100), `appraised_value`, `fha_fees_max`, `va_fees_max` |
| F (Appraisal) | `appraisal_date`, `appraised_value` |
| H (Insurance) | `homeowners` (default true), `homeowners_premium_max`, `homeowners_premium_pct`, `insurance_date`, `flood`, `flood_premium_max`, `flood_premium_pct`, `flood_date` |
| K, L | `inspection_days` (default the contract's) |
| P (Lead Paint) | `lead_known` (true, or text describing it), `records` (text listing them), `risk_assessment` (`received` or `waived`) |
| C (Seller Financing) | `seller_financing` (the note amount; default 10% of price as a second mortgage with a loan, else 80% as a first), `lien` (`first`, `second`), `rate` (7.25), `loan_type` (`amortized`, `interest_only`, `balloon`, `adjustable`), `term_years`, `interest_only_months`, `balloon_due_months`, `payment` (default the monthly payment over 30 years), `payment_period` (`monthly`, `quarterly`, `annual`), `first_payment_months` (1) |
| D (Assumption) | `mortgage_balance` (55% of price), `rate_type` (`fixed`, `variable`), `rate` (3.375), `max_rate`, `fees_cap` |
| G (Short Sale) | `short_sale_application_days`, `short_sale_approval_days`, `short_sale_closing_days`, `backup_offers` (`a` no back-up offers, `b` back-ups allowed) |
| S (Lease Purchase/Option) | `lease_type` (`purchase`, `option`), `attorney_fees_by` (`buyer`, `seller`, `split`) |
| T (Pre-Closing Occupancy) | `pre_closing_agreement_days`, `expense` (`seller`, `buyer`, `split`), `possession_date` (14 days before closing), `rent` (0.55% of price a month) |
| U (Post-Closing Occupancy) | `post_closing_agreement_days_before`, `expense`, `rent_back_days` (30), `rent_back_monthly` (0.55% of price). Also checks the contract's Para. 6(b) (occupancy after Closing); the key records no tenants |
| V (Sale of Buyer's Property) | `buyer_property` (a fictional street in the same city), `sale_contingency_date` (7 days before closing, with a note), `under_contract` (false) |
| W (Back-Up Contract) | `backup_notice_date` (14 days after the offer, with a note) |
| X (Kick-Out) | `kickout_deposit` (the initial deposit) |
| Z (Buyer's Attorney Approval) | `buyer_attorney_date` (5 days after the Effective Date, with a note) |
| N (Coastal Construction Control Line) | `cccl_requested` (true: the buyer requests the affidavit or survey; false: the buyer waives it and CCCLA-3 is left out; unset: neither box, as the rider has no default) |

A default is filled in only where the rider prints no default of its own; a blank that reads "if left blank, then 10" stays blank unless the spec sets it. The sale date on V and the dates on W and Z have no default in the rider: a real deal asks the agent (`frbar-package-check.md`), so the build notes the mock value it used.

Any rider also takes `fill` (blank ids or map field names, see [Field Maps](#field-maps)). The answer key takes only what the rider prints:

- **Executed key:** a rider's days and dates go into `contract` under the deal file's names (`skills/contract-timeline/references/frbar.md`). Most keep their spec name; `rent_back_days` becomes `seller_occupancy_days`. So do the yes/no boxes the deal file reads: `cccl_requested` (N), `rofr` and `condo_docs_before_contract` (A), and `lbp_waived` (P: true unless `risk_assessment` is `received`).
- **Offer key:** the listing file's names (`skills/seller-offer-review/references/listing-file.md`): `rent_back_days` and `rent_back_monthly` (U), `seller_financing` (C), `kickout` (X), and `insurance_days` (H), `sale_contingency_days` (V) and `attorney_days` (Z) counted from the offer to the rider's date.

### Addenda and Disclosures

`addenda` is a list of form codes (`"AGA"`, `"EAC-1"`) or objects (`{"form": "AGA", "gap_amount": 15000}`), in any family from `dev/forms/frbar-forms.json`. They are checked under Para. 19 "Other" by name.

| Form | Keys |
|---|---|
| AGA (Appraisal Gap) | `gap_amount` (default 3% of price), `pay` (`cash` or `finance`), `valuation_days`, `renegotiate_days` |
| EAC (Escalation) | `escalation_amount`, `maximum_price`, `pay`, `revised_price` |
| CDDA (Community Development District) | `district` (the name printed before "COMMUNITY DEVELOPMENT DISTRICT"; default the subdivision), `assessments` (up to two `{"amount", "per", "to"}` rows; default two yearly amounts to the county tax collector) |
| Any other | `fill` only, plus the automatic parties, property, signatures and initials |

Seller disclosures are set under `disclosures` instead (see [Package Contents](#package-contents)); one listed in `addenda` is treated the same way.

### Counters

`counters` is a list (or `counter` a single object), in order:

| Key | Default | Notes |
|---|---|---|
| `by` | alternating, `seller` first | Who makes the counter |
| `date` | the next day, during the day | When its maker signs |
| `price`, `closing` | unchanged | Checked on CO-3 with the new value |
| `changes` | none | Structured changes that become CO-3 rows with the contract line: `inspection_days`, `loan_approval_days`, `loan_application_days`, `deposit_days`, `additional_deposit`, `additional_deposit_days`, `title_evidence_days` |
| `terms` | none | Free-text rows, `[{"line": 53, "text": "..."}]`, after any `changes` rows |
| `included`, `excluded` | none | CO-3's items boxes |
| `deadline` | blank (2 days) | CO-3's acceptance deadline |
| `accepted` | from `stage` | Only the last counter. With `stage: countered` it defaults to false (pending) |
| `seller_signs_offer` | false | On the first counter: the seller also signs the offer's documents when countering |
| `method` | `co` | `co`: a Counter Offer (CO-3). `contract`: the seller counters on the contract itself (first counter only, by the seller) |

**Counter on the contract** (`method: contract`). Some sellers counter by marking up the buyer's contract instead of writing a CO-3:

- The seller checks "Seller counters Buyer's offer" (AS IS line 613, Standard line 699) and signs the contract at the counter's `date`.
- Each change to a contract blank (`price`, `closing` and the `changes` keys) is typed next to the offered value, which is struck through, with the seller's initials in the margin beside it.
- A new price (or additional deposit) also changes Para. 2's loan amount, at the offer's loan-to-value, and balance to close, so those lines are struck and retyped too and the page still adds up.
- `terms`, `included` and `excluded` go on Para. 20's empty lines after the buyer's own additional terms, as "Seller's counter-offer: ...", initialed the same way.
- **Accepted:** the buyer initials beside each change, next to the seller's. The last initial is the Effective Date, and the key's `effective_date_source` reads "Buyer's initials on the Seller's counter-offer changes (Para. 3(b))".
- **Pending** (`stage: countered`, not accepted): only the seller's marks, and the key is the offer's listing file.
- No CO-3 goes in the package. A `deadline` stops the build: the contract has no blank for a new acceptance deadline.

CO-3 says a counter "does not include terms and conditions of any other counter offer unless restated herein". So the answer key applies only the accepted counter to the original offer, and the build notes any earlier terms it drops. To carry a term through a chain, restate it in the last counter.

### Amendments

`amendments` is a list, signed after the Effective Date:

| Key | Default | Notes |
|---|---|---|
| `form` | `EA` for date changes, else `ACSP` | Any addendum family works with `fill` |
| `date` | within the period it extends, else about a week after the last | |
| `signed` | `all` | `buyer` or `seller` leaves it pending, and the answer key leaves it out |
| `closing`, `inspection_extra_days`, `inspection_until`, `loan_approval_extra_days`, `loan_approval_until` | none | EA-4 boxes |
| `title_cure_extra_days`, `title_cure_until`, `short_sale_extra_days`, `short_sale_until`, `sale_lease_extra_days`, `sale_lease_until`, `due_diligence_extra_days`, `due_diligence_until` | none | The other EA-4 boxes |
| `except_terms` | none | EA-4's "except:" area |
| `text`, `number`, `description` | none, per-form count | ACSP-4's terms and number; `description` for the answer key |

In the key, an EA-4's extra days change the matching `contract` field in the amendment's `changes` (inspection, loan approval, and the short sale approval deadline with Rider G). Its "until" dates go in `date_overrides` for the deadline they move (`inspection`, `loan_approval`, `title_cure`, `short_sale_approval`, `buyer_sale_closes`).

### Defects

`defects` is a list of names, or objects that pin where they land (`{"type": "missing-initials", "party": "buyer", "page": 6}`). See [Defects](#defects).

## Stages and Signatures

Every signature is a handwriting font with a "dotloop verified" stamp: date, time with the Eastern time zone, and a verification code. Every signer initials each page they sign, on the page footer or in the rider header.

| Stage | Offer (contract, riders, addenda) | Counters (CO-3) | Amendments | Effective Date |
|---|---|---|---|---|
| `offer` | Buyers only | None | None | None: the offer is pending |
| `countered` | Buyers (sellers too with `seller_signs_offer`) | Each counter by its maker; the last one by the other side only when `accepted` | None | The last counter's acceptance, or none while it's pending |
| `executed` | Buyers, then sellers at acceptance when there's no counter | As above, the last one accepted | None | The last signature on the final document |
| `amended` | As executed | As executed | Both sides on their date (or one side with `signed`) | As executed |

Some documents are signed out of that order, as they are in practice:

- The seller completes Rider P's disclosure (initials, checkboxes and signature) 12 days before the offer, and the buyer acknowledges it at the offer.
- The seller signs the other disclosures two weeks before the offer, and the buyer acknowledges them just before signing the offer.
- The buyer signs RCD-8 when the condo documents arrive. The seller signs NMOB-1 when calling for highest and best, and the buyer acknowledges it the day before the offer.
- Licensees sign Riders E and P next to their clients.
- Generated letters carry their issuer's signature, not the parties'.

## Defects

Defects make packages with the flaws the skills should catch. Each one is recorded in the answer key's `mock.defects` with where it landed.

| Defect | What it does |
|---|---|
| `missing-initials` | One signer's initials left off one page of the contract (default: the seller on an accepted contract, else the buyer; page 4) |
| `missing-signature` | One signer's signature and its date left off the contract |
| `blank-default` | Deposit, loan, inspection and title day blanks left empty, so the printed defaults apply (the key uses them) |
| `rider-conflict` | A rider the form doesn't allow: K on AS IS, or K and L together on Standard |
| `missing-disclosure` | A rider the property's facts require left out (P, A, B or E); if none is required, the flood disclosure (FD-2) that every residential sale needs |
| `unchecked-rider` | A rider attached but not checked in Para. 19 |
| `unattached-rider` | A rider checked in Para. 19 but not attached |
| `late-compensation-agreement` | Rider GG's compensation agreement signed 1 or 2 days after its window (needs GG on an accepted contract) |

## Outputs

In `out/mock-contracts/<id>/`:

- **`<Street>-Offer.pdf` or `<Street>-Contract.pdf`** (always): the package in the order the documents change hands ([Package Contents](#package-contents)). The form text stays real text and the filled values are typed as text, so `pdftotext -layout` reads both, as it does on an agent's Dotloop export.
- **`<Street>-Compensation-Agreement.pdf`** (with Rider GG): the CASSB-1 compensation agreement, on its own.
- **`key/<Street>-Answer-Key.json`** (`--answer-key`): the ground truth, shaped for the skill that reads that stage.
  - **Executed or amended** (`executed`, `amended`): contract-timeline's deal-file schema (`skills/contract-timeline/references/deal-file.md` and `frbar.md`). It holds `side`, `state`, `county`, `client`, `contract` (the contract as finally accepted, with the rider names), `deadlines` and `amendments` (each with its `changes`). `skills/contract-timeline/scripts/render.py` renders it directly.
    - With addenda it adds `contract.addenda` (their names). An Appraisal Gap Addendum adds two `deadlines` entries (valuation due, renegotiation ends), since contract-timeline sets no row of its own for AGA-1.
    - For a condo it adds `condo` and `condo_docs_received` (the RCD-8 date). For an HOA it adds `hoa` with `hoa_disclosure_before_contract`. Association approval comes from Riders A and B.
  - **Not accepted yet** (`offer`, or `countered` with the counter pending): seller-offer-review's listing file (`skills/seller-offer-review/references/listing-file.md`), since an offer isn't a contract and contract-timeline takes only an executed one.
    - It holds `analysis_date`, `listing` (address, county, `list_price`, year built, type, whether the flood disclosure was given), `seller` and one entry in `offers[]` with the offer as written, in that file's field names. Fields include the price, financing, down payment, lender and `approval` from the pre-approval or proof of funds, the deposit, days, riders, `buyer_broker_form` and percent, the appraisal gap and any escalation.
    - A pending counter changes nothing yet; it's listed in `mock.counters`.
    - `skills/seller-offer-review/scripts/render.py` renders it directly.
    - Handing this package to contract-timeline is itself a test: the skill should say the contract isn't executed yet.
  - **The `mock` block** (every stage) holds:
    - the stage, how the buyer's broker is paid (`buyer_broker`), and the compensation agreement's signing (`compensation_agreement`);
    - the escrow receipts (`deposits_received`) and a dropped disclosure (`dropped_disclosure`);
    - the documents in order, whether the offer is accepted and what's pending, and every counter with its date and terms;
    - the defects with where they landed, and a rider dropped, unattached or unchecked;
    - the property facts and the build notes.
- **`<Street>-...-Scanned.pdf`** (`--scanned`): the image-only copy.
- **`key/<Street>-Spec.json`** (always): the spec that built the package.

The key and spec sit in `key/`, apart from the documents, and are named after the property. So copying a package's PDFs into an eval run never brings the answers along, and keys from several packages never overwrite each other. To test a skill: build with `--answer-key`, copy the PDFs (never `key/`) into an eval run's `inputs/` (under `out/evals/`), run the eval per [development.md](development.md#evals), and grade what the skill read against the key: contract-timeline against an executed package's deal file, seller-offer-review against an offer's listing file.

## Field Maps

A field map, `dev/mock_contracts/fields/<FAMILY>.json`, names the blanks of one form and says what goes in each. Maps exist for FRBAR-ASIS, FRBAR-STANDARD, Riders A, B, C, D, E, F, FF, G, GG, H, K, L, N, P, S, T, U, V, W, X and Z, AGA, EAC, CDDA, NMOB, CCCLA, CO, EA, ACSP, SPDR, SPDC, FD, RCD, MISIRS and CASSB. On disclosures, the yes/no answer engine fills every question the map doesn't. Every other form gets only the automatic blanks until someone maps it.

**How blanks are found.** `locate.py` reads each page with PyMuPDF. It takes the Dotloop field outlines left in the export, drawn rules, underscore runs, checkbox squares and box glyphs, and text areas. Each blank gets an id:

- **`L27`, `L30.2`** on the contracts: from the printed line number in the margin, left to right. These ids are stable.
- **`P3.BI1`, `P3.SI2`**: the buyers' and sellers' initials slots on page 3.
- **`P1.7`** on forms without line numbers: the seventh blank on page 1 in reading order. These ids shift when detection changes, so maps for those forms use text anchors instead.

**Automatic blanks** on any form, found by their printed labels: the seller and buyer names (the blank before `("Seller")` or after "and"), the property ("described as", "located at"), an addendum's Effective Date ("Effective Date of"), signature and date boxes ("Buyer:" and "Date:", "Seller: [signature] / [print] Date:", or captions like `BUYER ... Date` printed under the line), the printed name next to a signature, and the initials slots (page footers, rider headers, and "Seller [ ][ ] and Buyer [ ][ ] acknowledge receipt" lines).

**Map format:**

```json
{"family": "CR-7_E", "revision": "CR-7 Rev. 10/21",
 "fields": {
   "repair_cap": {"at": {"label": "Repairs shall not exceed"}, "value": "money(v.repair_cap)"},
   "fha": {"at": {"after": "(CHECK IF APPLICABLE): FHA"}, "check": "financing == 'fha'"},
   "term_text": {"at": {"within": [105, 400, 580, 595], "page": 1, "all": true}, "rows": "[t['text'] for t in v.terms]"}},
 "roles": {
   "sign:buyer_agent": {"above": "BROKER", "page": 2, "nth": 0, "part": [0, 0.64]}}}
```

- **`at`**: a blank id, a list of anchors for text that flows across lines (every one must match, so a stale id stops the build instead of leaving a gap), or an anchor object:
  - `{"label": "..."}`: the blank whose text to its left ends with this.
  - `{"after": "..."}`: the blank whose text to its right starts with this.
  - `{"above": "BUYER"}`: the blank with this short caption printed under it.
  - `{"within": [x0, y0, x1, y1]}`: blanks centered in that page area, in points.
  - Narrow with `page`, `kind` (`line`, `field`, `area`, `check`), `nth` (0-based) and `all`, and `part: [0, 0.6]` for the left 60% of a blank. `{"at": "P2.1", "part": [...]}` narrows an id.
- **`value`**: a Python expression. It sees the scenario (`price`, `financing`, `riders`, `closing_date` and the rest; see `scenario.py`), `v` (this document's own values from the spec), and the helpers `money`, `mdy` and `when`. `None` or `""` leaves the blank empty.
- **`check`**: an expression; the box is checked when it's true.
- **`rows`**: an expression returning a list; each item goes in the next blank.
- **`roles`**: signature, date and initials slots the automatic detection misses, or overrides of it:
  - `sign:buyer`, `date:seller` and the like.
  - `sign:buyer_agent` and `sign:listing_agent`: licensees who sign next to their clients.
  - `initials:seller:1`: in-body initials for the first seller.

### The Value Guard

Every value a spec gives a rider, addendum, disclosure, counter or amendment must be one its form's map prints: a `v.<key>` in one of the map's `value`, `check` or `rows` expressions. Anything else stops the build before a page is drawn:

```
Rider U: rent_back_deposit has no blank in fields/CR-7_U.json. Mapped keys: expense, post_closing_agreement_days_before, rent_back_days, rent_back_monthly. Map the blank (docs/mock-contracts.md#field-maps) or drop the value.
```

- **A typo** gets the same error: fix the key.
- **A form with no map** refuses every value ("CR-7_M has no field map yet"). Its parties, property, signatures and initials still fill automatically.
- **Exempt keys** say how the document is built, not what it prints: `code`, `form`, `name`, `fill`, `answers`, `default_answer`, `date`, `signed`, `number` and `description`, plus a counter's `by`, `accepted`, `changes`, `seller_signs_offer` and `method`.
- **Printed on another form:** Rider GG also takes the compensation agreement's keys (CASSB-1 prints them), and Rider A's `community` names the condo on RCD-8.

To use a value the guard refuses, map its blank (below) or put it in `fill` by blank id.

**Adding a map for a new form.**

1. Run `locate.py FAMILY --draft` and `--debug out/mock-contracts/_drafts/FAMILY.pdf`, and look at the pages.
2. Write `fields/FAMILY.json` with the form's revision from the manifest. Prefer `label`, `after` and `above` anchors, then `within`, and ids only on the contracts. An anchor is matched against the text `locate.py` prints, which is cut to about 30 characters on each side: keep anchors short. Name each value key after the field the reading skill uses (`skills/contract-timeline/references/frbar.md`, `skills/seller-offer-review/references/listing-file.md`), so the key feeds it directly. A rider's days and dates reach the key on their own; a yes/no box the deal file reads goes in `DEAL_FLAGS` in `scenario.py`.
3. Render `--debug` again (mapped blanks show in red with their names), build a scenario that uses the form, and look at the filled page.
4. Add the form to `ROUND_TRIP` in `dev/tests/test_mock_contracts.py`, with a sample value for every key the map prints, and run `make test`. It checks that every anchor in every map still finds its blank, that the samples cover every key the map reads, and that each sample value is typed on the form.

## When a Form Is Revised

A map records the revision it was built for. When `make forms-check ARGS="--accept FAMILY"` records a new revision, building with that form stops: `fields/FAMILY.json was built for ...`. Re-anchor the map against the new PDF with `locate.py --debug`, update its `revision`, and run `make test` and `make mock-contracts`. Contract line numbers usually move between revisions, so check every `L` id. This is part of [Updating a Contract Form](development.md#updating-a-contract-form).

## Troubleshooting

- **`ModuleNotFoundError: pymupdf`:** run `.venv/bin/python -m pip install -r dev/requirements-tools.txt`.
- **"... is missing. The FR/BAR PDFs live in the git-ignored sources/":** copy the forms into `sources/Contracts/FARBAR/`, then run `make forms-check`.
- **"... has no blank in fields/...":** the value guard. Map the blank, put the value in `fill`, or drop it ([The Value Guard](#the-value-guard)).
- **"no blank matches ...":** an anchor lost its blank, after a detection change or a new revision. Run `locate.py FAMILY --debug` and fix the anchor.
- **Text in the wrong place, or too small:** the blank is narrower than the value. Use a shorter value, flow it across several blanks (`at` as a list), or narrow the anchor. Values shrink to fit down to 5.5 points.
- **A signature landed on the wrong line:** a caption anchor (`above`) matched a sentence. Captions must be four words or fewer; narrow the anchor with `page`, `nth` or `within`.
