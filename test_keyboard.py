#!/usr/bin/env python3
"""The keyboard and the mouse: the action registry every key is built
from, the command palette, the cheat sheet, remapping, and the gestures.

The registry is the thing worth testing hardest — a duplicate key or an
action that cannot be run by name is a bug in every one of the four
places that read it."""
import json
import os
import sys
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


app = H.app()
srv = H.Server({"/a": "<title>A</title><p>a", "/b": "<title>B</title><p>b",
                "/c": "<title>C</title><p>c"})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)

print("\n(1) the registry")
actions = win.actions_list()
check("there is a good number of actions", len(actions) > 60, len(actions))
check("every action has an id, a name, something to run and a key",
      all(e["id"] and e["str"] and callable(e["run"]) for e in actions))
ids = [e["id"] for e in actions]
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1][:4])
keys = {}
for e in actions:
    key = win.shortcut_for(e["id"], e["key"])
    if key:
        keys.setdefault(key, []).append(e["id"])
clashes = {k: v for k, v in keys.items() if len(v) > 1}
check("no two actions want the same key", not clashes, clashes)
check("every name is a real string, not a key that was never written",
      all(win.action_label(e) != e["str"] for e in actions),
      [e["str"] for e in actions if win.action_label(e) == e["str"]][:4])
check("the keys Tim already knows are still the ones in the list",
      {("newtab", "Ctrl+T"), ("closetab", "Ctrl+W"),
       ("address", "Ctrl+L"), ("find", "Ctrl+F"),
       ("passwords", "Ctrl+Shift+P"), ("private", "Ctrl+Shift+N")}
      <= {(e["id"], e["key"]) for e in actions})

print("\n(2) running an action by name")
before = win.tabs.count()
check("a new tab happens", win.run_action("newtab"))
H.spin(300)
check("...and there is one", win.tabs.count() == before + 1,
      (before, win.tabs.count()))
check("an action that does not exist is refused",
      not win.run_action("no-such-action"))

print("\n(3) a key he changed")
win.config["shortcuts"] = {"newtab": "Ctrl+Alt+N", "find": ""}
check("his key is the one used",
      win.shortcut_for("newtab", "Ctrl+T") == "Ctrl+Alt+N")
check("an empty one means the action has no key",
      win.shortcut_for("find", "Ctrl+F") == "")
check("everything else keeps its own",
      win.shortcut_for("closetab", "Ctrl+W") == "Ctrl+W")
win.config["shortcuts"] = {}

print("\n(4) the command palette")
menu = win.open_palette()
H.spin(200)
rows = [a for a in menu.actions() if a.text()]
check("it lists the actions", len(rows) > 50, len(rows))
check("each row says its key",
      any("Ctrl+T" in a.text() for a in rows),
      [a.text() for a in rows[:3]])
line = menu.findChild(B.QLineEdit, "paletteinput")
check("it has a box to type in", line is not None)
if line is not None:
    line.setText("new tab")
    line.textEdited.emit("new tab")
    H.spin(100)
    shown = [a for a in rows if a.isVisible()]
    check("typing narrows it down", 0 < len(shown) < len(rows),
          (len(shown), len(rows)))
menu.close()

print("\n(5) the cheat sheet")
before = win.tabs.count()
tab = win.open_cheatsheet()
H.spin(900)
check("it opens in a tab", win.tabs.count() == before + 1)
text = H.js(tab, "document.body.textContent", B.MAIN_WORLD_ID) or ""
check("with the keys in it", "Ctrl+T" in text and "Ctrl+W" in text,
      text[:60])
check("and what they do", "New tab" in text, text[:60])

print("\n(6, 7) the gestures \u2014 taken out again")
# Mouse gestures were built and then removed: they need a Python event
# filter on the widget the engine draws into, and that crashes this
# PyQt build when the interpreter tears down (measured: two crashes in
# six runs with it, none in six without). The side mouse buttons, which
# need no filter, stayed. See FEATURES.md 923/930/931.
check("the browser has no gesture filter any more",
      not hasattr(B, "GestureFilter"))
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))
H.spin(300)

print("\n(8) the focus cycle")
win.config["mouseGestures"] = False
win.urlbar.setFocus()
nxt = win.focus_cycle()
check("F6 moves off the address bar", nxt is not win.urlbar, nxt)
check("and comes back round", win.focus_cycle() is not None)

print("\n(9) copy keys and the selection search")
H.load(view, srv.url("/a"))
H.spin(300)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
check("copy title and address is an action",
      any(e["id"] == "copyurl" for e in actions))
win.run_action("copyurl")
H.spin(400)
from PyQt6.QtGui import QGuiApplication  # noqa: E402
check("and it copies both",
      "— http" in QGuiApplication.clipboard().text(),
      QGuiApplication.clipboard().text())
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.querySelector('p'));
 var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);})()""",
     B.MAIN_WORLD_ID)
before = win.tabs.count()
win.search_selection()
H.wait_for(lambda: win.tabs.count() > before, 4000)
check("searching the selection opens a tab", win.tabs.count() > before,
      (before, win.tabs.count()))

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
