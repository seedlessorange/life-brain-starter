---
description: Turn a recording into a transcript she can find, then file what was said
---

She has a recording (a voice note, a class, a meeting, a call) and wants it
transcribed. Built from three such asks in Sep 2026, one of which ended with
"the brain doesn't seem to be able to find it": the transcript has to land
where she will look, and what was said has to reach the brain.

What she said: $ARGUMENTS

## 1. Find the recording

- She named a file: use it.
- She said "the latest" or named nothing:
  `python3 brain/tools/transcribe.py --list` (voice notes in her recording
  folders) and `python3 brain/tools/transcribe.py --meetings` (meeting
  recordings in project folders). Pick the newest without a transcript and
  say which one you took.

For a voice note, pass `--language fr` or `en` from what she said or the
recording's context, and put names and jargon the model should expect in
`--prompt`. Meeting mode needs neither: it detects the language stretch by
stretch, so a meeting that switches between French and English stays intact.

## 2. Transcribe, locally

- **A meeting that belongs to a project** (it sits in a project's recordings
  folder, or she says it is a project meeting):
  `python3 brain/tools/transcribe.py --meeting "<path>"`.
  The transcript is written beside the recording as `<name> - Transcript.md`,
  in the project folder her team opens. This is the one kind of file the
  brain may create outside itself (CLAUDE.md hard rule 3), and it never
  touches anything already there.
- **Anything else** (a voice note, a class, a call):
  `python3 brain/tools/transcribe.py "<path>" --language <xx> --room <room>`,
  which files it under `brain/transcripts/`.

Long recordings take minutes: run it under `caffeinate -ims`, in the
background, and tell her it is running. Transcription is local (Whisper on
the Mac), so it costs no model call.

## 3. File what was said

Read the transcript once, then:

- **Minutes**, for a meeting: a short dated summary of decisions, owners and
  dates, saved beside the transcript for a project meeting or under the
  workstream's notes otherwise. If the team needs a Word copy, use
  `python3 brain/tools/todocx.py`.
- **Decisions** go to `brain/decisions.md` (append-only).
- **Tasks** with an owner and a date go to the right workstream, with a real
  `(due YYYY-MM-DD)`; promises she made to someone go on that person.
- **People:** everyone who spoke or was discussed gets a `Last` date via
  `python3 brain/tools/people_update.py "Name=YYYY-MM-DD"`. Distrust
  transcribed spellings; match against people.md names and `Also:` aliases.
  Someone new becomes a question, never an automatic entry.
- **Confidential:** if the recording is marked NDA or confidential in its
  name, or something said in it is flagged as under NDA, keep the transcript
  where it is and file only tasks and dates, no content.

## 4. Tell her where it is

One line with the transcript's path and what you filed ("3 tasks on the
project, 2 decisions, Last dates for two people"). Rebuild the pages
(CLAUDE.md rule 5).

## Twice a day, without her

The server also runs this on its own at 12:30 and 19:30 (config
`recordings_auto`). It finds new recordings in Voice Memos and Downloads
made since `since`, at least a minute long, finished (untouched for five
minutes), and not named confidential. It transcribes them locally, letting
Whisper detect the language, and queues each one: a note under 25 minutes
as a dump, a longer one as a meeting. Then it starts the queue run if the
Usage page's "Recordings" switch is on; otherwise the asks wait for the
night run. Its last pass is in `brain/.recordings-auto.json`. Voice Memos'
folder needs Full Disk Access for Terminal, which is what launches the
server. Without it, that folder shows up as `blocked` there.
