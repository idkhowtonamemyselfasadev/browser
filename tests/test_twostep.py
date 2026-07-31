"""Two-step autofill, driven with real Qt input against a real HTTP
server. Nothing here touches your data (see harness.boot)."""
import json, sys
import harness as H
import pages as PG
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

B = H.boot()
app = H.app()

srv = H.Server({})          # port first, so /hop/step1 can point at it
HOP_TARGET = "http://localhost:%d/hop/step2" % srv.port
H.Handler.pages = PG.pages(HOP_TARGET)

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


def true_val(sel):
    """The value as the DOM really holds it: read in the isolated
    world, where the page's hooks on HTMLInputElement do not exist."""
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel),
                B.PW_WORLD_ID)


def only(*entries):
    """Reset the vault to exactly these logins (last one is freshest)."""
    # through the accessor: the live list moved to data["items"] when the
    # password manager landed, and clearing the old key silently reset
    # nothing, so every section inherited the last one's logins
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    del PUSHES[:]
    for i, (host, user, pw) in enumerate(entries):
        br.vault.set_entry(host, "http", user, pw)
        br.vault.get(host, user)["used"] = 1000 + i
    br.vault._save()


def url(path, host="127.0.0.1"):
    return srv.url(path, host)


ATTACKS = r"""(function () {
  var out = [];
  var pw = document.querySelector('input[type=password]');
  var form = pw && pw.form;
  var btn = document.querySelector('button');
  var native = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype, 'value').set;   // to undo our own mess
  function t(name, fn) { try { fn(); } catch (e) {} out.push(name); }
  // stay on the page so the field can be inspected afterwards; the gate
  // has no submit hook by design, so this costs the attack nothing
  if (form) form.addEventListener('submit',
      function (e) { e.preventDefault(); }, true);
  // 1-2: make the browser think a click or a submit happened
  t('btn.click', function () { btn.click(); });
  t('form.requestSubmit', function () { form.requestSubmit(); });
  // 3-10: synthesised events of every shape, on every plausible target
  ['pointerdown', 'mousedown', 'mouseup', 'click', 'pointerup'].forEach(
    function (k) {
      t('dispatch ' + k, function () {
        [pw, btn, form, document, document.body, window].forEach(function (tg) {
          tg.dispatchEvent(new MouseEvent(k, {bubbles: true, view: window,
                                              cancelable: true}));
        });
      });
    });
  ['keydown', 'keyup', 'keypress'].forEach(function (k) {
    t('dispatch ' + k, function () {
      [pw, btn, form, document, document.body, window].forEach(function (tg) {
        tg.dispatchEvent(new KeyboardEvent(k, {bubbles: true, key: 'Enter',
                                               keyCode: 13, which: 13}));
      });
    });
  });
  // 11: the submit event itself
  t('dispatch submit', function () {
    form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
  });
  // 12: forge isTrusted on one event
  t('defineProperty isTrusted (event)', function () {
    var e = new MouseEvent('pointerdown', {bubbles: true});
    Object.defineProperty(e, 'isTrusted', {value: true, configurable: true});
    (btn || document).dispatchEvent(e);
  });
  // 13: forge isTrusted for every event, page-wide
  t('defineProperty isTrusted (Event.prototype)', function () {
    Object.defineProperty(Event.prototype, 'isTrusted',
                          {get: function () { return true; },
                           configurable: true});
    (btn || document).dispatchEvent(new MouseEvent('pointerdown',
                                                   {bubbles: true}));
    document.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true,
                                                         key: 'Tab'}));
  });
  // 14-16: focus tricks
  t('focus/blur', function () { pw.focus(); pw.blur(); pw.focus(); });
  t('select', function () { pw.select(); });
  t('autofocus', function () { pw.setAttribute('autofocus', ''); });
  // 17: pretend the field was already touched
  t('dispatch input/change/paste', function () {
    ['input', 'change', 'paste'].forEach(function (k) {
      pw.dispatchEvent(new Event(k, {bubbles: true}));
    });
  });
  // 18: a scripted "user" typing (this one legitimately makes the
  // filler back off for good, the way typing your own password does)
  t('execCommand insertText', function () {
    pw.focus(); document.execCommand('insertText', false, 'x');
    native.call(pw, ''); });
  // 19: watch the value arrive (an accessor on the element)
  t('value getter', function () {
    Object.defineProperty(pw, 'value', {set: function (v) { window.__stolen = v; },
                                        get: function () { return ''; },
                                        configurable: true});
  });
  // 20: replace the setter the filler uses
  t('HTMLInputElement.prototype.value setter', function () {
    var d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    Object.defineProperty(HTMLInputElement.prototype, 'value', {
      set: function (v) { window.__stolen2 = v; d.set.call(this, v); },
      get: function () { return d.get.call(this); }, configurable: true});
  });
  // 21: reach into the isolated world where the filler lives
  t('reach isolated world', function () {
    window.__seen_bpw = (typeof window.__bpw !== 'undefined');
    window.__seen_qt = (typeof qt !== 'undefined');
  });
  return out.length;
})()"""


def gate_holds(sel, label):
    """21 script-only attacks in the page's own world; the 22nd (a
    scripted form.submit(), which navigates) is its own test below."""
    n = H.js(view, ATTACKS)
    H.spin(400)
    check("%d script-only attacks leak nothing (%s)" % ((n or 0) + 1, label),
          true_val(sel) in ("", None), repr(true_val(sel)))
    check("the page's own value hooks captured nothing (%s)" % label,
          H.js(view, "window.__stolen === undefined"
                     " && window.__stolen2 === undefined"))
    check("page script cannot see the isolated world (%s)" % label,
          H.js(view, "!window.__seen_bpw && !window.__seen_qt"))


# =====================================================================
print("\n(c) the conventional form: both fields at once")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/both"))
check("username filled on load", val("#user") == "user@example.com",
      val("#user"))
check("password empty before any gesture", val("#pw") == "")
gate_holds("#pw", "both fields")

H.load(view, url("/both"))                       # a clean document
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("a real click on Log in fills and submits it",
      "password=hunter2" in view.url().query(), view.url().toString())

print("\n(c2) attack: a scripted form.submit(), no gesture anywhere")
H.load(view, url("/both"))
H.js(view, "document.forms[0].submit()")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("the form posts an empty password",
      "password=" in view.url().query()
      and "password=hunter2" not in view.url().query(),
      view.url().toString())

# =====================================================================
print("\n(a) two steps with a real navigation between them")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/nav/step1"))
check("step one: e-mail filled", val("#ap_email") == "user@example.com",
      val("#ap_email"))
check("step one: the browser remembered the account",
      any(v["username"] == "user@example.com" for v in br._pw_steps.values()))
check("step one: no password was sent to the page at all",
      all(p == "" for _, _, p in PUSHES), str(PUSHES))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(700)
check("step two reached", view.url().path() == "/nav/step2",
      view.url().toString())
check("step two: password empty before a gesture",
      val("#ap_password") == "")
gate_holds("#ap_password", "step two")

H.load(view, url("/nav/step2"))       # clean document, same half-login
check("still empty on a fresh step two", val("#ap_password") == "")
H.click(view, "#ap_password")         # into the box: this is the gesture
check("clicking into the box fills it",
      val("#ap_password") == "hunter2", val("#ap_password"))

H.load(view, url("/nav/step2"))       # again, to check the other gesture
check("still empty on a fresh step two", val("#ap_password") == "")
H.key(view, Qt.Key.Key_Tab)
check("step two: password fills on a real keystroke",
      val("#ap_password") == "hunter2", val("#ap_password"))

print("\n(a2) ... and a real click on Sign in submits it")
H.load(view, url("/nav/step1"))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(700)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("submitted with the password", "password=hunter2" in view.url().query(),
      view.url().toString())

# =====================================================================
print("\n(b) one document, the DOM swaps in place, no navigation")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/spa"))
check("step one: e-mail filled", val("#identifierId") == "user@example.com",
      val("#identifierId"))
check("step one: no password was sent to the page at all",
      all(p == "" for _, _, p in PUSHES), str(PUSHES))
H.click(view, "#next")                # swaps the field, no navigation
H.spin(900)
check("no navigation happened", view.url().path() == "/spa")
check("password box appeared", H.js(view, "!!document.querySelector('#pw')"))
check("password still empty right after the swap", val("#pw") == "")
check("only now is the password pushed",
      any(p == "hunter2" for _, _, p in PUSHES), str(PUSHES))
gate_holds("#pw", "after the swap")

H.load(view, url("/spa"))             # clean document, same flow again
H.click(view, "#next")
H.spin(900)
check("password empty right after the swap", val("#pw") == "")
H.click(view, "#signin")
check("password fills on the next real click", val("#pw") == "hunter2",
      val("#pw"))

# =====================================================================
print("\n(d) attack: the second step is on another origin")
only(("127.0.0.1", "user@example.com", "hunter2"),
     ("localhost", "someone.else@example.com", "otherpass"))
H.load(view, url("/hop/step1"))
check("step one: e-mail filled", val("#ap_email") == "user@example.com")
H.click(view, "#next")
H.wait_for(lambda: view.url().host() == "localhost")
H.spin(800)
check("landed on the other host", view.url().host() == "localhost",
      view.url().toString())
# The property, not the filing. The record itself outlives the hop now
# — one half-login per tab, expired by the clock — but it must not be
# readable here, and it must not choose here. What the browser
# remembers is a *name*, and a name is whatever some page put in a box;
# let it cross to an unrelated origin and a page in the middle of a
# redirect chain gets to pick which of his saved logins this host's
# password step hands over. Off the site it is not consulted at all,
# and this page is a fresh page like any other.
check("the half-login cannot be read on an unrelated origin",
      br._pw_step_for(view.page(), "localhost", "http") is None,
      str(br._pw_steps))
check("the identity does not cross: nothing here is answered as the saved user",
      (br._pw_entry_for(view.page(), "localhost", "http", "") or {}
       ).get("username") != "user@example.com",
      str(br._pw_entry_for(view.page(), "localhost", "http", "")))
check("the first host's password was never pushed there",
      all(not (path.startswith("/hop/step2") and p == "hunter2")
          for path, _, p in PUSHES), str(PUSHES))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
got = view.url().query()
check("the other host never sees the first host's password",
      "hunter2" not in got, got)
check("it filled only its own saved login", "password=otherpass" in got, got)

print("\n(d2) the same hop, with nothing saved for the other host")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/hop/step1"))
H.click(view, "#next")
H.wait_for(lambda: view.url().host() == "localhost")
H.spin(800)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
check("nothing is filled there", "password=" in view.url().query()
      and "hunter2" not in view.url().query(), view.url().toString())

# =====================================================================
print("\n(e) attack: a password box planted where nobody can see it")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/hidden"))
check("the visible e-mail box is still filled",
      val("#ap_email") == "user@example.com", val("#ap_email"))
check("the browser calls this an identifier step",
      all(p == "" for _, _, p in PUSHES), str(PUSHES))
H.click(view, "#next")
H.click(view, "#ap_email")
H.key(view, Qt.Key.Key_Tab)
H.spin(400)
check("display:none password box stays empty", val("#trap") == "",
      val("#trap"))
check("1px transparent password box stays empty", val("#trap2") == "",
      val("#trap2"))

# =====================================================================
print("\n(f) attack: two visible password boxes (a sign-up form)")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/twopw"))
check("no password was pushed", all(p == "" for _, _, p in PUSHES),
      str(PUSHES))
H.click(view, "#go")
H.click(view, "#pw1")
H.key(view, Qt.Key.Key_Tab)
H.spin(400)
check("first password box stays empty", val("#pw1") == "", val("#pw1"))
check("second password box stays empty", val("#pw2") == "", val("#pw2"))
check("the username box is left alone too", val("#user") == "", val("#user"))

# =====================================================================
print("\n(g) a lone password box, no identifier anywhere (re-auth)")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/lonepw"))
check("empty before a gesture", val("#pw") == "")
gate_holds("#pw", "lone password box")
H.load(view, url("/lonepw"))
H.click(view, "#go")
check("fills on a real click (the login is this host's own)",
      val("#pw") == "hunter2", val("#pw"))

# =====================================================================
print("\n(h) a page whose only text box is a search box")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/searchy"))
check("the search box is not an identifier box", val("#q") == "", val("#q"))

# =====================================================================
print("\n(i) wrong-account correction: he types a different e-mail")
only(("127.0.0.1", "alt@example.com", "altpass"),
     ("127.0.0.1", "user@example.com", "hunter2"))    # this one is freshest
H.load(view, url("/nav/step1"))
# Two accounts are saved here, so nothing is filled at all any more:
# the account chooser asks first (tests/test_acctpick.py). He waves it
# away and types the account he wants, which is what this section is
# about — and the box he types into is empty rather than holding the
# freshest account, which is one step less work than it used to be.
check("nothing was filled, the chooser asked instead",
      val("#ap_email") == "" and br._acct_chooser is not None,
      "%r / %r" % (val("#ap_email"), br._acct_chooser))
br._acct_chooser.cancel()
H.spin(300)
check("dismissing it leaves the box empty",
      val("#ap_email") == "", val("#ap_email"))
H.click(view, "#ap_email")
QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
               Qt.KeyboardModifier.ControlModifier)
H.spin(150)
H.type_text(view, "alt@example.com")
H.spin(600)
check("the field now holds what he typed",
      val("#ap_email") == "alt@example.com", val("#ap_email"))
check("the browser remembered the account he typed",
      any(v["username"] == "alt@example.com" and v["typed"]
          for v in br._pw_steps.values()), str(br._pw_steps))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("step two uses the password of the account he typed",
      "password=altpass" in view.url().query(), view.url().toString())

print("\n(j) an account with no saved password: fill nothing")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/nav/step1"))
H.click(view, "#ap_email")
QTest.keyClick(view.focusProxy(), Qt.Key.Key_A,
               Qt.KeyboardModifier.ControlModifier)
H.spin(150)
H.type_text(view, "stranger@example.com")
H.spin(600)
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(300)
check("no password for an account we do not know",
      "hunter2" not in view.url().query(), view.url().toString())

# =====================================================================
print("\n(k) the half-finished login expires")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/nav/step1"))
check("remembered", bool(br._pw_steps))
for v in br._pw_steps.values():
    v["at"] -= B.PW_STEP_TTL + 1
br._pw_step_prune()
check("gone after the time limit", not br._pw_steps, str(br._pw_steps))

# =====================================================================
print("\n(l) a second virtual browser cannot see the first's step one")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/nav/step1"))
main_keys = list(br._pw_steps)
br.new_tab(url("/nav/step2"), session="work")
H.spin(1500)
v2 = br.current()
H.wait_for(lambda: v2.url().path() == "/nav/step2")
H.spin(900)
check("the other session did not inherit the half-login",
      all(k[:2] == main_keys[0][:2] for k in br._pw_steps),
      str(list(br._pw_steps)))
check("its tab and profile are a different key",
      br._pw_step_key(v2.page(), "127.0.0.1") != main_keys[0],
      str(br._pw_step_key(v2.page(), "127.0.0.1")))
check("but the watcher runs in that profile too",
      any(path == "/nav/step2" and p == "hunter2" for path, _, p in PUSHES),
      str(PUSHES))
H.click(v2, "#signin")
H.wait_for(lambda: v2.url().path() == "/done")
H.spin(400)
check("and it fills there on a real click",
      "password=hunter2" in v2.url().query(), v2.url().toString())

br.tabs.setCurrentWidget(view)          # back to the first tab
H.spin(400)

# =====================================================================
print("\n(m) saving: step two has no username box, but we know the account")
only(("127.0.0.1", "user@example.com", "hunter2"))
br._pw_pending = None
H.load(view, url("/nav/step1"))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#ap_password")          # typing disarms the filler
H.type_text(view, "newpass")
check("what he typed stands", val("#ap_password") == "newpass",
      val("#ap_password"))
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
p = br._pw_pending or {}
check("the update prompt names the right account",
      p.get("username") == "user@example.com" and p.get("password") == "newpass",
      str({k: v for k, v in p.items() if k != "password"}))
check("the half-finished login is cleared once it is over",
      not br._pw_steps, str(br._pw_steps))
br._pw_dismiss()

# =====================================================================
print("\n(n) D3: an identifier box is only filled where this is a sign-in")
only(("127.0.0.1", "user@example.com", "hunter2"))
H.load(view, url("/newsletter"))
check("a newsletter box is left alone", val("#nl") == "", val("#nl"))
check("and nothing was pushed at it", all(u == "" for _, u, _ in PUSHES),
      str(PUSHES))
del PUSHES[:]
H.load(view, url("/bare"))
check("a bare e-mail box on an ordinary page is left alone",
      val("#bare") == "", val("#bare"))
check("nothing was pushed at it either", all(u == "" for _, u, _ in PUSHES),
      str(PUSHES))
H.load(view, url("/account/login"))
check("but a sign-in the URL admits to is still filled",
      val("#ap_email") == "user@example.com", val("#ap_email"))

# =====================================================================
print("\n(o) D1: first, second and third visit to a two-step site")
only()                                   # nothing saved at all
br._pw_pending = None
H.load(view, url("/nav/step1"))
check("visit 1: nothing to prefill", val("#ap_email") == "", val("#ap_email"))
H.click(view, "#ap_email")
H.type_text(view, "user@example.com")
H.spin(500)
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#ap_password")
H.type_text(view, "hunter2")
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(500)
p = br._pw_pending or {}
check("visit 1: the save prompt names the account, not a blank",
      p.get("username") == "user@example.com", str(p.get("username")))
br._pw_save_pending()
check("visit 1: saved under a real username",
      [e["username"] for e in br.vault.logins()] == ["user@example.com"],
      str(br.vault.logins()))

H.load(view, url("/nav/step1"))
check("visit 2: the e-mail is prefilled", val("#ap_email") == "user@example.com",
      val("#ap_email"))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
check("visit 2: the password is filled and submitted",
      "password=hunter2" in view.url().query(), view.url().toString())

H.load(view, url("/nav/step1"))
H.click(view, "#next")
H.wait_for(lambda: view.url().path() == "/nav/step2")
H.spin(800)
H.click(view, "#signin")
H.wait_for(lambda: view.url().path() == "/done")
H.spin(400)
check("visit 3: still right, and still one entry",
      "password=hunter2" in view.url().query()
      and len(br.vault.logins()) == 1, view.url().toString())

print("\n(o2) an old blank-username entry is renamed, not duplicated")
only()
br.vault.set_entry("127.0.0.1", "http", "", "hunter2")   # the old bug
br.vault.set_entry("127.0.0.1", "http", "user@example.com", "hunter2")
check("one entry left, with the name",
      [e["username"] for e in br.vault.logins()] == ["user@example.com"],
      str(br.vault.logins()))

# =====================================================================
print("\n(p) D2: two tabs on one site do not share one memory")
only(("127.0.0.1", "alpha@example.com", "alphapass"),
     ("127.0.0.1", "beta@example.com", "betapass"))     # beta is freshest
tab_a = view
br.tabs.setCurrentWidget(tab_a)
H.load(tab_a, url("/nav/step1"))
H.click(tab_a, "#ap_email")
QTest.keyClick(tab_a.focusProxy(), Qt.Key.Key_A,
               Qt.KeyboardModifier.ControlModifier)
H.spin(150)
H.type_text(tab_a, "alpha@example.com")
H.spin(600)
check("tab A holds what he typed", H.js(tab_a,
      "document.querySelector('#ap_email').value") == "alpha@example.com")

br.new_tab(url("/nav/step1"))            # a second tab, same site
H.spin(1500)
tab_b = br.current()
H.wait_for(lambda: tab_b.url().path() == "/nav/step1")
H.spin(900)
# Two accounts are saved, so tab B guesses nothing either — but the
# point of this section is that tab B is a page of its own, and the
# sharpest form of that is a tab B holding *nothing* while tab A holds
# what he typed in it.
check("tab B was given nothing at all", H.js(tab_b,
      "document.querySelector('#ap_email').value") == "",
      H.js(tab_b, "document.querySelector('#ap_email').value"))
check("and tab A's half-login is still the only one", len(br._pw_steps) == 1,
      str(br._pw_steps))
# he answers tab B's chooser with the other account
check("tab B was asked which account", br._acct_chooser is not None)
H.press([b for b in br._acct_chooser.buttons
         if b.text() == "beta@example.com"][0])
H.spin(600)
check("tab B holds the account he picked in tab B", H.js(tab_b,
      "document.querySelector('#ap_email').value") == "beta@example.com",
      H.js(tab_b, "document.querySelector('#ap_email').value"))
check("two separate half-logins, one per tab", len(br._pw_steps) == 2,
      str(br._pw_steps))

br.tabs.setCurrentWidget(tab_a)
H.spin(400)
H.click(tab_a, "#next")
H.wait_for(lambda: tab_a.url().path() == "/nav/step2")
H.spin(800)
H.click(tab_a, "#signin")
H.wait_for(lambda: tab_a.url().path() == "/done")
H.spin(400)
check("tab A still submits the account he typed",
      "password=alphapass" in tab_a.url().query(), tab_a.url().toString())

br.tabs.setCurrentWidget(tab_b)
H.spin(400)
H.click(tab_b, "#next")
H.wait_for(lambda: tab_b.url().path() == "/nav/step2")
H.spin(800)
H.click(tab_b, "#signin")
H.wait_for(lambda: tab_b.url().path() == "/done")
H.spin(400)
check("tab B never saw tab A's typed account",
      "password=betapass" in tab_b.url().query(), tab_b.url().toString())

H.load(tab_b, url("/nav/step1"))     # tab B halfway through again
H.spin(500)
# and again it is his pick that puts it there, not a guess
H.wait_for(lambda: br._acct_chooser is not None, 6000)
H.press([b for b in br._acct_chooser.buttons
         if b.text() == "beta@example.com"][0])
H.spin(600)
before = len(br._pw_steps)
check("tab B is halfway through a login", before >= 1, str(br._pw_steps))
br.close_tab(br.tabs.indexOf(tab_b))
H.spin(1500)
check("closing a tab takes its half-login with it",
      len(br._pw_steps) < before, "%d -> %d" % (before, len(br._pw_steps)))
br.tabs.setCurrentWidget(tab_a)
H.spin(300)

srv.stop()
bad = [n for ok, n in RESULTS if not ok]
print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
for n in bad:
    print("  FAILED: " + n)
sys.exit(1 if bad else 0)
