# Unit Test Triage

Review of `dev/tests/test_*.py` against the golden snapshots (`dev/golden.py`, `dev/golden/`).

- **Suite:** `.venv/bin/python -m unittest discover -s dev/tests` runs 495 tests (the 493 in scope plus the 2 in `test_golden.py`), all passing, in 38.6 s. All 495 are classified below; the two golden tests are KEEP.
- **Totals:** 392 keep, 86 rewrite, 12 remove, 5 merge.
- **Coverage:** not available. `.venv/bin/python -m coverage --version` gives `No module named coverage`. Nothing was installed.

## What Golden Pins, and What It Doesn't

I checked these gaps against the snapshot files. They are why several tests on unmodified fixtures stay KEEP, or become REWRITE instead of REMOVE:

1. **Floats are rounded to 2 decimals.** So `0.025` is stored as `0.03`, the loan-tax rates `0.0035` and `0.002` as `0.0`, `sale_to_list` `0.992` as `0.99`, a `down_pct` of `0.2615` as `0.26`, and concessions_pct `0.015` as `0.01` or `0.02`. Golden doesn't pin rates or fractions exactly.
2. **A list or tuple with any prose in it becomes `{"count": n}`.** That affects:
   - net-sheet lines `(key, label, amount)` in both offer skills, so no line amount is pinned, only `net` and `net_adj`
   - `counter_rows`
   - band tuples such as `('risk', 'At Risk')`, though `('comp', 'Competitive')` survives
   - timeline `open_rights`, `contingencies_waiting` and every `flags`, `agent_notes` and `warnings` list
3. **Timeline flags and notes, and CMA warnings, assumptions and notes, are plain strings with no key.** Golden can only count them, so any test about which one fired has to match prose. Offer flags carry `sev`, `topic` and `check`, so golden pins them per position. But many offer flags have `topic: None`: FHA condo approval, condo rescission, concessions over the cap, escalation cap and proof, FHA gap intent, and AGA with Rider F or FHA.
4. **A merged agent issue loses the engine's topic.** On `expired-aga.json`, the Rider GG flag that replaces the engine's flag has `topic: None`.
5. **Golden never runs `result()`, `summary()`, `worksheet()`, any renderer, ICS output or `handoff.validate`.** Every template, PDF, deck and schema check is outside it.
6. **Empty lists and dicts are dropped.** For example, `warnings == []` is simply absent. If one appears, golden reports it as `(new)`, so going from empty to not empty is still caught.

## Legend

- **KEEP:** covers a case golden doesn't, or is a compliance guard, an interface, tooling, or form routing.
- **REWRITE:** worth keeping, but brittle. The last column gives the concrete replacement.
- **REMOVE:** everything it asserts is already pinned by golden on an unmodified fixture. The only exception is a display string of a pinned number, noted per row.
- **MERGE:** folds into the named survivor.

## 1. Summary

| File | Tests | Keep | Rewrite | Remove | Merge |
|---|---:|---:|---:|---:|---:|
| test_contract_timeline.py | 67 | 51 | 15 | 0 | 1 |
| test_seller_offer_review.py | 26 | 14 | 12 | 0 | 0 |
| test_offer_engine.py | 45 | 33 | 10 | 2 | 0 |
| test_buyer_offer_strategy.py | 36 | 24 | 10 | 1 | 1 |
| test_contract_forms.py | 37 | 35 | 2 | 0 | 0 |
| test_buyer_cma.py | 29 | 19 | 6 | 4 | 0 |
| test_seller_cma.py | 52 | 32 | 14 | 4 | 2 |
| test_mls_cma.py | 32 | 29 | 3 | 0 | 0 |
| test_finance.py | 37 | 33 | 3 | 0 | 1 |
| test_profiles.py | 23 | 15 | 8 | 0 | 0 |
| test_agent_profile.py | 21 | 18 | 3 | 0 | 0 |
| test_design.py | 24 | 23 | 0 | 1 | 0 |
| test_prose.py | 11 | 11 | 0 | 0 | 0 |
| test_render.py | 9 | 9 | 0 | 0 | 0 |
| test_handoff.py | 4 | 4 | 0 | 0 | 0 |
| test_sync.py | 5 | 5 | 0 | 0 | 0 |
| test_lint_skills.py | 3 | 3 | 0 | 0 | 0 |
| test_style_check.py | 2 | 2 | 0 | 0 | 0 |
| test_mock_contracts.py | 30 | 30 | 0 | 0 | 0 |
| test_golden.py | 2 | 2 | 0 | 0 | 0 |
| **Total** | **495** | **392** | **86** | **12** | **5** |

## 2. Per File


### test_contract_timeline.py (67)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Holidays.test_observed_and_moving_holidays` | KEEP | Holiday calendar unit (observed/moving dates); no fixture. |  |
| `Holidays.test_saturday_new_years_observed_friday` | KEEP | TL-5 crash/rule regression, synthetic dates. |  |
| `Holidays.test_business_day_counting` | KEEP | Business-day arithmetic unit. |  |
| `FrbarDates.test_blank_association_approval_box_assumes_required` | REWRITE | Modified fixture (rule is new); rows are keys but the flag/note checks match sentences. | Keep the two `assertIn(key, rows)`. Replace the two prose checks with count deltas against the unmodified fixture: `len(r['flags']) == len(base['flags']) + 1` and `len(r['agent_notes']) == len(base['agent_notes']) + 2`, or a flag key (`'assoc_box_blank'`) once timeline flags carry keys. |
| `FrbarDates.test_first_deadline_includes_rows_both_sides_owe` | KEEP | Modified fixture (Rider GG + completed deposit); asserts keys only. |  |
| `FrbarDates.test_every_date` | REWRITE | Unmodified buyer-fha.json: every date, `day`, first_deadline/contingencies_end keys and pending keys are pinned by golden; only the flag/note sentences and the `source` label aren't. | Delete EXPECTED, `day`, first_deadline, contingencies_end, pending and `source` asserts. Keep TL-3 as `assertNotIn('appraisal', rows)` plus the FHA/VA flag as a key (`'fha_va_appraisal' in flag_keys`) once flags carry keys; drop the 'within 5 days' and 'Title evidence deadline blank' sentence checks (golden pins the counts). |
| `FrbarDates.test_rider_words_and_agent_notes` | REWRITE | Modified fixture; the whole-word rider parse is the rule, but 'Closing time isn't stated' matches a sentence. | Keep the appraisal-row asserts and the `not any(f.startswith('FHA/VA'))`. Replace the closing-time sentence with a note key (`'closing_time_assumed' in note_keys and not in flag_keys`), or `len(notes) == len(base_notes) + 1`. |
| `FrbarDates.test_cash_title_default_is_5_days` | KEEP | TL-2 on a modified copy (cash). |  |
| `FrbarDates.test_weekend_closing_extends` | REWRITE | TL-6/TL-8 on a modified copy; one assert matches the note sentence. | Drop `assertIn('closing extends to Mon Nov 2', note)`; the `when` asserts already pin the rule. |
| `FrbarDates.test_date_only_override_rolls_forward` | KEEP | TL-7 on a modified copy. |  |
| `FrbarDates.test_bad_inputs` | KEEP | TL-9 input errors. |  |
| `FrbarDates.test_contingency_after_closing_is_flagged` | REWRITE | Modified copy; asserts full flag sentences ('Inspection Period Ends (Right to Cancel) ends after closing'). | Assert the row facts (`rows['inspection']['when'] > rows['closing']['when']`) and a flag count delta of 1, or a flag key `('after_closing', 'inspection')` once flags carry keys. |
| `FrbarDates.test_association_rights_are_the_buyers` | KEEP | TL-11 on modified copies; party/contingency/when. |  |
| `FrbarDates.test_new_frbar_rows` | KEEP | TL-12/13/23 on a modified copy. |  |
| `FrbarDates.test_cash_drops_loan_deadlines` | KEEP | Modified copy (cash): row keys. |  |
| `FrbarDates.test_standard_contract_has_repair_notices_not_a_cancel_right` | KEEP | Form routing (Standard: repair notices, no cancel right). |  |
| `Amendments.test_moved_dates_show_was` | REWRITE | Unmodified seller-amended.json: `when`s and `was is None` are golden-pinned; the TL-21 summary text is the only guard for '30 (form default)'. | Delete the four `when`/`was`/`hoa_docs`/`lead_paint` asserts (golden). Keep the TL-21 checks, loosened to `'30 (form default)' in summary` and `'Dec 11, 2026' in summary`. |
| `Amendments.test_hoa_received_starts_review_window` | KEEP | Modified copy (HOA docs received). |  |
| `OtherContracts.test_other_contract_uses_its_own_rules_and_deadlines` | REWRITE | Unmodified other-contract.json: the TL-15 dates, contingencies_end key and the absent `deposit` row are golden-pinned; the rest is display text. | Delete the date/key asserts. Keep at most one structured check that the title commitment counts from the title company's receipt (a `basis`/`from` key on the row) instead of the `rule` sentence, and drop the `rules['family']` string. |
| `OtherContracts.test_best_effort_note_is_chat_only` | KEEP | Compliance: best-effort disclaimer never in the PDF or ICS. |  |
| `OtherContracts.test_frbar_revision_note_is_chat_only` | KEEP | Compliance: revision note stays in chat. |  |
| `OtherContracts.test_other_state_without_rules_is_refused` | KEEP | No built-in rules for other states (CLAUDE.md contract support). |  |
| `OtherContracts.test_other_contract_needs_deadlines` | KEEP | Input guard. |  |
| `Required.test_state_required` | KEEP | TL-4: never Florida by default. |  |
| `Required.test_florida_builder_contract_gets_no_frbar_rules` | KEEP | TL-4 form routing: non-FR/BAR Florida contract. |  |
| `Required.test_effective_date_required` | MERGE | Same input as the CLI test (effective date removed); the CLI test already exercises the DealError path. | Survivor: Required.test_cli_reports_problems_as_json (add one `assertRaises(timeline.DealError)` line). |
| `Required.test_quick_question_without_closing_date` | KEEP | Modified copy (no closing date). |  |
| `Required.test_per_deadline_time_and_no_rollover` | KEEP | Synthetic deadline (own time, no rollover). |  |
| `Required.test_cli_reports_problems_as_json` | KEEP | CLI contract. |  |
| `Pdf.test_render_uses_brand_and_side` | KEEP | Render contract: brand var, profile fields, no empty license line, sample mark. |  |
| `Riders.test_rider_k_turns_standard_into_a_walkaway` | KEEP | Form routing: Rider K on Standard. |  |
| `Riders.test_rider_l_keeps_repairs_and_adds_a_walkaway` | KEEP | Form routing: Rider L on Standard. |  |
| `Riders.test_reserved_rider_on_as_is_is_refused` | KEEP | Form routing: K RESERVED on AS IS (timeline path). |  |
| `Riders.test_rider_f_blank_date_is_ten_days_before_closing` | KEEP | Rider F default on a synthetic deal. |  |
| `Riders.test_rider_f_written_date` | KEEP | Rider F written date. |  |
| `Riders.test_rider_h_blank_is_the_earlier_date` | KEEP | Rider H default. |  |
| `Riders.test_rider_v_date_blank_waits_for_the_agent` | KEEP | Rider V pending/dated. |  |
| `Riders.test_short_sale_rows` | KEEP | Rider G defaults (10/90/30) on a synthetic deal; short-sale.json uses other values. |  |
| `Riders.test_post_closing_occupancy` | KEEP | Rider U. |  |
| `Riders.test_attorney_approval_dates` | KEEP | Riders Y/Z. |  |
| `Riders.test_mold_and_gg` | KEEP | Riders mold/GG. |  |
| `ContractHolidays.test_contract_holiday_list_only` | KEEP | TL-15/TL-24 holiday base 'none'. |  |
| `ContractHolidays.test_rollover_date_passes_a_contract_holiday` | REWRITE | Modified copy; dates are the rule, but one assert matches the exact rules-line sentence. | Keep the two `when` asserts; replace `assertIn('Only the holidays the contract lists.', ...)` with `assertIn('Holidays', [x['label'] for x in r['rules']['lines']])`. |
| `ContractHolidays.test_unknown_calendar` | KEEP | Input guard. |  |
| `AuditWording.test_closing_disclosure_counts_saturdays` | KEEP | TL-17 on a modified copy. |  |
| `AuditWording.test_insurance_bound_is_a_target` | KEEP | TL-25: `critical` is golden-pinned, but 'Lender Target' in the label is the fix itself and golden drops labels. |  |
| `AuditWording.test_open_rights_after_contingencies` | REWRITE | TL-14 on an unmodified fixture: open_rights are short labels (fine), but two asserts match rendered sentences. | Keep the two `open_rights` membership asserts. Replace the HTML sentence checks with a structural marker (the open-rights block's class/id present for the buyer view, absent for the seller view). |
| `TimeZones.test_panhandle_prints_central` | KEEP | TL-19 on a modified copy. |  |
| `TimeZones.test_split_county_is_flagged` | REWRITE | Modified copy; asserts the flag sentence 'spans two time zones'. | `len(flags_gulf) == len(flags_gulf_with_tz) + 1`, or a flag key `'time_zone_split'` once flags carry keys. |
| `Calendar.test_ics` | KEEP | ICS interface: framing, one VEVENT per row, VALARM on critical rows, 75-octet lines, stable UID. |  |
| `Calendar.test_render_writes_both` | KEEP | Render CLI contract. |  |
| `ShortSale.test_before_approval_rows_wait` | REWRITE | Unmodified short-sale.json: every date, every `when is None`, closing/contingencies_end None and `contingency` are golden-pinned; the rest matches rule and note sentences. | Delete the golden-pinned asserts. Replace the four `rule` sentences with a structured basis (`row['from'] == 'short_sale_approval'`) and the three agent_note sentences with a note count or note keys; keep the negative 'No closing date given' check. |
| `ShortSale.test_before_approval_renders` | REWRITE | Unmodified fixture; the ICS part (pending rows are never calendar events) is an interface check, the HTML part matches sentences. | Keep the two ICS asserts. Replace 'Awaiting Approval'/'10 days after short sale approval'/'Your main protections run through' with structural checks (pending rows render in the pending block; no contingency-summary block when contingencies_end is None). |
| `ShortSale.test_after_approval_rows_get_dates` | KEEP | Modified copy (approval received): Phase 2 dates. |  |
| `ShortSale.test_amended_closing_wins` | KEEP | Modified copy. |  |
| `Completed.test_done_rows` | KEEP | Modified copy (completed deposit): done flag, first deadline, ICS drops the done row. |  |
| `Completed.test_unknown_key` | KEEP | Input guard. |  |
| `ReportDetails.test_report_date` | KEEP | Input validation + date format. |  |
| `ReportDetails.test_ics_stamp_is_utc` | KEEP | ICS interface. |  |
| `ReportDetails.test_rollover_names_the_holiday` | REWRITE | Modified copy; asserts an exact note fragment 'a Saturday (Mon Oct 12 is Columbus Day)'. | `assertIn('Columbus Day', note)` and `assertIn('Tue Oct 13', note)`. |
| `ReportDetails.test_walkthrough_has_no_time` | REWRITE | Asserts exact display strings ('Thu Oct 29', 'Mon Nov 2 · before Closing') where structured flags exist. | `assertTrue(rows['walkthrough']['no_time'])` for the base case and `assertTrue(row['by_closing'])` (plus `when[:10] == '2026-11-02'`) for the Saturday closing. |
| `ReportDetails.test_condo_inspection_wording` | KEEP | The feature is the wording (unit vs. wind mitigation); short tokens. |  |
| `ReportDetails.test_custom_row_by_closing` | REWRITE | Custom-row rule is structural, but two asserts match display/rule strings exactly. | Replace `display == 'Fri Oct 30 · by Closing'` and `rule == 'By Closing'` with `assertTrue(rows['carpet']['by_closing'])`; keep `when` and the ordering assert. |
| `ReportDetails.test_title_by` | KEEP | Input validation and routing of the title party. |  |
| `ReportDetails.test_agent_notes_not_repeated` | KEEP | Dedup logic on synthetic notes. |  |
| `StripLayout.test_close_labels_never_overlap` | KEEP | Geometry invariant with user impact (overlapping labels). |  |
| `StripLayout.test_dense_fixture_renders` | KEEP | Crash smoke on the densest fixture (golden never renders). |  |

### test_seller_offer_review.py (26)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Analysis.test_single_summary_is_formatted` | REWRITE | result() is the template contract (golden doesn't run it), but several asserts are formatted strings of golden-pinned numbers. | Keep mode/action, `preliminary` truthy, `value_range == 'not provided'`, `to_confirm` truthy and the net_sheet column list. Replace '$382K FHA', '$350,689' and the counter row strings with `s['kpis'][1]['value'] == money(R['offers'][0]['ns']['net_adj'])` or drop them. |
| `Analysis.test_no_active_offers_stops` | KEEP | OFR-22 on a modified copy. |  |
| `Analysis.test_multi_plan` | REWRITE | Ranking is structural, but offers are matched by display label and `why`/`plan_note` by sentence. | Assert `[(p['id'], p['action']) for p in s['ranked']]` (or map labels to ids) and the balanced-priority headline COUNTER; drop the `why.startswith(...)` and both `plan_note` sentence checks (or give plan notes a key). |
| `Analysis.test_single_report_in_multi_context` | KEEP | Mode selection with multi-offer context; modified copy for the assumption. |  |
| `Analysis.test_labels` | KEEP | Unit test of the label functions (their output is the contract). |  |
| `Analysis.test_single_review_shows_no_letters` | REWRITE | The no-letters regex is the rule; two asserts are exact HTML fragments. | Keep both `assertNotRegex` and `'Offer from Whitfield · Compass' in doc`. Replace the two exact `<div class="big">...`/`<b>Sep 24...` fragments with `assertIn('Whitfield · Compass', doc)` (or drop them). |
| `Analysis.test_incomplete_contract_gets_no_recommendation` | REWRITE | Summary asserts are structural (not in golden); the three flag sentences are already golden-pinned as topics rider_E, lead_paint, loan_amount. | Keep the summary action/headline/counter/options and fixes `sev` list. Replace the three issue sentence checks with `{'rider_E','lead_paint','loan_amount'} <= {f['topic'] for f in flags}` or drop them (golden). |
| `Analysis.test_incomplete_offer_is_listed_but_not_ranked` | REWRITE | Modified copy; rank row and offers_active are structural; `why` sentence is brittle. | Drop `assertIn("can't be reviewed until the contract is corrected...", s['why'])`; keep the rest. |
| `Analysis.test_cli_reports_problems` | KEEP | CLI contract. |  |
| `Analysis.test_cma_handoff_in_markdown` | KEEP | Handoff interface (markdown block through the CLI). |  |
| `Analysis.test_texas_uses_estimates_not_florida_values` | KEEP | Compliance: no Florida numbers outside Florida; disclaimer chat-only. |  |
| `Analysis.test_best_effort_line_never_on_the_report` | KEEP | Compliance: best-effort line never in the PDF. |  |
| `Analysis.test_frbar_offer_is_fully_supported` | KEEP | Support key for FR/BAR; cheap. |  |
| `Pdf.test_html_uses_seller_theme_and_profile` | REWRITE | Brand/profile/OFR-4/no hard-coded orange are guards; two asserts are exact HTML fragments. | Keep brand var, Seller Side, SAMPLE DATA, brokerage, no 'Lic.', no '#C2410C', no 'CMA midpoint'. Replace the `<div class="big">ACCEPT...` and `<span><b>B (#1)</b>...` fragments with `'ACCEPT' in doc` and `'B (#1)' in doc` (OFR-28). |
| `Pdf.test_comparison_is_one_row_per_offer` | KEEP | Layout rule with user impact (rows not columns, no chart past six, landscape only for multi). |  |
| `Pdf.test_packet` | KEEP | Packet file-name contract. |  |
| `Pdf.test_lender_call_is_a_step_not_a_flag` | REWRITE | The rule (a step, not a flag) is structural; several asserts pin section numbers and markup. | Keep the flags check. Replace '8 · Questions for the Loan Officer' with 'Questions for the Loan Officer', the `<span class="cb">...` fragment with 'Loan officer called', keep the negative checks and the two 'on an FHA/conventional loan?' tokens. |
| `Pdf.test_default_theme_without_profile` | REWRITE | Default seller brand is a guard; one assert pins a whole header line with a date. | Keep `--brand:#C2410C`, 'Single Offer Review' and the 'None' check; replace the exact `Prepared for <b>Seller</b> · September 23, 2026</div>` with `'Prepared for' in header`. |
| `Pdf.test_texas_fine_print` | KEEP | Compliance: no Florida text on a Texas report. |  |
| `Pdf.test_renders_a_pdf` | KEEP | Single-review file name and PDF smoke. |  |
| `CounterWording.test_counter_says_what_changes` | REWRITE | OFR-16 synthetic, but asserts exact full-sentence equality. | Assert the parts: `'+$2,500' in s and '-2 points' in s and 'less certain' in s`; for the second call `'−$3,000' in s and '+$4,000' in s and '+5 points' in s`; keep the `endswith('risks losing a strong offer')` as `'strong offer' in s`. |
| `LapsedOffers.test_passed_deadline` | REWRITE | Unmodified expired-aga.json; action INCOMPLETE is golden-pinned; negative 'before Sep' check is the rule; positive sentence checks are brittle. | Keep `respond_by.startswith('Passed')`, the negative `'before Sep'` check, the revive counter and `counter is None`; drop `'new time for acceptance' in next_step` and the `action` assert (golden). |
| `LapsedOffers.test_estimated_deadline_counters_without_a_past_date` | REWRITE | Unmodified counter-chain-standard.json; action is golden-pinned; walk_away_until is an exact display string. | Keep `respond_by.startswith('Likely passed')` and the negative 'before' check; replace the walk_away_until equality with `'Oct 26' in walk_away_until` (the 30 days are pinned by golden `risk_days`); drop the `action` assert. |
| `LapsedOffers.test_broken_contract_gets_no_revive` | KEEP | No revive on a broken contract; `revive` isn't in golden (result()). |  |
| `LapsedOffers.test_aga_window_is_a_condition` | REWRITE | Unmodified expired-aga.json; exact walk_away_until string and a long note fragment. | `assertIn('Oct 26', c['walk_away_until'])` and `assertIn('gap', c['walk_away_note'])` (risk_days 36/30 are golden-pinned). |
| `AuditPlanWording.test_backup_only_after_primary_is_signed` | KEEP | OFR-6/OFR-21: only guard; the wording is the fix, and the negative check is robust. |  |

### test_offer_engine.py (45)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `MatchesPrototype.test_four_offers` | KEEP | Modified input (prototype costs): prototype parity and OFR-3/4/14/17 numbers; not in golden. Candidate to become a golden fixture. |  |
| `MatchesPrototype.test_minimal_single` | KEEP | Modified input (prototype costs); OFR-13/14. |  |
| `MatchesPrototype.test_two_offers_accept` | KEEP | Modified input (prototype costs). |  |
| `FloridaMarketDefaults.test_brokerage_assumed_at_five_percent_total` | KEEP | CORE-5 5% total: net-sheet lines are collapsed to counts and 0.025 rounds to 0.03 in golden. |  |
| `FloridaMarketDefaults.test_itemized_title_fees_and_stated_brokerage` | KEEP | Modified copy (stated brokerage). |  |
| `FloridaMarketDefaults.test_deal_quote_and_county_override` | KEEP | Modified copies (title quote, Miami-Dade). |  |
| `FloridaMarketDefaults.test_unknown_state_assumes_florida_and_says_so` | KEEP | Modified copy; high-impact assumption rule. |  |
| `OtherStates.test_national_estimates_not_florida` | KEEP | Compliance: never Florida numbers in Texas; lines not in golden. |  |
| `OtherStates.test_listing_costs_replace_the_estimates` | KEEP | Modified copy (listing costs win). |  |
| `Handoff.test_cma_range_and_midpoint` | KEEP | Handoff interface. |  |
| `Handoff.test_listing_file_wins_over_handoff` | KEEP | Handoff precedence. |  |
| `Rules.test_agent_overrides` | KEEP | Modified copy (agent scores/recommendation). |  |
| `Rules.test_counter_never_asks_fha_va_for_gap_money` | KEEP | OFR-3/OFR-17: counter_rows are collapsed to counts in golden (price 428000 is pinned). |  |
| `Rules.test_percent_written_as_whole_number_is_refused` | REWRITE | Asserts the full error sentence. | `assertRaisesRegex(oe.OfferError, r'listing_fee_pct.*0\.03')`. |
| `Rules.test_state_from_address_without_zip` | KEEP | Address parsing unit. |  |
| `Rules.test_no_transfer_tax_reads_as_none` | KEEP | Stub market; short prefix. |  |
| `Rules.test_required_inputs` | KEEP | Input guard. |  |
| `Rules.test_net_sheet_uses_finance_lines` | KEEP | Interface: engine reads finance's keyed lines and the market's tax name. |  |
| `CondoAndFlood.test_broward_condo` | REWRITE | CMA-5/CMA-6 on the unmodified fixture; asserts four full flag sentences. rider_A and flood_disclosure are already golden-pinned topics; FHA-approval and condo rescission flags have no topic. | Drop the rider_A/flood_disclosure sentence checks (golden). Add topics `fha_condo_approval` and `condo_rescission` to the engine and assert `{f['topic'] for f in flags}`; keep `request` truthy for the FHA-approval flag. |
| `CondoAndFlood.test_disclosure_given` | REWRITE | Modified copy; matches 'flood disclosure' in issue text although a topic exists. | `assertFalse(any(f['topic'] == 'flood_disclosure' for f in by_id(R)['A']['flags']))`. |
| `CondoAndFlood.test_not_florida` | KEEP | Compliance: no Florida statutes on a Texas offer; negative tokens. |  |
| `AuditSellerSideLimits.test_concessions_over_the_cap` | REWRITE | OFR-12 on a modified copy; asserts the sentence 'exceed the Conventional limit of 3% at 5% down'. | Add topic `concessions_cap` and assert `[f['sev'] for f in flags if f['topic'] == 'concessions_cap'] == ['High']` (or whatever sev it is). |
| `AuditSellerSideLimits.test_planned_quote_not_scored` | KEEP | OFR-18 score delta on modified copies. |  |
| `AuditReviewBenchmarks.test_norms_from_market_or_national` | KEEP | OFR-15: concessions_pct 0.015 isn't pinned exactly (golden rounds to 2 places); invariant on deposit vs. counter row. |  |
| `AuditReviewBenchmarks.test_handoff_side_and_nulls` | KEEP | OFR-24 handoff on a modified copy. |  |
| `AuditAppraisalAndEscalation.test_escalation_ranks_on_effective_price` | REWRITE | OFR-2 on unmodified escalation.json: price_base/price/escalated, rank and nets are golden-pinned; the note is an exact sentence. | Delete `escalation_note` equality and the golden-pinned asserts; keep one named assert `self.assertEqual(R['ranked'][0]['id'], 'A')` as the OFR-2 marker, or remove the test outright. |
| `AuditAppraisalAndEscalation.test_escalation_terms_are_checked` | REWRITE | Modified copy; matches flag sentences ('no cap', 'doesn't say how a competing offer is proven'); both flags have topic None. | Add topics `escalation_cap` and `escalation_proof`; assert both are in `{f['topic'] for f in flags}`. |
| `AuditAppraisalAndEscalation.test_fha_waiver_is_ignored` | REWRITE | OFR-3/OFR-17 on unmodified escalation.json: appraisal_protected, gap_cover, appraisal_days and the assumption field are golden-pinned; the rest is prose. | Delete the golden-pinned asserts. Add topic `fha_gap_intent` and assert it; drop the score `why` check. |
| `AuditAppraisalAndEscalation.test_financed_waiver_counts_only_documented_funds` | KEEP | Modified copies (waiver, gap funds). |  |
| `AuditAppraisalAndEscalation.test_price_above_midpoint_isnt_penalized` | KEEP | OFR-4 on a modified copy. |  |
| `MockContractFixes.test_lapsed_offer_is_blocking` | KEEP | Second half is a modified copy (same-day expiry); first half is golden-pinned and could be trimmed. |  |
| `MockContractFixes.test_estimated_deadline_is_high_not_blocking` | REMOVE | Unmodified counter-chain-standard.json: the expired flag (High, topic expired) and action COUNTER are golden-pinned; only `'delivered' in request` (wording) is not. |  |
| `MockContractFixes.test_counter_respects_the_sellers_last_counter` | REWRITE | First part is golden-pinned (counter_terms, flag topics) except RESTATE and the issue sentence; last part is a modified copy. | Delete the counter_terms, chain-count and inspection_period-topic asserts (golden) and the issue sentence. Keep `rows['Inspection Period'][3] == oe.RESTATE` and the $600,000 case. |
| `MockContractFixes.test_frbar_title_box_sets_who_pays` | KEEP | Para. 9(c)(i): net-sheet title line isn't in golden; modified copies. |  |
| `MockContractFixes.test_agent_issue_replaces_the_engine_flag` | REWRITE | Filters by 'GG' in the issue text and checks an issue prefix; the merged flag loses its topic (topic None), so golden can't key it either. | Keep the merged flag's topic (`rider_GG`) in the engine, then `[f['sev'] for f in flags if f['topic'] == 'rider_GG'] == ['Med']`; second half: `assertFalse(any(f['topic'] == 'inspection_period' for f in flags))`. |
| `MockContractFixes.test_advice_to_restate_in_a_counter_isnt_a_counter_chain_issue` | KEEP | Modified copy; topic/sev based; prefix is the test's own input. |  |
| `MockContractFixes.test_listing_broker_pays_is_not_an_assumption` | KEEP | Modified copy. |  |
| `MockContractFixes.test_preapproval_expiring_before_closing` | KEEP | Modified copies; topic/sev. |  |
| `MockContractFixes.test_proof_of_funds_below_the_cash_needed` | KEEP | Modified copies; boundary check. |  |
| `MockContractFixes.test_preapproval_cap` | REWRITE | The approval_cap flags on both unmodified fixtures are golden-pinned; the counter row labels are not (counter_rows collapse to counts). | Delete the two flag asserts; keep the two `'Pre-Approval' in counter_rows` asserts. |
| `MockContractFixes.test_standard_without_rider_f_appraises_within_loan_approval` | KEEP | Second half is a modified copy (no rider_F flag); form routing. |  |
| `MockContractFixes.test_standard_repairs_never_exceed_the_limit` | KEEP | Form routing (Standard repair limit); repair line isn't in golden. |  |
| `MockContractFixes.test_down_payment_from_loan_amount` | KEEP | down_pct 0.2615 rounds to 0.26 in golden, so the exact derivation isn't pinned. |  |
| `MockContractFixes.test_buyer_broker_paid_from_listing_fee` | KEEP | Modified copies. |  |
| `MockContractFixes.test_aga_walk_away_excludes_the_conditional_window` | REMOVE | Unmodified expired-aga.json; asserts only risk_days 36 and risk_days_ex_appraisal 30, both golden-pinned. |  |

### test_buyer_offer_strategy.py (36)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `MatchesPrototype.test_options` | REWRITE | Unmodified fha-competitive.json: price, score, cash worst/reserve, payment, ci, terms and the absent `stronger` option are golden-pinned. Only the lower_cost band `('risk','At Risk')` isn't (golden collapses that tuple to a count). | Delete everything but `self.assertEqual(r['bands']['lower_cost'][2][0], 'risk')`; remove the test entirely once golden keeps band keys. |
| `MatchesPrototype.test_seller_net_with_prototype_costs` | KEEP | Modified copy (prototype costs), OFR-10/13/14. |  |
| `MatchesPrototype.test_market_defaults` | KEEP | CORE-16: loan-tax rates 0.0035/0.002 round to 0.0 in golden, and closing_costs() isn't in golden. |  |
| `MissingData.test_minimal_is_preliminary` | REWRITE | Missing-field impacts, financing and down_pct are golden-pinned; summary strings aren't. | Delete the golden-pinned asserts; keep `assertTrue(s['preliminary'])` and `assertIn('assumed', s['financing'])`. |
| `MissingData.test_not_enough_cash_says_so` | REWRITE | Modified copy; constraint matched by sentence prefix. | `assertTrue(r['constraints'])` (or a constraint key `'cash'`) plus `assertNotIn('stronger', r['O'])`. |
| `MissingData.test_cash_buyer` | REMOVE | Unmodified cash.json: down_pct 1.0, financed False and loan_approval_days 0 are golden-pinned, and an OFR-1 regression would crash golden on cash.json. Only the summary label 'Cash' isn't pinned. |  |
| `MissingData.test_percent_down_still_refused` | KEEP | Input guard. |  |
| `MissingData.test_required` | KEEP | Input guard. |  |
| `EvalFindings.test_stronger_is_recommended_when_it_lifts_the_outlook_inside_limits` | REWRITE | Synthetic input (not in golden); the last assert is an exact `why` sentence. | Drop the `why['inspection_days']` equality or loosen to `'4-point' in why`. |
| `EvalFindings.test_planned_insurance_quote_is_not_scored` | REWRITE | OFR-18 synthetic; two exact sentence fragments. | Keep `promoted is None`; replace the score-why sentence with `o['insurance_quote'] == 'planned'` and the next_step check with `'insurance quote' in next_step`. |
| `EvalFindings.test_rate_written_as_fraction_is_refused` | KEEP | Input guard. |  |
| `HandoffAndOtherStates.test_handoff_fills_value_market_and_subject` | REWRITE | Unmodified texas-cma-escalation.json: value, list price, state, heat, promoted, terms and bands are golden-pinned, but sale_to_list 0.992 rounds to 0.99. | Delete the golden-pinned asserts; keep `B['market']['sale_to_list'] == 0.992` (or drop once golden keeps 3+ decimals). |
| `HandoffAndOtherStates.test_handoff_seller_paid_stats_fill_the_market_table` | KEEP | Modified copy; handoff-to-table interface. |  |
| `HandoffAndOtherStates.test_handoff_file_via_cli` | KEEP | CLI and handoff file. |  |
| `HandoffAndOtherStates.test_texas_worksheet_has_no_florida_forms` | KEEP | Compliance: no FR/BAR on another state's worksheet. |  |
| `HandoffAndOtherStates.test_florida_worksheet` | REWRITE | Worksheet isn't in golden; rider names are official titles (fine), but `rows[6]` pins row order and exact markdown. | `deposit = next(r for r in w['rows'] if r['field'] == 'Initial Deposit')`; `assertIn('$11,000', deposit['entry'])`. |
| `Pdf.test_options_html_is_buyer_side` | KEEP | Render contract: default buyer blue, side, no license line. |  |
| `Pdf.test_worksheet_never_shows_the_buyers_limits` | KEEP | Privacy guard (buyer's limits never on the worksheet). |  |
| `Pdf.test_option_choice` | KEEP | OFR-8 and the variant error path. |  |
| `Pdf.test_renders_both_pdfs` | KEEP | CLI/file-name contract. |  |
| `FloodCddCondo.test_flood_and_cdd_in_payment` | KEEP | OFR-26 on modified copies. |  |
| `FloodCddCondo.test_payment_label_without_quote` | KEEP | CMA-6 label rule on a modified copy. |  |
| `FloodCddCondo.test_condo_documents_and_flood_disclosure` | KEEP | CMA-5/CMA-6: document and statute names in result() (not in golden). |  |
| `AuditPricing.test_only_offer_never_above_list` | REWRITE | OFR-7 synthetic; the `why` fragment is brittle. | Keep the price assert; drop `assertIn('value range starts above it', why)`. |
| `AuditPricing.test_lower_cost_starts_from_the_agents_price` | KEEP | Modified copies (overrides). |  |
| `AuditPricing.test_option_that_saves_nothing_is_dropped` | KEEP | Invariant across fixtures; golden would show a diff, not a violation. |  |
| `AuditPricing.test_jumbo_and_fha_limits` | REWRITE | OFR-11 synthetic; matches assumption/limit sentences. | Assert the assumption by field (e.g. `a['field'] == 'loan_limit'`, adding a field if missing) and `r['limits']['recommended']` truthy; keep '$541,287' only as a number check if needed. |
| `FrbarGap.test_conventional_gap_uses_aga_not_rider_f` | KEEP | Form routing (AGA-1 vs. Rider F). |  |
| `OtherContractWorksheet.test_other_contract_rows_and_riders_are_generic` | KEEP | Compliance/form routing: no other state's form rules. |  |
| `OtherContractWorksheet.test_best_effort_line_is_chat_only` | KEEP | Compliance: disclaimer never in the worksheet. |  |
| `OtherContractWorksheet.test_fha_on_other_contract` | KEEP | Generic FHA addendum on another contract. |  |
| `OtherContractWorksheet.test_florida_keeps_its_inspection_period` | MERGE | One-line check on the same worksheet `test_florida_worksheet` builds. | Survivor: HandoffAndOtherStates.test_florida_worksheet (add `assertIn('Inspection Period', fields)`). |
| `InsuranceEstimate.test_older_home_estimate_and_floor` | KEEP | CORE-29 synthetic. |  |
| `AuditEscalationCap.test_cap_is_funded_from_the_same_risk_line` | KEEP | OFR-5 on a modified copy; structural plus a negative wording check. |  |
| `AuditEscalationCap.test_letters_cover_the_cap` | REWRITE | OFR-27 on a modified copy; exact sentence 'Letter at up to $637,000, the escalation cap'. | `assertIn('$637,000', text)` and `assertIn('escalation cap', text)`. |
| `AuditBuyerBrokerShortfall.test_shortfall_in_cash_to_close` | KEEP | CMA-4 on a modified copy. |  |

### test_contract_forms.py (37)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Module.test_normalize` | KEEP | Form routing. |  |
| `Module.test_walkaway` | KEEP | Form routing. |  |
| `Module.test_rider_codes` | KEEP | Rider parsing; RIDERS count guards a dropped rider. |  |
| `Module.test_rider_k_on_standard_is_as_is_math` | KEEP | Form routing (K). |  |
| `Module.test_rider_l_on_standard_keeps_repairs` | KEEP | Form routing (L). |  |
| `Module.test_reserved_riders_on_as_is` | KEEP | Form routing (I, K, L RESERVED). |  |
| `Module.test_revision_note` | KEEP | Form revision check. |  |
| `Module.test_repair_limits` | KEEP | Standard repair limits. |  |
| `AppraisalForm.test_detection_and_windows` | KEEP | AGA-1 vs. Rider F windows. |  |
| `AppraisalForm.test_aga_ends_the_appraisal_risk_sooner_on_a_long_close` | KEEP | Form routing on synthetic offers. |  |
| `AppraisalForm.test_short_close_makes_little_difference` | KEEP | Form routing. |  |
| `AppraisalForm.test_cash_offer_with_aga_carries_appraisal_risk` | KEEP | Form routing. |  |
| `AppraisalForm.test_aga_with_rider_f_or_fha_is_flagged` | REWRITE | Form routing, but matched by flag sentences ('not to use them together', 'FHA offer'). | Add topics `aga_with_rider_f` and `aga_fha` and assert them by topic. |
| `RiderWindowsAndPay.test_insurance_rider_window_counts` | KEEP | Rider H window. |  |
| `RiderWindowsAndPay.test_windows` | KEEP | Rider windows table. |  |
| `RiderWindowsAndPay.test_attorney_rider_without_date_is_an_assumption` | KEEP | Assumption by field. |  |
| `RiderWindowsAndPay.test_kickout_raises_a_sale_contingency` | KEEP | Riders V/X scoring. |  |
| `RiderWindowsAndPay.test_ff_credit_counts_toward_the_cap` | REWRITE | Rider FF vs. GG; matched by flag sentences ('exceed', 'Rider FF broker credit'). | Assert by topic (`concessions_cap`, the same topic proposed for OFR-12): absent with GG, present with FF. |
| `SellerEngine.test_as_is_uses_the_inspection_credit_only` | KEEP | Form routing (AS IS repair line). |  |
| `SellerEngine.test_standard_uses_the_repair_limits_only` | KEEP | Form routing (Standard repair limits). |  |
| `SellerEngine.test_same_offer_differs_only_by_form_rules` | KEEP | Form routing. |  |
| `SellerEngine.test_standard_with_rider_k_runs_as_is_math` | KEEP | Form routing (K). |  |
| `SellerEngine.test_standard_with_rider_l_walks_away_and_owes_repairs` | KEEP | Form routing (L). |  |
| `SellerEngine.test_reserved_rider_on_as_is_stops_the_review` | KEEP | Form routing (offer path). |  |
| `SellerEngine.test_rider_money_lines` | KEEP | Riders U/C net-sheet lines. |  |
| `SellerEngine.test_rider_f_default_runs_to_closing_minus_seven` | KEEP | Rider F default. |  |
| `SellerEngine.test_rider_flags` | KEEP | Rider flags; short distinctive tokens. |  |
| `SellerEngine.test_other_contract_walkaway_unstated_is_a_high_assumption` | KEEP | Never default a missing form silently. |  |
| `SellerEngine.test_other_contract_in_florida_gets_no_as_is_reserve` | KEEP | Form routing. |  |
| `SellerEngine.test_missing_form_in_florida_is_a_high_assumption` | KEEP | Never default a missing form silently. |  |
| `BuyerStrategy.test_worksheet_form_is_the_scored_form` | KEEP | Form routing (buyer side). |  |
| `BuyerStrategy.test_gap_option_is_scored_on_aga` | KEEP | Form routing (AGA-1). |  |
| `BuyerStrategy.test_needs_sale_is_scored_with_a_kickout` | KEEP | Riders V/X (buyer side). |  |
| `BuyerStrategy.test_ff_route_leaves_less_room_for_concessions` | KEEP | Rider FF (buyer side). |  |
| `BuyerStrategy.test_default_is_as_is_and_says_so` | KEEP | Missing form recorded as an assumption; worksheet part not in golden. |  |
| `Timeline.test_frbar_needs_its_form` | KEEP | Never default a missing form (timeline). |  |
| `Timeline.test_rows_follow_the_form` | KEEP | Form routing (timeline rows). |  |

### test_buyer_cma.py (29)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `MatchesPrototype.test_taxes` | REMOVE | Unmodified hickorywood.json; golden pins taxes[].annual (5931.54, 7578.61) exactly; only the rounded display string isn't. |  |
| `MatchesPrototype.test_payments` | REMOVE | Golden pins payments.rows total/cash_down and per_10k exactly. |  |
| `MatchesPrototype.test_credit_scenarios` | REMOVE | Golden pins every credit column (cash, payment, payback_years, over_cap, over_costs) and the buydown (covered, cost). |  |
| `MatchesPrototype.test_no_warnings_and_handoff` | REWRITE | Empty warnings and every handoff value are golden-pinned; `handoff.validate` on real output is the one interface check golden doesn't do. | Reduce to `handoff.validate(self.C['handoff'])` (and `len(comps_table) == len(handoff['comps'])`). |
| `Warnings.test_credit_over_program_limit` | REWRITE | Modified copy; warning matched by sentence. | Warning count delta (`len(C['warnings']) == len(base['warnings']) + 1`) or a warning key once warnings carry keys. |
| `Warnings.test_walk_away_above_range_and_credit_alt_mismatch` | KEEP | Modified copy; short tokens (a field name). |  |
| `Warnings.test_missing_field` | KEEP | Input guard. |  |
| `Warnings.test_input_checks` | KEEP | CMA-19/CMA-21. |  |
| `Warnings.test_thin_comps_warn` | REWRITE | Modified copy; matches 'Only 2 comps'. | Warning count delta, or `any('2' in w and 'comp' in w.lower() ...)`; better a warning key. |
| `Warnings.test_no_current_bill` | KEEP | CMA-13 render (not in golden). |  |
| `OtherMarkets.test_texas_without_millage_estimates_the_tax` | KEEP | Compliance: national estimate, not Florida. |  |
| `OtherMarkets.test_explicit_millage_works_anywhere` | KEEP | No Florida homestead in Texas. |  |
| `Pdf.test_brand_side_and_agent_fields` | KEEP | Render contract; DS-3 subject black. |  |
| `Pdf.test_full_pdf` | KEEP | PDF only, no JSON handed to the agent. |  |
| `Flood.test_get_a_quote` | KEEP | CMA-6 render rule (never $0, 'Get a Quote'); render not in golden. |  |
| `Flood.test_quote_counts` | KEEP | CMA-6 on a modified copy. |  |
| `Flood.test_zone_override` | KEEP | Modified copy. |  |
| `LoanTaxes.test_itemized_without_a_lender_figure` | KEEP | CORE-16 on a modified copy. |  |
| `LoanTaxes.test_lender_figure_is_left_alone` | REMOVE | Unmodified fixture; asserts only loan_taxes == 0, golden-pinned for every credit column. |  |
| `AuditMethod.test_adjustment_rates_outside_their_area_warn` | REWRITE | CMA-10; modified copy half matches a warning sentence. | Warning count delta for the Hillsborough case, or keep only `'Hillsborough' in w` (the county name is the point). |
| `AuditMethod.test_price_minus_credit_is_not_called_the_same_net` | REWRITE | CMA-11; the number is structural, one assert pins a long HTML sentence. | Keep `seller_cost_per_10k == 320` and the 'Same Seller Net' negative; replace the sentence with `assertIn('$320', html)`. |
| `AuditMethod.test_no_homestead_label` | REWRITE | CMA-14; pins a full heading. | `assertIn('No Homestead', html)` with the negative check. |
| `AuditMethod.test_mls_option` | KEEP | MLS assumption guard. |  |
| `AuditMethod.test_handoff_file_has_the_side` | KEEP | CMA-17 handoff file name. |  |
| `AuditMethod.test_export_resolves_beside_the_report` | KEEP | CLI path resolution. |  |
| `AuditMethod.test_handoff_file_defaults_next_to_report` | KEEP | Handoff file location. |  |
| `AuditMethod.test_offer_ladder_order` | KEEP | CMA-20 input guard. |  |
| `StatsWithoutAnExportRow.test_facts_rank_the_comps` | KEEP | stats.py CLI with no export row; the note substring is short. |  |
| `AuditBuyerBrokerShortfall.test_shortfall_row_and_cash` | KEEP | CMA-4 on a modified copy. |  |

### test_seller_cma.py (52)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `MatchesPrototype.test_nets` | REMOVE | Golden pins strategies[].net (423074, 422136, 425260 = prototype + 355); the `$422,136` display string is formatting. |  |
| `MatchesPrototype.test_net_lines` | REMOVE | Golden pins every net row's amounts by key and `preliminary`; the two labels are also asserted in test_finance/test_offer_engine and Costs.test_agent_terms_replace_placeholders. |  |
| `MatchesPrototype.test_buyer_payments` | REMOVE | Golden pins strategies payment/down and per_10k_display '$80' / down_per_10k_display '$500'. |  |
| `MatchesPrototype.test_no_warnings_but_assumptions` | REMOVE | Golden pins no warnings and the assumptions count (1); a brokerage assumption appearing changes the count. |  |
| `Handoff.test_seller_handoff` | REWRITE | Every handoff field is golden-pinned; the schema check is not. | Reduce to `handoff.validate(C['handoff'])`. |
| `Handoff.test_compute_cli_writes_handoff` | KEEP | CLI writes a loadable handoff. |  |
| `Costs.test_agent_terms_replace_placeholders` | KEEP | Modified copy (agreement terms). |  |
| `Costs.test_no_buyer_agent_fee` | KEEP | Modified copy. |  |
| `Costs.test_title_company_quote_replaces_built_in_fees` | KEEP | Modified copy. |  |
| `Costs.test_percent_is_rejected` | KEEP | Unit guard. |  |
| `Costs.test_credit_rows_by_key` | KEEP | CMA-1 on modified copies. |  |
| `Costs.test_payoff_hoa_and_other` | KEEP | Modified copy. |  |
| `Warnings.test_recommended_outside_range` | REWRITE | Modified copy; two warning sentences. | Warning count delta of 2, or warning keys (`outside_range`, `list_mismatch`). |
| `Warnings.test_expected_sale_above_range` | REWRITE | Modified copy; warning sentence. | Warning count delta of 1, or a warning key. |
| `Warnings.test_expected_sale_above_list_outside_competing_option` | KEEP | CMA-20. |  |
| `Warnings.test_missing_field` | KEEP | Input guard. |  |
| `OtherMarkets.test_texas_uses_labeled_estimates_not_florida_numbers` | KEEP | Compliance: no Florida numbers, estimates labeled. |  |
| `OtherMarkets.test_texas_deal_numbers_replace_the_estimates` | KEEP | Modified copy. |  |
| `OtherMarkets.test_texas_without_tax_rate_estimates_payments` | KEEP | National estimate. |  |
| `OtherMarkets.test_estimates_show_in_pdf_html` | KEEP | Compliance in the PDF (no transfer tax, Estimate labels). |  |
| `Brand.test_pdf_colors_side_and_agent_fields` | KEEP | Render contract; subject black. |  |
| `Brand.test_default_seller_orange` | KEEP | Default seller brand. |  |
| `Brand.test_deck_data_colors_and_agent` | REWRITE | Brand and agent-line checks are the contract; `party_both == '1F3A5F'` restates a constant and two asserts are display strings. | Keep brand, on_brand and `agent['lines'] == ['Sunshine Realty']`; drop party_both and the '$422,136' / '$400,000' display asserts; keep `'$80' in payment_takeaway` (placeholder filled). |
| `Brand.test_deck_roles_hold_contrast_for_any_brand` | KEEP | Contrast invariants for any brand. |  |
| `Brand.test_builder_has_no_hard_coded_colors` | KEEP | Compliance: no hard-coded colors in build_deck.js. |  |
| `DeckContent.test_missing_field` | KEEP | Deck input guard. |  |
| `DeckContent.test_competition_must_be_in_report` | KEEP | Deck consistency guard. |  |
| `DeckContent.test_net_note_lists_only_what_is_left_out` | REWRITE | Rule is real; the first assert pins the joined sentence. | Replace `'mortgage payoff, tax proration and repairs' in net_note` with three `assertIn(x, net_note)` for x in ('mortgage payoff', 'tax proration', 'repairs'); keep the negatives; replace 'Not included: repairs;' with `'repairs' in net_note`. |
| `DeckContent.test_strategy_title_follows_the_count` | REWRITE | Exact label equality. | `L = compute.cma.Labels(compute.ASSETS); self.assertEqual(D['labels']['deck_strat_title'], L('deck_strat_title_3'))`. |
| `DeckContent.test_expected_sub_follows_the_market` | REWRITE | Exact sentences for both market cases. | Compare to the label keys: `L('deck_expected_sub')` for the base case and `L('deck_expected_sub_at')` when expected sale equals list. |
| `DeckContent.test_comps_basis` | REWRITE | Exact sentences. | Compare to `L('deck_step_comps')` for the default and `L('deck_step_comps_basis', basis=...)` for the given basis (keep the 'never pool' comment). |
| `DeckContent.test_no_adjustments_note` | REWRITE | Exact sentence. | `self.assertEqual(D['labels']['deck_method_note'], L('deck_method_note_none'))`. |
| `DeckContent.test_no_mortgage_is_cash_at_closing` | REWRITE | Modified copy; the flags and the absent payoff row are the rule; net_sub and row label are sentences. | Keep `cash_at_closing and no_mortgage` and the no-payoff-row check; replace the net_sub sentence with `'cash at closing' in D['net_sub'].lower()` and drop the label equality. |
| `DeckContent.test_icons` | KEEP | Icon keys (never a pool the home may not have). |  |
| `DeckContent.test_counts_are_ranges` | KEEP | Deck content ranges. |  |
| `DeckContent.test_period_labels_across_new_year` | MERGE | Same function as AuditLowCma.test_period_labels. | Survivor: AuditLowCma.test_period_labels (add the year-boundary case). |
| `Files.test_full_pdf` | KEEP | PDF only, no JSON handed to the agent. |  |
| `Files.test_full_pptx` | REWRITE | Monochrome/subject-black/no-orange checks are compliance; the literal 15 slides/pages breaks on any slide change. | Replace `== 15` with `len(pdf_pages) == len(slides)` (PDF copy matches the deck) and keep a lower bound if wanted; keep every color and 'undefined' check. |
| `Files.test_long_wording_is_flagged` | REWRITE | Pins 'slide 7' (slide order). | Keep `len(checks) == 1` and `'deck.market_stats label' in checks[0]`; drop the slide number. |
| `Files.test_texas_pptx_without_export` | REWRITE | Pins 14 slides literally. | Assert no scatter chart in the deck (no `<c:scatterChart>` in ppt/charts) instead of `len(slides) == 14`; keep the PRELIMINARY/Documentary/placeholder negatives. |
| `Flood.test_flood_line` | KEEP | CMA-6; second half is a modified copy; the note isn't in golden. |  |
| `Flood.test_no_citizens_rule_outside_florida` | KEEP | Compliance: no Florida rule in Texas. |  |
| `HoldingCosts.test_net_after_holding` | KEEP | CMA-7 invariants on a modified copy. |  |
| `HoldingCosts.test_months_from_time_text` | KEEP | Parser unit. |  |
| `HoldingCosts.test_handoff_file_has_the_side` | MERGE | Runs the same compute.main as Handoff.test_compute_cli_writes_handoff. | Survivor: Handoff.test_compute_cli_writes_handoff (add `endswith('.seller.cma.json')`). |
| `AuditLowCma.test_deck_and_pdf_use_the_same_points` | KEEP | CMA-24. |  |
| `AuditLowCma.test_legend_lists_only_what_is_drawn` | KEEP | Legend rule. |  |
| `AuditLowCma.test_period_labels` | KEEP | CMA-25 (survivor of the period-label merge). |  |
| `AuditLowCma.test_method_note_lists_the_adjustments_used` | KEEP | CMA-26 (function output is the contract). |  |
| `AuditLowCma.test_payoff_from_a_balance_is_an_estimate` | KEEP | CMA-29. |  |
| `AuditMoneyLines.test_brokerage_assumed_when_not_given` | REWRITE | CORE-5/CMA-18 on a modified copy; exact labels and an exact note sentence. | Keep `standard_terms`/`incomplete`; loosen labels to `'Assumed' in label`, the note to `any('5%' in n and 'assumed' in n.lower() for n in notes)`; keep the PDF tile and deck `net_sub` token checks. |
| `AuditMoneyLines.test_tax_proration_and_surtax` | KEEP | CMA-3 on modified copies; the 'Not included' check is the proration-not-included rule. |  |

### test_mls_cma.py (32)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Load.test_stellar_export` | KEEP | Export parsing. |  |
| `Load.test_missing_columns_and_unknown_mls` | KEEP | Parser guards. |  |
| `Load.test_other_mls_column_names` | KEEP | Column mapping. |  |
| `Load.test_matrix_display_labels` | KEEP | Matrix labels. |  |
| `StandardNames.test_loads_and_drops_duplicate_sale` | KEEP | RESO export (not a golden input): dedup. |  |
| `StandardNames.test_cleans_fields` | KEEP | Field cleaning edge cases. |  |
| `StandardNames.test_distances_from_coordinates` | KEEP | Distances. |  |
| `StandardNames.test_ranking_and_competition` | KEEP | Ranking and relist detection. |  |
| `StandardNames.test_mismatch_penalties` | KEEP | Penalty table. |  |
| `Stats.test_market_stats` | KEEP | Stats invariants (direct, not through compute). |  |
| `Stats.test_exclude_address_drops_subject_rows` | KEEP | Subject exclusion. |  |
| `Stats.test_trend` | KEEP | Trend fit and r2 keys. |  |
| `Stats.test_price_outliers_leave_the_trend_alone` | KEEP | Outlier handling. |  |
| `Stats.test_trend_fits_sizes_on_both_sides` | KEEP | Fit window. |  |
| `Stats.test_too_few_sales_to_judge_outliers` | KEEP | Edge case. |  |
| `Stats.test_chart_drops_price_outliers_but_keeps_comps` | KEEP | Chart points rule. |  |
| `Blocks.test_groups_heading_intro_and_figure` | REWRITE | Keep-together grouping is real (print), but the assert pins exact HTML strings. | `self.assertEqual(out.count('<div class="kg sec">'), 2)` and assert '<p>loose</p>' sits between the two groups (index checks). |
| `Blocks.test_lone_h2_gets_section_class` | KEEP | Tiny contract. |  |
| `Blocks.test_dotplot_marks` | KEEP | One dot per comp. |  |
| `SubjectHeading.test_location_line_puts_mls_last` | REWRITE | The rule is ordering (MLS last); the assert pins the whole locality HTML. | `i = h.index; self.assertLess(i('Seminole County'), i('MLS O6433709'))` and `assertIn('<h1>517 Hickorywood Ave</h1>', h)`. |
| `SubjectHeading.test_escaping_and_empty_rows` | KEEP | Escaping and empty rows. |  |
| `AuditStatsAndCharts.test_distressed_and_new_construction_flags` | KEEP | CMA-8. |  |
| `AuditStatsAndCharts.test_distressed_sale_ranks_lower` | KEEP | CMA-8. |  |
| `AuditStatsAndCharts.test_limit_and_rest` | KEEP | Limit/rest. |  |
| `AuditStatsAndCharts.test_sale_to_list_is_net_of_seller_costs` | KEEP | CMA-9. |  |
| `AuditStatsAndCharts.test_months_supply_runs_to_as_of_with_pendings` | KEEP | CMA-12. |  |
| `AuditStatsAndCharts.test_bad_split_date_is_a_plain_error` | KEEP | Input guard. |  |
| `AuditStatsAndCharts.test_million_dollar_ticks` | KEEP | CMA-22: tick labels don't pile up (user-visible). |  |
| `DotPlotLabels.test_close_markers_label_on_opposite_sides` | REWRITE | CMA-23; asserts exact attribute strings. | Parse the two label elements (regex on `class="dp-(mark\|second)-lbl"`) and assert their `text-anchor` values differ. |
| `DeriveComps.test_itemized` | KEEP | CMA-2. |  |
| `DeriveComps.test_limits_and_replaced_values` | KEEP | CMA-2 limits. |  |
| `DeriveComps.test_hand_typed_must_agree` | KEEP | CMA-2. |  |

### test_finance.py (37)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Payments.test_pi_payment` | KEEP | Math unit. |  |
| `Payments.test_conventional_mi_below_20_percent` | KEEP | Math unit. |  |
| `Payments.test_fha_upfront_premium_in_loan` | KEEP | Math unit. |  |
| `Payments.test_fraction` | KEEP | Unit guard. |  |
| `Payments.test_concession_caps` | KEEP | Program caps table. |  |
| `Payments.test_buydown` | KEEP | Math unit. |  |
| `Taxes.test_florida_homestead_matches_prototype` | KEEP | CORE-17. |  |
| `Taxes.test_no_homestead` | KEEP | Math unit. |  |
| `Taxes.test_fallback_rate_and_unknown` | KEEP | Fallback and national estimate. |  |
| `Taxes.test_texas_style_exemptions` | KEEP | Exemption shapes. |  |
| `Taxes.test_owner_title_quote` | KEEP | Quote wins. |  |
| `Taxes.test_millage_lookup` | MERGE | One lookup that the tax-area test's first line also covers (same function, Seminole). | Survivor: Taxes.test_millage_by_tax_area_code (add the 'Altamonte' district line). |
| `Taxes.test_millage_by_tax_area_code` | KEEP | Tax-area code lookup. |  |
| `Taxes.test_check_units` | KEEP | Unit guard for every skill. |  |
| `Taxes.test_millage_row_never_guesses` | KEEP | Ambiguity guard. |  |
| `SellerSide.test_title_premium_florida` | KEEP | Promulgated rate math. |  |
| `SellerSide.test_seller_net_florida` | REWRITE | Keys, totals and assumptions are the contract; three asserts match line labels. | Drop the three `labels` asserts; the `[x['key'] for x in n['lines']]` list already covers transfer_tax/owner_title/estoppel. Keep the 0.70% only if needed as `'0.70%' in label`. |
| `SellerSide.test_buyer_pays_title_county` | REWRITE | Asserts by label ('Owner's Title Insurance') where a key exists. | `assertNotIn('owner_title', [x['key'] for x in f.seller_net(500000, miami)['lines']])`. |
| `SellerSide.test_other_state_uses_labeled_estimates` | REWRITE | The Estimate-label rule matters (CLAUDE.md), but three exact label equalities break on any rewording. | Keep the `assumed` estimate set and the 0.10% looked-up case; loosen labels to `assertIn('Estimate', labels[k])` for transfer_tax/owner_title/title_fees. |
| `SellerSide.test_no_state_transfer_tax` | KEEP | Texas: no transfer tax, never the 0.4% estimate. |  |
| `FloodInsurance.test_special_flood_hazard_area` | KEEP | CMA-6 (verified statute). |  |
| `FloodInsurance.test_citizens_phase_in` | KEEP | CMA-6 statutory thresholds and dates. |  |
| `FloodInsurance.test_condo_unit_policy_is_exempt` | KEEP | CMA-6. |  |
| `FloodInsurance.test_no_florida_rule_elsewhere` | KEEP | Compliance: no Florida rule elsewhere. |  |
| `FloodInsurance.test_quote_is_counted_and_never_zero` | KEEP | CMA-6: never $0. |  |
| `AuditMarketMoney.test_quote_beats_promulgated_table_and_warns_below_it` | KEEP | CORE-9. |  |
| `AuditMarketMoney.test_loan_taxes` | KEEP | CORE-16. |  |
| `AuditMarketMoney.test_second_homestead_exemption_starts_above_50000` | KEEP | CORE-17 edge case. |  |
| `AuditMarketMoney.test_layered_transfer_tax_warning` | KEEP | CORE-19. |  |
| `AuditLoanPrograms.test_va_funding_fee` | KEEP | OFR-25 table. |  |
| `AuditLoanPrograms.test_pmi_by_loan_to_value` | KEEP | OFR-25 table. |  |
| `AuditLoanPrograms.test_loan_limits` | KEEP | OFR-11 (2026 verified limits). |  |
| `AuditMoneyLines.test_proration_arrears_with_discount` | KEEP | CMA-3/OFR-14. |  |
| `AuditMoneyLines.test_miami_dade_surtax_by_property_type` | KEEP | CORE-6. |  |
| `AuditMoneyLines.test_buyer_pays_counties_move_the_search_fees` | KEEP | CORE-18 data. |  |
| `AuditMoneyLines.test_buyer_broker_shortfall` | KEEP | CMA-4. |  |
| `AuditMoneyLines.test_property_type` | KEEP | Normalizer unit. |  |

### test_profiles.py (23)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Parsing.test_errors_are_plain_language` | KEEP | Parser guard. |  |
| `Parsing.test_sections` | KEEP | Parser contract. |  |
| `Agent.test_full_profile` | KEEP | Profile loader contract. |  |
| `Agent.test_no_profile_lists_required_fields` | KEEP | Loader contract. |  |
| `Agent.test_only_required_fields` | KEEP | Loader contract. |  |
| `Agent.test_bad_color_warns_once` | KEEP | Loader contract. |  |
| `Agent.test_wrong_kind` | KEEP | Loader guard. |  |
| `Market.test_florida_gets_state_layer` | KEEP | Market layering. |  |
| `Market.test_mls_assumed_only_inside_coverage` | REWRITE | Structured MLS/source asserts carry the rule; two asserts match note sentences ('Stellar MLS was assumed', 'MLS wasn't given'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_puerto_rico_gets_stellar_but_no_florida_costs` | KEEP | Never Florida costs outside Florida. |  |
| `Market.test_mls_alias_and_explicit_mls` | REWRITE | Structured asserts plus a note sentence ('isn't built in'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_no_state_assumes_nothing_from_florida` | REWRITE | CORE-8/TL-4; structured asserts plus a note sentence ('don't assume Florida'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_other_states_get_national_estimates` | REWRITE | Structured asserts plus a note sentence ('national estimates'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_no_state_transfer_tax_states` | REWRITE | Structured asserts plus a note sentence ('no state transfer tax'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_estimates_never_mix_into_florida_values` | KEEP | Florida values never mixed with estimates. |  |
| `Market.test_county_override` | KEEP | County layer. |  |
| `Market.test_county_spellings` | REWRITE | CORE-10; `_county_key` equality is the rule, the unknown-county check matches a note sentence. | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `Market.test_bad_state` | KEEP | Input guard. |  |
| `Market.test_builtin_layers_are_valid` | KEEP | Data integrity of built-in layers. |  |
| `Millage.test_entries_are_complete_and_sourced` | KEEP | Data integrity (every row sourced, plausible). |  |
| `AuditMarketData.test_no_mls_without_a_county` | REWRITE | CORE-7; `mls is None` is the rule, the note check is a sentence. | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |
| `AuditMarketData.test_pinellas_is_stellar_brevard_is_not` | KEEP | CORE-7 coverage data. |  |
| `AuditMarketData.test_title_payer_by_county` | REWRITE | CORE-7 payer data is structural; the Monroe check matches a note sentence ('owner_title.payer varies by area'). | Keep the structured asserts (mls/source/get values); replace the note sentence with a note code (e.g. `m.note_codes`) or drop it. |

### test_agent_profile.py (21)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Images.test_single_brand_color_on_white` | KEEP | Color extraction. |  |
| `Images.test_two_strong_colors_offer_split` | REWRITE | Names and split are the rule; two asserts match advisory sentences. | Keep names and `'split' in suggestion`; replace the two note sentences with `any('Gold' in n for n in r['notes'])` or a note code. |
| `Images.test_exact_logo_colors_not_bucket_centers` | KEEP | Exact colors, not bucket centers. |  |
| `Images.test_small_accent_does_not_offer_split` | KEEP | Threshold rule. |  |
| `Images.test_black_and_white_logo` | KEEP | Fallback suggestions. |  |
| `Images.test_transparent_background_ignored` | KEEP | Alpha handling. |  |
| `Websites.test_theme_color_first_and_site_css` | KEEP | CORE-20 fetch rules and evidence. |  |
| `Websites.test_page_without_colors` | KEEP | Empty result. |  |
| `Websites.test_unreachable_site_asks_for_image` | KEEP | Error path (short token). |  |
| `Template.test_full_profile_passes_check` | KEEP | Template + checker + loader round trip; one warning substring is short. |  |
| `Template.test_minimal_profile_passes_check` | KEEP | Minimal template round trip. |  |
| `Template.test_quotes_survive` | KEEP | Quoting round trip. |  |
| `Check.test_leftover_placeholders` | KEEP | Checker guard. |  |
| `Check.test_missing_brokerage_and_bad_color` | REWRITE | Exact problem sentence 'Missing brokerage.'. | `assertTrue(any('brokerage' in p.lower() for p in r['problems']))`. |
| `Check.test_unreadable_file` | KEEP | Checker guard. |  |
| `AuditProfileFields.test_unquoted_number_is_a_problem` | KEEP | CORE-14. |  |
| `AuditProfileFields.test_licenses_and_brokerage_block` | KEEP | CORE-15; the notice line is the printed legal footer contract. |  |
| `AuditProfileFields.test_svg_logo` | KEEP | CORE-20 SVG. |  |
| `AuditProfileFields.test_unreadable_file_says_so` | KEEP | CORE-20 error path. |  |
| `AuditSmallFixes.test_agents_own_color_name` | REWRITE | CORE-27: the rule is that the agent's word is used; the assert pins the sentence start. | `assertIn('Gold', r['warnings'][0])` alongside the name assert. |
| `AuditSmallFixes.test_missing_logo_file` | KEEP | CORE-26 error path. |  |

### test_design.py (24)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `ColorMath.test_parse_hex` | KEEP | Unit. |  |
| `ColorMath.test_oklch_round_trip` | KEEP | Unit. |  |
| `ColorMath.test_contrast_reference_values` | KEEP | Unit. |  |
| `ColorMath.test_darken_to_reaches_target_and_keeps_hue_family` | KEEP | Legibility invariant. |  |
| `Defaults.test_default_sides` | KEEP | Default buyer blue / seller orange (CLAUDE.md). |  |
| `Defaults.test_defaults_are_not_adjusted` | KEEP | Defaults pass untouched. |  |
| `Defaults.test_default_party_colors` | KEEP | Party-coding defaults. |  |
| `Defaults.test_tints_close_to_prototype` | REMOVE | Pins tints near the prototype's hex values: fails on a deliberate palette tweak and guards no rule (legibility tests cover contrast). |  |
| `Resolution.test_order_side_then_primary_then_default` | KEEP | Resolution order. |  |
| `Resolution.test_invalid_color_falls_back_with_warning` | KEEP | Fallback. |  |
| `Resolution.test_invalid_side_override_falls_through_to_primary` | KEEP | Fallback. |  |
| `Resolution.test_bad_side` | KEEP | Guard. |  |
| `Legibility.test_every_brand_text_token_meets_its_target` | KEEP | Contrast targets for any brand. |  |
| `Legibility.test_light_color_keeps_original_for_accents_and_warns` | KEEP | Light-brand handling. |  |
| `StatusSeparation.test_status_shifts_away_from_matching_brand` | KEEP | Status colors stay distinct (CLAUDE.md meaning colors). |  |
| `StatusSeparation.test_named_brands_move_status_far_enough` | KEEP | DS-2. |  |
| `StatusSeparation.test_party_ink_is_readable` | KEEP | DS-1. |  |
| `StatusSeparation.test_unrelated_status_untouched` | KEEP | Status stability. |  |
| `Parties.test_single_color_stays_distinct` | KEEP | Party coding distinct. |  |
| `Parties.test_split_colors_kept_when_distinct` | KEEP | Split brand. |  |
| `Names.test_every_named_color_names_itself` | KEEP | Name table consistency. |  |
| `Names.test_common_brand_colors` | KEEP | Names used in agent-facing warnings. |  |
| `Formats.test_theme_is_json_serialisable` | KEEP | Interface. |  |
| `Formats.test_css_and_pptx` | KEEP | CSS var and PPTX color contract. |  |

### test_prose.py (11)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Phrases.test_red_flags` | KEEP | Fair-housing guard. |  |
| `Phrases.test_allowed_wording` | KEEP | Fair-housing false-positive guard. |  |
| `Phrases.test_phrase_table` | KEEP | FH-1/FH-2. |  |
| `Phrases.test_phrase_table_fh5` | KEEP | FH-5. |  |
| `Phrases.test_offer_reasons_describe_terms` | KEEP | FH-2 on the engine's own reasons for every loan type (modified copies). |  |
| `Phrases.test_em_dash_and_paths` | KEEP | Em-dash rule. |  |
| `PlaceNamesAndAllowList.test_place_keys_skipped` | KEEP | FH-3. |  |
| `PlaceNamesAndAllowList.test_allow_list` | KEEP | FH-3 allow list. |  |
| `PlaceNamesAndAllowList.test_allow_entry_needs_reason` | KEEP | FH-3 allow list. |  |
| `RenderStops.test_nothing_is_built` | KEEP | Render stops on a fair-housing issue. |  |
| `RenderStops.test_allow_list_is_logged` | KEEP | Allow list is reported. |  |

### test_render.py (9)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Filenames.test_slug` | KEEP | File-name contract. |  |
| `OutputDir.test_precedence` | KEEP | Output-folder contract. |  |
| `OutputDir.test_creates_missing_dir` | KEEP | Output-folder contract. |  |
| `OutputDir.test_falls_back_to_cwd_without_sandbox` | KEEP | Output-folder contract. |  |
| `Main.test_contract` | KEEP | render.main contract. |  |
| `Main.test_extra_args_and_partial_success` | KEEP | render.main contract. |  |
| `Pdf.test_html_to_pdf` | KEEP | PDF pipeline smoke. |  |
| `AuditNoticesAndBrokerage.test_name_without_brokerage_is_refused` | KEEP | CORE-3/4. |  |
| `AuditNoticesAndBrokerage.test_notices_print_disclaimers_verbatim` | KEEP | CMA-16/FH-6 (Equal Housing line). |  |

### test_handoff.py (4)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Handoff.test_round_trip_through_markdown` | KEEP | Handoff schema. |  |
| `Handoff.test_json_and_markdown_files` | KEEP | Handoff loader. |  |
| `Handoff.test_validation` | KEEP | Handoff validation. |  |
| `Handoff.test_filename` | KEEP | CMA-17 file names. |  |

### test_sync.py (5)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Sync.test_copies_only_into_skills_with_scripts` | KEEP | DOC-11 sync tooling. |  |
| `Sync.test_check_reports_each_kind_of_drift` | KEEP | Sync check tooling. |  |
| `Sync.test_references_go_only_to_skills_that_point_to_them` | KEEP | Sync tooling. |  |
| `Sync.test_staged_copies_must_match` | KEEP | DOC-8 pre-commit hook. |  |
| `SkillPaths.test_no_sandbox_paths_in_skills` | KEEP | CORE-21 (no /mnt paths). |  |

### test_lint_skills.py (3)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Lint.test_dev_only_imports` | KEEP | DOC-9 lint tooling. |  |
| `Lint.test_every_shipped_skill_passes` | KEEP | Lint over shipped skills. |  |
| `Lint.test_problems` | KEEP | Lint rules. |  |

### test_style_check.py (2)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Rules.test_headings` | KEEP | DOC-6 Title Case rule. |  |
| `Rules.test_word_dashes` | KEEP | DOC-12 dash rule. |  |

### test_mock_contracts.py (30)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `FieldMaps.test_every_map_resolves_on_its_form` | KEEP | Mock tooling: field maps resolve. |  |
| `FieldMaps.test_auto_roles_on_an_unmapped_rider` | KEEP | Mock tooling. |  |
| `KeyMatchesPdf.test_samples_cover_every_printed_key` | KEEP | Mock tooling: map/spec agreement. |  |
| `KeyMatchesPdf.test_every_value_is_on_its_form` | KEEP | Mock tooling (1.8 s). |  |
| `KeyMatchesPdf.test_a_value_with_no_blank_stops_the_build` | KEEP | Mock tooling guard. |  |
| `KeyMatchesPdf.test_rider_values_reach_both_keys` | KEEP | Answer-key interface with the skills. |  |
| `Packages.test_executed_package_reads_back_as_its_answer_key` | KEEP | Answer key vs. PDF. |  |
| `Packages.test_offer_is_signed_by_the_buyer_only` | KEEP | Stage rule. |  |
| `Packages.test_only_the_accepted_counter_changes_the_offer` | KEEP | Counter chain rule. |  |
| `Packages.test_pending_counter_leaves_the_offer_terms` | KEEP | Counter rule. |  |
| `Packages.test_amendments_carry_the_changes` | KEEP | Amendment rule. |  |
| `Packages.test_buyer_broker_compensation` | KEEP | GG/FF defaults. |  |
| `Packages.test_compensation_agreement` | KEEP | CASSB-1 timing. |  |
| `Packages.test_names` | KEEP | File naming. |  |
| `Packages.test_key_is_kept_apart_and_carries_the_gap_deadlines` | KEEP | Key location and AGA deadlines. |  |
| `Packages.test_flowed_text_skips_no_line` | KEEP | Flowed text on the form (visible in the mock PDF). |  |
| `Packages.test_package_follows_the_stage_and_the_facts` | KEEP | Package contents by stage. |  |
| `Packages.test_missing_disclosure_drops_the_flood_disclosure_when_no_rider_is_required` | KEEP | Defect behavior. |  |
| `Packages.test_disclosure_answers` | KEEP | SPDR answers. |  |
| `Packages.test_rules_come_from_contract_forms` | KEEP | Form routing through contract_forms. |  |
| `Packages.test_defects_are_recorded_in_the_key` | KEEP | Defects in the key. |  |
| `Packages.test_generated_people_never_share_a_name` | KEEP | Name uniqueness. |  |
| `Packages.test_follow_up_questions_follow_their_answer` | KEEP | SPDR follow-ups. |  |
| `Packages.test_rent_back_checks_para_6b` | KEEP | Para. 6(b). |  |
| `Packages.test_scanned_copy_has_no_text_layer` | KEEP | Scan option (2.5 s; slow tier candidate). |  |
| `Packages.test_every_scenario_builds` | KEEP | Every scenario builds (9.3 s; slow tier candidate). |  |
| `Packages.test_keys_render_through_the_skills` | KEEP | Answer keys render through the skills (5.5 s; slow tier candidate). |  |
| `Packages.test_seller_signs_offer` | KEEP | Signature events. |  |
| `Packages.test_counter_on_the_contract` | KEEP | Counter on the contract. |  |
| `Docs.test_documented_flags_exist` | KEEP | Doc/CLI agreement. |  |

### test_golden.py (2)

| Test | Verdict | Reason | Replacement / Survivor |
|---|---|---|---|
| `Golden.test_snapshots_match` | KEEP | The golden check itself. |  |
| `Golden.test_facts_drop_prose_and_keep_numbers` | KEEP | Unit of golden.facts. |  |

## 3. Audit IDs and Rules That Would Lose Their Only Guard

**None.** Applying every REMOVE leaves each audit ID and rule with at least one test, golden included. Below is what each REMOVE drops and what still guards it:

- `test_offer_engine.py` `MockContractFixes.test_estimated_deadline_is_high_not_blocking`: Unmodified counter-chain-standard.json: the expired flag (High, topic expired) and action COUNTER are golden-pinned; only `'delivered' in request` (wording) is not.
- `test_offer_engine.py` `MockContractFixes.test_aga_walk_away_excludes_the_conditional_window`: Unmodified expired-aga.json; asserts only risk_days 36 and risk_days_ex_appraisal 30, both golden-pinned.
- `test_buyer_offer_strategy.py` `MissingData.test_cash_buyer`: Unmodified cash.json: down_pct 1.0, financed False and loan_approval_days 0 are golden-pinned, and an OFR-1 regression would crash golden on cash.json. Only the summary label 'Cash' isn't pinned.
- `test_buyer_cma.py` `MatchesPrototype.test_taxes`: Unmodified hickorywood.json; golden pins taxes[].annual (5931.54, 7578.61) exactly; only the rounded display string isn't.
- `test_buyer_cma.py` `MatchesPrototype.test_payments`: Golden pins payments.rows total/cash_down and per_10k exactly.
- `test_buyer_cma.py` `MatchesPrototype.test_credit_scenarios`: Golden pins every credit column (cash, payment, payback_years, over_cap, over_costs) and the buydown (covered, cost).
- `test_buyer_cma.py` `LoanTaxes.test_lender_figure_is_left_alone`: Unmodified fixture; asserts only loan_taxes == 0, golden-pinned for every credit column.
- `test_seller_cma.py` `MatchesPrototype.test_nets`: Golden pins strategies[].net (423074, 422136, 425260 = prototype + 355); the `$422,136` display string is formatting.
- `test_seller_cma.py` `MatchesPrototype.test_net_lines`: Golden pins every net row's amounts by key and `preliminary`; the two labels are also asserted in test_finance/test_offer_engine and Costs.test_agent_terms_replace_placeholders.
- `test_seller_cma.py` `MatchesPrototype.test_buyer_payments`: Golden pins strategies payment/down and per_10k_display '$80' / down_per_10k_display '$500'.
- `test_seller_cma.py` `MatchesPrototype.test_no_warnings_but_assumptions`: Golden pins no warnings and the assumptions count (1); a brokerage assumption appearing changes the count.
- `test_design.py` `Defaults.test_tints_close_to_prototype`: Pins tints near the prototype's hex values: fails on a deliberate palette tweak and guards no rule (legibility tests cover contrast).

Guards that become golden-only, or rely on golden plus another test:

- **OFR-1 (cash buyer's 100% down passes the fraction check), `MissingData.test_cash_buyer`:** golden runs `cash.json` end to end, so a regression that raises would fail `test_snapshots_match`. Keep the test if you want the audit ID named in a failing test.
- **CORE-17 (2026 indexed homestead), in the buyer-cma and seller-cma prototype tests:** still covered directly by `test_finance.Taxes.test_florida_homestead_matches_prototype` and `AuditMarketMoney.test_second_homestead_exemption_starts_above_50000`.
- **CORE-16 (the lender's figure is left alone), `LoanTaxes.test_lender_figure_is_left_alone`:** golden pins `loan_taxes: 0` in every credit column, and the other branch keeps its own test (`test_itemized_without_a_lender_figure`).

None of the REWRITEs drops an audit ID's only assertion. Each one keeps its rule assertion (TL-3, TL-14, TL-21, OFR-2, OFR-16, OFR-18, CMA-10/11/14/23, CORE-5/CMA-18) and removes only the golden-pinned or prose parts.

### Merges

- `test_contract_timeline.py` `Required.test_effective_date_required` → Survivor: Required.test_cli_reports_problems_as_json (add one `assertRaises(timeline.DealError)` line).
- `test_buyer_offer_strategy.py` `OtherContractWorksheet.test_florida_keeps_its_inspection_period` → Survivor: HandoffAndOtherStates.test_florida_worksheet (add `assertIn('Inspection Period', fields)`).
- `test_seller_cma.py` `DeckContent.test_period_labels_across_new_year` → Survivor: AuditLowCma.test_period_labels (add the year-boundary case).
- `test_seller_cma.py` `HoldingCosts.test_handoff_file_has_the_side` → Survivor: Handoff.test_compute_cli_writes_handoff (add `endswith('.seller.cma.json')`).
- `test_finance.py` `Taxes.test_millage_lookup` → Survivor: Taxes.test_millage_by_tax_area_code (add the 'Altamonte' district line).

## 4. Changes That Would Make More Tests Removable

These are optional. Each one turns several REWRITE rows into plain key assertions, or lets golden cover more:

1. **Round small floats to 4+ decimals in `golden.facts`,** for example `round(v, 4)` when `abs(v) < 1`. This pins rates, which frees `test_market_defaults`, `test_norms_from_market_or_national`, `test_down_payment_from_loan_amount` and `test_handoff_fills_value_market_and_subject`.
2. **Keep the key and number members of mixed lists,** dropping only the prose items instead of collapsing to a count. Net-sheet line amounts, counter rows and band keys would then be pinned. `test_options`, `test_preapproval_cap` and parts of `test_counter_respects_the_sellers_last_counter` become REMOVE.
3. **Give timeline flags and agent_notes, and CMA warnings, a stable key** (`{"key": ..., "text": ...}`), as offer flags already carry `topic`. Also add the missing offer topics listed above, and keep `topic` on merged agent flags. About 30 of the REWRITE rows exist only because no key is there to assert.
4. **Optionally, move the prototype-cost variants into golden fixtures.** These are `test_offer_engine.MatchesPrototype.*` and `test_buyer_offer_strategy.test_seller_net_with_prototype_costs`. They pin exact nets on modified inputs, so today they need a hand edit whenever golden is re-approved.
5. **Add a slow tier.** `test_mock_contracts.py` takes about 25 s of the 38.6 s run. `test_every_scenario_builds` takes 9.3 s, `test_keys_render_through_the_skills` 5.5 s and `test_scanned_copy_has_no_text_layer` 2.5 s. They are tooling tests, so a `make test-slow` split, or a skip unless `SLOW=1`, would make `make test` much faster without losing them.
