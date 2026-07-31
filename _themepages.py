#!/usr/bin/env python3
"""Every page the browser brings with it, in a theme — checked and
photographed. Offscreen, scratch data only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/themepages")
THEME = sys.argv[2] if len(sys.argv) > 2 else "steampunk"
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1300, 880)
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


win.vault.add_item({"type": "login", "host": "github.com", "username": "user",
                    "password": "Xk7#mQp2$vLz9Rt4", "title": "GitHub"})
win.vault._save()
win.history = [{"url": "https://example.com/a", "title": "Example",
                "time": 1785000000}]
win.bookmarks = [{"id": 1, "title": "Example", "url": "https://example.com",
                  "parent": 0}]

B._select_theme(THEME)
win.apply_theme(THEME)
pal = B.theme_palette(THEME)
want = "rgb(%d, %d, %d)" % B._hex_rgb(pal["bg"])
fails = 0

pages = [("start", B.START_PAGE), ("history", B.HISTORY_PAGE),
         ("downloads", B.DOWNLOADS_PAGE), ("bookmarks", B.BOOKMARKS_PAGE),
         ("passwords", B.PASSWORDS_PAGE)]
for name, url in pages:
    view = win.new_tab(url=QUrl(url).toString())
    spin(2600)
    got = js(view.page(), """JSON.stringify({
        bg: getComputedStyle(document.body).backgroundColor,
        theme: document.documentElement.getAttribute("data-theme")})""")
    st = json.loads(got) if got else {}
    ok = st.get("bg") == want and st.get("theme") == THEME
    print(("  ok   " if ok else "  FAIL ")
          + "%-10s %s (want %s) theme=%s"
          % (name, st.get("bg"), want, st.get("theme")))
    fails += 0 if ok else 1
    win.grab().save(str(OUT / ("%s-%s.png" % (name, THEME))))

win.open_settings()
spin(3000)
got = js(win._panes["settings"].view.page(),
         "getComputedStyle(document.body).backgroundColor")
ok = got == want
print(("  ok   " if ok else "  FAIL ") + "%-10s %s" % ("settings", got))
fails += 0 if ok else 1
win.grab().save(str(OUT / ("settings-%s.png" % THEME)))

print("\n%d checks failed" % fails)
print("shots in", OUT)
app.quit()
sys.exit(1 if fails else 0)
