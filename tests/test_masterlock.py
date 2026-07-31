"""A locked vault, against a real browser and a real login page.

test_master.py proves the passwords are not on the disk. This one
proves the browser behaves: nothing filled, nothing offered, nothing
said, and nothing put into a page at all — and that the unlock box is
a window of the browser's own which Esc dismisses without taking the
pane underneath with it.

Nothing here touches your data (see harness.boot).
"""
import json
import sys

import harness as H
import pages as PG
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QLabel

B = H.boot()
app = H.app()

srv = H.Server({})
H.Handler.pages = PG.pages("http://localhost:%d/hop/step2" % srv.port)

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

TOASTS = []
_orig_prompt = br._password_prompt


def _record_prompt(host, username, update):
    TOASTS.append((host, username, update))
    _orig_prompt(host, username, update)


br._password_prompt = _record_prompt


def check(name, cond, extra=""):
    RESULTS.append((bool(cond), name))
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % extra) if extra and not cond else ""))


def true_val(sel):
    """The value as the DOM really holds it, read in the isolated
    world where the page's own hooks do not exist."""
    return H.js(view, "(function(){var e=document.querySelector(%s);"
                      "return e?e.value:null;})()" % json.dumps(sel),
                B.PW_WORLD_ID)


def filled():
    """Load the one-page login, touch it the way a person would — the
    gesture gate means nothing reaches the DOM until he does — and say
    what ended up in the password box."""
    del PUSHES[:]
    H.load(view, srv.url("/both"))
    H.spin(300)
    H.click(view, "#pw")
    H.spin(300)
    return true_val("#pw")


PASS = "the long way in"


def seed():
    br.vault.rows().clear()
    br.vault.data["entries"] = []
    br._pw_steps.clear()
    br.vault.set_entry("127.0.0.1", "http", "user", "hunter2")
    br.vault._save()


# ---------------------------------------------------------------- 1
print("\nunlocked, the browser fills as it always did")
seed()
check("the password reached the field", filled() == "hunter2")
check("and the browser is what pushed it", any(p[2] for p in PUSHES), PUSHES)

# ---------------------------------------------------------------- 2
print("\nswitching a master password on")
check("none yet", br.vault_lock.enabled() is False)
check("enable", br.vault_lock.enable(PASS) is True)
br.vault = br.make_vault()
check("the browser says it is on", br.master_state()["on"] is True)
check("and open", br.vault_locked() is False)
check("the login is still there", br.vault.get("127.0.0.1", "user") is not None)
check("it still fills", filled() == "hunter2")

# ---------------------------------------------------------------- 3
print("\nlocked: nothing is filled and nothing is said")
br.lock_vault()
check("the browser is locked", br.vault_locked() is True)
check("the vault it holds is empty", len(br.vault.items()) == 0)
del TOASTS[:]
got = filled()
check("NOTHING was put into the page at all", PUSHES == [], PUSHES)
check("the password field is empty", not got, repr(got))
check("the username field is empty too", not true_val("#user"),
      repr(true_val("#user")))
check("no toast, no bar, no box on screen", br._toast is None)

# a site cannot tell a locked vault from an empty one: both say nothing
del PUSHES[:]
H.load(view, srv.url("/nav/step1"))
H.spin(400)
H.click(view, "#ap_email")
H.spin(300)
check("a two-step page is told nothing either", PUSHES == [], PUSHES)

# ---------------------------------------------------------------- 4
print("\nlocked: a submitted login is not offered for saving")
del TOASTS[:]
br._password_submitted(view.page(), {
    "host": "127.0.0.1", "username": "someone", "password": "typedbyhand"})
H.spin(200)
check("no save prompt", TOASTS == [], TOASTS)
check("nothing was written", br.vault.get("127.0.0.1", "someone") is None)
check("and no toast came up", br._toast is None)

# ---------------------------------------------------------------- 5
print("\nlocked: the manager lists nothing and every slot refuses")
bridge, key = br.bridge, br._page_key
v = json.loads(bridge.getVault(key))
check("getVault says locked", v.get("locked") is True)
check("and hands over no items", v.get("items") == [])
for name, call in (
        ("revealField", lambda: bridge.revealField(key, "any", "password")),
        ("copyField", lambda: bridge.copyField(key, "any", "password")),
        ("saveItem", lambda: bridge.saveItem(
            key, json.dumps({"type": "login", "host": "x"}))),
        ("deleteItem", lambda: bridge.deleteItem(key, "any")),
        ("toggleFavourite", lambda: bridge.toggleFavourite(key, "any")),
        ("totpFor", lambda: bridge.totpFor(key, "any")),
        ("copyTotpCode", lambda: bridge.copyTotpCode(key, "any")),
        ("exportPasswords", lambda: bridge.exportPasswords(key)),
        ("importPasswords", lambda: bridge.importPasswords(key)),
        ("removeNeverSiteKeyed",
         lambda: bridge.removeNeverSiteKeyed(key, "x.example"))):
    check("%s refuses" % name, call() == "{}")
summary = json.loads(bridge.passwordSummary())
check("the settings line says locked", summary.get("locked") is True)
check("and counts nothing", summary.get("total") == 0)
state = json.loads(bridge.masterState())
check("masterState reports it", state["on"] and state["locked"])
check("the generator still works while locked",
      len(bridge.generatePassword(key, 20, True, True, True, False)) == 20)
check("and the vault is still locked after all of that",
      br.vault_locked() is True)

# ---------------------------------------------------------------- 6
print("\nunlock, use it, let it lock itself, unlock again")
check("unlock", br.vault_lock.unlock(PASS) is True)
br.vault = br.make_vault()
check("the login is back", br.vault.get("127.0.0.1", "user") is not None)
check("and it fills again", filled() == "hunter2")

check("the default is fifteen minutes",
      B.MASTER_LOCK_DEFAULT == 15 and br.master_lock_minutes() == 15)
br.config[B.MASTER_LOCK_KEY] = 15
br.vault_lock.touch()
br._master_tick()
check("a vault just used is not locked", br.vault_locked() is False)
br.vault_lock._used -= 16 * 60          # sixteen minutes of nothing
br._master_tick()
check("sixteen minutes later it has shut itself", br.vault_locked() is True)
check("and the vault it holds is empty again", len(br.vault.items()) == 0)
check("so nothing fills any more", not filled())
check("and nothing was pushed", PUSHES == [], PUSHES)
check("unlock again", br.vault_lock.unlock(PASS) is True)
br.vault = br.make_vault()
check("and it fills once more", filled() == "hunter2")

print("\nusing the vault holds the clock back")
br.vault_lock._used -= 14 * 60          # fourteen minutes in
bridge.getVault(key)                    # ...and he opens the manager
br._master_tick()
check("opening the manager put the clock back",
      br.vault_locked() is False)
check("and the idle time really did reset", br.vault_lock.idle() < 60,
      br.vault_lock.idle())

print("\nnever is never")
br.config[B.MASTER_LOCK_KEY] = 0
br.vault_lock._used -= 10 * 60 * 60      # ten hours
br._master_tick()
check("0 minutes means it never shuts itself", br.vault_locked() is False)
br.config[B.MASTER_LOCK_KEY] = 15

# ---------------------------------------------------------------- 7
print("\nthe unlock box is a window, and Esc belongs to it")
br.open_pane("passwords")
H.spin(500)
check("a pane is up", br._pane is not None and br._pane.isVisible())
br.lock_vault()
dialog = B.MasterUnlockDialog(br, br._ui_str, br.vault_lock)
QTimer.singleShot(500, lambda: QTest.keyClick(
    app.activeWindow() or dialog, Qt.Key.Key_Escape))
rc = dialog.exec()
H.spin(500)
check("Esc closed the box", rc == QDialog.DialogCode.Rejected)
check("and the pane underneath is still up",
      br._pane is not None and br._pane.isVisible())
check("no Esc is left waiting on the pane", br._esc_timer is None)
check("and the vault is still locked", br.vault_locked() is True)

print("\nEsc with a pane, the account panel and the box all up")
# The one that made Esc a dead key before: two QShortcuts matching a
# key is not a race the newer one wins, Qt runs neither. The unlock box
# adds no shortcut at all -- it is a modal window, so the pane's
# WindowShortcut is not even active while it is up -- and this is the
# check that says so with all three on screen at once.
br.close_pane()
H.spin(200)
br.vault_lock.unlock(PASS)
br.vault = br.make_vault()
check("the vault is open for this", br.vault_locked() is False)
br.vault.set_entry("127.0.0.1", "http", "other", "secondpw")
br.vault._save()
H.load(view, srv.url("/both"))
H.spin(400)
names = br._account_names(view)
check("two accounts are saved for the page", len(names) == 2, names)
br.open_account_chooser()
H.spin(400)
check("the panel is up", br._acct_chooser is not None
      and br._acct_chooser.isVisible())
br.lock_vault()
H.spin(200)
check("locking took the panel away with it", br._acct_chooser is None)
check("and the handle left the address bar",
      br.acctbtn.isVisible() is False)
check("and the panel lists nothing now", br._account_names(view) == [],
      br._account_names(view))

br.open_pane("passwords")
H.spin(500)
check("a pane is up again", br._pane is not None and br._pane.isVisible())
box = B.MasterUnlockDialog(br, br._ui_str, br.vault_lock)
QTimer.singleShot(500, lambda: QTest.keyClick(
    app.activeWindow() or box, Qt.Key.Key_Escape))
rc = box.exec()
H.spin(400)
check("Esc closed the box and not the pane",
      rc == QDialog.DialogCode.Rejected and br._pane is not None
      and br._pane.isVisible())
check("Esc still works for the pane afterwards", br._esc_timer is None)
br.close_pane()
H.spin(300)
check("the unlock box registers no shortcut of its own",
      box.findChildren(type(br._pane_esc)) == [],
      box.findChildren(type(br._pane_esc)))

print("\nopening the manager asks too, and comes up either way")
check("locked to start with", br.vault_locked() is True)
asked = {"n": 0}
_plain_ask = br.ask_unlock_vault


def refusing_ask():
    asked["n"] += 1
    QTimer.singleShot(400, lambda: [d.reject() for d
                                    in br.findChildren(B.MasterUnlockDialog)])
    return _plain_ask()


br.ask_unlock_vault = refusing_ask
br.open_passwords()
H.spin(600)
check("Ctrl+Shift+P offered the box", asked["n"] == 1)
check("and the pane came up anyway, showing the locked screen",
      br._pane is not None and br._pane.isVisible())
check("with the vault still shut", br.vault_locked() is True)
br.ask_unlock_vault = _plain_ask
br.close_pane()
H.spin(300)

print("\nthe chooser's own shortcut asks to unlock, because he asked")
check("still locked", br.vault_locked() is True)
unlocked = {"n": 0}
_real_ask = br.ask_unlock_vault


def counting_ask():
    unlocked["n"] += 1
    # the box is modal and blocks; nobody is sitting here to press Esc,
    # so this test waves it away the way a person who changed his mind
    # would, and the point of the check is that it came up at all
    QTimer.singleShot(400, lambda: [d.reject() for d
                                    in br.findChildren(B.MasterUnlockDialog)])
    return _real_ask()


br.ask_unlock_vault = counting_ask
br.open_account_chooser()       # Ctrl+Shift+M with the vault shut
H.spin(300)
check("Ctrl+Shift+M offered the unlock box", unlocked["n"] == 1)
check("and nothing was listed, because it was cancelled",
      br._acct_chooser is None)
br.ask_unlock_vault = _real_ask
check("a PAGE still never causes a box", br.vault_locked() is True)
del PUSHES[:]
H.load(view, srv.url("/both"))
H.spin(500)
check("a login page with two accounts saved raises nothing",
      br._acct_chooser is None)
check("and pushes nothing", PUSHES == [], PUSHES)
check("no unlock box came up by itself", br._master_asking is False)
br.vault_lock.unlock(PASS)
br.vault = br.make_vault()
br.vault.delete_item(br.vault.get("127.0.0.1", "other")["id"])
br.vault._save()
br._acct_auto.clear()
H.spin(100)

print("\nthe box says no to a wrong passphrase without closing")
br.lock_vault()
dialog = B.MasterUnlockDialog(br, br._ui_str, br.vault_lock)
dialog.show()
H.spin(150)
dialog._fields["pass"].setText("not the passphrase")
dialog._try()
H.spin(100)
check("it stayed open", dialog.isVisible())
check("it said so", dialog._note.text() == br._ui_str("masterWrong"),
      dialog._note.text())
check("it emptied the box", dialog.value("pass") == "")
check("and the vault is still locked", br.vault_locked() is True)
dialog._fields["pass"].setText(PASS)
dialog._try()
H.spin(100)
check("the right one closes it",
      dialog.result() == QDialog.DialogCode.Accepted)
check("and the vault is open", br.vault_lock.locked() is False)
br.vault = br.make_vault()
br.close_pane()
H.spin(300)

# ---------------------------------------------------------------- 8
print("\nthe setup box refuses what it should, and warns first")
dlg = B.MasterSetupDialog(br, br._ui_str, lambda: None)
dlg.show()
H.spin(120)
labels = [w.text() for w in dlg.findChildren(QLabel)]
check("the forgotten-passphrase warning is on the box itself",
      br._ui_str("masterWarnT") in labels, labels)
check("and so is what it means",
      any(br._ui_str("masterWarnB") == t for t in labels))
check("there is an export button on it",
      any(b.text() == br._ui_str("masterExportFirst")
          for b in dlg.findChildren(type(dlg._ok))))
check("the go button starts off", dlg._ok.isEnabled() is False)
check("there are two boxes, not one", len(dlg._fields) == 2)
check("and neither shows what is typed",
      all(f.echoMode() == f.EchoMode.Password
          for f in dlg._fields.values()))
dlg._fields["first"].setText("short")
dlg._fields["again"].setText("short")
H.spin(50)
check("too short is refused", dlg._ok.isEnabled() is False)
check("and says why", dlg._note.text() == br._ui_str("masterShort"))
dlg._fields["first"].setText("a long enough one")
dlg._fields["again"].setText("a long enough onf")
H.spin(50)
check("a mistyped second box is refused", dlg._ok.isEnabled() is False)
check("and says why", dlg._note.text() == br._ui_str("masterMismatch"))
dlg._fields["again"].setText("a long enough one")
H.spin(50)
check("two matching long ones are accepted", dlg._ok.isEnabled() is True)
dlg.reject()

# ---------------------------------------------------------------- 9
print("\nswitching it off puts everything back")
check("unlocked first", br.vault_locked() is False)
check("disable", br.vault_lock.disable() is True)
br.vault = br.make_vault()
check("off", br.master_state()["on"] is False)
check("the login survived", br.vault.get("127.0.0.1", "user") is not None)
check("and autofill is exactly what it was", filled() == "hunter2")
br.toggle_vault_lock()
check("Ctrl+Shift+L does nothing with no master password set",
      br.vault_locked() is False)
check("the save prompt works again too", br.bridge.passwordSummary() != "{}")

# --------------------------------------------------------------- 10
print("\na private tab is unaffected, locked or not")
# Two independent refusals that happen to point the same way. A private
# tab never fills and never saves whatever the vault is doing, and a
# locked vault never fills and never saves whatever the tab is. Neither
# is doing the other's job, so both are checked.
# the section above took the master password off again, so put one back:
# half of what follows is about a vault that is shut
if not br.vault_lock.enabled():
    check("a master password to shut", br.vault_lock.enable(PASS) is True)
    br.vault = br.make_vault()
check("the vault is open for this", br.vault_locked() is False)
priv = br.new_tab(url=srv.url("/both"), private=True)
H.spin(1200)
check("the tab really is private", br._page_is_private(priv.page()) is True)
del PUSHES[:]
H.click(priv, "#pw")
H.spin(400)
check("nothing was pushed into a private tab with the vault OPEN",
      PUSHES == [], PUSHES)
del TOASTS[:]
br._password_submitted(priv.page(), {
    "host": "127.0.0.1", "username": "someone", "password": "typedbyhand"})
H.spin(200)
check("and a private login is never offered for saving", TOASTS == [], TOASTS)
br.lock_vault()
del PUSHES[:]
H.load(priv, srv.url("/both"))
H.spin(400)
H.click(priv, "#pw")
H.spin(300)
check("still nothing with the vault LOCKED too", PUSHES == [], PUSHES)
check("and the vault is still shut", br.vault_locked() is True)
br.vault_lock.unlock(PASS)
br.vault = br.make_vault()
idx = br.tabs.indexOf(priv)
if idx >= 0:
    br.tabs.removeTab(idx)
H.spin(300)
view = br.current()

print("\nVault Password off means the whole thing is inert")
br.config["vaultPassword"] = False
check("nothing can be locked", br.vault_locked() is False)
del TOASTS[:]
check("nothing fills", not filled())
check("nothing was pushed", PUSHES == [], PUSHES)
check("passwordSummary says nothing", br.bridge.passwordSummary() == "{}")
br.config["vaultPassword"] = True

print()
bad = [n for ok, n in RESULTS if not ok]
print("%d checks, %d failed" % (len(RESULTS), len(bad)))
if bad:
    print("FAILED: " + ", ".join(bad))
else:
    print("all green")
srv.stop()
sys.exit(1 if bad else 0)
