#!/usr/bin/env python3
"""A look of his own, per site: his own CSS, a zoom level the site
keeps, and a theme that follows the clock."""
import datetime
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


PAGE = ("<!doctype html><title>Styled</title>"
        "<style>#box{width:100px;height:40px;background:#102030}</style>"
        "<div id=box>box</div><p id=p>text</p>")

app = H.app()
srv = H.Server({"/a": PAGE, "/b": PAGE})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))
H.spin(300)


def js(code):
    return H.js(view, code, B.MAIN_WORLD_ID)


print("\n(1) his own CSS for one site")
check("there is none to start with", win.site_style("127.0.0.1") == "")
win.site_style("127.0.0.1", "#box { background: rgb(0, 200, 0) !important; }")
H.load(view, srv.url("/a"))
H.spin(600)
check("it is on the page",
      js("getComputedStyle(document.getElementById('box')).backgroundColor")
      == "rgb(0, 200, 0)",
      js("getComputedStyle(document.getElementById('box')).backgroundColor"))
check("the stylesheet is the browser's own tag",
      js("!!document.getElementById('__mycss')"))
check("and it is remembered",
      "rgb(0, 200, 0)" in win.site_style("127.0.0.1"))
check("another site is untouched", win.site_style("example.com") == "")
win.site_style("127.0.0.1", "")
H.load(view, srv.url("/a"))
H.spin(600)
check("taking it off puts the site's own colour back",
      js("getComputedStyle(document.getElementById('box')).backgroundColor")
      == "rgb(16, 32, 48)",
      js("getComputedStyle(document.getElementById('box')).backgroundColor"))
check("and the tag is gone", not js("!!document.getElementById('__mycss')"))

print("\n(2) a zoom the site keeps")
win.config["zoomPerSite"] = True
win.config["zoomSites"] = {}
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
win.zoom_by(1)
H.spin(400)
level = win.zoom_now(view)
check("zooming is written down for the site",
      abs((win.site_zoom("127.0.0.1") or 0) - level) < .01,
      (win.site_zoom("127.0.0.1"), level))
other = win.new_tab(url=None)
H.load(other, srv.url("/b"))
H.spin(700)
check("a new tab on the same site opens at that level",
      abs(win.zoom_now(other) - level) < .01,
      (win.zoom_now(other), level))
win.tabs.setCurrentIndex(win.tabs.indexOf(other))
win.zoom_reset()
H.spin(300)
check("resetting takes it off the list",
      win.site_zoom("127.0.0.1") is None, win.config.get("zoomSites"))
win.config["zoomPerSite"] = False
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
win.zoom_by(1)
H.spin(300)
check("with that off nothing is written down",
      not win.config.get("zoomSites"), win.config.get("zoomSites"))
win.config["zoomPerSite"] = True
win.zoom_reset()

print("\n(3) a theme that follows the clock")
check("nothing happens without a plan", win.theme_schedule() is None)
now = datetime.datetime.now()
soon = (now + datetime.timedelta(hours=2)).strftime("%H:%M")
ago = (now - datetime.timedelta(hours=2)).strftime("%H:%M")
win.config["themeSchedule"] = {"day": "latte", "night": "mocha",
                               "from": ago, "to": soon}
check("inside the day window it is the day theme",
      win.theme_schedule() == "latte", win.theme_schedule())
win.config["themeSchedule"] = {"day": "latte", "night": "mocha",
                               "from": soon, "to": ago}
check("outside it, the night one", win.theme_schedule() == "mocha",
      win.theme_schedule())
win.config["theme"] = "mocha"
win.config["themeSchedule"] = {"day": "latte", "night": "mocha",
                               "from": ago, "to": soon}
check("applying it changes the theme", win.apply_theme_schedule() is True)
check("and the config says so", win.config.get("theme") == "latte",
      win.config.get("theme"))
check("applying it twice changes nothing",
      win.apply_theme_schedule() is False)
win.config["themeSchedule"] = {"day": "latte"}
check("half a plan is no plan", win.theme_schedule() is None)
win.config["themeSchedule"] = {"day": "latte", "night": "mocha",
                               "from": "nonsense", "to": "x"}
check("and nonsense in it is no plan either",
      win.theme_schedule() is None)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
