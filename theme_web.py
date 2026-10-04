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

While this is enabled, Chromium's ForceDarkMode auto-darkening is held
off (browser.force_dark_on) — the adaptive pass replaces it with the
actual palette instead of an inversion.

Kill switch: set "themeWeb": false in ~/.local/share/browser/config.json.
browser.py only calls script()/refresh()/repaint_open_sites()/enabled().
"""

import json
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


# ---------------------------------------------------------------------------
# Layer 1 — base CSS every theme gets
# ---------------------------------------------------------------------------

def _base_css(p, dark):
    media_filter = ("img, video { filter: brightness(.94); }\n" if dark else "")
    return f"""
html {{ background-color: {p['bg']} !important; }}
body {{ background-color: {p['bg']} !important; color: {p['text']} !important; }}
h1, h2, h3, h4, h5, h6 {{ color: {p['accent']} !important; }}
a, a:visited, a * {{ color: {p['accentLt']} !important; }}
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
{media_filter}body, div, section, article, main, header, footer, nav, td, th, li,
input, button, textarea, select, a, p, h1, h2, h3, h4, h5, h6 {{
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
    "label,h1,h2,h3,h4,h5,h6,a,dl,dt,dd,figure,figcaption,summary,details";

  function adaptOne(el) {
    var cs;
    try { cs = getComputedStyle(el); } catch (e) { return; }
    var saved = orig.get(el);
    if (!saved) {
      saved = { bg: cs.backgroundColor, color: cs.color,
                bgi: cs.backgroundImage,
                border: cs.borderTopColor, bw: cs.borderTopWidth };
      orig.set(el, saved);
    }
    var bg = parseColor(saved.bg);
    var bgL = bg && bg.a > .35 ? lum(bg) : null;
    if (bgL !== null) {
      if (TOK.dark && bgL > 150) {
        var t = bgL > 235 ? TOK.surface : (bgL > 195 ? TOK.surfaceAlt : TOK.hover);
        el.style.setProperty("background-color", t, "important");
        if (saved.bgi && saved.bgi.indexOf("gradient") >= 0)
          el.style.setProperty("background-image", "none", "important");
      } else if (!TOK.dark && bgL < 90) {
        el.style.setProperty("background-color",
          bgL < 40 ? TOK.surface : TOK.hover, "important");
        if (saved.bgi && saved.bgi.indexOf("gradient") >= 0)
          el.style.setProperty("background-image", "none", "important");
      }
    }
    var col = parseColor(saved.color);
    if (col) {
      var CL = lum(col);
      var isLink = el.tagName === "A";
      if (TOK.dark && CL < 110) {
        el.style.setProperty("color",
          isLink ? TOK.accentLt : TOK.text, "important");
      } else if (!TOK.dark && CL > 170 && (bgL === null || bgL >= 150)) {
        el.style.setProperty("color",
          isLink ? TOK.accent : TOK.text, "important");
      }
    }
    if (saved.bw && saved.bw !== "0px") {
      var bc = parseColor(saved.border);
      if (bc && bc.a > .2) {
        var BL = lum(bc);
        if ((TOK.dark && BL > 130) || (!TOK.dark && BL < 120))
          el.style.setProperty("border-color", TOK.sunken, "important");
      }
    }
  }

  function adapt(root) {
    var els;
    try {
      els = root && root.querySelectorAll ? root.querySelectorAll(SEL) : [];
    } catch (e) { return; }
    var n = Math.min(els.length, 8000);
    for (var i = 0; i < n; i++) adaptOne(els[i]);
    try { if (root && root.matches && root.matches(SEL)) adaptOne(root); }
    catch (e) {}
  }
  window.__stAdapt = adapt;  // ApplicationWorld only; the page can't see it

  function full() { paint(); adapt(document); }

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
        var added = muts[i].addedNodes;
        for (var j = 0; j < added.length; j++)
          if (added[j].nodeType === 1) queue.push(added[j]);
      }
      if (queue.length) schedule();
    });
    function arm() {
      if (document.documentElement)
        window.__stObs.observe(document.documentElement,
                               { childList: true, subtree: true });
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
                      "tokens": json.dumps(tokens)}


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
