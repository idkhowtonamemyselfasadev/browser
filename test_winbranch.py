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
import shutil
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
    B.os.environ["USERNAME"] = "ada"
    B._restrict_to_owner(target)
finally:
    B.subprocess.run = real_run
check("one call, to icacls", len(ran) == 1 and ran[0][0][0][0] == "icacls",
      ran)
cmd = ran[0][0][0] if ran else []
check("it names the file", str(target) in cmd, cmd)
check("inherited entries are dropped", "/inheritance:r" in cmd, cmd)
check("and this user, alone, is granted full control",
      "/grant:r" in cmd and "ada:F" in cmd, cmd)
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
    B.os.environ["USERNAME"] = "ada"
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

# ---------------------------------------------------------------------
print("\n(6) the screen stays awake there too, by the call Windows has")
# systemd-inhibit does not exist on Windows, so the feature was simply
# off there: keep_awake found no tool and answered False for ever.
# Windows has one call for this - SetThreadExecutionState - and it is a
# standing request rather than a child process.


class FakeK32:
    def __init__(self, answer=1):
        self.asked = []
        self.answer = answer

    def SetThreadExecutionState(self, flags):
        self.asked.append(flags)
        return self.answer


class PowerStub:
    """Enough of a Browser for the branch: the two flag constants come
    from the real class, so a change to them is a change to this."""
    _WIN_AWAKE_ON = B.Browser._WIN_AWAKE_ON
    _WIN_AWAKE_OFF = B.Browser._WIN_AWAKE_OFF

    def __init__(self, k32):
        self._k32 = k32

    def _win_power(self):
        return self._k32

    # the branch under test calls this on self; the real one is what we
    # want run, so it is borrowed from the class rather than faked
    _keep_awake_windows = B.Browser._keep_awake_windows


k32 = FakeK32()
stub = PowerStub(k32)
check("asking holds it", B.Browser._keep_awake_windows(stub, True) is True)
check("...with ES_CONTINUOUS, the screen and the machine",
      k32.asked == [0x80000003], [hex(a) for a in k32.asked])
check("...and it says it is holding", stub._awake_win is True)
check("letting go answers False",
      B.Browser._keep_awake_windows(stub, False) is False)
check("...by asking for nothing, which is ES_CONTINUOUS alone",
      k32.asked[-1] == 0x80000000, hex(k32.asked[-1]))
check("the flags are the documented ones",
      (B.Browser._WIN_AWAKE_ON, B.Browser._WIN_AWAKE_OFF)
      == (0x80000003, 0x80000000),
      (hex(B.Browser._WIN_AWAKE_ON), hex(B.Browser._WIN_AWAKE_OFF)))

refused = PowerStub(FakeK32(answer=0))
check("a refusal from Windows is not reported as a hold",
      B.Browser._keep_awake_windows(refused, True) is False)
check("and with no kernel32 under us it answers False, never raises",
      B.Browser._keep_awake_windows(PowerStub(None), True) is False)
check("_win_power answers None on this machine rather than raising",
      B.Browser._win_power(PowerStub(None)) is None)

real_sys = B.sys
try:
    fake_sys = Fake()
    fake_sys.platform = "win32"
    B.sys = fake_sys
    held = PowerStub(FakeK32())
    held._awake_win = True
    check("awake_holding reads that standing request on Windows",
          B.Browser.awake_holding(held) is True)
    held._awake_win = False
    check("...and nothing held is nothing held",
          B.Browser.awake_holding(held) is False)
    sent = PowerStub(FakeK32())
    check("keep_awake goes down that branch instead of looking for a tool",
          B.Browser.keep_awake(sent, True) is True)
finally:
    B.sys = real_sys

# ---------------------------------------------------------------------
print("\n(7) an address for another program, where the shell owns them")
# The Linux half looks for a binary by name: thunderbird, discord,
# steam. None of those is on the PATH under that name on Windows, where
# the register of who owns a scheme belongs to the shell - so the
# browser used to say "nothing on this machine can open a discord:
# address" on a machine where Discord was installed and working.


class Teller:
    def __init__(self):
        self.said = []
        self.remembered = []

    def flash(self, text):
        self.said.append(text)

    def _ui_str(self, key):
        return B.UI_STRINGS["en"][key]

    def set_scheme_app(self, scheme, program, host=""):
        self.remembered.append((scheme, program, host))
        return program


opened = []
had_startfile = hasattr(os, "startfile")
os.startfile = lambda target: opened.append(target)
try:
    teller = Teller()
    got = B.Browser._open_with_shell(
        teller, "discord://invite/abc", "discord", "example.com", ask=False)
    check("the address goes to the shell", opened == ["discord://invite/abc"],
          opened)
    check("...and that is reported as who opened it", got == "windows-shell",
          got)
    check("...in words naming the scheme, not a program it guessed",
          teller.said == ["Handed to Windows (discord:)"], teller.said)
    check("nothing is remembered when it was not asked",
          teller.remembered == [], teller.remembered)

    def no_handler(target):
        raise OSError(1155, "no application is associated")

    os.startfile = no_handler
    teller2 = Teller()
    check("a scheme with no program behind it answers False",
          B.Browser._open_with_shell(teller2, "nope9://x", "nope9",
                                     ask=False) is False)
    check("...and says so in the browser's own words",
          teller2.said == ["Nothing on this machine can open a nope9: "
                           "address."], teller2.said)
finally:
    if had_startfile:                      # pragma: no cover - not Windows
        pass
    else:
        del os.startfile

check("every word it says exists in both languages",
      all(key in B.UI_STRINGS["en"] and key in B.UI_STRINGS["de"]
          for key in ("navShellName", "navShellAsk", "navShellGave")),
      [k for k in ("navShellName", "navShellAsk", "navShellGave")
       if k not in B.UI_STRINGS["de"]])
check("the German ones are German, not the English left in place",
      B.UI_STRINGS["de"]["navShellGave"]
      != B.UI_STRINGS["en"]["navShellGave"])
check("open_with_app really takes that branch on Windows",
      'if sys.platform == "win32":\n            return self._open_with_shell('
      in SRC)
check("...and an http address is still never handed to anything",
      'in ("http", "https", "file", "about",' in SRC)

# ---------------------------------------------------------------------
print("\n(8) what the tabs are costing, where there is no /proc")
# process_cost and renderer_cpu read /proc, and said so: on Windows they
# answered nothing at all and every row of "what this is costing" was
# blank -- which reads as a broken page rather than a platform the code
# never asked about. Windows has the same two numbers in two calls.
asked = []


def probe(pid):
    asked.append(pid)
    # a working set of 300 MB, and 1.5 s kernel + 2.5 s user in Windows'
    # own 100-nanosecond units
    return (300 * 1024 * 1024, 15_000_000, 25_000_000)


cost = B._win_process_cost(4242, probe)
check("the pid asked about is the pid handed over", asked == [4242], asked)
check("the working set comes back as bytes",
      cost.get("bytes") == 300 * 1024 * 1024, cost)
check("kernel and user time together, in seconds",
      cost.get("seconds") == 4.0, cost)
check("and the pid is in the answer, as on the other platform",
      cost.get("pid") == 4242, cost)
check("a process that cannot be asked is {}, not a crash",
      B._win_process_cost(4242, lambda pid: None) == {})


def explodes(pid):
    raise OSError("gone")


check("a probe that raises is {} too",
      B._win_process_cost(4242, explodes) == {})
check("the real probe is what it reaches for by default",
      B._WIN_PROBE is B._win_process_probe)
check("...and that one answers None here rather than raising",
      B._win_process_cost(os.getpid()) == {})

real_sys = B.sys
try:
    fake_sys = Fake()
    fake_sys.platform = "win32"
    B.sys = fake_sys
    real_probe = B._WIN_PROBE
    B._WIN_PROBE = probe
    try:
        asked.clear()
        got = B.Browser.process_cost(99)
        check("process_cost goes that way on Windows",
              got.get("seconds") == 4.0 and asked == [99], (got, asked))
        seconds = B.Browser.renderer_cpu(Fake(), 99)
        check("...and so does renderer_cpu, in seconds",
              seconds == 4.0, seconds)
        check("a pid of nothing is still nothing",
              B.Browser.process_cost(0) == {})
        B._WIN_PROBE = lambda pid: None
        check("a renderer that has gone is 0.0 seconds, not an error",
              B.Browser.renderer_cpu(Fake(), 99) == 0.0)
    finally:
        B._WIN_PROBE = real_probe
finally:
    B.sys = real_sys

check("the Linux reading still works, on this machine, right now",
      B.Browser.process_cost(os.getpid()).get("bytes", 0) > 0,
      B.Browser.process_cost(os.getpid()))
check("memory pressure says nothing on Windows rather than a wrong number",
      "no counter" in (B.Browser.memory_pressure.__doc__ or ""),
      (B.Browser.memory_pressure.__doc__ or "")[:80])

# ---------------------------------------------------------------------
print("\n(9) reading a page aloud, where there is no speech-dispatcher")
# spd-say is a speech-dispatcher client and is what a Linux desktop has.
# Windows has none, so the browser said "no speech program installed" --
# on a machine whose own .NET has had a synthesiser in it for twenty
# years. PowerShell drives that one.
import base64  # noqa: E402


class Reader(Teller):
    _SAY_PS = B.Browser._SAY_PS
    _say_windows = B.Browser._say_windows
    _say_check = B.Browser._say_check
    stop_aloud = B.Browser.stop_aloud
    say_tool = B.Browser.say_tool


class FakePopen:
    made = []

    def __init__(self, argv, **kw):
        self.argv = argv
        self.kw = kw
        self.written = b""
        self.killed = False
        self.returncode = None
        FakePopen.made.append(self)
        parent = self

        class Pipe:
            def write(self, data):
                parent.written += data

            def close(self):
                pass
        self.stdin = Pipe()

    def kill(self):
        self.killed = True

    def poll(self):
        return self.returncode


real_sys, real_popen = B.sys, B.subprocess.Popen
try:
    fake_sys = Fake()
    fake_sys.platform = "win32"
    B.sys = fake_sys
    B.subprocess.Popen = FakePopen
    FakePopen.made = []
    reader = Reader()
    proc = reader._say_windows("H\u00f6rst du mich?", "de", 40)
    check("a reader is started", proc is not None and len(FakePopen.made) == 1)
    argv = proc.argv if proc else []
    check("...which is powershell, with no profile and no prompt",
          argv[:4] == ["powershell", "-NoProfile", "-NonInteractive",
                       "-Command"], argv[:4])
    script = argv[4] if len(argv) > 4 else ""
    check("it uses the synthesiser .NET already has",
          "System.Speech" in script and "SpeechSynthesizer" in script)
    check("the rate is carried over, on that platform's own scale",
          "$s.Rate = 4;" in script, script[:140])
    check("a voice for the language is asked for, and failing is allowed",
          "GetCultureInfo('de')" in script and "catch {}" in script)
    check("no console window flashes over the page",
          "creationflags" in (proc.kw if proc else {}))
    check("the text goes in through stdin, base64, so quoting cannot bite",
          proc.written == base64.b64encode("H\u00f6rst du mich?".encode()),
          proc.written)
    check("...and comes back out as itself, umlaut included",
          base64.b64decode(proc.written).decode("utf-8")
          == "H\u00f6rst du mich?")
    check("a language that is not one is not pasted into the script",
          "';" not in (reader._say_windows("x", "de'; rm -rf /", 0).argv[4]),
          reader._say_windows("x", "de'; rm -rf /", 0).argv[4][:120])

    # what happens when the synthesiser falls over at once
    reader._say = proc
    proc.returncode = 1
    check("a reader that fell over says so rather than claiming to read",
          reader._say_check() is False
          and reader.said[-1] == B.UI_STRINGS["en"]["sayFailed"],
          reader.said)
    proc.returncode = None
    check("...and one that is still going says nothing",
          reader._say_check() is True)

    # and stopping it
    started = []
    real_detached = B.QProcess.startDetached
    try:
        B.QProcess.startDetached = staticmethod(
            lambda *a, **k: started.append(a))
        reader._say = proc
        check("stopping it kills the reader", reader.stop_aloud() is True
              and proc.killed is True)
        check("...and nothing is asked of a speech daemon that is not there",
              started == [], started)
    finally:
        B.QProcess.startDetached = real_detached
    looked = []
    real_which = B.shutil.which
    try:
        B.shutil.which = lambda name: (looked.append(name),
                                       "C:/Windows/" + name)[1]
        found = B.Browser.say_tool(reader)
    finally:
        B.shutil.which = real_which
    check("say_tool looks for powershell there, not for spd-say",
          looked == ["powershell"] and found.endswith("powershell"),
          (looked, found))
finally:
    B.sys, B.subprocess.Popen = real_sys, real_popen

check("on this machine it is still speech-dispatcher that is looked for",
      B.Browser.say_tool(Reader()) == (shutil.which("spd-say") or ""))
check("the reader's words exist in both languages",
      all(B.UI_STRINGS["en"].get(k) and B.UI_STRINGS["de"].get(k)
          for k in ("sayStarted", "sayFailed", "sayMissing", "sayNothing")))

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
