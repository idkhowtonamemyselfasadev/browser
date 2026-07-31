#!/usr/bin/env python3
"""The whole path, end to end: the real browser, the real passwords
page, the real provider code — with the mock `op` standing in for the
binary that is not installed here.

Proves that with 1Password selected the page lists what op reports,
reveals a secret through the asynchronous path, shows a code op
produced, and that pulling op away mid-session degrades honestly."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

BIN = SCRATCH / "bin"
BIN.mkdir(parents=True, exist_ok=True)
shutil.copy(HERE / "tools" / "mock-op", BIN / "op")
os.chmod(BIN / "op", 0o755)
os.environ["PATH"] = str(BIN) + os.pathsep + os.environ["PATH"]
os.environ["MOCK_OP_STORE"] = str(SCRATCH / "op-store.json")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# a vault that already has things in it, as the father's would
seed = B.OnePasswordProvider(SCRATCH, vault_name="Browser")
seed.write_token("mock-service-account-token")
Path(os.environ["MOCK_OP_STORE"]).write_text(json.dumps({"items": []}))
seed.put({"type": "login", "title": "GitHub", "host": "github.com",
          "scheme": "https", "username": "user", "password": "op-side-secret",
          "totp": "JBSWY3DPEHPK3PXP", "tags": ["work"]})
seed.put({"type": "login", "title": "Bank", "host": "bank.example",
          "scheme": "https", "username": "10023455", "password": "another"})
seed.put({"type": "note", "title": "Recovery codes",
          "body": "1111-2222 3333-4444"})
seed.put({"type": "card", "title": "Girocard", "cardholder": "A. User",
          "number": "4111111111111111", "expiry": "12/28", "cvv": "123"})

B.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"passwordProvider": "1password",
                                     "opVault": "Browser", "translateLang": "en",
                                     "vaultPassword": True}))
# the seed provider already wrote the token into CONFIG_FILE.parent

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
started = time.time()
win = B.Browser()
boot = time.time() - started
win.resize(1280, 900)
win.show()


def pump(until, limit=30.0):
    """Turn the event loop by hand until something has happened. The
    store is reached for on a worker thread now, so nothing about it
    is true the instant Browser() returns."""
    end = time.time() + limit
    while time.time() < end and not until():
        app.processEvents()
        time.sleep(0.02)
    return until()


print("\nstartup with 1Password selected")
check("the window did not wait for op to answer", boot < 2.0, "%.1fs" % boot)
check("it starts on the file vault and says so",
      win.vault_checking == "1password", win.vault_checking)
check("provider is 1password once op has answered",
      pump(lambda: win.vault.provider.name == "1password"),
      win.vault.provider.name)
check("no fallback happened", win.vault_fell_back == "", win.vault_fell_back)
check("it listed what op has", len(win.vault.items()) == 4,
      len(win.vault.items()))
check("the token is not in config.json",
      "mock-service-account-token" not in B.CONFIG_FILE.read_text())
check("the token is in its own 0600 file",
      oct((B.CONFIG_FILE.parent / B.OP_TOKEN_FILE).stat().st_mode)[-3:]
      == "600")

blob = win.bridge.getVault(win._page_key)
check("no op-side secret in what the page gets",
      "op-side-secret" not in blob and "4111111111111111" not in blob
      and "1111-2222" not in blob)
check("the page is told the store cannot do health",
      json.loads(blob)["health"].get("unavailable") is True)
check("the page is told which store this is",
      json.loads(blob)["provider"] == "1password")

win.open_passwords()
# the manager is a pane over the current tab, not a tab of its own:
# win.current() is whatever he was looking at before
view = win._panes["passwords"].view
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/op.png")
steps = []


def shot(name):
    path = OUT.with_name(OUT.stem + "-" + name + OUT.suffix)
    view.grab().save(str(path))
    print("  shot", path)


def js(code, then):
    view.page().runJavaScript(code, B.MAIN_WORLD_ID, then)


def step_list():
    shot("list")
    js("JSON.stringify({rows: document.querySelectorAll('.row').length,"
       " store: document.querySelector('.storebar b').textContent,"
       " health: document.querySelector('.hchip').textContent})", got_list)


def got_list(raw):
    d = json.loads(raw)
    print("\nthe page against 1Password")
    check("every item is listed", d["rows"] == 4, d)
    check("the store is named on the page", "1Password" in d["store"],
          d["store"])
    check("health says honestly that it cannot run",
          "hand" in d["health"] or "gibt sie nicht" in d["health"], d["health"])
    js("[...document.querySelectorAll('.row')]"
       ".find(r => r.textContent.includes('GitHub')).click();"
       "document.querySelectorAll('.field .acts button').length", lambda _:
       QTimer.singleShot(1200, step_reveal))


def step_reveal():
    shot("detail")
    # two clicks: the reveal button arms itself first (see `armed`)
    js("(function(){"
       " const b=[...document.querySelectorAll('button')]"
       "  .find(x=>x.textContent==='Reveal');"
       " b.click(); b.click(); return !!b; })()",
       lambda _: QTimer.singleShot(2500, step_revealed))


def step_revealed():
    js("[...document.querySelectorAll('.field')]"
       ".map(f=>f.textContent).join('|')", got_revealed)


def got_revealed(text):
    print("\nfetching a secret through the asynchronous path")
    check("the password op holds arrived in the page",
          "op-side-secret" in text, text[:200])
    shot("revealed")
    js("(document.querySelector('.totp .code')||{}).textContent || ''",
       got_totp)


def got_totp(code):
    digits = "".join(c for c in code if c.isdigit())
    print("\nthe code op produced")
    check("six digits are on screen", len(digits) == 6, repr(code))
    # a code that rolled over between op producing it and this line is
    # still the right code, so the step either side of now counts
    at = time.time()
    want = {B.totp_code("JBSWY3DPEHPK3PXP", at=at),
            B.totp_code("JBSWY3DPEHPK3PXP", at=at - 30)}
    check("and it is the right code", digits in want, (digits, want))
    QTimer.singleShot(200, step_degrade)


def step_degrade():
    print("\nop disappears mid-session")
    # Only our scratch bin is on PATH for this one. Deleting the mock
    # has to mean `op` is really gone — on a machine with the real 1Password
    # CLI installed, shutil.which would otherwise find that instead and the
    # provider would report a token error rather than a missing binary.
    global _saved_path
    _saved_path = os.environ["PATH"]
    os.environ["PATH"] = str(BIN)
    (BIN / "op").unlink()
    win.vault.provider.forget_status()
    state = win.vault.provider.probe()
    check("the provider notices", state["ok"] is False
          and state["reason"] == "op-missing", state)
    check("the last good listing is kept, not wiped",
          len(win.vault.provider.load().get("items", [])) == 4)
    started = time.time()
    fresh = B.Browser()
    took = time.time() - started
    check("a browser started now opens at once", took < 2.0, "%.1fs" % took)
    check("on the file vault", fresh.vault.provider.name == "file",
          fresh.vault.provider.name)
    check("and says why once it has looked",
          pump(lambda: fresh.vault_fell_back == "op-missing"),
          fresh.vault_fell_back)
    check("without crashing or hanging", True)
    os.environ["PATH"] = _saved_path
    fresh.close()
    print("\n%d checks failed" % len(fails))
    for f in fails:
        print("  - " + f)
    app.exit(1 if fails else 0)


QTimer.singleShot(3000, step_list)
QTimer.singleShot(40000, lambda: (print("TIMED OUT"), app.exit(1)))
sys.exit(app.exec())
