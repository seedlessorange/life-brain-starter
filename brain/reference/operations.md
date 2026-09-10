# Operations — Windows, sharing, wiping, uploads

Load this when running any of these, not before.

## Windows, and sharing the brain with a friend

The tools run on Windows too: `Open Brain.bat` starts the server,
`Set Up Mornings (Windows).bat` registers the 7am run in Task Scheduler
(`brain/tools/morning.ps1` is the port of `morning.sh`,
`brain/tools/night.ps1` of `night.sh`), and secrets fall back from the macOS
Keychain to the `keyring` package (Windows Credential Manager). Calendar and
voice transcription work everywhere: `calendar_read` merges the Mac Calendar
app with any ICS feeds subscribed via `--add-feed` (addresses live in
git-ignored `brain/.calendar-feeds` — they are keys, never commit one), and
`transcribe.py` uses mlx_whisper on a Mac and faster-whisper (`pip install
faster-whisper`) anywhere else. The Season tab works the same everywhere;
only its "Calendar" block button is Mac-only. The other direction is
platform-free: slotted season items are regenerated into `brain/season.ics`
on every rebuild, and any calendar app — Outlook on a friend's Windows
machine included — can subscribe to `http://<host>:7718/season.ics`.

Keep new code platform-neutral: no bare `open`/`osascript`/`pgrep`/`pmset`
without a `sys.platform` branch, and secrets always through the
keychain-or-keyring helpers. Shell scripts come in pairs — a `.sh` and a
`.ps1` that do the same thing — and anything they both need to decide (which
jobs, which model, which hour) is computed once in Python and printed for both
to read, so the two can never drift.

**Never give anyone a copy of this folder — the markdown and the git history
carry her whole life.** When she wants to share the brain, run `python3
brain/tools/share.py` (preview, then `--yes`). It builds `dist/life-brain/` +
a zip from an allowlist: the code and page assets, every data file reseeded to
its format guide, generic `CLAUDE.md`/`config.json`/command files from
`brain/tools/share-templates/`, a fresh git history. It then scans the whole
package for her name, git identity and email and REFUSES to finish on any hit
— if it refuses, fix the source file or add a template overlay; never weaken
the scan. `dist/` is git-ignored and safe to delete.

**Updating a friend's brain without touching their life:**
`brain/tools/update.py` (ships in every package) replaces CODE only — tools,
commands, pages, launchers, reference docs — from a newer zip, and never
touches the data files, their config values, or their git history. New
config keys arrive with defaults; existing values always win. It previews
without `--yes`, snapshots their git, and archives every replaced file under
`brain/archive/update-<stamp>/`. Friends on a pre-update.py version run it
FROM the new package: `update.py --into <their brain> --yes`. The data/code
boundary lives in `DATA_FILES`/`DATA_DIRS` at the top of update.py — any new
owner-owned file must be added there, or an update would overwrite it.

## Two machines — moving the brain's home

The brain can live on two machines (say, the Mac laptop and an always-on
Windows desktop), with git as the bridge. The one hard rule: **exactly one
machine is the home** — it runs `serve.py` (the page and the Telegram bot),
the 7am morning task and the night shift. Two servers means two Telegram
pollers fighting over one bot token and two pages writing ticks into the
same files. The other machine keeps a full clone for attended sessions and
gets the home's work through the remote.

How the sync actually happens, all through `brain/tools/gitsync.py` (commit
what is dirty, `pull --rebase`, push; a conflicted rebase is aborted so a
machine never loses its own version):

- morning and night scripts pull before their run and push after (they
  already pushed; the pull is what brings the other machine's work in);
- `serve.py`'s auto-sync loop runs the full cycle every ~20 minutes, so page
  ticks and drafts reach the other machine the same day;
- an attended session on the non-home machine should start by pulling and
  end pushed — `/wrap`'s closing commit plus `gitsync.py --push` covers it.

Project folders don't travel by git: `sync.py` keeps a last-known snapshot
per source in `brain/.synced-state.json` (committed), so a machine missing
a project folder shows "as another machine last saw it" instead of a blank.
For the folders the owner wants actually present on both (so the Telegram
`send:` search can serve their files while the laptop is closed): app repos
get a clone on each machine; non-repo folders travel by a folder sync tool —
Syncthing fits, peer-to-peer with the always-on machine as the hub.

Moving the home is a checklist, not a project:

1. Old home: push everything, unregister the morning/night schedules, stop
   `serve.py`. New home: clone, `Check My Setup`, `Open Brain`, run the two
   setup scripts, set the machine to never sleep, start Beeper Desktop and
   the brain on login.
2. Re-enter what git deliberately doesn't carry: `beeper.py login`, the
   Telegram pairing (`brain/.telegram.json` — copy it or re-pair), 
   `brain/.calendar-feeds`, the Guardian key, site cookies, the email app
   password. Past page uploads (`brain/files/`) stay on the old machine.
3. Repoint addresses: the phone's bookmark and any `season.ics`
   subscription move to the new host's tailnet name, and the finance
   `redirect_url` in config must change AND be updated in the EnableBanking
   app registration, or bank consents break silently.

## Private files — what unattended runs never load

`"private"` in config.json lists paths the scheduled runs — the night shift
and the 7am morning run — must never load. The journal is the default (the
key absent means `["brain/journal/"]`; an explicit `[]` switches it off).
Enforced by `brain/tools/private_gate.py`, in two layers:

- **The OS lock is the layer that holds.** The scheduled scripts run
  `private_gate.py --lock` before their claude run — every private path is
  made unreadable, so the run cannot open it no matter what it decides
  to do — and `--unlock` after (trap-protected). Measured on Claude Code
  2.0.76: settings hooks do NOT fire in headless `claude -p` runs, which is
  why the lock, not the hook, carries the boundary. On Mac/Linux the lock
  is chmod 0; on Windows it is an icacls deny-read on the current user,
  inherited down the folder — same refusal, different spelling.
- **The hook is the second layer.** `.claude/settings.json` wires the same
  script as a PreToolUse hook: while `brain/.unattended` exists (the
  scripts write it around their run — a file, not an env var, because
  hooks get a scrubbed environment), any tool input mentioning a private
  path is denied with a message telling the run to work without it. The
  gate ignores a marker older than six hours.

Crash safety is automatic: her next attended session's first tool call
finds the stale lock and restores the files' modes. A session she is
actually in is never filtered.

The owner's control is the **Extra privacy** switch on the Usage page
(`/api/privacy` in serve.py). On writes `"private": ["brain/journal/"]`,
off writes `[]`; the copy beside it states the trade — the unattended
morning plan goes without yesterday's journal entry. A hand-extended
`private` list still works; the switch just resets it to the default if
toggled off and on.

The one visible cost: the unattended morning `/today` plans without
yesterday's journal entry. An attended `/today` still reads it. Never work
around the gate in an unattended run — a refused read there is the feature
doing its job.

## Wiping — starting fresh without losing anything

When she asks to wipe the brain, or a part of it ("clear my habits", "start
the goals over", "reset everything"), use `python3 brain/tools/reset.py` —
never delete by hand. It archives the current files to a timestamped folder
under `brain/archive/`, reseeds the core files with their own format guides,
snapshots git before and after, and rebuilds the pages. Run it WITHOUT `--yes`
first and show her the preview; add `--yes` only after she confirms. `--all`
takes everything except `decisions.md` (the why-log survives a fresh start
unless she names it explicitly).

## Documents she uploads

Files attached from the page land in `brain/files/YYYY-MM-DD/` and are listed
under an `## Attached files` heading in the queue item. **Read them with the
Read tool before acting on the request** — they are usually the whole point of
it (a syllabus to pull dates from, a screenshot of a problem, a letter to
reply to). Never move or delete them; they are her originals.

When a document yields dates, put each one in as a real `Due:` on a workstream
or a dated task, then say which dates you took and from which file. A syllabus
turned into six tracked deadlines is worth more than a summary of the
syllabus.
