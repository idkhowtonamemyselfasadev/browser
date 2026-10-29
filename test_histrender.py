#!/usr/bin/env python3
"""The browser's own pages have to actually draw.

test_histicon.py reads the source: the slot is there, the JS asks for a
map of icons, no page fetches one from a third party. All four of those
were true and green on 2026-10-27 while the history page rendered
**nothing at all**.

    history.html:523
      document.getElementById("v_searches").onclick = () => setView(...)

a96d8e8 (2026-10-22) took the Searches view out -- the <button> and one
textContent line went with it. That handler stayed behind.
getElementById returned null, setting .onclick on null threw, and an
uncaught throw in an inline script abandons every statement below it:
the Statistics button on the very next line, bygroup, shownoise,
export, delrange, popen, all five context-menu handlers, and the load()
at the bottom that puts the rows on screen. Five days, four static
greps and two green suites walked straight past it, because not one of
them loaded the page.

Found by claude-e7 in the macOS edition and reported across; the
numbers below were reproduced here before the fix was written.

So there are two kinds of check in here, and the first is the one that
generalises:

  (1) static, over every .html the browser ships: an element the script
      reaches for *and dereferences* must exist in the same file. The
      same orphan in settings.html -- which reaches for 295 of them --
      would break that page exactly as quietly.
  (2) live: open the pane for real, count the rows and the icons that
      are actually on screen, and check that the handlers which sat
      below the throw got wired.

A page being careful is left alone: `const x = getElementById("y")`
followed by `if (x)` is the correct way to ask for something optional.
It is the unguarded dereference that throws.

Offscreen, against scratch data. Your own history and config are never
opened.

    test_histrender.py                 this tree: static half, then live
    test_histrender.py --dir <path>    static half over another edition's
                                       pages; the live half is skipped,
                                       because it boots *this* build

The windows and mac trees ship the same nine pages, so check (1) is the
one thing one session can run for all of them. --dir never writes to the
folder it is pointed at and never imports anything out of it.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--dir", metavar="PATH", default=None,
                help="folder of .html pages to run the static half over "
                     "(default: this tree, which also runs the live half)")
ARGS = ap.parse_args()

PAGEDIR = Path(ARGS.dir).expanduser().resolve() if ARGS.dir else HERE
# The live half opens a pane in *this* build. Pointed at another
# edition's folder it would say nothing about that edition, so it is
# skipped rather than run against the wrong pages.
LIVE = PAGEDIR == HERE

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def js(page, code):
    """Run something in the pane's page and wait for the answer.

    The IIFE and MAIN_WORLD_ID are both load-bearing. runJavaScript
    evaluates an expression, so a bare `return` is a syntax error and
    comes back as None -- which reads exactly like a page that drew
    nothing, and costs an afternoon. The browser's own pages run in
    the main world.
    """
    box = {}
    loop = QEventLoop()
    page.runJavaScript("(function(){" + code + "})()", B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    if "v" not in box:
        # A timeout is not a value: returning box.get("v") here
        # answered None for both "the page said null" and "the page
        # never answered", and a caller writing `(js(...) or 0) >= 200`
        # then read silence as a confident zero. See tests/harness.py.
        raise AssertionError(
            "js() timed out, so the answer is not a measurement: %s"
            % str(code)[:120])
    return box["v"]


# =====================================================================
print("(1) every element the script dereferences exists in the page")
# =====================================================================
# Only the dereferenced ones, and only the ones named by a literal.
DEREF = re.compile(
    r"""getElementById\(\s*["']([A-Za-z0-9_\-]+)["']\s*\)\s*\.\s*[A-Za-z_]""")

if not PAGEDIR.is_dir():
    print("  FAIL no such folder  <%s>" % PAGEDIR)
    sys.exit(1)
if not LIVE:
    print("    (%s)" % PAGEDIR)

PAGES = sorted(PAGEDIR.glob("*.html"))
check("there are pages to check at all", len(PAGES) > 5, len(PAGES))

for page in PAGES:
    text = page.read_text(encoding="utf-8", errors="replace")
    # a commented-out handler is not a finding
    live = "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("//"))
    want = set(DEREF.findall(live))
    missing = []
    for name in sorted(want):
        # an id attribute anywhere in the file, in the static markup or
        # inside a template string, since many of these rows are built
        # by innerHTML at runtime; and `el.id = "x"` for the rest
        if re.search(r"""id\s*=\s*\\?["']?%s\b""" % re.escape(name), text):
            continue
        missing.append(name)
    check("%s: %d reached for, none missing" % (page.name, len(want)),
          not missing, ", ".join(missing) if missing else "")


# =====================================================================
if not LIVE:
    print("\n(2) the history page draws rows -- SKIPPED")
    print("    --dir was given; the live half boots this tree's build, so it")
    print("    would test %s's pages, not the ones above." % HERE.name)
    print("\n%d checks failed" % len(fails))
    sys.stdout.flush()
    os._exit(1 if fails else 0)

print("\n(2) the history page draws rows, with icons from the store")
# =====================================================================
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402

# English, not whatever the box is set to: the live half reads text off
# the page, and the first-run wizard comes up in German otherwise.
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "vaultPassword": True}))

from tests.harness import app, spin  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402

# Held in a name on purpose: nothing else references the QApplication,
# and a bare app() call lets it be collected the moment it returns --
# the next widget then dies with "Must construct a QApplication first".
qapp = app()
win = B.Browser()
win.show()
spin(800)

now = int(time.time())
# `t`, not `time`: history.html reads e.t, and a row with the wrong key
# still draws -- it just says "Invalid Date" -- so this would pass while
# testing nothing about the timestamp.
win.history.append({"url": "https://example.com/a", "title": "An example",
                    "t": now, "i": 0})

# a real 1x1 PNG in the icon store, so site_icon_data has bytes to serve
icons = Path(win.icons_dir())
icons.mkdir(parents=True, exist_ok=True)
(icons / "example.com.png").write_bytes(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"))

check("the store answers for that host",
      (win.site_icon_data("example.com") or "").startswith("data:image/png"))

win.open_history()
spin(4000)
page = win._panes["history"].view.page()

check("the page finished loading",
      js(page, "return document.readyState;") == "complete")

rows = js(page, "return document.querySelectorAll('#list > *').length;")
check("it drew something", (rows or 0) > 0, rows)
check("and the entry is on screen",
      js(page, "return (document.body.innerText || '')"
               ".toLowerCase().indexOf('example') >= 0;") is True)

imgs = js(page, "return document.querySelectorAll('#list img').length;")
check("the row has an icon", (imgs or 0) > 0, imgs)
check("...and it is a data: URL out of the local store",
      js(page, "return Array.from(document.querySelectorAll('#list img'))"
               ".every(function(i){return (i.src||'')"
               ".indexOf('data:') === 0;});") is True)
check("...and not one of them was fetched over the network",
      js(page, "return Array.from(document.querySelectorAll('#list img'))"
               ".filter(function(i){return /^https?:/.test(i.src||'');})"
               ".length;") == 0)

# The handlers that sat below the throw. Without these the page looks
# fine until something is clicked, which is why it survived five days.
for name in ("v_stats", "bygroup", "shownoise", "export", "delrange",
             "popen"):
    check("the %s control got wired" % name,
          js(page, "return typeof (document.getElementById('%s')"
                   " || {}).onclick;" % name) == "function")

print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
