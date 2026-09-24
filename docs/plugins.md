# Plugins

## core

Profiles every other plugin reads as context. Markdown output only. Other plugins use these profiles when present and never require them.

| Skill | Produces |
|---|---|
| `agent-profile` | `agent-profile.md`: name and brokerage (required); team, license, contact, voice, disclaimers, brand colors from hex codes, a website or an image (optional) |
| `market-profile` | `market-profile-<area>.md`: only the agent's own values (closing costs, commission, taxes, contract rules, CMA, MLS format); everything else from the built-in Florida and Stellar layers |

## transactions

Deal work from pricing through closing. Every skill has a markdown mode and a file mode.

| Skill | Side | File mode output |
|---|---|---|
| `buyer-cma` | Buyer | CMA PDF + `.cma.json` handoff |
| `seller-cma` | Listing | CMA PDF + editable listing presentation (PPTX), same numbers, + `.cma.json` handoff |
| `buyer-offer-strategy` | Buyer | Offer Options PDF + Offer Package Worksheet PDF (FR/BAR built in; other contracts by entry name) |
| `seller-offer-review` | Listing | Single- or multi-offer review PDF (net sheets, counter, certainty, ranking) |
| `contract-timeline` | Both | Contract timeline PDF (FR/BAR built in; other contracts from their own dates and rules) |

## Planned

`lead-gen`, `content`, `social-media`, `research`. New skills proposed for any plugin are in [roadmap.md](roadmap.md).
