#!/usr/bin/env python3
"""The buttons at the top are his to choose.

Covers, in the browser rather than in a docstring:

  * the default set is today's toolbar, to the button and in order
  * every removable button goes away and comes back, and a button that
    is away is off the layout rather than sitting there invisible
  * the four that cannot go do not go
  * a hidden button's keyboard shortcut still works, and the drop-down
    it used to hang off still lands somewhere on the screen
  * order: a button moves along the bar and the layout follows
  * what he chose survives a restart - in a second process, reading
    the same config file off disk
  * a name the browser has never heard of in the saved list is dropped
    rather than crashed on
  * a button a later version adds appears rather than staying hidden
    for ever, and one he switched off stays off
  * the right-click menu, the settings page and the config all say the
    same thing
  * the right-click reaches the menu from a button and not only from
    the gap between two of them, which is where nobody aims
  * a toolbar change made outside an open settings page reaches it, and
    the next switch flipped on that page does not undo the change
  * a row's switch says what the bar says, after every way the bar can
    move from somewhere else
  * Vault Password switched off takes the key button off the bar there
    and then, and switching it on puts it back - no restart either way
  * the star's tooltip is re-said in his language the moment he picks
    one, rather than at the next navigation
  * a real click at a real coordinate on a row switches that button
    off, and again on - the row belonged to its up arrow, so the
    switch could not be reached with a mouse at all
  * a real click on an arrow reorders and leaves the switch alone,
    and the two are nowhere near each other on the screen
  * a row that cannot be switched off answers a click instead of
    ignoring it, and looks unswitchable before it is clicked

Offscreen, against a scratch config. Your own data is never opened.
"""
import inspect
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
from PyQt6.QtCore import Qt, QPoint, QPointF  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def build(cfg=None):
    B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    base = {"translateLang": "en", "vaultPassword": True,
            "restoreTabs": False}
    base.update(cfg or {})
    B.CONFIG_FILE.write_text(json.dumps(base))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.resize(1300, 900)
    # offscreen or not, a window nobody showed reports every widget in
    # it invisible - and then every check below passes for the wrong
    # reason
    win.show()
    app.processEvents()
    return app, win


def bar_names(win):
    """What is actually laid out in the row, left to right."""
    lay = win._navlay
    out = []
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if w is None:
            continue
        if w is win.urlbar:
            out.append("address")
            continue
        for name, btn in win._tb_buttons.items():
            if btn is w:
                out.append(name)
                break
    return out


# =====================================================================
# --child: the same config file, opened again by a process of its own
# =====================================================================
if len(sys.argv) > 2 and sys.argv[1] == "--child":
    B.CONFIG_FILE = Path(sys.argv[2])
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.resize(1300, 900)
    win.show()
    app.processEvents()
    print("CHILD " + json.dumps({
        "layout": win.toolbar_layout(),
        "bar": bar_names(win),
        "printVisible": win._print_btn.isVisible(),
        "starVisible": win.starbtn.isVisible(),
    }))
    sys.exit(0)


app, win = build()
print("(1) the default set is today's toolbar")
TODAY = ["back", "forward", "reload", "home", "address", "favorites",
         "proxy", "print", "translate"]
check("the bar is drawn exactly as it always was",
      bar_names(win) == TODAY, bar_names(win))
check("plus the star and the tab groups button",
      win.toolbar_layout() == TODAY + ["star", "tabgroups"],
      win.toolbar_layout())
check("the star is in the address bar", win.starbtn.isVisible())
check("the tab groups button is in the corner", win._book.isVisible())
check("and the config was written with it",
      json.loads(B.CONFIG_FILE.read_text())["toolbarButtons"]
      == TODAY + ["star", "tabgroups"])


print("\n(2) every removable button goes away and comes back")
for item in B.TOOLBAR_ITEMS:
    name = item["name"]
    if item["fixed"]:
        continue
    btn = win._tb_buttons[name]
    win.toggle_toolbar_button(name, False)
    app.processEvents()
    gone = (name not in win.toolbar_layout() and not btn.isVisible()
            and name not in bar_names(win))
    # off the layout, not merely invisible: a hidden widget that is
    # still in the row is a hole in the bar
    if item["place"] == "bar":
        gone = gone and btn.parent() is None
    win.toggle_toolbar_button(name, True)
    app.processEvents()
    back = (name in win.toolbar_layout() and btn.isVisible())
    check("%s goes and comes back" % name, gone and back,
          "gone=%s back=%s" % (gone, back))
win.reset_toolbar()
app.processEvents()
check("and after all that the shipped set comes back whole",
      bar_names(win) == TODAY, bar_names(win))
check("the corner widget is let go with the tab groups button",
      (win.toggle_toolbar_button("tabgroups", False),
       win.tabs.cornerWidget(Qt.Corner.TopLeftCorner) is None)[1])
win.toggle_toolbar_button("tabgroups", True)
win.toggle_toolbar_button("star", False)
app.processEvents()
check("and the address bar takes its margin back when the star goes",
      win.urlbar.textMargins().right() == 0)
win.toggle_toolbar_button("star", True)
app.processEvents()
check("and gives it up again when it returns",
      win.urlbar.textMargins().right() == 28)


print("\n(3) four of them do not go")
for name in ("back", "forward", "reload", "address"):
    win.toggle_toolbar_button(name, False)
    app.processEvents()
    check("%s stays" % name, name in win.toolbar_layout()
          and name in bar_names(win))
check("even asked for straight out",
      (win.set_toolbar_buttons(["translate"]),
       all(n in win.toolbar_layout()
           for n in ("back", "forward", "reload", "address")))[1],
      win.toolbar_layout())
win.reset_toolbar()
app.processEvents()
check("and reset puts the shipped set back", bar_names(win) == TODAY,
      bar_names(win))


print("\n(4) a button that is gone keeps its keyboard shortcut")
win.toggle_toolbar_button("print", False)
win.toggle_toolbar_button("home", False)
app.processEvents()
check("the print button is off the bar",
      "print" not in bar_names(win) and not win._print_btn.isVisible())
# Ctrl+P is a QShortcut on the window and never knew about the button
shortcuts = {s.key().toString(): s for s in win.findChildren(
    __import__("PyQt6.QtGui", fromlist=["QShortcut"]).QShortcut)}
check("Ctrl+P is still bound", "Ctrl+P" in shortcuts)
check("and still enabled", shortcuts["Ctrl+P"].isEnabled())
check("Alt+Home is still bound with the home button gone",
      "Alt+Home" in shortcuts and shortcuts["Alt+Home"].isEnabled())
# the menu it used to drop from has to land somewhere he can see
anchor = win._menu_anchor(win._print_btn)
urlpt = win.urlbar.mapToGlobal(win.urlbar.rect().bottomLeft())
check("and its menu drops off the address bar instead", anchor == urlpt,
      "%s vs %s" % (anchor, urlpt))
win.toggle_toolbar_button("print", True)
app.processEvents()
check("back on the bar, the menu drops off the button again",
      win._menu_anchor(win._print_btn)
      == win._print_btn.mapToGlobal(win._print_btn.rect().bottomLeft()))
win.toggle_toolbar_button("home", True)
# go_home still runs with no button to click
win.go_home()
app.processEvents()
check("and Alt+Home's action runs with the button gone", True)


print("\n(5) order")
win.reset_toolbar()
app.processEvents()
win.move_toolbar_button("home", 1)
app.processEvents()
check("a button steps along the bar",
      bar_names(win) == ["back", "forward", "reload", "address", "home",
                         "favorites", "proxy", "print", "translate"],
      bar_names(win))
win.move_toolbar_button("home", -1)
app.processEvents()
check("and steps back", bar_names(win) == TODAY, bar_names(win))
win.move_toolbar_button("back", -1)
app.processEvents()
check("the first button cannot go further left", bar_names(win) == TODAY)
win.move_toolbar_button("translate", 1)
app.processEvents()
check("nor the last further right", bar_names(win) == TODAY)
win.set_toolbar_buttons(["address", "back", "forward", "reload", "proxy",
                         "print", "translate", "star", "tabgroups"])
app.processEvents()
check("the address bar can lead", bar_names(win)[0] == "address",
      bar_names(win))


print("\n(6) a saved list the browser cannot make sense of")
win.config["toolbarButtons"] = ["back", "flux-capacitor", "address",
                                "reload", 7, None, "forward", "back"]
win.config["toolbarKnown"] = list(B.TOOLBAR_ORDER)
out = win.toolbar_layout()
check("a name it has never heard of is dropped",
      "flux-capacitor" not in out, out)
check("and so is anything that is not a name at all",
      all(isinstance(n, str) for n in out), out)
check("a name written twice appears once",
      out.count("back") == 1, out)
check("and what is left still opens a browser",
      (win.rebuild_toolbar(), "address" in bar_names(win))[1],
      bar_names(win))
win.config["toolbarButtons"] = "not a list at all"
check("a saved list that is not a list falls back to the shipped set",
      win.toolbar_layout(save=False) == TODAY + ["star", "tabgroups"],
      win.toolbar_layout(save=False))


print("\n(7) a button a later version adds")
# what an upgrade looks like: the saved list, and a "known" list from
# before this button existed
win.config["toolbarButtons"] = ["back", "forward", "reload", "home",
                                "address", "favorites", "proxy", "print",
                                "translate"]
win.config["toolbarKnown"] = [n for n in B.TOOLBAR_ORDER
                              if n not in ("star", "tabgroups")]
out = win.toolbar_layout(save=False)
check("a new button that ships switched on appears",
      "star" in out and "tabgroups" in out, out)
check("and lands where it belongs rather than on the end",
      out.index("star") > out.index("translate"), out)
win.config["toolbarButtons"] = ["back", "forward", "reload", "address"]
win.config["toolbarKnown"] = list(B.TOOLBAR_ORDER)
out = win.toolbar_layout(save=False)
check("a button he switched off stays off",
      "print" not in out and "home" not in out and "star" not in out, out)
win.config["toolbarButtons"] = ["back", "forward", "reload", "address"]
win.config["toolbarKnown"] = ["back", "forward", "reload", "address"]
out = win.toolbar_layout(save=False)
check("but a list from before any of them was offered gets them all",
      all(n in out for n in TODAY), out)
win.config["toolbarButtons"] = ["back", "forward", "reload", "address"]
del win.config["toolbarKnown"]
out = win.toolbar_layout(save=False)
check("and a list with no record of what it was offered keeps its word",
      "print" not in out and "home" not in out, out)


print("\n(8) the menu, the page and the config agree")
win.reset_toolbar()
win.toggle_toolbar_button("print", False)
win.toggle_toolbar_button("history", True)
app.processEvents()
saved = json.loads(B.CONFIG_FILE.read_text())["toolbarButtons"]
check("the config holds what he picked",
      saved == win.toolbar_layout(), saved)

menu = win.toolbar_menu()
labels = {win._tb_label(n): n for n in B.TOOLBAR_ORDER}
ticked, greyed = set(), set()
for act in menu.actions():
    # the bookmarks bar rides along in this menu and is not a button,
    # so it is not part of what the button list has to agree with
    if act.isSeparator() or not act.isCheckable():
        continue
    label = act.text()
    if label not in labels:
        continue
    if act.isChecked():
        ticked.add(label)
    if not act.isEnabled():
        greyed.add(label)
check("the menu ticks exactly what is on",
      {labels[t] for t in ticked} == set(win.toolbar_layout()),
      sorted(labels[t] for t in ticked))
check("and greys out exactly the four that cannot go",
      {labels[g] for g in greyed}
      == {"back", "forward", "reload", "address"}, sorted(greyed))
check("the whole list is on offer",
      len([a for a in menu.actions()
           if a.isCheckable() and a.text() in labels])
      == len(B.TOOLBAR_ORDER), len(menu.actions()))
menu.deleteLater()

s = json.loads(win.bridge.getSettings())
check("the settings page is handed the same order",
      s["toolbarButtons"] == win.toolbar_layout(), s["toolbarButtons"])
check("and the whole registry to draw",
      [i["name"] for i in s["toolbarItems"]] == list(B.TOOLBAR_ORDER))
check("with the fixed ones marked",
      {i["name"] for i in s["toolbarItems"] if i["fixed"]}
      == {"back", "forward", "reload", "address"})

# and the page itself, drawn
win.open_pane("settings")
pane = win._panes["settings"]
deadline = time.time() + 40


def js(code):
    out = {}
    pane.view.page().runJavaScript(code, lambda r: out.setdefault("r", r))
    end = time.time() + 30
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)
        if "r" in out:
            return out["r"]
    return "<timeout>"


while time.time() < deadline:
    app.processEvents()
    time.sleep(0.02)
    if js("!!document.getElementById('tbbar')"
          " && document.querySelectorAll('#tbbar .wrow').length > 0"):
        break
page_bar = js("[...document.querySelectorAll('#tbbar .wrow')]"
              ".map(r=>r.dataset.tb)")
page_hid = js("[...document.querySelectorAll('#tbhid .wrow')]"
              ".map(r=>r.dataset.tb)")
page_else = js("[...document.querySelectorAll('#tbelse .wrow')]"
               ".map(r=>r.dataset.tb)")
check("the page draws the bar in the order the browser draws it",
      page_bar == bar_names(win), "%s vs %s" % (page_bar, bar_names(win)))
check("the page's switched-off list is what is missing from it",
      set(page_hid) == {i["name"] for i in B.TOOLBAR_ITEMS
                        if i["place"] == "bar"} - set(page_bar),
      page_hid)
check("and the two that live elsewhere are listed apart",
      page_else == ["star", "tabgroups"], page_else)
check("nothing he cannot change offers a switch he can flip",
      js("[...document.querySelectorAll('#tbbar .wrow')]"
         ".filter(r=>r.querySelector('input').disabled)"
         ".map(r=>r.dataset.tb)")
      == ["back", "forward", "reload", "address"])
check("a switch flipped on the page reaches the chrome",
      (js("document.querySelector('#tbhid [data-tb=find] input').click()"),
       [app.processEvents() for _ in range(30)],
       "find" in bar_names(win))[2], bar_names(win))
check("and the page and the chrome still agree afterwards",
      js("[...document.querySelectorAll('#tbbar .wrow')]"
         ".map(r=>r.dataset.tb)") == bar_names(win))
win.close_pane()
app.processEvents()


print("\n(9) the right-click lands wherever he aims it")
win.reset_toolbar()   # aim at a button that is actually up there
app.processEvents()
# the menu itself is exec'd, which would sit there for ever with no
# one to click it, so the real handler steps aside and a spy takes the
# signal instead - what is being asked here is whether the signal is
# emitted at all, not what the menu says
win.navbar.customContextMenuRequested.disconnect(win._toolbar_menu)
asked = []
win.navbar.customContextMenuRequested.connect(lambda p: asked.append(p))
QContextMenuEvent = __import__("PyQt6.QtGui",
                               fromlist=["QContextMenuEvent"]
                               ).QContextMenuEvent
QPoint = __import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint


def right_click(widget, at):
    asked.clear()
    app.sendEvent(widget, QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, at, widget.mapToGlobal(at)))
    app.processEvents()
    return bool(asked)


check("on the bar itself", right_click(win.navbar, QPoint(200, 10)))
# a button does not swallow it: he will aim at an icon, not at the gap
check("on a button, which is where he will aim",
      right_click(win._print_btn, QPoint(5, 5)))
check("and on the one he cannot remove either",
      right_click(win._tb_buttons["back"], QPoint(5, 5)))
win.navbar.customContextMenuRequested.connect(win._toolbar_menu)

menu = win.toolbar_menu()
bmbar = [a for a in menu.actions() if a.text() == win._ui_str("bmBar")]
check("the bookmarks bar is offered here too, where he will look for it",
      len(bmbar) == 1 and bmbar[0].isCheckable())
# one question, asked in one place: the tick reads bookmarks_bar_on(),
# not the raw config key, so it cannot drift from what the bar is doing
check("ticked as the bar really is",
      bmbar and bmbar[0].isChecked() == win.bookmarks_bar_on())
check("and the bar is away until he asks for it",
      not win.bookmarks_bar_on() and not bmbar[0].isChecked())
menu.deleteLater()


print("\n(10) it survives a restart")
win.reset_toolbar()
win.toggle_toolbar_button("print", False)
win.toggle_toolbar_button("star", False)
win.toggle_toolbar_button("newtab", True)
win.move_toolbar_button("newtab", -1)
app.processEvents()
wanted = win.toolbar_layout()
shared = SCRATCH / "restart-config.json"
shared.write_text(B.CONFIG_FILE.read_text())
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
res = subprocess.run([sys.executable, str(HERE / "test_toolbar.py"),
                      "--child", str(shared)],
                     capture_output=True, text=True, env=env, timeout=300)
line = [ln for ln in res.stdout.splitlines() if ln.startswith("CHILD ")]
check("the second run comes up at all", bool(line),
      res.stdout[-400:] + res.stderr[-400:])
if line:
    got = json.loads(line[0][6:])
    check("with the buttons he picked, in his order",
          got["layout"] == wanted, "%s vs %s" % (got["layout"], wanted))
    check("the one he took away is still gone",
          not got["printVisible"] and "print" not in got["bar"])
    check("the star he took away is still gone", not got["starVisible"])
    check("and the one he added is still where he put it",
          got["bar"].index("newtab") < got["bar"].index("home"),
          got["bar"])

print("\n(11) the settings page hears about a toolbar it did not change")
# The right-click menu works while Settings is up. A page that read the
# toolbar once at load draws the wrong ticks from then on, and the whole
# order it posts back on the next switch puts the menu's change back.
win.reset_toolbar()
app.processEvents()
win.open_pane("settings")
pane = win._panes["settings"]


def settle(pred, secs=25):
    """Pump until the page has caught up, or give up saying so."""
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
        try:
            if pred():
                return True
        except Exception:
            pass
    return False


def rows():
    """Every toolbar row the page is drawing, and whether it is ticked."""
    got = js("JSON.stringify([...document.querySelectorAll('.wrow[data-tb]')]"
             ".map(r=>[r.dataset.tb, !!r.querySelector('input').checked]))")
    try:
        return dict(json.loads(got))
    except (TypeError, ValueError):
        return {}


check("the page draws its toolbar at all",
      settle(lambda: len(rows()) == len(B.TOOLBAR_ORDER)), rows())
check("and every row starts out saying what the toolbar says",
      all(on == (name in win.toolbar_layout())
          for name, on in rows().items()), rows())

# the right-click menu, used while the page is up
win.toggle_toolbar_button("find", True)
app.processEvents()
check("the menu put Find on the bar", "find" in bar_names(win), bar_names(win))
check("and the open page hears about it rather than being asked to guess",
      settle(lambda: rows().get("find") is True), rows())
check("with Find drawn on the bar and not in the hidden list",
      js("[...document.querySelectorAll('#tbbar .wrow')].map(r=>r.dataset.tb)")
      == bar_names(win))

# ...and now a switch flipped on the page, which used to post the whole
# list the page loaded with and take Find back off
js("document.querySelector('#tbhid [data-tb=downloads] input').click()")
check("a switch on the page still reaches the chrome",
      settle(lambda: "downloads" in bar_names(win)), bar_names(win))
check("and it did not drop what the menu had added, in the chrome",
      "find" in bar_names(win), bar_names(win))
saved = json.loads(B.CONFIG_FILE.read_text()).get("toolbarButtons", [])
check("nor on disk", "find" in saved and "downloads" in saved, saved)
check("the page and the chrome still agree afterwards",
      settle(lambda: js("[...document.querySelectorAll('#tbbar .wrow')]"
                        ".map(r=>r.dataset.tb)") == bar_names(win)),
      bar_names(win))


print("\n(12) a row's tick is never the opposite of the truth")
# Every way the toolbar can move from outside the page, one at a time,
# and after each one every row on the page has to say what the bar says.
for name, on in (("history", True), ("print", False), ("star", False),
                 ("tabgroups", False), ("history", False), ("star", True)):
    win.toggle_toolbar_button(name, on)
    app.processEvents()
    live = win.toolbar_layout()
    ok = settle(lambda: rows() and all(
        t == (n in live) for n, t in rows().items()))
    check("after %s went %s, every row agrees with the bar"
          % (name, "on" if on else "off"), ok,
          {n: (t, n in live) for n, t in rows().items() if t != (n in live)})
win.reset_toolbar()
app.processEvents()
check("and after the whole lot is put back", settle(
    lambda: rows() and all(t == (n in win.toolbar_layout())
                           for n, t in rows().items())), rows())


print("\n(13) Vault Password takes the key button with it, now")
# A button with nothing behind it is worse than no button - and worse
# again when it has vanished from both places he could take it off from.
win.set_toolbar_buttons(list(B.TOOLBAR_DEFAULT) + ["passwords"])
app.processEvents()
key = win._tb_buttons["passwords"]
check("the key button is up there to start with",
      "passwords" in bar_names(win) and key.isVisible(), bar_names(win))
check("and the page draws a row for it",
      settle(lambda: "passwords" in rows()), sorted(rows()))

win.bridge.setSetting("vaultPassword", json.dumps(False))
app.processEvents()
check("switching the vault off takes it off the layout",
      "passwords" not in bar_names(win), bar_names(win))
check("and hides it, rather than leaving it there doing nothing",
      not key.isVisible())
menu = win.toolbar_menu()
check("the right-click menu no longer offers it",
      not any(a.text() == win._ui_str("tbPasswords") for a in menu.actions()))
menu.deleteLater()
check("nor does the settings page",
      settle(lambda: "passwords" not in rows()), sorted(rows()))
check("but the saved list still remembers it",
      "passwords" in win.config.get("toolbarButtons", []),
      win.config.get("toolbarButtons"))

win.bridge.setSetting("vaultPassword", json.dumps(True))
app.processEvents()
check("switching it back on brings the button back, with no restart",
      "passwords" in bar_names(win) and key.isVisible(), bar_names(win))
check("and the page gets its row back too",
      settle(lambda: rows().get("passwords") is True), sorted(rows()))

# The key button is the only one in the registry on a condition. Any
# other put on one has this same bug waiting for it - whatever flips
# the condition has to rebuild the toolbar - so both halves of that are
# said out loud here, and go off if a second one is added.
with_vault = {i["name"] for i in B.TOOLBAR_ITEMS
              if win._tb_available(i["name"])}
win.bridge.setSetting("vaultPassword", json.dumps(False))
app.processEvents()
without = {i["name"] for i in B.TOOLBAR_ITEMS if win._tb_available(i["name"])}
win.bridge.setSetting("vaultPassword", json.dumps(True))
app.processEvents()
check("with a vault, nothing in the registry is held back",
      with_vault == set(B.TOOLBAR_ORDER), sorted(set(B.TOOLBAR_ORDER)
                                                 - with_vault))
check("and the key button is the only one the vault decides",
      with_vault - without == {"passwords"} and not without - with_vault,
      sorted(with_vault ^ without))
check("_tb_available still puts exactly one name on a condition - "
      "a second needs its switch to rebuild the toolbar too",
      inspect.getsource(win._tb_available).count("if name == ") == 1)
win.close_pane()
app.processEvents()


print("\n(14) the star's tooltip follows a language change")
# relabel_toolbar skips the star, because only _sync_star knows whether
# it is going to add or remove. Skipped and not asked, the one tooltip
# that says what the button will do stayed a language behind until he
# next navigated somewhere.
win.toggle_toolbar_button("star", True)
app.processEvents()
seen = []
# three switches in a row, which is how it was caught: the tooltip has
# to be re-said every time, not once and then never again
for lang in ("en", "de", "en", "de"):
    win.config["translateLang"] = lang
    win.apply_language()
    app.processEvents()
    want = win._ui_str("bmRemove" if win._bookmark_for(win._bookmarkable())
                       else "bmAdd")
    got = win.starbtn.toolTip()
    seen.append(got)
    check("in %s the star says so at once, without a navigation" % lang,
          got == want, "%r vs %r" % (got, want))
check("and it really did move, and keep moving, and not settle",
      seen[0] != seen[1] and seen[0] == seen[2] and seen[1] == seen[3], seen)


print("\n(15) the row is switched by clicking it, and moved by aiming")
# Every check in here drives a real press and release at a real
# coordinate, because the whole bug was about where things are on the
# screen and nothing calling onclick() by hand could have seen it.
#
# What it was: a row is a <label>, and a <label> with no for= takes the
# first labelable element inside it as its control. <button> is
# labelable. The up and down arrows were built into the row ahead of
# the checkbox, so the row's control was the up arrow - and a click
# anywhere on the row, the middle of the switch included, moved the
# button up the bar instead of switching it off. Nothing a mouse could
# hit reached the switch.
win.config["translateLang"] = "en"   # (14) left it in German
win.apply_language()
win.reset_toolbar()
app.processEvents()
win.open_pane("settings")
pane = win._panes["settings"]
# an offscreen window nobody showed reports every element in it at
# 0x0, and then every coordinate below is 0 and every hit-area check
# passes without measuring anything
check("the settings pane is really on the screen, so a coordinate means "
      "something", pane.view.isVisible() and pane.view.width() > 0)


def goto_toolbar():
    """The rail shows one section at a time; a hidden one has no size.

    The click is re-issued until the section it asks for is the one
    really showing, rather than sent once and hoped for. A click that
    lands on a document being replaced is thrown away with it - and it
    still answers 'ok', because it did find the button, in the page
    that is about to go."""
    end = time.time() + 25
    while time.time() < end:
        js("""(() => {
          const tb = document.querySelector('#tbbar');
          if (!tb) return 'no toolbar section yet';
          for (const b of document.querySelectorAll('#sidebar button'))
            if (b._sec === tb.closest('section')) { b.onclick(); return 'ok'; }
          return 'no rail button';
        })()""")
        if settle(lambda: rect("#tbbar .wrow") is not None, secs=2):
            return True
    return False


def page_still(quiet=1.0):
    """True once no reload of this page is still in flight.

    Stamp the live document and see whether the stamp is still there a
    moment later: a document that replaced it has no stamp. Coordinates
    read off a page that is about to be replaced are measured
    honestly and then clicked at in the wrong document."""
    end = time.time() + 25
    while time.time() < end:
        stamp = "still-%.6f" % time.time()
        js("window.__stamp = %r" % stamp)
        until = time.time() + quiet
        while time.time() < until:
            app.processEvents()
            time.sleep(0.02)
        if js("window.__stamp || ''") == stamp:
            return True
    return False


def rect(sel):
    """Where something actually is, in the page's own coordinates."""
    got = js("(() => { const e = document.querySelector(%s); return e"
             " ? JSON.stringify(e.getBoundingClientRect().toJSON())"
             " : 'null'; })()" % json.dumps(sel))
    try:
        r = json.loads(got)
    except (TypeError, ValueError):
        return None
    return None if not r or not r["width"] else r


def click(x, y):
    """A press and a release, where a finger would land."""
    target = pane.view.focusProxy()
    for typ in (QMouseEvent.Type.MouseButtonPress,
                QMouseEvent.Type.MouseButtonRelease):
        gp = target.mapToGlobal(QPoint(int(x), int(y)))
        app.sendEvent(target, QMouseEvent(
            typ, QPointF(x, y), QPointF(x, y), QPointF(gp),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton
            if typ == QMouseEvent.Type.MouseButtonPress
            else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    app.processEvents()


def click_middle(sel):
    """Dead centre of something, which is where anyone aims."""
    r = rect(sel)
    if r is None:
        print("       (nothing measurable at %s - no click was sent)" % sel)
        return False
    click(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2)
    return True


def scroll_to(sel):
    js("(() => { const e = document.querySelector(%s);"
       " if (e) e.scrollIntoView({block: 'center'}); return 'ok'; })()"
       % json.dumps(sel))
    settle(lambda: (rect(sel) or {}).get("y", -1) >= 0)


settle(lambda: len(rows()) == len(B.TOOLBAR_ORDER))
check("no reload of the page is still in flight, so a coordinate read "
      "now is still there to be clicked", page_still())
check("and the Toolbar section is the one the rail is showing",
      goto_toolbar())

# --- the cause itself, named, so it cannot come back quietly
ctrl = js("""JSON.stringify([...document.querySelectorAll('#tbbar .wrow')]
  .filter(r => r.tagName === 'LABEL')
  .map(r => [r.dataset.tb, r.control ? r.control.tagName + ':'
       + (r.control.type || r.control.textContent) : 'none']))""")
try:
    ctrl = dict(json.loads(ctrl))
except (TypeError, ValueError):
    ctrl = {}
check("a switchable row's label belongs to its own switch, not to an arrow",
      ctrl and all(v == "INPUT:checkbox" for v in ctrl.values()), ctrl)

# --- (a) a click on the row, clear of every control, switches it off
scroll_to("#tbbar .wrow[data-tb=home]")
before = bar_names(win)
check("Start page is on the bar to begin with", "home" in before, before)
check("a click in the middle of its row - on no control at all - "
      "takes the button off the bar",
      click_middle("#tbbar .wrow[data-tb=home]")
      and settle(lambda: "home" not in bar_names(win)), bar_names(win))
check("and it took it off rather than shuffling the order",
      [n for n in before if n != "home"] == bar_names(win), bar_names(win))
check("the page moved it to the not-shown list to match",
      settle(lambda: rect("#tbhid .wrow[data-tb=home]") is not None))

# --- and again, to put it back
scroll_to("#tbhid .wrow[data-tb=home]")
check("a click on the row again puts the button back on the bar",
      click_middle("#tbhid .wrow[data-tb=home]")
      and settle(lambda: "home" in bar_names(win)), bar_names(win))
check("and the page and the chrome still say the same thing",
      settle(lambda: js("[...document.querySelectorAll('#tbbar .wrow')]"
                        ".map(r=>r.dataset.tb)") == bar_names(win)),
      bar_names(win))

# --- (b) a click on an arrow reorders, and leaves the switch alone
win.reset_toolbar()
app.processEvents()
goto_toolbar()
scroll_to("#tbbar .wrow[data-tb=home]")
before = bar_names(win)
check("a click on the down arrow moves the button along the bar",
      click_middle("#tbbar .wrow[data-tb=home] .warr button:last-child")
      and settle(lambda: bar_names(win) != before), bar_names(win))
check("and does not switch it off on the way",
      "home" in bar_names(win), bar_names(win))
check("it moved one place, over the address bar", bar_names(win)
      == ["back", "forward", "reload", "address", "home", "favorites",
          "proxy", "print", "translate"], bar_names(win))
scroll_to("#tbbar .wrow[data-tb=home]")
back_up = bar_names(win)
check("and the up arrow brings it back, still switched on",
      click_middle("#tbbar .wrow[data-tb=home] .warr button:first-child")
      and settle(lambda: bar_names(win) == before)
      and "home" in bar_names(win), bar_names(win))
check("neither arrow left the row's switch off",
      js("document.querySelector('#tbbar .wrow[data-tb=home] input').checked")
      is True)

# A disabled arrow fires no click, so the handler that says "not the
# switch, the arrow" never runs for one. That used to be the second
# way in: the row would fall back on its label, and its label was the
# arrow. Aimed at the last row's dead down arrow, nothing may happen.
check("the last row's down arrow is disabled, being the last",
      js("document.querySelector('#tbbar .wrow[data-tb=translate]"
         " .warr button:last-child').disabled") is True)
scroll_to("#tbbar .wrow[data-tb=translate]")
before = bar_names(win)
click_middle("#tbbar .wrow[data-tb=translate] .warr button:last-child")
app.processEvents()
time.sleep(0.4)
app.processEvents()
check("clicking it moves nothing", bar_names(win) == before, bar_names(win))
check("and does not switch the button off either",
      "translate" in bar_names(win), bar_names(win))

# --- (c) hit areas: the arrow is nowhere near the switch
win.reset_toolbar()
app.processEvents()
goto_toolbar()
scroll_to("#tbbar .wrow[data-tb=print]")
# whatever buttons the row has, however they are wrapped - the question
# is where they are, not what they are called
boxes = js("""JSON.stringify({
  btns: [...document.querySelectorAll('#tbbar .wrow[data-tb=print] button')]
          .map(b => b.getBoundingClientRect().toJSON()),
  sw: document.querySelector('#tbbar .wrow[data-tb=print] .wsw')
        .getBoundingClientRect().toJSON(),
  name: document.querySelector('#tbbar .wrow[data-tb=print] .wname')
        .getBoundingClientRect().toJSON(),
  row: document.querySelector('#tbbar .wrow[data-tb=print]')
        .getBoundingClientRect().toJSON()})""")
try:
    boxes = json.loads(boxes)
except (TypeError, ValueError):
    boxes = {}
arrows, swr = boxes.get("btns", []), boxes.get("sw")
check("the row really has both arrows and a switch, with a real size on "
      "a shown window",
      len(arrows) == 2 and all(a["width"] > 0 and a["height"] > 0
                               for a in arrows)
      and swr and swr["width"] > 0, boxes)
gaps = [swr["x"] - a["right"] for a in arrows] if arrows and swr else []
check("no arrow overlaps the switch", gaps and all(g > 0 for g in gaps), gaps)
# 18px was the old gap, and 18px is one thumb's slip on the way to a
# 42px switch. The two belong at opposite ends of the row.
check("nor abuts it - there is a whole row between them",
      gaps and min(gaps) >= 200, gaps)
check("the arrows sit at the leading edge, ahead of the button's name",
      arrows and all(a["right"] <= boxes["name"]["x"] for a in arrows),
      [a["right"] for a in arrows] if arrows else None)
check("and the switch is still the last thing in the row",
      swr and swr["right"] <= boxes["row"]["right"])

# --- (d) a row that cannot be switched off is not a dead row
scroll_to("#tbbar .wrow[data-tb=back]")
check("a fixed row says so in its class, for the styling to hang off",
      "fixed" in (js("document.querySelector("
                     "'#tbbar .wrow[data-tb=back]').className") or ""))
check("and its switch is visibly not his to move, before he clicks it",
      float(js("getComputedStyle(document.querySelector("
               "'#tbbar .wrow[data-tb=back] .wsw')).opacity") or 1) < 0.75)
check("while a switchable row's switch is not dimmed",
      float(js("getComputedStyle(document.querySelector("
               "'#tbbar .wrow[data-tb=print] .wsw')).opacity") or 0) == 1.0)
said_before = js("document.querySelector('#tbbar .wrow[data-tb=back]"
                 " .wsub').textContent")
before = bar_names(win)
click_middle("#tbbar .wrow[data-tb=back]")
app.processEvents()
check("a click on it does not take the button off the bar",
      settle(lambda: bar_names(win) == before) and "back" in bar_names(win),
      bar_names(win))
check("and it answers rather than ignoring him in silence",
      settle(lambda: js("document.querySelector('#tbbar .wrow[data-tb=back]"
                        " .wsub').textContent") != said_before),
      js("document.querySelector('#tbbar .wrow[data-tb=back] .wsub')"
         ".textContent"))
check("what it says is that it can be moved but not taken away",
      js("document.querySelector('#tbbar .wrow[data-tb=back] .wsub')"
         ".textContent") == win._ui_str("tbFixedWhy"))
check("the row is lit while it says it",
      "say" in (js("document.querySelector("
                   "'#tbbar .wrow[data-tb=back]').className") or ""))
check("a fixed row can still be moved along the bar",
      click_middle("#tbbar .wrow[data-tb=back] .warr button:last-child")
      and settle(lambda: bar_names(win)[0] != "back"), bar_names(win))

# --- (e) the same shape, anywhere else in Settings
# A <label> row that ends up owning a button instead of its switch is
# not a toolbar problem; it is a problem with putting a control in a
# label. Nowhere else in the page may have one.
stray = js("""JSON.stringify([...document.querySelectorAll('label')]
  .filter(l => l.control && !(l.control.tagName === 'INPUT'
      && (l.control.type === 'checkbox' || l.control.type === 'radio')))
  .map(l => (l.className || l.tagName) + ' -> ' + l.control.tagName))""")
check("no label anywhere in Settings is switched by anything but a switch",
      stray in ("[]", None), stray)
win.reset_toolbar()
app.processEvents()
win.close_pane()
app.processEvents()


print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
