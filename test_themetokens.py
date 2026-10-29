#!/usr/bin/env python3
"""Every colour the browser asks a theme for has to exist.

theme_color is forgiving by design:

    def theme_color(token, name=None):
        return theme_palette(name).get(token,
                                       THEME_SOURCE.get(token, "#000000"))

so a token nobody defines does not raise -- it comes back pure black.
That is the right behaviour for a theme file a user wrote by hand, and
the wrong behaviour for a token spelled wrong in this file, because the
result is a colour rather than an error.

It cost a real defect. `theme_color("base")` dimmed a sleeping tab, and
there is no "base" anywhere in THEME_SOURCE, so on all 116 themes the
veil was #000000 at alpha 110. On Mocha the background is black anyway,
which is where it was looked at; on the 30 light themes a sleeping tab
was veiled in black. Found here on 2026-10-29 while mirroring the tab
strip into a vertical rail, and independently in the Windows edition
the same day -- which is the best evidence either session had that it
was real rather than a misreading.

So: every token this file passes to theme_color as a literal must
resolve. Checked against THEME_SOURCE and against every one of the 116
palettes, because a token could be absent from the source and present
in the palettes, which still works, and the audit should say which.

This is the whole class, not the one line. A second token spelled
"bg0" or "foreground" would be exactly as silent.

Needs Qt only to import browser.py; opens no window, keeps no data,
writes nothing. Run with HOME pointed at a throwaway directory like
everything else here.
"""
import ast
import collections
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
sys.path.insert(0, str(REPO))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import browser as B  # noqa: E402  (after the environment is set)

SRC = (REPO / "browser.py").read_text(encoding="utf-8")


def literal_tokens(source):
    """Every token handed to theme_color as a plain string, read out of
    the tree.

    Not a regex over the text, for the reason its sibling
    test_bridgecalls gives for reading `class Bridge` the same way: a
    comment is not a call. The line that explains the fix --

        # theme_color("base") never found a palette entry and fell

    -- matched the regex exactly as hard as the bug it describes did,
    so the suite failed on the comment documenting the repair. A parsed
    tree holds calls and not comments, and cannot make that mistake.

    Only the literal calls either way: theme_color(token_variable)
    cannot be checked from here, and pretending otherwise would be the
    same kind of guess this file exists to stop.
    """
    out = collections.Counter()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = (fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else "")
        if name != "theme_color":
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out[first.value] += 1
    return out


USED = literal_tokens(SRC)

print("(1) every literal token resolves")
check("there are tokens to check", len(USED) >= 8, len(USED))

source = set(B.THEME_SOURCE)
themes = list(B.THEME_INDEX)
check("there are themes to check against", len(themes) > 100, len(themes))

unresolvable = []
for token in sorted(USED):
    in_source = token in source
    everywhere = all(token in B.theme_palette(n) for n in themes)
    if not (in_source or everywhere):
        unresolvable.append(token)
check("no token falls through to the #000000 default", not unresolvable,
      unresolvable)

# and it has to be able to fail, or it is decoration. "base" is the one
# that actually did, so it is the fixture.
gone = "base"
resolves = gone in source or all(gone in B.theme_palette(n)
                                 for n in themes)
check("...and the token that caused this would be caught", not resolves,
      "%r resolves after all, so it is the wrong fixture" % gone
      if resolves else "")
check("...so nothing still asks for it", not USED.get(gone, 0),
      USED.get(gone, 0))
# and the trap that caught this suite on the way in, kept as a check:
# the fix is explained in a comment that contains the call it replaced.
check("...and a comment naming it is not read as a call",
      'theme_color("%s")' % gone in SRC, "the fixture comment is gone")


print()
print("(2) the fallback is still the thing worth guarding against")
# If theme_color ever started raising, this suite would be pointless
# and should say so rather than passing quietly.
check("an unknown token really does come back black",
      B.theme_color("no-such-token-" + "x" * 8) == "#000000",
      B.theme_color("no-such-token-" + "x" * 8))
check("...and a known one does not", B.theme_color("bg") != "#000000"
      or B.theme_color("bg", "latte") != "#000000",
      B.theme_color("bg", "latte"))


print()
print("(3) a sleeping tab dims toward the background, not to black")
# the defect in its specific form: the veil is painted with the theme's
# own background so it reads as dimming on a light theme too
veil = re.search(r"_asleep[^)]*\)[^\n]*\n(?:.*\n){0,8}?"
                 r"\s*veil = QColor\(theme_color\(\"([a-z]+)\"\)\)", SRC)
check("the veil takes its colour from a real token", veil is not None,
      "" if veil else "could not find the veil line")
if veil:
    token = veil.group(1)
    check("...and that token is one the themes define", token in source,
          token)
    light = [n for n in themes if not B.theme_is_dark(n)]
    check("...so it differs from black on the light themes",
          all(B.theme_color(token, n).lower() not in ("#000000", "#000")
              for n in light), "%d light themes" % len(light))

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:6])))
else:
    print("all good")
sys.exit(1 if fails else 0)
