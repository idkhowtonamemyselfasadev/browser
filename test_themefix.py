#!/usr/bin/env python3
"""The two halves of a theme that were being decided somewhere else.

Auto-darkening is set in two places — on the cookie jar and on the
page — and the page wins. A light theme that only ever spoke to the
jar was a light theme with dark websites in it, on every tab, forever.

The ladder of quiet colours is the same shape of problem: a floor says
where a colour stops, so five rungs sharing a floor stop together, and
a menu entry that cannot be picked came out the same colour as one that
can. (The numbers for that live in test_contrast.py, which is where
colours are measured; what is here is the browser around it.)

Plus the three small ones: the theme picker writing past the snapshot
it redraws from, a theme name in the config that is not a name at all,
and Settings drawing nothing at all in silence."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCRATCH = Path(tempfile.mkdtemp(prefix="themefix-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402
from PyQt6.QtWebEngineCore import (QWebEngineSettings,  # noqa: E402
                                   QWebEngineScript)

B.CONFIG_FILE = SCRATCH / "config.json"
B.HISTORY_FILE = SCRATCH / "history.json"
B.DOWNLOADS_FILE = SCRATCH / "downloads.json"
B.HOSTS_FILE = SCRATCH / "hosts.json"
B.BOOKMARKS_FILE = SCRATCH / "bookmarks.json"
SCRATCH.mkdir(parents=True, exist_ok=True)

FD = QWebEngineSettings.WebAttribute.ForceDarkMode
SITE = "https://example.com/"
FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    print(("  ok   " if cond else "  FAIL ") + name
          + ("  <%s>" % detail if detail else ""))
    if not cond:
        FAILS += 1


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


def site_tab(win, html="<b>hi</b>"):
    """A tab sitting on a website, without a network. setHtml with a
    base URL commits that URL, which is what _url_changed answers to."""
    view = win.new_tab()
    spin(200)
    view.setHtml(html, QUrl(SITE))
    spin(400)
    return view


def page_fd(view):
    return view.page().settings().testAttribute(FD)


def profile_fd(win):
    return win.profile.settings().testAttribute(FD)


# ------------------------------------------------------------------
# The restart half of (1) is a second process, because that is what a
# restart is: the config on disk, read from nothing.
if "--restart-child" in sys.argv:
    B.CONFIG_FILE = Path(sys.argv[sys.argv.index("--restart-child") + 1])
    B.HISTORY_FILE = B.CONFIG_FILE.parent / "history.json"
    B.DOWNLOADS_FILE = B.CONFIG_FILE.parent / "downloads.json"
    B.HOSTS_FILE = B.CONFIG_FILE.parent / "hosts.json"
    B.BOOKMARKS_FILE = B.CONFIG_FILE.parent / "bookmarks.json"
    B._install_theme_flags()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.show()
    spin(600)
    view = site_tab(win)
    print("RESULT " + json.dumps({
        "theme": B.ACTIVE_THEME,
        "profile": bool(profile_fd(win)),
        "page": bool(page_fd(view)),
        "setting": bool(win.config.get("forceDark", True))}))
    app.quit()
    sys.exit(0)


B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en", "theme": "mocha",
                                     "forceDark": True}))
B._select_theme("mocha")
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()
spin(800)

print("\n(1) a light theme holds auto-darkening off, everywhere")
existing = site_tab(win)
check("a dark theme darkens websites, as it always did",
      profile_fd(win) is True and page_fd(existing) is True,
      "profile=%s page=%s" % (profile_fd(win), page_fd(existing)))

win.apply_theme("latte")
spin(300)
check("the light theme switches it off on the cookie jar",
      profile_fd(win) is False, str(profile_fd(win)))
fresh = site_tab(win)
check("a tab opened after the switch comes up undarkened",
      page_fd(fresh) is False, str(page_fd(fresh)))
existing.setHtml("<b>again</b>", QUrl("https://example.org/"))
spin(400)
check("and so does one that navigates again",
      page_fd(existing) is False, str(page_fd(existing)))
check("the setting itself is left where he put it",
      win.config.get("forceDark", True) is True)

print("\n(2) switching theme fixes the tabs that are already open")
win.apply_theme("mocha")
spin(300)
tab = site_tab(win)
check("a tab on a dark theme is darkened", page_fd(tab) is True)
win.apply_theme("latte")
spin(300)
check("switching to a light theme undarkens it where it stands, with "
      "no navigation", page_fd(tab) is False, str(page_fd(tab)))
check("and the other tabs on screen with it",
      not any(page_fd(w) for w in (existing, fresh, tab)))
win.apply_theme("solarized-dark")
spin(300)
check("the next dark theme brings it back", page_fd(tab) is True,
      str(page_fd(tab)))
own = win.tabs.widget(0)
check("our own pages are never darkened, whatever the theme is on",
      page_fd(own) is False, own.url().toString())

print("\n(3) and it survives a restart")
cfg = SCRATCH / "restart"
cfg.mkdir(exist_ok=True)
(cfg / "config.json").write_text(json.dumps({"theme": "latte",
                                             "forceDark": True}))
env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
           XDG_DATA_HOME=str(cfg / "share"),
           XDG_CONFIG_HOME=str(cfg / "config"),
           XDG_CACHE_HOME=str(cfg / "cache"))
run = subprocess.run([sys.executable, str(HERE / "test_themefix.py"),
                      "--restart-child", str(cfg / "config.json")],
                     capture_output=True, text=True, env=env, timeout=300)
line = [ln for ln in run.stdout.splitlines() if ln.startswith("RESULT ")]
got = json.loads(line[0][7:]) if line else {}
check("a browser started on a light theme starts undarkened",
      got.get("theme") == "latte" and got.get("profile") is False
      and got.get("page") is False,
      json.dumps(got) or (run.stderr or "")[-300:])
check("with the setting still switched on underneath",
      got.get("setting") is True, json.dumps(got))

print("\n(4) a theme name that is not a name")
for bad in ([], ["latte"], {"k": 1}, 42, None, "", "MOCHA", "no-such-theme"):
    B.CONFIG_FILE.write_text(json.dumps({"theme": bad}))
    try:
        name = B._install_theme_flags()
        ok = name == "mocha"
        why = name
    except Exception as e:
        ok, why = False, "%s: %s" % (type(e).__name__, e)
    check("%-16s falls back to the default" % json.dumps(bad), ok, str(why))
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en", "theme": "mocha",
                                     "forceDark": True}))
B._select_theme("mocha")
win.apply_theme("mocha")

print("\n(5) the picker writes through the same door as everything else")
win.open_settings()
spin(3500)
page = win._panes["settings"].view.page()
before = js(page, "String(window._theme)")
check("Settings comes up on the theme that is on", before == "mocha", before)
js(page, "pickTheme({key: 'latte'});")
spin(600)
check("picking one paints the browser", B.ACTIVE_THEME == "latte",
      B.ACTIVE_THEME)
got = json.loads(js(page, """JSON.stringify({
    snap: String(window._settings && window._settings.theme),
    theme: String(window._theme),
    sel: (document.querySelector('.tcard.sel') || {dataset:{}}).dataset.key
         || '',
    label: document.getElementById('themecurname').textContent})""") or "{}")
check("and the snapshot the page redraws from knows about it",
      got.get("snap") == "latte", got.get("snap"))
# the redraw that used to put Mocha back: uiStrings arriving late draws
# the page again out of window._settings
js(page, "load(window._settings); showTheme();")
spin(300)
after = json.loads(js(page, """JSON.stringify({
    theme: String(window._theme),
    sel: (document.querySelector('.tcard.sel') || {dataset:{}}).dataset.key
         || '',
    label: document.getElementById('themecurname').textContent})""") or "{}")
check("a redraw from the snapshot leaves the tick where it was",
      after.get("sel") == "latte" and after.get("theme") == "latte",
      json.dumps(after))
check("and the label with it", after.get("label") == "Catppuccin Latte",
      after.get("label"))
check("the browser and the page still agree", B.ACTIVE_THEME == "latte")
win.apply_theme("mocha")
spin(300)
win.close_pane()
spin(200)

print("\n(6) a bridge call that throws still leaves a drawn page")
# The stage that used to be outside every guard: the CALL, not the
# callback. A slot that cannot be reached throws in the channel
# callback, and everything after it never happened.
POISON = """
(function () {
  var real = null;
  Object.defineProperty(window, "QWebChannel", {
    configurable: true,
    set: function (v) { real = v; },
    get: function () {
      if (!real) return undefined;
      return function (transport, cb) {
        return new real(transport, function (ch) {
          var b = ch.objects.bridge;
          ch.objects.bridge = new Proxy(b, {
            get: function (o, k) {
              if (k === "getSettings")
                throw new Error("no such slot (test)");
              var v = o[k];
              return (typeof v === "function") ? v.bind(o) : v;
            }
          });
          cb(ch);
        });
      };
    }
  });
})();
"""
script = QWebEngineScript()
script.setName("poison-bridge")
script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
script.setRunsOnSubFrames(False)
script.setSourceCode(POISON)
win.profile.scripts().insert(script)
win._panes.pop("settings", None)
win._pane = None
win.open_settings()
spin(4500)
page = win._panes["settings"].view.page()
drawn = json.loads(js(page, """JSON.stringify({
    poisoned: (function () {
      try { bridge.getSettings; return false; } catch (e) { return true; } })(),
    fail: document.getElementById('drawfail').className,
    failtext: document.getElementById('drawfail').textContent.slice(0, 90),
    rail: document.querySelectorAll('#sidebar button').length,
    blank: document.getElementById('content').className,
    cards: document.querySelectorAll('.tcard').length,
    starters: document.querySelectorAll('#starters *').length,
    pw: document.getElementById('pwsummary').textContent.length})""") or "{}")
check("the slot really is unreachable in this run", drawn.get("poisoned"),
      json.dumps(drawn))
check("the page says out loud that a part of it did not draw",
      "on" in (drawn.get("fail") or ""), json.dumps(drawn))
check("and names the part", "settings" in (drawn.get("failtext") or ""),
      drawn.get("failtext"))
check("the rail is still built", (drawn.get("rail") or 0) > 4,
      str(drawn.get("rail")))
check("the content area is not left hidden",
      "blank" not in (drawn.get("blank") or ""), drawn.get("blank"))
check("the theme picker is still there", drawn.get("cards") == len(B.THEMES),
      str(drawn.get("cards")))
check("so is the password summary", (drawn.get("pw") or 0) > 0,
      str(drawn.get("pw")))

print("\n%d checks failed" % FAILS)
app.quit()
sys.exit(1 if FAILS else 0)
