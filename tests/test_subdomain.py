"""A half-finished login that walks to another subdomain, or from http
to https, and the password that used to fill step two.

The hole every one of these covers is the same one. The half-login was
filed under (profile, tab, host) and dropped the moment the tab changed
host, on the reasoning that the landing page is then just a fresh page
and "fills only from a login actually saved for the host it is on".
That reasoning assumed host-exact matching. Matching is not host-exact:
PasswordVault.entries_for deliberately lets a subdomain match its
parent's row, and lets an http row fill the site's https upgrade. So on
account.example.com the row saved for example.com *is* "a login saved
for the host it is on", and step two — which has no username box, so
there is nothing on screen to contradict it — was handed the freshest
one. In a session the site had just opened for the account he typed.

Every other suite here uses 127.0.0.1 and localhost as two flat,
unrelated hosts, which is exactly why this was never crossed with the
two-step record. These pages are served on sibling subdomains of one
parent, so a real navigation between them can be driven for real.

Nothing here touches your data (see harness.boot).
"""
import json
import sys
import time

import harness as H
import pages6 as PG6
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

B = H.boot()
app = H.app()

srv = H.Server({})
PORT = srv.port
H.Handler.pages = PG6.pages(PORT)

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

RESULTS = []
PUSHES = []                 # every credential the browser pushes at a page
_orig_push = br._pw_push


def _record(page, user, password):
    PUSHES.append((page.url().host(), page.url().path(), user, password))
    _orig_push(page, user, password)


br._pw_push = _record


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name + (
        ("  <%s>" % extra) if extra else ""))


def val(sel):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel))


def only(*entries):
    """Reset the vault to exactly these logins (last one is freshest)."""
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    br._pw_pending = None
    del PUSHES[:]
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def url(path, host="localhost"):
    return "http://%s:%d%s" % (host, PORT, path)


def type_into(sel, text):
    H.click(view, sel)
    QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier)
    H.spin(150)
    H.type_text(view, text)
    H.spin(600)


def step_two(path_end="/step2"):
    H.click(view, "#next")
    H.wait_for(lambda: view.url().path().endswith(path_end))
    H.spin(900)


def submit():
    H.click(view, "#signin")
    H.wait_for(lambda: view.url().path() == "/done")
    H.spin(400)
    return view.url().query()


def pushed_at(host):
    return [(u, p) for h, _, u, p in PUSHES if h == host]


# =====================================================================
print("\n(d4) the subdomain hop: he typed one account, step two is a "
      "sibling host")
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/sub/step1", "login.localhost"))
check("step one guesses the account saved for the parent domain",
      val("#ap_email") == "alice@x.com", val("#ap_email"))
type_into("#ap_email", "bob@x.com")
check("and he replaces it by hand", val("#ap_email") == "bob@x.com",
      val("#ap_email"))
check("the half-login says bob, and says he typed it",
      any(v["username"] == "bob@x.com" and v["typed"]
          for v in br._pw_steps.values()), str(br._pw_steps))
step_two()
check("step two really is on the sibling host",
      view.url().host() == "account.localhost", view.url().toString())
H.click(view, "#ap_password")           # one real click, the gesture gate
H.spin(600)
check("the password box stays empty", val("#ap_password") == "",
      repr(val("#ap_password")))
check("and alice's password was never pushed at the page",
      all(p != "ALICE-SECRET" for _, p in pushed_at("account.localhost")),
      str(pushed_at("account.localhost")))
got = submit()
check("nothing of alice's reaches the wire", "ALICE-SECRET" not in got, got)
check("the form went out empty", "password=" in got and got.endswith(
      "password="), got)
br._pw_dismiss()

# =====================================================================
print("\n(d5) the parent's row, and step two on a subdomain of it")
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/down/step1"))        # step one on the parent itself
check("step one guesses alice here too", val("#ap_email") == "alice@x.com",
      val("#ap_email"))
type_into("#ap_email", "bob@x.com")
step_two()
check("step two is on the subdomain",
      view.url().host() == "shop.localhost", view.url().toString())
H.click(view, "#ap_password")
H.spin(600)
check("the parent's row does not fill the subdomain's password box",
      val("#ap_password") == "", repr(val("#ap_password")))
got = submit()
check("and it does not reach the wire either", "ALICE-SECRET" not in got, got)
br._pw_dismiss()

# =====================================================================
print("\n(d6) the same hole through a change of scheme")
# An https step two cannot be served here without a certificate the
# engine would trust, so this one is asked at the decision point: the
# half-login is real, made by a real page and real typing, and
# _pw_entry_for is the function that answers "whose password box is
# this". An http row fills an https page (entries_for says so), which
# is the whole reason the scheme hop reached the same fallback.
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/same/step1", "login.localhost"))
type_into("#ap_email", "bob@x.com")
page = view.page()
check("the http half-login is on record",
      any(v["username"] == "bob@x.com" and v["scheme"] == "http"
          for v in br._pw_steps.values()), str(br._pw_steps))
check("an http row would indeed fill the https page",
      (br.vault.best_for("login.localhost", "https") or {}).get("username")
      == "alice@x.com",
      str(br.vault.best_for("login.localhost", "https")))
answer = br._pw_entry_for(page, "login.localhost", "https", "")
check("but the https step two gets nothing, not alice",
      answer is None, str(answer and answer.get("username")))
answer = br._pw_entry_for(page, "account.localhost", "https", "")
check("nor does an https step two on a sibling host",
      answer is None, str(answer and answer.get("username")))

# The other half of the scheme question, and the half that says the
# record is genuinely read across it rather than merely refusing
# everything: with the chosen account saved, the http half-login must
# govern the https page and fill it.
# bob's row is the older of the two, so alice is what the freshest-here
# fallback would hand over: filling bob means the half-login decided.
only(("localhost", "bob@x.com", "BOB-SECRET"),
     ("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/same/step1", "login.localhost"))
type_into("#ap_email", "bob@x.com")
page = view.page()
check("the freshest login on the https page is still alice's",
      (br.vault.best_for("login.localhost", "https") or {}).get("username")
      == "alice@x.com",
      str((br.vault.best_for("login.localhost", "https") or {}).get(
          "username")))
answer = br._pw_entry_for(page, "login.localhost", "https", "")
check("an http half-login governs the https step, and fills bob's",
      (answer or {}).get("password") == "BOB-SECRET",
      str(answer and answer.get("username")))
answer = br._pw_entry_for(page, "shop.localhost", "https", "")
check("and it governs the https step on a subdomain too",
      (answer or {}).get("password") == "BOB-SECRET",
      str(answer and answer.get("username")))

# The tab is in the key, and so is the profile: a page id the engine
# has handed out again in another virtual browser must not read this
# one's half-login.
key = br._pw_step_key(page, "login.localhost")
br._pw_steps[("other-profile", key[1], "login.localhost")] = {
    "host": "login.localhost", "scheme": "http",
    "username": "someone@else.com", "typed": True, "at": time.monotonic()}
answer = br._pw_step_for(page, "login.localhost", "http")
check("another profile's record is not this tab's half-login",
      (answer or {}).get("username") == "bob@x.com",
      str(answer and answer.get("username")))
del br._pw_steps[("other-profile", key[1], "login.localhost")]

# =====================================================================
print("\n(d6b) an open redirector cannot choose which password goes out")
# He types his ordinary account on the honest host. The chain routes
# him through an unrelated origin that writes a *different* account of
# his into its own box, and hands him back for the password step. The
# name the browser carries is only ever what some page put in a box, so
# off the site it must not be consulted at all: this page is a fresh
# page and gets the browser's own answer, not the redirector's.
#
# This one guards the fix rather than the original defect. The first
# attempt at it let the half-login govern the tab on any host, on the
# argument that a name can only narrow what the page already matched —
# true, and beside the point, because narrowing is choosing and the
# chooser was a stranger's page. It sent VIP-SECRET here.
only(("localhost", "vip@corp.com", "VIP-SECRET"),
     ("localhost", "personal@x.com", "PERSONAL-PW"))
H.load(view, url("/redir/a1"))
type_into("#ap_email", "personal@x.com")
check("the half-login is his, and hand-typed",
      [(v["host"], v["username"], v["typed"])
       for v in br._pw_steps.values()] ==
      [("localhost", "personal@x.com", True)], str(br._pw_steps))
H.click(view, "#next")
H.wait_for(lambda: view.url().host() == "127.0.0.1")
H.spin(1200)
check("the redirector names an account of its own",
      val("#ap_email") == "vip@corp.com", val("#ap_email"))
noted = [(v["host"], v["username"], v["typed"])
         for v in br._pw_steps.values()]
check("and its substitution is not recorded as something he typed",
      noted == [("127.0.0.1", "vip@corp.com", False)], str(noted))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/redir/a2")
H.spin(1200)
check("back on the honest host for the password step",
      view.url().host() == "localhost", view.url().toString())
check("the redirector's half-login cannot be read here",
      br._pw_step_for(view.page(), "localhost", "http") is None,
      str(br._pw_steps))
H.click(view, "#ap_password")
H.spin(700)
check("the redirector did not get to pick the account",
      val("#ap_password") != "VIP-SECRET", repr(val("#ap_password")))
# Two accounts are saved on this host, so the page nobody has claimed
# is answered by nobody: the browser no longer reaches for the freshest
# row, it asks. Strictly less than it used to hand out here, and the
# account the redirector wanted is still not among the answers offered
# — the panel lists what the vault holds for the honest host.
check("and neither did the browser, unasked",
      val("#ap_password") == "", repr(val("#ap_password")))
check("it asked instead", br._acct_chooser is not None)
check("the panel offers his own two accounts and nothing of anyone's",
      sorted(b.text() for b in br._acct_chooser.buttons)
      == ["personal@x.com", "vip@corp.com"],
      str([b.text() for b in br._acct_chooser.buttons]))
H.press([b for b in br._acct_chooser.buttons
         if b.text() == "personal@x.com"][0])
H.spin(600)
check("the honest host answers for itself once he has said who he is",
      val("#ap_password") == "PERSONAL-PW", repr(val("#ap_password")))
got = submit()
check("and that is what goes on the wire",
      "password=PERSONAL-PW" in got and "VIP-SECRET" not in got, got)
br._pw_dismiss()

# =====================================================================
print("\n(d6c) a save after an unrelated hop names nobody")
# The mirror of (d10). A step one abandoned on one origin must not put
# its account on a row saved for a different site — that row would fill
# under that name ever after.
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/redir/a1"))
type_into("#ap_email", "bob@x.com")
H.load(view, url("/redir/a2", "127.0.0.1"))    # a lone password box, elsewhere
H.click(view, "#ap_password")
H.spin(400)
H.type_text(view, "GATE-PW")
submit()
p = br._pw_pending or {}
check("the pending row carries no username at all",
      p.get("username") == "" and p.get("host") == "127.0.0.1",
      str({k: v for k, v in p.items() if k != "password"}))
br._pw_dismiss()

# =====================================================================
print("\n(d7) control: the chosen account's own password still crosses "
      "the hop")
# Again bob is the older row, so nothing but the half-login would pick
# him: alice is the freshest and alice is what the old code sent.
only(("localhost", "bob@x.com", "BOB-SECRET"),
     ("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/sub/step1", "login.localhost"))
type_into("#ap_email", "bob@x.com")
step_two()
H.click(view, "#ap_password")
H.spin(600)
check("bob's own password fills on the sibling host",
      val("#ap_password") == "BOB-SECRET", repr(val("#ap_password")))
got = submit()
check("and it is bob's that goes out", "password=BOB-SECRET" in got, got)
check("alice's never appears", "ALICE-SECRET" not in got, got)
br._pw_dismiss()

# =====================================================================
print("\n(d8) control: a genuinely fresh page on the site fills as it "
      "always did")
only(("localhost", "alice@x.com", "ALICE-SECRET"))
check("no half-login anywhere", not br._pw_steps, str(br._pw_steps))
H.load(view, url("/sub/step2", "account.localhost"))   # straight to step two
H.click(view, "#ap_password")
H.spin(600)
check("the parent's row fills a subdomain's lone password box",
      val("#ap_password") == "ALICE-SECRET", repr(val("#ap_password")))
got = submit()
check("and it reaches the wire", "password=ALICE-SECRET" in got, got)
br._pw_dismiss()

# =====================================================================
print("\n(d9) control: a login carried through to the end, and cleared")
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/same/step1", "login.localhost"))
check("step one filled", val("#ap_email") == "alice@x.com", val("#ap_email"))
step_two()
H.click(view, "#ap_password")
H.spin(600)
check("step two fills the account step one was filled with",
      val("#ap_password") == "ALICE-SECRET", repr(val("#ap_password")))
got = submit()
check("the whole two-step login still works end to end",
      "password=ALICE-SECRET" in got, got)
check("and the half-login is cleared once it is over",
      not br._pw_steps, str(br._pw_steps))
br._pw_dismiss()

# =====================================================================
print("\n(d10) saving after a hop knows whose password it is")
only(("localhost", "alice@x.com", "ALICE-SECRET"))
H.load(view, url("/sub/step1", "login.localhost"))
type_into("#ap_email", "bob@x.com")
step_two()
H.click(view, "#ap_password")
H.spin(400)
H.type_text(view, "BOB-TYPED")
submit()
p = br._pw_pending or {}
check("the save prompt names the account he chose, on the host that "
      "asked", (p.get("username"), p.get("host")) ==
      ("bob@x.com", "account.localhost"),
      str({k: v for k, v in p.items() if k != "password"}))
check("with the password the site actually took",
      p.get("password") == "BOB-TYPED")
check("and the tab is no longer halfway through anything",
      not br._pw_steps, str(br._pw_steps))
br._pw_dismiss()

# =====================================================================
print("\n(d11) a tab that finished one login is a fresh page again")
# What the half-login suppresses is the *guess*, and only on its own
# site: (d10) submitted, which clears the tab's record outright, so
# this fills normally again. Worth being exact about the case that
# does not submit — an SPA that signs in over fetch never reaches
# _password_submitted, so its record sits out the five minutes. What
# that costs is bounded: on the site it belongs to, the account he
# chose keeps answering instead of the freshest one, which is the
# behaviour wanted there anyway; anywhere else _pw_step_for cannot
# read it and the page fills exactly as it always did. See (d6b).
H.load(view, url("/sub/step2", "account.localhost"))
H.click(view, "#ap_password")
H.spin(600)
check("the freshest login on the site fills again",
      val("#ap_password") == "ALICE-SECRET", repr(val("#ap_password")))
br._pw_dismiss()

srv.stop()
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
sys.exit(1 if bad else 0)
