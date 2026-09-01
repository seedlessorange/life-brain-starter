---
description: Read inbox screenshots and update who the owner has actually spoken to
---

The owner has attached one or more screenshots of a messaging app's chat list
(WhatsApp, Instagram, Messenger, iMessage). Read them and update `people.md`
so they never have to log a conversation by hand.

This exists because there is no legitimate API that can read someone's
personal chats: WhatsApp has none and the unofficial libraries get numbers
permanently banned; Instagram's personal-account access ended in December
2024. A screenshot of the owner's own screen has no such problem, and a chat
list happens to show precisely the two things this system needs.

## What to read, and what to ignore

From each row in the list, take **only**:

- the **contact or group name**
- the **recency stamp** — `14:32`, `Yesterday`, `Monday`, `08/03/2026`

**Ignore the message previews completely.** Do not quote them, summarise them,
repeat them back, or store them anywhere. They are not what this is for. If a
preview reveals something that clearly needs action ("can you send the
documents"), you may mention that one thing in your report without quoting it
— but never write it into a file.

## Turning stamps into dates

- A time (`14:32`) means **today**.
- `Yesterday` means yesterday.
- A weekday name (`Monday`) means the most recent past occurrence of it.
- A date means itself. Check `about-me.md` for which day/month order the
  owner's apps use before reading an ambiguous one.
- If a row is unreadable, skip it and say so. **Never guess a date.**

## Then

1. **Write with the script, never by hand:**

   ```
   python3 brain/tools/people_update.py "Mum=today" "Ellis=2026-08-09" ...
   ```

   It refuses to move a date backwards, so running this on an old screenshot
   is safe. It also reports anyone who is not on the owner's people list.

2. **Ask about newcomers, do not add them silently.** A chat list contains
   plumbers, group chats and delivery notifications. Name the handful that
   look like real relationships and ask which the owner wants tracked.
   Adding everyone would turn a considered list into a contact dump, which
   is the one thing `people.md` is not.

3. **Rebuild** with `python3 brain/tools/build.py`.

4. **Report in the owner's language**: how many people you updated, who has
   now gone quiet past the rhythm they set, and who owes who. If someone
   marked `Focus: yes` is drifting, say so plainly — that is the whole point
   of the flag.

5. **Do not delete the screenshots.** They are the owner's; they live in
   `brain/files/`. Mention that they can clear that folder whenever they
   like.

## Rules

- **A screenshot is evidence of contact, not of a reply owed.** Seeing a name
  in the list tells you when you last spoke, not whose turn it is. Only
  change `Ball` if the owner says so, or if the list plainly shows the last
  message was incoming AND they ask you to infer it.
- Never write message content, phone numbers, or profile pictures into any
  file in this brain.
- If the attachment is not a chat list, say so rather than inventing rows.
