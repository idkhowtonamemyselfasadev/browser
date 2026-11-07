"""Site theming — the active theme restyles real websites, with character.

A companion to the engine pane. browser.py's own THEME_JS deliberately
paints only the six file:// pages of the browser; this module injects a
second, separate script into every cookie jar that does the opposite —
it skips file:// entirely and gives ordinary websites the active theme.

Three layers, all in one injected script:
  1. base CSS      — palette colours for page, text, forms,
                     scrollbars, selection; focus rings. No transition
                     between themes: see _base_css for why a fade on
                     every element was the fault behind most of what
                     the 2026-11-07 site matrix found.
  2. adaptive pass — JavaScript reads each element's real colours and
                     remaps them: on a dark theme a white card becomes a
                     `surface` card (brighter cards stay relatively
                     brighter, so the page keeps its depth), dark text
                     on it becomes readable; on a light theme the
                     reverse. A MutationObserver keeps up with pages
                     that build themselves as you scroll.

                     Three rules it never breaks, because breaking them
                     is what made websites look broken: text that
                     already reads (4.5:1 against what is really behind
                     it -- the ancestors' backgrounds, or on screen the
                     picture or layer lying under it) is left as the
                     site drew it, and text that does not is given a
                     colour that does; an element it has already
                     painted is recognised as its own work and never
                     remapped twice, while an element the site has
                     restyled since -- however late -- is read again
                     from scratch; and no picture is ever recoloured.
                     One run at a time: a live re-theme replaces the
                     last run instead of fighting it.
  3. identity      — the twelve character themes bring their own face:
                     Terminal Green gets phosphor glow, scanlines and a
                     sweeping refresh band; Game Boy pixelates images
                     inside its bezel; Newspaper prints in serif with
                     grayscale photos; Frutiger Aero floats glossy
                     bubbles; and so on. Animations respect
                     prefers-reduced-motion.

On a site this themes, Chromium's ForceDarkMode auto-darkening is held
off (Browser._apply_page_force_dark asks themes_host) — the adaptive
pass replaces it with the actual palette instead of an inversion. Sites
that are dark by design (NATIVE_DARK_SITES), Google (which has its own
light/dark switch) and every host he excluded from the page's
right-click menu are left alone, and auto-darken treats them as before.

The switch is Settings > Appearance > "Theme websites" ("themeWeb").
browser.py calls script()/refresh()/repaint_open_sites()/
undo_open_sites()/enabled()/themes_host()/toggle_host().
"""

import hashlib
import json
import re
import sys

from PyQt6.QtWebEngineCore import QWebEngineScript

SCRIPT_NAME = "site-theme"

# Both stacks end in a family that is certainly installed: "Bitstream
# Charter" and Charter are on neither his desktop nor this server
# (fc-match answers them with Noto Sans, which is not even a serif),
# and DejaVu Sans Mono is gone from Fedora 44 as well. A stack whose
# first names do not exist is not an error — the engine walks on — but
# a stack that can run out is, so the real faces are named too.
MONO = ('"JetBrainsMono Nerd Font", "DejaVu Sans Mono", "Noto Sans Mono",'
        ' "Liberation Mono", monospace')
SERIF = ('"Bitstream Charter", Charter, Georgia, "Liberation Serif",'
         ' "Noto Serif", "DejaVu Serif", "Times New Roman", serif')

# Which elements a theme may put its own face on.
#
# This list used to carry a, button, input, li, td, th, label, select
# and textarea as well, and that is where "icons turn into letters and
# boxes" came from: an icon font is nearly always worn by the clickable
# element itself (<button class="material-icons">delete</button>,
# <a class="fa fa-home"></a>), so forcing a face on a or button takes
# the icon font off and leaves the ligature's letters or a private-use
# box behind. The same swap changes text metrics inside boxes that were
# measured for another face, which is the other half of it: nav bars
# and buttons with fixed heights then overflow.
#
# What is left is running text, which no icon font is ever set on and
# no fixed-height box is ever built from. body carries the face into
# everything that does not ask for one of its own, so a page still
# reads in the theme's font; an element with a font-family of its own
# — every icon, every code block — keeps it.
FONT_SEL = ("body, p, h1, h2, h3, h4, h5, h6, blockquote, dt, dd,"
            " figcaption")

# There is deliberately no second rule here naming icon classes. The
# first thing tried was `font-family: revert !important` on anything
# with icon/symbol/awesome in its class, and it made matters worse:
# revert throws away the *author's* declaration, so the rule written to
# protect icon fonts was itself taking them off. Not matching the
# element in the first place is the only safe answer, and the list
# above does exactly that.

SQUARE = ("*, *::before, *::after { border-radius: 0 !important; }")


def _mod(browser):
    return sys.modules[type(browser).__module__]


def enabled(browser):
    return bool(browser.config.get("themeWeb", True))


def _skipped(browser):
    """Hosts never themed: dark by design, Google, and his own list."""
    mod = _mod(browser)
    own = browser.config.get("themeWebSkip") or []
    return sorted(set(mod.NATIVE_DARK_SITES)
                  | {h for h in own if isinstance(h, str) and h})


def _host(host):
    return (host or "").lower().removeprefix("www.")


def themes_host(browser, host):
    """Would a page on this host be themed right now?"""
    if not enabled(browser):
        return False
    host = _host(host)
    if not host or re.fullmatch(r"google\.[a-z.]+", host):
        return False
    return not any(host == d or host.endswith("." + d)
                   for d in _skipped(browser))


def toggle_host(browser, host):
    """Exclude a host from theming, or let it be themed again. Returns
    whether it is themed afterwards."""
    host = _host(host)
    own = [h for h in (browser.config.get("themeWebSkip") or [])
           if isinstance(h, str) and h]
    if host in own:
        own.remove(host)
    else:
        own.append(host)
    browser.config["themeWebSkip"] = sorted(own)
    browser.save_config()
    refresh(browser)
    return themes_host(browser, host)


# ---------------------------------------------------------------------------
# Layer 1 — base CSS every theme gets
# ---------------------------------------------------------------------------

def _base_css(p, dark):
    """The palette, and nothing that decides what a page looks like.

    Nor any transition. Every site element used to ease between
    colours over .35s (html.__st-live), which read as a soft theme
    switch and was in fact the fault behind most of what the matrix
    found: the pass reads an element's colours back right after it
    writes them, and during a transition the computed style is the
    colour the element is coming FROM. So "what the page looks like
    now that I am done" was recorded as the old colour, every later
    look saw the new one and took it for the site's doing, restored,
    judged a mid-fade grey, wrote again, and the observer saw the
    write -- a loop that kept the Outlook landing page's main thread
    busy for as long as the tab was open and left text black where
    the fade had been grey. The chrome switches theme in one frame;
    so do the sites now.

    What is *not* here any more is as important as what is. Pictures
    carried a brightness filter on every dark theme, which is exactly
    the "washed out, too dark" he sees; headings, links, buttons and
    form fields were painted by selector, without anyone asking what
    was behind them, which is where gold-on-blue headlines and
    "every button lost its colour" came from. Colour that depends on
    what is behind it is the adaptive pass's job now (see SITE_JS):
    it can measure the contrast, and a stylesheet cannot."""
    return f"""
html {{ background-color: {p['bg']} !important; }}
body {{ background-color: {p['bg']} !important; color: {p['text']} !important; }}
/* A placeholder is text too, and the one most often lost: the site
   picked its grey for the site's white field, and on the dark card
   this pass makes of that field it is nothing (the Microsoft sign-in
   page's "Email, phone, or Skype" was black at 60%% on near-black).
   The pass measures it like any other text and, only when it fails,
   hands the field one of these: dim first (the quietest token that
   clears 4.5:1 on every surface of all 116 palettes), the text
   colour, then white or black for a field on a brand colour. */
.__st-ph-dim::placeholder {{ color: {p['dim']} !important; }}
.__st-ph-text::placeholder {{ color: {p['text']} !important; }}
.__st-ph-white::placeholder {{ color: #ffffff !important; }}
.__st-ph-black::placeholder {{ color: #000000 !important; }}
::selection {{ background: {p['accent']} !important; color: {p['bg']} !important; }}
input, textarea {{ caret-color: {p['accent']}; }}
:focus-visible {{ outline: 2px solid {p['accent']} !important; outline-offset: 2px; }}
::-webkit-scrollbar {{ width: 12px; height: 12px; }}
::-webkit-scrollbar-track {{ background: {p['bg']}; }}
::-webkit-scrollbar-thumb {{
  background: {p['sunken']}; border-radius: 6px;
  border: 3px solid {p['bg']};
}}
::-webkit-scrollbar-thumb:hover {{ background: {p['muted']}; }}
"""


# ---------------------------------------------------------------------------
# Layer 3 — identity CSS per character theme
# (fixed inset overlays: ::before carries texture, ::after animation)
# ---------------------------------------------------------------------------

# The texture a theme lays over a page.
#
# z-index 1, not the 2147483645 it was: that number put scanlines,
# grids and vignettes over *everything*, site dialogs and menus
# included, so a modal came up looking dimmed and a dropdown had a
# grid drawn across it. 1 is above the page's own flow and below
# anything the site positions on purpose, which is what a texture
# wants to be. pointer-events: none keeps every click going through.
_OVERLAY = ("content: ''; position: fixed; inset: 0; pointer-events: none;"
            " z-index: 1;")
_MOTION = "@media (prefers-reduced-motion: no-preference)"


def _glow(color):
    return (f"text-shadow: 0 0 2px color-mix(in srgb, {color} 90%, transparent),"
            f" 0 0 9px color-mix(in srgb, {color} 55%, transparent);")


def _terminal(p):
    return f"""
{FONT_SEL} {{ font-family: {MONO} !important; }}
{SQUARE}
h1, h2, h3, a, button {{ {_glow(p['text'])} }}
h1::before, h2::before {{ content: "> "; opacity: .65; }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient(rgba(0,0,0,.30) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at 50% 45%, transparent 62%, rgba(0,10,0,.30) 100%);
}}
{_MOTION} {{
  html::after {{ content: ''; position: fixed; left: 0; right: 0; top: -30%;
    height: 26%; pointer-events: none; z-index: 2;
    background: linear-gradient(color-mix(in srgb, {p['text']} 0%, transparent),
      color-mix(in srgb, {p['text']} 6%, transparent) 50%,
      color-mix(in srgb, {p['text']} 0%, transparent));
    animation: __st_sweep 7s linear infinite; }}
  @keyframes __st_sweep {{ to {{ transform: translateY(520%); }} }}
}}
"""


def _amber(p):
    return f"""
{FONT_SEL} {{ font-family: {MONO} !important; }}
h1, h2, h3, a, button {{ {_glow(p['text'])} }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient(rgba(0,0,0,.28) 0 1px, transparent 1px 3px),
    repeating-linear-gradient(90deg, rgba(255,176,0,.03) 0 1px, transparent 1px 3px),
    radial-gradient(ellipse at 50% 42%, transparent 60%, rgba(10,4,0,.32) 100%);
}}
{_MOTION} {{
  html::before {{ animation: __st_flicker 5s steps(60) infinite; }}
  @keyframes __st_flicker {{
    0%, 93%, 100% {{ opacity: 1; }} 94% {{ opacity: .85; }} 96% {{ opacity: .95; }}
  }}
}}
"""


def _blueprint(p):
    line = f"color-mix(in srgb, {p['text']} 22%, transparent)"
    fine = f"color-mix(in srgb, {p['text']} 9%, transparent)"
    return f"""
h1, h2, h3, h4, h5, h6 {{ font-family: {MONO} !important;
  text-transform: uppercase; letter-spacing: .08em; }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient({line} 0 1px, transparent 1px 112px),
    repeating-linear-gradient(90deg, {line} 0 1px, transparent 1px 112px),
    repeating-linear-gradient({fine} 0 1px, transparent 1px 28px),
    repeating-linear-gradient(90deg, {fine} 0 1px, transparent 1px 28px),
    radial-gradient(ellipse at 50% 40%, transparent 60%,
      color-mix(in srgb, {p['accent']} 10%, transparent) 100%);
}}
"""


def _synthwave(p):
    pink = p['accent']
    return f"""
h1, h2, h3 {{ text-shadow: 0 0 2px color-mix(in srgb, {pink} 95%, transparent),
  0 0 15px color-mix(in srgb, {pink} 70%, transparent),
  0 0 34px color-mix(in srgb, {p['green']} 40%, transparent); }}
button, input, select, textarea {{
  box-shadow: 0 0 0 1px color-mix(in srgb, {pink} 35%, transparent),
    0 0 12px color-mix(in srgb, {pink} 22%, transparent) !important; }}
button:hover {{
  box-shadow: 0 0 0 1px color-mix(in srgb, {pink} 80%, transparent),
    0 0 20px color-mix(in srgb, {pink} 50%, transparent) !important; }}
html::before {{ {_OVERLAY}
  background-image:
    radial-gradient(1px 1px at 21% 12%, rgba(255,255,255,.8) 0 1px, transparent 2px),
    radial-gradient(1px 1px at 63% 7%, rgba(255,255,255,.6) 0 1px, transparent 2px),
    radial-gradient(1px 1px at 84% 19%, rgba(255,255,255,.7) 0 1px, transparent 2px),
    radial-gradient(1px 1px at 39% 23%, rgba(255,255,255,.5) 0 1px, transparent 2px);
}}
html::after {{ content: ''; position: fixed; left: 0; right: 0; bottom: 0;
  top: auto; height: 32%; pointer-events: none; z-index: 2;
  background:
    repeating-linear-gradient(color-mix(in srgb, {pink} 22%, transparent) 0 1px,
      transparent 1px 34px),
    repeating-linear-gradient(90deg, color-mix(in srgb, {pink} 16%, transparent) 0 2px,
      transparent 2px 90px),
    linear-gradient(to top, color-mix(in srgb, {pink} 10%, transparent), transparent);
  -webkit-mask-image: linear-gradient(to top, #000 55%, transparent);
}}
{_MOTION} {{
  html::after {{ animation: __st_gridpulse 4s ease-in-out infinite alternate; }}
  @keyframes __st_gridpulse {{ from {{ opacity: .7; }} to {{ opacity: 1; }} }}
}}
"""


def _gameboy(p):
    ink = "rgba(11,40,11,.16)"
    return f"""
{FONT_SEL} {{ font-family: {MONO} !important; }}
{SQUARE}
img, video {{ image-rendering: pixelated; }}
h1, h2, h3 {{ text-transform: uppercase; letter-spacing: .12em;
  text-shadow: 2px 2px 0 color-mix(in srgb, {p['text']} 45%, transparent); }}
button, input, select, textarea {{ border-width: 2px !important;
  box-shadow: 3px 3px 0 rgba(11,40,11,.85) !important; }}
button:hover {{ box-shadow: 2px 2px 0 rgba(11,40,11,.85) !important; }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient({ink} 0 1px, transparent 1px 3px),
    repeating-linear-gradient(90deg, {ink} 0 1px, transparent 1px 3px);
}}
html::after {{ {_OVERLAY} z-index: 2;
  box-shadow: inset 0 0 0 10px {p['accent']}, inset 0 0 0 14px {p['surface']};
}}
"""


def _c64(p):
    return f"""
{FONT_SEL} {{ font-family: {MONO} !important; }}
{SQUARE}
h1, h2 {{ text-transform: uppercase; letter-spacing: .16em; }}
h1::after {{ content: "\\2588"; margin-left: .25em; }}
html::before {{ {_OVERLAY}
  background: repeating-linear-gradient(rgba(0,0,0,.20) 0 1px, transparent 1px 4px);
}}
html::after {{ {_OVERLAY} z-index: 2;
  box-shadow: inset 0 0 0 12px {p['accent']};
}}
{_MOTION} {{
  h1::after {{ animation: __st_blink 1s steps(1) infinite; }}
  @keyframes __st_blink {{ 50% {{ opacity: 0; }} }}
}}
"""


def _sepia(p):
    return f"""
{FONT_SEL} {{ font-family: {SERIF} !important; }}
/* the one picture effect this theme is named after, kept mild */
img, video {{ filter: sepia(.18); }}
h1, h2, h3 {{ text-shadow: 0 1px 0 rgba(255,250,235,.55); }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient(78deg, rgba(120,92,48,.05) 0 1px, transparent 1px 4px),
    repeating-linear-gradient(166deg, rgba(120,92,48,.04) 0 1px, transparent 1px 4px),
    radial-gradient(70px 55px at 18% 24%, rgba(150,105,55,.16), transparent 70%),
    radial-gradient(90px 60px at 82% 70%, rgba(150,105,55,.12), transparent 70%),
    radial-gradient(ellipse at 50% 40%, transparent 60%, rgba(74,63,48,.14) 100%);
}}
"""


def _newspaper(p):
    ink = "rgba(26,26,26"
    return f"""
{FONT_SEL} {{ font-family: {SERIF} !important; }}
/* newsprint: the one effect this theme is named after */
img, video {{ filter: grayscale(.9); }}
h1 {{ text-transform: uppercase; letter-spacing: .04em;
  border-top: 3px double {ink},.8); border-bottom: 3px double {ink},.8); }}
h2 {{ border-bottom: 1px solid {ink},.6); }}
html::before {{ {_OVERLAY}
  background-image:
    repeating-radial-gradient(circle at 0 0, {ink},.05) 0 1px, transparent 1.5px 5px),
    repeating-linear-gradient(90deg, transparent 0 178px, {ink},.10) 178px 180px);
  background-size: 5px 5px, auto;
}}
"""


def _aero(p):
    white = "rgba(255,255,255"
    return f"""
button, input, select, textarea, img {{ border-radius: 12px !important; }}
button {{
  background-image: linear-gradient({white},.35), {white},.05) 46%, transparent 47%) !important;
  box-shadow: inset 0 1px 0 {white},.45), 0 4px 12px rgba(6,39,68,.35) !important; }}
html::before {{ {_OVERLAY}
  background:
    linear-gradient(color-mix(in srgb, {p['accentLt']} 10%, transparent), transparent 38%),
    radial-gradient(circle 34px at 24% 64%, transparent 60%, {white},.25) 78%, transparent 82%),
    radial-gradient(circle 20px at 78% 30%, transparent 58%, {white},.22) 78%, transparent 84%),
    radial-gradient(circle 50px at 88% 82%, transparent 62%, {white},.16) 80%, transparent 84%);
}}
{_MOTION} {{
  html::before {{ animation: __st_float 16s ease-in-out infinite alternate; }}
  @keyframes __st_float {{ from {{ transform: translateY(10px); }}
    to {{ transform: translateY(-10px); }} }}
}}
"""


def _wood(p):
    return f"""
h1, h2, h3 {{ font-family: {SERIF} !important;
  border-bottom: 2px solid color-mix(in srgb, {p['accent']} 40%, transparent); }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient(90deg, rgba(0,0,0,.18) 0 2px, transparent 2px 4px,
      rgba(243,230,208,.04) 4px 5px, transparent 5px 220px),
    repeating-linear-gradient(90deg, rgba(0,0,0,.08) 0 1px, transparent 1px 7px),
    linear-gradient(color-mix(in srgb, {p['yellow']} 6%, transparent), transparent 30%),
    radial-gradient(ellipse at 50% 40%, transparent 62%, rgba(0,0,0,.18) 100%);
}}
"""


def _steampunk(p):
    return f"""
{FONT_SEL} {{ font-family: {SERIF} !important; }}
h1, h2, h3 {{ text-shadow: 0 1px 0 rgba(0,0,0,.6);
  border-bottom: 2px solid color-mix(in srgb, {p['accent']} 45%, transparent); }}
html::before {{ {_OVERLAY}
  background-image:
    repeating-linear-gradient(115deg, color-mix(in srgb, {p['accent']} 5%, transparent) 0 1px,
      transparent 1px 7px),
    radial-gradient(circle at 15px 15px, color-mix(in srgb, {p['text']} 16%, transparent) 0 2px,
      rgba(120,78,30,.14) 2px 3.2px, transparent 3.6px),
    radial-gradient(ellipse at 0% 0%, color-mix(in srgb, {p['peach']} 9%, transparent), transparent 45%),
    radial-gradient(ellipse at 100% 100%, color-mix(in srgb, {p['accent']} 8%, transparent), transparent 45%),
    radial-gradient(ellipse at 50% 42%, transparent 62%, rgba(0,0,0,.22) 100%);
  background-size: auto, 44px 44px, auto, auto, auto;
}}
{_MOTION} {{
  html::before {{ animation: __st_gaslight 8s ease-in-out infinite; }}
  @keyframes __st_gaslight {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .88; }} }}
}}
"""


IDENTITY = {
    "terminal": _terminal,
    "amber": _amber,
    "blueprint": _blueprint,
    "synthwave": _synthwave,
    "gameboy": _gameboy,
    "c64": _c64,
    "sepia": _sepia,
    "newspaper": _newspaper,
    "aero": _aero,
    "wood": _wood,
    "steampunk": _steampunk,
}


def _site_css(browser):
    mod = _mod(browser)
    p = mod.theme_palette()
    entry = mod.theme_def()
    dark = bool(entry.get("dark"))
    css = _base_css(p, dark)
    identity = IDENTITY.get(entry.get("key"))
    if identity:
        css += identity(p)
    return css


# ---------------------------------------------------------------------------
# Layer 2 — the injected script: style element + adaptive recolour pass
# ---------------------------------------------------------------------------

SITE_JS = """(function () {
  if (location.protocol === "file:") return;
  var CSS = %(css)s;
  var TOK = %(tokens)s;
  var SKIP = %(skip)s;
  var GEN = %(gen)s;          // changes with the theme: see stale()
  var host = location.hostname.toLowerCase().replace(/^www\\./, "");
  if (/^google\\.[a-z.]+$/.test(host)) return;
  // One run at a time. A live re-theme runs this whole script again
  // in a page the last run is still watching, and the last run's
  // MutationObserver, its queue and its timers all survived in their
  // own closure with the OLD palette and the OLD generation. Every
  // write of the new run looked stale to the old one and vice versa,
  // and the two repainted each other's work for as long as the page
  // was open: a card in the last theme's surface with this theme's
  // text on it (the Microsoft sign-in page, Latte after Mocha), and a
  // main thread that never came back on a page that mutates a lot
  // (the Outlook landing page). So the run that starts switches the
  // old observer off and every leftover slice of the old run asks
  // whether it is still the current run before it touches anything.
  var RUN = (window.__stRun = (window.__stRun || 0) + 1);
  window.__stGen = GEN;
  if (window.__stStats) window.__stStats.why = [];   // this run's reasons, not the last's
  function current() { return window.__stRun === RUN; }
  if (window.__stObs) { window.__stObs.disconnect(); window.__stObs = null; }
  for (var k = 0; k < SKIP.length; k++)
    if (host === SKIP[k] || host.slice(-SKIP[k].length - 1) === "." + SKIP[k]) {
      // excluded while open (another tab's right-click, a live re-theme):
      // take off what an earlier run of this put here
      if (window.__stUndo) window.__stUndo();
      return;
    }

  function paint() {
    var root = document.documentElement;
    if (!root) return false;
    var el = document.getElementById("__sitetheme");
    if (!el) {
      el = document.createElement("style");
      el.id = "__sitetheme";
      root.appendChild(el);
    }
    el.textContent = CSS;
    // a Content-Security-Policy without 'unsafe-inline' (gov.uk) drops
    // the <style>, and the adaptive pass alone writes light text onto
    // the page's white: carry the sheet as a constructed one instead
    if (!el.sheet && window.CSSStyleSheet && "adoptedStyleSheets" in document) {
      try {
        var sh = window.__stSheet || (window.__stSheet = new CSSStyleSheet());
        sh.replaceSync(CSS);
        if (document.adoptedStyleSheets.indexOf(sh) < 0)
          document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sh]);
      } catch (e) {}
    }
    return true;
  }

  // ---- colour arithmetic ------------------------------------------
  // Everything below decides by measured contrast rather than by
  // "dark-ish/light-ish", because that is the whole difference between
  // a page that reads and the light-grey-on-white he was getting.

  function parseColor(s) {
    s = s || "";
    var m = /rgba?\\(([\\d.]+)[, ]+([\\d.]+)[, ]+([\\d.]+)(?:[,/ ]+([\\d.]+%%?))?\\)/.exec(s);
    if (m) {
      var a = m[4] === undefined ? 1
        : (m[4].indexOf("%%") >= 0 ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
      return { r: +m[1], g: +m[2], b: +m[3], a: isNaN(a) ? 1 : a };
    }
    m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s.trim());
    if (!m) return null;
    var h = m[1];
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16),
             b: parseInt(h.slice(4, 6), 16), a: 1 };
  }
  function lum(c) { return .2126 * c.r + .7152 * c.g + .0722 * c.b; }
  function chan(v) {
    v = v / 255;
    return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4);
  }
  function relLum(c) {
    return .2126 * chan(c.r) + .7152 * chan(c.g) + .0722 * chan(c.b);
  }
  // WCAG, the number the brief asks for: 4.5 is "readable"
  function contrast(fg, bg) {
    var a = relLum(fg) + .05, b = relLum(bg) + .05;
    return a > b ? a / b : b / a;
  }
  function blend(top, under) {       // top, with its alpha, over under
    var a = top.a;
    return { r: top.r * a + under.r * (1 - a),
             g: top.g * a + under.g * (1 - a),
             b: top.b * a + under.b * (1 - a), a: 1 };
  }
  function rgb(c) {
    return "rgb(" + Math.round(c.r) + ", " + Math.round(c.g) + ", "
      + Math.round(c.b) + ")";
  }
  function isPhoto(bgi) {
    return !!bgi && bgi !== "none" && bgi.indexOf("url(") >= 0;
  }

  var TOKC = {};                     // the palette, parsed once
  ["bg", "surface", "surfaceAlt", "hover", "sunken", "text",
   "accent", "accentLt", "dim"].forEach(function (k) {
    TOKC[k] = parseColor(TOK[k]) || { r: 128, g: 128, b: 128, a: 1 };
  });
  var PAGE = TOKC.bg;                // what html is painted with

  // What is really behind this element: the first opaque background
  // walking up, with any translucent ones blended over it. Returns
  // null when a picture or a gradient is in the way -- text over a
  // photo cannot be judged by colour, so the pass leaves it alone.
  // bgcache is emptied at the start of every flush: within one flush
  // the page does not move, between them it may.
  var bgcache = new Map();
  function behind(el) {
    // hit stays undefined while nothing has answered yet; null is a
    // real answer and means "a picture is behind this"
    var chain = [], node = el, hit, guard = 0;
    while (node && node.nodeType === 1 && guard++ < 60) {
      var soon = planned.get(node);
      if (soon) { hit = soon; break; }
      var known = bgcache.get(node);
      if (known !== undefined) { hit = known; break; }
      // An ancestor that was just restored and is fading back to the
      // site's colour (see later): what it looks like now is neither
      // ours nor the site's, so nothing on it can be judged yet. The
      // Outlook calendar's month panel fades over .2s; the dates in it
      // were judged against the dark it was leaving and painted white
      // for a panel that ended up light, and since the panel itself
      // needed no repaint, nothing ever came back to them.
      var rec = orig.get(node);
      if (rec && rec.pending) {
        for (var w = 0; w < chain.length; w++) bgcache.set(chain[w][0], "pending");
        bgcache.set(node, "pending");
        return "pending";
      }
      var cs = computed(node);
      if (!cs) break;
      var bgi = cs.backgroundImage;
      if (isPhoto(bgi) || (bgi && bgi.indexOf("gradient") >= 0)) {
        hit = null;
        for (var q = 0; q < chain.length; q++) bgcache.set(chain[q][0], null);
        bgcache.set(node, null);
        return null;
      }
      var c = parseColor(cs.backgroundColor);
      if (c && c.a > .004) {
        if (c.a > .995) { hit = c; break; }
        chain.push([node, c]);
      } else {
        chain.push([node, null]);
      }
      node = node.parentElement;
    }
    if (hit === "pending") {
      for (var y = 0; y < chain.length; y++) bgcache.set(chain[y][0], "pending");
      return "pending";
    }
    if (hit === null) {
      // a cached null is "there is a picture behind this", and that
      // answer travels down to the children: they are left alone too
      for (var z = 0; z < chain.length; z++) bgcache.set(chain[z][0], null);
      return null;
    }
    if (hit === undefined) hit = PAGE;   // off the top of the page: html
    for (var i = chain.length - 1; i >= 0; i--) {
      if (chain[i][1]) hit = blend(chain[i][1], hit);
      bgcache.set(chain[i][0], hit);
    }
    return hit;
  }

  // The ancestors are not always what is behind the text. A hero
  // section draws its photo as an <img> or a <picture> positioned
  // under the words, not as a background of their parent, so the
  // walk up finds nothing and answers "the page" -- and the pass then
  // paints a headline that sat readably on a light photo in the
  // theme's light text, which on that photo is nothing at all (the
  // Outlook landing page). So for an element on screen the stack of
  // elements under one point of its text is asked as well: a picture
  // in it beneath the element means "a picture is behind this"; an
  // opaque element beneath it that is not an ancestor is the real
  // backdrop and its colour is the answer. Off screen the stack
  // cannot be asked (elementsFromPoint only knows the viewport), and
  // the ancestors have to do. Cached per flush, like bgcache.
  var undercache = new Map();
  function underneath(el) {
    if (undercache.has(el)) return undercache.get(el);
    var out = undefined;              // undefined: nothing to add
    var r;
    try { r = el.getBoundingClientRect(); } catch (e) { r = null; }
    if (r && r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0
        && r.top < window.innerHeight && r.left < window.innerWidth
        && document.elementsFromPoint) {
      var x = Math.min(Math.max(r.left + Math.min(r.width / 2, 12), 0),
                       window.innerWidth - 1);
      var y = Math.min(Math.max(r.top + Math.min(r.height / 2, 10), 0),
                       window.innerHeight - 1);
      var stack;
      try { stack = document.elementsFromPoint(x, y); } catch (e) { stack = null; }
      if (stack) {
        var below = false;
        for (var i = 0; i < stack.length; i++) {
          var e = stack[i];
          if (e === el) { below = true; continue; }
          if (!below) continue;                 // above the text: an overlay
          if (e.contains(el)) {
            // an ancestor: the walk up sees its own background, and
            // stops at the first opaque one as this does
            var acs = computed(e);
            if (!acs) break;
            var abgi = acs.backgroundImage;
            if (isPhoto(abgi) || (abgi && abgi.indexOf("gradient") >= 0)) { out = null; break; }
            var ac = parseColor(acs.backgroundColor);
            if (ac && ac.a > .995) break;
            continue;
          }
          if (PICTURE[e.tagName] === 1) { out = null; break; }
          var soon = planned.get(e);
          if (soon) { out = soon; break; }
          var srec = orig.get(e);
          if (srec && srec.pending) { out = "pending"; break; }
          var cs = computed(e);
          if (!cs) continue;
          var bgi = cs.backgroundImage;
          if (isPhoto(bgi) || (bgi && bgi.indexOf("gradient") >= 0)) { out = null; break; }
          var c = parseColor(cs.backgroundColor);
          if (c && c.a > .995) { out = c; break; }
        }
      }
    }
    undercache.set(el, out);
    return out;
  }
  // what the text of an element really sits on: the ancestors' answer,
  // corrected by what lies underneath on screen
  function ground(el) {
    var under = underneath(el);
    if (under !== undefined) return under;    // a sibling layer decided
    return behind(el);
  }

  var csCache = new Map();
  function computed(el) {
    var c = csCache.get(el);
    if (c !== undefined) return c;
    try { c = getComputedStyle(el); } catch (e) { c = null; }
    csCache.set(el, c);
    return c;
  }

  // ---- what this pass has done to an element ----------------------
  var orig = window.__stOrig = window.__stOrig || new WeakMap();
  var SEL = "div,section,article,main,aside,header,footer,nav,ul,ol,table," +
    "tr,td,th,form,p,li,blockquote,pre,code,button,input,textarea,select," +
    "label,h1,h2,h3,h4,h5,h6,a,dl,dt,dd,figure,figcaption,summary,details," +
    // inline text: dark text in a span inside a white card stays dark
    // after the card turns dark unless the span is looked at as well
    "span,strong,b,em,i,small,font,mark,cite,time,abbr,sup,sub,u,s,q,kbd";

  // custom elements (<a-color-scheme>, web components) carry their own
  // backgrounds too: a light text inside one left white is unreadable
  var TAGS = {};
  SEL.toUpperCase().split(",").forEach(function (t) { TAGS[t] = 1; });
  function wanted(el) {
    var t = el.tagName;
    return TAGS[t] === 1 || t.indexOf("-") > 0;
  }

  var PROPS = ["background-color", "background-image", "color",
               "border-color"];
  var FIELD = { INPUT: 1, TEXTAREA: 1, SELECT: 1, BUTTON: 1 };

  // Only an element that shows text of its own needs a colour. A
  // wrapper gets none: its children inherit the site's colour and are
  // measured on their own backgrounds, which is the right answer and
  // thousands of writes fewer on a page like YouTube.
  function showsText(el) {
    if (FIELD[el.tagName] === 1) return true;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && /\\S/.test(n.nodeValue)) return true;
    }
    return false;
  }

  // An element that is a frame around one picture keeps the background
  // the picture was drawn for: a logo made for white paper on a dark
  // card is a black smudge, and a screenshot with a white matte grows
  // a white border out of nowhere.
  var PICTURE = { IMG: 1, PICTURE: 1, CANVAS: 1, VIDEO: 1, svg: 1, SVG: 1 };
  function framesPicture(el) {
    var kids = el.children, i, holds = false;
    for (i = 0; i < kids.length; i++)
      if (PICTURE[kids[i].tagName] === 1) { holds = true; break; }
    if (!holds) return false;        // the cheap answer, and nearly always
    var r;
    try { r = el.getBoundingClientRect(); } catch (e) { return false; }
    var area = r.width * r.height;
    if (!area || area > 120000) return false;      // a card, not a chip
    var pic = 0;
    for (i = 0; i < kids.length; i++)
      if (PICTURE[kids[i].tagName] === 1) {
        var kr = kids[i].getBoundingClientRect();
        pic += kr.width * kr.height;
      }
    return pic > area * .55;
  }

  // What of an element's colours this pass cares about: its fill;
  // its text colour only if it shows text (a card's colour is
  // inherited by its children and means nothing to the card -- and
  // it changes whenever an ancestor is painted, which made every
  // card on the Outlook landing page look "moved" at every look and
  // get restored and repainted, for as long as the page was open);
  // its border colour only if it has a border.
  function look(cs, saved) {
    return cs.backgroundColor
      + "|" + (saved.text ? cs.color : "")
      + "|" + (saved.bw && saved.bw !== "0px" ? cs.borderTopColor : "");
  }

  // What the element will look like once this pass's writes have
  // landed: the written values where they can be said in the
  // engine's own words, the read-back for the rest. A site's own
  // transition on the element (a card that fades on hover) makes the
  // read-back right after a write the colour the fade STARTS from,
  // and a record of that is a record of a lie: the next look would
  // find the finished colour, call it the site's doing and start
  // over. A translucent fill (a color-mix) cannot be predicted and is
  // read back as before; it is rare, and the retry below covers it.
  function expected(plan, done) {
    var saved = plan.saved;
    var bg = done.backgroundColor, col = done.color, bd = done.borderTopColor;
    for (var i = 0; i < plan.work.length; i++) {
      var prop = plan.work[i][0], c = parseColor(plan.work[i][1]);
      if (!c) continue;
      if (prop === "background-color") bg = rgb(c);
      else if (prop === "color") col = rgb(c);
      else if (prop === "border-color") bd = rgb(c);
    }
    return bg + "|" + (saved.text ? col : "")
      + "|" + (saved.bw && saved.bw !== "0px" ? bd : "");
  }

  // Is this element mid-way through a transition of its colours? Then
  // what it looks like now says nothing about what the site wants it
  // to look like, and the decision has to wait for the fade to end.
  function fading(cs) {
    var d = cs.transitionDuration;
    if (!d || /^(0s(, )?)+$/.test(d)) return false;
    var props = cs.transitionProperty || "all";
    return /\\ball\\b|color|background|border/.test(props);
  }
  // how long the longest of its transitions takes, in ms
  function fadeMs(cs) {
    var most = 0, parts = (cs.transitionDuration || "").split(",");
    for (var i = 0; i < parts.length; i++) {
      var m = /([\\d.]+)(m?s)/.exec(parts[i]);
      if (m) most = Math.max(most, parseFloat(m[1]) * (m[2] === "ms" ? 1 : 1000));
    }
    return Math.min(most, 3000);
  }

  function snapshot(el, cs) {
    var saved = { bg: cs.backgroundColor, color: cs.color,
                  bgi: cs.backgroundImage,
                  border: cs.borderTopColor, bw: cs.borderTopWidth,
                  inl: {}, set: false, gen: GEN,
                  seen: null, after: null,
                  // whether it had words when it was looked at: an
                  // element that gets them later has to be looked at
                  // again, and nothing in its colours will say so
                  text: showsText(el) };
    saved.seen = look(cs, saved);
    for (var i = 0, p; i < PROPS.length; i++) {
      p = PROPS[i];
      saved.inl[p] = [el.style.getPropertyValue(p),
                      el.style.getPropertyPriority(p)];
    }
    orig.set(el, saved);
    return saved;
  }

  // a re-theme (dark to light) must not keep what the last theme set
  function restore(el, saved) {
    if (!saved.set) return;
    if (saved.cls) { el.classList.remove(saved.cls); saved.cls = null; }
    for (var i = 0, p, o; i < PROPS.length; i++) {
      p = PROPS[i]; o = saved.inl[p];
      if (o[0]) el.style.setProperty(p, o[0], o[1]);
      else el.style.removeProperty(p);
    }
    saved.set = false;
    saved.put = {};
    saved.after = null;
  }

  function put(el, saved, prop, value) {
    saved.set = true;
    el.style.setProperty(prop, value, "important");
    (saved.put = saved.put || {})[prop] = el.style.getPropertyValue(prop);
  }

  // a page that rewrites an element's style attribute (OneTrust's
  // banner sets style="bottom: 0px") wipes the override but not the
  // text colour put on its children: dark text on the dark banner
  function reput(el) {
    var saved = orig.get(el);
    if (!saved || !saved.set || !saved.put) return;
    // a script that writes the style attribute back on every frame
    // would be answered on every frame: after a few rounds the
    // element is the site's
    if ((saved.reputs || 0) >= 5) return;
    for (var p in saved.put)
      if (el.style.getPropertyValue(p) !== saved.put[p]
          || el.style.getPropertyPriority(p) !== "important") {
        saved.reputs = (saved.reputs || 0) + 1;
        stats.reputs++;
        el.style.setProperty(p, saved.put[p], "important");
      }
  }

  // Has the page moved under us since we wrote?
  //
  // This is what stops the two oldest faults at once. A snapshot taken
  // before the site's own stylesheet arrived (an async sheet, a
  // single-page app re-rendering, a class that lands on scroll) used to
  // be kept forever, so the element stayed dark-on-dark and a second
  // pass over it did nothing at all -- remember() returned the stale
  // record and left. And a snapshot thrown away every time would mean
  // re-reading our own colour as if it were the site's and remapping
  // the remap. So: ours and still in place -> leave it; ours wiped by
  // the page -> read the site's colours again and decide again.
  //
  // It asks the style attribute, not the computed style, on purpose:
  // reading a computed value after a write forces a style recalc, and
  // one per painted element is most of a second on a big page.
  // "after" is what the page looked like once this pass was done with
  // the element, recorded in the third phase of a slice (see slice),
  // where the read costs one style recalculation for a whole chunk
  // rather than one per element. Anything different from it since is
  // the site's doing -- a stylesheet that arrived late, a class that
  // landed on scroll, a single-page app re-rendering the row -- and
  // then the element is read again from scratch. Anything the same is
  // this pass's own work and is left alone, which is what stops a
  // remap being remapped.
  function stale(el, saved, cs) {
    if (saved.gen !== GEN) return 1;
    // Words that arrived after the look. The Microsoft sign-in page
    // builds its "Sign in" heading empty and fills it in from a
    // script; the element's colours never change, so the record said
    // "nothing has moved" and the heading stayed in the site's dark
    // ink on the card this pass had just made dark.
    if (!saved.text && showsText(el)) { note(el, "text"); return 1; }
    var was = saved.set ? saved.after : saved.seen;
    if (!was) return 0;                     // painted, not yet recorded
    if (look(cs, saved) !== was) {
      if (fading(cs) && (saved.waits || 0) < 3) return 2;
      note(el, "look " + was + " -> " + look(cs, saved));
      return 1;
    }
    saved.waits = 0;                        // settled: the next fade starts afresh
    // ...and the other half of it: whether this element's text is
    // readable depends on what is *behind* it, which is another
    // element's business. A card that turns dark one pass after the
    // span inside it was judged against white leaves that span dark on
    // dark -- the span itself never changed, so nothing above would
    // have noticed. Amazon's product titles and Stack Overflow's menus
    // were exactly this.
    if (saved.under) {
      var now = saved.sib ? ground(el) : behind(el);
      if (now === "pending") return (saved.waits || 0) < 4 ? 2 : 1;
      if ((now ? rgb(now) : "img") !== saved.under) {
        note(el, "under " + saved.under + " -> " + (now ? rgb(now) : "img"));
        return 1;
      }
    }
    return 0;
  }
  // the first few reasons an element was looked at again, for the
  // diagnosis of a page that never settles
  function note(el, why) {
    var list = stats.why || (stats.why = []);
    var saved = orig.get(el);
    if (!saved || !saved.set) return;      // a re-snapshot costs nothing
    if (list.length < 24)
      list.push(el.tagName + "." + String(el.className || "").slice(0, 24) + ": " + why);
  }

  // come back to an element once its fade is over
  function later(el, saved, ms) {
    saved.waits = (saved.waits || 0) + 1;
    saved.pending = true;
    stats.waits++;
    setTimeout(function () {
      if (!current()) return;
      push(el);
      schedule();
    }, ms || 450);
  }

  // ---- the decision for one element -------------------------------
  //
  // Split in two halves on purpose. measure() only reads, plan() only
  // writes: a write between two reads makes the engine recalculate the
  // whole page's style before the next read can be answered, and with
  // a few thousand elements that is the difference between a pass that
  // is over before the page is painted and one he can watch happen.
  // What a measured element is *going* to be painted lives in planned,
  // so a child measured in the same slice already sees the dark card
  // its parent is about to become.
  var planned = new Map();
  var deferred = [];                 // restored this chunk, read again after

  function measure(el) {
    if (!el.isConnected) return null;      // taken out of the page: nothing to read
    var cs = computed(el);
    if (!cs) return null;
    var saved = orig.get(el);
    if (saved) saved.pending = false;
    if (saved) {
      var ts = clock();
      var moved = stale(el, saved, cs);
      stats.tStale += clock() - ts;
      if (moved === 0) return null;                    // nothing has moved
      if (moved === 2) { later(el, saved, fadeMs(cs) + 120); return null; }   // mid-fade: wait
      // An element this pass has restored and repainted again and
      // again is one it cannot agree with the site about -- a script
      // writing the colour back on every frame, a transition that
      // never settles. After a few rounds it is left as it is, which
      // is the worst case for that one element and keeps the page's
      // main thread free for everything else.
      // ...but a new theme is not a disagreement: every element is
      // "moved" by it, and a tab in which the theme was switched six
      // times must not stop following.
      if (saved.gen !== GEN) saved.flips = 0;
      else {
        if ((saved.flips || 0) >= 6) return null;
        saved.flips = (saved.flips || 0) + 1;
        stats.flips++;
      }
    }
    if (saved && saved.set) {
      // The site moved (or the theme did): start again from the
      // site's colours. The restore is a write, and reading this
      // element's computed style straight after it makes the engine
      // recalculate the whole page's style -- once per restored
      // element, which on a live re-theme of a 16000-element page was
      // a minute of main thread. So the restore is done now and the
      // reading is left to the slice, which comes back to every
      // restored element of the chunk after one recalculation.
      restore(el, saved);
      if (fading(cs)) {
        // the restore starts a fade back to the site's colours, and
        // what is read before it ends is neither ours nor the site's:
        // come back when it is over
        later(el, saved, fadeMs(cs) + 120);
        return null;
      }
      deferred.push(el);
      return null;
    }
    var flips = saved ? saved.flips : 0;
    var td = clock();
    saved = snapshot(el, cs);
    saved.flips = flips;
    var work = [];

    var bg = parseColor(saved.bg);
    var bgL = bg && bg.a > .35 ? lum(bg) : null;
    var changedBg = null;
    // How far from grey the fill is. A card, a panel, a table stripe
    // and a form field are all some shade of white or near-black, and
    // those are the ones worth repainting in the palette. A colour
    // with real chroma in it is the site saying something -- Amazon's
    // orange button, a red error strip, a brand header -- and
    // repainting that is "the coloured buttons lost their colour".
    // It keeps its colour; only the text on it is checked for being
    // readable, which happens below.
    var chroma = bg ? Math.max(bg.r, bg.g, bg.b) - Math.min(bg.r, bg.g, bg.b)
                    : 0;
    if (bgL !== null && chroma <= 45 && !framesPicture(el)) {
      var want = null;
      if (TOK.dark && bgL > 110)
        want = bgL > 235 ? "surface" : (bgL > 195 ? "surfaceAlt" : "hover");
      else if (!TOK.dark && bgL < 90)
        want = bgL < 40 ? "surface" : "hover";
      if (want) {
        // a translucent fill is a scrim or a tint: it keeps its alpha,
        // or a modal's rgba(0,0,0,.5) backdrop turns into an opaque
        // sheet that hides the whole page on a light theme
        work.push(["background-color", bg.a > .98 ? TOK[want]
          : "color-mix(in srgb, " + TOK[want] + " "
            + Math.round(bg.a * 100) + "%%, transparent)"]);
        var beneath = behind(el.parentElement);
        changedBg = bg.a > .98 ? TOKC[want]
          : blend({ r: TOKC[want].r, g: TOKC[want].g, b: TOKC[want].b,
                    a: bg.a }, (beneath && beneath !== "pending") ? beneath : PAGE);
        planned.set(el, changedBg);
        if (saved.bgi && saved.bgi.indexOf("gradient") >= 0)
          work.push(["background-image", "none"]);
      }
    }

    if (showsText(el)) {
      // what the text now sits on: our own fill if we just made one,
      // otherwise whatever the page has behind it. A null answer means
      // a photo or a gradient is behind it, and then the site's own
      // colour is the only one that can be trusted -- it is left alone.
      // the stack under the text is asked once, when the element is
      // decided: a hit test costs a millisecond or more on a big
      // page, and a full look at that page pays it for every element
      // on screen if the staleness check asks it too. So the record
      // says whether the stack decided, and only those few elements
      // are asked again (see stale)
      var sib = changedBg ? undefined : underneath(el);
      var under = changedBg || (sib !== undefined ? sib : behind(el));
      saved.sib = !changedBg && sib !== undefined;
      if (under === "pending") {
        // judged later, once what it sits on has settled
        saved.under = "pending";
        later(el, saved, 500);
        stats.tDecide += clock() - td;
        return work.length ? { el: el, saved: saved, work: work } : null;
      }
      var col = parseColor(saved.color);
      // what the decision below was made against, so a later pass can
      // tell that the ground has moved (see stale)
      saved.under = under ? rgb(under) : "img";
      if (under && col) {
        if (col.a < .995) col = blend(col, under);
        var link = el.tagName === "A";
        var head = /^H[1-6]$/.test(el.tagName);
        var tries = [];
        // What already reads is kept, links and headings included.
        // They used to be painted in the accent whatever their own
        // colour measured, and a wrong guess about the background --
        // a photo the walk up could not see -- then cost a headline
        // that was fine as the site drew it. The theme still reaches
        // them: a dark link on a card that has just turned dark no
        // longer reads, and that is when it gets the accent.
        if (contrast(col, under) >= 4.5) tries = null;         // readable: keep
        else if (link) tries.push(TOKC.accentLt, TOKC.text);
        else if (head) tries.push(TOKC.accent, TOKC.text);
        else tries.push(TOKC.text);
        if (tries) {
          // last resorts, in case the palette itself cannot carry this
          // background -- a brand-coloured panel, a near-black card
          tries.push({ r: 255, g: 255, b: 255, a: 1 },
                     { r: 0, g: 0, b: 0, a: 1 });
          var pick = null, had = contrast(col, under), best = had, bestCol = null;
          for (var i = 0; i < tries.length; i++) {
            var c = contrast(tries[i], under);
            if (c >= 4.5) { pick = tries[i]; break; }
            if (c > best) { best = c; bestCol = tries[i]; }
          }
          if (!pick && bestCol && had < 4.5) pick = bestCol;
          if (pick) work.push(["color", rgb(pick)]);
        }
      }
    }

    // the placeholder of an empty field, against the same ground
    if ((el.tagName === "INPUT" || el.tagName === "TEXTAREA") && el.placeholder
        && !el.value) {
      var ph = changedBg || ground(el);
      if (ph === "pending") ph = null;
      var pcs = null;
      try { pcs = getComputedStyle(el, "::placeholder"); } catch (e) {}
      var pc = pcs ? (parseColor(pcs.webkitTextFillColor) || parseColor(pcs.color)) : null;
      if (ph && pc) {
        if (pc.a < .995) pc = blend(pc, ph);
        var pop = parseFloat(pcs.opacity);
        if (pop < 1) pc = blend({ r: pc.r, g: pc.g, b: pc.b, a: pop }, ph);
        if (contrast(pc, ph) < 4.5) {
          var opts = [["__st-ph-dim", TOKC.dim], ["__st-ph-text", TOKC.text],
                      ["__st-ph-white", { r: 255, g: 255, b: 255, a: 1 }],
                      ["__st-ph-black", { r: 0, g: 0, b: 0, a: 1 }]];
          var cls = null, bestC = 0;
          for (var o = 0; o < opts.length; o++) {
            var cc = contrast(opts[o][1], ph);
            if (cc >= 4.5) { cls = opts[o][0]; break; }
            if (cc > bestC) { bestC = cc; cls = opts[o][0]; }
          }
          if (cls) work.push(["class", cls]);
        }
      }
    }

    if (saved.bw && saved.bw !== "0px") {
      var bc = parseColor(saved.border);
      if (bc && bc.a > .2) {
        var BL = lum(bc);
        if ((TOK.dark && BL > 130) || (!TOK.dark && BL < 120))
          work.push(["border-color", TOK.sunken]);
      }
    }
    stats.tDecide += clock() - td;
    return work.length ? { el: el, saved: saved, work: work } : null;
  }

  function applyPlan(p) {
    var bg = false;
    for (var i = 0; i < p.work.length; i++) {
      if (p.work[i][0] === "class") {
        p.el.classList.add(p.work[i][1]);
        p.saved.cls = p.work[i][1];
        p.saved.set = true;
        continue;
      }
      put(p.el, p.saved, p.work[i][0], p.work[i][1]);
      if (p.work[i][0] === "background-color") bg = true;
    }
    // A background that has just changed changes the answer for every
    // piece of text inside it, and those elements have not changed at
    // all themselves -- nothing else would ever come back to them. This
    // is where Stack Overflow's menu rows and Amazon's product titles
    // were left black on the dark card they sit in. stale() compares
    // what each of them was judged against, so the ones that are still
    // right cost one comparison and nothing else.
    if (bg) queueTree(p.el);
  }

  // ---- walking the page, a few milliseconds at a time --------------
  //
  // The old pass collected up to 8000 elements per call and dropped
  // the rest, so gnu.org (19431 elements) was themed down to the
  // middle of the page and raw below it. This one queues everything
  // and works through the queue in slices, so a big page finishes a
  // frame or two later instead of never.
  var queue = [], at = 0, scheduled = false;
  // One element, one place in the queue. A page that builds itself
  // (Stack Overflow adds some 9000 nodes as it comes up) hands the
  // observer a parent and then its children, and walking each of them
  // in turn means walking the same elements again and again: 99000
  // measurements for an 11500-element page, measured. With this, an
  // element already waiting is not queued a second time.
  var waiting = new WeakSet();
  var BUDGET = 16;                   // ms of reading per slice
  var CHUNK = 1000;                  // elements measured before writing

  function push(el) {
    if (waiting.has(el)) return;
    waiting.add(el);
    queue.push(el);
    stats.pushes++;
  }

  function queueTree(root) {
    // the document itself is nodeType 9, an element 1: the first pass
    // comes in as the document, every later one as an added element
    if (!root || !root.querySelectorAll) return;
    var tq = clock();
    queueTree2(root);
    stats.tQueue += clock() - tq;
  }
  function queueTree2(root) {
    if (root.nodeType === 1 && wanted(root)) push(root);
    var all;
    try { all = root.querySelectorAll("*"); } catch (e) { return; }
    for (var i = 0; i < all.length; i++)
      if (wanted(all[i])) push(all[i]);
  }

  // what the pass has cost, for the test that watches it (and for
  // anyone wondering where a slow page went). ApplicationWorld only.
  var stats = window.__stStats = window.__stStats
    || { slices: 0, measured: 0, painted: 0, ms: 0, fulls: 0, obs: 0,
         pushes: 0, flips: 0, waits: 0, reputs: 0 };
  ["fulls", "obs", "pushes", "flips", "waits", "reputs", "tStale", "tDecide",
   "tApply", "tAfter", "tQueue"].forEach(
    function (k) { if (!(k in stats)) stats[k] = 0; });
  var clock = (window.performance && performance.now)
    ? function () { return performance.now(); } : function () { return 0; };

  function slice() {
    scheduled = false;
    if (!current()) { queue = []; at = 0; return; }
    var t0 = (window.performance && performance.now) ? performance.now() : 0;
    stats.slices++;
    try {
      do {
        var plans = [], n = 0;
        csCache.clear(); bgcache.clear(); undercache.clear(); planned.clear();
        deferred = [];
        while (at < queue.length && n < CHUNK) {
          var el = queue[at++];
          waiting.delete(el);
          var p = measure(el);
          n++;
          if (p) plans.push(p);
        }
        if (deferred.length) {
          // the restored ones: one recalculation for all of them
          csCache.clear(); bgcache.clear(); undercache.clear();
          var again = deferred;
          deferred = [];
          for (var d = 0; d < again.length; d++) {
            var pd = measure(again[d]);
            n++;
            if (pd) plans.push(pd);
          }
        }
        stats.measured += n;
        stats.painted += plans.length;
        var ta = clock();
        for (var i = 0; i < plans.length; i++) applyPlan(plans[i]);
        stats.tApply += clock() - ta;
        ta = clock();
        // the third phase: with every write of this chunk made, read
        // back what the page now looks like, so the next pass over
        // these elements can tell its own work from the site's. One
        // style recalculation covers the whole chunk.
        csCache.clear();
        for (i = 0; i < plans.length; i++) {
          var done = computed(plans[i].el);
          if (done) plans[i].saved.after = expected(plans[i], done);
        }
        stats.tAfter += clock() - ta;
      } while (at < queue.length
               && (!t0 || performance.now() - t0 < BUDGET));
    } finally {
      if (t0) stats.ms += performance.now() - t0;
      csCache.clear(); bgcache.clear(); undercache.clear(); planned.clear();
      if (at >= queue.length) { queue = []; at = 0; }
      else if (at > 4000) { queue = queue.slice(at); at = 0; }
      stats.queue = queue.length - at;     // what is still to be looked at
      if (queue.length > at) schedule();
    }
  }

  // Neither a timer nor a frame will do for coming back for the next
  // slice. requestAnimationFrame never fires in a tab he has not
  // looked at yet, and setTimeout is throttled to about once a second
  // in exactly the same tab -- measured here: 600 elements a second,
  // so a 12000-element page took half a minute to finish and he saw
  // it finish. A MessageChannel message is an ordinary task and is
  // throttled by neither, so a background tab is themed at the speed
  // of the work rather than the speed of the clock.
  var hop = null;
  if (window.MessageChannel) {
    hop = new MessageChannel();
    hop.port1.onmessage = function () { slice(); };
  }

  function schedule() {
    if (scheduled || !current()) return;
    scheduled = true;
    if (hop) hop.port2.postMessage(0);
    else setTimeout(slice, 0);
  }

  // Looking at the whole page again is how a stylesheet that arrives
  // late is caught -- and also, if nothing holds it back, how a page
  // that adds a <style> for every lazy component (Stack Overflow does)
  // gets looked at twenty times over: 226000 elements measured for an
  // 11500-element page, and the pass still crawling half a minute in.
  // So: not more than one full look a second and a bit, and not more
  // than a handful in all. After that the observer's own records are
  // enough -- they name the elements that actually changed.
  // ...and the cap was four, which is how office.com kept light text
  // on white cards: the cards were looked at while their stylesheet
  // chunk was still on its way (a React page hydrating, section by
  // section), the chunk landed after the fourth look, and nothing
  // ever came back to them -- a stylesheet changing an element's
  // colours is not a mutation the observer can see. So the looks are
  // rate-limited rather than counted out: one every 1.5 seconds at
  // most, a generous ceiling for a page that never settles, and a
  // scroll asks for one as well, because what the page draws late is
  // nearly always what is about to come into view. A look at a page
  // that has not changed costs one comparison per element.
  var fulls = 0, lastFull = 0, fullPending = false;
  function fullQueue() {
    var now = Date.now();
    if (!current() || fulls >= 40) return;
    if (now - lastFull < 1500) {
      // not dropped: a stylesheet that lands inside the quiet period
      // still gets its look, when the period is over
      if (!fullPending) {
        fullPending = true;
        setTimeout(function () { fullPending = false; fullQueue(); },
                   1500 - (now - lastFull) + 20);
      }
      return;
    }
    fulls++;
    stats.fulls++;
    lastFull = now;
    queueTree(document);
    schedule();
  }

  function adapt(root) {
    queueTree(root || document.documentElement);
    // the first pass runs here and now: a page must not show one frame
    // of the site's own colours over the theme's background
    slice();
  }
  window.__stAdapt = adapt;  // ApplicationWorld only; the page can't see it

  // switched off in Settings: take back everything this put on the page
  window.__stUndo = function () {
    var el = document.getElementById("__sitetheme");
    if (el) el.remove();
    if (window.__stSheet && document.adoptedStyleSheets)
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(
        function (x) { return x !== window.__stSheet; });
    if (window.__stObs) { window.__stObs.disconnect(); window.__stObs = null; }
    queue = []; at = 0;
    var all = document.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var saved = orig.get(all[i]);
      if (saved) restore(all[i], saved);
    }
  };

  if (!paint()) {
    document.addEventListener("readystatechange", function once() {
      if (paint()) document.removeEventListener("readystatechange", once);
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { adapt(document); });
  } else {
    adapt(document);
  }
  // the second look is the one that catches a stylesheet that arrived
  // late: stale() lets it change its mind, where the old pass could not
  window.addEventListener("load", function () { fullQueue(); });
  // and a last one, for the pages that paint themselves a second or
  // two in (a framework hydrating, a consent banner restyling the body)
  setTimeout(fullQueue, 2500);
  setTimeout(fullQueue, 6000);
  setTimeout(fullQueue, 15000);
  window.addEventListener("scroll", fullQueue, { passive: true });

  if (!window.__stObs && window.MutationObserver) {
    window.__stObs = new MutationObserver(function (muts) {
      if (!current()) return;
      stats.obs++;
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === "attributes") {
          if (m.attributeName === "style") reput(m.target);
          // a class change restyles the element itself (a menu opening,
          // a row going "selected"); its subtree follows by inheritance
          // and is queued only when the DOM below it actually changes
          if (wanted(m.target)) push(m.target);
          continue;
        }
        var added = m.addedNodes;
        for (var j = 0; j < added.length; j++) {
          if (added[j].nodeType === 3) {
            // text put into an element that was empty when the pass
            // went past it (Amazon fills its truncated product titles
            // in afterwards): the element has no new child element to
            // notice, only words, and only now does it need a colour
            if (m.target && m.target.nodeType === 1 && wanted(m.target))
              push(m.target);
            continue;
          }
          if (added[j].nodeType !== 1) continue;
          queueTree(added[j]);
          // A stylesheet arriving is not a change to one element but to
          // the whole page: wikipedia's table of contents turned dark
          // text on the dark page this way, because the sheet that
          // coloured it landed after everything had been looked at.
          // The elements that have not moved cost one comparison each.
          var t = added[j].tagName;
          if ((t === "STYLE" && added[j].id !== "__sitetheme")
              || t === "LINK") {
            fullQueue();
            if (t === "LINK") added[j].addEventListener("load", fullQueue);
          }
        }
      }
      if (queue.length > at) schedule();
    });
    function arm() {
      if (document.documentElement)
        window.__stObs.observe(document.documentElement,
                               { childList: true, subtree: true,
                                 attributes: true,
                                 attributeFilter: ["style", "class"] });
      else setTimeout(arm, 50);
    }
    arm();
  }
})();"""


def _source(browser):
    mod = _mod(browser)
    p = mod.theme_palette()
    tokens = {
        "dark": bool(mod.theme_def().get("dark")),
        "bg": p["bg"], "surface": p["surface"], "surfaceAlt": p["surfaceAlt"],
        "hover": p["hover"], "sunken": p["sunken"], "text": p["text"],
        "accent": p["accent"], "accentLt": p["accentLt"], "dim": p["dim"],
    }
    css = _site_css(browser)
    # the generation: a page that is re-themed while it is open has to
    # forget what the last theme wrote, and a page that is merely
    # re-scanned must not. Anything that changes the look changes this
    # string, and stale() in the script keys off it.
    gen = hashlib.sha1((css + json.dumps(tokens, sort_keys=True))
                       .encode("utf-8")).hexdigest()[:12]
    return SITE_JS % {"css": json.dumps(css),
                      "tokens": json.dumps(tokens),
                      "gen": json.dumps(gen),
                      "skip": json.dumps(_skipped(browser))}


# ---------------------------------------------------------------------------
# Browser-facing API (unchanged shape)
# ---------------------------------------------------------------------------

def script(browser):
    """The QWebEngineScript a (new) profile should carry."""
    s = QWebEngineScript()
    s.setName(SCRIPT_NAME)
    s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    s.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    s.setRunsOnSubFrames(False)
    s.setSourceCode(_source(browser) if enabled(browser)
                    else "/* site theming off */")
    return s


def refresh(browser):
    """Swap the script in every cookie jar (same protocol as 'theme')."""
    for profile in browser._all_profiles():
        scripts = profile.scripts()
        for old in scripts.find(SCRIPT_NAME):
            scripts.remove(old)
        scripts.insert(script(browser))


def _open_sites(browser):
    for i in range(browser.tabs.count()):
        view = browser.tabs.widget(i)
        if browser._is_header(view) or not hasattr(view, "page"):
            continue
        try:
            if view.url().scheme() == "file":
                continue
        except AttributeError:
            continue
        yield view


def undo_open_sites(browser):
    """Switched off: open tabs lose the theme now, not at their next load."""
    mod = _mod(browser)
    for view in _open_sites(browser):
        view.page().runJavaScript(
            "window.__stUndo && window.__stUndo()", mod.APP_WORLD_ID)


def repaint_open_sites(browser):
    """Re-run the painter in already-open website tabs — live re-theme."""
    if not enabled(browser):
        return
    mod = _mod(browser)
    source = _source(browser)
    for i in range(browser.tabs.count()):
        view = browser.tabs.widget(i)
        if browser._is_header(view) or not hasattr(view, "page"):
            continue
        try:
            if view.url().scheme() == "file":
                continue
        except AttributeError:
            continue
        view.page().runJavaScript(source, mod.APP_WORLD_ID)
