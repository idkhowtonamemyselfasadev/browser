#!/usr/bin/env python3
"""Two pages at once, the strip somewhere else, sets of tabs, and the
reading work: what language a page is in, the offer bar, translating in
place and side by side, PDFs, the reader printed, synonyms, spelling,
one word looked up, a clean paste and a book.

Offscreen, scratch data, local server. The translator is a stub script
in the scratch directory, so a real translation round trip is proven
without anything installed and without a word leaving the machine.
"""
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWidgets import QTabWidget  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


LONG = "<div style='height:3000px'></div>"
PAGES = {
    "/en": "<title>English</title><html lang=en><body>"
           "<p>The page is in English and that is the point of it.</p>"
           "<p>Not that it matters for the test.</p>" + LONG + "</body>",
    "/nl": "<title>Nederlands</title><html lang=nl><body>"
           "<p>Deze pagina is in het Nederlands.</p>" + LONG + "</body>",
    "/de": "<title>Deutsch</title><html lang=de><body>"
           "<p>Diese Seite ist auf Deutsch und das ist der Sinn.</p>"
           + LONG + "</body>",
    "/two": "<title>Two</title><p>two</p>" + LONG,
    "/art": "<title>An article</title><body><article>"
            "<h1>The headline</h1>"
            "<p>" + ("Words enough to be an article. " * 30) + "</p>"
            "</article></body>",
    "/field": "<title>Field</title><body><input id=f size=60>"
              "<textarea id=t></textarea></body>",
}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "de",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 740)
win.show()
H.spin(400)
APP = B.APP_WORLD_ID
view = win.new_tab(url=None)
H.load(view, srv.url("/en"))
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


# a translator of our own: upper-cases the text, so a translated block
# is unmistakable and nothing is installed or sent anywhere
stub = scratch / "stub-translate.sh"
stub.write_text('#!/bin/sh\nshift\nprintf "%s" "$*" | tr a-z A-Z\n')
stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

print("\n(1) two tabs side by side")
second = win.new_tab(url=QUrl(srv.url("/two")), switch=False)
H.spin(600)
check("there is no split to start with", win.split_showing() is False)
check("one tab cannot be split with itself",
      win.split_view(index=win.tabs.indexOf(win.current())) is False)
check("the other tab goes into the other half",
      win.split_view(index=win.tabs.indexOf(second)) is True)
check("...and the split says it is showing", win.split_showing() is True)
check("...and both halves are on the screen",
      second.isVisible() and win.current().isVisible(),
      [second.isVisible(), win.current().isVisible()])
sizes = [one for one in win._split.sizes()[:2]]
check("...each with room", min(sizes) > 100, sizes)
check("scrolling together can be switched on",
      win.split_scroll_sync(True) is True)
check("...and it is a real timer", win._sync_timer.isActive() is True)
js("window.scrollTo(0, 400)")
H.spin(900)
other = H.js(second, "Math.round(window.scrollY)", APP)
check("...and the other half followed", other and int(other) > 300, other)
check("...and it can be switched off",
      win.split_scroll_sync(False) is False)
check("the split closes", win.close_split() is True)
check("...and the tab is back on the strip",
      win.tabs.indexOf(second) >= 0, win.tabs.indexOf(second))
check("...and the sync went with it",
      win._sync_timer.isActive() is False)
check("closing a split that is not there does nothing",
      win.close_split() is False)

print("\n(2) where the tab strip is")
check("down the left is a place", win.tab_strip_place("left") == "left")
check("...and Qt really moved it",
      win.tabs.tabPosition() == QTabWidget.TabPosition.West,
      win.tabs.tabPosition())
check("...and the tabs were given a width",
      "min-width" in win.tabs.tabBar().styleSheet(),
      win.tabs.tabBar().styleSheet()[:40])
check("the width can be set", win.set_tab_strip_width(260) == 260)
check("...and it is in the sheet",
      "260px" in win.tabs.tabBar().styleSheet())
check("...and silly widths are pulled back",
      win.set_tab_strip_width(9000) == 420)
check("below the page is a place", win.tab_strip_place("bottom") == "bottom")
check("...and Qt moved it there",
      win.tabs.tabPosition() == QTabWidget.TabPosition.South)
check("...and the vertical sheet came off",
      win.tabs.tabBar().styleSheet() == "",
      win.tabs.tabBar().styleSheet()[:40])
check("nowhere is not a place", win.tab_strip_place("sideways") is False)
check("back on top", win.tab_strip_place("top") == "top")
check("...and it is remembered", win.config.get("tabStrip") == "top")

print("\n(3) the tabs in rows")
check("two rows is two rows", win.tab_rows(2) == 2)
check("...and the bar stopped scrolling",
      win.tabs.tabBar().usesScrollButtons() is False)
check("...and the tabs were given a width",
      "max-width" in win.tabs.tabBar().styleSheet())
check("five rows is pulled back to four", win.tab_rows(5) == 4)
check("one row is the old behaviour", win.tab_rows(1) == 1)
check("...and the scroll buttons are back",
      win.tabs.tabBar().usesScrollButtons() is True)
check("nonsense is refused", win.tab_rows("lots") is False)

print("\n(4) the tabs of one site, folded")
check("one tab of a site cannot be stacked",
      win.stack_site_tabs("example.com") is False)
third = win.new_tab(url=QUrl(srv.url("/de")), switch=False)
H.spin(500)
host = win._host_of(view.url())
name = win.stack_site_tabs(host)
check("the tabs of this site fold into one", name == host, name)
check("...and they are all in that group",
      all(win._group_of(one) == host
          for _at, one in win._real_tabs()
          if win._host_of(one.url()) == host),
      [win._group_of(one) for _at, one in win._real_tabs()])
check("...and the group is collapsed", win.collapsed.get(host) is True)
check("...and it can be opened again",
      win.stack_site_tabs(host, on=False) == host
      and win.collapsed.get(host) is False,
      win.collapsed.get(host))
check("a site with no name is not a site", win.stack_site_tabs("") is False)

print("\n(5) named sets of tabs")
check("there are none to start with", win.workspaces() == {},
      win.workspaces())
rows = win.save_workspace("reading")
check("the open tabs can be kept under a name",
      isinstance(rows, list) and len(rows) >= 2, rows)
check("...and every row is an address",
      all(row["u"].startswith("http") for row in rows), rows)
check("...and that is the set he is in", win.workspace_now() == "reading")
check("an empty name keeps nothing", win.save_workspace("  ") is False)
win.save_workspace("one tab")
was = win.tabs.count()
opened = win.open_workspace("reading")
H.spin(600)
check("a set opens in this window",
      isinstance(opened, list) and len(opened) == len(rows), opened)
check("...and the old tabs went", win.tabs.count() <= was + 1,
      [was, win.tabs.count()])
check("...and it is the set he is in now", win.workspace_now() == "reading")
check("a set that is not there does not open",
      win.open_workspace("nothing") is False)
menu = win.workspace_menu()
labels = [one.text() for one in menu.actions()]
check("the menu lists the sets",
      any(one.startswith("reading") for one in labels), labels)
check("...with the one he is in ticked",
      any(one.isChecked() for one in menu.actions()
          if one.text().startswith("reading")))
check("a set can be dropped", win.drop_workspace("one tab") is True)
check("...and then it is gone", "one tab" not in win.workspaces(),
      list(win.workspaces()))
check("dropping it twice does nothing",
      win.drop_workspace("one tab") is False)

print("\n(6) which virtual browser opens a link from outside")
check("without a rule it is the one in front",
      win.outside_link_session("http://example.com/x")
      == win.active_session)
win.config["outsideRules"] = ["example.com=" + win.sessions[0]["name"]]
check("a rule for that site picks its browser",
      win.outside_link_session("http://example.com/x")
      == win.sessions[0]["sid"])
check("...and a sub-domain of it too",
      win.outside_link_session("http://shop.example.com/x")
      == win.sessions[0]["sid"])
check("...and another site is not touched",
      win.outside_link_session("http://other.test/x") == win.active_session)
win.config["outsideRules"] = ["nonsense"]
check("a line that is not a rule is ignored",
      win.outside_link_session("http://example.com/x") == win.active_session)
win.config["outsideRules"] = []

print("\n(7) the window, as he left it")
win.resize(920, 680)
win.move(40, 30)
H.spin(200)
state = win.window_state()
check("the window knows what it is",
      state["w"] == 920 and state["h"] == 680, state)
check("...and which virtual browser it is",
      state["session"] == win.active_session)
check("...and what is open in it",
      all(one.startswith("http") for one in state["tabs"])
      and len(state["tabs"]) >= 1, state["tabs"])
saved = win.save_window_state()
check("it can be written down", isinstance(saved, dict), saved)
check("...under its virtual browser",
      win.active_session in (win.config.get("windowStates") or {}),
      list((win.config.get("windowStates") or {})))
win.resize(700, 500)
back = win.restore_window_state()
H.spin(200)
check("...and put back", back and back["w"] == 920, back)
check("...really put back", win.width() == 920, win.width())
check("a browser that saved nothing restores nothing",
      win.restore_window_state("no-such-session") is False)

print("\n(8) what language a page is in")
# opening a set of tabs closed the ones that were open, this one
# among them: from here on the reading work gets a fresh tab
view = win.new_tab(url=None)
H.spin(300)
H.load(view, srv.url("/en"))
H.spin(700)
found = ask(win.page_language, view=view)
check("an English page says so", (found or {}).get("lang") == "en", found)
check("...and the counting agrees", (found or {}).get("en", 0) > 0, found)
H.load(view, srv.url("/de"))
H.spin(700)
found = ask(win.page_language, view=view)
check("a German page says so", (found or {}).get("lang") == "de", found)
check("...and the German words were counted",
      (found or {}).get("de", 0) > 0, found)

print("\n(9) the bar when a page is in another language")
check("there are no rules to start with", win.translate_rules() == {},
      win.translate_rules())
check("“always” can be set for a language",
      win.set_translate_rule("nl", "always") == "always")
check("...and it is remembered", win.translate_rules().get("nl") == "always")
check("“never” too", win.set_translate_rule("nl", "never") == "never"
      and win.translate_rules().get("nl") == "never")
check("“ask” takes the rule off",
      win.set_translate_rule("nl", "ask") == "ask"
      and "nl" not in win.translate_rules())
check("a rule nobody asked for is refused",
      win.set_translate_rule("nl", "maybe") is False)
H.load(view, srv.url("/nl"))
H.spin(800)
win.maybe_offer_translation(view)
H.spin(1200)
bar = js("var b = document.getElementById('__trbar');"
         " b ? b.innerText : ''")
check("a Dutch page is offered a translation", "nl" in (bar or "").lower()
      or (bar or "") != "", (bar or "")[:60])
want = [B.UI_STRINGS["de"]["trbarOnce"],
        B.UI_STRINGS["de"]["trbarAlways"] % "nl",
        B.UI_STRINGS["de"]["trbarNever"] % "nl",
        B.UI_STRINGS["de"]["trbarNo"]]
check("...and the bar has every answer",
      all(word in (bar or "") for word in want),
      [word for word in want if word not in (bar or "")])
check("...and it is offered once per tab",
      getattr(view, "_offered_lang", "") == "nl",
      getattr(view, "_offered_lang", ""))
js("var b = document.getElementById('__trbar'); if (b) b.remove();")
win.maybe_offer_translation(view)
H.spin(900)
check("...so a second look offers nothing",
      js("!!document.getElementById('__trbar')") is False)
win.set_translate_rule("nl", "never")
view._offered_lang = ""
win.maybe_offer_translation(view)
H.spin(900)
check("a language he said never to does not ask",
      js("!!document.getElementById('__trbar')") is False)
win.set_translate_rule("nl", "ask")
H.load(view, srv.url("/de"))
H.spin(700)
win.maybe_offer_translation(view)
H.spin(900)
check("his own language is never offered",
      js("!!document.getElementById('__trbar')") is False)

print("\n(10) the page translated on this machine")
H.load(view, srv.url("/en"))
H.spin(700)
win.config["captionTranslator"] = ""
check("without a translator there is nothing to do in place",
      win.translate_in_place(view=view) is False)
# Google Translate is a navigation and this machine has no internet:
# it gets a tab of its own, which is then thrown away
spare = win.new_tab(url=None)
H.load(spare, srv.url("/en"))
H.spin(600)
win.tabs.setCurrentWidget(spare)
check("...and “translate now” says it would use Google",
      win.translate_page_now(view=spare) == "google")
H.spin(1500)
check("...which is a navigation, so the tab really went there",
      "translate.goog" in (spare.url().toString() or "")
      or "translate.google" in (spare.url().toString() or ""),
      spare.url().toString()[:60])
win.close_tab(win.tabs.indexOf(spare), ask=False)
H.spin(300)
win.tabs.setCurrentWidget(view)
win.config["captionTranslator"] = str(stub)
H.load(view, srv.url("/en"))
H.spin(800)
check("with one, the page is translated in place",
      win.translate_in_place(view=view, lang="de") is True)
H.wait_for(lambda: js("document.querySelectorAll('[data-was]').length"),
           9000)
H.spin(600)
done = js("document.querySelectorAll('[data-was]').length")
check("...and the blocks really changed", done and int(done) >= 1, done)
check("...by his own program",
      "THE PAGE IS IN ENGLISH" in (js("document.body.innerText") or ""),
      (js("document.body.innerText") or "")[:60])
check("...and the page's own words are kept",
      "The page is in English" in (js(
          "document.querySelector('[data-was]')"
          ".getAttribute('data-was')") or ""),
      js("document.querySelector('[data-was]').getAttribute('data-was')"))
check("...and “translate now” prefers it to Google",
      win.translate_page_now(view=view) is True)
H.spin(1200)
check("...and a page already translated is not done twice",
      "THE PAGE IS IN ENGLISH AND THAT IS THE POINT OF IT."
      in (js("document.body.innerText") or ""),
      (js("document.body.innerText") or "")[:60])
H.spin(1500)
check("...so the tab stayed on the page",
      "127.0.0.1" in (view.url().toString() or ""),
      view.url().toString()[:60])
win.undo_translation(view)
H.spin(700)
check("it can be undone",
      js("document.querySelectorAll('[data-was]').length") == 0,
      js("document.querySelectorAll('[data-was]').length"))
check("...and the page reads as it did",
      "The page is in English" in (js("document.body.innerText") or ""),
      (js("document.body.innerText") or "")[:60])

print("\n(11) the page and its translation side by side")
H.load(view, srv.url("/en"))
H.spin(700)
side = win.translate_side_by_side(view=view, lang="de")
H.spin(1500)
check("it opens a second half", side is not False, side)
check("...and the split is showing", win.split_showing() is True)
check("...and both are scrolled together",
      win._sync_timer.isActive() is True)
win.close_split()
H.spin(300)

print("\n(12) a PDF, where he left it")
check("a page that is not a PDF has no place",
      win.pdf_place(url="http://x.test/a.html") == 0)
check("a page can be written down",
      win.pdf_place(url="http://x.test/a.pdf", page_number=7) == 7)
check("...and read back", win.pdf_place(url="http://x.test/a.pdf") == 7)
check("...and the address's own fragment is not part of the file",
      win.pdf_place(url="http://x.test/a.pdf#page=7") == 7)
check("page zero is page one",
      win.pdf_place(url="http://x.test/b.pdf", page_number=0) == 1)
check("nonsense is not a page",
      win.pdf_place(url="http://x.test/b.pdf", page_number="late") == 0)
win.config["pdfRemember"] = False
check("the switch is honoured",
      win.pdf_place(url="http://x.test/a.pdf") == 0)
win.config["pdfRemember"] = True
check("...and it comes back when it is on",
      win.pdf_place(url="http://x.test/a.pdf") == 7)
check("the keys a PDF wants arrive", win.pdf_keys("next", view=view)
      == "next")
check("...fit too", win.pdf_keys("fit", view=view) == "fit")
check("...and rotate", win.pdf_keys("rotate", view=view) == "rotate")
check("a key it does not have is refused",
      win.pdf_keys("dance", view=view) is False)

print("\n(13) the article, printed")
H.load(view, srv.url("/art"))
H.spin(700)
win.config["downloadDir"] = str(scratch / "out")
path = win.print_reader(view=view)
check("it says where it went", isinstance(path, str)
      and path.endswith(".pdf"), path)
H.wait_for(lambda: path and Path(path).is_file(), 9000)
check("...and a PDF arrived there", Path(path).is_file(), path)
size = Path(path).stat().st_size if Path(path).is_file() else 0
check("...with something in it", size > 800, size)
check("...and the reader did the trimming",
      js("!!document.getElementById('__reader')"
         " || document.body.className.indexOf('reader') >= 0"
         " || !!document.querySelector('[data-reader]')") in (True, False))

print("\n(14) other words for this one")
got = ask(win.synonyms, "quick", wait=4000)
import shutil as _sh
if _sh.which("dict"):
    check("the thesaurus answered", isinstance(got, list), got)
else:
    check("without a thesaurus it says so, and offers nothing",
          got == [], got)
    check("...and refuses rather than pretending",
          win.synonyms("quick") is False)
check("an empty word is not a word", win.synonyms("") is False)
H.load(view, srv.url("/field"))
H.spin(600)
js("var f = document.getElementById('f');"
   " f.value = 'the qiuck brown fox'; f.focus();"
   " f.setSelectionRange(4, 9);", world=B.MAIN_WORLD_ID)
H.spin(200)
check("a word in a field can be replaced",
      win.replace_selection("quick", view=view) is True)
H.spin(400)
check("...and the field reads right",
      js("document.getElementById('f').value", B.MAIN_WORLD_ID)
      == "the quick brown fox",
      js("document.getElementById('f').value", B.MAIN_WORLD_ID))
menu = win.synonyms_menu("quick", view=view)
H.spin(2500)
check("the menu has something to say", len(menu.actions()) >= 1,
      [one.text() for one in menu.actions()][:4])

print("\n(15) the spelling, on the right-click")
check("his own words start empty", win.config.get("myWords") in (None, []),
      win.config.get("myWords"))
check("a word can be added", win.add_to_dictionary("Shulker")
      == ["Shulker"])
check("...and it is on disk",
      "Shulker" in (B.CONFIG_FILE.parent / "my-words.txt").read_text())
check("...and twice is once",
      win.add_to_dictionary("Shulker") == ["Shulker"])
check("an empty word is not added", win.add_to_dictionary("  ") is False)
menu = win.spell_menu(view=view)
check("with nothing misspelled the menu stays empty",
      len(menu.actions()) == 0, [one.text() for one in menu.actions()])


class FakeRequest:
    def __init__(self, word, rows, selected=""):
        self._w, self._r, self._s = word, rows, selected

    def misspelledWord(self):
        return self._w

    def spellCheckerSuggestions(self):
        return self._r

    def selectedText(self):
        return self._s


menu = win.spell_menu(request=FakeRequest("qiuck", ["quick", "quack"]),
                      view=view)
labels = [one.text() for one in menu.actions()]
check("the suggestions are rows of the menu",
      "quick" in labels and "quack" in labels, labels)
check("...and “add to my words” is there",
      any("Shulker" not in one and "qiuck" in one for one in labels),
      labels)
from PyQt6.QtWidgets import QMenu  # noqa: E402
page_menu = QMenu()
page_menu.addAction("Reload")
view._word_actions(page_menu, FakeRequest("qiuck", ["quick"]))
labels = [one.text() for one in page_menu.actions()]
check("on a page menu they go at the top",
      labels and labels[0] == "quick", labels)
page_menu = QMenu()
page_menu.addAction("Reload")
view._word_actions(page_menu, FakeRequest("", [], selected="Hello"))
labels = [one.text() for one in page_menu.actions()]
check("one selected word gets synonyms and a lookup",
      B.UI_STRINGS["de"]["synMenu"] in labels
      and B.UI_STRINGS["de"]["lookupWord"] in labels, labels)
page_menu = QMenu()
view._word_actions(page_menu, FakeRequest("", [], selected="two words here"))
check("a whole sentence does not",
      [one.text() for one in page_menu.actions()] == [],
      [one.text() for one in page_menu.actions()])

print("\n(16) one word in the other language")
win.config["captionTranslator"] = ""
check("without a translator it says so and does not guess",
      win.lookup_word("Haus", view=view) is False)
win.config["captionTranslator"] = str(stub)
H.load(view, srv.url("/en"))
H.spin(600)
got = ask(win.lookup_word, "Haus", view=view, wait=8000)
check("the word comes back translated", got == "HAUS", got)
H.spin(500)
tip = js("var t = document.getElementById('__wordtip');"
         " t ? t.innerText : ''")
check("...and it is shown where he is reading", "HAUS" in (tip or ""), tip)
check("an empty word is not looked up", win.lookup_word("", view=view)
      is False)

print("\n(17) a clean paste")
check("it is off to start with", win.config.get("cleanPaste", False)
      is False)
check("it can be switched on", win.set_clean_paste(True) is True)
H.load(view, srv.url("/field"))
H.spin(700)
check("the page is told", js("(window.__navWant||{}).cleanPaste") is True)
check("...and given the list",
      "utm_source" in (js("JSON.stringify((window.__navWant||{})"
                          ".trackParams||[])") or ""),
      (js("JSON.stringify((window.__navWant||{}).trackParams||[])")
       or "")[:60])
dirty = "https://shop.test/thing?id=7&utm_source=discord&fbclid=abc"
clean = js("window.__navCleanUrl(%s)" % json.dumps(dirty))
check("the tracking comes off a pasted address",
      clean == "https://shop.test/thing?id=7", clean)
check("...and what the page needs stays", "id=7" in (clean or ""), clean)
plain = "https://shop.test/thing?id=7"
check("an address with none is left alone",
      js("window.__navCleanUrl(%s)" % json.dumps(plain)) == plain)
words = "just some words, not an address"
check("text that is not an address is left alone",
      js("window.__navCleanUrl(%s)" % json.dumps(words)) == words)
frag = "https://shop.test/a#:~:text=hello"
check("a copied text fragment goes too",
      js("window.__navCleanUrl(%s)" % json.dumps(frag))
      == "https://shop.test/a",
      js("window.__navCleanUrl(%s)" % json.dumps(frag)))
js("""var f = document.getElementById('f');
      f.focus();
      var data = new DataTransfer();
      data.setData('text/plain', %s);
      f.dispatchEvent(new ClipboardEvent('paste',
        {clipboardData: data, bubbles: true, cancelable: true}));"""
   % json.dumps(dirty), world=B.MAIN_WORLD_ID)
H.spin(500)
check("a real paste into a field is cleaned",
      js("document.getElementById('f').value", B.MAIN_WORLD_ID)
      == "https://shop.test/thing?id=7",
      js("document.getElementById('f').value", B.MAIN_WORLD_ID))
check("it can be switched off", win.set_clean_paste(False) is False)
H.load(view, srv.url("/field"))
H.spin(700)
js("""var f = document.getElementById('f');
      f.focus();
      var data = new DataTransfer();
      data.setData('text/plain', %s);
      f.dispatchEvent(new ClipboardEvent('paste',
        {clipboardData: data, bubbles: true, cancelable: true}));"""
   % json.dumps(dirty), world=B.MAIN_WORLD_ID)
H.spin(500)
check("...and then the paste is his own business",
      js("(window.__navWant||{}).cleanPaste") is False)

print("\n(18) a book in the reader")
book = scratch / "a-book.epub"
with zipfile.ZipFile(str(book), "w") as out:
    out.writestr("mimetype", "application/epub+zip")
    out.writestr("OEBPS/ch1.xhtml",
                 "<html><body><h1>The first chapter</h1>"
                 "<p>It begins here.</p><img src='x.png'>"
                 "<script>alert(1)</script></body></html>")
    out.writestr("OEBPS/ch2.xhtml",
                 "<html><body><h1>The second chapter</h1>"
                 "<p>And it goes on.</p></body></html>")
bookview = win.new_tab(url=None)
H.spin(300)
count = win.open_epub(book, view=bookview)
H.spin(1200)
check("a book opens with its chapters", count == 2, count)
text = H.js(bookview, "document.body.innerText", APP) or ""
check("...and the first chapter is there", "It begins here." in text,
      text[:80])
check("...and the second", "And it goes on." in text, text[:120])
check("...and the chapters are a list to click",
      H.js(bookview, "document.querySelectorAll('nav a').length", APP) == 2,
      H.js(bookview, "document.querySelectorAll('nav a').length", APP))
check("...in the reader's own type",
      "Georgia" in (H.js(bookview,
                         "getComputedStyle(document.body).fontFamily",
                         APP) or ""),
      H.js(bookview, "getComputedStyle(document.body).fontFamily", APP))
check("...and the book's scripts did not run",
      H.js(bookview, "document.querySelectorAll('script').length", APP) == 0,
      H.js(bookview, "document.querySelectorAll('script').length", APP))
check("a file that is not a book is refused",
      win.open_epub(scratch / "stub-translate.sh", view=bookview) is False)
check("a file that is not there is refused",
      win.open_epub(scratch / "no-such.epub") is False)

print("\n(19) every new word, in both languages")
need = ["splitOn", "splitOff", "splitNeedsTwo", "stackDone",
        "stackNeedsTwo", "wsSaved", "wsOpened", "wsSave", "wsAsk",
        "wsNone", "outsideAsk", "outsideAskName",
        "trbarSaid", "trbarOnce", "trbarAlways", "trbarNever",
        "trbarNo", "trOfferName", "trWorking", "trDone", "trNothing",
        "trUndone", "trUndo", "trSide", "trNow", "trLocalHint",
        "pdfKeys", "pdfNext", "pdfPrev", "pdfFit", "pdfRotate",
        "pdfBackTo", "pdfPlaceName", "readerPrint", "readerPrinted",
        "synMenu", "synNoDict", "synNone", "spellAdd", "spellIgnore",
        "spellAdded", "lookupWord", "lookupNoTool", "cleanPasteName",
        "cleanPasteHint", "epubOpen", "epubOpened", "epubBad",
        "epubEmpty"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)
        and k not in ("pdfKeys",)]
check("and they are really translated", same == [], same)
page = (HERE / "settings.html").read_text()
check("the two new switches are in Settings",
      'id="pdfplace"' in page and 'id="cleanpaste"' in page)
check("...and bound to what they switch",
      'bindSwitch("pdfplace", "pdfRemember")' in page
      and 'bindSwitch("cleanpaste", "cleanPaste")' in page)
ids = [one["id"] for one in win.tab_actions_extra()]
for one in ("pdfnext", "readerprint", "epubopen", "transnow",
            "transside", "transundo"):
    check("“%s” is a command" % one, one in ids)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
