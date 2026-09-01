---
description: Weekly events scout — refresh brain/events.md with what's on where they are
---

Find the events worth the owner's evenings — concerts, club nights,
exhibitions, fairs — for the coming ~6 weeks, wherever they currently are,
and rewrite `brain/events.md`. The Season tab renders it.

## Procedure

1. **The weekly gate, first, before loading anything else.** Read the
   `updated:` date in `brain/events.md`. If it is less than 6 days old and
   they did not explicitly ask for a re-scout this session, stop here and
   say so in one line. The night shift runs this most nights; skipping is
   the normal outcome.

2. **Load the taste file**: [brain/reference/going-out.md](../../brain/reference/going-out.md).
   It holds the music profile, the venue shortlists, and the scouting
   rules — they govern everything below.

3. **Work out where they are**: the nomadic-year table in
   `brain/about-me.md`, `weather.place` in `brain/config.json`, and the
   season dates in `brain/season.md`. If a season has a home base, prefer it even when a single weekend is
   elsewhere. If genuinely ambiguous, scout the base and say which you
   picked.

4. **Read `brain/season.md`** — what is already planned (avoid proposing
   clashes with slotted days) and which tray items an event could serve
   (a photo fair serves the camera items; a group-friendly night serves
   the cohort ones).

5. **Search the web** for the coming ~6 weeks: the city's venue shortlist,
   the artist watchlist, exhibitions and fairs matching their interests.
   Official venue and ticket pages over aggregators; note prices and
   doors; mark anything you could not verify `(unconfirmed)`. Batch the
   searches — this is the expensive step, keep it to one pass.

6. **Rewrite `brain/events.md`** whole: frontmatter `updated:` (today) and
   `where:`, then the sections — Club nights / Concerts / Exhibitions /
   Tech & learning / Fairs & one-offs / Watching for. Drop past items, cap
   ~30, at most one club pick per weekend, keep "Watching for" to real
   announcements worth catching. If the week found nothing new, keep the
   file honest and short rather than padded.

   One line per item, and **the URL is not optional**:

   ```
   - 2026-10-09 — Fakear at L'Olympia (French melodic) — €38.50 — https://…
   - 2026-10-08..2026-10-11 — Salon de la Photo, La Villette — €13 — https://…
   ```

   The page strips the URL into a Book button and turns a single date into
   a one-click "add to my season"; a range lands in the tray under its
   month instead. Add ` — unconfirmed` to any line you could not verify on
   an official page — it renders as a visible tag, which is the honest
   thing to show their.

7. **Rebuild the pages** (`build.py`, `map.py`, `rooms.py`, `proto.py`).

8. **Tell their the two or three finds that matter** — a watchlist artist
   announcing, something selling out, a find that fits a season item.
   In an unattended run, that note is the run's report text.

## Rules

- **Surface only.** Never book, buy, subscribe, create an account, or set
  an alert anywhere. If a find fits a season item that names people, the
  normal drafting rules apply — draft, never send.
- Public listings only; nothing behind a login.
- Slotting a day in season.md is theirs. Name the fit; write nothing there.
- This is a real web-search run — weekly on purpose. Do not lower the gate.
