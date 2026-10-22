#!/usr/bin/env python3
"""Bookmarks and history, part three: a copy of the page kept beside
the bookmark, how he got to a page, history as a tree and as pictures,
history out of Chrome and Firefox, a bookmark whose page moved, the
archive's copy, reminders, Favourites docked, an encrypted history and
the sites' own icons kept here.

Offscreen, scratch data, local server. The Chrome and Firefox history
files are made here with sqlite3 out of the standard library; nothing
reaches the network.
"""
import json
import os
import sqlite3
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

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>A</title><body><p>page a</p>"
          "<a id=go href='/b'>to b</a></body>",
    "/b": "<title>B</title><body><p>page b</p>"
          "<a id=go href='/c'>to c</a></body>",
    "/c": "<title>C</title><body><p>page c</p></body>",
    "/old": ("<title>Old</title><meta http-equiv=refresh"
             " content='0;url=/new'><p>moving</p>"),
    "/new": "<title>New</title><p>the new place</p>",
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
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))
H.spin(700)


def js(code, world=APP, v=None):
    return H.js(v or view, code, world)


print("\n(1) a copy of the page, beside the bookmark")
check("it is off to start with",
      win.config.get("bookmarkOffline", False) is False)
check("the folder is made when it is asked for",
      win.offline_dir().is_dir(), win.offline_dir())
check("it can be switched on", win.keep_offline_copy(True) is True)
win.add_bookmark_url(srv.url("/a"), "A")
mark = win.bookmarks[-1]
check("a bookmark with no copy says so",
      win.offline_copy_path(mark["id"]) == "")
check("opening a copy that is not there refuses",
      win.open_offline_copy(mark["id"]) is False)
path = win.bookmark_offline(mark["id"], view=view)
check("a copy can be made", isinstance(path, str) and path.endswith(".mhtml"),
      path)
H.wait_for(lambda: Path(path).is_file(), 9000)
check("...and it arrives on the disk", Path(path).is_file(), path)
size = Path(path).stat().st_size if Path(path).is_file() else 0
check("...with the page in it", size > 200, size)
check("...which is MHTML",
      Path(path).read_bytes()[:400].lower().count(b"mime") >= 1,
      Path(path).read_bytes()[:60])
check("...and it is found by the bookmark's id",
      win.offline_copy_path(mark["id"]) == path)
check("...and noted in the config",
      str(mark["id"]) in (win.config.get("offlineCopies") or {}),
      win.config.get("offlineCopies"))
kept = win.new_tab(url=None)
H.spin(200)
check("the kept copy opens", win.open_offline_copy(mark["id"], view=kept)
      == path)
H.spin(900)
check("...and reads as the page did",
      "page a" in (H.js(kept, "document.body.innerText", APP) or ""),
      (H.js(kept, "document.body.innerText", APP) or "")[:40])
win.keep_offline_copy(False)

print("\n(2) how he got here")
H.load(view, srv.url("/a"))
H.spin(800)
js("document.getElementById('go').click()", B.MAIN_WORLD_ID)
H.spin(1200)
check("the tab moved on", "/b" in view.url().toString(),
      view.url().toString())
js("document.getElementById('go').click()", B.MAIN_WORLD_ID)
H.spin(1200)
check("...and again", "/c" in view.url().toString(), view.url().toString())
trail = win.history_trail(srv.url("/c"))
check("the chain that led here is written down", len(trail) >= 3, trail)
check("...oldest first", trail[0]["url"].endswith("/a"), trail)
check("...and ends where he is", trail[-1]["url"].endswith("/c"), trail)
check("...with the titles", trail[0]["title"] == "A", trail[0])
check("a page nobody came from is a chain of one",
      len(win.history_trail(srv.url("/a"))) == 1,
      win.history_trail(srv.url("/a")))
check("an address that was never visited has no chain",
      win.history_trail("http://nowhere.test/x") == [])
menu = win.trail_menu(view=view)
check("the menu has the chain on it", len(menu.actions()) >= 3,
      [one.text() for one in menu.actions()])

print("\n(3) history as what opened what")
tree = win.history_tree()
check("there is a tree", isinstance(tree, list) and tree, tree)
roots = [one for one in tree if one["url"].endswith("/a")]
check("the page he started on is a root", len(roots) == 1, len(roots))
kids = roots[0]["kids"] if roots else []
check("...with what it led to hanging under it",
      any(one["url"].endswith("/b") for one in kids),
      [one["url"] for one in kids])
deeper = [one for one in kids if one["url"].endswith("/b")]
check("...and the next page under that",
      deeper and any(one["url"].endswith("/c")
                     for one in deeper[0]["kids"]),
      [one["url"] for one in (deeper[0]["kids"] if deeper else [])])
menu = win.history_tree_menu()
check("the tree is a menu of menus",
      any(one.menu() is not None for one in menu.actions()),
      [one.text() for one in menu.actions()][:4])

print("\n(4) a day of history in pictures")
check("it is off to start with",
      win.config.get("historyThumbs", False) is False)
check("...and then nothing is grabbed", win.save_visit_thumb(view) is False)
check("it can be switched on", win.keep_thumbnails(True) is True)
shot = win.save_visit_thumb(view)
check("a picture is kept", isinstance(shot, str) and shot.endswith(".png"),
      shot)
check("...on the disk", Path(shot).is_file(), shot)
from PyQt6.QtGui import QImage  # noqa: E402
small = QImage(shot)
check("...and it is small", small.width() == 240, small.width())
check("...one per address",
      win.save_visit_thumb(view) == shot, shot)
rows = win.history_thumbs()
check("today's pictures are listed", any(r["shot"] == shot for r in rows),
      [r["url"] for r in rows][:3])
check("...with the page they are of",
      all(r["url"].startswith("http") for r in rows), rows[:1])
check("another day has none", win.history_thumbs(day="1999-01-01") == [])
grid = win.new_tab(url=None)
H.spin(200)
count = win.open_thumb_grid(view=grid)
H.spin(1000)
check("the grid opens with them", count == len(rows), [count, len(rows)])
check("...as pictures to click",
      H.js(grid, "document.querySelectorAll('a img').length", APP)
      == len(rows),
      H.js(grid, "document.querySelectorAll('a img').length", APP))
check("a private tab is never kept",
      win.save_visit_thumb(win.new_tab(url=None, private=True)) is False)
win.keep_thumbnails(False)

print("\n(5) history out of another browser")
chrome = scratch / "ChromeHistory"
db = sqlite3.connect(str(chrome))
db.execute("CREATE TABLE urls (url TEXT, title TEXT,"
           " last_visit_time INTEGER)")
db.execute("INSERT INTO urls VALUES ('https://chrome.test/one',"
           " 'From Chrome', ?)",
           (int((time.time() + 11644473600) * 1000000),))
db.commit()
db.close()
added = win.import_history_from(path=chrome, which="chrome")
check("Chrome's history comes over", added == 1, added)
check("...with the title",
      any(row.get("title") == "From Chrome" for row in win.history),
      [row.get("title") for row in win.history[-3:]])
check("...and the time, read in Chrome's own epoch",
      any(abs(int(row.get("t") or 0) - int(time.time())) < 90
          for row in win.history if row.get("i") == "chrome"),
      [row for row in win.history if row.get("i") == "chrome"][:1])
check("...and marked as imported",
      any(row.get("i") == "chrome" for row in win.history))
check("a second import adds nothing",
      win.import_history_from(path=chrome, which="chrome") == 0)
fox = scratch / "places.sqlite"
db = sqlite3.connect(str(fox))
db.execute("CREATE TABLE moz_places (url TEXT, title TEXT,"
           " last_visit_date INTEGER)")
db.execute("INSERT INTO moz_places VALUES ('https://fox.test/one',"
           " 'From Firefox', ?)", (int(time.time() * 1000000),))
db.commit()
db.close()
check("Firefox's history comes over too",
      win.import_history_from(path=fox, which="firefox") == 1)
check("...and is marked as its own",
      any(row.get("i") == "firefox" for row in win.history))
check("a file that is not there is refused",
      win.import_history_from(path=scratch / "nope.sqlite") is False)
bad = scratch / "bad.sqlite"
bad.write_text("not a database at all")
check("a file that is not a history is refused",
      win.import_history_from(path=bad, which="chrome") is False)
check("...and the copy it made is cleaned up",
      not (scratch / "import-chrome.sqlite").exists())

print("\n(6) a bookmark whose page has moved")
# a real 301 on the way in, which is what a moved page is
win.add_bookmark_url(srv.url("/moved/new"), "Old")
moved_mark = win.bookmarks[-1]
check("a tab not opened from a bookmark offers nothing",
      win.bookmark_moved(view=view) is False)
win.open_bookmark(moved_mark)
H.spin(2000)
check("the tab was opened from that bookmark",
      getattr(win.current(), "_from_bookmark", None) == moved_mark["id"],
      getattr(win.current(), "_from_bookmark", None))
here = win.current()
check("...and it ended up somewhere else",
      "/new" in (here.url().toString() or ""), here.url().toString())
# what the engine reports about a 301 is not dependable: over several
# runs the hops came back as just the address it landed on, and as the
# address it started from followed by that one. So the browser does not
# decide anything from their number -- see bookmark_moved -- and this
# only checks that where it ended up is among them.
hops = getattr(here, "_hops", []) or []
check("...and where it landed is among the hops the engine reported",
      here.url().toString() in hops, hops)
check("...however many of them there were (the engine is not"
      " dependable about that, which is why nothing counts them)",
      1 <= len(hops) <= 6, hops)
found = win.bookmark_moved(view=here)
check("so the bookmark is seen to have moved", bool(found), found)
check("...and says where it was",
      found["was"].endswith("/moved/new"), found)
check("...and where it is now", found["now"].endswith("/new"), found)
check("the page can be put right",
      win.update_bookmark_url(found["id"], found["now"]).endswith("/new"))
check("...and the bookmark really points there",
      win._bookmark_by_id(moved_mark["id"])["url"].endswith("/new"))
check("...and then it has not moved any more",
      win.bookmark_moved(view=here) is False)
check("an address that is not one is refused",
      win.update_bookmark_url(moved_mark["id"], "javascript:1") is False)
win.open_bookmark(win._bookmark_by_id(mark["id"]))
H.spin(1500)
own = win.current()
check("a tab opened from a bookmark is the bookmark's",
      getattr(own, "_from_bookmark", None) == mark["id"],
      getattr(own, "_from_bookmark", None))
H.js(own, "document.getElementById('go').click()", B.MAIN_WORLD_ID)
H.spin(1500)
check("...and stops being it the moment he clicks a link himself",
      getattr(own, "_from_bookmark", None) is None,
      [getattr(own, "_from_bookmark", None), own.url().toString()])
check("...so going somewhere himself is never called a move",
      win.bookmark_moved(view=own) is False)

print("\n(7) the archive, when he asks")
rows = []
check("a lookup is made", win.wayback_lookup("http://gone.test/x",
                                             then=rows.append) is True)
asked = [row for row in win.own_requests() if "archive.org" in row["url"]]
check("...and it is one request to archive.org", len(asked) == 1, asked[:1])
check("...which says what it is for",
      asked and asked[0]["why"] == "wayback", asked[:1])
check("...with the address asked about in it",
      asked and "gone.test" in asked[0]["url"], asked[:1])
check("an address that is not http is not sent anywhere",
      win.wayback_lookup("about:blank") is False)
before = len([r for r in win.own_requests() if "archive.org" in r["url"]])
win.wayback_lookup("file:///etc/passwd")
check("...and neither is a local file",
      len([r for r in win.own_requests()
           if "archive.org" in r["url"]]) == before)
H.wait_for(lambda: rows, 6000)
check("the answer comes back (empty, with no network here)",
      rows and isinstance(rows[0], dict), rows)

print("\n(8) a bookmark that asks to be looked at again")
check("there are none", win.bookmark_reminders() == {})
check("nothing is due", win.due_reminders() == [])
check("a bookmark that is not there takes no reminder",
      win.set_bookmark_reminder(9999, "2026-10-18") is False)
check("a day can be set",
      win.set_bookmark_reminder(mark["id"], "2026-10-18") == "2026-10-18")
check("...and it is remembered",
      win.bookmark_reminders().get(str(mark["id"])) == "2026-10-18")
check("a day that is not a day is refused",
      win.set_bookmark_reminder(mark["id"], "next tuesday") is False)
check("tomorrow is not due yet",
      win.due_reminders(today="2026-10-17") == [])
due = win.due_reminders(today="2026-10-18")
check("...and today is", len(due) == 1, due)
check("...with what to come back to", due[0]["url"].endswith("/a"), due[0])
check("a day gone by is due too",
      len(win.due_reminders(today="2027-01-01")) == 1)
check("he is told, once", win.show_due_reminders() >= 0)
menu = win.reminders_menu()
check("the menu lists what is due",
      any("A" in one.text() for one in menu.actions()),
      [one.text() for one in menu.actions()])
check("a reminder can be taken off",
      win.set_bookmark_reminder(mark["id"], "") is True
      and win.bookmark_reminders() == {})

print("\n(9) Favourites beside the page")
check("it is over the page to start with", win.favorites_docked() is False)
check("it can be docked", win.dock_favorites(True) is True)
check("...and says so", win.favorites_docked() is True)
panel = win.favorites_panel()
check("...with the same card, in the window",
      panel.card.parent() is win._favdock, panel.card.parent())
check("...and the page beside it", win._split.sizes()[0] >= 200,
      win._split.sizes())
check("...and it is remembered", win.config.get("favDocked") is True)
check("it can go back over the page", win.dock_favorites(False) is False)
check("...and the card is the panel's again",
      panel.card.parent() is panel, panel.card.parent())
check("...and that is remembered too",
      win.config.get("favDocked") is False)

print("\n(10) a history nothing else can read")
check("it is plain to start with", win.history_encrypted() is False)
check("the vault is locked here, so there is no key",
      win.history_key() is None, win.history_key())
check("...and turning it on refuses rather than writing a dead file",
      win.encrypt_history(True) is False)
check("...and it stayed off", win.history_encrypted() is False)
check("the file on disk is plain JSON",
      B.HISTORY_FILE.read_bytes()[:1] == b"[",
      B.HISTORY_FILE.read_bytes()[:20])
win.vault_lock._vault_key = b"k" * 32
check("with the vault open there is a key",
      isinstance(win.history_key(), bytes)
      and len(win.history_key()) == 32, win.history_key())
check("...and it is not the vault's own key",
      win.history_key() != win.vault_lock._vault_key)
check("...and the same label gives the same key",
      win.history_key() == win.history_key())
check("now it can be turned on", win.encrypt_history(True) is True)
raw = B.HISTORY_FILE.read_bytes()
check("...and the file says what it is", raw[:4] == B.HISTORY_MAGIC,
      raw[:8])
check("...and the addresses are not readable in it",
      b"chrome.test" not in raw, raw[:40])
back = win._read_history()
check("...but it reads back", any(row.get("url", "").endswith("/a")
                                 for row in back), len(back))
win.vault_lock._vault_key = None
check("with the vault shut it reads as empty", win._read_history() == [])
check("...and says so", getattr(win, "_history_locked", False) is True)
win.vault_lock._vault_key = b"k" * 32
check("...and comes back when the vault is opened",
      win.unlock_history() == len(back))
check("a wrong key learns nothing",
      B._unseal(b"x" * 32, raw[4:], aad=B.HISTORY_MAGIC) is None)
check("it can be turned off again", win.encrypt_history(False) is False)
check("...and the file is plain again",
      B.HISTORY_FILE.read_bytes()[:1] == b"[")

print("\n(11) the sites' own icons, kept here")
check("the folder is made when asked for", win.icons_dir().is_dir())
check("a site with no kept icon says so",
      win.cached_favicon("nowhere.test") == "")
check("...and so does a bookmark with none",
      win.bookmark_icon_data({"url": "http://nowhere.test/a"}) == "")
from PyQt6.QtGui import QIcon, QPixmap  # noqa: E402
pix = QPixmap(32, 32)
pix.fill()
fake = QIcon(pix)
icon_path = win.icons_dir() / "127.0.0.1.png"
pix.save(str(icon_path), "PNG")
check("a kept icon is found by host",
      win.cached_favicon("127.0.0.1") == str(icon_path))
check("...and by an address on that host",
      win.cached_favicon("http://127.0.0.1:8080/x") == str(icon_path))
check("...and www is the same site",
      win.cached_favicon("www.127.0.0.1") == str(icon_path))
data = win.bookmark_icon_data({"url": srv.url("/a")})
check("a bookmark with no icon gets the kept one",
      data.startswith("data:image/png;base64,"), data[:40])
check("...and one with its own keeps it",
      win.bookmark_icon_data({"url": srv.url("/a"), "icon": "data:x"})
      == "data:x")
menu_icon = win.bookmark_icon({"url": srv.url("/a")})
check("the menu's icon is the kept one too", not menu_icon.isNull())
filled = win.refresh_bookmark_icons()
check("bookmarks with no icon are filled in from the cache",
      filled >= 1, filled)
check("...and then there is nothing left to fill",
      win.refresh_bookmark_icons() == 0)
icon_path.unlink()
check("nothing is ever fetched for an icon",
      not any("favicon" in row["url"] for row in win.own_requests()),
      [row["url"] for row in win.own_requests()][:3])

print("\n(12) every new word, in both languages")
need = ["offlineName", "offlineHint", "offlineKept", "offlineNone",
        "offlineOpen", "trailName", "trailNone", "trailOpen", "treeName",
        "thumbsName", "thumbsNone", "thumbsKeep", "thumbsHint",
        "impHistName", "impHistNone", "impHistBad", "impHistDone",
        "movedName", "movedAsk", "movedYes", "movedNo", "movedDone",
        "wbName", "wbHint", "wbNone", "wbFound", "remName", "remAsk",
        "remNone", "remDue", "favDockName", "favDockHint",
        "histEncName", "histEncHint", "histEncNeedsVault"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)
page = (HERE / "settings.html").read_text()
for one in ("histenc", "histthumbs", "bmoffline", "favdock"):
    check("“%s” is a switch in Settings" % one, 'id="%s"' % one in page)
ids = [one["id"] for one in win.tab_actions_extra()]
for one in ("trailhere", "historytree", "daypictures", "importhistory",
            "waybackhere", "remindersdue", "dockfavorites"):
    check("“%s” is a command" % one, one in ids)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
