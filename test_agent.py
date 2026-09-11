#!/usr/bin/env python3
"""The agent bridge: a script drives tabs through the local socket.

Offscreen, scratch data, its own socket name (so the browser you are
running is never touched): the bridge listens, a plain-socket client
opens a background tab on a local page, reads it, waits, clicks, types
into a React-style input and a contenteditable, presses Enter, takes a
screenshot, closes the tab -- and the visible tab never changes."""
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
agent_bridge.SOCKET_NAME = "browser-agent-test-%d" % os.getpid()
from PyQt6.QtCore import QTimer  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<!doctype html><title>Bridge page</title>
<h1 id=h>hello bridge</h1>
<button id=b onclick="document.getElementById('h').textContent='clicked'">go</button>
<input id=i oninput="document.getElementById('h').textContent='in:'+this.value">
<div id=e contenteditable=true></div>
<div id=k></div>
<script>
document.getElementById('e').addEventListener('input', function(){
  document.getElementById('k').textContent = 'ed:' + this.textContent; });
document.getElementById('i').addEventListener('keydown', function(ev){
  if (ev.key === 'Enter') document.getElementById('k').textContent = 'enter';
});
setTimeout(function(){ var l = document.createElement('p'); l.id = 'late';
  l.textContent = 'late'; document.body.appendChild(l); }, 1200);
</script>"""

app = H.app()
srv = H.Server({"/page": PAGE, "/other": "<title>Other</title><p>other</p>"})
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(500)
bridge = agent_bridge.install(win)
check("bridge listens", bridge is not None)
path = agent_bridge.socket_path()
check("socket file exists", os.path.exists(path), path)

# the client runs in a thread so the Qt loop keeps spinning underneath
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
                c = s.recv(65536)
                if not c:
                    break
                buf += c
            s.close()
            answers[name] = json.loads(buf.split(b"\n")[0].decode())
        except Exception as e:
            answers[name] = {"ok": False, "error": "client: %s" % e}
    t = threading.Thread(target=run, daemon=True)
    t.start()
    H.wait_for(lambda: name in answers, timeout=timeout * 1000)
    return answers.get(name, {"ok": False, "error": "no reply"})


r = client("ping", {"op": "ping"})
check("ping answers with our pid", r.get("pid") == os.getpid(), r)

r = client("bad", {"op": "nope"})
check("unknown op is an error, not a hang", r.get("ok") is False, r)

visible_before = win.current()
r = client("open", {"op": "open", "url": srv.url("/page")})
check("open returns a tab", r.get("ok") and "tab" in r, r)
tid = r["tab"]["id"]
check("visible tab unchanged by a background open", win.current() is visible_before)

r = client("wait", {"op": "wait", "tab": tid, "selector": "#h", "timeout": 10000})
check("wait finds the heading once loaded", r.get("ok") and r.get("found"), r)

r = client("tabs", {"op": "tabs"})
mine = [t for t in r.get("tabs", []) if t["id"] == tid]
check("tabs lists the new tab with its url", mine and "/page" in mine[0]["url"], r)
check("tabs marks it not current", mine and not mine[0]["current"])

r = client("text", {"op": "text", "tab": tid})
check("text reads the page", "hello bridge" in (r.get("text") or ""), r)
r = client("textsel", {"op": "text", "tab": tid, "selector": "#h"})
check("text with selector", (r.get("text") or "").strip() == "hello bridge", r)
r = client("textmiss", {"op": "text", "tab": tid, "selector": "#none"})
check("text on a missing node is an error", r.get("ok") is False, r)

r = client("html", {"op": "html", "tab": tid, "selector": "#b"})
check("html of a node", (r.get("html") or "").startswith("<button"), r)

r = client("js", {"op": "js", "tab": tid, "code": "1 + 2"})
check("js returns a value", r.get("result") == 3, r)
r = client("jsmain", {"op": "js", "tab": tid, "code": "document.title", "world": "main"})
check("js in the main world", r.get("result") == "Bridge page", r)

r = client("late", {"op": "wait", "tab": tid, "selector": "#late", "timeout": 10000})
check("wait polls until a late node appears", r.get("ok") and r.get("waited", 0) > 0, r)

r = client("click", {"op": "click", "tab": tid, "selector": "#b"})
check("click reports clicked", r.get("result") == "clicked", r)
r = client("afterclick", {"op": "text", "tab": tid, "selector": "#h"})
check("click ran the handler", (r.get("text") or "").strip() == "clicked", r)

r = client("type", {"op": "type", "tab": tid, "selector": "#i", "text": "abc"})
check("type into an input", r.get("result") == "typed", r)
r = client("aftertype", {"op": "text", "tab": tid, "selector": "#h"})
check("input event fired with the value", (r.get("text") or "").strip() == "in:abc", r)
r = client("typeclear", {"op": "type", "tab": tid, "selector": "#i", "text": "z", "clear": True})
r = client("aftertype2", {"op": "text", "tab": tid, "selector": "#h"})
check("clear replaces instead of appending", (r.get("text") or "").strip() == "in:z", r)

r = client("edit", {"op": "type", "tab": tid, "selector": "#e", "text": "hi there"})
check("type into contenteditable", r.get("result") == "typed", r)
r = client("afteredit", {"op": "text", "tab": tid, "selector": "#k"})
check("contenteditable input event carries the text",
      (r.get("text") or "").strip() == "ed:hi there", r)

# Enter on a hidden tab: needs the tab's own focus, so select it first
r = client("select", {"op": "select", "tab": tid})
H.spin(300)
check("select makes it current", win.current() is bridge._find(tid))
r = client("focus", {"op": "js", "tab": tid, "code": "document.getElementById('i').focus(); 'ok'"})
r = client("enter", {"op": "type", "tab": tid, "selector": "#i", "text": "", "enter": True})
H.spin(500)
r = client("afterenter", {"op": "text", "tab": tid, "selector": "#k"})
check("enter reaches the page as a real key", (r.get("text") or "").strip() == "enter", r)

shot = os.path.join(H.DATA, "shot.png")
r = client("shot", {"op": "shot", "tab": tid, "path": shot})
check("shot writes a png", r.get("ok") and os.path.getsize(shot) > 1000, r)

r = client("nav", {"op": "nav", "tab": tid, "url": srv.url("/other")})
r = client("navwait", {"op": "wait", "tab": tid, "selector": "p", "timeout": 10000})
r = client("navtext", {"op": "text", "tab": tid})
check("nav loads another page in the same tab", "other" in (r.get("text") or ""), r)

r = client("scroll", {"op": "scroll", "tab": tid, "y": "bottom"})
check("scroll answers", r.get("ok"), r)

n = win.tabs.count()
r = client("close", {"op": "close", "tab": tid})
H.spin(300)
check("close removes the tab", r.get("ok") and win.tabs.count() == n - 1, r)
r = client("gone", {"op": "text", "tab": tid})
check("closed tab is no-such-tab", r.get("error") == "no-such-tab", r)

r = client("off", {"op": "js", "tab": 999999, "code": "1"})
check("unknown tab id is no-such-tab", r.get("error") == "no-such-tab", r)

bridge.close()
check("socket removed on close", not os.path.exists(path))
srv.stop()
print("\n%d checks failed" % len(fails) if fails else "\nall checks passed")
QTimer.singleShot(0, app.quit)
app.exec()
sys.stdout.flush()
os._exit(1 if fails else 0)
