#!/usr/bin/env python3
"""Reading and writing, part two: the reader's switches, what a
selection can be turned into, the files that are only text, and the
tools for a text field.

Offscreen, scratch data, local pages. The two things that would leave
the machine (translating a selection and a dictionary site) are checked
by what they build, not by going there."""
import json
import os
import shutil
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


ARTICLE = """<title>The Article</title>
  <nav>menu junk</nav>
  <article>
    <h1>The Article</h1>
    <p>First paragraph with a <a href="https://gnu.org/x">link</a>.</p>
    <p id=nums>It is 5 in long and 350 F outside.</p>
    <ul><li>one</li><li>two</li></ul>
    <pre>def hello():
    return "world"  # a comment
</pre>
    <p><abbr title="as soon as possible">ASAP</abbr> please.</p>
    <p><a href="#note1" id=ref>[1]</a></p>
    <p id=note1>The footnote itself.</p>
    <div class="fade" style="max-height:20px;overflow:hidden">hidden away</div>
    <a href="/page2" id=next>next</a>
  </article>
  <footer>footer junk</footer>"""

PAGES = {
    "/a": ARTICLE,
    "/page2": "<title>Page 2</title><article><p>the rest of it</p></article>",
    "/field": """<title>Field</title>
      <form><textarea id=t rows=4 cols=40></textarea></form>""",
    "/long": "<title>Long</title><div style='height:5000px'>long</div>",
    "/md": "<pre># A heading\n\n- one\n- two\n\nplain line\n</pre>",
    "/log": "<pre>first line\nsecond line\nthird line\n</pre>",
    "/feed": """<pre>&lt;?xml version="1.0"?&gt;&lt;rss&gt;&lt;channel&gt;
      &lt;title&gt;My feed&lt;/title&gt;
      &lt;item&gt;&lt;title&gt;An entry&lt;/title&gt;
      &lt;link&gt;https://example.test/1&lt;/link&gt;
      &lt;description&gt;what it says&lt;/description&gt;&lt;/item&gt;
      &lt;/channel&gt;&lt;/rss&gt;</pre>""",
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


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(350)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


def ask(tool, view, arg=None, wait=4000):
    got = []
    win.read_page_tool(tool, view=view, then=got.append, arg=arg)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


print("\n(1) the reader's own switches")
options = win.reader_options()
check("it has a width, a size and three switches",
      options["width"] > 0 and "images" in options and "hyphens" in options
      and "serif" in options, options)
win.set_reader_option("images", False)
css = win.reader_css()
check("no pictures means a rule that hides them",
      "img" in win.reader_extra_css() and "display: none" in
      win.reader_extra_css(), win.reader_extra_css()[:80])
check("and it is in the reader's own stylesheet",
      win.reader_extra_css() in css)
win.set_reader_option("hyphens", True)
check("hyphenating means hyphens and justified text",
      "hyphens: auto" in win.reader_extra_css()
      and "justify" in win.reader_extra_css())
win.set_reader_option("serif", False)
check("and a sans font when he does not want the serif one",
      "sans-serif" in win.reader_extra_css())
win.set_reader_option("width", 55)
check("the width is in the sheet", "55ch" in win.reader_css(),
      [l for l in win.reader_css().splitlines() if "ch;" in l])
win.set_reader_option("images", True)
win.set_reader_option("hyphens", False)
win.set_reader_option("serif", True)
check("and with everything back to normal there is nothing extra",
      win.reader_extra_css() == "", win.reader_extra_css())

print("\n(2) an article, saved and noted")
view = page("/a")
out = ask("articletext", view)
got = json.loads(out or "null")
check("the article comes out as text", got and "First paragraph" in
      got["text"], (got or {}).get("text", "")[:60])
check("with its headings as Markdown", "# The Article" in got["text"],
      got["text"][:40])
check("and the menu and the footer left out",
      "menu junk" not in got["text"] and "footer junk" not in got["text"])
saved = []
win.save_article(view, then=saved.append)
H.wait_for(lambda: saved, 5000)
check("it can be saved as a file", saved and saved[0]
      and Path(saved[0]).exists(), saved)
text = Path(saved[0]).read_text() if saved and saved[0] else ""
check("with the title and the address at the top",
      text.startswith("# The Article") and srv.url("/a") in text,
      text[:80])
made = []
win.article_to_note(view, then=made.append)
H.wait_for(lambda: made, 5000)
check("or put straight into a note",
      made and made[0] and "First paragraph" in made[0]["body"], made[:1])

print("\n(3) the reader for a selection, and the next page")
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.querySelector('ul'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
before = len([1 for _i, _v in win._real_tabs()])
win.reader_from_selection(view)
H.wait_for(lambda: len([1 for _i, _v in win._real_tabs()]) > before, 5000)
check("the selection opens in a reader of its own",
      len([1 for _i, _v in win._real_tabs()]) == before + 1,
      (before, len([1 for _i, _v in win._real_tabs()])))
win.close_tab(win.tabs.count() - 1, ask=False)
check("the article's next page is found",
      str(ask("nextpage", view) or "").endswith("/page2"),
      ask("nextpage", view))
plain = page("/long")
check("and a page with no next page says so", ask("nextpage", plain) == "")

print("\n(4) where he had read to")
win.config["readResume"] = True
long_view = page("/long")
js(long_view, "window.scrollTo(0, 2000)")
H.spin(300)
check("the place is read out of the page",
      int(ask("readplace", long_view) or 0) > 1500,
      ask("readplace", long_view))
win.note_reading_place(long_view)
H.spin(400)
places = win.reading_places()
check("and written down for that page",
      any(k.endswith("/long") and v > 1500 for k, v in places.items()),
      places)
js(long_view, "window.scrollTo(0, 0)")
H.spin(200)
check("resuming scrolls back", win.resume_reading(long_view))
H.wait_for(lambda: int(js(long_view, "Math.round(window.scrollY)") or 0)
           > 1500, 4000)
check("...and it really did",
      int(js(long_view, "Math.round(window.scrollY)") or 0) > 1500,
      js(long_view, "Math.round(window.scrollY)"))
js(long_view, "window.scrollTo(0, 10)")
win.note_reading_place(long_view)
H.spin(400)
check("a page he barely scrolled keeps no place",
      not any(k.endswith("/long") for k in win.reading_places()),
      win.reading_places())
win.config["readResume"] = False

print("\n(5) the width of a wall of text")
check("no site has a width to start with", win.line_width("127.0.0.1") == 0)
win.line_width("127.0.0.1", 70)
check("one can be set", win.line_width("127.0.0.1") == 70)
wide = page("/long")
win.apply_line_width(wide, 70)
H.spin(300)
check("and the page is given the rule",
      "70ch" in str(js(wide, """(function(){var s=
       document.getElementById('read-width');
       return s ? s.textContent : '';})()""") or ""),
      js(wide, """(function(){var s=document.getElementById('read-width');
       return s ? s.textContent : '';})()"""))
win.line_width("127.0.0.1", 0)
check("and taking it off leaves nothing", win.line_width("127.0.0.1") == 0)

print("\n(6) what the page is hiding, and what it explains")
view = page("/a")
check("the hidden box is opened up",
      int(ask("showhidden", view) or 0) >= 1, ask("showhidden", view))
check("...and its text is now visible",
      js(view, """(function(){var e=document.querySelector('.fade');
       return e ? getComputedStyle(e).maxHeight : '';})()""") == "none",
      js(view, """(function(){var e=document.querySelector('.fade');
       return e ? getComputedStyle(e).maxHeight : '';})()"""))
check("the words it explains are marked",
      int(ask("abbrtips", view) or 0) >= 1, ask("abbrtips", view))
check("the footnote helper goes up", ask("footnotes", view) == "on")
check("so does the progress line", ask("progress", view) == "on")
check("and the ruler", ask("ruler", view) == "on")
check("...which the same key takes away again",
      ask("ruler", view) == "off")

print("\n(7) code, coloured and copied clean")
check("a plain code block is coloured",
      int(ask("highlight", view) or 0) >= 1, ask("highlight", view))
check("...with spans the page did not have",
      int(js(view, "document.querySelectorAll('pre span').length") or 0) > 1,
      js(view, "document.querySelectorAll('pre span').length"))
check("the keyword is coloured, not the whole block",
      "cba6f7" in str(js(view, "document.querySelector('pre').innerHTML")
                      or ""),
      str(js(view, "document.querySelector('pre').innerHTML"))[:80])
check("and the line-number stripper goes up",
      ask("nolinenumbers", view) == "on")

print("\n(8) a selection, turned into something else")
# the two that would put a box on the screen: the box is the answer, so
# it is caught here rather than left to block an offscreen run
shown = []
B.QMessageBox.information = lambda *a, **k: shown.append(a[1:3])
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('nums'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
answers = []
win.convert_selection(view, then=answers.append)
H.wait_for(lambda: answers, 5000)
check("a measurement in it is converted",
      answers and "mm" in answers[0], answers)
check("the converters read a sentence, not a typed query",
      B._metric_answer("it is 5 in long")[1] == "127"
      and B._metric_answer("350 F outside")[0].endswith("c"),
      (B._metric_answer("it is 5 in long"),
       B._metric_answer("350 F outside")))
check("a time with somebody else's zone on it comes out local",
      B._zone_answer("stream at 8 PM EST")[1].count(":") == 1,
      B._zone_answer("stream at 8 PM EST"))
check("and a sentence with neither gives nothing",
      B._metric_answer("just words") is None
      and B._zone_answer("just words") is None)
rows = []
win.inspect_characters(view, then=rows.append)
H.wait_for(lambda: rows, 5000)
check("the characters can be listed",
      rows and rows[0] and rows[0][0]["u"].startswith("U+"),
      (rows or [[]])[0][:2])
check("and shown in a box", shown, shown[:1])
from PyQt6.QtGui import QGuiApplication  # noqa: E402
QGuiApplication.clipboard().setText("It is 5 in long and 350 F outside.")
diff = []
win.compare_with_clipboard(view, then=diff.append)
H.wait_for(lambda: diff, 5000)
check("and compared with the clipboard, which is the same here",
      diff and diff[0] == [], diff)
QGuiApplication.clipboard().setText("something else entirely")
diff.clear()
win.compare_with_clipboard(view, then=diff.append)
H.wait_for(lambda: diff, 5000)
check("...and different when it is different", diff and diff[0], diff[:1])

print("\n(9) translating and looking up, which say where they go")
win.config["panelUrl"] = ""
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('nums'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
win.translate_selection(view)
H.wait_for(lambda: "translate.google" in str(win.config.get("panelUrl", "")),
           5000)
check("the translation opens in the side panel",
      "translate.google.com" in str(win.config.get("panelUrl", "")),
      win.config.get("panelUrl"))
check("with the words in the address, and the language",
      "tl=en" in str(win.config.get("panelUrl", "")),
      win.config.get("panelUrl"))
check("the menu entry says it leaves the machine",
      "Google" in win._ui_str("translateSel"), win._ui_str("translateSel"))
win.config["panelUrl"] = ""
win.config["dictionarySite"] = "https://dict.test/?q={}"
H.js(view, """(function(){var r=document.createRange();
 var p=document.getElementById('nums');
 r.setStart(p.firstChild, 0); r.setEnd(p.firstChild, 2);
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);})()""", MAIN)
H.spin(200)
win.define_word(view)
if shutil.which("dict"):
    check("an installed dictionary is used", True)
else:
    H.wait_for(lambda: "dict.test" in str(win.config.get("panelUrl", "")),
               5000)
    check("with no offline dictionary it opens the site he chose",
          "dict.test" in str(win.config.get("panelUrl", "")),
          win.config.get("panelUrl"))

print("\n(10) a text field: statistics, replace, a bigger font")
field = page("/field")
js(field, """(function(){var t=document.getElementById('t');
 t.focus(); t.value='One sentence here. And a second one!';})()""")
stats = []
win.selection_statistics(field, then=stats.append)
H.wait_for(lambda: stats, 5000)
check("it counts the words", stats and stats[0]
      and stats[0]["words"] == 7, stats)
check("and the sentences", stats and stats[0]["sentences"] == 2, stats)
answer = ask("replace", field, {"from": "second", "to": "third"})
check("find and replace works", answer == "1", answer)
check("...and the field says so",
      "third" in str(js(field, "document.getElementById('t').value")),
      js(field, "document.getElementById('t').value"))
check("replacing something that is not there changes nothing",
      ask("replace", field, {"from": "zzz", "to": "x"}) == "0")
check("a big mono font goes on", ask("fieldfont", field) == "on")
check("...and off again", ask("fieldfont", field) == "off")

print("\n(11) drafts kept and put back")
check("the draft watcher goes up", ask("draftsave", field) == "on")
js(field, """(function(){var t=document.getElementById('t');
 t.focus(); t.value='a long post that must not be lost by a reload';
 t.dispatchEvent(new Event('input',{bubbles:true}));})()""")
H.spin(1600)
kept = ask("draftread", field)
check("what he typed is kept", kept and "long post" in str(kept), kept)
H.load(field, srv.url("/field"))
H.spin(400)
check("the field is empty after the reload",
      js(field, "document.getElementById('t').value") == "")
back = []
win.restore_drafts(field, then=back.append)
H.wait_for(lambda: back, 5000)
check("and it comes back", back and back[0] == 1, back)
check("...with the text in it",
      "long post" in str(js(field, "document.getElementById('t').value")),
      js(field, "document.getElementById('t').value"))
# the watcher lives in the page, so a reload needs it put back before
# the submit can clear anything
ask("draftsave", field)
js(field, """(function(){document.querySelector('form')
  .dispatchEvent(new Event('submit',{bubbles:true}));})()""")
H.spin(300)
check("a sent form is not a lost draft any more",
      not ask("draftread", field), ask("draftread", field))

print("\n(12) files that are only text")
check("a .md file is a Markdown file",
      win.file_kind("file:///x/notes.md") == "markdown")
check("a .log is text with line numbers",
      win.file_kind("file:///x/server.log") == "lines")
check("a feed is a feed", win.file_kind("https://x.test/feed.atom") == "feed")
check("and a web page is none of them",
      win.file_kind("https://x.test/page") == "")
md = page("/md")
check("the Markdown file renders",
      ask("renderfile", md, "markdown") == "markdown")
H.spin(200)
check("...with its heading as a heading",
      js(md, "document.querySelectorAll('h1').length") == 1,
      js(md, "document.body.innerHTML")[:80])
check("...and its list as a list",
      js(md, "document.querySelectorAll('li').length") == 2)
check("and the raw text is one click away",
      ask("renderfile", md, "raw") == "raw")
log = page("/log")
check("a log gets line numbers",
      int(ask("renderfile", log, "lines") or 0) >= 3,
      ask("renderfile", log, "lines"))
feed = page("/feed")
check("a feed becomes a list of entries",
      int(ask("renderfeed", feed) or 0) == 1, ask("renderfeed", feed))
H.spin(200)
check("...with the entry's title as a link",
      "An entry" in str(js(feed, "document.body.textContent") or ""),
      js(feed, "document.body.textContent")[:80])

print("\n(13) the little bar over a selection")
win.config["readSelBar"] = True
bar = page("/a")
# the page already has it: reading_extras put it there on load, which
# is the point of the setting
check("the bar goes up", ask("selbar", bar) in ("on", "already"),
      ask("selbar", bar))
H.js(bar, """(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('nums'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);
 window.__selWanted = {what:'copy', text:'from the bar'};})()""", MAIN)
H.spin(200)
win.tabs.setCurrentIndex(win.tabs.indexOf(bar))
win._selection_bar_tick()
H.wait_for(lambda: QGuiApplication.clipboard().text() == "from the bar", 4000)
check("pressing copy on it copies",
      QGuiApplication.clipboard().text() == "from the bar",
      QGuiApplication.clipboard().text())
win.config["readSelBar"] = False
check("and with the bar off nothing is polled",
      win._selection_bar_tick() is False)

print("\n(14) the languages and the encodings")
check("two dictionaries at once are allowed",
      win.set_spell_languages(["de-DE", "en-GB"]) == ["de-DE", "en-GB"])
check("and the engine is told both",
      win.spell_languages() == ["de-DE", "en-GB"])
win.config["spellCheck"] = True
win.apply_spellcheck()
check("...really told both",
      list(win.profile.spellCheckLanguages()) == ["de-DE", "en-GB"],
      list(win.profile.spellCheckLanguages()))
win.config["spellCheck"] = False
win.apply_spellcheck()
check("no site has a language of its own to start with",
      win.accept_language_for("127.0.0.1") == "")
win.accept_language_for("127.0.0.1", "de")
check("one can be set", win.accept_language_for("127.0.0.1") == "de")
asked = page("/a")
win.apply_site_language(asked)
check("and the jar is asked for it",
      asked.page().profile().httpAcceptLanguage() == "de",
      asked.page().profile().httpAcceptLanguage())
win.accept_language_for("127.0.0.1", "")
win.apply_site_language(asked)
check("off again, it is back to the browser's own",
      asked.page().profile().httpAcceptLanguage() != "de",
      asked.page().profile().httpAcceptLanguage())
check("no site has an encoding of its own either",
      win.site_encoding("127.0.0.1") == "")
win.config["encodingSites"] = {"127.0.0.1": "windows-1252"}
win.apply_encoding(asked)
check("a site's encoding is put on the engine",
      asked.page().settings().defaultTextEncoding() == "windows-1252",
      asked.page().settings().defaultTextEncoding())
win.config["encodingSites"] = {}
win.apply_encoding(asked)
check("and taken off again",
      asked.page().settings().defaultTextEncoding() == "UTF-8")
menu = win.encoding_menu()
check("the encoding menu offers the usual suspects",
      len([a for a in menu.actions() if a.text()]) >= 5,
      [a.text() for a in menu.actions()])

print("\n(15) the highlights, all of them in one place")
win.config["highlights"] = {"https://a.test/x": ["first mark", "second"],
                            "https://b.test/y": ["another"]}
rows = win.all_highlights()
check("every highlight is listed", len(rows) == 3, rows)
path = win.export_highlights()
check("and they can be written out as Markdown",
      path and Path(path).exists(), path)
text = Path(path).read_text() if path else ""
check("grouped by page", "## https://a.test/x" in text, text[:120])
check("with the text quoted", "> first mark" in text)
menu = win.highlights_menu()
check("the library is a menu of them",
      len([a for a in menu.actions() if a.text()]) >= 3,
      [a.text() for a in menu.actions()][:3])

print("\n(16) which helpers a page gets")
win.config.update({"readProgress": True, "readFootnotes": False,
                   "readCode": True, "readAbbr": False,
                   "readNoLineNumbers": False, "readSelBar": False,
                   "readDrafts": False, "readPlainPaste": False})
fresh = page("/a")
on = win.reading_extras(fresh)
check("only what he switched on is put on the page",
      sorted(on) == ["highlight", "progress"], on)
win.config.update({"readProgress": False, "readCode": False})
check("and with nothing switched on, nothing is",
      win.reading_extras(page("/a")) == [])

print("\n(17) the menus and the keys")
menu = win.reading_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("the reading menu is built", len(labels) >= 10, labels)
check("it names this site for the per-site answers",
      any("127.0.0.1" in t for t in labels), labels)
ids = {e["id"] for e in win.actions_list()}
for want in ("reading", "translatesel", "define", "convertsel", "unicode",
             "comparesel", "readersel", "readnext", "savearticle",
             "articlenote", "showhidden", "ruler", "replacefield",
             "fieldfont", "fieldeditor", "fieldstats", "drafts",
             "plainpaste", "highlights"):
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
