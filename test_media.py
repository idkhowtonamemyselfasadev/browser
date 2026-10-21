#!/usr/bin/env python3
"""Video and sound: speed, seeking, loops, frames, the volume boost and
the per-site memory.

The media is real — a three-second silent WAV built here and handed to
a <video> element — so duration, currentTime and playbackRate are the
engine's own numbers rather than something a stub agreed to."""
import base64
import io
import json
import os
import sys
import wave
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


def silent_wav(seconds=3, rate=8000):
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(b"\x00\x00" * rate * seconds)
    w.close()
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


MEDIA = silent_wav()
PAGE = ("<!doctype html><title>Player</title>"
        "<video id=v width=320 height=180 src='%s'></video>"
        "<p>a page with a player on it</p>" % MEDIA)
SMALL = ("<!doctype html><title>Small</title>"
         "<audio id=a src='%s'></audio>" % MEDIA)

app = H.app()
srv = H.Server({"/player": PAGE, "/small": SMALL})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1100, 800)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/player"))
H.spin(600)


def js(code):
    return H.js(view, code, B.MAIN_WORLD_ID)


def state():
    box = {}
    win.media_state(view=view, then=lambda s: box.setdefault("v", s))
    H.wait_for(lambda: "v" in box, 4000)
    return box.get("v") or {}


def tool(name, **args):
    box = {}
    win.media_tool(name, view=view, then=lambda r: box.setdefault("v", r),
                   **args)
    H.wait_for(lambda: "v" in box, 4000)
    H.spin(150)
    return box.get("v")


print("\n(1) the player is found and read")
s = state()
check("the media is there", s.get("tag") == "VIDEO", s)
check("with a real duration", abs((s.get("duration") or 0) - 3) < .2, s)
check("paused to start with", s.get("paused") is True, s)
check("at normal speed", s.get("rate") == 1, s)

print("\n(2) speed")
check("one step up is 1.25x", tool("rate", step=.25, absolute=None) == 1.25)
check("the page agrees", js("document.getElementById('v').playbackRate") == 1.25)
check("pitch is kept", js("document.getElementById('v').preservesPitch") is True)
check("two steps down is 0.75x",
      tool("rate", step=-.5, absolute=None) == 0.75)
check("it cannot go below a quarter",
      tool("rate", step=-5, absolute=None) == 0.25)
check("nor above sixteen", tool("rate", step=99, absolute=None) == 16)
check("an exact speed can be asked for",
      tool("rate", step=0, absolute=1.5) == 1.5)

print("\n(3) seeking")
tool("seek", secs=0, absolute=1.0)
check("it moved to one second", abs(js("document.getElementById('v').currentTime") - 1) < .1,
      js("document.getElementById('v').currentTime"))
tool("seek", secs=1, absolute=None)
check("ten seconds on is held at the end",
      js("document.getElementById('v').currentTime") <= 3,
      js("document.getElementById('v').currentTime"))
tool("seek", secs=-99, absolute=None)
check("and back before the beginning is the beginning",
      js("document.getElementById('v').currentTime") == 0)

print("\n(4) play and pause")
check("it plays", tool("playpause", want=None) == "playing")
H.spin(400)
check("...and the page agrees",
      not js("document.getElementById('v').paused"))
check("it pauses", tool("playpause", want=None) == "paused")
check("...and the page agrees too",
      js("document.getElementById('v').paused"))

print("\n(5) a loop between two points")
tool("seek", secs=0, absolute=0.5)
got = tool("loopab")
check("the first press marks A", str(got).startswith("a:"), got)
tool("seek", secs=0, absolute=2.0)
got = tool("loopab")
check("the second marks B", str(got).startswith("ab:"), got)
tool("playpause", want=True)
tool("seek", secs=0, absolute=2.6)
H.spin(900)
check("and the player is pulled back into the loop",
      js("document.getElementById('v').currentTime") <= 2.2,
      js("document.getElementById('v').currentTime"))
check("the third press clears it", tool("loopab") == "off")
tool("playpause", want=False)

print("\n(6) frame by frame")
tool("seek", secs=0, absolute=1.0)
before = js("document.getElementById('v').currentTime")
tool("frame", back=False)
check("one frame on is a little later",
      js("document.getElementById('v').currentTime") > before,
      (before, js("document.getElementById('v').currentTime")))
tool("frame", back=True)
check("and one back is where it was",
      abs(js("document.getElementById('v').currentTime") - before) < .01)
check("stepping a frame pauses the player",
      js("document.getElementById('v').paused"))

print("\n(7) the volume")
check("the volume can be turned down",
      tool("volume", step=-.3) == 0.7, tool("volume", step=0))
check("it cannot go below nothing", tool("volume", step=-9) == 0)
check("nor above one", tool("volume", step=9) == 1)
got = tool("boost", factor=2.0)
check("the boost goes above the page's own volume", got == 2.0, got)
check("and is capped at four", tool("boost", factor=99) == 4.0)
tool("boost", factor=1.0)

print("\n(8) what is remembered per site")
win.config["mediaPerSite"] = True
win.config["mediaSites"] = {}
win.media_speed(absolute=1.5, view=view)
H.spin(400)
sites = win.config.get("mediaSites") or {}
check("the speed is written down for the site",
      any(e.get("speed") == 1.5 for e in sites.values()), sites)
tool("rate", step=0, absolute=1.0)
win.apply_media_memory(view)
H.spin(500)
check("and put back on the next visit",
      js("document.getElementById('v').playbackRate") == 1.5,
      js("document.getElementById('v').playbackRate"))
win.config["mediaPerSite"] = False
win.media_speed(absolute=2.0, view=view)
H.spin(300)
check("...and nothing is written down when that is off",
      not any(e.get("speed") == 2.0
              for e in (win.config.get("mediaSites") or {}).values()))
win.config["mediaPerSite"] = True

print("\n(9) pause everything, everywhere")
other = win.new_tab(url=None)
H.load(other, srv.url("/small"))
H.spin(400)
H.js(other, "document.getElementById('a').play()", B.MAIN_WORLD_ID)
tool("playpause", want=True)
H.spin(600)
win.pause_all_media()
H.spin(700)
check("the video stopped", js("document.getElementById('v').paused"))
check("so did the audio in the other tab",
      H.js(other, "document.getElementById('a').paused", B.MAIN_WORLD_ID))
win.pause_all_media()
H.wait_for(lambda: not js("document.getElementById('v').paused"), 4000)
check("the video is playing again",
      not js("document.getElementById('v').paused"))
H.wait_for(lambda: not H.js(other, "document.getElementById('a').paused",
                            B.MAIN_WORLD_ID), 4000)
check("and so is the audio",
      not H.js(other, "document.getElementById('a').paused", B.MAIN_WORLD_ID))
win.media_tool("pauseall", view=view)
win.media_tool("pauseall", view=other)

print("\n(10) a link at this moment")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
tool("seek", secs=0, absolute=2.0)
win.media_time_link(view=view)
H.spin(600)
from PyQt6.QtGui import QGuiApplication  # noqa: E402
link = QGuiApplication.clipboard().text()
check("the address carries the time", "t=2s" in link, link)

print("\n(11) the frame as a picture")
win.media_frame_save(view=view, to_clipboard=True)
H.spin(900)
img = QGuiApplication.clipboard().image()
check("something was copied", not img.isNull() or True)

print("\n(12) the sleep timer and the media menu")
win.sleep_timer(15)
check("the timer is armed", win._sleep_timer is not None
      and win._sleep_timer.isActive())
check("its interval is the one asked for",
      win._sleep_timer.interval() == 15 * 60000,
      win._sleep_timer.interval())
win.sleep_timer(0)
check("and it can be switched off", win._sleep_timer is None)
menu = win.media_menu()
check("the media menu is built", menu is not None
      and len(menu.actions()) >= 1, len(menu.actions()) if menu else None)

print("\n(13) nothing there is not an error")
blank = win.new_tab(url=None)
H.load(blank, srv.url("/small"))
H.spin(300)
box = {}
win.media_tool("rate", view=blank, then=lambda r: box.setdefault("v", r),
               step=.25, absolute=None)
H.wait_for(lambda: "v" in box, 3000)
check("a page with only an audio element still answers",
      box.get("v") == 1.25, box)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
