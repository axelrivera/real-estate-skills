# Plugins

## core

Profiles every other plugin reads as context. Markdown output only. Other plugins use these profiles when present and never require them.

| Skill | Produces |
|---|---|
| `agent-profile` | Agent profile: name and brokerage (required); team, license, contact, voice, disclaimers, brand colors (optional) |
| `market-profile` | Market profile: state, MLS, costs, contract rules, MLS export format |

## transactions

Deal work from pricing through closing. Every skill has a markdown mode and a file mode.

| Skill | Side | File mode output |
|---|---|---|
| `buyer-cma` | Buyer | CMA PDF |
| `seller-cma` | Listing | CMA PDF + listing presentation (PPTX) |
| `buyer-offer-strategy` | Buyer | Offer Options PDF + Offer Package Worksheet PDF |
| `seller-offer-review` | Listing | Single- or multi-offer review PDF |
| `contract-timeline` | Both | Contract timeline PDF |

## Planned

`lead-gen`, `content`, `social-media`, `research`.
