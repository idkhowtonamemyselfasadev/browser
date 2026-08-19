#!/usr/bin/env python3
"""Clicks and keyboard focus in newly opened tabs.

The report: on some sites (Amazon Music, the Microsoft sign-in)
nothing was clickable, and that freshly opened tabs neither loaded nor
took a click. The password watcher was the suspect: it puts capture-
phase listeners on the document of every http(s) page, so a listener
that swallowed a gesture would look exactly like that.

This suite holds down that it does not, and that the new-tab paths are
sound:

  * a real Qt mouse click on a page served over http reaches the
    button's own handler while the watcher is armed and waiting for a
    gesture -- the listeners observe, they never consume
  * nothing the watcher injects covers the page: elementFromPoint at
    the button's centre is the button
  * the same click is what releases the saved password, and NOT before
    -- the trust model is exercised, not stepped around
  * every way a tab is opened (empty, with a URL, and a target=_blank
    link clicked for real) produces a tab that loads and takes a click
  * a tab opened in the BACKGROUND leaves the keyboard where it was.
    It used to pull focus into the address bar, so the next thing typed
    at the page he was reading went into the address bar instead.

Offscreen, against a scratch profile and a scratch vault, over a local
http server on 127.0.0.1. Your own data is never opened and nothing
goes to the network.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
for cand in (HERE, Path.home() / "browser"):
    if (cand / "browser.py").exists():
        sys.path.insert(0, str(cand))
        break
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import Qt, QPointF, QEvent  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ---- a login page, over http, so the watcher runs at all -------------
# (PASSWORD_WATCH_JS returns immediately on anything but http/https, so
# a file:// fixture would test nothing.)
LOGIN = b"""<!doctype html><meta charset="utf-8"><title>login</title>
<style>body{margin:0;font:16px sans-serif}
 #go{position:absolute;left:40px;top:200px;width:220px;height:56px}
 input{display:block;margin:14px 40px;width:220px;height:32px}</style>
<h1>Sign in</h1>
<form onsubmit="return false">
  <input id="u" name="email" autocomplete="username" placeholder="E-mail">
  <input id="p" name="password" type="password" placeholder="Password">
  <button id="go" type="button"
          onclick="document.title='CLICKED'">Sign in</button>
</form>
"""
BLANK = b"""<!doctype html><meta charset="utf-8"><title>q</title>
<style>#b{position:absolute;left:40px;top:60px;width:220px;height:56px}</style>
<button id="b" onclick="document.title='CLICKED'">press me</button>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = BLANK if self.path.startswith("/q") else LOGIN
        if self.path.startswith("/link"):
            body = (b'<!doctype html><meta charset="utf-8"><title>l</title>'
                    b'<a id="l" href="/q" target="_blank" '
                    b'style="position:absolute;left:40px;top:80px">open</a>')
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1100, 800)
win.show()          # offscreen widgets are "invisible" until shown, and
                    # a hidden view reports the wrong size to a click


def pump(sec):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents()
        time.sleep(0.02)


def js(view, code, world=0, wait=8):
    box = {}
    view.page().runJavaScript(code, world, lambda r: box.update(r=r))
    t = time.time()
    while "r" not in box and time.time() - t < wait:
        app.processEvents()
        time.sleep(0.02)
    return box.get("r", "<timeout>")


def click(view, x, y):
    """A real Qt press/release on the widget the engine paints into.
    Chromium marks these isTrusted, which is the whole point: the
    gesture gate must accept them and the page must still get them."""
    w = view.focusProxy() or view
    pos = QPointF(float(x), float(y))
    g = QPointF(w.mapToGlobal(pos.toPoint()))
    for typ, held in ((QEvent.Type.MouseMove, Qt.MouseButton.NoButton),
                      (QEvent.Type.MouseButtonPress,
                       Qt.MouseButton.LeftButton),
                      (QEvent.Type.MouseButtonRelease,
                       Qt.MouseButton.NoButton)):
        app.sendEvent(w, QMouseEvent(typ, pos, g, Qt.MouseButton.LeftButton,
                                     held, Qt.KeyboardModifier.NoModifier))
        pump(0.25)


def centre(view, sel):
    return json.loads(js(view, "var r=document.querySelector(%s)"
                               ".getBoundingClientRect();"
                               "JSON.stringify([r.left+r.width/2,"
                               " r.top+r.height/2])" % json.dumps(sel)))


pump(1.5)
# scheme matters: an entry saved for https never fills a plain-http
# page (PasswordVault.entries_for), and the fixture is served over http
win.vault.add_item({"type": "login", "title": "T", "host": "127.0.0.1",
                    "scheme": "http", "username": "user@example.com",
                    "password": "hunter2"})

# ---------------------------------------------------------------- (a)
view = win.new_tab(BASE + "/login")
pump(4)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
pump(1.5)

check("a1 the watcher is actually running on this page",
      js(view, "typeof window.__bpw", B.PW_WORLD_ID) == "object",
      js(view, "typeof window.__bpw", B.PW_WORLD_ID))
check("a2 and is invisible from the page's own world",
      js(view, "typeof window.__bpw", 0) == "undefined")
check("a3 the username was filled, the password was not (no gesture yet)",
      js(view, "document.getElementById('u').value") == "user@example.com"
      and js(view, "document.getElementById('p').value") == "",
      (js(view, "document.getElementById('u').value"),
       js(view, "document.getElementById('p').value")))

x, y = centre(view, "#go")
check("a4 nothing is covering the button",
      js(view, "var e=document.elementFromPoint(%s,%s);"
               "e && e.id" % (x, y)) == "go",
      js(view, "var e=document.elementFromPoint(%s,%s);"
               "e && (e.id||e.nodeName)" % (x, y)))

click(view, x, y)
pump(1.5)
check("a5 the click reached the page's own handler",
      js(view, "document.title") == "CLICKED",
      js(view, "document.title"))
check("a6 and that same real gesture released the saved password",
      js(view, "document.getElementById('p').value") == "hunter2",
      js(view, "document.getElementById('p').value"))

# ---------------------------------------------------------------- (b)
# every way a tab is opened: it loads, and it takes a click
plain = win.new_tab(BASE + "/q")
pump(3)
win.tabs.setCurrentIndex(win.tabs.indexOf(plain))
pump(1)
check("b1 a tab opened with a URL loads",
      js(plain, "document.readyState") == "complete")
bx, by = centre(plain, "#b")
click(plain, bx, by)
pump(1)
check("b2 and takes a click", js(plain, "document.title") == "CLICKED",
      js(plain, "document.title"))

empty = win.new_tab()
pump(3)
check("b3 an empty tab lands on the start page",
      empty.url().toString().startswith("file:")
      and "start.html" in empty.url().toString(),
      empty.url().toString())

linker = win.new_tab(BASE + "/link")
pump(3)
win.tabs.setCurrentIndex(win.tabs.indexOf(linker))
pump(1)
before = win.tabs.count()
lx, ly = centre(linker, "#l")
click(linker, lx, ly)
pump(3)
check("b4 a target=_blank link clicked for real opens a tab",
      win.tabs.count() == before + 1,
      (before, win.tabs.count()))
opened = win.tabs.widget(win.tabs.count() - 1)
win.tabs.setCurrentIndex(win.tabs.count() - 1)
pump(1.5)
check("b5 that tab loads", js(opened, "document.readyState") == "complete",
      opened.url().toString())
ox, oy = centre(opened, "#b")
click(opened, ox, oy)
pump(1)
check("b6 and takes a click", js(opened, "document.title") == "CLICKED",
      js(opened, "document.title"))

# ---------------------------------------------------------------- (c)
# a background tab must not take the keyboard away from the page he is
# reading. "bg <url>" and a bare "raise" both come through new_tab with
# switch=False; _focus_url() used to run for those too, so the next
# thing typed at the page went into the address bar.
win.tabs.setCurrentIndex(win.tabs.indexOf(plain))
plain.setFocus()
pump(0.8)
held = win.tabs.currentWidget()
win.new_tab(url=None, switch=False)
pump(1.5)
check("c1 a background tab does not steal the keyboard",
      app.focusWidget() is not win.urlbar, app.focusWidget())
check("c2 and does not change which tab is in front",
      win.tabs.currentWidget() is held)

# the foreground case keeps its old behaviour: a tab he opened himself
# puts the cursor in the address bar, ready to type an address
win.new_tab(url=None, switch=True)
pump(1.5)
check("c3 a foreground empty tab still focuses the address bar",
      app.focusWidget() is win.urlbar, app.focusWidget())

print("%d checks failed" % len(fails))
if fails:
    print("failed:", ", ".join(fails))
srv.shutdown()
sys.exit(1 if fails else 0)
