#!/usr/bin/env python3
"""A page of the browser's own loads once, and a pane keeps what it has.

Settings used to flash: the page appeared, then his wallpaper showed
through where it had been, then the page appeared again. Two separate
causes, both of them a document being thrown away:

  * every navigation to one of our own pages was refused once and
    asked for again, so the engine loaded twice for one open
  * every open of a pane loaded again over the document that was
    already in there, and tore it down the moment the pane was up

Nobody was counting loads, which is why both survived so long. This
counts them.

Covers:

  * the first open of each of the five panes: exactly one loadStarted
  * the second and the third: none at all, and the document that was
    in there is the same object afterwards (a JS marker survives), so
    there is no moment where the pane is up with nothing in it
  * a new tab's start page: one load, not two
  * when something the page reads really has changed — a visit, a
    setting, a download, a bookmark — it does load again
  * and afterwards the trust is still right: our own page holds the
    bridge, a website holds `pw` and nothing else

Offscreen, against a scratch config. Your own data is never opened.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

PANES = ["settings", "downloads", "history", "bookmarks", "passwords"]
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "vaultPassword": True,
                                     "restoreTabs": False}))
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1280, 900)
win.show()


def spin(ms):
    """Let Qt (and the engine) get on with it for a while."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, script, world=B.MAIN_WORLD_ID, timeout=8000):
    """runJavaScript, synchronously, in a given world."""
    loop = QEventLoop()
    box = {"v": None, "got": False}

    def back(value):
        box["v"] = value
        box["got"] = True
        loop.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout)
    page.runJavaScript(script, world, back)
    loop.exec()
    return box["v"] if box["got"] else "<no answer>"


class Counter:
    """Every load a view starts and finishes, counted."""

    def __init__(self, view):
        self.view = view
        self.started = self.finished = self.ok = 0
        view.loadStarted.connect(self._start)
        view.loadFinished.connect(self._finish)

    def _start(self):
        self.started += 1

    def _finish(self, ok):
        self.finished += 1
        self.ok += int(bool(ok))

    def reset(self):
        self.started = self.finished = self.ok = 0
        return self


spin(2500)

# =====================================================================
print("\n(1) the first open of a pane loads once, not twice")
counters = {}
for name in PANES:
    win.close_pane()
    spin(150)
    win.open_pane(name)
    pane = win._panes[name]
    counters[name] = Counter(pane.view)
    spin(2500)
    check("%s: one load for the first open" % name,
          counters[name].started == 1,
          "loadStarted=%d" % counters[name].started)
    check("%s: and it arrived" % name, counters[name].ok == 1,
          "ok=%d" % counters[name].ok)
    check("%s: holding the bridge" % name,
          js(pane.view.page(), "typeof bridge") == "object")

# =====================================================================
print("\n(2) opening it again keeps the document that is already there")
for name in PANES:
    pane = win._panes[name]
    for again in (2, 3):
        win.close_pane()
        spin(150)
        js(pane.view.page(), "window.__kept = %d;" % again)
        counters[name].reset()
        win.open_pane(name)
        spin(1200)
        check("%s: open %d loads nothing" % (name, again),
              counters[name].started == 0,
              "loadStarted=%d" % counters[name].started)
        check("%s: open %d keeps the same document" % (name, again),
              js(pane.view.page(), "window.__kept") == again,
              js(pane.view.page(), "window.__kept"))
        check("%s: open %d still has the bridge" % (name, again),
              js(pane.view.page(), "typeof bridge") == "object")
        check("%s: open %d is on the full channel" % (name, again),
              pane.view.page()._channel_kind == "full")
win.close_pane()
spin(150)

# =====================================================================
print("\n(3) when what it shows really has changed, it loads again")
pane = win._panes["history"]
counter = counters["history"]


def reopen(label, change=None):
    win.close_pane()
    spin(150)
    if change is not None:
        change()
    counter.reset()
    win.open_pane("history")
    spin(1500)
    return counter.started


check("a visit makes it stale",
      reopen("visit", lambda: win._record_history(
          QUrl("https://example.com/"), "Example")) == 1)
check("and the next open is quiet again", reopen("quiet") == 0)
check("a saved setting makes it stale",
      reopen("config", lambda: (win.config.__setitem__("zoom", 1.1),
                                win.save_config())) == 1)
check("and the next open is quiet again", reopen("quiet") == 0)
check("a download makes it stale",
      reopen("download", win.bridge.downloadsChanged.emit) == 1)
check("a bookmark makes it stale",
      reopen("bookmark", win.bridge.bookmarksChanged.emit) == 1)
check("the vault makes it stale",
      reopen("vault", win.bridge.vaultChanged.emit) == 1)
check("the toolbar makes it stale",
      reopen("toolbar", win.bridge.toolbarChanged.emit) == 1)
win.close_pane()
spin(150)

# =====================================================================
print("\n(4) a new tab's start page loads once too")
view = win.new_tab()
tab_counter = Counter(view)
spin(2500)
check("one load for a new tab", tab_counter.started == 1,
      "loadStarted=%d" % tab_counter.started)
check("and it arrived", tab_counter.ok == 1, "ok=%d" % tab_counter.ok)
check("the start page holds the bridge",
      js(view.page(), "typeof bridge") == "object")
check("on the full channel", view.page()._channel_kind == "full")

# =====================================================================
print("\n(5) and a website still gets `pw` and nothing else")
site = SCRATCH / "not-ours.html"
site.write_text("<!doctype html><meta charset=utf-8><b id=x>not ours</b>")
view.load(QUrl.fromLocalFile(str(site)))
spin(2500)
check("the site loaded", js(view.page(), "document.getElementById('x')"
                            " && document.getElementById('x').textContent")
      == "not ours")
check("it is on the password channel", view.page()._channel_kind == "pw",
      view.page()._channel_kind)
check("no bridge in its own world",
      js(view.page(), "typeof bridge", B.MAIN_WORLD_ID) == "undefined")
check("no transport in its own world either",
      js(view.page(), "!!(window.qt && qt.webChannelTransport)",
         B.MAIN_WORLD_ID) is False)
check("the password channel is there, in its own world",
      js(view.page(), "!!(window.qt && qt.webChannelTransport)",
         B.PW_WORLD_ID) is True)

# back to one of ours: the bridge comes back
view.load(QUrl(B.START_PAGE))
spin(2500)
check("our own page gets it back", view.page()._channel_kind == "full")
check("and really has it", js(view.page(), "typeof bridge") == "object")

# =====================================================================
print("\n(6) priming grants nothing on its own")
page = view.page()
page.prime_trust(QUrl(B.SETTINGS_PAGE))
check("priming one of ours sets the full channel",
      page._channel_kind == "full")
page.prime_trust(QUrl("https://example.com/"))
check("priming a website sets the password one",
      page._channel_kind == "pw")
page._install_channel("full")
typed = B.QWebEnginePage.NavigationType.NavigationTypeTyped
allowed = page.acceptNavigationRequest(QUrl("https://example.com/"),
                                       typed, True)
check("a website is still bounced off the full channel",
      not allowed and page._channel_kind == "pw", page._channel_kind)

print("\nnothing anywhere near the real config")
check("this test never opened it",
      str(B.CONFIG_FILE).startswith(str(SCRATCH)), B.CONFIG_FILE)

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
