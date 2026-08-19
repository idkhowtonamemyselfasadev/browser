#!/usr/bin/env python3
"""The library-update offer must never trample another prompt.

Two defects, both security-adjacent, both fixed here:

 D1  A pkexec library upgrade can run for a long time. If, while it runs,
     a login form is submitted, the password-save prompt takes the toast
     slot. When the upgrade finished it rewrote WHATEVER toast was on
     screen -- so it rewrote the password prompt's label and buttons and
     stopped its 15-second self-destruct, which strands the plaintext
     password (_pw_pending) that timer was meant to clear, and turns its
     Save button into a Restart. _lib_upgrade_done now captures the toast
     it belongs to and touches nothing unless that exact toast is still up.

 D2  _toast_result is wired to updateFinished, which the browser's own
     git updater AND the plugin installer both emit. A finishing plugin
     install would overwrite the library offer and re-arm its timer to
     dismiss+stamp it, silently losing the offer for two days. The offer
     is now marked (property "libOffer") and _toast_result leaves it be.

Offscreen, scratch data. No dnf, no pkexec, no pip: _lib_run is replaced
so no real process is ever started.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()
app.processEvents()

# ---------------------------------------------------------------------
print("(1) D1: a finishing upgrade does not hijack the password prompt")
# the offer is up and he presses Update, but _lib_run is captured rather
# than run, so we hold the finished-callback and fire it when we choose
captured = {}
win._lib_run = lambda program, args, done: captured.update(done=done)
win._show_lib_toast()
check("the library offer is showing",
      win._toast is not None and win._toast.property("libOffer") is True)
win._lib_update_now()
check("pressing Update captured the finish callback", "done" in captured)

# now, mid-upgrade, a login form is submitted: the password prompt preempts
win._pw_pending = {"host": "bank.example", "scheme": "https",
                   "username": "user", "password": "s3cret"}
win._password_prompt("bank.example", "user", False)
pw_toast = win._toast
pw_label = win._toast_label.text()
pw_timer = win._toast_timer
check("the password prompt now owns the toast slot",
      pw_toast is not None and not pw_toast.property("libOffer"))
check("its 15s self-destruct is running", pw_timer.isActive())

# the upgrade finishes late, reporting success
win._lib_upgrade_done(0, "", None)   # emulate a stray fire without a token
# and the real captured callback (which carries the lib toast token):
captured["done"](0, "")

check("D1a the password prompt is still the toast on screen",
      win._toast is pw_toast, win._toast)
check("D1b its label was NOT rewritten to the upgrade result",
      win._toast_label.text() == pw_label, win._toast_label.text())
check("D1c its self-destruct timer was NOT stopped",
      pw_timer.isActive())
check("D1d the pending plaintext password was NOT stranded/cleared by it",
      win._pw_pending is not None
      and win._pw_pending.get("password") == "s3cret", win._pw_pending)

# clean up the password prompt state
win._pw_dismiss()
app.processEvents()

# ---------------------------------------------------------------------
print("\n(2) D2: a plugin install finishing does not overwrite the offer")
win._show_lib_toast()
offer = win._toast
offer_label = win._toast_label.text()
check("the offer is up again", offer is not None
      and offer.property("libOffer") is True)
# the plugin installer emits updateFinished -> _toast_result
win.bridge.updateFinished.emit("Plugin installed: something")
app.processEvents()
check("D2a the offer is still the toast on screen", win._toast is offer,
      win._toast)
check("D2b its label was not overwritten by the plugin message",
      win._toast_label.text() == offer_label, win._toast_label.text())
check("D2c it is still marked as the library offer",
      win._toast.property("libOffer") is True)
win._lib_dismiss()
app.processEvents()

# ---------------------------------------------------------------------
print("\n(3) _toast_result still works for a normal (non-offer) toast")
win._show_toast()      # the browser's own git-update toast: no libOffer
check("a plain update toast is not marked as the library offer",
      win._toast is not None and not win._toast.property("libOffer"))
win._toast_result("Updated to abc123")
check("its label updates as before",
      win._toast_label.text() == "Updated to abc123", win._toast_label.text())
win._hide_toast()

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
