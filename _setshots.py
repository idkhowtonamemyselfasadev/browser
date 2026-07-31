#!/usr/bin/env python3
"""Photograph the Settings page, section by section, in a theme.

Offscreen, against scratch data only — _boot redirects the config, the
history, the downloads, the hosts, the bookmarks and XDG_DATA_HOME into
a temporary directory before the browser is ever built.

    python3 _setshots.py OUTDIR [theme [theme ...]]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/setshots")
THEMES = sys.argv[2:] or ["mocha"]
OUT.mkdir(parents=True, exist_ok=True)

# the sections asked for, by the data-desc that names each one
WANT = [("general", "descSearch"), ("appearance", "descAppearance"),
        ("toolbar", "descToolbar"), ("theme", "descTheme"),
        ("privacy", "descPrivacy"), ("plugins", "descPlugins")]

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1400, 940)
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


win.open_settings()
spin(3000)
# Settings is a pane, not a tab: its own view is the one to talk to
page = win._panes["settings"].view.page()

for theme in THEMES:
    B._select_theme(theme)
    win.apply_theme(theme)
    spin(1200)
    for name, desc in WANT:
        n = js(page, """(function(){
          var secs=[...document.querySelectorAll('.content section')]
                     .filter(s=>!s.hidden);
          var i=secs.findIndex(s=>s.dataset.desc==='%s');
          if(i<0) return 'missing';
          showCat(i);
          return secs[i].querySelector('h2').textContent;
        })()""" % desc)
        spin(700)
        f = OUT / ("%s-%s.png" % (theme, name))
        win.grab().save(str(f))
        print("%-12s %-10s %-22s %s" % (theme, name, n, f))

print("scratch was", SCRATCH)
app.quit()
