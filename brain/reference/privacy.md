# Privacy levels: what runs may open, what may send, what may leave

Load this before changing what runs on a timer may read, the reading fence,
anything that sends, the mail readers, Telegram's replies, the GitHub push,
the small jobs' routing, presenting mode, or the Privacy page. The plan, its
reasoning and the deep dive's findings: `PRIVACY-PLAN.md` at the top of the
repo. Built 8 Oct 2026; her decisions are at the end of the plan.

## The shape

Three levels, a switch each, like the Usage page: **Everyday** (what she had
before), **Guarded**, **Locked**. A level clears her overrides; any switch can
then differ, and the page reads "your own mix". One table, `privacy.SWITCHES`,
says what each level sets; the server, the pages and every gate read it.

| Switch | Everyday | Guarded | Locked | Enforced in |
|---|---|---|---|---|
| `lock_transcripts` | open | locked | locked | `privacy.private_paths()` → run_policy and private_gate; the recordings timer |
| `lock_money` | open | locked | locked | the same |
| `lock_people` | open | open | locked | the same, plus the short people list |
| `send_email` | on (as set up) | touch | off | `email_send.send()` |
| `send_chat` | click | touch | off | `beeper.send_message()` |
| `mail_check` | on | on | off | `email_read.check/lookup`, `mail_local._guard`; also the 7am check, `plan_sources.mail_ready()` (8 Oct) |
| `mail_tasks` | on | off | off | `mail_tasks.check` |
| `telegram` | full | full | capture | `telegram_bridge._capture_only()`, `serve.telegram_voice` |
| `reach` | anywhere | named | brain | `run_policy.reach()` → `fences()` (runs she starts) |
| `reach_timer` | anywhere | brain | brain | the same, for runs on a timer |

Set on their own, no level touches them: `backup` (the GitHub push,
`gitsync.backup_allowed()`; a push also still needs config's `git_push`) and
`small_jobs` (claude | local_first | local_only; `llm._once`, Pen's
`_kept_open`, the voice's `_MIND`). Plus `presenting` and the folder list,
below.

"Runs on a timer" (the page's words; "nobody watching" in the plan): the
7am plan, the night shift and the twice-daily recordings pass. Woken
conversation turns continue a conversation she started, so they count as hers.

## Where the settings live, and who may change them

- `brain/tools/.run-policy/privacy.json` (gitignored): level, overrides,
  standalone switches, `folders`, `ticks`, `presenting`. No run can write
  that folder. Never move these into config.json, which runs can write.
- Only `serve.privacy_change()` writes it. **Tightening is one tap;
  loosening takes her Touch ID** (`privacy.confirm` → brainconfirm) and is
  refused while a page run is working. Adding a folder runs may read is a
  loosening. Presenting and the Mac check's ticks are one tap either way.
- **No file means Everyday; an unreadable file means Locked**, with a red
  line on the page.
- **It only subtracts.** A switch stops something that is set up; it never
  starts what isn't.
- The alarm watches `privacy.py`, `privacy_log.py`, `privacy_change`,
  beeper's `send_message`, Telegram's capture functions, `state:privacy`
  (values and folders) and `state:trips`. A page change approves
  `state:privacy` alone (`sentinel.accept_one`); a hand edit raises the card.

## The floor (no key reaches it)

Personal circles get Copy only; drafts made from other people's words never
get a send button; every run is sandboxed; the confidential-name guard; runs
on a timer can't send; and **the journal is private to runs on a timer at
every level** (her call, 8 Oct). Config's `private` list can only ADD paths.

## The reading fence (phases 3 and 4)

Claude Code 2.0.76 can only DENY reads: its sandbox builds the read list
from `Read(...)` deny rules and has no `allowRead`. So the fence is the
complement of the allowed folders, worked out at each launch
(`run_policy.reach_plan`): every entry of the home folder outside the brain,
the approved folders and `REACH_TOOL_NEEDS` (git's settings, Python's user
packages, Claude Code's shell snapshot), plus `/Volumes` and `/Users/Shared`.
One rule per entry: a rule on a folder covers what is inside it.

- **The size limit.** 2.0.76 passes the whole sandbox description as one
  argument, each rule several clauses long. 1,131 rules failed every command
  with `E2BIG`; 314 and 354 worked, and a 6,000-character command worked
  under 314. So a folder with more than `REACH_DIR_CAP` (150) entries is
  denied whole, and an approved folder inside it is reported as "dropped" on
  the Privacy page. A wildcard "everything except" is impossible: the
  converter escapes `^`, so no negated class survives.
- **The folder list** is `privacy.reach_folders()`, from the settings file,
  never config's sources (a run could add the home folder to its own fence).
  Config sources not yet approved show as "Let runs read it?".
- **Before upgrading Claude Code**: current versions read
  `sandbox.filesystem.denyRead`/`allowRead`, and their docs say Read rules
  cover the Read tool only. Rerun the probe harness on the new version
  first; run_policy must then write both forms. The self-test refuses an
  `allowRead` in the brain's shared settings (narrower wins, and those reach
  every run).
- Codex and Gemini get the same list through `fences()`; untested live.
  Windows has no sandbox: the Read-tool rules only.

## Where her words went, and the Mac check (phase 2)

- `privacy_log.py` is a PostToolUse hook every run the brain starts carries
  (`run_policy.settings`), never her own sessions. It records the KIND of
  what a run opened (journal, people, money, transcripts, drafts, school,
  brain, projects, outside) and, outside, only the top folder. Never content
  or file names. `brain/.privacy-log.jsonl`, unwritable by runs. A run on a
  timer that OPENED a kind its level locks is a trip: the red card.
- `mac_check.py`: plain code on her click. FileVault, firewall, Claude Code
  version, keys pasted into Claude's allow rules (counted and named, never
  shown), the GitHub copy's visibility (GitHub's public API, signed out),
  the mail password's Touch ID, the Telegram key file. Two reminders she
  ticks. Her own sessions are not judged (her call, 8 Oct).

## Presenting mode (phase 6)

While she shares her screen, every page is rebuilt WITHOUT the private
parts; nothing is hidden by a script. `privacy.present_filter` (one function
for index, map and rooms): the hidden areas' workstreams, any workstream or
task whose title names someone in a personal circle (name or Also:), every
note, any field naming one. `build.py` also drops the people list, the queue
(For you, outcomes), questions, Life and Season, the interests card,
countdowns, Claude's ranking, the decisions and waiting lists, the raw inbox,
drafts, money, and filters today's plan and the week plan to headings and
tasks (`present_md`). The find box skips people and files; `/api/recall`
answers nothing; the morning notification waits. A bar on every page turns
it off. Measured on a clone, 8 Oct: family-and-friend names on index.html
went from 6,090 to 9 (a classmate sharing a friend's first name, voice and
colour names, a news headline); 0 on the map and rooms.

Not covered: the Conversations, Usage, Routine and Kitchen pages; the page
says so.

## Mechanisms worth knowing

- **The recordings pass** starts its queue run with `by="auto"`, which gets
  the `scheduled` profile and `LIFEBRAIN_UNATTENDED` for that process only;
  with transcripts locked the timer doesn't start it, and Usage says "held".
- **The people list.** When `lock_people` is on, `private_gate.lock()`
  writes `brain/.people-digest.md` before closing people.md; `unlock()`
  removes it. `/today`, `/wrap`, `/queue` say to read it.
- **Telegram capture only**: lines, journal entries, dumps, photos and voice
  notes still land; taps, answers, file finding and the plan, scorecard,
  school and routine pushes stop; the evening keeps its bare ask.
- **Small jobs**: "this Mac only" refuses rather than fall back, and can't
  be chosen until `llm.ollama_answering()`; picture jobs refuse.
- `python3 brain/tools/privacy.py` prints the settings in force;
  `--presenting` exits 0 while presenting.

## Known gap, older than this work

The page server hands out `people.md`, `workstreams.md`, `drafts/*.md` and
`avatars/` as plain files to anything that can reach it (found 8 Oct while
mapping presenting mode; security.md).
