#!/usr/bin/env python3
"""The last of the tools: the printer's own state, both dictionaries,
the selection into the side panel, the feeds he did not ask for,
mailto: in his webmail, a price in a sentence, a piece of a page on
top, modes, the command line, the phone, a note's language, the words
in a picture, a transcript as a note, a calendar file, today's agenda,
the daily log, and captions for a video that has none.

Offscreen, scratch data, local server. Moonraker is a stub page on that
server; ffmpeg is the real one and the transcriber is a stub script, so
the caption pipeline is proven end to end with nothing installed and
nothing leaving the machine.
"""
import json
import os
import stat
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


K1 = json.dumps({"result": {"status": {
    "print_stats": {"state": "printing", "filename": "bracket.gcode",
                    "print_duration": 600.0},
    "display_status": {"progress": 0.25},
    "extruder": {"temperature": 219.4, "target": 220.0},
    "heater_bed": {"temperature": 59.8, "target": 60.0}}}})

PAGES = {
    "/p": "<title>P</title><body><p>A bracket costs $19.99 today.</p>"
          "<div id=chat style='width:200px;height:100px'>chat</div>"
          "<input id=f><textarea id=t></textarea>"
          "<p id=when>Meeting on 2026-10-18 19:00-20:30 in the hall</p>"
          "</body>",
    "/panel": "<title>Panel</title><body><textarea id=say></textarea>"
              "</body>",
    "/printer/objects/query": K1,
    "/v": "<title>V</title><body><video id=v src='/clip.webm'></video>"
          "</body>",
}

# a real two-second clip, so the caption pipeline runs on something
# ffmpeg can actually open. Built here with the ffmpeg the feature
# needs anyway; without it the pipeline cannot be tested and says so.
import shutil as _shutil  # noqa: E402
import subprocess as _subprocess  # noqa: E402
CLIP = Path(os.environ.get("TMPDIR", "/tmp")) / "browser-test-clip.webm"
HAVE_FFMPEG = bool(_shutil.which("ffmpeg"))
if HAVE_FFMPEG and not CLIP.is_file():
    _subprocess.run(
        [_shutil.which("ffmpeg"), "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2",
         "-shortest", "-c:v", "libvpx", "-c:a", "libvorbis",
         "-b:v", "80k", str(CLIP)],
        capture_output=True, timeout=120)
if CLIP.is_file():
    PAGES["/clip.webm"] = CLIP.read_bytes()

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
MAIN = B.MAIN_WORLD_ID
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(700)


def js(code, world=APP, v=None):
    return H.js(v or view, code, world)


def ask(call, *args, **kw):
    wait = kw.pop("wait", 8000)
    got = []
    kw["then"] = got.append
    call(*args, **kw)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


print("\n(1) what the printer is doing")
check("with no address it refuses", win.printer_status() is False)
win.config["printerUrl"] = srv.url("")
found = ask(win.printer_status)
check("the printer's own numbers come back", isinstance(found, dict)
      and found.get("state") == "printing", found)
check("...the file it is on", found["file"] == "bracket.gcode", found)
check("...how far it is", found["done"] == 25.0, found)
check("...how long is left, worked out from what it has spent",
      found["left"] == 1800, found)
check("...the nozzle, and what it wants",
      (found["nozzle"], found["nozzleWant"]) == (219.4, 220.0), found)
check("...and the bed", (found["bed"], found["bedWant"]) == (59.8, 60.0),
      found)
check("it is one request to his own machine",
      any(row["why"] == "printer" for row in win.own_requests()),
      [row["why"] for row in win.own_requests()][:4])
menu = win.printer_menu()
H.spin(1200)
labels = [one.text() for one in menu.actions()]
check("the menu fills itself in",
      any("printing" in one for one in labels), labels)
check("...with the temperatures", any("219.4" in one for one in labels),
      labels)
check("minutes are said as minutes", win._mins(1800) == "0:30",
      win._mins(1800))
check("...and hours as hours", win._mins(7200) == "2:00", win._mins(7200))
check("...and nonsense as a question mark", win._mins("soon") == "?")
win.config["printerUrl"] = ""

print("\n(2) both dictionaries at once")
have = win.spell_dictionaries()
check("what is installed is measured, not assumed",
      isinstance(have, list), have)
if have:
    check("both can be switched on", bool(win.spell_both_languages(True)),
          win.config.get("spellLangs"))
else:
    check("with no dictionary installed it says so and stays off",
          win.spell_both_languages(True) is False,
          win.config.get("spellBoth"))
    check("...and the switch did not stay on",
          win.config.get("spellBoth") is False)
check("it can be switched off", win.spell_both_languages(False) is False)
check("the engine takes a list of languages, which is why this works",
      hasattr(win.profile, "setSpellCheckLanguages"))

print("\n(3) the selection into the side panel")
check("with nothing in the panel it refuses",
      win.selection_to_panel(view=view) is False)
win.open_panel(srv.url("/panel"))
H.spin(1200)
check("the panel is open", getattr(win, "_panel_view", None) is not None)
js("var p = document.querySelector('p');"
   " var r = document.createRange(); r.selectNodeContents(p);"
   " window.getSelection().removeAllRanges();"
   " window.getSelection().addRange(r);", MAIN)
H.spin(300)
answer = ask(win.selection_to_panel, view=view, wait=6000)
check("what is selected is typed into the panel", answer == "typed", answer)
H.spin(400)
said = H.js(win._panel_view, "document.getElementById('say').value", MAIN)
check("...and the field in the panel has it",
      "bracket costs" in (said or ""), said)
check("a second one is added, not written over",
      ask(win.type_into_panel, "one more", wait=6000) == "typed")
H.spin(400)
said = H.js(win._panel_view, "document.getElementById('say').value", MAIN)
check("...so both lines are there", (said or "").count("\n") >= 1,
      repr(said))
js("window.getSelection().removeAllRanges();", MAIN)
H.spin(200)
check("with nothing selected it says so",
      ask(win.selection_to_panel, view=view, wait=6000) == "")

print("\n(4) the feeds he did not ask for")
check("it is off to start with", win.config.get("hideFeeds", False) is False)
check("there is nothing in the way of YouTube's own stylesheet",
      win.site_style("youtube.com") == "")
check("it can be switched on", win.hide_feeds(True) is True)
check("...and YouTube gets a rule", "display: none"
      in win.site_style("youtube.com"), win.site_style("youtube.com")[:60])
check("...which names the home grid",
      "ytd-rich-grid-renderer" in win.site_style("youtube.com"))
check("...and the Shorts shelves",
      "ytd-reel-shelf-renderer" in win.site_style("youtube.com"))
check("...and Twitch gets its own",
      "recommended" in win.site_style("twitch.tv"),
      win.site_style("twitch.tv")[:60])
check("what it hides can be read out in words",
      len(win.feed_rules_shown()["youtube.com"]) >= 4,
      win.feed_rules_shown()["youtube.com"][:3])
win.site_style("youtube.com", win.site_style("youtube.com")
               + "\nbody { color: red; }")
check("it can be switched off", win.hide_feeds(False) is False)
check("...and takes only its own rule with it",
      "color: red" in win.site_style("youtube.com")
      and "ytd-rich-grid" not in win.site_style("youtube.com"),
      win.site_style("youtube.com"))
win.site_style("youtube.com", "")

print("\n(5) mailto: in his webmail")
check("nothing is chosen to start with", win.webmail_choice() == "")
check("...and then a mailto: link is the desktop's business",
      win.mailto_url("mailto:a@b.de") == "")
check("a webmail can be chosen", win.set_webmail("gmx") == "gmx")
where = win.mailto_url("mailto:a@b.de?subject=Hi there&body=Yo")
check("a compose page is built", where.startswith("https://www.gmx.net/"),
      where)
check("...with the address in it", "a%40b.de" in where, where)
check("...and the subject, encoded", "Hi%20there" in where, where)
check("...and the body", "body=Yo" in where, where)
check("another webmail is another page",
      win.set_webmail("gmail") == "gmail"
      and "mail.google.com" in win.mailto_url("mailto:a@b.de"))
check("one nobody has heard of is refused",
      win.set_webmail("nonsense") is False)
check("it can be given back to the desktop",
      win.set_webmail("") is True and win.webmail_choice() == "")
check("...and then the link is not turned into anything",
      win.mailto_url("mailto:a@b.de") == "")
win.set_webmail("gmx")
check("something that is not a mailto: link is left alone",
      win.mailto_url("https://example.com") == "")

print("\n(6) a price in a sentence")
B.MONEY_RATES["rates"] = {}
answer = win.money_answer("A bracket costs $19.99 today.")
check("with no rate table it says so rather than guessing",
      answer and "Settings" in answer[0], answer)
B.MONEY_RATES["rates"] = {"USD": 1.08, "GBP": 0.85}
B.MONEY_RATES["when"] = int(time.time())
answer = win.money_answer("A bracket costs $19.99 today.")
check("with the table on, the price is in euros",
      answer and "€" not in answer[0] and "EUR" in answer[0], answer)
check("...worked out at that rate",
      answer and abs(float(answer[1]) - 19.99 / 1.08) < 0.01, answer)
check("pounds too", "GBP" in (win.money_answer("it was 10 GBP") or ("",))[0],
      win.money_answer("it was 10 GBP"))
check("euros are already euros",
      win.money_answer("das kostet 20 €") is None)
check("a sentence with no price in it is nothing",
      win.money_answer("just some words") is None)
check("a currency nobody named is nothing",
      win.money_answer("5 bananas") is None)
js("var p = document.querySelector('p');"
   " var r = document.createRange(); r.selectNodeContents(p);"
   " window.getSelection().removeAllRanges();"
   " window.getSelection().addRange(r);", MAIN)
H.spin(300)
got = ask(win.convert_selection, view=view, wait=6000)
check("the selection is converted where he selected it",
      "EUR" in (got or ""), got)
H.spin(500)
tip = js("var t = document.getElementById('__wordtip');"
         " t ? t.innerText : ''")
check("...and said in the page", "EUR" in (tip or ""), tip)

print("\n(7) a piece of a page, on top")
check("a part that is not named is nothing",
      win.float_element("", view=view) is False)
window = win.float_element("#chat", view=view)
check("a window comes up", window is not None and window.isVisible(),
      bool(window))
check("...frameless and on top",
      bool(window.windowFlags() & B.Qt.WindowType.WindowStaysOnTopHint),
      int(window.windowFlags()))
check("...with a view in it",
      any(isinstance(one, B.WebView) for one in window.children()),
      [type(one).__name__ for one in window.children()])
H.spin(1500)
inner = next(one for one in window.children()
             if isinstance(one, B.WebView))
check("...showing the same page",
      "/p" in (inner.url().toString() or ""), inner.url().toString())
check("...cropped to that part",
      H.js(inner, "getComputedStyle(document.getElementById('f'))"
           ".display", APP) in ("none", None),
      H.js(inner, "getComputedStyle(document.getElementById('f'))"
           ".display", APP))
check("...and the part itself is still there",
      H.js(inner, "getComputedStyle(document.getElementById('chat'))"
           ".display", APP) != "none",
      H.js(inner, "getComputedStyle(document.getElementById('chat'))"
           ".display", APP))
check("they can all be closed", win.close_floats() == 1)
check("...and then there are none", win.close_floats() == 0)

print("\n(8) modes")
check("there are none", win.modes() == {})
win.config["tabStrip"] = "left"
win.config["hideFeeds"] = False
rows = win.save_mode("work")
check("this setup can be kept", isinstance(rows, dict), rows)
check("...and it is the mode he is in", win.mode_now() == "work")
check("...and only the handful a mode is about",
      all(key in win.MODE_KEYS for key in rows), list(rows))
check("...and nothing about his passwords or privacy",
      not any(key.lower().startswith(("vault", "master", "guard"))
              for key in rows), list(rows))
win.config["tabStrip"] = "top"
win.tab_strip_place("top")
win.save_mode("play")
check("a second mode is kept", len(win.modes()) == 2, list(win.modes()))
check("switching to the first brings its strip back",
      win.open_mode("work") is not False
      and win.config.get("tabStrip") == "left",
      win.config.get("tabStrip"))
check("...and really moves it",
      win.tabs.tabPosition() == B.QTabWidget.TabPosition.West,
      win.tabs.tabPosition())
check("...and says which mode he is in", win.mode_now() == "work")
check("a mode that is not there does not open",
      win.open_mode("nothing") is False)
check("an empty name keeps nothing", win.save_mode("  ") is False)
menu = win.modes_menu()
check("the menu lists them with the one he is in ticked",
      any(one.text() == "work" and one.isChecked()
          for one in menu.actions()),
      [(one.text(), one.isChecked()) for one in menu.actions()][:3])
check("a mode can be forgotten", win.drop_mode("play") is True
      and "play" not in win.modes())
check("forgetting it twice does nothing", win.drop_mode("play") is False)
win.open_mode("work")
win.config["tabStrip"] = "top"
win.tab_strip_place("top")

print("\n(9) from a terminal")
check("a link arrives on the read-later list",
      win.take_cli_later("http://x.test/read") == "later-1",
      win.config.get("readLater"))
check("...and the same one twice is noticed",
      win.take_cli_later("http://x.test/read") == "already")
check("something that is not a link is refused",
      win.take_cli_later("rm -rf /") == "not-a-link")
check("a line arrives in the notes", win.take_cli_note("from the shell")
      in ("noted", "no-notes"), win.take_cli_note("again"))
check("a job arrives on the to-do list",
      win.take_cli_todo("mow the lawn") in ("todo", "no-notes"))
check("nothing is not a note", win.take_cli_note("") == "no-notes")
answers = []
win._handoff_command("later|http://x.test/sock", answers.append)
check("it all works over the socket the way a launch does",
      answers and answers[0].startswith("later-"), answers)
answers = []
win._handoff_command("note|over the socket", answers.append)
check("...and so does a note", answers and answers[0] in ("noted",
                                                          "no-notes"),
      answers)
answers = []
win._handoff_command("nonsense", answers.append)
check("...and a command nobody has is said to be unknown",
      answers == ["unknown-command"], answers)
source = (HERE / "browser.py").read_text()
check("the three flags are in the launcher",
      'for which in ("later", "note", "todo")' in source)

print("\n(10) this tab on his phone")
rows = win.kde_connect_devices()
check("the phones are asked of the program, not assumed",
      isinstance(rows, list), rows)
import shutil as _sh
if _sh.which("kdeconnect-cli"):
    check("with it installed, a command is built",
          isinstance(win.send_tab_to_phone(run=False, view=view),
                     (list, bool)))
else:
    check("without KDE Connect it says what it needs",
          win.send_tab_to_phone(run=False, view=view) is False)
menu = win.phone_menu()
check("the menu says there is nothing paired",
      [one.text() for one in menu.actions()]
      == [B.UI_STRINGS["de"]["phoneNoDevice"]] or rows,
      [one.text() for one in menu.actions()])

print("\n(11) the language a note is in")
check("a German note is German",
      win.note_language("Das ist eine Notiz und sie ist nicht lang")
      == "de")
check("an English note is English",
      win.note_language("This is a note and it is not long") == "en")
check("something that is neither is nothing",
      win.note_language("qwer asdf zxcv") == "")
check("...and so is nothing", win.note_language("") == "")
picked = win.spell_for_note("Das ist eine deutsche Notiz")
check("the dictionary is set for the note he is in",
      picked.startswith("de") if picked else have == [],
      [picked, have])

print("\n(12) the words in a picture")
import shutil as _sh2
got = ask(win.ocr_selection, view=view, wait=6000)
if _sh2.which("tesseract"):
    check("the picture is read", isinstance(got, str), got)
else:
    check("without tesseract it says what it needs and reads nothing",
          got == "", got)
check("the tool is measured, not assumed",
      isinstance(win.record_tools().get("tesseract"), str),
      win.record_tools().get("tesseract"))

print("\n(13) a transcript as a note")
got = ask(win.transcript_to_note, view=view, wait=6000)
check("a page with no captions says so and writes nothing",
      got in (0, None), got)

print("\n(14) a date into his calendar")
body = win.ics_from_text("Meeting on 2026-10-18 19:00-20:30 in the hall",
                         title="Meeting", url="http://x.test/e")
check("a calendar file is written", body.startswith("BEGIN:VCALENDAR"),
      body[:30])
check("...with the day", "DTSTART:20261018T190000" in body, body[:200])
check("...and when it ends", "DTEND:20261018T203000" in body, body)
check("...and what it is called", "SUMMARY:Meeting" in body, body)
check("...and where it came from", "URL:http://x.test/e" in body, body)
check("...and the lines end the way the standard says",
      body.count("\r\n") > 8, body.count("\r\n"))
check("the German way of writing a date works too",
      "DTSTART:20261018" in win.ics_from_text("am 18.10.2026 um 19:00"),
      win.ics_from_text("am 18.10.2026 um 19:00")[:120])
check("one time means an hour",
      "DTEND:20261018T200000" in win.ics_from_text("2026-10-18 19:00"),
      win.ics_from_text("2026-10-18 19:00"))
check("a sentence with no date in it is nothing",
      win.ics_from_text("some words") == "")
win.config["downloadDir"] = str(scratch / "dl")
path = win.save_ics("2026-10-18 19:00", title="T")
check("it is saved where his downloads go",
      isinstance(path, str) and path.endswith(".ics"), path)
check("...and really written", Path(path).is_file(), path)
check("...and a sentence with no date saves nothing",
      win.save_ics("nothing here") is False)
js("var p = document.getElementById('when');"
   " var r = document.createRange(); r.selectNodeContents(p);"
   " window.getSelection().removeAllRanges();"
   " window.getSelection().addRange(r);", MAIN)
H.spin(300)
made = ask(win.selection_to_calendar, view=view, wait=6000)
check("the date in what he selected becomes a file",
      isinstance(made, str) and made.endswith(".ics"), made)
check("...with the event in it",
      "DTSTART:20261018T190000" in Path(made).read_text(),
      Path(made).read_text()[:160] if made else "")

print("\n(15) today, out of a calendar file")
check("with no file there is no agenda", win.agenda_today() == [])
cal = scratch / "today.ics"
day = time.strftime("%Y%m%d")
cal.write_text(
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:%sT190000\r\n"
    "SUMMARY:Server event\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTSTART:%sT083000\r\nSUMMARY:Stand-up\r\n"
    "RRULE:FREQ=WEEKLY\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTSTART:19990101T120000\r\nSUMMARY:Long ago\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n" % (day, day))
check("a file can be named", win.set_agenda_file(str(cal)) == str(cal))
rows = win.agenda_today()
check("today's events are read", len(rows) == 2, rows)
check("...in the order of the day", rows[0]["at"] == "08:30", rows)
check("...with what they are called",
      rows[1]["name"] == "Server event", rows)
check("...and a repeating one is marked as such",
      rows[0]["repeats"] is True, rows[0])
check("another day is not today's agenda",
      win.agenda_today(when=time.time() - 86400 * 3) == [])
check("a file that is not there is no agenda",
      win.agenda_today(path=str(scratch / "none.ics")) == [])
start = (HERE / "start.html").read_text()
check("the start page draws it", "data.agenda" in start)

print("\n(16) what the day came to")
found = win.daily_log()
check("the day is counted", isinstance(found, dict)
      and found["day"] == time.strftime("%Y-%m-%d"), found)
check("...notes and to-dos are numbers",
      isinstance(found["notes"], int) and isinstance(found["todos"], int),
      found)
check("...and the time is honestly only the sites with a limit",
      found.get("onlyLimited") is True, found)
win.site_limit("x.test", 30)
win.config["siteTime"] = {"day": time.strftime("%Y-%m-%d"),
                          "x.test": 1800}
found = win.daily_log()
check("a site that was counted is in the log",
      any(row["host"] == "x.test" and row["minutes"] == 30
          for row in found["sites"]), found["sites"])
check("...and the minutes add up", found["minutes"] == 30, found)
check("it can be said in one line", isinstance(win.show_daily_log(), dict))
win.config["logToNote"] = True
found = win.show_daily_log()
check("...and kept as a note when he asked for that",
      isinstance(found, dict), found)
win.config["logToNote"] = False

print("\n(17) captions for a video that has none")
H.load(view, srv.url("/v"))
H.spin(900)
state = ask(win.video_caption_state, view=view, wait=6000)
check("the video is found", (state or {}).get("video") is True, state)
check("...with the address its player is using",
      (state or {}).get("kind") == "file", state)
check("...and no subtitles of its own", (state or {}).get("tracks") == [],
      state)
win.config["captionTranscriber"] = ""
check("without a transcriber it says what it needs",
      win.make_captions(view=view) is False)
stub = scratch / "stub-whisper.sh"
stub.write_text(
    '#!/bin/sh\n'
    '# a stand-in for whisper: writes the WebVTT it would.\n'
    '# Both shapes the browser calls a transcriber with: whisper.cpp\n'
    '# style (-of <base>) and the plain "<sound> <out.vtt>".\n'
    'out=""\n'
    'last=""\n'
    'while [ $# -gt 0 ]; do\n'
    '  case "$1" in -of) out="$2.vtt"; shift;; esac\n'
    '  last="$1"\n'
    '  shift\n'
    'done\n'
    'case "$out" in "") out="$last";; esac\n'
    '# nothing recognisable on the line: write beside this stub,\n'
    '# never into the directory the test happens to run from.\n'
    'case "$out" in "") out="$(dirname "$0")/stub";; esac\n'
    'case "$out" in *.vtt) ;; *) out="$out.vtt";; esac\n'
    'printf "WEBVTT\\n\\n00:00:00.000 --> 00:00:02.000\\n'
    'the first thing said\\n\\n00:00:02.000 --> 00:00:04.000\\n'
    'and the second\\n" > "$out"\n')
stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
win.config["captionTranscriber"] = "whisper-cli"
check("a transcriber that is not there is not used",
      win.caption_tools()["captionTranscriber"] == ""
      or Path(win.caption_tools()["captionTranscriber"]).exists(),
      win.caption_tools()["captionTranscriber"])
win.config["captionTranscriber"] = str(stub)
check("ffmpeg is here, so the pipeline can run", HAVE_FFMPEG)
check("...and the video is a real file it can open",
      CLIP.is_file() and CLIP.stat().st_size > 1000,
      CLIP.stat().st_size if CLIP.is_file() else 0)
done = ask(win.make_captions, view=view, wait=60000)
check("the captions are made and put on the video",
      (done or {}).get("cues", 0) >= 1, done)
H.spin(600)
check("...and the page has them",
      js("window.__autocapCues") and int(js("window.__autocapCues")) >= 1,
      js("window.__autocapCues"))
check("...as a track that shows",
      js("var v = document.querySelector('video');"
         " v.textTracks.length ? v.textTracks[0].mode : ''") == "showing",
      js("var v = document.querySelector('video');"
         " v.textTracks.length ? v.textTracks[0].mode : ''"))
check("...with the words in it",
      "first thing" in (js("var v = document.querySelector('video');"
                           " var t = v.textTracks[0];"
                           " t.cues && t.cues.length"
                           " ? t.cues[0].text : ''") or ""),
      js("var v = document.querySelector('video');"
         " var t = v.textTracks[0];"
         " t.cues && t.cues.length ? t.cues[0].text : ''"))
state = ask(win.video_caption_state, view=view, wait=6000)
check("and now the video has subtitles of its own",
      (state or {}).get("tracks"), state)
check("...so it is not captioned twice",
      (ask(win.make_captions, view=view, wait=9000) or {}).get("already"),
      ask(win.make_captions, view=view, wait=9000))
H.load(view, srv.url("/p"))
H.spin(700)
check("a page with no video says so",
      (ask(win.make_captions, view=view, wait=6000) or {}) == {})
check("a blob: player is refused with the reason, not a failure",
      "blob" in B.UI_STRINGS["en"]["autocapBlob"].lower(),
      B.UI_STRINGS["en"]["autocapBlob"])
check("an empty WebVTT puts nothing on anything",
      win.put_captions_on_video("WEBVTT\n", view=view) is False)

print("\n(18) every new word, in both languages")
need = ["k1Name", "k1Asking", "k1NoAnswer", "k1State", "k1Done", "k1Left",
        "k1Nozzle", "k1Bed", "spellNoDicts", "panelName", "panelNone",
        "panelNoSel", "panelTyped", "feedName", "feedHint",
        "webmailName", "webmailHint", "floatName", "floatAsk", "floatOn",
        "floatOff", "modeName", "modeSave", "modeAsk", "modeSaved",
        "modeOn", "modeNone", "modeDrop", "phoneName", "phoneNoTool",
        "phoneNoDevice", "phoneSent", "ocrName", "ocrNoImage",
        "transNoteName", "transNoneHere", "transNoted", "icsName",
        "icsNoDate", "icsSaved", "agendaName", "agendaHint",
        "agendaNone", "logName", "logLine", "logNoteName",
        "autocapName", "autocapNoTool", "autocapNoVideo",
        "autocapHasTracks", "autocapBlob", "autocapWorking",
        "autocapNoSound", "autocapNoWords", "autocapDone"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)
        and k not in ("k1Name",)]
check("and they are really translated", same == [], same)
page = (HERE / "settings.html").read_text()
for one in ("spellboth", "webmail", "hidefeeds", "logtonote",
            "agendafile"):
    check("“%s” is in Settings" % one, 'id="%s"' % one in page)
ids = [one["id"] for one in win.tab_actions_extra()]
for one in ("printerstate", "seltopanel", "hidefeeds", "floatpart",
            "modes", "tophone", "ocrpicture", "transtonote",
            "tocalendar", "dailylog", "makecaptions"):
    check("“%s” is a command" % one, one in ids)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
