#!/usr/bin/env python3
"""The Update button, on a copy that cannot update itself.

A folder unpacked from a zip has no .git. Git run inside one does not
fail politely — it walks *up* the tree looking for a repository and
reports what it finds on the way out, which is how "Stopping at
filesystem boundary" ends up in front of somebody who pressed a button
called Update. Worse: if an unrelated repository happens to sit above
the folder, git finds that one and pulls it.

So the button asks the folder whether it is a working copy before it
starts git at all. These checks are that promise, and the message it
gives instead.

Offscreen, against scratch data only — _boot redirects the config, the
history, the downloads, the hosts, the bookmarks and XDG_DATA_HOME into
a temporary directory before the browser is ever built.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  <%s>" % detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()

said = []
win.bridge.updateFinished.connect(lambda m: said.append(m))
real_app_dir = B.APP_DIR

# The two editions answer this differently on purpose, and the whole
# point of _update_without_clone is that the difference lives in one
# method. The Windows one is shipped as a zip and fetches a newer one;
# this one has no such route and can only say so. Both must refuse to
# run git, which is the property that matters either way.
ZIP_EDITION = hasattr(win.bridge, "_zip_update")
zip_calls = []
if ZIP_EDITION:
    win.bridge._zip_update = lambda *a: zip_calls.append(1)

print("\na folder that came out of a zip")
zipped = Path(tempfile.mkdtemp())
(zipped / "browser.py").write_text("# stand-in for the real thing\n")
B.APP_DIR = zipped
said.clear()
win.bridge.runUpdate()
app.processEvents()

if ZIP_EDITION:
    check("this edition goes and fetches a zip instead", bool(zip_calls))
    win.bridge._updating = None      # the stub never clears it
else:
    check("it answers rather than sitting there", bool(said))
    msg = said[-1] if said else ""
    check("it says the copy cannot update itself",
          "cannot update itself" in msg, msg)
    check("and says what to do about it",
          "zip" in msg.lower() and "clone" in msg.lower(), msg)
    check("and git's own wording never reaches him",
          "filesystem boundary" not in msg and "GIT_DISCOVERY" not in msg,
          msg)
check("git is never started, so no filesystem-boundary error",
      not isinstance(win.bridge._updating, B.QProcess))

print("\nthe answer is not carried over to the next press")
said.clear()
del zip_calls[:]
win.bridge.runUpdate()
app.processEvents()
check("pressing it again answers again", bool(said) or bool(zip_calls))
if ZIP_EDITION:
    win.bridge._updating = None

print("\na folder with an unrelated repo above it is left alone")
# the dangerous shape: git walking up would find the outer repo and pull
# it. The guard means we never get that far.
outer = Path(tempfile.mkdtemp())
subprocess.run(["git", "init", "-q", str(outer)], check=False,
               capture_output=True)
inner = outer / "browser-main"
inner.mkdir()
(inner / "browser.py").write_text("# stand-in\n")
B.APP_DIR = inner
said.clear()
del zip_calls[:]
win.bridge.runUpdate()
app.processEvents()
if ZIP_EDITION:
    check("still goes for a zip, though a repo sits above it",
          bool(zip_calls))
    win.bridge._updating = None
else:
    check("still refuses, though a repo sits above it",
          bool(said) and "cannot update itself" in said[-1],
          said[-1] if said else "")
check("and started no git process in the outer repo",
      not isinstance(win.bridge._updating, B.QProcess))

print("\na real working copy is still allowed to try")
B.APP_DIR = real_app_dir
check("the browser's own folder is a working copy",
      (real_app_dir / ".git").exists(), str(real_app_dir))
said.clear()
win.bridge.runUpdate()
app.processEvents()
check("so the button gets as far as running git",
      win.bridge._updating is not None or bool(said))
# do not leave a pull running against the real repo
if win.bridge._updating is not None:
    win.bridge._updating.kill()
    win.bridge._updating = None

print("\na copy stranded by the history being rewritten upstream")
# The one case that leaves an installed copy unable to update for ever:
# the published history is replaced, so a fast-forward can never happen
# again and every press of the button reports a deadlock. The folder
# holds only the browser, so the answer is to take what is published.


def git(*args, cwd=None):
    return subprocess.run(("git",) + args, cwd=cwd,
                          capture_output=True, text=True)


work = Path(tempfile.mkdtemp())
up, clone = work / "upstream", work / "clone"
up.mkdir()
git("init", "-q", "-b", "main", str(up))
(up / "a.txt").write_text("the old files, with the name in them\n")
git("add", "-A", cwd=up)
git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "old",
    cwd=up)
git("clone", "-q", str(up), str(clone))

# now rewrite it, exactly as a scrub-and-force-push does
git("checkout", "-q", "--orphan", "fresh", cwd=up)
(up / "a.txt").write_text("the scrubbed files\n")
git("add", "-A", cwd=up)
git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "clean",
    cwd=up)
git("branch", "-M", "fresh", "main", cwd=up)

pull = git("pull", "--ff-only", cwd=clone)
check("a plain pull cannot recover from this on its own",
      pull.returncode != 0,
      (pull.stderr.strip().splitlines() or [""])[-1])
check("so the copy is still on the old files",
      (clone / "a.txt").read_text().strip().endswith("name in them"))

B.APP_DIR = clone
said.clear()
win.bridge.runUpdate()
for _ in range(150):
    if said:
        break
    H_spin = app.processEvents()
    import time as _t
    _t.sleep(0.05)
check("the button answers", bool(said))
check("it took what is published",
      (clone / "a.txt").read_text().strip() == "the scrubbed files",
      (clone / "a.txt").read_text().strip())
check("and says the update landed",
      bool(said) and "Updated" in said[-1], said[-1] if said else "")

B.APP_DIR = real_app_dir
shutil.rmtree(work, ignore_errors=True)
shutil.rmtree(zipped, ignore_errors=True)
shutil.rmtree(outer, ignore_errors=True)

print("\n%d checks failed" % len(fails))
for f in fails:
    print("  - " + f)
app.quit()
sys.exit(1 if fails else 0)
