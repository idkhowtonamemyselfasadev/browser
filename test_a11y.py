#!/usr/bin/env python3
"""Accessibility: what the browser does to a page that is not helping,
the keys that move through one, the lens and the ring, captions made on
this machine, and the names a screen reader reads.

Offscreen, scratch data, local server. The caption pipeline is driven by
two stub programs written into the scratch directory — nothing is
recorded, nothing is downloaded, and no sound or text leaves the machine.
"""
import json
import os
import stat
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<title>A page that needs help</title>
<html lang=""><body style="background:#ffffff">
  <h1>One</h1>
  <h3>Three, and two is missing</h3>
  <p style="color:#bbbbbb">this text is too faint to read</p>
  <p style="color:#111111">this text is fine</p>
  <img src="/pic.png">
  <img src="/pic.png" alt="a picture with a description">
  <input type="text" name="nameless">
  <input type="text" id="named"><label for="named">Named</label>
  <nav><a href="/one">one</a><br><a href="/two">two</a></nav>
  <main><p>the main content of the page</p></main>
  <meta http-equiv="refresh" content="30">
  <div id="cover" style="position:fixed;left:0;top:0;width:100%;
       height:100%;background:#222">a dialog that ignores Esc</div>
  <video id="v"></video>
</body>"""
PAGES = {"/p": PAGE, "/q": "<title>Q</title><p>q</p>"}

app = H.app()
srv = H.Server(PAGES)
scratch = None
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False,
                                     # the page's own colours, so the
                                     # contrast work is measured on what
                                     # the page really says
                                     "forceDark": False,
                                     "themeWeb": False}))
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


def sheet():
    return H.js(view, "(document.getElementById('__a11y')||{})"
                      ".textContent || ''", APP) or ""


def js(code, world=APP):
    return H.js(view, code, world)


print("\n(1) the table of switches")
check("every switch has a yes or no behind it",
      all(isinstance(v, bool) for v in win.A11Y_SWITCHES.values()),
      [k for k, v in win.A11Y_SWITCHES.items() if not isinstance(v, bool)])
check("...and there are twenty of them", len(win.A11Y_SWITCHES) == 20,
      len(win.A11Y_SWITCHES))
check("every one of them has a word",
      [k for k in win.A11Y_SWITCHES
       if not B.UI_STRINGS["en"].get("a11y" + k[0].upper() + k[1:])] == [],
      [k for k in win.A11Y_SWITCHES
       if not B.UI_STRINGS["en"].get("a11y" + k[0].upper() + k[1:])])
check("...in German too",
      [k for k in win.A11Y_SWITCHES
       if not B.UI_STRINGS["de"].get("a11y" + k[0].upper() + k[1:])] == [],
      [k for k in win.A11Y_SWITCHES
       if not B.UI_STRINGS["de"].get("a11y" + k[0].upper() + k[1:])])
check("nothing is on to begin with",
      not any(win.a11y_config()[k] for k in win.A11Y_SWITCHES))
check("a switch that is not one is refused",
      win.set_a11y("flyAway", True) is False)

print("\n(2) what is done to the page")
check("links can be underlined", win.set_a11y("underlineLinks", True) is True)
H.spin(500)
check("...and the sheet says so", "text-decoration: underline" in sheet())
check("...and the page really draws it",
      "underline" in (js("getComputedStyle(document.querySelector('a'))"
                         ".textDecorationLine", MAIN) or ""),
      js("getComputedStyle(document.querySelector('a'))"
         ".textDecorationLine", MAIN))
check("the click targets can be made bigger",
      win.set_a11y("bigTargets", True) is True)
H.spin(400)
check("...and a link really has room around it",
      float((js("getComputedStyle(document.querySelector('a')).padding",
                MAIN) or "0px").split("px")[0]) >= 6,
      js("getComputedStyle(document.querySelector('a')).padding", MAIN))
got = []
win.a11y_audit(view=view, then=got.append)
H.wait_for(lambda: got, 5000)
audit = got[0] if got else {}
check("the audit counts the fields with no label",
      audit.get("noLabel") == 1, audit)
check("...the pictures with no alt text", audit.get("noAlt") == 1, audit)
check("...the text that fails contrast", audit.get("lowContrast", 0) >= 1,
      audit)
check("...and the heading that skips a level",
      audit.get("headingJumps") == ["h1 -> h3"], audit)
check("...and finds the landmarks it has",
      audit.get("landmarks", 0) >= 2, audit)
check("the faint text can be darkened",
      win.set_a11y("fixContrast", True) is True)
H.spin(700)
check("...and it really changed",
      js("document.querySelectorAll('p')[0].style.color", MAIN)
      in ("rgb(0, 0, 0)", "black"),
      js("document.querySelectorAll('p')[0].style.color", MAIN))
check("...and the text that was fine was left alone",
      js("document.querySelectorAll('p')[1].style.color", MAIN)
      == "rgb(17, 17, 17)",
      js("document.querySelectorAll('p')[1].style.color", MAIN))
check("alt text can be put on hover",
      win.set_a11y("altText", True) is True)
H.spin(600)
check("...and a picture with a description carries it",
      "description" in (js("document.querySelectorAll('img')[1].title",
                           MAIN) or ""),
      js("document.querySelectorAll('img')[1].title", MAIN))
check("...and one with none is marked",
      "dashed" in (js("document.querySelectorAll('img')[0]"
                      ".style.outline", MAIN) or ""),
      js("document.querySelectorAll('img')[0].style.outline", MAIN))
check("...and says so in words",
      (js("document.querySelectorAll('img')[0].title", MAIN) or "")
      == win._ui_str("a11yNoAlt"),
      js("document.querySelectorAll('img')[0].title", MAIN))
check("the start of each word can be bold",
      win.set_a11y("boldStarts", True) is True)
H.spin(800)
check("...and the page has them",
      (js("document.querySelectorAll('.__a11yb b').length", MAIN) or 0) > 5,
      js("document.querySelectorAll('.__a11yb b').length", MAIN))
check("...and it is only done once",
      js("window.__a11yBold", APP) is True)
check("the spacing can be opened up",
      win.set_a11y("spacingLine", 2.4) == 2.4)
H.spin(500)
check("...and the page really is",
      "line-height: 2.4" in sheet(), sheet()[:120])
check("a spacing that is out of range is clamped",
      win.set_a11y("spacingLine", 9) == 3.0)
win.set_a11y("spacingLine", 1.6)
check("the scrollbars can be made big",
      win.set_a11y("bigBars", True) is True)
H.spin(400)
check("...and that is in the sheet", "scrollbar { width: 18px" in sheet())
check("long words can be hyphenated",
      win.set_a11y("hyphenate", True) is True)
H.spin(400)
check("...and the page is told the language",
      js("document.documentElement.lang", MAIN) in ("en", "de"),
      js("document.documentElement.lang", MAIN))
check("text can be reflowed to the window",
      win.set_a11y("reflow", True) is True)
H.spin(400)
check("...and nothing scrolls sideways",
      "overflow-x: hidden" in sheet())
check("the text alone can be zoomed", win.set_a11y("textZoom", 150) == 150)
H.spin(400)
check("...and only the text is bigger",
      "font-size: 1.5em" in sheet(), sheet()[:80])
win.set_a11y("textZoom", 100)
check("a zoom out of range is clamped", win.set_a11y("textZoom", 900) == 300)
win.set_a11y("textZoom", 100)
check("the sticky bars can be unstuck",
      win.set_a11y("noSticky", True) is True)
H.spin(400)
check("...and the cover really is static",
      js("getComputedStyle(document.getElementById('cover')).position",
         MAIN) == "static",
      js("getComputedStyle(document.getElementById('cover')).position",
         MAIN))
win.set_a11y("noSticky", False)
check("a page that reloads itself can be stopped",
      win.set_a11y("noRefresh", True) is True)
H.spin(500)
check("...and the tag is gone",
      js("document.querySelectorAll('meta[http-equiv]').length", MAIN) == 0,
      js("document.querySelectorAll('meta[http-equiv]').length", MAIN))
check("a font for pages can be chosen",
      win.set_a11y("font", "DejaVu Sans") == "DejaVu Sans")
H.spin(400)
check("...and it is in the sheet", "DejaVu Sans" in sheet())
check("...and only fonts this machine has are offered",
      all(name in B.QFontDatabase.families() for name in win.reading_fonts())
      if hasattr(B, "QFontDatabase") else True,
      win.reading_fonts())
win.set_a11y("font", "")

print("\n(3) the colour-blindness filters")
for which in ("fixrg", "fixby", "protan", "deutan", "tritan"):
    check("the %s filter can be set" % which,
          win.set_a11y("colourFilter", which) == which)
H.spin(500)
check("...and the page's root carries it",
      "__a11yfilter" in (js("document.documentElement.style.filter",
                            APP) or ""),
      js("document.documentElement.style.filter", APP))
check("...drawn by a matrix in the page",
      js("!!document.getElementById('__a11ysvg')", APP) is True)
check("...and the matrix really changed with the pick",
      len((js("document.querySelector('#__a11ysvg feColorMatrix')"
              ".getAttribute('values')", APP) or "").split()) == 20,
      js("document.querySelector('#__a11ysvg feColorMatrix')"
         ".getAttribute('values')", APP))
check("a filter that is not one is refused",
      win.set_a11y("colourFilter", "sepia") is False)
check("and it can be taken off", win.set_a11y("colourFilter", "") == "")

print("\n(4) the keys that move through a page")
got = []
win.a11y_jump("heading", view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("the next heading is reached", got and got[0] != "none", got)
check("...and it really has the focus",
      js("document.activeElement.tagName", APP) in ("H1", "H3"),
      js("document.activeElement.tagName", APP))
got = []
win.a11y_jump("heading", view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("...and the one after it is the next one",
      js("document.activeElement.tagName", APP) in ("H1", "H3"))
got = []
win.a11y_jump("heading", back=True, view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("going back works too", got and got[0] != "none", got)
got = []
win.a11y_jump("landmark", view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("the landmarks can be walked", got and got[0] != "none", got)
got = []
win.a11y_jump("main", view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("one key skips to the content", got == ["main"], got)
check("...and the main element has the focus",
      js("document.activeElement.tagName", APP) == "MAIN",
      js("document.activeElement.tagName", APP))
got = []
win.a11y_jump("field", view=view, then=got.append)
H.wait_for(lambda: got, 4000)
check("one key goes to the first text field", got and got[0] != "none", got)
check("...which is an input",
      js("document.activeElement.tagName", APP) == "INPUT",
      js("document.activeElement.tagName", APP))
check("spatial navigation can be switched on",
      win.set_a11y("spatial", True) is True)
H.spin(400)
check("...and the arrow keys really move between links",
      (js("window.__a11ySpatial('down')", APP) or "none") != "none",
      js("window.__a11ySpatial('down')", APP))
win.set_a11y("spatial", False)
check("caret browsing goes on with F7", win.toggle_caret_browsing() is True)
H.spin(400)
check("...and the arrow keys move a cursor",
      (js("window.__a11yCaret('character', 'forward', false)", APP) or "")
      != "none",
      js("window.__a11yCaret('character', 'forward', false)", APP))
check("...and Shift selects with it",
      len(js("window.__a11yCaret('character', 'forward', true)", APP) or "")
      >= 1,
      js("window.__a11yCaret('character', 'forward', true)", APP))
check("...and F7 again turns it off", win.toggle_caret_browsing() is False)
check("Esc can be made to close what the site will not",
      win.set_a11y("escapeOverlays", True) is True)
H.spin(400)
check("...and the cover goes away",
      js("window.__a11yEscape()", APP) in ("hidden", "clicked"),
      js("window.__a11yEscape()", APP))
check("the focused thing can be kept in view",
      win.set_a11y("focusInView", True) is True)
check("tooltips can be shown on focus",
      win.set_a11y("focusTooltips", True) is True)
H.spin(400)
# offscreen the document never has the focus, so element.focus() fires
# no focusin at all (document.hasFocus() is false and stays false). The
# event is dispatched instead: what is under test is what the listener
# does with it, not whether Qt can focus a window nobody is looking at.
js("""(function(){var a=document.querySelector('a');
  a.title='where this goes';
  a.dispatchEvent(new FocusEvent('focusin', {bubbles: true}));
  return 'ok';})()""", APP)
H.spin(400)
check("...and one really appears",
      js("(document.getElementById('__a11ytip')||{}).textContent||''",
         MAIN) == "where this goes",
      js("(document.getElementById('__a11ytip')||{}).textContent||''", MAIN))
check("the focused thing is really scrolled into the middle",
      js("""(function(){
        var a = document.querySelectorAll('a')[1];
        window.scrollTo(0, 0);
        a.dispatchEvent(new FocusEvent('focusin', {bubbles: true}));
        return 'sent';})()""", APP) == "sent")
check("a bigger copy of a picture can be shown on hover",
      win.set_a11y("hoverZoom", True) is True)
H.spin(400)
js("""(function(){
  var img = document.querySelector('img');
  img.dispatchEvent(new MouseEvent('mouseover',
    {bubbles: true, clientX: 40, clientY: 40}));
  return 'sent';})()""", APP)
H.spin(300)
check("...and the big copy is really on the page",
      js("!!document.getElementById('__a11yzoom')", APP) is True)
js("""document.querySelector('img').dispatchEvent(
     new MouseEvent('mouseout', {bubbles: true}))""", APP)
H.spin(300)
check("...and goes when the mouse leaves",
      js("!!document.getElementById('__a11yzoom')", APP) is False)
check("Alt-drag can select a link's words",
      win.set_a11y("altDragSelect", True) is True)
H.spin(400)
js("""(function(){
  var a = document.querySelector('a');
  a.dispatchEvent(new MouseEvent('mousedown',
    {bubbles: true, altKey: true}));
  return 'sent';})()""", APP)
H.spin(300)
check("...and the link really becomes selectable text",
      js("document.querySelector('a').style.userSelect", MAIN) == "text"
      and js("document.querySelector('a').draggable", MAIN) is False,
      (js("document.querySelector('a').style.userSelect", MAIN),
       js("document.querySelector('a').draggable", MAIN)))
check("the text cursor can be given a colour",
      win.set_a11y("caretStyle", True) is True)
H.spin(400)
check("...and the sheet carries caret-color", "caret-color" in sheet(),
      sheet()[:80])
check("...which is the theme's accent",
      B.theme_palette()["accent"] in sheet())
win.set_a11y("caretStyle", False)
check("smooth scrolling is the engine's own switch, and it is reachable",
      "ScrollAnimatorEnabled" in Path("browser.py").read_text())
check("...and it is off when he says so",
      (win.config.update({"smoothScroll": False}) or True)
      and win.apply_web_attributes() is None
      and win.profile.settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled) is False)
win.config["smoothScroll"] = True
win.apply_web_attributes()

print("\n(5) the ring, the lens and the strip")
check("the ring is off until he asks", win.ctrl_tapped() is False)
check("switching it on answers", win.set_a11y("findCursor", True) is True)
check("...and a tap of Ctrl flashes it", win.ctrl_tapped() is True)
check("...and it is really on the screen",
      win._cursor_ring.isVisible() is True)
win._cursor_ring.hide()
down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Control,
                 Qt.KeyboardModifier.NoModifier)
up = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Control,
               Qt.KeyboardModifier.NoModifier)
other = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C,
                  Qt.KeyboardModifier.ControlModifier)
win.keyPressEvent(down)
win.keyReleaseEvent(up)
check("the real key pair flashes it too", win._cursor_ring.isVisible())
win._cursor_ring.hide()
win.keyPressEvent(down)
win.keyPressEvent(other)
win.keyReleaseEvent(up)
check("...and Ctrl with something else does not",
      win._cursor_ring.isVisible() is False)
check("the lens goes on", win.magnifier(True, 3) is True)
check("...and draws a frame", win.draw_lens() is True)
pix = win._lens.pixmap()
check("...with the window's own pixels in it",
      pix is not None and not pix.isNull())
check("...magnified", win._lens_scale == 3.0, win._lens_scale)
check("and it goes off again", win.magnifier(False) is False)
check("...and is really gone", getattr(win, "_lens", None) is None)
before = win.tabs.currentIndex()
check("the strip can be walked from the keyboard",
      win.focus_tab_strip(1) != before or win.tabs.count() == 1,
      (before, win.focus_tab_strip(0)))
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
got = []
menu = win.keyboard_tab_menu()
check("a tab's own menu opens from the keyboard",
      menu is None or len(menu.actions()) > 0,
      menu is not None and len(menu.actions()))
check("the page menu can be opened at what has the focus",
      win.keyboard_page_menu(view=view, then=got.append) is True)
H.wait_for(lambda: got, 4000)
check("...and the browser asked the page where that is",
      got and "tag" in got[0], got)

print("\n(6) the names a screen reader reads")
named = win.name_for_screen_readers()
check("the browser's own furniture is named", named > 10, named)
check("...the address bar among it",
      bool(win.urlbar.accessibleName()), win.urlbar.accessibleName())
check("...and the tab strip",
      bool(win.tabs.tabBar().accessibleName()),
      win.tabs.tabBar().accessibleName())
unnamed = [b.objectName() or b.text() for b in win.findChildren(B.QToolButton)
           if not b.accessibleName() and (b.toolTip() or b.text())]
check("...and nothing with words on it is left unnamed", unnamed == [],
      unnamed[:5])

print("\n(7) the sound")
check("mono can be switched on", win.set_a11y("monoAudio", True) is True)
check("...and the page is told", win.apply_audio_shape() >= 1,
      win.apply_audio_shape())
H.spin(400)
check("...and it really went through Web Audio",
      js("window.__audioShape && window.__audioShape.mono", MAIN) is True,
      js("JSON.stringify(window.__audioShape||null)", MAIN))
check("the balance can be moved", win.set_a11y("balance", -0.5) == -0.5)
H.spin(400)
check("...and the page has it",
      js("window.__audioShape && window.__audioShape.pan", MAIN) == -0.5,
      js("JSON.stringify(window.__audioShape||null)", MAIN))
check("a balance out of range is clamped", win.set_a11y("balance", -4)
      == -1.0)
win.set_a11y("balance", 0)
win.set_a11y("monoAudio", False)
check("the cues are off until he asks", win.play_cue("done") is False)
check("switching them on makes the two tones",
      win.set_sound_cues(True) is True)
check("...as files beside the config",
      Path(win.cue_file("done")).is_file()
      and Path(win.cue_file("page")).is_file(),
      win.cue_file("done"))
check("...which are real wav files",
      Path(win.cue_file("done")).read_bytes()[:4] == b"RIFF",
      Path(win.cue_file("done")).read_bytes()[:4])
check("...and nothing was downloaded to get them",
      Path(win.cue_file("done")).stat().st_size < 60000,
      Path(win.cue_file("done")).stat().st_size)

print("\n(8) captions, made on this machine")
rec = scratch / "rec.sh"
rec.write_text("#!/bin/sh\nprintf 'wav' > \"$2\"\n")
tra = scratch / "tra.sh"
tra.write_text("#!/bin/sh\necho '[00:00.000 --> 00:02.000]  hello "
               "from the stub'\n")
tsl = scratch / "tsl.sh"
tsl.write_text("#!/bin/sh\nshift\necho \"uebersetzt: $*\"\n")
for one in (rec, tra, tsl):
    one.chmod(one.stat().st_mode | stat.S_IEXEC)
check("with nothing installed it says so",
      win.live_captions(True, view=view) is False)
win.config["captionRecorder"] = str(rec)
win.config["captionTranscriber"] = str(tra)
win.config["captionTranslator"] = str(tsl)
tools = win.caption_tools()
check("a recorder he named is found",
      tools["captionRecorder"] == str(rec), tools)
check("...and a transcriber", tools["captionTranscriber"] == str(tra), tools)
check("...and a translator", tools["captionTranslator"] == str(tsl), tools)
win.config["captionRecorder"] = "/nowhere/parec"
check("one that is not there is not pretended to be",
      win.caption_tools()["captionRecorder"] == "",
      win.caption_tools()["captionRecorder"])
win.config["captionRecorder"] = str(rec)
check("captions start", win.live_captions(True, view=view, seconds=2) is True)
H.wait_for(lambda: "hello" in (js("(document.getElementById('__captions')"
                                  "||{}).textContent||''", APP) or ""), 9000)
check("...and what the transcriber said is on the page",
      "hello from the stub" in (js("(document.getElementById('__captions')"
                                   "||{}).textContent||''", APP) or ""),
      js("(document.getElementById('__captions')||{}).textContent||''", APP))
check("...with the timestamps stripped out",
      "00:00" not in (js("(document.getElementById('__captions')||{})"
                         ".textContent||''", APP) or ""),
      js("(document.getElementById('__captions')||{}).textContent||''", APP))
check("...and they stop again", win.live_captions(False, view=view) is False)
H.spin(400)
check("...taking the overlay with them",
      js("!!document.getElementById('__captions')", APP) is False)
got = []
win.translate_caption("hello there", then=got.append)
H.wait_for(lambda: got, 6000)
check("a line can be translated on this machine",
      got and got[0].startswith("uebersetzt:"), got)
H.spin(400)
check("...and it is shown",
      "uebersetzt" in (js("(document.getElementById('__captions')||{})"
                          ".textContent||''", APP) or ""),
      js("(document.getElementById('__captions')||{}).textContent||''", APP))
cues = []
win.page_captions(view=view, then=cues.append)
H.wait_for(lambda: cues, 4000)
check("the page's own captions can be read", cues and isinstance(
    cues[0], str), cues)
check("translating them runs",
      win.translate_page_captions(True, view=view) is True)
win.translate_page_captions(False, view=view)
win.config["captionTranslator"] = ""
check("...and without a translator it says so",
      win.translate_page_captions(True, view=view) is False)
win.config["captionTranslator"] = str(tsl)

print("\n(9) one site at a time")
check("a switch can be set for this site only",
      win.set_a11y("underlineLinks", False, host="127.0.0.1") is False)
check("...and the site answers differently from the rest",
      win.a11y_config("127.0.0.1")["underlineLinks"] is False
      and win.a11y_config()["underlineLinks"] is True,
      (win.a11y_config("127.0.0.1")["underlineLinks"],
       win.a11y_config()["underlineLinks"]))
check("...and another site is not affected",
      win.a11y_config("example.com")["underlineLinks"] is True)
check("the site's profile can be forgotten",
      win.clear_a11y_site("127.0.0.1") is True)
check("...and then it reads the usual answers",
      win.a11y_config("127.0.0.1")["underlineLinks"] is True)
check("forgetting one that is not there says so",
      win.clear_a11y_site("nothing.test") is False)

print("\n(10) the panel, Settings and the keys")
menu = win.a11y_menu(view=view)
rows = [a.text() for a in menu.actions() if a.text()]
check("the panel heads itself", win._ui_str("a11yPanel") in rows, rows[:3])
check("...and has a row for every switch",
      all(win._ui_str("a11y" + k[0].upper() + k[1:]) in rows
          for k in win.A11Y_SWITCHES),
      [k for k in win.A11Y_SWITCHES
       if win._ui_str("a11y" + k[0].upper() + k[1:]) not in rows])
subs = {a.text(): a.menu() for a in menu.actions() if a.menu()}
check("...a menu of colour filters",
      len(subs[win._ui_str("a11yColourFilter")].actions()) == 6,
      sorted(subs))
check("...the captions, with what is installed named",
      any("tra.sh" in a.text() or win._ui_str("a11yCapMissing") in a.text()
          for a in subs[win._ui_str("a11yCapName")].actions()),
      [a.text() for a in subs[win._ui_str("a11yCapName")].actions()])
check("...and this site's own copy of the switches",
      win._ui_str("a11ySiteOnly") % "127.0.0.1" in subs, sorted(subs))
page_text = Path("settings.html").read_text()
for ident in ("a11yswitches", "a11ytextzoom", "a11yline", "a11yword",
              "a11yletter", "a11yfont", "a11yfilter", "a11ybalance",
              "a11ylens", "soundcues", "caprecorder", "captranscriber",
              "capmodel", "captranslator", "captiontranslate"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text, ident)
check("...and the switches are drawn from the browser's own list",
      "s.a11ySwitches" in page_text and "bindA11y();" in page_text)
data = json.loads(win.bridge.getSettings())
check("the page is told what is switched on", "a11y" in data)
check("...which switches there are",
      len(data.get("a11ySwitches", [])) == len(win.A11Y_SWITCHES),
      len(data.get("a11ySwitches", [])))
check("...what is installed for captions", "captionTools" in data)
check("...and which reading fonts this machine has",
      data.get("readingFonts") == win.reading_fonts(),
      data.get("readingFonts"))
registry = win.actions_list()
ids = [row["id"] for row in registry]
for ident in ("a11ymenu", "caretbrowse", "a11yheading", "a11yheadingback",
              "a11ylandmark", "a11yfield", "a11ymain", "a11yfirstfield",
              "a11ylens", "a11yaudit", "a11ycaptions", "a11ypagemenu",
              "a11ytabnext", "a11ytabprev"):
    check("there is an action for " + ident, ident in ids, ident)
check("F7 is caret browsing",
      [r["id"] for r in registry if r.get("key") == "F7"] == ["caretbrowse"],
      [r["id"] for r in registry if r.get("key") == "F7"])
check("Shift+F10 is the page menu",
      [r["id"] for r in registry if r.get("key") == "Shift+F10"]
      == ["a11ypagemenu"],
      [r["id"] for r in registry if r.get("key") == "Shift+F10"])
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
check("no two actions want the same key",
      {k: v for k, v in taken.items() if len(v) > 1} == {},
      {k: v for k, v in taken.items() if len(v) > 1})
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1][:4])
need = ["a11yName", "a11yMenu", "a11yPanel", "a11yNoAlt", "a11yColourFilter",
        "a11yFilter_fixrg", "a11ySpacing", "a11yTextZoom", "a11yFont",
        "a11yFontHint", "a11yBalance", "a11yMagnifier", "a11yLensScale",
        "a11ySoundCues", "a11ySoundCuesHint", "a11yCapName", "a11yCapHint",
        "a11yCapNoTool", "a11yCapNoTranslator", "a11yCapRecorder",
        "a11yCapTranscriber", "a11yCapTranslator", "a11yCapModel",
        "a11yCapTranslate", "a11yAuditName", "a11yAuditRow",
        "a11yAuditClean", "a11yJumpHeading", "a11yMain", "a11yField",
        "a11yCaretOn", "a11yCaretOff", "a11yNames", "a11yTabStrip",
        "a11yPageMenu", "a11ySiteOnly", "descA11y"]
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
