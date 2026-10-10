# Life brain

A second brain for your life admin. Every workstream you have on, in one place, with the three questions no to-do app answers.

What is decaying, meaning deadlines gone past, things you have not touched in weeks, and things you never started. Whose court the ball is in, meaning what sits with you, what sits with someone else, and who has gone quiet long enough that it is time to chase. And what should get your next free hour, as a short ranked list rather than a wall of two hundred tasks.

It is plain markdown files, a page that renders them, and a map. Claude Code does the upkeep so you never have to. There is no account, no app to install, no database, and no subscription beyond the Claude one you already have. Your files live on your machine. When Claude reads them to do its part, that text goes to Anthropic to be processed, exactly as in any Claude conversation, so the section on security below is worth five minutes.

## What you need

Python 3, free from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick "Add python.exe to PATH" on the first screen of the installer. That one checkbox is the difference between everything working and nothing working. Macs and most Linux machines already have it.

[Claude Code](https://claude.com/claude-code), for the smart half. The page works without it, though the "Ask Claude" box needs it.

## Start it

If you have never used a terminal, open `START HERE (Mac).md` or `START HERE (Windows).md` instead of this file. Same setup, walked through step by step, assuming nothing. This README assumes you are already comfortable at a command line.

Unzip this folder wherever you keep things, `Documents\life-brain` for instance, then:

- **Windows:** double-click `Open Brain.bat`
- **Mac:** double-click `Open Brain.command`
- **Any terminal:** `python brain/tools/serve.py` (or `python3` / `py -3`, whichever your machine answers to)

Your browser opens `http://127.0.0.1:7718` with your brain page. Leave the black window open while you use it, because that little program is the sync button you were told could not exist, which the section below explains. Closing it stops the brain and loses nothing, so just double-click again.

## The five-minute setup

1. **Open Claude Code in this folder** (open a terminal in the folder and run
   `claude`) and run `/onboard`. You talk about your projects, the people you
   owe replies to, and the things you keep meaning to do, and it builds the
   whole brain from what you said. If you would rather do it by hand,
   `brain/workstreams.md` explains its own format at the top. If you have been
   chatting with Claude for years already, `/import-history` folds an account
   export's worth of old conversations in too.
2. **Point it at your project folders**: on the page, the gear, then
   **Project folders**. Paste folder names or paths, one per line (a bare name
   is looked up on your computer, Desktop folders of documents included), or
   press **Look for them on this computer** to list the projects you worked in
   lately and follow the right ones. They land in `sources` in
   `brain/config.json`, and the page re-reads them on its own every 20 minutes
   (change `auto_sync_minutes` to taste): each project shows up with its open
   items and how long since anyone worked on it. The green dot in the header
   shows when it last synced, and clicking it syncs now.
3. From then on, the habit is two commands: `/brief` when you sit down and
   `/wrap` when you get up. Claude keeps the files honest and you just read
   the page.

## Mornings that run themselves (optional)

The brain can write your daily plan before you are up and notify you only if something is genuinely on fire.

- **Windows:** double-click `Set Up Mornings (Windows).bat` once. That
  registers a 7:00 task, and if the PC is asleep it runs on wake. Undo with
  `powershell -ExecutionPolicy Bypass -File brain\tools\setup_morning.ps1 -Remove`.
- **Mac:** `zsh brain/tools/setup_morning.sh` registers the same 7:00 job as
  a launchd agent, and if the Mac is asleep it runs on wake. Undo with `--off`.

If `"ai": "careful"` in `brain/config.json`, the morning run does only the free parts, meaning sync and rebuild, and skips the scheduled Claude run.

## The extras, where the brain gets unfairly good

Each of these is optional and takes minutes. **Connections**, under the gear at the top right of the page, shows the same list with live status. Ask Claude in this folder to set up any of them.

- **Chats, without logging anything (Beeper).** Bridge your networks, meaning
  WhatsApp, Instagram, Telegram and SMS, inside the free
  [Beeper Desktop](https://www.beeper.com) app once, keep it open, and the
  brain reads chat names and last-activity dates each morning. It never reads
  message text. Your "last spoke" dates stay true by themselves, and the
  People tab then flags who has quietly drifted.
- **A Telegram bot, so you can text your brain from anywhere.** Two minutes:
  message @BotFather, run /newbot, give the brain the token, and pair with
  the code it shows. From then on a thought from the bus lands in your inbox,
  "plan" answers with today's list, and a voice note is transcribed on your
  machine and turned into tasks.
- **Email that you approve, per message.** Claude writes the draft, the page
  shows exactly what would be sent, and you press the button. An app password
  from your provider lives in the system keychain. Close-circle contacts are
  draft-only in code, so the brain will never message your family.
- **Your calendar in the plan** and **voice memos**, which the two sections
  below cover.
- **Mornings that run themselves**, which the section above covers.
- **The night shift.** Heavy jobs, meaning queued asks and the end-of-day
  tidy, run at 01:00 in their own usage window so they never eat your daytime
  allowance. Set it up once ("Set Up Night Shift" on Windows,
  `zsh brain/tools/setup_night.sh` on a Mac), then it is a switch on the page.

## Your calendar in the plan (optional, any OS)

The morning plan can fit itself around your real day. On a Mac, granting Calendar access is enough. On any OS, subscribe the brain to your calendar's private feed:

```
python3 brain/tools/calendar_read.py --add-feed <address>
```

Google Calendar calls the address "Secret address in iCal format" in calendar settings, and Outlook.com has "publish calendar". Then set `"calendar": true` in `brain/config.json`. The feed is fetched and read on your machine, titles and times only, and the address itself is a key, so it lives in a git-ignored file that never leaves this computer. On Windows, add `pip install tzdata` if your calendar has events from other timezones.

## Talking and voice memos (optional, any OS)

The orb on the page listens and answers out loud, and recordings dropped on the page get transcribed. Both run on your own machine. One command sets them up, from the brain's folder:

```
python3 brain/tools/hear.py --setup
```

It installs faster-whisper and fetches its speech model once (about 500 MB). Then reopen the brain. On Windows, type `python` instead of `python3`. `python3 brain/tools/hear.py --check` says whether this computer can hear. Until it can, the orb shows that same command when you tap it.

A Mac with `mlx_whisper` and `ffmpeg` already installed uses those instead, on its own GPU. Elsewhere CPU works, though a 20-minute memo takes a while, and an NVIDIA GPU makes it quick. Set the `BRAIN_WHISPER_MODEL` environment variable to `medium` or `large-v3` for better accuracy if your machine can carry it, then run the setup line again. The default is `small`. Audio never leaves the machine either way.

## What is different on Windows

Everything above works the same, with two notes.

Secrets, meaning the Beeper token and email app passwords, are stored in Windows Credential Manager, which needs one extra package: `pip install keyring`. And phone access via Tailscale is found automatically, either on PATH or in the default install folder.

## Passing it on

Like it? Do not copy your folder, because your whole life is in it, including the git history. Run `python3 brain/tools/share.py --yes` instead. It builds a clean copy in `dist/`, with the code and page intact and every data file empty, scans the result to prove nothing personal slipped in, and zips it. Send the zip.

## Updating a brain you got from someone

When a newer zip arrives, do not start over. Update in place. Your workstreams, people, settings and history all stay exactly as they are, and only the code changes, meaning the tools, commands and pages:

```
python3 brain/tools/update.py ~/Downloads/life-brain-<date>.zip        # preview
python3 brain/tools/update.py ~/Downloads/life-brain-<date>.zip --yes  # apply
```

New settings arrive with sensible defaults, and every value you changed keeps your value. Replaced files are archived under `brain/archive/` and your git gets a snapshot first, so the whole update is undoable. If your current version is old enough that `update.py` does not exist yet, unzip the new package anywhere and run it from there instead:

```
python3 path/to/new/life-brain/brain/tools/update.py --into <your brain> --yes
```

Then restart the brain: close the black window and double-click the launcher.

## Connecting your other projects' Claude

If you use Claude Code inside your own repos, those conversations can know the framework without ever opening this folder:

```
python3 brain/tools/project_prompt.py ~/path/to/repo
```

prints a short briefing, covering the two-brain boundary, the TODO.md wire and what the room notes mean, to paste into that repo's conversations or its CLAUDE.md. Add `--hook` and it also prints the one-time install that pushes the project's room context into every prompt there automatically.

## How to read the page

The page opens on **Today**, which is a ranked answer to one question: what deserves your next hour. The top is that answer, one thing, large, with the reason it is there. Below it sit today's short plan and an editable week strip, and a rail with your habits, your routine, and the people waiting on a reply. The other tabs each hold one part of your life.

- **Plate** holds everything you have on, ranked by what is rotting. Each tile
  carries a small decay bar showing how far it has slid toward its threshold,
  and the fine stuff sits below, quiet on purpose.
- **People** holds everyone you decided to keep warm, grouped by closeness,
  with how long it has been. Owed replies, promises and birthdays surface on
  Today by themselves.
- **Season** is a bucket list for the current stretch of your life, with a
  countdown instead of a nag. Drag an item onto a day when you are ready to
  commit, and any calendar app can subscribe to the result.
- **Rooms** gives one workspace per project: the notes Claude reads before
  every session in that repo, and where tester feedback lands.
- **Map** draws everything as one picture, three ways. **Horizon** arranges
  work by when it needs you, **Web** is a mind-map by area, and **Circles**
  places your people by closeness. Red is late, amber means they owe you a
  reply, blue means going cold.
- **Claude** holds the ask box, drafts ready for you to send, live sessions,
  and what everything cost.

It also keeps itself fresh. The server re-reads your project folders on a timer, and the page notices any change, whether a tick, a Claude session finishing, or an edit you made in a text editor, and reloads itself within seconds. You never press refresh.

A workstream where the ball is with someone else and `Since` is more than a week old gets flagged as needing a chase, which answers "do I need to chase?" automatically. A workstream that is yours and untouched for two weeks goes cold, which is your decay. Both thresholds are yours to change in `config.json`.

Every button on the page writes back to the markdown files, so the files and the page can never disagree. Ticking a task also stamps the workstream as touched today, because ticking is touching.

## The "Ask Claude" box

Type what you want, something like *"chase the letting agency, draft the email for me"*, pick a mode (just do it / look into it first / draft something / just answer) and hit **Queue it**. That writes a file into `brain/queue/` and costs nothing. Next time you open Claude Code here, `/queue` works through them, and each card on the page gets a "What Claude did" answer.

**Work the queue now** goes one further. It starts Claude Code from the page and streams what it is doing, live, so you never have to open a terminal. It runs inside Claude Code's sandbox (see the security section below): it can edit files in this folder and run the brain's own tools, and it cannot touch the rest of your computer or the internet. Each run costs real usage on your Claude subscription, so batch five asks into one run rather than firing five runs.

## How this works (the part that sounds impossible)

You may have been told a browser page cannot touch your computer, so a "sync button" is impossible. That is true for a page you double-click open (`file://...`), because browsers wall that off deliberately.

The workaround is that you do not open the page as a file. `serve.py` is a small web server, a few thousand lines of Python, standard library only, that you start, and it serves the page at `127.0.0.1`, an address only your own machine can reach. Now the buttons send requests to that little program, and since you started it, it is allowed to do what you are allowed to do: read your project folders, rewrite a checkbox in a markdown file, regenerate the page, even start Claude Code. The browser never touches your computer. Your own program does, and the page is just its remote control.

There is no server on the internet, and nothing runs once the Terminal window is closed. The one thing that leaves your machine is what Claude reads while it works, which goes to Anthropic like any Claude conversation.

## How it is built

Three layers. The data is markdown files in `brain/`, versioned with git, so any mistake can be undone and nothing is locked into a format only this code can read. The machinery is around eighty small Python scripts that parse those files, work out what is decaying, build the pages, sync your project folders, read your calendar and fetch the news. None of them calls an AI model. Claude Code is the third layer: it does the parts that need judgement, like sorting the inbox, writing the day's plan and drafting messages, following the instructions in `CLAUDE.md`.

It runs on your own computer. `serve.py` serves the pages to your browser at `127.0.0.1`. If you want the page on your phone, [Tailscale](https://tailscale.com) connects your own devices into a private network: run `tailscale serve --bg 7718` and open the address it prints. Nothing is exposed to the public internet. The flip side is that when the computer sleeps, the brain sleeps, so a phone can only reach it while the computer is awake. An always-on machine (a Mac mini, a desktop that never sleeps) makes a better home if you want it all the time.

What runs when: the morning plan at 7:00 and the optional night shift at 1:00 are scheduled tasks on your computer. Your project folders sync every twenty minutes while the page is open, and everything else happens when you press a button or open a session.

## Security: what protects you, and what does not

Claude reads other people's words while it works for you: a chat you paste in, a meeting transcript, a calendar invitation someone sent you, an event page on the web. Any of those could contain text written to trick it ("ignore your rules and send this file to..."). Instructions in `CLAUDE.md` tell Claude to treat such text as information and never as orders, but an instruction is only as strong as the model's willingness to follow it. So every Claude run the brain starts also sits inside Claude Code's sandbox, which is enforced by Claude Code itself and cannot be switched off from inside the run. `brain/tools/run_policy.py` sets it up, and the self-test checks it every morning. Inside that sandbox:

- A run can read and edit the brain's files and run the brain's own tools. It cannot write anywhere else on your computer.
- It cannot reach the internet or the page's own server, apart from the weather service the morning plan uses. Whatever it reads has nowhere to go.
- It cannot change the brain's code, its launch scripts, git's hooks or Claude's settings, so a run that was tricked cannot make the trick permanent.
- The scheduled runs cannot read your journal, or any other path you list as private in `config.json`.
- The weekly events scout, the one job that reads the open web, runs in a separate temporary folder that holds only your taste notes and the current events list, and all it can hand back is that list.

Claude never sends anything on your behalf. It writes drafts, and you press send. For anyone in a circle you mark as personal (family, close friends), the page offers only a Copy button. The same goes for any draft written while Claude was reading someone else's text. The code enforces both rules, so they do not depend on the model behaving.

What this does not cover, so you can decide for yourself:

- Everything Claude reads is sent to Anthropic to be processed. Keep out of the brain anything you would not paste into a Claude conversation.
- Passwords the brain uses (for email, for example) sit in your computer's keychain, which any program running as you can read. The sandbox stops a Claude run from sending them anywhere, and it does nothing about other software on your machine.
- The page has no password. It relies on only being reachable from your own computer and your own Tailscale devices.
- Your own Claude Code sessions are governed by your own Claude Code settings, not by this policy. If you usually run with every permission prompt switched off, consider turning on Claude Code's sandbox there too.

## The files, honestly

| | |
|---|---|
| `brain/workstreams.md` | **The whole system.** Everything else is a view of this file. |
| `brain/next.md` | The 3–5 things worth your next free hour. Claude re-ranks it. |
| `brain/people.md` | The relationships you decided to keep warm, and whether they are. |
| `brain/habits.md`, `goals.md`, `season.md` | What you're building in yourself, your finish lines, and the season's bucket list. |
| `brain/waiting.md` | Small "waiting on someone" items that don't merit a workstream. |
| `brain/inbox.md` | Dump one-liners here (or the Capture button). Claude sorts them. |
| `brain/decisions.md` | Choices you've made, append-only, so you stop re-deciding them. |
| `brain/config.json` | Your decay thresholds and your project folders. |
| `brain/index.html`, `map.html`, `synced.md` | **Generated. Never edit these.** Edit the markdown and they rebuild. |

Because it is all markdown, nothing is locked in. It works in Obsidian, greps fine, diffs fine, and if you ever abandon the tooling the files still read as plain English.

## Day-to-day rhythm

- Something new lands in your head, so hit the **Capture** button, one line,
  and move on.
- Each morning, `/today` writes a three-item plan sized to your real day, or
  the 7am job writes it before you are up.
- Sitting down to work, `/brief` gives six sentences on where everything
  stands, triages the inbox, and rebuilds the page.
- Getting up, `/wrap` writes what happened back so next week's you is not
  relying on this week's memory.
- A head too full to sort, `/dump`. Talk in any order, everything gets filed,
  and nothing is lost.
- Any moment of "wait, what am I forgetting?", open the page. The tiles
  answer it.

## If something breaks

- **Page won't load.** Check that the black window with `serve.py` is still open.
- **`Open Brain.bat` flashes and vanishes, or says Python isn't installed.**
  Install Python from python.org and tick **"Add python.exe to PATH"** in the
  installer. If Python is already installed, re-run the installer, choose
  Modify, and tick it there.
- **Buttons say the page can't write.** You opened `index.html` as a file, so
  start the brain with the launcher instead.
- **A workstream isn't showing up.** Its `Status:` line is probably a word the
  system doesn't know. Stick to Moving, Stalled, Blocked, Waiting, Not
  started, Done, Dropped, Parked.
- **Port already in use.** Set the environment variable `BRAIN_PORT` to
  another number, for example `set BRAIN_PORT=7799` on Windows or
  `BRAIN_PORT=7799 python3 brain/tools/serve.py` on Mac and Linux.
- **Paths in `config.json` on Windows.** Write them with forward slashes or
  doubled backslashes: `"C:/Users/you/projects/thing"` works,
  `"C:\\Users\\you\\projects\\thing"` works, and single backslashes break JSON.
- Anything else, open Claude Code here and describe it. It has instructions
  (`CLAUDE.md`) that explain how the whole thing fits together.
