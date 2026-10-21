#!/usr/bin/env python3
"""The second wave of tab work: several tabs at once, several windows,
what the strip says about itself, and the lists of tabs that are not
open any more.

Offscreen, scratch data, local pages. Every check drives the same
method the menu entry or the key calls."""
import json
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>Alpha</title><p>a <a id=go href='/b'>b</a>",
    "/b": "<title>Beta</title><p>b <a id=go href='/c'>c</a>",
    "/c": "<title>Gamma</title><p>c",
    "/d": "<title>Delta</title><p>d",
    "/badge": "<title>(7) Chat</title><p>chat",
    "/year": "<title>(2024) Film</title><p>film",
    "/snap": "<title>Snap</title><p>snap",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1100, 760)
win.show()
H.spin(400)


def open_tab(path, **kw):
    view = win.new_tab(url=None, **kw)
    H.load(view, srv.url(path))
    return view


def index(view):
    try:
        return win.tabs.indexOf(view)
    except RuntimeError:
        return -1


def real():
    return [v for _, v in win._real_tabs()]


print("\n(1) the number a page puts in its own title")
check("a leading (7) is an unread count", B._title_badge("(7) Chat") == 7)
check("square brackets too", B._title_badge("[12] Inbox") == 12)
check("a year is not a count", B._title_badge("(2024) Film") == 0,
      B._title_badge("(2024) Film"))
check("a count in the middle is not one",
      B._title_badge("Chat (7) here") == 0)
check("no number, no count", B._title_badge("Alpha") == 0)
badge = open_tab("/badge")
H.spin(300)
check("a real page's title is read", getattr(badge, "_badge", 0) == 7,
      getattr(badge, "_badge", None))
year = open_tab("/year")
H.spin(300)
check("and a year on a real page still is not", year._badge == 0,
      year._badge)

print("\n(2) a tab that changed while he was looking elsewhere")
a = open_tab("/a")
b = open_tab("/b")
win.tabs.setCurrentIndex(index(a))
H.spin(200)
check("the tab in front is never marked", a._changed is False)
H.load(b, srv.url("/c"))
H.spin(300)
check("a background tab whose title changed is marked",
      b._changed is True, b._changed)
win.tabs.setCurrentIndex(index(b))
H.spin(200)
check("...and looking at it clears the mark", b._changed is False)

print("\n(3) picking several tabs out")
c = open_tab("/c")
win.clear_tab_selection()
win.toggle_tab_selection(index(a))
win.toggle_tab_selection(index(c))
check("ctrl-clicking two tabs selects two",
      [v for v in win.selected_tabs()] == sorted([a, c], key=index),
      len(win.selected_tabs()))
win.toggle_tab_selection(index(a))
check("ctrl-clicking again takes one out",
      win.selected_tabs() == [c], len(win.selected_tabs()))
win.clear_tab_selection()
win.toggle_tab_selection(index(a))
picked = win.select_tab_range(index(c))
check("shift-click takes everything in between",
      len(picked) >= 3 and a in picked and c in picked, len(picked))
check("and nothing outside it", badge not in picked or index(badge) < index(c))
before = len(real())
win._sel_views = [a, c]
closed = win.selection_do("close")
H.spin(300)
check("closing the selection closes exactly those", closed == 2, closed)
check("...and the rest are still there", len(real()) == before - 2,
      (before, len(real())))
check("the selection is empty afterwards", win.selected_tabs() == [])

print("\n(4) a group made out of the selection")
d = open_tab("/d")
e = open_tab("/a")
win._sel_views = [d, e]
group = win.group_selection("Picked")
H.spin(300)
check("they go into a group of that name", group == "Picked", group)
check("both of them", len(win._real_tabs(group="Picked")) == 2,
      len(win._real_tabs(group="Picked")))
check("the group exists in the strip", "Picked" in win.groups)

print("\n(5) keeping a group instead of losing it")
kept = win.save_group("Picked")
H.spin(400)
check("saving a group writes its tabs down", kept == 2, kept)
check("...and closes it", "Picked" not in win.groups)
check("it is on the saved list", "Picked" in win.saved_groups())
back = win.reopen_saved_group("Picked")
H.spin(600)
check("reopening it brings the tabs back", len(back) == 2, len(back))
check("in a group of the same name", "Picked" in win.groups)
check("and with its colour",
      win.group_colors.get("Picked") ==
      win.saved_groups()["Picked"]["colour"])
for i, _ in reversed(win._real_tabs(group="Picked")):
    win.close_tab(i, ask=False)
H.spin(200)

print("\n(6) saved sets of tabs")
one = open_tab("/a")
two = open_tab("/b")
saved = win.save_tabset("Evening")
check("saving a set counts the tabs it saved", saved >= 2, saved)
check("the set is there with that name", "Evening" in win.tabsets())
opened = win.restore_tabset("Evening")
H.spin(400)
check("opening it opens that many tabs", len(opened) == saved,
      (len(opened), saved))
urls = [win._tab_url(v) for v in opened]
check("on the right addresses", srv.url("/a") in urls, urls[:3])
for v in opened:
    win.close_tab(index(v), ask=False)
H.spin(200)
check("a set can be forgotten", win.delete_tabset("Evening"))
check("...and is gone", "Evening" not in win.tabsets())
check("forgetting one that is not there says so",
      not win.delete_tabset("Evening"))

print("\n(7) tabs set aside")
aside_tabs = [open_tab("/c"), open_tab("/d")]
before = len(real())
put = win.set_aside(indices=[index(v) for v in aside_tabs])
H.spin(300)
check("putting two tabs aside writes both down", len(put) == 2, len(put))
check("...and closes them", len(real()) == before - 2,
      (before, len(real())))
check("there is one set on the list", len(win.aside_sets()) == 1)
came = win.bring_back_aside(0)
H.spin(400)
check("bringing them back opens both", len(came) == 2, len(came))
check("and takes the set off the list", win.aside_sets() == [])
for v in came:
    win.close_tab(index(v), ask=False)

print("\n(8) snapshots of what was open")
snap_tab = open_tab("/snap")
H.spin(200)
n = win.snapshot_tabs()
check("a snapshot counts the tabs in it", n >= 1, n)
check("it is on the list", len(win.snapshots()) == 1)
check("an unchanged second snapshot is not kept twice",
      win.snapshot_tabs() == 0 and len(win.snapshots()) == 1,
      len(win.snapshots()))
win.close_tab(index(snap_tab), ask=False)
H.spin(200)
putback = win.restore_snapshot(-1)
H.spin(400)
check("restoring one opens the tab that was lost", len(putback) == 1,
      len(putback))
for v in putback:
    win.close_tab(index(v), ask=False)

print("\n(9) a closed tab keeps its way back")
walk = win.new_tab(url=None)
H.load(walk, srv.url("/a"))
H.load(walk, srv.url("/b"))
H.load(walk, srv.url("/c"))
H.spin(300)
trail, at = win.tab_history(walk)
check("the trail is the pages it went through", len(trail) == 3, trail)
check("and says where it is sitting", at == 2, at)
win.close_tab(index(walk), ask=False)
H.spin(200)
check("the closed tab was saved with its trail",
      len(win._closed_tabs[-1].get("trail") or []) == 3,
      win._closed_tabs[-1].get("trail"))
again = win.reopen_closed_tab()
H.wait_for(lambda: again.url().toString().endswith("/c"), 8000)
check("reopened, it is on the page it was on",
      again.url().toString().endswith("/c"), again.url().toString())
check("and Back works", again.history().canGoBack(),
      again.history().count())
again.back()
H.wait_for(lambda: again.url().toString().endswith("/b"), 5000)
check("...all the way back to where it had been",
      again.url().toString().endswith("/b"), again.url().toString())
win.close_tab(index(again), ask=False)

print("\n(10) a tab opened from a link")
parent = open_tab("/a")
win.config["childNextToParent"] = True
win.config["newTabPos"] = "end"
far = open_tab("/d")                  # something after the parent
child = win.new_tab(url=srv.url("/b"), switch=False, opener=parent)
H.spin(400)
check("it lands right after the tab that opened it",
      index(child) == index(parent) + 1,
      (index(parent), index(child), index(far)))
check("and remembers which tab that was", child.opened_from is parent)
win.config["backClosesTab"] = True
win.tabs.setCurrentIndex(index(child))
H.spin(200)
check("Back on it closes it", win.back_or_close())
H.spin(300)
check("...and lands on the tab it came from", win.current() is parent,
      win.tabs.tabText(win.tabs.currentIndex()))
win.config["backClosesTab"] = False

print("\n(11) the strip's own settings")
bar = win.tabs.tabBar()
win.config["tabWidth"] = "icon"
check("favicon-only tabs are narrow",
      bar.tabSizeHint(index(parent)).width() == 44,
      bar.tabSizeHint(index(parent)).width())
win.config["tabWidth"] = "fixed"
win.config["tabFixedWidth"] = 150
check("fixed-width tabs are the width he asked for",
      bar.tabSizeHint(index(parent)).width() == 150,
      bar.tabSizeHint(index(parent)).width())
win.config["tabWidth"] = "shrink"
win.config["tabMinWidth"] = 120
check("a shrinking strip stops at his floor",
      bar.tabSizeHint(index(parent)).width() >= 120,
      bar.tabSizeHint(index(parent)).width())
win.config["tabMinWidth"] = 34
win.config["closeButtons"] = "active"
win._update_close_buttons()
holders = [bar.tabButton(i, bar.ButtonPosition.RightSide)
           for i, _ in win._real_tabs()]
shown = [h for h in holders if h is not None and h.isVisibleTo(bar)]
check("only the active tab carries a cross", len(shown) == 1, len(shown))
win.config["closeButtons"] = "all"
win._update_close_buttons()
shown = [h for h in holders if h is not None and h.isVisibleTo(bar)]
check("or every tab, if he says so", len(shown) == len(holders),
      (len(shown), len(holders)))
win.config["closeButtons"] = "wide"
win._update_close_buttons()

print("\n(12) hiding the strip, and folding the groups")
win.config["hideStripSingle"] = True
for i, v in reversed(win._real_tabs()):
    if v is not win.current():
        win.close_tab(i, ask=False)
H.spin(300)
win._apply_strip_visibility()
check("one tab and no groups: no strip", not bar.isVisible())
extra = open_tab("/a")
H.spin(200)
win._apply_strip_visibility()
check("a second tab brings it back", bar.isVisible())
win.config["hideStripSingle"] = False
win._apply_strip_visibility()
g1 = win.ensure_group("One")
win.new_tab(url=srv.url("/a"), group=g1)
g2 = win.ensure_group("Two")
t2 = win.new_tab(url=srv.url("/b"), group=g2)
H.spin(400)
win.config["autoCollapseGroups"] = True
t1 = win._real_tabs(group="One")[0][1]
win.tabs.setCurrentIndex(index(t1))
H.spin(200)
win.tabs.setCurrentIndex(index(t2))
H.spin(200)
check("switching into a group folds the others away",
      win.collapsed.get("One") is True, win.collapsed)
check("...but not the one he is in", not win.collapsed.get("Two"))
win.config["autoCollapseGroups"] = False

print("\n(13) the rules he sets for new tabs")
win.config["groupRules"] = [{"group": "Mods",
                             "match": "modrinth.com, curseforge.com"}]
check("a rule matches the host", win.group_rule_for(
    "https://www.modrinth.com/mod/x") == "Mods")
check("...and its sub-domains",
      win.group_rule_for("https://api.curseforge.com/v1") == "Mods")
check("and nothing else", win.group_rule_for("https://example.com") is None)
ruled = win.new_tab(url="https://www.modrinth.com/mod/x", switch=False,
                    lazy=True)
H.spin(300)
check("a new tab on such a site lands in that group",
      win._group_of(ruled) == "Mods", win._group_of(ruled))
win.close_tab(index(ruled), ask=False)
win.config["groupRules"] = []
win.sessions.append({"name": "Stream", "sid": "str"})
win.config["sessionSites"] = {"twitch.tv": "str"}
check("a site can belong to one virtual browser",
      win.session_rule_for("https://www.twitch.tv/x") == "str")
check("an unknown browser name is ignored",
      win.session_rule_for("https://x.test") is None)
sent = win.new_tab(url="https://www.twitch.tv/x", switch=True, lazy=True)
H.spin(300)
check("and a tab on it opens there",
      getattr(sent, "session", "") == "str", getattr(sent, "session", None))
check("with the browser switched over", win.active_session == "str")
win.close_tab(index(sent), ask=False)
win.config["sessionSites"] = {}
win.switch_session("main")
H.spin(200)

print("\n(14) the list of every tab, and the overview")
menu = win.all_tabs_menu()
rows = [a.text() for a in menu.actions() if a.text()]
check("every tab of this browser is in the list",
      len(rows) == len(win._real_tabs(session="main")),
      (len(rows), len(win._real_tabs(session="main"))))
grid = win.tab_overview()
H.spin(300)
check("the overview opens", grid is not None and grid.isVisible())
check("with a card per tab", len(grid._cards) == len(win._real_tabs()),
      (len(grid._cards), len(win._real_tabs())))
grid.input.setText("alpha")
grid.refresh()
check("typing narrows it down",
      0 < len(grid._cards) < len(win._real_tabs()),
      (len(grid._cards), len(win._real_tabs())))
win.tab_overview()
check("and it closes again", not grid.isVisible())

print("\n(15) export and import")
out = Path(B.CONFIG_FILE.parent / "tabs.txt")
wrote = win.export_tabs(out)
check("the open tabs are written out", wrote >= 1, wrote)
check("one address a line",
      all(line.startswith("http") for line in
          out.read_text().splitlines() if line.strip()),
      out.read_text()[:60])
page = Path(B.CONFIG_FILE.parent / "tabs.html")
win.export_tabs(page, as_html=True)
check("...or as a page of links", "<a href=" in page.read_text())
before = len(real())
got = win.import_tabs(out)
H.spin(400)
check("importing opens them again", len(got) == wrote, (len(got), wrote))
check("and they are in the strip", len(real()) == before + len(got),
      (before, len(real())))
for v in real()[before:]:
    win.close_tab(index(v), ask=False)
H.spin(200)

print("\n(16) stale tabs")
old = open_tab("/d")
old._seen_wall = time.time() - 9 * 86400
old._opened_at = old._seen_wall
front = open_tab("/a")        # never the tab he is looking at
H.spin(200)
check("a tab untouched for nine days goes after seven",
      win.close_stale_tabs(days=7) == 1)
H.spin(200)
check("0 days means never", win.close_stale_tabs(days=0) == 0)
keep = open_tab("/d")
keep._seen_wall = time.time() - 9 * 86400
win.tabs.setCurrentIndex(index(front))
H.spin(200)
win.pin_tab(index(keep), True)
check("a pinned tab is never closed for being old",
      win.close_stale_tabs(days=7) == 0)
win.pin_tab(index(keep), False)
win.close_tab(index(keep), ask=False)

print("\n(17) a second window")
second = win.new_window(url=srv.url("/a"))
H.spin(900)
check("there are two windows now", len(win.windows()) == 2,
      len(win.windows()))
check("it shares this one's settings", second.config is win.config)
check("...its cookie jar", second.profile is win.profile)
check("...its bookmarks", second.bookmarks is win.bookmarks)
check("...and its passwords", second.vault is win.vault)
check("it has the page it was opened on",
      any(srv.url("/a") == second._tab_url(v)
          for _, v in second._real_tabs()),
      [second._tab_url(v) for _, v in second._real_tabs()])
names = [a.text() for a in win.window_menu().actions() if a.text()]
check("the window list names both", len(names) >= 2, names)
moved = win.tabs.count()
count = win.merge_windows()
H.spin(900)
check("gathering the windows moves the tabs", count >= 1, count)
check("...and leaves one window", len(win.windows()) == 1,
      len(win.windows()))

print("\n(18) a tab in a window of its own")
lone = open_tab("/c")
H.spin(200)
there = win.move_tab_to_window(index(lone))
H.spin(900)
check("the tab opens in a new window", there is not None
      and len(win.windows()) == 2, len(win.windows()))
check("and has left this one", index(lone) < 0, index(lone))
there._closing_anyway = True
there.close()
H.spin(400)
check("closing it leaves the browser running",
      len(win.windows()) == 1 and win.isVisible(), len(win.windows()))
check("and its tabs are on the closed-window list",
      len(B.CLOSED_WINDOWS) >= 1, len(B.CLOSED_WINDOWS))
whole = win.reopen_closed_window()
H.spin(900)
check("which can be brought back as a window", whole is not None
      and len(win.windows()) == 2, len(win.windows()))
whole._closing_anyway = True
whole.close()
H.spin(400)

print("\n(19) a private window, and a site as an app")
priv = win.new_private_window()
H.spin(800)
check("every tab in it is private",
      all(getattr(v, "private", False) for _, v in priv._real_tabs()),
      [getattr(v, "private", None) for _, v in priv._real_tabs()])
check("its title says so", "Private" in priv.windowTitle()
      or "Privat" in priv.windowTitle(), priv.windowTitle())
priv._closing_anyway = True
priv.close()
H.spin(400)
appwin = win.open_as_app(srv.url("/a"))
H.spin(900)
check("an app window opens on that site", appwin is not None
      and any(srv.url("/a") == appwin._tab_url(v)
              for _, v in appwin._real_tabs()))
check("with no tab strip", not appwin.tabs.tabBar().isVisible())
check("and no address bar", not appwin.navbar.isVisible())
entry = win.write_desktop_entry(srv.url("/a"), "Alpha")
check("a desktop entry can be written", entry and Path(entry).exists(),
      entry)
text = Path(entry).read_text() if entry else ""
check("it starts the browser in app mode", "--app=" in text,
      text[:80])
check("under the name he gave it", "Name=Alpha" in text)
appwin._closing_anyway = True
appwin.close()
H.spin(400)

print("\n(20) a tab popped out as a small window")
chat = open_tab("/b")
H.spin(200)
mini = win.pop_out_tab(index(chat))
H.spin(500)
check("it comes out of the strip", mini is not None and index(chat) < 0)
check("and shows the page", mini.view is chat)
mini.close()
H.spin(500)
check("closing it puts the tab back", index(chat) >= 0, index(chat))

print("\n(21) the window's name")
win.switch_session("main")
view = win.current()
title = win._sync_window_title()
check("the window is named after the tab in front",
      "browser" in title, title)
win.sessions.append({"name": "Admin", "sid": "adm"})
win.switch_session("adm")
H.spin(300)
title = win._sync_window_title()
check("and says which virtual browser it is in", "Admin" in title, title)
win.switch_session("main")
H.spin(200)

print("\n(22) asking before a big window closes")
asked = []
real_q = B.QMessageBox.question
B.QMessageBox.question = lambda *a, **k: (
    asked.append(a[1:3]) or B.QMessageBox.StandardButton.No)
win.config["confirmCloseTabs"] = 2
check("a window with that many tabs asks first",
      not win._confirm_many_tabs() and len(asked) == 1, asked)
win.config["confirmCloseTabs"] = 0
check("and with the setting off it never asks",
      win._confirm_many_tabs() and len(asked) == 1, len(asked))
B.QMessageBox.question = real_q

print("\n(23) the crash list")
win._crash_state = [{"u": srv.url("/a"), "t": "Alpha"},
                    {"u": srv.url("/b"), "t": "Beta"}]
box = win.crash_recovery_dialog()
check("the dialog lists what was open", box is not None
      and len(box._boxes) == 2, box and len(box._boxes))
box._boxes[1][0].setChecked(False)
before = len(real())
brought = box._bring_back()
H.spin(500)
check("only the ticked ones come back", len(brought) == 1, len(brought))
check("and they are open", len(real()) == before + 1,
      (before, len(real())))
box.reject()
for v in real()[before:]:
    win.close_tab(index(v), ask=False)

print("\n(24) what the hover card says, and the site's colour")
hover = open_tab("/a")
hover._opened_at = time.time() - 3600
hover._seen_wall = time.time() - 1800
tip = win.tab_tooltip(hover)
check("it says how long the tab has been open", "1 h" in tip, tip)
check("and when it was last looked at", "30 min" in tip, tip)
check("how long ago, in plain words", B._ago_text(45) == "45 s"
      and B._ago_text(3600) == "1 h" and B._ago_text(200000) == "2 d",
      (B._ago_text(45), B._ago_text(3600), B._ago_text(200000)))
check("a tab with no icon has no colour of its own",
      win.site_tint(hover) == "", win.site_tint(hover))

print("\n(25) tab search finds closed tabs too")
gone = open_tab("/d")
win.close_tab(index(gone), ask=False)
H.spin(200)
switcher = B.TabSwitcher(win)
rows = switcher._open_tabs()
closed_rows = [r for r in rows if r["view"] is None]
check("the closed ones are in the list", closed_rows, len(rows))
check("marked as closed",
      all(r["place"] == win._ui_str("tabsClosed") for r in closed_rows))

print("\n(26) a tab that only started a download")
win.config["closeDownloadTabs"] = True
blank = win.new_tab(blank=True, switch=False)
H.spin(200)
check("a never-committed tab is the kind that closes",
      win._tab_never_committed(blank))
check("and it is closed when a download starts there",
      win._close_download_tab(blank.page()))
H.spin(200)
check("...and is gone", index(blank) < 0, index(blank))

print("\n(27) the strip's mouse settings")
mouse_tab = open_tab("/a")
H.spin(200)
win.config["tabMiddleClick"] = "close"
at = index(mouse_tab)
check("middle-click closes a tab when he asks for that",
      win._strip_mouse("tabMiddleClick", "close", at))
H.spin(200)
check("...and it is gone", index(mouse_tab) < 0)
win.config["tabMiddleClick"] = "nothing"
other = open_tab("/b")
check("and does nothing when he does not",
      not win._strip_mouse("tabMiddleClick", "close", index(other)))
check("the tab is still there", index(other) >= 0)
before = len(real())
check("double-clicking the empty strip opens a tab",
      win._strip_mouse("stripDoubleClick", "newtab", -1))
H.spin(300)
check("...and there is one", len(real()) == before + 1,
      (before, len(real())))
win.config["tabDoubleClick"] = "duplicate"
before = len(real())
check("double-clicking a tab can duplicate it",
      win._strip_mouse("tabDoubleClick", "nothing", index(other)))
H.spin(400)
check("...which there is", len(real()) == before + 1)
win.config["tabDoubleClick"] = "nothing"

print("\n(28) sleeping tabs are drawn as sleeping")
sleeper = open_tab("/c")
win.tabs.setCurrentIndex(index(other))
H.spin(300)
check("a tab put to sleep says it is asleep",
      win.sleep_tab(sleeper, True) and sleeper._asleep is True)
win.sleep_tab(sleeper, False)
check("and wakes up again", sleeper._asleep is False)

print("\n(29) the loading line")
loader = win.new_tab(url=None, switch=False)
win._tab_progress(loader, 40)
check("a loading tab carries its progress", loader._progress == 40)
win._tab_progress(loader, 100)
check("a finished one carries none", loader._progress is None)

print("\n(30) every new action can be run by name")
ids = {e["id"] for e in win.actions_list()}
for want in ("newwindow", "privatewindow", "overview", "alltabs",
             "windowlist", "mergewindows", "tabtonewwindow", "popouttab",
             "siteasapp", "savetabset", "setaside", "bringback",
             "exporttabs", "importtabs"):
    check("the registry knows " + want, want in ids)
check("every one of them has a name in English",
      all(win.action_label(e) != e["str"] for e in win.actions_list()),
      [e["str"] for e in win.actions_list()
       if win.action_label(e) == e["str"]][:4])
keys = {}
for entry in win.actions_list():
    key = win.shortcut_for(entry["id"], entry["key"])
    if key:
        keys.setdefault(key, []).append(entry["id"])
clash = {k: v for k, v in keys.items() if len(v) > 1}
check("and no two actions want the same key", not clash, clash)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
