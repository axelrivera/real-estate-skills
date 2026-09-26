# Skills

Every skill ships in one plugin, `real-estate` (`.claude-plugin/plugin.json` at the repo root), listed in the one-plugin marketplace `real-estate-skills`. New skills go in `skills/<skill>/`; there are no other plugins.

## Profile

Context every other skill reads. Markdown output only. Other skills use the profile when present and never require it. In Cowork it's saved in `.claude/real-estate/` in the working folder ([architecture.md](architecture.md#saved-files)).

| Skill | Produces |
|---|---|
| `agent-profile` | `profile.md`, from a two-round interview (the basics, then look and sound): name and brokerage (required); team, license, contact, voice, disclaimers, brand colors from hex codes, a website or an image. Also `project-instructions.md` to paste into a claude.ai or Cowork Project, with the setup steps in chat. No markets or costs: every report takes those from the listing ([local costs](architecture.md#local-costs)) |

## Deal Work

From pricing through closing. Every skill has a markdown mode and a file mode.

| Skill | Side | File Mode Output |
|---|---|---|
| `buyer-cma` | Buyer | CMA PDF + `.buyer.cma.json` handoff |
| `seller-cma` | Listing | CMA PDF; editable listing presentation (PPTX, same numbers, plus a PDF copy of the slides) when asked or accepted; `.seller.cma.json` handoff kept as a working file |
| `buyer-offer-strategy` | Buyer | Offer Options PDF + Offer Package Worksheet PDF (FR/BAR built in; other contracts by entry name) |
| `seller-offer-review` | Listing | Single- or multi-offer review PDF (net sheets, counter, certainty, ranking) |
| `contract-timeline` | Both | Contract timeline PDF + closing calendar (`.ics`) (FR/BAR built in; other contracts from their own dates and rules) |

## Planned

Lead generation, content, social media and research skills. Proposed skills are in [roadmap.md](roadmap.md).
