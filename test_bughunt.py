#!/usr/bin/env python3
"""Bugs that no suite saw because nothing ever walked the line they sat on.

Found on 2026-11-08 by linting the modules rather than by running them:

  * the volume and boost flashes said ``"%d%" % n``, an incomplete
    format, so turning a video up raised ValueError before the level
    was remembered -- per-site volume never saved once;
  * ``link_preview`` called ``_is_short``, which was never written, so
    with "resolve short links" on every Alt-hover over a link raised;
  * ``_webauth_ux`` named ``QWebEngineWebAuthUxRequest`` without
    importing it, so every passkey and security key request raised
    NameError and the site waited forever; and a finished or cancelled
    request still told you to touch your key;
  * the private cookie jar is shared by every window but was dropped
    when THIS window's strip had no private tab left, so a private
    window, or a private tab popped out into a mini window, was left on
    a deleted jar and the next script run on it segfaulted the browser;
  * a closed second window was never deleted, so its tabs kept running
    hidden (a video still playing in a window you closed);
  * a config.json with a value of the wrong kind in it (a hand edit:
    the browser never writes one) stopped the browser before any
    window, on every launch, with nothing on screen to say why;
  * slots the internal pages call trusted the JSON's shape (a list
    where an object was meant raised), and browsingStats built one
    bucket per requested day, so a huge number took all the memory.

The static half guards the whole family (a name nothing binds, a
``%`` format that cannot format) across every module the browser
loads. The runtime half drives the three paths themselves."""
import ast
import builtins
import json
import os
import re
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


if os.environ.get("BH_CHILD") == "safe-start":
    import harness as H  # noqa: E402
    B = H.boot()
    app = H.app()
    srv = H.Server({"/media": "<title>Media</title>x"})
    B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                         "restoreTabs": False,
                                         "minFont": "big",
                                         "permissionsKeyVersion": "two"}))
    for old in B.CONFIG_FILE.parent.glob("config.json.broken-*"):
        old.unlink()
    try:
        fresh = B._first_window(lambda: B.Browser())
        raised = ""
    except Exception as e:  # noqa: BLE001
        fresh, raised = None, repr(e)
    check("a window comes up anyway", fresh is not None and raised == "",
          raised)
    aside = list(B.CONFIG_FILE.parent.glob("config.json.broken-*"))
    check("...the file is set aside, not lost",
          len(aside) == 1 and '"minFont": "big"' in aside[0].read_text())
    if fresh is not None:
        flashed = []
        fresh.flash = lambda text, *a, **k: flashed.append(text)
        fresh.show()
        H.spin(300)
        page = fresh.new_tab(url=None)
        H.load(page, srv.url("/media"))
        # the page itself: under a CPU quota H.load can return on the
        # start page's own load (see the harness note)
        H.wait_for(lambda: "/media" in page.url().toString(), 6000)
        try:
            H.wait_for(lambda: H.js(page, "document.title") == "Media", 6000)
        except AssertionError:
            pass
        check("...and the window it gave browses",
              H.js(page, "document.title") == "Media")
        H.spin(2200)
        check("...and says why the settings are the defaults",
              any(aside and aside[0].name in t for t in flashed))
    B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
    saved = B.CONFIG_FILE.read_text()

    def never():
        raise RuntimeError("not the config's fault")

    try:
        B._first_window(never)
        raised = ""
    except RuntimeError as e:
        raised = str(e)
    check("a failure the defaults do not fix is raised as before",
          raised == "not the config's fault")
    check("...and the config is put back untouched",
          B.CONFIG_FILE.read_text() == saved
          and len(list(B.CONFIG_FILE.parent.glob("config.json.broken-*")))
          == 1)
    print("child done", flush=True)
    sys.stdout.flush()
    os._exit(0)


MODULES = ["browser.py", "agent_bridge.py", "theme_web.py", "page_guard.py",
           "privacy.py", "adblock.py", "capture.py", "engine_pane.py",
           "notes.py", "agent.py", "agent_socket.py", "mpris.py", "qr.py",
           "tmpscratch.py"]

print("(1) every name the modules read is bound somewhere")


def unbound(tree):
    """Names loaded that nothing in the module binds: no import, def,
    class, assignment, argument, loop target or ``except ... as``.
    Coarse on purpose (a name bound anywhere counts everywhere), so it
    never cries wolf, and still catches a helper that was never
    written or a class that was never imported."""
    bound = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            bound.update(n.names)
    return sorted({(n.id, n.lineno) for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                   and n.id not in bound}, key=lambda x: x[1])


SPEC = re.compile(r"%(\([^)]*\))?[-#0 +]*(\*|\d+)?(\.(\*|\d+))?[hlL]?"
                  r"[diouxXeEfFgGcrsa%]")


def broken_formats(tree):
    """``"..." % x`` whose string has a % that is not a conversion."""
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod)
                and isinstance(n.left, ast.Constant)
                and isinstance(n.left.value, str)):
            rest = SPEC.sub("", n.left.value)
            if "%" in rest:
                out.append((n.lineno, n.left.value[:40]))
    return out


for name in MODULES:
    path = HERE / name
    if not path.exists():
        continue
    tree = ast.parse(path.read_text(), name)
    loose = unbound(tree)
    check("%s reads no name that nothing binds" % name, not loose, loose[:5])
    bad = broken_formats(tree)
    check("%s has no %% format that cannot format" % name, not bad, bad[:5])

print("\n(1b) the guard sees the bugs it is for")
probe = ast.parse("import os\ndef f(u):\n    return _is_short(u) or os.sep\n"
                  "def g(r):\n    return QWebEngineWebAuthUxRequest.X\n")
check("a helper that was never written is caught",
      ("_is_short", 3) in unbound(probe), unbound(probe))
check("...and a class that was never imported",
      ("QWebEngineWebAuthUxRequest", 5) in unbound(probe))
check("an incomplete percent is caught",
      broken_formats(ast.parse('x = "%d%" % 5')) != [])
check("...and a doubled one is not",
      broken_formats(ast.parse('x = "%d%%" % 5\ny = "%(a)s %.2fx" % 1')) == [])

import harness as H  # noqa: E402
B = H.boot()

app = H.app()
srv = H.Server({"/media": "<title>Media</title><audio id=a controls></audio>"})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)

print("\n(2) turning a video up says so and is remembered")
view = win.new_tab(url=None)
H.load(view, srv.url("/media"))
flashed = []
real_flash = win.flash
win.flash = lambda text, *a, **k: (flashed.append(text), real_flash(text, *a, **k))
win.config["mediaPerSite"] = True
win.config.pop("mediaSites", None)
win.media_volume(-0.5, view=view)
# the first media call puts the tool in the page; under a CPU quota that
# took longer than 4 s and the check read an empty list
H.wait_for(lambda: flashed, 15000)
check("the volume flash is a percentage", flashed[:1] == ["50%"], flashed)
host = view.url().host()
check("...and the level is kept for the site",
      (win.config.get("mediaSites") or {}).get(host, {}).get("volume") == 0.5,
      win.config.get("mediaSites"))
flashed.clear()
win.media_boost(2.0, view=view)
H.wait_for(lambda: flashed, 4000)
check("the boost flash is a percentage too",
      bool(flashed) and re.fullmatch(r"\d+%", flashed[0] or "") is not None,
      flashed)
win.flash = real_flash

print("\n(3) Alt over a link with short links resolved")
asked = []
real_expand = win.expand_short_link
win.expand_short_link = lambda url, view=None, then=None: asked.append(url)
win.config["expandShort"] = True
try:
    line = win.link_preview("https://bit.ly/abc")
    raised = ""
except Exception as e:  # noqa: BLE001
    line, raised = "", repr(e)
check("hovering a short link does not raise", raised == "", raised)
check("...and asks the shortener", asked == ["https://bit.ly/abc"], asked)
asked.clear()
win.link_preview(srv.url("/media"))
check("an ordinary link asks nobody", asked == [], asked)
check("a subdomain of a shortener counts",
      win.is_short_link("https://www.bit.ly/x")
      and not win.is_short_link("https://notbit.ly/x"))
win.config["expandShort"] = False
win.expand_short_link = real_expand

print("\n(4) a security key request")
S = B.QWebEngineWebAuthUxRequest.WebAuthUxState


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, f):
        self.slots.append(f)

    def disconnect(self):
        if not self.slots:
            raise TypeError("nothing connected")
        self.slots = []


class FakeKey:
    def __init__(self, state):
        self._state = state
        self.stateChanged = Signal()
        self.cancelled = False

    def state(self):
        return self._state

    def cancel(self):
        self.cancelled = True


flashed = []
win.flash = lambda text, *a, **k: flashed.append(text)
key = FakeKey(S.FinishTokenCollection)
try:
    win._webauth_ux(key)
    raised = ""
except Exception as e:  # noqa: BLE001
    raised = repr(e)
check("a key request is handled, not a NameError", raised == "", raised)
check("...it says the key is done", flashed == [B.UI_STRINGS["en"]["keyDone"]],
      flashed)
check("...and follows the request's state", len(key.stateChanged.slots) == 1)
flashed.clear()
key._state = S.Completed
win._webauth_ux(key)
check("a completed request asks for no touch", flashed == [], flashed)
check("...and its state can still be named",
      win.webauth_state_name() == "Completed", win.webauth_state_name())
key2 = FakeKey(S.Cancelled)
check("a cancelled request says no", win._webauth_ux(key2) is False)
check("...asks for no touch", flashed == [], flashed)
check("...and is not cancelled twice", key2.cancelled is False)
key3 = FakeKey(S.NotStarted)
win._webauth_ux(key3)
check("a request still waiting asks for the touch",
      flashed == [B.UI_STRINGS["en"]["keyTouch"]], flashed)
win.flash = real_flash

print("\n(5) the private jar outlives this strip's last private tab")
srv2 = H.Server({"/p": "<title>P</title>p",
                 "/t": "<title>T</title><script>window.n=0;"
                       "setInterval(function(){window.n++},100)</script>"})
mine = win.new_tab(url=srv2.url("/p"), private=True)
H.load(mine, srv2.url("/p"))
other = win.new_private_window()
H.spin(1200)
theirs = other.current()
H.load(theirs, srv2.url("/p"))
check("the private window is on the same jar",
      theirs.page().profile() is win.private_profile(create=False))
win.close_tab(win.tabs.indexOf(mine), ask=False)
H.spin(800)
check("closing the last private tab HERE keeps the jar for the window",
      win.private_profile(create=False) is not None)
check("...and that window's page still answers (it used to segfault)",
      H.js(theirs, "document.title") == "P")
other.close()
H.spin(800)
check("closing the private window lets the jar go",
      win.private_profile(create=False) is None)

print("\n(6) a popped-out private tab keeps the jar too")
out = win.new_tab(url=srv2.url("/p"), private=True)
H.load(out, srv2.url("/p"))
stay = win.new_tab(url=srv2.url("/p"), private=True)
H.load(stay, srv2.url("/p"))
mini = win.pop_out_tab(win.tabs.indexOf(out))
H.spin(300)
win.close_tab(win.tabs.indexOf(stay), ask=False)
H.spin(800)
check("the jar stays while the mini window shows a private page",
      win.private_profile(create=False) is not None)
check("...and its page still answers", H.js(out, "document.title") == "P")
mini.close()
H.spin(300)
win.close_tab(win.tabs.indexOf(out), ask=False)
H.spin(800)
check("once it is back and closed, the jar goes",
      win.private_profile(create=False) is None)

print("\n(7) a closed window leaves nothing running")
second = win.new_window(url=srv2.url("/t"))
H.spin(1200)
ticking = second.current()
H.load(ticking, srv2.url("/t"))
second.close()
H.spin(800)
try:
    ticking.page()
    gone = False
except RuntimeError:
    gone = True
check("its tabs are deleted, not left ticking hidden", gone)
srv2.stop()

print("\n(8) what the internal pages send is checked for shape")
br = win.bridge
for slot, arg in (("saveProxyProfile", "[]"), ("openHistoryUrls", "[]"),
                  ("openHistoryUrls", "null"), ("bookmarkHistoryUrls", "null"),
                  ("bookmarkHistoryUrls", "-1"), ("restoreHistoryDay", "[]"),
                  ("restoreHistoryDay", '{"since": "abc"}')):
    try:
        getattr(br, slot)(arg)
        raised = ""
    except Exception as e:  # noqa: BLE001
        raised = repr(e)
    check("%s(%s) is refused, not raised" % (slot, arg), raised == "", raised)
import time as _t  # noqa: E402
began = _t.time()
stats = json.loads(br.browsingStats(2 ** 31 - 1))
check("a huge day count is clamped instead of eating the memory",
      len(stats.get("days", [])) == 3660 and _t.time() - began < 5,
      len(stats.get("days", [])))

print("\n(9) a hand-edited config.json that will not build a window")
# its own process: main() builds the first window with no other window
# alive, and that is the case this is for
import subprocess  # noqa: E402
child = subprocess.run([sys.executable, __file__], capture_output=True,
                       text=True, timeout=300,
                       env=dict(os.environ, BH_CHILD="safe-start"))
for row in child.stdout.splitlines():
    if row.startswith(("  ok   ", "  FAIL ")):
        check(row[7:].split("  <")[0], row.startswith("  ok"), "")
check("the safe-start child ran to the end",
      "child done" in child.stdout,
      "" if "child done" in child.stdout
      else child.stdout[-300:] + child.stderr[-300:])

srv.stop()
print("\nall good" if not fails else "\nFAILED: %d" % len(fails))
sys.exit(1 if fails else 0)
