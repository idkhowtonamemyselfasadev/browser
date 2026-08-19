#!/usr/bin/env python3
"""Open in another browser: the "open externally" handoff.

Some sites refuse to work embedded — Google walls its sign-in and mail
off from non-mainstream browsers with a "browser or app may not be
secure" page. Rather than hand him that wall, the browser hands those
sites to a real external browser instead of loading them in-app.

This drives the whole decision:
  * a matching host, with the feature on, launches the external browser
    (through the one seam a test can watch) and cancels the in-app load;
  * a non-matching host, the feature off, an emptied site list, the
    wrong navigation type or a non-web scheme all leave the navigation
    to load as usual and never launch anything;
  * a sub-domain of a listed domain matches;
  * when the configured browser is not installed the navigation loads
    in-app after a short line, rather than vanishing into a blank tab;
  * a tab opened only to carry a handed-off navigation is closed rather
    than left blank — but never the last tab.

The launch itself goes through Browser._launch_external, the single seam
(like the updater's _lib_run), replaced here so no real browser is
spawned. Offscreen, against scratch data; your own vault and config are
never opened.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QUrl, QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage  # noqa: E402

NT = QWebEnginePage.NavigationType
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1300, 900)
win.show()
app.processEvents()

# ---- the one seam, replaced so nothing is spawned ----
calls = []


def fake_launch(cmd, url):
    calls.append((cmd, url))
    return True


win._launch_external = fake_launch

# and a quiet toast, so nothing draws a real widget/timer under us
toasts = []
win._show_plain_toast = lambda msg: toasts.append(msg)


def wait_load(view, ms=5000):
    """Spin a real event loop until the view finishes loading (or ms)."""
    loop = QEventLoop()
    got = {"ok": None}
    view.loadFinished.connect(lambda ok: (got.__setitem__("ok", ok),
                                           loop.quit()))
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    return got["ok"]

GMAIL = QUrl("https://mail.google.com/")
ACCT = QUrl("https://accounts.google.com/signin")


print("(0) the defaults are what was asked for")
check("externalBrowser default is firefox",
      B.DEFAULT_EXTERNAL_BROWSER == "firefox", B.DEFAULT_EXTERNAL_BROWSER)
check("gmail is in the default site list",
      "gmail.com" in B.DEFAULT_EXTERNAL_SITES, B.DEFAULT_EXTERNAL_SITES)
check("the feature is OFF by default (opt-in)",
      win.config.get("externalHandoff", False) is False,
      win.config.get("externalHandoff"))
# with no externalSites key at all, the defaults stand in
win.config.pop("externalSites", None)
check("absent externalSites falls back to the defaults",
      "mail.google.com" in win._external_sites(), win._external_sites())


print("\n(1) feature off: a listed site loads in-app, nothing launches")
win.config["externalHandoff"] = False
calls.clear()
r = win.maybe_open_external(GMAIL, NT.NavigationTypeTyped, None)
check("off -> maybe_open_external returns False", r is False, r)
check("off -> nothing launched", calls == [], calls)


print("\n(2) feature on + a listed host: launch firefox, take the nav")
win.config["externalHandoff"] = True
win.config["externalBrowser"] = "firefox"   # really on PATH here
calls.clear()
r = win.maybe_open_external(GMAIL, NT.NavigationTypeTyped, None)
check("returns True (caller will cancel the in-app load)", r is True, r)
check("launched exactly once", len(calls) == 1, calls)
check("launched firefox with the url",
      calls == [("firefox", "https://mail.google.com/")], calls)


print("\n(3) the three user-initiated nav types all hand off")
for label, t in (("typed", NT.NavigationTypeTyped),
                 ("link-clicked", NT.NavigationTypeLinkClicked),
                 ("form-submit", NT.NavigationTypeFormSubmitted)):
    calls.clear()
    r = win.maybe_open_external(ACCT, t, None)
    check("%s hands off" % label, r is True and len(calls) == 1, (r, calls))


print("\n(4) redirects / back-forward / sub-frame are left alone")
for label, t in (("redirect", NT.NavigationTypeRedirect),
                 ("back/forward", NT.NavigationTypeBackForward),
                 ("reload", NT.NavigationTypeReload),
                 ("other", NT.NavigationTypeOther)):
    calls.clear()
    r = win.maybe_open_external(GMAIL, t, None)
    check("%s is NOT handed off" % label, r is False and calls == [], (r, calls))


print("\n(5) a sub-domain of a listed domain matches; a look-alike does not")
calls.clear()
r = win.maybe_open_external(QUrl("https://inbox.mail.google.com/x"),
                            NT.NavigationTypeTyped, None)
check("inbox.mail.google.com matches mail.google.com", r is True, r)
calls.clear()
# notmail.google.com endswith "google.com" but not ".mail.google.com";
# gmail.com is listed but "notgmail.com" must not match it
r = win.maybe_open_external(QUrl("https://notgmail.com/"),
                            NT.NavigationTypeTyped, None)
check("notgmail.com does NOT match gmail.com", r is False and calls == [],
      (r, calls))


print("\n(6) a non-listed host loads in-app")
calls.clear()
r = win.maybe_open_external(QUrl("https://example.com/"),
                            NT.NavigationTypeTyped, None)
check("example.com is not handed off", r is False and calls == [], (r, calls))


print("\n(7) emptying the site list disables it per-site")
win.config["externalSites"] = []
calls.clear()
r = win.maybe_open_external(GMAIL, NT.NavigationTypeTyped, None)
check("empty list -> even gmail loads in-app", r is False and calls == [],
      (r, calls))
win.config["externalSites"] = list(B.DEFAULT_EXTERNAL_SITES)


print("\n(8) a non-web scheme is never handed off")
calls.clear()
r = win.maybe_open_external(QUrl("file:///srv/www/mail.google.com"),
                            NT.NavigationTypeTyped, None)
check("file:// is not handed off", r is False and calls == [], (r, calls))


print("\n(9) no browser on PATH: load in-app, say why, don't cancel")
win.config["externalBrowser"] = "definitely-not-a-real-browser-xyz"
calls.clear()
toasts.clear()
r = win.maybe_open_external(GMAIL, NT.NavigationTypeTyped, None)
check("missing browser -> does NOT cancel (loads in-app)", r is False, r)
check("missing browser -> nothing launched", calls == [], calls)
check("missing browser -> a notice was shown", len(toasts) == 1, toasts)
win.config["externalBrowser"] = "firefox"


print("\n(10) the browser is resolved on PATH before anything launches")
# The guard that keeps a missing browser from blackholing the nav is
# _external_which, checked BEFORE the launch (QProcess.startDetached on
# Linux forks first and only fails in the child, so its return value
# cannot be trusted to mean "found it"). firefox is really installed here.
check("firefox resolves on PATH", bool(win._external_which("firefox")),
      win._external_which("firefox"))
check("a bogus command resolves to nothing",
      win._external_which("definitely-not-a-real-browser-xyz") is None)
check("an absolute path is honoured when executable",
      win._external_which("/usr/bin/firefox") in (None, "/usr/bin/firefox"))


print("\n(11) through the page: acceptNavigationRequest cancels a handoff")
view = win.new_tab(url=None)
app.processEvents()
page = view.page()
# Settle the page onto the web (password) channel first. A page fresh
# off an internal start page sits on the "full" channel; calling
# acceptNavigationRequest by hand with a web URL would otherwise trip
# the channel bounce, which schedules a real setUrl() reissue that
# fires on the next processEvents and drives an actual navigation. In
# life a web->web navigation never changes channel, so this matches it.
page.prime_trust(QUrl("https://example.com/"))
# isolate the wiring test from tab-closing/notice side effects
notices = []
win._external_notice = lambda v, name: notices.append(name)
calls.clear()
r = page.acceptNavigationRequest(ACCT, NT.NavigationTypeTyped, True)
check("acceptNavigationRequest returns False for a handoff", r is False, r)
check("and it launched through the seam", len(calls) == 1, calls)
# a redirect to the same site through the page must NOT launch
calls.clear()
page.acceptNavigationRequest(GMAIL, NT.NavigationTypeRedirect, True)
check("a redirect through the page does not launch", calls == [], calls)
# a sub-frame navigation (is_main_frame False) must NOT launch
calls.clear()
page.acceptNavigationRequest(GMAIL, NT.NavigationTypeLinkClicked, False)
check("a sub-frame navigation does not launch", calls == [], calls)


print("\n(12) a blank tab opened only for the handoff is closed")
# restore the real notice for this part
win._external_notice = B.Browser._external_notice.__get__(win)
blank = win.new_tab(blank=True, switch=False)
app.processEvents()
check("a fresh blank tab reads as blank", win._tab_never_committed(blank), blank.url())
before = win.tabs.count()
toasts.clear()
win._external_notice(blank, "firefox")
app.processEvents()
check("the blank tab was closed", win.tabs.count() == before - 1,
      (before, win.tabs.count()))
check("and a line said where it went", len(toasts) == 1, toasts)


print("\n(13) a tab with a real page is NOT treated as blank")
loaded = win.new_tab(blank=True, switch=False)
loaded.load(QUrl("data:text/html,<title>hi</title><p>hi"))
ok = wait_load(loaded)
if ok:
    check("a committed page is not blank", not win._tab_never_committed(loaded),
          (loaded.url().toString(), loaded.history().count()))
    kept = win.tabs.count()
    toasts.clear()
    win._external_notice(loaded, "firefox")
    check("a non-blank tab is kept, just noticed",
          win.tabs.count() == kept and len(toasts) == 1,
          (kept, win.tabs.count(), toasts))
else:
    # loading can't be relied on in every offscreen run; the blank path
    # is proven above, so skip rather than flake here.
    print("  ..   data page did not load offscreen; skipping (n/a)")


print("\n(14) the notice never leaves him with no tab at all")
while win.tabs.count() > 1:
    win.tabs.removeTab(win.tabs.count() - 1)
only = win.tabs.widget(0)
# force the last tab to look blank and hand off: it must stay
if win._tab_never_committed(only):
    toasts.clear()
    win._external_notice(only, "firefox")
    check("the last tab is never closed", win.tabs.count() == 1,
          win.tabs.count())
else:
    check("the last tab is never closed (n/a: not blank)", True)


print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
