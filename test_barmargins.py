#!/usr/bin/env python3
"""One widget owns the address bar's margins, or the marks paint on it.

62e5819 made both of the bar's security marks appear for the first
time, and made update_bar_marks call place_bar_extras -- which is the
function that works out how much margin the address text has to give
up to whatever is sitting inside the bar. That was right and it was
half of it.

The other half: _sync_acct wrote the SAME two margins from two guesses
of its own, `24 if the account handle is up else 0` on the left and
`28 if the star is up else 0` on the right. It knows nothing about the
lock button, nothing about either mark, and nothing about the four
buttons on the right. And _url_changed asks it on the line AFTER
show_address:

        self.show_address(url, view)      # -> place_bar_extras, 283px
    ...
        self._sync_acct()                 # -> 0px

So on every navigation the margin was computed correctly and then
thrown away. Driven on 2026-10-29, same window, one call apart:

    place_bar_extras owns it:  left=283  right=52
    after _sync_acct:          left=0    right=28

Left 283 -> 0 puts the address text straight over the lock button and
over the whole look-alike badge. Right 52 -> 28 runs it under the copy
button. The badge the commit had just brought back was being painted
on, which is the one thing a security mark must not be.

Found by driving the real widget, not by reading it: both halves of
this are invisible in the source of either function. server-71's
test_barmarks.py says plainly that it does not build a window, and
this is the thing that costs.

Third defect, same cause: place_bar_extras never knew about the
account handle at all. _place_acct puts it at x=5 and the lock sits at
x=4, both 20px wide, so on a site with more than one saved login they
were drawn on top of each other.

The fix is one owner. place_bar_extras lays out the handle with
everything else and writes both margins; _sync_acct decides only
whether the handle is visible and then asks. The old line stays as the
fallback for the boot order where the extras do not exist yet.

Drives a real Browser offscreen against scratch data. Your own config
is never touched.
"""
import argparse
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--dir", metavar="PATH", default=None,
                help="an edition's folder to drive instead of this one "
                     "(default: this tree). Needs that tree's own "
                     "_boot.py, which every edition has.")
ARGS = ap.parse_args()
REPO = Path(ARGS.dir).expanduser().resolve() if ARGS.dir else HERE
if REPO != HERE:
    print("    (%s)" % REPO)
    for needed in ("browser.py", "_boot.py"):
        if not (REPO / needed).is_file():
            print("  FAIL no %s in  <%s>" % (needed, REPO))
            sys.exit(1)
sys.path.insert(0, str(REPO))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import json  # noqa: E402
from _boot import B  # noqa: E402

B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "vaultPassword": True}))

from tests.harness import app, spin  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

qapp = app()
win = B.Browser()
win.show()
spin(600)

bar = win.urlbar
made = getattr(win, "_barextras", None) or {}
lock = made.get("lockbtn")
badge = getattr(win, "_securelbl", None)
acct = getattr(win, "acctbtn", None)
# a punycode host that reads as apple.com with a Cyrillic first letter
LOOKALIKE = QUrl("https://xn--pple-43d.com/")


def left():
    return bar.textMargins().left()


def right():
    return bar.textMargins().right()


def ink_starts_at():
    """Where the address text begins. Anything inside the bar to the
    left of this is being painted on."""
    return left()


def ink_ends_at():
    return bar.width() - right()


print("\n(1) the furniture is in the bar")
check("the extras were built", bool(made), sorted(made) or "none")
check("the lock button is there", lock is not None)
check("the look-alike badge is there", badge is not None)
check("the account handle is there", acct is not None)
if not made or lock is None or badge is None or acct is None:
    print("\nBLOCKED: the bar's furniture is not there, nothing to measure")
    sys.exit(1)

print("\n(2) the badge appears, and place_bar_extras gives it room")
win.update_bar_marks(url=LOOKALIKE)
spin(80)
# the fixture first: if the badge is not up, every number below is
# measuring the wrong state and would pass for the wrong reason
check("the badge is up (the fixture, asserted before the numbers)",
      badge.isVisible(), badge.property("state"))
check("it is a real width, not a collapsed label", badge.width() > 40,
      badge.width())
with_badge_left, with_badge_right = left(), right()
check("the margin clears the lock and the badge",
      with_badge_left >= badge.x() + badge.width(),
      "margin %d, badge ends %d" % (with_badge_left,
                                    badge.x() + badge.width()))
check("the badge sits after the lock, not on it",
      badge.x() >= lock.x() + lock.width(),
      "lock ends %d, badge starts %d" % (lock.x() + lock.width(),
                                         badge.x()))

print("\n(3) _sync_acct does not take the margin back")
# the bug: this is the next line _url_changed runs after show_address
before_l, before_r = left(), right()
win._sync_acct()
spin(40)
check("the badge is still up (the fixture)", badge.isVisible())
check("the left margin survived", left() == before_l,
      "%d -> %d" % (before_l, left()))
check("the right margin survived", right() == before_r,
      "%d -> %d" % (before_r, right()))
check("the address does not start on top of the badge",
      ink_starts_at() >= badge.x() + badge.width(),
      "ink at %d, badge ends %d" % (ink_starts_at(),
                                    badge.x() + badge.width()))

print("\n(4) the real navigation order, as _url_changed runs it")
# show_address first, then _sync_star and _sync_acct: 45548-45552
win.show_address(LOOKALIKE)
win._sync_star()
win._sync_acct()
spin(80)
check("the badge is up after a navigation (the fixture)",
      badge.isVisible(), badge.text()[:28])
check("the bar shows the punycode, not the look-alike",
      "xn--" in bar.text(), bar.text())
check("the margin still clears the badge",
      ink_starts_at() >= badge.x() + badge.width(),
      "ink at %d, badge ends %d" % (ink_starts_at(),
                                    badge.x() + badge.width()))
check("the tooltip is not a Python repr", "PyQt6" not in bar.toolTip(),
      bar.toolTip()[:40] or "(empty)")

print("\n(5) the right-hand buttons keep their room")
shown = [n for n in ("barkey", "barqr", "barcopy", "barclear")
         if made.get(n) is not None and made[n].isVisible()]
check("there is a right-hand button to measure (the fixture)",
      bool(shown), shown or "none")
if shown:
    first = min(made[n].x() for n in shown)
    # place_bar_extras leaves itself 2px of slack by design
    check("the address text stops at the first of them",
          ink_ends_at() <= first + 2,
          "ink ends %d, first button at %d" % (ink_ends_at(), first))

print("\n(6) the account handle has a place of its own")
acct.setVisible(True)
win.place_bar_extras()
spin(40)
check("the handle is up (the fixture)", acct.isVisible())
check("the handle is not on top of the lock",
      acct.x() >= lock.x() + lock.width(),
      "lock ends %d, handle starts %d" % (lock.x() + lock.width(), acct.x()))
check("the margin clears the handle too",
      left() >= acct.x() + acct.width(),
      "margin %d, handle ends %d" % (left(), acct.x() + acct.width()))
acct.setVisible(False)
win.place_bar_extras()

print("\n(7) one place decides the margins")
# Parsed, not grepped: a comment naming setTextMargins would satisfy a
# text scan, and the whole point of this section is WHERE the call is.
SRC = (REPO / "browser.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


def margin_writers(node):
    """Every setTextMargins call under `node`, with the enclosing
    function and whether it is guarded by the owner declining."""
    out = []
    for func in ast.walk(node):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(func):
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "setTextMargins"):
                continue
            guard = None
            for branch in ast.walk(func):
                if (isinstance(branch, ast.If)
                        and any(c is call for c in ast.walk(branch.test))
                        is False
                        and any(c is call for n in branch.body
                                for c in ast.walk(n))):
                    guard = ast.unparse(branch.test)
            out.append((func.name, call.lineno, guard))
    return out


writers = margin_writers(TREE)
by_func = {}
for name, line, guard in writers:
    by_func.setdefault(name, []).append((line, guard))
check("the margins are written in exactly three places",
      len(writers) == 3, sorted((n, l) for n, l, _ in writers))
check("place_bar_extras is one of them, the owner",
      "place_bar_extras" in by_func, sorted(by_func))
check("__init__ sets the one-time value before anything is built",
      "__init__" in by_func, by_func.get("__init__"))
# _sync_acct keeps ONE write, and only for the boot order: the extras
# are built from a singleShot(0), so on a real boot _sync_acct runs
# twice out of three times before they exist and place_bar_extras has
# nothing to measure. Measured, not assumed -- that is why the line is
# still there rather than deleted as dead.
sync_writes = by_func.get("_sync_acct", [])
check("_sync_acct writes it at most once", len(sync_writes) <= 1,
      sync_writes or "never")
if sync_writes:
    _line, guard = sync_writes[0]
    check("...and only where the owner declined",
          guard == "not self.place_bar_extras()", guard)
check("_sync_acct asks the owner first",
      any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr == "place_bar_extras"
          for f in ast.walk(TREE)
          if isinstance(f, ast.FunctionDef) and f.name == "_sync_acct"
          for n in ast.walk(f)))

print()
if fails:
    print("%d FAILED:" % len(fails))
    for one in fails:
        print("  - " + one)
    sys.exit(1)
print("all ok")
