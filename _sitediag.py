#!/usr/bin/env python3
"""Why did the site theme do that? One real page, one theme, and for
each element matching a selector the chain of ancestors with their
colours and what the pass recorded about them.
    _sitediag.py URL THEME SELECTOR [settle-ms] [shot.png]
With DIAG_SWITCH=<theme2> in the environment the page is re-themed
live after the first look and the pass's counters (and the JS heap)
are printed every 2 s for DIAG_WATCH seconds (default 30): the shape
of a pass that does not come to rest."""
import json
import os
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
        bg: cs.backgroundColor, bgi: cs.backgroundImage.slice(0, 160),
        clip: cs.webkitBackgroundClip, fill: cs.webkitTextFillColor,
        color: cs.color, rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
        style: (n.getAttribute("style") || "").slice(0, 90),
        rec: o ? {set: o.set, bg: o.bg, color: o.color, under: o.under,
                  seen: o.seen, after: o.after, gen: o.gen, text: o.text,
                  flips: o.flips, given: o.given, sib: o.sib} : null});
      n = n.parentElement;
    }
    out.push(chain);
  }
  var stack = [];
  var groundNow = els.length && window.__stGround ? window.__stGround(els[0]) : null;
  if (els.length) {
    var r0 = els[0].getBoundingClientRect();
    var pts = document.elementsFromPoint(r0.left + Math.min(r0.width / 2, 12),
                                         r0.top + Math.min(r0.height / 2, 10));
    var below = false;
    for (var k = 0; k < pts.length && stack.length < 12; k++) {
      var e = pts[k];
      if (e === els[0]) { below = true; continue; }
      if (!below) continue;
      var ecs = getComputedStyle(e);
      stack.push({tag: e.tagName, cls: String(e.className || "").slice(0, 30),
        anc: e.contains(els[0]), bg: ecs.backgroundColor, bgi: ecs.backgroundImage.slice(0, 50),
        op: ecs.opacity, vis: ecs.visibility, w: Math.round(e.getBoundingClientRect().width)});
    }
  }
  return JSON.stringify({stats: window.__stStats, run: window.__stRun, chains: out, stack: stack, ground: groundNow});
})(%s)""" % json.dumps(sel)
KEYS = ["slices", "measured", "painted", "fulls", "obs", "flips", "waits",
        "reputs", "pendingN", "queue", "ms"]
WATCH = ("(function(){var e=document.querySelector(%s);var o=e&&window.__stOrig&&window.__stOrig.get(e);"
         "return JSON.stringify([window.__stStats, performance.memory ? performance.memory.usedJSHeapSize : 0,"
         " document.getElementsByTagName('*').length, e ? [getComputedStyle(e).color, o ? o.under : null, o ? o.set : null,"
         " getComputedStyle(document.body).backgroundColor, String(document.documentElement.className).slice(0, 30),"
         " window.__stGround ? window.__stGround(e) : null] : null])})()" % json.dumps(sel))


def brief(label):
    raw = js(view.page(), WATCH, B.APP_WORLD_ID)
    st, heap, n, first = json.loads(raw) if raw else ({}, 0, 0, None)
    st = st or {}
    print("%-9s" % label, " ".join("%s=%s" % (k, int(st.get(k, 0) or 0)) for k in KEYS),
          "heapMB=%d" % (heap // 1048576), "nodes=%d" % n,
          "| first match: color=%s under=%s set=%s ground=%s body=%s html.class=%s" % (
              first[0], first[1], first[2], first[5], first[3], first[4]) if first else "",
          flush=True)


def chains():
    raw = js(view.page(), DIAG, B.APP_WORLD_ID)
    data = json.loads(raw) if raw else {}
    print("stats", data.get("stats"), "run", data.get("run"))
    print("ground now (what the pass sees behind the first match):", data.get("ground"))
    if data.get("stack"):
        print("---- under the first match (hit test):")
        for e in data["stack"]:
            print("  %-8s %-30s %s bg=%s bgi=%s op=%s vis=%s w=%s" % (
                e["tag"], e["cls"], "ancestor" if e["anc"] else "sibling ", e["bg"],
                e["bgi"][:30], e["op"], e["vis"], e["w"]))
    for chain in data.get("chains", []):
        print("----")
        for c in chain:
            print("  %-8s %-36s bg=%-22s bgi=%-14s color=%-20s rect=%s" % (
                c["tag"], c["cls"], c["bg"], c["bgi"][:14], c["color"], c["rect"]))
            if c["bgi"] not in ("none", ""):
                print("           bgi:", c["bgi"], "| clip:", c["clip"], "| fill:", c["fill"])
            if c["style"]:
                print("           style:", c["style"])
            if c["rec"]:
                print("           rec:", json.dumps(c["rec"]))


chains()
spin(5000)
print("stats 5s later", js(view.page(), "JSON.stringify(window.__stStats)", B.APP_WORLD_ID))
spin(5000)
print("stats 10s later", js(view.page(), "JSON.stringify(window.__stStats)", B.APP_WORLD_ID))
if os.environ.get("DIAG_SWITCH") or os.environ.get("DIAG_WATCH"):
    brief("before")
    if os.environ.get("DIAG_SWITCH"):
        win.apply_theme(os.environ["DIAG_SWITCH"], save=False)
    for t in range(0, int(os.environ.get("DIAG_WATCH", "30")), 2):
        spin(2000)
        brief("+%ds" % (t + 2))
    chains()
view.grab().save(str(Path(sys.argv[5]) if len(sys.argv) > 5 else "sitediag.png"))
app.quit()
