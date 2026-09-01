# Start here — Mac

This is a second brain for your life admin. It's a folder of plain text
files, a page that renders them, and Claude Code doing the filing so you
never have to.

Setup is six short steps and takes about twenty minutes, most of which is a
download running in the background. **You do not need to know anything about
Terminal** — Step 2 teaches you the one thing you need, and it takes ten
seconds.

If you get stuck at any point, double-click **`Check My Setup.command`** — it
looks at your machine and tells you which step is unfinished.

---

## Step 1 — Put the folder somewhere permanent

Double-click the zip. Finder expands it into a folder. Move that folder
somewhere you won't move it again — `Documents` is a good choice.

Don't leave it in Downloads. Some Macs clean that folder out, and this
folder becomes your actual notes.

It does **not** have to go in any particular place. The brain works out where
it lives on its own.

---

## Step 2 — Open Terminal at your folder

You need this a handful of times. It's one move and it always works:

1. Press **⌘ + Space**, type **Terminal**, press **Return**. A window with a
   text prompt opens.
2. Type `cd ` — the letters c, d, and then **a space**. Don't press Return.
3. **Drag your life-brain folder from Finder into the Terminal window.** It
   pastes the location for you.
4. Press **Return**.

That's it. Terminal is now "pointed at" your brain folder, and everything
below happens in this window. Leave it open.

---

## Step 3 — Let macOS trust the folder

macOS blocks files that arrived from the internet until you say otherwise.
Without this step, double-clicking anything in this folder shows a warning
like *"Apple could not verify this file is free of malware."*

In the Terminal window from Step 2, paste this line and press Return:

```
xattr -dr com.apple.quarantine .
```

Nothing visible happens. That's success — every launcher in the folder now
opens with a normal double-click.

*(If you'd rather not run that: you can instead right-click each `.command`
file and choose **Open**, then **Open** again in the dialog. Same result, one
file at a time. On very recent macOS you may need System Settings → Privacy
& Security → **Open Anyway** after the first attempt.)*

---

## Step 4 — Python

Python is the free programming language the page is built on. Most Macs
already have it.

**Check:** in your Terminal window, type this and press Return:

```
python3 --version
```

- **A version number appears** (like `Python 3.12.4`) — you're done, skip to
  Step 5.
- **A window pops up offering to install developer tools** — click
  **Install** and wait for it to finish. That gets you Python *and* Git in
  one go. Then run the check again.
- **"command not found"** — type `xcode-select --install`, press Return, and
  click Install on the dialog.

**Now try the page:** double-click **`Open Brain.command`** in the folder. A
Terminal window opens and your browser shows your brain page.

Leave that window open while you use the page. Closing it just stops the
page; nothing is lost.

---

## Step 5 — Claude Code

The page works on its own, but Claude Code is what makes the brain maintain
itself. This is the part you've probably not done before. It's still just an
installer.

1. Go to **[claude.com/claude-code](https://claude.com/claude-code)**.
2. Follow the install instructions for Mac on that page. Take whatever the
   page offers you — it stays current in a way a written guide can't.
3. When it's finished, go back to your Terminal window (Step 2) and type:

   ```
   claude
   ```

   The first time, it walks you through signing in with your Claude account
   in the browser. Do that once and it remembers.

**Check it worked:** double-click **`Check My Setup.command`**. It should say
Claude Code is installed.

That check also looks for **Git** — your undo button. The brain snapshots
your files before and after every job, so a bad edit is always reversible.
Macs that have the developer tools from Step 4 already have it.

---

## Step 6 — Build your brain

With `claude` running in your Terminal, type this and press Return:

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

## Step 7 — Settings that matter on a Pro plan

Claude's Pro plan gives you a generous but finite amount of usage in rolling
five-hour windows. These keep the brain comfortably inside it.

**a) Careful mode is already on.** On the page, next to "Talk to Claude",
you'll see a **Careful / Full** switch already set to **Careful**. That means
nothing runs or spends unless you ask it to, and jobs use the cheapest model
by default. Leave it there.

**b) Don't pick Opus.** When a job offers you a model, choose **Haiku** for
filing and tidying, **Sonnet** when you want it to think. Opus isn't included
on Pro.

**c) Mornings that run themselves.** In your Terminal window (Step 2), type:

```
zsh brain/tools/setup_morning.sh
```

Every morning at 7:00 the brain syncs, rebuilds the page, and notifies you
*only* if something is genuinely overdue. In Careful mode it does all of that
without spending anything. If your Mac is asleep at 7:00, it runs when you
open the lid.

To undo: same command with ` --off` on the end.

**d) The night shift — worth it if your Mac stays on.** The heavy jobs run at
1am so they aren't competing with your day for the same allowance, and
they're finished long before you wake.

```
zsh brain/tools/setup_night.sh
```

Then on the page, click **Turn on** next to "Night shift."

**Is this right for you?**

- **An iMac, Mac mini, or a laptop you leave plugged in and open** — yes. Run
  the command it prints at the end (`sudo pmset repeat wakeorpoweron ...`) so
  the Mac wakes itself for the job.
- **A MacBook you close at night** — it will simply skip most nights, which
  is harmless. It refuses to run on battery, and it refuses to run in
  daylight, so it will never surprise you at 9am. You can turn it on and
  forget about it; it just won't do much.

---

## That's setup. Here's the daily rhythm.

You only ever do three things:

1. **Drop thoughts in.** Type them into the box on the page, any time, in any
   order. No categories, no tags.
2. **Tick things off** on the page as you do them.
3. **Answer direct questions** when the brain asks one.

Everything else — filing, re-ranking, chasing dates, rebuilding the page — is
Claude's job. That's the whole point: a second brain that needs discipline
from you is dead in three weeks.

When you sit down, open Terminal at the folder (Step 2), run `claude`, and
type `/brief` — it catches you up in plain language. When you get up, `/wrap`
folds the session back into the files.

---

## Two things Macs do better

Both optional, both worth it, both set up by asking Claude in the folder.

- **Your real calendar in your daily plan.** On a Mac, granting Calendar
  access is all it takes — the morning plan then fits itself around the
  meetings you actually have. Titles and times are read on this Mac and
  nothing about your calendar leaves it.
- **Voice memos, transcribed on your own machine.** Drop a recording on the
  page and an Apple Silicon Mac transcribes it with its own GPU, then turns
  it into tasks. Nothing is uploaded.

The **Connections** button at the top right of the page lists these and the
rest — chat sync, a Telegram bot, email drafts — with live status.

---

## When something goes wrong

**Double-click `Check My Setup.command` first.** It diagnoses the common
problems and tells you the fix.

| What you see | What it means |
|---|---|
| *"Apple could not verify..."* | Step 3 hasn't been done. Run the `xattr` line. |
| The Terminal window flashes and vanishes | Python is missing. Run `xcode-select --install`. |
| Browser says "can't connect" | The page isn't running. Double-click `Open Brain.command`. |
| `command not found: claude` | Claude Code isn't installed, or this window was open before you installed it. Close it, open a new one. |
| The page looks out of date | Click the green dot in the header to sync now. |
| A job says "already running" | One job runs at a time. Wait for it, or reload the page. |

`Check My Setup.command` also runs the brain's own health check — several
dozen checks over its files and its safety rules, in about a second. If that
part reports a problem, copy those lines into `claude` and it will fix them.

Anything else: run `claude` in the folder and just describe what happened. It
can read its own logs and usually fixes it.

---

## What this does with your data

Everything stays in this folder on your Mac. The page runs on your own
machine and is only reachable from it.

The brain drafts messages and emails for you, but **it never sends
anything** — you always press the button yourself. Anyone you mark as close
family or a close friend is draft-only in code; the brain cannot message them
even if you ask it to.

---

## What it costs

Nothing beyond the Claude subscription you already have. To see what you've
been using, in Terminal at the folder:

```
python3 brain/tools/usage.py
```

That's every job the brain has run, by day and by model. For where you
actually stand against your plan's limits, run `claude` and type `/usage`.
