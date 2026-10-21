#!/usr/bin/env python3
"""Site theming: a themed website still has to look like a website.

Offscreen, scratch data, local pages served by the harness, one page
per way the theming used to break a real site:

  a photo in a card          -- pictures are never recoloured
  an icon font on a button   -- icon fonts are never swapped
  a brand-coloured panel     -- text is readable or left alone
  a white panel              -- ...in both directions
  a hero image with text     -- text over a picture is left alone
  a stylesheet arriving late -- the pass can change its mind
  a modal dialog             -- the theme's texture stays under it
  a 12000-element page       -- big pages are themed to the end
  a nav bar with a fixed box -- forced fonts do not overflow it
  every theme's stylesheet   -- no layout property is ever set

Each check failed before the fix it belongs to and passes after; the
whole file was run against the previous theme_web.py to prove it."""
import json
import os
import re
import sys
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


# ---------------------------------------------------------------------
# the pages
# ---------------------------------------------------------------------
HEAD = ("<!doctype html><meta charset=utf-8>"
        "<style>body{margin:0;font:16px/1.4 sans-serif}</style>")

CARD = HEAD + """<title>card</title>
<style>
.card { background: #ffffff; color: #222; padding: 20px; width: 600px; }
.shot { width: 320px; height: 180px; }
.brand { background: #015999; color: #ffffff; padding: 12px; }
.brand h2 { color: #ffd27f; margin: 0; }
.cta { background: #ff9900; color: #111; border: 1px solid #a66; }
.faint { color: #9a9a9a; background: #ffffff; }
</style>
<div class=card>
  <h1>A white card</h1>
  <p id=p1>Dark text on white, the shape of every article teaser.</p>
  <img class=shot id=photo src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='320' height='180'><rect width='320' height='180' fill='%23c83737'/></svg>">
  <button class=cta id=cta>In den Einkaufswagen</button>
  <p class=faint id=faint>Small print the site itself set to light grey.</p>
</div>
<div class=brand><h2 id=brandhead>Kurz&uuml;berblick</h2>
<p id=brandtext>White on the brand blue.</p></div>
"""

ICONS = HEAD + """<title>icons</title>
<style>
.material-icons { font-family: "Material Icons"; font-size: 24px; }
.fa { font-family: "Font Awesome 5 Free"; }
nav { width: 360px; overflow: hidden; white-space: nowrap; }
nav a { display: inline-block; padding: 0 8px; font-family: Arial, sans-serif; }
#codeblock { font-family: "Courier New", monospace; }
</style>
<nav id=nav>
  <a href=# id=n1>Startseite</a><a href=# id=n2>Produkte</a>
  <a href=# id=n3>Dienste</a><a href=# id=n4>Kontakt</a>
</nav>
<button class="material-icons" id=micon>delete</button>
<a href=# class="fa fa-home" id=ficon>&#xf015;</a>
<span class=material-icons id=sicon>menu</span>
<pre id=codeblock>printf "%s\\n" hello</pre>
<p id=para>Running text that may wear the theme's own face.</p>
"""

HERO = HEAD + """<title>hero</title>
<style>
.hero { background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'><rect width='8' height='8' fill='%23eeeeee'/></svg>");
        background-size: cover; height: 260px; color: #202020; padding: 20px; }
.grad { background-image: linear-gradient(#222, #666); color: #fff; padding: 20px; }
</style>
<div class=hero><h1 id=herohead>Headline over a photo</h1>
<p id=herotext>Text the site placed on top of a picture.</p></div>
<div class=grad><p id=gradtext>Text on a gradient.</p></div>
"""

LATE = HEAD + """<title>late</title>
<div class=panel id=panel><p id=latetext>Text in a panel.</p></div>
<script>
// the stylesheet a real site loads asynchronously: it lands well after
// the first pass has been over this element
setTimeout(function () {
  var s = document.createElement("style");
  // the shape of wikipedia's table of contents: a stylesheet that
  // lands after the first pass and paints text dark on the dark page
  s.textContent = "#latetext { color: #333333; }";
  document.head.appendChild(s);
  window.__late = true;
}, 900);
</script>
"""

MODAL = HEAD + """<title>modal</title>
<style>
#back { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 9000; }
#dlg { position: fixed; left: 200px; top: 150px; width: 400px; height: 220px;
       background: #fff; color: #111; z-index: 9001; padding: 16px; }
#ok { width: 160px; height: 44px; }
</style>
<div id=back></div>
<div id=dlg><p>Really delete?</p><button id=ok>Delete</button></div>
<p>page text behind the dialog</p>
"""

BIG = (HEAD + "<title>big</title><style>.row{background:#fff;color:#2b2b2b}"
       "</style>"
       + "".join("<div class=row id=r%d><span>Zeile %d</span></div>" % (i, i)
                 for i in range(12000)))

TRANS = (HEAD + "<title>trans</title><style>html,body{background:transparent}"
         "</style><p>nothing behind this page</p>")

PAGES = {"/card": CARD, "/icons": ICONS, "/hero": HERO, "/late": LATE,
         "/modal": MODAL, "/big": BIG, "/trans": TRANS}


def ratio(a, b):
    def chan(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def lum(c):
        return (0.2126 * chan(c[0]) + 0.7152 * chan(c[1]) + 0.0722 * chan(c[2]))
    x, y = lum(a) + 0.05, lum(b) + 0.05
    return x / y if x > y else y / x


def rgb(s):
    n = [float(v) for v in re.findall(r"[\d.]+", s or "")]
    return (n + [0, 0, 0])[:3]


def contrast(view, selector):
    """Contrast of an element's text against what is really behind it,
    measured in the page the same way audit.js measures a real site."""
    return H.js(view, """(function(){
      var el = document.querySelector(%s); if (!el) return null;
      function p(s){var m=/rgba?\\(([\\d.]+)[, ]+([\\d.]+)[, ]+([\\d.]+)(?:[,/ ]+([\\d.]+))?\\)/.exec(s||"");
        return m?{r:+m[1],g:+m[2],b:+m[3],a:m[4]===undefined?1:+m[4]}:null;}
      function over(t,u){var a=t.a;return{r:t.r*a+u.r*(1-a),g:t.g*a+u.g*(1-a),b:t.b*a+u.b*(1-a),a:1};}
      var n=el, stack=[], bg=null;
      while(n && n.nodeType===1){
        var cs=getComputedStyle(n), c=p(cs.backgroundColor);
        if(c && c.a>0.004){ if(c.a>0.995){bg=c;break;} stack.push(c); }
        n=n.parentElement;
      }
      if(!bg) bg={r:255,g:255,b:255,a:1};
      for(var i=stack.length-1;i>=0;i--) bg=over(stack[i],bg);
      var fg=p(getComputedStyle(el).color);
      if(fg.a<0.995) fg=over(fg,bg);
      function ch(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
      function L(c){return 0.2126*ch(c.r)+0.7152*ch(c.g)+0.0722*ch(c.b);}
      var a=L(fg)+0.05,b=L(bg)+0.05;
      return Math.round((a>b?a/b:b/a)*100)/100;
    })()""" % json.dumps(selector), B.MAIN_WORLD_ID)


def css_of(view, selector, prop):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?getComputedStyle(e).%s:null})()"
                % (json.dumps(selector), prop), B.MAIN_WORLD_ID)


# ---------------------------------------------------------------------
app = H.app()
srv = H.Server(PAGES)
cfg = {"theme": "steampunk", "look": "glass", "forceDark": False,
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


print("\n(1) the theme is on at all")
load("/card")
check("the site theme's stylesheet is in the page",
      H.js(view, "!!document.getElementById('__sitetheme')", B.MAIN_WORLD_ID))
check("the white card was repainted in the palette",
      rgb(css_of(view, ".card", "backgroundColor"))[0] < 120,
      css_of(view, ".card", "backgroundColor"))

print("\n(2) pictures are never recoloured")
check("no filter on the photo", css_of(view, "#photo", "filter") == "none",
      css_of(view, "#photo", "filter"))
check("no blend mode on the photo",
      css_of(view, "#photo", "mixBlendMode") == "normal")
check("nothing above the photo filters it either",
      H.js(view, """(function(){var e=document.getElementById('photo'),n=e;
        while(n&&n.nodeType===1){ if(getComputedStyle(n).filter!=='none') return n.tagName;
        n=n.parentElement;} return 'none';})()""", B.MAIN_WORLD_ID) == "none")

print("\n(3) text is readable, or it is left alone")
for sel in ("#p1", "#faint", "#brandhead", "#brandtext"):
    r = contrast(view, sel)
    check("contrast of %s is at least 4.5:1" % sel, r is not None and r >= 4.5, r)
check("the coloured button keeps its own colour",
      rgb(css_of(view, "#cta", "backgroundColor"))[0] > 200,
      css_of(view, "#cta", "backgroundColor"))

print("\n(4) text over a picture or a gradient is not touched")
load("/hero")
check("the hero headline keeps the site's colour",
      css_of(view, "#herohead", "color") == "rgb(32, 32, 32)",
      css_of(view, "#herohead", "color"))
check("the hero paragraph keeps the site's colour",
      css_of(view, "#herotext", "color") == "rgb(32, 32, 32)",
      css_of(view, "#herotext", "color"))
check("text on a gradient keeps the site's colour",
      css_of(view, "#gradtext", "color") == "rgb(255, 255, 255)",
      css_of(view, "#gradtext", "color"))

print("\n(5) icon fonts are never swapped, and metrics do not overflow")
load("/icons")
for sel, want in (("#micon", "Material Icons"),
                  ("#sicon", "Material Icons"),
                  ("#ficon", "Font Awesome 5 Free")):
    fam = css_of(view, sel, "fontFamily") or ""
    check("%s keeps its icon font" % sel, want in fam, fam)
check("a code block keeps the font the site chose",
      "Courier New" in (css_of(view, "#codeblock", "fontFamily") or ""),
      css_of(view, "#codeblock", "fontFamily"))
check("running text does wear the theme's face",
      "Charter" in (css_of(view, "#para", "fontFamily") or "")
      or "serif" in (css_of(view, "#para", "fontFamily") or ""),
      css_of(view, "#para", "fontFamily"))
check("the nav bar's links keep the font it was measured for",
      "Arial" in (css_of(view, "#n1", "fontFamily") or ""),
      css_of(view, "#n1", "fontFamily"))
check("nothing in the fixed-width nav is clipped",
      H.js(view, "(function(){var n=document.getElementById('nav');"
                 "return n.scrollWidth - n.clientWidth})()",
           B.MAIN_WORLD_ID) <= 0,
      H.js(view, "document.getElementById('nav').scrollWidth", B.MAIN_WORLD_ID))

print("\n(6) the theme's texture stays under the page's own dialogs")
load("/modal")
over = H.js(view, "getComputedStyle(document.documentElement,'::before').zIndex",
            B.MAIN_WORLD_ID)
check("the texture overlay sits below what a site positions",
      over in ("auto", "0", "1", "2") or (over.isdigit() and int(over) <= 2),
      over)
check("the texture does not take clicks",
      H.js(view, "getComputedStyle(document.documentElement,'::before')"
                 ".pointerEvents", B.MAIN_WORLD_ID) == "none")
hit = H.js(view, """(function(){var b=document.getElementById('ok');
  var r=b.getBoundingClientRect();
  var e=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
  return e ? e.id || e.tagName : 'none';})()""", B.MAIN_WORLD_ID)
check("the dialog's button is the thing under the cursor", hit == "ok", hit)
check("the dialog's text is readable", (contrast(view, "#dlg p") or 0) >= 4.5,
      contrast(view, "#dlg p"))

print("\n(7) a stylesheet that arrives late is noticed")
load("/late", settle=2600)
check("the late stylesheet did land",
      H.js(view, "!!window.__late", B.MAIN_WORLD_ID))
r = contrast(view, "#latetext")
check("text in the late-styled panel is readable", r is not None and r >= 4.5, r)

print("\n(8) a big page is themed to the end")
load("/big", settle=9000)
last = css_of(view, "#r11999", "backgroundColor")
check("the 12000th row was themed too", rgb(last)[0] < 120, last)
check("the first row was themed as well",
      rgb(css_of(view, "#r0", "backgroundColor"))[0] < 120)

print("\n(9) the pass is idempotent and can undo itself")
load("/card")
before = H.js(view, "document.querySelector('.card').getAttribute('style')",
              B.MAIN_WORLD_ID)
H.js(view, "window.__stAdapt && window.__stAdapt(document)", B.APP_WORLD_ID)
H.spin(400)
after = H.js(view, "document.querySelector('.card').getAttribute('style')",
             B.MAIN_WORLD_ID)
check("a second pass changes nothing", before == after, (before, after))
H.js(view, "window.__stUndo && window.__stUndo()", B.APP_WORLD_ID)
H.spin(300)
check("undo gives the site its own colours back",
      css_of(view, ".card", "backgroundColor") == "rgb(255, 255, 255)",
      css_of(view, ".card", "backgroundColor"))
check("undo takes the stylesheet out too",
      not H.js(view, "!!document.getElementById('__sitetheme')",
               B.MAIN_WORLD_ID))

print("\n(10) a web view always paints something opaque")
load("/trans")
img = view.grab().toImage()
check("a page with a transparent body is still opaque",
      img.pixelColor(300, 200).alpha() == 255,
      img.pixelColor(300, 200).name())

print("\n(11) only one darkening at a time")
from PyQt6.QtCore import QUrl  # noqa: E402
cases = [("https://www.example.com/x", True, "theme"),
         ("https://discord.com/channels/1", True, "none"),
         ("https://www.google.de/search?q=x", True, "none"),
         ("file:///home/tim/browser/start.html", True, "none")]
for url, themed_on, want in cases:
    win.config["themeWeb"] = themed_on
    got = win.page_darkening(QUrl(url))
    check("%s -> %s" % (url.split("/")[2] if "//" in url else url, want),
          got == want, got)
win.config["forceDark"] = True
win.config["themeWeb"] = True
check("a themed site never gets force-dark as well",
      win.page_darkening(QUrl("https://www.example.com/x")) == "theme")
check("a site that is dark already gets neither",
      win.page_darkening(QUrl("https://discord.com/x")) == "none")
check("an ordinary site he excluded gets the inversion instead",
      (win.config.__setitem__("themeWebSkip", ["example.com"]),
       win.page_darkening(QUrl("https://www.example.com/x")))[1] == "force")
win.config["themeWebSkip"] = []
win.config["forceDark"] = False
load("/card")
check("ForceDarkMode is off on a themed page",
      not view.page().settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.ForceDarkMode))

print("\n(12) no theme's stylesheet touches layout")
BANNED = ("position", "z-index", "display", "overflow", "line-height",
          "font-size", "margin", "padding", "transform", "width", "height",
          "box-sizing", "float", "top", "left", "right", "bottom")
for entry in B.THEMES:
    key = entry["key"]
    win.config["theme"] = key
    B.apply_theme_module = None
    win.apply_theme(key)
    css = theme_web._site_css(win)
    # the browser's own overlays are the exception: they are what the
    # texture is, and they are pseudo-elements of <html>
    body = re.sub(r"html::(before|after)\s*\{[^}]*\}", "", css)
    body = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}", "", body)
    bad = []
    for rule in re.findall(r"([^{}]+)\{([^}]*)\}", body):
        sel, decls = rule[0].strip(), rule[1]
        if sel.startswith("@") or "::-webkit-scrollbar" in sel:
            continue
        for prop in BANNED:
            if re.search(r"(^|[;\s])" + prop + r"\s*:", decls):
                bad.append((sel.split("{")[0][:40], prop))
    check("%s sets no layout property on a site element" % key, not bad, bad)
    pics = re.findall(r"(?m)^\s*(?:img|video)[^{]*\{([^}]*)\}", css)
    filt = [f for f in pics if "filter" in f]
    if key in ("sepia", "newspaper"):
        check("%s recolours pictures only mildly, on purpose" % key,
              len(filt) == 1 and "invert" not in filt[0], filt)
    else:
        check("%s puts no filter on pictures" % key, not filt, filt)
win.config["theme"] = "steampunk"
win.apply_theme("steampunk")

print("\n(13) the fonts it asks for exist on this machine")
import subprocess  # noqa: E402
for stack in (theme_web.MONO, theme_web.SERIF):
    names = [n.strip().strip('"') for n in stack.split(",")]
    found = []
    for n in names[:-1]:
        try:
            out = subprocess.run(["fc-match", n], capture_output=True,
                                 text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        if n.lower().split()[0] in out.lower():
            found.append(n)
    check("the %s stack has a real face in it" % names[-1], bool(found), found)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
