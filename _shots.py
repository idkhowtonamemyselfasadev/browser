#!/usr/bin/env python3
"""Photograph the worst themes on Settings and on the start page.

Runs against whichever tree it is dropped into, so the same script
takes the before and the after. Settings is photographed with the
mouse actually resting on the Brave card, because the black box in
the screenshot that started this is the hover state of a card.
Offscreen, scratch only.

  python3 _shots.py <outdir>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl, QPoint  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

# the palettes that came out worst on the ramp, and the ones that
# painted a texture over the page
SETTINGS_THEMES = ["nord-light", "solarized-light", "tokyonight-day",
                   "everforest-light", "c64", "gameboy", "steam", "mocha"]
START_THEMES = ["terminal", "sepia", "steampunk", "blueprint", "synthwave",
                "gameboy", "amber", "nord-light", "mocha"]

cfg = json.loads(B.CONFIG_FILE.read_text()) if B.CONFIG_FILE.exists() else {}
cfg.setdefault("startPage", {})["setupDone"] = True
B.CONFIG_FILE.write_text(json.dumps(cfg))

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
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


# ------------------------------------------------------- the start page
view = win.new_tab(url=QUrl(B.START_PAGE).toString())
spin(3000)
page = view.page()
js(page, """localStorage.setItem("bg", "backgrounds/nature-1018.jpg");""")
view.reload()
spin(3000)

for key in START_THEMES:
    win.apply_theme(key)
    spin(900)
    win.grab().save(str(OUT / ("start-photo-%s.png" % key)))
    js(page, """document.body.classList.remove("hasbg");
                document.body.style.backgroundImage = "";""")
    spin(500)
    win.grab().save(str(OUT / ("start-plain-%s.png" % key)))
    js(page, """document.body.classList.add("hasbg");
                document.body.style.backgroundImage =
                  'url("backgrounds/nature-1018.jpg")';""")
    spin(300)
    print("  start   %s" % key, flush=True)

# ---------------------------------------------------------- Settings
win.open_settings()
spin(3500)
sview = win._panes["settings"].view
spage = sview.page()
# the Search section, where the six search-engine cards are
js(spage, """(function () {
  var b = [...document.querySelectorAll("#sidebar button")]
    .find(x => /search/i.test(x.textContent));
  if (b) b.click();
})()""")
spin(1200)

# where the Brave card is, in the view's own coordinates
rect = js(spage, """(function () {
  var c = [...document.querySelectorAll(".card")]
    .find(x => /brave/i.test(x.textContent));
  if (!c) return null;
  var r = c.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
                         text: c.textContent.trim().slice(0, 40)});
})()""")
print("  brave card:", rect, flush=True)
spot = json.loads(rect) if rect else None

target = sview.focusProxy() or sview
for key in SETTINGS_THEMES:
    win.apply_theme(key)
    spin(900)
    if spot:
        # a real mouse move, so :hover is the engine's and not a fake
        QTest.mouseMove(target, QPoint(int(spot["x"]), int(spot["y"])))
        spin(600)
    win.grab().save(str(OUT / ("settings-search-%s.png" % key)))
    print("  settings %s" % key, flush=True)

print("shots in", OUT)
app.quit()
