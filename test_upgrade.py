#!/usr/bin/env python3
"""A true cross-version test: the browser as it was BEFORE any of this
work writes a vault, and the browser as it is now reads it.

The old code is checked out of git rather than imitated, so this proves
the real upgrade path — the one your own passwords.json will take —
without ever going near your file. Then it goes back the other way:
the old build reads a vault the new one wrote, because a downgrade
should not lose your logins either.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = Path(__file__).resolve().parent
BASE = os.environ.get("OLD_REV", "b791f0e")

TMP = Path(tempfile.mkdtemp(prefix="upgrade-"))
OLD = HERE / "_oldbrowser_undertest.py"
OLD.write_bytes(subprocess.run(["git", "-C", str(HERE), "show",
                                "%s:browser.py" % BASE],
                               capture_output=True, check=True).stdout)
sys.path.insert(0, str(HERE))

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


try:
    import _oldbrowser_undertest as OLDB
    import browser as NEW

    print("\nthe old build writes a vault (%s)" % BASE)
    d = TMP / "vault"
    d.mkdir(parents=True)
    old_vault = OLDB.PasswordVault(d)
    old_vault.set_entry("github.com", "https", "user", "hunter2")
    old_vault.set_entry("amazon.de", "https", "user@example.com", "Sommer#2019")
    old_vault.set_entry("intranet.local", "http", "", "no-username-here")
    old_vault.never("tracker.example")
    check("the old build really is the old one",
          not hasattr(OLDB, "generate_password")
          and hasattr(OLDB.PasswordVault, "public_entries"))
    check("it wrote the format we expect",
          (d / "passwords.json").read_bytes()[:4] == b"BPW1")
    check("three logins in it", len(old_vault.data["entries"]) == 3)

    print("\nthe new build reads it")
    new_vault = NEW.PasswordVault(d)
    check("all three came across", len(new_vault.logins()) == 3,
          len(new_vault.logins()))
    check("passwords intact",
          new_vault.get("github.com", "user")["password"] == "hunter2"
          and new_vault.get("amazon.de", "user@example.com")["password"]
          == "Sommer#2019")
    check("an empty username survives",
          new_vault.get("intranet.local", "")["password"] == "no-username-here")
    check("schemes intact",
          new_vault.get("intranet.local", "")["scheme"] == "http")
    check("never-list came across", new_vault.is_never("tracker.example"))
    check("everything got an id and a type",
          all(i.get("id") and i.get("type") == "login"
              for i in new_vault.items()))
    check("autofill still finds them",
          new_vault.best_for("github.com", "https")["username"] == "user")

    print("\nand writing it back does not disturb anything")
    new_vault.add_item({"type": "note", "title": "wifi", "body": "secret"})
    again = NEW.PasswordVault(d)
    check("still three logins", len(again.logins()) == 3)
    check("plus the new note", len(again.items()) == 4)
    check("running the upgrade twice adds nothing",
          len(NEW.PasswordVault(d).items()) == 4)

    print("\nand the old build can still read what the new one wrote")
    back = OLDB.PasswordVault(d)
    check("the old build still finds its logins",
          len(back.data["entries"]) == 3, len(back.data["entries"]))
    check("with the right passwords",
          back.get("github.com", "user")["password"] == "hunter2")
    check("and its never-list",
          back.is_never("tracker.example"))

    print("\nnothing anywhere near the real vault")
    real = Path.home() / ".local/share/browser/passwords.json"
    check("this test never opened it",
          str(real) not in str(d) and d.is_relative_to(TMP))
finally:
    OLD.unlink(missing_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
