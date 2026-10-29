#!/usr/bin/env python3
"""The address bar's marks, driven with the argument type it really gets.

Both of the bar's security marks -- the look-alike-domain badge and
the plain-http "not secure" badge -- existed, were wired to
show_address, and had never once appeared on screen. One line:

    parsed = QUrl(str(url or ""))

`str()` of a QUrl is its REPR, "PyQt6.QtCore.QUrl('https://x/')", and
QUrl() of that parses to an empty everything. Nothing raises. Every
real navigation arrives as a QUrl -- urlChanged emits one, it goes to
_url_changed, then show_address, then update_bar_marks -- so host was
always "" and the else branch hid the mark on every page load. The
only caller that worked was restore_address (Escape in the bar),
because it happens to pass a string.

Found by browser-mac-8f, who drove the bar instead of grepping it.
Reproduced here, then fixed by `as_qurl`.

So this suite never passes a string where the browser passes a QUrl.
That is the whole point: a suite written with strings passes on the
broken tree, which is how this survived.

Also checked, because they are the same mistake and were found with it:

  save_link_target   scheme "" is not https -> Alt+click-to-save and
      "save image as" returned False and saved nothing. Two of its
      three callers hand it an explicit QUrl.
  group_rule_for     host "" -> a tab opened with a QUrl never matched
  session_rule_for   a rule he had written.
  show_address       the tooltip shown when the bar cuts a long
      address off displayed the Python repr.
  update_bar_marks   never called place_bar_extras, so a mark that did
      show kept its default geometry over the lock button and the text
      margin was never recomputed.

WHAT THIS SUITE DOES NOT DO, said plainly. It checks the conditions
the bar's marks are decided by, with both argument types, and it reads
the tree for the idiom that broke them -- it does NOT build a Browser
and look at the widget. Proven by mutation: reverting update_bar_marks
or save_link_target to `QUrl(str(...))` is caught by the STATIC check
at (2), not by a behavioural one, so a *different* way of emptying the
host there would slip past this file. browser-mac-8f's test_barmarks.py
is the one that drives the real window and reads label visibility and
geometry; that is the suite to port if only one of the two travels.

Needs Qt only to import browser.py and QUrl. Opens no window, no
network connection, and writes nothing outside HOME. Run with HOME
pointed at a throwaway directory.
"""
import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--dir", metavar="PATH", default=None,
                help="an edition's folder to check instead of this one")
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


from PyQt6.QtCore import QUrl           # noqa: E402
import browser as B                     # noqa: E402

SRC = (REPO / "browser.py").read_text(encoding="utf-8")

print("(1) as_qurl exists and is honest about both input types")
has = hasattr(B, "as_qurl")
check("as_qurl is there", has)
if not has:
    print("\nFAILED 1\n  - as_qurl is there")
    sys.exit(1)

RAW = "https://cdn.example.com/mods/cool.jar"
for kind, arg in (("string", RAW), ("QUrl", QUrl(RAW))):
    got = B.as_qurl(arg)
    check("as_qurl(%s) keeps the host" % kind,
          got.host() == "cdn.example.com", got.host())
    check("as_qurl(%s) keeps the scheme" % kind,
          got.scheme() == "https", got.scheme())
check("as_qurl copies rather than aliasing", B.as_qurl(QUrl(RAW)) is not None)
mine = QUrl(RAW)
copy = B.as_qurl(mine)
copy.setHost("evil.example")
check("mutating the copy leaves the caller's QUrl alone",
      mine.host() == "cdn.example.com", mine.host())
check("as_qurl(None) is empty, not a crash", B.as_qurl(None).toString() == "")
check("as_qurl('') is empty", B.as_qurl("").host() == "")

print("(2) the raw idiom is gone from the tree")
# the helper's own body and its docstring are the only two allowed
loose = [SRC.count("\n", 0, m.start()) + 1
         for m in re.finditer(r"QUrl\(str\(", SRC)]
body = SRC.index("def as_qurl(url):")
after = SRC.index("def lookalike_warning(host):")
inside = [n for n in loose
          if body < sum(len(x) + 1 for x in SRC.split("\n")[:n - 1]) < after]
check("every QUrl(str(...)) outside as_qurl is gone",
      len(loose) == len(inside), "%d outside" % (len(loose) - len(inside)))

print("(3) lookalike_warning fires on a QUrl, not just a string")
ATTACKS = {"https://xn--pple-43d.com/": "mixed",
           "https://xn--80ak6aa92e.com/": "script",
           "https://xn--pypal-4ve.com/": "mixed"}
for raw, want in ATTACKS.items():
    for kind, arg in (("string", raw), ("QUrl", QUrl(raw))):
        host = B.as_qurl(arg).host()
        got = B.lookalike_warning(host)
        check("%-26s as %-6s warns (%s)" % (raw[8:30], kind, want),
              got.startswith(want + ":"), got or "nothing")
for raw in ("https://apple.com/", "https://paypal.com/",
            "https://www.google.com/", "https://de.wikipedia.org/"):
    for kind, arg in (("string", raw), ("QUrl", QUrl(raw))):
        host = B.as_qurl(arg).host()
        check("%-26s as %-6s stays quiet" % (raw[8:30], kind),
              B.lookalike_warning(host) == "", B.lookalike_warning(host))

print("(4) the http mark's own condition, both argument types")
for raw, want in (("http://example.com/", True),
                  ("https://example.com/", False),
                  ("about:blank", False)):
    for kind, arg in (("string", raw), ("QUrl", QUrl(raw))):
        p = B.as_qurl(arg)
        fires = p.scheme() == "http" and bool(
            B.PasswordVault.normalize_host(p.host()))
        check("%-22s as %-6s not-secure=%s" % (raw, kind, want),
              fires == want, fires)

print("(5) save_link_target's gate opens for a QUrl")
for kind, arg in (("string", RAW), ("QUrl", QUrl(RAW))):
    check("save gate passes for %s" % kind,
          B.as_qurl(arg).scheme() in ("http", "https"),
          B.as_qurl(arg).scheme())

print("(6) the rule lookups see a host")
for kind, arg in (("string", RAW), ("QUrl", QUrl(RAW))):
    got = (B.as_qurl(arg).host() or "").lower()
    check("rule host for %s" % kind, got == "cdn.example.com", got)

print("(7) update_bar_marks asks for the marks to be placed")
fn = re.search(r"\n    def update_bar_marks\(.*?\n    def ", SRC, re.S)
check("update_bar_marks is in the tree", fn is not None)
if fn:
    check("it calls place_bar_extras",
          "place_bar_extras()" in fn.group(0))
    check("it does not re-stringify the url",
          "QUrl(str(" not in fn.group(0))

print("(8) the tooltip on a cut-off address is an address")
tip = re.search(r"setToolTip\(\s*\n?\s*\"\" if fits else ([^\n]*)", SRC)
check("show_address builds its tooltip", tip is not None)
if tip:
    check("not from str(url)", "str(url" not in tip.group(1), tip.group(1))
check("pretty_url of a QUrl's toString is the address",
      B.pretty_url(B.as_qurl(QUrl(RAW)).toString()) == RAW,
      B.pretty_url(B.as_qurl(QUrl(RAW)).toString()))

print("")
print("FAILED %d" % len(fails) if fails else "all ok")
for what in fails:
    print("  - " + what)
sys.exit(1 if fails else 0)
