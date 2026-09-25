# Fair Housing

Read this before writing any text a client or the public could read: report findings, deck and card text, watch items, questions for the other agent, reasons, clause language, and chat text the agent may forward. It applies to advice to the agent too, because steering happens in conversation as well as in writing.

This is how the skills apply the rules, not legal advice. The agent's broker is the authority on compliance.

## Contents

- The Core Rule
- Protected Classes
- Wording
- Topics With Their Own Rule
- Choosing Between Buyers
- When the Agent Asks for It
- Sources

## The Core Rule

Describe the property, the numbers and the terms. Never describe people: not who the home suits, who should buy it, who lives nearby, or who the neighborhood is right for. A statement that shows a preference, limitation or discrimination based on a protected class is unlawful in any form, written or spoken (42 U.S.C. 3604(c), 24 CFR 100.75). So is steering: nudging a buyer toward or away from an area by how it is described, including exaggerating its drawbacks or saying they wouldn't fit in (24 CFR 100.70(c)).

## Protected Classes

- **Federal (Fair Housing Act):** race, color, religion, sex, disability, familial status (children under 18, pregnancy, custody), national origin.
- **Always treated as protected:** sexual orientation and gender identity. The REALTOR Code of Ethics (Article 10) and many state and local laws protect them explicitly.
- **State and local:** many places add more (age, marital status, source of income, military or veteran status, and others). Florida and Texas state law match the federal list; cities and counties can add to it. Apply every class listed in the market's `fair_housing.extra_protected_classes` as well. Built in for Florida counties (from each county's code, checked September 2026, with the source in `fair_housing.source`): Miami-Dade, Orange, Hillsborough and Pinellas, which add classes such as age, marital status, sexual orientation, gender identity and, in Miami-Dade and Orange, source of income. Cities (Orlando, Tampa, St. Petersburg and others) have their own ordinances that aren't built in: ask the agent, and for any other county or state nothing is built in. When the agent mentions a local class that isn't there, apply it for the rest of the conversation.

## Wording

| Avoid | Why | Write Instead |
|---|---|---|
| "Perfect for a growing family", "ideal for young professionals", "great for retirees", "family-friendly street" | Says who the home suits (familial status, age) | The features: "four bedrooms, fenced yard, cul-de-sac lot" |
| "Adults only", "no kids", "mature neighbors" | Limits familial status | Leave it out. A 55+ community is described as 55+ only when it qualifies as housing for older persons and says so |
| "Safe neighborhood", "low-crime area", "good part of town", "rough area" | Safety claims steer, and are rarely provable | Leave it out. If the client asks, point them to the local police department's public crime data |
| "Great schools", "A-rated schools", "top school district" | School quality is a common proxy for steering | Taxing district and millage are costs and are fine. If the client asks about schools, name the assigned school when known and point them to the district to verify |
| "Up-and-coming", "transitional", "exclusive", "diverse", "changing neighborhood" | Coded descriptions of who lives there | Market facts: days on market, price trend, distance to named amenities |
| Any mention of the racial, religious or ethnic makeup of an area | Never volunteered (REALTOR Standard of Practice 10-1) | Leave it out |
| "Christian home", "near our church community" | Religion | Leave it out |
| "No wheelchairs", "must be able to climb stairs", "able-bodied" | Disability | Describe the home: "second-floor primary suite, no elevator", "step-free entry", "grab bars in the hall bath" |
| "No Section 8", "no vouchers", "must have W-2 income", "VA buyers need not apply" | Source of income, where local law protects it (Miami-Dade and Orange County, Florida, among others), and a financing type standing in for a person | Describe terms, not buyers: "Seller prefers offers with a 10-day inspection period". On the seller side, compare loan programs by their mechanics (appraisal rules, timelines), never by who uses them |

**Allowed, per HUD's advertising guidance:** describing the property and its rooms ("family room", "walk-in closet", "two bedrooms", "master bedroom", though "primary bedroom" is the common term now), services and rules ("no pets", "no smoking"), and physical facts about the area ("quiet cul-de-sac", "walking distance to the park", "0.4 miles to the lake"). A feature is never the problem; attaching it to a kind of person is.

**Pointing to a source is fine.** "School ratings are available from the district" and "crime data is on the sheriff's site" pass the render check, because they name the official source instead of making a claim. "Great schools" and "low crime" are claims and are blocked either way.

**Proper names.** Address, subdivision, city, county and school fields aren't checked. When a proper name in prose trips the check (a place like "Asian Community Center"), keep the name and add it to the data file's allow list with a reason: `"fair_housing_allow": [{"phrase": "Asian Community Center", "reason": "name of the community center 0.3 miles away"}]`. Use it only for names, never to let a description through. The render prints each entry it used, so tell the agent.

## Topics With Their Own Rule

- **Neighborhood sections** in a CMA are about the market: sales, prices, days on market, supply, and named amenities with distances. Never about the people who live there.
- **Who will buy.** Talk about buyer behavior by price and terms ("buyers at this price mostly use conventional loans with 5 to 10% down"), never by who the buyers are.
- **Photos and marketing plans** (seller launch plans): describe the property, the price and the process. Marketing aimed at, or away from, a group of people is not a plan the skill writes.
- **Accessibility:** describe features precisely. Never say who can or can't live there.
- **Equal Housing Opportunity.** Marketing pieces (a listing presentation, a launch plan, anything that advertises a listing or the agent) carry the Equal Housing Opportunity statement or logo, per HUD's advertising guidance (24 CFR 109, still used as the standard). The deck adds the statement automatically unless the agent's profile disclaimers already include it. Reports for a client (a CMA, an offer review) print the agent's disclaimers; if the brokerage requires the EHO statement on every document, put it in the profile's disclaimers and every file carries it.

## Choosing Between Buyers

For seller-side offer reviews. Judge every offer only on price, terms, financing mechanics, contingencies, deposits, timing and documented proof (approval letters, proof of funds). Never on names, photos, letters, family, age, language, accent, nationality, religion or anything else about who the buyer is.

- **Loan type is a term, not a person.** Explain what it changes (appraisal standards, required repairs, timelines, seller-paid costs) and price that into the comparison. Don't describe the buyer through it.
- **Where the market lists source of income or military or veteran status,** don't recommend refusing a loan type outright; compare its terms and suggest the agent confirm with their broker.
- **Letters, photos and personal details** from buyers are not read, summarized or scored. Say they were set aside.

For buyer-side offers: no personal letters, photos or buyer background in the offer package.

## When the Agent Asks for It

Don't write the problem version. Say in one sentence why (fair housing, briefly, no lecture), then give the compliant version that still makes the point: "I'll leave out 'great for families' because it can read as a familial-status preference under fair housing rules; here it is with the features that make that case: four bedrooms, a fenced yard and a cul-de-sac." If the agent insists, keep doing the rest of the work without that part. Don't flag innocent wording (like "family room") or accuse the agent of anything.

## Sources

- Fair Housing Act, 42 U.S.C. 3604(c) (discriminatory statements) and 3607(b) (housing for older persons).
- 24 CFR 100.75 (discriminatory advertisements, statements and notices) and 100.70(c) (steering).
- HUD, "Guidance Regarding Advertisements Under Section 804(c) of the Fair Housing Act," January 9, 1995.
- National Association of REALTORS, Code of Ethics, Article 10 and Standard of Practice 10-1.
