# Skills

Every skill ships in one plugin, `real-estate` (`.claude-plugin/plugin.json` at the repo root), listed in the one-plugin marketplace `real-estate-skills`. New skills go in `skills/<skill>/`; there are no other plugins.

## Profile

Context every other skill reads. Markdown output only. Other skills use the profile when present and never require it. In Cowork it's saved as `profile.md` in the working folder ([architecture.md](architecture.md#saved-files)).

| Skill | Produces |
|---|---|
| `agent-profile` | `profile.md`, from a two-round interview (the basics, then look and sound): name and brokerage (required); team, license, contact, voice, disclaimers, brand colors from hex codes, a website or an image. Also `project-instructions.md` to paste into a claude.ai or Cowork Project, with the setup steps in chat. No markets or costs: every report takes those from the listing ([local costs](architecture.md#local-costs)) |

## Deal Work

From pricing through closing. Every skill has a markdown mode and a file mode.

| Skill | Side | File Mode Output |
|---|---|---|
| `buyer-cma` | Buyer | CMA PDF; Pricing Activity sheet (one landscape page, the scatter only, with or without the price) when asked; `.buyer.cma.json` handoff kept as a working file |
| `seller-cma` | Listing | CMA PDF; editable listing presentation (PPTX, same numbers, plus a PDF copy of the slides) when asked or accepted; Pricing Activity sheet (one landscape page, the scatter only, with or without the price) when asked; Competitive Position sheet (one landscape page: the homes for sale and under contract against the home at the recommended or the agent's price, with crosshairs) when asked; `.seller.cma.json` handoff kept as a working file |
| `seller-net-sheet` | Listing | One-page seller net sheet PDF at one to three prices (no CMA or offer needed): brokerage, transfer tax, title, prorations, credits and payoffs down to the cash at closing |
| `seller-market-timing` | Listing | Buying Pattern PDF (one landscape page): every closed sale in a neighborhood by month and sold price, from an MLS export of 12, 24 (default) or 36 months, with the busy season boxed, the busiest month marked and when to list. For the agent's listing conversation, no notes |
| `buyer-offer-strategy` | Buyer | Offer Options PDF + Offer Package Worksheet PDF (FAR/BAR contracts, riders and addenda fully supported; other contracts best effort, by entry name) |
| `seller-offer-review` | Listing | Single- or multi-offer review PDF (net sheets, counter, certainty, ranking; FAR/BAR fully supported, other contracts best effort) |
| `contract-timeline` | Both | Contract timeline PDF + closing calendar (`.ics`) (FAR/BAR contracts and every rider fully supported; other contracts best effort, from their own dates and rules) |

## Planned

Lead generation, content, social media and research skills. Proposed skills are in [roadmap.md](roadmap.md).
