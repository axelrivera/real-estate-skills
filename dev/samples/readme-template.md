<!-- Template for samples/README.md, filled in by make samples (dev/samples_readme.py). Each {{pattern}} becomes a link to the matching file in samples/ with its page, slide or event count. -->
# Sample Output

One sample of every file the skills produce, for preview. All of it is mock data: the agent (Jordan Avery, Sample Realty), the clients, the addresses, the neighborhoods and the MLS numbers are fictional. Seminole County and the public data sources are real because the Florida tax math depends on them. Every page is marked "Sample Data".

Each skill can also answer in chat as a markdown summary; only the file outputs are shown here. Regenerate these files and this page with `make samples` (the text is in `dev/samples/readme-template.md`).

## Buyer CMA

{{buyer-cma/*-Buyer-CMA.pdf}}. A buyer-side comparative market analysis for a renovated pool home listed at $474,900. It opens with a one-page summary and a suggested opening offer, target and walk-away price, then covers the full listing history, five adjusted comps, a price-vs-size scatterplot, the competition, market conditions, taxes at the buyer's price, payment scenarios, price vs. seller credit, watch items and questions for the listing agent.

## Seller CMA

- {{seller-cma/*-Seller-CMA.pdf}}. The listing-side analysis for the same home: a recommended list price and supported range, adjusted comps, the scatterplot, competition, market conditions, three pricing strategies with estimated net proceeds, what buyers would pay per month at each price, a launch plan and the documents needed from the seller.
- {{seller-cma/*-Listing-Presentation.pptx}}. An editable listing presentation with the same numbers, for the listing appointment.
- {{seller-cma/*-Listing-Presentation.pdf}}. The same presentation as a PDF, the backup copy delivered with the PPTX.

## Buyer Offer Strategy

- {{buyer-offer-strategy/*-Offer-Options.pdf}}. An FHA buyer competing with two other offers on a $365,000 listing. It shows the recommended offer inside the buyer's limits, the alternatives and what each changes and costs, and how the offer scores against the competition from the listing agent's side.
- {{buyer-offer-strategy/*-Offer-Package.pdf}}. The worksheet for writing the recommended offer on the FR/BAR AS IS contract: contract entries by paragraph, riders, draft language for additional terms, the offer package checklist and what to request from the seller after acceptance.

## Contract Timeline

- {{contract-timeline/*-Contract-Timeline-*.pdf}}. Every deadline in the executed FHA contract from the buyer's side, from the Effective Date and deposit through inspection, loan approval, title, walk-through and closing, with who owes each one and what happens if it's missed.
- {{contract-timeline/*-Contract-Timeline-*.ics}}. The same deadlines as a calendar file to import into Google Calendar, Outlook or Apple Calendar.

## Seller Offer Review

- {{seller-offer-review/*-VA-Offer-Review.pdf}}. One offer on a $515,000 listing: a VA offer above list with a seller credit and a small deposit. It opens with a one-page summary: the recommendation to counter, the counter terms and the seller's net as offered, if the appraisal or inspection goes badly and with the counter. The detail pages cover the net sheet, the contingency timeline, a terms review, a certainty scorecard, risk flags, a verification checklist and questions for the buyer's agent and the loan officer.
- {{seller-offer-review/*-Multiple-Offer-Review.pdf}}. The same listing once a second offer arrives, a conventional offer at a lower price. For each offer it shows the seller's net as offered and if the appraisal or inspection goes badly, a certainty score and risk flags, then ranks them and recommends accepting the conventional offer.
