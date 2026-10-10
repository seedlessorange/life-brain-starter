# Brain Pen: the ⌃⌥R rewriter

Load this when changing `pen.py`, `pen.swift`, `make_pen_app.sh`, the
`/api/pen/*` endpoints, or `writing-samples.md`. Built 7 Oct 2026 at her
request: select text (or just click into a box) in any app, press ⌃⌥R, get
it back in her voice in the tone she picks, give feedback, and it improves.

## What she sees

- ⌃⌥R in any app. A panel opens under the caret with the text rewritten
  "Polished": her voice, the register the app implies (WhatsApp stays a
  chat, Outlook stays an email). Buttons, also ⌘1 to ⌘9: Polished, Fix
  typos, Warmer, Politer, Casual, Shorter, English, Français, Español.
- The line under the text takes feedback. A note plus Return rewrites again
  with it; Return on an empty line (or ⌘Return) puts the text back in the
  box; Esc closes and changes nothing. The rewrite is editable in place.
- Panel keys: ⌘R another version, ⌘D show or hide the changes, ⌘I how
  your message reads, ⌘B brain check, ⌘E edit the rewrite, ⌘L back to the note line, ⌘T
  tu or vous, ⌘G the reader, ⌘⇧C copy instead of replacing, ⌘, shortcuts.
  The one button is Replace (⌘Return): it puts the rewrite in place of
  her text.

## Languages, cost, models (7 Oct, her questions)

- Fix typos runs on Haiku (`TONE_MODELS`, 0.7 s warm), the tones on the
  default model (Sonnet: 1.3 to 4 s warm). One kept-open Claude per model,
  both warmed together. Measured on the ledger: a Sonnet rewrite is about
  5.8k tokens, almost all cache reads, roughly $0.003 of plan allowance.
  (Before 7 Oct the pen folded cache reads into input and the ledger
  showed it about five times dearer.)
- Every text is told to come back in its own language: one open session
  otherwise carried French into the next English text.
- In gendered languages the panel shows Tu/Vous (⌘T) and Reader (⌘G:
  auto, a man, a woman, not sure, a group). Auto follows the original's tu
  or vous, then the people file; the reader's gender comes from people.md
  Pronouns or is left out of the wording, never guessed from a name. Her
  own agreements come from her voice rules (feminine).
- Polished must keep every sentence's point (it once dropped "je suis
  désolé"); Fix typos keeps chat shorthand and lowercase.

## Her words first (added 7 Oct, her ask: useful, never replacing the
## human touch)

- **The changes view** is on by default (⌘D toggles, remembered): her
  words struck through on red, the rewrite's on green, word by word
  (longest common subsequence in pen.swift). Clicking a change puts her
  words back for that change only, so she keeps the phrasing she likes.
  Translations show plain text: every word changes.
- **How does this read?** (`pen.read`, `/api/pen/read`; ⌘I in the panel,
  ⌃⌥H anywhere, where the read shows under the caret and nothing changes).
  One or two sentences on how HER original message will land and the one
  thing likely to be misread, at most one suggestion, never a rewrite. It
  uses the same kept-open Claude (a turn marked READ) and the person's
  Pronouns, else "they". Em dashes are stripped in code.
- The menu-bar pencil: Rewrite, Train my voice, Learning mode, Shortcuts,
  Open at login. The settings window has three tabs: My voice (paste real
  sent messages; see and forget feedback notes), Learning, Shortcuts.

## Shortcuts (added 7 Oct, her ask: no mouse)

- Any action takes any keys with ⌃, ⌥ or ⌘: open the pen (default ⌃⌥R),
  open Train my voice, how does this read (default ⌃⌥H), and each tone
  "straight into the box" (default ⌃⌥T for Fix typos). Kept in the app's own preferences (UserDefaults
  `shortcuts`), since they belong to this Mac's keyboard, not the brain.
- A tone's own shortcut rewrites and pastes with no panel; a small toast
  under the caret says what happened, and ⌘Z in the app undoes it. Before
  pasting it checks she is still in the same box and that its text has not
  changed (`stillThere`); if she moved on, the rewrite goes on the
  clipboard instead.
- A combination another app already holds shows "taken" in the tab.

## Learning mode (added 7 Oct, her ask: off unless she turns it on)

- Its purpose is that she writes better herself, which is why it sits
  apart from the rewrites. Stored as `learning` in `.pen-log.json`.
- After she USES a rewrite (a message she only selected may be someone
  else's), `/api/pen/done` passes the original to `pen.learn_later`: one
  background no-tools call (`llm.complete("penlearn")`) lists real
  mistakes as JSON. Style never counts (lowercase, "tmrw", emoji, a chat
  without a full stop). Code drops any mistake whose words are not in her
  text, and keeps only the pattern name, at most six of her words, the fix,
  a one-line rule and whether it is wrong in any sentence (`always`).
- Known pattern names go back into the call so the same mistake groups
  under one name. `patterns()` lists those seen twice or more in 60 days,
  with counts for the last two weeks and the two before ("fading").
- The panel shows one tip when a repeated misspelling (`always` only, so a
  correct "its" is never flagged) is in the text she is rewriting. "Not a
  mistake" stops counting a pattern.

## The brain, in slices (8 Oct, her choice over a "full brain" mode)

She asked whether the pen should get the whole brain. Not as a mode: about
55k tokens a turn against 6k, her family, health and money facts in the
room with every text she sends a recruiter, and a model that holds the
brain adds "as discussed Tuesday". She chose three slices instead:

- **Names** (`names_for`, every rewrite, no model). The distinctive words
  in the names of her people, workstreams, rooms and places (from the
  graph; a word in the Mac's word list never counts) that appear in the
  text, or are one slip from a capitalised word in it (two past eight
  letters, swapped letters count as one), ride in the turn as "NAMES IN
  THIS TEXT". Two names equally near are left alone. Nothing else about
  anyone goes in. `pen.py names "text"` shows it.
- **Put-backs** (`revert_line`). Clicking a change back to her words is
  counted per tone (`reverts` in the log; a put-back is not a hand edit).
  At 3 or more over 2 or more uses in 30 days, that tone's turns are told
  to change less. In the turn, not the pack, so the cache stays.
- **Brain check** (⌘B in the panel, `pen.check`, `/api/pen/check`). The
  graph is asked about the names in her message only (`recall` with
  `word_ok`, twelve seeds, one hop, 20 facts; the person from the chat
  title is added). It runs in its own kept-open session
  (`brain-pen-check-`), so the facts never sit where rewrites are written,
  and it reports only: "You wrote “due Tuesday 13 Oct”. The update is due
  Monday 12 Oct." Each slip must quote the line of her notes it rests on;
  code drops it when that quote, or her words, are not really there.
  A weekday next to a date ("jeudi 9", "Thursday, October 9") is checked
  in code (`weekday_slips`), exact and free; without a month, the number
  must end the phrase, so "Saturday 2 tickets" is not a date. No facts on
  the names means no model call.
- Measured 8 Oct over nine messages: every slip caught, every correct
  version passed, 4 to 6.5 s cold and 1.3 to 2.6 s warm. An earlier
  version, given six seeds, missed the right fact and "corrected" a due
  date with another event's date; the twelve seeds and the quoted source
  are the fix. `pen.py check "text"`. The log keeps `checked`, the
  number of slips shown, so two weeks of use say whether it earns its key.

## How it works

- **The app** (`pen.swift`, built by `make_pen_app.sh` into
  `Brain Pen.app` at the repo root, gitignored). The hotkey is Carbon's
  `RegisterEventHotKey`, which needs no permission. Reading the box and
  pressing ⌘C/⌘A/⌘V need Accessibility. It reads the selection through
  Accessibility, else the whole box's value, else a ⌘C (then ⌘A ⌘C, only
  in a text role or an app that exposes nothing; never in Finder). Password
  fields are refused. Putting back is a paste, marked transient for
  clipboard managers, and her clipboard is restored after. It never
  presses send.
- **The server** (`/api/pen/state|warm|rewrite|done|sample|forget`). These
  reach only `pen.py`. The rewrite text is never written to disk.
- **The model** (`pen.py`). One Claude kept open (`voice._Mind` with the
  pen's own system prompt, `brain-pen-` temp folder, 45 minutes keep-warm,
  20 turns), sealed like llm.py. Measured 7 Oct on Sonnet: about 2 s per
  rewrite when warm, 4 to 6 s cold. The app warms it when she switches to
  a chat, mail or browser app, at most every ten minutes. A rewrite that
  fails `textcheck` is redone once in the same session. If the kept-open
  one fails, or config routes the job (`llm.jobs.pen`, e.g. Ollama), the
  answer comes from `llm.complete("pen", audience="other")`. Model: config
  `pen.model`, else `llm.models.pen`, else `llm.model`.
- **What each rewrite is told** (`pen.py pack` prints it): the voice card,
  all of `writing-rules.md`, `writing-samples.md`, and her last ten feedback
  notes from the past 30 days. Per turn: the register from the app, the
  tone, the person's Register and Pronouns when the greeting or window
  title names exactly one people.md entry, the names in the text, the
  tone's "change less" line when she keeps undoing it, and her notes on
  this text.

## What is kept, and how it learns

- `brain/.pen-log.json` (gitignored): per use, the app, register, tone,
  used, edited by hand, length, put-backs per tone, slips the brain check
  showed, and her feedback notes. Never the text and
  never the window title: she will sometimes select someone else's message.
- Same day: the last ten notes ride in every rewrite. Forget removes one.
- Weekly: `lessons.py` reads the notes as `pen` signals, so repeated
  feedback becomes a proposed writing rule in the lesson tray, kept or
  binned by her.
- `brain/writing-samples.md` (gitignored, her words): messages she pasted,
  under headings, separated by `---`. The brain appends what she pastes and
  never rewrites it.

## Finding it

- `Brain Pen.app` sits at the top of the life-brain folder (gitignored, so
  only the build script is in git). Spotlight finds it as "Brain Pen".
- On a MacBook with a notch, a full menu bar hides the newest icons
  behind it, so the pencil can be invisible. Opening Brain Pen again
  (Finder, Spotlight) shows its window (`applicationShouldHandleReopen`),
  and a launch without Accessibility opens the window by itself. The
  window's top line says whether Accessibility is on, with a button to
  the right settings pane.

## The window and the panel (7 Oct, her review)

- Until Accessibility is on, the window is only a setup screen (switch it
  on; "Fix the switch" runs `tccutil reset Accessibility` for Brain Pen's
  own entry and restarts it, for a switch left over from an older build).
  Once on, the setup is gone: three tabs and a "Ready · ⌃⌥R" line.
- Nothing selected is no longer an error: the panel opens a box to paste
  or type into, and the rewrite goes on the clipboard (the button reads
  Copy). Password fields are still refused. The panel has a close button.
- The recorder refuses combinations that would break basics in every app
  (⌘Z, ⇧⌘Z, ⌘C, ⌘V, ⌘X, ⌘A, ⌘S, ⌘Q, ⌘W, ⌘Tab, ⌘Space) and flags others
  apps use (⌥Space for Alfred, ⌘T, ⌘F…).

## Two fixes from her first real use (7 Oct)

- Replace in Beeper pasted her copied screenshot instead of the rewrite:
  Chrome-based apps read the clipboard late, and the 0.9 s restore beat
  them. The restore now waits 3 s and is skipped if anything else touched
  the clipboard meanwhile; the rewrite is re-checked on the clipboard just
  before ⌘V.
- Pasting into the panel did nothing: a menu-bar app has no Edit menu, so
  ⌘V/⌘C/⌘X/⌘A/⌘Z had nowhere to go. A hidden Edit menu plus `editKey`
  (sent straight to the focused box) fixes the panel and the settings
  window; checked in a hidden window (empty before, pasted after).

## Rebuilding

`zsh brain/tools/make_pen_app.sh`, then Accessibility has to be switched on
again for the new build (macOS ties it to the signature). `pen.swift`,
`make_pen_app.sh` and the built app are on the security alarm's watch
list, because the app holds Accessibility.
