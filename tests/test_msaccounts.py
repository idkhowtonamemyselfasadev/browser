"""The Microsoft-login defects, driven with real Qt input against a
real HTTP server.

Three of them, all reported as "I picked the other account and the
password never came":

  * the Site box in the manager stored whatever was typed into it, so
    a login pasted in as https://login.live.com/ could never equal the
    host of any page (u, u2);
  * once anything had been typed, the watcher stopped noticing which
    account the document was actually carrying — and login.live.com
    swaps its password step in without reloading, so there was no
    later moment at which it could have caught up (v, v2, v3);
  * a password box standing under an account we have nothing saved for
    was filled from the freshest login on the host instead (w);
  * and nothing anywhere said a row was dead (x).

Nothing here touches your data (see harness.boot).
"""
import json
import pathlib
import sys
import tempfile

import harness as H
import pages as PG
import pages4 as PG4
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

B = H.boot()
app = H.app()

srv = H.Server({})
PAGES = PG.pages("http://localhost:%d/hop/step2" % srv.port)
PAGES.update(PG4.PAGES)
H.Handler.pages = PAGES

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

RESULTS = []
PUSHES = []                 # every credential the browser pushes at a page
_orig_push = br._pw_push


def _record(page, user, password):
    PUSHES.append((page.url().path(), user, password))
    _orig_push(page, user, password)


br._pw_push = _record


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name + (
        ("  <%s>" % extra) if extra else ""))


def val(sel):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel))


def wipe():
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    del PUSHES[:]


def only(*entries):
    """Reset the vault to exactly these logins (last one is freshest)."""
    wipe()
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


def pushed(secret):
    return any(p == secret for _, _, p in PUSHES)


def type_into(sel, text):
    H.click(view, sel)
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier)
    H.spin(150)
    H.type_text(view, text)
    H.spin(600)


# =====================================================================
print("\n(u) the Site box swallowed a URL and the row went dead")
wipe()
row = br.vault.add_item({"type": "login", "host": "https://login.live.com/",
                         "username": "user@outlook.com", "password": "s3cret"})
check("the pasted URL is stored as a bare host",
      row["host"] == "login.live.com", row["host"])
check("and the row matches the page it was meant for",
      (br.vault.best_for("login.live.com", "https") or {}).get("username")
      == "user@outlook.com",
      str(br.vault.best_for("login.live.com", "https")))
check("a subdomain of it matches too, as it always did",
      br.vault.best_for("login.live.com", "https") is not None)

row2 = br.vault.add_item({"type": "login", "host": "http://intranet:8080/x",
                          "username": "user", "password": "p"})
check("a pasted URL brings its scheme with it",
      (row2["host"], row2["scheme"]) == ("intranet", "http"), str(row2))
row3 = br.vault.add_item({"type": "login", "host": "www.Example.COM",
                          "username": "user", "password": "p"})
check("a bare host is folded the way it always was",
      (row3["host"], row3["scheme"]) == ("example.com", "https"), str(row3))
check("and a bare host does not touch the scheme",
      br.vault.add_item({"type": "login", "host": "example.org",
                         "username": "t", "password": "p",
                         "scheme": "http"})["scheme"] == "http")

print("\n(u2) ... and the rows already saved that way are repaired")
raw = {"version": 1, "items": [
    {"type": "login", "host": "https://login.live.com/", "username": "a",
     "password": "p"},
    {"type": "login", "host": "login.live.com", "username": "b",
     "password": "p"},
    {"type": "login", "host": "the blue folder on my desk", "username": "c",
     "password": "p"},
    {"type": "note", "title": "n", "body": "b"}]}
one = B.PasswordVault.migrate(raw)
two = B.PasswordVault.migrate(json.loads(json.dumps(one)))
check("the URL row is a host now", one["items"][0]["host"] == "login.live.com",
      one["items"][0]["host"])
check("a row that was already right is left alone",
      one["items"][1]["host"] == "login.live.com", one["items"][1]["host"])
check("a Site with no host in it at all is carried through, not emptied",
      one["items"][2]["host"] == "the blue folder on my desk",
      one["items"][2]["host"])
check("the note is still a note, untouched",
      one["items"][3]["type"] == "note" and one["items"][3]["body"] == "b",
      str(one["items"][3]))
check("running the repair twice changes nothing",
      two["items"] == one["items"])

print("\n(u3) ... and such a row fills on the real page")
wipe()
br.vault.add_item({"type": "login", "host": "http://127.0.0.1:%d/" % srv.port,
                   "username": "user@example.com", "password": "hunter2"})
H.load(view, url("/both"))
check("the e-mail is filled from the row that was pasted as a URL",
      val("#user") == "user@example.com", val("#user"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("and the password goes out with it",
      "password=hunter2" in view.url().query(), view.url().toString())

# =====================================================================
print("\n(v) he types one account, then picks the other off a tile")
only(("127.0.0.1", "work@example.com", "workpass"),
     ("127.0.0.1", "alt@example.com", "altpass"))     # alt is the freshest
H.load(view, url("/ms/tiles"))
H.js(view, "window.__mark = 42")
type_into("#loginfmt", "alt@example.com")
check("the browser has the account he typed",
      any(v["username"] == "alt@example.com" and v["typed"]
          for v in br._pw_steps.values()), str(br._pw_steps))
H.click(view, "#tileB")            # no typing: the tile fills the box
H.spin(700)
check("the box now holds the other account",
      val("#loginfmt") == "work@example.com", val("#loginfmt"))
check("and the browser followed the switch",
      any(v["username"] == "work@example.com" for v in br._pw_steps.values()),
      str(br._pw_steps))
H.click(view, "#next")             # swaps the password step in, no navigation
H.spin(900)
check("the document was never reloaded", H.js(view, "window.__mark") == 42)
check("there is no username box left to read it from",
      not H.js(view, "!!document.querySelector('#loginfmt')"))
check("the password box arrived", H.js(view, "!!document.querySelector('#pw')"))
check("still empty before a gesture", val("#pw") == "", val("#pw"))
H.click(view, "#pw")
check("a real click fills the password of the account he picked",
      val("#pw") == "workpass", val("#pw"))
check("the account he typed first never had its password handed over",
      not pushed("altpass"), str(PUSHES))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("and that is what goes on the wire",
      "password=workpass" in view.url().query(), view.url().toString())

print("\n(v2) the same switch, with the address left in a box")
only(("127.0.0.1", "work@example.com", "workpass"),
     ("127.0.0.1", "alt@example.com", "altpass"))
H.load(view, url("/ms/tiles-kept"))
type_into("#loginfmt", "alt@example.com")
H.click(view, "#tileB")
H.spin(700)
H.click(view, "#next")
H.spin(900)
H.click(view, "#pw")
check("the password matches the name standing beside it",
      val("#pw") == "workpass", val("#pw"))
check("the first account's password never left the browser",
      not pushed("altpass"), str(PUSHES))

print("\n(v3) the reverse: he types one, the tile puts the first back")
only(("127.0.0.1", "work@example.com", "workpass"),
     ("127.0.0.1", "alt@example.com", "altpass"))
H.load(view, url("/ms/tiles"))
type_into("#loginfmt", "work@example.com")
H.click(view, "#tileA")            # back to alt, without typing it
H.spin(700)
H.click(view, "#next")
H.spin(900)
H.click(view, "#pw")
check("the password follows the account back",
      val("#pw") == "altpass", val("#pw"))
check("the typed account's password was not handed out beside the other name",
      not pushed("workpass"), str(PUSHES))

print("\n(v4) an account he typed stays typed, even when the page"
      " puts it back for him")
only(("127.0.0.1", "alt@example.com", "altpass"))
H.load(view, url("/ms/tiles"))
type_into("#loginfmt", "work@example.com")   # nothing saved for this one
H.click(view, "#tileA")                      # the page offers alt instead
H.spin(700)
H.js(view, "document.querySelector('#loginfmt').value = 'work@example.com'")
H.click(view, "#tileB")                      # ... and puts his own back
H.spin(700)
H.click(view, "#next")
H.spin(900)
H.click(view, "#pw")
check("nothing is filled under an account he typed and we do not know",
      val("#pw") == "", val("#pw"))
check("and the only saved password stayed in the browser",
      not pushed("altpass"), str(PUSHES))

# =====================================================================
print("\n(w) a password box under a name we have nothing saved for")
only(("127.0.0.1", "alt@example.com", "altpass"))
H.load(view, url("/ms/prefilled-stranger"))
check("the site's own account is left standing",
      val("#user") == "work@example.com", val("#user"))
H.click(view, "#pw")
H.spin(300)
check("no other account's password is filled beside it",
      val("#pw") == "", val("#pw"))
check("nor was one pushed at the page", not pushed("altpass"), str(PUSHES))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("nothing goes out on the wire either",
      "altpass" not in view.url().query(), view.url().toString())

print("\n(w2) ... and the same page, when it is an account we do know")
only(("127.0.0.1", "work@example.com", "workpass"),
     ("127.0.0.1", "alt@example.com", "altpass"))
H.load(view, url("/ms/prefilled-known"))
check("the site's own account is left standing",
      val("#user") == "alt@example.com", val("#user"))
H.click(view, "#pw")
check("its own password fills", val("#pw") == "altpass", val("#pw"))
check("and the freshest login's was not the one used",
      val("#pw") != "workpass", val("#pw"))

# =====================================================================
# The three sequences an independent reviewer used to break the first
# draft of this fix. All of them cross a document boundary after an
# account has been written into the box without being typed, which is
# where that draft let go of the one thing it had to hold.
print("\n(y) a tile writes a third account, then a real navigation")
only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
H.load(view, url("/ms/nav-step1"))
type_into("#loginfmt", "stranger@example.com")     # nothing saved for this
check("the browser has the account he typed, flagged typed",
      any(v["username"] == "stranger@example.com" and v["typed"]
          for v in br._pw_steps.values()), str(br._pw_steps))
H.click(view, "#tile")                             # written, not typed
H.spin(800)
check("the note followed the account the page wrote",
      any(v["username"] == "decoy@example.com" for v in br._pw_steps.values()),
      str(br._pw_steps))
check("and the half-login is still hand-chosen, for the other account too",
      all(v["typed"] for v in br._pw_steps.values()), str(br._pw_steps))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
H.spin(800)
check("a real navigation happened: this is a new document",
      view.url().path() == "/ms/nav-step2", view.url().toString())
check("the page claims an account we never saved",
      H.js(view, "document.querySelector('#who').textContent")
      == "stranger@example.com")
H.click(view, "#pw")
H.spin(400)
check("no saved password is filled under a name we do not know",
      val("#pw") == "", "filled=%r" % val("#pw"))
check("and none was ever pushed at the page", not pushed("VICTIMPASS"),
      str(PUSHES))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("nothing goes out on the wire either",
      "VICTIMPASS" not in view.url().query(), view.url().toString())

print("\n(y1b) the same, with the page navigating itself")
only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
H.load(view, url("/ms/nav-step1"))
type_into("#loginfmt", "stranger@example.com")
H.click(view, "#tile")
H.spin(800)
H.js(view, "location.href='/ms/nav-step2'")
H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
H.spin(800)
H.click(view, "#pw")
H.spin(400)
check("a scripted navigation after a tile fills nothing",
      val("#pw") == "", "filled=%r" % val("#pw"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("and nothing on the wire", "VICTIMPASS" not in view.url().query(),
      view.url().toString())

print("\n(y1c) control: the same, with no tile at all")
only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
H.load(view, url("/ms/nav-step1"))
type_into("#loginfmt", "stranger@example.com")
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
H.spin(800)
H.click(view, "#pw")
H.spin(400)
check("a typed account we do not know fills nothing, as it always did",
      val("#pw") == "", "filled=%r" % val("#pw"))

print("\n(y2) two accounts typed in one document, then the first comes back")
only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
H.load(view, url("/ms/nav-step1"))
H.js(view, "window.__T='a@b.co'")
type_into("#loginfmt", "a@b.co")                       # 6 characters
type_into("#loginfmt", "quite-a-long-address@example.com")   # and 32 more
H.click(view, "#tile")                                 # the first one back
H.spin(900)
check("the note is back on the first account",
      any(v["username"] == "a@b.co" for v in br._pw_steps.values()),
      str(br._pw_steps))
check("and it is still known to be hand-chosen",
      all(v["typed"] for v in br._pw_steps.values()), str(br._pw_steps))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
H.spin(800)
H.click(view, "#pw")
H.spin(400)
check("no stranger's password under an account he typed himself",
      val("#pw") == "", "filled=%r" % val("#pw"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("and nothing on the wire", "VICTIMPASS" not in view.url().query(),
      view.url().toString())

print("\n(y3) a write the page makes with no event of any kind")
# Nothing is asserted here about the browser *noticing* this: a bare
# `el.value = x` from page script fires no event, mutates no attribute
# and moves no node, so there is nothing to notice short of polling
# the DOM, which no browser does. What has to hold is the outcome —
# an account the note is stale about is still an account whose own
# password is the only one that can be filled, so a stale note costs
# a fill, never a disclosure.
only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
H.load(view, url("/ms/nav-step1"))
type_into("#loginfmt", "a@x.co")
type_into("#loginfmt", "another-long-name@example.com")
H.js(view, "document.querySelector('#loginfmt').value='a@x.co'")
H.spin(800)
H.js(view, "location.href='/ms/nav-step2'")
H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
H.spin(800)
H.click(view, "#pw")
H.spin(400)
check("nothing is filled for either account he typed",
      val("#pw") == "", "filled=%r" % val("#pw"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("and nothing on the wire", "VICTIMPASS" not in view.url().query(),
      view.url().toString())

# =====================================================================
print("\n(z) the password we filled is taken back when the account"
      " changes under it")
only(("127.0.0.1", "A@example.com", "APASS"))
H.load(view, url("/ms/swap"))
type_into("#user", "A@example.com")
H.click(view, "#pw")
H.spin(400)
check("A's password is in the box", val("#pw") == "APASS", val("#pw"))
H.click(view, "#toB")            # the page writes an account we do not know
H.spin(900)
check("it does not stay there under the other account's name",
      val("#pw") == "", "user=%r pw=%r" % (val("#user"), val("#pw")))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("and it does not go out under that name",
      "APASS" not in view.url().query(), view.url().toString())

print("\n(z2) ... and the same when he retypes the account himself")
only(("127.0.0.1", "A@example.com", "APASS"))
H.load(view, url("/ms/swap"))
type_into("#user", "A@example.com")
H.click(view, "#pw")
H.spin(400)
check("A's password is in the box", val("#pw") == "APASS", val("#pw"))
type_into("#user", "B@example.com")
H.spin(900)
check("it does not stay there under the name he retyped",
      val("#pw") == "", "user=%r pw=%r" % (val("#user"), val("#pw")))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
check("nor go out under it", "APASS" not in view.url().query(),
      view.url().toString())

print("\n(z3) ... and when both accounts are saved, the password follows"
      " the name back and forth")
only(("127.0.0.1", "A@example.com", "APASS"),
     ("127.0.0.1", "B@example.com", "BPASS"))
H.load(view, url("/ms/swap"))
type_into("#user", "A@example.com")
H.click(view, "#pw")
H.spin(400)
check("A gets A's password", val("#pw") == "APASS", val("#pw"))
H.click(view, "#toB")
H.spin(900)
check("switching to B swaps the password too", val("#pw") == "BPASS",
      "user=%r pw=%r" % (val("#user"), val("#pw")))
H.click(view, "#toA")
H.spin(900)
check("and back to A", val("#pw") == "APASS",
      "user=%r pw=%r" % (val("#user"), val("#pw")))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done", 8000)
H.spin(300)
q = view.url().query()
check("the wire carries one account's name with its own password",
      "username=A%40example.com" in q and "password=APASS" in q, q)

print("\n(z4) an account written into the Site box is not a host")
check("typed into the Site box, safe.com@evil.com yields no host",
      B.PasswordVault.parse_site("safe.com@evil.com", hand_typed=True)[0]
      == "",
      str(B.PasswordVault.parse_site("safe.com@evil.com", hand_typed=True)))
check("so the row keeps its text and does not come to life on evil.com",
      B.PasswordVault.normalize_host("safe.com@evil.com")
      == "safe.com@evil.com",
      B.PasswordVault.normalize_host("safe.com@evil.com"))
check("and it is called dead, so he is told rather than surprised",
      B.PasswordVault.unmatchable({"type": "login",
                                   "host": "safe.com@evil.com"}))
check("read plainly as a URL it is evil.com, which is what a file and a"
      " store get — see (z6)",
      B.PasswordVault.parse_site("safe.com@evil.com")[0] == "evil.com",
      str(B.PasswordVault.parse_site("safe.com@evil.com")))

print("\n(z6) ... but only the Site box refuses it: a file and a store"
      " keep every row they had")
# The guard above is for a line a person typed. Everything arriving
# from an export or from 1Password is read the way a URL is read, the
# way it always was — Chrome writes every Android login as
# android://<hash>@<package>/ and a router login really can carry its
# credentials in the URL, and refusing those loses rows he has.
rows = [["name", "url", "username", "password", "note"]]
for i in range(200):                       # ordinary web logins
    rows.append(["site%d" % i, "https://site%d.example/login" % i,
                 "user%d@x.com" % i, "pass%d!" % i, ""])
for i in range(40):                        # Chrome's Android app shape
    rows.append(["app%d" % i,
                 "android://5Yl2Xz9k_hash%d==@com.example.app%d/" % (i, i),
                 "user%d@x.com" % i, "apppass%d!" % i, ""])
for i in range(5):                         # credentials in the URL
    rows.append(["cred%d" % i, "https://admin:hunter2@router%d.example/" % i,
                 "admin", "routerpass%d" % i, ""])
csv_text = "\n".join(",".join('"%s"' % c for c in r) for r in rows)
scratch = B.PasswordVault(pathlib.Path(tempfile.mkdtemp(prefix="csv-in-")))
scratch.data = B.PasswordVault._empty()
added, updated, skipped = scratch.import_csv(csv_text)
imported = [i for i in scratch.items() if i.get("type") == "login"]
check("every row in the file is a row in the vault",
      (added, updated, skipped) == (len(rows) - 1, 0, 0),
      "in=%d added=%d updated=%d skipped=%d"
      % (len(rows) - 1, added, updated, skipped))
check("the Android app logins came through",
      sum(1 for i in imported
          if i.get("host", "").startswith("com.example.app")) == 40)
check("so did the ones with credentials in the URL",
      sum(1 for i in imported
          if i.get("host", "").startswith("router")) == 5)
check("and the host is the one after the @, which is what a URL means",
      any(i.get("host") == "router0.example" for i in imported),
      str([i.get("host") for i in imported[-5:]]))
# An Android row is kept as its package name and is NOT called dead. It
# will never match a page, but com.example.app0 is a perfectly good
# host name and the manager saying otherwise would be it asserting
# something it cannot know. Keeping the row is the part that matters:
# it is the record that a password exists.
check("an Android row is kept rather than judged",
      not B.PasswordVault.unmatchable(
          next(i for i in imported
               if i.get("host") == "com.example.app0")))

op = B.OnePasswordProvider.__new__(B.OnePasswordProvider)


def op_host(href):
    return B.OnePasswordProvider._from_op_item(
        op, {"id": "i", "title": "t", "category": "LOGIN",
             "urls": [{"primary": True, "href": href}],
             "additional_information": "user@x.com"}).get("host")


check("a 1Password login whose URL carries a user still has its host",
      op_host("https://user@example.com/") == "example.com",
      repr(op_host("https://user@example.com/")))
check("and one with a password in the URL too",
      op_host("https://admin:pw@router.example/") == "router.example",
      repr(op_host("https://admin:pw@router.example/")))
check("an ordinary one is untouched",
      op_host("https://example.com/login") == "example.com")
check("and a listing that names no site at all is still the empty one",
      op_host("") == "")

# =====================================================================
print("\n(z5) two rules hold that line, and either one alone is enough")
# The sequence from (y), run three times: with each rule switched off
# in turn, and then with both. Belt and braces are only worth having if
# each is load-bearing on its own, and the last run is what says the
# other two were measuring something.
#
# out of __dict__, not off the class: reading a staticmethod through
# the class hands back the bare function, and putting that back turns
# it into an ordinary method that gets `self` as its first argument
# ever after.
KEEP_STICKS = vars(B.Browser)["_typed_sticks"]
KEEP_ENTRY = vars(B.Browser)["_pw_step_entry"]
# "the half-login stops being hand-chosen as soon as the page reports
# the account as a guess again"
LOOSE_STICKS = staticmethod(lambda old, typed: bool(typed))
# "a half-login we have nothing saved for may fall back to a guess"
LOOSE_ENTRY = (lambda self, host, scheme, step:
               self.vault.for_username(host, scheme, step["username"])
               or (None if step["typed"]
                   else self.vault.best_for(host, scheme)))


def leaks_through():
    """Run (y) once. Reports the half-login as it stood when step one
    was left — submitting forgets it — and then what reached the page
    and what reached the wire."""
    only(("127.0.0.1", "victim.user@example.com", "VICTIMPASS"))
    H.load(view, url("/ms/nav-step1"))
    type_into("#loginfmt", "stranger@example.com")
    H.click(view, "#tile")
    H.spin(800)
    noted = [dict(v) for v in br._pw_steps.values()]
    H.click(view, "#next")
    H.wait_for(lambda: view.url().path() == "/ms/nav-step2", 8000)
    H.spin(800)
    H.click(view, "#pw")
    H.spin(400)
    filled = val("#pw")
    H.click(view, "#signin")
    H.wait_for(lambda: view.url().path() == "/done", 8000)
    H.spin(300)
    return noted, filled, view.url().query()


try:
    B.Browser._typed_sticks = LOOSE_STICKS
    noted, filled, wire = leaks_through()
    check("with the sticky-typed rule off, the other one still holds",
          filled == "" and "VICTIMPASS" not in wire,
          "filled=%r wire=%s" % (filled, wire))
finally:
    B.Browser._typed_sticks = KEEP_STICKS
try:
    B.Browser._pw_step_entry = LOOSE_ENTRY
    noted, filled, wire = leaks_through()
    check("with the no-guessing rule off, the other one still holds",
          filled == "" and "VICTIMPASS" not in wire,
          "filled=%r wire=%s" % (filled, wire))
finally:
    B.Browser._pw_step_entry = KEEP_ENTRY
try:
    B.Browser._typed_sticks = LOOSE_STICKS
    B.Browser._pw_step_entry = LOOSE_ENTRY
    noted, filled, wire = leaks_through()
    # Still nothing, with both of them off — because in this sequence
    # there is a third rule in front of them: the watcher never lowers
    # `typed` inside a document, so the report that arrives already
    # says hand-chosen and neither of the two is asked anything.
    #
    # That is worth being exact about. These two are alone only once
    # the document is gone and the watcher's memory with it — going
    # Back, or Forward, or reloading. test_round3 (q3) is that
    # sequence, and there switching both off does put the old leak
    # back, which is what proves they carry weight.
    check("with both off the watcher itself still reports hand-chosen",
          bool(noted) and all(v["typed"] for v in noted), str(noted))
    check("so this sequence leaks nothing even then",
          filled == "" and "VICTIMPASS" not in wire,
          "filled=%r wire=%s" % (filled, wire))
finally:
    B.Browser._typed_sticks = KEEP_STICKS
    B.Browser._pw_step_entry = KEEP_ENTRY

# =====================================================================
print("\n(x) a row that can never match says so in the manager")
wipe()
dead = br.vault.add_item({"type": "login", "host": "the blue folder",
                          "username": "user", "password": "p"})
alive = br.vault.add_item({"type": "login", "host": "example.com",
                           "username": "user", "password": "p"})
shown = {i["id"]: i for i in br.vault.redacted_items()}
check("the dead row is flagged for the page",
      shown[dead["id"]].get("dead") is True, str(shown[dead["id"]]))
check("the live row is not", "dead" not in shown[alive["id"]],
      str(shown[alive["id"]]))
check("and no password came along for the ride",
      all("password" not in i for i in shown.values()))
note_id = br.vault.add_item({"type": "note", "title": "n"})["id"]
shown = {i["id"]: i for i in br.vault.redacted_items()}
check("a note is never called dead, whatever its title",
      "dead" not in shown[note_id], str(shown[note_id]))

br.open_passwords()
H.spin(1500)
# the manager is a pane now, not a tab: br.current() is the page underneath
mgr = br._panes["passwords"].view
H.wait_for(lambda: H.js(mgr, "!!document.querySelector('.row')") is True,
           8000)
H.js(mgr, "[...document.querySelectorAll('.row')]"
          ".find(r => r.textContent.includes('the blue folder')).click()")
H.spin(700)
note = H.js(mgr, "(function(){var e=document.querySelector('#deadsite');"
                 "return e?e.textContent:null;})()")
check("the manager says so on the row itself", bool(note), repr(note))
H.js(mgr, "[...document.querySelectorAll('.row')]"
          ".find(r => r.textContent.includes('example.com')).click()")
H.spin(700)
check("and says nothing on a row that is fine",
      H.js(mgr, "!document.querySelector('#deadsite')"))
br.close_tab(br.tabs.indexOf(mgr))
H.spin(500)

srv.stop()
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
sys.exit(1 if bad else 0)
