#!/usr/bin/env python3
"""The looks — the shape of the browser, checked offscreen against
scratch data.

What matters here: the classic look is the browser that was always
there, byte for byte; the furniture a look builds goes up and comes
down without a restart; the pins are the start page's quick links and
they survive being written down; every look works in every palette
because no look owns a colour; and the circle start page really is a
ring with the caret still in the search box."""
import base64
import inspect
import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCRATCH = Path(tempfile.mkdtemp(prefix="lookstest-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import (QBuffer, QIODevice, QTimer,  # noqa: E402
                          QEventLoop)
from PyQt6.QtGui import QColor, QPixmap  # noqa: E402

HERE = Path(__file__).resolve().parent
B.CONFIG_FILE = SCRATCH / "config.json"
B.HISTORY_FILE = SCRATCH / "history.json"
B.DOWNLOADS_FILE = SCRATCH / "downloads.json"
B.HOSTS_FILE = SCRATCH / "hosts.json"
B.BOOKMARKS_FILE = SCRATCH / "bookmarks.json"
SCRATCH.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))

FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    print(("  ok   " if cond else "  FAIL ") + name
          + ("  <%s>" % detail if detail else ""))
    if not cond:
        FAILS += 1


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


# ---------------------------------------------------------------- (1)
print("\n(1) the five looks")
check("classic is the default", B.DEFAULT_LOOK == "classic")
check("there are five of them, classic first",
      B.look_names() == ["classic", "taskbar", "macos", "circle", "glass"],
      ", ".join(B.look_names()))
check("every look names itself and says what it does",
      all(B.UI_STRINGS["en"].get(entry["name"])
          and B.UI_STRINGS["en"].get(entry["note"]) for entry in B.LOOKS))
check("and says it in German too, which is the language it starts in",
      all(B.UI_STRINGS["de"].get(entry["name"])
          and B.UI_STRINGS["de"].get(entry["note"]) for entry in B.LOOKS))
for junk in ("nonsense", "", None, ["macos"], {"key": "macos"}, 7):
    B._select_look(junk)
    if B.active_look() != "classic":
        check("a look that is not a look falls back to classic", False,
              repr(junk))
        break
else:
    check("a look that is not a look falls back to classic", True)
B._select_look("classic")

# ---------------------------------------------------------------- (2)
print("\n(2) classic is the browser that was always there")
check("classic adds nothing at all to the sheet",
      B.look_style("classic") == "", repr(B.look_style("classic")[:40]))
check("and adds nothing in any palette either",
      all(B.look_style("classic", t["key"]) == "" for t in B.THEMES))

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()
spin(300)

classic_sheet = app.styleSheet()
check("the window's sheet is exactly the theme's sheet",
      classic_sheet == B.theme_style(), "%d chars" % len(classic_sheet))
root = win.centralWidget().layout()
check("the window still has its three rows and no fourth",
      root.count() == 3, root.count())
check("no taskbar and no dock have been built",
      win.taskbar is None and win.dock is None)

# ---------------------------------------------------------------- (3)
print("\n(3) the furniture goes up and comes down")
win.apply_look("taskbar")
spin(200)
check("the taskbar look builds a taskbar and shows it",
      win.taskbar is not None and win.taskbar.isVisible())
check("and it is the fourth row of the window, under the page",
      root.count() == 4 and root.itemAt(3).widget() is win.taskbar)
check("the dock is not built for a look that has no dock",
      win.dock is None)
check("the taskbar asks for no width, so the window stays resizable",
      win.taskbar.minimumSizeHint().width() == 0)

win.apply_look("macos")
spin(200)
check("the dock look builds a dock and shows it",
      win.dock is not None and win.dock.isVisible())
check("and puts the taskbar away", not win.taskbar.isVisible())
check("the dock floats over the page, not in the window's rows",
      win.dock.parentWidget() is win.tabs and root.count() == 4)
check("the dock look brings a sheet of its own",
      "border-radius" in B.look_style("macos"))

win.apply_look("circle")
spin(200)
check("the circle look is the start page's business, not the chrome's",
      not win.taskbar.isVisible() and not win.dock.isVisible()
      and B.look_style("circle") == "")

win.apply_look("classic")
spin(200)
check("classic puts everything away again",
      not win.taskbar.isVisible() and not win.dock.isVisible())
check("and the sheet is byte for byte the one we started with",
      app.styleSheet() == classic_sheet)

# the page's right-click menu is part of "classic is unchanged": a look
# with nowhere to put a pin does not offer to make one
source = inspect.getsource(B.WebView.contextMenuEvent)
check("the page menu only offers pinning where there is furniture for it",
      "look_is_pinned()" in source)
check("which is the taskbar and the dock, and not classic or circle",
      [look for look in B.look_names() if B.look_is_pinned(look)]
      == ["taskbar", "macos"])
for look, words in (("taskbar", ("pinTaskbar", "unpinTaskbar")),
                    ("macos", ("pinDock", "unpinDock")),
                    ("classic", ("pinLinks", "unpinLinks"))):
    B._select_look(look)
    if win.pin_labels() != words:
        check("pinning is named after the furniture it goes on", False,
              "%s: %s" % (look, win.pin_labels()))
        break
else:
    check("pinning is named after the furniture it goes on", True)
B._select_look("classic")

# ---------------------------------------------------------------- (4)
print("\n(4) the pins are the start page's quick links")
check("a browser that has never run setup shows the same two the start "
      "page would", [p["name"] for p in win.pins()] == ["GitHub", "YouTube"],
      ", ".join(p["name"] for p in win.pins()))
check("pinning a page says it worked",
      win.add_pin("https://example.com/news", "Example News"))
check("and pinning it twice does not put it on twice",
      not win.add_pin("https://www.example.com/news/", "Again"))
check("the pin is there, under the name it was given",
      [p["name"] for p in win.pins()][-1] == "Example News")
check("is_pinned finds it however the address is spelled",
      win.is_pinned("https://www.example.com/news/"))
check("a javascript: address is never pinned",
      not win.add_pin("javascript:alert(1)", "Bad"))
check("and neither is a file on the disk",
      not win.add_pin("file:///etc/passwd", "Worse"))

saved = json.loads(B.CONFIG_FILE.read_text())
stored = saved.get("startPage", {}).get("quicklinks")
check("the list is written where the start page keeps its own",
      isinstance(stored, str), type(stored).__name__)
check("and it is the same JSON string shape the page mirrors",
      isinstance(json.loads(stored or "[]"), list)
      and json.loads(stored)[-1]["url"] == "https://example.com/news")

check("unpinning takes it off", win.remove_pin("https://example.com/news"))
check("and unpinning what is not there says so",
      not win.remove_pin("https://example.com/news"))
win.add_pin("https://example.com/news", "Example News")

# a hand-edited file must never take the browser down with it
for junk in ('nonsense', '{"not": "a list"}', '[1, 2, 3]', ''):
    win.config["startPage"] = {"quicklinks": junk}
    check("a config holding %r reads back as no pins" % junk[:14],
          win.pins() == [], repr(win.pins()[:1]))
win.config["startPage"] = {"quicklinks": json.dumps(
    [{"name": "Kept", "url": "https://example.com/"},
     {"url": "javascript:alert(1)"},
     {"name": "Dup", "url": "https://www.example.com"}])}
check("and one with rubbish in it keeps only what is really a pin",
      [p["name"] for p in win.pins()] == ["Kept"],
      ", ".join(p["name"] for p in win.pins()))
win.set_pins([{"name": "Example", "url": "https://example.com/", "icon": ""}])

# ---------------------------------------------------------------- (6)
print("\n(6) Frutiger Aero is a palette like any other")
check("it is in the catalogue", "aero" in B.THEME_INDEX)
aero = B.THEME_INDEX["aero"]
check("on the shelf for a theme that is a place rather than a palette",
      aero["group"] == "character", aero["group"])
check("it is named", aero["name"] == "Frutiger Aero", aero["name"])
payload = B.theme_payload("aero")
check("the painter gets one colour per token",
      len(payload["map"]) == len(B.THEME_SOURCE), len(payload["map"]))
check("it is not the identity palette, so pages really repaint",
      not payload["identity"])
check("it carries its gloss as a theme's own CSS", bool(payload["extra"]))
pal = B.theme_palette("aero")
check("what you read on it clears WCAG on the page and on an island",
      B.contrast_ratio(pal["text"], pal["bg"]) >= 4.5
      and B.contrast_ratio(pal["text"], pal["surface"]) >= 4.5,
      "%.2f / %.2f" % (B.contrast_ratio(pal["text"], pal["bg"]),
                       B.contrast_ratio(pal["text"], pal["surface"])))
check("and its sheet is not the default one",
      B.theme_style("aero") != B.theme_style("mocha"))
check("every look works on it too, as on all the others",
      all(isinstance(B.look_style(look, "aero"), str)
          for look in B.look_names()))

# ---------------------------------------------------------------- (7)
print("\n(7) no look owns a colour")
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")
known = set(B.THEME_SOURCE.values())
known_rgb = {B._hex_rgb(v) for v in known}


def strays(css):
    out = []
    for match in LITERAL.finditer(css):
        value = match.group(0)
        if value.startswith("#"):
            if len(value) == 7 and value == value.lower() and value in known:
                continue
        else:
            inner = value[value.index("(") + 1:-1].replace("/", ",").split(",")
            try:
                rgb = tuple(int(float(p)) for p in inner[:3])
            except ValueError:
                continue
            if rgb == (0, 0, 0) or rgb in known_rgb:
                continue
        out.append(value)
    return out


loose = []
for look in B.look_names():
    loose += ["%s: %s" % (look, s) for s in strays(B.LOOK_QSS.get(look, ""))]
check("every colour a look writes is a token the engine knows",
      not loose, ", ".join(sorted(set(loose))[:6]))

# A look's sheet goes through the same substitution as everything else,
# so a colour in one would be repainted. None of them has a colour in it
# today — a look owns geometry — but the machinery is what is checked
# here, not the current contents.
probe = B.tint("QLabel#probe { color: #cdd6f4; background: #0d0d12; }",
               "latte")
check("a look's sheet is painted by the palette, like every other sheet",
      "#cdd6f4" not in probe and "#0d0d12" not in probe, probe.strip())

# And the real guarantee: whatever a look puts on the sheet, in any of
# the palettes, is a colour out of that palette and nothing else.
outside = []
for look in B.look_names():
    for theme in B.THEMES:
        sheet = B.look_style(look, theme["key"])
        if not sheet:
            continue
        palette = B.theme_palette(theme["key"])
        allowed = {v.lower() for v in palette.values()}
        allowed_rgb = {B._hex_rgb(v) for v in allowed}
        for match in LITERAL.finditer(sheet):
            value = match.group(0)
            if value.startswith("#"):
                if value.lower() in allowed:
                    continue
            else:
                inner = value[value.index("(") + 1:-1] \
                    .replace("/", ",").split(",")
                try:
                    rgb = tuple(int(float(p)) for p in inner[:3])
                except ValueError:
                    continue
                if rgb == (0, 0, 0) or rgb in allowed_rgb:
                    continue
            outside.append("%s/%s: %s" % (look, theme["key"], value))
check("and in all %d palettes a look never names a colour that is not in "
      "the palette" % len(B.THEMES), not outside,
      ", ".join(sorted(set(outside))[:6]))

# ---------------------------------------------------------------- (8)
print("\n(8) the start page in each look")
view = win.new_tab()
page = view.page()
for _ in range(60):        # software rendering makes this slow, not stuck
    spin(500)
    if js(page, "document.readyState === 'complete' "
                "&& !!document.getElementById('ring')"):
        break
check("the start page came up", bool(js(page, "!!document.getElementById"
                                             "('clock')")))


def look_page(look):
    win.apply_look(look)
    for _ in range(10):
        spin(400)
        got = probe_page()
        if got:
            return got
    return {}


def probe_page():
    return json.loads(js(page, """JSON.stringify({
        look: document.documentElement.getAttribute("data-look"),
        ring: document.querySelectorAll("#ring .ritem").length,
        ringShown: getComputedStyle(document.getElementById("ring"))
                     .display !== "none",
        links: document.querySelectorAll(".links a").length,
        linksShown: !!document.getElementById("links").offsetParent,
        search: !!document.querySelector("form.search input"),
        focused: document.activeElement ===
                 document.querySelector("form.search input"),
        clock: !!document.getElementById("clock").offsetParent,
        pins: (JSON.parse(localStorage.getItem("quicklinks") || "[]")).length
      })""") or "{}")

got = look_page("classic")
check("classic: the quick links are on the page, the ring is not",
      got.get("linksShown") and not got.get("ringShown")
      and got.get("links") == got.get("pins"),
      "%s links, ring %s" % (got.get("links"), got.get("ringShown")))
check("classic: the caret is in the search box, as it always was",
      got.get("focused"), got.get("focused"))

got = look_page("circle")
check("circle: the page knows which look it is being drawn in",
      got.get("look") == "circle", got.get("look"))
check("circle: the ring is up and the flat list is not",
      got.get("ringShown") and not got.get("linksShown"))
check("circle: one item per quick link, plus the one that adds another",
      got.get("ring") == got.get("pins") + 1,
      "%s items for %s links" % (got.get("ring"), got.get("pins")))
check("circle: the clock and the search box are still there",
      got.get("clock") and got.get("search"))
check("circle: and the caret is still in the search box",
      got.get("focused"), got.get("focused"))

spun = json.loads(js(page, """(function () {
  var one = document.querySelector("#ring .ritem");
  var before = one ? one.style.left + "/" + one.style.top : "";
  var e = new WheelEvent("wheel", {deltaY: 400, cancelable: true,
                                   bubbles: true});
  window.dispatchEvent(e);
  return JSON.stringify({before: before, stopped: e.defaultPrevented});
})()""") or "{}")
check("circle: the wheel is taken by the ring instead of scrolling the page",
      spun.get("stopped") is True, spun)
spin(500)
after = js(page, """(function () {
  var one = document.querySelector("#ring .ritem");
  return one ? one.style.left + "/" + one.style.top : "";
})()""")
check("circle: and the ring has turned",
      bool(after) and after != spun.get("before"),
      "%s -> %s" % (spun.get("before"), after))

round_trip = json.loads(js(page, """(function () {
  var items = document.querySelectorAll("#ring .ritem");
  var mid = {x: innerWidth / 2, y: innerHeight / 2}, out = [], far = 0;
  for (var i = 0; i < items.length; i++) {
    var r = items[i].getBoundingClientRect();
    out.push([Math.round(r.left), Math.round(r.top),
              Math.round(r.right), Math.round(r.bottom)]);
  }
  var box = document.querySelector("form.search").getBoundingClientRect();
  var over = 0;
  for (var j = 0; j < out.length; j++)
    if (out[j][0] < box.right && out[j][2] > box.left
        && out[j][1] < box.bottom && out[j][3] > box.top) over++;
  var off = 0;
  for (var k = 0; k < out.length; k++)
    if (out[k][0] < 0 || out[k][1] < 0 || out[k][2] > innerWidth
        || out[k][3] > innerHeight) off++;
  return JSON.stringify({count: out.length, overHub: over, offScreen: off});
})()""") or "{}")
check("circle: no ring item sits on top of the search box",
      round_trip.get("overHub") == 0, round_trip)
check("circle: and none of them is off the edge of the window",
      round_trip.get("offScreen") == 0, round_trip)

after_items = js(page, """(function () {
  var one = document.querySelector("#ring .ritem");
  return one ? getComputedStyle(one).transform : "";
})()""")
check("circle: an item really is placed around the middle",
      bool(after_items) and after_items != "none", repr(after_items)[:60])

got = look_page("taskbar")
check("taskbar: the quick links have moved off the page onto the bar",
      not got.get("linksShown") and not got.get("ringShown"),
      "links %s ring %s" % (got.get("linksShown"), got.get("ringShown")))
check("taskbar: the clock and the search box stay",
      got.get("clock") and got.get("search"))
check("taskbar: and the bar has one button per link",
      win.taskbar._shown == got.get("pins"),
      "%s buttons, %s links" % (win.taskbar._shown, got.get("pins")))

got = look_page("macos")
check("dock: the quick links are on the dock, not on the page",
      not got.get("linksShown"))
check("dock: and the dock has one icon per link",
      len(win.dock._icons) == got.get("pins"),
      "%s icons, %s links" % (len(win.dock._icons), got.get("pins")))

# ---------------------------------------------------------------- (9)
print("\n(9) pinning from the chrome reaches a page that is already open")
win.apply_look("taskbar")
spin(300)
win.add_pin("https://example.net/late", "Late Arrival")
spin(600)
landed = json.loads(js(page, """JSON.stringify({
    stored: (JSON.parse(localStorage.getItem("quicklinks") || "[]"))
              .map(function (l) { return l.name; }),
    drawn: Array.prototype.map.call(
      document.querySelectorAll(".links a"),
      function (a) { return a.firstChild.textContent; })
  })""") or "{}")
check("the open start page has the new pin without being reloaded",
      "Late Arrival" in (landed.get("stored") or []), landed.get("stored"))
check("and the taskbar drew it too",
      any(b.pin["name"] == "Late Arrival" for b in win.taskbar._buttons),
      [b.pin["name"] for b in win.taskbar._buttons])
win.remove_pin("https://example.net/late")
spin(400)
gone = js(page, """(JSON.parse(localStorage.getItem("quicklinks") || "[]"))
                     .map(function (l) { return l.name; }).join(",")""")
check("and unpinning reaches it the same way",
      "Late Arrival" not in (gone or ""), gone)

# ---------------------------------------------------------------- (10)
print("\n(10) the settings page offers the looks")
win.apply_look("classic")
spin(200)
settings = json.loads(win.bridge.getSettings())
check("the settings payload says which look is on",
      settings.get("look") == "classic", settings.get("look"))
check("and offers all four, named in words rather than keys",
      [card["value"] for card in settings.get("looks", [])]
      == B.look_names()
      and all(card["name"] and card["sub"]
              for card in settings.get("looks", [])))
win.bridge.setSetting("look", json.dumps("macos"))
spin(300)
check("choosing one through the settings door puts it on",
      B.active_look() == "macos" and win.dock.isVisible())
check("and writes it down", json.loads(
    B.CONFIG_FILE.read_text()).get("look") == "macos")
win.bridge.setSetting("look", json.dumps("classic"))
spin(200)
# ---------------------------------------------------------------- (12)
print("\n(12) icons of any shape, and never on top of each other")


def fake_icon(width, height):
    """A favicon of a deliberately awkward shape, in the form a pin
    stores one."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(200, 30, 90))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    return B.ICON_PREFIX + base64.b64encode(bytes(buf.data())).decode()


SHAPES = [("Tiny", 16, 16), ("Huge", 128, 128), ("Wide", 96, 18),
          ("Tall", 11, 74), ("Odd", 37, 53), ("None", 0, 0)]
win.apply_look("macos")
spin(300)
win.set_pins([{"name": name,
               "url": "https://%s.example/" % name.lower(),
               "icon": fake_icon(w, h) if w else ""}
              for name, w, h in SHAPES])
spin(400)
dock = win.dock
cells = dock.cells()
check("the dock has one cell per pin", len(cells) == len(SHAPES),
      "%d cells, %d pins" % (len(cells), len(SHAPES)))
check("and every cell is exactly the same size, whatever the icon was",
      len({(c.width(), c.height()) for c, _p, _x in cells}) == 1,
      sorted({(c.width(), c.height()) for c, _p, _x in cells}))
check("every icon is fitted into one square of its own",
      all(pix.width() == dock.ICON_MAX and pix.height() == dock.ICON_MAX
          for _c, _p, pix in cells),
      sorted({(p.width(), p.height()) for _c, _q, p in cells}))


def overlaps(rects):
    return [(i, j) for i in range(len(rects)) for j in range(i + 1, len(rects))
            if rects[i].intersects(rects[j])]


check("no two cells intersect", not overlaps([c for c, _p, _x in cells]),
      overlaps([c for c, _p, _x in cells])[:3])

# ...and that holds while the row is magnified, wherever the cursor is
clashes = []
for focus in range(0, dock.width() + 1, 5):
    dock._focus = focus
    dock._reach = 1.0
    drawn = [r for r, _p, _x in dock.item_rects()]
    if overlaps(drawn):
        clashes.append((focus, overlaps(drawn)[:2]))
    if any(r.width() > dock.CELL or r.height() > dock.CELL for r in drawn):
        clashes.append((focus, "an icon outgrew its cell"))
dock._focus = None
dock._reach = 0.0
check("and no icon overlaps another at any point of the magnification",
      not clashes, clashes[:2])
check("nor does one ever grow past its own cell",
      dock.ICON_MAX < dock.CELL,
      "%d vs %d" % (dock.ICON_MAX, dock.CELL))

win.apply_look("taskbar")
spin(400)
buttons = [b for b in win.taskbar._buttons[:win.taskbar._shown]]
check("the taskbar draws the same awkward icons at one size too",
      bool(buttons) and len({(b.iconSize().width(),
                              b.iconSize().height()) for b in buttons}) == 1)
check("and its buttons do not overlap either",
      not overlaps([b.geometry() for b in buttons]),
      overlaps([b.geometry() for b in buttons])[:3])
win.set_pins([{"name": "Example", "url": "https://example.com/", "icon": ""}])
win.apply_look("classic")
spin(200)

# ---------------------------------------------------------------- (13)
# Both of these run before section (11): that section builds a second
# Browser in the same process, and a second Browser stalls the first's
# page JS (see the note at the head of apply_look / the design doc), so
# anything that needs live runJavaScript on `page` has to come first.
print("\n(13) Liquid Glass frosts the chrome, never the page")
from PyQt6.QtCore import Qt as _Qt  # noqa: E402
check("the glass look is on the shelf, and a chrome look not a pin one",
      "glass" in B.look_names() and not B.look_is_pinned("glass"))
gsheet = B.look_style("glass")
check("its sheet frosts the chrome with translucent surfaces",
      "rgba(" in gsheet and "transparent" in gsheet, gsheet[:40])
check("and turns the window's own base transparent so the blur shows through",
      "QMainWindow { background: transparent" in gsheet)
check("the window carries an alpha channel for the compositor to blur",
      win.testAttribute(_Qt.WidgetAttribute.WA_TranslucentBackground))
win.apply_look("glass")
spin(200)
check("choosing glass puts its frosted sheet on the window",
      "QMainWindow { background: transparent" in app.styleSheet())
check("the page behind the glass stays fully opaque - only the chrome frosts",
      view.page().backgroundColor().alpha() == 255,
      view.page().backgroundColor().alpha())
gset = json.loads(win.bridge.getSettings())
check("settings offers glass as one of the look cards, named in words",
      any(c["value"] == "glass" and c["name"] and c["sub"]
          for c in gset.get("looks", [])))
win.apply_look("classic")
spin(200)
check("and leaving glass restores the classic look's sheet - the theme's "
      "own, with nothing added",
      app.styleSheet() == B.theme_style())

# ---------------------------------------------------------------- (14)
print("\n(14) the circle rework: a big disc and a pendulum sway")
circle_src = (HERE / "start.html").read_text()
check("the wheel-driven pendulum wobble is in the page's script",
      "swayVel" in circle_src and "SWAY_SPRING" in circle_src
      and "placeDisc" in circle_src)
# the loop must be cheap: an eased glide + a shared spring, no live
# per-frame filter, and it MUST park itself (ringRaf -> 0) once the ring
# and the sway have both settled, rather than run forever
check("the ring turns with a cheap eased glide, not a per-frame filter",
      "RING_EASE" in circle_src and "ringTarget" in circle_src
      and "url(#woodgrain)" not in circle_src
      and "feDisplacementMap" not in circle_src)
check("the animation loop stops itself at rest (no idle rAF churn)",
      "(spinDone && swayDone) ? 0 : requestAnimationFrame(ringSpin)"
      in circle_src)
got = look_page("circle")
check("the circle look is on and the page knows it",
      got.get("look") == "circle", got.get("look"))
disc = json.loads(js(page, """(function () {
  var d = document.getElementById("ringdisc");
  if (!d) return "{}";
  var cs = getComputedStyle(d);
  var r = d.getBoundingClientRect();
  return JSON.stringify({shown: cs.display !== "none",
                         w: Math.round(r.width), h: Math.round(r.height)});
})()""") or "{}")
check("the big background disc is drawn in the circle look",
      disc.get("shown") and disc.get("w", 0) > 200 and disc.get("h", 0) > 150,
      disc)
js(page, """window.dispatchEvent(new WheelEvent("wheel",
      {deltaY: 500, cancelable: true, bubbles: true}))""")
spin(80)
swung = js(page, """(function () {
  var one = document.querySelector("#ring .ritem");
  return one ? one.style.transform : "";
})()""") or ""
m_swung = re.search(r"translateX\(([-0-9.]+)px\)", swung)
check("mid-swing a pin is translated sideways - the pendulum swings",
      m_swung is not None and abs(float(m_swung.group(1))) > 0.5,
      repr(swung)[:70])
spin(1600)
settled = js(page, """(function () {
  var one = document.querySelector("#ring .ritem");
  return one ? one.style.transform : "";
})()""") or ""
m_settled = re.search(r"translateX\(([-0-9.]+)px\)", settled)
check("and the sway settles back to rest",
      m_settled is not None and abs(float(m_settled.group(1))) < 1.0,
      repr(settled)[:70])
win.apply_look("classic")
spin(200)
hidden = js(page,
            """getComputedStyle(document.getElementById("ringdisc")).display""")
check("and in the classic look the disc is gone again",
      hidden == "none", hidden)
win.apply_look("classic")

# ---------------------------------------------------------------- (15)
# The Wood colour theme (the circle look no longer wears a wooden wheel;
# the theme itself stays, a warm walnut palette selectable like any other).
print("\n(15) the Wood theme")

check("Wood is on the shelf, a selectable theme", "wood" in B.theme_names())
wpay = B.theme_payload("wood")
check("its payload is built and named in words",
      wpay.get("name") == "Wood" and wpay.get("key") == "wood",
      wpay.get("name"))
check("it is a dark theme with a warm walnut ground",
      wpay.get("dark") and B.theme_palette("wood")["bg"] == "#21140b",
      B.theme_palette("wood")["bg"])
wpal = B.theme_palette("wood")
worst = min(B.contrast_ratio(wpal[t], wpal["bg"])
            for t in ("text", "subtext", "accent", "green", "yellow",
                      "peach", "red"))
check("every ink it reads with clears the contrast floor on its ground",
      worst >= 4.5, "worst %.2f" % worst)
# it brings its own gloss (a _THEME_EXTRAS entry) on top of the recolour
sheet = B.theme_style("wood")
check("and the theme brings its own serif gloss without breaking the Qt sheet",
      sheet.startswith(B._recolor(B.STYLE, B.theme_palette("wood"), qt=True))
      and "Charter" in sheet)

# the Wood theme is selectable in the circle look without a wooden wheel
win.apply_theme("wood")
win.apply_look("circle")
spin(300)
themed = js(page, '''(function () {
  var disc = document.getElementById("ringdisc");
  var face = document.getElementById("ringface");
  return JSON.stringify({disc: disc ? getComputedStyle(disc).display : "none",
                         face: !!face});
})()''') or "{}"
themed = json.loads(themed)
check("the circle disc still renders under the Wood theme; no wooden wheel left",
      themed.get("disc") != "none" and themed.get("face") is False, themed)
win.apply_theme("mocha")
win.apply_look("classic")
spin(200)

# ---------------------------------------------------------------- (11)
print("\n(11) the look survives being shut down")
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en", "look": "macos",
                                     "theme": "gruvbox"}))
B._install_theme_flags()
check("the look is settled before the window is built",
      B.active_look() == "macos", B.active_look())
second = B.Browser()
second.show()
spin(400)
check("a browser started on it comes up wearing it, without being told",
      second.dock is not None and second.dock.isVisible()
      and second.taskbar is None)
check("and its sheet carries both the theme and the look",
      "border-radius" in app.styleSheet()
      and app.styleSheet().startswith(B.theme_style("gruvbox")[:400]))
second.close()
second.deleteLater()
spin(200)


print("\n%d checks failed" % FAILS)
# Straight out, the way test_newtab.py goes out and for the same reason:
# this suite leaves two windows and their cookie jars standing, and Qt's
# teardown of those either hangs or falls over after the last check has
# already been printed. The answer is not to wait for it.
sys.stdout.flush()
os._exit(1 if FAILS else 0)
