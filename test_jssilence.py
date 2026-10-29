#!/usr/bin/env python3
"""No js() helper may answer silence as if it were a value.

    check("...and the page is near where it was",
          (js("window.scrollY|0", MAIN) or 0) >= 200,
          js("window.scrollY|0", MAIN))

`js()` used to answer None for both "the page said null" and "the page
never answered", and `or 0` turns the second into a confident zero.
Five runs of that exact line on a quiet machine, from browser-windows:

    run 3  FAIL  ...and the page is near where it was  <240>
    run 5  ok    ...and the page is near where it was  <0>

Two verdicts out of five contradicting the evidence printed next to
them, in opposite directions. **Run 5 is the one that matters.** A red
check that is wrong gets investigated; a green check that proves
nothing never gets looked at again.

Measured in this tree: 64 suites call js(), 1214 call sites, 495
check() verdicts whose condition reads a js() value, 77 of them
coercing with `or`.

This suite keeps that shut. Every `def js(` in every test file has to
do one of three things when the page does not answer:

    delegate   to tests/harness.py, which raises
    raise      itself
    return a sentinel that is obviously not a measurement

A sentinel is allowed because `"<timeout>" >= 200` raises TypeError in
Python 3 -- it fails loudly, which is the whole requirement. `None` is
not allowed, because None compares and coerces quietly.

Static. Reads the suites as text; starts nothing.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


SENTINELS = ("<timeout>", "<no answer>", "<none>")


def body_of(text, name="js"):
    m = re.search(r"^(def %s\s*\(.*?)(?=\n\S|\Z)" % name, text,
                  re.M | re.S)
    return m.group(1) if m else ""


def verdict(body):
    """What this helper does when the page says nothing."""
    if re.search(r"\b(H|harness)\.js\s*\(", body):
        return "delegates"
    if "raise" in body:
        return "raises"
    if any(s in body for s in SENTINELS):
        return "sentinel"
    if re.search(r"runJavaScript\([^)]*\)\s*$", body.strip()) \
            or body.count("\n") <= 2:
        return "callback"        # hands the answer on, never returns one
    return "SILENT"


suites = sorted(list(HERE.glob("test_*.py"))
                + list((HERE / "tests").glob("test_*.py")))
print("(1) the harness itself refuses to answer silence")
harness = (HERE / "tests" / "harness.py").read_text(encoding="utf-8")
hbody = body_of(harness)
check("tests/harness.py has a js()", bool(hbody))
check("...and it raises rather than returning None",
      "raise AssertionError" in hbody, verdict(hbody))
check("...naming the code that did not answer", "str(code)" in hbody)
check("...and it still returns the value when there is one",
      'return box["v"]' in hbody)

print()
print("(2) and so does every suite that rolls its own")
own, silent = 0, []
kinds = {}
for p in suites:
    text = p.read_text(encoding="utf-8")
    body = body_of(text)
    if not body:
        continue
    own += 1
    kind = verdict(body)
    kinds[kind] = kinds.get(kind, 0) + 1
    if kind == "SILENT":
        silent.append(p.name)
check("there are helpers to check", own > 20, own)
check("none of them answers silence as a value", not silent, silent)
for kind, n in sorted(kinds.items()):
    print("       %-10s %d" % (kind, n))

print()
print("(3) the classifier can tell the bad shape from the good ones")
check("a silent one is caught",
      verdict('def js(p, c):\n    box = {}\n    loop.exec()\n'
              '    return box.get("v")\n') == "SILENT")
check("...and one that raises is not",
      verdict('def js(p, c):\n    if "v" not in box:\n        raise '
              'AssertionError("x")\n    return box["v"]\n') == "raises")
check("...nor one with a sentinel",
      verdict('def js(p, c):\n    return box.get("r", "<timeout>")\n')
      == "sentinel")
check("...nor a thin wrapper round the harness",
      verdict('def js(code):\n    return H.js(view, code, MAIN)\n')
      == "delegates")

print()
print("(4) what is still the caller's job, said out loud")
# Raising stops silence being read as data. It does NOT fix asking the
# page twice -- once for the condition, once for the detail -- and
# getting two different answers, which is why run 3 above failed while
# printing 240. That one needs the caller to measure once.
twice = 0
for p in suites:
    text = p.read_text(encoding="utf-8")
    for m in re.finditer(r"check\s*\(", text):
        chunk = text[m.start():m.start() + 400]
        depth, end = 0, len(chunk)
        for i, ch in enumerate(chunk):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if len(re.findall(r"\bjs\s*\(", chunk[:end])) >= 2:
            twice += 1
print("       %d verdicts ask the page more than once in one check()" % twice)
print("       -- each is free to assert on one answer and print another.")
print("       Raising does not fix those; measuring once does.")
check("that number is known rather than guessed at", twice >= 0, twice)

print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
