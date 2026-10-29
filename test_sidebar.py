#!/usr/bin/env python3
"""The tabs down the side have to be the same tabs.

A vertical tab sidebar is cheap to draw and expensive to get wrong,
because it is a *second* picture of a thing that already has one. The
failure that matters is not a crash -- it is a sidebar that is quietly
one tab, one title or one folded group behind the strip, which looks
like a browser losing tabs.

So almost every check in here is the same shape: ask the sidebar what
it is showing, ask the QTabWidget what is actually open, and fail if
they differ. The rail reads the tab bar on every paint rather than
keeping a model of its own, which is what makes that answerable at all.

The one thing it cannot read off a signal is a title, an icon, a badge
or a loading line: those change in a hundred places across browser.py
and none of them emit anything. That is what the fingerprint tick is
for, and it is checked here by changing a title behind the sidebar's
back and asking whether it caught up.

Offscreen, against scratch data. Your own config is never touched.
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

B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "vaultPassword": True}))

from tests.harness import app, spin  # noqa: E402
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

qapp = app()
win = B.Browser()
win.show()
spin(600)


def rail_indices():
    """The tab indices the rail is showing, top to bottom."""
    return [row["i"] for row in win.sidebar.rail.rows()]


def visible_indices():
    """The tab indices the strip is showing. The rail has to match
    this exactly -- same set, same order."""
    bar = win.tabs.tabBar()
    return [i for i in range(win.tabs.count()) if bar.isTabVisible(i)]


print("\n(1) along the top by default, and the strip is the strip")
check("the rail is built either way", win.sidebar is not None)
check("...but off until he asks", win.tab_sidebar_on() is False)
check("...and not on screen", win.sidebar.isVisible() is False)
check("the horizontal strip is visible", win.tabs.tabBar().isVisible())
check("the strip is on top", win.config.get("tabStrip", "top") == "top")

print("\n(2) it is the strip, moved -- not a second one")
win.toggle_tab_sidebar(True)
spin(300)
check("the rail is on", win.tab_sidebar_on() is True)
check("...and on screen", win.sidebar.isVisible() is True)
check("the Qt tab bar is hidden", win.tabs.tabBar().isVisible() is False)
check("...which is what _apply_strip_visibility now answers",
      win._apply_strip_visibility() is False)
check("it went through the one door that places the strip",
      win.config.get("tabStrip") == "left", win.config.get("tabStrip"))
check("...so Qt's own position went with it, for a mode to restore",
      win.tabs.tabPosition() == B.QTabWidget.TabPosition.West,
      win.tabs.tabPosition())
check("the rail is on the left of the outer splitter",
      win._shell.indexOf(win.sidebar) == 0)
win.tab_strip_place("right")
spin(250)
check("down the right puts it on the other side",
      win._shell.indexOf(win.sidebar) == 1
      and win.sidebar.isVisible() is True,
      win._shell.indexOf(win.sidebar))
win.tab_strip_place("bottom")
spin(250)
check("below the page is the strip again, not the rail",
      win.sidebar.isVisible() is False
      and win.tabs.tabBar().isVisible() is True)
win.tab_strip_place("left")
spin(250)
check("and back to the rail", win.sidebar.isVisible() is True)

print("\n(3) the rail shows the tabs that are open, in order")
for url in ("https://example.com/one", "https://example.net/two",
            "https://example.org/three"):
    win.new_tab(url=url)
spin(400)
win.sidebar.relayout()
check("one row per visible tab, same order",
      rail_indices() == visible_indices(),
      "rail=%s strip=%s" % (rail_indices(), visible_indices()))
check("...and there are some", len(rail_indices()) >= 4,
      len(rail_indices()))
check("every row is a real tab, no group pills yet",
      all(row["tab"] is not None for row in win.sidebar.rail.rows()))

print("\n(4) a group is a pill in the rail, and folding it folds the rail")
first = win.tabs.widget(win.tabs.currentIndex())
# _register_group directly: _tab_to_new_group asks for a name in a
# modal dialog, which offscreen is a test that never comes back
win._register_group("Reading", "#89b4fa", at=win.tabs.indexOf(first))
first.group = "Reading"
spin(300)
win.sidebar.relayout()
group = win.groups[0] if win.groups else None
check("the group exists", group is not None, group)
pills = [r for r in win.sidebar.rail.rows() if r["tab"] is None]
check("its pill is a row in the rail", len(pills) == 1,
      [r["group"] for r in pills])
check("the member row knows its group",
      any(r["tab"] is not None and r["group"] == group
          for r in win.sidebar.rail.rows()))
before = len(rail_indices())
win._toggle_collapse(group)
spin(200)
check("folding it takes the member out of the rail",
      len(rail_indices()) < before, "%d -> %d" % (before, len(rail_indices())))
check("...and the rail still agrees with the strip",
      rail_indices() == visible_indices())
check("...and the pill stays",
      any(r["tab"] is None for r in win.sidebar.rail.rows()))
win._toggle_collapse(group)
spin(200)
check("unfolding brings it back", len(rail_indices()) == before)

print("\n(5) another virtual browser is another set of tabs")
win.sessions.append({"name": "Browser 2", "sid": "test2"})
win.switch_session("test2")
spin(400)
check("the rail follows the session", rail_indices() == visible_indices(),
      "rail=%s strip=%s" % (rail_indices(), visible_indices()))
check("...and shows fewer tabs than the first one had",
      len(rail_indices()) < before, len(rail_indices()))
win.switch_session("main")
spin(300)
check("and back", rail_indices() == visible_indices())

print("\n(6) a click in the rail picks that tab")
rows = win.sidebar.rail._layout()
tabrows = [(r, rect) for r, rect in rows if r["tab"] is not None]
check("there is something to click", len(tabrows) >= 2, len(tabrows))
if len(tabrows) >= 2:
    target, rect = tabrows[-1]
    want = target["i"]
    win.tabs.setCurrentIndex(tabrows[0][0]["i"])
    spin(100)
    QTest.mouseClick(win.sidebar.rail, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     QPoint(rect.x() + 40, rect.center().y()))
    spin(250)
    check("the clicked row became the current tab",
          win.tabs.currentIndex() == want,
          "wanted %d, got %d" % (want, win.tabs.currentIndex()))

print("\n(7) the cross on a row closes that tab")
rows = [(r, rect) for r, rect in win.sidebar.rail._layout()
        if r["tab"] is not None and not getattr(r["tab"], "pinned", False)]
if rows:
    target, rect = rows[-1]
    count = win.tabs.count()
    was = len(rail_indices())
    box = win.sidebar.rail._close_box(rect)
    win.tabs.setCurrentIndex(target["i"])   # the cross shows on this row
    spin(150)
    QTest.mouseClick(win.sidebar.rail, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, box.center())
    spin(400)
    # "fewer", not "one fewer": closing the last tab of a group takes
    # the group's pill with it, which is close_tab's own behaviour and
    # is exactly what the rail should show
    check("the tab went", win.tabs.count() < count,
          "%d -> %d" % (count, win.tabs.count()))
    check("...and the rail lost its row", len(rail_indices()) < was,
          "%d -> %d" % (was, len(rail_indices())))
    check("...without the rail and the strip drifting apart",
          rail_indices() == visible_indices())

print("\n(8) nothing a tab says about itself gets lost")
view = None
for i, candidate in win._real_tabs(session="main"):
    if win._group_of(candidate) is None:
        view = candidate
        break
if view is not None:
    i = win.tabs.indexOf(view)
    view._badge = 4
    view._asleep = True
    view._progress = 40
    view._changed = True
    spin(50)
    pix = QPixmap(win.sidebar.rail.size())
    try:
        win.sidebar.rail.render(pix)
        drew = True
    except Exception as exc:                      # noqa: BLE001
        drew = False
        print("    render raised:", exc)
    check("a row with every mark on it still paints", drew)
    view._badge = 0
    view._asleep = False
    view._progress = None
    view._changed = False

print("\n(9) the fingerprint tick catches what no signal reports")
if view is not None:
    i = win.tabs.indexOf(view)
    win.sidebar.relayout()                        # fingerprint is now level
    check("level after a redraw", win.sidebar.poke() is False)
    # straight onto the QTabWidget, the way a page's own title change
    # reaches the strip -- no signal of ours fires for this
    win.tabs.setTabText(i, "a title nobody announced")
    check("a title changed behind its back wakes it",
          win.sidebar.poke() is True)
    check("...and it is level again afterwards",
          win.sidebar.poke() is False)

print("\n(10) folded, it is favicons and 46 pixels")
win.fold_tab_sidebar(True)
spin(300)
check("it says it is folded", win.sidebar.folded is True)
check("...the rail knows too", win.sidebar.rail._folded() is True)
check("...and it is 46 wide, not 200",
      win.sidebar.maximumWidth() == B.SIDEBAR_FOLDED,
      win.sidebar.maximumWidth())
check("the same rows are still in it", rail_indices() == visible_indices())
pix = QPixmap(max(1, win.sidebar.rail.width()),
              max(1, win.sidebar.rail.height()))
try:
    win.sidebar.rail.render(pix)
    folded_drew = True
except Exception as exc:                          # noqa: BLE001
    folded_drew = False
    print("    render raised:", exc)
check("...and it paints folded", folded_drew)
win.fold_tab_sidebar(False)
spin(200)
check("unfolding gives the width back",
      win.sidebar.maximumWidth() == B.SIDEBAR_MAX,
      win.sidebar.maximumWidth())

print("\n(11) the keyboard has somewhere to go")
win.focus_tab_strip()
check("F6 lands on the rail, not on a hidden strip",
      win.sidebar.rail.hasFocus() is True)
at = win.tabs.currentIndex()
win.focus_tab_strip(1)
check("...and the arrows walk the list",
      win.tabs.currentIndex() != at or len(rail_indices()) < 2,
      "%d -> %d" % (at, win.tabs.currentIndex()))

print("\n(12) it is in the one table that feeds keys, palette and Settings")
ids = {entry["id"]: entry for entry in win.actions_list()}
check("the sidebar action is registered", "tabsidebar" in ids)
check("...with F9", ids.get("tabsidebar", {}).get("key") == "F9",
      ids.get("tabsidebar", {}).get("key"))
check("the fold action is registered", "sidebarfold" in ids)
check("...with Shift+F9", ids.get("sidebarfold", {}).get("key") == "Shift+F9",
      ids.get("sidebarfold", {}).get("key"))
for key in ("actTabSidebar", "actSidebarFold", "tabWhereName",
            "tabWhereHint", "tabWhereTop", "tabWhereBottom",
            "tabWhereLeft", "tabWhereRight"):
    check("%s reads in both languages" % key,
          bool(B.UI_STRINGS["en"].get(key))
          and bool(B.UI_STRINGS["de"].get(key)))
# getSettings answers the page, so it answers JSON
settings = json.loads(win.bridge.getSettings())
check("the settings page is told where the strip is",
      settings.get("tabStrip") in ("top", "bottom", "left", "right"),
      settings.get("tabStrip"))
check("...and how wide a side strip is",
      isinstance(settings.get("tabStripWidth"), int),
      settings.get("tabStripWidth"))

print("\n(13) one width, not two")
win.tab_strip_place("left")
spin(200)
check("the side strip's own width setting drives the rail",
      win.set_tab_strip_width(260) == 260
      and win.sidebar.sizeHint().width() == 260,
      win.sidebar.sizeHint().width())
check("...and a silly width is pulled back the same way it always was",
      win.set_tab_strip_width(9000) == B.SIDEBAR_MAX)
check("...and there is no second width key",
      "sidebarWidth" not in win.config, list(win.config)[:0] or "clean")

print("\n(14) switching it off puts the strip back")
win.toggle_tab_sidebar(False)
spin(300)
check("the rail is off", win.tab_sidebar_on() is False)
check("...and off screen", win.sidebar.isVisible() is False)
check("the horizontal strip is back", win.tabs.tabBar().isVisible() is True)
check("...and the tabs are all still there",
      len(win._real_tabs(session="main")) >= 1,
      len(win._real_tabs(session="main")))

print("\n(15) fullscreen and auto-hide take it away, and give back one strip")
win.tab_strip_place("left")
spin(250)
check("the rail is on to start with", win.sidebar.isVisible() is True)
win.set_fullscreen(True)
spin(250)
check("fullscreen hides the rail", win.sidebar.isVisible() is False)
check("...and the strip stays hidden too",
      win.tabs.tabBar().isVisible() is False)
win.set_fullscreen(False)
spin(300)
check("leaving fullscreen brings the rail back",
      win.sidebar.isVisible() is True)
check("...and NOT the horizontal strip as well",
      win.tabs.tabBar().isVisible() is False)
win.show_chrome(False)
spin(200)
check("auto-hide takes the rail with the chrome",
      win.sidebar.isVisible() is False)
win.show_chrome(True)
spin(200)
check("...and gives back exactly one strip",
      win.sidebar.isVisible() is True
      and win.tabs.tabBar().isVisible() is False)
win.tab_strip_place("top")
spin(200)
win.set_fullscreen(True)
spin(200)
win.set_fullscreen(False)
spin(250)
check("with the tabs on top, fullscreen still gives the strip back",
      win.tabs.tabBar().isVisible() is True
      and win.sidebar.isVisible() is False)

print("\n(16) F9 puts it back on the side it came off")
win.tab_strip_place("right")
spin(200)
win.toggle_tab_sidebar()                     # off
spin(200)
check("off goes to the top", win.config.get("tabStrip") == "top",
      win.config.get("tabStrip"))
win.toggle_tab_sidebar()                     # and on again
spin(200)
check("...and on goes back to the right, not to the left",
      win.config.get("tabStrip") == "right", win.config.get("tabStrip"))
check("...on the right-hand side of the splitter",
      win._shell.indexOf(win.sidebar) == 1)

print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
