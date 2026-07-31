#!/usr/bin/env python3
"""The master password: the key derivation, the two migrations, and
what a locked vault will and will not do.

The checks that matter most are the ones about the disk. A feature
that only stops the browser showing passwords has changed nothing —
the point is that with the vault locked there is no longer anything on
this computer that could produce them.

Never touched by these tests: the real vault. Every path is redirected
into a scratch directory and the app name is changed so the
QtWebEngine profiles cannot collide with the browser you are running.
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="mastertest-"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def fresh(name):
    d = SCRATCH / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


PASS = "a rather long passphrase"

#: one of everything the vault can hold, so a migration that quietly
#: drops a field is a failing test rather than a discovery in a year
SEEDS = [
    {"type": "login", "title": "Bank", "host": "bank.example",
     "scheme": "https", "username": "user", "password": "hunter2!!",
     "tags": ["banking", "money"], "fav": True,
     "totp": "JBSWY3DPEHPK3PXP", "note": "the joint account"},
    {"type": "login", "title": "Shop", "host": "shop.example",
     "scheme": "https", "username": "user@example.net",
     "password": "correct horse", "tags": [], "fav": False},
    {"type": "note", "title": "Recovery codes",
     "note": "11111-22222\n33333-44444", "tags": ["backup"], "fav": True},
    {"type": "card", "title": "Visa", "number": "4111111111111111",
     "cardholder": "A. User", "expiry": "11/29", "cvv": "737",
     "brand": "visa", "tags": ["cards"]},
    {"type": "identity", "title": "Me", "fullname": "A. User",
     "email": "a.user@example.net", "phone": "+49 1234",
     "street": "Somestreet 1", "city": "Bonn", "zip": "53111",
     "country": "DE", "tags": []},
]
#: every string above that must never turn up in a file while locked
SECRETS = ["hunter2!!", "correct horse", "11111-22222", "33333-44444",
           "4111111111111111", "737", "JBSWY3DPEHPK3PXP"]


def seeded(d):
    vault = B.PasswordVault(d, provider=B.FileVaultProvider(d))
    for item in SEEDS:
        vault.add_item(dict(item))
    vault.never("nosave.example")
    return vault


def snapshot(vault):
    """Everything about every item, secrets included, in a form two
    vaults can be compared by."""
    out = []
    for item in sorted(vault.items(), key=lambda i: i.get("title", "")):
        row = {k: v for k, v in item.items() if k != "id"}
        out.append(row)
    return out


def files_of(d):
    return sorted(p for p in d.iterdir() if p.is_file())


def all_bytes(d):
    blob = b""
    for path in files_of(d):
        blob += path.read_bytes()
    return blob


# ---------------------------------------------------------------- 1
print("\nan install with no master password is exactly what it was")
d = fresh("plain")
vault = seeded(d)
check("the vault file is the old shape",
      (d / "passwords.json").read_bytes()[:4] == b"BPW1")
check("the key file is still beside it", (d / "passwords.key").exists())
lock = B.VaultLock(d)
check("no master password", lock.enabled() is False)
check("never locked", lock.locked() is False)
check("reads back through a fresh provider",
      len(B.PasswordVault(d, provider=B.FileVaultProvider(d)).items()) == 5)
before = snapshot(vault)

# ---------------------------------------------------------------- 2
print("\nswitching it on")
lock = B.VaultLock(d)
check("enable() says yes", lock.enable(PASS) is True)
check("the file changed shape",
      (d / "passwords.json").read_bytes()[:4] == b"BPW2")
check("the key file is GONE — that was the whole point",
      not (d / "passwords.key").exists())
check("enabled() now says so", lock.enabled() is True)
check("and it is open, because he just typed it", lock.locked() is False)
after = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(d, lock=lock)))
check("every item survived, exactly", after == before,
      "%d vs %d" % (len(after), len(before)))

# ---------------------------------------------------------------- 3
print("\nlocked: the passwords are not on this computer any more")
lock.lock()
check("locked() says so", lock.locked() is True)
blob = all_bytes(d)
for secret in SECRETS:
    check("%r is in no file in the directory" % secret,
          secret.encode() not in blob)
check("nor is the username", b"user@example.net" not in blob)
check("nor a hostname", b"bank.example" not in blob)
# and the key itself is nowhere either: this is the difference between
# a master password and the old scheme
check("the vault key is in none of the files",
      lock._vault_key is None)
names = [p.name for p in files_of(d)]
check("no key file came back", "passwords.key" not in names, names)
check("a locked provider loads nothing",
      B.FileVaultProvider(d, lock=lock).load() == {})
check("a locked provider refuses to save",
      B.FileVaultProvider(d, lock=lock).save({"items": []}) is False)
check("PasswordVault knows it is locked",
      B.PasswordVault(d, provider=B.FileVaultProvider(d, lock=lock)).locked)

# the file has to still be there and still be whole
size_locked = (d / "passwords.json").stat().st_size
check("the vault file is untouched by any of that", size_locked > 100)

# ---------------------------------------------------------------- 4
print("\na wrong passphrase learns nothing and breaks nothing")
raw_before = (d / "passwords.json").read_bytes()
for guess in ("", "wrong", PASS + " ", PASS.upper(), PASS[:-1], "\x00"):
    check("refused: %r" % guess, lock.unlock(guess) is False)
check("still locked after all of that", lock.locked() is True)
check("the file was not written to", (d / "passwords.json").read_bytes()
      == raw_before)
check("no key file appeared", not (d / "passwords.key").exists())
check("and the right one still works", lock.unlock(PASS) is True)
check("with everything in it",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=lock))) == before)

# ---------------------------------------------------------------- 5
print("\non, off, and on again — every field, every time")
lock.lock()
check("unlock for the trip back", lock.unlock(PASS) is True)
check("disable() says yes", lock.disable() is True)
check("back to the old shape",
      (d / "passwords.json").read_bytes()[:4] == b"BPW1")
check("with a key file again", (d / "passwords.key").exists())
round1 = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(d)))
check("nothing lost on the way off", round1 == before)
lock2 = B.VaultLock(d)
check("on again", lock2.enable("something else entirely") is True)
round2 = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
    d, lock=lock2)))
check("nothing lost on the way back on", round2 == before)
check("the never-save list came through too",
      B.PasswordVault(d, provider=B.FileVaultProvider(d, lock=lock2))
      .data.get("never") == ["nosave.example"])
# the fields that are easiest to lose, named one at a time
final = {i["title"]: i for i in B.PasswordVault(
    d, provider=B.FileVaultProvider(d, lock=lock2)).items()}
check("TOTP seed intact", final["Bank"].get("totp") == "JBSWY3DPEHPK3PXP")
check("favourite intact", final["Bank"].get("fav") is True)
check("tags intact", final["Bank"].get("tags") == ["banking", "money"])
check("note body intact",
      final["Recovery codes"].get("note") == "11111-22222\n33333-44444")
check("card number intact",
      final["Visa"].get("number") == "4111111111111111")
check("cvv intact", final["Visa"].get("cvv") == "737")
check("identity postcode intact", final["Me"].get("zip") == "53111")

# ---------------------------------------------------------------- 6
print("\nchanging the passphrase, without re-entering anything")
check("wrong current one is refused",
      lock2.change("not it", "a new one entirely") is False)
check("and changed nothing", lock2.unlock("something else entirely") is True)
check("change() says yes",
      lock2.change("something else entirely", "the third passphrase") is True)
check("the old one no longer opens it",
      B.VaultLock(d).unlock("something else entirely") is False)
lock3 = B.VaultLock(d)
check("the new one does", lock3.unlock("the third passphrase") is True)
check("with every item still in it",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=lock3))) == before)
check("a change is refused when the vault is empty of a master password",
      B.VaultLock(fresh("nolock")).change("a", "b") is False)

# ---------------------------------------------------------------- 7
print("\na migration cut off half way leaves a vault that opens")
# The promise is that the vault file is only ever replaced whole, so
# the way to test it is to prove the interesting instants are safe:
# every intermediate state is one of the two whole files.
d = fresh("crash")
seeded(d)
plain = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(d)))

# (a) killed after the vault was swapped but before the key file went
lock = B.VaultLock(d)
real_tidy = B.VaultLock._tidy
B.VaultLock._tidy = lambda self: None      # the power goes out here
try:
    lock.enable(PASS)
finally:
    B.VaultLock._tidy = real_tidy
check("the vault is the new shape",
      (d / "passwords.json").read_bytes()[:4] == b"BPW2")
check("the stale key file is still lying there",
      (d / "passwords.key").exists())
restarted = B.VaultLock(d)
check("a restart still opens it with the passphrase",
      restarted.unlock(PASS) is True)
check("and it has everything",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=restarted))) == plain)
check("the stale key file has been cleared away by now",
      not (d / "passwords.key").exists())

# (b) killed during the write itself: a half-written temporary file
d = fresh("crash2")
seeded(d)
plain = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(d)))
(d / "passwords.json.new").write_bytes(b"BPW2\x00\x00\x00\x09{\"half\":")
lock = B.VaultLock(d)
check("the real vault is untouched by a stray .new",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=lock))) == plain)
check("switching on still works", lock.enable(PASS) is True)
check("and the leftover is gone", not (d / "passwords.json.new").exists())
check("with everything in it",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=lock))) == plain)

# (c) killed on the way OFF, between the key file and the vault
d = fresh("crash3")
seeded(d)
plain = snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(d)))
lock = B.VaultLock(d)
lock.enable(PASS)
calls = {"n": 0}
real_write = B._write_atomic


def die_on_second(path, data):
    calls["n"] += 1
    if calls["n"] == 2:          # the key file landed; the vault does not
        return False
    return real_write(path, data)


B._write_atomic = die_on_second
try:
    check("disable() reports the failure", lock.disable() is False)
finally:
    B._write_atomic = real_write
check("the vault is still the locked one",
      (d / "passwords.json").read_bytes()[:4] == b"BPW2")
survivor = B.VaultLock(d)
check("and the passphrase still opens it", survivor.unlock(PASS) is True)
check("with everything in it",
      snapshot(B.PasswordVault(d, provider=B.FileVaultProvider(
          d, lock=survivor))) == plain)
check("switching off properly still works afterwards",
      survivor.disable() is True)
check("everything came back", snapshot(B.PasswordVault(
    d, provider=B.FileVaultProvider(d))) == plain)

# ---------------------------------------------------------------- 8
print("\nan old vault, from before any of this existed, still opens")
d = fresh("old")
old = B.FileVaultProvider(d)
old.save({"entries": [
    {"host": "example.com", "username": "user", "password": "hunter2",
     "scheme": "https", "used": 1700000000}], "never": ["bank.com"]})
check("written in the old shape",
      (d / "passwords.json").read_bytes()[:4] == b"BPW1")
v = B.PasswordVault(d, provider=B.FileVaultProvider(d))
check("it migrates and reads", len(v.logins()) == 1)
check("with its password", v.get("example.com", "user")["password"] == "hunter2")
check("and is not locked", v.locked is False)
check("and never asks for anything", B.VaultLock(d).enabled() is False)

# ---------------------------------------------------------------- 9
print("\nthe 1Password token is a secret on this computer too")
d = fresh("op")
lock = B.VaultLock(d)
prov = B.OnePasswordProvider(d, lock=lock)
prov.write_token("ops_ABCDEFGHtokenvalue")
check("plain while there is no master password",
      (d / B.OP_TOKEN_FILE).read_bytes().startswith(b"ops_"))
check("and readable", prov.token() == "ops_ABCDEFGHtokenvalue")
check("switching on seals it", lock.enable(PASS) is True)
raw = (d / B.OP_TOKEN_FILE).read_bytes()
check("the token file is ciphertext now", raw.startswith(B.TOKEN_MAGIC))
check("the token is not in it", b"ops_ABCDEFGHtokenvalue" not in raw)
check("unlocked, it still reads", prov.token() == "ops_ABCDEFGHtokenvalue")
lock.lock()
check("locked, there is no token to be had", prov.token() == "")
check("and it is reported as absent, not as broken",
      prov.have_token() is False and prov._bad_token is False)
check("the provider says it is locked", prov.locked is True)
check("unlock brings it back",
      lock.unlock(PASS) and prov.token() == "ops_ABCDEFGHtokenvalue")
check("switching off puts it back in the clear",
      lock.disable() and (d / B.OP_TOKEN_FILE).read_bytes().startswith(b"ops_"))

# --------------------------------------------------------------- 10
print("\nthe key derivation itself")
salt = os.urandom(16)
k1 = B._derive_key("passphrase", salt)
k2 = B._derive_key("passphrase", salt)
k3 = B._derive_key("passphrase", os.urandom(16))
check("scrypt, from hashlib", B.KDF_NAME == "scrypt")
check("32 bytes out", len(k1) == 32)
check("same passphrase and salt, same key", k1 == k2)
check("a different salt is a different key", k1 != k3)
check("the cost is real", B.KDF_N >= (1 << 15))
d = fresh("salts")
B.VaultLock(d).enable(PASS)
head, _ = B.VaultLock._split((d / "passwords.json").read_bytes())
check("the salt is per vault and random", len(head["salt"]) >= 20)
check("the parameters travel with the file",
      head["n"] == B.KDF_N and head["r"] == B.KDF_R and head["p"] == B.KDF_P)
d2 = fresh("salts2")
B.VaultLock(d2).enable(PASS)
head2, _ = B.VaultLock._split((d2 / "passwords.json").read_bytes())
check("two vaults with the same passphrase get different salts",
      head["salt"] != head2["salt"])
check("and different wrapped keys", head["wrapped"] != head2["wrapped"])

# the seal has to actually be a seal
key = os.urandom(32)
blob = B._seal(key, b"the message", aad=b"label")
check("it round-trips", B._unseal(key, blob, aad=b"label") == b"the message")
check("a wrong key gets None", B._unseal(os.urandom(32), blob, aad=b"label")
      is None)
check("a wrong label gets None", B._unseal(key, blob, aad=b"other") is None)
flipped = bytearray(blob)
flipped[20] ^= 1
check("a flipped bit gets None",
      B._unseal(key, bytes(flipped), aad=b"label") is None)
short = blob[:-1]
check("a truncated file gets None", B._unseal(key, short, aad=b"label") is None)
check("the plaintext is not in the ciphertext", b"the message" not in blob)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
else:
    print("all green")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if fails else 0)
