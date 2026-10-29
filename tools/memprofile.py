#!/usr/bin/env python3
"""What the browser actually costs, in MB, at 1 / 10 / 50 tabs.

Nobody had measured it. "Does not eat RAM" is a claim in the same
position "no telemetry" was in: true or false, but unverified either
way, and a headline claim nobody has numbers for is a headline claim
you cannot make.

HOW IT MEASURES, because the obvious way is wrong. QtWebEngine is not
one process: there is this one, a GPU process, a zygote, a utility
process and one renderer per site-ish. Measuring our own RSS reports a
fraction of the truth, and summing RSS across the tree reports far more
than the truth, because those processes share a great deal of mapped
library. So this reads PSS out of /proc/<pid>/smaps_rollup for every
process in the tree and adds that up: PSS divides each shared page by
the number of processes sharing it, which is the only number that adds
up to something real.

HOW IT PROTECTS THE MACHINE. Fifty renderers is a genuine load and the
desktop has crashed under load before, so every stage checks
MemAvailable first and stops rather than pushing the box into swap --
a measurement taken while swapping is not a measurement of the browser.
The test server would be the right home for this by the house rules,
and it cannot run it: no display and no QtWebEngine there.

    tools/memprofile.py                 1, 10 and 50 tabs
    tools/memprofile.py --tabs 1,10     fewer stages
    tools/memprofile.py --floor 2000    stop below 2000 MB available

Offscreen, against scratch data, local pages only -- no network, so
nothing here depends on how fast a website is today.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--tabs", default="1,10,50",
                help="tab counts to measure, in order (default 1,10,50)")
ap.add_argument("--floor", type=int, default=1500,
                help="stop before a stage if less than this many MB are "
                     "available (default 1500)")
ap.add_argument("--settle", type=float, default=3.0,
                help="seconds to let things settle before reading (3)")
ap.add_argument("--json", default="", help="also write the rows here")
ARGS = ap.parse_args()

STAGES = [int(n) for n in ARGS.tabs.split(",") if n.strip()]


def mem_available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


def descendants(pid):
    """This process and everything under it, however deep."""
    seen, stack = [], [pid]
    while stack:
        this = stack.pop()
        seen.append(this)
        try:
            kids = Path("/proc/%d/task" % this)
            for task in kids.iterdir():
                children = (task / "children")
                if children.exists():
                    stack += [int(x) for x in
                              children.read_text().split()]
        except (OSError, ValueError):
            continue
    return seen


def pss_mb(pids):
    """Proportional set size over a process tree, in MB."""
    total = 0
    counted = 0
    for pid in pids:
        try:
            roll = Path("/proc/%d/smaps_rollup" % pid).read_text()
        except OSError:
            continue
        for line in roll.splitlines():
            if line.startswith("Pss:"):
                total += int(line.split()[1])
                counted += 1
                break
    return total / 1024.0, counted


def cpu_seconds(pids):
    total = 0.0
    ticks = os.sysconf("SC_CLK_TCK")
    for pid in pids:
        try:
            stat = Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1]
        except (OSError, IndexError):
            continue
        parts = stat.split()
        try:
            total += (int(parts[11]) + int(parts[12])) / ticks
        except (IndexError, ValueError):
            continue
    return total


# ---- the browser, offscreen, against scratch data -------------------
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
from _boot import B  # noqa: E402
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
from tests.harness import Server, app, spin  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402

#: a page with enough in it to make a renderer do real work, and
#: nothing in it that varies between runs
BODY = ("<title>page %d</title><style>body{font:16px sans-serif;"
        "margin:2em}</style><h1>Heading %d</h1>"
        + "<p>" + ("word " * 120) + "</p>" * 12)
PAGES = {"/p%d" % i: (BODY % (i, i)) for i in range(60)}

server = Server(PAGES)
qapp = app()
win = B.Browser()
win.resize(1280, 800)
win.show()
spin(1500)

ME = os.getpid()
rows = []


def sample(label, tabs):
    time.sleep(ARGS.settle)
    for _ in range(12):
        spin(250)
    pids = descendants(ME)
    mb, counted = pss_mb(pids)
    rows.append({"what": label, "tabs": tabs, "pss_mb": round(mb, 1),
                 "processes": counted,
                 "cpu_s": round(cpu_seconds(pids), 2),
                 "avail_mb": mem_available_mb()})
    print("  %-14s tabs=%-4d PSS=%8.1f MB   processes=%-3d  "
          "cpu=%6.2fs  free=%d MB"
          % (label, tabs, mb, counted, rows[-1]["cpu_s"],
             rows[-1]["avail_mb"]))
    return mb


print("browser memory profile -- PSS over the whole process tree")
print("  sleeping after : %s min (0 = never)"
      % win.config.get("sleepAfter", "unset"))
print("  available now  : %d MB, floor %d MB\n" % (mem_available_mb(),
                                                   ARGS.floor))

sample("just started", len(win._real_tabs()))

opened = len(win._real_tabs())
for want in STAGES:
    free = mem_available_mb()
    if free < ARGS.floor:
        print("  STOPPED before %d tabs: %d MB available, floor is %d."
              % (want, free, ARGS.floor))
        print("  A measurement taken while swapping is not a measurement.")
        break
    while opened < want:
        win.new_tab(url=QUrl(server.url("/p%d" % (opened % 60))),
                    switch=False)
        opened += 1
        spin(120)
    spin(1200)
    sample("%d tabs" % want, len(win._real_tabs()))

print()
if len(rows) > 1:
    base = rows[0]["pss_mb"]
    for row in rows[1:]:
        per = ((row["pss_mb"] - base) / row["tabs"]) if row["tabs"] else 0
        print("  %-10s %8.1f MB   %+7.1f over idle   %5.1f MB a tab"
              % (row["what"], row["pss_mb"], row["pss_mb"] - base, per))

if ARGS.json:
    Path(ARGS.json).write_text(json.dumps(rows, indent=2))
    print("\n  rows written to %s" % ARGS.json)

server.stop()
sys.stdout.flush()
os._exit(0)
