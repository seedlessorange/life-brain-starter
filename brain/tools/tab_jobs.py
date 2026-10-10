"""The Jobs tab: where the job hunt stands.

A seasonal place, like School: in the bar only while config `jobs.on` is
true. Its question is "where is my search?" — what needs her (chases, roles
going stale), what is in play by stage, and the new roles the scan found.
The data and every rule live in jobs.py; this file only draws them.
"""
from datetime import date

import os
import re

import agents as AG
import browser_core as BC
import career as C
import jobs as J
from build import e, glance_row

STAGE_LABEL = {"interested": "Want to apply", "applied": "Applied",
               "interviewing": "Interviewing", "offer": "Offer",
               "closed": "Closed"}
# The buttons each stage offers, as (label, stage, outcome). The next step
# first; the honest ending last.
STAGE_ACTS = {
    "interested": [("Applied", "applied", ""), ("Let it go", "closed", "withdrew")],
    "applied": [("Got an interview", "interviewing", ""),
                ("Rejected", "closed", "rejected")],
    "interviewing": [("Got an offer", "offer", ""),
                     ("Rejected", "closed", "rejected"),
                     ("Withdrew", "closed", "withdrew")],
    "offer": [("Accepted", "closed", "accepted"),
              ("Declined", "closed", "declined")],
}


def _days(n):
    if n is None:
        return ""
    return "today" if n <= 0 else "1 day" if n == 1 else "%d days" % n


_HELPERS = {}


def _helpers():
    if not _HELPERS:
        try:
            _HELPERS.update(BC.status())
        except Exception:                                       # noqa: BLE001
            _HELPERS.update(installed=False, chrome=False,
                            on={h: False for h in BC.HELPERS})
    return _HELPERS


def _work():
    """What the server is writing right now, by role (brain/.jobs-work.json):
    a row being written shows it instead of its buttons."""
    import json as _json
    from datetime import datetime as _dt
    try:
        with open(os.path.join(J.BRAIN, ".jobs-work.json"), encoding="utf-8") as f:
            items = _json.load(f)
    except Exception:                                           # noqa: BLE001
        return {}
    out = {}
    for it in items:
        try:
            age = (_dt.now() - _dt.strptime(it["started"], "%Y-%m-%d %H:%M:%S")).total_seconds()
        except (KeyError, ValueError):
            continue
        if it.get("state") in ("queued", "running") and age < 900:
            out[it.get("ref", "")] = it
    return out


_WORK = {}


def _busy(ref):
    if not _WORK:
        _WORK.update(_work() or {"": None})
    it = _WORK.get(ref)
    return ('<span class="jbbusy">Writing&hellip; started %s</span>'
            % e(it["started"][11:16])) if it else ""


def _doc_id(rel):
    """The file viewer's id for a kit file, or "" when it is not there."""
    if not rel:
        return ""
    import docs as D
    p = os.path.join(J.BRAIN, rel)
    return D._id(p) if os.path.exists(p) else ""


def _kit(a):
    """The application kit as buttons that open each piece."""
    out = []
    for key, label in (("cv", "CV"), ("letter", "Cover letter"), ("prep", "Prep")):
        fid = _doc_id(a.get(key))
        if not fid:
            continue
        if key == "prep":
            out.append(f'<button class="mini jbkit" data-openfile="{fid}"'
                       ' title="Open your interview prep">Prep &#10003;</button>')
            continue
        tip = "Open your %s to read and edit it" % label.lower()
        chk = a.get("check" if key == "letter" else "cvcheck")
        if chk:
            tip += ". Read closely, it goes beyond your profile here: " + chk
        out.append(f'<button class="mini jbkit" data-jkit="{e(a["heading"])}"'
                   f' data-jkitdoc="{key}" title="{e(tip)}">{label} &#10003;</button>')
    return "".join(out)


def _form_btn(a, label=None):
    """Fill the form (helper on) or open it in her browser."""
    if not a["link"].startswith("https://"):
        return ""
    h = e(a["heading"])
    if _helpers()["on"].get("apply") and _helpers().get("installed"):
        return (f'<button class="mini go needs-server" data-jfill="{h}" title="Opens'
                ' the form in Chrome and fills it from your profile, CV attached.'
                ' It never clicks Submit.">%s</button>' % (label or "Fill the form"))
    import browser_apply as BA
    return (f'<button class="mini go" data-jopen="{e(BA.apply_url(a["link"]))}"'
            ' title="The form in your browser, for you to fill. Switch on form'
            ' filling (Next moves, or Browser helpers) and the brain fills it for'
            ' you; you still press Submit.">Open the form &#8599;</button>')


def _btn(label, **data):
    attrs = " ".join(f'data-{k}="{e(v)}"' for k, v in data.items())
    return f'<button class="mini" {attrs}>{label}</button>'


def _stage_btns(a):
    """One clear next step for the role's stage, the rest under More."""
    h = a["heading"]
    if _busy(h):
        return _kit(a) + _busy(h)
    ready = bool(_doc_id(a.get("cv")) and _doc_id(a.get("letter")))
    main, more = [], []
    if a["stage"] == "interested":
        if ready:
            main += [_form_btn(a), _btn("I applied", jstage="applied",
                                       joutcome="", jhead=h)]
        else:
            main.append(f'<button class="mini go needs-server" data-jprepare-head='
                        f'"{e(h)}" title="A CV and a cover letter for this role, from'
                        ' your profile. About a minute.">Prepare application</button>')
            more.append(_btn("I applied", jstage="applied", joutcome="", jhead=h))
        more.append(_btn("Let it go", jstage="closed", joutcome="withdrew", jhead=h))
    elif a["stage"] == "applied":
        if a["ball"] == "Them":
            main.append(_btn("Chased", jchased=h))
        main.append(_btn("Got an interview", jstage="interviewing", joutcome="", jhead=h))
        more += [_btn("Rejected", jstage="closed", joutcome="rejected", jhead=h),
                 _btn("Withdrew", jstage="closed", joutcome="withdrew", jhead=h)]
    elif a["stage"] == "interviewing":
        if not _doc_id(a.get("prep")):
            main.append(f'<button class="mini go needs-server" data-jprep="{e(h)}"'
                        ' title="Likely questions, your stories for each, your gaps'
                        ' and what to ask them">Prep me</button>')
        main.append(_btn("Got an offer", jstage="offer", joutcome="", jhead=h))
        more += [_btn("Chased", jchased=h),
                 _btn("Rejected", jstage="closed", joutcome="rejected", jhead=h),
                 _btn("Withdrew", jstage="closed", joutcome="withdrew", jhead=h)]
    elif a["stage"] == "offer":
        main += [_btn("Accepted", jstage="closed", joutcome="accepted", jhead=h),
                 _btn("Declined", jstage="closed", joutcome="declined", jhead=h)]
    if a["stage"] in ("interested", "applied"):
        more += [f'<button class="mini needs-server" data-jcv="{e(h)}">'
                 + ("Rewrite the CV" if _doc_id(a.get("cv")) else "Tailor a CV")
                 + "</button>",
                 f'<button class="mini needs-server" data-jletter="{e(h)}">'
                 + ("Rewrite the letter" if _doc_id(a.get("letter"))
                    else "Write a cover letter") + "</button>"]
    if a["stage"] in ("applied", "interviewing") and _doc_id(a.get("prep")):
        more.append(f'<button class="mini needs-server" data-jprep="{e(h)}">'
                    "Redo the prep</button>")
    more.append('<button class="mini needs-server" data-box data-box-intent='
                f'"draft" data-box-text="%s" title="{AG.short()} drafts it; you send it">'
                "Draft a note to someone there</button>"
                % e("Draft a short note to someone I know at %s about the %s "
                    "role (%s). Check who I know there first."
                    % (a["company"], a["role"], STAGE_LABEL[a["stage"]].lower())))
    if a["stage"] == "interested" and ready:
        main = [_kit(a)] + main
    elif _kit(a):
        main = [_kit(a)] + main
    return ("".join(main) + '<details class="jbmore"><summary class="mini">More'
            '</summary><div class="jbmorebody">%s</div></details>' % "".join(more))


def _app_row(a, why=""):
    title = (f'<a href="{e(a["link"])}" target="_blank" rel="noopener">'
             f'{e(a["role"])}</a>' if a["link"].startswith("http")
             else e(a["role"]))
    sub = " · ".join(x for x in (
        a["company"], a["where"], a.get("track", ""),
        why or ("%s, %s" % (STAGE_LABEL[a["stage"]], _days(a["days"]))
                if a["days"] is not None else STAGE_LABEL[a["stage"]]),
        ("via " + a["via"]) if a["via"] else "",
        ("next: " + a["next"]) if a["next"] else "",
        ("posting gone since " + a["gone"]) if a["gone"] else "") if x)
    return (f'<div class="mtrow jbrow"><span class="mttask">{title}'
            f"<i>{e(sub)}</i></span>"
            f'<span class="jbacts">{_stage_btns(a)}</span></div>')


def _lead_row(r, show_company=False):
    sub = " · ".join(x for x in (
        r.get("company") if show_company else "",
        r.get("where"), ("posted " + _short(r["posted"])) if r.get("posted")
        else "", "via LinkedIn" if r.get("key", "").startswith("linkedin:")
        else "", "a reach" if r.get("reach") else "") if x)
    k = e(r["key"])
    # Only a web link: the scanners keep https today, and the row shouldn't
    # depend on that if a new source forgets.
    href = e(r["url"]) if re.match(r"https?://", str(r.get("url") or ""), re.I) else "#"
    if _busy(r["key"]):
        return (f'<div class="mtrow jbrow"><span class="mttask">'
                f'<a href="{href}" target="_blank" rel="noopener">'
                f'{e(r["title"])}</a><i>{e(sub)}</i></span>'
                f'<span class="jbacts">{_busy(r["key"])}</span></div>')
    chip = ""
    if "score" in r:
        tip = r.get("fit", "")
        if r.get("gaps"):
            tip += " Gaps: " + "; ".join(r["gaps"]) + "."
        if r.get("auth") == "needs sponsorship":
            tip += " Needs a visa sponsor."
        cls = "hi" if r["score"] >= 4 else "mid" if r["score"] >= 3 else "lo"
        chip = (f'<span class="jbscore jb{cls}" title="Fit {r["score"]:.1f} out of'
                f' 5. {e(tip)}"><small>Fit</small>{r["score"]:.1f}</span>')
    return (f'<div class="mtrow jbrow">{chip}<span class="mttask">'
            f'<a href="{href}" target="_blank" rel="noopener">'
            f'{e(r["title"])}</a><i>{e(sub)}</i></span>'
            f'<span class="jbacts">'
            f'<button class="mini go needs-server" data-jprepare-key="{k}"'
            ' title="Into your tracker, with a CV and a cover letter written for'
            ' it from your profile. About a minute.">Prepare application</button>'
            f'<button class="mini" data-jlead="interested" data-jkey="{k}"'
            ' title="Into your tracker, nothing written yet">Save</button>'
            f'<button class="mini" data-jlead="skip" data-jkey="{k}"'
            ' title="Never shown again">Not for me</button></span></div>')


def _short(iso):
    try:
        d = date.fromisoformat(iso[:10])
        return "%d %s" % (d.day, d.strftime("%b"))
    except ValueError:
        return iso


def _by_company(rows):
    by = {}
    for r in rows:
        by.setdefault(r["company"], []).append(r)
    out = []
    # The company with the most roles first; three showing per company, the
    # rest folded, so one big employer cannot bury the others.
    for comp in sorted(by, key=lambda c: (-len(by[c]), c.lower())):
        rs = by[comp]
        body = "".join(_lead_row(r) for r in rs[:3])
        if len(rs) > 3:
            body += ('<details class="ghost"><summary>%d more at %s</summary>'
                     "%s</details>" % (len(rs) - 3, e(comp),
                                       "".join(_lead_row(r) for r in rs[3:])))
        out.append('<h3 class="area">%s</h3>%s' % (e(comp), body))
    return "".join(out)


def _track_leads(rs):
    """One track's new roles: scored 4 and up first, then unscored, six
    showing; under 4 folded, which is career-ops' rule: a weak fit costs an
    application and a recruiter's time."""
    good = sorted((r for r in rs if r.get("score", 0) >= 4),
                  key=lambda r: -r["score"])
    open_ = sorted((r for r in rs if "score" not in r),
                   key=lambda r: (r.get("key", "").startswith("linkedin:"),
                                  r.get("company", "").lower()))
    weak = sorted((r for r in rs if "score" in r and r["score"] < 4),
                  key=lambda r: -r["score"])
    shown = good + open_
    if not shown:
        # Nothing reaches 4 on this track: its best three still show, so a
        # track never looks empty when its closest match is a 3.8.
        shown, weak = weak[:3], weak[3:]
    out = "".join(_lead_row(r, True) for r in shown[:6])
    if len(shown) > 6:
        out += ('<details class="ghost"><summary>%d more</summary>%s</details>'
                % (len(shown) - 6, "".join(_lead_row(r, True) for r in shown[6:])))
    if weak:
        out += ('<details class="ghost"><summary>Scored under 4 &middot; %d'
                "</summary>%s</details>" % (len(weak), "".join(
                    _lead_row(r, True) for r in weak)))
    return out


def _leads_card(rows):
    """New roles, one section per track, in her order of tracks."""
    if not rows:
        return ""
    names = [t["name"] for t in J.tracks()]
    by = {}
    for r in rows:
        tr = next((x for x in (r.get("tracks") or []) if x in names),
                  names[0] if names else "")
        by.setdefault(tr, []).append(r)
    parts = []
    for n in names + [k for k in by if k not in names]:
        if by.get(n):
            parts.append(('<h3 class="area">%s</h3>' % e(n) if len(by) > 1
                          or n != "My search" else "") + _track_leads(by[n]))
    unscored = sum(1 for r in rows if "score" not in r)
    score_btn = ""
    if unscored and C.has_profile():
        score_btn = ('<button class="mini needs-server" data-jscore title="A 1 to 5'
                     ' fit against your career profile and the track, about ten'
                     ' seconds a role">Score %d</button>' % min(unscored, 15))
    legend = ('<p class="mshelp jblegend">Fit is out of 5: how well the role'
              ' matches your profile and that track. 4 and up is worth applying.'
              ' Hover a fit for the reasons and the gaps.</p>'
              if any("score" in r for r in rows) else "")
    return ('<section class="pdtray schoolcard jbleads"><h2>New roles'
            '<span class="sccount">%d</span>%s</h2>%s%s</section>'
            % (len(rows), score_btn, legend, "".join(parts)))


def _funnel_card():
    rows = [f for f in J.funnel() if f["found"] or f["pursued"]]
    if not rows:
        return ""
    out = []
    for f in rows:
        line = " · ".join([
            "%d found" % f["found"],
            "%d applied" % f["applied"],
            "%d interview%s" % (f["interviews"], "" if f["interviews"] == 1 else "s"),
            "%d offer%s" % (f["offers"], "" if f["offers"] == 1 else "s")])
        tip = ("%d%% of applications reached an interview" % f["rate"]
               if f["rate"] is not None else "No applications yet")
        warn = ""
        if f["applied"] >= 6 and not f["interviews"]:
            warn = (' <span class="jbwarn" title="Six or more applications and no'
                    ' interview: the CV angle, the titles or the track itself">'
                    "needs a look</span>")
        out.append(f'<div class="mtrow" title="{e(tip)}"><span class="mttask">'
                   f'{e(f["track"])}{warn}<i>{e(line)}</i></span></div>')
    return ('<section class="pdtray schoolcard jbfunnel"><h2>How each track is'
            ' doing</h2>%s</section>' % "".join(out))


def _track_form(t):
    lvl = t.get("level") or "post-mba"
    return (
        '<details class="jbtrack"%s><summary>%s</summary>'
        '<label class="jblab">Name<input class="jbin" data-tf="name" value="%s"'
        ' placeholder="Product at a scale-up" autocomplete="off"></label>'
        '<label class="jblab">Your one line: what and why<textarea class="jbin"'
        ' data-tf="why" rows="2" placeholder="Product roles at Paris scale-ups,'
        ' because...">%s</textarea></label>'
        '<label class="jblab">Titles<textarea class="jbin" data-tf="titles"'
        ' rows="3" placeholder="product manager, chef de produit, product'
        ' owner">%s</textarea></label>'
        '<label class="jblab">Places<input class="jbin" data-tf="places"'
        ' value="%s" placeholder="Paris, Remote" autocomplete="off"></label>'
        '<label class="jblab">Level<select class="jbin" data-tf="level">'
        '<option value="post-mba"%s>Post-MBA: no junior roles</option>'
        '<option value="any"%s>Any level</option></select></label>'
        '<div class="scacts"><button class="mini" data-tpropose>Propose titles'
        '</button><button class="mini" data-tremove>Remove this track</button>'
        '</div></details>'
        % (" open" if not t.get("titles") else "", e(t.get("name") or "New track"),
           e(t.get("name", "")), e(t.get("why", "")),
           e(", ".join(t.get("titles") or [])), e(", ".join(t.get("places") or [])),
           " selected" if lvl == "post-mba" else "",
           " selected" if lvl == "any" else ""))


def _tracks_card(jc):
    ts = J.tracks(jc)
    return ('<section class="pdtray jbtracks needs-server"><h2>Your tracks</h2>'
            '<p class="mshelp">Two or three searches, each its own titles,'
            ' places and reason. The score reads the reason.</p>'
            '<div id="jbtracklist">%s</div>'
            '<template id="jbtracknew">%s</template>'
            '<div class="scacts"><button class="mini" id="jbtrackadd">Add a track'
            '</button><button class="mini" id="jbtracksave">Save tracks</button>'
            '<span class="mshelp" id="jbtrackhelp"></span></div></section>'
            % ("".join(_track_form(t) for t in ts), _track_form({})))


def _prefs_card(jc):
    t = ", ".join(jc["titles"])
    p = ", ".join(jc["places"])
    return ('<section class="pdtray jbprefs needs-server"><h2>What you look for</h2>'
            '<label class="jblab">Roles<input class="jbin" id="jbtitles"'
            f' value="{e(t)}" placeholder="product manager, chief of staff"'
            ' autocomplete="off"></label>'
            '<label class="jblab">Places<input class="jbin" id="jbplaces"'
            f' value="{e(p)}" placeholder="Paris, Remote" autocomplete="off">'
            '</label>'
            '<div class="scacts"><button class="mini" id="jbprefsave">Save</button>'
            '<span class="mshelp">A role word matches the start of a word in'
            ' the title. Leave places empty for anywhere.</span></div></section>')


def _companies_card(jc, st):
    rows = []
    for c in sorted(jc["companies"], key=lambda c: c.get("name", "").lower()):
        info = (st.get("companies") or {}).get(c["name"]) or {}
        label = J.BOARDS.get(c.get("board"), {}).get("label", c.get("board"))
        if info.get("error"):
            note = "did not answer last time"
        elif info:
            note = "%d open, %d match" % (info.get("open", 0),
                                          info.get("matched", 0))
        else:
            note = "not scanned yet"
        rows.append(f'<div class="mtrow"><span class="mttask">{e(c["name"])}'
                    f'<i>{e(label)} · {e(note)}</i></span>'
                    f'<button class="mini" data-jdrop="{e(c["name"])}"'
                    f' title="Stop following {e(c["name"])}">&times;</button></div>')
    for pg in jc.get("pages") or []:
        info = (st.get("sources") or {}).get(pg.get("name")) or {}
        note = ("%d links, %d match" % (info.get("open", 0), info.get("matched", 0))
                if info else "read by the browser search")
        rows.append(f'<div class="mtrow"><span class="mttask">{e(pg.get("name"))}'
                    f'<i>Careers page · {e(note)}</i></span>'
                    f'<button class="mini" data-jdrop="{e(pg.get("name"))}"'
                    f' title="Stop following {e(pg.get("name"))}">&times;</button></div>')
    return ('<section class="pdtray schoolcard jbcomps needs-server"><h2>Companies you follow'
            '<span class="sccount">%d</span></h2>%s'
            '<div class="jbadd"><input class="jbin" id="jbcomp"'
            ' placeholder="Company name or careers page link" autocomplete="off">'
            '<button class="mini" id="jbcompadd">Follow</button></div>'
            '<p class="mshelp" id="jbcomphelp">Works for companies on Ashby,'
            ' Greenhouse, Lever, Workable, SmartRecruiters, Recruitee and'
            ' Teamtailor.</p></section>'
            % (len(rows), "".join(rows)))


def _profile_card():
    text = C._read(C.PROFILE)
    blanks = len(re.findall(r"\[blank\]", text))
    stories = len(re.findall(r"(?m)^### ", C._read(C.STORIES)))
    line = " · ".join(x for x in (
        ("%d blank%s to fill" % (blanks, "" if blanks == 1 else "s")) if blanks
        else "complete" if text else "not started",
        "%d stor%s in the bank" % (stories, "y" if stories == 1 else "ies"))
        if x)
    return ('<section class="pdtray jbprof needs-server"><h2>Your career profile</h2>'
            '<p class="mshelp">%s</p><div class="scacts">'
            '<button class="mini" data-box data-box-intent="update" data-box-text="'
            'Help me fill the [blank] lines in my career profile (career/profile.md),'
            ' one question at a time.">Fill the blanks</button>'
            '<button class="mini" id="jbstories" title="Stories for interviews from'
            ' your profile and your recent days, added to the end of the bank for'
            ' you to keep or cut">Propose stories</button></div></section>'
            % e(line))


HELPER_TEXT = {
    "apply": ("Fill application forms",
              "Fills the form in Chrome from your profile, and you press Submit."),
    "linkedin": ("Read my LinkedIn connections",
                 "Against LinkedIn's terms; reads once a day at a person's pace."),
    "scan": ("Search LinkedIn jobs and careers pages",
             "Logged out, a few searches when you check the boards."),
}


def _browser_card():
    h = _helpers()
    if not h.get("chrome"):
        return ""
    if not h.get("installed"):
        return ('<section class="pdtray jbbrowser needs-server"><h2>Browser helpers'
                '</h2><p class="mshelp">Off until you set them up: about 140 MB,'
                ' inside the brain, using your Chrome.</p><div class="scacts">'
                '<button class="mini" id="jbbsetup">Set up</button></div>'
                '</section>')
    rows = []
    for k in BC.HELPERS:
        name, note = HELPER_TEXT[k]
        on = h["on"].get(k)
        extra = ""
        if on and k == "linkedin":
            extra = ('<span class="jbacts"><button class="mini" data-jbstart="linkedin"'
                     ' data-jbwhat="login">Log in</button><button class="mini"'
                     ' data-jbstart="linkedin" data-jbwhat="connections">Read'
                     ' connections</button></span>')
        rows.append(
            f'<div class="mtrow jbrow"><span class="mttask">{e(name)}'
            f'<i>{e(note)}</i>{extra}</span>'
            f'<button class="mini" data-jbswitch="{k}" data-on="{0 if on else 1}"'
            + (' title="Takes your Touch ID">Switch on</button>' if not on
               else '>Switch off</button>') + "</div>")
    return ('<section class="pdtray schoolcard jbbrowser needs-server"><h2>Browser'
            ' helpers</h2>%s<p class="mshelp" id="jbbstatus"></p></section>'
            % "".join(rows))


def _own_card():
    return ('<section class="pdtray jbown needs-server"><h2>Found one yourself</h2>'
            '<input class="jbin" id="jbowntitle" placeholder="Role" autocomplete="off">'
            '<input class="jbin" id="jbowncomp" placeholder="Company" autocomplete="off">'
            '<input class="jbin" id="jbownlink" placeholder="Link (optional)"'
            ' autocomplete="off">'
            '<div class="scacts"><button class="mini" id="jbownadd">Track it'
            '</button></div></section>')


def _hero(jc, st, live, needs, lead_n):
    n = len(live)
    if not jc["companies"] or not J.tracks(jc):
        head = "Job hunt. Tell it what you look for."
    elif n:
        head = "Job hunt. %d role%s in play." % (n, "" if n == 1 else "s")
    else:
        head = "Job hunt."
    by = {}
    for a in live:
        by[a["stage"]] = by.get(a["stage"], 0) + 1
    bits = [{"icon": "alert", "text": "%d need you" % len(needs),
             "title": "Chases and roles going stale", "kind": "warn"}
            if needs else {},
            {"icon": "doc", "text": "%d new" % lead_n,
             "title": "New roles from the scan, waiting for a yes or no"}
            if lead_n else {},
            {"icon": "flag", "text": "%d applied" % by["applied"],
             "title": "Applied, waiting on them"} if by.get("applied") else {},
            {"icon": "calendar", "text": "%d interviewing" % by["interviewing"],
             "title": "In interviews"} if by.get("interviewing") else {},
            {"icon": "cake", "text": "%d offer%s" % (
                by["offer"], "" if by["offer"] == 1 else "s"),
             "title": "Offers to answer"} if by.get("offer") else {}]
    scanned = st.get("scanned", "")
    scan = ('<div class="scacts mttray needs-server"><button class="ghostbtn"'
            ' id="jbscan" data-browser="%s" title="Reads the job board of every company you'
            ' follow and keeps the roles that match what you look for">'
            'Check the boards</button><span class="mshelp" id="jbscanhelp">%s'
            "</span></div>"
            % (("1" if _helpers()["on"].get("scan") and _helpers().get("installed")
                else "0"), e(" · ".join(x for x in (
                "%d companies" % len(jc["companies"]) if jc["companies"] else "",
                ("last looked " + scanned) if scanned else "") if x))))
    does = ('<p class="jbdoes">Every morning your brain reads the job boards of'
            ' the companies you follow and scores each new role 1 to 5. For any'
            ' role it writes a tailored CV and cover letter, preps you for the'
            ' interview, and fills the application form. You press Submit.</p>')
    work = '<div class="jbwork" id="jbwork" hidden></div>'
    return ('<h2 class="skinx skinx-greet">%s</h2>' % e(head)
            + does + glance_row([b for b in bits if b]) + scan + work)


def _move(text, faint, btn):
    return (f'<div class="mtrow jbrow jbmove"><span class="mttask">{e(text)}'
            f'<i>{e(faint)}</i></span><span class="jbacts">{btn}</span></div>')


def _next_moves(jc, apps, flags, leads):
    """What the brain can do for her right now, most useful first, five at
    most: chases, applications ready to send, the best new roles, then the
    two inputs that make everything else sharper."""
    moves = []
    for f in flags:
        h = f["heading"]
        if f["need"] == "chase":
            moves.append(_move(f["text"], f["why"], _btn("Chased", jchased=h)))
        elif f["stage"] == "interested":
            ready = _doc_id(f.get("cv")) and _doc_id(f.get("letter"))
            moves.append(_move(f["text"], f["why"], _form_btn(f) if ready else
                               f'<button class="mini go needs-server" data-jprepare-head'
                               f'="{e(h)}">Prepare application</button>'))
        else:
            moves.append(_move(f["text"], f["why"], ""))
    flagged = {f["heading"] for f in flags}
    for a in apps:
        if (a["stage"] == "interested" and a["heading"] not in flagged
                and _doc_id(a.get("cv")) and _doc_id(a.get("letter"))):
            moves.append(_move("Send your application to %s" % a["company"],
                               "%s · CV and cover letter ready" % a["role"],
                               _form_btn(a)))
    best, seen_t = [], set()
    for r in sorted((r for r in leads if r.get("score", 0) >= 3.5),
                    key=lambda r: -r["score"]):
        t = (J.fold(r["title"]), J.fold(r["company"]))
        if t not in seen_t:          # one posting per title per company
            seen_t.add(t)
            best.append(r)
        if len(best) == 2:
            break
    for r in best:
        tr = (r.get("tracks") or [""])[0]
        moves.append(_move("Apply for %s at %s" % (r["title"], r["company"]),
                           "Fit %.1f out of 5%s · CV and letter in about a minute"
                           % (r["score"], (" on your %s track" % tr) if tr else ""),
                           f'<button class="mini go needs-server" data-jprepare-key='
                           f'"{e(r["key"])}">Prepare application</button>'))
    if len(best) > 1:
        keys = ",".join(r["key"] for r in best)
        moves.append(_move("Prepare all %d at once" % len(best),
                           "They are written side by side; keep working meanwhile",
                           f'<button class="mini needs-server" data-jprepare-many='
                           f'"{e(keys)}">Prepare all {len(best)}</button>'))
    ready = [a for a in apps if a["stage"] == "interested"
             and _doc_id(a.get("cv")) and _doc_id(a.get("letter"))]
    h = _helpers()
    if ready and h.get("chrome") and not h["on"].get("apply"):
        moves.append(_move("Let the brain fill your application forms",
                           "It fills the form in Chrome from your profile, CV"
                           " attached. You check it and press Submit",
                           ('<button class="mini" data-jbswitch="apply" data-on="1"'
                            ' title="Takes your Touch ID">Switch on</button>')
                           if h.get("installed") else
                           '<button class="mini" data-jbsetupbtn>Set up</button>'))
    unscored = sum(1 for r in leads if "score" not in r)
    if unscored and C.has_profile():
        moves.append(_move("Score %d new role%s" % (unscored, "" if unscored == 1 else "s"),
                           "A 1 to 5 fit for each, so the best rise to the top",
                           '<button class="mini needs-server" data-jscore>Score'
                           " them</button>"))
    for t in J.tracks(jc):
        if not t["why"] and t["name"] != "My search":
            moves.append(_move("Say why you want the %s track" % t["name"],
                               "One line. The score reads it; today it guesses",
                               _btn("Write it", jtrackfocus=t["name"])))
            break
    blanks = len(re.findall(r"\[blank\]", C._read(C.PROFILE)))
    if blanks:
        moves.append(_move("Fill %d blanks in your career profile" % blanks,
                           "Target roles, salary floor, start date: the CV, letter"
                           " and score all read them",
                           '<button class="mini" data-box data-box-intent="update"'
                           ' data-box-text="Help me fill the [blank] lines in my career'
                           ' profile (career/profile.md), one question at a time.">'
                           "Fill the blanks</button>"))
    if not moves:
        return ""
    return ('<section class="pdtray schoolcard jbmoves"><h2>Next moves</h2>%s'
            "</section>" % "".join(moves[:6]))


def view(cfg=None, today=None):
    today = today or date.today()
    jc = J.jobs_cfg(cfg)
    st = J._state()
    apps = J.applications(today, cfg)
    flags = J.flags(today, cfg)
    live = [a for a in apps if a["stage"] != "closed"]
    closed = [a for a in apps if a["stage"] == "closed"]
    leads = J.leads(st)
    main = [_hero(jc, st, live, flags, len(leads)),
            _next_moves(jc, apps, flags, leads)]
    if live:
        groups = []
        for s_ in ("offer", "interviewing", "applied", "interested"):
            rs = [a for a in live if a["stage"] == s_]
            if rs:
                groups.append('<h3 class="area">%s</h3>%s' % (
                    e(STAGE_LABEL[s_]), "".join(_app_row(a) for a in rs)))
        main.append('<section class="pdtray schoolcard"><h2>Your applications'
                    '<span class="sccount">%d</span></h2>%s</section>'
                    % (len(live), "".join(groups)))
    main.append(_leads_card(leads))
    main.append(_funnel_card())
    if closed:
        main.append('<details class="ghost schoolmore"><summary>Closed '
                    "&middot; %d</summary>%s</details>" % (
                        len(closed), "".join(
                            '<div class="mtrow"><span class="mttask">%s<i>%s'
                            "</i></span></div>" % (
                                e(a["heading"]), e(a["outcome"] or "closed"))
                            for a in closed)))
    rail = [_profile_card(), _tracks_card(jc), _companies_card(jc, st),
            _own_card(), _browser_card()]
    return ('<div class="todaygrid jobsview"><div class="todaymain">%s</div>'
            '<aside class="todayrail">%s</aside></div>'
            % ("".join(m for m in main if m), "".join(rail)) + AG.say(KIT_EDITOR))


KIT_EDITOR = (
    '<div id="jbkited" class="jbkited" hidden role="dialog" aria-modal="true"'
    ' aria-labelledby="jbkittitle"><div class="jbkitcard">'
    '<div class="jbkithead"><div><p class="eyebrow" id="jbkitwhat"></p>'
    '<h2 id="jbkittitle"></h2></div><div class="jbkittabs">'
    '<button class="mini" data-kitdoc="cv">CV</button>'
    '<button class="mini" data-kitdoc="letter">Cover letter</button></div>'
    '<button class="mini" id="jbkitclose" aria-label="Close">Close</button></div>'
    '<p class="jbkitcheck" id="jbkitcheck" hidden></p>'
    '<textarea id="jbkittext" spellcheck="true" aria-label="The document"></textarea>'
    '<div class="jbkitask"><input id="jbkitask" autocomplete="off" placeholder='
    '"Or tell Claude what to change: shorter summary, lead with the product work..."'
    ' aria-label="What to change">'
    '<label class="jbkitrem"><input type="checkbox" id="jbkitremember" checked>'
    ' Remember for next time</label>'
    '<button class="mini" id="jbkitrevise">Change it</button></div>'
    '<div class="jbkitfoot"><button class="mini go" id="jbkitsave">Save</button>'
    '<button class="mini" id="jbkitword">Open in Word</button>'
    '<span class="mshelp" id="jbkitsay">Edit the text directly. Save rebuilds the'
    ' Word file and learns from what you changed.</span></div>'
    '<details class="jbkitlessons"><summary id="jbkitlessonsum">What your'
    ' applications learned</summary><ul id="jbkitlessons"></ul></details>'
    '</div></div>')


def sweep_rows(cfg=None, today=None):
    """Today's two-minute sweep: the chases only. A stale role is a choice,
    not a two-minute job, so it waits on the Jobs tab."""
    if not J.is_on(cfg):
        return ""
    out = []
    for f in J.flags(today, cfg):
        if f["need"] != "chase":
            continue
        out.append('<a class="drow owed" href="#/jobs">'
                   f'<span class="dname">{e(f["text"])}</span>'
                   f'<span class="dwhy">&middot; {e(f["why"])}</span>'
                   '<span class="darrow" aria-hidden="true">&rarr;</span></a>')
    return "".join(out)


def render(V, cfg, today):
    if J.is_on(cfg):
        V["jobs"].append(view(cfg, today))
