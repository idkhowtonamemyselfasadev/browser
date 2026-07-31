"""Offscreen test harness for the two-step autofill work.

Never touches your real data: every file path the browser uses is
redirected into a scratch directory and the app name is changed so the
QtWebEngine profiles cannot collide with the running browser.
"""
import os, sys, json, shutil, threading, functools, http.server, socketserver

import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # the browser itself
# one directory per process, not one for everybody: two suites running
# at the same time used to share this and wipe each other's data
# half-way through, which shows up as failures in whichever run lost the
# race rather than as anything to do with the code under test
DATA = os.path.join(tempfile.gettempdir(),
                    "browser-pwtest-%d" % os.getpid())

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_DATA_HOME"] = os.path.join(DATA, "share")
os.environ["XDG_CONFIG_HOME"] = os.path.join(DATA, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(DATA, "cache")

sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QEventLoop, QPoint, Qt, QUrl
from PyQt6.QtTest import QTest


def fresh_data():
    shutil.rmtree(DATA, ignore_errors=True)
    for sub in ("share", "config", "cache", "cfg"):
        os.makedirs(os.path.join(DATA, sub), exist_ok=True)


def boot():
    """Import browser with every data file redirected, return module."""
    fresh_data()
    import browser as B
    from pathlib import Path
    cfg = Path(DATA) / "cfg"
    B.CONFIG_FILE = cfg / "config.json"
    B.HISTORY_FILE = cfg / "history.json"
    B.DOWNLOADS_FILE = cfg / "downloads.json"
    B.HOSTS_FILE = cfg / "hosts.json"
    B.BOOKMARKS_FILE = cfg / "bookmarks.json"
    for name in ("SESSION_FILE", "PLUGINS_DIR", "PLUGIN_FILE", "TABS_FILE"):
        if hasattr(B, name):
            v = getattr(B, name)
            setattr(B, name, cfg / os.path.basename(str(v)))
    # A scratch config is a fresh install, where Vault Password is off.
    # These suites are the password suites, so it goes on — and it has
    # to be in the file, not set afterwards the way savePasswords is:
    # the watcher is injected while the profile is built.
    import json
    cfg.mkdir(parents=True, exist_ok=True)
    if not B.CONFIG_FILE.exists():
        B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": True}))
    return B


def app():
    a = QApplication.instance() or QApplication(sys.argv)
    a.setApplicationName("browser-shot")
    return a


# ---- a real HTTP server, two hostnames, one document root ----------
class Handler(http.server.SimpleHTTPRequestHandler):
    pages = {}

    def do_GET(self):
        path = self.path.split("?")[0]
        body = self.pages.get(path)
        if body is None:
            self.send_error(404)
            return
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self.send_response(303)
        self.send_header("Location", self.headers.get("X-Next") or "/step2")
        self.end_headers()

    def log_message(self, *a):
        pass


class Server:
    def __init__(self, pages):
        Handler.pages = dict(pages)
        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()

    def url(self, path, host="127.0.0.1"):
        return "http://%s:%d%s" % (host, self.port, path)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


# ---- waiting helpers ------------------------------------------------
def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_for(fn, timeout=8000, step=50):
    waited = 0
    while waited < timeout:
        if fn():
            return True
        spin(step)
        waited += step
    return False


def js(view, code, world=None):
    """Run JS and return the value (blocking)."""
    box = {}
    loop = QEventLoop()

    def done(v):
        box["v"] = v
        loop.quit()
    if world is None:
        view.page().runJavaScript(code, done)
    else:
        view.page().runJavaScript(code, world, done)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    return box.get("v")


def load(view, url):
    box = {"done": False}

    def fin(ok):
        box["done"] = True
    c = view.loadFinished.connect(fin)
    view.load(QUrl(url))
    wait_for(lambda: box["done"], 15000)
    view.loadFinished.disconnect(c)
    spin(500)  # let document-idle scripts and the channel settle


def rect(view, selector):
    r = js(view, "(function(){var e=document.querySelector(%s);"
                 "if(!e)return null;var r=e.getBoundingClientRect();"
                 "return [r.left+r.width/2, r.top+r.height/2];})()"
           % json.dumps(selector))
    return r


def click(view, selector, zoom=1.0):
    """A REAL Qt mouse click on the element (isTrusted events)."""
    r = rect(view, selector)
    assert r, "no element " + selector
    p = QPoint(int(r[0] * zoom), int(r[1] * zoom))
    w = view.focusProxy() or view
    QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    spin(60)
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    spin(250)


def press(widget):
    """A real platform press and release on a widget of the browser's
    own chrome.

    Deliberately not QAbstractButton.click(), which only emits the
    signal. The account chooser's whole safety argument is that the
    press authorising a fill is a genuine one that no page can make;
    a test that emitted the signal directly would go on passing if the
    widget ever became reachable from a page, which is precisely the
    thing it is supposed to catch."""
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    spin(400)


def key(view, qtkey, text=""):
    w = view.focusProxy() or view
    QTest.keyClick(w, qtkey)
    spin(250)


def type_text(view, s):
    w = view.focusProxy() or view
    for ch in s:
        QTest.keyClicks(w, ch)
        spin(20)
    spin(200)
