---
description: Scan the computer for project folders and propose which ones the brain should follow
---

Find the projects the owner is actually working in, and propose changes to
what the brain follows. People move between many folders and the brain only
knows the ones in `config.json`.

## Procedure

1. **Run the free scan first** — it costs nothing and does the whole search:

   ```
   python3 brain/tools/discover.py
   ```

   It lists every project folder under the home directory, ranked by when it
   was last genuinely touched (git commits and file edits, ignoring build
   output), and marks which ones the brain already follows.

2. **Look inside the untracked active ones** before proposing anything. A
   folder name is not enough to know what something is. Read its README,
   CLAUDE.md or package.json and say in one plain sentence what it appears
   to be. If you genuinely cannot tell, say so rather than inventing a
   description.

3. **Propose, in the owner's language.** Three groups:

   - **Add these** — active, untracked, and clearly theirs. Say what each
     one is and why it is worth following.
   - **Probably not** — active but not really a project (a clone of someone
     else's repo, a course exercise, a scratch folder). Name them so the
     owner can overrule you.
   - **Park or drop these** — folders the brain follows that have been quiet
     for months. Untracked-and-quiet needs no action; *tracked* and quiet is
     clutter in the briefing every day.

4. **Ask before editing `config.json`.** This is one of the few places where
   guessing is expensive: a wrong entry means a folder the owner does not
   care about shows up in the briefing forever, and a missing one means real
   work stays invisible. Show the list, let them pick.

5. **When the owner has chosen**, edit `brain/config.json`'s `sources`
   array. Use `~/` paths, not absolute ones. Add a `files` list only when
   the default scan misses the checklist file that matters (the default
   already looks for TODO.md, TODOS.md, TASKS.md, NEXT.md, README.md,
   CLAUDE.md, notes.md).

6. **Then sync and rebuild:**

   ```
   python3 brain/tools/sync.py
   python3 brain/tools/build.py
   ```

7. **Consider whether any of them deserve a workstream.** A folder in
   `sources` shows its open items on the page, which is not the same as
   being tracked as work with a next action and a ball. If something the
   owner adds is genuinely live work, propose the workstream too — but do
   not create one per folder by reflex.

## Rules

- **Reading a folder is free; adding it is not.** Every source makes the
  briefing longer. Prefer fewer, real ones.
- **Never add a folder outside the home directory**, and never add one that
  belongs to someone else's account.
- If a scan turns up something that looks like coursework with a deadline,
  say so — that is a workstream with a `Due:` date, not just a folder.
