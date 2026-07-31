#!/usr/bin/env python3
"""The two page settings, and where a new tab lands.

"When the browser starts" and "What a new tab shows" are two separate
settings that look almost the same, so the checks that matter most here
are the ones proving they do not bleed into each other, and the ones
proving a tab nobody navigated is never written back into the session.
That last one is what made a custom page feel like it "infinitely
opens" itself: every empty tab became a real saved tab, and the strip
grew at every launch.

Scratch everything - config, history, downloads, hosts, bookmarks, the
vault and XDG_DATA_HOME all point into a throwaway directory, and the
application name is changed so the QtWebEngine profiles cannot collide
with the browser you have running. Nothing here ever reads your data."""
import http.server
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def scratch(name):
    d = Path(tempfile.mkdtemp(prefix="browser-shot-" + name + "-"))
    (d / "share").mkdir(parents=True, exist_ok=True)
    return d


def settings_view(win):
    """The view inside the Settings pane. Looked up in one place: the
    browser is growing panes for every one of its own pages, and the
    attribute holding this one is renamed when that lands."""
    pane = getattr(win, "_settings_pane", None)
    if pane is None:
        pane = (getattr(win, "_panes", None) or {}).get("settings")
    return None if pane is None else pane.view


def redirect(cfg):
    """Every data file into scratch, before Browser() reads any."""
    cfg.mkdir(parents=True, exist_ok=True)
    for name in ("CONFIG_FILE", "HISTORY_FILE", "DOWNLOADS_FILE",
                 "HOSTS_FILE", "BOOKMARKS_FILE"):
        setattr(B, name, cfg / (name.lower() + ".json"))


# ---- a server that can redirect, which the shared harness cannot -----
class Handler(http.server.SimpleHTTPRequestHandler):
    pages = {}

    def do_GET(self):
        path = self.path.split("?")[0]
        body = self.pages.get(path)
        if body is None:
            self.send_error(404)
            return
        if body.startswith("slow "):
            # long enough that anything typed into a brand-new tab
            # reaches the network first, and this one never commits
            time.sleep(3)
            body = body[5:]
        if body.startswith("301 "):
            self.send_response(301)
            self.send_header("Location", body[4:])
            self.end_headers()
            return
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class Server:
    def __init__(self, pages):
        Handler.pages = dict(pages)
        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)


# =====================================================================
# --launch: one Browser started from a given config, in its own process
# =====================================================================
if len(sys.argv) > 2 and sys.argv[1] == "--launch":
    conf = json.loads(sys.argv[2])
    d = scratch("launch")
    os.environ["XDG_DATA_HOME"] = str(d / "share")
    import browser as B
    from PyQt6.QtWidgets import QApplication
    import harness as H
    redirect(d / "cfg")
    B.CONFIG_FILE.write_text(json.dumps(conf))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.show()                 # or every widget reports invisible
    H.spin(1500)
    opened = [(w.url().toString() or getattr(w, "_requested", "")
               or getattr(w, "_pending", ""))
              for w in (win.tabs.widget(i) for i in range(win.tabs.count()))
              if not win._is_header(w)]
    # what a new tab shows in the same run, with the same config
    fresh = win.new_tab()
    H.spin(800)
    win._save_groups()
    print("LAUNCH " + json.dumps({
        "opened": opened,
        "fresh": fresh.url().toString() or getattr(fresh, "_requested", ""),
        "saved": win.config.get("sessionTabs") or {},
        "start": B.START_PAGE.toString()}))
    sys.stdout.flush()
    os._exit(0)                # Qt teardown offscreen is not worth waiting on


# =====================================================================
# --settings: the settings page itself, driven from inside the document
# =====================================================================
if len(sys.argv) > 1 and sys.argv[1] == "--settings":
    d = scratch("settings")
    os.environ["XDG_DATA_HOME"] = str(d / "share")
    import browser as B
    from PyQt6.QtWidgets import QApplication
    import harness as H
    redirect(d / "cfg")
    B.CONFIG_FILE.write_text(json.dumps(
        {"newTabUrl": "youtube.com", "newTabPos": "end",
         "translateLang": "en"}))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.show()
    win.open_settings()
    H.spin(3000)
    view = settings_view(win)
    out = {}
    # sections that are not the open one are display:none, and nothing
    # inside one of those can take the focus - so open Browsing first
    H.js(view, """(function () {
      var secs = visibleSections();
      var want = document.querySelector('section[data-desc="descBrowsing"]');
      showCat(secs.indexOf(want));
      return 1;
    })()""", B.MAIN_WORLD_ID)
    H.spin(300)
    out["reachable"] = H.js(view, """(function () {
      var e = document.getElementById('newtaburl');
      e.focus();
      return document.activeElement === e;
    })()""", B.MAIN_WORLD_ID)

    # (a) clear the box and leave it - no Save click anywhere
    H.js(view, """(function () {
      var e = document.getElementById('newtaburl');
      e.focus(); e.value = ''; e.blur();
      return 1;
    })()""", B.MAIN_WORLD_ID)
    H.spin(800)
    out["cleared"] = win.config.get("newTabUrl", "MISSING")
    out["card"] = H.js(view, """(function () {
      var sel = document.querySelector('#newtabpage .card.sel');
      return sel ? sel.dataset.value : '?';
    })()""", B.MAIN_WORLD_ID)

    # (b) pick a card, then let the page redraw itself from its own
    #     snapshot the way the uiStrings callback does
    H.js(view, """(function () {
      var cards = document.querySelectorAll('#newtabpos .card');
      for (var c of cards) if (c.dataset.value === 'after') c.click();
      return 1;
    })()""", B.MAIN_WORLD_ID)
    H.spin(500)
    out["posSaved"] = win.config.get("newTabPos", "MISSING")
    out["posAfterRedraw"] = H.js(view, """(function () {
      load(window._settings);
      var sel = document.querySelector('#newtabpos .card.sel');
      return sel ? sel.dataset.value : '?';
    })()""", B.MAIN_WORLD_ID)

    # (c) the two page settings are separate fields. The box only
    #     exists once the card beside it is picked, same as the other
    H.js(view, """(function () {
      for (var c of document.querySelectorAll('#startpage .card'))
        if (c.dataset.value === 'custom') c.click();
      return 1;
    })()""", B.MAIN_WORLD_ID)
    H.spin(300)
    H.js(view, """(function () {
      var e = document.getElementById('starturl');
      e.focus(); e.value = 'example.com'; e.blur();
      return 1;
    })()""", B.MAIN_WORLD_ID)
    H.spin(900)
    out["startSaved"] = win.config.get("startUrl", "MISSING")
    out["newTabUntouched"] = win.config.get("newTabUrl", "MISSING")
    print("SETTINGS " + json.dumps(out))
    sys.stdout.flush()
    os._exit(0)


# =====================================================================
# --allsettings: the start page's own button, and a Settings pane that
# is never allowed to come up empty
# =====================================================================
if len(sys.argv) > 1 and sys.argv[1] == "--allsettings":
    d = scratch("allset")
    os.environ["XDG_DATA_HOME"] = str(d / "share")
    import browser as B
    from PyQt6.QtWidgets import QApplication
    import harness as H
    redirect(d / "cfg")
    B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.show()
    win.activateWindow()
    H.spin(1500)
    start = win.current()
    # the page has to be up and holding its bridge, or the button it
    # carries is not there to be pressed yet
    H.wait_for(lambda: H.js(start, "typeof bridge !== 'undefined' && !!bridge",
                            B.MAIN_WORLD_ID) is True, 25000)
    out = {"startPage": start.url().toString() == B.START_PAGE.toString()}
    # the real button in the start page's own panel, not open_settings()
    H.js(start, "document.getElementById('allsettings').click()",
         B.MAIN_WORLD_ID)
    H.wait_for(lambda: settings_view(win) is not None, 20000)
    H.spin(3500)
    view = settings_view(win)
    if view is None:
        print("ALLSET " + json.dumps(dict(out, paneUp=False)))
        sys.stdout.flush()
        os._exit(0)
    pane = view.parentWidget()
    while pane is not None and not hasattr(pane, "dismiss"):
        pane = pane.parentWidget()
    out["paneUp"] = bool(pane is not None and pane.isVisible())
    out["paneUrl"] = view.url().toString()

    STATE = """(function () {
      var secs = [...document.querySelectorAll('.content section')];
      var c = document.getElementById('content');
      var f = document.getElementById('drawfail');
      return JSON.stringify({
        rail: document.querySelectorAll('#sidebar button').length,
        active: secs.filter((s) => s.classList.contains('active')).length,
        display: getComputedStyle(c).display,
        said: f ? f.textContent : null});
    })()"""

    def state():
        return json.loads(H.js(view, STATE, B.MAIN_WORLD_ID) or "null")

    out["opened"] = state()
    # a rail index that no longer points at a section - what is left
    # after a section is hidden underneath the rail that listed it
    H.js(view, "showCat(999)", B.MAIN_WORLD_ID)
    H.spin(200)
    out["stale"] = state()
    # and the pair that is what a blank pane actually looked like:
    # nothing showing, with an empty search box
    H.js(view, """(function () {
      document.getElementById('content').classList.add('blank');
      for (var s of document.querySelectorAll('.content section'))
        s.classList.remove('active');
      settle();
    })()""", B.MAIN_WORLD_ID)
    H.spin(200)
    out["settled"] = state()
    # something that did not draw has to say so
    H.js(view, "drawFailed('themes', 'boom')", B.MAIN_WORLD_ID)
    H.spin(200)
    out["said"] = state().get("said") or ""
    # the rail's own "All settings" button, which is the other control
    # with that name: it clears a filter that matched nothing. From a
    # known-good page, so this measures the filter and nothing else.
    H.js(view, "showCat(0)", B.MAIN_WORLD_ID)
    H.spin(200)
    H.js(view, """(function () {
      var box = document.getElementById('navfilter');
      box.value = 'zzzznothingmatchesthis';
      filterNav(box.value);
    })()""", B.MAIN_WORLD_ID)
    H.spin(300)
    out["filtered"] = state()
    H.js(view, "document.getElementById('showall').click()", B.MAIN_WORLD_ID)
    H.spin(400)
    out["unfiltered"] = state()
    print("ALLSET " + json.dumps(out))
    sys.stdout.flush()
    os._exit(0)


# =====================================================================
# the suite itself
# =====================================================================
d = scratch("main")
os.environ["XDG_DATA_HOME"] = str(d / "share")
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
import harness as H  # noqa: E402

cfg = d / "cfg"
redirect(cfg)
B.CONFIG_FILE.write_text(json.dumps({"restoreTabs": False,
                                     "translateLang": "en"}))
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()                     # or every widget reports invisible


def section(title, fn):
    print("\n" + title)
    try:
        fn()
    except Exception as exc:                          # noqa: BLE001
        check(title + ": ran at all", False, repr(exc)[:140])


# ---------------------------------------------------------------- (1)
def where_a_new_tab_opens():
    win.config["newTabPos"] = "after"
    first = win.current()
    a = win.new_tab(blank=True)
    b = win.new_tab(blank=True)
    win.tabs.setCurrentIndex(win.tabs.indexOf(a))
    cur = win.tabs.currentIndex()
    made = win.new_tab(blank=True)
    check("\"after\" puts it right after the tab it came from",
          win.tabs.indexOf(made) == cur + 1,
          "%d, wanted %d" % (win.tabs.indexOf(made), cur + 1))
    check("and does not send it to the end",
          win.tabs.indexOf(made) != win.tabs.count() - 1,
          win.tabs.indexOf(made))

    win.config["newTabPos"] = "end"
    win.tabs.setCurrentIndex(win.tabs.indexOf(a))
    last = win.new_tab(blank=True)
    check("\"end\" puts it at the end of the strip",
          win.tabs.indexOf(last) == win.tabs.count() - 1,
          "%d of %d" % (win.tabs.indexOf(last), win.tabs.count()))
    for v in (a, b, made, last):
        i = win.tabs.indexOf(v)
        if i >= 0:
            win.close_tab(i)
    win.tabs.setCurrentIndex(win.tabs.indexOf(first))


section("(1) where a new tab opens", where_a_new_tab_opens)


# ---------------------------------------------------------------- (2)
def other_virtual_browser():
    win.config["newTabPos"] = "after"
    win.sessions.append({"name": "Browser 2", "sid": "b"})
    mine = win.new_tab(blank=True, group=None, session="main")
    # one more behind it, or "right after this tab" and "at the end"
    # are the same index and the check would prove nothing
    win.new_tab(blank=True, group=None, session="main")
    win.tabs.setCurrentIndex(win.tabs.indexOf(mine))
    cur = win.tabs.currentIndex()
    other = win.new_tab(blank=True, group=None, session="b")
    check("a tab for another virtual browser is not slid into this one's",
          win.tabs.indexOf(other) != cur + 1,
          "landed at %d, this browser's tab is at %d"
          % (win.tabs.indexOf(other), cur))
    check("every tab before it still belongs to this browser",
          all(getattr(win.tabs.widget(i), "session", "main") == "main"
              for i in range(win.tabs.indexOf(other))
              if not win._is_header(win.tabs.widget(i))))
    win.config["newTabPos"] = "end"


section("(2) a new tab in another virtual browser", other_virtual_browser)


# ---------------------------------------------------------------- (3)
def what_the_settings_resolve_to():
    win.config["newTabUrl"] = ""
    check("no address means the start page",
          win.new_tab_target() == B.START_PAGE, win.new_tab_target().toString())
    win.config["newTabUrl"] = "about:blank"
    check("an address the browser will not open means the start page too",
          win.new_tab_target() == B.START_PAGE, win.new_tab_target().toString())
    win.config["newTabUrl"] = "example.com"
    check("an address it will open is what a new tab gets",
          win.new_tab_target().host() == "example.com",
          win.new_tab_target().toString())
    check("and it gets https, not a nonsense scheme",
          win.new_tab_target().scheme() == "https")
    win.config["startUrl"] = "example.org"
    check("the launch page is read from its own setting",
          win.start_target().host() == "example.org",
          win.start_target().toString())
    check("and setting one leaves the other exactly where it was",
          win.new_tab_target().host() == "example.com")
    win.config["startUrl"] = ""
    win.config["newTabUrl"] = ""


section("(3) what the two settings resolve to", what_the_settings_resolve_to)


# ---------------------------------------------------------------- (4)
srv = Server({"/home": "<!doctype html><title>home</title>home",
              "/other": "<!doctype html><title>other</title>other",
              "/redir": "301 /home",
              # a page that routes in the browser instead of over the
              # network - a webmail, a dashboard, anything with a hash
              # router. Nothing is ever loaded when it moves.
              "/spa": "<!doctype html><title>spa</title>spa",
              # a new-tab page that takes its time arriving, so that
              # what he does next gets there before it does
              "/slow": "slow <!doctype html><title>slow</title>slow",
              # /twice -> /redir -> /home, two hops on the way in
              "/twice": "301 /redir"})
# an absolute redirect off this host: same server, other name for it
Handler.pages["/xhost"] = "301 http://localhost:%d/home" % srv.port


def a_tab_he_never_navigated():
    win.config["newTabUrl"] = srv.url("/home")
    blank = win.new_tab()
    H.wait_for(lambda: blank.url().path() == "/home", 15000)
    H.spin(800)   # let that load finish before starting one on top of it
    win._save_groups()
    saved = json.dumps(win.config.get("sessionTabs") or {})
    check("the page really came up", blank.url().path() == "/home",
          blank.url().toString())
    check("an empty tab on a page of his own is not saved as a tab",
          "/home" not in saved, saved[:160])

    H.load(blank, srv.url("/other"))
    H.wait_for(lambda: blank.url().path() == "/other", 15000)
    check("the navigation really landed", blank.url().path() == "/other",
          blank.url().toString())
    win._save_groups()
    saved = json.dumps(win.config.get("sessionTabs") or {})
    check("but the moment he goes somewhere, the tab is remembered",
          "/other" in saved, saved[:160])

    # a bare host redirects (youtube.com -> www.youtube.com), and the
    # tab must stay anonymous through it
    win.config["newTabUrl"] = srv.url("/redir")
    bounced = win.new_tab()
    H.wait_for(lambda: bounced.url().path() == "/home", 15000)
    H.spin(800)
    win._save_groups()
    saved = json.dumps(win.config.get("sessionTabs") or {})
    check("a redirect on the way in does not make it a tab of his own",
          "/home" not in saved, saved[:200])
    for v in (blank, bounced):
        i = win.tabs.indexOf(v)
        if i >= 0:
            win.close_tab(i)
    win.config["newTabUrl"] = ""


section("(4) a tab he opened and never navigated", a_tab_he_never_navigated)


# ---------------------------------------------------------------- (4b)
def client_side_navigation():
    """He is somewhere he chose even when no document was ever loaded
    to get there. Counting loads misses this; the address does not."""
    for name, code, want in (
            ("a hash router", "location.hash = 'inbox/42'", "#inbox/42"),
            ("history.pushState", "history.pushState({}, '', '/spa/mail/42')",
             "/spa/mail/42")):
        win.config["newTabUrl"] = srv.url("/spa")
        tab = win.new_tab()
        H.wait_for(lambda t=tab: t.url().path() == "/spa", 15000)
        H.spin(800)
        check("the %s page came up blank first" % name,
              win._is_blank_tab(tab), tab.url().toString())
        H.js(tab, code)
        H.spin(700)
        win._save_groups()
        saved = json.dumps(win.config.get("sessionTabs") or {})
        check("%s moves the tab, so it is remembered" % name,
              want in saved, saved[:200])
        i = win.tabs.indexOf(tab)
        if i >= 0:
            win.close_tab(i)
    win.config["newTabUrl"] = ""


section("(4b) a page that routes in the browser", client_side_navigation)


# ---------------------------------------------------------------- (4c)
def straight_to_an_address_of_his_own():
    """Ctrl+T and an address, before the new-tab page has so much as
    arrived. The browser used to read "where an empty tab rests" off
    the first page that committed in it - which, when he types fast, is
    the page he asked for. The tab then counted as empty for the rest
    of its life and was dropped from the session without a word, and
    only when he opened it, went to one page and left it there."""
    def opened_then(label, newtab, go, want):
        win.config["newTabUrl"] = newtab
        tab = win.new_tab()
        go(tab)          # no waiting: the new-tab page has not committed
        H.wait_for(lambda: want in tab.url().toString(), 25000)
        H.spin(700)
        win._save_groups()
        saved = json.dumps(win.config.get("sessionTabs") or {})
        check(label, want in saved, saved[:220])
        i = win.tabs.indexOf(tab)
        if i >= 0:
            win.close_tab(i)

    def typed(target):
        def go(_tab):
            win.urlbar.setText(target)
            win._navigate()
        return go

    def loaded(target):
        from PyQt6.QtCore import QUrl
        return lambda tab: tab.load(QUrl(target))

    opened_then("an address typed into a tab that has not settled is kept",
                srv.url("/slow"), typed(srv.url("/other")), "/other")
    opened_then("and kept when the new-tab page is the ordinary start page",
                "", typed(srv.url("/other")), "/other")
    opened_then("a load issued the moment the tab exists is kept too",
                srv.url("/slow"), loaded(srv.url("/other")), "/other")
    opened_then("a redirect on the way to where he typed is kept",
                srv.url("/slow"), typed(srv.url("/redir")), "/home")
    opened_then("two redirects on the way there, likewise",
                srv.url("/slow"), typed(srv.url("/twice")), "/home")
    opened_then("a redirect onto another host, likewise",
                srv.url("/slow"), typed(srv.url("/xhost")), "localhost")
    opened_then("and an address that turns out to be a 404 is still his",
                srv.url("/slow"), typed(srv.url("/gone")), "/gone")
    win.config["newTabUrl"] = ""


section("(4c) a tab he typed into before it settled",
        straight_to_an_address_of_his_own)


# ---------------------------------------------------------------- (4d)
def a_new_tab_page_that_moves_by_itself():
    """The other side of the same coin: a page of his own that arrives
    by way of a second load must not turn an untouched tab into a saved
    one. That is the "it keeps opening itself" complaint, and only the
    plainest of these was recognised before."""
    for label, page in (
            ("a redirect", "301 /home"),
            ("a meta refresh",
             "<!doctype html><meta http-equiv=\"refresh\" "
             "content=\"0;url=/home\">wait"),
            ("a script that sends it on",
             "<!doctype html><script>location.replace('/home')</script>w")):
        Handler.pages["/mover"] = page
        win.config["newTabUrl"] = srv.url("/mover")
        tab = win.new_tab()
        H.wait_for(lambda t=tab: t.url().path() == "/home", 20000)
        H.spin(900)
        win._save_groups()
        saved = json.dumps(win.config.get("sessionTabs") or {})
        check("a new-tab page that arrives by %s is still an empty tab"
              % label, "/home" not in saved, saved[:220])
        i = win.tabs.indexOf(tab)
        if i >= 0:
            win.close_tab(i)
    # and the plain untouched tab, on the start page, stays empty too
    win.config["newTabUrl"] = ""
    tab = win.new_tab()
    H.spin(1500)
    win._save_groups()
    saved = json.dumps(win.config.get("sessionTabs") or {})
    check("a new tab nobody touched is not written into the session",
          "start.html" not in saved and win._is_blank_tab(tab), saved[:220])
    check("and the marker is still on it, not torn off by the channel hop",
          win._is_blank_tab(tab), getattr(tab, "_blank_home", "?"))
    # then he goes somewhere in it, the ordinary way, and it is his
    H.load(tab, srv.url("/other"))
    H.wait_for(lambda: tab.url().path() == "/other", 15000)
    win._save_groups()
    saved = json.dumps(win.config.get("sessionTabs") or {})
    check("and the moment he goes somewhere in it, it is remembered",
          "/other" in saved, saved[:220])
    i = win.tabs.indexOf(tab)
    if i >= 0:
        win.close_tab(i)


section("(4d) a new-tab page that moves by itself",
        a_new_tab_page_that_moves_by_itself)


# ---------------------------------------------------------------- (5)
def a_way_back_to_the_start_page():
    win.config["newTabUrl"] = srv.url("/home")
    tab = win.new_tab()
    H.wait_for(lambda: tab.url().path() == "/home", 15000)
    win.go_home()
    H.wait_for(lambda: win.current().url() == B.START_PAGE, 15000)
    check("Alt+Home reaches the start page with a page of his own set",
          win.current().url() == B.START_PAGE, win.current().url().toString())
    keys = [s.key().toString() for s in win.findChildren(
        __import__("PyQt6.QtGui", fromlist=["QShortcut"]).QShortcut)]
    check("and the shortcut is really bound", "Alt+Home" in keys,
          [k for k in keys if "Home" in k])
    btn = getattr(win, "_home_btn", None)
    check("there is a button for it too, for anyone who does not know it",
          btn is not None and btn.isVisible(),
          None if btn is None else btn.toolTip())
    i = win.tabs.indexOf(tab)
    if i >= 0:
        win.close_tab(i)
    win.config["newTabUrl"] = ""


section("(5) the way back to the start page", a_way_back_to_the_start_page)


# ---------------------------------------------------------------- (6)
def the_page_at_launch():
    runs = {}
    for name, conf in (
            ("custom", {"startUrl": "example.com", "restoreTabs": True}),
            ("both", {"startUrl": "example.com", "newTabUrl": "example.net",
                      "restoreTabs": True}),
            ("restored", {"startUrl": "example.com", "restoreTabs": True,
                          "sessionTabs": {"main": [{"u": "https://example.net/",
                                                    "t": "kept"}]}})):
        r = subprocess.run([sys.executable, str(HERE / "test_newtab.py"),
                            "--launch", json.dumps(conf)],
                           capture_output=True, text=True, timeout=300)
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("LAUNCH ")]
        runs[name] = json.loads(line[0][7:]) if line else {}
        if not line:
            print("      (no answer from --launch %s) %s"
                  % (name, r.stderr.strip().splitlines()[-1:]))

    one = runs.get("custom", {})
    check("the browser opens on the page he set",
          any("example.com" in u for u in one.get("opened", [])),
          one.get("opened"))
    check("and a new tab in the same run still shows the start page",
          one.get("fresh", "") == one.get("start", "?"), one.get("fresh"))
    check("the tab it opened is not written back into the session",
          "example.com" not in json.dumps(one.get("saved", {})),
          one.get("saved"))

    two = runs.get("both", {})
    check("with both set, launch takes the launch page",
          any("example.com" in u for u in two.get("opened", [])),
          two.get("opened"))
    check("and a new tab takes the new-tab page",
          "example.net" in two.get("fresh", ""), two.get("fresh"))

    back = runs.get("restored", {})
    check("tabs from last time come back",
          any("example.net" in u for u in back.get("opened", [])),
          back.get("opened"))
    check("and they win: no launch page is forced on top of them",
          not any("example.com" in u for u in back.get("opened", [])),
          back.get("opened"))


section("(6) the page the browser starts on", the_page_at_launch)


# ---------------------------------------------------------------- (7)
def the_settings_page_itself():
    r = subprocess.run([sys.executable, str(HERE / "test_newtab.py"),
                        "--settings"], capture_output=True, text=True,
                       timeout=300)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("SETTINGS ")]
    if not line:
        print("      (no answer) %s" % r.stderr.strip().splitlines()[-3:])
    out = json.loads(line[0][9:]) if line else {}
    check("the address box is on screen and can be typed in",
          out.get("reachable") is True, out.get("reachable"))
    check("clearing the box and leaving it saves, with no Save click",
          out.get("cleared") == "", out.get("cleared"))
    check("and the cards say the start page is what opens now",
          out.get("card") == "start", out.get("card"))
    check("picking where a new tab opens is written down",
          out.get("posSaved") == "after", out.get("posSaved"))
    check("and a redraw from the page's own snapshot keeps it",
          out.get("posAfterRedraw") == "after", out.get("posAfterRedraw"))
    check("the launch address saves itself on leaving the box",
          out.get("startSaved") == "example.com", out.get("startSaved"))
    check("and writing it does not touch what a new tab shows",
          out.get("newTabUntouched") == "", out.get("newTabUntouched"))


section("(7) the settings page itself", the_settings_page_itself)


# ---------------------------------------------------------------- (8)
def settings_is_never_blank():
    r = subprocess.run([sys.executable, str(HERE / "test_newtab.py"),
                        "--allsettings"], capture_output=True, text=True,
                       timeout=300)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("ALLSET ")]
    if not line:
        print("      (no answer) %s" % r.stderr.strip().splitlines()[-3:])
    o = json.loads(line[0][7:]) if line else {}
    op = o.get("opened") or {}
    check("the tab really was on the start page", o.get("startPage") is True)
    check("its \"All settings\" button brings the pane up",
          o.get("paneUp") is True and "settings.html" in o.get("paneUrl", ""),
          o.get("paneUrl"))
    check("with a rail, one section showing and content on screen",
          op.get("rail", 0) > 0 and op.get("active") == 1
          and op.get("display") != "none", op)
    st = o.get("stale") or {}
    check("a rail index pointing at nothing still leaves a section up",
          st.get("active") == 1 and st.get("display") != "none", st)
    se = o.get("settled") or {}
    check("nothing showing with an empty search box puts itself right",
          se.get("active") == 1 and se.get("display") != "none", se)
    check("and a part that did not draw says so out loud",
          "themes" in (o.get("said") or ""), o.get("said"))
    fi = o.get("filtered") or {}
    check("a search nothing matches does hide the content",
          fi.get("display") == "none", fi)
    un = o.get("unfiltered") or {}
    check("and the rail's own \"All settings\" brings it back",
          un.get("display") != "none" and un.get("active") == 1, un)


section("(8) Settings never comes up blank", settings_is_never_blank)


print("\n%d failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
