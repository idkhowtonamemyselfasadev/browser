#!/usr/bin/env python3
"""What a page may do in its own window: the guards in page_guard.py,
the navigation rules that go with them, and the flags the engine can
only be given at launch.

Offscreen, scratch data, local pages. The one thing that goes online
(resolving a short link) is driven against a local server started
here."""
import json
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
import page_guard as PG  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGES = {
    "/a": "<title>Alpha</title><p id=p>alpha</p>",
    "/copy": """<title>Copy</title><p id=p>take this</p>
      <script>window.stolen=0;
      document.addEventListener('copy', function(e){
        window.stolen=1;
        try{e.clipboardData.setData('text/plain','and my advert');}catch(x){}
      });</script>""",
    "/leave": """<title>Leave</title><script>
      window.onbeforeunload = function(){ return 'stay'; };
      window.addEventListener('beforeunload', function(){ window.trapped=1; });
      </script>""",
    "/frames": """<title>Frames</title>
      <iframe id=own src="/a"></iframe>
      <iframe id=other src="http://localhost:1/x"></iframe>""",
    "/banner": """<title>Banner</title>
      <div id="cookie-consent-dialog">
        <button id=yes>Accept all</button>
        <button id=no>Reject all</button>
      </div>
      <form><button id=plain>Decline</button></form>
      <script>window.clicked='';
      document.getElementById('no').addEventListener('click',
        function(){ window.clicked='no'; });
      document.getElementById('plain').addEventListener('click',
        function(){ window.clicked='plain'; });</script>""",
    "/pop": """<title>Pop</title><script>
      window.opened = window.open('/a', '_blank');
      </script>""",
    "/ws": """<title>Ws</title><script>
      try { window.sock = new WebSocket('ws://127.0.0.1:1/x'); } catch (e) {}
      </script>""",
    "/ad": """<title>Ad</title><div class="advert">buy</div><p id=p>text</p>""",
}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
scratch = B.CONFIG_FILE.parent
MAIN = B.MAIN_WORLD_ID


def guard(**on):
    """Switch guards on, put the script back and start a fresh tab."""
    for name in PG.GUARDS:
        win.config["guard" + name[0].upper() + name[1:]] = bool(
            on.get(name, False))
    win.refresh_guard_scripts()


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(300)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


print("\n(1) the rule table the page reads")
rules = PG.rules({"guardFingerprint": True,
                  "guardOff": {"fingerprint": ["Example.COM", "www.x.test"]},
                  "blockApis": {"y.test": ["webgl", "nonsense"]},
                  "fakePlaces": {"z.test": {"lat": 52.5, "lon": 13.4}},
                  "hideElements": {"ad.test": [".advert", ""]},
                  "popupSites": ["pop.test"]})
check("a guard that is on says so", rules["on"]["fingerprint"])
check("one that is not, does not", not rules["on"]["banners"])
check("an excused site is listed without its www",
      rules["off"]["x.test"] == ["fingerprint"], rules["off"])
check("a blocked API becomes the names to take out of the page",
      "WebGLRenderingContext" in rules["apis"]["y.test"], rules["apis"])
check("a name nobody knows is dropped, not trusted",
      "nonsense" not in str(rules["apis"]), rules["apis"])
check("a place is two numbers", rules["places"]["z.test"]["lat"] == 52.5)
check("an empty selector is not a rule",
      rules["hide"]["ad.test"] == [".advert"], rules["hide"])
check("the popup allow list is there", rules["allow"] == ["pop.test"])
check("nothing on means no script at all", not PG.wanted({}))
check("one thing on means there is one", PG.wanted({"guardGpc": True}))
check("so does a per-site rule on its own",
      PG.wanted({"hideElements": {"a.test": [".x"]}}))

print("\n(2) a selector for one element")
check("an id is the whole selector",
      PG.selector_for([{"tag": "DIV", "class": "a"},
                       {"tag": "SPAN", "id": "banner"}]) == "#banner")
check("otherwise the tag and its classes",
      PG.selector_for([{"tag": "DIV", "class": "wrap"},
                       {"tag": "SPAN", "class": "ad big extra"}])
      == "div.wrap > span.ad.big",
      PG.selector_for([{"tag": "DIV", "class": "wrap"},
                       {"tag": "SPAN", "class": "ad big extra"}]))
check("junk in a class name is left out",
      ".." not in PG.selector_for([{"tag": "P", "class": "a:b c"}]))
check("nothing usable gives nothing", PG.selector_for([]) == "")

print("\n(3) the script is only there when something is on")
guard()
names = [s.name() for s in win.profile.scripts().toList()]
check("nothing on: no guard script", PG.GUARD_SCRIPT_NAME not in names, names)
guard(gpc=True)
names = [s.name() for s in win.profile.scripts().toList()]
check("one thing on: one guard script",
      names.count(PG.GUARD_SCRIPT_NAME) == 1, names)
win.refresh_guard_scripts()
names = [s.name() for s in win.profile.scripts().toList()]
check("and putting it back does not leave two",
      names.count(PG.GUARD_SCRIPT_NAME) == 1, names)

print("\n(4) what the machine looks like")
guard(fingerprint=True)
view = page("/a")
check("the number of cores is not the real one",
      js(view, "navigator.hardwareConcurrency") == 4,
      js(view, "navigator.hardwareConcurrency"))
check("getImageData is not the engine's own any more",
      "native code" not in str(js(
          view, "String(CanvasRenderingContext2D.prototype.getImageData)")),
      js(view, "String(CanvasRenderingContext2D.prototype.getImageData)")[:40])
check("a canvas still draws",
      js(view, """(function(){var c=document.createElement('canvas');
        c.width=8;c.height=8;var x=c.getContext('2d');
        x.fillStyle='#f00';x.fillRect(0,0,8,8);
        return c.toDataURL().slice(0,11);})()""") == "data:image/",
      js(view, "1"))
win.config["guardOff"] = {"fingerprint": ["127.0.0.1"]}
win.refresh_guard_scripts()
view2 = page("/a")
check("a site he excused gets the real answer",
      js(view2, "navigator.hardwareConcurrency") != 4,
      js(view2, "navigator.hardwareConcurrency"))
win.config["guardOff"] = {}

print("\n(5) the clipboard")
guard(clipboardRead=True, copyGuard=True)
view = page("/copy")
check("reading the clipboard is refused",
      js(view, """(function(){var out='allowed';
        try{navigator.clipboard.readText().catch(function(){});}catch(e){}
        return String(navigator.clipboard.readText).indexOf('native')<0
               ? 'blocked' : out;})()""") == "blocked")
H.js(view, """(function(){var r=document.createRange();
 r.selectNodeContents(document.getElementById('p'));
 var s=window.getSelection();s.removeAllRanges();s.addRange(r);
 document.execCommand('copy');})()""", MAIN)
H.spin(300)
check("the site's own copy handler never runs",
      js(view, "window.stolen") == 0, js(view, "window.stolen"))

print("\n(6) the “Leave site?” box")
guard(leaveTrap=True)
view = page("/leave")
check("the page cannot set one", js(view, "String(window.onbeforeunload)")
      in ("null", "undefined"), js(view, "String(window.onbeforeunload)"))
check("and cannot listen for one either",
      js(view, "String(window.trapped)") in ("undefined", "0"),
      js(view, "String(window.trapped)"))
win.config["leaveTrapSites"] = ["127.0.0.1"]
win.refresh_guard_scripts()
view = page("/leave")
check("a site he named keeps its box",
      js(view, "String(window.onbeforeunload)") not in ("null", "undefined"),
      js(view, "String(window.onbeforeunload)"))
win.config["leaveTrapSites"] = []

print("\n(7) the signal, the place, and the APIs")
guard(gpc=True, noWebRTC=True)
win.config["fakePlaces"] = {"127.0.0.1": {"lat": 52.52, "lon": 13.4}}
win.config["blockApis"] = {"127.0.0.1": ["wasm", "webgl"]}
win.refresh_guard_scripts()
view = page("/a")
check("the page is told not to sell or share",
      js(view, "navigator.globalPrivacyControl") is True)
check("and do-not-track with it", js(view, "navigator.doNotTrack") == "1")
check("WebAssembly is gone",
      js(view, "String(typeof WebAssembly)") == "undefined")
check("so is WebGL", js(view, "String(typeof WebGLRenderingContext)")
      == "undefined")
check("and a canvas refuses a webgl context",
      js(view, "String(document.createElement('canvas')"
               ".getContext('webgl'))") == "null")
check("WebRTC is off", js(view, "String(typeof RTCPeerConnection)")
      in ("undefined",), js(view, "String(typeof RTCPeerConnection)"))
place = H.js(view, """new Promise(function(ok){
  navigator.geolocation.getCurrentPosition(function(p){
    ok(p.coords.latitude + ',' + p.coords.longitude); });
})""", MAIN)
H.spin(400)
check("the place is the one he typed in",
      win.fake_place("127.0.0.1") == {"lat": 52.52, "lon": 13.4},
      win.fake_place("127.0.0.1"))
win.config["blockApis"] = {}
win.config["fakePlaces"] = {}

print("\n(8) frames from other sites, and the site's own fonts")
guard(noFrames=True, localFonts=True)
view = page("/frames")
H.spin(500)
check("a frame from another host is taken out",
      js(view, "String(!!document.getElementById('other'))") == "false",
      js(view, "document.querySelectorAll('iframe').length"))
check("its own frame stays",
      js(view, "String(!!document.getElementById('own'))") == "true")
check("the local font stack is put on the page",
      js(view, "String(!!document.getElementById('guard-fonts'))") == "true")

print("\n(9) the sockets a page holds open")
guard(wsLog=True)
view = page("/ws")
H.spin(400)
rows = js(view, "JSON.stringify(window.__guardWs || [])")
check("the page wrote down the socket it opened",
      "127.0.0.1:1" in str(rows), rows)
got = {}
win.websockets(view, then=lambda r: got.setdefault("rows", r))
H.wait_for(lambda: "rows" in got, 4000)
check("and the browser can read that list",
      got.get("rows") and got["rows"][0]["url"].startswith("ws://"),
      got.get("rows"))

print("\n(10) the windows a page tried to open")
guard(popups=True)
view = page("/pop")
H.spin(400)
check("window.open gave the page nothing",
      js(view, "String(window.opened)") == "null",
      js(view, "String(window.opened)"))
got = {}
win.blocked_popups(view, then=lambda r: got.setdefault("rows", r))
H.wait_for(lambda: "rows" in got, 4000)
check("the attempt was written down", got.get("rows"), got)
menu = win.popup_menu(rows=got.get("rows") or [])
labels = [a.text() for a in menu.actions() if a.text()]
check("and the panel offers to open it", any("/a" in t for t in labels),
      labels)
check("with an always-allow for this site",
      any("127.0.0.1" in t for t in labels), labels)
win.config["popupSites"] = ["127.0.0.1"]
win.refresh_guard_scripts()
view = page("/pop")
H.spin(400)
check("a site he allowed is not touched at all",
      js(view, "String(window.__guardPopups)") == "undefined",
      js(view, "String(window.__guardPopups)"))
win.config["popupSites"] = []
check("an allowed window opens as a tab by default",
      win.popup_mode() == "tab")
win.config["popupMode"] = "window"
check("...or as a small window when he says so",
      win.popup_mode() == "window")
win.config["popupMode"] = "tab"

print("\n(11) cookie banners")
guard(banners=True)
view = page("/banner")
H.wait_for(lambda: js(view, "String(window.clicked)") == "no", 5000)
check("the reject button in a consent dialog is clicked",
      js(view, "String(window.clicked)") == "no",
      js(view, "String(window.clicked)"))
check("a decline button in an ordinary form is left alone",
      js(view, "String(window.clicked)") != "plain")

print("\n(12) hiding an element for good")
guard()
win.config["hideElements"] = {}
check("hiding one writes the rule down",
      win.hide_element(".advert", "127.0.0.1") == [".advert"])
win.refresh_guard_scripts()
view = page("/ad")
H.spin(400)
check("and the element is not drawn",
      js(view, """(function(){var e=document.querySelector('.advert');
        return e ? getComputedStyle(e).display : 'gone';})()""") == "none",
      js(view, """(function(){var e=document.querySelector('.advert');
        return e ? getComputedStyle(e).display : 'gone';})()"""))
check("the rest of the page is untouched",
      js(view, "document.getElementById('p').textContent") == "text")
check("it is listed for this site",
      win.hidden_elements("127.0.0.1") == [".advert"])
win.hide_element(".advert", "127.0.0.1", on=False)
H.spin(300)
check("and taking it off leaves nothing behind",
      win.hidden_elements("127.0.0.1") == [])
check("the open page is put back at once",
      js(view, """(function(){var e=document.querySelector('.advert');
        return e ? getComputedStyle(e).display : 'gone';})()""") == "block",
      js(view, """(function(){var e=document.querySelector('.advert');
        return e ? getComputedStyle(e).display : 'gone';})()"""))

print("\n(13) https only")
win.config["httpsOnly"] = True
check("an http address is moved to https",
      win.https_upgrade(QUrl("http://example.com/x")).toString()
      == "https://example.com/x")
check("the home network is left alone",
      win.https_upgrade(QUrl("http://192.168.1.1/")) is None)
check("and so is localhost",
      win.https_upgrade(QUrl("http://127.0.0.1:8000/")) is None)
check("an https address needs nothing",
      win.https_upgrade(QUrl("https://example.com/")) is None)
win.toggle_site_rule("httpsExempt", "insecure.test")
check("a site he excused is left on http",
      win.https_upgrade(QUrl("http://insecure.test/")) is None)
check("he can say carry on once", win.allow_http_once("example.com")
      and win.http_allowed("example.com"))
check("and that is not remembered for another host",
      not win.http_allowed("other.test"))
win.config["httpsOnly"] = False

print("\n(14) a page that redirects a tab he is not on")
win.config["redirectGuard"] = True
a = page("/a")
b = page("/a")
win.tabs.setCurrentIndex(win.tabs.indexOf(b))
H.spin(200)
kinds = B.QWebEnginePage.NavigationType
check("a redirect inside the same site is fine",
      win.redirect_is_wanted(a, QUrl(srv.url("/b")),
                             kinds.NavigationTypeRedirect))
check("a redirect he clicked for is fine",
      win.redirect_is_wanted(a, QUrl("https://elsewhere.test/"),
                             kinds.NavigationTypeLinkClicked))
check("a redirect to another site out of a background tab is not",
      not win.redirect_is_wanted(a, QUrl("https://elsewhere.test/"),
                                 kinds.NavigationTypeRedirect))
check("the same thing in the tab he is looking at is allowed",
      win.redirect_is_wanted(b, QUrl("https://elsewhere.test/"),
                             kinds.NavigationTypeRedirect))
check("and it was written down", win._blocked_redirects, win._blocked_redirects)
win.config["redirectGuard"] = False

print("\n(15) a download from somewhere else")


class FakeRequest:
    def __init__(self, url, page_url):
        self._url = QUrl(url)
        self._page = type("P", (), {"url": lambda s: QUrl(page_url)})()

    def url(self):
        return self._url

    def page(self):
        return self._page


check("a file from another site is named",
      win.download_from_elsewhere(
          FakeRequest("https://files.other/x.zip", "https://site.test/p"))
      == "files.other")
check("a file from the site itself is not",
      win.download_from_elsewhere(
          FakeRequest("https://site.test/x.zip", "https://site.test/p")) == "")
check("nor one from its own sub-domain",
      win.download_from_elsewhere(
          FakeRequest("https://dl.site.test/x.zip", "https://site.test/p"))
      == "")

print("\n(16) tabs that are never saved")
win.toggle_site_rule("noRestoreSites", "secret.test")
check("a site can be left out of the session",
      win.restore_excluded("https://secret.test/x"))
check("and another one is not", not win.restore_excluded("https://gnu.org/"))
hidden = win.new_tab(url="https://secret.test/x", lazy=True, switch=False)
H.spin(300)
win._save_groups(quiet=False)
saved = json.dumps(win.config.get("sessionTabs", {}))
check("so it is not in what was written down", "secret.test" not in saved,
      saved[:120])
win.close_tab(win.tabs.indexOf(hidden), ask=False)

print("\n(17) working offline")
check("it goes on", win.work_offline(True) is True and win.offline_now())
view = win.new_tab(url=None)
H.spin(200)
before = view.url().toString()
H.load(view, srv.url("/a"))
H.spin(600)
check("and nothing new is loaded",
      not view.url().toString().endswith("/a"),
      view.url().toString())
check("it goes off again", win.work_offline(False) is False)
H.load(view, srv.url("/a"))
H.spin(600)
check("and then it loads", view.url().toString().endswith("/a"),
      view.url().toString())

print("\n(18) the flags the engine only hears at launch")
check("nothing asked for, no flags", B._privacy_flags({}) == ())
flags = B._privacy_flags({"blockPings": True, "noSpeculative": True,
                          "siteIsolation": True, "webrtcGuard": True,
                          "trimReferrer": "none"})
check("each switch is one flag", "--no-pings" in flags
      and "--no-referrers" in flags and "--site-per-process" in flags
      and "--dns-prefetch-disable" in flags, flags)
check("the WebRTC one is the narrow one",
      any("default_public_interface_only" in f for f in flags), flags)
doh = B._privacy_flags({"doh": True,
                        "dohUrl": "https://dns.example/dns-query"})
check("encrypted DNS carries its provider",
      any("dns-over-https-templates=https://dns.example" in f for f in doh),
      doh)
check("and an address that is not https is refused",
      B._privacy_flags({"doh": True, "dohUrl": "http://dns.example"}) == ())
blocked = B._privacy_flags({"blockHosts": ["Ads.Example.com", "bad host"]})
check("a blocked domain becomes a resolver rule",
      any("MAP ads.example.com 0.0.0.0" in f for f in blocked), blocked)
check("and junk in the list is dropped",
      not any("bad host" in f for f in blocked), blocked)
replay = B._privacy_flags({"blockReplay": True})
check("the session recorders are blocked by name",
      any("hotjar.com" in f for f in replay), replay[:1])
(scratch / "phishing-hosts.txt").write_text(
    "# mine\nbad.example\nAlso-Bad.example\nnot a host\n")
check("his own phishing list is read off the disk",
      B._phishing_hosts() == ["bad.example", "also-bad.example"],
      B._phishing_hosts())
phish = B._privacy_flags({"phishingList": True})
check("and goes into the same rule",
      any("bad.example" in f for f in phish), phish)
check("offline asks for a proxy nothing answers",
      any("proxy-server=127.0.0.1:1" in f
          for f in B._privacy_flags({"offline": True})))
check("the browser can say what is still waiting for a restart",
      win.privacy_flags_wanted() == B._privacy_flags(win.config))

print("\n(19) one language")
win.config["oneLanguage"] = True
win.config["translateLang"] = "de"
win.apply_language()
check("Accept-Language carries one language only",
      win.profile.httpAcceptLanguage() == "de",
      win.profile.httpAcceptLanguage())
win.config["oneLanguage"] = False
win.apply_language()
check("and both again when he switches it off",
      win.profile.httpAcceptLanguage() == "de,en",
      win.profile.httpAcceptLanguage())
win.config["translateLang"] = "en"
win.apply_language()

print("\n(20) a private tab keeps itself out of things")
priv = win.new_private_tab()
H.load(priv, srv.url("/a"))
H.spin(400)
check("it is not captured", not win.shot_allowed(priv))
check("...and nothing is produced", win.shot_visible(view=priv) is None)
win.config["shotPrivate"] = True
check("unless he says so", win.shot_allowed(priv))
win.config["shotPrivate"] = False
win._audible = priv
check("it never appears in the media list", win._audible_view() is None)
win.config["privateNoMedia"] = False
check("...unless he switches that off too", win._audible_view() is priv)
win.config["privateNoMedia"] = True
win._audible = None
win.close_tab(win.tabs.indexOf(priv), ask=False)

print("\n(21) what a link really is")
line = win.link_preview(
    "https://www.google.com/url?q=https%3A%2F%2Fgnu.org%2Fx")
check("a wrapper says where it really goes", "gnu.org" in line, line)
plain = win.link_preview(srv.url("/a"))
check("an ordinary link is just itself", plain == srv.url("/a"), plain)
short = H.Server({"/s": "<title>S</title>short"})
got = {}
win.expand_short_link(short.url("/s"), then=lambda w: got.setdefault("to", w))
H.wait_for(lambda: "to" in got, 6000)
check("a link that does not redirect resolves to nothing",
      got.get("to") == "", got)
short.stop()

print("\n(22) the summary at a start")
win.config["guardGpc"] = True
win.config["privacySnapshot"] = []
changed = win.privacy_changed_since()
check("it knows what is newly on", "gpc" in changed["on"], changed)
lines = win.check_privacy_at_start()
check("and says so once", lines, lines)
check("the list is written down for the next start",
      "gpc" in win.config["privacySnapshot"], win.config["privacySnapshot"])
check("a second look has nothing to say",
      win.check_privacy_at_start() == [])
win.config["privacyCheck"] = False
win.config["guardBanners"] = True
check("and nothing at all when he switched the summary off",
      win.check_privacy_at_start() == [])
win.config["privacyCheck"] = True

print("\n(23) the menu")
menu = win.guard_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("every guard is in the menu", len(labels) >= len(PG.GUARDS), labels)
rows = [a for a in menu.actions() if a.text()]
check("every guard is a switch",
      all(a.isCheckable() for a in rows[:len(PG.GUARDS)]),
      [a.text() for a in rows[:len(PG.GUARDS)] if not a.isCheckable()])
win.tabs.setCurrentIndex(win.tabs.indexOf(page("/a")))
H.spin(200)
menu = win.guard_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("and on a real page it offers this site's exceptions",
      any("127.0.0.1" in t for t in labels), labels)
priv_menu = win.privacy_menu()
subs = [a.text() for a in priv_menu.actions() if a.text()]
check("the privacy menu carries the guards and the blocked windows",
      any(win._ui_str("guardMenu") == t for t in subs)
      and any(win._ui_str("popupBlocked") == t for t in subs), subs)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
