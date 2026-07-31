#!/usr/bin/env python3
"""The theme engine, checked offscreen against scratch data.

What matters here: the default theme is the sheet that was always
there, every palette reaches every part of the browser, a theme lands
without a restart, and the one thing that does need a restart is the
one thing we say needs a restart."""
import itertools
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SCRATCH = Path(tempfile.mkdtemp(prefix="themetest-"))
os.environ["XDG_DATA_HOME"] = str(SCRATCH / "share")
os.environ["XDG_CONFIG_HOME"] = str(SCRATCH / "config")
os.environ["XDG_CACHE_HOME"] = str(SCRATCH / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop  # noqa: E402

B.CONFIG_FILE = SCRATCH / "config.json"
B.HISTORY_FILE = SCRATCH / "history.json"
B.DOWNLOADS_FILE = SCRATCH / "downloads.json"
B.HOSTS_FILE = SCRATCH / "hosts.json"
B.BOOKMARKS_FILE = SCRATCH / "bookmarks.json"
SCRATCH.mkdir(parents=True, exist_ok=True)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))

FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    print(("  ok   " if cond else "  FAIL ") + name
          + ("  <%s>" % detail if detail else ""))
    if not cond:
        FAILS += 1


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(page, code):
    box = {}
    loop = QEventLoop()
    page.runJavaScript(code, B.MAIN_WORLD_ID,
                       lambda r: (box.update({"v": r}), loop.quit()))
    QTimer.singleShot(8000, loop.quit)
    loop.exec()
    return box.get("v")


print("\n(1) the catalogue")
keys = [t["key"] for t in B.THEMES]
check("every theme has its own key", len(set(keys)) == len(keys), len(keys))
check("there are three shelves and every theme is on one",
      {t["group"] for t in B.THEMES} == set(B.THEME_GROUPS),
      ", ".join(B.THEME_GROUPS))
check("every theme names itself",
      all(t["name"] and t["note"] is not None for t in B.THEMES))
check("light themes are not marked dark",
      all(not t["dark"] for t in B.THEMES if t["group"] == "light"))
counts = {g: sum(1 for t in B.THEMES if t["group"] == g)
          for g in B.THEME_GROUPS}
print("       %s = %d" % (counts, len(B.THEMES)))

# no palette is another palette wearing a different name
worst = None
for a, b in itertools.combinations(B.THEMES, 2):
    pa, pb = B.theme_palette(a["key"]), B.theme_palette(b["key"])
    far = max(sum(abs(x - y) for x, y in zip(B._hex_rgb(pa[k]),
                                             B._hex_rgb(pb[k])))
              for k in ("bg", "surface", "text", "accent", "green", "red"))
    if worst is None or far < worst[0]:
        worst = (far, a["name"], b["name"])
check("no two palettes are the same palette twice", worst[0] >= 12,
      "closest: %s / %s at %d" % (worst[1], worst[2], worst[0]))

print("\n(2) the default theme is the sheet that was always there")
check("byte for byte", B.theme_style("mocha") == B.STYLE)
check("and it says so in its name",
      B.THEME_INDEX[B.DEFAULT_THEME]["name"] == "Catppuccin Mocha")
check("an unknown name falls back to it instead of breaking",
      B.theme_style("no-such-theme") == B.STYLE)

print("\n(3) recolouring reaches everything and invents nothing")
import re  # noqa: E402
for key in ("gruvbox", "latte", "steampunk", "steam", "terminal"):
    sheet = B.theme_style(key)
    pal = B.theme_palette(key)
    stray = [h for h in set(re.findall(r"#[0-9a-f]{6}\b", sheet))
             if h in B.THEME_SOURCE.values()]
    check("%s: no Mocha literal survives in the Qt sheet" % key, not stray,
          ", ".join(sorted(stray)))
    check("%s: the window takes the palette's background" % key,
          pal["bg"].upper() in sheet or pal["bg"] in sheet)
# a black scrim behind a dialog is a scrim, not the background
check("a dimmed backdrop stays black in a light theme",
      "rgba(0, 0, 0, 200)" in B.theme_style("latte"))

print("\n(4) the browser wears it")
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.show()
spin(1500)

check("a fresh config gets the default theme", B.ACTIVE_THEME == "mocha")
check("and the application sheet is the default one",
      app.styleSheet() == B.STYLE)

win.apply_theme("gruvbox-light")
check("switching writes it down", win.config.get("theme") == "gruvbox-light")
check("and repaints the window without a restart",
      app.styleSheet() != B.STYLE
      and B.theme_palette("gruvbox-light")["bg"].upper() in app.styleSheet())

names = set()
for prof in win._all_profiles():
    for s in prof.scripts().toList():
        names.add(s.name())
check("every cookie jar carries the painter", "theme" in names,
      ", ".join(sorted(names)))
fresh = win._session_profile("themetest")
spin(300)
check("and so does a virtual browser made afterwards",
      any(s.name() == "theme" for s in fresh.scripts().toList()))
check("the painter carries the current palette, not the default",
      B.theme_palette("gruvbox-light")["bg"] in
      [s.sourceCode() for s in fresh.scripts().toList()
       if s.name() == "theme"][0])

print("\n(5) a light theme and what websites are told")
check("a light theme is not marked dark", not B.theme_is_dark("gruvbox-light"))
attr = B.QWebEngineSettings.WebAttribute.ForceDarkMode
win.config["forceDark"] = True
win.apply_web_attributes()
check("auto-darken is off while a light theme is on",
      not win.profile.settings().testAttribute(attr))
win.apply_theme("mocha")
check("and comes back with a dark one",
      win.profile.settings().testAttribute(attr))
check("the setting itself was never touched", win.config["forceDark"] is True)

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = \
    "--blink-settings=preferredColorScheme=0 --something-else"
B.CONFIG_FILE.write_text(json.dumps({"theme": "gruvbox-light"}))
B._install_theme_flags()
flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
check("launching on a light theme asks websites for their light version",
      "preferredColorScheme=1" in flags
      and "preferredColorScheme=0" not in flags, flags.strip())
check("and nothing else in the flags was disturbed",
      "--something-else" in flags)
B.CONFIG_FILE.write_text(json.dumps({"theme": "mocha"}))
B._install_theme_flags()
check("launching on a dark one asks for dark, as it always did",
      "preferredColorScheme=0" in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"])
B._select_theme("mocha")

print("\n(6) the page in the browser")
win.open_settings()
spin(3500)
page = win._panes["settings"].view.page()
js(page, "window.__probe = 'kept';")

for key in ("steampunk", "solarized-light", "mocha"):
    win.apply_theme(key)
    spin(700)
    got = json.loads(js(page, """JSON.stringify({
        probe: window.__probe || "",
        theme: document.documentElement.getAttribute("data-theme"),
        bg: getComputedStyle(document.body).backgroundColor,
        cards: document.querySelectorAll(".tcard").length,
        sel: (document.querySelector(".tcard.sel") || {dataset: {}})
               .dataset.key || "",
        varbg: getComputedStyle(document.documentElement)
                 .getPropertyValue("--bg").trim()})""") or "{}")
    pal = B.theme_palette(key)
    rgb = "rgb(%d, %d, %d)" % B._hex_rgb(pal["bg"])
    check("%s: the open page repaints in place" % key,
          got.get("probe") == "kept" and got.get("theme") == key,
          got.get("theme"))
    check("%s: right down to its background" % key, got.get("bg") == rgb,
          "%s vs %s" % (got.get("bg"), rgb))
    check("%s: and hands the palette to the page as variables" % key,
          got.get("varbg") == pal["bg"], got.get("varbg"))
    check("%s: the picker lists every theme and ticks this one" % key,
          got.get("cards") == len(B.THEMES) and got.get("sel") == key,
          "%s cards, %s ticked" % (got.get("cards"), got.get("sel")))

print("\n(6b) finding a theme")
got = json.loads(js(page, """(function () {
  var rail = document.getElementById("navfilter");
  rail.value = "steampunk";
  rail.oninput({target: rail});
  var hit = [...document.querySelectorAll("#sidebar button")]
              .filter(function (b) { return b.style.display !== "none"; })
              .map(function (b) { return b.textContent.trim(); });
  rail.value = "";
  rail.oninput({target: rail});
  var box = document.getElementById("themefilter");
  box.value = "gruvbox";
  box.oninput({target: box});
  var shown = [...document.querySelectorAll(".tcard")]
                .filter(function (c) { return c.style.display !== "none"; })
                .map(function (c) { return c.dataset.key; });
  box.value = "zzzz";
  box.oninput({target: box});
  var none = document.getElementById("themenomatch")
               .classList.contains("on");
  box.value = "";
  box.oninput({target: box});
  return JSON.stringify({rail: hit, shown: shown, none: none,
                         back: document.querySelectorAll(".tcard").length});
})()""") or "{}")
check("the rail's own search finds the section by a theme's name",
      got.get("rail") == ["Theme"], str(got.get("rail")))
check("the box in the section narrows it to one family",
      sorted(got.get("shown", [])) == ["gruvbox", "gruvbox-hard",
                                       "gruvbox-light", "gruvbox-light-hard"],
      ", ".join(got.get("shown", [])))
check("and says so when nothing matches", got.get("none") is True)
check("clearing it brings them all back",
      got.get("back") == len(B.THEMES))

print("\n(7) it does not touch anything that is not ours")
tab = win.new_tab(url=(SCRATCH / "stranger.html").as_uri())
(SCRATCH / "stranger.html").write_text(
    "<style>body{background:#cdd6f4}</style><p id=p>hi</p>")
tab.load(B.QUrl.fromLocalFile(str(SCRATCH / "stranger.html")))
spin(2000)
win.apply_theme("terminal")
spin(900)
got = js(tab.page(), "getComputedStyle(document.body).backgroundColor")
check("someone else's HTML on the disk keeps its own colours",
      got == "rgb(205, 214, 244)", str(got))
check("and never sees the palette",
      js(tab.page(), "typeof window.__applyTheme") == "undefined")

print("\n(8) the bridge")
cat = json.loads(win.bridge.themes())
check("the picker is handed the whole catalogue",
      len(cat["themes"]) == len(B.THEMES) and cat["groups"] == B.THEME_GROUPS)
check("with a swatch for each", all(len(t["swatch"]) == 6
                                    for t in cat["themes"]))
s = json.loads(win.bridge.getSettings())
check("settings say which theme is on", s["theme"] == B.ACTIVE_THEME)
check("a dark theme on a dark start needs no restart",
      s["themeLaunchDark"] is True and s["themeDark"] is True,
      "launched dark=%s, now dark=%s" % (s["themeLaunchDark"], s["themeDark"]))
win.bridge.setTheme("solarized-light")
s = json.loads(win.bridge.getSettings())
check("a light theme on a dark start is where the picker offers one",
      s["themeLaunchDark"] is True and s["themeDark"] is False,
      "launched dark=%s, now dark=%s" % (s["themeLaunchDark"], s["themeDark"]))
win.bridge.setTheme("nord")
check("setting one through the bridge takes", B.ACTIVE_THEME == "nord")

print("\n(9) every string the picker shows exists in both languages")
missing = [k for k in B.UI_STRINGS["en"] if k.startswith("theme")
           and k not in B.UI_STRINGS["de"]]
check("English and German both have them", not missing, ", ".join(missing))

print("\n%d checks failed" % FAILS)
app.quit()
sys.exit(1 if FAILS else 0)
