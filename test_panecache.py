#!/usr/bin/env python3
"""A pane you closed should not keep a renderer for the whole session.

Settings, History, Bookmarks, Downloads and the password manager are
PagePanes: the browser's own pages shown over the current tab. They are
cached in Browser._panes so reopening one is instant.

That dict was only ever written to. Nothing took a pane out, and
close_pane only calls dismiss(), which hides. A hidden pane is a live
QWebEngineView with a renderer process of its own -- so opening those
five pages once each and closing all five held, measured here in PSS
over the whole process tree:

    baseline                     308.7 MB   4 processes
    five opened and CLOSED       450.3 MB   9 processes
    held with nothing on screen  +141.6 MB  +5 processes

Found by browser-mac, who measured 725.8 MiB for seven pages in RSS.
RSS double-counts the engine pages renderers share, so their per-page
figure and this one are not comparable and both are right -- which is
exactly why the metric has to be named. This file uses PSS.

free_idle_panes() gives those back. The one just closed stays, because
closing Settings and opening it again is the common move; the rest go
45 seconds after they leave the screen, and immediately when the
machine is short of memory, on the reasoning that a page nobody is
looking at is worth less than a tab he might want back.

Two properties matter more than the megabytes, and both are checked
below: a pane that is ON SCREEN is never freed whatever is asked, and
a freed page still opens. The cache is an optimisation. It may cost a
moment; it must never cost a feature.
"""
import json
import os
import sys
import time
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
from tests.harness import app, spin  # noqa: E402

NAMES = ["settings", "history", "bookmarks", "downloads", "passwords"]


def tree(pid):
    seen, stack = [], [pid]
    while stack:
        this = stack.pop()
        seen.append(this)
        try:
            for task in Path("/proc/%d/task" % this).iterdir():
                kids = task / "children"
                if kids.exists():
                    stack += [int(x) for x in kids.read_text().split()]
        except (OSError, ValueError):
            continue
    return seen


def pss():
    """MB and process count for the whole tree."""
    pids = tree(os.getpid())
    total = 0
    for pid in pids:
        try:
            for line in Path("/proc/%d/smaps_rollup" % pid).read_text(
                    ).splitlines():
                if line.startswith("Pss:"):
                    total += int(line.split()[1])
                    break
        except OSError:
            continue
    return total / 1024.0, len(pids)


def settle():
    time.sleep(1.5)
    for _ in range(10):
        spin(200)


qapp = app()
win = B.Browser()
win.resize(1200, 800)
win.show()
spin(1500)

print("(1) opening and closing the panes leaves them cached")
settle()
base_mb, base_procs = pss()
for name in NAMES:
    win.open_pane(name)
    spin(2400)
    win.close_pane()
    spin(500)
settle()
open_mb, open_procs = pss()
check("all five were built", len(win._panes) == len(NAMES),
      sorted(win._panes))
check("...and none of them is on screen",
      not [n for n, p in win._panes.items() if p.isVisible()])
check("...and each one still costs a process",
      open_procs - base_procs >= len(NAMES) - 1,
      "%d -> %d" % (base_procs, open_procs))
print("       %.1f MB / %d processes -> %.1f MB / %d after five panes"
      % (base_mb, base_procs, open_mb, open_procs))

print()
print("(2) freeing them gives the renderers back")
freed = win.free_idle_panes(keep="passwords")
settle()
free_mb, free_procs = pss()
check("the four that were not kept went", len(freed) == 4, freed)
check("...and the one just closed stayed", list(win._panes) == ["passwords"],
      sorted(win._panes))
check("...the processes really went",
      free_procs < open_procs, "%d -> %d" % (open_procs, free_procs))
check("...and so did the memory", free_mb < open_mb - 20,
      "%.1f -> %.1f MB" % (open_mb, free_mb))
print("       gave back %.1f MB and %d processes"
      % (open_mb - free_mb, open_procs - free_procs))

print()
print("(3) a pane that is ON SCREEN is never freed, whatever is asked")
win.open_pane("history")
spin(2400)
got = win.free_idle_panes()          # no keep= at all
check("it was asked to free everything", isinstance(got, list), got)
check("...and left the visible one alone", "history" in win._panes, got)
check("...which is still on screen",
      win._panes["history"].isVisible() is True)
check("...and is still the current pane", win._pane is win._panes["history"])
win.close_pane()
spin(500)

print()
print("(4) a freed page still opens -- an optimisation, not a feature")
win.free_idle_panes()
check("the cache is empty", len(win._panes) == 0, sorted(win._panes))
win.open_pane("settings")
spin(2400)
pane = win._panes.get("settings")
check("settings opens again from nothing", pane is not None)
check("...and is on screen", pane is not None and pane.isVisible())
check("...with a live view behind it",
      pane is not None and getattr(pane, "view", None) is not None)
win.close_pane()
spin(400)

print()
print("(5) the guard is what is doing it")
# As a no-op, (2) must fail. A test that stays green with the feature
# torn out is testing the fixtures.
real = B.Browser.free_idle_panes
try:
    B.Browser.free_idle_panes = lambda self, keep=None: []
    for name in NAMES:
        win.open_pane(name)
        spin(1800)
        win.close_pane()
        spin(400)
    settle()
    before_mb, before_procs = pss()
    win.free_idle_panes(keep="passwords")
    settle()
    after_mb, after_procs = pss()
    check("with it stubbed out, nothing is freed",
          after_procs >= before_procs - 1,
          "%d -> %d" % (before_procs, after_procs))
    check("...and the memory stays put", after_mb > before_mb - 20,
          "%.1f -> %.1f MB" % (before_mb, after_mb))
finally:
    B.Browser.free_idle_panes = real
check("and the real one still frees", len(win.free_idle_panes()) > 0)

print()
print("(6) the policy is wired, not merely available")
src = (HERE / "browser.py").read_text(encoding="utf-8")
check("closing a pane schedules the sweep",
      "PANE_IDLE_MS" in src and "free_idle_panes(keep=n)" in src)
check("...and memory pressure does it at once, before sleeping a tab",
      "self.free_idle_panes()\n            acted = self.sleep_oldest(2)"
      in src)
check("release breaks the page-holds-pane ring by hand",
      "page.pane = None" in src)

print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
