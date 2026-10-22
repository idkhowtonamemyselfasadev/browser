#!/usr/bin/env python3
"""Appearance, part two: themes of his own, the size and shape of the
chrome, how pages are shown, the start page's layout, and the two things
the browser can follow (the desktop's light/dark setting and a file of
colours).

Offscreen, scratch data, local server. Nothing here goes online: the
themes are read from files written in the scratch directory, and the
desktop's colour scheme is asked of Qt, not of a portal.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()
from PyQt6.QtCore import QPoint, QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QIcon, QPixmap  # noqa: E402

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


PAGE = ('<title>A page</title>'
        '<meta name="theme-color" content="#223344">'
        '<p style="color:#333">a page with text on it</p>'
        '<div style="height:3000px"></div>')
PAGES = {"/p": PAGE, "/q": "<title>Q</title><p>q</p>",
         "/echo": "<title>echo</title>"}

app = H.app()
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en",
                                     "restoreTabs": False}))
win = B.Browser()
win.resize(1100, 800)
win.show()
H.spin(400)
MAIN = B.MAIN_WORLD_ID
APP = B.APP_WORLD_ID
scratch = B.CONFIG_FILE.parent
view = win.new_tab(url=None)
H.load(view, srv.url("/p"))
H.spin(500)


def look(v=None):
    return H.js(v or view,
                "(document.getElementById('__pagelook')||{})"
                ".textContent || ''", APP) or ""


def filt(v=None):
    return H.js(v or view, "document.documentElement.style.filter", APP) or ""


SEED = {"bg": "#101014", "surface": "#1a1a22", "text": "#d8d8e0",
        "accent": "#7aa2f7", "green": "#9ece6a", "yellow": "#e0af68",
        "peach": "#ff9e64", "red": "#f7768e"}

print("\n(1) a theme of his own")
key = win.save_custom_theme("Kitty Night", SEED)
check("it is saved under a prefixed key", key == "mine-kitty-night", key)
check("...and joins the catalogue", key in B.THEME_INDEX)
check("...on the shelf he gave it",
      B.THEME_INDEX[key]["group"] == "character")
check("...and the picker lists it",
      any(row["key"] == key for row in B.theme_catalogue()))
win.apply_theme(key)
check("it can be worn", B.ACTIVE_THEME == key, B.ACTIVE_THEME)
check("...and the window really is painted in it",
      "#101014" in app.styleSheet().lower())
check("...and the derived colours came out of the eight",
      B.theme_palette(key)["crust"] not in ("", None),
      B.theme_palette(key)["crust"])
check("the eight can be read back",
      B.theme_seed(key)["accent"] == "#7aa2f7", B.theme_seed(key))
check("a half-written seed is still a theme",
      B._custom_entry("mine-half", {"bg": "#000000"})["text"]
      == B.THEME_INDEX[B.DEFAULT_THEME]["text"])
check("a key that is not his own is refused",
      B.register_custom_themes({"mocha": {"bg": "#ffffff"}}) == [])
check("...and mocha is untouched",
      B.THEME_INDEX["mocha"]["bg"] != "#ffffff",
      B.THEME_INDEX["mocha"]["bg"])
# that call registered a table of its own, which is what the real one
# does with the config: his own themes go back in before anything else
win.load_custom_themes()
check("...and his own are still there after it", key in B.THEME_INDEX)
seen = win.theme_warnings({"bg": "#101014", "surface": "#111118",
                           "text": "#141418", "accent": "#101014"})
check("a theme too faint to read says so", len(seen) >= 2, seen)
check("...with the measured ratio",
      all(0 < row["ratio"] < 21 for row in seen), seen)
check("a readable one says nothing", win.theme_warnings(SEED) == [],
      win.theme_warnings(SEED))

print("\n(2) a theme in a file")
out = win.export_theme(key, path=str(scratch / "mine.json"))
check("it writes out", bool(out) and Path(out).is_file(), out)
written = json.loads(Path(out).read_text())
check("...as the eight colours and a name",
      written["colors"]["bg"] == "#101014" and written["name"], written)
back = win.import_theme(str(scratch / "mine.json"))
check("...and reads back in", back.startswith("mine-"), back)
(scratch / "kitty.conf").write_text(
    "# a kitty theme\nbackground #202030\nforeground #e0e0ee\n"
    "color1 #ff6666\ncolor2 #66ff66\ncolor4 #88aaff\n")
kit = win.import_theme(str(scratch / "kitty.conf"))
check("a kitty.conf is read", kit.startswith("mine-"), kit)
check("...with its background", B.THEME_INDEX[kit]["bg"] == "#202030",
      B.THEME_INDEX[kit]["bg"])
check("...and color4 as the accent",
      B.THEME_INDEX[kit]["accent"] == "#88aaff",
      B.THEME_INDEX[kit]["accent"])
(scratch / "base16.yaml").write_text(
    'base00: "1d2021"\nbase05: "d5c4a1"\nbase0d: "83a598"\n'
    'base08: "fb4934"\n')
b16 = win.import_theme(str(scratch / "base16.yaml"))
check("a base16 YAML is read too", B.THEME_INDEX[b16]["bg"] == "#1d2021",
      B.THEME_INDEX[b16]["bg"])
check("...and its accent", B.THEME_INDEX[b16]["accent"] == "#83a598",
      B.THEME_INDEX[b16]["accent"])
(scratch / "code.json").write_text(json.dumps(
    {"name": "Code", "colors": {"editor.background": "#1e1e2e",
                                "editor.foreground": "#cdd6f4",
                                "focusBorder": "#89b4fa"}}))
vsc = win.import_theme(str(scratch / "code.json"))
check("a VS Code theme is read", B.THEME_INDEX[vsc]["bg"] == "#1e1e2e",
      B.THEME_INDEX[vsc]["bg"])
(scratch / "nothing.txt").write_text("this file has no colours in it\n")
check("a file with no colours is refused",
      win.import_theme(str(scratch / "nothing.txt")) == "")
win.apply_theme("mocha")
acc = win.accent_override("#ff8800")
check("the accent can be replaced", acc.startswith("mine-"), acc)
check("...and the rest of the palette is the theme's",
      B.theme_palette(acc)["bg"] == B.theme_palette("mocha")["bg"])
check("...with his accent on it",
      B.theme_palette(acc)["accent"] == "#ff8800",
      B.theme_palette(acc)["accent"])
check("a colour that is not a colour is refused",
      win.accent_override("orange") == "")
win.apply_theme(key)
check("one of his own can be deleted", win.drop_custom_theme(key) is True)
check("...and the browser falls back rather than wear nothing",
      win.config.get("theme") == B.DEFAULT_THEME, win.config.get("theme"))
check("...and it is out of the catalogue", key not in B.THEME_INDEX)
check("deleting one that is not there says so",
      win.drop_custom_theme("mine-nope") is False)

print("\n(3) the size, shape and lettering of the chrome")
check("compact is a size", win.set_ui_size("compact") is True)
check("...and the sheet says so",
      "padding: 5px 6px 5px 14px" in app.styleSheet())
check("a size that is not offered is refused",
      win.set_ui_size("enormous") is False)
win.set_ui_size("normal")
check("normal adds no size rule of its own",
      "QTabBar::tab { padding:" not in B.chrome_style({"uiSize": "normal"}),
      B.chrome_style({"uiSize": "normal"})[:60])
check("the corners can be squared", win.set_corner_radius(0) == 0)
check("...and every surface is square",
      "border-radius: 0px" in app.styleSheet())
check("...and rounded again", win.set_corner_radius(14) == 14)
check("a radius out of range is clamped", win.set_corner_radius(99) == 24)
check("the UI font can be set",
      win.set_ui_font("JetBrainsMono Nerd Font", 15) is True)
check("...and is in the sheet", 'font-size: 15px' in app.styleSheet())
fams = win.ui_font_families()
check("the picker has monospace families first",
      len(fams["mono"]) > 0 and "mono" in fams and "other" in fams,
      len(fams["mono"]))
check("glass strength is a number", win.set_glass_strength(50) == 50)
check("...which only glass reads",
      "rgba(13, 13, 18, 127)" not in app.styleSheet())
win.apply_look("glass")
win.set_glass_strength(100)
check("...and in glass it is in the sheet",
      "rgba(13, 13, 18, 40)" in app.styleSheet()
      or "rgba(13, 13, 18, 41)" in app.styleSheet(),
      [ln for ln in app.styleSheet().splitlines() if "13, 13, 18," in ln][:2])
win.apply_look("classic")
check("words can go on the buttons", win.set_text_labels(True) is True)
check("...and the buttons carry a style for it",
      any(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
          for b in win.findChildren(B.QToolButton)))
win.set_text_labels(False)
check("the focus ring can be thick", win.set_focus_ring("thick") == "thick")
check("...and is in the sheet", "2px solid" in app.styleSheet())
check("it can be switched off", win.set_focus_ring("off") == "off")
check("...and then nothing outlines", "outline: none" in app.styleSheet())
win.set_focus_ring("normal")
win.config["tabMaxWidth"] = 200
win.config["toolbarHeight"] = 40
win.config["plainMenus"] = True
win.apply_chrome_style()
check("the widest a tab may get is in the sheet",
      "max-width: 200px" in app.styleSheet())
check("...and the toolbar's height", "min-height: 40px" in app.styleSheet())
check("...and plain menus", "padding: 10px 24px" in app.styleSheet())
for key_ in ("tabMaxWidth", "toolbarHeight", "plainMenus"):
    win.config.pop(key_, None)
win.apply_chrome_style()
check("the animation switch answers", win.set_ui_animation(False) is False)
check("...and the browser knows it is off", win.ui_animation_on() is False)
check("...and our own pages are told to hold still",
      "animation: none" in win.own_page_theme()["extra"],
      win.own_page_theme()["extra"][:60])
win.set_ui_animation(True)
check("close buttons can be asked for on every tab",
      win.config.get("closeButtons", "wide") == "wide")

print("\n(4) how websites are shown")
check("the scrollbars can be themed", win.set_scrollbars("themed") == "themed")
H.spin(500)
check("...and the page has the sheet for it",
      "::-webkit-scrollbar" in look(), look()[:60])
check("...in the theme's colours",
      B.theme_palette()["surface"] in look(), look()[:200])
check("a style that is not offered is refused",
      win.set_scrollbars("curly") is False)
check("one site can be excused",
      win.set_scrollbars(host="127.0.0.1") is True)
H.spin(500)
check("...and then its scrollbars are its own",
      "::-webkit-scrollbar" not in look(), look()[:60])
win.set_scrollbars(host="127.0.0.1")
win.set_scrollbars("normal")
check("the selection colour can be ours",
      win.set_themed_selection(True) is True)
H.spin(400)
check("...and the page says so", "::selection" in look())
win.set_themed_selection(False)
check("a page with no background of its own can have the theme's",
      win.set_unstyled_background(True) is True)
H.spin(400)
check("...and the rule is there", "html:not([style" in look(), look()[:60])
win.set_unstyled_background(False)
check("a site can have its own text size",
      win.set_site_font_size("127.0.0.1", 22) == 22)
H.spin(500)
check("...and the page really is that size",
      H.js(view, "getComputedStyle(document.documentElement).fontSize",
           MAIN) == "22px",
      H.js(view, "getComputedStyle(document.documentElement).fontSize", MAIN))
check("...and it can be taken off again",
      win.set_site_font_size("127.0.0.1", None) == 0)
check("the evening is worked out from two times",
      B.evening_now({"nightDimFrom": "00:00", "nightDimTo": "23:59"}) is True)
check("...and wraps around midnight",
      B.evening_now({"nightDimFrom": "21:00", "nightDimTo": "07:00"},
                    time.struct_time((2026, 10, 18, 23, 30, 0, 5, 291, 0)))
      is True)
check("...and says no outside the hours",
      B.evening_now({"nightDimFrom": "21:00", "nightDimTo": "07:00"},
                    time.struct_time((2026, 10, 18, 12, 0, 0, 5, 291, 0)))
      is False)
check("two times the same is no evening at all",
      B.evening_now({"nightDimFrom": "07:00", "nightDimTo": "07:00"})
      is False)
check("the dimmer takes a strength", win.set_night_dim(30, "00:00", "23:59")
      == 30)
H.spin(500)
check("...and the page is dimmed", "brightness(0.7)" in filt(), filt())
check("...and the chrome is not", app.styleSheet().count("brightness") == 0)
check("warmer colours too", win.set_warm_night(True, 50) is True)
H.spin(500)
check("...and the filter has the sepia in it", "sepia(" in filt(), filt())
win.set_warm_night(False)
win.set_night_dim(0)
H.spin(400)
check("...and with both off nothing is filtered", filt() == "", filt())
check("grey can go on everywhere", win.toggle_greyscale() is True)
H.spin(400)
check("...and the page is grey", "grayscale(1)" in filt(), filt())
win.toggle_greyscale(on=False)
check("one site can be grey on its own",
      win.toggle_greyscale(host="127.0.0.1") is True)
H.spin(500)
check("...and that site is grey", "grayscale(1)" in filt(), filt())
check("...and it comes off again",
      win.toggle_greyscale(host="127.0.0.1") is False)
check("the fallback fonts are settable",
      win.set_site_font("mono", "JetBrainsMono Nerd Font") is True)
check("...and reach every jar", "mono" in win.apply_site_fonts(),
      win.apply_site_fonts())
check("...including the emoji family",
      win.set_site_font("emoji", "Noto Color Emoji") is True
      and win.config.get("emojiFont") == "Noto Color Emoji")
check("...which is Chromium's pictograph family",
      win.SITE_FONT_ROLES["emoji"] == "PictographFont")
check("a role that is not one is refused",
      win.set_site_font("curly", "x") is False)

print("\n(5) plain files and a PDF")
(scratch / "plain.txt").write_text("just some text in a file\n")
check("plain files can be ours", win.set_raw_views(True) is True)
raw = win.new_tab(url=None)
H.load(raw, QUrl.fromLocalFile(str(scratch / "plain.txt")).toString())
H.spin(900)
check("...and a .txt is on the theme's background",
      H.js(raw, "getComputedStyle(document.body).backgroundColor", MAIN)
      != "rgba(0, 0, 0, 0)",
      H.js(raw, "getComputedStyle(document.body).backgroundColor", MAIN))
check("...and its text is the theme's",
      H.js(raw, "getComputedStyle(document.querySelector('pre')).color",
           MAIN) != "rgb(0, 0, 0)",
      H.js(raw, "getComputedStyle(document.querySelector('pre')).color", MAIN))
shot = QImage(8, 8, QImage.Format.Format_ARGB32)
shot.fill(0)
shot.save(str(scratch / "clear.png"), "PNG")
H.load(raw, QUrl.fromLocalFile(str(scratch / "clear.png")).toString())
H.spin(900)
check("an image on its own gets a checkerboard",
      "linear-gradient" in (H.js(
          raw, "getComputedStyle(document.body).backgroundImage", MAIN) or ""),
      (H.js(raw, "getComputedStyle(document.body).backgroundImage",
            MAIN) or "")[:40])
win.set_raw_views(False, checker=False)
check("the dark PDF switch answers", win.set_dark_pdf(True) is True)
pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
       b"/Contents 4 0 R>>endobj\n4 0 obj<</Length 44>>stream\n"
       b"BT /F1 24 Tf 20 100 Td (hello pdf) Tj ET\nendstream\nendobj\n"
       b"trailer<</Root 1 0 R>>\n")
(scratch / "t.pdf").write_bytes(pdf)
win.config["pdfViewer"] = True
win.apply_web_attributes()
H.load(raw, QUrl.fromLocalFile(str(scratch / "t.pdf")).toString())
H.spin(2500)
check("...and the plugin really carries the filter",
      "invert(1)" in (H.js(
          raw, "(document.querySelector('embed')||{}).style"
               " && document.querySelector('embed').style.filter || ''",
          APP) or ""),
      H.js(raw, "(document.querySelector('embed')||{}).style"
                " && document.querySelector('embed').style.filter || ''",
           APP))
win.set_dark_pdf(False)
win.close_tab(win.tabs.indexOf(raw))

print("\n(6) the chrome's own marks")
check("a virtual browser can have a colour",
      win.set_session_tint("#ff8800") == "#ff8800")
check("...and it is in the sheet", "#ff8800" in app.styleSheet())
check("a colour that is not one is refused",
      win.set_session_tint("mauve") == "")
check("...and it can be taken off", win.set_session_tint("") == "")
check("private tabs have their own colour",
      win.set_private_tint("#cba6f7") == "#cba6f7")
priv = win.new_tab(url=None, private=True)
H.spin(300)
check("...and a private tab is written in it",
      win.tabs.tabBar().tabTextColor(win.tabs.indexOf(priv)).name()
      == "#cba6f7",
      win.tabs.tabBar().tabTextColor(win.tabs.indexOf(priv)).name())
check("...and an ordinary tab is not",
      not win.tabs.tabBar().tabTextColor(win.tabs.indexOf(view)).isValid())
win.close_tab(win.tabs.indexOf(priv))
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
pix = QPixmap(16, 16)
pix.fill(QColor("#ff0000"))
flat = win.mono_icon(QIcon(pix))
check("a favicon can be flattened", not flat.isNull())
win.config["monoFavicons"] = True
flat = win.mono_icon(QIcon(pix))
img = flat.pixmap(16, 16).toImage()
check("...and every pixel is the theme's text colour",
      img.pixelColor(8, 8).name() == B.theme_palette()["text"],
      (img.pixelColor(8, 8).name(), B.theme_palette()["text"]))
check("...and switching it on repaints the strip",
      win.set_mono_favicons(True) is True)
win.set_mono_favicons(False)
check("the status line can move into the bar",
      win.set_status_line("bar") == "bar")
view.setFocus()          # hovering a link means the page has the focus
H.spin(150)
win.show_hovered_link(srv.url("/q"), view=view)
check("...and the hovered link is said over the bar",
      "/q" in win.bar_hover_text(), win.bar_hover_text())
win.urlbar.setFocus()
win.show_hovered_link(srv.url("/q"), view=view)
check("...but never over an address he is typing in",
      win.bar_hover_text() == "", win.bar_hover_text())
view.setFocus()
win.show_hovered_link(srv.url("/q"), view=view)
check("...without touching what is in the bar",
      "/q" not in win.urlbar.text(), win.urlbar.text())
win.show_hovered_link("", view=view)
check("...and it goes away afterwards", win.bar_hover_text() == "",
      win.bar_hover_text())
check("it can be switched off entirely", win.set_status_line("off") == "off")
win.show_hovered_link(srv.url("/q"), view=view)
check("...and then nothing is said",
      not (getattr(win, "_hoverlbl", None)
           and win._hoverlbl.isVisible()))
check("and a size for it", win.set_status_line("bottom", 11) == "bottom")
win.config["titleFormat"] = "page"
check("the window can be called after the page only",
      "browser" not in win._sync_window_title(), win._sync_window_title())
win.config["titleFormat"] = "full"
check("...or the usual way", win._sync_window_title().endswith("browser"),
      win._sync_window_title())
win.config["titleFormat"] = "site"
H.spin(200)
check("...or after the site",
      "127.0.0.1" in win._sync_window_title(), win._sync_window_title())
win.config.pop("titleFormat", None)
check("the chrome can hide itself", win.set_auto_hide_chrome(True) is True)
check("...and it is away", win.chrome_shown() is False)
check("the top edge brings it back", win.chrome_peek(2) is True)
check("...and it is there", win.chrome_shown() is True)
check("going back down puts it away", win.chrome_peek(300) is True)
check("...and it is gone again", win.chrome_shown() is False)
win.focus_address()
check("Ctrl+L brings it back too", win.chrome_shown() is True)
check("and it can be switched off", win.set_auto_hide_chrome(False) is False)
check("...which leaves the chrome up", win.chrome_shown() is True)
check("the fullscreen reveal has its own switch",
      win.set_reveal_in_fullscreen(True) is True)
win.set_reveal_in_fullscreen(False)
got = []
win.set_page_theme_colour(True)
win.page_theme_colour(view=view, then=got.append)
H.wait_for(lambda: got, 5000)
check("a site's own theme-color is read", got == ["#223344"], got)
check("...and the toolbar wears it", "#223344" in app.styleSheet())
check("...and a virtual browser's colour wins over it",
      win.set_session_tint("#00ff00") == "#00ff00"
      and "#00ff00" in app.styleSheet())
win.set_session_tint("")
win.set_page_theme_colour(False)
check("...and switching it off takes it away",
      "#223344" not in app.styleSheet())

print("\n(7) a page that did not load")
html = win.error_page_html("http://nowhere.invalid/x", "no answer")
check("the error page names the address", "nowhere.invalid" in html)
check("...says what went wrong", "no answer" in html)
check("...offers a key to try again", "Enter" in html and "keydown" in html)
check("...and is painted in the palette",
      B.theme_palette()["bg"] in html, B.theme_palette()["bg"])
check("it is off until he asks",
      win.maybe_error_page(view=view) is False)
check("switching it on answers", win.set_themed_errors(True) is True)
page = win._live_page(view)
page._reissue = (QUrl(srv.url("/p")), False)
check("...and a channel bounce is never dressed as an error",
      win.maybe_error_page(view=view) is False)
page._reissue = None
check("...but a real failure is",
      win.maybe_error_page(view=view, reason="no answer") is True)
H.spin(600)
check("...and the tab is showing it",
      "nowhere" in (H.js(view, "document.body.innerHTML", MAIN) or "")
      or "did not load" in (H.js(view, "document.body.innerText",
                                 MAIN) or ""),
      (H.js(view, "document.body.innerText", MAIN) or "")[:60])
win.set_themed_errors(False)
H.load(view, srv.url("/p"))
H.spin(400)

print("\n(8) the start page and its pictures")
layout = win.start_layout()
check("the layout has every answer in it",
      set(layout) == set(win.START_LAYOUT), sorted(layout))
check("the clock can be switched off",
      win.set_start_layout("clock", False) is False)
check("seconds can go on", win.set_start_layout("seconds", True) is True)
check("the search box can move",
      win.set_start_layout("search", "top") == "top")
check("...but only where there is room for it",
      win.set_start_layout("search", "sideways") is False)
check("...and the junk is not stored",
      win.start_layout()["search"] == "top", win.start_layout())
check("the quick links take a scale",
      win.set_start_layout("quick", 1.4) == 1.4)
check("...clamped to something sane",
      win.set_start_layout("quick", 9) == 2.0)
check("a key that is not a layout answer is refused",
      win.set_start_layout("colour", "red") is False)
shots = scratch / "walls"
shots.mkdir(exist_ok=True)
for name in ("a.png", "b.jpg", "notes.txt"):
    if name.endswith(".txt"):
        (shots / name).write_text("not a picture")
    else:
        shot = QImage(4, 4, QImage.Format.Format_RGB32)
        shot.fill(0x112233)
        shot.save(str(shots / name))
check("a wallpaper folder can be named",
      win.set_wallpaper_folder(str(shots)) == str(shots))
rows = win.wallpaper_list()
check("...and only its pictures are listed", len(rows) == 2, rows)
check("...as the files they are",
      all(r.endswith((".png", ".jpg")) for r in rows), rows)
check("how often it changes is a number", win.set_wallpaper_every(15) == 15)
payload = win.wallpaper_payload()
check("the page is handed file addresses",
      all(u.startswith("file://") for u in payload["shots"]), payload)
check("...and the interval", payload["every"] == 15, payload)
check("a folder that is not there lists nothing",
      win.wallpaper_list(str(scratch / "nope")) == [])
start = win.new_tab(url=None)
H.load(start, B.START_PAGE)
H.spin(1200)
check("the start page took the layout",
      H.js(start, "JSON.stringify(window.LAYOUT || {})", MAIN) is not None)
check("...and it is the one he set",
      H.js(start, "(document.getElementById('clock')||{}).style"
                  " && document.getElementById('clock').style.display",
           MAIN) == "none",
      H.js(start, "(document.getElementById('clock')||{}).style.display",
           MAIN))
check("...and the quick links are scaled",
      (H.js(start, "getComputedStyle(document.documentElement)"
                   ".getPropertyValue('--quickscale')", MAIN) or "").strip()
      in ("2", "2.0"),
      H.js(start, "getComputedStyle(document.documentElement)"
                  ".getPropertyValue('--quickscale')", MAIN))
check("...and a wallpaper is on it",
      "walls" in (H.js(start, "document.body.style.backgroundImage",
                       MAIN) or ""),
      (H.js(start, "document.body.style.backgroundImage", MAIN) or "")[:60])
win.set_wallpaper_folder("")
win.config.pop("startLayout", None)
win.close_tab(win.tabs.indexOf(start))

print("\n(9) following the desktop, and a file of colours")
check("the desktop's setting is asked of Qt",
      win.desktop_colour_scheme() in ("", "dark", "light"),
      win.desktop_colour_scheme())
check("following is off until he asks",
      win.follow_desktop_scheme() == "")
check("switching it on answers",
      win.set_follow_scheme(True, dark="nord", light="latte") is True)
win.desktop_colour_scheme = lambda: "light"
check("...and a light desktop picks his light theme",
      win.follow_desktop_scheme() == "latte", win.config.get("theme"))
win.desktop_colour_scheme = lambda: "dark"
check("...and a dark one his dark theme",
      win.follow_desktop_scheme() == "nord", win.config.get("theme"))
win.desktop_colour_scheme = lambda: ""
check("...and a desktop with no answer changes nothing",
      win.follow_desktop_scheme() == "")
win.set_follow_scheme(False)
(scratch / "rice.conf").write_text(
    "background #202030\nforeground #e0e0ee\ncolor4 #88aaff\n")
check("a colour file can be followed",
      win.follow_colour_file(str(scratch / "rice.conf")).endswith("rice.conf"))
check("...and a change re-themes the browser",
      win._colour_file_changed(str(scratch / "rice.conf"))
      == "mine-desktop")
check("...wearing it", win.config.get("theme") == "mine-desktop",
      win.config.get("theme"))
check("...in the colours of the file", "#202030" in app.styleSheet().lower())
(scratch / "rice.conf").write_text("background #303040\nforeground #eeeeff\n")
win._colour_file_changed(str(scratch / "rice.conf"))
check("...and a second change replaces it rather than adding another",
      len([k for k in win.custom_themes() if k == "mine-desktop"]) == 1
      and "#303040" in app.styleSheet().lower(),
      sorted(win.custom_themes()))
check("a file with nothing in it changes nothing",
      win._colour_file_changed(str(scratch / "nothing.txt")) is False)
win.follow_colour_file("", on=False)
win.apply_theme("mocha")

print("\n(10) the themes he keeps coming back to")
check("a theme can be starred", win.star_theme("nord") is True)
check("...and another", win.star_theme("latte") is True)
check("...and they are listed", win.favourite_themes() == ["nord", "latte"],
      win.favourite_themes())
check("the next one is the next one", win.cycle_theme() == "nord")
check("...and round it goes", win.cycle_theme() == "latte")
check("...and back", win.cycle_theme() == "nord")
check("the star comes off again", win.star_theme("nord") is False)
check("a theme that is not in the catalogue cannot be starred",
      win.star_theme("nothing-like-this") is False)
win.config["favouriteThemes"] = []
check("with nothing starred it says so", win.cycle_theme() == "")
win.apply_theme("mocha")

print("\n(11) the flat look")
check("it is one of the looks",
      any(entry["key"] == "flat" for entry in B.LOOKS))
win.apply_look("flat")
check("...and it can be worn", B.active_look() == "flat")
check("...and it is square",
      "border-radius: 0px" in app.styleSheet())
check("...and lettered in one font",
      'font-family: "JetBrainsMono Nerd Font", monospace' in
      app.styleSheet())
win.apply_look("classic")

print("\n(12) the appearance menu, Settings and the words")
menu = win.appearance_menu()
rows = [a.text() for a in menu.actions()]
check("the menu has the themes", win._ui_str("themeMine") in rows, rows)
check("...the shape", win._ui_str("lookMenuName") in rows, rows)
check("...the size", win._ui_str("uiSizeName") in rows, rows)
check("...and the switches worth having here",
      win._ui_str("greyName") in rows, rows)
subs = {a.text(): a.menu() for a in menu.actions() if a.menu()}
check("the looks are all offered",
      len(subs[win._ui_str("lookMenuName")].actions()) == len(B.LOOKS))
check("...and this site has its own rows",
      any("127.0.0.1" in text for text in rows), rows)
page_text = Path("settings.html").read_text()
for ident in ("nightdim", "warmnight", "greyscale", "scrollbars",
              "themedselection", "unstyledbg", "rawviews", "rawchecker",
              "darkpdf", "darksiterules", "sitefontmono", "emojifont",
              "uisize", "uifont", "cornerradius", "glassstrength",
              "textlabels", "focusring", "uianim", "tabmaxwidth",
              "toolbarheight", "plainmenus", "monofavicons", "autohide",
              "revealfs", "statusline", "titleformat", "pagethemecolour",
              "themederrors", "devtoolsdark", "startclock", "startseconds",
              "startdate", "starthour24", "startsearchpos", "startquick",
              "wallfolder", "wallevery", "followscheme", "schemedark",
              "schemelight", "colourfile", "themesave", "themeexport",
              "themeimport", "themestarbtn", "themecyclebtn",
              "appearancereset", "appearanceundo"):
    check("Settings has a row for " + ident,
          ('id="%s"' % ident) in page_text, ident)
check("...and they are all bound",
      'bindAppearance();' in page_text
      and '["warmnight", "warmNight"]' in page_text)
need = ["themeMine", "themeEditor", "themeSave", "themeExport",
        "themeImport", "themeImportBad", "themeAccent", "themeFaint",
        "uiSizeName", "uiSizeHint", "uiSize_compact", "uiFontName",
        "uiRadiusName", "uiGlassName", "uiLabelsName", "uiFocusName",
        "uiAnimName", "uiToolbarName", "uiPlainMenusName",
        "appearanceResetName", "appearanceReset", "pageLookName",
        "nightDimName", "warmNightName", "greyName", "scrollbarsName",
        "selectionName", "unstyledName", "siteFontSizeName",
        "siteFontsName", "siteFont_emoji", "sessionTintName",
        "privateTintName", "monoFaviconsName", "statusLineName",
        "titleFormatName", "autoHideName", "revealFsName",
        "pageColourName", "themedErrorsName", "errTitle", "errAgain",
        "startLayoutName", "startClockName", "startQuickName",
        "wallFolderName", "wallEveryName", "darkSiteName", "darkSiteHere",
        "followSchemeName", "colourFileName", "themeStarName",
        "themeCycle", "lookFlat", "lookFlatSub", "rawViewName",
        "darkPdfName", "devtoolsDarkName", "appearanceMenu",
        "lookMenuName"]
missing_en = [k for k in need if not B.UI_STRINGS["en"].get(k)]
missing_de = [k for k in need if not B.UI_STRINGS["de"].get(k)]
check("every new word has an English", missing_en == [], missing_en)
check("...and a German", missing_de == [], missing_de)
same = [k for k in need
        if k not in ("siteFont_emoji", "lookFlat", "errTitle")
        and B.UI_STRINGS["en"].get(k) == B.UI_STRINGS["de"].get(k)]
check("and they are really translated", same == [], same)
rows = win.actions_list()
ids = [row.get("id") for row in rows]
for ident in ("lookmenu", "themecycle", "themestar", "uilabels",
              "autohide", "greyscale", "monofavicons", "themeeditor"):
    check("there is an action for " + ident, ident in ids, ident)
check("no two actions share an id", len(ids) == len(set(ids)),
      [i for i in ids if ids.count(i) > 1][:4])
keys = {}
for row in rows:
    if row.get("key"):
        keys.setdefault(row["key"], []).append(row["id"])
check("no two actions want the same key",
      {k: v for k, v in keys.items() if len(v) > 1} == {},
      {k: v for k, v in keys.items() if len(v) > 1})
check("the reset knows every key this wave added",
      all(k in win.APPEARANCE_KEYS for k in
          ("uiSize", "cornerRadius", "scrollbars", "nightDim", "startLayout",
           "wallpaperFolder", "customThemes", "favouriteThemes",
           "rawViews", "darkPdf", "monoFavicons", "statusLine")),
      [k for k in ("uiSize", "rawViews", "darkPdf")
       if k not in win.APPEARANCE_KEYS])
win.set_ui_size("big")
win.save_custom_theme("Keep me", SEED)
was = win.reset_appearance()
check("resetting puts the theme back", B.ACTIVE_THEME == B.DEFAULT_THEME,
      B.ACTIVE_THEME)
check("...and the size", win.config.get("uiSize") is None)
check("...and keeps a backup of what was there",
      "uiSize" in was and "customThemes" in was, sorted(was)[:5])
check("...which can be put back",
      win.undo_reset_appearance() is True
      and win.config.get("uiSize") == "big", win.config.get("uiSize"))
check("...his own themes included",
      any(k.startswith("mine-keep") for k in win.custom_themes()),
      sorted(win.custom_themes()))
win.reset_appearance(keep_backup=False)
check("an undo with no backup says so",
      win.undo_reset_appearance() is False)

print()
if fails:
    print("FAILED %d" % len(fails))
    for row in fails:
        print("  - " + row)
    sys.exit(1)
print("all good")
