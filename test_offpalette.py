#!/usr/bin/env python3
"""A surface the browser paints has to come out of the theme.

Its sibling test_themetokens asks whether a token the code NAMES
exists. This one asks the opposite question, and it is the one that
was never asked: whether a colour the code paints was named at all.

A hardcoded `#11111b` resolves nowhere, raises nothing, and looks
perfectly right on the theme it was eyedropped from -- which is the
one it gets looked at on. Everything built on the palette moves when
the theme does; a literal does not, and the mismatch only shows up on
somebody else's theme.

Eight surfaces were doing it on 2026-10-29:

  the diff viewer, the Markdown viewer, the plain-text viewer, the
  regex tester and the HTTP inspector  -- dark slabs in a light window
  the focus and site-limit block pages -- #000 on all 116 themes
  reader mode on a SELECTION           -- #000 while reader mode on a
      PAGE (reader_css) was correctly on the theme, and 17px while the
      page reader honoured readerSize

and five overlays the tools draw on top of a site (the selection bar,
the footnote card, the click-to-load placeholder, the measuring tag,
the form badges). Those five were off-palette even on the DEFAULT
theme: they carried upstream Catppuccin's #11111b, and no palette in
this file holds that colour -- the browser's own island is surface,
#0d0d12. Nobody saw it because on a near-black theme two near-blacks
look like one.

What is checked:

  1. no Mocha literal is left loose in a <style> the browser writes
  2. every colour in the seven page-side tool dicts is a token's
  3. tint_js moves all of them on a light theme and NOTHING else --
     non-colour bytes identical, the default theme untouched, and the
     `rgba(0, 0, 0, 0)` the form inspector COMPARES against left alone
     (rewriting that one would silently stop it matching anything)

Needs Qt only to import browser.py; opens no window, writes nothing.
Run with HOME pointed at a throwaway directory.
"""
import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--dir", metavar="PATH", default=None,
                help="an edition's folder to check instead of this one "
                     "(default: this tree)")
ARGS = ap.parse_args()
REPO = Path(ARGS.dir).expanduser().resolve() if ARGS.dir else HERE
MINE = REPO == HERE

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
sys.path.insert(0, str(REPO))
if not MINE:
    print("    (%s)" % REPO)
    if not (REPO / "browser.py").is_file():
        print("  FAIL no browser.py in  <%s>" % REPO)
        sys.exit(1)

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import browser as B  # noqa: E402  (after the environment is set)

SRC = (REPO / "browser.py").read_text(encoding="utf-8")
TOKEN_HEX = {lit.lower() for lit in B.THEME_SOURCE.values()}

# Colours that are deliberately NOT the browser's theme, each with the
# reason it is exempt. A new entry here is a decision, not a shrug.
ALLOWED = {
    "#2b2b2b": "Minecraft's own chat background - the game's palette, "
               "not ours, and it has to match the game",
    "#ffffff": "Minecraft chat text, same reason; also the only safe "
               "ink for print-to-PDF, which must not follow a theme",
    "#94e2d5": "a named entry in the colour PICKER he chooses from - "
               "the list is colours, not theme tokens",
    "#cba6f7": "same list ('Purple'), and the default privateTint, "
               "which is his pick and not the theme's",
}

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
# a <style> the browser writes into a page it generates itself
STYLE = re.compile(r'"<style>[^"]*"(?:\s*\n\s*"[^"]*")*')

print("(1) no loose literal in a <style> the browser writes")
loose = {}
for block in STYLE.finditer(SRC):
    line = SRC.count("\n", 0, block.start()) + 1
    for lit in HEX.findall(block.group(0)):
        low = lit.lower()
        if low in TOKEN_HEX or low in ALLOWED:
            continue
        loose.setdefault(low, []).append(line)
check("every colour in a generated page is a token or allowed",
      not loose, loose or "none")

print("(2) the page-side tools paint in tokens")
TOOLS = ("DESK_TOOLS", "READ_TOOLS", "DEV_TOOLS_PAGE", "MEDIA_TOOLS2",
         "PLAY_TOOLS", "FORM_TOOLS", "FILE_TOOLS")
present = [n for n in TOOLS if hasattr(B, n)]
check("the tool tables are there", len(present) == len(TOOLS),
      "%d/%d: %s" % (len(present), len(TOOLS),
                     sorted(set(TOOLS) - set(present)) or "all"))
stray = {}
for name in present:
    for key, src in getattr(B, name).items():
        for lit in HEX.findall(src):
            low = lit.lower()
            if low in TOKEN_HEX or low in ALLOWED:
                continue
            stray.setdefault(low, []).append("%s.%s" % (name, key))
check("no off-palette colour in any tool snippet", not stray,
      stray or "none")

print("(3) tint_js moves the colours and nothing else")
# both spellings: the literals going in, and the rgb(r g b / a) the
# swap writes out. A mask that knew only the first would report every
# rewritten snippet as "text changed" -- which it did, the first time.
MASK = re.compile(r"#[0-9a-fA-F]{6}\b"
                  r"|rgba?\(\s*\d+\s*,[^)]*\)"
                  r"|rgb\(\s*\d+ \d+ \d+(?: / [^)]*)?\)")
lights = [t["key"] for t in B.THEMES if t.get("group") == "light"]
check("there are light themes to check against", len(lights) >= 10,
      len(lights))

snippets = [(n, k, s) for n in present
            for k, s in getattr(B, n).items()]
check("there are snippets to check", len(snippets) >= 50, len(snippets))

untouched = [(n, k) for n, k, s in snippets
             if B.tint_js(s, B.DEFAULT_THEME) != s]
check("the default theme is returned byte for byte", not untouched,
      untouched or "all %d identical" % len(snippets))

damaged, moved = [], 0
for theme in lights[:6]:
    for n, k, s in snippets:
        out = B.tint_js(s, theme)
        if MASK.sub("@", s) != MASK.sub("@", out):
            damaged.append("%s/%s.%s" % (theme, n, k))
        moved += out != s
check("only colour literals change", not damaged, damaged[:4] or "none")
check("colours actually do change on a light theme", moved > 0, moved)

print("(4) the scrims and the comparison literal are left alone")
holder = [s for _n, _k, s in snippets if "rgba(0, 0, 0, 0)" in s]
check("the form inspector's transparent-compare is in the tree",
      len(holder) == 1, len(holder))
if holder:
    kept = all("rgba(0, 0, 0, 0)" in B.tint_js(holder[0], t)
               for t in lights[:6])
    check("it survives every light theme unchanged", kept)

# Named for what it actually tests. The first version of this said
# "a shadow stays a shadow", and it passed with _recolor's shadow
# exemption deliberately deleted -- because every black in these
# snippets is at alpha .55-.6, so the ALPHA FLOOR catches them and the
# shadow branch is never reached. A check that cannot fail for the
# reason it names is the thing this whole file exists to stop, so it
# says alpha floor, which is the branch it really covers.
scrim = [(t, n, k) for t in lights[:3] for n, k, s in snippets
         if "rgba(0,0,0,.6)" in s
         and "rgba(0,0,0,.6)" not in B.tint_js(s, t)]
check("a low-alpha black stays a scrim", not scrim, scrim[:3] or "none")
# the shadow exemption itself: no snippet here has a near-opaque black
# behind the word "shadow", so nothing in this tree exercises it. Said
# out loud rather than left to look covered.
opaque = [(n, k) for n, k, s in snippets
          if re.search(r"shadow[^;]*rgba\(\s*0\s*,\s*0\s*,\s*0\s*,"
                       r"\s*(?:0?\.[89]|1(?:\.0+)?)\s*\)", s)]
check("the shadow exemption has nothing to guard here (not covered)",
      not opaque, opaque or "0 near-opaque shadows")

print("(5) the surfaces that were wrong are right")
pal = B.theme_palette(lights[0])
for name, key in (("READ_TOOLS", "selbar"),
                  ("READ_TOOLS", "footnotes"),
                  ("MEDIA_TOOLS2", "heldembeds"),
                  ("DESK_TOOLS", "counter")):
    table = getattr(B, name, {})
    if key not in table:
        check("%s.%s is in the tree" % (name, key), False, "missing")
        continue
    out = B.tint_js(table[key], lights[0])
    check("%s.%s paints on the theme's surface" % (name, key),
          pal["surface"].upper() in out.upper(), pal["surface"])

print("")
print("FAILED %d" % len(fails) if fails else "all ok")
for what in fails:
    print("  - " + what)
sys.exit(1 if fails else 0)
