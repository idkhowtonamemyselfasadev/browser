#!/usr/bin/env python3
"""What the browser itself sends, which userscripts ran here, the
window under a word, a window through Tor, and the two permissions a
page can take the machine over with.

Offscreen, scratch data, local server. Nothing here reaches the
network: the archive lookup and the Tor window are checked as the
request and the command they would make.
"""
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
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtNetwork import QNetworkRequest  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {"/p": "<title>P</title><body><p>a page</p>"
                "<div id=box style='width:200px;height:120px'>box</div>"
                "</body>",
         "/q": "<title>Q</title><p>another</p>"}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "de",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(900, 700)
win.show()
H.spin(400)
APP = B.APP_WORLD_ID
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(700)


def js(code, world=APP, v=None):
    return H.js(v or view, code, world)


print("\n(1) what the browser itself sends")
check("the log starts out as a list", isinstance(win.own_requests(), list))
check("...and it is on", win._nam.watching is True)
req = QNetworkRequest(QUrl("http://127.0.0.1:1/never"))
req.setRawHeader(b"X-Why", b"test")
reply = win._nam.get(req)
H.spin(200)
rows = win.own_requests()
check("a connection the browser makes is written down",
      any(row["url"].endswith("/never") for row in rows),
      [row["url"] for row in rows][:3])
row = next(row for row in rows if row["url"].endswith("/never"))
check("...with how it was made", row["how"] == "get", row)
check("...and who wanted it", row["why"] == "test", row)
check("...and when", row["t"] > 0, row)
check("the places are counted",
      win.own_request_hosts().get("127.0.0.1", 0) >= 1,
      win.own_request_hosts())
check("one host can be asked for",
      all(r["host"] == "127.0.0.1"
          for r in win.own_requests(host="127.0.0.1")),
      win.own_requests(host="127.0.0.1")[:1])
check("a host nobody talked to is empty",
      win.own_requests(host="nowhere.test") == [])
check("the log can be switched off", win.watch_own_requests(False) is False)
win._nam.get(QNetworkRequest(QUrl("http://127.0.0.1:1/quiet")))
H.spin(200)
check("...and then nothing is written down",
      not any(r["url"].endswith("/quiet") for r in win.own_requests()),
      [r["url"] for r in win.own_requests()][:3])
check("...and it comes back on", win.watch_own_requests(True) is True)
check("the switch is remembered", win.config.get("ownRequestLog") is True)
before = len(win.own_requests())
check("it can be cleared", win.clear_own_requests() == before, before)
check("...and then it is empty", win.own_requests() == [])
check("a page's own traffic is not in it",
      not any("/p" in r["url"] for r in win.own_requests()),
      [r["url"] for r in win.own_requests()][:3])
menu = win.own_requests_menu()
check("the menu says there is nothing yet",
      any(one.text() == B.UI_STRINGS["de"]["ownNone"]
          for one in menu.actions()),
      [one.text() for one in menu.actions()][:3])
win._nam.get(QNetworkRequest(QUrl("http://127.0.0.1:1/again")))
H.spin(200)
menu = win.own_requests_menu()
labels = [one.text() for one in menu.actions()]
check("...and lists the places when there are some",
      any("127.0.0.1" in one for one in labels), labels[:4])
check("...and offers to clear it",
      B.UI_STRINGS["de"]["ownClear"] in labels, labels)

print("\n(2) which userscripts ran on this page")
check("with none installed it says so", win.page_userscripts(view=view) == [])
menu = win.userscripts_menu(view=view)
check("...and the menu does too",
      [one.text() for one in menu.actions()]
      == [B.UI_STRINGS["de"]["usNone"]],
      [one.text() for one in menu.actions()])
(win.plugins_dir / "here.user.js").write_text(
    "// ==UserScript==\n// @name Runs here\n"
    "// @match http://127.0.0.1/*\n// @match http://127.0.0.1:*/*\n"
    "// @grant GM_xmlhttpRequest\n// @grant GM_setValue\n"
    "// ==/UserScript==\nconsole.log(1)\n")
(win.plugins_dir / "elsewhere.user.js").write_text(
    "// ==UserScript==\n// @name Somewhere else\n"
    "// @match https://example.com/*\n// ==/UserScript==\n")
rows = win.page_userscripts(view=view)
check("two installed scripts are both listed", len(rows) == 2, len(rows))
mine = next(r for r in rows if r["title"] == "Runs here")
other = next(r for r in rows if r["title"] == "Somewhere else")
check("the one matching this page says it ran", mine["runs"] is True, mine)
check("...and the other says it did not", other["runs"] is False, other)
check("what it asked for is read off its header",
      "GM_xmlhttpRequest" in mine["grant"], mine["grant"])
check("...and what it really may do is spelled out",
      any("not granted" in one for one in mine["may"]), mine["may"])
check("...including the page itself",
      any("change this page" in one for one in mine["may"]), mine["may"])
check("a script that asked for nothing may only touch the page",
      other["may"] == ["read and change this page"], other["may"])
check("when it runs is said too", mine["when"] == "document ready", mine)
check("...and in which world", mine["world"] == "app", mine)
check("the powers of nothing are just the page",
      win.userscript_powers([]) == ["read and change this page"])
check("unsafeWindow is refused in words",
      any("own world" in one
          for one in win.userscript_powers(["unsafeWindow"])),
      win.userscript_powers(["unsafeWindow"]))
menu = win.userscripts_menu(view=view)
labels = [one.text() for one in menu.actions()]
check("the audit menu ticks the one that ran",
      any(one.startswith("✓") and "Runs here" in one
          for one in labels), labels)
check("...and does not tick the other",
      any(not one.startswith("✓") and "Somewhere" in one
          for one in labels), labels)
for one in (win.plugins_dir / "here.user.js",
            win.plugins_dir / "elsewhere.user.js"):
    one.unlink()

print("\n(3) the window, under a word")
check("no word is set to start with", win.browser_lock_set() is False)
check("locking without one refuses", win.lock_browser() is False)
check("a word can be set", win.set_browser_lock("open sesame") is True)
check("...and it is not kept as itself",
      "open sesame" not in json.dumps(win.config),
      [k for k in win.config if "lock" in k.lower()])
check("...and the right word opens it",
      win.check_browser_lock("open sesame") is True)
check("...and a wrong one does not",
      win.check_browser_lock("open sesam") is False)
check("the window covers", win.lock_browser() is True)
check("...and says it is locked", win.locked_now() is True)
cover = win._lock_cover
check("...with a cover over the whole window",
      cover.width() >= win.width() - 2, [cover.width(), win.width()])
box = cover.findChild(type(win.urlbar).__bases__[0], "lockinput") \
    or cover.findChild(object, "lockinput")
check("...and a box to type the word in", box is not None)
check("locking twice is still locked", win.lock_browser() is True)
check("it opens again", win.unlock_browser() is True)
check("...and says so", win.locked_now() is False)
check("opening what is not locked does nothing",
      win.unlock_browser() is False)
check("an empty word takes the lock off",
      win.set_browser_lock("") is False
      and win.browser_lock_set() is False)
check("...and then any word opens it",
      win.check_browser_lock("anything") is True)
ids = [one["id"] for one in win.tab_actions_extra()]
check("there is a command for it", "lockbrowser" in ids
      or any("lock" in one for one in ids), [o for o in ids if "lock" in o])

print("\n(4) a window through Tor")
running = win.tor_running()
check("whether Tor is listening is measured, not assumed",
      running in (True, False), running)
check("...on a port nothing is on, it is False",
      win.tor_running(port=9) is False)
plan = win.tor_command("http://x.test/a")
check("the plan is its own process", plan["args"][0] == sys.executable,
      plan["args"][0])
check("...running this browser", plan["args"][1].endswith("browser.py"),
      plan["args"][1])
check("...with the address on the command line",
      "http://x.test/a" in plan["args"], plan["args"])
check("...through the SOCKS port",
      "socks5://127.0.0.1:9050" in plan["env"]["QTWEBENGINE_CHROMIUM_FLAGS"],
      plan["env"]["QTWEBENGINE_CHROMIUM_FLAGS"])
check("...and names kept off the machine too",
      "host-resolver-rules" in plan["env"]["QTWEBENGINE_CHROMIUM_FLAGS"])
check("...on data of its own",
      plan["env"]["BROWSER_HOME"].endswith("tor-profile"),
      plan["env"]["BROWSER_HOME"])
check("...which is not his own data",
      plan["env"]["BROWSER_HOME"] != str(B.BROWSER_HOME),
      [plan["env"]["BROWSER_HOME"], str(B.BROWSER_HOME)])
if not running:
    check("without Tor it refuses rather than opening a plain window",
          win.open_tor_window() is False)
else:
    check("with Tor it would start that process",
          isinstance(win.open_tor_window(start=False), dict))
# the test harness points the files at its own scratch directory, so
# where they land for a *fresh* process is asked of a fresh process
import subprocess  # noqa: E402
out = subprocess.run(
    [sys.executable, "-c",
     "import os,sys;os.environ['QT_QPA_PLATFORM']='offscreen';"
     "os.environ['BROWSER_NO_LIB_CHECK']='1';"
     "sys.path.insert(0, %r);import browser as b;"
     "print(b.BROWSER_HOME);print(b.HISTORY_FILE);"
     "print(b.BOOKMARKS_FILE);print(b.SINGLE_INSTANCE_SOCKET)"
     % str(HERE)],
    capture_output=True, text=True,
    env=dict(os.environ, BROWSER_HOME=str(scratch / "elsewhere")))
rows = [one for one in out.stdout.splitlines() if one.strip()]
check("BROWSER_HOME moves his data", rows and rows[0].endswith("elsewhere"),
      rows[:1] or out.stderr[-200:])
check("...the history with it",
      len(rows) > 1 and rows[1].startswith(rows[0]), rows[1:2])
check("...and the bookmarks",
      len(rows) > 2 and rows[2].startswith(rows[0]), rows[2:3])
check("...and the door is not the one he is using",
      len(rows) > 3 and rows[3] != "browser-single-instance", rows[3:4])

print("\n(5) the whole screen, per site")
check("it is not asked about to start with",
      win.config.get("askFullscreen", False) is False)
check("there are no rules", win.fullscreen_rules() == {})
check("a site can be allowed",
      win.set_fullscreen_rule("x.test", True) is True)
check("...and it answers for that site", win.fullscreen_rule("x.test") is True)
check("...and for a sub-domain of it",
      win.fullscreen_rule("sub.x.test") is True)
check("...and not for another", win.fullscreen_rule("y.test") is None)
check("a site can be refused",
      win.set_fullscreen_rule("y.test", False) is False
      and win.fullscreen_rule("y.test") is False)
check("a rule can be taken off",
      win.set_fullscreen_rule("y.test", None) is True
      and win.fullscreen_rule("y.test") is None)
check("a site with no name is not a site",
      win.set_fullscreen_rule("", True) is False)
check("asking can be switched on", win.ask_fullscreen(True) is True)
check("...and off again", win.ask_fullscreen(False) is False)
win.ask_fullscreen(True)
check("the bar can be put up", win.offer_fullscreen_rule("x.test",
                                                         view=view) is True)
H.spin(500)
bar = js("var b = document.getElementById('__fsbar');"
         " b ? b.innerText : ''")
check("...and it says which site", "x.test" in (bar or ""), (bar or "")[:60])
want = [B.UI_STRINGS["de"]["fsBarKeep"], B.UI_STRINGS["de"]["fsBarStop"],
        B.UI_STRINGS["de"]["fsBarNever"]]
check("...and offers the three answers",
      all(one in (bar or "") for one in want),
      [one for one in want if one not in (bar or "")])
js("window.__fsAnswer = 'never';")
H.spin(900)
check("“never for this site” is remembered",
      win.fullscreen_rule("x.test") is False, win.fullscreen_rules())
win.set_fullscreen_rule("x.test", None)
check("the bar is taken down when it is answered",
      js("!!document.getElementById('__fsbar')") is False)
win.offer_fullscreen_rule("x.test", view=view)
H.spin(400)
js("window.__fsAnswer = 'keep';")
H.spin(900)
check("“that is fine” is remembered too",
      win.fullscreen_rule("x.test") is True, win.fullscreen_rules())
check("the browser can give the screen back itself",
      win.leave_fullscreen(view=view) is True)

print("\n(6) the mouse, and the words the card says")
from PyQt6.QtWebEngineCore import QWebEnginePermission  # noqa: E402
check("the pointer is something a site has to ask for",
      QWebEnginePermission.PermissionType.MouseLock
      in B.PERMISSION_LABELS,
      list(B.PERMISSION_LABELS))
check("...and the card has words for it",
      B.PERMISSION_LABELS[QWebEnginePermission.PermissionType.MouseLock]
      == "permMouse")
check("every permission label is a string key that exists",
      all(B.UI_STRINGS["en"].get(key) and B.UI_STRINGS["de"].get(key)
          for key in B.PERMISSION_LABELS.values()),
      [k for k in B.PERMISSION_LABELS.values()
       if not B.UI_STRINGS["de"].get(k)])
check("...and the card's own sentence is translated",
      B.UI_STRINGS["en"]["permWants"] != B.UI_STRINGS["de"]["permWants"],
      [B.UI_STRINGS["en"]["permWants"], B.UI_STRINGS["de"]["permWants"]])
check("...in both languages, with the two holes in it",
      B.UI_STRINGS["de"]["permWants"].count("%s") == 2,
      B.UI_STRINGS["de"]["permWants"])
check("the microphone still has its words",
      B.UI_STRINGS["en"][B.PERMISSION_LABELS[
          QWebEnginePermission.PermissionType.MediaAudioCapture]]
      == "use your microphone")

print("\n(7) every new word, in both languages")
need = ["permWants", "permThisRun", "permMic", "permCam", "permMicCam",
        "permNotify", "permMouse", "ownName", "ownNone", "ownClear",
        "ownWatch", "ownWatchHint", "usName", "usNone", "usRanHere",
        "usNotHere", "usWhen", "torName", "torNone", "torOpened",
        "torHint", "fsAskName", "fsAskHint", "fsBarSaid", "fsBarKeep",
        "fsBarStop", "fsBarNever", "fsDenied"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)
        and k not in ("permWants",)]
check("and they are really translated", same == [], same)
page = (HERE / "settings.html").read_text()
check("the two switches are in Settings",
      'id="askfullscreen"' in page and 'id="ownlog"' in page)
check("...and bound to what they switch",
      'bindSwitch("askfullscreen", "askFullscreen")' in page
      and 'bindSwitch("ownlog", "ownRequestLog")' in page)
ids = [one["id"] for one in win.tab_actions_extra()]
for one in ("ownsends", "userscripts", "torwindow"):
    check("“%s” is a command" % one, one in ids)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
