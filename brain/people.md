---
maintained-by: you and claude, together
---

# People

Not a contact list. A list of the relationships you have decided are worth
keeping warm, and whether they are.

One `## ` heading per person, then:

- **Circle:** which group they belong to. Your groups live in
  `brain/config.json` (`circles`) and are yours to change — the defaults are
  Inner, Close, Friends, Family, Dating, Work, Network, Acquaintances,
  One-off. Each group has a default rhythm and a `personal` flag (personal
  groups are draft-only: Claude can never message them for you).
- **Every:** the rhythm, independent of the group. This is the fix for
  "family I speak to weekly" vs "family I speak to quarterly" — both are
  `Circle: Family`, with a different `Every`. Leave it blank to use the
  group's default; set it (`weekly`, `3 days`, `monthly`, `quarterly`) to
  override.
- **How:** how you know them — one line, for the day a name goes blank.
- **Where:** where they live — powers "who's near me this season" and sane
  hours to call, since your people are scattered across countries.
- **Birthday:** `MM-DD` (or `YYYY-MM-DD`) — surfaces a few days ahead.

Checkboxes under a person are **promises** — things said in a chat that must
not evaporate with it. They tick, park and drop like any task, and surface in
your daily chases while open.
- **Ball:** `Me` if you owe them a message, `Them` if you are waiting, `Nobody`
  if it is even.
- **Last:** the date you last actually spoke. The page's "Spoke today" button
  writes this for you.
- **Focus:** `yes` for the handful you are deliberately investing in this
  season. Focus people surface sooner when they go quiet.
- **Also:** other names they appear under in your chat apps, comma separated
  — `Mom, Maman`. Without this the automatic sync cannot find them.
- **Why:** one line, for the days it feels like admin.

Free text under a person becomes collapsible notes — where you left it, what
they have going on, what to ask about next time.
