#!/usr/bin/env python3
"""What the tabs cost: the task manager, the hover card, tabs that go to
sleep on their own, lite mode, the cache and the startup figure."""
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

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


BIG = ("<!doctype html><title>Heavy</title>"
       + "".join("<p id=p%d>%s</p>" % (i, "x" * 400) for i in range(400)))

app = H.app()
srv = H.Server({"/a": "<title>Alpha</title><p>a</p>",
                "/b": "<title>Beta</title><p>b</p>",
                "/heavy": BIG})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
first = win.new_tab(url=None)
H.load(first, srv.url("/a"))
second = win.new_tab(url=None, switch=False)
H.load(second, srv.url("/heavy"))
H.spin(900)

print("\n(1) what one renderer costs")
pid = first.page().renderProcessPid()
check("a tab has a render process", pid and pid > 0, pid)
cost = win.process_cost(pid)
check("its memory can be read", cost.get("bytes", 0) > 1024 * 1024, cost)
check("and its processor time", "seconds" in cost, cost)
check("a process that is not there answers nothing",
      win.process_cost(999999) == {}, win.process_cost(999999))
check("and so does no process at all", win.process_cost(0) == {})

print("\n(2) the task manager")
rows = win.tab_costs()
check("there is a row per tab", len(rows) == len(win._real_tabs()), len(rows))
check("every row says which tab it is",
      all(r["title"] is not None and r["index"] >= 0 for r in rows))
check("the heaviest is first",
      rows == sorted(rows, key=lambda r: -r["bytes"]), [r["bytes"] for r in rows])
check("a shared process is only counted once",
      all(r["bytes"] == 0 for r in rows if r["shared"]),
      [(r["shared"], r["bytes"]) for r in rows])
menu = win.task_menu()
labels = [a.text() for a in menu.actions()]
check("the menu starts with the total",
      "tabs" in labels[0] and ("MB" in labels[0] or "KB" in labels[0]),
      labels[0])
check("and has a row per tab", len(menu.actions()) >= len(rows), labels[:3])

print("\n(3) the hover card")
tip = win.tab_tooltip(first)
check("it says the address", "/a" in tip, tip)
check("and what the tab costs", "MB" in tip or "KB" in tip, tip)
win.refresh_tab_tooltips()
check("the strip carries it",
      "/a" in win.tabs.tabToolTip(win.tabs.indexOf(first)),
      win.tabs.tabToolTip(win.tabs.indexOf(first)))
win.sleep_tab(second, True)
H.spin(300)
check("a sleeping tab says so in its card",
      "asleep" in win.tab_tooltip(second), win.tab_tooltip(second))
win.sleep_tab(second, False)

print("\n(4) tabs that fall asleep by themselves")
win.config["sleepAfter"] = 0
check("off by default, nothing sleeps", win.auto_sleep() == 0)
win.config["sleepAfter"] = 1
second._seen_at = 0.0          # as if it had not been looked at for ages
first._seen_at = 0.0
win.tabs.setCurrentIndex(win.tabs.indexOf(first))
H.spin(200)
gone = win.auto_sleep()
check("an old tab is put to sleep", gone >= 1, gone)
check("but never the one in front", first not in win.sleeping_tabs())
win.config["sleepAfter"] = 0
win.sleep_tab(second, False)

print("\n(5) lite mode")
attr = B.QWebEngineSettings.WebAttribute
check("it goes on", win.lite_mode(True) is True)
check("images are off", not win.profile.settings().testAttribute(
    attr.AutoLoadImages))
check("and nothing plays by itself",
      win.profile.settings().testAttribute(attr.PlaybackRequiresUserGesture))
check("the tabs that are open follow",
      not first.page().settings().testAttribute(attr.AutoLoadImages))
check("and it goes off again", win.lite_mode(False) is False)
check("with the images back",
      win.profile.settings().testAttribute(attr.AutoLoadImages))

print("\n(6) the cache and the clock")
check("the cache can be cleared", win.clear_cache() >= 1)
check("the startup figure is a number",
      isinstance(win.startup_seconds(), float), win.startup_seconds())

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
