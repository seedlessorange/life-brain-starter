# Start here — Windows

This is a second brain for your life admin. It's a folder of plain text
files, a page that renders them, and Claude Code doing the filing so you
never have to.

Setup is four steps and takes about twenty minutes, most of which is two
downloads running in the background. **You do not need to know anything
about terminals.** Where a step needs one, it says exactly what to type.

If you get stuck at any point, double-click **`Check My Setup.bat`** — it
looks at your machine and tells you which step is unfinished.

---

## Step 1 — Put the folder somewhere permanent

Unzip this folder to somewhere you won't move it later. `Documents\life-brain`
is a good choice.

Don't put it in Downloads. Some Windows setups clear that folder, and this
folder becomes your actual notes.

---

## Step 2 — Install Python

Python is the free programming language the page is built on. You install it
once and never think about it again.

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and
   click the big yellow **Download Python** button.
2. Run the file it downloads.
3. **On the first screen, tick the box that says "Add python.exe to PATH."**
   It's at the bottom and it is easy to miss.

   That checkbox is the single most common reason this doesn't work. If you
   miss it, run the installer again and choose Modify.
4. Click **Install Now** and let it finish.

**Check it worked:** double-click **`Open Brain.bat`** in this folder. A
black window opens and your browser shows your brain page. If instead the
black window says Python isn't installed, the checkbox got missed — install
again.

Leave that black window open while you use the page. Closing it just stops
the page; nothing is lost.

---

## Step 3 — Install Claude Code

The page works on its own, but Claude Code is what makes the brain maintain
itself. This is the part you've probably not done before. It's still just an
installer.

1. Go to **[claude.com/claude-code](https://claude.com/claude-code)**.
2. Follow the install instructions for Windows on that page. Take whatever
   the page offers you — it stays current in a way a written guide can't.
3. When it's finished, you need to sign in once. Open a terminal (Step 4
   explains how, in one line) and type:

   ```
   claude
   ```

   The first time, it walks you through signing in with your Claude account
   in the browser. Do that once and it remembers.

**Check it worked:** double-click **`Check My Setup.bat`**. It should say
Claude Code is installed.

That check also looks for **Git**. Git is what gives you an undo button —
the brain snapshots your files before and after every job, so a bad edit is
always reversible. Most people who install Claude Code already have it. If
the check says it's missing, get it from
**[git-scm.com/download/win](https://git-scm.com/download/win)** and accept
every default. Everything works without it; you just lose the safety net.

---

## Step 4 — Opening a terminal in this folder

You need this exactly twice: once for setup, once whenever you want to talk
to your brain directly. It's one action.

**In File Explorer, open this folder. Click the address bar at the top
(where it shows the folder path), type `cmd`, and press Enter.**

A black window opens, already pointing at this folder. That's it — that's
the whole skill.

Now type this and press Enter:

```
claude
```

You're talking to Claude, inside your brain folder. It can read and write
the files here and nothing outside them.

---

## Step 5 — Build your brain

With `claude` running (from Step 4), type this and press Enter:

```
/onboard
```

The `/` at the start matters — it's how you run one of the brain's built-in
routines rather than just chatting.

Then **talk**. It asks about your projects, the people you owe replies to,
the deadlines you're carrying, the things you keep meaning to do. Answer in
whatever order things come to you — it sorts them out. There is no format to
learn and nothing you can get wrong.

When it's done, go back to your browser and refresh. Your brain is there.

---

## Step 6 — Settings that matter on a Pro plan

Claude's Pro plan gives you a generous but finite amount of usage in rolling
five-hour windows. Three settings keep the brain comfortably inside it. Do
these once.

**a) Turn on Careful mode.** On the page, find the **Careful / Full** switch
next to "Talk to Claude" and set it to **Careful**. This means nothing runs
or spends unless you ask it to, and jobs use the cheapest model by default.

**b) Don't pick Opus.** When a job offers you a model, choose **Haiku** for
filing and tidying, **Sonnet** when you want it to think. Opus isn't
included on Pro.

**c) Turn on the night shift.** This is the one that makes Pro comfortable.
The heavy jobs run at 1am while you're asleep, so they aren't competing with
your day for the same allowance — and they're finished long before you wake.

Double-click **`Set Up Night Shift (Windows).bat`** once. Then on the page,
click **Turn on** next to "Night shift." (It stays off until you click that,
so setting up the schedule by accident costs nothing.)

Your PC needs to be on (or asleep — Windows wakes it for the job) at 1am. It
refuses to run on battery, and it refuses to run in daylight, so a laptop
you shut at midnight just skips the night rather than surprising you at
9:15am.

**d) Optional — mornings that run themselves.** Double-click
**`Set Up Mornings (Windows).bat`** once. Every morning at 7:00 the brain
syncs your folders, rebuilds the page, and notifies you *only* if something
is genuinely overdue. In Careful mode it does all of that without spending
anything.

---

## That's setup. Here's the daily rhythm.

You only ever do three things:

1. **Drop thoughts in.** Type them into the box on the page, any time, in
   any order. No categories, no tags.
2. **Tick things off** on the page as you do them.
3. **Answer direct questions** when the brain asks one.

Everything else — filing, re-ranking, chasing dates, rebuilding the page —
is Claude's job. That's the whole point: a second brain that needs
discipline from you is dead in three weeks.

When you sit down at your computer, open a terminal in the folder (Step 4),
run `claude`, and type `/brief` — it catches you up in plain language. When
you get up, `/wrap` folds the session back into the files.

---

## When something goes wrong

**Double-click `Check My Setup.bat` first.** It diagnoses the three common
problems and tells you the fix.

| What you see | What it means |
|---|---|
| The black window flashes and vanishes | Python isn't on PATH. Reinstall it with the checkbox ticked (Step 2). |
| Browser says "can't reach this page" | The black window isn't running. Double-click `Open Brain.bat`. |
| `'claude' is not recognized` | Claude Code isn't installed, or the terminal was open before you installed it. Close the black window, open a new one, try again. |
| The page looks out of date | Click the green dot in the header to sync now. |
| A job says "already running" | One job runs at a time. Wait for it, or reload the page. |

`Check My Setup.bat` also runs the brain's own health check — several dozen
checks over its files and its safety rules, in about a second. If that part
reports a problem, copy those lines into `claude` and it will fix them.

Anything else: open `claude` in the folder and just describe what happened.
It can read its own logs and usually fixes it.

---

## What this does with your data

Everything stays in this folder on your PC. The page runs on your own
machine and is only reachable from it.

The brain drafts messages and emails for you, but **it never sends
anything** — you always press the button yourself. Anyone you mark as close
family or a close friend is draft-only in code; the brain cannot message
them even if you ask it to.

---

## What it costs

Nothing beyond the Claude subscription you already have. To see what you've
been using, open a terminal in the folder and type:

```
python brain\tools\usage.py
```

That's every job the brain has run, by day and by model. For where you
actually stand against your plan's limits, run `claude` and type `/usage`.
