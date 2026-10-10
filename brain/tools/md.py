"""Minimal Markdown -> HTML renderer for the brain pages.

Deliberately small and dependency-free — it covers exactly what this brain's
markdown uses: frontmatter, headings, tables, lists, task lists, blockquotes,
rules, and inline emphasis/code/links/strike. Nothing to install, ever.

If you find yourself wanting markdown syntax it doesn't cover, extend this
rather than working around it in the page.
"""

import hashlib
import html
import json
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
# A plan task's short version: what still counts when the day goes sideways.
SHORT = re.compile(r"\s*\(short:\s*([^)]*)\)", re.I)
# A plan task's moment: a clock time and the thing she will meet at it —
# `(at 12:30, after Strategy)`. An if-then plan (Gollwitzer & Sheeran 2006);
# the cue is an event, never a scene to picture (aphantasia). The clock time
# is required so "(at the bank)" in her own words is never read as one.
AT = re.compile(r"\s*\(at\s+(\d{1,2}[:h]\d{2})(?:\s*,\s*([^)]*))?\)", re.I)


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
    # First, so a ~ inside the short version never reads as the estimate.
    text = SHORT.sub("", text)
    text = AT.sub("", text)
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
    text = re.sub(r"\s*\(ends: \d{4}-\d{2}-\d{2}\)", "", text)
    text = re.sub(r"\s*\(repeat: (?:weekly|fortnightly|monthly)\)", "", text,
                  flags=re.I)
    text = re.sub(r"\s*\(did: \d{4}-\d{2}-\d{2}(?: \d{4}-\d{2}-\d{2})*\)",
                  "", text)
    text = EST.sub("", text)
    text = re.sub(r"\s*\(urgent\)", "", text, flags=re.I)
    text = CARRYING.sub("", text)
    # Collapse the gaps a removed suffix leaves behind. model.py strips the
    # same suffixes without their leading space, so a task that carries a
    # note AFTER its "(due …) ~20m" ended up with two spaces on one side and
    # one on the other — two different keys for one line, and every tick on
    # it refused with "that item has changed" (found 18 Sep).
    text = re.sub(r"[ \t]{2,}", " ", DROPPED.sub("", text))
    return text.strip()

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


# The only kinds of address a rendered link may carry. The text behind a
# link is often someone else's (a feed, a scouted event, tester feedback in
# a room note), and a javascript: link would run with the page's access to
# the local server. Anchors and relative paths have no scheme and pass.
SAFE_SCHEMES = ("http", "https", "mailto", "tel")
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")


def safe_href(url):
    """The URL as the browser will read it, or "" when it is not safe to
    link. Browsers drop tabs and newlines anywhere in a URL and skip leading
    spaces and control characters, so " JaVa\\tScript:" must be caught as
    javascript: — the check runs on the URL in that same cleaned form."""
    s = re.sub(r"[\t\n\r]", "", url or "")
    s = re.sub(r"^[\x00-\x20]+", "", s)
    m = _SCHEME.match(s)
    if m and m.group(1).lower() not in SAFE_SCHEMES:
        return ""
    return s


def json_for_script(obj, **kw):
    """json.dumps for data inlined in a <script>. A name or task containing
    "</script>" would otherwise end the script and start markup of its own;
    the \\u escapes read back as the same characters in JavaScript and JSON.
    U+2028/2029 are line breaks to older JavaScript engines."""
    return (json.dumps(obj, **kw)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _link(m):
    # m.group(2) arrives HTML-escaped by inline(); unescape once so the check
    # and the attribute both see the address the browser will follow.
    url = safe_href(html.unescape(m.group(2)))
    if not url:
        return m.group(1)
    return f'<a href="{html.escape(url, quote=True)}">{m.group(1)}</a>'


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
    s = LINK.sub(_link, s)
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



def row_buttons(text, key, src, ws="", open_=True):
    """A task row's buttons after the tickbox, in one place since 7 Oct (the
    fewer-doors plan). The plan rows drawn here and the front rows drawn by
    build.py's taskrow kept their own copies, and the copies drifted: one
    grew a speech bubble the other never had. ✦ hands the task to Claude in
    the box (talk it through, or Start it for me); ⋯ holds dates, rewording
    and dropping. A finished, parked or dropped task gets only ⋯."""
    q = lambda v: html.escape(v, quote=True)  # noqa: E731
    out = ""
    if open_:
        import agents as AG     # fixed wording: the agent the runs use
        out += ('<button class="tstart needs-server" data-claudestart="'
                + q(text) + '"' + (f' data-claudews="{q(ws)}"' if ws else "")
                + AG.say(' title="Hand it to Claude: talk it through, or have it start'
                         ' the legwork. It never sends anything."'
                         ' aria-label="Hand this task to Claude">&#10022;</button>'))
    out += (f'<button class="tmenu needs-server" data-task="{key}" data-src="{src}"'
            + (f' data-ws="{q(ws)}"' if ws else "")
            + ' title="Dates, rewording, dropping"'
            ' aria-label="More for this task">&#8943;</button>')
    return out

def render(text, task_source=None, heading_id=None, ws_lookup=None,
           row_extra=None):
    """Render markdown to an HTML fragment.

    `task_source` makes `- [ ]` checkboxes clickable, writing back to that
    filename through the local server. Without it they render as static boxes,
    which is the right degradation when the page is opened as a plain file.

    `ws_lookup`, when given, maps a task's bare text to its (workstream,
    short label) so a lifted-out task can say which project it belongs to —
    "Write up the 18 August meeting" means little without knowing whose
    meeting. Open tasks only; a done row has stopped needing its context.

    `row_extra`, when given, takes an open task's bare text and returns HTML
    to add under it (a reading's speed-read button, from build.py).
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
            # A numbered list with blank lines between items arrives here one
            # item at a time; its own number keeps it from reading 1, 1, 1.
            num = int(re.match(r"^\s*(\d+)", line).group(1)) if ordered else 1
            items, cls = [], ""
            base_ind = len(lines[i]) - len(lines[i].lstrip())
            while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                ind = len(lines[i]) - len(lines[i].lstrip())
                if ind > base_ind and items:
                    # Bullets indented under an item belong to it: the plan's
                    # "The Friday hour" carries three steps, and drawn as
                    # siblings they turned "Do these three" into six cards
                    # (9 Oct). They render as a list inside their parent.
                    sub = []
                    while (i < n and lines[i].strip()
                           and len(lines[i]) - len(lines[i].lstrip()) > base_ind):
                        sub.append(lines[i][base_ind:])
                        i += 1
                    k = min(len(x) - len(x.lstrip()) for x in sub)
                    inner = render("\n".join(x[k:] for x in sub),
                                   task_source=task_source)
                    inner = inner.replace("<ul", '<ul data-sub="1"', 1) \
                        .replace("<ol", '<ol data-sub="1"', 1)
                    items[-1] = (items[-1][:-len("</li>")]
                                 + f'<div class="subitems">{inner}</div></li>')
                    continue
                bullet = re.match(r"^\s*([-*+]|\d+\.)", lines[i]).group(1)
                item = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i])
                first = item
                i += 1
                while (i < n and lines[i].strip()
                       and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i])
                       and not lines[i].strip().startswith(("#", "|", ">"))
                       and not re.fullmatch(r"-{3,}", lines[i].strip())):
                    item += " " + lines[i].strip()
                    i += 1
                # Only the shape serve.task_action can find again ("- [ ] x"
                # or "* [ ] x"): a box drawn for "1. [ ] x" or "- [ ]x" was
                # refused on every tap (9 Oct audit).
                task = (re.match(r"^\[([ xX])\]\s+(.*)", item)
                        if bullet in ("-", "*") else None)
                if task:
                    cls = ' class="tasks"'
                    done = task.group(1).lower() == "x"
                    body = task.group(2)
                    # The short version stays in the file for the Telegram
                    # evening message, but not on the page: under each plan
                    # row it read as clutter (her call, 8 Oct).
                    body = SHORT.sub("", body)
                    m_at = AT.search(body)
                    body = AT.sub("", body)
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
                    # When, and after what — ahead of the estimate, because the
                    # moment is what gets an awkward task started at all.
                    if m_at and not done:
                        cue = (m_at.group(2) or "").strip()
                        est = (f'<span class="tat">{html.escape(m_at.group(1))}'
                               + (f'<i> {html.escape(cue)}</i>' if cue else "")
                               + "</span>" + est)
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
                            import lines as LN   # here: lines needs model, which needs md
                            chip = ('<button class="tws"' + LN.ws_attr(wsname)
                                    + ' data-wsopen="'
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
                        menu = row_buttons(
                            shown.strip(), key, task_source, wsname,
                            open_=not done and not m_until and not m_drop)
                    else:
                        box = ('<span class="box done">&#10003;</span>' if done
                               else '<span class="box"></span>')
                        menu = ""
                    rowcls = " ".join(filter(None, [
                        "done" if done else "",
                        "parked" if m_until else "",
                        "dropped" if m_drop else ""]))
                    fold = ""
                    extra = (row_extra(bare(first[4:])) if row_extra
                             and not done and not m_drop else "")
                    items.append(f'<li class="{rowcls}">{box}'
                                 f'<span class="ttext">{inline(shown)}{est}{note}'
                                 f'{extra}</span>'
                                 f"{chip}{menu}{fold}</li>")
                else:
                    items.append(f"<li>{inline(item)}</li>")
            start = f' start="{num}"' if num != 1 else ""
            out.append(f"<{tag}{cls}{start}>" + "".join(items) + f"</{tag}>")
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
