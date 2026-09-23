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
| `buyer-cma` | Buyer | CMA PDF |
| `seller-cma` | Listing | CMA PDF + listing presentation (PPTX) |
| `buyer-offer-strategy` | Buyer | Offer Options PDF + Offer Package Worksheet PDF |
| `seller-offer-review` | Listing | Single- or multi-offer review PDF |
| `contract-timeline` | Both | Contract timeline PDF |

## Planned

`lead-gen`, `content`, `social-media`, `research`.
