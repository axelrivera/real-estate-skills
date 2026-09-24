# Architecture

Decisions that apply to every plugin and skill in this marketplace.

## Runtimes

Skills run in the Claude **desktop app and cloud**: claude.ai chat and Cowork. Claude Code is not a supported runtime. Both runtimes run skills in the same Linux sandbox; see [runtime-support.md](runtime-support.md).

- A skill refers to its own files by paths relative to its skill directory (`scripts/render.py`).
- No paths outside the skill directory (`../../shared/`). Cowork installs plugins from the marketplace, and claude.ai uploads each skill on its own.
- No `/mnt/...` paths hard-coded in instructions. See [Output location](#output-location).
- Skill `description` must stay under 1,024 characters (claude.ai limit).

## Self-contained skills and shared code

Each skill directory is complete on its own. Code used by several skills is edited in one place and copied into each skill:

```
shared/                         # edit shared code here
shared/references/              # shared reference files (fair-housing.md), not code
plugins/<plugin>/skills/<skill>/
  scripts/_shared/              # copy made by the sync tool, never edit by hand
  references/fair-housing.md    # copy, only in skills whose SKILL.md points to it
dev/sync_shared.py              # make sync / make check-sync (also a pre-commit hook)
Makefile                        # make package: one zip per skill for claude.ai upload
```

A shared reference file is copied into a skill's `references/` only when its SKILL.md mentions `references/<name>.md`, so a skill opts in by pointing to it.

The `_shared/` copies are **committed**. Adding the marketplace by URL clones the repo, so every installed skill already has its code. Use copies, not symlinks.

## Guardrails

Every SKILL.md opens with a **Guardrails** section, right after its intro, covering fair housing, em dashes and Title Case labels. How strong the fair-housing part is depends on how much client-facing prose the skill writes:

| Level | Skills | What it has |
|---|---|---|
| Strong | buyer-cma, seller-cma, seller-offer-review | Guardrails with the skill's risky spots named, `references/fair-housing.md`, the render check, a fair-housing eval |
| Standard | buyer-offer-strategy, agent-profile | Guardrails, `references/fair-housing.md`, a fair-housing eval (and the render check for buyer-offer-strategy) |
| Light | contract-timeline, market-profile | A short Guardrails section (and the render check for contract-timeline) |

The render check is `shared/prose.py`, run by `render.main` before any file is built. It stops on an em dash used in a sentence (a lone one for an empty value is fine) or a clear fair-housing phrase and names each field to rewrite. The phrase list is a backstop for the written rules, not a replacement: it catches clear cases only, and chat replies are covered by the SKILL.md rules alone. State and local protected classes live in the market profile's `fair_housing.extra_protected_classes`.

## Output modes

Every skill has two modes built from one data file:

```
analysis scripts → <skill>.json → assets/<name>-template.md, filled by Claude → markdown in chat  (markdown mode)
                                → scripts/render.py --format pdf|pptx         → PDF / PPTX         (file mode)
```

- The math always runs in scripts. Markdown mode takes its numbers from the same JSON and its layout from a template, so chat and files agree without a script writing markdown. See [skill-guidelines.md](skill-guidelines.md#scripts-vs-templates).
- Default: **file mode** when the user asks for something to print, send, present, or "the report/deck"; **markdown mode** for quick questions. The user can switch by asking, and the skill offers the other mode in one line.
- Markdown mode mirrors the file's page-1 executive summary; detail tables on request.
- Every skill with file outputs has one entry point, `scripts/render.py DATA.json --format pdf|pptx|all --out DIR`. See [development.md](development.md#skill-render-contract).
- If rendering a file fails, say so plainly and fall back to markdown mode.

### Output location

Save files to the first of:

1. `OUTPUT_DIR` environment variable (local development only)
2. `/mnt/user-data/outputs/` (sandbox)
3. The current working directory

Never write into the skill's own folder, which is the working directory in claude.ai. This rule lives in `shared/` and is not repeated per skill.

## Profiles (core plugin)

Two markdown documents, used as context by every other skill:

| Profile | Answers | Examples |
|---|---|---|
| **Agent profile** | *Who* | Name, brokerage, team, license, contact, voice, disclaimers, [brand colors](#brand-colors) |
| **Market profile** | *Where* | State, MLS, closing costs, transfer taxes, who pays title, contract forms and deadline rules, MLS export columns |

An agent can have one agent profile and several market profiles.

Format: a YAML front block with the values scripts need, followed by readable prose.

```markdown
---
profile: market
schema: 1
name: Seminole County
state: FL
mls: Stellar
closing_costs:
  settlement_fee: 800
...
---

# Market profile: Seminole County
...
```

A user's market profile only needs `state`. Everything else is optional and overrides the built-in layers.

### Agent profile fields

Only **name** and **brokerage** are required. Everything else is optional:

```yaml
profile: agent
schema: 1
name: "Jane Doe"               # required
brokerage: "Sunshine Realty"   # required
team: "The Doe Group"          # optional
license: "SL1234567"           # optional
phone: ...                     # optional
email: ...                     # optional
website: ...                   # optional
brand: ...                     # optional, see Brand colors
```

Voice and disclaimers are optional prose sections below the YAML block.

- **Skip missing fields.** Outputs leave out any field that isn't set. No placeholders, no empty labels, no "License: N/A".
- **No profile at all.** A skill asks only for name and brokerage, and only when its output shows them (file-mode headers, signatures). Markdown answers to quick questions don't need them.

### Brand colors

Users are non-technical, so they shouldn't need to know hex codes. `agent-profile` accepts brand colors in any of these ways:

| User provides | How the colors are found |
|---|---|
| **Hex codes** | Used as given |
| **Website** | Read from the site's CSS and theme colors. If web access isn't available in the runtime, ask for an image instead |
| **Image** (logo, business card, flyer) | A script pulls out the main colors, skipping black, white and grey. Claude estimates from the image only if the script can't run |
| **Nothing** | Built-in defaults |

- **Confirm in plain words.** Name what was found ("Navy and gold. Navy for all reports?") and confirm before saving. Hex codes are shown only if the user asks.
- **Offer a split only when there's a choice.** Ask about separate buyer and seller colors only when the source has two strong colors.
- **Pick sensibly.** Mostly black → offer charcoal or navy. Too pale for text (yellow, light gold) → use it for accents only and say so.
- **Save a readable name.** Store the color name next to the code: `primary: "#1F3A5F"  # Navy`.
- **The image is only for reading colors.** Logos are not stored and not placed in reports.

The agent profile can set the primary color used in file-mode outputs (PDF, PPTX). Markdown mode ignores it.

```yaml
brand:
  primary: "#0B6E4F"          # both sides, unless overridden below
  buyer_primary: "#0B6E4F"    # optional, buyer-side documents
  seller_primary: "#8C1D40"   # optional, listing-side documents
```

The color for a document is picked in this order:

1. `buyer_primary` / `seller_primary` for the document's side
2. `primary`
3. Built-in default: buyer `#1A74AD` (blue), seller `#C2410C` (orange)

A skill that serves both sides (`contract-timeline`) uses the side of the view being rendered.

How the color reaches every output:

- **One input, full palette.** `shared/design.py` derives the rest from the primary color: dark shade for headings and emphasis, light tints for panels, callouts and rules, and chart accents. Skills never hard-code brand hex values in CSS, renderers or the deck builder. They take tokens from `shared/design`.
- **Status colors stay fixed.** Good / caution / risk (green `#2E7D5B`, amber `#B7791F`, red `#B3261E`) are not branded, so a meaning never changes color. If the brand color is close to one of them, the palette shifts that status color slightly so it still reads differently.
- **Legibility.** If the primary color doesn't reach WCAG AA contrast on white, a darkened version is used for text, and the original is used only for fills and accents. `agent-profile` mentions this in plain words when the color is saved.
- **Party coding.** Documents that show both parties (the timeline's Buyer / Seller / Both markers) use the resolved buyer and seller colors. If the two are the same or too close, the second party gets a clearly different shade, and parties are always labeled in text, never by color alone.
- **Side labels.** Default blue and orange keep buyer and seller documents easy to tell apart. With a single brand color that signal is gone, so every file-mode output shows its side (Buyer / Seller) in the header on every page.
- **Print-light PDFs.** Agents print these reports, so color goes into type, rules and thin accent bars, not background fills. Section headings are colored text with no rule under them (most sit on a boxed table or panel, and a rule on a box doubles the line); table headers are bold colored text over a rule, with no zebra rows; the page-1 answer, plans and callouts are outlined or carry a left bar; highlighted rows and status cells get a thin left mark and bold or colored text. A fill is allowed only where it is the data itself: chart bands and marks, timeline bars, meters, small status pills. Shared rules live in `shared/report.css` and `shared/cma.css`.

### Built-in market layers

Market values come in layers, merged in this order (later wins):

| Layer | File | Holds | Applies to |
|---|---|---|---|
| State | `shared/markets/states/fl.md` | Closing costs, title, property tax, contract rules, CMA adjustments, county overrides | Florida properties only |
| MLS | `shared/markets/mls/stellar.md` | History codes, CMA export columns, coverage | Stellar, in any state it serves (Florida and Puerto Rico) |
| Built-in county override | `county_overrides` in a built-in layer | Local customs (Miami-Dade stamps, who pays title) | That county |
| User profile | the agent's market profile | Anything | Its state |
| Profile county override | `county_overrides` in the agent's profile | The agent's own county exceptions | That county |

The agent always wins: a built-in county custom never overrides a value the agent set. A heading with nothing under it (`closing_costs:`) sets nothing. County names match loosely ("Miami Dade", "St. Johns" or "Saint Johns"); a Florida county that isn't one of the 67 gets a note. With no state, nothing built in applies: the skill asks for the state and never assumes Florida.

State and MLS are separate because an MLS can span states (Stellar serves Puerto Rico) and a state can have several MLSs (Miami-Dade isn't Stellar). Without a profile or a stated MLS, an MLS is assumed only when exactly one built-in MLS covers the property's county (never from the state alone), and the skill says so. Every value carries its source, so a skill can tell a built-in default from the agent's own number.

For any other state or MLS, the profile is built from what the user provides in chat or project files.

## Skills never require other skills

Users can turn any skill off. Skills share **files**, not invocations:

1. A consumer looks for its input (profile, CMA handoff) in the chat, then project files, then the working directory.
2. If it's missing, the consumer collects what *its own task* needs (it carries the schema and defaults via `_shared/`), then offers to save the result as a file.
3. It may mention the producing skill in one line ("Tip: `market-profile` saves this so you're not asked again"). It never says a skill must be enabled.

Outside the built-in market, a missing value is **never** filled with a Florida default. Ask, or use a labeled assumption and mark the report **Preliminary**.

**Per-deal costs.** A number that belongs to one deal (a title company quote, a transfer tax the agent confirmed for this county) goes in that deal's data file (`listing.costs` in the offer skills, `costs.title_fees` in the seller CMA), on top of the market layers, and is reported as "this listing". Numbers the agent uses on every deal belong in the market profile.

**Shares of price.** Every `*_pct` field in data files and profiles is a fraction: `0.025` means 2.5%. Interest `rate` is the exception, written as a percent (`6.95`) the way lenders quote it. Scripts refuse a `*_pct` of 1 or more with a message instead of guessing.

## Handoffs between skills

A skill whose output feeds another has a small, **versioned handoff schema**, separate from its full internal JSON.

| Producer | Handoff | Consumers |
|---|---|---|
| `buyer-cma` | `cma-handoff v1` | `buyer-offer-strategy` |
| `seller-cma` | `cma-handoff v1` | `seller-offer-review` |
| `agent-profile` | agent profile | all skills |
| `market-profile` | market profile | all skills |

`cma-handoff v1` carries: as-of date, subject facts, value range, recommended price, adjusted comps (compact), market conditions, and the market profile used.

Both modes carry the handoff:
- **File mode:** `<address>.cma.json` saved next to the PDF.
- **Markdown mode:** a fenced `cma-handoff v1` block at the end of the reply, so it survives copy-paste, project files and new chats.

Consumers accept input in this order:

| Available | Behavior |
|---|---|
| Handoff JSON file | Use directly |
| Markdown with a handoff block | Parse the block |
| Other CMA (plain markdown, another tool's PDF, notes) | Extract, confirm key numbers with the user, label as assumptions |
| Nothing | Conservative defaults, report marked **Preliminary** |
