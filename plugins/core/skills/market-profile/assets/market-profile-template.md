---
profile: market
schema: 1
name: "{{market name}}"
state: "{{state}}"
area: "{{counties or cities}}"
mls: "{{MLS name}}"

closing_costs:
  {{closing cost settings}}

brokerage:
  {{brokerage settings}}

property_tax:
  {{property tax settings}}

holding_costs:
  {{holding cost settings}}

buyer_costs:
  {{buyer cost settings}}

contract:
  {{contract settings}}

cma:
  {{cma settings}}

mls_format:
  {{mls format settings}}

county_overrides:
  {{county exceptions}}
---

# Market profile: {{market name}}

{{one line: state, area and MLS}}

Used as context by the real estate skills. Keep this file in your Project files so every chat can use it. Anything not listed here uses the built-in defaults for {{state}}, where there are any.

## What's customized

{{short plain-language list of the agent's own values, e.g. "Title settlement fee: $850 (Seaside Title quote, 2026)"}}

## Notes

{{sources, dates, and anything the agent wants remembered about this market}}
