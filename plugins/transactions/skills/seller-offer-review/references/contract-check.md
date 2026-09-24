# Checking the Contract Before Reviewing It

Read this whenever a contract is uploaded. Before scoring an offer, check that the contract can be reviewed as written. Record what you find in the offer's `contract_issues` (see `listing-file.md`). The engine adds the checks it can prove from the fields itself: riders the terms call for, loan amount vs. down payment, loan approval after closing.

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
- The time for acceptance has already passed.
- Two parts of the contract give different prices, deposits or financing and you can't tell which governs.

## High

- Blank lines that the form doesn't default: deposit amount, escrow agent, additional deposit due date, loan amount or type, closing date.
- A rider the terms call for isn't attached: FHA/VA financing, sale of the buyer's property, appraisal terms, HOA or condo.
- A required disclosure is missing: lead-based paint for homes built before 1978 (federal). In Florida, the HOA disclosure summary; without it the buyer may cancel within 3 days.
- The rider checklist and the attached riders disagree.

Some of these are the listing side's job (the seller's HOA and lead-paint disclosures): write the fix for the agent, and leave `request` out so it doesn't go to the buyer's agent.

## Blanks That Fall Back to the Form

A blank that the form fills in is not an issue: record the form's value and say so. On the FR/BAR AS IS contract a blank inspection period is 15 days, and a blank loan approval period is the form default in Para. 8(b). Other states: check the form's own default language.

## Consistency

- Deposit plus loan amount plus balance due at closing equals the price.
- The loan amount matches the down payment.
- The loan approval and appraisal deadlines fall before closing.
- Additional terms don't contradict the main paragraphs (they usually govern: note which one you used).

## Writing an Issue

One short sentence for `issue` naming the paragraph or rider; `fix` says what gets it resolved; `request` is the sentence for the buyer's agent ("Please have the second buyer sign and initial every page."). Describe the document, never the buyer (fair housing).
