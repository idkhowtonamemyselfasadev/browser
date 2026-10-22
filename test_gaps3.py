#!/usr/bin/env python3
"""The six features that were built with no test naming them.

Found by reading FEATURES.md back: every "done" line is supposed to name
the test that covers it, and six named only the code. These are the
checks they were missing — the noisy tab, the wheel over a video, no
autoplay-next, "show in folder" when a download finishes, a capture a
few seconds from now, and muting every tab at once.

Offscreen, scratch data, local server.
"""
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

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/v": "<title>V</title><body><video id=v src='/c.webm' "
          "style='width:300px;height:200px'></video>"
          "<div class='ytp-ce-element'>end card</div></body>",
    "/q": "<title>Q</title><p>quiet</p>",
}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "de",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(900, 700)
win.show()
H.spin(400)
APP = B.APP_WORLD_ID
MAIN = B.MAIN_WORLD_ID
view = win.new_tab(url=None)
H.load(view, srv.url("/v"))
H.spin(800)


def js(code, world=APP, v=None):
    return H.js(v or view, code, world)


print("\n(1) the wheel over a video changes its volume")
check("the tool arms itself once",
      win.media_tool("wheelvolume", view=view) is not False)
H.spin(600)
check("...and says so in the page",
      js("!!window.__wheelVol", APP) is True,
      js("!!window.__wheelVol", APP))
js("""var v = document.getElementById('v');
      v.volume = 0.5;
      v.dispatchEvent(new WheelEvent('wheel',
        {deltaY: 120, bubbles: true, cancelable: true}));""", MAIN)
H.spin(300)
down = js("document.getElementById('v').volume", MAIN)
check("a wheel down turns it down", down is not None and down < 0.5,
      down)
js("""var v = document.getElementById('v');
      v.dispatchEvent(new WheelEvent('wheel',
        {deltaY: -120, bubbles: true, cancelable: true}));
      v.dispatchEvent(new WheelEvent('wheel',
        {deltaY: -120, bubbles: true, cancelable: true}));""", MAIN)
H.spin(300)
up = js("document.getElementById('v').volume", MAIN)
check("...and a wheel up turns it up again", up is not None and up > down,
      [down, up])
check("...and what it is now is shown over the video",
      js("var t = document.getElementById('__volmark');"
         " t ? t.innerText : ''", MAIN) != "",
      js("var t = document.getElementById('__volmark');"
         " t ? t.innerText : ''", MAIN))
check("it does not arm itself twice",
      win.media_tool("wheelvolume", view=view) is not False)

print("\n(2) no autoplay-next")
answer = []
win.media_tool("noautonext", view=view, then=answer.append)
H.wait_for(lambda: answer, 5000)
check("it can be switched on", answer and answer[0] == "on", answer)
check("...and the end cards are hidden",
      js("getComputedStyle(document.querySelector('.ytp-ce-element'))"
         ".display", MAIN) == "none",
      js("getComputedStyle(document.querySelector('.ytp-ce-element'))"
         ".display", MAIN))
check("...and the video is marked so it is not done twice",
      js("document.getElementById('v').dataset.noAutoNext", MAIN) == "1")
answer = []
win.media_tool("noautonext", view=view, then=answer.append)
H.wait_for(lambda: answer, 5000)
check("...and it can be switched off again",
      answer and answer[0] == "off", answer)
check("...which puts the end cards back",
      js("getComputedStyle(document.querySelector('.ytp-ce-element'))"
         ".display", MAIN) != "none")

print("\n(3) the live edge, and catching up to it")
# a real stream is not something this server can serve, so the video's
# seekable range is made to look like one: that is the one thing the
# live tools read. It is installed in the application world, because
# that is the world the media tools run in -- a property defined on an
# element in one JS world is not visible in another, which is the whole
# point of the isolation.
js("""var v = document.getElementById('v');
      v.__fakeEnd = 100;
      Object.defineProperty(v, 'seekable', {configurable: true,
        get: function () {
          var end = v.__fakeEnd;
          return {length: 1, end: function () { return end; },
                  start: function () { return 0; }}; }});
      Object.defineProperty(v, 'currentTime', {configurable: true,
        get: function () { return v.__at || 0; },
        set: function (x) { v.__at = x; }});
      v.__at = 40;""", APP)
H.spin(200)
check("the stand-in stream is in place",
      js("document.getElementById('v').seekable.end(0)", APP) == 100,
      js("document.getElementById('v').seekable.end(0)", APP))
win.media_live(view=view)
H.spin(600)
at = js("document.getElementById('v').__at", APP)
check("“jump to live” lands at the live edge",
      at is not None and at > 99, at)
js("document.getElementById('v').__at = 40;", APP)
H.spin(200)
answer = []
win.media_catch_up(view=view, then=answer.append)
H.wait_for(lambda: answer, 5000)
check("catching up can be switched on", answer and answer[0] == "on",
      answer)
check("...and it plays faster while he is behind",
      js("document.getElementById('v').playbackRate", APP) == 1.1,
      js("document.getElementById('v').playbackRate", APP))
js("""var v = document.getElementById('v');
      v.__at = 99.8;
      v.dispatchEvent(new Event('timeupdate'));""", APP)
H.spin(300)
check("...and goes back to normal once he is level",
      js("document.getElementById('v').playbackRate", APP) == 1,
      js("document.getElementById('v').playbackRate", APP))
js("""var v = document.getElementById('v');
      v.__at = 10;
      v.dispatchEvent(new Event('timeupdate'));""", APP)
H.spin(300)
check("...and faster again if he falls behind",
      js("document.getElementById('v').playbackRate", APP) == 1.1,
      js("document.getElementById('v').playbackRate", APP))
answer = []
win.media_catch_up(view=view, then=answer.append)
H.wait_for(lambda: answer, 5000)
check("...and it can be switched off", answer and answer[0] == "off",
      answer)
check("...which puts the speed back",
      js("document.getElementById('v').playbackRate", APP) == 1)
check("the menu offers it",
      bool(B.UI_STRINGS["de"]["mediaCatchUp"])
      and B.UI_STRINGS["de"]["mediaCatchUp"]
      != B.UI_STRINGS["en"]["mediaCatchUp"],
      [B.UI_STRINGS["en"]["mediaCatchUp"],
       B.UI_STRINGS["de"]["mediaCatchUp"]])

print("\n(4) which tab is making that noise")
check("with nothing playing it says so",
      win.goto_audible_tab() is None)
quiet = win.new_tab(url=QUrl(srv.url("/q")), switch=False)
H.spin(600)


class FakePage:
    """A page that says it is audible, which offscreen nothing is."""

    def __init__(self, real):
        self._real = real

    def recentlyAudible(self):
        return True

    def isAudioMuted(self):
        return False

    def __getattr__(self, name):
        return getattr(self._real, name)


real_page = view.page
view.page = lambda: FakePage(real_page())
win.tabs.setCurrentWidget(quiet)
H.spin(200)
check("the tab making a sound is found",
      win.goto_audible_tab() is view, win.goto_audible_tab() is view)
check("...and it is the one in front now",
      win.current() is view, win.current() is view)
check("asking again with one noisy tab stays there",
      win.goto_audible_tab() is view)
menu = win.media_menu()
check("the sound menu lists it", len(menu.actions()) >= 1,
      [one.text() for one in menu.actions()][:3])
view.page = real_page

print("\n(5) mute every tab, and let them go again")
check("every tab can be muted", win.mute_all_tabs(on=True) is not False)
H.spin(300)
check("...and they really are",
      all(v.page().isAudioMuted() for _i, v in win._real_tabs()),
      [v.page().isAudioMuted() for _i, v in win._real_tabs()])
check("...and they can all be let go again",
      win.mute_all_tabs(on=False) is not False)
H.spin(300)
check("...really let go",
      not any(v.page().isAudioMuted() for _i, v in win._real_tabs()),
      [v.page().isAudioMuted() for _i, v in win._real_tabs()])

print("\n(6) a capture a few seconds from now")
win.config["shotDir"] = str(scratch / "shots")
before = len(list((scratch / "shots").glob("*"))) \
    if (scratch / "shots").is_dir() else 0
check("it says it is coming", win.shot_after(seconds=1) is True)
H.wait_for(lambda: (scratch / "shots").is_dir()
           and len(list((scratch / "shots").glob("*"))) > before, 9000)
after = len(list((scratch / "shots").glob("*"))) \
    if (scratch / "shots").is_dir() else 0
check("...and a picture arrives a second later", after > before,
      [before, after])
check("the whole page can be asked for instead",
      win.shot_after(seconds=1, kind="full") is True)
H.spin(2500)
check("...and that arrives too",
      len(list((scratch / "shots").glob("*"))) > after,
      [after, len(list((scratch / "shots").glob("*")))])

print("\n(7) show in folder, when the file is really there")
opened = []
real_open = B.QDesktopServices.openUrl
B.QDesktopServices.openUrl = lambda url: opened.append(url.toString())


class FakeRequest:
    def __init__(self, done, where):
        self._done = done
        self._where = where

    def isFinished(self):
        return self._done

    def downloadDirectory(self):
        return self._where


win._opened_when_done(FakeRequest(False, str(scratch)))
check("a download still running opens nothing", opened == [], opened)
win._opened_when_done(FakeRequest(True, str(scratch)))
check("...and a finished one opens its folder",
      len(opened) == 1 and opened[0].endswith(scratch.name),
      opened)
check("...the folder, not the file",
      opened and opened[0].startswith("file://"), opened)


class BrokenRequest:
    def isFinished(self):
        raise RuntimeError("the request went away")


win._opened_when_done(BrokenRequest())
check("a request that went away opens nothing and does not raise",
      len(opened) == 1, opened)
B.QDesktopServices.openUrl = real_open

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
