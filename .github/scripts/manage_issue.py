#!/usr/bin/env python3
"""Keep exactly one security issue, and only when there is a reason for it.

Fed the findings from security_report.py, this opens an issue when there
is something to act on, edits that same issue when the situation changes,
and closes it when everything is clear again. It never opens a second
one: a check that files a fresh issue every five weeks is a check that
gets muted.

    python3 .github/scripts/manage_issue.py --findings f.json --report r.md

Talks to GitHub through the `gh` CLI, which is already on the runner and
already authenticated by the workflow's GITHUB_TOKEN. No other secret is
involved. --dry-run prints what it would do and changes nothing.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TITLE = "Browser security check"
LABEL = "security-check"
MARKER = "<!-- browser-security-check-state: %s -->"
MARKER_RE = re.compile(r"<!-- browser-security-check-state: (.*?) -->")

FOOTER = """
---

*Opened by the scheduled security check
(`.github/workflows/security-check.yml`). It edits this one issue rather
than opening new ones, and closes it when there is nothing left to do.
Nothing here is urgent unless it says so.*
"""


class Gh:
    def __init__(self, dry_run=False, binary="gh"):
        self.dry_run = dry_run
        self.binary = binary

    def read(self, *args):
        out = subprocess.run([self.binary, *args], capture_output=True,
                             text=True, check=True)
        return out.stdout

    def write(self, *args, stdin=None):
        if self.dry_run:
            print("would run: %s %s" % (self.binary, " ".join(
                a if len(a) < 60 else a[:57] + "..." for a in args)))
            return ""
        out = subprocess.run([self.binary, *args], input=stdin,
                             capture_output=True, text=True, check=True)
        return out.stdout


def existing_issue(gh):
    """The one issue this check owns, open or closed, or None."""
    raw = gh.read("issue", "list", "--label", LABEL, "--state", "all",
                  "--limit", "50", "--json", "number,state,title,body")
    issues = json.loads(raw or "[]")
    mine = [i for i in issues if i.get("title") == TITLE]
    if not mine:
        return None
    return sorted(mine, key=lambda i: i["number"])[-1]


def stored_ids(issue):
    if not issue:
        return None
    found = MARKER_RE.search(issue.get("body") or "")
    if not found:
        return None
    try:
        return json.loads(found.group(1)).get("ids")
    except ValueError:
        return None


def body_for(report_text, ids):
    return (report_text.rstrip() + "\n" + FOOTER
            + "\n" + MARKER % json.dumps({"ids": ids}) + "\n")


def decide(findings, issue):
    """(action, why) — the whole policy in one place.

    act    something is installable/fixable  -> the issue must be open
    watch  worth knowing, nothing to install -> say it once, do not nag
    none   all clear                         -> close anything open
    """
    ids = sorted(f["id"] for f in findings)
    act = [f for f in findings if f["level"] == "act"]
    open_now = bool(issue) and issue.get("state", "").upper() == "OPEN"
    changed = stored_ids(issue) != ids

    if not findings:
        if open_now:
            return "close", "everything is clear again"
        return "silent", "nothing to report"
    if act:
        if not issue:
            return "create", "there is something to act on"
        if not open_now:
            return "reopen", "there is something to act on again"
        return ("edit-and-comment" if changed else "edit",
                "the issue is already open")
    # watch only
    if not issue:
        return "create", "worth knowing about, nothing to install"
    if open_now:
        return ("edit-and-comment" if changed else "edit",
                "the issue is already open")
    if changed:
        return "reopen", "something new is worth knowing about"
    return "silent", "already reported and nothing changed"


def summarise(findings):
    act = [f for f in findings if f["level"] == "act"]
    watch = [f for f in findings if f["level"] == "watch"]
    if act:
        return "Something to do: " + "; ".join(f["title"] for f in act)
    return "Worth knowing: " + "; ".join(f["title"] for f in watch)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--findings", required=True,
                    help="the JSON from security_report.py --json")
    ap.add_argument("--report", required=True,
                    help="the markdown from security_report.py --out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gh", default="gh", help="the gh binary to use")
    args = ap.parse_args()

    findings = json.loads(Path(args.findings).read_text())["findings"]
    report = Path(args.report).read_text()
    gh = Gh(args.dry_run, args.gh)

    issue = existing_issue(gh)
    action, why = decide(findings, issue)
    ids = sorted(f["id"] for f in findings)
    body = body_for(report, ids)
    number = str(issue["number"]) if issue else None
    print("issue: %s | action: %s (%s)" % (number or "none", action, why))

    if action == "silent":
        return 0
    if action == "create":
        # the label may not exist yet on a fresh repository
        try:
            gh.write("label", "create", LABEL, "--color", "b60205",
                     "--description", "Scheduled security check", "--force")
        except subprocess.CalledProcessError as exc:
            print("could not create the label: %s" % exc.stderr)
        gh.write("issue", "create", "--title", TITLE, "--label", LABEL,
                 "--body-file", "-", stdin=body)
        return 0
    if action == "close":
        gh.write("issue", "comment", number, "--body",
                 "All clear — the last check found nothing to act on. "
                 "Closing; the scheduled check will reopen this if that "
                 "changes.")
        gh.write("issue", "close", number)
        return 0
    if action == "reopen":
        gh.write("issue", "reopen", number)
    gh.write("issue", "edit", number, "--body-file", "-", stdin=body)
    if action in ("reopen", "edit-and-comment"):
        gh.write("issue", "comment", number, "--body", summarise(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
