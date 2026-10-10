# What each model call is told about her

Load this when changing anything that builds a prompt, adds a model call, or
touches `context.py`, `llm.py`'s `audience`, `textcheck.py`, `recall_hook.py`,
`corrections.py` or `audit.py`. Built 7 Oct 2026 from the plan in
`brain/drafts/smarter-brain-plan.md`; tracked as the workstream "Brain:
smarter context".

## The card and the rules (context.py)

- `card()` is a short description of her, about 1,200 characters, generated
  on every call from `about-me.md` and config `now`. Nothing stores it, so it
  cannot drift from the source. It never carries family, health, money,
  properties or dating: those sections are skipped by name.
- `card("voice")` is the version for text someone else reads: name,
  languages, tone. It is framed as how to sound, never as content, so an
  employer form cannot pick up her aphantasia or how she works.
- `rules_for(kind, person, front)`: `"other"` adds `writing-style-short.md`,
  the exact-limits line and the person's Register, Reach and Pronouns;
  `"plan"` adds her capacity and `rulings_for(front)`; `"her"` and `"code"`
  add nothing beyond the card.
- `rulings_for(front)`: up to three recent `decisions.md` entries that name
  the workstream or room. Mechanical, no model.
- `python3 brain/tools/context.py card|rules|rulings|call` prints any of them.
- `jarvis()` is the profile she pastes into claude.ai and ChatGPT: the
  audit's persona, briefing and "what works" lines (fixed in the code), the
  card's Who, Education and Projects lines, and the five things she keeps
  correcting (`JARVIS_CORRECTING`). Each version is held to 1,500
  characters in code. `context.py jarvis --write` keeps both in
  `brain/evals/jarvis.json` with a `sha`; the page shows an "Update your
  Claude profile" card while `sha` differs from `pasted_sha`, which only
  the page writes.

## Where it is wired

- `llm.complete(..., audience="her"|"other", person=, front=, limit_hint=)`
  is the one door for the small no-tool calls. With an audience, the card
  and rules go in front of the system prompt. With `"other"`, the reply goes
  through `textcheck.problems` (em dashes, the tells her rules ban, a named
  limit) and is redone once; what still fails comes back flagged and lands
  on the usage ledger line. A new call that writes text for someone else
  passes `audience="other"`; a call working for her passes `"her"`.
- Revise also carries the person's fields in `revise_prompt`. The task and
  person packs for Talk it through carry the card, rulings and person rules.
- The Telegram ask and `/queue` draft mode are told to load
  `writing-rules.md` and the person's entry first (they run in the brain
  folder, where tools can read).
- `recall_hook.py` in her app repos: the card on the first prompt of each
  session (seen ids in `brain/.cache/`), the writing slice when the prompt
  is a writing ask, the room's rulings once. A code prompt still gets only
  the room card.
- Runs started in another repo (any profile) load only local settings and
  get that repo's own `CLAUDE.md` as text through
  `run_policy.project_instructions()`; Claude Code keeps only the last
  `--append-system-prompt`, so callers pass their own text as `system=`.

## How the brain sees whether it was right

- `corrections.py`: her corrections per session, by the audit's types,
  counted from her own typed words in every Claude Code project and the page
  conversations. Counts in `brain/evals/corrections-rate.json`; her lines in
  the gitignored `brain/.corrections-lines.jsonl`. The morning job refreshes
  it and the usage page shows the line. Baseline counted this tool's way:
  28% of sessions, 10 Aug to 28 Sep. Week-to-week moves under ten points are
  noise; compare four-week averages.
- Drafts keep both versions in `brain/drafts/.versions/`; Copy and Open in
  email count as used. `model.py --drafts` reports used as is, edited then
  used, not used.
- `drafteval.py --if-changed` runs on the night shift when the writing rules
  or the cases changed, through the same revise path the page uses.
- `calibrate.py --save` keeps the plan scorecard weekly in `brain/evals/`;
  `/brief` raises a finding once.

## The quarterly audit (audit.py, /claude-audit)

- `audit.py sift [--since D] [--export ZIP]` gathers her typed messages the
  way `corrections.py` picks them (plus a claude.ai export when given),
  drops anything on the audit's held-back list before writing, tags
  corrections, praise and facts, and writes the numbers and six theme
  files to the OS temp folder. It refuses a folder inside the repo. The
  window starts at the last `## Update` or the "Written" date of
  `reference/claude-audit.md`.
- `/claude-audit` is attended only: six readers, one per theme, then a
  dated `## Update` at the end of the audit file and `context.py jarvis
  --write`.

## The lesson tray (lessons.py)

- `lessons.py propose [--if-due]`: one no-tools `llm.complete("lessons")`
  call (Sonnet unless config `llm.models.lessons` says otherwise, audience
  "her") over 7 to 14 days of her signals: correction lines, word diffs of
  drafts she changed, discard and skip reasons, Revise instructions. Drafts
  on run_policy's copy-only list are left out whole, and a job skip passes
  only her reason and her track name, never the role's own text. Earlier
  lessons, kept or binned, go in so they are not proposed again. The answer
  is checked in code (at most five, known targets, a person only from
  people.md headings) and kept in `brain/lessons.json`.
- The morning job runs `--if-due`: a week since the last proposal, three new
  signals, and fewer than five still open. `lessons.py signals` shows what
  a call would read, for free.
- Each open lesson is a Confirm line in For you (`tray_lessons.py`). Keep
  queues one ask that tells the run where the lesson goes, with its wording
  fenced as data; coaching lessons come back as a proposed line, since runs
  do not edit CLAUDE.md. Bin only marks it.
- The reasons: Didn't use on a draft offers wrong tone, wrong facts, not
  needed, did it myself (stored as `reason` in `drafts/.versions/`); Not for
  me on a job lead offers wrong role, wrong place, wrong level, already on
  it (`skip_reason` in `.jobs-state.json`). Revise keeps her instruction in
  the versions file as `revisions`. `model.py --drafts` counts the reasons.
