"""The brain's `find` calls, for Windows.

Where the brain walks big folders on every page build it shells out to
find(1): fast, and every Mac has it. Windows' find.exe is a text search that
answers those calls with nothing, so a day's files, a turn's changed files
and a project's file list came back empty there (28 Sep audit). This is the
same walk in Python — slower, and correct.
"""
import os


def walk(root, maxdepth=None, skip=(), newer=None, until=None,
         hidden=True, follow=False):
    """Files under root, like `find root -type f`.

    maxdepth    as find's -maxdepth: 1 is root's own files
    skip        names never entered or listed (find's -prune / -not -path)
    newer       a datetime: modified after it (find -newermt)
    until       a datetime: not modified after it (find ! -newermt)
    hidden      False leaves out dot-files and everything in dot-folders
    follow      follow symlinked folders (find -L)
    """
    t0 = newer.timestamp() if newer else None
    t1 = until.timestamp() if until else None
    root = os.path.abspath(root)
    base = root.rstrip(os.sep).count(os.sep)
    out = []
    for d, dirs, files in os.walk(root, followlinks=follow):
        depth = d.rstrip(os.sep).count(os.sep) - base
        dirs[:] = [x for x in dirs
                   if x not in skip and (hidden or not x.startswith("."))]
        if maxdepth is not None and depth >= maxdepth - 1:
            dirs[:] = []
        if maxdepth is not None and depth >= maxdepth:
            continue
        for fn in files:
            if fn in skip or (not hidden and fn.startswith(".")):
                continue
            p = os.path.join(d, fn)
            if t0 is not None or t1 is not None:
                try:
                    m = os.stat(p).st_mtime
                except OSError:
                    continue
                if (t0 is not None and m <= t0) or (t1 is not None and m > t1):
                    continue
            out.append(p)
    return out
