#!/usr/bin/env python3
"""Reading: reader mode, the outline, the word count, link hints, the
accessibility switches, highlights kept per page, and reading aloud."""
import json
import os
import shutil
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


BODY = " ".join(["Dies ist ein langer Absatz mit vielen Woertern, damit der "
                 "Lesemodus ihn als Artikel erkennt."] * 6)
ARTICLE = ("<!doctype html><title>Article</title>"
           "<style>body{margin:0}</style>"
           "<nav id=nav><a href='#x'>menu one</a> <a href='#y'>menu two</a></nav>"
           "<aside id=side>a sidebar full of other things</aside>"
           "<article id=art><h1>The headline</h1>"
           "<p id=p1>" + BODY + "</p>"
           "<h2>A section</h2><p id=p2>" + BODY + "</p>"
           "<h3>Deeper</h3><p id=p3>" + BODY + "</p>"
           "<p><a id=inside href='/b'>a link in the article</a></p></article>"
           "<footer id=foot>the footer</footer>")
PLAIN = "<!doctype html><title>Plain</title><p>short</p>"

app = H.app()
srv = H.Server({"/a": ARTICLE, "/b": "<title>B</title><p>b</p>",
                "/plain": PLAIN})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 800)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))
H.spin(400)


def tool(name, **args):
    box = {}
    win.read_tool(name, view=view, then=lambda r: box.setdefault("v", r),
                  **args)
    H.wait_for(lambda: "v" in box, 4000)
    H.spin(150)
    return box.get("v")


def js(code):
    return H.js(view, code, B.MAIN_WORLD_ID)


print("\n(1) reader mode")
got = tool("reader", css=win.reader_css())
check("it finds the article", got == "on", got)
check("the article is marked",
      js("document.getElementById('art').className").find("__readerbody") >= 0,
      js("document.getElementById('art').className"))
check("the menu is hidden",
      js("getComputedStyle(document.getElementById('nav')).display") == "none")
check("so is the sidebar",
      js("getComputedStyle(document.getElementById('side')).display") == "none")
check("and the footer",
      js("getComputedStyle(document.getElementById('foot')).display") == "none")
check("the article itself is not",
      js("getComputedStyle(document.getElementById('art')).display") != "none")
check("the page is in the theme's colours",
      js("getComputedStyle(document.body).backgroundColor")
      != "rgba(0, 0, 0, 0)",
      js("getComputedStyle(document.body).backgroundColor"))
check("a link inside it still works",
      js("!!document.getElementById('inside')"))
check("and it all comes back", tool("reader", css=win.reader_css()) == "off")
check("the menu is there again",
      js("getComputedStyle(document.getElementById('nav')).display") != "none")
H.load(view, srv.url("/plain"))
H.spin(300)
check("a page with no article says so",
      tool("reader", css=win.reader_css()) == "no article")

print("\n(2) the outline")
H.load(view, srv.url("/a"))
H.spin(300)
heads = json.loads(tool("outline") or "[]")
check("every heading is listed", len(heads) == 3, heads)
check("with its level", [h["level"] for h in heads] == [1, 2, 3], heads)
check("and an id to jump to", all(h["id"] for h in heads), heads)

print("\n(3) the word count")
got = json.loads(tool("wordcount") or "{}")
check("it counts the words", got.get("words", 0) > 100, got)
check("and says how long that takes", got.get("minutes", 0) >= 1, got)
js("""(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('p1'));
 var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);})()""")
H.spin(200)
sel = json.loads(tool("wordcount") or "{}")
check("a selection is counted on its own",
      sel.get("selection") is True and sel["words"] < got["words"], sel)
js("window.getSelection().removeAllRanges()")

print("\n(4) link hints")
n = tool("hints")
check("every link gets a label", isinstance(n, int) and n >= 3, n)
check("the labels are on the page",
      js("document.querySelectorAll('#__hints span').length") == n,
      js("document.querySelectorAll('#__hints span').length"))
first = js("document.querySelector('#__hints span').textContent")
check("they are letters", first and first.isalpha(), first)
tool("hintpress", key="z" if first != "z" else "q")
H.spin(200)
check("a letter that matches nothing takes the labels away",
      js("!!document.getElementById('__hints')") is False
      or js("document.querySelectorAll('#__hints span').length") == 0,
      js("!!document.getElementById('__hints')"))
n = tool("hints")
tool("hintpress", key=first)
H.spin(600)
check("and the right letter follows the link",
      not js("!!document.getElementById('__hints')"))

print("\n(5) the reading switches")
H.load(view, srv.url("/a"))
H.spin(300)
for what in ("contrast", "readable", "spacing", "motion", "cursor", "focus",
             "stillgifs"):
    win.access_switch(what, view=view)
    H.spin(120)
    check("%s goes on" % what,
          js("!!document.getElementById('__a11y_%s')" % what))
check("high contrast really is high contrast",
      js("getComputedStyle(document.body).color") == "rgb(255, 255, 255)",
      js("getComputedStyle(document.body).color"))
for what in ("contrast", "readable", "spacing", "motion", "cursor", "focus",
             "stillgifs"):
    win.access_switch(what, view=view)
    H.spin(120)
check("and they all come off again",
      js("document.querySelectorAll('[id^=__a11y_]').length") == 0,
      js("document.querySelectorAll('[id^=__a11y_]').length"))

print("\n(6) a smallest text size for one site")
win.site_min_font("127.0.0.1", 18)
H.load(view, srv.url("/a"))
H.spin(400)
check("the site has its own minimum",
      view.page().settings().fontSize(
          B.QWebEngineSettings.FontSize.MinimumFontSize) == 18,
      view.page().settings().fontSize(
          B.QWebEngineSettings.FontSize.MinimumFontSize))
check("and it is remembered", win.site_min_font("127.0.0.1") == 18)
win.site_min_font("127.0.0.1", 0)
H.load(view, srv.url("/a"))
H.spin(400)
check("taking it off puts the browser's own back",
      view.page().settings().fontSize(
          B.QWebEngineSettings.FontSize.MinimumFontSize) == 0)

print("\n(7) highlights that stay")
H.load(view, srv.url("/a"))
H.spin(300)
js("""(function(){var r=document.createRange();
 var p=document.getElementById('p2'), t=p.firstChild;
 r.setStart(t, 0); r.setEnd(t, 12);
 var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);})()""")
H.spin(200)
win.add_highlight(view=view)
H.spin(700)
check("the words are marked",
      js("document.querySelectorAll('mark.__hl').length") >= 1,
      js("document.querySelectorAll('mark.__hl').length"))
saved = win.highlights_for(view.url())
check("and written down for this address", len(saved) == 1, saved)
H.load(view, srv.url("/a"))
H.spin(1200)
check("they come back on the next visit",
      js("document.querySelectorAll('mark.__hl').length") >= 1,
      js("document.querySelectorAll('mark.__hl').length"))
win.clear_highlights(view=view)
H.spin(900)
check("and can be cleared", not win.highlights_for(view.url()))

print("\n(8) reading aloud")
if shutil.which("spd-say"):
    H.load(view, srv.url("/a"))
    H.spin(300)
    check("it starts", win.read_aloud(view=view))
    H.spin(600)
    check("and stops", win.stop_aloud())
else:
    check("without a speech program it says so politely",
          win.read_aloud(view=view) is False)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
