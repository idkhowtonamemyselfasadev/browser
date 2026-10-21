#!/usr/bin/env python3
"""The agent bridge, part two: the page as numbered refs, what a tab
fetched, a file through the session, the event stream, watches, macros,
auto-click rules, the tabs the agent owns, the audit log, permission
levels, and the ops added for all of it.

Offscreen, scratch data, its own socket name — the browser you are
running is never touched. The client runs in a thread so the Qt loop
keeps spinning underneath, exactly as test_agent.py does.
"""
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
import agent_bridge  # noqa: E402
agent_bridge.SOCKET_NAME = "browser-agent-test2-%d" % os.getpid()
import agent as client  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = """<!doctype html><title>Agent page</title>
<h1 id=h>a page for an agent</h1>
<a id=link href="/other">the other page</a>
<button id=b onclick="document.getElementById('h').textContent='clicked'">go</button>
<input id=i name=who><textarea id=t></textarea>
<input id=file type=file>
<div id=shadowhost></div>
<iframe id=frame src="/inner"></iframe>
<img src="/pic.png" alt="a picture">
<div id=counter>0</div>
<script>
  var host = document.getElementById('shadowhost');
  var root = host.attachShadow({mode: 'open'});
  root.innerHTML = '<button id=deep>deep button</button>'
    + '<span id=deeptext>in the shadow</span>';
  root.getElementById('deep').addEventListener('click', function () {
    document.getElementById('h').textContent = 'deep clicked';
  });
  window.__bump = function () {
    var el = document.getElementById('counter');
    el.textContent = String(Number(el.textContent) + 1);
  };
</script>"""
INNER = "<!doctype html><title>Inner</title><p id=deepframe>inside a frame</p>"
PAGES = {"/page": PAGE, "/other": "<title>Other</title><p>other</p>",
         "/inner": INNER, "/thing.txt": "the bytes in the file"}

app = H.app()
srv = H.Server(PAGES)
scratch = B.CONFIG_FILE.parent
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(500)
bridge = agent_bridge.install(win)
check("the bridge listens", bridge is not None)
path = agent_bridge.socket_path()
client.SOCKET_NAME = agent_bridge.SOCKET_NAME
answers = {}


def ask(name, req, timeout=30):
    """One request from a thread, so the Qt loop keeps running."""
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
        except Exception as e:
            answers[name] = {"ok": False, "error": "client: %s" % e}
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    H.wait_for(lambda: name in answers, timeout=timeout * 1000)
    return answers.get(name, {"ok": False, "error": "no reply"})


r = ask("open", {"op": "open", "url": srv.url("/page")})
check("a tab opens", r.get("ok") and "tab" in r, r)
tid = r["tab"]["id"]
r = ask("wait", {"op": "wait", "tab": tid, "selector": "#h",
                 "timeout": 10000})
check("...and the page is there", r.get("ok") and r.get("found"), r)

print("\n(1) the page as numbered refs")
r = ask("tree", {"op": "tree", "tab": tid})
check("the tree comes back", r.get("ok") and r.get("tree"), str(r)[:120])
rows = r.get("tree") or []
check("...with a ref on every row",
      all(isinstance(one.get("ref"), int) for one in rows), rows[:2])
check("...and a role", any(one["role"] == "link" for one in rows),
      [one["role"] for one in rows][:8])
check("...and a name",
      any("the other page" in (one.get("name") or "") for one in rows),
      [one.get("name") for one in rows][:6])
check("...and where it is on the page",
      all(isinstance(one.get("x"), int) for one in rows), rows[:2])
button = next((one for one in rows if one["role"] == "button"
               and "go" in (one.get("name") or "")), None)
check("the button is in the tree", button is not None,
      [one.get("name") for one in rows])
r = ask("clickref", {"op": "click", "tab": tid, "ref": button["ref"]}) \
    if button else {}
check("a ref can be clicked instead of a selector",
      r.get("ok") or r.get("result") in ("clicked", None), r)
H.spin(400)
r = ask("text1", {"op": "text", "tab": tid, "selector": "#h"})
check("...and the page really reacted",
      "clicked" in str(r.get("text") or ""), r)

print("\n(2) selectors that reach into frames and shadow roots")
r = ask("deep", {"op": "text", "tab": tid,
                 "selector": "#shadowhost >>> #deeptext"})
check("a shadow root can be read",
      "in the shadow" in str(r.get("text") or ""), r)
r = ask("deepclick", {"op": "click", "tab": tid,
                      "selector": "#shadowhost >>> #deep"})
check("...and clicked", r.get("ok"), r)
H.spin(400)
r = ask("text2", {"op": "text", "tab": tid, "selector": "#h"})
check("...and the page says so", "deep clicked" in str(r.get("text") or ""),
      r)
r = ask("frame", {"op": "text", "tab": tid,
                  "selector": "#frame >>> #deepframe"})
check("an iframe can be read too",
      "inside a frame" in str(r.get("text") or ""), r)
r = ask("nodeep", {"op": "text", "tab": tid,
                   "selector": "#nothing >>> #deep"})
check("...and a path that does not exist is no match", not r.get("ok"), r)

print("\n(3) what the tab fetched")
r = ask("net", {"op": "network", "tab": tid})
check("the requests come back", r.get("ok") and r.get("requests"),
      str(r)[:100])
rows = r.get("requests") or []
check("...with the document among them",
      any(one["kind"] == "document" for one in rows),
      [one["kind"] for one in rows][:6])
check("...and a size for each", all("size" in one for one in rows),
      rows[:2])
check("...and it says what it cannot know",
      "status" in str(r.get("note") or ""), r.get("note"))

print("\n(4) a file through the browser's own session")
out = scratch / "fetched.txt"
r = ask("down", {"op": "download", "tab": tid,
                 "url": srv.url("/thing.txt"), "path": str(out)},
        timeout=40)
check("the file comes down", r.get("ok"), r)
check("...and is really there", out.is_file() and out.read_text()
      == "the bytes in the file", out.is_file() and out.read_text()[:40])
check("...with its size", r.get("bytes") == len("the bytes in the file"), r)
check("...and its hash", len(str(r.get("sha256") or "")) == 64, r)
r = ask("down2", {"op": "download", "tab": tid,
                  "url": srv.url("/nothing-here"),
                  "path": str(scratch / "no.txt")}, timeout=40)
check("a fetch that fails says so", r.get("ok") is False, r)

print("\n(5) the event stream")
events = []


# the listener stays up for the rest of the test: the watch a few
# groups below fires into the same stream, and a listener that hangs up
# after the first few events would miss it
stop = []


def listen():
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(path)
        s.sendall((json.dumps({"op": "events"}) + "\n").encode())
        buf = b""
        while not stop:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                if line.strip():
                    events.append(json.loads(line.decode()))
        s.close()
    except Exception as e:
        events.append({"error": str(e)})


thread = threading.Thread(target=listen, daemon=True)
thread.start()
H.wait_for(lambda: events, 8000)
check("the stream answers that it is listening",
      events and events[0].get("listening") is True, events[:1])
r = ask("nav2", {"op": "nav", "tab": tid, "url": srv.url("/other")})
H.wait_for(lambda: any(one.get("event") == "loaded" for one in events),
           12000)
check("a load is an event",
      any(one.get("event") == "loaded" for one in events),
      [one.get("event") for one in events])
check("...with the tab and the address in it",
      any(one.get("event") == "loaded" and one.get("url")
          for one in events),
      [one for one in events if one.get("event") == "loaded"][:1])
r = ask("nav3", {"op": "nav", "tab": tid, "url": srv.url("/page")})
H.wait_for(lambda: any(one.get("event") == "title" for one in events),
           12000)
check("a title change is an event too",
      any(one.get("event") == "title" for one in events),
      [one.get("event") for one in events])

print("\n(6) watching a page")
r = ask("wait2", {"op": "wait", "tab": tid, "selector": "#counter",
                  "timeout": 10000})
r = ask("watch", {"op": "watch", "tab": tid, "selector": "#counter",
                  "every": 2})
check("a watch starts", r.get("ok") and r.get("watch"), r)
which = r.get("watch")
r = ask("watches", {"op": "watches"})
check("...and is listed",
      any(one.get("id") == which for one in r.get("watches") or []), r)
H.spin(500)
watched = [v for _i, v in bridge._views()
           if getattr(v, "_agent_id", None) == tid][0]
check("...and the page it watches has the element",
      (H.js(watched, "document.getElementById('counter').textContent",
            B.APP_WORLD_ID) or "") != "",
      H.js(watched, "document.getElementById('counter').textContent",
           B.APP_WORLD_ID))
H.js(watched, "window.__bump()", B.MAIN_WORLD_ID)
H.wait_for(lambda: any(one.get("event") == "changed" for one in events),
           14000)
check("...and it fires when the element changes",
      any(one.get("event") == "changed" for one in events),
      [one.get("event") for one in events][-4:])
found = [one for one in events if one.get("event") == "changed"]
check("...with the old text and the new",
      found and found[0].get("was") != found[0].get("now"), found[:1])
r = ask("unwatch", {"op": "unwatch", "watch": which})
check("a watch can be stopped", r.get("ok"), r)
r = ask("watches2", {"op": "watches"})
check("...and it is gone", not r.get("watches"), r)

print("\n(7) a tab that reloads itself")
r = ask("refresh", {"op": "refresh", "tab": tid, "every": 3})
check("a scheduled reload is set", r.get("ok") and r.get("every") == 3, r)
r = ask("refresh0", {"op": "refresh", "tab": tid, "every": 0})
check("...and can be switched off", r.get("ok") and r.get("every") == 0, r)

print("\n(8) macros")
r = ask("mstart", {"op": "macro", "tab": tid, "do": "start"})
check("recording starts", r.get("ok") and r.get("recording"), r)
view = [v for i, v in bridge._views() if v._agent_id == tid][0]
H.js(view, """(function(){
  document.getElementById('b').click();
  var el = document.getElementById('i');
  el.value = 'typed by hand';
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return 'done';})()""", B.MAIN_WORLD_ID)
H.spin(500)
r = ask("mstop", {"op": "macro", "tab": tid, "do": "stop",
                  "name": "demo"})
check("...and stops with the steps in it",
      r.get("ok") and len(r.get("steps") or []) >= 2, r)
steps = r.get("steps") or []
check("...which are clicks and typing",
      {one["op"] for one in steps} <= {"click", "type"},
      [one["op"] for one in steps])
check("...with the selector of what was touched",
      all(one.get("selector") for one in steps), steps[:2])
r = ask("mlist", {"op": "macro", "do": "list"})
check("a macro can be kept by name", "demo" in (r.get("macros") or []), r)
H.js(view, """(function(){
  document.getElementById('h').textContent = 'before replay';
  document.getElementById('i').value = '';
  return 'reset';})()""", B.MAIN_WORLD_ID)
H.spin(300)
r = ask("mplay", {"op": "macro", "tab": tid, "do": "play",
                  "name": "demo"}, timeout=30)
check("...and played back", r.get("ok") and r.get("played") >= 2, r)
H.spin(600)
r = ask("afterplay", {"op": "text", "tab": tid, "selector": "#h"})
check("...which really did it again",
      "clicked" in str(r.get("text") or ""), r)
r = ask("afterfield", {"op": "js", "tab": tid,
                       "code": "document.getElementById('i').value"})
check("...including the typing",
      "typed by hand" in str(r.get("result") or ""), r)
r = ask("mplay2", {"op": "macro", "tab": tid, "do": "play",
                   "name": "nothing"})
check("a macro that is not there says so", r.get("ok") is False, r)

print("\n(9) a button clicked for him")
r = ask("auto", {"op": "autoclick", "host": "127.0.0.1",
                 "selector": "#b"})
check("a rule can be set", r.get("ok") and r.get("rules"), r)
check("...and is kept against the site",
      "#b" in (r["rules"].get("127.0.0.1") or []), r["rules"])
r = ask("nav4", {"op": "nav", "tab": tid, "url": srv.url("/page")})
H.wait_for(lambda: (H.js(view, "document.getElementById('h')"
                              ".textContent", B.MAIN_WORLD_ID) or "")
           == "clicked", 12000)
check("...and the button really gets clicked when the page arrives",
      (H.js(view, "document.getElementById('h').textContent",
            B.MAIN_WORLD_ID) or "") == "clicked",
      H.js(view, "document.getElementById('h').textContent",
           B.MAIN_WORLD_ID))
r = ask("autooff", {"op": "autoclick", "host": "127.0.0.1",
                    "remove": True})
check("...and the rule can be taken away",
      not (r.get("rules") or {}).get("127.0.0.1"), r)

print("\n(10) the tabs the agent owns")
r = ask("mine", {"op": "mine", "do": "list"})
check("the tabs it opened are its own",
      any(one["id"] == tid for one in r.get("tabs") or []), r)
r = ask("mineidle", {"op": "mine", "do": "idle", "after": 3600})
check("an idle time can be set", r.get("ok") and r.get("after") == 3600, r)
check("...and nothing is closed before it",
      bridge.close_idle_agent_tabs() == [],
      bridge.close_idle_agent_tabs())
r = ask("open2", {"op": "open", "url": srv.url("/other")})
spare = r["tab"]["id"]
before = len(bridge._views())
r = ask("mineclose", {"op": "mine", "do": "close"})
check("they can all be closed in one go", r.get("closed") >= 2, r)
check("...and they really are", len(bridge._views()) < before,
      (before, len(bridge._views())))

print("\n(11) the audit log and the permission levels")
r = ask("audit", {"op": "audit", "limit": 20})
check("every op is written down", r.get("ok") and r.get("audit"),
      str(r)[:100])
rows = r.get("audit") or []
check("...with the op and the time",
      all(one.get("op") and one.get("t") for one in rows), rows[:2])
check("...and this very request in it",
      any(one["op"] == "audit" for one in rows),
      [one["op"] for one in rows][-4:])
r = ask("perm", {"op": "permissions"})
check("the level can be asked for", r.get("level") == "full", r)
r = ask("permread", {"op": "permissions", "level": "read"})
check("...and set", r.get("level") == "read", r)
r = ask("openread", {"op": "open", "url": srv.url("/other")})
check("a read-only bridge refuses to open a tab",
      r.get("ok") is False and "read" in str(r.get("error")), r)
r = ask("textread", {"op": "tabs"})
check("...but still answers a read op", r.get("ok"), r)
r = ask("permfull", {"op": "permissions", "level": "full"})
check("...and full is full again", r.get("level") == "full", r)
r = ask("permops", {"op": "permissions", "ops": ["tabs", "permissions"]})
check("an allow list of ops can be set", r.get("ops") == ["tabs",
                                                          "permissions"], r)
r = ask("opsrefuse", {"op": "ping"})
check("...and an op not on it is refused",
      r.get("ok") is False and "not-allowed" in str(r.get("error")), r)
r = ask("permops2", {"op": "permissions", "ops": []})
check("...and clearing the list lets everything through again",
      r.get("ok") and ask("ping2", {"op": "ping"}).get("ok"), r)
r = ask("hist", {"op": "history", "text": "other"})
check("his history is off even at full permission",
      r.get("ok") is False, r)
win.config["bridgeHistory"] = True
win.history = [{"url": srv.url("/other"), "title": "other",
                "t": time.time()}]
r = ask("hist2", {"op": "history", "text": "other"})
check("...and on when he says so", r.get("ok") and r.get("history"), r)
win.config["bridgeHistory"] = False
r = ask("off", {"op": "permissions", "level": "off"})
r = ask("offping", {"op": "ping"})
check("switched off, the bridge answers nothing but why",
      r.get("ok") is False and r.get("error") == "bridge-off", r)
win.config["bridgeLevel"] = "full"

print("\n(12) the rest of the new ops")
# "mine close" above closed the agent's own tabs, this one included, so
# a fresh one is opened for the ops that need a page
r = ask("open4", {"op": "open", "url": srv.url("/page")})
tid = r["tab"]["id"]
ask("wait4", {"op": "wait", "tab": tid, "selector": "#h",
              "timeout": 10000})
r = ask("open3", {"op": "open", "url": srv.url("/page"),
                  "private": True})
check("a tab can be opened as a private one", r.get("ok"), r)
priv = r["tab"]["id"]
check("...and it really is private",
      any(getattr(v, "private", False) for _i, v in bridge._views()
          if getattr(v, "_agent_id", None) == priv))
r = ask("view", {"op": "viewport", "tab": priv, "size": "phone"})
check("a tab can be given a phone's size", r.get("ok"), r)
r = ask("view2", {"op": "viewport", "tab": priv, "width": 500,
                  "height": 400})
check("...or a size of its own",
      r.get("ok") and r.get("width") == 500, r)
r = ask("view3", {"op": "viewport", "tab": priv})
check("...and put back", r.get("ok"), r)
r = ask("groups", {"op": "groups"})
check("the groups can be listed", r.get("ok") and "groups" in r, r)
r = ask("groupmove", {"op": "groups", "move": priv, "group": "agents"})
check("...and a tab moved into one", r.get("ok"), r)
check("...which the browser agrees with",
      any(win._group_of(v) == "agents" for _i, v in bridge._views()
          if getattr(v, "_agent_id", None) == priv),
      [win._group_of(v) for _i, v in bridge._views()])
(scratch / "upload.txt").write_text("a file to upload")
r = ask("upload", {"op": "upload", "tab": tid,
                   "paths": [str(scratch / "upload.txt")]})
check("files can be set for the page's chooser", r.get("ok"), r)
view = [v for i, v in bridge._views() if v._agent_id == tid][0]
check("...and the page's chooser is answered with them",
      view.page()._agent_files == [str(scratch / "upload.txt")],
      getattr(view.page(), "_agent_files", None))
r = ask("upload2", {"op": "upload", "tab": tid,
                    "paths": [str(scratch / "nope.txt")]})
check("a file that is not there is refused", r.get("ok") is False, r)
r = ask("point", {"op": "pointer", "tab": tid, "kind": "move",
                  "x": 40, "y": 40})
check("the pointer can be moved", r.get("ok"), r)
r = ask("point2", {"op": "pointer", "tab": tid, "kind": "right",
                   "x": 40, "y": 40})
check("...and right-clicked", r.get("ok"), r)
r = ask("point3", {"op": "pointer", "tab": tid, "kind": "drag",
                   "x": 10, "y": 10, "tox": 80, "toy": 80})
check("...and dragged", r.get("ok"), r)

print("\n(13) the client as a module, and a batch")
missing = [name for name in client.OPS
           if not callable(getattr(client,
                                   client._RENAMED.get(name, name), None))]
check("every op has a function of its own", missing == [], missing)
check("...and the three that would shadow a builtin are renamed",
      callable(client.open_tab) and callable(client.type_text)
      and not hasattr(client, "type"),
      sorted(client._RENAMED))
check("...and there is one for the new ones",
      all(callable(getattr(client, name, None))
          for name in ("tree", "network", "watch", "macro", "audit",
                       "permissions", "pointer")))
check("the batch runner is there", callable(client.run))
check("...and reads a file of steps", callable(client.run_file))
check("...and the event stream is a generator", callable(client.stream))
steps = [{"op": "ping"}, {"op": "tabs"}]
(scratch / "steps.json").write_text(json.dumps(steps))
done = {}


def batch():
    try:
        done["rows"] = client.run_file(str(scratch / "steps.json"))
    except Exception as e:
        done["rows"] = [{"ok": False, "error": str(e)}]


thread = threading.Thread(target=batch, daemon=True)
thread.start()
H.wait_for(lambda: "rows" in done, 20000)
rows = done.get("rows") or []
check("a batch of ops runs in order", len(rows) == 2, rows)
check("...and all of them answered", all(one.get("ok") for one in rows),
      rows)
bad = [{"op": "ping"}, {"op": "nonsense"}, {"op": "ping"}]
done2 = {}


def batch2():
    done2["rows"] = client.run(bad)


thread = threading.Thread(target=batch2, daemon=True)
thread.start()
H.wait_for(lambda: "rows" in done2, 20000)
rows = done2.get("rows") or []
check("a batch stops at the first failure", len(rows) == 2, rows)
check("...and says which step it was",
      rows and rows[-1].get("ok") is False, rows[-1:])

print("\n(14) the http mirror, and the headless instance")
mirror = agent_bridge.RestMirror(bridge, port=8911, token="secret")
check("the mirror starts", mirror.start() is True)
got = {}


def post(body, token="secret"):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        "http://127.0.0.1:8911/", data=json.dumps(body).encode(),
        headers={"X-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as answer:
            got["answer"] = json.loads(answer.read().decode())
    except urllib.error.HTTPError as e:
        got["answer"] = json.loads(e.read().decode())
    except Exception as e:
        got["answer"] = {"ok": False, "error": str(e)}


thread = threading.Thread(target=lambda: post({"op": "ping"}), daemon=True)
thread.start()
H.wait_for(lambda: "answer" in got, 25000)
check("an op over http answers",
      (got.get("answer") or {}).get("ok") is True, got)
got.clear()
thread = threading.Thread(target=lambda: post({"op": "ping"}, token="wrong"),
                          daemon=True)
thread.start()
H.wait_for(lambda: "answer" in got, 25000)
check("...and a wrong token is refused",
      (got.get("answer") or {}).get("error") == "bad-token", got)
mirror.stop()
source = Path("browser.py").read_text()
check("the headless instance is a launch flag",
      '"--agent" in argv' in source)
check("...with its own sockets, never the one he is using",
      'SINGLE_INSTANCE_SOCKET += "-agent"' in source
      and 'agent_bridge.SOCKET_NAME += "-agent"' in source)
check("...and it shows no window at all",
      "nothing is shown at all" in source)

print("\n(15) the event hooks")
hook = scratch / "hook.sh"
hook.write_text("#!/bin/sh\ncat > %s\n" % (scratch / "hook-saw.json"))
hook.chmod(0o755)
win.config["eventHooks"] = {"loaded": str(hook)}
bridge.emit("loaded", tab=tid, url=srv.url("/page"), ok=True)
H.wait_for(lambda: (scratch / "hook-saw.json").is_file(), 8000)
check("a hook runs when an event happens",
      (scratch / "hook-saw.json").is_file())
check("...and is handed the event as JSON",
      "loaded" in (scratch / "hook-saw.json").read_text()
      if (scratch / "hook-saw.json").is_file() else False,
      (scratch / "hook-saw.json").read_text()[:80]
      if (scratch / "hook-saw.json").is_file() else "")
win.config["eventHooks"] = {}
check("...and nothing runs without one",
      bridge.run_hook("loaded", {"event": "loaded"}) == "")

stop.append(True)
H.spin(300)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
