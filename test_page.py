#!/usr/bin/env python3
"""The passwords page driven for real, and the clipboard read
afterwards — because the only way to know what "Copy code" copies is
to look at what ends up there.

Covers, in the browser rather than in a docstring:

  * S1: the button labelled "Copy code" puts the six digits on the
    clipboard, and never the two-factor seed
  * a page holding a key from an earlier run says so instead of
    rendering nothing at all
  * a reveal that failed does not read as "this account has no
    password"

Offscreen, against a scratch vault. Your own is never opened.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

SEED = "JBSWY3DPEHPK3PXP"
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "vaultPassword": True}))

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1280, 900)
win.show()

win.vault.add_item({"type": "login", "title": "GitHub", "host": "github.com",
                    "username": "user", "password": "file-side-secret",
                    "totp": SEED})
win.open_passwords()
# the manager is a pane over the current tab, not a tab of its own:
# win.current() is whatever he was looking at before
view = win._panes["passwords"].view
results = {}


def js(code, then):
    view.page().runJavaScript(code, B.MAIN_WORLD_ID, then)


def step_open():
    js("[...document.querySelectorAll('.row')]"
       ".find(r => r.textContent.includes('GitHub')).click();"
       "document.querySelectorAll('.row').length",
       lambda n: (results.__setitem__("rows", n),
                  QTimer.singleShot(1500, step_code)))


def step_code():
    js("(document.querySelector('.totp .code')||{}).textContent||''",
       got_code)


def got_code(text):
    print("\nS1: what “Copy code” actually copies")
    digits = "".join(c for c in text if c.isdigit())
    results["onscreen"] = digits
    check("a six-digit code is on screen", len(digits) == 6, repr(text))
    QGuiApplication.clipboard().setText("CLIPBOARD-UNTOUCHED")
    js("(function(){"
       " const b=[...document.querySelectorAll('button')]"
       "  .find(x=>x.textContent==='Copy code');"
       " if (b) b.click(); return !!b; })()",
       lambda ok: (results.__setitem__("clicked", ok),
                   QTimer.singleShot(1500, read_clipboard)))


def read_clipboard():
    got = QGuiApplication.clipboard().text()
    check("the button is there and was clicked", results.get("clicked"))
    at = time.time()
    live = {results["onscreen"], B.totp_code(SEED, at=at),
            B.totp_code(SEED, at=at - 30)}
    check("the clipboard holds a live code, not the placeholder",
          got in live and got.isdigit() and len(got) == 6,
          (repr(got), live))
    check("and NOT the two-factor seed", SEED not in got, repr(got))
    check("the seed is not on the clipboard in any shape",
          SEED.lower() not in got.lower(), repr(got))
    QTimer.singleShot(200, step_reveal_fail)


def step_reveal_fail():
    """The ordinary reveal path, to prove the honest-reply rewrite did
    not break the case that always worked."""
    js("(function(){"
       " const rows=[...document.querySelectorAll('.field')];"
       " const r=rows.find(f=>f.querySelector('label') &&"
       "   f.querySelector('label').textContent==='Password');"
       " const b=[...r.querySelectorAll('button')]"
       "   .find(x=>x.textContent==='Reveal');"
       " b.click(); b.click(); return !!b; })()",
       lambda _: QTimer.singleShot(1500, revealed))


def revealed():
    js("[...document.querySelectorAll('.field')].map(f=>f.textContent)"
       ".join('|')", got_revealed)


def got_revealed(text):
    print("\na reveal that worked still works")
    check("the password arrived", "file-side-secret" in text, text[:200])
    check("and it is not the placeholder dash",
          "Could not get" not in text and "Nothing is stored" not in text)
    QTimer.singleShot(200, step_edit)


NAME_BOX = """(function(){
  const f = [...document.querySelectorAll('.field')].find(
    x => x.querySelector('label')
         && x.querySelector('label').textContent === 'Name');
  return f ? f.querySelector('input') : null; })()"""


def step_edit():
    """D2: a store swapping in — or any vaultChanged at all — used to
    rebuild every box in the editor from the snapshot taken when Edit
    was pressed, throwing away everything typed since."""
    print("\na redraw arriving while he is typing")
    js("(function(){ const b=document.getElementById('editbtn');"
       " if (b) b.click(); return !!b; })()",
       lambda ok: (check("the editor opened", bool(ok)),
                   QTimer.singleShot(900, type_into_editor)))


def type_into_editor():
    js("(function(){ const i = " + NAME_BOX + ";"
       " if (!i) return 'NO NAME BOX';"
       " i.value = 'TYPED BUT NOT SAVED';"
       " i.dispatchEvent(new Event('input'));"
       " return i.value; })()", typed)


def typed(value):
    check("there is a Name box to type in", value == "TYPED BUT NOT SAVED",
          value)
    win.bridge.vaultChanged.emit()      # exactly what an adoption fires
    QTimer.singleShot(1400, read_editor)


def read_editor():
    js("(function(){ const i = " + NAME_BOX + ";"
       " const save = [...document.querySelectorAll('button')]"
       "   .find(b => b.textContent === 'Save');"
       " return JSON.stringify({open: !!save,"
       "   value: i ? i.value : null}); })()", editor_read)


def editor_read(raw):
    d = json.loads(raw)
    check("the editor is still open", d["open"], d)
    check("and what was typed is still in the box",
          d["value"] == "TYPED BUT NOT SAVED", d)
    js("(function(){ const b=[...document.querySelectorAll('button')]"
       "  .find(x=>x.textContent==='Cancel'); if (b) b.click();"
       " return !!b; })()",
       lambda _: QTimer.singleShot(1200, after_cancel))


def after_cancel():
    js("JSON.stringify({edit: !![...document.querySelectorAll('button')]"
       "  .find(b=>b.textContent==='Edit'),"
       " typed: document.body.textContent.includes('TYPED BUT NOT SAVED')})",
       cancelled)


def cancelled(raw):
    d = json.loads(raw)
    check("closing it lets the page catch up", d["edit"], d)
    check("and nothing typed was ever saved", not d["typed"], d)
    QTimer.singleShot(200, step_export_row)


def step_export_row():
    print("\nthe file vault can be exported, and says how it keeps things")
    js("JSON.stringify({off: document.getElementById('exportbtn').disabled,"
       " where: document.getElementById('where').textContent})", got_export)


def got_export(raw):
    d = json.loads(raw)
    check("Export is offered by the store that can fill it", d["off"] is False,
          d)
    check("and the line describing that store is there",
          len(d["where"]) > 10, d)
    QTimer.singleShot(200, step_store_note)


def step_store_note():
    print("\nthe store line while a store is being reached for")
    js("(function(){ VAULT.checking='1password'; render();"
       " const t=document.getElementById('store').textContent;"
       " VAULT.checking=''; render(); return t; })()", got_store_note)


def got_store_note(text):
    check("it names the store it is waiting on",
          "Reaching for 1Password" in (text or ""), repr(text))
    check("and does not run two ellipses together",
          "\u2026\u2026" not in (text or "").replace(" ", ""), repr(text))
    QTimer.singleShot(200, step_settings)


def step_settings():
    """The section main restyled, with our content in it."""
    print("\nthe Passwords section in Settings")
    win.open_settings()
    QTimer.singleShot(3000, read_settings)


def read_settings():
    win._panes["settings"].view.page().runJavaScript("""JSON.stringify({
      summary: document.getElementById('pwsummary').textContent,
      hint: getComputedStyle(document.getElementById('t_pwHint')).display,
      open: !!document.getElementById('pwopen'),
      savePw: !!document.getElementById('savepasswords'),
      leftovers: ['pwlist','pwnever','pwsite','pwuser','pwpass','pwsavebtn']
                 .filter(i => document.getElementById(i)),
      rail: [...document.querySelectorAll('#sidebar button')]
        .filter(b => (b.dataset.hay||'').includes('password'))
        .map(b => b.textContent.trim())
    })""", B.MAIN_WORLD_ID, got_settings)


def got_settings(raw):
    d = json.loads(raw)
    check("the summary names the store and counts what is in it",
          "This computer" in d["summary"] and "1 Logins" in d["summary"],
          d["summary"])
    check("the way in to the manager is there", d["open"], d)
    check("so is the privacy switch, which is not part of the manager",
          d["savePw"], d)
    check("nothing is left of the inline manager", d["leftovers"] == [],
          d["leftovers"])
    check("the file vault's own line is shown for the file vault",
          d["hint"] != "none", d["hint"])
    # main's rail indexes section text, and it only reindexes if
    # whatever painted the section said so. Plugins answers to
    # "password" too now — Vault Password is switched on and off there,
    # so someone searching the rail for it should land on both.
    check("the rail can still find the section by what it says",
          "Passwords" in d["rail"], d["rail"])
    check("and Plugins, where the feature is switched on",
          "Plugins" in d["rail"], d["rail"])
    win.close_settings()
    QTimer.singleShot(400, step_denied)


def step_denied():
    """A key from an earlier run of the browser."""
    print("\na page holding a stale key")
    url = view.url().toString().split("?")[0] + "?k=" + "0" * 32
    view.load(B.QUrl(url))
    QTimer.singleShot(3500, denied_check)


def denied_check():
    js("document.body.textContent", got_denied)


def got_denied(text):
    check("the page is not blank", len((text or "").strip()) > 40,
          repr((text or "")[:120]))
    check("it says the page is out of date",
          "out of date" in (text or ""), (text or "")[:200])
    check("and says what to do about it",
          "menu" in (text or ""), (text or "")[:200])
    print("\n%d checks failed" % len(fails))
    for f in fails:
        print("  - " + f)
    app.exit(1 if fails else 0)


QTimer.singleShot(3500, step_open)
QTimer.singleShot(45000, lambda: (print("TIMED OUT"), app.exit(1)))
sys.exit(app.exec())
