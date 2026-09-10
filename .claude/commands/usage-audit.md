# /usage-audit — where the Claude usage goes, and how to spend less

You are auditing how the owner and this brain USE Claude — run shapes, ask
habits, model choices — not the brain's content. The output is one file,
`brain/usage-audit.md`, which the Usage page renders.

## What to read (this order, nothing more)

1. `python3 brain/tools/usage.py --json --days 30` — the ledger: every model
   call with tokens, model, turns, seconds, labels.
2. `brain/.agent-runs.json` — the last 20 page runs: their summaries and
   logs. The log lines show each run's tool steps, so you can see what a run
   actually did with its turns.
3. The three NEWEST files in `brain/sessions/` — her conversations: how she
   asks, how many follow-ups a question took, whether Claude had to ask back.
4. Only if one run deserves a deeper look: ONE transcript from this
   folder's directory under `~/.claude/projects/` (the entry whose name
   ends `-life-brain`; take the largest recent `.jsonl`). They are big — never read more than one, and read it with
   `tail`/`grep`, not whole.

Do NOT read people.md, workstreams.md, drafts or the rest of the brain. This
audit is about usage patterns; the life content is out of scope and reading
it just spends what the audit is trying to save.

## What to look for

From the ledger (numbers):
- Where the tokens and model-minutes actually went — by job, by model. Note
  that cache reads are cheap; fresh input + output tokens are the real cost.
- Run shape: several small runs in a day where one batched run would have
  done; turns per run creeping up.
- Model fit: Sonnet runs whose work was mechanical (Haiku-shaped), or Haiku
  runs that visibly struggled (errors, retries in the log).

From transcripts and run logs (habits):
- Asks that took clarification rounds — where one more sentence upfront
  (what, where, what "done" looks like) would have saved a whole round trip.
- Re-explained context: things told to Claude that the brain already knows,
  or the same background pasted twice in a week.
- Tool churn inside runs: reading a big file where a summary command exists,
  repeated rebuilds, steps that produced nothing the run used.
- Full-brain questions that the Ask panel's file chips would have scoped.

## The report — brain/usage-audit.md

Overwrite the file. Under 60 lines. Exactly this shape:

```
---
updated: YYYY-MM-DD
---
## Where it went (last 30 days)
Three to six lines telling the ledger's story in plain words.

## What I noticed
Three to five findings. Each: the pattern, one concrete example (a run named
by its button name and day, or a quote of how something was asked), and
roughly what it cost.

## Try this
Three to five suggestions, ranked by payoff, one or two sentences each with
the why. A suggestion must never remove functionality — cheaper routes to
the same result only. If a habit is already good, say so once; no padding.
```

Plain language, numbers rounded, no jargon, no file paths in prose (call
runs by their button names — "Work the queue", "the 7am plan"). No
reassurance triads.

## Boundaries

- Write only `brain/usage-audit.md`; everything else is read-only.
- Quotes from her conversations exist to show HOW something was asked: keep
  them under 15 words and skip anything personal or sensitive — this report
  can be on screen when the brain is shared.
- Suggestions about HER habits are written to her, kindly and directly
  ("front-load the goal and the deadline and you save the follow-up turn"),
  never about her.

## After writing

Rebuild the pages:

```
python3 brain/tools/build.py
python3 brain/tools/map.py
python3 brain/tools/rooms.py
python3 brain/tools/proto.py
```

End with one line: the single biggest saving you found.
