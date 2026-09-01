---
description: Where do things stand? Catch the owner up and triage the inbox
---

Give the owner an honest picture of where everything stands, then tidy as you
go. Cheap first, model second: most of this is reading files, not thinking.

## Procedure

1. **Run the free computations first:**
   ```
   python3 brain/tools/gitsync.py --pull
   python3 brain/tools/model.py
   python3 brain/tools/sync.py
   python3 brain/tools/sessions.py
   python3 brain/tools/news.py fetch --explain
   ```
   The pull brings in what the other machine (the always-on home) pushed —
   never fatal, and a conflict leaves this machine's version in place.
   The first prints what is overdue, needs a chase, or is going cold — that
   output is the skeleton of your briefing. If it prints a STALE WORDING
   section, fix those lines in workstreams.md before briefing: reword each to
   what is true today (past tense, or the real next step), and where the truth
   is unknown — did the thing happen? — add the question to questions.md
   rather than guessing. The second refreshes the mirror of
   their project folders. The third prints the Sessions page's loose ends:
   conversations waiting on an answer, stopped mid-plan, or holding queued
   messages — unfinished business the owner may have forgotten. Name any in
   the briefing ("the Zephyr conversation is still waiting on your answer
   from Tuesday"); silence would let it rot invisibly.

2. **Read `brain/workstreams.md`, `brain/next.md`, `brain/inbox.md`**, the
   pending files in `brain/queue/`, and the last two digests in
   `brain/daily/` — they are what past sessions decided and learned.

3. **Brief the owner, in about six sentences, plain language.** Lead with
   what needs them: anything overdue, anyone to chase, anything going cold.
   Then what is quietly fine. Then anything queued or in the inbox. No file
   names in the prose — say "the deposit refund", not "workstreams.md line 40".
   If `brain/season.md` has a season running low — few weekends left against
   many unslotted ideas — one sentence of push, once ("9 weekends left and 7
   ideas without a day; slot two or drop two"). Never more than a sentence,
   and never when the tray is small: the bucket must stay the fun part.

4. **Farm any waiting journal entries.** List `brain/journal/` against
   `brain/journal/.farmed.json`; entries not recorded there get farmed the
   way `/journal` says (Last dates, tasks, ticks — never rewriting her
   words), then recorded. A refused read means this run is unattended and
   the journal is private to it — skip without retrying.

5. **Triage the inbox.** For each line in `brain/inbox.md`: attach it as a
   task to the workstream it belongs to, promote it to a new workstream if it
   is clearly one, or ask the owner if you genuinely cannot tell. Remove
   triaged lines. Do not silently drop anything.

6. **Fix stale metadata while you are there.** A workstream whose tasks are
   all ticked but whose Status is still Moving; a Done item still sitting in
   `next.md`; a Ball line with no Since date. Repair quietly, mention briefly.

7. **Rebuild the pages:**
   ```
   python3 brain/tools/build.py
   python3 brain/tools/map.py
   python3 brain/tools/rooms.py
   python3 brain/tools/proto.py
   ```

8. If there are pending queue items, say so and offer to run `/queue` —
   they outrank everything else, because they are what the owner asked for.

9. **Money, only if it needs her.** Read `brain/finance/summary.json` if it
   exists (a few hundred bytes — never read `brain/finance/raw/`, which is
   her raw transactions). Say one line about money only when one of these is
   true: a bank's consent lapses within 14 days (name the date — renewing is
   `python3 brain/tools/finance.py link ...` plus one approval on her
   phone); the current month's spending is already 1.5× the three-month
   average; or the EUR total is under `finance.floor` in config.json, if she
   has set one. Otherwise the page's Money card carries the numbers and the
   brief stays quiet about them.

10. **Trips carry a settle-up.** Whenever a trip with an end date enters the
   brain — from the inbox, a dump, or a new event task — attach a companion
   task in the same workstream: `- [ ] Settle up the money from <trip> —
   who paid what, square it (waiting until <day after return>) ~15m`. It
   stays parked until she is home, then surfaces on its own.

11. **The stakes sweep — dates aren't the only weight.** The ranking runs on
    dates, decay and whose hands things are in, so an undated task can hide
    forever inside a healthy workstream. Once per brief, read the open tasks
    of live workstreams for content the metadata can't see: safety (fire,
    water, electrics), legal or tax exposure, health, a season or
    counterparty about to close. Surface at most three, say plainly why each
    matters now, and propose a date or (urgent) — her call. The
    wildfire-trees task hid this way for a week; this sweep exists so that
    never repeats.
