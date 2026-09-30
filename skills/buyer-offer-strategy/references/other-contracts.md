# Other Contracts (Best Effort)

Read this for any purchase contract that isn't the Florida Realtors/Florida Bar AS IS or Standard form: another state's form, a builder or bank contract, an attorney-drafted agreement, or a Florida form other than FR/BAR (the Florida Realtors CRSP, Vacant Land). Only the FR/BAR forms are fully supported, because only they have been checked line by line. Every other contract is read on a best-effort basis: you read it, the scripts do the math on what you recorded, and the agent confirms your reading.

## Contents

- The Rules
- 1. Identify the Form
- 2. Time Rules
- 3. Terms by Function
- 4. Recording It
- 5. Confirm and Disclose

## The Rules

- **No borrowed defaults.** A blank in another contract never takes an FR/BAR default (15-day inspection, 1.5% repair limits, 3-day deposit) or a default you remember from some other form. Use only a default the contract itself prints ("if left blank, then..."). Otherwise ask the agent, or record the reading as a high-impact assumption.
- **No built-in state rules.** The skills carry no rules for any other state's forms. Time rules, holidays, deadlines and cancel rights come only from the contract in front of you and from the agent.
- **Cite the contract.** Every term you record names the paragraph or section it came from, in the contract's own numbering.
- **Ask, don't guess.** When the contract is silent or unclear on something that moves a date or money (whether an inspection period lets the buyer cancel for any reason, whether a period counts business days), ask the agent in one line, or record your reading as a high-impact assumption and say so.
- **Quick questions give both counts.** When a quick date question doesn't say whether the period counts calendar or business days and the contract isn't in hand, answer with both dates and say which one the contract decides.

## 1. Identify the Form

Record the form's name and version exactly as printed (title, form number, revision date in the footer) in the data file's form name field. If there's no printed form name (an attorney-drafted contract), say so and use a short description ("Attorney-Drafted Purchase Agreement"). If a Florida contract turns out to be FR/BAR after all (the footer reads FloridaRealtors/FloridaBar), switch to the FR/BAR path.

## 2. Time Rules

Find where the contract defines time (a "Time", "Computation of Time", "Days" or "Definitions" paragraph):

- Are days calendar days or business days? Do short periods (a few days or less) skip weekends?
- When does a day end (5:00 PM, 11:59 PM, "local time" where the property is)?
- What happens when a period ends on a weekend or holiday: extended to the next business day, or not? Does that apply to every deadline or only some?
- Which holidays count? The federal list, a list the contract defines, or none?
- Dates counted back from closing: does a weekend move them earlier, later, or not at all?

Record what the contract says. When it's silent on one of these, ask the agent; don't assume Florida's rules, because that's what quietly moves a deadline by a day. If a single deadline has its own time or rollover rule (a period that ends at 5:00 PM on its last day and is never extended), record it on that deadline rather than for the whole contract.

The contract timeline needs only how days are counted (`day_count`) to run. Leave out any other rule you haven't read or been told: the script uses the neutral reading until the agent answers (nothing skipped or moved, the federal holidays, no time of day on the dates), lists each open rule in an agent note, and the report marks it "to confirm". Never fill one in to make the run work.

## 3. Terms by Function

Look for each of these by what it does, not by what a given state calls it:

| Function | What to Record | Often Called |
|---|---|---|
| Deposit | Amount, who holds it, due date or days, any later deposit | Earnest money, escrow deposit, good-faith deposit |
| Walk-away window | Days, from what event, and whether the buyer may cancel for **any reason** (a walk-away) or only for listed defects (a repair or objection process) | Inspection period, due diligence period, option period, contingency period |
| Repairs | Any seller repair obligation or cap, and the notice and response deadlines | Repair request, objection and resolution |
| Financing | Loan type and amount, application and approval deadlines, what happens if approval doesn't come | Loan contingency, financing addendum |
| Appraisal | Whether a low appraisal lets the buyer cancel or renegotiate, and until when | Appraisal contingency or addendum, part of the financing terms |
| Title and survey | Who orders and pays for title, when the commitment is due, objection and cure periods | Title policy, title objections |
| Disclosures and association documents | What the seller delivers, when, and any buyer review or cancel period | Seller disclosure, HOA or condo resale documents |
| Sale of the buyer's home | Days or date, and any kick-out right | Sale contingency, kick-out |
| Closing and possession | Closing date and time, possession at or after closing, any rent-back | Closing, settlement, possession |
| Costs | Who pays transfer taxes, title, fees, concessions | Closing costs, seller contributions |
| Addenda and counteroffers | Every one, in signing order; later documents override earlier ones | Addendum, amendment, counter |

Handwritten or initialed changes override typed text; flag anything illegible instead of guessing.

## 4. Recording It

- **Contract timeline:** set `"form_family": "other"`, `"form"` to the form name, and one `deadlines` entry per date the contract creates, using the contract's own words for `label` (Title Case), `action` and `if_missed`, and its paragraph numbers for `source`. Put the time rules in `rules`. Mark `contingency: true` only on buyer protections that end on that date. A period that runs from someone's receipt gets `receipt_date` and `what`. Formats are in `deal-file.md`.
- **Seller offer review:** set `contract_form` to the form's name (never `standard`, which means the FR/BAR Standard form and its repair limits) and `inspection_days` to the walk-away window. Set `inspection_walkaway` from the contract: `true` when the buyer may cancel for any reason in it, `false` for a repair or objection process only. If you can't tell, leave it out: the engine assumes a walk-away (the cautious reading for the seller) and flags it as high impact.
- **Buyer offer strategy:** set `worksheet.contract_name` to the form's name. The worksheet lists entries by name with no paragraph numbers and generic addendum names; walk the agent through where each goes in their form, and ask before adding anything their form set doesn't have.
- **Costs** aren't contract rules: they follow `local-costs.md` (a looked-up transfer tax, else labeled national estimates).

## 5. Confirm and Disclose

- **Quick question** about one date: answer, and state in the same reply the rule you used and the reading to confirm ("7 days after Nov 20, ending 5:00 PM, not extended; confirm your form says the same").
- **Full timeline or review:** before running, list the key readings back to the agent in plain words ("Due diligence: 7 days after the Effective Date, ends Nov 27 at 5 PM; buyer may cancel for any reason") and ask them to confirm. Anything you had to interpret goes in the notes.
- **Chat disclaimer.** The scripts return `support: "best_effort"` and the line to use in `chat_notes` (only there: the timeline keeps it out of `agent_notes`, which can reach a markdown timeline). Say it once, in chat, in your own short words: only Florida FR/BAR contracts are fully supported, this contract was read on a best-effort basis, and the agent should check every date and term against the signed contract, with a real estate attorney licensed in the property's state for anything that matters. **Never put it in a PDF, calendar file, worksheet or markdown report:** those go to clients and into transaction files.
