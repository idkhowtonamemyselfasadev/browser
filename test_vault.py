#!/usr/bin/env python3
"""Vault tests: migration, generator, TOTP against RFC 6238's own
published vectors, health, search and import/export.

Never touched by these tests: the real vault. Everything runs against a
scratch directory under /tmp.
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="vaulttest-"))
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def fresh(name="v"):
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    for f in ("passwords.json", "passwords.key"):
        (d / f).unlink(missing_ok=True)
    return d


# ---------------------------------------------------------------- 1
print("\nmigration from the v1 (host/username/password) file")
d = fresh("mig")
old = B.FileVaultProvider(d)
old.save({"entries": [
    {"host": "example.com", "username": "user", "password": "hunter2",
     "scheme": "https", "used": 1700000000},
    {"host": "shop.de", "username": "", "password": "p2", "scheme": "http",
     "used": 1700000001}],
    "never": ["www.Bank.com"]})
v = B.PasswordVault(d)
check("both logins survived", len(v.logins()) == 2, len(v.logins()))
e = v.get("example.com", "user")
check("password intact", e and e["password"] == "hunter2")
check("scheme intact", e and e["scheme"] == "https")
check("used carried into created/changed",
      e["created"] == 1700000000 and e["changed"] == 1700000000)
check("every item has an id and a type",
      all(i.get("id") and i["type"] == "login" for i in v.items()))
check("never list normalised", v.data["never"] == ["bank.com"],
      v.data["never"])
check("is_never still works", v.is_never("www.bank.com"))

print("\nmigration is idempotent")
once = B.PasswordVault.migrate(old.load())
twice = B.PasswordVault.migrate(json.loads(json.dumps(once)))
ids_once = sorted(i["id"] for i in once["items"])
ids_twice = sorted(i["id"] for i in twice["items"])
check("same items, same ids", ids_once == ids_twice)
v._save()
v2 = B.PasswordVault(d)
check("reload after save keeps 2 logins", len(v2.logins()) == 2)
check("no duplicates from the entries mirror",
      len(B.PasswordVault(d).logins()) == 2)

print("\nsafe against a file written by a newer version")
d = fresh("future")
B.FileVaultProvider(d).save({
    "version": 99, "quantumField": {"a": 1},
    "items": [{"id": "x1", "type": "hologram", "title": "?",
               "unknownField": "keep me", "secretSauce": [1, 2]}],
    "never": []})
v = B.PasswordVault(d)
check("version not downgraded", v.data["version"] == 99, v.data["version"])
check("unknown top-level key kept", v.data.get("quantumField") == {"a": 1})
item = v.item("x1")
check("unknown type kept", item.get("type") == "hologram", item.get("type"))
check("unknown per-item field kept", item.get("unknownField") == "keep me")
holo = v.add_item({"type": "hologram", "title": "future",
                   "password": "NEWER-VAULT-SECRET", "colour": "blue"})
shown = [i for i in v.redacted_items() if i["id"] == holo["id"]][0]
check("a newer type's secret-looking field is held back all the same",
      "password" not in shown and shown.get("hasPassword") is True, shown)
check("and the rest of it still reaches the page",
      shown.get("colour") == "blue", shown)
check("nothing about it was rewritten on the way through",
      v.item(holo["id"])["password"] == "NEWER-VAULT-SECRET")
check("unknown list field kept", item.get("secretSauce") == [1, 2])
v._save()
v = B.PasswordVault(d)
check("still there after a save round trip",
      v.data.get("quantumField") == {"a": 1}
      and v.item("x1").get("unknownField") == "keep me"
      and v.data["version"] == 99)

# ---------------------------------------------------------------- 2
print("\npassword generator")
p = B.generate_password(24)
check("length honoured", len(p) == 24)
check("no ambiguous characters by default",
      not any(c in p for c in "l1IO0o"))
check("uses secrets, not random",
      "secrets" in B.generate_password.__globals__
      and "choice" in B.generate_password.__code__.co_names)
longs = {B.generate_password(20) for _ in range(200)}
check("200 draws are all different", len(longs) == 200)
p = B.generate_password(30, symbols=True, digits=True, upper=True,
                        ambiguous=True)
check("every class present when asked",
      any(c.islower() for c in p) and any(c.isupper() for c in p)
      and any(c.isdigit() for c in p)
      and any(c in B.GEN_SYMBOLS for c in p))
p = B.generate_password(16, symbols=False, digits=False, upper=False)
check("classes can be switched off", p.isalpha() and p.islower())
check("length is clamped, never crashes",
      len(B.generate_password(1)) == 4 and len(B.generate_password(9999)) == 128)

# ---------------------------------------------------------------- 3
print("\nTOTP — RFC 6238 Appendix B published test vectors")
# The RFC's shared secrets are ASCII "12345678901234567890" repeated to
# the hash's block size; the vault takes base32, so encode them.
sha1 = base64.b32encode(b"12345678901234567890").decode()
sha256 = base64.b32encode(b"12345678901234567890" * 2)[:52].decode()
sha512 = base64.b32encode((b"12345678901234567890" * 4)[:64]).decode()
vectors = [
    (59, "94287082", sha1, "sha1"),
    (1111111109, "07081804", sha1, "sha1"),
    (1111111111, "14050471", sha1, "sha1"),
    (1234567890, "89005924", sha1, "sha1"),
    (2000000000, "69279037", sha1, "sha1"),
    (20000000000, "65353130", sha1, "sha1"),
    (59, "46119246", sha256, "sha256"),
    (1111111109, "68084774", sha256, "sha256"),
    (1234567890, "91819424", sha256, "sha256"),
    (20000000000, "77737706", sha256, "sha256"),
    (59, "90693936", sha512, "sha512"),
    (1111111109, "25091201", sha512, "sha512"),
    (1234567890, "93441116", sha512, "sha512"),
    (20000000000, "47863826", sha512, "sha512"),
]
for at, want, secret, alg in vectors:
    got = B.totp_code(secret, at=at, digits=8, algorithm=alg)
    check("RFC 6238 %s t=%d -> %s" % (alg, at, want), got == want, got)
check("6 digits is the last 6 of the 8",
      B.totp_code(sha1, at=59) == "287082", B.totp_code(sha1, at=59))
check("countdown inside the period",
      B.totp_remaining(30, at=1000) == 20.0, B.totp_remaining(30, at=1000))

print("\notpauth:// parsing")
u = B.parse_otpauth(
    "otpauth://totp/GitHub:user?secret=" + sha1
    + "&issuer=GitHub&digits=8&period=60&algorithm=SHA256")
check("secret read", u and u["secret"] == sha1)
check("issuer read", u and u["issuer"] == "GitHub")
check("label read", u and u["label"] == "GitHub:user")
check("digits read", u and u["digits"] == 8)
check("period read", u and u["period"] == 60)
check("algorithm read", u and u["algorithm"] == "sha256")
check("bare base32 accepted", B.parse_otpauth(sha1)["secret"] == sha1)
check("spaces and lower case accepted",
      B.parse_otpauth(sha1.lower()[:8] + " " + sha1.lower()[8:]) is not None)
check("garbage refused", B.parse_otpauth("not base32 at all!!") is None)
check("empty refused", B.parse_otpauth("") is None)
check("wrong scheme refused",
      B.parse_otpauth("https://totp/x?secret=" + sha1) is None)
check("hotp refused", B.parse_otpauth("otpauth://hotp/x?secret=" + sha1)
      is None)

# ---------------------------------------------------------------- 4
print("\npassword health (offline only)")
d = fresh("health")
v = B.PasswordVault(d)
now = int(time.time())
v.add_item({"type": "login", "host": "a.com", "username": "t",
            "password": "Reused#Pass99"})
v.add_item({"type": "login", "host": "b.com", "username": "t",
            "password": "Reused#Pass99"})
v.add_item({"type": "login", "host": "c.com", "username": "t",
            "password": "abc"})
strong = v.add_item({"type": "login", "host": "d.com", "username": "t",
                     "password": B.generate_password(24)})
oldie = v.add_item({"type": "login", "host": "e.com", "username": "t",
                    "password": B.generate_password(24)})
oldie["changed"] = now - 400 * 86400
h = v.health()
ids = {i["host"]: i["id"] for i in v.logins()}
check("reuse found on both sides", h["totals"]["reused"] == 2)
check("short password is weak", "weak" in h["flags"].get(ids["c.com"], []))
check("generated password is not weak",
      "weak" not in h["flags"].get(ids["d.com"], []))
check("stale password flagged old",
      "old" in h["flags"].get(ids["e.com"], []))
check("fresh strong password has no flags at all",
      strong["id"] not in h["flags"])
check("totals line up", h["totals"]["weak"] == 1 and h["totals"]["old"] == 1,
      h["totals"])
check("health never touches the network",
      "urllib" not in B.PasswordVault.health.__code__.co_names)

# ---------------------------------------------------------------- 5
print("\nitem types")
d = fresh("types")
v = B.PasswordVault(d)
n = v.add_item({"type": "note", "title": "wifi", "body": "the key is 1234"})
c = v.add_item({"type": "card", "title": "giro", "number": "4111111111111111",
                "cardholder": "A. User", "expiry": "12/28", "cvv": "123"})
i = v.add_item({"type": "identity", "title": "home", "fullname": "A. User",
                "email": "t@example.com", "city": "Berlin"})
v = B.PasswordVault(d)
check("note round-trips", v.item(n["id"])["body"] == "the key is 1234")
check("card round-trips", v.item(c["id"])["number"] == "4111111111111111")
check("identity round-trips", v.item(i["id"])["email"] == "t@example.com")
check("types kept apart", len(v.logins()) == 0 and len(v.items()) == 3)
check("an unknown type from a newer vault is kept, not coerced",
      B.PasswordVault._normalize({"type": "spaceship"})["type"]
      == "spaceship")
check("a missing type still becomes a login",
      B.PasswordVault._normalize({})["type"] == "login")

# ---------------------------------------------------------------- 6
print("\nimport / export")
d = fresh("io")
v = B.PasswordVault(d)
csv_text = ('name,url,username,password\n'
            'Example,https://example.com/login,user,pw1\n'
            'Shop,http://shop.de/,,pw2\n'
            'Broken,,nobody,pw3\n'
            'NoPass,https://x.com/,user,\n')
check("import counts", v.import_csv(csv_text) == (2, 0, 2), v.import_csv)
d = fresh("io2")
v = B.PasswordVault(d)
added, updated, skipped = v.import_csv(csv_text)
check("2 added first time", (added, updated, skipped) == (2, 0, 2))
check("host normalised", v.get("example.com", "user") is not None)
check("http scheme kept", v.get("shop.de", "")["scheme"] == "http")
again = v.import_csv(csv_text)
check("second import adds nothing", again == (0, 0, 4), again)
check("still only 2 logins", len(v.logins()) == 2)
changed = csv_text.replace("user,pw1", "user,pw1-new")
check("changed password updates", v.import_csv(changed) == (0, 1, 3))
check("update landed", v.get("example.com", "user")["password"] == "pw1-new")
rows = v.export_rows()
check("export header", rows[0] == B.PasswordVault.EXPORT_HEADER)
check("export has both logins", len(rows) == 3, rows)
check("export carries the password in the clear (that is the point)",
      any("pw1-new" in r for r in rows))

print("\nan export cannot be turned into a spreadsheet formula")
d = fresh("inject")
v = B.PasswordVault(d)
ATTACK = "=cmd|' /C calc'!A0"
v.add_item({"type": "login", "host": "evil.example", "username": "user",
            "password": ATTACK, "title": "=HYPERLINK(\"x\")"})
rows = v.export_rows()
check("no exported cell starts with a formula character",
      not any(str(c)[:1] in B.PasswordVault.FORMULA_LEAD
              for r in rows for c in r), rows)
back = B.PasswordVault(fresh("inject2"))
import io as _io
import csv as _csv
buf = _io.StringIO()
_csv.writer(buf).writerows(rows)
back.import_csv(buf.getvalue())
check("and the round trip gives back the password he actually had",
      back.get("evil.example", "user")["password"] == ATTACK,
      back.get("evil.example", "user"))

print("\nan import of a real-sized export does not take a minute")
d = fresh("bulk")
v = B.PasswordVault(d)
lines = ["name,url,username,password"]
for n in range(2000):
    lines.append("site%d,https://site%d.example/,user,pw%d" % (n, n, n))
started = time.time()
counts = v.import_csv("\n".join(lines))
took = time.time() - started
check("all 2000 rows landed", counts == (2000, 0, 0), counts)
check("in well under a second, not 55 of them", took < 5, "%.1fs" % took)
check("and they really are in the file",
      len(B.PasswordVault(d).logins()) == 2000)

print("\nan import that cannot be written leaves nothing behind")
d = fresh("noroom")
v = B.PasswordVault(d)
v.add_item({"type": "login", "host": "kept.example", "username": "user",
            "password": "already-here"})
before = len(v.items())
(d / "passwords.json").chmod(0o400)
d.chmod(0o500)                      # nothing new can be written here
try:
    counts = v.import_csv("name,url,username,password\n"
                          "New,https://new.example/,user,pw\n")
finally:
    d.chmod(0o700)
    (d / "passwords.json").chmod(0o600)
check("it says nothing was imported", counts == (0, 0, 1), counts)
check("and left no row behind in memory either",
      len(v.items()) == before, len(v.items()))
check("the vault on disk is untouched",
      len(B.PasswordVault(d).items()) == before)

print("\na padded two-factor secret is not thrown away")
check("padded base32 decodes",
      B.parse_otpauth("JBSWY3DPEHPK3PXP====") is not None)
check("and gives the same code as the unpadded form",
      B.totp_code("JBSWY3DPEHPK3PXP====", at=59)
      == B.totp_code("JBSWY3DPEHPK3PXP", at=59))
kept = B.PasswordVault._normalize({"type": "login",
                                   "totp": "JBSWY3DPEHPK3PXP===="})
check("and _normalize keeps the seed instead of wiping it",
      kept["totp"] == "JBSWY3DPEHPK3PXP====", kept["totp"])

# ---------------------------------------------------------------- 7
print("\ntags and favourites")
d = fresh("org")
v = B.PasswordVault(d)
a = v.add_item({"type": "login", "host": "github.com", "username": "user",
                "password": "s3cret!", "tags": ["work", "dev"],
                "title": "GitHub"})
v.add_item({"type": "note", "title": "Router", "body": "admin panel",
            "tags": ["home"]})
check("all_tags sorted", v.all_tags() == ["dev", "home", "work"], v.all_tags())
check("fav toggles on", v.toggle_fav(a["id"]) is True)
check("fav toggles back", v.toggle_fav(a["id"]) is False)
# searching and filtering are the page's job, over the listing it was
# already given; the vault-side search(), matches() and
# public_entries() had no caller left and are gone
check("no vault-side search left to keep in step with the page",
      not any(hasattr(B.PasswordVault, n)
              for n in ("search", "matches", "public_entries")))
check("and the page still cannot search by password",
      all("password" not in i for i in v.redacted_items()))

# ---------------------------------------------------------------- 8
print("\nbackend seam")
class MemoryBackend(B.VaultProvider):
    name = "memory"

    def __init__(self):
        self.blob = {}

    def load(self):
        return json.loads(json.dumps(self.blob))

    def save(self, data):
        self.blob = json.loads(json.dumps(data))
        return True

mem = MemoryBackend()
v = B.PasswordVault(provider=mem)
v.set_entry("example.com", "https", "user", "pw")
check("writes went to the injected backend", "items" in mem.blob)
check("reads come back from it",
      B.PasswordVault(provider=mem).get("example.com", "user")["password"] == "pw")
check("nothing was written to disk",
      not (TMP / "passwords.json").exists())
check("PasswordVault names no file path",
      "passwords.json" not in "".join(
          str(c) for c in B.PasswordVault.__dict__.values()
          if isinstance(c, str)))

# ---------------------------------------------------------------- 9
print("\nfile permissions and scrambling")
d = fresh("perm")
v = B.PasswordVault(d)
v.set_entry("secretsite.com", "https", "user", "TotallyUniqueString42")
raw = (d / "passwords.json").read_bytes()
check("password is not in the file in the clear",
      b"TotallyUniqueString42" not in raw)
check("vault file is 0600", oct((d / "passwords.json").stat().st_mode)[-3:]
      == "600")
check("key file is 0600", oct((d / "passwords.key").stat().st_mode)[-3:]
      == "600")

print("\nautofill semantics unchanged")
d = fresh("fill")
v = B.PasswordVault(d)
v.set_entry("example.com", "http", "old", "p1")
time.sleep(1.05)
v.set_entry("example.com", "https", "new", "p2")
check("most recent wins", v.best_for("example.com", "https")["username"]
      == "new")
check("subdomain matches parent",
      v.best_for("mail.example.com", "https") is not None)
check("http entry fills https", v.best_for("example.com", "https")
      is not None)
v2 = B.PasswordVault(fresh("fill2"))
v2.set_entry("only-https.com", "https", "t", "p")
check("https entry does not fill http",
      v2.best_for("only-https.com", "http") is None)
check("unrelated host does not match",
      v2.best_for("notonly-https.com", "https") is None)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
