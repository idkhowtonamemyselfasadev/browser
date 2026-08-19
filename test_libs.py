#!/usr/bin/env python3
"""The libraries underneath: the every-two-days check, and the identity
the engine hands to Google.

Two features, one file, because they are the same promise from two
sides — the browser is honest about what it is, and it keeps what it is
standing on current.

Nothing in here starts a real command. `_lib_run` is the single seam the
whole feature goes through, and every check below replaces it, so no dnf
is asked anything and pkexec — which would put a root-password box on
somebody's screen — is never reached at all. What it is *asked* to run
is asserted instead, which is the part that matters.

Offscreen, against scratch data only — _boot redirects the config, the
history, the downloads, the hosts, the bookmarks and XDG_DATA_HOME into
a temporary directory before the browser is ever built.
"""
import json
import os
import sys
import time
from pathlib import Path

# The browser arms the check itself twenty seconds after startup. Left
# on, that would run a real dnf somewhere in the middle of this file and
# make the counted commands below depend on the weather. Off here, and
# driven by hand instead -- with the armed case checked at the end, on a
# browser built without the flag.
os.environ["BROWSER_NO_LIB_CHECK"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication, QToolButton  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()

# every command the browser asks for, and the callback it is waiting on
runs = []


def fake_run(program, args, done):
    runs.append((program, list(args), done))
    return None


win._lib_run = fake_run


def arm(every=2, last=0):
    """A config in a known state, and no toast in the way."""
    win._hide_toast()
    app.processEvents()
    win._toast = None
    win._lib_checking = False
    win.config["libUpdateEvery"] = every
    win.config["libUpdateLast"] = last
    win.save_config()
    del runs[:]


def stamped():
    """What actually reached the config file on disk, not the copy in
    memory — the point of the stamp is that it survives the process."""
    try:
        return json.loads(B.CONFIG_FILE.read_text()).get("libUpdateLast", 0)
    except Exception:
        return 0


def toast_buttons():
    if not win._toast:
        return []
    return [b.text() for b in win._toast.findChildren(QToolButton)]


print("\nGoogle is told the same thing twice")
# The user-agent says Chrome (the QtWebEngine token is stripped); the
# client hints used to still say Chromium, and sign-in read both, saw
# the mismatch and answered "this browser or app may not be secure".
for label, storage in (("a normal cookie jar", "test-hints"),
                       ("a private window", None)):
    profile = win._make_profile(storage)
    try:
        brands = profile.clientHints().fullVersionList()
    except AttributeError:
        brands = {}
    check(label + " advertises Google Chrome",
          "Google Chrome" in brands, str(brands))
    check(label + " still advertises Chromium",
          "Chromium" in brands, str(brands))
    check(label + " gives the brand a real version",
          bool(brands.get("Google Chrome")), str(brands))
    ua = profile.httpUserAgent()
    check(label + " keeps the QtWebEngine token out of the user-agent",
          "QtWebEngine" not in ua, ua)

print("\nthe gate")
arm(every=2, last=0)
win._check_lib_updates()
check("a stale stamp starts a check", len(runs) == 1,
      "%d commands" % len(runs))
if runs:
    program, args, _ = runs[0]
    check("and the check is the one that needs no root",
          program != "pkexec" and "upgrade" not in args,
          "%s %s" % (program, args))
    check("it asks about the libraries the browser runs on",
          any("pyqt6" in a.lower() for a in args)
          or "pip" in args, "%s %s" % (program, args))

arm(every=2, last=int(time.time()))
win._check_lib_updates()
check("a fresh stamp starts nothing", not runs, "%d commands" % len(runs))

arm(every=0, last=0)
win._check_lib_updates()
check("zero days is off, however stale the stamp is", not runs,
      "%d commands" % len(runs))
check("and off does not quietly move the stamp on", stamped() == 0,
      str(stamped()))

arm(every=2, last=0)
win._check_lib_updates()
win._check_lib_updates()
check("a check already in flight is not started twice", len(runs) == 1,
      "%d commands" % len(runs))

print("\nnothing to do is silent")
arm(every=2, last=0)
before = time.time()
win._check_lib_updates()
runs[0][2](0, "")            # dnf: 0 means nothing waiting
app.processEvents()
check("a clean check writes the stamp down", stamped() >= int(before),
      str(stamped()))
check("and says nothing at all", win._toast is None)
check("so the next tick asks nothing", (win._check_lib_updates(),
                                        len(runs) == 1)[1],
      "%d commands" % len(runs))

print("\na check that could not be made is not an answer")
arm(every=2, last=0)
win._check_lib_updates()
runs[0][2](-1, "")           # no dnf on this machine, or no network
app.processEvents()
check("a failed check leaves the stamp alone", stamped() == 0,
      str(stamped()))
check("and puts nothing on the screen", win._toast is None)
win._lib_checking = False
win._check_lib_updates()
check("so it is tried again next time", len(runs) == 2,
      "%d commands" % len(runs))

print("\nupdates waiting: an offer, never a surprise")
arm(every=2, last=0)
win._check_lib_updates()
runs[0][2](100, "")          # dnf: 100 means there is something
app.processEvents()
check("it offers", win._toast is not None)
check("with an Update button",
      win._ui_str("libUpdateBtn") in toast_buttons(), str(toast_buttons()))
check("and the offer alone runs nothing else", len(runs) == 1,
      str([r[0] for r in runs]))
check("and does not stamp before it is answered", stamped() == 0,
      str(stamped()))

print("\n\"not now\" is an answer too")
before = time.time()
win._lib_dismiss()
app.processEvents()
check("dismissing takes the toast away", win._toast is None)
check("and stamps, so it does not ask again tomorrow",
      stamped() >= int(before), str(stamped()))

print("\nUpdate: the one press that is allowed to ask for root")
arm(every=2, last=0)
win._check_lib_updates()
runs[0][2](100, "")
app.processEvents()
del runs[:]
win._lib_update_now()
check("pressing Update runs exactly one command", len(runs) == 1,
      "%d commands" % len(runs))
if runs:
    program, args, _ = runs[0]
    if sys.platform == "win32":
        check("which is pip, in this interpreter",
              program == sys.executable and "pip" in args,
              "%s %s" % (program, args))
        check("and installs the browser's own libraries",
              "PyQt6" in args, "%s %s" % (program, args))
    else:
        check("which is the one that goes through polkit",
              program == "pkexec", "%s %s" % (program, args))
        check("and is a dnf upgrade of the browser's own packages",
              args[:1] == ["dnf"] and "upgrade" in args
              and any("pyqt6" in a.lower() for a in args),
              "%s %s" % (program, args))

before = time.time()
runs[0][2](0, "")
app.processEvents()
check("a successful upgrade is written down", stamped() >= int(before),
      str(stamped()))
check("and offers the restart the new libraries need",
      win._ui_str("restartNow") in toast_buttons(), str(toast_buttons()))

print("\nan upgrade that did not take")
arm(every=2, last=0)
win._check_lib_updates()
runs[0][2](100, "")
app.processEvents()
del runs[:]
win._lib_update_now()
before = time.time()
runs[0][2](1, "")            # pkexec cancelled, or dnf refused
app.processEvents()
check("it says so rather than pretending",
      win._toast is not None
      and win._toast_label.text() == win._ui_str("libFailed"),
      win._toast_label.text() if win._toast else "no toast")
check("no restart is offered for libraries that did not change",
      win._ui_str("restartNow") not in toast_buttons(), str(toast_buttons()))
check("and it is not offered again in six hours", stamped() >= int(before),
      str(stamped()))

print("\none prompt at a time")
arm(every=2, last=0)
win._show_restart_toast("something else is asking")
win._check_lib_updates()
runs[0][2](100, "")
app.processEvents()
check("the library offer waits its turn",
      win._toast is not None
      and win._toast_label.text() == "something else is asking",
      win._toast_label.text() if win._toast else "no toast")
check("and nothing is stamped, so the offer is not lost", stamped() == 0,
      str(stamped()))
win._hide_toast()
app.processEvents()

print("\nthe setting reaches the settings page")
arm(every=3, last=0)
settings = json.loads(win.bridge.getSettings())
check("getSettings carries the interval",
      settings.get("libUpdateEvery") == 3, str(settings.get("libUpdateEvery")))
win.config.pop("libUpdateEvery", None)
settings = json.loads(win.bridge.getSettings())
check("and a config that never had it defaults to two days",
      settings.get("libUpdateEvery") == B.LIB_UPDATE_DAYS,
      str(settings.get("libUpdateEvery")))
page = (Path(__file__).resolve().parent / "settings.html").read_text()
check("the page has a control for it", 'id="libdays"' in page)
check("wired to the same key", '"libUpdateEvery"' in page)
for key in ("libUpdates", "libUpdatesHint", "libAvailable", "libUpdateBtn",
            "libUpdating", "libUpdated", "libFailed", "restartNow"):
    check("English has a string for " + key, key in B.UI_STRINGS["en"])

print("\nthe timers")
check("the harness flag leaves the automatic check unarmed",
      win._lib_timer is None)
os.environ.pop("BROWSER_NO_LIB_CHECK", None)
second = B.Browser()
# its own twenty-second shot is still out there; nothing to check means
# nothing to run, so it lands on a browser that has the feature switched
# off and goes quietly nowhere
second.config["libUpdateEvery"] = 0
check("without it, a long-running session keeps looking",
      second._lib_timer is not None and second._lib_timer.isActive())
check("on the six-hourly tick",
      second._lib_timer.interval() == B.LIB_TICK_MS,
      str(second._lib_timer.interval()))
check("and the first look waits until the window is up",
      B.LIB_FIRST_MS >= 5000, str(B.LIB_FIRST_MS))
second._lib_timer.stop()

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
app.quit()
sys.exit(1 if fails else 0)
