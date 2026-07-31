#!/usr/bin/env python3
"""Is every theme readable? Not a matter of taste — a number.

WCAG 2.1 contrast ratios for the pairs the browser's own pages and its
Qt sheet actually produce, computed for all of the palettes. Text wants
4.5:1; big text, a glyph and the edge of a control want 3:1.

Three parts:

  (1) a written-down table of the pairs that only exist in combination
      — quiet text on a raised island, a placeholder inside an input,
      the label on an accent-coloured button. No stylesheet ever says
      those two colours in the same rule, so nothing mechanical can
      find them; they are read off the pages by hand and listed here.

  (2) a mechanical sweep of every rule in every page and in the Qt
      sheet that names a colour AND a background, alpha composited on
      what the thing actually sits on.

  (3) the colours that are not in the palette at all: a hex literal the
      engine does not know, or a colour written into a JavaScript
      string, where no repainting can ever reach it.

  (6) every one of those measures a colour against a BACKGROUND, and
      that is not the whole of readability. Two colours that both clear
      4.5:1 against the same background can be the same colour as each
      other, and a floor is exactly the thing that arranges it: raise
      five rungs until each one clears the floor and all five stop on
      the floor, together. Then the hint under a field, a quiet caption
      and a sentence are one colour, and a menu entry that cannot be
      picked looks like one that can. So the ladder is measured against
      itself as well, rung by rung, and the pairs the stylesheets put
      side by side are measured against each other.

Catppuccin Mocha is the browser as it was drawn and is not the theme
engine's to correct: where Mocha itself sits under a target, the target
for every other palette is Mocha's own number, so a theme may be as
quiet as the original but never quieter. Part (1) prints Mocha's own
shortfalls at the end, by name, so they stay documented rather than
forgotten.

Readability is bought with saturation. The walk that makes a colour
readable keeps its hue exactly and pays in how vivid it is, which is
free for a palette with room to move and expensive for one that is a
fixed set of colours: Game Boy is four greens and the Commodore 64 is
sixteen fixed inks, and their derived tokens end up washed against
those. Part (5) prints what each theme paid, so the bill is on the
table rather than hidden in the palette.

Run it on its own for the whole table:  python3 test_contrast.py -v
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402

VERBOSE = "-v" in sys.argv or "--table" in sys.argv
FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    print(("  ok   " if cond else "  FAIL ") + name
          + ("  <%s>" % detail if detail else ""))
    if not cond:
        FAILS += 1


# what a pair is for, and what WCAG asks of it
BODY, LARGE, UI, OFF = "body", "large", "glyph", "disabled"
TARGET = {BODY: 4.5, LARGE: 3.0, UI: 3.0, OFF: 3.0}

# the backgrounds text is laid on, and what each one is in the pages:
#   bg          the window and the page behind it
#   crust       the panel behind a password's detail
#   mantle      an input on the passwords page
#   surface     an island, a card, a section
#   surfaceAlt  a raised row inside an island
#   hover       an island under the mouse
SURFACES = ("bg", "crust", "mantle", "surface", "surfaceAlt", "hover")

PAIRS = []


def add(fg, bg, role, why):
    PAIRS.append((fg, bg, role, why))


for s in SURFACES:
    add("text", s, BODY, "what you read")
    add("subtext", s, BODY, "secondary text")
    add("overlay", s, BODY, "quiet text, hints, placeholders")
    add("bright", s, LARGE, "a heading, the clock")
for s in ("bg", "surface"):
    add("subtext1", s, BODY, "a label one step up from quiet")
    add("dim", s, BODY, "the hint under a dialog field")
    add("accent", s, BODY, "a link, an accent label")
    add("green", s, BODY, "it worked")
    add("red", s, BODY, "it did not")
    add("yellow", s, BODY, "a warning line")
    add("peach", s, BODY, "a flagged password")
    add("muted", s, OFF, "a disabled thing")
    add("sunken", s, UI, "a track, a rule, an empty bar")
# a colour used as a fill, with the page's own background as the label
for fill in ("accent", "accentLt", "green", "greenLt", "red", "yellow",
             "peach", "text", "bright", "subtext"):
    add("bg", fill, BODY,
        "text inside a selection" if fill == "text"
        else "the label on a %s fill" % fill)
# the edge of a control: a hairline is the overlay colour at .4
add("overlay@0.4", "bg", UI, "a hairline on the page")
add("overlay@0.4", "surface", UI, "a hairline on an island")
add("overlay@0.45", "bg", UI, "the edge of the search box")
# and what a focus ring and a selection are painted with
add("subtext", "bg", UI, "the focus ring on the start page's search box")
add("text", "bg", UI, "the focus ring in settings")
add("text", "surface", UI, "the focus ring on a card")


def resolve(token, pal, over=None):
    """A token, possibly carrying an alpha, flattened onto `over`."""
    if "@" in token:
        name, alpha = token.split("@")
        return B.flatten(pal[name], pal[over], float(alpha))
    return pal[token]


def audit(key):
    pal = B.theme_palette(key)
    return [(fg, bg, role, why, B.contrast_ratio(resolve(fg, pal, bg),
                                                 pal[bg]))
            for fg, bg, role, why in PAIRS]


# Mocha is the reference: nothing may be quieter than the browser as it
# was drawn, and where Mocha clears the target the target stands.
REFERENCE = {(fg, bg): r for fg, bg, role, why, r in audit("mocha")}


def floor_for(fg, bg, role):
    return min(TARGET[role], round(REFERENCE[(fg, bg)], 2))


# ------------------------------------------------- (1) the pair table
print("\n(1) every pair every palette produces")
failed = []
passing = []
for t in B.THEMES:
    key = t["key"]
    rows = audit(key)
    bad = [r for r in rows if r[4] + 5e-3 < floor_for(r[0], r[1], r[2])]
    if bad:
        failed.append((key, t["name"], bad))
    else:
        low = min(rows, key=lambda x: x[4] / floor_for(x[0], x[1], x[2]))
        passing.append((low[4] / floor_for(low[0], low[1], low[2]), key, low))
    if VERBOSE:
        print("\n  %-22s %s" % (key, t["name"]))
        for fg, bg, role, why, r in rows:
            need = floor_for(fg, bg, role)
            print("    %-14s on %-11s %-9s %6.2f  need %4.2f  %s"
                  % (fg, bg, role, r, need,
                     "ok" if r + 5e-3 >= need else "FAIL"))

print("  %d themes x %d pairs = %d ratios"
      % (len(B.THEMES), len(PAIRS), len(B.THEMES) * len(PAIRS)))
if failed:
    print("\n  worst offenders:")
    for key, name, bad in sorted(failed,
                                 key=lambda x: min(r for *_, r in x[2]))[:25]:
        fg, bg, role, why, r = min(bad, key=lambda x: x[4])
        print("    %-22s %-26s %-12s on %-11s %5.2f  need %4.2f  (%s)"
              % (key, name, fg, bg, r, floor_for(fg, bg, role), why))
        for fg, bg, role, why, r in sorted(bad, key=lambda x: x[4])[1:6]:
            print("      %-12s on %-11s %5.2f  need %4.2f"
                  % (fg, bg, r, floor_for(fg, bg, role)))
check("no palette is quieter than the target, or than Mocha where Mocha "
      "is quieter", not failed,
      "%d themes short" % len(failed) if failed else "")

print("\n  the five closest calls that still clear it:")
for score, key, low in sorted(passing)[:5]:
    fg, bg, role, why, r = low
    print("    %-22s %-12s on %-11s %5.2f  need %4.2f"
          % (key, fg, bg, r, floor_for(fg, bg, role)))

# and the absolute view: how many pairs clear WCAG outright, and which
# of Mocha's own do not
print("\n  against WCAG outright, with nothing forgiven:")
short = 0
total = 0
for t in B.THEMES:
    for fg, bg, role, why, r in audit(t["key"]):
        total += 1
        if r + 5e-3 < TARGET[role]:
            short += 1
print("    %d of %d pairs clear the full target (%.1f%%)"
      % (total - short, total, 100.0 * (total - short) / total))
print("    Mocha's own shortfalls, kept on purpose — this palette is the "
      "browser as it was drawn:")
for fg, bg, role, why, r in audit("mocha"):
    if r + 5e-3 < TARGET[role]:
        print("      %-12s on %-11s %5.2f  target %4.2f   %s"
              % (fg, bg, r, TARGET[role], why))


# ------------------------------------------ (2) the mechanical sweep
print("\n(2) every rule that names a colour and a background")
NAME = {v: k for k, v in B.THEME_SOURCE.items()}
NAME_RGB = {B._hex_rgb(v): k for k, v in B.THEME_SOURCE.items()}

# A translucent fill is flattened onto what the thing actually sits on:
# a page's own elements sit on the page, and the chrome's sit on a tab
# or a toolbar, which is an island.
UNDER = {"browser.py": "surface"}

# The handful of rules whose foreground is a glyph and not a sentence:
# WCAG asks 3:1 of those, not 4.5.
GLYPH = ("QToolButton#tabclose",)


def token_of(value):
    m = re.search(r"#[0-9a-f]{6}\b|rgba?\([^)]*\)", value)
    if not m:
        return None
    lit = m.group(0)
    if lit.startswith("#"):
        return (NAME.get(lit), 1.0)
    inner = lit[lit.index("(") + 1:-1].replace("/", ",").split(",")
    try:
        rgb = tuple(int(float(p)) for p in inner[:3])
    except ValueError:
        return None
    alpha = 1.0
    if len(inner) > 3:
        try:
            alpha = float(inner[3])
        except ValueError:
            return None
        if alpha > 1:
            alpha /= 255.0
    if rgb == (0, 0, 0):
        return ("bg", alpha)
    return (NAME_RGB.get(rgb), alpha)


def sheets():
    for f in ("start.html", "settings.html", "history.html",
              "downloads.html", "bookmarks.html", "passwords.html"):
        text = (HERE / f).read_text(encoding="utf-8")
        for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S):
            yield f, m.group(1)
    yield "browser.py", B.STYLE


RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
combos = []
seen = set()
for name, css in sheets():
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in RULE.finditer(css):
        sel = re.sub(r"\s+", " ", m.group(1).strip())[:52]
        f = b = None
        for decl in m.group(2).split(";"):
            if ":" not in decl:
                continue
            prop, val = decl.split(":", 1)
            got = token_of(val)
            if not got or not got[0]:
                continue
            if prop.strip().lower() == "color":
                f = got
            elif prop.strip().lower() in ("background", "background-color"):
                b = got
        if not (f and b):
            continue
        under = UNDER.get(name, "bg")
        role = UI if any(g in sel for g in GLYPH) else BODY
        key = (f, b, under, role)
        if key in seen:
            continue
        seen.add(key)
        combos.append((name, sel, f, b, under, role))
print("  %d distinct colour-on-colour rules" % len(combos))


def rule_ratio(pal, f, b, under):
    base = B.flatten(pal[b[0]], pal[under], b[1])
    return B.contrast_ratio(B.flatten(pal[f[0]], base, f[1]), base)


mocha = B.theme_palette("mocha")
bad2 = []
for t in B.THEMES:
    pal = B.theme_palette(t["key"])
    for name, sel, f, b, under, role in combos:
        r = rule_ratio(pal, f, b, under)
        need = min(TARGET[role], round(rule_ratio(mocha, f, b, under), 2))
        if r + 5e-3 < need:
            bad2.append((t["key"], name, sel, r, need))
if bad2:
    print("  worst:")
    for row in sorted(bad2, key=lambda x: x[3])[:20]:
        print("    %-20s %-14s %-46s %5.2f need %4.2f"
              % (row[0], row[1], row[2], row[3], row[4]))
check("and every one of them is readable in every theme", not bad2,
      "%d rule/theme pairs short" % len(bad2) if bad2 else "")


# ---------------------------------------- (3) nothing outside the map
print("\n(3) no colour escapes the palette")
lit = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")
known = set(B.THEME_SOURCE.values())
known_rgb = {B._hex_rgb(v) for v in known}
PAGES = ("start.html", "settings.html", "history.html", "downloads.html",
         "bookmarks.html", "passwords.html")
stray = []
for f in PAGES:
    text = (HERE / f).read_text(encoding="utf-8")
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S):
        for c in lit.finditer(m.group(1)):
            v = c.group(0)
            if v.startswith("#"):
                if len(v) == 7 and v == v.lower() and v in known:
                    continue
            else:
                inner = v[v.index("(") + 1:-1].replace("/", ",").split(",")
                try:
                    rgb = tuple(int(float(p)) for p in inner[:3])
                except ValueError:
                    continue
                if rgb == (0, 0, 0) or rgb in known_rgb:
                    continue
            stray.append("%s: %s" % (f, v))
check("every colour in a page's stylesheet is a token the engine knows",
      not stray, ", ".join(sorted(set(stray))[:8]))

# A colour written into a JavaScript string is never repainted: those
# read the palette out of the custom properties instead.
jsstray = []
for f in PAGES:
    text = (HERE / f).read_text(encoding="utf-8")
    masked = list(text)
    for m in re.finditer(r"<style[^>]*>.*?</style>", text, re.S):
        for i in range(m.start(), m.end()):
            if masked[i] != "\n":
                masked[i] = " "
    for m in re.finditer(r"[\"']#[0-9a-fA-F]{3,8}[\"']", "".join(masked)):
        jsstray.append("%s: %s" % (f, m.group(0)))
check("and no page hands the browser a colour of its own in JavaScript",
      not jsstray, ", ".join(sorted(set(jsstray))[:8]))

# The Qt sheet is painted by substitution too: nothing in it may be a
# literal the substitution table has never heard of.
qt = []
for c in lit.finditer(B.theme_style("mocha")):
    v = c.group(0)
    if v.startswith("#"):
        if len(v) == 7 and v == v.lower() and v in known:
            continue
    else:
        inner = v[v.index("(") + 1:-1].replace("/", ",").split(",")
        try:
            rgb = tuple(int(float(p)) for p in inner[:3])
        except ValueError:
            continue
        if rgb == (0, 0, 0) or rgb in known_rgb:
            continue
    qt.append(v)
check("and the Qt sheet has none either", not qt, ", ".join(sorted(set(qt))))

# A pattern is a background. It never lies over an input, a button or a
# line of text, so no theme's own CSS may put one on top of the page.
print("\n(4) a texture is behind the page, never over it")
over = []
for t in B.THEMES:
    css = t.get("css", "")
    for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        sel, body = m.group(1), m.group(2)
        if "::after" not in sel and "::before" not in sel:
            continue
        if "gradient(" in body and "position: fixed" in body:
            over.append("%s %s" % (t["key"], sel.strip()[:40]))
check("no theme lays a pattern over the page with a fixed overlay",
      not over, ", ".join(over[:6]))

# --------------------------------- (6) the ladder measured against itself
# A background is not the only thing a colour is read against. These
# pairs are two foregrounds sitting side by side on the same surface,
# where the question is whether you can tell them apart at all.
print("\n(6) every rung stands apart from the one below it")

CHAIN = list(B._THEME_RAMP) + ["text"]
# What Mocha puts between two neighbouring rungs, which is the rhythm
# the browser was drawn with. Nothing may be tighter than the engine's
# own step, and nothing may be tighter than Mocha where Mocha is
# tighter - the same bargain the pair table strikes.
STEP = B._RUNG_STEP
MOCHA = B.theme_palette("mocha")

tight = []
worst = []
for t in B.THEMES:
    pal = B.theme_palette(t["key"])
    for a, b in zip(CHAIN, CHAIN[1:]):
        r = B.contrast_ratio(pal[a], pal[b])
        need = min(STEP, round(B.contrast_ratio(MOCHA[a], MOCHA[b]), 3))
        worst.append((r, t["key"], a, b, need))
        if r + 5e-3 < need:
            tight.append((r, t["key"], a, b, need))
        if VERBOSE:
            print("    %-22s %-9s/%-9s %6.3f  need %5.3f  %s"
                  % (t["key"], a, b, r, need,
                     "ok" if r + 5e-3 >= need else "FAIL"))
print("  %d themes x %d neighbouring pairs = %d steps"
      % (len(B.THEMES), len(CHAIN) - 1, len(worst)))
if tight:
    print("  the rungs that landed on top of each other:")
    for r, key, a, b, need in sorted(tight)[:20]:
        pal = B.theme_palette(key)
        print("    %-22s %-9s %s / %-9s %s  %6.3f  need %5.3f"
              % (key, a, pal[a], b, pal[b], r, need))
check("no rung of the ladder collapses into the one below it", not tight,
      "%d steps too tight" % len(tight) if tight else "")
print("  the five tightest that still stand apart:")
for r, key, a, b, need in sorted(worst)[:5]:
    print("    %-22s %-9s/%-9s %6.3f  need %5.3f" % (key, a, b, r, need))

# The one pair that is a foreground on a foreground in the Qt sheet
# rather than a step of the ladder: a menu entry that cannot be picked
# next to one that can. This is the defect the ladder's step exists to
# stop coming back, so it is written down by name.
# The pairs the pages and the Qt sheet put beside each other rather
# than stacking. Two rungs n apart are n steps apart, so that is what
# is asked of them; the first line is the defect this whole part exists
# to stop coming back, written down by name.
print("\n  and the pairs that are read side by side, not stacked:")
SIDE = [("subtext", "text", "a disabled menu entry beside an enabled one"),
        ("overlay", "text", "a placeholder beside what you typed"),
        ("dim", "text", "the hint under a field beside its label"),
        ("subtext", "subtext1", "two quiet labels one rung apart"),
        ("muted", "text", "a switched-off row beside a live one")]
sidebad = []
for t in B.THEMES:
    pal = B.theme_palette(t["key"])
    for a, b, why in SIDE:
        r = B.contrast_ratio(pal[a], pal[b])
        apart = abs(CHAIN.index(a) - CHAIN.index(b))
        need = min(STEP ** apart, round(B.contrast_ratio(MOCHA[a],
                                                         MOCHA[b]), 3))
        if r + 5e-3 < need:
            sidebad.append((r, t["key"], a, b, need, why))
if sidebad:
    for r, key, a, b, need, why in sorted(sidebad)[:20]:
        pal = B.theme_palette(key)
        print("    %-22s %-9s %s / %-9s %s  %6.3f  need %5.3f  (%s)"
              % (key, a, pal[a], b, pal[b], r, need, why))
for a, b, why in SIDE:
    low = min((B.contrast_ratio(B.theme_palette(t["key"])[a],
                                B.theme_palette(t["key"])[b]), t["key"])
              for t in B.THEMES)
    apart = abs(CHAIN.index(a) - CHAIN.index(b))
    print("    %-9s vs %-9s tightest %6.3f in %-18s need %5.3f  %s"
          % (a, b, low[0], low[1],
             min(STEP ** apart, round(B.contrast_ratio(MOCHA[a], MOCHA[b]),
                                      3)), why))
check("and the pairs that sit side by side stay told apart", not sidebad,
      "%d pairs too tight" % len(sidebad) if sidebad else "")


# ------------------------------------------- (5) what the ramp cost
# Not a pass or a fail — a receipt. A palette that was already
# readable paid nothing; a palette that is a fixed set of inks paid
# the most, and those are the ones to look at with an eye rather than
# a number.
print("\n(5) what each theme paid in saturation to become readable")


def _hsl_sat(value):
    r, g, b = (c / 255.0 for c in B._hex_rgb(value))
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == lo:
        return 0.0
    light = (hi + lo) / 2.0
    return (hi - lo) / (2.0 - hi - lo if light > 0.5 else hi + lo)


bill = []
for t in B.THEMES:
    seed = {k: v for k, v in t.items()
            if k in B.THEME_SOURCE or k in ("dark", "exact")}
    plain = dict(seed)
    plain["exact"] = True          # the palette as it would be unfitted
    try:
        was = B._expand_palette(dict(t.get("seed") or seed, exact=True))
    except Exception:
        continue
    now = B.theme_palette(t["key"])
    drops = [(_hsl_sat(was[k]) - _hsl_sat(now[k])) * 100
             for k in now if k in was]
    if drops:
        bill.append((max(drops), sum(d for d in drops if d > 0) / len(drops),
                     t["key"], t["name"]))
bill.sort(reverse=True)
print("    the ten that paid most (worst token, then the average):")
for worst, mean, key, name in bill[:10]:
    print("      %-22s %-26s -%5.1f pts  avg -%4.1f"
          % (key, name, worst, mean))
print("    %d of %d themes paid nothing at all"
      % (sum(1 for w, m, k, n in bill if w < 0.05), len(bill)))

print("\n%d checks failed" % FAILS)
sys.exit(1 if FAILS else 0)
