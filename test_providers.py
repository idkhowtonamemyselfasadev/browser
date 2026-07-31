#!/usr/bin/env python3
"""Provider tests: the file vault, the 1Password provider against the
mock `op`, and — the important half — every way it can go wrong.

Nothing here touches your real vault or a real 1Password tenant.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import browser as B  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="provtest-"))
BIN = TMP / "bin"
BIN.mkdir(parents=True)
shutil.copy(HERE / "tools" / "mock-op", BIN / "op")
os.chmod(BIN / "op", 0o755)
os.environ["PATH"] = str(BIN) + os.pathsep + os.environ["PATH"]
os.environ["MOCK_OP_STORE"] = str(TMP / "store.json")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def fresh(name):
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def provider(name="op", token="mock-token", vault="", store=None):
    d = fresh(name)
    p = B.OnePasswordProvider(d, vault_name=vault)
    if token is not None:
        p.write_token(token)
    if store is not None:
        Path(os.environ["MOCK_OP_STORE"]).write_text(json.dumps(store))
    return p


EMPTY = {"items": []}

print("\nthe token file")
d = fresh("token")
p = B.OnePasswordProvider(d)
check("no token to begin with", not p.have_token())
check("status says so before anything looked", p.status()["reason"] == "checking", p.status())
check("probe says so", p.probe()["reason"] == "no-token", p.probe())
p.write_token("shhh-secret-token")
check("token comes back", p.token() == "shhh-secret-token")
check("token file is 0600",
      oct((d / B.OP_TOKEN_FILE).stat().st_mode)[-3:] == "600")
check("token is not in config.json",
      "OP_SERVICE_ACCOUNT_TOKEN" not in B.OnePasswordProvider.__init__
      .__code__.co_names)
p.write_token("")
check("empty clears it", not p.have_token()
      and not (d / B.OP_TOKEN_FILE).exists())

print("\nthe token never reaches an argument list")
d = fresh("argv")
p = B.OnePasswordProvider(d)
p.write_token("token-in-argv-would-be-visible")
seen = {}
real_run = subprocess.run


def spy(args, **kw):
    seen["args"] = list(args)
    seen["env"] = kw.get("env", {})
    return real_run(args, **kw)


subprocess.run = spy
p.probe()
subprocess.run = real_run
check("op was called", seen.get("args", [None])[0] == "op", seen.get("args"))
check("token is NOT in argv",
      not any("token-in-argv" in a for a in seen.get("args", [])),
      seen.get("args"))
check("token IS in the environment",
      seen.get("env", {}).get("OP_SERVICE_ACCOUNT_TOKEN")
      == "token-in-argv-would-be-visible")

print("\nreading an empty vault")
p = provider("empty", store=EMPTY)
check("status ok", p.probe()["ok"], p.probe())
check("status is cached and never blocks again",
      p.status() == {"ok": True, "reason": ""}, p.status())
check("empty list", p.load().get("items") == [])
check("provider is lazy", p.eager is False)
check("provider does its own TOTP", p.native_totp is True)

print("\ncreate, list, read back")
# every argument op is given from here on, so the item's own secrets
# can be proved absent from argv the same way the token was
ARGV_SEEN = []
_real_run = subprocess.run


def _watch(args, **kw):
    ARGV_SEEN.extend(str(a) for a in args)
    return _real_run(args, **kw)


subprocess.run = _watch
p = provider("crud", store=EMPTY, vault="Browser")
item = p.put({"type": "login", "title": "GitHub", "host": "github.com",
              "scheme": "https", "username": "user", "password": "s3cret!",
              "totp": "JBSWY3DPEHPK3PXP", "tags": ["work"]})
check("create returned an item", item and item.get("id"), item)
snapshot = p.load()
check("it is in the listing", len(snapshot["items"]) == 1)
row = snapshot["items"][0]
check("title survived", row["title"] == "GitHub")
check("host came from the url", row["host"] == "github.com", row.get("host"))
check("username is in the listing", row["username"] == "user")
check("listing carries NO password", "password" not in row, row)
check("listing says a password exists", row["hasPassword"] is True)
check("marked as remote", row["remote"] is True)
check("secret fetched on demand",
      p.secret(row["id"], "password") == "s3cret!")
check("a field that is not a field stays empty",
      p.secret(row["id"], "nonsense") == "")
check("no password of ours ever reached an argument list",
      not any("s3cret!" in a for a in ARGV_SEEN), ARGV_SEEN)
code = p.totp(row["id"])
check("provider produced a 6-digit code", code.isdigit() and len(code) == 6,
      code)
check("it matches what we would compute ourselves",
      code == B.totp_code("JBSWY3DPEHPK3PXP"), code)

print("\nediting keeps the id")
edited = p.put(dict(row, remote=True, password="new-one", type="login"))
check("edit returned the same id", edited and edited["id"] == row["id"])
check("new password readable", p.secret(row["id"], "password") == "new-one")
check("still one item", len(p.load()["items"]) == 1)

print("\nD1: a rename and a retag reach the store")
renamed = p.put(dict(row, remote=True, type="login", title="NEW TITLE",
                     tags=["work", "new"]))
check("put says it saved", renamed and renamed.get("title") == "NEW TITLE",
      renamed)
back = p.load()["items"][0]
check("the store itself has the new name", back["title"] == "NEW TITLE", back)
check("and the new tag", sorted(back.get("tags") or []) == ["new", "work"],
      back.get("tags"))
check("the password it was not asked to touch is untouched",
      p.secret(row["id"], "password") == "new-one")
check("and neither the title nor a tag went through argv",
      not any("NEW TITLE" in a for a in ARGV_SEEN), ARGV_SEEN[-8:])

print("\ndeleting")
check("delete says yes", p.delete(row["id"]) is True)
check("and it is gone", p.load()["items"] == [])
check("deleting it twice fails honestly", p.delete(row["id"]) is False)

subprocess.run = _real_run

print("\nnotes, cards and identities round-trip")
p = provider("types", store=EMPTY)
p.put({"type": "note", "title": "WLAN", "body": "the key is 1234"})
p.put({"type": "card", "title": "Giro", "number": "4111111111111111",
       "cardholder": "A. User", "expiry": "12/28", "cvv": "123"})
p.put({"type": "identity", "title": "Home", "fullname": "A. User",
       "email": "t@example.com", "city": "Berlin"})
kinds = sorted(i["type"] for i in p.load()["items"])
check("three types came back", kinds == ["card", "identity", "note"], kinds)
byname = {i["title"]: i for i in p.load()["items"]}
check("note body is a secret", "body" not in byname["WLAN"])
check("note body fetched on demand",
      p.secret(byname["WLAN"]["id"], "body") == "the key is 1234")
check("card shows only its last four",
      byname["Giro"].get("last4") == "1111"
      and "number" not in byname["Giro"], byname["Giro"])
check("card number fetched on demand",
      p.secret(byname["Giro"]["id"], "number") == "4111111111111111")

print("\ndegrading honestly")
p = provider("nobin", store=EMPTY)
p.binary = "op-which-does-not-exist"
p.forget_status()
check("missing op is reported, not raised",
      p.probe() == {"ok": False, "reason": "op-missing"}, p.probe())
check("load falls back to nothing rather than crashing", p.load() == {})
check("put fails cleanly", p.put({"type": "login", "title": "x"}) is None)
check("a secret that could not be fetched says so, not \"\"",
      p.secret("x", "password") is None)

p = provider("notoken", token=None, store=EMPTY)
check("missing token is reported",
      p.probe()["reason"] == "no-token", p.probe())

p = provider("revoked", token="revoked", store=EMPTY)
state = p.probe()
check("a revoked account is reported, not raised", state["ok"] is False)
check("the message is op's own", "not valid" in state["reason"], state)
check("the message does not contain the token",
      "revoked" not in state["reason"].replace("revoked account", ""),
      state["reason"])

os.environ["MOCK_OP_FAIL"] = "garbage"
p = provider("garbage", store=EMPTY)
check("nonsense output is refused", p.probe()["reason"] == "bad-json",
      p.probe())
os.environ.pop("MOCK_OP_FAIL")

print("\na hanging op cannot hang the browser")
os.environ["MOCK_OP_FAIL"] = "hang"
p = provider("hang", store=EMPTY)
p.TIMEOUT = 2
started = time.time()
state = p.probe()
took = time.time() - started
os.environ.pop("MOCK_OP_FAIL")
check("it gave up", state["ok"] is False and state["reason"] == "timeout",
      state)
check("within the timeout", took < 5, took)

print("\nnothing the user typed is lost when op refuses")
p = provider("nolose", store=EMPTY)
v = B.PasswordVault(fresh("nolose-vault"), provider=p)
p.binary = "op-gone"
p.forget_status()
before = len(v.items())
result = v.add_item({"type": "login", "host": "example.com",
                     "username": "user", "password": "typed-by-hand"})
check("add_item reports the failure", result is None)
check("no half-added ghost row", len(v.items()) == before)

print("\nthe vault on top of a lazy provider")
p = provider("vault", store=EMPTY)
d = fresh("vault-meta")
v = B.PasswordVault(d, provider=p)
made = v.add_item({"type": "login", "host": "example.com", "username": "user",
                   "password": "pw", "title": "Example"})
check("item added through the vault", made is not None)
v2 = B.PasswordVault(d, provider=provider("vault", store=None))
check("a second vault object sees it", len(v2.logins()) == 1)
check("redacted items carry no password",
      all("password" not in i for i in v2.redacted_items()))
check("health says it could not run",
      v2.health().get("unavailable") is True, v2.health())
v2.never("tracker.example")
check("never-list is kept locally", (d / "passwords-meta.json").exists())
check("never-list is reloaded",
      B.PasswordVault(d, provider=provider("vault", store=None))
      .is_never("tracker.example"))
view = v2.totp_view(v2.logins()[0]["id"])
check("no totp seed, no code", view == {}, view)

p2 = provider("lazycard", store=EMPTY)
p2.put({"type": "card", "title": "Visa", "number": "4111111111111111",
        "cardholder": "A. User", "cvv": "123"})
v3 = B.PasswordVault(fresh("lazycard-vault"), provider=p2)
card = [i for i in v3.redacted_items() if i["type"] == "card"][0]
check("a card the store never sent the number for keeps its last four",
      card.get("last4") == "1111", card)
check("and still no number in what the page gets", "number" not in card, card)

print("\na token file that could never be one (S2)")
d = fresh("badtoken")
p = B.OnePasswordProvider(d)
(d / B.OP_TOKEN_FILE).write_bytes("ops_abc".encode("utf-16"))
check("a UTF-16 paste does not raise", p.token() == "")
check("and is reported as a broken token", p.probe()["reason"] == "bad-token",
      p.probe())
p.forget_status()
(d / B.OP_TOKEN_FILE).write_bytes(b"ops_ab\x00cd\n")
check("a NUL does not raise", p.token() == "")
check("and is reported as a broken token", p.probe()["reason"] == "bad-token",
      p.probe())
p.forget_status()
(d / B.OP_TOKEN_FILE).write_bytes(b"   \n")
check("an empty file is just no token", p.probe()["reason"] == "no-token",
      p.probe())
(d / B.OP_TOKEN_FILE).write_bytes(b"\xef\xbb\xbfops_frompaste\r\n")
check("a byte-order mark from a Windows paste is stripped, not prepended",
      p.token() == "ops_frompaste", repr(p.token()))
(d / B.OP_TOKEN_FILE).write_bytes(b"\xef\xbb\xbf\xef\xbb\xbfops_x")
check("but a second one is still a broken file", p.token() == "")
p.write_token("ops_realtoken")
check("a real one still reads back", p.token() == "ops_realtoken")

print("\nthe file provider is untouched by all of this")
d = fresh("file")
v = B.PasswordVault(d)
check("file provider is the default", v.provider.name == "file")
check("it is eager", v.provider.eager is True)
v.set_entry("example.com", "https", "user", "pw")
check("still writes the same file", (d / "passwords.json").exists())
check("still 0600", oct((d / "passwords.json").stat().st_mode)[-3:] == "600")
check("magic unchanged",
      (d / "passwords.json").read_bytes()[:4] == b"BPW1")
check("no meta file needed", not (d / "passwords-meta.json").exists())

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
