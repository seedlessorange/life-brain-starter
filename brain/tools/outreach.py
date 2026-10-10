"""Outreach: message templates filled for one person, and where each ask stands.

A template is a message written once and reused: asking for a coffee chat,
thanking someone after one, nudging an ask that went quiet. They live in
brain/templates/*.md:

    ---
    name: Coffee chat ask
    channel: linkedin          # linkedin | email | message
    limit: 200                 # optional, characters (a LinkedIn invite note)
    subject: ...               # email only
    stage: asked               # optional: sending it moves the person here
    use: ask                   # ask | thanks | nudge | keep | intro
    ---
    Hi {first}, ...

Filling is plain substitution, here, with no model call: {first}, {name},
{company}, {role}, {how}, {met}, {where}, {me}. A field the person doesn't
have becomes a marked gap ("[company?]") for the owner to fill, never a guess.
The result is an ordinary draft in brain/drafts/, one person per draft, and
The owner sends it; nothing here sends anything.

The safeguard. Drafts the server writes are trusted, and a trusted draft to a
Network contact gets a send button. So a template must be what the owner
saved on the page: every save records the file's hash in
tools/.run-policy/template-hashes.json, which Claude runs cannot write, and a
template changed any other way (a run that had read someone's pasted message,
say) is refused until it is saved again from the page. The first templates,
copied from tools/outreach-templates/ the first time anyone asks, are
recorded as they are copied.
"""

import hashlib
import json
import os
import re
import shutil
from datetime import date

import model as M

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
TDIR = os.path.join(BRAIN, "templates")
SEEDS = os.path.join(HERE, "outreach-templates")
HASHES = os.path.join(HERE, ".run-policy", "template-hashes.json")
DRAFTS = os.path.join(BRAIN, "drafts")

CHANNELS = ("linkedin", "email", "message")
USES = ("ask", "thanks", "nudge", "keep", "intro")
FIELDS = ("first", "name", "company", "role", "how", "met", "where", "me")
PLACEHOLDER = re.compile(r"\{(" + "|".join(FIELDS) + r")\}")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hashes():
    try:
        with open(HASHES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _record(fn, text):
    h = _hashes()
    h[fn] = _sha(text)
    os.makedirs(os.path.dirname(HASHES), exist_ok=True)
    tmp = HASHES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=1, sort_keys=True)
    os.replace(tmp, HASHES)


def _seed():
    """First use: copy the starter templates in and trust them as copied."""
    if os.path.isdir(TDIR) and any(fn.endswith(".md") for fn in os.listdir(TDIR)):
        return
    if not os.path.isdir(SEEDS):
        return
    os.makedirs(TDIR, exist_ok=True)
    for fn in sorted(os.listdir(SEEDS)):
        if fn.endswith(".md") and not os.path.exists(os.path.join(TDIR, fn)):
            with open(os.path.join(SEEDS, fn), encoding="utf-8") as f:
                text = f.read()
            with open(os.path.join(TDIR, fn), "w", encoding="utf-8") as f:
                f.write(text)
            _record(fn, text)


def _parse(text):
    meta, body = {}, text
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = re.sub(r"\s+#.*$", "", v).strip()
                meta[k.strip().lower()] = v
        body = m.group(2)
    return meta, body.strip()


def _slug(s, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:n].strip("-") or "template"


def _safe_name(fn):
    fn = os.path.basename(fn or "")
    if not re.match(r"^[a-z0-9][a-z0-9-]*\.md$", fn):
        raise ValueError("no such template")
    return fn


def list_templates():
    """Every template, in name order, with whether it can be used as it is."""
    _seed()
    out = []
    if not os.path.isdir(TDIR):
        return out
    h = _hashes()
    for fn in sorted(os.listdir(TDIR)):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(TDIR, fn), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        meta, body = _parse(text)
        try:
            limit = int(meta.get("limit") or 0)
        except ValueError:
            limit = 0
        out.append({
            "file": fn,
            "name": meta.get("name") or fn[:-3].replace("-", " "),
            "channel": meta.get("channel", "message").lower(),
            "limit": limit,
            "subject": meta.get("subject", ""),
            "stage": meta.get("stage", "").lower(),
            "use": meta.get("use", "").lower(),
            "body": body,
            "trusted": h.get(fn) == _sha(text),
        })
    out.sort(key=lambda t: t["name"].lower())
    return out


def save_template(fn, name, channel, body, limit="", subject="", stage="", use=""):
    """Write a template from the page and trust it. Returns its file name."""
    name = " ".join((name or "").split())
    body = (body or "").strip()
    channel = (channel or "message").lower()
    stage = (stage or "").lower()
    use = (use or "").lower()
    if not name:
        raise ValueError("give the template a name")
    if not body:
        raise ValueError("the template has no text")
    if channel not in CHANNELS:
        raise ValueError("channel must be linkedin, email or message")
    if stage and stage not in M.STAGES:
        raise ValueError("stage must be one of: " + ", ".join(M.STAGES))
    if use and use not in USES:
        use = ""
    lim = str(limit or "").strip()
    if lim and not lim.isdigit():
        raise ValueError("the limit is a number of characters")
    os.makedirs(TDIR, exist_ok=True)
    if fn:
        fn = _safe_name(fn)
    else:
        fn = _slug(name) + ".md"
        n = 2
        while os.path.exists(os.path.join(TDIR, fn)):
            fn = f"{_slug(name)}-{n}.md"
            n += 1
    head = ["---", f"name: {name}", f"channel: {channel}"]
    if lim and lim != "0":
        head.append(f"limit: {lim}")
    if channel == "email" and (subject or "").strip():
        head.append(f"subject: {' '.join(subject.split())}")
    if stage:
        head.append(f"stage: {stage}")
    if use:
        head.append(f"use: {use}")
    head.append("---")
    text = "\n".join(head) + "\n" + body + "\n"
    path = os.path.join(TDIR, fn)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    _record(fn, text)
    return fn


def archive_template(fn):
    """Out of the list, kept on disk (templates/archive/). Nothing is deleted."""
    fn = _safe_name(fn)
    src = os.path.join(TDIR, fn)
    if not os.path.isfile(src):
        raise ValueError("no such template")
    os.makedirs(os.path.join(TDIR, "archive"), exist_ok=True)
    dst = os.path.join(TDIR, "archive", fn)
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(TDIR, "archive", f"{fn[:-3]}-{n}.md")
        n += 1
    shutil.move(src, dst)


def owner_name(cfg=None):
    """The owner's first name for {me}, from config's `owner` ("Sam's").
    "My" (the starter's default) is not a name, so it gives nothing."""
    cfg = cfg if cfg is not None else M.load_config()
    own = str(cfg.get("owner") or "").strip()
    own = re.sub(r"['’]s$", "", own).strip()
    return "" if own.lower() in ("my", "me", "") else own.split()[0]


def fill_text(text, person, me=""):
    """Put the person into a template's text. Missing fields become a gap."""
    name = person.get("name", "")
    vals = {
        "first": name.split()[0] if name else "",
        "name": name,
        "company": person.get("company", ""),
        "role": person.get("role", ""),
        "how": person.get("how", ""),
        "met": person.get("met", ""),
        "where": person.get("where", ""),
        "me": me,
    }
    gaps = {"me": "[your name]"}

    def sub(m):
        k = m.group(1)
        return vals.get(k) or gaps.get(k) or f"[{k}?]"
    return PLACEHOLDER.sub(sub, text or "")


def beeper_here():
    """Whether Beeper has ever synced on this machine: only then can a
    message draft offer Beeper's send button instead of copy."""
    return os.path.exists(os.path.join(BRAIN, ".beeper-review.json"))


def fill(template_file, person_name, today=None, preview=False, body=None,
         subject=None):
    """Make a draft for one person from one template. Returns the draft's
    details for the page: file, body, channel, limit, subject, to, linkedin.

    `preview` writes nothing: the page shows the filled text first, so
    trying three templates doesn't leave three drafts behind. The draft is
    written when the owner copies, keeps or sends it, with the text as they
    edited it (`body`, `subject`)."""
    today = today or date.today()
    fn = _safe_name(template_file)
    tpl = next((t for t in list_templates() if t["file"] == fn), None)
    if tpl is None:
        raise ValueError("no such template")
    if not tpl["trusted"]:
        raise ValueError(f"“{tpl['name']}” was changed outside the page. "
                         "Open it under Templates and save it to use it again.")
    people = {p["name"].lower(): p for p in M.load_people(today=today)}
    p = people.get((person_name or "").strip().lower())
    if p is None:
        raise ValueError(f"nobody called {person_name!r}")
    me = owner_name()
    kind = "email" if tpl["channel"] == "email" else "message"
    body = (body if body is not None else fill_text(tpl["body"], p, me)).strip()
    if kind != "email":
        subject = ""
    elif subject is None:
        subject = fill_text(tpl["subject"], p, me)
    channel = {"email": "email", "linkedin": "linkedin"}.get(
        tpl["channel"], "beeper" if beeper_here() else "")
    to = p["emails"][0] if (kind == "email" and p.get("emails")) else ""
    out = {"file": "", "body": body, "channel": channel, "kind": kind,
           "limit": tpl["limit"], "subject": subject, "to": to,
           "linkedin": p.get("linkedin", ""), "stage": tpl["stage"],
           "personal": p.get("personal", True), "template": tpl["name"]}
    if preview:
        return out
    if not body:
        raise ValueError("the message is empty")
    os.makedirs(DRAFTS, exist_ok=True)
    base = f"{today.isoformat()}-{_slug(p['name'], 30)}-{fn[:-3]}"
    dfn, n = base + ".md", 2
    while os.path.exists(os.path.join(DRAFTS, dfn)):
        dfn = f"{base}-{n}.md"
        n += 1
    head = ["---", f"kind: {kind}"]
    if channel:
        head.append(f"channel: {channel}")
    if to:
        head.append(f"to: {to}")
    head += [f"person: {p['name']}",
             f"task: {tpl['name']}, {p['name']}",
             "status: draft",
             f"created: {today.isoformat()}"]
    if subject:
        head.append(f"subject: {' '.join(subject.split())}")
    if tpl["stage"]:
        head.append(f"stage: {tpl['stage']}")
    if tpl["limit"]:
        head.append(f"limit: {tpl['limit']}")
    head += [f"template: {fn}", "---"]
    with open(os.path.join(DRAFTS, dfn), "w", encoding="utf-8") as f:
        f.write("\n".join(head) + "\n" + body + "\n")
    out["file"] = dfn
    return out


def draft_stage(dfn):
    """(person, stage) a sent draft moves someone to, or ("", "")."""
    path = os.path.join(DRAFTS, os.path.basename(dfn or ""))
    if not (dfn or "").endswith(".md") or not os.path.isfile(path):
        return "", ""
    with open(path, encoding="utf-8") as f:
        meta, _ = _parse(f.read())
    st = meta.get("stage", "").lower()
    return meta.get("person", ""), (st if st in M.STAGES else "")


def moves_forward(current, new):
    """A stage only moves on: a thank-you sent to someone already met must
    not turn them back into `asked`."""
    order = {s: i for i, s in enumerate(M.STAGES)}
    if new not in order:
        return False
    cur = (current or "").split()[0:2]
    cur = " ".join(cur) if cur[:2] == ["to", "reach"] else (cur[0] if cur else "")
    return order[new] > order.get(cur, -1)


PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def clean_note(text):
    """A note in the owner's words. Phone numbers stay out of the brain."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("write the note first")
    if PHONE.search(text):
        raise ValueError("That looks like a phone number. Numbers stay in your "
                         "phone's contacts, not the brain.")
    return text


# ---------------------------------------------------------------------------
# LinkedIn, from the page. The export is the only route (LinkedIn has no
# connections API and scraping breaks its terms): the owner downloads it, the
# page either finds it in Downloads or takes an upload, and only the three
# small CSVs the brain uses are kept. messages.csv is never opened.

LI_DIR = os.path.join(BRAIN, "files", "linkedin")
LI_KEEP = ("connections.csv", "invitations.csv", "profile.csv")


def li_sources():
    """Where an export can be read from, newest first: the brain's own copy
    (brain/files/linkedin/) and any export zip in Downloads."""
    out = []
    if os.path.isdir(LI_DIR):
        for fn in os.listdir(LI_DIR):
            # The export's Connections.csv, or the browser helper's
            # Connections-browser.csv (browser_linkedin.py), same columns.
            if fn.lower().startswith("connections") and fn.lower().endswith(".csv"):
                out.append(("brain", LI_DIR, os.path.getmtime(os.path.join(LI_DIR, fn))))
    dl = os.path.expanduser("~/Downloads")
    try:
        for fn in os.listdir(dl):
            low = fn.lower()
            if low.endswith(".zip") and "linkedin" in low:
                out.append(("downloads", os.path.join(dl, fn),
                            os.path.getmtime(os.path.join(dl, fn))))
    except OSError:
        pass
    out.sort(key=lambda x: -x[2])
    return out


def li_take_zip(path_or_bytes):
    """Keep only the three CSVs the brain reads from an export zip, in
    brain/files/linkedin/ (git never sees brain/files/). Returns their names."""
    import io
    import zipfile
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    kept = []
    try:
        with zipfile.ZipFile(src) as z:
            members = {os.path.basename(m).lower(): m for m in z.namelist()}
            os.makedirs(LI_DIR, exist_ok=True)
            for want in LI_KEEP:
                m = members.get(want)
                if not m:
                    continue
                info = z.getinfo(m)
                if info.file_size > 20 * 1024 * 1024:
                    raise ValueError(f"{want} is too big to be a LinkedIn export")
                data = z.read(m)
                with open(os.path.join(LI_DIR, want.capitalize()), "wb") as f:
                    f.write(data)
                kept.append(want)
    except zipfile.BadZipFile:
        raise ValueError("That isn't a zip file. Upload the file LinkedIn emailed you.")
    if "connections.csv" not in kept:
        raise ValueError("No Connections.csv inside. Ask LinkedIn for the export "
                         "that includes Connections.")
    return kept


def li_connections():
    """(rows, source label, date) from the newest export, or ([], "", None).
    A Downloads zip is copied in first, so later reads need no Downloads."""
    from linkedin_import import find_exports, read_rows
    srcs = li_sources()
    if not srcs:
        return [], "", None
    kind, path, mtime = srcs[0]
    if kind == "downloads":
        try:
            li_take_zip(path)
        except ValueError:
            pass
    rows, seen = [], set()
    if os.path.isdir(LI_DIR):
        # The export first: its rows carry the connected-on date. The
        # browser's copy adds who joined since; anyone in both counts once.
        exports = sorted(find_exports(LI_DIR), key=lambda x: "browser" in x[0])
        for label, text in exports:
            for r in read_rows(text):
                k = (r.get("url") or "").rstrip("/").lower() or r["name"].lower()
                if k not in seen:
                    seen.add(k)
                    rows.append(r)
    return rows, os.path.basename(path), date.fromtimestamp(mtime)


def li_own_names():
    """The owner's own name from the export's Profile.csv, to leave them out."""
    import csv
    import io
    from people_update import normalise
    p = os.path.join(LI_DIR, "Profile.csv")
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(io.StringIO(f.read())))
    except OSError:
        return set()
    out = set()
    for r in rows[:1]:
        first = (r.get("First Name") or "").strip()
        last = (r.get("Last Name") or "").strip()
        if first:
            out.add(normalise(f"{first} {last}".strip()))
    return out


def li_fill_plan(rows):
    """What an import would write: [(person, [fields])], plus the count of
    connections that matched nobody and the ambiguous first names."""
    from linkedin_import import build_index, resolve, fill_fields, tidy_url
    matches, ambiguous, unknown = resolve(rows, build_index())
    plan = []
    for name, r in matches:
        vals = {"role": r["role"], "company": r["company"],
                "linkedin": tidy_url(r["url"]),
                "met": f"on LinkedIn, {r['when']}" if r["when"] else ""}
        fields = fill_fields(name, vals, dry_run=True)
        if fields:
            plan.append((name, fields, vals))
    return plan, len(unknown), [(n, r["name"]) for n, r in ambiguous]


def li_candidates(rows, targets=(), people=None):
    """Connections not on the people list, ranked for outreach: a target
    company or field first, then roles that can hire, refer or advise, then
    the most recent connections. Leaves out anyone hidden or already kept."""
    from linkedin_import import build_index, resolve, tidy_url
    from people_update import normalise
    try:
        from crosschannel import SENIOR
    except Exception:
        SENIOR = re.compile(r"\b(founder|ceo|director|head of|vp|partner)\b", re.I)
    _m, _a, unknown = resolve(rows, build_index())
    try:
        with open(os.path.join(BRAIN, "people-ignored.json"), encoding="utf-8") as f:
            hidden = {normalise(x) for x in json.load(f)}
    except (OSError, ValueError):
        hidden = set()
    hidden |= li_own_names()
    tg = [t.strip().lower() for t in targets if t and t.strip()]
    out = []
    for r in unknown:
        if normalise(r["name"]) in hidden:
            continue
        work = f"{r['role']} {r['company']}".lower()
        hit = next((t for t in tg if t in work), "")
        out.append({"name": r["name"], "role": r["role"], "company": r["company"],
                    "url": tidy_url(r["url"]), "when": r["when"],
                    "target": hit, "senior": bool(SENIOR.search(r["role"] or ""))})

    def when_key(c):
        m = re.match(r"([A-Z][a-z]{2}) (\d{4})", c["when"] or "")
        if not m:
            return 0
        mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
               "Oct", "Nov", "Dec"].index(m.group(1)) if m.group(1) in (
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec").split() else 0
        return int(m.group(2)) * 12 + mon
    out.sort(key=lambda c: (not c["target"], not c["senior"], -when_key(c),
                            c["name"].lower()))
    return out
