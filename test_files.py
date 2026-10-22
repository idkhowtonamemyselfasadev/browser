#!/usr/bin/env python3
"""Downloads and the things kept about pages: which folder a file lands
in, what a page has to download, what a file really is, searching the
history by what was on the page, and the read-later list."""
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

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PICTURE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'"
           " width='10' height='10'><rect width='10' height='10'/></svg>")
PAGE = ("<!doctype html><title>Files</title>"
        "<img src='/one.png'><img src='/two.jpg'>"
        "<div style=\"background-image:url('/three.webp')\">bg</div>"
        "<video src='/clip.mp4'></video>"
        "<a href='/pack.mrpack'>a modpack</a>"
        "<a href='/notes.pdf'>a pdf</a>"
        "<a href='/plain.html'>not a file</a>"
        "<p>Der Amboss repariert Werkzeuge und kostet Erfahrung.</p>")

app = H.app()
srv = H.Server({"/f": PAGE, "/plain.html": "<title>plain</title>plain"})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/f"))
H.spin(400)

print("\n(1) which shelf a file belongs on")
for name, kind in (("a.png", "Pictures"), ("b.MP4", "Video"),
                   ("c.flac", "Music"), ("d.pdf", "Documents"),
                   ("e.tar.gz", "Archives"), ("f.AppImage", "Programs"),
                   ("sodium.jar", "Mods"), ("g.mrpack", "Mods"),
                   ("h.weirdext", "")):
    check("%s -> %s" % (name, kind or "the downloads folder"),
          win.download_kind(name) == kind, win.download_kind(name))

print("\n(2) where it lands")
win.config["sortDownloads"] = False
check("off, everything goes to the downloads folder",
      win.download_dir_for("a.png") == win.download_dir(),
      str(win.download_dir_for("a.png")))
win.config["sortDownloads"] = True
target = win.download_dir_for("sodium.jar")
check("on, a mod goes to Mods", target.name == "Mods", str(target))
check("and the folder is made", target.exists(), str(target))
check("something unknown still goes to the downloads folder",
      win.download_dir_for("x.weirdext") == win.download_dir())
win.config["sortDownloads"] = False

print("\n(3) what a file really is")
probe = Path(B.CONFIG_FILE).parent / "probe.bin"
probe.write_bytes(b"hello")
check("the hash is the file's own hash",
      win.file_hash(probe) ==
      "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
      win.file_hash(probe))
check("a file that is not there has no hash", win.file_hash(probe / "no") == "")
check("a program is flagged as one", win.download_warning("setup.exe")
      and win.download_warning("mod.jar") and win.download_warning("x.AppImage"))
check("a picture is not", not win.download_warning("holiday.jpg"))

print("\n(4) what this page has to offer")
box = {}
win.page_files("images", view=view, then=lambda u: box.setdefault("v", u))
H.wait_for(lambda: "v" in box, 4000)
images = box["v"]
check("both pictures are found",
      any(u.endswith("/one.png") for u in images)
      and any(u.endswith("/two.jpg") for u in images), images)
check("and the one in the CSS background too",
      any(u.endswith("/three.webp") for u in images), images)
box = {}
win.page_files("media", view=view, then=lambda u: box.setdefault("v", u))
H.wait_for(lambda: "v" in box, 4000)
check("the video is found", any(u.endswith("/clip.mp4") for u in box["v"]),
      box["v"])
box = {}
win.page_files("links", view=view, then=lambda u: box.setdefault("v", u))
H.wait_for(lambda: "v" in box, 4000)
links = box["v"]
check("the files behind links are found",
      any(u.endswith("/pack.mrpack") for u in links)
      and any(u.endswith("/notes.pdf") for u in links), links)
check("an ordinary page is not one of them",
      not any(u.endswith("/plain.html") for u in links), links)

print("\n(5) searching the history by what was on the page")
win.config["indexPages"] = True
win.history = []
H.load(view, srv.url("/f"))
H.spin(3200)
check("the page is in the history", len(win.history) >= 1, win.history)
index = win.config.get("pageIndex") or {}
check("and its words were kept",
      any("Amboss" in text for text in index.values()), list(index)[:2])
found = win.search_history("amboss werkzeuge")
check("which is how it is found again",
      found and found[0]["found"] == "text", found[:1])
check("a title search still says so",
      (win.search_history("Files") or [{}])[0].get("found") == "title",
      win.search_history("Files")[:1])
check("nonsense finds nothing", win.search_history("zzzqqq") == [])
win.config["indexPages"] = False
win.config["pageIndex"] = {}
H.load(view, srv.url("/f"))
H.spin(3000)
check("with the index off nothing is written down",
      not win.config.get("pageIndex"), win.config.get("pageIndex"))

print("\n(6) read later")
win.config["readLater"] = []
check("a page goes on the list", win.read_later() is True)
items = win.config.get("readLater")
check("with its address", items and items[0]["url"].endswith("/f"), items)
check("the same page again takes it off", win.read_later() is False)
check("and the list is empty", not win.config.get("readLater"))
win.read_later("https://modrinth.com/mods", "Mods")
menu = win.read_later_menu()
check("the list is a menu", any("Mods" in a.text() for a in menu.actions()),
      [a.text() for a in menu.actions()])
check("a page that is not a web page is refused",
      win.read_later("file:///etc/passwd") is False)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
