"""The private tab, and zoom from the keyboard.

Everything here is driven against a real HTTP server with real Qt
input, and nothing touches your data (see harness.boot). The point of
the private-tab half is not that the feature works - it is that
nothing is left behind, so almost every check below is a check that
some file, list or jar is still empty, with a normal tab doing the
same thing right next to it to prove the check can fail.
"""
import json
import os
import sys
import tempfile

import harness as H
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeySequence, QWheelEvent
from PyQt6.QtWidgets import QApplication

B = H.boot()
app = H.app()

COOKIE_PAGE = """<!doctype html><meta charset=utf-8><title>cookies</title>
<body style="font:16px sans-serif"><h1>cookie page</h1>
<script>
window.setTrace = function () {
  document.cookie = "trace=iwashere; path=/";
  localStorage.setItem("trace", "iwashere");
  sessionStorage.setItem("trace", "iwashere");
};
window.readTrace = function () {
  // JSON, not join: join turns a missing item into an empty string and
  // "nothing is there" would read exactly like "an empty value is there"
  return JSON.stringify([document.cookie, localStorage.getItem("trace"),
                         sessionStorage.getItem("trace")]);
};
window.readShared = function () {
  // what the JAR holds. sessionStorage belongs to the tab, not the jar,
  // so a second tab is not supposed to see it and asking would be a
  // check that fails for the wrong reason
  return JSON.stringify([document.cookie, localStorage.getItem("trace")]);
};
</script>
</body>"""

LOGIN_PAGE = """<!doctype html><meta charset=utf-8><title>Log in</title>
<body style="font:16px sans-serif">
<form method=GET action="/done">
  <input id=user name=username type=text autocomplete=username
         style="display:block;width:320px;height:32px">
  <input id=pw name=password type=password
         style="display:block;width:320px;height:32px">
  <button id=signin type=submit style="height:34px">Log in</button>
</form>
</body>"""

DOWNLOAD_PAGE = """<!doctype html><meta charset=utf-8><title>get a file</title>
<body style="font:16px sans-serif"><h1>download</h1>
<script>
window.grab = function (name) {
  var b = new Blob(["hello"], {type: "text/plain"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = name;
  document.body.appendChild(a);
  a.click();
};
</script>
</body>"""

SCRIPT_PAGE = """<!doctype html><meta charset=utf-8><title>a plugin</title>
<body style="font:16px sans-serif"><h1>plugin</h1>
<script>
window.grabScript = function () {
  var b = new Blob(["// nothing"], {type: "text/javascript"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = "sneaky.user.js";
  document.body.appendChild(a);
  a.click();
};
</script>
</body>"""

DONE = "<!doctype html><meta charset=utf-8><title>done</title><body>done"

srv = H.Server({"/cookies": COOKIE_PAGE, "/login": LOGIN_PAGE,
                "/get": DOWNLOAD_PAGE, "/script": SCRIPT_PAGE,
                "/done": DONE})

DL_DIR = tempfile.mkdtemp(prefix="browser-privdl-")

br = B.Browser()
br.config["savePasswords"] = True
br.config["askDownload"] = False
br.config["downloadDir"] = DL_DIR
br.config["zoom"] = 1.0
br.show()
H.spin(300)

RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % extra) if extra else ""))


def section(title):
    print("\n== %s ==" % title)


def show(view):
    br.tabs.setCurrentIndex(br.tabs.indexOf(view))
    H.spin(120)


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


def history_file():
    try:
        return B.HISTORY_FILE.read_text()
    except OSError:
        return ""


# ==================================================================== #
section("a private tab writes nothing down")
# ==================================================================== #
br.history = []
br.save_history()
br.known_hosts.clear()

priv = br.new_private_tab()
check("Ctrl+Shift+N gives a tab flagged private", priv.private is True)
check("its jar is off the record",
      priv.page().profile().isOffTheRecord())
check("its jar is not the main one", priv.page().profile() is not br.profile)
check("the password watcher is not in that jar at all",
      not priv.page().profile().scripts().find("password-watch"))
check("it is in the main jar, so the check above means something",
      bool(br.profile.scripts().find("password-watch")))

show(priv)
H.load(priv, url("/cookies", "localhost"))
H.js(priv, "window.setTrace()")
H.spin(200)
check("the private tab really did set them",
      H.js(priv, "window.readTrace()") == '["trace=iwashere","iwashere","iwashere"]',
      H.js(priv, "window.readTrace()"))

# a login, typed and submitted for real
H.load(priv, url("/login", "localhost"))
show(priv)
H.click(priv, "#user")
H.type_text(priv, "ghost@example.com")
H.click(priv, "#pw")
H.type_text(priv, "s3cret-in-private")
before_vault = len(br.vault.rows())
H.click(priv, "#signin")
H.spin(600)

check("no history file entry for the private tab",
      "localhost" not in history_file() and not br.history,
      repr(br.history)[:80])
check("no host kept for the address bar's suggestions",
      "localhost" not in br.known_hosts, repr(sorted(br.known_hosts)))
check("nothing was written to the vault",
      len(br.vault.rows()) == before_vault)
check("no save prompt is waiting", br._pw_pending is None)
check("no toast is up at all", br._toast is None)
check("the watcher is not even present in the page",
      H.js(priv, "typeof window.__bpw", B.PW_WORLD_ID) == "undefined",
      str(H.js(priv, "typeof window.__bpw", B.PW_WORLD_ID)))

br._save_groups()
saved = json.loads(B.CONFIG_FILE.read_text())
check("nothing of it in sessionTabs",
      "localhost" not in json.dumps(saved.get("sessionTabs") or {}),
      json.dumps(saved.get("sessionTabs") or {})[:120])
check("nothing of it in tabGroups",
      "localhost" not in json.dumps(saved.get("tabGroups") or []))

# ==================================================================== #
section("the same thing in a normal tab, so the checks above can fail")
# ==================================================================== #
normal = br.new_tab(url=url("/login"))
show(normal)
H.spin(600)
H.click(normal, "#user")
H.type_text(normal, "real@example.com")
H.click(normal, "#pw")
H.type_text(normal, "s3cret-in-the-open")
H.click(normal, "#signin")
H.spin(800)
check("a normal tab DOES get the save prompt",
      br._pw_pending is not None,
      repr(br._pw_pending and br._pw_pending.get("username")))
br._pw_dismiss()
check("a normal tab DOES leave history", bool(br.history), repr(br.history)[:80])
check("a normal tab DOES leave a host for the suggestions",
      "127.0.0.1" in br.known_hosts, repr(sorted(br.known_hosts)))

# ==================================================================== #
section("a normal tab cannot see what a private tab left")
# ==================================================================== #
seer = br.new_tab(url=url("/cookies", "localhost"))
show(seer)
H.spin(700)
seen = H.js(seer, "window.readTrace()")
check("no cookie and no localStorage in a normal tab", seen == '["",null,null]', str(seen))

# ==================================================================== #
section("two private tabs are one place")
# ==================================================================== #
priv2 = br.new_private_tab()
check("the second private tab shares the first one's jar",
      priv2.page().profile() is priv.page().profile())
show(priv2)
H.load(priv2, url("/cookies", "localhost"))
seen2 = H.js(priv2, "window.readShared()")
check("it sees the first private tab's cookie and storage",
      seen2 == '["trace=iwashere","iwashere"]', str(seen2))

# ==================================================================== #
section("a link out of a private tab stays private")
# ==================================================================== #
child = priv2.createWindow(
    B.QWebEnginePage.WebWindowType.WebBrowserBackgroundTab)
check("the tab a page opened is private too", getattr(child, "private", False))
check("and it is in the same jar",
      child.page().profile() is priv.page().profile())
br.close_tab(br.tabs.indexOf(child))

# ==================================================================== #
section("downloads")
# ==================================================================== #
before_dl = len(br.downloads)
show(priv2)
H.load(priv2, url("/get", "localhost"))
H.js(priv2, "window.grab('private-note.txt')")
H.spin(1200)
check("a private download is not written into the list",
      len(br.downloads) == before_dl, "%d -> %d" % (before_dl, len(br.downloads)))
check("and not into downloads.json",
      "private-note.txt" not in (
          B.DOWNLOADS_FILE.read_text() if B.DOWNLOADS_FILE.exists() else ""))
check("but the file was still fetched",
      os.path.exists(os.path.join(DL_DIR, "private-note.txt")),
      repr(sorted(os.listdir(DL_DIR))))

getter = br.new_tab(url=url("/get"))
show(getter)
H.spin(800)
H.js(getter, "window.grab('open-note.txt')")
H.spin(1200)
check("a normal download IS written into the list",
      any(e.get("name") == "open-note.txt" for e in br.downloads),
      repr([e.get("name") for e in br.downloads]))
br.close_tab(br.tabs.indexOf(getter))

# a page printed to PDF out of a private tab
before_dl = len(br.downloads)
show(priv2)
H.load(priv2, url("/cookies", "localhost"))
br.save_as_pdf()
H.spin(2500)
check("a PDF printed out of a private tab is not listed",
      len(br.downloads) == before_dl,
      repr([e.get("name") for e in br.downloads]))
check("and not in downloads.json",
      "cookie page" not in (
          B.DOWNLOADS_FILE.read_text() if B.DOWNLOADS_FILE.exists() else ""))
check("but the PDF was still written",
      any(f.endswith(".pdf") for f in os.listdir(DL_DIR)),
      repr(sorted(os.listdir(DL_DIR))))

# a userscript does not install itself out of a private tab
before_plugins = sorted(os.listdir(br.plugins_dir)) \
    if br.plugins_dir.exists() else []
H.load(priv2, url("/script", "localhost"))
H.js(priv2, "window.grabScript()")
H.spin(1500)
now_plugins = sorted(os.listdir(br.plugins_dir)) \
    if br.plugins_dir.exists() else []
check("a userscript does not install itself out of a private tab",
      now_plugins == before_plugins, repr(now_plugins))
check("it came down as an ordinary file instead",
      "sneaky.user.js" in os.listdir(DL_DIR), repr(sorted(os.listdir(DL_DIR))))
check("and left no download record either",
      not any(e.get("name") == "sneaky.user.js" for e in br.downloads))

# ==================================================================== #
section("closing the last private tab throws the jar away")
# ==================================================================== #
jar = priv.page().profile()
br.close_tab(br.tabs.indexOf(priv))
check("one private tab left: the jar stays",
      br.session_profiles.get(B.PRIVATE_SESSION) is jar)
check("a closed private tab is not on the reopen list",
      not any("localhost" in (e.get("url") or "")
              for e in br._closed_tabs),
      repr([e.get("url") for e in br._closed_tabs])[:140])

br.close_tab(br.tabs.indexOf(priv2))
H.spin(400)
check("the last one closed: the jar is gone",
      B.PRIVATE_SESSION not in br.session_profiles,
      repr(list(br.session_profiles)))

fresh = br.new_private_tab()
check("a new private tab gets a brand-new jar",
      fresh.page().profile() is not jar)
show(fresh)
H.load(fresh, url("/cookies", "localhost"))
seen3 = H.js(fresh, "window.readTrace()")
check("and the old cookie and storage are gone", seen3 == '["",null,null]', str(seen3))
br.close_tab(br.tabs.indexOf(fresh))
H.spin(300)

# ==================================================================== #
section("it is obvious a tab is private")
# ==================================================================== #
mark = br.new_private_tab()
show(mark)
check("the badge beside the address bar is up", br.privlbl.isVisible())
check("the window says so in its name",
      br._ui_str("privateTab") in br.windowTitle(), br.windowTitle())
i = br.tabs.indexOf(mark)
check("the tab has a mark of its own", not br.tabs.tabIcon(i).isNull())
check("and a tooltip that says what it is",
      br._ui_str("privateTip") in br.tabs.tabToolTip(i),
      br.tabs.tabToolTip(i))
show(normal)
check("the badge goes away on a normal tab", not br.privlbl.isVisible())
br.close_tab(br.tabs.indexOf(mark))
H.spin(200)
check("and the window name goes back", br.windowTitle() == "browser",
      br.windowTitle())

# ==================================================================== #
section("zoom")
# ==================================================================== #
br.config["zoom"] = 1.0
zoomer = br.new_tab(url=url("/cookies"))
show(zoomer)
H.spin(700)
check("a fresh tab sits at the configured default",
      abs(zoomer.zoomFactor() - 1.0) < 1e-6, zoomer.zoomFactor())

br.zoom_by(1)
check("Ctrl+= steps to 110%", abs(zoomer.zoomFactor() - 1.1) < 1e-6,
      zoomer.zoomFactor())
br.zoom_by(1)
check("again to 125%", abs(zoomer.zoomFactor() - 1.25) < 1e-6,
      zoomer.zoomFactor())
br.zoom_by(-1)
br.zoom_by(-1)
br.zoom_by(-1)
check("three times Ctrl+- lands on 90%",
      abs(zoomer.zoomFactor() - 0.9) < 1e-6, zoomer.zoomFactor())
check("the level is shown", br._zoom_badge is not None
      and br._zoom_badge.isVisible() and br._zoom_badge.text() == "90%",
      br._zoom_badge.text())
br.zoom_reset()
check("Ctrl+0 goes back to the configured default",
      abs(zoomer.zoomFactor() - 1.0) < 1e-6, zoomer.zoomFactor())

for _ in range(30):
    br.zoom_by(1)
check("the top of the range holds at 500%",
      abs(zoomer.zoomFactor() - 5.0) < 1e-6, zoomer.zoomFactor())
for _ in range(40):
    br.zoom_by(-1)
check("the bottom holds at 25%",
      abs(zoomer.zoomFactor() - 0.25) < 1e-6, zoomer.zoomFactor())
br.zoom_reset()

# zoom is the tab's, not the browser's
other = br.new_tab(url=url("/cookies"))
show(other)
H.spin(700)
show(zoomer)
br.zoom_by(1)
br.zoom_by(1)
check("zooming one tab leaves the next one alone",
      abs(zoomer.zoomFactor() - 1.25) < 1e-6
      and abs(other.zoomFactor() - 1.0) < 1e-6,
      "%s / %s" % (zoomer.zoomFactor(), other.zoomFactor()))

# the slider and the shortcut cannot disagree
br.bridge.setSetting("zoom", "1.5")
H.spin(200)
check("moving the slider puts every tab there, zoomed ones included",
      abs(zoomer.zoomFactor() - 1.5) < 1e-6
      and abs(other.zoomFactor() - 1.5) < 1e-6,
      "%s / %s" % (zoomer.zoomFactor(), other.zoomFactor()))
check("and the config agrees", abs(br.zoom_default() - 1.5) < 1e-6)
br.zoom_by(1)
check("a step from there is a step off the slider's value",
      abs(zoomer.zoomFactor() - 1.75) < 1e-6, zoomer.zoomFactor())
br.zoom_reset()
check("Ctrl+0 returns to whatever the slider now says",
      abs(zoomer.zoomFactor() - 1.5) < 1e-6, zoomer.zoomFactor())

# The browser's own pages are never zoomed a tab at a time - they sit
# where the Page zoom slider says and move with it, which is what the
# slider has always meant. The slider is capped at 200% in Settings, so
# it can never do to them what the keyboard ladder's 500% would.
own = br.new_tab()
show(own)
H.spin(700)
check("a tab on one of the browser's own pages sits at the slider's level",
      own.url().scheme() == "file" and abs(own.zoomFactor() - 1.5) < 1e-6,
      "%s %s" % (own.url().scheme(), own.zoomFactor()))
br.zoom_by(1)
check("and a zoom shortcut does not move it",
      abs(own.zoomFactor() - 1.5) < 1e-6, own.zoomFactor())
check("it was not given a level of its own either",
      getattr(own, "_zoom", None) is None, repr(getattr(own, "_zoom", None)))
br.bridge.setSetting("zoom", "2.0")
H.spin(200)
check("but the slider does move it",
      abs(own.zoomFactor() - 2.0) < 1e-6, own.zoomFactor())
br.open_pane("settings")
H.spin(800)
check("a pane opens at the slider's level, not at 100%",
      abs(br._pane.view.zoomFactor() - 2.0) < 1e-6,
      br._pane.view.zoomFactor())
br.bridge.setSetting("zoom", "1.25")
H.spin(300)
check("and moves when the slider does, while it is open",
      abs(br._pane.view.zoomFactor() - 1.25) < 1e-6,
      br._pane.view.zoomFactor())
br.close_pane()
H.spin(200)
br.bridge.setSetting("zoom", "1.0")
H.spin(150)

# ==================================================================== #
section("the keys themselves are bound")
# ==================================================================== #
bound = {QKeySequence(k).toString()
         for sc in br.findChildren(B.QShortcut) for k in sc.keys()}
for want in ("Ctrl+=", "Ctrl++", "Ctrl+-", "Ctrl+0", "Ctrl+Shift+N"):
    check("%s is bound" % want,
          QKeySequence(want).toString() in bound,
          sorted(x for x in bound if "Ctrl" in x)[:6])

# and a real Ctrl+wheel over the page
wheeler = br.new_tab(url=url("/cookies"))
show(wheeler)
H.spin(700)
br.bridge.setSetting("zoom", "1.0")
H.spin(150)
target = wheeler.focusProxy() or wheeler
for delta, name, want in ((120, "Ctrl+wheel up zooms in", 1.1),
                          (-120, "Ctrl+wheel down zooms out", 1.0)):
    QApplication.sendEvent(target, QWheelEvent(
        QPointF(20, 20), QPointF(target.mapToGlobal(QPoint(20, 20))),
        QPoint(0, delta), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase, False))
    H.spin(150)
    check(name, abs(wheeler.zoomFactor() - want) < 1e-6,
          wheeler.zoomFactor())



# ==================================================================== #
section("zoom keeps its hands off the tab behind a pane")
# ==================================================================== #
br.bridge.setSetting("zoom", "1.0")
H.spin(150)
behind = br.new_tab(url=url("/cookies"))
show(behind)
H.spin(700)
br.zoom_by(1)
check("the tab in front zooms normally",
      abs(behind.zoomFactor() - 1.1) < 1e-6, behind.zoomFactor())
for pane in ("settings", "history", "downloads", "bookmarks"):
    br.open_pane(pane)
    H.spin(500)
    was = behind.zoomFactor()
    br.zoom_by(1)
    br.zoom_by(-1)
    br.zoom_reset()
    check("with the %s pane up, no shortcut reaches the tab behind it"
          % pane, abs(behind.zoomFactor() - was) < 1e-6,
          "%s -> %s" % (was, behind.zoomFactor()))
    check("...and _zoom_target says so out loud",
          br._zoom_target() is None, repr(br._zoom_target()))
    br.close_pane()
    H.spin(250)
check("the tab is still where the shortcut left it",
      abs(behind.zoomFactor() - 1.1) < 1e-6, behind.zoomFactor())


def wheel(widget, delta):
    """A real Ctrl+wheel on a widget."""
    QApplication.sendEvent(widget, QWheelEvent(
        QPointF(20, 20), QPointF(widget.mapToGlobal(QPoint(20, 20))),
        QPoint(0, delta), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase, False))
    H.spin(150)


# a pane is a WebView too, so Ctrl+wheel inside one used to be caught
# by the same filter and handed to the tab hidden behind it
br.open_pane("history")
H.spin(600)
was_tab = behind.zoomFactor()
was_pane = br._pane.view.zoomFactor()
pane_target = br._pane.view.focusProxy() or br._pane.view
wheel(pane_target, 240)
check("Ctrl+wheel inside a pane does not touch the tab behind it",
      abs(behind.zoomFactor() - was_tab) < 1e-6,
      "%s -> %s" % (was_tab, behind.zoomFactor()))
br.close_pane()
H.spin(300)
br.open_pane("history")
H.spin(600)
check("and the pane is back at the slider's level next time it opens",
      abs(br._pane.view.zoomFactor() - was_pane) < 1e-6,
      "%s -> %s" % (was_pane, br._pane.view.zoomFactor()))
br.close_pane()
H.spin(250)

# ==================================================================== #
section("Ctrl+wheel is the engine's, and the browser reads it back")
# ==================================================================== #
# Nothing in this file intercepts the wheel: Chromium climbs this very
# ladder itself, where the wheel actually arrives, and a Python event
# filter on the widget it arrives at destabilises the engine. What is
# under test is that the browser notices what the engine did.
br.bridge.setSetting("zoom", "1.0")
H.spin(150)
fine = br.new_tab(url=url("/cookies"))
show(fine)
H.spin(700)
fine_target = fine.focusProxy() or fine
br.zoom_reset()
wheel(fine_target, 120)
after = fine.zoomFactor()
check("Ctrl+wheel moves the page up the ladder",
      any(abs(after - z) < 1e-3 for z in B.ZOOM_STEPS) and after > 1.0,
      after)
check("and the level it reads at is the one the wheel set",
      abs(br.zoom_now(fine) - after) < 1e-9, br.zoom_now(fine))

# the two things the browser has to get right about a level it did not
# set: keep it, and still be able to take it away again
H.load(fine, url("/cookies?again=1"))
H.spin(400)
check("a navigation does not throw a wheeled level away",
      abs(fine.zoomFactor() - after) < 1e-3, fine.zoomFactor())
check("...because the tab has adopted it as its own",
      getattr(fine, "_zoom", None) is not None
      and abs(fine._zoom - after) < 1e-3, repr(getattr(fine, "_zoom", None)))
br.zoom_by(1)
check("Ctrl+= carries on from where the wheel left off",
      fine.zoomFactor() > after + 1e-3, fine.zoomFactor())
br.zoom_reset()
check("and Ctrl+0 still puts it back to the slider's level",
      abs(fine.zoomFactor() - 1.0) < 1e-6, fine.zoomFactor())
br.bridge.setSetting("zoom", "1.25")
H.spin(200)
check("and the slider still reaches a tab that had been wheeled",
      abs(fine.zoomFactor() - 1.25) < 1e-6, fine.zoomFactor())
br.bridge.setSetting("zoom", "1.0")
H.spin(200)
br.close_tab(br.tabs.indexOf(fine))
H.spin(150)

# ==================================================================== #
section("the account chooser is blind in a private tab")
# ==================================================================== #
ACCTS = [("one@example.com", "pw-of-account-one"),
         ("two@example.com", "pw-of-account-two")]
EVALS = []          # every script string handed to a page we watch


def watch(page):
    """Record every script evaluated in this page. The DOM is not the
    thing under test here: a password put into a script for the
    off-the-record renderer has already left the vault and reached the
    engine, whether or not anything in that page happens to catch it."""
    real = page.runJavaScript

    def rec(*a, **k):
        if a and isinstance(a[0], str):
            EVALS.append(a[0])
        return real(*a, **k)
    page.runJavaScript = rec


def seed(host):
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    br._acct_auto.clear()
    br._close_account_chooser()
    for i, (u, p) in enumerate(ACCTS):
        br.vault.set_entry(host, "http", u, p)
        br.vault.get(host, u)["used"] = 1000 + i
    br.vault._save()


def vault_bytes():
    """The vault file exactly as it is on disk. Scrambled, so it is
    never read for content - it is compared with itself. Every save
    picks a fresh nonce, so one byte of difference means _save ran."""
    try:
        return br.vault.provider.file.read_bytes()
    except (OSError, AttributeError):
        return b""


PHOST = B.PasswordVault.normalize_host("localhost")
NHOST = B.PasswordVault.normalize_host("127.0.0.1")
seed(PHOST)
seed(NHOST)          # both hosts, so neither tab is the odd one out
for u, p in ACCTS:
    br.vault.set_entry(PHOST, "http", u, p)
br.vault._save()

pv = br.new_private_tab()
show(pv)
H.load(pv, url("/login", "localhost"))
watch(pv.page())

saves = {"n": 0}
touches = []
real_save, real_touch = br.vault._save, br.vault.touch


def counted_save(*a, **k):
    saves["n"] += 1
    return real_save(*a, **k)


def counted_touch(*a, **k):
    touches.append(a)
    return real_touch(*a, **k)


br.vault._save = counted_save
br.vault.touch = counted_touch
del EVALS[:]

check("nothing is offered for a private tab",
      br._account_names(pv) == [], repr(br._account_names(pv)))
br._sync_acct()
check("the @ handle is not in the address bar",
      not br.acctbtn.isVisible())
br.open_account_chooser()
H.spin(300)
check("Ctrl+Shift+M raises nothing", br._acct_chooser is None)
br._maybe_offer_accounts(pv.page(), PHOST, "http", "username", False)
H.spin(300)
check("and the watcher's own offer raises nothing either",
      br._acct_chooser is None)

# the panel's own delivery path, called straight, as if a panel raised
# over a normal tab were somehow answered while a private one is there.
# The file is read here and not further up: the spins above turn the
# event loop, and a save somebody else had queued landing in one of
# them would be laid at this call's door.
before_bytes = vault_bytes()
saves["n"] = 0
del touches[:]
br._account_chosen(pv.page(), PHOST, "http", ACCTS[0][0])
H.spin(300)
check("_account_chosen writes nothing to the vault", saves["n"] == 0,
      saves["n"])
check("it does not so much as touch a row", touches == [], repr(touches))
check("the vault file on disk is byte for byte what it was",
      vault_bytes() == before_bytes)
secrets = [p for _, p in ACCTS] + [u for u, _ in ACCTS]
leaked = [e for e in EVALS if any(x in e for x in secrets)]
check("no saved name or password was ever put into a script for the "
      "private renderer", not leaked, repr(leaked)[:200])
check("the fill call was not made at all",
      not any("__bpw" in e and "choose" in e for e in EVALS),
      repr([e[:60] for e in EVALS])[:200])
check("the DOM stayed empty too",
      H.js(pv, "document.querySelector('#pw').value") == "",
      repr(H.js(pv, "document.querySelector('#pw').value")))

# ==================================================================== #
section("the same panel over a normal tab, so the checks above can fail")
# ==================================================================== #
nv = br.new_tab(url=url("/login"))
show(nv)
H.spin(900)
watch(nv.page())
del EVALS[:]
check("two accounts are on offer for a normal tab",
      len(br._account_names(nv)) == 2, repr(br._account_names(nv)))
br._sync_acct()
check("the @ handle IS in the address bar", br.acctbtn.isVisible())
br.open_account_chooser()
H.spin(400)
check("Ctrl+Shift+M DOES raise the panel", br._acct_chooser is not None)
picked = None
if br._acct_chooser is not None:
    for b in br._acct_chooser.buttons:
        if b.text() == ACCTS[0][0]:
            picked = b
if picked is not None:
    H.press(picked)
H.spin(600)
check("picking a name DOES put its password into a script",
      any(ACCTS[0][1] in e for e in EVALS),
      repr([e[:50] for e in EVALS])[:160])
check("and DOES write the vault", saves["n"] > 0, saves["n"])
br.vault._save, br.vault.touch = real_save, real_touch
br._close_account_chooser()
br.close_tab(br.tabs.indexOf(nv))
br.close_tab(br.tabs.indexOf(pv))
H.spin(300)

# ==================================================================== #
section("the badge is on the toolbar row, wherever the row is")
# ==================================================================== #
badged = br.new_private_tab()
show(badged)
H.spin(200)
check("the badge is up", br.privlbl.isVisible())
check("it is on the nav row itself",
      br.privlbl.parentWidget() is br.navbar,
      repr(br.privlbl.parentWidget()))
order = [n for n in br.toolbar_layout() if n != "address"] + ["address"]
br.set_toolbar_buttons(order)
H.spin(250)
check("it survives the toolbar being rebuilt", br.privlbl.isVisible())
lay = br._navlay
idx = {lay.itemAt(i).widget(): i for i in range(lay.count())}
check("and still sits in front of the address bar, wherever that is",
      idx.get(br.privlbl) is not None
      and idx.get(br.privlbl) == idx.get(br.urlbar) - 1,
      "%s / %s" % (idx.get(br.privlbl), idx.get(br.urlbar)))
br.reset_toolbar()
H.spin(250)
check("and after a reset to the shipped set", br.privlbl.isVisible())

# the window's own name must not be the badge's to skip
saved_lbl = br.privlbl
br.privlbl = None
br.setWindowTitle("wrong")
br._update_private_marks()
check("the window says Private even with no badge built yet",
      br._ui_str("privateTab") in br.windowTitle(), br.windowTitle())
br.privlbl = saved_lbl

# ==================================================================== #
section("changing language with a pane open")
# ==================================================================== #
br.open_pane("settings")
H.spin(600)
crashed = ""
try:
    br.apply_language()
except Exception as exc:                                 # noqa: BLE001
    crashed = "%s: %s" % (type(exc).__name__, exc)
H.spin(600)
check("apply_language does not fall over", crashed == "", crashed)
check("the pane is still there", br.pane_open("settings"))
check("and the private tab is still marked",
      br._ui_str("privateTab") in br.windowTitle(), br.windowTitle())
br.close_pane()
H.spin(250)
check("nothing anywhere still talks about _settings_pane",
      not hasattr(br, "_settings_pane"))

# ==================================================================== #
section("permissions a private tab gives are its own")
# ==================================================================== #
br.config.setdefault("permissions", {})
PERM_KEY = "http://localhost|MediaAudioCapture"
br.config["permissions"][PERM_KEY] = True
br._private_perms["never|X"] = True
check("a private tab has a book of its own",
      br._private_perms != {} and "never|X" not in br._session_perms)
br.close_tab(br.tabs.indexOf(badged))
H.spin(400)
check("the last private tab closing empties it",
      br._private_perms == {}, repr(br._private_perms))
check("...and takes the jar with it",
      B.PRIVATE_SESSION not in br.session_profiles)
br.config["permissions"].pop(PERM_KEY, None)

# ==================================================================== #
section("a private tab leaves nothing in the files on disk")
# ==================================================================== #
def file_text(path):
    try:
        return path.read_text()
    except OSError:
        return ""


# Normal tabs on both hostnames have been open for most of this run, so
# the files already have their hosts in them. The evidence looked for
# here is evidence only the private tab could have left: hosts.json is
# emptied first and nothing else navigates afterwards, and a query
# nobody else has ever asked for stands in for the rest.
MARK = "ghostonly"
br.known_hosts.clear()
try:
    B.HOSTS_FILE.unlink()
except OSError:
    pass
br.history = []
br.save_history()

leaver = br.new_private_tab()
show(leaver)
H.load(leaver, url("/cookies?" + MARK + "=1", "localhost"))
H.js(leaver, "window.setTrace()")
H.spin(400)
br._save_groups()
br.save_history()
br.save_downloads()
H.spin(200)

check("no host of its own in hosts.json",
      "localhost" not in file_text(B.HOSTS_FILE),
      file_text(B.HOSTS_FILE)[:120] or "(no file)")
check("nothing of it in history.json",
      MARK not in file_text(B.HISTORY_FILE) and not br.history,
      repr(br.history)[:100])
check("nothing of it in downloads.json",
      MARK not in file_text(B.DOWNLOADS_FILE))
check("nothing of it in the config's sessionTabs",
      MARK not in json.dumps(
          json.loads(file_text(B.CONFIG_FILE) or "{}").get("sessionTabs")
          or {}))
check("nothing of it in the config's tabGroups",
      MARK not in json.dumps(
          json.loads(file_text(B.CONFIG_FILE) or "{}").get("tabGroups")
          or []))

# ...and the same page in a normal tab lands in all of them, so the
# five checks above are checks and not a spelling mistake
opener = br.new_tab(url=url("/cookies?" + MARK + "=2"))
show(opener)
H.spin(900)
br._save_groups()
br.save_history()
H.spin(200)
check("a normal tab on the same page DOES land in hosts.json",
      "127.0.0.1" in file_text(B.HOSTS_FILE),
      file_text(B.HOSTS_FILE)[:120] or "(no file)")
check("and in history.json", MARK in file_text(B.HISTORY_FILE))
check("and in the config's sessionTabs",
      MARK in json.dumps(
          json.loads(file_text(B.CONFIG_FILE) or "{}").get("sessionTabs")
          or {}))
br.close_tab(br.tabs.indexOf(opener))
H.spin(200)
show(leaver)
check("no login of its own reached the vault",
      not any(e.get("username") == "ghost@example.com"
              for e in br.vault.logins()),
      repr([e.get("username") for e in br.vault.logins()])[:140])

# ==================================================================== #
section("Ctrl+D from a private tab: a deliberate exception")
# ==================================================================== #
# Asking for a bookmark is him saying "keep this", the same as asking
# for a download. What a private tab refuses to keep is the record it
# would have kept without being asked.
before_bm = len(br.bookmarks)
br.toggle_bookmark()
H.spin(300)
check("Ctrl+D still saves a bookmark from a private tab",
      len(br.bookmarks) == before_bm + 1,
      "%d -> %d" % (before_bm, len(br.bookmarks)))
br.toggle_bookmark()
H.spin(300)
check("and Ctrl+D again takes it away", len(br.bookmarks) == before_bm)

# ==================================================================== #
section("a private download's name is spoken for while it is in flight")
# ==================================================================== #
scratch = tempfile.mkdtemp(prefix="browser-privrace-")
first = br._unique_download_name("race.txt", scratch, hold=True)
second = br._unique_download_name("race.txt", scratch)
check("the private one gets the plain name", first == "race.txt", first)
check("a normal one racing it does NOT get the same name",
      second == "race (1).txt", second)
check("the held name is on the list", "race.txt" in br._dl_held,
      repr(sorted(br._dl_held))[:120])

before_dl = len(br.downloads)
H.load(leaver, url("/get", "localhost"))
H.js(leaver, "window.grab('held.txt')")
H.spin(1200)
check("a real private download holds its name too",
      "held.txt" in br._dl_held, repr(sorted(br._dl_held))[:160])
check("and still keeps no row", len(br.downloads) == before_dl)
br.close_tab(br.tabs.indexOf(leaver))
H.spin(300)

# ==================================================================== #
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
srv.stop()
# Qt takes the process down now and then while it disposes of the web
# engine, after the last line of the test has already run - the same
# teardown crash test_theme.py has had for a while, on code that was
# never touched. Every check is in by this point, so the verdict is
# handed over from here rather than through an interpreter shutdown
# that is allowed to change it.
sys.stdout.flush()
os._exit(1 if bad else 0)
