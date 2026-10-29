#!/usr/bin/env python3
"""No page calls a Bridge method that is not there.

test_histrender asks the other half of this question: an element the
script reaches for and dereferences has to exist in the same file. The
pages reach for two kinds of thing, though, and only one of them was
checked. The other is browser.py:

    player.html:203   bridge.playerQueue(...)      unguarded
    player.html:172   bridge.playerSubtitles(...)  guarded

Neither method existed on the Bridge. The unguarded one threw
"bridge.playerQueue is not a function" on **every single open** of the
player, and it looked fine because it was the LAST statement in its
callback -- the two label assignments above it had already run, so the
buttons read correctly and nothing was visibly wrong. Anything added
below that line would have been dead with no symptom at all.

The guarded one was worse in a quieter way: Subtitles is a *button*,
so the page advertised a feature the browser could not do and clicking
it did nothing at all. playerQueue was guarded on 2026-10-29 and
playerSubtitles was given its Bridge method the same day, so the pin
below is down to one entry.

That is the b68049e shape again: an orphan left behind by a design that
moved on, where the only witness is a console nobody reads. Written in
the Windows edition, where the unguarded playerQueue was still live,
and taken upstream because the class of bug is in shared code -- the
nine pages and this file. The guard is this suite, so the next one
fails a run instead of shipping.

Two different verdicts, deliberately:

  unguarded + missing   a throw on open. Fails.
  guarded + missing     no throw, but the page advertises a button that
                        cannot work. Allowed, and PINNED by name below,
                        so an existing gap is tolerated and a NEW one
                        is a failure rather than quietly joining the
                        list.

Static: reads the nine pages and browser.py's AST. No Qt, no browser,
no network, writes nothing. Runs from anywhere.
"""
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE

# Methods the pages call that browser.py does not define, and which are
# guarded so they fail silently rather than throwing. Each one is a
# feature the page offers and the browser cannot do -- a missing Bridge
# method and, for subtitles, a file picker. Named here rather than
# hidden so the list can only shrink on purpose.
KNOWN_GAPS = {
    "playerQueue": "the playlist does not arrive this way any more -- "
                   "open_player injects window.__playerLoad(files)",
}

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def bridge_methods(src):
    """Every method on class Bridge, from the AST rather than a grep:
    `def siteIcons` also matches a method of some other class, and a
    name that merely appears in a comment matches nothing at all."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == "Bridge":
            return {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


CALL = re.compile(r"bridge\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
# `if (bridge.x)`, `if (bridge && bridge.x)`, `bridge.x && bridge.x(...)`,
# `typeof bridge.x === "function"` -- the shapes the pages actually use
# to ask before calling.
def guards(text, name):
    pats = (
        r"if\s*\(\s*bridge\s*&&\s*bridge\.%s\s*\)" % name,
        r"if\s*\(\s*bridge\.%s\s*\)" % name,
        r"bridge\.%s\s*&&" % name,
        r"typeof\s+bridge\.%s\s*===?\s*[\"']function[\"']" % name,
    )
    return any(re.search(p, text) for p in pats)


pages = sorted(REPO.glob("*.html"))
src = (REPO / "browser.py").read_text(encoding="utf-8")
HAVE = bridge_methods(src)

print("(1) the page set and the Bridge are both there")
check("nine shared pages", len(pages) == 9, [p.name for p in pages])
check("the Bridge has its methods", len(HAVE) > 100, len(HAVE))

called = {}
for page in pages:
    text = page.read_text(encoding="utf-8")
    for name in CALL.findall(text):
        called.setdefault(name, []).append((page.name, guards(text, name)))
check("the pages call into it", len(called) > 80, len(called))


print()
print("(2) nothing unguarded calls a method that is not there")
throwers = []
for name, sites in sorted(called.items()):
    if name in HAVE:
        continue
    for page, guarded in sites:
        if not guarded:
            throwers.append("%s calls bridge.%s unguarded" % (page, name))
check("no page throws on a missing Bridge method", not throwers, throwers)

# it has to be able to fail: the real line, as it was before 51ecdbe
sample = "        bridge.playerQueue((json) => {\n"
check("...and an unguarded call is recognised as one",
      not guards(sample, "playerQueue"))
check("...while the guarded form is not",
      guards("if (bridge.playerQueue) {\n  bridge.playerQueue((j) => {",
             "playerQueue"))


print()
print("(3) the methods that are missing but guarded are the known ones")
missing = sorted(n for n in called if n not in HAVE)
new_gaps = [n for n in missing if n not in KNOWN_GAPS]
check("no NEW feature advertised that the browser cannot do", not new_gaps,
      new_gaps)
# and the pin has to stay honest in the other direction too: a name
# listed here that is no longer missing means the feature landed and the
# list should say so.
stale = sorted(n for n in KNOWN_GAPS if n in HAVE or n not in called)
check("...and the pinned list has no entries that are fixed already",
      not stale, stale)
for name in missing:
    where = ", ".join(sorted({p for p, _g in called[name]}))
    print("       known gap: bridge.%s (%s) -- %s"
          % (name, where, KNOWN_GAPS.get(name, "?")))


print()
print("(4) the ones a port has gone without before are present")
# history.html needs these two and nothing static noticed when they were
# absent: the page loaded, threw inside its own callback and drew no
# rows. See a6cb6e3.
for name in ("siteIcons", "historyRows", "uiStrings"):
    check("bridge.%s exists" % name, name in HAVE)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:6])))
else:
    print("all good")
sys.exit(1 if fails else 0)
