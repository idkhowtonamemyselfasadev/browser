#!/usr/bin/env python3
"""The page tools and the navigation helpers.

Local pages that are built to be awkward in the way real sites are: one
that blocks copying, one with a fixed bar over the content, one with a
next-page link, one with headings, one that plays something. Each tool
is run on the page it is for and the page is asked what changed."""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


LOCKED = """<!doctype html><title>Locked</title>
<style>body{user-select:none}</style>
<p id=t>You may not copy this.</p>
<script>
document.addEventListener('copy', function (e) { e.preventDefault(); }, true);
document.oncontextmenu = function () { return false; };
</script>"""

STICKY = """<!doctype html><title>Sticky</title>
<style>#bar{position:fixed;top:0;left:0;right:0;height:80px;background:#246}
#side{position:sticky;top:0;height:40px;background:#642}
body{margin:0;height:3000px}</style>
<div id=bar>a fixed bar</div><div id=side>a sticky one</div>
<p id=p>content under them</p>"""

PAGED = """<!doctype html><title>Paged</title>
<link rel=next href="/page2">
<a href="/prev" rel=prev>Previous</a>
<h1 id=h1>First heading</h1><p style="height:900px">...</p>
<h2 id=h2>Second heading</h2><p style="height:900px">...</p>
<h3 id=h3>Third heading</h3>"""

MIXED = """<!doctype html><title>Mixed</title>
<details id=d><summary>more</summary><p>hidden text</p></details>
<input type=password id=pw value=secret>
<video id=v loop autoplay muted><source src="data:video/mp4;base64,"></video>
<a id=visited href="/a">a link</a>
<p id=words>Some words worth linking to.</p>"""

FEEDS = """<!doctype html><title>Feeds</title>
<link rel=alternate type="application/rss+xml" title="News feed" href="/rss.xml">
<a href="/blog/feed">subscribe</a>"""

PAGES = {"/locked": LOCKED, "/sticky": STICKY, "/paged": PAGED,
         "/feeds": FEEDS,
         "/page2": "<title>Page two</title>two", "/prev": "<title>Prev</title>p",
         "/mixed": MIXED, "/a": "<title>A</title>a",
         "/deep/b/c": "<title>Deep</title><p>deep page</p>",
         "/deep/b/": "<title>Up one</title><p>up one</p>",
         "/deep/": "<title>Up two</title><p>up two</p>"}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1100, 800)
win.show()
H.spin(400)
view = win.new_tab(url=None)


def tool(name, **args):
    box = {}
    loop_done = []
    win.page_tool(name, view=view, then=lambda r: box.setdefault("v", r),
                  **args)
    H.wait_for(lambda: "v" in box, 4000)
    H.spin(200)
    return box.get("v")


def js(code):
    return H.js(view, code, B.MAIN_WORLD_ID)


print("\n(1) a site that blocks copying")
H.load(view, srv.url("/locked"))
check("the page says text may not be selected",
      js("getComputedStyle(document.getElementById('t')).userSelect")
      in ("none", "-webkit-none"),
      js("getComputedStyle(document.getElementById('t')).userSelect"))
check("the tool runs", tool("unlock") == "unlocked")
check("text may be selected now",
      js("getComputedStyle(document.getElementById('t')).userSelect") == "text",
      js("getComputedStyle(document.getElementById('t')).userSelect"))
check("and it does not run twice", tool("unlock") == "already")

print("\n(2) bars that will not move")
H.load(view, srv.url("/sticky"))
check("the bar is fixed to start with",
      js("getComputedStyle(document.getElementById('bar')).position") == "fixed")
got = tool("unstick")
check("the tool says how many it unpinned",
      isinstance(got, str) and got.startswith("on:"), got)
check("the fixed bar is in the page now",
      js("getComputedStyle(document.getElementById('bar')).position") == "static",
      js("getComputedStyle(document.getElementById('bar')).position"))
check("so is the sticky one",
      js("getComputedStyle(document.getElementById('side')).position") == "static")
check("and it can be switched off again", tool("unstick") == "off")
check("which puts the bar back",
      js("getComputedStyle(document.getElementById('bar')).position") == "fixed")

print("\n(3) the page's own next and previous")
H.load(view, srv.url("/paged"))
H.spin(300)
win.go_page(False)
H.wait_for(lambda: view.url().toString().endswith("/page2"), 4000)
check("next goes to the declared next page",
      view.url().toString().endswith("/page2"), view.url().toString())
H.load(view, srv.url("/paged"))
H.spin(300)
win.go_page(True)
H.wait_for(lambda: view.url().toString().endswith("/prev"), 4000)
check("previous follows the previous link",
      view.url().toString().endswith("/prev"), view.url().toString())

print("\n(4) jumping between headings")
H.load(view, srv.url("/paged"))
H.spin(400)
js("window.scrollTo(0,0)")
tool("heading", back=False)
H.spin(600)
y1 = js("window.scrollY")
check("the first jump lands on the first heading", y1 >= 0 and y1 < 200,
      y1)
tool("heading", back=False)
H.spin(600)
y2 = js("window.scrollY")
check("the second goes further", y2 > y1, (y1, y2))
tool("heading", back=True)
H.spin(600)
check("and back goes back up", js("window.scrollY") < y2, js("window.scrollY"))

print("\n(5) up a level")
H.load(view, srv.url("/deep/b/c"))
H.spin(200)
win.go_up_level()
H.wait_for(lambda: view.url().path() == "/deep/b", 4000)
check("one step up the path", view.url().path() in ("/deep/b", "/deep/b/"),
      view.url().path())
win.go_up_level()
H.wait_for(lambda: view.url().path() in ("/deep", "/deep/"), 4000)
check("and another", view.url().path() in ("/deep", "/deep/"),
      view.url().path())

print("\n(6) the odds and ends")
H.load(view, srv.url("/mixed"))
H.spin(300)
check("expand opens a closed details block",
      (tool("expand") or 0) >= 1 and js("document.getElementById('d').open"))
check("show-password turns the field into text",
      (tool("showpw") or 0) >= 1
      and js("document.getElementById('pw').type") == "text")
check("...and back again",
      (tool("showpw") or 0) >= 1
      and js("document.getElementById('pw').type") == "password")
check("visited links get a colour of their own", tool("visited") == "on")
check("which can be taken off again", tool("visited") == "off")
check("the scroll-to-top button appears", tool("totop") == "on")
check("it is there", js("!!document.getElementById('__totop')"))
check("and goes away", tool("totop") == "off")
check("edit mode makes the page editable",
      tool("edit") == "on" and js("document.body.isContentEditable"))
check("and off again",
      tool("edit") == "off" and not js("document.body.isContentEditable"))
got = tool("stopmedia")
check("stopping everything moving says so",
      isinstance(got, str) and got.startswith("stopped:"), got)
check("and a stylesheet holds the animations",
      js("!!document.getElementById('__nomotion')"))
tool("stopmedia")
check("freezing the page says so", tool("freeze") == "frozen")
check("and it is only done once", tool("freeze") == "already")
check("thawing says so", tool("thaw") == "thawed")

print("\n(7) a link to the selected words")
H.load(view, srv.url("/mixed"))
H.spin(300)
js("""(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('words'));
 var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);})()""")
H.spin(200)
win.copy_text_link()
H.spin(600)
got = QGuiApplication.clipboard().text()
check("the clipboard holds a text-fragment link",
      "#:~:text=" in got and "worth%20linking" in got, got)

print("\n(8) redirect wrappers")
cases = [
    ("https://www.google.com/url?q=https%3A%2F%2Fmodrinth.com%2Fmods&sa=t",
     "https://modrinth.com/mods"),
    ("https://www.youtube.com/redirect?q=https%3A%2F%2Fexample.com%2Fa",
     "https://example.com/a"),
    ("https://discord.com/external?url=https%3A%2F%2Fexample.org%2Fx",
     "https://example.org/x"),
    ("https://modrinth.com/mods", "https://modrinth.com/mods"),
]
for raw, want in cases:
    got = win.unwrap_redirect(raw)
    check("%s -> %s" % (raw.split("?")[0], want), got == want, got)

print("\n(9) the history menus (held Back, middle-clicked Back)")
H.load(view, srv.url("/a"))
H.load(view, srv.url("/mixed"))
H.load(view, srv.url("/paged"))
H.spin(300)
menu = win.history_menu(forward=False)
check("back has a list", menu is not None and len(menu.actions()) >= 2,
      len(menu.actions()) if menu else None)
check("forward has none here", win.history_menu(forward=True) is None)
view.back()
H.spin(900)
check("and forward has one after going back",
      win.history_menu(forward=True) is not None)

print("\n(10) the feeds a page offers")
H.load(view, srv.url("/feeds"))
H.spin(300)
box = {}
win.page_tool("feeds", view=view, then=lambda r: box.setdefault("v", r))
H.wait_for(lambda: "v" in box, 4000)
feeds = json.loads(box.get("v") or "[]")
check("the declared feed is found",
      any("/rss.xml" in f[1] for f in feeds), feeds)
check("...with its title", any(f[0] == "News feed" for f in feeds), feeds)
check("a link that looks like a feed is found too",
      any("/blog/feed" in f[1] for f in feeds), feeds)
box = {}
H.load(view, srv.url("/mixed"))
H.spin(200)
win.page_tool("feeds", view=view, then=lambda r: box.setdefault("v", r))
H.wait_for(lambda: "v" in box, 4000)
check("a page without feeds says nothing",
      json.loads(box.get("v") or "[]") == [], box.get("v"))

print("\n(10b) the things the back button and the link menu do")
H.load(view, srv.url("/a"))
H.load(view, srv.url("/mixed"))
H.load(view, srv.url("/paged"))
H.spin(400)
before = len([1 for _, v in win._real_tabs()])
win._nav_button_middle("back")
H.wait_for(lambda: len([1 for _, v in win._real_tabs()]) > before, 4000)
check("middle-clicking Back opens that step in a new tab",
      len([1 for _, v in win._real_tabs()]) == before + 1,
      (before, len([1 for _, v in win._real_tabs()])))
check("and this tab stayed where it was",
      view.url().toString().endswith("/paged"), view.url().toString())
# a tab of its own, so "the first page of this site" is a page this
# test knows about rather than whatever ran before it
fresh = win.new_tab(url=None)
H.load(fresh, srv.url("/a"))
H.load(fresh, srv.url("/mixed"))
H.load(fresh, srv.url("/paged"))
H.spin(300)
win.tabs.setCurrentIndex(win.tabs.indexOf(fresh))
H.spin(200)
got = win.go_site_start()
H.wait_for(lambda: fresh.url().toString().endswith("/a"), 4000)
check("back-to-the-first-page goes to the first page of this site",
      got is not None and fresh.url().toString().endswith("/a"),
      fresh.url().toString())
win.hard_reload()
H.spin(900)
check("a hard reload still has the page",
      fresh.url().toString().endswith("/a"), fresh.url().toString())
win.tabs.setCurrentIndex(win.tabs.indexOf(view))

print("\n(11) the link under the mouse")
win.show_hovered_link("https://www.google.com/url?q=https%3A%2F%2Fmodrinth.com%2F")
check("the line is shown", win._hoverlbl.isVisible())
check("with the wrapper unwrapped",
      win._hoverlbl.text() == "https://modrinth.com/", win._hoverlbl.text())
win.show_hovered_link("")
check("and goes away when nothing is hovered",
      not win._hoverlbl.isVisible())

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
