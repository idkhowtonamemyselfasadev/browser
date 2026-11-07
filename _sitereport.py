#!/usr/bin/env python3
"""The site x theme matrix as Markdown, from what _sitematrix.py wrote.

    _sitereport.py DIR [DIR...]   (each holding worker folders with rows.jsonl)

A cell is the share of the text on the page that measures under 3:1
against what is really behind it -- unreadable, not merely weak --
with the form fields and the flat (invisible) text boxes folded in.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def rows_in(dirs):
    for d in dirs:
        for f in sorted(Path(d).glob("**/rows.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    r["worker"] = ("fresh" if "fresh" in str(f) else "live")
                    yield r


def cell(r):
    if r.get("error"):
        return "busy" if "timeout" in r["error"] or "busy" in r["error"] else "err"
    j = max(1, r.get("judged", 0))
    bad = 100.0 * r.get("bad", 0) / j
    marks = ""
    if r.get("badInputs"):
        marks += "f"
    if r.get("flatLooked") and r["flat"] / r["flatLooked"] > 0.15:
        marks += "i"
    if not r.get("themed"):
        return "-" if bad < 2 else "%.0f%%-" % bad
    if bad < 0.5 and not marks:
        return "ok"
    return "%.0f%%%s" % (bad, marks) if bad >= 0.5 else "ok" + marks


def short(site):
    s = site.replace("https://", "").replace("http://", "").replace("www.", "")
    return s[:34]


def table(rows, themes, title):
    sites = []
    grid = defaultdict(dict)
    for r in rows:
        if r["site"] not in sites:
            sites.append(r["site"])
        grid[r["site"]][r["theme"]] = cell(r)
    out = ["### " + title, "",
           "| site | " + " | ".join(themes) + " |",
           "|---|" + "---|" * len(themes)]
    for s in sites:
        out.append("| %s | %s |" % (short(s), " | ".join(
            grid[s].get(t, "·") for t in themes)))
    return out


def summary(rows, title):
    per_site = defaultdict(lambda: [0, 0, []])
    per_theme = defaultdict(lambda: [0, 0])
    for r in rows:
        c = cell(r)
        bad = c not in ("ok", "-") and not c.startswith("ok")
        per_site[r["site"]][1] += 1
        per_theme[r["theme"]][1] += 1
        if bad:
            per_site[r["site"]][0] += 1
            per_theme[r["theme"]][0] += 1
            per_site[r["site"]][2].append("%s %s" % (r["theme"], c))
    out = ["### " + title, "", "| site | themes with a problem | worst |",
           "|---|---|---|"]
    for s, (b, n, which) in sorted(per_site.items(),
                                  key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
        out.append("| %s | %d / %d | %s |" % (short(s), b, n,
                                              ", ".join(which[:4])))
    worst = sorted(per_theme.items(), key=lambda kv: -kv[1][0])[:12]
    out += ["", "Themes with the most problem sites: "
            + ", ".join("%s (%d/%d)" % (t, b, n) for t, (b, n) in worst)]
    return out


def main():
    rows = list(rows_in(sys.argv[1:]))
    fresh = [r for r in rows if r["worker"].startswith("fresh")]
    live = [r for r in rows if r["worker"].startswith("live")]
    out = []
    if fresh:
        themes = []
        for r in fresh:
            if r["theme"] not in themes:
                themes.append(r["theme"])
        out += table(fresh, themes, "Fresh load, anchor themes "
                     "(cell: share of text under 3:1; f = a form field, "
                     "i = text invisible in the screenshot, - = not themed)")
        out.append("")
    if live:
        out += summary(live, "Live re-theme, all %d themes: problems per site"
                       % len({r["theme"] for r in live}))
    print("\n".join(out))


if __name__ == "__main__":
    main()
