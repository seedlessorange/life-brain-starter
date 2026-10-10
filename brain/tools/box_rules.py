"""What the box and the voice tell Claude about reading her words.

Since 7 Oct (the fewer-doors plan) the box has no modes to pick: she says
what she wants and Claude works out which kind of thing it is. These are the
words that make that work, kept in one place so the typed box (chrome.py),
a spoken update (serve.py's VOICE_UPDATE) and a conversation in the brain's
own folder (sessions.py) can never drift apart.

Before this, the instruction to tick and file lived only behind the "Tick
off what happened" mode, so the box's default conversation never ticked
anything unless she picked a mode first; across 468 conversations the modes
were picked three times.
"""

# The daily-update rule: what "reconcile" means. Said in front of her words
# by the update intent (a button that sends it for her) and by voice.
RECONCILE = (
    "Daily update. Reconcile, do not just file: anything I say is DONE gets "
    "ticked in the workstream it lives in (and Touched stamped); new "
    "priorities re-rank next.md; corrections update the source files; "
    "genuinely new items get filed where they belong. Only ask if something "
    "truly cannot be placed. ")

# The standing note for a conversation in the brain's own folder: how to read
# a message that carries no instruction of its own. A project folder's
# conversation never gets it (it cannot write the brain's files).
READ_HER = (
    "(Note from the brain, for you only: she no longer picks a mode before "
    "she writes, so read what she means and do that. Something she says is "
    "done gets ticked where it lives, with Touched stamped; someone she says "
    "she spoke to gets their Last date; a correction fixes the file it lives "
    "in; anything new gets filed where it belongs, a task as a line that "
    "reads on its own a week later (a verb, the thing it is about, no codes "
    "or labels like \"M4\" or \"Gate:\"). A request for a message, "
    "email or post is a draft: load brain/writing-rules.md first, save it in "
    "brain/drafts/ in the draft format, show the text here, and never send "
    "it. \"Tear this apart\" or a request for a critique gets "
    ".claude/commands/critic.md in full, without rewriting her work. A "
    "business or strategy question gets .claude/commands/consult.md. A long "
    "run of unrelated thoughts is a brain dump: sort all of it with the rules "
    "in .claude/commands/dump.md and lose nothing. When she asks only for an "
    "answer, or says not to change anything, change nothing. If a line could "
    "fairly mean two different things, ask with CHOICES instead of guessing. "
    "End by saying in one plain line what you changed, if anything.)")
