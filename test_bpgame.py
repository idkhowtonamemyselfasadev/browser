#!/usr/bin/env python3
"""The hidden start-page extra: it stays dormant until the secret is
entered in the one theme it lives in, never steals focus, and shuts the
moment it is closed or the theme changes. Offscreen, scratch data only."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
SCRATCH = Path(tempfile.mkdtemp(prefix="bpgame-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402

B.CONFIG_FILE = SCRATCH / "config.json"
B.HISTORY_FILE = SCRATCH / "history.json"
B.DOWNLOADS_FILE = SCRATCH / "downloads.json"
B.HOSTS_FILE = SCRATCH / "hosts.json"
B.BOOKMARKS_FILE = SCRATCH / "bookmarks.json"
# skip the first-run wizard that would cover the start page
B.CONFIG_FILE.write_text(json.dumps({"startPage": {"setupDone": True}}))

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1100, 720)
win.show()

fails = 0


def check(name, cond, detail=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + name + (
        "" if cond else "  <%s>" % detail))
    if not cond:
        fails += 1


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(6000, loop.quit)
    loop.exec()
    return box.get("v")


KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown",
          "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"]
SEND = "".join(
    "window.dispatchEvent(new KeyboardEvent('keydown',{key:%s,bubbles:true}));"
    % json.dumps(k) for k in KONAMI)


def on(page):
    return js(page, "document.getElementById('bpgame')"
                    ".classList.contains('on')")


view = win.new_tab(url=QUrl(B.START_PAGE).toString())
spin(2600)
page = view.page()
js(page, "window.__bpErr='';window.addEventListener('error',"
         "function(e){window.__bpErr=String(e.message||e.error);});")

print("(1) it is invisible and dormant until summoned")
check("the overlay exists but is not shown",
      js(page, "!!document.getElementById('bpgame') && "
               "getComputedStyle(document.getElementById('bpgame'))"
               ".display") == "none")

print("\n(2) the secret does nothing in the wrong theme")
win.apply_theme("mocha")
spin(500)
js(page, "document.activeElement && document.activeElement.blur();")
js(page, SEND)
spin(200)
check("Konami in mocha leaves it closed", on(page) is False)

print("\n(3) the search box is never hijacked")
win.apply_theme("blueprint")
spin(700)
js(page, "document.querySelector('form.search input').focus();")
js(page, SEND)
spin(200)
check("Konami while typing in search is ignored", on(page) is False)
check("and the search box still holds focus",
      js(page, "document.activeElement === "
               "document.querySelector('form.search input')") is True)

print("\n(4) the secret opens it in the right theme")
js(page, "document.activeElement && document.activeElement.blur();")
js(page, SEND)
spin(300)
check("Konami in blueprint opens the game", on(page) is True)
check("and the canvas got a drawing surface",
      (js(page, "document.getElementById('bpcanvas').width") or 0) > 0)

print("\n(5) it plays without throwing and survives input")
js(page, "window.dispatchEvent(new KeyboardEvent('keydown',"
         "{key:' ',bubbles:true}));")          # jump
js(page, "window.dispatchEvent(new KeyboardEvent('keydown',"
         "{key:'ArrowRight',bubbles:true}));")  # move
spin(600)
check("still running after a jump and a move", on(page) is True)
check("no game error reached the page",
      js(page, "window.__bpErr || ''") in ("", None))

print("\n(6) Escape closes it and it stops")
js(page, "window.dispatchEvent(new KeyboardEvent('keydown',"
         "{key:'Escape',bubbles:true}));")
spin(200)
check("Escape closes the overlay", on(page) is False)

print("\n(7) leaving the theme closes it")
js(page, "document.activeElement && document.activeElement.blur();")
js(page, SEND)
spin(300)
check("re-opened in blueprint", on(page) is True)
win.apply_theme("nord")
spin(500)
check("switching theme shuts the game", on(page) is False)

print("\n%d checks failed" % fails)
app.quit()
sys.exit(1 if fails else 0)
