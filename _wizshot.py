#!/usr/bin/env python3
"""Photograph the master password's own page in the setup wizard:
untouched, switched on with the fields empty, mid-entry, with the two
boxes disagreeing, and the summary — in English and in German.

Against a scratch profile. Never goes near your own data — see _boot.

    python3 _wizshot.py [outdir]
"""
import json
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
win.resize(1180, 860)
win.show()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def value(code, wait=2500):
    box = {}
    loop = QEventLoop()

    def got(v):
        box["v"] = v
        loop.quit()
    view.page().runJavaScript(code, got)
    QTimer.singleShot(wait, loop.quit)
    loop.exec()
    return box.get("v")


def js(code, wait=350):
    view.page().runJavaScript(code)
    spin(wait)


spin(400)
view = win.current()
view.setFocus()

TYPE = """(function(){var A=document.getElementById('wizmasterA'),
  Bx=document.getElementById('wizmasterB');
  if(!A||!Bx)return;A.value=%s;A.oninput();Bx.value=%s;Bx.oninput();})()"""


def shoot(name):
    win.grab().save(str(OUT / name))
    print(OUT / name)


for lang, tag in (("en", ""), ("de", "-de")):
    # Leaving the wizard applies what was typed, so the first language
    # really does set one. Take it off again, or the second language
    # photographs the "you already have one" row instead of the offer.
    if win.vault_lock.enabled() and not win.vault_lock.locked():
        win.vault_lock.disable()
        win.vault = win.make_vault()
    assert not win.vault_lock.enabled(), "left a master password behind"
    win.config["translateLang"] = lang
    win.save_config()
    nav = win._ui_str("wizNavMaster")
    master = win._ui_str("wizMasterT")

    view.load(B.START_PAGE)
    spin(3200)
    js("putVal('vaultPassword', true); openWiz(0)", 600)
    at = value("(function(){var p=wizPages();for(var i=0;i<p.length;i++){"
               "if(p[i].nav===%s)return i;}return -1;})()" % json.dumps(nav))
    assert at is not None and at >= 0, "no master page in %s" % lang
    js("gotoWiz(%d)" % at, 700)

    shoot("wizard-master-page%s.png" % tag)

    toggle = ("(function(){var r=[].slice.call("
              "document.querySelectorAll('.wrow')).filter(function(e){"
              "var n=e.querySelector('.wname');"
              "return n && n.textContent===%s;})[0];if(r)r.onclick();})()"
              % json.dumps(master))
    js(toggle, 600)
    shoot("wizard-master-on%s.png" % tag)

    js(TYPE % (json.dumps("goldfish harbour"), json.dumps("goldfish har")), 450)
    shoot("wizard-master-mismatch%s.png" % tag)

    js(TYPE % (json.dumps("goldfish harbour pencil"),
               json.dumps("goldfish harbour pencil")), 450)
    shoot("wizard-master-set%s.png" % tag)

    js("gotoWiz(wizPages().length - 1)", 1000)
    shoot("wizard-master-summary%s.png" % tag)

    js("leaveWiz()", 700)
