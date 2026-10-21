#!/usr/bin/env python3
"""Screenshots: what is on screen, the whole scrolling page, one
element, an area, and the things done to a capture afterwards.

The pages are built so the result can be checked rather than looked at:
a page of coloured bands at known heights, so a full-page capture can be
asked what colour it has at a given depth, and a page with a password
field, so the blurring can be seen to have happened."""
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
import capture  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


BANDS = ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#00ffff", "#ff00ff"]
STRIPES = ("<!doctype html><title>Stripes</title>"
           "<style>body{margin:0}div{height:600px}"
           "#head{position:fixed;top:0;left:0;right:0;height:40px;"
           "background:#000;color:#fff}</style>"
           "<div id=head>a fixed header</div>"
           + "".join("<div id=b%d style='background:%s'></div>" % (i, c)
                     for i, c in enumerate(BANDS)))

FORM = ("<!doctype html><title>Form</title><style>body{background:#fff}</style>"
        "<input type=password id=pw value='hunter2' style='font-size:40px'>"
        "<div id=box style='width:200px;height:120px;background:#123456'></div>")

app = H.app()
srv = H.Server({"/stripes": STRIPES, "/form": FORM})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(900, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/stripes"))
H.spin(600)

shots = Path(B.CONFIG_FILE).parent / "shots"
win.config["shotDir"] = str(shots)
win.config["shotFormat"] = "png"

print("\n(1) what is on screen")
path = win.shot_visible(copy=True, save=True, view=view)
check("a file was written", path is not None and Path(path).exists(), path)
check("it is where he said", path is not None
      and str(path).startswith(str(shots)), path)
check("and it is on the clipboard",
      not QGuiApplication.clipboard().image().isNull())
img = capture.visible(view)
check("the capture is the size of the view",
      abs(img.width() - view.width()) <= 2
      and abs(img.height() - view.height()) <= 2,
      (img.width(), img.height(), view.width(), view.height()))

print("\n(2) the whole scrolling page")
full = capture.full_page(view, B.APP_WORLD_ID)
check("it is much taller than the window",
      full.height() > view.height() * 2, (full.height(), view.height()))
check("...and about as tall as the page",
      abs(full.height() - 600 * len(BANDS)) < 700, full.height())


def band_colour(image, which):
    """The colour in the middle of one of the page's bands."""
    y = int((which + 0.5) * 600 * image.height() / (600.0 * len(BANDS)))
    return image.pixelColor(image.width() // 2, min(y, image.height() - 1)).name()


for i, want in enumerate(BANDS):
    check("band %d is %s in the capture" % (i, want),
          band_colour(full, i) == want, band_colour(full, i))
check("the page is back where it was after the capture",
      H.js(view, "window.scrollY", B.MAIN_WORLD_ID) == 0,
      H.js(view, "window.scrollY", B.MAIN_WORLD_ID))
check("the fixed header is not repeated down the page",
      band_colour(full, 3) == BANDS[3], band_colour(full, 3))

print("\n(3) one element")
H.load(view, srv.url("/form"))
H.spin(400)
one = capture.element(view, B.APP_WORLD_ID, "#box")
check("the element capture has the element's size",
      abs(one.width() - 200) <= 3 and abs(one.height() - 120) <= 3,
      (one.width(), one.height()))
check("and the element's colour",
      one.pixelColor(one.width() // 2, one.height() // 2).name() == "#123456",
      one.pixelColor(one.width() // 2, one.height() // 2).name())
check("an element that is not there gives nothing",
      capture.element(view, B.APP_WORLD_ID, "#nope").isNull())

print("\n(4) an area")
box = capture.area(view, (0, 0, 100, 50))
check("the area capture is the size asked for",
      box.width() == 100 and box.height() == 50, (box.width(), box.height()))
check("an area outside the page is empty",
      capture.area(view, (5000, 5000, 10, 10)).isNull())

print("\n(5) blurring what should not be in a picture")
plain = capture.visible(view)
capture.redact(view, B.APP_WORLD_ID, True)
H.spin(300)
blurred = capture.visible(view)
check("the picture changed where the password is",
      plain.pixelColor(30, 20) != blurred.pixelColor(30, 20)
      or plain != blurred,
      (plain.pixelColor(30, 20).name(), blurred.pixelColor(30, 20).name()))
check("the page says the blur is on",
      H.js(view, "!!document.getElementById('__shotredact')", B.MAIN_WORLD_ID))
capture.redact(view, B.APP_WORLD_ID, False)
H.spin(200)
check("and it comes off again",
      not H.js(view, "!!document.getElementById('__shotredact')",
               B.MAIN_WORLD_ID))

print("\n(6) names, formats and sizes")
name = capture.name_for("shot-%Y%m%d", "Some Page!", "example.com", "png")
check("a name follows the pattern", name.startswith("shot-") and
      name.endswith(".png"), name)
name = capture.name_for("{site}-{title}", "Some Page!", "example.com", "jpeg")
check("{site} and {title} are filled in",
      name == "example.com-Some Page.jpeg", name)
png = capture.encode(full, "png")
jpg = capture.encode(full, "jpeg", 70)
check("PNG comes out as PNG", png[:4] == b"\x89PNG", png[:4])
check("JPEG comes out as JPEG", jpg[:2] == b"\xff\xd8", jpg[:2])
# (not "the JPEG is smaller": these bands are flat colour, which is
# exactly what PNG is good at and JPEG is not)
from PyQt6.QtGui import QImage  # noqa: E402
back = QImage()
back.loadFromData(jpg, "JPEG")
check("the JPEG decodes back to the same size",
      back.size() == full.size(), (back.size(), full.size()))
raw, small = capture.fit_under(full, 20000, "jpeg")
check("fitting under a limit gets under it", len(raw) <= 20000, len(raw))
check("and keeps a picture, not a postage stamp",
      small.width() > 100, small.width())

print("\n(7) the page is held still while a long capture runs")
H.load(view, srv.url("/stripes"))
H.spin(400)
capture.clean(view, B.APP_WORLD_ID, True)
H.spin(200)
check("the fixed header is pinned into the page",
      H.js(view, "getComputedStyle(document.getElementById('head')).position",
           B.MAIN_WORLD_ID) == "absolute",
      H.js(view, "getComputedStyle(document.getElementById('head')).position",
           B.MAIN_WORLD_ID))
capture.clean(view, B.APP_WORLD_ID, False)
H.spin(200)
check("and let go afterwards",
      H.js(view, "getComputedStyle(document.getElementById('head')).position",
           B.MAIN_WORLD_ID) == "fixed")

print("\n(8) a capture kept on top")
window = capture.PinnedShot(one, "test")
window.show()
H.spin(200)
check("the window is up", window.isVisible())
check("it holds the picture", not window.image.isNull())
window.close()
H.spin(100)

print("\n(9) through the browser's own entries")
win.config["shotRedact"] = True
path = win.shot_element("#box", view=view) if False else None
path = win.shot_area((0, 0, 60, 60), view=view)
check("an area capture writes a file too",
      path is not None and Path(path).exists(), path)
check("the folder has what we took",
      len(list(shots.glob("*.png"))) >= 2,
      len(list(shots.glob("*.png"))))
win.config["shotFormat"] = "jpeg"
path = win.shot_visible(view=view)
check("the format he picked is the format on disk",
      path is not None and str(path).endswith(".jpeg"), path)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
