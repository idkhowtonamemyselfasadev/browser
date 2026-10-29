#!/usr/bin/env python3
"""A sleeping tab gives its renderer back and keeps your place.

Both halves matter, and the second is the one that gets lost. Letting
a page go to save memory and then putting the reader back at the TOP of
it is a bad trade however many megabytes it buys -- browser-android hit
exactly that and had to add a saved scroll position to get it back.

This edition does not have that bug, and this suite is here so it stays
that way, because the memory numbers measured on 2026-10-29 argue for
turning sleeping ON by default and that argument depends on the feature
not being annoying.

MEASURED, not assumed (tools/memprofile.py and the runs behind it):

    25 tabs awake        533.2 MB   29 processes
    25 tabs asleep       335.3 MB    4 processes   -198.0 MB, -25

So the renderers really are released; Qt's Discarded lifecycle is doing
what it says. And the main process keeps about 1.2 MB per tab that has
been opened, which is NOT a leak: opening and closing twenty tabs three
times over costs +16.8 MB, then +0.6, then +0.1. The first round's
memory is kept and reused, which is an allocator holding freed pages.
That was worth measuring rather than chasing.

A NOTE ON MEASURING THIS AT ALL. The first version of the scroll check
reported "back at the top", confidently and wrongly. tests/harness.py's
js() takes an EXPRESSION, the code passed it had a `return` in it, and
the resulting SyntaxError came back as None -- which reads exactly like
a scroll position of zero. js() answering None for both "the page said
null" and "that did not run" is a real sharp edge under all 92 suites
here. Every check below therefore asserts its own fixture first: if the
page did not scroll, nothing after it is evidence.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


from _boot import B  # noqa: E402

B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
from tests.harness import Server, app, spin, js  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

TALL = ("<title>tall</title><style>body{margin:0}</style>"
        + "".join("<p style='height:60px'>line %d</p>" % i
                  for i in range(200)))
server = Server({"/tall": TALL, "/other": "<title>other</title>ok"})
qapp = app()
win = B.Browser()
win.resize(1200, 800)
win.show()
spin(1200)

print("(1) the fixture is a page that can actually be scrolled")
view = win.new_tab(url=QUrl(server.url("/tall")))
spin(3000)
height = js(view, "document.body.scrollHeight")
check("the page is taller than the window", (height or 0) > 5000, height)
js(view, "window.scrollTo(0, 4000)")
spin(800)
was = js(view, "Math.round(window.scrollY)")
check("...and it really scrolled", (was or 0) > 3000, was)

print()
print("(2) a tab in front never sleeps")
check("the browser refuses", win.sleep_tab(view, True) is False)
other = win.new_tab(url=QUrl(server.url("/other")))
spin(1500)

print()
print("(3) now it sleeps, and gives the renderer back")
check("it sleeps", win.sleep_tab(view, True) is True)
check("...and says so", getattr(view, "_asleep", False) is True)
check("...and Qt agrees it is no longer active", view in win.sleeping_tabs())
spin(1200)

print()
print("(4) and waking it puts him back where he was")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
spin(4000)
ready = js(view, "document.readyState")
check("the page came back", ready == "complete", ready)
now = js(view, "Math.round(window.scrollY)")
if ready != "complete":
    check("INCONCLUSIVE: the page had not finished reloading", False, ready)
else:
    check("...at the place he left it, not at the top",
          (now or 0) > 3000, "was %s, now %s" % (was, now))
    check("...and not merely somewhere non-zero",
          abs((now or 0) - (was or 0)) < 400, "was %s, now %s" % (was, now))
check("...and it is awake again", not getattr(view, "_asleep", True))

print()
print("(5) the things that must never be put to sleep")
loud = win.new_tab(url=QUrl(server.url("/other")))
spin(1200)
win.tabs.setCurrentIndex(win.tabs.indexOf(other))
spin(600)
loud.pinned = True
check("a pinned tab stays awake unless he asks",
      win.sleep_tab(loud, True) is False)
win.config["sleepPinned"] = True
check("...and sleeps once he has", win.sleep_tab(loud, True) is True)
win.config["sleepPinned"] = False
win.sleep_tab(loud, False)

print()
print("(6) auto_sleep is off until a number says otherwise")
win.config["sleepAfter"] = 0
check("zero minutes means never", win.auto_sleep() == 0)
check("...and that is the shipped default",
      '"sleepAfter": c.get("sleepAfter", 0)'
      in (HERE / "browser.py").read_text(encoding="utf-8"))

server.stop()
print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
