---
description: First-time setup — guide a full brain dump and build the brain from nothing
---

This is the first fill of an empty (or nearly empty) brain. The owner is about
to talk through their whole life — spoken or typed. Your job is to guide the
ramble so no domain gets forgotten, collect all of it, and build the brain,
asking only the questions that change where something goes.

Do not treat this as a form. A form gets abandoned. Guide, then listen.

## Step 0a — which plan is paying for this

The brain runs on their own Claude subscription, and this very run is the
biggest single spend of their first day. Before the ramble, ask one question:
**Pro or Max?** Then set it and say what you set, in one line.

- **Pro** → `python3 -c "import sys;sys.path.insert(0,'brain/tools');import
  serve;serve.set_ai_plan('pro')"` — nothing runs unasked, Haiku by default,
  a $2/day ceiling that asks twice before a big run.
- **Max** → the same with `'max'` — the 7am plan writes itself, Sonnet by
  default, the day's tasks get prepared ahead of them.

Not sure, or they'd rather not say: use Pro. It is the careful one and
nothing is lost by starting there. Mention once that every piece of this has
its own switch on the Claude tab under Usage, and move on — this is one
question, not a settings tour. On Pro, also name the night shift as the one
setup step worth doing (`zsh brain/tools/setup_night.sh`): it moves the heavy
runs into a usage window their own day never wanted.

The page asks this same question with two cards before its dump box, so
someone who came through the page has already answered it — check
`ai_features()["plan"]` rather than asking twice.

## Step 0 — make it a conversation, not a form

Open warmly and put them at ease. Something like:

> Just talk to me — who you are, what's going on in your life, what's on your
> mind. Anything that feels relevant. There's no right order and nothing to
> fill in; I'll make sense of it and check with you before I write anything
> down. Type or talk, whichever's easier.

Then **let them lead**. Do not read a list of categories at them — that turns
a conversation into an intake form and they clam up. Instead, listen, and use
the seven areas below as *your own* mental checklist of what a full picture
covers. Follow what they give you, and when they slow down, ask a warm,
specific follow-up that flows from what they just said rather than jumping to
the next category:

- they mention a project → "what's the state of that, and is anything due?"
- they mention a person → "are you two in good touch, or is that one you've
  been meaning to reach?"
- they mention a worry → "is that a decision you're sitting on, or a thing on
  a deadline?"

The nine areas a complete picture covers (your checklist, not their script):

1. **Who they are** — where they are in life, where they live, what they study
   or build. This becomes `about-me.md`, the durable core.
2. **What fills their days** — projects, work, study. These become the fronts
   everything else is grouped under.
3. **The people** — family, close friends, the far-away ones they don't want
   to drift from.
4. **What's weighing on them** — deadlines, dread, an unmade decision.
5. **Loose threads** — what they owe someone, who owes them, replies pending.
6. **What they're building in themselves** — habits, and the honest frequency.
7. **The shape of their ordinary day** — when they wake, work, train, flag;
   plans have to land in real gaps. This becomes `routine.md`, in their words.
8. **What they enjoy and look forward to** — curiosities, hobbies, dated
   things they're counting down to, what this season of their life is for.
   These become `interests.md`, `countdowns.md` and `season.md` — the parts
   of the brain that never nag.
9. **Anything else** — small nagging things, or something that fits no box.

When they wind down, glance at the checklist and gently raise only what's
genuinely missing and likely to matter — "you didn't mention family, is that
by choice?" — phrased as curiosity, not as a gap in a form. One or two such
nudges, not seven.

## Step 1 — collect, don't file yet

Gather everything across however many messages it takes. Don't start writing
files mid-ramble; it breaks their flow and you'll file half-formed items.

## Step 2 — show the sort

When they're done, lay out the organisation in plain language, grouped by
front, before writing anything:

> Here's what I heard. **School** — a new front, with the thesis and two
> deadlines (I need the real dates). **Family** — staying close to your mum,
> and you owe your dad a call. **Habits** — exercise 3x, reading 4x. **One
> decision** — whether to move to Florida. Fifteen small things went to your
> inbox. Have I got it right, and what did I miss?

## Step 3 — the few questions that matter

Ask only what changes filing, batched, no more than eight:
- **Dates** for anything with a deadline.
- **Closeness + rhythm** for the people (which circle, how often).
- **Honest habit targets** — push back once if a number smells aspirational.
- **Whose court** for anything they're waiting on.
- Anything that contradicts something already in the brain.

If they say "you decide", use your best guess and mark it as a guess.

## Step 4 — build it

Write it all:
- Fronts become `Area:` values; each real project becomes a workstream.
- On-fire and promises become tasks, dated where dated. Promises about a
  specific person go under that person in `people.md`, not a workstream.
- Waiting items go to `waiting.md`; people to `people.md` with circle + rhythm;
  habits to `habits.md` with targets; the decision to `questions.md`; small
  things to `inbox.md`.
- The day's shape goes to `routine.md` (their words, lightly tidied);
  curiosities to `interests.md` (each with a small next Spark); dated
  things they look forward to become `countdowns.md` lines; if they talked
  about what this stretch of life is for, sketch `season.md` and let them
  edit it. Finish lines they name for a project go to `goals.md` under its
  room, dated with the normal `(due ...)` syntax.
- Then set `about-me.md` from what you learned about who they are — school,
  family, where they live, how they work. This is the durable core.
- Rebuild: `python3 brain/tools/build.py && python3 brain/tools/map.py && python3 brain/tools/rooms.py && python3 brain/tools/proto.py`.

## Step 5 — hand back

Tell them, in six sentences: what you built, the single most urgent thing, and
what you still need from them (usually a few dates). Suggest they run `/today`
tomorrow morning. **Nothing they said should have been lost** — if something
had no clear home, it's in the inbox, not gone.

**If any of their projects are code repos now in `sources`**, mention the
Sessions page once: it holds a live Claude conversation per project, so
"keep working on X" is a conversation there, not a new ask each time.

## Step 6 — offer the extras, by value

The brain's best tricks are connections most owners never discover on their
own. After the hand-back, offer them ONCE, as a short menu — what each one
does for them, not how it works. Set up only what they say yes to; a "later"
goes to `brain/questions.md` so it resurfaces. The menu:

- **Your old Claude account (recommend this one first)** — "if you've used
  Claude before, that account holds years of your own words — projects,
  people, how you write. Export it from claude.ai (Settings → Privacy →
  Export data) and the brain reads all of it into your backstory, so you
  never have to retell it." When they say yes, run `/import-history` once
  the zips are in Downloads; if the export needs to be requested first, the
  waiting-on-the-email step goes to `questions.md` so it resurfaces.
- **Chats (Beeper)** — "your 'last spoke' dates update themselves from your
  real chats — names and dates only, never messages. Bridge your networks in
  Beeper Desktop once and the morning sync does the rest."
- **Telegram bot** — "text your brain from anywhere: a thought from the bus
  lands in your inbox, 'plan' answers with today, and a voice note becomes
  tasks. Two minutes with @BotFather."
- **Calendar** — "the morning plan fits around your real day instead of
  ignoring it. Mac: add the account to the Calendar app. Any OS:
  `calendar_read.py --add-feed` with your calendar's private address."
- **Email sending** — "Claude drafts, you press send: an app password from
  your provider, kept in the system keychain, and drafts get an
  approve-and-send button. Personal circles stay draft-only, always."
- **Mornings that run themselves** — "the plan is written before you're up,
  and it only notifies you when something is genuinely on fire. Mac: a
  launchd job. Windows: double-click 'Set Up Mornings'."
- **The night shift** — "the heavy jobs — queued asks, the end-of-day tidy
  — run at 01:00 in their own usage window, so they never eat your daytime
  allowance. Set it up once, then it's a switch on the page."
- **Voice memos** — "drop a recording on the page and it becomes a
  transcript and then tasks, all on this machine."
- **Other repos' Claude** — "working in a project with its own Claude
  conversations? `project_prompt.py <folder>` prints the briefing that
  teaches them the framework — paste it there once."
- **The journal** — "tell the day in a couple of minutes — typed, spoken,
  or a voice note captioned 'journal' — and it's kept in your own words,
  private, while the brain quietly updates who you spoke to and what got
  done. `/journal` any evening."

Two or three yeses is a good first day; never push the whole list. The
Connections button on the page (top right) shows this list again with live
status, so name it as the place to come back to.

**Point them at the chat sorter.** If Beeper is connected and unmatched chats
are waiting, sorting them into circles is the other half of filling the brain
— say so explicitly ("~120 chats are waiting on the People tab; ten minutes of
sorting gives every relationship a real last-spoke date"). The page's
post-build screen offers a "Sort your chat contacts" button for exactly this;
an unsorted pile a week later means the push didn't land.

**Follow-up questions go in `brain/questions.md`**, one `- [ ]` checkbox per
question, each line self-contained enough to answer cold. When the dump came
through the page there is nobody to ask interactively — the questions file IS
the interview's second half. The page renders it as an "answer me" list; when
an answer arrives later, file it and tick the question. Never leave follow-ups
only as prose in the report.

**Re-runs merge, never duplicate.** On a brain that already has people and
workstreams, match against what exists (names, `Also:` aliases, context like
city or project) before creating anything. An unsure person-match becomes a
question in `questions.md`, not a second entry.

## Leaving and coming back

Nobody is trapped in onboarding. If the owner wants to stop mid-way — says
so, drifts off, or just stops answering — end gracefully, never with a
guilt trip:

- **File what you have, immediately.** Everything said so far lands in the
  brain now, best-guessed where needed. Items held back "until we finish
  the interview" are items lost to a closed laptop.
- **Write the unasked questions to `brain/questions.md`** — they are the
  rest of the interview, answerable cold, one checkbox each.
- **Say how to resume, in one line:** "run `/onboard` again anytime — it
  picks up from what's already filed and never duplicates." (True because
  re-runs merge; see below.)
- The page behaves the same way: a half-written brain dump is saved on the
  owner's device, the button reads "Continue where you left off", and the
  tours resume from the step where they were skipped.

## Rules

- Never invent a task, a person, or a date they didn't give you.
- Guesses are marked as guesses so they can be corrected.
- This is repeatable and shareable: it must work the same on an empty brain
  belonging to someone you know nothing about. Ask, don't assume.

## Searching the computer for context (when asked)

If the queued dump says to search the computer, then for every project, app or
company the owner names, go and find the real thing before you interview them:

1. Run `python3 brain/tools/discover.py --json` to list their project folders
   with paths and last-touched dates.
2. For a named project (e.g. "Lumen"), match it to a folder by name. If one
   matches, read its `README.md`, `CLAUDE.md`, `package.json` or top TODO to
   learn what it actually is and what is open — then write the workstream from
   *that*, not just from the sentence they said. Add the folder to
   `config.json`'s `sources` so it syncs from then on.
3. If they mention another brain or vault (a folder with its own `brain/` or a
   planning system), note it and offer to follow it — do not read deeply
   without asking.
4. Say what you found: "You mentioned Lumen — I found the folder, last touched
   6 days ago, it's a React app, and there were 4 open TODOs, which I've pulled
   in." Finding real context is the point; guessing is not. If nothing
   matches a name, say so rather than inventing detail.

Never read outside the owner's home directory, and never open anything that
looks like secrets, keys or finances without asking.
