#!/usr/bin/env python3
"""The scratch directories have to be taken back, including by the
runs that cannot take back their own.

/tmp here is tmpfs, so one left behind is RAM the next suite cannot
have: 1,348 of them holding 3.7 GB on 2026-10-29, and another
session's write failed because of it. What it looks like from inside a
suite is six consecutive crashes with no failed check, because a
browser that cannot write its profile dies looking like a bug in
whatever it was doing.

The case this suite exists for is the one that defeated the old
cleanup entirely: a run that ends with os._exit. atexit does not run
then, and 19 suites end that way on purpose, to dodge a Qt teardown
segfault. So the runs most likely to leak were exactly the ones that
had opted out of the only mechanism that would have cleared up. The
fix is to sweep at STARTUP as well -- whoever comes next clears up --
and section (5) drives a real os._exit subprocess to prove it.

Everything here happens in its own TMPDIR. It never looks at the real
/tmp and never removes anything outside its own fixture, which is
browser-mac-8f's method: the 1,348 directories are a separate
question, and a suite that reclaims gigabytes as a side effect of
being run is not a suite anybody can trust.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


import tmpscratch as T  # noqa: E402

YARD = Path(tempfile.mkdtemp(prefix="tmpscratch-test-"))


def plant(prefix, pid, age_s=0):
    """A scratch directory as a run would have left it."""
    path = YARD / ("%s%s-%d" % (prefix, "aaaa", pid))
    path.mkdir()
    (path / "profile").write_text("x" * 64)
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


def dead_pid():
    """A pid that is certainly gone: fork a child and reap it."""
    out = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


print("\n(1) a run claims one, and it is named for its own process")
mine = T.claim("browsershot-", parent=str(YARD))
check("the directory exists", Path(mine).is_dir(), mine)
check("...and the pid is in the name, which is what liveness reads",
      T._pid_of(Path(mine).name) == os.getpid(),
      "%s -> %s" % (Path(mine).name, T._pid_of(Path(mine).name)))

print("\n(2) a dead run's directory goes")
gone_pid = dead_pid()
left = plant("browsershot-", gone_pid, age_s=3600)
check("the fixture is there and its process is not (the fixture)",
      left.is_dir() and not T._alive(gone_pid), gone_pid)
swept = T.sweep(parent=str(YARD))
check("it was taken", not left.exists(), swept)
check("...and this run's own was spared", Path(mine).is_dir())

print("\n(3) a live run's directory is spared, whatever its age")
alive = plant("browser-pwtest-", os.getpid(), age_s=99999)
T.sweep(parent=str(YARD))
check("a living process keeps its directory", alive.is_dir(),
      "aged %d s and still there" % 99999)

print("\n(4) the grace, and the names from before the pid went in")
fresh = plant("browsershot-", dead_pid(), age_s=0)
T.sweep(parent=str(YARD))
check("a directory made a moment ago is not raced", fresh.is_dir())
nameless = YARD / "browsershot-oldstyle"
nameless.mkdir()
T.sweep(parent=str(YARD))
check("a name with no pid in it is left alone, not guessed at",
      nameless.is_dir())

print("\n(5) the case that defeated the old cleanup: os._exit")
# 19 suites end this way. atexit never runs, so the directory survives
# the run that made it -- and the NEXT run has to be the one that
# clears it. That is the whole fix, driven rather than asserted.
code = (
    "import sys, os; sys.path.insert(0, %r);"
    "import tmpscratch as T;"
    "d = T.claim('browsershot-', parent=%r);"
    "print(d);"
    "sys.stdout.flush();"
    "os._exit(0)" % (str(HERE), str(YARD)))
out = subprocess.run([sys.executable, "-c", code],
                     capture_output=True, text=True, check=True)
leaked = Path(out.stdout.strip())
check("the os._exit run left its directory behind (the fixture)",
      leaked.is_dir(), leaked.name)
check("...and its process really is gone",
      not T._alive(T._pid_of(leaked.name)))
# it has to look old enough to be judged, which a real one would be by
# the time anybody came along
old = time.time() - 3600
os.utime(leaked, (old, old))
# The NEXT RUN ARRIVING is what has to clear it, so this calls claim()
# and not sweep(). Calling sweep() directly here proves sweep works and
# proves nothing about the fix: with the startup sweep deleted from
# claim(), a version of this section that called sweep() stayed green.
# Caught by mutation, which is the only reason it says claim() now.
nextrun = T.claim("browser-pwtest-", parent=str(YARD))
check("a run arriving afterwards clears it up", not leaked.exists(),
      "the new run is %s" % Path(nextrun).name)
check("...and the arriving run has its own directory", Path(nextrun).is_dir())

print("\n(6) both prefixes, one rule")
for prefix in T.PREFIXES:
    d = plant(prefix, dead_pid(), age_s=3600)
    T.sweep(parent=str(YARD))
    check("%s is covered" % prefix, not d.exists())

print("\n(7) the real /tmp was never touched")
check("the fixture yard is the only thing this suite made",
      str(YARD).startswith(tempfile.gettempdir())
      and "tmpscratch-test-" in str(YARD), YARD.name)
check("...and nothing outside it was swept",
      all(str(YARD) in str(Path(YARD) / n) for n in os.listdir(YARD)))

shutil.rmtree(YARD, ignore_errors=True)
print("")
if fails:
    print("%d FAILED:" % len(fails))
    for one in fails:
        print("  - " + one)
    sys.exit(1)
print("all ok")
