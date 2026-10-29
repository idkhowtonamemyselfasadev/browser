#!/usr/bin/env python3
"""create=True has to create the DEFAULT folder too.

    def download_dir(self, create=True):
        chosen = ...
        if chosen:
            path.mkdir(parents=True, exist_ok=True)   # created
            ...
        return DOWNLOAD_DIR                            # never created

Every folder except the one most people use. With no ~/Downloads on the
machine, save_article, the subtitle export and every ordinary download
wrote into a directory that was not there.

The docstring made it sharper rather than softer: it already said the
default is for "when he picked none (or picked one that has since gone
away)" -- and the gone-away case is precisely the one that fell past
the mkdir. An external disk that is not plugged in lands exactly there.
Code and docstring disagreed and the docstring was right.

WHY THIS NEEDS ITS OWN SUITE. The bug is invisible on any machine that
happens to have a ~/Downloads, which is nearly all of them.
browser-mac's reading and media suites passed at 11:13 and failed at
13:00 on identical code, purely on whether that folder existed in the
throwaway HOME they were handed. That is not flakiness and "it passed
in my run" is no evidence either way -- it is an environment the suite
has to MAKE rather than find. So every case here points DOWNLOAD_DIR at
a path that is guaranteed not to exist.

Both directions of the contract, because create=False has a promise of
its own: merely asking where downloads go must never conjure the folder
up.

No window, no network, nothing outside its own temp directory.
"""
import os
import shutil
import sys
import tempfile
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

SCRATCH = Path(tempfile.mkdtemp(prefix="browser-dldir-"))


class Fake:
    """Just enough browser: download_dir reads self.config and the
    module global, and nothing else."""
    download_dir = B.Browser.download_dir

    def __init__(self, chosen=""):
        self.config = {"downloadDir": chosen}


def with_default(path):
    """Point the module's default somewhere that does not exist."""
    B.DOWNLOAD_DIR = path
    return path


print("(1) no folder chosen -- the default is made, not assumed")
missing = with_default(SCRATCH / "no-downloads-here")
check("the fixture really is absent to start with",
      not missing.exists(), missing)
got = Fake().download_dir()
check("it answers the default", got == missing, got)
check("...and the folder is there afterwards", missing.exists())

print()
print("(2) ...but only when it was asked to create one")
absent = with_default(SCRATCH / "never-made")
got = Fake().download_dir(create=False)
check("create=False answers the same place", got == absent, got)
check("...and did NOT conjure it up", not absent.exists(), absent)

print()
print("(3) a chosen folder is made, as it always was")
chosen = SCRATCH / "picked" / "deeper"
got = Fake(str(chosen)).download_dir()
check("it answers the chosen one", got == chosen, got)
check("...and made it", chosen.exists())
gone = SCRATCH / "picked2"
got = Fake(str(gone)).download_dir(create=False)
check("create=False answers it without making it",
      got == gone and not gone.exists(), gone)

print()
print("(4) the case the docstring names: the chosen one has gone away")
# an external disk that is not plugged in. A path UNDER a regular file
# cannot be made, which is the same failure mkdir reports.
blocker = SCRATCH / "not-a-folder"
blocker.write_text("this is a file")
fallback = with_default(SCRATCH / "fallback-downloads")
check("the fallback is absent to start with", not fallback.exists())
got = Fake(str(blocker / "sub")).download_dir()
check("it falls through to the default", got == fallback, got)
check("...and the default was made, which is the whole bug",
      fallback.exists(), fallback)

print()
print("(5) and it is idempotent, because it runs on every download")
again = Fake().download_dir()
check("a second call is happy with a folder that exists",
      again == fallback and fallback.exists())
# a default that cannot be made must not raise: a download into an
# impossible folder fails either way, and an exception here would take
# the window with it
with_default(blocker / "impossible")
try:
    got = Fake().download_dir()
    raised = None
except Exception as exc:                            # noqa: BLE001
    raised = exc
check("an impossible default is survived, not raised", raised is None,
      raised)

shutil.rmtree(SCRATCH, ignore_errors=True)
print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
