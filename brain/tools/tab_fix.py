"""Under the hood: Fix and improve (8 Oct 2026).

The page's doors to what used to need a Claude Code chat: check the brain
when something is wrong, ask Claude to change how it works, take a change
back, and pack your improvements for whoever shared the brain with you. The
work happens in fix.py and the box; this file only draws the section.
"""
import agents as AG
import fix
from build import e


def section():
    hist = fix.history()
    rows = "".join(
        '<li class="fixh">'
        f'<span class="fixwhat">{e(h["what"])}'
        f'<i>{e(h["when"])} &middot; {e(h["nfiles"])}, {e(h["where"])}</i></span>'
        + (f'<button class="mini needs-server" data-fixundo="{e(h["sha"][:12])}"'
           f' data-fixwhat="{e(h["what"])}">Undo</button>'
           if h["undoable"] else "")
        + "</li>"
        for h in hist)
    changes = (
        '<details class="hoodfold"><summary>Recent changes'
        f' <span class="agn">{len(hist)}</span></summary>'
        '<p class="fixnote">Undo takes one back and keeps a record, so an '
        'undo can be undone too.</p>'
        f'<ul class="fixlist">{rows}</ul>'
        '<span class="mshelp" id="fixundo-said"></span></details>'
        if hist else "")
    return (
        '<section id="fix" class="hoodsec"><h3 class="area">Fix and improve</h3>'
        '<div class="fixrow">'
        '<button class="mini needs-server" id="fixcheck">Something&rsquo;s '
        'wrong?</button>'
        f'<span class="fixsub">The brain checks itself, then {AG.short()} looks for '
        'the cause with you.</span>'
        '<span class="mshelp" id="fixcheck-said"></span></div>'
        '<div class="fixrow">'
        '<button class="mini needs-server" data-box data-box-fresh '
        'data-box-text="Change how the brain works: ">Change how it works'
        '</button>'
        f'<span class="fixsub">Say what should be different; {AG.short()} changes '
        'the brain when you press Run.</span></div>'
        + changes +
        '<div class="fixrow">'
        '<input id="fixnote" class="fixin" autocomplete="off" '
        'placeholder="What your change does, and why">'
        '<button class="mini needs-server" id="fixshare">Pack my changes'
        '</button>'
        '<span class="fixsub">One file with your changes to the brain&rsquo;s '
        'code, never your notes, for whoever shared the brain with you. '
        'Sending it is up to you.</span>'
        '<span class="mshelp" id="fixshare-said"></span></div>'
        "</section>")
