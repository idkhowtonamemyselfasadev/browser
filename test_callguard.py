#!/usr/bin/env python3
"""A tab on a call says so, in a file anything on the machine can read.

The desktop here mixes what the browser plays into a virtual microphone,
so a song can be shared into a call. When the call is IN the browser,
that same audio loops straight back into the microphone and echo
cancellation eats the speaker's voice. The cure is to stop sharing while
a tab is capturing, and the only thing that knows a tab is capturing is
the browser -- so it publishes it:

    $XDG_RUNTIME_DIR/browser-call.on   (the temporary directory if unset)

exists while at least one tab holds a live microphone track, has its
mtime refreshed every five seconds while that lasts, and is removed when
the last capture ends, when the capturing tab closes, and on the way out.
A reader treats an mtime older than fifteen seconds as stale, so a
browser killed with -9 cannot leave a lie behind -- but a clean exit
still takes the file away.

What is asserted here:

  * the path, the heartbeat, and that nothing is written INTO the file
    (not the site, not the tab, not the number of tracks),
  * up when a page reports a capture, down when it reports none, down
    when the tab closes, down when a page falls silent, down on quit,
  * a flag this browser did not raise is never taken down by it,
  * the real JavaScript, on a real page, with Chromium's fake capture
    device: getUserMedia is wrapped additively (same name, same arity,
    the same own properties a native method has, still on the
    prototype, errors still errors), a live track is counted, stop()
    takes it off the count, a clone of a live track keeps the call up
    after the original is stopped, the callback-shaped getUserMedia
    this engine still carries counts too, a capture inside a
    cross-origin-shaped iframe is found, and navigating away clears the
    page's contribution,
  * the page cannot join in: watching every event it can reach teaches
    it nothing, because both sides took the natives the count travels
    on before any page script ran -- so a forged event raises no flag,
  * and it cannot talk this browser out of a microphone it is really
    holding: a page that makes readyState answer "ended", or empties
    getAudioTracks, or swallows addEventListener to get hold of the
    watcher's own "it stopped" callback, is still counted as capturing.
    (What is NOT claimed, and is not asserted here because it is true:
    a page that plants an iframe of its own can poison that frame
    before the watcher reaches it, read the token out of it, and then
    lie about ITS OWN tab in either direction. See the changelog.)
  * the count lives in the isolated world, invisible to the page, and
    both scripts are in every cookie jar -- the main one, a virtual
    browser's, and the off-the-record one a private tab uses.

Offscreen, against scratch data; your own vault, config and runtime
directory are never touched.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# the flag must land in scratch, never in the real runtime directory
# where the running browser's own would be
RUN = Path(tempfile.mkdtemp(prefix="browsercall-run-"))
os.environ["XDG_RUNTIME_DIR"] = str(RUN)
# there is no microphone offscreen. Chromium's fake capture device is a
# real device as far as the page is concerned: getUserMedia resolves
# with a genuine MediaStreamTrack, which is exactly what is being
# counted here. The fake UI answers the engine's own permission prompt,
# which is not what this suite is about.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    + " --use-fake-device-for-media-stream --use-fake-ui-for-media-stream")

from _boot import B  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

PAGES = Path(tempfile.mkdtemp(prefix="browsercall-pages-"))
FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1200, 800)
# offscreen widgets report themselves invisible until shown, and a view
# nobody showed loads and paints differently
win.show()
app.processEvents()

FLAG = Path(B.call_flag_path())


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def load(view, url):
    """Wait for a page to be up. A load already in flight (the start
    page this tab opened with) is cancelled by this one and reports
    itself finished-and-failed on the way out, so the first answer is
    not necessarily ours: wait for one that succeeded."""
    done = []
    view.loadFinished.connect(lambda ok: done.append(ok))
    view.load(QUrl(url) if isinstance(url, str) else url)
    end = time.time() + 20
    while True not in done and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    pump(0.3)
    return True in done


def js(page, code, world=B.MAIN_WORLD_ID, wait=8):
    box = {}
    page.runJavaScript(code, world, lambda r: box.update(r=r))
    end = time.time() + wait
    while "r" not in box and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    return box.get("r", "<timeout>")


def poll():
    """One round of what the timer does: ask every frame of every page,
    and let the answers come back."""
    win._call_poll()
    pump(1.2)


def tick():
    """A whole heartbeat: forget what is gone, publish, ask again."""
    win._call_tick()
    pump(1.2)


# ---------------------------------------------------------------- (1)
print("\n(1) the contract: where the flag is and what is in it")
check("the path is the runtime directory's browser-call.on",
      B.call_flag_path() == os.path.join(str(RUN), "browser-call.on"),
      B.call_flag_path())
saved = os.environ.pop("XDG_RUNTIME_DIR")
check("...and the temporary directory when there is no runtime one",
      B.call_flag_path() == os.path.join(tempfile.gettempdir(),
                                         "browser-call.on"),
      B.call_flag_path())
os.environ["XDG_RUNTIME_DIR"] = saved
check("the name is the one the audio side listens for",
      B.CALL_FLAG_NAME == "browser-call.on", B.CALL_FLAG_NAME)
check("the heartbeat is five seconds", B.CALL_TICK_MS == 5000,
      B.CALL_TICK_MS)
check("a page that falls silent is dropped before a reader calls the "
      "file stale", 0 < B.CALL_STALE < 15, B.CALL_STALE)
check("the heartbeat is running", win._call_timer.isActive())
check("...at that interval", win._call_timer.interval() == B.CALL_TICK_MS,
      win._call_timer.interval())
# from here on the beat is driven by hand, so nothing lands between an
# arrangement and the check that reads it
win._call_timer.stop()
check("nobody is on a call at rest", win.call_in_progress() is False)
check("...and there is no flag", not FLAG.exists())

# ---------------------------------------------------------------- (2)
print("\n(2) a tab reports a live microphone")
view = win.current()
page = view.page()
key = win._call_page_key(page)
win._call_report(key, 1)
check("the flag is up", FLAG.exists())
check("the browser says so too", win.call_in_progress() is True)
check("nothing is written into it - not the site, not the tab",
      FLAG.stat().st_size == 0, FLAG.stat().st_size)
check("a page is named by something a new page cannot inherit",
      win._call_page_key(page) == key
      and win._call_page_key(page) != win._call_ids + 1)

old = time.time() - 40
os.utime(FLAG, (old, old))
check("the file has been made to look stale", time.time() - FLAG.stat().st_mtime > 30)
win._call_apply()
check("a heartbeat refreshes the mtime",
      time.time() - FLAG.stat().st_mtime < 3,
      time.time() - FLAG.stat().st_mtime)

# ---------------------------------------------------------------- (3)
print("\n(3) and takes it down again")
win._call_report(key, 0)
check("no capture, no flag", not FLAG.exists())
check("...and the browser agrees", win.call_in_progress() is False)

win._call_report(key, 2)
check("two tracks on one page still means one call", FLAG.exists())
win._call_live[key] = time.monotonic() - (B.CALL_STALE + 5)
tick()
check("a page that stops answering stops counting", not FLAG.exists())

# ---------------------------------------------------------------- (4)
print("\n(4) the capturing tab closes")
second = win.new_tab(url="about:blank", switch=False)
pump(0.4)
skey = win._call_page_key(second.page())
win._call_report(skey, 1)
check("the second tab's call raises the flag", FLAG.exists())
index = win.tabs.indexOf(second)
check("the tab is in the strip", index >= 0, index)
win.close_tab(index)
pump(0.4)
tick()
check("closing it takes the flag down", not FLAG.exists())
check("...and empties the list", win._call_live == {}, win._call_live)

# ---------------------------------------------------------------- (5)
print("\n(5) a flag this browser did not raise is not its to take down")
FLAG.write_text("")
check("a foreign flag is there", FLAG.exists())
check("...and we did not raise it", B._call_flag_raised is False)
B.call_flag_drop()
check("dropping ours leaves theirs alone", FLAG.exists())
win._call_apply()
check("...and so does a whole heartbeat with nobody on a call",
      FLAG.exists())
FLAG.unlink()
B.call_flag_raise()
check("raising it works when it is ours", FLAG.exists()
      and B._call_flag_raised is True)
B.call_flag_drop()
check("...and then it comes down", not FLAG.exists())

# ---------------------------------------------------------------- (6)
print("\n(6) the script, on a real page, with a real (fake) microphone")
(PAGES / "inner.html").write_text(
    "<!doctype html><html><body>inner</body></html>", encoding="utf-8")
(PAGES / "call.html").write_text(
    "<!doctype html><html><body>outer"
    "<iframe src='inner.html'></iframe></body></html>", encoding="utf-8")
view = win.current()
page = view.page()
key = win._call_page_key(page)
ok = load(view, QUrl.fromLocalFile(str(PAGES / "call.html")))
check("the page is up", ok)
check("...on a secure page, so there is a microphone API at all",
      js(page, "!!(window.isSecureContext && navigator.mediaDevices)")
      is True)

check("getUserMedia is still a function",
      js(page, "typeof navigator.mediaDevices.getUserMedia") == "function")
check("...still the prototype's, not one planted on the object",
      js(page, "Object.getOwnPropertyDescriptor("
               "navigator.mediaDevices, 'getUserMedia') === undefined")
      is True)
# the engine's own getUserMedia declares no arguments (the constraints
# are optional), while the wrapper is written with one - so a zero here
# is the copied arity and not a coincidence
check("...still called getUserMedia, still declaring what it declared",
      js(page, "navigator.mediaDevices.getUserMedia.name + '/' + "
               "navigator.mediaDevices.getUserMedia.length")
      == "getUserMedia/0",
      js(page, "navigator.mediaDevices.getUserMedia.name + '/' + "
               "navigator.mediaDevices.getUserMedia.length"))
check("...and still saying it is native",
      "[native code]" in str(js(page, "'' + "
                                "navigator.mediaDevices.getUserMedia")))
check("stop() is left looking native too",
      "[native code]" in str(js(page, "'' + MediaStreamTrack.prototype.stop")))

check("the count is not in the page's world",
      js(page, "typeof window.__callLive") == "undefined")
check("...it is in ours", js(page, "typeof window.__callLive",
                            B.APP_WORLD_ID) == "function")
check("...and it starts at nothing",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0)

# a promise cannot be carried back out of the page, so the outcome is
# parked in a variable and read a moment later
js(page, "window.__e = 'pending';"
         "navigator.mediaDevices.getUserMedia({}).then("
         "function () { window.__e = 'resolved'; },"
         "function (e) { window.__e = 'rejected:' + e.name; }); 0")
pump(0.8)
check("a bad call still fails the way the engine fails it",
      js(page, "window.__e") == "rejected:TypeError",
      js(page, "window.__e"))

poll()
check("no call yet", not FLAG.exists())

js(page, "window.__t = null;"
         "navigator.mediaDevices.getUserMedia({audio: true}).then("
         "function (s) { window.__t = s.getAudioTracks()[0]; }); 0")
pump(1.5)
check("the page got its stream",
      js(page, "window.__t && window.__t.kind") == "audio",
      js(page, "'' + window.__t"))
check("the isolated world counted it",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1)
poll()
check("a poll raises the flag", FLAG.exists())
check("...and the browser says a call is on", win.call_in_progress() is True)
check("...for that page", key in win._call_live, win._call_live)

js(page, "window.__t.stop(); 0")
pump(0.5)
check("the page's own stop() still ran",
      js(page, "window.__t.readyState") == "ended")
check("...and the count came down",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0)
poll()
check("the flag comes down with it", not FLAG.exists())

# ---------------------------------------------------------------- (7)
print("\n(7) a clone of a live track is a live microphone")
js(page, "window.__t = null; window.__c = null;"
         "navigator.mediaDevices.getUserMedia({audio: true}).then("
         "function (s) { window.__t = s.getAudioTracks()[0]; }); 0")
pump(1.5)
check("a fresh capture is counted",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1)
js(page, "window.__c = window.__t.clone(); window.__t.stop(); 0")
pump(0.6)
check("cloning it and stopping the original leaves the clone capturing",
      js(page, "window.__c.readyState + '/' + window.__t.readyState")
      == "live/ended",
      js(page, "window.__c.readyState + '/' + window.__t.readyState"))
check("...so the call is still on",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1,
      js(page, "window.__callLive()", B.APP_WORLD_ID))
poll()
check("...and the flag stays up - the music must not come back mid-call",
      FLAG.exists())
js(page, "window.__c.stop(); 0")
pump(0.6)
check("stopping the clone ends it",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0)
poll()
check("...and the flag comes down", not FLAG.exists())

print("\n(8) the callback-shaped getUserMedia, and a page that "
      "tries to join in")
check("the engine still carries the old call",
      js(page, "typeof navigator.getUserMedia") == "function")
js(page, "window.__lt = null; window.__lerr = null;"
         "navigator.getUserMedia({audio: true},"
         " function (s) { window.__lt = s.getAudioTracks()[0]; },"
         " function (e) { window.__lerr = e.name; }); 0")
pump(1.5)
check("it hands the page a microphone",
      js(page, "window.__lt && window.__lt.kind") == "audio",
      js(page, "window.__lerr"))
check("...and that microphone is counted too",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1)
poll()
check("...so the flag is up for it", FLAG.exists())
js(page, "window.__lt.stop(); 0")
pump(0.6)
poll()
check("...and down again when it stops", not FLAG.exists())
js(page, "window.__e2 = 'none';"
         "try { navigator.getUserMedia({audio: true}); }"
         "catch (e) { window.__e2 = 'sync:' + e.name; } 0")
pump(0.4)
check("calling it wrongly still throws what it threw before",
      js(page, "window.__e2") == "sync:TypeError", js(page, "window.__e2"))

check("the wrapper has the own properties a native method has, "
      "and no others",
      js(page, "JSON.stringify(Object.getOwnPropertyNames("
               "navigator.mediaDevices.getUserMedia))")
      == js(page, "JSON.stringify(Object.getOwnPropertyNames("
                  "navigator.mediaDevices.enumerateDevices))"),
      js(page, "JSON.stringify(Object.getOwnPropertyNames("
               "navigator.mediaDevices.getUserMedia))"))
# the page watches every event it can reach, hoping to read the token
js(page, "window.__tok = null;"
         "var d = EventTarget.prototype.dispatchEvent;"
         "EventTarget.prototype.dispatchEvent = function (ev) {"
         "  if (ev && /^__call/.test(ev.type)) window.__tok = ev.type;"
         "  return d.apply(this, arguments); }; 0")
js(page, "window.__t3 = null;"
         "navigator.mediaDevices.getUserMedia({audio: true}).then("
         "function (s) { window.__t3 = s.getAudioTracks()[0]; }); 0")
pump(1.5)
check("a real capture still counts while the page is watching",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1)
check("...but watching taught the page nothing",
      js(page, "window.__tok") is None, js(page, "window.__tok"))
js(page, "window.__t3.stop(); 0")
pump(0.6)
check("the capture ends as it always did",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0)
js(page, "document.dispatchEvent("
         "new CustomEvent('__call_forged', {detail: 7})); 0")
pump(0.4)
check("an event the page forges changes nothing",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0,
      js(page, "window.__callLive()", B.APP_WORLD_ID))
poll()
check("...and raises no flag", not FLAG.exists())

print("\n(8b) a page cannot talk the browser out of a live microphone")
# each of these is a hook the watcher used to read late, and each one
# hid a microphone that was really running
ok = load(view, QUrl.fromLocalFile(str(PAGES / "call.html")))
check("a fresh document to attack from", ok)
check("...starting at nothing",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 0)
check("the page can make readyState lie",
      js(page, "(function () { try {"
               " Object.defineProperty(MediaStreamTrack.prototype,"
               " 'readyState', {get: function () { return 'ended'; },"
               " configurable: true}); return 'patched';"
               "} catch (e) { return 'no:' + e.name; } })()") == "patched")
check("...and empty getAudioTracks()",
      js(page, "(function () { try {"
               " MediaStream.prototype.getAudioTracks ="
               " function () { return []; }; return 'patched';"
               "} catch (e) { return 'no:' + e.name; } })()") == "patched")
check("...and swallow every listener the watcher might register",
      js(page, "window.__caught = null;"
               "(function () { var a = EventTarget.prototype.addEventListener;"
               " EventTarget.prototype.addEventListener ="
               "   function (t, fn) { if (t === 'ended') {"
               "     window.__caught = fn; return; }"
               "     return a.apply(this, arguments); };"
               " return 'patched'; })()") == "patched")
# getTracks(), because the page just emptied getAudioTracks() -
# the watcher reads its own copy of it and is not fooled
js(page, "window.__a = null;"
         "navigator.mediaDevices.getUserMedia({audio: true}).then("
         "function (s) { window.__a = s.getTracks()[0]; }); 0")
pump(1.8)
check("the microphone is really running",
      js(page, "window.__a && window.__a.kind") == "audio",
      js(page, "'' + window.__a"))
check("...and it is counted anyway",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1,
      js(page, "window.__callLive()", B.APP_WORLD_ID))
poll()
check("...so the flag is up", FLAG.exists())
check("the page never got hold of the watcher's callback",
      js(page, "typeof window.__caught") == "object",
      js(page, "typeof window.__caught"))
js(page, "try { window.__caught(); } catch (e) {} 0")
pump(0.5)
check("...and calling what it did get changes nothing",
      js(page, "window.__callLive()", B.APP_WORLD_ID) == 1)
poll()
check("...the flag stays up while the microphone is open", FLAG.exists())
js(page, "window.__a.stop(); 0")
pump(0.6)
poll()
check("stopping it for real still ends the call", not FLAG.exists())

# ---------------------------------------------------------------- (9)
print("\n(9) a capture in a frame is a capture")
frames = win._call_frames(page)
check("the page has more than one frame", len(frames) >= 2, len(frames))
child = [f for f in frames if not f.isMainFrame()]
check("...and one of them is the iframe", len(child) == 1, len(child))
box = {}
child[0].runJavaScript(
    "window.__t = null;"
    "navigator.mediaDevices.getUserMedia({audio: true}).then("
    "function (s) { window.__t = s.getAudioTracks()[0]; }); 1",
    B.MAIN_WORLD_ID, lambda r: box.update(r=r))
pump(1.5)
check("the frame asked for the microphone", box.get("r") == 1, box)
poll()
check("the browser found it there too", FLAG.exists())
check("...and hangs it on the page the frame is in", key in win._call_live,
      win._call_live)

ok = load(view, QUrl.fromLocalFile(str(PAGES / "inner.html")))
check("the tab goes somewhere else", ok)
poll()
check("a new document is a page with no call on it", not FLAG.exists())
check("...and nothing is left on the list", win._call_live == {},
      win._call_live)

# ---------------------------------------------------------------- (10)
print("\n(10) every cookie jar carries both halves")


def scripts_of(profile):
    return (len(profile.scripts().find("call-watch")),
            len(profile.scripts().find("call-relay")))


check("the main jar has the watcher and the relay",
      scripts_of(win.profile) == (1, 1), scripts_of(win.profile))
private = win.private_profile()
check("so does the one a private tab uses", scripts_of(private) == (1, 1),
      scripts_of(private))
made = win._make_profile("callguard-test")
check("so does a virtual browser made later", scripts_of(made) == (1, 1),
      scripts_of(made))
watch = win.profile.scripts().find("call-watch")[0]
relay = win.profile.scripts().find("call-relay")[0]
check("the watcher runs in the page's own world, from the first line on",
      watch.worldId() == B.MAIN_WORLD_ID
      and watch.injectionPoint()
      == B.QWebEngineScript.InjectionPoint.DocumentCreation)
check("...and in every frame, because a meeting is often in one",
      watch.runsOnSubFrames() and relay.runsOnSubFrames())
check("the relay runs in the isolated world",
      relay.worldId() == B.APP_WORLD_ID, relay.worldId())
check("the two meet under a name a page cannot guess",
      win._call_event_name() in watch.sourceCode()
      and win._call_event_name() in relay.sourceCode()
      and len(win._call_event_name()) > 12, win._call_event_name())
check("...and it is not the same name twice in a row",
      win._call_event_name() == win._call_key)
check("the password watcher is left exactly where it was",
      B.PW_WORLD_ID != B.APP_WORLD_ID and B.PW_WORLD_ID != B.MAIN_WORLD_ID)

# ---------------------------------------------------------------- (11)
print("\n(11) the way out")
win._call_report(key, 1)
check("a call is on as the browser is asked to quit", FLAG.exists())
app.aboutToQuit.emit()
app.processEvents()
check("quitting takes the flag down", not FLAG.exists())
check("...and it stays down", not FLAG.exists() and B._call_flag_raised is False)

print("\n%d checks failed" % len(FAILS))
for name in FAILS:
    print("  - " + name)
sys.exit(1 if FAILS else 0)
