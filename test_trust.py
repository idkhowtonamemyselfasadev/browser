#!/usr/bin/env python3
"""What a website can reach, proved rather than asserted.

Two halves:

* every keyed bridge slot, called with a key that is not this run's,
  must hand back nothing and change nothing;
* a page served over real HTTP must not see the full bridge at all —
  only the minimal `pw` object, and only in an isolated world.

Runs offscreen against scratch data; never touches your own vault.
"""
import http.server
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QUrl  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ---- a real web server, so this is a real remote origin ----
SITE = SCRATCH / "site"
SITE.mkdir(parents=True, exist_ok=True)
(SITE / "evil.html").write_text("""<!doctype html>
<meta charset="utf-8"><title>evil</title>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<body>a website</body>
""")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
server.RequestHandlerClass.directory = str(SITE)
Quiet.directory = str(SITE)
threading.Thread(target=server.serve_forever, daemon=True).start()
PORT = server.server_address[1]

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1100, 800)
win.show()

vault = win.vault
vault.add_item({"type": "login", "host": "bank.example", "username": "user",
                "password": "TOP-SECRET-NEVER-LEAK", "title": "Bank",
                "totp": "JBSWY3DPEHPK3PXP"})
vault.add_item({"type": "note", "title": "note", "body": "SECRET-NOTE-BODY"})
item = vault.logins()[0]
bridge = win.bridge
REAL = win._page_key
BOGUS = "0" * 32

print("\nevery keyed slot, called with a key that is not this run's")
before = json.dumps(vault.data, sort_keys=True)
check("getVault", bridge.getVault(BOGUS) == "{}")
check("revealField gives nothing",
      bridge.revealField(BOGUS, item["id"], "password") == "{}")
check("copyField gives nothing",
      bridge.copyField(BOGUS, item["id"], "password") == "{}")
check("totpFor gives nothing", bridge.totpFor(BOGUS, item["id"]) == "{}")
check("checkTotpSecret gives nothing",
      bridge.checkTotpSecret(BOGUS, "JBSWY3DPEHPK3PXP") == "{}")
check("saveItem changes nothing",
      bridge.saveItem(BOGUS, json.dumps({"type": "login", "host": "evil.com",
                                         "password": "x"})) == "{}")
check("deleteItem refuses", bridge.deleteItem(BOGUS, item["id"]) == "{}")
check("toggleFavourite refuses",
      bridge.toggleFavourite(BOGUS, item["id"]) == "{}")
check("generatePassword refuses",
      bridge.generatePassword(BOGUS, 20, True, True, True, False) == "")
check("removeNeverSiteKeyed refuses",
      bridge.removeNeverSiteKeyed(BOGUS, "x.com") == "{}")
check("importPasswords refuses (no file dialog opens)",
      bridge.importPasswords(BOGUS) == "{}")
check("exportPasswords refuses (no warning dialog opens)",
      bridge.exportPasswords(BOGUS) == "{}")
check("vaultProviders refuses", bridge.vaultProviders(BOGUS) == "[]")
check("the six unkeyed password slots are gone",
      not any(hasattr(bridge, n) for n in
              ("listPasswords", "revealPassword", "copyPassword",
               "setPassword", "deletePassword", "removeNeverSite")))
check("setVaultProvider refuses",
      bridge.setVaultProvider(BOGUS, "1password") == "{}")
check("setOpToken refuses (no dialog opens)", bridge.setOpToken(BOGUS) == "{}")
check("setOpVault refuses", bridge.setOpVault(BOGUS, "Evil") == "{}")
check("closePasswords does nothing", bridge.closePasswords(BOGUS) is None)
check("the vault is byte-for-byte unchanged",
      json.dumps(vault.data, sort_keys=True) == before)
check("provider was not switched",
      win.vault.provider.name == "file" and
      win.config.get("passwordProvider") in (None, "file"))
check("no 1Password vault name was set", not win.config.get("opVault"))

print("\nthe same slots with the real key do work")
data = json.loads(bridge.getVault(REAL))
check("getVault answers", len(data["items"]) == 2)
check("reveal answers",
      json.loads(bridge.revealField(REAL, item["id"], "password"))["value"]
      == "TOP-SECRET-NEVER-LEAK")
check("generator answers",
      len(bridge.generatePassword(REAL, 20, True, True, True, False)) == 20)
# a slot must not raise on whatever it is handed: this one used to put
# int() straight on a length that came in over the channel
check("a length that is not a number is a default, not a traceback",
      len(bridge.generatePassword(REAL, "", True, True, True, False)) == 20)
check("copyGenerated refuses a wrong key", bridge.copyGenerated(BOGUS) == "{}")
check("and says whether it really copied",
      json.loads(bridge.copyGenerated(REAL)).get("ok") is True)

print("\nno secret is in what the page is given")
blob = bridge.getVault(REAL)
check("no password in the listing", "TOP-SECRET-NEVER-LEAK" not in blob)
check("no note body in the listing", "SECRET-NOTE-BODY" not in blob)
check("no two-factor seed in the listing", "JBSWY3DPEHPK3PXP" not in blob)
check("but the page knows they exist",
      all(i.get("hasPassword") or i.get("hasBody") for i in data["items"]))

print("\nreveal only hands over fields an item actually has")
check("a made-up field gives nothing",
      json.loads(bridge.revealField(REAL, item["id"], "id"))["value"] == "")
check("a rejected key gets nothing the page can draw",
      bridge.getVault(BOGUS) == "{}")
check("another item's type of field gives nothing",
      json.loads(bridge.revealField(REAL, item["id"], "body"))["value"] == "")

# ---- and now a real page over real HTTP ----
url = "http://127.0.0.1:%d/evil.html" % PORT
win.new_tab(url=url)
view = win.current()

PROBE = """(function () {
  return JSON.stringify({
    world: %d,
    qt: typeof qt,
    transport: (typeof qt !== 'undefined' && !!qt.webChannelTransport),
    bridgeGlobal: typeof bridge,
    href: location.href
  });
})()"""

results = {}


def probe_world(world, name, then):
    def got(value):
        results[name] = json.loads(value)
        then()
    view.page().runJavaScript(PROBE % world, world, got)


def channel_objects(then):
    """What the isolated world's channel actually exposes. Built in two
    steps because runJavaScript does not wait on a promise: open the
    channel, then read what it found a moment later."""
    open_js = """
      window.__keys = "pending";
      new QWebChannel(qt.webChannelTransport, function (ch) {
        window.__keys = JSON.stringify(Object.keys(ch.objects).sort());
      });
      typeof QWebChannel;
    """

    def read():
        view.page().runJavaScript(
            "window.__keys", B.PW_WORLD_ID,
            lambda v: (results.__setitem__("objects", v), then()))

    def opened(kind):
        results["qwebchannel"] = kind
        QTimer.singleShot(400, read)

    view.page().runJavaScript(open_js, B.PW_WORLD_ID, opened)


def finish():
    main = results.get("main", {})
    pw = results.get("pw", {})
    print("\na page served over real HTTP")
    check("it really is an http page",
          main.get("href", "").startswith("http://127.0.0.1"), main.get("href"))
    check("the page's own world has no channel at all",
          main.get("qt") == "undefined" and not main.get("transport"), main)
    check("no `bridge` global in the page's world",
          main.get("bridgeGlobal") == "undefined", main)
    check("the isolated world does have the transport",
          pw.get("transport") is True, pw)
    objects = results.get("objects")
    # runJavaScript resolves a Promise to null on some Qt builds, so
    # fall back to what the channel reports synchronously
    check("qwebchannel.js is there to build one",
          results.get("qwebchannel") == "function", results.get("qwebchannel"))
    check("and it carries only `pw`", objects == '["pw"]', repr(objects))
    check("never `bridge`", "bridge" not in (objects or ""), objects)
    print("\n%d checks failed" % len(fails))
    for f in fails:
        print("  - " + f)
    server.shutdown()
    app.exit(1 if fails else 0)


def start():
    probe_world(B.MAIN_WORLD_ID, "main",
                lambda: probe_world(B.PW_WORLD_ID, "pw",
                                    lambda: channel_objects(finish)))


QTimer.singleShot(3000, start)
QTimer.singleShot(25000, lambda: (print("TIMED OUT"), app.exit(1)))
sys.exit(app.exec())
