---
profile: agent
schema: 2
name: "{{full name}}"
team: "{{team name}}"
brokerage: "{{brokerage}}"
license: "{{license number}}"
licenses:  # only when licensed in more than one state, or the type matters; otherwise use license
  - {state: "{{ST}}", type: "{{sales associate, broker associate or broker}}", number: "{{license number}}"}
brokerage_license: "{{brokerage license number}}"
brokerage_address: "{{brokerage office address}}"
brokerage_phone: "{{brokerage office phone}}"
phone: "{{phone}}"
email: "{{email}}"
website: "{{website}}"
brand:
  primary: "{{#RRGGBB}}"  # {{color name}}
  buyer_primary: "{{#RRGGBB}}"  # {{color name}}
  seller_primary: "{{#RRGGBB}}"  # {{color name}}
---

# Profile: {{full name}}

{{team name}} · {{brokerage}}

Used as context by the real estate skills.

## Brand Colors

{{color name}} for all reports.

## Voice

{{how the agent writes}}

## Disclaimers

{{disclaimers for documents}}
