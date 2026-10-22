#!/usr/bin/env python3
"""Keyboard, mouse and gestures, part two: the keys a site keeps, the
keys he never means to press, two-step keys, the address bar as a
terminal, a text box in his own editor, vim keys on a page, and what the
mouse does.

Offscreen, scratch data, local server. The editor is a stub script in
the scratch directory, so the round trip is proven without opening kitty.
"""
import json
import os
import stat
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
from PyQt6.QtCore import QUrl  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<title>Keys and mouse</title><body>
  <a id="link" href="/one">a link to follow</a>
  <img id="pic" src="/pic.png">
  <input id="f"><textarea id="t"></textarea>
  <p>some words to select</p>
  <div style="height:3000px"></div>
</body>"""
PAGES = {"/p": PAGE, "/one": "<title>One</title><p>one</p>",
         "/two": "<title>Two</title><p>two</p>"}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 740)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
APP = B.APP_WORLD_ID
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(800)


def js(code, world=APP, v=None):
    return H.js(v or view, code, world)


def ask(call, *args, **kw):
    wait = kw.pop("wait", 6000)
    got = []
    kw["then"] = got.append
    call(*args, **kw)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


print("\n(1) the keys he never means to press")
check("the guard list starts empty", win.key_guard_list() == [],
      win.key_guard_list())
check("a key can be guarded", win.set_key_guard("F1") is True)
check("...and it says so", win.key_guarded("F1") is True)
check("...and another key is not", win.key_guarded("F2") is False)
check("...and it can be taken off", win.set_key_guard("F1") is False)
check("an empty key is not a key", win.set_key_guard("") is False)

print("\n(2) the keys a site keeps")
check("a site can keep one", win.set_keys_through("127.0.0.1", "Ctrl+K")
      is True)
check("...and it is listed for that site",
      win.site_keys_through("127.0.0.1") == ["Ctrl+K"],
      win.site_keys_through("127.0.0.1"))
check("...and a sub-domain of it too",
      win.site_keys_through("sub.127.0.0.1") == ["Ctrl+K"],
      win.site_keys_through("sub.127.0.0.1"))
check("...and another site keeps nothing",
      win.site_keys_through("example.com") == [])
H.load(view, srv.url("/p"))
H.spin(800)
check("the page is told the table of keys sites keep",
      "Ctrl+K" in (js("JSON.stringify((window.__navWant||{})"
                      ".keysThroughRows||{})", APP) or ""),
      js("JSON.stringify((window.__navWant||{}).keysThroughRows||{})",
         APP))
check("...and it recognises that key",
      js("""window.__navKeysThrough({ctrlKey: true, altKey: false,
            shiftKey: false, key: 'k'})""", APP) is True)
check("...and not another", js("""window.__navKeysThrough({ctrlKey: true,
      altKey: false, shiftKey: false, key: 'j'})""", APP) is False)
check("it can be given back", win.set_keys_through("127.0.0.1", "Ctrl+K")
      is False)

print("\n(3) one shortcut off on one site")
check("a shortcut can be switched off here",
      win.set_key_off_here("newtab", "127.0.0.1") is True)
check("...and the browser knows not to run it",
      win.key_allowed_here("newtab", view) is False)
check("...while another shortcut still runs",
      win.key_allowed_here("reload", view) is True)
check("...and on another site it runs too",
      win.site_keys_off("example.com") == [])
check("it can be switched back on",
      win.set_key_off_here("newtab", "127.0.0.1") is False)

print("\n(4) two-step keys, and doing it again")
check("a letter can be bound", win.set_key_sequence("b", "bookmark")
      == "bookmark")
check("...and it is in the table", win.key_sequences() == {"b": "bookmark"},
      win.key_sequences())
check("the leader starts the wait", win.start_key_sequence() is True)
check("...and the browser is waiting",
      getattr(win, "_chord_waiting", False) is True)
check("...and the letter runs it",
      win.finish_key_sequence("b") == "bookmark")
check("...and the wait is over",
      getattr(win, "_chord_waiting", True) is False)
check("a letter with nothing on it says so",
      win.start_key_sequence() and win.finish_key_sequence("q") == "")
check("a letter with no leader does nothing",
      win.finish_key_sequence("b") == "")
check("doing it again repeats the last one",
      win.repeat_last_action() == "bookmark")
check("a letter can be unbound",
      win.set_key_sequence("b", "") == "")

print("\n(5) the keys that need more than one press")
check("Ctrl+Q once only asks", win.hold_to_quit() is False)
check("...twice in a moment means it", win.hold_to_quit() is True)
win._quit_asked = 0
check("...and a long wait makes it ask again",
      win.hold_to_quit() is False)
check("the quit action is the asking one, not a bare close",
      any(row["id"] == "quit"
          and row["run"].__name__ == "hold_to_quit"
          for row in win.actions_list()),
      [row["run"].__name__ for row in win.actions_list()
       if row["id"] == "quit"])

print("\n(6) the tabs, by number and by order")
second = win.new_tab(url=None)
H.load(second, srv.url("/two"))
H.spin(700)
third = win.new_tab(url=None)
H.load(third, srv.url("/one"))
H.spin(700)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(300)
check("a virtual browser can be reached by number",
      win.goto_session_number(1) is True)
check("...and one that is not there is refused",
      win.goto_session_number(9) is False)
rows = win.recent_tab_order()
check("the tabs have a most-recently-used order", len(rows) >= 3, len(rows))
check("...with the one he is on first", rows[0] is view,
      win.tabs.tabText(win.tabs.indexOf(rows[0])))
win.config["mruTabs"] = True
check("Ctrl+Tab can follow that order", win.cycle_recent(1) is True)
check("...and it really went to the one before",
      win.current() is not view, win.tabs.currentIndex())
win.config["mruTabs"] = False
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(300)
check("a group's tabs can be cycled on their own",
      win.cycle_group_tabs(1) is True)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(300)
was = win.tabs.currentIndex()
check("a peek goes to the tab he was on", win.peek_tab(True) is True)
check("...which is a different tab", win.tabs.currentIndex() != was,
      (was, win.tabs.currentIndex()))
check("...and letting go comes back", win.peek_tab(False) is True)
check("...to where he was", win.tabs.currentIndex() == was,
      (was, win.tabs.currentIndex()))
check("a peek with nothing to peek at says so", win.peek_tab(False) is False)

print("\n(7) the address bar as a terminal")
win.urlbar.setText("https://example.com/a/b/c")
win.urlbar.setCursorPosition(len(win.urlbar.text()))
check("Ctrl+W kills the word behind", win.readline_key("killword") is True)
check("...and really did", win.urlbar.text() == "https://example.com/a/b/",
      win.urlbar.text())
check("Ctrl+U kills the line", win.readline_key("killline") is True)
check("...and it is empty", win.urlbar.text() == "", win.urlbar.text())
win.urlbar.setText("one two three")
win.urlbar.setCursorPosition(4)
check("Ctrl+A goes to the start", win.readline_key("home") is True
      and win.urlbar.cursorPosition() == 0,
      win.urlbar.cursorPosition())
check("Ctrl+E goes to the end", win.readline_key("end") is True
      and win.urlbar.cursorPosition() == len("one two three"),
      win.urlbar.cursorPosition())
win.urlbar.setCursorPosition(len("one two three"))
check("Alt+B steps a word back", win.readline_key("wordback") is True
      and win.urlbar.cursorPosition() == len("one two "),
      win.urlbar.cursorPosition())
check("Alt+F steps a word forward",
      win.readline_key("wordforward") is True
      and win.urlbar.cursorPosition() >= len("one two "),
      win.urlbar.cursorPosition())
check("Ctrl+K kills to the end",
      win.readline_key("killend") is True)
check("a key that is not one of them is refused",
      win.readline_key("explode") is False)
win.urlbar.setText("")

print("\n(8) shortcuts that follow the key, not the letter")
check("undo is bound to both places it lives",
      win.layout_keys_for("undo", "Ctrl+Z") == ["Ctrl+Z", "Ctrl+Y"],
      win.layout_keys_for("undo", "Ctrl+Z"))
check("the quick find is bound to the German place too",
      "Ctrl+Shift+7" in win.layout_keys_for("quickfind", "Ctrl+/"),
      win.layout_keys_for("quickfind", "Ctrl+/"))
check("an action with no twin keeps its own key",
      win.layout_keys_for("newtab", "Ctrl+T") == ["Ctrl+T"],
      win.layout_keys_for("newtab", "Ctrl+T"))
win.config["layoutKeys"] = False
check("...and with the setting off, only his own key is bound",
      win.layout_keys_for("undo", "Ctrl+Z") == ["Ctrl+Z"],
      win.layout_keys_for("undo", "Ctrl+Z"))
win.config["layoutKeys"] = True

print("\n(9) a text box in his own editor, and text the page lost")
stub = scratch / "editor.sh"
stub.write_text("#!/bin/sh\nprintf 'from the editor' > \"$1\"\n")
stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
win.config["externalEditor"] = str(stub)
js("document.getElementById('f').focus()", MAIN)
js("document.getElementById('f').value = 'half a sentence'", MAIN)
H.spin(300)
check("the focused box goes to the editor",
      win.edit_in_editor(view=view) is True)
H.wait_for(lambda: js("document.getElementById('f').value", MAIN)
           == "from the editor", 8000)
check("...and what the editor wrote comes back",
      js("document.getElementById('f').value", MAIN) == "from the editor",
      js("document.getElementById('f').value", MAIN))
win.config["externalEditor"] = "/nowhere/editor"
check("an editor that is not installed says so",
      win.edit_in_editor(view=view) is False)
win.config["externalEditor"] = str(stub)
check("drafts are kept by default",
      js("(window.__navWant||{}).keepDrafts", APP) is True)
js("""(function(){
  var el = document.getElementById('t');
  el.value = 'a draft of something';
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.focus();
  return 'typed';})()""", APP)
H.spin(400)
check("...and the page really wrote one down",
      "draft of something" in (js(
          "sessionStorage.getItem('__formdraft') || ''", APP) or ""),
      js("sessionStorage.getItem('__formdraft') || ''", APP))
js("document.getElementById('t').value = ''", APP)
js("document.getElementById('t').focus()", APP)
H.spin(200)
got = ask(win.recover_form_text, view=view)
check("...and it can be brought back",
      "draft of something" in str(got or ""), got)
check("...into the box", "draft of something" in (js(
    "document.getElementById('t').value", MAIN) or ""),
    js("document.getElementById('t').value", MAIN))

print("\n(10) vim keys, and the gestures the page sees")
# the browser's own poll takes these every quarter second (which is how
# gt and / reach it at all), so it is stopped while the test reads them
win.watch_page_gestures(False)
check("vim keys can go on", win.set_vim_keys(True) is True)
H.load(view, srv.url("/p"))
H.spin(800)
check("...and the page is told", js("(window.__navWant||{}).vimKeys", APP)
      is True)
js("window.scrollTo(0, 0)", MAIN)
H.spin(200)
js("""document.dispatchEvent(new KeyboardEvent('keydown',
     {bubbles: true, key: 'j'}))""", APP)
H.spin(300)
check("...and j really scrolls", (js("window.scrollY|0", MAIN) or 0) > 0,
      js("window.scrollY|0", MAIN))
js("""document.dispatchEvent(new KeyboardEvent('keydown',
     {bubbles: true, key: 'G'}))""", APP)
H.spin(400)
check("...and G goes to the bottom",
      (js("window.scrollY|0", MAIN) or 0) > 1000,
      js("window.scrollY|0", MAIN))
js("""(function(){
  document.dispatchEvent(new KeyboardEvent('keydown',
    {bubbles: true, key: 'g'}));
  document.dispatchEvent(new KeyboardEvent('keydown',
    {bubbles: true, key: 'g'}));
  return 'gg';})()""", APP)
H.spin(400)
check("...and gg comes back to the top",
      (js("window.scrollY|0", MAIN) or 0) < 50,
      js("window.scrollY|0", MAIN))
js("""(function(){
  document.dispatchEvent(new KeyboardEvent('keydown',
    {bubbles: true, key: 'g'}));
  document.dispatchEvent(new KeyboardEvent('keydown',
    {bubbles: true, key: 't'}));
  return 'gt';})()""", APP)
H.spin(200)
check("...and gt asks the browser for the next tab",
      js("window.__navTakeTabStep()", APP) == 1,
      js("window.__navTakeTabStep()", APP))
js("""document.dispatchEvent(new KeyboardEvent('keydown',
     {bubbles: true, key: '/'}))""", APP)
H.spin(200)
check("...and / asks for the find bar",
      js("window.__navTakeFind()", APP) is True)
check("a key typed in a text box is left alone",
      js("""(function(){
        var el = document.getElementById('f');
        el.focus();
        var was = window.scrollY;
        el.dispatchEvent(new KeyboardEvent('keydown',
          {bubbles: true, key: 'j'}));
        return window.scrollY === was;})()""", APP) is True)
win.set_vim_keys(False)

win.watch_page_gestures(True)

print("\n(11) the mouse")
rows = win.mouse_config()
# three of them (tabDouble, tabMiddle, barDouble) were read by
# nothing and are gone; what is left is what the mouse really has
check("the mouse has its answers", len(rows) >= 8, sorted(rows))
check("middle-click autoscroll is off by default",
      rows["autoScroll"] is False)
check("...because middle-click pastes on this desktop", True)
check("hovering a tab while dragging is on by default",
      rows["hoverSwitch"] is True)
check("a switch can be set", win.set_mouse("superDrag", True) is True)
check("...and it reaches the page",
      (H.load(view, srv.url("/p")), H.spin(800),
       js("(window.__navWant||{}).superDrag", APP))[2] is True)
# The tab-strip clicks had two settings each and two implementations:
# mouse.tabDouble, read by tab_click_action, which the strip never
# called -- and tabDoubleClick, read by the strip's own event filter.
# The dead half is gone; this is the half that runs.
win.config["tabDoubleClick"] = "duplicate"
before = win.tabs.count()
check("a double-click on a tab does what he picked",
      win._strip_mouse("tabDoubleClick", "nothing",
                       win.tabs.indexOf(second)) is True)
check("...which made a tab", win.tabs.count() == before + 1,
      (before, win.tabs.count()))
win.close_tab(win.tabs.count() - 1)
win.config["tabMiddleClick"] = "close"
spare = win.new_tab(url=None)
H.spin(300)
before = win.tabs.count()
check("a middle-click closes a tab",
      win._strip_mouse("tabMiddleClick", "close",
                       win.tabs.indexOf(spare)) is True)
check("...and it is gone", win.tabs.count() == before - 1,
      (before, win.tabs.count()))
win.config["stripDoubleClick"] = "newtab"
before = win.tabs.count()
check("the empty strip opens a tab",
      win._strip_mouse("stripDoubleClick", "newtab", -1) is True
      and win.tabs.count() == before + 1,
      (before, win.tabs.count()))
win.close_tab(win.tabs.count() - 1)
check("and the dead pair is really gone",
      not hasattr(win, "tab_click_action")
      and not hasattr(win, "bar_click_action")
      and "tabDouble" not in win.mouse_config())
cfg = {"mouse": {"tabDouble": "pin"}}
B._migrate_tabclick_config(cfg)
check("...with what he picked in it handed to the one that works",
      cfg.get("tabDoubleClick") == "pin"
      and "tabDouble" not in cfg["mouse"], cfg)
check("a wheel step can be set", win.set_mouse("wheelStep", 120) == 120)
check("...and the page is told",
      (H.load(view, srv.url("/p")), H.spin(800),
       js("(window.__navWant||{}).wheelStep", APP))[2] == 120)
win.set_mouse("wheelStep", 0)
check("a dragged link opens in the background",
      win.super_drag(srv.url("/one"), kind="link") == srv.url("/one"))
check("dragged text is searched",
      "127.0.0.1" not in str(win.super_drag("some words", kind="text")),
      win.super_drag("some words", kind="text"))
check("a swipe goes back", win.swipe_navigate("back") == "back")
check("...and forward", win.swipe_navigate("forward") == "forward")
check("...and nothing else does anything",
      win.swipe_navigate("sideways") == "")
check("hovering a tab mid-drag switches to it",
      win.hover_switch(win.tabs.indexOf(second)) is True)
check("...and an index that is not a tab does not",
      win.hover_switch(999) is False)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
menu = win.gesture_help()
check("the gesture help is a list of what the mouse does",
      len(menu.actions()) >= 5, len(menu.actions()))
from PyQt6.QtGui import QGuiApplication
QGuiApplication.clipboard().setText(srv.url("/two"))
before = win.tabs.count()
check("a middle-click on the new-tab button opens the clipboard",
      win.clipboard_new_tab() == srv.url("/two"))
check("...as a tab", win.tabs.count() == before + 1,
      (before, win.tabs.count()))
win.close_tab(win.tabs.count() - 1)
QGuiApplication.clipboard().setText("some words to look up")
before = win.tabs.count()
out = win.clipboard_new_tab()
check("...and words on the clipboard are searched",
      bool(out) and "127.0.0.1" not in str(out), out)
win.close_tab(win.tabs.count() - 1)
QGuiApplication.clipboard().setText("")
got = ask(win.focus_first_field, view=view)
check("one key goes to the page's first text box",
      str(got or "") not in ("", "none"), got)
check("...and the caret is really in it",
      js("document.activeElement.tagName", APP) in ("INPUT", "TEXTAREA"),
      js("document.activeElement.tagName", APP))

print("\n(12) the window manager's keys, and a bound script")
check("the commands it may send are named",
      len(win.GLOBAL_COMMANDS) >= 10, sorted(win.GLOBAL_COMMANDS))
check("...each with a word", all(B.UI_STRINGS["en"].get(word)
                                for word in win.GLOBAL_COMMANDS.values()),
      [w for w in win.GLOBAL_COMMANDS.values()
       if not B.UI_STRINGS["en"].get(w)])
before = win.tabs.count()
check("a command really runs", win.run_global_command("new-tab")
      == "new-tab")
check("...and it did something", win.tabs.count() == before + 1)
win.close_tab(win.tabs.count() - 1)
check("raising the window is one of them",
      win.run_global_command("raise") == "raised")
check("a command that is not one answers nothing",
      win.run_global_command("make-coffee") == "")
binds = win.global_binds()
check("the binds for his hyprland.conf are printed",
      len(binds) == len(win.GLOBAL_COMMANDS), len(binds))
check("...as lines he can paste",
      all(one.startswith("bind = ") for one in binds), binds[:1])
(win.plugins_dir).mkdir(parents=True, exist_ok=True)
(win.plugins_dir / "zbound.user.js").write_text(
    "window.__boundRan = (window.__boundRan || 0) + 1;")
check("a key can run one of his scripts",
      win.run_bound_script("zbound.user.js", view=view) is True)
H.spin(500)
check("...and it really ran in the page",
      (js("window.__boundRan|0", MAIN) or 0) >= 1,
      js("window.__boundRan|0", MAIN))
check("a script that is not there says so",
      win.run_bound_script("nothing.user.js", view=view) is False)
(win.plugins_dir / "zbound.user.js").unlink()

print("\n(13) the context menu from a key")
check("the menu actions are named", len(win.MENU_ACTIONS) >= 6,
      sorted(win.MENU_ACTIONS))
js("""(function(){
  window.__navLastTarget = document.getElementById('link');
  return 'set';})()""", APP)
got = ask(win.menu_action, "copylink", view=view)
check("the link under the pointer can be copied",
      "/one" in str(got or ""), got)
got = ask(win.menu_action, "openlinktab", view=view)
check("...and opened in a tab", "/one" in str(got or ""), got)
win.close_tab(win.tabs.count() - 1)
js("""(function(){
  window.__navLastTarget = document.getElementById('pic');
  return 'set';})()""", APP)
got = ask(win.menu_action, "copyimage", view=view)
check("the picture's address can be copied",
      "pic.png" in str(got or ""), got)
check("a menu action that is not one is refused",
      win.menu_action("explode", view=view) is False)

print("\n(14) Settings, the menu and the words")
menu = win.key_menu(view=view)
rows = [a.text() for a in menu.actions() if a.text()]
for word in ("mouseSuperDrag", "mouseLasso", "keyVimName", "keyMru",
             "keyReadline", "keyEditor", "keyRecover", "keyRepeat"):
    check("the menu offers " + word, win._ui_str(word) in rows, rows[:5])
page_text = Path("settings.html").read_text()
for ident in ("layoutkeys", "mrutabs", "vimkeys", "readlinekeys",
              "keepdrafts", "keyguard", "keysthrough", "keysequences",
              "externaleditor", "boundscript", "mouseswitches",
              "tabdouble", "tabmiddle", "wheelstep",
              "keystep", "globalbinds"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text, ident)
check("...and they are bound", "bindKeys();" in page_text)
data = json.loads(win.bridge.getSettings())
for key in ("layoutKeys", "mruTabs", "vimKeys", "keyGuard", "keysThrough",
            "keySequences", "mouse", "globalBinds"):
    check("the page is told " + key, key in data, key)
registry = win.actions_list()
ids = [row["id"] for row in registry]
for ident in ("keymenu", "keyrepeat", "keychord", "keypeek",
              "keygroupcycle", "keyeditor", "keyrecover", "keyfirstfield",
              "keyscript", "mousemenu"):
    check("there is an action for " + ident, ident in ids, ident)
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
check("no two actions want the same key",
      {k: v for k, v in taken.items() if len(v) > 1} == {},
      {k: v for k, v in taken.items() if len(v) > 1})
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1][:4])
need = ["keyMenu", "keyGuardName", "keyThroughName", "keyThroughHere",
        "keyOffHere", "keyChordName", "keyChordWaiting", "keyNoLast",
        "keyRepeat", "keyQuitAgain", "keyGroupCycle", "keyPeek", "keyMru",
        "keyReadline", "keyEditor", "keyEditorName", "keyNoEditor",
        "keyNoField", "keyEditedBack", "keyRecover", "keyNoLostText",
        "keyDraftName", "keyScriptName", "keyScriptRan", "keyFirstField",
        "keyVimName", "keyGlobalName", "keyLayoutName", "mouseMenu",
        "mouseSuperDrag", "mouseLasso", "mouseSwipeNav",
        "mouseAutoScroll", "mouseHoverSwitch", "mouseTabDouble",
        "mouseAct_close", "mouseWheelStep", "mouseGestureHelp",
        "ctxOpenLinkTab", "ctxCopyLink", "descKeys"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
