#!/usr/bin/env python3
"""What is kept, who it says you are, and what the connection is: the
cookie rules, the permission overview, the certificates, the sites that
have stored something, the window lock.

Offscreen, scratch data, local pages. The certificate code is driven
against this machine (a port nothing is listening on, and a stub for
the handshake itself), so no part of this test goes near the web."""
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
    "/store": """<title>Store</title><script>
      try { localStorage.setItem('k', 'x'.repeat(100)); } catch (e) {}
      </script>""",
    "/media": "<title>Media</title><p>media</p>",
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


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(300)
    return view


print("\n(1) what a site may keep")
check("every site may keep its cookies by default",
      win.cookie_rule("example.com") == "allow")
check("one can be told to keep them until close",
      win.cookie_rule("example.com", "close") == "close")
check("...or not to keep them at all",
      win.cookie_rule("ads.example", "block") == "block")
check("nonsense is not a rule",
      win.cookie_rule("example.com", "maybe") == "close")
check("a rule covers the site's own sub-domains",
      win.cookie_rule_for("shop.example.com") == "close",
      win.cookie_rule_for("shop.example.com"))
check("and a cookie domain with a leading dot",
      win.cookie_rule_for(".ads.example") == "block")
check("another site is not covered",
      win.cookie_rule_for("gnu.org") == "allow")
check("back to allow takes the rule out",
      win.cookie_rule("example.com", "allow") == "allow"
      and "example.com" not in win.cookie_rules())


class FakeCookie:
    def __init__(self, name, domain):
        self._name = name
        self._domain = domain

    def name(self):
        return self._name.encode()

    def domain(self):
        return self._domain


class FakeStore:
    def __init__(self):
        self.deleted = []

    def deleteCookie(self, cookie):
        self.deleted.append(cookie.domain())


store = FakeStore()
before = win._cookies_blocked
check("a blocked site's cookie is deleted the moment it arrives",
      win._cookie_arrived(store, FakeCookie("id", ".ads.example"))
      and store.deleted == [".ads.example"], store.deleted)
check("and counted", win._cookies_blocked == before + 1)
win.cookie_rule("keeper.test", "close")
check("a keep-until-close cookie is let through",
      not win._cookie_arrived(store, FakeCookie("sid", "keeper.test")))
check("...and its site written down for the clear at close",
      "keeper.test" in win._cookies_until_close,
      win._cookies_until_close)
check("an ordinary cookie is nobody's business",
      not win._cookie_arrived(store, FakeCookie("x", "gnu.org")))
check("clearing at close empties the list",
      win.clear_until_close() == 1 and not win._cookies_until_close)

print("\n(2) what sites may do")
win.config["permissions"] = {"https://a.test|use the camera": True,
                             "https://b.test|know where you are": True}
win.config["permissionTimes"] = {}
rows = win.permission_rows()
check("every allowed thing is a row", len(rows) == 2, rows)
check("each row says the site and what it may do",
      rows[0]["origin"] == "https://a.test"
      and rows[0]["what"] == "use the camera", rows[0])
win.note_permission("https://a.test|use the camera", True, "used")
check("using one is written down",
      win.permission_rows()[0]["used"] > 0, win.permission_rows()[0])
check("and it is in the log",
      any(r["what"] == "used" for r in win.permission_log()),
      win.permission_log(3))
check("one can be taken back",
      win.revoke_permission("https://a.test|use the camera"))
check("...and is gone", len(win.permission_rows()) == 1)
check("taking back something that is not there says so",
      not win.revoke_permission("https://nothing.test|x"))
win.config["permissions"]["https://old.test|use the microphone"] = True
win.config["permissionTimes"]["https://old.test|use the microphone"] = {
    "t": int(time.time()) - 400 * 86400,
    "used": int(time.time()) - 400 * 86400}
check("an unused permission expires after the days he set",
      win.prune_permissions(days=30) == 1, win.permission_rows())
check("0 days means they never expire", win.prune_permissions(days=0) == 0)
check("and everything can go at once",
      win.revoke_all_permissions() == 1 and not win.permission_rows())

print("\n(3) allow, deny, and “this time”")


class FakePermission:
    def __init__(self):
        self.answered = ""

    def grant(self):
        self.answered = "grant"

    def deny(self):
        self.answered = "deny"


def ask(storable=True, private=False):
    perm = FakePermission()
    win._perm_queue.append((perm, None, "a.test", "use the camera",
                            "https://a.test|use the camera",
                            "https://a.test", storable, private))
    win._next_permission()
    H.spin(150)
    card = win._perm_widget
    buttons = card.findChildren(B.QToolButton) if card is not None else []
    return perm, card, buttons


win.config["permissions"] = {}
perm, card, buttons = ask()
labels = [b.text() for b in buttons]
check("the card offers three answers", len(buttons) == 3, labels)
check("one of them is “this time”",
      win._ui_str("permOnce") in labels, labels)
once = [b for b in buttons if b.text() == win._ui_str("permOnce")][0]
once.click()
H.spin(200)
check("it grants", perm.answered == "grant")
check("but is not remembered", not win.config.get("permissions"),
      win.config.get("permissions"))
check("and not even for this run",
      "https://a.test|use the camera" not in win._session_perms,
      win._session_perms)
check("the log says it was a one-off",
      any(r["what"] == "once" for r in win.permission_log()),
      win.permission_log(3))
perm, card, buttons = ask()
allow = [b for b in buttons if b.text() == win._ui_str("permAllow")][0]
allow.click()
H.spin(200)
check("a plain allow is remembered",
      win.config.get("permissions", {}).get(
          "https://a.test|use the camera") is True,
      win.config.get("permissions"))
perm, card, buttons = ask(storable=False)
check("a page with no origin worth the name gets no “this time”",
      len(buttons) == 2, [b.text() for b in buttons])
[b for b in buttons if b.text() == win._ui_str("permDeny")][0].click()
H.spin(200)
check("...and a deny is a deny", perm.answered == "deny")

print("\n(4) which tab is using a device")
win.config["guardMediaLog"] = True
win.refresh_guard_scripts()
view = page("/media")
check("getUserMedia is not the engine's own any more",
      "native code" not in str(H.js(
          view, "String(navigator.mediaDevices.getUserMedia)", MAIN)),
      H.js(view, "String(navigator.mediaDevices.getUserMedia)", MAIN)[:40])
check("the page has a note to write into",
      H.js(view, "JSON.stringify(window.__guardMedia)", MAIN) == "[]")
H.js(view, "window.__guardMedia = ['camera','microphone']", MAIN)
got = {}
win.media_users(then=lambda rows: got.setdefault("rows", rows))
H.wait_for(lambda: "rows" in got, 4000)
kinds = sorted(r["kind"] for r in got.get("rows", []))
check("the browser reads it", kinds == ["camera", "microphone"], kinds)
win._media_seen(got["rows"])
check("the mark in the bar goes up",
      win._mediabtn.isVisible() or win._media_live, win._media_live)
menu = win.media_use_menu()
check("and offers to stop each one",
      len([a for a in menu.actions() if a.text()]) == 2,
      [a.text() for a in menu.actions()])
check("stopping tells the page to stop", win.stop_media_use(view))
H.spin(300)
check("...and the note is empty again",
      H.js(view, "JSON.stringify(window.__guardMedia)", MAIN) == "[]",
      H.js(view, "JSON.stringify(window.__guardMedia)", MAIN))
win._media_seen([])
check("the mark goes away", not win._mediabtn.isVisible())
win.config["guardMediaLog"] = False
win.refresh_guard_scripts()

print("\n(5) a browser that keeps nothing")
sid = win.add_throwaway_session()
H.spin(300)
check("it is a virtual browser like any other",
      any(e["sid"] == sid for e in win.sessions))
check("and it is marked as a throwaway", win.session_is_throwaway(sid))
profile = win._session_profile(sid)
check("its cookie jar has nowhere to write", profile.isOffTheRecord(),
      profile.isOffTheRecord())
check("the main one still has", not win.profile.isOffTheRecord())
win.switch_session("main")
H.spin(200)
win.toggle_site_rule("cleanRoomSites", "bank.test")
check("a site can be given a clean room",
      win.clean_room_for("https://bank.test/login"))
check("and another one not",
      not win.clean_room_for("https://gnu.org/"))
rooms = len(win.throwaway_sessions())
room_tab = win.open_clean_room("https://bank.test/login")
H.spin(400)
check("opening one makes a fresh browser for it",
      len(win.throwaway_sessions()) == rooms + 1)
check("and the tab is in it",
      win.session_is_throwaway(getattr(room_tab, "session", "")),
      getattr(room_tab, "session", None))
win.switch_session("main")
H.spin(200)

print("\n(6) the certificate, and the connection")
info = win.certificate_for("127.0.0.1", port=1)
check("a port nothing answers on says what went wrong",
      info.get("error"), info)
check("a host with no name at all gives nothing",
      win.certificate_for("") == {})
win.certificate_for = lambda host, port=443, timeout=4.0: {
    "host": host, "sha256": "aa" * 32, "subject": host, "issuer": "Me",
    "from": "x", "until": "y", "tls": "TLSv1.3", "cipher": "C",
    "ip": "127.0.0.1", "names": [host], "serial": "1"}
first = win.check_certificate("own.test")
check("the first look just writes the fingerprint down",
      first["first"] and not first["changed"], first)
same = win.check_certificate("own.test")
check("the same certificate is not a change",
      not same["changed"] and not same["first"])
win.certificate_for = lambda host, port=443, timeout=4.0: {
    "host": host, "sha256": "bb" * 32, "subject": host, "issuer": "Me",
    "from": "x", "until": "y", "tls": "TLSv1.3", "cipher": "C",
    "ip": "127.0.0.1", "names": [host], "serial": "2"}
changed = win.check_certificate("own.test")
check("a different one is", changed["changed"], changed)
check("nothing is trusted to start with",
      not win.certificate_excepted("printer.test"))
check("one can be trusted for good",
      win.trust_certificate("printer.test", "cc" * 32))
check("...and is", win.certificate_excepted("printer.test", "cc" * 32))
check("but not a different certificate on the same host",
      not win.certificate_excepted("printer.test", "dd" * 32))
check("and it can be forgotten",
      win.forget_certificate_exception("printer.test")
      and not win.certificate_excepted("printer.test"))


class FakeCertError:
    def __init__(self, host, overridable=True):
        self._url = QUrl("https://%s/x" % host)
        self._over = overridable

    def url(self):
        return self._url

    def description(self):
        return "self signed certificate"

    def isOverridable(self):
        return self._over


asked = []
real_q = B.QMessageBox.question
B.QMessageBox.question = lambda *a, **k: (
    asked.append(a[1]) or B.QMessageBox.StandardButton.Yes)
check("a certificate the engine refuses is put to him",
      win.certificate_error(FakeCertError("printer.test"))
      and len(asked) == 1, asked)
check("...and saying yes trusts that one",
      win.certificate_excepted("printer.test"))
check("the next time it is not asked again",
      win.certificate_error(FakeCertError("printer.test"))
      and len(asked) == 1)
B.QMessageBox.question = lambda *a, **k: (
    asked.append(a[1]) or B.QMessageBox.StandardButton.No)
check("saying no means the page does not load",
      not win.certificate_error(FakeCertError("other.test")))
check("and one the engine says cannot be overridden is never offered",
      not win.certificate_error(FakeCertError("hard.test",
                                              overridable=False))
      and len(asked) == 2, len(asked))
B.QMessageBox.question = real_q
details = win.connection_details("localhost")
check("the connection says what the name resolved to",
      "127.0.0.1" in details.get("ip", ""), details)
check("and whether a proxy rule covers it", "proxy" in details, details)

print("\n(7) insecure parts, storage and workers")
view = page("/store")
H.spin(400)
got = {}
win.mixed_content(view, then=lambda rows: got.setdefault("mixed", rows))
H.wait_for(lambda: "mixed" in got, 4000)
check("an http page is not asked about mixed content",
      got.get("mixed") == [], got)
got = {}
win.storage_sizes(view, then=lambda out: got.setdefault("size", out))
H.wait_for(lambda: "size" in got, 4000)
check("what a page put in local storage is counted",
      got.get("size", {}).get("local", 0) > 100, got)
check("and how many keys it used", got["size"]["keys"] == 1, got)
got = {}
win.service_workers(view, then=lambda rows: got.setdefault("sw", rows))
H.wait_for(lambda: "sw" in got, 5000)
check("a page with no service worker says so", got.get("sw") == [], got)
check("...and that answer came from the page, not from a promise "
      "nobody could read",
      isinstance(got.get("sw"), list), got)
dropped = []
win.drop_service_workers(view, then=dropped.append)
H.wait_for(lambda: dropped, 5000)
check("dropping them answers how many there were",
      dropped and str(dropped[0]) in ("0", "none"), dropped)
check("and dropping them is still a safe thing to ask",
      win.drop_service_workers(view))

print("\n(8) the sites he only passed through")
win._cookies = {("id", "tracker.test"): "", ("sid", "gnu.org"): ""}
win.history = [{"url": "https://gnu.org/a", "title": "Gnu",
                "t": int(time.time())}]
win.note_redirect_hop("tracker.test")
win.note_redirect_hop("tracker.test")
win.note_redirect_hop("gnu.org")
rows = win.bounce_hosts()
check("a site he only passed through and that stored something is listed",
      [r["host"] for r in rows] == ["tracker.test"], rows)
check("with how many times", rows[0]["hops"] == 2, rows)
check("a site he actually read is not listed",
      not any(r["host"] == "gnu.org" for r in rows))
win.note_redirect_hop("nothing.test")
check("nor one that stored nothing",
      not any(r["host"] == "nothing.test" for r in win.bounce_hosts()))
check("cleaning them clears what they left",
      win.clean_bounce_trackers() == 1)
check("and takes them off the list", win.bounce_hosts() == [])

print("\n(9) who is logged in")
win._cookies = {("sessionid", "forum.test"): "",
                ("auth_token", "shop.test"): "",
                ("lang", "plain.test"): ""}
rows = win.logged_in_sites()
check("the sites with a login-looking cookie are named",
      sorted(r["host"] for r in rows) == ["forum.test", "shop.test"], rows)
check("one with only a language cookie is not",
      not any(r["host"] == "plain.test" for r in rows))
check("and signing out of one is offered", win.sign_out_site("forum.test"))

print("\n(10) what each site has stored")
rows = win.site_data_rows()
check("every site that put a cookie down is a row", len(rows) == 3, rows)
check("with how many and which", rows[0]["cookies"] == 1
      and rows[0]["names"], rows[0])

print("\n(11) sites that want to handle a kind of link")


class FakeHandler:
    def __init__(self, scheme, origin):
        self._scheme = scheme
        self._origin = QUrl(origin)
        self.answer = ""

    def scheme(self):
        return self._scheme

    def origin(self):
        return self._origin

    def accept(self):
        self.answer = "accept"

    def reject(self):
        self.answer = "reject"


B.QMessageBox.question = lambda *a, **k: B.QMessageBox.StandardButton.No
handler = FakeHandler("mailto", "https://mail.test")
check("a site asking is refused when he says no",
      not win.protocol_handler_asked(handler)
      and handler.answer == "reject", handler.answer)
check("and the answer is written down",
      win.protocol_handlers().get("mailto|https://mail.test") is False,
      win.protocol_handlers())
B.QMessageBox.question = lambda *a, **k: B.QMessageBox.StandardButton.Yes
handler = FakeHandler("web+mod", "https://mods.test")
check("and accepted when he says yes",
      win.protocol_handler_asked(handler) and handler.answer == "accept")
again = FakeHandler("web+mod", "https://mods.test")
check("the next time it is not asked again",
      win.protocol_handler_asked(again) and again.answer == "accept")
check("one can be taken off the list",
      win.remove_protocol_handler("web+mod|https://mods.test"))
B.QMessageBox.question = real_q

print("\n(12) the window, locked")
check("there is no lock until he sets one", not win.browser_lock_set())
check("locking without a word does nothing", not win.lock_browser())
check("setting one works", win.set_browser_lock("open sesame"))
check("and is stored as a hash, not the word",
      "open sesame" not in json.dumps(win.config),
      [k for k in win.config if "lock" in k.lower()])
check("the right word is accepted", win.check_browser_lock("open sesame"))
check("a wrong one is not", not win.check_browser_lock("open seseme"))
check("the window locks", win.lock_browser() and win.locked_now())
box = win._lock_cover.findChild(B.QLineEdit, "lockinput")
check("there is a box to type in", box is not None)
box.setText("wrong")
box.returnPressed.emit()
H.spin(150)
check("a wrong word keeps it locked", win.locked_now())
box.setText("open sesame")
box.returnPressed.emit()
H.spin(150)
check("the right one opens it", not win.locked_now())
win.config["lockAfter"] = 1
win._last_touch = time.monotonic() - 120
check("and it locks itself after a while idle", win._lock_tick()
      and win.locked_now())
win.unlock_browser()
win.config["lockAfter"] = 0
check("taking the word off takes the lock off",
      win.set_browser_lock("") is False and not win.browser_lock_set())

print("\n(13) the privacy rules as one file")
win.config["httpsOnly"] = True
win.config["guardGpc"] = True
win.config["cookieRules"] = {"ads.example": "block"}
out = scratch / "privacy.json"
wrote = win.export_privacy(out)
check("the rules are written out", wrote >= 3, wrote)
saved = json.loads(out.read_text())
check("the switches are in it", saved.get("httpsOnly") is True)
check("the guards too", saved.get("guardGpc") is True)
check("and the per-site rules",
      saved.get("cookieRules") == {"ads.example": "block"})
check("nothing else of the config goes with them",
      "zoom" not in saved and "theme" not in saved, sorted(saved)[:6])
win.config["httpsOnly"] = False
win.config["cookieRules"] = {}
taken = win.import_privacy(out)
check("reading it back takes the rules", taken >= 3, taken)
check("...and they are in force again", win.config["httpsOnly"] is True
      and win.cookie_rule("ads.example") == "block")
(scratch / "other.json").write_text(json.dumps({"zoom": 3,
                                                "httpsOnly": False}))
check("a file with other settings in it only gives up the privacy ones",
      win.import_privacy(scratch / "other.json") == 1
      and win.config.get("zoom") != 3, win.config.get("zoom"))
check("and junk is no rules at all",
      win.import_privacy(scratch / "nope.json") == 0)

print("\n(14) what each virtual browser wipes on the way out")
check("nothing, until he says", win.clear_on_exit_for("main") == [])
check("it takes the kinds he names",
      win.clear_on_exit_for("main", ["cookies", "cache", "nonsense"])
      == ["cookies", "cache"],
      win.clear_on_exit_for("main"))
win.history = [{"url": "https://x.test/a", "title": "x",
                "t": int(time.time()), "s": "two"},
               {"url": "https://y.test/a", "title": "y",
                "t": int(time.time())}]
win.sessions.append({"name": "Two", "sid": "two"})
win.clear_on_exit_for("two", ["history"])
win._session_profile("two")
done = win.clear_on_exit_per_session()
check("and does them", done >= 1, done)
check("one browser's history goes without touching the other's",
      [e["url"] for e in win.history] == ["https://y.test/a"], win.history)
win.clear_on_exit_for("main", [])
win.clear_on_exit_for("two", [])

print("\n(15) the count in the bar")
win.config["trackerBadge"] = True
win._cookies_blocked = 3
label = win.tracker_badge()
check("the badge shows what was refused",
      label is not None and label.isVisible() and label.text() == "3",
      label.text() if label is not None else None)
win.config["trackerBadge"] = False
check("and is off unless he asks for it",
      not win.tracker_badge().isVisible())

print("\n(16) the menus")
for name, builder in (("cookies", win.cookie_menu),
                      ("permissions", win.permissions_menu),
                      ("certificate", win.certificate_menu),
                      ("what is stored", win.storage_menu)):
    menu = builder()
    check("the %s menu is built" % name,
          len([a for a in menu.actions() if a.text()]) >= 1,
          [a.text() for a in menu.actions()][:3])
priv = win.privacy_menu()
labels = [a.text() for a in priv.actions() if a.text()]
check("and the privacy menu carries them all",
      win._ui_str("cookieRule") in labels
      and win._ui_str("permOverview") in labels
      and win._ui_str("dataMenu") in labels, labels)
ids = {e["id"] for e in win.actions_list()}
for want in ("lockwindow", "cleanroom", "throwaway", "certificate",
             "permissions", "sitedata", "exportprivacy", "importprivacy"):
    check("the registry knows " + want, want in ids)
keys = {}
for entry in win.actions_list():
    key = win.shortcut_for(entry["id"], entry["key"])
    if key:
        keys.setdefault(key, []).append(entry["id"])
clash = {k: v for k, v in keys.items() if len(v) > 1}
check("and no two actions want the same key", not clash, clash)

print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
