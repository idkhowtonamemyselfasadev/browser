#!/usr/bin/env python3
"""Process-lifecycle safety: single instance, hand-off, crash detection.

The bugs this guards against were live in the field and were costing
real data and sanity:

 * a `kill -9` cleanup left a stale single-instance socket, and the next
   launch would not reclaim it -- it must, when the owner is gone;
 * a busy primary missed the old 300ms probe, so a relaunch removed the
   socket unconditionally and became a SECOND browser on the same
   profile, whereupon new tabs rendered blank and took no input. A live
   instance must never be displaced;
 * `--background` (the `music` command) became a window-owning primary
   instead of handing its URL to the running browser as a quiet tab;
 * a second launch read the still-set "runOpen" flag as a crash and wiped
   history/cookies out from under the healthy first instance. Crash
   detection is now pid + start-time based: a live owner is not a crash.

All offscreen, against scratch data; the real vault and config are never
opened. No page is loaded to completion, so nothing here depends on the
network or on QtWebEngine finishing a load.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")


def dead_pid():
    """A pid that is certainly not alive: a child we already reaped."""
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


# ---------------------------------------------------------------------
print("(1) _proc_start_time reads a real start-time and refuses a ghost")
import os  # noqa: E402
mine = B._proc_start_time(os.getpid())
check("our own start-time is a positive integer", isinstance(mine, int)
      and mine > 0, mine)
dp = dead_pid()
check("a dead pid has no readable start-time (None)",
      B._proc_start_time(dp) is None, B._proc_start_time(dp))

# ---------------------------------------------------------------------
print("\n(2) _run_was_crash: only a dead owner is a crash")
check("no marker at all is not a crash", B._run_was_crash(None) is False)
check("a clean-exit False is not a crash", B._run_was_crash(False) is False)
check("a legacy bare-True is not treated as a crash (safety: no wipe)",
      B._run_was_crash(True) is False)
check("a marker whose process is gone IS a crash",
      B._run_was_crash({"pid": dp, "start": 123}) is True)
check("a marker for a process still alive (same start) is NOT a crash",
      B._run_was_crash({"pid": os.getpid(), "start": mine}) is False)
check("a marker for a recycled pid (alive, different start) IS a crash",
      B._run_was_crash({"pid": os.getpid(), "start": mine + 1}) is True)
check("a marker with no usable pid is not a crash",
      B._run_was_crash({"start": 5}) is False)

# ---------------------------------------------------------------------
print("\n(3) single-instance hand-off never displaces a live owner")
name = "browser-shot-life-%d" % os.getpid()
B.SINGLE_INSTANCE_SOCKET = name
QLocalServer.removeServer(name)

# nobody home: a hand-off attempt fails cleanly (does NOT remove anything)
check("hand-off to a socket that nobody owns returns False",
      B._handoff_to_existing(False, None) is False)

got = []


def wire(server):
    def on_conn():
        conn = server.nextPendingConnection()
        if conn is None:
            return
        if conn.waitForReadyRead(1500):
            got.append(bytes(conn.readAll()).decode())
    server.newConnection.connect(on_conn)


primary = QLocalServer()
listened = primary.listen(name)
check("a fresh primary can listen on the socket", listened, primary.errorString())
full_path = primary.fullServerName()
wire(primary)

check("a plain relaunch hands a URL to the live primary",
      B._handoff_to_existing(False, "https://relaunch.example/") is True)
app.processEvents()
time.sleep(0.05)
app.processEvents()
check("the primary received exactly that URL",
      got and got[-1] == "https://relaunch.example/", got)

check("--background hands off too, marked as a background tab",
      B._handoff_to_existing(True, "https://music.example/") is True)
app.processEvents(); time.sleep(0.05); app.processEvents()
check("the primary received a 'bg ' prefixed message",
      got and got[-1] == "bg https://music.example/", got)

check("a bare relaunch with no URL asks only to be raised",
      B._handoff_to_existing(False, None) is True)
app.processEvents(); time.sleep(0.05); app.processEvents()
check("the primary received 'raise'", got and got[-1] == "raise", got)

# a live owner is never displaced: a rival cannot listen on the same name
rival = QLocalServer()
check("a second listen() on a live socket is refused (owner not orphaned)",
      rival.listen(name) is False, rival.errorString())

# ---------------------------------------------------------------------
print("\n(4) a stale socket left by a killed owner is reclaimed")
primary.close()                 # the owner 'dies'
# leave a stale leftover where the socket file was, as a kill -9 would
try:
    Path(full_path).touch()
except OSError:
    pass
reclaim = QLocalServer()
first = reclaim.listen(name)
if not first:
    # the name looks taken (stale file). Nobody answers it...
    check("nobody answers the stale socket",
          B._handoff_to_existing(False, None) is False)
    QLocalServer.removeServer(name)
    first = reclaim.listen(name)
check("after the owner is gone, a new launch owns the socket", first,
      reclaim.errorString())
reclaim.close()
QLocalServer.removeServer(name)

# ---------------------------------------------------------------------
print("\n(5) a genuine crash of the previous run wipes as configured")
cfg = SCRATCH / "config.json"
hist = SCRATCH / "history.json"
B.CONFIG_FILE = cfg
B.HISTORY_FILE = hist
cfg.write_text(json.dumps({
    "vaultPassword": True,
    "clearHistoryExit": True,
    # marker points at a process that is gone -> a real crash
    "runOpen": {"pid": dp, "start": 999},
}))
hist.write_text(json.dumps([{"url": "https://old.example/", "title": "old"}]))
win = B.Browser()
win.show()
app.processEvents()
check("history from a crashed run with clear-on-exit is wiped",
      win.history == [], win.history)
marker = win.config.get("runOpen")
check("this run records a pid+start marker of its own",
      isinstance(marker, dict) and marker.get("pid") == os.getpid(), marker)
check("and the marker carries a start-time", marker.get("start") is not None
      if isinstance(marker, dict) else False, marker)

# ---------------------------------------------------------------------
print("\n(6) a still-alive owner (concurrent launch) does NOT wipe history")
cfg.write_text(json.dumps({
    "vaultPassword": True,
    "clearHistoryExit": True,
    # marker points at a process that is very much alive: us
    "runOpen": {"pid": os.getpid(), "start": mine},
}))
hist.write_text(json.dumps([{"url": "https://keep.example/", "title": "keep"}]))
win2 = B.Browser()
win2.show()
app.processEvents()
check("history is preserved when the previous owner is still running",
      win2.history == [{"url": "https://keep.example/", "title": "keep"}],
      win2.history)

# ---------------------------------------------------------------------
print("\n(7) _handoff_message: a URL-less message opens no spare tab")
base = win2.tabs.count()
win2._handoff_message("raise")
app.processEvents()
check("'raise' opens no tab", win2.tabs.count() == base, win2.tabs.count())
win2._handoff_message("bg ")
app.processEvents()
check("a bare 'bg' opens no tab", win2.tabs.count() == base, win2.tabs.count())
win2._handoff_message("%u")
app.processEvents()
check("an unsubstituted %u opens no tab",
      win2.tabs.count() == base, win2.tabs.count())

print("\n(8) _handoff_message: a real URL opens a tab; 'bg' stays behind")
win2._handoff_message("https://front.example/")
app.processEvents()
check("a plain URL adds a tab", win2.tabs.count() == base + 1,
      win2.tabs.count())
check("and it is switched to (foreground)",
      win2.current() is win2.tabs.widget(win2.tabs.count() - 1))
cur_before = win2.tabs.currentIndex()
win2._handoff_message("bg https://ghost.example/")
app.processEvents()
check("a 'bg' URL adds a tab too", win2.tabs.count() == base + 2,
      win2.tabs.count())
check("but does NOT steal the current tab (stays where he was)",
      win2.tabs.currentIndex() == cur_before, win2.tabs.currentIndex())

print("\n(9) the music/autoplay hand-off tab is playable, not throttled")
# The `music` command hands "bg <amazon-music-url>#autoplay" to the running
# browser. A background tab sits on a hidden page, which Chromium treats as
# hidden -> autoplay refused, media throttled: after the lifecycle fix that
# is exactly why music stopped playing. The fix keeps the #autoplay tab's
# page visible + Active so it can start, WITHOUT switching to it (no focus
# steal) and WITHOUT raising or becoming a second instance.
check("a URL with the #autoplay marker is recognised",
      B._wants_autoplay("https://music.example/#autoplay") is True)
check("a plain URL is not autoplay", B._wants_autoplay("https://x.example/")
      is False)

base = win2.tabs.count()
cur = win2.tabs.currentIndex()
win2._handoff_message("bg https://music.example/my/playlists#autoplay")
app.processEvents(); time.sleep(0.1); app.processEvents()
music = win2.tabs.widget(win2.tabs.count() - 1)
check("the music hand-off opened a tab", win2.tabs.count() == base + 1,
      win2.tabs.count())
check("it did NOT steal the current tab (no focus steal)",
      win2.tabs.currentIndex() == cur, win2.tabs.currentIndex())
check("its page is kept visible so Chromium lets it start playing",
      music.page().isVisible() is True, music.page().isVisible())
check("its page is pinned Active (never frozen/discarded under us)",
      music.page().lifecycleState()
      == B.QWebEnginePage.LifecycleState.Active,
      music.page().lifecycleState())
check("and it is marked to stay playable across in-app navigations",
      getattr(music, "_keep_playing", False) is True)

# scoped: an ordinary background tab (no #autoplay) is left hidden, so the
# throttle-avoidance is only for the music tab, not every bg tab
cur2 = win2.tabs.currentIndex()
win2._handoff_message("bg https://plain.example/")
app.processEvents(); time.sleep(0.1); app.processEvents()
plain = win2.tabs.widget(win2.tabs.count() - 1)
check("a plain background tab is NOT force-woken (stays a normal bg tab)",
      plain.page().isVisible() is False
      and getattr(plain, "_keep_playing", False) is False,
      (plain.page().isVisible(), getattr(plain, "_keep_playing", False)))
check("the plain bg tab did not steal focus either",
      win2.tabs.currentIndex() == cur2, win2.tabs.currentIndex())

# and none of this created a rival primary: the music tab is a TAB on the
# existing window, not a second window/instance. (The single-instance
# socket guarantee itself is proven in sections 3-4; the fix here adds
# only page visibility and never touches the primary-election path.)
check("the music tab lives on the existing window, not a new instance",
      win2.tabs.widget(win2.tabs.indexOf(music)) is music
      and music.window() is win2)

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
