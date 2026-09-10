---
description: End of session — fold what happened back into the brain
---

Whatever happened this session, write it back so the brain never goes stale.
A brain updated from memory next week is fiction; do it now, while it is true.

## Procedure

0. **Commit the pre-wrap state:** `git add -A && git commit -m "pre-wrap snapshot"`
   (skip silently if the tree is clean). This is the undo for everything below.

1. **Update `brain/workstreams.md`** for anything that moved this session:
   - Progress on a workstream → tick its tasks, set `Touched` to today,
     update `Next` to the new next action.
   - The ball changed hands → set `Ball` AND `Since` together. Never one
     without the other; `Since` powers the chase reminders.
   - Something finished → Status: Done. Something abandoned → Dropped, with a
     line of why in its notes. Never delete a workstream — Done and Dropped
     entries are the record.

2. **Re-rank `brain/next.md`.** Open work only, 3–5 items, one clear top
   item. Finished items move to the `## Done` trail (newest first, one line
   each) and the list renumbers from 1.

3. **New decisions → append to `brain/decisions.md`.** Only real ones — a
   choice the owner would be annoyed to see re-opened. Never edit past
   entries.

4. **Anything the owner said in passing that is really a new commitment**
   ("I should sort out the car insurance") → a line in `brain/inbox.md` if
   small, a workstream if clearly not.

5. **Close the loop on queue items** you worked: `status: done` or
   `dropped`, plus an `## Outcome` section in the owner's language.

6. **Write the session digest** to `brain/daily/YYYY-MM-DD.md` (append if the
   file exists — several sessions a day is normal). Under 15 lines:
   ```
   ## HH:MM
   Context: what this session was about
   Decisions: what got decided, and why (— if none)
   Facts learned: durable new facts (— if none)
   ```
   **Promote any durable fact into `brain/about-me.md`** at the same time —
   the digest is the log, about-me is the truth.

7. **Big-question evidence.** If the owner keeps a
   `brain/rooms/big-questions.md` and the session produced real evidence
   bearing on one of their standing life questions, append ONE dated line
   under the matching heading. Evidence is what happened, not
   interpretation; never delete an old line, never push toward an answer.
   Most sessions produce none — skip silently.

7b. **The weekly contradiction sweep.** If `brain/.last-sweep` is missing or
    older than 7 days: with the files already in this session's context,
    look for the same fact told two different ways across about-me.md,
    workstreams.md, people.md, goals.md and routine.md. Fix the ones where
    one side is clearly current (correct the stale file); put the ones you
    cannot settle in `brain/questions.md` as one checkbox each, naming
    both versions. Then `touch brain/.last-sweep`. Read nothing extra for
    this — if a file is not already loaded, it is not swept this week.
    Under 7 days: skip silently.

8. **Rebuild — this is not optional:**
   ```
   python3 brain/tools/build.py
   python3 brain/tools/map.py
   python3 brain/tools/rooms.py
   python3 brain/tools/proto.py
   ```

9. **Commit:** `git add -A && git commit -m "wrap: <one line on what moved>"`

10. **Confirm in two sentences:** what you recorded, and the single most
    important thing waiting for them next time.
