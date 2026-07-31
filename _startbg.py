#!/usr/bin/env python3
"""The start page over a photograph, in a row of themes.

A wallpaper is the one background the palette knows nothing about: the
clock and the date sit straight on somebody's picture, and a bright sky
under a light theme's dark text is exactly where legibility goes. This
photographs it, and reads back what the scrim and the halo actually
came out as. Offscreen, scratch data only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B, SCRATCH  # noqa: E402,F401
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer, QEventLoop, QUrl  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/startbg")
SHOTS = sys.argv[2].split(",") if len(sys.argv) > 2 else [
    "mocha", "nord-light", "solarized-light", "gruvbox-light", "terminal",
    "sepia", "steam"]
OUT.mkdir(parents=True, exist_ok=True)

# the start page, not the setup wizard that covers it on a fresh config
cfg = json.loads(B.CONFIG_FILE.read_text()) if B.CONFIG_FILE.exists() else {}
cfg.setdefault("startPage", {})["setupDone"] = True
B.CONFIG_FILE.write_text(json.dumps(cfg))

app = QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1280, 860)
win.show()


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


view = win.new_tab(url=QUrl(B.START_PAGE).toString())
spin(3000)
page = view.page()
js(page, """localStorage.setItem("bg", "backgrounds/nature-1018.jpg");""")
view.reload()
spin(3000)

fails = 0
for key in SHOTS:
    win.apply_theme(key)
    spin(900)
    win.grab().save(str(OUT / ("startbg-%s.png" % key)))
    # and the same page with nothing behind it, where a theme's own
    # texture is the only thing on the background
    js(page, """document.body.classList.remove("hasbg");
                document.body.style.backgroundImage = "";""")
    spin(400)
    win.grab().save(str(OUT / ("startplain-%s.png" % key)))
    js(page, """document.body.classList.add("hasbg");
                document.body.style.backgroundImage =
                  'url("backgrounds/nature-1018.jpg")';""")
    spin(400)
    got = js(page, """JSON.stringify({
        hasbg: document.body.classList.contains("hasbg"),
        scrim: getComputedStyle(document.body, "::before").backgroundColor,
        halo: getComputedStyle(document.getElementById("clock")).textShadow,
        clock: getComputedStyle(document.getElementById("clock")).color})""")
    st = json.loads(got) if got else {}
    pal = B.theme_palette(key)
    want = "rgb(%d, %d, %d)" % B._hex_rgb(pal["bg"])
    ok = st.get("hasbg") and st.get("scrim") == want and want in (
        st.get("halo") or "")
    print(("  ok   " if ok else "  FAIL ")
          + "%-18s scrim=%-18s wanted %s" % (key, st.get("scrim"), want))
    print("         halo=%s" % (st.get("halo") or "")[:96])
    fails += 0 if ok else 1

# A theme with a texture puts it on the page and nowhere else. This is
# what the diagonal hatch running through the start page's search box
# was: a pattern on a fixed sheet of glass over the whole window.
print()
for key in ("terminal", "amber", "blueprint", "synthwave", "gameboy",
            "sepia", "steampunk"):
    win.apply_theme(key)
    spin(700)
    got = js(page, """(function () {
      function bg(el) { return el ? getComputedStyle(el).backgroundImage
                                  : "none"; }
      function over(el) {
        if (!el) return "none";
        return getComputedStyle(el, "::after").backgroundImage + " "
             + getComputedStyle(el, "::before").backgroundImage;
      }
      document.body.classList.remove("hasbg");
      document.body.style.backgroundImage = "";
      return JSON.stringify({
        page: bg(document.body),
        root: over(document.documentElement),
        input: bg(document.querySelector("form.search input")),
        box: bg(document.querySelector("form.search")),
        link: bg(document.querySelector(".links a"))});
    })()""")
    st = json.loads(got) if got else {}
    behind = "gradient" in (st.get("page") or "")
    clear = not any("gradient" in (st.get(k) or "")
                    for k in ("root", "input", "box", "link"))
    print(("  ok   " if behind and clear else "  FAIL ")
          + "%-12s texture on the page=%s, off the box and the links=%s"
          % (key, behind, clear))
    fails += 0 if behind and clear else 1

print("\n%d checks failed" % fails)
print("shots in", OUT)
app.quit()
sys.exit(1 if fails else 0)
