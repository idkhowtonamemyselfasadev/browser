#!/usr/bin/env python3
"""A minimal, island-styled web browser. Tabs, search bar, start page."""
import base64
import csv
import datetime
import functools
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import unicodedata
import uuid
import time
from pathlib import Path

CONFIG_FILE = Path.home() / ".local/share/browser/config.json"

# sites see prefers-color-scheme: dark and serve their native dark theme
# (0 = dark); must be set before Qt WebEngine starts
# (idempotent: a restarted child inherits the parent's flags)
if ("--blink-settings=preferredColorScheme=0"
        not in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")):
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        + " --blink-settings=preferredColorScheme=0")
# the embedded inspector (DevTools) only serves its frontend resources
# when remote debugging is enabled; bound to localhost by Chromium
os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "127.0.0.1:9222")

from PyQt6.QtCore import (
    QBuffer, QElapsedTimer, QEvent, QEventLoop, QFile, QIODevice, QObject,
    QPoint, QProcess, QRect, QSize, QStringListModel, QTimer, QUrl,
    QUrlQuery, Qt,
    pyqtProperty, pyqtSignal, pyqtSlot,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import (
    QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPen, QPixmap,
    QShortcut, QGuiApplication,
)
from PyQt6.QtWidgets import (
    QApplication, QCompleter, QFileDialog, QFrame, QInputDialog, QLabel,
    QMainWindow, QMenu, QProgressBar, QScrollArea, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLineEdit, QListWidget, QListWidgetItem,
    QSizePolicy, QTabWidget, QTabBar, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QHeaderView,
    QToolButton, QWidgetAction, QMessageBox, QDialog, QDialogButtonBox,
    QCheckBox,
)
from PyQt6.QtWebEngineCore import (
    QWebEnginePermission, QWebEngineProfile, QWebEnginePage, QWebEngineScript,
    QWebEngineSettings,
)
from PyQt6.QtNetwork import (
    QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkProxy,
    QNetworkRequest,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6 import sip

# a real printer needs QtPrintSupport, which is a separate package on
# some distributions; saving a PDF works either way, so the printer
# entry simply stays out of the menu when it is not there
try:
    from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
    HAVE_PRINTER = True
except ImportError:  # pragma: no cover - depends on the installation
    QPrintDialog = QPrinter = None
    HAVE_PRINTER = False

APP_DIR = Path(__file__).resolve().parent
# version query defeats the renderer's cache of local pages, so a new
# tab always shows the current start.html, not a stale cached copy
START_PAGE = QUrl.fromLocalFile(str(APP_DIR / "start.html"))
START_PAGE.setQuery("v=%d" % (APP_DIR / "start.html").stat().st_mtime)

# BROWSER_TIMING=1 puts a stopwatch on opening Settings: one line per
# phase on stderr and nothing anywhere else. Switched off it costs one
# name lookup per phase and writes nothing at all.
TIMING = os.environ.get("BROWSER_TIMING") == "1"


def _timing(label, started):
    """One phase, and how long it took, on stderr."""
    if TIMING:
        print("[timing] %-20s %7.1f ms"
              % (label, (time.perf_counter() - started) * 1000),
              file=sys.stderr, flush=True)


def _timed(fn):
    """Wall time of one bridge answer. With the stopwatch off the call
    goes straight through."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        if not TIMING:
            return fn(*args, **kwargs)
        started = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            _timing("bridge." + fn.__name__, started)
    return run


SEARCH_URL = "https://www.google.com/search?q={}"
SEARCH_ENGINES = {
    "google": ("Google", "https://www.google.com/search?q={}"),
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "bing": ("Bing", "https://www.bing.com/search?q={}"),
    "brave": ("Brave", "https://search.brave.com/search?q={}"),
    "ecosia": ("Ecosia", "https://www.ecosia.org/search?q={}"),
    "startpage": ("Startpage", "https://www.startpage.com/sp/search?query={}"),
}
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
DOWNLOAD_DIR = Path.home() / "Downloads"
# spell-check needs a Chromium .bdic dictionary on disk; these are
# the ones worth offering, and the UI says so when one is missing
SPELL_LANGUAGES = [
    ("en-US", "English (US)"), ("en-GB", "English (UK)"),
    ("de-DE", "Deutsch"), ("fr-FR", "Fran\u00e7ais"),
    ("es-ES", "Espa\u00f1ol"), ("it-IT", "Italiano"),
    ("nl-NL", "Nederlands"), ("pt-BR", "Portugu\u00eas (BR)"),
    ("pl-PL", "Polski"), ("ru-RU", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439"),
    ("sv-SE", "Svenska"), ("tr-TR", "T\u00fcrk\u00e7e"),
]
HOSTS_FILE = Path.home() / ".local/share/browser/hosts.json"
HISTORY_FILE = Path.home() / ".local/share/browser/history.json"
HISTORY_PAGE = QUrl.fromLocalFile(str(APP_DIR / "history.html"))
HISTORY_PAGE.setQuery("v=%d" % (APP_DIR / "history.html").stat().st_mtime)
SETTINGS_PAGE = QUrl.fromLocalFile(str(APP_DIR / "settings.html"))
if (APP_DIR / "settings.html").exists():
    SETTINGS_PAGE.setQuery("v=%d" % (APP_DIR / "settings.html").stat().st_mtime)
DOWNLOADS_FILE = Path.home() / ".local/share/browser/downloads.json"
DOWNLOADS_PAGE = QUrl.fromLocalFile(str(APP_DIR / "downloads.html"))
if (APP_DIR / "downloads.html").exists():
    DOWNLOADS_PAGE.setQuery(
        "v=%d" % (APP_DIR / "downloads.html").stat().st_mtime)
BOOKMARKS_FILE = Path.home() / ".local/share/browser/bookmarks.json"
BOOKMARKS_PAGE = QUrl.fromLocalFile(str(APP_DIR / "bookmarks.html"))
if (APP_DIR / "bookmarks.html").exists():
    BOOKMARKS_PAGE.setQuery(
        "v=%d" % (APP_DIR / "bookmarks.html").stat().st_mtime)
PASSWORDS_PAGE = QUrl.fromLocalFile(str(APP_DIR / "passwords.html"))
if (APP_DIR / "passwords.html").exists():
    PASSWORDS_PAGE.setQuery(
        "v=%d" % (APP_DIR / "passwords.html").stat().st_mtime)
# How long Esc waits for the page in a pane to say whether it wanted
# the key for itself. Only a page that has stopped answering ever
# spends it: a live one replies in well under a millisecond.
PANE_ESC_MS = 250
HISTORY_MAX = 3000
DOWNLOADS_MAX = 500
CLOSED_TABS_MAX = 10  # how far back Ctrl+Shift+T reaches
# The rungs Ctrl+= and Ctrl+- climb: the ladder every browser uses,
# fine where reading actually happens and coarse out at the ends.
ZOOM_STEPS = (0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25,
              1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0)
# Where a private tab's cookies live. It is filed with the virtual
# browsers so that every "for every cookie jar" loop in here reaches
# it too, but it is deliberately not one of them: it is absent from
# self.sessions, so it gets no pill, no Shift+Tab stop and no line in
# the config. The name cannot collide - a real sid is "main" or eight
# hex characters.
PRIVATE_SESSION = "private"
# a print that never reports back must not leave a record stuck on
# "active" for the rest of the run: unremovable, and holding its name
PDF_TIMEOUT_MS = 120000
BOOKMARKS_MAX = 2000
# How deep the Favourites menu is prepared to nest folders. Well past
# anything anyone files by hand, and short enough that a bookmarks.json
# hand-written into a thousand-deep chain cannot walk the menu builder
# off the end of Python's stack. Nothing is lost past it: the folder is
# still there, still in the manager, and the menu says so.
BOOKMARKS_DEPTH = 20

# sites that ship their own dark theme (served via preferredColorScheme):
# force-dark would only slow them down repainting an already-dark page
NATIVE_DARK_SITES = {
    "github.com", "youtube.com", "reddit.com", "twitch.tv", "discord.com",
    "netflix.com", "spotify.com", "tiktok.com", "instagram.com",
    "modrinth.com", "duckduckgo.com",
}

# Google search stays LIGHT while the rest of the web is dark: the
# engine asks every site for dark, so Google's dark gray is inverted
# back to a light look (images and video are re-inverted to normal)
GOOGLE_BLACK_JS = r"""
(function () {
  if (!/^(www\.)?google\.[a-z.]+$/.test(location.hostname)) return;
  var s = document.createElement("style");
  s.textContent =
    "html, body { background: #000 !important; }" +
    ".sfbg, .minidiv, #searchform, #appbar, #sfcnt, #footcnt, #fbar," +
    " #footer, .appbar { background: #000 !important; }";
  (document.head || document.documentElement).appendChild(s);
})();
"""

GOOGLE_LIGHT_JS = r"""
(function () {
  if (!/^(www\.)?google\.[a-z.]+$/.test(location.hostname)) return;
  var bg = getComputedStyle(document.body).backgroundColor;
  var m = bg.match(/\d+/g);
  if (m && (+m[0] + +m[1] + +m[2]) / 3 > 128) return;  // already light
  var s = document.createElement("style");
  s.textContent =
    "html { filter: invert(1) hue-rotate(180deg); background: #fff !important; }" +
    "img, video, iframe, svg, canvas { filter: invert(1) hue-rotate(180deg); }";
  (document.head || document.documentElement).appendChild(s);
})();
"""

# script worlds: 0 (MainWorld) belongs to the page's own JavaScript.
# The password machinery lives in UserWorld — its watcher script and
# the minimal web channel remote pages get are invisible from world 0.
MAIN_WORLD_ID = QWebEngineScript.ScriptWorldId.MainWorld.value
PW_WORLD_ID = QWebEngineScript.ScriptWorldId.UserWorld.value

# how long a half-finished login (step one done, step two still to
# come) is remembered. Long enough for a slow "Next", short enough that
# an abandoned form does not leave an identity lying around all day.
PW_STEP_TTL = 300

# The one content script the password manager runs, in an isolated
# world (qwebchannel.js is prepended at build time). It does three
# things:
#
#   1. reports a submitted login form to the browser, so it can offer
#      to save it. Only {host, scheme, username, password} crosses.
#   2. reports what the page is currently ASKING for — an identifier,
#      a password, or nothing — so the browser can fill the right one.
#      Modern sign-ins (Amazon, Google, Microsoft) put the e-mail on
#      one screen and the password on the next, either after a real
#      navigation or by swapping the DOM in place; a MutationObserver
#      catches the second kind.
#   3. fills what the browser pushes back.
#
# The channel is one-way by design: the page describes itself and the
# browser answers by pushing values into this world. There is no slot
# that hands a credential back to a caller, so nothing a page could
# reach can ask "what would you fill here?" and read the answer.
#
# The username lands immediately, the password does not: it waits for
# a genuine user gesture, the way Chrome and Firefox gate theirs.
# Until then the field really is empty, so a script on the page — an
# injected one, or a login form parked off-screen — reads nothing, and
# no script can forge the gesture (only real input carries isTrusted).
# The bar is one real interaction with the page, not with the form in
# particular: a password box outside a <form> puts the listeners on the
# document, and a page that controls its own DOM could wrap an
# invisible form around the field regardless. That is the same bar
# Chrome sets. Clicking "Sign in" clears it, so nobody retypes.
PASSWORD_WATCH_JS = r"""
(function () {
  if (window !== window.top) return;              // top-level frame only
  if (!/^https?:$/.test(location.protocol)) return;
  if (typeof qt === "undefined" || !qt.webChannelTransport) return;
  var pwObj = null;                    // connect early: a submit often
  new QWebChannel(qt.webChannelTransport, function (ch) {   // unloads
    pwObj = ch.objects.pw || null;                // the page instantly
    report(true);                   // "here is what this page wants"
  });

  // ---- saving -----------------------------------------------------
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!pwObj || !form || form.nodeName !== "FORM") return;
    var pw = form.querySelector('input[type="password"]');
    if (!pw || !pw.value) return;
    var user = "";
    var inputs = form.querySelectorAll("input");
    for (var i = 0; i < inputs.length; i++) {  // last user field above
      if (inputs[i] === pw) break;             // the password box
      var t = (inputs[i].type || "text").toLowerCase();
      if ((t === "text" || t === "email" || t === "tel") && inputs[i].value)
        user = inputs[i].value;
    }
    pwObj.formSubmitted(JSON.stringify({
      host: location.hostname,
      scheme: location.protocol.slice(0, -1),
      username: user, password: pw.value}));
  }, true);

  // ---- what is the page asking for? -------------------------------
  var IDENT = /user|e-?mail|login|logon|account|ident|signin|phone|mobile/i;
  var NOT_IDENT = /search|query|coupon|promo|captcha|postal|postcode/i;
  var GO_ON = /^(next|continue|proceed|sign ?in|log ?in|log ?on|submit|weiter|anmelden|einloggen|fortfahren)$/i;
  var NOT_SIGNIN = /newsletter|abonnier|subscribe|kontakt|contact|feedback|gutschein|voucher/i;
  // whole path segments only: /author/someone is not an auth page,
  // and "account" and "konto" are dropped altogether — /my-account/news
  // is an ordinary page with an ordinary newsletter box on it
  var SIGNIN_URL = /(^|[^a-z])(sign-?in|log-?in|log-?on|o?auth|sso|session|passwo|anmeld|einlogg)([^a-z]|$)/i;
  // the address as it was when this document was built. A page can
  // rewrite its own URL with replaceState at any moment; letting that
  // alone turn an ordinary page into a "sign-in" would hand every page
  // the fill for the asking.
  var FIRST_URL = location.pathname + location.search;

  function usable(el) {          // shown to a person, not planted for us
    if (!el || el.disabled) return false;
    if (el.type === "hidden" || el.hidden) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    var st = el.ownerDocument.defaultView.getComputedStyle(el);
    if (!st) return true;
    if (st.visibility === "hidden" || st.display === "none") return false;
    if (parseFloat(st.opacity || "1") === 0) return false;
    return true;
  }

  function textish(el) {
    var t = (el.type || "text").toLowerCase();
    return t === "text" || t === "email" || t === "tel";
  }

  function words(el) {
    var s = [el.name, el.id, el.placeholder,
             el.getAttribute("aria-label") || ""].join(" ");
    var lab = el.labels && el.labels[0];
    if (lab) s += " " + (lab.textContent || "");
    return s;
  }

  // Is a lone identifier box step one of a login, or the newsletter
  // box at the bottom of a shop?
  //
  // This is a politeness filter, not a boundary. A page that controls
  // its own DOM can always dress up as a sign-in — put a password box
  // in the form, call the button "Continue" — and it is welcome to:
  // all it can obtain is the username, on its own origin, for an
  // account it is about to be told anyway. What the filter buys is
  // that ordinary pages are left alone by accident. The things that
  // actually hold are elsewhere: the password waits for a real
  // gesture, and a credential never crosses to another host.
  // It cannot be gamed in the other direction either — "Kontakt"
  // planted inside a genuine sign-in form does not stop the fill,
  // because the password box settles it first.
  function signinContext(field) {
    var scope = field.form || field.parentElement;
    if (!scope) return false;
    // a password box in the same form, even one the page is keeping
    // hidden for its second screen (Google does exactly that). Only in
    // the same form: one hidden login box in a site-wide layout must
    // not vouch for every other box on the page.
    if (scope.querySelector('input[type="password"]')) return true;
    if (SIGNIN_URL.test(FIRST_URL)) return true;
    if (NOT_SIGNIN.test((scope.textContent || "").slice(0, 600))) return false;
    var btns = scope.querySelectorAll(
        'button, input[type=submit], input[type=button], [role=button]');
    for (var i = 0; i < btns.length && i < 20; i++) {
      var label = (btns[i].value || btns[i].textContent || "").trim();
      if (GO_ON.test(label)) return true;      // "Next", "Continue"...
    }
    return false;
  }

  function identLooks(el) {      // an identifier box, not a search box
    if ((el.type || "").toLowerCase() === "email") return true;
    var ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (ac.indexOf("username") >= 0 || ac.indexOf("email") >= 0) return true;
    var s = words(el);
    if (NOT_IDENT.test(s)) return false;
    return IDENT.test(s);
  }

  // the identity this document is carrying, and whether a person put
  // it there (as opposed to us, or the site pre-filling it)
  var seen = {name: "", typed: false};
  function sameAcct(a, b) {
    return (a || "").toLowerCase() === (b || "").toLowerCase();
  }
  function noteIdentity(v, typed) {
    v = (v || "").trim();
    if (typed) { seen.name = v; seen.typed = true; return; }
    if (!v || sameAcct(v, seen.name)) return;
    // A different account has turned up without anyone typing it: the
    // account tiles on login.live.com, or a site pre-filling its own
    // form. It used to be ignored, and login.live.com swaps its
    // password step in without ever reloading the document, so there
    // was no later moment at which the switch could be noticed — the
    // browser stayed on the first account for the rest of the tab's
    // life. What is in the box now is the account being signed in as.
    //
    // Only the NAME follows. `typed` never comes back down: once a
    // person has typed an account into this document, this login is
    // hand-chosen for good, whatever the page writes into the box
    // afterwards. A draft of this fix cleared the flag for any account
    // it had not itself watched being typed, and that one bit was
    // enough to let a saved password out under a name he had typed
    // himself — a page only had to write a third account into the box
    // on its way to the password step.
    seen.name = v;
  }

  function survey() {
    var inputs = document.getElementsByTagName("input");
    var pws = [], texts = [];
    for (var i = 0; i < inputs.length && i < 300; i++) {
      var el = inputs[i];
      if ((el.type || "").toLowerCase() === "password") {
        if (usable(el)) pws.push(el);
      } else if (textish(el) && usable(el)) texts.push(el);
    }
    var out = {stage: "none", pw: null, user: null};
    if (pws.length === 1) {          // exactly one: a login, not a
      out.stage = "password";        // sign-up or change-password form
      out.pw = pws[0];
      var form = out.pw.form;
      for (var j = 0; j < texts.length; j++) {   // last box above it
        if (form && texts[j].form !== form) continue;
        if (out.pw.compareDocumentPosition(texts[j])
            & Node.DOCUMENT_POSITION_PRECEDING) out.user = texts[j];
      }
    } else if (pws.length === 0) {
      for (var k = 0; k < texts.length; k++) {
        if (!identLooks(texts[k])) continue;
        if (!out.user || (!out.user.form && texts[k].form)) out.user = texts[k];
        if (out.user.form) break;    // one inside a form beats a loose one
      }
      if (out.user && signinContext(out.user)) out.stage = "username";
      else out.user = null;
    }
    if (out.user) noteIdentity(out.user.value, false);
    return out;
  }

  // ---- telling the browser ----------------------------------------
  var watching = false, obs = null, timer = null, lastSent = null;

  function report(force) {
    if (!pwObj) return;
    var s = survey();
    var msg = JSON.stringify({
      host: location.hostname,
      scheme: location.protocol.slice(0, -1),
      stage: s.stage,
      username: (s.user && s.user.value.trim()) || seen.name,
      typed: seen.typed});
    if (msg === lastSent && !force) return;
    lastSent = msg;
    pwObj.loginFormSeen(msg);        // one-way: nothing comes back here
  }

  function schedule(always) {         // quiet until the browser answers
    if ((!watching && !always) || timer) return;
    timer = setTimeout(function () { timer = null; report(false); }, 200);
  }

  function later(e) {   // a click on "Next" redraws a moment afterwards
    if (e.isTrusted) setTimeout(function () { report(false); }, 400);
  }

  function watch() {
    if (watching) return;
    watching = true;
    if (window.MutationObserver && document.documentElement) {
      obs = new MutationObserver(schedule);
      obs.observe(document.documentElement, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ["type", "class", "style", "hidden", "disabled",
                          "aria-hidden"]});
    }
    document.addEventListener("pointerdown", later, true);
    document.addEventListener("keydown", later, true);
  }

  document.addEventListener("input", function (e) {
    var el = e.target;               // they are typing their own account
    if (!e.isTrusted || !el || el.nodeName !== "INPUT") return;
    if (!textish(el) || !identLooks(el)) return;
    // He has changed what stood in the box — typed over it, pasted,
    // cut, or emptied it to put his other account in. From here on the
    // account is his and the filler never writes the identifier again,
    // however often the page redraws.
    //
    // This is the username's half of what mine/onMine do for the
    // password, and it has to be a latch rather than a value test:
    // login.live.com throws the box away and builds a new one, and a
    // new box is empty, which is exactly the state the old rule read
    // as "nobody is signing in here yet, fill the saved account". So
    // he cleared it, the address was back inside the 200ms report, and
    // what he typed next landed on the end of it —
    // first@example.comsecond@example.com, over and over.
    //
    // Our own fills never reach here: setVal dispatches the input
    // event itself, and a dispatched event is not isTrusted.
    if (!ourUser(el)) { userTaken = true; myUser = null; }
    noteIdentity(el.value, true);
    // Always, even before the browser has said it is interested: on a
    // site with nothing saved yet this is the only chance to learn
    // which account he is signing up with, and step two of a two-step
    // form has no username box to learn it from. It costs one message
    // per identifier box a person actually types in.
    schedule(true);
  }, true);

  // ---- filling ----------------------------------------------------
  function setVal(el, v) {
    var d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,
                                            "value");
    if (d && d.set) d.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  }

  var armed = null;                  // {pw, user, pass, scope}
  var mine = null;   // {el, val}: the last value THIS filler wrote, so
                     // it can be told apart from one he typed himself
  var myUser = null;      // the same, for the identifier box
  var userTaken = false;  // he has edited the account himself, so the
                          // account this document is signing in as is
                          // his for the rest of its life

  function typeable(el) {                  // somewhere the user types
    if (!el) return false;
    if (el.isContentEditable === true) return true;
    if (el.nodeName === "TEXTAREA" || el.nodeName === "SELECT") return true;
    if (el.nodeName !== "INPUT") return false;   // a submit button is not
    return /^(text|password|email|tel|url|search|number)$/.test(
        (el.type || "text").toLowerCase());
  }
  function inserting(e) {                  // a keystroke that adds text
    return !!e.key && (e.key.length === 1 || e.key === "Backspace"
                       || e.key === "Delete");
  }
  function disarm() {
    var a = armed;
    if (!a) return;
    armed = null;
    a.scope.removeEventListener("pointerdown", onPoint, true);
    a.scope.removeEventListener("keydown", onKey, true);
    a.scope.removeEventListener("input", onEdit, true);
    a.scope.removeEventListener("paste", onEdit, true);
  }
  function ours(el) {          // a value this filler put there, intact
    return !!mine && mine.el === el && el.value === mine.val;
  }
  function ourUser(el) {       // the same test for the identifier box
    return !!myUser && myUser.el === el && el.value === myUser.val;
  }
  function fill() {
    var a = armed;
    if (!a) return;
    // Do not spend the gesture on a box that cannot take the value: a
    // page that swaps its form in place (Microsoft does) would other-
    // wise have the click consumed by a node it is about to discard,
    // and nothing would be armed when the real box arrives.
    if (!a.pw.isConnected) return;
    if (a.pw.value && !ours(a.pw)) return disarm();   // his own typing
    disarm();
    setVal(a.pw, a.pass);
    mine = {el: a.pw, val: a.pass};
  }
  function onEdit(e) {   // typing their own login: leave it alone
    if (!armed) return;
    if (e.isTrusted && (e.target === armed.pw || e.target === armed.user))
      disarm();
  }
  function onKey(e) {
    if (!armed || !e.isTrusted) return;
    if (inserting(e) && typeable(e.target)) return disarm();
    // Only the two keys that mean "done with this box". It used to be
    // everything that was not a character, which included the modifier
    // of every shortcut: Ctrl+A to select the address before changing
    // account dropped the previous account's password in first, and
    // nothing could correct it afterwards.
    if (e.key === "Enter" || e.key === "Tab") fill();
  }
  function onPoint(e) {
    // Any real click on the page, including one into the e-mail or the
    // password box. Excluding those two was the whole bug: clicking the
    // field you want filled is the commonest way to start a login, and
    // it was the one gesture defined to do nothing. isTrusted is the
    // boundary that matters here; where the click landed is not — and
    // onEdit below still steps aside the moment he actually types.
    if (armed && e.isTrusted) fill();
  }
  // deliberately no submit hook: the UA marks a submit raised by a
  // scripted el.click() as trusted too, which would hand the password
  // straight to an injected script. A person cannot reach the button
  // without a real pointerdown or keydown; a script cannot fake one.
  function arm(pw, user, pass) {
    disarm();
    // document, not pw.form: listeners on the form never saw a click
    // beside it, or a Tab with nothing focused, so those gestures were
    // swallowed. The fill target is armed.pw either way, so widening
    // where we listen does not widen what we write.
    armed = {pw: pw, user: user, pass: pass, scope: document};
    armed.scope.addEventListener("pointerdown", onPoint, true);
    armed.scope.addEventListener("keydown", onKey, true);
    armed.scope.addEventListener("input", onEdit, true);
    armed.scope.addEventListener("paste", onEdit, true);
  }

  function onMine(e) {
    // He is typing over a password we filled in. Ours has to leave the
    // box first, or he types onto the end of a value he cannot see and
    // submits the two stuck together.
    //
    // This cannot live in onKey: fill() disarms, and onKey returns at
    // once when nothing is armed — which is exactly the state the box
    // is in after we filled it. So this listener stays on for the life
    // of the page and does nothing until `mine` says we wrote something
    // and it is still sitting there untouched.
    if (!mine || !e.isTrusted || e.target !== mine.el) return;
    if (e.type === "keydown" && !inserting(e)) return;
    if (ours(mine.el)) setVal(mine.el, "");
    mine = null;
  }
  document.addEventListener("keydown", onMine, true);
  document.addEventListener("paste", onMine, true);

  // the browser pushes here; this world is invisible to page script
  window.__bpw = {
    offer: function (user, pass) {
      watch();
      var s = survey();
      if (s.user && user && !s.user.value && !userTaken) {
        setVal(s.user, user);
        myUser = {el: s.user, val: user};
        noteIdentity(user, false);
      }
      if (s.stage === "password" && s.pw && !pass) {
        // Nothing belongs in this box any more: he has changed account
        // since we filled it, to one we have nothing saved for. Our own
        // value has to come back out — left there it is the first
        // account's password, and the form would submit it under the
        // second account's name. Only ever our own value, and only
        // while it is untouched: what he typed himself is his.
        if (ours(s.pw)) { setVal(s.pw, ""); mine = null; }
        disarm();
        return;
      }
      if (s.stage === "password" && s.pw && pass && ours(s.pw)
          && mine.val !== pass) {
        // He changed account after we had already filled. The gesture
        // that put our value there has happened, so correcting it is
        // not a new disclosure — and without this the first account's
        // password stays in the box and gets submitted with the second
        // account's name.
        setVal(s.pw, pass);
        mine = {el: s.pw, val: pass};
        disarm();
      } else if (s.stage === "password" && s.pw && pass && !s.pw.value) {
        if (!armed || armed.pw !== s.pw || armed.pass !== pass)
          arm(s.pw, s.user, pass);
      } else if (!s.pw) {
        disarm();                  // the password box went away again
      }
    },
    // He has named the account himself, in the browser's own window,
    // on a widget no page can reach, position, draw over or fake a
    // click on. That press is the real gesture the password waits for,
    // so this writes it in rather than arming and waiting for a second
    // one on the page: it is the same boundary, crossed on the chrome's
    // side of the window instead of the document's. Nothing here is
    // reachable from the page — this world is invisible from world 0 —
    // and only the one account he pointed at ever arrives.
    choose: function (user, pass) {
      watch();
      var s = survey();
      if (s.user && user) {
        setVal(s.user, user);
        myUser = {el: s.user, val: user};
      }
      // whatever the page does to the box afterwards, this document is
      // signing in as the account he chose: the filler never writes the
      // identifier again and the guess never comes back.
      if (user) { userTaken = true; noteIdentity(user, true); }
      if (s.stage === "password" && s.pw && pass) {
        // Deliberately over the top of a value already in the box,
        // ours or his. He is looking at the wrong account's password
        // and has just said which one he wants instead; refusing to
        // replace it is what made the old behaviour useless to him.
        disarm();
        setVal(s.pw, pass);
        mine = {el: s.pw, val: pass};
      } else {
        // No password box on screen — step one of a two-step login.
        // The gesture pays for what it is standing in front of and no
        // more: the box that turns up next is armed the ordinary way.
        disarm();
      }
    },
    // force is the tab-change nudge's: the report is deduplicated
    // against the last one sent, and a tab coming to the front has not
    // changed anything the page can see, so without it the browser
    // would never hear about a login form that arrived out of sight.
    // Every older caller passes nothing and gets the old behaviour.
    rescan: function (force) { report(!!force); }
  };
})();
"""

# what a site may ask for, in words the permission bar can show
PERMISSION_LABELS = {
    QWebEnginePermission.PermissionType.MediaAudioCapture:
        "use your microphone",
    QWebEnginePermission.PermissionType.MediaVideoCapture:
        "use your camera",
    QWebEnginePermission.PermissionType.MediaAudioVideoCapture:
        "use your microphone and camera",
    QWebEnginePermission.PermissionType.Notifications:
        "show notifications",
}
# no desktop capture in that list on purpose: Qt never routes it through
# permissionRequested. getDisplayMedia() raises desktopMediaRequested
# instead, which SharePicker answers.

# the port a scheme means when the URL does not spell one out
DEFAULT_PORTS = {"http": 80, "https": 443}

# a plain public hostname and nothing else: no scheme, no port, no path.
# What an old host-only permission key was allowed to look like.
_BARE_HOST = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _origin_key(origin, page_url=None):
    """The identity a permission answer is filed under.

    The web platform's unit of trust is the origin — scheme, host and
    port together. https://p.example and https://p.example:8443 are two
    different sites and have to be asked separately; keying on the bare
    host (as this used to) quietly handed one of them the other's yes.

    Pages the engine cannot name get no durable identity at all. Every
    local file arrives as the single opaque origin "file:///", so one
    local page's yes would speak for every HTML file on the disk: the
    file's own path stands in for an origin, and nothing hostless is
    ever written to the config. Returns (key, what to show, may store).
    """
    scheme = (origin.scheme() or "").lower()
    host = origin.host()
    if scheme in DEFAULT_PORTS and host:
        port = origin.port(DEFAULT_PORTS[scheme])
        show = host if port == DEFAULT_PORTS[scheme] else "%s:%d" % (host, port)
        if scheme == "http":  # worth seeing on the card: this is not TLS
            show = "http://" + show
        return "%s://%s:%d" % (scheme, host, port), show, True
    if page_url is not None and page_url.isLocalFile():
        path = page_url.toLocalFile()
        return "file://" + path, Path(path).name or path, False
    shown = origin.toString() or (
        page_url.toString() if page_url is not None else "")
    return shown or "an unnamed page", shown or "An unnamed page", False


VAULT_PASSWORD_KEY = "vaultPassword"
#: how long an unlocked vault stays unlocked with nothing happening
MASTER_LOCK_KEY = "masterLockMinutes"
#: Fifteen minutes. Long enough that a morning of signing in and out
#: never asks twice; short enough that a laptop left on a desk over
#: lunch is shut again before anyone walks past it. 0 is never, which
#: is his to choose — the box in Settings says what it means.
MASTER_LOCK_DEFAULT = 15


def _vault_password_default(config, directory):
    """Vault Password is something he switches on. For an install that
    predates the switch there is nothing to switch on: the password
    manager was simply there, unconditionally, so it stays there.

    Finished setup is the marker. The wizard is what asks the question
    now, and an install that has already been through the wizard can
    never be asked again — so it must not be silently switched off
    underneath someone who has been using it for weeks.

    The files on disk are the safety net for the other order of events:
    saved a password, never finished the wizard. Anyone holding a vault
    keeps the thing that reads it, whatever the flags say."""
    if (config.get("startPage") or {}).get("setupDone"):
        return True
    for name in ("passwords.json", "passwords-meta.json", "1password-token"):
        if (directory / name).exists():
            return True
    return str(config.get("passwordProvider", "file") or "file") != "file"


def _migrate_permission_config(config):
    """Permission keys used to be "<host>|<type>", which handed
    https://p.example:8443 whatever https://p.example had been allowed
    and collapsed every local file into one key. Keys are real origins
    now, so the old ones have to be re-read.

    A capture or notification grant can only ever have been made from a
    secure context, so a bare public hostname re-reads as https on the
    default port: the one origin such a key names on its own. That is a
    narrowing — it never lets through an origin the old key did not, it
    can only ask once more. Everything else (local files, IP literals,
    localhost, anything already carrying a scheme or a port) cannot be
    re-read without guessing, so it is set aside under
    "permissionsLegacy" and never consulted again. Nothing is deleted
    and nothing is widened. The version marker makes this run once, on
    a config the old browser wrote and never on one this browser did.
    """
    if config.get("permissionsKeyVersion", 1) >= 2:
        return config
    old = config.get("permissions")
    if isinstance(old, dict) and old:
        fresh, legacy = {}, dict(config.get("permissionsLegacy") or {})
        for key, value in old.items():
            host, _, kind = key.rpartition("|")
            host = host.lower()
            if (host and kind and _BARE_HOST.match(host)
                    and not host.replace(".", "").isdigit()):
                fresh["https://%s:443|%s" % (host, kind)] = value
            else:
                legacy[key] = value
        config["permissions"] = fresh
        if legacy:
            config["permissionsLegacy"] = legacy
    config["permissionsKeyVersion"] = 2
    return config


# sentinel: "new tab inherits the current tab's group"
INHERIT_GROUP = object()

# palette offered when creating a tab group
GROUP_COLORS = [
    ("Blue", "#89b4fa"), ("Pink", "#f38ba8"), ("Green", "#a6e3a1"),
    ("Yellow", "#f9e2af"), ("Purple", "#cba6f7"), ("Teal", "#94e2d5"),
    ("Orange", "#fab387"), ("Gray", "#6c7086"),
]

# UI translations for the browser's own pages (start, settings,
# history). Languages not listed fall back to English — websites and
# Google still follow the chosen language via Accept-Language.
UI_STRINGS = {
"en": {"settings":"Settings","search":"Search","searchEngine":"Search engine",
"appearance":"Appearance","whiteGoogle":"White Google",
"whiteGoogleHint":"Off = pitch-black Google",
"autoDarken":"Auto-darken light websites","pageZoom":"Page zoom",
"zoomHint":"Makes everything on a website bigger or smaller. Ctrl + and Ctrl \u2212 zoom one tab; Ctrl 0 puts it back to this.",
"minFont":"Minimum text size","minFontHint":"Forces tiny website text to be at least this big.",
"browsing":"Browsing","reopenTabs":"Reopen tabs from last time",
"askDownload":"Ask where to save each download","translation":"Language",
"translateInto":"Browser and translate language",
"translateHint":"Changes this page, the start page, Google and the translate button.",
"privacy":"Privacy","saveHistory":"Save history","viewHistory":"View history",
"clearHistory":"Clear history","clearCookies":"Clear cookies",
"cookiesHint":"Clear cookies logs this virtual browser out everywhere.",
"updates":"Updates","checkUpdates":"Check for updates","setupT":"Setup",
"runSetup":"Run setup again","setupHint":"Language, search, wallpaper, privacy and quick links",
"filterPh":"Search\u2026","add":"Add","background":"Background",
"allSettings":"All settings","searchSite":"Search {}",
"wizWelcome":"Welcome! Let's set things up",
"wizDrag":"Grab the search bar and drag it wherever you want it.",
"center":"Center it again","nextBtn":"Next \u2192","wallpaper":"Wallpaper",
"pickWallpaper":"Pick a wallpaper for your start page.","finish":"Finish",
"history":"History","searchHistory":"Search history","clearAll":"Clear all",
"noHistory":"No history.","today":"Today","yesterday":"Yesterday",
"downloads":"Downloads","noDownloads":"No downloads.",
"dlClearAll":"Clear finished","dlOpen":"Open","dlFolder":"Folder",
"dlRemove":"Remove","dlCancel":"Cancel","dlPause":"Pause",
"dlResume":"Resume","dlDone":"Done","dlCancelled":"Cancelled",
"dlFailed":"Failed","dlPaused":"Paused","dlLeft":"left",
"plugins":"Plugins",
"pluginsHint":"Userscripts (.user.js) in this folder run on matching pages.",
"reloadPlugins":"Reload plugins","noPlugins":"No plugins installed.","quickInstall":"Quick install","getMore":"Browse Greasy Fork","network":"Network (proxy)","proxyMode":"Proxy","proxySystem":"System","proxyDirect":"Direct (no proxy)","proxyCustom":"Custom","proxyType":"Type","proxyHost":"Host","proxyPort":"Port","proxyHint":"Pick a profile here or from the toolbar proxy button.","autoHint":"Rules override the mode above for matching sites; changes apply after a restart (system proxy is read at launch).","rulesTitle":"Per-site rules","inspectorHint":"Press F12 on any page to open the inspector (DevTools).","fromFile":"From file\u2026","install":"Install","installed":"Installed \u2713","passwords":"Passwords","noPasswords":"No saved passwords.","pwHint":"Stored scrambled on this computer \u2014 anyone who can use this user account can read them.","pwNever":"Never saved for","pwSite":"Site","pwUser":"Username","pwPass":"Password","pwHide":"Hide","pwCopy":"Copy","pwCopied":"Copied \u2713","pwEdit":"Edit","pwSaveBtn":"Save","pwUpdateBtn":"Update","pwSaveAsk":"Save password for {}?","pwUpdateAsk":"Update password for {}?","pwNeverBtn":"Never for this site","close":"Close",
"catGeneral":"General","catPrivacy":"Privacy","catAdvanced":"Advanced",
"catSystem":"Browser","off":"Off",
"addProxy":"Add proxy profile","proxyName":"Name",
"wizBrand":"Setup","wizStepOf":"Step {a} of {b}","wizNavWelcome":"Welcome","wizNavSearch":"Search","wizNavLook":"Start page","wizNavWeb":"Websites","wizNavPrivacy":"Privacy","wizNavLinks":"Quick links","wizNavDone":"Finish","wizWelcomeT":"Welcome","wizWelcomeP":"Let's set your browser up. Nine quick steps \u2014 and you can change every one of them later under Settings.","wizLangLabel":"Language","wizLangHint":"Changes the browser's own pages, the language websites are asked for, and the translate button.","wizSearchT":"Choose your search engine","wizSearchP":"The start page and the address bar send your searches here.","wizLookT":"Make the start page yours","wizLookP":"Whether the browser opens on it, what it looks like, and where the search bar sits.","wizPosLabel":"Search bar position","wizPosHint":"Drag the bar in the preview \u2014 the real start page follows.","wizOwnImage":"Use your own image\u2026","wizWebT":"How websites look","wizWebP":"These apply to every site you visit.","wizDarkHint":"Bright pages get darkened so they don't blind you at night.","wizZoomHint":"Makes everything on a website bigger or smaller.","wizPrivP":"None of this leaves your computer. Choose what the browser remembers.","wizHistHint":"Pages you visit are listed on the history page.","wizPwOffer":"Offer to save passwords","wizPwHint":"When you log in somewhere, the browser asks whether it should remember it.","wizTabsHint":"Start again where you left off.","wizDlHint":"Off = everything lands in your Downloads folder.","wizLinksT":"Quick links","wizLinksP":"Shortcuts under the search bar on every new tab.","wizLinksYours":"On your start page","wizLinksSug":"Suggestions","wizNamePh":"Name","wizDoneT":"You're all set","wizDoneP":"Here is what you picked. Anything can be changed later under Settings \u2014 Setup.","wizSumBar":"Search bar","wizNone":"None","wizCentered":"Centered","wizCustom":"Where you put it","wizYourImage":"Your image","wizOn":"On","wizOff":"Off","wizBack":"\u2190 Back","wizSkip":"Skip to the summary","wizLeaveT":"Leave setup?","wizLeaveP":"Everything you already picked is kept; only a quick link typed but not added is dropped. Setup opens again on your next new tab, or from Settings.","wizLeaveBtn":"Leave","wizStay":"Keep setting up","wizRailFoot":"Settings \u2014 Setup re-runs this any time.","wizNature":"Nature","wizNavTheme":"Colours","wizThemeT":"Pick your colours","wizThemeP":"A theme paints the browser and its own pages. Websites keep the colours their makers gave them.","wizThemeMore":"Twelve of a hundred and fourteen \u2014 the rest are under Settings \u2014 Theme, with a search box.",
"findPh":"Find in page","findNext":"Next match","findPrev":"Previous match",
"findCase":"Match case","findClose":"Close find bar",
"savePdf":"Save as PDF","printTo":"Print\u2026",
"pdfSaving":"Saving as PDF\u2026","pdfFailed":"Could not save the PDF",
"tabSearchPh":"Search tabs\u2026","noTabs":"No matching tabs.",
"startPageName":"Start page",
"bookmarks":"Bookmarks","bmAdd":"Bookmark this page","bmRemove":"Remove bookmark","bmBar":"Bookmarks bar","bmBarEmpty":"No bookmarks yet \u2014 press Ctrl+D on a page you like.","bmOpen":"Open","bmOpenNew":"Open in new tab","bmOpenAll":"Open all in new tabs","bmRename":"Rename","bmEditUrl":"Edit address\u2026","bmDelete":"Delete","bmManage":"Bookmark manager","bmNewFolder":"New folder","bmFolderName":"Folder name","bmNoBookmarks":"No bookmarks.","bmSearch":"Search bookmarks","bmName":"Name","bmUrl":"Address","bmSave":"Save","bmCancel":"Cancel","bmUp":"Up","bmDown":"Down","bmNoFolder":"Bookmarks bar","bmShowBar":"Show bookmarks bar","bmEmptyFolder":"Empty","bmNewName":"New name","bmSure":"Sure?","bmMore":"More bookmarks","bmDeleteFolder":"Delete the folder and its contents ({})","bmMoveTo":"Move to folder","bmFavHint":"Click a folder to open it.",
"setFilterPh":"Search settings\u2026",
"setNoMatch":"Nothing here matches that.",
"setSaved":"Every change is saved the moment you make it.",
"setRailFoot":"Nothing here is sent anywhere \u2014 it all lives in one file on this computer.",
"setDone":"Done",
"setAll":"All settings",
"setSearchTips":"\u2191 \u2193 move \u00b7 Enter opens \u00b7 Esc clears",
"theme":"Theme","themeHint":"A theme paints the browser and its own pages. Websites keep the colours their makers gave them.","themeFilterPh":"Search themes\u2026","themeDark":"Dark","themeLight":"Light","themeCharacter":"With character","themeCurrent":"In use","themeNoMatch":"No theme by that name.","themeRestart":"Websites are still being asked for their dark version. Restart the browser and they follow this theme too.","themeRestartLight":"Websites are still being asked for their light version. Restart the browser and they follow this theme too.","themeRestartBtn":"Restart now","descTheme":"The colours of the browser itself, and of its own pages.",
"descSearch":"Where the address bar and the start page send what you type.",
"descAppearance":"How websites are painted, and how big.",
"descBrowsing":"Tabs, media and the things a page is allowed to start on its own.",
"descDownloads":"Where files land and whether you are asked first.",
"descLanguage":"The language of the browser, of the websites it asks for, and of the spell checker.",
"descPrivacy":"None of this leaves your computer. Choose what the browser remembers.",
"descPasswords":"Where your logins, notes and cards are kept, and the way in to the password manager.",
"descPlugins":"Small userscripts that run on the sites you tell them to \u2014 and the browser's own optional features.",
"vaultPw":"Vault Password","vaultPwHint":"The built-in password manager: saves your logins and fills them back in, with secure notes, payment cards, two-factor codes and a generator. It ships with the browser and does nothing at all until you switch it on.","vaultKept":"Switching this off deletes nothing. Your saved passwords stay on this computer exactly as they are, and they are all there again the moment you switch it back on.","builtIn":"Built-in features","wizVaultT":"Vault Password","wizVaultHint":"A password manager built into the browser: it remembers your logins, fills them back in, and keeps secure notes, cards and two-factor codes. Leave it off and the browser never looks at a login form at all. You can switch it on later under Settings \u2192 Plugins.","wizMasterT":"Master password","wizNavMaster":"Master password","wizMasterP":"One password that locks all the others. This is the only choice here you cannot undo later, so it has a page to itself.","wizMasterLater":"You can also switch this on at any time under Settings \u2192 Passwords.","wizMasterAuto":"Once it is on, the browser locks itself again after 15 minutes of not using your passwords and asks for this password when you next need one. You can change that later under Settings \u2192 Passwords.","wizMasterNoVault":"Nothing to lock","wizMasterNoVaultHint":"The password manager is switched off, so the browser is not keeping any passwords to lock. Switch Vault Password on one step back if you want this.","wizMasterWarnB":"There is no way to reset a master password and no way round it. Nobody can recover it \u2014 not you, not this browser, not whoever wrote it. If you forget it, the passwords stay on this computer and stay unreadable for ever. Pick something you will not lose.","wizMasterHint":"Lock your saved passwords with a passphrase only you know. Without it the key sits in a file next to them, where anything running on this computer can read it.","wizMasterSet":"Set \u2713 \u2014 this is switched on when you finish setup.","wizMasterTyping":"Type it in both boxes to switch it on.","wizMasterHave":"You already have a master password. Change or remove it under Settings \u2192 Passwords.","wizMasterSum":"Master password","wizMasterSumSet":"On","wizMasterSumUnset":"Off \u2014 not finished",
"descNetwork":"Route your traffic through a proxy \u2014 everywhere, or site by site.",
"descUpdates":"Pull the newest version of the browser from its repository.",
"descSetup":"Run the first-run walk-through again, any time.",
"media":"Media",
"searchSuggest":"Search suggestions while typing",
"searchSuggestHint":"Off = nothing you type in the address bar is sent to the search engine. Guesses from your own history still show.",
"smoothScroll":"Smooth scrolling",
"smoothScrollHint":"Scrolling glides instead of jumping line by line.",
"blockAutoplay":"Block videos from playing on their own",
"blockAutoplayHint":"A page has to be clicked before it may play sound or video. Calls and voice chats need this off to ring.",
"pdfViewer":"Open PDFs in the browser",
"pdfViewerHint":"Off = a PDF is downloaded instead of shown.",
"downloads":"Downloads",
"downloadFolder":"Download folder",
"downloadFolderHint":"Where files land when you are not asked.",
"chooseFolder":"Choose\u2026",
"useDefault":"Use ~/Downloads",
"clearHistExit":"Clear history when the browser closes",
"clearCookiesExit":"Clear cookies when the browser closes",
"clearExitHint":"Cookies go for every virtual browser, so you start each session logged out. A site that keeps your login in its own storage rather than in a cookie can still recognise you \u2014 log out on the site itself for those.",
"clearExitCrash":"Kept up even when the browser is killed: a wipe the last run did not get to do is done at the next start.",
"spellCheck":"Check spelling as I type",
"spellLang":"Spell-check language",
"spellHint":"Needs the matching dictionary installed on this computer (Chromium .bdic); without it nothing is underlined.",
"newTabPos":"Where a new tab opens",
"newTabPosEnd":"At the end of the strip",
"newTabPosEndSub":"Every new tab goes to the far right.",
"newTabPosAfter":"Right after this tab",
"newTabPosAfterSub":"The new tab lands next to the one it came from \u2014 from the last tab in the strip that is the same place as the end.",
"newTabPage":"What a new tab shows",
"newTabPageStart":"The start page",
"newTabPageStartSub":"Clock, search bar and your quick links.",
"newTabPageCustom":"A page you choose",
"newTabPageCustomSub":"Type an address below.",
"newTabUrlPh":"example.com",
"newTabUrlAsk":"Type an address, then press Save \u2014 until you do, new tabs still show the start page.",
"newTabUrlBad":"That is not an address the browser can open \u2014 new tabs still open {a}.",
"newTabUrlOk":"New tabs open {a}",
"startUrl":"When the browser starts",
"startUrlHint":"The first tab at launch. Tabs reopened from last time come back instead of it.",
"startUrlStart":"The start page",
"startUrlStartSub":"Clock, search bar and your quick links.",
"startUrlCustom":"A page you choose",
"startUrlCustomSub":"Type an address below.",
"startUrlPh":"example.com",
"startUrlAsk":"Type an address, then press Save \u2014 until you do, the browser starts on the start page.",
"startUrlBad":"That is not an address the browser can open \u2014 the browser still starts on {a}.",
"startUrlOk":"The browser starts on {a}",
"theStartPage":"the start page",
"setDrawFailed":"Part of this page could not be drawn ({}). The rest of it is still here.",
"homePage":"Start page",
"restartLater":"Applies to pages you open from now on.",
"pwManage":"Password manager","pwManageHint":"Logins, secure notes, cards and identities \u2014 with a generator, two-factor codes and a health check.","pwOpenManager":"Open the password manager","pwSearchPh":"Search everything\u2026","pwNew":"New","pwNewLogin":"Login","pwNewNote":"Secure note","pwNewCard":"Payment card","pwNewIdentity":"Identity","pwAll":"All","pwLogins":"Logins","pwNotes":"Notes","pwCards":"Cards","pwIdentities":"Identities","pwFavs":"Favourites","pwFav":"Favourite","pwSort":"Sort","pwSortName":"Name","pwSortUsed":"Recently used","pwSortChanged":"Recently changed","pwNoMatch":"Nothing matches that.","pwTitle":"Name","pwNote":"Note","pwTags":"Tags","pwTagsPh":"work, banking","pwFilterTag":"Tag","pwAllTags":"All tags","pwDelete":"Delete","pwDeleteAsk":"Delete \u201c{}\u201d for good?","pwCancel":"Cancel","pwReveal":"Reveal","pwRevealAsk":"Show this on screen?","pwCopyUser":"Copy username","pwCopyPass":"Copy password","pwCopyCode":"Copy code","pwOpenSite":"Open site","pwGen":"Generate","pwGenTitle":"Password generator","pwGenLength":"Length","pwGenSymbols":"Symbols","pwGenDigits":"Digits","pwGenUpper":"Capitals","pwGenAmbig":"Allow lookalikes (l 1 I O 0)","pwGenUse":"Use this one","pwGenAgain":"Again","pw2fa":"Two-factor code","pw2faSecret":"Two-factor secret","pw2faPh":"otpauth://\u2026 or the base32 secret","pw2faBad":"That is not a usable two-factor secret.","pw2faOk":"Two-factor secret accepted \u2713","pw2faNone":"No two-factor code stored.","pwHealth":"Health","pwReused":"Reused","pwWeak":"Weak","pwOld":"Never changed","pwHealthy":"Nothing to fix \u2713","pwReusedHint":"Used on more than one site \u2014 one break-in opens them all.","pwWeakHint":"Short or too simple to hold up.","pwOldHint":"Unchanged for over a year.","pwStrength":"Strength","pwStrengthWeak":"weak","pwStrengthFair":"fair","pwStrengthStrong":"strong","pwImport":"Import\u2026","pwExport":"Export\u2026","pwImportDone":"Imported: {a} added, {b} updated, {c} skipped.","pwImportFailed":"Nothing could be read from that file.","pwExportWarnT":"This writes every password in plain text.","pwExportWarnB":"The file will hold all {} logins with their passwords, notes and two-factor secrets, readable by anyone who opens it. Nothing in it is encrypted, scrambled or protected in any way. Delete it as soon as you are done with it.","pwExportGo":"Write the plain-text file","pwExportDone":"Written to {}","pwAllFiles":"All files","pwNeverEmpty":"Nothing on the never-save list.","pwCardNumber":"Card number","pwCardHolder":"Name on card","pwCardExpiry":"Expires","pwCardCvv":"Security code","pwCardBrand":"Card type","pwIdName":"Full name","pwIdEmail":"Email","pwIdPhone":"Phone","pwIdStreet":"Street","pwIdCity":"City","pwIdZip":"Postcode","pwIdCountry":"Country","pwNoteBody":"Note contents","pwUnnamed":"Untitled","pwChanged":"Changed","pwCreated":"Added","pwUsed":"Last used","pwNeverUsed":"never","pwLeaveBlank":"Leave blank to keep the password already saved","pwCount":"{} items","pwSaved":"Saved \u2713","pwEmptyTitle":"Nothing saved yet","pwEmptyBody":"Log in somewhere and the browser offers to remember it \u2014 or add something here yourself.","pwPickHint":"Pick something on the left to see it.","pwGenCopied":"A new password is on the clipboard \u2713","pwStore":"Where the secrets are kept","pwStoreFile":"This computer","pwStore1p":"1Password","pwOpToken":"1Password token","pwOpTokenAsk":"Paste the service-account token. It is kept in a file only you can read, is never shown again, and never leaves this computer except to 1Password itself.","pwOpVault":"Vault name","pwOpVaultHint":"The vault the service account is allowed into.","pwOpNoBinary":"The 1Password command-line tool (op) is not installed.","pwOpNoToken":"No service-account token yet.","pwOpFailed":"1Password would not answer: {}","pwSetToken":"Set token\u2026","pwTokenSet":"Token stored \u2713","pwFellBack":"Falling back to the vault on this computer \u2014 {}","pwHealthNA":"The health check needs the passwords themselves, and this store does not hand them over.","pwSwitch":"Use this one","pwActive":"In use","pwFetching":"Fetching\u2026","pwExportNA":"Only the vault on this computer can be exported. 1Password does not hand the passwords over, so the file would list every login with an empty password column \u2014 something that looks like a backup and is not one.","pwOpBadToken":"The token file cannot be read \u2014 paste the token again.","pwStoreChecking":"Reaching for {}\u2026","pwGenHint":"Need a new one? Ctrl+Shift+G puts a strong password on the clipboard.","pwSaveFailed":"Not saved \u2014 the store would not take it.","pwDeleteFailed":"Not deleted \u2014 it is still in the store.","pwFetchFailed":"Could not get that from the store.","pwNothingThere":"Nothing is stored in that field.","pwImporting":"Importing\u2026","pwDenied":"This page is out of date","pwDeniedBody":"Open the password manager again from the menu. The key this page is holding belongs to an earlier run of the browser, so nothing was handed over.","pwSiteDead":"Not a host name, so this login never fills anywhere.","pwStoreHint":"Switching does not move or copy anything \u2014 each store keeps what it already had.","pwVaultNewer":"These passwords were saved by a newer version of the browser and this one cannot read them. Nothing has been changed or lost \u2014 open them with the newer version. Until then nothing here can be shown or saved.","acctPickTitle":"Which account?","acctPickBody":"More than one login is saved for {}. Pick the one to sign in with \u2014 nothing is filled in until you do, and the page is never told what is on this list.","acctPickNoName":"(no username saved)","acctPickCancel":"Not now","acctPickTip":"Choose which saved account signs in here","acctPickNone":"Only one login is saved for this page.",
"toolbar":"Toolbar","descToolbar":"Which buttons sit at the top, and in what order.","tbHint":"A right-click on the toolbar itself opens the same list.","cardRendering":"How pages are drawn","cardSize":"Size","cardKept":"What is kept","cardInstalled":"Installed","tbShown":"On the toolbar","tbHidden":"Not shown","tbElsewhere":"Elsewhere in the chrome","tbElsewhereHint":"These sit where they sit \u2014 you can take one away, but not move it.","tbFixed":"Always there","tbFixedWhy":"This one stays. You can move it along the bar, but not take it away.","tbMoveUp":"Move earlier on the bar","tbMoveDown":"Move later on the bar","tbFixedHint":"Back, forward, reload and the address bar stay. A browser with no way back is a broken browser.","tbShortcutHint":"Taking a button away never touches its keyboard shortcut \u2014 Ctrl+P still prints.","tbReset":"Back to the usual set","tbCustomize":"Customise toolbar\u2026","tbBack":"Back","tbForward":"Forward","tbReload":"Reload","tbHome":"Start page","tbNewTab":"New tab","tbAddress":"Address bar","tbFind":"Find on page","tbHistory":"History","tbDownloads":"Downloads","tbBookmarks":"Bookmarks","tbPasswords":"Passwords","tbProxy":"Proxy","tbPrint":"Print","tbTranslate":"Translate","tbSettings":"Settings","tbFullscreen":"Full screen","tbStar":"Bookmark star","tbGroups":"Tab groups","tbFavorites":"Favourites",
"privateTab":"Private","privateNew":"New private tab",
"privateTip":"Private tab \u2014 nothing is kept once it closes",
"masterPw":"Master password","masterPwName":"Lock the vault with a master password","masterPwHint":"The key to your saved passwords is worked out from a passphrase you type, instead of being kept in a file next to them. Until you unlock it, nothing on this computer can read them \u2014 not the browser, not anyone using your account.","masterWarnT":"If you forget it, your passwords are gone.","masterWarnB":"There is no way to reset a master password and no way round it. Nobody can recover it \u2014 not you, not this browser, not whoever wrote it. The passwords stay on this computer and stay unreadable for ever. Export them first if you want a way back, and keep that file somewhere safe.","masterSetT":"Set a master password","masterSetGo":"Switch it on","masterNewPh":"Master password","masterAgainPh":"Type it again","masterPassPh":"Master password","masterCurrentPh":"Current master password","masterMinHint":"At least 8 characters. A few unrelated words you will not forget beat a short one with punctuation in it.","masterMismatch":"The two do not match.","masterShort":"Too short \u2014 8 characters at the very least.","masterExportFirst":"Export passwords first\u2026","masterUnlockT":"Unlock passwords","masterUnlockAsk":"Type your master password to unlock the vault.","masterUnlockGo":"Unlock","masterWrong":"That was not it.","masterChangeT":"Change master password","masterChangeAsk":"Your saved passwords are not touched \u2014 only the key changes.","masterChangeGo":"Change it","masterChangeDone":"Master password changed \u2713","masterOnDone":"The vault is locked with your master password \u2713","masterOffT":"Switch the master password off?","masterOffB":"Your passwords all stay exactly where they are. But the key goes back into a file next to them, so anyone who can use this computer account will be able to read them again.","masterOffDone":"Master password removed","masterFailed":"That did not work \u2014 nothing was changed.","masterLockNow":"Lock now","masterChangeBtn":"Change master password\u2026","masterAuto":"Lock again after","masterAutoHint":"With nothing happening for this long, the vault shuts itself and asks again.","masterAutoNever":"Never","masterMinutes":"{} minutes","masterHour":"1 hour","masterOn":"On \u2014 unlocked","masterShut":"On \u2014 locked","masterOffState":"Off","masterLockedTitle":"The vault is locked","masterLockedBody":"Your saved passwords are unreadable until you type your master password.","masterUnlockBtn":"Unlock\u2026","masterLockedLine":"Locked \u2014 unlock the password manager to see what is saved.","masterEncHint":"Encrypted on this computer with your master password. Locked, nothing here can read them.",
"privatePermHint":"Only in this private tab."},
"de": {"settings":"Einstellungen","search":"Suche","searchEngine":"Suchmaschine",
"appearance":"Aussehen","whiteGoogle":"Wei\u00dfes Google",
"whiteGoogleHint":"Aus = pechschwarzes Google",
"autoDarken":"Helle Seiten abdunkeln","pageZoom":"Seitenzoom",
"zoomHint":"Macht alles auf einer Webseite gr\u00f6\u00dfer oder kleiner. Strg + und Strg \u2212 zoomen einen Tab; Strg 0 setzt ihn hierhin zur\u00fcck.",
"minFont":"Minimale Textgr\u00f6\u00dfe","minFontHint":"Erzwingt, dass winziger Text mindestens so gro\u00df ist.",
"browsing":"Surfen","reopenTabs":"Tabs vom letzten Mal \u00f6ffnen",
"askDownload":"Bei Downloads nach Speicherort fragen","translation":"Sprache",
"translateInto":"Browser- und \u00dcbersetzungssprache",
"translateHint":"\u00c4ndert diese Seite, die Startseite, Google und den \u00dcbersetzen-Knopf.",
"privacy":"Privatsph\u00e4re","saveHistory":"Verlauf speichern",
"viewHistory":"Verlauf ansehen","clearHistory":"Verlauf l\u00f6schen",
"clearCookies":"Cookies l\u00f6schen",
"cookiesHint":"Cookies l\u00f6schen meldet diesen virtuellen Browser \u00fcberall ab.",
"updates":"Updates","checkUpdates":"Nach Updates suchen","setupT":"Einrichtung",
"runSetup":"Einrichtung neu starten","setupHint":"Sprache, Suche, Hintergrund, Privatsph\u00e4re und Links",
"filterPh":"Suchen\u2026","add":"Hinzuf\u00fcgen","background":"Hintergrund",
"allSettings":"Alle Einstellungen","searchSite":"{} durchsuchen",
"wizWelcome":"Willkommen! Richten wir alles ein",
"wizDrag":"Zieh die Suchleiste dorthin, wo du sie haben willst.",
"center":"Wieder zentrieren","nextBtn":"Weiter \u2192","wallpaper":"Hintergrundbild",
"pickWallpaper":"W\u00e4hle ein Hintergrundbild f\u00fcr deine Startseite.",
"finish":"Fertig","history":"Verlauf","searchHistory":"Verlauf durchsuchen",
"clearAll":"Alles l\u00f6schen","noHistory":"Kein Verlauf.","today":"Heute",
"yesterday":"Gestern",
"downloads":"Downloads","noDownloads":"Keine Downloads.",
"dlClearAll":"Fertige entfernen","dlOpen":"\u00d6ffnen","dlFolder":"Ordner",
"dlRemove":"Entfernen","dlCancel":"Abbrechen","dlPause":"Pause",
"dlResume":"Fortsetzen","dlDone":"Fertig","dlCancelled":"Abgebrochen",
"dlFailed":"Fehlgeschlagen","dlPaused":"Pausiert","dlLeft":"verbleibend",
"plugins":"Plugins",
"pluginsHint":"Userscripts (.user.js) in diesem Ordner laufen auf passenden Seiten.",
"reloadPlugins":"Plugins neu laden","noPlugins":"Keine Plugins installiert.","quickInstall":"Schnellinstallation","getMore":"Greasy Fork durchsuchen","network":"Netzwerk (Proxy)","proxyMode":"Proxy","proxySystem":"System","proxyDirect":"Direkt (kein Proxy)","proxyCustom":"Benutzerdefiniert","proxyType":"Typ","proxyHost":"Host","proxyPort":"Port","proxyHint":"W\u00e4hle ein Profil hier oder \u00fcber den Proxy-Knopf in der Leiste.","autoHint":"Regeln \u00fcberschreiben den Modus oben f\u00fcr passende Seiten; \u00c4nderungen gelten nach einem Neustart (System-Proxy wird beim Start gelesen).","rulesTitle":"Seitenregeln","inspectorHint":"F12 auf einer Seite \u00f6ffnet den Inspektor (DevTools).","fromFile":"Aus Datei\u2026","install":"Installieren","installed":"Installiert \u2713","passwords":"Passw\u00f6rter","noPasswords":"Keine gespeicherten Passw\u00f6rter.","pwHint":"Verschleiert auf diesem Computer gespeichert \u2014 wer dieses Benutzerkonto nutzt, kann sie lesen.","pwNever":"Nie speichern f\u00fcr","pwSite":"Seite","pwUser":"Benutzername","pwPass":"Passwort","pwHide":"Verbergen","pwCopy":"Kopieren","pwCopied":"Kopiert \u2713","pwEdit":"Bearbeiten","pwSaveBtn":"Speichern","pwUpdateBtn":"Aktualisieren","pwSaveAsk":"Passwort f\u00fcr {} speichern?","pwUpdateAsk":"Passwort f\u00fcr {} aktualisieren?","pwNeverBtn":"Nie f\u00fcr diese Seite","close":"Schlie\u00dfen",
"catGeneral":"Allgemein","catPrivacy":"Privatsph\u00e4re",
"catAdvanced":"Erweitert","catSystem":"Browser","off":"Aus",
"addProxy":"Proxy-Profil hinzuf\u00fcgen","proxyName":"Name",
"wizBrand":"Einrichtung","wizStepOf":"Schritt {a} von {b}","wizNavWelcome":"Willkommen","wizNavSearch":"Suche","wizNavLook":"Startseite","wizNavWeb":"Webseiten","wizNavPrivacy":"Privatsph\u00e4re","wizNavLinks":"Schnelllinks","wizNavDone":"Fertig","wizWelcomeT":"Willkommen","wizWelcomeP":"Richten wir deinen Browser ein. Neun kurze Schritte \u2014 und alles davon l\u00e4sst sich sp\u00e4ter in den Einstellungen \u00e4ndern.","wizLangLabel":"Sprache","wizLangHint":"\u00c4ndert die Seiten des Browsers, die Sprache, die Webseiten bekommen, und den \u00dcbersetzen-Knopf.","wizSearchT":"W\u00e4hle deine Suchmaschine","wizSearchP":"Startseite und Adressleiste schicken deine Suchen dorthin.","wizLookT":"Mach die Startseite zu deiner","wizLookP":"Ob der Browser damit startet, wie sie aussieht und wo die Suchleiste sitzt.","wizPosLabel":"Position der Suchleiste","wizPosHint":"Zieh die Leiste in der Vorschau \u2014 die echte Startseite macht es nach.","wizOwnImage":"Eigenes Bild verwenden\u2026","wizWebT":"Wie Webseiten aussehen","wizWebP":"Das gilt f\u00fcr jede Seite, die du besuchst.","wizDarkHint":"Helle Seiten werden abgedunkelt, damit sie dich nachts nicht blenden.","wizZoomHint":"Macht alles auf einer Webseite gr\u00f6\u00dfer oder kleiner.","wizPrivP":"Nichts davon verl\u00e4sst deinen Computer. W\u00e4hle, woran sich der Browser erinnert.","wizHistHint":"Besuchte Seiten stehen auf der Verlaufsseite.","wizPwOffer":"Passw\u00f6rter zum Speichern anbieten","wizPwHint":"Wenn du dich irgendwo anmeldest, fragt der Browser, ob er es sich merken soll.","wizTabsHint":"Da weitermachen, wo du aufgeh\u00f6rt hast.","wizDlHint":"Aus = alles landet im Downloads-Ordner.","wizLinksT":"Schnelllinks","wizLinksP":"Verkn\u00fcpfungen unter der Suchleiste auf jedem neuen Tab.","wizLinksYours":"Auf deiner Startseite","wizLinksSug":"Vorschl\u00e4ge","wizNamePh":"Name","wizDoneT":"Alles bereit","wizDoneP":"Das hast du gew\u00e4hlt. Alles l\u00e4sst sich sp\u00e4ter unter Einstellungen \u2014 Einrichtung \u00e4ndern.","wizSumBar":"Suchleiste","wizNone":"Keins","wizCentered":"Mittig","wizCustom":"Wo du sie hingelegt hast","wizYourImage":"Dein Bild","wizOn":"An","wizOff":"Aus","wizBack":"\u2190 Zur\u00fcck","wizSkip":"Direkt zur \u00dcbersicht","wizLeaveT":"Einrichtung verlassen?","wizLeaveP":"Alles bereits Gew\u00e4hlte bleibt erhalten; nur ein Schnelllink, den du getippt, aber nicht hinzugef\u00fcgt hast, geht verloren. Die Einrichtung \u00f6ffnet sich beim n\u00e4chsten neuen Tab wieder oder \u00fcber die Einstellungen.","wizLeaveBtn":"Verlassen","wizStay":"Weiter einrichten","wizRailFoot":"Einstellungen \u2014 Einrichtung startet das jederzeit neu.","wizNature":"Natur","wizNavTheme":"Farben","wizThemeT":"W\u00e4hle deine Farben","wizThemeP":"Ein Design f\u00e4rbt den Browser und seine eigenen Seiten. Webseiten behalten die Farben, die ihre Macher ihnen gegeben haben.","wizThemeMore":"Zw\u00f6lf von hundertvierzehn \u2014 der Rest steht unter Einstellungen \u2014 Design, mit einem Suchfeld.",
"findPh":"Auf Seite suchen","findNext":"N\u00e4chster Treffer",
"findPrev":"Vorheriger Treffer","findCase":"Gro\u00df-/Kleinschreibung",
"findClose":"Suchleiste schlie\u00dfen",
"savePdf":"Als PDF speichern","printTo":"Drucken\u2026",
"pdfSaving":"Wird als PDF gespeichert\u2026",
"pdfFailed":"PDF konnte nicht gespeichert werden",
"tabSearchPh":"Tabs durchsuchen\u2026","noTabs":"Keine passenden Tabs.",
"startPageName":"Startseite",
"bookmarks":"Lesezeichen","bmAdd":"Diese Seite als Lesezeichen","bmRemove":"Lesezeichen entfernen","bmBar":"Lesezeichenleiste","bmBarEmpty":"Noch keine Lesezeichen \u2014 Strg+D auf einer Seite, die dir gef\u00e4llt.","bmOpen":"\u00d6ffnen","bmOpenNew":"In neuem Tab \u00f6ffnen","bmOpenAll":"Alle in neuen Tabs \u00f6ffnen","bmRename":"Umbenennen","bmEditUrl":"Adresse bearbeiten\u2026","bmDelete":"L\u00f6schen","bmManage":"Lesezeichenverwaltung","bmNewFolder":"Neuer Ordner","bmFolderName":"Ordnername","bmNoBookmarks":"Keine Lesezeichen.","bmSearch":"Lesezeichen durchsuchen","bmName":"Name","bmUrl":"Adresse","bmSave":"Speichern","bmCancel":"Abbrechen","bmUp":"Hoch","bmDown":"Runter","bmNoFolder":"Lesezeichenleiste","bmShowBar":"Lesezeichenleiste anzeigen","bmEmptyFolder":"Leer","bmNewName":"Neuer Name","bmSure":"Sicher?","bmMore":"Weitere Lesezeichen","bmDeleteFolder":"Ordner samt Inhalt l\u00f6schen ({})","bmMoveTo":"In Ordner verschieben","bmFavHint":"Auf einen Ordner klicken, um ihn zu \u00f6ffnen.",
"setFilterPh":"Einstellungen suchen\u2026",
"setNoMatch":"Dazu passt hier nichts.",
"setSaved":"Jede \u00c4nderung wird sofort gespeichert.",
"setRailFoot":"Nichts davon geht irgendwohin \u2014 alles steht in einer Datei auf diesem Computer.",
"setDone":"Fertig",
"setAll":"Alle Einstellungen",
"setSearchTips":"\u2191 \u2193 wechseln \u00b7 Enter \u00f6ffnet \u00b7 Esc leert",
"theme":"Design","themeHint":"Ein Design f\u00e4rbt den Browser und seine eigenen Seiten. Webseiten behalten die Farben, die ihre Macher ihnen gegeben haben.","themeFilterPh":"Designs durchsuchen\u2026","themeDark":"Dunkel","themeLight":"Hell","themeCharacter":"Mit Charakter","themeCurrent":"In Benutzung","themeNoMatch":"Kein Design mit diesem Namen.","themeRestart":"Webseiten wird weiterhin gesagt, sie sollen ihre dunkle Fassung zeigen. Starte den Browser neu, dann folgen sie diesem Design auch.","themeRestartLight":"Webseiten wird weiterhin gesagt, sie sollen ihre helle Fassung zeigen. Starte den Browser neu, dann folgen sie diesem Design auch.","themeRestartBtn":"Jetzt neu starten","descTheme":"Die Farben des Browsers selbst \u2014 und seiner eigenen Seiten.",
"descSearch":"Wohin Adressleiste und Startseite schicken, was du tippst.",
"descAppearance":"Wie Webseiten gezeichnet werden \u2014 und wie gro\u00df.",
"descBrowsing":"Tabs, Medien und was eine Seite von allein starten darf.",
"descDownloads":"Wo Dateien landen und ob vorher gefragt wird.",
"descLanguage":"Die Sprache des Browsers, der angeforderten Webseiten und der Rechtschreibpr\u00fcfung.",
"descPrivacy":"Nichts davon verl\u00e4sst deinen Computer. W\u00e4hle, woran sich der Browser erinnert.",
"descPasswords":"Wo deine Logins, Notizen und Karten liegen \u2014 und der Weg in die Passwortverwaltung.",
"descPlugins":"Kleine Userscripts, die auf den Seiten laufen, die du angibst \u2014 und die eigenen optionalen Funktionen des Browsers.",
"vaultPw":"Vault Password","vaultPwHint":"Die eingebaute Passwortverwaltung: merkt sich deine Logins und f\u00fcllt sie wieder aus, mit sicheren Notizen, Zahlungskarten, Zwei-Faktor-Codes und Generator. Sie ist im Browser enthalten und tut gar nichts, bis du sie einschaltest.","vaultKept":"Ausschalten l\u00f6scht nichts. Deine gespeicherten Passw\u00f6rter bleiben genau so auf diesem Computer liegen und sind sofort wieder da, wenn du es wieder einschaltest.","builtIn":"Eingebaute Funktionen","wizVaultT":"Vault Password","wizVaultHint":"Eine Passwortverwaltung im Browser: sie merkt sich deine Logins, f\u00fcllt sie wieder aus und verwahrt sichere Notizen, Karten und Zwei-Faktor-Codes. L\u00e4sst du sie aus, schaut der Browser Anmeldeformulare gar nicht erst an. Du kannst sie sp\u00e4ter unter Einstellungen \u2192 Plugins einschalten.","wizMasterT":"Hauptpasswort","wizNavMaster":"Hauptpasswort","wizMasterP":"Ein Passwort, das alle anderen abschlie\u00dft. Es ist die einzige Entscheidung hier, die du sp\u00e4ter nicht r\u00fcckg\u00e4ngig machen kannst \u2014 deshalb hat sie eine eigene Seite.","wizMasterLater":"Du kannst das auch jederzeit unter Einstellungen \u2192 Passw\u00f6rter einschalten.","wizMasterAuto":"Sobald es an ist, schlie\u00dft sich der Browser nach 15 Minuten ohne Benutzung deiner Passw\u00f6rter wieder ab und fragt danach, wenn du das n\u00e4chste Mal eins brauchst. Das kannst du sp\u00e4ter unter Einstellungen \u2192 Passw\u00f6rter \u00e4ndern.","wizMasterNoVault":"Nichts abzuschlie\u00dfen","wizMasterNoVaultHint":"Die Passwortverwaltung ist ausgeschaltet, der Browser verwahrt also keine Passw\u00f6rter, die abgeschlossen werden k\u00f6nnten. Schalte einen Schritt zur\u00fcck Vault Password ein, wenn du das m\u00f6chtest.","wizMasterWarnB":"Ein Hauptpasswort l\u00e4sst sich nicht zur\u00fccksetzen und nicht umgehen. Niemand kann es wiederherstellen \u2014 du nicht, dieser Browser nicht, und auch nicht, wer ihn geschrieben hat. Wenn du es vergisst, bleiben die Passw\u00f6rter auf diesem Computer und bleiben f\u00fcr immer unlesbar. Nimm etwas, das du nicht verlierst.","wizMasterHint":"Sch\u00fctze deine gespeicherten Passw\u00f6rter mit einem Kennwort, das nur du kennst. Ohne eins liegt der Schl\u00fcssel in einer Datei daneben, wo ihn alles lesen kann, was auf diesem Computer l\u00e4uft.","wizMasterSet":"Gesetzt \u2713 \u2014 das wird eingeschaltet, wenn du die Einrichtung abschlie\u00dft.","wizMasterTyping":"Gib es in beide Felder ein, um es einzuschalten.","wizMasterHave":"Du hast bereits ein Hauptpasswort. \u00c4ndern oder entfernen kannst du es unter Einstellungen \u2192 Passw\u00f6rter.","wizMasterSum":"Hauptpasswort","wizMasterSumSet":"An","wizMasterSumUnset":"Aus \u2014 nicht fertig",
"descNetwork":"Den Verkehr \u00fcber einen Proxy leiten \u2014 \u00fcberall oder pro Seite.",
"descUpdates":"Die neueste Version des Browsers aus dem Repository holen.",
"descSetup":"Die Ersteinrichtung jederzeit noch einmal durchlaufen.",
"media":"Medien",
"searchSuggest":"Suchvorschl\u00e4ge beim Tippen",
"searchSuggestHint":"Aus = nichts aus der Adressleiste geht an die Suchmaschine. Vorschl\u00e4ge aus deinem Verlauf bleiben.",
"smoothScroll":"Sanftes Scrollen",
"smoothScrollHint":"Das Scrollen gleitet, statt zeilenweise zu springen.",
"blockAutoplay":"Videos nicht von allein starten lassen",
"blockAutoplayHint":"Erst ein Klick auf die Seite erlaubt Ton und Video. Anrufe und Sprachchats brauchen das aus, um zu klingeln.",
"pdfViewer":"PDFs im Browser \u00f6ffnen",
"pdfViewerHint":"Aus = ein PDF wird heruntergeladen statt angezeigt.",
"downloads":"Downloads",
"downloadFolder":"Download-Ordner",
"downloadFolderHint":"Wo Dateien landen, wenn nicht gefragt wird.",
"chooseFolder":"Ausw\u00e4hlen\u2026",
"useDefault":"~/Downloads verwenden",
"clearHistExit":"Verlauf beim Schlie\u00dfen l\u00f6schen",
"clearCookiesExit":"Cookies beim Schlie\u00dfen l\u00f6schen",
"clearExitHint":"Cookies verschwinden f\u00fcr jeden virtuellen Browser \u2014 du startest also \u00fcberall abgemeldet. Eine Seite, die deinen Login im eigenen Speicher statt in einem Cookie h\u00e4lt, kann dich trotzdem wiedererkennen \u2014 melde dich daf\u00fcr auf der Seite selbst ab.",
"clearExitCrash":"Gilt auch, wenn der Browser abst\u00fcrzt: Was der letzte Lauf nicht mehr geschafft hat, wird beim n\u00e4chsten Start nachgeholt.",
"spellCheck":"Rechtschreibung beim Tippen pr\u00fcfen",
"spellLang":"Sprache der Rechtschreibpr\u00fcfung",
"spellHint":"Braucht das passende W\u00f6rterbuch auf diesem Computer (Chromium .bdic); ohne es wird nichts unterringelt.",
"newTabPos":"Wo ein neuer Tab aufgeht",
"newTabPosEnd":"Am Ende der Leiste",
"newTabPosEndSub":"Jeder neue Tab geht ganz nach rechts.",
"newTabPosAfter":"Direkt neben diesem Tab",
"newTabPosAfterSub":"Der neue Tab landet neben dem, aus dem er kam \u2014 beim letzten Tab der Leiste ist das dieselbe Stelle wie das Ende.",
"newTabPage":"Was ein neuer Tab zeigt",
"newTabPageStart":"Die Startseite",
"newTabPageStartSub":"Uhr, Suchleiste und deine Schnelllinks.",
"newTabPageCustom":"Eine Seite deiner Wahl",
"newTabPageCustomSub":"Trag unten eine Adresse ein.",
"newTabUrlPh":"example.com",
"newTabUrlAsk":"Trag eine Adresse ein und dr\u00fcck Speichern \u2014 bis dahin zeigen neue Tabs weiter die Startseite.",
"newTabUrlBad":"Das ist keine Adresse, die der Browser \u00f6ffnen kann \u2014 f\u00fcr neue Tabs bleibt es bei {a}.",
"newTabUrlOk":"Neue Tabs \u00f6ffnen {a}",
"startUrl":"Wenn der Browser startet",
"startUrlHint":"Der erste Tab beim Start. Tabs vom letzten Mal kommen stattdessen zur\u00fcck.",
"startUrlStart":"Die Startseite",
"startUrlStartSub":"Uhr, Suchleiste und deine Schnelllinks.",
"startUrlCustom":"Eine Seite deiner Wahl",
"startUrlCustomSub":"Trag unten eine Adresse ein.",
"startUrlPh":"example.com",
"startUrlAsk":"Trag eine Adresse ein und dr\u00fcck Speichern \u2014 bis dahin startet der Browser mit der Startseite.",
"startUrlBad":"Das ist keine Adresse, die der Browser \u00f6ffnen kann \u2014 beim Start bleibt es bei {a}.",
"startUrlOk":"Der Browser startet mit {a}",
"theStartPage":"der Startseite",
"setDrawFailed":"Ein Teil dieser Seite konnte nicht gezeichnet werden ({}). Der Rest ist da.",
"homePage":"Startseite",
"restartLater":"Gilt f\u00fcr Seiten, die du ab jetzt \u00f6ffnest.",
"pwManage":"Passwortverwaltung","pwManageHint":"Logins, sichere Notizen, Karten und Identit\u00e4ten \u2014 mit Generator, Zwei-Faktor-Codes und Sicherheitspr\u00fcfung.","pwOpenManager":"Passwortverwaltung \u00f6ffnen","pwSearchPh":"Alles durchsuchen\u2026","pwNew":"Neu","pwNewLogin":"Login","pwNewNote":"Sichere Notiz","pwNewCard":"Zahlungskarte","pwNewIdentity":"Identit\u00e4t","pwAll":"Alle","pwLogins":"Logins","pwNotes":"Notizen","pwCards":"Karten","pwIdentities":"Identit\u00e4ten","pwFavs":"Favoriten","pwFav":"Favorit","pwSort":"Sortierung","pwSortName":"Name","pwSortUsed":"Zuletzt benutzt","pwSortChanged":"Zuletzt ge\u00e4ndert","pwNoMatch":"Daf\u00fcr gibt es keinen Treffer.","pwTitle":"Name","pwNote":"Notiz","pwTags":"Schlagw\u00f6rter","pwTagsPh":"Arbeit, Bank","pwFilterTag":"Schlagwort","pwAllTags":"Alle Schlagw\u00f6rter","pwDelete":"L\u00f6schen","pwDeleteAsk":"\u201e{}\u201c endg\u00fcltig l\u00f6schen?","pwCancel":"Abbrechen","pwReveal":"Anzeigen","pwRevealAsk":"Das hier auf dem Bildschirm anzeigen?","pwCopyUser":"Benutzernamen kopieren","pwCopyPass":"Passwort kopieren","pwCopyCode":"Code kopieren","pwOpenSite":"Seite \u00f6ffnen","pwGen":"Erzeugen","pwGenTitle":"Passwortgenerator","pwGenLength":"L\u00e4nge","pwGenSymbols":"Sonderzeichen","pwGenDigits":"Ziffern","pwGenUpper":"Gro\u00dfbuchstaben","pwGenAmbig":"Verwechselbare zulassen (l 1 I O 0)","pwGenUse":"Das hier nehmen","pwGenAgain":"Nochmal","pw2fa":"Zwei-Faktor-Code","pw2faSecret":"Zwei-Faktor-Geheimnis","pw2faPh":"otpauth://\u2026 oder das Base32-Geheimnis","pw2faBad":"Das ist kein brauchbares Zwei-Faktor-Geheimnis.","pw2faOk":"Zwei-Faktor-Geheimnis \u00fcbernommen \u2713","pw2faNone":"Kein Zwei-Faktor-Code hinterlegt.","pwHealth":"Sicherheit","pwReused":"Mehrfach benutzt","pwWeak":"Schwach","pwOld":"Nie ge\u00e4ndert","pwHealthy":"Nichts zu tun \u2713","pwReusedHint":"Auf mehreren Seiten benutzt \u2014 ein Einbruch \u00f6ffnet alle.","pwWeakHint":"Zu kurz oder zu einfach.","pwOldHint":"Seit \u00fcber einem Jahr unver\u00e4ndert.","pwStrength":"St\u00e4rke","pwStrengthWeak":"schwach","pwStrengthFair":"mittel","pwStrengthStrong":"stark","pwImport":"Importieren\u2026","pwExport":"Exportieren\u2026","pwImportDone":"Importiert: {a} neu, {b} aktualisiert, {c} \u00fcbersprungen.","pwImportFailed":"Aus dieser Datei war nichts zu lesen.","pwExportWarnT":"Das schreibt alle Passw\u00f6rter im Klartext.","pwExportWarnB":"Die Datei enth\u00e4lt alle {} Logins mit Passw\u00f6rtern, Notizen und Zwei-Faktor-Geheimnissen, lesbar f\u00fcr jeden, der sie \u00f6ffnet. Nichts darin ist verschl\u00fcsselt, verschleiert oder sonst gesch\u00fctzt. L\u00f6sche sie, sobald du sie nicht mehr brauchst.","pwExportGo":"Klartextdatei schreiben","pwExportDone":"Geschrieben nach {}","pwAllFiles":"Alle Dateien","pwNeverEmpty":"Nichts auf der Nie-speichern-Liste.","pwCardNumber":"Kartennummer","pwCardHolder":"Name auf der Karte","pwCardExpiry":"G\u00fcltig bis","pwCardCvv":"Pr\u00fcfnummer","pwCardBrand":"Kartenart","pwIdName":"Vollst\u00e4ndiger Name","pwIdEmail":"E-Mail","pwIdPhone":"Telefon","pwIdStreet":"Stra\u00dfe","pwIdCity":"Ort","pwIdZip":"Postleitzahl","pwIdCountry":"Land","pwNoteBody":"Inhalt der Notiz","pwUnnamed":"Ohne Namen","pwChanged":"Ge\u00e4ndert","pwCreated":"Hinzugef\u00fcgt","pwUsed":"Zuletzt benutzt","pwNeverUsed":"nie","pwLeaveBlank":"Leer lassen, um das gespeicherte Passwort zu behalten","pwCount":"{} Eintr\u00e4ge","pwSaved":"Gespeichert \u2713","pwEmptyTitle":"Noch nichts gespeichert","pwEmptyBody":"Melde dich irgendwo an, dann bietet der Browser an, es zu merken \u2014 oder trage hier selbst etwas ein.","pwPickHint":"W\u00e4hle links etwas aus, um es zu sehen.","pwGenCopied":"Ein neues Passwort liegt in der Zwischenablage \u2713","pwStore":"Wo die Geheimnisse liegen","pwStoreFile":"Dieser Computer","pwStore1p":"1Password","pwOpToken":"1Password-Token","pwOpTokenAsk":"F\u00fcge das Service-Account-Token ein. Es liegt in einer Datei, die nur du lesen kannst, wird nie wieder angezeigt und verl\u00e4sst diesen Computer nur Richtung 1Password.","pwOpVault":"Tresorname","pwOpVaultHint":"Der Tresor, in den der Service-Account darf.","pwOpNoBinary":"Das 1Password-Kommandozeilenprogramm (op) ist nicht installiert.","pwOpNoToken":"Noch kein Service-Account-Token.","pwOpFailed":"1Password hat nicht geantwortet: {}","pwSetToken":"Token setzen\u2026","pwTokenSet":"Token gespeichert \u2713","pwFellBack":"Es wird der Tresor auf diesem Computer benutzt \u2014 {}","pwHealthNA":"Die Sicherheitspr\u00fcfung braucht die Passw\u00f6rter selbst, und dieser Speicher gibt sie nicht heraus.","pwSwitch":"Diesen nehmen","pwActive":"In Benutzung","pwFetching":"Wird geholt\u2026","pwExportNA":"Exportieren geht nur aus dem Tresor auf diesem Computer. 1Password gibt die Passw\u00f6rter nicht heraus, die Datei h\u00e4tte also bei jedem Login eine leere Passwortspalte \u2014 etwas, das wie eine Sicherung aussieht und keine ist.","pwOpBadToken":"Die Token-Datei ist nicht lesbar \u2014 f\u00fcge das Token noch einmal ein.","pwStoreChecking":"{} wird erreicht\u2026","pwGenHint":"Ein neues gebraucht? Strg+Umschalt+G legt ein starkes Passwort in die Zwischenablage.","pwSaveFailed":"Nicht gespeichert \u2014 der Speicher hat es nicht angenommen.","pwDeleteFailed":"Nicht gel\u00f6scht \u2014 es liegt noch im Speicher.","pwFetchFailed":"Das war aus dem Speicher nicht zu holen.","pwNothingThere":"In diesem Feld ist nichts hinterlegt.","pwImporting":"Wird importiert\u2026","pwDenied":"Diese Seite ist veraltet","pwDeniedBody":"\u00d6ffne die Passwortverwaltung noch einmal \u00fcber das Men\u00fc. Der Schl\u00fcssel dieser Seite stammt aus einem fr\u00fcheren Start des Browsers, deshalb wurde nichts herausgegeben.","pwSiteDead":"Kein Hostname \u2014 dieser Login wird nirgends ausgef\u00fcllt.","pwStoreHint":"Umschalten verschiebt und kopiert nichts \u2014 jeder Speicher beh\u00e4lt, was er schon hatte.","pwVaultNewer":"Diese Passw\u00f6rter wurden von einer neueren Version des Browsers gespeichert, und diese hier kann sie nicht lesen. Es ist nichts ge\u00e4ndert und nichts verloren \u2014 \u00f6ffne sie mit der neueren Version. Bis dahin kann hier nichts angezeigt oder gespeichert werden.","acctPickTitle":"Welches Konto?","acctPickBody":"F\u00fcr {} ist mehr als ein Login gespeichert. W\u00e4hle das Konto, mit dem du dich anmelden willst \u2014 vorher wird nichts ausgef\u00fcllt, und die Seite erf\u00e4hrt nie, was auf dieser Liste steht.","acctPickNoName":"(kein Benutzername gespeichert)","acctPickCancel":"Jetzt nicht","acctPickTip":"W\u00e4hlen, mit welchem gespeicherten Konto sich der Browser hier anmeldet","acctPickNone":"F\u00fcr diese Seite ist nur ein Login gespeichert.",
"toolbar":"Werkzeugleiste","descToolbar":"Welche Kn\u00f6pfe oben stehen und in welcher Reihenfolge.","tbHint":"Ein Rechtsklick auf die Leiste selbst zeigt dieselbe Liste.","cardRendering":"Wie Seiten gezeichnet werden","cardSize":"Gr\u00f6\u00dfe","cardKept":"Was gespeichert bleibt","cardInstalled":"Installiert","tbShown":"Auf der Leiste","tbHidden":"Nicht zu sehen","tbElsewhere":"Woanders im Rahmen","tbElsewhereHint":"Die bleiben, wo sie sind \u2014 wegnehmen geht, verschieben nicht.","tbFixed":"Immer da","tbFixedWhy":"Der bleibt. Verschieben geht, wegnehmen nicht.","tbMoveUp":"Weiter nach vorn auf der Leiste","tbMoveDown":"Weiter nach hinten auf der Leiste","tbFixedHint":"Zur\u00fcck, vor, neu laden und die Adressleiste bleiben. Ein Browser ohne Weg zur\u00fcck ist kaputt.","tbShortcutHint":"Einen Knopf wegnehmen r\u00fchrt sein Tastenk\u00fcrzel nicht an \u2014 Strg+P druckt weiterhin.","tbReset":"Zur\u00fcck zur \u00fcblichen Auswahl","tbCustomize":"Werkzeugleiste anpassen\u2026","tbBack":"Zur\u00fcck","tbForward":"Vorw\u00e4rts","tbReload":"Neu laden","tbHome":"Startseite","tbNewTab":"Neuer Tab","tbAddress":"Adressleiste","tbFind":"Auf der Seite suchen","tbHistory":"Verlauf","tbDownloads":"Downloads","tbBookmarks":"Lesezeichen","tbPasswords":"Passw\u00f6rter","tbProxy":"Proxy","tbPrint":"Drucken","tbTranslate":"\u00dcbersetzen","tbSettings":"Einstellungen","tbFullscreen":"Vollbild","tbStar":"Lesezeichenstern","tbGroups":"Tab-Gruppen","tbFavorites":"Favoriten",
"privateTab":"Privat","privateNew":"Neuer privater Tab",
"privateTip":"Privater Tab \u2014 nichts bleibt zur\u00fcck, wenn er zugeht",
"masterPw":"Hauptpasswort","masterPwName":"Den Tresor mit einem Hauptpasswort abschlie\u00dfen","masterPwHint":"Der Schl\u00fcssel zu deinen gespeicherten Passw\u00f6rtern wird aus einem Kennwort berechnet, das du eintippst, statt in einer Datei daneben zu liegen. Solange du nicht aufschlie\u00dft, kann sie auf diesem Computer nichts lesen \u2014 weder der Browser noch irgendwer, der dein Benutzerkonto benutzt.","masterWarnT":"Wenn du es vergisst, sind deine Passw\u00f6rter weg.","masterWarnB":"Ein Hauptpasswort l\u00e4sst sich nicht zur\u00fccksetzen und nicht umgehen. Niemand kann es wiederherstellen \u2014 du nicht, dieser Browser nicht, und auch nicht, wer ihn geschrieben hat. Die Passw\u00f6rter bleiben auf diesem Computer und bleiben f\u00fcr immer unlesbar. Exportiere sie vorher, wenn du einen Weg zur\u00fcck willst, und bewahre diese Datei sicher auf.","masterSetT":"Hauptpasswort festlegen","masterSetGo":"Einschalten","masterNewPh":"Hauptpasswort","masterAgainPh":"Noch einmal eingeben","masterPassPh":"Hauptpasswort","masterCurrentPh":"Aktuelles Hauptpasswort","masterMinHint":"Mindestens 8 Zeichen. Ein paar zusammenhanglose W\u00f6rter, die du nicht vergisst, sind besser als etwas Kurzes mit Sonderzeichen.","masterMismatch":"Die beiden stimmen nicht \u00fcberein.","masterShort":"Zu kurz \u2014 mindestens 8 Zeichen.","masterExportFirst":"Passw\u00f6rter vorher exportieren\u2026","masterUnlockT":"Passw\u00f6rter aufschlie\u00dfen","masterUnlockAsk":"Gib dein Hauptpasswort ein, um den Tresor aufzuschlie\u00dfen.","masterUnlockGo":"Aufschlie\u00dfen","masterWrong":"Das war es nicht.","masterChangeT":"Hauptpasswort \u00e4ndern","masterChangeAsk":"An deinen gespeicherten Passw\u00f6rtern \u00e4ndert sich nichts \u2014 nur am Schl\u00fcssel.","masterChangeGo":"\u00c4ndern","masterChangeDone":"Hauptpasswort ge\u00e4ndert \u2713","masterOnDone":"Der Tresor ist mit deinem Hauptpasswort abgeschlossen \u2713","masterOffT":"Hauptpasswort ausschalten?","masterOffB":"Deine Passw\u00f6rter bleiben alle genau da, wo sie sind. Aber der Schl\u00fcssel liegt dann wieder in einer Datei daneben, und jeder, der dieses Computerkonto benutzen kann, kann sie wieder lesen.","masterOffDone":"Hauptpasswort entfernt","masterFailed":"Das hat nicht geklappt \u2014 es wurde nichts ge\u00e4ndert.","masterLockNow":"Jetzt abschlie\u00dfen","masterChangeBtn":"Hauptpasswort \u00e4ndern\u2026","masterAuto":"Wieder abschlie\u00dfen nach","masterAutoHint":"Passiert so lange nichts, schlie\u00dft sich der Tresor von selbst und fragt wieder.","masterAutoNever":"Nie","masterMinutes":"{} Minuten","masterHour":"1 Stunde","masterOn":"An \u2014 aufgeschlossen","masterShut":"An \u2014 abgeschlossen","masterOffState":"Aus","masterLockedTitle":"Der Tresor ist abgeschlossen","masterLockedBody":"Deine gespeicherten Passw\u00f6rter sind unlesbar, bis du dein Hauptpasswort eingibst.","masterUnlockBtn":"Aufschlie\u00dfen\u2026","masterLockedLine":"Abgeschlossen \u2014 schlie\u00dfe die Passwortverwaltung auf, um zu sehen, was gespeichert ist.","masterEncHint":"Auf diesem Computer mit deinem Hauptpasswort verschl\u00fcsselt. Solange abgeschlossen ist, kann sie hier nichts lesen.",
"privatePermHint":"Nur in diesem privaten Tab."},
"fr": {"settings":"Param\u00e8tres","search":"Recherche","searchEngine":"Moteur de recherche",
"appearance":"Apparence","whiteGoogle":"Google blanc",
"whiteGoogleHint":"D\u00e9sactiv\u00e9 = Google noir",
"autoDarken":"Assombrir les sites clairs","pageZoom":"Zoom de page",
"browsing":"Navigation","reopenTabs":"Rouvrir les onglets pr\u00e9c\u00e9dents",
"askDownload":"Demander o\u00f9 enregistrer chaque fichier","translation":"Langue",
"translateInto":"Langue du navigateur et de traduction",
"translateHint":"Change cette page, la page d'accueil, Google et le bouton de traduction.",
"privacy":"Confidentialit\u00e9","saveHistory":"Enregistrer l'historique",
"viewHistory":"Voir l'historique","clearHistory":"Effacer l'historique",
"clearCookies":"Effacer les cookies",
"cookiesHint":"Effacer les cookies d\u00e9connecte ce navigateur virtuel partout.",
"updates":"Mises \u00e0 jour","checkUpdates":"Rechercher des mises \u00e0 jour",
"setupT":"Configuration","runSetup":"Relancer la configuration",
"setupHint":"D\u00e9placez la barre, choisissez un fond",
"filterPh":"Rechercher\u2026","add":"Ajouter","background":"Fond d'\u00e9cran",
"allSettings":"Tous les param\u00e8tres","searchSite":"Rechercher sur {}",
"wizWelcome":"Bienvenue ! Configurons tout \u00e7a",
"wizDrag":"Saisissez la barre de recherche et placez-la o\u00f9 vous voulez.",
"center":"Recentrer","nextBtn":"Suivant \u2192","wallpaper":"Fond d'\u00e9cran",
"pickWallpaper":"Choisissez un fond pour votre page d'accueil.","finish":"Terminer",
"history":"Historique","searchHistory":"Rechercher dans l'historique",
"clearAll":"Tout effacer","noHistory":"Aucun historique.","today":"Aujourd'hui",
"yesterday":"Hier"},
"es": {"settings":"Ajustes","search":"B\u00fasqueda","searchEngine":"Buscador",
"appearance":"Apariencia","whiteGoogle":"Google blanco",
"whiteGoogleHint":"Apagado = Google negro","autoDarken":"Oscurecer sitios claros",
"pageZoom":"Zoom de p\u00e1gina","browsing":"Navegaci\u00f3n",
"reopenTabs":"Reabrir pesta\u00f1as anteriores",
"askDownload":"Preguntar d\u00f3nde guardar cada descarga","translation":"Idioma",
"translateInto":"Idioma del navegador y de traducci\u00f3n",
"translateHint":"Cambia esta p\u00e1gina, la p\u00e1gina de inicio, Google y el bot\u00f3n de traducir.",
"privacy":"Privacidad","saveHistory":"Guardar historial",
"viewHistory":"Ver historial","clearHistory":"Borrar historial",
"clearCookies":"Borrar cookies",
"cookiesHint":"Borrar cookies cierra la sesi\u00f3n de este navegador virtual en todas partes.",
"updates":"Actualizaciones","checkUpdates":"Buscar actualizaciones",
"setupT":"Configuraci\u00f3n","runSetup":"Repetir configuraci\u00f3n",
"setupHint":"Arrastra la barra, elige un fondo","filterPh":"Buscar\u2026",
"add":"A\u00f1adir","background":"Fondo","allSettings":"Todos los ajustes",
"searchSite":"Buscar en {}","wizWelcome":"\u00a1Bienvenido! Vamos a configurarlo",
"wizDrag":"Arrastra la barra de b\u00fasqueda a donde quieras.",
"center":"Centrar de nuevo","nextBtn":"Siguiente \u2192","wallpaper":"Fondo",
"pickWallpaper":"Elige un fondo para tu p\u00e1gina de inicio.","finish":"Listo",
"history":"Historial","searchHistory":"Buscar en el historial",
"clearAll":"Borrar todo","noHistory":"Sin historial.","today":"Hoy",
"yesterday":"Ayer"},
"it": {"settings":"Impostazioni","search":"Ricerca","searchEngine":"Motore di ricerca",
"appearance":"Aspetto","whiteGoogle":"Google bianco",
"whiteGoogleHint":"Spento = Google nero","autoDarken":"Scurisci i siti chiari",
"pageZoom":"Zoom pagina","browsing":"Navigazione",
"reopenTabs":"Riapri le schede precedenti",
"askDownload":"Chiedi dove salvare ogni download","translation":"Lingua",
"translateInto":"Lingua del browser e di traduzione",
"translateHint":"Cambia questa pagina, la pagina iniziale, Google e il pulsante traduci.",
"privacy":"Privacy","saveHistory":"Salva cronologia",
"viewHistory":"Vedi cronologia","clearHistory":"Cancella cronologia",
"clearCookies":"Cancella cookie",
"cookiesHint":"Cancellare i cookie disconnette questo browser virtuale ovunque.",
"updates":"Aggiornamenti","checkUpdates":"Cerca aggiornamenti",
"setupT":"Configurazione","runSetup":"Ripeti configurazione",
"setupHint":"Trascina la barra, scegli uno sfondo","filterPh":"Cerca\u2026",
"add":"Aggiungi","background":"Sfondo","allSettings":"Tutte le impostazioni",
"searchSite":"Cerca su {}","wizWelcome":"Benvenuto! Configuriamo tutto",
"wizDrag":"Trascina la barra di ricerca dove preferisci.",
"center":"Ricentra","nextBtn":"Avanti \u2192","wallpaper":"Sfondo",
"pickWallpaper":"Scegli uno sfondo per la pagina iniziale.","finish":"Fine",
"history":"Cronologia","searchHistory":"Cerca nella cronologia",
"clearAll":"Cancella tutto","noHistory":"Nessuna cronologia.","today":"Oggi",
"yesterday":"Ieri"},
"pt": {"settings":"Configura\u00e7\u00f5es","search":"Pesquisa","searchEngine":"Motor de busca",
"appearance":"Apar\u00eancia","whiteGoogle":"Google branco",
"whiteGoogleHint":"Desligado = Google preto","autoDarken":"Escurecer sites claros",
"pageZoom":"Zoom da p\u00e1gina","browsing":"Navega\u00e7\u00e3o",
"reopenTabs":"Reabrir abas da \u00faltima vez",
"askDownload":"Perguntar onde salvar cada download","translation":"Idioma",
"translateInto":"Idioma do navegador e de tradu\u00e7\u00e3o",
"translateHint":"Muda esta p\u00e1gina, a p\u00e1gina inicial, o Google e o bot\u00e3o de traduzir.",
"privacy":"Privacidade","saveHistory":"Salvar hist\u00f3rico",
"viewHistory":"Ver hist\u00f3rico","clearHistory":"Limpar hist\u00f3rico",
"clearCookies":"Limpar cookies",
"cookiesHint":"Limpar cookies desconecta este navegador virtual em todo lugar.",
"updates":"Atualiza\u00e7\u00f5es","checkUpdates":"Procurar atualiza\u00e7\u00f5es",
"setupT":"Configura\u00e7\u00e3o","runSetup":"Repetir configura\u00e7\u00e3o",
"setupHint":"Arraste a barra, escolha um fundo","filterPh":"Pesquisar\u2026",
"add":"Adicionar","background":"Plano de fundo","allSettings":"Todas as configura\u00e7\u00f5es",
"searchSite":"Pesquisar no {}","wizWelcome":"Bem-vindo! Vamos configurar",
"wizDrag":"Arraste a barra de pesquisa para onde quiser.",
"center":"Centralizar","nextBtn":"Avan\u00e7ar \u2192","wallpaper":"Plano de fundo",
"pickWallpaper":"Escolha um plano de fundo para sua p\u00e1gina inicial.","finish":"Concluir",
"history":"Hist\u00f3rico","searchHistory":"Pesquisar no hist\u00f3rico",
"clearAll":"Limpar tudo","noHistory":"Sem hist\u00f3rico.","today":"Hoje",
"yesterday":"Ontem"},
"nl": {"settings":"Instellingen","search":"Zoeken","searchEngine":"Zoekmachine",
"appearance":"Uiterlijk","whiteGoogle":"Wit Google",
"whiteGoogleHint":"Uit = pikzwart Google","autoDarken":"Lichte sites verdonkeren",
"pageZoom":"Paginazoom","browsing":"Browsen",
"reopenTabs":"Tabbladen van vorige keer heropenen",
"askDownload":"Vragen waar elke download wordt opgeslagen","translation":"Taal",
"translateInto":"Browser- en vertaaltaal",
"translateHint":"Verandert deze pagina, de startpagina, Google en de vertaalknop.",
"privacy":"Privacy","saveHistory":"Geschiedenis opslaan",
"viewHistory":"Geschiedenis bekijken","clearHistory":"Geschiedenis wissen",
"clearCookies":"Cookies wissen",
"cookiesHint":"Cookies wissen logt deze virtuele browser overal uit.",
"updates":"Updates","checkUpdates":"Zoeken naar updates","setupT":"Installatie",
"runSetup":"Installatie opnieuw","setupHint":"Sleep de zoekbalk, kies een achtergrond",
"filterPh":"Zoeken\u2026","add":"Toevoegen","background":"Achtergrond",
"allSettings":"Alle instellingen","searchSite":"Zoeken op {}",
"wizWelcome":"Welkom! Laten we alles instellen",
"wizDrag":"Sleep de zoekbalk naar waar je hem wilt hebben.",
"center":"Opnieuw centreren","nextBtn":"Volgende \u2192","wallpaper":"Achtergrond",
"pickWallpaper":"Kies een achtergrond voor je startpagina.","finish":"Klaar",
"history":"Geschiedenis","searchHistory":"Zoek in geschiedenis",
"clearAll":"Alles wissen","noHistory":"Geen geschiedenis.","today":"Vandaag",
"yesterday":"Gisteren"},
"pl": {"settings":"Ustawienia","search":"Szukanie","searchEngine":"Wyszukiwarka",
"appearance":"Wygl\u0105d","whiteGoogle":"Bia\u0142e Google",
"whiteGoogleHint":"Wy\u0142\u0105czone = czarne Google",
"autoDarken":"Przyciemniaj jasne strony","pageZoom":"Powi\u0119kszenie strony",
"browsing":"Przegl\u0105danie","reopenTabs":"Przywr\u00f3\u0107 karty z ostatniego razu",
"askDownload":"Pytaj, gdzie zapisa\u0107 ka\u017cdy plik","translation":"J\u0119zyk",
"translateInto":"J\u0119zyk przegl\u0105darki i t\u0142umaczenia",
"translateHint":"Zmienia t\u0119 stron\u0119, stron\u0119 startow\u0105, Google i przycisk t\u0142umaczenia.",
"privacy":"Prywatno\u015b\u0107","saveHistory":"Zapisuj histori\u0119",
"viewHistory":"Poka\u017c histori\u0119","clearHistory":"Wyczy\u015b\u0107 histori\u0119",
"clearCookies":"Wyczy\u015b\u0107 cookies",
"cookiesHint":"Wyczyszczenie cookies wylogowuje t\u0119 przegl\u0105dark\u0119 wsz\u0119dzie.",
"updates":"Aktualizacje","checkUpdates":"Sprawd\u017a aktualizacje",
"setupT":"Konfiguracja","runSetup":"Powt\u00f3rz konfiguracj\u0119",
"setupHint":"Przeci\u0105gnij pasek, wybierz tapet\u0119","filterPh":"Szukaj\u2026",
"add":"Dodaj","background":"T\u0142o","allSettings":"Wszystkie ustawienia",
"searchSite":"Szukaj w {}","wizWelcome":"Witaj! Skonfigurujmy wszystko",
"wizDrag":"Przeci\u0105gnij pasek wyszukiwania, gdzie chcesz.",
"center":"Wy\u015brodkuj","nextBtn":"Dalej \u2192","wallpaper":"Tapeta",
"pickWallpaper":"Wybierz tapet\u0119 strony startowej.","finish":"Gotowe",
"history":"Historia","searchHistory":"Szukaj w historii",
"clearAll":"Wyczy\u015b\u0107 wszystko","noHistory":"Brak historii.","today":"Dzisiaj",
"yesterday":"Wczoraj"},
"tr": {"settings":"Ayarlar","search":"Arama","searchEngine":"Arama motoru",
"appearance":"G\u00f6r\u00fcn\u00fcm","whiteGoogle":"Beyaz Google",
"whiteGoogleHint":"Kapal\u0131 = simsiyah Google",
"autoDarken":"A\u00e7\u0131k siteleri karart","pageZoom":"Sayfa yak\u0131nla\u015ft\u0131rma",
"browsing":"Gezinme","reopenTabs":"Son sekmeleri yeniden a\u00e7",
"askDownload":"Her indirmede nereye kaydedilece\u011fini sor","translation":"Dil",
"translateInto":"Taray\u0131c\u0131 ve \u00e7eviri dili",
"translateHint":"Bu sayfay\u0131, ba\u015flang\u0131\u00e7 sayfas\u0131n\u0131, Google'\u0131 ve \u00e7eviri d\u00fc\u011fmesini de\u011fi\u015ftirir.",
"privacy":"Gizlilik","saveHistory":"Ge\u00e7mi\u015fi kaydet",
"viewHistory":"Ge\u00e7mi\u015fi g\u00f6r","clearHistory":"Ge\u00e7mi\u015fi sil",
"clearCookies":"\u00c7erezleri sil",
"cookiesHint":"\u00c7erezleri silmek bu sanal taray\u0131c\u0131y\u0131 her yerden \u00e7\u0131k\u0131\u015f yapt\u0131r\u0131r.",
"updates":"G\u00fcncellemeler","checkUpdates":"G\u00fcncelleme ara","setupT":"Kurulum",
"runSetup":"Kurulumu tekrar \u00e7al\u0131\u015ft\u0131r",
"setupHint":"Arama \u00e7ubu\u011funu s\u00fcr\u00fckle, duvar ka\u011f\u0131d\u0131 se\u00e7",
"filterPh":"Ara\u2026","add":"Ekle","background":"Arka plan",
"allSettings":"T\u00fcm ayarlar","searchSite":"{} \u00fczerinde ara",
"wizWelcome":"Ho\u015f geldin! Her \u015feyi kural\u0131m",
"wizDrag":"Arama \u00e7ubu\u011funu istedi\u011fin yere s\u00fcr\u00fckle.",
"center":"Yeniden ortala","nextBtn":"\u0130leri \u2192","wallpaper":"Duvar ka\u011f\u0131d\u0131",
"pickWallpaper":"Ba\u015flang\u0131\u00e7 sayfan i\u00e7in duvar ka\u011f\u0131d\u0131 se\u00e7.",
"finish":"Bitti","history":"Ge\u00e7mi\u015f","searchHistory":"Ge\u00e7mi\u015fte ara",
"clearAll":"T\u00fcm\u00fcn\u00fc sil","noHistory":"Ge\u00e7mi\u015f yok.","today":"Bug\u00fcn",
"yesterday":"D\u00fcn"},
"ru": {"settings":"\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438","search":"\u041f\u043e\u0438\u0441\u043a",
"searchEngine":"\u041f\u043e\u0438\u0441\u043a\u043e\u0432\u0430\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430",
"appearance":"\u0412\u043d\u0435\u0448\u043d\u0438\u0439 \u0432\u0438\u0434",
"whiteGoogle":"\u0411\u0435\u043b\u044b\u0439 Google",
"whiteGoogleHint":"\u0412\u044b\u043a\u043b = \u0447\u0451\u0440\u043d\u044b\u0439 Google",
"autoDarken":"\u0417\u0430\u0442\u0435\u043c\u043d\u044f\u0442\u044c \u0441\u0432\u0435\u0442\u043b\u044b\u0435 \u0441\u0430\u0439\u0442\u044b",
"pageZoom":"\u041c\u0430\u0441\u0448\u0442\u0430\u0431 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b",
"browsing":"\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440",
"reopenTabs":"\u041e\u0442\u043a\u0440\u044b\u0432\u0430\u0442\u044c \u043f\u0440\u043e\u0448\u043b\u044b\u0435 \u0432\u043a\u043b\u0430\u0434\u043a\u0438",
"askDownload":"\u0421\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0442\u044c, \u043a\u0443\u0434\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c",
"translation":"\u042f\u0437\u044b\u043a",
"translateInto":"\u042f\u0437\u044b\u043a \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430 \u0438 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0430",
"translateHint":"\u041c\u0435\u043d\u044f\u0435\u0442 \u044d\u0442\u0443 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443, \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u0443\u044e, Google \u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0430.",
"privacy":"\u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
"saveHistory":"\u0421\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
"viewHistory":"\u0418\u0441\u0442\u043e\u0440\u0438\u044f",
"clearHistory":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
"clearCookies":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c cookies",
"cookiesHint":"\u041e\u0447\u0438\u0441\u0442\u043a\u0430 cookies \u0432\u044b\u0445\u043e\u0434\u0438\u0442 \u0438\u0437 \u0432\u0441\u0435\u0445 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u043e\u0432.",
"updates":"\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f",
"checkUpdates":"\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f",
"setupT":"\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430",
"runSetup":"\u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e",
"setupHint":"\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0441\u0442\u0440\u043e\u043a\u0443, \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043e\u0431\u043e\u0438",
"filterPh":"\u041f\u043e\u0438\u0441\u043a\u2026","add":"\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
"background":"\u0424\u043e\u043d","allSettings":"\u0412\u0441\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
"searchSite":"\u041f\u043e\u0438\u0441\u043a \u0432 {}",
"wizWelcome":"\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c!",
"wizDrag":"\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0441\u0442\u0440\u043e\u043a\u0443 \u043f\u043e\u0438\u0441\u043a\u0430 \u043a\u0443\u0434\u0430 \u0443\u0433\u043e\u0434\u043d\u043e.",
"center":"\u041f\u043e \u0446\u0435\u043d\u0442\u0440\u0443","nextBtn":"\u0414\u0430\u043b\u0435\u0435 \u2192",
"wallpaper":"\u041e\u0431\u043e\u0438",
"pickWallpaper":"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043e\u0431\u043e\u0438 \u0434\u043b\u044f \u0441\u0442\u0430\u0440\u0442\u043e\u0432\u043e\u0439.",
"finish":"\u0413\u043e\u0442\u043e\u0432\u043e","history":"\u0418\u0441\u0442\u043e\u0440\u0438\u044f",
"searchHistory":"\u041f\u043e\u0438\u0441\u043a \u0432 \u0438\u0441\u0442\u043e\u0440\u0438\u0438",
"clearAll":"\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0432\u0441\u0451",
"noHistory":"\u0418\u0441\u0442\u043e\u0440\u0438\u0438 \u043d\u0435\u0442.",
"today":"\u0421\u0435\u0433\u043e\u0434\u043d\u044f","yesterday":"\u0412\u0447\u0435\u0440\u0430"},
"ja": {"settings":"\u8a2d\u5b9a","search":"\u691c\u7d22","searchEngine":"\u691c\u7d22\u30a8\u30f3\u30b8\u30f3",
"appearance":"\u5916\u89b3","whiteGoogle":"\u767d\u3044Google",
"whiteGoogleHint":"\u30aa\u30d5 = \u771f\u3063\u9ed2\u306aGoogle",
"autoDarken":"\u660e\u308b\u3044\u30b5\u30a4\u30c8\u3092\u6697\u304f\u3059\u308b",
"pageZoom":"\u30da\u30fc\u30b8\u30ba\u30fc\u30e0","browsing":"\u30d6\u30e9\u30a6\u30b8\u30f3\u30b0",
"reopenTabs":"\u524d\u56de\u306e\u30bf\u30d6\u3092\u5fa9\u5143",
"askDownload":"\u4fdd\u5b58\u5148\u3092\u6bce\u56de\u78ba\u8a8d","translation":"\u8a00\u8a9e",
"translateInto":"\u30d6\u30e9\u30a6\u30b6\u3068\u7ffb\u8a33\u306e\u8a00\u8a9e",
"translateHint":"\u3053\u306e\u30da\u30fc\u30b8\u3001\u30b9\u30bf\u30fc\u30c8\u30da\u30fc\u30b8\u3001Google\u3001\u7ffb\u8a33\u30dc\u30bf\u30f3\u304c\u5909\u308f\u308a\u307e\u3059\u3002",
"privacy":"\u30d7\u30e9\u30a4\u30d0\u30b7\u30fc","saveHistory":"\u5c65\u6b74\u3092\u4fdd\u5b58",
"viewHistory":"\u5c65\u6b74\u3092\u898b\u308b","clearHistory":"\u5c65\u6b74\u3092\u6d88\u53bb",
"clearCookies":"Cookie\u3092\u6d88\u53bb",
"cookiesHint":"Cookie\u6d88\u53bb\u3067\u3053\u306e\u4eee\u60f3\u30d6\u30e9\u30a6\u30b6\u306f\u5168\u3066\u30ed\u30b0\u30a2\u30a6\u30c8\u3055\u308c\u307e\u3059\u3002",
"updates":"\u30a2\u30c3\u30d7\u30c7\u30fc\u30c8","checkUpdates":"\u66f4\u65b0\u3092\u78ba\u8a8d",
"setupT":"\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7","runSetup":"\u30bb\u30c3\u30c8\u30a2\u30c3\u30d7\u3092\u3084\u308a\u76f4\u3059",
"setupHint":"\u691c\u7d22\u30d0\u30fc\u3092\u52d5\u304b\u3057\u3001\u58c1\u7d19\u3092\u9078\u3076",
"filterPh":"\u691c\u7d22\u2026","add":"\u8ffd\u52a0","background":"\u80cc\u666f",
"allSettings":"\u3059\u3079\u3066\u306e\u8a2d\u5b9a","searchSite":"{}\u3067\u691c\u7d22",
"wizWelcome":"\u3088\u3046\u3053\u305d\uff01\u8a2d\u5b9a\u3057\u307e\u3057\u3087\u3046",
"wizDrag":"\u691c\u7d22\u30d0\u30fc\u3092\u597d\u304d\u306a\u5834\u6240\u306b\u30c9\u30e9\u30c3\u30b0\u3002",
"center":"\u4e2d\u592e\u306b\u623b\u3059","nextBtn":"\u6b21\u3078 \u2192","wallpaper":"\u58c1\u7d19",
"pickWallpaper":"\u30b9\u30bf\u30fc\u30c8\u30da\u30fc\u30b8\u306e\u58c1\u7d19\u3092\u9078\u3093\u3067\u304f\u3060\u3055\u3044\u3002",
"finish":"\u5b8c\u4e86","history":"\u5c65\u6b74","searchHistory":"\u5c65\u6b74\u3092\u691c\u7d22",
"clearAll":"\u3059\u3079\u3066\u6d88\u53bb","noHistory":"\u5c65\u6b74\u306a\u3057\u3002",
"today":"\u4eca\u65e5","yesterday":"\u6628\u65e5"},
"zh": {"settings":"\u8bbe\u7f6e","search":"\u641c\u7d22","searchEngine":"\u641c\u7d22\u5f15\u64ce",
"appearance":"\u5916\u89c2","whiteGoogle":"\u767d\u8272Google",
"whiteGoogleHint":"\u5173\u95ed = \u7eaf\u9ed1Google",
"autoDarken":"\u8c03\u6697\u6d45\u8272\u7f51\u7ad9","pageZoom":"\u9875\u9762\u7f29\u653e",
"browsing":"\u6d4f\u89c8","reopenTabs":"\u6062\u590d\u4e0a\u6b21\u7684\u6807\u7b7e\u9875",
"askDownload":"\u6bcf\u6b21\u4e0b\u8f7d\u65f6\u8be2\u95ee\u4fdd\u5b58\u4f4d\u7f6e",
"translation":"\u8bed\u8a00","translateInto":"\u6d4f\u89c8\u5668\u548c\u7ffb\u8bd1\u8bed\u8a00",
"translateHint":"\u66f4\u6539\u6b64\u9875\u3001\u8d77\u59cb\u9875\u3001Google\u548c\u7ffb\u8bd1\u6309\u94ae\u3002",
"privacy":"\u9690\u79c1","saveHistory":"\u4fdd\u5b58\u5386\u53f2\u8bb0\u5f55",
"viewHistory":"\u67e5\u770b\u5386\u53f2","clearHistory":"\u6e05\u9664\u5386\u53f2",
"clearCookies":"\u6e05\u9664Cookie",
"cookiesHint":"\u6e05\u9664Cookie\u5c06\u9000\u51fa\u6b64\u865a\u62df\u6d4f\u89c8\u5668\u7684\u6240\u6709\u767b\u5f55\u3002",
"updates":"\u66f4\u65b0","checkUpdates":"\u68c0\u67e5\u66f4\u65b0","setupT":"\u8bbe\u7f6e\u5411\u5bfc",
"runSetup":"\u91cd\u65b0\u8fd0\u884c\u8bbe\u7f6e","setupHint":"\u62d6\u52a8\u641c\u7d22\u680f\uff0c\u9009\u62e9\u58c1\u7eb8",
"filterPh":"\u641c\u7d22\u2026","add":"\u6dfb\u52a0","background":"\u80cc\u666f",
"allSettings":"\u6240\u6709\u8bbe\u7f6e","searchSite":"\u5728{}\u641c\u7d22",
"wizWelcome":"\u6b22\u8fce\uff01\u6765\u8bbe\u7f6e\u4e00\u4e0b",
"wizDrag":"\u628a\u641c\u7d22\u680f\u62d6\u5230\u4f60\u60f3\u8981\u7684\u4f4d\u7f6e\u3002",
"center":"\u91cd\u65b0\u5c45\u4e2d","nextBtn":"\u4e0b\u4e00\u6b65 \u2192","wallpaper":"\u58c1\u7eb8",
"pickWallpaper":"\u4e3a\u8d77\u59cb\u9875\u9009\u62e9\u58c1\u7eb8\u3002","finish":"\u5b8c\u6210",
"history":"\u5386\u53f2","searchHistory":"\u641c\u7d22\u5386\u53f2",
"clearAll":"\u6e05\u9664\u5168\u90e8","noHistory":"\u6ca1\u6709\u5386\u53f2\u8bb0\u5f55\u3002",
"today":"\u4eca\u5929","yesterday":"\u6628\u5929"},
}

# built-in starter plugins (id -> (name, description, userscript source)).
# kept simple and self-contained — no Tampermonkey GM_* APIs, which the
# engine does not provide
STARTER_PLUGINS = {
    "yt-skip-ads": ("Skip YouTube ads",
        "Auto-clicks the skip button and speeds through unskippable ads.",
        """// ==UserScript==
// @name Skip YouTube ads
// @match *://*.youtube.com/*
// ==/UserScript==
setInterval(function () {
  var b = document.querySelector('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button');
  if (b) b.click();
  var ad = document.querySelector('.ad-showing');
  var v = document.querySelector('video');
  if (ad && v && v.duration) { v.currentTime = v.duration; v.muted = true; }
}, 500);
"""),
    "yt-hide-shorts": ("Hide YouTube Shorts",
        "Removes Shorts shelves and the sidebar entry.",
        """// ==UserScript==
// @name Hide YouTube Shorts
// @match *://*.youtube.com/*
// ==/UserScript==
var css = document.createElement('style');
css.textContent =
  'ytd-reel-shelf-renderer, ytd-rich-shelf-renderer[is-shorts],' +
  'ytd-guide-entry-renderer:has(a[title="Shorts"]),' +
  'ytd-mini-guide-entry-renderer[aria-label="Shorts"] { display: none !important; }';
document.documentElement.appendChild(css);
"""),
    "cookie-away": ("Dismiss cookie banners",
        "Clicks away common cookie-consent popups automatically.",
        """// ==UserScript==
// @name Dismiss cookie banners
// @match *://*/*
// ==/UserScript==
setInterval(function () {
  var sels = ['#onetrust-accept-btn-handler','button[aria-label*="ccept"]',
    'button[title*="ccept"]','.fc-cta-consent','[data-testid="accept-button"]'];
  for (var i = 0; i < sels.length; i++) {
    var b = document.querySelector(sels[i]);
    if (b) { b.click(); break; }
  }
}, 1000);
"""),
    "text-select": ("Allow text selection",
        "Re-enables copying and selecting on sites that block it.",
        """// ==UserScript==
// @name Allow text selection
// @match *://*/*
// ==/UserScript==
var s = document.createElement('style');
s.textContent = '* { user-select: text !important; -webkit-user-select: text !important; }';
document.documentElement.appendChild(s);
document.addEventListener('copy', function (e) { e.stopPropagation(); }, true);
document.addEventListener('contextmenu', function (e) { e.stopPropagation(); }, true);
"""),
}

# english search aliases for the language menu
LANGUAGE_ALIASES = {
    "af": "afrikaans", "sq": "albanian", "am": "amharic", "ar": "arabic",
    "hy": "armenian", "az": "azerbaijani", "eu": "basque", "be": "belarusian",
    "bn": "bengali", "bs": "bosnian", "bg": "bulgarian", "ca": "catalan",
    "ceb": "cebuano", "zh-CN": "chinese simplified", "zh-TW": "chinese traditional",
    "co": "corsican", "hr": "croatian", "cs": "czech", "da": "danish",
    "nl": "dutch", "en": "english", "eo": "esperanto", "et": "estonian",
    "fi": "finnish", "fr": "french", "fy": "frisian", "gl": "galician",
    "ka": "georgian", "de": "german", "el": "greek", "gu": "gujarati",
    "ht": "haitian creole", "ha": "hausa", "haw": "hawaiian", "he": "hebrew",
    "hi": "hindi", "hmn": "hmong", "hu": "hungarian", "is": "icelandic",
    "ig": "igbo", "id": "indonesian", "ga": "irish", "it": "italian",
    "ja": "japanese", "jv": "javanese", "kn": "kannada", "kk": "kazakh",
    "km": "khmer", "rw": "kinyarwanda", "ko": "korean", "ku": "kurdish",
    "ky": "kyrgyz", "lo": "lao", "la": "latin", "lv": "latvian",
    "lt": "lithuanian", "lb": "luxembourgish", "mk": "macedonian",
    "mg": "malagasy", "ms": "malay", "ml": "malayalam", "mt": "maltese",
    "mi": "maori", "mr": "marathi", "mn": "mongolian", "my": "burmese",
    "ne": "nepali", "no": "norwegian", "ny": "chichewa", "or": "odia",
    "ps": "pashto", "fa": "persian farsi", "pl": "polish", "pt": "portuguese",
    "pa": "punjabi", "ro": "romanian", "ru": "russian", "sm": "samoan",
    "gd": "scots gaelic", "sr": "serbian", "st": "sesotho", "sn": "shona",
    "sd": "sindhi", "si": "sinhala", "sk": "slovak", "sl": "slovenian",
    "so": "somali", "es": "spanish", "su": "sundanese", "sw": "swahili",
    "sv": "swedish", "tl": "filipino tagalog", "tg": "tajik", "ta": "tamil",
    "tt": "tatar", "te": "telugu", "th": "thai", "tr": "turkish",
    "tk": "turkmen", "uk": "ukrainian", "ur": "urdu", "ug": "uyghur",
    "uz": "uzbek", "vi": "vietnamese", "cy": "welsh", "xh": "xhosa",
    "yi": "yiddish", "yo": "yoruba", "zu": "zulu",
}

# every language Google Translate speaks (code, native name)
LANGUAGES = [
    ("af", "Afrikaans"), ("sq", "Shqip"), ("am", "አማርኛ"), ("ar", "العربية"),
    ("hy", "Հայերեն"), ("az", "Azərbaycan"), ("eu", "Euskara"),
    ("be", "Беларуская"), ("bn", "বাংলা"), ("bs", "Bosanski"),
    ("bg", "Български"), ("ca", "Català"), ("ceb", "Cebuano"),
    ("zh-CN", "中文(简体)"), ("zh-TW", "中文(繁體)"), ("co", "Corsu"),
    ("hr", "Hrvatski"), ("cs", "Čeština"), ("da", "Dansk"),
    ("nl", "Nederlands"), ("en", "English"), ("eo", "Esperanto"),
    ("et", "Eesti"), ("fi", "Suomi"), ("fr", "Français"), ("fy", "Frysk"),
    ("gl", "Galego"), ("ka", "ქართული"), ("de", "Deutsch"),
    ("el", "Ελληνικά"), ("gu", "ગુજરાતી"), ("ht", "Kreyòl"),
    ("ha", "Hausa"), ("haw", "ʻŌlelo Hawaiʻi"), ("he", "עברית"),
    ("hi", "हिन्दी"), ("hmn", "Hmong"), ("hu", "Magyar"),
    ("is", "Íslenska"), ("ig", "Igbo"), ("id", "Indonesia"),
    ("ga", "Gaeilge"), ("it", "Italiano"), ("ja", "日本語"),
    ("jv", "Basa Jawa"), ("kn", "ಕನ್ನಡ"), ("kk", "Қазақ"),
    ("km", "ខ្មែរ"), ("rw", "Kinyarwanda"), ("ko", "한국어"),
    ("ku", "Kurdî"), ("ky", "Кыргызча"), ("lo", "ລາວ"),
    ("la", "Latina"), ("lv", "Latviešu"), ("lt", "Lietuvių"),
    ("lb", "Lëtzebuergesch"), ("mk", "Македонски"), ("mg", "Malagasy"),
    ("ms", "Melayu"), ("ml", "മലയാളം"), ("mt", "Malti"),
    ("mi", "Māori"), ("mr", "मराठी"), ("mn", "Монгол"),
    ("my", "မြန်မာ"), ("ne", "नेपाली"), ("no", "Norsk"),
    ("ny", "Chichewa"), ("or", "ଓଡ଼ିଆ"), ("ps", "پښتو"),
    ("fa", "فارسی"), ("pl", "Polski"), ("pt", "Português"),
    ("pa", "ਪੰਜਾਬੀ"), ("ro", "Română"), ("ru", "Русский"),
    ("sm", "Sāmoa"), ("gd", "Gàidhlig"), ("sr", "Српски"),
    ("st", "Sesotho"), ("sn", "Shona"), ("sd", "سنڌي"),
    ("si", "සිංහල"), ("sk", "Slovenčina"), ("sl", "Slovenščina"),
    ("so", "Soomaali"), ("es", "Español"), ("su", "Basa Sunda"),
    ("sw", "Kiswahili"), ("sv", "Svenska"), ("tl", "Filipino"),
    ("tg", "Тоҷикӣ"), ("ta", "தமிழ்"), ("tt", "Татар"),
    ("te", "తెలుగు"), ("th", "ไทย"), ("tr", "Türkçe"),
    ("tk", "Türkmen"), ("uk", "Українська"), ("ur", "اردو"),
    ("ug", "ئۇيغۇرچە"), ("uz", "Oʻzbek"), ("vi", "Tiếng Việt"),
    ("cy", "Cymraeg"), ("xh", "isiXhosa"), ("yi", "ייִדיש"),
    ("yo", "Yorùbá"), ("zu", "isiZulu"),
]

# domain guesses for the address bar ("wiki" -> wikipedia.org);
# visited sites are remembered and suggested too
COMMON_SITES = [
    "wikipedia.org", "youtube.com", "github.com", "google.com",
    "reddit.com", "amazon.de", "ebay.de", "netflix.com", "spotify.com",
    "twitch.tv", "instagram.com", "tiktok.com", "discord.com",
    "translate.google.com", "maps.google.com", "web.de", "gmx.net",
]

# Every button in the chrome he is allowed to show, hide or move, in
# the order they come back in when he asks for the default set. Adding
# one here is all it takes: the settings page, the right-click menu and
# the saved list all read this and nothing else.
#
#   place  "bar"  the row with the address bar - the only place where
#                 order means anything
#          "url"  inside the address bar, pinned to its right edge
#          "tabs" the corner of the tab strip
#   fixed  a button the browser will not let him lose. A browser with
#          no way back, no way to reload and nowhere to type an address
#          is not a browser any more.
#   on     in the default set. Today's toolbar, exactly, so nobody's
#          chrome moves on upgrade.
#   act    the method it calls. "" for the address bar, which is not a
#          button at all but does take part in the order.
TOOLBAR_ITEMS = [
    {"name": "back", "glyph": "\u2039", "place": "bar", "fixed": True,
     "on": True, "act": "_tb_back", "str": "tbBack", "key": ""},
    {"name": "forward", "glyph": "\u203a", "place": "bar", "fixed": True,
     "on": True, "act": "_tb_forward", "str": "tbForward", "key": ""},
    {"name": "reload", "glyph": "\u27f3", "place": "bar", "fixed": True,
     "on": True, "act": "_tb_reload", "str": "tbReload", "key": "Ctrl+R"},
    {"name": "home", "glyph": "\u2302", "place": "bar", "fixed": False,
     "on": True, "act": "go_home", "str": "tbHome", "key": "Alt+Home"},
    {"name": "newtab", "glyph": "+", "place": "bar", "fixed": False,
     "on": False, "act": "_tb_newtab", "str": "tbNewTab", "key": "Ctrl+T"},
    {"name": "address", "glyph": "", "place": "bar", "fixed": True,
     "on": True, "act": "", "str": "tbAddress", "key": "Ctrl+L"},
    {"name": "favorites", "glyph": "\U0001f4c1", "place": "bar",
     "fixed": False, "on": True, "act": "toggle_favorites",
     "str": "tbFavorites", "key": "Ctrl+Shift+F"},
    {"name": "find", "glyph": "\u2315", "place": "bar", "fixed": False,
     "on": False, "act": "open_find", "str": "tbFind", "key": "Ctrl+F"},
    {"name": "history", "glyph": "\U0001f558", "place": "bar",
     "fixed": False, "on": False, "act": "toggle_history",
     "str": "tbHistory", "key": "Ctrl+H"},
    {"name": "downloads", "glyph": "\u2913", "place": "bar", "fixed": False,
     "on": False, "act": "toggle_downloads", "str": "tbDownloads",
     "key": "Ctrl+J"},
    {"name": "bookmarks", "glyph": "\U0001f4da", "place": "bar",
     "fixed": False, "on": False, "act": "toggle_bookmarks",
     "str": "tbBookmarks", "key": "Ctrl+Shift+O"},
    {"name": "passwords", "glyph": "\U0001f511", "place": "bar",
     "fixed": False, "on": False, "act": "toggle_passwords",
     "str": "tbPasswords", "key": "Ctrl+Shift+P"},
    {"name": "proxy", "glyph": "\U0001f4e1", "place": "bar", "fixed": False,
     "on": True, "act": "_proxy_menu", "str": "tbProxy", "key": ""},
    {"name": "print", "glyph": "\U0001f5a8", "place": "bar", "fixed": False,
     "on": True, "act": "print_page", "str": "tbPrint", "key": "Ctrl+P"},
    {"name": "translate", "glyph": "\U0001f310", "place": "bar",
     "fixed": False, "on": True, "act": "_translate_menu",
     "str": "tbTranslate", "key": ""},
    {"name": "settings", "glyph": "\u2699", "place": "bar", "fixed": False,
     "on": False, "act": "toggle_settings", "str": "tbSettings",
     "key": "Ctrl+,"},
    {"name": "fullscreen", "glyph": "\u26f6", "place": "bar", "fixed": False,
     "on": False, "act": "_tb_fullscreen", "str": "tbFullscreen",
     "key": "F11"},
    {"name": "star", "glyph": "\u2606", "place": "url", "fixed": False,
     "on": True, "act": "toggle_bookmark", "str": "tbStar", "key": "Ctrl+D"},
    {"name": "tabgroups", "glyph": "\U0001f4d1", "place": "tabs",
     "fixed": False, "on": True, "act": "_group_menu", "str": "tbGroups",
     "key": ""},
]
TOOLBAR_BY_NAME = {i["name"]: i for i in TOOLBAR_ITEMS}
TOOLBAR_ORDER = [i["name"] for i in TOOLBAR_ITEMS]
TOOLBAR_DEFAULT = [i["name"] for i in TOOLBAR_ITEMS if i["on"]]

STYLE = """
* { font-family: "JetBrainsMono Nerd Font", "Inter", sans-serif; font-size: 13px; }
QMainWindow, #chrome { background: #000000; }

QLineEdit#urlbar {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    padding: 7px 16px;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}
QLineEdit#urlbar:focus { border: 1px solid #a6adc8; }

QToolButton {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: none;
    border-radius: 12px;
    padding: 5px 11px;
    font-weight: bold;
}
QToolButton:hover { background: #16161d; color: #ffffff; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: rgba(13, 13, 18, 200);
    color: #a6adc8;
    border-radius: 0px;
    padding: 7px 6px 7px 14px;
    margin: 4px 3px 6px 3px;
}
QTabBar::tab:selected {
    background: #16161d;
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 90);
}
QTabBar::tab:hover { color: #cdd6f4; }

#dlbar { background: #000000; border-top: 1px solid rgba(108, 112, 134, 50); }
#dlitem { background: rgba(13, 13, 18, 230); border-radius: 12px; }
QLabel#dlname { color: #cdd6f4; }
QLabel#dlinfo { color: #6c7086; font-size: 11px; }
QToolButton#dlall { background: transparent; color: #6c7086; }
QToolButton#dlall:hover { background: #16161d; color: #cdd6f4; }
QProgressBar {
    background: #16161d;
    border: none;
    border-radius: 3px;
    max-height: 6px;
}
QProgressBar::chunk { background: #89b4fa; border-radius: 3px; }

QToolButton#tabclose {
    background: rgba(108, 112, 134, 60);
    color: #cdd6f4;
    min-width: 18px; max-width: 18px;
    min-height: 18px; max-height: 18px;
    border-radius: 9px;
    padding: 0px;
    font-size: 12px;
    font-weight: normal;
}
QToolButton#tabclose:hover { background: rgba(243, 139, 168, 70); color: #f38ba8; }

#toast { background: #0d0d12; border: 1px solid rgba(108, 112, 134, 110); }
#permcard { background: #0d0d12; border: 1px solid rgba(108, 112, 134, 130); }
#permcard QLabel { color: #cdd6f4; }
#permcard QToolButton { padding: 6px 16px; border: 1px solid rgba(108, 112, 134, 90); }
#permcard QToolButton#permallow { background: #a6e3a1; color: #000000; border: none; }
#permcard QToolButton#permallow:hover { background: #c4f0c0; }
#permcard QLabel#permhint { color: #6c7086; font-size: 11px; }
#toast QLabel { color: #cdd6f4; }

/* the screen-share picker: same island over a dimmed window, square */
#sharepane { background: rgba(0, 0, 0, 200); }
#sharepanel { background: #000000; border: 1px solid rgba(108, 112, 134, 130); }
#sharepanel QLabel { color: #cdd6f4; }
#sharepanel QLabel#sharehead { color: #6c7086; font-size: 11px; }
#sharepanel QScrollArea { background: transparent; border: none; }
#sharepanel QToolButton {
    border-radius: 0px;
    padding: 7px 12px;
    border: 1px solid rgba(108, 112, 134, 90);
    font-weight: normal;
}
#sharepanel QToolButton#shareitem {
    background: #0d0d12; color: #cdd6f4; text-align: left;
}
#sharepanel QToolButton#shareitem:hover { background: #16161d; color: #ffffff; }
#sharepanel QToolButton#sharecancel { background: #0d0d12; }
#sharepanel QToolButton#sharecancel:hover { background: #16161d; }

/* the account chooser: the same island, listing names and nothing else */
#acctpane { background: rgba(0, 0, 0, 200); }
#acctpanel { background: #000000; border: 1px solid rgba(108, 112, 134, 130); }
#acctpanel QLabel { color: #cdd6f4; }
#acctpanel QLabel#accthead { font-size: 15px; }
#acctpanel QLabel#acctbody { color: #a6adc8; font-size: 12px; }
#acctpanel QScrollArea { background: transparent; border: none; }
/* the scroll area's own viewport, which otherwise shows the palette's
   pale default through the gap under a short list */
#acctpanel QScrollArea > QWidget > QWidget { background: transparent; }
#acctpanel QToolButton {
    border-radius: 0px;
    padding: 8px 12px;
    border: 1px solid rgba(108, 112, 134, 90);
    font-weight: normal;
}
#acctpanel QToolButton#acctitem {
    background: #0d0d12; color: #cdd6f4; text-align: left;
}
#acctpanel QToolButton#acctitem:hover { background: #16161d; color: #ffffff; }
#acctpanel QToolButton#acctcancel { background: #0d0d12; }
#acctpanel QToolButton#acctcancel:hover { background: #16161d; }
QToolButton#acctbtn {
    background: transparent;
    border: none;
    border-radius: 0px;
    color: #6c7086;
    font-size: 13px;
    padding: 0px;
}
QToolButton#acctbtn:hover { color: #cdd6f4; }

QMenu {
    background: #0d0d12;
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 110);
    padding: 4px;
}
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: #16161d; color: #ffffff; }
/* the sheet sets QMenu's colour, which wins over the palette, so
   without this a menu entry that cannot be picked looks exactly
   like one that can - and the toolbar menu has four of them */
QMenu::item:disabled { color: #a6adc8; }
QMenu::separator { height: 1px; background: rgba(108, 112, 134, 70); margin: 4px 8px; }

QToolButton#groupbtn {
    font-size: 15px;
    padding: 5px 12px;
    margin: 4px 0 6px 6px;
    border-radius: 0px;
}
QToolButton#newtabbtn {
    padding: 0px;
    margin: 0px;
    border-radius: 0px;
    font-size: 15px;
}

/* the bookmarks bar: a thin strip under the address bar */
/* the Favourites panel: Edge's drop-down, not a chain of menus.
   The sheet fills the window and paints nothing at all - it is there to
   catch a click that means "somewhere else", and to keep the card out
   of a popup of its own so that a drag inside it can work. */
#favshade { background: transparent; }
#favpanel { background: #0a0a0d; border: 1px solid rgba(108, 112, 134, 110); }
#favhead { background: #0d0d12; }
QLabel#favtitle { color: #cdd6f4; font-size: 15px; font-weight: bold; }
QLabel#favhint { color: #6c7086; font-size: 12px; }
QToolButton#favshut {
    background: transparent;
    color: #a6adc8;
    border-radius: 0px;
    font-size: 15px;
    padding: 3px 9px;
}
QToolButton#favshut:hover { background: #16161d; color: #ffffff; }
QLineEdit#favsearch {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    padding: 8px 11px;
    font-size: 14px;
}
QLineEdit#favsearch:focus { border: 1px solid #a6adc8; }
QTreeWidget#favtree {
    background: #0a0a0d;
    color: #cdd6f4;
    border: none;
    outline: none;
    font-size: 14px;
}
QTreeWidget#favtree::item { min-height: 30px; border: none; padding-left: 2px; }
QTreeWidget#favtree::item:hover { background: #16161d; color: #ffffff; }
QTreeWidget#favtree::item:selected { background: #313244; color: #ffffff; }
/* renaming happens in the row, so the box that opens there has to look
   like it belongs to this panel and not to the desktop */
QTreeWidget#favtree QLineEdit {
    background: #0d0d12;
    color: #cdd6f4;
    border: 1px solid #a6adc8;
    border-radius: 0px;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}
#favfoot { background: #0d0d12; border-top: 1px solid rgba(108, 112, 134, 50); }
QToolButton#favbtn {
    background: rgba(13, 13, 18, 230);
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    font-weight: normal;
    padding: 8px 12px;
}
QToolButton#favbtn:hover { background: #16161d; color: #ffffff; }
QToolButton#favbtn:disabled {
    color: #45475a;
    border: 1px solid rgba(108, 112, 134, 40);
    background: transparent;
}

#bmbar { background: #000000; border-top: 1px solid rgba(108, 112, 134, 40); }
QToolButton#bmitem {
    background: transparent;
    color: #a6adc8;
    border-radius: 0px;
    padding: 4px 8px;
    font-weight: normal;
    font-size: 12px;
}
QToolButton#bmitem:hover { background: #16161d; color: #ffffff; }
QToolButton#bmmore {
    background: transparent;
    color: #6c7086;
    border-radius: 0px;
    padding: 4px 8px;
    font-size: 13px;
}
QToolButton#bmmore:hover { background: #16161d; color: #ffffff; }
QLabel#bmempty { color: #45475a; font-size: 12px; }

/* the star, sitting inside the address bar */
QToolButton#starbtn {
    background: transparent;
    color: #a6adc8;
    border-radius: 0px;
    padding: 0px;
    font-size: 15px;
    font-weight: normal;
}
QToolButton#starbtn:hover { background: #16161d; color: #cdd6f4; }
QToolButton#starbtn[on="true"] { color: #f9e2af; }
QToolButton#starbtn[on="true"]:hover { color: #f9e2af; }
QToolButton#starbtn:disabled { color: #45475a; background: transparent; }

/* find in page: a small island in the top right of the page area */
#findbar { background: #0d0d12; border: 1px solid rgba(108, 112, 134, 110); }
QLineEdit#findinput {
    background: #000000;
    color: #cdd6f4;
    border: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    padding: 5px 8px;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}
QLineEdit#findinput:focus { border: 1px solid #a6adc8; }
QLabel#findcount { color: #6c7086; font-size: 12px; }
QLabel#findcount[dim="0"] { color: #cdd6f4; }
#findbar QToolButton {
    background: transparent;
    color: #a6adc8;
    border: 1px solid transparent;
    border-radius: 0px;
    padding: 4px 8px;
    font-weight: normal;
}
#findbar QToolButton:hover { background: #16161d; color: #ffffff; }
#findbar QToolButton:checked {
    background: #16161d; color: #ffffff;
    border: 1px solid rgba(108, 112, 134, 110);
}
#findbar QToolButton:disabled { color: #45475a; background: transparent; }

/* the tab switcher: a dimmed backdrop with a list floating on it */
#switchpane { background: rgba(0, 0, 0, 200); }
#switchpanel { background: #000000; border: 1px solid rgba(108, 112, 134, 110); }
QLineEdit#switchinput {
    background: #0d0d12;
    color: #cdd6f4;
    border: none;
    border-bottom: 1px solid rgba(108, 112, 134, 70);
    border-radius: 0px;
    padding: 11px 14px;
    font-size: 14px;
    selection-background-color: #45475a;
    selection-color: #ffffff;
}
QListWidget#switchlist {
    background: #000000;
    border: none;
    outline: 0;
}
QListWidget#switchlist::item { border: none; }
QListWidget#switchlist::item:selected { background: #16161d; }
QListWidget#switchlist QScrollBar:vertical {
    background: #000000; width: 8px; margin: 0px;
}
QListWidget#switchlist QScrollBar::handle:vertical {
    background: rgba(108, 112, 134, 90); min-height: 26px; border-radius: 0px;
}
QListWidget#switchlist QScrollBar::add-line:vertical,
QListWidget#switchlist QScrollBar::sub-line:vertical { height: 0px; }
QListWidget#switchlist QScrollBar::add-page:vertical,
QListWidget#switchlist QScrollBar::sub-page:vertical { background: #000000; }
QLabel#switchtitle { color: #cdd6f4; }
QLabel#switchtitle[here="1"] { color: #ffffff; font-weight: bold; }
QLabel#switchurl { color: #6c7086; font-size: 11px; }
QLabel#switchbadge { color: #a6adc8; font-size: 11px; }
QLabel#switchempty { color: #6c7086; }

/* the settings pane: it covers the whole window, so it is not an
   island on a backdrop any more — it is the window's content */
#setpane { background: #000000; }
#setpanel { background: #000000; }
#sethead {
    background: #0d0d12;
    border-bottom: 1px solid rgba(108, 112, 134, 70);
}
QLabel#setescl { color: #6c7086; font-size: 12px; }
"""


# =====================================================================
# Themes
# =====================================================================
# One palette drives the whole browser: the Qt stylesheet above and the
# CSS inside the browser's own HTML pages. Neither of those has
# variables, and the six pages each carry their own copy of the palette
# as plain hex literals — so the engine works the other way round. The
# Catppuccin Mocha literals already in STYLE and in the pages ARE the
# token names, and painting a theme is a literal-for-literal
# substitution driven by the table below. Python does it for the Qt
# sheet; the injected THEME_JS does exactly the same thing to every
# <style> in one of our own pages. One palette, both halves.
#
# Substitution is written so it can never bite its own tail: in a page
# what comes out is space-separated rgb(), which the pattern that goes
# in does not match. The untouched original is kept on the <style>
# element besides, so switching theme again starts from Mocha every
# time instead of recolouring a recolouring.

# token -> the Mocha literal that stands for it in STYLE and the pages
THEME_SOURCE = {
    "bg": "#000000",            # the window and the page behind it
    "crust": "#060608",
    "mantle": "#0a0a0d",
    "surface": "#0d0d12",       # an island
    "surfaceAlt": "#101018",
    "hover": "#16161d",         # an island under the mouse
    "sunken": "#313244",
    "muted": "#45475a",         # a disabled thing
    "overlay2": "#585b70",
    "overlay": "#6c7086",       # hairlines and quiet text
    "dim": "#8a8a8a",
    "subtext": "#a6adc8",
    "subtext1": "#bac2de",
    "text": "#cdd6f4",          # what you read
    "bright": "#ffffff",        # what stands out
    "accent": "#89b4fa",
    "accentLt": "#b4d0fb",
    "green": "#a6e3a1",
    "greenLt": "#c4f0c0",
    "yellow": "#f9e2af",
    "peach": "#fab387",
    "red": "#f38ba8",
}

# where a derived token sits on the line from the background to the
# text colour — measured off Mocha, so a palette that gives only its
# background and its text still comes out with Mocha's rhythm
_THEME_RAMP = {"sunken": 0.252, "muted": 0.347, "overlay2": 0.439,
               "overlay": 0.534, "dim": 0.625, "subtext": 0.813,
               "subtext1": 0.908}


def _hex_rgb(value):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c + c for c in value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c))))
                                   for c in rgb)


def _mix(a, b, t):
    """t of the way from colour a to colour b."""
    x, y = _hex_rgb(a), _hex_rgb(b)
    return _rgb_hex(tuple(x[i] + (y[i] - x[i]) * t for i in range(3)))


def _luma(value):
    r, g, b = _hex_rgb(value)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _srgb(channel):
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value):
    """WCAG 2.1 relative luminance — not _luma, which is a quick
    is-this-dark answer in plain sRGB. This is the number a contrast
    ratio is made of."""
    r, g, b = (_srgb(c) for c in _hex_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """1 for two colours that are the same, 21 for black on white.
    Text wants 4.5, big text and the edge of a control want 3."""
    x, y = relative_luminance(a), relative_luminance(b)
    if x < y:
        x, y = y, x
    return (x + 0.05) / (y + 0.05)


def flatten(fg, bg, alpha):
    """What a colour at `alpha` over `bg` actually looks like — the
    same sum the renderer does, so a hairline is measured as what is
    on the screen and not as what was typed."""
    if alpha >= 1:
        return fg
    return _mix(bg, fg, max(0.0, float(alpha)))


# What every colour has to reach. A token that is read has to clear
# WCAG's 4.5:1 against the page and against an island, whatever palette
# it comes out of; a token that is only ever seen — a track, a
# hairline, a disabled label — keeps the contrast Mocha gives it,
# whatever that happens to be, so a palette comes out with the rhythm
# the browser was drawn with instead of a guess at it.
_READ_FLOOR = 4.5
_QUIET_TOKENS = ("sunken", "muted", "overlay2")
# every background a colour can land on: the page, an island, the
# island under the mouse, a raised row, an input, a panel
_SURFACE_TOKENS = ("bg", "crust", "mantle", "surface", "surfaceAlt",
                   "hover")
_FLOORS = {}
for _t in _THEME_RAMP:
    _FLOORS[_t] = tuple(
        contrast_ratio(THEME_SOURCE[_t], THEME_SOURCE[_s])
        if _t in _QUIET_TOKENS else _READ_FLOOR
        for _s in _SURFACE_TOKENS)


# How far apart two rungs of the ladder have to stand. A floor alone
# does not give you a hierarchy: five rungs that all have to clear
# 4.5:1 will happily arrive at 4.5:1 together, and then the hint under
# a field, a quiet caption and a sentence are the same colour, and a
# menu entry that cannot be picked looks exactly like one that can.
# Mocha's own tightest step is 1.22, so 1.15 is a rhythm the browser
# was already drawn with rather than a new one imposed on it.
_RUNG_STEP = 1.15
_RUNG_CHAIN = tuple(_THEME_RAMP) + ("text",)


def _raise_to(color, surfaces, floors, far):
    """The same colour, moved toward the theme's far end only as far as
    it has to go to be readable on every background it can land on.

    A straight walk to white or to black keeps the hue exactly — every
    channel difference scales by the same factor, so the angle does not
    move — and it pays for the contrast in saturation, which is the
    only currency there is: a colour that has to travel a long way
    arrives paler than it set out. A pink stays a pink, but a theme
    built out of four greens has tokens that end up washed against the
    four (see the note on Game Boy in test_contrast.py). A theme that
    was already readable is not walked at all."""
    def clears(c, slack=0.0):
        return all(contrast_ratio(c, s) >= f - slack
                   for s, f in zip(surfaces, floors))

    if clears(color, 1e-9):
        return color
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if clears(_mix(color, far, mid)):
            hi = mid
        else:
            lo = mid
    return _mix(color, far, hi)


def _expand_palette(seed):
    """A theme is written down as a handful of colours; the other
    fifteen are derived from them so every palette keeps the same
    contrast rhythm instead of being guessed at twenty-two times.

    "Rhythm" is a measured thing here, not a proportion: a derived
    colour starts where the straight line from the background to the
    text puts it and is then pushed outward until it clears the floor
    for what it is used for. A palette that was already readable comes
    out exactly as it was written.

    A seed marked `exact` is a palette that is written down in full and
    is left alone — that is Mocha, which is the browser as it was drawn
    and is not the theme engine's to correct."""
    pal = {}
    bg = seed["bg"]
    text = seed["text"]
    dark = seed.get("dark")
    if dark is None:
        dark = _luma(bg) < 0.5
    far = "#ffffff" if dark else "#000000"
    exact = bool(seed.get("exact"))
    pal["bg"] = bg
    pal["text"] = text
    pal["surface"] = seed.get("surface") or _mix(bg, text, 0.066)
    pal["crust"] = seed.get("crust") or _mix(bg, pal["surface"], 0.45)
    pal["mantle"] = seed.get("mantle") or _mix(bg, pal["surface"], 0.75)
    pal["surfaceAlt"] = seed.get("surfaceAlt") or _mix(pal["surface"], text,
                                                       0.022)
    pal["hover"] = seed.get("hover") or _mix(pal["surface"], text, 0.052)
    surfaces = [pal[s] for s in _SURFACE_TOKENS]
    read = [_READ_FLOOR] * len(surfaces)
    if not exact:
        text = _raise_to(text, surfaces, read, far)
        pal["text"] = text
    rung = 0.0
    for token, t in _THEME_RAMP.items():
        value = seed.get(token) or _mix(bg, text, t)
        if not exact:
            value = _raise_to(value, surfaces, _FLOORS[token], far)
            # the ladder keeps its rungs in order: a quiet colour is
            # never left louder than the one above it
            if contrast_ratio(value, bg) < rung:
                value = _raise_to(value, [bg], [rung], far)
            rung = contrast_ratio(value, bg)
        pal[token] = value
    if not exact:
        _separate_rungs(pal, far)
        text = pal["text"]
    pal["bright"] = seed.get("bright") or _mix(text, far, 0.55)
    for token, fallback in (("accent", "#89b4fa"), ("green", "#a6e3a1"),
                            ("yellow", "#f9e2af"), ("peach", "#fab387"),
                            ("red", "#f38ba8")):
        value = seed.get(token) or fallback
        if not exact:
            value = _raise_to(value, surfaces, read, far)
        pal[token] = value
    pal["accentLt"] = seed.get("accentLt") or _mix(pal["accent"], far, 0.35)
    pal["greenLt"] = seed.get("greenLt") or _mix(pal["green"], far, 0.35)
    return pal


def _separate_rungs(pal, far):
    """Push the ladder apart, in place.

    Every rung has already been raised until it clears its floor
    against every background it can land on. That makes each one
    readable and says nothing at all about the next one: a floor is
    where a colour stops, so a floor shared by five rungs is where five
    rungs stop, together. This is the other half — each rung also has
    to stand a step above the one below it.

    A step is measured against the background, which is the same
    measurement as the two rungs against each other: for two colours on
    the same side of the background, their contrast with one another is
    exactly the ratio of their contrasts with it. So a ladder in ratios
    against the background is a ladder in readable difference, and it
    can only ever push a colour further from the background — the floor
    it already cleared is never given back.

    A palette does not always have room for the whole ladder; a theme
    whose text is already white has nowhere further to go. The step is
    then shrunk to whatever does fit, which is worth more than a
    nominal step that piles the top three rungs on the far end."""
    bg = pal["bg"]
    surfaces = [pal[s] for s in _SURFACE_TOKENS]
    base = [contrast_ratio(pal[t], bg) for t in _RUNG_CHAIN]
    headroom = contrast_ratio(far, bg)

    def ladder(step):
        want = [base[0]]
        for r in base[1:]:
            want.append(max(r, want[-1] * step))
        return want

    step = _RUNG_STEP
    if ladder(step)[-1] > headroom:
        lo, hi = 1.0, step
        for _ in range(24):
            mid = (lo + hi) / 2.0
            if ladder(mid)[-1] <= headroom:
                lo = mid
            else:
                hi = mid
        step = lo
    # walked rung by rung off where the rung below actually landed, not
    # off where it was asked to: a rung raised to clear a floor on some
    # island often overshoots what the step asked of it, and stepping
    # off the asking price rather than the paid one is how the step
    # above it comes out short
    want = base[0]
    for token in _RUNG_CHAIN[1:]:
        want *= step
        if contrast_ratio(pal[token], bg) + 1e-9 < want:
            floors = list(_FLOORS[token]) if token in _FLOORS \
                else [_READ_FLOOR] * len(surfaces)
            # the old floors travel with the new one: a rung moved for
            # the sake of the step still has to clear what it cleared
            pal[token] = _raise_to(pal[token], surfaces + [bg],
                                   floors + [want], far)
        want = contrast_ratio(pal[token], bg)


_COLOR_RE = re.compile(r"#[0-9a-f]{6}\b|rgba?\(\s*\d+\s*,[^)]*\)")


def _recolor(css, palette, qt=False):
    """Every Mocha literal in a stylesheet swapped for the same token
    out of another palette.

    Two colours are left where they are on purpose: a black used as a
    shadow, and a black scrim thin enough to be one (a dimmed backdrop
    behind a dialog stays a dimmed backdrop, it is not the window's
    background wearing an alpha). A near-opaque black IS an island over
    the wallpaper on the start page, so that one does move."""
    by_hex = {lit: palette[token] for token, lit in THEME_SOURCE.items()}
    by_rgb = {_hex_rgb(lit): palette[token]
              for token, lit in THEME_SOURCE.items() if lit != "#000000"}

    def swap(match):
        lit = match.group(0)
        if lit.startswith("#"):
            new = by_hex.get(lit)
            return new.upper() if new else lit
        inner = lit[lit.index("(") + 1:-1].split(",")
        if len(inner) < 3:
            return lit
        try:
            rgb = tuple(int(float(p)) for p in inner[:3])
        except ValueError:
            return lit
        alpha = inner[3].strip() if len(inner) > 3 else None
        if rgb == (0, 0, 0):
            if alpha is None:
                return lit
            start = max(css.rfind(";", 0, match.start()),
                        css.rfind("{", 0, match.start()),
                        css.rfind("}", 0, match.start()))
            if "shadow" in css[start + 1:match.start()]:
                return lit
            try:
                value = float(alpha)
            except ValueError:
                return lit
            if value > 1:
                value /= 255.0
            if value < 0.8:
                return lit
            new = palette["bg"]
        else:
            new = by_rgb.get(rgb)
            if not new:
                return lit
        r, g, b = _hex_rgb(new)
        if qt:
            return ("rgba(%d, %d, %d, %s)" % (r, g, b, alpha)
                    if alpha is not None else "rgb(%d, %d, %d)" % (r, g, b))
        return ("rgb(%d %d %d / %s)" % (r, g, b, alpha)
                if alpha is not None else "rgb(%d %d %d)" % (r, g, b))

    return _COLOR_RE.sub(swap, css)


DEFAULT_THEME = "mocha"
ACTIVE_THEME = DEFAULT_THEME
_PALETTE_CACHE = {}


def theme_names():
    return [t["key"] for t in THEMES]


def theme_def(name=None):
    key = name or ACTIVE_THEME
    # a hand-edited config can hold anything at all where a theme name
    # belongs, and a list is not something you can look up
    if not isinstance(key, str):
        key = DEFAULT_THEME
    return THEME_INDEX.get(key) or THEME_INDEX[DEFAULT_THEME]


def theme_is_dark(name=None):
    return bool(theme_def(name)["dark"])


def theme_palette(name=None):
    entry = theme_def(name)
    key = entry["key"]
    if key not in _PALETTE_CACHE:
        _PALETTE_CACHE[key] = _expand_palette(entry)
    return _PALETTE_CACHE[key]


def theme_style(name=None):
    """The Qt stylesheet for a theme. The default theme is the sheet
    written above, byte for byte: nobody's browser changes because a
    theme engine arrived."""
    entry = theme_def(name)
    sheet = (STYLE if entry["key"] == DEFAULT_THEME
             else _recolor(STYLE, theme_palette(entry["key"]), qt=True))
    return sheet + entry.get("qss", "")


def tint(qss, name=None):
    """The same substitution for a stylesheet set on one widget."""
    entry = theme_def(name)
    if entry["key"] == DEFAULT_THEME:
        return qss
    return _recolor(qss, theme_palette(entry["key"]), qt=True)


def theme_color(token, name=None):
    return theme_palette(name).get(token, THEME_SOURCE.get(token, "#000000"))


def readable_on(fill, name=None):
    """What to write on a fill of `fill`. A tab group's colour is the
    user's pick and not the theme's, so the theme's background is not
    always something that can be read on it: it is used while it can
    be, and black or white — whichever is further away — when it
    cannot. On Mocha every group colour clears it, so nothing there
    moves."""
    pal = theme_palette(name)
    if contrast_ratio(pal["bg"], fill) >= 3.0:
        return pal["bg"]
    return max(("#000000", "#ffffff"), key=lambda c: contrast_ratio(c, fill))


def theme_payload(name=None):
    """What the injected script needs to paint a page."""
    entry = theme_def(name)
    palette = theme_palette(entry["key"])
    return {"key": entry["key"], "name": entry["name"],
            "dark": bool(entry["dark"]),
            "identity": entry["key"] == DEFAULT_THEME,
            "map": {lit: palette[token]
                    for token, lit in THEME_SOURCE.items()},
            "colors": palette, "extra": entry.get("css", "")}


def _theme_card(entry):
    """One theme as a picker wants it: name, shelf, where it comes
    from, and the colours a preview swatch is painted with."""
    palette = theme_palette(entry["key"])
    return {"key": entry["key"], "name": entry["name"],
            "group": entry["group"], "dark": bool(entry["dark"]),
            "note": entry.get("note", ""),
            "swatch": [palette["bg"], palette["surface"],
                       palette["text"], palette["accent"],
                       palette["green"], palette["red"]]}


def theme_catalogue():
    """Every theme, for Settings' picker."""
    return [_theme_card(entry) for entry in THEMES]


# The dozen setup offers. A hundred and fourteen palettes is a
# catalogue to browse, not a question to answer, so the wizard shows
# four on each shelf and points at Settings for the rest. They are
# chosen to sit as far apart as the catalogue allows -- the default, a
# cold one, a warm one and a stark one; the same spread again in
# daylight; then four that are a place rather than a palette -- and not
# to be the twelve best known, because a row of famous names that all
# look alike would teach him nothing about what is in there.
WIZARD_THEMES = [
    "mocha", "nord", "gruvbox", "pitch",                    # dark
    "latte", "solarized-light", "sakura", "high-contrast",  # light
    "terminal", "synthwave", "sepia", "gameboy",            # with character
]


def wizard_themes():
    """The twelve, plus whatever is actually in use when that is not
    one of them: setup run a second time must never open on a picker
    with nothing ticked. Only these palettes get built, so this stays
    cheap enough to ride along in getSettings()."""
    keys = list(WIZARD_THEMES)
    if ACTIVE_THEME not in keys:
        keys.append(ACTIVE_THEME)
    return [_theme_card(THEME_INDEX[k]) for k in keys if k in THEME_INDEX]


# The script that paints one of our own pages. It runs on nothing else:
# a stranger's HTML on the disk keeps the colours its author chose, and
# a website never sees this at all.
THEME_JS = r"""
(function () {
  if (location.protocol !== "file:") return;
  if (!/\/(start|settings|history|downloads|bookmarks|passwords)\.html$/
        .test(location.pathname)) return;
  var T = %(payload)s;

  function build(t) {
    var hex = {}, rgb = {};
    for (var lit in t.map) {
      hex[lit] = t.map[lit].toUpperCase();
      if (lit !== "#000000")
        rgb[parseInt(lit.slice(1, 3), 16) + "," + parseInt(lit.slice(3, 5), 16)
            + "," + parseInt(lit.slice(5, 7), 16)] = t.map[lit];
    }
    t._hex = hex; t._rgb = rgb;
  }

  // the same swap browser.py does to the Qt stylesheet, in the page
  function recolor(css, t) {
    return css.replace(/#[0-9a-f]{6}\b|rgba?\(\s*\d+\s*,[^)]*\)/g,
      function (lit, off) {
        if (lit.charAt(0) === "#") {
          var h = t._hex[lit];
          return h ? "rgb(" + parseInt(h.slice(1, 3), 16) + " "
                     + parseInt(h.slice(3, 5), 16) + " "
                     + parseInt(h.slice(5, 7), 16) + ")" : lit;
        }
        var inner = lit.slice(lit.indexOf("(") + 1, -1).split(",");
        var r = parseInt(inner[0], 10), g = parseInt(inner[1], 10),
            b = parseInt(inner[2], 10);
        var a = inner.length > 3 ? inner[3].trim() : null, col;
        if (r === 0 && g === 0 && b === 0) {
          if (a === null) return lit;
          var cut = Math.max(css.lastIndexOf(";", off),
                             css.lastIndexOf("{", off),
                             css.lastIndexOf("}", off));
          if (css.slice(cut + 1, off).indexOf("shadow") >= 0) return lit;
          var av = parseFloat(a);
          if (av > 1) av = av / 255;
          if (!(av >= 0.8)) return lit;
          col = t.map["#000000"];
        } else {
          col = t._rgb[r + "," + g + "," + b];
          if (!col) return lit;
        }
        var R = parseInt(col.slice(1, 3), 16),
            G = parseInt(col.slice(3, 5), 16),
            B = parseInt(col.slice(5, 7), 16);
        return a === null ? "rgb(" + R + " " + G + " " + B + ")"
                          : "rgb(" + R + " " + G + " " + B + " / " + a + ")";
      });
  }

  // nothing is shown in the wrong colours on the way: the page waits,
  // over its own background, until the palette is on it
  var hide = null;
  function arm() {
    if (T.identity || hide) return;
    var root = document.documentElement;
    if (!root) { setTimeout(arm, 0); return; }
    hide = document.createElement("style");
    hide.id = "themehide";
    hide.textContent = "html{background:" + T.colors.bg
                     + " !important}body{visibility:hidden !important}";
    root.appendChild(hide);
    setTimeout(unhide, 2000);   // a page is never left hidden
  }
  function unhide() {
    if (hide && hide.parentNode) hide.parentNode.removeChild(hide);
    hide = null;
  }

  function extra(t) {
    var el = document.getElementById("themeextra");
    if (t.extra) {
      if (!el) {
        el = document.createElement("style");
        el.id = "themeextra";
        (document.head || document.documentElement).appendChild(el);
      }
      el.textContent = t.extra;
    } else if (el && el.parentNode) {
      el.parentNode.removeChild(el);
    }
  }

  function apply(t) {
    T = t; build(T);
    var root = document.documentElement;
    if (root) {
      root.setAttribute("data-theme", T.key);
      for (var k in T.colors)
        root.style.setProperty("--" + k.toLowerCase(), T.colors[k]);
      if (!T.identity) root.style.colorScheme = T.dark ? "dark" : "light";
      else root.style.colorScheme = "";
    }
    var sheets = document.querySelectorAll("style");
    for (var i = 0; i < sheets.length; i++) {
      var st = sheets[i];
      if (st.id === "themeextra" || st.id === "themehide") continue;
      // what the file actually says, kept aside: switching theme again
      // starts from the original every time instead of recolouring a
      // recolouring. A sheet the parser was still filling when the last
      // pass ran has grown since — take the new tail, not the whole of
      // it, or the part already painted would be lost.
      var cur = st.textContent, done = st.__themePainted;
      if (done !== undefined && cur.slice(0, done.length) === done)
        st.__themeOrig += cur.slice(done.length);
      else if (cur !== done)
        st.__themeOrig = cur;
      var out = T.identity ? st.__themeOrig : recolor(st.__themeOrig, T);
      st.__themePainted = out;
      if (out !== cur) st.textContent = out;
    }
    extra(T);
    unhide();
    // the picker's tick follows the browser, not only its own clicks
    document.dispatchEvent(new CustomEvent("themepainted",
                                           {detail: T.key}));
  }

  build(T);
  arm();
  window.__theme = function () { return T; };
  window.__applyTheme = function (j) {
    apply(typeof j === "string" ? JSON.parse(j) : j);
  };
  function ready() { apply(T); }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", ready);
  else ready();
})();
"""

# ---------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------
# Each row is (key, name, shelf, where it comes from, background,
# island, text, accent, green, yellow, peach, red). Everything else —
# the hairlines, the quiet text, the hover, the disabled grey — is
# derived from those, so every palette keeps the rhythm the browser was
# drawn with. Palettes that have a name and an author are credited by
# it; the rest are drawn here.
_CATALOGUE = [
    # -- Catppuccin (catppuccin.com) ----------------------------------
    ("mocha", "Catppuccin Mocha", "dark", "Catppuccin · the original look",
     "#000000", "#0d0d12", "#cdd6f4", "#89b4fa", "#a6e3a1", "#f9e2af",
     "#fab387", "#f38ba8"),
    ("macchiato", "Catppuccin Macchiato", "dark", "Catppuccin",
     "#181926", "#24273a", "#cad3f5", "#8aadf4", "#a6da95", "#eed49f",
     "#f5a97f", "#ed8796"),
    ("frappe", "Catppuccin Frappé", "dark", "Catppuccin",
     "#232634", "#303446", "#c6d0f5", "#8caaee", "#a6d189", "#e5c890",
     "#ef9f76", "#e78284"),
    ("latte", "Catppuccin Latte", "light", "Catppuccin",
     "#dce0e8", "#eff1f5", "#4c4f69", "#1e66f5", "#40a02b", "#df8e1d",
     "#fe640b", "#d20f39"),

    # -- Gruvbox (Pavel Pertsev) --------------------------------------
    ("gruvbox", "Gruvbox Dark", "dark", "Gruvbox",
     "#1d2021", "#282828", "#ebdbb2", "#83a598", "#b8bb26", "#fabd2f",
     "#fe8019", "#fb4934"),
    ("gruvbox-hard", "Gruvbox Dark Hard", "dark", "Gruvbox",
     "#141617", "#1d2021", "#ebdbb2", "#83a598", "#b8bb26", "#fabd2f",
     "#fe8019", "#fb4934"),
    ("gruvbox-light", "Gruvbox Light", "light", "Gruvbox",
     "#ebdbb2", "#fbf1c7", "#3c3836", "#076678", "#79740e", "#b57614",
     "#af3a03", "#9d0006"),
    ("gruvbox-light-hard", "Gruvbox Light Hard", "light", "Gruvbox",
     "#f2e5bc", "#f9f5d7", "#3c3836", "#076678", "#79740e", "#b57614",
     "#af3a03", "#9d0006"),

    # -- Nord (Arctic Ice Studio) -------------------------------------
    ("nord", "Nord", "dark", "Nord",
     "#242933", "#2e3440", "#d8dee9", "#88c0d0", "#a3be8c", "#ebcb8b",
     "#d08770", "#bf616a"),
    ("nord-light", "Nord Snow Storm", "light", "Nord",
     "#d8dee9", "#eceff4", "#2e3440", "#5e81ac", "#a3be8c", "#ebcb8b",
     "#d08770", "#bf616a"),

    ("dracula", "Dracula", "dark", "Dracula",
     "#21222c", "#282a36", "#f8f8f2", "#bd93f9", "#50fa7b", "#f1fa8c",
     "#ffb86c", "#ff5555"),

    # -- Solarized (Ethan Schoonover) ---------------------------------
    ("solarized-dark", "Solarized Dark", "dark", "Solarized",
     "#002b36", "#073642", "#93a1a1", "#268bd2", "#859900", "#b58900",
     "#cb4b16", "#dc322f"),
    ("solarized-light", "Solarized Light", "light", "Solarized",
     "#eee8d5", "#fdf6e3", "#586e75", "#268bd2", "#859900", "#b58900",
     "#cb4b16", "#dc322f"),

    # -- Tokyo Night (Folke Lemaitre) ---------------------------------
    ("tokyonight", "Tokyo Night", "dark", "Tokyo Night",
     "#16161e", "#1a1b26", "#c0caf5", "#7aa2f7", "#9ece6a", "#e0af68",
     "#ff9e64", "#f7768e"),
    ("tokyonight-storm", "Tokyo Night Storm", "dark", "Tokyo Night",
     "#1f2335", "#24283b", "#c0caf5", "#7aa2f7", "#9ece6a", "#e0af68",
     "#ff9e64", "#f7768e"),
    ("tokyonight-moon", "Tokyo Night Moon", "dark", "Tokyo Night",
     "#1e2030", "#222436", "#c8d3f5", "#82aaff", "#c3e88d", "#ffc777",
     "#ff966c", "#ff757f"),
    ("tokyonight-day", "Tokyo Night Day", "light", "Tokyo Night",
     "#d0d5e3", "#e1e2e7", "#3760bf", "#2e7de9", "#587539", "#8c6c3e",
     "#b15c00", "#f52a65"),

    # -- Everforest (sainnhe) -----------------------------------------
    ("everforest-hard", "Everforest Dark Hard", "dark", "Everforest",
     "#1e2326", "#272e33", "#d3c6aa", "#7fbbb3", "#a7c080", "#dbbc7f",
     "#e69875", "#e67e80"),
    ("everforest-soft", "Everforest Dark Soft", "dark", "Everforest",
     "#293136", "#333c43", "#d3c6aa", "#7fbbb3", "#a7c080", "#dbbc7f",
     "#e69875", "#e67e80"),
    ("everforest-light", "Everforest Light", "light", "Everforest",
     "#f2efdf", "#fdf6e3", "#5c6a72", "#3a94c5", "#8da101", "#dfa000",
     "#f57d26", "#f85552"),

    # -- Rosé Pine (rosepinetheme.com) ---------------------------
    ("rose-pine", "Rosé Pine", "dark", "Rosé Pine",
     "#131019", "#191724", "#e0def4", "#c4a7e7", "#9ccfd8", "#f6c177",
     "#ebbcba", "#eb6f92"),
    ("rose-pine-moon", "Rosé Pine Moon", "dark", "Rosé Pine",
     "#1f1d30", "#232136", "#e0def4", "#c4a7e7", "#9ccfd8", "#f6c177",
     "#ea9a97", "#eb6f92"),
    ("rose-pine-dawn", "Rosé Pine Dawn", "light", "Rosé Pine",
     "#f2e9e1", "#faf4ed", "#575279", "#907aa9", "#56949f", "#ea9d34",
     "#d7827e", "#b4637a"),

    # -- Kanagawa (rebelot) -------------------------------------------
    ("kanagawa", "Kanagawa Wave", "dark", "Kanagawa",
     "#16161d", "#1f1f28", "#dcd7ba", "#7e9cd8", "#98bb6c", "#e6c384",
     "#ffa066", "#c34043"),
    ("kanagawa-dragon", "Kanagawa Dragon", "dark", "Kanagawa",
     "#0d0c0c", "#181616", "#c5c9c5", "#8ba4b0", "#8a9a7b", "#c4b28a",
     "#b6927b", "#c4746e"),
    ("kanagawa-lotus", "Kanagawa Lotus", "light", "Kanagawa",
     "#e7dba0", "#f2ecbc", "#545464", "#4d699b", "#6f894e", "#77713f",
     "#cc6d00", "#c84053"),

    ("monokai", "Monokai", "dark", "Monokai",
     "#1e1f1c", "#272822", "#f8f8f2", "#66d9ef", "#a6e22e", "#e6db74",
     "#fd971f", "#f92672"),
    ("monokai-pro", "Monokai Pro", "dark", "Monokai",
     "#221f22", "#2d2a2e", "#fcfcfa", "#78dce8", "#a9dc76", "#ffd866",
     "#fc9867", "#ff6188"),

    ("one-dark", "One Dark", "dark", "Atom One",
     "#21252b", "#282c34", "#abb2bf", "#61afef", "#98c379", "#e5c07b",
     "#d19a66", "#e06c75"),
    ("one-light", "One Light", "light", "Atom One",
     "#eaeaeb", "#fafafa", "#383a42", "#4078f2", "#50a14f", "#c18401",
     "#d75f00", "#e45649"),

    # -- Ayu (Ike Ku) -------------------------------------------------
    ("ayu-dark", "Ayu Dark", "dark", "Ayu",
     "#0b0e14", "#131721", "#bfbdb6", "#59c2ff", "#aad94c", "#e6b673",
     "#ff8f40", "#f26d78"),
    ("ayu-mirage", "Ayu Mirage", "dark", "Ayu",
     "#1a1f29", "#242936", "#cccac2", "#73d0ff", "#d5ff80", "#ffcc66",
     "#ffad66", "#f28779"),
    ("ayu-light", "Ayu Light", "light", "Ayu",
     "#f0f0f0", "#fcfcfc", "#5c6166", "#399ee6", "#86b300", "#f2ae49",
     "#fa8d3e", "#f07171"),

    # -- Material (Mattia Astorino) -----------------------------------
    ("material-darker", "Material Darker", "dark", "Material",
     "#1a1a1a", "#212121", "#eeffff", "#82aaff", "#c3e88d", "#ffcb6b",
     "#f78c6c", "#f07178"),
    ("material-palenight", "Material Palenight", "dark", "Material",
     "#202331", "#292d3e", "#a6accd", "#82aaff", "#c3e88d", "#ffcb6b",
     "#f78c6c", "#f07178"),
    ("material-ocean", "Material Oceanic", "dark", "Material",
     "#1e272c", "#263238", "#eeffff", "#82aaff", "#c3e88d", "#ffcb6b",
     "#f78c6c", "#f07178"),

    # -- Oxocarbon (IBM Carbon) ---------------------------------------
    ("oxocarbon", "Oxocarbon Dark", "dark", "IBM Carbon",
     "#0c0c0c", "#161616", "#f2f4f8", "#33b1ff", "#42be65", "#f1c21b",
     "#ff7eb6", "#ee5396"),
    ("oxocarbon-light", "Oxocarbon Light", "light", "IBM Carbon",
     "#dde1e6", "#f2f4f8", "#161616", "#0f62fe", "#198038", "#8e6a00",
     "#ff7eb6", "#da1e28"),

    # -- Nightfox family (EdenEast) -----------------------------------
    ("nightfox", "Nightfox", "dark", "Nightfox",
     "#131a24", "#192330", "#cdcecf", "#719cd6", "#81b29a", "#dbc074",
     "#f4a261", "#c94f6d"),
    ("duskfox", "Duskfox", "dark", "Nightfox",
     "#191726", "#232136", "#e0def4", "#569fba", "#a3be8c", "#f6c177",
     "#f5a191", "#eb6f92"),
    ("nordfox", "Nordfox", "dark", "Nightfox",
     "#232831", "#2e3440", "#cdcecf", "#81a1c1", "#a3be8c", "#ebcb8b",
     "#d08770", "#bf616a"),
    ("terafox", "Terafox", "dark", "Nightfox",
     "#0f1c1e", "#152528", "#e6eaea", "#5a93aa", "#7aa4a1", "#fda47f",
     "#ff8349", "#e85c51"),
    ("carbonfox", "Carbonfox", "dark", "Nightfox",
     "#0c0c0c", "#161616", "#f2f4f8", "#78a9ff", "#25be6a", "#f1c21b",
     "#3ddbd9", "#ee5396"),
    ("dayfox", "Dayfox", "light", "Nightfox",
     "#e7dfd7", "#f6f2ee", "#3d2b5a", "#2848a9", "#396847", "#ac5402",
     "#c26d3a", "#a5222f"),

    ("doom-one", "Doom One", "dark", "Doom Emacs",
     "#21242b", "#282c34", "#bbc2cf", "#51afef", "#98be65", "#ecbe7b",
     "#da8548", "#ff6c6b"),
    ("zenburn", "Zenburn", "dark", "Zenburn",
     "#333333", "#3f3f3f", "#dcdccc", "#8cd0d3", "#7f9f7f", "#f0dfaf",
     "#dfaf8f", "#cc9393"),

    ("iceberg", "Iceberg", "dark", "Iceberg",
     "#0f1117", "#161821", "#c6c8d1", "#84a0c6", "#b4be82", "#e2a478",
     "#e2a478", "#e27878"),
    ("iceberg-light", "Iceberg Light", "light", "Iceberg",
     "#dcdfe7", "#e8e9ec", "#33374c", "#2d539e", "#668e3d", "#c57339",
     "#c57339", "#cc517a"),

    ("night-owl", "Night Owl", "dark", "Sarah Drasner",
     "#011627", "#0b2942", "#d6deeb", "#82aaff", "#addb67", "#ecc48d",
     "#f78c6c", "#ef5350"),
    ("light-owl", "Light Owl", "light", "Sarah Drasner",
     "#eeeef0", "#fbfbfb", "#403f53", "#4876d6", "#2aa298", "#daaa01",
     "#aa0982", "#de3d3b"),

    ("github-dark", "GitHub Dark", "dark", "GitHub",
     "#0d1117", "#161b22", "#c9d1d9", "#58a6ff", "#3fb950", "#d29922",
     "#ffa657", "#f85149"),
    ("github-dimmed", "GitHub Dark Dimmed", "dark", "GitHub",
     "#1c2128", "#22272e", "#adbac7", "#539bf5", "#57ab5a", "#c69026",
     "#e0823d", "#e5534b"),
    ("github-light", "GitHub Light", "light", "GitHub",
     "#eaeef2", "#ffffff", "#24292f", "#0969da", "#1a7f37", "#9a6700",
     "#bc4c00", "#cf222e"),

    ("vscode-dark", "VS Code Dark+", "dark", "Visual Studio Code",
     "#1e1e1e", "#252526", "#d4d4d4", "#569cd6", "#6a9955", "#dcdcaa",
     "#ce9178", "#f44747"),
    ("vscode-light", "VS Code Light+", "light", "Visual Studio Code",
     "#ececec", "#ffffff", "#333333", "#005cc5", "#098658", "#795e26",
     "#a31515", "#cd3131"),

    ("cobalt2", "Cobalt2", "dark", "Wes Bos",
     "#193549", "#1f4662", "#ffffff", "#ffc600", "#3ad900", "#ffc600",
     "#ff9d00", "#ff628c"),
    ("horizon", "Horizon", "dark", "Horizon",
     "#1c1e26", "#232530", "#d5d8da", "#26bbd9", "#29d398", "#fac29a",
     "#f09483", "#e95678"),
    ("panda", "Panda", "dark", "Panda Syntax",
     "#292a2b", "#31353a", "#e6e6e6", "#45a9f9", "#19f9d8", "#ffb86c",
     "#ff9ac1", "#ff2c6d"),
    ("oceanic-next", "Oceanic Next", "dark", "Oceanic Next",
     "#16232b", "#1b2b34", "#c0c5ce", "#6699cc", "#99c794", "#fac863",
     "#f99157", "#ec5f67"),
    ("tomorrow-night", "Tomorrow Night", "dark", "Chris Kempson",
     "#1d1f21", "#282a2e", "#c5c8c6", "#81a2be", "#b5bd68", "#f0c674",
     "#de935f", "#cc6666"),
    ("tomorrow-eighties", "Tomorrow Night Eighties", "dark", "Chris Kempson",
     "#2d2d2d", "#393939", "#cccccc", "#6699cc", "#99cc99", "#ffcc66",
     "#f99157", "#f2777a"),
    ("snazzy", "Hyper Snazzy", "dark", "Sindre Sorhus",
     "#1e1f29", "#282a36", "#eff0eb", "#57c7ff", "#5af78e", "#f3f99d",
     "#ff6ac1", "#ff5c57"),
    ("challenger-deep", "Challenger Deep", "dark", "Challenger Deep",
     "#17152a", "#1e1c31", "#cbe3e7", "#65b2ff", "#62de84", "#ffe9aa",
     "#906cff", "#ff5370"),
    ("nightfly", "Nightfly", "dark", "Bluz71",
     "#010e1a", "#011627", "#c3ccdc", "#82aaff", "#a1cd5e", "#e3d18a",
     "#f78c6c", "#fc514e"),
    ("moonfly", "Moonfly", "dark", "Bluz71",
     "#080808", "#191919", "#c6c6c6", "#80a0ff", "#8cc85f", "#e3c78a",
     "#de935f", "#ff5454"),
    ("poimandres", "Poimandres", "dark", "Poimandres",
     "#14161f", "#1b1e28", "#a6accd", "#89ddff", "#5de4c7", "#fffac2",
     "#fcc5e9", "#d0679d"),
    ("aura", "Aura", "dark", "Daniel Kuroski",
     "#110f17", "#15141b", "#edecee", "#a277ff", "#61ffca", "#ffca85",
     "#f694ff", "#ff6767"),
    ("vitesse-dark", "Vitesse Dark", "dark", "Anthony Fu",
     "#0b0b0b", "#121212", "#dbd7ca", "#6394bf", "#4d9375", "#e6cc77",
     "#d4976c", "#cb7676"),
    ("vitesse-light", "Vitesse Light", "light", "Anthony Fu",
     "#eae9e2", "#f8f8f6", "#393a34", "#296aa3", "#1e754f", "#bda437",
     "#a65e2b", "#ab5959"),
    ("flexoki-dark", "Flexoki Dark", "dark", "Steph Ango",
     "#100f0f", "#1c1b1a", "#cecdc3", "#4385be", "#879a39", "#d0a215",
     "#da702c", "#d14d41"),
    ("flexoki-light", "Flexoki Light", "light", "Steph Ango",
     "#e6e4d9", "#fffcf0", "#100f0f", "#205ea6", "#66800b", "#ad8301",
     "#bc5215", "#af3029"),
    ("modus-vivendi", "Modus Vivendi", "dark", "Protesilaos Stavrou",
     "#000000", "#1e1e1e", "#ffffff", "#2fafff", "#44bc44", "#d0bc00",
     "#fec43f", "#ff5f59"),
    ("modus-operandi", "Modus Operandi", "light", "Protesilaos Stavrou",
     "#f2f2f2", "#ffffff", "#000000", "#0031a9", "#006800", "#6f5500",
     "#a0522d", "#a60000"),
    ("sonokai", "Sonokai", "dark", "sainnhe",
     "#222327", "#2c2e34", "#e2e2e3", "#76cce0", "#9ed072", "#e7c664",
     "#f39660", "#fc5d7c"),
    ("sonokai-shusia", "Sonokai Shusia", "dark", "sainnhe",
     "#222022", "#2d2a2e", "#e3e1e4", "#78dce8", "#9ecd6f", "#e7c664",
     "#f39660", "#f85e84"),
    ("melange", "Melange Dark", "dark", "Salva Bonet",
     "#211f1c", "#292522", "#ece1d7", "#7f91b2", "#85b695", "#ebc06d",
     "#d9915b", "#d47766"),
    ("apprentice", "Apprentice", "dark", "romainl",
     "#1c1c1c", "#262626", "#bcbcbc", "#5f87af", "#5f875f", "#ffffaf",
     "#ff8700", "#af5f5f"),
    ("jellybeans", "Jellybeans", "dark", "NanoTech",
     "#0f0f0f", "#151515", "#e8e8d3", "#8fbfdc", "#99ad6a", "#fad07a",
     "#ffb964", "#cf6a4c"),
    ("spacemacs", "Spacemacs Dark", "dark", "Spacemacs",
     "#212026", "#292b2e", "#b2b2b2", "#4f97d7", "#67b11d", "#b1951d",
     "#dc752f", "#f2241f"),
    ("papercolor", "PaperColor Light", "light", "Nikyle Nguyen",
     "#e4e4e4", "#eeeeee", "#444444", "#0087af", "#008700", "#af8700",
     "#d75f00", "#af0000"),

    # -- drawn here ---------------------------------------------------
    ("steam", "Steam", "dark", "Like the game client",
     "#1b2838", "#2a475e", "#c7d5e0", "#66c0f4", "#a4d007", "#e5c463",
     "#d98d3a", "#d94141"),
    ("slate", "Slate", "dark", "Cool neutral grey",
     "#0f1418", "#182027", "#cbd5dd", "#6aa9d8", "#7fbf95", "#d9c273",
     "#d99a6a", "#d97080"),
    ("charcoal", "Charcoal", "dark", "No colour cast at all",
     "#0e0e0e", "#191919", "#d6d6d6", "#9aa0a6", "#7fb27f", "#d4bd6a",
     "#d1926a", "#cf6a6a"),
    ("pitch", "Pitch", "dark", "Maximum contrast",
     "#000000", "#0a0a0a", "#ffffff", "#ffffff", "#00ff87", "#ffe600",
     "#ff9d00", "#ff4d4d"),
    ("midnight", "Midnight Blue", "dark", "Deep navy",
     "#060d1a", "#0d1728", "#cfdcf0", "#4d8bff", "#5fbf8a", "#ddc069",
     "#dd9a5f", "#e05f74"),
    ("nautical", "Nautical", "dark", "Harbour at night",
     "#071a26", "#0e2b3b", "#d7e7ef", "#2fa4c9", "#4fb997", "#e8c46a",
     "#e08a52", "#d95a5a"),
    ("deep-sea", "Deep Sea", "dark", "Under the surface",
     "#01121a", "#04202c", "#b7dfe6", "#3fd0d6", "#38b09a", "#d9d17a",
     "#d98a6a", "#e05a72"),
    ("emerald", "Emerald", "dark", "Green stone",
     "#041410", "#0a231b", "#ccf0e0", "#2fd39a", "#5fe0a8", "#d9d06a",
     "#d99a5a", "#e0607a"),
    ("forest", "Forest Night", "dark", "Under the trees",
     "#101a12", "#17261a", "#cfe0cd", "#7fb069", "#9ccb7a", "#d9c06a",
     "#c98a52", "#c15f5f"),
    ("autumn", "Autumn", "dark", "Falling leaves",
     "#1a1311", "#241a16", "#e8d3c0", "#d97742", "#8a9a4b", "#e0a534",
     "#d9884a", "#b1442c"),
    ("volcano", "Volcano", "dark", "Molten",
     "#150c0c", "#241110", "#f0d6c8", "#ff6b35", "#9fb04a", "#ffb238",
     "#ff8c42", "#e03e2f"),
    ("sunset", "Sunset", "dark", "Last light",
     "#1b0f16", "#2a1520", "#ffe0d0", "#ff7b54", "#9ec46a", "#ffcf70",
     "#ff9e64", "#ff5470"),
    ("crimson", "Crimson", "dark", "Red on near-black",
     "#14090c", "#200f14", "#f0d8dd", "#e0435f", "#7fae7f", "#d9b45c",
     "#d98a6a", "#ff5c78"),
    ("wine", "Wine", "dark", "Dark berry",
     "#1a0e13", "#26141c", "#ecd7de", "#a8577a", "#7f9a6a", "#cfa95f",
     "#c4795f", "#d2496b"),
    ("plum", "Plum", "dark", "Soft purple",
     "#150d18", "#221327", "#ead8f0", "#b07ad0", "#7fbf9a", "#d9bf6a",
     "#d99a7a", "#d9607f"),
    ("royal", "Royal", "dark", "Purple and gold",
     "#120c22", "#1d1436", "#e9e2ff", "#b08d3a", "#6fbf8e", "#e0c063",
     "#d69a5a", "#c25a72"),
    ("cyberpunk", "Cyberpunk", "dark", "Neon on black",
     "#0d0221", "#170a2b", "#e6f1ff", "#00f0ff", "#00ff9f", "#fcee0c",
     "#ff9f1c", "#ff003c"),
    ("halloween", "Halloween", "dark", "Pumpkin season",
     "#120b04", "#1f1208", "#f2dcc0", "#ff7518", "#7fbf3f", "#ffc93c",
     "#ff9a3c", "#b03a2e"),
    ("sakura", "Sakura", "light", "Cherry blossom",
     "#f5e6ea", "#fffafb", "#4d3b45", "#d4738f", "#7fae7f", "#d0a24a",
     "#e0906a", "#c4485f"),
    ("lavender", "Lavender", "light", "Pale purple",
     "#ece8f5", "#fbf9ff", "#453d5c", "#7c5cbf", "#56926b", "#a8811f",
     "#b96a3f", "#b03a5b"),
    ("winter", "Winter", "light", "Cold daylight",
     "#dfe7ee", "#f4f8fb", "#33414f", "#3f7fbf", "#4f9a7a", "#a8862f",
     "#b0693f", "#b0455a"),
    ("mint", "Mint", "light", "Fresh green",
     "#e2efe8", "#f5fbf7", "#2f4239", "#2f9e73", "#3fae7f", "#a08a2a",
     "#b06a3a", "#ae4050"),
    ("moss", "Moss", "light", "Olive and stone",
     "#e4e8dc", "#f4f7ee", "#3d4436", "#5f7d3a", "#6f9440", "#a8861f",
     "#b0682f", "#a33c33"),
    ("ink", "Ink", "light", "Blue-grey paper",
     "#e7ebf0", "#f8fafc", "#24303c", "#2f6f9f", "#3f8a5f", "#93711f",
     "#a5623a", "#a33a4a"),
    ("high-contrast", "High Contrast Light", "light", "Black on white",
     "#f2f2f2", "#ffffff", "#000000", "#0033cc", "#006400", "#7a5c00",
     "#a34700", "#b00000"),

    # -- with character -----------------------------------------------
    ("steampunk", "Steampunk", "character", "Brass, copper and oxblood",
     "#16100a", "#241a10", "#e9d5aa", "#c08a35", "#7d8a3c", "#d9a441",
     "#b5713f", "#a8362b"),
    ("terminal", "Terminal Green", "character", "Phosphor on glass",
     "#001200", "#002a06", "#33ff66", "#7cffb2", "#33ff66", "#b6ff5c",
     "#5cffa0", "#ff6b6b"),
    ("amber", "Amber CRT", "character", "The other phosphor",
     "#120a00", "#1f1400", "#ffb000", "#ffd27f", "#c8a000", "#ffcc33",
     "#ff9d00", "#ff6a3d"),
    ("blueprint", "Blueprint", "character", "Drawn on the drafting table",
     "#06294a", "#0b3763", "#d6e9ff", "#7fd4ff", "#8fe3c0", "#ffe08a",
     "#ffb37f", "#ff8a8a"),
    ("synthwave", "Synthwave '84", "character", "Robb Owen · neon grid",
     "#1e1a2b", "#2a2139", "#f6f2ff", "#ff7edb", "#72f1b8", "#fede5d",
     "#ff8b39", "#fe4450"),
    ("gameboy", "Game Boy", "character", "Four shades of green",
     "#0b280b", "#144014", "#9bbc0f", "#8bac0f", "#9bbc0f", "#c8d858",
     "#c2843a", "#c2412d"),
    ("c64", "Commodore 64", "character", "Home computer blue",
     "#35298c", "#40318d", "#b8b0f0", "#7c70da", "#55a049", "#bfce72",
     "#8b5429", "#883932"),
    ("sepia", "Sepia Paper", "character", "Old book, light",
     "#e8dfc8", "#f6efdc", "#4a3f30", "#8a5a2b", "#5f6b34", "#a8791f",
     "#b4652a", "#963228"),
    ("newspaper", "Newspaper", "character", "Print, light",
     "#e9e7e1", "#fbfaf7", "#1a1a1a", "#8c1d18", "#2f5d3a", "#8a6d1f",
     "#a55b2a", "#8c1d18"),
]

# The few themes that are more than a palette: an explicit token table
# (the default one, so it stays exactly the sheet written above), CSS
# appended to our own pages, and QSS appended to the Qt sheet.
#
# A texture is a background. It is painted on the body, which puts it
# behind everything the page draws on top — an island, a button, an
# input, a line of text — instead of over the lot on a fixed overlay,
# which is where the hatch running through the search box came from.
# The body's background reaches the whole window either way: with
# nothing on the html element, the renderer hands the body's
# background to the canvas.
_THEME_EXTRAS = {
    # the sheet as written, token for token — `exact` keeps the fitting
    # off it: this palette is the browser as it was drawn
    "mocha": dict(THEME_SOURCE, exact=True),

    "steampunk": {
        "bright": "#fff3d6",
        # a slab face for the headings, a brass rule under them, and a
        # brushed-metal sheen over the whole page. No image files: the
        # texture is two repeating gradients.
        "css": """
:root[data-theme="steampunk"] h1,
:root[data-theme="steampunk"] h2,
:root[data-theme="steampunk"] .cname,
:root[data-theme="steampunk"] #clock {
  font-family: "Bitstream Charter", "Charter", "Georgia",
               "Liberation Serif", "Times New Roman", serif !important;
  letter-spacing: .02em;
}
:root[data-theme="steampunk"] h1,
:root[data-theme="steampunk"] h2 {
  border-bottom: 2px solid rgb(192 138 53 / .45);
  padding-bottom: 6px;
  text-shadow: 0 1px 0 rgb(0 0 0 / .6);
}
:root[data-theme="steampunk"] body {
  background-image:
    repeating-linear-gradient(115deg, rgb(255 231 178 / .028) 0 2px,
                              rgb(0 0 0 / 0) 2px 5px),
    radial-gradient(circle at 50% 0%, rgb(192 138 53 / .10), transparent 62%);
  background-attachment: fixed;
}
""",
        "qss": """
QLineEdit#urlbar, QMenu, QToolButton#groupbtn {
    font-family: "Bitstream Charter", "Charter", "Georgia",
                 "Liberation Serif", serif;
}
""",
    },

    "terminal": {
        "css": """
:root[data-theme="terminal"] body, :root[data-theme="terminal"] * {
  font-family: "JetBrainsMono Nerd Font", "DejaVu Sans Mono",
               "Liberation Mono", monospace !important;
}
:root[data-theme="terminal"] h1, :root[data-theme="terminal"] h2,
:root[data-theme="terminal"] body:not(.hasbg) #clock {
  text-shadow: 0 0 8px rgb(51 255 102 / .55);
}
:root[data-theme="terminal"] body {
  background-image: repeating-linear-gradient(rgb(0 0 0 / .22) 0 1px,
                                              rgb(0 0 0 / 0) 1px 3px);
  background-attachment: fixed;
}
""",
    },

    "amber": {
        "css": """
:root[data-theme="amber"] body, :root[data-theme="amber"] * {
  font-family: "JetBrainsMono Nerd Font", "DejaVu Sans Mono",
               "Liberation Mono", monospace !important;
}
:root[data-theme="amber"] h1, :root[data-theme="amber"] h2,
:root[data-theme="amber"] body:not(.hasbg) #clock {
  text-shadow: 0 0 9px rgb(255 176 0 / .5);
}
:root[data-theme="amber"] body {
  background-image: repeating-linear-gradient(rgb(0 0 0 / .24) 0 1px,
                                              rgb(0 0 0 / 0) 1px 3px);
  background-attachment: fixed;
}
""",
    },

    "blueprint": {
        "css": """
:root[data-theme="blueprint"] h1, :root[data-theme="blueprint"] h2,
:root[data-theme="blueprint"] #clock {
  font-family: "JetBrainsMono Nerd Font", "DejaVu Sans Mono", monospace
               !important;
  text-transform: uppercase; letter-spacing: .08em;
}
:root[data-theme="blueprint"] body {
  background-image:
    repeating-linear-gradient(rgb(214 233 255 / .07) 0 1px,
                              rgb(0 0 0 / 0) 1px 28px),
    repeating-linear-gradient(90deg, rgb(214 233 255 / .07) 0 1px,
                              rgb(0 0 0 / 0) 1px 28px);
  background-attachment: fixed;
}
""",
    },

    "synthwave": {
        "css": """
:root[data-theme="synthwave"] h1, :root[data-theme="synthwave"] h2,
:root[data-theme="synthwave"] body:not(.hasbg) #clock {
  text-shadow: 0 0 2px rgb(255 126 219 / .9), 0 0 14px rgb(255 126 219 / .6);
}
:root[data-theme="synthwave"] body {
  background-image:
    linear-gradient(rgb(0 0 0 / 0) 55%, rgb(255 126 219 / .07)),
    repeating-linear-gradient(90deg, rgb(114 241 184 / .05) 0 1px,
                              rgb(0 0 0 / 0) 1px 42px);
  background-attachment: fixed;
}
""",
    },

    "gameboy": {
        "css": """
:root[data-theme="gameboy"] body, :root[data-theme="gameboy"] * {
  font-family: "JetBrainsMono Nerd Font", "DejaVu Sans Mono", monospace
               !important;
}
:root[data-theme="gameboy"] img { image-rendering: pixelated; }
:root[data-theme="gameboy"] body {
  background-image: repeating-linear-gradient(rgb(11 40 11 / .16) 0 1px,
                                              rgb(0 0 0 / 0) 1px 2px);
  background-attachment: fixed;
}
""",
    },

    "c64": {
        "css": """
:root[data-theme="c64"] body, :root[data-theme="c64"] * {
  font-family: "JetBrainsMono Nerd Font", "DejaVu Sans Mono", monospace
               !important;
  letter-spacing: .04em;
}
""",
    },

    "sepia": {
        "css": """
:root[data-theme="sepia"] body, :root[data-theme="sepia"] h1,
:root[data-theme="sepia"] h2, :root[data-theme="sepia"] p {
  font-family: "Bitstream Charter", "Charter", "Georgia",
               "Liberation Serif", "Times New Roman", serif !important;
}
:root[data-theme="sepia"] body {
  background-image:
    repeating-linear-gradient(78deg, rgb(120 92 48 / .035) 0 2px,
                              rgb(0 0 0 / 0) 2px 6px);
  background-attachment: fixed;
}
""",
        "qss": """
QLineEdit#urlbar, QMenu {
    font-family: "Bitstream Charter", "Charter", "Georgia",
                 "Liberation Serif", serif;
}
""",
    },

    "newspaper": {
        "css": """
:root[data-theme="newspaper"] body, :root[data-theme="newspaper"] h1,
:root[data-theme="newspaper"] h2, :root[data-theme="newspaper"] p {
  font-family: "Bitstream Charter", "Charter", "Georgia",
               "Liberation Serif", "Times New Roman", serif !important;
}
:root[data-theme="newspaper"] h1 {
  border-top: 3px double rgb(26 26 26 / .8);
  border-bottom: 3px double rgb(26 26 26 / .8);
  padding: 8px 0; letter-spacing: .04em;
}
:root[data-theme="newspaper"] h2 {
  border-bottom: 1px solid rgb(26 26 26 / .5); padding-bottom: 5px;
}
""",
        "qss": """
QLineEdit#urlbar, QMenu {
    font-family: "Bitstream Charter", "Charter", "Georgia",
                 "Liberation Serif", serif;
}
""",
    },
}


def _build_themes():
    themes = []
    for row in _CATALOGUE:
        (key, name, group, note, bg, surface, text,
         accent, green, yellow, peach, red) = row
        entry = {"key": key, "name": name, "group": group, "note": note,
                 "bg": bg, "surface": surface, "text": text,
                 "accent": accent, "green": green, "yellow": yellow,
                 "peach": peach, "red": red}
        entry.update(_THEME_EXTRAS.get(key, {}))
        entry["dark"] = group != "light" and _luma(bg) < 0.5
        themes.append(entry)
    return themes


THEMES = _build_themes()
THEME_INDEX = {t["key"]: t for t in THEMES}
THEME_GROUPS = ["dark", "light", "character"]


# the address bar's suggestion list is a popup of its own and does not
# take the application sheet, so it carries a copy that is tinted along
# with everything else
COMPLETER_QSS = """
            QListView {
                background: #0d0d12; color: #cdd6f4;
                border: 1px solid rgba(108, 112, 134, 110);
                border-radius: 10px; padding: 4px; outline: 0;
            }
            QListView::item { padding: 6px 10px; border-radius: 7px; }
            QListView::item:selected { background: #16161d; color: #ffffff; }
        """


class GroupMenu(QMenu):
    """The book-button menu; right-clicking a group offers to delete it."""

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            action = self.actionAt(event.position().toPoint())
            group = action.data() if action else None
            if group:
                sub = QMenu(self)
                delete = sub.addAction("Delete \u201c%s\u201d" % group)
                chosen = sub.exec(event.globalPosition().toPoint())
                if chosen is delete:
                    self.browser.delete_group(group)
                self.close()
                return
        super().mouseReleaseEvent(event)


class GroupTabBar(QTabBar):
    """Chrome-style painting: group headers as colored pills, group
    members with a colored underline."""

    def __init__(self, browser):
        super().__init__()
        self.browser = browser

    def _tabs(self):
        return getattr(self.browser, "tabs", None)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        tabs = self._tabs()
        w = tabs.widget(index) if tabs else None
        if w is not None and getattr(w, "group_header", None) is not None:
            width = self.fontMetrics().horizontalAdvance(w.group_header) + 30
            return QSize(max(width, 44), size.height())
        if tabs is None:
            return QSize(min(max(size.width(), 160), 240), size.height())
        # tabs share the bar width and shrink as more open, like Chrome
        members = 0
        pills = 0
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            wi = tabs.widget(i)
            if wi is None:
                continue
            if getattr(wi, "group_header", None) is not None:
                pills += (self.fontMetrics().horizontalAdvance(wi.group_header)
                          + 30 + 6)
            else:
                members += 1
        available = self.width() - pills - 46  # room for the + button
        share = available // max(1, members) - 6  # per-tab margins
        return QSize(max(34, min(240, share)), size.height())

    def tabLayoutChange(self):
        super().tabLayoutChange()
        if getattr(self.browser, "tabs", None):
            update = getattr(self.browser, "_update_close_buttons", None)
            if update is not None:
                update()
            place = getattr(self.browser, "_place_newtab", None)
            if place is not None:
                place()

    def paintEvent(self, event):
        super().paintEvent(event)
        tabs = self._tabs()
        if tabs is None:
            return
        painter = QPainter(self)
        for i in range(self.count()):
            if not self.isTabVisible(i):
                continue
            w = tabs.widget(i)
            if w is None:
                continue
            rect = self.tabRect(i)
            header = getattr(w, "group_header", None)
            if header is not None:
                color = QColor(self.browser.group_colors.get(
                    header, theme_color("overlay")))
                pill = rect.adjusted(3, 8, -3, -10)
                painter.fillRect(pill, color)
                painter.setPen(QColor(readable_on(color.name())))
                painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, header)
            elif getattr(w, "private", False):
                # a private tab is never in a group, so this underline
                # can never be mistaken for one
                painter.fillRect(rect.x() + 2, rect.bottom() - 2,
                                 rect.width() - 4, 3,
                                 QColor(theme_color("bright")))
            else:
                group = getattr(w, "group", None)
                if group is not None:
                    color = QColor(self.browser.group_colors.get(group, "#6c7086"))
                    painter.fillRect(rect.x() + 2, rect.bottom() - 2,
                                     rect.width() - 4, 3, color)
        painter.end()


class TabWidget(QTabWidget):
    def __init__(self, browser):
        super().__init__()
        self.setTabBar(GroupTabBar(browser))


_QWC_SRC = None


def _qwebchannel_source():
    """qwebchannel.js out of Qt's resources, cached; prepended to the
    password watcher so the isolated world can open its channel."""
    global _QWC_SRC
    if _QWC_SRC is None:
        f = QFile(":/qtwebchannel/qwebchannel.js")
        if f.open(QFile.OpenModeFlag.ReadOnly):
            _QWC_SRC = bytes(f.readAll()).decode("utf-8")
            f.close()
        else:
            _QWC_SRC = ""
    return _QWC_SRC


def _write_private(path, data):
    """Write bytes with owner-only permissions (0600), creating the
    directory as needed; an existing file is clamped to 0600 too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)


def _keystream_xor(key, nonce, data):
    """XOR with a sha256-derived keystream. This is OBFUSCATION, not
    strong encryption — see the FileVaultBackend docstring."""
    out = bytearray(len(data))
    block = b""
    for i in range(len(data)):
        if i % 32 == 0:
            block = hashlib.sha256(
                key + nonce + (i // 32).to_bytes(8, "big")).digest()
        out[i] = data[i] ^ block[i % 32]
    return bytes(out)


def _write_atomic(path, data):
    """Replace a file in one step, owner-readable only.

    The vault is only ever swapped like this. The new contents are
    written beside it under a temporary name, pushed all the way down
    to the disk, and then moved onto the real name — and a rename
    within one directory is something the filesystem either did or did
    not do. There is no instant at which passwords.json is half of the
    old thing and half of the new one, which is what makes a migration
    that is interrupted by a power cut cost nothing: what survives is
    whichever whole file was there at the time.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".new")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp), str(path))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    try:                       # and the rename itself, for the same reason
        dirfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except OSError:
        pass
    return True


# ---- the master password ----
#
# Without one, the key to the vault is a random file lying next to it:
# anything running as this user can read both and therefore read every
# password. That is what FileVaultProvider's honest note is about, and
# a master password is the answer to it — the key stops being a file
# at all and is worked out, every time, from a passphrase that exists
# only in his head and only in this process while the vault is open.
#
# The parts, all of them out of the standard library:
#
#   scrypt turns the passphrase into a wrapping key. It is memory-hard
#   on purpose, so a machine trying words out of a list pays in RAM as
#   well as in time and cannot simply buy a thousand GPUs' worth of
#   parallelism. N=2**16 is 64 MB and about an eighth of a second on
#   this laptop: unnoticeable when you type it, ruinous at scale. The
#   parameters are written into the file next to the salt, so raising
#   them in five years' time costs one write and opens every older
#   vault on the way past.
#
#   HMAC-SHA256 in counter mode is the cipher, and HMAC-SHA256 over
#   the ciphertext is the seal — encrypt-then-MAC, which is the
#   composition without the sharp edges. There is no AES in the Python
#   standard library and none in Qt; the alternative was to depend on
#   `cryptography` for one call, which is a package to install, keep
#   patched and trust in a browser that so far needs none. A keystream
#   from a PRF and an encrypt-then-MAC seal are ordinary constructions
#   made of a primitive this file already uses, not something invented
#   here — the invention rule is why the KDF is scrypt and not a loop
#   of sha256.
#
# What it does not do: protect a vault that is open. While it is
# unlocked the key is in this process's memory, Python cannot reliably
# wipe it, and anything that can read this process can have it. That
# is what auto-lock is for. Locked, there is nothing on this computer
# that can produce the passwords.

#: the vault as it has always been: scrambled with the key file
VAULT_MAGIC = b"BPW1"
#: the vault under a master password
MASTER_MAGIC = b"BPW2"
#: a 1Password service-account token under the same key
TOKEN_MAGIC = b"BPT2"

KDF_NAME = "scrypt"
KDF_N = 1 << 16
KDF_R = 8
KDF_P = 1
#: 128 * N * r is 64 MB; scrypt refuses if maxmem is under what it needs
KDF_MAXMEM = 192 * 1024 * 1024
#: shorter than this is not a passphrase, and the box says so
MASTER_MIN = 8

OP_TOKEN_FILE = "1password-token"


def _derive_key(passphrase, salt, n=KDF_N, r=KDF_R, p=KDF_P):
    """The wrapping key for a passphrase. scrypt, from hashlib.

    Normalised to NFC first, and that is not a detail for the person
    typing it: "schön" typed on one keyboard is o-with-diaeresis as a
    single character, and on another it is a plain o followed by a
    combining diaeresis. They look identical on screen, they are
    different bytes, and without this they derive different keys — so
    a passphrase with an umlaut in it could be typed exactly right
    and rejected, for ever, with no way to tell why. Both spellings
    fold to the same one here."""
    text = unicodedata.normalize("NFC", str(passphrase))
    return hashlib.scrypt(text.encode("utf-8"), salt=salt,
                          n=int(n), r=int(r), p=int(p), dklen=32,
                          maxmem=KDF_MAXMEM)


def _subkeys(key):
    """One key in, two out: never encrypt and authenticate with the
    same bytes."""
    return (hmac.new(key, b"browser-vault-encrypt", hashlib.sha256).digest(),
            hmac.new(key, b"browser-vault-mac", hashlib.sha256).digest())


def _prf_stream(key, nonce, length):
    """HMAC-SHA256 counter mode: the keystream."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"),
                        hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def _xor(data, stream):
    return bytes(a ^ b for a, b in zip(data, stream))


def _seal(key, plaintext, aad=b""):
    """nonce || ciphertext || tag. Encrypt, then authenticate the
    ciphertext — and the label with it, so a wrapped key cannot be
    fed back in as a vault body."""
    enc, mac = _subkeys(key)
    nonce = os.urandom(16)
    body = _xor(plaintext, _prf_stream(enc, nonce, len(plaintext)))
    return nonce + body + hmac.new(mac, aad + nonce + body,
                                   hashlib.sha256).digest()


def _unseal(key, blob, aad=b""):
    """The plaintext, or None. None is the only thing a wrong key ever
    learns: the tag is checked before a single byte is decrypted, and
    it is checked in constant time."""
    if len(blob) < 48:
        return None
    nonce, body, tag = blob[:16], blob[16:-32], blob[-32:]
    enc, mac = _subkeys(key)
    if not hmac.compare_digest(
            hmac.new(mac, aad + nonce + body, hashlib.sha256).digest(), tag):
        return None
    return _xor(body, _prf_stream(enc, nonce, len(body)))


class VaultLock:
    """Locked and unlocked, and the two migrations between them.

    One object owns the vault file, whichever of the two shapes it is
    in, and the key while there is one. Everything else — the
    provider, the manager page, autofill — asks it `locked()` and gets
    on with its life.

    The two shapes are told apart by the file's own first four bytes,
    so the answer to "is there a master password?" comes out of the
    same file as the passwords do and cannot drift away from them the
    way a line in config.json could. A file that has been carried to
    another machine, or restored out of a backup, still says what it
    is.

    A master-locked file is:

        BPW2 | 4-byte header length | header (JSON) | sealed body

    The header is the salt, the KDF's parameters and the vault key
    wrapped under the passphrase. Both halves are in the one file, so
    both are swapped by the one os.replace — see _write_atomic, which
    is where the promise about interrupted migrations actually lives.
    """

    def __init__(self, directory):
        directory = Path(directory) if directory is not None else Path(".")
        self.dir = directory
        self.file = directory / "passwords.json"
        self.key_file = directory / "passwords.key"
        self.token_file = directory / OP_TOKEN_FILE
        #: the vault key while unlocked; None is the locked state, and
        #: it is the whole of the locked state
        self._vault_key = None
        self._used = time.monotonic()

    # ---- what is on the disk ----
    def _raw(self):
        try:
            return self.file.read_bytes()
        except OSError:
            return b""

    #: every shape of vault file this build can read. A newer build
    #: may write one that is not in here — see foreign().
    KNOWN_MAGIC = (VAULT_MAGIC, MASTER_MAGIC)

    def foreign(self):
        """Is there a vault here that this build does not understand?

        The master password added a second shape to this file, which
        makes the question live rather than theoretical: an older build
        meeting a BPW2 vault sees a magic it has never heard of. Left
        alone that ends in silence and total loss — the file reads as
        no passwords at all, and the next save replaces it with that
        nothing.

        So anything unaccounted for is refused: not read, not written
        over, and the manager says why. Refusing is recoverable — run
        the build that wrote it, or move the file aside. Guessing is
        not. The same guard is on main without a master password in
        sight, because it is what makes shipping this one safe."""
        try:
            head = self.file.read_bytes()[:4]
        except OSError:
            return False              # no file at all: a fresh install
        if not head:
            return False              # an empty file is nothing to lose
        return not head.startswith(self.KNOWN_MAGIC)

    def enabled(self):
        """Is there a master password? Four bytes off the front of the
        vault, which is cheap enough to ask on every page."""
        try:
            with open(self.file, "rb") as handle:
                return handle.read(4) == MASTER_MAGIC
        except OSError:
            return False

    def locked(self):
        return self.enabled() and self._vault_key is None

    def can_seal(self):
        """Unlocked, with a key to seal things under."""
        return self.enabled() and self._vault_key is not None

    def touch(self):
        """The vault was used. Auto-lock counts from here."""
        self._used = time.monotonic()

    def idle(self):
        return time.monotonic() - self._used

    def state(self):
        return {"on": self.enabled(), "locked": self.locked()}

    # ---- the file's two halves ----
    @staticmethod
    def _split(raw):
        """(header, sealed body), or (None, b"") for anything that is
        not a master-locked vault."""
        if not raw.startswith(MASTER_MAGIC) or len(raw) < 8:
            return None, b""
        size = int.from_bytes(raw[4:8], "big")
        if size <= 0 or size > 65536 or len(raw) < 8 + size:
            return None, b""
        try:
            head = json.loads(raw[8:8 + size].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, b""
        return (head if isinstance(head, dict) else None), raw[8 + size:]

    @staticmethod
    def _join(head, body):
        blob = json.dumps(head, separators=(",", ":")).encode()
        return MASTER_MAGIC + len(blob).to_bytes(4, "big") + blob + body

    def _unwrap(self, head, passphrase):
        """The vault key out of a header, or None when the passphrase
        is wrong.

        Wrong is only ever wrong: the seal fails, nothing is
        decrypted, nothing is written, and the caller is told no. A
        typo cannot damage a vault from in here."""
        # The header is outside the MAC, so nothing in it is trusted:
        # it is only ever checked. That is safe because every field
        # here feeds the derivation — change the name, the cost or the
        # salt and a different key comes out, and the wrap tag fails.
        # Checking it anyway means an unknown value is refused here,
        # plainly, rather than being a field a later version might
        # dispatch on. Never dispatch on it.
        if str(head.get("kdf", KDF_NAME)) != KDF_NAME:
            return None
        try:
            salt = base64.b64decode(head.get("salt", ""), validate=True)
            wrapped = base64.b64decode(head.get("wrapped", ""), validate=True)
            n = int(head.get("n", KDF_N))
            r = int(head.get("r", KDF_R))
            p = int(head.get("p", KDF_P))
        except (ValueError, TypeError):
            return None
        if len(salt) < 8 or len(wrapped) < 48 or not 1 < n <= (1 << 22):
            return None
        if not 0 < r <= 64 or not 0 < p <= 16:
            return None
        try:
            wrap = _derive_key(passphrase, salt, n, r, p)
        except (ValueError, MemoryError):
            return None
        return _unseal(wrap, wrapped, aad=b"vault-key")

    def _plain_key(self):
        """The key file, made if it is not there.

        Only ever reached when there is no master password: this is
        the old scheme, and it is the one the honest note on
        FileVaultProvider is about."""
        try:
            key = self.key_file.read_bytes()
        except OSError:
            key = b""
        if len(key) != 32:
            key = os.urandom(32)
            _write_private(self.key_file, key)
        return key

    def _tidy(self):
        """Leftovers of a migration that was cut off half way.

        The vault itself is never in doubt — one os.replace, so it is
        one file or the other — but switching on can be interrupted
        between replacing the vault and taking the old key file away,
        and that key file is the exact thing a master password exists
        to get rid of. It goes the moment anything looks at a locked
        vault. Half-written temporary files go with it: they are named
        for their target and nothing reads them."""
        if self.enabled():
            try:
                self.key_file.unlink()
            except OSError:
                pass
        for path in (self.file, self.key_file):
            try:
                path.with_name(path.name + ".new").unlink()
            except OSError:
                pass

    # ---- locking ----
    def unlock(self, passphrase):
        """Try a passphrase. True only when it opened the vault as
        well as the key — a header that unwraps but a body that will
        not is a damaged file, not an unlocked one, and saying yes to
        it would hand back an empty vault that the next write would
        make true."""
        head, body = self._split(self._raw())
        if head is None:
            return False
        key = self._unwrap(head, passphrase)
        if key is None or _unseal(key, body, aad=MASTER_MAGIC) is None:
            return False
        self._vault_key = key
        self.touch()
        self._tidy()
        return True

    def lock(self):
        """Forget the key. Everything that could read a password goes
        with it, because the key was the only copy."""
        self._vault_key = None

    # ---- the vault itself ----
    def read(self):
        """The snapshot, or {} — locked, missing, or unreadable all
        answer the same way. It is the caller's job never to write {}
        back over a vault it could not read, and write() below is
        where that is actually enforced."""
        raw = self._raw()
        if not raw:
            return {}
        if raw.startswith(MASTER_MAGIC):
            self._tidy()
            if self._vault_key is None:
                return {}
            head, body = self._split(raw)
            if head is None:
                return {}
            plain = _unseal(self._vault_key, body, aad=MASTER_MAGIC)
            if plain is None:
                return {}
            try:
                data = json.loads(plain)
            except (ValueError, UnicodeDecodeError):
                return {}
            return data if isinstance(data, dict) else {}
        if not raw.startswith(VAULT_MAGIC) or len(raw) < 20:
            return {}
        nonce, body = raw[4:20], raw[20:]
        try:
            data = json.loads(_keystream_xor(self._plain_key(), nonce, body))
        except (ValueError, UnicodeDecodeError):
            return {}   # wrong or lost key file: start over, never crash
        return data if isinstance(data, dict) else {}

    def write(self, data):
        """Persist the snapshot in whichever shape the vault is in.

        Locked, this refuses. It is the last line: the vault a locked
        browser holds in memory is empty, so anything that reached a
        save with the vault locked would write emptiness over every
        password there is. Nothing should get this far — the callers
        all check — and it says no anyway."""
        if self.foreign():
            return False       # not ours to replace: see foreign()
        if self.enabled():
            if self._vault_key is None:
                return False
            self.touch()
            return self._write_master(data, self._vault_key, None)
        nonce = os.urandom(16)
        body = _keystream_xor(self._plain_key(), nonce,
                              json.dumps(data).encode())
        return _write_atomic(self.file, VAULT_MAGIC + nonce + body)

    def _write_master(self, data, key, head):
        """One sealed vault, header and body together, in one step."""
        if head is None:
            head, _ = self._split(self._raw())
        if head is None:
            return False
        body = _seal(key, json.dumps(data).encode(), aad=MASTER_MAGIC)
        return _write_atomic(self.file, self._join(head, body))

    def _install(self, data, passphrase):
        """Seal a snapshot under a brand-new key and a brand-new salt,
        and make that the vault. Returns the key, or None."""
        salt = os.urandom(16)
        try:
            wrap = _derive_key(passphrase, salt)
        except (ValueError, MemoryError):
            return None
        key = os.urandom(32)
        head = {"kdf": KDF_NAME, "n": KDF_N, "r": KDF_R, "p": KDF_P,
                "salt": base64.b64encode(salt).decode(),
                "wrapped": base64.b64encode(
                    _seal(wrap, key, aad=b"vault-key")).decode()}
        if not self._write_master(data, key, head):
            return None
        return key

    # ---- the two migrations ----
    def enable(self, passphrase):
        """Switch a master password on.

        The vault is read with the key that is on the disk, a brand-new
        vault key is made, everything is written back sealed under it,
        and only then is the old key file taken away.

        A new key rather than the old one on purpose. The key file may
        be in a backup, on a stick, in a filesystem snapshot; keeping
        it would mean the vault he just locked can still be opened by
        something he threw away last year.

        Interrupted anywhere, this leaves a vault that opens. Before
        the swap: the old file and the old key file, untouched. After
        it: the new file and the passphrase. There is no third state,
        because the swap is one os.replace — and if the power goes
        between the swap and the unlink, the stale key file opens
        nothing and _tidy takes it on the next look."""
        if self.enabled() or not passphrase or self.foreign():
            return False
        data = self.read()
        token = self._token_plain()
        key = self._install(data, passphrase)
        if key is None:
            return False
        self._vault_key = key
        self.touch()
        self._token_store(token)
        self._tidy()
        return True

    def disable(self):
        """Switch it off again, with everything still in it.

        The order is enable's, backwards, for the same reason: the new
        key file is written first and the vault second, so at every
        instant the file on the disk has something that can open it —
        before the swap the sealed vault and the passphrase, after it
        the scrambled vault and the key file beside it. A cut power in
        between costs one unused random file.

        Only from unlocked. Switching off is not a way round the
        passphrase; it needs the vault open, which needs the
        passphrase."""
        if not self.enabled() or self._vault_key is None:
            return False
        data = self.read()
        token = self._token_plain()
        key = os.urandom(32)
        if not _write_atomic(self.key_file, key):
            return False
        nonce = os.urandom(16)
        body = _keystream_xor(key, nonce, json.dumps(data).encode())
        if not _write_atomic(self.file, VAULT_MAGIC + nonce + body):
            return False
        self._vault_key = None
        self._token_store(token)
        return True

    def change(self, old, new):
        """A different passphrase, without re-entering one password.

        Nothing stored is retyped and nothing is asked of him twice:
        the old passphrase has to unwrap the current key — that is the
        check, and it works whether the vault is open or not — and then
        the whole thing is written back under a fresh salt and a fresh
        vault key. Fresh because a copy of yesterday's file should not
        open with tomorrow's passphrase, nor the other way round."""
        if not self.enabled() or not new:
            return False
        head, body = self._split(self._raw())
        if head is None:
            return False
        key = self._unwrap(head, old)
        if key is None:
            return False
        plain = _unseal(key, body, aad=MASTER_MAGIC)
        if plain is None:
            return False
        try:
            data = json.loads(plain)
        except (ValueError, UnicodeDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        fresh = self._install(data, new)
        if fresh is None:
            return False
        self._vault_key = fresh
        self.touch()
        return True

    # ---- the 1Password token, which is a secret on this computer ----
    #
    # A master password cannot lock 1Password: those secrets are
    # theirs, and the service account can be used from any machine
    # that holds the token. What it can do is stop THIS machine being
    # the easy way in. The token is sealed under the same key, so a
    # locked browser cannot speak for him to 1Password either, and the
    # token file on its own is ciphertext.
    def _token_plain(self):
        """The token as bytes, unsealed if it needs it, b"" if there
        is none or it cannot be read."""
        try:
            raw = self.token_file.read_bytes()
        except OSError:
            return b""
        return self.open_token(raw) or b""

    def open_token(self, raw):
        """A token file's contents. A file from before this feature is
        not sealed and is handed straight back; that is also what
        happens to one an interrupted migration left plain."""
        if not raw.startswith(TOKEN_MAGIC):
            return raw
        if self._vault_key is None:
            return None
        return _unseal(self._vault_key, raw[len(TOKEN_MAGIC):],
                       aad=TOKEN_MAGIC)

    def seal_token(self, data):
        return TOKEN_MAGIC + _seal(self._vault_key, data, aad=TOKEN_MAGIC)

    def _token_store(self, data):
        """Put the token back in whichever shape now matches the
        vault. Losing it is survivable — the box that asks for it says
        so and he pastes it again — which is why this happens after
        the vault has already been swapped, never before."""
        if not data:
            return
        try:
            if self.can_seal():
                _write_private(self.token_file, self.seal_token(data))
            else:
                _write_private(self.token_file, data)
        except OSError:
            pass


# ---- password generator ----
GEN_LOWER = "abcdefghijkmnpqrstuvwxyz"      # no l, o
GEN_LOWER_AMBIG = "lo"
GEN_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"      # no I, O
GEN_UPPER_AMBIG = "IO"
GEN_DIGITS = "23456789"                     # no 0, 1
GEN_DIGITS_AMBIG = "01"
GEN_SYMBOLS = "!#$%&()*+,-./:;=?@[]^_{}~"


def generate_password(length=20, symbols=True, digits=True, upper=True,
                      ambiguous=False):
    """A random password from `secrets` — never `random`, whose output
    stream can be predicted from a few hundred of its own numbers.

    `ambiguous=False` drops the characters people misread off a screen
    or over the phone (l/1/I, O/0). The result always contains at least
    one character of every class that is switched on, which is what
    most sites' rules actually demand."""
    length = max(4, min(128, int(length)))
    classes = [GEN_LOWER + (GEN_LOWER_AMBIG if ambiguous else "")]
    if upper:
        classes.append(GEN_UPPER + (GEN_UPPER_AMBIG if ambiguous else ""))
    if digits:
        classes.append(GEN_DIGITS + (GEN_DIGITS_AMBIG if ambiguous else ""))
    if symbols:
        classes.append(GEN_SYMBOLS)
    pool = "".join(classes)
    while True:
        out = [secrets.choice(pool) for _ in range(length)]
        if all(any(c in group for c in out) for group in classes):
            return "".join(out)


# ---- two-factor codes (TOTP, RFC 6238) ----
def _b32_decode(secret):
    """Base32 the way authenticator apps print it: any case, spaces and
    dashes anywhere, padding optional — and that means optional in both
    directions. A secret that arrives already padded ("JBSW...PXP====")
    is not an error: the padding is stripped with everything else and
    put back to the length b32decode insists on."""
    text = re.sub(r"[\s=-]", "", str(secret or "")).upper()
    text += "=" * (-len(text) % 8)
    return base64.b32decode(text)


def parse_otpauth(text):
    """An `otpauth://totp/...` URI (what the QR code on a site's
    two-factor page actually contains) or a bare base32 secret ->
    {secret, digits, period, algorithm, issuer, label}, or None.
    Anything that is not decodable base32 is refused here rather than
    stored as a code that could never work."""
    text = str(text or "").strip()
    if not text:
        return None
    out = {"secret": text, "digits": 6, "period": 30, "algorithm": "sha1",
           "issuer": "", "label": ""}
    if "://" in text:
        url = QUrl(text)
        if url.scheme().lower() != "otpauth" or url.host().lower() != "totp":
            return None
        query = QUrlQuery(url.query())
        out["secret"] = query.queryItemValue("secret")
        out["label"] = url.path().lstrip("/")
        out["issuer"] = query.queryItemValue("issuer") or ""
        for name, low, high in (("digits", 6, 10), ("period", 5, 300)):
            if query.hasQueryItem(name):
                try:
                    out[name] = max(low, min(high,
                                             int(query.queryItemValue(name))))
                except ValueError:
                    pass
        algorithm = (query.queryItemValue("algorithm") or "sha1").lower()
        if algorithm in ("sha1", "sha256", "sha512"):
            out["algorithm"] = algorithm
    try:
        if not _b32_decode(out["secret"]):
            return None
    except Exception:
        return None
    return out


def totp_code(secret, at=None, digits=6, period=30, algorithm="sha1"):
    """The code showing right now. Straight RFC 6238: HMAC over the
    time step, then the standard dynamic truncation. Proven against
    that RFC's own published vectors in test_vault.py."""
    counter = int((time.time() if at is None else at) // period)
    digest = hmac.new(_b32_decode(secret), struct.pack(">Q", counter),
                      getattr(hashlib, algorithm)).digest()
    offset = digest[-1] & 0x0f
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return str(code % (10 ** digits)).zfill(digits)


def totp_remaining(period=30, at=None):
    """Seconds until the current code rolls over."""
    return period - ((time.time() if at is None else at) % period)


# ---- password health: entirely offline. There is no breach API here
# and no network call of any kind — reuse is worked out against this
# vault alone, strength from the password's own shape. ----
PW_OLD_DAYS = 365


def password_strength(password):
    """A rough bits-of-entropy estimate: how big a character pool the
    password draws from, times how much of it is actually varied. An
    estimate, not a measurement — a passphrase of four common words
    scores well here and would still fall to a dictionary attack — so
    it is only ever used to sort passwords into weak/fair/strong, never
    shown as a promise about anything."""
    if not password:
        return 0
    pool = 0
    for pattern, size in ((r"[a-z]", 26), (r"[A-Z]", 26), (r"[0-9]", 10),
                          (r"[^A-Za-z0-9]", 32)):
        if re.search(pattern, password):
            pool += size
    # "aaaaaaaaaaaaaaaa" is not as strong as its length suggests
    length = min(len(password), len(set(password)) * 3)
    return int(length * math.log2(pool or 1))


class BackgroundCall(QObject):
    """Run one slow thing off the GUI thread and deliver the answer
    back on it.

    `op` is a subprocess that talks to a server on the other side of
    the internet; calling it straight from a slot would freeze the
    window for as long as it takes. The worker thread does the call and
    the signal carries the result home — Qt queues it onto the GUI
    thread by itself, which is the only safe way back."""

    done = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self, then):
        self.done.connect(then)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result = self._fn()
        except Exception:      # a provider blowing up must not take
            result = None      # the browser with it
        try:
            self.done.emit(result)
        except RuntimeError:
            pass               # the window went away while we worked


class VaultProvider:
    """Where the secrets actually live.

    Deliberately narrow. Everything above it — the item model, search,
    health, TOTP, import/export, the manager page — is written against
    PasswordVault and knows nothing about files, scrambling, CLIs or
    tokens. A new place to keep secrets means implementing this and
    nothing else.

    Two shapes of provider are supported, and `eager` says which:

    * eager (the file vault): `load` returns every item with its
      secrets in place and `save` writes the whole snapshot back.
    * lazy (anything remote): `load` returns the items WITHOUT their
      secrets — enough to draw the list — and each secret is fetched
      one at a time through `secret`, which may be slow and therefore
      is never called on the GUI thread.
    """

    name = "none"
    #: does load() bring the secrets with it?
    eager = True
    #: can this provider answer TOTP itself, or do we compute it?
    native_totp = False
    #: is a master password shut over it right now? A locked provider
    #: hands out nothing and takes nothing: load() is empty and save()
    #: refuses, so an empty vault can never be written over a full one.
    locked = False


    def status(self):
        """{"ok": bool, "reason": str} — plain words, shown to the user
        as-is when something is wrong. Never contains a token, and
        never blocks: it is called straight from the GUI thread."""
        return {"ok": True, "reason": ""}

    def load(self):
        """The whole snapshot: {"items": [...], "never": [...]}."""
        return {}

    def save(self, data):
        """Whole-snapshot write. Eager providers only."""
        return False

    def put(self, item):
        """Create or update one item. Lazy providers only. Returns the
        stored item (with its id filled in) or None on failure."""
        return None

    def delete(self, item_id):
        """Remove one item. Lazy providers only."""
        return False

    def secret(self, item_id, field):
        """One named secret. Lazy providers only; may block, so it is
        always called from a worker thread. Returns None when the store
        could not produce it — which is a different answer from "" and
        must not be shown as an empty password."""
        return ""

    def probe(self):
        """Go and find out whether this provider works, however long
        that takes. Worker thread only; status() is the cheap, cached
        answer the GUI thread is allowed to ask for."""
        return self.status()

    def totp(self, item_id):
        """The current code, when the provider can produce one itself."""
        return ""


class FileVaultProvider(VaultProvider):
    """The vault as a file next to the config — the default, and the
    one in use unless another provider was chosen.

    Two ways of keeping it, and VaultLock owns both.

    Without a master password, which is still what an install gets
    until he asks for one: the file is XOR-scrambled with a random
    per-install key file and both are chmod 0600. That keeps passwords
    out of casual greps and plain-text backups, and it is worth saying
    plainly that it is no more than that — the key is lying next to
    the lock, so anyone who can read this user's files can decode it.
    The OS user account is the boundary.

    With one: the key is derived from a passphrase and is on the disk
    nowhere at all. See VaultLock.
    """

    MAGIC = VAULT_MAGIC
    name = "file"
    eager = True

    def __init__(self, directory, lock=None):
        self.lock = lock if lock is not None else VaultLock(directory)
        self.file = self.lock.file
        self.key_file = self.lock.key_file

    @property
    def locked(self):
        return self.lock.locked()

    def foreign(self):
        """A vault here that this build does not understand. The lock
        owns the file and both of its shapes, so it is the one that
        knows; this is here because the provider is what the pages
        ask."""
        return self.lock.foreign()

    def status(self):
        if self.foreign():
            return {"ok": False, "reason": "vault-newer"}
        return {"ok": True, "reason": ""}

    def load(self):
        return self.lock.read()

    def save(self, data):
        return self.lock.write(data)


OP_CATEGORIES = {"login": "LOGIN", "note": "SECURE_NOTE",
                 "card": "CREDIT_CARD", "identity": "IDENTITY"}
OP_KINDS = {v: k for k, v in OP_CATEGORIES.items()}


class OnePasswordProvider(VaultProvider):
    """Secrets kept in 1Password, reached through the official `op`
    command-line tool with a service-account token.

    Why the CLI and not the desktop app: a service account needs no
    desktop app and no browser sign-in, which is the only way this
    works with the browser on Linux and the vault administered from
    Windows.

    How the token is handled, and this is the whole security story of
    this class:

    * it lives in its own file, chmod 0600, next to the config — never
      in config.json, never in the repo, never in a widget;
    * it is read at the moment of use and passed to `op` through the
      environment, never as a command-line argument, because argv is
      world-readable in `ps`;
    * it never appears in a log line, an exception message, an export
      or anything a page can ask for. `status()` reports whether a
      token is present, never a single byte of it;
    * a token file that could never be one — a NUL byte in it, a
      UTF-16 paste, half a line — is refused here rather than carried
      into subprocess.run, which would raise on the way past and take
      the whole startup with it.

    The stored secrets get the same treatment: an item's values are
    handed to `op` as a JSON template on its standard input, never as
    `password=…` in argv, for exactly the reason above.

    Every `op` call is a subprocess with a timeout, and every one of
    them blocks — so every one of them is issued from a worker thread.
    `status()` is the single exception and the reason it exists: it
    answers from the last real check and never shells out, so the GUI
    thread can ask it freely. `probe()` is the one that goes and looks.

    If `op` is missing, the token is absent, or the service account
    has been revoked, `probe()` says so in plain words and the browser
    falls back to the file vault — it never hangs, never crashes at
    startup and never writes to the wrong place.
    """

    name = "1password"
    eager = False
    native_totp = True
    TIMEOUT = 20

    @property
    def locked(self):
        return self.lock is not None and self.lock.locked()

    def __init__(self, directory, vault_name="", binary="op", lock=None):
        self.token_file = directory / OP_TOKEN_FILE
        #: the master password, when there is one. It does not lock
        #: 1Password — nothing here could — but it locks this
        #: computer's way in: the token is sealed with the vault and
        #: `op` is never run while that seal is shut.
        self.lock = lock
        self.vault_name = vault_name or ""
        self.binary = binary or "op"
        self.last_error = ""
        self._cache = None          # last good snapshot
        self._probe = None          # (ok, reason) once worked out
        self._down = ""             # it stopped answering since then
        self._bad_token = False     # there is one, but it is unusable

    # ---- token ----
    def token(self):
        """Read at use time. Returns "" when there is none — and also
        when what is there could not possibly be one.

        That second case is the whole point of this being careful:
        read_text() on a UTF-16 paste raises UnicodeDecodeError, and a
        token with a NUL in it makes subprocess.run raise ValueError
        as it builds the environment. This is reached from
        Browser.__init__ by way of make_vault, so either of those
        would mean no window at all — a truncated paste into a file
        must cost an honest message on the passwords page, not the
        browser."""
        self._bad_token = False
        try:
            raw = self.token_file.read_bytes()
        except OSError:
            return ""
        if raw.startswith(TOKEN_MAGIC):
            # sealed. Locked, that reads as no token at all rather than
            # as a broken one: there is nothing wrong with the file.
            raw = (self.lock.open_token(raw) or b"") if self.lock else b""
        try:
            # utf-8-sig: a token pasted on Windows — which is where this
            # tenant is administered from — arrives with a byte-order
            # mark in front of it, and prepending that to the token
            # buys an authentication error instead of a working store
            text = raw.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            self._bad_token = True
            return ""
        if not text:
            self._bad_token = bool(raw.strip())
            return ""
        # one line of printable characters is the whole shape of a
        # service-account token; anything else is a broken paste
        if any(ord(c) < 0x20 or ord(c) == 0x7f or c == "\ufeff"
               for c in text):
            self._bad_token = True
            return ""
        return text

    def _no_token_reason(self):
        return "bad-token" if self._bad_token else "no-token"

    #: failures that mean the store itself is not reachable, as opposed
    #: to one item not being there or having no one-time password
    STORE_DOWN = ("no-token", "bad-token", "no-op", "timeout")
    AUTH_GONE = re.compile(r"authenticat|not authori[sz]ed|is ?n.t valid",
                           re.I)

    def _note_failure(self, reason):
        """A failure that says the store is gone, not that one item is.

        The cached "everything is fine" is dropped, so the header stops
        saying it the moment a revoked token starts failing every
        fetch, and the next probe from a worker thread finds out
        whether it has come back."""
        text = str(reason)
        if text in self.STORE_DOWN or self.AUTH_GONE.search(text):
            self._probe = None
            self._down = text
        return reason

    def have_token(self):
        return bool(self.token())

    def write_token(self, text):
        """Store a service-account token, owner-readable only."""
        text = (text or "").strip()
        if not text:
            try:
                self.token_file.unlink()
            except OSError:
                pass
            self._probe = None
            return True
        blob = text.encode()
        if self.lock is not None and self.lock.can_seal():
            blob = self.lock.seal_token(blob)
        try:
            _write_private(self.token_file, blob)
        except OSError:
            return False
        self._probe = None
        return True

    # ---- running op ----
    def _run(self, args, want_json=True, stdin=None):
        """One `op` call. Returns (ok, payload). The token goes in the
        environment and an item's values go in on standard input;
        nothing secret is ever put in argv or in the error text we
        keep.

        Blocks for up to TIMEOUT seconds, so: worker thread only."""
        def fail(reason):
            return (False, self._note_failure(reason))
        token = self.token()
        if not token:
            return fail(self._no_token_reason())
        env = dict(os.environ)
        env["OP_SERVICE_ACCOUNT_TOKEN"] = token
        env["OP_FORMAT"] = "json"
        # a service account must never be asked to open a browser
        env.pop("OP_CONNECT_HOST", None)
        env.pop("OP_CONNECT_TOKEN", None)
        try:
            done = subprocess.run(
                [self.binary] + list(args), env=env, capture_output=True,
                text=True, timeout=self.TIMEOUT, check=False,
                # always a pipe, even when there is nothing to send, so
                # `op` never inherits a terminal and never waits on one
                input=stdin if stdin is not None else "")
        except FileNotFoundError:
            return fail("no-op")
        except subprocess.TimeoutExpired:
            return fail("timeout")
        except ValueError:
            # something unusable got as far as the environment or the
            # argument list: refuse the call, never raise out of it
            return fail("bad-token")
        except OSError as exc:
            return fail("failed: %s" % exc.strerror)
        if done.returncode != 0:
            # op's own message, trimmed. It never echoes the token, but
            # keep it short so nothing long gets copied around either.
            message = (done.stderr or "").strip().splitlines()
            return fail(message[-1][:200] if message else "failed")
        if not want_json:
            return (True, (done.stdout or "").strip())
        try:
            return (True, json.loads(done.stdout or "null"))
        except ValueError:
            return fail("bad-json")

    def _vault_args(self):
        return ["--vault", self.vault_name] if self.vault_name else []

    def status(self):
        """Is this provider usable right now? Answered from the last
        real check and nothing else — this is called from the GUI
        thread and must not shell out, so before anything has looked
        it honestly says "still checking" rather than blocking to find
        out."""
        if self._probe is None:
            return {"ok": False, "reason": self._down or "checking"}
        return {"ok": self._probe[0], "reason": self._probe[1]}

    def probe(self):
        """Go and look: `op whoami`, which is a subprocess and a round
        trip to 1Password. Worker thread only. Cached afterwards, so
        the page does not shell out on every render."""
        if self._probe is None:
            self._down = ""
            if not shutil.which(self.binary):
                self._probe = (False, "op-missing")
            elif not self.have_token():
                self._probe = (False, self._no_token_reason())
            else:
                ok, payload = self._run(["whoami"])
                self._probe = (True, "") if ok else (False, str(payload))
        return self.status()

    def forget_status(self):
        self._probe = None
        self._down = ""

    # ---- reading ----
    def load(self):
        """`op item list` — titles, usernames and URLs, no secrets. On
        any failure the last good snapshot is returned unchanged rather
        than an empty vault, so a dropped network never looks like
        "everything is gone"."""
        state = self.probe()
        if not state["ok"]:
            self.last_error = state["reason"]
            return self._cache or {}
        ok, payload = self._run(["item", "list", "--format", "json"]
                                + self._vault_args())
        if not ok or not isinstance(payload, list):
            self.last_error = str(payload)
            return self._cache or {}
        self.last_error = ""
        items = [self._from_op_summary(entry) for entry in payload]
        self._cache = {"items": [i for i in items if i],
                       "never": (self._cache or {}).get("never", []),
                       "version": PasswordVault.VERSION}
        return self._cache

    def _from_op_summary(self, entry):
        """One row of `op item list` -> our item shape, secrets absent.
        `additional_information` is where op puts the username for a
        login and the last four digits for a card."""
        if not isinstance(entry, dict) or not entry.get("id"):
            return None
        kind = OP_KINDS.get(str(entry.get("category", "")).upper(), "note")
        urls = entry.get("urls") or []
        href = ""
        for url in urls:
            if isinstance(url, dict) and (url.get("primary") or not href):
                href = url.get("href", "") or href
        item = {"id": entry["id"], "type": kind,
                "title": entry.get("title", ""),
                "tags": list(entry.get("tags") or []),
                "fav": bool(entry.get("favorite")),
                "created": _op_time(entry.get("created_at")),
                "changed": _op_time(entry.get("updated_at")),
                "used": _op_time(entry.get("updated_at")),
                "remote": True}
        extra = str(entry.get("additional_information") or "")
        if kind == "login":
            item["host"], item["scheme"] = PasswordVault.parse_site(href)
            item["username"] = "" if extra == "—" else extra
            # secrets are not in the listing; the page needs to know
            # they exist so it can offer to reveal them
            item["hasPassword"] = True
            # `op item list` does not say whether there is a one-time
            # password on the item, and we are not fetching every item
            # just to find out — the page asks for the code and hides
            # the row when nothing comes back
            item["totpUnknown"] = True
        elif kind == "card":
            item["last4"] = extra[-4:] if extra else ""
            item["hasNumber"] = True
        elif kind == "note":
            item["hasBody"] = True
        return item

    def details(self, item_id):
        """`op item get` — the full item including its secrets. Only
        ever called from a worker thread."""
        ok, payload = self._run(["item", "get", str(item_id),
                                 "--format", "json"] + self._vault_args())
        if not ok or not isinstance(payload, dict):
            self.last_error = str(payload)
            return None
        self.last_error = ""
        return self._from_op_item(payload)

    def _from_op_item(self, entry):
        item = self._from_op_summary(entry) or {}
        fields = {}
        for field in (entry.get("fields") or []):
            if not isinstance(field, dict):
                continue
            key = str(field.get("id") or field.get("label") or "").lower()
            if field.get("value") is not None:
                fields[key] = str(field["value"])
        kind = item.get("type", "login")
        if kind == "login":
            item["username"] = fields.get("username", item.get("username", ""))
            item["password"] = fields.get("password", "")
            item["totp"] = fields.get("totp", "")
            item["hasPassword"] = bool(item["password"])
            item["hasTotp"] = bool(item["totp"])
        elif kind == "card":
            item["number"] = fields.get("ccnum", "")
            item["cvv"] = fields.get("cvv", "")
            item["cardholder"] = fields.get("cardholder", "")
            item["expiry"] = fields.get("expiry", "")
            item["brand"] = fields.get("type", "")
            item["hasNumber"] = bool(item["number"])
        elif kind == "note":
            item["body"] = fields.get("notesplain", "")
            item["hasBody"] = bool(item["body"])
        elif kind == "identity":
            for ours, theirs in (("fullname", "fullname"), ("email", "email"),
                                 ("phone", "defphone"), ("street", "address"),
                                 ("city", "city"), ("zip", "zip"),
                                 ("country", "country")):
                item[ours] = fields.get(theirs, "")
        item["note"] = fields.get("notesplain", item.get("note", ""))
        return item

    def secret(self, item_id, field):
        """None when op would not hand it over. The page has to be able
        to tell that apart from a field that is genuinely empty, or a
        failed fetch reads as "this password is blank"."""
        item = self.details(item_id)
        if item is None:
            return None
        value = item.get(field, "")
        return value if isinstance(value, str) else ""

    def totp(self, item_id):
        ok, payload = self._run(["item", "get", str(item_id), "--otp"]
                                + self._vault_args(), want_json=False)
        if not ok:
            self.last_error = str(payload)
            return ""
        return str(payload).strip()

    # ---- writing ----
    #: our field name -> (op's field id, op's type, op's purpose)
    OP_FIELDS = {
        "login": (("username", "username", "STRING", "USERNAME"),
                  ("password", "password", "CONCEALED", "PASSWORD"),
                  ("totp", "totp", "OTP", "")),
        "card": (("cardholder", "cardholder", "STRING", ""),
                 ("number", "ccnum", "CONCEALED", ""),
                 ("expiry", "expiry", "STRING", ""),
                 ("cvv", "cvv", "CONCEALED", ""),
                 ("brand", "type", "STRING", "")),
        "note": (("body", "notesPlain", "STRING", "NOTES"),),
        "identity": (("fullname", "fullname", "STRING", ""),
                     ("email", "email", "STRING", ""),
                     ("phone", "defphone", "STRING", ""),
                     ("street", "address", "STRING", ""),
                     ("city", "city", "STRING", ""),
                     ("zip", "zip", "STRING", ""),
                     ("country", "country", "STRING", "")),
    }

    def put(self, item):
        """Create or update, through op's JSON item template on its
        standard input — `op item create -` and the piped form of
        `op item edit`.

        The alternative, op's `password=<value>` assignment syntax, is
        an argument, and an argument is in `ps` for every process on
        this machine for as long as the call runs. That is the exact
        reasoning this class already applies to the service-account
        token; a password just typed into a form deserves no less.

        An edit reads the item back first and writes our changes into
        what op already has, so a field this browser does not model
        survives being edited from here untouched.

        A failure returns None and leaves the caller's copy of the item
        alone, so nothing he just typed is thrown away."""
        fields = self._fields_for(item)
        if item.get("id") and item.get("remote"):
            ok, current = self._run(["item", "get", str(item["id"]),
                                     "--format", "json"] + self._vault_args())
            if not ok or not isinstance(current, dict):
                self.last_error = str(current)
                return None
            document = self._merged(current, item, fields)
            args = (["item", "edit", str(item["id"]), "--format", "json"]
                    + self._vault_args())
        else:
            document = {
                "title": item.get("title") or item.get("host", ""),
                "category": OP_CATEGORIES.get(item.get("type", "login"),
                                              "LOGIN"),
                "fields": fields,
                "tags": [str(t) for t in (item.get("tags") or [])]}
            if item.get("type") == "login" and item.get("host"):
                document["urls"] = [
                    {"label": "website", "primary": True,
                     "href": "%s://%s/" % (item.get("scheme", "https"),
                                           item["host"])}]
            args = (["item", "create", "-", "--format", "json"]
                    + self._vault_args())
        ok, payload = self._run(args, stdin=json.dumps(document))
        if not ok:
            self.last_error = str(payload)
            return None
        self.last_error = ""
        self._cache = None       # next load picks the change up
        if isinstance(payload, dict) and payload.get("id"):
            return self._from_op_item(payload)
        return dict(item)

    @classmethod
    def _fields_for(cls, item):
        """op's own field shape for the values this item carries. An
        empty value is left out entirely, which is how op is told to
        leave what is already there alone."""
        out = []
        kind = item.get("type", "login")
        for ours, theirs, ftype, purpose in cls.OP_FIELDS.get(kind, ()):
            value = item.get(ours)
            if not value:
                continue
            field = {"id": theirs, "type": ftype, "label": theirs,
                     "value": str(value)}
            if purpose:
                field["purpose"] = purpose
            out.append(field)
        if item.get("note") and kind != "note":
            out.append({"id": "notesPlain", "type": "STRING",
                        "purpose": "NOTES", "label": "notesPlain",
                        "value": str(item["note"])})
        return out

    @staticmethod
    def _merged(current, item, fields):
        """The item op just gave us with our changes written into it,
        and anything this browser has no idea about left exactly as it
        was.

        "Our changes" has to mean everything the editor offers a box
        for, not just the fields. Writing only `fields` meant the Name
        and Tags boxes did nothing at all: op sent its own title and
        tags straight back, PasswordVault._save did item.update(stored)
        with them — reverting what was on screen too — and the page
        said "Saved ✓" over a rename that never happened."""
        existing = [dict(f) for f in (current.get("fields") or [])
                    if isinstance(f, dict)]
        index = {str(f.get("id", "")).lower(): f for f in existing}
        for field in fields:
            found = index.get(field["id"].lower())
            if found is None:
                existing.append(dict(field))
            else:
                found["value"] = field["value"]
        out = dict(current)
        out["fields"] = existing
        if "title" in item:
            out["title"] = str(item["title"])
        if "tags" in item:
            out["tags"] = [str(t) for t in (item["tags"] or [])]
        if item.get("type") == "login" and item.get("host"):
            out["urls"] = [{"label": "website", "primary": True,
                            "href": "%s://%s/" % (item.get("scheme", "https"),
                                                  item["host"])}]
        return out

    def delete(self, item_id):
        ok, payload = self._run(["item", "delete", str(item_id)]
                                + self._vault_args(), want_json=False)
        if not ok:
            self.last_error = str(payload)
            return False
        self.last_error = ""
        self._cache = None
        return True


def _op_time(text):
    """op's RFC 3339 timestamps -> unix seconds, 0 when unparseable."""
    if not text:
        return 0
    try:
        cleaned = str(text).replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(cleaned).timestamp())
    except (ValueError, TypeError):
        return 0


def scheme_of(parsed):
    """http or https out of a parsed URL; https for anything else, so
    a Site with no scheme in it is treated the way the web is."""
    return (parsed.scheme() if parsed.scheme() in ("http", "https")
            else "https")


class PasswordVault:
    """Everything the password manager knows how to do, over whatever
    VaultBackend it was handed: logins, secure notes, payment cards and
    identities, plus search, health, TOTP and import/export.

    The security of the stored secrets is entirely the backend's story
    — see FileVaultBackend, which is the one in use today, for exactly
    what that is worth.

    The stored shape is versioned (`version`), items carry a `type`,
    and both migrate() and the item normaliser leave fields they do not
    recognise alone. A future item type therefore costs one entry in
    TYPES and its default fields — not another migration.
    """

    VERSION = 2
    TYPES = ("login", "note", "card", "identity")

    def __init__(self, directory=None, provider=None):
        self.provider = provider if provider is not None \
            else FileVaultProvider(directory)
        #: the never-save list is ours, not the provider's — a remote
        #: vault has no idea which sites we decided not to ask about,
        #: and it is not a secret, so it lives in a small local file
        self.meta_file = ((directory or Path(".")) / "passwords-meta.json")
        self.data = self._empty()
        self._load()

    @property
    def locked(self):
        """Is a master password shut over the store? Everything above
        here asks this rather than the provider, because the answer is
        the same question whichever store is in use."""
        return bool(getattr(self.provider, "locked", False))

    def switch_provider(self, provider):
        """Point at a different store. Nothing is copied or moved: the
        new provider's contents are simply what he now sees.

        This loads, so it blocks for as long as the new provider takes
        — worker thread, or a provider known to be local. The GUI
        thread uses adopt() instead."""
        self.provider = provider
        self._load()

    def adopt(self, provider, snapshot):
        """Take on a provider whose status check and first load have
        already happened on a worker thread.

        This is the way a remote store arrives on the GUI thread: by
        the time anything here runs, the subprocess is finished and
        the snapshot is a plain dict, so nothing blocks.

        Refuses onto a locked vault, and says so. The callers check
        too, and this is the floor under them for the same reason
        _save has one: a snapshot arriving here carries the secrets
        themselves, so the cost of one caller forgetting is every
        password in a browser that is supposed to be holding none."""
        if bool(getattr(provider, "locked", False)):
            return False
        self.provider = provider
        self.data = self.migrate(snapshot or {})
        if not provider.eager:
            self.data["never"] = self._load_meta().get("never", [])
        return True

    @classmethod
    def _empty(cls):
        return {"version": cls.VERSION, "items": [], "never": []}

    #: a character no page's host can ever contain. A Site holding one
    #: came back out of parse_site untouched, because nothing
    #: host-shaped could be found in it.
    NOT_A_HOST = re.compile(r"[\s/\\?#@]")

    @staticmethod
    def parse_site(text, hand_typed=False):
        """What a site is called, out of whatever names it: a bare
        host, or the whole URL somebody pasted out of the address bar.
        Returns (host, scheme); the host is "" when there is none.

        This is the one place a URL is taken apart. The CSV import and
        the 1Password reader used to do it themselves and the Site box
        in the manager did not do it at all — a row saved as
        "https://login.live.com/" was stored with the slashes still on
        and could never equal a page's host, so it quietly filled
        nothing for ever.

        hand_typed is for the Site box, and only for it. A URL with
        something before an @ means the host after the @ —
        safe.com@evil.com is evil.com — and for a file an export wrote,
        or a store where he already keeps his logins, that reading is
        simply the right one: Chrome writes every Android login as
        android://<hash>@<package>/, and a router login really can have
        its credentials in the URL. Refusing those would throw away
        rows he has, which is worse than anything it would prevent.

        A line a person typed or pasted into a box himself is the one
        place it is worth not walking into: a row that has sat there
        matching nothing must not quietly come to life on a host that
        is not the one its Site appears to name. There it yields no
        host, keeps the text it had, and the manager says it never
        fills."""
        text = (text or "").strip()
        parsed = QUrl(text if "://" in text else "https://" + text)
        if hand_typed and parsed.userInfo():
            return "", scheme_of(parsed)
        host = (parsed.host() or "").strip().lower().removeprefix("www.")
        return host, scheme_of(parsed)

    @classmethod
    def normalize_host(cls, host):
        """parse_site's host, and — when nothing host-shaped came out
        — the text exactly as it was, only folded.

        Keeping it matters: this runs over every stored row on every
        load, which is where old rows are repaired, and a row it
        cannot make sense of must come through untouched rather than
        have its Site emptied on his behalf. It fills nothing either
        way; blanking it would throw away the only clue to what it
        was for. Repairing in place like this is idempotent, so a
        vault that has already been through it is left alone."""
        text = (host or "").strip()
        return (cls.parse_site(text, hand_typed=True)[0]
                or text.lower().removeprefix("www."))

    @classmethod
    def unmatchable(cls, item):
        """A login the browser can never fill: its Site is not a host
        and no page will ever be equal to it. The manager says so on
        the row — nothing else in the app would ever mention it."""
        if item.get("type", "login") != "login":
            return False
        host = str(item.get("host", ""))
        return not host or bool(cls.NOT_A_HOST.search(host))

    def _load(self):
        self.data = self.migrate(self.provider.load())
        if not self.provider.eager:
            self.data["never"] = self._load_meta().get("never", [])

    def _load_meta(self):
        try:
            data = json.loads(self.meta_file.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_meta(self):
        try:
            _write_private(self.meta_file,
                           json.dumps({"never": self.data.get("never", [])})
                           .encode())
        except OSError:
            pass

    def rows(self):
        """The live list of saved logins. A sibling branch keeps them
        under another key and reaches them through items(); go through
        that accessor where it exists so a merge cannot quietly leave
        this reading a key nothing writes any more."""
        items = getattr(self, "items", None)
        return items() if callable(items) else self.data["entries"]

    def _absorb_blank(self, host, username, password):
        """A second-step form has no username box, so before this
        branch existed its password was saved with no name at all. The
        same password under a real name is that same login, finally
        named: take the nameless row away rather than leave a blank
        line in the password list for ever. Runs on every named save,
        not just the first — the named row may already exist."""
        rows = self.rows()
        for e in [x for x in rows
                  if x.get("type", "login") == "login"
                  and x.get("host") == host and not x.get("username")
                  and x.get("password") == password]:
            rows.remove(e)
            # a lazy store keeps its own copy: dropping our row is not
            # enough, it would come straight back on the next reload
            if not self.provider.eager and e.get("id"):
                try:
                    self.provider.delete(e["id"])
                except Exception:
                    pass
    def _save(self, item=None, deleted=None):
        """Persist. An eager provider takes the whole snapshot; a lazy
        one is told about the single item that changed, and is never
        handed the rest of the vault to write back.

        A locked vault writes nothing at all. What it holds in memory
        is empty — that is what locked means down at the provider —
        and handing that snapshot to save() would put emptiness over
        every password there is. Nothing is supposed to reach here
        locked; this is the floor under all of it."""
        if self.locked:
            return False
        if self.provider.eager:
            # `entries` is written alongside `items` purely so that a
            # downgrade to an older build still finds its logins;
            # migrate() dedupes by (host, username), so reading it back
            # adds nothing
            self.data["entries"] = [
                {"host": e.get("host", ""), "username": e.get("username", ""),
                 "password": e.get("password", ""),
                 "scheme": e.get("scheme", "https"), "used": e.get("used", 0)}
                for e in self.logins()]
            return self.provider.save(self.data)
        self._save_meta()
        if deleted is not None:
            return self.provider.delete(deleted)
        if item is None:
            return True
        stored = self.provider.put(item)
        if stored is None:
            return False    # the caller's item is untouched: nothing lost
        item.update(stored)
        return True

    # ---- migration ----
    @classmethod
    def migrate(cls, data):
        """Bring any vault this browser has ever written up to the
        current item shape, without losing a thing.

        Idempotent — running it on its own output changes nothing — and
        safe against a file from a *newer* version: unknown top-level
        keys and unknown per-item fields are carried through untouched,
        and a higher version number stays higher so a newer build never
        finds its own file quietly downgraded."""
        if not isinstance(data, dict):
            return cls._empty()
        out = dict(data)
        items = [dict(i) for i in (out.get("items") or [])
                 if isinstance(i, dict)]
        seen = {(i.get("host"), i.get("username")) for i in items
                if i.get("type", "login") == "login"}
        for legacy in (out.pop("entries", None) or []):   # the v1 shape
            if not isinstance(legacy, dict):
                continue
            host = cls.normalize_host(legacy.get("host", ""))
            username = str(legacy.get("username", ""))
            if not host or (host, username) in seen:
                continue
            seen.add((host, username))
            used = int(legacy.get("used", 0) or 0)
            item = dict(legacy)
            item.update({"type": "login", "host": host, "username": username,
                         "created": used, "changed": used, "used": used})
            items.append(item)
        for item in items:
            cls._normalize(item)
        out["items"] = items
        never = []
        for host in (out.get("never") or []):
            host = cls.normalize_host(host)
            if host and host not in never:
                never.append(host)
        out["never"] = never
        out["version"] = max(int(out.get("version") or 0), cls.VERSION)
        return out

    @classmethod
    def _normalize(cls, item):
        """Fill in what this item type needs and leave everything else
        alone, so a field from a newer version survives the round trip.

        A `type` this build has never heard of is one of those: it
        belongs to a newer vault, so it keeps its name and its fields
        and is simply carried through. Turning it into a login and
        handing it login defaults would be the one place migrate is
        unsafe against a newer file, and it would put whatever that
        type calls a secret in front of the page as an ordinary
        field — see redacted_items, which redacts it blind."""
        item.setdefault("id", uuid.uuid4().hex)
        if not isinstance(item.get("type"), str) or not item["type"].strip():
            item["type"] = "login"
        now = int(time.time())
        item["used"] = int(item.get("used") or 0)
        item["created"] = int(item.get("created") or item["used"] or now)
        item["changed"] = int(item.get("changed") or item["created"])
        item.setdefault("title", "")
        item.setdefault("note", "")
        if not isinstance(item.get("tags"), list):
            item["tags"] = []
        item["tags"] = [str(t).strip() for t in item["tags"] if str(t).strip()]
        item["fav"] = bool(item.get("fav"))
        if item["type"] == "login":
            raw = str(item.get("host", ""))
            item["host"] = cls.normalize_host(raw)
            if "://" in raw:
                # a URL pasted into the Site box brings its scheme with
                # it; a Site already stored as a host says nothing about
                # the scheme, so that one is left exactly as it is
                item["scheme"] = cls.parse_site(raw, hand_typed=True)[1]
            for field in ("username", "password", "totp"):
                item.setdefault(field, "")
            if item["totp"] and parse_otpauth(item["totp"]) is None:
                item["totp"] = ""   # not base32: it could never work
            if item.get("scheme") not in ("http", "https"):
                item["scheme"] = "https"
        elif item["type"] == "note":
            item.setdefault("body", "")
        elif item["type"] == "card":
            for field in ("cardholder", "number", "expiry", "cvv", "brand"):
                item.setdefault(field, "")
        elif item["type"] == "identity":
            for field in ("fullname", "email", "phone", "street", "city",
                          "zip", "country"):
                item.setdefault(field, "")
        return item

    # ---- items ----
    def items(self):
        return self.data.setdefault("items", [])

    def logins(self):
        return [i for i in self.items() if i.get("type", "login") == "login"]

    def item(self, item_id):
        for i in self.items():
            if i.get("id") == item_id:
                return i
        return None

    def get(self, host, username):
        host = self.normalize_host(host)
        for e in self.logins():
            if e.get("host") == host and e.get("username") == username:
                return e
        return None

    def entries_for(self, page_host, page_scheme):
        """Every entry that may fill this page, most recently used
        first. Subdomains match their parent's entry (the app's usual
        host semantics); a login saved on http also fills the site's
        https upgrade, never the other way around."""
        page_host = self.normalize_host(page_host)
        out = []
        for e in self.logins():
            if not (page_host == e.get("host")
                    or page_host.endswith("." + e.get("host", "!"))):
                continue
            saved = e.get("scheme", "https")
            if not (page_scheme == saved
                    or (page_scheme == "https" and saved == "http")):
                continue
            out.append(e)
        out.sort(key=lambda e: e.get("used", 0), reverse=True)
        return out

    def best_for(self, page_host, page_scheme):
        """Most recently used entry for this host, or None."""
        entries = self.entries_for(page_host, page_scheme)
        return entries[0] if entries else None

    def for_username(self, page_host, page_scheme, username):
        """The entry for one particular account on this page. Accounts
        are compared case-insensitively: nobody types their e-mail the
        same way twice."""
        want = (username or "").strip().casefold()
        if not want:
            return None
        for e in self.entries_for(page_host, page_scheme):
            if e.get("username", "").strip().casefold() == want:
                return e
        return None

    def set_entry(self, host, scheme, username, password):
        host = self.normalize_host(host)
        if not host or not password:
            return None
        if username:
            self._absorb_blank(host, username, password)
        e = self.get(host, username)
        now = int(time.time())
        fresh = e is None
        if e is None:
            e = self._normalize({"type": "login", "host": host,
                                 "username": username, "created": now})
            self.items().append(e)
        if e.get("password") != password:
            e["changed"] = now
        e["scheme"] = scheme if scheme in ("http", "https") else "https"
        e["password"] = password
        e["used"] = now
        if not self._save(e):
            if fresh:
                self.items().remove(e)   # the store refused it: no ghost row
            return None
        return e

    def add_item(self, fields):
        item = {"created": int(time.time())}
        item.update({k: v for k, v in dict(fields).items() if k != "id"})
        self._normalize(item)
        item["changed"] = int(time.time())
        self.items().append(item)
        if not self._save(item):
            self.items().remove(item)   # the store refused it: no ghost row
            return None
        return item

    def update_item(self, item_id, fields):
        """None when the store would not take it. The row must not say
        "Saved" over a value 1Password still has the old version of, so
        a refused write is rolled back here and reported."""
        item = self.item(item_id)
        if item is None:
            return None
        before = dict(item)
        was = self._secret_of(item)
        item.update({k: v for k, v in dict(fields).items()
                     if k not in ("id", "created")})
        self._normalize(item)
        if self._secret_of(item) != was:
            item["changed"] = int(time.time())
        if not self._save(item):
            item.clear()
            item.update(before)   # what is on screen is what is stored
            return None
        return item

    def delete_item(self, item_id):
        """False when the store still has it. The row is dropped after
        the delete lands, never before — a revoked token used to take
        the row off the page while the item sat in 1Password."""
        item = self.item(item_id)
        if item is None:
            return False
        kept = [i for i in self.items() if i.get("id") != item_id]
        if not self.provider.eager:
            if not self._save(deleted=item_id):
                return False
            self.data["items"] = kept
            return True
        before = self.data["items"]
        self.data["items"] = kept
        if not self._save():
            self.data["items"] = before
            return False
        return True

    def toggle_fav(self, item_id):
        item = self.item(item_id)
        if item is None:
            return False
        item["fav"] = not item.get("fav")
        if not self._save(item):
            item["fav"] = not item["fav"]
        return item["fav"]

    @staticmethod
    def _secret_of(item):
        kind = item.get("type", "login")
        if kind == "login":
            return item.get("password", "")
        if kind == "card":
            return item.get("number", "")
        if kind == "note":
            return item.get("body", "")
        return ""

    def delete(self, host, username):
        host = self.normalize_host(host)
        self.data["items"] = [
            e for e in self.items()
            if not (e.get("type", "login") == "login"
                    and e.get("host") == host
                    and e.get("username") == username)]
        self._save()

    def touch(self, host, username):
        """Freshest login wins autofill. Only recorded for a provider
        that keeps it for us — a remote one would mean a write (and a
        subprocess) on every page load, which is not worth it."""
        e = self.get(host, username)
        if e is not None and self.provider.eager:
            e["used"] = int(time.time())
            self._save(e)

    # ---- what the manager page is allowed to see ----
    #: the fields that are the whole point of the vault. They are kept
    #: out of the listing the page gets and only ever handed over one
    #: at a time, by name, through a keyed slot.
    SECRET_FIELDS = {"login": ("password", "totp"),
                     "card": ("number", "cvv"),
                     "note": ("body",),
                     "identity": ()}
    #: what gets held back from an item type this build does not know.
    #: A newer vault's type has secrets too, and guessing wrong in this
    #: direction only costs a field the page cannot draw yet.
    UNKNOWN_SECRETS = ("password", "passphrase", "secret", "totp", "otp",
                       "number", "ccnum", "cvv", "pin", "body", "key",
                       "privatekey", "token", "credential", "seed")

    def redacted_items(self):
        """Every item with its secrets removed, plus a "has one" flag
        so the page can still draw the right buttons. A card keeps its
        last four digits, because that is how anyone recognises which
        card it is, and those four digits are not the secret."""
        out = []
        for item in self.items():
            kind = item.get("type", "login")
            known = kind in self.SECRET_FIELDS
            secrets_here = (self.SECRET_FIELDS.get(kind, ()) if known
                            else tuple(k for k in item
                                       if k.lower() in self.UNKNOWN_SECRETS))
            shown = {k: v for k, v in item.items() if k not in secrets_here}
            for field in secrets_here:
                flag = "has" + field[:1].upper() + field[1:]
                # a lazy provider has already said whether the secret
                # is there; it just has not handed it over, and that
                # answer must not be overwritten with "no"
                shown[flag] = bool(item.get(field)) or bool(item.get(flag))
            if kind == "card":
                number = re.sub(r"\D", "", item.get("number", ""))
                # a lazy store never sent the number but did send the
                # last four; recomputing them from nothing turns
                # "•••• 1111" into a card with no name on it at all
                shown["last4"] = (number[-4:] if number
                                  else str(item.get("last4", "")))
            if kind == "login" and (self.provider.eager
                                    or not item.get("remote")):
                shown["strength"] = password_strength(item.get("password", ""))
            if self.unmatchable(item):
                shown["dead"] = True
            out.append(shown)
        return out

    def reveal(self, item_id, field):
        """One named field of one item. Only fields this item type
        actually has — a page cannot fish for `_key` or `id`.

        None means the store was asked and would not answer. "" means
        the field is there and empty. The page shows those two very
        differently, so they must not arrive as the same thing."""
        item = self.item(item_id)
        if item is None:
            return ""
        allowed = set(self.SECRET_FIELDS.get(item.get("type", "login"), ()))
        allowed.update(("username", "title", "note", "host", "cardholder",
                        "expiry", "brand", "fullname", "email", "phone",
                        "street", "city", "zip", "country"))
        if field not in allowed:
            return ""
        if not self.provider.eager and item.get("remote"):
            return self.provider.secret(item_id, field)
        value = item.get(field, "")
        return value if isinstance(value, str) else ""

    def totp_view(self, item_id):
        """The code showing right now and how long it has left. The
        seed never leaves this object — and when the provider can
        produce the code itself (1Password can), the seed never even
        reaches us."""
        item = self.item(item_id)
        if item is None:
            return {}
        if self.provider.native_totp and item.get("remote"):
            code = self.provider.totp(item_id)
            if not code:
                return {}
            return {"code": code, "period": 30,
                    "left": round(totp_remaining(30), 1)}
        if not item.get("totp"):
            return {}
        parsed = parse_otpauth(item["totp"])
        if parsed is None:
            return {"error": True}
        try:
            code = totp_code(parsed["secret"], digits=parsed["digits"],
                             period=parsed["period"],
                             algorithm=parsed["algorithm"])
        except Exception:
            return {"error": True}
        return {"code": code, "period": parsed["period"],
                "left": round(totp_remaining(parsed["period"]), 1)}

    # ---- search / organisation ----
    def all_tags(self):
        tags = set()
        for i in self.items():
            tags.update(i.get("tags") or [])
        return sorted(tags, key=str.lower)

    # Searching and filtering happen in the page, over the listing it
    # was already given — which is every field except the secrets. The
    # vault-side search(), matches() and public_entries() that used to
    # be here had no caller left once the manager moved off the
    # settings page, and dead code that touches secrets is worth
    # deleting rather than keeping warm.

    # ---- health ----
    def health(self):
        """Flags per item id plus the totals for the page header. All
        of it worked out here, offline, from the vault's own contents.

        A lazy provider has not handed us the passwords, so there is
        nothing to judge and nothing is claimed: the page is told the
        check could not run rather than being shown a reassuring zero.
        """
        if not self.provider.eager:
            return {"flags": {}, "totals": {}, "unavailable": True}
        counts = {}
        for i in self.items():
            secret = self._secret_of(i)
            if secret and i.get("type", "login") == "login":
                counts[secret] = counts.get(secret, 0) + 1
        now = time.time()
        flags, totals = {}, {"reused": 0, "weak": 0, "old": 0}
        for i in self.items():
            if i.get("type", "login") != "login":
                continue
            secret = self._secret_of(i)
            if not secret:
                continue
            mine = []
            if counts.get(secret, 0) > 1:
                mine.append("reused")
            if len(secret) < 10 or password_strength(secret) < 60:
                mine.append("weak")
            changed = int(i.get("changed") or i.get("created") or 0)
            if changed and (now - changed) > PW_OLD_DAYS * 86400:
                mine.append("old")
            if mine:
                flags[i.get("id")] = mine
                for name in mine:
                    totals[name] += 1
        return {"flags": flags, "totals": totals}

    # ---- import / export ----
    EXPORT_HEADER = ["name", "url", "username", "password", "note", "totp"]
    #: the characters Excel and LibreOffice read as "this cell is a
    #: formula, run it" when a CSV is opened
    FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")

    @classmethod
    def _formula(cls, text):
        return (text[:1] in cls.FORMULA_LEAD
                or (text[:1] == "'" and cls._formula(text[1:])))

    @classmethod
    def _csv_safe(cls, value):
        """A cell no spreadsheet can be talked into running.

        A password of `=cmd|' /C calc'!A0` is a perfectly good password
        and a working attack on whoever opens the export: Excel and
        LibreOffice execute a cell that starts with =, +, - or @. A
        leading apostrophe makes it text again, and _csv_plain takes it
        back off on the way in, so a round trip through this browser
        still returns the password he actually had."""
        text = str(value or "")
        return "'" + text if cls._formula(text) else text

    @classmethod
    def _csv_plain(cls, value):
        """Undo _csv_safe. Only ever strips an apostrophe that is there
        because one was added."""
        text = str(value or "")
        return text[1:] if text[:1] == "'" and cls._formula(text[1:]) else text

    def export_rows(self):
        """The Chrome/Firefox CSV shape, logins only, in the clear —
        the caller has to say that out loud before writing it."""
        rows = [list(self.EXPORT_HEADER)]
        for e in sorted(self.logins(), key=lambda e: e.get("host", "")):
            rows.append([self._csv_safe(x) for x in (
                e.get("title") or e.get("host", ""),
                "%s://%s/" % (e.get("scheme", "https"), e.get("host", "")),
                e.get("username", ""), e.get("password", ""),
                e.get("note", ""), e.get("totp", ""))])
        return rows

    def import_csv(self, text):
        """A Chrome or Firefox password export. Returns (added,
        updated, skipped). An entry that is already here is updated in
        place, so importing the same file twice changes nothing the
        second time.

        A file vault is written ONCE, at the end. Saving per row meant
        re-scrambling and rewriting the whole vault for every line of
        the file: 200 rows took half a second, 2000 took 55, and a
        normal Chrome export is bigger than that. A remote store still
        costs one call per row — there is no batch on the other end —
        which is exactly why the whole import runs off the GUI thread.

        Blocks for as long as the file is long: worker thread only."""
        try:
            rows = list(csv.DictReader(io.StringIO(text)))
        except (csv.Error, ValueError):
            return (0, 0, 0)
        eager = self.provider.eager
        now = int(time.time())
        # what to put back if the one write at the end does not land
        was_items, rollback = list(self.items()), []
        by_login = {}
        if eager:      # get() is a scan; over thousands of rows that is
            for e in self.logins():                    # the whole cost
                by_login.setdefault((e.get("host"), e.get("username")), e)
        added = updated = skipped = 0
        for row in rows:
            low = {(k or "").strip().lower(): (v or "")
                   for k, v in row.items() if k}
            url = self._csv_plain(low.get("url") or low.get("login_uri")
                                  or low.get("web site")
                                  or low.get("hostname") or "")
            username = self._csv_plain(
                low.get("username") or low.get("login_username")
                or low.get("login name") or low.get("user") or "")
            password = self._csv_plain(low.get("password") or "")
            name = self._csv_plain(low.get("name") or low.get("title") or "")
            host, scheme = self.parse_site(url)
            if not host or not password:
                skipped += 1
                continue
            existing = (by_login.get((host, username)) if eager
                        else self.get(host, username))
            if existing is None:
                fresh = self._normalize({
                    "type": "login", "host": host, "username": username,
                    "password": password, "scheme": scheme, "title": name,
                    "created": now})
                self.items().append(fresh)
                if eager:
                    by_login[(host, username)] = fresh
                    added += 1
                elif self._save(fresh):
                    added += 1
                else:
                    self.items().remove(fresh)
                    skipped += 1
            elif existing.get("password") != password:
                was = (existing.get("password", ""), existing.get("changed"))
                existing["password"] = password
                existing["changed"] = now
                if eager:
                    rollback.append((existing, was))
                    updated += 1
                elif self._save(existing):
                    updated += 1
                else:
                    existing["password"], existing["changed"] = was
                    skipped += 1
            else:
                skipped += 1
        if eager and (added or updated) and not self._save():
            # nothing reached the file, so nothing may be left behind in
            # memory pretending it did — the page would show rows that
            # vanish at the next start
            self.data["items"] = was_items
            for item, (password, changed) in rollback:
                item["password"], item["changed"] = password, changed
            return (0, 0, added + updated + skipped)
        return (added, updated, skipped)

    # ---- never-save list ----
    def is_never(self, host):
        return self.normalize_host(host) in self.data.get("never", [])

    def never(self, host):
        host = self.normalize_host(host)
        if host and host not in self.data.setdefault("never", []):
            self.data["never"].append(host)
            self._save()
            self._save_meta()

    def remove_never(self, host):
        host = self.normalize_host(host)
        if host in self.data.get("never", []):
            self.data["never"].remove(host)
            self._save()
            self._save_meta()


class PasswordBridge(QObject):
    """The ONLY object remote pages can reach, over a channel living
    in an isolated script world. One instance per page: the page's
    real URL is authoritative, so a site cannot save credentials
    under someone else's host. No settings or config access here."""

    def __init__(self, browser, page):
        super().__init__(page)
        self.browser = browser
        self.page = page

    @pyqtSlot(str)
    def formSubmitted(self, payload_json):
        try:
            data = json.loads(payload_json)
        except ValueError:
            return
        if isinstance(data, dict):
            self.browser._password_submitted(self.page, data)

    @pyqtSlot(str)
    def loginFormSeen(self, payload_json):
        """The watcher says what the page is asking for right now (an
        identifier, a password, or nothing) and which account it is
        carrying. One-way like formSubmitted: this returns nothing, so
        a caller learns nothing. If the browser decides something
        should be filled it pushes it into the isolated world itself —
        there is deliberately no slot that answers "what would you fill
        here?", because that answer is the credential."""
        try:
            data = json.loads(payload_json)
        except ValueError:
            return
        if isinstance(data, dict):
            self.browser._login_form_seen(self.page, data)


class Bridge(QObject):
    """Exposed to the start/history pages via QWebChannel."""

    updateFinished = pyqtSignal(str)
    #: (ticket, json) — the answer to a secret that had to be fetched
    #: from a remote store, delivered once the worker thread is done
    vaultSecret = pyqtSignal(str, str)
    #: the vault as a whole changed under the page's feet
    vaultChanged = pyqtSignal()
    downloadsChanged = pyqtSignal()
    bookmarksChanged = pyqtSignal()
    #: the buttons in the chrome changed while a page was looking at
    #: them - the right-click menu was used, or the vault was switched
    #: and took the key button with it
    toolbarChanged = pyqtSignal()

    def __init__(self, browser):
        super().__init__()
        self.browser = browser
        self._updating = None
        self._last_generated = ""

    @pyqtSlot()
    def runUpdate(self):
        """Pull the newest version from GitHub (async; result via signal).

        A merge that was interrupted — the machine went to sleep, the
        browser was closed halfway, an update ran while the tree was in
        a state — leaves a conflicted index behind, and from then on
        every single pull dies with "Exiting because of an unresolved
        conflict". The button stays broken forever and the message says
        nothing a person can act on.

        Nobody edits the browser's own folder by hand, so there is
        never anything in that half-finished merge worth keeping: clear
        it first, every time. `git merge --abort` says there is nothing
        to abort when the tree is clean, which is the ordinary case and
        is fine — the pull runs either way.

        A copy that came out of a zip has no .git at all, and git run
        inside one does not fail politely: it walks *up* the directory
        tree hunting for a repository and reports whatever it finds on
        the way out, which is how "Stopping at filesystem boundary"
        ends up in front of somebody who only pressed Update. Worse, if
        an unrelated repository happens to sit above the folder, git
        finds that one and pulls it. So the folder is asked whether it
        is a repository before git is started at all."""
        if self._updating is not None:
            return
        if not (APP_DIR / ".git").exists():
            self._update_without_clone()
            return
        tidy = QProcess(self)
        self._updating = tidy
        tidy.setWorkingDirectory(str(APP_DIR))
        tidy.finished.connect(lambda *_: self._pull_after(tidy))
        tidy.errorOccurred.connect(lambda *_: self._pull_after(tidy))
        tidy.start("git", ["merge", "--abort"])

    def _update_without_clone(self):
        """There is no clone to pull into. Its own method because this is
        the one place the two editions genuinely disagree: the Windows
        one is shipped as a zip and can fetch and unpack a newer one by
        itself, so it replaces this. Kept apart so a change to the
        button above never lands on that difference."""
        self.updateFinished.emit(
            "This copy cannot update itself: it was unpacked from a "
            "zip, so it has no link to GitHub. Download the newest "
            "zip, or replace this folder with a git clone of the "
            "repo and the button will work from then on.")

    def _reset_to_origin(self):
        """Take what GitHub has, wholesale.

        Reached only when a pull cannot fast-forward. The folder holds the
        browser and nothing of the person's own — the config, the history
        and the vault all live elsewhere — so there is nothing here to
        weigh against what is published, and a copy that cannot pull is
        otherwise stuck on its old files for ever.

        `fetch` then `reset --hard FETCH_HEAD`, because after a rewrite
        upstream the local branch's idea of origin/main is itself stale."""
        proc = QProcess(self)
        self._updating = proc
        proc.setWorkingDirectory(str(APP_DIR))
        proc.finished.connect(lambda *_: self._reset_done(proc))
        proc.errorOccurred.connect(lambda *_: self._reset_done(proc))
        proc.start("git", ["fetch", "--prune", "origin"])

    def _reset_done(self, proc):
        if self._updating is not proc:
            return
        ok = (proc.exitStatus() == QProcess.ExitStatus.NormalExit
              and proc.exitCode() == 0)
        proc.deleteLater()
        if not ok:
            self._updating = None
            self.updateFinished.emit(
                "Update failed: could not reach GitHub.")
            return
        hard = QProcess(self)
        self._updating = hard
        hard.setWorkingDirectory(str(APP_DIR))
        hard.finished.connect(lambda *_: self._reset_finished(hard))
        hard.errorOccurred.connect(lambda *_: self._reset_finished(hard))
        hard.start("git", ["reset", "--hard", "origin/HEAD"])

    def _reset_finished(self, proc):
        if self._updating is not proc:
            return
        self._updating = None
        err = bytes(proc.readAllStandardError()).decode(errors="replace")
        ok = (proc.exitStatus() == QProcess.ExitStatus.NormalExit
              and proc.exitCode() == 0)
        proc.deleteLater()
        if ok:
            self.updateFinished.emit(
                "Updated! Restart the browser to finish.")
        else:
            last = (err.strip().splitlines() or ["unknown error"])[-1]
            self.updateFinished.emit("Update failed: " + last)

    def _pull_after(self, tidy):
        """The tidy-up is done, whatever it found. Now the actual pull."""
        if self._updating is not tidy:
            return
        tidy.deleteLater()
        proc = QProcess(self)
        self._updating = proc
        proc.setWorkingDirectory(str(APP_DIR))
        proc.finished.connect(lambda *_: self._update_done(proc))
        proc.errorOccurred.connect(lambda *_: self._update_done(proc))
        proc.start("git", ["pull", "--ff-only"])

    def _update_done(self, proc):
        if self._updating is not proc:
            return
        self._updating = None
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        err = bytes(proc.readAllStandardError()).decode(errors="replace")
        proc.deleteLater()
        if proc.exitStatus() != QProcess.ExitStatus.NormalExit or proc.error() == QProcess.ProcessError.FailedToStart:
            msg = "Update needs git and a cloned copy of the repo."
        elif proc.exitCode() != 0:
            last = (err.strip().splitlines() or ["unknown error"])[-1]
            # git's own wording for these two is true and useless. Both
            # mean the same thing to the person holding the mouse: this
            # copy and GitHub's have gone their separate ways, and no
            # update can arrive until that is settled.
            if "fast-forward" in last or "diverged" in last:
                # The two have gone their separate ways. Nobody edits the
                # browser's own folder by hand, so there is nothing here
                # worth keeping over what GitHub has — and the one thing
                # that genuinely causes this is the history being rewritten
                # upstream, after which a pull can never succeed again and
                # the copy is stranded on old files for good. Take what is
                # published instead of explaining the deadlock.
                self._reset_to_origin()
                return
            elif "unresolved conflict" in last or "MERGE_HEAD" in last:
                msg = ("Update failed: a half-finished merge is in the way. "
                       "Try once more — this clears it first now.")
            elif ("not a git repository" in last
                  or "filesystem boundary" in last):
                # runUpdate checks for .git before starting, so this is
                # the belt to that brace: a .git that exists but is not
                # a repository git will work with lands here rather than
                # showing him git's own sentence about filesystems.
                msg = ("This copy cannot update itself: the folder is not "
                       "a working copy of the repo. Download the newest "
                       "zip, or replace this folder with a git clone.")
            else:
                msg = "Update failed: " + last
        elif "Already up to date" in out:
            msg = "You have the newest version \u2713"
        else:
            msg = "Updated! Restart the browser to finish."
        self.updateFinished.emit(msg)

    @pyqtSlot()
    def openSettings(self):
        """The start page's "All settings" button: opens the pane over
        whatever the tab is showing, instead of navigating to it."""
        self.browser.open_settings()

    @pyqtSlot()
    def closePane(self):
        """Esc (or Done) inside one of our own pages: close the pane it
        lives in. Unkeyed on purpose — closing a pane of ours gives a
        caller nothing, and a website never reaches this object at
        all."""
        self.browser.close_pane()

    @pyqtSlot(result=bool)
    def historyEnabled(self):
        return self.browser.config.get("history", True)

    @pyqtSlot(bool)
    def setHistoryEnabled(self, enabled):
        self.browser.config["history"] = enabled
        self.browser.save_config()

    @pyqtSlot(result=str)
    @_timed
    def uiStrings(self):
        lang = self.browser.config.get("translateLang", "de")
        strings = dict(UI_STRINGS["en"])
        override = UI_STRINGS.get(lang) or UI_STRINGS.get(lang.split("-")[0])
        if override:
            strings.update(override)
        strings["lang"] = lang
        return json.dumps(strings)

    @pyqtSlot(result=str)
    @_timed
    def themes(self):
        """The whole catalogue for the picker: name, shelf, where the
        palette comes from, and the colours its swatch is painted in.
        Its own slot and not part of getSettings: it is a hundred-odd
        entries and it never changes while the browser runs."""
        return json.dumps({"themes": theme_catalogue(),
                           "groups": THEME_GROUPS})

    @pyqtSlot(str)
    def setTheme(self, name):
        """Paint the browser in another theme, now."""
        self.browser.apply_theme(str(name))

    @pyqtSlot()
    def restartBrowser(self):
        """Only offered for the one part of a theme that cannot be
        changed while the engine is running (see _install_theme_flags)."""
        self.browser.restart()

    @pyqtSlot(result=str)
    @_timed
    def getSettings(self):
        c = self.browser.config
        key = c.get("searchEngine", "google")
        if key not in SEARCH_ENGINES:
            key = "google"
        name, template = SEARCH_ENGINES[key]
        action, _, param = template.partition("?")
        tb = self._toolbar_state()
        return json.dumps({
            "searchEngine": key,
            "engines": [[k, v[0]] for k, v in SEARCH_ENGINES.items()],
            "searchName": name,
            "searchAction": action,
            "searchParam": param.split("=")[0] if param else "q",
            "theme": ACTIVE_THEME,
            "themeDark": theme_is_dark(),
            # what the engine was started as. Differs from themeDark
            # only after he switched between a light and a dark theme
            # in this run, which is exactly when websites are still
            # being told the old thing.
            "themeLaunchDark": bool(getattr(self.browser, "_launched_dark",
                                            True)),
            "themeName": theme_def()["name"],
            # Setup's small shelf. Part of getSettings and not a slot
            # of its own like themes(): the wizard runs before anything
            # is configured and must not wait on a second round trip,
            # and twelve palettes cost nothing next to a hundred.
            "themePicks": wizard_themes(),
            "googleLight": c.get("googleLight", True),
            "forceDark": c.get("forceDark", True),
            "restoreTabs": c.get("restoreTabs", True),
            "zoom": c.get("zoom", 1.0),
            "minFont": c.get("minFont", 0),
            "askDownload": bool(c.get("askDownload", False)),
            "downloadDir": str(self.browser.download_dir(create=False)),
            "downloadDirDefault": str(DOWNLOAD_DIR),
            "history": c.get("history", True),
            "savePasswords": c.get("savePasswords", True),
            "vaultPassword": bool(c.get(VAULT_PASSWORD_KEY, True)),
            # whether there is anything to keep, so switching off can
            # say so. A file test, never a read: no secret comes near
            # the settings page to answer this.
            "vaultKept": (CONFIG_FILE.parent / "passwords.json").exists(),
            # the wizard offers to set a master password, and must not
            # offer to set a second one over an install that has one
            "masterOn": self.browser.vault_lock.enabled(),
            "masterMin": MASTER_MIN,
            "searchSuggestions": bool(c.get("searchSuggestions", True)),
            "smoothScroll": bool(c.get("smoothScroll", True)),
            "blockAutoplay": bool(c.get("blockAutoplay", False)),
            "pdfViewer": bool(c.get("pdfViewer", False)),
            "clearHistoryExit": bool(c.get("clearHistoryExit", False)),
            "clearCookiesExit": bool(c.get("clearCookiesExit", False)),
            "spellCheck": bool(c.get("spellCheck", False)),
            "spellCheckLang": self.browser.spell_language(),
            "spellLanguages": [[code, name] for code, name in SPELL_LANGUAGES],
            "newTabPos": c.get("newTabPos", "end"),
            "newTabUrl": c.get("newTabUrl", ""),
            "startUrl": c.get("startUrl", ""),
            "translateLang": c.get("translateLang", "de"),
            "languages": [[code, name, LANGUAGE_ALIASES.get(code, "")]
                          for code, name in LANGUAGES],
            # the buttons in the chrome: what is up there now, and
            # everything the browser could put there. The page reads
            # the names out of window.STR itself, so switching language
            # redraws the list without asking for the settings again.
            "toolbarButtons": tb["shown"],
            "toolbarItems": tb["items"],
            "activeProxy": c.get("activeProxy", "system"),
            "proxyProfiles": c.get("proxyProfiles", []),
            "proxyAuto": c.get("proxyAuto") or {"rules": [], "default": "direct"},
        })

    def _toolbar_state(self):
        """The chrome's buttons, as a page that draws them needs them:
        what is up there now, in order, and every button the browser is
        prepared to put there. Not everything in the registry is on
        offer - _tb_available leaves out the ones with nothing behind
        them - so the two lists have to be read together or a page ends
        up drawing a row for a button that is not on offer, or missing
        one that is."""
        return {
            "shown": self.browser.toolbar_layout(),
            "items": [
                {"name": i["name"], "str": i["str"], "glyph": i["glyph"],
                 "place": i["place"], "fixed": i["fixed"], "key": i["key"]}
                for i in TOOLBAR_ITEMS
                if self.browser._tb_available(i["name"])],
        }

    @pyqtSlot(str, bool)
    def setToolbarButton(self, name, on):
        """One button on or off - what a switch on the settings page
        means.

        The page says which button and which way, and not what the
        whole row ought to look like afterwards. It has a copy of that
        row, but the right-click menu on the bar works while the page
        is up, so the copy can be a change out of date - and posting it
        back would put back whatever the menu had just done. The
        browser has the row that is actually on the screen."""
        self.browser.toggle_toolbar_button(str(name), bool(on))

    @pyqtSlot(result=str)
    def toolbarState(self):
        """The same two lists getSettings() hands out, on their own.

        A settings page that is already open reads them again whenever
        toolbarChanged fires, so what it draws is the toolbar as it is
        now rather than the toolbar as it was when the page loaded -
        and so the whole order it posts back on the next tick is not
        one the right-click menu has moved on from."""
        return json.dumps(self._toolbar_state())

    @pyqtSlot(result=str)
    def resetToolbar(self):
        """Put the buttons at the top back to the set the browser ships
        with, and hand back what that turned out to be so the page can
        redraw from it rather than guess."""
        self.browser.reset_toolbar()
        return json.dumps(self.browser.toolbar_layout())

    @pyqtSlot(str)
    def setProxyAuto(self, auto_json):
        try:
            auto = json.loads(auto_json)
        except ValueError:
            return
        if not isinstance(auto, dict):
            return
        for rule in auto.get("rules", []):
            if isinstance(rule, dict):
                rule["pattern"] = _normalize_rule_pattern(
                    rule.get("pattern", ""))
        self.browser.config["proxyAuto"] = auto
        self.browser.save_config()
        self.browser.apply_proxy()

    @pyqtSlot(str)
    def setActiveProxy(self, name):
        self.browser.set_active_proxy(name)

    @pyqtSlot(str)
    def saveProxyProfile(self, profile_json):
        try:
            prof = json.loads(profile_json)
        except ValueError:
            return
        name = (prof.get("name") or "").strip()
        if not name or name in ("system", "direct"):
            return
        prof["name"] = name
        profs = [p for p in self.browser.config.get("proxyProfiles", [])
                 if p.get("name") != name]
        profs.append(prof)
        self.browser.config["proxyProfiles"] = profs
        self.browser.save_config()
        self.browser.apply_proxy()

    @pyqtSlot(str)
    def deleteProxyProfile(self, name):
        b = self.browser
        b.config["proxyProfiles"] = [
            p for p in b.config.get("proxyProfiles", [])
            if p.get("name") != name]
        if b.config.get("activeProxy") == name:
            b.config["activeProxy"] = "system"
        b.save_config()
        b.apply_proxy()

    @pyqtSlot(str, str)
    def setSetting(self, key, value_json):
        try:
            value = json.loads(value_json)
        except ValueError:
            return
        browser = self.browser
        browser.config[key] = value
        browser.save_config()
        if key == "googleLight":
            browser.refresh_google_scripts()
        elif key == VAULT_PASSWORD_KEY:
            browser.refresh_password_script()
            # _tb_available stops offering the key button the moment
            # there is no vault behind it, and the bar has to hear
            # that now: left up, it is a button that does nothing and
            # has vanished from both places he could take it off from
            browser.rebuild_toolbar()
        elif key == "translateLang":
            browser.apply_language()
        elif key == "proxy":
            browser.apply_proxy()
        elif key == "toolbarButtons":
            # straight back through the same door the right-click menu
            # uses, so an unknown name from a hand-edited config or a
            # newer settings page is dropped rather than drawn
            browser.set_toolbar_buttons(value if isinstance(value, list)
                                        else [])
        elif key == "theme":
            # the settings page writes every setting through one door;
            # a theme also has to be painted, and this is where that
            # happens so the page does not need a second door for it
            browser.apply_theme(str(value))
        elif key in ("forceDark", "smoothScroll", "blockAutoplay",
                     "pdfViewer"):
            browser.apply_web_attributes()
        elif key in ("spellCheck", "spellCheckLang"):
            browser.apply_spellcheck()
        elif key == "zoom":
            # Moving the slider re-bases every tab, one a shortcut had
            # moved included, so the number in Settings and the number a
            # tab sits at can never drift apart.
            for i in range(browser.tabs.count()):
                w = browser.tabs.widget(i)
                if hasattr(w, "setZoomFactor"):
                    w._zoom = None
                    browser._apply_zoom(w)
            # the panes are the browser's own pages and follow the
            # slider like everything else - _apply_zoom is asked
            # rather than the factor set by hand, so there is one
            # place that decides what a page sits at.
            for pane in browser._panes.values():
                browser._apply_zoom(pane.view)
        elif key == "minFont":
            browser.apply_font_size()
            for i in range(browser.tabs.count()):
                w = browser.tabs.widget(i)
                if hasattr(w, "reload") and w.url().scheme() in ("http", "https"):
                    w.reload()

    @pyqtSlot(str, str, result=str)
    def setPageUrl(self, which, text):
        """Save one of the two page addresses - "startUrl" for the tab
        the browser opens on, "newTabUrl" for every new tab - and answer
        with what it actually resolves to. The two are independent:
        writing one never touches the other. An empty answer means the
        browser could make nothing of it, and nothing was saved - the
        settings page says so instead of pretending it took.

        (Named "which", not "key": a first argument called key means
        this run's page key everywhere else in here, and the invariant
        checks say so.)"""
        which = str(which)
        if which not in ("startUrl", "newTabUrl"):
            return ""
        text = str(text or "").strip()
        if not text:
            self.browser.config[which] = ""
            self.browser.save_config()
            return ""
        resolved = self.browser.resolve_page_url(text)
        if not resolved:
            return ""
        self.browser.config[which] = text
        self.browser.save_config()
        return resolved

    @pyqtProperty(bool, constant=True)
    def timing(self):
        """Whether BROWSER_TIMING=1, so the page knows if it is worth
        taking marks of itself. A constant property is on the channel
        from the start - the page reads it without asking."""
        return TIMING

    @pyqtSlot(str, float)
    def pageTiming(self, label, ms):
        """A mark the settings page took of itself, printed in the same
        list as the browser's own phases. Silent unless BROWSER_TIMING=1."""
        if TIMING:
            print("[timing] page.%-15s %7.1f ms" % (str(label)[:15], ms),
                  file=sys.stderr, flush=True)

    @pyqtSlot(result=str)
    def pickDownloadDir(self):
        """Folder picker for downloads; answers with the folder that is
        in force afterwards, so a cancelled dialog changes nothing."""
        browser = self.browser
        chosen = QFileDialog.getExistingDirectory(
            browser, browser._ui_str("downloadFolder"),
            str(browser.download_dir(create=False)))
        if chosen:
            browser.config["downloadDir"] = chosen
            browser.save_config()
        return str(browser.download_dir(create=False))

    @pyqtSlot()
    def clearCookies(self):
        """Wipe cookies + cache of the CURRENT virtual browser only."""
        view = self.browser.current()
        profile = (view.page().profile() if view is not None
                   else self.browser.profile)
        profile.cookieStore().deleteAllCookies()
        profile.clearHttpCache()

    # ---- passwords ----
    # There is exactly one unkeyed password slot left, and it is this
    # one: a count. The old unkeyed pair — revealPassword(host,
    # username) and copyPassword — handed a plaintext password to
    # anything that could reach this bridge, with no key and no
    # confirmation, and were left behind when the manager moved to its
    # own keyed page. Everything below passwordSummary takes the key.
    @pyqtSlot(result=str)
    @_timed
    def passwordSummary(self):
        """The one line the settings page shows now that the real
        manager lives on a page of its own."""
        if not self.browser.vault_password_on():
            return "{}"
        if self.browser.vault_locked():
            return json.dumps({"locked": True, "total": 0, "counts": {},
                               "never": 0, "health": {}, "healthNA": False,
                               "store": "", "storeOk": True, "eager": True,
                               "checking": "", "fellBack": ""})
        v = self.browser.vault
        counts = {}
        for item in v.items():
            kind = item.get("type", "login")
            counts[kind] = counts.get(kind, 0) + 1
        state = v.provider.status()
        health = v.health()
        return json.dumps({"total": len(v.items()), "counts": counts,
                           # why the store is unhappy, so the one line
                           # this page shows can say it rather than
                           # reporting an empty vault that is not empty
                           "reason": state["reason"],
                           "never": len(v.data.get("never", [])),
                           "health": health.get("totals", {}),
                           # no flags because the check could not run is
                           # not the same news as no flags because there
                           # is nothing wrong, and this line is the only
                           # thing about the vault the settings page says
                           "healthNA": bool(health.get("unavailable")),
                           "store": self._provider_label(v.provider),
                           "storeOk": state["ok"],
                           # the settings page has one line about how the
                           # secrets are kept, and it describes the file
                           # vault; it is only true when that is the store
                           "eager": v.provider.eager,
                           "checking": self.browser.vault_checking,
                           "fellBack": self.browser.vault_fell_back})

    # ---- the passwords page ----
    # Same rule as downloads and bookmarks, and it matters more here:
    # every slot below takes this run's key, which only a page the
    # browser opened itself ever carries. A website talking raw
    # QWebChannel — or a passwords.html holding a key from an earlier
    # run — reaches none of them. Note that a website cannot even get
    # this far: remote pages are handed the minimal PasswordBridge in
    # an isolated world and never see `bridge` at all. The key is the
    # second lock, not the first.
    @pyqtSlot()
    def openPasswordsPage(self):
        """Harmless on purpose: it only brings up a page of our own."""
        self.browser.open_passwords()

    @pyqtSlot(str)
    def closePasswords(self, key):
        """Esc inside the passwords page, which now closes the pane it
        lives in. Kept keyed like every other slot here."""
        if self._own_page(key):
            self.browser.close_pane()

    @pyqtSlot(str, result=str)
    def getVault(self, key):
        """The whole vault with every secret stripped out — passwords,
        card numbers, CVVs, TOTP seeds and note bodies stay in the
        browser until something asks for one by name."""
        if not self._own_page(key):
            return "{}"
        if self.browser.vault_locked():
            # Not an empty vault — a shut one. The page draws the lock
            # and the way to open it; drawing "nothing saved yet" over
            # a full vault would be a lie he could act on.
            return json.dumps({"items": [], "never": [], "tags": [],
                               "health": {"flags": {}, "totals": {}},
                               "locked": True,
                               "provider": self.browser.vault.provider.name,
                               "eager": True, "ok": True, "reason": "",
                               "checking": "", "fellBack": ""})
        # Drawing the manager is using the vault, so the auto-lock
        # clock goes back to the start here as well as in _vault_page.
        # It is not in _vault_page itself because this slot has to keep
        # answering while the vault is shut — the page needs to be told
        # that it is shut — and a slot that answers when locked cannot
        # be the one that also asserts it is not.
        self.browser.vault_lock.touch()
        v = self.browser.vault
        state = v.provider.status()
        return json.dumps({"items": v.redacted_items(),
                           "never": sorted(v.data.get("never", [])),
                           "tags": v.all_tags(),
                           "health": v.health(),
                           "provider": v.provider.name,
                           "providerLabel": self._provider_label(v.provider),
                           "eager": v.provider.eager,
                           "ok": state["ok"],
                           "reason": state["reason"],
                           # the store he picked is still being reached
                           # for; the file vault is what he has meanwhile
                           "checking": self.browser.vault_checking,
                           "fellBack": self.browser.vault_fell_back})

    def _ticket(self):
        self._tickets = getattr(self, "_tickets", 0) + 1
        return "t%d" % self._tickets

    def _fetch(self, work, deliver):
        """A secret the provider has to go and get. The slot answers
        straight away with a ticket so the GUI thread is never blocked
        on a subprocess, and the real answer arrives on vaultSecret."""
        ticket = self._ticket()

        def done(result):
            self.vaultSecret.emit(ticket, json.dumps(deliver(result)))
        self.browser.vault_job(work, done)
        return json.dumps({"pending": ticket})

    @staticmethod
    def _revealed(value):
        """None is "the store would not give it to us"; "" is "that
        field is empty". Showing the first as the second puts a dash
        on screen where a password should be and reads as though the
        account has none."""
        return {"ok": value is not None, "value": value or ""}

    @pyqtSlot(str, str, str, result=str)
    def revealField(self, key, item_id, field):
        """One secret, named explicitly, after the page has asked him
        to confirm. Never a whole item at once."""
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault
        if vault.provider.eager:
            return json.dumps(self._revealed(vault.reveal(item_id, field)))
        return self._fetch(lambda: vault.reveal(item_id, field),
                           self._revealed)

    @pyqtSlot(str, str, str, result=str)
    def copyField(self, key, item_id, field):
        """App-side clipboard: web content never gets clipboard
        permission, so the secret is copied here and not in the page."""
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault

        def copy(text):
            if text:
                QGuiApplication.clipboard().setText(text)
            # three outcomes, not two: copied, nothing there to copy,
            # and the store would not answer
            return {"ok": bool(text), "failed": text is None}
        if vault.provider.eager:
            return json.dumps(copy(vault.reveal(item_id, field)))
        return self._fetch(lambda: vault.reveal(item_id, field), copy)

    @pyqtSlot(str, str, result=str)
    def saveItem(self, key, payload):
        """Add (no id) or update (id) one item. Only the fields the
        page actually sends are touched, so a blank password box in the
        edit form leaves the stored password alone.

        A store that has to be written over a subprocess answers with a
        ticket; the page waits for the real answer rather than the
        window waiting for `op`."""
        if not self._vault_page(key):
            return "{}"
        try:
            fields = json.loads(payload)
        except ValueError:
            return "{}"
        if not isinstance(fields, dict):
            return "{}"
        item_id = str(fields.pop("id", "") or "")
        vault = self.browser.vault

        def work():
            return (vault.update_item(item_id, fields) if item_id
                    else vault.add_item(fields))

        def done(item):
            return {"ok": item is not None, "id": (item or {}).get("id", "")}
        if vault.provider.eager:
            return json.dumps(done(work()))
        return self._fetch(work, done)

    @pyqtSlot(str, str, result=str)
    def deleteItem(self, key, item_id):
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault

        def work():
            return vault.delete_item(item_id)

        def done(gone):
            return {"ok": bool(gone)}
        if vault.provider.eager:
            return json.dumps(done(work()))
        return self._fetch(work, done)

    @pyqtSlot(str, str, result=str)
    def toggleFavourite(self, key, item_id):
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault

        def work():
            return vault.toggle_fav(item_id)

        def done(fav):
            return {"ok": True, "fav": bool(fav)}
        if vault.provider.eager:
            return json.dumps(done(work()))
        return self._fetch(work, done)

    @pyqtSlot(str, str, result=str)
    def removeNeverSiteKeyed(self, key, host):
        if not self._vault_page(key):
            return "{}"
        self.browser.vault.remove_never(host)
        return self.getVault(key)

    @pyqtSlot(str, int, bool, bool, bool, bool, result=str)
    def generatePassword(self, key, length, symbols, digits, upper,
                         ambiguous):
        if not self._own_page(key):
            return ""
        try:
            length = int(length)
        except (TypeError, ValueError):
            length = 20     # a slot must not raise on what it was handed
        self.browser.config["pwGen"] = {
            "length": length, "symbols": bool(symbols),
            "digits": bool(digits), "upper": bool(upper),
            "ambiguous": bool(ambiguous)}
        self.browser.save_config()
        password = generate_password(length, symbols, digits, upper, ambiguous)
        self._last_generated = password
        return password

    @pyqtSlot(str, result=str)
    def copyGenerated(self, key):
        """The password the generator last produced, onto the
        clipboard. The page has to ask for this because it cannot do
        it itself: web content gets no clipboard permission here, and
        document.execCommand("copy") simply returns false.

        Only what generatePassword just handed out, never arbitrary
        text a page felt like putting there."""
        if not self._own_page(key):
            return "{}"
        if not self._last_generated:
            return json.dumps({"ok": False})
        QGuiApplication.clipboard().setText(self._last_generated)
        return json.dumps({"ok": True})

    @pyqtSlot(str, str, result=str)
    def totpFor(self, key, item_id):
        """The code showing right now plus how long it has left. The
        seed itself never crosses over."""
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault
        if vault.provider.eager:
            return json.dumps(vault.totp_view(item_id))
        return self._fetch(lambda: vault.totp_view(item_id),
                           lambda view: view or {})

    @pyqtSlot(str, str, result=str)
    def copyTotpCode(self, key, item_id):
        """The code showing right now, onto the clipboard.

        Deliberately NOT copyField(item, "totp"): that field holds the
        seed, which is the long-lived secret the codes are made from.
        Putting it on the clipboard where he asked for a thirty-second
        code is the one mistake this whole feature must not make."""
        if not self._vault_page(key):
            return "{}"
        vault = self.browser.vault

        def copy(view):
            code = str((view or {}).get("code", ""))
            if code:
                QGuiApplication.clipboard().setText(code)
            return {"ok": bool(code), "failed": not view}
        if vault.provider.eager:
            return json.dumps(copy(vault.totp_view(item_id)))
        return self._fetch(lambda: vault.totp_view(item_id), copy)

    @pyqtSlot(str, str, result=str)
    def checkTotpSecret(self, key, text):
        """Does this otpauth:// URI or base32 secret actually work?
        Answered before it is saved, so a bad paste is caught here."""
        if not self._own_page(key):
            return "{}"
        parsed = parse_otpauth(text)
        return json.dumps({"ok": parsed is not None,
                           "issuer": (parsed or {}).get("issuer", ""),
                           "label": (parsed or {}).get("label", "")})

    @pyqtSlot(str, result=str)
    def importPasswords(self, key):
        """Native file picker, then a Chrome/Firefox CSV. The page
        never reads the file itself.

        The picker has to run here — it is a window — but the import
        does not: a two-thousand-row export used to hold the whole
        browser still for the best part of a minute, so the reading
        and the writing happen on a worker thread and the page is
        given a ticket."""
        if not self._vault_page(key):
            return "{}"
        picked = self.browser.pick_import_file()
        if not isinstance(picked, str):
            return json.dumps(picked)      # cancelled, or unreadable
        vault = self.browser.vault

        def done(counts):
            if not counts:
                return {"error": "failed"}
            return {"added": counts[0], "updated": counts[1],
                    "skipped": counts[2]}
        return self._fetch(lambda: vault.import_csv(picked), done)

    @pyqtSlot(str, result=str)
    def exportPasswords(self, key):
        """Plain-text export. The browser puts the warning up itself,
        in a native dialog the page cannot dress up or skip."""
        if not self._vault_page(key):
            return "{}"
        return json.dumps(self.browser.export_passwords())

    def _provider_label(self, provider):
        """The store's name in his language, plus which 1Password vault
        it is pointed at when that is set."""
        if provider.name == "1password":
            name = self.browser._ui_str("pwStore1p")
            return (name + " \u2014 " + provider.vault_name
                    if provider.vault_name else name)
        return self.browser._ui_str("pwStoreFile")

    def _provider_states(self):
        """What he can choose between, and what is wrong with each.
        No token, no token length, nothing derived from one.

        Probes every provider, and probing 1Password is a subprocess
        and a network round trip: worker thread only."""
        out = []
        for name in ("file", "1password"):
            provider = self.browser.build_provider(name)
            state = provider.probe()
            entry = {"name": name, "label": self._provider_label(provider),
                     "ok": state["ok"], "reason": state["reason"],
                     # what he chose, not what is loaded this second —
                     # a remote store is still being reached for a
                     # moment after it is picked
                     "active": name == self.browser.vault_provider_name()}
            if name == "1password":
                entry["hasToken"] = provider.have_token()
                entry["vault"] = provider.vault_name
            out.append(entry)
        return out

    @pyqtSlot(str, result=str)
    def vaultProviders(self, key):
        """Answers with a ticket: see _provider_states for why this
        cannot happen on the GUI thread."""
        if not self._own_page(key):
            return "[]"
        return self._fetch(self._provider_states,
                           lambda out: {"providers": out or []})

    @pyqtSlot(str, str, result=str)
    def setVaultProvider(self, key, name):
        if not self._own_page(key) or name not in ("file", "1password"):
            return "{}"
        return json.dumps(self.browser.set_vault_provider(name))

    @pyqtSlot(str, result=str)
    def setOpToken(self, key):
        """Ask for the service-account token in a native dialog and put
        it in its own 0600 file. It is typed into the app, never into a
        page; it is never echoed back, never returned by any slot, and
        never written to config.json."""
        if not self._own_page(key):
            return "{}"
        return json.dumps(self.browser.ask_op_token())

    @pyqtSlot(str, str, result=str)
    def setOpVault(self, key, name):
        if not self._own_page(key):
            return "{}"
        self.browser.config["opVault"] = str(name or "")
        self.browser.save_config()
        if self.browser.vault.provider.name == "1password":
            self.browser.vault = self.browser.make_vault()
        return json.dumps({"vault": str(name or "")})

    @pyqtSlot(result=str)
    def masterState(self):
        """On, shut, and after how long. Three booleans and a number —
        nothing here is a secret, and the settings page needs all of
        them to draw the section at all."""
        return json.dumps(self.browser.master_state())

    @pyqtSlot(bool, result=str)
    def setMasterPassword(self, on):
        """The switch in Settings. Every path out of here goes through
        a window of the browser's own — the passphrase is typed into
        the application, never into this page, and this page is never
        told it."""
        return json.dumps(self.browser.set_master_password(bool(on)))

    @pyqtSlot(result=str)
    def changeMasterPassword(self):
        return json.dumps(self.browser.change_master_password())

    @pyqtSlot(int, result=str)
    def setMasterMinutes(self, minutes):
        return json.dumps(self.browser.set_master_minutes(minutes))

    @pyqtSlot(result=str)
    def lockVault(self):
        """Shut it now. Unkeyed on purpose: locking is the safe
        direction, and something that can only ever make the browser
        hold fewer secrets does not need guarding."""
        self.browser.lock_vault()
        return json.dumps(self.browser.master_state())

    @pyqtSlot(result=str)
    def unlockVault(self):
        """Ask for the passphrase. It only raises the box — the answer
        goes to the lock, never back through here."""
        self.browser.ask_unlock_vault()
        return json.dumps(self.browser.master_state())

    @pyqtSlot(str, result=str)
    def setupMaster(self, passphrase):
        """The master password, chosen in the setup wizard.

        This is the one place a passphrase is typed into a page rather
        than into a window of the browser's own, and the difference is
        worth being explicit about. The rule everywhere else — never in
        a page — exists because a box asking for the master password is
        a box a website could one day draw a convincing copy of, and
        the person cannot tell them apart. That risk is about
        *unlocking*: a page that wants the passphrase out of him.

        Setting one is the other direction and a different situation.
        The wizard is a page of the browser's own, opened by the
        browser, reachable only over the full bridge no website can
        see, on a first run before any site has been visited. Nothing
        is being asked for that a site could use; a value is being
        handed in. A website cannot reach this slot, and a fake wizard
        would already be a fake browser.

        Unlocking stays in the Qt dialog. See MasterUnlockDialog."""
        return json.dumps(self.browser.setup_master(passphrase))

    @pyqtSlot(result=str)
    def clearSetupMaster(self):
        """He switched it back off before leaving the wizard."""
        return json.dumps(self.browser.clear_setup_master())

    @pyqtSlot()
    def requestSetup(self):
        self.browser._setup_flag = True

    @pyqtSlot(result=bool)
    def popSetupFlag(self):
        flag = getattr(self.browser, "_setup_flag", False)
        self.browser._setup_flag = False
        return flag

    @pyqtSlot(result=bool)
    def googleLight(self):
        return self.browser.config.get("googleLight", True)

    @pyqtSlot(bool)
    def setGoogleLight(self, on):
        self.browser.config["googleLight"] = bool(on)
        self.browser.save_config()
        self.browser.refresh_google_scripts()

    @pyqtSlot(result=str)
    def getStartData(self):
        """Start-page setup shared across all cookie jars."""
        return json.dumps(self.browser.config.get("startPage", {}))

    @pyqtSlot(str)
    def setStartData(self, data):
        try:
            self.browser.config["startPage"] = json.loads(data)
        except ValueError:
            return
        self.browser.save_config()

    @pyqtSlot()
    def openHistoryPage(self):
        """Settings' "View history". Harmless on purpose: it only
        brings up a page of our own."""
        self.browser.open_history()

    @pyqtSlot(result=str)
    def getHistory(self):
        return json.dumps(self.browser.history)

    @pyqtSlot()
    def clearHistory(self):
        self.browser.history = []
        self.browser.save_history()

    # ---- downloads ----
    def _own_page(self, key):
        """The downloads page gets this run's key in its URL; a website
        never sees it, so its raw QWebChannel calls end here."""
        return bool(key) and key == self.browser._page_key

    def _vault_page(self, key):
        """The same, and the vault has to be open as well.

        Every slot that could show, change or write a secret asks this
        instead of _own_page. A locked vault holds nothing anyway —
        that is what locking does — so this is not the only thing
        standing between a locked browser and a password; it is the
        one that makes the answer "no" rather than "here is an empty
        list", which is a different sentence to put on a screen.

        Winding the auto-lock clock here as well is deliberate: this
        is exactly the set of things that count as using the vault, so
        the clock is reset by using it and by nothing else. Reading a
        password keeps it open; leaving the manager sitting there does
        not."""
        if not self._own_page(key):
            return False
        if self.browser.vault_locked():
            return False
        self.browser.vault_lock.touch()
        return True

    def _running(self, key, dl_id):
        if not self._own_page(key):
            return None
        return self.browser.dl_active.get(dl_id)

    @pyqtSlot()
    def openDownloadsPage(self):
        """Harmless on purpose: it only brings up a page of our own."""
        self.browser.open_downloads()

    @pyqtSlot(str)
    def closeDownloads(self, key):
        """Esc inside the downloads page, which now closes the pane it
        lives in. Kept keyed like the rest: the guard is what makes the
        whole set of slots below trustworthy, and one of them quietly
        losing it is exactly the change nobody would notice."""
        if self._own_page(key):
            self.browser.close_pane()

    @pyqtSlot(str, result=str)
    def getDownloads(self, key):
        if not self._own_page(key):
            return "[]"
        return json.dumps(self.browser.downloads_data())

    @pyqtSlot(str, int)
    def cancelDownload(self, key, dl_id):
        request = self._running(key, dl_id)
        if request is not None:
            request.cancel()

    @pyqtSlot(str, int)
    def pauseDownload(self, key, dl_id):
        request = self._running(key, dl_id)
        if request is not None:
            request.pause()

    @pyqtSlot(str, int)
    def resumeDownload(self, key, dl_id):
        request = self._running(key, dl_id)
        if request is not None:
            request.resume()

    @pyqtSlot(str, int)
    def openDownload(self, key, dl_id):
        if self._own_page(key):
            self.browser.open_download(dl_id)

    @pyqtSlot(str, int)
    def openDownloadFolder(self, key, dl_id):
        if self._own_page(key):
            self.browser.open_download(dl_id, folder=True)

    @pyqtSlot(str, int)
    def removeDownload(self, key, dl_id):
        if self._own_page(key):
            self.browser.remove_download(dl_id)

    @pyqtSlot(str)
    def clearDownloads(self, key):
        if self._own_page(key):
            self.browser.clear_downloads()

    # ---- bookmarks ----
    # Same deal as the downloads slots above: everything that reads or
    # changes the list takes this run's key first, so a site talking raw
    # QWebChannel (or a page holding a key from an older run) gets
    # nothing at all.
    #
    # What actually keeps the key safe is that nothing foreign can run
    # inside bookmarks.html — NOT that the channel would be taken away
    # in time. It would not: bookmarks.html replacing itself with
    # about:blank keeps the full channel and a live transport, because
    # the engine resolves about:blank internally and
    # acceptNavigationRequest never sees it. That document is harmless
    # only because the key does not survive into it, so every slot
    # below stays shut for it too.
    @pyqtSlot()
    def openBookmarksPage(self):
        """Harmless on purpose: it only brings up a page of our own."""
        self.browser.open_bookmarks()

    @pyqtSlot(str)
    def closeBookmarks(self, key):
        """Esc inside the bookmarks page, which now closes the pane it
        lives in. Kept keyed like every other slot here."""
        if self._own_page(key):
            self.browser.close_pane()

    @pyqtSlot(str, result=str)
    def getBookmarks(self, key):
        if not self._own_page(key):
            return "[]"
        return json.dumps(self.browser.bookmarks)

    @pyqtSlot(str, int, str, str)
    def updateBookmark(self, key, bid, title, url):
        if self._own_page(key):
            self.browser.update_bookmark(bid, title, url)

    @pyqtSlot(str, int)
    def removeBookmark(self, key, bid):
        if self._own_page(key):
            self.browser.remove_bookmark(bid)

    @pyqtSlot(str, int, int, int)
    def moveBookmark(self, key, bid, parent, index):
        if self._own_page(key):
            self.browser.move_bookmark(bid, parent, index)

    @pyqtSlot(str, str, int, result=int)
    def addBookmarkFolder(self, key, name, parent):
        """A folder, at the root (parent 0) or inside another one.

        One signature and not two: QWebChannel resolves an overloaded
        slot by argument count on the host side, and a page that got it
        wrong would silently get the other one."""
        if not self._own_page(key):
            return 0
        return self.browser.add_bookmark_folder(name, parent)

    @pyqtSlot(str, int, bool)
    def openBookmarkById(self, key, bid, new_tab):
        if self._own_page(key):
            self.browser.open_bookmark_id(bid, new_tab)

    @pyqtSlot(str, result=bool)
    def bookmarksBarVisible(self, key):
        if not self._own_page(key):
            return False
        return self.browser.bookmarks_bar_on()

    @pyqtSlot(str, bool)
    def setBookmarksBarVisible(self, key, on):
        if self._own_page(key):
            self.browser.toggle_bookmarks_bar(on)

    @pyqtSlot(result=str)
    @_timed
    def getPlugins(self):
        b = self.browser
        return json.dumps({
            "plugins": [n[len("plugin-"):] for n in b.plugin_script_names],
            "folder": str(b.plugins_dir),
        })

    @pyqtSlot(result=str)
    def reloadPlugins(self):
        self.browser.reload_plugins()
        return self.getPlugins()

    @pyqtSlot(result=str)
    @_timed
    def starterPlugins(self):
        return json.dumps([{"id": k, "name": v[0], "desc": v[1]}
                           for k, v in STARTER_PLUGINS.items()])

    @pyqtSlot(str, result=bool)
    def installStarter(self, plugin_id):
        return self.browser.install_starter(plugin_id)

    @pyqtSlot()
    def addPluginFromFile(self):
        self.browser.add_plugin_from_file()

    @pyqtSlot(str, str)
    def savePlugin(self, filename, source):
        self.browser.save_plugin(filename, source)


def _same_page(url, page):
    """Same document as one of our own pages, give or take the
    cache-busting ?v= query or an #anchor within it."""
    def bare(text):
        return text.split("#")[0].split("?")[0]
    return bare(url.toString() if isinstance(url, QUrl)
                else str(url)) == bare(page.toString())


def _same_address(url, text):
    """The same address, give or take the trailing slash a bare host
    grows on the way to the network: "https://example.com" is asked for
    and "https://example.com/" is what comes back. Qt's own
    StripTrailingSlash is no help — it leaves the root one alone, which
    is the one that keeps appearing."""
    def bare(u):
        s = (u if isinstance(u, QUrl) else QUrl(u)).toString()
        return s[:-1] if s.endswith("/") else s
    return bare(url) == bare(text)


def _is_pane_url(url):
    """One of the browser's own pages that lives in a pane now. Such a
    page is never saved as a tab and never restored as one: the pane is
    a keystroke away, and a restored tab would be carrying a page key
    from a run that has ended."""
    return any(_same_page(url, page)
               for page in (SETTINGS_PAGE, DOWNLOADS_PAGE, HISTORY_PAGE,
                            BOOKMARKS_PAGE, PASSWORDS_PAGE))


# Everything the browser's own pages read, counted. A pane notes this
# down when its document loads and compares it on the way back up: if
# nothing the page shows has moved, there is nothing to load again.
# Module-level rather than per-window, so a second window saving a
# setting makes the first window's panes stale too.
_page_data_rev = 0


def _page_data_changed(*_ignored):
    """Something one of our own pages reads has changed — the config,
    the history, the downloads, the bookmarks, the vault, the toolbar.
    Deliberately one counter for all of them and not one per page: it
    is compared, never read, and erring towards one load too many is
    the safe direction."""
    global _page_data_rev
    _page_data_rev += 1


def is_internal_page(url):
    """True only for the browser's own start/settings/history/downloads/
    bookmarks/passwords document. Everything else — a site, but also some random
    .html the user opened from disk — counts as untrusted content."""
    if url.scheme() != "file":
        return False
    try:
        path = Path(url.toLocalFile()).resolve()
    except (OSError, ValueError):
        return False
    return path in (APP_DIR / "start.html", APP_DIR / "settings.html",
                    APP_DIR / "history.html", APP_DIR / "downloads.html",
                    APP_DIR / "bookmarks.html", APP_DIR / "passwords.html")


class WebPage(QWebEnginePage):
    """Hands out web channels by trust level: the browser's own pages
    (start/settings/history) get the full settings bridge in the main
    world, like before — but anything from the network only ever sees
    the minimal password channel, and only in an isolated world its
    own JavaScript cannot touch.

    A page can hold exactly one web channel, and Qt only moves it to
    the new world from the *next* document on. So when the trust level
    flips, the navigation is bounced and re-issued a tick later, once
    the transport has landed where it belongs; same page object, so
    back/forward history survives. Bouncing costs a tick only on the
    rare web <-> settings hop, never between two pages of a site."""

    def __init__(self, browser, profile, view):
        super().__init__(profile, view)
        self.browser = browser
        self._full_channel = QWebChannel(self)
        self._full_channel.registerObject("bridge", browser.bridge)
        self._pw_channel = QWebChannel(self)
        self._pw_channel.registerObject("pw", PasswordBridge(browser, self))
        self._view = view        # who the navigation answers are for
        self._channel_kind = None
        self._reissue = None
        self._bounced = None     # the address a bounce will ask for again
        self._healed = False
        self._set_channel("pw")  # untrusted until a URL proves otherwise
        self.loadFinished.connect(self._verify_channel)

    def _set_channel(self, kind):
        self._healed = False   # a fresh trust level gets a fresh retry
        self._install_channel(kind)

    def _install_channel(self, kind):
        # the recorded kind and the installed channel move together —
        # nothing may conclude "already right" while they disagree
        self._channel_kind = kind
        if kind == "full":
            self.setWebChannel(self._full_channel, MAIN_WORLD_ID)
        else:
            self.setWebChannel(self._pw_channel, PW_WORLD_ID)

    def prime_trust(self, url):
        """Settle the trust level for a URL that is about to be asked
        for, before it is asked for.

        The bounce below reaches the same answer, but it pays for it
        with a whole extra navigation — the engine starts a load, the
        load is refused, and only the second one brings a document up.
        A pane knows which of our own pages it is opening before it
        loads anything, so it can simply say so, and the navigation
        that follows sails straight through.

        This grants nothing on its own: `acceptNavigationRequest`
        still re-derives the trust level from every main-frame URL and
        still bounces a mismatch, so a page primed for one of ours
        that is then sent somewhere else lands on the password channel
        before that document exists, exactly as before."""
        kind = "full" if is_internal_page(url) else "pw"
        if kind != self._channel_kind:
            self._set_channel(kind)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # runs before the new document exists, so the channel is always
        # settled before any of that document's scripts can look
        if is_main_frame:
            self._count_navigation(url, nav_type)
            kind = "full" if is_internal_page(url) else "pw"
            if kind != self._channel_kind:
                self._set_channel(kind)
                back_fwd = (nav_type == QWebEnginePage.NavigationType
                            .NavigationTypeBackForward)
                self._reissue = (QUrl(url), back_fwd)
                self._bounced = QUrl(url)
                QTimer.singleShot(0, self._retry_navigation)
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def _count_navigation(self, url, nav_type):
        """Every main-frame navigation the tab starts, counted in order,
        and whether it is still the page the tab was opened on arriving.

        A redirect belongs to whatever sent it — a server hop, a meta
        refresh, a script — so it inherits that answer instead of being
        judged on its own address; anything else is judged on its own.
        Counted before the channel bounce, not after: a bounced
        navigation still moves the tab's address, and if this ran later
        a brand-new tab on one of our own pages would look as though it
        had gone somewhere before it had gone anywhere. The re-issue is
        the same navigation asked for twice, so it is not counted twice.

        This is the only place in the browser that sees a navigation
        before it commits, which is the whole reason the page a tab was
        opened on and the page he went to can be told apart at all."""
        resent, self._bounced = self._bounced == url, None
        view = self._view
        if view is None:
            return
        if not resent:
            view._nav_serial = getattr(view, "_nav_serial", 0) + 1
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeRedirect:
            home = getattr(view, "_blank_home", "")
            view._nav_arrival = bool(home) and _same_address(url, home)

    def restore_trust(self):
        """A navigation that turned out to be a download never brings a
        new document up, so the page still on screen is left holding
        the channel that was meant for the page which never arrived.
        Put the right one back — and since the transport only reaches a
        document while it is being built, one of our own pages has to
        come round again to pick it up."""
        kind = "full" if is_internal_page(self.url()) else "pw"
        if kind == self._channel_kind:
            return
        self._install_channel(kind)
        if kind == "full":
            # a tick later: the download it came with is still being
            # accepted, and reloading out from under it kills it
            QTimer.singleShot(0, lambda: self.triggerAction(
                QWebEnginePage.WebAction.Reload))

    def _verify_channel(self, ok):
        """Did the bridge actually make it into one of our own pages?
        Only asked of trusted pages: a site missing its watcher is not
        worth reloading somebody's page over."""
        if ok and self._channel_kind == "full" and not self._healed:
            self.runJavaScript(
                "typeof qt !== 'undefined' && !!qt.webChannelTransport",
                MAIN_WORLD_ID, self._heal_channel)

    def _heal_channel(self, has_channel):
        """It lost the race: a fresh document picks the transport up.
        Once per trust switch, so this can never loop.

        This is an async reply and it outlives the navigation that was
        in flight when we asked, so the page may be showing a site by
        now. Trust is re-derived from the page as it stands: the kind
        catches a navigation still in flight, the URL catches one that
        has already committed. Never hand the bridge to a document
        that is no longer ours."""
        if has_channel or self._healed:
            return
        if self._channel_kind != "full" or not is_internal_page(self.url()):
            return
        self._healed = True
        self._install_channel("full")
        self.triggerAction(QWebEnginePage.WebAction.Reload)

    def _retry_navigation(self):
        """Latest bounced URL wins; a second bounce finds nothing left.
        Back/forward replays through the history so the other half of
        the stack survives the hop."""
        pending, self._reissue = self._reissue, None
        if pending is None:
            return
        url, back_fwd = pending
        if back_fwd:
            hist = self.history()
            if hist.canGoBack() and hist.backItem().url() == url:
                return hist.back()
            if hist.canGoForward() and hist.forwardItem().url() == url:
                return hist.forward()
            for item in hist.items():
                if item.url() == url:
                    return hist.goToItem(item)
        self.setUrl(url)


class WebView(QWebEngineView):
    page_class = WebPage  # subclasses swap in a page of their own

    def __init__(self, browser, profile):
        super().__init__()
        self.browser = browser
        # what the page below reports about each navigation it starts.
        # Kept here and not on the page: swapping cookie jars builds a
        # new page underneath a tab that goes on being the same tab.
        self._nav_serial = 0
        self._nav_arrival = False
        self.private = False
        self.attach_profile(profile)

    def attach_profile(self, profile):
        self.browser._drop_share(self)  # the page below is about to go
        old = self.page()
        page = self.page_class(self.browser, profile, self)
        page.fullScreenRequested.connect(self._fullscreen)
        page.permissionRequested.connect(self._permission)
        # screen sharing never travels through permissionRequested: Qt
        # raises this instead, and while nothing was connected to it
        # every getDisplayMedia() call died on the spot with AbortError
        page.desktopMediaRequested.connect(self._desktop_media)
        page.proxyAuthenticationRequired.connect(self.browser._proxy_auth)
        self.setPage(page)
        if old is not None and old is not page:
            try:
                old.deleteLater()
            except RuntimeError:
                pass  # Qt already disposed of the replaced page

    def createWindow(self, wtype):
        # tab for a link opened by a page (ctrl+click, middle-click,
        # target=_blank); the engine loads the URL itself, so don't load
        # the start page. Ctrl/middle-click = background tab, like Chrome.
        background = (wtype ==
                      QWebEnginePage.WebWindowType.WebBrowserBackgroundTab)
        # a link followed out of a private tab opens in another private
        # tab: letting it land in the normal jar would hand the site he
        # was reading anonymously his real cookies
        return self.browser.new_tab(switch=not background, blank=True,
                                    private=self.private)

    def _permission(self, permission):
        # the page comes along: a permission's origin is "file:///" for
        # every local page alike, and only the document knows which file
        self.browser._permission_requested(permission, self.page())

    def _desktop_media(self, request):
        # the view and the page both: closing a tab deletes the view,
        # swapping a cookie jar deletes the page, and either one takes
        # the WebContents the engine is still holding a pointer to
        self.browser._desktop_media_requested(request, self.page(), self)

    def _fullscreen(self, request):
        request.accept()
        self.browser.set_fullscreen(request.toggleOn())


class PanePage(WebPage):
    """The page inside a pane. It is one of the browser's own pages, so
    the trust rules hand it the full bridge exactly as before — but a
    pane is not a tab, so a link that leads somewhere else (view
    history, browse Greasy Fork, open a bookmark, run setup again)
    steps out into a real tab instead of stranding the user in a pane
    that is no longer the page it claims to be.

    Which document belongs in here is the pane's business, not the
    page's: the pane sets `pane` on this object right after building
    it, and the answer is asked for again every time rather than
    remembered, because three of these pages carry this run's key in
    their query."""

    pane = None

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # nothing but the pane's own document is ever allowed to become
        # the pane's document — not about:, not data:, not a site. The
        # ones a user could plausibly have meant to visit open as a
        # tab; the rest are simply refused.
        pane = self.pane
        if (is_main_frame and pane is not None
                and not _same_page(url, pane.page_url())):
            if url.scheme() in ("http", "https", "file"):
                self.browser.leave_pane(QUrl(url))
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class PaneView(WebView):
    page_class = PanePage


class MasterDialog(QDialog):
    """The shape the three master-password boxes share.

    A window of the browser's own, and never a page. A page that asked
    for the master password is a page a website could one day draw a
    convincing copy of; this one has the application's title bar, is
    modal, and no document can put one on screen.

    Esc closes this and nothing else. The Esc that takes a pane down
    is a shortcut on the main window (see _pane_escape), and a modal
    dialog is a different active window — so while one of these is up
    the key belongs to it, and dismissing it leaves whatever was
    underneath exactly where it was. test_master.py holds that down.
    """

    def __init__(self, parent, strings, title):
        super().__init__(parent)
        self._str = strings
        self._check = None
        self._ok = None
        self._note = None
        self._fields = {}
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(18, 16, 18, 14)
        self._lay.setSpacing(9)

    # ---- building ----
    def line(self, body, css="color:#8a8a8a;font-size:12px;"):
        label = QLabel(body)
        label.setWordWrap(True)
        label.setStyleSheet(tint(css))
        self._lay.addWidget(label)
        return label

    def field(self, name, placeholder):
        """A box that never shows what is typed into it."""
        box = QLineEdit()
        box.setEchoMode(QLineEdit.EchoMode.Password)
        box.setPlaceholderText(placeholder)
        box.textChanged.connect(self.recheck)
        self._lay.addWidget(box)
        self._fields[name] = box
        return box

    def buttons(self, go_text):
        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(tint("color:#f38ba8;font-size:12px;"))
        self._lay.addWidget(self._note)
        row = QDialogButtonBox(self)
        self._ok = row.addButton(go_text,
                                 QDialogButtonBox.ButtonRole.AcceptRole)
        row.addButton(self._str("pwCancel"),
                      QDialogButtonBox.ButtonRole.RejectRole)
        row.accepted.connect(self._try)
        row.rejected.connect(self.reject)
        self._lay.addWidget(row)
        self.recheck()
        return row

    def set_check(self, check):
        """What has to be true before the box may close. Returns "" to
        let it close, or the sentence to put under the fields."""
        self._check = check

    def showEvent(self, event):
        """Make room for the words before the box is on screen.

        A wrapped QLabel only knows how tall it is once it knows how
        wide it is, and a dialog's sizeHint is worked out before the
        layout has settled on a width — so the box came up the height
        of one unwrapped line and drew the warning over the paragraph
        under it. The warning is the one thing on this dialog that must
        be readable, so the height is asked for at the width the box
        actually has, and the box is never allowed to be shorter."""
        super().showEvent(event)
        width = max(self.minimumWidth(), self.width())
        height = self._lay.heightForWidth(width) if self._lay.hasHeightForWidth() \
            else self._lay.sizeHint().height()
        if height > 0:
            self.setMinimumHeight(height)
            self.resize(width, max(height, self.height()))

    # ---- using ----
    def value(self, name):
        return self._fields[name].text()

    def say(self, message):
        if self._note is not None:
            self._note.setText(message)

    def recheck(self):
        """Whether the go button can be pressed at all. Overridden."""

    def _try(self):
        problem = self._check(self) if self._check is not None else ""
        if problem:
            self.say(problem)
            return
        self.accept()


class MasterUnlockDialog(MasterDialog):
    """Type it, and the vault opens.

    A wrong passphrase is answered here rather than by closing and
    reopening: the box stays, says so, and empties itself. It learns
    nothing from being wrong — no hint, no count, no whether-it-was-
    close — because there is nothing it could say that would help him
    and not help someone else."""

    def __init__(self, parent, strings, lock):
        super().__init__(parent, strings, strings("masterUnlockT"))
        self.line(strings("masterUnlockAsk"), "color:#cdd6f4;font-size:13px;")
        self._box = self.field("pass", strings("masterPassPh"))
        self.buttons(strings("masterUnlockGo"))

        def check(dialog):
            if lock.unlock(dialog.value("pass")):
                return ""
            dialog._box.clear()
            dialog._box.setFocus()
            return strings("masterWrong")
        self.set_check(check)

    def recheck(self):
        if self._ok is not None:
            self._ok.setEnabled(bool(self.value("pass")))


class MasterSetupDialog(MasterDialog):
    """Switching it on, with the consequence that cannot be undone put
    in front of him before he commits to it rather than after.

    Two boxes, because a passphrase typed once and mistyped once locks
    a vault nobody will ever open again. An export button, because the
    only way back from a forgotten passphrase is a copy he chose to
    make while he still knew it — offered here, at the one moment the
    question is actually in front of him."""

    def __init__(self, parent, strings, export):
        super().__init__(parent, strings, strings("masterSetT"))
        self.line(strings("masterWarnT"),
                  "color:#f9e2af;font-size:14px;font-weight:600;")
        self.line(strings("masterWarnB"), "color:#cdd6f4;font-size:12px;")
        self.field("first", strings("masterNewPh"))
        self.field("again", strings("masterAgainPh"))
        self.line(strings("masterMinHint"))
        row = self.buttons(strings("masterSetGo"))
        saveit = row.addButton(strings("masterExportFirst"),
                               QDialogButtonBox.ButtonRole.ActionRole)
        saveit.clicked.connect(export)

    def recheck(self):
        if self._ok is None:
            return
        first, again = self.value("first"), self.value("again")
        self._ok.setEnabled(len(first) >= MASTER_MIN and first == again)
        if first and len(first) < MASTER_MIN:
            self.say(self._str("masterShort"))
        elif first and again and first != again:
            self.say(self._str("masterMismatch"))
        else:
            self.say("")


class MasterChangeDialog(MasterDialog):
    """A different passphrase, without re-entering a single password.

    Only the key changes: see VaultLock.change. The old one is asked
    for because it is the proof, not because anything stored needs
    reading back."""

    def __init__(self, parent, strings, lock):
        super().__init__(parent, strings, strings("masterChangeT"))
        self.line(strings("masterChangeAsk"), "color:#cdd6f4;font-size:13px;")
        self._old = self.field("old", strings("masterCurrentPh"))
        self.field("first", strings("masterNewPh"))
        self.field("again", strings("masterAgainPh"))
        self.line(strings("masterMinHint"))
        self.buttons(strings("masterChangeGo"))

        def check(dialog):
            if lock.change(dialog.value("old"), dialog.value("first")):
                return ""
            dialog._old.clear()
            dialog._old.setFocus()
            return strings("masterWrong")
        self.set_check(check)

    def recheck(self):
        if self._ok is None:
            return
        first, again = self.value("first"), self.value("again")
        self._ok.setEnabled(bool(self.value("old"))
                            and len(first) >= MASTER_MIN and first == again)
        if first and len(first) < MASTER_MIN:
            self.say(self._str("masterShort"))
        elif first and again and first != again:
            self.say(self._str("masterMismatch"))
        else:
            self.say("")


class PagePane(QWidget):
    """One of the browser's own pages shown as a pane over the current
    tab rather than as a page you navigate to: no tab is spent on it,
    no history entry is written, the address bar keeps showing the tab
    underneath, and closing the pane leaves that tab exactly where it
    was. Same HTML and the same bridge as before — only the frame
    around it changed.

    Settings, history, downloads, bookmarks and the password manager
    are all this class: a name and a callable saying which URL to load.
    The callable is asked again on every open, because downloads,
    bookmarks and passwords carry this run's page key in their query
    (see Bridge._own_page) — a pane cannot come back up holding a key
    from an earlier run the way a restored tab could.

    It covers the entire window — address bar, tab strip and download
    bar included — so nothing of the chrome underneath shows through.
    There is no backdrop left to click, so the ways out are the ✕ in
    its header and Esc. Esc belongs to the Browser rather than to each
    pane: one window-wide shortcut, switched on while a pane is up and
    off the moment it goes down (see Browser.open_pane), so exactly one
    thing can ever happen when he presses it.

    Shortcuts that act on tabs (Ctrl+T, Ctrl+W, Ctrl+L, …) close the
    pane first — see Browser.__init__ — so their result is never
    something that happens behind a screen he cannot see past."""

    def __init__(self, browser, name, url_fn):
        super().__init__(browser, objectName="setpane")
        self.browser = browser
        self.name = name
        self._url_fn = url_fn
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        self.panel = QWidget(self, objectName="setpanel")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(1, 1, 1, 1)
        col.setSpacing(0)

        head = QWidget(objectName="sethead")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(head)
        row.setContentsMargins(14, 8, 8, 8)
        row.setSpacing(10)
        # no title up here: the page prints its own, translated
        self.esc_lbl = QLabel(objectName="setescl")
        self.close_btn = QToolButton(text="\u2715", objectName="tabclose")
        self.close_btn.setToolTip(browser._ui_str("close"))
        self.close_btn.clicked.connect(browser.close_pane)
        row.addStretch()
        row.addWidget(self.esc_lbl)
        row.addWidget(self.close_btn)
        col.addWidget(head)

        # Always the main profile, even while a virtual browser is up:
        # all five of these pages show data the whole browser shares and
        # reach it through the bridge, not through the cookie jar, so
        # nothing crosses between sessions. Give a pane per-profile
        # content one day and this is the line that will be wrong.
        self.view = PaneView(browser, browser.profile)
        self.view.page().pane = self
        # A tab gets force-dark switched off for the browser's own
        # pages in _url_changed; the pane is not a tab, so nobody was
        # doing it here and Chromium was re-darkening an already black
        # page — greying the white toggles and the sliders' fill.
        self.view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.ForceDarkMode, False)
        self.view.urlChanged.connect(self._guard_url)
        col.addWidget(self.view, 1)
        browser.installEventFilter(self)

        # what is in there now, and what the browser had recorded
        # when it arrived — see _stale()
        self._loaded = None
        self._loading = None
        self.view.loadFinished.connect(self._load_done)

        self._t0 = 0.0   # when this open began, for BROWSER_TIMING=1
        if TIMING:
            self.view.loadStarted.connect(
                lambda: _timing("page loadStarted", self._t0))
            self.view.loadFinished.connect(
                lambda ok: _timing("page loadFinished", self._t0))

    def page_url(self):
        """Which document belongs in this pane — asked fresh every
        time, so the per-run key in a downloads/bookmarks/passwords URL
        is always the current one."""
        return QUrl(self._url_fn())

    def open(self, started=None):
        # `started` is the stopwatch BROWSER_TIMING=1 runs on opening
        # Settings; every other pane starts its own here, so the
        # load lines above are never measured from zero.
        self._t0 = time.perf_counter() if started is None else started
        self.browser._apply_zoom(self.view)
        self.close_btn.setToolTip(self.browser._ui_str("close"))
        self.esc_lbl.setText(self.browser._ui_str("close") + "  \u00b7  Esc")
        url = self.page_url()
        if self._stale(url):
            self._loading = (url, _page_data_rev)
            self.view.page().prime_trust(QUrl(url))
            self.view.load(QUrl(url))
        else:
            # the open that costs nothing. Said out loud, because
            # "no load lines at all" and "the stopwatch is broken"
            # look the same in the list otherwise
            _timing("page kept", self._t0)
        self.place()
        self.show()
        self.raise_()
        self.view.setFocus()

    def _stale(self, url):
        """Is there anything to load, or is the document already in
        here still true?

        It used to be loaded again on every open, so that a download
        that finished or a bookmark added while the pane sat closed
        would be there when it came back up. But a load throws the old
        document away the moment it starts, and the pane is on screen
        by then: he saw the page he asked for, then his wallpaper
        through the gap where it had been, then the page again. The
        first open of a run was the only clean one, because that one
        had nothing to throw away.

        So the reason for loading again is kept and the loading is
        not: nothing the page reads has changed, nothing to do. When
        something has changed the load happens exactly as before —
        rarely, and never twice in a row.

        The document has to be this pane's own page, arrived in one
        piece (a failed load records nothing), and asked for under the
        same address, key and all."""
        if self._loaded is None:
            return True
        was_url, was_rev = self._loaded
        return (was_rev != _page_data_rev
                or QUrl(was_url) != QUrl(url)
                or not _same_page(self.view.url(), url))

    def _load_done(self, ok):
        """A document that arrived is one this pane can come back to.
        One that did not — a refused navigation, a load that failed —
        leaves the note where it was, so the reload that follows it
        still counts as the load this open asked for."""
        if ok and self._loading is not None:
            self._loaded, self._loading = self._loading, None

    def _guard_url(self, url):
        """The pane refuses every navigation that is not its own page,
        but the engine resolves a couple of them (about:blank) without
        ever asking. So check again where a document actually commits:
        anything else in here would be holding the full bridge, and it
        is not entitled to it. Only the pane's own page can get this
        far, and it gets its own page back."""
        if url.isEmpty() or _same_page(url, self.page_url()):
            return
        QTimer.singleShot(0, lambda: self.view.load(self.page_url()))

    def dismiss(self):
        if not self.isVisible():
            return
        self.hide()
        view = self.browser.current()
        if view is not None and not self.browser._is_header(view):
            view.setFocus()

    def place(self):
        """The whole window, at every window size: the pane is what he
        asked for — settings on the full screen, not a strip below the
        address bar. The window itself never moves or resizes, so the
        Hyprland tile stays exactly as it was."""
        self.setGeometry(self.parentWidget().rect())
        self.panel.setGeometry(self.rect())

    def eventFilter(self, obj, event):
        if (obj is self.browser and self.isVisible()
                and event.type() == QEvent.Type.Resize):
            self.place()
        return super().eventFilter(obj, event)


class SwitchLine(QLineEdit):
    """The switcher's filter box. It keeps the focus while the arrows
    walk the list underneath, so typing never has to stop."""

    def __init__(self, switcher, parent):
        super().__init__(parent, objectName="switchinput")
        self._panel = switcher

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._panel.dismiss()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._panel.move_selection(1 if key == Qt.Key.Key_Down else -1)
            return
        if key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            self._panel.move_selection(6 if key == Qt.Key.Key_PageDown else -6)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._panel.activate()
            return
        super().keyPressEvent(event)


class TabSwitcher(QWidget):
    """Ctrl+Shift+A: every open tab of every virtual browser in one
    list, filtered as you type. Each row says which virtual browser (and
    which group) the tab lives in, and Enter jumps to it — switching
    virtual browser and unfolding a collapsed group on the way."""

    ROWS = 300  # a filter that matches everything stays cheap to draw

    def __init__(self, browser):
        super().__init__(browser.tabs, objectName="switchpane")
        self.browser = browser
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._rows = []

        self.panel = QWidget(self, objectName="switchpanel")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(1, 1, 1, 1)
        col.setSpacing(0)

        self.input = SwitchLine(self, self.panel)
        self.input.textEdited.connect(lambda _t: self.refresh())
        col.addWidget(self.input)

        self.list = QListWidget(self.panel, objectName="switchlist")
        self.list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda _i: self.activate())
        col.addWidget(self.list, 1)

        self.empty = QLabel("", self.panel, objectName="switchempty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setContentsMargins(0, 24, 0, 24)
        self.empty.hide()
        col.addWidget(self.empty)

        browser.tabs.installEventFilter(self)

    # ---- what there is to switch to ----
    def _open_tabs(self):
        b = self.browser
        names = {e["sid"]: e["name"] for e in b.sessions}
        here = b.current()
        out = []
        for i in range(b.tabs.count()):
            w = b.tabs.widget(i)
            if b._is_header(w) or not hasattr(w, "url"):
                continue
            url = (w.url().toString() or getattr(w, "_pending", "")
                   or getattr(w, "_requested", ""))
            sid = getattr(w, "session", "main")
            group = b._group_of(w)
            place = names.get(sid, sid)
            if group:
                place += " \u00b7 " + group
            out.append({
                "view": w,
                "title": b.tabs.tabText(i) or QUrl(url).host() or "Tab",
                "url": "" if _same_page(QUrl(url), START_PAGE)
                       else url,
                "place": place,
                "here": w is here,
            })
        return out

    def _row_widget(self, info, width):
        row = QWidget(objectName="switchrow")
        grid = QGridLayout(row)
        grid.setContentsMargins(12, 7, 12, 7)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(1)
        metrics = row.fontMetrics()
        # every string in a row is a page title or a page URL: the site
        # wrote it, so none of it may reach Qt as markup
        badge = QLabel(objectName="switchbadge")
        set_plain(badge, info["place"])
        badge.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        room = max(120, width - 210)
        title = QLabel(objectName="switchtitle")
        title.setProperty("here", "1" if info["here"] else "0")
        set_plain(title, metrics.elidedText(
            info["title"], Qt.TextElideMode.ElideRight, room), info["title"])
        sub = QLabel(objectName="switchurl")
        set_plain(sub, metrics.elidedText(
            info["url"] or self.browser._ui_str("startPageName"),
            Qt.TextElideMode.ElideMiddle, max(160, width - 60)))
        grid.addWidget(title, 0, 0)
        grid.addWidget(badge, 0, 1)
        grid.addWidget(sub, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        return row

    def refresh(self):
        words = self.input.text().lower().split()
        width = max(320, self.panel.width())
        self.list.clear()
        self._rows = []
        for info in self._open_tabs():
            hay = " ".join((info["title"], info["url"],
                            info["place"])).lower()
            if any(word not in hay for word in words):
                continue
            item = QListWidgetItem()
            widget = self._row_widget(info, width)
            item.setSizeHint(widget.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, widget)
            self._rows.append(info)
            if len(self._rows) >= self.ROWS:
                break
        if self._rows:
            self.list.setCurrentRow(0)
        self.empty.setText(self.browser._ui_str("noTabs"))
        self.empty.setVisible(not self._rows)
        self.list.setVisible(bool(self._rows))
        self.place()

    # ---- keyboard ----
    def move_selection(self, step):
        n = self.list.count()
        if not n:
            return
        self.list.setCurrentRow((self.list.currentRow() + step) % n)

    def activate(self):
        row = self.list.currentRow()
        if not (0 <= row < len(self._rows)):
            return
        view = self._rows[row]["view"]
        self.dismiss()
        self.browser.focus_tab(view)

    # ---- opening and closing ----
    def open(self):
        self.input.setPlaceholderText(self.browser._ui_str("tabSearchPh"))
        self.input.clear()
        self.place()
        self.refresh()
        self.show()
        self.raise_()
        self.input.setFocus()

    def dismiss(self):
        if not self.isVisible():
            return
        self.hide()
        self.list.clear()
        self._rows = []
        view = self.browser.current()
        if view is not None and not self.browser._is_header(view):
            view.setFocus()

    def place(self):
        """Centred, and only as tall as the rows it has to show — up to
        the room the window leaves it."""
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        margin = 24 if min(self.width(), self.height()) > 420 else 4
        width = max(0, min(660, self.width() - 2 * margin))
        wanted = self.input.sizeHint().height() + 6
        if self._rows:
            wanted += sum(self.list.sizeHintForRow(i)
                          for i in range(self.list.count()))
        else:
            wanted += self.empty.sizeHint().height() + 48
        height = max(0, min(480, self.height() - 2 * margin, wanted))
        self.panel.setGeometry((self.width() - width) // 2,
                               max(margin, (self.height() - height) // 3),
                               width, height)

    def eventFilter(self, obj, event):
        if (obj is self.browser.tabs and self.isVisible()
                and event.type() == QEvent.Type.Resize):
            self.place()   # first for the width the rows have to fit
            self.refresh()  # ends by placing again, now knowing its height
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.dismiss()
        else:
            super().mousePressEvent(event)


class FindLine(QLineEdit):
    """The find bar's input. Enter/Shift+Enter step through the matches
    and Esc closes the bar — handled here rather than with a window-wide
    Esc shortcut, which would steal the key from whatever page is in the
    tab. (The one window-wide Esc there is belongs to the panes, and it
    is only switched on while a pane is up — and a pane refuses to open
    the find bar at all, so the two never both want the key.)"""

    def __init__(self, bar):
        super().__init__(bar, objectName="findinput")
        self._bar = bar

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._bar.dismiss()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            back = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._bar.step(-1 if back else 1)
            return
        super().keyPressEvent(event)


class FindBar(QWidget):
    """Ctrl+F. Counts the matches on the page in front of him and steps
    through them, showing "3/17" (greyed out when nothing matches).

    It follows the current tab: switching tabs clears the highlights in
    the tab being left and re-runs the search in the new one, so no tab
    is ever left lit up behind his back. A tab closed while the bar is
    open is dropped without touching its page — the C++ object is on its
    way out and asking it anything would crash."""

    def __init__(self, browser):
        super().__init__(browser.tabs, objectName="findbar")
        self.browser = browser
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._view = None   # the tab currently being searched
        self._seq = 0       # answers to older searches are ignored

        row = QHBoxLayout(self)
        row.setContentsMargins(9, 6, 6, 6)
        row.setSpacing(4)

        self.input = FindLine(self)
        self.input.setFixedWidth(230)
        self.input.textEdited.connect(lambda _t: self.search(0, restart=True))
        row.addWidget(self.input)

        self.count = QLabel("", objectName="findcount")
        self.count.setMinimumWidth(54)
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setProperty("dim", "1")
        row.addWidget(self.count)

        self.case = QToolButton(text="Aa")
        self.case.setCheckable(True)
        self.case.clicked.connect(lambda: self.search(0, restart=True))
        row.addWidget(self.case)

        self.prev = QToolButton(text="\u2039")
        self.prev.clicked.connect(lambda: self.step(-1))
        row.addWidget(self.prev)

        self.next = QToolButton(text="\u203a")
        self.next.clicked.connect(lambda: self.step(1))
        row.addWidget(self.next)

        self.close_btn = QToolButton(text="\u2715")
        self.close_btn.clicked.connect(self.dismiss)
        row.addWidget(self.close_btn)

        browser.tabs.installEventFilter(self)
        self.retranslate()

    def retranslate(self):
        s = self.browser._ui_str
        self.input.setPlaceholderText(s("findPh"))
        self.case.setToolTip(s("findCase"))
        self.prev.setToolTip(s("findPrev"))
        self.next.setToolTip(s("findNext"))
        self.close_btn.setToolTip(s("findClose"))

    # ---- the tab being searched ----
    def _live(self):
        """The view we are searching, or None once it has gone away."""
        view = self._view
        if view is None:
            return None
        try:
            view.page()
        except RuntimeError:
            self._view = None
            return None
        return view

    def _clear(self, view):
        """Drop the highlights in a page without disturbing anything else."""
        if view is None:
            return
        try:
            view.page().findText("")
        except RuntimeError:
            pass

    def forget(self, view):
        """The tab we were searching is being closed: let go of it
        without touching its page, which is on its way out."""
        if view is self._view:
            self._view = None

    def _watch(self, view, on):
        """Follow the tracked tab's loads: a page that was still coming
        in when the bar opened, or one he navigated to with the bar
        still up, gets counted once it is actually there."""
        if view is None:
            return
        try:
            if on:
                view.loadFinished.connect(self._page_loaded)
            else:
                view.loadFinished.disconnect(self._page_loaded)
        except (RuntimeError, TypeError):
            pass

    def _page_loaded(self, _ok):
        if self.isVisible():
            self.search(0, restart=True)

    def retarget(self):
        """Point the bar at the tab in front of him now."""
        view = self.browser.current()
        if view is not None and self.browser._is_header(view):
            view = None
        current = self._live()
        if view is current:
            return
        self._clear(current)
        self._watch(current, False)
        self._view = view
        self._watch(view, True)
        self._seq += 1
        if self.isVisible():
            self.search(0, restart=True)
        else:
            self._report(0, 0)

    # ---- searching ----
    def step(self, direction):
        if not self.input.text():
            return
        self.search(direction)

    def search(self, direction=0, restart=False):
        view = self._live()
        text = self.input.text()
        self._seq += 1
        token = self._seq
        if view is None:
            self._report(0, 0)
            return
        if not text:
            self._clear(view)
            self._report(0, 0)
            return
        flags = QWebEnginePage.FindFlag(0)
        if self.case.isChecked():
            flags |= QWebEnginePage.FindFlag.FindCaseSensitively
        if direction < 0:
            flags |= QWebEnginePage.FindFlag.FindBackward
        try:
            if restart:
                # a changed term or a flipped Aa must count from the top
                view.page().findText("")
            view.page().findText(
                text, flags, lambda res, t=token: self._result(t, res))
        except RuntimeError:
            self._view = None
            self._report(0, 0)

    def _result(self, token, result):
        if token != self._seq:
            return  # an answer to a search that has already been replaced
        try:
            self._report(result.numberOfMatches(), result.activeMatch())
        except (RuntimeError, AttributeError):
            self._report(0, 0)

    def _report(self, matches, active):
        if not self.input.text():
            self.count.setText("")
        else:
            self.count.setText("%d/%d" % (active, matches))
        dim = "1" if not matches else "0"
        if self.count.property("dim") != dim:
            self.count.setProperty("dim", dim)
            self.count.style().unpolish(self.count)
            self.count.style().polish(self.count)
        self.prev.setEnabled(bool(matches))
        self.next.setEnabled(bool(matches))

    # ---- opening and closing ----
    def open(self):
        self.retranslate()
        self._watch(self._live(), False)
        self._view = None
        self.retarget()
        self.place()
        self.show()
        self.raise_()
        self.input.setFocus()
        self.input.selectAll()
        self.search(0, restart=True)

    def dismiss(self):
        if not self.isVisible():
            return
        self._clear(self._live())
        self._seq += 1
        self.hide()
        view = self.browser.current()
        if view is not None and not self.browser._is_header(view):
            view.setFocus()

    def place(self):
        """Top right of the page, clear of the tab strip above it."""
        parent = self.parentWidget()
        size = self.sizeHint()
        width = min(size.width(), max(0, parent.width() - 16))
        bar = self.browser.tabs.tabBar()
        top = (bar.height() if bar.isVisible() else 0) + 6
        self.setGeometry(max(0, parent.width() - width - 14), top,
                         width, size.height())

    def eventFilter(self, obj, event):
        if (obj is self.browser.tabs and self.isVisible()
                and event.type() == QEvent.Type.Resize):
            self.place()
        return super().eventFilter(obj, event)


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


class DownloadWidget(QWidget):
    """One entry in the download bar: name, progress, speed, time left."""

    def __init__(self, request, on_dismiss):
        super().__init__(objectName="dlitem")
        self.req = request
        self.on_dismiss = on_dismiss
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_bytes = 0
        self.last_ms = 0
        self.speed = 0.0

        self.setFixedWidth(360)
        name = request.downloadFileName()
        self.name = QLabel(objectName="dlname")
        self.name.setText(self.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, 230))
        self.name.setToolTip(name)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.info = QLabel("Starting…", objectName="dlinfo")

        self.open_btn = QToolButton(text="Open")
        self.open_btn.hide()
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.req.downloadDirectory())))
        self.close_btn = QToolButton(text="✕")
        self.close_btn.clicked.connect(self._cancel_or_dismiss)

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 8, 8)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.name, 0, 0)
        grid.addWidget(self.open_btn, 0, 1)
        grid.addWidget(self.close_btn, 0, 2)
        grid.addWidget(self.bar, 1, 0, 1, 3)
        grid.addWidget(self.info, 2, 0, 1, 3)

        request.receivedBytesChanged.connect(self._progress)
        request.totalBytesChanged.connect(self._progress)
        request.stateChanged.connect(self._state_changed)

    def _progress(self):
        if self.req.state() != self.req.DownloadState.DownloadInProgress:
            return
        received, total = self.req.receivedBytes(), self.req.totalBytes()
        ms = self.clock.elapsed()
        if ms - self.last_ms >= 300:
            instant = (received - self.last_bytes) / ((ms - self.last_ms) / 1000)
            self.speed = instant if not self.speed else 0.7 * self.speed + 0.3 * instant
            self.last_bytes, self.last_ms = received, ms
        parts = []
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(round(received / total * 1000))
            parts.append(f"{fmt_size(received)} / {fmt_size(total)}")
        else:
            self.bar.setRange(0, 0)  # size unknown: busy animation
            parts.append(fmt_size(received))
        if self.speed > 0:
            parts.append(f"{fmt_size(self.speed)}/s")
            if total > 0:
                parts.append(f"{fmt_time((total - received) / self.speed)} left")
        self.info.setText(" · ".join(parts))

    def _state_changed(self, state):
        St = self.req.DownloadState
        if state == St.DownloadCompleted:
            self.bar.setRange(0, 1000)
            self.bar.setValue(1000)
            self.info.setText(f"Done · {fmt_size(self.req.receivedBytes())}")
            self.open_btn.show()
        elif state == St.DownloadCancelled:
            self.bar.setRange(0, 1000)
            self.info.setText("Cancelled")
        elif state == St.DownloadInterrupted:
            self.bar.setRange(0, 1000)
            self.info.setText("Failed: " + self.req.interruptReasonString())

    def _cancel_or_dismiss(self):
        if self.req.state() == self.req.DownloadState.DownloadInProgress:
            self.req.cancel()
        else:
            self.on_dismiss(self)


class LocalFileWidget(QWidget):
    """A file the browser produced itself (a printed PDF) in the download
    bar. The same island as a real download, minus everything only a
    network transfer has: there is nothing here to pause or resume."""

    def __init__(self, name, on_dismiss):
        super().__init__(objectName="dlitem")
        self.on_dismiss = on_dismiss
        self.path = None

        self.setFixedWidth(360)
        self.name = QLabel(objectName="dlname")
        # the file name came out of the page title: page-controlled
        set_plain(self.name, self.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, 230), name)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 0)  # busy: rendering reports no progress
        self.info = QLabel(objectName="dlinfo")

        self.open_btn = QToolButton(text="Open")
        self.open_btn.hide()
        self.open_btn.clicked.connect(self._open)
        self.close_btn = QToolButton(text="\u2715")
        self.close_btn.clicked.connect(lambda: self.on_dismiss(self))

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 8, 8)
        grid.setVerticalSpacing(4)
        grid.addWidget(self.name, 0, 0)
        grid.addWidget(self.open_btn, 0, 1)
        grid.addWidget(self.close_btn, 0, 2)
        grid.addWidget(self.bar, 1, 0, 1, 3)
        grid.addWidget(self.info, 2, 0, 1, 3)

    def _open(self):
        if self.path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def finished(self, path, size, ok, done_text, fail_text):
        self.bar.setRange(0, 1000)
        self.bar.setValue(1000 if ok else 0)
        if ok:
            self.path = path
            self.info.setText("%s \u00b7 %s" % (done_text, fmt_size(size)))
            self.open_btn.show()
        else:
            self.info.setText(fail_text)


def set_plain(label, text, tooltip=None):
    """Put a string a website controls into a label as text and nothing
    else. Qt guesses rich text from the content, so a page titled
    "<b>Your Bank</b>" would otherwise render bold — and the elision
    would land in the wrong place, having counted the tags. Tooltips
    guess the same way and have no plain-text mode, so the tooltip is
    escaped into markup that renders back as the original characters."""
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(text)
    if tooltip is not None:
        label.setToolTip(html.escape(tooltip))


def _sane_number(value, limit=1 << 53):
    """A count or timestamp read back from disk, or 0 if it is nonsense
    (a string, a dict, 1e400 — all of it ends up in downloads.json)."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if 0 <= number <= limit else 0


def load_downloads():
    """The saved download list with every field pulled back into shape:
    a hand-edited or half-written file must never keep the browser from
    starting, and a "still running" entry can only be a leftover."""
    try:
        raw = json.loads(DOWNLOADS_FILE.read_text())
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    entries, used = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        dl_id = _sane_number(entry.get("id"))
        if dl_id <= 0 or dl_id in used:
            dl_id = max(used, default=0) + 1
        used.add(dl_id)
        entry["id"] = dl_id
        entry["name"] = str(entry.get("name") or "")
        entry["dir"] = str(entry.get("dir") or "")
        entry["url"] = str(entry.get("url") or "")
        for key in ("t", "received", "size"):
            entry[key] = _sane_number(entry.get(key))
        entry["paused"] = False
        entry["local"] = bool(entry.get("local"))
        if entry.get("state") not in ("done", "cancelled", "failed"):
            entry["state"] = "failed"  # nothing keeps running across a start
        entries.append(entry)
    return entries[-DOWNLOADS_MAX:]


def _clean_bookmark_url(text):
    """What the manager's address field is allowed to become: an http(s)
    URL, or nothing at all.

    A bare "example.com" gets https:// put in front of it. Anything
    already naming a scheme has to name one we would really load —
    gluing https:// onto "javascript:alert(1)" used to make an https
    URL that passed the scheme check and was stored for good. A colon
    followed by digits is a port, not a scheme, so "localhost:8080"
    still means what he meant."""
    text = str(text or "").strip()
    if not text:
        return ""
    if "://" in text:
        url = QUrl(text)
    elif re.match(r"[a-z][a-z0-9+.\-]*:(?!\d)", text, re.I):
        return ""  # javascript:, mailto:, data:, about: … none of ours
    else:
        url = QUrl("https://" + text)
    if url.scheme() not in ("http", "https") or not url.host():
        return ""
    return url.toString()


def _bookmark_key(url):
    """What makes two addresses the same bookmark: everything, give or
    take a trailing slash on a bare host (https://x.com/ == https://x.com)."""
    text = url.toString() if isinstance(url, QUrl) else str(url or "")
    return text[:-1] if text.endswith("/") and text.count("/") == 3 else text


# the only favicon encoding this browser writes, and the only one it
# reads back: the manager page puts it straight into an <img src>
ICON_PREFIX = "data:image/png;base64,"


def _icon_data(icon):
    """A favicon as a small data: URL — that is what bookmarks.json
    keeps, so a bookmark shows its icon before the site is visited."""
    if icon is None or icon.isNull():
        return ""
    pix = icon.pixmap(16, 16)
    if pix.isNull():
        return ""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pix.save(buf, "PNG"):
        return ""
    return ICON_PREFIX + base64.b64encode(bytes(buf.data())).decode()


def _blank_favicon():
    """A quiet ring standing in for a site that has no favicon, so the
    bar's text columns line up whether an icon arrived or not."""
    pix = QPixmap(16, 16)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(theme_color("overlay")))
    painter.drawEllipse(3, 3, 9, 9)
    painter.end()
    return QIcon(pix)


def _folder_icon():
    """A folder, drawn rather than borrowed. The desktop's own folder
    icon is a colour picture from somebody else's theme, and this
    chrome is black with no blue in it."""
    pix = QPixmap(16, 16)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QColor(theme_color("subtext"))
    painter.setPen(pen)
    painter.setBrush(QColor(0, 0, 0, 0))
    # the tab along the top, then the body
    painter.drawLine(2, 4, 6, 4)
    painter.drawLine(6, 4, 7, 6)
    painter.drawRect(2, 5, 11, 8)
    painter.end()
    return QIcon(pix)


def _icon_from_data(text):
    """The stored data: URL back as a QIcon; anything odd gives a null
    icon rather than raising — bookmarks.json is a file on disk."""
    prefix = ICON_PREFIX
    if not isinstance(text, str) or not text.startswith(prefix):
        return QIcon()
    try:
        raw = base64.b64decode(text[len(prefix):], validate=True)
    except Exception:
        return QIcon()
    pix = QPixmap()
    if not pix.loadFromData(raw, "PNG"):
        return QIcon()
    return QIcon(pix)


def _reparent_bookmarks(entries):
    """Every entry hung off something that is really there, and the
    whole lot guaranteed to be a tree.

    Two things can be wrong with a parent. It can point at nothing —
    a folder deleted, or cut off by the cap — and then the entry goes
    back to the root, which is where it can be seen. Or a run of
    folders can point round in a circle: A inside B inside A, which no
    click in this browser can produce but a text editor can. Every
    folder that cannot reach the root by walking up its parents is put
    at the root, circle and contents alike. That flattens a corrupt
    corner rather than repairing it, and it loses nothing: every
    bookmark is still in the list, still visible, just a level up.

    The point is the guarantee. After this, walking parents terminates
    and so does walking children — the menu builder, the delete, the
    manager's sections all lean on it."""
    folders = {e["id"] for e in entries if e["type"] == "folder"}
    for entry in entries:
        if entry["parent"] not in folders:
            entry["parent"] = 0
    up = {e["id"]: e["parent"] for e in entries if e["type"] == "folder"}
    rooted = set()
    for fid in up:
        chain, node = [], fid
        while node and node not in rooted:
            if node in chain:
                chain = []   # a circle: nothing walked on this trip is rooted
                break
            chain.append(node)
            node = up[node]
        rooted.update(chain)
    if len(rooted) != len(up):
        for entry in entries:
            if entry["type"] == "folder" and entry["id"] not in rooted:
                entry["parent"] = 0
    return entries


def load_bookmarks():
    """The saved bookmarks with every field pulled back into shape, in
    the spirit of load_downloads(): a hand-edited or half-written file
    must never keep the browser from starting.

    Folders nest: a folder's parent is 0 (the bar itself) or another
    folder that really exists, as deep as he likes. What comes out of
    here is always a tree — see _reparent_bookmarks, which is what
    stands between a hand-edited file and a menu that recurses for
    ever. Only http(s) links survive — a bookmarks.json carrying a
    javascript: or file: URL would otherwise be a way to aim the
    browser at something it should never load from a click."""
    try:
        raw = json.loads(BOOKMARKS_FILE.read_text())
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    entries, used = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        bid = _sane_number(item.get("id"))
        if bid <= 0 or bid in used:
            bid = max(used, default=0) + 1
        used.add(bid)
        kind = "folder" if item.get("type") == "folder" else "link"
        url = "" if kind == "folder" else str(item.get("url") or "")
        if kind == "link" and QUrl(url).scheme() not in ("http", "https"):
            continue
        # the manager puts this straight into an <img src>, so only a
        # PNG data: URL of our own making is allowed through
        icon = item.get("icon")
        if not (isinstance(icon, str) and icon.startswith(ICON_PREFIX)):
            icon = ""
        entries.append({
            "id": bid,
            "type": kind,
            "title": str(item.get("title") or "")[:300],
            "url": url,
            "icon": icon[:20000],
            "parent": _sane_number(item.get("parent")),
            "t": _sane_number(item.get("t")),
        })
    # the cap first, then the parenting: a folder cut off by the cap
    # must not leave its children pointing at an id that is not in the
    # list any more (invisible on the bar, unreachable in the manager)
    entries = entries[:BOOKMARKS_MAX]
    return _reparent_bookmarks(entries)


class BookmarkButton(QToolButton):
    """One entry on the bookmarks bar. Left click opens it in this tab
    (a folder drops its menu down), middle click opens it in a new tab,
    right click offers rename and delete."""

    def __init__(self, browser, entry):
        super().__init__(objectName="bmitem")
        self.browser = browser
        self.entry = entry
        title = (entry.get("title") or "").strip()
        if entry["type"] == "link" and not title:
            title = QUrl(entry["url"]).host() or entry["url"]
        self.setToolTip(entry.get("url") or title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # a plain character budget, not fontMetrics: the stylesheet's
        # font only reaches the widget on polish, long after __init__
        short = title if len(title) <= 23 else title[:22].rstrip() + "\u2026"
        if entry["type"] == "folder":
            self.setText("\u25b8 " + short)
        else:
            icon = _icon_from_data(entry.get("icon", ""))
            self.setIcon(icon if not icon.isNull() else _blank_favicon())
            self.setIconSize(QSize(16, 16))
            self.setText(short)
            self.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.clicked.connect(self._left_click)

    def _menu_later(self, opener):
        """The menu goes up a tick later, on a clean stack, holding only
        the entry and a point — never this widget.

        Deleting an entry from its own menu does tear this button down
        mid-menu, but Qt holds a deleteLater() posted inside a nested
        loop until the loop that was current when it was posted exits,
        so the button outlives the call either way. This is tidiness,
        not a fix: it just means nothing here has to rely on knowing
        that."""
        where = self.mapToGlobal(self.rect().bottomLeft())
        entry = self.entry
        QTimer.singleShot(0, lambda: opener(entry, where))

    def _left_click(self):
        if self.entry["type"] == "folder":
            self._menu_later(self.browser.bookmark_folder_menu)
        else:
            self.browser.open_bookmark(self.entry)

    def mousePressEvent(self, event):
        # QToolButton only ever reacts to the left button, so the other
        # two are handled on press before it drops them on the floor
        if event.button() == Qt.MouseButton.MiddleButton:
            self.browser.open_bookmark(self.entry, new_tab=True)
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._menu_later(self.browser.bookmark_menu)
            return
        super().mousePressEvent(event)


class BookmarkMenu(QMenu):
    """A drop-down of bookmarks whose rows can be right-clicked, the
    way Edge's Favourites list can.

    It is a shortcut and never the only way in: every folder submenu
    spells Rename, New folder and Delete out as items you can see and
    click, because a right-click inside a menu is a thing you have to
    already know about. Somebody who does know it should not have to
    go and find the manager.

    Each row carries its entry in the action's data, folders included —
    a submenu's own menuAction() is the row you point at, so setting the
    data there is what makes a folder answer."""

    def __init__(self, browser, parent=None):
        # a submenu belongs to the menu above it; a menu that starts a
        # chain belongs to the window, exactly as a plain QMenu(self)
        # built anywhere else in here does. Parentless it would be
        # collected the moment the last name for it went out of scope,
        # taking every submenu under it with it.
        super().__init__(parent if parent is not None else browser)
        self.browser = browser

    def contextMenuEvent(self, event):
        action = self.actionAt(event.pos())
        entry = action.data() if action is not None else None
        if not isinstance(entry, dict) or "id" not in entry:
            return   # a row that is not a bookmark: nothing to offer
        where = event.globalPos()
        browser = self.browser
        top = self
        while isinstance(top.parent(), QMenu):
            top = top.parent()
        # the menu he right-clicked in goes first, then the second menu
        # opens on a clean stack — one drop-down on the screen at a time
        top.close()
        QTimer.singleShot(0, lambda: browser.bookmark_menu(entry, where))


class FavoritesTree(QTreeWidget):
    """The list inside the Favourites panel, and the dragging that goes
    on in it.

    Qt is never allowed to move a row by itself. An internal move would
    shuffle the widget and leave bookmarks.json exactly as it was, and
    the next redraw would put everything back — so the drop is read off
    the indicator, handed to the browser's own list, and the tree is
    built again from what came out of that. One story about where a
    bookmark is, and the file tells it.

    The indicator is drawn here rather than by the style. Dropping
    *into* a folder and dropping *between* two rows are different
    things and have to look different: a box round the folder for one,
    a line between the rows for the other, and the line starts where
    the rows it sits between start, so which folder it is going into is
    on the screen too."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self._drop = None      # (kind, rect) while a drag is over us
        self._dragged = 0      # the id being dragged, from startDrag
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        # left on: it is what makes Qt work out whether the pointer is
        # over a row or between two of them, which is the whole question
        # here. Qt's own hairline is drawn underneath ours and says the
        # same thing more quietly.
        self.setDropIndicatorShown(True)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(28)

    # ---- what a drop at this point would mean
    def _target(self, item, where):
        """(folder id, seat among its children) for an indicator, or
        None when the drop would mean nothing."""
        panel = self.panel
        onto = QAbstractItemView.DropIndicatorPosition
        if item is None or where == onto.OnViewport:
            return 0, BOOKMARKS_MAX      # the empty space below: the root
        entry = panel._entry(item)
        if entry is None:
            return None                  # the "nothing found" line
        if where == onto.OnItem:
            if entry["type"] == "folder":
                return entry["id"], BOOKMARKS_MAX
            where = onto.BelowItem       # a bookmark cannot hold anything
        parent = item.parent()
        above = parent if parent is not None else self.invisibleRootItem()
        seat = above.indexOfChild(item)
        if where == onto.BelowItem:
            seat += 1
        holder = panel._entry(parent)
        return (holder["id"] if holder else 0), seat

    def _ours(self, event):
        """Only a row this list itself picked up.

        `_dragged` is set in startDrag and cleared the moment it
        returns, so anything from outside — a file off the desktop, a
        link out of a page — arrives to find it empty and is turned
        away. That is a firmer question than asking the event who its
        source is, and it can be asked on any platform: a drag from
        another process has no source to name."""
        if not self._dragged:
            return False
        source = event.source()
        return source is None or source is self

    def _allowed(self, target):
        if target is None or not self._dragged:
            return False
        browser = self.panel.browser
        moving = browser._bookmark_by_id(self._dragged)
        if moving is None:
            return False
        if moving["type"] != "folder":
            return True
        # a folder into itself, or into anything already inside it
        return target[0] not in browser._bookmark_subtree(self._dragged)

    # ---- the drag itself
    def startDrag(self, actions):
        entry = self.panel._entry(self.currentItem())
        self._dragged = entry["id"] if entry is not None else 0
        if not self._dragged:
            return
        self.panel.dragging = True
        try:
            super().startDrag(actions)
        finally:
            self.panel.dragging = False
            self._dragged = 0
            self._clear_drop()

    def dragEnterEvent(self, event):
        if not self._ours(event):
            event.ignore()      # nothing from outside this list, ever
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if not self._ours(event):
            event.ignore()
            return
        super().dragMoveEvent(event)     # this is what works the indicator
        if not event.isAccepted():
            # Qt has already said no - a row dropped on itself, say.
            # Its no stands; this only ever narrows what is allowed.
            self._clear_drop()
            return
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        where = self.dropIndicatorPosition()
        target = self._target(item, where)
        if not self._allowed(target):
            self._clear_drop()
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self._mark(item, where)

    def dragLeaveEvent(self, event):
        self._clear_drop()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        """Read, then handed on. super() is never called: letting the
        base class do the move is what would take the row out of the
        widget behind the browser's back."""
        if not self._ours(event):
            event.ignore()
            return
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        target = self._target(item, self.dropIndicatorPosition())
        moved = self._dragged
        self._clear_drop()
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        # accepted first, then handed to the base class: its dropOn()
        # turns straight round on an event that is already accepted, so
        # it never touches the model - but it still stops the autoscroll
        # and puts the tree back into NoState, which it must
        super().dropEvent(event)
        if self._allowed(target) and moved:
            self.panel.drop_onto(moved, target[0], target[1])

    # ---- drawing where it would land
    def _mark(self, item, where):
        onto = QAbstractItemView.DropIndicatorPosition
        if item is None or where == onto.OnViewport:
            last = self.topLevelItem(self.topLevelItemCount() - 1)
            bottom = (self.visualItemRect(last).bottom() + 1
                      if last is not None else 0)
            self._set_drop(("between",
                            QRect(0, bottom, self.viewport().width(), 0)))
            return
        rect = self.visualItemRect(item)
        entry = self.panel._entry(item)
        if where == onto.OnItem and entry and entry["type"] == "folder":
            self._set_drop(("into", QRect(0, rect.top(),
                                          self.viewport().width(),
                                          rect.height())))
            return
        y = rect.top() if where == onto.AboveItem else rect.bottom() + 1
        # the line starts where the rows do, so its indent says which
        # folder it would be dropping into
        self._set_drop(("between",
                        QRect(rect.left(), y,
                              self.viewport().width() - rect.left(), 0)))

    def _set_drop(self, mark):
        if mark != self._drop:
            self._drop = mark
            self.viewport().update()

    def _clear_drop(self):
        if self._drop is not None:
            self._drop = None
            self.viewport().update()

    def paintEvent(self, event):
        # Qt's own hairline is switched off for the length of the paint
        # and straight back on again. The flag has to stay on the rest
        # of the time - it is what makes dragMoveEvent work out whether
        # the pointer is over a row or between two - but two indicators
        # saying the same thing in two weights is one too many.
        self.setDropIndicatorShown(False)
        try:
            super().paintEvent(event)
        finally:
            self.setDropIndicatorShown(True)
        if self._drop is None:
            return
        kind, rect = self._drop
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor(theme_color("text")), 2))
        if kind == "into":
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(rect.adjusted(1, 1, -2, -2))
        else:
            y = max(1, min(rect.top(), self.viewport().height() - 2))
            painter.drawLine(rect.left(), y, rect.right(), y)
            painter.drawLine(rect.left() + 1, y - 4, rect.left() + 1, y + 4)
        painter.end()


class FavoritesPanel(QWidget):
    """Edge's Favourites panel — and deliberately not a chain of menus.

    A menu whose folders open sideways asks you to hold the pointer
    inside a narrow corridor while you drag it across: stray off the
    path and the whole chain shuts and you begin again. That is a
    fiddly game at the best of times and an unkind one for hands that
    are not steady, which is the whole reason this browser has a
    Favourites button at all. So this is what Edge really puts under
    its own: a panel that drops down and stays down. A title, a search
    box, and one list underneath. A folder opens *in place* — the list
    grows downwards, nothing flies out sideways — and it stays open
    until it is closed again. A missed click costs nothing.

    It is a widget over the window and not a popup of its own, which
    matters more than it sounds. A Qt popup holds the mouse grab, and
    a drag needs that grab; starting one inside a popup is how a panel
    ends up shutting itself the moment you pick a bookmark up. So this
    is a sheet the size of the window with the card sitting on it: the
    sheet paints nothing at all, it is only there to catch the click
    that means "somewhere else", and dragging inside the card is
    ordinary dragging inside an ordinary window.

    Every row carries a ⋯ of its own at the right-hand end, and it
    is always there rather than appearing on hover. A right-click on
    the row does the same thing, for anyone who has the habit; nothing
    is only reachable that way, because knowing that a right-click is a
    thing is exactly what cannot be assumed here.

    Renaming happens in the row itself, not in a dialog: a box on top
    of a panel is one more window to understand."""

    WIDTH = 440
    MIN_H = 240
    MAX_H = 560
    ROW = 30

    def __init__(self, browser):
        super().__init__(browser, objectName="favshade")
        self.browser = browser
        self.dragging = False   # a drag in flight: the sheet stays put
        self._open = set()      # the folder ids he has opened, kept across
        self._busy = False      # rebuilds. Guards the tree's own signals
        self._rows = 0

        self.card = QWidget(self, objectName="favpanel")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        head = QWidget(objectName="favhead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(13, 10, 7, 8)
        hl.setSpacing(8)
        self.title = QLabel(objectName="favtitle")
        self.shut = QToolButton(text="\u2715", objectName="favshut")
        self.shut.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shut.clicked.connect(self.close)
        hl.addWidget(self.title, 1)
        hl.addWidget(self.shut)
        lay.addWidget(head)

        box = QWidget(objectName="favsearchbox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(13, 0, 13, 8)
        bl.setSpacing(5)
        self.search = QLineEdit(objectName="favsearch")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._filter())
        self.hint = QLabel(objectName="favhint")
        bl.addWidget(self.search)
        bl.addWidget(self.hint)
        lay.addWidget(box)

        self.tree = FavoritesTree(self)
        tree = self.tree
        tree.setObjectName("favtree")
        tree.setColumnCount(2)
        tree.setHeaderHidden(True)
        tree.setIndentation(16)
        tree.setUniformRowHeights(True)
        tree.setIconSize(QSize(16, 16))
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # a rename happens when it is asked for and never because a
        # second click landed on a row he was only trying to open
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._menu_at)
        tree.itemClicked.connect(self._clicked)
        tree.itemChanged.connect(self._renamed)
        tree.itemExpanded.connect(lambda i: self._remember(i, True))
        tree.itemCollapsed.connect(lambda i: self._remember(i, False))
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(1, 36)
        lay.addWidget(tree, 1)

        # two rows rather than one: three buttons side by side would
        # set a floor under the panel's width half again as wide as the
        # list it sits under
        foot = QWidget(objectName="favfoot")
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(11, 9, 11, 11)
        fl.setSpacing(7)
        top = QHBoxLayout()
        top.setSpacing(7)
        self.addbtn = QToolButton(objectName="favbtn")
        self.addbtn.clicked.connect(lambda: self._add_page(0))
        self.foldbtn = QToolButton(objectName="favbtn")
        self.foldbtn.clicked.connect(lambda: self.new_folder(0))
        self.managebtn = QToolButton(objectName="favbtn")
        self.managebtn.clicked.connect(self._manage)
        for button in (self.addbtn, self.foldbtn, self.managebtn):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        top.addWidget(self.addbtn)
        top.addStretch(1)
        top.addWidget(self.foldbtn)
        fl.addLayout(top)
        bottom = QHBoxLayout()
        bottom.addWidget(self.managebtn)
        bottom.addStretch(1)
        fl.addLayout(bottom)
        lay.addWidget(foot)

        browser.bridge.bookmarksChanged.connect(self._changed)

    # ---------------------------------------------------------- opening
    def open_up(self):
        """Down from the button, and never off the edge of the window."""
        self.relabel()
        self.refill()
        self.search.clear()
        self.place()
        self.show()
        self.raise_()
        self.search.setFocus()

    def place(self):
        """The sheet is the window; the card hangs off the button. Asked
        again on every resize, so the card follows the button rather
        than being left behind at the old width."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        btn = parent._tb_buttons.get("favorites")
        anchor = btn if (btn is not None and btn.isVisible()) else parent.urlbar
        at = anchor.mapTo(parent, QPoint(0, anchor.height() + 3))
        card = self.card
        x = max(6, min(at.x(), self.width() - card.width() - 6))
        y = max(6, min(at.y(), max(6, self.height() - card.height() - 6)))
        card.move(x, y)

    def mousePressEvent(self, event):
        """A press on the sheet is a press somewhere else: the panel
        closes. Never while a drag is in flight — a bookmark in the air
        is not a change of mind."""
        if not self.dragging:
            self.close()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key.Key_F2:
            self.rename(self.tree.currentItem())
            return
        super().keyPressEvent(event)

    def relabel(self):
        """Its words, in his language. Asked again every time it opens,
        so a language changed behind it is right the next time."""
        say = self.browser._ui_str
        self.title.setText(say("tbFavorites"))
        self.shut.setToolTip(say("close"))
        self.search.setPlaceholderText(say("bmSearch"))
        self.hint.setText(say("bmFavHint"))
        self.foldbtn.setText(say("bmNewFolder"))
        self.managebtn.setText(say("bmManage"))
        self._sync_add()

    def _sync_add(self):
        """The one button that changes what it says: this page is in
        there, or it is not, exactly like the star."""
        browser = self.browser
        url = browser._bookmarkable()
        here = browser._bookmark_for(url) if not url.isEmpty() else None
        self.addbtn.setEnabled(not url.isEmpty())
        self.addbtn.setText(browser._ui_str("bmRemove" if here
                                            else "bmAdd"))

    # ---------------------------------------------------------- filling
    def _entry(self, item):
        if item is None:
            return None
        return self.browser._bookmark_by_id(
            item.data(0, Qt.ItemDataRole.UserRole))

    def _changed(self):
        """The collection moved somewhere else — the star, the bar, the
        manager, or this panel itself. Redrawn a tick later: this also
        fires from inside the tree's own itemChanged, and clearing a
        tree from inside its own signal is asking for trouble."""
        if self.isVisible():
            QTimer.singleShot(0, self._maybe_refill)

    def _maybe_refill(self):
        """Not while he is typing a name into a row, and not with a
        bookmark in the air. Making a folder saves the list, which lands
        back here as a change to redraw — and redrawing would pull the
        row out from under the name box that was opened for it."""
        if self.tree.state() == QAbstractItemView.State.EditingState:
            return
        if self.dragging:
            return
        self.refill()

    def refill(self):
        self._busy = True
        chosen = self._entry(self.tree.currentItem())
        self.tree.clear()
        self._rows = 0
        self._fill(self.tree.invisibleRootItem(), 0, 0)
        if not self.browser.bookmarks:
            self._placeholder(self.browser._ui_str("bmNoBookmarks"))
        self._busy = False
        if chosen is not None:
            item = self._find(chosen["id"])
            if item is not None:
                self.tree.setCurrentItem(item)
        self._filter()
        self._sync_add()
        self._resize()

    def _fill(self, parent, fid, depth):
        for entry in self.browser._bookmark_kids(fid):
            item = QTreeWidgetItem(parent)
            item.setText(0, self.browser._bm_label(entry))
            item.setData(0, Qt.ItemDataRole.UserRole, entry["id"])
            item.setText(1, "\u22ef")
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
            item.setToolTip(1, self.browser._ui_str("bmMore"))
            flags = (Qt.ItemFlag.ItemIsEnabled
                     | Qt.ItemFlag.ItemIsSelectable
                     | Qt.ItemFlag.ItemIsDragEnabled)
            self._rows += 1
            if entry["type"] == "folder":
                item.setIcon(0, self.browser._folder_icon())
                # only a folder may be dropped into
                flags |= Qt.ItemFlag.ItemIsDropEnabled
                item.setFlags(flags)
                if depth < BOOKMARKS_DEPTH:
                    self._fill(item, entry["id"], depth + 1)
                item.setExpanded(entry["id"] in self._open)
            else:
                item.setFlags(flags)
                item.setIcon(0, self.browser.bookmark_icon(entry))
                item.setToolTip(0, entry.get("url") or "")

    def _placeholder(self, text):
        item = QTreeWidgetItem(self.tree.invisibleRootItem())
        item.setText(0, text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)

    def _find(self, bid, parent=None):
        parent = self.tree.invisibleRootItem() if parent is None else parent
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == bid:
                return child
            found = self._find(bid, child)
            if found is not None:
                return found
        return None

    def _resize(self):
        """As tall as its rows want, and never taller than the window
        it hangs in. A card that runs off the bottom edge is cut there,
        and what is along the bottom of this one is the row of buttons
        — so the first thing to go is the half of "Remove bookmark"
        below the middle of the letters. Adding a bookmark from the
        panel is exactly when that happens: the list grows by a row and
        the button changes to say Remove at the same moment."""
        rows = max(1, min(self._rows, 40))
        row = (self.tree.sizeHintForRow(0) if self.tree.topLevelItemCount()
               else self.ROW)
        chrome = (self.card.layout().sizeHint().height()
                  - self.tree.sizeHint().height())
        height = max(self.MIN_H, min(self.MAX_H, chrome + row * rows + 8))
        room = self.headroom()
        if height > room:
            # whole rows or none. A list stopped through the middle of
            # a row is a row with its bottom half sliced off, which is
            # the thing this is here to stop rather than move
            height = min(height, chrome + row * max(1, (room - chrome - 8)
                                                    // row) + 8)
        self.card.resize(self.WIDTH, min(height, room))
        # placed again from here and not only when it opens: the card
        # is resized every time the collection changes underneath it,
        # and a taller card measured against the old corner is a card
        # off the edge
        if self.isVisible():
            self.place()

    def headroom(self):
        """The tallest the card may be and still stand clear of both
        edges of the window. Never below what the card itself cannot
        shrink under — Qt would refuse that anyway, and pretending
        otherwise would only move the clipping somewhere else."""
        parent = self.parentWidget()
        if parent is None:
            return self.MAX_H
        floor = self.card.minimumSizeHint().height()
        return max(floor, parent.height() - 12)

    def _remember(self, item, opened):
        if self._busy:
            return
        entry = self._entry(item)
        if entry is None:
            return
        if opened:
            self._open.add(entry["id"])
        else:
            self._open.discard(entry["id"])

    # ------------------------------------------------------- dropping in
    def drop_onto(self, bid, parent, seat):
        """A row let go of. `seat` was counted among the rows on the
        screen, and move_bookmark counts among the entries left after
        the one being moved is taken out — so a row moving further down
        inside its own folder loses one place on the way."""
        browser = self.browser
        entry = browser._bookmark_by_id(bid)
        if entry is None:
            return
        if (entry["type"] == "folder"
                and parent in browser._bookmark_subtree(bid)):
            return
        if entry["parent"] == parent:
            kids = browser._bookmark_kids(parent)
            if entry in kids and kids.index(entry) < seat:
                seat -= 1
        elif parent:
            self._open.add(parent)   # show him where it went
        browser.move_bookmark(bid, parent, seat)
        self.refill()
        item = self._find(bid)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    # -------------------------------------------------------- searching
    def _filter(self):
        """What he typed, against titles and addresses. A folder stays
        on the list while anything inside it matches, and opens itself
        so he can see what did — and closes back to however he had it
        the moment the box is empty again."""
        query = self.search.text().strip().lower()
        self._drop_placeholder()
        self._busy = True
        hits = self._walk(self.tree.invisibleRootItem(), query)
        self._busy = False
        self.hint.setVisible(not query)
        if query and not hits and self.browser.bookmarks:
            self._placeholder(self.browser._ui_str("bmNoBookmarks"))

    def _drop_placeholder(self):
        """The "nothing found" line, taken off before the next keystroke
        is answered — left where it was, one per letter typed would pile
        up down the panel."""
        if not self.browser.bookmarks:
            return   # an empty collection keeps its line
        last = self.tree.topLevelItem(self.tree.topLevelItemCount() - 1)
        if last is not None and last.flags() == Qt.ItemFlag.NoItemFlags:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(last))

    def _walk(self, item, query):
        inside = 0
        for i in range(item.childCount()):
            inside += self._walk(item.child(i), query)
        entry = self._entry(item)
        if entry is None:
            return inside
        hay = (item.text(0) + " " + (entry.get("url") or "")).lower()
        mine = (not query) or (query in hay)
        show = mine or inside > 0
        item.setHidden(not show)
        if entry["type"] == "folder":
            item.setExpanded(bool(inside) if query
                             else entry["id"] in self._open)
        return 1 if show else 0

    # --------------------------------------------------------- clicking
    def _clicked(self, item, column):
        entry = self._entry(item)
        if entry is None:
            return
        if column == 1:
            rect = self.tree.visualItemRect(item)
            self._menu_for(item, self.tree.viewport().mapToGlobal(
                QPoint(rect.right() - 6, rect.bottom())))
            return
        if entry["type"] == "folder":
            item.setExpanded(not item.isExpanded())
            return
        self.close()
        self.browser.open_bookmark(entry)

    def _menu_at(self, pos):
        item = self.tree.itemAt(pos)
        if item is not None:
            self._menu_for(item, self.tree.viewport().mapToGlobal(pos))

    def _menu_for(self, item, where):
        """Shown with popup() and not exec(): a nested event loop in the
        middle of a click on a list is a thing to do without if it can
        be done without. The actions come back as signals."""
        menu = self.row_menu(item)
        if menu is None:
            return
        self._rowmenu = menu     # a name for it, so nothing collects it
        menu.popup(where)

    def row_menu(self, item):
        """Everything this row can have done to it. Built apart from the
        click that shows it, so what it says can be read without a menu
        having to be on the screen.

        Move to folder stays here now that a row can be dragged. Anyone
        who cannot hold a mouse button down and steer at the same time
        still has to be able to move a bookmark, and having both costs
        nothing."""
        entry = self._entry(item)
        if entry is None:
            return None
        browser = self.browser
        menu = QMenu(self)
        if entry["type"] == "link":
            menu.addAction(browser._ui_str("bmOpen")).triggered.connect(
                lambda: self._open_row(entry, False))
            menu.addAction(browser._ui_str("bmOpenNew")).triggered.connect(
                lambda: self._open_row(entry, True))
        else:
            links = [k for k in browser._bookmark_kids(entry["id"])
                     if k["type"] == "link"]
            if links:
                menu.addAction(
                    browser._ui_str("bmOpenAll")).triggered.connect(
                    lambda _=False, ks=links: self._open_all(ks))
            add = menu.addAction(browser._ui_str("bmAdd"))
            add.setEnabled(not browser._bookmarkable().isEmpty())
            add.triggered.connect(lambda: self._add_page(entry["id"]))
            menu.addAction(
                browser._ui_str("bmNewFolder")).triggered.connect(
                lambda: self.new_folder(entry["id"]))
        menu.addSeparator()
        menu.addAction(browser._ui_str("bmRename")).triggered.connect(
            lambda: self.rename(item))
        if entry["type"] == "link":
            menu.addAction(browser._ui_str("bmEditUrl")).triggered.connect(
                lambda: self._readdress(entry))
        move = menu.addMenu(browser._ui_str("bmMoveTo"))
        browser.fill_folder_picker(
            move, lambda fid: browser.move_bookmark(entry["id"], fid,
                                                    BOOKMARKS_MAX),
            barred=(browser._bookmark_subtree(entry["id"])
                    if entry["type"] == "folder" else set()),
            here=entry["parent"])
        menu.addSeparator()
        browser._add_delete_action(menu, entry)
        return menu

    def _open_row(self, entry, new_tab):
        self.close()
        self.browser.open_bookmark(entry, new_tab=new_tab)

    def _open_all(self, links):
        self.close()
        for link in links:
            self.browser.open_bookmark(link, new_tab=True)

    def _readdress(self, entry):
        """The address box is a dialog, opened on a clean stack rather
        than from inside the menu that asked for it."""
        QTimer.singleShot(
            0, lambda: self.browser._readdress_bookmark(entry))

    def _manage(self):
        self.close()
        self.browser.open_bookmarks()

    # ----------------------------------------------------------- making
    def _add_page(self, parent=0):
        """The page he is on: in, or back out again if it is already
        there, exactly like the star. Then the row it landed on is
        picked out, so he can see where it went."""
        browser = self.browser
        url = browser._bookmarkable()
        if url.isEmpty():
            return
        if browser._bookmark_for(url) is not None and not parent:
            browser.toggle_bookmark()
            return
        if parent:
            self._open.add(parent)
        browser.add_bookmark_here(parent)
        self.refill()
        entry = browser._bookmark_for(url)
        if entry is not None:
            item = self._find(entry["id"])
            if item is not None:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)

    def new_folder(self, parent=0):
        """A folder, and then straight into naming it. No dialog and no
        folder called "New folder" left lying about for him to work out
        how to rename later."""
        bid = self.browser.add_bookmark_folder("", parent)
        if not bid:
            return
        if parent:
            self._open.add(parent)
        self._open.add(bid)
        self.search.clear()
        self.refill()
        item = self._find(bid)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
            self.rename(item)

    def rename(self, item):
        """In the row itself. The flag goes on for this one edit and
        comes off again when it is over, so an ordinary click on a row
        can never turn into a rename he did not ask for."""
        if self._entry(item) is None:
            return
        # putting the flag on is itself a change to the item, and the
        # handler for that takes the flag straight back off again - so
        # the guard goes up around it or the edit never opens
        self._busy = True
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._busy = False
        self.tree.setCurrentItem(item)
        self.tree.editItem(item, 0)

    def _renamed(self, item, column):
        """The edit box closed. Everything this touches on the item —
        putting the editable flag away, putting an emptied name back —
        is itself a change to the item, so the guard goes up first or
        this calls itself until the stack runs out."""
        if self._busy or column != 0:
            return
        entry = self._entry(item)
        self._busy = True
        try:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            text = item.text(0).strip()
            if entry is None:
                return
            if not text:      # a name rubbed out is not a name
                item.setText(0, self.browser._bm_label(entry))
                return
        finally:
            self._busy = False
        if text != self.browser._bm_label(entry):
            self.browser.update_bookmark(entry["id"], text,
                                         entry.get("url", ""))


class BookmarksBar(QWidget):
    """The strip of bookmarks under the address bar.

    It places its own children instead of handing them to a
    QHBoxLayout, and that is the whole point. A layout pushes the sum
    of its children's minimum widths up through QMainWindow, so a
    dozen bookmarks with ordinary titles would quietly decide that the
    window may never be narrower than three thousand pixels — the star,
    the proxy button and half the address bar would go off the edge of
    the screen and stay there.

    So: this asks for no width at all, fills the row with as many
    entries as really fit, and puts everything after that behind a »
    menu. Nothing is built while the bar is hidden, and the row is
    capped, so the cost does not follow the size of the collection."""

    MARGIN_X = 8
    MARGIN_TOP = 3
    MARGIN_BOTTOM = 4
    GAP = 2
    MAX_BUTTONS = 60  # a row this long has not fit on a screen yet

    def __init__(self, browser):
        super().__init__(objectName="bmbar")
        self.browser = browser
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(browser._bmbar_menu)
        self._entries = []   # the root bookmarks, in order
        self._buttons = []   # the ones built so far, same order
        self._shown = 0      # how many of them are on the row
        self.more = QToolButton(self, text="\u00bb", objectName="bmmore")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.clicked.connect(self._overflow_menu)
        self.more.hide()
        self.empty = QLabel("", self, objectName="bmempty")
        self.empty.hide()
        self._row = self._measure_row()
        self.setFixedHeight(self._row + self.MARGIN_TOP + self.MARGIN_BOTTOM)

    def _measure_row(self):
        """How tall one entry is, asked of a real button once, so the
        strip is the right height for the stylesheet's font."""
        probe = BookmarkButton(self.browser, {
            "type": "link", "title": "Ag", "url": "https://x.example/",
            "icon": "", "id": 0, "parent": 0})
        probe.setParent(self)
        probe.ensurePolished()
        height = probe.sizeHint().height()
        probe.setParent(None)
        probe.deleteLater()
        return max(20, height)

    # -- the bar never dictates how narrow the window may be
    def minimumSizeHint(self):
        return QSize(0, self.height())

    def sizeHint(self):
        return QSize(0, self.height())

    def set_entries(self, entries):
        """The list changed: drop the row and lay it out again."""
        for button in self._buttons:
            button.setParent(None)
            button.deleteLater()
        self._buttons = []
        self._entries = entries
        self.empty.setText(self.browser._ui_str("bmBarEmpty"))
        self.empty.adjustSize()
        self._relayout()

    def update_icon(self, entry):
        """A favicon arrived for one bookmark. Just that button, please:
        rebuilding the row for it is what used to freeze the browser
        for half a minute on a big collection."""
        for button in self._buttons:
            if button.entry is entry:
                icon = _icon_from_data(entry.get("icon", ""))
                button.setIcon(icon if not icon.isNull() else _blank_favicon())
                return

    def _button(self, index):
        while len(self._buttons) <= index:
            button = BookmarkButton(self.browser,
                                    self._entries[len(self._buttons)])
            button.setParent(self)
            button.ensurePolished()
            button.resize(button.sizeHint().width(), self._row)
            self._buttons.append(button)
        return self._buttons[index]

    def _relayout(self):
        # a hidden bar builds nothing at all; showEvent brings it back
        if not self.isVisible():
            return
        total = len(self._entries)
        self.empty.setVisible(total == 0)
        if total == 0:
            self.empty.move(self.MARGIN_X, self.MARGIN_TOP)
            self.more.hide()
            return
        self.more.resize(self.more.sizeHint().width(), self._row)
        right = self.width() - self.MARGIN_X
        x = self.MARGIN_X
        shown = 0
        for i in range(min(total, self.MAX_BUTTONS)):
            button = self._button(i)
            # everything but a last entry has to leave the » its corner
            edge = right if i == total - 1 else right - self.more.width() - self.GAP
            if shown and x + button.width() > edge:
                break
            button.move(x, self.MARGIN_TOP)
            button.show()
            x += button.width() + self.GAP
            shown += 1
        for button in self._buttons[shown:]:
            button.hide()
        self._shown = shown
        if shown < total:
            self.more.move(right - self.more.width(), self.MARGIN_TOP)
            self.more.show()
            self.more.raise_()  # a squeezed row must not bury the way out
            self.more.setToolTip(self.browser._ui_str("bmMore"))
        else:
            self.more.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout()

    def _overflow_menu(self):
        """Everything the row had no room for, folders and all."""
        browser = self.browser
        menu = BookmarkMenu(browser)
        browser._fill_entries(menu, self._entries[self._shown:], 1)
        menu.addSeparator()
        menu.addAction(browser._ui_str("bmManage")).triggered.connect(
            browser.open_bookmarks)
        menu.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))
class SharePicker(QWidget):
    """Where a getDisplayMedia() call is answered.

    Qt does not ask whether a page may capture the desktop, it asks
    *what* it should capture: the request carries a list of screens and
    a list of windows, and exactly one of them — or nothing — goes back.
    So this is a picker, not a yes/no card, and it is the browser's half
    of the handshake. On Wayland the compositor's own portal dialog then
    has the last word over what the cast may really see; that is the
    desktop's business and this does not try to talk it out of it.

    Esc, Cancel and a click outside the panel all mean no: a request
    that is never answered leaves the page hanging forever.

    The request is a borrowed temporary, and unlike a permission it has
    no copy constructor to park an owned copy in — its screen and window
    models are torn down the moment the slot returns. So the picker runs
    a nested event loop and the slot does not return until the user has
    pointed at something, which is what makes a modal dialog modal. The
    rest of the browser keeps drawing and scrolling meanwhile."""

    def __init__(self, browser, request, origin, sources=()):
        super().__init__(browser, objectName="sharepane")
        self.browser = browser
        self.request = request
        self.answered = False
        self.lost = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # The engine's half of this request is a callback holding a raw,
        # non-owning pointer to the tab's WebContents. The nested loop
        # below is what lets the tab be closed while the picker is up,
        # and once that tab is gone answering the request — or even
        # cancelling it — walks straight into freed memory. So watch the
        # tab: deleteLater is how every close path gets there, and the
        # event arrives while the tab is still whole, which is the last
        # moment an answer can safely be sent.
        self.sources = [s for s in sources if s is not None]
        for source in self.sources:
            source.installEventFilter(self)
            source.destroyed.connect(self._lost)

        self.panel = QWidget(self, objectName="sharepanel")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(10)
        title = QLabel("%s wants to share a screen or a window." % origin)
        title.setWordWrap(True)
        col.addWidget(title)

        body = QWidget()
        rows = QVBoxLayout(body)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        self.choices = 0
        for heading, model, pick in (
                ("Screens", request.screensModel(), request.selectScreen),
                ("Windows", request.windowsModel(), request.selectWindow)):
            count = model.rowCount() if model is not None else 0
            if not count:
                continue
            rows.addWidget(QLabel(heading, objectName="sharehead"))
            for row in range(count):
                name = model.index(row, 0).data(Qt.ItemDataRole.DisplayRole)
                button = QToolButton(text=str(name or "%s %d"
                                              % (heading[:-1], row + 1)),
                                     objectName="shareitem")
                button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding,
                                     QSizePolicy.Policy.Fixed)
                button.clicked.connect(
                    lambda _, p=pick, m=model, r=row: self._choose(p, m, r))
                rows.addWidget(button)
                self.choices += 1
        if not self.choices:
            rows.addWidget(QLabel("Nothing here can be shared."))
        rows.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch()
        cancel = QToolButton(text="Cancel", objectName="sharecancel")
        cancel.clicked.connect(self.cancel)
        foot.addWidget(cancel)
        col.addLayout(foot)

        esc = QShortcut(QKeySequence("Esc"), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self.cancel)
        self.esc = esc
        self._loop = None

    def wait(self):
        """Block the signal handler until the request has been answered
        — quitting too if the picker or the whole browser goes away."""
        loop = self._loop = QEventLoop()
        self.destroyed.connect(loop.quit)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(loop.quit)
        try:
            if not self.answered:
                loop.exec()
        finally:
            self._loop = None
            if app is not None:  # the loop is about to go; let go of it
                app.aboutToQuit.disconnect(loop.quit)

    def place(self):
        """Centred on the window, never wider or taller than it."""
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        width = max(240, min(520, self.width() - 48))
        self.panel.setFixedWidth(width)
        wanted = self.panel.sizeHint().height()
        height = max(140, min(wanted, self.height() - 48))
        self.panel.resize(width, height)
        self.panel.move((self.width() - width) // 2,
                        (self.height() - height) // 2)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.DeferredDelete
                and obj in self.sources and not self.answered):
            # a backstop only: every place in here that gives up a tab
            # calls Browser._drop_share first, which is earlier and
            # safer. By the time a deletion has got this far the tab may
            # already be half gone, and there is no answer that is safe
            # in every such case — cancelling is right when the tab
            # alone is going, which is what an unforeseen path most
            # likely is.
            self.cancel()
        return super().eventFilter(obj, event)

    def owns(self, widget):
        """Whether this picker belongs to that tab."""
        return widget is not None and widget in self.sources

    def _lost(self):
        """The tab went without a DeferredDelete anybody could see —
        torn down by its parent, say. Nothing may be sent any more, so
        the request is abandoned unanswered and the page simply never
        hears back; a hung promise beats a use-after-free."""
        self.lost = True
        self.answered = True
        self._done()

    def _choose(self, pick, model, row):
        if self.answered:
            return
        self.answered = True
        try:
            # rows are looked up now, not stashed: a QModelIndex kept
            # over a click is not worth the paper it is printed on
            pick(model.index(row, 0))
        except RuntimeError:
            pass  # the request left with its tab while the picker was up
        self._done()

    def cancel(self):
        if not self.answered:
            self.answered = True
            if not self.lost:
                try:
                    self.request.cancel()
                except RuntimeError:
                    pass
        self._done()

    def _done(self):
        for source in self.sources:
            try:
                source.removeEventFilter(self)
            except RuntimeError:
                pass
        self.hide()
        if self._loop is not None:
            self._loop.quit()

    def mousePressEvent(self, event):
        # a click on the dimmed area outside the panel means no
        if not self.panel.geometry().contains(event.pos()):
            self.cancel()


class AccountChooser(QWidget):
    """Which of the saved accounts is signing in here.

    Browser chrome on purpose, and the whole point of the feature. A
    list of accounts drawn into the page would be readable by the page,
    and then merely showing a sign-in form would tell a site every
    account its visitor keeps there — before he had chosen anything, and
    whether or not he ever meant to sign in. So the names live in a Qt
    widget over the window, never in a document: nothing about this
    panel exists in any renderer, and only the one account he points at
    ever crosses, only to the host it was saved for.

    Names and nothing else. No password, no strength, no two-factor
    code, nothing computed from a secret — not even a hint of how many
    characters long it is. The password is looked up at the moment of
    the click, from the vault, by name; this widget never holds one.

    Pointing at a name is what authorises the fill. It is a real
    gesture in the same sense the watcher script means by isTrusted — a
    Qt press on a widget the page cannot reach, move, cover or
    synthesise — which is why the isolated world may write the password
    straight in instead of arming and waiting for a touch on the page.
    Esc, "Not now" and a click on the dimmed area outside the panel all
    mean no, and no means nothing is filled at all."""

    def __init__(self, browser, page, host, scheme, names, body_text=""):
        super().__init__(browser, objectName="acctpane")
        self.browser = browser
        self.page = page
        self.host = host
        self.scheme = scheme
        self.names = list(names)
        self.answered = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # the page can go while the panel is up — a tab closed behind
        # it, a virtual browser torn down. Filling a dead page is at
        # best pointless, so the panel goes with it.
        try:
            page.destroyed.connect(self._page_gone)
        except (AttributeError, TypeError):
            pass

        self.panel = QWidget(self, objectName="acctpanel")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(10)
        title = QLabel(browser._ui_str("acctPickTitle"), objectName="accthead")
        title.setWordWrap(True)
        col.addWidget(title)
        body = QLabel(body_text or browser._ui_str("acctPickBody")
                      .format(host), objectName="acctbody")
        body.setWordWrap(True)
        col.addWidget(body)

        rows_in = QWidget()
        rows = QVBoxLayout(rows_in)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        self.buttons = []
        blank = QPixmap(1, 1)
        blank.fill(Qt.GlobalColor.transparent)
        for name in self.names:
            btn = QToolButton(
                text=(name or browser._ui_str("acctPickNoName")),
                objectName="acctitem")
            btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding,
                              QSizePolicy.Policy.Fixed)
            # An address centred in a wide button is hard to run an eye
            # down. QToolButton ignores text-align on its own; give it an
            # icon it will never draw and it lays the text out beside it,
            # from the left, which is where a list of names belongs.
            btn.setIcon(QIcon(blank))
            btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setToolTip(name)
            btn.clicked.connect(
                lambda _=False, chosen=name: self._choose(chosen))
            rows.addWidget(btn)
            self.buttons.append(btn)
        rows.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(rows_in)
        col.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch()
        cancel = QToolButton(text=browser._ui_str("acctPickCancel"),
                             objectName="acctcancel")
        cancel.clicked.connect(self.cancel)
        foot.addWidget(cancel)
        col.addLayout(foot)

        # the panel takes the keyboard when it comes up, so Esc and Tab
        # are its own; see event() below for why that matters
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def event(self, e):
        """Esc is taken here rather than with a QShortcut, and that is
        not a style choice.

        The window already has an Esc shortcut — Browser._pane_esc, on
        WindowShortcut, the one a pane is closed with. Two shortcuts
        matching one key is not a race the newer one wins: Qt calls it
        ambiguous and runs *neither* handler. With a pane up and this
        panel over it, Esc became a permanent no-op — the exact thing
        _pane_esc exists to promise, that if focus ends up somewhere
        unexpected Esc still gets him out.

        ShortcutOverride is the mechanism meant for this. The focus
        widget is offered the key before any shortcut is matched, and
        accepting it means "this one is mine, do not run the shortcut".
        It is offered up the parent chain as well, so it still works
        when he has tabbed onto one of the account buttons. Nothing is
        registered, so nothing can be ambiguous with anything, and the
        moment this panel goes Esc belongs to the pane again, exactly
        as it does with no chooser in the browser at all.

        keyPressEvent alone is not enough and this is not belt and
        braces. Shortcuts are matched before the key is delivered to
        anybody, so without the override _pane_esc simply wins: the
        pane closes and the panel he was actually looking at stays
        where it is. Measured, all four ways round — with the old
        shortcut Esc is ambiguous and closes nothing; with the
        shortcut and a focus policy it is still ambiguous; with
        keyPressEvent and no override the wrong one closes; only this
        pair does the right thing. tests/test_acctpick.py (j) fails on
        each of the other three."""
        if (e.type() == QEvent.Type.ShortcutOverride
                and not self.answered
                and e.key() == Qt.Key.Key_Escape):
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(e)

    def place(self):
        """Centred on the window, never wider or taller than it."""
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        width = max(240, min(460, self.width() - 48))
        self.panel.setFixedWidth(width)
        wanted = self.panel.sizeHint().height()
        height = max(140, min(wanted, self.height() - 48))
        self.panel.resize(width, height)
        self.panel.move((self.width() - width) // 2,
                        (self.height() - height) // 2)

    def _page_gone(self, *_):
        self.page = None
        self.cancel()

    def _choose(self, name):
        if self.answered:
            return
        self.answered = True
        page, self.page = self.page, None
        self._done()
        if page is not None:
            self.browser._account_chosen(page, self.host, self.scheme, name)

    def cancel(self):
        """No account chosen, so nothing is filled — not the one the
        browser would have guessed either. Dismissing is an answer."""
        self.answered = True
        self._done()

    def _done(self):
        self.hide()
        self.browser._close_account_chooser(self)

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.pos()):
            self.cancel()


class Browser(QMainWindow):
    def __init__(self, initial_url=None):
        super().__init__()
        self._initial_url = initial_url
        self.setWindowTitle("browser")
        self.resize(1280, 820)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme_style())

        try:
            self.config = json.loads(CONFIG_FILE.read_text())
        except Exception:
            self.config = {}
        # host-only permission keys predate both ports and local files
        stale = self.config.get("permissionsKeyVersion", 1) < 2
        _migrate_permission_config(self.config)
        # before the first cookie jar, because every jar carries the
        # script that paints our own pages in this theme
        _select_theme(self.config.get("theme", DEFAULT_THEME))
        # what the browser was launched as: a light theme picked now
        # cannot reach the websites until the next start (see
        # _install_theme_flags), and Settings says so when they differ
        self._launched_dark = theme_is_dark()
        # Vault Password is opt-in, but only for someone who is being
        # asked. Settled once, here, before anything reads it — after
        # this the key is always present and every later read is a
        # plain lookup (see _vault_password_default).
        if VAULT_PASSWORD_KEY not in self.config:
            self.config[VAULT_PASSWORD_KEY] = _vault_password_default(
                self.config, CONFIG_FILE.parent)
        try:
            self.history = json.loads(HISTORY_FILE.read_text())
        except Exception:
            self.history = []
        # saved logins. Which store they live in is an explicit
        # setting, never a guess — and if the chosen one cannot be
        # reached the browser says so and uses the built-in file vault
        # rather than starting up broken (see make_vault).
        self.vault_fell_back = ""
        self.vault_checking = ""
        self._vault_jobs = set()
        # The master password, if there is one. It is made before the
        # vault because the vault is built on it: every FileVaultProvider
        # this window ever makes shares this one lock, so unlocking is
        # something that happens once and not once per provider.
        self.vault_lock = VaultLock(CONFIG_FILE.parent)
        self._master_asking = False   # one box, however many pages ask
        #: bumped every time the vault is locked. Work that was already
        #: in flight is stale from that moment on — see vault_job.
        self._vault_epoch = 0
        self.vault = self.make_vault()
        # Auto-lock. Looked at twice a minute rather than armed for an
        # exact moment: a timer set for twenty past two does not go off
        # at all if the machine was asleep at twenty past two, and a
        # vault that quietly stays open because the laptop was shut is
        # the one case this feature exists for.
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30000)
        self._lock_timer.timeout.connect(self._master_tick)
        self._lock_timer.start()
        self.downloads = load_downloads()
        self.bookmarks = load_bookmarks()
        self.dl_active = {}  # id -> running QWebEngineDownloadRequest
        self._dl_seq = max((e["id"] for e in self.downloads), default=0) + 1
        # only pages the browser opened itself carry this run's key, so a
        # website talking raw QWebChannel can't drive the download slots
        self._page_key = uuid.uuid4().hex
        self.bridge = Bridge(self)
        # the pushes that tell a page of ours its data moved. A pane
        # that skipped a load because nothing had changed is only
        # right if every change comes past here (see _page_data_changed)
        for _changed in (self.bridge.downloadsChanged,
                         self.bridge.bookmarksChanged,
                         self.bridge.vaultChanged,
                         self.bridge.toolbarChanged,
                         self.bridge.updateFinished):
            _changed.connect(_page_data_changed)

        # userscript plugins: *.user.js files next to the config
        # (Greasemonkey-style; Qt WebEngine can't run real extensions)
        self.plugins_dir = CONFIG_FILE.parent / "plugins"
        self.plugin_scripts = self._load_plugins()
        self.plugin_script_names = [s.name() for s in self.plugin_scripts]

        # a cookie wipe asked for at shutdown may not outlive the
        # shutdown, so the request is written down and honoured here.
        # "runOpen" is the other half: it is set for as long as a run is
        # in progress and cleared on the way out, so finding it still
        # set means the last run was killed rather than closed - and a
        # wipe it never got to do is done now instead.
        pending = bool(self.config.pop("cookiesWipePending", False))
        crashed = bool(self.config.pop("runOpen", False))
        self._wipe_cookies_at_start = pending or (
            crashed and bool(self.config.get("clearCookiesExit")))
        if crashed and self.config.get("clearHistoryExit"):
            self.history = []
            self.save_history()
        self._exit_cleared = False
        self.config["runOpen"] = True
        self.save_config()
        self.profile = self._make_profile("browser")
        self._perm_queue = []
        self._perm_widget = None
        self._session_perms = {}
        # names minted for files that keep no row: a private download,
        # and a private page printed to PDF. self.downloads speaks for
        # every other in-flight name, and cannot speak for these.
        self._dl_held = set()
        # what a private tab was allowed, kept apart from the rest and
        # thrown away with the last private tab
        self._private_perms = {}
        self._share_picker = None
        # the account chooser on screen, and the pages it has already
        # offered itself to unasked (page id -> host), so a login form
        # that redraws itself forty times does not throw up forty panels
        self._acct_chooser = None
        self._acct_auto = {}
        if stale:  # write the converted keys back, so this runs once
            self.save_config()

        # top island bar: nav buttons + url bar. Which buttons, and in
        # what order, is his - see TOOLBAR_ITEMS and rebuild_toolbar.
        self._tb_buttons = {}
        self.urlbar = QLineEdit(objectName="urlbar")
        self.urlbar.setPlaceholderText("Search or enter address")
        self.urlbar.returnPressed.connect(self._navigate)

        # the star lives inside the address bar, like Chrome's: the bar
        # keeps a right margin free for it and it rides along on resize
        self.starbtn = QToolButton(self.urlbar, text="\u2606",
                                   objectName="starbtn")
        self.starbtn.setFixedSize(24, 22)
        self.starbtn.setCursor(Qt.CursorShape.ArrowCursor)
        self.starbtn.clicked.connect(self.toggle_bookmark)
        self._tb_buttons["star"] = self.starbtn

        # and the account chooser's handle lives at the other end of it.
        # It is only ever there when this page really has more than one
        # saved login, so the bar looks exactly as it always did on the
        # sites where there is nothing to choose between. The tooltip is
        # written later, in _sync_acct: self.config is not read yet.
        self.acctbtn = QToolButton(self.urlbar, text="@",
                                   objectName="acctbtn")
        self.acctbtn.setFixedSize(20, 22)
        self.acctbtn.setCursor(Qt.CursorShape.ArrowCursor)
        self.acctbtn.clicked.connect(self.open_account_chooser)
        self.acctbtn.hide()
        self.urlbar.setTextMargins(0, 0, 28, 0)
        self.urlbar.installEventFilter(self)

        # suggestions dropdown: domain guesses + Google search suggestions
        try:
            self.known_hosts = set(json.loads(HOSTS_FILE.read_text()))
        except Exception:
            self.known_hosts = set()
        self.suggest_model = QStringListModel(self)
        self.completer = QCompleter(self.suggest_model, self)
        self.completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.urlbar.setCompleter(self.completer)
        self.completer.activated.connect(
            lambda _: QTimer.singleShot(0, self._navigate))
        self.completer.popup().setStyleSheet(tint(COMPLETER_QSS))
        self._nam = QNetworkAccessManager(self)
        self._suggest_reply = None
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(150)
        self._suggest_timer.timeout.connect(self._fetch_suggestions)
        self.urlbar.textEdited.connect(lambda _t: self._suggest_timer.start())

        # says "private" right next to the address bar whenever the
        # tab in front is one; the tab strip says it too, but the
        # window must never depend on him remembering which tab he
        # is in. Not a toolbar button: it is not his to switch off,
        # so it is not in the registry - rebuild_toolbar puts it in
        # front of the address bar wherever that has ended up.
        self.privlbl = QLabel(objectName="privatebadge")
        self.privlbl.setStyleSheet(tint(
            "QLabel#privatebadge { background: #16161d; color: #ffffff;"
            " border: 1px solid rgba(108, 112, 134, 110);"
            " padding: 4px 10px; font-weight: bold; }"))
        self.privlbl.hide()

        # The buttons are all built here; which of them end up on the
        # bar, and in what order, is rebuild_toolbar's job. The row is
        # a widget rather than a bare layout so a right-click anywhere
        # on it has something to land on.
        self.navbar = QWidget(objectName="navbar")
        bar = QHBoxLayout(self.navbar)
        bar.setContentsMargins(10, 8, 10, 2)
        bar.setSpacing(6)
        self._navlay = bar
        self.navbar.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.navbar.customContextMenuRequested.connect(self._toolbar_menu)
        self._make_toolbar_buttons()

        self.tabs = TabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.tabBar().tabMoved.connect(self._tab_moved)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.currentChanged.connect(self._tab_changed)

        # Chrome-style tab groups: a colored name label sits in the tab
        # strip before its tabs; clicking it collapses/expands the group
        self.groups = []
        self.group_colors = {}
        self.collapsed = {}
        self.group_ids = {}
        self.group_profiles = {}
        self.group_sessions = {}
        # the last few closed tabs, oldest first (Ctrl+Shift+T)
        self._closed_tabs = []
        self.sessions = [{"name": "Browser 1", "sid": "main"}]
        self.active_session = "main"
        self.session_profiles = {}
        self._book = QToolButton(text="📑", objectName="groupbtn")
        self._book.clicked.connect(self._group_menu)
        self._tb_buttons["tabgroups"] = self._book
        self.tabs.setCornerWidget(self._book, Qt.Corner.TopLeftCorner)
        # the + rides along right after the last tab, like Chrome
        self._newtab_btn = QToolButton(self.tabs.tabBar(), text="+",
                                       objectName="newtabbtn")
        self._newtab_btn.setToolTip("New tab")
        self._newtab_btn.setFixedSize(28, 26)
        self._newtab_btn.clicked.connect(lambda: self.new_tab())
        self._newtab_btn.show()
        self.tabs.tabBar().installEventFilter(self)

        self.chrome = QWidget(objectName="chrome")
        lay = QVBoxLayout(self.chrome)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        # virtual browsers: each entry up here is a full browser with
        # its own cookies and its own tabs
        self.sessrow = QWidget(objectName="sessrow")
        self.sesslay = QHBoxLayout(self.sessrow)
        self.sesslay.setContentsMargins(8, 4, 8, 0)
        self.sesslay.setSpacing(6)
        lay.addWidget(self.sessrow)
        lay.addWidget(self.navbar)

        self.rebuild_toolbar()

        # bookmarks bar: a strip under the address bar, toggled with
        # Ctrl+Shift+B and remembered in the config
        self.bmbar = BookmarksBar(self)
        self.bmbar.hide()  # rebuild_bookmarks_bar decides, once loaded
        lay.addWidget(self.bmbar)

        # download bar (hidden until a download starts)
        self.dlbar = QWidget(objectName="dlbar")
        self.dllay = QHBoxLayout(self.dlbar)
        self.dllay.setContentsMargins(10, 8, 10, 8)
        self.dllay.setSpacing(8)
        self._dlall = QToolButton(text="\u2913", objectName="dlall")
        self._dlall.setToolTip("All downloads")
        self._dlall.clicked.connect(self.open_downloads)
        self.dllay.addWidget(self._dlall)
        self.dllay.addStretch()  # toasts land between button and stretch
        self.dlbar.hide()

        root = QWidget()
        rlay = QVBoxLayout(root)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(self.chrome)
        rlay.addWidget(self.tabs, 1)
        rlay.addWidget(self.dlbar)
        self.setCentralWidget(root)

        # A pane covers the window, chrome included. A shortcut that
        # opens a tab, closes one or jumps to the address bar would
        # otherwise do its work behind a screen he cannot see past, and
        # the browser would look like it ignored him. These close
        # whatever pane is up first and then act, so he sees what
        # happened. The pane shortcuts themselves are in the second
        # group below: they toggle instead.
        def out_of_pane(fn):
            def run():
                self.close_pane()
                fn()
            return run

        for key, fn in {
            "Ctrl+T": self.new_tab,
            "Ctrl+W": lambda: self.close_tab(self.tabs.currentIndex()),
            "Ctrl+L": self._focus_url,
            "Ctrl+R": lambda: self.current().reload(),
            "F5": lambda: self.current().reload(),
            "Ctrl+Tab": lambda: self._cycle(1),
            "Ctrl+Shift+Tab": lambda: self._cycle(-1),
            "Shift+Tab": lambda: self._cycle_session(1),
            "Ctrl+D": self.toggle_bookmark,
            "Ctrl+Shift+B": self.toggle_bookmarks_bar,
            "Ctrl+Shift+G": self.generate_to_clipboard,
            "F12": self.toggle_inspector,
            "Ctrl+Shift+I": self.toggle_inspector,
            "Ctrl+F": self.open_find,
            "Ctrl+P": self.print_page,
            "Ctrl+Shift+T": self.reopen_closed_tab,
            "Ctrl+Shift+A": self.open_tab_switcher,
            "Ctrl+Shift+M": self.open_account_chooser,
            "Ctrl+Shift+N": self.new_private_tab,
            "Ctrl+Shift+V": self.play_externally,
            "Alt+Home": self.go_home,
        }.items():
            QShortcut(QKeySequence(key), self).activated.connect(
                out_of_pane(fn))
        for key, fn in {
            "Ctrl+Q": self.close,
            "F11": lambda: self.set_fullscreen(not self.isFullScreen()),
            "Ctrl+,": self.toggle_settings,
            "Ctrl+H": self.toggle_history,
            "Ctrl+J": self.toggle_downloads,
            "Ctrl+Shift+O": self.toggle_bookmarks,
            "Ctrl+Shift+F": self.toggle_favorites,
            "Ctrl+Shift+P": self.toggle_passwords,
            # zoom deliberately stays out of the settings-closing list:
            # zooming the page behind a screen he cannot see past would
            # look like the browser had ignored him
            "Ctrl+=": lambda: self.zoom_by(1),
            "Ctrl++": lambda: self.zoom_by(1),
            "Ctrl+Shift+=": lambda: self.zoom_by(1),
            "Ctrl+-": lambda: self.zoom_by(-1),
            "Ctrl+_": lambda: self.zoom_by(-1),
            "Ctrl+0": self.zoom_reset,
            "Ctrl+Shift+L": self.toggle_vault_lock,
        }.items():
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        self.bridge.updateFinished.connect(self._toast_result)
        QTimer.singleShot(3000, self._check_updates)
        self._toast = None
        self._pw_pending = None
        # half-finished logins: (profile, host) -> the account whose
        # password step is still to come. See _pw_step_remember.
        self._pw_steps = {}
        # the browser's own pages live in panes over the current tab,
        # never in tabs of their own: name -> PagePane, each built on
        # first use and reused after. self._pane is the one on screen.
        self._panes = {}
        self._pane = None
        # One Esc for every pane, switched on only while one is up, so
        # Esc keeps meaning whatever it means to the page in the tab
        # underneath the rest of the time — and so that two panes can
        # never both answer it. Window-wide rather than bound to the
        # pane because a pane hides everything: if focus ever ends up
        # somewhere unexpected, Esc must still get him out.
        #
        # A window shortcut is matched before the key can reach the web
        # view, so the page cannot hold Esc back by itself, however it
        # is written. It does not act on its own either: see
        # _pane_escape, which asks the page first.
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.setContext(Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self._pane_escape)
        esc.setEnabled(False)
        self._pane_esc = esc
        self._esc_turn = 0      # which Esc an answer belongs to
        self._esc_timer = None  # the fallback that closes on silence
        self._findbar = None  # built on first Ctrl+F, reused after
        self._switcher = None  # built on first Ctrl+Shift+A, reused after

        # virtual browsers and groups survive restarts
        QApplication.instance().aboutToQuit.connect(self._save_groups)
        # every way out, not just the window's close button: quit from
        # the menu, a restart after an update, a Ctrl+Q
        QApplication.instance().aboutToQuit.connect(self._clear_on_exit)
        saved_sessions = [e for e in self.config.get("sessions", [])
                          if e.get("sid") and e.get("name")]
        if saved_sessions:
            self.sessions = saved_sessions
            if not any(e["sid"] == "main" for e in self.sessions):
                self.sessions.insert(0, {"name": "Browser 1", "sid": "main"})
        self.apply_proxy()
        self.active_session = self.sessions[0]["sid"]
        if self.config.get("restoreTabs", True):
            self._restore_groups()
            self._restore_session_tabs()
        # the page he set for launch opens in the first tab - but only
        # when there was nothing to come back to. Tabs from last time
        # are where he actually left off and they win over a page he
        # set once; an address on the command line wins over both.
        came_back = any(not self._is_header(self.tabs.widget(i))
                        for i in range(self.tabs.count()))
        self.new_tab(url=initial_url, group=None,
                     session=self.active_session, at_end=True,
                     home=None if came_back else self.start_target())
        self.switch_session(self.active_session)
        self.rebuild_bookmarks_bar()

    def _restore_url(self, saved):
        """What a saved tab URL turns into on the way back in. None
        means the tab is not restored at all: a page that is a pane now
        stays closed, however an older version saved it (see
        _is_pane_url). An empty string keeps its old meaning of "a
        fresh start page"."""
        u = str(saved or "")
        if not u:
            return u
        if _is_pane_url(u):
            return None
        return u

    def _restore_session_tabs(self):
        valid = {e["sid"] for e in self.sessions}
        for sid, items in (self.config.get("sessionTabs") or {}).items():
            if sid not in valid:
                continue
            for item in items:
                if isinstance(item, dict):
                    u, t = item.get("u", ""), item.get("t") or None
                else:
                    u, t = item, None
                u = self._restore_url(u)
                if u:
                    self.new_tab(url=u, group=None, session=sid,
                                 switch=False, lazy=True, title=t,
                                 at_end=True)

    def _save_groups(self):
        data = []
        for g in self.groups:
            urls = []
            for i in self._group_indices(g):
                view = self.tabs.widget(i)
                if getattr(view, "private", False):
                    continue     # cannot happen; costs nothing to say
                url = view.url()
                if _same_page(url, START_PAGE) or self._is_blank_tab(view):
                    urls.append({"u": "", "t": ""})
                    continue
                u = (url.toString() or getattr(view, "_pending", "")
                     or getattr(view, "_requested", ""))
                if _is_pane_url(u):
                    continue  # a pane now: never saved as a tab again
                urls.append({"u": u, "t": self.tabs.tabText(i)})
            data.append({"name": g,
                         "color": self.group_colors.get(g, "#6c7086"),
                         "collapsed": bool(self.collapsed.get(g)),
                         "gid": self.group_ids.get(g),
                         "session": self.group_sessions.get(g, "main"),
                         "urls": urls})
        self.config["tabGroups"] = data
        # loose tabs are saved per virtual browser too (start pages
        # excluded — every start spawns a fresh one anyway)
        session_tabs = {}
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if self._is_header(view) or self._group_of(view) is not None:
                continue
            if getattr(view, "private", False):
                # never written into the session, so never restored at
                # the next start: a private tab ends when it is closed
                continue
            url = view.url()
            # a start page, or a tab opened on a page of his own and
            # never taken anywhere: every start makes a fresh one, so
            # saving it would mean one more tab at every launch
            if _same_page(url, START_PAGE) or self._is_blank_tab(view):
                continue
            u = (url.toString() or getattr(view, "_pending", "")
                 or getattr(view, "_requested", ""))
            if not u or _is_pane_url(u):
                continue
            sid = getattr(view, "session", "main")
            session_tabs.setdefault(sid, []).append(
                {"u": u, "t": self.tabs.tabText(i)})
        self.config["sessionTabs"] = session_tabs
        self.config["sessions"] = self.sessions
        self.save_config()

    def _restore_groups(self):
        for entry in self.config.get("tabGroups", []):
            name = entry.get("name")
            # sorted out before the group exists, so a group left with
            # nothing to restore never gets an empty pill in the strip
            members = []
            for item in entry.get("urls", []):
                if isinstance(item, dict):
                    u, t = item.get("u", ""), item.get("t") or None
                else:
                    u, t = item, None
                u = self._restore_url(u)
                if u is None:
                    continue
                members.append((u, t))
            if not name or name in self.groups or not members:
                continue
            if entry.get("gid"):
                self.group_ids[name] = entry["gid"]
            session = entry.get("session", "main")
            if not any(e["sid"] == session for e in self.sessions):
                session = "main"
            self._register_group(name, entry.get("color", "#6c7086"),
                                 session=session)
            for u, t in members:
                self.new_tab(url=u or None, group=name, switch=False,
                             lazy=bool(u), title=t, at_end=True)
            if entry.get("collapsed"):
                self._toggle_collapse(name)

    # ---- updates ----
    def _check_updates(self):
        """Quietly look for a newer version on GitHub at startup."""
        if not (APP_DIR / ".git").exists():
            return
        fetch = QProcess(self)
        fetch.setWorkingDirectory(str(APP_DIR))

        def fetched(*_):
            try:
                fetch.deleteLater()
            except RuntimeError:
                return  # quitting while the check was in flight
            self._count_behind()
        fetch.finished.connect(fetched)
        fetch.start("git", ["fetch", "--quiet"])

    def _count_behind(self):
        proc = QProcess(self)
        proc.setWorkingDirectory(str(APP_DIR))

        def done(*_):
            try:
                out = bytes(proc.readAllStandardOutput()).decode().strip()
                code = proc.exitCode()
                proc.deleteLater()
            except RuntimeError:
                return  # quitting while the check was in flight
            if code == 0 and out.isdigit() and int(out) > 0:
                self._show_toast()
        proc.finished.connect(done)
        proc.start("git", ["rev-list", "--count", "HEAD..@{u}"])

    def _show_toast(self):
        if self._toast:
            return
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self._toast_label = QLabel("Update available")
        update = QToolButton(text="Update now")
        close = QToolButton(text="\u2715", objectName="tabclose")
        lay.addWidget(self._toast_label)
        lay.addWidget(update)
        lay.addWidget(close)

        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(5000)
        self._toast_timer.timeout.connect(self._hide_toast)

        close.clicked.connect(self._hide_toast)
        update.clicked.connect(lambda: (
            self._toast_timer.stop(),
            update.hide(),
            self._toast_label.setText("Updating\u2026"),
            self.bridge.runUpdate(),
        ))

        self._place_toast()
        toast.show()
        toast.raise_()
        self._toast_timer.start()

    def _place_toast(self):
        if self._toast:
            self._toast.adjustSize()
            self._toast.move(self.width() - self._toast.width() - 16, 54)

    def _hide_toast(self):
        if self._toast:
            self._toast_timer.stop()
            self._toast.deleteLater()
            self._toast = None

    def _toast_result(self, msg):
        if not self._toast:
            return
        self._toast_label.setText(msg)
        if msg.startswith("Updated"):
            restart = QToolButton(text="Restart now")
            restart.clicked.connect(self.restart)
            self._toast.layout().insertWidget(1, restart)
            self._toast_timer.stop()  # stays until acted on or dismissed
        else:
            self._toast_timer.setInterval(8000)
            self._toast_timer.start()
        self._place_toast()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_toast()
        self._place_perm()
        self._place_share()
        self._place_account_chooser()
        self._place_favorites()
        self._place_zoom_badge()

    # ---- tabs ----
    def current(self):
        return self.tabs.currentWidget()

    def new_tab(self, url=None, switch=True, blank=False,
                group=INHERIT_GROUP, session=None, lazy=False, title=None,
                at_end=False, home=None, private=False):
        # home: the page an empty tab opens on, when it is not the one a
        # new tab normally shows - the launch tab uses it for the
        # start-up page. Ignored when url says where to go.
        # at_end: this tab is being put back, not opened. "Right after
        # this tab" is about where a tab you just opened should land;
        # applied to a restore it would stack every saved tab on top of
        # the one before it and hand back a reversed strip.
        if private:
            # a group carries a virtual browser's cookie jar with it,
            # and this tab's jar is not one of those: it joins none
            group = None
        if group is INHERIT_GROUP:
            group = self._group_of(self.current())
        if session is None:
            session = (self.group_sessions.get(group)
                       if group is not None else self.active_session)
        view = WebView(self, self._profile_for(group, session, private))
        view.private = private
        self._apply_zoom(view)
        view.group = group
        view.session = session or "main"
        view.urlChanged.connect(lambda u, v=view: self._url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: self._title_changed(v, t))
        view.iconChanged.connect(lambda ic, v=view: self._icon_changed(v, ic))
        view.loadFinished.connect(lambda ok, v=view: self._autofill(v, ok))
        view.printRequested.connect(lambda v=view: self._print_requested(v))
        after = (not at_end
                 and self.config.get("newTabPos", "end") == "after")
        cur = self.tabs.currentIndex()
        held = self.tabs.widget(cur) if cur >= 0 else None
        if group is not None:
            if self.collapsed.get(group):
                self._toggle_collapse(group)
            block = [self._header_index(group)] + self._group_indices(group)
            at = max(block) + 1
            # "right after the current tab" only ever lands inside the
            # group's own block, so a group is never split in two
            if after and cur in self._group_indices(group):
                at = cur + 1
            i = self.tabs.insertTab(at, view, "New tab")
        elif (after and held is not None and not self._is_header(held)
                and getattr(held, "group", None) is None
                # and in this virtual browser: "right after this tab"
                # must never drop a tab into another browser's block
                and getattr(held, "session", "main") == view.session):
            i = self.tabs.insertTab(cur + 1, view, "New tab")
        else:
            i = self.tabs.addTab(view, "New tab")

        self._add_close_button(i, view)
        if private:
            self.tabs.setTabIcon(i, self._private_icon())
            self.tabs.setTabToolTip(i, self._ui_str("privateTip"))

        if switch:
            self.tabs.setCurrentIndex(i)
        if not blank:
            if url is None:
                target = home if home is not None else self.new_tab_target()
                # a tab he opened and never took anywhere stays
                # anonymous whatever it happens to show: session saving
                # skips those. Without this every empty tab opened on a
                # page of his own came back as a real tab at the next
                # start, and the strip grew every single run.
                view._blank_home = target.toString()
                if not _same_page(target, START_PAGE):
                    view._requested = target.toString()
                # the start page is one of ours: say so before asking
                # for it, so the navigation is not bounced and re-issued
                view.page().prime_trust(target)
                view.load(target)
                self._focus_url()
            elif lazy:
                # the page loads only when the tab is first opened,
                # so restored sessions cost no memory until used
                view._pending = url
                view._requested = url
            else:
                view._requested = url  # fallback for saving before commit
                view.page().prime_trust(QUrl(url))
                view.load(QUrl(url))
        if title:
            self.tabs.setTabText(i, title)
        elif lazy and url:
            self.tabs.setTabText(i, QUrl(url).host() or "Tab")
        self._update_private_marks()
        return view

    def new_private_tab(self):
        """Ctrl+Shift+N. A tab that leaves nothing behind: no history,
        no cookies or storage once the last one closes, no saved
        password, no download record and no favicon kept. Not a cleanup
        routine - a cookie jar with nowhere to write, which is a far
        better promise than one that tries to tidy up after itself."""
        return self.new_tab(group=None, private=True)

    def _private_icon(self):
        """The mark a private tab wears in the strip. Drawn here rather
        than shipped as a file or a glyph, so it cannot go missing with
        a font, and it follows the theme."""
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme_color("bright")))
        p.drawEllipse(2, 3, 12, 11)
        p.setBrush(QColor(theme_color("bg")))
        p.drawRect(3, 6, 10, 3)
        p.end()
        return QIcon(pix)

    def private_tabs(self):
        """Every private tab open right now."""
        out = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if getattr(w, "private", False):
                out.append(w)
        return out

    def _update_private_marks(self):
        """What says "this is private": the badge beside the address bar
        for the tab in front, and the window's own name for as long as
        any private tab is open at all.

        Two marks, and neither may depend on the other. The badge is a
        widget that does not exist yet while the chrome is being built,
        and is taken off the row and put back every time the toolbar is
        rebuilt; the window title is a property of the window and is
        always there. Ask about them separately, or a missing badge
        takes the title down with it."""
        if getattr(self, "tabs", None) is None:
            return
        private = bool(self.private_tabs())
        self.setWindowTitle("browser \u2014 " + self._ui_str("privateTab")
                            if private else "browser")
        lbl = getattr(self, "privlbl", None)
        if lbl is None:
            return                     # still being built
        lbl.setText(self._ui_str("privateTab"))
        lbl.setVisible(bool(getattr(self.current(), "private", False)))

    # ---- page zoom ----
    @staticmethod
    def _is_web(url):
        return url.scheme() in ("http", "https")

    def zoom_default(self):
        """The level the Page zoom slider in Settings is set to. One
        number for the whole browser, which is what it has always
        meant."""
        try:
            factor = float(self.config.get("zoom", 1.0) or 1.0)
        except (TypeError, ValueError):
            return 1.0
        return min(max(factor, ZOOM_STEPS[0]), ZOOM_STEPS[-1])

    def _apply_zoom(self, view, adopt=True):
        """Put one page at the level it belongs at.

        A level a tab was given by hand is a level for a website: the
        browser's own pages - start, settings, history, downloads,
        bookmarks, passwords, and the panes those last ones open in -
        are not websites and are never zoomed one at a time. They sit
        where the Page zoom slider says, and move when it moves, which
        is the one number they have always answered to. Left to a
        per-tab level they would take a comic strip's 500% with them
        and Settings would be three buttons and no way to reach the
        rest.

        Ctrl and the wheel is the engine's own doing - it climbs this
        very ladder, in Chromium, where the wheel actually arrives -
        and it tells nobody. So before a level is put back on a page,
        a level the engine set behind our back is taken as this tab's
        own: otherwise the first link he followed would throw away the
        size he had just wheeled the article up to. adopt=False is the
        keyboard, which has already decided what it wants."""
        if view is None or not hasattr(view, "setZoomFactor"):
            return
        try:
            url = view.url()
        except RuntimeError:
            return
        if adopt and self._is_web(url):
            here = self.zoom_now(view)
            last = getattr(view, "_zoom_set", None)
            if last is not None and abs(here - last) > 1e-3:
                view._zoom = here
        want = getattr(view, "_zoom", None)
        if want is None or not self._is_web(url):
            want = self.zoom_default()
        # what we asked for, so a level that turns up later and is not
        # this one can only have come from the engine
        view._zoom_set = want
        if abs(self.zoom_now(view) - want) < 1e-6:
            return
        # ...and the engine is only spoken to when there is something to
        # say. This runs at every navigation, which is the engine in the
        # middle of committing one, and reaching back into it there to
        # set the size it already has is asking for trouble for nothing.
        view.setZoomFactor(want)

    def _zoom_target(self):
        """The tab a zoom shortcut acts on, or None.

        Not while any pane is up - settings, history, downloads,
        bookmarks or the password manager. A pane covers the page that
        would change, so nothing he could see would move, and the tab
        he cannot see would silently be somewhere else when he came
        back to it. (This asked about the settings pane alone, from
        when that was the only one there was.)"""
        view = self.current()
        if view is None or not hasattr(view, "setZoomFactor"):
            return None
        if self.pane_open() or not self._is_web(view.url()):
            return None
        return view

    def zoom_now(self, view):
        """Where a page actually sits, asked of the page.

        Ctrl and the wheel is the engine's own, and it does not say so
        - so the level is read off the page rather than off the last
        thing this file asked for. See _apply_zoom."""
        try:
            return float(view.zoomFactor())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return self.zoom_default()

    def zoom_by(self, direction):
        """Ctrl+= / Ctrl+-: one rung up or down, for this tab. Zoom
        belongs to the page being read - a comic strip at 200% must not
        blow up the mail tab beside it - and Ctrl+0 needs somewhere to
        go back to, which is the level Settings holds."""
        view = self._zoom_target()
        if view is None:
            return
        # from where the page is, not from where this file last put it:
        # Ctrl+= after a Ctrl+wheel carries on up the same ladder
        now = self.zoom_now(view)
        if direction > 0:
            want = next((z for z in ZOOM_STEPS if z > now + 1e-6),
                        ZOOM_STEPS[-1])
        else:
            want = next((z for z in reversed(ZOOM_STEPS) if z < now - 1e-6),
                        ZOOM_STEPS[0])
        view._zoom = want
        self._apply_zoom(view, adopt=False)
        self._show_zoom(view)

    def zoom_reset(self):
        """Ctrl+0: back to the level the Page zoom slider is set to."""
        view = self._zoom_target()
        if view is None:
            return
        view._zoom = None
        self._apply_zoom(view, adopt=False)
        self._show_zoom(view)

    def _show_zoom(self, view):
        """Says where he is for a moment, low and out of the way. One
        label, made once and shown again after that: the toast in the
        top right is for things he has to answer, and this is not one."""
        badge = getattr(self, "_zoom_badge", None)
        if badge is None:
            badge = QLabel(self, objectName="zoombadge")
            badge.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            badge.setStyleSheet(tint(
                "QLabel#zoombadge { background: #0d0d12; color: #cdd6f4;"
                " border: 1px solid rgba(108, 112, 134, 110);"
                " padding: 6px 14px; }"))
            self._zoom_badge = badge
            self._zoom_timer = QTimer(self)
            self._zoom_timer.setSingleShot(True)
            self._zoom_timer.timeout.connect(badge.hide)
        badge.setText("%d%%" % round(view.zoomFactor() * 100))
        badge.adjustSize()
        badge.show()
        self._place_zoom_badge()
        badge.raise_()
        self._zoom_timer.start(1400)

    def _place_zoom_badge(self):
        badge = getattr(self, "_zoom_badge", None)
        if badge is not None and badge.isVisible():
            badge.move(max(0, (self.width() - badge.width()) // 2),
                       max(0, self.height() - badge.height() - 24))

    def _blank_settled(self, view, url):
        """Where a tab he opened blank came to rest, and whether it has
        moved off it since.

        The page a new tab is opened on is the address `new_tab` asked
        for, plus every redirect off that address on the way in:
        youtube.com arrives as www.youtube.com, and a page of his own
        may bounce through a consent hop or refresh itself into place.
        None of that is him going anywhere. Everything else is - an
        address typed into the bar, a link followed, a form sent, and
        the moves that load no document at all, which is how a hash
        router or history.pushState travels. A webmail he set as his
        new-tab page routes that way, and the tab has to come back with
        the message he had open in it.

        Which one it was is read off the navigation the page started,
        not off "whatever committed first". That distinction is the
        whole bug: open a tab and type an address into it, and the
        typed load overtakes the new-tab page before it ever commits.
        The tab was then recorded as resting on the address he had just
        chosen, stayed anonymous for the rest of its life, and was
        dropped from the session without a word."""
        home = getattr(view, "_blank_home", "")
        if not home:
            return
        here = url.toString()
        if not here:
            return                     # mid-bounce: nothing has committed
        if here == getattr(view, "_blank_at", ""):
            return                     # a reload, or it never moved
        serial = getattr(view, "_nav_serial", 0)
        if (getattr(view, "_nav_arrival", False)
                and serial != getattr(view, "_blank_serial", None)):
            view._blank_at = here      # still the page it was opened on
            view._blank_serial = serial
        else:
            # either he asked for this, or the address moved with no
            # navigation behind it at all — a hash router, pushState
            view._blank_home = ""      # his tab now, wherever it ends up

    @staticmethod
    def _is_blank_tab(view):
        """A tab he opened and never navigated. Whatever it shows, it
        shows it because that is what an empty tab shows here, so there
        is nothing of his in it worth saving."""
        return bool(getattr(view, "_blank_home", ""))

    @staticmethod
    def resolve_page_url(text):
        """The address one of the page settings turns into - the
        start-up page or the new-tab page - or "" when it is not one
        the browser could open. "example.com" gets https,
        but "localhost:8080" is a host and a port and would otherwise
        become the nonsense host "localhost:8080" - so it gets http."""
        home = str(text or "").strip()
        if not home:
            return ""
        if "://" not in home:
            head = home.split("/")[0]
            _, _, port = head.partition(":")
            home = ("http://" if port.isdigit() else "https://") + home
        url = QUrl(home)
        if not url.isValid() or not url.host():
            return ""
        if url.scheme() not in ("http", "https", "file"):
            return ""
        return url.toString()

    def new_tab_target(self):
        """What a new tab shows: the start page, or the address he set."""
        home = self.resolve_page_url(self.config.get("newTabUrl"))
        return QUrl(home) if home else QUrl(START_PAGE)

    def start_target(self):
        """What the browser opens on: the start page, or the address he
        set for launch. Nothing to do with what a new tab shows - they
        are two settings, and neither one writes the other."""
        home = self.resolve_page_url(self.config.get("startUrl"))
        return QUrl(home) if home else QUrl(START_PAGE)

    def go_home(self):
        """Alt+Home, and the \u2302 button next to reload: the start
        page, in this tab. Set a page of your own for new tabs and
        there is otherwise no way back to it - it is a local file with
        a name nobody could type, and the address bar holds itself
        empty while it is up."""
        view = self.current()
        if view is None or self._is_header(view):
            self.new_tab(home=QUrl(START_PAGE))
            return
        view._pending = None
        view._requested = ""
        view.load(QUrl(START_PAGE))

    def _add_close_button(self, index, view):
        close = QToolButton(text="✕", objectName="tabclose")
        close.clicked.connect(lambda _, v=view: self.close_tab(self.tabs.indexOf(v)))
        # wrapper centers the circle between the tab text and the tab's right wall
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.addWidget(close)
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, holder)

    def close_tab(self, index):
        w = self.tabs.widget(index)
        if w is None or self._is_header(w):
            return
        private = getattr(w, "private", False)
        # first of all, while the tab is still whole
        self._drop_share(w)
        bar = getattr(self, "_findbar", None)
        if bar is not None:
            bar.forget(w)
        switcher = getattr(self, "_switcher", None)
        if switcher is not None and switcher.isVisible():
            switcher.dismiss()
        self._remember_closed(w, index)
        group = self._group_of(w)
        self.tabs.removeTab(index)
        w.deleteLater()
        # a group whose last tab closes disappears, like in Chrome
        if group is not None and not self._group_indices(group):
            h = self._header_index(group)
            if h is not None:
                hw = self.tabs.widget(h)
                self.tabs.removeTab(h)
                hw.deleteLater()
            self.groups.remove(group)
            self.group_colors.pop(group, None)
            self.collapsed.pop(group, None)
        if private:
            self._drop_private_profile()
        self._update_private_marks()
        self._ensure_tab_or_quit()

    def _remember_closed(self, view, index):
        """What it takes to bring a tab back: where it sat, which virtual
        browser it belonged to and which group it was in. A tab that
        never got a URL (a brand new one) is not worth remembering."""
        if getattr(view, "private", False):
            # Ctrl+Shift+T must not bring it back - not as a private tab
            # he did not ask for, and certainly not as a normal one
            return
        url = (view.url().toString() or getattr(view, "_pending", "")
               or getattr(view, "_requested", ""))
        if not url:
            return
        self._closed_tabs.append({
            "url": url,
            "title": self.tabs.tabText(index),
            "index": index,
            "group": self._group_of(view),
            "session": getattr(view, "session", "main"),
        })
        del self._closed_tabs[:-CLOSED_TABS_MAX]

    def reopen_closed_tab(self):
        """Ctrl+Shift+T: the most recently closed tab, back in its
        virtual browser, its group and its place in the strip."""
        if not self._closed_tabs:
            return None
        saved = self._closed_tabs.pop()
        session = saved.get("session") or "main"
        if not any(e["sid"] == session for e in self.sessions):
            session = self.active_session  # that virtual browser is gone
        if session != self.active_session:
            self.switch_session(session)
        group = saved.get("group")
        # a group deleted in the meantime is not resurrected: the tab
        # comes back ungrouped rather than inventing a group around it
        if group is not None and (group not in self.groups
                                  or self.group_sessions.get(group) != session):
            group = None
        view = self.new_tab(url=saved["url"], group=group, session=session,
                            title=saved.get("title") or None)
        self._restore_tab_index(view, saved.get("index"))
        return view

    def _restore_tab_index(self, view, want):
        """Put a reopened tab back where it sat — but only into a slot
        that is its own kind. A slot now held by a group's pill, by
        another group's tab or by another virtual browser is left alone
        and the tab stays where new_tab put it."""
        if want is None:
            return
        here = self.tabs.indexOf(view)
        if here < 0:
            return
        want = max(0, min(int(want), self.tabs.count() - 1))
        if want == here:
            return
        occupant = self.tabs.widget(want)
        if occupant is None or self._is_header(occupant):
            return
        if (self._group_of(occupant) != self._group_of(view)
                or getattr(occupant, "session", "main")
                != getattr(view, "session", "main")):
            return
        self.tabs.tabBar().moveTab(here, want)

    def _cycle(self, step):
        # skip group headers and collapsed (hidden) tabs
        bar = self.tabs.tabBar()
        n = self.tabs.count()
        i = self.tabs.currentIndex()
        for _ in range(n):
            i = (i + step) % n
            if bar.isTabVisible(i) and not self._is_header(self.tabs.widget(i)):
                self.tabs.setCurrentIndex(i)
                return

    # ---- drag & drop between groups ----
    def _tab_moved(self, _frm, _to):
        """While a tab is dragged, its group follows its position:
        inside a group's block (or onto its pill) joins it, outside
        leaves. Qt reports every displaced tab here, so only the tab
        actually held by the user is ever reassigned."""
        if getattr(self, "_fixing", False):
            return
        w = getattr(self, "_drag_view", None)
        if w is None:
            return
        to = self.tabs.indexOf(w)
        if to < 0:
            return
        left = self.tabs.widget(to - 1) if to > 0 else None
        right = (self.tabs.widget(to + 1)
                 if to + 1 < self.tabs.count() else None)
        if left is None:
            lg = None
        elif self._is_header(left):
            lg = left.group_header
        else:
            lg = getattr(left, "group", None)
        if right is not None and self._is_header(right):
            # dropped onto the pill: merge into that group
            target = right.group_header
        else:
            rg = None if right is None else getattr(right, "group", None)
            target = lg if lg is not None and lg == rg else None
        if target is not None and self.collapsed.get(target):
            target = None  # no dropping into a folded group
        if getattr(w, "private", False):
            target = None  # dragged or not, a private tab joins none
        w.group = target
        self.tabs.tabBar().update()

    def _fix_group_layout(self, group):
        """Ensure the group's tabs sit contiguously after its pill."""
        bar = self.tabs.tabBar()
        for _ in range(self.tabs.count()):
            h = self._header_index(group)
            members = self._group_indices(group)
            if h is None or not members:
                return
            want = set(range(h + 1, h + 1 + len(members)))
            misplaced = [m for m in members if m not in want]
            if not misplaced:
                return
            m = misplaced[0]
            bar.moveTab(m, h + len(members) if m > h else h)

    def _finalize_drag(self):
        held = self.current()  # the tab the user was dragging stays active
        self._fixing = True
        try:
            for g in list(self.groups):
                self._fix_group_layout(g)
        finally:
            self._fixing = False
        for g in list(self.groups):
            self._cleanup_group_if_empty(g)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not self._is_header(w):
                self._sync_profile(w)
        if held is not None:
            i = self.tabs.indexOf(held)
            if i >= 0 and not self._is_header(held):
                self.tabs.setCurrentIndex(i)
        self.tabs.tabBar().update()

    # ---- translation ----
    def _translate_menu(self):
        menu = QMenu(self)
        current = self.config.get("translateLang", "de")

        search = QLineEdit(menu)
        search.setPlaceholderText("Search language\u2026")
        search.setStyleSheet(tint(
            "QLineEdit { background: #000000; color: #cdd6f4;"
            " border: 1px solid rgba(108, 112, 134, 110);"
            " border-radius: 0px; padding: 6px 10px; margin: 2px 4px; }"))
        box = QWidgetAction(menu)
        box.setDefaultWidget(search)
        menu.addAction(box)

        entries = []
        for code, name in LANGUAGES:
            mark = "\u2713 " if code == current else "    "
            action = menu.addAction(mark + name)
            action.triggered.connect(
                lambda _, c=code: self._translate_page(c))
            haystack = " ".join((name.lower(), code.lower(),
                                 LANGUAGE_ALIASES.get(code, "")))
            entries.append((action, haystack))

        def apply_filter(text):
            needle = text.strip().lower()
            for action, haystack in entries:
                action.setVisible(needle in haystack)
        search.textChanged.connect(apply_filter)
        search.returnPressed.connect(lambda: next(
            (a.trigger() or menu.close()
             for a, _h in entries if a.isVisible()), None))
        menu.aboutToShow.connect(search.setFocus)
        self._tmenu = menu  # kept for tests
        menu.exec(self._menu_anchor(self._translate_btn))

    def _translate_page(self, lang):
        self.config["translateLang"] = lang
        self.save_config()
        self.apply_language()
        view = self.current()
        if view is None:
            return
        url = view.url()
        if url.scheme() not in ("http", "https"):
            return
        target = QUrl("https://translate.google.com/translate")
        q = QUrlQuery()
        q.addQueryItem("sl", "auto")
        q.addQueryItem("tl", lang)
        q.addQueryItem("u", url.toString())
        target.setQuery(q)
        view.load(target)

    # ---- virtual browsers ----
    def _cycle_session(self, step):
        """Shift+Tab hops to the next virtual browser."""
        if len(self.sessions) < 2:
            return
        sids = [e["sid"] for e in self.sessions]
        i = sids.index(self.active_session) if self.active_session in sids else 0
        self.switch_session(sids[(i + step) % len(sids)])

    def _update_session_bar(self):
        lay = self.sesslay
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # also sweep strays a drag left floating outside the layout
        for child in self.sessrow.children():
            if isinstance(child, QWidget):
                child.hide()
                child.deleteLater()
        for entry in self.sessions:
            active = entry["sid"] == self.active_session
            b = QToolButton(text=entry["name"])
            b.setStyleSheet(tint(
                "QToolButton { background: %s; color: %s; border: 1px solid %s;"
                " border-radius: 0px; padding: 4px 14px; font-weight: %s; }"
                % (("#16161d", "#ffffff", "#a6adc8", "bold") if active
                   else ("#0d0d12", "#6c7086", "rgba(108, 112, 134, 60)", "normal"))))
            b.clicked.connect(lambda _, sid=entry["sid"]: self.switch_session(sid))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, sid=entry["sid"], b=b: self._session_menu(b, sid))
            b._session_sid = entry["sid"]
            b.installEventFilter(self)
            lay.addWidget(b)
        plus = QToolButton(text="+")
        plus.setToolTip("New virtual browser (own cookies and tabs)")
        plus.setStyleSheet(tint(
            "QToolButton { background: #0d0d12; color: #6c7086;"
            " border: 1px solid rgba(108, 112, 134, 60);"
            " border-radius: 0px; padding: 4px 10px; }"))
        plus.clicked.connect(self._add_session)
        lay.addWidget(plus)
        lay.addStretch()

    def switch_session(self, sid):
        self.active_session = sid
        bar = self.tabs.tabBar()
        first = None
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            in_session = getattr(w, "session", "main") == sid
            if self._is_header(w):
                visible = in_session
            else:
                g = getattr(w, "group", None)
                visible = in_session and not (g and self.collapsed.get(g))
            bar.setTabVisible(i, visible)
            if visible and not self._is_header(w) and first is None:
                first = i
        self._update_session_bar()
        current = self.current()
        if (current is None or self._is_header(current)
                or getattr(current, "session", "main") != sid):
            if first is not None:
                self.tabs.setCurrentIndex(first)
            else:
                self.new_tab(group=None)  # fresh, ungrouped, this browser
        bar.update()

    def _add_session(self):
        names = {e["name"] for e in self.sessions}
        n = 2
        while "Browser %d" % n in names:
            n += 1
        name, ok = QInputDialog.getText(
            self, "New browser", "Name:", text="Browser %d" % n)
        name = name.strip()
        if not ok or not name:
            return
        while name in names:
            name += " 2"
        self.sessions.append({"name": name, "sid": uuid.uuid4().hex[:8]})
        self.switch_session(self.sessions[-1]["sid"])

    def _session_buttons_in_layout(self):
        out = []
        for k in range(self.sesslay.count()):
            w = self.sesslay.itemAt(k).widget()
            if w is not None and hasattr(w, "_session_sid"):
                out.append(w)
        return out

    def _drag_session_move(self, local_x):
        drag = self._sess_drag
        btn = drag["btn"]
        if not drag["moved"]:
            if abs(local_x - drag["x"]) <= 12:
                return
            # lift the button out of the row; a spacer keeps its slot
            drag["moved"] = True
            drag["index"] = self._session_buttons_in_layout().index(btn)
            spacer = QWidget(self.sessrow)
            spacer.setFixedSize(btn.size())
            drag["spacer"] = spacer
            self.sesslay.removeWidget(btn)
            self.sesslay.insertWidget(drag["index"], spacer)
            spacer.show()
        # the button follows the cursor (all math in strip coordinates)
        x = int(local_x - drag["grip"])
        x = max(0, min(x, self.sessrow.width() - btn.width()))
        btn.move(x, btn.y())
        btn.raise_()
        # the gap travels as the cursor crosses neighbors
        others = self._session_buttons_in_layout()
        target = sum(1 for b in others
                     if local_x > b.geometry().center().x())
        if target != drag["index"]:
            drag["index"] = target
            self.sesslay.removeWidget(drag["spacer"])
            self.sesslay.insertWidget(target, drag["spacer"])
            self.sesslay.activate()

    def _drag_session_drop(self, drag):
        drag["btn"].hide()
        drag["btn"].deleteLater()  # the rebuild recreates it in place
        spacer = drag["spacer"]
        if spacer is not None:
            self.sesslay.removeWidget(spacer)
            spacer.deleteLater()
        sid = drag["btn"]._session_sid
        entry = next((e for e in self.sessions if e["sid"] == sid), None)
        if entry is not None:
            rest = [e for e in self.sessions if e["sid"] != sid]
            i = max(0, min(drag["index"], len(rest)))
            self.sessions = rest[:i] + [entry] + rest[i:]
        self._update_session_bar()

    def _session_menu(self, button, sid):
        menu = QMenu(self)
        name = next((e["name"] for e in self.sessions if e["sid"] == sid), sid)
        rename = menu.addAction("Rename\u2026")
        close = menu.addAction("Close \u201c%s\u201d" % name)
        close.setEnabled(len(self.sessions) > 1)
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is close:
            self._close_session(sid)
        elif chosen is rename:
            new, ok = QInputDialog.getText(
                self, "Rename browser", "Name:", text=name)
            new = new.strip()
            if ok and new and all(e["name"] != new for e in self.sessions):
                for entry in self.sessions:
                    if entry["sid"] == sid:
                        entry["name"] = new
                self._update_session_bar()

    def _close_session(self, sid):
        if len(self.sessions) <= 1:
            return
        for i in reversed(range(self.tabs.count())):
            w = self.tabs.widget(i)
            if getattr(w, "session", "main") == sid:
                self._drop_share(w)
                self.tabs.removeTab(i)
                w.deleteLater()
        for g in [g for g, s in list(self.group_sessions.items()) if s == sid]:
            if g in self.groups:
                self.groups.remove(g)
            self.group_colors.pop(g, None)
            self.collapsed.pop(g, None)
            self.group_ids.pop(g, None)
            self.group_sessions.pop(g, None)
        self.sessions = [e for e in self.sessions if e["sid"] != sid]
        self.session_profiles.pop(sid, None)
        self._closed_tabs = [t for t in self._closed_tabs
                             if t.get("session") != sid]
        if self.active_session == sid:
            self.switch_session(self.sessions[0]["sid"])
        else:
            self._update_session_bar()

    # ---- site permissions (microphone, camera, notifications) ----
    def _permission_requested(self, permission, page=None):
        label = PERMISSION_LABELS.get(permission.permissionType())
        if label is None:
            return  # let the engine keep its default for exotic requests
        page_url = None
        if page is not None:
            try:
                page_url = page.url()
            except RuntimeError:
                page_url = None  # the tab went away mid-request
        origin, show, storable = _origin_key(permission.origin(), page_url)
        key = "%s|%s" % (origin, permission.permissionType().name)
        # `origin` is the key; `show` is the short name the card prints
        # A private tab answers out of a book of its own and writes into
        # it: nothing it allows is stored, and nothing stored is read
        # for it - an "always allow" he once gave a site cannot arm that
        # site's microphone in a tab he opened to be nobody in. The book
        # goes when the last private tab does.
        private = self._page_is_private(page)
        answered = self._private_perms if private else self._session_perms
        storable = storable and not private
        # only an origin the engine can name is ever answered from the
        # config: a hostless one speaks for every local file at once
        if storable and self.config.get("permissions", {}).get(key):
            permission.grant()
            return
        if key in answered:
            permission.grant() if answered[key] else permission.deny()
            return
        # Qt hands the slot a permission that dies with the signal
        # call, so a card the user answers seconds later would grant a
        # freed object: getUserMedia would hang forever (and touching
        # it can take the process down). Park an owned copy instead.
        self._perm_queue.append((QWebEnginePermission(permission), page,
                                 show, label, key, origin, storable,
                                 private))
        self._next_permission()

    @staticmethod
    def _page_is_private(page):
        """Whether a page sits in the off-the-record jar. Asked of the
        profile, not of a tab: the profile is the thing that cannot
        write, so it is the thing worth asking."""
        if page is None:
            return False
        try:
            return bool(page.profile().isOffTheRecord())
        except (AttributeError, RuntimeError):
            return False

    def _request_is_live(self, page):
        """Whether the tab the card belongs to is still there.

        isValid() is no help: it stays True for a permission whose tab
        closed minutes ago. Whether the page object still exists is the
        one thing that can honestly be checked, and it is the only thing
        worth checking. It is deliberately not compared against the
        page's URL: the origin that asks is very often not the origin in
        the address bar. A cross-origin <iframe allow="microphone"> is
        how Meet, Jitsi and Teams embeds ask, and a window.open() popup
        that writes its own document sits at about:blank while asking as
        its opener. Refusing those on a URL mismatch does not deny them
        — grant() is simply never called and getUserMedia() hangs for
        ever with no error at all, which is far worse than answering a
        request whose page has since moved on."""
        if page is None:
            return True  # no witness; answer it and let the engine judge
        try:
            return not sip.isdeleted(page)
        except RuntimeError:
            return False

    def _next_permission(self):
        if self._perm_widget is not None or not self._perm_queue:
            return
        (permission, page, show, label,
         key, origin, storable, private) = self._perm_queue.pop(0)
        # a small card in the bottom-right corner, clear of the tabs
        card = QWidget(self, objectName="permcard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setFixedWidth(300)
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(12)
        msg = QLabel("%s wants to %s." % (show, label))
        msg.setWordWrap(True)
        v.addWidget(msg)
        if private or not storable:
            # a local file has no origin the engine can tell apart from
            # the next one's, so an "always" here would be an always for
            # every page on the disk. Say so rather than promise it.
            hint = QLabel(self._ui_str("privatePermHint") if private
                          else "Only until you close the browser.",
                          objectName="permhint")
            hint.setWordWrap(True)
            v.addWidget(hint)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        deny = QToolButton(text="Deny")
        allow = QToolButton(text="Allow", objectName="permallow")
        row.addWidget(deny)
        row.addWidget(allow)
        v.addLayout(row)
        self._perm_widget = card

        def decide(granted):
            # the tab may have navigated away or closed while the card
            # sat there; the copy then refers to a request that is no
            # longer live and answering it would be meaningless
            if self._request_is_live(page):
                permission.grant() if granted else permission.deny()
            book = self._private_perms if private else self._session_perms
            book[key] = granted
            # only allows are remembered across restarts, and only for
            # an origin worth the name: a local file is this run only
            if granted and storable:
                self.config.setdefault("permissions", {})[key] = True
                self.save_config()
            # hide first: deleteLater runs a turn later, and the next
            # card goes up in the same corner right now
            card.hide()
            card.deleteLater()
            self._perm_widget = None
            self._next_permission()

        allow.clicked.connect(lambda: decide(True))
        deny.clicked.connect(lambda: decide(False))
        self._place_perm()
        card.show()
        card.raise_()

    def _place_perm(self):
        card = getattr(self, "_perm_widget", None)
        if card is not None:
            card.adjustSize()
            card.move(self.width() - card.width() - 18,
                      self.height() - card.height() - 18)

    # ---- screen sharing ----
    def _desktop_media_requested(self, request, page=None, view=None):
        """getDisplayMedia() lands here, not in permissionRequested:
        Qt asks *what* to share rather than whether it may, and hands
        over the screens and windows it is willing to give. Until this
        was connected the call failed instantly with AbortError."""
        if self._share_picker is not None:
            request.cancel()  # one picker at a time; the rest are noise
            return
        page_url = QUrl()
        if page is not None:
            try:
                page_url = page.url()
            except RuntimeError:
                page_url = QUrl()
        _, show, _ = _origin_key(page_url, page_url)
        picker = SharePicker(self, request, show, (view, page))
        self._share_picker = picker
        try:
            picker.place()
            picker.show()
            picker.raise_()
            picker.setFocus()
            picker.wait()  # the request is only alive inside this slot
            # `answered` is set by the tab-lost path too, precisely so
            # that nothing is sent to a request whose tab has gone
            if not picker.answered:  # closed some other way; say no
                try:
                    request.cancel()
                except RuntimeError:
                    pass  # its tab took it with it
        finally:
            self._share_picker = None
            picker.hide()
            picker.deleteLater()

    def _place_share(self):
        picker = getattr(self, "_share_picker", None)
        if picker is not None and picker.isVisible():
            picker.place()

    def _drop_share(self, widget=None):
        """Decline a screen-share request before its tab is taken away.

        The engine answers a desktop-media request through a callback
        holding a raw pointer to the tab's WebContents, and by the time
        the tab is actually deleted that pointer is already dangling —
        answering it then is a use-after-free, and so is letting the
        request die unanswered. Every place the browser gives up a tab
        or gives up altogether comes through here first, while the tab
        is still whole and cancelling is still safe."""
        picker = getattr(self, "_share_picker", None)
        if picker is not None and (widget is None or picker.owns(widget)):
            picker.cancel()

    # ---- tab groups (Chrome-style inline headers) ----
    def _group_of(self, widget):
        if widget is None or self._is_header(widget):
            return None
        return getattr(widget, "group", None)

    def _is_header(self, widget):
        return getattr(widget, "group_header", None) is not None

    def _header_index(self, group):
        for i in range(self.tabs.count()):
            if getattr(self.tabs.widget(i), "group_header", None) == group:
                return i
        return None

    def _group_indices(self, group):
        return [i for i in range(self.tabs.count())
                if not self._is_header(self.tabs.widget(i))
                and getattr(self.tabs.widget(i), "group", None) == group]

    def _group_dot(self, group):
        pix = QPixmap(12, 12)
        pix.fill(QColor(self.group_colors.get(group, "#6c7086")))
        return QIcon(pix)

    def _group_menu(self):
        menu = GroupMenu(self)
        listed = [g for g in self.groups
                  if self.group_sessions.get(g, "main") == self.active_session]
        for g in listed:
            action = menu.addAction(self._group_dot(g), g)
            action.setData(g)
            action.triggered.connect(lambda _, g=g: self._goto_group(g))
        if listed:
            menu.addSeparator()
        menu.addAction("New group\u2026").triggered.connect(self._new_group)
        menu.exec(self._menu_anchor(self._book))

    def _prompt_group(self):
        """Ask for a name and color; returns (name, color) or None."""
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        name = name.strip()
        if not ok or not name or name in self.groups:
            return None
        picker = QMenu(self)
        for label, color in GROUP_COLORS:
            pix = QPixmap(12, 12)
            pix.fill(QColor(color))
            picker.addAction(QIcon(pix), label).setData(color)
        chosen = picker.exec(
            self._menu_anchor(self._book))
        fallback = GROUP_COLORS[len(self.groups) % len(GROUP_COLORS)][1]
        return name, (chosen.data() if chosen else fallback)

    def _register_group(self, name, color, at=None, session=None):
        self.groups.append(name)
        self.group_colors[name] = color
        self.collapsed[name] = False
        session = session or self.active_session
        self.group_sessions[name] = session
        header = QWidget()
        header.group_header = name
        header.session = session
        if at is None:
            self.tabs.addTab(header, name)
        else:
            self.tabs.insertTab(at, header, name)
        self.tabs.tabBar().update()

    def _new_group(self):
        result = self._prompt_group()
        if result is None:
            return
        self._register_group(*result)
        self.new_tab(group=result[0])  # every group starts with a fresh tab

    def _tab_to_new_group(self, index):
        result = self._prompt_group()
        if result is None:
            return
        view = self.tabs.widget(index)
        self._register_group(*result, at=index)  # header lands before the tab
        view.group = result[0]
        self._sync_profile(view)
        self.tabs.tabBar().update()

    def _move_tab_to_group(self, index, group):
        view = self.tabs.widget(index)
        old = self._group_of(view)
        if old == group:
            return
        title = self.tabs.tabText(index)
        was_current = view is self.current()
        self.tabs.removeTab(index)
        view.group = group
        if group is not None:
            if self.collapsed.get(group):
                self._toggle_collapse(group)
            block = [self._header_index(group)] + self._group_indices(group)
            j = self.tabs.insertTab(max(block) + 1, view, title)
        else:
            j = self.tabs.addTab(view, title)
        self.tabs.setTabIcon(j, view.icon())
        self._add_close_button(j, view)
        self._sync_profile(view)
        if was_current:
            self.tabs.setCurrentIndex(j)
        if old is not None:
            self._cleanup_group_if_empty(old)
        self.tabs.tabBar().update()

    def _cleanup_group_if_empty(self, group):
        if self._group_indices(group):
            return
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)

    def _rename_group(self, old, new):
        new = new.strip()
        if not new or new in self.groups or old not in self.groups:
            return
        for i in self._group_indices(old):
            self.tabs.widget(i).group = new
        h = self._header_index(old)
        if h is not None:
            self.tabs.widget(h).group_header = new
            self.tabs.setTabText(h, new)
        self.groups[self.groups.index(old)] = new
        self.group_colors[new] = self.group_colors.pop(old, "#6c7086")
        self.collapsed[new] = self.collapsed.pop(old, False)
        if old in self.group_ids:
            self.group_ids[new] = self.group_ids.pop(old)
        self.tabs.tabBar().update()

    def ungroup(self, group):
        """Dissolve the group but keep its tabs, like Chrome's Ungroup."""
        if self.collapsed.get(group):
            self._toggle_collapse(group)
        for i in self._group_indices(group):
            member = self.tabs.widget(i)
            member.group = None
            self._sync_profile(member)
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)
        self.tabs.tabBar().update()

    def _tab_menu(self, index):
        view = self.tabs.widget(index)
        group = self._group_of(view)
        menu = QMenu(self)
        if getattr(view, "private", False):
            pass   # a private tab joins no group: its jar is not one
        elif group is None:
            menu.addAction("Add tab to new group\u2026").triggered.connect(
                lambda: self._tab_to_new_group(self.tabs.indexOf(view)))
            if self.groups:
                sub = menu.addMenu("Add tab to group")
                for g in self.groups:
                    sub.addAction(self._group_dot(g), g).triggered.connect(
                        lambda _, g=g: self._move_tab_to_group(
                            self.tabs.indexOf(view), g))
        else:
            menu.addAction("New tab in group").triggered.connect(
                lambda: self.new_tab(group=group))
            menu.addAction("Remove from group").triggered.connect(
                lambda: self._move_tab_to_group(self.tabs.indexOf(view), None))
        menu.addSeparator()
        menu.addAction(self._ui_str("privateNew")
                       + "  \u00b7  Ctrl+Shift+N").triggered.connect(
            self.new_private_tab)
        menu.addSeparator()
        menu.addAction("Close tab").triggered.connect(
            lambda: self.close_tab(self.tabs.indexOf(view)))
        bar = self.tabs.tabBar()
        menu.exec(bar.mapToGlobal(bar.tabRect(index).bottomLeft()))

    def _header_menu(self, index):
        group = self.tabs.widget(index).group_header
        menu = QMenu(self)
        menu.addAction("New tab in group").triggered.connect(
            lambda: self.new_tab(group=group))
        menu.addAction("Rename\u2026").triggered.connect(
            lambda: self._rename_dialog(group))
        colors = menu.addMenu("Color")
        for label, color in GROUP_COLORS:
            pix = QPixmap(12, 12)
            pix.fill(QColor(color))
            colors.addAction(QIcon(pix), label).triggered.connect(
                lambda _, c=color: self._set_group_color(group, c))
        menu.addSeparator()
        menu.addAction("Ungroup").triggered.connect(
            lambda: self.ungroup(group))
        menu.addAction("Close group").triggered.connect(
            lambda: self.delete_group(group))
        bar = self.tabs.tabBar()
        menu.exec(bar.mapToGlobal(bar.tabRect(index).bottomLeft()))

    def _rename_dialog(self, group):
        name, ok = QInputDialog.getText(
            self, "Rename group", "Group name:", text=group)
        if ok:
            self._rename_group(group, name)

    def _set_group_color(self, group, color):
        if group in self.group_colors:
            self.group_colors[group] = color
            self.tabs.tabBar().update()

    def _goto_group(self, group):
        if self.collapsed.get(group):
            self._toggle_collapse(group)
        members = self._group_indices(group)
        if members:
            self.tabs.setCurrentIndex(members[0])

    def _toggle_collapse(self, group):
        self.collapsed[group] = not self.collapsed.get(group, False)
        bar = self.tabs.tabBar()
        for i in self._group_indices(group):
            bar.setTabVisible(i, not self.collapsed[group])

    def _nearest_tab(self, index):
        bar = self.tabs.tabBar()
        order = list(range(index + 1, self.tabs.count()))
        order += list(range(index - 1, -1, -1))
        for i in order:
            if bar.isTabVisible(i) and not self._is_header(self.tabs.widget(i)):
                return i
        return None

    def delete_group(self, group):
        """Close the group's tabs and its header."""
        for i in reversed(self._group_indices(group)):
            w = self.tabs.widget(i)
            self._drop_share(w)
            self.tabs.removeTab(i)
            w.deleteLater()
        h = self._header_index(group)
        if h is not None:
            hw = self.tabs.widget(h)
            self.tabs.removeTab(h)
            hw.deleteLater()
        if group in self.groups:
            self.groups.remove(group)
        self.group_colors.pop(group, None)
        self.collapsed.pop(group, None)
        self._ensure_tab_or_quit()

    def _ensure_tab_or_quit(self):
        """Closing the very last tab closes the browser, like Chrome.
        Other virtual browsers keep this one alive with a fresh tab;
        tabs surviving only in folded groups unfold instead."""
        real = [i for i in range(self.tabs.count())
                if not self._is_header(self.tabs.widget(i))]
        if not real:
            self.close()
            return
        mine = [i for i in real
                if getattr(self.tabs.widget(i), "session", "main")
                == self.active_session]
        if not mine:
            self.new_tab(group=None)
            return
        bar = self.tabs.tabBar()
        if not any(bar.isTabVisible(i) for i in mine):
            for g in self.groups:
                if (self.collapsed.get(g)
                        and self.group_sessions.get(g, "main")
                        == self.active_session):
                    self._toggle_collapse(g)
                    members = self._group_indices(g)
                    if members:
                        self.tabs.setCurrentIndex(members[0])
                    break

    # ---- navigation ----
    def _navigate(self):
        text = self.urlbar.text().strip()
        if not text:
            return
        if " " in text or ("." not in text and text != "localhost"):
            engine = SEARCH_ENGINES.get(self.config.get("searchEngine", "google"),
                                        SEARCH_ENGINES["google"])
            url = engine[1].format(QUrl.toPercentEncoding(text).data().decode())
        elif "://" in text:
            url = text
        else:
            url = "https://" + text
        view = self.current()
        # every other way of starting a load leaves the address behind
        # as a fallback; a shutdown mid-load must not lose this one
        view._requested = url
        view.load(QUrl(url))
        view.setFocus()

    def _focus_url(self):
        self.urlbar.setFocus()
        self.urlbar.selectAll()

    # ---- suggestions ----
    def _fetch_suggestions(self):
        text = self.urlbar.text().strip().lower()
        if len(text) < 2 or "://" in text or not self.urlbar.hasFocus():
            return
        domains = [d for d in COMMON_SITES + sorted(self.known_hosts)
                   if d.startswith(text) or d.split(".")[0].startswith(text)
                   or d.startswith("www." + text)]
        domains = list(dict.fromkeys(domains))
        domains = [d for d in domains
                   if not (d.startswith("www.") and d[4:] in domains)][:3]
        if self._suggest_reply is not None:
            self._suggest_reply.abort()
        if (not self.config.get("searchSuggestions", True)
                or getattr(self.current(), "private", False)):
            # switched off, or the tab in front is private: nothing
            # typed here leaves the machine, and a private tab must not
            # hand the search engine a word-by-word account of what he
            # is looking for. The guesses from his own history and the
            # common-site list still show.
            self.suggest_model.setStringList(domains)
            if domains and self.urlbar.hasFocus():
                self.completer.complete()
            return
        url = QUrl(SUGGEST_URL)
        q = QUrlQuery()
        q.addQueryItem("client", "firefox")
        q.addQueryItem("q", text)
        url.setQuery(q)
        reply = self._nam.get(QNetworkRequest(url))
        self._suggest_reply = reply
        reply.finished.connect(
            lambda r=reply, t=text, d=domains: self._got_suggestions(r, t, d))

    def _got_suggestions(self, reply, text, domains):
        if reply is self._suggest_reply:
            self._suggest_reply = None
        searches = []
        try:
            searches = json.loads(bytes(reply.readAll()).decode())[1]
        except Exception:
            pass
        reply.deleteLater()
        if self.urlbar.text().strip().lower() != text:
            return  # user typed on; a newer request is coming
        items = domains + [s for s in searches if s not in domains][:6]
        self.suggest_model.setStringList(items)
        if items and self.urlbar.hasFocus():
            self.completer.complete()

    def _remember_host(self, url):
        host = url.host()
        if url.scheme() in ("http", "https") and host and host not in self.known_hosts:
            self.known_hosts.add(host)
            try:
                HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
                HOSTS_FILE.write_text(json.dumps(sorted(self.known_hosts)))
            except OSError:
                pass

    def force_dark_on(self):
        """Whether websites are auto-darkened at all just now: the
        setting he chose, and only while the browser itself is dark.
        A light theme holds it off — darkened websites inside a white
        browser is the one combination nobody wants — and the setting
        is left where he put it, so it comes back with the next dark
        theme.

        One question, asked in two places, because auto-darkening is
        set in two places: on the cookie jar, and on the page."""
        return bool(self.config.get("forceDark", True)) and theme_is_dark()

    def _apply_page_force_dark(self, view, url=None):
        """Auto-darkening for one tab.

        A page-level attribute beats the profile's, so this is the one
        that decides: a theme that holds force-dark off on every jar
        and not here holds it off nowhere."""
        if url is None:
            url = view.url()
        host = url.host().removeprefix("www.")
        # our own pages (start/settings/history) are already dark by
        # design — force-dark would invert their white toggles to gray
        own_page = url.scheme() == "file"
        native_dark = (own_page
                       or any(host == d or host.endswith("." + d)
                              for d in NATIVE_DARK_SITES)
                       or bool(re.fullmatch(r"google\.[a-z.]+", host)))
        view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.ForceDarkMode,
            self.force_dark_on() and not native_dark)

    def _refresh_page_force_dark(self):
        """The same question re-asked of every tab and every pane that
        already exists. Switching to a light theme has to fix the tabs
        he is looking at, not only the next page he opens: the
        page-level override outlives the profile's and would otherwise
        sit there force-darkening until he navigated."""
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "page") and hasattr(w, "url"):
                self._apply_page_force_dark(w)
        for pane in (getattr(self, "_panes", None) or {}).values():
            if getattr(pane, "view", None) is not None:
                self._apply_page_force_dark(pane.view)

    def _url_changed(self, view, url):
        self._blank_settled(view, url)
        # the level this tab reads at, re-applied at every navigation:
        # the engine's zoom rides on the page, and a website reached
        # from one of the browser's own pages must not inherit its level
        self._apply_zoom(view)
        if not getattr(view, "private", False):
            # the address bar's suggestions are a record of where he has
            # been, and a private tab adds nothing to that either
            self._remember_host(url)
        self._apply_page_force_dark(view, url)
        # never clobber the bar while the user is typing in it
        if view is self.current() and not self.urlbar.hasFocus():
            self.urlbar.setText("" if url == START_PAGE else url.toString())
            self.urlbar.setCursorPosition(0)
        if view is self.current():
            self._sync_star()
            self._sync_acct()
        self._check_account_chooser()

    def _place_newtab(self):
        btn = getattr(self, "_newtab_btn", None)
        if btn is None:
            return
        bar = self.tabs.tabBar()
        last = None
        for i in range(self.tabs.count()):
            if bar.isTabVisible(i):
                last = i
        x = 6 if last is None else bar.tabRect(last).right() + 6
        x = min(x, bar.width() - btn.width() - 2)
        y = max(0, (bar.height() - btn.height()) // 2)
        btn.move(max(0, x), y)
        btn.raise_()

    def _update_close_buttons(self):
        """Very small tabs show just the site icon: the close button
        survives only on the active tab, like Chrome."""
        bar = self.tabs.tabBar()
        current = self.tabs.currentIndex()
        for i in range(self.tabs.count()):
            holder = bar.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if holder is None:
                continue
            want = bar.tabRect(i).width() >= 90 or i == current
            if holder.isVisibleTo(bar) != want:
                holder.setVisible(want)

    def _icon_changed(self, view, icon):
        if getattr(view, "private", False):
            # the mark stays put: the strip says "private", not which
            # site - and nothing keeps the site's icon anywhere
            return
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabIcon(i, icon)
        self._fill_bookmark_icon(view, icon)

    def _fill_bookmark_icon(self, view, icon):
        """A page bookmarked before its favicon had arrived gets it now.
        Only ever fills a blank, so this cannot churn the file."""
        entry = self._bookmark_for(view.url())
        if entry is None or entry.get("icon"):
            return
        data = _icon_data(icon)
        if not data:
            return
        entry["icon"] = data
        # the file, and the one button that changed — not the whole row,
        # and not a redraw of an open manager page either
        self.write_bookmarks()
        bar = getattr(self, "bmbar", None)
        if bar is not None:
            bar.update_icon(entry)

    def _title_changed(self, view, title):
        private = getattr(view, "private", False)
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabText(i, title or "New tab")
            tip = title
            if private:
                tip = ((title + "  \u00b7  ") if title else "") \
                    + self._ui_str("privateTip")
            self.tabs.setTabToolTip(i, tip)
        if private:
            return          # a private tab writes no history, ever
        self._record_history(view.url(), title)

    # ---- history ----
    def _record_history(self, url, title):
        if not self.config.get("history", True):
            return
        if url.scheme() not in ("http", "https") or not title:
            return
        entry = {"url": url.toString(), "title": title, "t": int(time.time())}
        if self.history and self.history[-1]["url"] == entry["url"]:
            self.history[-1] = entry  # same page: refresh title/time only
        else:
            self.history.append(entry)
            if len(self.history) > HISTORY_MAX:
                del self.history[:len(self.history) - HISTORY_MAX + 500]
        self.save_history()

    def save_history(self):
        _page_data_changed()
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.history))
        except OSError:
            pass

    def save_config(self):
        _page_data_changed()
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self.config))
        except OSError:
            pass

    def eventFilter(self, obj, event):
        # the star rides along inside the address bar, and so does
        # the account chooser's handle at the other end
        if (obj is getattr(self, "urlbar", None)
                and event.type() == QEvent.Type.Resize):
            self._place_star()
            self._place_acct()
        # dragging a virtual-browser button: it lifts out of the row
        # and floats with the cursor, a gap marks where it will land
        if isinstance(obj, QToolButton) and hasattr(obj, "_session_sid"):
            if (event.type() == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton):
                local = self.sessrow.mapFromGlobal(
                    event.globalPosition().toPoint()).x()
                self._sess_drag = {"btn": obj, "moved": False,
                                   "x": local,
                                   "grip": event.position().x(),
                                   "spacer": None, "index": 0}
            elif (event.type() == QEvent.Type.MouseMove
                    and getattr(self, "_sess_drag", None)):
                self._drag_session_move(self.sessrow.mapFromGlobal(
                    event.globalPosition().toPoint()).x())
            elif (event.type() == QEvent.Type.MouseButtonRelease
                    and getattr(self, "_sess_drag", None)):
                drag = self._sess_drag
                self._sess_drag = None
                if drag["moved"]:
                    self._drag_session_drop(drag)
                    return True  # a drag is not a click
            return False
        # group headers act as fold/unfold buttons: swallow their clicks
        # before Qt selects them, so the page never flashes
        if (obj is self.tabs.tabBar()
                and event.type() in (QEvent.Type.MouseButtonPress,
                                     QEvent.Type.MouseButtonDblClick)):
            i = obj.tabAt(event.position().toPoint())
            if event.type() == QEvent.Type.MouseButtonPress:
                self._drag_active = True
                w0 = self.tabs.widget(i) if i >= 0 else None
                # remember which tab the hand is on: during a drag Qt
                # also reports the tabs being pushed aside, and only the
                # held tab may change group membership
                self._drag_view = (w0 if w0 is not None
                                   and not self._is_header(w0) else None)
            if i >= 0:
                w = self.tabs.widget(i)
                if event.button() == Qt.MouseButton.RightButton:
                    if self._is_header(w):
                        self._header_menu(i)
                    else:
                        self._tab_menu(i)
                    return True
                if self._is_header(w):
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._header_clicked(w.group_header, i)
                    return True
        if (obj is self.tabs.tabBar()
                and event.type() == QEvent.Type.MouseButtonRelease
                and getattr(self, "_drag_active", False)):
            self._drag_active = False
            self._drag_view = None
            QTimer.singleShot(0, self._finalize_drag)
        return super().eventFilter(obj, event)

    def _tab_changed(self, index):
        self._update_private_marks()
        w = self.tabs.widget(index)
        if w is not None and self._is_header(w):
            # selection landed on a header some indirect way: step off it
            QTimer.singleShot(0, lambda: self._step_off_header(index))
            return
        if w is not None and getattr(w, "_pending", None):
            pending = w._pending
            w._pending = None
            w.load(QUrl(pending))
        if w is not None and hasattr(w, "url"):
            url = w.url()
            self.urlbar.setText("" if url == START_PAGE else url.toString())
        bar = getattr(self, "_findbar", None)
        if bar is not None:
            bar.retarget()
        self._sync_star()
        self._sync_acct()
        self._check_account_chooser()
        self._nudge_accounts(w if hasattr(w, "page") else None)
        self._update_close_buttons()

    def _step_off_header(self, index):
        # only act if the selection is still stuck on that header
        w = self.tabs.widget(index)
        if (self.tabs.currentIndex() != index or w is None
                or not self._is_header(w)):
            return
        target = self._nearest_tab(index)
        if target is not None:
            self.tabs.setCurrentIndex(target)

    def _header_clicked(self, group, index):
        bar = self.tabs.tabBar()
        if not self.collapsed.get(group, False):
            # about to collapse: leave the group BEFORE its tabs hide,
            # otherwise Qt momentarily selects the header (flash)
            cur = self.tabs.currentIndex()
            if self._group_of(self.tabs.widget(cur)) == group:
                outside = [i for i in range(self.tabs.count())
                           if bar.isTabVisible(i)
                           and not self._is_header(self.tabs.widget(i))
                           and self._group_of(self.tabs.widget(i)) != group]
                if outside:
                    self.tabs.setCurrentIndex(
                        min(outside, key=lambda i: abs(i - cur)))
                else:
                    self.new_tab(group=None)  # fresh ungrouped tab
        self._toggle_collapse(group)

    # ---- misc ----
    def open_find(self):
        """Ctrl+F. Not while a pane is up: it covers the page the bar
        would be searching. (The shortcut steps out of the pane first,
        so this only bites callers that did not.)"""
        if self.pane_open():
            return
        if self._findbar is None:
            self._findbar = FindBar(self)
        self._findbar.open()

    def open_tab_switcher(self):
        """Ctrl+Shift+A."""
        if self.pane_open():
            return
        if self._switcher is None:
            self._switcher = TabSwitcher(self)
        self._switcher.open()

    def focus_tab(self, view):
        """Bring one tab to the front from wherever it is: another
        virtual browser, or a group folded shut."""
        if view is None:
            return
        try:
            if self.tabs.indexOf(view) < 0:
                return  # closed while the switcher was open
        except RuntimeError:
            return
        session = getattr(view, "session", "main")
        if (session != self.active_session
                and any(e["sid"] == session for e in self.sessions)):
            self.switch_session(session)
        group = self._group_of(view)
        if group is not None and self.collapsed.get(group):
            self._toggle_collapse(group)
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setCurrentIndex(index)
            view.setFocus()

    def set_fullscreen(self, on):
        self.chrome.setVisible(not on)
        self.tabs.tabBar().setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    def _make_profile(self, storage):
        """A fully configured cookie jar; each tab group gets its own.

        storage=None builds the off-the-record jar a private tab uses.
        A profile with no storage name has nowhere to write: cookies,
        local storage, the cache and the favicons all live in memory and
        die with it. Nothing here has to tidy up afterwards, because
        nothing was ever put down - which is the only promise about
        traces worth making."""
        private = storage is None
        profile = (QWebEngineProfile(self) if private
                   else QWebEngineProfile(storage, self))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            if private else
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        profile.downloadRequested.connect(self._download)
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        # the start page is a local file; without this it may not navigate
        # to the web (search box / quick links -> ERR_NETWORK_ACCESS_DENIED)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        # smooth scrolling, autoplay, the PDF viewer and force-dark are
        # all settings now: one place sets them, for every jar
        self.apply_web_attributes(profile)
        self.apply_spellcheck(profile)
        # some sites (Teams…) block calls on unknown browsers; the engine
        # IS Chromium, so drop the QtWebEngine token from the identity
        profile.setHttpUserAgent(
            re.sub(r"\s?QtWebEngine/[\d.]+", "", profile.httpUserAgent()))
        lang = self.config.get("translateLang", "de")
        profile.setHttpAcceptLanguage(
            lang if lang.startswith("en") else lang + ",en")
        profile.settings().setFontSize(
            QWebEngineSettings.FontSize.MinimumFontSize,
            int(self.config.get("minFont", 0) or 0))
        self._forget_opaque_permissions(profile)
        profile.scripts().insert(self._google_script())
        profile.scripts().insert(self._theme_script())
        # Vault Password off means the watcher never reaches a page at
        # all — not injected and idle, simply absent. Every profile
        # comes through here, including a virtual browser made later,
        # so this is the whole gate.
        # ...and a private tab is where it never reaches at all: the
        # watcher is not injected into the off-the-record jar, so there
        # is nothing there to offer a save or to fill from.
        if self.vault_password_on() and not private:
            profile.scripts().insert(self._password_script())
        for script in self.plugin_scripts:
            profile.scripts().insert(script)
        if getattr(self, "_wipe_cookies_at_start", False):
            # "clear cookies when the browser closes" was on last time;
            # every jar opened this run starts empty, late ones included
            profile.cookieStore().deleteAllCookies()
            profile.clearHttpCache()
        return profile

    def _forget_opaque_permissions(self, profile):
        """Every local page is the one origin "file:///" as far as the
        engine is concerned, so a permission it kept on disk for one of
        them would still be arming every other HTML file on the disk
        next week. The browser remembers a local page for the session
        only; the engine is made to forget them at every start."""
        try:
            stored = profile.listAllPermissions()
        except (AttributeError, RuntimeError):
            return
        for permission in stored:
            if not permission.origin().host():
                permission.reset()

    def _google_script(self):
        script = QWebEngineScript()
        script.setName("google-mode")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(
            GOOGLE_LIGHT_JS if self.config.get("googleLight", True)
            else GOOGLE_BLACK_JS)
        return script

    def _theme_script(self):
        """What paints one of the browser's own pages. It carries the
        palette with it, so the page is in the right colours from the
        first frame instead of flashing the default one first."""
        script = QWebEngineScript()
        script.setName("theme")
        script.setInjectionPoint(
            QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(THEME_JS % {"payload":
                                         json.dumps(theme_payload())})
        return script

    def _password_script(self):
        script = QWebEngineScript()
        script.setName("password-watch")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.Deferred)
        script.setWorldId(QWebEngineScript.ScriptWorldId.UserWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(_qwebchannel_source() + "\n"
                             + PASSWORD_WATCH_JS)
        return script

    # ---- the buttons in the chrome ----
    # He picks which of them are there and what order they come in.
    # Everything below reads TOOLBAR_ITEMS and the two config keys, so
    # a button added to the registry needs nothing else anywhere.

    def _tb_back(self):
        self.current().back()

    def _tb_forward(self):
        self.current().forward()

    def _tb_reload(self):
        self.current().reload()

    def _tb_newtab(self):
        self.new_tab()

    def _tb_fullscreen(self):
        self.set_fullscreen(not self.isFullScreen())

    def _tb_label(self, name):
        """What this button is called, in his language."""
        item = TOOLBAR_BY_NAME.get(name)
        return self._ui_str(item["str"]) if item else name

    def _tb_tip(self, name):
        """Its tooltip: the name, and the key that does the same thing
        - which keeps working whether the button is there or not."""
        item = TOOLBAR_BY_NAME.get(name)
        if not item:
            return ""
        key = item["key"]
        return self._tb_label(name) + ("  \u00b7  " + key if key else "")

    def _tb_available(self, name):
        """Whether this button is on offer at all. Only the password
        manager is ever off the list: with Vault Password switched off
        there is nothing behind it, and a button that does nothing is
        worse than no button. The saved list still remembers it, so
        switching the vault back on brings the button back too."""
        if name not in TOOLBAR_BY_NAME:
            return False
        if name == "passwords":
            return bool(self.vault_password_on())
        return True

    def _make_toolbar_buttons(self):
        """One QToolButton per registry entry that lives on the bar.
        All of them are built, always - switching one off takes it off
        the layout, it does not stop it existing, so switching it back
        on is a relayout and not a rebuild."""
        for item in TOOLBAR_ITEMS:
            name = item["name"]
            if item["place"] != "bar" or name == "address":
                continue
            btn = QToolButton(text=item["glyph"])
            btn.clicked.connect(getattr(self, item["act"]))
            self._tb_buttons[name] = btn
        # the names the rest of the browser already knows four of them by
        self._home_btn = self._tb_buttons["home"]
        self._proxy_btn = self._tb_buttons["proxy"]
        self._print_btn = self._tb_buttons["print"]
        self._translate_btn = self._tb_buttons["translate"]

    def toolbar_layout(self, save=True):
        """The chrome's buttons, in order, as the saved list asks for
        them - and sound whatever that list says.

        A name this version has never heard of is dropped rather than
        crashed on, so a list written by a later version, or edited by
        hand, still opens a browser. A button he is not allowed to lose
        is put back where it belongs. And a button a later version adds
        that the saved list predates comes in at its home position
        instead of staying invisible for ever: "toolbarKnown" remembers
        every button he has already been offered, which is what tells
        brand new apart from deliberately switched off."""
        c = self.config
        saved = c.get("toolbarButtons")
        known = c.get("toolbarKnown")
        first_run = not isinstance(saved, list)
        out, seen = [], set()
        if not first_run:
            for name in saved:
                if (isinstance(name, str) and name in TOOLBAR_BY_NAME
                        and name not in seen):
                    seen.add(name)
                    out.append(name)
        if first_run:
            # nothing saved, or something that is not a list at all:
            # every button is new, so the shipped set is what he gets
            known_set = set()
        elif isinstance(known, list):
            known_set = {n for n in known if isinstance(n, str)}
        else:
            # a saved list with no record of what it was offered
            # alongside it was written by hand, and a list written by
            # hand means exactly what it says
            known_set = set(TOOLBAR_ORDER)

        def home_for(name):
            """Where a button belongs when nothing has moved it: ahead
            of the first button the registry puts after it."""
            rank = TOOLBAR_ORDER.index(name)
            for i, other in enumerate(out):
                if TOOLBAR_ORDER.index(other) > rank:
                    return i
            return len(out)

        for name in TOOLBAR_ORDER:
            if name in seen:
                continue
            item = TOOLBAR_BY_NAME[name]
            if item["fixed"] or (name not in known_set and item["on"]):
                out.insert(home_for(name), name)
                seen.add(name)
        if save and (out != saved or known_set != set(TOOLBAR_ORDER)):
            c["toolbarButtons"] = list(out)
            c["toolbarKnown"] = list(TOOLBAR_ORDER)
            self.save_config()
        return out

    def rebuild_toolbar(self):
        """Put the chrome's buttons where the saved list says.

        A button he switched off comes off the layout and is hidden -
        genuinely gone, not sitting there invisible waiting to be
        clicked. Its keyboard shortcut is a QShortcut on the window and
        never knew about the button in the first place, so Ctrl+P still
        prints with the print button gone."""
        names = [n for n in self.toolbar_layout() if self._tb_available(n)]
        wanted = set(names)
        bar = self._navlay
        while bar.count():
            w = bar.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
        for name in names:
            if TOOLBAR_BY_NAME[name]["place"] != "bar":
                continue
            if name == "address":
                # the private badge is not a button in the registry: it
                # is not his to switch off and there is nothing to click
                # on it. It rides in front of the address bar, so it
                # follows the bar wherever he has moved it to.
                bar.addWidget(self.privlbl)
                bar.addWidget(self.urlbar, 1)
                self.urlbar.show()
            else:
                btn = self._tb_buttons[name]
                bar.addWidget(btn)
                btn.show()
        for name, btn in self._tb_buttons.items():
            if (TOOLBAR_BY_NAME[name]["place"] == "bar"
                    and name not in wanted):
                btn.hide()
        # the star rides inside the address bar, so gone means the bar
        # gets its right margin back rather than keeping a gap
        star = getattr(self, "starbtn", None)
        if star is not None:
            on = "star" in wanted
            star.setVisible(on)
            if on:
                self._place_star()
        self._sync_acct()
        # and the tab groups button is the tab strip's corner
        book = getattr(self, "_book", None)
        if book is not None:
            corner = Qt.Corner.TopLeftCorner
            if "tabgroups" in wanted:
                self.tabs.setCornerWidget(book, corner)
                book.show()
            else:
                self.tabs.setCornerWidget(None, corner)
                book.hide()
        self.relabel_toolbar()
        self._update_proxy_btn()
        # A settings page may be open on the very list that just moved.
        # It is not asked to guess: it is told, the same way the
        # downloads and bookmarks pages are told, and reads the toolbar
        # again rather than posting back the copy it loaded with.
        bridge = getattr(self, "bridge", None)
        if bridge is not None:
            bridge.toolbarChanged.emit()
        # the badge was taken off the row with everything else a moment
        # ago: whether it belongs back on the screen is asked again
        self._update_private_marks()

    def relabel_toolbar(self):
        """The tooltips, in his language. Apart from rebuild_toolbar so
        that a language change can call it on its own."""
        for name, btn in self._tb_buttons.items():
            if name == "star":
                continue  # _sync_star says whether it adds or removes
            btn.setToolTip(self._tb_tip(name))
        # and the star's tooltip is _sync_star's to write, so it is
        # asked rather than skipped: left out, the one button whose
        # tooltip says what it will do stays in the old language until
        # he happens to navigate somewhere
        self._sync_star()

    def set_toolbar_buttons(self, names):
        """Take a whole order at once - what the settings page sends.
        Anything unknown in it is dropped on the way in, so the config
        never grows a name the browser cannot draw."""
        clean, seen = [], set()
        for name in names or []:
            name = str(name)
            if name in TOOLBAR_BY_NAME and name not in seen:
                seen.add(name)
                clean.append(name)
        self.config["toolbarButtons"] = clean
        self.config["toolbarKnown"] = list(TOOLBAR_ORDER)
        self.save_config()
        self.rebuild_toolbar()

    def toggle_toolbar_button(self, name, on=None):
        """One button on or off, coming back where it belongs."""
        item = TOOLBAR_BY_NAME.get(name)
        if item is None or item["fixed"]:
            return
        names = self.toolbar_layout()
        there = name in names
        if on is None:
            on = not there
        if bool(on) == there:
            return
        if on:
            rank = TOOLBAR_ORDER.index(name)
            at = len(names)
            for i, other in enumerate(names):
                if TOOLBAR_ORDER.index(other) > rank:
                    at = i
                    break
            names.insert(at, name)
        else:
            names.remove(name)
        self.set_toolbar_buttons(names)

    def move_toolbar_button(self, name, delta):
        """One step left or right, past the next button that is also on
        the bar - the star and the tab groups button sit where they sit
        and are stepped over rather than swapped with."""
        names = self.toolbar_layout()
        if name not in names or TOOLBAR_BY_NAME[name]["place"] != "bar":
            return
        i = names.index(name)
        j = i + (1 if delta > 0 else -1)
        while 0 <= j < len(names):
            if TOOLBAR_BY_NAME[names[j]]["place"] == "bar":
                break
            j += 1 if delta > 0 else -1
        if not (0 <= j < len(names)):
            return
        names.insert(j, names.pop(i))
        self.set_toolbar_buttons(names)

    def reset_toolbar(self):
        """Back to the set the browser ships with."""
        self.set_toolbar_buttons(list(TOOLBAR_DEFAULT))

    def _toolbar_menu(self, pos):
        menu = self.toolbar_menu()
        menu.exec(self.navbar.mapToGlobal(pos))

    def toolbar_menu(self):
        """Right-click the row: every button the browser has, ticked if
        it is there. The ones he cannot lose are in the list too, ticked
        and greyed, so the menu is the whole picture rather than a
        puzzle about what is missing from it.

        Built apart from the right-click that shows it, so what it says
        can be read without a menu having to be on the screen."""
        menu = QMenu(self)
        shown = set(self.toolbar_layout())
        elsewhere = False
        for item in TOOLBAR_ITEMS:
            name = item["name"]
            if not self._tb_available(name):
                continue
            if item["place"] != "bar" and not elsewhere:
                elsewhere = True
                menu.addSeparator()
                menu.addAction(self._ui_str("tbElsewhere")).setEnabled(False)
            act = menu.addAction(self._tb_label(name))
            act.setCheckable(True)
            act.setChecked(name in shown)
            if item["fixed"]:
                act.setEnabled(False)
            else:
                act.triggered.connect(
                    lambda _c, n=name: self.toggle_toolbar_button(n))
        # the bookmarks bar is a strip and not a button, so it is not
        # in the list above - but this is where he will look for it
        menu.addSeparator()
        bm = menu.addAction(self._ui_str("bmBar"))
        bm.setCheckable(True)
        bm.setChecked(self.bookmarks_bar_on())
        bm.triggered.connect(lambda on: self.toggle_bookmarks_bar(on))
        menu.addSeparator()
        menu.addAction(self._ui_str("tbReset")).triggered.connect(
            self.reset_toolbar)
        menu.addAction(self._ui_str("tbCustomize")).triggered.connect(
            self.open_settings)
        return menu

    def _menu_anchor(self, btn):
        """Where a button's drop-down drops from. A button he switched
        off has no corner on the screen to hang anything off, so its
        menu comes off the address bar instead - which is how Ctrl+P
        still puts the print menu somewhere he can see it."""
        if btn is not None and btn.isVisible():
            return btn.mapToGlobal(btn.rect().bottomLeft())
        bar = self.urlbar
        return bar.mapToGlobal(bar.rect().bottomLeft())

    def _ui_str(self, key):
        """One UI string in the chosen language (English fallback)."""
        lang = self.config.get("translateLang", "de")
        table = (UI_STRINGS.get(lang)
                 or UI_STRINGS.get(lang.split("-")[0]) or {})
        return table.get(key) or UI_STRINGS["en"].get(key, key)

    # ---- password manager ----
    def _autofill(self, view, ok=True):
        """Frictionless: a saved login fills in on load, no prompting.

        The work is done by the conversation in _login_form_seen — the
        watcher describes the page and the browser pushes back what
        belongs there. The watcher opens that conversation itself as
        soon as its channel is up; this only nudges it, for the load
        that finished before the script even ran."""
        # A new document is a new chance to ask. The chooser offers
        # itself once per page and host, so that a login form redrawing
        # itself forty times does not raise forty panels; a load is a
        # different page, and dismissing the box on the last one is not
        # an answer about this one. A form swapped in place — which is
        # what Microsoft does — is the same document and still gets the
        # one offer it already had.
        self._acct_auto.pop(id(view.page()), None)
        if not ok or not self.vault_password_on():
            return
        if getattr(view, "private", False):
            return          # nothing is ever filled into a private tab
        url = view.url()
        if url.scheme() not in ("http", "https"):
            return
        if self.vault.best_for(url.host(), url.scheme()) is None:
            return
        view.page().runJavaScript(
            "window.__bpw && window.__bpw.rescan();", PW_WORLD_ID)

    # ---- two-step logins -------------------------------------------
    # Amazon, Google and Microsoft ask for the e-mail on one screen and
    # the password on the next. Step two usually has no username field
    # at all, so the account chosen in step one has to be remembered
    # here, on the browser side: page state does not survive the
    # navigation, and the page is not to be trusted with it anyway.
    #
    # Cross-origin rule: the memory is filed under (profile, tab,
    # host) and read back only where the page and that host are the
    # same site — which is a question for the vault, because the vault
    # is what would carry the password between them. Two ways to be the
    # same site, and a page needs one of them: the hosts are equal or
    # one is a suffix of the other (example.com and
    # account.example.com), or some saved login matches them both
    # (signin.example.com and account.example.com, siblings that share
    # their parent's row). Scheme is not asked at all, since an http
    # row already fills the site's https upgrade.
    #
    # A step that lands off the site — amazon.com -> amazon.de, a hop
    # to an identity provider, an attacker's redirect — cannot read it,
    # and such a page is treated as a fresh page: it fills only from a
    # login actually saved for the host it is on, exactly as it did
    # before any of this.
    #
    # It used to be dropped the moment the tab changed host at all, on
    # that same "fresh page" reasoning — which assumed host-exact
    # matching. Matching is not host-exact: entries_for lets a
    # subdomain match its parent's row and lets an http row fill the
    # site's https upgrade. So a login begun on example.com and carried
    # on at account.example.com lost its identity at the hop, was read
    # as a page asking for a password out of nowhere, and was handed
    # the freshest row on example.com — the *other* account's password,
    # inside a session the site had just opened for the account he had
    # typed. The record now reaches exactly as far as the password
    # would, and not one host further.
    #
    # Not one host further is the whole of it. What is remembered is a
    # name, and a name is not his signature: the watcher reports
    # whatever value stands in the box, and any page can put a value
    # there. Off the site that name would be a stranger's page choosing
    # which of his saved logins the honest site's password step hands
    # over — so off the site it is not consulted at all, and the
    # browser's own "freshest here" answers, as it did before. On the
    # site it grants nothing new: a page that is on the site can put a
    # name in a visible box and be answered from it already.
    #
    # The tab is in the key because a login is one person working
    # through one tab: a second tab on the same site cannot overwrite
    # what he typed in the first, nor read it, and a virtual browser
    # cannot see another's half-finished login. Closing the tab takes
    # its half-login with it rather than leaving it lying around for
    # the rest of the five minutes.
    def _pw_step_key(self, page, host):
        """Profile, tab, host. The profile is in it as well as the tab
        so that a page id the engine has handed out again in another
        virtual browser cannot read the first one's half-login."""
        profile = page.profile()
        return ((profile.storageName() or str(id(profile))),
                id(page), host)

    def _pw_step_remember(self, page, host, scheme, username, typed):
        if not username:
            return
        key = self._pw_step_key(page, host)
        # Only this host's own record hands the flag on. Inheriting it
        # from whatever the tab was doing before would let a page on
        # the way past claim he typed the account it substituted, which
        # is precisely what _typed_sticks exists to refuse.
        old = self._pw_steps.get(key)
        typed = self._typed_sticks(old, typed)
        # One half-login per tab: a person works through one login at a
        # time. A step one on a second host replaces the first rather
        # than sitting beside it, so "the login this tab is in the
        # middle of" is never a question with two answers.
        for stale in [k for k in self._pw_steps
                      if k[1] == id(page) and k != key]:
            del self._pw_steps[stale]
        if key not in self._pw_steps:
            self._pw_step_follow(page)
        self._pw_steps[key] = {
            "host": host, "scheme": scheme, "username": username[:200],
            "typed": typed, "at": time.monotonic()}

    @staticmethod
    def _typed_sticks(old, typed):
        """Is this half-login hand-chosen? Once it has been, it stays
        that way for the rest of its life — for every account, not just
        the one he typed.

        Both ways it could come back down are the same mistake. Going
        Back rebuilds the document with the field restored but with no
        memory of who filled it, so the account returns reported as a
        guess; and a page that writes another account into the box on
        its way to the password step reports that one as a guess too.
        Believing either turns "he typed an account we have nothing
        saved for, so fill nothing" into "fill the account we do know"
        — a saved password going out under a name he never saved.

        Nothing real is lost by holding it. The account may still
        change, and the new account's own password still fills; the
        only thing withheld is the guess, and after he has typed, a
        guess is not what anybody wants.

        Kept on purpose, though nothing on the live path reads the flag
        any more: _pw_step_entry refuses the guess outright, so it gets
        there first every time. This is the belt to that pair of
        braces, and it is worth the few lines — the guess is one
        `or best_for(...)` away from coming back, and if it ever does
        it must not find the flag already lowered. test_msaccounts (z5)
        loosens _pw_step_entry back to the old rule for one run, which
        is where this is the only thing standing."""
        return bool(typed) or bool(old is not None and old.get("typed"))

    def _pw_step_follow(self, page):
        """A closed tab's half-login goes with it — and nothing can be
        read back through a page id the engine has since reused."""
        if getattr(page, "_pw_step_hooked", False):
            return
        try:
            page._pw_step_hooked = True
            page.destroyed.connect(
                lambda _=None, pid=id(page): self._pw_step_page_gone(pid))
        except (AttributeError, TypeError):
            pass

    def _pw_step_page_gone(self, page_id):
        for key in [k for k in self._pw_steps if k[1] == page_id]:
            del self._pw_steps[key]
        self._acct_auto.pop(page_id, None)

    def _pw_same_site(self, page_host, page_scheme, step):
        """Is a half-login made on step's host this page's business?

        The question is asked of the vault, because the vault is what
        would carry a password between the two hosts, and the reach of
        the memory must be the reach of the password — no shorter, or
        the parent's freshest login fills a step two that already
        belongs to somebody; no longer, or a page off the site gets to
        say whose password this is.

        Two ways to be one site. The plain one is the host relation
        entries_for fills by: equal, or one a suffix of the other, so a
        login begun on example.com is still that login on
        account.example.com.

        The other is the one the first misses, and the one the whole
        defect was made of: signin.example.com and account.example.com
        are *siblings*. Neither is a suffix of the other, and yet the
        row saved for example.com fills them both — so a login begun on
        one is answered on the other from the very same set of logins,
        which is what makes it the same login. Some saved row matching
        both hosts is exactly that condition, and it says no wherever
        the vault holds nothing the two have in common."""
        step_host = step.get("host", "")
        if not step_host:
            return False
        if (page_host == step_host
                or page_host.endswith("." + step_host)
                or step_host.endswith("." + page_host)):
            return True
        here = {id(e) for e in self.vault.entries_for(page_host, page_scheme)}
        return any(id(e) in here for e in self.vault.entries_for(
            step_host, step.get("scheme", "")))

    def _pw_step_for(self, page, host, scheme):
        """The half-login this page may be answered from: this tab's
        own — profile and tab both, so a page id the engine has handed
        out again in another virtual browser cannot read the first
        one's — and only where the page is the same site as the host it
        was made on.

        There is only ever one per tab. Off that site the answer is
        None, and None here means "nothing to say", not "fill
        nothing": a page elsewhere is a fresh page and gets the
        freshest login saved for it, exactly as it did before any of
        this. What must not happen is the half-login *choosing* there."""
        self._pw_step_prune()
        want = self._pw_step_key(page, None)[:2]
        step = next((s for k, s in self._pw_steps.items() if k[:2] == want),
                    None)
        if step is None or not self._pw_same_site(host, scheme, step):
            return None
        return step

    def _pw_step_forget(self, page, host=None):
        """The login is over: the tab's half-login goes, all of it, and
        not merely the record filed under whichever host happened to
        submit the form."""
        for key in [k for k in self._pw_steps if k[1] == id(page)]:
            del self._pw_steps[key]

    def _pw_step_prune(self):
        """Expire half-logins nobody came back to."""
        now = time.monotonic()
        for key in list(self._pw_steps):
            if now - self._pw_steps[key].get("at", 0) > PW_STEP_TTL:
                del self._pw_steps[key]

    def _pw_push(self, page, username, password):
        """The one direction credentials move: browser -> isolated
        world. The password still only reaches the DOM once the person
        touches the page (see PASSWORD_WATCH_JS)."""
        if password:
            # a password going out to a page is the vault being used,
            # and auto-lock counts from the last time it was
            self.vault_lock.touch()
        page.runJavaScript("window.__bpw && window.__bpw.offer(%s, %s);"
                           % (json.dumps(username), json.dumps(password)),
                           PW_WORLD_ID)

    def _pw_entry_for(self, page, host, scheme, seen_user):
        """Which saved login belongs in this password box: the account
        the document is carrying, or the one step one was filled with.

        An account the page is showing gets its own password or none.
        It does not matter whether he typed it or picked it off a list
        of account tiles: a password box standing under a name is the
        one place another account's password must never land, and
        falling back to "the freshest login on this host" there is
        exactly how the wrong one used to get in.

        Only when this tab is not halfway through a login at all is
        the freshest login on the host the answer — a page asking for
        a password out of nowhere, with nothing on screen to say whose
        it should be.

        "Halfway through a login" is asked of this site, not of this
        exact host and scheme. Asking it that narrowly was the bug: the
        record is filed per host, the vault matches whole families of
        hosts, so a step from example.com down to account.example.com
        turned a login already claimed by one account back into a page
        asking out of nowhere — and the freshest row on the parent
        domain went out under the name he had typed. Asking it more
        widely than the site would be the mirror of that bug, since the
        name is only ever what some page put in a box."""
        if seen_user:
            return self.vault.for_username(host, scheme, seen_user)
        step = self._pw_step_for(page, host, scheme)
        if step is not None:
            return self._pw_step_entry(host, scheme, step)
        if len(self._saved_account_names(host, scheme)) > 1:
            # More than one account is saved here and nobody has said
            # which. There is no answer to guess at, so nothing is
            # handed over: the chooser asks, and the fill follows the
            # answer. This is the whole of "before it gets autofilled" —
            # a password box on a site with two accounts stays empty
            # until he has pointed at one.
            return None
        return self.vault.best_for(host, scheme)

    def _pw_step_entry(self, host, scheme, step):
        """The saved login a half-finished login is for, or None.

        None means none. A tab that is halfway through a login is
        halfway through *that* login, and the freshest password on the
        host is not it — it is a different account's, and it would be
        handed over under a name that is not its own. This used to fall
        back to that guess whenever the account was not one we had
        saved and nobody had been watched typing it, which is exactly
        how the second Microsoft account, the one never saved, got the
        first one's password."""
        return self.vault.for_username(host, scheme, step["username"])

    # ---- the account chooser ----
    #
    # Two accounts on one site used to be a coin toss: the browser
    # filled the freshest and there was no way to say otherwise. The
    # chooser is the way to say otherwise, and everything about it is
    # arranged so that saying so is safe.
    #
    # The list never enters a page. It is assembled here, shown in a Qt
    # widget, and thrown away; a site that puts a sign-in form on screen
    # learns nothing at all about which accounts are saved for it.
    #
    # Nothing fills until he points at a name — not the password and
    # not the username either. While two accounts are saved for a site
    # there is no answer to guess at, so the browser stops guessing
    # (see _pw_entry_for): the form he is looking at is empty, the
    # chooser asks, and the fill follows his answer. That press is the
    # real gesture — on chrome, which no script can reach — and it
    # stands in for the touch on the page that PASSWORD_WATCH_JS
    # otherwise waits for. Dismissing is an answer too: no account, no
    # fill, and the form is left exactly as the site drew it.
    def _saved_account_names(self, host, scheme):
        """The accounts saved for this host, freshest first, one line
        per account. Two rows that fill the same page under the same
        name — example.com and www.example.com — are one account and
        not a choice, which matters: this count is what decides whether
        anything fills on its own."""
        out, seen = [], set()
        for entry in self.vault.entries_for(host, scheme):
            name = entry.get("username", "")
            key = name.strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    def _account_names(self, view=None):
        """Every saved account that could fill this page, freshest
        first — usernames only, and only ever inside the browser."""
        if not self.vault_password_on():
            return []
        view = self.current() if view is None else view
        if (view is None or self._is_header(view)
                or not hasattr(view, "url") or not hasattr(view, "page")):
            return []
        if getattr(view, "private", False):
            # A private tab is not offered saved logins, so it is not
            # asked which one either. This is the one answer the whole
            # panel hangs off: the `@` in the address bar, Ctrl+Shift+M
            # and the offer the watcher would raise all ask here, so
            # all three go quiet together - and no saved name is so
            # much as read to decide it.
            return []
        try:
            url = view.url()
        except RuntimeError:
            return []
        if url.scheme() not in ("http", "https"):
            return []
        host = PasswordVault.normalize_host(url.host())
        if not host:
            return []
        return self._saved_account_names(host, url.scheme())

    def _place_acct(self):
        btn = getattr(self, "acctbtn", None)
        if btn is None:
            return
        btn.move(5, max(0, (self.urlbar.height() - btn.height()) // 2))

    def _sync_acct(self):
        """The handle is in the bar exactly when there is a choice to
        make. One saved login is not a choice, so the address bar of
        every ordinary site looks the way it always has."""
        btn = getattr(self, "acctbtn", None)
        if btn is None:
            return
        on = len(self._account_names()) > 1
        if on:
            btn.setToolTip(self._ui_str("acctPickTip"))
        btn.setVisible(on)
        star = getattr(self, "starbtn", None)
        right = 28 if (star is not None and not star.isHidden()) else 0
        self.urlbar.setTextMargins(24 if on else 0, 0, right, 0)
        if on:
            self._place_acct()

    def open_account_chooser(self):
        """Ctrl+Shift+M, or the handle in the address bar.

        M rather than the obvious U: Ctrl+Shift+U is how IBus starts a
        Unicode code-point entry inside a text box, which is exactly
        where a person reaching for this shortcut has their cursor, and
        an input method gets the key before any application does.
        Ctrl+Shift+M is free here and is where Chrome keeps "choose who
        is using this browser", which is the same question.

        On demand, because the offer is made once per page and answered
        once: he waves it away and then wants it after all, or he signs
        in, signs out and comes back as the other account without the
        document ever being rebuilt. One saved login opens it too when
        he asks by hand — he asked, and a shortcut that silently does
        nothing is worse than a small box saying there is only the
        one. Nothing saved at all opens nothing: an empty list is not a
        question."""
        # Never over a pane. _maybe_offer_accounts refuses to raise it
        # while one is up, and this is the same rule from the other
        # side: the panel is about the sign-in form in the tab, and a
        # pane is covering that form. The Ctrl+Shift+M binding is in
        # the out_of_pane group and has already come through here once;
        # doing it again costs nothing and makes the handle in the
        # address bar obey the same rule rather than relying on being
        # unclickable underneath.
        self.close_pane()
        # Locked, there is nothing to choose between — _account_names
        # reads the vault, and a locked vault holds nothing. That is
        # the right answer to a page asking, and the wrong one to a
        # person asking: this is a shortcut he pressed, so it may ask
        # back, exactly as opening the manager does. One box, because
        # he asked for it. Nothing on a page can reach here.
        if self.vault_password_on() and self.vault_locked():
            self.ask_unlock_vault()
        view = self.current()
        names = self._account_names(view)
        if not names:
            return
        body = "" if len(names) > 1 else self._ui_str("acctPickNone")
        self._show_account_chooser(view, names, body)

    def _show_account_chooser(self, view, names, body=""):
        self._close_account_chooser()
        try:
            url = view.url()
        except RuntimeError:
            return
        host = PasswordVault.normalize_host(url.host())
        if not host or url.scheme() not in ("http", "https"):
            return
        chooser = AccountChooser(self, view.page(), host, url.scheme(),
                                 names, body)
        self._acct_chooser = chooser
        chooser.place()
        chooser.show()
        chooser.raise_()
        chooser.setFocus()

    def _place_account_chooser(self):
        chooser = getattr(self, "_acct_chooser", None)
        if chooser is not None and chooser.isVisible():
            chooser.place()

    def _close_account_chooser(self, which=None):
        chooser = getattr(self, "_acct_chooser", None)
        if which is not None and which is not chooser:
            which.hide()
            which.deleteLater()
            return
        if chooser is None:
            return
        self._acct_chooser = None
        chooser.hide()
        chooser.deleteLater()

    def _check_account_chooser(self):
        """The panel belongs to one page on one host. Switch tab, or let
        that page walk off the site, and the question it is asking is no
        longer the question on screen — so it goes, answering nothing."""
        chooser = getattr(self, "_acct_chooser", None)
        if chooser is None:
            return
        view = self.current()
        page = view.page() if (view is not None
                               and hasattr(view, "page")) else None
        ok = page is not None and page is chooser.page
        if ok:
            try:
                url = page.url()
                ok = (url.scheme() in ("http", "https")
                      and PasswordVault.normalize_host(url.host())
                      == chooser.host)
            except RuntimeError:
                ok = False
        if not ok:
            chooser.cancel()

    def _nudge_accounts(self, view):
        """A tab coming to the front may have had a sign-in form on it
        all along. Nothing was filled and no panel was raised while it
        was out of sight — a background tab must not throw a box over
        whatever he is reading — so ask the page to describe itself
        again now that it is the tab in front of him."""
        if self._acct_chooser is not None:
            return
        if view is None or not hasattr(view, "page"):
            return
        if len(self._account_names(view)) < 2:
            return
        try:
            view.page().runJavaScript(
                "window.__bpw && window.__bpw.rescan(true);", PW_WORLD_ID)
        except RuntimeError:
            pass

    def _maybe_offer_accounts(self, page, host, scheme, stage, typed):
        """A login step is on screen and more than one account is saved
        for it: ask, once, rather than guessing. Nothing has been put
        in the form and nothing will be until this is answered.

        It is only ever the guess this replaces. The moment he has named
        an account himself — typed it, or chosen it here — the panel
        stays away, because the question has an answer."""
        if stage not in ("username", "password"):
            return
        if typed:
            return                     # he has said who he is
        step = self._pw_step_for(page, host, scheme)
        if step is not None and step.get("typed"):
            return                     # already hand-chosen this login
        if self._acct_auto.get(id(page)) == host:
            return                # asked once for this document and host
        if (self._acct_chooser is not None or self._share_picker is not None
                or self._pane is not None):
            return                     # something else already has the window
        view = self.current()
        if (view is None or not hasattr(view, "page")
                or view.page() is not page):
            return                     # a background tab throws up nothing
        names = self._account_names(view)
        if len(names) < 2:
            return                     # nothing to choose between
        self._acct_auto[id(page)] = host
        self._pw_step_follow(page)     # the latch goes with the page
        self._show_account_chooser(view, names)

    def _account_chosen(self, page, host, scheme, name):
        """He pointed at a name. This is the whole authorisation.

        The press was a real one, on a widget of the browser's own — the
        page cannot reach it, move it, draw over it or synthesise a
        click on it, and there is no slot on the web channel that leads
        here. So the password may go straight into the box instead of
        arming and waiting for a second gesture on the page: the bar has
        already been cleared, on the chrome's side of the window.

        The page's live URL is authoritative, as everywhere else in this
        file. A panel raised on one host cannot deliver a password to
        the page it is over once that page has gone somewhere else.

        The choice is recorded as hand-chosen (`typed`), which is what
        it is. That is the same latch typing an account by hand sets:
        the guess is out of play for the rest of this login, on this
        step and on the one after it, and _typed_sticks will not let it
        back down again."""
        if not self.vault_password_on():
            return
        if self._page_is_private(page):
            # Belt and braces to _account_names, and not the same lock:
            # that one is about what is offered, this one about what a
            # panel already on the screen can deliver if the tab
            # underneath it turned private in between. Nothing is read
            # out of the vault, nothing is written back to it, and no
            # password is ever put into a script for that renderer.
            return
        try:
            url = page.url()
        except RuntimeError:
            return
        if (url.scheme() not in ("http", "https") or url.scheme() != scheme
                or PasswordVault.normalize_host(url.host()) != host):
            return
        entry = self.vault.for_username(host, scheme, name)
        if entry is None:
            return
        username = entry.get("username", "")
        self._pw_step_remember(page, host, scheme, username, True)
        # the one he keeps picking becomes the one the guess would make
        self.vault.touch(entry.get("host", host), username)
        self._pw_push_chosen(page, username, entry.get("password", ""))
        self._sync_acct()

    def _pw_push_chosen(self, page, username, password):
        """The chosen account, to the isolated world, for a fill that
        needs no further gesture. Kept apart from _pw_push on purpose:
        that one is the browser's guess and arms, this one is his answer
        and lands. Only ever called from _account_chosen."""
        page.runJavaScript("window.__bpw && window.__bpw.choose(%s, %s);"
                           % (json.dumps(username), json.dumps(password)),
                           PW_WORLD_ID)

    def _login_form_seen(self, page, data):
        """The watcher describes the login step the page is showing.
        The page's real URL is authoritative — the host the content
        script reports only has to agree, it is never trusted on its
        own."""
        # Nothing should be able to reach here with Vault Password off
        # — the watcher that calls it is never injected — but the slot
        # exists on the channel every site holds, so it says no itself
        # rather than trusting that.
        if not self.vault_password_on():
            return
        if self._page_is_private(page):
            # A private tab neither fills nor offers to save. Filling
            # would put a saved login into a page he opened precisely so
            # that it would not be him - and the watcher is not even
            # injected into that jar, so this is the second lock.
            return
        # Locked: nothing is filled, and nothing is said about it.
        #
        # A separate reason from the one above, not a duplicate of it:
        # a private tab has nothing to do with whether the vault is
        # open, and an ordinary tab over a locked vault has to be just
        # as silent. This is the quiet failure the feature stands or
        # falls on. The watcher fires on every login form on every
        # page, so anything that asked here — a box, a toast, a bar
        # across the top — would be a prompt storm the moment he opened
        # three tabs, and a prompt storm is how people learn to click
        # things away without reading them. So a locked browser fills
        # nothing and mentions nothing, and unlocking is something he
        # goes and does when he wants it: Ctrl+Shift+L, the manager, or
        # Settings.
        #
        # The page is told nothing either. Not "locked", not "there is
        # something here" — no _pw_push at all, so a site cannot learn
        # from the silence whether anything is saved for it. Locked
        # looks exactly like a vault with nothing in it, from the
        # outside.
        if self.vault_locked():
            return
        url = page.url()
        if url.scheme() not in ("http", "https"):
            return
        host = PasswordVault.normalize_host(url.host())
        if not host or host != PasswordVault.normalize_host(
                str(data.get("host", ""))):
            return
        scheme = url.scheme()
        self._pw_step_prune()             # drop half-logins that timed out
        saved = self.vault.best_for(host, scheme)
        stage = str(data.get("stage", ""))
        seen_user = str(data.get("username", ""))[:200]
        typed = bool(data.get("typed"))
        self._sync_acct()
        self._maybe_offer_accounts(page, host, scheme, stage, typed)
        if stage == "username":
            # Step one. There is no password box on screen, so nothing
            # secret is sent to the page — at most the account name.
            #
            # The account is remembered even when nothing is saved for
            # this site yet: step two of a first-ever login has no
            # username box either, so without this it would be saved
            # under a blank username — and the visit after that would
            # then fill nothing at all, because the account he types is
            # one the vault does not know. The note never leaves the
            # browser, belongs to this tab and this host, and expires.
            if not seen_user and typed:
                # The box is empty and he has typed in it: he cleared it
                # to put another account in. Volunteering the saved one
                # back is how "i cand even get a second acound in cause
                # i cand enter my email" happened. Say nothing, and
                # leave the note on the last account he chose himself.
                self._pw_push(page, "", "")
            elif (not seen_user and saved is not None
                    and len(self._saved_account_names(host, scheme)) <= 1):
                seen_user, typed = saved.get("username", ""), False
                self._pw_push(page, seen_user, "")
            else:
                self._pw_push(page, "", "")   # watch, fill nothing
            if seen_user and (saved is not None
                              or self.config.get("savePasswords", True)):
                self._pw_step_remember(page, host, scheme, seen_user, typed)
            return
        if saved is None:
            return                        # nothing saved here: stay quiet
        if stage == "password":
            entry = self._pw_entry_for(page, host, scheme, seen_user)
            if entry is None:
                self._pw_push(page, "", "")   # keep watching, fill nothing
                return
            self._pw_push(page, entry.get("username", ""),
                          entry.get("password", ""))
        else:
            self._pw_push(page, "", "")       # no login on screen yet

    def _password_submitted(self, page, data):
        """A login form was submitted. The page's real URL is
        authoritative — the host the content script reports only has
        to agree, it is never trusted on its own."""
        if not self.vault_password_on():
            return          # nothing offered, so nothing ever stored
        if self._page_is_private(page):
            return          # nothing a private tab does is ever saved
        # Locked: no save prompt either. The toast would be an offer
        # the browser cannot keep — the vault it would write to is shut
        # — and it would be an offer arriving at exactly the moment he
        # has just typed a password into a page.
        if self.vault_locked():
            return
        url = page.url()
        if url.scheme() not in ("http", "https"):
            return
        host = PasswordVault.normalize_host(url.host())
        if not host or host != PasswordVault.normalize_host(
                str(data.get("host", ""))):
            return
        username = str(data.get("username", ""))[:200]
        if not username:
            # A second-step form has no username box: the account is
            # the one step one was filled with — not necessarily on
            # this exact host, since the step may have walked down to a
            # subdomain on the way here, but on this site. A half-login
            # from anywhere else names nobody: a row saved under a name
            # he never typed on this site is one that fills for that
            # name ever after.
            step = self._pw_step_for(page, host, url.scheme())
            if step is not None:
                username = step["username"]
        self._pw_step_forget(page, host)      # the login is over
        password = str(data.get("password", ""))
        if not password or len(password) > 500:
            return
        if not self.config.get("savePasswords", True):
            return  # "offer to save passwords" is off (setup wizard/settings)
        if self.vault.is_never(host):
            return
        existing = self.vault.get(host, username)
        if existing is not None and existing.get("password") == password:
            self.vault.touch(host, username)  # freshest wins autofill
            return
        self._pw_pending = {"host": host, "scheme": url.scheme(),
                            "username": username, "password": password}
        self._password_prompt(host, username, existing is not None)

    def _password_prompt(self, host, username, update):
        """Save/Update toast. The password itself never appears in any
        label (or log) — site and username only."""
        if self._toast:
            self._hide_toast()
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        ask = self._ui_str("pwUpdateAsk" if update else "pwSaveAsk")
        self._toast_label = QLabel(
            ask.format(host) + ((" \u2014 " + username) if username else ""))
        # The generator deliberately does not appear in this prompt: it
        # fires on submit, and a new password would not be the one the
        # site just accepted. But this is the one moment he is thinking
        # about passwords at all, so it says where the generator is.
        column = QVBoxLayout()
        column.setSpacing(1)
        column.addWidget(self._toast_label)
        hint = QLabel(self._ui_str("pwGenHint"))
        hint.setStyleSheet(tint("color:#8a8a8a;font-size:11px;"))
        column.addWidget(hint)
        save = QToolButton(
            text=self._ui_str("pwUpdateBtn" if update else "pwSaveBtn"))
        close = QToolButton(text="\u2715", objectName="tabclose")
        lay.addLayout(column)
        lay.addWidget(save)
        never = None
        if not update:  # "never" only makes sense for brand-new saves
            never = QToolButton(text=self._ui_str("pwNeverBtn"))
            lay.addWidget(never)
        lay.addWidget(close)

        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(15000)
        self._toast_timer.timeout.connect(self._pw_dismiss)
        close.clicked.connect(self._pw_dismiss)
        save.clicked.connect(self._pw_save_pending)
        if never is not None:
            never.clicked.connect(self._pw_never_pending)
        self._place_toast()
        toast.show()
        toast.raise_()
        self._toast_timer.start()

    def _pw_dismiss(self):
        """Dismissed or timed out: forget the credential, save nothing."""
        self._pw_pending = None
        self._hide_toast()

    def _pw_save_pending(self):
        p = self._pw_pending
        self._pw_pending = None
        self._hide_toast()
        if not p:
            return
        vault = self.vault
        if vault.provider.eager:
            vault.set_entry(p["host"], p["scheme"], p["username"],
                            p["password"])
            return
        # a remote store means a subprocess, and a subprocess must not
        # hang off the click that dismissed the toast
        self.vault_job(
            lambda: vault.set_entry(p["host"], p["scheme"], p["username"],
                                    p["password"]),
            lambda _saved: self.bridge.vaultChanged.emit())

    def _pw_never_pending(self):
        p = self._pw_pending
        self._pw_pending = None
        self._hide_toast()
        if p:
            self.vault.never(p["host"])

    # ---- the browser's own pages, as panes over the current tab ----
    def _pane_url_fn(self, name):
        """Which URL each pane loads. Downloads, bookmarks and
        passwords go through the Browser method that mints this run's
        page key into the query; settings and history are static."""
        return {"settings": lambda: SETTINGS_PAGE,
                "history": lambda: HISTORY_PAGE,
                "downloads": self.downloads_url,
                "bookmarks": self.bookmarks_url,
                "passwords": self.passwords_url}[name]

    def open_pane(self, name, started=None):
        """Bring one of our own pages up over the current tab. Built on
        first use, kept around afterwards.

        Exactly one pane is ever on screen: opening a second dismisses
        the first rather than stacking on top of it, so Esc and the ✕
        always mean the pane he is looking at.

        `started` is the caller's stopwatch for BROWSER_TIMING=1 - only
        open_settings keeps one."""
        pane = self._panes.get(name)
        if pane is None:
            pane = self._panes[name] = PagePane(
                self, name, self._pane_url_fn(name))
            if started is not None:
                _timing("pane built", started)
        if self._pane is not None and self._pane is not pane:
            self._pane.dismiss()
        self._pane = pane
        # an Esc still waiting on the pane that was here is not about
        # this one
        self._pane_escape_forget()
        self._pane_esc.setEnabled(True)
        pane.open(started)

    def _pane_escape(self):
        """Esc while a pane is up. The shortcut gets the key before the
        page can, so ask the page what Esc means to it right now — a
        password editor half typed, a bookmark being renamed, a
        settings search box with something in it all want it first —
        and take the pane down only when the answer is no.

        The question is never allowed to hang. A page that has stopped
        answering is closed over anyway once PANE_ESC_MS is up, and a
        second Esc while one is still in flight closes at once, so
        silence costs a quarter of a second and never the way out."""
        pane = self._pane
        if pane is None or not pane.isVisible():
            return
        if self._esc_timer is not None:   # asked already; he pressed again
            self._pane_escape_close(self._esc_turn)
            return
        self._esc_turn += 1
        turn = self._esc_turn
        timer = self._esc_timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=turn: self._pane_escape_close(t))
        timer.start(PANE_ESC_MS)
        pane.view.page().runJavaScript(
            "(window.__paneEsc && window.__paneEsc()) ? 1 : 0",
            lambda took, t=turn: self._pane_escape_answer(t, took))

    def _pane_escape_answer(self, turn, took):
        """What the page said. A truthy answer means it did something
        contextual with the key and the pane stays; anything else, and
        the pane goes. An answer belonging to an older Esc is dropped —
        the pane it was about is not on screen any more."""
        if turn != self._esc_turn or self._esc_timer is None:
            return
        if took:
            self._esc_timer.stop()
            self._esc_timer = None
            return
        self._pane_escape_close(turn)

    def _pane_escape_close(self, turn):
        if turn != self._esc_turn or self._esc_timer is None:
            return
        self.close_pane()

    def _pane_escape_forget(self):
        """Drop any Esc still waiting on an answer. The pane it was
        asked about is not the one on screen any more, so neither the
        answer nor the fallback may act on what is."""
        self._esc_turn += 1
        if self._esc_timer is not None:
            self._esc_timer.stop()
            self._esc_timer = None

    def close_pane(self):
        """Whatever pane is up goes down. Safe to call when none is."""
        pane, self._pane = self._pane, None
        self._pane_esc.setEnabled(False)
        self._pane_escape_forget()
        if pane is not None:
            pane.dismiss()

    def toggle_pane(self, name):
        """The shortcut that opened a pane closes it again: with the
        pane covering the window it is the obvious way back out."""
        if self.pane_open(name):
            self.close_pane()
        else:
            self.open_pane(name)

    def pane_open(self, name=None):
        """Is a pane up — that one, or any at all?"""
        pane = self._pane
        if pane is None or not pane.isVisible():
            return False
        return name is None or pane.name == name

    def leave_pane(self, url):
        """A link inside a pane that points somewhere else: the pane
        steps aside and the destination opens as a proper tab. Deferred
        a tick — this comes out of the navigation the pane just
        refused."""
        self.close_pane()
        # url=None would not mean the start page to new_tab — it means
        # the page he set for new tabs, which is how "Re-run setup"
        # used to land on his own new-tab page with no wizard on it.
        # The start page is asked for by name, as home.
        if _same_page(url, START_PAGE):
            QTimer.singleShot(0, lambda: self.new_tab(home=QUrl(START_PAGE)))
        else:
            target = url.toString()
            QTimer.singleShot(0, lambda: self.new_tab(url=target))

    def open_settings(self):
        """A pane like the rest, but the only one with a stopwatch on
        it: BROWSER_TIMING=1 prints a line per phase of opening
        Settings, the slowest page the browser has of its own."""
        started = time.perf_counter()
        if TIMING:
            print("[timing] ---- Settings (page.* from the page's own start)",
                  file=sys.stderr, flush=True)
        self.open_pane("settings", started)
        _timing("open_settings", started)

    def open_history(self):
        """Ctrl+H, and settings' "View history". A pane like the rest:
        history is something he glances at, not a place he browses to,
        and it used to cost him a tab and a history entry of its own
        every time — the page recording the visit that opened it."""
        self.open_pane("history")

    def toggle_history(self):
        """Ctrl+H both ways."""
        self.toggle_pane("history")

    def close_settings(self):
        """Only ever asked to close the settings pane, but there is
        only one pane at a time, so this is close_pane."""
        self.close_pane()

    def toggle_settings(self):
        self.toggle_pane("settings")

    def settings_open(self):
        return self.pane_open("settings")

    def download_dir(self, create=True):
        """Where downloads land: the folder he picked in settings, or
        ~/Downloads when he picked none (or picked one that has since
        gone away). create=False only answers the question - merely
        looking at the setting must not conjure the folder up."""
        chosen = str(self.config.get("downloadDir") or "").strip()
        if chosen:
            path = Path(chosen).expanduser()
            if not create:
                return path
            try:
                path.mkdir(parents=True, exist_ok=True)
                return path
            except OSError:
                pass
        return DOWNLOAD_DIR

    def _all_profiles(self, profile=None):
        """Every cookie jar there is — the main one and every virtual
        browser's. Passing one profile targets just that one, which is
        how _make_profile configures a jar that is not on the list yet."""
        if profile is not None:
            return [profile]
        return [self.profile] + list(self.session_profiles.values())

    def apply_web_attributes(self, profile=None):
        """The engine switches that live on a profile. Every one of them
        has to reach every profile, or a setting would hold for the main
        virtual browser and quietly not for the others."""
        c = self.config
        attr = QWebEngineSettings.WebAttribute
        for prof in self._all_profiles(profile):
            s = prof.settings()
            # auto-darken pages that have no dark theme of their own —
            # see force_dark_on for when that is, and _url_changed for
            # the other half of it, which is the half that decides
            s.setAttribute(attr.ForceDarkMode, self.force_dark_on())
            s.setAttribute(attr.ScrollAnimatorEnabled,
                           bool(c.get("smoothScroll", True)))
            # off by default: calls should ring without a click first
            s.setAttribute(attr.PlaybackRequiresUserGesture,
                           bool(c.get("blockAutoplay", False)))
            # the internal PDF viewer is a Chromium plugin: without
            # PluginsEnabled the flag alone does nothing and PDFs keep
            # being downloaded
            pdf = bool(c.get("pdfViewer", False))
            s.setAttribute(attr.PluginsEnabled, pdf)
            s.setAttribute(attr.PdfViewerEnabled, pdf)
        # and the half of force-dark that lives on the page, for the
        # tabs that are already open. Only when this is everything —
        # a single jar being configured has no tabs of its own yet.
        if profile is None and getattr(self, "tabs", None) is not None:
            self._refresh_page_force_dark()

    def spell_language(self):
        """The dictionary to check against: the one he picked, or the
        browser's own language when he never picked one (German browser,
        German spell-check) falling back to English."""
        picked = str(self.config.get("spellCheckLang") or "").strip()
        codes = [code for code, _ in SPELL_LANGUAGES]
        if picked in codes:
            return picked
        lang = str(self.config.get("translateLang", "de")).lower()
        base = lang.split("-")[0]
        for code in codes:
            if code.lower() == lang or code.split("-")[0] == base:
                return code
        return "en-US"

    def apply_spellcheck(self, profile=None):
        """Spell-check underlining in text boxes, in one language."""
        on = bool(self.config.get("spellCheck", False))
        lang = self.spell_language()
        for prof in self._all_profiles(profile):
            prof.setSpellCheckEnabled(on)
            prof.setSpellCheckLanguages([lang] if on else [])

    def apply_font_size(self):
        px = int(self.config.get("minFont", 0) or 0)
        for profile in [self.profile] + list(self.session_profiles.values()):
            profile.settings().setFontSize(
                QWebEngineSettings.FontSize.MinimumFontSize, px)

    # ---- inspector (Chromium DevTools over remote debugging) ----
    def toggle_inspector(self):
        view = self.current()
        if view is None or not hasattr(view, "page"):
            return
        existing = getattr(view, "_devtools", None)
        if existing is not None:
            existing.close()
            view._devtools = None
            return
        # the embedded devtools:// frontend fails to load on some Qt
        # builds; the remote-debugging server serves the same DevTools
        # over http, which works everywhere
        cur = view.url().toString()
        reply = self._nam.get(QNetworkRequest(
            QUrl("http://127.0.0.1:9222/json/list")))
        reply.finished.connect(
            lambda r=reply, v=view, u=cur: self._open_inspector(r, v, u))

    def _open_inspector(self, reply, view, cur_url):
        base = "http://127.0.0.1:9222"
        frontend = base + "/"  # fallback: pick-a-page list
        try:
            targets = json.loads(bytes(reply.readAll()).decode())
            match = next((t for t in targets if t.get("type") == "page"
                          and t.get("url") == cur_url), None)
            match = match or next((t for t in targets
                                   if t.get("type") == "page"), None)
            if match and match.get("devtoolsFrontendUrl"):
                fe = match["devtoolsFrontendUrl"]
                frontend = fe if fe.startswith("http") else base + fe
        except Exception:
            pass
        reply.deleteLater()
        dt = QWebEngineView()
        dt.setWindowTitle("Inspector")
        dt.resize(1000, 640)
        dt.setWindowIcon(self.windowIcon())
        dt.load(QUrl(frontend))
        dt.destroyed.connect(lambda: setattr(view, "_devtools", None))
        dt.show()
        view._devtools = dt

    # ---- proxy switcher (SwitchyOmega-style) ----
    def _migrate_proxy(self):
        _migrate_proxy_config(self.config)

    def _apply_proxy_profile(self, name):
        """QtNetwork side (search suggestions, inspector fetch). Never
        app-wide: an application proxy would override the launch flags
        inside the web engine and freeze there, so it lives on the
        QNAM alone."""
        prof = next((p for p in self.config.get("proxyProfiles", [])
                     if p.get("name") == name), None)
        if prof is None:  # "system", "direct" or a deleted profile
            kind = (QNetworkProxy.ProxyType.NoProxy if name == "direct"
                    else QNetworkProxy.ProxyType.DefaultProxy)
            self._nam.setProxy(QNetworkProxy(kind))
            return
        kind = (QNetworkProxy.ProxyType.Socks5Proxy
                if prof.get("type") == "socks5"
                else QNetworkProxy.ProxyType.HttpProxy)
        proxy = QNetworkProxy(kind, prof.get("host", ""),
                              int(prof.get("port") or 0))
        if prof.get("user"):
            proxy.setUser(prof["user"])
            proxy.setPassword(prof.get("password", ""))
        self._nam.setProxy(proxy)

    def apply_proxy(self):
        self._migrate_proxy()
        # rules route per-site inside Chromium (the PAC baked in at
        # launch); QtNetwork follows the default mode
        self._apply_proxy_profile(self.config.get("activeProxy", "system"))
        if self._proxy_restart_needed():
            self._show_restart_toast("Proxy change applies after a restart")
        self._update_proxy_btn()

    def _proxy_restart_needed(self):
        """The web engine reads its proxy flags only at startup:
        true when the config drifted from what this process was
        launched with."""
        return (_PROXY_FLAGS_AT_LAUNCH is not None
                and _proxy_launch_flags(self.config)
                != _PROXY_FLAGS_AT_LAUNCH)

    def _proxy_auth(self, url, authenticator, proxy_host):
        # Chromium asks for proxy credentials itself; answer from the
        # matching profile (QNetworkProxy user/password never reach it)
        host = proxy_host.rsplit(":", 1)[0]
        for p in self.config.get("proxyProfiles", []):
            if p.get("user") and p.get("host") in (proxy_host, host):
                authenticator.setUser(p["user"])
                authenticator.setPassword(p.get("password", ""))
                return

    def _show_restart_toast(self, message):
        """Update-toast styling, but for settings Chromium only reads
        at launch; stays until dismissed or acted on."""
        if self._toast:
            return
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self._toast_label = QLabel(message)
        restart = QToolButton(text="Restart now")
        close = QToolButton(text="\u2715", objectName="tabclose")
        lay.addWidget(self._toast_label)
        lay.addWidget(restart)
        lay.addWidget(close)

        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)
        close.clicked.connect(self._hide_toast)
        restart.clicked.connect(self.restart)

        self._place_toast()
        toast.show()
        toast.raise_()

    def _proxy_profiles(self):
        base = [{"name": "system", "label": "System", "builtin": True},
                {"name": "direct", "label": "Direct", "builtin": True}]
        return base + [dict(p, label=p["name"], builtin=False)
                       for p in self.config.get("proxyProfiles", [])]

    def _proxy_menu(self):
        menu = QMenu(self)
        active = self.config.get("activeProxy", "system")
        for p in self._proxy_profiles():
            mark = "\u2713 " if p["name"] == active else "    "
            menu.addAction(mark + p["label"]).triggered.connect(
                lambda _, n=p["name"]: self.set_active_proxy(n))
        menu.addSeparator()
        menu.addAction("Manage profiles\u2026").triggered.connect(
            self.open_settings)
        menu.exec(self._menu_anchor(self._proxy_btn))

    def set_active_proxy(self, name):
        self.config["activeProxy"] = name
        self.save_config()
        self.apply_proxy()

    def _update_proxy_btn(self):
        btn = getattr(self, "_proxy_btn", None)
        if btn is None:
            return
        active = self.config.get("activeProxy", "system")
        label = {"system": "System", "direct": "Direct"}.get(active, active)
        rules = self._has_proxy_rules()
        btn.setToolTip("Proxy: " + label
                       + (" + site rules" if rules else ""))
        # tinted whenever a proxy can actually route traffic
        btn.setStyleSheet(tint(
            "QToolButton { color: %s; }" %
            ("#a6e3a1" if rules or active not in ("system", "direct")
             else "#cdd6f4")))

    def _has_proxy_rules(self):
        return any((r.get("pattern") or "").strip()
                   for r in (self.config.get("proxyAuto") or {})
                   .get("rules", []))

    def apply_language(self):
        """The chosen language reaches websites (Accept-Language, so
        Google speaks it too) and the browser's own pages."""
        lang = self.config.get("translateLang", "de")
        accept = lang if lang.startswith("en") else lang + ",en"
        for profile in [self.profile] + list(self.session_profiles.values()):
            profile.setHttpAcceptLanguage(accept)
        # the tooltips in the chrome are in his language too
        self.relabel_toolbar()
        # no dictionary of his own picked means the spell checker
        # follows the browser's language, so it has to move along too
        self.apply_spellcheck()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "url") and w.url().scheme() == "file":
                w.reload()
        if self._pane is not None and self._pane.isVisible():
            self._pane.view.load(self._pane.page_url())
        self._update_private_marks()

    def refresh_google_scripts(self):
        """Swap the Google white/black script in every cookie jar."""
        for profile in [self.profile] + list(self.session_profiles.values()):
            scripts = profile.scripts()
            for old in scripts.find("google-mode"):
                scripts.remove(old)
            scripts.insert(self._google_script())

    def refresh_theme_scripts(self):
        """Swap the painter in every cookie jar, so the next page he
        opens is in the new colours too."""
        for profile in self._all_profiles():
            scripts = profile.scripts()
            for old in scripts.find("theme"):
                scripts.remove(old)
            scripts.insert(self._theme_script())

    def _own_open_pages(self):
        """The browser's own pages that are open right now — every tab
        showing one, plus every pane that has been built, which is not
        a tab. A pane that has been opened once is kept around hidden;
        repainting it while it is down costs nothing and means it does
        not come back up in last week's colours."""
        views = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "page") and hasattr(w, "url") \
                    and w.url().scheme() == "file":
                views.append(w)
        for pane in (getattr(self, "_panes", None) or {}).values():
            if getattr(pane, "view", None) is not None:
                views.append(pane.view)
        return views

    def _restyle_widgets(self):
        """The few widgets that carry a stylesheet of their own instead
        of living off the application's."""
        completer = getattr(self, "completer", None)
        if completer is not None:
            completer.popup().setStyleSheet(tint(COMPLETER_QSS))
        if getattr(self, "sesslay", None) is not None:
            self._update_session_bar()
        self._update_proxy_btn()
        bar = getattr(self, "tabs", None)
        if bar is not None:
            bar.tabBar().update()

    def apply_theme(self, name, save=True):
        """A theme lands everywhere at once and nothing has to be
        restarted for it: the window's sheet, the widgets that keep one
        of their own, the jars that paint the next page, and every page
        of ours that is already open. The single exception is what
        websites are told about dark mode — a launch flag; Settings
        offers the restart when that one actually changed."""
        name = _select_theme(name)
        if save:
            self.config["theme"] = name
            self.save_config()
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme_style(name))
        self.refresh_theme_scripts()
        self._restyle_widgets()
        # force-dark and a light theme cannot both be right
        self.apply_web_attributes()
        payload = json.dumps(json.dumps(theme_payload(name)))
        for view in self._own_open_pages():
            view.page().runJavaScript(
                "window.__applyTheme && window.__applyTheme(%s)" % payload,
                MAIN_WORLD_ID)

    def refresh_password_script(self):
        """Installing or removing Vault Password takes effect on the
        next page he opens, not the next time he starts the browser.

        Every cookie jar, the same as the Google script: a setting that
        held for the main virtual browser and quietly not for the
        others would be worse than one that needed a restart."""
        for profile in [self.profile] + list(self.session_profiles.values()):
            scripts = profile.scripts()
            for old in scripts.find("password-watch"):
                scripts.remove(old)
            if self.vault_password_on() and not profile.isOffTheRecord():
                scripts.insert(self._password_script())

    @staticmethod
    def _plugin_glob_to_regex(seg):
        """Glob segment -> regex source: * -> .*, rest escaped
        ( / escaped too, for the JS /.../ literal)."""
        out = []
        for ch in seg:
            if ch == "*":
                out.append(".*")
            elif ch == "/":
                out.append(r"\/")
            else:
                out.append(re.escape(ch))
        return "".join(out)

    def _plugin_pattern_to_regex(self, pattern):
        """Chrome-style match pattern -> regex on the FULL url, matched
        by component so `*.x.com` covers x.com and its subdomains and a
        stray `.x.com/` in a path can't trigger it."""
        m = re.match(r"^(\*|https?|file|ftp)://([^/]*)(/.*)?$", pattern)
        if not m:  # not a scheme://host/path pattern: fall back to a glob
            return "^%s$" % self._plugin_glob_to_regex(pattern)
        scheme, host, path = m.group(1), m.group(2), m.group(3) or "/*"
        scheme_re = r"https?" if scheme == "*" else re.escape(scheme)
        if host == "*":
            host_re = r"[^/]+"
        elif host.startswith("*."):
            host_re = r"(?:[^/]+\.)?" + re.escape(host[2:])
        else:
            host_re = self._plugin_glob_to_regex(host)
        path_re = self._plugin_glob_to_regex(path)
        return r"^%s:\/\/%s%s$" % (scheme_re, host_re, path_re)

    def _plugin_wrap(self, source):
        """Honor // @match and // @include lines: the script only runs
        on matching URLs (any pattern may match). None = everywhere."""
        patterns = re.findall(r"^\s*//\s*@(?:match|include)\s+(\S+)",
                              source, re.MULTILINE)
        if not patterns:
            return source
        regex = "|".join(self._plugin_pattern_to_regex(p) for p in patterns)
        return "if (new RegExp(%s).test(location.href)) {\n%s\n}" % (
            json.dumps(regex), source)

    def _load_plugins(self):
        """Every *.user.js in the plugins folder becomes an injectable
        script; the folder is created on first start."""
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return []
        scripts = []
        for f in sorted(self.plugins_dir.glob("*.user.js")):
            try:
                source = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            script = QWebEngineScript()
            # source first: setSourceCode parses ==UserScript== metadata
            # and would overwrite the name / injection point set before
            script.setSourceCode(self._plugin_wrap(source))
            script.setName("plugin-" + f.name)
            script.setInjectionPoint(
                QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            scripts.append(script)
        return scripts

    def _plugin_toast(self, name):
        self.bridge.updateFinished.emit("Plugin installed: " + name)
        self._show_toast()
        if self._toast:
            self._toast_label.setText("Plugin installed ✓")

    def _plugin_downloaded(self, request):
        if request.isFinished() and request.state() == \
                request.DownloadState.DownloadCompleted:
            self.reload_plugins()
            self._plugin_toast(request.downloadFileName())

    def _safe_plugin_name(self, filename):
        base = re.sub(r"[^\w.-]", "_", Path(filename).name)
        if not base.endswith(".user.js"):
            base = base.removesuffix(".js") + ".user.js"
        return base

    def save_plugin(self, filename, source):
        """Write a userscript into the plugins folder and activate it."""
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            (self.plugins_dir / self._safe_plugin_name(filename)).write_text(
                source, encoding="utf-8")
        except OSError:
            return False
        self.reload_plugins()
        self._plugin_toast(self._safe_plugin_name(filename))
        return True

    def install_starter(self, plugin_id):
        entry = STARTER_PLUGINS.get(plugin_id)
        if entry is None:
            return False
        return self.save_plugin(plugin_id + ".user.js", entry[2])

    def add_plugin_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add plugin", str(Path.home()),
            "Userscripts (*.user.js *.js)")
        if not path:
            return
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self.save_plugin(Path(path).name, source)

    def reload_plugins(self):
        """Re-read the plugins folder into every cookie jar."""
        # the one thing Settings shows that is not in the config: a
        # plugin installed from a tab has to reach a pane that is
        # sitting closed (see _page_data_changed)
        _page_data_changed()
        old_names = self.plugin_script_names
        self.plugin_scripts = self._load_plugins()
        self.plugin_script_names = [s.name() for s in self.plugin_scripts]
        for profile in [self.profile] + list(self.session_profiles.values()):
            scripts = profile.scripts()
            for name in old_names:
                for stale in scripts.find(name):
                    scripts.remove(stale)
            for script in self.plugin_scripts:
                scripts.insert(script)

    def _profile_for(self, group, session="main", private=False):
        """Cookies are per virtual browser: every tab in it — grouped
        or not — shares that browser's jar. A private tab is in none
        of them: it is in the one jar that writes nothing down."""
        if private:
            return self.private_profile()
        return self._session_profile(session or "main")

    def private_profile(self, create=True):
        """The single off-the-record jar every private tab shares.

        One jar, not one per tab, so two private tabs are one browsing
        context — a login in the first is still a login in the second,
        which is what anybody expects of them — while no normal tab
        can see any of it. It lives in session_profiles so that every
        "for every cookie jar" loop reaches it too."""
        profile = self.session_profiles.get(PRIVATE_SESSION)
        if profile is None and create:
            profile = self._make_profile(None)
            self.session_profiles[PRIVATE_SESSION] = profile
        return profile

    def _drop_private_profile(self):
        """The last private tab has closed: the jar goes, and what it
        was holding in memory goes with it. What was allowed in a
        private tab is forgotten here too."""
        if self.private_tabs():
            return
        self._private_perms.clear()
        profile = self.session_profiles.pop(PRIVATE_SESSION, None)
        if profile is not None:
            # a turn later: the tab's own page is on the deferred-delete
            # queue and has to go first, or the profile would be pulled
            # out from under a page still holding it
            QTimer.singleShot(0, profile.deleteLater)

    def _session_profile(self, sid):
        if sid == "main":
            return self.profile
        if sid not in self.session_profiles:
            self.session_profiles[sid] = self._make_profile("browser-s-" + sid)
        return self.session_profiles[sid]

    def _sync_profile(self, view):
        """Keep a tab in its virtual browser's cookie jar (no-op unless
        it somehow ended up in the wrong one)."""
        want = self._profile_for(self._group_of(view),
                                 getattr(view, "session", "main"),
                                 getattr(view, "private", False))
        if view.page().profile() is want:
            return
        url = view.url()
        target = url if url.toString() else QUrl(getattr(view, "_requested", ""))
        view.attach_profile(want)
        view.load(target if target.toString() else START_PAGE)

    def _download(self, request):
        # the click that started this was a navigation as far as the
        # page was concerned, and it swapped channels for a document
        # that is never coming: give the page its own bridge back
        page = request.page()
        if isinstance(page, WebPage):
            page.restore_trust()
        # a .user.js is a plugin: install it straight into the folder
        name = request.downloadFileName()
        if name.endswith(".user.js") and not self._page_is_private(page):
            # ...but never out of a private tab. A userscript puts
            # itself in the plugins folder and runs on every page from
            # then on, which is about as far from "nothing is kept" as a
            # download gets: there it comes down as an ordinary file.
            request.setDownloadDirectory(str(self.plugins_dir))
            request.setDownloadFileName(name)
            request.accept()
            request.isFinishedChanged.connect(
                lambda r=request: self._plugin_downloaded(r))
            return
        if self.config.get("askDownload"):
            path, _ = QFileDialog.getSaveFileName(
                self, "Save file",
                str(self.download_dir() / request.downloadFileName()))
            if not path:
                request.cancel()
                return
            request.setDownloadDirectory(str(Path(path).parent))
            request.setDownloadFileName(Path(path).name)
            request.accept()
            self._show_download(request)
            return
        request.setDownloadDirectory(str(self.download_dir()))
        request.setDownloadFileName(
            self._unique_download_name(request.downloadFileName(),
                                       hold=self._page_is_private(page)))
        request.accept()
        self._show_download(request)

    def _show_download(self, request):
        """A toast in the download bar plus an entry on the downloads
        page — except from a private tab, which gets the toast and no
        entry. The file itself is what he asked for and it lands on disk
        like any other; the list of what he has fetched is a record, and
        a private tab keeps none."""
        widget = DownloadWidget(request, self._dismiss_download)
        self.dllay.insertWidget(self.dllay.count() - 1, widget)
        self.dlbar.show()
        if not self._page_is_private(self._download_page(request)):
            self._track_download(request)

    @staticmethod
    def _download_page(request):
        try:
            return request.page()
        except (AttributeError, RuntimeError):
            return None

    # ---- downloads page ----
    def _unique_download_name(self, name, directory=None, hold=False):
        """Never overwrite: name.pdf -> name (1).pdf. A download still in
        flight only holds name.pdf.download, so the running ones are
        asked too instead of letting both land on the same file.

        A name the browser minted for a file of its own stays that
        record's for good, even if the render failed and left nothing on
        disk: a failed row that later points at somebody else's file is
        exactly the confusion the name is there to prevent.

        hold=True is a file out of a private tab. It gets no row, so the
        list of rows cannot say the name is taken - a normal download
        starting a second later would be handed the same one and the two
        would land on top of each other. The name is held here instead,
        for the rest of the run: it costs a string, and it is the same
        promise every other minted name gets."""
        directory = Path(directory) if directory else self.download_dir()
        stem, suffix = Path(name).stem, Path(name).suffix
        busy = {e["name"] for e in self.downloads
                if e["state"] == "active" or e.get("local")} | self._dl_held
        n = 1
        while name in busy or (directory / name).exists():
            name = f"{stem} ({n}){suffix}"
            n += 1
        if hold:
            self._dl_held.add(name)
        return name

    def _add_download_entry(self, entry, record=True):
        """Everything the browser puts on disk — fetched or produced —
        goes on this one list, so there is one downloads.json and one
        downloads page rather than a second notion of the same thing.

        record=False is a private tab: the file is written and the toast
        follows it along the bottom of the window, but no row is kept.
        It is still given an id, because the toast is keyed on one."""
        entry["id"] = self._dl_seq
        self._dl_seq += 1
        if not record:
            return entry
        self.downloads.append(entry)
        while len(self.downloads) > DOWNLOADS_MAX:
            oldest = next((e for e in self.downloads
                           if e.get("state") != "active"), None)
            if oldest is None:
                break
            self.downloads.remove(oldest)
        return entry

    def _track_download(self, request):
        """Follow a running download until it lands, then keep the record."""
        entry = self._add_download_entry(
            {"name": request.downloadFileName(),
             "dir": request.downloadDirectory(),
             "url": request.url().toString(), "t": int(time.time()),
             "state": "active", "received": 0, "size": 0, "paused": False})
        self.dl_active[entry["id"]] = request
        request.receivedBytesChanged.connect(
            lambda *_, r=request, e=entry: self._download_progress(r, e))
        request.totalBytesChanged.connect(
            lambda *_, r=request, e=entry: self._download_progress(r, e))
        request.isPausedChanged.connect(
            lambda *_, r=request, e=entry: e.update(paused=r.isPaused()))
        request.stateChanged.connect(
            lambda *_, r=request, e=entry: self._download_state(r, e))
        self.bridge.downloadsChanged.emit()

    def _download_progress(self, request, entry):
        if entry["state"] != "active":
            return  # a trailing update after the end would zero the record
        entry["received"] = request.receivedBytes()
        entry["size"] = request.totalBytes()

    def _download_state(self, request, entry):
        St = request.DownloadState
        state = request.state()
        if state == St.DownloadInProgress or entry["state"] != "active":
            return  # paused, or an end we already wrote down
        entry["state"] = {St.DownloadCompleted: "done",
                          St.DownloadCancelled: "cancelled"}.get(state,
                                                                 "failed")
        entry["name"] = request.downloadFileName()
        entry["dir"] = request.downloadDirectory()
        # Qt reports 0 bytes once a download was cancelled: keep the
        # furthest point the file actually reached
        entry["received"] = max(entry["received"], request.receivedBytes())
        entry["size"] = (request.totalBytes() or entry["received"]
                         if entry["state"] == "done" else entry["received"])
        entry["paused"] = False
        self.dl_active.pop(entry["id"], None)
        self.save_downloads()
        self.bridge.downloadsChanged.emit()

    def downloads_data(self):
        """What the downloads page renders; a file gone from disk gets its
        open actions greyed out instead of an error."""
        items = []
        for entry in self.downloads:
            item = dict(entry)
            folder, name = entry.get("dir") or "", entry.get("name") or ""
            try:
                item["dirExists"] = bool(folder) and Path(folder).is_dir()
                item["exists"] = (bool(folder) and bool(name)
                                  and (Path(folder) / name).is_file())
            except OSError:
                item["exists"] = item["dirExists"] = False
            items.append(item)
        return items

    def _download_entry(self, dl_id):
        return next((e for e in self.downloads if e.get("id") == dl_id), None)

    def open_download(self, dl_id, folder=False):
        entry = self._download_entry(dl_id)
        if entry is None:
            return
        if not entry.get("dir") or not entry.get("name"):
            return
        path = Path(entry["dir"]) / entry["name"]
        target = path.parent if folder else path
        try:
            if not (target.is_dir() if folder else target.is_file()):
                return  # deleted behind our back, or never a file
        except OSError:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def remove_download(self, dl_id):
        entry = self._download_entry(dl_id)
        if entry is None or entry.get("state") == "active":
            return
        self.downloads.remove(entry)
        self.save_downloads()

    def clear_downloads(self):
        self.downloads = [e for e in self.downloads
                          if e.get("state") == "active"]
        self.save_downloads()

    def save_downloads(self):
        _page_data_changed()
        try:
            DOWNLOADS_FILE.parent.mkdir(parents=True, exist_ok=True)
            done = [e for e in self.downloads if e.get("state") != "active"]
            DOWNLOADS_FILE.write_text(json.dumps(done[-DOWNLOADS_MAX:]))
        except OSError:
            pass

    # ---- bookmarks ----
    def save_bookmarks(self):
        """A change worth showing everywhere: to disk, then the bar, the
        star and any manager page that is open."""
        self.write_bookmarks()
        self.rebuild_bookmarks_bar()
        self._sync_star()
        self.bridge.bookmarksChanged.emit()

    def write_bookmarks(self):
        _page_data_changed()
        try:
            BOOKMARKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            # written whole: the cap is kept on the way in, so
            # nothing here may silently fall off the end
            BOOKMARKS_FILE.write_text(json.dumps(self.bookmarks))
        except OSError:
            pass

    def _bookmark_folder_ids(self):
        return {e["id"] for e in self.bookmarks if e["type"] == "folder"}

    def _bookmark_kids(self, fid):
        """What is directly inside a folder (0 = the bar itself), in the
        order he put it in."""
        return [e for e in self.bookmarks if e["parent"] == fid]

    def _bookmark_subtree(self, fid):
        """A folder's id and every id under it, however deep.

        Walked level by level with a set of what has been seen, never by
        recursion: load_bookmarks promises a tree, and this does not
        have to be told twice to come back even so."""
        found, edge = {fid}, {fid}
        while edge:
            step = set()
            for entry in self.bookmarks:
                if entry["parent"] in edge and entry["id"] not in found:
                    found.add(entry["id"])
                    if entry["type"] == "folder":
                        step.add(entry["id"])
            edge = step
        return found

    def bookmark_folder_tree(self, parent=0, depth=0):
        """Every folder, in the order it reads on the screen, each with
        how deep it sits — what a list of folders to pick from needs."""
        out = []
        for entry in self.bookmarks:
            if entry["type"] != "folder" or entry["parent"] != parent:
                continue
            out.append((entry, depth))
            if depth < BOOKMARKS_DEPTH:
                out.extend(self.bookmark_folder_tree(entry["id"], depth + 1))
        return out

    def _bookmark_by_id(self, bid):
        for entry in self.bookmarks:
            if entry["id"] == bid:
                return entry
        return None

    def _bookmark_for(self, url):
        """The bookmark for this address, if there is one."""
        key = _bookmark_key(url)
        if not key:
            return None
        for entry in self.bookmarks:
            if entry["type"] == "link" and _bookmark_key(entry["url"]) == key:
                return entry
        return None

    def _bookmarkable(self, view=None):
        """The address the star acts on, or an empty QUrl. Only real web
        pages: bookmarking one of our own file: pages would preserve a
        cache-busting query (and this run's page key) forever."""
        view = self.current() if view is None else view
        if view is None or self._is_header(view) or not hasattr(view, "url"):
            return QUrl()
        url = view.url()
        return url if url.scheme() in ("http", "https") else QUrl()

    def _place_star(self):
        btn = getattr(self, "starbtn", None)
        if btn is None:
            return
        btn.move(self.urlbar.width() - btn.width() - 7,
                 max(0, (self.urlbar.height() - btn.height()) // 2))

    def _sync_star(self):
        """Filled star = this page is bookmarked."""
        btn = getattr(self, "starbtn", None)
        if btn is None:
            return
        url = self._bookmarkable()
        entry = self._bookmark_for(url) if not url.isEmpty() else None
        btn.setEnabled(not url.isEmpty())
        btn.setText("\u2605" if entry else "\u2606")
        btn.setToolTip(self._ui_str("bmRemove" if entry else "bmAdd"))
        if btn.property("on") != bool(entry):
            btn.setProperty("on", bool(entry))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def toggle_bookmark(self):
        """Ctrl+D / the star: add this page, or drop it if it is already
        in there."""
        url = self._bookmarkable()
        if url.isEmpty():
            return
        entry = self._bookmark_for(url)
        if entry is None:
            self.add_bookmark_here(0)
            return
        self.bookmarks.remove(entry)
        self.save_bookmarks()

    def add_bookmark_here(self, parent=0):
        """This page, into the folder he pointed at.

        Edge's star opens a little card with a Folder box on it, and
        this is that card without the card: he picks the folder in the
        menu he is already in. A page that is already bookmarked is
        moved into the folder rather than copied — asking for it to be
        in there and getting a second one of it is nobody's meaning."""
        url = self._bookmarkable()
        if url.isEmpty():
            return
        parent = _sane_number(parent)
        if parent not in self._bookmark_folder_ids():
            parent = 0
        entry = self._bookmark_for(url)
        if entry is not None:
            if entry["parent"] != parent:
                self.move_bookmark(entry["id"], parent, BOOKMARKS_MAX)
            return
        if len(self.bookmarks) >= BOOKMARKS_MAX:
            return  # full: refuse it now rather than lose it later
        view = self.current()
        title = (self.tabs.tabText(self.tabs.indexOf(view)) or "").strip()
        if title in ("", "New tab"):
            title = url.host() or url.toString()
        self.bookmarks.append({
            "id": max((e["id"] for e in self.bookmarks), default=0) + 1,
            "type": "link",
            "title": title[:300],
            "url": url.toString(),
            "icon": _icon_data(view.icon()),
            "parent": parent,
            "t": int(time.time()),
        })
        self.save_bookmarks()

    def open_bookmark(self, entry, new_tab=False):
        """Never loads anything but http(s): bookmarks.json is a file on
        disk and a hand-written javascript: entry must stay inert.

        The manager is a pane over the current tab, and "open here"
        means that tab — so the pane steps aside first, or the page he
        asked for would arrive behind a screen he cannot see past."""
        url = QUrl(entry.get("url") or "")
        if url.scheme() not in ("http", "https"):
            return
        self.close_pane()
        view = self.current()
        if new_tab or view is None or self._is_header(view):
            self.new_tab(url=url.toString())
        else:
            view.load(url)

    def open_bookmark_id(self, bid, new_tab=False):
        entry = self._bookmark_by_id(bid)
        if entry is not None and entry["type"] == "link":
            self.open_bookmark(entry, new_tab=new_tab)

    def update_bookmark(self, bid, title, url):
        entry = self._bookmark_by_id(bid)
        if entry is None:
            return
        title = str(title or "").strip()[:300]
        if entry["type"] == "link":
            text = _clean_bookmark_url(url)
            if text and text != entry["url"]:
                entry["url"] = text
                entry["icon"] = ""  # a new address, a new favicon
        entry["title"] = title or entry["title"]
        self.save_bookmarks()

    def remove_bookmark(self, bid):
        entry = self._bookmark_by_id(bid)
        if entry is None:
            return
        # a folder goes with everything in it, all the way down —
        # folders inside it and their contents too, so nothing is left
        # pointing at a folder that is not there any more
        doomed = (self._bookmark_subtree(entry["id"])
                  if entry["type"] == "folder" else {entry["id"]})
        self.bookmarks = [e for e in self.bookmarks if e["id"] not in doomed]
        self.save_bookmarks()

    def move_bookmark(self, bid, parent, index):
        """Reorder within a folder and move between folders, in one:
        `index` is the seat among the new siblings (clamped)."""
        entry = self._bookmark_by_id(bid)
        if entry is None:
            return
        parent = _sane_number(parent)
        if parent not in self._bookmark_folder_ids():
            parent = 0
        if (entry["type"] == "folder"
                and parent in self._bookmark_subtree(entry["id"])):
            return  # a folder cannot be put inside itself, or its own child
        self.bookmarks.remove(entry)
        entry["parent"] = parent
        siblings = [e for e in self.bookmarks if e["parent"] == parent]
        index = max(0, min(int(index), len(siblings)))
        if index < len(siblings):
            at = self.bookmarks.index(siblings[index])
        elif siblings:
            at = self.bookmarks.index(siblings[-1]) + 1
        else:
            at = len(self.bookmarks)
        self.bookmarks.insert(at, entry)
        self.save_bookmarks()

    def add_bookmark_folder(self, name, parent=0):
        """A new folder, at the root or inside another one."""
        if len(self.bookmarks) >= BOOKMARKS_MAX:
            return 0
        parent = _sane_number(parent)
        if parent not in self._bookmark_folder_ids():
            parent = 0
        bid = max((e["id"] for e in self.bookmarks), default=0) + 1
        self.bookmarks.append({
            "id": bid, "type": "folder",
            "title": str(name or "").strip()[:300] or self._ui_str("bmNewFolder"),
            "url": "", "icon": "", "parent": parent, "t": int(time.time()),
        })
        self.save_bookmarks()
        return bid

    def bookmarks_bar_on(self):
        """Off until he asks for it.

        The Favourites button is the way to the collection now, and it
        holds the whole of it — folders, folders inside folders, a
        search box. A strip under the address bar showing the top level
        of the same thing is a second answer to a question that already
        has one, and it is a row of the window gone for good. So it
        stays away, and Ctrl+Shift+B and the switch in Settings bring it
        back for anyone who wants it. Somebody who has already turned it
        on keeps it: only the never-answered case changed."""
        choice = self.config.get("bookmarksBar")
        if choice is None:
            return False
        return bool(choice)

    def toggle_bookmarks_bar(self, on=None):
        show = (not self.bookmarks_bar_on()) if on is None else bool(on)
        self.config["bookmarksBar"] = show
        self.save_config()
        if getattr(self, "bmbar", None) is not None:
            self.bmbar.setVisible(show)
        self.bridge.bookmarksChanged.emit()

    def rebuild_bookmarks_bar(self):
        bar = getattr(self, "bmbar", None)
        if bar is None:
            return
        bar.set_entries([e for e in self.bookmarks if e["parent"] == 0])
        bar.setVisible(self.bookmarks_bar_on())

    def bookmark_icon(self, entry):
        icon = _icon_from_data(entry.get("icon", ""))
        return icon if not icon.isNull() else _blank_favicon()

    def _bm_label(self, entry):
        """One row's text: what he called it, or the address if he
        called it nothing. Cut, because a menu as wide as a title with
        no spaces in it is a menu off the side of the screen."""
        title = (entry.get("title") or "").strip()
        if not title:
            title = QUrl(entry.get("url") or "").host() or entry.get("url", "")
        return title[:60]

    def _fill_entries(self, menu, kids, depth):
        """A row per thing in a folder: a folder opens sideways, a
        bookmark opens the page."""
        for kid in kids:
            if kid["type"] == "folder":
                self._folder_submenu(menu, kid, depth)
                continue
            action = menu.addAction(self._bm_label(kid))
            action.setData(kid)
            action.setIcon(self.bookmark_icon(kid))
            action.triggered.connect(
                lambda _=False, k=kid: self.open_bookmark(k))

    def _folder_submenu(self, menu, entry, depth):
        """A folder as a submenu of the menu it sits in.

        Past BOOKMARKS_DEPTH the nesting stops rather than the folder
        disappearing: the row is still there and still says its name,
        and it opens the manager, where there is no depth at all."""
        if depth > BOOKMARKS_DEPTH:
            action = menu.addAction(self._folder_icon(), self._bm_label(entry))
            action.setData(entry)
            action.triggered.connect(self.open_bookmarks)
            return None
        sub = BookmarkMenu(self, menu)
        sub.setTitle(self._bm_label(entry))
        sub.setIcon(self._folder_icon())
        menu.addMenu(sub)
        # the row he points at is the submenu's own action, so that is
        # where the entry has to hang for a right-click to find it
        sub.menuAction().setData(entry)
        self.fill_folder_menu(sub, entry, depth)
        self._fill_folder_actions(sub, entry)
        return sub

    def _folder_icon(self):
        icon = getattr(self, "_bmfoldericon", None)
        if icon is None:
            icon = _folder_icon()
            self._bmfoldericon = icon
        return icon

    def fill_folder_menu(self, menu, entry, depth=0):
        """A folder's contents — folders inside it included, which drop
        down again — plus a way to open the lot."""
        kids = self._bookmark_kids(entry["id"])
        self._fill_entries(menu, kids, depth + 1)
        if not kids:
            menu.addAction(self._ui_str("bmEmptyFolder")).setEnabled(False)
            return kids
        links = [k for k in kids if k["type"] == "link"]
        if links:
            menu.addSeparator()
            menu.addAction(self._ui_str("bmOpenAll")).triggered.connect(
                lambda _=False, ks=links: [
                    self.open_bookmark(k, new_tab=True) for k in ks])
        return kids

    def _fill_folder_actions(self, menu, entry):
        """What a folder can have done to it, written out as items you
        can see: put this page in here, make a folder in here, rename
        it, throw it away.

        Edge hides all four behind a right-click. They are spelled out
        here because the person this is for does not right-click, and a
        rename he cannot find is a rename that does not exist. The
        right-click works too — see BookmarkMenu."""
        menu.addSeparator()
        add = menu.addAction(self._ui_str("bmAdd"))
        add.setEnabled(not self._bookmarkable().isEmpty())
        add.triggered.connect(
            lambda _=False, e=entry: self.add_bookmark_here(e["id"]))
        menu.addAction(self._ui_str("bmNewFolder")).triggered.connect(
            lambda _=False, e=entry: self._new_folder_in(e["id"]))
        menu.addAction(self._ui_str("bmRename")).triggered.connect(
            lambda _=False, e=entry: self._rename_bookmark(e))
        self._add_delete_action(menu, entry)

    def _new_folder_in(self, parent=0, take_page=False):
        """A new folder, named before it exists — the name box is the
        whole point, an unnamed "New folder" is what he then has to go
        and find a way to rename."""
        name, ok = QInputDialog.getText(
            self, self._ui_str("bmNewFolder"), self._ui_str("bmFolderName"),
            QLineEdit.EchoMode.Normal, "")
        if not ok:
            return 0
        bid = self.add_bookmark_folder(name, parent)
        if bid and take_page:
            self.add_bookmark_here(bid)
        return bid

    def fill_folder_picker(self, menu, chosen, barred=(), here=None):
        """A list of folders to pick one of: the bar itself first, then
        every folder there is, stepped in so what sits inside what can
        be read straight off it.

        `barred` is the one move that would tie the collection in a
        knot — a folder into itself or into its own child — and it is
        left off the list rather than refused after the click."""
        barred = set(barred)
        top = menu.addAction(self._ui_str("bmNoFolder"))
        top.setEnabled(here != 0)
        top.triggered.connect(lambda: chosen(0))
        for entry, depth in self.bookmark_folder_tree():
            if entry["id"] in barred:
                continue
            action = menu.addAction("    " * depth + self._bm_label(entry))
            action.setIcon(self._folder_icon())
            action.setEnabled(here != entry["id"])
            action.triggered.connect(
                lambda _=False, e=entry: chosen(e["id"]))

    def favorites_panel(self):
        """The Favourites panel, built the first time it is asked for
        and kept after — it holds which folders he has open."""
        panel = getattr(self, "_favpanel", None)
        if panel is None:
            panel = FavoritesPanel(self)
            self._favpanel = panel
        return panel

    def toggle_favorites(self):
        """The Favourites button, and Ctrl+Shift+F. A panel that is
        already up comes down again."""
        panel = self.favorites_panel()
        if panel.isVisible():
            panel.close()
            return
        panel.open_up()

    def _place_favorites(self):
        panel = getattr(self, "_favpanel", None)
        if panel is not None and panel.isVisible():
            panel.place()

    def _add_delete_action(self, menu, entry):
        """Delete. A folder that would take bookmarks down with it has
        to be asked twice — the row goes straight to disk and there is
        no undo, and the manager arms its own button the same way."""
        kids = self._bookmark_subtree(entry["id"]) - {entry["id"]}
        if entry["type"] != "folder" or not kids:
            menu.addAction(self._ui_str("bmDelete")).triggered.connect(
                lambda _=False, e=entry: self.remove_bookmark(e["id"]))
            return
        confirm = menu.addMenu(self._ui_str("bmDelete"))
        confirm.addAction(
            self._ui_str("bmDeleteFolder").format(len(kids))
        ).triggered.connect(
            lambda _=False, e=entry: self.remove_bookmark(e["id"]))

    def bookmark_folder_menu(self, entry, where):
        """A folder on the bar drops its contents down — the same menu
        the Favourites button would give it, so the two cannot drift."""
        menu = BookmarkMenu(self)
        self.fill_folder_menu(menu, entry)
        self._fill_folder_actions(menu, entry)
        menu.exec(where)

    def bookmark_menu(self, entry, where):
        """Right click on a bar entry."""
        menu = QMenu(self)
        if entry["type"] == "link":
            menu.addAction(self._ui_str("bmOpen")).triggered.connect(
                lambda _=False, e=entry: self.open_bookmark(e))
            menu.addAction(self._ui_str("bmOpenNew")).triggered.connect(
                lambda _=False, e=entry: self.open_bookmark(e, new_tab=True))
            menu.addSeparator()
        else:
            menu.addAction(self._ui_str("bmNewFolder")).triggered.connect(
                lambda _=False, e=entry: self._new_folder_in(e["id"]))
        menu.addAction(self._ui_str("bmRename")).triggered.connect(
            lambda _=False, e=entry: self._rename_bookmark(e))
        if entry["type"] == "link":
            menu.addAction(self._ui_str("bmEditUrl")).triggered.connect(
                lambda _=False, e=entry: self._readdress_bookmark(e))
        self._add_delete_action(menu, entry)
        menu.addSeparator()
        menu.addAction(self._ui_str("bmManage")).triggered.connect(
            self.open_bookmarks)
        menu.exec(where)

    def _bmbar_menu(self, pos):
        """Right click on the empty part of the bar."""
        menu = QMenu(self)
        menu.addAction(self._ui_str("bmManage")).triggered.connect(
            self.open_bookmarks)
        menu.addAction(self._ui_str("bmNewFolder")).triggered.connect(
            lambda: self._new_folder_in(0))
        menu.addSeparator()
        hide = menu.addAction(self._ui_str("bmBar"))
        hide.setCheckable(True)
        hide.setChecked(self.bookmarks_bar_on())
        hide.triggered.connect(lambda on: self.toggle_bookmarks_bar(on))
        menu.exec(self.bmbar.mapToGlobal(pos))

    def _rename_bookmark(self, entry):
        name, ok = QInputDialog.getText(
            self, self._ui_str("bmRename"), self._ui_str("bmNewName"),
            QLineEdit.EchoMode.Normal, entry.get("title", ""))
        if ok:
            self.update_bookmark(entry["id"], name, entry.get("url", ""))

    def _readdress_bookmark(self, entry):
        text, ok = QInputDialog.getText(
            self, self._ui_str("bmEditUrl"), self._ui_str("bmUrl"),
            QLineEdit.EchoMode.Normal, entry.get("url", ""))
        if ok:
            self.update_bookmark(entry["id"], entry.get("title", ""), text)

    def bookmarks_url(self):
        """The bookmarks page plus this run's key (see Bridge._own_page)."""
        url = QUrl(BOOKMARKS_PAGE)
        query = url.query()
        url.setQuery((query + "&" if query else "") + "k=" + self._page_key)
        return url.toString()

    def open_bookmarks(self):
        """The bookmarks manager, as a pane over the current tab —
        Ctrl+Shift+O, the bar's context menus and the » overflow menu
        all end here. It used to be a tab that had to be hunted down
        and reused; a pane needs none of that."""
        self.open_pane("bookmarks")

    def toggle_bookmarks(self):
        """Ctrl+Shift+O both ways."""
        self.toggle_pane("bookmarks")

    # ---- which store the secrets live in ----
    def vault_password_on(self):
        """Is Vault Password installed?

        Off means the login watcher is never put into a page, so no
        site is ever looked at for a login, nothing is ever offered to
        save, and nothing is ever written to the vault. What is already
        on disk is left exactly where it is — switching off is not a
        delete, and switching back on finds everything still there.

        The inline default is True on purpose: __init__ settles the key
        for every profile, so this only answers if someone edited it
        back out of config.json by hand, and the safe answer there is
        what every install did before the switch existed."""
        return bool(self.config.get(VAULT_PASSWORD_KEY, True))

    def vault_provider_name(self):
        return str(self.config.get("passwordProvider", "file") or "file")

    def build_provider(self, name):
        """One provider by name. Never raises: an unknown name is the
        file vault, which always works."""
        if name == "1password":
            return OnePasswordProvider(
                CONFIG_FILE.parent,
                vault_name=str(self.config.get("opVault", "") or ""),
                binary=str(self.config.get("opBinary", "") or "op"),
                lock=self.vault_lock)
        return FileVaultProvider(CONFIG_FILE.parent, lock=self.vault_lock)

    def make_vault(self):
        """The vault the browser starts with.

        The window opens on the file vault, always, and a store that
        lives somewhere else is reached for on a worker thread. When
        the answer comes back it swaps in and the page redraws; when it
        does not — `op` not installed, no token, a revoked service
        account — the fallback and its reason are on screen in plain
        words.

        This used to ask the provider on the way past, on the GUI
        thread, which meant a hanging `op` bought twenty seconds of no
        window at all before the browser had drawn a pixel."""
        self.vault_fell_back = ""
        self.vault_checking = ""
        vault = PasswordVault(
            CONFIG_FILE.parent,
            provider=FileVaultProvider(CONFIG_FILE.parent,
                                       lock=self.vault_lock))
        name = self.vault_provider_name()
        # A store somewhere else is only worth reaching for if the
        # feature that reads it is installed: without this, an `op`
        # subprocess runs at every start for a manager he switched off.
        # ...and only when the vault is open. A master password guards
        # the way into 1Password from this computer even though it
        # cannot guard 1Password: locked, the token is sealed and `op`
        # is not run at all, so there is nothing to reach for yet.
        if name != "file" and self.vault_password_on() \
                and not self.vault_lock.locked():
            self.vault_checking = name
            self.vault_job(lambda: self._reach_for(name), self._vault_reached)
        return vault

    def _reach_for(self, name):
        """Worker thread: is that store there, and what is in it? Both
        answers together, because both are subprocesses."""
        provider = self.build_provider(name)
        state = provider.probe()
        return (name, provider, state,
                provider.load() if state["ok"] else None)

    def _vault_reached(self, result):
        """Back on the GUI thread with the answer, and nothing here
        blocks: the subprocess is long finished and the snapshot is a
        plain dict."""
        if not result:
            self.vault_checking = ""
            self.vault_fell_back = "failed"
        else:
            name, provider, state, snapshot = result
            if name != self.vault_provider_name():
                return            # he picked something else meanwhile
            self.vault_checking = ""
            if state["ok"] and self.vault_locked():
                # It shut while we were away. The snapshot in hand is
                # 1Password's, passwords and all, and putting it into
                # the vault would hand a locked browser every secret
                # it is meant not to have -- filling forms, listing
                # accounts in the chooser, the lot. Drop it: the file
                # vault, which is locked, stays.
                self.vault_fell_back = ""
            elif state["ok"]:
                self.vault_fell_back = ""
                self.vault.adopt(provider, snapshot)
            else:
                self.vault_fell_back = state["reason"] or "unavailable"
        bridge = getattr(self, "bridge", None)
        if bridge is not None:
            bridge.vaultChanged.emit()

    def set_vault_provider(self, name):
        """Switch stores on purpose. Nothing is copied and nothing is
        moved: each store keeps exactly what it already had, and he
        sees whichever one is selected. Import/export is the way to
        move things between them, deliberately."""
        self.config["passwordProvider"] = name
        self.save_config()
        self.vault = self.make_vault()
        self.bridge.vaultChanged.emit()
        return {"provider": name, "checking": self.vault_checking,
                "fellBack": self.vault_fell_back}

    # ---- the master password ----
    def vault_locked(self):
        """Is the vault shut right now?

        A question about the data, and only about the data: is there a
        master password on this file, and is it closed? An install that
        has never set one answers False for ever and behaves exactly as
        it always has.

        Deliberately NOT "...and is the password manager switched on".
        It used to be, and the two answers could disagree: with Vault
        Password off and a locked vault on disk, the manager reported
        "nothing saved yet" over a full one. Whether the feature is
        installed decides whether anything asks the question at all —
        the watcher is not injected, the pane will not open — it cannot
        decide whether the bytes are readable. They are not."""
        return self.vault_lock.locked()

    def master_lock_minutes(self):
        """How long an open vault stays open with nothing happening."""
        try:
            minutes = int(self.config.get(MASTER_LOCK_KEY,
                                          MASTER_LOCK_DEFAULT))
        except (TypeError, ValueError):
            minutes = MASTER_LOCK_DEFAULT
        return max(0, min(1440, minutes))

    def master_state(self):
        """The three facts every page needs and none of them a secret."""
        return {"on": self.vault_lock.enabled(),
                "locked": self.vault_lock.locked(),
                "minutes": self.master_lock_minutes(),
                "installed": self.vault_password_on()}

    def _master_tick(self):
        """The auto-lock clock. can_seal() is "on and open", so a vault
        with no master password is never woken up by this at all."""
        minutes = self.master_lock_minutes()
        if minutes and self.vault_lock.can_seal() \
                and self.vault_lock.idle() > minutes * 60:
            self.lock_vault()

    def lock_vault(self):
        """Shut it, now — the menu, the shortcut, or the clock.

        The key is dropped and the vault is rebuilt from the file,
        which locked reads as empty. There is then nothing left in
        this process to show, to fill or to save: locking is not a
        flag that the rest of the code has to remember to honour, it
        takes the passwords away."""
        if not self.vault_lock.can_seal():
            return False
        self.vault_lock.lock()
        # Everything already on its way back from a worker thread is
        # now answering a question the browser is no longer allowed to
        # ask. Moving the epoch on is what drops it (see vault_job).
        self._vault_epoch += 1
        self.vault = self.make_vault()
        self._close_account_chooser()   # nothing left to choose between
        self._vault_changed()
        return True

    def _vault_changed(self):
        """The vault is not what it was. Everything drawn from it is
        redrawn: the pages that are listening, and the handle in the
        address bar, which is in the bar exactly when there is a choice
        to make and so must leave it when the vault shuts."""
        self._sync_acct()
        bridge = getattr(self, "bridge", None)
        if bridge is not None:
            bridge.vaultChanged.emit()

    def ask_unlock_vault(self):
        """The passphrase, in a box of the browser's own.

        True when the vault is open by the time this returns, which
        includes the case where there was never a master password to
        be asked for. Cancelling is a real answer and is taken as one.

        Only ever one box at a time. Several pages can want the vault
        at the same moment — two tabs on login forms, the manager, the
        settings page — and the failure that would follow is a stack
        of identical dialogs, which is the prompt storm this feature
        is supposed not to be."""
        if not self.vault_lock.locked():
            return True
        if self._master_asking:
            return False
        self._master_asking = True
        try:
            MasterUnlockDialog(self, self._ui_str, self.vault_lock).exec()
        finally:
            self._master_asking = False
        if self.vault_lock.locked():
            return False
        self.vault = self.make_vault()
        self._vault_changed()
        return True

    def setup_master(self, passphrase):
        """Switch a master password on from the setup wizard.

        Refuses to touch an install that already has one: the wizard
        can be re-run, and re-keying a vault is a different operation
        with a different question (the old passphrase) that belongs in
        Settings. The wizard says so rather than offering a second one.

        The vault is left OPEN for this session, and that is a
        deliberate choice rather than an oversight. At rest it is
        genuinely locked — the file is sealed and the key file is gone,
        which is the property that matters — but shutting it the
        instant setup ends would mean a brand-new install where the
        first login is silently never offered for saving, because a
        locked vault offers nothing. He typed the passphrase seconds
        ago and is sitting in front of the machine; auto-lock is armed
        from here and shuts it after the usual quarter of an hour. The
        wizard row says so in as many words."""
        text = str(passphrase or "")
        if len(text) < MASTER_MIN:
            return dict(self.master_state(), set=False)
        if self.vault_lock.enabled():
            return dict(self.master_state(), set=True, already=True)
        ok = self.vault_lock.enable(text)
        del text
        if ok:
            self.vault = self.make_vault()
            self.vault_lock.touch()      # the idle clock starts now
            self._vault_changed()
        return dict(self.master_state(), set=bool(ok))

    def clear_setup_master(self):
        """He turned it off again before leaving the wizard.

        Only ever undoes what this wizard run did: switching off needs
        the vault open, and it is open exactly when this run is what
        opened it."""
        if self.vault_lock.enabled() and not self.vault_lock.locked():
            if self.vault_lock.disable():
                self.vault = self.make_vault()
                self._vault_changed()
        return dict(self.master_state(), set=False)

    def set_master_password(self, on):
        """Switch it on or off. Returns where things ended up, which
        is not always where the switch was moved to — he can change
        his mind in either dialog, and the page redraws from this."""
        want = bool(on)
        if want == self.vault_lock.enabled():
            return self.master_state()
        if want:
            self._master_enable()
        else:
            self._master_disable()
        return self.master_state()

    def _master_enable(self):
        dialog = MasterSetupDialog(self, self._ui_str, self.export_passwords)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.vault_lock.enable(dialog.value("first")):
            self._toast_result(self._ui_str("masterFailed"))
            return
        self.vault = self.make_vault()
        self._vault_changed()
        self._toast_result(self._ui_str("masterOnDone"))

    def _master_disable(self):
        """Off again, with everything still in it.

        It needs the vault open, so it needs the passphrase: switching
        off in Settings is not a way round the thing. And it says what
        going back means, because it means the key returns to a file
        sitting next to the lock."""
        if not self.ask_unlock_vault():
            return
        answer = QMessageBox.question(
            self, self._ui_str("masterOffT"), self._ui_str("masterOffB"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.vault_lock.disable():
            self._toast_result(self._ui_str("masterFailed"))
            return
        self.vault = self.make_vault()
        self._vault_changed()
        self._toast_result(self._ui_str("masterOffDone"))

    def change_master_password(self):
        """A new passphrase. The dialog does the work and says no to a
        wrong current one itself, so there is nothing to report here
        beyond where things stand afterwards."""
        if not self.vault_lock.enabled():
            return self.master_state()
        dialog = MasterChangeDialog(self, self._ui_str, self.vault_lock)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.vault = self.make_vault()
            self._vault_changed()
            self._toast_result(self._ui_str("masterChangeDone"))
        return self.master_state()

    def set_master_minutes(self, minutes):
        try:
            minutes = max(0, min(1440, int(minutes)))
        except (TypeError, ValueError):
            return self.master_state()
        self.config[MASTER_LOCK_KEY] = minutes
        self.save_config()
        return self.master_state()

    def ask_op_token(self):
        """The service-account token, typed into a native dialog.

        It goes straight into its own chmod 0600 file and nowhere else:
        not into config.json, not into a page, not into an argument
        list. QLineEdit.Password mode means it is not on screen while
        he types it either. Leaving the box empty removes a token that
        was already there."""
        provider = OnePasswordProvider(CONFIG_FILE.parent,
                                       lock=self.vault_lock)
        text, ok = QInputDialog.getText(
            self, self._ui_str("pwOpToken"), self._ui_str("pwOpTokenAsk"),
            QLineEdit.EchoMode.Password, "")
        if not ok:
            return {"cancelled": True}
        provider.write_token(text)
        del text
        if self.vault_provider_name() == "1password":
            self.vault = self.make_vault()   # the check runs in the
        return {"hasToken": provider.have_token(),   # background now
                "checking": self.vault_checking}

    def vault_job(self, work, then):
        """Run a provider call off the GUI thread (see BackgroundCall)
        and hand the result to `then` back on it.

        A job that was in flight when the vault was locked is dropped
        on arrival, and this is the whole of "cancel in-flight work on
        lock": a thread cannot be called back, and `op` is allowed
        twenty seconds, so there is always a window in which a fetch
        that started while the vault was open finishes after it has
        shut. What such a job carries is exactly what locking was
        supposed to take away — a 1Password snapshot with the
        passwords in it, or one secret on its way to the manager page.

        It is done by counting rather than by asking whether the vault
        is locked *now*, because unlocking again must not resurrect it
        either: the answer belongs to the browser as it was before the
        lock, and that browser is gone. See lock_vault."""
        job = BackgroundCall(work, self)
        self._vault_jobs.add(job)
        epoch = self._vault_epoch

        def finish(result):
            self._vault_jobs.discard(job)
            if epoch != self._vault_epoch:
                return
            then(result)
        job.start(finish)

    def passwords_url(self):
        """The passwords page plus this run's key (see Bridge._own_page)."""
        url = QUrl(PASSWORDS_PAGE)
        query = url.query()
        url.setQuery((query + "&" if query else "") + "k=" + self._page_key)
        return url.toString()

    def open_passwords(self):
        """The password manager, as a pane over the current tab — the
        last of the browser's own pages to stop being one. It used to be
        a tab that had to be hunted down and reused, and that reuse
        existed only because a second passwords tab would have been
        wrong; a pane cannot be opened twice.

        Silent when Vault Password is not installed: the shortcut stays
        bound either way, so gating here rather than at the binding
        means switching it on works without a restart. Gating here also
        means the pane is never even built, so there is no hidden
        passwords page sitting in an install that has none."""
        if not self.vault_password_on():
            return
        # Opening the manager is him asking for the vault in so many
        # words, so this is the one place it is right to ask back. The
        # pane comes up either way: cancelling leaves the locked screen
        # with its own button, rather than a shortcut that appears to
        # do nothing.
        self.ask_unlock_vault()
        self.open_pane("passwords")

    def toggle_passwords(self):
        """Ctrl+Shift+P both ways — but only ever opens when Vault
        Password is on. Closing is unconditional: if a pane is somehow
        up it must always be possible to get out of it."""
        if self.pane_open("passwords"):
            self.close_pane()
        else:
            self.open_passwords()

    def toggle_vault_lock(self):
        """Ctrl+Shift+L. Shut if it is open, ask if it is shut, and
        nothing at all on an install with no master password — the
        shortcut is bound either way so that switching one on works
        without a restart."""
        if not self.vault_lock.enabled():
            return
        if self.vault_lock.locked():
            self.ask_unlock_vault()
        else:
            self.lock_vault()

    def generate_to_clipboard(self):
        """Ctrl+Shift+G: a fresh strong password straight onto the
        clipboard, for the sign-up form in front of him. It never
        appears in a label, a log or a page — the clipboard is the
        only place it goes, and the settings the passwords page was
        last set to are the ones used."""
        if not self.vault_password_on():
            return
        options = self.config.get("pwGen") or {}
        password = generate_password(
            int(options.get("length", 20)),
            bool(options.get("symbols", True)),
            bool(options.get("digits", True)),
            bool(options.get("upper", True)),
            bool(options.get("ambiguous", False)))
        QGuiApplication.clipboard().setText(password)
        del password
        self._show_plain_toast(self._ui_str("pwGenCopied"))

    def _show_plain_toast(self, message):
        """A line of text that goes away by itself. Nothing to click."""
        if self._toast:
            self._hide_toast()
        toast = QWidget(self, objectName="toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(toast)
        lay.setContentsMargins(14, 8, 14, 8)
        self._toast_label = QLabel(message)
        lay.addWidget(self._toast_label)
        self._toast = toast
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(2600)
        self._toast_timer.timeout.connect(self._hide_toast)
        self._place_toast()
        toast.show()
        toast.raise_()
        self._toast_timer.start()

    def pick_import_file(self):
        """The native picker, and the text of what he picked — so the
        page never sees a path and never reads a file itself.

        Returns a dict instead when there is nothing to import. The
        importing itself happens elsewhere, on a worker thread; this
        part has to be here because a file dialog is a window."""
        path, _ = QFileDialog.getOpenFileName(
            self, self._ui_str("pwImport"), str(Path.home()),
            "CSV (*.csv);;" + self._ui_str("pwAllFiles") + " (*)")
        if not path:
            return {"cancelled": True}
        try:
            return Path(path).read_text(encoding="utf-8-sig",
                                        errors="replace")
        except OSError as exc:
            return {"error": str(exc)}

    def export_passwords(self):
        """Write the vault out as plain CSV — but only after he has
        read, in a native dialog he cannot restyle away, exactly what
        that file will contain and what it will not protect.

        Only from a store that has actually handed the passwords over.
        1Password has not: export_rows() would read an empty password
        off every row and write a file that looks exactly like a backup
        and is not one. Fetching them instead would be one subprocess
        per login behind a modal dialog, which is not an export either
        — so this says no, and the page greys the button out."""
        if not self.vault.provider.eager:
            return {"unavailable": True}
        count = len(self.vault.logins())
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self._ui_str("pwExport"))
        box.setText(self._ui_str("pwExportWarnT"))
        box.setInformativeText(
            self._ui_str("pwExportWarnB").format(count))
        box.setStandardButtons(QMessageBox.StandardButton.Cancel)
        go = box.addButton(self._ui_str("pwExportGo"),
                           QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not go:
            return {"cancelled": True}
        path, _ = QFileDialog.getSaveFileName(
            self, self._ui_str("pwExport"),
            str(Path.home() / "passwords.csv"), "CSV (*.csv)")
        if not path:
            return {"cancelled": True}
        return self.write_export(path)

    def write_export(self, path):
        """The plain-text file itself.

        0600 from the moment it exists, not after it is written and
        closed: the old order left every password in the clear at
        whatever the umask happened to say for as long as the write
        took, and skipped the chmod altogether if writerows threw."""
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(fd, 0o600)   # O_CREAT does not re-mode a file
            except (OSError, AttributeError):
                # OSError: the file was already there; this re-modes it.
                # AttributeError: Windows has no fchmod at all, and an
                # AttributeError is not an OSError, so leaving it out
                # took the whole export down rather than the one line
                # that cannot work there. The export is still written —
                # it just carries the folder's protection, the same as
                # every other file this edition writes on Windows.
                pass
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(self.vault.export_rows())
        except (OSError, csv.Error) as exc:
            return {"error": str(exc)}
        return {"written": len(self.vault.logins()), "path": path}

    def downloads_url(self):
        """The downloads page plus this run's key (see Bridge._own_page)."""
        url = QUrl(DOWNLOADS_PAGE)
        query = url.query()
        url.setQuery((query + "&" if query else "") + "k=" + self._page_key)
        return url.toString()

    def open_downloads(self):
        """The downloads page, as a pane over the current tab. It used
        to be a tab of its own, hunted down and reused if one was
        already open; a pane needs none of that, and it costs him
        neither a tab, a history entry nor the address bar."""
        self.open_pane("downloads")

    def toggle_downloads(self):
        """Ctrl+J both ways."""
        self.toggle_pane("downloads")

    # ---- print / save as PDF ----
    def print_menu(self):
        """Saving a PDF is what Qt WebEngine can always do; the printer
        entry only appears when QtPrintSupport imported."""
        menu = QMenu(self)
        menu.addAction(self._ui_str("savePdf")).triggered.connect(
            self.save_as_pdf)
        if HAVE_PRINTER:
            menu.addAction(self._ui_str("printTo")).triggered.connect(
                self.print_to_printer)
        return menu

    def play_externally(self):
        """Ctrl+Shift+V: hand the page to mpv.

        Some broadcasters stream HEVC, and Chromium only decodes it
        where the platform already has a decoder — which on most Linux
        builds, Fedora's included, it does not. The picture then never
        appears however well the rest of the page works. mpv (through
        yt-dlp) has no such gap, so rather than pretend, we hand the
        page over. Nothing here is browser-specific: it is the address
        bar's URL and an external program."""
        view = self.current()
        if view is None or self._is_header(view):
            return
        url = view.url().toString()
        if not url.startswith(("http://", "https://")):
            return  # our own pages have nothing to hand over
        player = shutil.which("mpv") or shutil.which("vlc")
        if not player:
            return  # nothing installed to hand it to; stay quiet
        proc = QProcess(self)
        # detached: closing the browser should not kill what he is watching
        proc.startDetached(player, [url])

    def print_page(self):
        """Ctrl+P. Never two menus at once: the shortcut and a page's own
        window.print() can both land here for the same keypress. And
        never over a pane: it covers the window, so the menu would be
        offering to print a page he cannot see. (The shortcut steps out
        of the pane first; window.print() from the tab underneath does
        not, and it is the one that would surprise him.)"""
        view = self.current()
        if view is None or self._is_header(view) or self.pane_open():
            return
        if getattr(self, "_print_menu_up", False):
            return
        self._print_menu_up = True
        btn = self._print_btn
        try:
            self.print_menu().exec(self._menu_anchor(btn))
        finally:
            self._print_menu_up = False

    def _print_requested(self, view):
        """window.print() from a page: only ever for the tab in front of
        him, and only through the same menu Ctrl+P opens — a background
        tab does not get to put a menu on the screen."""
        if view is self.current():
            self.print_page()

    def _page_filename(self, view, suffix):
        """A sane file name out of the page title."""
        title = (view.title() or "").strip()
        if not title:
            title = view.url().host() or "page"
        name = re.sub(r'[\\/:*?"<>|]', " ", title)
        name = re.sub(r"[\x00-\x1f]", "", name)
        name = re.sub(r"\s+", " ", name).strip(" .")
        return (name[:80].strip(" .") or "page") + suffix

    def save_as_pdf(self):
        """The page as a PDF in the usual download folder, listed on the
        usual downloads page — unless it is a private tab, where the
        file is written and the listing is not."""
        view = self.current()
        if view is None or self._is_header(view):
            return None
        folder = self.download_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        private = self._page_is_private(view.page())
        name = self._unique_download_name(self._page_filename(view, ".pdf"),
                                          hold=private)
        path = folder / name
        entry = self._add_download_entry(
            {"name": name, "dir": str(folder),
             "url": view.url().toString(), "t": int(time.time()),
             "state": "active", "received": 0, "size": 0, "paused": False,
             # a file we render ourselves: nothing to pause or cancel,
             # so the downloads page leaves those buttons off
             "local": True},
            record=not private)
        widget = LocalFileWidget(name, self._dismiss_download)
        widget.info.setText(self._ui_str("pdfSaving"))
        self.dllay.insertWidget(self.dllay.count() - 1, widget)
        self.dlbar.show()
        self.bridge.downloadsChanged.emit()

        page = view.page()

        def done(finished, ok):
            # pdfPrintingFinished belongs to the page, not to one print:
            # start a second one while the first is still rendering and
            # both closures hear both answers. Each only answers for its
            # own file, or the one about to succeed gets marked with the
            # other's failure.
            if finished != str(path):
                return
            try:
                page.pdfPrintingFinished.disconnect(done)
            except TypeError:
                pass
            self._pdf_finished(entry, path, ok, widget)

        page.pdfPrintingFinished.connect(done)
        view.printToPdf(str(path))
        # a print that never reports back would hold this record on
        # "active" forever: unremovable, unclearable, name reserved
        QTimer.singleShot(PDF_TIMEOUT_MS,
                          lambda: self._pdf_finished(entry, path, False,
                                                     widget))
        return entry

    def _pdf_finished(self, entry, path, ok, widget):
        if entry["state"] != "active":
            return  # an end we already wrote down (see _download_state)
        size = 0
        try:
            size = path.stat().st_size
        except OSError:
            ok = False
        good = bool(ok and size)
        entry["state"] = "done" if good else "failed"
        entry["received"] = entry["size"] = size if good else 0
        self.save_downloads()
        self.bridge.downloadsChanged.emit()
        try:
            widget.finished(path, size, good, self._ui_str("dlDone"),
                            self._ui_str("pdfFailed"))
        except RuntimeError:
            pass  # he dismissed the toast while the PDF was rendering

    def print_to_printer(self):
        view = self.current()
        if view is None or self._is_header(view) or not HAVE_PRINTER:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(self._page_filename(view, ""))
        if not QPrintDialog(printer, self).exec():
            return
        # printing is asynchronous: the printer has to outlive this call
        self._printer = printer
        view.print(printer)

    def restart(self):
        """Relaunch the browser (used after an update)."""
        if getattr(self, "_instance_server", None) is not None:
            # free the single-instance socket so the successor
            # becomes the new primary instead of handing off to us
            self._instance_server.close()
            QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
        # successor waits for this process to exit before starting
        os.environ["BROWSER_RESTART_WAIT"] = str(os.getpid())
        QProcess.startDetached(sys.executable, [str(APP_DIR / "browser.py")])
        QApplication.instance().quit()

    def _clear_on_exit(self):
        """"Clear when I close the browser". History is written out here
        and now; cookies are asked for here and marked to be asked for
        again at the next start, because a wipe fired into a profile
        that is shutting down is not one I can promise. Reached from
        closeEvent and from aboutToQuit (which is what a restart and a
        quit from the menu go through), so it runs once and only once."""
        if self._exit_cleared:
            return
        self._exit_cleared = True
        if self.config.get("clearHistoryExit"):
            self.history = []
            self.save_history()
        if self.config.get("clearCookiesExit"):
            for profile in self._all_profiles():
                profile.cookieStore().deleteAllCookies()
                profile.clearHttpCache()
            self.config["cookiesWipePending"] = True
        # the run ended the way it was meant to: nothing left over for
        # the next start to catch up on
        self.config["runOpen"] = False
        self.save_config()

    def closeEvent(self, event):
        # a screen-share picker still up is declined here, while its tab
        # is whole: everything below this line is teardown
        self._drop_share()
        self._clear_on_exit()
        # closing the window from the compositor (e.g. Super+Q) must end
        # the process too — a lingering ghost would hold the
        # single-instance socket and swallow future launches
        QApplication.instance().quit()
        super().closeEvent(event)

    def _dismiss_download(self, widget):
        self.dllay.removeWidget(widget)
        widget.deleteLater()
        if self.dllay.count() <= 2:  # only the button and the stretch left
            self.dlbar.hide()


_PROXY_FLAGS_AT_LAUNCH = None  # what Chromium was started with
_RULE_PROXY = None  # the RuleProxy serving per-site rules, if any


def _migrate_proxy_config(config):
    # old single-proxy config -> a named profile + active selection
    if "activeProxy" not in config:
        old = config.get("proxy")
        if isinstance(old, dict) and old.get("mode") == "custom":
            config["proxyProfiles"] = [
                {"name": "Proxy", "type": old.get("type", "http"),
                 "host": old.get("host", ""), "port": old.get("port", 0)}]
            config["activeProxy"] = "Proxy"
        else:
            config["activeProxy"] = (old or {}).get("mode", "system")
    if config.get("activeProxy") == "auto":
        # rules now apply in every mode; the old Auto mode collapses
        # to the default route its rules fell back to
        config["activeProxy"] = (config.get("proxyAuto") or {}).get(
            "default", "direct")
    return config


def _normalize_rule_pattern(pattern):
    """A pasted URL becomes its hostname: scheme, path, query,
    credentials and port are stripped so "https://www.youtube.com/"
    just works as a rule pattern."""
    pat = (pattern or "").strip().lower()
    pat = re.sub(r"^[a-z][a-z0-9+.-]*://", "", pat)
    pat = pat.split("/", 1)[0].split("?", 1)[0]
    if "@" in pat:
        pat = pat.rsplit("@", 1)[1]
    return re.sub(r":\d+$", "", pat)


def _system_proxy_route():
    """The system proxy from the environment as (route, bypass hosts),
    resolved once at launch. Nothing configured means direct."""
    val = scheme = ""
    for var in ("https_proxy", "http_proxy", "all_proxy"):
        val = os.environ.get(var, "") or os.environ.get(var.upper(), "")
        if val:
            break
    val = val.strip().rstrip("/")
    if "://" in val:
        scheme, _, val = val.partition("://")
    if "@" in val:
        val = val.rsplit("@", 1)[1]
    host, _, port = val.rpartition(":")
    host = re.sub(r"[^A-Za-z0-9.-]", "", host)
    if not host or not port.isdigit():
        return ("direct",), []
    kind = "socks5" if scheme.lower().startswith("socks") else "http"
    bypass = [re.sub(r":\d+$", "", e.strip().lstrip("*."))
              for e in re.split(r"[\s,]+", os.environ.get("no_proxy", "")
                                or os.environ.get("NO_PROXY", ""))]
    return (kind, host, int(port), "", ""), [b for b in bypass if b]


def _proxy_hostport(prof):
    """Sanitized (host, port) of a profile, or None if unusable."""
    if not prof:
        return None
    host = re.sub(r"[^A-Za-z0-9.-]", "", str(prof.get("host", "")))
    try:
        port = int(prof.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return (host, port) if host and port else None


def _proxy_route(profiles, name):
    """A profile as a routing tuple: ("direct",) or
    (kind, host, port, user, password)."""
    prof = profiles.get(name)
    hp = _proxy_hostport(prof)
    if hp is None:  # "direct", "system" or a deleted/broken profile
        return ("direct",)
    kind = "socks5" if prof.get("type") == "socks5" else "http"
    return (kind, hp[0], hp[1], str(prof.get("user") or ""),
            str(prof.get("password") or ""))


def _rule_matches(host, pattern):
    """Same semantics the PAC conditions had: exact host or dot-suffix
    subdomain match; shell-style wildcards when "*" appears."""
    pat = re.sub(r"[^a-z0-9.*-]", "", _normalize_rule_pattern(pattern))
    host = (host or "").lower().rstrip(".")
    if not pat:
        return False
    if pat.startswith("*."):
        pat = pat[2:]
    if "*" in pat:
        return re.fullmatch(
            re.escape(pat).replace(r"\*", ".*"), host) is not None
    return host == pat or host.endswith("." + pat)


def _proxy_routing(config):
    """The per-site routing plan as (rules, bypass, default) — rules
    are (pattern, route) pairs — or None when no rules exist."""
    active = config.get("activeProxy", "system")
    if active == "auto":  # pre-rules-everywhere config, unmigrated
        active = (config.get("proxyAuto") or {}).get("default", "direct")
    profiles = {p.get("name"): p for p in config.get("proxyProfiles", [])}
    rules = []
    for rule in (config.get("proxyAuto") or {}).get("rules", []):
        pat = re.sub(r"[^a-z0-9.*-]", "",
                     _normalize_rule_pattern(rule.get("pattern", "")))
        if pat:
            rules.append((pat, _proxy_route(profiles,
                                            rule.get("profile", "direct"))))
    if not rules:
        return None
    bypass = []
    if active == "direct":
        default = ("direct",)
    elif active in profiles:
        default = _proxy_route(profiles, active)  # dead default blocks
    else:  # system — re-resolved only at launch
        default, bypass = _system_proxy_route()
    return rules, bypass, default


class RuleProxy:
    """Local forwarding proxy: the engine's per-site routing. A PAC
    cannot do this job — Chromium treats command-line PACs as
    non-mandatory and silently falls back to DIRECT when the returned
    proxy is dead — so matched hosts tunnel through here instead, and
    a dead upstream means a 502: blocked, never leaked. Speaks CONNECT
    and absolute-URI HTTP; upstreams are http proxies (with basic
    auth) or socks5."""

    def __init__(self, rules, bypass, default):
        self.rules = rules
        self.bypass = bypass
        self.default = default
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        try:
            self.server.close()
        except OSError:
            pass

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return  # server closed
            threading.Thread(target=self._serve, args=(conn,),
                             daemon=True).start()

    def _route_for(self, host):
        for pattern, route in self.rules:
            if _rule_matches(host, pattern):
                return route
        for pattern in self.bypass:  # the system proxy's no_proxy list
            if _rule_matches(host, pattern):
                return ("direct",)
        return self.default

    def _serve(self, client):
        upstream = None
        try:
            client.settimeout(30)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(65536)
                if not chunk:
                    return
                head += chunk
                if len(head) > 262144:
                    return
            line = head.split(b"\r\n", 1)[0].decode("latin1")
            method, _, target = line.partition(" ")
            target = target.split(" ", 1)[0]
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                port = int(port or 443)
            else:
                m = re.match(r"[a-z]+://(\[[^\]]+\]|[^/:?]+)(?::(\d+))?",
                             target, re.I)
                if m is None:
                    return
                host, port = m.group(1), int(m.group(2) or 80)
                head = self._single_use(head)
            host = host.strip("[]")
            route = self._route_for(host.lower())
            if method != "CONNECT" and route[0] != "http":
                # direct and socks routes talk to the origin itself,
                # which expects origin-form ("GET / HTTP/1.1"), not
                # the proxy absolute-form the engine sent us
                path = target[m.end():] or "/"
                head = head.replace(
                    ("%s %s " % (method, target)).encode("latin1"),
                    ("%s %s " % (method, path)).encode("latin1"), 1)
            if route[0] == "http":
                upstream = self._http_upstream(route, head)
            else:
                upstream = (socket.create_connection((host, port), 15)
                            if route[0] == "direct"
                            else self._socks_upstream(route, host, port))
                if method == "CONNECT":
                    client.sendall(b"HTTP/1.1 200 Connection Established"
                                   b"\r\n\r\n")
                else:
                    upstream.sendall(head)
        except Exception:
            # fail closed: a dead upstream blocks the site — matched
            # traffic must never silently fall back to a direct
            # connection
            try:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n"
                               b"Content-Length: 0\r\n"
                               b"Connection: close\r\n\r\n")
            except OSError:
                pass
            for sock in (client, upstream):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            return
        client.settimeout(None)
        upstream.settimeout(None)
        self._splice(client, upstream)

    @staticmethod
    def _single_use(head):
        # one request per connection: a kept-alive proxy connection
        # would let the engine reuse this tunnel for a different host
        hdr, _, body = head.partition(b"\r\n\r\n")
        hdr = re.sub(rb"\r\n(?:proxy-)?connection:[^\r]*", b"", hdr,
                     flags=re.I)
        return hdr + b"\r\nConnection: close\r\n\r\n" + body

    @staticmethod
    def _http_upstream(route, head):
        _, phost, pport, user, password = route
        upstream = socket.create_connection((phost, pport), 15)
        if user:
            cred = base64.b64encode(
                ("%s:%s" % (user, password)).encode()).decode()
            hdr, _, body = head.partition(b"\r\n\r\n")
            head = (hdr + ("\r\nProxy-Authorization: Basic %s"
                           % cred).encode() + b"\r\n\r\n" + body)
        upstream.sendall(head)
        return upstream

    @staticmethod
    def _socks_upstream(route, host, port):
        _, phost, pport, user, password = route

        def recvn(sock, n):
            buf = b""
            while len(buf) < n:
                chunk = sock.recv(n - len(buf))
                if not chunk:
                    raise OSError("socks connection closed")
                buf += chunk
            return buf

        upstream = socket.create_connection((phost, pport), 15)
        try:
            methods = b"\x00\x02" if user else b"\x00"
            upstream.sendall(b"\x05" + bytes([len(methods)]) + methods)
            choice = recvn(upstream, 2)[1]
            if choice == 2:  # username/password, RFC 1929
                upstream.sendall(bytes([1, len(user)]) + user.encode()
                                 + bytes([len(password)])
                                 + password.encode())
                if recvn(upstream, 2)[1] != 0:
                    raise OSError("socks auth refused")
            elif choice != 0:
                raise OSError("no acceptable socks method")
            upstream.sendall(b"\x05\x01\x00\x03"
                             + bytes([len(host)]) + host.encode("latin1")
                             + port.to_bytes(2, "big"))
            reply = recvn(upstream, 4)
            if reply[1] != 0:
                raise OSError("socks connect refused")
            if reply[3] == 1:  # bound address, by type
                recvn(upstream, 6)
            elif reply[3] == 3:
                recvn(upstream, recvn(upstream, 1)[0] + 2)
            elif reply[3] == 4:
                recvn(upstream, 18)
            return upstream
        except Exception:
            upstream.close()
            raise

    @staticmethod
    def _splice(a, b):
        def pump(src, dst):
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            for sock in (src, dst):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        threading.Thread(target=pump, args=(b, a), daemon=True).start()
        pump(a, b)
        for sock in (a, b):
            try:
                sock.close()
            except OSError:
                pass


def _proxy_launch_flags(config):
    """Canonical launch proxy setting for a config — used both to set
    up the engine and to detect drift for the restart toast. The web
    engine reads proxy settings only once, at startup: a Qt
    application proxy set later is ignored, and one set earlier
    overrides these flags and then freezes, so any change means a
    restart. Plain Chromium flags when no per-site rules exist; with
    rules, a routing signature that _install_proxy_flags materializes
    as a RuleProxy."""
    routing = _proxy_routing(config)
    if routing is not None:
        return "helper:%r" % (routing,)
    active = config.get("activeProxy", "system")
    if active == "auto":  # pre-rules-everywhere config, unmigrated
        active = (config.get("proxyAuto") or {}).get("default", "direct")
    profiles = {p.get("name"): p for p in config.get("proxyProfiles", [])}
    if active == "direct":
        return "--no-proxy-server"
    hp = _proxy_hostport(profiles.get(active))
    if hp is None:  # "system" or a broken/deleted profile
        return ""
    scheme = ("socks5://" if profiles[active].get("type") == "socks5"
              else "")
    return "--proxy-server=%s%s:%d" % (scheme, hp[0], hp[1])


def _install_proxy_flags():
    """Bake the proxy config into Chromium's command line; must run
    before the QApplication (and thus the web engine) exists. Any
    proxy flags already in the environment are stripped first: an
    in-app restart hands the child the parent's flags, and a stale
    --no-proxy-server/--proxy-server/--proxy-pac-url would silently
    win over the current config. Per-site rules start a RuleProxy and
    point the engine at it."""
    global _PROXY_FLAGS_AT_LAUNCH, _RULE_PROXY
    try:
        config = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        config = {}
    _migrate_proxy_config(config)
    flags = _proxy_launch_flags(config)
    if _RULE_PROXY is not None:  # re-entry (tests): free the old port
        _RULE_PROXY.close()
        _RULE_PROXY = None
    real = flags
    if flags.startswith("helper:"):
        _RULE_PROXY = RuleProxy(*_proxy_routing(config))
        real = "--proxy-server=127.0.0.1:%d" % _RULE_PROXY.port
    env = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    env = re.sub(r"\s*--(?:proxy-server|proxy-pac-url)=\S+", "", env)
    env = re.sub(r"\s*--no-proxy-server\b", "", env)
    env = re.sub(r"\s*--widevine-path=\S+", "", env)
    # HEVC is patent-encumbered, so Chromium keeps it behind a switch and
    # only ever uses a decoder the platform already provides — Windows
    # with the HEVC extension installed, or hardware that offers it.
    # Where there is none the flag changes nothing. Broadcasters stream
    # HEVC (ARD's live channels do), and without it their player retries
    # a decoder it cannot have and gives up with "Wiedergabefehler".
    if "PlatformHEVCDecoderSupport" not in env:
        env += " --enable-features=PlatformHEVCDecoderSupport"
    cdm = _widevine_path()
    if cdm:
        env += ' --widevine-path="%s"' % cdm
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        env + " " + real if real else env)
    _PROXY_FLAGS_AT_LAUNCH = flags
    return real


def _widevine_path():
    """Where a Widevine CDM might already be sitting on this machine.

    Streaming sites — ARD and the other broadcasters, Netflix, Prime —
    hand out DRM-protected video and simply refuse to play if the
    browser reports no Widevine. Qt WebEngine can use one, but ships
    none: it is Google's proprietary binary and only browsers with a
    licence may distribute it. So we borrow the one an installed
    Chrome or Edge already put on the disk. Nothing is downloaded and
    nothing is copied; if none is there we say nothing and DRM video
    keeps refusing to play, exactly as before."""
    homes, roots = [], []
    if sys.platform == "win32":
        lib = "widevinecdm.dll"
        plat = "win_x64" if sys.maxsize > 2 ** 32 else "win_x86"
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if not base:
                continue
            roots += [Path(base) / "Google/Chrome/Application",
                      Path(base) / "Microsoft/Edge/Application",
                      Path(base) / "BraveSoftware/Brave-Browser/Application",
                      Path(base) / "Google/Chrome/User Data",
                      Path(base) / "Microsoft/Edge/User Data"]
    else:
        lib = "libwidevinecdm.so"
        plat = "linux_x64" if sys.maxsize > 2 ** 32 else "linux_x86"
        roots += [Path("/opt/google/chrome"), Path("/opt/brave.com/brave"),
                  Path("/opt/microsoft/msedge"),
                  Path("/usr/lib64/chromium-browser"),
                  Path("/usr/lib/chromium-browser")]
        homes += [Path.home() / ".config/google-chrome",
                  Path.home() / ".config/chromium",
                  Path.home() / ".config/BraveSoftware/Brave-Browser"]
    found = []
    for root in roots + homes:
        try:
            if not root.is_dir():
                continue
            # WidevineCdm sits either directly under the root or one
            # version directory down (Chrome keeps one per release)
            for base in [root] + sorted(root.iterdir(), reverse=True)[:12]:
                cdm = (base / "WidevineCdm" / "_platform_specific"
                       / plat / lib)
                if cdm.is_file():
                    found.append(cdm)
        except OSError:
            continue
    return str(found[0]) if found else ""


def _select_theme(name):
    """Make a theme the current one for this process. Nothing is
    painted here — this only settles which palette everything that
    asks from now on will get, and it has to happen before the first
    cookie jar is built (every jar carries the script that paints our
    own pages)."""
    global ACTIVE_THEME
    # the config is a file on disk and a file on disk can say anything;
    # a theme that is a list is not a theme, and a browser that will
    # not start is a worse answer than the default one
    if not isinstance(name, str) or name not in THEME_INDEX:
        name = DEFAULT_THEME
    ACTIVE_THEME = name
    return name


def _install_theme_flags():
    """One half of a theme is decided before Qt starts: what websites
    are told about dark mode.

    The flag near the top of this file says "the browser is dark", and
    every site that has a dark version serves it. That is right for a
    dark theme and wrong for a light one — a white browser full of
    black websites. It is a launch flag, so it is rewritten here, from
    the theme in the config, while there is still no engine to hear it.
    Switching theme later paints the browser at once and says in
    Settings that the websites want a restart."""
    try:
        config = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        config = {}
    name = _select_theme(config.get("theme", DEFAULT_THEME))
    env = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    env = re.sub(r"\s*--blink-settings=preferredColorScheme=\d", "", env)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        env + " --blink-settings=preferredColorScheme="
        + ("0" if theme_is_dark(name) else "1"))
    return name


SINGLE_INSTANCE_SOCKET = "browser-single-instance"


def _pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    # a URL argument means we were asked to open a link (e.g. as the
    # system default browser)
    url = sys.argv[1] if len(sys.argv) > 1 else None

    # started by our own restart(): let the old process finish dying
    # so the profile and socket are free
    predecessor = os.environ.pop("BROWSER_RESTART_WAIT", None)
    if predecessor:
        for _ in range(60):
            try:
                if not _pid_alive(int(predecessor)):
                    break
            except ValueError:
                break
            time.sleep(0.1)

    # single instance: two instances sharing one profile breaks Chromium's
    # network/cache storage, so hand the link to the running one instead
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_SOCKET)
    if probe.waitForConnected(300):
        probe.write((url or "raise").encode())
        probe.flush()
        probe.waitForBytesWritten(300)
        return

    QGuiApplication.setDesktopFileName("browser")
    _install_proxy_flags()
    _install_theme_flags()
    app = QApplication(sys.argv)
    app.setApplicationName("browser")
    app.setWindowIcon(QIcon(str(APP_DIR / "icon.svg")))
    app.setStyleSheet(theme_style())
    win = Browser(initial_url=url)

    QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_SOCKET)
    win._instance_server = server

    def handoff():
        conn = server.nextPendingConnection()

        def read():
            message = bytes(conn.readAll()).decode().strip()
            win.new_tab(url=None if message in ("", "raise") else message)
            win.showNormal()
            win.raise_()
            win.activateWindow()
        conn.readyRead.connect(read)

    server.newConnection.connect(handoff)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
