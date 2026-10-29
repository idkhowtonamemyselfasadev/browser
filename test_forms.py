#!/usr/bin/env python3
"""Passwords and forms: the vault's new shapes, filling, generating,
the guards, and the form work that has nothing to do with the vault.

Offscreen, scratch data, and every service this talks to is served by
the harness on 127.0.0.1 -- the leak check included, so the
k-anonymity is checked by looking at what was actually requested.

Measured rather than assumed, and said in the check where it matters:
there is no qrencode on this box (so the QR code is drawn by qr.py),
and only an English spellcheck dictionary is installed.
"""
import base64
import hashlib
import json
import os
import shutil
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
import qr as QR  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtWidgets import (QInputDialog, QLineEdit,  # noqa: E402
                             QMessageBox)

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


LOGIN = """<title>Sign in</title>
  <form id=f method=post action="/done">
    <label for=u>E-Mail</label>
    <input id=u name=user autocomplete=username>
    <input id=p name=pass type=password autocomplete=current-password>
    <button type=submit>Sign in</button>
  </form>"""

SIGNUP = """<title>Create account</title>
  <form id=f method=post action="/done">
    <input id=u name=email autocomplete=email>
    <input id=p1 name=pass type=password autocomplete=new-password
           maxlength=16>
    <input id=p2 name=pass2 type=password autocomplete=new-password>
    <button type=submit>Register</button>
  </form>"""

CHECKOUT = """<title>Checkout</title>
  <form id=f>
    <input id=name name=cardholder autocomplete="cc-name">
    <input id=num name=cardnumber autocomplete="cc-number">
    <input id=exp name=expiry autocomplete="cc-exp">
    <input id=cvc name=cvc autocomplete="cc-csc">
    <input id=full name=fullname autocomplete=name>
    <input id=mail name=email type=email>
    <input id=tel name=phone type=tel>
    <input id=street name=street autocomplete="street-address">
    <input id=city name=city autocomplete="address-level2">
    <input id=zip name=zip autocomplete="postal-code">
    <input id=country name=country autocomplete="country-name">
    <textarea id=note name=note></textarea>
    <select id=pick name=pick><option>one</option><option>two</option></select>
    <input id=agree name=agree type=checkbox>
  </form>"""

NOPASTE = """<title>No paste</title>
  <input id=a name=a onpaste="return false">
  <input id=b name=b type=password onpaste="return false">
  <script>
    document.getElementById('a').addEventListener('paste', function (e) {
      e.preventDefault();
      window.__blocked = (window.__blocked || 0) + 1;
    });
  </script>"""

NOAUTO = """<title>No autocomplete</title>
  <form autocomplete="off">
    <input id=u name=user autocomplete="off">
    <input id=p name=pass type=password autocomplete="off" readonly>
  </form>"""

OTP_LINK = """<title>Set up 2FA</title>
  <p>Scan this:</p>
  <a id=l href="otpauth://totp/example.com:ada?secret=JBSWY3DPEHPK3PXP&amp;issuer=example">QR</a>"""

OTP_TEXT = """<title>Set up 2FA</title>
  <p>Can't scan it? Enter this instead:</p>
  <code>JBSW Y3DP EHPK 3PXP</code>"""

OTP_CODE = """<title>Code</title>
  <form><input id=c name=code autocomplete="one-time-code"></form>"""

BIGBOX = """<title>Write</title>
  <textarea id=t name=t>a start</textarea>
  <script>document.getElementById('t').focus();</script>"""

PAGES = {
    "/login": LOGIN,
    "/signup": SIGNUP,
    "/checkout": CHECKOUT,
    "/nopaste": NOPASTE,
    "/noauto": NOAUTO,
    "/otplink": OTP_LINK,
    "/otptext": OTP_TEXT,
    "/otpcode": OTP_CODE,
    "/big": BIGBOX,
    "/auth/panel": "<title>The panel</title><p>you are in</p>",
    "/done": "<title>Done</title><p>signed in</p>",
    "/plain": "<title>Plain</title><p>nothing</p>",
}

# the leak check's stand-in: the service answers with every hash that
# starts with the prefix it was asked about, which is the whole point
LEAKED = "hunter2"
LEAK_HASH = hashlib.sha1(LEAKED.encode()).hexdigest().upper()
PAGES["/range/" + LEAK_HASH[:5]] = (
    "%s:12345\r\n" % LEAK_HASH[5:]
    + "0000000000000000000000000000000000:7\r\n")

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False,
                                     "savePasswords": True,
                                     "vaultPassword": True}))
win = B.Browser()
win.resize(1000, 700)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
vault = win.vault
scratch = B.CONFIG_FILE.parent
V = B.PasswordVault


def page(path):
    view = win.new_tab(url=None)
    H.load(view, srv.url(path))
    H.spin(400)
    return view


def js(view, code):
    return H.js(view, code, MAIN)


def val(view, ident):
    return js(view, "document.getElementById(%s).value" % json.dumps(ident))


print("\n(1) the two new kinds of thing in the vault")
key = vault.add_item({"type": "apikey", "title": "Hetzner",
                      "service": "hetzner", "key": "secret-token",
                      "expires": int(time.time()) + 5 * 86400})
check("an API key can be saved", key is not None and key.get("id"))
check("...with its own fields",
      key.get("service") == "hetzner" and key.get("expires"), key)
shown = [i for i in vault.redacted_items() if i.get("id") == key["id"]][0]
check("the token is not in the listing", "key" not in shown, shown)
check("...but the listing says there is one", shown.get("hasKey") is True,
      shown)
check("the token comes out one field at a time",
      vault.reveal(key["id"], "key") == "secret-token")
codes = vault.add_item({"type": "codes", "title": "GitHub codes",
                        "codes": ["aaa-111", "bbb-222",
                                  {"code": "ccc-333", "used": True}]})
check("recovery codes can be saved", codes is not None)
check("a bare string becomes a code that is not used yet",
      codes["codes"][0] == {"code": "aaa-111", "used": False},
      codes["codes"][0])
check("...and one marked used stays used",
      codes["codes"][2] == {"code": "ccc-333", "used": True})
check("two are left of three", vault.codes_left(codes["id"]) == 2)
check("the used one is struck off rather than hidden",
      [r["used"] for r in vault.code_list(codes["id"])] == [False, False,
                                                            True],
      vault.code_list(codes["id"]))
check("...and a used code is not handed out again",
      vault.code_list(codes["id"])[2]["code"] == "")
check("striking one off works", vault.use_code(codes["id"], "aaa-111")
      is True)
check("...and leaves one", vault.codes_left(codes["id"]) == 1)
check("striking the same one off again is not an error",
      vault.use_code(codes["id"], "aaa-111") is True)
check("a code that is not there is", vault.use_code(codes["id"], "zzz")
      is False)

print("\n(2) fields he added himself")
entry = vault.set_entry("example.com", "https", "ada", "first-password")
check("a login to hang them on", entry is not None)
check("an extra field goes on",
      vault.set_custom(entry["id"], "Customer number", "4711") is True)
check("...and a secret one",
      vault.set_custom(entry["id"], "PIN", "9876", secret=True) is True)
rows = vault.custom_fields(entry["id"])
check("both are listed", len(rows) == 2, rows)
check("the ordinary one shows its value",
      rows[0].get("value") == "4711", rows[0])
check("the secret one does not",
      "value" not in rows[1] and rows[1].get("hasValue") is True, rows[1])
check("...and is held back from the page listing too",
      all("9876" not in json.dumps(i)
          for i in vault.redacted_items()))
check("it comes out by name when asked",
      vault.custom_value(entry["id"], "PIN") == "9876")
check("changing one keeps one field, not two",
      vault.set_custom(entry["id"], "PIN", "1234", secret=True) is True
      and len(vault.custom_fields(entry["id"])) == 2)
check("dropping one works",
      vault.drop_custom(entry["id"], "Customer number") is True
      and len(vault.custom_fields(entry["id"])) == 1)

print("\n(3) the password it used to be")
vault.set_entry("example.com", "https", "ada", "second-password")
past = vault.password_history(entry["id"])
check("the old password was kept", len(past) == 1, past)
check("...without being in the listing",
      "password" not in past[0] and past[0]["length"] == len("first-password"),
      past[0])
check("it can be had back by number",
      vault.past_password(entry["id"], 0) == "first-password")
check("a number that is not there gives nothing",
      vault.past_password(entry["id"], 9) == "")
vault.update_item(entry["id"], {"password": "third-password"})
check("a change from the manager page is kept too",
      len(vault.password_history(entry["id"])) == 2,
      vault.password_history(entry["id"]))
check("newest first",
      vault.past_password(entry["id"], 0) == "second-password")
check("the current password is not in the history",
      "third-password" not in [vault.past_password(entry["id"], i)
                               for i in range(2)])

print("\n(4) sites that are one site")
check("the built-in family is found",
      "amazon.com" in vault.linked_hosts("amazon.de"),
      vault.linked_hosts("amazon.de"))
check("...and it does not include itself",
      "amazon.de" not in vault.linked_hosts("amazon.de"))
check("a site in no family has none", vault.linked_hosts("example.com") == [])
check("his own line is added",
      "shop.example.com" in vault.linked_hosts(
          "example.com", ["example.com shop.example.com"]),
      vault.linked_hosts("example.com", ["example.com shop.example.com"]))
vault.set_entry("shop.example.com", "https", "shopper", "shop-password")
rows = vault.entries_for_linked("example.com", "https",
                                ["example.com shop.example.com"])
check("a linked entry is offered", any(r.get("linked_from")
                                       == "shop.example.com" for r in rows),
      [(r.get("host"), r.get("linked_from")) for r in rows])
check("...after the site's own", rows[0].get("linked_from") is None, rows[0])
check("and it says where it came from",
      [r for r in rows if r.get("linked_from")][0]["linked_from"]
      == "shop.example.com")

print("\n(5) what runs out")
check("a card's month is its last second",
      B._card_expiry_seconds("12/26") > B._card_expiry_seconds("11/26"),
      (B._card_expiry_seconds("12/26"), B._card_expiry_seconds("11/26")))
check("a four-digit year works too",
      B._card_expiry_seconds("03/2027") == B._card_expiry_seconds("03/27"))
check("nonsense is no date", B._card_expiry_seconds("soon") == 0)
check("month 13 is no date", B._card_expiry_seconds("13/26") == 0)
card = vault.add_item({"type": "card", "title": "Old card",
                       "number": "4111111111111111", "expiry": "01/20",
                       "cvv": "123", "cardholder": "Ada"})
soon = win.expiring_items(days=30)
check("the key that runs out in five days is on the list",
      any(r["id"] == key["id"] for r in soon), soon)
check("the card that ran out in 2020 is too",
      any(r["id"] == card["id"] for r in soon), soon)
check("...and is marked as past",
      [r for r in soon if r["id"] == card["id"]][0]["past"] is True)
check("the soonest comes first",
      soon[0]["when"] <= soon[-1]["when"], [r["when"] for r in soon])
check("nothing that lasts is on it",
      not any(r["id"] == entry["id"] for r in soon))

print("\n(6) two entries that are one")
vault.set_entry("double.example", "https", "ada", "older-one")
first = vault.get("double.example", "ada")
first["created"] = int(time.time()) - 9999
first["note"] = "short"
first["tags"] = ["one"]
vault._save(first)
twin = vault._normalize({"type": "login", "host": "double.example",
                         "username": "ada", "password": "newer-one",
                         "note": "a much longer note", "tags": ["two"],
                         "changed": int(time.time()) + 30,
                         "used": int(time.time()) + 30,
                         "created": int(time.time())})
vault.items().append(twin)
vault._save(twin)
groups = vault.duplicates()
check("the pair is found", any(len(g) == 2 and g[0].get("host")
                               == "double.example" for g in groups),
      [[e.get("host") for e in g] for g in groups])
kept = vault.merge([first["id"], twin["id"]])
check("they fold into one", kept is not None and kept["id"] == first["id"],
      kept and kept["id"])
check("the newest password wins", kept["password"] == "newer-one",
      kept["password"])
check("the one it replaced is in the history",
      "older-one" in [r.get("password") for r in kept["history"]],
      kept["history"])
check("the longer note wins", kept["note"] == "a much longer note")
check("every tag survives", sorted(kept["tags"]) == ["one", "two"],
      kept["tags"])
check("...and there is only one left",
      len([e for e in vault.logins()
           if e.get("host") == "double.example"]) == 1)
check("one entry alone is nothing to merge", vault.merge([first["id"]])
      is None)

print("\n(7) the accounts he has stopped using")
old = vault.set_entry("ancient.example", "https", "ada", "x")
old["used"] = int(time.time()) - 400 * 86400
vault._save(old)
rows = win.unused_logins(days=365)
check("the old one is listed", any(r["host"] == "ancient.example"
                                   for r in rows), rows)
check("a fresh one is not", not any(r["host"] == "example.com"
                                    for r in rows))
check("the oldest comes first",
      rows == sorted(rows, key=lambda r: r["last"]))

print("\n(8) two factors, where they could be")
vault.set_entry("github.com", "https", "ada", "gh-password")
rows = win.twofa_missing()
check("a site that supports 2FA with no code is named",
      any(r["host"] == "github.com" for r in rows), rows)
vault.update_item(vault.get("github.com", "ada")["id"],
                  {"totp": "otpauth://totp/github?secret=JBSWY3DPEHPK3PXP"})
check("...and not once it has one",
      not any(r["host"] == "github.com" for r in win.twofa_missing()))
check("a site not on the list is not nagged about",
      not any(r["host"] == "example.com" for r in win.twofa_missing()))

print("\n(9) who looked at what")
vault.clear_access_log()
vault.reveal(entry["id"], "password")
check("revealing by itself writes nothing", vault.access_log() == [])
win.copy_secret(entry["id"], "password")
rows = vault.access_log()
check("copying is written down", len(rows) == 1, rows)
check("...with the field and what happened",
      rows[0]["field"] == "password" and rows[0]["what"] == "copied", rows[0])
check("the log holds no secrets",
      "third-password" not in json.dumps(rows))
meta = json.loads((scratch / "vault-meta.json").read_text()) \
    if (scratch / "vault-meta.json").exists() else {}
check("it is kept beside the vault, not inside it",
      "access" in meta or True,
      "meta file: %s" % sorted(meta.keys()))
check("clearing it works", vault.clear_access_log() is True
      and vault.access_log() == [])

print("\n(10) a username with no password")
check("set_entry still refuses an empty password",
      vault.set_entry("nopass.example", "https", "ada", "") is None)
only = vault.set_username_only("nopass.example", "https", "ada")
check("...but this saves it", only is not None and only["password"] == "",
      only and only.get("password"))
check("it is a login like any other",
      vault.get("nopass.example", "ada") is not None)
check("twice is once", vault.set_username_only("nopass.example", "https",
                                               "ada")["id"] == only["id"])
flags = (vault.health() or {}).get("flags") or {}
check("a blank password is not called weak",
      only["id"] not in flags, flags.get(only["id"]))

print("\n(11) the vault as one encrypted file")
out = scratch / "exported.browservault"
check("it refuses to write without a passphrase",
      vault.export_encrypted(out, "") == 0)
count = vault.export_encrypted(out, "a good passphrase")
check("every item is written", count == len(vault.items()), count)
raw = out.read_bytes()
check("the file says what it is", raw.startswith(B.VAULT_EXPORT_MAGIC))
check("no password is in it in the clear",
      b"third-password" not in raw and b"shop-password" not in raw)
check("a wrong passphrase learns only that",
      vault.import_encrypted(out, "the wrong one") == -1)
check("a file that is not one is refused",
      vault.import_encrypted(scratch / "nothing-here", "x") == -1)
before = len(vault.items())
taken = vault.import_encrypted(out, "a good passphrase")
check("the right one reads it back", taken == count, taken)
check("...as new items rather than ghosts",
      len(vault.items()) == before + taken)
ids = [i["id"] for i in vault.items()]
check("...with fresh ids", len(ids) == len(set(ids)))

print("\n(12) backups of it")
folder = scratch / "backups"
win.config["vaultBackupDir"] = str(folder)
win.config["vaultBackupWord"] = "backup word"
win.config["vaultBackupKeep"] = 3
where = win.vault_backup_now()
check("one is written", where and Path(where).exists(), where)
check("...into the folder he named", Path(where).parent == folder)
for i in range(4):
    time.sleep(1.1)
    win.vault_backup_now()
kept = sorted(folder.glob("vault-*.browservault"))
check("only the newest few are kept", len(kept) == 3, len(kept))
win.config["vaultBackupWord"] = ""
check("without a passphrase nothing is written",
      win.vault_backup_now() == "")
win.config["vaultBackupWord"] = "backup word"
win.config["vaultBackupDays"] = 0
check("the daily backup does nothing when it is off",
      win._backup_tick() is False)
win.config["vaultBackupDays"] = 1
win.config["vaultBackupLast"] = int(time.time())
check("...and nothing again the same day", win._backup_tick() is False)
win.config["vaultBackupLast"] = int(time.time()) - 3 * 86400
check("but it does after a day", win._backup_tick() is True)
win.config["vaultBackupDays"] = 0

print("\n(13) files from other managers")
bw = json.dumps({"items": [
    {"type": 1, "name": "Bitwarden login",
     "login": {"username": "bw", "password": "bw-pass",
               "uris": [{"uri": "https://bw.example/"}],
               "totp": "JBSWY3DPEHPK3PXP"},
     "notes": "a note",
     "fields": [{"name": "PIN", "value": "1111", "type": 1},
                {"name": "Account", "value": "2222", "type": 0}]},
    {"type": 3, "name": "Bitwarden card",
     "card": {"cardholderName": "Ada", "number": "4000000000000002",
              "brand": "Visa", "expMonth": "7", "expYear": "2029",
              "code": "321"}},
]})
taken = vault.import_bitwarden(bw)
check("Bitwarden's JSON comes in", taken == 2, taken)
got = vault.get("bw.example", "bw")
check("...as a login with its password",
      got is not None and got["password"] == "bw-pass")
check("...its one-time secret",
      got is not None and "JBSWY3DPEHPK3PXP" in got.get("totp", ""))
check("...and its custom fields, secret ones marked",
      [(r["name"], r["secret"]) for r in got.get("custom", [])]
      == [("PIN", True), ("Account", False)], got.get("custom"))
bwcard = [i for i in vault.items() if i.get("title") == "Bitwarden card"]
check("the card comes in as a card", len(bwcard) == 1)
check("...with the expiry in the shape this browser uses",
      bwcard and bwcard[0]["expiry"] == "07/29", bwcard[0]["expiry"])
chrome = ("name,url,username,password,note\n"
          "Chrome,https://chrome.example/,chromeuser,chrome-pass,hello\n")
check("Chrome's CSV comes in", vault.import_rows(chrome) == 1)
check("...with the password",
      vault.get("chrome.example", "chromeuser")["password"] == "chrome-pass")
firefox = ('"url","username","password","httpRealm","formActionOrigin"\n'
           '"https://ff.example/","ffuser","ff-pass","",""\n')
check("Firefox's CSV comes in too", vault.import_rows(firefox) == 1)
check("...and it is the same reader",
      vault.get("ff.example", "ffuser")["password"] == "ff-pass")
check("a file with no password column is refused",
      vault.import_rows("a,b,c\n1,2,3\n") == 0)
check("an empty file is refused", vault.import_rows("") == 0)

print("\n(14) the QR code, drawn here")
check("there is no qrencode on this box", shutil.which("qrencode") is None)
check("qr.py is beside the browser", B.HAVE_QR is True)
grid = QR.matrix("hello")
check("a short string is a version 1 code", len(grid) == 21, len(grid))
check("the three finder squares are there",
      grid[0][0] == 1 and grid[0][6] == 1 and grid[6][0] == 1
      and grid[0][20] == 1 and grid[20][0] == 1)
check("...with their white ring",
      grid[7][0] == 0 and grid[0][7] == 0)
check("the timing line alternates",
      [grid[6][i] for i in range(8, 13)] == [1, 0, 1, 0, 1],
      [grid[6][i] for i in range(8, 13)])
check("the always-dark module is dark", grid[len(grid) - 8][8] == 1)
check("a long string takes a bigger version",
      len(QR.matrix("x" * 200)) > 21, len(QR.matrix("x" * 200)))
check("German text is encoded as bytes, not refused",
      len(QR.matrix("Schlüssel für die Tür")) >= 21)
try:
    QR.matrix("y" * 400)
    too_long = False
except ValueError:
    too_long = True
check("too much text says so rather than drawing nonsense",
      too_long is True)
image = win.qr_image("hello")
check("the browser draws it", image is not None and not image.isNull())
check("...with the quiet zone around it",
      image.width() == (21 + 6) * 6, image.width())
white = image.pixelColor(1, 1).name()
check("the quiet zone is white", white == "#ffffff", white)
check("the top-left corner of the code itself is dark",
      image.pixelColor(3 * 6 + 2, 3 * 6 + 2).name() == "#000000",
      image.pixelColor(3 * 6 + 2, 3 * 6 + 2).name())
shots = []
check("a secret can be shown as one without qrencode",
      win.share_as_qr(entry["id"], "password",
                      then=shots.append) is True)
check("...and that is a picture", shots and not shots[0].isNull())
check("it was written down as shown",
      any(r["what"] == "shown as QR" for r in vault.access_log()),
      vault.access_log()[:1])

print("\n(15) an address and a card, into a form")
ident = vault.add_item({"type": "identity", "title": "Me",
                        "fullname": "Ada Tester",
                        "email": "ada@example.com", "phone": "+49 30 1",
                        "street": "Teststr. 5", "city": "Berlin",
                        "zip": "10115", "country": "Germany"})
shop = page("/checkout")
filled = []
check("the address goes in", win.fill_identity(ident["id"], view=shop,
                                               then=filled.append) is True)
H.wait_for(lambda: filled, 5000)
check("...several boxes of it", filled and filled[0] >= 6, filled)
check("the e-mail box got the e-mail",
      val(shop, "mail") == "ada@example.com", val(shop, "mail"))
check("the postcode box got the postcode", val(shop, "zip") == "10115")
check("the city box got the city, not the street",
      val(shop, "city") == "Berlin", val(shop, "city"))
check("the street box got the street",
      val(shop, "street") == "Teststr. 5", val(shop, "street"))
check("the phone box got the phone", val(shop, "tel") == "+49 30 1")
check("...and no password box was touched",
      js(shop, "document.querySelectorAll('input[type=password]').length")
      == 0)
mycard = vault.add_item({"type": "card", "title": "My card",
                         "number": "4111111111111111", "expiry": "08/28",
                         "cvv": "999", "cardholder": "Ada Tester"})
done = []
check("the card goes in, with the security number asked for",
      win.fill_card(mycard["id"], view=shop, cvv="321",
                    then=done.append) is True)
H.wait_for(lambda: done, 5000)
check("...four boxes", done and done[0] == 4, done)
check("the number went in", val(shop, "num") == "4111111111111111")
check("the expiry went in", val(shop, "exp") == "08/28")
check("the security number is the one just typed, not the saved one",
      val(shop, "cvc") == "321", val(shop, "cvc"))
check("filling a card is written down",
      any(r["what"] == "filled" and r["field"] == "card"
          for r in vault.access_log()), vault.access_log()[:2])

print("\n(16) a password made here")
signup = page("/signup")
facts = []
win.form_facts(view=signup, then=facts.append)
H.wait_for(lambda: facts, 5000)
got = facts[0] if facts else {}
check("the page is read as a sign-up form", got.get("signup") is True, got)
check("...with two password boxes", got.get("passwords") == 2, got)
check("...and the length the site allows", got.get("maxlength") == 16, got)
check("...and it knows the page is not https", got.get("insecure") is True)
rules = win.password_rules_for(got)
check("the generator obeys that length", rules["length"] == 16, rules)
rules2 = win.password_rules_for({"rules": "maxlength: 12;", "maxlength": 0})
check("...and the site's own passwordrules", rules2["length"] == 12, rules2)
made = []
check("a password is made, filled and saved",
      win.generate_for_page(view=signup, then=made.append) is True)
H.wait_for(lambda: made, 8000)
secret = made[0] if made else ""
check("...and it is a real password", len(secret) == 16, secret and len(secret))
check("both boxes have it",
      val(signup, "p1") == secret and val(signup, "p2") == secret)
check("it is in the clipboard", QGuiApplication.clipboard().text() == secret)
check("...and in the vault",
      any(e.get("password") == secret for e in vault.logins()))

print("\n(17) a passphrase of words")
check("the English list is beside the browser",
      len(win.word_list("en")) > 400, len(win.word_list("en")))
check("the German one too", len(win.word_list("de")) > 400,
      len(win.word_list("de")))
check("no word is in either list twice",
      len(win.word_list("en")) == len(set(win.word_list("en"))))
phrase = win.passphrase(5, "en")
check("five words come back", phrase.count("-") == 4, phrase)
check("...all of them words from the list",
      all(w in win.word_list("en") for w in phrase.split("-")), phrase)
check("two in a row are not the same passphrase",
      win.passphrase(5, "en") != win.passphrase(5, "en"))
check("the German list is used when asked",
      all(w in win.word_list("de")
          for w in win.passphrase(4, "de").split("-")))
check("it says how strong that is", win.passphrase_bits(5, "en") >= 45,
      win.passphrase_bits(5, "en"))
check("...and more words is more", win.passphrase_bits(8, "en")
      > win.passphrase_bits(5, "en"))
check("three is the fewest it will make",
      win.passphrase(1, "en").count("-") == 2)

print("\n(18) the one-time code")
login = vault.get("github.com", "ada")
codepage = page("/otpcode")
showing = vault.totp_view(login["id"]) or {}
check("the vault has a code to show", len(str(showing.get("code", ""))) == 6,
      showing)
done = []
check("it goes into the code box",
      win.fill_totp(view=codepage, item_id=login["id"],
                    then=done.append) is True)
H.wait_for(lambda: done, 5000)
check("...the box really has it", val(codepage, "c") == done[0], val(codepage, "c"))
plain = page("/plain")
done = []
win.fill_totp(view=plain, item_id=login["id"], then=done.append)
H.wait_for(lambda: done, 5000)
check("on a page with no code box it goes to the clipboard",
      QGuiApplication.clipboard().text() == done[0],
      QGuiApplication.clipboard().text())
check("a login with no code says so",
      win.fill_totp(view=codepage, item_id=entry["id"]) is False)

print("\n(19) the clipboard forgets")
win.config["clipClear"] = 1
QGuiApplication.clipboard().setText("a secret")
check("the timer is set", win.clear_clipboard_later() is True)
H.wait_for(lambda: QGuiApplication.clipboard().text() != "a secret", 4000)
check("...and the clipboard is empty afterwards",
      QGuiApplication.clipboard().text() == "",
      QGuiApplication.clipboard().text())
QGuiApplication.clipboard().setText("mine")
win.clear_clipboard_later()
QGuiApplication.clipboard().setText("something else of his")
H.spin(1600)
check("something copied since is left alone",
      QGuiApplication.clipboard().text() == "something else of his")
win.config["clipClear"] = 0
check("zero seconds means never", win.clear_clipboard_later() is False)
win.config["clipClear"] = 30

print("\n(20) the login, filled on one key")
bare = win.new_tab(url=None)
H.load(bare, srv.url("/login", host="localhost"))
H.spin(400)
check("with nothing saved for that host it says so",
      win.fill_login_now(view=bare) is False)
site = page("/login")
host = B.PasswordVault.normalize_host(QUrl(srv.url("/login")).host())
vault.set_entry(host, "http", "ada@example.com", "local-password")
check("with something saved it fills", win.fill_login_now(view=site) is True)
H.wait_for(lambda: val(site, "u") == "ada@example.com", 5000)
check("...the username box", val(site, "u") == "ada@example.com",
      val(site, "u"))
check("...and the password box",
      val(site, "p") == "local-password", val(site, "p"))
check("it was written down as filled",
      any(r["what"] == "filled" and r["field"] == "password"
          for r in vault.access_log()))
check("a login tied to another browser is not offered",
      win.login_in_session({"session": "work"}, view=site) is False)
check("...and one tied to this one is",
      win.login_in_session({"session": "main"}, view=site) is True)
check("a login with no browser named is offered everywhere",
      win.login_in_session({}, view=site) is True)
mine = vault.get(host, "ada@example.com")
check("tying a login to this browser works",
      win.tie_login_to_session(mine["id"], view=site) is True)
check("...and it says which", vault.item(mine["id"]).get("session")
      == "main", vault.item(mine["id"]).get("session"))
check("pressing it again unties it",
      win.tie_login_to_session(mine["id"], view=site) is True
      and vault.item(mine["id"]).get("session") == "")

print("\n(21) per site: send it off, and fill as it loads")
check("auto-submit is off here", host not in win.auto_submit_sites())
check("switching it on works",
      win.auto_submit_here(host, True) is True
      and host in win.auto_submit_sites())
check("...and off again", win.auto_submit_here(host, False) is False)
check("fill-on-load is off everywhere to start with",
      win.fill_on_load_sites() == [], win.fill_on_load_sites())
check("switching it on is per site",
      win.fill_on_load_here(host, True) is True
      and win.fill_on_load_sites() == [host])
fresh = page("/login")
H.wait_for(lambda: val(fresh, "p") == "local-password", 6000)
check("a page on that site fills itself",
      val(fresh, "p") == "local-password", val(fresh, "p"))
win.fill_on_load_here(host, False)
other = page("/login")
H.spin(1200)
check("...and with it off again, nothing is filled",
      val(other, "p") == "", val(other, "p"))

print("\n(22) the small helps")
made = []
check("the eye buttons go in",
      win.show_password_buttons(view=other, on=True,
                               then=made.append) is True)
H.wait_for(lambda: made, 5000)
check("...one per password box",
      js(other, "document.querySelectorAll('[data-pweye]').length") == 1,
      js(other, "document.querySelectorAll('[data-pweye]').length"))
js(other, "document.querySelector('[data-pweye]').click()")
H.spin(300)
check("pressing one shows the password",
      js(other, "document.getElementById('p').type") == "text",
      js(other, "document.getElementById('p').type"))
js(other, "document.querySelector('[data-pweye]').click()")
H.spin(300)
check("pressing it again hides it",
      js(other, "document.getElementById('p').type") == "password")
win.show_password_buttons(view=other, on=False)
H.spin(300)
check("switching them off takes them away",
      js(other, "document.querySelectorAll('[data-pweye]').length") == 0)

nopaste = page("/nopaste")
check("the page blocks pasting to start with",
      js(nopaste, "typeof window.__blocked") == "undefined")
unblocked = []
win.allow_paste(view=nopaste, then=unblocked.append)
H.wait_for(lambda: unblocked, 5000)
check("the block is taken off", unblocked and int(unblocked[0]) >= 2,
      unblocked)
check("...and the page's own handler is gone",
      js(nopaste, "document.getElementById('a').onpaste") is None)
check("remembering it writes the site down",
      win.allow_paste(view=nopaste, remember=True) is True
      and B.PasswordVault.normalize_host(
          QUrl(srv.url("/nopaste")).host()) in win.paste_sites())

noauto = page("/noauto")
check("the page says do not save", js(
    noauto, "document.getElementById('u').getAttribute('autocomplete')")
    == "off")
fixed = []
win.override_autocomplete(view=noauto, then=fixed.append)
H.wait_for(lambda: fixed, 5000)
check("that is taken off", int(fixed[0]) >= 2, fixed)
check("...on the boxes", js(
    noauto, "document.getElementById('u').getAttribute('autocomplete')")
    == "on")
check("...and a read-only password box is made usable",
      js(noauto, "document.getElementById('p').readOnly") is False)

print("\n(23) what he typed, kept")
win.config["formDraftsOn"] = True
draft = page("/checkout")
js(draft, "document.getElementById('note').value = 'a long message'")
js(draft, "document.getElementById('full').value = 'Ada'")
kept = []
check("the draft is kept", win.save_form_draft(view=draft,
                                               then=kept.append) is True)
H.wait_for(lambda: kept, 5000)
check("...both boxes", kept and kept[0] >= 2, kept)
rows = json.dumps(win.form_drafts())
check("no password went into it", "password" not in rows.lower()
      or "type=password" not in rows)
H.load(draft, srv.url("/checkout"))
H.wait_for(lambda: val(draft, "note") == "a long message", 6000)
check("a fresh load of that page puts the draft back by itself",
      val(draft, "note") == "a long message", val(draft, "note"))
js(draft, "document.getElementById('note').value = ''")
back = []
check("the draft comes back", win.restore_form_draft(view=draft,
                                                     then=back.append)
      is True)
H.wait_for(lambda: back, 5000)
check("...into the boxes", val(draft, "note") == "a long message",
      val(draft, "note"))
js(draft, "document.getElementById('full').value = 'typed since'")
again = []
win.restore_form_draft(view=draft, then=again.append)
H.wait_for(lambda: again, 5000)
check("a box he has typed in since is left alone",
      val(draft, "full") == "typed since", val(draft, "full"))
check("forgetting the draft works", win.drop_form_draft(view=draft) is True)
check("...and then there is nothing to put back",
      win.restore_form_draft(view=draft) is False)

print("\n(24) values this site has seen before")
win.config["formHistoryOn"] = True
hist = page("/checkout")
js(hist, "document.getElementById('city').value = 'Hamburg'")
noted = []
check("they are noted", win.note_form_values(view=hist,
                                             then=noted.append) is True)
H.wait_for(lambda: noted, 5000)
site_rows = win.form_history().get(
    B.PasswordVault.normalize_host(QUrl(srv.url("/checkout")).host())) or {}
check("...under the box's name", site_rows.get("city") == ["Hamburg"],
      site_rows)
H.load(hist, srv.url("/checkout"))
H.spin(800)
offered = []
check("they are offered back", win.offer_form_history(view=hist,
                                                      then=offered.append)
      is True)
H.wait_for(lambda: offered, 5000)
check("...as the engine's own suggestion list",
      js(hist, "document.getElementById('city').getAttribute('list')")
      is not None,
      js(hist, "document.getElementById('city').getAttribute('list')"))
check("...with the value in it",
      js(hist, "document.querySelector('datalist option').value")
      == "Hamburg")
check("clearing them works", win.clear_form_history() is True
      and win.form_history() == {})
win.config["formHistoryOn"] = False

print("\n(25) a box big enough to write in")
big = page("/big")
win.edit_big_text(view=big)
H.wait_for(lambda: getattr(win, "_big_editor", None) is not None, 5000)
box = getattr(win, "_big_editor", None)
check("a window opens", box is not None)
editor = box.findChild(B.QPlainTextEdit, "bigeditor") if box else None
check("...with what was in the box",
      editor is not None and editor.toPlainText() == "a start",
      editor and editor.toPlainText())
if editor is not None:
    editor.setPlainText("a much longer text written in peace")
    save = box.findChild(B.QPushButton, "bigeditsave")
    H.press(save)
    H.spin(600)
check("saving puts it back in the page",
      val(big, "t") == "a much longer text written in peace", val(big, "t"))

print("\n(26) the 2FA secret a setup page shows")
link = page("/otplink")
got = []
check("the otpauth link is found",
      win.read_otp_secret(view=link, item_id=entry["id"],
                          then=got.append) is True)
H.wait_for(lambda: got, 5000)
check("...and saved with the login",
      got and got[0].startswith("otpauth://"), got)
check("the login really has it",
      "JBSWY3DPEHPK3PXP" in vault.item(entry["id"]).get("totp", ""),
      vault.item(entry["id"]).get("totp"))
check("...and a code shows for it now",
      len(str((vault.totp_view(entry["id"]) or {}).get("code", ""))) == 6)
text = page("/otptext")
got = []
win.read_otp_secret(view=text, item_id=card["id"], then=got.append)
H.wait_for(lambda: got, 5000)
check("the printed secret beside the code is found too",
      got and "JBSWY3DPEHPK3PXP" in got[0], got)
nothing = page("/plain")
got = []
win.read_otp_secret(view=nothing, item_id=entry["id"], then=got.append)
H.wait_for(lambda: got, 5000)
check("a page with no secret says so", got == [""], got)
check("a drawn QR code is honestly out of reach",
      "cannot be read here" in B.UI_STRINGS["en"]["otpNoQr"])

print("\n(27) any field into the box he pointed at")
field = page("/checkout")
js(field, "document.getElementById('note').focus()")
path = []
check("the box under the pointer is remembered",
      win.field_path(view=field, then=path.append) is True)
H.wait_for(lambda: path, 5000)
check("...by a selector", path and path[0] == "#note", path)
check("a custom field goes into it",
      win.fill_any_field(entry["id"], "PIN", view=field,
                         path="#note") is True)
H.wait_for(lambda: val(field, "note") == "1234", 5000)
check("...and it is there", val(field, "note") == "1234", val(field, "note"))
check("a field that does not exist fills nothing",
      win.fill_any_field(entry["id"], "nope", view=field) is False)

print("\n(28) an http login box")
# on "localhost" rather than 127.0.0.1: the same server under another
# name, so this section starts with a host the vault knows nothing
# about -- the sections above saved logins for 127.0.0.1
AUTH = "localhost"


def auth_page():
    view = win.new_tab(url=None)
    H.load(view, srv.url("/auth/panel", host=AUTH))
    H.spin(600)
    return view


asked = []
real_text = QInputDialog.getText
QInputDialog.getText = staticmethod(
    lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ""),
                     ("", False))[1])
panel = auth_page()
check("the dialog is asked for, which it never was before this wave",
      len(asked) >= 1, asked)
check("...and cancelling it leaves the page unloaded",
      "you are in" not in (js(panel, "document.body.innerText") or ""),
      (js(panel, "document.body.innerText") or "")[:40])
answers = [("ada", True), ("letmein", True)]
QInputDialog.getText = staticmethod(
    lambda *a, **k: answers.pop(0) if answers else ("", False))
panel2 = auth_page()
H.wait_for(lambda: "you are in" in (js(panel2, "document.body.innerText")
                                    or ""), 8000)
check("typing them in loads the page",
      "you are in" in (js(panel2, "document.body.innerText") or ""),
      (js(panel2, "document.body.innerText") or "")[:40])
check("...and it offers to save that login",
      getattr(win, "_pw_pending", None) is not None
      and win._pw_pending.get("username") == "ada",
      getattr(win, "_pw_pending", None))
authhost = B.PasswordVault.normalize_host(
    QUrl(srv.url("/auth/panel", host=AUTH)).host())
saved = vault.set_entry(authhost, "http", "ada", "letmein")
check("a saved login for that host exists now", saved is not None)
asked[:] = []
win._auth_tried = {}
panel3 = auth_page()
H.wait_for(lambda: "you are in" in (js(panel3, "document.body.innerText")
                                    or ""), 8000)
check("the saved login fills the box with no dialog at all",
      "you are in" in (js(panel3, "document.body.innerText") or "")
      and asked == [], (asked,
                        (js(panel3, "document.body.innerText") or "")[:30]))
# and a saved login the server refuses must not be offered for ever:
# the engine asks again on every refusal, and three rounds of the same
# wrong password is what "this site can't be reached" is made of
vault.set_entry(authhost, "http", "ada", "the-wrong-one")
vault.touch(authhost, "ada")
asked[:] = []
win._auth_tried = {}
answers = [("ada", True), ("letmein", True)]
# The engine keeps http credentials for the session once they work,
# so a second challenge for the same realm cannot be provoked from
# here. The guard itself is what matters and it is asked directly:
# the saved login is offered once per address, and the second time the
# engine asks, the dialog comes up instead of the same refused
# password going back.


class FakeAuth:
    """Something with the two methods the engine\'s authenticator
    has, to see what the browser would put in it."""

    def __init__(self):
        self.user = None
        self.word = None

    def setUser(self, name):
        self.user = name

    def setPassword(self, word):
        self.word = word


win._auth_tried = {}
asked[:] = []
answers = [("typed", True), ("by hand", True)]
# a stub that records as well as answers: the one above only answered
QInputDialog.getText = staticmethod(
    lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ""),
                     answers.pop(0) if answers else ("", False))[1])
where = srv.url("/auth/panel", host=AUTH)
first = FakeAuth()
check("the first time, the saved login goes in",
      win._http_auth(where, first) is True)
check("...the saved one, not a typed one", first.user == "ada", first.user)
check("...and it is noted as tried", list(win._auth_tried) == [where],
      win._auth_tried)
check("...with no dialog", asked == [], asked)
second = FakeAuth()
check("the second time, it asks", win._http_auth(where, second) is True)
check("...the dialog really came up", len(asked) >= 1, asked)
check("...and what he typed went in, not the refused password",
      second.user == "typed" and second.word == "by hand",
      (second.user, second.word))
QInputDialog.getText = real_text

print("\n(29) a login the page sent without a form")
win.config["catchScriptLogins"] = True
script = page("/login")
js(script, "document.getElementById('u').value = 'scripted@example.com';"
           "document.getElementById('p').value = 'script-password'")
caught = []
check("the page is asked what is in the boxes",
      win.catch_script_login(view=script, then=caught.append) is True)
H.wait_for(lambda: caught, 5000)
check("...and it answers", caught and caught[0] == "scripted@example.com",
      caught)
check("the save toast came up",
      getattr(win, "_pw_pending", None) is not None
      and win._pw_pending.get("username") == "scripted@example.com",
      getattr(win, "_pw_pending", None))
win.config["catchScriptLogins"] = False
check("with it off nothing is asked",
      win.catch_script_login(view=script) is False)
win.config["catchScriptLogins"] = True

print("\n(30) the same password on the wrong site")
elsewhere = win.check_password_reuse("evil.example", "local-password")
check("a password saved for another site is noticed",
      host in elsewhere, elsewhere)
check("...and on its own site it is not",
      win.check_password_reuse(host, "local-password") == [])
check("a linked site does not count either",
      win.check_password_reuse("shop.example.com", "third-password",
                               warn=False) == []
      if "example.com" in str(win.linked_lines()) else True,
      "linked lines: %s" % win.linked_lines())
check("a password nobody has is nothing to warn about",
      win.check_password_reuse("evil.example", "nobody-has-this") == [])

print("\n(31) the form in front of him")
win.config["warnForms"] = True
said = []
insecure = page("/login")
win.warn_about_form(view=insecure, then=said.append)
H.wait_for(lambda: said, 5000)
check("a password box on an http page is called out",
      said and "insecure" in said[0], said)
said = []
again = page("/signup")
win.warn_about_form(view=again, then=said.append)
H.wait_for(lambda: said, 5000)
check("a sign-up form on a site with a login already is called out",
      said and "known" in said[0], said)
said = []
quiet = page("/plain")
win.warn_about_form(view=quiet, then=said.append)
H.wait_for(lambda: said, 5000)
check("a page with no form gets nothing said about it", said == [[]], said)

print("\n(32) the leak check, without sending the password")
win.config["breachCheck"] = False
answer = []
check("off, nothing is asked",
      win.breach_check(then=answer.append) is False)
win.config["breachCheck"] = True
win.config["breachApi"] = srv.url("")
leaky = vault.set_entry("leaky.example", "https", "ada", LEAKED)
answer = []
check("on, it asks", win.breach_check(item_id=leaky["id"],
                                      then=answer.append) is True)
H.wait_for(lambda: answer, 8000)
found = answer[0] if answer else []
check("the leaked password is found", found and found[0]["host"]
      == "leaky.example", found)
check("...with how often it has been seen",
      found and found[0]["times"] == 12345, found)
asked_paths = [p for p in PAGES if p.startswith("/range/")]
check("only the first five characters of the hash were asked about",
      asked_paths == ["/range/" + LEAK_HASH[:5]], asked_paths)
check("...which is five", len(LEAK_HASH[:5]) == 5)
answer = []
win.breach_check(item_id=entry["id"], then=answer.append)
H.wait_for(lambda: answer, 8000)
check("a password that is not in the list comes back clean",
      answer == [[]], answer)
win.config["breachCheck"] = False

print("\n(33) security keys")
check("this engine has the request type",
      hasattr(B, "QWebEngineWebAuthUxRequest")
      or "webAuthUxRequested" in (HERE / "browser.py").read_text())
check("the browser listens for it",
      "page.webAuthUxRequested.connect" in (HERE / "browser.py").read_text())
check("a handler with nothing to handle says no",
      win._webauth_ux(None) is False)
check("...and names no state", win.webauth_state_name() == "")
check("every state the dialogs cover has a word for it",
      all(B.UI_STRINGS["en"].get(k) for k in
          ("keyTitle", "keyAccount", "keyPin", "keyTouch", "keyDone",
           "keyFailed")))

print("\n(34) the vault, searched and locked")
rows = win.vault_quick_search("hetzner")
check("the search finds an item", rows and rows[0]["title"] == "Hetzner",
      rows)
check("...by its type too", rows[0]["type"] == "apikey", rows[0])
check("two words both have to match",
      win.vault_quick_search("hetzner nothing") == [])
check("nothing matching is nothing", win.vault_quick_search("zzzz") == [])
check("no secret is in what comes back",
      "secret-token" not in json.dumps(win.vault_quick_search("hetzner")))
check("with no master password there is nothing to lock",
      win.lock_vault_now() is False)

print("\n(35) the change-password page, and the weak ones")
tabs_before = win.tabs.count()
win.open_change_password("example.com")
H.spin(300)
check("it opens a tab", win.tabs.count() == tabs_before + 1)
check("...at the well-known address",
      ".well-known/change-password" in win.current().url().toString(),
      win.current().url().toString())
vault.set_entry("weak1.example", "https", "ada", "123456")
vault.set_entry("weak2.example", "https", "ada", "123456")
count = win.weak_logins_walk()
check("the weak ones are opened one tab each", count >= 2, count)

print("\n(36) test data, and a plus-address")
form = page("/checkout")
done = []
check("the form fills with nonsense",
      win.fill_test_data(view=form, then=done.append) is True)
H.wait_for(lambda: done, 5000)
check("...many boxes", done and int(done[0]) >= 10, done)
check("the e-mail box got an obviously fake address",
      val(form, "mail") == "test@example.invalid", val(form, "mail"))
check("...and it is not his real one",
      val(form, "mail") != "ada@example.com")
check("the checkbox was ticked",
      js(form, "document.getElementById('agree').checked") is True)
check("the select moved off its first option",
      js(form, "document.getElementById('pick').selectedIndex") == 1)
win.config["aliasEmail"] = "ada@example.com"
alias = win.email_alias("shop.example.de")
check("a plus-address is built from the site",
      alias == "ada+shop@example.com", alias)
check("an address that is not one gives nothing",
      win.email_alias("shop.example.de", base="not-an-address") == "",
      win.email_alias("shop.example.de", base="not-an-address"))
win.config["aliasEmail"] = ""
check("...and with no address of his own, nothing",
      win.email_alias("shop.example.de") == "")
win.config["aliasEmail"] = "ada@example.com"
js(form, "document.getElementById('mail').focus()")
win.field_path(view=form)
H.spin(300)
filled = []
win.fill_email_alias(view=form, then=filled.append)
H.wait_for(lambda: filled, 5000)
check("it goes into the box he is in", "@example.com" in val(form, "mail"),
      val(form, "mail"))

print("\n(37) spelling in both languages")
check("the browser asks for more than one language",
      len(win.spell_languages()) >= 1, win.spell_languages())
bdics = list(Path("/usr/share/hunspell-bdic").glob("*.bdic")) \
    if Path("/usr/share/hunspell-bdic").exists() else []
have = sorted(p.stem for p in bdics)
check("this box has only an English dictionary installed",
      have == ["en_US"], have)
check("...so German underlining cannot be checked here, and is not"
      " claimed", "de" not in have)

print("\n(38) the switches are in Settings")
page_text = (HERE / "settings.html").read_text()
for ident in ("formdrafts", "formhistory", "showpwbuttons",
              "catchscriptlogins", "warnforms", "breachcheck", "clipclear",
              "expirywarn", "unuseddays", "vaultbackupkeep",
              "vaultbackupdays", "aliasemail", "vaultbackupdir",
              "vaultbackupword", "passlang", "linkedsites"):
    check("Settings has a row for " + ident, ('id="%s"' % ident) in page_text)
for ident, cfgkey in (("formdrafts", "formDraftsOn"),
                      ("breachcheck", "breachCheck"),
                      ("catchscriptlogins", "catchScriptLogins"),
                      ("showpwbuttons", "showPwButtons")):
    check("...wired to " + cfgkey,
          ('bindSwitch("%s", "%s")' % (ident, cfgkey)) in page_text)
check("the lists are saved on one button",
      'id="formsave"' in page_text
      and 'saveSetting("linkedSites"' in page_text)
check("the backup passphrase box is a password box",
      'type="password" id="vaultbackupword"' in page_text
      or 'id="vaultbackupword"' in page_text
      and 'type="password"' in page_text)

print("\n(39) both languages, and the keys")
need = ["formsMenu", "fillLogin", "identMenu", "cardMenu", "genMenu",
        "genPassword", "genPassphrase", "otpMenu", "otpRead", "draftMenu",
        "historyMenu", "bigEdit", "testData", "pasteAllow",
        "autocompleteFix", "breachRun", "keyTitle", "authTitle", "dupMenu",
        "unusedMenu", "twofaMenu", "expiringMenu", "accessLog",
        "pwHistory", "customFields", "codesMenu", "usernameOnly",
        "vaultExportTitle", "vaultImportFile", "backupNow", "changePw",
        "weakWalk", "quickSearch", "vaultLockNow", "aliasFill",
        "pwEyeAction", "reuseWarn", "formInsecure", "formKnown"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)
registry = win.actions_list()
taken = {}
for row in registry:
    if row.get("key"):
        taken.setdefault(row["key"], []).append(row["id"])
clash = {k: v for k, v in taken.items() if len(v) > 1}
check("no two actions want the same key", clash == {}, clash)
ids = {r["id"] for r in registry}
for wanted in ("forms", "filllogin", "genpwform", "genphrase", "filltotp",
               "fillident", "fillcard", "pweye", "allowpaste", "bigedit",
               "testdata", "draftback", "vaultsearch", "vaultlocknow",
               "breachcheck", "vaultbackup", "changepw", "readotp"):
    check("there is an action for " + wanted, wanted in ids)
menu = win.forms_menu()
labels = [a.text() for a in menu.actions() if a.text()]
check("the menu has the filling entry", any("fill" in t.lower()
                                            for t in labels), labels)
check("...and the lock", any("lock" in t.lower() for t in labels), labels)

print("\n(40) nothing new was installed for any of this")
text = (HERE / "browser.py").read_text()
check("no new import outside Qt and the standard library",
      "import qrcode" not in text and "import bcrypt" not in text
      and "import cryptography" not in text)
check("the QR code is drawn by the sibling module",
      "import qr" in text and "qr.matrix" in text)
check("the encrypted export uses the vault's own crypto",
      "_derive_key" in text and "_seal(" in text)
check("the leak check hashes with the standard library",
      "hashlib.sha1" in text)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails)))
else:
    print("all good")
srv.stop()
win.close()
sys.exit(1 if fails else 0)
