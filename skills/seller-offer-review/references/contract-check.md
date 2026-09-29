# Checking the Contract Before Reviewing It

Read this whenever a contract is uploaded. Before scoring an offer, check that the contract can be reviewed as written. Record what you find in the offer's `contract_issues` (see `listing-file.md`), except what the engine already raises from the fields (below). For an FR/BAR contract, also run the full list in `frbar-package-check.md`: required riders and disclosures by the property's facts, RESERVED riders, and which blanks have form defaults.

## What the Engine Already Raises

Record the field and let the engine write these; don't add a `contract_issues` entry for them. If you do write one (to say something more specific), give it the `topic` below: the engine drops its own flag and keeps yours at the higher of the two levels.

| Topic | Raised When | Level |
|---|---|---|
| `expired` | `expires` is before `analysis_date` (with `expires_estimated`: likely passed) | Blocking (High when estimated) |
| `approval_cap` | the price is above `approval_max_price`, or the loan above `approval_max_loan` | High |
| `approval_expires` | the pre-approval letter expires before closing | Med |
| `proof_of_funds` | `proof_of_funds` is below the down payment plus the appraisal gap the buyer covers | High |
| `counter_chain` | the live offer is weaker than the seller's last counter in `prior_counters` on inspection, loan approval, deposit, concessions or gap | High |
| `rider_E`, `rider_V`, `rider_F`, `rider_A`, `rider_B` | FHA/VA without Rider E; a sale contingency without Rider V; an appraisal period without Rider F (not for FR/BAR Para. 8(b)); a condo without Rider A; an HOA without Rider A or B (only when `riders` is listed) | High (F: Med) |
| `rider_GG` | Rider GG attached: the compensation agreement isn't seen yet | Med |
| `lead_paint` | built before 1978 with no lead-based paint disclosure (Rider P) | High |
| `loan_amount` | `loan_amount` doesn't match the down payment | Med |
| `inspection_period` | an inspection period of 15 days or more | Med |
| `flood_disclosure` | the market requires the seller's flood disclosure and `listing.flood_disclosure` isn't `true` | Med |

Also raised, with no topic because they have nothing to duplicate: rider risks (short sale, attorney approval, a sale contingency without a kick-out, an assessment with no payoff agreement, a mortgage assumption), AGA-1 conflicts, FHA/VA condo approval, loan approval after closing, and the Standard form's repair limits.

This is a completeness check, not a legal opinion. Never tell the agent a contract is or isn't binding; say it can't be reviewed as written, and point questions about validity to a real estate attorney licensed in the property's state.

## Severity

| Severity | Meaning | What the Report Does |
|---|---|---|
| **Blocking** | The contract can't be reviewed as written | No recommendation, counter, options or ranking. The review shows **CONTRACT INCOMPLETE**, what to fix, and the numbers as written for reference only |
| **High** | A required piece is missing or wrong, but the terms can still be read | A risk flag, a request to the buyer's agent, a note on the checklist |
| **Med** / **Low** | Worth fixing in the counter or before closing | A risk flag |

## Blocking

- A buyer named in the contract hasn't signed, or a signature page is missing.
- Pages are missing, or a rider the contract says is attached isn't there.
- The purchase price, the property or the parties are blank or don't match the listing.
- Handwritten or struck changes aren't initialed by every buyer.
- The time for acceptance has already passed (automatic from `expires`). A seller counter with a new time for acceptance revives a lapsed offer, so the reply may show what that counter could look like, labeled as reference.
- Two parts of the contract give different prices, deposits or financing and you can't tell which governs.

## High

- Blank lines that the form doesn't default: deposit amount, escrow agent, additional deposit due date, loan amount or type, closing date.
- A rider the terms call for isn't attached: FHA/VA financing, sale of the buyer's property, appraisal terms, HOA or condo.
- A required disclosure is missing: lead-based paint for homes built before 1978 (federal). In Florida, the HOA disclosure summary (without it the buyer may cancel within 3 days after receiving it) and the seller's flood disclosure (FD-2, s. 689.302, at or before signing; set `listing.flood_disclosure` once it's given).
- A condo: the condo rider, and for an FHA or VA offer the project's approval. The buyer's rescission windows start when they receive the association documents, the milestone summary and the SIRS, so deliver them right away (`condo.md`).
- The rider checklist and the attached riders disagree.
- **Delivery date unknown:** a deadline counted from delivery (a counteroffer "2 days after delivery" with no acceptance date) is counted from the signature date. Set `expires` to that date and `expires_estimated: true`: if it has passed, it's a High issue and a question for the buyer's agent (when was it delivered?), not Blocking.
- A counteroffer that doesn't restate a term from an earlier counter: under FR/BAR CO-3 only what the counter states carries, so the original offer's term governs. Record the governing terms in the offer and the seller's counters in `prior_counters`; the engine raises it (`counter_chain`).

Some of these are the listing side's job (the seller's HOA and lead-paint disclosures): write the fix for the agent, and leave `request` out so it doesn't go to the buyer's agent.

## Med

- A seller disclosure that contradicts a rider or the listing (the seller's property disclosure says no HOA while Rider B is attached): the listing side's fix. Have the seller correct and initial the disclosure and deliver it to the buyer; no `request`.

## Blanks That Fall Back to the Form

A blank that the form fills in is not an issue: record the form's value and say so. FR/BAR defaults (both forms and every rider) are listed in `frbar-package-check.md`. Any other contract: only a default the contract itself prints counts; otherwise it's a question (`other-contracts.md`).

## Consistency

- Deposit plus loan amount plus balance due at closing equals the price.
- The loan amount matches the down payment.
- The loan approval and appraisal deadlines fall before closing.
- Additional terms don't contradict the main paragraphs (they usually govern: note which one you used).

## Writing an Issue

One short sentence for `issue` naming the paragraph or rider; `fix` says what gets it resolved; `request` is the sentence for the buyer's agent ("Please have the second buyer sign and initial every page."). Describe the document, never the buyer (fair housing).
