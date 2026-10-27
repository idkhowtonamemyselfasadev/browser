#!/usr/bin/env python3
"""The address bar: what a typed line means, what the drop-down
offers, what the bar shows about the page, and the engines behind a
search.

Offscreen, scratch data, local server. Nothing here asks a search
engine anything: the suggestion service is off in these runs and the
one network thing that is tested (a site's own OpenSearch offer) is
served by the harness.
"""
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
from PyQt6.QtCore import QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import QInputDialog  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


OPENSEARCH_PAGE = """<title>A searchable site</title>
  <link rel="search" type="application/opensearchdescription+xml"
        href="/osd.xml" title="Example Search">
  <p>a page that says how to search it</p>"""

OSD = """<?xml version="1.0"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>Example</ShortName>
  <Url type="text/html" template="https://example.test/find?q={searchTerms}"/>
</OpenSearchDescription>"""

RATES = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01">
 <Cube><Cube time='2026-10-17'>
  <Cube currency='USD' rate='1.0850'/>
  <Cube currency='GBP' rate='0.8600'/>
  <Cube currency='CHF' rate='0.9400'/>
 </Cube></Cube>
</gesmes:Envelope>"""

PAGES = {
    "/searchable": OPENSEARCH_PAGE,
    "/osd.xml": OSD,
    "/rates.xml": RATES,
    "/plain": "<title>Plain</title><p>nothing</p>",
    "/one": "<title>One</title><p>page one</p>",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False,
                                     "searchSuggestions": False}))
win = B.Browser()
win.resize(1100, 700)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
scratch = B.CONFIG_FILE.parent


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(400)
    return view


def js(view, code, world=MAIN):
    return H.js(view, code, world)


print("\n(1) what somebody pasted")
check("a link in angle brackets is a link",
      B.tidy_typed("<https://example.com/x>") == "https://example.com/x",
      B.tidy_typed("<https://example.com/x>"))
check("a link in quotes too",
      B.tidy_typed('"example.com"') == "example.com",
      B.tidy_typed('"example.com"'))
check("a sentence's full stop is not part of the address",
      B.tidy_typed("Look at example.com.") == "Look at example.com.",
      B.tidy_typed("Look at example.com."))
check("...but a bare host with one is",
      B.tidy_typed("example.com.") == "example.com",
      B.tidy_typed("example.com."))
check("SHOUTING at a domain still goes there",
      B.tidy_typed("YOUTUBE.COM") == "youtube.com",
      B.tidy_typed("YOUTUBE.COM"))
check("a space in the middle of a host is a typo, not a search",
      B.tidy_typed("you tube.com") == "youtube.com",
      B.tidy_typed("you tube.com"))
check("the path keeps its own case",
      B.tidy_typed("EXAMPLE.com/Path/File") == "example.com/Path/File",
      B.tidy_typed("EXAMPLE.com/Path/File"))
check("a real search is left exactly as it is",
      B.tidy_typed("best mods for 1.20") == "best mods for 1.20")
check("a dotted thing with no known ending is a search",
      B.tidy_typed("spam.and eggs") == "spam.and eggs",
      B.tidy_typed("spam.and eggs"))
check("a scheme is left alone", B.tidy_typed("http://localhost:8000/x")
      == "http://localhost:8000/x")
check("...but the space after it is not",
      B.tidy_typed("https:// example.com") == "https://example.com",
      B.tidy_typed("https:// example.com"))
check("nothing in, nothing out", B.tidy_typed("   ") == "")

print("\n(2) the address split for the eye")
check("the domain is the registrable part",
      B.bar_domain_parts("https://paypal.com.evil.ru/login")
      == ("https://paypal.com.", "evil.ru", "/login"),
      B.bar_domain_parts("https://paypal.com.evil.ru/login"))
check("a plain host is all domain",
      B.bar_domain_parts("example.com") == ("", "example.com", ""),
      B.bar_domain_parts("example.com"))
check("a sub-domain is dimmed",
      B.bar_domain_parts("https://www.example.com/a/b")
      == ("https://www.", "example.com", "/a/b"),
      B.bar_domain_parts("https://www.example.com/a/b"))
check("a two-part country domain keeps three labels",
      B.bar_domain_parts("https://shop.example.co.uk/x")[1]
      == "example.co.uk",
      B.bar_domain_parts("https://shop.example.co.uk/x"))
check("an IP address is the domain",
      B.bar_domain_parts("http://192.168.1.50:7860/x")[1]
      == "192.168.1.50",
      B.bar_domain_parts("http://192.168.1.50:7860/x"))
check("something that is not an address has no domain",
      B.bar_domain_parts("just some words") == ("just some words", "", ""),
      B.bar_domain_parts("just some words"))

print("\n(3) the address as something to read")
check("percent-encoding is shown as the letters",
      "Hallo Welt" in B.pretty_url("https://example.com/?q=Hallo%20Welt"),
      B.pretty_url("https://example.com/?q=Hallo%20Welt"))
check("an umlaut too",
      "\u00fc" in B.pretty_url("https://example.com/f%C3%BCr"),
      B.pretty_url("https://example.com/f%C3%BCr"))
check("punycode is shown in its own letters",
      "xn--" not in B.pretty_url("https://xn--mnchen-3ya.de/"),
      B.pretty_url("https://xn--mnchen-3ya.de/"))
check("https:// comes off when he asks",
      B.pretty_url("https://example.com/x", hide_scheme=True)
      == "example.com/x",
      B.pretty_url("https://example.com/x", hide_scheme=True))
check("...and www. with it",
      B.pretty_url("https://www.example.com/", hide_scheme=True)
      == "example.com/",
      B.pretty_url("https://www.example.com/", hide_scheme=True))
check("http:// is left visible, because it matters",
      B.pretty_url("http://example.com/", hide_scheme=True)
      .startswith("http://"),
      B.pretty_url("http://example.com/", hide_scheme=True))
check("decoding can be switched off",
      B.pretty_url("https://example.com/?q=a%20b", decode=False)
      == "https://example.com/?q=a%20b")

print("\n(4) a name dressed up as another")
check("a Cyrillic a in apple.com is caught",
      B.lookalike_warning("\u0430pple.com") != "",
      B.lookalike_warning("\u0430pple.com"))
check("two scripts in one label are caught",
      B.lookalike_warning("p\u0430ypal.com").startswith("mixed:")
      or B.lookalike_warning("p\u0430ypal.com").startswith("script:"),
      B.lookalike_warning("p\u0430ypal.com"))
check("a capital I for an l in paypal is caught",
      B.lookalike_warning("paypaI.com") != "",
      B.lookalike_warning("paypaI.com"))
check("an ordinary name is not",
      B.lookalike_warning("example.com") == "",
      B.lookalike_warning("example.com"))
check("...nor is a long German one",
      B.lookalike_warning("sparkasse-koeln-bonn.de") == "",
      B.lookalike_warning("sparkasse-koeln-bonn.de"))
check("nothing in, nothing said", B.lookalike_warning("") == "")

print("\n(5) one letter off a site he visits")
known = ["youtube.com", "modrinth.com", "example.com"]
check("a transposition is caught",
      B.domain_typo("youtuube.com", known) == "youtube.com",
      B.domain_typo("youtuube.com", known))
check("a missing letter is caught",
      B.domain_typo("modrith.com", known) == "modrinth.com",
      B.domain_typo("modrith.com", known))
check("the site itself is not 'did you mean'",
      B.domain_typo("youtube.com", known) == "")
check("something unrelated is not corrected",
      B.domain_typo("wikipedia.org", known) == "",
      B.domain_typo("wikipedia.org", known))
check("and it only ever suggests from the list it was given",
      B.domain_typo("gogle.com", known) == "")

print("\n(6) what may be sent to a search engine")
check("words are a search", B.looks_like_search("best mods 1.20") is True)
check("an address is not", B.looks_like_search("https://example.com")
      is False)
check("a host is not", B.looks_like_search("example.com") is False)
check("a path is not", B.looks_like_search("$HOME/x") is False)
check("a Windows path is not", B.looks_like_search("C:\\\\Users\\\\x")
      is False)
check("an e-mail address is not",
      B.looks_like_search("tim@example.com") is False)
check("a long token is not",
      B.looks_like_search("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9") is False)
check("a card-shaped number is not",
      B.looks_like_search("4111 1111 1111 1111") is False)
check("something very long is not",
      B.looks_like_search("x" * 200) is False)
check("a German sentence is", B.looks_like_search("wie macht man das")
      is True)

print("\n(7) numbers and networks in the bar")
check("0x1f is answered", B.bar_answer("0x1f") is not None)
check("...with the decimal in it", "31" in B.bar_answer("0x1f")[0],
      B.bar_answer("0x1f"))
check("255 in hex is answered",
      B.bar_answer("255 in hex")[1] == "0xFF",
      B.bar_answer("255 in hex"))
check("1010b is binary", B.bar_answer("1010b")[1] == "10",
      B.bar_answer("1010b"))
check("a base can be asked for by its long name",
      B.bar_answer("31 to binary")[1] == "0b11111",
      B.bar_answer("31 to binary"))
check("a network is written out",
      "192.168.1.255" in B.bar_answer("ip 192.168.1.0/24")[0],
      B.bar_answer("ip 192.168.1.0/24"))
check("...with how many addresses are in it",
      "254" in B.bar_answer("ip 192.168.1.0/24")[0],
      B.bar_answer("ip 192.168.1.0/24"))
check("a /32 is answered too",
      B.bar_answer("ip 10.0.0.1/32") is not None)
check("nonsense is not answered", B.bar_answer("ip not.an.ip/99") is None)
check("an ordinary word is not a number", B.bar_answer("hello") is None
      or "=" not in str(B.bar_answer("hello")))

print("\n(8) money, only out of a table he asked for")
B.MONEY_RATES.update({"when": 0, "base": "EUR", "rates": {}})
answer = B.bar_answer("20 usd in eur")
check("with no rates it says so rather than guessing",
      answer is not None and answer[1] == "", answer)
B.MONEY_RATES.update({"when": int(time.time()), "base": "EUR",
                      "rates": {"USD": 1.0850, "GBP": 0.86}})
answer = B.bar_answer("20 usd in eur")
check("with rates it answers", answer is not None and answer[1], answer)
check("...and the sum is right",
      abs(float(answer[1]) - 20 / 1.085) < 0.01, answer)
check("euros into pounds work too",
      abs(float(B.bar_answer("10 eur in gbp")[1]) - 8.6) < 0.01,
      B.bar_answer("10 eur in gbp"))
check("a currency nobody knows is not answered",
      B.bar_answer("10 xyz in eur") is None)
check("the same currency twice is not a conversion",
      B.bar_answer("10 eur in eur") is None)
check("a comma is a decimal point here",
      B.bar_answer("1,50 eur in usd") is not None,
      B.bar_answer("1,50 eur in usd"))

print("\n(9) the bar as a widget")
bar = win.urlbar
check("it is the browser's own line edit",
      isinstance(bar, B.UrlBar), type(bar).__name__)
# The launch tab is still loading start.html when this section is
# reached: sections (1)-(8) are pure-function checks and run in a few
# milliseconds, far quicker than the start page finishes, so the bar
# legitimately showed 0.7 here. Wait for the page the line belongs to
# instead of asserting into the middle of its load.
H.wait_for(lambda: bar.progress() == 0, timeout=8000)
check("the progress starts at nothing", bar.progress() == 0,
      bar.progress())
check("it takes a fraction", bar.set_progress(0.4) == 0.4)
check("...and clamps what is over one", bar.set_progress(4) == 1.0)
check("...and zero means nothing is loading", bar.set_progress(0) == 0)
parts = bar.set_parts("https://www.", "example.com", "/x")
check("it takes the three parts", parts
      == ("https://www.", "example.com", "/x"), parts)
check("the text origin is inside the bar",
      0 < bar.text_origin() < bar.width(), bar.text_origin())
bar.setText("https://www.example.com/x")
H.spin(60)
check("painting with parts and progress does not fall over",
      bar.set_progress(0.5) == 0.5 and bar.isVisible() is not None)
bar.set_progress(0)
view = page("/one")
H.spin(200)
load = bar.drag_payload()
check("a drag from the bar carries the page's address",
      load.get("url", "").startswith("http://127.0.0.1"), load)
check("...and its title", load.get("title"), load)

print("\n(10) what the bar shows")
win.config["barDecode"] = True
win.config["barHideScheme"] = False
shown = win.show_address(srv.url("/one?q=Hallo%20Welt"), view)
check("the address is shown decoded", "Hallo Welt" in shown, shown)
check("...and split for the eye", win.urlbar.parts()[1] == "127.0.0.1",
      win.urlbar.parts())
win.config["barHideScheme"] = True
shown = win.show_address("https://www.example.com/x")
check("https:// and www. come off when he asks",
      shown == "example.com/x", shown)
win.config["barHideScheme"] = False
check("copying gives the real address, not what is shown",
      win.copy_address("https://example.com/f%C3%BCr") is True
      and QGuiApplication.clipboard().text()
      == "https://example.com/f%C3%BCr",
      QGuiApplication.clipboard().text())
long_url = "https://example.com/" + "a" * 300
win.show_address(long_url)
check("an address too long for the bar gets the whole thing on hover",
      "a" * 50 in win.urlbar.toolTip(), win.urlbar.toolTip()[:40])
win.show_address(srv.url("/one"), view)
check("...and a short one needs no tooltip", win.urlbar.toolTip() == "",
      win.urlbar.toolTip())

print("\n(11) the marks beside the address")
win._build_bar_extras()
H.spin(100)
win.show_address(srv.url("/one"), view)
check("an http page is called not secure",
      win._securelbl.isVisible() is True)
check("...in those words",
      win._securelbl.text() == B.UI_STRINGS["en"]["barNotSecure"],
      win._securelbl.text())
win.update_bar_marks("https://example.com/")
check("an https page is not", win._securelbl.isVisible() is False)
win.update_bar_marks("https://p\u0430ypal.com/")
check("a look-alike name is called out",
      win._securelbl.isVisible() is True
      and "dressed" in win._securelbl.text().lower(),
      win._securelbl.text())
check("the lock button is there", win._barextras.get("lockbtn")
      is not None)
check("the copy button is there", win._barextras.get("barcopy")
      is not None)
check("the bar keeps a margin for them",
      win.urlbar.textMargins().left() > 0
      or win.urlbar.textMargins().right() > 0,
      (win.urlbar.textMargins().left(),
       win.urlbar.textMargins().right()))

print("\n(12) the lock's own menu")
win.show_address(srv.url("/one"), view)
menu = win.site_info_menu(view=view)
labels = [a.text() for a in menu.actions() if a.text()]
check("it names the host", any("127.0.0.1" in t for t in labels), labels)
check("...and says the connection is not secure",
      any("not secure" in t.lower() for t in labels), labels)
check("it offers what the page may do",
      any("may do" in t.lower() or "darf" in t.lower() for t in labels),
      labels)
facts = win.site_info(view)
check("the facts say which host", facts.get("host") == "127.0.0.1", facts)
check("...that it is not secure", facts.get("secure") is False)
check("...and which cookie rule it is under",
      "cookieRule" in facts, facts)
check("no certificate is fetched unless it is asked for",
      facts.get("cert") == {}, facts.get("cert"))

print("\n(13) the scopes")
check("@tabs is a scope", win.bar_scope("@tabs mod") == ("tabs", "mod"),
      win.bar_scope("@tabs mod"))
check("a short form works", win.bar_scope("@book x")
      == ("bookmarks", "x"), win.bar_scope("@book x"))
check("the German word works too",
      win.bar_scope("@chronik x") == ("history", "x"),
      win.bar_scope("@chronik x"))
check("something that is not a scope is left alone",
      win.bar_scope("@nonsense x") == ("", "@nonsense x"),
      win.bar_scope("@nonsense x"))
check("and ordinary text has no scope",
      win.bar_scope("just words") == ("", "just words"))

print("\n(14) Settings in the drop-down")
rows = win.settings_rows("dark")
check("a word finds settings rows", len(rows) >= 1, rows[:3])
check("...with the label and the key",
      all(len(r) == 2 and r[0] and r[1] for r in rows), rows[:2])
check("nonsense finds nothing", win.settings_rows("zzzznothing") == [])
check("an empty line finds nothing", win.settings_rows("") == [])

print("\n(15) the site's own search")
check("YouTube is searchable",
      "search_query=" in win.site_search_url("youtube.com", "mods"),
      win.site_search_url("youtube.com", "mods"))
check("...with the words in it",
      "mods" in win.site_search_url("youtube.com", "mods"))
check("Modrinth too", "modrinth.com" in win.site_search_url(
    "modrinth.com", "sodium"))
check("a sub-domain counts as the site",
      win.site_search_url("www.youtube.com", "x") != "")
check("a site nobody knows is not searchable",
      win.site_search_url("example.invalid", "x") == "")
check("a site that said how is searchable",
      win.note_opensearch("example.test", "Example",
                          "https://example.test/find?q={searchTerms}")
      is True
      and win.site_search_url("example.test", "abc")
      == "https://example.test/find?q=abc",
      win.site_search_url("example.test", "abc"))
check("a template with nowhere for the words is refused",
      win.note_opensearch("bad.test", "Bad", "https://bad.test/")
      is False)
win._site_search = "youtube.com"
check("Tab starts a site search", win.bar_tab_pressed() is True)
check("...and the bar says which site",
      win.searching_site() == "youtube.com", win.searching_site())
where = win._resolve_typed("sodium mod")
check("what he types next searches that site",
      "youtube.com" in where and "sodium" in where, where)
check("...and the mode is over", win.searching_site() == "")

print("\n(16) completing a domain as he types")
win.history = [{"url": "https://modrinth.com/mods", "title": "Modrinth",
                "t": int(time.time())}] * 3 + [
    {"url": "https://modcheck.example/x", "title": "Other",
     "t": int(time.time())}]
check("the site he goes to most is filled in",
      win.inline_completion("mod") == "modrinth.com",
      win.inline_completion("mod"))
check("one letter is not enough", win.inline_completion("m") == "")
check("a space means he is searching", win.inline_completion("mod x")
      == "")
check("a site he asked not to be offered is not",
      "modrinth.com" in win.never_suggest("modrinth.com")
      and win.inline_completion("mod") == "modcheck.example",
      win.inline_completion("mod"))
win.never_suggest("modrinth.com", on=False)
win.config["barInline"] = False
check("and it can be switched off", win.inline_completion("mod") == "")
win.config["barInline"] = True

print("\n(17) the rows the drop-down shows")
win.bookmarks = [{"type": "link", "title": "Modrinth",
                  "url": "https://modrinth.com/"}]
rows = win._own_suggestions("modrinth")
check("a bookmark turns up", any("Modrinth" in r for r in rows), rows[:3])
check("...and the history", any("modrinth.com/mods" in r for r in rows),
      rows[:4])
rows = win._own_suggestions("2+2")
check("an answer row comes first", rows and rows[0].startswith("= "),
      rows[:2])
check("...and Enter on it copies",
      win._suggest_actions.get(rows[0], ("", ""))[0] == "copy",
      win._suggest_actions.get(rows[0]))
rows = win._own_suggestions("@bookmarks modrinth")
check("a scope leaves the other sources out",
      rows and all("★" in r or not r for r in rows), rows[:3])
win.config["barSources"] = {"history": False, "bookmarks": True,
                            "tabs": True, "answers": True, "search": True,
                            "settings": True, "windows": True}
rows = win._own_suggestions("modrinth")
check("a source he switched off is not used",
      not any("modrinth.com/mods —" in r for r in rows), rows[:3])
win.config.pop("barSources", None)
win.config["barRows"] = 5
check("the number of rows is his", win.bar_row_limit() == 5)
win.config["barRows"] = 14

print("\n(18) the engines")
engines = win.all_engines()
check("the built-in ones are there", len(engines) >= 3, len(engines))
check("adding one works",
      win.add_engine("Mine", "https://mine.test/?q=%s", "m") is True)
check("...and it is in the list",
      any(r["name"] == "Mine" for r in win.all_engines()))
check("an address with nowhere for the words is refused",
      win.add_engine("Bad", "https://bad.test/") is False)
check("a search with it comes out right",
      win.engine_url("Mine", "a b") == "https://mine.test/?q=a%20b",
      win.engine_url("Mine", "a b"))
check("the list can be reordered",
      win.add_engine("Second", "https://two.test/?q=%s") is True
      and win.move_engine("Second", up=True) is True)
check("...and one can be taken off",
      win.drop_engine("Second") is True
      and not any(r["name"] == "Second" for r in win.all_engines()))
check("a keyword from the engines list reaches the resolver",
      win.parse_engines("Mods|https://modrinth.com/mods?q=%s|mo")
      and "modrinth.com" in win._resolve_typed("mo sodium"),
      win._resolve_typed("mo sodium"))
check("German text can go to its own engine",
      win.parse_lang_engines("de=Mine en=google")
      and win.engine_for_text("wie geht das") == "Mine",
      win.engine_for_text("wie geht das"))
check("...and English to the other",
      win.engine_for_text("how does this work") == "google",
      win.engine_for_text("how does this work"))
check("the language guess reads the letters",
      win.guess_language("für die Tür") == "de"
      and win.guess_language("for the door") == "en")
win.config.pop("langEngines", None)
win.config["privateEngine"] = "Mods"
check("a private tab can search somewhere else",
      win.private_engine() == "Mods", win.private_engine())
win.config["privateEngine"] = ""

print("\n(19) keywords")
check("a keyword can be set",
      win.set_keyword("https://example.test/k", "kk") is True)
check("...and it opens that address",
      win._resolve_typed("kk") == "https://example.test/k",
      win._resolve_typed("kk"))
check("a keyword with words after it, on a plain bookmark, is a search",
      "example.test/k" not in win._resolve_typed("kk and words"),
      win._resolve_typed("kk and words"))
check("a keyword whose address takes words uses them",
      win.set_keyword("https://mods.test/?q=%s", "mm")
      and win._resolve_typed("mm sodium")
      == "https://mods.test/?q=sodium",
      win._resolve_typed("mm sodium"))

print("\n(20) the searches page is gone, by request")
check("the browser does not write searches down any more",
      not any(hasattr(win, name) for name in
              ("search_log", "note_search_row", "search_rows",
               "clear_search_log", "open_searches")),
      [n for n in ("search_log", "note_search_row", "search_rows",
                   "clear_search_log", "open_searches") if hasattr(win, n)])
check("...and the page itself is not there", not (HERE / "searches.html").exists())
check("an empty bar offers the clipboard and nothing he searched for",
      all("\u2b8c" in row for row in win.empty_bar_rows()),
      win.empty_bar_rows())
cfg = {"searchLog": [{"q": "old"}], "recentSearches": ["old"],
       "searchLogOn": True, "recentSearchList": True}
B._migrate_drop_searches(cfg)
check("and a config that still holds them has them taken out", cfg == {}, cfg)

print("\n(21) the browser's own pages all get their bridge")
check("the list is one list now", len(B.OWN_PAGES) >= 9, B.OWN_PAGES)
for name in ("notes.html", "player.html", "mictest.html"):
    check(name + " is on it",
          B.is_internal_page(QUrl.fromLocalFile(str(HERE / name)))
          is True)
check("...and a page of somebody else's is not",
      B.is_internal_page(QUrl.fromLocalFile(str(scratch / "start.html")))
      is False)
# and the proof that matters: the page gets a channel with the
# settings bridge on it, with the slot its own JavaScript calls.
# Before this wave notes.html was handed the password channel, so
# bridge.desk did not exist and the drawer did nothing at all.
ASK_CHANNEL = """(function () {
  if (typeof qt === 'undefined' || typeof QWebChannel === 'undefined') {
    return 'nochannel';
  }
  new QWebChannel(qt.webChannelTransport, function (ch) {
    window.__objs = Object.keys(ch.objects).join(',');
    window.__hasDesk = !!(ch.objects.bridge && ch.objects.bridge.desk);
    window.__hasPw = !!ch.objects.pw;
  });
  return 'asked';
})()"""
notes = win.new_tab(url=None)
notes.page().prime_trust(win.notes_url())
H.load(notes, win.notes_url().toString())
H.spin(600)
check("the notes page is handed a channel",
      js(notes, ASK_CHANNEL) == "asked", js(notes, ASK_CHANNEL))
H.wait_for(lambda: js(notes, "window.__objs") is not None, 6000)
check("...and the object on it is the settings bridge",
      "bridge" in str(js(notes, "window.__objs") or ""),
      js(notes, "window.__objs"))
check("...with the drawer slot its own script calls",
      js(notes, "!!window.__hasDesk") is True,
      js(notes, "window.__objs"))
site = page("/plain")
check("an ordinary site has no channel in its own world at all",
      js(site, ASK_CHANNEL) == "nochannel", js(site, ASK_CHANNEL))
check("...and the password channel it does get is in an isolated world",
      js(site, "typeof window.pw") == "undefined",
      js(site, "typeof window.pw"))

print("\n(22) the keys in the bar")
view = page("/one")
win.urlbar.setFocus()
win.urlbar.setText("")
check("typing is remembered per tab",
      win.note_typed("first", view) and win.note_typed("second", view)
      and win.typed_history(view) == ["first", "second"],
      win.typed_history(view))
win._typed_at = len(win.typed_history(view))
check("Up gives the last thing typed here",
      win.step_typed(back=True, view=view) == "second",
      win.step_typed(back=True, view=view))
check("...and again the one before",
      win.step_typed(back=True, view=view) == "first")
check("Down comes back", win.step_typed(back=False, view=view)
      == "second")
other = page("/plain")
check("another tab has its own list", win.typed_history(other) == [],
      win.typed_history(other))
win.urlbar.setText(srv.url("/plain"))
before = win.tabs.count()
check("Shift+Enter opens a background tab",
      win.navigate_background() is True)
check("...and it is a new tab", win.tabs.count() == before + 1)
check("...that did not take the focus", win.tabs.currentWidget() is other,
      win.tabs.currentIndex())
QGuiApplication.clipboard().setText(srv.url("/one"))
check("middle-click pastes and goes", win.paste_and_go() is True)
win.urlbar.setText("")
check("...and an empty clipboard does nothing",
      (QGuiApplication.clipboard().clear(), win.paste_and_go())[1] is False)

print("\n(23) Ctrl+L, twice")
win.show_address("https://example.com/a/long/path", view)
win.urlbar.setFocus()
# each press is asked for once: the detail of a check must not call
# it again, or the second press happens before the first is read
first = win.focus_address()
check("the first press selects everything", first == "all", first)
check("...really everything",
      win.urlbar.selectedText() == win.urlbar.text(),
      win.urlbar.selectedText())
second = win.focus_address()
check("the second selects the path", second == "path", second)
check("...which is the path",
      win.urlbar.selectedText() == "/a/long/path",
      win.urlbar.selectedText())
win.urlbar.setText("https://example.com/other/path")
third = win.focus_address()
check("a changed address selects everything again", third == "all", third)
check("Escape puts the address back",
      win.restore_address() is True)
check("clearing the bar keeps the focus",
      win.clear_address() is True and win.urlbar.text() == ""
      and win.urlbar.hasFocus() is True)

print("\n(24) the bar's size and place")
win.config["barTextSize"] = 130
check("the text can be made bigger", win.bar_font_scale() == 130)
check("...and the font really changed",
      win.urlbar.font().pointSize() > 0, win.urlbar.font().pointSize())
win.config["barTextSize"] = 100
win.bar_font_scale()
check("the toolbar can go under the page",
      win.bar_at_bottom(True) is True)
column = win.centralWidget().layout()
check("...and it really moved",
      column.indexOf(win.chrome) == column.count() - 1,
      (column.indexOf(win.chrome), column.count()))
check("and back up again", win.bar_at_bottom(False) is False)
check("...really back", column.indexOf(win.chrome) == 0,
      column.indexOf(win.chrome))

print("\n(25) the progress in the bar")
win.config["barProgress"] = True
check("a loading page fills the line",
      win.bar_progress(40, win.current()) == 0.4,
      win.bar_progress(40, win.current()))
check("...and finishing empties it",
      win.bar_progress(0, win.current()) == 0)
win.config["barProgress"] = False
check("it can be switched off",
      win.bar_progress(50, win.current()) == 0)
win.config["barProgress"] = True
# loadProgress hands out a percent, always. The bar used to guess, and
# treated anything <= 1 as a finished fraction: 1% flashed a full bar.
check("one percent is one percent, not a full bar",
      win.bar_progress(1, win.current()) == 0.01,
      win.bar_progress(1, win.current()))
check("...and ninety-nine is not finished either",
      win.bar_progress(99, win.current()) == 0.99,
      win.bar_progress(99, win.current()))

# Switching away from a half-loaded tab left its line standing in the
# bar for good: that tab's own loadFinished(0) lands when it is no
# longer in front and was dropped, and nothing else cleared the bar.
#
# Every tab in this block has to be a tab that is NOT loading, because
# the thing under test is what the bar does on a switch and a real load
# writes the bar legitimately. `new_tab(url=None)` is not an empty tab
# -- url=None means "whatever an empty tab opens on", so it loads the
# start page and reports its progress like any other page. That made
# these checks fail about one run in twelve with the bar reading 0.7:
# not the switch failing to clear it, a real loadProgress(70) from the
# new tab, honoured exactly as intended. `blank=True` is the one that
# opens a tab and loads nothing (see `if not blank:` in new_tab).
H.wait_for(lambda: win.urlbar.progress() == 0, timeout=8000)
loading = win.current()
win.bar_progress(60, loading)
check("a loading tab puts its line up", win.urlbar.progress() == 0.6,
      win.urlbar.progress())
fresh = win.new_tab(url=None, blank=True)
H.spin(150)
check("the new tab is loading nothing of its own",
      not fresh.url().toString(), fresh.url().toString())
check("switching to another tab takes the line down",
      win.urlbar.progress() == 0, win.urlbar.progress())
check("...and the old tab finishing in the background leaves it down",
      win.bar_progress(0, loading) is False
      and win.urlbar.progress() == 0, win.urlbar.progress())
win.tabs.setCurrentIndex(win.tabs.indexOf(loading))
H.spin(150)
check("...and coming back shows that tab, which is no longer loading",
      win.urlbar.progress() == 0, win.urlbar.progress())
win.bar_progress(35, win.current())
win.tabs.setCurrentIndex(win.tabs.indexOf(fresh))
H.spin(150)
check("a tab still loading when you leave it keeps its own place",
      win.urlbar.progress() == 0, win.urlbar.progress())
win.tabs.setCurrentIndex(win.tabs.indexOf(loading))
H.spin(150)
check("...and shows it again when you come back",
      abs(win.urlbar.progress() - 0.35) < 0.001, win.urlbar.progress())
win.bar_progress(0, win.current())

print("\n(26) a site that offers its own search")
site = page("/searchable")
H.spin(1200)
check("the page's offer was read",
      getattr(site, "_opensearch", None) is not None,
      getattr(site, "_opensearch", None))
win.config.pop("openSearch", None)
taken = []
win.offer_opensearch(site)
H.wait_for(lambda: win.opensearch_for("127.0.0.1"), 8000)
check("adding it reads the description file",
      "example.test/find" in win.opensearch_for("127.0.0.1"),
      win.opensearch_for("127.0.0.1"))
check("...and the site is searchable from the bar now",
      "q=abc" in win.site_search_url("127.0.0.1", "abc"),
      win.site_search_url("127.0.0.1", "abc"))

print("\n(27) the rates, fetched only when asked")
B.MONEY_RATES.update({"when": 0, "rates": {}})
win.config["moneyRates"] = False
check("off, nothing is fetched", win.fetch_rates() is False)
win.config["moneyRates"] = True
win.config["moneyUrl"] = srv.url("/rates.xml")
got = []
check("on, the file is fetched", win.fetch_rates(then=got.append) is True)
H.wait_for(lambda: got, 8000)
check("...and the table is filled", got and got[0] == 3, got)
check("the answer works now",
      B.bar_answer("20 usd in eur") is not None
      and B.bar_answer("20 usd in eur")[1], B.bar_answer("20 usd in eur"))
check("a second ask inside the day does not fetch again",
      win.fetch_rates() is False)
check("what was fetched survives a restart",
      win.load_saved_rates() == 3, win.load_saved_rates())

print("\n(28) Settings, the words and the keys")
page_text = (HERE / "settings.html").read_text()
check("there is a section for the bar",
      'data-desc="descBar"' in page_text)
for ident in ("barprogress", "bardimpath", "bardecode", "barhidescheme",
              "barinline", "barlock", "barcopybtn", "barclearbtn",
              "barqrbtn", "barbottom", "moneyrates",
              "barrows", "bartextsize", "privateengine",
              "langenginestext", "barsourcestext", "enginestext"):
    check("Settings has a row for " + ident, ('id="%s"' % ident)
          in page_text)
for ident, cfgkey in (("bardimpath", "barDimPath"),
                      ("barinline", "barInline"),
                      ("moneyrates", "moneyRates"),
                      ("barbottom", "barBottom")):
    check("...wired to " + cfgkey,
          ('bindSwitch("%s", "%s")' % (ident, cfgkey)) in page_text)
need = ["barMenu", "barNotSecure", "barLookalike", "barCertLook",
        "barCopyTip", "barClearTip", "barQrTip", "barAnswerCopied",
        "barDidYouMean", "barSearchSite", "barBackground",
        "barKeywordTitle", "barNeverSuggest", "barEngines",
        "barProgressName",
        "barDimPathName", "barDecodeName", "barInlineName",
        "barRowsName", "barTextSizeName", "barBottomName",
        "moneyRatesName", "enginesName", "descBar"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)
registry = win.actions_list()
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
clash = {k: v for k, v in taken.items() if len(v) > 1}
check("no two actions want the same key", clash == {}, clash)
ids = [r["id"] for r in registry]
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1])
for wanted in ("barcopyurl", "barqrcode", "barsiteinfo", "barengines",
               "barkeyword", "baropensearch", "barbottom"):
    check("there is an action for " + wanted, wanted in ids)

print("\n(29) the test rig cleans up after itself")
check("the harness takes its scratch directory away at exit",
      "_tidy_scratch" in (HERE / "tests" / "harness.py").read_text())
check("...and anything left behind by a run that is gone",
      "ProcessLookupError" in (HERE / "tests" / "harness.py").read_text())

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails)))
else:
    print("all good")
srv.stop()
win.close()
sys.exit(1 if fails else 0)
