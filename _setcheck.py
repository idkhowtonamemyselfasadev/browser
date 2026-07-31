#!/usr/bin/env python3
"""The Settings page after the redesign: does everything still work?

Search and its per-section counts, the mark down the left of a
matching row, the keyboard on the search box, "All settings", the
Toolbar's three lists and the card that goes away with its list, the
theme filter, and the error handling. Offscreen, scratch data only.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

SHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    print(("  ok   " if cond else "  FAIL ") + name
          + ("  <%s>" % (detail,) if detail != "" else ""))
    if not cond:
        FAILS += 1


app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1400, 940)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


win.open_settings()
spin(3000)
page = win._panes["settings"].view.page()


def js(code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


print("\n(1) the page came up whole")
o = json.loads(js("""JSON.stringify({
  rail: document.querySelectorAll('#sidebar button').length,
  active: [...document.querySelectorAll('.content section')]
            .filter(s=>s.classList.contains('active')).length,
  panels: document.querySelectorAll('.panel').length,
  blank: document.getElementById('content').className,
  fail: document.getElementById('drawfail').className,
  searchInTop: !!document.querySelector('#topbar #navfilter'),
  contentClass: document.getElementById('content').className})"""))
check("the rail has a way into every section", o["rail"] > 10, o["rail"])
check("exactly one section is showing", o["active"] == 1)
check("the sections are built out of cards", o["panels"] >= 25, o["panels"])
check("nothing failed to draw", o["fail"] == "", repr(o["fail"]))
check("the content is not blanked", "blank" not in o["blank"])
check("the search box is in the top bar, not the rail", o["searchInTop"])

print("\n(2) the cards are painted by the palette, not by a literal")
o = json.loads(js("""(function(){
  var p=document.querySelector('.panel');
  var cs=getComputedStyle(p), body=getComputedStyle(document.body);
  return JSON.stringify({panel: cs.backgroundColor,
                         page: body.backgroundColor,
                         title: getComputedStyle(
                           document.querySelector('.panel h2.sub')).fontSize});
})()"""))
pal = B.theme_palette("mocha")
check("a card sits on the surface token", o["panel"].replace(" ", "")
      in ("rgb(13,13,18)", "rgb(13, 13, 18)".replace(" ", "")), o["panel"])
check("the page is the bg token", o["page"].replace(" ", "") == "rgb(0,0,0)",
      o["page"])
check("a card title outranks a row label (14px)",
      float(o["title"].replace("px", "")) > 14, o["title"])

print("\n(3) search: counts on the rail, a mark down the left")
o = json.loads(js("""(function(){
  var box=document.getElementById('navfilter');
  box.value='cookies'; box.oninput({target:box});
  var btns=[...document.querySelectorAll('#sidebar button')];
  return JSON.stringify({
    shown: btns.filter(b=>b.style.display!=='none').map(b=>b.textContent.trim()),
    hits: btns.filter(b=>b.dataset.hits).map(b=>[b.textContent.trim(), b.dataset.hits]),
    marked: document.querySelectorAll('.hit').length,
    dimmed: document.querySelectorAll('.dim').length,
    tips: document.getElementById('searchtips').className,
    showall: document.getElementById('showall').className,
    blank: document.getElementById('content').className});
})()"""))
check("only the sections that carry the word stay listed",
      len(o["shown"]) > 0 and len(o["shown"]) < 12, o["shown"])
check("the rail says how many settings matched, per section",
      len(o["hits"]) > 0, o["hits"])
check("the matching rows are marked", o["marked"] > 0, o["marked"])
check("the rest step back", o["dimmed"] > 0, o["dimmed"])
check("the keyboard line is up", "on" in o["tips"])
check("and All settings is offered", "on" in o["showall"])

if SHOT:
    SHOT.parent.mkdir(parents=True, exist_ok=True)
    spin(400)
    win.grab().save(str(SHOT))
    print("  search screenshot ->", SHOT)

print("\n(4) the keyboard on the search box")
# a needle that leaves more than one section standing: with only one
# match down-arrow correctly wraps back onto it, which proves nothing
o = json.loads(js("""(function(){
  var box=document.getElementById('navfilter');
  box.value='e'; box.oninput({target:box});
  var was=window._cat;
  box.onkeydown({key:'ArrowDown', preventDefault:function(){}, target:box});
  var moved=window._cat;
  box.onkeydown({key:'Escape', preventDefault:function(){},
                 stopPropagation:function(){}, target:box});
  return JSON.stringify({was:was, moved:moved, value:box.value,
    seen: [...document.querySelectorAll('#sidebar button')]
            .filter(b=>b.style.display!=='none').length,
    marked: document.querySelectorAll('.hit').length});
})()"""))
check("down arrow walks the sections that matched",
      o["seen"] > 1 and o["was"] != o["moved"],
      "%d sections listed, %s -> %s" % (o["seen"], o["was"], o["moved"]))
check("Esc empties the box rather than closing the page", o["value"] == "")
check("and the marks come off with it", o["marked"] == 0)

print("\n(5) nothing matches: the box survives what it emptied")
o = json.loads(js("""(function(){
  var box=document.getElementById('navfilter');
  box.value='zzzznothing'; box.oninput({target:box});
  var vis=getComputedStyle(document.getElementById('navfilter')).display;
  var r=JSON.stringify({
    content: getComputedStyle(document.getElementById('content')).display,
    boxstill: vis,
    nomatch: document.getElementById('nomatch').className});
  document.getElementById('showall').click();
  return r;
})()"""))
check("the pane steps aside", o["content"] == "none", o["content"])
check("but the search box is still on screen to fix the typo",
      o["boxstill"] != "none", o["boxstill"])
check("and it says so", "on" in o["nomatch"])
o = json.loads(js("""JSON.stringify({
  content: getComputedStyle(document.getElementById('content')).display,
  active: [...document.querySelectorAll('.content section')]
            .filter(s=>s.classList.contains('active')).length})"""))
check("All settings brings the pane back", o["content"] != "none")
check("with a section showing", o["active"] == 1)

print("\n(6) the Toolbar's three lists, and the card that goes with one")
o = json.loads(js("""JSON.stringify({
  bar: document.querySelectorAll('#tbbar .wrow').length,
  hid: document.querySelectorAll('#tbhid .wrow').length,
  els: [...document.querySelectorAll('#tbelse .wrow')].map(r=>r.dataset.tb),
  hidcard: document.getElementById('tbhidpanel').style.display,
  arrows: document.querySelectorAll('#tbbar .wrow button').length,
  reset: !!document.getElementById('tbreset'),
  incards: !!document.querySelector('.panel #tbbar')})"""))
check("the toolbar list is drawn", o["bar"] > 5, o["bar"])
check("and it is inside a card", o["incards"])
check("elsewhere-in-the-chrome is its own list", o["els"] == ["star", "tabgroups"],
      o["els"])
check("the arrows are there", o["arrows"] > 0, o["arrows"])
check("an empty Not-shown list takes its whole card away",
      (o["hid"] == 0) == (o["hidcard"] == "none"),
      "%d rows, card display %r" % (o["hid"], o["hidcard"]))

print("\n(7) the theme picker and its own filter")
o = json.loads(js("""(function(){
  var b=document.getElementById('themefilter');
  b.value='gruvbox'; b.oninput({target:b});
  var shown=[...document.querySelectorAll('.tcard')]
              .filter(c=>c.style.display!=='none').map(c=>c.dataset.key);
  b.value='zzzz'; b.oninput({target:b});
  var none=document.getElementById('themenomatch').classList.contains('on');
  b.value=''; b.oninput({target:b});
  return JSON.stringify({total: document.querySelectorAll('.tcard').length,
                         gruv: shown, none: none});
})()"""))
check("every theme has a card", o["total"] == len(B.THEMES),
      "%d of %d" % (o["total"], len(B.THEMES)))
check("the theme filter still filters", sorted(o["gruv"]) ==
      ["gruvbox", "gruvbox-hard", "gruvbox-light", "gruvbox-light-hard"],
      o["gruv"])
check("and says when nothing matches", o["none"])

print("\n(8) a part that will not draw still says so")
o = json.loads(js("""(function(){
  drawFailed('themes','boom');
  var r=JSON.stringify({cls: document.getElementById('drawfail').className,
    txt: document.getElementById('drawfail').textContent.slice(0,60)});
  document.getElementById('drawfail').className='';
  return r;
})()"""))
check("the banner comes up", "on" in o["cls"])
check("and names the part", "themes" in o["txt"], o["txt"])

print("\n%d checks failed" % FAILS)
app.quit()
sys.exit(1 if FAILS else 0)
