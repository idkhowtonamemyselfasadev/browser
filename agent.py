#!/usr/bin/env python3
"""Drive the running browser from the terminal (the agent bridge client).

No Qt needed here: it is a plain Unix socket in the temp directory.
One request, one JSON reply. Plain results print as text; --json
prints the whole reply.

  agent.py ping
  agent.py tabs
  agent.py open URL [--switch]                 -> prints the new tab id
  agent.py close|select|reload|info [--tab ID]
  agent.py nav URL [--tab ID]
  agent.py js 'CODE' [--tab ID] [--main]
  agent.py text [SELECTOR] [--tab ID]
  agent.py html [SELECTOR] [--tab ID]
  agent.py wait SELECTOR [--tab ID] [--timeout MS] [--gone]
  agent.py click SELECTOR [--tab ID] [--index N]
  agent.py type SELECTOR TEXT [--tab ID] [--clear] [--enter]
  agent.py key NAME [--tab ID]
  agent.py scroll [Y|bottom] [--tab ID]
  agent.py shot PATH [--tab ID]
  agent.py restart
  agent.py chatgpt 'QUESTION' [--tab ID] [--timeout S]   (see below)

`chatgpt` is the one composite command: it opens (or reuses) a
chatgpt.com tab in the background, types the question, sends it, waits
for the answer to finish streaming and prints it. The tab stays open so
a follow-up question lands in the same conversation. Whoever is using
the PC never sees the tab unless they go looking for it.

Exit status: 0 on ok, 1 on an error reply, 2 when no browser is running.
"""
import argparse
import json
import os
import socket
import sys
import time

SOCKET_NAME = "browser-agent"


def socket_path():
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", SOCKET_NAME)


def call(req, timeout=60.0):
    """One request, one reply. Raises ConnectionError when nobody
    listens (browser not running, or started before the bridge existed)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(socket_path())
    except OSError as e:
        raise ConnectionError("browser not running (or bridge off): %s" % e)
    with s:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                raise ConnectionError("browser closed the connection")
            buf += chunk
    return json.loads(buf.split(b"\n", 1)[0].decode())


# ---- the ChatGPT helper -----------------------------------------------
CHATGPT = "https://chatgpt.com/"
PROMPT_SEL = "#prompt-textarea, div[contenteditable='true'], textarea"
SEND_SEL = ("button[data-testid='send-button'], "
            "button[aria-label='Send prompt'], form button[type='submit']")
STOP_SEL = ("button[data-testid='stop-button'], "
            "button[aria-label='Stop streaming'], button[aria-label='Stop generating']")
ANSWER_JS = """
(function(){
  var msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
  if (!msgs.length) return null;
  var last = msgs[msgs.length - 1];
  return last.innerText;
})()"""
COUNT_JS = "document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"


def chatgpt_tab(tab=None):
    if tab is not None:
        return tab
    for t in call({"op": "tabs"})["tabs"]:
        if "chatgpt.com" in t["url"] or "chat.openai.com" in t["url"]:
            return t["id"]
    r = call({"op": "open", "url": CHATGPT})
    if not r.get("ok"):
        raise RuntimeError(r.get("error"))
    return r["tab"]["id"]


def ask_chatgpt(question, tab=None, timeout=180):
    tab = chatgpt_tab(tab)
    r = call({"op": "wait", "tab": tab, "selector": PROMPT_SEL,
              "timeout": 30000}, timeout=40)
    if not r.get("ok"):
        text = call({"op": "text", "tab": tab}).get("text") or ""
        raise RuntimeError("no prompt box on chatgpt tab (login or "
                           "challenge page?): " + text[:300].replace("\n", " "))
    before = call({"op": "js", "tab": tab, "code": COUNT_JS}).get("result") or 0
    r = call({"op": "type", "tab": tab, "selector": PROMPT_SEL,
              "text": question, "clear": True})
    if not r.get("ok"):
        raise RuntimeError("typing failed: %s" % r)
    time.sleep(0.5)
    r = call({"op": "click", "tab": tab, "selector": SEND_SEL})
    if not r.get("ok"):
        call({"op": "key", "tab": tab, "key": "enter"})
    # a new assistant message appears, then the stop button goes away
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = call({"op": "js", "tab": tab, "code": COUNT_JS}).get("result") or 0
        if n > before:
            break
        time.sleep(1)
    else:
        raise RuntimeError("no answer started within %ss" % timeout)
    time.sleep(1)
    stable, last = 0, None
    while time.time() < deadline:
        streaming = call({"op": "js", "tab": tab,
                          "code": "!!document.querySelector(%s)"
                          % json.dumps(STOP_SEL)}).get("result")
        text = call({"op": "js", "tab": tab, "code": ANSWER_JS}).get("result")
        if not streaming and text == last:
            stable += 1
            if stable >= 2:
                return text or ""
        else:
            stable = 0
        last = text
        time.sleep(1.5)
    return (last or "") + "\n[cut off: still streaming after %ss]" % timeout


# ---- CLI --------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("op")
    p.add_argument("args", nargs="*")
    p.add_argument("--tab", type=int)
    p.add_argument("--json", action="store_true")
    p.add_argument("--switch", action="store_true")
    p.add_argument("--main", action="store_true", help="js: page's main world")
    p.add_argument("--timeout", type=float)
    p.add_argument("--gone", action="store_true")
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--enter", action="store_true")
    a = p.parse_args(argv)
    op, args = a.op, a.args
    req = {"op": op}
    if a.tab is not None:
        req["tab"] = a.tab
    try:
        if op == "chatgpt":
            print(ask_chatgpt(" ".join(args), a.tab, a.timeout or 180))
            return 0
        if op == "open":
            req.update(url=args[0], switch=a.switch)
        elif op == "nav":
            req.update(url=args[0])
        elif op == "js":
            req.update(code=" ".join(args), world="main" if a.main else "app")
        elif op in ("text", "html"):
            if args:
                req.update(selector=args[0])
        elif op == "wait":
            req.update(selector=args[0], gone=a.gone,
                       timeout=int((a.timeout or 15) * 1000))
        elif op == "click":
            req.update(selector=args[0], index=a.index)
        elif op == "type":
            req.update(selector=args[0], text=" ".join(args[1:]),
                       clear=a.clear, enter=a.enter)
        elif op == "key":
            req.update(key=args[0] if args else "enter")
        elif op == "scroll":
            y = args[0] if args else "bottom"
            req.update(y=y if y == "bottom" else int(y))
        elif op == "shot":
            req.update(path=os.path.abspath(args[0]))
        r = call(req, timeout=(a.timeout or 15) + 30 if op == "wait" else 60)
    except ConnectionError as e:
        print(e, file=sys.stderr)
        return 2
    except Exception as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    if a.json or op in ("tabs", "info"):
        print(json.dumps(r, indent=1, ensure_ascii=False))
    elif op == "open":
        print(r["tab"]["id"] if r.get("ok") else r)
    elif op in ("text", "html"):
        print(r.get(op) if r.get("ok") else r)
    elif op == "js":
        v = r.get("result")
        print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    else:
        print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
