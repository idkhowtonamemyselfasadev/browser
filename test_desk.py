#!/usr/bin/env python3
"""The desk drawer: notes, to-dos, clips, collections and snippets, the
things that put something into it, and the tools that work on a text
field or a selection.

Offscreen, scratch data, local pages. The storage is notes.py, which is
plain files and dictionaries, so most of this is exact."""
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
import notes as N  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>Alpha</title><p id=p>alpha beta</p>",
    "/field": """<title>Field</title>
      <textarea id=t rows=4 cols=40></textarea>
      <input id=i type=text>""",
    "/rich": """<title>Rich</title>
      <article>
        <h2>How to</h2>
        <p>Some <b>bold</b> and a <a href="https://gnu.org/x">link</a>.</p>
        <ul><li>first step</li><li>second step</li><li>third step</li></ul>
        <pre><code>make all</code></pre>
      </article>
      <nav>menu junk</nav><footer>footer junk</footer>
      <table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>
      <a href="mailto:ada@example.com">mail</a>
      <p>numbers: 12, 7.5 and 1.234,50</p>""",
    "/video": "<title>Vid</title><video id=v src='/x.mp4'></video>",
    "/block": "<title>Block</title><p>blocked?</p>",
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
MAIN = B.MAIN_WORLD_ID


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(300)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


print("\n(1) a note is a file")
text = N.note_text({"title": "Server rules", "tags": ["mc", "server"],
                    "t": 100, "edited": 200, "body": "be nice\n\nand quiet"})
check("it has front matter", text.startswith("---\ntitle: Server rules"),
      text[:40])
back = N.parse_note(text)
check("and reads back the same", back["title"] == "Server rules"
      and back["tags"] == ["mc", "server"] and back["t"] == 100
      and back["body"] == "be nice\n\nand quiet", back)
plain = N.parse_note("just some text\n")
check("a file somebody dropped in is still a note",
      plain["body"] == "just some text\n" and plain["title"] == "", plain)
check("a title becomes a sane file name",
      N.slug("Server rules & stuff!") == "server-rules-stuff",
      N.slug("Server rules & stuff!"))
check("and something unusable still gives a name",
      N.slug("!!!") == "note")

print("\n(2) the drawer")
desk = win.desk()
check("the browser has one", desk is not None)
check("in a folder of plain files",
      str(win.notes_folder()).endswith("notes"), win.notes_folder())
one = desk.save_note(title="Alpha note", body="first", tags=["mc"])
two = desk.save_note(title="Beta note", body="second")
check("a note is saved", one["id"] == "alpha-note", one["id"])
check("and is a file on the disk",
      (win.notes_folder() / "alpha-note.md").exists())
check("both are listed",
      sorted(n["id"] for n in desk.notes()) == ["alpha-note", "beta-note"],
      [n["id"] for n in desk.notes()])
desk.save_note("alpha-note", "Alpha note", "first again")
check("and the one touched last is first",
      [n["id"] for n in desk.notes()][0] == "alpha-note",
      [n["id"] for n in desk.notes()])
check("a search finds one by its text",
      [n["id"] for n in desk.notes("first")] == ["alpha-note"])
check("and by its tag", [n["id"] for n in desk.notes("mc")] == ["alpha-note"])
desk.append_note("alpha-note", "a line more")
check("a line can be added to one",
      "a line more" in desk.note("alpha-note")["body"])
check("editing it keeps its id",
      desk.save_note("alpha-note", "Alpha note", "changed")["id"]
      == "alpha-note")
daily = desk.daily_note()
check("today has a note of its own", daily["id"] == N.today(), daily["id"])
check("and asking twice gives the same one",
      desk.daily_note()["id"] == daily["id"])
check("a note can be deleted", desk.delete_note("beta-note"))
check("...and is gone", desk.note("beta-note") is None)

print("\n(3) the to-do list is a Markdown file")
desk.add_todo("fix the plugin", link="https://x.test/a")
desk.add_todo("pay the server", due=int(time.time()) - 60)
rows = desk.todos()
check("two things to do", len(rows) == 2, rows)
check("the link is kept", rows[0]["link"] == "https://x.test/a", rows[0])
check("and the time", rows[1]["due"] > 0, rows[1])
raw = (win.notes_folder() / "todo.md").read_text()
check("the file is a list anybody can edit",
      raw.startswith("- [ ] fix the plugin"), raw[:40])
desk.toggle_todo(0)
check("one can be ticked off", desk.todos()[0]["done"])
check("and the file says so",
      (win.notes_folder() / "todo.md").read_text().startswith("- [x]"))
desk.move_todo(1, -1)
check("the order can be changed",
      desk.todos()[0]["text"] == "pay the server",
      [r["text"] for r in desk.todos()])
check("one that is due is reported", len(desk.due_todos()) == 1,
      desk.due_todos())
check("the done ones can be cleared", desk.clear_done_todos() == 1)
check("...and the rest stay", len(desk.todos()) == 1)
desk.delete_todo(desk.todos()[0]["id"])
check("and one can be deleted", desk.todos() == [])

print("\n(4) snippets, collections and clips")
desk.set_snippet(";ip", "192.0.2.10")
check("a snippet is kept", desk.expand(";ip") == "192.0.2.10")
check("and listed", ";ip" in desk.snippets())
check("an empty one takes it off", ";ip" not in desk.set_snippet(";ip", ""))
desk.set_snippet(";ip", "192.0.2.10")
desk.add_to_collection("Mods", "Sodium", "https://modrinth.com/mod/sodium")
check("a collection is a Markdown list",
      desk.collection("Mods").startswith("- [Sodium](https://"),
      desk.collection("Mods"))
check("and is listed", "mods" in desk.collections(), desk.collections())
desk.add_clip("hello")
desk.add_clip("world")
check("clips are newest first",
      [c["text"] for c in desk.clips()] == ["world", "hello"])
desk.pin_clip(1)
desk.clear_clips()
check("clearing keeps the pinned one",
      [c["text"] for c in desk.clips()] == ["hello"], desk.clips())
check("and one can be dropped", desk.drop_clip(0) == [])

print("\n(5) one search across the drawer")
found = desk.search_all("sodium")
check("a collection is found", [r["kind"] for r in found] == ["collection"],
      found)
desk.add_todo("sodium update")
check("so is a to-do",
      sorted(r["kind"] for r in desk.search_all("sodium"))
      == ["collection", "todo"], desk.search_all("sodium"))
check("and nothing matches nothing", desk.search_all("zzzz") == [])

print("\n(6) the door the panel talks through")
check("it says where the notes are",
      json.loads(json.dumps(win.desk_do("where", "{}")))["folder"]
      == str(win.notes_folder()))
check("it lists them", len(win.desk_do("notes", "{}")) >= 1)
made = win.desk_do("saveNote", json.dumps({"title": "From the panel",
                                           "body": "x"}))
check("it saves one", made and made["id"] == "from-the-panel", made)
check("it reads one back",
      win.desk_do("note", json.dumps({"id": made["id"]}))["title"]
      == "From the panel")
check("it deletes one",
      win.desk_do("deleteNote", json.dumps({"id": made["id"]})) is True)
check("it adds a to-do",
      any(r["text"] == "from the panel"
          for r in win.desk_do("addTodo",
                               json.dumps({"text": "from the panel"}))))
check("the clips are refused while the history is off",
      win.desk_do("clips", "{}") is None)
win.config["clipHistory"] = True
check("...and offered when it is on", win.desk_do("clips", "{}") == [])
win.config["clipHistory"] = False
check("junk from the page is no verb at all",
      win.desk_do("nonsense", "not json") is None)

print("\n(7) what goes into the drawer from a page")
view = page("/a")
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('p'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
before = len(desk.note(N.today())["body"])
win.clip_selection(view)
H.wait_for(lambda: len(desk.note(N.today())["body"]) > before, 4000)
body = desk.note(N.today())["body"]
check("the selection lands in today's note", "alpha beta" in body, body[-80:])
check("with the page it came from under it", srv.url("/a") in body)
note = win.page_to_note(view)
check("the page itself can be a note", note and srv.url("/a") in note["body"],
      note)
rows = win.tab_to_todo(win.tabs.indexOf(view), close=False)
check("and a tab can be a to-do",
      any(r["link"] == srv.url("/a") for r in rows), rows[-1])
path = win.collect_page("Reading", view)
check("a page goes into a collection", path and "reading" in path, path)

print("\n(8) a quick note, typed into a box")
real_ask = B.QInputDialog.getMultiLineText
B.QInputDialog.getMultiLineText = lambda *a, **k: ("a thought", True)
win.quick_capture()
check("it is written into today's note",
      "a thought" in desk.note(N.today())["body"])
B.QInputDialog.getMultiLineText = lambda *a, **k: ("", False)
before = desk.note(N.today())["body"]
win.quick_capture()
check("and nothing is written when he cancels",
      desk.note(N.today())["body"] == before)
B.QInputDialog.getMultiLineText = real_ask

print("\n(9) snippets in a real text field")
win.config["snippets"] = True
win.refresh_snippet_script()
names = [s.name() for s in win.profile.scripts().toList()]
check("the expander is in the jar", "snippets" in names, names[-3:])
field = page("/field")
H.spin(300)
js(field, """(function(){var t=document.getElementById('t');
 t.focus(); t.value=';ip '; t.setSelectionRange(4,4);
 t.dispatchEvent(new KeyboardEvent('keyup',{key:' ',bubbles:true}));})()""")
H.spin(300)
check("typing the key puts the text in",
      "192.0.2.10" in str(js(field, "document.getElementById('t').value")),
      js(field, "document.getElementById('t').value"))
js(field, """(function(){var t=document.getElementById('t');
 t.value='plain text '; t.setSelectionRange(11,11);
 t.dispatchEvent(new KeyboardEvent('keyup',{key:' ',bubbles:true}));})()""")
H.spin(250)
check("and ordinary typing is left alone",
      js(field, "document.getElementById('t').value") == "plain text ",
      js(field, "document.getElementById('t').value"))

print("\n(10) the tools for a text field")
js(field, """(function(){var t=document.getElementById('t');
 t.focus(); t.value='beta\\nalpha\\nbeta\\n'; t.setSelectionRange(0,0);})()""")
answers = []
win.desk_tool("textcase", view=field, then=answers.append, arg="upper")
H.wait_for(lambda: answers, 4000)
check("upper case works",
      js(field, "document.getElementById('t').value").startswith("BETA"),
      js(field, "document.getElementById('t').value"))
answers.clear()
win.desk_tool("textcase", view=field, then=answers.append, arg="sort")
H.wait_for(lambda: answers, 4000)
check("sorting the lines works",
      js(field, "document.getElementById('t').value").startswith("\nALPHA"),
      repr(js(field, "document.getElementById('t').value")))
answers.clear()
win.desk_tool("textcase", view=field, then=answers.append, arg="dedupe")
H.wait_for(lambda: answers, 4000)
check("and dropping the duplicate lines",
      js(field, "document.getElementById('t').value").count("BETA") == 1,
      repr(js(field, "document.getElementById('t').value")))
answers.clear()
win.insert_text("§c", view=field)
H.spin(300)
check("a character can be inserted",
      "§c" in js(field, "document.getElementById('t').value"),
      js(field, "document.getElementById('t').value"))
answers.clear()
win.desk_tool("counter", view=field, then=answers.append)
H.wait_for(lambda: answers, 4000)
check("the character counter goes up", answers == ["on"], answers)
answers.clear()
win.desk_tool("smartpaste", view=field, then=answers.append)
H.wait_for(lambda: answers, 4000)
check("and so does smart paste", answers == ["on"], answers)

print("\n(11) the tools for a page and a selection")
rich = page("/rich")
H.spin(300)
H.js(rich, """(function(){var r=document.createRange();
 r.selectNodeContents(document.querySelector('article'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
got = []
win.desk_tool("selmarkdown", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
md = got[0] if got else ""
check("the selection comes out as Markdown",
      "## How to" in md and "**bold**" in md
      and "[link](https://gnu.org/x)" in md, md[:120])
check("with the list as a list", "- first step" in md, md[:200])
got.clear()
win.desk_tool("cleantext", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
clean = got[0] if got else ""
check("the clean text has the article", "second step" in clean, clean[:80])
check("and not the menu or the footer",
      "menu junk" not in clean and "footer junk" not in clean, clean[:200])
got.clear()
win.desk_tool("tables", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
tables = json.loads(got[0] or "[]")
check("the table is read", tables and tables[0][0] == ["a", "b"], tables)
copied = []
win.copy_tables("markdown", view=rich, then=copied.append)
H.wait_for(lambda: copied, 4000)
check("and copied as Markdown",
      copied and copied[0].startswith("| a | b |"), copied[:1])
got.clear()
win.desk_tool("links", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
out = json.loads(got[0] or "{}")
check("every link is listed",
      any(r["url"] == "https://gnu.org/x" for r in out.get("links", [])),
      out.get("links"))
check("and every email address",
      "ada@example.com" in out.get("mails", []), out.get("mails"))
got.clear()
win.desk_tool("pagelists", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
lists = json.loads(got[0] or "[]")
check("a list on the page is found",
      lists and len(lists[0]) == 3, lists)
made = []
win.checklist_from_page(rich, then=made.append)
H.wait_for(lambda: made, 4000)
check("and becomes to-dos", made and made[0] == 3, made)
check("which are on the list",
      any(r["text"] == "first step" for r in desk.todos()),
      [r["text"] for r in desk.todos()][:4])
H.js(rich, """(function(){var r=document.createRange();
 r.selectNodeContents(document.querySelectorAll('p')[1]);
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
sums = []
win.sum_selection(rich, then=sums.append)
H.wait_for(lambda: sums, 4000)
check("the numbers in a selection are added up",
      sums and sums[0] and sums[0]["count"] == 3, sums)
check("...reading 1.234,50 as one number",
      sums and sums[0] and sums[0]["max"] == 1234.5, sums)
check("and the German thousands separator is read right",
      sums and abs(sums[0]["sum"] - (12 + 7.5 + 1234.50)) < 0.01, sums)
got.clear()
win.desk_tool("fragment", view=rich, then=got.append)
H.wait_for(lambda: got, 4000)
check("a link to the selection is a text fragment",
      got and "#:~:text=" in got[0], got[:1])

print("\n(12) a moment of a video, noted")
vid = page("/video")
H.spin(300)
js(vid, "document.getElementById('v').currentTime = 42")
before = desk.note(N.today())["body"]
win.video_time_note(vid)
H.wait_for(lambda: desk.note(N.today())["body"] != before, 4000)
check("the note has the moment in it",
      "0:42" in desk.note(N.today())["body"],
      desk.note(N.today())["body"][-60:])

print("\n(13) focus mode")
win.config["focusSites"] = []
check("it is off to start with", not win.focusing())
win.start_focus(15, ["127.0.0.1"])
check("it goes on for the minutes he said",
      win.focusing() and win.focus_until() > time.time() + 800,
      win.focus_until() - time.time())
check("and blocks the site he named",
      win.focus_blocks(srv.url("/block")))
check("but not another one", not win.focus_blocks("https://gnu.org/"))
blocked = page("/block")
H.spin(600)
check("a blocked page does not load",
      "blocked?" not in str(js(blocked, "document.body.textContent") or ""),
      js(blocked, "document.body.textContent"))
check("and says how long is left",
      "left" in str(js(blocked, "document.body.textContent") or "").lower()
      or "min" in str(js(blocked, "document.body.textContent") or ""),
      js(blocked, "document.body.textContent"))
check("one site can be put on the list from the menu",
      win.toggle_focus_site("gnu.org") is True
      and "gnu.org" in win.config["focusSites"])
check("and taken off again", win.toggle_focus_site("gnu.org") is False)
win.stop_focus()
check("stopping lifts it", not win.focusing())
win.config["focusSites"] = []

print("\n(14) a daily limit per site")
check("no site has a limit to start with", win.site_limit("127.0.0.1") == 0)
win.site_limit("127.0.0.1", 30)
check("one can be set", win.site_limit("127.0.0.1") == 30)
view = page("/a")
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
win.config["siteTime"] = {}
win.note_site_time(600)
check("the time in front is counted",
      abs(win.site_minutes_today("127.0.0.1") - 10) < 0.1,
      win.site_minutes_today("127.0.0.1"))
check("and nothing is counted for a site with no limit",
      win.site_minutes_today("gnu.org") == 0)
check("the limit is not reached yet", not win.limit_reached(srv.url("/a")))
win.note_site_time(1800)
check("after enough time it is", win.limit_reached(srv.url("/a")),
      win.site_minutes_today("127.0.0.1"))
page_html = win.limit_page(srv.url("/a"))
check("and the page says so", "127.0.0.1" in page_html
      and "30" in page_html, page_html[-120:])
win.site_limit("127.0.0.1", 0)
check("the limit can be taken off", win.site_limit("127.0.0.1") == 0)
win.config["siteTime"] = {}

print("\n(15) timers and the pomodoro")
win.config["timers"] = []
row = win.start_timer(5, "tea")
check("a timer is set", row["name"] == "tea" and row["at"] > time.time())
check("and listed", len(win.timers()) == 1)
win.config["timers"] = [{"name": "tea", "at": int(time.time()) - 1}]
win._desk_tick()
check("one that is up goes off and is taken off the list",
      win.timers() == [], win.timers())
win.pomodoro(25, 5)
check("a pomodoro sets two timers", len(win.timers()) == 2, win.timers())
check("and a focus block with it", win.focusing())
win.stop_focus()
win.config["timers"] = []

print("\n(16) notifications held back, and written down")


class FakeNotification:
    def __init__(self, host, title, body):
        self._host = host
        self._title = title
        self._body = body
        self.shown = False
        self.closed = False

    def origin(self):
        return QUrl("https://" + self._host)

    def title(self):
        return self._title

    def message(self):
        return self._body

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True


win.config["notifyLog"] = []
note = FakeNotification("chat.test", "Ping", "hello there")
check("a notification is shown", win._web_notification(note) and note.shown)
check("and written down",
      win.notification_log()[0]["title"] == "Ping",
      win.notification_log()[:1])
win.do_not_disturb(30)
check("do not disturb goes on", win.dnd_until() > time.time())
held = FakeNotification("chat.test", "Later", "quiet")
check("the next one is held, not shown",
      not win._web_notification(held) and not held.shown and held.closed)
check("but still written down",
      win.notification_log()[0]["title"] == "Later")
check("and said afterwards", win.release_held_notifications() == 1)
check("a second call has nothing to say",
      win.release_held_notifications() == 0)
win.do_not_disturb(30)
check("and it can be switched off again", win.dnd_until() == 0,
      win.dnd_until())

print("\n(16b) the engine gets its Python back before the end")
check("the presenter is released on request",
      win._release_engine_hooks() is True)
note = FakeNotification("chat.test", "After", "still works")
check("...and the browser can still write one down",
      win.note_notification("chat.test", "After", "still works") >= 1)
check("which is in the log",
      win.notification_log()[0]["title"] == "After",
      win.notification_log()[:1])

print("\n(17) a tab put off until later")
later = page("/a")
win.config["snoozed"] = []
at = win.snooze_tab(win.tabs.indexOf(later), minutes=60)
H.spin(200)


def gone(view):
    # a closed tab's C++ half is gone; asking it anything raises
    try:
        return win.tabs.indexOf(view) < 0
    except RuntimeError:
        return True


check("the tab goes", at and gone(later))
check("and is on the list", len(win.snoozed_tabs()) == 1)
check("nothing comes back before its time", win.wake_snoozed() == 0)
win.config["snoozed"][0]["at"] = int(time.time()) - 1
check("and it comes back when it is due", win.wake_snoozed() == 1)
H.spin(400)
check("the list is empty again", win.snoozed_tabs() == [])
morning = page("/a")
at = win.snooze_tab(win.tabs.indexOf(morning), until_morning=True)
check("tomorrow morning is eight o'clock",
      time.localtime(at).tm_hour == 8, time.strftime("%c", time.localtime(at)))
win.config["snoozed"] = []

print("\n(18) a page that opens itself at a time")
win.config["scheduled"] = []
win.schedule_tab("https://rewards.test/daily", "00:01")
check("it is on the list", len(win.scheduled_tabs()) == 1)
opened = win.run_scheduled_tabs()
H.spin(300)
check("and opens when its time has passed today", opened == 1, opened)
check("but not twice in one day", win.run_scheduled_tabs() == 0)
win.schedule_tab("https://rewards.test/daily", on=False)
check("and it can be taken off", win.scheduled_tabs() == [])
check("junk is never scheduled",
      win.schedule_tab("not a url") == [])

print("\n(19) the window with nothing in the way")
check("zen mode hides the furniture",
      win.zen_mode(True) and not win.navbar.isVisible()
      and not win.tabs.tabBar().isVisible())
check("and brings it back",
      win.zen_mode(False) is False and win.navbar.isVisible()
      and win.tabs.tabBar().isVisible())

print("\n(20) one box for everything")
win.history = [{"url": "https://gnu.org/sodium", "title": "Sodium page",
                "t": int(time.time())}]
win.bookmark_link("https://modrinth.com/mod/sodium", "Sodium mod")
rows = win.search_everything("sodium")
kinds = sorted({r["kind"] for r in rows})
check("it looks in the bookmarks, the history and the drawer",
      "bookmark" in kinds and "history" in kinds, kinds)
check("and in the open tabs too",
      "tab" in sorted({r["kind"] for r in win.search_everything("alpha")}),
      sorted({r["kind"] for r in win.search_everything("alpha")}))
check("nothing typed, nothing found", win.search_everything("") == [])

print("\n(21) countdowns")
win.config["countdowns"] = []
rows = win.add_countdown("Season", "2030-01-01")
check("a date can be counted down to", rows and rows[0]["days"] > 1000, rows)
check("a date in the past says so",
      win.add_countdown("Past", "2020-01-01")[0]["past"] is True
      or any(r["past"] for r in win.countdowns()), win.countdowns())
check("junk is not a date",
      len(win.add_countdown("Nope", "whenever")) == 2,
      win.add_countdown("Nope", "whenever"))

print("\n(21b) the countdowns reach the start page")
bridge = B.Bridge(win)
win.config["countdowns"] = []
win.add_countdown("Season", "2030-01-01")
extras = json.loads(bridge.startExtras())
check("the start page is given them", extras.get("countdowns"), extras)
check("with how long is left",
      extras["countdowns"][0]["left"].endswith("d"),
      extras["countdowns"][0])
win.add_countdown("Long gone", "2020-01-01")
check("and a date in the past is not shown",
      all(c["name"] != "Long gone" for c in
          json.loads(bridge.startExtras())["countdowns"]),
      json.loads(bridge.startExtras())["countdowns"])

print("\n(22) the things this machine may or may not have")
answer = win.qr_code("https://example.test/x")
import shutil as _sh
check("a QR code is drawn either way", answer is True, answer)
if not _sh.which("qrencode"):
    check("...and without qrencode it is the browser's own encoder"
          " (qr.py) that drew it", win.qr_image("x") is not None)
found = [p for p in win.EXTERNAL_PROGRAMS if _sh.which(p)]
opened = win.open_externally(srv.url("/a"))
if found:
    check("the page opens in something that is installed",
          opened in found, opened)
else:
    check("and with nothing installed it says so", opened == "")
menu = win.external_menu()
check("the menu only offers what is there",
      len([a for a in menu.actions() if a.isEnabled()]) == len(found),
      [a.text() for a in menu.actions()])

print("\n(23) the big editor")
js(field, """(function(){var t=document.getElementById('t');
 t.focus(); t.value='short';})()""")
real_exec = B.QDialog.exec
B.QDialog.exec = lambda self: (
    self.findChild(B.QPlainTextEdit).setPlainText("much longer text")
    or B.QDialog.DialogCode.Accepted)
win.big_editor(field)
H.wait_for(lambda: js(field, "document.getElementById('t').value")
           == "much longer text", 5000)
check("what he wrote goes back into the field",
      js(field, "document.getElementById('t').value") == "much longer text",
      js(field, "document.getElementById('t').value"))
B.QDialog.exec = real_exec

print("\n(24) the menus and the keys")
menu = win.desk_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("the drawer's menu is built", len(labels) >= 8, labels)
check("the text tools are a menu",
      len([a for a in win.text_tools_menu().actions() if a.text()]) >= 7)
check("so is the character picker",
      len([a for a in win.char_picker().actions() if a.text()]) >= 5)
check("and the notification list",
      len([a for a in win.notification_menu().actions() if a.text()]) >= 1)
ids = {e["id"] for e in win.actions_list()}
for want in ("notes", "capture", "clipsel", "pagenote", "tabtodo", "zen",
             "everything", "focus", "pomodoro", "snooze", "copyselmd",
             "copyclean", "copyhighlight", "copytable", "sumsel",
             "bigeditor", "chars", "qrcode", "openexternal", "desk"):
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
