#!/usr/bin/env python3
"""A finished document as a PDF, the format applications and forms ask for.

    python3 brain/tools/topdf.py cv.md               # cv.pdf beside it
    python3 brain/tools/topdf.py cv.md out.pdf
    python3 brain/tools/topdf.py letter.docx         # Word files too

Why this exists (7 Oct 2026): she asked a conversation for her CV as a PDF and
it spent twelve tries on tools this Mac does not have (pandoc with no LaTeX,
LibreOffice, wkhtmltopdf) before handing the job back to her. Markdown goes
through the brain's own renderer (md.py) into a page styled for paper, a Word
file through macOS's textutil, and the page is printed to PDF by:

  1. WebKit, through osascript: built into every Mac, and the one engine that
     works inside a conversation's sandbox. Chrome does not (tested 7 Oct:
     its single-instance lock needs a socket and its helper a port
     registration, and the sandbox refuses both).
  2. Chrome, headless, when there is no WebKit (not a Mac) or it failed.

Nothing is fetched from the network. toshare.py --pdf uses this to put the
PDF in To share.
"""
import html
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Arc.app/Contents/MacOS/Arc",
]

# Paper, not screen: A4, quiet type, headings that separate without shouting.
PAGE_CSS = """
@page { size: A4; margin: 16mm 17mm 16mm 17mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 10.4pt/1.42 "Helvetica Neue", Helvetica, Arial, sans-serif;
       color: #1d1d1f; margin: 0; }
h1, h2 { font-size: 19pt; font-weight: 600; letter-spacing: -.01em;
         margin: 0 0 3pt; }
h3 { font-size: 9.4pt; font-weight: 700; letter-spacing: .08em;
     text-transform: uppercase; color: #3a3a3c; margin: 13pt 0 5pt;
     padding-bottom: 3pt; border-bottom: .6pt solid #c7c7cc; }
h4 { font-size: 10.4pt; font-weight: 600; margin: 8pt 0 2pt; }
h1 strong, h2 strong, h3 strong, h4 strong { font-weight: inherit; }
p { margin: 0 0 5pt; }
ul, ol { margin: 0 0 6pt; padding-left: 14pt; }
li { margin: 0 0 2.5pt; }
a { color: inherit; text-decoration: none; }
hr { border: 0; border-top: .6pt solid #c7c7cc; margin: 9pt 0; }
table { border-collapse: collapse; margin: 0 0 6pt; }
td, th { padding: 2pt 6pt 2pt 0; vertical-align: top; text-align: left; }
h2 + p, h1 + p { color: #48484a; margin-bottom: 4pt; }
h3, h4 { break-after: avoid; }
li, p { break-inside: avoid; }
"""


# WebKit's own printing: the page laid out at the text width, paginated onto
# A4 with these margins (points), saved straight to a file with no dialog.
WEBKIT_JS = r"""
ObjC.import('Cocoa');
ObjC.import('WebKit');
function run(argv) {
  var page = argv[0], out = argv[1];
  var W = 595.28, H = 841.89, M = 46;
  $.NSApplication.sharedApplication;
  var wv = $.WebView.alloc.initWithFrameFrameNameGroupName(
    $.NSMakeRect(0, 0, W - 2 * M, H), $(), $());
  wv.mainFrame.loadRequest($.NSURLRequest.requestWithURL($.NSURL.fileURLWithPath(page)));
  var t0 = Date.now();
  while (wv.isLoading && Date.now() - t0 < 20000)
    $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.05));
  $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.3));
  var pi = $.NSPrintInfo.alloc.initWithDictionary($.NSMutableDictionary.dictionary);
  pi.paperSize = $.NSMakeSize(W, H);
  pi.topMargin = M; pi.bottomMargin = M; pi.leftMargin = M; pi.rightMargin = M;
  pi.horizontalPagination = $.NSFitPagination;
  pi.verticalPagination = $.NSAutoPagination;
  pi.horizontallyCentered = false; pi.verticallyCentered = false;
  pi.jobDisposition = $.NSPrintSaveJob;
  pi.dictionary.setObjectForKey($.NSURL.fileURLWithPath(out), $.NSPrintJobSavingURL);
  var op = $.NSPrintOperation.printOperationWithViewPrintInfo(
    wv.mainFrame.frameView.documentView, pi);
  op.showsPrintPanel = false; op.showsProgressPanel = false;
  return op.runOperation ? 'written' : 'failed';
}
"""


def chrome():
    for p in CHROMES:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    for name in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return ""


def _from_markdown(path):
    import md as MD
    with open(path, encoding="utf-8", errors="replace") as f:
        _, body = MD.split_frontmatter(f.read())
    return MD.render(body)


def _from_word(path):
    """A .docx as HTML, through macOS's own converter."""
    r = subprocess.run(["textutil", "-convert", "html", "-stdout", path],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("could not read the Word file: "
                           + (r.stderr or "").strip()[-200:])
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", r.stdout)
    return m.group(1) if m else r.stdout


def page(src):
    """The source as one self-contained page, ready to print."""
    ext = os.path.splitext(src)[1].lower()
    if ext in (".md", ".markdown"):
        body = _from_markdown(src)
    elif ext == ".docx":
        body = _from_word(src)
    elif ext in (".html", ".htm"):
        with open(src, encoding="utf-8", errors="replace") as f:
            return f.read()
    elif ext == ".txt":
        with open(src, encoding="utf-8", errors="replace") as f:
            body = "<pre style='white-space:pre-wrap;font:inherit'>%s</pre>" % (
                html.escape(f.read()))
    else:
        raise ValueError("can make a PDF from .md, .docx, .html or .txt, "
                         "not " + (ext or "a file with no extension"))
    title = html.escape(os.path.splitext(os.path.basename(src))[0])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title>"
            "<style>%s</style></head><body>%s</body></html>"
            % (title, PAGE_CSS, body))


def make(src, dest=""):
    """Write the PDF and return its path."""
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.isfile(src):
        raise ValueError("no such file: " + src)
    import school
    if school.is_confidential(src):
        raise ValueError("that file is marked confidential")
    dest = os.path.abspath(dest or os.path.splitext(src)[0] + ".pdf")
    work = tempfile.mkdtemp(prefix="topdf-")
    try:
        page_path = os.path.join(work, "page.html")
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(page(src))
        tmp_pdf = os.path.join(work, "out.pdf")
        why = []
        for engine in (_webkit, _chrome):
            ok, msg = engine(page_path, tmp_pdf, work)
            if ok:
                break
            if msg:
                why.append(msg)
        else:
            raise RuntimeError("could not print the page to PDF ("
                               + "; ".join(why)[-400:] + "). Open the Word copy "
                               "and use File > Save as PDF")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(tmp_pdf, dest)
        return dest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _good(path):
    return os.path.isfile(path) and os.path.getsize(path) > 500


def _webkit(page_path, tmp_pdf, work):
    """(ok, why not) for macOS's own WebKit."""
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return False, ""
    js = os.path.join(work, "print.js")
    with open(js, "w", encoding="utf-8") as f:
        f.write(WEBKIT_JS)
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", js, page_path, tmp_pdf],
                           capture_output=True, text=True, timeout=90,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "WebKit took too long"
    if _good(tmp_pdf):
        return True, ""
    return False, "WebKit: " + ((r.stderr or r.stdout).strip()[-200:] or "no file")


def _chrome(page_path, tmp_pdf, work):
    """(ok, why not) for headless Chrome."""
    exe = chrome()
    if not exe:
        return False, "no Chrome"
    log_path = os.path.join(work, "chrome.log")
    cmd = [exe, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--disable-background-networking",
           "--no-pdf-header-footer", "--hide-scrollbars",
           "--user-data-dir=" + os.path.join(work, "profile"),
           "--print-to-pdf=" + tmp_pdf, "file://" + page_path]
    # Chrome prints in a couple of seconds and then, on this Mac, never
    # exits (tested 7 Oct: the PDF was done at 2s, the process still up
    # at 90). So wait for its "written" line, then close it ourselves.
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL,
                                start_new_session=True)
    done, waited = False, 0.0
    try:
        while waited < 60:
            with open(log_path, errors="replace") as f:
                if "bytes written to file" in f.read():
                    done = True
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.3)
            waited += 0.3
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
    if done or _good(tmp_pdf):
        return True, ""
    with open(log_path, errors="replace") as f:
        tail = f.read().strip()[-200:]
    return False, "Chrome: " + (tail or "no file")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        sys.exit(__doc__.split("\n\n")[1])
    try:
        print(make(args[0], args[1] if len(args) > 1 else ""))
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
