# What the brain spends, and how to keep it cheap

Load this when changing anything that starts a model run, when she asks what
the brain costs, or when setting the brain up for someone on a smaller plan.

## Where AI actually runs

Most of this system runs no model at all — `sync.py`, `beeper.py`, `model.py`,
`graph.py`, `build.py`, `map.py`, `rooms.py`, `import_chats.py`,
`calendar_read.py`, `transcribe.py` and `people_update.py` are plain code, and
that is the design. Eight paths reach a model:

| Path | Started by | Model | Typical size |
|---|---|---|---|
| Page runs (`/queue`, `/brief`, `/today`, `/wrap`, `/sync`, `/discover`, audit) | her tap | careful→haiku, full→sonnet | ~1.4M tokens, 3–5 min |
| Room / map / drawer "Quick run" | her tap | same | same shape |
| Morning `/today` | 7am schedule, **full mode only** | default | ~570k tokens, ~70s |
| Night shift | 01:00 schedule, off by default | config | one run per job |
| Sessions conversations | her typing | her pick | one turn each, context grows |
| Draft revise | "Revise" on a draft | `llm` block: haiku, or local Ollama | ~3k tokens |
| Naming a conversation | first exchange of a Sessions convo | `llm` block: haiku, or local Ollama | ~1k tokens |
| News breakdowns (finance, entrepreneurship) | morning job / first `--explain` of the day, then cached | `llm` block: haiku, or local Ollama | ~2k tokens per learning topic per day, + one each on Sundays for the weekly recaps |
| Voice turns (the talk orb, a spoken question on Telegram) | her speaking | `voice.model`: Haiku, no tools; the full brain only when she asks it to do something | ~3k tokens, ~6s; a lookup or a page-open spends nothing |
| Draft eval (`drafteval.py`) | her ask, never scheduled | revise on the `llm` model, judge on opus | 2 calls per case, ~5k tokens each; 13 cases ≈ 3 min |
| `recall_hook.py` in her app repos | every prompt there | none — it only injects text | typically 300–900 chars; grows with room notes (caps: 1200-char notes + 8 tasks/workstream) |

## The number that matters is turns, not tokens

Every tool call is a full API round-trip that re-reads the whole context. A
1.4M-token `/queue` run is not 1.4M tokens of thinking; it is roughly 45 turns
of ~40k context each. So the two levers are **fewer turns** and **less context
riding on every turn**, in that order.

This is why:

- **CLAUDE.md is kept lean and this file exists.** Everything in CLAUDE.md is
  re-read on every turn of every run. A paragraph moved here costs nothing
  until a session actually needs it. When you add to CLAUDE.md, ask whether
  every run needs it on every turn; if not, it belongs in `brain/reference/`.
- **TodoWrite is off in this repo** (`.claude/settings.json`,
  `todoFeatureEnabled: false`). A measured `/queue` run spent 8 of its 47
  turns writing a scratch list nobody read — about 17% of the run.
- **Edits are batched.** Five separate `Edit` calls on five queue items are
  five turns. Read what you need, decide, then write.
- **`draft_revise` is the shape to copy** for any narrow job: one no-tool
  call, `--tools ""`, run from a temp dir so no CLAUDE.md and no file reads
  happen. Seconds, and a small share of the window. Which Claude answers is
  config, not code — `llm.model` (and `llm.models` per job) in config.json.
  It is on **sonnet** here: on a Max plan these jobs are reading and judgement,
  and Haiku was the wrong economy. The shipped default stays haiku for anyone
  cloning the repo on a smaller plan. Never route a draft reword through
  `/queue`, which reloads everything.
- **`people.md` is large.** Reading it pins ~17k tokens for the rest of a run.
  Prefer `python3 brain/tools/model.py --people` (owed replies, due promises,
  birthdays, gone-quiet — a few hundred bytes) when you need the flagged
  subset rather than the whole file.

## Local models (Ollama)

The small no-tool jobs — draft revise, conversation naming — can run on a
local model instead of Haiku. `brain/tools/llm.py` reads the `llm` block in
config.json: `provider` picks the default route, `jobs` overrides per job
(`{"revise": "ollama"}`), `ollama.model` names the model. Setup is: install
Ollama (one step, ollama.com), `ollama pull llama3.2`, put that name in
config, flip the provider. Every call falls back to Claude when Ollama can't
answer, so a machine without it never notices the setting — which is also why
the shared package can carry this code to friends without a GPU. Local calls
land in the ledger at $0 under `ollama:<model>`.

The heavy runs (`/queue`, `/wrap`, `/today`) stay Claude on purpose. That
trade would be the life-admin quietly rotting to save a subscription-covered
call — the one failure this system exists to prevent.

## The ledger

`brain/tools/usage.py` is the one account. Every model call writes a line to
`brain/.usage.jsonl` — page runs, the morning plan, the night shift, Sessions
turns, draft revisions.

```
python3 brain/tools/usage.py            # today, this week, by job, by model
python3 brain/tools/usage.py --days 30
python3 brain/tools/usage.py --json     # what the page reads
```

Recording never breaks the thing being recorded: `record()` swallows every
error. The dollar figures are what the tokens would have cost at published API
rates — a size signal for comparing a Haiku run against an Opus one, which is
why the Usage page shows none of them. On a subscription nothing is billed,
and Claude Code does not expose plan limits to a script, so `/usage` inside
Claude Code is the only place that shows where she actually stands.

## The night shift

Subscriptions meter usage in rolling five-hour windows. The night shift moves
the heavy jobs into a window that would otherwise go unused, and finishes long
before anyone is awake.

`night.enabled` in config.json switches it on; `zsh brain/tools/setup_night.sh`
(or `setup_night.ps1`) schedules it. Defaults to 01:00 for a specific reason:
that window closes at 06:00, before the 07:00 morning plan opens a fresh one.
Move it later and the two compete, which is the whole thing it exists to
avoid.

It refuses to run outside 23:00–06:00 (a laptop opened at 09:15 must not
suddenly start a twenty-minute run), refuses on battery unless told otherwise,
runs once a night, and snapshots git before and after. `/today` is deliberately
not an allowed night job — the morning plan is written in the morning, against
the day it is planning. Its report lands in `brain/.night-report.md`.

**It has the same boundary as everything else**, and more need of it because
nobody is watching: it drafts, files and tidies; it sends nothing, submits
nothing, buys nothing.

Night runs are not free — they draw on the same weekly allowance. They just
spend it at an hour when nothing else wants it. That trade is good on Max and
arguably better on Pro: a Pro plan's five-hour window is the constraint that
actually bites during a working day, and the night shift keeps the brain's
heaviest runs out of it entirely (on Haiku, in careful mode). Recommend it to
Pro users rather than warning them off it.

## Budget mode, and the per-feature switches

`config.json` has `"ai": "full" | "careful"`, switchable from the page
(the Careful/Full control next to Talk to Claude). The preset means:

**Careful** fits a Pro plan: the 7am job does the free work (Beeper sync,
rebuild, notification) but skips the scheduled Claude run, page-started runs
default to Haiku unless she picks a model, and nothing is prepared unasked.
**Full** fits Max: the morning plan runs itself, Sonnet is the default, and
openers get prepared. Respect the effective settings: never start a run she
did not ask for when the settings say not to, and prefer batching several
queue items into one run.

**The preset is not all-or-nothing.** `config.json` may carry an
`ai_features` object that overrides the preset key by key — set from the
**Usage page** (`brain/usage.html`, generated by `build.py`), which also
shows the ledger, explains plan limits to a Pro user, and hosts the
**usage audit**: `/usage-audit` (a page button or a typed command) reads the
ledger, the run logs and a few conversations, then writes
`brain/usage-audit.md` — where the spend went, which habits cost extra, and
what would cost less. The page renders the latest report.

```
"ai_features": {
  "morning": true|false,             // the scheduled 7am Claude run
  "model":  "haiku"|"sonnet"|"opus", // default when no model was picked
  "openers": true|false,             // prepare openers/drafts unasked
  "news":    true|false,             // the daily news breakdowns
  "daily_runs": 10                   // runs/day before a page run asks twice
}
```

A key that is absent follows the preset. The resolution lives in ONE place —
`ai_features()` in serve.py — and morning.sh/.ps1, sessions.py, news.py and
the `/today` command read the same config keys. When judging what to do in a
run (openers, model choice), check `ai_features` before falling back to `ai`.

`news: false` is the last scheduled spend a Careful plan can drop: with the
7am run off, the daily breakdowns are the only model call the morning job
makes. The briefing itself is free either way — it just stops explaining the
jargon. `news.py` reads the key directly (`_explainers_on`), so the switch
holds for a terminal `news.py fetch --explain` too.

**The daily limit is counted in runs** (`daily_runs`, a whole number;
absent means no limit). It counts what the Usage page's "Today: N runs"
card counts, every ledger line since midnight, so the morning plan, each
Sessions turn and each draft revision are one run apiece. Both read
`usage.runs_today()`. Once today reaches the limit, a run started from a
page button (`/api/agent`) is refused with a message naming the limit, and
the page asks once more before going ahead (`anyway`). Scheduled work is
never blocked.

It used to be dollars (`daily_cap`). On a subscription nothing is billed
per token, so the ledger's dollar figure is only a size signal, and a
limit in dollars measured the wrong thing. The old key is never read: a
leftover `2.0` would otherwise become a two-run limit. It is dropped the
next time any switch is saved.

The page offers 5, 10 and 20 runs. On this brain's ledger (30 days to
28 Sep 2026: about 180 runs, 6 a day), 23 days had 5 or fewer and 28 had
8 or fewer. The two outliers were a long conversation day (25) and a
draft-eval day (67). So 5 is a quiet week, 10 is an ordinary busy day with
room to spare, and 20 is a heavy working day.

## The two recommended shapes

`AI_PLANS` in serve.py names the two known-good states, and `/api/aiplan`
applies one in a single write: the preset, plus the overrides that shape
needs, with every other override cleared.

| | Pro | Max |
|---|---|---|
| Preset | Careful | Full |
| 7am plan | off | on |
| Default model | Haiku | Sonnet |
| Openers | off | on |
| Daily limit | 10 runs | none |

Pro's 10 leaves room for the comfortable Pro day: one or two batched page
runs plus the small calls (a conversation, a few revisions, the news
breakdowns).

Neither shape touches the **night shift** or **extra privacy**: turning the
night shift on means a terminal setup command the page cannot run, and
privacy is a choice about her journal, not about spend. Both keep their own
switch.

`ai_features()["plan"]` reports which shape the settings currently match, or
`"custom"` — that is what lets the pages answer "am I set up for Pro?" without
making anyone read seven switches.

**The plan question is asked before the first brain dump**, not after: the
onboarding build run is the biggest single spend of anyone's first day, so
asking afterwards asks after the money is gone. The step lives in the dump
overlay (`_AI_SETUP` in build.py), shows the two cards plus every individual
switch under "Set each one myself", and marks itself answered in
localStorage (`ai-plan-set`) so it appears once. The same screen carries the
style chooser (the ⋯ menu's skin chips) — a tap restyles the page live and
saves through `/api/appearance`, so the first look is also chosen before the
first build. Skipping it (closing the
overlay) leaves it unanswered, so it comes back. Everything in it stays
reachable afterwards on the Usage page.

Two jobs sidestep the preset: `/sync` and `/discover` (`LIGHT_JOBS` in
serve.py) default to Haiku even in Full mode — they are mechanical reads and
Sonnet buys nothing there. An explicit pick, or a default-model override on
the Usage page, still wins.

**Openers are the proactivity dial.** When they are on, don't just list work
— *open* it: look up the number and put it in the task, draft the first
message into `brain/drafts/`, research the train times into the task note
(`/today`'s Openers rule). The boundary never moves with the dial: an opener
is preparation she approves, never a send, purchase, submission, or anything
irreversible. With openers off, prepare nothing unasked.

Queue items may carry a `model:` field (`haiku`, `sonnet`, `opus`, `fable`)
that she picked. Respect it — it is her choosing what to spend. If a job
clearly needs more than it was given, say so in the Outcome rather than
silently deciding. Opus **is** available on Pro plans these days, but it
drains a small allowance fastest — so careful mode never chooses it FOR her;
an explicit pick (a queue card, the Usage page's default-model switch) always
stands.

**Fable** (added 2026-09-10) is the fourth pick, and the one for prose: a
letter to Casey, a school essay, a message that has to land. It costs
roughly twice Opus per token (`RATES` in usage.py), so it is never a default
— careful mode and full mode both ignore it unless she picks it. Two things
to know when touching the code: the list of pickable models and the id each
one needs live in **usage.py** (`PICKABLE`, `cli_model`), and every picker
reads from there — adding a model is one edit. And `claude --model fable`
comes back 404; it goes by `claude-fable-5`, which is what `cli_model`
returns.

`MAX_ASK_CHARS` in serve.py caps a single pasted ask at 200k characters —
about 50k tokens. That is a real ceiling on a small plan, not a formality.
