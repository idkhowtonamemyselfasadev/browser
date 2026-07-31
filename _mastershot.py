#!/usr/bin/env python3
"""Photograph the master password: the box that switches it on and
what it warns, the unlock box, and Settings with it switched on.

Against a scratch vault with invented logins. Never goes near your
own data — see _boot.

    python3 _mastershot.py [outdir]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1180, 800)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


spin(300)
win.vault.set_entry("outlook.com", "https", "a.person@outlook.com", "aaaa")
win.vault.set_entry("bank.de", "https", "aperson", "bbbb")
win.vault.add_item({"type": "note", "title": "Recovery codes",
                    "note": "11111-22222"})
win.vault._save()

# ---- 1. the box that switches it on, warning and all ----
setup = B.MasterSetupDialog(win, win._ui_str, lambda: None)
setup.show()
spin(500)
setup.grab().save(str(OUT / "master-setup.png"))
print(OUT / "master-setup.png")
setup.reject()
spin(200)

# ---- 2. the same box with a passphrase in it, ready to go ----
setup2 = B.MasterSetupDialog(win, win._ui_str, lambda: None)
setup2.show()
setup2._fields["first"].setText("goldfish harbour pencil")
setup2._fields["again"].setText("goldfish harbour")
spin(400)
setup2.grab().save(str(OUT / "master-setup-mismatch.png"))
print(OUT / "master-setup-mismatch.png")
setup2.reject()
spin(200)

# ---- 3. the unlock box, over the window, having been told no once ----
assert win.vault_lock.enable("goldfish harbour pencil")
win.vault = win.make_vault()
win.lock_vault()
unlock = B.MasterUnlockDialog(win, win._ui_str, win.vault_lock)
unlock.show()
spin(300)
unlock._fields["pass"].setText("goldfish harbor pencil")
unlock._try()          # a near miss, so the box is shown saying so
spin(300)
unlock.grab().save(str(OUT / "master-unlock.png"))
print(OUT / "master-unlock.png")
unlock.reject()
spin(200)

# ---- 4. Settings, with it switched on ----
assert win.vault_lock.unlock("goldfish harbour pencil")
win.vault = win.make_vault()
win.open_pane("settings")
spin(3500)
pane = win._panes["settings"]
# Settings shows one section at a time off the rail, so scrolling to
# the Passwords section is not enough — its rail button is the one that
# has to be pressed.
pane.view.page().runJavaScript(
    "(function(){var b=[].slice.call("
    "document.querySelectorAll('#sidebar button')).filter("
    "function(x){return x._sec && x._sec.dataset.desc==='descPasswords';});"
    "if(b.length){b[0].click();return 'clicked';}return 'not found';})()",
    lambda r: print("   rail:", r))
spin(1500)
pane.view.page().runJavaScript(
    "(function(){var s=document.getElementById('masterpw');"
    "if(!s)return 'no switch';"
    "s.closest('.panel').scrollIntoView({block:'center'});"
    "return 'scrolled';})()", lambda r: print("   scroll:", r))
spin(1200)
win.grab().save(str(OUT / "master-settings.png"))
print(OUT / "master-settings.png")

# ---- 5. the manager, locked ----
win.close_pane()
spin(300)
win.lock_vault()
win.open_pane("passwords")
spin(3500)
win.grab().save(str(OUT / "master-locked-manager.png"))
print(OUT / "master-locked-manager.png")
