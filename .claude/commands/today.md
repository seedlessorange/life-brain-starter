---
description: Write today's plan — short, achievable, and honest about yesterday
---

Write `brain/today.md` — the plan for today. This is the file the owner
reads with their coffee, so it has one job: a list they can actually finish.

## Read first

1. `brain/today.md` as it stands — yesterday's plan. What got ticked, what
   didn't? Unfinished items either roll forward (at the top, named as
   carry-overs) or get consciously dropped with a one-line reason, so that
   nothing leaves the plan without the owner seeing it go.
   **Say each thing once.** The closing section is for what is NOT in
   today's list — what you deliberately left out and why. Anything already
   in the three or the chases must not be restated there; seeing the same
   task three times is what makes the page feel like it is nagging.
   Anything already ticked is finished business: it does not need a line
   explaining that it carried.
   **The evening check leaves markers — honour them:**
   - `(carrying YYYY-MM-DD)` = the owner explicitly chose to roll it
     forward. It goes to the TOP of today's list (marker removed). If
     yesterday's plan shows it was already a carry, say so in the intro —
     "third day carrying this" — because a task carried three times is
     either mis-sized or mis-wanted, and the plan should say which it
     suspects.
   - `(dropped YYYY-MM-DD)` = they retired it at the evening check. It
     stays dropped. Do not resurrect it unless its workstream urgency
     changed underneath them (then name that plainly: "you dropped this
     Tuesday, but the deadline moved").
2. `brain/workstreams.md` via `python3 brain/tools/model.py` — the flagged
   items (overdue, chase, cold) are today's candidates.
3. `brain/queue/` — anything the owner asked for that is still pending.
4. `brain/synced.md` — what the project folders say is open. **Compare with
   yesterday**: `git -C <brain root> diff HEAD@{1.day.ago} -- brain/synced.md`
   (fall back to `git log -p` if the reflog is short). Anything genuinely NEW
   from a folder that looks like real work gets one line in a "New from your
   folders" section at the bottom of the plan — a suggestion, never silently
   promoted into a workstream. For sources whose files are prose rather than
   checkboxes, a changed file date alone is the signal: name the file that
   moved.
5. `brain/goals.md` — the finish lines the owner set, per project. A goal
   due within two weeks makes its project's tasks strong candidates for the
   three; a goal past its date is treated exactly like any overdue item and
   named plainly ("the beta was due Tuesday"). Self-imposed dates are real
   dates — that is the whole point of writing them down.
6. `brain/habits.md` — do not list habits as tasks (the page tracks them),
   but if a habit's week is mathematically at risk, say so in one line.
7. `brain/about-me.md` — the owner's real constraints. The plan must fit
   the life they are actually living this month: a work-from-home week and
   a travel week are different sizes.
8. `brain/config.json` → `"week"` — the fixed skeleton of the week, if the
   owner has filled one in. **The day's fixed commitments decide the plan's
   shape:** state the day's skeleton in one line at the top ("meetings till
   4, gym at 7"), then fit the three into the real gaps — which usually
   means smaller tasks on committed days. If a `week.days` entry names a
   sport or class, that counts as the day's exercise; don't plan a second
   workout. Entries may be missing — never invent them.
9. **If `"calendar": true` in config** — run
   `python3 brain/tools/calendar_read.py --days 1` for today's REAL events
   (titles and times, read locally from the Mac Calendar app and any
   subscribed ICS feeds). They join the day's skeleton
   line, and the plan fits around them — an event is a fact, not a
   candidate. Glance at `--days 7` too: anything big looming inside the
   week deserves one line of warning at the bottom. If the read returns
   nothing, say nothing (no events and no access look identical — never
   claim an empty day from an empty read).

## The rules of the list

- **Three tasks, not five — and one from each horizon.** `model.py` labels
  every live workstream `now`, `push` or `slow`:
  - **`now`** — a clock is running on it. Take the top one. This is the
    slot deadlines win.
  - **`push`** — the owner set a Focus, or a goal in `goals.md` is pulling.
    Take the one touched least recently.
  - **`slow`** — real work with nothing forcing it. Take the most
    neglected.
  Drawing all three off the top of one sorted list is what starves the long
  horizons: a deadline beats an ambition every single morning, and by
  induction the ambition never gets a morning at all. If a pool is empty,
  fill from `now`, and say in the intro that everything today is
  deadline-led. Keep the old balance rule as a tiebreak within a pool —
  never three from the same front unless a real deadline forces it.
- **Rank on when the work must happen, not when the thing happens.** A trip
  on the 20th needs its ticket a fortnight earlier; `model.py` computes
  that second date (`act_by`) from the verb, or from an explicit
  `(by YYYY-MM-DD)`. Read `pressed_task` / `pressed_act_days` — a negative
  number means the owner is already past the moment to act, and the plan
  must say so in those words ("the seat should have been booked eleven days
  ago"), not "due on the 20th".
- **Fix what the ranking cannot see, before ranking.** Run
  `python3 -c "import sys;sys.path.insert(0,'brain/tools');import model as M;
  items=M.load();print(M.blind_spots(items));print(M.prep_gaps(items))"`.
  A task naming a date only in its words is sorted as undated, and a
  meeting living in a note is invisible entirely. Offer the encodings in
  the plan (one line, at the bottom) — never write dates into the owner's
  file on a guess.
- **Quote task wording EXACTLY.** When a plan item is a workstream task,
  its checkbox line must repeat the task's text verbatim — the page mirrors
  a tick on Today into the workstream by matching that text, and a reworded
  line breaks the mirror (the task then looks undone forever). Coaching
  colour ("twenty minutes, external deadline") goes in the intro paragraph
  or after the list, never inside the checkbox line.
- **Don't list the quick wins.** The page already surfaces small,
  time-pressed tasks in its own "Off your plate in minutes" strip, weekend-
  aware (office-hours errands wait for Monday). The three are for what
  needs a real block of attention.
- **At least one of the three is not computer work.** Productive
  procrastination is the classic failure mode — the screen work never needs
  the reminder; family, admin, health and the physical world do.
- **Call people by the name in `people.md`.** A plan that renames someone
  is using a word the owner did not choose. Use the entry's name, always.
- **Never plan contact with someone the owner is WITH.** Before writing
  "call X" or "message X", check `people.md`: anyone with a `Hold:` date is
  physically with them (that is what the hold means), and so is anyone
  whose `Where:` matches where the owner is this month. Being together is
  not a reason to schedule a phone call. If the relationship still deserves
  something, the task is a real-life one ("ask them about X over lunch"),
  never a call.
- **Relationships follow geography.** When a chase or relationship item
  makes the list, prefer people whose `Where:`/`Tags:` match where the
  owner is this month — especially anyone marked Focus. Being in the same
  place is the cheapest moment a relationship will ever get.
- **Each task is one sitting** — under an hour, phrased as a physical
  action ("email X asking Y", not "make progress on X"). If a flagged item
  is bigger than that, the task is its first concrete step.
- **Chases are free.** A chase is two minutes, so up to two chase items can
  ride along in their own short section without counting against the three.
- **If the calendar is against them** (they say they have no time today),
  the honest plan is one task and the chases. A plan that ignores reality
  trains the owner to ignore the plan.
- **On a light day, surface one spark.** If nothing is overdue and the list
  came out short, read `brain/interests.md` (if it exists) and add ONE
  spark as an unnumbered last line — `*If there's slack:* <spark>` — chosen
  for where the owner is. Never as a task, never on a heavy day, and never
  the same spark two days running.
- **One line of push at the top.** Encouraging, specific, no cheerleading —
  name what finishing today's three actually buys them. Second person,
  plain words, no exclamation marks.
- **Openers (Full mode only — check `ai` in `brain/config.json`; skip when
  `careful`).** For up to two of today's tasks where you can genuinely
  start the work, START it and hand the owner the opening: the phone
  number looked up (WebSearch) and put in the task text; the first message
  drafted into `brain/drafts/` ready to approve; the travel options for a
  dated trip researched into the task's note with times and rough prices.
  An opener is never a send, a purchase, or a form submission — it is the
  hard first step done, so the owner's part is approving and finishing.
  Mark each in the plan: *"opener ready — the number is in the task"*. In
  `careful` mode, plan only.

## Format of `brain/today.md`

```
---
updated: YYYY-MM-DD
---

# Today — <weekday> <date>

<one line of push — what today's list buys the owner>

## Do these three

- [ ] <task 1 — the top priority>
- [ ] <task 2 — different front>
- [ ] <task 3 — different front>

## Two-minute chases

- [ ] <chase, if any>

## Not today, and why

- <what rolled forward or got dropped from yesterday, one line each — omit
  the section on a clean slate>
```

## Afterwards

- Update `Touched:` in `workstreams.md` for anything the plan pulled from,
  only if you actually advanced it while drafting (e.g. you drafted the
  email — put the draft under the workstream's notes and say so).
- Rebuild: `python3 brain/tools/build.py`.
- Tell the owner the plan in the terminal too, three lines, so they don't
  have to switch to the page.

Run this every morning. If it is run twice in a day, refresh rather than
duplicate — same file, same date, updated ticks preserved.

## Parked tasks

A task ending in `(waiting until YYYY-MM-DD)` is deliberately parked — the
owner could not start it yet. Do not put it in the plan, do not count it as
something they are failing to do, and do not remove the marker. It reappears
on its own the day it comes due, and that is when it belongs in the three.

## The calendar (only if enabled)

If `brain/config.json` has `"calendar": true`, run
`python3 brain/tools/calendar_read.py` first and plan the day around it. If
The owner has three meetings and one free hour, the three tasks must fit
that hour — do not hand them a plan their real day has no room for. Mention
the shape briefly ("you've got a packed morning, so today's three are
small"). Titles and times only; never repeat private event details. If it
returns nothing, carry on as normal — calendar reading is best-effort and
off by default.

## Two honesty rules for the written plan

- **The weekday in the title must match the real date** — derive it from
  the actual calendar, never from memory ("Friday 15 August" on a Saturday
  makes the whole plan read stale).
- **The narrative must only lean on still-open items.** If it references
  yesterday's carries, check they are still open at write time.
