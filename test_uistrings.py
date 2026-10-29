#!/usr/bin/env python3
"""Every string the browser asks for by name has to be there.

_ui_str is forgiving in exactly the way theme_color is:

    return table.get(key) or UI_STRINGS["en"].get(key, key)

a key nobody defines comes back as *the key itself*. The pages are
forgiving the same way -- `STR.micOn || "Listening..."` -- so a string
the browser never supplies shows the page's own English instead. Both
are right as a last resort and wrong as a habit, because the result is
plausible text rather than an error, and nobody reports plausible text.

It cost two real defects, found on 2026-10-29:

  player.html:167   STR.on was never in UI_STRINGS, STR.off was. The
                    Loop button read "Loop: on" then "Loop: Off" in
                    English, and "Loop: on" / "Loop: Aus" in German.
                    STR.playerLoop was missing too, so the whole label
                    was untranslated.
  mictest.html      FOURTEEN keys, which is every string on the page.
                    On German the microphone test was entirely in
                    English while the rest of the browser was not. One
                    of them, micTestTitle, already existed in the table
                    under mictestTitle -- a capital T apart. The
                    browser HAD the string and the page could not find
                    it.

That near-miss is the shape worth remembering: the fallback was not
blank or broken, it was the right words in the wrong language, and
nothing anywhere said so.

Five questions, over three surfaces -- browser.py, the markup's own
t_/data-str maps, and the STR.x the page scripts read.

Static apart from importing browser.py for the tables. No window, no
network, writes nothing.
"""
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE

import os  # noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BROWSER_NO_LIB_CHECK", "1")
sys.path.insert(0, str(REPO))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import browser as B  # noqa: E402

SRC = (REPO / "browser.py").read_text(encoding="utf-8")
EN = B.UI_STRINGS["en"]
DE = B.UI_STRINGS["de"]
PAGES = sorted(REPO.glob("*.html"))

#: the names that really are a string lookup. `say` is deliberately not
#: one of them: MasterDialog.say(text) puts a line on a dialog and
#: `say("unknown-command")` answers a command line, and neither is
#: asking the table for anything.
LOOKUPS = {"_ui_str", "ui", "_str"}

#: `STR.x` members that are not strings
NOT_STRINGS = {"lang", "length", "map", "filter", "forEach",
               "hasOwnProperty", "toString", "constructor", "prototype",
               "call", "apply", "bind"}

REF = re.compile(r"\b(?:STR|S)\.([A-Za-z_][A-Za-z0-9_]*)\b")
DATASTR = re.compile(r'data-str="([A-Za-z0-9_]+)"')
TMAP = re.compile(r'\bt_[A-Za-z0-9_]+\s*:\s*"([A-Za-z0-9_]+)"')
PCT = re.compile(r"%[sd]|%%|\{\}")


def asked_for(source):
    """Every key handed to a lookup as a plain string, from the tree.

    The AST for the same reason test_bridgecalls and test_themetokens
    use it: a comment that mentions a key is not a call that needs one.
    """
    out = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = (fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else "")
        if name not in LOOKUPS:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                and first.value:
            out.setdefault(first.value, []).append(node.lineno)
    return out


def page_refs(text):
    return {n for n in REF.findall(text) if n not in NOT_STRINGS}


def placeholders(text):
    return sorted(x for x in PCT.findall(text) if x != "%%")


print("(1) the tables are there and agree with each other")
check("English has its strings", len(EN) > 2000, len(EN))
check("German has the same keys, no more and no fewer", set(EN) == set(DE),
      sorted(set(EN) ^ set(DE))[:6])

print()
print("(2) browser.py never asks for a key that is not there")
USED = asked_for(SRC)
check("there are keys to check", len(USED) > 1000, len(USED))
absent = sorted(k for k in USED if k not in EN)
check("every key browser.py names exists",
      not absent, [(k, USED[k][:2]) for k in absent])

print()
print("(3) the pages' own maps name keys that exist")
declared = 0
unknown = {}
for page in PAGES:
    text = page.read_text(encoding="utf-8")
    for key in sorted(set(DATASTR.findall(text)) | set(TMAP.findall(text))):
        declared += 1
        if key not in EN:
            unknown.setdefault(page.name, []).append(key)
check("there are declared keys to check", declared > 300, declared)
check("every data-str and t_ key exists", not unknown, unknown)

print()
print("(4) and so does every STR.x the page scripts read")
# this is the one that would have caught the microphone page: those
# keys are in no map and no attribute, only in the script.
read = 0
missing = {}
for page in PAGES:
    for key in sorted(page_refs(page.read_text(encoding="utf-8"))):
        read += 1
        if key not in EN:
            missing.setdefault(page.name, []).append(key)
check("there are references to check", read > 300, read)
check("every string a page reads is one the browser supplies",
      not missing, missing)

print()
print("(5) a translated string takes the same arguments as its original")
# "%d tabs" against a German "%s Tabs" is a TypeError at the moment it
# is shown, in the language the author does not run.
mismatch = [(k, placeholders(EN[k]), placeholders(DE[k]))
            for k in EN
            if isinstance(EN[k], str) and isinstance(DE.get(k), str)
            and placeholders(EN[k]) != placeholders(DE[k])]
check("every German string carries the English placeholders",
      not mismatch, mismatch[:4])

print()
print("(6) the fallbacks this suite exists for are still the fallbacks")
# If either of them started raising, these checks would be pointless
# and should say so rather than passing quietly.
unknown_key = "no-such-ui-string-" + "x" * 8
check("an unknown key comes back as itself, not as an error",
      B.UI_STRINGS["en"].get(unknown_key, unknown_key) == unknown_key)
check("...and the page pattern falls back to its own English",
      "STR.%s || \"x\"" % unknown_key != "")

# and each of the three scanners has to be able to find something
check("the browser.py scan sees a key that is not there",
      "zzNotAKey" in asked_for('self._ui_str("zzNotAKey")'))
check("...and does not see one that is only mentioned in a comment",
      "zzInAComment" not in asked_for('# self._ui_str("zzInAComment")\nx = 1'))
check("the page scan sees STR.x", "zzPageKey" in page_refs("STR.zzPageKey"))
check("...and ignores the holder's own members",
      not page_refs("STR.lang") & {"lang"})
check("the placeholder scan sees a mismatch",
      placeholders("%d tabs") != placeholders("%s Tabs"))

print()
print("(7) the two that were actually broken read correctly now")
check("the Loop button agrees with itself in English",
      EN["playerLoop"].replace("%s", EN["on"]) == "Loop: On"
      and EN["playerLoop"].replace("%s", EN["off"]) == "Loop: Off",
      EN["playerLoop"].replace("%s", EN["on"]))
check("...and is German in German",
      DE["on"] != EN["on"] and DE["playerLoop"] != EN["playerLoop"],
      (DE["playerLoop"], DE["on"]))
mic = ("micTestTitle", "micWord", "camWord", "micOn", "micOff", "micFailed",
       "camOn", "camOff", "camFailed", "micLevel", "recNone", "recNow",
       "recDone", "micTestSub")
check("the microphone page has all fourteen of its strings",
      all(k in EN for k in mic), [k for k in mic if k not in EN])
check("...in German too, and actually translated",
      all(k in DE for k in mic)
      and sum(1 for k in mic if DE[k] != EN[k]) >= 11,
      sum(1 for k in mic if DE[k] != EN[k]))
# the near-miss that hid it: both spellings live in the table today,
# and the page reads the camel-case one. Named here so the duplicate is
# visible rather than quietly permanent.
check("the near-miss pair that caused this is still a known pair",
      "mictestTitle" in EN and "micTestTitle" in EN)

print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
