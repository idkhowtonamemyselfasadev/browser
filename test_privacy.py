#!/usr/bin/env python3
"""Privacy: the request interceptor, the per-site switches, forgetting a
site, the panic key and streamer mode.

The interceptor runs on the engine's own thread for every request, so
most of it is tested the way the engine uses it — a request object in,
blocked or redirected out — rather than by loading pages and hoping. The
per-site switches are tested on real pages, because that is where they
could be quietly ignored."""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
import privacy  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


print("\n(1) the plain questions")
check("a tracking parameter comes off",
      privacy.strip_tracking("https://x.de/a?utm_source=mail&id=3")
      == "https://x.de/a?id=3",
      privacy.strip_tracking("https://x.de/a?utm_source=mail&id=3"))
check("several come off at once",
      privacy.strip_tracking("https://x.de/?fbclid=1&gclid=2&q=keep")
      == "https://x.de/?q=keep")
check("an address with nothing to take off is handed back as it was",
      privacy.strip_tracking("https://x.de/a?id=3")
      == "https://x.de/a?id=3")
check("the page's own parameters are kept",
      "th=1" in privacy.strip_tracking("https://amazon.de/dp/X?th=1&utm_id=9"))
for host, local in (("localhost", True), ("127.0.0.1", True),
                    ("192.168.1.50", True), ("10.0.0.5", True),
                    ("fritz.box", False), ("printer.local", True),
                    ("example.com", False), ("8.8.8.8", False)):
    check("%s is %slocal" % (host, "" if local else "not "),
          privacy.is_local(host) == local, privacy.is_local(host))
check("a sub-domain is matched by its domain",
      privacy.matches("ads.doubleclick.net", privacy.DEFAULT_BLOCK))
check("a look-alike is not",
      not privacy.matches("notdoubleclick.net", privacy.DEFAULT_BLOCK))
check("www. is ignored on both sides",
      privacy.matches("www.criteo.com", ["criteo.com"]))


class FakeConfig(dict):
    pass


def ask(url, page, **config):
    """What check_request says about one navigation."""
    from PyQt6.QtCore import QUrl as U
    allow, want = privacy.check_request(FakeConfig(config), U(url), U(page))
    return allow, want.toString()


print("\n(2) what a page may navigate to")
allow, _ = ask("http://192.168.1.1/admin", "https://news.de/", blockLocal=True)
check("a website may not reach the home network", not allow)
allow, _ = ask("http://127.0.0.1:8123/api", "https://news.de/", blockLocal=True)
check("...nor this machine", not allow)
allow, _ = ask("http://printer.local/", "https://news.de/", blockLocal=True)
check("...nor a .local name", not allow)
allow, _ = ask("http://192.168.1.1/admin", "http://192.168.1.5/",
               blockLocal=True)
check("but one local page may reach another", allow)
allow, _ = ask("http://192.168.1.1/x", "https://news.de/", blockLocal=False)
check("and nothing is stopped while that is off", allow)
allow, _ = ask("https://news.de/a", "https://news.de/", blockLocal=True)
check("an ordinary page is an ordinary page", allow)

allow, want = ask("https://news.de/a?utm_source=x&id=1", "https://news.de/",
                  stripTracking=True)
check("the tracking is taken off on the way out",
      allow and want == "https://news.de/a?id=1", want)
allow, want = ask("https://news.de/a?id=1", "https://news.de/",
                  stripTracking=True)
check("a clean address is left alone", want.endswith("?id=1"), want)
allow, want = ask("https://news.de/a?utm_source=x", "https://news.de/",
                  stripTracking=False)
check("...and nothing is cleaned while that is off",
      "utm_source" in want, want)
allow, want = ask("mailto:someone@example.com", "https://news.de/",
                  blockLocal=True, stripTracking=True)
check("a non-web address is none of its business", allow)

print("\n(3) the report")
# (the browser's own counters are checked below, on the real window)

print("\n(5) the per-site switches, on real pages")
app = H.app()
SCRIPTED = ("<!doctype html><title>plain</title><p id=p>no script ran</p>"
            "<img id=i src='data:image/svg+xml;utf8,<svg xmlns=\"http://"
            "www.w3.org/2000/svg\" width=\"40\" height=\"40\"><rect width="
            "\"40\" height=\"40\" fill=\"red\"/></svg>'>"
            "<script>document.getElementById('p').textContent="
            "'the script ran';document.title='scripted'</script>")
srv = H.Server({"/s": SCRIPTED})
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(900, 700)
win.show()
H.spin(400)
view = win.new_tab(url=None)

H.load(view, srv.url("/s"))
check("the page's script runs to begin with",
      H.js(view, "document.getElementById('p').textContent",
           B.MAIN_WORLD_ID) == "the script ran")
win.toggle_site_rule("noScriptSites", "127.0.0.1")
check("the site is on the list now",
      win.site_rule_on("noScriptSites", "127.0.0.1"))
H.load(view, srv.url("/s"))
H.spin(400)
check("and its script does not run any more",
      H.js(view, "document.getElementById('p').textContent",
           B.MAIN_WORLD_ID) is None
      or view.page().settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.JavascriptEnabled) is False,
      view.page().settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.JavascriptEnabled))
check("another host is untouched by that rule",
      not win.site_rule_on("noScriptSites", "localhost"))
win.toggle_site_rule("noScriptSites", "127.0.0.1")
H.load(view, srv.url("/s"))
H.spin(300)
check("taking it off the list brings the script back",
      H.js(view, "document.getElementById('p').textContent",
           B.MAIN_WORLD_ID) == "the script ran")

win.toggle_site_rule("noImageSites", "127.0.0.1")
H.load(view, srv.url("/s"))
H.spin(400)
check("images are off for that site",
      not view.page().settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.AutoLoadImages))
win.toggle_site_rule("noImageSites", "127.0.0.1")
H.load(view, srv.url("/s"))
H.spin(300)
check("and on again afterwards",
      view.page().settings().testAttribute(
          B.QWebEngineSettings.WebAttribute.AutoLoadImages))

print("\n(6) sites that are never written down")
win.history = []
win.known_hosts = set()
win.toggle_site_rule("noHistorySites", "127.0.0.1")
H.load(view, srv.url("/s"))
H.spin(500)
check("nothing was recorded for it", not win.history, win.history)
check("and the address bar does not learn the host either",
      "127.0.0.1" not in win.known_hosts, win.known_hosts)
win.toggle_site_rule("noHistorySites", "127.0.0.1")
H.load(view, srv.url("/s"))
H.spin(500)
check("an ordinary site still is", len(win.history) >= 1, len(win.history))

print("\n(7) forgetting a site")
win.history.append({"url": "https://forgetme.example/a", "title": "x", "t": 0})
win.known_hosts.add("forgetme.example")
win.config["permissions"] = {"https://forgetme.example|Notifications": True}
gone = win.forget_site("forgetme.example")
check("its pages are out of the history",
      not any("forgetme.example" in e["url"] for e in win.history), gone)
check("its permissions are gone",
      not any("forgetme.example" in k
              for k in win.config.get("permissions", {})))
check("and the address bar has forgotten it",
      "forgetme.example" not in win.known_hosts)

print("\n(8) the panic key and streamer mode")
win.urlbar.setText("something private")
win.panic()
H.spin(500)
check("the address bar is empty", win.urlbar.text() == "", win.urlbar.text())
check("every tab was sent somewhere blank",
      all(v.url().toString() in ("about:blank", "")
          for _, v in win._real_tabs()),
      [v.url().toString() for _, v in win._real_tabs()])
check("and everything is muted",
      all(v.page().isAudioMuted() for _, v in win._real_tabs()))
on = win.streamer_mode(True)
from PyQt6.QtWidgets import QLineEdit  # noqa: E402
check("streamer mode hides what is in the address bar",
      on and win.urlbar.echoMode() == QLineEdit.EchoMode.Password,
      win.urlbar.echoMode())
win.streamer_mode(False)
check("and gives it back",
      win.urlbar.echoMode() == QLineEdit.EchoMode.Normal,
      win.urlbar.echoMode())

print("\n(8b) the report counts what was refused and cleaned")
win.config["blockLocal"] = True
win.config["stripTracking"] = True
win._priv_report = None
H.load(view, srv.url("/s"))
H.spin(300)
before = win.privacy_report()
check("it starts at nothing",
      before.get("blocked") == 0 and before.get("stripped") == 0, before)
win.privacy_blocked("ads.example")
win.privacy_stripped()
after = win.privacy_report()
check("a refusal is counted", after.get("blocked") == 1, after)
check("a cleaned address too", after.get("stripped") == 1, after)
check("and the host is named",
      after.get("worst") == [("ads.example", 1)], after)

print("\n(9) the menu the page offers")
H.load(view, srv.url("/s"))
H.spin(300)
menu = win.privacy_menu()
labels = [a.text() for a in menu.actions()]
check("it names this site", any("127.0.0.1" in t for t in labels), labels[:3])
# the four rules for this site, by name: the menu has grown switches
# of its own since (work offline, and the guards under it), so a count
# of everything checkable says nothing about these four
wanted = [win._ui_str(k) % "127.0.0.1" for k in
          ("privNoScript", "privNoImages", "privAlways", "privNoHistory")]
check("it has the four per-site switches",
      all(any(a.text() == t and a.isCheckable() for a in menu.actions())
          for t in wanted),
      [t for t in wanted
       if not any(a.text() == t and a.isCheckable() for a in menu.actions())])
check("and says what was refused and cleaned",
      any("refused" in a.text() for a in menu.actions()),
      [a.text() for a in menu.actions()][-3:])

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
