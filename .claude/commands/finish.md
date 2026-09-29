---
description: A brain feature is done — check it properly, commit it, publish it to the starter
---

She says a change to the brain is finished. Built from Aug–Sep 2026, when she
asked "please double check it" seven times and "is everything pushed to the
starter?" six times: the checks and the publish belong to the work, not to
her memory.

What was built: $ARGUMENTS (or the work in this session)

## 1. It builds

- `python3 -m py_compile` every tool file this work changed.
- Rebuild the pages (`python3 brain/tools/rebuild.py`, CLAUDE.md rule 5).
  A traceback is a stop.
- `python3 brain/tools/selftest.py` must pass.
- If the work touched the revise path or writing-rules.md, run
  `python3 brain/tools/drafteval.py` and compare with the last full run.

## 2. The server runs the new code

If `serve.py`, `sessions.py` or anything they import changed, restart the
server: `curl -s http://127.0.0.1:7718/api/agent` must show
`"running": false` (never kill a run mid-flight), then kill the `serve.py`
process and relaunch with `open "Open Brain.command"`, never from this shell.
It can take up to a minute to bind.

## 3. It looks right, where she will see it

If the work changed anything on a page, open it with the browse tool:

- Load `http://127.0.0.1:7718/?bust=<timestamp>` (cache-bust every load).
- Check the changed part at phone width (`viewport 390x844`) and at desktop
  width. Put `innerWidth` in any layout probe and discard a result taken at
  the wrong width; the viewport silently resets between batches.
- Check it in the active look (config `style`), then flip
  `document.documentElement.dataset.style` to each other style for a
  preview. A clipped or odd element is usually a skin CSS rule colliding on a
  class name, not build.py.
- Fix what is broken before going on. Screenshot the changed part for her.

## 4. Commit

Other sessions edit the same files and commit with `git add -A`, so name the
paths: `git add <the files this work changed> && git commit`. Say if a
startup snapshot already swept your changes into its commit.

## 5. Publish to the starter

Only once steps 1–3 pass and she has seen the result (this command running
is her saying so). The starter repo is the one CLAUDE.md hard rule 4b names;
if it names none, skip this step and say so.

- Every tool and command ships automatically, name-scrubbed. Data folders do
  not: a tool that reads a new data folder must cope with it missing, or the
  folder needs its empty format guide under `brain/tools/share-templates/`.
  Her own data (cases, drafts, people) never ships.
- `python3 brain/tools/share.py --yes && git --git-dir=dist/life-brain/.git --work-tree=dist/life-brain push --force <starter repo URL> blair:blair`.
  Gate on the exit code only; never read success out of the output.
- Never `git -C dist/life-brain push`. dist/ sits inside her own repo, so when
  the package has no history of its own (a refused or half-finished build),
  `-C` climbs to her repo and force-pushes her whole life to the public
  starter. The `--git-dir` form fails instead. share.py also refuses to
  finish unless the package's git top level is the package folder itself.
- Before that push, grep the built package for place and project names from
  this work: share.py's scan catches people and known words, not new ones.

## 6. Report

Two lines: what was checked (and anything you fixed on the way), and whether
it is published, with the starter commit.
