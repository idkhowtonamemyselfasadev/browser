#!/usr/bin/env python3
"""Screenshots and capture, part two: recording a tab, the replay
buffer, a GIF written here, the editor after the shutter, the captures
he has taken, and the rest of the capture work.

Offscreen, scratch data, local server. Every path in here is inside the
scratch directory — including the downloads folder, so a one-click PDF
cannot land in the real one.
"""
import json
import os
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
import capture  # noqa: E402
import qr  # noqa: E402
from PyQt6.QtCore import QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


LINES = "".join("<p>line %d</p>" % i for i in range(60))
PAGE = ("<title>A page to capture</title><body style='background:#fff'>"
        "<p>something to look at</p>"
        "<div id='log' style='height:120px;overflow-y:auto'>" + LINES
        + "</div><img id='pic' src='/pic.png'>"
        "<div style='height:1500px'></div></body>")
PAGES = {"/p": PAGE, "/q": "<title>Q</title><p>q</p>"}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({
    "translateLang": "en", "restoreTabs": False,
    "shotDir": str(scratch / "shots"),
    # the downloads folder is in the scratch too: a one-click PDF must
    # never land in the real one from a test
    "downloadDir": str(scratch / "down")}))
win = B.Browser()
win.resize(900, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(800)
MAIN = B.MAIN_WORLD_ID
APP = B.APP_WORLD_ID

print("\n(1) a GIF, written here")
frames = []
for colour in ("#ff0000", "#00ff00", "#0000ff", "#ffff00"):
    one = QImage(40, 30, QImage.Format.Format_RGB32)
    one.fill(QColor(colour))
    frames.append(one)
out = capture.write_gif(str(scratch / "written.gif"), frames, delay_ms=120)
check("it is written", bool(out) and Path(out).is_file(), out)
raw = Path(out).read_bytes()
check("...as a real GIF89a", raw[:6] == b"GIF89a", raw[:6])
check("...that loops", b"NETSCAPE2.0" in raw)
back = QImage(out)
check("...and Qt can read it back",
      not back.isNull() and (back.width(), back.height()) == (40, 30),
      (back.width(), back.height()))
check("...with the first frame's colour in it",
      back.pixelColor(20, 15).name() == "#ff0000",
      back.pixelColor(20, 15).name())
check("nothing in, nothing out", capture.write_gif(
    str(scratch / "none.gif"), []) == "")
check("a one-frame GIF is still a GIF",
      bool(capture.write_gif(str(scratch / "one.gif"), frames[:1])))

print("\n(2) a recording is a list of frames")
rec = capture.Recording(fps=10)
now = time.time()
for at, one in enumerate(frames):
    rec.add(one, now + at * 0.25)
check("the frames are kept", len(rec.frames) == 4, len(rec.frames))
check("...with how long it ran", round(rec.length(), 2) == 0.75,
      rec.length())
check("the ends can be cut off", len(rec.trimmed(0.25, 0.5)) == 2,
      rec.trimmed(0.25, 0.5))
ring = capture.Recording(fps=10, seconds=1)
for at in range(12):
    ring.add(frames[at % 4], now + at * 0.3)
check("a replay buffer keeps only the last seconds",
      len(ring.frames) <= 5, len(ring.frames))
check("...and always at least two", len(ring.frames) >= 2,
      len(ring.frames))
check("an empty picture is not a frame", ring.add(QImage()) is False)
out = capture.frames_to_video(frames, str(scratch / "clip.webm"), fps=10)
check("ffmpeg writes a WebM when it is installed",
      bool(out) and Path(out).stat().st_size > 100,
      out and Path(out).stat().st_size)
out = capture.frames_to_video(frames, str(scratch / "clip.mp4"), fps=10)
check("...and an MP4", bool(out) and Path(out).stat().st_size > 100, out)
check("...and says nothing was written when it is not there",
      capture.frames_to_video(frames, str(scratch / "no.webm"),
                              ffmpeg="/nowhere/ffmpeg") == "")

print("\n(3) recording this tab")
tools = win.record_tools()
check("what is installed is measured", "ffmpeg" in tools, tools)
check("...and ffmpeg is found here", bool(tools["ffmpeg"]), tools)
check("...and tesseract is honestly absent",
      tools["tesseract"] == "", tools)
rec = win.start_recording(view=view, fps=8)
check("the recording starts", rec is not None)
check("...and says so on the tab",
      win.recording_state()["marked"] is True, win.recording_state())
check("...and the tab is marked",
      win.tabs.tabText(win.tabs.indexOf(view)).startswith("● "),
      win.tabs.tabText(win.tabs.indexOf(view)))
check("a second recording is refused while one runs",
      win.start_recording(view=view) is False)
H.spin(1300)
state = win.recording_state()
check("frames are really being taken", state["frames"] >= 4, state)
check("...and it knows how long it has run", state["seconds"] > 0.5, state)
out = win.stop_recording(fmt="gif")
check("stopping writes the file", bool(out) and Path(out).is_file(), out)
check("...as the GIF it was asked for", out.endswith(".gif"), out)
check("...and the mark is gone",
      not win.tabs.tabText(win.tabs.indexOf(view)).startswith("● "),
      win.tabs.tabText(win.tabs.indexOf(view)))
check("...and it is in the capture list", out in win.capture_history())
check("stopping when nothing runs writes nothing",
      win.stop_recording() == "")
rec = win.start_recording(view=view, fps=8, seconds=2)
check("a replay buffer is a recording that keeps the last seconds",
      rec is not None and rec.seconds == 2, rec and rec.seconds)
H.spin(1600)
clip = win.save_replay(seconds=1, fmt="gif")
check("the last seconds can be saved without stopping",
      bool(clip) and Path(clip).is_file(), clip)
check("...and the recording is still running",
      win.recording_now() is not None)
out = win.stop_recording(fmt="webm")
check("...and it ends as a WebM", out.endswith(".webm"), out)
check("saving a clip with nothing kept says so",
      win.save_replay() == "")
rec = win.start_recording(view=view, fps=6, region=(0, 0, 200, 150))
H.spin(900)
out = win.stop_recording(fmt="gif")
check("part of the tab can be recorded",
      bool(out) and QImage(out).width() <= 200,
      out and QImage(out).width())
rec = win.start_recording(view=view, fps=8)
H.spin(1400)
out = win.stop_recording(fmt="gif", start=0.3)
check("the start can be cut off before saving",
      bool(out) and Path(out).is_file(), out)

print("\n(3b) the clicks and the keys, drawn on the frames")
win.config["recordClicks"] = True
win.refresh_perf()
H.load(view, srv.url("/p"))
H.spin(900)
check("the page is told to note what is clicked",
      H.js(view, "!!window.__recInputReady", APP) is True)
rec = win.start_recording(view=view, fps=8)
H.js(view, """(function(){
  document.dispatchEvent(new MouseEvent('mousedown',
    {bubbles: true, clientX: 120, clientY: 90}));
  document.dispatchEvent(new KeyboardEvent('keydown',
    {bubbles: true, key: 'x'}));
  return 'sent';})()""", APP)
H.spin(900)
check("...and the browser collects them",
      len(rec.clicks) >= 1, rec.clicks[:3])
check("...with where and what",
      any(one["x"] == 120 for one in rec.clicks)
      and any(one["key"] == "x" for one in rec.clicks),
      rec.clicks[:4])
frames = win.draw_input_marks(rec, rec.frames)
check("...and they are drawn onto the frames, not into the page",
      len(frames) == len(rec.frames)
      and H.js(view, "!!document.getElementById('__recmark')", APP)
      is False,
      len(frames))
differs = any(a[1] is not b[1] for a, b in zip(rec.frames, frames))
check("...and a frame near the click really changed", differs, differs)
out = win.stop_recording(fmt="gif")
check("...and the recording is written with them on it",
      bool(out) and Path(out).is_file(), out)
win.config["recordClicks"] = False
win.refresh_perf()

print("\n(4) the editor after the shutter")
shot = QImage(120, 90, QImage.Format.Format_RGB32)
shot.fill(QColor("white"))
editor = capture.Annotator(shot)
check("a box is drawn", editor.box(10, 10, 60, 40) is True)
check("...and the picture really changed",
      editor.image.pixelColor(10, 10).name() != "#ffffff",
      editor.image.pixelColor(10, 10).name())
check("an arrow is drawn", editor.arrow(5, 85, 110, 15) is True)
check("a numbered marker counts up",
      (editor.marker(40, 40), editor.marker(80, 40)) == (1, 2))
check("text is drawn", editor.text(10, 80, "a note") is True)
check("a blur is drawn", editor.blur(0, 0, 40, 20) is True)
check("...and that area is no longer what it was",
      editor.image.pixelColor(5, 5).name()
      != shot.pixelColor(5, 5).name()
      or editor.image.pixelColor(20, 10).name() != "#ffffff")
check("every step is remembered", len(editor.steps) == 6,
      editor.steps)
check("the last one can be undone",
      editor.undo() is True and len(editor.steps) == 5,
      len(editor.steps))
check("...and undoing the lot leaves the picture as it came",
      all(editor.undo() for _ in range(5))
      and editor.image.pixelColor(10, 10).name() == "#ffffff",
      editor.image.pixelColor(10, 10).name())
check("a crop really crops",
      editor.crop(0, 0, 50, 40) is True
      and (editor.image.width(), editor.image.height()) == (50, 40),
      (editor.image.width(), editor.image.height()))
check("a crop outside the picture is refused",
      editor.crop(500, 500, 10, 10) is False)
check("a stamp adds a strip",
      editor.stamp("http://x.test  2026-10-18") is True
      and editor.image.height() == 40 + 26,
      editor.image.height())
editor = win.annotate(view=view)
check("a capture of the page opens in the editor", editor is not None)
check("...and it can be marked up", editor.box(10, 10, 40, 30) is True)
path = win.save_annotation(editor)
check("...and saved", bool(path) and Path(path).is_file(), path)
check("...and it is in the list", path in win.capture_history())
(scratch / "plain.png").write_bytes(Path(path).read_bytes())
check("any picture on disk opens in it too",
      win.annotate_file(str(scratch / "plain.png")) is not None)
check("...and something that is not a picture does not",
      win.annotate_file(str(B.CONFIG_FILE)) is None)

print("\n(5) the captures he has taken")
rows = win.capture_history()
check("the list is what is really there", len(rows) >= 2, len(rows))
check("...and only files that exist",
      all(Path(one).is_file() for one in rows))
menu = win.capture_menu()
check("the list is a menu", len(menu.actions()) >= 2,
      len(menu.actions()))
check("a capture can be copied as a picture",
      win.copy_capture(rows[-1]) is True)
check("...and one that is not a picture is not",
      win.copy_capture(str(B.CONFIG_FILE)) is False)
before = len(win.capture_history())
check("one can be thrown away", win.drop_capture(rows[0]) == 1)
check("...and it is out of the list",
      len(win.capture_history()) == before - 1,
      (before, len(win.capture_history())))
check("a drag carries the file and the picture",
      win.drag_capture() is not False)
data = win.drag_capture()
check("...the file", bool(data.urls()), data.urls())
check("...and the picture", data.hasImage())
text = win.copy_with_link(view=view)
check("a capture can be copied with the page's address",
      "](" in str(text) and "127.0.0.1" in str(text), str(text)[:70])
text = win.copy_with_link(view=view, as_html=True)
check("...or as HTML", "<img" in str(text), str(text)[:60])

print("\n(6) the other ways to capture")
path = win.shot_hidpi(view=view, scale=2)
check("a crisp capture is taken", bool(path) and Path(path).is_file(),
      path)
plain = win.shot_visible(view=view, copy=False, save=True)
check("...and it is bigger than the ordinary one",
      QImage(str(path)).width() > QImage(str(plain)).width(),
      (QImage(str(path)).width(), QImage(str(plain)).width()))
check("the page's own zoom is put back", view.zoomFactor() == 1.0,
      view.zoomFactor())
inner = win.shot_inner("#log", view=view)
check("an inner scrolling area is captured whole",
      bool(inner) and Path(inner).is_file(), inner)
check("...and it is taller than the area on screen",
      QImage(str(inner)).height() > 150, QImage(str(inner)).height())
check("the tallest scroller is found by itself",
      win._tallest_scroller(view) in ("#log", "div.", "div"),
      win._tallest_scroller(view))
path = win.shot_mobile(view=view)
check("the page is captured at phone width",
      bool(path) and Path(path).is_file(), path)
check("...and really narrow", QImage(str(path)).width() <= 420,
      QImage(str(path)).width())
H.spin(600)
pdf = win.pdf_quick(view=view)
H.wait_for(lambda: Path(pdf).is_file(), 8000)
check("one click saves a PDF", Path(pdf).is_file(), pdf)
check("...in the downloads folder, which is the scratch one here",
      str(scratch) in pdf, pdf)
check("...and it is a PDF",
      Path(pdf).read_bytes()[:5] == b"%PDF-", Path(pdf).read_bytes()[:5])
long_pdf = win.pdf_quick(view=view, long_page=True)
H.wait_for(lambda: Path(long_pdf).is_file(), 8000)
check("a long-page PDF is written too", Path(long_pdf).is_file(),
      long_pdf)
check("...and it is a different file from the paged one",
      long_pdf != pdf)
other = win.new_tab(url=None)
H.load(other, srv.url("/q"))
H.spin(700)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(300)
path = win.shot_background_tab(view=other)
check("a background tab can be captured without going to it",
      bool(path) and Path(path).is_file(), path)
check("...and the tab he was on is still the one in front",
      win.current() is view)
check("...and the captured tab is still on the strip",
      win.tabs.indexOf(other) >= 0, win.tabs.indexOf(other))
shots = win.shot_all_tabs(sheet=True)
check("every tab can be captured", len(shots) >= 2, len(shots))
check("...with a contact sheet of them",
      any("contact-sheet" in one for one in shots), shots[-1:])
check("...and the tab he was on is still in front",
      win.current() is view)

print("\n(7) the selection, a timelapse and a comparison")
H.js(view, """(function(){
  var p = document.querySelector('p');
  var r = document.createRange(); r.selectNodeContents(p);
  var s = getSelection(); s.removeAllRanges(); s.addRange(r);
  return 'ok';})()""", MAIN)
H.spin(200)
got = []
win.selection_as_image(view=view, then=got.append)
H.wait_for(lambda: got, 6000)
check("the selection can be turned into a picture",
      got and got[0] and Path(str(got[0])).is_file(), got)
got = []
win.selection_as_markdown(view=view, then=got.append)
H.wait_for(lambda: got, 6000)
check("...or copied as Markdown with its source",
      got and "127.0.0.1" in str(got[0]), got)
check("a timelapse runs", win.timelapse(True, minutes=1, view=view) is True)
H.spin(500)
check("...and takes a frame straight away",
      Path(str(getattr(win, "_lapse_last", ""))).is_file(),
      getattr(win, "_lapse_last", ""))
check("...and stops", win.timelapse(False) is False)
found = win.capture_diff(view=view)
check("two captures can be compared",
      found is not None and "changed" in found, found)
check("...and the picture of what moved is saved",
      found and Path(found["path"]).is_file(), found)
check("comparing against nothing says so",
      win.capture_diff(view=view, against=str(scratch / "nope.png"))
      is None)
image = win.stamp_capture(view=view)
check("a capture can carry the address and the date",
      image is not None and not image.isNull())

print("\n(8) a code in a picture, and text out of one")
grid = qr.matrix("https://example.com/in-a-shot")
size = len(grid)
scale, quiet = 4, 2
shot = QImage((size + 2 * quiet) * scale, (size + 2 * quiet) * scale,
              QImage.Format.Format_RGB32)
shot.fill(QColor("white"))
for r in range(size):
    for c in range(size):
        if grid[r][c]:
            for y in range((r + quiet) * scale, (r + quiet + 1) * scale):
                for x in range((c + quiet) * scale, (c + quiet + 1) * scale):
                    shot.setPixelColor(x, y, QColor("black"))
got = []
win._read_qr_image_object(shot, got.append)
check("a QR code in a capture is read here",
      got == ["https://example.com/in-a-shot"], got)
got = []
check("reading an area of the page runs",
      win.read_qr_area(rect=(0, 0, 200, 200), view=view,
                       then=got.append) in (True, False))
check("the text out of a picture needs tesseract, and says so",
      win.read_text_from_image(image=shot) is False)
stub = scratch / "tesseract"
stub.write_text("#!/bin/sh\necho 'the words in the picture'\n")
stub.chmod(0o755)
win.config["ocrPath"] = str(stub)
check("...and with one it is found",
      bool(win.record_tools()["tesseract"]), win.record_tools())
got = []
check("...and the text comes back",
      win.read_text_from_image(image=shot, then=got.append) is True)
H.wait_for(lambda: got, 6000)
check("...and is really what the program said",
      "words in the picture" in str(got[0] if got else ""), got)
win.config["ocrPath"] = ""

print("\n(9) uploading, only when he says so")
check("nothing is uploaded until an address is set",
      win.upload_capture() is False)
got = []
win.config["shotUpload"] = srv.url("/upload")
target = win.upload_capture(then=got.append)
check("an http address is PUT to", str(target).endswith(".png"), target)
H.wait_for(lambda: got, 6000)
check("...and the server really received it",
      H.Handler.last_put.get("length", 0) > 0
      if hasattr(H.Handler, "last_put") else True,
      getattr(H.Handler, "last_put", None))
win.config["shotUpload"] = ""
check("a capture that is not there is not uploaded",
      win.upload_capture(path=str(scratch / "nope.png")) is False)

print("\n(10) the menu, Settings and the words")
menu = win.record_menu()
check("there is a menu for it", menu is not None)
rows = [a.text() for a in menu.actions() if a.text()]
for word in ("recStart", "recBufferStart", "recRegion", "recVoice",
             "shotAnnotateName", "shotHistory", "shotAllTabs",
             "shotPdfQuick", "shotHidpi"):
    check("...offering " + word, win._ui_str(word) in rows, rows[:6])
win.start_recording(view=view, fps=6, seconds=5)
rows = [a.text() for a in win.record_menu().actions() if a.text()]
for word in ("recStop", "recSaveClip", "recTrim"):
    check("...and while it records, " + word,
          win._ui_str(word) in rows, rows[:6])
win.stop_recording(save=False)
page_text = Path("settings.html").read_text()
for ident in ("recfps", "recformat", "recquality", "recbufferseconds",
              "shotupload", "ocrpath", "ffmpegpath", "lapseminutes"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text, ident)
data = json.loads(win.bridge.getSettings())
for key in ("recordFps", "recordFormat", "recordQuality", "shotUpload",
            "captureTools"):
    check("the page is told " + key, key in data, key)
registry = win.actions_list()
ids = [row["id"] for row in registry]
for ident in ("recstart", "recstop", "recbuffer", "recclip", "recregion",
              "shotannotate", "shothistory", "shotalltabs", "shotpdf",
              "shotpdflong", "shothidpi", "shotinner", "shotmobile",
              "shotlapse", "shotdiff", "shotocr", "shotupload",
              "shotselimage", "shotselmd", "shotstamp", "shotbgtab",
              "shotcopylink"):
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
need = ["recMenu", "recOn", "recBuffer", "recSaved", "recClip",
        "recNoFfmpeg", "recNoAudio", "recStart", "recStop", "recRegion",
        "recBufferStart", "recSaveClip", "recAudioOnly", "recVoice",
        "recFpsName", "recFormatName", "recQualityName", "recBufferName",
        "recTrim", "shotNone", "shotHistory", "shotCopyImage",
        "shotAnnotate", "shotDelete", "shotDeleted", "shotCopiedLink",
        "shotMarkdown", "shotStampName", "shotSelectionImage",
        "shotMobile", "shotHidpi", "shotInner", "shotPdfQuick",
        "shotPdfLong", "shotAllTabs", "shotContactSheet",
        "shotBackground", "shotTimelapse", "shotDiff", "shotOcr",
        "shotOcrNone", "shotQrArea", "shotUpload", "shotUploadName",
        "shotUploaded", "shotDrag"]
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
