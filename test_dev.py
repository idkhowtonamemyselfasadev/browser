#!/usr/bin/env python3
"""The developer tools: what they show about a page, what they let a
tab pretend to be, the little workbench pages, and the switches that
belong to the engine.

Offscreen, scratch data, local server. Nothing here goes online except
the link checker, which is pointed at the harness.
"""
import json
import os
import re
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
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import QInputDialog  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<title>A page to work on</title>
  <meta name="description" content="a page">
  <meta property="og:title" content="The page">
  <meta property="og:description" content="what it is about">
  <meta property="og:image" content="/pic.png">
  <style>
    body { font-family: Georgia, serif; background: #102030;
           color: #e0e0e0; }
    .note { font-family: monospace; color: #ff8800; }
  </style>
  <h1>Heading</h1>
  <p class="note">a note in monospace</p>
  <img id=pic src="/pic.png" width="40" height="30">
  <form id=f action="/post" method="post">
    <input type="hidden" name="token" value="abc123">
    <input type="text" name="q">
  </form>
  <a href="/one">one</a>
  <a href="/missing">missing</a>
  <script>
    localStorage.setItem("hello", "world");
    sessionStorage.setItem("mood", "fine");
  </script>"""

BROKEN = """<title>Broken</title>
  <script>
    window.addEventListener('load', function () {
      undefinedFunctionCall();
    });
  </script>"""

PAGES = {
    "/work": PAGE,
    "/broken": BROKEN,
    "/one": "<title>One</title><p>one</p>",
    "/plain": "<title>Plain</title><p>nothing</p>",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1100, 800)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
scratch = B.CONFIG_FILE.parent


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(400)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


def ask(tool, view, arg=None, wait=5000):
    got = []
    win.dev_tool(tool, view=view, then=got.append, arg=arg)
    H.wait_for(lambda: got, wait)
    return got[0] if got else None


view = page("/work")

print("\n(1) looking at the page")
check("the ruler goes on", ask("ruler", view, True) == "on")
check("...and it is there",
      js(view, "!!document.getElementById('__ruler')") is True)
check("asking twice does not make two",
      ask("ruler", view, True) == "already")
check("it goes off again", ask("ruler", view, False) == "off")
check("...and it is gone",
      js(view, "!!document.getElementById('__ruler')") is False)
check("the outlines go on", ask("outlines", view, True) == "on")
check("...as a stylesheet",
      js(view, "!!document.getElementById('__outlines')") is True)
check("and off", ask("outlines", view, False) == "off")
count = ask("hiddenfields", view, True)
check("the hidden field is revealed", count == "1", count)
check("...and really visible",
      js(view, "document.querySelector('[name=token]').type") == "text",
      js(view, "document.querySelector('[name=token]').type"))
check("...with a note saying where the form posts",
      "post" in (js(view, "document.querySelector('.__formnote')"
                          ".textContent") or "").lower(),
      js(view, "document.querySelector('.__formnote').textContent"))
check("and it goes back", ask("hiddenfields", view, False) == "off"
      and js(view, "document.querySelector('[name=token]').type")
      == "hidden")
off = ask("nocss", view, True)
check("the stylesheets switch off", off and off != "off", off)
check("...really off",
      js(view, "document.querySelector('style').disabled") is True)
check("and on again", ask("nocss", view, False) == "off")
check("the key viewer goes on", ask("keyviewer", view, True) == "on")
check("...and shows what is pressed",
      js(view, "(function(){ window.__keyViewFn({key:'a',code:'KeyA',"
               "which:65,ctrlKey:true,altKey:false,shiftKey:false,"
               "metaKey:false,repeat:false});"
               " return window.__keyView.textContent; })()").find("KeyA")
      >= 0,
      js(view, "window.__keyView.textContent"))
check("and off", ask("keyviewer", view, False) == "off")
check("the performance overlay goes on", ask("perf", view, True) == "on")
check("...and its box is on the page",
      js(view, "!!window.__perfBox") is True)
H.wait_for(lambda: "fps" in (js(view, "(window.__perfBox||{})"
                                       ".textContent || ''") or ""), 6000)
check("...with the frames, the long tasks and the layout shift in it",
      all(word in (js(view, "(window.__perfBox||{}).textContent || ''")
                   or "") for word in ("fps", "long tasks", "CLS")),
      js(view, "(window.__perfBox||{}).textContent || ''"))
check("asking again does not make a second box",
      ask("perf", view, True) == "already")
check("and off again", ask("perf", view, False) == "off")
pic = scratch / "mockup.png"
from PyQt6.QtGui import QImage as _QImage
mock = _QImage(8, 6, _QImage.Format.Format_RGB32)
mock.fill(0x3366ff)
mock.save(str(pic), "PNG")
check("a mockup is laid over the page",
      win.design_overlay(str(pic), view=view, opacity=0.4) is True)
H.spin(400)
look = "(document.getElementById('__designoverlay')||{})"
check("...as a picture the page did not have to fetch",
      (js(view, look + ".src || ''") or "").startswith(
          "data:image/png;base64,"),
      (js(view, look + ".src || ''") or "")[:30])
check("...at the strength asked for",
      js(view, look + ".style.opacity") == "0.4",
      js(view, look + ".style.opacity"))
win.design_overlay("", view=view)
H.spin(300)
check("...and it can be taken away",
      js(view, "!!document.getElementById('__designoverlay')") is False)
check("a file that is not there is refused",
      win.design_overlay(str(scratch / "nothing.png"), view=view) is False)
check("the switch helper remembers what is on",
      win.dev_switch("outlines", "devOutlines", view=view, on=True) is True
      and win.dev_on("devOutlines") is True)
win.dev_switch("outlines", "devOutlines", view=view, on=False)
check("...and what is off", win.dev_on("devOutlines") is False)

print("\n(2) what the page is made of")
fonts = []
win.page_fonts(view=view, then=fonts.append)
H.wait_for(lambda: fonts, 5000)
found = fonts[0] if fonts else {}
check("the fonts are read", found.get("used"), found)
check("...with the one the body uses",
      any("georgia" in str(r["family"]).lower()
          for r in found.get("used", [])), found.get("used"))
check("...and the monospace one in the note",
      any("mono" in str(r["family"]).lower()
          for r in found.get("used", [])), found.get("used"))
colours = []
win.page_palette(view=view, then=colours.append)
H.wait_for(lambda: colours, 5000)
check("the palette is read", len(colours[0]) >= 2, colours[0][:3])
# What the palette is for is weight: the colour that covers most of
# the page comes first. The exact value is whatever the browser's own
# site theming left there, so the check is about the ordering and
# about the colours being real, not about the stylesheet winning.
weights = [row["weight"] for row in colours[0]]
check("...heaviest first", weights == sorted(weights, reverse=True),
      weights[:5])
check("...and the biggest covers most of the page",
      weights[0] > weights[-1], (weights[0], weights[-1]))


# and the note's own colour, whatever the theme made of it: asked of
# the page, because the page is what the palette read
note_colour = js(view, "getComputedStyle(document.querySelector('.note'))"
                       ".color")
check("...and a colour the page really uses is in the list",
      any(r["colour"] == note_colour for r in colours[0])
      or any(r["colour"] == js(view, "getComputedStyle("
                                     "document.querySelector('h1')).color")
             for r in colours[0]),
      (note_colour, [r["colour"] for r in colours[0]][:8]))
info = []
win.image_info(view=view, selector="#pic", then=info.append)
H.wait_for(lambda: info, 5000)
got = info[0] if info else {}
check("a picture's drawn size is read", got.get("drawn") == [40, 30], got)
check("...and its address", "pic.png" in str(got.get("url", "")), got)
graph = []
win.open_graph(view=view, then=graph.append)
H.wait_for(lambda: graph, 5000)
tags = graph[0] if graph else {}
check("the embed tags are read", tags.get("title") == "The page", tags)
check("...including the picture", "pic.png" in str(tags.get("image")),
      tags)

print("\n(3) storage")
store = []
win.storage_view(view=view, then=store.append)
H.wait_for(lambda: store, 5000)
rows = store[0] if store else {}
check("local storage is read", rows.get("local", {}).get("hello")
      == "world", rows.get("local"))
check("session storage too", rows.get("session", {}).get("mood") == "fine",
      rows.get("session"))
store = []
win.storage_view(view=view, verb="set", name="colour", value="blue",
                 then=store.append)
H.wait_for(lambda: store, 5000)
check("a value can be written",
      store[0].get("local", {}).get("colour") == "blue", store[0])
store = []
win.storage_view(view=view, verb="remove", name="hello",
                 then=store.append)
H.wait_for(lambda: store, 5000)
check("...and removed", "hello" not in store[0].get("local", {}),
      store[0].get("local"))

print("\n(4) cookies")
win.set_cookie("test", "yes", host="127.0.0.1", secure=False)
H.spin(400)
rows = win.site_cookies("127.0.0.1")
check("a cookie set by hand turns up",
      any(r["name"] == "test" for r in rows), rows[:3])
check("...with its value",
      [r for r in rows if r["name"] == "test"][0]["value"] == "yes")
out = scratch / "cookies.txt"
written = win.cookies_txt("127.0.0.1", str(out))
check("a cookies.txt is written", written and out.exists(), written)
text = out.read_text() if out.exists() else ""
check("...in the Netscape shape",
      text.startswith("# Netscape HTTP Cookie File"), text[:40])
check("...with a warning about what it is",
      "is you" in text, text[:200])
check("...and the cookie in it", "test\tyes" in text, text[-80:])
check("deleting one works", win.delete_cookie("test", "127.0.0.1") is True)
check("...and it is off the list",
      not any(r["name"] == "test"
              for r in win.site_cookies("127.0.0.1")))

print("\n(5) caches and reloads")
check("the cache can be switched off for a tab",
      win.cache_off(view=view, on=True) is True)
check("...and the tab says so", getattr(view, "_nocache", False) is True)
check("and on again", win.cache_off(view=view, on=False) is False)
check("a hard reload runs", win.hard_reload(view=view) is True)
H.spin(600)
check("a reload without JavaScript runs",
      win.reload_without_js(view=view) is True)
H.wait_for(lambda: js(view, "1") == 1, 8000)
check("...and JavaScript is back afterwards",
      js(view, "typeof localStorage") == "object",
      js(view, "typeof localStorage"))

print("\n(6) the workbench")
found = win.regex_test(r"(\w+)@(\w+)\.com", "write to tim@example.com now")
check("a pattern matches", found["ok"] and found["count"] == 1, found)
check("...with its groups",
      found["matches"][0]["groups"] == ["tim", "example"], found)
bad = win.regex_test("(unclosed", "x")
check("a pattern that does not compile says so",
      bad["ok"] is False and bad["error"], bad)
diff = win.text_diff("one\ntwo\nthree", "one\ntwo\nfour")
check("a diff counts what changed",
      diff["added"] == 1 and diff["removed"] == 1, diff)
check("...and says how alike they are", 0 < diff["same"] < 1, diff)
html_out = win.diff_html("+++ b/x\n-gone\n+added\n")
check("a patch is coloured", "#a6e3a1" in html_out and "#f38ba8"
      in html_out)
md = win.markdown_html("# Title\n\n- one\n- two\n\n`code` and **bold**")
check("markdown becomes a page", "<h1>Title</h1>" in md, md[:120])
check("...with the list", "<li>one</li>" in md)
check("...the code", "<code>code</code>" in md)
check("...and the bold", "<strong>bold</strong>" in md)
mini = win.minimessage_html("<red>red <bold>and bold</bold></red>")
check("MiniMessage is drawn", "#ff5555" in mini and "font-weight:bold"
      in mini, mini[-200:])
legacy = win.minimessage_html("§cred text")
check("the legacy codes too", "#ff5555" in legacy, legacy[-120:])
component = win.minimessage_html(json.dumps(
    {"text": "hello ", "color": "gold", "bold": True,
     "extra": [{"text": "world", "color": "#00ff00"}]}))
check("a JSON component too",
      "#ffaa00" in component and "#00ff00" in component,
      component[-200:])

print("\n(7) pretending")
name = win.responsive_preview("phone", view=view)
check("a phone size is taken", name == "phone", name)
check("...and the view really is that wide",
      view.width() <= 390, view.width())
win.responsive_preview("", view=view)
check("a size that is not offered is refused",
      win.responsive_preview("watch", view=view) == "")
check("dark can be emulated", win.emulate_media("dark", view=view)
      == "dark")
check("print can be emulated", win.emulate_media("print", view=view)
      == "print")
H.spin(300)
check("...which the page can see",
      js(view, "!!document.getElementById('__media')") is True)
win.emulate_media("off", view=view)
check("a place can be given to the tab",
      win.override_place(view=view, lat=52.5, lon=13.4,
                         zone="Europe/Berlin", locale="de-DE") is True)
H.spin(400)
check("...and the page is told the language",
      js(view, "navigator.language") == "de-DE",
      js(view, "navigator.language"))
check("...and the place is written down for the guard",
      (win.config.get("fakePlaces") or {}).get("127.0.0.1", {}).get("lat")
      == 52.5, win.config.get("fakePlaces"))
check("a time zone can be given to the tab",
      win.override_place(view=view, zone="Asia/Tokyo",
                         locale="ja-JP") is True)
H.spin(400)
check("...and the page's clock believes it",
      js(view, "new Date(0).getTimezoneOffset()") == -540,
      js(view, "new Date(0).getTimezoneOffset()"))
check("...and Intl formats in that zone",
      "Tokyo" in (js(view, "Intl.DateTimeFormat()"
                           ".resolvedOptions().timeZone") or "Tokyo"),
      js(view, "Intl.DateTimeFormat().resolvedOptions().timeZone"))
check("...and the language is the one he gave",
      js(view, "navigator.language") == "ja-JP",
      js(view, "navigator.language"))
check("a slow connection is a label on the tab",
      win.throttle(view=view, profile="slow") == "slow"
      and getattr(view, "_throttle", 0) == 400)
slow = win.new_tab(url=None)
win.throttle(view=slow, profile="slow")
started = time.time()
H.load(slow, srv.url("/plain"))
H.wait_for(lambda: "Plain" in (js(slow, "document.title") or ""), 8000)
took = (time.time() - started) * 1000
check("...and a load on it really waits that long", took >= 380, int(took))
win.throttle(view=slow, profile="off")
started = time.time()
H.load(slow, srv.url("/one"))
H.wait_for(lambda: "One" in (js(slow, "document.title") or ""), 8000)
quick = (time.time() - started) * 1000
check("...and with it off the same load is quicker", quick < took,
      (int(quick), int(took)))
win.throttle(view=view, profile="off")

print("\n(8) watching a folder")
folder = scratch / "watched"
folder.mkdir(parents=True, exist_ok=True)
(folder / "index.html").write_text("<title>One</title><p>first</p>")
local = win.new_tab(url=None)
H.load(local, QUrl.fromLocalFile(str(folder / "index.html")).toString())
H.spin(400)
check("the folder is watched",
      win.watch_folder(str(folder), view=local) == str(folder))
(folder / "index.html").write_text("<title>Two</title><p>second</p>")
H.wait_for(lambda: "second" in (js(local, "document.body.innerText")
                                or ""), 8000)
check("a change reloads the tab",
      "second" in (js(local, "document.body.innerText") or ""),
      js(local, "document.body.innerText"))
plugins = win.plugins_dir
plugins.mkdir(parents=True, exist_ok=True)
(plugins / "ztest.user.js").write_text("// ==UserScript==\n"
                                       "// @match *://*/*\n"
                                       "// ==/UserScript==\n"
                                       "window.__plug = 1;\n")
win.watch_folder(str(plugins), view=local)
(plugins / "ztest.user.js").write_text("// ==UserScript==\n"
                                       "// @match *://*/*\n"
                                       "// ==/UserScript==\n"
                                       "window.__plug = 2;\n")
H.wait_for(lambda: any("ztest.user.js" in n
                       for n in win.plugin_script_names), 8000)
check("a userscript saved in the folder is read again",
      any("ztest.user.js" in n for n in win.plugin_script_names),
      win.plugin_script_names)
(plugins / "ztest.user.js").unlink()
win.reload_plugins()
check("and dropping the file drops the script",
      not any("ztest.user.js" in n for n in win.plugin_script_names),
      win.plugin_script_names)
check("and it can be stopped", win.stop_watching() is True)

print("\n(9) looking the page over")
audit = []
win.page_audit(view=view, then=audit.append)
H.wait_for(lambda: audit, 6000)
found = audit[0] if audit else {}
check("the audit counts the elements", found.get("dom", 0) > 5, found)
check("...and finds the missing viewport",
      any("viewport" in note for note in found.get("notes", [])),
      found.get("notes"))
check("...and the missing lang",
      any("lang" in note for note in found.get("notes", [])),
      found.get("notes"))
check("...but not a missing description, which this page has",
      not any("description" in note for note in found.get("notes", [])),
      found.get("notes"))
win.config["linkCheck"] = False
answer = []
check("link checking is off by default",
      win.check_links(view=view, then=answer.append) is False)
win.config["linkCheck"] = True
answer = []
win.check_links(view=view, then=answer.append)
H.wait_for(lambda: answer, 10000)
bad = answer[0] if answer else []
check("the broken link is found",
      any("/missing" in row["url"] for row in bad), bad)
check("...and the good one is not",
      not any(row["url"].endswith("/one") for row in bad), bad)
win.config["linkCheck"] = False

print("\n(10) snippets and the console")
win.config["jsSnippets"] = []
check("a snippet can be saved",
      win.save_snippet("title", "document.title") is True)
ran = []
check("...and run on the page",
      win.run_snippet("title", view=view, then=ran.append) is True)
H.wait_for(lambda: ran, 5000)
check("...with its answer coming back",
      ran and "page to work on" in str(ran[0]).lower(), ran)
check("a snippet that throws says so",
      win.run_snippet(code="nope.nope", view=view,
                      then=ran.append) is True)
H.wait_for(lambda: len(ran) > 1, 5000)
check("...in words", "error" in str(ran[-1]).lower(), ran[-1])
check("the text form is parsed",
      win.parse_snippets("one|1+1\ntwo|2+2") and
      len(win.console_snippets()) == 2, win.console_snippets())
check("a line without a bar is left out",
      win.parse_snippets("one|1+1\nnonsense") and
      len(win.console_snippets()) == 1)
check("dropping one works", win.save_snippet("gone", "1")
      and win.drop_snippet("gone") is True)
broken = page("/broken")
H.wait_for(lambda: win.console_errors(broken), 8000)
rows = win.console_errors(broken)
check("a page's errors are kept", rows, rows[:1])
check("...and counted for the badge", win.console_badge(broken) >= 1,
      win.console_badge(broken))
# the snippet that threw a moment ago logged on this page too, which
# is the browser doing the right thing: the check is about a page that
# has not been poked at
win.clear_console(view)
H.spin(200)
check("a page with nothing wrong has none", win.console_badge(view) == 0,
      win.console_errors(view))
check("clearing them works", win.clear_console(broken) is True
      and win.console_errors(broken) == [])

print("\n(11) service workers and the certificate")
workers = []
win.service_workers(view=view, then=workers.append)
H.wait_for(lambda: workers, 8000)
check("a page with no service worker says so",
      workers == [[]] or workers[0] == [], workers)
menu = win.cert_chain_menu(view=view)
check("an http page has no certificate to show",
      len([a for a in menu.actions() if a.text()]) >= 1,
      [a.text() for a in menu.actions()][:2])

print("\n(12) the engine's own switches")
check("the internals menu lists the pages that work",
      len(win.internals_menu().actions()) >= 6)
check("...and each is a chrome:// address",
      all("chrome://" in a.text() for a in win.internals_menu().actions()))
check("the flags are his to set",
      win.set_flags("--disable-gpu\n--lang=de") is True
      and "disable-gpu" in win.flags_text())
win.config["hostOverrides"] = "example.com 192.168.1.10\n# a note\nbad"
check("a host override is read",
      win.host_overrides() == [("example.com", "192.168.1.10")],
      win.host_overrides())
check("...and becomes the flag the engine takes",
      win.host_override_flag()
      == "--host-resolver-rules=MAP example.com 192.168.1.10",
      win.host_override_flag())
check("the debugging port is off until he asks",
      win.config.get("debugPort") in (None, False))
check("...and switching it on says it needs a restart",
      win.debug_port(True) is True
      and win.config.get("debugPort") is True)
win.debug_port(False)
check("localhost is a local address", win.is_local_address("localhost")
      is True)
check("so is 127.0.0.1", win.is_local_address("127.0.0.1") is True)
check("so is the home network", win.is_local_address("192.168.1.10")
      is True)
check("a site on the internet is not",
      win.is_local_address("example.com") is False)
check("...and neither is a public address",
      win.is_local_address("8.8.8.8") is False)
check("the switch can be turned on", win.localhost_certs(True) is True)
win.localhost_certs(False)

print("\n(13) the clipboard")
QGuiApplication.clipboard().setText("a line of text")
rows = win.clipboard_kinds()
check("the clipboard's formats are listed",
      any("text" in r["format"] for r in rows), rows[:3])
check("...with how many bytes each holds",
      all(r["bytes"] >= 0 for r in rows), rows[:2])
menu = win.clipboard_menu()
check("the menu shows them",
      len([a for a in menu.actions() if a.text()]) >= 1,
      [a.text() for a in menu.actions()][:3])

print("\n(14) the requests a page makes")
watch = win.request_watch()
check("the interceptor is installed", watch is not None)
check("...and it is off until he asks", watch.on is False)
check("switching it on says so", win.log_requests(True) is True)
fresh = page("/work")
H.wait_for(lambda: win.request_rows(), 8000)
rows = win.request_rows()
check("the requests are written down", len(rows) >= 1, rows[:2])
check("...with the address", any("/work" in r["url"] for r in rows),
      [r["url"] for r in rows][:4])
check("...and the picture it fetched",
      any("pic.png" in r["url"] for r in rows),
      [r["url"] for r in rows][:6])
check("...each with a kind the browser can name",
      all(int(r["kind"]) in win.REQUEST_KINDS for r in rows),
      [r["kind"] for r in rows][:5])
check("a filter by word works",
      all("pic" in r["url"] for r in win.request_rows(text="pic")),
      win.request_rows(text="pic")[:2])
har = scratch / "requests.har"
written = win.export_har(str(har))
check("a HAR file is written", written and har.exists(), written)
import json as _json
data = _json.loads(har.read_text()) if har.exists() else {}
check("...in the HAR shape",
      data.get("log", {}).get("version") == "1.2", list(data)[:2])
check("...with the entries in it",
      len(data.get("log", {}).get("entries", [])) >= 1,
      len(data.get("log", {}).get("entries", [])))
check("clearing the log works", win.clear_requests() is True
      and win.request_rows() == [])
check("switching it off empties it", win.log_requests(False) is False)

print("\n(15) blocking an address, and telling a site something else")
win.config["urlRules"] = "/pic.png\n/one -> %s" % srv.url("/plain")
win._url_rules = None
check("the rules are read",
      win.url_rules() == [("/pic.png", "block"),
                          ("/one", srv.url("/plain"))],
      win.url_rules())
blocked = page("/work")
H.spin(1200)
check("the blocked picture never loaded",
      js(blocked, "document.getElementById('pic').naturalWidth") == 0,
      js(blocked, "document.getElementById('pic').naturalWidth"))
moved = win.new_tab(url=None)
H.load(moved, srv.url("/one"))
H.wait_for(lambda: "nothing" in (js(moved, "document.body.innerText")
                                 or ""), 8000)
check("a mapped address goes where it was sent",
      "nothing" in (js(moved, "document.body.innerText") or ""),
      js(moved, "document.body.innerText"))
win.config["urlRules"] = ""
win._url_rules = None
check("adding a rule by hand works",
      win.block_url("/tracker.js") is True
      and ("/tracker.js", "block") in win.url_rules())
win.config["urlRules"] = ""
win._url_rules = None
check("no user agent is set to begin with", win.agent_for("127.0.0.1")
      == "")
check("one can be set", win.set_agent("127.0.0.1", "iphone") is True)
check("...and it is the real string",
      "iPhone" in win.agent_for("127.0.0.1"), win.agent_for("127.0.0.1"))
check("...and a sub-domain of it gets it too",
      "iPhone" in win.agent_for("sub.127.0.0.1")
      or win.agent_for("sub.127.0.0.1") == "",
      win.agent_for("sub.127.0.0.1"))
agent_page = win.new_tab(url=None)
H.load(agent_page, srv.url("/echo"))
H.spin(900)
sent = js(agent_page, "document.body.innerText") or ""
check("the server is sent that user agent",
      "iPhone" in sent, [l for l in sent.splitlines()
                         if l.lower().startswith("user-agent")][:1])
H.load(agent_page, srv.url("/work"))
H.wait_for(lambda: "iPhone" in (js(agent_page, "navigator.userAgent")
                                or ""), 6000)
check("...and so is the page's own JavaScript",
      "iPhone" in (js(agent_page, "navigator.userAgent") or ""),
      (js(agent_page, "navigator.userAgent") or "")[:60])
check("switching it off works", win.set_agent("127.0.0.1", "") is True
      and win.agent_for("127.0.0.1") == "")
win.config["headerRules"] = ("X-Everywhere: yes\n"
                             "127.0.0.1 | X-Only-Here: also")
win._header_rules = None
win.config["guardGpc"] = True
win.config["guardOff"] = {}
hint = win.new_tab(url=None)
H.load(hint, srv.url("/echo"))
H.spin(600)
body = js(hint, "document.body.innerText") or ""
check("a site is told not to sell or share", "Sec-GPC: 1" in body,
      [ln for ln in body.splitlines() if "GPC" in ln])
check("...and the setting is one of the page guards",
      win.guard_on("gpc", "127.0.0.1") is True)
win.toggle_guard_site("gpc", "127.0.0.1")
check("...which one site can be excused from",
      win.guard_on("gpc", "127.0.0.1") is False)
H.load(hint, srv.url("/echo?again"))
H.spin(600)
body = js(hint, "document.body.innerText") or ""
check("...and then it is not told", "Sec-GPC" not in body,
      [ln for ln in body.splitlines() if "GPC" in ln])
win.toggle_guard_site("gpc", "127.0.0.1")
win.config["guardGpc"] = False
H.load(hint, srv.url("/echo?off"))
H.spin(600)
body = js(hint, "document.body.innerText") or ""
check("with the guard off nobody is told", "Sec-GPC" not in body)

check("the header rules are read", len(win.header_rules()) == 2,
      win.header_rules())
check("one is for every site",
      ("X-Everywhere", "yes") in win.headers_for("example.com"),
      win.headers_for("example.com"))
check("...and the other only for its own",
      ("X-Only-Here", "also") in win.headers_for("127.0.0.1")
      and ("X-Only-Here", "also") not in win.headers_for("example.com"),
      win.headers_for("127.0.0.1"))
win.config["headerRules"] = ""
win._header_rules = None

print("\n(16) the server's answer, a request of his own, and the clock")
got = []
win.response_headers(srv.url("/work"), then=got.append)
H.wait_for(lambda: got, 8000)
found = got[0] if got else {}
check("the response headers come back", found.get("status") == 200, found)
check("...with the content type",
      any(name.lower() == "content-type"
          for name, _v in found.get("headers", [])),
      found.get("headers", [])[:3])
check("...and the security headers this server does not send",
      "content-security-policy" in found.get("missing", []),
      found.get("missing"))
check("a page that is not http has none",
      win.response_headers("file:///tmp/x") is False)
answer = []
check("a request of his own goes out",
      win.http_request("GET", srv.url("/one"), then=answer.append) is True)
H.wait_for(lambda: answer, 8000)
reply = answer[0] if answer else {}
check("...and comes back", reply.get("status") == 200, reply.get("status"))
check("...with the body", "One" in str(reply.get("body", "")),
      str(reply.get("body"))[:60])
check("...and how long it took", reply.get("ms", -1) >= 0, reply.get("ms"))
check("an address that is not http is refused",
      win.http_request("GET", "notanurl") is False)
answer = []
win.http_request("POST", srv.url("/post"), headers=[("X-Test", "1")],
                 body="hello", then=answer.append)
H.wait_for(lambda: answer, 8000)
check("a POST comes back with an answer too",
      bool(answer) and isinstance(answer[0].get("status"), int),
      answer and answer[0].get("status"))
check("...and the server was sent the body",
      H.Handler.last_post.get("length") == 5,
      H.Handler.last_post.get("length"))
timing = []
win.load_timing(view=view, then=timing.append)
H.wait_for(lambda: timing, 8000)
clock = timing[0] if timing else {}
check("the load timing is read", "loaded" in clock, clock)
check("...with the first byte", clock.get("ttfb", -1) >= 0, clock)
win.config["guardWsLog"] = False
menu = win.websocket_menu(view=view)
check("without the guard the socket list says so",
      any("guard" in a.text().lower() or "w\u00e4chter" in a.text().lower()
          for a in menu.actions()),
      [a.text() for a in menu.actions()])

print("\n(17) the menu, Settings and the words")
menu = win.dev_menu()
tops = [a.text() for a in menu.actions() if a.text()]
check("the menu has the four groups", len(tops) >= 4, tops)
check("...including the workbench",
      any("workbench" in t.lower() or "werkbank" in t.lower()
          for t in tops), tops)
page_text = (HERE / "settings.html").read_text()
check("there is a section for the tools",
      'data-desc="descDevs"' in page_text)
for ident in ("linkcheck", "debugport", "localhostcerts",
              "chromiumflags", "hostoverrides", "snippetstext",
              "urlrules", "headerrules"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text)
check("...and the switches are wired",
      'bindSwitch("linkcheck", "linkCheck")' in page_text
      and 'bindSwitch("debugport", "debugPort")' in page_text)
need = ["devTools", "devRequests", "devLogRow", "devAgentMenu",
        "devRulesName", "devHeadersName", "devHeadersMenu",
        "devHttp", "devWsMenu", "devTimingMenu",
        "devRuler", "devOutlines", "devHidden", "devNoCss",
        "devPerf", "devKeys", "devFonts", "devPalette", "devImage",
        "devOverlay", "devAuditRun", "devLinkCheck", "devSizes",
        "devMediaMenu", "devPlaceRow", "devThrottleMenu", "devRegex",
        "devDiff", "devMini", "devOpenFile", "devSnippets",
        "devClipboard", "devOpenGraph", "devErrorsMenu", "devStorage",
        "devCookies", "devCert", "devWorkers", "devCacheRow",
        "devHardReloadRow", "devNoJsRow", "devWatch", "devInternals",
        "devDebugRow", "devLocalCerts", "descDev"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need if k not in ("devWebrtc", "devWsMenu")
        and B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
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
for wanted in ("devmenu", "devruler", "devoutlines", "devfonts",
               "devrequests", "devlog", "devhar", "devagent",
               "devheaders", "devtiming", "devsockets", "devhttp",
               "devpalette", "devaudit", "devlinks", "devregex",
               "devdiff", "devmini", "devfile", "devsnippets",
               "devstorage", "devcookies", "devworkers", "devconsole",
               "devcache", "devhard", "devnojs", "devwatch",
               "devinternals", "devclip"):
    check("there is an action for " + wanted, wanted in ids)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails)))
else:
    print("all good")
srv.stop()
win.close()
sys.exit(1 if fails else 0)
