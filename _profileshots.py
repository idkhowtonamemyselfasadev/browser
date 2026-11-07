#!/usr/bin/env python3
"""Signed-in pages in every theme, from a COPY of a real profile.

View only. The browser is booted offscreen on a copy of a data
directory (cookies included, so the pages come up signed in), each
address is opened and left alone -- nothing is clicked, typed, sent
or changed -- and every theme is applied to it live, with
_siteaudit.js measuring what the page reads like and a screenshot
kept per theme. The copy and the screenshots are the caller's to
delete afterwards; nothing here writes outside OUT and the copy.

    _profileshots.py --copy DIR --out DIR --urls a,b [--themes all|k1,k2]
                     [--settle 9000] [--dwell 1300]

--copy is a directory holding `share/browser` (the data directory as
copied) and is used as XDG_DATA_HOME, so the engine finds the copied
cookie jar under the application's own name; config.json in the copy
is edited so no saved tabs are restored and no bridge is opened.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--copy", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--urls", required=True)
ap.add_argument("--themes", default="all")
ap.add_argument("--settle", type=int, default=9000)
ap.add_argument("--dwell", type=int, default=1300)
ap.add_argument("--width", type=int, default=1400)
ap.add_argument("--height", type=int, default=900)
ap.add_argument("--diag", default="", help="selector: print records of matching elements after each theme")
ap.add_argument("--diag-area", default="", help="x,y,w,h in CSS px: only elements inside it")
args = ap.parse_args()

COPY = Path(args.copy).resolve()
HOME = COPY / "share" / "browser"
if not (HOME / "config.json").exists():
    sys.exit("no copied profile at %s" % HOME)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
os.environ["BROWSER_NO_UPDATE_CHECK"] = "1"
os.environ["BROWSER_NO_AGENT"] = "1"
os.environ["XDG_DATA_HOME"] = str(COPY / "share")
os.environ["XDG_CONFIG_HOME"] = str(COPY / "config")
os.environ["XDG_CACHE_HOME"] = str(COPY / "cache")
os.environ["BROWSER_HOME"] = str(HOME)
cfg = json.loads((HOME / "config.json").read_text())
cfg.update({"restoreTabs": False, "agentBridge": False, "themeWeb": True,
            "look": "classic", "translateLang": "en",
            # no vault: a master-password dialog would block an
            # offscreen browser for ever, and nothing here fills a form
            "vaultPassword": False})
cfg.pop("themeWebSkip", None)
(HOME / "config.json").write_text(json.dumps(cfg))
for name in ("tabs.txt", "session.json"):
    try:
        (HOME / name).unlink()
    except OSError:
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# where it is, if it stops answering: SIGUSR1 dumps every thread's stack
import faulthandler  # noqa: E402
import signal  # noqa: E402
faulthandler.register(signal.SIGUSR1, all_threads=True)
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog  # noqa: E402

# No dialog can be answered offscreen, and a modal one blocks the event
# loop for ever (Outlook asks to become the mailto: handler the moment
# it loads: QMessageBox.question). Every modal is answered "No" or
# "cancel" before it is shown, which is also the only answer a
# view-only run may give.
_NO = QMessageBox.StandardButton.No
QMessageBox.question = staticmethod(lambda *a, **k: _NO)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QDialog.exec = lambda self, *a, **k: 0
QDialog.open = lambda self, *a, **k: None
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402

AUDIT = (HERE / "_siteaudit.js").read_text(encoding="utf-8")
OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
B._install_theme_flags()
app = QApplication(sys.argv[:1])
app.setApplicationName("browser")       # the engine's storage is named after it
win = B.Browser()
win.resize(args.width, args.height)
win.show()
themes = ([t["key"] for t in B.THEMES] if args.themes == "all"
          else [t for t in args.themes.split(",") if t])


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code, timeout=12000):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    return box.get("v", "__timeout__")


def load(view, url, settle):
    box = {"done": None}

    def fin(ok):
        box["done"] = ok
    c = view.loadFinished.connect(fin)
    view.load(QUrl(url))
    waited = 0
    while box["done"] is None and waited < 40000:
        spin(100)
        waited += 100
    view.loadFinished.disconnect(c)
    spin(settle)
    return box["done"]


def flat_boxes(img, boxes):
    if img.format() != QImage.Format.Format_RGB32:
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = img.constBits()
    buf.setsize(bpl * h)
    mv = memoryview(buf)
    flat, looked = 0, 0
    for box in boxes:
        x, y, bw, bh = box[0], box[1], box[2], box[3]
        if bw < 16 or bh < 8 or x + bw > w or y + bh > h:
            continue
        step = 2 if bw * bh < 20000 else 3
        vals = []
        for yy in range(y, y + bh, step):
            row = yy * bpl
            for xx in range(x, x + bw, step):
                o = row + xx * 4
                vals.append((mv[o + 2] * 54 + mv[o + 1] * 183 + mv[o] * 19) >> 8)
        if len(vals) < 20:
            continue
        looked += 1
        if max(vals) - min(vals) < 12:
            flat += 1
    return flat, looked


def settle_pass(view, dwell, limit=12000):
    """Wait until the pass has nothing left in its queue (a theme
    switch on a 20000-element app takes seconds), then the dwell."""
    waited = 0
    while waited < limit:
        spin(200)
        waited += 200
        box = {}
        loop = QEventLoop()
        view.page().runJavaScript(
            "(window.__stStats && (window.__stStats.queue + window.__stStats.pendingN)) || 0",
            B.APP_WORLD_ID, lambda r: (box.update({"v": r}), loop.quit()))
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        if box.get("v") == 0:
            break
    # ...and the one slice a fired timer queues
    spin(300)
    spin(dwell)


def slug(url):
    s = re.sub(r"^https?://", "", url).replace("www.", "")
    return re.sub(r"[^a-z0-9.]+", "_", s.lower()).strip("_")[:50]


rows = open(OUT / "rows.jsonl", "a", encoding="utf-8")


def say(msg):
    print("%s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


view = win.new_tab(url=None)
spin(500)
for url in [u for u in args.urls.split(",") if u]:
    name = slug(url)
    say("load %s" % url)
    ok = load(view, url, args.settle)
    say("  landed on %s (ok=%s)" % (view.url().toString()[:90], ok))
    stuck = 0
    for key in themes:
        win.apply_theme(key, save=False)
        settle_pass(view, args.dwell)
        row = {"site": url, "slug": name, "theme": key,
               "dark": bool(B.theme_is_dark(key)),
               "final": view.url().toString()[:120], "loaded": bool(ok)}
        if stuck >= 3:
            row["error"] = "page busy (skipped)"
            rows.write(json.dumps(row) + "\n")
            rows.flush()
            continue
        raw = js(view.page(), AUDIT)
        stuck = stuck + 1 if raw == "__timeout__" else 0
        try:
            data = json.loads(raw) if isinstance(raw, str) else None
        except ValueError:
            data = None
        if not data:
            row["error"] = str(raw)[:120]
            rows.write(json.dumps(row) + "\n")
            rows.flush()
            say("  %-20s NO AUDIT" % key)
            continue
        img = view.grab().toImage()
        flat, looked = flat_boxes(img, data.get("boxes") or [])
        data.pop("boxes", None)
        # the text of the worst offenders is layout, not content: keep
        # only the tag and the colours, never what the page said
        for w in data.get("worst", []):
            w.pop("text", None)
            w.pop("id", None)
        data.pop("title", None)
        row.update(data)
        row["flat"], row["flatLooked"] = flat, looked
        judged = max(1, data.get("judged", 0))
        row["badFrac"] = round(data.get("bad", 0) / judged, 4)
        row["isBad"] = bool(row["badFrac"] > 0.02 or data.get("badInputs", 0)
                            or (looked and flat / looked > 0.15))
        img.save(str(OUT / ("%s--%s.jpg" % (name, key))), "JPEG", 70)
        if args.diag:
            area = [int(v) for v in args.diag_area.split(",")] if args.diag_area else None
            DIAG = r"""(function (sel, area) {
  var out = [], els = document.querySelectorAll(sel), n = 0;
  for (var i = 0; i < els.length && n < 3; i++) {
    var el = els[i], r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (area && !(r.left >= area[0] && r.top >= area[1] && r.right <= area[0] + area[2] && r.bottom <= area[1] + area[3])) continue;
    var txt = ""; for (var k = 0; k < el.childNodes.length; k++) if (el.childNodes[k].nodeType === 3) txt += el.childNodes[k].nodeValue;
    if (!txt.trim()) continue;
    n++;
    var chain = [], node = el;
    while (node && node.nodeType === 1 && chain.length < 7) {
      var cs = getComputedStyle(node), o = window.__stOrig && window.__stOrig.get(node);
      chain.push({tag: node.tagName, cls: String(node.className || "").slice(0, 28), bg: cs.backgroundColor, color: cs.color,
        tr: cs.transitionDuration.slice(0, 12) + "/" + cs.transitionProperty.slice(0, 24),
        style: (node.getAttribute("style") || "").slice(0, 70),
        rec: o ? {set: o.set, color: o.color, bg: o.bg, after: o.after, gen: o.gen.slice(0, 4), under: o.under, waits: o.waits, flips: o.flips, pending: o.pending, text: o.text} : null});
      node = node.parentElement;
    }
    out.push({len: txt.trim().length, chain: chain});
  }
  var st = window.__stStats || {};
  return JSON.stringify({vw: innerWidth, vh: innerHeight, run: window.__stRun, gen: window.__stGen, stats: st, els: out});
})(%s, %s)""" % (json.dumps(args.diag), json.dumps(area))
            box = {}
            loop = QEventLoop()
            view.page().runJavaScript(DIAG, B.APP_WORLD_ID, lambda r: (box.update({"v": r}), loop.quit()))
            QTimer.singleShot(15000, loop.quit)
            loop.exec()
            try:
                d = json.loads(box.get("v") or "{}")
            except ValueError:
                d = {"raw": str(box.get("v"))[:200]}
            st = d.get("stats", {})
            say("  DIAG %s run=%s gen=%s vw=%s vh=%s stats=%s" % (key, d.get("run"), d.get("gen"), d.get("vw"), d.get("vh"),
                {k: (round(v) if isinstance(v, float) else v) for k, v in st.items() if k != "why"}))
            for w in (st.get("why") or [])[:6]:
                say("    why: " + w[:160])
            for e in d.get("els", []):
                say("    element (%d chars):" % e["len"])
                for c in e["chain"]:
                    say("      %-6s %-28s bg=%-20s color=%-20s tr=%s" % (c["tag"], c["cls"], c["bg"], c["color"], c["tr"]))
                    if c["style"]:
                        say("             style: " + c["style"])
                    if c["rec"]:
                        say("             rec: " + json.dumps(c["rec"]))
        rows.write(json.dumps(row) + "\n")
        rows.flush()
        say("  %-20s themed=%s bad=%4.1f%% weak=%4.1f%% inputs %d/%d flat %d/%d%s"
            % (key, data.get("themed"), 100 * row["badFrac"],
               100 * data.get("weak", 0) / judged, data.get("badInputs", 0),
               data.get("inputs", 0), flat, looked,
               "  <-- BAD" if row["isBad"] else ""))
    win.apply_theme("mocha", save=False)
    spin(300)
    old = view
    view = win.new_tab(url=None)
    spin(300)
    try:
        win.close_tab(win.tabs.indexOf(old), ask=False)
    except Exception:
        pass
    spin(300)
say("done")
rows.close()
app.quit()
os._exit(0)
