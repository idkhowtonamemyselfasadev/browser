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
sys.path.insert(0, ROOT)
import tmpscratch  # noqa: E402

# Swept for on the way in, which is the half that was missing: atexit
# does not run when a process dies by a signal or calls os._exit, and
# 19 suites end with os._exit to dodge a Qt teardown segfault. So the
# runs most likely to leak were exactly the ones that had opted out of
# the only mechanism that would have tidied up. The run that made the
# mess cannot be relied on to clear it, so the next one does.
DATA = tmpscratch.claim("browser-pwtest-")


def _tidy_scratch():
    """This run's own directory, on the way out.

    The sweep of OTHER runs' leavings lives in tmpscratch and happens
    at STARTUP now. It used to be here, and it asked the age before the
    liveness: it skipped anything under a day old and only then checked
    whether the process still existed. So the age did the deciding, the
    pid check was never reached for anything from the same day, and a
    day of this suite's own output is gigabytes. Liveness decides now,
    and it decides in one place rather than two.
    """
    shutil.rmtree(DATA, ignore_errors=True)


atexit.register(_tidy_scratch)


def _end_the_browsers():
    """Tear the browser down the way the real program does, on the way
    out of a suite.

    MEASURED, 2026-11-02, and it inverts what three of us had concluded.
    browser.py already has a thorough teardown -- _end_process: stop
    every timer, sip.delete every view, every QWebEnginePage found
    through gc (which reaches the PagePanes that _real_tabs cannot), then
    every profile. It is wired twice, to app.aboutToQuit and again after
    app.exec() returns, and BOTH of those live inside main(), which runs
    only under __main__. A suite builds Browser() directly, so no test
    has ever run any of it.

    That is the whole story of the intermittent exit-139 at interpreter
    shutdown. Driven in a probe with two tabs and one Settings pane:

        without the product's teardown   3 pages left, 3 warnings, 3/3 runs
        with it                          0 pages left, 0 warnings, 3/3 runs

    Deterministic both ways, six runs, no crash-rate needed -- the
    condition the race needs is simply absent once the product's own
    teardown runs. So the fix is NOT a fifth page-releasing hook in
    _release_engine_hooks, which is what the rate-hunting pointed at:
    that would be a second implementation of what _end_process already
    does, which is this tree's recurring bug. The product was right and
    the harness was skipping it.

    Registered AFTER _tidy_scratch so it runs BEFORE it (atexit is
    LIFO): the browser goes while its scratch files still exist. Does
    nothing for the suites that end in os._exit -- atexit cannot run
    for them -- and those are also the ones that never see the crash,
    because os._exit skips the teardown the fault lives in.
    """
    app = QApplication.instance()
    if app is None:
        return
    mod = sys.modules.get("browser")
    # _tear_down_engine, NOT _end_process: the latter is that plus
    # os._exit(0), so a suite calling it would report success whatever
    # its checks said. Nearly landed that way; what saved it was an
    # atexit ordering accident, which is not a safety mechanism.
    end = getattr(mod, "_tear_down_engine", None)
    if end is None:
        return
    seen = []
    for widget in app.topLevelWidgets():
        if type(widget).__name__ == "Browser" and widget not in seen:
            seen.append(widget)
    for win in seen:
        try:
            end(win)
        except Exception:
            pass


# NOT REGISTERED, and the measurement is why. Wiring this up did two
# things, both bad:
#
#   it did not work. test_barsuggest took exit 139 at interpreter
#   shutdown in a full 111-suite run WITH this active -- the third
#   occurrence of the crash it was written for. atexit is LIFO and
#   Browser.__init__ registers _release_engine_hooks later than this
#   module is imported, so the profile is released BEFORE this would
#   delete the pages. The 8 clean runs that convinced me were luck;
#   the five "still not deleted" warnings staying at five were the
#   evidence that it ran too late, and I read them and carried on.
#
# It is NOT, however, guilty of the other thing I first blamed it for.
# test_downloads aborted ("wrapped C/C++ object of type Bridge has
# been deleted") in the run with this active and was green in the run
# before, and 5 runs each way read 1-in-5 against 0-in-5, which looked
# like cause. Fifteen runs with this OFF gave 2 aborts in 15. So that
# abort is pre-existing and intermittent, it was green at baseline by
# luck, and this change did not cause it. Written down because the
# first version of this comment said it did.
#
# So the product's teardown is still the right mechanism and this is
# the wrong place to call it from: it has to run BEFORE the engine
# hooks let the profile go, which means at the end of a suite rather
# than at interpreter exit. Left here, unregistered, with the
# measurement, because the next person will have the same idea.
_END_THE_BROWSERS_DISABLED = _end_the_browsers

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_DATA_HOME"] = os.path.join(DATA, "share")
os.environ["XDG_CONFIG_HOME"] = os.path.join(DATA, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(DATA, "cache")
# no suite asks git whether this checkout is behind its remote, and a
# checkout with unpushed commits raises a real toast three seconds into
# every window. Two suites assert that no toast is up; they were red
# for a day's worth of commits for that reason alone.
os.environ["BROWSER_NO_UPDATE_CHECK"] = "1"

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
    for name in ("SESSION_FILE", "PLUGINS_DIR", "PLUGIN_FILE",
                 "TABS_FILE", "GPU_REPORT_FILE"):
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
                    "jar": "application/java-archive",
                    "xml": "text/xml"}.get(
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
    auth_user = "ada"
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
        # A handler thread waits on a keep-alive connection the engine
        # holds open, and ThreadingTCPServer joins every one of them in
        # server_close(): test_dev printed "all good" and then sat in
        # srv.stop() until the 900 s timeout killed it. Daemon threads,
        # not joined -- the process is ending anyway.
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False
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
    want_file = QUrl(url).scheme() == "file"
    box = {"done": False}

    def fin(ok):
        # the page asked for, not the start page a tab made a moment ago
        # was still loading: on THAT loadFinished this returned at once,
        # and the test went on against the wrong document (behind most of
        # the reds that came only under a CPU quota, 2026-11-13)
        if not want_file:
            try:
                if view.url().scheme() == "file":
                    return
            except RuntimeError:
                pass
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
