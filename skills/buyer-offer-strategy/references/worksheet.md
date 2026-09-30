# Offer Package Worksheet: Entries, Riders, Additional Terms, Checklist

The worksheet turns the chosen option into what the agent types into the contract and assembles for the package. It contains offer terms only: never the buyer's max price, cash or reserve. Suggested clause language is a starting draft for the agent and broker, not legal advice.

## Florida (FR/BAR)

The worksheet follows the FR/BAR contract's paragraphs (1 parties and property, 2 price and deposits, 3 time for acceptance, 4 closing, 6 occupancy, 8 financing, 9 closing costs and title, 12 inspection), checked against the revisions in `frbar-contract.md`. Riders are named by their CR-7 letter; what each one does, its blanks and defaults are in `frbar-riders.md`, and the addenda (AGA-1, EAC-1, CDDA-2) in `frbar-addenda.md`.

- **AS IS** (default): the buyer can cancel for any reason during the inspection period; no seller repairs. The usual choice for competitive offers.
- **Standard:** no inspection walk-away; the seller pays repairs up to the General Repair, WDO and Permit Limits (Para. 9(a), 1.5% of price each if blank; set others in `worksheet.repair_limits`). Only when the buyer asks (a well-kept home, soft market, no competition). Set `worksheet.contract_form: "standard"` **before** running: the options are scored on the same form the worksheet prints, so a changed form means a re-run. Riders I, K and L exist only for the Standard form; never add them to an AS IS offer.

## Other Contracts

Only FR/BAR is built in. For any other form, the worksheet lists the same entries by name with no paragraph numbers and generic addendum names. Put the form's name in `worksheet.contract_name` so it prints, read `other-contracts.md`, and walk the agent through where each entry goes in their form: deposit and its due date, the walk-away or inspection period and its notice rules, financing and appraisal terms, title. Ask before adding anything their form set doesn't have (an escalation clause, for example, only when the form and the listing agent allow it). The chat reply carries the best-effort line; the worksheet never does.

## Riders: When Each Is Recommended

| Rider (FR/BAR) | Trigger | Suggested Inputs |
|---|---|---|
| FHA/VA Financing Rider (E) | financing fha or va | appraised-value threshold = price; the Para. 2 seller's cap for lender-required appraisal repairs prints as a red blank (no default: a blank is ambiguous), with a note that on a contract that owes no other repairs it's new exposure for the seller |
| Appraisal Contingency Rider (F) | conventional or usda without AGA-1 (a USDA gap goes in Additional Terms with Rider F) | value threshold = price; appraisal date (blank = 10 days before closing, notice within 3 days after) |
| Appraisal Gap Addendum (AGA-1) | conventional or cash with an appraisal gap (the form's own scope: never FHA, VA or USDA) | Gap Amount; valuation days filled so AGA-1's periods (valuation + 3 + 3) end with the Loan Approval Period, or by closing for cash (30 days, the form's default, when that fits); 3 days to agree on new terms. Not used with Rider F |
| Homeowners' Association/Community Disclosure Rider (B) | `hoa_monthly` > 0 or `hoa_name` | association, dues, approval required, special assessments; the seller's disclosure summary before the buyer signs |
| Condominium Rider (A) | `property.type` = condo | association, approval, milestone inspection and SIRS status, documents requested |
| Lead-Based Paint Disclosure Rider (P) | built before 1978 | disclosure and 10-day risk-assessment opportunity (buyer may waive) |
| Homeowner's/Flood Insurance Rider (H) | roof 15+ years, flood zone A/V, or no insurance quote yet (financed) | premium caps; date (blank = the earlier of 30 days after the Effective Date or 10 days before closing) |
| Sale of Buyer's Property Rider (V) + Kick-Out Clause Rider (X) | `buyer.needs_sale` | the sale date (no default), the buyer's address, the kick-out deposit; warn that it weakens the offer |
| Back-Up Contract Rider (W) | `competition.backup` | the seller's notice date (no default) |
| Escalation Addendum (EAC-1) | the chosen option escalates | increment, cap, proof of competing offer |
| Community Development District Addendum (CDDA-2) | `property.cdd` | district name, annual amount and outstanding debt |
| Short Sale Approval Contingency Rider (G) | `property.short_sale` | approval deadline (90 days if blank) |
| Seller's Agreement with Respect to Buyer's Broker Compensation Rider (GG) | buyer-broker pay requested from the seller (default route) | who signs the compensation agreement; signed within 3 days. Doesn't use the loan's concession room |
| Credit Related to Buyer's Broker Compensation Rider (FF) | `buyer_broker_form: FF` | credit as a % of price; what happens over the lender's limit. Counts toward the concession limit with any closing-cost credit, so the options leave less room for concessions |

Other contracts get the same list with generic names ("Appraisal Contingency Addendum").

## Additional Terms (Draft Language)

Only when they apply: seller-paid closing costs (unused amounts aren't paid to the buyer), appraisal gap when AGA-1 doesn't apply (an FHA/VA offer, where it's stated intent only; a USDA offer, with Rider F; or another contract: the buyer pays up to $X of any shortfall; beyond that the appraisal protection applies), seller-provided reports within 2 days (in Florida the 4-point and wind-mitigation reports speed up the insurance quote), escalation (only when the addendum isn't used).

## Package Checklist

Printed with blank Date / Notes columns; a box is checked when the buyer file's `checklist` says `Yes` or `Done`: contract completed and initialed; riders attached and signed; additional terms reviewed by the broker; pre-approval letter at the offer price (or proof of funds for cash); proof of funds for deposit, closing costs and any appraisal gap; insurance quote; agency disclosure (Florida: brokerage relationship disclosure); buyer-broker agreement matching the compensation request; wire-fraud advisory; lead-based paint disclosure for pre-1978 homes; inspector booked inside the inspection period; lender confirms the closing timeline. **Never include** personal letters, photos or buyer background (fair housing): the Do Not Include row prints a cross, never a check. A cover note to the listing agent about the terms is the alternative (`fair-housing.md`).
