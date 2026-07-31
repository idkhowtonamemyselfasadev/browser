#!/usr/bin/env python3
"""Open the passwords page in a real (offscreen) browser against a
scratch vault and photograph it. Never touches your own data."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/passwords.png")

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1280, 900)
win.show()

v = win.vault
now = int(time.time())
v.add_item({"type": "login", "host": "github.com", "username": "user",
            "password": "Xk7#mQp2$vLz9Rt4", "title": "GitHub",
            "tags": ["work", "dev"], "fav": True,
            "totp": "otpauth://totp/GitHub:user?secret=JBSWY3DPEHPK3PXP"
                    "&issuer=GitHub"})
v.add_item({"type": "login", "host": "amazon.de", "username": "user@example.com",
            "password": "sommer2019", "title": "Amazon", "tags": ["shopping"]})
v.add_item({"type": "login", "host": "ebay.de", "username": "user",
            "password": "sommer2019", "title": "eBay", "tags": ["shopping"]})
v.add_item({"type": "login", "host": "bank.example", "username": "10023455",
            "password": "abc", "title": "Bank"})
old = v.add_item({"type": "login", "host": "forum.old.net", "username": "user",
                  "password": "Zq3!wRt8&yUi0pAs", "title": "Old forum"})
old["changed"] = now - 500 * 86400
v.add_item({"type": "note", "title": "WLAN at home",
            "body": "SSID Fritzbox7590\nkey: correct-horse-battery",
            "tags": ["home"]})
v.add_item({"type": "card", "title": "Girocard", "cardholder": "A. User",
            "number": "4111111111111111", "expiry": "12/28", "cvv": "123",
            "brand": "Visa", "tags": ["banking"]})
v.add_item({"type": "identity", "title": "Home address", "fullname": "A. User",
            "email": "user@example.com", "city": "Berlin", "zip": "10115",
            "street": "Musterstr. 1", "country": "Germany"})
v.never("tracker.example")
v._save()

win.open_passwords()
view = win.current()

steps = []


def shoot(name, js=None, then_ms=900):
    def run():
        if js:
            view.page().runJavaScript(js, B.MAIN_WORLD_ID)
        QTimer.singleShot(then_ms, lambda: grab(name))
    return run


def grab(name):
    path = OUT.with_name(OUT.stem + "-" + name + OUT.suffix)
    view.grab().save(str(path))
    print("shot", path)
    nxt()


def nxt():
    if steps:
        steps.pop(0)()
    else:
        QTimer.singleShot(200, app.quit)


def report():
    view.page().runJavaScript(
        "JSON.stringify({items: VAULT.items.length,"
        " rows: document.querySelectorAll('.row').length,"
        " health: VAULT.health.totals,"
        " leaked: JSON.stringify(VAULT.items).includes('Xk7#mQp2')"
        "   || JSON.stringify(VAULT.items).includes('4111111111111111')"
        "   || JSON.stringify(VAULT.items).includes('correct-horse'),"
        " title: document.title})",
        B.MAIN_WORLD_ID, lambda r: (print("PAGE:", r), nxt()))


steps = [
    shoot("list"),
    lambda: report(),
    shoot("detail", "document.querySelectorAll('.row')[0].click()"),
    shoot("edit", "document.getElementById('editbtn').click()"),
    shoot("gen", "document.getElementById('genbtn').click()"),
    shoot("note", "editing=null;"
                  "[...document.querySelectorAll('.row')]"
                  ".find(r=>r.textContent.includes('WLAN')).click()"),
]
QTimer.singleShot(2500, nxt)
app.exec()
