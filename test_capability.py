#!/usr/bin/env python3
"""A control the browser shows is a promise it can keep.

Three bugs in one day were the same shape, and they were found one at a
time in three different editions:

    the Subtitles button    bridge.playerSubtitles existed nowhere.
                            Guarded, so clicking it did nothing at all.
    the Graphics button     "Open Windows' graphics settings", offered
                            on macOS, whose handler opens with
                            `if sys.platform != "win32": return False`.
    the PSI switch          "Sleep background tabs before the machine
                            swaps" reads /proc/pressure/memory. Where
                            there is no such file the reading stays 0.0,
                            `0.0 >= limit` is never true, and the
                            browser watches nothing.

Every one of them is the UI's idea of what exists and the code's idea
of what runs being maintained separately, with nothing comparing them.
The result is worse for the person than a missing feature, because the
control's presence IS the promise.

The browser already answers these questions -- the payload carries a
flag per optional thing -- so this suite checks the other half: that
the page actually READS each flag and hides what the flag is about.
Two of them were being computed and ignored.

It deliberately does NOT try to find gated handlers mechanically. A
scan for functions branching on sys.platform returns 30 here, of which
23 look "silent" -- and most of those are _write_private, _pid_alive,
main and friends, which are plumbing and correctly say nothing. Without
a reachability analysis from control to handler that scan is a hunting
tool, not a test, and a test that cries wolf gets switched off. So this
is a written-down table, small and exact, and the pin is what keeps it
from rotting.

No window; reads the payload and the page.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


from _boot import B  # noqa: E402

B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
from tests.harness import app, spin  # noqa: E402

#: flag in the payload -> the element settings.html hides on it
WIRED = {
    "themeWebAvailable": "themewebrow",
    "pressureAvailable": "pressurerow",
    "captureAvailable": "shotpanel",
}

#: computed and NOT read by the page, with why it is not wired yet.
#: privacy.py's docstring says "without this file the browser starts
#: and the privacy switches are simply not there" -- and on this page
#: they still are. Which switches belong to privacy.py and which are
#: the browser's own is a reading job, and hiding the wrong ones would
#: be worse than the bug, so it is named here rather than guessed at.
UNWIRED = {
    "privacyAvailable": "privacy.py's own docstring promises the "
                        "switches disappear without it; settings.html "
                        "does not read the flag. Which rows are its "
                        "own has to be read, not guessed.",
}

qapp = app()
win = B.Browser()
win.show()
spin(500)
PAYLOAD = json.loads(win.bridge.getSettings())
PAGE = (HERE / "settings.html").read_text(encoding="utf-8")

print("(1) the browser answers every capability question")
for flag in list(WIRED) + list(UNWIRED):
    check("the payload carries %s" % flag, flag in PAYLOAD,
          PAYLOAD.get(flag))
    check("...as a yes or a no, not a maybe",
          isinstance(PAYLOAD.get(flag), bool), type(PAYLOAD.get(flag)))

print()
print("(2) ...and the page acts on the ones it is wired for")
for flag, element in WIRED.items():
    check("settings.html has #%s" % element,
          'id="%s"' % element in PAGE)
    check("...and hides it on %s" % flag,
          flag in PAGE and element in PAGE,
          "flag used: %s" % (flag in PAGE))

print()
print("(3) the ones that are not wired are named, not forgotten")
for flag, why in UNWIRED.items():
    check("%s is still unread by the page" % flag, flag not in PAGE,
          "it is read now -- move it to WIRED")
    print("       not wired: %s" % why)

print()
print("(4) the capability is asked of the machine, not of the platform")
# sys.platform != "win32" would say yes on macOS, which has no /proc at
# all, AND on a Linux kernel built without PSI. The question is whether
# the counter is readable here.
src = (HERE / "browser.py").read_text(encoding="utf-8")
check("the pressure flag asks whether the counter reads",
      "def pressure_available" in src
      and "bool(self.memory_pressure())" in src)
check("...and remembers the answer rather than re-reading per call",
      "_have_pressure" in src)
real = win.memory_pressure
try:
    win.memory_pressure = lambda: {}
    win._have_pressure = None
    check("a machine with no counter answers no",
          win.pressure_available() is False)
finally:
    win.memory_pressure = real
    win._have_pressure = None
check("and this machine, which has one, answers yes",
      win.pressure_available() is True, win.pressure_available())

print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
