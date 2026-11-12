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
    "/timers": "<title>t</title><script>window.ticks=0;"
                "setInterval(function(){window.ticks++},20)</script>"})
br = B.Browser()
br.show()
H.spin(300)
view = br.current()

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

bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED:", n)
sys.stdout.flush()
H.os._exit(1 if bad else 0) if hasattr(H, "os") else sys.exit(1 if bad else 0)
