"""Site theming — the active theme restyles real websites, with character.

A companion to the engine pane. browser.py's own THEME_JS deliberately
paints only the six file:// pages of the browser; this module injects a
second, separate script into every cookie jar that does the opposite —
it skips file:// entirely and gives ordinary websites the active theme.

Three layers, all in one injected script:
  1. base CSS      — palette colours for page, text, links, forms,
                     scrollbars, selection; smooth transitions between
                     themes; focus rings.
  2. adaptive pass — JavaScript reads each element's real colours and
                     remaps them: on a dark theme a white card becomes a
                     `surface` card (brighter cards stay relatively
                     brighter, so the page keeps its depth), dark text
                     on it becomes readable; on a light theme the
                     reverse. A MutationObserver keeps up with pages
                     that build themselves as you scroll.
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

import json
import re
import sys

from PyQt6.QtWebEngineCore import QWebEngineScript

SCRIPT_NAME = "site-theme"

MONO = '"JetBrainsMono Nerd Font", "DejaVu Sans Mono", "Liberation Mono", monospace'
SERIF = '"Bitstream Charter", Charter, Georgia, "Liberation Serif", "Times New Roman", serif'

# Font forcing skips span/i/div so icon fonts keep rendering as icons.
FONT_SEL = ("body, p, h1, h2, h3, h4, h5, h6, a, li, td, th, input, button,"
            " textarea, select, label, blockquote, dt, dd, figcaption")

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
    media_filter = ("img, video { filter: brightness(.94); }\n" if dark else "")
    return f"""
html {{ background-color: {p['bg']} !important; }}
body {{ background-color: {p['bg']} !important; color: {p['text']} !important; }}
h1, h2, h3, h4, h5, h6 {{ color: {p['accent']} !important; }}
a, a:visited {{ color: {p['accentLt']} !important; }}
input, textarea, select {{
  background-color: {p['surface']} !important;
  color: {p['text']} !important;
  border-color: {p['sunken']} !important;
}}
button {{
  background-color: {p['surfaceAlt']} !important;
  color: {p['text']} !important;
  border-color: {p['sunken']} !important;
}}
button:hover {{ background-color: {p['hover']} !important; }}
::placeholder {{ color: {p['overlay']} !important; }}
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
{media_filter}html.__st-live :is(body, div, section, article, main, header, footer,
nav, td, th, li, input, button, textarea, select, a, p, h1, h2, h3, h4,
h5, h6) {{
  transition: background-color .35s ease, color .35s ease,
              border-color .35s ease;
}}
"""


# ---------------------------------------------------------------------------
# Layer 3 — identity CSS per character theme
# (fixed inset overlays: ::before carries texture, ::after animation)
# ---------------------------------------------------------------------------

_OVERLAY = ("content: ''; position: fixed; inset: 0; pointer-events: none;"
            " z-index: 2147483645;")
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
    radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(0,10,0,.55) 100%);
}}
{_MOTION} {{
  html::after {{ content: ''; position: fixed; left: 0; right: 0; top: -30%;
    height: 26%; pointer-events: none; z-index: 2147483646;
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
    radial-gradient(ellipse at 50% 42%, transparent 50%, rgba(10,4,0,.6) 100%);
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
  top: auto; height: 32%; pointer-events: none; z-index: 2147483646;
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
button:hover {{ transform: translate(1px, 1px);
  box-shadow: 2px 2px 0 rgba(11,40,11,.85) !important; }}
html::before {{ {_OVERLAY}
  background:
    repeating-linear-gradient({ink} 0 1px, transparent 1px 3px),
    repeating-linear-gradient(90deg, {ink} 0 1px, transparent 1px 3px);
}}
html::after {{ {_OVERLAY} z-index: 2147483646;
  box-shadow: inset 0 0 0 10px {p['accent']}, inset 0 0 0 14px {p['surface']};
}}
"""


def _c64(p):
    return f"""
{FONT_SEL} {{ font-family: {MONO} !important; letter-spacing: .04em; }}
{SQUARE}
h1, h2 {{ text-transform: uppercase; letter-spacing: .16em; }}
h1::after {{ content: "\\2588"; margin-left: .25em; }}
html::before {{ {_OVERLAY}
  background: repeating-linear-gradient(rgba(0,0,0,.20) 0 1px, transparent 1px 4px);
}}
html::after {{ {_OVERLAY} z-index: 2147483646;
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
img, video {{ filter: sepia(.25) contrast(.98); }}
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
img, video {{ filter: grayscale(1) contrast(1.06); }}
h1 {{ text-transform: uppercase; letter-spacing: .04em;
  border-top: 3px double {ink},.8); border-bottom: 3px double {ink},.8);
  padding: .25em 0; }}
h2 {{ border-bottom: 1px solid {ink},.6); padding-bottom: .15em; }}
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
    radial-gradient(ellipse at 50% 40%, transparent 55%, rgba(0,0,0,.30) 100%);
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
    radial-gradient(ellipse at 50% 42%, transparent 55%, rgba(0,0,0,.40) 100%);
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
  var host = location.hostname.toLowerCase().replace(/^www\\./, "");
  if (/^google\\.[a-z.]+$/.test(host)) return;
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

  function parseColor(s) {
    var m = /rgba?\\(([\\d.]+)[, ]+([\\d.]+)[, ]+([\\d.]+)(?:[,/ ]+([\\d.]+%%?))?\\)/.exec(s || "");
    if (!m) return null;
    var a = m[4] === undefined ? 1
      : (m[4].indexOf("%%") >= 0 ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return { r: +m[1], g: +m[2], b: +m[3], a: a };
  }
  function lum(c) { return .2126 * c.r + .7152 * c.g + .0722 * c.b; }

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
  function collect(root) {
    var all = root && root.querySelectorAll ? root.querySelectorAll("*") : [];
    var out = [];
    for (var i = 0; i < all.length && out.length < 8000; i++)
      if (wanted(all[i])) out.push(all[i]);
    return out;
  }

  var PROPS = ["background-color", "background-image", "color",
               "border-color"];

  // Reads first, writes after (see adapt): a computed style read right
  // after a write forces a full style recalc, once per element.
  function remember(el) {
    var saved = orig.get(el), cs, i, p;
    if (saved) return saved;
    try { cs = getComputedStyle(el); } catch (e) { return null; }
    saved = { bg: cs.backgroundColor, color: cs.color,
              bgi: cs.backgroundImage,
              border: cs.borderTopColor, bw: cs.borderTopWidth,
              inl: {}, set: false };
    for (i = 0; i < PROPS.length; i++) {
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
    for (var i = 0, p, o; i < PROPS.length; i++) {
      p = PROPS[i]; o = saved.inl[p];
      if (o[0]) el.style.setProperty(p, o[0], o[1]);
      else el.style.removeProperty(p);
    }
    saved.set = false;
    saved.put = {};
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
    for (var p in saved.put)
      if (el.style.getPropertyValue(p) !== saved.put[p]
          || el.style.getPropertyPriority(p) !== "important")
        el.style.setProperty(p, saved.put[p], "important");
  }

  function adaptOne(el) {
    var saved = remember(el);
    if (!saved) return;
    restore(el, saved);
    var bg = parseColor(saved.bg);
    var bgL = bg && bg.a > .35 ? lum(bg) : null;
    // a translucent fill is a scrim or a tint: it keeps its alpha, or a
    // modal's rgba(0,0,0,.5) backdrop turns into an opaque sheet that
    // hides the whole page on a light theme
    function fill(t) {
      return bg.a > .98 ? t : "color-mix(in srgb, " + t + " "
        + Math.round(bg.a * 100) + "%%, transparent)";
    }
    if (bgL !== null) {
      if (TOK.dark && bgL > 110) {
        var t = bgL > 235 ? TOK.surface : (bgL > 195 ? TOK.surfaceAlt : TOK.hover);
        put(el, saved, "background-color", fill(t));
        if (saved.bgi && saved.bgi.indexOf("gradient") >= 0)
          put(el, saved, "background-image", "none");
      } else if (!TOK.dark && bgL < 90) {
        put(el, saved, "background-color", fill(bgL < 40 ? TOK.surface : TOK.hover));
        if (saved.bgi && saved.bgi.indexOf("gradient") >= 0)
          put(el, saved, "background-image", "none");
      }
    }
    var col = parseColor(saved.color);
    if (col) {
      var CL = lum(col);
      var isLink = el.tagName === "A";
      if (TOK.dark && CL < 110) {
        put(el, saved, "color", isLink ? TOK.accentLt : TOK.text);
      } else if (!TOK.dark && CL > 130 && (bgL === null || bgL >= 150)) {
        put(el, saved, "color", isLink ? TOK.accent : TOK.text);
      }
    }
    if (saved.bw && saved.bw !== "0px") {
      var bc = parseColor(saved.border);
      if (bc && bc.a > .2) {
        var BL = lum(bc);
        if ((TOK.dark && BL > 130) || (!TOK.dark && BL < 120))
          put(el, saved, "border-color", TOK.sunken);
      }
    }
  }

  function adapt(root) {
    var els;
    try { els = collect(root); } catch (e) { return; }
    var n = els.length, self = false, i;
    try { self = !!(root && root.tagName && wanted(root)); }
    catch (e) {}
    if (self) remember(root);
    for (i = 0; i < n; i++) remember(els[i]);
    for (i = 0; i < n; i++) adaptOne(els[i]);
    if (self) adaptOne(root);
  }
  window.__stAdapt = adapt;  // ApplicationWorld only; the page can't see it

  function full() { paint(); adapt(document); }

  // switched off in Settings: take back everything this put on the page
  window.__stUndo = function () {
    var el = document.getElementById("__sitetheme");
    if (el) el.remove();
    if (window.__stSheet && document.adoptedStyleSheets)
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(
        function (x) { return x !== window.__stSheet; });
    if (window.__stObs) { window.__stObs.disconnect(); window.__stObs = null; }
    if (document.documentElement)
      document.documentElement.classList.remove("__st-live");
    var all = document.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var saved = orig.get(all[i]);
      if (saved) restore(all[i], saved);
    }
  };

  // colours ease between themes, but a page loading does not fade in
  function live() {
    setTimeout(function () {
      if (document.documentElement)
        document.documentElement.classList.add("__st-live");
    }, 1200);
  }
  if (document.readyState === "complete") live();
  else window.addEventListener("load", live);

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
  window.addEventListener("load", function () { adapt(document); });

  if (!window.__stObs && window.MutationObserver) {
    var queue = [], scheduled = false;
    function flush() {
      scheduled = false;
      var batch = queue.splice(0, 400);
      for (var i = 0; i < batch.length; i++) window.__stAdapt(batch[i]);
      if (queue.length) schedule();
    }
    function schedule() {
      if (scheduled) return;
      scheduled = true;
      if (window.requestIdleCallback) requestIdleCallback(flush, { timeout: 300 });
      else setTimeout(flush, 120);
    }
    window.__stObs = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        if (muts[i].type === "attributes") { reput(muts[i].target); continue; }
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++)
          if (added[j].nodeType === 1) queue.push(added[j]);
      }
      if (queue.length) schedule();
    });
    function arm() {
      if (document.documentElement)
        window.__stObs.observe(document.documentElement,
                               { childList: true, subtree: true,
                                 attributes: true,
                                 attributeFilter: ["style"] });
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
        "accent": p["accent"], "accentLt": p["accentLt"],
    }
    return SITE_JS % {"css": json.dumps(_site_css(browser)),
                      "tokens": json.dumps(tokens),
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
