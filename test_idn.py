#!/usr/bin/env python3
"""The address bar must not show a name that is lying.

    xn--pypal-4ve.com   decodes to   pаypal.com   (Cyrillic а)
    xn--pple-43d.com    decodes to   аpple.com
    xn--gogle-3nd.com   decodes to   g̵ogle.com   (a stroked g)

No font and no reader tells those from the real thing, and the address
bar is the only place a person can check who they are actually talking
to. It is the one piece of chrome where "looks right" IS the attack.

WHAT WAS THERE BEFORE, and it is the fourth time in one day that a
comment and the code disagreed and the COMMENT was right:

    # the host in its own letters: QUrl keeps punycode in
    # toString, and the point of showing it decoded is that
    # xn--pple-43d.com is not apple.com
    host = url.host()
    if host.startswith("xn--") or ".xn--" in host:

Both halves wrong. QUrl.host() has ALREADY decoded the IDN, so the
test never matched and the branch never ran once. And the reasoning is
backwards: decoded, xn--pple-43d.com reads AS apple.com. Punycode was
never the problem being guarded against -- punycode is the warning. Qt
had been decoding the whole time and nothing was deciding whether it
should.

So this suite checks BOTH ENDS, because a rule that breaks real names
is a rule somebody switches off:

  (2) the three attacks come back as punycode
  (3) münchen.de, bücher.de, 中国.cn and яндекс.рф stay readable
  (4) the guard is load-bearing -- disabled, exactly the attacks fail
      and the real names still pass, so it cannot be satisfied by
      refusing to decode anything
  (5) what is still broken, pinned rather than pretended about

Found by browser-mac and live in every edition. Static apart from
importing browser.py; no window, no network.
"""
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

#: punycode, what it decodes to, and what it is pretending to be
ATTACKS = [
    ("xn--pypal-4ve.com", "pаypal.com", "paypal.com"),
    ("xn--pple-43d.com", "аpple.com", "apple.com"),
    ("xn--gogle-3nd.com", "g̵ogle.com", "google.com"),
]

#: real names people really type. If any of these stops being readable
#: the fix is worse than the bug.
REAL = [
    ("xn--mnchen-3ya.de", "münchen.de"),
    ("xn--bcher-kva.de", "bücher.de"),
    ("xn--fiqs8s.cn", "中国.cn"),
    ("xn--d1acpjx3f.xn--p1ai", "яндекс."
                               "рф"),
]


def shown(host):
    return B.pretty_url("https://%s/" % host, hide_scheme=True).rstrip("/")


print("(1) the fixtures really are what they claim")
from PyQt6.QtCore import QUrl  # noqa: E402
for ace, decoded, _target in ATTACKS:
    got = QUrl("https://%s/" % ace).host()
    check("%s really decodes to the lookalike" % ace, got == decoded,
          got)
check("...and Qt decodes it without being asked, which is the bug",
      all(not QUrl("https://%s/" % a).host().startswith("xn--")
          for a, _d, _t in ATTACKS))

print()
print("(2) a name that mixes alphabets is shown as punycode")
for ace, decoded, target in ATTACKS:
    got = shown(ace)
    check("%s is not shown as %s" % (ace, target), got == ace, got)
    check("...and never as its decoded form", decoded not in got, got)

print()
print("(3) ...and a real international name is still readable")
for ace, decoded in REAL:
    got = shown(ace)
    check("%s still reads as %s" % (ace, decoded), got == decoded, got)
check("an ordinary name is untouched",
      B.pretty_url("https://example.com/a?b=c", hide_scheme=True)
      == "example.com/a?b=c")

print()
print("(4) the guard is what is doing it")
# Disabled, the suite must fail on exactly the attacks and on nothing
# else. A test that goes green when the guard is torn out is testing
# the fixtures; one that fails on the real names too would be satisfied
# by refusing to decode anything at all, which is not a fix.
real_guard = B.idn_safe_to_show
try:
    B.idn_safe_to_show = lambda host: True       # as it was
    broken = [a for a, _d, _t in ATTACKS if shown(a) != a]
    still_fine = [a for a, d in REAL if shown(a) == d]
finally:
    B.idn_safe_to_show = real_guard
check("without it, every attack gets through", len(broken) == 3, broken)
check("...and the real names were never the thing stopping it",
      len(still_fine) == len(REAL), still_fine)
check("and with it back, the attacks are stopped again",
      all(shown(a) == a for a, _d, _t in ATTACKS))

print()
print("(5) what it does NOT catch, pinned so it cannot go stale")
# A label confusable while being entirely one script. Five Cyrillic
# letters reading "apple", mixing nothing. Catching it means knowing
# which alphabets the person actually READS -- a policy for the four
# editions to agree, not a default to invent in one function.
WHOLE_SCRIPT = "xn--80ak6aa92e.com"
got = shown(WHOLE_SCRIPT)
check("the whole-script case is still shown decoded", got != WHOLE_SCRIPT,
      got)
check("...but it does get the address bar's warning instead",
      bool(B.lookalike_warning(QUrl("https://%s/" % WHOLE_SCRIPT).host())),
      B.lookalike_warning(QUrl("https://%s/" % WHOLE_SCRIPT).host()))
print("       pinned: %s shows as %s -- one script, so the display rule"
      % (WHOLE_SCRIPT, got))
print("       lets it through. The day that changes, this check fails")
print("       rather than the pin quietly going stale.")

print()
print("(6) the warning label and the display rule are separate things")
# Defence in depth: the display rule decides what the bar SHOWS, and
# lookalike_warning decides whether to flag it. Neither replaces the
# other, and the second has its own false positive worth knowing about.
check("a mixed-script attack is both hidden and flagged",
      shown("xn--pple-43d.com") == "xn--pple-43d.com"
      and B.lookalike_warning("аpple.com").startswith("mixed:"))
check("a real Russian name is shown decoded even though it is flagged",
      shown("xn--d1acpjx3f.xn--p1ai").startswith("я"),
      shown("xn--d1acpjx3f.xn--p1ai"))
print("       note: lookalike_warning flags яндекс.рф as script: --")
print("       a false positive on the WARNING, not on the display.")

print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
