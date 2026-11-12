"""Bugs found by the 2026-11 line-by-line review, one check each.

Plain functions of browser.py where possible, so most of this needs no
window. Nothing here touches your data (see harness.boot)."""
import json, sys
import harness as H

B = H.boot()
RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % extra) if extra else ""))


# -- the bar's calculator: a power of a power must not blow up ----------
for expr in ("((9^64)^64)^2", "(((9^64)^64)^64)", "(9^64)^64"):
    try:
        got = B._calc_answer(expr)
        check("calc %s answers or declines without raising" % expr,
              got is None or isinstance(got, tuple), got)
    except Exception as e:
        check("calc %s answers or declines without raising" % expr,
              False, repr(e)[:80])
check("calc still does 12*64", B._calc_answer("12*64") == ("= 768", "768"))
check("calc still does 2^10", B._calc_answer("2^10") == ("= 1024", "1024"))

# -- a bad debug port in the config must not stop the start ---------------
for bad in ("abc", 99999, [1], -5):
    B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    B.CONFIG_FILE.write_text(json.dumps({"debugPort": True,
                                         "debugPortNumber": bad}))
    try:
        flags = B._startup_flags()
        check("debugPortNumber=%r still starts" % (bad,),
              "--remote-debugging-port=9222" in flags, flags)
    except Exception as e:
        check("debugPortNumber=%r still starts" % (bad,), False, repr(e)[:80])
B.CONFIG_FILE.write_text(json.dumps({"debugPort": True,
                                     "debugPortNumber": 9333}))
check("a good debug port is kept",
      "--remote-debugging-port=9333" in B._startup_flags())
B.CONFIG_FILE.unlink()

# -- the Minecraft ping never raises, whatever the server sends ---------
import socket as _socket, threading as _threading


def _fake_mc(answer):
    srv_sock = _socket.socket()
    srv_sock.bind(("127.0.0.1", 0))
    srv_sock.listen(1)

    def serve():
        c, _ = srv_sock.accept()
        try:
            c.recv(4096)
            body = json.dumps(answer).encode()
            pkt = b"\x00" + B._varint(len(body)) + body
            c.sendall(B._varint(len(pkt)) + pkt)
        finally:
            c.close()
            srv_sock.close()
    _threading.Thread(target=serve, daemon=True).start()
    return srv_sock.getsockname()[1]


for answer in ([], 7, {"players": "lots"}, {"players": {"online": "x"}},
               {"description": {"extra": 5}}, {"version": "1.21"}):
    port = _fake_mc(answer)
    try:
        got = B.mc_ping("127.0.0.1", port, timeout=2)
        check("mc_ping survives %r" % (answer,), isinstance(got, dict), got)
    except Exception as e:
        check("mc_ping survives %r" % (answer,), False, repr(e)[:80])
port = _fake_mc({"players": {"online": 3, "max": 20},
                 "version": {"name": "1.21"}, "description": "hi"})
got = B.mc_ping("127.0.0.1", port, timeout=2)
check("mc_ping still reads a real answer",
      got.get("up") and got.get("players") == 3 and got.get("motd") == "hi",
      got)

# -- window-level checks ---------------------------------------------------
app = H.app()
srv = H.Server({
    "/urltext": "<title>u</title><p id=t>see https://a.example/x and "
                "&lt;img src=x onerror=&quot;window.pwned=1&quot;&gt; too</p>",
    "/boldtext": "<title>b</title><p id=t>Hello reader "
                 "&lt;img src=x onerror=&quot;window.pwned2=1&quot;&gt; "
                 "a&lt;i&gt;b</p>",
    "/code": "<title>c</title><pre id=c>// a comment \"quoted\" 42\n"
             "var s = \"text\"; x = f(3); # hash &lt;b&gt;</pre>",
    "/timers": "<title>t</title><script>window.ticks=0;"
                "setInterval(function(){window.ticks++},20)</script>"})
br = B.Browser()
br.show()
H.spin(300)
view = br.current()

# the page menu's Freeze: the page's own timers must stop
H.load(view, srv.url("/timers"))
H.spin(500)
br.page_tool("freeze", view=view)
H.spin(300)
H.js(view, "window.later=0;setTimeout(function(){window.later=1},10);"
           "window.base=window.ticks")
H.spin(600)
check("Freeze stops the page's running interval",
      H.js(view, "window.ticks-window.base") == 0,
      H.js(view, "window.ticks-window.base"))
check("Freeze stops a timer the page sets afterwards",
      H.js(view, "window.later") == 0)
br.page_tool("thaw", view=view)
H.spin(200)
H.js(view, "window.later2=0;setTimeout(function(){window.later2=1},10)")
H.spin(300)
check("Thaw gives the page its timers back", H.js(view, "window.later2") == 1)

# clickable addresses: the page's own text must stay text
br.config["nav"] = {"clickableUrls": True}
br.refresh_nav()
H.load(view, srv.url("/urltext"))
H.spin(1500)
check("clickable URLs: the address became a link",
      H.js(view, "document.querySelectorAll('#t a.__navurl').length") == 1)
check("clickable URLs: text that looks like markup is not run",
      H.js(view, "window.pwned === undefined && "
                 "!document.querySelector('#t img')"))
check("clickable URLs: the words around it are kept",
      "onerror" in (H.js(view, "document.getElementById('t').textContent")
                    or ""))
br.config["nav"] = {}
br.refresh_nav()

# bold word starts (accessibility): the page's text must stay text
br.config["a11y"] = {"boldStarts": True}
br.refresh_a11y()
H.load(view, srv.url("/boldtext"))
H.spin(1500)
check("bold starts: words got their bold start",
      (H.js(view, "document.querySelectorAll('#t b').length") or 0) >= 2)
check("bold starts: text that looks like markup is not run",
      H.js(view, "window.pwned2 === undefined && "
                 "!document.querySelector('#t img')"))
check("bold starts: the text reads the same",
      H.js(view, "document.getElementById('t').textContent")
      == 'Hello reader <img src=x onerror="window.pwned2=1"> a<i>b')
br.config["a11y"] = {}
br.refresh_a11y()

# code highlighting: colours only, the code itself unchanged
H.load(view, srv.url("/code"))
H.spin(800)
before = H.js(view, "document.getElementById('c').textContent")
br.read_page_tool("highlight", view=view)
H.spin(500)
after = H.js(view, "document.getElementById('c').textContent")
check("highlight: coloured something",
      (H.js(view, "document.querySelectorAll('#c span').length") or 0) > 0)
check("highlight: the code reads exactly as before", before == after,
      repr(after)[:160])

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
