#!/usr/bin/env python3
"""https-only has to ask, which it has never once done.

The setting's own hint, in Settings, in both languages:

    "An http address is tried over https first; if that fails you are
     asked before it loads."

The asking never happened. Two wires were missing, not one:

  note_https_upgrade  had no caller anywhere in the file. The upgrade
      itself worked -- the interceptor swapped the scheme and sent the
      tab to the secure address -- but nothing recorded where the tab
      had come from, so view._upgraded_from was never set.
  https_fallback      was connected to nothing. Its own docstring
      calls it "the whole difference between https-only and
      https-mostly", the dialog it shows is written and translated
      (httpsWarnT / httpsWarnB), and allow_http_once exists to carry
      the answer. All of it was unreachable.

What that cost him, said the right way round, because "https-only is
broken" reads like the opposite failure: it failed CLOSED. An
http-only site was simply unreachable with no way through and no
explanation. Safer than advertised, and the promise unmet.

A third thing, found by driving rather than by reading the dead code:
the breadcrumb outlived the navigation it described. The original
returned early on a successful load WITHOUT clearing it, so after an
upgrade that worked, the next failed navigation anywhere in that tab
would have offered the insecure address of the page before it. A
downgrade prompt for an unrelated error is worse than no prompt. It is
cleared on success now, and the failure path additionally checks that
the address that failed IS the one the upgrade went to.

Also measured, because it decides whether the clearing matters: a
failed load fires loadFinished(False) TWICE with the attempted
address still in the view, and an aborted load does not fire a failure
at all -- it reports (True, "about:blank"). So clearing the breadcrumb
on first use is what stops the dialog appearing twice, and there is no
spurious-dialog-on-abort case to guard.

Driven through a real tab made by new_tab, so the connect under test
is the real one rather than a hand-made signal. The dialog is answered
by a stub, because the box IS the answer and an offscreen run cannot
click it.
"""
import argparse
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--dir", metavar="PATH", default=None,
                help="an edition's folder to drive instead of this one")
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
                                     "vaultPassword": True,
                                     "httpsOnly": True}))

from tests.harness import app, spin  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

qapp = app()
win = B.Browser()
win.show()
spin(600)

SRC = (REPO / "browser.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)

HTTP = QUrl("http://httponly.example/page")
HTTPS = QUrl("https://httponly.example/page")

asked = []


def stub(_parent, title, body, *a, **k):
    """Stand in for the box. The box IS the answer, so it is recorded
    rather than shown, and the reply is whatever the test set."""
    asked.append((title, body))
    return stub.answer


stub.answer = B.QMessageBox.StandardButton.No
B.QMessageBox.question = stub


print("\n(1) both wires exist at all")
# This is the whole bug, so it is asserted on the tree and not only
# on behaviour: a connect is the kind of thing that cannot be seen
# from inside the function it should call.
calls = [n for n in ast.walk(TREE)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and n.func.attr == "note_https_upgrade"]
check("note_https_upgrade has a caller", bool(calls),
      "%d call site(s) at line(s) %s"
      % (len(calls), [c.lineno for c in calls]) if calls else "NONE")
wired = re.search(r"loadFinished\.connect\([^)]*https_fallback", SRC)
check("https_fallback is connected to loadFinished", bool(wired))
check("the setting still promises the asking",
      "asked before it loads" in B.UI_STRINGS["en"]["httpsOnlyHint"],
      B.UI_STRINGS["en"]["httpsOnlyHint"])
for key in ("httpsWarnT", "httpsWarnB"):
    for lang in ("en", "de"):
        check("%s is there in %s" % (key, lang),
              bool(B.UI_STRINGS.get(lang, {}).get(key)))

print("\n(2) a real tab, and an ordinary failure asks nothing")
view = win.new_tab(url="about:blank", switch=True)
spin(300)
check("the tab was made (the fixture)", view is not None)
if view is None:
    print("\nBLOCKED: no tab to drive")
    sys.exit(1)
check("it carries no breadcrumb yet (the fixture)",
      not getattr(view, "_upgraded_from", ""),
      getattr(view, "_upgraded_from", "") or "none")
asked.clear()
view.loadFinished.emit(False)
spin(80)
check("a failed load with no upgrade behind it asks nothing",
      not asked, len(asked))

print("\n(3) the breadcrumb, then the asking")
check("note_https_upgrade records both ends",
      win.note_https_upgrade(view, HTTP, HTTPS) is True)
check("...where he came from", getattr(view, "_upgraded_from", "")
      == HTTP.toString(), getattr(view, "_upgraded_from", ""))
check("...and where it went", getattr(view, "_upgraded_to", "")
      == HTTPS.toString(), getattr(view, "_upgraded_to", ""))
asked.clear()
stub.answer = B.QMessageBox.StandardButton.No
# The view has to be holding the address that failed, which is what a
# real failure leaves behind. It is settled on a page that needs no
# network and THAT is recorded as where the upgrade went, because
# setUrl on a host which does not resolve fires a genuine
# loadFinished(False) inside the spin -- which spent the breadcrumb
# before this test's own emit and made section (4) fail for a reason
# that was nothing to do with the browser.
here = QUrl(view.url().toString())
win.note_https_upgrade(view, HTTP, here)
view.loadFinished.emit(False)
spin(80)
check("the secure address failing asks once", len(asked) == 1, len(asked))
if asked:
    check("...and the question names the host",
          "httponly.example" in asked[0][1], asked[0][1][:60])
check("saying no loads nothing insecure",
      not win.http_allowed("httponly.example"))
check("...and the breadcrumb is spent, so it cannot ask twice",
      not getattr(view, "_upgraded_from", ""),
      getattr(view, "_upgraded_from", "") or "none")
asked.clear()
view.loadFinished.emit(False)
spin(80)
check("a second failure is silent", not asked, len(asked))

print("\n(4) saying yes is the only way anything insecure loads")
win.note_https_upgrade(view, HTTP, QUrl(view.url().toString()))
asked.clear()
stub.answer = B.QMessageBox.StandardButton.Yes
check("http is not allowed before he says so (the fixture)",
      not win.http_allowed("httponly.example"))
view.loadFinished.emit(False)
spin(120)
check("he was asked", len(asked) == 1, len(asked))
check("...and only then is the host excused",
      win.http_allowed("httponly.example"))

print("\n(5) the breadcrumb does not outlive its own navigation")
# the bug the dead code would have shipped: a success left the
# breadcrumb set, so the NEXT failure in the tab offered the insecure
# address of the page before it
view2 = win.new_tab(url="about:blank", switch=True)
spin(300)
check("a second tab, clean (the fixture)", view2 is not None
      and not getattr(view2, "_upgraded_from", ""))
win.note_https_upgrade(view2, QUrl("http://other.example/"),
                       QUrl("https://other.example/"))
view2.loadFinished.emit(True)
spin(80)
check("a successful load spends the breadcrumb",
      not getattr(view2, "_upgraded_from", ""),
      getattr(view2, "_upgraded_from", "") or "none")
asked.clear()
stub.answer = B.QMessageBox.StandardButton.Yes
view2.loadFinished.emit(False)
spin(80)
check("so a later unrelated failure offers no downgrade",
      not asked, asked[0][1][:40] if asked else 0)
check("...and nothing was excused behind his back",
      not win.http_allowed("other.example"))

print("\n(6) a failure on some other page is not the upgrade's failure")
view3 = win.new_tab(url="about:blank", switch=True)
spin(300)
# recorded as going somewhere the view is NOT, which is the case this
# guards: some other page in the tab failing is not the upgrade failing
win.note_https_upgrade(view3, HTTP,
                       QUrl("https://somewhere.else.example/"))
asked.clear()
view3.loadFinished.emit(False)
spin(80)
check("a different address failing asks nothing", not asked,
      asked[0][1][:40] if asked else 0)
check("...and the breadcrumb is still there for its own page",
      getattr(view3, "_upgraded_from", "") == HTTP.toString(),
      getattr(view3, "_upgraded_from", "") or "none")

print("")
if fails:
    print("%d FAILED:" % len(fails))
    for one in fails:
        print("  - " + one)
    sys.exit(1)
print("all ok")
