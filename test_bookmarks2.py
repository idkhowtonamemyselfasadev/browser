#!/usr/bin/env python3
"""The second wave of bookmark and history work: tags, notes,
nicknames, backups, imports, the views the history page draws, and the
tidying-up jobs.

Offscreen, scratch data, local pages. Nothing in here goes online: the
two jobs that do (the dead-link check and the https upgrade) are driven
against a local server started by this test, which is as close to the
real thing as a server on this machine can be."""
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

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>Alpha</title><p>a",
    "/b": "<title>Beta</title><p>b",
    "/long": "<title>Long</title><div style='height:4000px'>long</div>",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
scratch = B.CONFIG_FILE.parent

print("\n(1) a page title, tidied up")
check("a chat count comes off", B._clean_title("(3) #general") == "#general",
      B._clean_title("(3) #general"))
check("a site name comes off the end",
      B._clean_title("Cat video - YouTube") == "Cat video",
      B._clean_title("Cat video - YouTube"))
check("both at once",
      B._clean_title("(12) Inbox | YouTube") == "Inbox",
      B._clean_title("(12) Inbox | YouTube"))
check("an ordinary title is left alone",
      B._clean_title("Alpha") == "Alpha")
check("a title that is only a count keeps something",
      B._clean_title("(3)") == "(3)", B._clean_title("(3)"))

print("\n(2) hops and searches, read out of an address")
check("a login bounce is a hop",
      B._is_noise("https://accounts.google.com/signin"))
check("a link wrapper is a hop", B._is_noise("https://t.co/abcd"))
check("a page he read is not", not B._is_noise("https://gnu.org/x"))
check("a search page says what was searched for",
      B._search_terms("https://www.google.com/search?q=minecraft+server")
      == "minecraft server",
      B._search_terms("https://www.google.com/search?q=minecraft+server"))
check("...on any site that calls it a search",
      B._search_terms("https://modrinth.com/mods?q=sodium") == "sodium",
      B._search_terms("https://modrinth.com/mods?q=sodium"))
check("an ordinary page is no search",
      B._search_terms("https://gnu.org/software/?page=2") == "",
      B._search_terms("https://gnu.org/software/?page=2"))

print("\n(3) the history, filtered")
now = int(time.time())
win.history = [
    {"url": "https://gnu.org/a", "title": "Gnu A", "t": now - 30},
    {"url": "https://gnu.org/b", "title": "Gnu B", "t": now - 7200},
    {"url": "https://example.com/x", "title": "Ex", "t": now - 200000},
    {"url": "https://accounts.google.com/signin", "title": "In",
     "t": now - 60},
    {"url": "https://www.google.com/search?q=cats", "title": "cats",
     "t": now - 90},
    {"url": "https://gnu.org/c", "title": "Gnu C", "t": now - 100,
     "s": "two"},
]
rows = win.history_rows()
check("the hops are left out by default",
      not any("accounts.google" in r["url"] for r in rows), len(rows))
check("newest first", rows[0]["url"].endswith("/a"), rows[0]["url"])
check("a search finds by title", len(win.history_rows(query="gnu b")) == 1,
      len(win.history_rows(query="gnu b")))
check("a site filter takes its sub-domains too",
      len(win.history_rows(host="gnu.org")) == 3,
      len(win.history_rows(host="gnu.org")))
check("a date range cuts it down",
      len(win.history_rows(since=now - 3600)) == 3,
      len(win.history_rows(since=now - 3600)))
check("one virtual browser at a time",
      len(win.history_rows(session="two")) == 1)
check("and the hops come back when asked",
      any("accounts.google" in r["url"]
          for r in win.history_rows(noise=True)))

print("\n(4) the days, the sites, the searches, the sums")
days = win.history_days()
check("the timeline has a row per day", len(days) >= 2, len(days))
check("each day counts its pages", all(d["pages"] >= 1 for d in days), days)
top = win.most_visited()
check("the most visited site is the one with three pages",
      top and top[0]["host"] == "gnu.org", top[:2])
check("a hop is never counted as a site",
      not any(r["host"] == "accounts.google.com" for r in top), top)
queries = win.search_queries()
check("his searches are in the list",
      any(q["q"] == "cats" for q in queries), queries)
stats = win.browsing_stats(7)
check("the statistics cover seven days", len(stats["days"]) == 7)
check("and count the pages", stats["pages"] >= 4, stats["pages"])
check("with the busiest sites named", stats["sites"][0]["host"] == "gnu.org",
      stats["sites"][:2])
grouped = win.group_history_by_site()
check("grouping by site folds the three gnu pages into one row",
      any(g["host"] == "gnu.org" and len(g["rows"]) == 3 for g in grouped),
      [(g["host"], len(g["rows"])) for g in grouped])

print("\n(5) what a page was, and how often")
info = win.visit_info("https://gnu.org/a")
check("a page knows it was visited once", info["count"] == 1, info)
check("and when", info["last"] == now - 30, info)
check("a page never visited says so",
      win.visit_info("https://nowhere.test")["count"] == 0)
streak = win.site_streak("gnu.org")
# as many days in a row as the fixture actually covers: "two hours ago"
# is yesterday when this runs just after midnight, which is how this
# check first failed
gnu_days = len({B._day_start(e["t"]) for e in win.history
                if "gnu.org" in e["url"]})
check("the streak is every day the site was visited",
      streak["streak"] == gnu_days, (streak, gnu_days))
check("and its visits are counted", streak["visits"] == 3, streak)

print("\n(6) forgetting")
gone = win.delete_history_entries(["https://gnu.org/b"])
check("one page can be forgotten", gone == 1, gone)
check("...and is not in the list", not any(
    r["url"].endswith("/b") for r in win.history_rows()))
back = win.undo_history_delete()
check("and the delete can be taken back", back == 6, back)
gone = win.forget_history_site("gnu.org")
check("a whole site goes in one step", gone == 3, gone)
win.undo_history_delete()
gone = win.delete_history_range(since=now - 3600)
check("so does a time range", gone == 4, gone)
win.undo_history_delete()
check("clearing it all is undoable too",
      win.clear_history() == 6 and win.undo_history_delete() == 6)
win.history.append({"url": "https://old.test/x", "title": "Old",
                    "t": now - 40 * 86400})
check("history older than he wants kept is pruned",
      win.prune_history(days=30) == 1, len(win.history))
check("0 days means keep everything", win.prune_history(days=0) == 0)

print("\n(7) a tab whose history is paused, and a site never written down")
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))
H.spin(300)
check("a tab can be paused", win.pause_history(view, True) is True)
before = len(win.history)
H.load(view, srv.url("/b"))
H.spin(500)
check("...and nothing of it is written down", len(win.history) == before,
      (before, len(win.history)))
win.pause_history(view, False)
check("a site can be put on this browser's never-record list",
      win.toggle_never_record("127.0.0.1") is True)
check("...and the browser knows it", win.never_record("127.0.0.1"))
before = len(win.history)
H.load(view, srv.url("/a"))
H.spin(500)
check("so that site is not written down either",
      len(win.history) == before, (before, len(win.history)))
check("and it can be taken off again",
      win.toggle_never_record("127.0.0.1") is False
      and not win.never_record("127.0.0.1"))

print("\n(8) the history, written out")
out = scratch / "hist.csv"
wrote = win.export_history(out, "csv")
check("a CSV is written", wrote >= 1 and out.exists(), wrote)
text = out.read_text()
check("with a header and the rows", text.startswith("when,title,url,browser"),
      text[:40])
asjson = scratch / "hist.json"
win.export_history(asjson, "json")
check("and JSON too", json.loads(asjson.read_text())[0].get("url"))

print("\n(9) opening a day of history again")
win.history = [{"url": srv.url("/a"), "title": "Alpha", "t": now - 100},
               {"url": srv.url("/b"), "title": "Beta", "t": now - 200}]
opened = win.restore_day(now - 86400, now)
H.spin(500)
check("every page of that span opens", len(opened) == 2, len(opened))
for v in opened:
    win.close_tab(win.tabs.indexOf(v), ask=False)
opened = win.restore_day(now - 86400, now, as_group="Monday")
H.spin(500)
check("and can land in a group of its own",
      all(win._group_of(v) == "Monday" for v in opened),
      [win._group_of(v) for v in opened])
for v in opened:
    win.close_tab(win.tabs.indexOf(v), ask=False)
H.spin(200)

print("\n(10) carry on where you left off")
later = win.continue_where()
check("it offers something to carry on with", later, later)
check("with a reason for each", all(r["why"] in ("closed", "read")
                                   for r in later))

print("\n(11) tags, notes and nicknames")
one = win.bookmark_link(srv.url("/a"), "Alpha")
two = win.bookmark_link(srv.url("/b"), "Beta")
check("a link can be bookmarked without opening it", one is not None)
tags = win.bookmark_tags(one["id"], "mc, Server print")
check("tags are split on commas and spaces",
      tags == ["mc", "server", "print"], tags)
check("they are kept lower case", "server" in tags)
check("the tag list knows how many carry each",
      ("mc", 1) in win.all_bookmark_tags(), win.all_bookmark_tags())
check("and what carries one",
      [e["id"] for e in win.bookmarks_with_tag("mc")] == [one["id"]])
check("tags can be cleared", win.bookmark_tags(one["id"], "") == [])
win.bookmark_tags(one["id"], "mc")
check("a note can be written on a bookmark",
      win.bookmark_note(one["id"], "the one that works") ==
      "the one that works")
check("...and read back", win.bookmark_note(one["id"]) ==
      "the one that works")
check("a nickname is one typeable word",
      win.bookmark_nickname(one["id"], "My Mods") == "mymods",
      win.bookmark_nickname(one["id"]))
check("typing it in the bar resolves to that bookmark",
      win._resolve_typed("mymods") == srv.url("/a"),
      win._resolve_typed("mymods"))
check("and a word that is nobody's nickname does not",
      win.nickname_url("nothing") == "")

print("\n(12) the Favourites search")
found = win.search_bookmarks("alpha")
check("a word finds the bookmark", [e["id"] for e in found] == [one["id"]],
      [e.get("title") for e in found])
check("tag: is exact",
      [e["id"] for e in win.search_bookmarks("tag:mc")] == [one["id"]])
check("site: is too",
      len(win.search_bookmarks("site:127.0.0.1")) == 2,
      len(win.search_bookmarks("site:127.0.0.1")))
check("a note is searched as well",
      [e["id"] for e in win.search_bookmarks("works")] == [one["id"]])
win.note_bookmark_opened(two)
win.note_bookmark_opened(two)
ranked = win.search_bookmarks("")
check("the one he actually opens comes first",
      ranked[0]["id"] == two["id"],
      [(e.get("title"), e.get("opens")) for e in ranked])

print("\n(13) smart folders")
check("a search can be saved as a folder",
      win.save_smart_folder("Minecraft", "tag:mc"))
check("and holds what matches now",
      [e["id"] for e in win.smart_folder_matches("Minecraft")] == [one["id"]])
check("a folder that is not there holds nothing",
      win.smart_folder_matches("nope") == [])

print("\n(14) duplicates, and the ones he never opens")
dupe = win.bookmark_link(srv.url("/a"), "Alpha again")
groups = win.find_duplicate_bookmarks()
check("two bookmarks on one page are found as a pair",
      len(groups) == 1 and len(groups[0]) == 2, groups)
win.bookmark_tags(dupe["id"], "extra")
gone = win.merge_duplicate_bookmarks()
check("merging them leaves one", gone == 1, gone)
check("and the one left has both sets of tags",
      "extra" in win.bookmark_tags(one["id"]), win.bookmark_tags(one["id"]))
old = win.bookmark_link("https://never.test/x", "Never")
old["t"] = int(time.time()) - 400 * 86400
unused = win.unused_bookmarks()
check("a bookmark never opened in a year is on the unused list",
      any(e["id"] == old["id"] for e in unused), len(unused))
check("one he opened today is not",
      not any(e["id"] == two["id"] for e in unused))
win.remove_bookmark(old["id"])

print("\n(15) locks, colours and separators")
folder = win.add_bookmark_folder("Locked")
check("a folder can be locked", win.lock_folder(folder) is True)
check("...and says so", win.folder_locked(folder))
inside = win.bookmark_link(srv.url("/b"), "Inside", folder)
before = len(win.bookmarks)
win.remove_bookmark(inside["id"])
check("nothing is deleted out of a locked folder",
      len(win.bookmarks) == before, (before, len(win.bookmarks)))
win.move_bookmark(inside["id"], 0, 0)
check("and nothing is dragged out of one",
      inside["parent"] == folder, inside["parent"])
win.lock_folder(folder, False)
win.remove_bookmark(inside["id"])
check("unlocked, it deletes again", len(win.bookmarks) == before - 1)
check("the undo puts it back", win.undo_bookmark_delete() == before)
check("a folder takes a colour from the palette",
      win.folder_colour(folder, B.GROUP_COLORS[0][1]) == B.GROUP_COLORS[0][1])
check("and refuses one that is not in it",
      win.folder_colour(folder, "#123456") == B.GROUP_COLORS[0][1])
sep = win.add_separator(0)
check("a separator can be added", sep is not None
      and sep["type"] == "separator")
check("the bar draws it without a button",
      any(e.get("type") == "separator" for e in win.bookmarks))
win.rebuild_bookmarks_bar()
H.spin(200)
check("...and the bar still builds", win.bmbar is not None)
win.remove_bookmark(sep["id"])

print("\n(16) sorting and opening a folder")
box = win.add_bookmark_folder("Box")
win.bookmark_link(srv.url("/b"), "Zebra", box)
win.bookmark_link(srv.url("/a"), "Apple", box)
order = win.sort_folder(box, "title")
check("a folder sorts by name",
      [e["title"] for e in order] == ["Apple", "Zebra"],
      [e["title"] for e in order])
win.sort_folder(box, "title", permanent=True)
check("and the order can be kept",
      [e["title"] for e in win._bookmark_kids(box)] == ["Apple", "Zebra"])
tabs = win.open_folder_as_tabs(box)
H.spin(500)
check("every bookmark in it opens", len(tabs) == 2, len(tabs))
for v in tabs:
    win.close_tab(win.tabs.indexOf(v), ask=False)
tabs = win.open_folder_as_tabs(box, as_group=True)
H.spin(500)
check("or as a group named after the folder",
      all(win._group_of(v) == "Box" for v in tabs),
      [win._group_of(v) for v in tabs])
for v in tabs:
    win.close_tab(win.tabs.indexOf(v), ask=False)
H.spin(200)

print("\n(17) a bookmarklet")
let = win.save_bookmarklet("Reds", "javascript:document.body.dataset.ran='1'")
check("it is saved as a script, never as an address",
      let is not None and let["js"].startswith("document.")
      and let["url"] == "", let)
check("a javascript: bookmark cannot come back out of the file as a URL",
      all(e.get("url", "") == "" or
          B.QUrl(e["url"]).scheme() in ("http", "https")
          for e in win.bookmarks))
run_view = win.new_tab(url=None)
H.load(run_view, srv.url("/a"))
H.spin(300)
win.tabs.setCurrentIndex(win.tabs.indexOf(run_view))
check("running it works on a web page",
      win.run_bookmarklet(let, run_view))
H.spin(300)
check("...and really ran",
      H.js(run_view, "document.body.dataset.ran", B.MAIN_WORLD_ID) == "1",
      H.js(run_view, "document.body.dataset.ran", B.MAIN_WORLD_ID))
inner = win.new_tab(url=None)
H.spin(400)
check("but never on a page of the browser's own",
      not win.run_bookmarklet(let, inner))
win.close_tab(win.tabs.indexOf(inner), ask=False)
win.remove_bookmark(let["id"])

print("\n(18) where he had read to")
check("a bookmark remembers a scroll position",
      win.bookmark_scroll(two["id"], 1200) == 1200)
check("and gives it back", win.bookmark_scroll(two["id"]) == 1200)
check("0 clears it", win.bookmark_scroll(two["id"], 0) == 0)

print("\n(19) copies between virtual browsers")
win.sessions.append({"name": "Work", "sid": "work"})
made = win.copy_bookmarks_to_session(one["id"], "work")
check("a bookmark can be copied into another browser", made == 1, made)
copies = [e for e in win.bookmarks if e.get("sid") == "work"]
check("the copy is marked for that browser", len(copies) == 1, len(copies))
check("this browser does not show it",
      not any(e.get("sid") == "work" for e in win.session_bookmarks("main")))
check("and that one does",
      any(e.get("sid") == "work" for e in win.session_bookmarks("work")))
check("an unknown browser gets nothing",
      win.copy_bookmarks_to_session(one["id"], "nope") == 0)
for e in copies:
    win.remove_bookmark(e["id"])

print("\n(20) backups, and the file in a folder of his")
path = win.backup_bookmarks()
check("a dated copy is written", path and Path(path).exists(), path)
check("it is on the list of backups", win.bookmark_backups(),
      win.bookmark_backups())
count = len(win.bookmarks)
win.bookmarks = []
win.save_bookmarks()
kept = win.restore_bookmark_backup(win.bookmark_backups()[0])
check("and it can be put back", kept == count, (kept, count))
check("a made-up backup name is refused",
      win.restore_bookmark_backup("../../etc/passwd") == 0)
mirror = scratch / "mirror"
win.config["bookmarkMirror"] = str(mirror)
wrote = win.mirror_bookmarks()
check("the mirror is written where he said",
      wrote and (mirror / "bookmarks.json").exists(), wrote)
extra = json.loads((mirror / "bookmarks.json").read_text())
extra.append({"id": 9999, "type": "link", "title": "From the other machine",
              "url": "https://other.test/x", "parent": 0, "t": now})
(mirror / "bookmarks.json").write_text(json.dumps(extra))
added = win.merge_bookmark_mirror()
check("what only the mirror has is taken back", added == 1, added)
check("...and nothing is taken twice", win.merge_bookmark_mirror() == 0)
win.config["bookmarkMirror"] = ""

print("\n(21) import and export")
out = scratch / "bm.html"
wrote = win.export_bookmarks(out, "html")
check("the Netscape file every browser reads is written",
      wrote >= 1 and "NETSCAPE-Bookmark-file-1" in out.read_text(), wrote)
check("with the links in it", 'HREF="' + srv.url("/a") in out.read_text())
md = scratch / "bm.md"
win.export_bookmarks(md, "md")
check("a Markdown list too", md.read_text().startswith("- ["),
      md.read_text()[:40])
asjson = scratch / "bm.json"
win.export_bookmarks(asjson, "json")
check("and plain JSON", isinstance(json.loads(asjson.read_text()), list))
before = len(win.bookmarks)
added = win.import_bookmarks(out)
check("importing the file back adds its links", added >= 1, added)
check("under a folder of its own, not over what is there",
      len(win.bookmarks) > before
      and any(e["type"] == "folder" and e["title"] == "bm"
              for e in win.bookmarks))
chrome = scratch / "Bookmarks"
chrome.write_text(json.dumps({"roots": {"bookmark_bar": {
    "children": [
        {"type": "folder", "name": "Mods", "children": [
            {"type": "url", "name": "Modrinth",
             "url": "https://modrinth.com/"}]},
        {"type": "url", "name": "News", "url": "https://news.test/"}]}}}))
added = win.import_bookmarks(chrome)
check("Chrome's own file is read too", added == 2, added)
check("with its folders kept",
      any(e["type"] == "folder" and e["title"] == "Mods"
          for e in win.bookmarks))
firefox = scratch / "ff.json"
firefox.write_text(json.dumps({"children": [
    {"type": "text/x-moz-place-container", "title": "FF",
     "children": [{"type": "text/x-moz-place", "title": "Gnu",
                   "uri": "https://gnu.org/"}]}]}))
check("and Firefox's", win.import_bookmarks(firefox) == 1)

print("\n(22) the two jobs that go online")
dead = H.Server({"/alive": "<title>Alive</title>ok"})
alive_url = dead.url("/alive")
gone_url = dead.url("/gone")
win.bookmarks = [e for e in win.bookmarks if e["type"] != "link"]
a_entry = win.bookmark_link(alive_url, "Alive")
b_entry = win.bookmark_link(gone_url, "Gone")
answer = {}
win.check_bookmarks(then=lambda r: answer.update(r))
H.wait_for(lambda: "asked" in answer, 8000)
check("every bookmark is asked about", answer.get("asked") == 2, answer)
check("the live one is reported live", answer.get("ok") == 1, answer)
check("and the missing one as dead",
      [d["url"] for d in answer.get("dead", [])] == [gone_url], answer)
moved = win.apply_moved_bookmarks([{"id": a_entry["id"],
                                    "to": "https://moved.test/x"}])
check("a moved address is only taken when offered", moved == 1)
check("...and is the new one",
      win._bookmark_by_id(a_entry["id"])["url"] == "https://moved.test/x")
win.bookmarks = [e for e in win.bookmarks if e["type"] != "link"]
http_entry = win.bookmark_link("http://127.0.0.1:%d/alive" % dead.port,
                               "Insecure")
result = {}
win.upgrade_bookmarks_https(then=lambda r: result.update(r))
H.wait_for(lambda: "asked" in result, 8000)
check("the https check asks about the http ones", result.get("asked") == 1,
      result)
check("and leaves a bookmark alone when https does not answer",
      result.get("upgraded") == 0
      and win._bookmark_by_id(http_entry["id"])["url"].startswith("http://"),
      result)
dead.stop()

print("\n(23) what the history page asks for")
bridge = B.Bridge(win)
win.history = [{"url": "https://gnu.org/a", "title": "Gnu", "t": now - 10}]
rows = json.loads(bridge.historyRows(json.dumps({"q": "gnu"})))
check("the page gets its rows", len(rows) == 1, rows)
check("and the days", json.loads(bridge.historyDays()), bridge.historyDays())
check("and the virtual browsers",
      isinstance(json.loads(bridge.historySessions()), list))
check("the most visited", json.loads(bridge.mostVisited(5)))
check("the searches", isinstance(json.loads(bridge.searchQueries()), list))
check("the statistics", json.loads(bridge.browsingStats(7))["days"])
check("one delete door takes a list of addresses",
      bridge.deleteHistory(json.dumps({"urls": ["https://gnu.org/a"]})) == 1)
check("and the undo puts it back", bridge.undoHistory() == 1)
check("a site can be forgotten from a row",
      bridge.forgetHistorySite("gnu.org") == 1)
check("a never-record switch is there too",
      bridge.neverRecord("gnu.org") is True
      and bridge.neverRecord("gnu.org") is False)
check("nonsense from the page is refused, not acted on",
      bridge.deleteHistory("not json") == 0
      and bridge.openHistoryUrls("{}") == 0)

print("\n(24) the start page's two extra rows")
win.config["startContinue"] = True
win.config["startRecent"] = True
win.bookmark_link(srv.url("/a"), "Alpha")
extras = json.loads(bridge.startExtras())
check("the start page is offered something to carry on with",
      extras["continue"], extras)
check("and the bookmarks just added", extras["recent"], extras)
win.config["startRecent"] = False
check("the bookmark row is off unless he asks for it",
      json.loads(bridge.startExtras())["recent"] == [])
win.config["startContinue"] = False
check("and so is the other one",
      json.loads(bridge.startExtras())["continue"] == [])

print("\n(25) the menus are built and say what they do")
tools = win.bookmark_tools_menu()
labels = [a.text() for a in tools.actions() if a.text()]
check("the bookmark tools menu is built", len(labels) >= 4, labels)
check("the two that go online say so",
      any("online" in t or "online" in t.lower() for t in labels), labels)
folder_menu = win.folder_tools_menu(win._bookmark_by_id(box)
                                    or {"id": box})
check("a folder's own menu is built",
      len([a.text() for a in folder_menu.actions() if a.text()]) >= 4)
backups = win.backups_menu()
check("the backups menu lists them",
      len([a.text() for a in backups.actions() if a.text()]) >= 1)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
