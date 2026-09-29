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
  confirm, read. Never a new standalone review card.
- **One grouping of fronts: the area.** Rooms carry the `area` of her life;
  wings retired.
- **Machinery lives under the hood**, behind the gear.

## The places

| Place | Question | Views and parts |
|---|---|---|
| Today (`#/today`) | What do I do now? | the day, the three, School today, the Friday hour on its day, the two-minute sweep (owed replies + quick wins), For you, the week-fits forecast; rail: the calendar, Today's rhythm (habits, tonight's dinner, routine lines) |
| Plate (`#/plate`) | What's on my plate this week? | List (by area, finish lines on top; rail: horizons, what the ranking can't see, where attention went, Also needs you; foot: pages with no open work, the big questions, the idea shelf, audit an area) · Week (`#/week`, the week grid) · Map (`map.html`) |
| School (`#/school`) | What does this term need? | the season slot: a tab only while config `now.areas` holds School and `now.until` has not passed (`model.school_tab_on()`) |
| People (`#/people`) | Who needs me? | List · Circles (`map.html#circles`) |
| Life (`#/life`) | How am I living? | Overview (today's slice of each) · Season (`#/season`) · Kitchen (`cook.html`) · Routine (`routines.html`) · News (`#/news`); Learn and Journal are cards on the overview |
| Under the hood (`#/hood`, the gear) | How does the brain run? | Settings (jobs and runs, the queue, what Claude finished, recordings, the look; rail: connections, AI and spend, the brain's memory) · Usage (`usage.html`) · Conversations (`sessions.html`) |

A project's page is `rooms.html#room/<slug>`, reached from its row ("Its
page") or its finish line. A bare `rooms.html` goes to the Plate. The old
`#/claude` hash lands under the hood.

## The box

- **Scope:** none (the whole brain, source "The brain"); a task, workstream
  or person (a conversation in the brain's folder opened with context.py's
  pack, source "brain"); or a project folder (`src`: the conversation works
  in that repo). Intents that write into the brain (update, draft, dump)
  move a project scope to the brain's side of the same front.
- **Intents** (behind ⋯): talk (default), just save it (`/api/capture`),
  tick off what happened, draft, look into it first, just answer, tear it
  apart, the frameworks, keep it as my journal (`/api/queue` mode journal,
  no model), queue it for later (`/api/queue`). The live ones are the
  queue's own modes, said as an instruction in front of her words.
- **Receipts** come from the turn's own "Wrote"/"Edited" steps, never from
  what the model says it did.
- **For you** in the panel reads `/api/tray` (build.py writes
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
