# The Condition Ladder

Condition is one level per home, from a fixed list. You pick the level for the home (`subject.condition`) and for each comp (`comps.cards[].condition`) from the listing's own words; compute.py adjusts each comp by the difference between the two levels' dollar values. Never type a condition amount on a card: a typed renovation, kitchen, bath or update adjustment stops compute.py and names the card.

## The Levels

Lowest first. The dollar value of each is over an original home, from the market (`cma.adjustments.condition_levels`; built in for Florida).

| Level | Pick it when the listing (or, for the seller's home, the seller) says | Florida value |
|---|---|---|
| `original` | Original, dated, needs updating, TLC, as-is, investor special; or nothing at all about updates (a listing with updates says so) | $0 |
| `cosmetic` | Paint, flooring, light fixtures, new counters on original cabinets; "updated" or "refreshed" with no kitchen or bath named | $5,000 |
| `baths_only` | Every full bath updated; kitchen original | $10,000 |
| `kitchen_only` | Kitchen updated (new cabinets, or new counters and appliances together); the baths original, or only some of them updated | $15,000 |
| `kitchen_and_baths` | Kitchen and every full bath updated; the rest (flooring, finishes) original or not mentioned | $25,000 |
| `full_renovation` | Renovated or remodeled throughout: kitchen, every bath, and flooring and finishes too | $45,000 |
| `new` | New construction, or gutted and rebuilt in the last few years | $50,000 |

## Rules for the In-Between Cases

- **Partly done counts as the level below.** One of two baths updated is not "baths"; a kitchen with new counters but original cabinets and appliances is `cosmetic`, not `kitchen_only`. So an updated kitchen with one refreshed bath and an original primary bath is `kitchen_only`.
- **"Updated" without saying what** ("updated pool home", "move-in ready", "renovated" with no rooms named) is `cosmetic`. "Fully renovated", "renovated throughout" or "completely remodeled" is `full_renovation`.
- **"Updated kitchen and baths"** is `kitchen_and_baths`, not `full_renovation`, unless the remarks also name new flooring or finishes throughout.
- **Systems aren't condition.** The roof goes by its age band and newer AC, water heater or windows by the documented-systems rate (`method.md`); neither moves a home up the ladder.
- **The seller's home** takes its level from what the seller describes today, never from an old listing of it. An update the seller can't document still counts for the level (it's what buyers will see), but say in `method_note` that it's from the seller.

When the listing is too thin to place a comp, pick the lower of the two levels it could be and say so in that card's bullets, in words.

## Outside the Built-In Market

With no built-in values (another state, or a home outside `cma.calibrated_for`), give `comps.condition_values`: `{level: dollars over an original home}` for every level used, from paired sales in the export or the agent's own rates, scaled to the price. Each level is worth at least the one below it. Say where they came from in `method_note`.
