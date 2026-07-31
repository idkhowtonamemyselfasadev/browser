"""Round-three defects: Back losing the hand-typed flag (N1), the
sign-in filter's unconditional branches (N2), a first-ever login on a
page that renders late (N3), and the blank-row repair (N4/N6)."""
import json, sys
import harness as H
import pages as PG
import pages3 as PG3
from PyQt6.QtCore import Qt
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtTest import QTest

B = H.boot()
app = H.app()

srv = H.Server({})
pages = PG.pages("http://localhost:%d/hop/step2" % srv.port)
pages.update(PG3.PAGES)
H.Handler.pages = pages

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name + (
        ("  <%s>" % extra) if extra else ""))


def val(sel):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel))


def only(*entries):
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


def step():
    return list(br._pw_steps.values())


def go(action):
    view.page().triggerAction(action)
    H.spin(1200)


def to_step2():
    H.click(view, "#next")
    H.wait_for(lambda: view.url().path() == "/nav/step2")
    H.spin(800)


def password_offered():
    """Spring the gate on step two and report what landed."""
    H.click(view, "#ap_password")
    H.key(view, Qt.Key.Key_Tab)
    H.spin(300)
    return val("#ap_password")


# =====================================================================
print("\n(q) N1: Back must not turn a typed account into a guess")
only(("127.0.0.1", "known@example.com", "pw-known"))
H.load(view, url("/nav/step1"))
check("step one prefilled the saved account",
      val("#ap_email") == "known@example.com", val("#ap_email"))
H.click(view, "#ap_email")
QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
               Qt.KeyboardModifier.ControlModifier)
H.spin(150)
H.type_text(view, "stranger@example.com")
H.spin(600)
check("he typed an account the vault does not know",
      step() and step()[0]["username"] == "stranger@example.com"
      and step()[0]["typed"], str(step()))
to_step2()
check("step two fills nothing, as advertised", password_offered() == "",
      password_offered())

go(QWebEnginePage.WebAction.Back)
H.wait_for(lambda: view.url().path() == "/nav/step1")
H.spin(900)
shown = val("#ap_email")
print("   after Back the box shows:", repr(shown))
check("Back kept the hand-typed flag",
      step() and step()[0]["typed"], str(step()))
to_step2()
got = password_offered()
check("after Back, step two still fills nothing",
      got == "" if shown == "stranger@example.com" else got == "pw-known",
      "box=%r filled=%r" % (shown, got))
check("no saved password went out under the typed name",
      got != "pw-known" or shown == "known@example.com",
      "box=%r filled=%r" % (shown, got))

print("\n(q2) ... and on the wire, and after Forward and a reload")
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
check("submitted an empty password", "password=" in view.url().query()
      and "pw-known" not in view.url().query(), view.url().toString())
go(QWebEnginePage.WebAction.Back)          # /done -> step two
H.spin(600)
go(QWebEnginePage.WebAction.Back)          # step two -> step one
H.wait_for(lambda: view.url().path() == "/nav/step1")
H.spin(900)
go(QWebEnginePage.WebAction.Forward)       # and forward again
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(900)
check("forward to step two fills nothing either", password_offered() == "",
      password_offered())
go(QWebEnginePage.WebAction.Back)
H.wait_for(lambda: view.url().path() == "/nav/step1")
H.spin(900)
go(QWebEnginePage.WebAction.Reload)
H.wait_for(lambda: view.url().path() == "/nav/step1")
H.spin(1200)
shown = val("#ap_email")
print("   after Reload the box shows:", repr(shown))
to_step2()
got = password_offered()
check("after a reload the fill still matches the box",
      got == "" if shown != "known@example.com" else got == "pw-known",
      "box=%r filled=%r" % (shown, got))

print("\n(q3) ... and the guards are what save it (bug restored on purpose)")
only(("127.0.0.1", "known@example.com", "pw-known"))
# Two rules hold this line now, so both have to come off to get the old
# bug back: the half-login stops being hand-chosen the moment the page
# reports the account as a guess again, and a half-login we have
# nothing saved for is allowed to fall back to the freshest login on
# the host. Either one alone still fills nothing — which is the point.
# out of __dict__, not off the class: reading a staticmethod through
# the class hands back the bare function, and putting that back turns
# it into an ordinary method that then gets `self` as its first
# argument for the rest of the run
keep_sticks = vars(B.Browser)["_typed_sticks"]
keep_entry = vars(B.Browser)["_pw_step_entry"]
B.Browser._typed_sticks = staticmethod(lambda old, typed: bool(typed))
B.Browser._pw_step_entry = (
    lambda self, host, scheme, step:
    self.vault.for_username(host, scheme, step["username"])
    or (None if step["typed"] else self.vault.best_for(host, scheme)))
try:
    H.load(view, url("/nav/step1"))
    H.click(view, "#ap_email")
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier)
    H.spin(150)
    H.type_text(view, "stranger@example.com")
    H.spin(600)
    to_step2()
    go(QWebEnginePage.WebAction.Back)
    H.wait_for(lambda: view.url().path() == "/nav/step1")
    H.spin(900)
    shown = val("#ap_email")
    to_step2()
    got = password_offered()
    check("without the guard the old bug is back (so the guard is real)",
          shown == "stranger@example.com" and got == "pw-known",
          "box=%r filled=%r" % (shown, got))
finally:
    B.Browser._typed_sticks = keep_sticks
    B.Browser._pw_step_entry = keep_entry

# =====================================================================
print("\n(r) N2: the sign-in filter's two overrides")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/nl-with-modal"))
check("a hidden login modal elsewhere does not vouch for a newsletter box",
      val("#nl") == "", val("#nl"))
H.load(view, url("/my-account/news"))
check("'account' in the path no longer unlocks a fill", val("#nl") == "",
      val("#nl"))
H.load(view, url("/author/someone"))
check("/author/someone is not an auth page", val("#nl") == "", val("#nl"))
H.load(view, url("/plainpage"))
H.spin(1200)                       # it replaceStates to /signin by now
check("the page rewrote its own URL",
      view.url().path() == "/signin", view.url().toString())
check("rewriting the URL in place does not unlock a fill",
      val("#nl") == "", val("#nl"))
H.load(view, url("/realsignin"))
check("a real sign-in still fills, planted 'Kontakt' and all",
      val("#ap_email") == "user@example.com", val("#ap_email"))

# =====================================================================
print("\n(s) N3: a first-ever login on a page that renders late")
only()                              # nothing saved anywhere
br._pw_pending = None
H.load(view, url("/late"))
check("no Next button yet", not H.js(view, "!!document.querySelector('#next')"))
H.click(view, "#identifierId")
H.type_text(view, "user@example.com")
H.spin(1600)                        # the button turns up meanwhile
check("the Next button has arrived",
      H.js(view, "!!document.querySelector('#next')"))
check("the browser learned the account anyway",
      step() and step()[0]["username"] == "user@example.com", str(step()))
H.click(view, "#next")
H.spin(900)
H.click(view, "#pw")
H.type_text(view, "hunter2")
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(500)
p = br._pw_pending or {}
check("the save prompt names the account, not a blank",
      p.get("username") == "user@example.com", str(p.get("username")))
br._pw_save_pending()
check("saved under a real username",
      [e["username"] for e in br.vault.logins()] == ["user@example.com"],
      str(br.vault.logins()))

# =====================================================================
print("\n(t) N4/N6: the blank-row repair")
v = br.vault
v.rows().clear()
v.data["entries"] = []
v.set_entry("a.com", "http", "", "P")
v.set_entry("a.com", "http", "user@x.com", "Q")
check("two rows to start with", len(v.logins()) == 2,
      str(v.logins()))
v.set_entry("a.com", "http", "user@x.com", "P")   # the named row exists
check("the blank row is absorbed even when the named row already exists",
      [e["username"] for e in v.logins()] == ["user@x.com"],
      str(v.logins()))
check("and the named row carries the password",
      v.get("a.com", "user@x.com")["password"] == "P")

v.rows().clear()
v.data["entries"] = []
v.set_entry("b.com", "http", "", "P")
v.set_entry("b.com", "http", "someone@x.com", "OTHER")
check("a blank row with a different password is left alone",
      len(v.logins()) == 2, str(v.logins()))

v.rows().clear()
v.data["entries"] = []
v.data["items"] = []
v.items = lambda: v.data["items"]           # the sibling branch's store
check("rows() follows items() when the store moves",
      v.rows() is v.data["items"])
v.data["items"].append({"type": "login", "host": "c.com", "username": "",
                        "password": "P"})
v._absorb_blank("c.com", "user@x.com", "P")
check("and the repair writes through it", v.data["items"] == [],
      str(v.data["items"]))
del v.items

srv.stop()
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
sys.exit(1 if bad else 0)
