#!/usr/bin/env python3
"""Settings as a page: nothing listed twice, nothing silently dead,
and a sheet you can see the window through.

He opened Settings and found two sections called "The address bar",
one after the other. Underneath that were worse things of the same
kind: two different switches sharing one id, so one of them was never
found and never did anything; a never-sleep list and a screen-awake
switch sharing one config key, so the switch wiped the list; and a
"Browsing" section that had grown into a dumping ground of 23 panels
while "Downloads" held two rows.

So this measures the page itself -- the file, the rail it builds, and
the behaviour behind the two switches that collided -- rather than how
it looks."""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


def settings_view(win):
    pane = getattr(win, "_settings_pane", None)
    if pane is None:
        pane = (getattr(win, "_panes", None) or {}).get("settings")
    return None if pane is None else pane.view


PAGE = Path(B.APP_DIR / "settings.html").read_text(encoding="utf-8")
START = Path(B.APP_DIR / "start.html").read_text(encoding="utf-8")

app = H.app()
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1100, 760)
win.show()
H.spin(400)


print("\n(1) nothing in the file is there twice")
ids = re.findall(r'\bid="([^"]+)"', PAGE)
dup = sorted(k for k, n in Counter(ids).items() if n > 1)
check("every element with an id has it to itself", not dup,
      ", ".join(dup[:6]) + ((" +%d more" % (len(dup) - 6)) if len(dup) > 6
                            else ""))
check("...and there are plenty of them to get wrong", len(ids) > 900,
      len(ids))

sections = re.findall(r'<section ([^>]*)>\s*<h2[^>]*>(.*?)</h2>', PAGE, re.S)
names = [re.sub(r"<[^>]+>", "", title).strip() for _, title in sections]
twice = sorted(k for k, n in Counter(names).items() if n > 1)
check("no two sections carry the same name", not twice, twice)
check("...across the whole rail", len(names) >= 20, len(names))

blocks = re.findall(r'<div class="panel">.*?(?=<div class="panel">|</section>)',
                    PAGE, re.S)
heads = [re.search(r'<h2 class="sub"[^>]*>(.*?)</h2>', b, re.S) for b in blocks]
titles = [re.sub(r"<[^>]+>", "", m.group(1)).strip() for m in heads if m]
pairs = Counter(titles)
# a card title may legitimately repeat in two different sections ("The
# address bar" names both the section and its first card); what must not
# happen is the same card twice in the same section
same = []
for m in re.finditer(r'<section [^>]*>.*?</section>', PAGE, re.S):
    body = m.group(0)
    here = [re.sub(r"<[^>]+>", "", t).strip() for t in
            re.findall(r'<h2 class="sub"[^>]*>(.*?)</h2>', body, re.S)]
    same += [k for k, n in Counter(here).items() if n > 1]
check("and no section repeats a card of its own", not same, same)


print("\n(2) the switches that used to share an id")
check("the perf switch and the video switch are two elements",
      PAGE.count('id="perfpausehidden"') == 1
      and PAGE.count('id="pausehidden"') == 1,
      PAGE.count('id="pausehidden"'))
check("...and each writes where it belongs: one into perf, one on its own",
      '["perfpausehidden", "pauseHidden"]' in PAGE
      and 'bindSwitch("pausehidden", "pauseHidden")' in PAGE)
check("the never-sleep list and the screen-awake switch are two elements",
      PAGE.count('id="keepawake"') == 1
      and PAGE.count('id="screenawake"') == 1)
check("...and the switch writes its own key",
      'bindSwitch("screenawake", "screenAwake")' in PAGE
      and 'bindSwitch("keepawake"' not in PAGE)


print("\n(3) and what that collision did to the config")
win.config["keepAwake"] = ["music.amazon.de"]
win.config["screenAwake"] = True
check("the screen-awake switch leaves the never-sleep list alone",
      win.keep_awake_sites() == ["music.amazon.de"],
      win.keep_awake_sites())
check("...and the list leaves the switch alone",
      win.config.get("screenAwake") is True)
old = {"keepAwake": True}
B._migrate_awake_config(old)
check("a config from before the split hands the boolean over",
      old.get("screenAwake") is True and old.get("keepAwake") == [], old)
keep = {"keepAwake": ["discord.com"]}
B._migrate_awake_config(keep)
check("...and a list is left exactly as it was",
      keep["keepAwake"] == ["discord.com"] and "screenAwake" not in keep,
      keep)


print("\n(4) every section says what it is, in both languages")
bad = []
for attrs, title in sections:
    desc = re.search(r'data-desc="([^"]+)"', attrs)
    group = re.search(r'data-group="([^"]+)"', attrs)
    name = re.sub(r"<[^>]+>", "", title).strip()
    if not desc or not group:
        bad.append(name + ": no group or no description")
        continue
    for lang in ("en", "de"):
        if desc.group(1) not in B.UI_STRINGS[lang]:
            bad.append("%s: %s missing in %s" % (name, desc.group(1), lang))
    if group.group(1) not in ("gen", "priv", "adv", "sys"):
        bad.append(name + ": unknown group " + group.group(1))
check("each one has a group and a line that is written in en and de",
      not bad, bad[:4])

label_map = re.findall(r'\bt_(\w+):"(\w+)"', PAGE)
known = {"t_" + a for a, _ in label_map}
heads = set(re.findall(r'<h2[^>]*id="(t_[^"]+)"', PAGE))
# the map is the only thing that translates a heading: an id missing
# from it stays in English however the browser is set
unmapped = sorted(h for h in heads if h not in known)
check("and every heading is in the map that translates it",
      not unmapped, unmapped[:5])
missing = sorted({key for _, key in label_map
                  if key not in B.UI_STRINGS["en"]})
check("...and every string it maps to is defined", not missing,
      missing[:5])


print("\n(5) the sections hold what their names promise")
def section_of(panel_title):
    for m in re.finditer(r'<section [^>]*>\s*<h2[^>]*>(.*?)</h2>(.*?)</section>',
                         PAGE, re.S):
        if re.search(r'<h2 class="sub"[^>]*>%s</h2>' % re.escape(panel_title),
                     m.group(2)):
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


check("the tab strip's own settings sit under Tabs",
      section_of("How wide tabs are") == "Tabs",
      section_of("How wide tabs are"))
check("the click on a tab is offered once, with the other tab settings",
      PAGE.count('id="tabdouble"') == 1
      and section_of("Double-click on a tab") == "Tabs",
      section_of("Double-click on a tab"))
check("video and sound have a section instead of a corner of Browsing",
      section_of("Video and sound") == "Video and sound",
      section_of("Video and sound"))
check("the keyboard shortcuts sit with the keys",
      section_of("Keyboard shortcuts") == "Keys and the mouse",
      section_of("Keyboard shortcuts"))
check("downloads are one section, not two",
      names.count("Downloads") == 1 and "More about downloads" not in names,
      [n for n in names if "ownload" in n])
browsing = re.search(r'<section [^>]*data-desc="descBrowsing".*?</section>',
                     PAGE, re.S).group(0)
check("and Browsing is no longer where everything was tipped",
      len(re.findall(r'<div class="panel">', browsing)) <= 6,
      len(re.findall(r'<div class="panel">', browsing)))


print("\n(6) you can see the window through it")
css = PAGE.split("</style>")[0]
check("the rail, the search strip and the cards are not solid slabs",
      css.count("backdrop-filter") >= 3
      and "rgba(13, 13, 18, .58)" in css, css.count("backdrop-filter"))
check("the glass look takes the page itself down to see-through",
      ':root[data-look="glass"] body' in css)
check("...and the flat look keeps its square, quiet shapes",
      ':root[data-look="flat"] .panel' in css)
# the painter swaps a literal rgb triple for the theme's and keeps the
# alpha; a colour that is not one of its literals would stay Mocha in
# all 113 other palettes
known_rgb = {tuple(int(lit[i:i + 2], 16) for i in (1, 3, 5))
             for lit in B.THEME_SOURCE.values()}
off = []
for m in re.finditer(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', css):
    if tuple(int(g) for g in m.groups()) not in known_rgb:
        off.append(m.group(0))
check("and every see-through colour is one the painter can repaint",
      not off, sorted(set(off))[:4])


print("\n(7) one of our own pages lets the window through")
win.apply_look("glass", save=False)
win.open_settings()
H.spin(2500)
view = settings_view(win)
check("Settings opens", view is not None)
if view is not None:
    page = view.page()
    check("under glass the engine paints no base behind it",
          page.backgroundColor().alpha() == 0,
          page.backgroundColor().name())
    check("...and the page is told which look it is in",
          H.js(view, "document.documentElement.getAttribute('data-look')",
               B.MAIN_WORLD_ID) == "glass")
    win.apply_look("classic", save=False)
    H.spin(600)
    check("and back in a solid look it is solid again",
          page.backgroundColor().alpha() == 255,
          page.backgroundColor().alpha())
    check("...which the page hears about too",
          H.js(view, "document.documentElement.getAttribute('data-look')",
               B.MAIN_WORLD_ID) == "classic")


print("\n(8) the rail it actually builds")
if view is not None:
    rail = H.js(view, """(function () {
      var out = [];
      var btns = document.querySelectorAll('#sidebar button');
      for (var i = 0; i < btns.length; i++)
        out.push(btns[i].textContent.trim());
      return JSON.stringify(out);
    })()""", B.MAIN_WORLD_ID)
    rows = json.loads(rail or "[]")
    check("every section has a button", len(rows) >= 20, len(rows))
    again = sorted(k for k, n in Counter(rows).items() if n > 1)
    check("and no name is on it twice", not again, again)
    check("...including the one he photographed",
          rows.count("The address bar") == 1, rows)
    check("and every name on it is in the language he chose",
          all(not re.search(r"^t_|^[a-z]+[A-Z]", row) for row in rows), rows)


print("\n(9) carry on is gone, not hidden")
check("the browser no longer works out where he left off",
      not hasattr(win, "continue_where"))
extras = json.loads(win.bridge.startExtras())
check("the start page is not offered the row any more",
      "continue" not in extras, sorted(extras))
check("...and does not draw one", "startCarryOn" not in START)
check("no string is left behind in either language",
      all("startCarryOn" not in B.UI_STRINGS[lang] for lang in ("en", "de")))
check("and the switch that offered it is out of Settings",
      "startcontinue" not in PAGE and "startContinue" not in PAGE)
check("...while the row beside it still works",
      "recent" in extras, sorted(extras))


print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
