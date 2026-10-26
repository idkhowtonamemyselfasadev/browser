#!/usr/bin/env python3
"""Photograph the browser for the README's galleries, offscreen, against
scratch data — never near your own profile (see _boot.py).

    python3 _gallery.py OUT_DIR looks  [look,look,...]   [theme]
    python3 _gallery.py OUT_DIR themes [theme,theme,...] [look]

One picture per process, on purpose. Liquid Glass blurs through an alpha
channel that belongs to the window and is fixed when the window is created,
so a look switched at runtime would be photographed without its blur; a
fresh process is also the only way to be sure nothing of the previous
shot is still on screen.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/gallery")
MODE = sys.argv[2] if len(sys.argv) > 2 else "looks"
LOOKS_DEFAULT = ["classic", "taskbar", "macos", "circle", "glass", "flat"]
THEMES_DEFAULT = ["mocha", "gruvbox", "nord", "dracula", "tokyonight",
                  "everforest-hard", "rose-pine", "latte", "solarized-light",
                  "terminal", "newspaper", "gameboy"]
ITEMS = (sys.argv[3].split(",") if len(sys.argv) > 3
         else (LOOKS_DEFAULT if MODE == "looks" else THEMES_DEFAULT))
OTHER = sys.argv[4] if len(sys.argv) > 4 else ("mocha" if MODE == "looks"
                                               else "classic")
OUT.mkdir(parents=True, exist_ok=True)

if len(ITEMS) > 1:
    bad = 0
    for key in ITEMS:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            str(OUT), MODE, key, OTHER])
        bad += 1 if r.returncode else 0
    print("\n%d of %d %s failed" % (bad, len(ITEMS), MODE))
    print("shots in", OUT)
    sys.exit(1 if bad else 0)

KEY = ITEMS[0]
LOOK, THEME = (KEY, OTHER) if MODE == "looks" else (OTHER, KEY)
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

# A scratch profile is a fresh install, so without this the browser opens its
# first-run wizard, in German (translateLang defaults to "de") - a picture of
# the setup rather than of the browser. Written before Browser() reads it.
#
# The startPage blob is the start page's own localStorage, so every value in it
# is a string (SHARED_KEYS in start.html). Six quick links rather than the two
# it ships with, because the Taskbar and Dock looks put the pins in the chrome
# and two of them photograph as an empty strip.
LINKS = [("GitHub", "https://github.com"),
         ("Wikipedia", "https://en.wikipedia.org/wiki/Main_Page"),
         ("Hacker News", "https://news.ycombinator.com"),
         ("YouTube", "https://www.youtube.com"),
         ("Mastodon", "https://joinmastodon.org"),
         ("Twitch", "https://twitch.tv")]
start = {"setupDone": "1",
         "quicklinks": json.dumps([{"name": n, "url": u} for n, u in LINKS])}
if MODE == "looks":
    # Liquid Glass is frosted chrome with the wallpaper showing through it, so
    # photographing it on a bare background shows a grey bar and nothing of the
    # feature. The themes are shot without one, where the palette is the point.
    start["bg"] = "backgrounds/nature-1018.jpg"
B.CONFIG_FILE.write_text(json.dumps({
    "vaultPassword": True,
    "look": LOOK,
    "theme": THEME,
    "translateLang": "en",
    "startPage": start,
}))

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1360, 900)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


spin(3000)

# The Taskbar and Dock looks draw the pinned sites by favicon alone, and a site
# that has never been opened has no favicon yet - six empty circles in the
# picture. So visit them once, let the icons arrive and be cached, then close
# them again. Needs the network; without it the pins simply stay blank.
if MODE == "looks":
    for _, url in LINKS:
        win.new_tab(url, switch=False)
    spin(30000)   # 15 s was not enough for the heavier sites' icons
    while win.tabs.count() > 1:
        win.close_tab(win.tabs.count() - 1, ask=False)
    spin(1500)

# a second tab, so the strip in the picture is not one lonely tab
win.new_tab()
spin(4000)   # long enough for the wallpaper to be decoded and drawn

path = OUT / ("%s-%s.png" % ("look" if MODE == "looks" else "theme", KEY))
ok = win.grab().save(str(path))
print("%-16s look=%-9s theme=%-16s saved=%s %s"
      % (KEY, B.active_look(), THEME, ok, path))

fails = 0
if MODE == "looks" and B.active_look() != LOOK:
    print("  FAIL the browser is not in that look")
    fails += 1
if not ok or not path.exists() or path.stat().st_size < 10000:
    print("  FAIL no picture came out")
    fails += 1
app.quit()
sys.exit(1 if fails else 0)
