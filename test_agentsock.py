#!/usr/bin/env python3
"""Both ends of the agent bridge agree where the socket is.

`browser --agent` is the headless mode whose entire purpose is to be
driven by agent.py, and agent.py could not reach it. browser.py did
`agent_bridge.SOCKET_NAME += "-agent"`, which reached the server's
constant; agent.py carried its own copy of both the name and
socket_path() and never heard. Measured before the fix:

    normal    server /tmp/browser-agent        client /tmp/browser-agent
    --agent   server /tmp/browser-agent-agent  client /tmp/browser-agent

Deterministic, in every shipped build, and silent: listen() returned
False, install() turned that into None, and browser.py only printed on
an exception -- so the first thing to notice was a KeyError three
frames away pointing at the bridge instead of the path.

No Qt in here: the point is that the client's half needs none, which
is why the duplication existed in the first place."""
import ast
import io
import os
import socket
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent_socket as A  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


print("\n(1) one name, one path, both ends")
check("the bridge takes its path from agent_socket",
      "agent_socket.socket_path" in (HERE / "agent_bridge.py").read_text())
check("...and the client does too",
      "agent_socket.candidate_paths" in (HERE / "agent.py").read_text())
for name, text in (("agent_bridge.py",
                    (HERE / "agent_bridge.py").read_text()),
                   ("agent.py", (HERE / "agent.py").read_text())):
    check("%s holds no second name of its own" % name,
          'SOCKET_NAME = "browser-agent"' not in text)

print("\n(2) the headless mode is reachable, which is the bug")
# the client resolves by looking, so plant a real socket at the
# headless path and check the client picks it
live = []
for headless in (False, True):
    path = A.socket_path(headless)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        if os.path.exists(path) and A.is_ours(path):
            os.unlink(path)
        srv.bind(path)
        srv.listen(1)
        live.append((srv, path))
        chose = None
        for cand in A.candidate_paths():
            if A.is_ours(cand):
                chose = cand
                break
        check("with only the %s socket up, the client picks it"
              % ("headless" if headless else "normal"),
              chose == path, "%s vs %s" % (chose, path))
    except OSError as e:
        check("could bind %s" % path, False, e)
    finally:
        for srv_, path_ in live:
            srv_.close()
            try:
                os.unlink(path_)
            except OSError:
                pass
        live = []

print("\n(3) the directory is private, and chosen by looking")
here = A.socket_dir()
check("a real directory", os.path.isdir(here), here)
info = os.stat(here)
check("owned by us", info.st_uid == os.getuid(), info.st_uid)
if here.startswith("/run/user/") or os.environ.get("XDG_RUNTIME_DIR"):
    check("...and not world-writable",
          not (info.st_mode & stat.S_IWOTH), oct(info.st_mode))
else:
    check("SKIPPED: no runtime dir on this box, so $TMPDIR it is", True,
          here)
check("an explicit directory is obeyed",
      (os.environ.__setitem__(A.DIR_ENV, "/tmp"),
       A.socket_dir())[1] == "/tmp")
os.environ.pop(A.DIR_ENV, None)
check("an explicit full path is obeyed",
      (os.environ.__setitem__(A.PATH_ENV, "/tmp/zz-agent"),
       A.socket_path())[1] == "/tmp/zz-agent")
os.environ.pop(A.PATH_ENV, None)

print("\n(4) the ceiling is measured, or it is not reported")
limit = A.sun_path_max()
check("a limit came back from the kernel", limit is not None, limit)
if limit is not None:
    check("...and it is the usable maximum, not sizeof(sun_path)",
          90 < limit < 110, limit)
    probe = A.socket_dir() + "/" + "x" * limit
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(probe)
        over = False
        os.unlink(probe)
    except OSError:
        over = True
    finally:
        sock.close()
    check("a path one past it really is refused", over,
          "len %d" % len(probe))
check("sun_path_max returns None rather than a guess when it cannot "
      "measure (by construction)",
      "return best" in io.open(HERE / "agent_socket.py").read()
      and "return None" in io.open(HERE / "agent_socket.py").read())

print("\n(5) ownership is checked before connecting and before unlinking")
src = (HERE / "agent_bridge.py").read_text()
check("the bridge only unlinks a socket that is ours",
      src.count("agent_socket.is_ours") >= 2, src.count("is_ours"))
check("...and never removeServer on a bare name",
      "removeServer(SOCKET_NAME)" not in src)
TREE = ast.parse(src)
for fn in ast.walk(TREE):
    if isinstance(fn, ast.FunctionDef) and fn.name == "close":
        has = any(isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") == "is_ours"
                  for n in ast.walk(fn))
        check("close() checks before it unlinks, since it runs at every "
              "normal exit", has)
check("the client checks ownership before connecting",
      "is_ours" in (HERE / "agent.py").read_text())
check("a path that is not a socket is not ours",
      not A.is_ours(str(HERE / "agent.py")))
check("a directory is not ours either", not A.is_ours("/tmp"))

print("\n(6) the failure is loud")
check("the bridge explains a refusal instead of returning in silence",
      "_why_not" in src and "cannot listen on" in src)
# the literal is NOT what to look for: the bridge references the
# constant, which is the coupling that matters. Asking for the string
# "BROWSER_AGENT_SOCKET_DIR" in the source would be satisfied by
# hardcoding it and broken by doing it right -- which is what the first
# version of this row did, and it went red against correct code.
check("...and names the override through the constant",
      "agent_socket.DIR_ENV" in src)

print()
if fails:
    print("%d FAILED:" % len(fails))
    for one in fails:
        print("  - " + one)
    sys.exit(1)
print("all ok")
