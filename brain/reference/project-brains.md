# The project brains, and how they report up

Load this when working on the handoff, on `sync.py`, or in one of her app
repos' own brains.

Her app repos keep their own second brain — the same design as this one, one
level down: `state.md` (what actually works for a user, as Works / Unverified /
Half-built / Fake / Broken), `next.md` (ranked open work), `questions.md`
(decisions blocked on her), `qa.md` (what she still has to check by hand).
**`brain-kit/` inside the first repo you set up is the portable
installer** (`python3 install.py /path/to/repo`, costs nothing, safe to re-run
— it refreshes the tools and never touches markdown). Install the project brain in
whichever repos you actually work in; the recall hook can also run alone in
a repo that has no project brain of its
own (sync falls back to its README).

**Two brains, one boundary, and it must not move:** the project brain owns
*what state this project is in*; this brain owns *whether it deserves her
week*. So a workstream for one of those repos holds the room, its due date,
its goal and one next action — not a mirror of the project's task list. Two
files listing the same tasks is how both of them start lying.

**The project repo's own `brain/handoff.md` is the whole integration** (these
are files in each app repo, not in this brain). Each project brain generates
it (that repo's `brain/tools/handoff.py`, run by its `build.py`): fifteen lines
carrying the worry headline, the top three next actions as plain `- [ ]`
lines, how many decisions are blocked on her, how many hand-checks are owed.
`sync.py` reads unticked checkboxes out of the files a source lists, so that
markdown convention *is* the wire — there is no endpoint and no schema to keep
in step. Three rules hold it together:

- **Its `- [ ]` lines are the only checkboxes allowed in a file this brain
  reads.** Anything else in a listed file arrives here as a task.
- **`sync.py` regenerates it before reading it** (`refresh_handoff`), so it
  cannot go stale between builds in that repo. That is the maintenance rule
  crossing the boundary: she should not have to remember to rebuild a page in
  another folder for this one to be true. It runs no model and writes only
  that one file — the single exception to "sync only reads".
- **`(yours, not Claude's)` on an action is the field that matters most.** It
  means nobody but her can do it, so it is a real candidate for her three in
  `/today`; everything else in that list can be delegated to a run.

`rooms.py` reads the handoff (`handoff_for`) and shows it on the room, with an
**Open its brain** button that opens that repo's own page. Alongside it, the
ask box on a room already runs Claude Code **in that repo** (`job: project` in
`serve.py`, cwd set to the source folder, her room notes prepended, that
repo's own CLAUDE.md steering it) — so the rooms page is the cockpit, and the
project brain is what the run reads and updates. A project session that
changes anything rebuilds its own page, which refreshes its handoff, which
lands here on the next sync. Nothing to remember at either end.

**Events flow up through `tell.py`.** The handoff carries open work; it
cannot carry news. When a project session learns a real-world fact the
brain tracks (an approval landed, a blocker cleared, she says a thing is
done), its CLAUDE.md tells it to run
`python3 ~/life-brain/brain/tools/tell.py "…" --from <Project>` — a
zero-token CLI that drops a pending item into `brain/queue/` for the next
run to file. Added after a project's paperwork was approved and sat unreported for
days while the daily plan kept chasing it. Items arrive marked
`source:` and "[reported by a … session]" — status facts, not her words.

A repo with no brain simply reports nothing and keeps using a top-level
`TODO.md`. Not every project earns a brain — Listo is a hackathon and the
portfolio site is an afternoon; a full ledger on either is overhead wearing
rigour's clothes.

## The Sessions page

`brain/sessions.html` (a hand-written page, not generated — safe to edit
directly) is the multi-conversation cockpit: one live, resumable Claude Code
conversation per project, several at once, driven by `brain/tools/sessions.py`
through serve.py's `/api/sessions/*` endpoints. Records live in
`brain/sessions.json`, transcripts in `brain/sessions/` — inside the brain, so
git stays the undo. Three rules it enforces:

- **One pair of hands per room.** In any one project only the conversation
  holding the hands may write files or run commands; siblings run read-only.
- **Sending never happens there.** Anything outward goes through the normal
  draft flow.
- The vocabulary: a *conversation* lives on the Sessions page; the "Quick run"
  buttons on the workstream drawer, the map panel and a room are one-shot
  `/api/agent` runs. Keep the two names distinct in any copy you write — they
  were both called "session" once and it confused everyone.

Every conversation turn resends its whole context, so a long conversation is
the most expensive thing on the page. `CONTEXT_BUDGET` caps it at 200k before
compacting, and each turn writes to the usage ledger — see
[ai-usage.md](ai-usage.md).

**Task- and person-scoped conversations ("Talk it through").** The
speech-bubble button on any open task row (Today, the plate) and the "Talk it
through" button on a person card open a chat drawer on the same page — a real
conversation in the brain's own folder, so the brain's CLAUDE.md and every
boundary in it steer each turn. `/api/sessions/new` with `kind: task|person`
builds a context pack first (`brain/tools/context.py`, mechanical, no model):
the task, its workstream block, the people.md entries it names, season lines
naming them — a page, deliberately not the whole brain, because every later
turn pays for what rides in. The pack travels inside the first turn's prompt,
marked as data rather than instructions, and never appears in the transcript.
The drawer remembers task → conversation in the browser (localStorage), so
reopening a task resumes its conversation; the same conversation appears on
the Sessions page under "The brain" with all the usual machinery — loose
ends, follow-ups, the ledger, compaction.

**Loose ends are tracked mechanically, never guessed.** A conversation can
end a turn owing something: a question she has not answered, a checklist
(Claude's own TodoWrite, captured from the event stream where a repo allows
that tool) with steps still open, a turn she stopped mid-flight, queued
messages waiting in its outbox, or follow-ups its last reply declared.
That last one is a wire format, not NLP: every turn's system prompt asks
the conversation to end with a literal `NEXT:` block when it leaves work
undone (`FOLLOWUP_SYS`), the pump parses it — with a conservative fallback
for trailing "Next steps:" headings — and the page renders each item as a
tap-to-queue suggestion. A clean reply with no block clears the old ones:
the conversation moved on. `sessions.py` records all five on the convo;
the page shows them (the checklist box, the dashed queued bubbles, the
"stopped mid-turn" line), and `python3 brain/tools/sessions.py` prints the
list — `/brief` runs it so unfinished business surfaces in the briefing.
Messages sent mid-turn queue and auto-send when the turn ends cleanly; a
question or a failure holds the queue, because firing a stale message past
an unanswered question is worse than waiting.
