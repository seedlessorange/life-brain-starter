# The page: five places and one box

Since 28 Sep 2026 ("The brain, redrawn": the plan is
`design/the-brain-redrawn.html`, the decision is in `decisions.md`). Load this
when a task is about where something shows on the page, or when adding a
card, a tray item or a way to talk to Claude.

## The rules the layout follows

- **Each place answers one question.** A card that does not answer its
  place's question belongs somewhere else. `route_views()` in build.py is
  the one place that moves a card between views.
- **Everything has one home.** A task lives on its front, a person on People,
  a meal in the Kitchen. Anywhere else it shows is a reference that opens the
  same card with the same buttons.
- **One box to talk to Claude**, on every page (chrome.py `ask_block()`).
  Never add a new text box that sends to Claude: open the box instead, with
  `window.brainBox.open({scope, intent, text, paths})` or an element carrying
  `data-box` (`data-box-ws`, `-task`, `-person`, `-src` + `-label`,
  `-intent`, `-text`).
- **One tray for what the brain proposes.** Anything waiting on her decision
  is a `tray_item()` in build.py's For you, in the order send, answer,
  confirm, read. Never a new standalone review card. The page's own
  questions (`model.asks()`, drawn by `tab_asks.py`, answered by serve.py
  `ask_answer`) lead the answer lines: at most three a day, one tap each,
  the guess marked `.primary` only when there is evidence for it, and a
  "not yet" quiet for 14 days in config `asked` (8 Oct audit). A project
  with three or more late tasks is one question, not one per task: "Go
  through them" lists each for three days past the daily limit, with Done,
  Still on, Next week (a real new date) and Let it go; "Let them all go"
  drops them. A task on today's plan never joins a pile, and prep for a
  named day that has passed ("ready for its 8 Oct gate",
  `model.event_passed`) goes to Probably done instead (10 Oct).
- **One grouping of fronts: the area.** Rooms carry the `area` of her life;
  wings retired.
- **Machinery lives under the hood**, behind the gear.

Four more since 7 Oct ("Fewer doors": the plan is `design/fewer-doors.html`,
the audit behind it `design/ux-audit-2026-10-07.md`):

- **A second door replaces the first.** When something new does what an
  existing button already does, one of them goes.
- **Her words choose the mode.** Claude works out what she meant. A switch
  exists only when it changes where her words go: kept without AI, kept
  private, masked for another AI.
- **One "behind" number per page,** counted one way everywhere.
- **The build keeps count.** `budget.py` holds the limits (header controls,
  the box's ⋯, a task's ⋯, a task row's buttons, page lengths); the
  self-test fails when a count goes over. A cut lowers its limit; raising
  one is her decision, never a fix for a failing build.

Four more from her 8 Oct review of the week ahead ("M4 — the ranking
function, gate readiness and the…", "and 7 more" dropping to a new line):

- **A task shown away from its front names the front.** Wherever a task
  appears outside its project (the week ahead, This week, the When card,
  For you), it carries the project as a `.fc-proj` chip.
- **Whole titles.** A task title wraps or clamps with CSS (`-webkit-line-clamp`,
  the full text in `title`), never `clip()`ped mid-word in Python.
  `budget.py --measure` counts titles that end in "…" and fails above zero.
- **A fold opens in place.** "Show N more" is a `<details>` whose rest
  appears under the shown items, in the same list, never a link that
  lands somewhere else.
- **The words are checked too.** A task line that won't read cold (a code,
  a bare label) is caught by `model.unclear_reason`; `tasklint.py` drafts a
  plainer wording each morning, and For you offers it with "Use this
  wording" or "Keep as is". A task the brain can verify itself goes in
  `model.SETTLED`, so "Probably done?" says what it checked.

## The places

| Place | Question | Views and parts |
|---|---|---|
| Today (`#/today`) | What do I do now? | the day, the three (with "Not today, and why"), the Friday hour on its day, "Also due by <day after tomorrow>" (every task due by then, live from the fronts, by area; the late ones folded behind one figure counted like the Week's "Already late"), Quick replies (the plan's chases and owed replies, one line), For you (five on show); rail: the calendar, Today's rhythm (habits, tonight's dinner, routine lines), and from 17:00 on her clock Today so far |
| Plate (`#/plate`) | What's on my plate this week? | List (by area, finish lines on top; rail: horizons, where attention went; foot: pages with no open work, the big questions, the idea shelf, audit an area) · Week (`#/week`, the week grid and the week ahead, whether the fortnight fits) · Map (`map.html`). "Claude can get ahead" and "What the ranking can't see" are For you lines since 7 Oct |
| Jobs (`#/jobs`) | Where is my job hunt? | the season slot for a search: a tab only while config `jobs.on` is true (`chrome.jobs_on()`). Needs you (chases, stale roles), In play by stage, New roles by company; rail: what you look for, companies you follow, found one yourself. `tab_jobs.py` |
| School (`#/school`) | What does this term need? | the season slot: a tab only while config `now.areas` holds School and `now.until` has not passed (`model.school_tab_on()`) |
| People (`#/people`) | Who needs me? | Needs you (Focus, Today's five, You owe a reply, Gone quiet, Outreach; rail: Up next) · Everyone (`#/everyone`: search, filters, the shelves, Dormant, archived, duplicates, the sorter) · Circles (`map.html#circles`). Needs you and Everyone are one section with a switch: page.js sets `data-ppl`, page.css shows `.pneedonly` or `.pall` |
| Life (`#/life`) | How am I living? | Overview (the habits lead in the wide column as a table, the last eight weeks then this week day by day; Season and Out there under them (Out there: the scout's starred picks, each with "+ Season"); Tonight, Routine, Learn and Journal in the side column; on a phone Tonight comes first) · Season (`#/season`; Out there at its foot, the picks first under "Top picks") · Kitchen (`cook.html`) · Routine (`routines.html`); Learn and Journal are cards on the overview |
| News (`#/news`) | What is going on out there? | the briefing (`newsview`). A part of Life until 8 Oct, when she asked for it in the bar; the header limit went to 13 for it |
| Under the hood (`#/hood`, the gear) | How does the brain run? | Settings (jobs and runs, the queue, what Claude finished, Fix and improve (tab_fix.py over fix.py: Something's wrong? runs the self-test and hands the report to the box, Change how it works opens the box, Recent changes with Undo by git revert, Pack my changes writes code-only changes to one file and never sends), recordings, the look; rail: connections, AI and spend, the brain's memory) · Usage (`usage.html`) · Privacy (`privacy.html`, privacy_page.py; [privacy.md](privacy.md)) · Conversations (`sessions.html`) |

A project's page is `rooms.html#room/<slug>`, reached from its row ("Its
page") or its finish line. A bare `rooms.html` goes to the Plate. The old
`#/claude` hash lands under the hood.

## Parts of the brain (8 Oct)

Her ask: let someone who wants less of the brain switch parts off. Under
the gear, "Parts of the brain" lists People, Habits, Routines, Kitchen,
Season, Learning, Journal, News and the Job hunt, each with Turn off /
Turn on (`/api/parts`, `tools/parts.py`). Off takes the part out of the
bar (People, News; Life once all six of its parts are off), off Life's
switch and cards, off Today's rhythm, out of the tips and the tour, and
stops its own background work. Its view says "<Part> is off" with the way
back, for an old link. Its files stay. A new part-specific card asks
`parts.on(<part>, cfg)` before it draws.

## The box

- **Scope:** none (the whole brain, source "The brain"); a task, workstream
  or person (a conversation in the brain's folder opened with context.py's
  pack, source "brain"); or a project folder (`src`: the conversation works
  in that repo). Intents that write into the brain (update, draft, dump)
  move a project scope to the brain's side of the same front.
- **No modes to pick** (7 Oct). Claude reads what she means: a
  conversation in the brain's own folder is told once how (`box_rules.py`
  READ_HER: tick, file, draft with the writing rules, critique, frameworks,
  a brain dump, or just answer), and voice's update reads the same rule.
  ⋯ holds three switches, each changing where the words go: just save it
  (`/api/capture`, no model), private journal (`/api/queue` mode journal,
  no model), hide the names (anonymize.py; text carrying its placeholders
  gets the names put back). The other intents stay in code for buttons
  that send them for her (Prepare application drafts, the security card
  looks into it first, a project's brain dump): `brainBox.open({intent})`.
- **Talk** is a button in the bar on every page and every style again
  since 9 Oct (`orb.button_html()`, through `data-talk`), just before ✦ Ask.
  Her words: "chatting back and forth is very important and it seems
  hidden". From 7 to 9 Oct it was only the box's mic, which went when the
  button came back (one door). On Orbit's Today it talks through the deck's
  orb while the deck is on screen; elsewhere the spoken conversation opens.
  Space still starts it. Under 1280px it is the orb alone, round; the bar
  also drops the name under 1100px and closes up the tabs at 761 to 860px,
  so seven tabs and a long name fit. An unsent line stays in the box across
  pages (`ask-draft`), which is what the ✎ ramble note did.
- **Start it for me**: opened from a task's ✦, the box offers the legwork
  run (page.js `window.brainStart`, a just-do-it queue item); what she
  types goes with it as precisions.
- **Receipts** come from the turn's own "Wrote"/"Edited" steps, never from
  what the model says it did.
- **For you** on Today shows five, the rest one click away; the panel reads `/api/tray` (build.py writes
  `brain/.tray.json`); each line is a door to the item on Today. "Got it" on
  a Read item stores its id in config `tray_seen`.
- Attachments ride as `files` (uploads) or `paths` (files already in the
  brain) on `/api/sessions/new` and `/say`; the server names them by full
  path (`attach_note`).
- **Files** is the list pane's second tab (docs.py, 28 Sep): drafts,
  transcripts, study guides, book notes, Word files in the brain, and
  what changed lately in her project folders, newest first. Her question
  was where a transcript or a new document can be seen, opened and fixed.
  The page knows ids only; `/api/files/read`, `/save` and `/open` look the
  id up again in a fresh list, so no path from the page reaches a file
  (security.md, finding 11). Markdown inside the brain edits in place (git
  is the undo); project files, Word files and PDFs open in their own app
  or the Finder, never edited here. Word previews from its own XML, study
  guides show in a frame, a confidential-named file is never previewed,
  and the journal is never listed. New documents from the last three days
  are Read lines in For you with an Open button (`data-openfile`), except
  message drafts (already Send lines) and batch re-renders.

## The task row

Every task, everywhere: the tick, then ✦ and ⋯ (`md.row_buttons`, one
copy for the plan rows and build.py's `taskrow`). On a laptop ⋯ shows when
she points at the row; on a touch screen it always shows.

- **After a tick** a line opens under the row, "Anything follow?" (page.js
  `followLine`). Enter posts `/api/task/follow`; serve.py `task_follow` has
  a small model (llm job "follow") say whether it is a next step (a new task
  under the ticked one, on its front even when ticked from Today), an
  answer (queued to be filed; the task line is left alone), or a hand-off
  (a chase task waiting until the day she named, Ball and Since moved
  together). Unsure, it asks with three buttons. Left empty, the line folds
  away after eight seconds; while it is open the page holds its refresh.
- **⋯** groups the rest: When (deadline, how long, park, block time), Change
  (reword, drop), and On today's three (kick, swap, another day, move).

## Where the code lives

- `build()` in build.py builds the shared state (the ranked workstreams,
  people, the queue, the For you lists), then calls one file per place:
  `tab_today.py`, `tab_plate.py`, `tab_people.py` and `tab_hood.py`, each a
  `render()` that takes only what it needs. Life, Season, News and the page
  assembly stay in `build()`. Shared card helpers (`tray_item`,
  `area_groups`, `route_views`…) stay in build.py and the tabs import them.
- A new card goes in its place's tab file. A helper two tabs need goes in
  build.py. Check the change with `python3 brain/tools/rebuild.py`.
- Server endpoints are named methods in serve.py's `Handler`, each marked
  with its path: `@on_post("/api/tick")`, or `@on_get("/api/tray*")` where
  `*` means a prefix. The first match in definition order wins.
