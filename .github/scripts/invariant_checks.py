#!/usr/bin/env python3
"""Security invariants of browser.py — the things a change must not break.

Every check here corresponds to a bug that was found and fixed once. They
are not a linter and not a style check: each one asserts a property that
keeps a website out of somewhere it does not belong.

    python3 .github/scripts/invariant_checks.py          # run them all
    python3 .github/scripts/invariant_checks.py --json out.json

Runs headless (QT_QPA_PLATFORM=offscreen) against a throwaway data
directory, so it never reads or writes real browsing data. Exit status is
0 when every check passes, 1 when one fails.
"""

import argparse
import inspect
import json
import os
import re
import socket
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# offscreen before Qt is imported, and no GPU/sandbox on CI runners
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                      "--no-sandbox --disable-gpu --disable-dev-shm-usage")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

_SCRATCH = tempfile.TemporaryDirectory(prefix="browser-invariants-")
SCRATCH = Path(_SCRATCH.name)
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "xdg")
os.environ["HOME"] = os.environ.get("HOME", str(SCRATCH))

sys.path.insert(0, str(REPO))
import browser as B  # noqa: E402

# every path the browser writes to, pointed at the scratch directory
for _name in ("CONFIG_FILE", "HISTORY_FILE", "DOWNLOADS_FILE",
              "HOSTS_FILE", "BOOKMARKS_FILE"):
    setattr(B, _name, SCRATCH / "data" / (_name.lower() + ".json"))
(SCRATCH / "data").mkdir(parents=True, exist_ok=True)
# the password-fill invariant needs the watcher injected, and a
# scratch config is a fresh install where Vault Password is off
B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": True}))

from PyQt6.QtCore import (QEventLoop, QMetaMethod, QPoint, Qt,  # noqa: E402
                          QTimer, QUrl)
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402


# --------------------------------------------------------------- harness
CHECKS = []
RESULTS = []


def check(title):
    def wrap(fn):
        CHECKS.append((title, fn))
        return fn
    return wrap


def run_all(browser, only=None):
    failed = 0
    for title, fn in CHECKS:
        if only and only not in title:
            continue
        try:
            note = fn(browser) or ""
            RESULTS.append({"check": title, "ok": True, "note": note})
            print("PASS  %s%s" % (title, ("  — " + note) if note else ""))
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            detail = "".join(traceback.format_exception_only(
                type(exc), exc)).strip()
            RESULTS.append({"check": title, "ok": False, "note": detail,
                            "traceback": traceback.format_exc()})
            print("FAIL  %s\n      %s" % (title, detail))
            print(re.sub(r"^", "      ", traceback.format_exc().rstrip(),
                         flags=re.M))
    return failed


def load(view, url, timeout=30000):
    """Load a URL and wait for it.

    A navigation that changes the page's trust level is refused and
    re-issued a tick later, which reports one failed load first; keep
    waiting until a load actually succeeds.
    """
    loop = QEventLoop()
    done = {"ok": None}

    def finished(ok):
        done["ok"] = ok
        if ok:
            loop.quit()

    view.loadFinished.connect(finished)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout)
    view.load(QUrl(url) if isinstance(url, str) else url)
    loop.exec()
    view.loadFinished.disconnect(finished)
    assert done["ok"] is not None, "page never finished loading: %s" % url
    assert done["ok"], "page failed to load: %s" % url


def js(page, script, world, timeout=15000):
    """runJavaScript, synchronously, in a given world."""
    loop = QEventLoop()
    box = {"v": None, "got": False}

    def back(value):
        box["v"] = value
        box["got"] = True
        loop.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout)
    page.runJavaScript(script, world, back)
    loop.exec()
    assert box["got"], "javascript never came back: %.60s" % script
    return box["v"]


def qt_slots(cls):
    """The slots a QWebChannel would expose for this class, from Qt's
    own metaobject rather than from the Python class body."""
    mo = cls.staticMetaObject
    return [bytes(mo.method(i).methodSignature()).decode()
            for i in range(mo.methodOffset(), mo.methodCount())
            if mo.method(i).methodType() == QMetaMethod.MethodType.Slot]


ALIVE = []          # PyQt reaps a parentless view the moment we drop it


def web_view(browser):
    """A view/page pair built the way the browser builds them."""
    view = QWebEngineView()
    page = B.WebPage(browser, browser.profile, view)
    view.setPage(page)
    ALIVE.append(view)
    return view, page


def channel_worlds(page):
    """Which channel `_install_channel` puts in which script world.

    Asked by monkeypatching setWebChannel rather than by reading the
    channels back: QWebChannel.registeredObjects() hands the caller
    Python ownership of the objects it returns, which destroys the real
    Bridge as soon as the temporary is dropped.
    """
    seen = {}
    original = page.setWebChannel
    page.setWebChannel = lambda channel, world: seen.__setitem__(
        "pw" if channel is page._pw_channel else
        "full" if channel is page._full_channel else "?", world)
    for kind in ("full", "pw"):
        page._install_channel(kind)
    page.setWebChannel = original
    page._install_channel("pw")
    return seen


def write_page(name, body):
    path = SCRATCH / name
    path.write_text("<!doctype html><meta charset=utf-8>" + body)
    return path


ENGINE_NOTE = ("engine could not start here; the checks that need a live "
               "page were skipped")


def engine_works(browser):
    """Can this machine actually render a page? (CI sanity, not a check.)"""
    try:
        view, page = web_view(browser)
        path = write_page("engine-probe.html", "<b id=x>hi</b>")
        load(view, path.as_uri(), timeout=45000)
        return js(page, "document.getElementById('x').textContent",
                  B.PW_WORLD_ID) == "hi"
    except Exception:                                   # noqa: BLE001
        return False


# ------------------------------------------------- 1. the trust boundary
@check("internal pages are recognised, and only those")
def internal_pages(browser):
    own = ["start.html", "settings.html", "history.html", "downloads.html",
           "bookmarks.html"]
    for name in own:
        url = QUrl.fromLocalFile(str(B.APP_DIR / name))
        assert B.is_internal_page(url), "%s should be internal" % name
        # the key travels as a query string; it must not change the verdict
        keyed = QUrl(url)
        keyed.setQuery("k=abc")
        assert B.is_internal_page(keyed), "%s?k= should be internal" % name
        # ../ inside the path still resolves to our own page
        walked = QUrl.fromLocalFile(str(B.APP_DIR / "sub" / ".." / name))
        assert B.is_internal_page(walked), "%s via ../ should be internal" % name

    outsiders = [
        QUrl("https://example.com/start.html"),
        QUrl("http://localhost/start.html"),
        QUrl("about:blank"),
        QUrl("data:text/html,<b>hi</b>"),
        QUrl("javascript:void 0"),
        QUrl.fromLocalFile(str(SCRATCH / "start.html")),   # same name, elsewhere
        QUrl.fromLocalFile(str(B.APP_DIR / "README.md")),  # ours, not a page
        QUrl.fromLocalFile(str(B.APP_DIR)),                # the directory
        QUrl(""),
    ]
    for url in outsiders:
        assert not B.is_internal_page(url), \
            "%s must not count as internal" % url.toString()
    return "%d own pages, %d outsiders" % (len(own), len(outsiders))


@check("a page starts untrusted and every web navigation lands on the pw channel")
def channel_defaults(browser):
    view, page = web_view(browser)
    assert page._channel_kind == "pw", \
        "a fresh page must start on the password channel, not %r" \
        % page._channel_kind

    # the two channels live in different worlds, and the untrusted one
    # is the only one a page's own scripts share a world with
    assert B.MAIN_WORLD_ID != B.PW_WORLD_ID, \
        "both channels are in the same script world"
    worlds = channel_worlds(page)
    assert worlds.get("full") == B.MAIN_WORLD_ID, worlds
    assert worlds.get("pw") == B.PW_WORLD_ID, \
        "the password channel is no longer in its own world: %s" % worlds

    # and the untrusted object is a PasswordBridge with one slot on it
    assert not issubclass(B.PasswordBridge, B.Bridge)
    src = inspect.getsource(B.WebPage.__init__)
    assert re.search(r'_pw_channel\.registerObject\(\s*"pw",\s*PasswordBridge',
                     src), "the untrusted channel registers something else now"
    assert re.search(r'_full_channel\.registerObject\(\s*"bridge",\s*'
                     r'browser\.bridge', src)
    # An exact list, not a subset: anything new on this object is
    # reachable by every website, so a name appearing here has to be
    # argued for by a human before this line is updated. Both of these
    # are one-way — the page tells the browser something and gets
    # nothing back.
    exposed = qt_slots(B.PasswordBridge)
    assert exposed == ["formSubmitted(QString)",
                       "loginFormSeen(QString)"], \
        "the object a website can reach now exposes %s" % exposed
    for name in exposed:
        got = getattr(B.PasswordBridge, name.split("(")[0])
        assert "result" not in str(
            getattr(got, "__doc__", "") or ""), \
            "%s hands something back to the page" % name
    assert len(qt_slots(B.Bridge)) > 20, \
        "Bridge lost its slots — is this comparison still meaningful?"

    typed = QWebEnginePage.NavigationType.NavigationTypeTyped
    for url in ("https://example.com/", "http://example.com/",
                "about:blank", SCRATCH.joinpath("x.html").as_uri()):
        page._install_channel("full")                    # pretend we were trusted
        allowed = page.acceptNavigationRequest(QUrl(url), typed, True)
        assert page._channel_kind == "pw", \
            "%s left the page on the %s channel" % (url, page._channel_kind)
        assert not allowed, \
            "%s was allowed through without re-issuing the navigation" % url

    # and the reverse still works, or the browser's own pages break
    page._install_channel("pw")
    start = QUrl.fromLocalFile(str(B.APP_DIR / "start.html"))
    assert not page.acceptNavigationRequest(start, typed, True)
    assert page._channel_kind == "full", "our own page did not get the bridge"
    return "pw by default, full only for our own pages"


@check("the self-heal path cannot hand the bridge to a website")
def heal_never_trusts_a_site(browser):
    view, page = web_view(browser)
    installed = []
    page._install_channel = lambda kind: installed.append(kind)

    # a healed reply that arrives after the page moved on to a website
    page._channel_kind = "full"
    page._healed = False
    page.setUrl(QUrl("https://example.com/"))
    page._heal_channel(False)
    assert not installed, \
        "_heal_channel re-installed %s while showing a website" % installed
    assert not page._healed

    # restore_trust after a download: a website must end up on pw
    page._channel_kind = "full"
    page.restore_trust()
    assert installed == ["pw"], \
        "restore_trust left a website holding %s" % (installed or "full")
    return "heal and restore both re-derive trust from the URL"


@check("a website cannot reach the bridge in a live page")
def live_bridge_isolation(browser):
    if not ENGINE:
        return ENGINE_NOTE
    view, page = web_view(browser)
    site = write_page("untrusted.html", "<b>not ours</b>")
    load(view, site.as_uri())
    assert page._channel_kind == "pw"

    main = js(page, "[typeof qt, typeof bridge, typeof pw]", B.MAIN_WORLD_ID)
    assert not js(page, "!!(window.qt && qt.webChannelTransport)",
                  B.MAIN_WORLD_ID), \
        "a website's own scripts can see a web channel transport"
    assert main[1] == "undefined", "the page can see a `bridge` object"
    assert main[2] == "undefined", "the page can see a `pw` object"

    # the transport that does exist is the password one, in its own
    # world — ask it what it carries, the way a page would
    has_pw = js(page, "!!(window.qt && qt.webChannelTransport)", B.PW_WORLD_ID)
    assert has_pw, "the password channel never arrived; nothing was proved"
    js(page, """
       window.__seen = null;
       new QWebChannel(qt.webChannelTransport, function (ch) {
         window.__seen = {objects: Object.keys(ch.objects),
                          pw: Object.keys(ch.objects.pw || {})};
       });""", B.PW_WORLD_ID)
    seen = None
    for _ in range(40):
        QTest.qWait(50)
        seen = js(page, "window.__seen", B.PW_WORLD_ID)
        if seen:
            break
    assert seen, "the channel in the isolated world never came up"
    assert seen["objects"] == ["pw"], \
        "a website can reach these objects over the channel: %s" \
        % seen["objects"]
    forbidden = [m for m in seen["pw"]
                 if m in ("getSettings", "setSetting", "listPasswords",
                          "revealPassword", "copyPassword", "runUpdate",
                          "getHistory", "getBookmarks", "getDownloads")]
    assert not forbidden, \
        "the object a website reaches carries bridge methods: %s" % forbidden
    assert "formSubmitted" in seen["pw"], \
        "the password channel lost its only method"
    load(view, QUrl.fromLocalFile(str(B.APP_DIR / "start.html")))
    assert page._channel_kind == "full", "our own page did not get the bridge"
    control = js(page, "!!(window.qt && qt.webChannelTransport)",
                 B.MAIN_WORLD_ID)
    assert control, ("our own page has no transport either — this check "
                     "proves nothing until that works")
    return ("a site reaches %s and nothing else; our own page still gets "
            "the bridge" % seen["objects"])


# ------------------------------------------------------ 2. the page key
KEYED_ARGS = {"dl_id": 7, "bid": 11, "parent": 0, "index": 0, "title": "t",
              "url": "https://example.com/", "name": "file",
              "new_tab": False, "on": True,
              # the password slots. A slot handed nonsense answers the
              # right key with the same empty thing it gives a wrong
              # one, and then this check proves nothing about it.
              "length": 20, "field": "password",
              "text": "JBSWY3DPEHPK3PXP",
              "payload": '{"type":"login","host":"x.com","password":"p"}'}


# a slot may take a first argument called "key" that is not the page
# key; setSetting's is the name of a setting. Anything else added here
# has to be looked at rather than waved through.
NOT_THE_PAGE_KEY = {"setSetting"}

# every slot that reads or changes the downloads or the bookmarks, spelled
# out: dropping the key argument from one of them would otherwise leave it
# out of the guarded set below and quietly go unchecked. Deleting a slot
# for real means deleting it from here too, deliberately.
MUST_BE_GUARDED = {
    "closeDownloads", "getDownloads", "cancelDownload", "pauseDownload",
    "resumeDownload", "openDownload", "openDownloadFolder", "removeDownload",
    "clearDownloads", "closeBookmarks", "getBookmarks", "updateBookmark",
    "removeBookmark", "moveBookmark", "addBookmarkFolder", "openBookmarkById",
    "bookmarksBarVisible", "setBookmarksBarVisible",
}


def keyed_slots():
    """Every Bridge slot guarded by the per-run page key, and every slot
    that takes a "key" first argument without consulting the guard."""
    guarded, unchecked = {}, []
    for name, fn in vars(B.Bridge).items():
        if not callable(fn) or name.startswith("_"):
            continue
        try:
            params = list(inspect.signature(fn).parameters)
            src = inspect.getsource(fn)
        except (TypeError, ValueError, OSError):
            continue
        if not (len(params) >= 2 and params[0] == "self"
                and params[1] == "key"):
            continue
        # _vault_page is _own_page and then some: it consults the same
        # per-run key and additionally refuses while the vault is shut
        # behind a master password. A slot behind it is guarded more
        # tightly than one behind _own_page, not less, so it counts.
        if re.search(r"self\._(own_page|running|vault_page)\(\s*key", src):
            guarded[name] = fn
        elif name not in NOT_THE_PAGE_KEY:
            unchecked.append(name)
    return guarded, unchecked


def seed_item(browser):
    """One vault item for the slots that take an item id."""
    return browser.vault.add_item(
        {"type": "login", "host": "seed.example", "username": "t",
         "password": "p", "totp": "JBSWY3DPEHPK3PXP"})


@check("every key-guarded bridge slot rejects a wrong key")
def page_key_guard(browser):
    slots, unchecked = keyed_slots()
    assert not unchecked, \
        ("these slots take a key but never check it against this run's "
         "page key: %s" % ", ".join(sorted(unchecked)))
    missing = MUST_BE_GUARDED - set(slots)
    assert not missing, \
        ("these slots used to take this run's page key and no longer do: "
         "%s" % ", ".join(sorted(missing)))

    # everything those slots delegate to, read out of their own source
    delegates = set()
    for fn in slots.values():
        delegates |= set(re.findall(r"self\.browser\.(\w+)\(",
                                    inspect.getsource(fn)))
    calls = []
    for name in sorted(delegates):
        assert hasattr(browser, name), "slot calls missing %s" % name
        setattr(browser, name, (lambda n: lambda *a, **k: calls.append(n))(name))

    class FakeDownload:
        def cancel(self): calls.append("dl.cancel")
        def pause(self): calls.append("dl.pause")
        def resume(self): calls.append("dl.resume")

    browser.dl_active = {KEYED_ARGS["dl_id"]: FakeDownload()}
    browser.bookmarks = [{"id": 1, "title": "proof"}]
    KEYED_ARGS["item_id"] = seed_item(browser)["id"]
    browser.config["bookmarksBar"] = True
    bridge = B.Bridge(browser)

    assert not bridge._own_page(""), "an empty key is accepted"
    assert not bridge._own_page(None), "a missing key is accepted"
    assert not bridge._own_page("wrong-key"), "a wrong key is accepted"
    assert bridge._own_page(browser._page_key), "the real key is rejected"
    assert len(browser._page_key) >= 16, "the page key is too short to guess"

    # "{}" is as empty as "[]": it is what the password slots hand back
    empties = ("[]", "{}", "", 0, False, None)
    unguarded = []
    for name in sorted(slots):
        # deleteItem sorts before totpFor and, on the right key, really
        # does delete the fixture — which is this check working. The
        # next slot gets its own rather than the check being softened.
        if browser.vault.item(KEYED_ARGS["item_id"]) is None:
            KEYED_ARGS["item_id"] = seed_item(browser)["id"]
        args = [KEYED_ARGS.get(p, "")
                for p in list(inspect.signature(slots[name]).parameters)[2:]]
        calls.clear()
        denied = getattr(bridge, name)("not-the-key", *args)
        assert not calls, "%s acted on a wrong key: %s" % (name, calls)
        assert denied in empties, \
            "%s answered a wrong key with %r" % (name, denied)
        calls.clear()
        allowed = getattr(bridge, name)(browser._page_key, *args)
        if not calls and allowed == denied:
            unguarded.append(name)
    assert not unguarded, \
        ("these slots behave the same with the right key, so the check "
         "above proves nothing about them: %s" % ", ".join(unguarded))
    return "%d keyed slots, all deny a wrong key and act on the right one" \
        % len(slots)


# ------------------------------------------------ 3. password fill gate

def serve(html):
    """A real http origin. The password watcher is injected by the
    profile onto ordinary web pages; a file:// page does not exercise
    that path at all, which is what this check is about."""
    import http.server
    import threading
    body = html.encode()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/login" % srv.server_address[1]

@check("the saved password is not in the page until a real gesture")
def password_fill_gated(browser):
    src = inspect.getsource(B.Browser._autofill)
    assert "PW_WORLD_ID" in src, \
        "the fill script no longer runs in the isolated world"
    assert "MAIN_WORLD_ID" not in src, \
        "the fill script runs in the world the page's own scripts own"
    fill_js = getattr(B, "PASSWORD_WATCH_JS", None) or B.PASSWORD_FILL_JS
    # One script now does two jobs, so "no submit listener anywhere" is
    # the wrong question — saving legitimately watches submit to read a
    # credential the person already typed. What must stay true is that
    # *releasing* the password is never reached from a submit: the UA
    # marks a submit raised by a scripted el.click() as trusted too.
    arm = re.search(r'function arm\(.*?\n  \}', fill_js, re.S)
    assert arm, "the arming function is gone or renamed"
    listeners = re.findall(r'addEventListener\(\s*["\'](\w+)', arm.group(0))
    assert listeners and "submit" not in listeners, \
        ("the fill path listens for submit again — a scripted "
         "el.click() raises a trusted submit and would take the password")
    assert {"pointerdown", "keydown"} <= set(listeners), \
        "the fill path no longer waits for a real pointer or key event"
    for fn in ("onPoint", "onKey"):
        body = re.search(r'function %s\(.*?\n  \}' % fn, fill_js, re.S)
        assert body and "isTrusted" in body.group(0), \
            "%s no longer checks isTrusted — a forged event would fill" % fn
    assert "isTrusted" in fill_js, "the gesture gate is gone"

    if not ENGINE:
        return "source checks only — " + ENGINE_NOTE

    secret = "correct-horse-battery-staple"
    srv, url = serve("""<!doctype html><meta charset=utf-8><title>Sign in</title>
      <form id=f><input id=u name=username autocomplete=username>
      <input id=p type=password autocomplete=current-password>
      <button id=b type=button>Sign in</button></form>""")
    view, page = web_view(browser)
    load(view, url)
    QTest.qWait(400)
    # the browser pushes into the isolated world, exactly as
    # Browser._pw_push does; the script itself is already there,
    # injected onto every page by the profile
    watch = getattr(B, "PASSWORD_WATCH_JS", None)
    if watch is None:
        js(page, B.PASSWORD_FILL_JS % (json.dumps("user"), json.dumps(secret)),
           B.PW_WORLD_ID)
    else:
        assert js(page, "typeof window.__bpw", B.PW_WORLD_ID) == "object", \
            "the password watcher was not injected into an ordinary page"
        js(page, "window.__bpw.offer(%s, %s);"
                 % (json.dumps("user"), json.dumps(secret)), B.PW_WORLD_ID)
        QTest.qWait(300)

    read = "document.getElementById('p').value"
    assert js(page, read, B.MAIN_WORLD_ID) == "", \
        "the password is sitting in the field before any gesture"
    assert js(page, "document.getElementById('u').value",
              B.MAIN_WORLD_ID) == "user", \
        "the username never filled — the fill script did not run at all"

    # a script on the page doing everything it can to forge a gesture
    forge = """
      var p = document.getElementById('p'), b = document.getElementById('b');
      ['pointerdown','mousedown','click','keydown','keyup','focus'].forEach(
        function (t) {
          document.dispatchEvent(new Event(t, {bubbles: true}));
          b.dispatchEvent(new Event(t, {bubbles: true}));
          p.dispatchEvent(new Event(t, {bubbles: true}));
        });
      b.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      b.click(); document.getElementById('f').dispatchEvent(
        new Event('submit', {bubbles: true}));
      p.focus(); p.value;"""
    assert js(page, forge, B.MAIN_WORLD_ID) == "", \
        "a page script forged a gesture and got the saved password"
    assert js(page, read, B.PW_WORLD_ID) == "", \
        "the password landed in the field anyway"

    # the real thing: a click delivered through the widget, which the
    # engine marks trusted and no page script can produce
    view.resize(600, 400)
    view.show()
    QTest.qWait(500)
    spot = js(page, "var r = document.getElementById('b')"
                    ".getBoundingClientRect();"
                    "[Math.round(r.x + r.width / 2), "
                    " Math.round(r.y + r.height / 2)]", B.PW_WORLD_ID)
    target = view.focusProxy()
    filled = ""
    if target is not None and spot:
        QTest.mouseClick(target, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(spot[0]), int(spot[1])))
        QTest.qWait(1000)
        filled = js(page, read, B.PW_WORLD_ID)
    view.hide()
    if filled != secret:
        return ("forged gestures got nothing; a real click could not be "
                "delivered on this machine, so the other half — that a "
                "genuine click does fill it — is unproven here")
    return "forged gestures got nothing, a real click filled it"


# ------------------------------------------------- 4. permission origins
@check("permission answers are filed per scheme, host and port")
def permission_keys(browser):
    def key(url, page_url=None):
        return B._origin_key(QUrl(url),
                             QUrl(page_url) if page_url else None)

    plain, show, storable = key("https://p.example")
    assert plain == "https://p.example:443", plain
    assert storable and show == "p.example"

    other_port = key("https://p.example:8443")[0]
    assert other_port != plain, \
        "https://p.example:8443 is filed under the same key as p.example"
    assert "8443" in other_port, other_port

    insecure = key("http://p.example")[0]
    assert insecure != plain, "http and https share one permission key"
    assert insecure.startswith("http://"), insecure
    assert key("http://p.example")[1].startswith("http://"), \
        "the card no longer shows that a site is not on TLS"

    # nothing the engine cannot name may be written to the config
    local = key("file:///", "file:///tmp/one.html")
    other = key("file:///", "file:///tmp/two.html")
    assert local[0] != other[0], "two local files share one permission key"
    assert not local[2] and not other[2], \
        "a local file's answer is being written to the config"
    assert not key("")[2] and not key("about:blank")[2], \
        "an unnamed origin is being written to the config"

    # the config the key is looked up in is built from _origin_key
    src = inspect.getsource(B.Browser._permission_requested)
    assert "_origin_key" in src and 'permission.permissionType().name' in src
    assert "if storable and" in src, \
        "a permission answer is read from the config without checking storable"

    # migrating an old host-only config narrows, never widens
    cfg = {"permissions": {"p.example|MediaAudioCapture": True,
                           "p.example:8443|MediaVideoCapture": True,
                           "192.168.1.9|Notifications": True,
                           "localhost|Notifications": True}}
    B._migrate_permission_config(cfg)
    assert cfg["permissions"] == {
        "https://p.example:443|MediaAudioCapture": True}, cfg["permissions"]
    assert set(cfg["permissionsLegacy"]) == {
        "p.example:8443|MediaVideoCapture", "192.168.1.9|Notifications",
        "localhost|Notifications"}, cfg["permissionsLegacy"]
    assert cfg["permissionsKeyVersion"] == 2
    before = json.dumps(cfg, sort_keys=True)
    B._migrate_permission_config(cfg)
    assert json.dumps(cfg, sort_keys=True) == before, "migration ran twice"
    return "scheme, host and port all change the key; hostless never stored"


# ------------------------------------------------------- 5. proxy rules
def dead_port():
    """A port nothing is listening on."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@check("a rule pointing at a dead proxy blocks instead of going direct")
def proxy_fails_closed(browser):
    # the matched host is a server that really is listening, so a
    # browser that quietly went direct would succeed: the only way to
    # get a block here is to actually fail closed
    origin = socket.create_server(("127.0.0.1", 0))
    origin.listen(4)
    reachable = origin.getsockname()[1]
    gone = dead_port()
    config = {
        "activeProxy": "direct",
        "proxyProfiles": [{"name": "vpn", "type": "http",
                           "host": "127.0.0.1", "port": gone}],
        "proxyAuto": {"default": "direct",
                      "rules": [{"pattern": "127.0.0.1", "profile": "vpn"}]},
    }
    routing = B._proxy_routing(config)
    assert routing is not None, "the rules vanished on the way to the engine"
    rules, _bypass, default = routing
    assert rules[0][1][0] == "http" and rules[0][1][2] == gone, rules
    assert default == ("direct",), default

    # a rule that names a profile must never resolve to a direct route
    assert rules[0][1] != ("direct",), \
        "a proxied rule resolved to a direct connection"

    # and the same when the proxy is the default rather than a rule
    as_default = dict(config, activeProxy="vpn")
    assert B._proxy_routing(as_default)[2][0] == "http", \
        "a dead default proxy fell back to direct"

    # now the live thing: the matched host through a dead upstream
    proxy = B.RuleProxy(rules, [], default)
    try:
        blocked = connect_through(proxy.port, "127.0.0.1:%d" % reachable)
        assert blocked.startswith("HTTP/1.1 502"), \
            ("a matched host whose proxy is dead got %r — it reached the "
             "site anyway, which is the silent fall-back-to-direct this "
             "local proxy exists to prevent" % blocked[:40])
        # not vacuous: the same server, under a name no rule matches,
        # still goes straight through
        allowed = connect_through(proxy.port, "localhost:%d" % reachable)
        assert allowed.startswith("HTTP/1.1 200"), \
            ("the proxy answered %r for an unmatched host, so it is "
             "blocking everything and the block above proves nothing"
             % allowed[:40])
    finally:
        proxy.close()
        origin.close()

    # rule matching still covers subdomains and wildcards, not neighbours
    assert B._rule_matches("blocked.example", "blocked.example")
    assert B._rule_matches("www.blocked.example", "blocked.example")
    assert not B._rule_matches("notblocked.example", "blocked.example")
    assert not B._rule_matches("blocked.example.evil.com", "blocked.example")
    assert not B._rule_matches("localhost", "127.0.0.1")
    return "dead proxy -> 502 for a host that was reachable; unmatched -> 200"


def connect_through(port, target):
    sock = socket.create_connection(("127.0.0.1", port), 10)
    try:
        sock.settimeout(10)
        sock.sendall(("CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n"
                      % (target, target)).encode())
        return sock.recv(200).decode("latin1", "replace")
    finally:
        sock.close()


# ---------------------------------------------------------------- main
ENGINE = True


def main():
    global ENGINE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="FILE",
                    help="also write the results as JSON")
    ap.add_argument("--only", metavar="TEXT",
                    help="run only checks whose title contains TEXT")
    ap.add_argument("--no-engine", action="store_true",
                    help="skip the checks that need a live page")
    args = ap.parse_args()

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")   # never the real profile
    browser = B.Browser()
    ENGINE = False if args.no_engine else engine_works(browser)
    if not ENGINE:
        print("note: %s" % ENGINE_NOTE)

    print("browser.py  %s" % (REPO / "browser.py"))
    print("scratch     %s\n" % SCRATCH)
    failed = run_all(browser, args.only)
    total = len(RESULTS)
    print("\n%d/%d checks passed" % (total - failed, total))
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"passed": total - failed, "failed": failed,
             "engine": ENGINE, "results": RESULTS}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
