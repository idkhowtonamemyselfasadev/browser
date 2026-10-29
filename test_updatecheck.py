#!/usr/bin/env python3
"""The update check has to ask the question it claims to answer.

`git rev-list --count HEAD..@{u}` counts commits reachable from the
upstream and not from HEAD. For two histories that share a root that is
"behind by N", which is what the toast says. For two that do not share
one it is "all of them" -- and `pull --ff-only` cannot fast-forward
across unrelated histories, so the toast appeared at every launch and
the button behind it could never make it go away.

That is the same shape as the other defects found on 2026-10-29:
theme_color("base") returning #000000, _ui_str returning its own key,
settings.html calling a function defined in another page. A forgiving
answer to a question nobody asked.

This drives REAL git repositories in a scratch directory -- three of
them, one per state -- because the bug was in what git actually
answers, and a mock of git would have been written from the same wrong
assumption as the code.

    related, behind      merge-base --is-ancestor -> 0   a pull works
    related, diverged    merge-base --is-ancestor -> 1   it does not
    unrelated histories  merge-base --is-ancestor -> 1   it does not

No Qt, no browser, no network, nothing outside its own temp directory.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


ENV = dict(os.environ,
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e",
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)


def git(cwd, *args):
    out = subprocess.run(["git"] + list(args), cwd=str(cwd), env=ENV,
                         capture_output=True, text=True)
    return out.returncode, (out.stdout + out.stderr).strip()


SCRATCH = Path(tempfile.mkdtemp(prefix="browser-updatecheck-"))


def build(name, kind):
    """A clone and its upstream, in one of the three states."""
    root = SCRATCH / name
    remote, clone = root / "remote", root / "clone"
    for d in (remote, clone):
        d.mkdir(parents=True)
    git(remote, "init", "-q", "-b", "main")
    (remote / "f.txt").write_text("one\n")
    git(remote, "add", "-A")
    git(remote, "commit", "-qm", "one")

    if kind == "unrelated":
        # the shape the rewrite produced: a clone with its own root
        git(clone, "init", "-q", "-b", "main")
        (clone / "f.txt").write_text("old\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "an unrelated root")
        git(clone, "remote", "add", "origin", str(remote))
        git(clone, "fetch", "-q", "origin")
        git(clone, "branch", "--set-upstream-to=origin/main")
    else:
        git(clone, "clone", "-q", str(remote), ".")
        if kind == "diverged":
            (clone / "mine.txt").write_text("local\n")
            git(clone, "add", "-A")
            git(clone, "commit", "-qm", "a local commit")
    if kind in ("behind", "diverged"):
        (remote / "f.txt").write_text("two\n")
        git(remote, "add", "-A")
        git(remote, "commit", "-qm", "two")
        git(clone, "fetch", "-q", "origin")
    return clone


print("(1) the three states really are the three states")
repos = {k: build(k, k) for k in ("behind", "diverged", "unrelated")}
for kind, clone in repos.items():
    code, _ = git(clone, "rev-parse", "--verify", "@{u}")
    check("%s: the clone follows an upstream" % kind, code == 0)
check("unrelated really has no common commit",
      git(repos["unrelated"], "merge-base", "HEAD", "@{u}")[0] != 0)
check("diverged really does have one",
      git(repos["diverged"], "merge-base", "HEAD", "@{u}")[0] == 0)

print()
print("(2) the old question says 'update available' in all three")
# this is the bug, kept as a fixture: the count the check used to trust
# is above zero even when no pull can ever succeed.
for kind, clone in repos.items():
    code, out = git(clone, "rev-list", "--count", "HEAD..@{u}")
    check("%s: rev-list counts %s" % (kind, out or "?"),
          code == 0 and out.isdigit() and int(out) > 0, out)

print()
print("(3) the new question tells the three apart")
answers = {}
for kind, clone in repos.items():
    answers[kind] = git(clone, "merge-base", "--is-ancestor",
                        "HEAD", "@{u}")[0]
check("behind    -> a pull will work", answers["behind"] == 0,
      answers["behind"])
check("diverged  -> it will not", answers["diverged"] == 1,
      answers["diverged"])
check("unrelated -> it will not", answers["unrelated"] == 1,
      answers["unrelated"])

print()
print("(4) ...and git agrees, when actually asked to do it")
for kind, clone in repos.items():
    code, out = git(clone, "pull", "--ff-only")
    worked = code == 0
    check("%s: pull --ff-only %s" % (kind, "succeeds" if worked
                                     else "fails"),
          worked == (answers[kind] == 0),
          out.strip().splitlines()[-1] if out else "")

print()
print("(5) the recovery path recognises what git says when it fails")
# _update_done matches on the last line of git's stderr. If git's
# wording ever changes, the reset path silently stops being reachable
# and the copy is stranded for good -- so the wording is asserted.
for kind in ("diverged", "unrelated"):
    clone = build(kind + "2", kind)
    _code, out = git(clone, "pull", "--ff-only")
    last = (out.strip().splitlines() or ["?"])[-1]
    check("%s: the last line still names a fast-forward" % kind,
          "fast-forward" in last.lower() or "diverged" in last.lower(),
          last)

print()
print("(6) the source asks the new question and still keeps --ff-only")
SRC = (HERE / "browser.py").read_text(encoding="utf-8")
check("the check runs merge-base --is-ancestor",
      '"merge-base", "--is-ancestor", "HEAD", "@{u}"' in SRC)
check("the count is still there, for the case where it means something",
      '"rev-list", "--count", "HEAD..@{u}"' in SRC)
# --ff-only is the only reason this was merely broken and not dangerous:
# a plain `git pull` would have merged the pre-rewrite history back into
# the user's clone, bringing the strings the rewrite removed with it.
check("the pull is still --ff-only, never a plain pull",
      '"pull", "--ff-only"' in SRC and '"pull"]' not in SRC)
check("a stranded copy is offered a replace, not a pull",
      "_stranded" in SRC and "Replace it" in SRC)

shutil.rmtree(SCRATCH, ignore_errors=True)
print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
