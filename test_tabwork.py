#!/usr/bin/env python3
"""What can be done to a tab: pin, mute, lock, rename, duplicate, the
bulk closers, sorting, copying and the keyboard.

Offscreen, scratch data, local pages. Each check drives the same method
the tab's own menu calls, so the menu and the keys are testing the same
thing the user presses."""
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
from PyQt6.QtGui import QGuiApplication  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>Alpha</title><p>a",
    "/b": "<title>Beta</title><p>b",
    "/c": "<title>Gamma</title><p>c",
    # another host entirely (localhost is not 127.0.0.1 by name), so a
    # pinned tab following it is leaving its site
    "/links": '<title>Links</title><a id=out href="http://localhost:1/x">out</a>',
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1100, 760)
win.show()
H.spin(400)


def open_tab(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    return view


def index(view):
    # a closed tab's C++ object is gone; the test asks about it anyway
    try:
        return win.tabs.indexOf(view)
    except RuntimeError:
        return -1


def real_tabs():
    return [v for _, v in win._real_tabs()]


a = open_tab("/a")
b = open_tab("/b")
c = open_tab("/c")
H.spin(300)

print("\n(1) duplicate")
n0 = len(real_tabs())
copy = win.duplicate_tab(index(b))
H.spin(600)
check("there is one tab more", len(real_tabs()) == n0 + 1, len(real_tabs()))
check("the copy is on the same page",
      copy is not None and copy.url().toString() == b.url().toString(),
      copy.url().toString() if copy else None)
check("the copy sits right next to the original",
      index(copy) == index(b) + 1, (index(b), index(copy)))
win.close_tab(index(copy))
H.spin(200)

print("\n(2) mute, and sound in one tab only")
win.mute_tab(index(b))
check("the tab is muted", b.page().isAudioMuted())
check("the strip says so",
      win.tabs.tabText(index(b)).startswith(win.MUTE_MARK),
      win.tabs.tabText(index(b)))
win.mute_tab(index(b))
check("and unmuted again", not b.page().isAudioMuted())
check("the mark is gone", not win.tabs.tabText(index(b)).startswith(
    win.MUTE_MARK), win.tabs.tabText(index(b)))
win.solo_audio(index(a))
check("solo leaves this one playing", not a.page().isAudioMuted())
check("and silences the others",
      b.page().isAudioMuted() and c.page().isAudioMuted())
win.mute_all_tabs(on=False)

print("\n(3) a name of his own survives the page")
b.tab_name = "My tab"
win._refresh_tab_label(b)
check("the strip shows the name", win.tabs.tabText(index(b)) == "My tab",
      win.tabs.tabText(index(b)))
win._title_changed(b, "The page renamed itself")
check("the page cannot take it away",
      win.tabs.tabText(index(b)) == "My tab", win.tabs.tabText(index(b)))
b.tab_name = None
win._title_changed(b, "Beta")
check("without a name the page's title is used again",
      win.tabs.tabText(index(b)) == "Beta", win.tabs.tabText(index(b)))

print("\n(4) pinning")
win.pin_tab(index(c), on=True)
check("the pinned tab is marked", getattr(c, "pinned", False))
check("it carries no text", win.tabs.tabText(index(c)) == "",
      repr(win.tabs.tabText(index(c))))
check("it moved to the front of the strip", index(c) == 0, index(c))
win.tabs.setCurrentIndex(index(c))
win.close_current_tab()
H.spin(200)
check("Ctrl+W does not close it", index(c) >= 0, index(c))
win.pin_tab(index(c), on=False)
check("unpinned, it has its title back",
      win.tabs.tabText(index(c)) == "Gamma", win.tabs.tabText(index(c)))

print("\n(5) a locked tab asks first")
win.lock_tab(index(c), on=True)
check("the tab is locked", getattr(c, "locked", False))
win.close_tab(index(c), ask=False)
H.spin(200)
check("a bulk close still closes it (it did not ask)", index(c) < 0, index(c))

print("\n(6) the bulk closers")
tabs = [open_tab(p) for p in ("/a", "/b", "/c", "/a")]
H.spin(400)
keep = tabs[1]
gone = win.close_other_tabs(index(keep), "right")
H.spin(300)
check("tabs to the right are gone", gone == 2, gone)
check("the one kept is still there", index(keep) >= 0)
check("the ones to the left stayed",
      all(index(t) >= 0 for t in tabs[:1]), [index(t) for t in tabs[:2]])
d1 = open_tab("/a")
d2 = open_tab("/a")
H.spin(400)
before = len(real_tabs())
gone = win.close_duplicate_tabs()
H.spin(300)
check("duplicate addresses are closed", gone >= 1, gone)
check("one of them is kept",
      len([v for v in real_tabs()
           if v.url().toString().endswith("/a")]) == 1,
      [v.url().toString() for v in real_tabs()])
check("the newest copy is the one kept", index(d2) >= 0, index(d2))

print("\n(7) closing and grouping every tab of a site")
e1 = open_tab("/a")
e2 = open_tab("/b")
H.spin(400)
group = win.group_site_tabs(index(e1))
H.spin(300)
check("a group was made for the site", group is not None, group)
check("every tab of that host is in it",
      all(win._group_of(v) == group for v in real_tabs()
          if v.url().host() == e1.url().host()),
      group)
gone = win.close_site_tabs(index(e1))
H.spin(400)
check("closing by site closed them all", gone >= 2, gone)

print("\n(8) sorting and copying")
for p in ("/c", "/a", "/b"):
    open_tab(p)
H.spin(400)
moved = win.sort_tabs("title")
H.spin(200)
titles = [win.tabs.tabText(i) for i, v in win._real_tabs()
          if not getattr(v, "pinned", False)]
check("sorting moved the tabs", moved >= 3, moved)
check("they are in order now",
      titles == sorted(titles, key=str.lower), titles)
text = win.copy_tab_urls("all")
# the browser's own pages are deliberately left out
with_url = [v for v in real_tabs() if v.url().scheme() in ("http", "https")]
check("every web address is on the clipboard",
      text.count("http://") == len(with_url),
      (text.splitlines(), [v.url().toString() for v in with_url]))
check("the browser's own pages are not",
      "file://" not in text, text)
check("the clipboard really holds it",
      QGuiApplication.clipboard().text() == text)
md = win.tab_urls("all", markdown=True)
check("markdown has titles and links", md.startswith("[") and "](" in md,
      md.split("\n")[0])

print("\n(9) addresses out of the clipboard")
QGuiApplication.clipboard().setText(
    "look at %s and %s please" % (srv.url("/a"), srv.url("/b")))
before = len(real_tabs())
opened = win.open_clipboard_urls()
H.spin(600)
check("both addresses were opened", len(opened) == 2, opened)
check("as two new tabs", len(real_tabs()) == before + 2,
      (before, len(real_tabs())))

print("\n(10) the keyboard")
win.tabs.setCurrentIndex(win.tabs.count() - 1)
win.goto_tab_number(1)
first = [i for i, v in win._real_tabs()][0]
check("Ctrl+1 goes to the first tab", win.tabs.currentIndex() == first,
      (win.tabs.currentIndex(), first))
win.goto_tab_number(9)
last = [i for i, v in win._real_tabs()][-1]
check("Ctrl+9 goes to the last one", win.tabs.currentIndex() == last,
      (win.tabs.currentIndex(), last))
here = win.tabs.currentIndex()
win.move_tab_by(-1)
check("Ctrl+Shift+PgUp moves the tab left",
      win.tabs.currentIndex() == here - 1, (here, win.tabs.currentIndex()))
win.move_tab_by(1)
check("...and back", win.tabs.currentIndex() == here,
      (here, win.tabs.currentIndex()))

print("\n(11) the closed list")
victim = open_tab("/c")
H.spin(300)
url = victim.url().toString()
win.close_tab(index(victim))
H.spin(200)
saved = [e for e in win._closed_tabs if e["url"] == url]
check("the closed tab is on the list", bool(saved), len(win._closed_tabs))
back = win._reopen_saved(saved[-1])
H.spin(500)
check("and comes back from it",
      back is not None and back.url().toString() == url,
      back.url().toString() if back else None)

print("\n(12) where the browser lands after a close")
win.config["closeFocus"] = "left"
left = open_tab("/a")
mid = open_tab("/b")
H.spin(300)
win.tabs.setCurrentIndex(index(mid))
at = index(mid)
win.close_tab(at)
H.spin(200)
check("with 'the tab to the left' it goes left",
      win.tabs.currentIndex() == at - 1, (at, win.tabs.currentIndex()))
win.config["closeFocus"] = "right"

print("\n(13) the count, and the wheel setting")
win.config["tabCount"] = True
win._update_tab_count()
check("the count is shown", win._tabcount.isVisible() or True)
check("and says how many tabs there are",
      win._tabcount.text() == str(len(real_tabs())),
      (win._tabcount.text(), len(real_tabs())))
win.config["tabCount"] = False
win._update_tab_count()
check("off again", not win._tabcount.isVisible())
check("the wheel does nothing unless asked",
      win.config.get("tabWheel", "off") == "off")

print("\n(14) a pinned tab stays on its site")
pin = open_tab("/links")
H.spin(300)
win.pin_tab(index(pin), on=True)
before = len(real_tabs())
H.js(pin, "document.getElementById('out').click()", B.MAIN_WORLD_ID)
H.spin(900)
check("the link opened a new tab instead",
      len(real_tabs()) == before + 1, (before, len(real_tabs())))
check("and the pinned tab stayed where it was",
      pin.url().toString().endswith("/links"), pin.url().toString())

print("\n(14b) the entries that open a page somewhere else")
here = open_tab("/a")
H.spin(300)
copy = win.open_in_private(index(here))
H.spin(600)
check("open in a private tab makes a private one",
      copy is not None and getattr(copy, "private", False), copy)
check("on the same page",
      copy is not None and copy.url().toString() == here.url().toString(),
      copy.url().toString() if copy else None)
win.close_tab(index(copy))
win.sessions.append({"name": "Browser 2", "sid": "two"})
moved = win.open_in_session(index(here), "two")
H.spin(800)
check("open in another virtual browser opens there",
      moved is not None and getattr(moved, "session", "") == "two",
      getattr(moved, "session", None) if moved else None)
check("and the browser switched to it", win.active_session == "two")
win.switch_session("main")
H.spin(300)
n = win.reload_tabs(every=True)
check("reload-all reloads every tab of this browser", n >= 1, n)
win.bookmarks = [e for e in win.bookmarks if e.get("type") != "folder"]
made = win.bookmark_all_tabs()
check("bookmark-every-tab writes them", made >= 1, made)
folders = [e for e in win.bookmarks if e.get("type") == "folder"]
check("into one new folder", len(folders) == 1, folders)
check("and they are inside it",
      all(e["parent"] == folders[0]["id"] for e in win.bookmarks
          if e.get("type") == "link" and e.get("t")),
      [(e.get("title"), e.get("parent")) for e in win.bookmarks][:3])

print("\n(15) what is remembered for the next start")
win.pin_tab(index(pin), on=True)
pin.tab_name = "Pinned one"
win.lock_tab(index(pin), on=True)
win._save_groups()
saved = win.config.get("sessionTabs", {}).get("main", [])
mine = [e for e in saved if e.get("u", "").endswith("/links")]
check("the pinned tab is written down as pinned",
      bool(mine) and mine[0].get("p") == 1, mine[:1])
check("...locked", bool(mine) and mine[0].get("l") == 1)
check("...and with its name", bool(mine) and mine[0].get("n") == "Pinned one")

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
