#!/usr/bin/env python3
"""The video and the sound, part two: what a video looks like, what it
sounds like, what it says about itself, and the rules per site.

Offscreen, scratch data, local media. The video is a tiny generated
file served by the harness, so everything here is a real <video>
element with a real duration."""
import base64
import json
import os
import shutil
import sys
import time
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


# A page with a video element that has a duration and a caption track,
# without needing a real codec: the element answers every question the
# tools ask of it, and the ones that need decoded frames say so.
VIDEO_PAGE = """<title>Video</title>
  <video id=v width=320 height=180 controls>
    <track id=t kind=subtitles srclang=en label=English
           src="/subs.vtt" default>
  </video>
  <div id=description>
    Chapters:
    0:00 the start
    1:30 the middle
    12:05 the end
  </div>
  <iframe id=embed width=320 height=180
          src="https://www.youtube.com/embed/abc123"></iframe>
  <a href="/clip.mp4">a clip</a>
  <a href="/song.mp3">a song</a>
  <script>
    // a duration and a position without a codec: the tools read these
    // properties, and a fake one is still a real property
    var v = document.getElementById('v');
    Object.defineProperty(v, 'duration', {get: function(){ return 600; }});
    Object.defineProperty(v, 'videoWidth', {get: function(){ return 1920; }});
    Object.defineProperty(v, 'videoHeight', {get: function(){ return 1080; }});
    var at = 120;
    Object.defineProperty(v, 'currentTime',
      {get: function(){ return at; }, set: function(x){ at = x; }});
    Object.defineProperty(v, 'paused', {get: function(){ return false; }});
  </script>"""

SUBS = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
the first line

2
00:00:04.000 --> 00:00:06.000
the second line
"""

PAGES = {
    "/v": VIDEO_PAGE,
    "/subs.vtt": SUBS,
    "/plain": "<title>Plain</title><p>no media here</p>",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
scratch = B.CONFIG_FILE.parent


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(400)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


def ask(tool, view, arg=None, wait=5000):
    got = []
    win.media_tool2(tool, view=view, then=got.append, arg=arg)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


print("\n(1) subtitles in and out")
check("an srt time is written the way an srt writes it",
      B._srt_time(62.5) == "00:01:02,500", B._srt_time(62.5))
check("and a round second has no stray milliseconds",
      B._srt_time(3600) == "01:00:00,000", B._srt_time(3600))
vtt = B._srt_to_vtt("1\n00:00:01,000 --> 00:00:03,000\nhello\n")
check("an srt becomes WebVTT", vtt.startswith("WEBVTT"), vtt[:20])
check("...with the full stop the engine wants",
      "00:00:01.000 --> 00:00:03.000" in vtt, vtt)

print("\n(2) what the video is")
view = page("/v")
stats = []
win.media_stats(view, then=stats.append)
H.wait_for(lambda: stats, 5000)
got = stats[0] if stats else {}
check("its size is read off the element",
      got.get("width") == 1920 and got.get("height") == 1080, got)
check("so is where it is", got.get("at") == 120, got)
check("and how long it is", got.get("duration") == 600, got)
check("and that it has a caption track", got.get("tracks", 0) >= 1, got)
ends = []
win.media_ends_at(view, then=ends.append)
H.wait_for(lambda: ends, 5000)
check("when it ends is worked out from what is left",
      ends and ends[0] and ends[0]["left"] == 480, ends)
check("...and said as a clock time", ends and ":" in ends[0]["at"], ends)

print("\n(3) how the picture looks")
answer = ask("filters", view, {"brightness": 1.3})
check("a filter is put on the video", answer and "1.3" in answer, answer)
check("and the element really has it",
      "brightness(1.3)" in str(js(view, "document.getElementById('v')"
                                  ".style.filter") or ""),
      js(view, "document.getElementById('v').style.filter"))
ask("filters", view, {"brightness": 1, "contrast": 1, "saturate": 1})
check("back to normal is a filter too",
      "brightness(1)" in str(js(view, "document.getElementById('v')"
                                ".style.filter") or ""))
answer = ask("turn", view, {"by": 90})
check("a quarter turn is remembered as 90", answer and '"deg": 90' in
      answer.replace('"deg":90', '"deg": 90'), answer)
check("and the element is turned",
      "rotate(90deg)" in str(js(view, "document.getElementById('v')"
                                ".style.transform") or ""),
      js(view, "document.getElementById('v').style.transform"))
answer = ask("turn", view, {"flip": True})
check("mirroring is on top of the turn",
      "scaleX(-1)" in str(js(view, "document.getElementById('v')"
                             ".style.transform") or ""),
      js(view, "document.getElementById('v').style.transform"))
ask("turn", view, {"reset": True})
check("straightening clears both",
      "rotate(0deg)" in str(js(view, "document.getElementById('v')"
                               ".style.transform") or ""))
answer = ask("zoom", view, {"by": 0.5})
check("zooming scales it", "scale(1.5)" in str(
    js(view, "document.getElementById('v').style.transform") or ""),
      js(view, "document.getElementById('v').style.transform"))
ask("zoom", view, {"crop": True})
check("and cropping fills the box",
      js(view, "document.getElementById('v').style.objectFit") == "cover",
      js(view, "document.getElementById('v').style.objectFit"))
ask("zoom", view, {"reset": True})
check("the cursor can be hidden over a video",
      ask("hidecursor", view) in ("on", "already"))

print("\n(4) where he was")
win.config["mediaResume"] = True
win.config["mediaPlaces"] = {}
win.note_media_place(view)
H.wait_for(lambda: win.media_places(), 4000)
places = win.media_places()
check("how far in he got is written down",
      any(row.get("at") == 120 for row in places.values()), places)
check("with the video's own title",
      any(row.get("title") for row in places.values()), places)
js(view, "document.getElementById('v').currentTime = 0")
check("resuming puts him back", win.resume_media(view))
H.wait_for(lambda: int(js(view, "document.getElementById('v')"
                          ".currentTime") or 0) > 100, 4000)
check("...and it really did",
      int(js(view, "document.getElementById('v').currentTime") or 0) == 120,
      js(view, "document.getElementById('v').currentTime"))
rows = win.media_history()
check("the history has the video", rows and rows[0]["at"] == 120, rows[:1])
menu = win.media_history_menu()
check("and a menu to go back to it",
      len([a for a in menu.actions() if a.text()]) >= 2,
      [a.text() for a in menu.actions()])
check("which can be forgotten", win.clear_media_history() >= 1
      and win.media_places() == {})
plain = page("/plain")
win.note_media_place(plain)
H.spin(400)
check("a page with no video writes nothing down", win.media_places() == {})

print("\n(5) captions")
answer = ask("captions", view)
check("captions can be switched", answer in ("on", "off"), answer)
answer = ask("captions", view, {"lang": "en"})
check("and a language can be asked for", answer == "on", answer)
rows = []
win.transcript(view, then=rows.append)
H.wait_for(lambda: rows, 5000)
check("the transcript comes out of the track",
      rows and rows[0] and len(rows[0]) == 2, rows[:1])
check("with the times and the words",
      rows[0][0]["t"] == 1 and "first line" in rows[0][0]["text"],
      rows[0][:1])
path = win.save_subtitles(rows[0])
check("and it can be written out as an srt",
      path and Path(path).exists(), path)
text = Path(path).read_text() if path else ""
check("...in the srt format", "00:00:01,000 --> 00:00:03,000" in text,
      text[:60])
win.config.update({"capSize": 150, "capColour": "#ffff00",
                   "capBack": "none", "capBottom": 60})
css = win.caption_style_css()
check("his caption style becomes a cue rule",
      "::cue" in css and "150%" in css and "#ffff00" in css, css[:90])
check("and lifting them is a rule of its own",
      "bottom: 60px" in css, css)
check("the page is given it", win.apply_caption_style(view))
H.spin(200)
check("...really given it",
      "150%" in str(js(view, """(function(){var s=
       document.getElementById('media-cue-style');
       return s ? s.textContent : '';})()""") or ""),
      js(view, """(function(){var s=
       document.getElementById('media-cue-style');
       return s ? s.textContent : '';})()"""))
win.config.update({"capSize": 0, "capColour": "", "capBack": "",
                   "capBottom": 0})
check("with nothing set there is no rule at all",
      win.caption_style_css() == "")
subs = scratch / "mine.srt"
subs.write_text("1\n00:00:02,000 --> 00:00:04,000\nfrom a file\n")
check("subtitles can be loaded from a file",
      win.load_subtitles(str(subs), view=view) == str(subs))
H.spin(400)
check("...and the track is on the video",
      int(js(view, "document.querySelectorAll('track[data-browser-sub]')"
             ".length") or 0) == 1,
      js(view, "document.querySelectorAll('track').length"))
win.clear_subtitles(view)
H.spin(300)
check("and taken off again",
      int(js(view, "document.querySelectorAll('track[data-browser-sub]')"
             ".length") or 0) == 0)
check("a file that is not there is refused",
      win.load_subtitles(str(scratch / "nope.srt"), view=view) == "")

# The player page's "Subtitles..." button went through bridge.
# playerSubtitles, which browser.py did not have: the call is guarded,
# so clicking it did nothing at all -- no error, no message. The
# picker, the SRT-to-WebVTT conversion and the data: URL were all
# already there behind load_subtitles; only the door from the page was
# missing. These check the door and the step it shares.
import base64 as _b64                                        # noqa: E402
data, chosen = win.subtitle_data_url(str(subs))
check("a subtitle file comes back as a data: URL",
      data.startswith("data:text/vtt;charset=utf-8;base64,"), data[:40])
check("...naming the file it came from", chosen == str(subs), chosen)
decoded = _b64.b64decode(data.split(",", 1)[1]).decode("utf-8")
check("...as WebVTT, because the engine takes nothing else",
      decoded.startswith("WEBVTT"), decoded[:20])
check("...with the comma in the .srt time turned into a full stop",
      "00:00:02.000 --> 00:00:04.000" in decoded,
      decoded.replace("\n", " | ")[:70])
check("...and the line itself is still in it", "from a file" in decoded)
vtt = scratch / "already.vtt"
vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nas is\n")
asis = _b64.b64decode(
    win.subtitle_data_url(str(vtt))[0].split(",", 1)[1]).decode("utf-8")
check("a file that is already WebVTT is not converted twice",
      asis.count("WEBVTT") == 1, asis.count("WEBVTT"))
check("nothing comes back for a file that is not there",
      win.subtitle_data_url(str(scratch / "nope.srt")) == ("", ""))
check("the player page can reach it at last",
      hasattr(win.bridge, "playerSubtitles"))
check("...and it answers the page with the same data: URL",
      win.bridge.playerSubtitles.__doc__ is not None)

print("\n(6) chapters out of the page")
rows = []
win.chapters(view, then=rows.append)
H.wait_for(lambda: rows, 5000)
check("the timestamps become chapters",
      rows and len(rows[0]) == 3, rows[:1])
check("in order, with their seconds",
      rows[0][0]["t"] == 0 and rows[0][1]["t"] == 90
      and rows[0][2]["t"] == 725, [r["t"] for r in rows[0]])
menu = win.chapters_menu(view=view)
H.spin(700)
check("and a menu to jump with",
      len([a for a in menu.actions() if a.text()]) >= 3,
      [a.text() for a in menu.actions()][:3])
ask("seek", view, 90)
check("which really seeks",
      int(js(view, "document.getElementById('v').currentTime") or 0) == 90,
      js(view, "document.getElementById('v').currentTime"))

print("\n(7) the sound")
out = []
win.audio_chain(view=view, then=out.append, level=True)
H.wait_for(lambda: out, 5000)
answer = out[0] if out else None
if answer in ("taken", "noaudio", "none"):
    check("the sound chain says why it could not be built",
          answer in ("taken", "noaudio"), answer)
else:
    check("the chain is built and the limiter is on",
          answer and answer.get("level") is True, answer)
    check("with ten bands", answer and len(answer.get("bands", [])) == 10,
          (answer or {}).get("freqs"))
    out.clear()
    win.audio_chain(view=view, then=out.append, balance=-0.5)
    H.wait_for(lambda: out, 5000)
    check("the balance can be moved",
          out and out[0] and abs(out[0]["balance"] + 0.5) < 0.01, out)
    out.clear()
    win.equaliser("podcast", view=view, then=out.append)
    H.wait_for(lambda: out, 5000)
    check("a preset sets the bands",
          out and out[0] and out[0]["bands"][0] == -6, out)
    out.clear()
    win.audio_chain(view=view, then=out.append, mono=True)
    H.wait_for(lambda: out, 5000)
    check("and a mono downmix", out and out[0] and out[0]["mono"] is True,
          out)
check("the presets are ten numbers each",
      all(len(v) == 10 for v in win.equaliser_presets().values()),
      {k: len(v) for k, v in win.equaliser_presets().items()})
check("an unknown preset is refused", win.equaliser("nonsense") is False)
answer = ask("skipsilence", view)
check("skipping the quiet parts answers one way or the other",
      answer in ("on", "already", "taken", "noaudio"), answer)
# through audio_output, which is the door that reads the answer the
# page stashed (the tool itself can only say that it asked)
sink = []
win.audio_output("", view=view, then=sink.append)
H.wait_for(lambda: sink, 6000)
check("the output device is asked of the element",
      sink and sink[0] in ("ok", "nosink", "refused"), sink)

print("\n(8) the rules per site")
check("no site has an autoplay rule to start with",
      win.autoplay_rule("127.0.0.1") == "default")
check("one can be set", win.autoplay_rule("127.0.0.1", "mute") == "mute")
check("nonsense is not a rule",
      win.autoplay_rule("127.0.0.1", "maybe") == "mute")
muted = page("/v")
H.spin(300)
check("and a muted site's page is muted",
      win.apply_autoplay_rule(muted) == "mute")
H.spin(300)
check("...really muted",
      js(muted, "document.getElementById('v').muted") is True,
      js(muted, "document.getElementById('v').muted"))
check("back to default takes the rule off",
      win.autoplay_rule("127.0.0.1", "default") == "default")
check("a site can be muted for good",
      win.always_mute("127.0.0.1") is True
      and win.site_rule_on("muteSites", "127.0.0.1"))
win.always_mute("127.0.0.1")
check("no site has a quality rule either",
      win.site_quality("127.0.0.1") == "")
win.site_quality("127.0.0.1", "720p")
check("one can be set", win.site_quality("127.0.0.1") == "720p")
win.site_quality("127.0.0.1", "")
check("no site has a microphone of its own",
      win.mic_for_site("127.0.0.1") == "")
win.mic_for_site("127.0.0.1", "device-abc")
check("one can be chosen", win.mic_for_site("127.0.0.1") == "device-abc")
check("and it reaches the guard's own table",
      B.page_guard.rules(win.config)["mics"].get("127.0.0.1")
      == "device-abc",
      B.page_guard.rules(win.config)["mics"])
check("the call settings are three switches",
      win.call_audio_for_site("127.0.0.1", {"noise": False})
      == {"noise": False},
      win.call_audio_for_site("127.0.0.1"))
check("...and they reach the guard too",
      B.page_guard.rules(win.config)["calls"].get("127.0.0.1")
      == {"noise": False},
      B.page_guard.rules(win.config)["calls"])
check("which means the guard is wanted at all",
      B.page_guard.wanted(win.config))
win.mic_for_site("127.0.0.1", "")
win.call_audio_for_site("127.0.0.1", {})

print("\n(9) his microphone in a real page")
win.mic_for_site("127.0.0.1", "device-abc")
win.call_audio_for_site("127.0.0.1", {"noise": False, "gain": True})
win.refresh_guard_scripts()
mic_page = page("/v")
H.spin(300)
asked = js(mic_page, """(function(){
  if (!navigator.mediaDevices) return 'nomd';
  var seen = null;
  navigator.mediaDevices.getUserMedia({audio: true}).catch(function(){});
  return String(navigator.mediaDevices.getUserMedia).indexOf('native') < 0
         ? 'wrapped' : 'native';})()""")
check("getUserMedia is wrapped where he set a microphone",
      asked == "wrapped", asked)
win.mic_for_site("127.0.0.1", "")
win.call_audio_for_site("127.0.0.1", {})
win.refresh_guard_scripts()

print("\n(10) the other tabs, quietened or paused")
win.config["duckLevel"] = 0.2
other = page("/v")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
check("ducking touches the tabs that are making a noise",
      isinstance(win.duck_others(view), int))
win.config["duckLevel"] = 0
check("and does nothing at all when it is off",
      win.duck_others(view) == 0)
win.config["pauseForCalls"] = True
win._media_live = [{"view": other, "kind": "microphone",
                    "title": "call"}]
paused = win.pause_for_call()
check("a call pauses what is playing elsewhere",
      isinstance(paused, int), paused)
check("and the tabs it paused are remembered",
      isinstance(win._paused_for_call, list))
win.resume_after_call()
check("...and played again afterwards", win._paused_for_call == [])
win._media_live = []
win.config["pauseForCalls"] = False
check("with the setting off a call changes nothing",
      win.pause_for_call() == 0)

print("\n(11) embeds and the links on a page")
answer = ask("heldembeds", view)
check("an embedded player is held back",
      int(answer or 0) >= 1, answer)
check("...and its address is kept for the click",
      js(view, "document.getElementById('embed').dataset.heldSrc")
      .startswith("https://www.youtube.com/embed/"),
      js(view, "document.getElementById('embed').dataset.heldSrc"))
check("the placeholder is in the page",
      int(js(view, "document.querySelectorAll('[data-held-by]').length")
          or 0) >= 1,
      js(view, "document.querySelectorAll('[data-held-by]').length"))
rows = []
win.media_links(view, then=rows.append)
H.wait_for(lambda: rows, 5000)
check("every media link is collected",
      rows and len(rows[0]) == 2, rows[:1])
check("with its own title",
      rows and any(r["title"] == "a clip" for r in rows[0]), rows[:1])
menu = win.media_links(view, then=lambda r: None)
check("and a menu is built from them",
      isinstance(win._fill_media_links(B.QMenu(win), rows[0]), B.QMenu))

print("\n(12) audio only, and shorts")
check("sound only hides the video", win.audio_only(True, view) is True)
H.spin(300)
check("...really hides it",
      js(view, "document.getElementById('v').style.visibility") == "hidden",
      js(view, "document.getElementById('v').style.visibility"))
win.audio_only(False, view)
H.spin(200)
check("and brings it back",
      js(view, "document.getElementById('v').style.visibility") != "hidden")
check("a page that is not a short gives no other address",
      ask("shorts", view) == "")

print("\n(13) what the page says is playing")
js(view, """(function(){ if (navigator.mediaSession) {
  navigator.mediaSession.metadata = new MediaMetadata(
    {title: 'A song', artist: 'Someone'});
} })()""")
H.spin(200)
out = []
win.media_session(view, then=out.append)
H.wait_for(lambda: out, 5000)
check("the title and the artist are read",
      out and out[0] and out[0].get("title") == "A song", out)
win.config["trackNotice"] = True
win._audible = view
win._last_track = ""
win._track_tick()
H.spin(500)
check("and the track notice says it once",
      "A song" in str(win._last_track), win._last_track)
before = win._last_track
win._track_tick()
H.spin(300)
check("...and not again for the same track",
      win._last_track == before)
win.config["trackNotice"] = False
win._audible = None
check("with the notice off nothing is polled",
      win._track_tick() is False)

print("\n(14) what a loaded page gets")
win.config.update({"pauseHidden": True, "holdFast": True,
                   "hideCursor": False, "heldEmbeds": False,
                   "spoilerShield": False, "capOn": False,
                   "mediaResume": False, "shortsPlayer": False})
fresh = page("/v")
on = win.media_extras(fresh)
check("only what he switched on is put on the page",
      sorted(on) == ["holdfast", "pausehidden"], on)
win.config.update({"pauseHidden": False, "holdFast": False})
check("and nothing when nothing is on", win.media_extras(page("/v")) == [])

print("\n(15) the menu and the keys")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
menu = win.media_menu2()
labels = [a.text() for a in menu.actions() if a.text()]
check("the media menu is built", len(labels) >= 8, labels)
check("it names this site for the per-site rules",
      any("127.0.0.1" in t for t in labels), labels)
ids = {e["id"] for e in win.actions_list()}
for want in ("media2", "mediastats", "endsat", "captions", "subtitles",
             "transcript", "chapters", "levelaudio", "skipsilence",
             "audioonly", "mpv", "mediahistory"):
    check("the registry knows " + want, want in ids)
check("every action has a name in English",
      all(win.action_label(e) != e["str"] for e in win.actions_list()),
      [e["str"] for e in win.actions_list()
       if win.action_label(e) == e["str"]][:4])
keys = {}
for entry in win.actions_list():
    key = win.shortcut_for(entry["id"], entry["key"])
    if key:
        keys.setdefault(key, []).append(entry["id"])
clash = {k: v for k, v in keys.items() if len(v) > 1}
check("and no two want the same key", not clash, clash)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
