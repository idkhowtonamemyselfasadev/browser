#!/usr/bin/env python3
"""The colours that used to be written into JavaScript now name a
custom property. Do those properties actually exist on the root, and
does a light theme really move them off Mocha? Asked of the running
page, not of the source."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1200, 820)
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


TOKENS = ("red", "yellow", "green", "peach", "subtext")
fails = 0
win.open_settings()
spin(3500)
page = win._panes["settings"].view.page()

for key in ("mocha", "nord-light", "gruvbox-light", "c64"):
    win.apply_theme(key)
    spin(900)
    got = js(page, """(function () {
      var cs = getComputedStyle(document.documentElement), o = {};
      %s
      var p = document.createElement("div");
      p.style.color = "var(--yellow, #f9e2af)";
      document.body.appendChild(p);
      o.resolved = getComputedStyle(p).color;
      p.remove();
      return JSON.stringify(o);
    })()""" % "".join('o[%r] = cs.getPropertyValue("--%s").trim();' % (t, t)
                      for t in TOKENS))
    st = json.loads(got) if got else {}
    pal = B.theme_palette(key)
    want = "rgb(%d, %d, %d)" % B._hex_rgb(pal["yellow"])
    defined = all(st.get(t) for t in TOKENS)
    matches = all((st.get(t) or "").lower() == pal[t].lower() for t in TOKENS)
    resolved = st.get("resolved") == want
    ok = defined and matches and resolved
    print(("  ok   " if ok else "  FAIL ")
          + "%-16s --yellow=%-9s palette=%-9s var() -> %-18s want %s"
          % (key, st.get("yellow"), pal["yellow"], st.get("resolved"), want))
    fails += 0 if ok else 1

print("\n%d checks failed" % fails)
app.quit()
sys.exit(1 if fails else 0)
