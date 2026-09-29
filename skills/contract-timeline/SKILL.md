---
name: contract-timeline
description: Reads an executed real estate purchase contract (with riders, addenda and counteroffers) and lays out every deadline, from the Effective Date and deposits through inspection, appraisal, loan approval, title, walk-through and closing, from the buyer's or the seller's side, with who owes each one, the action and what happens if it's missed. Florida FR/BAR contracts (AS IS and Standard, every rider and addendum) are fully supported; any other contract is read on a best-effort basis from its own dates and time rules. Use it whenever an agent has an accepted or executed contract and asks for key dates, deadlines, a contract timeline or closing calendar, "when does the inspection period end", "what's due next", a deadline summary for a client, or when an amendment or extension is signed and the dates need to be re-run. Not for writing or analyzing offers before acceptance.
---

# Contract Timeline

Turns an executed contract into a timeline of every deadline. The dates come from a script, never mental math, because one wrong day can cost a client their deposit.

Two views of the same dates: the **buyer view** highlights the buyer's actions and when their protections end; the **seller view** highlights the seller's obligations and until when the buyer can still cancel. Use the side the agent represents, and ask if it's unclear.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Flags and notes are about dates, terms and documents, never about the buyer, the seller or the neighborhood. Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **Contract support.** Only Florida FR/BAR contracts (AS IS and Standard, with their CR-7 riders and addenda) are fully supported. For any other contract the script output has `support: "best_effort"` and the line to use in `chat_notes`: say it once in chat, in your own short words. The same goes for a note that an FR/BAR contract isn't the revision the rules were checked against. Never put either in a PDF, calendar file, worksheet or markdown report.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## 1. Read the Executed Documents

Read the whole package: contract, every rider and addendum, and every counteroffer (`pdftotext -layout`, or read scanned pages directly). Record the terms in a deal file: read `references/deal-file.md` for the format.

- **Not executed yet** (only one party signed or initialed): stop before the scripts. Say what's missing, list the terms recorded (price, deposit, periods, riders) and offer to build the timeline once it's signed; run a what-if only when the agent gives the expected Effective Date. If the acceptance time in Para. 3 (or the contract's own) has passed, say so and suggest confirming with the other agent; never say the offer lapsed or is void.
- **Effective Date** is when the last party signed or initialed **and delivered** the final counteroffer or acceptance, not the offer date. Write down the evidence, and ask for the delivery date when it differs from the signature date. When the package shows signing times but no delivery (a Dotloop or DocuSign log), use the last signature or initial, say so in `agent_notes` and go on. If it's ambiguous, or later than today for a contract the agent calls executed, stop and ask: every deadline depends on it. A future date is fine for a what-if ("if we go under contract on the 20th"); say it's hypothetical.
- **A counter made on the contract itself** (the seller checks "Seller counters Buyer's offer", strikes terms and initials the changes): the Effective Date is the last party's last initial or signature on the changed terms, once delivered. The time to accept that counter is Para. 3(a)'s (2 days after delivery unless another time is written), not the buyer's original offer deadline.
- **Later documents win:** counteroffers override the offer; initialed handwritten changes override typed text. When two documents disagree on a fact (a condo document receipt date), use the later signed one and add the difference to `flags`. If something is illegible, flag it instead of guessing.
- **Already done:** an escrow receipt in the package means the deposit is in: record it in `completed` with the receipt date (`references/deal-file.md`), and the same for any other deadline the package or the agent shows as met. Done rows show as done and drop out of the calendar reminders.
- **Short sale (Rider G):** only the deposit, the short sale rows and Rider GG count from the Effective Date; every other period and the closing count from the buyer's receipt of the approval (`references/frbar.md`). Until `short_sale_approval_received` is recorded they stay pending, and the report and calendar still work.
- **FR/BAR contracts (Florida):** read `references/frbar.md` for where each date goes in the deal file and the defaults for blanks, `references/frbar-riders.md` for every rider attached (deadlines, defaults, what changes), and `references/frbar-addenda.md` for any addendum (counteroffer, extension, escalation, appraisal gap, co-op). Check the package with `references/frbar-package-check.md` (riders checked vs. attached, RESERVED riders on AS IS). `references/frbar-contract.md` has every paragraph of both forms when you need one. List every default you used in `agent_notes` so the agent can confirm it.
- **Two kinds of notes.** `flags` print on the report as "Check:" lines, so use them for what the client should also see (a date two documents disagree on, a tight loan approval). `agent_notes` stay in chat: defaults used for blanks, readings to confirm, anything that would confuse a client. These are agent notes, each with the question to ask: a blank with no default (Rider H's premium caps), a document the timeline depends on that wasn't uploaded (Rider GG's compensation agreement), and money that doesn't add up (deposits plus loan plus balance differ from the price, often after a counter changed the price).
- **Amendments dated after today:** ask the agent to confirm the signing date before using them.
- **Any other contract** (another state's form, a builder contract, the Florida Realtors CRSP): read `references/other-contracts.md`. You list the deadlines yourself, and the time rules come from the contract's definitions; nothing about another state's forms is built in.

## 2. Compute

Write deal.json in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files).

Florida rules are built in; for any other contract the time rules come from the contract (never estimated).

```
python3 scripts/timeline.py deal.json [--side buyer|seller]   # --side overrides the deal file's side
```

It prints every date already formatted, or `ok: false` with `problems` to fix. Spot-check before going further: the deposit and loan application dates, anything extended to the next business day, and a closing date that extended past a weekend or holiday.

The script adds its own notes; don't add these yourself. `flags`: loan approval within 5 days of closing or after it, a contingency that ends after closing, a closing on a weekend or holiday, the FHA/VA appraisal note. `agent_notes`: the title evidence, Rider F appraisal and Rider H insurance defaults, the closing time when the contract states none (10:00 AM), who designates the closing agent when `title_by` is blank, the Rider G notes (Para. 4 closing replaced, approval not received, Rider GG's start), and market assumptions. Every other default you used goes in `agent_notes` (deposit, inspection and loan days, rider periods); the script drops an exact repeat and your note on a default it reports. Pass the `agent_notes` on in plain words; MLS assumptions are already left out, because the MLS doesn't matter for a timeline.

## 3. Deliver

**Quick question** ("when does the inspection end?", "what's due this week?"): answer from the output in a sentence or two, plus at most one line on the rule used or what to confirm. A deal file with just the Effective Date, the time rules and the one deadline is enough; leave the closing date out if you don't have it (dates counted back from closing then wait for it). **Full timeline in chat:** fill in `assets/timeline-template.md` with the output's values. **A report to send or print:**

```
python3 scripts/render.py deal.json [--format pdf|ics|all] [--profile profile.md] [--date YYYY-MM-DD]
```

`all` (the default) saves the PDF and a closing calendar (`.ics`: one event per dated deadline not yet done, a reminder the day before each critical one) that the agent or client can import into any calendar app. It saves the PDF to the outputs folder; `--profile` puts the agent's name and brand colors on it (found as `references/saved-files.md` describes). The PDF's Prepared date is today; `--date` (or `report_date` in the deal file) sets another. If it can't render, say so and give the markdown timeline instead.

With the PDF, keep the chat reply short: a small table of the key dates only (first deadline, when the contingencies end, closing), not the full template, since the PDF has everything. Always tell the agent, in plain words: the first deadline and who owes it, when the contingencies end, the closing date, every flag, and every agent note to confirm. Offer the other format in one line. Keep the deal file in the temporary folder for re-runs in this conversation (`references/saved-files.md`, Working Files); never present or offer it.

## Amendments and Extensions

Add the amendment to `amendments` in signing order (format in `references/deal-file.md`), re-run, and answer with the output's `moved` list: one line per moved deadline, "Closing: Fri Nov 6 · 10:00 AM (was Fri Oct 30)", then anything the move made tight (flags). The report compares the original contract with the current one and shows moved dates as "was".

In this conversation, add it to the deal file in the temporary folder. In a later conversation, or when no deal file exists yet, rebuild the deal file from the executed package (the contract as first signed) and add each amendment to `amendments` in signing order, so the report still shows the "was" dates. The deal file is a working file: never hand it to the agent (`references/saved-files.md`).

## Limits

Dates are computed from the documents as recorded; the documents control. Lender dates (insurance bound, Closing Disclosure) are estimates. Recommend the escrow or title agent confirm the timeline, and a real estate attorney for any dispute about deadlines. Not legal advice.
