# Offer Package Worksheet: Entries, Riders, Additional Terms, Checklist

The worksheet turns the chosen option into what the agent types into the contract and assembles for the package. It contains offer terms only: never the buyer's max price, cash or reserve. Suggested clause language is a starting draft for the agent and broker, not legal advice.

## Florida (FR/BAR)

The worksheet follows the FR/BAR **AS IS** contract's paragraphs (1 parties and property, 2 price and deposits, 3 time for acceptance, 4 closing, 6 occupancy, 8 financing, 9 closing costs and title, 12 inspection). Paragraph numbers and rider titles change between revisions: verify against the current form in Form Simplicity.

- **AS IS** (default): the buyer can cancel for any reason during the inspection period; no seller repairs. The usual choice for competitive offers.
- **Standard:** seller repair obligations up to a repair limit. Only when the buyer asks (a well-kept home, soft market, no competition). Set `worksheet.contract_form: "standard"`.

## Other States

The worksheet lists the same entries by name with no paragraph numbers, because every state's form orders them differently. Put the form's name in `worksheet.contract_name` ("TREC One to Four Family Residential Contract (Resale)") so it prints. Walk the agent through where each entry goes in their form:

| Entry | Look For |
|---|---|
| Deposit | "Earnest money" and its due date (TX, CO, GA: often 1–3 days) |
| Walk-Away Window | Option period and option fee (TX), due-diligence period and fee (NC, GA), inspection contingency (most others) |
| Financing, Loan Approval | Financing addendum or loan contingency section |
| Title | "Title policy": who furnishes it varies by state and county |
| Texas (TREC) | Option fee and option period in Para. 5; financing on the Third Party Financing Addendum (loan approval, appraisal as a condition there), not a separate appraisal rider; earnest money due within 3 days. TREC has no escalation addendum: write escalation in Special Provisions only if the listing agent accepts it |

Rider names are generic outside Florida ("Appraisal Contingency Addendum"); map them to the state's forms. Ask the agent before adding anything their form set doesn't have.

## Riders: When Each Is Recommended

| Rider | Trigger | Suggested Inputs |
|---|---|---|
| FHA/VA Financing | financing fha or va | appraised-value threshold = price (amendatory / escape clause) |
| Appraisal Contingency | conventional or usda | value threshold = price; appraisal period (21 days); pair with gap language when there's a gap |
| HOA / Community Disclosure | `hoa_monthly` > 0 or `hoa_name` | association, dues, approval required, special assessments |
| Condominium | `property.type` = condo | association, approval, reserve study and milestone inspection status |
| Lead-Based Paint (Federal) | built before 1978 | disclosure and 10-day risk-assessment opportunity (buyer may waive) |
| Homeowners' / Flood Insurance | roof 15+ years, flood zone A/V, or no insurance quote yet (financed) | days to obtain coverage; max acceptable premium |
| Sale of Buyer's Property + Kick-Out | `buyer.needs_sale` | days, the buyer's address, 72-hour kick-out; warn that it weakens the offer |
| Back-Up Contract | `competition.backup` | — |
| Escalation Addendum | the chosen option escalates | increment, cap, proof of competing offer |
| CDD / Special District | `property.cdd` | annual amount and outstanding debt |
| Short Sale | `property.short_sale` | lender approval period |

## Additional Terms (Draft Language)

Only when they apply: seller-paid closing costs (unused amounts aren't paid to the buyer), appraisal gap (the buyer pays up to $X of any shortfall; beyond that the appraisal rider applies), seller-provided reports within 2 days (in Florida the 4-point and wind-mitigation reports speed up the insurance quote), escalation (only when the addendum isn't used).

## Package Checklist

Printed with blank Date / Notes columns; a box is checked when the buyer file's `checklist` says `Yes` or `Done`: contract completed and initialed; riders attached and signed; additional terms reviewed by the broker; pre-approval letter at the offer price (or proof of funds for cash); proof of funds for deposit, closing costs and gap; insurance quote; agency disclosure (Florida: brokerage relationship disclosure); buyer-broker agreement matching the compensation request; wire-fraud advisory; lead-based paint disclosure for pre-1978 homes; inspector booked inside the inspection period; lender confirms the closing timeline. **Never include** personal letters, photos or buyer background (fair housing).
