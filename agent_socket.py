#!/usr/bin/env python3
"""Where the agent bridge's socket is, agreed by both ends.

This exists because the two ends could not agree. agent_bridge.py (the
server, which needs Qt) and agent.py (the client, which deliberately
does not -- "No Qt needed here" is the second line of its docstring)
each carried their own SOCKET_NAME and their own copy of socket_path().
The bodies were identical, so nothing looked wrong; the docstrings had
already drifted, which is the kind of divergence you get just before a
behavioural one.

Then browser.py renamed one of them. Launched headless -- `browser
--agent`, the mode whose entire purpose is to be driven by agent.py --
it does `SOCKET_NAME += "-agent"`, which reaches the server's constant
and not the client's. Measured:

    normal      server /tmp/browser-agent        client /tmp/browser-agent
    --agent     server /tmp/browser-agent-agent  client /tmp/browser-agent

So the headless agent browser could not be reached by the agent client,
deterministically, in every shipped build. The browser even prints the
real path at startup, and the client computes its own and never reads
that line.

Nothing here imports Qt, so both ends can share it.
"""
import os
import socket
import stat

BASE_NAME = "browser-agent"
#: headless adds this, so a `browser --agent` and an ordinary window can
#: both be up without fighting over one socket
HEADLESS_SUFFIX = "-agent"
#: an explicit answer, for a harness with a long temp path or a user who
#: wants two of these side by side
DIR_ENV = "BROWSER_AGENT_SOCKET_DIR"
PATH_ENV = "BROWSER_AGENT_SOCKET"


def sun_path_max():
    """The longest AF_UNIX path this kernel will actually bind, measured.

    Not a constant: it is 107 usable bytes on Linux and 103 on Darwin
    (sizeof(sun_path) less the terminator), and since the whole point
    of knowing it is a diagnostic that tells the truth, a figure from
    the wrong platform's header is worse than none.

    Probed from the SHORTEST writable directory we have, never from the
    temporary directory -- measuring against the thing under test is
    how the first version of this measurement was right on Linux by
    luck (because /tmp is four characters) and wrong on macOS, where a
    long temporary path is the default.

    Returns None when nothing bound at any length, because an
    unmeasurable situation must not produce a plausible number. A
    caller that gets None says so instead of quoting a figure.
    """
    base = None
    for cand in ("/tmp", "/run/user/%d" % os.getuid(),
                 os.path.expanduser("~")):
        if os.path.isdir(cand) and os.access(cand, os.W_OK):
            base = cand
            break
    if base is None:
        return None
    best = None
    for total in range(len(base) + 2, len(base) + 130):
        path = base + "/" + "s" * (total - len(base) - 1)
        if len(path) != total:
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(path)
            best = total
            os.unlink(path)
        except OSError:
            if best is not None:
                break
        finally:
            sock.close()
    return best


def socket_dir():
    """The directory the socket lives in.

    XDG_RUNTIME_DIR, then /run/user/<uid> if it is there and ours, then
    the temporary directory. Both of the first two are 0700 and
    per-user; the third is $TMPDIR, which is per-user on macOS
    (/var/folders/.../T) and /tmp on Linux.

    Keyed on the variable AND the directory on purpose: on this box
    XDG_RUNTIME_DIR is unset while /run/user/<uid> exists at 0700, so
    testing the variable alone falls through to the shared /tmp. The
    older call_flag_path() in browser.py keys on the variable alone and
    has exactly that gap.
    """
    told = os.environ.get(DIR_ENV)
    if told and os.path.isdir(told):
        return told
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg and os.path.isdir(xdg):
        return xdg
    run = "/run/user/%d" % os.getuid()
    try:
        info = os.stat(run)
        if stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid():
            return run
    except OSError:
        pass
    return os.environ.get("TMPDIR") or "/tmp"


def socket_name(headless=False):
    return BASE_NAME + (HEADLESS_SUFFIX if headless else "")


def socket_path(headless=False):
    """The full path. One function, both ends, so they cannot disagree."""
    told = os.environ.get(PATH_ENV)
    if told:
        return told
    return os.path.join(socket_dir(), socket_name(headless))


def candidate_paths():
    """Every path a browser might be listening on, best first.

    The client cannot know whether the browser it wants is headless, so
    it does not guess: it asks which of these exists. An explicit
    BROWSER_AGENT_SOCKET short-circuits the lot.
    """
    told = os.environ.get(PATH_ENV)
    if told:
        return [told]
    here = socket_dir()
    out = [os.path.join(here, socket_name(h)) for h in (False, True)]
    # the pre-2026-11-02 home, so a browser from before this change is
    # still reachable: accepted ONLY if it is a socket and ours, which
    # is the precondition and not a follow-up -- a legacy path in a
    # world-writable directory that we connect to without checking is
    # the hole this change is closing, wearing a compatibility label.
    legacy = os.path.join(os.environ.get("TMPDIR") or "/tmp",
                          socket_name(False))
    for extra in (legacy, legacy + HEADLESS_SUFFIX):
        if extra not in out:
            out.append(extra)
    return out


def is_ours(path):
    """Whether this path is a socket that belongs to us.

    The server sets 0700 on the socket IT makes, which says nothing
    about what the client dials. A squatter's socket in a shared
    directory is 0777 and theirs, and the asymmetry is what makes
    impersonation work -- so the client checks before it connects, and
    the server checks before it unlinks.
    """
    try:
        info = os.stat(path)
    except OSError:
        return False
    return stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid()
