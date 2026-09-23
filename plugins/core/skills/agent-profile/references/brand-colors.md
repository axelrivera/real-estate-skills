# Brand colors

Reports use one main color per side. Everything else (shades, tints, chart colors) is derived from it, so the agent only chooses one or two colors. Without any, buyer reports are blue and seller reports orange.

## Asking

Offer the three ways in plain words, and make skipping easy:

> If you want your reports in your brand colors, send your logo or another image, your website, or the color codes if you know them. Or skip this and reports use blue for buyers and orange for sellers.

## Reading the colors

- **Color codes:** use them as given (`#1F3A5F`, `1F3A5F` and `#abc` all work).
- **Image or website:** run `python3 scripts/extract_colors.py <image path or website>`. It returns:
  - `colors`: the main colors, strongest first, each with a `name` ("Navy") and whether it's too `light` for text
  - `suggestion.primary`: the color to propose
  - `suggestion.split`: present only when there are two strong, distinct colors
  - `suggestion.alternatives`: present when the image is only black, white or grey
  - `notes`: things to tell the agent, already in plain words

If the website can't be opened (some sites block automated visits), ask for an image of the logo or a business card instead.

## Confirming

Always confirm by name before saving, because a wrong guess ends up on every report:

- One color: "Your logo is mostly Navy. Use Navy for all your reports?"
- With a `split`: "Your logo has Navy and Gold. Use Navy for everything, or Navy for buyer reports and Gold for seller reports?"
- Black-and-white logo: "Your logo is black and white. Charcoal or Navy work well on reports. Which do you prefer, or would you rather keep the default colors?"
- Too light (`light: true`): "Gold is light, so reports use a darker gold for text and Gold for accents." It's information, not a question.

Only ask about separate buyer and seller colors when there's a `split` or the agent brings it up.

## Saving

- One color for both sides: `primary`.
- Separate colors: `buyer_primary` and `seller_primary` (no `primary` needed).
- Keep the color name as the comment after each code; it's how people reading the file know what it is.
- The image is only used to read colors. It isn't saved and doesn't go on reports.
