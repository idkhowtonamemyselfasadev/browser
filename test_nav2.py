#!/usr/bin/env python3
"""Getting around a page, part two: what a page is made of, what to do
with a selection, the switches that take the page's own cleverness out
of the way, a note stuck to an address, a code in a picture, and the
things another program should open.

Offscreen, scratch data, local server. Nothing goes online: the archive
address is built and never fetched, and the QR code is drawn by qr.py
and read back by qr.py.
"""
import base64
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
import qr  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<title>A page to get around</title><body>
  <p>plain text with https://example.com/in-text in the middle of it</p>
  <a href="/one">the first link</a>
  <a href="/two">the second link</a>
  <a href="/three">the third link</a>
  <img src="/pic.png" width="20" height="10" alt="a picture">
  <img id="code" src="/code.png">
  <iframe src="/frame" width="0" height="0"></iframe>
  <main><h2>The heading</h2><form><input name="q"></form></main>
  <meta http-equiv="refresh" content="20">
  <div style="height:2000px"></div>
</body>"""
PAGES = {"/p": PAGE, "/one": "<title>One</title><p>one</p>",
         "/two": "<title>Two</title><p>two</p>",
         "/three": "<title>Three</title><p>three</p>",
         "/frame": "<title>A frame</title><p>in a frame</p>",
         "/other": "<title>Other</title><p>nothing to find here</p>"}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1100, 800)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
APP = B.APP_WORLD_ID
scratch = B.CONFIG_FILE.parent
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(700)


def js(code, world=APP):
    return H.js(view, code, world)


def ask(call, *args, **kw):
    wait = kw.pop("wait", 6000)
    got = []
    kw["then"] = got.append
    call(*args, **kw)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


print("\n(1) the switches that get the page out of the way")
check("there are six of them", len(win.NAV_SWITCHES) == 6,
      list(win.NAV_SWITCHES))
check("each has a word",
      [k for k in win.NAV_SWITCHES
       if not B.UI_STRINGS["en"].get("nav" + k[0].upper() + k[1:])] == [],
      [k for k in win.NAV_SWITCHES
       if not B.UI_STRINGS["en"].get("nav" + k[0].upper() + k[1:])])
check("...in German too",
      [k for k in win.NAV_SWITCHES
       if not B.UI_STRINGS["de"].get("nav" + k[0].upper() + k[1:])] == [],
      [k for k in win.NAV_SWITCHES
       if not B.UI_STRINGS["de"].get("nav" + k[0].upper() + k[1:])])
check("a switch that is not one is refused",
      win.set_nav("teleport", True) is False)
check("plain addresses can be made clickable",
      win.set_nav("clickableUrls", True) is True)
H.spin(600)
check("...and the one in the text became a link",
      (js("document.querySelectorAll('a.__navurl').length", MAIN) or 0) == 1,
      js("document.querySelectorAll('a.__navurl').length", MAIN))
check("...pointing where it says",
      js("document.querySelector('a.__navurl').href", MAIN)
      == "https://example.com/in-text",
      js("document.querySelector('a.__navurl').href", MAIN))
check("the scroll can be kept from the site",
      win.set_nav("noScrollHijack", True) is True)
H.spin(400)
check("...and the sheet says so",
      "scroll-behavior: auto" in (js("(document.getElementById('__nav')"
                                     "||{}).textContent||''", APP) or ""),
      js("(document.getElementById('__nav')||{}).textContent||''", APP))
check("the keys can be kept from the site",
      win.set_nav("noKeyGrab", True) is True)
check("the middle-button scroll can go on",
      win.set_nav("autoScroll", True) is True)
H.spin(300)
check("...and nothing is rolling yet",
      js("window.__navAutoScroll(false)", APP) == "off")
check("a box over links can go on", win.set_nav("boxLinks", True) is True)
check("one site can answer differently",
      win.set_nav("noKeyGrab", False, host="127.0.0.1") is False)
check("...and it does",
      win.nav_config("127.0.0.1")["noKeyGrab"] is False
      and win.nav_config()["noKeyGrab"] is True,
      (win.nav_config("127.0.0.1")["noKeyGrab"],
       win.nav_config()["noKeyGrab"]))
for key in ("clickableUrls", "noScrollHijack", "noKeyGrab", "autoScroll",
            "boxLinks"):
    win.set_nav(key, False)

print("\n(2) what is in the selection")
js("""(function(){
  var r = document.createRange();
  r.setStartBefore(document.querySelectorAll('a')[0]);
  r.setEndAfter(document.querySelectorAll('a')[2]);
  var s = getSelection(); s.removeAllRanges(); s.addRange(r);
  return 'selected';})()""", MAIN)
rows = ask(win.selection_links, view=view)
check("the links in it are listed", len(rows or []) == 3, rows)
check("...with their words", any("first" in (r.get("text") or "")
                                for r in (rows or [])), rows)
before = win.tabs.count()
opened = ask(win.open_selection_links, view=view)
check("they can all be opened at once", len(opened or []) == 3, opened)
check("...as tabs", win.tabs.count() == before + 3,
      (before, win.tabs.count()))
for _ in range(3):
    win.close_tab(win.tabs.count() - 1)
js("""(function(){
  var p = document.querySelector('p');
  var r = document.createRange();
  r.selectNodeContents(p);
  var s = getSelection(); s.removeAllRanges(); s.addRange(r);
  return 'selected';})()""", MAIN)
found = ask(win.selection_url, view=view)
check("an address in the selected text is found",
      found == "https://example.com/in-text", found)
js("getSelection().removeAllRanges()", MAIN)
nothing = ask(win.selection_url, view=view)
check("...and with nothing selected there is none", nothing == "", nothing)

print("\n(3) the pictures, the frames and the shape")
pics = ask(win.gallery_images, view=view)
check("the pictures are listed", len(pics or []) >= 1, pics)
check("...with their size and their alt text",
      any(p.get("alt") == "a picture" for p in (pics or [])), pics)
gallery = win.image_gallery(view=view)
H.spin(500)
check("the gallery is a menu of them",
      len(gallery.actions()) >= 1, len(gallery.actions()))
frames = ask(win.page_frames, view=view)
check("the frames are listed", len(frames or []) == 1, frames)
check("...with their address",
      "/frame" in str((frames or [{}])[0].get("url", "")), frames)
menu = win.frames_menu(view=view)
H.spin(500)
check("...and each one can be opened in a tab",
      any("/frame" in a.text() for a in menu.actions()),
      [a.text() for a in menu.actions()])
check("a frame can be reloaded", win.reload_frame("/frame", view=view) is True)
rows = ask(win.structure_overlay, True, view=view)
check("the page's shape is drawn", (rows or 0) >= 2, rows)
H.spin(300)
check("...as a list in the page",
      js("!!document.getElementById('__navstructure')", APP) is True)
ask(win.structure_overlay, False, view=view)
H.spin(200)
check("...and it goes away again",
      js("!!document.getElementById('__navstructure')", APP) is False)
shown = ask(win.view_image, "next", view=view)
check("one picture can be shown full size",
      str(shown or "").startswith("http"), shown)
H.spin(300)
check("...over the page",
      js("!!document.getElementById('__navviewer')", APP) is True)
ask(win.view_image, "off", view=view)
H.spin(200)
check("...and closed", js("!!document.getElementById('__navviewer')",
                          APP) is False)

print("\n(4) finding things")
marks = ask(win.find_marks, "link", view=view)
check("every match gets a mark", (marks or 0) >= 3, marks)
H.spin(300)
check("...on a rail beside the scrollbar",
      js("!!document.getElementById('__navmarks')", APP) is True)
check("...one tick each",
      (js("document.getElementById('__navmarks').children.length", APP)
       or 0) >= 3,
      js("document.getElementById('__navmarks').children.length", APP))
whole = ask(win.find_marks, "lin", view=view, whole=True)
check("whole-word mode finds fewer", (whole or 0) == 0, whole)
regex = ask(win.find_marks, "th(e|ird)", view=view, regex=True)
check("a regular expression works", (regex or 0) >= 1, regex)
bad = ask(win.find_marks, "(unclosed", view=view, regex=True)
check("...and one that does not compile says so", bad == -1, bad)
link = ask(win.find_link, "second", view=view)
check("a link can be found by its words",
      str(link or "").endswith("/two"), link)
check("...and it has the focus",
      js("document.activeElement.textContent", APP) == "the second link",
      js("document.activeElement.textContent", APP))
missing = ask(win.find_link, "nowhere", view=view)
check("...and one that is not there says none", missing == "none", missing)
other = win.new_tab(url=None)
H.load(other, srv.url("/other"))
H.spin(600)
rows = ask(win.find_in_all_tabs, "the third link", wait=8000)
check("every tab is searched", len(rows or []) >= 1, rows)
check("...and the tab with it is named",
      any("get around" in (r.get("title") or "") for r in (rows or [])),
      rows)
check("...with how many times it is in there",
      all(r.get("count", 0) >= 1 for r in (rows or [])), rows)
rows = ask(win.find_in_all_tabs, "zzzznothing", wait=8000)
check("...and nothing is nothing", rows == [], rows)
all_menu = win.all_tabs_find_menu("the third link")
H.spin(800)
check("the matches are a menu", len(all_menu.actions()) >= 1,
      [a.text() for a in all_menu.actions()])
win.close_tab(win.tabs.indexOf(other))
win.tabs.setCurrentIndex(win.tabs.indexOf(view))

print("\n(5) addresses rewritten before they load")
check("a rule can be set",
      win.set_url_rewrites(["reddit.com -> old.reddit.com"])
      == [("reddit.com", "old.reddit.com")])
check("...and it rewrites",
      win.rewrite_url(QUrl("https://reddit.com/r/x")).toString()
      == "https://old.reddit.com/r/x",
      win.rewrite_url(QUrl("https://reddit.com/r/x")).toString())
check("...and leaves everything else alone",
      win.rewrite_url(QUrl("https://example.com/")).toString()
      == "https://example.com/")
check("a rule as a pair works too",
      win.set_url_rewrites([["a.test", "b.test"]])
      == [("a.test", "b.test")])
check("a rule that would not make an address is ignored",
      win.set_url_rewrites(["https:// -> nonsense "])
      and win.rewrite_url(QUrl("https://x.test/")).toString()
      == "https://x.test/",
      win.rewrite_url(QUrl("https://x.test/")).toString())
win.set_url_rewrites([])
check("...and with no rules nothing is touched",
      win.rewrite_url(QUrl("https://reddit.com/")).toString()
      == "https://reddit.com/")

print("\n(6) a note stuck to a page")
check("a note can be written", win.page_note(text="remember this one")
      == "remember this one")
H.spin(400)
check("...and it is on the page",
      js("(document.getElementById('__pagenote')||{}).textContent||''",
         APP) == "remember this one",
      js("(document.getElementById('__pagenote')||{}).textContent||''", APP))
check("...and read back", win.page_note() == "remember this one")
check("...against the address without its query",
      win.page_note(url=srv.url("/p") + "?x=1") == "remember this one",
      win.page_note(url=srv.url("/p") + "?x=1"))
check("another page has none", win.page_note(url=srv.url("/one")) == "")
check("it can be taken away", win.page_note(text="") == "")
H.spin(300)
check("...and the box goes with it",
      js("!!document.getElementById('__pagenote')", APP) is False)

print("\n(7) the mobile version, and a site's cache")
check("the mobile version is one switch", win.view_as_mobile(view=view)
      is True)
H.spin(700)
check("...and the tab really is phone-wide", view.width() <= 400,
      view.width())
check("...and the site is told it is a phone",
      "iPhone" in str(win.agent_for("127.0.0.1")),
      win.agent_for("127.0.0.1"))
check("and back again", win.view_as_mobile(view=view) is False)
H.spin(500)
check("...with the agent put back", win.agent_for("127.0.0.1") == "",
      win.agent_for("127.0.0.1"))
check("one site's cache and workers can be dropped",
      win.clear_site_cache(view=view) is True)
H.spin(700)

print("\n(8) a page that did not load")
found = win.error_details(url="https://nothing.test/x",
                          reason="Name or service not known")
check("a name that would not resolve is named that",
      found["kind"] == "dns", found)
check("...in words", "looked up" in found["words"], found["words"])
check("a refused connection is named too",
      win.error_details(url="x", reason="Connection refused")["kind"]
      == "refused")
check("...and a timeout", win.error_details(
    url="x", reason="Operation timed out")["kind"] == "timeout")
check("...and a certificate", win.error_details(
    url="x", reason="SSL certificate problem")["kind"] == "cert")
check("...and nothing at all is said to be nothing at all",
      win.error_details(url="x", reason="")["kind"] == "unknown")
check("the archived copy is an address, not a fetch",
      found["archive"].startswith("https://web.archive.org/web/2/"),
      found["archive"])
html_out = win.error_page_html("https://nothing.test/x", found["words"],
                               details=found)
check("the error page carries the archive offer",
      "web.archive.org" in html_out)
check("...and the reason", "looked up" in html_out)
check("...and a key to try again", "Enter" in html_out)
check("the archive address is built for any page",
      win.archive_url(srv.url("/p")).endswith(srv.url("/p")))
check("...and not for a file", win.archive_url("file:///tmp/x") == "")
check("trying again when the network is back can be armed",
      win.retry_when_online(view=view, url=srv.url("/p")) is True)
check("...and not for something that is not a web address",
      win.retry_when_online(view=view, url="file:///tmp/x") is False)
timer = getattr(win, "_retry_timer", None)
if timer is not None:
    timer.stop()

print("\n(9) a code in a picture")
grid = qr.matrix("https://example.com/from-a-picture")
scale, quiet = 4, 2
size = len(grid)
shot = QImage((size + 2 * quiet) * scale, (size + 2 * quiet) * scale,
              QImage.Format.Format_RGB32)
shot.fill(QColor("white"))
for r in range(size):
    for c in range(size):
        if grid[r][c]:
            for y in range((r + quiet) * scale, (r + quiet + 1) * scale):
                for x in range((c + quiet) * scale, (c + quiet + 1) * scale):
                    shot.setPixelColor(x, y, QColor("black"))
shot.save(str(scratch / "code.png"), "PNG")
raw = (scratch / "code.png").read_bytes()
data = "data:image/png;base64," + base64.b64encode(raw).decode()
got = []
win._read_qr_data(data, got.append)
check("a QR code in a picture is read here",
      got == ["https://example.com/from-a-picture"], got)
plain = QImage(60, 60, QImage.Format.Format_RGB32)
plain.fill(QColor("white"))
out = []
win._read_qr_image_object(plain, out.append)
check("...and a picture with no code says so", out == [""], out)
check("the decoder is the encoder's own tables, run backwards",
      qr.read_matrix(qr.matrix("round trip")) == "round trip")
check("...for an address", qr.read_matrix(qr.matrix(
    "https://example.com/a?b=c#d")) == "https://example.com/a?b=c#d")
check("...for a long one",
      qr.read_matrix(qr.matrix("x" * 200)) == "x" * 200)
check("...and out of pixels at any module size",
      all(qr.read_pixels(
          (lambda g, s, q: (lambda x, y: (
              0 <= y // s - q < len(g) and 0 <= x // s - q < len(g)
              and bool(g[y // s - q][x // s - q]))))(
                  qr.matrix("pixels"), step, 2),
          (len(qr.matrix("pixels")) + 4) * step,
          (len(qr.matrix("pixels")) + 4) * step) == "pixels"
          for step in (1, 3, 6)))
check("a grid that is not a code reads as nothing",
      qr.read_matrix([[0] * 21 for _ in range(21)]) == "")

print("\n(10) another program's address")
check("what could open a scheme is measured, not assumed",
      isinstance(win.scheme_choices("mailto"), list),
      win.scheme_choices("mailto"))
check("an unknown scheme offers xdg-open or nothing",
      all(Path(one).is_file() for one in win.scheme_choices("spotify")),
      win.scheme_choices("spotify"))
check("an answer can be remembered for one site",
      win.set_scheme_app("discord", "/usr/bin/true", "example.com")
      == "/usr/bin/true")
check("...and it is what that site gets",
      win.scheme_app("discord", "example.com") == "/usr/bin/true")
check("...while another site still has none",
      win.scheme_app("discord", "other.test") == "")
check("an answer can be remembered for the scheme itself",
      win.set_scheme_app("steam", "/usr/bin/true") == "/usr/bin/true")
check("...and every site gets it",
      win.scheme_app("steam", "anywhere.test") == "/usr/bin/true")
check("an address really goes to it",
      win.open_with_app("discord://invite/abc", host="example.com",
                        ask=False) == "/usr/bin/true")
check("an http address is never handed over",
      win.open_with_app("https://example.com/", ask=False) is False)
check("a scheme nobody has claimed goes to the desktop's own opener",
      str(win.open_with_app("nonsense9://x", ask=False)).endswith(
          "xdg-open"),
      win.open_with_app("nonsense9://x", ask=False))
was = win.scheme_choices
win.scheme_choices = lambda scheme: []
check("...and with nothing installed at all it says so",
      win.open_with_app("nonsense8://x", ask=False) is False)
win.scheme_choices = was
rows = [a.text() for a in win.scheme_menu().actions()]
check("what has been answered is listed", len(rows) == 2, rows)
check("...and can be forgotten",
      win.set_scheme_app("discord", "", "example.com") == ""
      and win.scheme_app("discord", "example.com") == "")
win.set_scheme_app("steam", "")

print("\n(11) a look at a link, and the other half")
win.config["linkPreview"] = True
holder = win.link_preview_window(srv.url("/one"))
check("the linked page opens in a small window", holder is not None)
check("...which is a view of its own",
      getattr(win, "_preview_view", None) is not None)
check("...in a jar that writes nothing down",
      win._preview_view.page().profile().isOffTheRecord() is True)
H.spin(600)
check("...and it can be thrown away", win.close_link_preview() is True)
check("...and then there is none", getattr(win, "_preview", None) is None)
check("a preview of something that is not a page is refused",
      win.link_preview_window("file:///tmp/x") is None)
check("a link can be opened in the side pane",
      win.open_in_pane(srv.url("/two")) is True)
H.spin(500)
check("...and not a file", win.open_in_pane("file:///tmp/x") is False)

print("\n(12) the menu, Settings and the keys")
menu = win.nav_menu(view=view)
rows = [a.text() for a in menu.actions() if a.text()]
check("the menu offers what the page is made of",
      win._ui_str("navInfoName") in rows, rows[:4])
check("...the pictures", win._ui_str("navImages") in rows, rows[:6])
check("...the frames", win._ui_str("navFrames") in rows, rows[:8])
check("...the selection tools",
      win._ui_str("navOpenAllLinks") in rows, rows)
check("...every switch",
      all(win._ui_str("nav" + k[0].upper() + k[1:]) in rows
          for k in win.NAV_SWITCHES),
      [k for k in win.NAV_SWITCHES
       if win._ui_str("nav" + k[0].upper() + k[1:]) not in rows])
check("...and this site's own copy of the four worth having per site",
      win._ui_str("a11ySiteOnly") % "127.0.0.1"
      in [a.text() for a in menu.actions() if a.menu()],
      [a.text() for a in menu.actions() if a.menu()])
page_text = Path("settings.html").read_text()
for ident in ("navswitches", "linkpreview", "autoretry", "urlrewrites",
              "externalplayer", "schemeapps"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text, ident)
check("...and the switches come from the browser's own list",
      "s.navSwitches" in page_text and "bindNav();" in page_text)
data = json.loads(win.bridge.getSettings())
check("the page is told what is switched on", "nav" in data)
check("...which switches there are",
      len(data.get("navSwitches", [])) == len(win.NAV_SWITCHES))
check("...the rewrite rules", "urlRewrites" in data)
check("...and what answers which scheme", "schemeApps" in data)
registry = win.actions_list()
ids = [row["id"] for row in registry]
for ident in ("navmenu", "navfindall", "navmobile", "navnote",
              "navstructure", "navimages", "navinfo", "navframes",
              "navarchive", "navother", "navplayer", "navcache",
              "navprintsel", "navselection", "navselall", "navschemes"):
    check("there is an action for " + ident, ident in ids, ident)
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
check("no two actions want the same key",
      {k: v for k, v in taken.items() if len(v) > 1} == {},
      {k: v for k, v in taken.items() if len(v) > 1})
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1][:4])
need = ["navMenu", "navInfoName", "navImages", "navFrames", "navNoFrames",
        "navFrameBlocked", "navOpenSelection", "navOpenAllLinks",
        "navNoLinks", "navNoUrlThere", "navFindAll", "navNoMatches",
        "navFindLink", "navStructure", "navViewImage", "navMobileOn",
        "navMobileOff", "navRewriteName", "navRewriteHint", "navNoteName",
        "navNoteAsk", "navBackOnline", "navArchiveName", "navArchiveAsk",
        "navErr_dns", "navErr_refused", "navErr_timeout", "navErr_cert",
        "navOtherBrowser", "navPlayer", "navPlayerName", "navClearCache",
        "navPrintSelection", "navQrName", "navQrRead", "navQrNone",
        "navAppName", "navAppAsk", "navNoApp", "navHandedTo",
        "navPreviewKeep", "navPane", "linkPreviewName", "descNav",
        "navErrProxy"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
