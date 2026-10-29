#!/usr/bin/env python3
"""The newer agent-bridge ops: the page as Markdown, where an element
is, finding by words, filling a form, waiting for the fetching to stop,
the console, dialogs, PDF, links, tables, cookies, bookmarks, downloads
and the notice in the corner.

Same shape as test_agent.py — a real socket, a real client in a thread,
a real browser underneath, and its own socket name so the browser the owner is
actually using is never touched."""
import json
import os
import socket
import sys
import threading
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
import agent_bridge  # noqa: E402
agent_bridge.SOCKET_NAME = "browser-agentops-test-%d" % os.getpid()

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


ARTICLE = """<!doctype html><title>Article</title>
<nav>menu that does not belong in the text</nav>
<h1>Sodium</h1>
<p>A rendering engine <a href="https://modrinth.com/mod/sodium">on Modrinth</a>.</p>
<ul><li>fast</li><li>free</li></ul>
<table id=t><tr><th>name</th><th>count</th></tr>
<tr><td>alpha</td><td>3</td></tr><tr><td>beta</td><td>4</td></tr></table>
<form><input id=user><input id=pass type=password>
<select id=pick><option value=a>a</option><option value=b>b</option></select>
<input id=agree type=checkbox></form>
<button id=save>Save changes</button>
<p id=later></p>
<script>
console.log("hello from the page");
setTimeout(function () { throw new Error("boom"); }, 50);
setTimeout(function () {
  fetch(location.pathname + "?x=1").catch(function () {});
}, 150);
window.__ask = function () { return confirm("really?"); };
</script>"""

app = H.app()
srv = H.Server({"/a": ARTICLE, "/b": "<title>B</title><p>b</p>"})
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(500)
bridge = agent_bridge.install(win)
path = agent_bridge.socket_path()
check("the bridge is listening", bridge is not None and os.path.exists(path))

answers = {}


def client(name, req, timeout=30):
    def run():
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(path)
            s.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            s.close()
            answers[name] = json.loads(buf.split(b"\n")[0].decode())
        except Exception as exc:
            answers[name] = {"ok": False, "error": "client: %s" % exc}
    t = threading.Thread(target=run, daemon=True)
    t.start()
    H.wait_for(lambda: name in answers, timeout=timeout * 1000)
    return answers.get(name, {"ok": False, "error": "no reply"})


r = client("open", {"op": "open", "url": srv.url("/a")})
tid = r["tab"]["id"]
client("wait", {"op": "wait", "tab": tid, "selector": "#save",
                "timeout": 10000})

print("\n(1) the page as Markdown")
r = client("md", {"op": "markdown", "tab": tid})
text = r.get("text") or ""
check("it comes back", r.get("ok"), r)
check("the heading is a heading", "# Sodium" in text, text[:80])
check("a link keeps its address",
      "[on Modrinth](https://modrinth.com/mod/sodium)" in text, text[:200])
check("the list is a list", "- fast" in text, text)
check("the menu is left out", "menu that does not belong" not in text, text)
r = client("mdsel", {"op": "markdown", "tab": tid, "selector": "#t"})
check("a selector narrows it to that part",
      "alpha" in (r.get("text") or "") and "Sodium" not in (r.get("text") or ""),
      (r.get("text") or "")[:60])

print("\n(2) where an element is")
r = client("box", {"op": "box", "tab": tid, "selector": "#save"})
box = r.get("box") or {}
check("it answers", r.get("ok"), r)
check("with a real size", box.get("width", 0) > 10 and box.get("height", 0) > 5,
      box)
check("and says it can be seen", box.get("visible") is True, box)
check("and what it says", "Save changes" in (box.get("text") or ""), box)
r = client("boxmiss", {"op": "box", "tab": tid, "selector": "#nope"})
check("an element that is not there is not an error with a box",
      r.get("ok") is False or r.get("box") is None, r)

print("\n(3) finding by the words on it")
r = client("find", {"op": "find", "tab": tid, "text": "save changes"})
found = r.get("found") or []
check("the button is found", any(f["tag"] == "button" for f in found), found)
check("with a selector that works",
      any(f["selector"] for f in found), found)
sel = [f["selector"] for f in found if f["tag"] == "button"][0]
r = client("clickfound", {"op": "click", "tab": tid, "selector": sel})
check("and the selector can be clicked", r.get("ok"), r)

print("\n(4) filling a form")
r = client("fill", {"op": "fill", "tab": tid, "fields": {
    "#user": "ada", "#pass": "secret", "#pick": "b", "#agree": True,
    "#missing": "x"}})
result = r.get("result") or {}
check("four fields were filled", len(result.get("filled", [])) == 4, result)
check("and the one that is not there is named",
      result.get("missing") == ["#missing"], result)
r = client("checkfill", {"op": "js", "tab": tid,
                         "code": "JSON.stringify([document.getElementById('user').value,"
                                 "document.getElementById('pick').value,"
                                 "document.getElementById('agree').checked])"})
check("the page really has them",
      json.loads(r.get("result") or "[]") == ["ada", "b", True], r)

print("\n(5) waiting for the fetching to stop")
r = client("idle", {"op": "idle", "tab": tid, "quiet": 300, "timeout": 5000})
idle = r.get("idle") or {}
check("it waits and says so", r.get("ok") and idle.get("idle") is True, r)
check("and says how long it waited", idle.get("waited", 0) >= 300, idle)

print("\n(6) links and tables")
r = client("links", {"op": "links", "tab": tid})
links = r.get("links") or []
check("the link is listed",
      any(l["url"].startswith("https://modrinth.com") for l in links), links)
r = client("linkspat", {"op": "links", "tab": tid, "pattern": "modrinth"})
check("a pattern narrows it", len(r.get("links") or []) == 1, r.get("links"))
r = client("tables", {"op": "tables", "tab": tid})
tables = r.get("tables") or []
check("the table comes back as rows",
      tables and tables[0][0] == ["name", "count"], tables)
check("with its data", tables and tables[0][1] == ["alpha", "3"], tables)

print("\n(7) the console")
r = client("console", {"op": "console", "tab": tid})
msgs = r.get("messages") or []
check("what the page logged is there",
      any("hello from the page" in m["text"] for m in msgs), msgs[:3])
check("and what it threw",
      any("boom" in m["text"] for m in msgs), msgs[:5])
r = client("consoleclear", {"op": "console", "tab": tid, "clear": True})
r = client("console2", {"op": "console", "tab": tid})
check("clearing empties it", not r.get("messages"), r)

print("\n(8) dialogs")
r = client("dialogset", {"op": "dialog", "tab": tid, "answer": True})
check("an answer can be set", r.get("answer") is True, r)
r = client("confirm", {"op": "js", "tab": tid, "code": "window.__ask()",
                       "world": "main"})
check("confirm() comes back with it rather than hanging",
      r.get("result") is True, r)
r = client("dialoglog", {"op": "dialog", "tab": tid})
check("and the question is logged",
      any("really?" in d["text"] for d in (r.get("last") or [])), r)

print("\n(9) a PDF of the page")
out = Path(B.CONFIG_FILE).parent / "page.pdf"
r = client("pdf", {"op": "pdf", "tab": tid, "path": str(out)}, timeout=40)
check("the file was written", r.get("ok") and out.exists(), r)
check("and it is a PDF", out.exists() and out.read_bytes()[:4] == b"%PDF",
      out.read_bytes()[:8] if out.exists() else None)

print("\n(10) cookies, by name only")
H.js(win.current(), "document.cookie='probe=1'", B.MAIN_WORLD_ID)
H.spin(400)
r = client("cookies", {"op": "cookies"})
cookies = r.get("cookies") or []
check("the list comes back", r.get("ok"), r)
check("no value is ever in it",
      all("value" not in c for c in cookies), cookies[:3])

print("\n(11) bookmarks, downloads and a word in the corner")
r = client("bmadd", {"op": "bookmarks", "action": "add",
                     "url": "https://modrinth.com/mods", "title": "Mods"})
check("a bookmark can be added", r.get("ok"), r)
r = client("bmsearch", {"op": "bookmarks", "text": "mods"})
check("and found again",
      any(b["url"] == "https://modrinth.com/mods"
          for b in (r.get("bookmarks") or [])), r)
r = client("dl", {"op": "downloads"})
check("the downloads list answers", r.get("ok"), r)
r = client("notify", {"op": "notify", "text": "Claude is done"})
check("a notice can be shown", r.get("ok"), r)
check("and it is on the window",
      getattr(win, "_flash", None) is not None
      and win._flash.text() == "Claude is done",
      getattr(win, "_flash", None) and win._flash.text())

print("\n(12) the ops that need something are honest about it")
for req in ({"op": "find", "tab": tid}, {"op": "fill", "tab": tid},
            {"op": "pdf", "tab": tid}, {"op": "notify"}):
    r = client("bad-" + req["op"] + str(len(answers)), req)
    check("%s without its argument is an error" % req["op"],
          r.get("ok") is False, r)

client("close", {"op": "close", "tab": tid})

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
