#!/usr/bin/env python3
"""The browser's own pages are panes, not pages.

Settings, downloads, history, bookmarks and the password manager all
behave the same way now: they come up over whatever tab is showing,
Esc puts it back, and none of them is a place you can navigate to.

Covers, in the browser rather than in a docstring:

  * opening any of the five costs no tab
  * only one pane is ever on screen
  * Esc closes the pane and leaves the tab underneath exactly where
    it was — not a start page loaded over it
  * Esc belongs to the page first: an open password editor, a bookmark
    being renamed and a settings search box with something in it each
    take it, keep the pane, and keep what was typed — and the next Esc
    closes the pane as always
  * a pane whose page never answers still goes down
  * "Re-run setup" lands on the start page with the wizard on it, not
    on the page he set for new tabs
  * the shortcut that opened a pane closes it again
  * none of the five is ever written into sessionTabs, and a session
    saved by an older version that did write one does not restore it
  * with Vault Password off the passwords pane does not open at all,
    and is never even built — in a process of its own, because that
    switch is read once when the browser starts

Offscreen, against a scratch config. Your own data is never opened.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer, Qt, QUrl  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

PANES = ["settings", "downloads", "history", "bookmarks", "passwords"]
OTHER_FOUR = ["settings", "downloads", "history", "bookmarks"]
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def build(vault_on):
    """One Browser, offscreen, against this process's scratch config."""
    B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                         "vaultPassword": vault_on,
                                         "restoreTabs": True}))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.resize(1280, 900)
    win.show()
    return app, win


# =====================================================================
# --vaultoff: Vault Password is read at startup, so it gets its own
# process rather than a second Browser in this one
# =====================================================================
if len(sys.argv) > 1 and sys.argv[1] == "--vaultoff":
    app, win = build(False)
    app.processEvents()
    out = {"on": win.vault_password_on(), "tabs0": win.tabs.count()}
    win.open_passwords()
    app.processEvents()
    out["paneOpen"] = win.pane_open("passwords")
    out["anyPane"] = win.pane_open()
    out["built"] = "passwords" in win._panes
    out["tabs1"] = win.tabs.count()
    win.toggle_passwords()
    app.processEvents()
    out["toggleOpened"] = win.pane_open()
    out["builtAfterToggle"] = "passwords" in win._panes
    out["otherFour"] = all((win.open_pane(n), win.pane_open(n))[1]
                           for n in OTHER_FOUR)
    win.close_pane()
    print("VAULTOFF " + json.dumps(out))
    sys.stdout.flush()
    os._exit(0)


app, win = build(True)

opener = {"settings": win.open_settings,
          "downloads": win.open_downloads,
          "history": win.open_history,
          "bookmarks": win.open_bookmarks,
          "passwords": win.open_passwords}
toggler = {"settings": win.toggle_settings,
           "downloads": win.toggle_downloads,
           "history": win.toggle_history,
           "bookmarks": win.toggle_bookmarks,
           "passwords": win.toggle_passwords}
PAGES = [("settings", B.SETTINGS_PAGE), ("downloads", B.DOWNLOADS_PAGE),
         ("history", B.HISTORY_PAGE), ("bookmarks", B.BOOKMARKS_PAGE),
         ("passwords", B.PASSWORDS_PAGE)]


def spin(ms):
    """Let the browser and its renderers get on with it."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    """Run something in a pane's page and wait for the answer."""
    box = {}
    loop = QEventLoop()
    page.runJavaScript("(function(){" + code + "})()", B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


def tap_esc():
    """The key itself, into whatever has the focus — so Qt's shortcut
    map is what decides, exactly as it does in normal use. Nothing
    here calls the slot behind the shortcut: a shortcut left disabled,
    or one that never matches, must show up as a pane that stays."""
    QTest.keyClick(QApplication.focusWidget() or win, Qt.Key.Key_Escape)


def press_esc(wait=5.0):
    """Esc, and then wait for the pane to go. The pane asks its page
    what Esc means there before closing, so the answer comes a turn of
    the event loop later — and, for a page that never answers, no later
    than the fallback."""
    tap_esc()
    deadline = time.monotonic() + wait
    while win.pane_open() and time.monotonic() < deadline:
        spin(20)


print("\n(1) opening one of our own pages costs no tab")
win.new_tab(url="http://127.0.0.1:9/one")
app.processEvents()
before = win.tabs.count()
for name in PANES:
    opener[name]()
    app.processEvents()
    check("%s opens" % name, win.pane_open(name))
    check("%s spends no tab" % name, win.tabs.count() == before,
          "%d -> %d" % (before, win.tabs.count()))
win.close_pane()
app.processEvents()

print("\n(2) only one pane is ever on screen")
win.open_settings()
win.open_history()
app.processEvents()
check("the second one replaced the first", win.pane_open("history"))
check("and the first is down", not win._panes["settings"].isVisible())
up = [n for n, p in win._panes.items() if p.isVisible()]
check("exactly one pane visible", len(up) == 1, up)
win.close_pane()

print("\n(3) Esc closes the pane and leaves the tab underneath alone")
win.new_tab(url="http://127.0.0.1:9/underneath")
app.processEvents()
under = win.current()
under_url = under.url().toString() or getattr(under, "_requested", "")
tabs_before = win.tabs.count()
for name in PANES:
    opener[name]()
    app.processEvents()
    check("%s: Esc is armed while it is up" % name, win._pane_esc.isEnabled())
    press_esc()
    app.processEvents()
    check("%s: Esc closed it" % name, not win.pane_open())
    check("%s: Esc is disarmed again" % name, not win._pane_esc.isEnabled())
    check("%s: same tab underneath" % name, win.current() is under)
    now = win.current().url().toString() or getattr(under, "_requested", "")
    check("%s: and it is where it was" % name, now == under_url,
          "%r -> %r" % (under_url, now))
    check("%s: no tab gained or lost" % name,
          win.tabs.count() == tabs_before,
          "%d -> %d" % (tabs_before, win.tabs.count()))

print("\n(4) the shortcut that opened it closes it")
for name in PANES:
    toggler[name]()
    app.processEvents()
    opened = win.pane_open(name)
    toggler[name]()
    app.processEvents()
    check("%s toggles both ways" % name, opened and not win.pane_open(name),
          "opened=%s still=%s" % (opened, win.pane_open(name)))

print("\n(5) none of the five is ever saved as a tab")
for name in PANES:
    opener[name]()
    app.processEvents()
win._save_groups()
app.processEvents()
saved = json.loads(B.CONFIG_FILE.read_text()).get("sessionTabs") or {}
flat = []
for items in saved.values():
    for item in items:
        flat.append(item.get("u", "") if isinstance(item, dict) else item)
check("something was saved at all", bool(flat), flat)
for name, page in PAGES:
    hit = [u for u in flat if B._same_page(u, page)]
    check("no %s in sessionTabs" % name, not hit, hit)
win.close_pane()

print("\n(6) a session saved by an older version does not restore one")
for name, page in PAGES:
    check("a saved %s tab is dropped on the way in" % name,
          win._restore_url(page.toString()) is None,
          win._restore_url(page.toString()))
check("a saved passwords tab with last run's key is dropped too",
      win._restore_url(win.passwords_url()) is None,
      win._restore_url(win.passwords_url()))
check("_is_pane_url knows all five",
      all(B._is_pane_url(p) for _, p in PAGES))
check("and does not swallow a real site",
      not B._is_pane_url(QUrl("https://example.com/settings.html")))
check("an ordinary tab still restores",
      win._restore_url("https://example.com/") == "https://example.com/")
check("and an empty one still means a fresh start page",
      win._restore_url("") == "")

print("\n(7) a link out of a pane opens a real tab, and drops the pane")
win.open_bookmarks()
app.processEvents()
count = win.tabs.count()
win.leave_pane(QUrl("https://example.com/somewhere"))
app.processEvents()
check("the pane went down", not win.pane_open())
for _ in range(50):
    app.processEvents()
check("and a tab opened for it", win.tabs.count() == count + 1,
      "%d -> %d" % (count, win.tabs.count()))

print("\n(8) with Vault Password off, the passwords pane does not open")
r = subprocess.run([sys.executable, str(HERE / "test_panes.py"), "--vaultoff"],
                   capture_output=True, text=True, timeout=300)
line = [ln for ln in r.stdout.splitlines() if ln.startswith("VAULTOFF ")]
off = json.loads(line[0][len("VAULTOFF "):]) if line else {}
check("the off-run reported at all", bool(off), r.stdout[-400:] + r.stderr[-400:])
check("Vault Password really is off", off.get("on") is False, off)
check("the pane did not open", off.get("paneOpen") is False, off)
check("no pane opened at all", off.get("anyPane") is False, off)
check("it was not even built", off.get("built") is False, off)
check("and it cost no tab", off.get("tabs0") == off.get("tabs1"),
      "%s -> %s" % (off.get("tabs0"), off.get("tabs1")))
check("Ctrl+Shift+P does nothing either",
      off.get("toggleOpened") is False, off)
check("still not built", off.get("builtAfterToggle") is False, off)
check("the other four still open with it off",
      off.get("otherFour") is True, off)

print("\n(9) Esc belongs to the page before it belongs to the pane")


def open_and_settle(name, ms=3500):
    """Open a pane and wait for its page to be there to talk to."""
    opener[name]()
    spin(ms)
    return win._panes[name].view.page()


# -- the password entry he is halfway through typing
page = open_and_settle("passwords")
check("the passwords page is loaded",
      js(page, "return document.readyState;") == "complete")
check("and it says what Esc means to it",
      js(page, "return typeof window.__paneEsc;") == "function")
js(page, """
  document.getElementById("newbtn").click();
  const b = document.querySelectorAll("#newmenu button");
  if (b.length) b[0].click();
  return 1;
""")
spin(400)
check("the new-login editor is open",
      js(page, "return editing && editing.type;") == "login")
js(page, 'document.querySelectorAll(".panel input")[0].focus(); return 1;')
spin(200)
QTest.keyClicks(QApplication.focusWidget() or win, "hunter")
spin(300)
check("and it has what he typed in it",
      js(page, "return editing && editing.title;") == "hunter",
      js(page, "return JSON.stringify(editing);"))
tap_esc()
spin(700)
check("Esc: the pane is still up", win.pane_open("passwords"))
check("Esc: the editor closed", js(page, "return editing;") is None)
check("Esc: and what he typed was not thrown away",
      js(page, "return escDraft && escDraft.title;") == "hunter",
      js(page, "return JSON.stringify(escDraft);"))
js(page, """
  document.getElementById("newbtn").click();
  document.querySelectorAll("#newmenu button")[0].click();
  return 1;
""")
spin(400)
check("and it comes back when he opens the entry again",
      js(page, 'return document.querySelectorAll(".panel input")[0].value;')
      == "hunter")
tap_esc()
spin(700)
check("the second Esc puts that editor away too",
      win.pane_open("passwords"))
press_esc()
check("and the third closes the pane", not win.pane_open())

# -- the settings search box
page = open_and_settle("settings")
js(page, 'document.getElementById("navfilter").focus(); return 1;')
spin(200)
QTest.keyClicks(QApplication.focusWidget() or win, "prox")
spin(300)
check("the settings search box has something in it",
      js(page, 'return document.getElementById("navfilter").value;') == "prox")
tap_esc()
spin(700)
check("Esc: the settings pane is still up", win.pane_open("settings"))
check("Esc: the box is empty",
      js(page, 'return document.getElementById("navfilter").value;') == "",
      js(page, 'return document.getElementById("navfilter").value;'))
press_esc()
check("and the next Esc closes settings", not win.pane_open())

# -- the bookmark being renamed
win.bookmarks = [{"id": 1, "type": "link", "title": "Example",
                  "url": "https://example.com/", "icon": "", "parent": 0,
                  "t": 0}]
page = open_and_settle("bookmarks")
js(page, "beginEdit(1); return 1;")
spin(300)
check("a bookmark is being renamed", js(page, "return editing;") == 1)
tap_esc()
spin(700)
check("Esc: the bookmarks pane is still up", win.pane_open("bookmarks"))
check("Esc: the rename was dropped", js(page, "return editing;") == 0)
press_esc()
check("and the next Esc closes bookmarks", not win.pane_open())

# -- with nothing contextual open, all five still close on one Esc
for name in PANES:
    opener[name]()
    spin(2500)
    press_esc()
    check("%s: one Esc still closes it" % name, not win.pane_open())
    check("%s: and Esc is disarmed again" % name,
          not win._pane_esc.isEnabled())

print("\n(10) a pane whose page never answers goes down anyway")
page = open_and_settle("history", 2500)
# the question goes out and nothing ever comes back: a wedged renderer,
# a page that threw, a document swapped underneath the pane
page.runJavaScript = lambda *a, **k: None
began = time.monotonic()
press_esc()
took = (time.monotonic() - began) * 1000
del page.runJavaScript
check("the pane closed with no answer at all", not win.pane_open())
check("and it did not take long about it",
      took < 4 * B.PANE_ESC_MS, "%.0f ms" % took)
check("nor did it close before it had asked", took >= B.PANE_ESC_MS - 30,
      "%.0f ms" % took)

# and the question it never answered cannot come back to close whatever
# is up by the time the fallback fires
page = open_and_settle("downloads", 2500)
page.runJavaScript = lambda *a, **k: None
tap_esc()
del page.runJavaScript
win.open_bookmarks()
spin(int(B.PANE_ESC_MS * 3))
check("an Esc left in the air does not close the next pane",
      win.pane_open("bookmarks"))
press_esc()
check("which still closes on an Esc of its own", not win.pane_open())

print("\n(11) Re-run setup lands on the start page, wizard and all")
win.config["newTabUrl"] = "http://127.0.0.1:9/his-own-new-tab"
before = win.tabs.count()
page = open_and_settle("settings")
js(page, 'document.getElementById("rerunsetup").click(); return 1;')
spin(5000)
check("the settings pane stepped aside", not win.pane_open())
check("and one tab opened for it", win.tabs.count() == before + 1,
      "%d -> %d" % (before, win.tabs.count()))
opened = win.tabs.widget(win.tabs.count() - 1)
check("on the start page, not the page he set for new tabs",
      B._same_page(opened.url(), B.START_PAGE), opened.url().toString())
check("with the wizard actually running",
      js(opened.page(),
         'return document.getElementById("wizard").classList'
         '.contains("open");') is True)
check("and the flag was consumed, so it cannot ambush him later",
      win._setup_flag is False, win._setup_flag)

print("\nnothing anywhere near the real vault")
check("this test never opened it",
      str(B.CONFIG_FILE).startswith(str(SCRATCH)), B.CONFIG_FILE)

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
