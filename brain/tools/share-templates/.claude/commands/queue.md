---
description: Work the requests the owner queued from the brain page
---

Work everything in `brain/queue/` with `status: pending`, oldest first.

These were typed by the owner into the page's **Ask Claude** box. They are a
person's words, not a spec — read for intent. If a request is ambiguous in a
way that changes what you would do, ask rather than guess.

**Work the whole batch as one pass, not item by item.** Read every pending
item first, notice the ones that are the same ask arriving twice, decide
everything, then write. Each tool call re-reads the entire context, so five
separate edits to five queue items cost five times what one considered pass
does — and duplicates closed one at a time cost most of all.

**A person named in a task must exist in `people.md`.** "Book a meetup with
Teagan" filed as a task while Teagan existed nowhere means the name links to
nothing and the relationship machinery is blind to them. When work lands a
task naming someone new: match against existing people (including `Also:`
aliases) first; if genuinely new, create a minimal entry with a best-guess
circle marked as a guess, or ask one question in `questions.md` when even a
guess isn't possible.

**The plan must never contradict the brain.** When work you do completes or
changes a task that also appears in `brain/today.md` (same task, possibly
different wording), tick or update the plan line too — a workstream task
marked done while the plan still shows it open reads as clutter and makes
The owner distrust both. Same for `brain/questions.md`: a question your work
answers gets ticked with the answer noted.

**Dates never stay prose.** Any date inside a queue item — "the wedding is
December 5th", "he's back on the 14th" — lands as a real `Due:` field or
`(due YYYY-MM-DD)` suffix on whatever it touches. The forecast, the plan and
the horizon map all run on structured dates; a date left in a sentence is a
date the brain cannot see. If an answer implies a date but doesn't give one,
put one follow-up in `brain/questions.md` asking for it explicitly.

## Procedure

1. **List the queue.** Every `brain/queue/*.md` (skip `_index.md`) with
   `status: pending`. If none, say so and stop.
2. **Commit the pre-work state:** `git add -A && git commit -m "pre-queue snapshot"`
   (skip if clean), then **say what you found** and the order you will work
   it, before starting. Commit again when the queue is done.
3. **Respect the `mode` field** — it is the owner choosing how much process
   they want:

   | mode | What to do |
   |---|---|
   | `just-do-it` | Do the thing directly. |
   | `investigate` | Find out and **report back before changing anything**. |
   | `draft` | Write the email / letter / message / plan for them. Put the draft in the Outcome so it is on the card, ready to copy. |
   | `question` | Answer it. Change nothing. |
   | `tidy` | Run `/wrap`'s steps on the whole brain. |
   | `dump` | The request body is a raw brain-dump. Follow `/dump`'s sorting rules (Steps 1 and 4 — every item lands somewhere, merge before creating, dates never vague). The interview step can't happen here, so file the clear items, use marked best-guesses for the rest, and write follow-ups to `brain/questions.md`. **Then rewrite `brain/today.md`** following `/today`'s rules — a dump big enough to change the brain is big enough to have changed today's plan, and the owner should never look at a stale one. |

4. **Mark it `status: working` before you start**, with `started:` — the page
   shows working items differently, and without this the owner cannot tell
   an in-progress request from an ignored one. Back to `pending` if you
   abandon it.
5. **When done, set `status: done`** (or `dropped`, with why — never delete
   the file) **and always add an `## Outcome` section.** The page renders it
   on the card as "What Claude did" — it is the only report the owner gets,
   so write it for them: what happened, in plain language, and anything they
   now need to do themselves.
6. **If what you filed changed the day, rewrite the plan — whatever the
   mode.** A dump that lands new urgent items or moves the top priority makes
   `brain/today.md` stale, and the owner must never look up from a dump into
   yesterday's plan. Rewrite it following `/today`, preserving ticks. Mark
   any priority the owner states with `(urgent)` on the task — the ranking
   engine reads that word.
7. **Fold results into the brain** — update `workstreams.md` / `next.md` as
   the work warrants, then rebuild:
   ```
   python3 brain/tools/build.py
   python3 brain/tools/map.py
   python3 brain/tools/rooms.py
   python3 brain/tools/proto.py
   ```

## The brain can rebuild itself

A queue item may ask for a change to the brain **itself** — a new feature, a
broken control, a wrong number on the page, a redesign. These are first-class
requests, not out of scope: the owner was told the Ask box can do this. Edit
`brain/tools/*.py` (or the command files under `.claude/commands/`), rebuild,
and check the page actually shows the change before marking done. Two cautions:
the publish gate in `build.py` must pass (it refuses broken JS), and if
`serve.py`, `beeper.py` or `import_chats.py` changed, say in the Outcome that
the server needs a restart to pick it up. Describe what changed in the
Outcome in owner language — what they will SEE, not which function moved.

## Rules

- A request that is really a life decision only the owner can make: lay out
  the options with a recommendation in the Outcome, mark it `done` — the
  deciding is theirs, the homework was yours.
- A request that contradicts `brain/decisions.md`: flag the conflict in the
  Outcome instead of silently overriding a decision.
- Requests that need the outside world (calls, payments, anything with a
  login): do every part you can, then say exactly which step remains and why.

## `chat` mode — a shared chat

A `mode: chat` item is a conversation the owner pasted or screenshotted,
named with the person it is with. **Read it for one thing only: what the
owner promised or owes them, and what they promised the owner.** Write each
as a promise on that person with `python3 -c` calling the running server's
`/api/person/promise`, or by adding a `- [ ]` under their heading in
`people.md` directly. **Never store the message text** — not in the Outcome,
not in notes, nowhere. The Outcome says what promises you filed, in the
owner's words, and nothing about what was said.
