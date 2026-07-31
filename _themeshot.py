#!/usr/bin/env python3
"""Photograph the browser in a row of themes, offscreen, against
scratch data — and prove a theme lands on a page that is already open
without reloading it."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/theme")
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = sys.argv[2].split(",") if len(sys.argv) > 2 else [
    "mocha", "steampunk", "steam", "gruvbox-light", "terminal",
    "nord", "dracula", "solarized-light", "blueprint", "synthwave",
    "newspaper", "tokyonight"]

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1360, 900)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()

    def done(r):
        box["v"] = r
        loop.quit()
    page.runJavaScript(code, B.MAIN_WORLD_ID, done)
    QTimer.singleShot(6000, loop.quit)
    loop.exec()
    return box.get("v")


win.open_settings()
spin(3500)
page = win._panes["settings"].view.page()

# a mark that only survives if the page is never reloaded
js(page, "window.__mark = 'alive-' + Date.now();")
mark = js(page, "window.__mark")
print("mark set:", mark)

# open the picker itself, so the shots show what he actually clicks
js(page, """(function () {
  var b = [...document.querySelectorAll('#sidebar button')]
            .find(function (x) { return x._sec
              && x._sec.dataset.desc === 'descTheme'; });
  if (b) b.click();
})()""")
spin(600)

report = []
for key in SHOTS:
    win.apply_theme(key)
    spin(900)
    win.grab().save(str(OUT / ("settings-%s.png" % key)))
    state = js(page, """JSON.stringify({
        mark: window.__mark || "",
        attr: document.documentElement.getAttribute("data-theme"),
        body: getComputedStyle(document.body).backgroundColor,
        h2: getComputedStyle(document.querySelector("h2")).color,
        font: getComputedStyle(document.querySelector("h2")).fontFamily,
        extra: !!document.getElementById("themeextra"),
        cards: document.querySelectorAll(".tcard").length,
        sel: (document.querySelector(".tcard.sel") || {}).dataset
             && document.querySelector(".tcard.sel").dataset.key
      })""")
    st = json.loads(state) if state else {}
    pal = B.theme_palette(key)
    report.append((key, st, pal))
    print("%-18s attr=%-18s body=%-22s sel=%-16s extra=%s mark=%s"
          % (key, st.get("attr"), st.get("body"), st.get("sel"),
             st.get("extra"), st.get("mark") == mark))

# and the chrome: settings closed, tabs and address bar in view
win.close_settings()
win.new_tab()
win.new_tab()
spin(2500)
for key in SHOTS:
    win.apply_theme(key)
    spin(700)
    win.grab().save(str(OUT / ("chrome-%s.png" % key)))

print("\n--- checks")
fails = 0
for key, st, pal in report:
    def want(cond, msg):
        global fails
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails += 1
    rgb = tuple(B._hex_rgb(pal["bg"]))
    want(st.get("attr") == key, "%s: the page says which theme it is" % key)
    want(st.get("body") == "rgb%s" % (rgb,) or st.get("body", "").replace(
        " ", "") == "rgb%s" % (rgb,),
        "%s: the page background is the palette's (%s vs %s)"
        % (key, st.get("body"), pal["bg"]))
    want(st.get("mark") == mark, "%s: the page was never reloaded" % key)
    want(st.get("cards") == len(B.THEMES),
         "%s: every theme is in the picker (%s)" % (key, st.get("cards")))
    want(st.get("sel") == key, "%s: the picker shows which one is on" % key)
seen = {key: st for key, st, _ in report}
for key in ("steampunk", "terminal", "blueprint", "synthwave", "newspaper"):
    st = seen.get(key)
    if st:
        print(("  ok   " if st.get("extra") else "  FAIL ")
              + "%s: brings CSS of its own" % key)
        fails += 0 if st.get("extra") else 1
st = seen.get("mocha", {})
print(("  ok   " if not st.get("extra") else "  FAIL ")
      + "mocha: brings none, it is the sheet as written")
fails += 1 if st.get("extra") else 0

print("\n%d checks failed" % fails)
print("shots in", OUT)
app.quit()
sys.exit(1 if fails else 0)
