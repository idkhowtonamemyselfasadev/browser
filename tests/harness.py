"""Offscreen test harness for the two-step autofill work.

Never touches your real data: every file path the browser uses is
redirected into a scratch directory and the app name is changed so the
QtWebEngine profiles cannot collide with the running browser.
"""
import atexit, os, sys, json, shutil, threading, functools, http.server, socketserver
import time

import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # the browser itself
# one directory per process, not one for everybody: two suites running
# at the same time used to share this and wipe each other's data
# half-way through, which shows up as failures in whichever run lost the
# race rather than as anything to do with the code under test
DATA = os.path.join(tempfile.gettempdir(),
                    "browser-pwtest-%d" % os.getpid())


def _tidy_scratch():
    """Take this run's scratch directory away when the process ends.

    Why this is here at all: every run left its directory behind, and
    a profile with a cache in it is 70-80 MB. After a few hundred runs
    /tmp was full, and what that looks like is not "no space left" --
    it is the last few tests of a suite segfaulting and timing out,
    because a browser that cannot write its profile dies in a way that
    looks like a bug in whatever it was doing.

    Anything older than a day from a run that is no longer there goes
    with it, so a suite that was killed does not leave its own behind.
    """
    shutil.rmtree(DATA, ignore_errors=True)
    parent = tempfile.gettempdir()
    now = time.time()
    try:
        names = os.listdir(parent)
    except OSError:
        return
    for name in names:
        if not name.startswith("browser-pwtest-"):
            continue
        path = os.path.join(parent, name)
        try:
            if now - os.path.getmtime(path) < 86400:
                continue
            pid = int(name.rsplit("-", 1)[-1])
        except (OSError, ValueError):
            continue
        try:
            os.kill(pid, 0)          # still running: leave it alone
        except ProcessLookupError:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


atexit.register(_tidy_scratch)

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
        # exactly the auth paths, not every path that starts with
        # those five letters: "/author/someone" is a page, and asking
        # for a password on it hung a whole suite for fifteen minutes
        if (path == "/auth" or path.startswith("/auth/")) \
                and not self._auth_ok():
            self.send_response(401)
            self.send_header("WWW-Authenticate",
                             'Basic realm="the test server"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.startswith("/moved/"):
            # a real 301, which is the only honest way to test what a
            # browser does with one: the engine never hands an
            # embedder a status code, so a test that wants a redirect
            # has to make the server send one
            where = "/" + path[len("/moved/"):]
            self.send_response(301)
            self.send_header("Location", where)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/echo":
            # what the server was actually sent, so a test can check a
            # header the browser added rather than what JavaScript says
            lines = ["%s: %s" % (k, v) for k, v in self.headers.items()]
            raw = ("<title>echo</title><pre>" + "\n".join(lines)
                   + "</pre>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        body = self.pages.get(path)
        if body is None:
            self.send_error(404)
            return
        # a page given as bytes is served as itself, with a type from
        # its ending: a test that needs a real picture (for its
        # natural size, say) cannot get one out of text/html
        if isinstance(body, bytes):
            raw = body
            kind = {"png": "image/png", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "gif": "image/gif",
                    "webp": "image/webp", "pdf": "application/pdf",
                    "zip": "application/zip",
                    "jar": "application/java-archive"}.get(
                        path.rsplit(".", 1)[-1].lower(),
                        "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    #: paths under this prefix ask for a basic-auth login, and only
    #: this one is accepted. A browser has no way to test its own
    #: http-auth dialog without a server that asks for one.
    auth_user = "tim"
    auth_password = "letmein"

    def _auth_ok(self):
        import base64
        want = "Basic " + base64.b64encode(
            ("%s:%s" % (self.auth_user, self.auth_password)).encode()
        ).decode()
        return self.headers.get("Authorization") == want

    def do_HEAD(self):
        """The same answer as GET without the body. SimpleHTTPRequest-
        Handler's own do_HEAD serves the filesystem, which has none of
        these pages in it and answered 404 to everything -- and a test
        of "is this page still there?" needs a server that can say
        yes."""
        path = self.path.split("?")[0]
        body = self.pages.get(path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()

    #: what the last POST carried, for a test that wants to look
    last_post = {}

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        path = self.path.split("?")[0]
        Handler.last_post = {"path": path, "length": n,
                             "type": self.headers.get("Content-Type", ""),
                             "head": body[:400]}
        # a Moonraker-shaped answer, so the 3D-printer upload can be
        # tested against something that behaves like the printer does
        if path.startswith("/server/files/upload"):
            answer = b'{"item": {"path": "test.gcode"}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)
            return
        self.send_response(303)
        self.send_header("Location", self.headers.get("X-Next") or "/step2")
        self.end_headers()

    #: what the last PUT carried -- the capture upload uses PUT, and a
    #: test that cannot see what arrived cannot prove it arrived
    last_put = {}

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        Handler.last_put = {"path": self.path.split("?")[0], "length": n,
                            "type": self.headers.get("Content-Type", ""),
                            "head": body[:64]}
        self.send_response(201)
        self.send_header("Content-Length", "0")
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


#: how long js() waits for the page before it gives up and says so
JS_TIMEOUT_MS = 5000


def js(view, code, world=None):
    """Run JS and return the value (blocking).

    A TIMEOUT IS NOT A VALUE, and this used to answer `None` for both
    "the page said null" and "the page never answered". Those are not
    the same thing, and a suite cannot tell them apart afterwards:

        check("...and the page is near where it was",
              (js("window.scrollY|0", MAIN) or 0) >= 200,
              js("window.scrollY|0", MAIN))

    `or 0` turns "I never heard back" into a confident zero. Five runs
    of exactly that line on a quiet machine, reported by
    browser-windows:

        run 3  FAIL  ...and the page is near where it was  <240>
        run 5  ok    ...and the page is near where it was  <0>

    Two verdicts out of five contradicting the evidence printed beside
    them, in opposite directions. Run 5 is the one that matters: a red
    check that is wrong gets investigated, and **a green check that
    proves nothing is never looked at again**.

    There are 495 check() verdicts across these suites whose condition
    reads a js() value, 77 of them coercing with `or`. Every one was
    free to treat silence as a measurement.

    So silence raises. A suite that dies saying "js() timed out" is
    telling the truth; one that says "ok, scroll was 0" is not.

    Note what this does NOT fix. The example above asks the page twice
    -- once for the condition and once for the detail -- and the value
    can change between them, which is why run 3 failed while printing
    240. That is a caller bug and it needs the caller to measure once
    and assert on the thing it measured. Raising here only stops
    silence being mistaken for data.
    """
    box = {}
    loop = QEventLoop()

    def done(v):
        box["v"] = v
        loop.quit()
    if world is None:
        view.page().runJavaScript(code, done)
    else:
        view.page().runJavaScript(code, world, done)
    QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    if "v" not in box:
        raise AssertionError(
            "js() timed out after %d ms, so the answer below is not a "
            "measurement: %s" % (JS_TIMEOUT_MS, str(code)[:120]))
    return box["v"]


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
