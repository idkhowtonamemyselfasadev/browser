#!/usr/bin/env python3
"""The two ways 1Password used to take the browser down with it, and a
third way it used to lie about a write — all three measured rather than
asserted.

  * a hanging `op`: Browser() and vaultProviders() both used to sit
    there for the full twenty-second timeout, on the GUI thread
  * a token file that is not a token: a UTF-16 paste or a NUL byte
    raised out of Browser.__init__ and there was no window at all
  * a token revoked mid-session: update_item returned the item it had
    just changed and delete_item returned True, both without ever
    looking at what the store said

Offscreen, against a scratch config and the mock `op`. Your own vault
is never opened.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

BIN = SCRATCH / "bin"
BIN.mkdir(parents=True, exist_ok=True)
shutil.copy(HERE / "tools" / "mock-op", BIN / "op")
os.chmod(BIN / "op", 0o755)
os.environ["PATH"] = str(BIN) + os.pathsep + os.environ["PATH"]
os.environ["MOCK_OP_STORE"] = str(SCRATCH / "op-store.json")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def config(**extra):
    B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    B.CONFIG_FILE.write_text(json.dumps(
        dict({"passwordProvider": "1password", "opVault": "Browser",
              "translateLang": "en", "vaultPassword": True}, **extra)))


TOKEN_FILE = B.CONFIG_FILE.parent / B.OP_TOKEN_FILE


def token(raw):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_bytes(raw)


app = QApplication(sys.argv)
app.setApplicationName("browser-shot")


def pump(until, limit=30.0):
    end = time.time() + limit
    while time.time() < end and not until():
        app.processEvents()
        time.sleep(0.02)
    return until()


# ------------------------------------------------------------------ S3
print("\nS3: `op` hangs and the window still opens")
os.environ["MOCK_OP_FAIL"] = "hang"
Path(os.environ["MOCK_OP_STORE"]).write_text(json.dumps({"items": []}))
config()
token(b"mock-service-account-token\n")

started = time.time()
win = B.Browser()
boot = time.time() - started
check("Browser() did not wait for op", boot < 2.0, "%.1fs" % boot)
check("it opened on the file vault meanwhile",
      win.vault.provider.name == "file", win.vault.provider.name)
check("and says which store it is still reaching for",
      win.vault_checking == "1password", win.vault_checking)

started = time.time()
reply = win.bridge.vaultProviders(win._page_key)
took = time.time() - started
check("vaultProviders answered at once", took < 0.5, "%.1fs" % took)
check("with a ticket, not a list", "pending" in json.loads(reply), reply)

started = time.time()
blob = json.loads(win.bridge.getVault(win._page_key))
took = time.time() - started
check("getVault answered at once too", took < 0.5, "%.1fs" % took)
check("and the page is told the store is still being reached for",
      blob.get("checking") == "1password", blob.get("checking"))

started = time.time()
summary = json.loads(win.bridge.passwordSummary())
took = time.time() - started
check("so did the settings summary", took < 0.5, "%.1fs" % took)
check("and the file vault it is running on really can do health",
      summary.get("healthNA") is False, summary)
win.close()
os.environ.pop("MOCK_OP_FAIL")

# ------------------------------------------------------------------ S2
print("\nS2: a token file that could never be a token")
for name, raw in (("a UTF-16 paste", "ops_abcdef".encode("utf-16")),
                  ("a NUL byte", b"ops_ab\x00cdef\n"),
                  ("half a line", b"\xff\xfe\x00")):
    token(raw)
    config()
    try:
        broken = B.Browser()
        opened = True
    except Exception as exc:            # noqa: BLE001 - that is the point
        broken, opened = None, False
        print("    raised:", exc)
    check("%s still gives a window" % name, opened)
    if broken is None:
        continue
    pump(lambda: broken.vault_checking == "")
    check("%s falls back and says why" % name,
          broken.vault_fell_back == "bad-token", broken.vault_fell_back)
    check("%s left the file vault in charge" % name,
          broken.vault.provider.name == "file")
    broken.close()

# ------------------------------------------------------------------ 1
print("\nthe good path still works, asynchronously")
Path(os.environ["MOCK_OP_STORE"]).write_text(json.dumps({"items": []}))
seed = B.OnePasswordProvider(B.CONFIG_FILE.parent, vault_name="Browser")
seed.write_token("mock-service-account-token")
seed.put({"type": "login", "title": "GitHub", "host": "github.com",
          "scheme": "https", "username": "user", "password": "op-side-secret"})
seed.put({"type": "login", "title": "Bank", "host": "bank.example",
          "scheme": "https", "username": "10023455", "password": "another"})
config()
win = B.Browser()
check("the store swapped in once op answered",
      pump(lambda: win.vault.provider.name == "1password"),
      win.vault.provider.name)
check("with what op has in it", len(win.vault.items()) == 2,
      len(win.vault.items()))
check("and nothing to explain away", win.vault_fell_back == "",
      win.vault_fell_back)

# ------------------------------------------------------------------ 2
print("\nD1: a rename under 1Password reaches 1Password")
first = win.vault.logins()[0]
result = win.vault.update_item(first["id"], {"title": "NEW TITLE",
                                             "tags": ["work", "new"]})
check("update_item says it saved", result is not None)
check("the row on screen shows the new name",
      win.vault.item(first["id"])["title"] == "NEW TITLE",
      win.vault.item(first["id"])["title"])
elsewhere = B.OnePasswordProvider(B.CONFIG_FILE.parent, vault_name="Browser")
stored = {i["title"]: i for i in (elsewhere.load().get("items") or [])}
check("and so does the store, read back from scratch",
      "NEW TITLE" in stored, sorted(stored))
check("with the tag that was typed beside it",
      sorted(stored.get("NEW TITLE", {}).get("tags") or []) == ["new", "work"],
      stored.get("NEW TITLE", {}).get("tags"))

print("\nD1: export does not offer a file it cannot fill")
out = json.loads(win.bridge.exportPasswords(win._page_key))
check("the bridge says no rather than writing empty passwords",
      out.get("unavailable") is True, out)
check("nothing was written", "path" not in out, out)
check("and the page greys the button out",
      "exportBtn.disabled" in (HERE / "passwords.html").read_text())

print("\nthe token is revoked mid-session")
item = win.vault.item(win.vault.logins()[0]["id"])
was = dict(item)
seed.write_token("revoked")
win.vault.provider.forget_status()

result = win.vault.update_item(item["id"], {"title": "renamed by hand"})
check("update_item reports the refusal instead of the item", result is None,
      result)
check("and the row on screen still says what the store says",
      win.vault.item(item["id"])["title"] == was["title"],
      win.vault.item(item["id"])["title"])
saved = win.bridge.saveItem(win._page_key, json.dumps(
    {"id": item["id"], "type": "login", "title": "renamed by hand"}))
ticket = json.loads(saved).get("pending")
check("the page is given a ticket, not a freeze", bool(ticket), saved)

got = {}
win.bridge.vaultSecret.connect(lambda t, p: got.__setitem__(t, json.loads(p)))
check("and the answer that comes back says it did not save",
      pump(lambda: ticket in got) and got[ticket].get("ok") is False,
      got.get(ticket))

before = len(win.vault.items())
check("delete_item reports the refusal instead of True",
      win.vault.delete_item(item["id"]) is False)
check("and the row is still there, because the item still is",
      len(win.vault.items()) == before and win.vault.item(item["id"]))
blob = json.loads(win.bridge.getVault(win._page_key))
check("the store bar stops claiming everything is fine",
      blob.get("ok") is False, blob.get("ok"))
check("and says what it is", "valid" in str(blob.get("reason", "")),
      blob.get("reason"))

print("\nthe settings summary does not imply a clean bill of health")
summary = json.loads(win.bridge.passwordSummary())
check("it says the check could not run", summary.get("healthNA") is True,
      summary)
check("and reports no flags, because it has none to report",
      summary.get("health") == {}, summary.get("health"))
settings_src = (HERE / "settings.html").read_text()
check("settings.html actually shows that caveat",
      "d.healthNA" in settings_src)
check("the summary says the store does not keep anything here",
      summary.get("eager") is False, summary.get("eager"))
check("and settings.html hides the scrambled-on-this-computer line for it",
      'd.eager === false ? "none" : ""' in settings_src)
check("the inline manager is gone from settings.html, markup and all",
      not any(x in settings_src for x in
              ("pwlist", "pwnever", "pwsavebtn", "renderPasswords",
               "listPasswords", "revealPassword", "copyPassword",
               "setPassword", "deletePassword", "removeNeverSite")))
check("but the privacy switch that is not part of it stayed",
      'id="savepasswords"' in settings_src)

print("\nthe save prompt points at the generator")
win._password_prompt("example.com", "user", False)
labels = [w.text() for w in win._toast.findChildren(type(win._toast_label))]
check("the prompt names the shortcut",
      any("Ctrl+Shift+G" in t for t in labels), labels)
check("and still never shows the password",
      not any("secret" in t.lower() for t in labels), labels)
win._pw_dismiss()

print("\nthe export file is never readable by anyone else")
out = SCRATCH / "export.csv"
out.write_text("stale, world readable")
out.chmod(0o644)
win.vault.add_item({"type": "login", "host": "evil.example",
                    "username": "user", "password": "=cmd|' /C calc'!A0"})
written = win.write_export(str(out))
check("it wrote", written.get("written"), written)
check("0600, even over a file that was 0644",
      oct(out.stat().st_mode)[-3:] == "600", oct(out.stat().st_mode))
check("and no cell in it can be run by a spreadsheet",
      "\n=cmd" not in out.read_text() and ",=cmd" not in out.read_text(),
      out.read_text()[:200])

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)

# This one boots several browsers on purpose, one of them against an
# `op` that never returns. Unwinding QtWebEngine from under that is
# not something this test has anything to say about, and a teardown
# crash would read as a failed check, so the answer is reported and
# the process leaves without going back through it.
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if fails else 0)
