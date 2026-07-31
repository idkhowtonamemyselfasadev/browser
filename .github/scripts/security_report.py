#!/usr/bin/env python3
"""How exposed is this browser right now, in plain language.

The browser is a Python shell around Qt WebEngine, and Qt WebEngine is
Chromium. Almost every vulnerability that will ever matter here is a
Chromium one, fixed upstream and delivered as a new PyQt6-WebEngine. So
this asks four questions:

  * which Chromium is the engine, and how old is that now?
  * are Chrome vulnerabilities known to be exploited in the wild newer
    than that engine? (CISA's KEV list — the ones actually being used,
    not the whole CVE firehose)
  * is there a newer PyQt6 / PyQt6-WebEngine to install?
  * does anyone have a published advisory against the versions pinned
    in .github/requirements.txt? (OSV)

Everything it reads is public: no token, no account, no secrets.

    python3 .github/scripts/security_report.py --out report.md

Findings come out at two levels. "act" means there is something to
install or fix. "watch" means it is worth knowing but nothing can be
installed to fix it. A source that cannot be reached is reported as
unknown and never counts as a finding — a check that cries wolf when
the network hiccups is a check that gets ignored.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO / ".github" / "requirements.txt"
TIMEOUT = 30
UA = "browser-security-check (+https://github.com/)"

CHROME_VERSIONS = ("https://versionhistory.googleapis.com/v1/chrome/platforms/"
                   "linux/channels/stable/versions")
KEV_URL = ("https://www.cisa.gov/sites/default/files/feeds/"
           "known_exploited_vulnerabilities.json")
OSV_URL = "https://api.osv.dev/v1/query"
PYPI = "https://pypi.org/pypi/%s/json"

# how far behind Chrome stable the engine may drift before it is worth
# saying so out loud. Qt always trails Chrome by a release or two and
# backports security fixes into its snapshot, so a small gap is normal
# and mentioning it every five weeks would just be noise.
GAP_WORTH_MENTIONING = 3

problems = []          # sources that could not be read


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA,
        **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def try_fetch(what, url, data=None):
    try:
        return fetch(url, data)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        problems.append("%s could not be read (%s)" % (what, exc))
        return None


def major(version):
    try:
        return int(str(version).split(".")[0])
    except (ValueError, AttributeError):
        return None


# ------------------------------------------------------------- the engine
def installed_engine():
    """What the engine here actually is."""
    out = {}
    try:
        from PyQt6.QtWebEngineCore import (qWebEngineChromiumVersion,
                                           qWebEngineVersion)
        out["chromium"] = qWebEngineChromiumVersion()
        out["qtwebengine"] = qWebEngineVersion()
    except Exception as exc:                            # noqa: BLE001
        problems.append("the installed engine could not be asked its "
                        "version (%s)" % exc)
    try:
        from importlib.metadata import version as dist_version
        for dist in ("PyQt6", "PyQt6-WebEngine"):
            try:
                out[dist] = dist_version(dist)
            except Exception:                           # noqa: BLE001
                pass
    except Exception:                                   # noqa: BLE001
        pass
    return out


def pinned_versions():
    """What .github/requirements.txt asks CI to install."""
    pins = {}
    if not REQUIREMENTS.exists():
        problems.append("%s is missing" % REQUIREMENTS.name)
        return pins
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([A-Za-z0-9._-]+)$", line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def chrome_stable():
    data = try_fetch("the Chrome stable version",
                     CHROME_VERSIONS + "?pageSize=1")
    if not data or not data.get("versions"):
        return None
    return data["versions"][0]["version"]


def branch_ended(chromium_major):
    """When the next Chromium major went stable — i.e. the day this
    engine's branch stopped being the current one."""
    if chromium_major is None:
        return None
    url = (CHROME_VERSIONS + "/all/releases?order_by=starttime%%20asc"
           "&pageSize=1&filter=version%%3E%%3D%d.0.0.0,version%%3C%d.0.0.0"
           % (chromium_major + 1, chromium_major + 2))
    data = try_fetch("the Chrome release history", url)
    if not data or not data.get("releases"):
        return None
    start = data["releases"][0].get("serving", {}).get("startTime", "")
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return None


def kev_since(when):
    """Chrome/Chromium entries on CISA's known-exploited list added
    after `when` — the vulnerabilities that are actually being used."""
    data = try_fetch("CISA's known-exploited-vulnerabilities list", KEV_URL)
    if not data:
        return None
    hits = []
    for item in data.get("vulnerabilities", []):
        name = (item.get("vendorProject", "") + " "
                + item.get("product", "")).lower()
        if "chrom" not in name:
            continue
        try:
            added = datetime.fromisoformat(
                item["dateAdded"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if when is None or added > when:
            hits.append({"cve": item.get("cveID"), "added": item["dateAdded"],
                         "what": item.get("vulnerabilityName", ""),
                         "product": item.get("product", "")})
    hits.sort(key=lambda h: h["added"])
    return hits


def newest_on_pypi(package):
    data = try_fetch("the newest %s release on PyPI" % package, PYPI % package)
    if not data:
        return None
    return data.get("info", {}).get("version")


def osv_advisories(package, version):
    body = json.dumps({"package": {"name": package, "ecosystem": "PyPI"},
                       "version": version}).encode()
    data = try_fetch("OSV advisories for %s" % package, OSV_URL, body)
    if data is None:
        return None
    return [{"id": v.get("id"), "summary": (v.get("summary") or "").strip()}
            for v in data.get("vulns", [])]


# ------------------------------------------------------------- the report
def collect(invariants):
    report = {"findings": [], "unknown": problems, "context": {}}
    ctx = report["context"]

    engine = installed_engine()
    pins = pinned_versions()
    ctx["engine"] = engine
    ctx["pinned"] = pins

    chromium = engine.get("chromium")
    stable = chrome_stable()
    ctx["chrome_stable"] = stable
    gap = None
    if chromium and stable:
        gap = (major(stable) or 0) - (major(chromium) or 0)
        ctx["majors_behind"] = gap

    ended = branch_ended(major(chromium)) if chromium else None
    ctx["branch_ended"] = ended.date().isoformat() if ended else None
    kev = kev_since(ended) if chromium else None
    ctx["kev"] = kev

    # ---- act: the invariant checks
    if invariants is not None:
        ctx["invariants"] = {"passed": invariants.get("passed"),
                             "failed": invariants.get("failed"),
                             "engine_available": invariants.get("engine")}
        broken = [r["check"] for r in invariants.get("results", [])
                  if not r.get("ok")]
        if broken:
            report["findings"].append({
                "id": "invariants",
                "level": "act",
                "title": "The browser's own security checks are failing",
                "detail": "These checks each guard something that was broken "
                          "once already:\n\n"
                          + "\n".join("- %s" % b for b in broken)
                          + "\n\nRun them yourself with "
                            "`python3 .github/scripts/invariant_checks.py`. "
                            "Whatever changed most recently is the place to "
                            "look."})

    # ---- act: a newer engine to install
    for package, pinned in sorted(pins.items()):
        newest = newest_on_pypi(package)
        if newest:
            ctx.setdefault("newest", {})[package] = newest
        if newest and newest != pinned:
            report["findings"].append({
                "id": "update-%s" % package.lower(),
                "level": "act",
                "title": "%s %s is out (this repo pins %s)"
                         % (package, newest, pinned),
                "detail": "Update the pin in `.github/requirements.txt` — "
                          "Dependabot usually opens that pull request on its "
                          "own — and update the copy on your machine:\n\n"
                          "```sh\nsudo dnf upgrade python3-pyqt6-webengine\n"
                          "```\n\nA new PyQt6-WebEngine is normally a newer "
                          "Chromium underneath, which is the update that "
                          "actually matters."})

    # ---- act: published advisories against what is pinned
    for package, pinned in sorted(pins.items()):
        vulns = osv_advisories(package, pinned)
        if vulns:
            report["findings"].append({
                "id": "osv-%s" % package.lower(),
                "level": "act",
                "title": "%s %s has a published advisory" % (package, pinned),
                "detail": "\n".join("- **%s** %s" % (v["id"], v["summary"])
                                    for v in vulns)
                          + "\n\nUpdate the pin to a version the advisory "
                            "does not cover."})

    # ---- watch: an engine that has fallen behind
    if kev:
        report["findings"].append({
            "id": "kev-" + "-".join(sorted(h["cve"] or "?" for h in kev)),
            "level": "watch",
            "title": "%d Chrome holes known to be exploited are newer than "
                     "this engine" % len(kev),
            "detail": engine_paragraph(chromium, stable, gap, ended)
                      + "\n\nCISA lists these as being used against people "
                        "in the real world, and they were listed after that "
                        "date:\n\n"
                      + "\n".join(
                          "- **%s** (%s) %s" % (h["cve"], h["added"],
                                                h["what"] or h["product"])
                          for h in kev)
                      + "\n\nThere is nothing to install if the versions "
                        "above are already the newest ones — Qt decides when "
                        "its Chromium moves, and it backports fixes into the "
                        "version it ships, so some of these are very likely "
                        "already fixed in the engine you have. Treat it as a "
                        "reason to take the next engine update promptly, not "
                        "as an emergency."})
    elif gap is not None and gap >= GAP_WORTH_MENTIONING:
        report["findings"].append({
            "id": "gap-%d" % gap,
            "level": "watch",
            "title": "The engine is %d Chrome versions behind" % gap,
            "detail": engine_paragraph(chromium, stable, gap, ended)})
    return report


def engine_paragraph(chromium, stable, gap, ended):
    bits = ["This browser renders pages with Chromium **%s** (inside Qt "
            "WebEngine)." % (chromium or "unknown")]
    if stable:
        bits.append("Google's current Chrome is **%s**%s."
                    % (stable, ", %d major versions ahead" % gap
                       if gap else ""))
    if ended:
        bits.append("Chromium %s stopped being the current branch on %s."
                    % (major(chromium), ended.date().isoformat()))
    return " ".join(bits)


def markdown(report):
    ctx = report["context"]
    act = [f for f in report["findings"] if f["level"] == "act"]
    watch = [f for f in report["findings"] if f["level"] == "watch"]
    out = ["# Browser security check",
           "",
           "_%s_" % datetime.now(timezone.utc).strftime("%d %B %Y"),
           ""]

    if act:
        out += ["## Something to do", ""]
    elif watch:
        out += ["## Nothing to install, but worth knowing", ""]
    else:
        out += ["## Nothing to do", "",
                "Everything checked out. No action needed.", ""]

    for finding in act + watch:
        out += ["### %s" % finding["title"], "", finding["detail"], ""]

    out += ["## What the engine is", "",
            engine_paragraph(ctx.get("engine", {}).get("chromium"),
                             ctx.get("chrome_stable"),
                             ctx.get("majors_behind"),
                             None), ""]
    pins = ctx.get("pinned", {})
    newest = ctx.get("newest", {})
    if pins:
        out += ["| Package | Pinned here | Newest on PyPI |",
                "|---|---|---|"]
        out += ["| %s | %s | %s |" % (p, v, newest.get(p, "?"))
                for p, v in sorted(pins.items())]
        out += [""]
    engine = ctx.get("engine", {})
    if engine.get("qtwebengine"):
        out += ["The engine CI actually loaded was Qt WebEngine %s."
                % engine["qtwebengine"], ""]
    out += ["To see what *your* machine is running:", "",
            "```sh",
            "python3 -c \"from PyQt6.QtWebEngineCore import "
            "qWebEngineChromiumVersion as v; print(v())\"",
            "```", ""]

    inv = ctx.get("invariants")
    if inv:
        out += ["## The browser's own checks", "",
                "%s of %s passed.%s"
                % (inv.get("passed"),
                   (inv.get("passed") or 0) + (inv.get("failed") or 0),
                   "" if inv.get("engine_available") else
                   " (The checks needing a live page were skipped — the "
                   "engine would not start on the runner.)"), ""]

    if report["unknown"]:
        out += ["## Could not be checked this time", ""]
        out += ["- %s" % p for p in report["unknown"]]
        out += ["", "Nothing is concluded from these; the next run tries "
                    "again.", ""]
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--invariants", metavar="FILE",
                    help="the JSON written by invariant_checks.py --json")
    ap.add_argument("--out", metavar="FILE", help="write the report here")
    ap.add_argument("--json", metavar="FILE", help="write the findings here")
    args = ap.parse_args()

    invariants = None
    if args.invariants and Path(args.invariants).exists():
        invariants = json.loads(Path(args.invariants).read_text())

    report = collect(invariants)
    text = markdown(report)
    if args.out:
        Path(args.out).write_text(text)
    else:
        sys.stdout.write(text)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
