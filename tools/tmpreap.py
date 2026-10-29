#!/usr/bin/env python3
"""Take back the scratch directories the suites left in /tmp.

/tmp here is tmpfs, so a directory left behind is RAM the next suite
cannot have. On 2026-10-29 there were 1,348 of them holding 3.7 GB,
60% of /tmp, and a write from another session failed because of it.

Two leaks made them, and only one was known about:

  browser-pwtest-<pid>   tests/harness.py. It HAS a cleanup, and the
      cleanup has an age gate in front of its own pid check -- it
      skips anything under a day old BEFORE asking whether the process
      is still there. A run killed by a timeout is provably finished,
      and its directory was kept for 24 hours anyway.
  browsershot-<random>   _boot.py. No cleanup at all. Every suite that
      imports it leaked one, permanently. harness.py's docstring
      describes the exact failure this causes -- a browser that cannot
      write its profile dies in a way that looks like a bug in
      whatever it was doing -- and the file one directory away did not
      have the fix.

What makes a directory safe to take:

  named with a pid   the pid no longer exists. That is sufficient on
      its own: the process that owned it is gone. (A recycled pid can
      only make this MORE conservative -- it looks alive, so we leave
      it.)
  named at random    no process has it open or is sitting in it, and
      it has not been touched for --min-age seconds. Both are checked
      through /proc rather than assumed.

Default is a dry run. --go does the work.
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

PREFIXES = ("browser-pwtest-", "browsershot-")

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--go", action="store_true",
                help="actually remove them (default: say what would go)")
ap.add_argument("--min-age", type=int, default=1800, metavar="SECONDS",
                help="leave a randomly-named directory alone until it "
                     "has been untouched this long (default 1800)")
ap.add_argument("--dir", default="/tmp", metavar="PATH")
ARGS = ap.parse_args()
ROOT = Path(ARGS.dir)


def live_paths():
    """Every path a running process has open or is sitting in.

    Read from /proc, so a directory in use is never guessed at. A
    process we may not look inside is skipped rather than assumed
    idle -- which keeps the answer conservative.
    """
    busy = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        for where in ("cwd", "root", "exe"):
            try:
                busy.add(os.readlink(proc / where))
            except OSError:
                pass
        try:
            for fd in (proc / "fd").iterdir():
                try:
                    busy.add(os.readlink(fd))
                except OSError:
                    pass
        except OSError:
            pass
    return busy


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True            # exists, not ours: treat as alive
    return True


def main():
    if not ROOT.is_dir():
        print("no such directory: %s" % ROOT)
        return 2
    busy = live_paths()
    now = time.time()
    go, keep, bytes_freed = [], [], 0
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_dir() or not entry.name.startswith(PREFIXES):
            continue
        tail = entry.name.rsplit("-", 1)[-1]
        if tail.isdigit():
            if pid_alive(int(tail)):
                keep.append((entry, "its process is still running"))
                continue
            why = "its process is gone"
        else:
            held = [p for p in busy if p.startswith(str(entry))]
            if held:
                keep.append((entry, "a running process has it open"))
                continue
            try:
                idle = now - entry.stat().st_mtime
            except OSError:
                continue
            if idle < ARGS.min_age:
                keep.append((entry, "touched %d s ago" % idle))
                continue
            why = "untouched for %d s, nothing has it open" % int(idle)
        size = 0
        for path, _dirs, files in os.walk(entry):
            for name in files:
                try:
                    size += os.lstat(os.path.join(path, name)).st_size
                except OSError:
                    pass
        go.append((entry, why, size))
        bytes_freed += size

    for entry, why in keep[:6]:
        print("  keep  %-34s %s" % (entry.name, why))
    if len(keep) > 6:
        print("  keep  ... and %d more" % (len(keep) - 6))
    print("")
    print("%d to take, %.1f GB; %d kept"
          % (len(go), bytes_freed / 1e9, len(keep)))
    if not ARGS.go:
        print("dry run. --go to do it.")
        return 0
    gone = 0
    for entry, _why, _size in go:
        shutil.rmtree(entry, ignore_errors=True)
        if not entry.exists():
            gone += 1
    print("removed %d of %d" % (gone, len(go)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
