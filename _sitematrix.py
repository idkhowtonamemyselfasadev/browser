#!/usr/bin/env python3
"""Real websites x every theme: measured, photographed, written down.

Offscreen, scratch data, the real network. One browser, one tab; each
site is loaded once and then every theme is applied to it live, the
way Settings > Theme does it, with _siteaudit.js measuring what the
page reads like after each one and a screenshot of the view kept for
the themes worth looking at (and for every one that failed).

    _sitematrix.py --out DIR [--sites a.com,b.com | --list FILE]
                   [--themes all|dark|light|k1,k2] [--shots anchors|all|none]
                   [--boot mocha] [--settle 7000]

The result is DIR/rows.jsonl, one JSON object per (site, theme), which
_sitereport.py turns into the matrix. Nothing is signed in to and no
page is interacted with: the sign-in pages are measured as they come.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# --theme-module PATH: measure with another theme_web.py (the one git
# HEAD had, for a "before" matrix) in place of the tree's. It has to
# be in sys.modules before browser.py is imported, which is what
# _boot does, so the flag is read here by hand.
if "--theme-module" in sys.argv:
    import importlib.util
    _path = sys.argv[sys.argv.index("--theme-module") + 1]
    _spec = importlib.util.spec_from_file_location("theme_web", _path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["theme_web"] = _mod
    _spec.loader.exec_module(_mod)
import tmpscratch  # noqa: E402,F401  (claims a scratch dir, swept)
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402

HERE = Path(__file__).resolve().parent
AUDIT = (HERE / "_siteaudit.js").read_text(encoding="utf-8")

ANCHORS = ["mocha", "latte", "gruvbox", "gruvbox-light", "nord", "dracula",
           "solarized-light", "high-contrast", "terminal", "newspaper",
           "sepia", "gameboy", "synthwave", "aero", "steampunk",
           "papercolor", "one-light", "github-light", "tokyonight-day",
           "amber", "c64", "blueprint", "wood"]

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--sites", default="")
ap.add_argument("--list", default="")
ap.add_argument("--themes", default="all")
ap.add_argument("--shots", default="anchors")
ap.add_argument("--boot", default="mocha")
ap.add_argument("--settle", type=int, default=6000)
ap.add_argument("--dwell", type=int, default=1100)
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--height", type=int, default=900)
ap.add_argument("--fresh", action="store_true",
                help="load the site again for every theme (the first-visit "
                     "path) instead of re-theming it live")
ap.add_argument("--audit-timeout", type=int, default=9000)
ap.add_argument("--shard", default="", help="i/n: every n-th site from i")
ap.add_argument("--theme-module", default="", help="another theme_web.py to measure")
args = ap.parse_args()

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
sites = [s for s in args.sites.split(",") if s]
if args.list:
    for line in Path(args.list).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            sites.append(line)

if args.shard:
    i, n = [int(x) for x in args.shard.split("/")]
    sites = sites[i::n]

B.CONFIG_FILE.write_text(json.dumps({
    "theme": args.boot, "look": "classic", "themeWeb": True,
    "forceDark": True, "translateLang": "en", "vaultPassword": False,
    "agentBridge": False}))
B._install_theme_flags()

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(args.width, args.height)
win.show()

if args.themes == "all":
    themes = [t["key"] for t in B.THEMES]
elif args.themes == "dark":
    themes = [t["key"] for t in B.THEMES if t["dark"]]
elif args.themes == "light":
    themes = [t["key"] for t in B.THEMES if not t["dark"]]
else:
    themes = [t for t in args.themes.split(",") if t]


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code, world=None, timeout=15000):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID if world is None else world,
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
    while box["done"] is None and waited < 30000:
        spin(100)
        waited += 100
    view.loadFinished.disconnect(c)
    spin(settle)
    return box["done"]


def flat_boxes(img, boxes):
    """How many of the text boxes the page says are visible have no
    visible text in the picture: a flat patch of one colour where
    words should be. This is the check that needs no trust in the
    DOM: invisible text is invisible here whatever the styles say."""
    if img.format() != QImage.Format.Format_RGB32:
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    buf = img.constBits()
    buf.setsize(bpl * h)
    mv = memoryview(buf)
    flat, looked, samples = 0, 0, []
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
                b, g, r = mv[o], mv[o + 1], mv[o + 2]
                vals.append((r * 54 + g * 183 + b * 19) >> 8)
        if len(vals) < 20:
            continue
        looked += 1
        lo, hi = min(vals), max(vals)
        if hi - lo < 12:
            flat += 1
            if len(samples) < 8:
                samples.append({"rect": [x, y, bw, bh], "text": box[7],
                                "fg": box[4], "bg": box[5], "ratio": box[6],
                                "span": hi - lo})
    return flat, looked, samples


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
    return re.sub(r"[^a-z0-9.]+", "_", s.lower()).strip("_")[:60]


rows = open(OUT / "rows.jsonl", "a", encoding="utf-8")
log = open(OUT / "log.txt", "a", encoding="utf-8")


def say(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()


view = win.new_tab(url=None)
spin(500)
for site in sites:
    url = site if site.startswith("http") else "https://" + site
    name = slug(site)
    if not args.fresh:
        say("load %s" % url)
        ok = load(view, url, args.settle)
        final = view.url().toString()
        say("  landed on %s (ok=%s)" % (final, ok))
    stuck = 0
    for key in themes:
        if args.fresh:
            # the theme is on the jar before the page is created, so
            # the script runs once, at document creation, as on a
            # first visit; and a fresh tab, so nothing of the last
            # page's process is inherited
            win.apply_theme(key, save=False)
            spin(200)
            say("load %s in %s" % (url, key))
            ok = load(view, url, args.settle)
            final = view.url().toString()
            say("  landed on %s (ok=%s)" % (final, ok))
        else:
            win.apply_theme(key, save=False)
            settle_pass(view, args.dwell)
        if stuck >= 5:
            # a page whose main thread no longer answers is not going
            # to answer for the next hundred themes either
            rows.write(json.dumps({"site": site, "slug": name, "theme": key,
                                   "dark": bool(B.theme_is_dark(key)),
                                   "final": final, "loaded": bool(ok),
                                   "error": "page busy (skipped)"}) + "\n")
            rows.flush()
            continue
        raw = js(view.page(), AUDIT, timeout=args.audit_timeout)
        if raw == "__timeout__":
            # a page busy with its own work (the Outlook landing page
            # runs 15-30 s of script after load): one more try, later
            spin(6000)
            raw = js(view.page(), AUDIT, timeout=args.audit_timeout)
        stuck = stuck + 1 if raw == "__timeout__" else 0
        row = {"site": site, "slug": name, "theme": key,
               "dark": bool(B.theme_is_dark(key)), "final": final,
               "loaded": bool(ok)}
        try:
            data = json.loads(raw) if isinstance(raw, str) else None
        except ValueError:
            data = None
        if not data:
            row["error"] = str(raw)[:120]
            rows.write(json.dumps(row) + "\n")
            rows.flush()
            say("  %-20s NO AUDIT (%s)" % (key, str(raw)[:60]))
            continue
        img = view.grab().toImage()
        flat, looked, samples = flat_boxes(img, data.get("boxes") or [])
        data.pop("boxes", None)
        row.update(data)
        row["flat"] = flat
        row["flatLooked"] = looked
        row["flatSamples"] = samples
        judged = max(1, data.get("judged", 0))
        badness = data.get("bad", 0) / judged
        row["badFrac"] = round(badness, 4)
        is_bad = (badness > 0.02 or data.get("badInputs", 0) > 0
                  or (looked and flat / looked > 0.15))
        row["isBad"] = bool(is_bad)
        shoot = (args.shots == "all"
                 or (args.shots == "anchors" and (key in ANCHORS or is_bad)))
        if shoot:
            shot = OUT / ("%s--%s.jpg" % (name, key))
            img.save(str(shot), "JPEG", 72)
            row["shot"] = shot.name
        rows.write(json.dumps(row) + "\n")
        rows.flush()
        say("  %-20s themed=%s bad=%4.1f%% weak=%4.1f%% unjudged=%4.1f%% "
            "inputs %d/%d flat %d/%d%s"
            % (key, data.get("themed"), 100 * badness,
               100 * data.get("weak", 0) / judged,
               100 * data.get("unjudged", 0) / max(1, data.get("chars", 1)),
               data.get("badInputs", 0), data.get("inputs", 0), flat, looked,
               "  <-- BAD" if is_bad else ""))
    # the next site starts from the boot theme, like a fresh start,
    # and in a new tab: a page that has been through a hundred themes
    # is not the page the next site should inherit a process from
    win.apply_theme(args.boot, save=False)
    spin(300)
    old = view
    view = win.new_tab(url=None)
    spin(300)
    try:
        win.close_tab(win.tabs.indexOf(old), ask=False)
    except Exception:
        pass
    spin(300)

say("done: %d sites x %d themes" % (len(sites), len(themes)))
rows.close()
log.close()
app.quit()
sys.exit(0)
