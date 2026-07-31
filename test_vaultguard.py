#!/usr/bin/env python3
"""A vault this build does not understand is never read as empty and
never written over.

The failure this exists to stop is the worst one a password manager
has: an older build meets a newer build's vault, reads it as no
passwords at all, and its first save replaces every password with that
nothing. Silently. The Windows edition is regenerated from the Linux
one every so often and `git checkout` of an older commit costs
nothing, so this is not a hypothetical ordering.

Never touches your own data: everything is under a scratch directory.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCRATCH = Path(tempfile.mkdtemp(prefix="vaultguard-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
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


def known_magic():
    """Every vault shape this build understands, wherever it keeps the
    list. On main that is the provider; once a master password exists
    the lock owns the file and therefore the list."""
    for holder in (getattr(B, "VaultLock", None), B.FileVaultProvider):
        magic = getattr(holder, "KNOWN_MAGIC", None)
        if magic:
            return tuple(magic)
    raise AssertionError("no build knows nothing")


def newer_magic():
    """A four-byte magic this build has never heard of.

    Worked out rather than written down. "BPW2" was the obvious stand-in
    for "a newer build" right up until a newer build actually used it,
    at which point a hard-coded one would quietly stop testing anything
    -- the file would be perfectly readable and every check would pass
    for the wrong reason."""
    known = known_magic()
    for candidate in [b"BPW%d" % n for n in range(2, 10)] + [b"ZZZZ"]:
        if candidate not in known:
            return candidate
    raise AssertionError("this build claims to know every shape there is")


MAGIC_NEWER = newer_magic()
#: what a newer build's vault looks like from here: a magic this one
#: has never heard of, and bytes it cannot make sense of
NEWER = MAGIC_NEWER + b"\x00\x00\x01\x2c" + os.urandom(300)

# ---------------------------------------------------------------- 1
print("\nstanding in for a newer build with magic %s"
      % MAGIC_NEWER.decode())
check("it really is a shape this build does not know",
      MAGIC_NEWER not in known_magic(), known_magic())

print("\nan ordinary vault is completely unaffected")
d = fresh("normal")
p = B.FileVaultProvider(d)
p.save({"items": [{"id": "1", "type": "login", "host": "example.com",
                   "username": "user", "password": "hunter2"}], "never": []})
check("written", (d / "passwords.json").read_bytes()[:4] == b"BPW1")
check("not foreign", p.foreign() is False)
check("status is ok", p.status()["ok"] is True)
check("reads back", p.load()["items"][0]["password"] == "hunter2")
check("saves again", p.save(p.load()) is True)
v = B.PasswordVault(d, provider=B.FileVaultProvider(d))
check("through PasswordVault too", len(v.items()) == 1)

# ---------------------------------------------------------------- 2
print("\na fresh install is not mistaken for a foreign vault")
d = fresh("empty")
p = B.FileVaultProvider(d)
check("no file at all: not foreign", p.foreign() is False)
check("and it can be written", p.save({"items": [], "never": []}) is True)
d = fresh("zero")
(d / "passwords.json").write_bytes(b"")
p = B.FileVaultProvider(d)
check("a zero-byte file: not foreign", p.foreign() is False)
check("and it can be written over", p.save({"items": [], "never": []}) is True)

# ---------------------------------------------------------------- 3
print("\na vault from a newer build is refused, not guessed at")
d = fresh("newer")
vault_file = d / "passwords.json"
vault_file.write_bytes(NEWER)
before = vault_file.read_bytes()
p = B.FileVaultProvider(d)
check("foreign() says so", p.foreign() is True)
check("status is not ok", p.status()["ok"] is False)
check("and names the reason", p.status()["reason"] == "vault-newer",
      p.status()["reason"])
check("load hands out nothing", p.load() == {})
check("SAVE REFUSES", p.save({"items": [], "never": []}) is False)
check("and the file is byte-for-byte what it was",
      vault_file.read_bytes() == before)

# ---------------------------------------------------------------- 4
print("\nthe whole destruction, replayed end to end")
# This is the reported scenario: a browser starts on the newer vault,
# the user does the most ordinary thing there is -- signs in somewhere
# -- and every password is gone. Each step below is what actually ran.
d = fresh("replay")
vault_file = d / "passwords.json"
vault_file.write_bytes(NEWER)
before = vault_file.read_bytes()
v = B.PasswordVault(d, provider=B.FileVaultProvider(d))
check("the vault looks empty in memory, as it must", len(v.items()) == 0)
check("but it knows the store is unhappy",
      v.provider.status()["ok"] is False)
saved = v.set_entry("example.com", "https", "user", "newpassword")
check("saving a login reports failure rather than succeeding",
      not saved, saved)
check("THE FILE SURVIVED", vault_file.read_bytes() == before)
check("still the newer shape",
      vault_file.read_bytes()[:4] == MAGIC_NEWER)
v.never("nosave.example")
check("the never-save list cannot destroy it either",
      vault_file.read_bytes() == before)
item = v.add_item({"type": "note", "title": "x", "note": "y"})
check("adding an item cannot destroy it either",
      vault_file.read_bytes() == before)
if item and item.get("id"):
    v.delete_item(item["id"])
    check("nor can deleting one", vault_file.read_bytes() == before)
imported = v.import_csv("url,username,password\nx.example,a,b\n")
check("nor can a CSV import", vault_file.read_bytes() == before,
      imported)

# ---------------------------------------------------------------- 5
print("\nthe browser says so, in words, on both pages")
strings = B.UI_STRINGS
check("there is an English sentence for it", "pwVaultNewer" in strings["en"])
check("and a German one", "pwVaultNewer" in strings["de"])
check("it says nothing is lost",
      "lost" in strings["en"]["pwVaultNewer"].lower())
page = (Path(__file__).resolve().parent / "passwords.html").read_text()
check("the manager maps the reason to that sentence",
      'reason === "vault-newer"' in page and "pwVaultNewer" in page)
settings = (Path(__file__).resolve().parent / "settings.html").read_text()
check("and so does the settings line",
      'vault-newer' in settings and "pwVaultNewer" in settings)

# ---------------------------------------------------------------- 6
print("\nrecovery: the newer build still opens it afterwards")
# Refusing has to be reversible, which is the whole argument for
# refusing. Nothing this build did may stand in the newer one's way.
d = fresh("recover")
vault_file = d / "passwords.json"
vault_file.write_bytes(NEWER)
p = B.FileVaultProvider(d)
p.load()
p.save({"items": [], "never": []})
p.foreign()
check("after everything this build tried, the bytes are untouched",
      vault_file.read_bytes() == NEWER)
check("and no key file was minted over it",
      not (d / "passwords.key").exists() or
      (d / "passwords.key").read_bytes() != NEWER)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
else:
    print("all green")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if fails else 0)
