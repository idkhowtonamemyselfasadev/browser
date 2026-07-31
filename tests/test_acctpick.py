"""The account chooser, driven with real Qt input against a real HTTP
server. Nothing here touches your data (see harness.boot).

The property under test, over and over: with two accounts saved for a
site, the form he is looking at is EMPTY until he has pointed at one of
them, and afterwards it holds that account and no other — in the DOM,
in the isolated world, and on the wire.
"""
import json
import sys

import harness as H
import pages7 as PG
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

B = H.boot()
app = H.app()

srv = H.Server(PG.pages())

br = B.Browser()
br.config["savePasswords"] = True
br.show()
H.spin(300)
view = br.current()

RESULTS = []
PUSHES = []       # every credential the browser pushes at a page, guessed
CHOSEN = []       # ... and every one it pushes because he picked it
_orig_push = br._pw_push
_orig_chosen = br._pw_push_chosen


def _record(page, user, password):
    PUSHES.append((page.url().path(), user, password))
    _orig_push(page, user, password)


def _record_chosen(page, user, password):
    CHOSEN.append((page.url().path(), user, password))
    _orig_chosen(page, user, password)


br._pw_push = _record
br._pw_push_chosen = _record_chosen

ONE = ("one@example.com", "pw-of-account-one")
TWO = ("two@example.com", "pw-of-account-two")


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name + (
        ("  <%s>" % (extra,)) if extra else ""))


def section(title):
    print("\n" + title)


def val(sel):
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel))


def true_val(sel):
    """The value as the DOM really holds it: read in the isolated world,
    where the page's own hooks on HTMLInputElement do not exist."""
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel),
                B.PW_WORLD_ID)


def only(*entries):
    """Reset the vault to exactly these logins (last one is freshest)."""
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    br._acct_auto.clear()
    br._close_account_chooser()
    del PUSHES[:]
    del CHOSEN[:]
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def two_accounts(host="127.0.0.1"):
    """TWO is saved first, ONE last, so ONE is the freshest — the one
    the browser would have guessed. Every test below picks TWO, so a
    fill that came from the guess is impossible to mistake for a pass."""
    only((host, TWO[0], TWO[1]), (host, ONE[0], ONE[1]))


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


def chooser():
    return br._acct_chooser


def wait_chooser(want=True, ms=6000):
    return H.wait_for(lambda: (chooser() is not None) == want, ms)


def names_on_panel():
    ch = chooser()
    return [] if ch is None else [b.text() for b in ch.buttons]


def esc_to_focus():
    """Esc where a person's Esc goes: at whatever holds the keyboard."""
    QTest.keyClick(QApplication.focusWidget() or br, Qt.Key.Key_Escape)
    H.spin(600)


def click_widget(w):
    """A real Qt press and release on a widget of the browser's own —
    H.press, never QAbstractButton.click(). See harness.press."""
    H.press(w)


def pick(name):
    ch = chooser()
    assert ch is not None, "no chooser on screen"
    for b in ch.buttons:
        if b.text() == name:
            click_widget(b)
            return True
    return False


def _panel_text():
    from PyQt6.QtWidgets import QLabel
    ch = chooser()
    return "" if ch is None else " ".join(
        w.text() for w in ch.panel.findChildren(QLabel))


def wire():
    """What actually left the browser: these forms submit by GET."""
    return view.url().toString()


# ===================================================================== #
section("(a) two accounts on one host: nothing is filled, the box asks")
two_accounts()
H.load(view, url("/pick/both"))
check("the chooser is on screen", wait_chooser(True))
check("it lists both accounts, freshest first",
      names_on_panel() == [ONE[0], TWO[0]], names_on_panel())
check("the username box is empty before he picks", true_val("#user") == "",
      repr(true_val("#user")))
check("the password box is empty before he picks", true_val("#pw") == "",
      repr(true_val("#pw")))
check("nothing was pushed at the page at all",
      all((not u and not p) for _, u, p in PUSHES), PUSHES)
check("and no password of either account was pushed",
      all(p not in (ONE[1], TWO[1]) for _, _, p in PUSHES), PUSHES)

section("    ... he picks the second account")
check("the panel had a button for it", pick(TWO[0]))
check("the chooser is gone", wait_chooser(False))
check("the username box holds the second account",
      true_val("#user") == TWO[0], true_val("#user"))
check("the password box holds the second account's password",
      true_val("#pw") == TWO[1], repr(true_val("#pw")))
check("the page itself sees the same values (no hidden second value)",
      val("#pw") == TWO[1] and val("#user") == TWO[0])
check("the first account's password never reached the page",
      all(p != ONE[1] for _, _, p in PUSHES + CHOSEN), PUSHES + CHOSEN)
check("only the chosen account crossed", CHOSEN == [("/pick/both",) + TWO],
      CHOSEN)

section("    ... and on the wire")
H.click(view, "#signin")
H.wait_for(lambda: "/done" in view.url().path(), 6000)
check("the wire carries the second account", TWO[1] in wire() and
      TWO[0].replace("@", "%40") in wire(), wire())
check("the wire never carries the first account's password",
      ONE[1] not in wire(), wire())

# ===================================================================== #
section("(b) one account: no chooser, today's behaviour exactly")
only(("127.0.0.1", ONE[0], ONE[1]))
H.load(view, url("/pick/both"))
H.spin(700)
check("no chooser", chooser() is None)
check("the address-bar handle stays away", br.acctbtn.isHidden())
check("the username still fills on its own", true_val("#user") == ONE[0],
      true_val("#user"))
check("the password still waits for a gesture", true_val("#pw") == "",
      repr(true_val("#pw")))
H.click(view, "#pw")
check("and lands on one", true_val("#pw") == ONE[1], repr(true_val("#pw")))
# the same document, with no panel over it: the node count to beat in (g)
NODES_WITHOUT_PANEL = H.js(view, "document.querySelectorAll('*').length")

section("    ... asked for by hand with only the one, it says so")
br.open_account_chooser()
H.spin(400)
check("the box opens because he asked", chooser() is not None)
check("with the one account on it", names_on_panel() == [ONE[0]],
      names_on_panel())
check("and says there is nothing to choose between",
      br._ui_str("acctPickNone") in _panel_text(), _panel_text())
pick(ONE[0])
H.spin(400)
check("and picking still works from it", true_val("#pw") == ONE[1],
      repr(true_val("#pw")))

# ===================================================================== #
section("(c) dismissing fills nothing")
two_accounts()
H.load(view, url("/pick/both"))
check("the chooser is up", wait_chooser(True))
QTest.keyClick(chooser(), Qt.Key.Key_Escape)
H.spin(400)
check("Esc closes it", chooser() is None)
check("the username box is still empty", true_val("#user") == "",
      repr(true_val("#user")))
check("the password box is still empty", true_val("#pw") == "",
      repr(true_val("#pw")))
check("nothing was marked hand-chosen", not any(
    s.get("typed") for s in br._pw_steps.values()), br._pw_steps)
H.click(view, "#pw")
H.spin(400)
check("a click on the page does not bring the guess back either",
      true_val("#pw") == "" and true_val("#user") == "",
      (true_val("#user"), true_val("#pw")))
H.click(view, "#signin")
H.wait_for(lambda: "/done" in view.url().path(), 6000)
check("so nothing goes on the wire", ONE[1] not in wire()
      and TWO[1] not in wire(), wire())

# ===================================================================== #
section("(d) summoned by hand, from the address bar")
two_accounts()
H.load(view, url("/pick/both"))
check("the automatic offer came up", wait_chooser(True))
QTest.keyClick(chooser(), Qt.Key.Key_Escape)
H.spin(300)
check("...and was dismissed", chooser() is None)
check("the handle is in the address bar", not br.acctbtn.isHidden())
click_widget(br.acctbtn)
check("clicking it brings the box back", wait_chooser(True))
check("with both accounts on it", names_on_panel() == [ONE[0], TWO[0]],
      names_on_panel())
pick(TWO[0])
H.spin(400)
check("picking fills the second account", true_val("#pw") == TWO[1],
      repr(true_val("#pw")))
check("and its username", true_val("#user") == TWO[0], true_val("#user"))

section("    ... and it corrects a wrong account already in the form")
check("summon it again", (br.open_account_chooser(), wait_chooser(True))[1])
pick(ONE[0])
H.spin(400)
check("the form now holds the first account", true_val("#user") == ONE[0]
      and true_val("#pw") == ONE[1],
      (true_val("#user"), true_val("#pw")))
check("with nothing of the second left behind", true_val("#pw") != TWO[1])

# ===================================================================== #
section("(e) two steps, a real navigation, no username box on step two")
two_accounts()
H.load(view, url("/pick/step1"))
check("the chooser is up on step one", wait_chooser(True))
check("the e-mail box is empty until he picks",
      true_val("#ap_email") == "", repr(true_val("#ap_email")))
pick(TWO[0])
H.spin(400)
check("picking fills the e-mail", true_val("#ap_email") == TWO[0],
      true_val("#ap_email"))
check("and the choice is remembered as hand-chosen", any(
    s.get("typed") and s.get("username") == TWO[0]
    for s in br._pw_steps.values()), br._pw_steps)
H.click(view, "#next")
H.wait_for(lambda: "/pick/step2" in view.url().path(), 8000)
H.spin(700)
check("step two has no username box at all",
      H.js(view, "!!document.querySelector('input[type=email]')") is False)
check("no second panel: the question already has an answer",
      chooser() is None)
check("the password box waits for a gesture", true_val("#ap_password") == "",
      repr(true_val("#ap_password")))
H.click(view, "#ap_password")
check("and then holds the account he chose on step one",
      true_val("#ap_password") == TWO[1], repr(true_val("#ap_password")))
check("never the freshest one", true_val("#ap_password") != ONE[1])
H.click(view, "#signin")
H.wait_for(lambda: "/done" in view.url().path(), 6000)
check("the wire carries the chosen account only",
      TWO[1] in wire() and ONE[1] not in wire(), wire())

section("    ... summoned straight onto a password-only step")
two_accounts()
H.load(view, url("/pick/step2"))
check("a lone password step raises the chooser", wait_chooser(True))
check("the box is empty", true_val("#ap_password") == "",
      repr(true_val("#ap_password")))
pick(TWO[0])
H.spin(400)
check("the pick alone fills it — no touch on the page",
      true_val("#ap_password") == TWO[1], repr(true_val("#ap_password")))
check("and never the other account", true_val("#ap_password") != ONE[1])

# ===================================================================== #
section("(f) the form swapped in place, no reload — the Microsoft case")
two_accounts()
H.load(view, url("/pick/spa"))
check("the chooser is up", wait_chooser(True))
check("the e-mail box is empty", true_val("#identifierId") == "",
      repr(true_val("#identifierId")))
pick(TWO[0])
H.spin(400)
check("picking fills the e-mail", true_val("#identifierId") == TWO[0],
      true_val("#identifierId"))
H.click(view, "#next")
H.spin(800)
check("the document swapped its form without navigating",
      "/pick/spa" in view.url().path()
      and H.js(view, "!!document.querySelector('#pw')") is True)
check("the username box is gone", H.js(
    view, "!!document.querySelector('#identifierId')") is False)
check("no second panel", chooser() is None)
H.click(view, "#pw")
check("the password of the chosen account lands",
      true_val("#pw") == TWO[1], repr(true_val("#pw")))
check("never the other one", true_val("#pw") != ONE[1])
H.click(view, "#signin")
H.wait_for(lambda: "/done" in view.url().path(), 6000)
check("and that is what goes on the wire",
      TWO[1] in wire() and ONE[1] not in wire(), wire())

# ===================================================================== #
section("(g) a page cannot see the chooser")
two_accounts()
before = H.js(view, "Object.getOwnPropertyNames(window).join(',')")
H.load(view, url("/pick/both"))
check("the chooser is up", wait_chooser(True))
after = H.js(view, "Object.getOwnPropertyNames(window).join(',')")
check("no new global appeared in the page's world",
      set(after.split(",")) - set(before.split(",")) == set(),
      sorted(set(after.split(",")) - set(before.split(","))))
check("__bpw is not visible from the page",
      H.js(view, "typeof window.__bpw") == "undefined",
      H.js(view, "typeof window.__bpw"))
check("it is only in the isolated world",
      H.js(view, "typeof window.__bpw.choose", B.PW_WORLD_ID) == "function")
html = H.js(view, "document.documentElement.outerHTML")
check("no account name is anywhere in the document",
      ONE[0] not in html and TWO[0] not in html)
check("nor any password", ONE[1] not in html and TWO[1] not in html)
nodes = H.js(view, "document.querySelectorAll('*').length")
check("the document has exactly the nodes it has without the panel",
      nodes == NODES_WITHOUT_PANEL, (nodes, NODES_WITHOUT_PANEL))
check("not a word of the panel is in the page",
      br._ui_str("acctPickTitle") not in html
      and br._ui_str("acctPickCancel") not in html)
check("no shadow root was planted on the body",
      H.js(view, "!!document.body.shadowRoot") is False)
vals = H.js(view, "(function(){var o=[];var e=document.forms[0].elements;"
                  "for(var i=0;i<e.length;i++)o.push(e[i].value);"
                  "return o.join('|');})()")
check("every field the page can read is empty",
      all(v == "" for v in vals.split("|")), repr(vals))

# ===================================================================== #
section("(h) forged events cannot open it, or choose from it")
FORGE = r"""(function () {
  var found = [];
  if (typeof window.__bpw !== "undefined") found.push("__bpw reachable");
  var targets = [document, document.documentElement, document.body];
  var q = document.querySelectorAll("input, button");
  for (var i = 0; i < q.length; i++) targets.push(q[i]);
  var kinds = ["pointerdown", "mousedown", "mouseup", "pointerup",
               "keydown", "keyup", "paste", "focus", "input", "change"];
  for (var a = 0; a < targets.length; a++) {
    for (var b = 0; b < kinds.length; b++) {
      try {
        var ev;
        if (kinds[b] === "keydown" || kinds[b] === "keyup")
          ev = new KeyboardEvent(kinds[b], {key: "Enter", bubbles: true,
                                            ctrlKey: true, shiftKey: true});
        else if (kinds[b].indexOf("pointer") === 0
                 || kinds[b].indexOf("mouse") === 0)
          ev = new MouseEvent(kinds[b], {bubbles: true, button: 0});
        else ev = new Event(kinds[b], {bubbles: true});
        targets[a].dispatchEvent(ev);
      } catch (e) {}
    }
  }
  // and the one thing a page could hope to reach: the channel object
  try { if (window.qt && qt.webChannelTransport) found.push("transport"); }
  catch (e) {}
  return found.join(",");
})()"""

two_accounts()
del CHOSEN[:]
H.load(view, url("/pick/both"))
check("the chooser is up", wait_chooser(True))
open_before = chooser()
found = H.js(view, FORGE)
H.spin(600)
check("the page found nothing of ours", found == "", found)
check("the panel is untouched by all of it", chooser() is open_before)
check("nothing was chosen", CHOSEN == [], CHOSEN)
check("the username box is still empty", true_val("#user") == "",
      repr(true_val("#user")))
check("the password box is still empty", true_val("#pw") == "",
      repr(true_val("#pw")))

section("    ... and with no chooser on screen, they cannot raise one")
QTest.keyClick(chooser(), Qt.Key.Key_Escape)
H.spin(300)
check("dismissed", chooser() is None)
found = H.js(view, FORGE)
H.spin(600)
check("no panel was raised by forged input", chooser() is None)
check("still nothing chosen", CHOSEN == [], CHOSEN)
check("and still nothing in the form",
      true_val("#user") == "" and true_val("#pw") == "",
      (true_val("#user"), true_val("#pw")))

# ===================================================================== #
section("(h2) the panel belongs to one page, and goes when that page does")
two_accounts()
H.load(view, url("/pick/both"))
check("the chooser is up", wait_chooser(True))
br.new_tab(url("/done"))
H.spin(1200)
check("switching tab takes the question away", chooser() is None)
check("and it filled nothing on the way out", true_val("#user") == "")
br.close_tab(br.tabs.indexOf(br.current()))
H.spin(600)
view = br.current()

# ===================================================================== #
section("(i) the panel holds names and nothing else")
two_accounts()
H.load(view, url("/pick/both"))
check("the chooser is up", wait_chooser(True))
ch = chooser()
blob = json.dumps({k: repr(v) for k, v in vars(ch).items()})
check("no password anywhere in its state",
      ONE[1] not in blob and TWO[1] not in blob)
labels = " | ".join([b.text() for b in ch.buttons]
                    + [b.toolTip() for b in ch.buttons])
check("its buttons carry usernames only",
      ONE[1] not in labels and TWO[1] not in labels, labels)
check("it never holds an entry, only names",
      all(not isinstance(v, dict) for v in vars(ch).values()))
ch.cancel()
H.spin(200)

# ===================================================================== #
section("(j) Esc: one key, one owner, whatever else is on screen")
# The panel used to register an Esc QShortcut of its own. The window
# already has one — _pane_esc — and two shortcuts matching one key is
# not a race the newer one wins: Qt calls it ambiguous and runs
# neither. With a pane up and the panel over it, Esc closed nothing at
# all, for ever, which is the one thing _pane_esc promises never
# happens.
#
# These checks were run against every way of getting it wrong, and
# each one is caught: the shipped shortcut (ambiguous, nothing
# closes), the shortcut with a focus policy bolted on (still
# ambiguous), and a plain keyPressEvent with no ShortcutOverride —
# which is the quiet one, because the browser still looks responsive:
# the pane closes and the panel he was looking at stays.
from PyQt6.QtGui import QKeySequence, QShortcut     # noqa: E402

two_accounts()
H.load(view, url("/pick/both"))
wait_chooser(True)
chooser().cancel()
H.spin(300)

AMBIG = []
br._pane_esc.activatedAmbiguously.connect(lambda: AMBIG.append("pane"))

br.open_settings()
H.wait_for(lambda: br._pane is not None and br._pane.isVisible(), 8000)
check("a pane is up", br._pane is not None and br._pane.isVisible())
# raised over the pane on purpose: the state open_account_chooser now
# refuses to create, kept as the belt to that pair of braces
br._show_account_chooser(view, [ONE[0], TWO[0]])
H.spin(400)
check("and the panel over it", chooser() is not None)
check("the panel registers no Esc shortcut of its own",
      not [sc for sc in chooser().findChildren(QShortcut)
           if sc.key() == QKeySequence("Esc")],
      str([sc.key().toString() for sc in chooser().findChildren(QShortcut)]))

esc_to_focus()
check("the first Esc takes the panel and leaves the pane",
      chooser() is None and br._pane is not None and br._pane.isVisible(),
      "chooser=%s pane=%s" % (chooser() is not None, br._pane is not None))
esc_to_focus()
check("the second Esc takes the pane, as it always did",
      br._pane is None or not br._pane.isVisible())
check("and nothing was ever ambiguous", AMBIG == [], AMBIG)

section("    ... and the panel is never over a pane in the first place")
br.open_settings()
H.wait_for(lambda: br._pane is not None and br._pane.isVisible(), 8000)
check("a pane is up again", br._pane is not None and br._pane.isVisible())
br.open_account_chooser()
H.spin(500)
check("asking for the panel takes the pane down",
      br._pane is None or not br._pane.isVisible())
check("and the panel is up", chooser() is not None)
check("with the keyboard, so Esc is its own",
      QApplication.focusWidget() is chooser(),
      type(QApplication.focusWidget()).__name__)
esc_to_focus()
check("which closes it and fills nothing", chooser() is None
      and true_val("#pw") == "", repr(true_val("#pw")))

# ===================================================================== #
section("(k) the half-login machinery is left as it was")
check("_typed_sticks still latches on", B.Browser._typed_sticks(
    {"typed": True}, False) is True)
check("_typed_sticks still starts from the flag it is given",
      B.Browser._typed_sticks(None, True) is True)
check("and stays down when neither says so",
      B.Browser._typed_sticks({"typed": False}, False) is False)
check("PW_STEP_TTL untouched", B.PW_STEP_TTL == 300)

# ===================================================================== #
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
srv.stop()
sys.exit(1 if bad else 0)
