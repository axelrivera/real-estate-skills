# Checking the Contract Before Reviewing It

Read this whenever a contract is uploaded. Before scoring an offer, check that the contract can be reviewed as written. Record what you find in the offer's `contract_issues` (see `listing-file.md`), except what the engine already raises from the fields (below). For a FAR/BAR contract, also run the full list in `farbar-package-check.md`: required riders and disclosures by the property's facts, RESERVED riders, and which blanks have form defaults.

## What the Engine Already Raises

Record the field and let the engine write these; don't add a `contract_issues` entry for them. If you do write one (to say something more specific), give it the `topic` below: the engine drops its own flag and keeps yours at the higher of the two levels.

| Topic | Raised When | Level |
|---|---|---|
| `expired` | `expires` is before `analysis_date` (with `expires_estimated`: likely passed); or it falls on `analysis_date` (it ends today) | Blocking (High when estimated or today) |
| `approval_cap` | the price is above `approval_max_price`, or the loan above `approval_max_loan` | High |
| `approval_expires` | the pre-approval letter expires before closing | Med |
| `proof_of_funds` | `proof_of_funds` is below the down payment plus the appraisal gap the buyer covers | High |
| `counter_chain` | the live offer is weaker than the seller's last counter in `prior_counters` on inspection, loan approval, deposit, concessions or gap, or has another closing date | High |
| `rider_E`, `rider_V`, `rider_F`, `rider_A`, `rider_B` | FHA/VA without Rider E; a sale contingency without Rider V; an appraisal period without Rider F (not for FAR/BAR Para. 8(b)); a condo without Rider A; an HOA without Rider A or B (every offer whose rider list was read; on FAR/BAR an unread list is an assumption instead, `listing-file.md`) | High (F: Med) |
| `rider_GG` | Rider GG attached: the compensation agreement isn't seen yet | Med |
| `rider_K_terms` | Rider K on the Standard form: it deletes the Para. 9(a) limits and Paras. 11 and 12, but not the 125% escrow, and has no permit cooperation clause (listed with the risk flags, never a top risk) | Low |
| `lead_paint` | built before 1978 (`year_built`, or `built_before_1978` from the seller disclosure) with no lead-based paint disclosure (Rider P) | High |
| `loan_amount` | `loan_amount` doesn't match the down payment; or the deposit, `loan_amount` and `balance_to_close` don't add up to the price (a counter changed the price without restating the loan and balance) | Med |
| `buyer_changes` | the buyer's counter changed a term from the buyer's original terms (the first `by: "buyer"` entry in `prior_counters`) that no seller counter stated: a later closing date, a longer period, a smaller deposit, more concessions | Med |
| `inspection_period` | an inspection period of 15 days or more | Med |
| `flood_disclosure` | the market requires the seller's flood disclosure and `listing.flood_disclosure` isn't `true` | Med |
| `hoa_conflict` | `listing.hoa_conflict` is set: the packages disagree on the HOA assessment. Raised on every offer, never on one alone | Low |

Also raised, with no topic because they have nothing to duplicate: rider risks (short sale, attorney approval, a sale contingency without a kick-out, an assessment with no payoff agreement, a mortgage assumption), AGA-1 conflicts (with Rider F; on an FHA, VA or USDA offer, which AGA-1 doesn't fit; a periods total that runs past closing, or ends within 3 days of it, `aga_window_at_closing`), a free-text pre-approval expiry (recorded as an assumption), FHA/VA condo approval, loan approval after closing, and the Standard form's repair limits.

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
- The time for acceptance has already passed (automatic from `expires`). State the fact (the offer's own deadline has passed), never whether it can still be accepted; a seller counter sets a new time for acceptance, so the reply may show what that counter could look like, labeled as reference.
- Two parts of the contract give different prices, deposits or financing and you can't tell which governs.

## High

- Blank lines that the form doesn't default: deposit amount, escrow agent, additional deposit due date, loan amount or type, closing date.
- A rider the terms call for isn't attached: FHA/VA financing, sale of the buyer's property, appraisal terms, HOA or condo.
- A required disclosure is missing: lead-based paint for homes built before 1978 (federal). In Florida, the HOA disclosure summary (without it the buyer may cancel within 3 days after receiving it) and the seller's flood disclosure (FD-2, s. 689.302, at or before signing; set `listing.flood_disclosure` once it's given).
- A condo: the condo rider, and for an FHA or VA offer the project's approval. The buyer's rescission windows start when they receive the association documents, the milestone summary and the SIRS, so deliver them right away (`condo.md`).
- The rider checklist and the attached riders disagree.
- **Delivery date unknown:** a deadline counted from delivery (a counteroffer "2 days after delivery" with no acceptance date) is counted from the signature date. Set `expires` to that date, with no time when the form names none (the engine reads it as the end of the day and lists the assumption), and `expires_estimated: true`: if it has passed, it's a High issue and a question for the buyer's agent (when was it delivered?), not Blocking.
- A counteroffer that doesn't restate a term from an earlier counter: under FAR/BAR CO-3 only what the counter states carries, so the original offer's term governs. Record the governing terms in the offer and the seller's counters in `prior_counters`; the engine raises it (`counter_chain`).

Some of these are the listing side's job (the seller's HOA and lead-paint disclosures): write the fix for the agent, and leave `request` out so it doesn't go to the buyer's agent.

## Med

- A seller disclosure that contradicts a rider or the listing (the seller's property disclosure says no HOA while Rider B is attached): the listing side's fix. Have the seller correct and initial the disclosure and deliver it to the buyer; no `request`.

## Blanks That Fall Back to the Form

A blank that the form fills in is not an issue: record the form's value and say so. FAR/BAR defaults (both forms and every rider) are listed in `farbar-package-check.md`. Any other contract: only a default the contract itself prints counts; otherwise it's a question (`other-contracts.md`).

## Consistency

- Deposit plus loan amount plus balance due at closing equals the price: record `balance_to_close` (Para. 2(e)) and the engine checks it.
- The loan amount matches the down payment.
- The loan approval and appraisal deadlines fall before closing.
- Additional terms don't contradict the main paragraphs (they usually govern: note which one you used).

## Writing an Issue

One short sentence for `issue` naming the paragraph or rider; `fix` says what gets it resolved (the listing side by role, "the listing broker", never a brokerage name the profile doesn't confirm); name each form by its plain name ("the compensation agreement", "the Appraisal Gap Addendum"), never by its code alone (CASSB-1, AGA-1): the reader is the seller; `request` is the sentence for the buyer's agent ("Please have the second buyer sign and initial every page."). Describe the document, never the buyer (fair housing).
