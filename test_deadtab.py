#!/usr/bin/env python3
"""A dead renderer must not leave a blank, unclickable tab.

When a tab's render process dies -- a crash, an out-of-memory kill, or the
GPU process taking it down -- Qt leaves the QWebEngineView blank and
unresponsive. Nothing loads, nothing takes a click: the classic "dead
tab". new_tab now connects renderProcessTerminated to _render_gone,
which reloads once to bring a fresh renderer up, and only if that dies too
falls back to a plain recovery page with a link to try again -- never a
black hole.

This drives _render_gone directly (a renderer cannot be crashed to order
offscreen) and checks each branch. Offscreen, scratch data; the real vault
and config are never opened.
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1000, 700)
win.show()
app.processEvents()

STAT = QWebEnginePage.RenderProcessTerminationStatus
CRASH = STAT.CrashedTerminationStatus
NORMAL = STAT.NormalTerminationStatus

print("(1) the signal is wired for every new tab")
view = win.new_tab(url=None)
app.processEvents()
# a page it can point a recovery link at
view._requested = "https://example.test/page"

# spy on the two recovery routes so we can see which one _render_gone took
reloads = []
pages = []
win._crash_reload = lambda v: reloads.append(v)
win._show_crash_page = lambda v, t: pages.append((v, t))

print("\n(2) a normal, intended teardown is left alone")
win._render_gone(view, NORMAL, 0)
app.processEvents(); time.sleep(0.12); app.processEvents()
check("no reload scheduled for a normal termination", reloads == [], reloads)
check("no recovery page for a normal termination", pages == [], pages)
check("no crash timestamp stamped", getattr(view, "_crash_reload_at", 0) == 0)

print("\n(3) a crashed renderer is reloaded once to revive it")
win._render_gone(view, CRASH, 1)
check("a crash stamps the time of the reload attempt",
      getattr(view, "_crash_reload_at", 0) > 0)
app.processEvents(); time.sleep(0.12); app.processEvents()
check("the crash scheduled exactly one reload", reloads == [view], reloads)
check("no recovery page yet -- the reload gets first go", pages == [], pages)

print("\n(4) a second crash right after (the reload did not help) shows "
      "the recovery page instead of looping")
win._render_gone(view, CRASH, 1)
app.processEvents(); time.sleep(0.05); app.processEvents()
check("no second reload was scheduled", reloads == [view], reloads)
check("the recovery page was shown for this view",
      len(pages) == 1 and pages[0][0] is view, pages)
# _render_gone offers `url() or _requested or _pending`. Which of the
# three is non-empty depends on how far this view's load got, so a
# check that names one of them is a check about the box it runs on:
# this one first asserted _requested won (true only while the page had
# not committed an address) and then that url() won (true only once it
# had). It failed on Tim's desktop the first way and on the server the
# second. Assert the precedence instead, on views whose three sources
# the test sets itself -- and keep the claim about `view` to the one
# thing that is true either way.
check("and it carries one of the three addresses it may offer",
      pages and pages[0][1] in (view.url().toString(),
                                getattr(view, "_requested", ""),
                                getattr(view, "_pending", "")), pages)
check("...which is a real address, not nothing",
      pages and pages[0][1], pages)

asked = []
rang = []
# their own spies: the shared `reloads`/`pages` lists are what the
# later sections assert on, and these extra crashes must not land in
# them
win._show_crash_page = lambda v, t: asked.append((v, t))
win._crash_reload = lambda v: rang.append(v)


def offered(address, requested, pending):
    """What the recovery page is handed for a view whose three address
    sources are exactly these. Two crashes: the first is spent on the
    reload attempt, the second is the one that gives up and offers."""
    probe = win.new_tab(url=None, blank=True)
    app.processEvents()
    probe.url = lambda: QUrl(address)
    probe._requested = requested
    probe._pending = pending
    before = len(asked)
    win._render_gone(probe, CRASH, 1)
    app.processEvents(); time.sleep(0.05); app.processEvents()
    win._render_gone(probe, CRASH, 1)
    app.processEvents(); time.sleep(0.05); app.processEvents()
    return asked[before][1] if len(asked) > before else None


check("the view's own address wins when it has one",
      offered("https://loaded.test/a", "https://asked.test/b",
              "https://pending.test/c") == "https://loaded.test/a")
check("...the requested one when it has not",
      offered("", "https://asked.test/b",
              "https://pending.test/c") == "https://asked.test/b")
check("...and the pending one when there is nothing else",
      offered("", "", "https://pending.test/c") == "https://pending.test/c")
nothing = offered("", "", "")
check("with none of the three, nothing is offered",
      not nothing, nothing)
win._show_crash_page = lambda v, t: pages.append((v, t))
win._crash_reload = lambda v: reloads.append(v)

print("\n(5) with nothing to reload, it goes straight to the recovery page")
view2 = win.new_tab(url=None)
app.processEvents()
pages2 = []
win._show_crash_page = lambda v, t: pages2.append((v, t))
win._crash_reload = lambda v: reloads.append(("unexpected", v))
# a fresh blank view: url() empty and no _requested -> target is ""
win._render_gone(view2, CRASH, 1)
app.processEvents(); time.sleep(0.05); app.processEvents()
check("no reload attempted when there is no address",
      all(r == view for r in reloads), reloads)
check("the recovery page is shown even with an empty target",
      len(pages2) == 1 and pages2[0][0] is view2, pages2)

print("\n(6) the real _show_crash_page builds without raising")
# restore the real method and let it run against a live view
win2 = win  # alias for clarity
B.Browser._show_crash_page(win, view2, "https://example.test/page")
app.processEvents()
check("the real recovery page rendered without error", True)

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
