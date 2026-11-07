#!/usr/bin/env python3
"""Site theming: the rules the site x theme matrix taught it (2026-11-07).

Fifty-four real sites in every one of the 116 themes, measured in the
page and looked at, and each of these pages is the shape of one thing
that was wrong. Run against the theme_web.py of commit dc74e63 (the
tree before the fixes; theme-audit/check/rules_on_head.py does it),
23 of the 45 checks are red, in sections 1, 3, 4, 5, 6, 7, 9, 10 and 11.
Sections 2 and 8 are green on it: the placeholder page and the big
page are the shape of what the Microsoft sign-in page and the Outlook
landing page did on the old code, and this file pins the rule that
fixed them rather than reproducing the exact page.

  a theme switched while the page is open   -- one run at a time: the
                                               last theme's observer
                                               no longer fights the new
  a placeholder in a field left transparent -- judged against what is
                                               really behind the field
  a heading filled in by a script           -- words that arrive late
                                               are looked at again
  a headline over a sibling picture         -- left as the site drew it
  a card restyled by a late stylesheet      -- looked at again, however
                                               late (no cap of four)
  a card with a transition on its colours   -- read back as written,
                                               not mid-fade; no loop
  a link that already reads                 -- keeps its own colour
  a card whose colour is inherited          -- not "moved" when an
                                               ancestor is painted
  a headline cut out of a gradient          -- the gradient is the ink,
                                               not a picture behind it;
                                               the words inside get a
                                               fill of their own
  a section re-rendered around its text     -- a changed ground is not a
                                               disagreement: no cap on
                                               judging it afresh
  a big page re-themed live                 -- finishes in seconds, not
                                               a recalculation per
                                               element
  a theme switched over a panel that fades  -- what sits on the panel
                                               waits for it to settle
                                               (Outlook's calendar)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
import theme_web  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


HEAD = ("<!doctype html><meta charset=utf-8>"
        "<style>body{margin:0;font:16px/1.4 sans-serif}</style>")

SIGNIN = HEAD + """<title>signin</title>
<style>
.card { background: #fff; color: #1b1b1b; width: 440px; padding: 44px; }
.field { background: transparent; border: 0; border-bottom: 1px solid #666;
         color: #1b1b1b; width: 100%; font-size: 15px; padding: 6px 0; }
.field::placeholder { color: #000; opacity: .6; }
.heading { font-size: 24px; font-weight: 600; min-height: 30px; }
</style>
<div class=card>
  <div class=heading id=heading></div>
  <input class=field id=email placeholder="Email, phone, or Skype">
  <p id=note>No account? <a href=# id=create>Create one!</a></p>
</div>
<script>
setTimeout(function () {
  document.getElementById("heading").textContent = "Sign in";
  window.__filled = true;
}, 700);
</script>
"""

HERO = HEAD + """<title>hero</title>
<style>
.hero { position: relative; height: 320px; }
.hero img { position: absolute; inset: 0; width: 100%; height: 100%; }
.hero .copy { position: absolute; left: 40px; top: 60px; color: #0e1726; }
.hero h1 { margin: 0; font-size: 40px; }
</style>
<div class=hero>
  <img src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'><rect width='8' height='8' fill='%23dfe9f5'/></svg>">
  <div class=copy><h1 id=headline>Your inbox, organized.</h1>
  <p id=sub>Three accounts in one place.</p></div>
</div>
<p id=body>Ordinary text under the hero.</p>
"""

LATE = HEAD + """<title>late</title>
<section id=section><a class=card id=card href=#>
  <p id=desc>Think through projects, summarize threads.</p></a></section>
<script>
// the card's own stylesheet chunk lands well after the pass has been
// everywhere, and after what used to be its last look
var n = 0;
var t = setInterval(function () {
  var s = document.createElement("style");
  s.textContent = n === 5 ? "#card { background: #fff; color: #616161; display: block; padding: 20px }"
                          : ".filler" + n + " { color: red }";
  document.head.appendChild(s);
  if (++n > 6) { clearInterval(t); window.__late = true; }
}, 900);
</script>
"""

PANEL = HEAD + """<title>panel</title>
<style>
/* Outlook's month panel: a light panel with a transition on everything,
   dates inside it in the site's dark ink */
.panel { background: #f5f5f5; color: #242424; padding: 20px; width: 240px;
         transition: all .2s; }
.panel span { display: inline-block; width: 24px; }
</style>
<div class=panel id=panel>
  <span id=d1>1</span><span id=d2>2</span><span id=d3>3</span><span id=d4>4</span>
</div>
"""

FADE = HEAD + """<title>fade</title>
<style>
.card { background: #fff; color: #222; padding: 20px; width: 500px;
        transition: background-color .6s ease, color .6s ease; }
</style>
<div class=card id=card><p id=text>Text in a card that fades.</p></div>
<div class=card id=card2><span id=plain>A card whose colour is only inherited.</span></div>
"""

LINKS = HEAD + """<title>links</title>
<style>
body { color: #ddd; }
.dark { background: #202020; color: #e8e8e8; padding: 20px; }
.dark a { color: #ffd27f; }
.white { background: #fff; color: #222; padding: 20px; }
.white a { color: #0645ad; }
</style>
<div class=dark><a href=# id=gold>A gold link that already reads</a></div>
<div class=white><a href=# id=blue>A blue link on a white card</a></div>
"""

BIG = (HEAD + "<title>big</title><style>.row{background:#fff;color:#2b2b2b}"
       "</style>"
       + "".join("<div class=row id=r%d><span>Zeile %d</span></div>" % (i, i)
                 for i in range(8000)))

GRAD = HEAD + """<title>grad</title>
<style>
h1 { margin: 24px; font-size: 40px; display: inline-block;
     -webkit-background-clip: text; background-clip: text;
     -webkit-text-fill-color: transparent; }
#ink, #split { background-image: linear-gradient(90deg, #000, #2a2a2a); }
#keep { background-image: linear-gradient(90deg, #8fd3ff, #ffb3dc); }
#filled { -webkit-text-fill-color: #1b1b1b; color: #fff; display: block; }
</style>
<h1 id=ink>Work smarter across the suite</h1><br>
<h1 id=keep>Pastel on dark reads</h1><br>
<h1 id=split><span id=part>Words in spans,</span> <span>gradient on the headline</span></h1>
<h2 id=filled>A fill the site set itself</h2>
<p id=body>Ordinary text under the headlines.</p>
"""

# a page that re-renders the section around a footnote again and again
# while it hydrates (the Outlook landing page): the footnote itself
# never changes, only what it sits on
HYDRATE = HEAD + """<title>hydrate</title>
<style>
.card { background: #fff; padding: 24px; }
#note { color: #17253d; font-size: 13px; }
</style>
<div id=host><div class=card><p id=note>Footnote text, dark navy, the site's own.</p></div></div>
<p id=body>Ordinary text under it.</p>
<script>
var n = 0;
var t = setInterval(function () {
  var fresh = document.createElement("div");
  fresh.className = "card";
  fresh.appendChild(document.getElementById("note"));
  var host = document.getElementById("host");
  host.replaceChild(fresh, host.firstElementChild);
  if (++n >= 9) { clearInterval(t); window.__rerendered = true; }
}, 220);
</script>
"""

PAGES = {"/signin": SIGNIN, "/hero": HERO, "/late": LATE, "/fade": FADE,
         "/links": LINKS, "/big": BIG, "/panel": PANEL, "/grad": GRAD,
         "/hydrate": HYDRATE}

AUDIT = (HERE / "_siteaudit.js").read_text(encoding="utf-8")


def rgb(s):
    n = [float(v) for v in re.findall(r"[\d.]+", s or "")]
    return (n + [0, 0, 0])[:3]


def css_of(view, selector, prop, pseudo=None):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?getComputedStyle(e%s).%s:null})()"
                % (json.dumps(selector), ", %s" % json.dumps(pseudo) if pseudo else "",
                   prop), B.MAIN_WORLD_ID)


def ratio(a, b):
    def chan(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def lum(c):
        return 0.2126 * chan(c[0]) + 0.7152 * chan(c[1]) + 0.0722 * chan(c[2])
    x, y = lum(a) + 0.05, lum(b) + 0.05
    return x / y if x > y else y / x


def audit(view):
    raw = H.js(view, AUDIT, B.MAIN_WORLD_ID)
    return json.loads(raw)


def stats(view):
    raw = H.js(view, "JSON.stringify(window.__stStats || {})", B.APP_WORLD_ID)
    return json.loads(raw or "{}")


app = H.app()
srv = H.Server(PAGES)
cfg = {"theme": "mocha", "look": "classic", "forceDark": True,
       "minFont": 0, "zoom": 1, "translateLang": "en"}
B.CONFIG_FILE.write_text(json.dumps(cfg))
win = B.Browser()
win.resize(1200, 800)
win.show()
H.spin(400)
view = win.new_tab(url=None)


def load(path, settle=900):
    H.load(view, srv.url(path))
    H.spin(settle)


print("\n(1) a theme switched while the page is open: one run, not two")
load("/signin", settle=1500)
card_dark = css_of(view, ".card", "backgroundColor")
check("on Mocha the white card is dark", rgb(card_dark)[0] < 60, card_dark)
win.apply_theme("latte")
H.spin(1800)
card_light = css_of(view, ".card", "backgroundColor")
check("on Latte the same card is light, not the last theme's dark",
      rgb(card_light)[0] > 200, card_light)
a = audit(view)
check("and nothing on it is unreadable", a["bad"] == 0, a["worst"][:3])
check("exactly one run is live",
      H.js(view, "window.__stRun", B.APP_WORLD_ID) == 2
      and H.js(view, "!!window.__stObs", B.APP_WORLD_ID))
win.apply_theme("mocha")
H.spin(1500)
card_dark2 = css_of(view, ".card", "backgroundColor")
check("and back to Mocha the card is dark again", rgb(card_dark2)[0] < 60,
      card_dark2)
# eight more switches: the pass gives an element up after six rounds
# of disagreeing with the site, and a theme switch must not count
for key in ("nord", "latte", "dracula", "papercolor", "gruvbox",
            "solarized-light", "terminal", "latte"):
    win.apply_theme(key, save=False)
    H.spin(900)
check("after eight more switches the card still follows (light on Latte)",
      rgb(css_of(view, ".card", "backgroundColor"))[0] > 200,
      css_of(view, ".card", "backgroundColor"))
win.apply_theme("mocha", save=False)
H.spin(1200)
check("...and dark on Mocha", rgb(css_of(view, ".card", "backgroundColor"))[0] < 60,
      css_of(view, ".card", "backgroundColor"))

print("\n(2) a placeholder is judged against what is behind the field")
ph = css_of(view, "#email", "color", "::placeholder")
bg = css_of(view, ".card", "backgroundColor")
r = ratio(rgb(ph), rgb(bg))
check("the placeholder reads on the dark card (was black at 60%%)",
      r >= 4.5, "%.2f %s on %s" % (r, ph, bg))
check("the field itself was not given a fill it did not have",
      css_of(view, "#email", "backgroundColor") == "rgba(0, 0, 0, 0)",
      css_of(view, "#email", "backgroundColor"))

print("\n(3) words that arrive after the look are looked at again")
check("the heading was filled in by the page",
      H.js(view, "!!window.__filled", B.MAIN_WORLD_ID))
hc = css_of(view, "#heading", "color")
r = ratio(rgb(hc), rgb(bg))
check("the late heading reads on the dark card", r >= 4.5,
      "%.2f %s on %s" % (r, hc, bg))

print("\n(4) a headline over a sibling picture is left as the site drew it")
load("/hero", settle=1500)
check("the headline keeps the site's colour",
      css_of(view, "#headline", "color") == "rgb(14, 23, 38)",
      css_of(view, "#headline", "color"))
check("so does the line under it",
      css_of(view, "#sub", "color") == "rgb(14, 23, 38)",
      css_of(view, "#sub", "color"))
check("while ordinary text on the page is themed",
      rgb(css_of(view, "#body", "color"))[0] > 150,
      css_of(view, "#body", "color"))

print("\n(5) a card restyled by a late stylesheet is looked at again")
load("/late", settle=7500)
check("the late stylesheets did land", H.js(view, "!!window.__late", B.MAIN_WORLD_ID))
cb = css_of(view, "#card", "backgroundColor")
dc = css_of(view, "#desc", "color")
check("the card that turned white late is dark now", rgb(cb)[0] < 60, cb)
r = ratio(rgb(dc), rgb(cb))
check("and its text reads on it (was theme-light on white)", r >= 4.5,
      "%.2f %s on %s" % (r, dc, cb))

print("\n(6) a card with a transition on its colours settles")
load("/fade", settle=3500)
s0 = stats(view)
cb = css_of(view, "#card", "backgroundColor")
tc = css_of(view, "#text", "color")
check("the fading card is dark", rgb(cb)[0] < 60, cb)
check("its text reads", ratio(rgb(tc), rgb(cb)) >= 4.5, (tc, cb))
H.js(view, "window.__stAdapt && window.__stAdapt(document)", B.APP_WORLD_ID)
H.spin(2500)
s1 = stats(view)
check("a second look over the page restores nothing (no mid-fade loop)",
      s1.get("flips", 0) - s0.get("flips", 0) == 0,
      "flips %s -> %s" % (s0.get("flips"), s1.get("flips")))
check("and the card whose colour is only inherited was never 'moved'",
      s1.get("why", []) == [] or not any("card2" in w for w in s1.get("why", [])),
      s1.get("why", [])[:3])

print("\n(7) a link that already reads keeps its own colour")
load("/links", settle=1500)
check("the gold link on the dark panel is still gold",
      css_of(view, "#gold", "color") == "rgb(255, 210, 127)",
      css_of(view, "#gold", "color"))
blue = css_of(view, "#blue", "color")
wbg = css_of(view, ".white", "backgroundColor")
check("the blue link on the card that turned dark was recoloured",
      blue != "rgb(6, 69, 173)" and ratio(rgb(blue), rgb(wbg)) >= 4.5,
      (blue, wbg))

print("\n(8) a big page re-themed live finishes in seconds")
load("/big", settle=6000)
check("the page was themed", rgb(css_of(view, "#r7999", "backgroundColor"))[0] < 120)
t0 = time.time()
win.apply_theme("latte")
H.spin(500)
# the first slice runs synchronously; the rest hop through a
# MessageChannel. Wait for the queue to drain, then ask how long the
# pass itself spent (not the wall clock, which is this test's own).
for _ in range(40):
    s = stats(view)
    last = rgb(css_of(view, "#r7999", "backgroundColor"))
    if last[0] > 200:
        break
    H.spin(250)
took = time.time() - t0
check("the last row is in the new theme", last[0] > 200, last)
check("and it took under 12 seconds for 16000 elements (was a style "
      "recalculation per restored element)", took < 12, "%.1fs" % took)
win.apply_theme("mocha")
H.spin(500)

print("\n(9) a theme switched over a panel that fades: what sits on it waits")
load("/panel", settle=1500)
pb = css_of(view, "#panel", "backgroundColor")
check("on Mocha the light panel is dark", rgb(pb)[0] < 60, pb)
check("and a date on it reads", ratio(rgb(css_of(view, "#d2", "color")), rgb(pb)) >= 4.5,
      (css_of(view, "#d2", "color"), pb))
win.apply_theme("latte", save=False)
H.spin(2500)
pb = css_of(view, "#panel", "backgroundColor")
dc = css_of(view, "#d2", "color")
check("on Latte the panel is light again (the site's own, no repaint needed)",
      rgb(pb)[0] > 200, pb)
check("and the date was not judged against the dark the panel was fading "
      "from: it reads on the light panel (was white on light)",
      ratio(rgb(dc), rgb(pb)) >= 4.5, "%.2f %s on %s" % (ratio(rgb(dc), rgb(pb)), dc, pb))
win.apply_theme("mocha", save=False)
H.spin(1200)

print("\n(10) a headline cut out of a gradient: the gradient is the ink, not a picture")
load("/grad", settle=1500)
bb = css_of(view, "body", "backgroundColor")
check("on Mocha the white page is dark", rgb(bb)[0] < 60, bb)
fill = css_of(view, "#ink", "webkitTextFillColor")
check("the black-gradient headline is no longer cut out of its gradient (was "
      "black letters on the dark page, and 'a picture, leave it' to the pass)",
      css_of(view, "#ink", "backgroundImage") == "none"
      and ratio(rgb(fill), rgb(bb)) >= 4.5, (fill, bb))
check("the pastel gradient, which reads on dark, is kept",
      "gradient" in (css_of(view, "#keep", "backgroundImage") or ""))
pf = css_of(view, "#part", "webkitTextFillColor")
check("the words inside such a headline (spans with an inherited transparent "
      "fill) get a fill of their own that reads", ratio(rgb(pf), rgb(bb)) >= 4.5, (pf, bb))
ff = css_of(view, "#filled", "webkitTextFillColor")
check("a heading whose fill the site set itself is repainted in its fill, not "
      "only in `color`", ratio(rgb(ff), rgb(bb)) >= 4.5, (ff, bb))
a = audit(view)
check("the audit sees gradient letters too, and finds nothing unreadable",
      a["bad"] == 0 and a["judged"] > 0, a["worst"][:3])
win.apply_theme("latte", save=False)
H.spin(2000)
bb = css_of(view, "body", "backgroundColor")
check("on Latte the black gradient is the site's own again (it reads on light)",
      "gradient" in (css_of(view, "#ink", "backgroundImage") or ""),
      css_of(view, "#ink", "backgroundImage"))
kf = css_of(view, "#keep", "webkitTextFillColor")
check("and the pastel one, unreadable on light, is now letters in a colour that reads",
      css_of(view, "#keep", "backgroundImage") == "none"
      and ratio(rgb(kf), rgb(bb)) >= 4.5, (kf, bb))
a = audit(view)
check("nothing unreadable on Latte either", a["bad"] == 0, a["worst"][:3])
win.apply_theme("mocha", save=False)
H.spin(1200)

print("\n(11) a section re-rendered nine times around its footnote: not a disagreement")
load("/hydrate", settle=3800)
check("the page did re-render the section nine times",
      H.js(view, "!!window.__rerendered", B.MAIN_WORLD_ID))
cb = css_of(view, "#host .card", "backgroundColor")
nc = css_of(view, "#note", "color")
check("the last card is dark", rgb(cb)[0] < 60, cb)
check("and the footnote reads on it (was given up after six re-looks and left in the "
      "site's navy on the dark card)", ratio(rgb(nc), rgb(cb)) >= 4.5,
      "%.2f %s on %s" % (ratio(rgb(nc), rgb(cb)), nc, cb))

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.stdout.flush()
    os._exit(1)
print("all good")
# os._exit skips the interpreter's teardown (and the engine crash that
# lives in it) -- and the buffered stdout with it, unless it is flushed
sys.stdout.flush()
os._exit(0)
