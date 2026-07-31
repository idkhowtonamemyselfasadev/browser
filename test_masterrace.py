#!/usr/bin/env python3
"""The review findings, each with the failure it reported reproduced
first and then shown not to happen.

The one that mattered: a 1Password fetch started while the vault was
open lands after it has been locked, and repopulates a locked browser's
vault with plaintext passwords. `make_vault` refused to *start* such a
fetch while locked, but nothing checked the way back in, and a worker
thread cannot be recalled — `op` is allowed twenty seconds.

Never touches your own data.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="masterrace-"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

cfg = SCRATCH / "cfg"
cfg.mkdir(parents=True, exist_ok=True)
for name in ("CONFIG_FILE", "HISTORY_FILE", "DOWNLOADS_FILE", "HOSTS_FILE",
             "BOOKMARKS_FILE"):
    setattr(B, name, cfg / (name.lower() + ".json"))
B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": True}))

app = QApplication.instance() or QApplication(sys.argv)
app.setApplicationName("browser-shot")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


PASS = "a long enough passphrase"
#: what the worker thread comes back holding: 1Password's answer, with
#: the passwords in it
OP_SNAPSHOT = {"version": 2, "items": [
    {"id": "op1", "type": "login", "host": "work.example", "scheme": "https",
     "username": "user@work.example", "password": "OP-SECRET-PASSWORD",
     "title": "Work"},
    {"id": "op2", "type": "login", "host": "work.example", "scheme": "https",
     "username": "user@home.example", "password": "OP-OTHER-PASSWORD",
     "title": "Home"}], "never": []}

win = B.Browser()
win.show()

# ---------------------------------------------------------------- 1
print("\na 1Password fetch that lands after the lock is dropped")
win.vault.set_entry("work.example", "https", "user", "localpw")
win.vault._save()
check("enable a master password", win.vault_lock.enable(PASS) is True)
win.vault = win.make_vault()

provider = B.OnePasswordProvider(B.CONFIG_FILE.parent, lock=win.vault_lock)
result = ("1password", provider, {"ok": True, "reason": ""}, OP_SNAPSHOT)
win.config["passwordProvider"] = "1password"

win.lock_vault()
check("the browser is locked", win.vault_locked() is True)
check("and holds nothing", len(win.vault.items()) == 0)

# the worker thread's answer arrives now, exactly as _vault_reached
# would be handed it
win._vault_reached(result)

check("STILL holds nothing", len(win.vault.items()) == 0,
      [i.get("username") for i in win.vault.items()])
check("no account names to list", win._account_names() == [],
      win._account_names())
check("the store did not swap in under the lock",
      win.vault.provider.name == "file", win.vault.provider.name)
check("still locked", win.vault_locked() is True)
blob = json.dumps(win.vault.data)
check("no 1Password password anywhere in the vault",
      "OP-SECRET-PASSWORD" not in blob and "OP-OTHER-PASSWORD" not in blob)

# ---------------------------------------------------------------- 2
print("\nadopt() refuses onto a locked vault whoever calls it")
took = win.vault.adopt(provider, OP_SNAPSHOT)
check("adopt says no", took is False)
check("and took nothing", len(win.vault.items()) == 0)

# ---------------------------------------------------------------- 3
print("\nthe epoch drops every job that was already in flight")
delivered = []
win.vault_job(lambda: "an answer from before", delivered.append)
win.lock_vault()      # already locked, so force the epoch on by hand
win._vault_epoch += 1
for _ in range(60):
    app.processEvents()
    if delivered:
        break
check("a job started before the lock delivers nothing", delivered == [],
      delivered)
# and one started after it still works, or locking would break the browser
after = []
win.vault_job(lambda: "a fresh answer", after.append)
for _ in range(200):
    app.processEvents()
    if after:
        break
check("a job started after the lock still delivers", after == ["a fresh answer"],
      after)

# ---------------------------------------------------------------- 4
print("\nunlocking does not resurrect a dropped answer")
check("unlock", win.vault_lock.unlock(PASS) is True)
win.vault = win.make_vault()
check("the local login is back", win.vault.get("work.example", "user")
      is not None)
blob = json.dumps(win.vault.data)
check("and the 1Password snapshot never arrived",
      "OP-SECRET-PASSWORD" not in blob)

# ---------------------------------------------------------------- 5
print("\nunlocked, the same answer is taken normally")
win._vault_reached(("1password", provider, {"ok": True, "reason": ""},
                    OP_SNAPSHOT))
check("adopted when the vault is open", len(win.vault.items()) == 2,
      len(win.vault.items()))
check("with 1Password's accounts",
      sorted(i["username"] for i in win.vault.items())
      == ["user@home.example", "user@work.example"])
win.config["passwordProvider"] = "file"
win.vault = win.make_vault()

# ---------------------------------------------------------------- 6
print("\nthe two 'locked' questions agree (finding 3)")
win.config["vaultPassword"] = False
check("Vault Password is off", win.vault_password_on() is False)
win.lock_vault()
check("a locked vault still reports locked", win.vault_locked() is True)
answer = json.loads(win.bridge.getVault(win._page_key))
check("and the manager is not told 'nothing saved yet'",
      answer.get("locked") is True, answer)
check("the chooser raises no box with the feature off",
      win._account_names() == [])
win.config["vaultPassword"] = True
check("unlock again", win.vault_lock.unlock(PASS) is True)
win.vault = win.make_vault()

# ---------------------------------------------------------------- 7
print("\nunicode: an umlaut typed two ways is one passphrase (finding 4)")
d = SCRATCH / "nfc"
d.mkdir(parents=True, exist_ok=True)
lock = B.VaultLock(d)
B.FileVaultProvider(d, lock=lock).save(
    {"items": [{"id": "1", "type": "login", "host": "x.example",
                "username": "t", "password": "p"}], "never": []})
nfc = "Schönespassphrase"          # ö as one character
nfd = "Schönespassphrase"        # o + combining diaeresis
check("the two spellings really are different bytes",
      nfc.encode() != nfd.encode())
check("enable with the composed one", lock.enable(nfc) is True)
lock.lock()
check("the decomposed one opens it too", lock.unlock(nfd) is True)
lock.lock()
check("and so does the composed one", lock.unlock(nfc) is True)
check("a genuinely different passphrase still does not",
      B.VaultLock(d).unlock("Schonespassphrase") is False)

print("\nthe kdf name is checked, never dispatched on (finding 4)")
head, body = B.VaultLock._split((d / "passwords.json").read_bytes())
check("it is written", head.get("kdf") == "scrypt")
tampered = dict(head)
tampered["kdf"] = "something-else"
check("an unknown one is refused outright",
      B.VaultLock(d)._unwrap(tampered, nfc) is None)
check("and the real header still opens", B.VaultLock(d)._unwrap(head, nfc)
      is not None)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
else:
    print("all green")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if fails else 0)
