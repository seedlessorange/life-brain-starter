---
description: Keep her account of the day in her own words, then quietly farm it into the brain
---

The owner is telling you what happened in her life — typed, dictated, or as
a reply to the evening Telegram check. This is a **journal entry first** and
brain input second. Two jobs, in this order.

**Entries from the page or Telegram are already kept** — `serve.py` writes
them to `brain/journal/` mechanically the moment they arrive, no Claude
involved. For those, Step 1 is done; your work is Step 2, on every entry not
yet farmed: read `brain/journal/.farmed.json` (a map of entry date → date
farmed; a missing file means nothing is farmed yet), farm what's missing,
then record it there. Step 1 below applies when she journals directly in a
session and no file exists yet.

## Step 1 — keep her words

Write the entry to `brain/journal/YYYY-MM-DD.md` (create the folder if it is
missing), dated for **the day it describes**, not the day it arrives:

- An entry written in the evening is about today.
- An entry written in the morning that talks about "yesterday" or reads in
  the past tense about a finished day gets yesterday's date.
- When genuinely unsure, use today and say so in your report.

Format — frontmatter, then her words untouched:

```
---
written: YYYY-MM-DD
via: page | telegram | session
---

<her words, verbatim — typos, half-thoughts and all>
```

**Never rewrite, tidy, or summarize the entry itself.** Like the room notes,
this file is her voice; the whole value of a journal is that it is what she
actually said. If the same day gets a second entry, append it under a `---`
separator with its own `written:` line — never merge or reorder.

If the entry arrived as a transcript (`brain/transcripts/...`), the
transcript text is the entry; copy it in verbatim.

## Step 2 — farm it, without her asking

Read the entry once and quietly update the brain from it:

- **People.** Anyone she spoke to, saw, or met gets their `Last` date set via
  `python3 brain/tools/people_update.py "Name=YYYY-MM-DD" ...` (one call, all
  names). Match against `people.md` names AND `Also:` aliases; distrust
  transcribed spellings exactly as `/dump` does. Someone clearly new is a
  question, never an automatic new entry.
- **Promises and tasks.** "I told X I'd..." files as a task or promise on the
  right workstream or person. A date said out loud becomes a real `(due ...)`.
- **Done things.** If the entry says she finished something the brain tracks,
  tick it and set `Touched:` — the entry is her saying so, which is the
  evidence Done requires.
- **Facts.** A durable new fact about her life goes to `about-me.md`;
  a decision she states goes to `decisions.md`.
- **Feelings and worries stay in the journal.** They are the point of the
  entry, not noise — but a worry that names a concrete undone thing can also
  land as a task, phrased as the action.
- Follow-up questions go to `brain/questions.md` when there is no
  conversation to ask in.
- **Leave the morning trace.** Append one line to `brain/journal-trace.md`:
  `- YYYY-MM-DD — <one neutral sentence on the day's shape>`. Shape means
  energy, screen vs physical, roughly who she was with (people.md names
  only) — e.g. `- 2026-08-24 — physical day at Faverolles with the family,
  barely any screen`. This file lives OUTSIDE the private journal on
  purpose: the unattended morning plan reads it so it knows what yesterday
  was like. Neutral means no quotes, no feelings, nothing she would mind a
  scheduled run reading — when in doubt, say less. Never rewrite a past
  line; she may delete any of them.
- **Mark it farmed.** Update `brain/journal/.farmed.json` with the entry's
  date so the next session doesn't farm it twice. The Journal habit needs no
  update — it counts the entry files by itself.
- **Only attended sessions farm.** If a read of `brain/journal/` is refused,
  this run is unattended and the journal is private to it — by design. Skip
  farming entirely, don't retry, and leave `.farmed.json` alone.

## Step 3 — rebuild and report

- Rebuild: `python3 brain/tools/build.py && python3 brain/tools/map.py && python3 brain/tools/rooms.py && python3 brain/tools/proto.py`
- Report (or write the Outcome) in two short parts: "kept as your
  <date> entry", then what the farming changed — people dated, tasks filed,
  anything ticked. Never read her entry back to her.

## Rules

- The journal is append-only. Never edit a past day's entry, never delete
  one, never "clean up" the folder.
- One file per day, `YYYY-MM-DD.md`, nothing else in `brain/journal/`.
- This command must stay cheap: one read of the entry, batched writes. It is
  a nightly habit, and a habit that costs a full run dies.
