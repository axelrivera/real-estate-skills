# Roadmap

New skills and scope decisions that aren't defects. Defects go in an audit and are tracked in [status.md](status.md). Each item keeps its ID from the audit that raised it, so history stays traceable. Build any new skill per [skill-guidelines.md](skill-guidelines.md) and [architecture.md](architecture.md), and add it to [plugins.md](plugins.md) and the marketplace catalog.

## New Skills

| ID | Priority | Skill | Plugin | Builds On |
|---|---|---|---|---|
| GAP-1 | High | `listing-copy`: MLS remarks, social posts, flyer copy | `content` (planned) or a new `marketing` | agent profile `voice`, `shared/prose.py`, `fair-housing.md`, MLS layer character limits |
| GAP-2 | High | `buyer-consultation`: plain-language buyer-broker agreement summary and fee conversation guide | `transactions` | agent profile, market profile brokerage terms |
| GAP-3 | Medium | `repair-negotiation`: inspection repair request and response | `transactions` | contract-timeline's inspection deadline, FR/BAR AS IS and Standard repair rules |
| GAP-4 | Medium | `seller-net-sheet` and `buyer-cash-to-close`: standalone, no CMA or offer needed | `transactions` | `shared/finance.py` (`seller_net`, payments, proration) |
| GAP-5 | Medium | Transaction checklist and weekly client update emails | `transactions` | contract-timeline's data JSON |
| GAP-6 | Low | Active listing performance and price reduction review; seller disclosure prep | `transactions` | seller-cma, `shared/mls.py`; after the CMA and offer skills are stable |

### GAP-1: Listing Copy

The highest-volume writing task agents have, and the riskiest for fair housing. Writes MLS public remarks, social posts and flyer copy from the listing's facts, in the agent's voice, and runs every piece through the `prose.py` check before it's returned.

- **Enforces** the MLS layer's character limits (public remarks, private remarks), and never puts showing or commission terms in public remarks.
- **Open questions:** Should it live in the planned `content` plugin or a new `marketing` plugin? Should it also write alt text for listing photos? Which MLS limits beyond Stellar need a layer?

### GAP-2: Buyer Consultation

After the 2024 NAR settlement, a written buyer agreement is required before touring. This skill reads the agent profile and produces a plain-language summary of the agent's agreement (term, fee, who may pay it, how to end it) and a guide for the fee conversation.

- **Guardrails:** no legal advice; it summarizes the agent's own form, and the buyer is told to read the agreement itself. Commissions are negotiable and not set by law.
- **Open questions:** Which agreement forms are built in (the FR/BAR exclusive buyer brokerage agreement first)? Should it produce a one-page PDF for the buyer?

### GAP-3: Repair Negotiation

Drafts the repair request or the response to one, with the contract math: under FR/BAR AS IS, cancel or ask for a credit; under the Standard contract, the General Repair, WDO and Permit Limits (Para. 9(a), 1.5% of price each if blank), the seller's 10-day estimate window and the 5-day election when repairs exceed a limit (Para. 12). contract-timeline already dates those windows. Reads contract-timeline's data for the inspection deadline when present.

- **Open questions:** Should it read an inspection report PDF and extract the items, or take a list? Should it show a credit-vs-repair comparison?

### GAP-4: Standalone Net Sheet and Cash to Close

The two most-requested quick numbers, without building a CMA or reviewing an offer. Both are thin skills on `shared/finance.py`: a data JSON, a markdown template and a one-page PDF each.

- **Depends on** the audit's money-line fixes (tax proration with `tax_paid`, the buyer-broker shortfall line, Florida mortgage stamps and intangible tax, no built-in commissions).

### GAP-5: Transaction Checklist and Client Updates

Reads contract-timeline's data JSON and writes a to-do list per party and a weekly status email for the buyer or seller: what happened, what's next, and what they need to do.

- **Open questions:** Should it track which items are done (the agent updates the data file), or only look forward from today's date?

### GAP-6: Listing Performance and Disclosures

A review of an active listing's showings, days on market and competing listings, with a price-reduction recommendation, plus help preparing the seller's disclosure. Deferred until the CMA and offer skills are stable.

## Scope Extensions

| ID | Item | Notes |
|---|---|---|
| CORE-19 | Tiered and layered transfer taxes | NY mansion tax, WA REET tiers, NJ, LA Measure ULA, Philadelphia city plus state, DC. Support `deed_transfer_tax_tiers` (same format as title tiers) and a list of layered taxes. Until then the market check warns that tiered states need the agent's number. |
| CORE-30 | Rentals and leases | Security deposit rules (Florida s. 83.49), lease forms, lease fees, and leased and Active Under Contract MLS statuses. |
| | More state market layers | Only Florida is built in. Texas is the most-tested non-Florida case in the fixtures. |
| | More MLS layers | Only Stellar is built in. Miami (MIAMI REALTORS) and BeachesMLS cover the southeast Florida counties Stellar doesn't. |
| | Offer outcome log | Ported from the prototype: record how offers turned out to calibrate scoring. |
| | Trigger-description optimization | skill-creator's `run_loop`, run in Claude Code. |
