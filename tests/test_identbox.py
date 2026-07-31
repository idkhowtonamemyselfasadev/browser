"""The e-mail box that would not let him type a second account.

His words: "if i wanne sign in to microsoft it just spam enter my email
and i cand even get a second acound in cause i cand enter my email".

The browser filled the saved address, and every time he emptied the box
to type the other one it came straight back. Two doors it came through:

  * the identifier step reported an empty box, the browser read that as
    "nobody is signing in yet" and pushed the saved account again; and
  * on a one-screen form the PASSWORD push carries a username with it,
    which landed in the box the same way.

The rule these all measure: the browser fills the account once, and the
moment he changes or clears it that is his choice for the rest of the
document.

Nothing here touches your data (see harness.boot).
"""
import json
import sys

import harness as H
import pages as PG
import pages4 as PG4
import pages5 as PG5
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

B = H.boot()
app = H.app()

srv = H.Server({})
PAGES = PG.pages("http://localhost:%d/hop/step2" % srv.port)
PAGES.update(PG4.PAGES)
PAGES.update(PG5.PAGES)
H.Handler.pages = PAGES

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

RESULTS = []
PUSHES = []
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
    wipe()
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


def clear_box(sel):
    """What he actually does: click the box, select all, delete."""
    H.click(view, sel)
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier)
    H.spin(120)
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_Backspace)
    H.spin(700)


def backspace_out(sel, n):
    """The other way he does it: hold backspace to the end."""
    H.click(view, sel)
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_End)
    for _ in range(n):
        QTest.keyClick(view.focusProxy(), Qt.Key.Key_Backspace)
        H.spin(25)
    H.spin(700)


FIRST = "first@example.com"
SECOND = "second@example.com"

# =====================================================================
print("\n(a) the first fill still happens, exactly once")
only(("127.0.0.1", FIRST, "firstpass"))
H.load(view, url("/ms2/rerender"))
H.js(view, "window.__mark = 7")
check("the saved address is filled on arrival",
      val("#loginfmt") == FIRST, val("#loginfmt"))

print("\n(b) he empties the box — and it stays empty")
clear_box("#loginfmt")
check("the box is empty right after he clears it",
      val("#loginfmt") == "", val("#loginfmt"))
H.spin(1200)                       # the 200ms report and the 400ms nudge
check("and it is still empty a second later",
      val("#loginfmt") == "", val("#loginfmt"))
check("the document was never reloaded", H.js(view, "window.__mark") == 7)

print("\n(c) clearing it again does not bring it back either")
for i in range(3):
    clear_box("#loginfmt")
    check("cleared %d: the saved address did not come back" % (i + 1),
          val("#loginfmt") == "", val("#loginfmt"))

print("\n(d) now the second account goes in, and stays in")
H.click(view, "#loginfmt")
H.type_text(view, SECOND)
H.spin(700)
check("the second account is in the box",
      val("#loginfmt") == SECOND, val("#loginfmt"))
check("the browser has the account he typed",
      any(v["username"] == SECOND and v["typed"]
          for v in br._pw_steps.values()), str(br._pw_steps))

print("\n(e) ... through a re-render that carries the value over")
H.click(view, "#rr")
H.spin(900)
check("the box still holds his account", val("#loginfmt") == SECOND,
      val("#loginfmt"))
check("the first account did not come back", val("#loginfmt") != FIRST,
      val("#loginfmt"))

print("\n(f) ... through a re-render that hands back an empty box")
H.click(view, "#rrempty")
H.spin(1200)
check("an empty box is left empty", val("#loginfmt") != FIRST,
      val("#loginfmt"))
H.spin(800)
check("and still is after the observer has settled",
      val("#loginfmt") != FIRST, val("#loginfmt"))

print("\n(g) ... through a rescan(), which is what _autofill nudges")
H.js(view, "window.__bpw && window.__bpw.rescan();", B.PW_WORLD_ID)
H.spin(900)
check("rescan does not re-enter the saved address",
      val("#loginfmt") != FIRST, val("#loginfmt"))

print("\n(h) ... and through a loadFinished on a document that already"
      " finished loading")
view.loadFinished.emit(True)       # the second finish, same document
H.spin(1200)
check("a second loadFinished does not re-enter it either",
      val("#loginfmt") != FIRST, val("#loginfmt"))
check("nor did the browser push the first account's password",
      not any(p == "firstpass" for _, _, p in PUSHES), str(PUSHES))

print("\n(i) he types it back in and walks on to the password step")
H.click(view, "#loginfmt")
H.type_text(view, SECOND)
H.spin(700)
check("his account is in the box again", val("#loginfmt") == SECOND,
      val("#loginfmt"))
H.click(view, "#next")
H.spin(900)
check("the password step arrived",
      H.js(view, "!!document.querySelector('#pw')"))
H.click(view, "#pw")
H.spin(400)
check("nothing is filled for an account we have never saved",
      val("#pw") == "", val("#pw"))
check("and the saved account's password never left the browser",
      not any(p == "firstpass" for _, _, p in PUSHES), str(PUSHES))

# =====================================================================
print("\n(j) a real navigation is a fresh page: the fill happens again")
only(("127.0.0.1", FIRST, "firstpass"))
H.load(view, url("/ms2/rerender"))
check("a new document fills the saved address as it always did",
      val("#loginfmt") == FIRST, val("#loginfmt"))
H.click(view, "#next")
H.spin(900)
H.click(view, "#pw")
H.spin(400)
check("and the two-step flow still hands the password over",
      val("#pw") == "firstpass", val("#pw"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("which is what goes on the wire",
      "password=firstpass" in view.url().query(), view.url().toString())

# =====================================================================
print("\n(k) the one-screen form: the password push carries a username")
only(("127.0.0.1", FIRST, "firstpass"))
H.load(view, url("/ms2/onescreen"))
check("the saved address is filled", val("#user") == FIRST, val("#user"))
clear_box("#user")
check("clearing it leaves it cleared here too",
      val("#user") == "", val("#user"))
H.spin(1000)
check("and it is still clear after the push at the password stage",
      val("#user") == "", val("#user"))
H.click(view, "#user")
H.type_text(view, SECOND)
H.spin(800)
check("his second account goes in", val("#user") == SECOND, val("#user"))
H.click(view, "#pw")
H.spin(400)
check("no saved password lands under an account he typed",
      val("#pw") == "", val("#pw"))
check("the box was not rewritten by the password push",
      val("#user") == SECOND, val("#user"))

print("\n(l) the second account, once saved, fills like any other")
only(("127.0.0.1", FIRST, "firstpass"),
     ("127.0.0.1", SECOND, "secondpass"))
H.load(view, url("/ms2/onescreen"))
# Both accounts are saved now, so nothing fills on arrival: with two to
# choose between the browser asks instead of guessing (test_acctpick).
# What this section is about is the account he names getting its own
# password, and that is unchanged.
check("nothing fills on arrival, the chooser asks",
      val("#user") == "" and br._acct_chooser is not None,
      "%r / %r" % (val("#user"), br._acct_chooser))
br._acct_chooser.cancel()
H.spin(300)
H.click(view, "#user")
H.type_text(view, FIRST)
H.spin(800)
check("he types the other one instead", val("#user") == FIRST, val("#user"))
H.click(view, "#pw")
H.spin(400)
check("and its own password fills, not the freshest one's",
      val("#pw") == "firstpass", val("#pw"))

print("\n(m) backspacing to the end counts as clearing it, too")
only(("127.0.0.1", FIRST, "firstpass"))
H.load(view, url("/ms2/rerender"))
check("filled once more", val("#loginfmt") == FIRST, val("#loginfmt"))
backspace_out("#loginfmt", len(FIRST))
check("held down to empty, and it stays empty",
      val("#loginfmt") == "", val("#loginfmt"))
H.spin(900)
check("still empty", val("#loginfmt") == "", val("#loginfmt"))

# =====================================================================
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAIL " + n)
srv.stop()
sys.exit(1 if bad else 0)
