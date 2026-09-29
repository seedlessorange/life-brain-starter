#!/usr/bin/env python3
"""Fill in who your professional contacts actually are, from LinkedIn's export.

    python3 brain/tools/linkedin_import.py ~/Downloads          # show what it found
    python3 brain/tools/linkedin_import.py ~/Downloads --write   # fill people.md

Your people file tends to know when you last spoke to a professional contact
and nothing else about them — no role, no company, no link. This fills that in,
which is what turns a list of names into something you can ask questions of.

LinkedIn has no API for your connections, and scraping the site breaks their
terms. The legitimate route is their own copy-of-your-data export, and that is
the only thing this reads. Ask for it at Settings > Data privacy > Get a copy
of your data > Connections; it arrives by email as a zip in about ten minutes.
Drop the zip in Downloads — this reads inside it, no unzipping needed.

WHAT IT WRITES: Role, Company, LinkedIn and Met, for people already on your
list. Four rules hold it honest:

  - It only ever fills a BLANK field. Anything you wrote yourself is never
    touched, and re-running is safe.
  - It never adds anyone. A LinkedIn connection who is not already on your
    people list is reported and skipped — the same rule the Beeper sync
    follows, and for the same reason: a connections list is full of recruiters.
  - It never matches on a guess. A first name that could be two people is
    reported as ambiguous rather than filed against whichever came first.
  - It does not read the export's email column at all. People.md holds context
    you chose to keep, not a contact database.
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from import_chats import PEOPLE, people_aliases          # noqa: E402
from people_update import normalise                      # noqa: E402

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_NAMES = {i: m for m, i in
               zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], range(1, 13))}
# The export is written in the language of the account, so the same three
# columns arrive under French or Spanish headers on a French or Spanish login.
HEADERS = {
    "first": ("first name", "prénom", "prenom", "nombre"),
    "last": ("last name", "nom", "apellidos"),
    "url": ("url", "profil url", "perfil url"),
    "company": ("company", "société", "societe", "entreprise", "empresa"),
    "position": ("position", "poste", "puesto", "cargo"),
    "when": ("connected on", "date de connexion", "fecha de conexión",
             "fecha de conexion"),
}


def find_exports(root):
    """Every Connections.csv under `root`, loose or inside an export zip.

    Returned as (label, text) so a zip needs no unpacking — she downloads the
    file and points this at Downloads, which is the whole interaction.
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")][:200]
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            low = fn.lower()
            if low.endswith(".csv") and "connection" in low:
                try:
                    with open(path, encoding="utf-8-sig", errors="replace") as f:
                        out.append((path, f.read()))
                except OSError:
                    pass
            elif low.endswith(".zip"):
                try:
                    with zipfile.ZipFile(path) as z:
                        for member in z.namelist():
                            if "connection" in member.lower() and member.lower().endswith(".csv"):
                                raw = z.read(member).decode("utf-8-sig", errors="replace")
                                out.append((f"{path} :: {member}", raw))
                except (zipfile.BadZipFile, OSError, KeyError):
                    pass
    return out


def read_rows(text):
    """The export opens with a few lines of preamble before the real header,
    so the header is found by looking for it rather than assumed to be line 1."""
    lines = text.split("\n")
    start = 0
    for i, line in enumerate(lines[:12]):
        low = line.lower()
        if ("first name" in low or "prénom" in low or "prenom" in low) and "," in low:
            start = i
            break
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    cols = {}
    for key, names in HEADERS.items():
        for field in (reader.fieldnames or []):
            if (field or "").strip().lower() in names:
                cols[key] = field
                break

    rows = []
    for r in reader:
        def get(key):
            return (r.get(cols[key]) or "").strip() if key in cols else ""
        first, last = get("first"), get("last")
        name = " ".join(x for x in (first, last) if x)
        if not name:
            continue
        rows.append({
            "name": name,
            "first": first,
            "url": get("url"),
            "company": get("company"),
            "role": get("position"),
            "when": parse_when(get("when")),
        })
    return rows


def parse_when(s):
    """`21 Aug 2024` -> `Aug 2024`, for the page to print after the word "met".

    The month is as precise as this claims to be, and the claim stays modest:
    it is when you connected on LinkedIn, which is often but not always when
    you actually met.
    """
    s = (s or "").strip().lower()
    m = re.match(r"(\d{1,2})\s+([a-zà-ÿ]{3,})\s+(\d{4})", s)
    if m and m.group(2)[:3] in MONTHS:
        return f"{MONTH_NAMES[MONTHS[m.group(2)[:3]]]} {m.group(3)}"
    m = re.match(r"(\d{4})-(\d{2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{MONTH_NAMES[int(m.group(2))]} {m.group(1)}"
    return ""


def tidy_url(u):
    """A profile link, normalised the same way model.py does when it reads one."""
    u = (u or "").strip()
    if not u:
        return ""
    u = u.rstrip("/")
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    if not u.startswith("https://"):
        u = "https://" + u.lstrip("/") if "linkedin.com" in u.lower() else ""
    return u


# --------------------------------------------------------------------------
# matching: a full name, or an unmistakable first name, and nothing looser

def build_index():
    """{normalised name: canonical} over every name and `Also:` alias."""
    idx = {}
    for canonical, names in people_aliases().items():
        for alias in names:
            n = normalise(alias)
            if n:
                idx.setdefault(n, canonical)
    return idx


def resolve(rows, idx):
    """Work out who each connection is. Returns (matches, ambiguous, unknown).

    A full-name hit is taken. A first-name-only hit is taken ONLY when it is
    unmistakable in both directions: exactly one person on the list goes by
    that name, and exactly one connection in the export claims it. Two Sophies
    in a thousand connections is the normal case, and filing a job title
    against the wrong friend is worse than filing nothing.
    """
    first_counts = {}
    for r in rows:
        first_counts[normalise(r["first"])] = first_counts.get(normalise(r["first"]), 0) + 1

    matches, ambiguous, unknown = [], [], []
    for r in rows:
        full = normalise(r["name"])
        if full in idx:
            matches.append((idx[full], r))
            continue
        first = normalise(r["first"])
        if first and first in idx:
            if first_counts.get(first, 0) == 1:
                matches.append((idx[first], r))
            else:
                ambiguous.append((idx[first], r))
            continue
        unknown.append(r)
    return matches, ambiguous, unknown


# --------------------------------------------------------------------------
# writing: fill blanks, never overwrite

FIELD_ORDER = ("Role", "Company", "LinkedIn", "Met")


def person_block(lines, name):
    """(start, end) line numbers of one person's entry, or None."""
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.*)$", line.strip())
        if m and re.sub(r"[*`]", "", m.group(1)).strip().lower() == name.lower():
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j].strip()):
            end = j
            break
    return start, end


def fill_fields(name, values, path=None, dry_run=False):
    """Write the blank fields among `values` for one person.

    Returns the field names actually written. A field she has already filled
    in is left exactly as she wrote it — this only ever completes a record.

    `dry_run` works out the same answer without saving, so the preview says
    what the run would really do rather than assuming an empty file. A preview
    that overstates on a re-run is worse than no preview: it makes a finished
    import look like an unstarted one.
    """
    path = path or PEOPLE
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    span = person_block(lines, name)
    if not span:
        return []
    start, end = span

    have, last_field = set(), start
    for j in range(start + 1, end):
        m = re.match(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$", lines[j])
        if m:
            last_field = j
            if m.group(2).strip():
                have.add(m.group(1).strip().lower())

    written, insert = [], last_field + 1
    for field in FIELD_ORDER:
        value = (values.get(field.lower()) or "").strip()
        if not value or field.lower() in have:
            continue
        lines.insert(insert, f"- **{field}:** {value}")
        insert += 1
        written.append(field)

    if written and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--write", action="store_true",
                    help="actually fill people.md (otherwise just report)")
    ap.add_argument("--people", default=None, help="a different people.md (for testing)")
    ap.add_argument("--show", type=int, default=25,
                    help="how many rows to print in each list")
    args = ap.parse_args()

    root = os.path.expanduser(args.folder)
    if not os.path.isdir(root):
        sys.exit(f"No such folder: {root}")

    exports = find_exports(root)
    if not exports:
        sys.exit(
            f"No LinkedIn connections export found under {root}.\n"
            "Ask LinkedIn for one: Settings > Data privacy > Get a copy of your\n"
            "data > Connections. It emails you a zip in about ten minutes —\n"
            "save it to Downloads and run this again. The zip works as-is.")

    rows, seen = [], set()
    for label, text in exports:
        got = read_rows(text)
        print(f"Read {len(got)} connections from {label}")
        for r in got:
            key = (normalise(r["name"]), r["company"].lower())
            if key not in seen:
                seen.add(key)
                rows.append(r)
    if not rows:
        sys.exit("That export had no readable connection rows.")

    idx = build_index()
    matches, ambiguous, unknown = resolve(rows, idx)
    print(f"\n{len(rows)} connections. {len(matches)} are on your people list, "
          f"{len(ambiguous)} ambiguous, {len(unknown)} not on it.\n")

    filled, already = [], 0
    for who, r in sorted(matches, key=lambda m: m[0].lower()):
        values = {
            "role": r["role"],
            "company": r["company"],
            "linkedin": tidy_url(r["url"]),
            # The page prints this after the word "met", so it is phrased to
            # read as a sentence there: "met on LinkedIn, Mar 2025".
            "met": f"on LinkedIn, {r['when']}" if r["when"] else "",
        }
        written = fill_fields(who, values, args.people, dry_run=not args.write)
        if not written:
            already += 1
            continue
        filled.append((who, r, written))

    verb = "filled" if args.write else "would fill"
    for who, r, written in filled[:args.show]:
        detail = " at ".join(x for x in (r["role"], r["company"]) if x) or "(no role listed)"
        print(f"  {who:<28}{detail[:48]:<50}{verb} {', '.join(written)}")
    if len(filled) > args.show:
        print(f"  ... and {len(filled) - args.show} more")

    if ambiguous:
        print(f"\nAmbiguous — several connections share this first name, so nothing "
              f"was written ({len(ambiguous)} total, first {min(args.show, len(ambiguous))}):")
        for who, r in ambiguous[:args.show]:
            at = f" at {r['company']}" if r["company"] else ""
            print(f"  '{r['name']}'{at} might be your {who}")
        print("  Settle one by adding their full name as an `Also:` line on that "
              "person, then re-run.")

    if unknown:
        print(f"\nNot on your people list: {len(unknown)} "
              f"connection{'s' if len(unknown) != 1 else ''}. Nothing was added — "
              "add anyone worth keeping on the People page first.")

    if args.write:
        print(f"\nFilled {len(filled)} people ({already} already complete). "
              "Rebuild with: python3 brain/tools/build.py")
    else:
        print(f"\nNothing was changed ({already} already complete). "
              "Re-run with --write to apply.")


if __name__ == "__main__":
    main()
