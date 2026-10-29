#!/usr/bin/env python3
"""One scratch directory per test run, and whoever comes next clears up.

/tmp on this machine is tmpfs, so a directory left behind is RAM the
next suite cannot have. On 2026-10-29 there were 1,348 of them holding
3.7 GB -- 60% of /tmp -- and a write from another session failed
because of it. What that looks like from inside a suite is not "no
space left": it is the last few tests segfaulting and timing out,
because a browser that cannot write its profile dies in a way that
looks like a bug in whatever it was doing. tests/harness.py's own
docstring has described that failure for a long time, for disk.

It leaked anyway, for three reasons that had to be separated before
any of them could be fixed:

  _boot.py had no cleanup at all. 33 suites import it.

  atexit does not run when a process dies by a signal or calls
  os._exit -- and 19 suites end with os._exit, to dodge a Qt teardown
  segfault. So the runs most likely to leak are exactly the ones that
  opted out of the mechanism that would have tidied up.

  the sweep of OTHER runs' leavings asked the age before the liveness:
  it skipped anything under a day old and only then checked whether
  the process still existed. The age did the deciding, liveness was
  never reached for anything from the same day, and a day of a suite's
  own output is gigabytes.

So: sweep at STARTUP as well as at exit. The run that made the mess is
precisely the run that cannot be relied on to clear it, so the next
one does. browser-mac-8f's fix; the diagnosis is theirs and windows'.

Liveness decides, and the pid is in the name for that reason -- both
prefixes now, which is the change that lets one rule cover both. A
recycled pid can only make this MORE careful: it looks alive, so the
directory is left. A minute of grace on top, so a sibling that has
made its directory but not yet written to it is never raced.
"""
import atexit
import os
import shutil
import tempfile
import time

PREFIXES = ("browser-pwtest-", "browsershot-")
GRACE_S = 60


def _pid_of(name):
    """The pid a scratch directory is named for, or None."""
    tail = name.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True            # exists and is not ours: leave it
    return True


def sweep(parent=None):
    """Take away every scratch directory whose process has gone.

    Returns the names removed, so a test can watch it work rather than
    take its word.
    """
    parent = parent or tempfile.gettempdir()
    now = time.time()
    gone = []
    try:
        names = os.listdir(parent)
    except OSError:
        return gone
    for name in names:
        if not name.startswith(PREFIXES):
            continue
        path = os.path.join(parent, name)
        if not os.path.isdir(path):
            continue
        pid = _pid_of(name)
        if pid is None:
            continue           # an older name, before the pid went in
        if _alive(pid):
            continue
        try:
            if now - os.path.getmtime(path) < GRACE_S:
                continue       # made, not yet written to: not ours to judge
        except OSError:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            gone.append(name)
    return gone


def claim(prefix, parent=None):
    """This run's own scratch directory, swept for and swept after.

    The pid goes in the NAME, as a suffix, so the sweep above can ask
    whether the owner is still running. mkdtemp keeps the uniqueness.
    """
    sweep(parent)
    path = tempfile.mkdtemp(prefix=prefix, suffix="-%d" % os.getpid(),
                            dir=parent)
    atexit.register(lambda: shutil.rmtree(path, ignore_errors=True))
    return path
