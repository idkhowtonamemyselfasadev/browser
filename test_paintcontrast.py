#!/usr/bin/env python3
"""The colours the chrome PAINTS, as against the ones it styles.

test_contrast.py sweeps every rule in every page and in the Qt sheet
that names a colour and a background. That is mechanical and it is
thorough, and it cannot see a single pixel of this:

    painter.setPen(QColor(theme_color("muted")))
    painter.drawText(rect, ..., "\u25cb")

A painted widget names its colours in Python. No stylesheet rule ever
puts those two tokens in one place, so no sweep of the stylesheets can
pair them, and a contrast suite that only sweeps stylesheets is green
by construction however bad the painting is. Two widgets paint their
own surfaces here -- GroupTabBar and TabRail -- and between them they
draw the tab strip and the whole vertical sidebar.

That gap had three things in it on 2026-10-29, found after
browser-android hit the same shape in a Kotlin painter and asked
whether anyone had the list:

    the asleep mark          muted on a tab      1.97-2.39:1   116/116
    the no-favicon letter    subtext on sunken   3.57 worst     70/116
    the sidebar tab count    overlay on mantle   4.05 on Mocha   1/116

The first is the instructive one and it is android's exactly: `muted`
EXISTS, so nothing fell back and nothing went obviously wrong. It is a
grey that is almost right, and nobody reports almost-right. THEME_SOURCE
calls it "a disabled thing"; it was never a foreground.

So this file is two halves, and the second is the one that keeps it
honest:

  (1) the table. Every foreground/background pair the two painters
      actually produce, with what it is and what it has to clear. Hand
      written, because only the code knows what a pen lands on.

  (2) a check that the table is COMPLETE: every theme_color("x")
      literal inside a painting method has to appear in the table as a
      foreground or as a background. Add a colour to a paintEvent
      without saying what it sits on and this fails. Without that half
      the table is a snapshot that rots the first time somebody paints
      something new.

Gates are WCAG 2.1: 4.5:1 for text, 3:1 for a glyph or the edge of a
control. Needs Qt only to import browser.py; opens no window.
"""
import ast
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
sys.path.insert(0, str(HERE))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import browser as B  # noqa: E402

TEXT, GLYPH = 4.5, 3.0

#: (foreground token, background token, what it is, what it must clear)
#:
#: The background is what the thing is drawn ON, which for a row or a
#: tab is whichever state it is in -- so a pen that can land on two
#: surfaces appears twice. A pair painted with readable_on() is not in
#: here: that function picks its own foreground against the fill and is
#: correct by construction.
PAINTED = [
    # ---- GroupTabBar: the horizontal strip ----
    ("overlay", "surface", "the asleep mark on a tab", GLYPH),
    ("overlay", "hover", "the asleep mark on the selected tab", GLYPH),
    ("bright", "surface", "the loading line along a tab", GLYPH),
    ("bright", "hover", "the loading line, selected tab", GLYPH),
    ("bright", "surface", "the dot saying a tab changed", GLYPH),
    ("bright", "hover", "the ring round a ctrl-clicked tab", GLYPH),
    # ---- TabRail: the vertical sidebar ----
    ("subtext", "mantle", "an ordinary row's title", TEXT),
    ("subtext", "surface", "a hovered row's title", TEXT),
    ("text", "hover", "the current row's title", TEXT),
    ("text", "sunken", "the letter standing in for a missing favicon", TEXT),
    ("subtext", "hover", "the close cross on the current row", GLYPH),
    ("subtext", "surface", "the close cross on a hovered row", GLYPH),
    ("overlay", "hover", "the current row's border", GLYPH),
    ("accent", "mantle", "the loading bar under a row", GLYPH),
    ("accent", "hover", "the loading bar, current row", GLYPH),
    ("bright", "mantle", "the dot saying a row changed", GLYPH),
    ("bright", "surface", "the ring round a ctrl-clicked row", GLYPH),
]

#: Fills that are MEANT to be quiet, with the gated pair that carries
#: the meaning instead. These are not exempt because measuring them was
#: inconvenient -- they are exempt because a contrast ratio is the
#: wrong question for them, and the right question is asked elsewhere
#: in the table above. Each one has to name where.
#:
#: The rule for adding to this list: if the thing itself says something
#: -- a mark, a letter, a line, an edge you are meant to see -- it
#: belongs in PAINTED and is gated. If its only job is to be the
#: backdrop for something that IS gated, it belongs here.
QUIET = [
    ("sunken", "mantle", "the favicon chip is a slot, not a mark; it is "
                         "deliberately close to the rail, and the letter "
                         "inside it is gated as text on sunken"),
    ("bg", "surface", "the veil over a sleeping row exists to REDUCE "
                      "contrast; the mark that says the row is asleep is "
                      "gated as overlay on surface"),
]

#: tokens a painter may name without being a foreground or a background
#: in the table above, with the reason. A fill that something else is
#: measured against is already covered by the pair that names it.
PAINT_ONLY = {
    "bright": "also the fill of the unread badge, whose own ink is "
              "chosen by readable_on()",
    "overlay": "also the fallback colour of a group pill, whose ink is "
               "chosen by readable_on()",
}

THEMES = list(B.THEME_INDEX)
PAL = {t: B.theme_palette(t) for t in THEMES}


def ratio(fg, bg, theme):
    return B.contrast_ratio(PAL[theme][fg], PAL[theme][bg])


print("(1) every pair the chrome paints, on every theme")
check("there are themes to check", len(THEMES) > 100, len(THEMES))
check("there are pairs to check", len(PAINTED) >= 15, len(PAINTED))
bad = []
for fg, bg, what, gate in PAINTED:
    lows = sorted((ratio(fg, bg, t), t) for t in THEMES)
    if lows[0][0] < gate:
        under = sum(1 for r, _t in lows if r < gate)
        bad.append("%s (%s on %s) %.2f on %s, %d themes short"
                   % (what, fg, bg, lows[0][0], lows[0][1], under))
check("no painted pair falls under what it has to clear", not bad, bad)
# and the exemptions have to be real: a fill that is not actually quiet
# is not being exempted, it is being hidden.
loud = [w for fg, bg, w in QUIET
        if min(ratio(fg, bg, t) for t in THEMES) >= GLYPH]
check("every pair excused as a quiet fill really is a quiet one",
      not loud, loud)
for fg, bg, why in QUIET:
    print("       quiet by design: %s on %s -- %s" % (fg, bg, why))
for fg, bg, what, gate in PAINTED:
    lows = sorted(ratio(fg, bg, t) for t in THEMES)
    print("       %-46s %.1f  worst %.2f" % (what, gate, lows[0]))


print()
print("(2) ...and the table knows about every colour they paint")
SRC = (HERE / "browser.py").read_text(encoding="utf-8")
PAINTERS = ("paintEvent", "_paint_tab", "_paint_group", "_extras",
            "_initial")


def painted_tokens(source):
    """Every theme_color("x") literal inside a painting method.

    The AST, not a regex, for the reason this tree has now learned
    three times in one day: a comment explaining a colour that USED to
    be painted matches a text scan exactly as hard as a colour that is.
    """
    out = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in PAINTERS:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call) or not inner.args:
                continue
            fn = inner.func
            name = (fn.id if isinstance(fn, ast.Name)
                    else fn.attr if isinstance(fn, ast.Attribute) else "")
            if name != "theme_color":
                continue
            first = inner.args[0]
            if isinstance(first, ast.Constant) \
                    and isinstance(first.value, str):
                out.setdefault(first.value, set()).add(node.name)
    return out


USED = painted_tokens(SRC)
check("the painters were found", len(USED) >= 5, sorted(USED))
listed = ({fg for fg, _b, _w, _g in PAINTED}
          | {bg for _f, bg, _w, _g in PAINTED}
          | {fg for fg, _b, _w in QUIET} | {bg for _f, bg, _w in QUIET})
unlisted = sorted(t for t in USED if t not in listed
                  and t not in PAINT_ONLY)
check("every colour a painter names is in the table", not unlisted,
      {t: sorted(USED[t]) for t in unlisted})
stale = sorted(t for t in PAINT_ONLY if t not in USED)
check("...and nothing is excused that is no longer painted", not stale,
      stale)


print()
print("(3) the scanner can tell a call from a comment")
check("a painted colour is found",
      "zzTok" in painted_tokens(
          'class X:\n    def paintEvent(self, e):\n'
          '        p.setPen(theme_color("zzTok"))\n'))
check("...and one that is only talked about is not",
      "zzTok" not in painted_tokens(
          'class X:\n    def paintEvent(self, e):\n'
          '        # was theme_color("zzTok")\n        pass\n'))
check("...and one painted outside a painter is not this file's business",
      "zzTok" not in painted_tokens(
          'def elsewhere():\n    return theme_color("zzTok")\n'))


print()
print("(4) the three that were actually wrong are gone")
# kept as fixtures: these are the exact pairs that shipped, and if any
# of them comes back this says which.
for fg, bg, what, gate in (("muted", "surface", "the asleep mark", GLYPH),
                           ("muted", "hover", "the asleep mark", GLYPH),
                           ("subtext", "sunken", "the chip letter", TEXT)):
    worst = min(ratio(fg, bg, t) for t in THEMES)
    check("%s on %s is still too quiet to use (%.2f)" % (fg, bg, worst),
          worst < gate, worst)
check("...so the asleep mark no longer uses muted",
      "muted" not in USED, sorted(USED.get("muted", [])))
check("...and the chip letter no longer uses subtext on sunken",
      'painter.setBrush(QColor(theme_color("sunken")))\n'
      '        painter.drawRoundedRect(box, 4, 4)' in SRC
      and 'theme_color("subtext")))\n        font = painter.font()'
      not in SRC)

print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
