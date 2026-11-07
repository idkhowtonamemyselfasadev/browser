#!/usr/bin/env python3
"""Why did the site theme do that? One real page, one theme, and for
each element matching a selector the chain of ancestors with their
colours and what the pass recorded about them.
    _sitediag.py URL THEME SELECTOR [settle-ms]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402

url, theme, sel = sys.argv[1], sys.argv[2], sys.argv[3]
settle = int(sys.argv[4]) if len(sys.argv) > 4 else 7000
B.CONFIG_FILE.write_text(json.dumps({
    "theme": theme, "look": "classic", "themeWeb": True, "forceDark": True,
    "translateLang": "en", "vaultPassword": False, "agentBridge": False}))
B._install_theme_flags()
app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1280, 900)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code, world):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, world, lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    return box.get("v")


view = win.new_tab(url=None)
spin(300)
view.load(QUrl(url))
spin(settle)
print("landed on", view.url().toString())
DIAG = r"""(function (sel) {
  var out = [], els = document.querySelectorAll(sel);
  for (var i = 0; i < els.length && i < 3; i++) {
    var chain = [], n = els[i];
    while (n && n.nodeType === 1 && chain.length < 14) {
      var cs = getComputedStyle(n);
      var o = window.__stOrig && window.__stOrig.get(n);
      var r = n.getBoundingClientRect();
      chain.push({tag: n.tagName, cls: String(n.className || "").slice(0, 36),
        bg: cs.backgroundColor, bgi: cs.backgroundImage.slice(0, 40),
        color: cs.color, rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
        style: (n.getAttribute("style") || "").slice(0, 90),
        rec: o ? {set: o.set, bg: o.bg, color: o.color, under: o.under,
                  seen: o.seen, after: o.after, gen: o.gen, text: o.text} : null});
      n = n.parentElement;
    }
    out.push(chain);
  }
  return JSON.stringify({stats: window.__stStats, run: window.__stRun, chains: out});
})(%s)""" % json.dumps(sel)
raw = js(view.page(), DIAG, B.APP_WORLD_ID)
data = json.loads(raw) if raw else {}
print("stats", data.get("stats"), "run", data.get("run"))
spin(5000)
print("stats 5s later", js(view.page(), "JSON.stringify(window.__stStats)", B.APP_WORLD_ID))
spin(5000)
print("stats 10s later", js(view.page(), "JSON.stringify(window.__stStats)", B.APP_WORLD_ID))
for chain in data.get("chains", []):
    print("----")
    for c in chain:
        print("  %-8s %-36s bg=%-22s bgi=%-14s color=%-20s rect=%s" % (
            c["tag"], c["cls"], c["bg"], c["bgi"][:14], c["color"], c["rect"]))
        if c["style"]:
            print("           style:", c["style"])
        if c["rec"]:
            print("           rec:", json.dumps(c["rec"]))
view.grab().save(str(Path(sys.argv[5]) if len(sys.argv) > 5 else "sitediag.png"))
app.quit()
