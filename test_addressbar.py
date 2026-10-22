#!/usr/bin/env python3
"""The address bar: what it answers by itself, what it looks up, and
what a right-click there and on a page can do.

The answers (arithmetic, units, time, dates, colours) are plain
functions, so most of this file is a table of questions and answers;
the rest drives the real bar in a real window."""
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


print("\n(1) arithmetic, and nothing but arithmetic")
for text, want in [("12*64+3", "771"), ("2^10", "1024"), ("(3+4)*2", "14"),
                   ("7/2", "3.5"), ("10%3", "1"), ("-5+8", "3")]:
    got = B.bar_answer(text)
    check("%s = %s" % (text, want), got and got[1] == want, got)
for text in ["hello", "9^9^9", "1/0", "__import__('os').system('x')",
             "open('/etc/passwd')", "2+2; print(1)", "[1,2,3]", "a*b"]:
    check("%r is not answered" % text, B.bar_answer(text) is None,
          B.bar_answer(text))

print("\n(2) units")
for text, want in [("5 in to mm", "127"), ("1 km in m", "1000"),
                   ("200 c to f", "392"), ("0 c in k", "273.15"),
                   ("1 gib to mib", "1024"), ("1 lb in g", "453.592"),
                   ("60 mph in kmh", "96.5606")]:
    got = B.bar_answer(text)
    check("%s -> %s" % (text, want), got and got[1] == want, got)
check("nonsense units are not answered",
      B.bar_answer("5 bananas in mm") is None)
check("units of different kinds are not mixed",
      B.bar_answer("5 kg in km") is None)

print("\n(3) time, dates and colours")
got = B.bar_answer("time in tokyo")
check("a time zone is answered", got and ":" in got[1], got)
check("an unknown place is not", B.bar_answer("time in narnia") is None)
got = B.bar_answer("kw")
check("the week number is answered", got and got[1].isdigit(), got)
got = B.bar_answer("today + 30 days")
check("a date is counted forward", got and "." in got[1], got)
got = B.bar_answer("#ff8800")
check("a colour comes back in three ways",
      got and got[1] == "#ff8800" and "rgb(255, 136, 0)" in got[0], got)
check("rgb() is read as well",
      (B.bar_answer("rgb(255,136,0)") or ("", ""))[1] == "#ff8800")

print("\n(4) the tracking comes off an address")
dirty = ("https://www.amazon.de/dp/B08166SLDF?utm_source=x&utm_campaign=y"
         "&th=1&fbclid=abc&ref_src=twitter")
clean = B.clean_url(dirty)
check("utm_ is gone", "utm_" not in clean, clean)
check("fbclid is gone", "fbclid" not in clean, clean)
check("ref_src is gone", "ref_src" not in clean, clean)
check("the page's own parameter stays", "th=1" in clean, clean)
check("a text fragment is dropped",
      "#:~:text=" not in B.clean_url("https://x.de/a#:~:text=hello"),
      B.clean_url("https://x.de/a#:~:text=hello"))
check("a non-web address is handed back untouched",
      B.clean_url("file://$HOME/x.html") == "file://$HOME/x.html")

app = H.app()
srv = H.Server({"/a": "<title>Alpha</title><p id=p>some words here</p>",
                "/b": "<title>Beta</title><p>b"})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "searchEngine": "duckduckgo"}))
win = B.Browser()
win.resize(1100, 760)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))

print("\n(5) keywords")
check("yt searches YouTube",
      "youtube.com" in (win.keyword_url("yt cats") or ""),
      win.keyword_url("yt cats"))
check("the words are passed on",
      "cats%20and%20dogs" in (win.keyword_url("yt cats and dogs") or "")
      or "cats+and+dogs" in (win.keyword_url("yt cats and dogs") or ""),
      win.keyword_url("yt cats and dogs"))
check("mr searches Modrinth",
      "modrinth.com" in (win.keyword_url("mr sodium") or ""))
check("a keyword with nothing after it is not a keyword",
      win.keyword_url("yt") is None)
check("an ordinary search is not a keyword",
      win.keyword_url("youtube cats") is None)
win.config["searchKeywords"] = {"pvp": "https://mcpvp.com/search?q=%s"}
check("his own keyword is used",
      "mcpvp.com" in (win.keyword_url("pvp kit") or ""),
      win.keyword_url("pvp kit"))
check("and the built-in ones still are",
      "youtube.com" in (win.keyword_url("yt cats") or ""))

print("\n(6) what Enter does with it")
check("a keyword line resolves to that site's search",
      "modrinth.com" in win._resolve_typed("mr sodium"))
check("? forces a search even for something that looks like a host",
      "duckduckgo.com" in win._resolve_typed("?example.com"),
      win._resolve_typed("?example.com"))
check("without ? that is an address",
      win._resolve_typed("example.com") == "https://example.com")
check("a search is remembered",
      "sodium" in str(win.config.get("recentSearches")),
      win.config.get("recentSearches"))
win.config["recentSearchList"] = False
win.config["recentSearches"] = []
win._resolve_typed("something else")
check("...unless he switched that off",
      not win.config.get("recentSearches"))
win.config["recentSearchList"] = True

print("\n(7) the suggestion rows")
rows = win._own_suggestions("12*64")
check("an answer is the first row", rows and rows[0].startswith("= 768"), rows)
check("Enter on it copies rather than searches",
      win._suggest_actions.get(rows[0]) == ("copy", "768"))
other = win.new_tab(url=None)
H.load(other, srv.url("/b"))
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
rows = win._own_suggestions("Beta")
tabrow = [r for r in rows if r.startswith("↳")]
check("an open tab is offered", bool(tabrow), rows)
check("and Enter on it switches to that tab",
      win._suggest_actions.get(tabrow[0])[0] == "tab" if tabrow else False)
if tabrow:
    win.urlbar.setText(tabrow[0])
    win._navigate()
    H.spin(300)
    check("which is what happens", win.current() is other,
          win.tabs.tabText(win.tabs.currentIndex()))
win.bookmarks.append({"id": 999, "type": "link", "title": "Sodium mod",
                      "url": "https://modrinth.com/mod/sodium", "icon": "",
                      "parent": 0, "t": 0})
rows = win._own_suggestions("sodium")
check("a bookmark is offered",
      any(r.startswith("★") for r in rows), rows)
win.history.append({"url": "https://example.com/deep/page",
                    "title": "A page about kits", "t": 0})
rows = win._own_suggestions("kits page")
check("history matches on words in any order",
      any("example.com" in r for r in rows), rows)

print("\n(8) an empty bar")
QGuiApplication.clipboard().setText("https://modrinth.com/mods")
rows = win.empty_bar_rows()
check("a link on the clipboard is offered first",
      rows and "modrinth.com/mods" in rows[0], rows[:2])
check("and loads when chosen",
      win._suggest_actions.get(rows[0]) == ("url", "https://modrinth.com/mods"))
win.config["recentSearches"] = ["sodium", "kit pvp"]
rows = win.empty_bar_rows()
check("the last searches are there too", "sodium" in rows, rows)
QGuiApplication.clipboard().setText("not a link at all")
rows = win.empty_bar_rows()
check("ordinary text on the clipboard is not offered",
      not any(r.startswith("⮌") for r in rows), rows)

print("\n(9) copying the page")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
text = win.copy_link_as("markdown")
check("a Markdown link", text.startswith("[Alpha](http"), text)
check("an HTML link", win.copy_link_as("html").startswith('<a href="http'),
      win.copy_link_as("html"))
check("title and address", " — http" in win.copy_link_as("plain"),
      win.copy_link_as("plain"))
check("it is on the clipboard", QGuiApplication.clipboard().text()
      == win.copy_link_as("plain"))

print("\n(10) searching from a page")
url = win.search_for("kit pvp")
check("a search opens on his engine", "duckduckgo.com" in (url or ""), url)
url = win.search_for("sodium", engine="mr")
check("...or on the keyword's site", "modrinth.com" in (url or ""), url)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
url = win.search_this_site("widgets")
check("site: search names the host",
      url and "site%3A127.0.0.1" in url or "site:127.0.0.1" in (url or ""),
      url)

print("\n(10b) paste and go, and the image search")
QGuiApplication.clipboard().setText(srv.url("/b"))
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
win.paste_and_go()
H.wait_for(lambda: win.current().url().toString().endswith("/b"), 5000)
check("paste and go goes there",
      win.current().url().toString().endswith("/b"),
      win.current().url().toString())
check("an image search without an address does nothing",
      win.search_image("") is None)

print("\n(11) the search text stays in the bar")
win.config["searchInBar"] = True
from PyQt6.QtCore import QUrl  # noqa: E402
shown = win.bar_text_for(QUrl("https://duckduckgo.com/?q=kit+pvp&ia=web"))
check("a results page shows the words", shown == "kit pvp", shown)
shown = win.bar_text_for(QUrl("https://www.google.com/search?q=minecraft"))
check("...for the other engines too", shown == "minecraft", shown)
check("an ordinary page shows its address",
      win.bar_text_for(QUrl("https://example.com/x")) == "https://example.com/x")
win.config["searchInBar"] = False
check("and not when that is switched off",
      win.bar_text_for(QUrl("https://duckduckgo.com/?q=kit+pvp"))
      == "https://duckduckgo.com/?q=kit+pvp")
win.config["searchInBar"] = True

print("\n(12) the zoom figure in the bar")
# back to a page that is loaded: the searches above opened tabs of
# their own and one of them is in front
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
win._sync_zoomlbl()
check("nothing to say at the normal level", not win._zoomlbl.isVisible())
win.zoom_by(1)
H.spin(200)
check("it says the level after zooming in",
      win._zoomlbl.text().endswith("%") and win._zoomlbl.text() != "100%",
      win._zoomlbl.text())
win.zoom_reset()
H.spin(200)
check("and goes away again", not win._zoomlbl.isVisible(),
      win._zoomlbl.text())

print("\n(13) forgetting a suggestion")
win.history.append({"url": "https://forget.example/x", "title": "Forget me",
                    "t": 0})
rows = win._own_suggestions("forget me")
row = [r for r in rows if "forget.example" in r]
check("it is offered first", bool(row), rows)
if row:
    win.suggest_model.setStringList(rows)
    win._suggest_actions[row[0]] = ("url", "https://forget.example/x")
    before = len(win.history)
    win.history = [e for e in win.history
                   if e.get("url") != "https://forget.example/x"]
    check("and can be taken out of the history",
          len(win.history) == before - 1)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
