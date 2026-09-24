# What Client Materials Must Show

Read this when the agent works outside Florida, holds more than one license, or asks what their documents must show. It's a starting point for the conversation, not legal advice: the agent's broker decides what their materials carry, and state rules change.

| State | What Advertising and Client Materials Commonly Need | Profile Fields |
|---|---|---|
| Florida | The brokerage's licensed name with the agent's name (rule 61J2-10.025) | `brokerage` |
| California | The agent's DRE license number on first-point-of-contact materials, and the responsible broker's identity (Bus. & Prof. Code 10140.6) | `license` or `licenses`, `brokerage` |
| New York | The broker's name, office address and phone in advertising (19 NYCRR 175.25) | `brokerage`, `brokerage_address`, `brokerage_phone` |
| Texas | The broker's name in advertising; websites link the Information About Brokerage Services and the Consumer Protection Notice (TREC rules) | `brokerage`; the links go on the agent's website, not in these files |

Every file the skills make prints the agent's name with the brokerage, the license when given, and a brokerage line (license, office address, phone) in the closing notices when those fields are set. Anything else the broker requires (a statement, a disclosure) goes in the profile's Disclaimers section, which every file prints verbatim.

When a state isn't listed, ask the agent what their broker requires rather than guessing.
