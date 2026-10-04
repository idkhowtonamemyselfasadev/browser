#!/usr/bin/env python3
""""Save image" for anything drawn under the cursor.

The engine's own menu only offers "Save image" on a bare <img>. The
report was every other picture: the one under a transparent overlay,
a CSS background, a canvas, and sites that swallow the right-click so
the menu never shows. This suite holds down that:

  * an <img> under an overlay div is found and downloaded through the
    engine (it lands in the download folder with its real name)
  * a CSS background-image is found and downloaded the same way
  * a canvas is written straight from its data: URL as a PNG
  * a spot with no picture says so and writes nothing
  * Shift + right-click is not stoppable by the page; a plain one is

Offscreen, scratch profile, local http server on 127.0.0.1.
"""
import base64
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
for cand in (HERE, Path.home() / "browser"):
    if (cand / "browser.py").exists():
        sys.path.insert(0, str(cand))
        break
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QPoint  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# a 1x1 red PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg==")
PAGE = b"""<!doctype html><meta charset="utf-8"><title>pics</title>
<style>body{margin:0}
 #wrap{position:absolute;left:40px;top:40px;width:200px;height:200px}
 #wrap img{width:200px;height:200px}
 #overlay{position:absolute;left:0;top:0;width:200px;height:200px;background:transparent}
 #bg{position:absolute;left:300px;top:40px;width:200px;height:200px;
     background:url(/bg.png) center/cover no-repeat}
 #cv{position:absolute;left:560px;top:40px}
 #empty{position:absolute;left:40px;top:300px;width:200px;height:100px}
 /* a zoom viewer: the picture takes no pointer events, a box above it takes the gestures */
 #zoom{position:absolute;left:300px;top:300px;width:300px;height:300px;overflow:hidden}
 #zoom img{position:absolute;left:-50px;top:-50px;width:400px;height:400px;pointer-events:none;transform:scale(1.5)}
 #zoom .pan{position:absolute;inset:0;cursor:grab}
</style>
<div id="wrap"><img id="pic" src="/pic.png"><div id="overlay"></div></div>
<div id="bg"></div>
<canvas id="cv" width="120" height="120"></canvas>
<div id="empty">plain text</div>
<div id="zoom"><img id="big" src="/big.png"><div class="pan"></div></div>
<script>
 var c=document.getElementById('cv').getContext('2d'); c.fillStyle='#0f0'; c.fillRect(0,0,120,120);
 window.menus=0;
 document.addEventListener('contextmenu', function(e){ window.menus++; e.preventDefault(); });
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith(".png"):
            body, ctype = PNG, "image/png"
        else:
            body, ctype = PAGE, "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
DL = SCRATCH / "dl"
win = B.Browser()
win.config["downloadDir"] = str(DL)
win.resize(1100, 800)
win.show()


def pump(sec):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents()
        time.sleep(0.02)


def js(view, code, world=0, wait=8):
    box = {}
    view.page().runJavaScript(code, world, lambda r: box.update(r=r))
    t = time.time()
    while "r" not in box and time.time() - t < wait:
        app.processEvents()
        time.sleep(0.02)
    return box.get("r", "<timeout>")


def centre(view, sel):
    return json.loads(js(view, "var r=document.querySelector(%s)"
                               ".getBoundingClientRect();"
                               "JSON.stringify([r.left+r.width/2,"
                               " r.top+r.height/2])" % json.dumps(sel)))


def files():
    return sorted(p.name for p in DL.glob("*")) if DL.exists() else []


def wait_files(n, sec=8):
    t = time.time()
    while time.time() - t < sec:
        f = [x for x in files() if not x.endswith(".download")]
        if len(f) >= n:
            return f
        pump(0.2)
    return files()


pump(1.5)
view = win.new_tab(BASE + "/pics")
pump(4)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
pump(1.5)

# (a) the <img> under a transparent overlay
x, y = centre(view, "#overlay")
check("a1 the overlay is what the page reports at that spot",
      js(view, "document.elementFromPoint(%s,%s).id" % (x, y)) == "overlay")
view.save_image_at(QPoint(int(x), int(y)))
got = wait_files(1)
check("a2 the picture under it was downloaded", got == ["pic.png"], got)
check("a3 with its bytes intact",
      (DL / "pic.png").exists() and (DL / "pic.png").read_bytes() == PNG)

# (b) a CSS background
x, y = centre(view, "#bg")
view.save_image_at(QPoint(int(x), int(y)))
got = wait_files(2)
check("b1 the background image was downloaded", "bg.png" in got, got)

# (c) a canvas: no address, written from its data: URL
x, y = centre(view, "#cv")
view.save_image_at(QPoint(int(x), int(y)))
got = wait_files(3)
cv = [f for f in got if f not in ("pic.png", "bg.png")]
check("c1 the canvas was written as a file", len(cv) == 1 and cv[0].endswith(".png"), got)
check("c2 and it is a PNG named after the page",
      cv and (DL / cv[0]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and cv[0].startswith("pics"), cv)
check("c3 it is on the downloads list as a local file",
      any(e.get("local") and e["name"] == (cv[0] if cv else "") and e["state"] == "done"
          for e in win.downloads))

# (d2) a zoom viewer: pointer-events:none on the picture, gestures on a box above
x, y = centre(view, "#zoom")
check("d2a hit-testing does not see the picture there",
      js(view, "document.elementsFromPoint(%s,%s).map(e=>e.tagName).join()" % (x, y)).find("IMG") < 0)
view.save_image_at(QPoint(int(x), int(y)))
got = wait_files(4)
check("d2b the zoomed picture was still found and downloaded", "big.png" in got, got)

# (d) nowhere near a picture
before = files()
x, y = centre(view, "#empty")
view.save_image_at(QPoint(int(x), int(y)))
pump(2)
check("d1 nothing is written when there is no image", files() == before, files())

# (e) the page swallows right-clicks; Shift + right-click still gets through
r = js(view, "window.menus=0; var e=new MouseEvent('contextmenu',{bubbles:true,cancelable:true});"
             "document.body.dispatchEvent(e); JSON.stringify([window.menus, e.defaultPrevented])")
check("e1 a plain right-click is the page's to swallow", r == "[1,true]", r)
r = js(view, "window.menus=0; var e=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,shiftKey:true});"
             "document.body.dispatchEvent(e); JSON.stringify([window.menus, e.defaultPrevented])")
check("e2 Shift + right-click never reaches the page's handler", r == "[0,false]", r)

print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
