---
name: mock-contract
description: Development only (this repo, Claude Code). Builds a realistic mock FR/BAR contract package as one PDF (the AS IS or Standard contract with its riders, addenda, counter offers and amendments, filled in and signed Dotloop-style) at any stage, from a buyer-signed offer to an executed or amended contract, from a scenario described in chat or in a file. Optionally writes an answer key (a contract-timeline deal file once executed, a seller-offer-review listing file before), a scanned image-only copy, and deliberate defects (missing initials, conflicting or unattached riders, blanks left to defaults). Use it whenever the user asks for a mock, fake, sample or test contract, a contract package or PDF to test the contract skills with, "an executed AS IS with riders E and H", "a countered Standard contract", "an offer package with an appraisal gap", or a contract with specific defects. Never shipped; outputs stay in out/mock-contracts/.
---

# Mock Contract

Builds mock FR/BAR contract packages for testing the contract-reading skills. The full reference (spec keys, flags, stages, defects, field maps) is [docs/mock-contracts.md](../../../docs/mock-contracts.md): read the sections you need before writing a spec.

## Guardrails

- **Fictional data only.** Never put a real person, brokerage, street address, MLS number or tax ID in a spec, even if the user pastes one from a real deal: swap in made-up values and say so. Real cities, ZIP codes and counties are fine with a made-up street.
- **FR/BAR only.** Only the forms in `dev/forms/frbar-forms.json` have PDFs. Another state's contract, a builder's form or CRSP can't be built. Say so, and don't fake one.
- **Never default the contract form.** Ask AS IS or Standard when the user doesn't say.
- **The rules come from `shared/contract_forms.py`.** If the builder refuses a rider combination, pass the reason on. Build it only if the user wants that flaw (the `rider-conflict` defect).
- **Outputs stay in `out/mock-contracts/`.** Never write mock PDFs into `skills/`, `samples/`, `dev/evals/` or anywhere else that's committed: they contain Florida Realtors' form text. Specs may be committed in `dev/mock_contracts/scenarios/` when the user asks to keep one.

## Steps

1. **Check the tools.** `.venv/bin/python -c "import pymupdf"` must work, and `sources/Contracts/FARBAR/` must exist. If not, give the fix from the doc's Setup section and stop.
2. **Read the scenario.** It comes from the chat, a file, or both. A file can be a spec, a contract-timeline deal file or fixture (see the mapping below), an offer JSON, or a markdown term sheet.
3. **Turn it into a spec** per the doc's Scenario Spec section.
   - Only `form` is required. Ask one short question if the form is missing, or if the stage is truly unclear ("executed" is the default). Don't ask about anything the defaults cover.
   - Put what the user said in the spec. Let the builder add the riders the facts require (P before 1978, A condo, B HOA, E FHA/VA, V sale of home); it reports them in its notes.
   - The package holds what the two sides exchange at that stage (the doc's Package Contents section): the seller's disclosures and the buyer's pre-approval or proof of funds with the offer, then escrow receipts after acceptance. Set property facts (`cdd`, `sinkhole_claim`, `coastal`, `flood_zone`, a condo `unit`) rather than listing forms, and use `package.include` or `package.exclude` for anything else. Put disclosure answers the user states in `disclosures` (`{"SPDR": {"answers": {"roof": "yes"}}}`). Never add brokerage notices, inspection or appraisal reports.
   - Buyer's broker compensation is always in the package: Rider GG with a broker-to-broker compensation agreement by default. With GG the builder also writes the CASSB-1 agreement as a separate `<Street>-Compensation-Agreement.pdf`, executed after the Effective Date and inside GG's window (a draft signed by the buyer's broker when the offer isn't accepted yet); report it as its own file. Set `buyer_broker` only when the user says otherwise: `{"form": "GG", "between": "seller", "amount": 9500}`, `{"form": "FF", "percent": 2.5}` for a credit to the buyer, or `"none"` when the test is a package without it.
   - Put terms that have no blank of their own in `additional_terms`, in a counter's `terms`, or in an ACSP amendment's `text`.
   - A seller who "countered on the contract", "marked up the contract" or "initialed the changes" is `"method": "contract"` on the first counter (the seller's only). Otherwise counters are CO-3s.
   - Leave `name` out: the builder names the folder from the street, stage and a hash of the spec, so scenarios never collide. Set a short kebab-case `name` only when the user wants to keep the scenario as a starter.
4. **Map any form that needs it.** A form with no `dev/mock_contracts/fields/<FAMILY>.json` still gets its parties, property, signatures and initials. If the scenario needs its other blanks:
   - Run `locate.py <FAMILY>` (add `--debug out/mock-contracts/_drafts/<FAMILY>.pdf` and look at the page).
   - Either set the blanks by id in that document's `fill`, for a one-off, or write a map per the doc's Field Maps section and save it, so the next scenario has it.
5. **Write and build.**
   - Write the spec to `out/mock-contracts/_specs/<anything>.json` (the builder copies it into the package's `key/` folder), or to `dev/mock_contracts/scenarios/<name>.json` if the user wants to keep it.
   - Run `.venv/bin/python dev/mock_contracts/build.py <spec> [--answer-key] [--scanned] [--defects a,b]`, adding only the flags the user asked for. The default output is the PDF alone.
   - On an error, fix the spec or the map and run it again. A `ScenarioError` is written to be passed to the user as is.
   - "`<key>` has no blank in fields/`<FAMILY>`.json" (or "has no field map yet") is the value guard: every value in the answer key must be printed on the PDF. If the user asked for that value, map its blank (step 4) and build again; if it was a typo or a guess, fix or drop it. Never silence it by moving the value somewhere the key doesn't read.
6. **Look at it.** The builder prints the package path; its folder is FOLDER below. Render the pages that changed (the contract's first page, its signature page: index 12 on AS IS, 13 on Standard, each rider or addendum you filled by hand) to PNG and view them:

   ```bash
   .venv/bin/python -c "import pymupdf; d = pymupdf.open('PDF'); [d[i].get_pixmap(dpi=110).save(f'FOLDER/p{i + 1}.png') for i in (0, 12)]"
   ```

   Struck values and initials stamps are small: crop to the area (`clip=pymupdf.Rect(...)`) at 150 to 200 dpi to read them.

   Check that the values sit on their blanks and the right parties signed. Fix any anchor that missed.
7. **Report.** Give:
   - the path to the PDF, and to the compensation agreement, key and scan if made. The key and spec are in `key/`: when copying a package into an eval's inputs, copy only the PDFs;
   - the documents in order, the stage, and who has signed what;
   - the Effective Date, or what's pending;
   - the riders the builder added and the defects injected;
   - any assumption you made.

   Keep it short. If you wrote a new field map, say so: it's a committed file.

## From a Deal File or Fixture

| Deal file (`contract.*`) | Spec |
|---|---|
| `contract_form` | `form` |
| `buyer`, `seller` (text) | `buyers`, `sellers` (split on " and ") |
| `property` | `property.address`; top-level `county` gives `property.county` |
| `price`, `financing` | `price`, `financing.type` |
| `effective_date`, `closing_date` | `dates.effective`, `dates.closing` |
| `deposit_days`, `deposit_amount_str` | `deposit.days`, `deposit.initial` |
| `additional_deposit_days`, `additional_deposit_amount_str` | `deposit.additional_days`, `deposit.additional` |
| `loan_application_days`, `loan_approval_days` | `financing.application_days`, `financing.approval_days` |
| `inspection_days`, `title_by`, `year_built`, `tenants` | same keys (`year_built` under `property`) |
| `riders` | `riders` |
| `amendments[]` | `amendments[]`: `date`; `changes.closing_date` becomes `closing`; a change in days becomes the extra days |

Use `stage: executed`, or `amended` when there are amendments. A key built from the result (`--answer-key`) should match the deal file on the fields above: compare them, and mention any difference.
