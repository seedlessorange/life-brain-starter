"""Minimal Markdown -> HTML renderer for the brain pages.

Deliberately small and dependency-free — it covers exactly what this brain's
markdown uses: frontmatter, headings, tables, lists, task lists, blockquotes,
rules, and inline emphasis/code/links/strike. Nothing to install, ever.

If you find yourself wanting markdown syntax it doesn't cover, extend this
rather than working around it in the page.
"""

import hashlib
import html
import re

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)([^\*]+?)(?<!\s)\*(?!\*)")
STRIKE = re.compile(r"~~(.+?)~~", re.S)
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
# Not anchored to end-of-line, and identical to model.py's — suffixes arrive
# in any order, and the two parsers drifting apart breaks every tick hash.
UNTIL = re.compile(r"\s*\(waiting until (\d{4}-\d{2}-\d{2})\)")
DROPPED = re.compile(r"\s*\(dropped (\d{4}-\d{2}-\d{2})\)")
# The evening check's deliberate roll-forward — state, not part of the words.
CARRYING = re.compile(r"\s*\(carrying (\d{4}-\d{2}-\d{2})\)")
# A rough time estimate on a task: ~30m, ~2h, ~1h30.
EST = re.compile(r"\s*~\s*(\d+h\d*m?|\d+m)\b", re.I)


def bare(text):
    """A task's own words, with every suffix the page or the parser added
    taken off: state markers, the ~time estimate, and a (due …) that really
    parses as a deadline.

    THIS IS THE HASH INPUT FOR taskkey. Every place that computes a key must
    strip identically or the key drifts and the action lands on "that item has
    changed" — so there is one definition and serve.py, the renderer and the
    evening check all call it. It used to live only in serve.py, which meant
    the page's own key included a `~30m` the server had already stripped, and
    adding an estimate to a task silently broke its tickbox.
    """
    from model import parse_due          # late: keeps md.py import-light
    text = UNTIL.sub("", text)
    text = re.sub(r"\s*\((?:due|by) ([^)]+)\)",
                  lambda m: "" if parse_due(m.group(1)) else m.group(0), text)
    # Season suffixes are state too: a chip dragged to another day rewrites
    # (planned: …), and the tick hash must not move with it. Mirrors
    # model.py's WITH/WHEN/PLANNED, including the only-if-it-parses rule.
    text = re.sub(r"\s*\((?:when|planned): ([^)]+)\)",
                  lambda m: "" if parse_due(m.group(1)) else m.group(0), text)
    text = re.sub(r"\s*\(with: [^)]+\)", "", text)
    text = re.sub(r"\s*\(fits: [^)]+\)", "", text)
    text = re.sub(r"\s*\(repeat: (?:weekly|fortnightly|monthly)\)", "", text,
                  flags=re.I)
    text = re.sub(r"\s*\(did: \d{4}-\d{2}-\d{2}(?: \d{4}-\d{2}-\d{2})*\)",
                  "", text)
    text = EST.sub("", text)
    text = re.sub(r"\s*\(urgent\)", "", text, flags=re.I)
    text = CARRYING.sub("", text)
    return DROPPED.sub("", text).strip()

# Status words that get a coloured chip when they are a whole table cell.
STATUS = {
    "moving": "ok", "done": "ok",
    "waiting": "wait", "blocked": "bad", "stalled": "bad",
    "not started": "unk", "parked": "unk", "dropped": "unk",
    "me": "mine", "them": "wait", "nobody": "unk",
}


def split_frontmatter(text):
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end():]


def inline(s):
    """Escape, then apply inline markup. Code spans are protected first, so
    backticked text never has its asterisks eaten."""
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = INLINE_CODE.sub(stash, s)
    s = html.escape(s, quote=False)
    s = STRIKE.sub(r"<del>\1</del>", s)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    s = ITALIC.sub(r"<em>\1</em>", s)
    s = LINK.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', s)
    s = re.sub(r"\x00(\d+)\x00",
               lambda m: f"<code>{html.escape(codes[int(m.group(1))])}</code>", s)
    return s


def taskkey(text):
    """A stable id for a checklist item: a hash of its own words.

    Deliberately not the line number. Items get inserted and reordered all the
    time, and a tick landing on the wrong item is worse than one that fails to
    land. Hashed from the item's first line only, because that is the line a
    file writer will actually find.
    """
    return hashlib.sha1(plain(text).encode("utf-8")).hexdigest()[:12]


def plain(s):
    """Markdown to bare text — what a person would read aloud."""
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\*\*|\*|`|~~", "", s)
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s).strip()


def _cells(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def _chip(cell):
    """Turn a bare status word in a table cell into a coloured chip."""
    key = STATUS.get(re.sub(r"<[^>]+>", "", cell).strip().lower().rstrip("."))
    if key:
        return f'<span class="v v-{key}">{re.sub(chr(60) + "[^>]+" + chr(62), "", cell).strip()}</span>'
    return cell


def render(text, task_source=None, heading_id=None, ws_lookup=None):
    """Render markdown to an HTML fragment.

    `task_source` makes `- [ ]` checkboxes clickable, writing back to that
    filename through the local server. Without it they render as static boxes,
    which is the right degradation when the page is opened as a plain file.

    `ws_lookup`, when given, maps a task's bare text to its (workstream,
    short label) so a lifted-out task can say which project it belongs to —
    "Write up the 18 August meeting" means little without knowing whose
    meeting. Open tasks only; a done row has stopped needing its context.
    """
    _, body = split_frontmatter(text)
    lines = body.split("\n")
    out, i, n = [], 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            hid = heading_id(txt) if heading_id else ""
            idattr = f' id="{hid}"' if hid else ""
            out.append(f"<h{lvl}{idattr}>{inline(txt)}</h{lvl}>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = _cells(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            out.append('<div class="tw"><table><thead><tr>')
            out.extend(f"<th>{inline(h)}</th>" for h in head)
            out.append("</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>")
                out.extend(f"<td>{_chip(inline(c))}</td>" for c in r)
                out.append("</tr>")
            out.append("</tbody></table></div>")
            continue

        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue

        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            items, cls = [], ""
            while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                item = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i])
                first = item
                i += 1
                while (i < n and lines[i].strip()
                       and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i])
                       and not lines[i].strip().startswith(("#", "|", ">"))
                       and not re.fullmatch(r"-{3,}", lines[i].strip())):
                    item += " " + lines[i].strip()
                    i += 1
                task = re.match(r"^\[([ xX])\]\s*(.*)", item)
                if task:
                    cls = ' class="tasks"'
                    done = task.group(1).lower() == "x"
                    body = task.group(2)
                    # Same state suffixes the workstream cards use, so a task
                    # looks and behaves identically wherever it is rendered.
                    m_until = UNTIL.search(body)
                    m_drop = DROPPED.search(body)
                    m_carry = CARRYING.search(body)
                    m_est = EST.search(body)
                    shown = UNTIL.sub("", DROPPED.sub("", CARRYING.sub("", body)))
                    shown = re.sub(r"\s*\(urgent\)", "", shown, flags=re.I)
                    shown = EST.sub("", shown)
                    # How long it takes, shown where the eye already is. Without
                    # this the plan could not answer "I have twenty minutes —
                    # what fits?", which is most of what a plan is for.
                    est = (f'<span class="test">{html.escape(m_est.group(1))}</span>'
                           if m_est and not done else "")
                    note = ""
                    if m_drop:
                        note = '<span class="tnote">dropped</span>'
                    elif m_until:
                        note = f'<span class="tnote">waiting until {m_until.group(1)}</span>'
                    elif m_carry:
                        note = '<span class="tnote">carrying to tomorrow</span>'
                    chip, wsname = "", ""
                    if task_source and ws_lookup and not done:
                        hit = ws_lookup(plain(shown))
                        if hit:
                            wsname = hit[0]
                            chip = ('<button class="tws" data-wsopen="'
                                    + html.escape(wsname, quote=True)
                                    + '" title="' + html.escape(wsname, quote=True)
                                    + ' &mdash; open the project">'
                                    + html.escape(hit[1] or wsname) + "</button>")
                    if task_source:
                        raw_first = re.match(r"^\[[ xX]\]\s*(.*)", first).group(1)
                        key = taskkey(bare(raw_first))
                        box = ('<button class="box tick" aria-pressed="'
                               + ("true" if done else "false")
                               + f'" data-src="{task_source}" data-key="{key}"'
                               + ' title="Tick it off">'
                               + ("&#10003;" if done else "") + "</button>")
                        menu = ""
                        # The assistant's hand on every open task: one tap and
                        # Claude does the legwork (research, numbers, drafts) —
                        # never the booking, paying or sending.
                        if not done and not m_until and not m_drop:
                            menu += ('<button class="tstart needs-server"'
                                     ' data-claudestart="'
                                     + html.escape(shown.strip(), quote=True)
                                     + '" title="Claude starts this now: options '
                                     'researched, numbers found, drafts written. '
                                     'It never sends anything."'
                                     ' aria-label="Have Claude start this">&#10022;</button>')
                        menu += (f'<button class="tmenu needs-server" data-task="{key}"'
                                 f' data-src="{task_source}"'
                                 + (f' data-ws="{html.escape(wsname, quote=True)}"'
                                    if wsname else "")
                                 + ' aria-label="More ways to close this">&#8943;</button>')
                    else:
                        box = ('<span class="box done">&#10003;</span>' if done
                               else '<span class="box"></span>')
                        menu = ""
                    rowcls = " ".join(filter(None, [
                        "done" if done else "",
                        "parked" if m_until else "",
                        "dropped" if m_drop else ""]))
                    items.append(f'<li class="{rowcls}">{box}'
                                 f'<span class="ttext">{inline(shown)}{est}{note}</span>'
                                 f"{chip}{menu}</li>")
                else:
                    items.append(f"<li>{inline(item)}</li>")
            out.append(f"<{tag}{cls}>" + "".join(items) + f"</{tag}>")
            continue

        buf = [stripped]
        i += 1
        while (i < n and lines[i].strip()
               and not re.match(r"^\s*(#{1,6}\s|[-*+]\s|\d+\.\s|\||>)", lines[i])
               and not re.fullmatch(r"-{3,}", lines[i].strip())):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")

    return "\n".join(out)
