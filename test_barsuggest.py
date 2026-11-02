#!/usr/bin/env python3
"""What he searched for yesterday is not offered to him today, and the
drop-down never takes the Enter key off him.

Reported through the coordinator on 2026-11-02: typing in the address
bar pops up a chooser listing things he had googled, and "focus gets
stuck on it -- he can't just type and hit Enter". He had typed
"i like pancakes" a few times and it kept coming back.

6221736 had already dropped the recentSearches list and the rows an
empty bar showed. This is the half that was left, and it is the half
that was never a list: a results page sits in the history like any
other page, and the TITLE of a results page is the query. So the
ordinary history row built the search back up out of nothing kept on
purpose. Driven here, before the fix, with one google.com/search entry
in the history:

    _own_suggestions("i like") -> ["i like pancakes - Google Search
                                   - https://www.google.com/search?..."]
    _own_suggestions("panc")   -> the same row

The second half, measured the same way. The drop-down opened with row 0
already current, and on a real desktop the popup holds the keyboard, so
Enter reaches the POPUP, not the bar. QCompleter then activates row 0:

    typed  "i like pancakes", pressed Enter
    loaded "https://www.google.com/search?q=i like pancakes"
    bar now holds that address, not his sentence

He had not chosen that row. That is the trap -- not focus that cannot
be escaped, but Enter going somewhere he did not type."""
import ast
import io
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
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


print("\n(1) which addresses are a record of a search")
SEARCHES = [
    "https://www.google.com/search?q=i+like+pancakes",
    "https://google.de/search?q=wetter",
    "https://news.google.com/search?q=pancakes",
    "https://duckduckgo.com/?q=how+to+cook+pancakes",
    "https://html.duckduckgo.com/html/?q=x",
    "https://www.bing.com/search?q=x",
    "https://search.brave.com/search?q=x",
    "https://www.ecosia.org/search?q=x",
    "https://www.startpage.com/sp/search?query=x",
    "https://search.yahoo.com/search?p=x",
    "https://yandex.com/search/?text=x",
    "https://www.baidu.com/s?wd=x",
]
for url in SEARCHES:
    check("a search: %s" % url[:52], B.is_search_result(url), url)
NOT_SEARCHES = [
    # an engine's own site, with nothing searched
    "https://www.google.com/",
    "https://duckduckgo.com/",
    # an engine host doing something that is not a search: these are
    # pages he went to, and dropping them would be a worse bug than
    # the one being fixed
    "https://www.google.com/maps?q=berlin",
    "https://mail.google.com/mail/u/0/#inbox",
    "https://docs.google.com/document/d/abc/edit",
    "https://drive.google.com/drive/my-drive",
    "https://brave.com/download/",
    # an ordinary page that happens to carry a q
    "https://modrinth.com/mods?q=sodium",
    "https://example.com/search?q=widgets",
    # a search ON a site, which is a page he went to and which the
    # keyword table (gh, so, mo) opens on purpose: the host is not an
    # engine, so none of these are touched
    "https://github.com/search?q=pancakes",
    "https://stackoverflow.com/search?q=pancakes",
    "https://modrinth.com/mods?q=sodium",
    "https://namemc.com/search?q=pancake",
    "https://www.youtube.com/results?search_query=pancakes",
    "",
    "not a url at all",
]
for url in NOT_SEARCHES:
    check("not a search: %r" % url[:52], not B.is_search_result(url), url)

app = H.app()
srv = H.Server({"/a": "<title>Alpha</title><p>words</p>",
                "/b": "<title>Beta</title><p>more</p>"})
win = B.Browser()
win.show()
view = win.current()
H.spin(400)
# no network in here: the engine's own live suggestions are a separate
# feature behind a separate setting, and this file is about the rows
# the browser builds itself.
win.config["searchSuggestions"] = False

PAST = [
    {"url": "https://www.google.com/search?q=i+like+pancakes",
     "title": "i like pancakes - Google Search", "t": 0},
    {"url": "https://duckduckgo.com/?q=how+to+cook+pancakes",
     "title": "how to cook pancakes at DuckDuckGo", "t": 0},
    {"url": "https://www.bing.com/search?q=kit+pvp+server",
     "title": "kit pvp server - Bing", "t": 0},
]
KEPT = {"url": "https://modrinth.com/mod/sodium",
        "title": "Sodium - Minecraft Mod", "t": 0}
win.history.extend(PAST + [KEPT])

print("\n(1b) every shipped engine, through its own template")
for key, (name, pattern) in B.SEARCH_ENGINES.items():
    url = pattern.format("i+like+pancakes")
    check("%s: %s" % (name, url[:46]),
          B.search_query_of(url) == "i like pancakes", B.search_query_of(url))
    front = B.QUrl(url)
    front.setQuery("")
    check("...but %s's own front page is not a search" % name,
          not B.is_search_result(front.toString()), front.toString())

print("\n(1c) and it is the query itself, decoded in the right order")
for raw, want in [("i+like+pancakes", "i like pancakes"),
                  ("a%2Bb", "a+b"),
                  ("c%2B%2B", "c++"),
                  ("a+b", "a b"),
                  ("caf%C3%A9+au+lait", "caf\u00e9 au lait"),
                  ("100%25+sure", "100% sure"),
                  ("a%20b", "a b"),
                  ("%E2%9C%93+ok", "\u2713 ok")]:
    got = B.search_query_of("https://www.google.com/search?q=" + raw)
    check("?q=%s reads as %r" % (raw, want), got == want, got)
check("a map is not a search", B.search_query_of(
    "https://www.google.com/maps?q=berlin") == "", B.search_query_of(
    "https://www.google.com/maps?q=berlin"))

print("\n(1d) a seventh engine is covered by being in the table")
# the only check that the table walk is load-bearing: this host's name
# is in no word list and its parameter is in no key list, so nothing
# but the walk can find it. Without this the walk could be deleted and
# every other check here would still pass -- which is what happened
# when it was first mutated.
B.SEARCH_ENGINES["nonsuch"] = ("Nonsuch",
                               "https://finderoo.example/find?term={}")
try:
    check("its results page is a search",
          B.is_search_result("https://finderoo.example/find?term=pancakes"))
    check("and the query comes back out",
          B.search_query_of(
              "https://finderoo.example/find?term=i+like+pancakes")
          == "i like pancakes")
    check("while its front page is not",
          not B.is_search_result("https://finderoo.example/"))
finally:
    del B.SEARCH_ENGINES["nonsuch"]

print("\n(1e) and an engine he added himself")
win_cfg = None
check("an own engine's results page is a search",
      B.is_search_result("https://finderoo.example/find?term=pancakes",
                         ["https://finderoo.example/find?term=%s"]))
check("...written with {searchTerms} too",
      B.is_search_result("https://finderoo.example/find?term=pancakes",
                         ["https://finderoo.example/find?term={searchTerms}"]))
check("...and the query comes back out",
      B.search_query_of("https://finderoo.example/find?term=c%2B%2B",
                        ["https://finderoo.example/find?term=%s"]) == "c++")
check("a junk own engine with no slot is ignored, not crashed on",
      B.search_query_of("https://finderoo.example/find?term=x",
                        ["", None, "not a url", "https://x/{brace}"]) == "")
check("and a keyword search is still not a search",
      not B.is_search_result("https://github.com/search?q=pancakes",
                             ["https://finderoo.example/find?term=%s"]))

print("\n(1f) mac's matrix, as it was sent, unchanged")
# browser-mac-8f sent these 12 must-drop / 8 must-keep on 2026-11-02.
# The must-keep half is the valuable half: gh, so, map and namemc are
# live entries in the keyword table and the per-site search map, so
# they are routes this browser offers on purpose.
MAC_DROP = [
    "https://www.google.com/search?q=a",
    "https://www.google.de/search?q=a",
    "https://www.google.co.uk/search?q=a",
    "https://news.google.com/search?q=a",
    "https://duckduckgo.com/?q=a",
    "https://html.duckduckgo.com/html/?q=a",
    "https://lite.duckduckgo.com/lite/?q=a",
    "https://www.bing.com/search?q=a",
    "https://www.bing.de/search?q=a",
    "https://search.brave.com/search?q=a",
    "https://www.ecosia.org/search?q=a",
    "https://www.startpage.com/sp/search?query=a",
]
MAC_KEEP = [
    "https://github.com/search?q=a",
    "https://stackoverflow.com/search?q=a",
    "https://namemc.com/search?q=a",
    "https://www.reddit.com/search?q=a",
    "https://modrinth.com/mods?q=a",
    "https://www.openstreetmap.org/search?query=a",
    "https://en.wikipedia.org/w/index.php?search=a",
    "https://docs.python.org/3/library/os.html",
]
for url in MAC_DROP:
    check("drop: " + url[8:58], B.is_search_result(url), url)
for url in MAC_KEEP:
    check("keep: " + url[8:58], not B.is_search_result(url), url)
# and the cases mac's own prototype has no case for: it has no path
# gate, so every google.* address carrying a q drops under it. Sent
# back to them rather than fixed here.
for url in ["https://www.google.com/maps?q=berlin",
            "https://www.google.com/finance?q=AAPL",
            "https://drive.google.com/drive/search?q=invoice",
            "https://www.google.com/maps/search/?api=1&query=berlin"]:
    check("keep: " + url[8:58], not B.is_search_result(url), url)

print("\n(2) a past search is never a row")
for typed in ("i li", "i like", "i like pancakes", "panc", "pancakes",
              "how to", "cook", "kit pvp", "google", "duckduckgo",
              "bing", "search"):
    rows = win._own_suggestions(typed)
    bad = [r for r in rows
           if "pancake" in r.lower() or "kit pvp" in r.lower()
           or "/search?" in r or "?q=" in r]
    check("typing %r offers nothing he searched for" % typed, not bad, bad)

print("\n(3) and the rest of the drop-down still works")
rows = win._own_suggestions("sodium")
check("a page he actually visited is still offered",
      any("modrinth.com/mod/sodium" in r for r in rows), rows)
win.bookmarks.append({"id": 999, "type": "link", "title": "Pancake recipes",
                      "url": "https://example.com/pancakes", "icon": "",
                      "parent": 0, "t": 0})
rows = win._own_suggestions("pancake")
check("a bookmark is still offered, even one about pancakes",
      any(r.startswith("★") for r in rows), rows)
other = win.new_tab(url=srv.url("/b"))
H.spin(600)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(100)
rows = win._own_suggestions("Beta")
check("an open tab is still offered",
      any(r.startswith("↳") for r in rows), rows)
check("arithmetic still answers", any("=" in r
      for r in win._own_suggestions("12*64")),
      win._own_suggestions("12*64"))
QGuiApplication.clipboard().setText("https://modrinth.com/mods")
rows = win.empty_bar_rows()
check("an empty bar still offers a link on the clipboard",
      rows and "modrinth.com/mods" in rows[0], rows[:2])

check("an empty bar with nothing on the clipboard offers nothing",
      (QGuiApplication.clipboard().setText("just some words"),
       win.empty_bar_rows())[1] == [], win.empty_bar_rows())
# the filter must not hang off searchSuggestions: that flag only gates
# the engine's remote suggest call, and the rows come out of his own
# history either way. Measured on the shipped code by mac, and the
# reason "switch the setting off" was never the fix.
win.config["searchSuggestions"] = True
rows = win._own_suggestions("i like")
check("and the filter does not hang off searchSuggestions",
      not any("pancake" in r.lower() for r in rows), rows)
win.config["searchSuggestions"] = False

print("\n(4) the Enter key stays his")
loads = []
real_resolve = win._resolve_typed
win._resolve_typed = lambda t: loads.append(t) or real_resolve(t)


def arm(text):
    loads.clear()
    win.urlbar.setFocus()
    H.spin(40)
    win.urlbar.setText(text)
    win._fetch_suggestions()
    H.spin(120)
    return win.completer.popup()


popup = arm("pancake")
check("the drop-down is open", popup.isVisible())
check("with rows in it", len(win.suggest_model.stringList()) > 0,
      win.suggest_model.stringList())
check("and no row picked", popup.currentIndex().row() == -1,
      popup.currentIndex().row())
# the popup is where the key lands on a real desktop: it is shown, so
# it holds the keyboard. Sending it to the bar instead would test the
# one path that was never broken.
QTest.keyClick(popup, Qt.Key.Key_Return)
H.spin(250)
check("Enter navigates to what he typed", loads == ["pancake"], loads)
check("and the bar still holds what he typed",
      win.urlbar.text() == "pancake", win.urlbar.text())

popup = arm("pancake")
QTest.keyClick(popup, Qt.Key.Key_Down)
H.spin(80)
check("Down picks the first row", popup.currentIndex().row() == 0,
      popup.currentIndex().row())
QTest.keyClick(popup, Qt.Key.Key_Return)
H.spin(250)
check("and then Enter takes that row",
      loads and loads[0].startswith("https://example.com/pancakes"), loads)

popup = arm("pancake")
QTest.keyClick(popup, Qt.Key.Key_Escape)
H.spin(80)
check("Escape closes the drop-down", not popup.isVisible())
win.urlbar.setFocus()
win.urlbar.setText("i like pancakes")
loads.clear()
win._navigate()
H.spin(250)
check("and a plain search still runs",
      loads == ["i like pancakes"], loads)
check("on his engine",
      "duckduckgo" in (win.search_for("i like pancakes") or "")
      or "google" in (win.search_for("i like pancakes") or ""),
      win.search_for("i like pancakes"))

print("\n(5) one owner, so the next row cannot arrive pre-picked")
TREE = ast.parse(io.open(HERE / "browser.py", encoding="utf-8").read())
owners = set()
for fn in ast.walk(TREE):
    if not isinstance(fn, ast.FunctionDef):
        continue
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "complete"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "completer"):
            owners.add(fn.name)
check("only _show_rows opens the drop-down", owners == {"_show_rows"},
      sorted(owners))
show = [f for f in ast.walk(TREE)
        if isinstance(f, ast.FunctionDef) and f.name == "_show_rows"]
check("_show_rows exists once", len(show) == 1, len(show))
if show:
    body = ast.dump(show[0])
    check("and clears the current row after opening",
          "setCurrentIndex" in body and "clearSelection" in body)
# the sentinel is how a template is matched, so only the one function
# that owns the matching may name it. bar_text_for walked the table
# itself until 2026-11-02 and this is what stops it coming back: two
# implementations of one question, with one of them live, is the bug
# _migrate_tabclick_config was written about.
sentinel = set()
for fn in ast.walk(TREE):
    if not isinstance(fn, ast.FunctionDef):
        continue
    if any(isinstance(n, ast.Name) and n.id == "_SEARCH_SENTINEL"
           for n in ast.walk(fn)):
        sentinel.add(fn.name)
check("only two functions know how a template is matched",
      sentinel == {"search_query_of", "_engine_result_urls"},
      sorted(sentinel))
bar = [f for f in ast.walk(TREE)
       if isinstance(f, ast.FunctionDef) and f.name == "bar_text_for"]
check("bar_text_for asks search_query_of",
      bool(bar) and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "search_query_of"
                        for n in ast.walk(bar[0])))
check("...and does not walk the engine table itself",
      bool(bar) and not any(isinstance(n, ast.Name)
                            and n.id == "SEARCH_ENGINES"
                            for n in ast.walk(bar[0])))
hist = [f for f in ast.walk(TREE)
        if isinstance(f, ast.FunctionDef) and f.name == "_own_suggestions"]
check("_own_suggestions asks is_search_result",
      bool(hist) and any(isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name)
                         and n.func.id == "is_search_result"
                         for n in ast.walk(hist[0])))

srv.stop()
print()
if fails:
    print("%d FAILED:" % len(fails))
    for one in fails:
        print("  - " + one)
    sys.exit(1)
print("all ok")
