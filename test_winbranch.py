#!/usr/bin/env python3
"""The Windows branches of this file, checked on Linux.

browser.py is one file for both editions, and the Windows one is
generated from it (see tools/win_port.json in browser-windows). The
branches that only Windows takes are therefore written here and run
nowhere: nobody on this machine finds out when one of them stops
making sense, and the one that proved it was a call left behind by a
port whose definition never came with it -- `_write_atomic` has been
asking `_restrict_to_owner` to lock a vault down since the bug sweep,
and the name did not exist in this file at all. On Linux the branch is
never taken, so nothing failed; on Windows the other edition happened
to carry a copy. Nothing checked that it still did.

So: every win32 branch in this file, exercised here.

  * the folder everything of his lives in, built by running the real
    statements out of the real file with a `sys` and an `os` of our
    choosing -- faking sys.platform and importing does not work, the
    standard library reads it too;
  * the ACL helper, called for real with what it shells out to gone;
  * `_write_private` down both sides of its branch;
  * the glass look, which must not ask for an alpha window there;
  * and the two things main() only does on Windows, read out of its
    source, because main() cannot be run twice in one process.

Nothing here writes outside a throwaway directory, and nothing here
needs the network or a window.
"""
import ast
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402

SCRATCH = Path(tempfile.mkdtemp(prefix="winbranch-"))
SRC = (HERE / "browser.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def source_of(name):
    """One top-level def's source, by name."""
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return ast.get_source_segment(SRC, node) or ""
    return ""


# ---------------------------------------------------------------------
print("(1) where everything of his is kept, on either platform")
WANTED = {"BROWSER_HOME", "CONFIG_FILE", "HOSTS_FILE", "HISTORY_FILE",
          "DOWNLOADS_FILE", "BOOKMARKS_FILE"}


def assigns(node):
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


REGION = [n for n in TREE.body if assigns(n) & WANTED]


class Fake:
    pass


def build(platform, environ):
    """Run that region with a sys and an os of our choosing."""
    fake_sys, fake_os = Fake(), Fake()
    fake_sys.platform = platform
    fake_os.environ = environ
    ns = {"sys": fake_sys, "os": fake_os, "Path": Path, "QUrl": B.QUrl,
          "APP_DIR": HERE}
    exec(compile(ast.Module(body=REGION, type_ignores=[]),
                 "<browser-home region>", "exec"), ns)
    return {k: str(ns[k]) for k in WANTED if k in ns}


check("the statements that build them were all found",
      len(REGION) >= 2
      and WANTED <= set().union(*(assigns(n) for n in REGION)),
      len(REGION))

appdata = str(SCRATCH / "AppData" / "Local")
win = build("win32", {"LOCALAPPDATA": appdata})
want = str(Path(appdata) / "browser")
check("on Windows it is %LOCALAPPDATA%\\browser",
      win["BROWSER_HOME"] == want, win["BROWSER_HOME"])
for key in ("CONFIG", "HISTORY", "DOWNLOADS", "HOSTS", "BOOKMARKS"):
    check("%s.json sits under it" % key.lower(),
          win[key + "_FILE"] == str(Path(want) / (key.lower() + ".json")),
          win[key + "_FILE"])
check("and nothing of his lands on a POSIX path there",
      not any(".local/share" in v for v in win.values()), win)
check("with no %LOCALAPPDATA% at all it falls back to the home folder",
      build("win32", {})["BROWSER_HOME"] == str(Path.home() / "browser"),
      build("win32", {})["BROWSER_HOME"])
check("on Linux the very same statements give the POSIX path",
      build("linux", {})["BROWSER_HOME"]
      == str(Path.home() / ".local/share/browser"),
      build("linux", {})["BROWSER_HOME"])
for plat in ("win32", "linux"):
    moved = build(plat, {"BROWSER_HOME": str(SCRATCH / "elsewhere"),
                         "LOCALAPPDATA": appdata})
    check("BROWSER_HOME still moves all of it at once (%s)" % plat,
          moved["BROWSER_HOME"] == str(SCRATCH / "elsewhere")
          and moved["CONFIG_FILE"]
          == str(SCRATCH / "elsewhere" / "config.json"), moved)
check("imported normally, it is this machine's own folder",
      str(B.BROWSER_HOME).startswith(str(Path.home())), str(B.BROWSER_HOME))

# ---------------------------------------------------------------------
print("\n(2) making a file owner-only where there is no chmod to do it")
check("the name _write_atomic has been calling exists",
      callable(getattr(B, "_restrict_to_owner", None)))
check("and _write_atomic really does call it",
      "_restrict_to_owner(tmp)" in source_of("_write_atomic"))

target = SCRATCH / "vault" / "passwords.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(b"secret")

ran = []
real_run = subprocess.run
try:
    B.subprocess.run = lambda *a, **k: ran.append((a, k))
    B.os.environ["USERNAME"] = "tim"
    B._restrict_to_owner(target)
finally:
    B.subprocess.run = real_run
check("one call, to icacls", len(ran) == 1 and ran[0][0][0][0] == "icacls",
      ran)
cmd = ran[0][0][0] if ran else []
check("it names the file", str(target) in cmd, cmd)
check("inherited entries are dropped", "/inheritance:r" in cmd, cmd)
check("and this user, alone, is granted full control",
      "/grant:r" in cmd and "tim:F" in cmd, cmd)
check("no console window flashes up under pythonw",
      ran and "creationflags" in ran[0][1], ran[0][1] if ran else None)
check("it does not wait forever on a wedged icacls",
      ran and ran[0][1].get("timeout"), ran[0][1] if ran else None)

ran = []
try:
    B.os.environ.pop("USERNAME", None)
    B.subprocess.run = lambda *a, **k: ran.append(a)
    B._restrict_to_owner(target)
finally:
    B.subprocess.run = real_run
check("with no USERNAME to grant to it does nothing at all", not ran, ran)


def explode(*a, **k):
    raise FileNotFoundError(2, "icacls")


try:
    B.os.environ["USERNAME"] = "tim"
    B.subprocess.run = explode
    B._restrict_to_owner(target)
    survived = True
except Exception as exc:                       # pragma: no cover - the bug
    survived = False
    print("   raised: %r" % (exc,))
finally:
    B.subprocess.run = real_run
check("a machine without icacls is not a crash while saving a password",
      survived)
check("and the file is still there, with what was in it",
      target.read_bytes() == b"secret")

# ---------------------------------------------------------------------
print("\n(3) _write_private, down both sides of the branch")
posix_file = SCRATCH / "posix" / "key"
B._write_private(posix_file, b"\x00\x01key bytes\n")
check("the bytes arrive exactly", posix_file.read_bytes()
      == b"\x00\x01key bytes\n")
mode = stat.S_IMODE(posix_file.stat().st_mode)
check("and here it is 0600, as it always was", mode == 0o600, oct(mode))

called = []
win_file = SCRATCH / "win" / "key"
real_sys, real_restrict, real_chmod = B.sys, B._restrict_to_owner, B.os.chmod
try:
    fake_sys = Fake()
    fake_sys.platform = "win32"
    fake_sys.argv = real_sys.argv
    B.sys = fake_sys
    B._restrict_to_owner = lambda p: called.append(Path(p))
    B.os.chmod = lambda *a, **k: called.append("chmod")
    B._write_private(win_file, b"win bytes")
finally:
    B.sys, B._restrict_to_owner = real_sys, real_restrict
    B.os.chmod = real_chmod
check("on Windows the file is locked down by ACL", called == [win_file],
      called)
check("and os.chmod, which does nothing there, is not called instead",
      "chmod" not in called, called)
check("the bytes still arrive", win_file.read_bytes() == b"win bytes")

# ---------------------------------------------------------------------
print("\n(4) glass does not ask Windows for a window it cannot blur")
real_sys = B.sys
try:
    fake_sys = Fake()
    fake_sys.platform = "win32"
    B.sys = fake_sys
    win_glass = B.look_style("glass", "mocha")
    win_classic = B.look_style("classic", "mocha")
finally:
    B.sys = real_sys
lin_glass = B.look_style("glass", "mocha")
check("on Windows glass sits on a solid base",
      "QMainWindow, #root" in win_glass and "background" in win_glass,
      win_glass[-120:])
check("on Linux it does not (the compositor blurs it there)",
      "QMainWindow, #root { background: #000000; }" not in lin_glass)
check("and classic is untouched on both",
      win_classic == B.look_style("classic", "mocha"))

init = source_of("Browser") or ""
if not init:
    for node in ast.walk(TREE):
        if isinstance(node, ast.ClassDef) and node.name == "Browser":
            init = ast.get_source_segment(SRC, node) or ""
            break
spot = init.find("WA_TranslucentBackground")
guard = init[max(0, spot - 400):spot]
check("the alpha window itself is asked for only off Windows",
      'active_look() == "glass" and sys.platform != "win32"' in guard,
      guard[-120:])

# ---------------------------------------------------------------------
print("\n(5) the two things main() only does on Windows")
main_src = source_of("main")
check("main() was found", bool(main_src))
check("the taskbar is told which app this is",
      "SetCurrentProcessExplicitAppUserModelID" in main_src)
check("...before the QApplication exists, which is the only time it works",
      main_src.find("SetCurrentProcessExplicitAppUserModelID")
      < main_src.find("app = QApplication("), main_src.find("app = QAppl"))
check("the window icon is the .ico there and the .svg here",
      'icon = "icon.ico" if sys.platform == "win32" else "icon.svg"'
      in main_src)
check("and this edition still ships the .svg it names",
      (HERE / "icon.svg").exists())

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
