#!/usr/bin/env python3
"""The small developer tools: the JSON tree, the formatter, the CSV
table, copy buttons on code blocks, what an element is called, the
colour under the cursor, curl, the source view, and the conversions the
address bar answers."""
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
from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


print("\n(1) the conversions")
for text, want in [
        ("b64 hello", "aGVsbG8="),
        ("b64d aGVsbG8=", "hello"),
        ("url Hallo Welt", "Hallo%20Welt"),
        ("urld Hallo%20Welt", "Hallo Welt"),
        ("hex AB", "4142"),
        ("html <b>&", "&lt;b&gt;&amp;"),
]:
    got = B.bar_answer(text)
    check("%s -> %s" % (text, want), got and got[1] == want, got)
got = B.bar_answer("ts 1700000000")
check("a unix timestamp becomes a date",
      got and got[1].startswith("2023-11-"), got)
got = B.bar_answer("ts 1700000000000")
check("milliseconds work too", got and got[1].startswith("2023-11-"), got)
got = B.bar_answer(
    "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0aW0iLCJhZG1pbiI6dHJ1ZX0.sig")
check("a JWT is opened up",
      got and '"sub"' in got[1] and "HS256" in got[1], got)
check("ordinary text is not mistaken for one",
      B.bar_answer("b64") is None and B.bar_answer("hello world") is None
      and B.bar_answer("added") is None,
      (B.bar_answer("b64"), B.bar_answer("added")))

JSON_PAGE = ('<!doctype html><title>api</title><pre>'
             '{"name":"sodium","versions":[1,2,3],'
             '"meta":{"author":"jellysquid","downloads":4200000}}</pre>')
CSV_PAGE = ('<!doctype html><title>data</title><pre>name,count,note\n'
            'alpha,3,"a, quoted one"\nbeta,4,plain\ngamma,5,last</pre>')
MIN_PAGE = ('<!doctype html><title>min</title><pre>'
            '.a{color:red}.b{color:blue;background:url("x;y")}</pre>')
CODE_PAGE = ('<!doctype html><title>code</title>'
             '<pre id=c1><code>print("one")</code></pre>'
             '<pre id=c2><code>print("two")</code></pre>')
ELEM_PAGE = ('<!doctype html><title>elem</title>'
             '<style>body{margin:0}#box{width:200px;height:100px;'
             'background:#20c020}</style>'
             '<div class="wrap"><div id=box class="a b">text in the box</div>'
             '</div>')

app = H.app()
srv = H.Server({"/json": JSON_PAGE, "/csv": CSV_PAGE, "/min": MIN_PAGE,
                "/code": CODE_PAGE, "/elem": ELEM_PAGE})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)


def tool(name, **args):
    box = {}
    win.dev_tool(name, view=view, then=lambda r: box.setdefault("v", r),
                 **args)
    H.wait_for(lambda: "v" in box, 4000)
    H.spin(150)
    return box.get("v")


def js(code):
    return H.js(view, code, B.MAIN_WORLD_ID)


print("\n(2) JSON as a tree")
H.load(view, srv.url("/json"))
check("the tree is built", tool("json") == "on")
check("it is in the page", js("!!document.getElementById('__jsonview')"))
check("the top level is there",
      "sodium" in (js("document.getElementById('__jsonview').textContent")
                   or ""),
      (js("document.getElementById('__jsonview').textContent") or "")[:60])
check("the raw text is out of the way",
      js("document.querySelector('body > pre').style.display") == "none")
check("and it folds away again", tool("json") == "off")
check("...putting the raw text back",
      js("document.querySelector('body > pre').style.display") == "")
H.load(view, srv.url("/csv"))
check("a page that is not JSON says so", tool("json") == "not json")

print("\n(3) a CSV file as a table")
got = tool("csv")
check("the table was built", got == "4x3", got)
check("it is in the page", js("!!document.getElementById('__csvtable')"))
check("the header row is a header row",
      js("document.querySelectorAll('#__csvtable th').length") == 3,
      js("document.querySelectorAll('#__csvtable th').length"))
check("a quoted comma stayed in its own cell",
      js("document.querySelectorAll('#__csvtable tr')[1]"
         ".children[2].textContent") == "a, quoted one",
      js("document.querySelectorAll('#__csvtable tr')[1].children[2].textContent"))
check("and it can be taken away again", tool("csv") == "off")

print("\n(4) formatting a minified file")
H.load(view, srv.url("/min"))
check("it formats", tool("pretty") == "on")
text = js("document.querySelector('body > pre').textContent")
check("there are line breaks now", text.count("\n") >= 3, repr(text[:80]))
check("a brace in a string was left alone", 'url("x;y")' in text, text)
check("and it can be put back", tool("pretty") == "off")
check("exactly as it was",
      js("document.querySelector('body > pre').textContent")
      == '.a{color:red}.b{color:blue;background:url("x;y")}')

print("\n(5) copy buttons on code blocks")
H.load(view, srv.url("/code"))
check("two blocks got a button", tool("codecopy") == 2, tool("codecopy"))
check("they are in the page",
      js("document.querySelectorAll('.__copybtn').length") == 2)
check("and it does not add them twice", tool("codecopy") == "already")

print("\n(6) what this element is called")
H.load(view, srv.url("/elem"))
H.spin(300)
raw = tool("selector", x=100, y=50)
got = json.loads(raw)
check("the CSS selector names it", got["css"] == "#box", got["css"])
check("the XPath walks down to it",
      got["xpath"].endswith("div[1]/div[1]"), got["xpath"])
check("the HTML is the element's own",
      got["html"].startswith('<div id="box"'), got["html"][:40])
win.copy_selector(QPoint(100, 50), "css", view=view)
H.spin(500)
check("and it goes on the clipboard",
      QGuiApplication.clipboard().text() == "#box",
      QGuiApplication.clipboard().text())

print("\n(7) the colour under the cursor")
colour = win.pick_colour(QPoint(100, 50), view=view)
check("it reads the pixel", colour == "#20c020", colour)
check("and copies it", QGuiApplication.clipboard().text() == "#20c020")

print("\n(8) curl")
text = win.copy_as_curl(view=view)
check("it starts with curl", text.startswith("curl '"), text[:40])
check("it carries the address", "/elem" in text, text[:80])
check("and a user agent", "User-Agent:" in text)

print("\n(9) the page source")
before = len([1 for _, v in win._real_tabs()])
win.view_source(view=view)
H.wait_for(lambda: len([1 for _, v in win._real_tabs()]) > before, 4000)
H.spin(800)
source_tab = win.current()
body = H.js(source_tab, "document.body.textContent", B.MAIN_WORLD_ID) or ""
check("a tab opened with the source in it", "text in the box" in body,
      body[:60])
check("with line numbers",
      (H.js(source_tab, "document.querySelectorAll('td.n').length",
            B.MAIN_WORLD_ID) or 0) >= 3,
      H.js(source_tab, "document.querySelectorAll('td.n').length",
           B.MAIN_WORLD_ID))

print("\n(10) servers on this machine")
ports = win.local_servers(ports=(srv.port, 1))
check("the one that is listening is found", srv.port in ports, ports)
check("and the one that is not, is not", 1 not in ports, ports)
menu = win.local_server_menu()
check("the menu is built", menu is not None and len(menu.actions()) >= 1)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
