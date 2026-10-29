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
  agent.py pdf PATH [--tab ID]
  agent.py markdown [SELECTOR] [--tab ID]      -> the page as Markdown
  agent.py box SELECTOR [--tab ID]             -> where it is, how it looks
  agent.py find TEXT [--tab ID]                -> elements by their words
  agent.py fill '{"#user":"ada"}' [--tab ID]   -> a whole form at once
  agent.py idle [QUIET_MS] [--tab ID]          -> wait for the fetching to stop
  agent.py links [PATTERN] [--tab ID]
  agent.py tables [INDEX] [--tab ID]
  agent.py console [clear] [--tab ID]
  agent.py dialog [true|false|TEXT] [--tab ID] -> answer alert/confirm/prompt
  agent.py cookies [HOST]                      -> names only, never values
  agent.py bookmarks [TEXT] | bookmarks add URL [TITLE]
  agent.py downloads
  agent.py notify TEXT
  agent.py restart
  agent.py chatgpt 'QUESTION' [--tab ID] [--timeout S]   (see below)
  agent.py ask claude 'QUESTION' [--tab ID]    -> an assistant in a tab
  agent.py tree [LIMIT] [--tab ID]             -> the page as numbered refs
  agent.py network [--tab ID]                  -> what the tab fetched
  agent.py download URL PATH [--tab ID]        -> through this session
  agent.py events [KIND...]                    -> stream tab events
  agent.py watch SELECTOR [EVERY] [--tab ID]   -> say when it changes
  agent.py unwatch [ID|all]
  agent.py refresh SECONDS [--tab ID]          -> reload on a timer
  agent.py macro start|stop|play|list [NAME]
  agent.py autoclick HOST SELECTOR [remove]
  agent.py mine [list|close|idle SECONDS]      -> the tabs this opened
  agent.py audit [clear]                       -> what has driven this
  agent.py permissions [off|read|full]
  agent.py search 'WORDS'                      -> results as a list
  agent.py viewport phone|WIDTH HEIGHT [--tab ID]
  agent.py groups [move TAB GROUP]
  agent.py history 'WORDS'                     -> off unless allowed
  agent.py upload PATH... [#selector] [--tab ID]
  agent.py pointer click|right|move|drag X Y [TOX TOY] [--tab ID]
  agent.py run steps.json                      -> a batch, stops on error

As a module: `import agent; agent.open(url=...); agent.run(steps)`.
Every op has a function of the same name, and agent.stream() yields
events as they arrive.

`chatgpt` is the one composite command: it opens (or reuses) a
chatgpt.com tab in the background, types the question, sends it, waits
for the answer to finish streaming and prints it. The tab stays open so
a follow-up question lands in the same conversation. Whoever is using
the PC never sees the tab unless they go looking for it.

Exit status: 0 on ok, 1 on an error reply, 2 when no browser is running.
"""
import argparse
import io
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


# ---- usable as a module ----------------------------------------------
# `import agent` and call agent.text(), agent.click(), agent.run(...).
# Every op is a function here because a script that has to build
# dictionaries of strings is a script nobody writes twice. One function
# per op, generated from the names, plus the handful that take their
# arguments in an order worth remembering.

#: the ops this client knows how to name. The browser may answer more
#: (it says so for an unknown op), and a new one needs no change here
#: beyond a line in this tuple to get a function of its own.
OPS = (
    "ping", "tabs", "open", "close", "select", "nav", "reload", "info",
    "js", "text", "html", "wait", "click", "type", "key", "scroll",
    "shot", "pdf", "markdown", "box", "find", "fill", "idle", "links",
    "tables", "console", "dialog", "cookies", "bookmarks", "downloads",
    "notify", "restart", "tree", "network", "download", "events",
    "watch", "unwatch", "watches", "refresh", "macro", "autoclick",
    "mine", "audit", "permissions", "search", "ask", "viewport",
    "groups", "history", "upload", "pointer",
)


def op(name, **what):
    """One op by name, with its arguments. The honest primitive: every
    function below is this with the name filled in."""
    req = {"op": str(name)}
    req.update({k: v for k, v in what.items() if v is not None})
    answer = call(req, timeout=float(what.pop("timeout_s", 60) or 60))
    return answer


def _make(name):
    def run(**what):
        return op(name, **what)
    run.__name__ = name
    run.__doc__ = "The bridge's %s op. Keyword arguments go straight " \
                  "through as JSON." % name
    return run


#: three op names are also the names of builtins, and a module that
#: shadows open() breaks the next thing that opens a file -- which is
#: exactly what happened to run_file(). They get a plain name instead,
#: and op("open", ...) still reaches them by their real name.
_RENAMED = {"open": "open_tab", "type": "type_text", "print": "print_page"}

for _name in OPS:
    globals().setdefault(_RENAMED.get(_name, _name), _make(_name))


def run(steps, stop_on_error=True):
    """A list of ops, in order, stopping at the first failure.

    `steps` is a list of dictionaries -- the same shape the socket
    takes, so a batch file is a list of what you would have typed.
    Returns the answers, and raises nothing: the caller gets to see
    which step failed and what it said."""
    if isinstance(steps, (str, bytes)):
        steps = json.loads(steps)
    out = []
    for one in steps:
        if not isinstance(one, dict) or not one.get("op"):
            out.append({"ok": False, "error": "step needs an op"})
            if stop_on_error:
                break
            continue
        answer = call(one, timeout=float(one.pop("timeout_s", 60) or 60))
        out.append(answer)
        if stop_on_error and not answer.get("ok"):
            break
    return out


def run_file(path, stop_on_error=True):
    """The same, out of a file of JSON steps."""
    with io.open(path, "r", encoding="utf-8") as handle:
        return run(json.load(handle), stop_on_error)


def stream(kinds=None, tab=None, on_event=None, timeout=None):
    """Listen to the browser's events until the caller has had enough.

    Yields each event as it arrives (and calls on_event too, for the
    scripts that would rather hand in a function). The connection is
    the subscription: hanging up ends it."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout or 3600)
    s.connect(socket_path())
    req = {"op": "events"}
    if kinds:
        req["kinds"] = list(kinds)
    if tab is not None:
        req["tab"] = tab
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                if not line.strip():
                    continue
                try:
                    row = json.loads(line.decode())
                except ValueError:
                    continue
                if on_event is not None:
                    on_event(row)
                yield row
    finally:
        s.close()


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
        elif op == "markdown":
            if args:
                req.update(selector=args[0])
        elif op == "box":
            req.update(selector=args[0])
        elif op == "find":
            req.update(text=" ".join(args))
        elif op == "fill":
            # one JSON object: {"#user": "ada", "#pass": "..."}
            req.update(fields=json.loads(args[0]))
        elif op == "idle":
            req.update(quiet=int(args[0]) if args else 700,
                       timeout=int((a.timeout or 15) * 1000))
        elif op == "links":
            if args:
                req.update(pattern=args[0])
        elif op == "tables":
            if args:
                req.update(index=int(args[0]))
        elif op == "console":
            req.update(clear=bool(args and args[0] == "clear"))
        elif op == "dialog":
            if args:
                answer = args[0]
                req.update(answer=True if answer == "true"
                           else False if answer == "false" else answer)
        elif op == "pdf":
            req.update(path=os.path.abspath(args[0]))
        elif op == "cookies":
            if args:
                req.update(host=args[0])
        elif op == "bookmarks":
            if args and args[0] == "add":
                req.update(action="add", url=args[1] if len(args) > 1 else "",
                           title=" ".join(args[2:]))
            elif args:
                req.update(text=" ".join(args))
        elif op == "notify":
            req.update(text=" ".join(args))
        elif op == "key":
            req.update(key=args[0] if args else "enter")
        elif op == "scroll":
            y = args[0] if args else "bottom"
            req.update(y=y if y == "bottom" else int(y))
        elif op == "shot":
            req.update(path=os.path.abspath(args[0]))
        elif op == "run":
            # a batch of ops out of a file: the one command that is not
            # a single op, because "do these five things and stop if
            # one fails" is what a script actually wants
            answers = run_file(args[0])
            print(json.dumps(answers, indent=1, ensure_ascii=False))
            return 0 if all(one.get("ok") for one in answers) else 1
        elif op == "events":
            for row in stream(kinds=args or None, tab=a.tab,
                              timeout=a.timeout):
                print(json.dumps(row, ensure_ascii=False), flush=True)
            return 0
        elif op == "tree":
            req.update(limit=int(args[0]) if args else 200)
        elif op == "download":
            req.update(url=args[0], path=os.path.abspath(args[1]))
        elif op == "watch":
            req.update(selector=args[0] if args else "body",
                       every=int(args[1]) if len(args) > 1 else 60)
        elif op == "unwatch":
            req.update(watch=args[0] if args else "all")
        elif op == "refresh":
            req.update(every=int(args[0]) if args else 0)
        elif op == "macro":
            req.update(do=args[0] if args else "status",
                       name=args[1] if len(args) > 1 else "")
        elif op == "autoclick":
            req.update(host=args[0] if args else "",
                       selector=args[1] if len(args) > 1 else "",
                       remove=bool(len(args) > 2 and args[2] == "remove"))
        elif op == "mine":
            req.update(do=args[0] if args else "list",
                       after=int(args[1]) if len(args) > 1 else None)
        elif op == "audit":
            req.update(clear=bool(args and args[0] == "clear"))
        elif op == "permissions":
            if args:
                req.update(level=args[0])
        elif op == "search":
            req.update(text=" ".join(args))
        elif op == "ask":
            req.update(which=args[0] if args else "claude",
                       text=" ".join(args[1:]))
        elif op == "viewport":
            if args and args[0].isdigit() and len(args) > 1:
                req.update(width=int(args[0]), height=int(args[1]))
            elif args:
                req.update(size=args[0])
        elif op == "groups":
            if args and args[0] == "move":
                req.update(move=int(args[1]),
                           group=args[2] if len(args) > 2 else "")
        elif op == "history":
            req.update(text=" ".join(args), limit=50)
        elif op == "upload":
            req.update(paths=[os.path.abspath(one) for one in args
                              if not one.startswith("#")],
                       selector=next((one for one in args
                                      if one.startswith("#")), ""))
        elif op == "pointer":
            req.update(kind=args[0] if args else "click",
                       x=int(args[1]) if len(args) > 1 else 0,
                       y=int(args[2]) if len(args) > 2 else 0,
                       tox=int(args[3]) if len(args) > 3 else None,
                       toy=int(args[4]) if len(args) > 4 else None)
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
