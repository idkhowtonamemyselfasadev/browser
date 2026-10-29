#!/usr/bin/env python3
"""The one list that holds everything has to actually hold everything.

actions_list() is read by four things -- the keys, the command palette,
the cheat sheet and Settings' key editor -- so an action in it is
reachable four ways and an action out of it is reachable none. That is
the design, and it is good. What it does not survive is two entries
being folded together on the way to the palette.

The palette used to fold by LABEL: if two rows read the same, the
second was dropped as a duplicate key for the first. Most of the time
that is right -- Ctrl+= and Ctrl++ and Ctrl+Shift+= are one action
under three keys, and so are Ctrl+1..9. But it is the wrong test, and
on 2026-10-29 it was hiding seven things:

    inspector, inspector2   carried "tbFind", the FIND BUTTON's own
                            string, so F12 and Ctrl+Shift+I read as
                            "Find on page" everywhere -- the cheat
                            sheet, Settings' key editor, the palette --
                            and the palette then dropped them both as
                            duplicates of Find. The developer tools
                            could not be reached or rebound by name.
                            "devTools" already existed and nothing
                            used it.
    six more                genuinely different actions whose English
                            happened to match: a PDF's paging against a
                            site's, the accessibility menu's heading
                            jump against the keyboard one, and so on.

Folding by the action's own string key instead is the right test: two
entries sharing a string ARE one action by construction, and two
entries that merely read alike are not.

This is browser-android's shape one level up. Their palette did not
list a feature that had a run() branch and a menu item, so the one
searchable list of everything did not know it existed. Not a dead
control -- a live feature with no road to it.

Boots a browser offscreen because action_label() needs one. Touches
nothing of yours.
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

qapp = app()
win = B.Browser()
win.show()
spin(400)

#: Pairs of string keys whose text is the same on purpose, because they
#: reach the same thing from two different menus. Pinned by name so a
#: NEW collision is a failure rather than two identical rows nobody can
#: tell apart. The fix for a new one is a distinguishing word, not an
#: entry here.
SAME_ON_PURPOSE = {
    frozenset(("navClearCache", "devHardReloadRow")):
        "the address bar's menu and the developer menu offer the same "
        "clear-and-reload",
    frozenset(("a11yJumpHeading", "actNextHeading")):
        "the accessibility menu and the keyboard reach one heading jump",
    frozenset(("a11yJumpHeadingBack", "actPrevHeading")):
        "the same, backwards",
    frozenset(("pageSaveMd", "readSaveMd")):
        "page tools and the reader offer the same Markdown save",
}

entries = win.actions_list()

print("(1) the table is whole")
check("there are actions", len(entries) > 300, len(entries))
check("every action has an id, a string and something to run",
      all(e.get("id") and e.get("str") and callable(e.get("run"))
          for e in entries))
blank = [e["id"] for e in entries if not win.action_label(e).strip()]
check("every action has a label", not blank, blank)
raw = [e["id"] for e in entries if win.action_label(e) == e["str"]]
check("...and no label is just the raw string key", not raw, raw)

print()
print("(2) the palette offers one row per action, not per wording")
by_str = {}
for e in entries:
    by_str.setdefault(e["str"], []).append(e["id"])
by_label = {}
for e in entries:
    by_label.setdefault(win.action_label(e), []).append(e["id"])
print("       %d actions -> %d rows folding by string, %d by label"
      % (len(entries), len(by_str), len(by_label)))

# the defect, as a measurement: an action the label rule would have hid
hidden = []
for label, ids in by_label.items():
    strs = {e["str"] for e in entries if e["id"] in ids}
    if len(strs) > 1 and frozenset(strs) not in SAME_ON_PURPOSE:
        hidden.append((label, sorted(strs)))
check("no two different actions read as the same thing", not hidden,
      hidden)
for strs, why in SAME_ON_PURPOSE.items():
    present = [s for s in strs if s in by_str]
    check("the pinned pair %s is still a pair"
          % "/".join(sorted(strs)), len(present) == 2, present)
    print("       same on purpose: %s" % why)

print()
print("(3) the palette actually folds the way it says it does")
src = (HERE / "browser.py").read_text(encoding="utf-8")
check("open_palette folds on the action's string key",
      'if entry["str"] in seen:' in src)
check("...not on the words it reads as",
      "if label in seen:" not in src)

print()
print("(4) the developer tools are their own command again")
dev = [e for e in entries if e["id"] in ("inspector", "inspector2")]
check("both inspector entries are there", len(dev) == 2, len(dev))
check("...and neither borrows the Find button's string",
      all(e["str"] != "tbFind" for e in dev), [e["str"] for e in dev])
check("...they say what they are",
      all(win.action_label(e) == B.UI_STRINGS["en"]["devTools"]
          for e in dev), [win.action_label(e) for e in dev])
check("...in German too",
      B.UI_STRINGS["de"]["devTools"] != B.UI_STRINGS["en"]["devTools"],
      B.UI_STRINGS["de"]["devTools"])
find = [e for e in entries if e["id"] == "find"]
check("and Find is still Find", find and find[0]["str"] == "actFind")

print("\n%d checks failed" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
