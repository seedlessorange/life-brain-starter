"""Two For you lines the learning loop adds (smarter-brain plan, items 11-13).

- One Confirm line per open lesson from the weekly lesson tray (lessons.py):
  the lesson is the line; Keep or Bin inside, the evidence one fold down.
- One Send line when the profile block she pastes into claude.ai and
  ChatGPT (evals/jarvis.json) has changed since she last pasted it: Copy for
  each, then Pasted. Nothing shows when the file is missing.

build() calls render() just before it prints For you. The page helpers come
from build.py, so run the page with build.py.
"""

import agents as AG
import json
import os

from build import BRAIN, _tid, e, tray_item


def _dm(iso):
    """"2026-10-07" -> "7 Oct"."""
    from datetime import date
    try:
        d = date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{d.day} {d:%b}"


def lesson_items():
    try:
        import lessons as LS
        st = LS.load()
        pend = LS.open_lessons(st)
    except Exception:                                    # noqa: BLE001
        return []
    out = []
    for l in pend:
        lid = e(l.get("id"))
        why = l.get("why") or ""
        body = ('<div class="mttray lstray needs-server">'
                '<div class="mtrow lsrow"><span class="mttask">'
                "Keep this lesson?"
                f'<i title="{e(why)}">for {e(LS.target_words(l.get("target", "")))}'
                f' &middot; {e(_dm(l.get("proposed")))}</i></span>'
                f'<button class="mini" data-lsact="keep" data-lsid="{lid}"'
                f' title="{AG.short()} files it where it belongs on the next queue run">'
                "Keep</button>"
                f'<button class="mini" data-lsact="bin" data-lsid="{lid}"'
                ' title="Never proposed again">Bin</button></div>'
                '<details class="ghost lsev"><summary>What it is based on</summary>'
                f'<p>{e(l.get("evidence"))}</p>'
                + (f"<p>{e(why)}</p>" if why else "")
                + '</details><span class="mshelp lshelp"></span></div>')
        # The whole lesson is the line (lessons.py caps it at 300
        # characters): cut short, the rule she is asked to keep is unread.
        # Where it goes is the faint line inside, said once.
        out.append(tray_item(_tid("lesson", l.get("id")), "confirm",
                             l.get("lesson") or "", body))
    return out


def jarvis_item():
    try:
        with open(os.path.join(BRAIN, "evals", "jarvis.json"),
                  encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(j, dict) or not j.get("sha") or not j.get("claude") \
            or j.get("sha") == j.get("pasted_sha"):
        return None
    when = _dm(j.get("generated"))
    gpt = j.get("chatgpt") or ""
    body = ('<div class="mttray jvtray needs-server">'
            '<div class="mtrow jvrow"><span class="mttask">'
            "Paste each into that app&rsquo;s settings"
            + (f"<i>changed {e(when)}</i>" if when else "") + "</span>"
            '<span class="jvacts">'
            '<button class="mini" data-jvcopy="claude">Copy for Claude</button>'
            + ('<button class="mini" data-jvcopy="chatgpt">Copy for ChatGPT</button>'
               if gpt else "")
            + f'<button class="mini" data-jvpasted="{e(j["sha"])}">Pasted</button>'
            "</span></div>"
            f'<textarea class="jvtext" id="jv-claude" hidden readonly>{e(j["claude"])}</textarea>'
            + (f'<textarea class="jvtext" id="jv-chatgpt" hidden readonly>{e(gpt)}</textarea>'
               if gpt else "")
            + '<details class="ghost lsev"><summary>See the text</summary>'
            f'<pre class="jvshow">{e(j["claude"])}</pre></details>'
            '<span class="mshelp jvhelp"></span></div>')
    return tray_item("jarvis", "send", "Update your Claude profile", body)


def render(tray_send, tray_confirm):
    """Adds its lines in place. Never raises: For you must print."""
    try:
        tray_confirm.extend(lesson_items())
    except Exception:                                    # noqa: BLE001
        pass
    try:
        it = jarvis_item()
        if it:
            tray_send.append(it)
    except Exception:                                    # noqa: BLE001
        pass
