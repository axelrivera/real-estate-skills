# Roadmap

New skills and scope decisions that aren't defects. Defects go in an audit and are tracked in [status.md](status.md). Each item keeps its ID from the audit that raised it, so history stays traceable. Build any new skill per [skill-guidelines.md](skill-guidelines.md) and [architecture.md](architecture.md), and add it to [skills.md](skills.md). Every skill ships in the one `real-estate` plugin.

## New Skills

| ID | Priority | Skill | Builds On |
|---|---|---|---|
| GAP-1 | High | `listing-copy`: MLS remarks, social posts, flyer copy | profile `voice`, `shared/prose.py`, `fair-housing.md`, MLS layer character limits |
| GAP-2 | High | `buyer-consultation`: plain-language buyer-broker agreement summary and fee conversation guide | profile, the deal's brokerage terms |
| GAP-3 | Medium | `repair-negotiation`: inspection repair request and response | contract-timeline's inspection deadline, FAR/BAR AS IS and Standard repair rules |
| GAP-4 | Low | `buyer-cash-to-close`: standalone, no CMA or offer needed (`seller-net-sheet` built 2026-10-01) | `shared/finance.py` (payments, loan taxes, buyer-broker shortfall) |
| GAP-5 | Medium | Transaction checklist and weekly client update emails | contract-timeline's data JSON |
| GAP-6 | Low | Active listing performance and price reduction review; seller disclosure prep | seller-cma, `shared/mls.py`; after the CMA and offer skills are stable |

### GAP-1: Listing Copy

The highest-volume writing task agents have, and the riskiest for fair housing. Writes MLS public remarks, social posts and flyer copy from the listing's facts, in the agent's voice, and runs every piece through the `prose.py` check before it's returned.

- **Enforces** the MLS layer's character limits (public remarks, private remarks), and never puts showing or commission terms in public remarks.
- **Open questions:** Should it also write alt text for listing photos? Which MLS limits beyond Stellar need a layer?

### GAP-2: Buyer Consultation

After the 2024 NAR settlement, a written buyer agreement is required before touring. This skill reads the agent's profile and produces a plain-language summary of the agent's agreement (term, fee, who may pay it, how to end it) and a guide for the fee conversation.

- **Guardrails:** no legal advice; it summarizes the agent's own form, and the buyer is told to read the agreement itself. Commissions are negotiable and not set by law.
- **Open questions:** Which agreement forms are built in (the FAR/BAR exclusive buyer brokerage agreement first)? Should it produce a one-page PDF for the buyer?

### GAP-3: Repair Negotiation

Drafts the repair request or the response to one, with the contract math: under FAR/BAR AS IS, cancel or ask for a credit; under the Standard contract, the General Repair, WDO and Permit Limits (Para. 9(a), 1.5% of price each if blank), the seller's 10-day estimate window and the 5-day election when repairs exceed a limit (Para. 12). contract-timeline already dates those windows. Reads contract-timeline's data for the inspection deadline when present. Florida Realtors' Buyer's Request for Repairs and/or Remedies (BRR-1) is the Standard form's repair notice and is described in `shared/references/farbar-addenda.md`; Rider L (right to inspect and cancel) keeps the same repair process.

- **Open questions:** Should it read an inspection report PDF and extract the items, or take a list? Should it show a credit-vs-repair comparison?

### GAP-4: Standalone Cash to Close

The seller half, `seller-net-sheet`, was built on 2026-10-01. The buyer half stays here at a lower priority: the lender's Loan Estimate is the official cash-to-close figure, and buyer-cma and buyer-offer-strategy already show cash to close for their scenarios.

- **Before building it,** merge the two buyer closing-cost estimates into one shared function: buyer-cma's `buyer_closing_costs` (`compute.py`) and buyer-offer-strategy's `closing_costs` / `buyer_cash` (`strategy.py`) estimate differently today (prepaids and the cash-buyer share are only in the strategy).
- **Same shape as the seller net sheet:** a data JSON, a markdown template and a one-page PDF.

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
| | More state market layers | Only Florida is built in. Texas is the most-tested non-Florida market case in the fixtures (costs only: no other state's contract rules are built in; contracts outside FAR/BAR are best effort). |
| | More fully supported contracts | A contract becomes fully supported only through the same process as FAR/BAR: its PDFs in `sources/`, the manifest, `make forms-check`, and references read from the forms. |
| | More MLS layers | Only Stellar is built in. Miami (MIAMI REALTORS) and BeachesMLS cover the southeast Florida counties Stellar doesn't. |
| | Offer outcome log | Ported from the prototype: record how offers turned out to calibrate scoring. |
| | Trigger-description optimization | skill-creator's `run_loop`, run in Claude Code. |

## Dev Tooling

| ID | Item | Notes |
|---|---|---|
| | Release workflow | A GitHub Action (`.github/workflows/release.yml`) that builds `make package` on a clean runner and creates the GitHub release with the release zip only. Trigger on a `v*` tag push or on a `plugin.json` version change in `main`; fail if the tag and version differ. Needs `permissions: contents: write` and a `make setup` that works on Ubuntu (Node from `.nvmrc`); if that's heavy, call `dev/package.py plugin` and leave the checks to the pull request. Until then, releases are made by hand with `gh release create` ([development.md](development.md)). |
