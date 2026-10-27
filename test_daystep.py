#!/usr/bin/env python3
"""A day is not 86400 seconds, and the streaks used to think it was.

Twice a year a local day is 23 or 25 hours long. Everything in the
browser that walks day boundaries -- how many days in a row a site was
visited, the per-day chart in the history page -- keys its days by
local midnight (_day_start). Stepping between those midnights by a flat
86400 lands on 01:00 or 23:00 of the neighbouring day and never on its
midnight, so the lookup misses and the day reads as a gap: every streak
in the browser broke on the morning of 2026-10-25, when the clocks went
back.

This pins the clock to Europe/Berlin and walks both changes of 2026 --
the 23-hour day in March and the 25-hour day in October -- through
_day_step and then through the two features that depend on it.

Offscreen, scratch data; the real history and config are never opened.
"""
import os
import sys
import time
from pathlib import Path

# before anything reads the clock: these checks are about one zone, and
# a run on a UTC box would pass without ever meeting a clock change
os.environ["TZ"] = "Europe/Berlin"
time.tzset()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def at(y, m, d, hh=12, mm=0):
    """A local timestamp, with mktime deciding the offset."""
    return int(time.mktime((y, m, d, hh, mm, 0, 0, 0, -1)))


def shown(ts):
    return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(ts))


# the two changes of 2026 in this zone: forward 29 March, back 25 October
SPRING = (2026, 3, 29)
AUTUMN = (2026, 10, 25)

print("(1) the zone really has the clock changes these checks need")
check("the 29th of March is 23 hours long",
      at(2026, 3, 30, 0) - at(2026, 3, 29, 0) == 23 * 3600,
      (at(2026, 3, 30, 0) - at(2026, 3, 29, 0)) / 3600)
check("the 25th of October is 25 hours long",
      at(2026, 10, 26, 0) - at(2026, 10, 25, 0) == 25 * 3600,
      (at(2026, 10, 26, 0) - at(2026, 10, 25, 0)) / 3600)

print("\n(2) a day step lands on midnight, both ways, across both changes")
for name, (y, m, d) in (("spring forward", SPRING), ("clocks back", AUTUMN)):
    after = B._day_start(at(y, m, d + 1))
    before = B._day_start(at(y, m, d))
    check("%s: back one day from the morning after is its midnight"
          % name, B._day_before(after) == before,
          "%s -> %s, wanted %s" % (shown(after), shown(B._day_before(after)),
                                   shown(before)))
    check("%s: forward one day from the day itself is the next midnight"
          % name, B._day_after(before) == after,
          "%s -> %s, wanted %s" % (shown(before), shown(B._day_after(before)),
                                   shown(after)))
    check("%s: a flat 86400 would have missed it (the old bug)" % name,
          after - 86400 != before,
          "%s vs %s" % (shown(after - 86400), shown(before)))

print("\n(3) a step is still a step on an ordinary day, and reverses")
plain = B._day_start(at(2026, 6, 15))
check("back then forward is where it started",
      B._day_after(B._day_before(plain)) == plain)
check("forward then back is where it started",
      B._day_before(B._day_after(plain)) == plain)
check("an ordinary step really is 86400 here",
      plain - B._day_before(plain) == 86400,
      plain - B._day_before(plain))
check("it crosses the end of a month",
      time.localtime(B._day_before(B._day_start(at(2026, 7, 1)))).tm_mon == 6)
check("...and the end of a year",
      time.localtime(B._day_before(B._day_start(at(2026, 1, 1)))).tm_year
      == 2025)
check("a step of several days is that many days",
      time.localtime(B._day_step(plain, -5)).tm_mday == 10,
      time.localtime(B._day_step(plain, -5)).tm_mday)

print("\n(4) a streak that runs through the clocks going back")


class Fake:
    """Both site_streak and browsing_stats read nothing but
    self.history, so they are called unbound against this rather than
    against a real Browser: a window would need a QApplication and
    would walk into the first-run wizard on a scratch profile, neither
    of which has anything to do with the arithmetic under test."""

    def __init__(self):
        self.history = []

    def site_streak(self, host):
        return B.Browser.site_streak(self, host)

    def browsing_stats(self, days=7):
        return B.Browser.browsing_stats(self, days=days)


win = Fake()
# four days in a row ending the morning after the change, which is the
# run that used to be cut to one
run = [at(2026, 10, 23, 9), at(2026, 10, 24, 9),
       at(2026, 10, 25, 9), at(2026, 10, 26, 9)]
win.history = [{"url": "https://streak.test/p%d" % i, "t": t}
               for i, t in enumerate(run)]
real_time = time.time
try:
    time.time = lambda: float(at(2026, 10, 26, 21))
    got = win.site_streak("streak.test")
    check("all four days count", got["streak"] == 4, got)
    check("...and so does the visit total", got["visits"] == 4, got)
    check("...and the number of distinct days", got["days"] == 4, got)

    # the same run, but he has not been there yet today: counts to
    # yesterday, which is the other branch of the same arithmetic
    win.history = [{"url": "https://streak.test/p%d" % i, "t": t}
                   for i, t in enumerate(run[:3])]
    got = win.site_streak("streak.test")
    check("not yet today, the run up to yesterday still counts",
          got["streak"] == 3, got)

    print("\n(5) a streak through the clocks going forward")
    spring = [at(2026, 3, 27, 9), at(2026, 3, 28, 9),
              at(2026, 3, 29, 9), at(2026, 3, 30, 9)]
    win.history = [{"url": "https://spring.test/p%d" % i, "t": t}
                   for i, t in enumerate(spring)]
    time.time = lambda: float(at(2026, 3, 30, 21))
    got = win.site_streak("spring.test")
    check("all four days count across the short day",
          got["streak"] == 4, got)

    print("\n(6) a gap is still a gap")
    gapped = [at(2026, 10, 22, 9), at(2026, 10, 25, 9), at(2026, 10, 26, 9)]
    win.history = [{"url": "https://gap.test/p%d" % i, "t": t}
                   for i, t in enumerate(gapped)]
    time.time = lambda: float(at(2026, 10, 26, 21))
    got = win.site_streak("gap.test")
    check("the streak stops at the missing day", got["streak"] == 2, got)
    check("...but every visit is still counted", got["visits"] == 3, got)

    print("\n(7) the per-day chart puts the pages on the right days")
    pages = []
    for day, n in ((23, 1), (24, 2), (25, 3), (26, 4)):
        pages += [{"url": "https://chart.test/%d-%d" % (day, i),
                   "t": at(2026, 10, day, 9)} for i in range(n)]
    win.history = pages
    stats = win.browsing_stats(days=5)
    check("there is a bucket per day asked for",
          len(stats["days"]) == 5, len(stats["days"]))
    check("every bucket is a real local midnight",
          all(time.localtime(row["t"]).tm_hour == 0
              for row in stats["days"]),
          [shown(row["t"]) for row in stats["days"]])
    check("no page fell down a gap between the buckets",
          sum(row["pages"] for row in stats["days"]) == len(pages),
          (sum(row["pages"] for row in stats["days"]), len(pages)))
    counted = {time.localtime(row["t"]).tm_mday: row["pages"]
               for row in stats["days"]}
    check("the day the clocks changed has its three pages",
          counted.get(25) == 3, counted)
    check("...and the morning after has its four",
          counted.get(26) == 4, counted)
    check("...and the quiet day before has one",
          counted.get(23) == 1, counted)
finally:
    time.time = real_time

print("\n(8) a day of history to restore is a calendar day")
midnight = B._day_start(at(2026, 10, 25, 9))
check("the day the clocks went back is 25 hours of history",
      B._day_after(midnight) - midnight == 25 * 3600,
      (B._day_after(midnight) - midnight) / 3600)
check("...so a flat 86400 would have left an hour of it behind",
      midnight + 86400 < B._day_after(midnight))
# the bridge used to work the end of the span out for itself, so the
# page's own restore never reached the default above
source = Path(B.__file__ if hasattr(B, "__file__")
              else HERE / "browser.py").read_text(errors="replace")
check("the bridge leaves the end of the span to restore_day",
      "int(since) + 86400" not in source)

print("\n(9) a tab snoozed until tomorrow morning comes back tomorrow")
# the call site takes the date out of a day step and puts 08:00 on it.
# `time.time() + 86400` is still *today* at 00:30 on the morning the
# clocks go back, and is the day after tomorrow late on the short day.
check("the snooze steps through the calendar",
      "_day_after(time.time())" in source)
for label, now, wanted in (
        ("after midnight on the 25-hour day", at(2026, 10, 25, 0, 30), 26),
        ("late on the evening before the 23-hour day",
         at(2026, 3, 28, 23, 30), 29),
        ("an ordinary evening", at(2026, 6, 15, 23, 30), 16)):
    stepped = time.localtime(B._day_after(now))
    check("%s: tomorrow is the %dth" % (label, wanted),
          stepped.tm_mday == wanted, stepped.tm_mday)
    flat = time.localtime(now + 86400)
    if flat.tm_mday != wanted:
        check("...and a flat 86400 would have said the %dth (the old bug)"
              % flat.tm_mday, True)
    morning = int(time.mktime((stepped.tm_year, stepped.tm_mon,
                               stepped.tm_mday, 8, 0, 0, 0, 0, -1)))
    check("...and 08:00 on it is still ahead", morning > now, shown(morning))

print("\n%d checks failed" % len(fails))
for name in fails:
    print("  - " + name)
sys.exit(1 if fails else 0)
