#!/usr/bin/env python3
"""Downloads and files: the record, the file, the archives, the
pictures, and the handoffs to other programs.

Offscreen, scratch data, local server. Every file this makes is made
here, in the scratch folder, so nothing in the real downloads folder is
touched.

Measured rather than assumed, and said in the check: there is no
yt-dlp, no clamscan and no torrent client on this box, and no 3D
printer on this network -- so those four are tested by what the browser
says when the program is missing, plus (for the printer) the request it
builds, against a stand-in in the harness.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QColor  # noqa: E402
from PyQt6.QtWidgets import (QInputDialog, QMessageBox,  # noqa: E402
                             QPlainTextEdit)

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PICTURES = """<title>A gallery</title>
  <img id=big src="/big.png" width=800 height=600>
  <img id=small src="/small.png" width=16 height=16>
  <div id=back style="background-image:url('/back.png');width:10px;
       height:10px"></div>
  <a href="/one.pdf">one</a>
  <a href="/two.pdf">two</a>
  <a href="/three.zip">three</a>
  <a href="javascript:void 0">nothing</a>
  <input id=up type=file accept="image/*">
  <p>Some words in the article.</p>"""

def _png(width, height, colour="#336699"):
    """A real PNG, so a picture on the test page has a real size."""
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QImage, QColor
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    out = bytes(buffer.data())
    buffer.close()
    return out


PAGES = {
    "/pics": PICTURES,
    "/big.png": _png(800, 600),
    "/small.png": _png(16, 16, "#993366"),
    "/back.png": _png(64, 64, "#669933"),
    "/one.pdf": "%PDF-1.4 not really a pdf",
    "/two.pdf": "%PDF-1.4 nor this",
    "/three.zip": "PK\x03\x04 not really a zip",
    "/file.txt": "a file to download, with words in it",
    "/plain": "<title>Plain</title><p>nothing here</p>",
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
dl = scratch / "downloads-test"
dl.mkdir(parents=True, exist_ok=True)
win.config["downloadDir"] = str(dl)


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(400)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


def made(name, text="hello", when=None, state="done", url="", source=""):
    """A file on disk plus the row that says it was downloaded."""
    path = dl / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    entry = win._add_download_entry({
        "name": name, "dir": str(dl), "url": url or srv.url("/" + name),
        "from": source, "t": int(when if when is not None else time.time()),
        "state": state, "received": path.stat().st_size,
        "size": path.stat().st_size})
    win.save_downloads()
    return entry


print("\n(1) the list, filtered")
win.downloads[:] = []
one = made("report.pdf", "a report", source=srv.url("/pics"))
two = made("sodium.jar", "not really a jar")
three = made("holiday.png", "not really a png",
             when=time.time() - 40 * 86400)
check("the list has what was put on it", len(win.downloads) == 3)
check("a word finds one", [e["name"] for e in win.download_rows("report")]
      == ["report.pdf"], [e["name"] for e in win.download_rows("report")])
check("two words both have to match",
      win.download_rows("report sodium") == [])
check("a kind filters", [e["name"] for e in win.download_rows(kind="Mods")]
      == ["sodium.jar"], win.download_rows(kind="Mods"))
check("pictures are their own kind",
      [e["name"] for e in win.download_rows(kind="Pictures")]
      == ["holiday.png"])
check("a number of days filters out the old one",
      len(win.download_rows(days=7)) == 2, len(win.download_rows(days=7)))
check("the site filters", len(win.download_rows(site="127.0.0.1")) == 3,
      len(win.download_rows(site="127.0.0.1")))
check("a site nothing came from filters everything out",
      win.download_rows(site="example.com") == [])
check("the sites are counted",
      win.download_sites() and win.download_sites()[0][1] == 3,
      win.download_sites())
check("an entry is found by its id",
      win.download_entry(one["id"])["name"] == "report.pdf")
check("...and its path put together",
      win.download_path(one) == dl / "report.pdf")
check("a row with no folder has no path",
      win.download_path({"name": "x"}) is None)

print("\n(2) the page it came from")
check("the source page is kept", win.download_source(one["id"])
      == srv.url("/pics"), win.download_source(one["id"]))
check("a row without one says so", win.download_source(two["id"]) == "")
before = win.tabs.count()
check("it opens", win.open_download_source(one["id"]) is not None)
check("...in a tab", win.tabs.count() == before + 1)
check("and with nothing to open it says so",
      win.open_download_source(two["id"]) is False)

print("\n(3) the checksum, and the same file twice")
digest = win.download_hash(one["id"])
check("a checksum is worked out", len(digest) == 64, digest[:16])
import hashlib  # noqa: E402
check("...and it is the file's own",
      digest == hashlib.sha256(b"a report").hexdigest(), digest[:16])
check("it is kept on the row", win.download_entry(one["id"])["sha256"]
      == digest)
check("a file that is gone has none",
      win.download_hash(9999) == "")
check("the same name is noticed",
      (win.download_twice("report.pdf") or {}).get("id") == one["id"])
check("the same bytes under another name are noticed too",
      (win.download_twice("other.pdf", digest) or {}).get("id")
      == one["id"])
check("something new is not", win.download_twice("brand-new.pdf") is None)

print("\n(4) off the list, and off the disk")
spare = made("spare.txt", "throw me away")
path = win.download_path(spare)
check("forgetting it takes the row", win.forget_download(spare["id"])
      is True)
check("...and leaves the file", path.exists())
check("...and the row is gone", win.download_entry(spare["id"]) is None)
again = made("spare2.txt", "delete me")
path2 = win.download_path(again)
real_question = QMessageBox.question
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
check("deleting the file asks first, and No keeps it",
      win.forget_download(again["id"], from_disk=True) is False
      and path2.exists())
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
check("...and Yes deletes it",
      win.forget_download(again["id"], from_disk=True) is True)
check("the file is really gone", not path2.exists())
QMessageBox.question = real_question

print("\n(5) the list tidied")
win.config["dlKeepDays"] = 0
check("off, nothing is dropped", win.clean_downloads() == 0)
win.config["dlKeepDays"] = 7
gone = win.clean_downloads()
check("a row older than a week is dropped", gone == 1, gone)
check("...and the newer ones are not", len(win.downloads) == 2,
      len(win.downloads))
check("the file of the dropped row is untouched",
      (dl / "holiday.png").exists())
win.config["dlKeepDays"] = 0

print("\n(6) the list as a file")
out = scratch / "downloads.csv"
count = win.export_downloads(out)
check("every row is written", count == len(win.downloads), count)
text = out.read_text()
check("the header names the columns",
      text.splitlines()[0] == "name,url,from,size,when,sha256,state",
      text.splitlines()[0])
check("the checksum is in it", digest in text)
check("the source page is in it", srv.url("/pics") in text)

print("\n(7) what can be done with one")
check("the address is copied", win.copy_download_link(one["id"]) is True)
check("...really", QGuiApplication.clipboard().text()
      == one["url"], QGuiApplication.clipboard().text())
check("a row with no address copies nothing",
      win.copy_download_link(9999) is False)
opened = []
real_popen = subprocess.Popen
subprocess.Popen = lambda *a, **k: (opened.append(a[0]),
                                    real_popen(["true"]))[1]
check("a file is opened with the desktop's opener",
      win.open_download_file(one["id"]) is True)
check("...by xdg-open", opened and "xdg-open" in opened[0][0], opened)
check("the last download is the one that opens",
      win.open_last_download() is True)
win.set_open_with("pdf", "nautilus")
opened[:] = []
win.open_download_file(one["id"])
check("his own rule picks the program",
      opened and "nautilus" in opened[0][0], opened)
win.set_open_with("pdf", "")
runner = made("thing.appimage", "not really a program")
QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.No
opened[:] = []
check("a downloaded program asks before it is opened",
      win.open_download_file(runner["id"]) is False and opened == [])
QMessageBox.question = real_question
subprocess.Popen = real_popen

print("\n(8) open-with rules")
win.parse_open_with("stl=prusa-slicer\n zip = file-roller \n# a note\nbad")
check("the rules are read", win.open_with_rules()
      == {"stl": "prusa-slicer", "zip": "file-roller"},
      win.open_with_rules())
check("a line without an = is ignored", "bad" not in win.open_with_rules())
check("a program that is not installed is named",
      ("stl", "prusa-slicer") in win.open_with_missing(),
      win.open_with_missing())
check("...and does not become the program used",
      win.open_with_for("thing.stl") == "")
win.parse_open_with("txt=nautilus")
check("one that is installed does",
      win.open_with_for("notes.txt").endswith("nautilus"),
      win.open_with_for("notes.txt"))
win.parse_open_with("")

print("\n(9) the name a file is saved under")
win.config["dlTemplate"] = ""
check("with no pattern the name is the site's",
      win.apply_template("photo.jpg") == "photo.jpg")
win.config["dlTemplate"] = "{date}-{site}-{name}.{ext}"
got = win.apply_template("photo.jpg", url="https://example.com/x/photo.jpg")
check("the pattern is used",
      got == "%s-example.com-photo.jpg" % time.strftime("%Y-%m-%d"), got)
win.config["dlTemplate"] = "{title}.{ext}"
check("a title with a slash in it cannot make a folder",
      "/" not in win.apply_template("a.jpg", title="some/title"),
      win.apply_template("a.jpg", title="some/title"))
win.config["dlTemplate"] = "{name}"
check("the ending is put back even if the pattern forgets it",
      win.apply_template("photo.jpg") == "photo.jpg")
win.config["dlTemplate"] = "{title}.{ext}"
check("a very long title is cut to something a filesystem takes",
      len(win.apply_template("a.jpg", title="x" * 400)) <= 180)
win.config["dlTemplate"] = ""

print("\n(10) kinds he does not want, and sizes he does not want")
win.config["dlBlocked"] = "exe msi .scr"
check("the list is read", win.blocked_endings() == ["exe", "msi", "scr"],
      win.blocked_endings())
check("one of them is caught", win.download_blocked("setup.exe") is True)
check("something else is not", win.download_blocked("notes.txt") is False)
win.config["dlBlocked"] = ""
win.config["dlAskFor"] = "jar zip"
check("asking is per kind", win.download_should_ask("mod.jar") is True)
check("...and not for the rest",
      win.download_should_ask("photo.png") is False)
win.config["askDownload"] = True
check("“ask every time” still wins",
      win.download_should_ask("photo.png") is True)
win.config["askDownload"] = False
win.config["dlAskFor"] = ""
check("there is room on this disk", win.free_space(dl) > 0,
      win.free_space(dl))
win.config["dlBigMb"] = 0
check("with no size set nothing is big", win.download_too_big(1 << 30) == "")
win.config["dlBigMb"] = 10
check("over the size it says so",
      win.download_too_big(20 << 20) == "big")
check("under it, nothing", win.download_too_big(1 << 20) == "")
check("something bigger than the disk says that instead",
      win.download_too_big(win.free_space(dl) + (1 << 30)) == "space")
win.config["dlBigMb"] = 0

print("\n(11) folders of their own")
check("with nothing set there is no private folder",
      win.private_download_dir() is None)
priv = scratch / "private-dl"
win.config["privateDlDir"] = str(priv)
check("with a folder set it is made", win.private_download_dir() == priv
      and priv.exists())
(priv / "something.txt").write_text("from a private tab")
win.config["privateDlWipe"] = False
check("without the switch nothing is emptied",
      win.clear_private_downloads() == 0)
win.config["privateDlWipe"] = True
check("with it, the folder is emptied",
      win.clear_private_downloads() == 1)
check("...really", not (priv / "something.txt").exists())
work = scratch / "work-dl"
check("a virtual browser has no folder unless he says",
      win.session_download_dir("work") is None)
win.set_session_download_dir("work", str(work))
check("...and then it has one", win.session_download_dir("work") == work)
check("the main browser still has none",
      win.session_download_dir("main") is None)

print("\n(12) where a file came from, in the file")
win.config["dlOrigin"] = False
mark = made("marked.txt", "note my origin")
check("off, nothing is written",
      win.note_origin(win.download_path(mark), "https://example.com/x")
      is False)
win.config["dlOrigin"] = True
wrote = win.note_origin(win.download_path(mark), "https://example.com/x",
                        "https://example.com/page")
check("on, the attribute is written", wrote is True, wrote)
check("...and reads back",
      win.read_origin(win.download_path(mark))
      == "https://example.com/x",
      win.read_origin(win.download_path(mark)))
check("a file that is not there has none", win.read_origin(dl / "nope") == "")
win.config["dlOrigin"] = False

print("\n(13) holding and carrying on")
check("a download nothing is holding cannot be paused",
      win.pause_download(one["id"]) is False)
check("...and a finished one has nothing to resume",
      win.resume_download(one["id"]) is False)
broken = made("broken.zip", "half a file", state="failed")
check("a failed one is fetched again instead",
      win.resume_download(broken["id"]) is True)

print("\n(14) the queue")
win.config["dlAtOnce"] = 0
check("with no limit nothing is queued",
      win.queue_download(None, {"id": 1}) is False)
win.config["dlAtOnce"] = 1


class FakeRequest:
    """Something with the three methods the queue uses."""

    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def isPaused(self):
        return self.paused


first = {"id": 101, "state": "active", "name": "first"}
second = {"id": 102, "state": "active", "name": "second"}
win.downloads.extend([first, second])
held = FakeRequest()
win.dl_active[102] = held
check("the second one is held back",
      win.queue_download(held, second) is True)
check("...and it says so on the row", second.get("queued") is True)
check("...and the request is paused", held.paused is True)
check("it is in the queue", win.queued_downloads() == [102],
      win.queued_downloads())
check("moving it in the queue works",
      win.reorder_queue(102, up=True) is True)
first["state"] = "done"
check("when a slot comes free it is let through",
      win.start_next_download() == 102)
check("...and it is running again", held.paused is False)
check("...and off the queue", win.queued_downloads() == [])
win.downloads.remove(first)
win.downloads.remove(second)
win.dl_active.pop(102, None)
win.config["dlAtOnce"] = 0

print("\n(15) the speed cap")
win.config["dlSpeedKb"] = 0
check("with no cap nothing is measured", win._speed_tick() == 0)
win.config["dlSpeedKb"] = 100
fast = {"id": 201, "state": "active", "name": "fast", "received": 0}
win.downloads.append(fast)
held2 = FakeRequest()
win.dl_active[201] = held2
win._speed_tick()
fast["received"] = 5 << 20            # five megabytes in a moment
win._dl_speed[201] = (0, time.monotonic() - 1.0)
rate = win._speed_tick()
check("a download over the cap is measured", rate > 100 * 1024, rate)
check("...and held back for a moment", held2.paused is True)
H.spin(1200)
check("...and let go again", held2.paused is False)
win.downloads.remove(fast)
win.dl_active.pop(201, None)
win.config["dlSpeedKb"] = 0

print("\n(16) a download at a chosen time")
win.config["dlLater"] = []
check("nothing is waiting", win._schedule_tick() == 0)
win.schedule_download(srv.url("/file.txt"), time.time() - 5, "later.txt")
check("one is written down", len(win.scheduled_downloads()) == 1)
page("/plain")
started = win._schedule_tick()
check("its time has come, so it starts", started == 1, started)
check("...and the list is empty again", win.scheduled_downloads() == [])
H.wait_for(lambda: any(e.get("name", "").startswith("later")
                       or e.get("name") == "file.txt"
                       for e in win.downloads), 8000)
check("the file really came down",
      any("file" in e.get("name", "") or "later" in e.get("name", "")
          for e in win.downloads),
      [e.get("name") for e in win.downloads][-3:])

print("\n(17) inside an archive")
zip_path = dl / "bundle.zip"
with zipfile.ZipFile(zip_path, "w") as archive:
    archive.writestr("readme.txt", "a readme inside")
    archive.writestr("inner/thing.cfg", "a config inside")
rows = win.archive_list(zip_path)
check("a zip is listed", len(rows) == 2, rows)
check("...with names and sizes",
      {r["name"] for r in rows} == {"readme.txt", "inner/thing.cfg"},
      rows)
tar_path = dl / "bundle.tar.gz"
with tarfile.open(tar_path, "w:gz") as archive:
    inner = dl / "in-tar.txt"
    inner.write_text("a file in a tar")
    archive.add(inner, arcname="in-tar.txt")
check("a tar.gz is listed too",
      [r["name"] for r in win.archive_list(tar_path)] == ["in-tar.txt"],
      win.archive_list(tar_path))
check("something that is not an archive lists nothing",
      win.archive_list(dl / "report.pdf") == [])
bad_zip = dl / "evil.zip"
with zipfile.ZipFile(bad_zip, "w") as archive:
    archive.writestr("../escaped.txt", "outside")
check("an archive that writes outside its folder is spotted",
      win.archive_unsafe(win.archive_list(bad_zip)) == ["../escaped.txt"],
      win.archive_unsafe(win.archive_list(bad_zip)))
check("...and it is refused rather than unpacked",
      win.extract_archive(path=bad_zip, ask=False) == "")
check("...and nothing landed outside", not (dl.parent / "escaped.txt")
      .exists())
where = win.extract_archive(path=zip_path, ask=False)
check("a good one is unpacked", where and Path(where).exists(), where)
check("...into a folder of its own name",
      Path(where).name == "bundle", where)
check("...with the files in it",
      (Path(where) / "readme.txt").read_text() == "a readme inside")
check("one file can be pulled out on its own",
      win.archive_file(zip_path, "inner/thing.cfg")
      == str(dl / "thing.cfg"), win.archive_file(zip_path,
                                                 "inner/thing.cfg"))
check("...and it has the right bytes",
      (dl / "thing.cfg").read_text() == "a config inside")
check("a path that points outside is refused there too",
      win.archive_file(zip_path, "../../escaped.txt") == "")

print("\n(18) what a mod says about itself")
fabric_jar = dl / "sodium-0.5.8.jar"
with zipfile.ZipFile(fabric_jar, "w") as archive:
    archive.writestr("fabric.mod.json", json.dumps({
        "id": "sodium", "name": "Sodium", "version": "0.5.8",
        "environment": "client",
        "depends": {"minecraft": "1.20.4", "fabricloader": ">=0.15"}}))
info = win.mod_info(fabric_jar)
check("a Fabric mod is read", info.get("loader") == "Fabric", info)
check("...with its name and version",
      (info.get("name"), info.get("version")) == ("Sodium", "0.5.8"), info)
check("...and which Minecraft it wants",
      info.get("minecraft") == "1.20.4", info)
forge_jar = dl / "jei-15.jar"
with zipfile.ZipFile(forge_jar, "w") as archive:
    archive.writestr("META-INF/mods.toml", '''
modLoader="javafml"
[[mods]]
modId="jei"
version="15.2.0"
displayName="Just Enough Items"
[[dependencies.jei]]
    modId="minecraft"
    versionRange="[1.20.1,1.21)"
''')
info = win.mod_info(forge_jar)
check("a Forge mod is read too", info.get("loader") == "Forge", info)
check("...with its display name",
      info.get("name") == "Just Enough Items", info)
check("...and the Minecraft range",
      "1.20.1" in info.get("minecraft", ""), info)
check("a jar that says nothing says nothing",
      win.mod_info(zip_path) == {}, win.mod_info(zip_path))
check("something that is not a jar at all is no trouble",
      win.mod_info(dl / "report.pdf") == {})

print("\n(19) a mod into an instance")
instance = scratch / "instance-one"
win.config["mcInstances"] = ""
check("with no instance set it refuses",
      win.route_mod(path=fabric_jar, ask=False) == "")
win.config["mcInstances"] = str(instance)
where = win.route_mod(path=fabric_jar, ask=False)
check("with one set it lands in mods",
      where and Path(where).parent == instance / "mods", where)
check("...and is really there", Path(where).exists())
check("an instance he never listed is refused",
      win.route_mod(path=fabric_jar, instance="/tmp/elsewhere",
                    ask=False) == "")

print("\n(20) pictures")
shot = QImage(40, 30, QImage.Format.Format_RGB32)
shot.fill(QColor("#336699"))
png = dl / "colour.png"
check("a picture to work with", shot.save(str(png), "PNG") is True)
made_jpg = win.convert_image(png, "jpg")
check("it converts", made_jpg and Path(made_jpg).exists(), made_jpg)
check("...to the name asked for", made_jpg.endswith(".jpg"), made_jpg)
check("...and the original is left alone", png.exists())
check("a file that is not a picture converts to nothing",
      win.convert_image(dl / "report.pdf", "png") == "")
# a JPEG with an Exif block spliced in, to show the strip does something
raw = Path(made_jpg).read_bytes()
exif = b"\xff\xe1\x00\x16Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00"
with_exif = dl / "with-exif.jpg"
with_exif.write_bytes(raw[:2] + exif + raw[2:])
check("the test's own file carries Exif",
      win.image_has_metadata(with_exif) is True)
clean = win.strip_metadata(with_exif)
check("stripping writes a new file", clean and Path(clean).exists(), clean)
check("...with no Exif in it",
      win.image_has_metadata(Path(clean)) is False)
check("...and the picture is still the same size",
      QImage(str(clean)).size() == QImage(str(with_exif)).size(),
      (QImage(str(clean)).size(), QImage(str(with_exif)).size()))
check("the original is untouched", win.image_has_metadata(with_exif) is True)

print("\n(21) the full-size version of a picture")
check("Twitter's own parameter is used",
      "name=orig" in win.biggest_image_url(
          "https://pbs.twimg.com/media/abc?format=jpg&name=small"),
      win.biggest_image_url(
          "https://pbs.twimg.com/media/abc?format=jpg&name=small"))
check("Wikimedia's thumb path is dropped",
      win.biggest_image_url(
          "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/"
          "X.jpg/800px-X.jpg")
      == "https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg",
      win.biggest_image_url(
          "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/"
          "X.jpg/800px-X.jpg"))
check("Reddit's resize parameters are dropped",
      "width=" not in win.biggest_image_url(
          "https://preview.redd.it/abc.jpg?width=640&crop=smart&auto=webp"))
check("a plain address with a size in the name loses it",
      win.biggest_image_url("https://example.com/photo_800x600.jpg")
      == "https://example.com/photo.jpg",
      win.biggest_image_url("https://example.com/photo_800x600.jpg"))
check("anything else is left exactly as it is",
      win.biggest_image_url("https://example.com/photo.jpg")
      == "https://example.com/photo.jpg")

print("\n(22) the page's side")
gallery = page("/pics")
rows = []
win.page_images(view=gallery, then=rows.append)
H.wait_for(lambda: rows, 5000)
found = rows[0] if rows else []
check("the pictures are found", len(found) >= 2, found)
check("...with their real sizes",
      any(r.get("width") == 800 for r in found), found)
check("...and the background one too",
      any(r.get("alt") == "background" for r in found), found)
rows = []
win.page_images(view=gallery, then=rows.append, least=100)
H.wait_for(lambda: rows, 5000)
check("the size filter leaves the little ones out",
      all((r.get("width") or 0) >= 100 or not r.get("width")
          for r in rows[0]), rows[0])
links = []
win.page_links_of(["pdf"], view=gallery, then=links.append)
H.wait_for(lambda: links, 5000)
check("the links of one kind are found", len(links[0]) == 2, links[0])
check("...and nothing else", all(r["url"].endswith(".pdf")
                                 for r in links[0]), links[0])
boxes = []
win.upload_boxes(view=gallery, then=boxes.append)
H.wait_for(lambda: boxes, 5000)
check("the upload box is found", len(boxes[0]) == 1, boxes[0])
check("...with what it takes", boxes[0][0]["accept"] == "image/*",
      boxes[0])

print("\n(23) saving what is on the page")
win.downloads[:] = []
saved = []
win.save_images(view=gallery, least=100, then=saved.append)
H.wait_for(lambda: saved, 6000)
check("the big pictures are saved", saved and saved[0] >= 1, saved)
H.wait_for(lambda: win.downloads, 8000)
check("...and they land on the list", len(win.downloads) >= 1,
      [e.get("name") for e in win.downloads])
one_file = []
win.save_page_one_file(view=gallery, path=str(dl / "page.html"),
                       then=one_file.append)
H.wait_for(lambda: one_file, 8000)
check("the page is saved as one file",
      one_file and Path(one_file[0]).exists(), one_file)
text = Path(one_file[0]).read_text() if one_file and one_file[0] else ""
check("...with its stylesheet written in",
      "<style>" in text or "<style" in text, text[:80])
check("...and no script tags left",
      "<script" not in text.lower(), text[:80])
mhtml = []
win.save_page_one_file(view=gallery, path=str(dl / "page.mhtml"),
                       then=mhtml.append)
H.wait_for(lambda: mhtml, 8000)
H.spin(1500)
check("the engine's own MHTML is used for .mhtml",
      (dl / "page.mhtml").exists(), mhtml)
md = []
win.save_page_markdown(view=gallery, path=str(dl / "page.md"),
                       then=md.append)
H.wait_for(lambda: md, 8000)
check("the article is saved as Markdown",
      md and md[0] and Path(md[0]).exists(), md)
body = Path(md[0]).read_text() if md and md[0] else ""
check("...with a heading and the address it came from",
      body.startswith("# ") and "127.0.0.1" in body, body[:60])
check("...and the words of the page in it",
      "words in the article" in body, body[-80:])

print("\n(24) uploads")
QGuiApplication.clipboard().clear()
check("with no picture in the clipboard it says so",
      win.paste_image_upload(view=gallery) is False)
QGuiApplication.clipboard().setImage(shot)
pasted = []
check("with one, it goes into the box",
      win.paste_image_upload(view=gallery, then=pasted.append) is True)
H.wait_for(lambda: pasted, 6000)
check("...and the page has a file now", pasted == ["ok"], pasted)
check("the page really sees it",
      js(gallery, "document.getElementById('up').files.length") == 1,
      js(gallery, "document.getElementById('up').files.length"))
check("...with the name the browser gave it",
      js(gallery, "document.getElementById('up').files[0].name")
      == "pasted.png",
      js(gallery, "document.getElementById('up').files[0].name"))
recent = win.recent_for_upload()
check("the recent downloads are offered", len(recent) >= 1, recent[:2])
check("...newest first",
      recent == sorted(recent, key=lambda r: -r["when"]))
win.config["stripUploadExif"] = True
put = []
win.put_file_in_upload(with_exif, view=gallery, then=put.append)
H.wait_for(lambda: put, 6000)
check("a file from disk goes into the box", put == ["ok"], put)
check("...and the camera data was taken out on the way",
      js(gallery, "document.getElementById('up').files[0].name")
      == "with-exif-clean.jpg",
      js(gallery, "document.getElementById('up').files[0].name"))
win.config["stripUploadExif"] = False
check("a site can be excepted",
      win.keep_exif_here("photos.example", True) is True
      and "photos.example" in win.exif_keep_sites())
menu = win.upload_recent_menu(view=gallery)
check("the menu lists something", len([a for a in menu.actions()
                                       if a.text()]) >= 1,
      [a.text() for a in menu.actions()][:3])

print("\n(25) the other programs, and what is said when they are missing")
check("there is no torrent client here",
      not any(shutil.which(n) for n in ("transmission-gtk", "qbittorrent",
                                        "deluge", "ktorrent")))
check("a magnet link says so rather than opening a blank tab",
      win.torrent_handoff("magnet:?xt=urn:btih:abc") is False)
check("something that is not a torrent is not its business",
      win.torrent_handoff("https://example.com/x") is False)
check("there is no yt-dlp here", win.ytdlp_ready() is False)
check("...so saving a video says so",
      win.save_with_ytdlp(url="https://example.com/v") is False)
check("there is no clamscan here", win.clamav_ready() is False)
# a row of its own: the sections above empty the list on purpose
scan_row = made("scanme.txt", "scan me")
scanned = []
check("...so a scan reports no scanner rather than clean",
      win.scan_download(scan_row["id"], then=scanned.append) is False)
check("...in those words", scanned == ["noscanner"], scanned)
check("...and the row says it too",
      (win.download_entry(scan_row["id"]) or {}).get("scan")
      == "noscanner",
      win.download_entry(scan_row["id"]))
gcode = made("cube.gcode", "G28\nG1 X0 Y0\n")
win.config["printerUrl"] = ""
check("with no printer address it refuses",
      win.send_to_printer(gcode["id"]) is False)
win.config["printerUrl"] = srv.url("")
sent = []
check("with one, the upload goes out",
      win.send_to_printer(gcode["id"], then=sent.append) is True)
H.wait_for(lambda: sent, 8000)
check("...and the printer took it", sent == [200], sent)
post = H.Handler.last_post
check("it went to Moonraker's upload path",
      post.get("path") == "/server/files/upload", post.get("path"))
check("...as a multipart form",
      "multipart/form-data" in post.get("type", ""), post.get("type"))
check("...with the file's name in it",
      b"cube.gcode" in post.get("head", b""), post.get("head", b"")[:60])
check("a file that is not G-code is refused",
      win.send_to_printer(scan_row["id"]) is False)
win.config["printerUrl"] = ""

print("\n(26) when a download lands")
win.config["dlNotify"] = True
landed = made("quiet.txt", "nothing to see")
check("nothing is said while this window is the active one",
      win.notify_download_done(landed) is False
      if win.isActiveWindow() else True,
      "active: %s" % win.isActiveWindow())
win.isActiveWindow = lambda: False
check("a word is said when he is elsewhere",
      win.notify_download_done(landed) is not None)
win.config["dlNotify"] = False
check("...and nothing when the switch is off",
      win.notify_download_done(landed) is False)
del win.isActiveWindow
win.config["dlAutoExtract"] = False
check("with the switch off an archive is left alone",
      win.offer_extract(made("left.zip", "PK not really")) is False)
win.config["dlRouteMods"] = False
check("...and so is a mod", win.offer_mod_route(
    made("quiet.jar", "not really")) is False)
win.config["dlHashAll"] = True
fresh = made("hashme.txt", "hash me please")
did = win._download_landed(fresh)
check("the landing does the things that are switched on",
      "hash" in did, did)
check("...and the checksum is on the row",
      len(win.download_entry(fresh["id"]).get("sha256", "")) == 64)
win.config["dlHashAll"] = False

print("\n(27) a look at a file without another program")
check("a picture can be previewed", win.preview_download(
    made("look.png", png.read_bytes())["id"]) is True)
box = getattr(win, "_dl_preview", None)
check("...in a window", box is not None and box.isVisible())
if box is not None:
    box.close()
text_row = made("notes.txt", "a line\nand another")
check("a text file can be previewed", win.preview_download(text_row["id"])
      is True)
box = getattr(win, "_dl_preview", None)
editor = box.findChild(QPlainTextEdit, "dlpreview") if box else None
check("...with its text in it",
      editor is not None and "and another" in editor.toPlainText(),
      editor and editor.toPlainText()[:30])
if box is not None:
    box.close()
zip_row = made("bundle2.zip", zip_path.read_bytes())
check("an archive can be previewed", win.preview_download(zip_row["id"])
      is True)
box = getattr(win, "_dl_preview", None)
editor = box.findChild(QPlainTextEdit, "dlpreview") if box else None
check("...and it lists what is inside",
      editor is not None and "readme.txt" in editor.toPlainText(),
      editor and editor.toPlainText()[:40])
if box is not None:
    box.close()
check("something with nothing to show says so",
      win.preview_download(made("thing.bin", b"\x00\x01")["id"]) is False)

print("\n(28) a list of addresses, and a link saved")
win.downloads[:] = []
page("/plain")
count = win.batch_download("%s\n%s\n# a note\nnot-an-address"
                           % (srv.url("/one.pdf"), srv.url("/two.pdf")),
                           folder=str(dl))
check("the usable addresses are started", count == 2, count)
check("...and a line that is not one is skipped", count != 3)
check("an empty list starts nothing", win.batch_download("") == 0)
H.wait_for(lambda: len(win.downloads) >= 2, 10000)
check("they land", len(win.downloads) >= 2,
      [e.get("name") for e in win.downloads])
win.downloads[:] = []
check("a link can be saved instead of followed",
      win.save_link_target(srv.url("/file.txt")) is True)
H.wait_for(lambda: win.downloads, 8000)
check("...and it lands", any("file" in e.get("name", "")
                             for e in win.downloads),
      [e.get("name") for e in win.downloads])
check("a link that is not http is not saved",
      win.save_link_target("ftp://example.com/x") is False)

print("\n(29) the PDF choice that was already there")
check("Settings has the switch",
      'id="pdfviewer"' in (HERE / "settings.html").read_text())
check("...and the browser reads it",
      "PdfViewerEnabled" in (HERE / "browser.py").read_text())

print("\n(30) Settings, the words, and the keys")
page_text = (HERE / "settings.html").read_text()
check("there is a section of its own",
      'data-desc="descDownloadsMore"' in page_text)
for ident in ("dlorigin", "dlhashall", "dlnotify", "dlautoextract",
              "dlroutemods", "dlscan", "altclicksave", "stripuploadexif",
              "imgbiggest", "privatedlwipe", "dlkeepdays", "dlbigmb",
              "dlatonce", "dlspeedkb", "imgleast", "dltemplate",
              "privatedldir", "printerurl", "dlblocked", "dlaskfor",
              "openwithtext"):
    check("Settings has a row for " + ident, ('id="%s"' % ident)
          in page_text)
for ident, cfgkey in (("dlorigin", "dlOrigin"),
                      ("dlscan", "dlScan"),
                      ("altclicksave", "altClickSave"),
                      ("imgbiggest", "imgBiggest")):
    check("...wired to " + cfgkey,
          ('bindSwitch("%s", "%s")' % (ident, cfgkey)) in page_text)
check("the text boxes are saved on one button",
      'id="dlsave"' in page_text and 'saveSetting("dlTemplate"'
      in page_text)
need = ["dlFiles", "dlSource", "dlHash", "dlDelete", "dlExport",
        "dlCopyLink", "dlAgainAction", "dlOpenLast", "dlOpenIt",
        "dlOpenWith", "dlExtract", "dlArchiveList", "dlModInfo",
        "imgConvert", "imgSaveAll", "dlNoTorrent", "dlNoYtdlp",
        "dlNoClam", "dlPrinter", "dlPreview", "dlBatch", "upPaste",
        "upRecent", "pageSaveOne", "pageSaveMd", "dlSearch",
        "dlQueueMenu", "dlCarryOn", "descDownloadsMore"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)
registry = win.actions_list()
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
clash = {k: v for k, v in taken.items() if len(v) > 1}
check("no two actions want the same key", clash == {}, clash)
ids = [r["id"] for r in registry]
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1])
for wanted in ("dlmenu", "dllast", "dlsearch", "dlexport", "dlbatch",
               "saveimages", "savepageone", "savepagemd", "ytdlpsave",
               "pasteupload", "uploadrecent"):
    check("there is an action for " + wanted, wanted in ids)
menu = win.downloads_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("the menu has the last-download entry",
      any("last" in t.lower() for t in labels), labels)
check("...and the search", any("search" in t.lower() for t in labels),
      labels)

print("\n(31) a download dragged out of the bar")


class FinishedRequest:
    """Enough of a download request for the bar widget: a finished one,
    pointing at a file that is really there."""

    class DownloadState:
        DownloadCompleted = 2
        DownloadInProgress = 0

    def __init__(self, folder, name):
        self.folder, self.name = str(folder), str(name)
        self.receivedBytesChanged = _Signal()
        self.totalBytesChanged = _Signal()
        self.stateChanged = _Signal()
        self.isPausedChanged = _Signal()
        self.isFinishedChanged = _Signal()

    def downloadFileName(self):
        return self.name

    def downloadDirectory(self):
        return self.folder

    def state(self):
        return self.DownloadState.DownloadCompleted

    def receivedBytes(self):
        return 1

    def totalBytes(self):
        return 1

    def isPaused(self):
        return False


class _Signal:
    def connect(self, _slot):
        return None


dragged = made("dragme.txt", "drag me somewhere")
widget = B.DownloadWidget(FinishedRequest(dl, "dragme.txt"),
                          lambda *_a: None)
check("the widget knows which file it has",
      widget.file_path() == dl / "dragme.txt", widget.file_path())
load = widget.drag_payload()
check("a drag from it carries a file url",
      load.get("url", "").startswith("file://")
      and load["url"].endswith("dragme.txt"), load)
check("...and the plain path as text",
      load.get("text") == str(dl / "dragme.txt"), load)
unfinished = FinishedRequest(dl, "nothing-here.txt")
unfinished.state = lambda: FinishedRequest.DownloadState.DownloadInProgress
widget2 = B.DownloadWidget(unfinished, lambda *_a: None)
check("a download still coming carries nothing",
      widget2.drag_payload() == {}, widget2.drag_payload())
widget.deleteLater()
widget2.deleteLater()

print("\n(32) what the engine will not do, measured")
# 385 in the backlog asks for big downloads split over several
# connections. This is where the backlog gets its answer: the engine's
# own download object has no way to ask for a byte range, so segments
# would mean a second downloader beside it, with its own resume, queue,
# progress and error handling.
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest  # noqa: E402
names = [n for n in dir(QWebEngineDownloadRequest) if not n.startswith("_")]
# "...Changed" contains "ange": what matters is a range to ask for
ranges = [n for n in names
          if "range" in n.lower() and not n.endswith("Changed")]
check("the engine's download has no byte-range control",
      ranges == [], ranges)
check("...and no notion of segments or connections",
      not any(w in n.lower() for n in names
              for w in ("segment", "connection", "parallel")),
      [n for n in names if "segment" in n.lower()])
check("what it does have is pause and resume",
      "pause" in names and "resume" in names)

print("\n(33) nothing new was installed for any of this")
text = (HERE / "browser.py").read_text()
check("the archives are the standard library's",
      "import zipfile" in text and "import tarfile" in text)
check("no new picture library", "import PIL" not in text
      and "from PIL" not in text)
check("the checksums are hashlib's", "hashlib.sha256" in text)
check("the pictures go through Qt's own QImage", "QImage(str(" in text)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails)))
else:
    print("all good")
srv.stop()
win.close()
sys.exit(1 if fails else 0)
