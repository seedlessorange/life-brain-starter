---
description: A trip into a packing list, built from the trip, the place, the weather and her sizes
---

A packing list comes back before every trip, and each time who she is and
what the trip is get typed out again. This command reads
what the brain already knows instead.

## Procedure

1. **The trip.** Take it from `$ARGUMENTS`, or from the nearest dated trip in `countdowns.md`, `season.md` or `workstreams.md`. You need:
   - where she's going
   - the dates
   - what's planned (a wedding, the beach, a work week)
   - anything unusual, such as a dress code or hand luggage only

   Ask once, in one question, for whatever is missing.
2. **What the brain knows:**
   - her sizes in `about-me.md`, for anything she may need to buy
   - her routines in `brain/routines/`, since skincare and supplements travel with her
   - the season's plans for that place
   - the house she leaves from, because a trip out of the country house packs differently from one out of the city
3. **The weather.** Within a week of departure, run `python3 brain/tools/weather.py --place "<place>"`. Further out, use the typical weather for that month and label it as typical.
4. **Write the list** as a draft, with `kind: note` and `expires:` set to the departure date, in the file `brain/drafts/pack-<place>-<date>.md`.
   - Group the items by clothes, toiletries and routine, tech and chargers, documents, and trip-specific.
   - Write items as `- [ ]` so they paste into a notes app as a checklist.
   - Be specific where her notes allow: "the dress for Saturday's wedding" beats "formal outfit".
   - Count quantities from the number of nights.
   - Give each document its own line (passport, tickets, bookings), and never write the numbers themselves.
5. **Things to buy** get their own heading, with sizes filled in.
6. Rebuild the pages.
