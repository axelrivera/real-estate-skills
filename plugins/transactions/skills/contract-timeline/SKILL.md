---
name: contract-timeline
description: Reads an executed real estate purchase contract (with riders, addenda and counteroffers) and lays out every deadline, from the Effective Date and deposits through inspection, appraisal, loan approval, title, walk-through and closing, from the buyer's or the seller's side, with who owes each one, the action and what happens if it's missed. Florida FR/BAR contracts are built in; other states' contracts work from the contract's own dates and time rules. Use it whenever an agent has an accepted or executed contract and asks for key dates, deadlines, a contract timeline or closing calendar, "when does the inspection period end", "what's due next", a deadline summary for a client, or when an amendment or extension is signed and the dates need to be re-run. Not for writing or analyzing offers before acceptance.
---

# Contract timeline

Turns an executed contract into a timeline of every deadline. The dates come from a script, never mental math, because one wrong day can cost a client their deposit.

Two views of the same dates: the **buyer view** highlights the buyer's actions and when their protections end; the **seller view** highlights the seller's obligations and until when the buyer can still cancel. Use the side the agent represents, and ask if it's unclear.

## 1. Read the executed documents

Read the whole package: contract, every rider and addendum, and every counteroffer (`pdftotext -layout`, or read scanned pages directly). Record the terms in a deal file: read `references/deal-file.md` for the format.

- **Effective Date** is the last signature or initial on the final counteroffer or acceptance, not the offer date. Write down the evidence. If it's ambiguous, or later than today for a contract the agent calls executed, stop and ask: every deadline depends on it. A future date is fine for a what-if ("if we go under contract on the 20th"); say it's hypothetical.
- **Later documents win:** counteroffers override the offer; initialed handwritten changes override typed text. If something is illegible or two documents disagree, add it to `flags` instead of guessing.
- **FR/BAR contracts (Florida):** read `references/frbar.md` for where each date lives and the form defaults for blanks. List every default you used in `agent_notes` so the agent can confirm it.
- **Two kinds of notes.** `flags` print on the report as "Check:" lines, so use them for what the client should also see (a date two documents disagree on, a tight loan approval). `agent_notes` stay in chat: defaults used for blanks, readings to confirm, anything that would confuse a client.
- **Any other contract:** read `references/other-contracts.md`. You list the deadlines yourself, and the time rules come from the contract's definitions if the agent's market profile doesn't have them.

## 2. Compute

Include the agent's market profile when there is one (Project files, uploads); Florida rules are built in.

```
python3 scripts/timeline.py deal.json [--market market-profile.md]
```

It prints every date already formatted, or `ok: false` with `problems` to fix. Spot-check before going further: the deposit and loan application dates (short periods skip weekends and holidays), anything rolled to the next business day, and that closing isn't on a weekend or holiday.

The script adds its own notes: a `flags` line when loan approval falls within 5 days of closing, and `agent_notes` for a closing time the contract doesn't state (10:00 AM used) and for market assumptions (for example no built-in rules for the state). Pass the `agent_notes` on in plain words; MLS assumptions are already left out, because the MLS doesn't matter for a timeline.

## 3. Deliver

**Quick question** ("when does the inspection end?", "what's due this week?"): answer from the output in a sentence or two. A deal file with just the Effective Date, the time rules and the one deadline is enough; leave the closing date out if you don't have it (dates counted back from closing then wait for it). **Full timeline in chat:** fill in `assets/timeline-template.md` with the output's values. **A report to send or print:**

```
python3 scripts/render.py deal.json [--agent agent-profile.md] [--market market-profile.md]
```

It saves the PDF to the outputs folder in the agent's brand colors, when their profile is available. If it can't render, say so and give the markdown timeline instead.

With the PDF, keep the chat reply short: a small table of the key dates only (first deadline, when the contingencies end, closing), not the full template, since the PDF has everything. Always tell the agent, in plain words: the first deadline and who owes it, when the contingencies end, the closing date, every flag, and every agent note to confirm. Offer the other format in one line. Keep the deal file with the deliverable: it's the record for re-runs.

## Amendments and extensions

Don't rebuild the deal file. Add the amendment to `amendments` in signing order (format in `references/deal-file.md`), re-run, and answer with the output's `moved` list: one line per moved deadline, "Closing: Fri Nov 6 · 10:00 AM (was Fri Oct 30)", then anything the move made tight (flags). The report compares the original contract with the current one and shows moved dates as "was". Save the updated deal file to the outputs folder (uploads are read-only) and hand it back for next time.

## Limits

Dates are computed from the documents as recorded; the documents control. Lender dates (insurance bound, Closing Disclosure) are estimates. Recommend the escrow or title agent confirm the timeline, and a real estate attorney for any dispute about deadlines. Not legal advice.
