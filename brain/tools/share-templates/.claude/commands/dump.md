---
description: Take a raw brain-dump (spoken or typed) and organize all of it into the brain
---

The owner is about to empty their head at you — spoken through dictation or
typed, in no order, mixing errands, deadlines, ideas, guilt, chores and
half-thoughts. Your job: **organize every last item into the brain, ask the
few questions that change where things go, and lose nothing.**

If they invoked this with text, that is the dump. If not, say:

> Talk. Don't sort, don't filter, don't finish sentences — just get it all
> out. Everything from every corner: work, family, money, people you owe
> replies to, things you're worried about. Say "done" when you're empty.

and wait. If they keep adding across several messages, keep collecting until
they say they're done.

## Step 1 — sort silently

Parse the dump into items. For each, decide its home:

| It sounds like... | It goes... |
|---|---|
| A project with multiple steps or an ongoing worry | A **workstream** (new, or merged into an existing one) |
| A single small action | A `- [ ]` under the closest workstream, or **Personal admin** |
| "I'm waiting for X to get back to me" | The **waiting** table, with who and since when |
| A real date ("essay due the 25th") | A `Due:` field on its workstream — dates are the one thing never left vague |
| A repeating intention ("I should run more") | A **habit** — but only with their yes, see Step 3 |
| A choice they keep circling ("should I drop Z?") | A direct question in Step 3, then **decisions.md** |
| Unclassifiable, but said | **inbox.md** — the net under everything |

Merge before creating: if it belongs to an existing workstream, it goes
there. New workstreams use the owner's actual areas (the fronts set up at
onboarding) unless something clearly needs a new one.

**People merge the same way — never duplicate a person.** Before adding
anyone, check `people.md` (names AND `Also:` aliases) with context, not just
string equality: a first name mentioned near a project usually means the
person already on file for that project. A confident match = update the
existing entry (new facts, promises, `Also:` alias if the dump used a
different name). A plausible-but-unsure match = do NOT create a second
entry; add one question to `brain/questions.md` ("Is 'X' the same person as
'Y'?") and file the info under the likelier one with a `(unconfirmed)`
note. Only a clearly new person gets a new entry.

**Distrust transcribed names.** Dumps are usually dictated, and
speech-to-text anglicises and mangles names constantly. For every person
name a dump introduces: if it is a common English name in an otherwise
non-English social context, sounds phonetically close to an existing
person, or is spelled two ways in the same dump — treat the spelling as
SUSPECT. File under your best guess and add a one-line check to
`brain/questions.md`. Never let a transcription error become a permanent
person.

## Step 2 — show the sort, compactly

Before writing anything, show the organization in plain language, grouped by
area — one line per item, with `(new)` markers and your guesses flagged:

> **Work** — 4 items into "Q3 handover", one looks time-sensitive (the
> insurance thing — guessing this month?)
> **Study** — new workstream "Thesis", 3 items, no dates given yet
> ...

## Step 3 — ask the follow-ups, in one batch

Only questions that change how something is filed, and no more than
**eight**, grouped by front. The ones that earn their place:

- **Dates:** "You said the essay is due 'soon' — what's the actual date?"
- **The ball:** "The application — are you waiting on them, or do they owe
  you nothing and it's on you?"
- **Weight:** "You mentioned Z in passing — is that a live thing or can I
  park it?"
- **Habits:** "You said you want to read more — track it as a habit with a
  weekly target, or is that a someday-thought for the inbox?"
- **Standing conflicts:** anything that contradicts a decision in
  `decisions.md` — flag it, don't silently override.

If they answer "just file it" or "you decide", stop asking and use your
best guess, marked in the file as a guess (`Why: (guessed — correct me)`).

**When the dump arrives through the page** (a queue job — no conversation to
ask in): do not hold anything back waiting for answers. File everything with
best guesses, and write each follow-up as a checkbox in `brain/questions.md`
— one line each, self-contained enough to answer cold. The page renders
these as an "answer me" list with a button per question; they are the
*interface* for follow-ups, not an afterthought in the report.

**Chase the date in the question itself.** Most follow-ups exist because a
date is missing — so ASK for it: not "do you know about the wedding?" but
"what DATE is the wedding?" A question whose answer could carry a date must
request the date explicitly. And when any answer or dump line contains a
date, it lands as a real `Due:` field or `(due YYYY-MM-DD)` task suffix —
the forecast and the horizon map run on those; a date left in prose is
invisible to both.

## Step 4 — write, rebuild, report

- File everything. **Every item they said lands somewhere** — when in doubt,
  inbox with a note, never dropped.
- Respect the format: exact field names, the fixed status vocabulary,
  `Ball` and `Since` set together, no two checkboxes with identical wording.
- New habits go to `habits.md` with the target they gave (push back once if
  the target smells aspirational, then accept their answer).
- Rebuild: `python3 brain/tools/build.py && python3 brain/tools/map.py && python3 brain/tools/rooms.py && python3 brain/tools/proto.py`.
- Report in their language: how many items, where they went, what you
  guessed, and the single thing that now looks most urgent — then suggest
  `/today` if the top of the stack changed.

## Rules

- **Never summarize items away.** "Various chores" is a filing failure;
  each chore they named is its own checkbox.
- **Don't multiply workstreams.** Twenty tiny tasks is one workstream with
  twenty checkboxes, not twenty workstreams.
- **Guilt is data.** "I feel bad about never calling my grandmother" files
  as a real item (Personal, with a Why), not as noise to skip.
- Re-runnable: this is not just for day one. A weekly re-dump merges into
  what exists — it must never duplicate items already tracked.

## If the dump asks you to search the computer

A dump that begins with an instruction to search the computer (from the
page's guided brain-dump) means: for any project or app named, match it to a
folder via `python3 brain/tools/discover.py --json`, read that folder's
README/CLAUDE/package to enrich the workstream with real context, and add it
to `config.json` sources. Report what you found. Never read outside the home
directory or open anything resembling secrets.
