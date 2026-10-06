# Architecture

Decisions that apply to every skill in the `real-estate` plugin.

## Packaging

One plugin, and the repo root is the plugin: `.claude-plugin/plugin.json` (name `real-estate`, the only place the version lives) and `skills/<skill>/`. The same folder holds `.claude-plugin/marketplace.json`, a one-plugin marketplace named `real-estate-skills` whose entry points back at the root (`"source": "./"`), so the repo can be added by URL. With 10 to 15 skills planned, one install beats splitting skills across plugins: there's no install order and one file to upload. New skills go in `skills/`; don't add plugins.

Three ways in, all from the same `skills/` folder:

| Route | Built By | Contains |
|---|---|---|
| Marketplace (Cowork, desktop app) | Adding `axelrivera/real-estate-skills` | The repo; only `skills/` loads |
| `real-estate-<version>.plugin` (desktop app upload) | `make package` | `.claude-plugin/plugin.json`, `skills/`, `LICENSE` |
| `real-estate-skills-<version>.zip` (release, for sharing) | `make package` | The `.plugin`, the agent guide (`dev/package/README.md`: install, profile, MLS export and comps search, property report, each skill with inputs and examples) the PDF manual (`dev/package/*.pdf`, built from the guide by `make manual`) and `LICENSE` |
| One zip per skill (claude.ai) | `make package-skills` | That skill's folder |

## Runtimes

Skills run in the Claude **desktop app and cloud**: claude.ai chat and Cowork. Claude Code is not a supported runtime. Both runtimes run skills in the same Linux sandbox; see [runtime-support.md](runtime-support.md).

- A skill refers to its own files by paths relative to its skill directory (`scripts/render.py`).
- No paths outside the skill directory (`../../shared/`). claude.ai uploads each skill on its own, so a skill can't reach the repo's `shared/`.
- No `/mnt/...` paths hard-coded in instructions. See [Output location](#output-location).
- Skill `description` must stay under 1,024 characters (claude.ai limit).

## Self-contained skills and shared code

Each skill directory is complete on its own. Code used by several skills is edited in one place and copied into each skill:

```
shared/                         # edit shared code here
shared/references/              # shared reference files (fair-housing.md, saved-files.md), not code
skills/<skill>/
  scripts/_shared/              # copy made by the sync tool, never edit by hand
  references/fair-housing.md    # copy, only in skills whose SKILL.md points to it
dev/sync_shared.py              # make sync / make check-sync (also a pre-commit hook)
Makefile                        # make package: one .plugin; make package-skills: one zip per skill
```

A shared reference file is copied into a skill's `references/` only when its SKILL.md mentions `references/<name>.md`, so a skill opts in by pointing to it.

The `_shared/` copies are **committed**. Adding the marketplace by URL clones the repo, so every installed skill already has its code. Use copies, not symlinks.

## Contract support

Only contracts that have been through PDF extraction and the forms manifest get built-in references. Today that is the Florida Realtors/Florida Bar AS IS and Standard contracts, all 33 CR-7 riders and the related Florida Realtors addenda and disclosures (`dev/forms/farbar-forms.json`, checked with `make forms-check`; see [development.md](development.md#updating-a-contract-form)). They're described in four shared references, organized by form rather than by skill, and synced into each skill that reads contracts:

| Reference | Covers |
|---|---|
| `farbar-contract.md` | Both forms paragraph by paragraph, the Standards, every blank and default, every deadline, the AS IS vs. Standard differences |
| `farbar-riders.md` | Riders A to GG: which form allows each (I, K, L are RESERVED on AS IS), blanks and defaults, deadlines, cancel rights, money effects, what each skill does with it |
| `farbar-addenda.md` | Counteroffer, extension, escalation, appraisal gap, CDD, co-op, repair request, walk-through, disclosures, multiple offers, closing and escrow forms |
| `farbar-package-check.md` | What a package must contain given the property's facts, which blanks have defaults, consistency checks |

Each skill keeps a thin reference that maps those rules to its own data file (`contract-timeline/references/farbar.md`, `seller-offer-review/references/contract-fields.md`, `buyer-offer-strategy/references/worksheet.md`). The deterministic rules live in `shared/contract_forms.py`: the form, the rider letters, and what the riders do to the inspection terms (Standard + Rider K runs AS IS math; Standard + Rider L keeps the repair limits and adds a walk-away).

Every other contract (another state's form, a builder contract, the Florida Realtors CRSP) is read on a best-effort basis through one shared guide, `other-contracts.md`: terms found by function, no borrowed defaults, no built-in rules for any other state, every reading cited and confirmed with the agent. The scripts return `support: "best_effort"` and a `chat_notes` line; the skill says it in chat, never in a PDF, calendar file, worksheet or markdown report. A note that a FAR/BAR contract isn't the verified revision follows the same rule.

## Guardrails

Every SKILL.md opens with a **Guardrails** section, right after its intro, covering fair housing, em dashes and Title Case labels. How strong the fair-housing part is depends on how much client-facing prose the skill writes:

| Level | Skills | What it has |
|---|---|---|
| Strong | buyer-cma, seller-cma, seller-offer-review | Guardrails with the skill's risky spots named, `references/fair-housing.md`, the render check, a fair-housing eval |
| Standard | buyer-offer-strategy, agent-profile | Guardrails, `references/fair-housing.md`, a fair-housing eval (and the render check for buyer-offer-strategy) |
| Light | contract-timeline, seller-net-sheet | A short Guardrails section and the render check |

The render check is `shared/prose.py`, run by `render.main` before any file is built. It stops on an em dash used in a sentence (a lone one for an empty value is fine), a clear fair-housing phrase, or client wording a client shouldn't see (tool words, unfilled `{placeholders}`, data keys, ISO dates in a sentence and the short jargon list in `prose.JARGON`; see `shared/references/client-wording.md`), and lists every field to rewrite at once as `field: problem → fix`. It reads the data file, the other files the render reads (the seller CMA's deck file, a `--cma` handoff's client-facing parts) and the profile's voice and disclaimers (em dashes, fair housing and tool words only). Missing data never stops it. Label fields the model types (each skill's `labels` patterns) are put in Title Case instead of stopping. Text the scripts write is checked in dev by `make style-check`, over every fixture's rendered HTML and calendar text. The phrase list is a backstop for the written rules, not a replacement: it catches clear cases only, and chat replies are covered by the SKILL.md rules alone. State and local protected classes live in the built-in market's `fair_housing.extra_protected_classes` (some Florida counties).

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

1. `--out` on the command line
2. `OUTPUT_DIR` environment variable (local development only)
3. The sandbox's outputs folder, when it exists
4. The current working directory

Never write into the skill's own folder, which is the working directory in claude.ai. This rule lives in `shared/` and is not repeated per skill.

The outputs folder holds deliverables only (PDF, PowerPoint, ICS, the profile and its project instructions). Data files and handoffs are working files in a temporary folder (`mktemp -d`), never presented or offered for download (`shared/references/saved-files.md`, Working Files). render.py returns and prints only the deliverables.

## Shared Report Kit

Every skill with file outputs is built on these pieces. The rules they enforce, so a report is right by construction for any input: a figure is computed once, formatted once and placed; a note is said once; a label never carries a note; the model writes judgment only.

### The Document Model

One run, one model. A skill's compute step (`compute.py`, `review.py`, `strategy.py`, `timeline.py`) reads the data file, copies it (it never changes its input) and returns one dict: each figure as a number and as its display text (formatted once with `fmt`), the rows and their ledgers, the facts, tiles, flags, the notes registry's lists and every sentence the script writes. `render.main(build, formats, compute=compute)` runs `compute(data, ctx)` once and hands the same result to every format's `build(result, fmt, out_dir, ctx)`: the PDF, the deck, the calendar file and the worksheet only read and place it. The markdown template and the chat reply are filled from the same model, printed as JSON by the compute step. So the same figure can't read differently in two places, and nothing is recomputed per format.

### Data, Judgment and Script Wording

The data file holds two kinds of fields, listed per skill in its data reference:

- **Data** the model copies from the sources (prices, dates, day counts, rider letters, comps and their adjustments) as plain numbers and ISO dates.
- **Judgment** the model writes (why this price, what to prepare, a terms reason, a condition), **figure-free**: no digits, `$`, `%`, months, seasons or weekdays, and nothing about who owns or lives in the home. `prose.figures` and `prose.people` find them, and the compute step and `render.py` refuse the field with a message to rewrite it.
- **Choices by rule, not by the model.** Where two runs on the same data must agree, the script decides by one documented rule and the model gives only the inputs that need judgment: the CMAs' supported range (`cma.choose_range`: the normal width centered on the median adjusted value, $5,000 ends rounded half up, pulled in so one comp never sets an end; `range_override` `{low, high, reason}` only for an agent's own range, shown as theirs) and comp condition (`cma.apply_condition_adjustments`: the model picks a level from the condition ladder for the home and each comp, `shared/references/condition-ladder.md`, and the script adjusts by the difference in the market's `cma.adjustments.condition_levels`; a typed condition amount stops the run).
- **Categories the model picks, prices the script sets.** Where the call is judgment but the numbers must reproduce, the model picks a named category (checked by `shared/choices.py`; an unknown value stops the run naming the allowed ones) and the script turns it into prices by rule. The script suggests the category from the data; the model keeps it or picks another with a figure-free reason; the agent's own numbers go in an override with a reason, shown as theirs. Buyer CMA: `offer_plan.posture` (`leverage`, `standard`, `competitive`, `must_win`; suggested by `cma.suggest_posture` from the history and the market, never `must_win`), priced by `offer_plan_for` in its compute.py (the gut check's `rough` uses the same function with the suggested posture, so the two agree), `plan_override` for the agent's steps; the credit offers are priced from the plan's opening, and the handoff carries `posture` beside the plan's numbers. Seller CMA: `pricing.stance` (`draw_offers`, `market` or `premium`, checked by `choices.pick`): `cma.suggest_stance` suggests one from months of supply, the share of active listings with a price cut and recent sale-to-final-list (never `premium` on a reprice or relist); the model keeps it or gives a figure-free `stance_reason`. `cma.list_price_at` puts the list price at the stance's share of the range on a portal search-bracket step ($469,900), and compute.py builds the options around it by rule (a step above and below inside the range, Stay plus cuts on a reprice, the failed price capping a relist, any two within 1% made one), with each option's time and seller credit from the export. The agent's own price is `price_override` `{list_price, reason}`, shown as theirs beside the stance's. Offers: the offer review's counter stance (`counter.stance`: `firm`, `meet_partway`, `terms_only`; the engine suggests one from the offers), the seller's priority (`seller.priority`) and the buyer's (`buyer_priority`, the buyer's own call, never suggested). Every category goes through `shared/choices.py` (`pick`): a missing one takes the suggestion or the default, an unknown one stops the run naming every choice (`field: problem → fix`). A pick that differs from the suggestion needs a figure-free reason; the category's sentence is the script's (labels.json), and the document model carries the pick, the suggestion and the reason.

Every sentence that states a count, price, percent, date or comparison is the script's, from `assets/labels.json`. Fields the script now writes (a CMA's `paragraph`, `key_stats` or a card's `meta`, an offer review's `counter.rows`) are refused when the model types them, with where the judgment goes instead. This replaced the claim-checking regexes that tried to catch wrong facts in model prose: with no facts in model prose, there's nothing to catch. A new fact goes in as a labels.json key and a script sentence, never as a model field.

### The Pieces

**Compute once.** `render.main(build, formats, compute=compute)` (above). Without `compute`, `build` gets the data file; only the agent profile (markdown only) has no compute step.

**`shared/fmt.py`: every figure as text.** Half-up rounding (half away from zero) throughout; `None` prints as the empty-value dash.

| Function | Output |
|---|---|
| `half_up(v, unit=1)` | `2.5 → 3`, `−2.5 → −3`; `unit` 1000, 5000, 0.1… |
| `money(v, unit=1, style="minus")` | `$474,900`, `−$1,200`; `style="accounting"` `($1,200)`, `"signed"` `+$1,200` |
| `k(v, digits=0)` | `$455K`; `digits=1` `$432.5K`; from a million `$1.25M` (never `$1,000K`) |
| `pct(f, digits=1, fixed=False, symbol=True)` | `2.5%`, `3%`; `fixed` keeps zeros `3.0%`; `digits=None` the `:g` form; `symbol=False` the bare number |
| `num(v, digits=0)` | `1,850` |
| `months(m)` | `1.3 months`, `1 month` (months of supply) |
| `date_long(d)` / `date_short(d, year=True, weekday=False)` | `September 26, 2026` / `Sep 26, 2026`, `Sat Sep 26` |
| `when(v, style="short")` | `Thu Sep 24, 5:00 PM`; `"dot"` `Sep 24, 2026 · 5:00 PM`; `"deadline"` `Thu Sep 24 · 5 PM`; `"long"` `September 24, 2026, 5:00 PM`; `"row"` `Thu Sep 24 · 5:00 PM` (a timeline row) |
| `clock(t, full=True)`, `weekday(d)` | `5:00 PM` (`5 PM`), `Thursday` |
| `range(lo, hi, f=money)` | `$420,000–$450,000`: an unspaced en dash; equal ends print once |
| `period_labels(window)`, `unspaced(text)` | `April–June`, `July 15–September`; `April – June` → `April–June` |

Dates take a `date`, a `datetime` or an ISO string and never print ISO; text that isn't a date passes through. `dev/tests/test_fmt.py` checks each function, and against the older shared formatters that still exist (`finance.money`, `offer_engine.short_price`/`pct`/`fmt_when`/`fmt_when_short`, `deadline_label`): the same text, except ties round up. A skill keeps no formatter of its own.

**`finance.Ledger`: columns that add up.** `add(key, label, amount)` (signed), `cost(...)` (a positive cost, stored negative), `credit(...)`: each line is rounded once, half-up to the dollar, when added. `total(keys=None)` and `costs()` sum the rounded lines, so a printed column always adds to its printed total; `amount(key)`, `rows(f=fmt.money, sign=True)`, `tuples()` (offer_engine.net_sheet's `(key, label, amount)` shape). `finance.seller_net_ledger(price, net, payoff)` wraps `seller_net`'s result. `offer_engine.net_sheet` builds every offer's net on one (`ledger` on the sheet; `lines` its rounded lines, `net` their sum, `holding` rounded the same way), so both offer skills' net sheets add up.

**`shared/notes.py`: one notes registry per document.** `N.add(key, text, kind)` with kind `assumption`, `estimate`, `info` or `chat_only`; a key (or the same text under another key) added twice keeps the first. `N.pdf()` lists the notes block (assumptions, estimates, then the rest, each in the order added; no chat-only notes), `N.chat()` everything. `N.label_problems(labels)` / `N.check_labels(labels)` catch a label that carries a note's text or tags itself `(Estimate)` / `(Assumed)`.

**`shared/layout.py`: components and the page-fit pipeline.** Cell text is escaped; `layout.Raw(html)` passes markup a renderer built.

| Piece | What it makes |
|---|---|
| `Col(key, label, align="text"\|"num", min, max, wrap)` + `table(cols, rows, total=None, keep="auto"\|"brk"\|"whole", head=True)` | A boxed table: headers wrap at spaces, figures right-aligned, tabular and never wrapped; an optional total row; long tables run on whole rows (`.brk`) unless `whole`; `head=False` for a short list with no header row |
| `tiles(items, n)` | Exactly `n` equal slots of (label, value[, sub[, cls]]); fewer items leave slots empty; `cls` marks a kind of tile for the skill's CSS |
| `fact_row(items)` | Short facts on one line between thin rules |
| `notes_block(N)` | The notes block from a registry (or a list) |
| `header(title, subtitle, prepared, tag, sample)`, `footer(left)` | The report header and running footer |
| `Chart().mark(key, label, swatch)` + `chart.legend()` + `chart_frame(svg, legend, title, takeaway)` | A legend built only from series actually drawn (marked), in an outlined chart box with at most one takeaway |
| `text_width(text, size, bold, tnum)`, `wrap_lines(text, width, size)` | Text measured with the bundled font's metrics (same units as `size`), for charts and decks |
| `Fit(...)` + `print_pdf(doc, path, fit, footer_html)` | The one page-fit pipeline (below) |

A short plain block between groups (a paragraph under 15% of the page) that would reach a page's bottom margin starts the next page in the estimate too, since the print moves it whole rather than splitting it at the pixel. A CMA's scatter always prints at its full size: it never shrinks to finish a page, and empty space is preferred to a smaller chart. When a chart group doesn't fit, the notes after its figure (an excluded-homes note, the chart's read-out box) follow it to the next page when the heading, intro and chart fit here at full size; otherwise the whole group moves. `Fit` holds a document's fit rules: `limit` (px page 1 may fill; the printable height by default), `end` (the selector that starts page 2, `.pb`; `None` when page 1 fits itself), `one_page` (the whole document is one page), `steps` (body classes or JS functions applied in order until page 1 fits), `tail` (body classes tried when the last page is under `tail_below` full, kept only when they save a page; after them every `Fit` tries `KEEP_TAIL` when the last page still holds only a few closing lines, under 15% full: the document's last block keeps with the block before it, which moves on with it (unless the last block starts a page on purpose), kept only when the last page then fills past 15% with no page added and no new half-empty page between), `blocks` (page-1 blocks named when it still overflows), `paginate` (keep-together groups and run-on tables for the later pages: `group_blocks` and `PAGINATE_JS`, moved here from `cma.py`), `landscape`, `margins`. `print_pdf` prints, reads the pages back (`page_fill`, pdftotext), and prints once more when page 1 spilled (refit 40px tighter), a tail step may save or fill the last page, or a block printed lower than estimated; the second print is kept only when it's better. It returns the steps used, page 1's height, the pages and the checks for stderr.

**Where a table may split: one rule for every PDF.** A table splits across pages only with at least 3 body rows on each side; a summary row (`total`, `total2`, `subtotal`, `final`) prints with the 2 rows above it; a small table never splits (fewer than 8 body rows that take under a quarter of the page); a table that tall in fewer rows (offers side by side, each row a paragraph) may split with 2 rows a side when it has under 6, rather than leave the page before it half empty. A table that may split draws its outline on the table itself, square: a wrapper broken across pages would stretch to the page foot and print an empty band under the last row. `TABLE_BREAKS_JS` sets this on the rows themselves (`break-before: avoid` where a break isn't allowed, `break-inside: avoid` on a small table, `data-split` on each table) at the start of `fit_page`, before anything is measured, so Chromium's print keeps it for any data; `PAGINATE_JS` lets a table run on only when it's marked `rows`. **The layout probe** (`LAYOUT_PROBE=1`, dev only: `make layout-check` and the generated tests set it) puts a tiny, nearly transparent marker in each row's first cell just before printing, reads the markers back from the PDF and prints a `Check: ... split table` line for any table that broke the rule; a client PDF never carries a marker.

**The bundled font.** Inter 4.1 (SIL Open Font License, `shared/fonts/LICENSE.txt`), regular and bold, subset to Latin as WOFF2 (about 30 KB each). `report.css` declares it as `"Report Sans"` (weights 600 and up use the bold file) and `render.page` inlines the files as data URIs, so the page needs no font path in the sandbox; `render.html_to_pdf` loads every face before measuring. Every PDF skill sets the body class `font-bundled`, so the page prints in Inter in the sandbox and locally alike. `shared/fonts/metrics.json` holds each character's advance width (and tabular digits) for `layout.text_width`, generated by `dev/font_metrics.py` in Chromium. Every skill that renders a PDF ships `fonts/` in `scripts/_shared/` (about 73 KB). The PowerPoint deck keeps Arial for PowerPoint users.

**`prose.figures(text)`: figure-free model text.** The figures in a string the model wrote: a dollar amount, a percent, any digits, and a date in words (a month's name, "May" only after "in", "by", "since" and the like; a season, "fall" only as one, never a place like Winter Park or Altamonte Springs; a weekday). Links and emails keep their digits. A label or judgment field with one is refused with a message to the agent, since the script prints every figure and date itself. **`prose.people(text)`** finds what describes the people who own or live in the home (lives in, vacant, a tenant, owner-occupied, relocating, divorcing, their family, an estate sale): the CMAs and the offer review refuse it in judgment fields (`prose.PEOPLE_FIX`), for fair housing and the seller's privacy. Contract data (a lease the contract assigns, a possession note) isn't checked with it.

### Building a Skill on the Kit

Every file-mode skill is on the kit; a new one is built the same way. References by shape: the seller net sheet for a one-page report (`skills/seller-net-sheet/scripts/compute.py` and `render.py`, `assets/labels.json`, `dev/generators/seller_net_sheet.py`, `dev/tests/test_generated_seller_net_sheet.py`); the buyer CMA for a long, paginated report with a chart (its points and trend computed once in the model, `cma.scatter_points`, and drawn with `cma.scatter(points=..., chart=layout.Chart())`, so the legend names the series drawn and the caption's trend is the drawn one); the seller CMA for a report and a deck from one model (each option has one closing date that sets its proration and holding costs; `deck.py` only picks the model's figures for each slide, and `prep.items` are the report's Before We List, page 1's first steps and the deck's launch plan at once); the seller offer review for several documents from one run (`review.compute` builds the comparison and each single review as `review.result` models, with flags keyed by topic and a What to Confirm table beside one notes block); the buyer offer strategy for two PDFs from one model (`strategy.result`, reasons kept as label keys with their figures, one `framing` for what the recommended offer is, the buyer's limits named by one function, `limits_broken`); the contract timeline for a PDF and a calendar file from the same rows.

1. **One document model.** The compute step returns one dict (above); `render.py` passes it as `render.main(..., compute=...)`, and each format's `build(result, ...)` only places it. Compute copies the data before filling anything in (a handoff's defaults too).
2. **Wording in `assets/labels.json`.** Every label and sentence a script writes is a key there, filled with `fmt.fill` (the skill's `t()`): a part in `[brackets]` prints only when every placeholder in it has a value, so a template names an optional field inside one (`"because {read}[ ({basis})]"`) and reads whole without it, and the result never carries a doubled space or a space before punctuation. The keys cover headings (`h_`), legends (`lg_`), rows, facts, tiles, notes (`note_<registry key>`), Preliminary reasons, warnings. `make style-check` holds the `h_`, `th_`, `lg_`, `sum_`… keys to Title Case, so sentences use other prefixes. Code keeps no client wording of its own.
3. **`fmt` only.** Every display string comes from `fmt`.
4. **A `Ledger` per column.** Itemize in the ledger (a title fee total split into its fees is one ledger line per fee), take subtotals with `total(where=...)` and display every row from ledger amounts, so each printed column adds up.
5. **One `notes.Notes` registry.** Give each note a key and a kind: `assumption` and `estimate` (on the page, and the reply says them as its assumption lines), `info` (the page's notes and the markdown sheet's), `chat_only` (the reply only: a default commission, which is a default, not an assumption; anything assumed, such as no HOA, is an `assumption` and prints once on the page). The model carries `notes` (`N.pdf()`), `assumptions` (the reply's kinds), `chat_notes` (`info` only, so the reply and the markdown sheet never repeat each other) and `note_keys`. One key per fact, whichever way it falls (one `tax` note, worded by case). A fact a page already says elsewhere (the Preliminary line, a tile) isn't also a note. Run `N.label_problems` on every label in compute and stop on any. A note the model adds about a script note or a row takes its key, so the script keeps one.
6. **Model text is judgment or names.** No model field states a fact; what's left (labels included) is checked with `prose.figures` and refused with a figure in it, and a field the script writes is refused by name.
7. **The layout kit.** `layout.header`, `fact_row`, `tiles` (fixed slot count, a class per kind of tile), `table` (`Col`, `row_classes`, `Raw` cells for a span the skill styles), `Chart().mark()` as each series is drawn, `chart_frame`, `notes_block`. The skill's CSS styles kit classes under its own class (`.net-tiles .kit-tile`) and never redefines the kit. The page fit is a `layout.Fit` printed with `layout.print_pdf`; act on `info["top"] > info["limit"]` and `info["steps"]`. Nothing is measured by hand: headers wrap (`overflow-wrap:anywhere` where one may be a single long word). The body class `font-bundled` is on.
8. **Say each fact once.** No section, note, fact or tile restates another element (a "not included" note under a Preliminary line that says it, a costs tile beside a tile showing the same costs). A spare tile slot may stay empty.
9. **A generator and its generated test.** `dev/generators/<skill>.py`: `generate(seed)` returns a valid, realistic input (price ranges, long names and labels, edge dates, optional fields missing, the skill's rare branches) and `agent(seed)` a profile. `dev/tests/test_generated_<skill>.py` asserts only universal properties over `FUZZ_N` seeds (8 in `make test`): columns add up, each note once (by key and by text, on the page once), no label carries a note, legends name what's drawn, the input unchanged, and printed: the page count, nothing clipped or over, every dollar figure and percent on the page from the model. `make fuzz` runs 25 on fresh seeds; a failure is fixed in the construction, never with a special case ([development.md](development.md#tests)).
10. **Tests, golden, docs.** Skill tests assert keys, flags and numbers, never sentences; the generated test covers columns, labels and pages. `make golden` and explain every diff. SKILL.md, the data reference (which fields are data, which are judgment), the example data, the fixtures and `evals.json` (behaviors, never the script's wording), then `make samples`.

## Profiles

One markdown file, `profile.md`, used as context by every other skill. It says who the agent is: name, brokerage, team, license, contact, voice, disclaimers and [brand colors](#brand-colors). Nothing about markets or costs: those come from the property (see [Local costs](#local-costs)).

`agent-profile` builds it from a two-round interview (the basics, then look and sound), modeled on the prototype onboarding interviews: fill-in-the-blank questions with examples, everything skippable, saved after the first round.

When the interview is done it also writes `project-instructions.md` (from `assets/project-instructions-template.md`), a short first-person prompt the agent pastes into a claude.ai Project's instructions or a Cowork project's Instructions: it names the agent, points to `profile.md`, and says to use the skills, the profile's voice and the guardrails. It names only the agent, so a profile change never makes it stale. The hand-over recommends a Project and gives the setup steps for where the agent is (`references/project-setup.md`). No other skill reads it.

### Saved Files

In Cowork with a working folder selected, the profile is saved as `profile.md` directly in that folder. Every later session finds it there without an upload; so does a profile the agent keeps anywhere in that folder under another name (any file that starts with `profile: agent`). In any chat it can also be pasted or uploaded, or kept in a Project's files. Skills resolve the path from the agent's working folder, never the current directory (Cowork runs skills from a plugin folder). Without a working folder, and in claude.ai, it goes to the outputs folder with one line on keeping it (Project files, or share at the start of a chat). Scripts never search for it: the model finds the file and passes `--profile`.

The rules live in `shared/references/saved-files.md`, copied into every skill that reads or writes a profile or a CMA handoff.

Format: a YAML front block with the values scripts need, followed by readable prose.

```markdown
---
profile: agent
schema: 2
name: "Jane Doe"
brokerage: "Sunshine Realty"
team: "The Doe Group"
brand:
  primary: "#1F3A5F"  # Navy
---

# Profile: Jane Doe
...
```

### Agent Fields

Only **name** and **brokerage** are required. Everything else is optional:

```yaml
profile: agent
schema: 2
name: "Jane Doe"               # needed on client files
brokerage: "Sunshine Realty"   # needed on client files
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

The profile can set the primary color used in file-mode outputs (PDF, PPTX). Markdown mode ignores it.

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
- **One hue, unless the color means something.** Every output uses only the brand color's shades and tints, plus black, grays and white. A color leaves the brand only when the color itself carries meaning: status (good / caution / risk) and party coding (the timeline's Buyer / Seller / Both markers). Everything else is a derivation: the subject home and the price lines are black (`--subject` in `shared/cma.css`), the deck's dark slides are `brand_deep`, and highlights are brand tints and borders. The palette's navy "both" color appears only as a party marker. In the deck, every role that carries text or a mark is checked for contrast, so light (yellow), mid and near-black brands all work: chart marks 3:1 on white and apart from the black subject and gray other sales; small brand text uses `brand_strong` (7:1); text and circles on the dark slides use the lightest tint that reaches 7:1 on `brand_deep` (`contrast_roles` in `skills/seller-cma/scripts/deck.py`).
- **Side labels.** Default blue and orange keep buyer and seller documents easy to tell apart. With a single brand color that signal is gone, so every file-mode output shows its side (Buyer / Seller) in the header on every page.
- **Print-light PDFs.** Agents print these reports, so color goes into type, rules and thin accent bars, not background fills. Section headings are colored text with no rule under them (most sit on a boxed table or panel, and a rule on a box doubles the line); table headers are bold colored text over a rule, with no zebra rows; the page-1 answer, plans and callouts are outlined or carry a left bar; highlighted rows and status cells get a thin left mark and bold or colored text. A fill is allowed only where it is the data itself: chart bands and marks, timeline bars, meters, small status pills. One exception: a chart's takeaway box (`.chart-read` in `shared/cma.css`, the CMA scatterplot's "where this home sits against the dashed line") gets the faint `--brand-callout` tint, a left bar, an icon and a bold colored headline, because it's the one line a skimming reader must see. Keep it to one per chart and never use it for general notes. Shared rules live in `shared/report.css` and `shared/cma.css`.

**Status colors and color vision (DS-4).** Good and risk look alike under deuteranopia (both read olive-brown), and the caution base (`#B7791F`) is only 3.6:1 on white. So status is never shown by color alone: every colored cell, pill or bar has a word or icon with it (Favorable / Watch / Weak, a pill label, a legend). The `*-base` status colors are for fills, borders and chart marks; text uses `*-strong`. Party colors follow the same split: the raw color for borders and fills, `party_*_ink` (darkened to 4.5:1) for text (DS-1). A brand color within 0.10 (OKLab) of a status color rotates that status away from it; the default blue and orange are a checked pair and never shift (DS-2).

### Built-in market layers

Market values come in layers, merged in this order (later wins):

| Layer | File | Holds | Applies to |
|---|---|---|---|
| State | `shared/markets/states/fl.md` | Closing costs, title, property tax, contract rules, CMA adjustments, county overrides | Florida properties only |
| MLS | `shared/markets/mls/stellar.md` | History codes, CMA export columns, coverage | Stellar, in any state it serves (Florida and Puerto Rico) |
| Built-in county override | `county_overrides` in a built-in layer | Local customs (Miami-Dade stamps, who pays title) | That county |
| National estimates | `shared/markets/national.md` | Transfer tax, title, fees, commission (5% total), property tax, insurance, utilities (never contract rules); the states with no state transfer tax (none charged, source `national`) | Any property, for each section key no layer above set (source `estimate`) |

The deal's own numbers go on top (`Market.with_deal`, source `deal`). A heading with nothing under it (`closing_costs:`) sets nothing. National estimates fill whole keys, never leaves, so an estimated fee never mixes into Florida's fee list. County names match loosely ("Miami Dade", "St. Johns" or "Saint Johns"); a Florida county that isn't one of the 67 gets a note. With no state, only the national estimates apply: the skill takes the state from the listing or asks, and never assumes Florida.

State and MLS are separate because an MLS can span states (Stellar serves Puerto Rico) and a state can have several MLSs (Miami-Dade isn't Stellar). Without a stated MLS, an MLS is assumed only when exactly one built-in MLS covers the property's county (never from the state alone), and the skill says so. Every value carries its source, so a skill can tell a built-in default from the agent's own number.

For any other MLS, the skill maps the export's column headers itself (`--columns`, `export_columns`).

### Local Costs

Convention over configuration: reports never ask about local costs up front. They take the state and county from the listing, use this deal's numbers, then the built-in local values, then the national estimates (commission 5% total). A report says which figures are estimates once, in its footnotes or notes block, never inside column headers, tiles or row labels, and never twice; a default commission is a default, not an assumption, and gets no label (`make style-check` fails on an Assumed or Estimate mark in a label). Best-practice assumptions throughout: the 15 states with no state transfer tax get none (never the estimate), and the buyer's agent fee is included (the 2.5% default) until the deal says otherwise. Elsewhere outside Florida the skill looks up the state's transfer tax from a trusted source (the state revenue department, the statute, or the county recorder) and falls back to the estimate when in doubt. The reply lists the estimates the agent can replace, and the agent's numbers go in the same data file for a re-render. Estimates don't mark a report Preliminary; only a value with no estimate at all does. Contract time rules are never estimated: they come from the contract. The rules for Claude are in `shared/references/local-costs.md`.

## Skills never require other skills

Users can turn any skill off. Skills share **files**, not invocations:

1. A consumer looks for its input (profile, CMA handoff) in the chat, then Project files, then the Cowork working folder (profiles) or this conversation's temporary folder (handoffs), per [Saved files](#saved-files).
2. If it's missing, the consumer collects what *its own task* needs (it carries the schema and defaults via `_shared/`), then offers to save the result as a file.
3. It may mention the producing skill in one line ("Tip: `agent-profile` saves this so you're not asked again"). It never says a skill must be enabled.

Outside the built-in market, a missing value is **never** filled with a Florida default: it's a national estimate, named once in the report's notes.

**Per-deal costs.** A number that belongs to one deal (a title company quote, the transfer tax looked up for this state, the listing agreement's commission) goes in that deal's data file (`listing.costs` in seller-offer-review, `property.costs` in buyer-offer-strategy, `costs` in the CMAs, keys in `profiles.DEAL_COSTS`), on top of the market layers, and is reported as "this listing". Nothing is saved across deals.

**Shares of price.** Every `*_pct` field in data files and market layers is a fraction: `0.025` means 2.5%. Interest `rate` is the exception, written as a percent (`6.95`) the way lenders quote it. Scripts refuse a `*_pct` of 1 or more with a message instead of guessing.

## Handoffs between skills

A skill whose output feeds another has a small, **versioned handoff schema**, separate from its full internal JSON.

| Producer | Handoff | Consumers |
|---|---|---|
| `buyer-cma` | `cma-handoff v1` | `buyer-offer-strategy` |
| `seller-cma` | `cma-handoff v1` | `seller-offer-review` |
| `agent-profile` | `profile.md` | all skills |

`cma-handoff v1` carries: as-of date, subject facts, value range, recommended price, adjusted comps (compact), market conditions, and the market used (`market_profile`: state and MLS).

Both modes save the handoff; neither shows it to the agent (no JSON in chat or downloads):
- **File mode:** compute.py saves `<address>.buyer.cma.json` or `<address>.seller.cma.json` next to report.json in the conversation's temporary folder (the side keeps two CMAs of one address apart). It's a working file, never presented; in a new conversation the offer skill reads the CMA PDF and confirms the range with the agent.
- **Markdown mode:** the same file from compute.py. The chat summary never carries a JSON block: the agents aren't technical.

Consumers accept input in this order:

| Available | Behavior |
|---|---|
| Handoff JSON file (this conversation) | Use directly |
| Markdown with an old handoff block | Parse the block (still read, no longer written) |
| Any CMA PDF or summary (ours from an earlier conversation, another tool's, notes) | Extract, confirm key numbers with the user, label as assumptions |
| Nothing | Conservative defaults, report marked **Preliminary** |
