#!/usr/bin/env python3
"""Vault Password switched off: the browser does not look at logins.

The claim being tested is a negative, which is the kind that rots
quietly — every other password suite runs with the feature ON, so
nothing else here would notice if "off" started meaning "off except for
this one path". So these checks are about absence: nothing injected
into a page, no way in, nothing written to disk.

The pair that carries the most weight is (3): the same probe returns
"object" with the feature on and "undefined" with it off. Either half
alone would prove nothing, which is why both are run — each in its own
process, because two Browser windows in one process do not both get to
load pages reliably offscreen.

Scratch everything, never your own vault."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def scratch(name):
    d = Path(tempfile.mkdtemp(prefix="browser-shot-" + name + "-"))
    (d / "share").mkdir(parents=True, exist_ok=True)
    return d


def redirect(cfg):
    """Every data file into scratch, before Browser() reads any."""
    for name in ("CONFIG_FILE", "HISTORY_FILE", "DOWNLOADS_FILE",
                 "HOSTS_FILE", "BOOKMARKS_FILE"):
        setattr(B, name, cfg / (name.lower() + ".json"))


# =====================================================================
# --probe: one Browser, one page, in a process of its own
# =====================================================================
if len(sys.argv) > 2 and sys.argv[1] == "--settings":
    # Hiding a section renumbers the rail: showCat indexes into the
    # section list and buildNav numbers its buttons from it, so if the
    # two ever disagree a rail click opens the wrong page. Proved here
    # by clicking the last button and seeing which section comes up.
    on = sys.argv[2] == "on"
    d = scratch("settings")
    os.environ["XDG_DATA_HOME"] = str(d / "share")
    import browser as B
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    import harness as H
    cfg = d / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    redirect(cfg)
    B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": on,
                                         "translateLang": "en"}))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    win = B.Browser()
    win.show()
    win.open_settings()
    H.spin(3000)
    page = win._panes["settings"].view.page()
    box = {}
    page.runJavaScript("""(function () {
      var sec = document.querySelector('section[data-desc="descPasswords"]');
      var btns = [...document.querySelectorAll('#sidebar button')];
      var last = btns[btns.length - 1];
      last.click();
      var shown = [...document.querySelectorAll('.content section')]
                  .filter(s => s.classList.contains('active'));
      return JSON.stringify({
        pwHidden: !!(sec && sec.hidden),
        pwVisible: !!(sec && !sec.hidden),
        buttons: btns.length,
        lastName: last.textContent.trim(),
        openedName: shown.length === 1
                    ? shown[0].querySelector('h2').textContent.trim() : "?",
        vaultRow: !!document.getElementById('vaultpw'),
        vaultChecked: !!(document.getElementById('vaultpw') || {}).checked,
        keptNote: (document.getElementById('t_vaultKept') || {}).textContent
      });
    })()""", B.MAIN_WORLD_ID, lambda r: (box.update({"v": r}), app.quit()))
    QTimer.singleShot(8000, app.quit)
    app.exec()
    print("SETTINGS " + (box.get("v") or "{}"))
    sys.stdout.flush()
    os._exit(0)


if len(sys.argv) > 2 and sys.argv[1] == "--probe":
    on = sys.argv[2] == "on"
    d = scratch("probe")
    os.environ["XDG_DATA_HOME"] = str(d / "share")
    import browser as B
    from PyQt6.QtWidgets import QApplication
    import harness as H
    cfg = d / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    redirect(cfg)
    B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": on}))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("browser-shot")
    srv = H.Server({"/login": "<!doctype html><form>"
                              "<input id=u type=email><input id=p type=password>"
                              "<button id=go>Log in</button></form>"})
    win = B.Browser()
    win.show()                 # or every widget reports invisible
    win.new_tab(url=srv.url("/login"))
    H.spin(300)
    view = win.current()
    H.load(view, srv.url("/login"))
    print("PROBE %s %s" % (view.url().path(),
                           H.js(view, "typeof window.__bpw", B.PW_WORLD_ID)))
    sys.stdout.flush()
    os._exit(0)                # Qt teardown offscreen is not worth waiting on


# =====================================================================
# (1) who gets it switched on — the pure function, no Qt in the way
# =====================================================================
print("\n(1) who gets it switched on")
os.environ["XDG_DATA_HOME"] = str(scratch("defaults") / "share")
import browser as B  # noqa: E402

empty = scratch("empty")
check("a fresh install is off",
      B._vault_password_default({}, empty) is False)
check("an install that finished setup keeps it",
      B._vault_password_default({"startPage": {"setupDone": "1"}}, empty)
      is True)
withvault = scratch("withvault")
(withvault / "passwords.json").write_text("{}")
check("a vault on disk keeps it, wizard or no wizard",
      B._vault_password_default({}, withvault) is True)
check("a chosen remote store keeps it",
      B._vault_password_default({"passwordProvider": "1password"}, empty)
      is True)
check("an explicit file provider does not, on its own",
      B._vault_password_default({"passwordProvider": "file"}, empty) is False)


# =====================================================================
# (2) one browser, switched on, then off underneath itself
# =====================================================================
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
import harness as H  # noqa: E402

d = scratch("live")
cfg = d / "cfg"
cfg.mkdir(parents=True, exist_ok=True)
redirect(cfg)
B.CONFIG_FILE.write_text(json.dumps({"vaultPassword": True}))
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()

print("\n(2) the watcher follows the switch, in every cookie jar")
check("on: the main profile has it",
      len(win.profile.scripts().find("password-watch")) == 1)
# the real path a second cookie jar arrives by — _session_profile is
# what every virtual browser goes through, and it is the registry the
# appliers iterate, so a detached _make_profile would prove nothing
later = win._session_profile("later")
check("on: so does a virtual browser made afterwards",
      len(later.scripts().find("password-watch")) == 1)

print("\n(3) and no page ever sees it")
out = {}
for mode in ("on", "off"):
    r = subprocess.run([sys.executable, str(HERE / "test_vaultoff.py"),
                        "--probe", mode],
                       capture_output=True, text=True, timeout=180)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("PROBE ")]
    out[mode] = line[0].split() if line else ["PROBE", "", ""]
check("the probe page really loaded, both times",
      out["on"][1] == "/login" and out["off"][1] == "/login",
      "%s / %s" % (out["on"][1], out["off"][1]))
check("with it on, the watcher's world is live",
      out["on"][2] == "object", out["on"][2])
check("with it off, there is nothing there",
      out["off"][2] == "undefined", out["off"][2])


# =====================================================================
# (4) seed a vault, then switch off underneath it
# =====================================================================
print("\n(4) switching off keeps what is already there")
win.vault.set_entry("example.com", "https", "user@example.com", "hunter2")
win.vault.set_entry("example.com", "https", "work@example.com", "s3cret")
vault_file = cfg / "passwords.json"
check("the vault is on disk", vault_file.exists())
size = vault_file.stat().st_size

win.bridge.setSetting("vaultPassword", "false")
H.spin(200)
check("switching off deletes nothing",
      vault_file.exists() and vault_file.stat().st_size == size,
      vault_file.stat().st_size if vault_file.exists() else "gone")
check("and the watcher goes with it",
      len(win.profile.scripts().find("password-watch")) == 0)
check("in the jars made earlier too",
      len(later.scripts().find("password-watch")) == 0)


# =====================================================================
# (5) with it off, there is no way in and nothing to write
# =====================================================================
print("\n(5) no way in")
before = win.tabs.count()
win.open_passwords()
check("Ctrl+Shift+P opens nothing", win.tabs.count() == before,
      "%d -> %d" % (before, win.tabs.count()))
clip = QGuiApplication.clipboard()
clip.setText("untouched")
win.generate_to_clipboard()
check("Ctrl+Shift+G puts nothing on the clipboard",
      clip.text() == "untouched", clip.text())
check("a saved passwords tab is not restored",
      win._restore_url(B.PASSWORDS_PAGE.toString()) is None)
check("the settings page is told, so it can hide the section",
      json.loads(win.bridge.getSettings())["vaultPassword"] is False)
check("and the summary says nothing", win.bridge.passwordSummary() == "{}")

view = win.current()
if view is not None and hasattr(view, "page"):
    win._password_submitted(view.page(), json.dumps(
        {"host": "nowhere.example", "scheme": "https",
         "username": "user@example.com", "password": "hunter2"}))
    H.spin(200)
check("a submitted login is not even considered",
      win._pw_pending in (None, {}), str(win._pw_pending))
check("and the vault file did not grow",
      vault_file.stat().st_size == size, vault_file.stat().st_size)


# =====================================================================
# (6) back on, live, with everything still in it
# =====================================================================
print("\n(6) switching back on")
win.bridge.setSetting("vaultPassword", "true")
H.spin(200)
check("the watcher returns without a restart",
      len(win.profile.scripts().find("password-watch")) == 1)
back = B.PasswordVault(cfg, provider=B.FileVaultProvider(cfg))
names = sorted(i.get("username", "") for i in back.items())
check("and both logins are still there",
      names == ["user@example.com", "work@example.com"], names)


# =====================================================================
# (7) what Settings looks like either way
# =====================================================================
print("\n(7) the Passwords section comes and goes, and the rail keeps up")
sett = {}
for mode in ("on", "off"):
    r = subprocess.run([sys.executable, str(HERE / "test_vaultoff.py"),
                        "--settings", mode],
                       capture_output=True, text=True, timeout=180)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("SETTINGS ")]
    sett[mode] = json.loads(line[0][len("SETTINGS "):]) if line else {}

check("on: the Passwords section is in Settings",
      sett["on"].get("pwVisible") is True, sett["on"])
check("off: it is not", sett["off"].get("pwHidden") is True, sett["off"])
check("off: the rail is one button shorter",
      sett["off"].get("buttons") == sett["on"].get("buttons", 0) - 1,
      "%s -> %s" % (sett["on"].get("buttons"), sett["off"].get("buttons")))
for mode in ("on", "off"):
    check("%s: the last rail button opens the section it names" % mode,
          sett[mode].get("lastName")
          and sett[mode].get("lastName") == sett[mode].get("openedName"),
          "%s -> %s" % (sett[mode].get("lastName"),
                        sett[mode].get("openedName")))
check("the switch is in Plugins either way",
      sett["on"].get("vaultRow") and sett["off"].get("vaultRow"))
check("and it shows the right state",
      sett["on"].get("vaultChecked") is True
      and sett["off"].get("vaultChecked") is False,
      "%s / %s" % (sett["on"].get("vaultChecked"),
                   sett["off"].get("vaultChecked")))
check("off with no vault yet says nothing about keeping anything",
      sett["off"].get("keptNote") == "", repr(sett["off"].get("keptNote")))

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
