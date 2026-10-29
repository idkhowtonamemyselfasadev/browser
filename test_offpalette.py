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
import ast
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
# Every exemption is scoped to WHERE it applies. A flat list cannot
# say "black is fine behind a video", only "black is fine", and the
# difference is a guard that keeps working. This file already made
# that mistake twice: a global #ffffff entry written for Minecraft
# chat text silently excused a white background on every generated
# page, and a global #000 would have excused a black one forever.
# Each key is (literal, where); `where` is the enclosing function for
# a generated page, or TABLE.key for a tool snippet.
ALLOWED_AT = {
    ("#2b2b2b", "minimessage_html"):
        "Minecraft's own chat background - the game's palette, not "
        "ours, and it has to match the game it is previewing",
    ("#ffffff", "minimessage_html"):
        "Minecraft chat text, same reason",
    ("#000", "MEDIA_TOOLS2.winfull"):
        "the letterbox behind a video at full screen - black is the "
        "absence of a frame, not a surface, and it must not take the "
        "theme's colour on a light one",
    ("#000", "PLAY_TOOLS.twitchgrid"):
        "same: the bars beside a stream that does not fill its cell",
}

# Colours that are not surfaces at all: entries in the colour PICKER
# he chooses from. The list is colours, so a literal is the only thing
# it could be. Global, because a colour named "Teal" is teal wherever
# the list is read from.
ALLOWED_NAMED = {
    "#94e2d5": "a named entry in the colour picker ('Teal')",
    "#cba6f7": "the same list ('Purple'), and the default privateTint, "
               "which is his pick and not the theme's",
}

# Three digits as well as six, and that is not pedantry -- it was a
# hole in this file. The first version read only {6}, so it passed
# clean on a tree where the focus page and the site-limit page were
# back to a hardcoded `#000` and the selection reader with them.
# "all ok" meant "all ok except flat black". Caught by browser-mac-8f
# reading this suite against the diff it was supposed to cover, which
# is the only way a blind spot in a guard ever gets found: the guard
# cannot report what it cannot see.
#
# _recolor is blind the same way -- its _COLOR_RE is {6} too -- so a
# three-digit literal can never be swapped for a token even where
# tint_js runs. That makes it worse than an off-palette six-digit one,
# not more forgivable, and it is why `#000` is NOT excused below for
# being bg's own value in short form.
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
# the short form on its own: _recolor cannot swap one at all
SHORT_HEX = re.compile(r"#[0-9a-fA-F]{3}\b")
# a <style> the browser writes into a page it generates itself
STYLE = re.compile(r'"<style>[^"]*"(?:\s*\n\s*"[^"]*")*')


def widen(lit):
    """#abc -> #aabbcc, so one literal has one spelling."""
    low = lit.lower()
    if len(low) == 4:
        return "#" + "".join(c + c for c in low[1:])
    return low


DEF = re.compile(r"^\s*def (\w+)\(", re.M)


def enclosing(offset):
    """The function a point in the source is inside."""
    last = "<module>"
    for m in DEF.finditer(SRC):
        if m.start() > offset:
            break
        last = m.group(1)
    return last


print("(1) no loose literal in a <style> the browser writes")
# A token's own hex is NOT excused here, unlike in the tool snippets
# below. These pages are built by string formatting and nothing ever
# recolours them, so `#000000` written into one is a literal that
# happens to equal bg today and will not move when the theme does.
# Being spelled like a token is not the same as coming from one.
loose = {}
for block in STYLE.finditer(SRC):
    where = enclosing(block.start())
    for lit in HEX.findall(block.group(0)):
        low, wide = lit.lower(), widen(lit)
        if (low, where) in ALLOWED_AT or (wide, where) in ALLOWED_AT:
            continue
        if low in ALLOWED_NAMED or wide in ALLOWED_NAMED:
            continue
        loose.setdefault("%s in %s" % (low, where), []).append(where)
check("every colour in a generated page is a token or allowed",
      not loose, sorted(loose) or "none")

# The literals nobody has decided about yet, each keyed to the exact
# place it is in. Not an exemption and not a failure: an OPEN ITEM,
# printed every run with its reason so it cannot rot into silence the
# way ALLOWED did when it was global.
#
# The number is pinned. A new undecided literal fails until somebody
# writes a line here saying what it is, which is the point: the cost
# of leaving one is one sentence, and the cost of hiding one is a
# guard nobody trusts.
PENDING_AT = {
    ("PAGE_TOOLS.visited", "#b48ead"):
        "recolours the SITE's visited links, not our chrome. Whether "
        "the browser should repaint somebody else's links in its own "
        "accent is a product call, not a theming bug",
    ("READER_TOOLS.hints", "#ffd866"):
        "the highlighter pen's yellow. A highlighter is a real object "
        "and yellow is what one is; a themed highlighter is a "
        "different feature, not a fix to this one",
    ("READER_TOOLS.hints", "#806000"):
        "the pen's darker edge, same decision",
    ("READER_TOOLS.hints", "#000"):
        "the pen's ink. It cannot move while the yellow under it "
        "cannot move, or the pen stops being readable",
    ("PAGE_TOOLS.totop", "#fff"):
        "the back-to-top button's ink. Measured: its fill is "
        "rgba(20,20,20,.75), alpha under 0.8, which _recolor leaves "
        "alone BY DESIGN as a scrim -- so only the ink could move, and "
        "bright-on-that-unmoved-scrim fails 4.5:1 on 30 of the 116 "
        "themes, every one of them light. Moving the ink alone makes "
        "it worse. Needs the fill dealt with first",
}

print("(2) the page-side tools paint in tokens")
TOOLS = ("DESK_TOOLS", "READ_TOOLS", "DEV_TOOLS_PAGE", "MEDIA_TOOLS2",
         "PLAY_TOOLS", "FORM_TOOLS", "FILE_TOOLS")
# The tuple is for PRESENCE only: it says these names must still
# exist, so a rename shows up as a failure rather than as a table
# quietly dropping out of the sweep. What gets SWEPT is whatever the
# module holds, because the tuple named seven and there are eleven.
#
# browser-windows-9a proved the cost with a control, which is what
# makes it convincing: #11111b into PAGE_TOOLS.totop gave "all ok",
# and the same literal in READ_TOOLS failed. Reproduced here before
# changing this -- plus #123456 into READER_TOOLS, also "all ok".
# DEV_TOOLS, MEDIA_TOOLS, PAGE_TOOLS and READER_TOOLS were unswept,
# including the two that still hold off-palette literals. The guard
# worked on everything it covered, which is exactly why nobody saw it.
missing = [n for n in TOOLS if not hasattr(B, n)]
check("the tool tables are still named what they were", not missing,
      missing or "all %d" % len(TOOLS))
present = sorted(n for n in dir(B)
                 if "TOOLS" in n and isinstance(getattr(B, n, None), dict))
check("every table the module holds is swept", len(present) >= len(TOOLS),
      "%d swept: %s" % (len(present), ", ".join(present)))
# Here a token's own hex IS fine: tint_js runs _recolor over these,
# so #0d0d12 becomes the theme's surface. A three-digit one is not,
# even when it widens to a token -- _COLOR_RE cannot match it, so it
# would sit there unswapped looking correct.
stray, short, open_items = {}, {}, []
for name in present:
    for key, src in getattr(B, name).items():
        for lit in HEX.findall(src):
            low = lit.lower()
            where = "%s.%s" % (name, key)
            if (low, where) in ALLOWED_AT or low in ALLOWED_NAMED:
                continue
            if (where, low) in PENDING_AT:
                open_items.append((where, low))
                continue
            if len(low) == 4:
                short.setdefault(low, []).append(where)
                continue
            if low in TOKEN_HEX:
                continue
            stray.setdefault(low, []).append(where)
check("no off-palette colour in any tool snippet", not stray,
      stray or "none")
check("no three-digit colour, which _recolor cannot swap", not short,
      short or "none")
# The twin of the three-digit hole, and it was in THIS suite as much as
# in _recolor: every literal was lower-cased before TOKEN_HEX was
# asked, so an UPPERCASE token literal read as "a token, fine" and
# could never be swapped. _COLOR_RE is #[0-9a-f]{6} with no re.I.
# Nothing in the tree is uppercase today, so this is a trap and not a
# live bug -- which is exactly why the guard should hold it rather
# than a comment. Raised by server-71 after my own measurement showed
# tint_js leaving #FFFFFF alone on every theme.
caps = {}
for name in present:
    for key, src in getattr(B, name).items():
        for lit in HEX.findall(src):
            if lit != lit.lower():
                caps.setdefault(lit, []).append("%s.%s" % (name, key))
check("every colour literal is lower case, since _recolor is not",
      not caps, caps or "none")
# The other spelling. HEX cannot see rgba() at all, and _recolor judges
# those by RGB TRIPLE against the tokens' own triples (its by_rgb), so
# that is how they are judged here. This tree is clean by luck -- the
# islands all happen to be rgba(13,13,18,...), which is surface -- but
# mac had five live ones: they filtered porting hunks on #11111b alone,
# so rgba(17,17,27,...) survived in three overlays and stayed
# off-palette on all 116 themes WITH the dispatcher fix in place.
# Raised by mac via server-71; the three below were measured here
# first, not taken on the report.
RGBFN = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*"
                   r"(?:,([^)]*))?\)")
TOKEN_RGB = {B._hex_rgb(v) for v in B.THEME_SOURCE.values()
             if isinstance(v, str) and v.startswith("#")}
# Each exemption matches a branch _recolor really has, not a shrug.
RGB_ALLOWED = {
    ((20, 20, 20), "PAGE_TOOLS.totop"):
        "the back-to-top scrim. Alpha .75 is under _recolor's 0.8 "
        "floor, so it is left alone BY DESIGN -- and measured here, "
        "theming the ink above it alone fails 4.5:1 on 30 of 116",
    ((128, 128, 128), "PAGE_TOOLS.totop"):
        "a neutral hairline: grey on purpose, so it reads on whatever "
        "the SITE behind it happens to be",
    ((128, 128, 128), "DEV_TOOLS.csv"):
        "the same hairline in the CSV grid",
}
rgbs, rgb_open = {}, []
for name in present:
    for key, src in getattr(B, name).items():
        if not isinstance(src, str):
            continue
        for found in RGBFN.finditer(src):
            rgb = tuple(int(x) for x in found.groups()[:3])
            where = "%s.%s" % (name, key)
            # a black with an alpha is a shadow or a scrim; _recolor
            # leaves those under .8 and that is its own tested branch
            if rgb == (0, 0, 0):
                continue
            if (rgb, where) in RGB_ALLOWED:
                rgb_open.append((rgb, where))
                continue
            if rgb in TOKEN_RGB:
                continue
            rgbs.setdefault(found.group(0), []).append(where)
check("no off-palette rgb() in any tool snippet", not rgbs,
      rgbs or "none")
rgb_stale = sorted(set(RGB_ALLOWED) - set(rgb_open))
check("...and no rgb exemption is left explaining a literal that is gone",
      not rgb_stale, rgb_stale or "none")
check("no open item has been left out of PENDING_AT",
      len(set(open_items)) == len(PENDING_AT),
      "%d of %d named" % (len(set(open_items)), len(PENDING_AT)))
stale = sorted(set(PENDING_AT) - set(open_items))
check("...and no reason is left explaining a literal that is gone",
      not stale, stale or "none")
print("      %d open item%s, awaiting a product decision:"
      % (len(set(open_items)), "" if len(set(open_items)) == 1 else "s"))
for where, low in sorted(set(open_items)):
    print("        %-24s %-9s %s"
          % (where, low, PENDING_AT[(where, low)].split(".")[0]))

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
# Counted as a SET, not a list: DEV_TOOLS.update(DEV_TOOLS_PAGE)
# means the wider sweep sees one source string under two names, so a
# length of 1 here was measuring the shape of the table list and not
# the thing this check names.
holder = sorted({s for _n, _k, s in snippets if "rgba(0, 0, 0, 0)" in s})
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

print("(6) every painting table's dispatcher calls tint_js")
# The check that was missing, and the reason this file went green over
# a fix that did not reach the page. Check (2) reads the snippets and
# check (3) tints them in isolation; NEITHER asks whether the thing
# that runs them calls tint_js. dev_tool did not, and
# DEV_TOOLS.update(DEV_TOOLS_PAGE) makes it the only route to five of
# the overlays -- so their literals sat on tokens with the swap never
# applied. Correct on mocha, whose surface IS #0d0d12, and unchanged
# on all 28 light themes. Shape contributed by browser-windows-9a,
# who read the computed background out of the page.
#
# Two outcomes, not one, because they are different facts:
#   a table whose painters use TOKEN literals and is dispatched
#   without a tint is a BUG -- the swap exists and is being skipped.
#   a table whose painters use only non-token literals is dispatched
#   cold harmlessly: there is nothing for _recolor to swap. Adding
#   tint_js there would make this check green and change no pixel,
#   which is the shape this whole file exists to refuse. So it is
#   REPORTED and does not fail, and the fix is to normalise the
#   literals -- a decision per site, not a mechanical one.
COLOUR = re.compile(r"#[0-9a-fA-F]{3,6}\b|rgba?\(")
tables = sorted(n for n in dir(B)
                if "TOOLS" in n and isinstance(getattr(B, n, None), dict))
cold, harmless = [], []
for name in tables:
    table = getattr(B, name)
    painters = [k for k, v in table.items() if COLOUR.search(str(v))]
    if not painters:
        continue
    # `source =` and `code =` are both in use; a table with neither is
    # merged into another one's dispatcher (DEV_TOOLS_PAGE is) and is
    # covered wherever that one is.
    hit = re.search(r"(?:source|code) = %s\.get\(name\)" % name, SRC)
    if not hit:
        continue
    if "tint_js(" in SRC[hit.start():hit.start() + 1400]:
        continue
    swappable = any(lit.lower() in TOKEN_HEX
                    for k in painters
                    for lit in HEX.findall(str(table[k])))
    (cold if swappable else harmless).append(name)
check("no table with token literals is dispatched without a tint",
      not cold, cold or "none")
print("      (dispatched cold, nothing to swap: %s)"
      % (", ".join(harmless) or "none"))

# The three-digit literals left in on purpose, each with the reason and
# the measurement behind it. A short literal is invisible to _recolor
# (its _COLOR_RE is six-digit only), so leaving one is a decision that
# has to be written down, not a spelling.
KEPT_SHORT = {
    ("MEDIA_TOOLS2", "winfull"):
        "the letterbox behind a fullscreen video. Black is what a video "
        "is surrounded by; a light theme's background around a film is "
        "the bug, not the fix",
    ("PLAY_TOOLS", "twitchgrid"):
        "the same, for the multi-stream grid",
    ("READER_TOOLS", "hints"):
        "a highlighter pen: black ink on #ffd866 yellow. The yellow is "
        "not a token and must not be, so the ink beside it cannot move "
        "either. A product call, not ours",
    ("PAGE_TOOLS", "totop"):
        "its fill is rgba(20,20,20,.75) -- alpha under 0.8, which "
        "_recolor leaves alone BY DESIGN as a scrim. So only the ink "
        "could move, and bright-on-that-scrim fails 4.5:1 on 30 of the "
        "116 themes, every one of them light. Normalising the ink alone "
        "would make it worse, not better",
}
still_short = {}
# every painting table, not just the seven in TOOLS: the short
# literals that were left in on purpose live in MEDIA_TOOLS,
# PAGE_TOOLS and READER_TOOLS, which that tuple does not name
ALL_TABLES = [n for n in dir(B)
              if "TOOLS" in n and isinstance(getattr(B, n), dict)]
for name in ALL_TABLES:
    for key, src in getattr(B, name).items():
        if isinstance(src, str) and SHORT_HEX.search(src):
            still_short[(name, key)] = sorted(set(SHORT_HEX.findall(src)))
undocumented = {k: v for k, v in still_short.items() if k not in KEPT_SHORT}
check("every short literal left in a snippet has a written reason",
      not undocumented, undocumented or "none")
gone = [k for k in KEPT_SHORT if k not in still_short]
check("...and every written reason still has a literal to explain",
      not gone, gone or "%d/%d" % (len(KEPT_SHORT), len(KEPT_SHORT)))
# the two that WERE normalised, checked where it matters: the pair has
# to invert together, or a chip goes unreadable on half the themes
for name, key in (("MEDIA_TOOLS", "wheelvolume"), ("PAGE_TOOLS", "edit")):
    table = getattr(B, name, {})
    if key not in table:
        check("%s.%s is in the tree" % (name, key), False, "missing")
        continue
    pairs = [(B.theme_palette(th["key"])["bright"],
              B.theme_palette(th["key"])["bg"]) for th in B.THEMES]
    worst = min(B.contrast_ratio(ink, fill) for ink, fill in pairs)
    check("%s.%s reads on every theme" % (name, key), worst >= 4.5,
          "worst %.2f:1 of 116" % worst)

# And the other direction, which nothing asserted: every tint_js call
# site has to BE one of those dispatchers. It holds in this tree -- all
# of them are -- and it holds only until someone adds a tenth site,
# which is why it is written down. Proposed by browser-windows-9a after
# they found what tinting the wrong thing does; see section (7).
# Parsed, not grepped: the question is which function the call is in.
TREE = ast.parse(SRC)
TABLE_GET = re.compile(r"[A-Z_]*TOOLS[A-Z0-9_]*\.get\(")
sites, bad_sites = 0, []
for func in ast.walk(TREE):
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if func.name == "tint_js":
        continue
    calls = [c for c in ast.walk(func)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
             and c.func.id == "tint_js"]
    if not calls:
        continue
    sites += len(calls)
    body = ast.unparse(func)
    if not TABLE_GET.search(body):
        bad_sites.append("%s:%d" % (func.name, calls[0].lineno))
check("every tint_js call site is a painting-table dispatcher",
      not bad_sites, bad_sites or "all %d of them" % sites)

print("(7) the injected snippets take their colours from the payload")
# A different question from (2), and the one (2) cannot ask. The tool
# dicts go through tint_js, so for those "is it a token" is the whole
# test. NAV_JS and A11Y_JS are injected as scripts and get their
# colours from a payload the browser builds -- so a literal there can
# be a perfectly good token and still never move, because nothing
# tints it. What matters is whether the value is REACHED through the
# payload at all.
#
# Found this way on 2026-10-29: the alt-drag link box in NAV_JS drew
# its border from W.accent and filled with a hardcoded
# rgba(137,180,250,0.12) on the line below. Catppuccin blue at 12%, a
# real token's colour, wrong on 115 of the 116 themes -- the outline
# moved with the theme and the fill did not.
INJECTED = ("NAV_JS", "A11Y_JS", "THEME_JS")
# These must NEVER be handed to tint_js, and the reasons have nothing
# to do with palettes -- which matters, because "they are injected, not
# dispatched" is a weak argument and these are three concrete harms.
# Measured on this tree by diffing each blob against tint_js(blob,
# "latte"), after browser-windows-9a swept 20 blobs on theirs:
#
#   THEME_JS  the swap table is keyed BY the THEME_SOURCE literals, so
#             tinting rewrites the LOOKUP KEY, not a colour:
#                 col = t.map["#000000"]  ->  t.map["#DCE0E8"]
#             which is undefined, and the in-page swap stops working
#             for the bg token on every one of our own pages. The
#             comparison above it, `lit !== "#000000"`, inverts its
#             meaning in the same edit.
#   A11Y_JS   the contrast rescue picks its ink from a MEASURED
#             luminance; theming either half undoes the fix.
#   all three the fallbacks are rewritten, not just the paints:
#                 (W.accentSoft || "rgba(137,180,250,0.12)")
#                 (W.accentSoft || "rgb(27 90 217 / 0.12)")
#             which freezes the fallback to whichever theme was live
#             when the script was injected. A fallback frozen to one
#             theme is exactly the bug a fallback exists to prevent.
#             Nine lines in A11Y_JS and six in NAV_JS.
# A colour reached as `(W.something || "<literal>")` is themed: the
# literal is only the fallback for a payload that did not arrive.
FALLBACK = re.compile(r'W\.[A-Za-z_]+\s*(?:\|\|\s*W\.[A-Za-z_]+\s*)*'
                      r'\|\|\s*"(?:#[0-9a-fA-F]{3,8}|rgba?\([^")]*\))"')
ANY_COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([0-9.,\s]*\)')
# Each of these is a decision, with the reason it is not themed.
# Keyed by (blob, literal), not by literal alone. The global version
# of this list is the mistake section (2) already had to fix: a reason
# written for one place silently excuses the same bytes everywhere
# else. #000000 appears in two of these blobs for two unrelated
# reasons, and only one of them is about ink.
NOT_THEMED = {
    ("NAV_JS", "rgba(0,0,0,0.92)"):
        "the image lightbox backdrop, drawn over a SITE: a dim, not a "
        "surface. Lightening it on a light theme is the bug, not the fix",
    ("A11Y_JS", "rgba(0, 0, 0, 0)"):
        "the transparent value the contrast pass COMPARES against while "
        "walking up for a real background. Never painted",
    ("A11Y_JS", "rgb(255, 255, 255)"):
        "what an unstyled page's background is taken to be when nothing "
        "up the tree sets one. A measurement default, not a colour we paint",
    ("A11Y_JS", "#000000"):
        "half of a computed ink pair, picked against a MEASURED "
        "luminance so low-contrast text on a site becomes readable. A "
        "theme colour here would undo the fix",
    ("A11Y_JS", "#ffffff"):
        "the other half of that pair, same reason",
    ("THEME_JS", "#000000"):
        "not ink at all: this is the KEY the in-page swap table is "
        "looked up by, and the literal it compares against. Theming it "
        "rewrites the key to one the table does not hold, so the swap "
        "stops working rather than coming out the wrong colour",
}
missing = [n for n in INJECTED if not hasattr(B, n)]
check("the injected snippets are there", not missing,
      missing or "%d/%d" % (len(INJECTED), len(INJECTED)))
loose_js = {}
covered = 0
for name in [n for n in INJECTED if hasattr(B, n)]:
    body = getattr(B, name)
    covered += len(FALLBACK.findall(body))
    blanked = FALLBACK.sub(lambda m: " " * len(m.group(0)), body)
    for found in ANY_COLOUR.finditer(blanked):
        lit = found.group(0)
        if (name, lit) in NOT_THEMED:
            continue
        line = body.count("\n", 0, found.start()) + 1
        loose_js.setdefault(lit, []).append("%s+%d" % (name, line))
check("there are payload fallbacks to find (the fixture)", covered > 10,
      covered)
check("every colour is a payload fallback or a named exception",
      not loose_js, loose_js or "none")
seen_js = set()
for name in [n for n in INJECTED if hasattr(B, n)]:
    body = getattr(B, name)
    blanked = FALLBACK.sub(lambda m: " " * len(m.group(0)), body)
    for found in ANY_COLOUR.finditer(blanked):
        if (name, found.group(0)) in NOT_THEMED:
            seen_js.add((name, found.group(0)))
js_stale = sorted(set(NOT_THEMED) - seen_js)
check("...and no reason is left explaining a literal that is gone",
      not js_stale, js_stale or "all %d still there" % len(NOT_THEMED))

# The class behind the two findings above, and the only shape a
# fallback can take without being one theme's value frozen in: where
# the fallback literal is a token's colour, it has to be THAT key's
# token. Otherwise the literal is a record of an intent the code does
# not carry out -- and because the payload only ever sends a few keys,
# the fallback never runs, so nothing on screen ever contradicts it.
#
# Found on 2026-10-29: the find-in-page marks on the scroll rail asked
# for W.accent and fell back to yellow's colour, and the outline that
# marks an image with no alt text asked for W.accent and fell back to
# red's. Both drew in accent, which is also the link colour and the
# focus ring on most themes, so a search hit and an accessibility
# problem both looked like links. Raised by browser-windows-9a.
#
# The LAST key in the chain is the one the literal belongs to:
# (W.caretColour || W.accent || "#89b4fa") is correct, and reading the
# first key instead reports it as a mismatch. That false positive is
# why this is written as a chain and not as a single name.
PAIR = re.compile(r'(?:W\.[A-Za-z_]+\s*\|\|\s*)*W\.([A-Za-z_]+)\s*'
                  r'\|\|\s*"(#[0-9a-fA-F]{3,8}|rgba?\([^")]*\))"')
BY_HEX = {v.lower(): k for k, v in B.THEME_SOURCE.items()
          if isinstance(v, str) and v.startswith("#")}
wrong_token, pairs = [], 0
for name in [n for n in INJECTED if hasattr(B, n)]:
    body = getattr(B, name)
    for found in PAIR.finditer(body):
        pairs += 1
        key, lit = found.group(1), found.group(2).lower()
        if len(lit) == 4:          # expand #abc before asking
            lit = "#" + "".join(c + c for c in lit[1:])
        owner = BY_HEX.get(lit)
        if owner and owner != key:
            wrong_token.append(
                "%s+%d: W.%s falls back to %s, which is %s"
                % (name, body.count("\n", 0, found.start()) + 1,
                   key, found.group(2), owner))
check("there are fallback pairs to check (the fixture)", pairs > 10, pairs)
check("every fallback literal is its own key's token",
      not wrong_token, wrong_token or "all %d agree" % pairs)

# and the one that was wrong, checked where it is decided rather than
# in the snippet: the fill has to follow the accent, and has to come
# out byte for byte on the default theme like everything else here.
soft = {}
for key in (B.DEFAULT_THEME, "latte"):
    if key not in [t["key"] for t in B.THEMES]:
        continue
    soft[key] = "rgba(%d, %d, %d, 0.12)" % B._hex_rgb(
        B.theme_palette(key)["accent"])
check("the soft accent is byte for byte the old literal on the default "
      "theme", soft.get(B.DEFAULT_THEME) == "rgba(137, 180, 250, 0.12)",
      soft.get(B.DEFAULT_THEME))
check("...and a different colour on a light theme",
      soft.get("latte") != soft.get(B.DEFAULT_THEME), soft.get("latte"))
wrong = [t["key"] for t in B.THEMES
         if B.theme_palette(t["key"])["accent"].lower() != "#89b4fa"]
check("the hardcoded fill was wrong on more than half the themes",
      len(wrong) > len(B.THEMES) // 2,
      "%d of %d" % (len(wrong), len(B.THEMES)))
check("the snippet reads it from the payload now",
      "W.accentSoft" in B.NAV_JS)

print("")
print("FAILED %d" % len(fails) if fails else "all ok")
for what in fails:
    print("  - " + what)
sys.exit(1 if fails else 0)
