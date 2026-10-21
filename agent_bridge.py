"""Agent bridge: lets a script on this machine drive the running browser.

This is the browser's "extension for Claude": a second local socket
(`browser-agent`, next to the single-instance one) speaking one JSON
object per line. A client sends {"op": ..., ...} and gets exactly one
{"ok": true/false, ...} line back, however long the browser takes to
answer (page JS is asynchronous, so the reply comes when the page has
spoken, not when the request was read).

Everything works on tabs that are not the visible one and while the
browser is not the focused window -- a hidden tab keeps its own DOM --
so a script can ask a page questions without ever taking the screen
away from whoever is using the PC. Nothing here raises the window.

Ops (tab = id from "tabs", or omitted for the current tab):
  ping                       -> {"ok": true, "pid": ...}
  tabs                       -> {"tabs": [{"id","index","url","title",
                                  "current","loading"}]}
  open  url [switch]         -> opens a tab (background unless switch)
  close tab
  select tab                 -> makes it the visible tab
  nav   tab url
  reload tab
  info  tab                  -> url/title/loading of one tab
  js    tab code [world]     -> runs JS; world "app" (default) or "main"
  text  tab [selector]       -> innerText of the page or a node
  html  tab [selector]       -> outerHTML (capped at 2 MB)
  wait  tab selector [timeout_ms] [gone] -> waits for a node (or its absence)
  click tab selector [index] -> real DOM click on the nth match
  type  tab selector text [clear] [enter] -> focuses and types
  key   tab name             -> a real key press (Enter, Escape, Tab, ...)
  scroll tab [y|"bottom"]
  shot  tab path             -> PNG of the view (best on the visible tab)
  pdf   tab path             -> the page printed to a PDF file
  markdown tab [selector]    -> the readable part of the page as Markdown
  box   tab selector         -> where an element is and what it looks like
  find  tab text [limit]     -> elements by their words, each with a selector
  fill  tab fields           -> {"selector": "value", ...} into a form
  idle  tab [quiet] [timeout]-> waits until the page stops fetching things
  links tab [pattern]        -> every link, filtered
  tables tab [index]         -> the page's tables as rows
  console tab [clear]        -> what the page logged, and what it threw
  dialog tab [answer]        -> what alert/confirm/prompt get told
  cookies [host]             -> cookie names for a site, never their values
  bookmarks [text|add]       -> search the bookmarks, or add a page
  downloads                  -> what has been downloaded
  notify text                -> a line in the corner of the browser
  restart                    -> the browser's own relaunch (keeps tabs)

Off switch: config "agentBridge": false, or BROWSER_NO_AGENT=1.
The socket is a user-owned Unix socket in the temp directory; only
processes running as the same user can reach it.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QApplication

SOCKET_NAME = "browser-agent"
HTML_CAP = 2 * 1024 * 1024

APP_WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld.value
MAIN_WORLD = QWebEngineScript.ScriptWorldId.MainWorld.value

KEYS = {
    "enter": Qt.Key.Key_Return, "return": Qt.Key.Key_Return,
    "tab": Qt.Key.Key_Tab, "escape": Qt.Key.Key_Escape,
    "esc": Qt.Key.Key_Escape, "backspace": Qt.Key.Key_Backspace,
    "delete": Qt.Key.Key_Delete, "space": Qt.Key.Key_Space,
    "up": Qt.Key.Key_Up, "down": Qt.Key.Key_Down,
    "left": Qt.Key.Key_Left, "right": Qt.Key.Key_Right,
    "home": Qt.Key.Key_Home, "end": Qt.Key.Key_End,
    "pageup": Qt.Key.Key_PageUp, "pagedown": Qt.Key.Key_PageDown,
    "f5": Qt.Key.Key_F5,
}
KEY_TEXT = {"enter": "\r", "return": "\r", "tab": "\t", "space": " "}


def socket_path():
    """Where the socket lives: QLocalServer puts a bare name into
    QDir::tempPath(), which is $TMPDIR or /tmp."""
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", SOCKET_NAME)


def _json_or(raw, fallback):
    """What the page handed back, parsed -- or the fallback.

    The page answers with a JSON string rather than an object because
    runJavaScript can only bring back what Qt can convert, and a string
    always converts."""
    if raw in (None, ""):
        return fallback
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return fallback


def _js_string(s):
    return json.dumps("" if s is None else str(s))


# --- the page-side helpers every DOM op is built from ---------------
# One finder for every op that takes a selector, and it understands
# three things a plain querySelector does not:
#   * "a >>> b" steps through an iframe or a shadow root -- a selector
#     that cannot reach into either is a selector that cannot touch
#     half the pages that exist;
#   * an index, for the third button that looks like the other two;
#   * a shadow root that is closed is honestly out of reach, and the
#     answer is null rather than a guess.
_FIND = """
(function(sel, index){
  var parts = String(sel).split(">>>");
  var root = document, el = null;
  for (var p = 0; p < parts.length; p++) {
    var one = parts[p].trim();
    if (!one) continue;
    var last = p === parts.length - 1;
    if (last) {
      var all = root.querySelectorAll(one);
      return all.length > index ? all[index] : null;
    }
    el = root.querySelector(one);
    if (!el) return null;
    if (el.shadowRoot) { root = el.shadowRoot; continue; }
    if (el.contentDocument) { root = el.contentDocument; continue; }
    return null;
  }
  return el;
})"""

_TEXT_JS = """
(function(sel){
  var el = sel ? FIND(sel, 0) : document.body;
  if (!el) return null;
  return el.innerText !== undefined ? el.innerText : el.textContent;
})(%s)""".replace("FIND", _FIND)

_HTML_JS = """
(function(sel, cap){
  var el = sel ? FIND(sel, 0) : document.documentElement;
  if (!el) return null;
  var h = el.outerHTML;
  return h.length > cap ? h.slice(0, cap) : h;
})(%s, %d)""".replace("FIND", _FIND)

_EXISTS_JS = ("!!" + _FIND + "(%s, 0)")

# a ref from the last tree: the element is still in window.__agentRefs,
# which is what makes "click 7" possible at all
_CLICK_REF_JS = """
(function(at){
  var el = (window.__agentRefs || [])[at];
  if (!el) return "no-ref";
  el.scrollIntoView({block: "center"});
  var r = el.getBoundingClientRect();
  var o = {bubbles: true, cancelable: true, view: window,
           clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
  el.dispatchEvent(new PointerEvent("pointerdown", o));
  el.dispatchEvent(new MouseEvent("mousedown", o));
  if (el.focus) el.focus();
  el.dispatchEvent(new PointerEvent("pointerup", o));
  el.dispatchEvent(new MouseEvent("mouseup", o));
  el.click();
  return "clicked";
})(%d)"""

_TYPE_REF_JS = """
(function(at, text, clear){
  var el = (window.__agentRefs || [])[at];
  if (!el) return "no-ref";
  el.focus();
  if (clear && "value" in el) el.value = "";
  if ("value" in el) {
    el.value = (el.value || "") + text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  } else {
    el.textContent = text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
  }
  return "typed";
})(%d, %s, %s)"""

_CLICK_JS = """
(function(sel, index){
  var el = FIND(sel, index);
  if (!el) return "no-match";
  el.scrollIntoView({block: "center"});
  var r = el.getBoundingClientRect();
  var o = {bubbles: true, cancelable: true, view: window,
           clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
  el.dispatchEvent(new PointerEvent("pointerdown", o));
  el.dispatchEvent(new MouseEvent("mousedown", o));
  if (el.focus) el.focus();
  el.dispatchEvent(new PointerEvent("pointerup", o));
  el.dispatchEvent(new MouseEvent("mouseup", o));
  el.click();
  return "clicked";
})(%s, %d)""".replace("FIND", _FIND)

# React-style apps ignore a plain .value assignment; the native setter
# plus an input event is what they listen to. A contenteditable editor
# (ProseMirror, Draft, Lexical) only reacts to execCommand("insertText").
_TYPE_JS = """
(function(sel, text, clear){
  var el = FIND(sel, 0);
  if (!el) return "no-match";
  el.scrollIntoView({block: "center"});
  el.focus();
  var tag = (el.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") {
    var proto = tag === "input" ? HTMLInputElement.prototype
                                : HTMLTextAreaElement.prototype;
    var set = Object.getOwnPropertyDescriptor(proto, "value").set;
    var value = clear ? text : (el.value + text);
    set.call(el, value);
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
    return "typed";
  }
  if (el.isContentEditable) {
    if (clear) {
      document.execCommand("selectAll", false, null);
      document.execCommand("delete", false, null);
    }
    var ok = document.execCommand("insertText", false, text);
    if (!ok) {
      el.textContent = (clear ? "" : el.textContent) + text;
      el.dispatchEvent(new InputEvent("input", {bubbles: true,
                       inputType: "insertText", data: text}));
    }
    return "typed";
  }
  return "not-editable";
})(%s, %s, %s)""".replace("FIND", _FIND)

_SCROLL_JS = """
(function(y){
  if (y === "bottom") window.scrollTo(0, document.documentElement.scrollHeight);
  else window.scrollTo(0, y);
  return window.scrollY;
})(%s)"""


# ---- the scripts the newer ops run -----------------------------------
# All of them answer with JSON so the bridge can hand the reply straight
# on without a second round trip.

_MARKDOWN_JS = """
(function (sel) {
  var root = sel ? document.querySelector(sel) : document.body;
  if (!root) return null;
  // the readable part of the page, not its furniture
  var drop = "nav, header, footer, aside, script, style, noscript, form,"
    + " [aria-hidden=true], .nav, .menu, .sidebar, .cookie, .consent";
  var clone = root.cloneNode(true);
  clone.querySelectorAll(drop).forEach(function (el) { el.remove(); });
  var out = [];
  function walk(node) {
    if (node.nodeType === 3) {
      var text = node.nodeValue.replace(/\\s+/g, " ");
      if (text.trim()) out.push(text);
      return;
    }
    if (node.nodeType !== 1) return;
    var tag = node.tagName.toLowerCase();
    if (tag === "a" && node.getAttribute("href")) {
      var label = (node.textContent || "").replace(/\\s+/g, " ").trim();
      if (label) out.push("[" + label + "](" + node.href + ")");
      return;
    }
    if (tag === "img") {
      if (node.alt) out.push("![" + node.alt + "](" + node.src + ")");
      return;
    }
    if (/^h[1-6]$/.test(tag)) out.push("\\n\\n" + "#".repeat(+tag[1]) + " ");
    else if (tag === "li") out.push("\\n- ");
    else if (tag === "br") out.push("\\n");
    else if (/^(p|div|section|article|tr|pre|blockquote|ul|ol|table)$/.test(tag))
      out.push("\\n\\n");
    else if (tag === "code") out.push("`");
    for (var i = 0; i < node.childNodes.length; i++) walk(node.childNodes[i]);
    if (tag === "code") out.push("`");
  }
  walk(clone);
  return out.join("").replace(/\\n{3,}/g, "\\n\\n").trim();
})(%s)"""

_BOX_JS = """
(function (sel) {
  var el = document.querySelector(sel);
  if (!el) return null;
  var r = el.getBoundingClientRect(), cs = getComputedStyle(el);
  return JSON.stringify({
    x: Math.round(r.left), y: Math.round(r.top),
    width: Math.round(r.width), height: Math.round(r.height),
    inView: r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
    visible: !!(r.width || r.height) && cs.visibility !== "hidden"
             && cs.display !== "none" && +cs.opacity > 0.05,
    display: cs.display, position: cs.position, zIndex: cs.zIndex,
    color: cs.color, background: cs.backgroundColor,
    font: cs.fontSize + " " + cs.fontFamily.split(",")[0],
    text: (el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 200),
    tag: el.tagName.toLowerCase(), id: el.id || "",
    classes: typeof el.className === "string" ? el.className : ""
  });
})(%s)"""

_FILL_JS = """
(function (pairs) {
  var done = [], missed = [];
  Object.keys(pairs).forEach(function (sel) {
    var el = document.querySelector(sel);
    if (!el) { missed.push(sel); return; }
    var value = pairs[sel];
    var tag = el.tagName.toLowerCase();
    if (tag === "select") {
      el.value = value;
    } else if (el.type === "checkbox" || el.type === "radio") {
      el.checked = !!value && value !== "false";
    } else {
      el.focus();
      el.value = value;
    }
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
    done.push(sel);
  });
  return JSON.stringify({filled: done, missing: missed});
})(%s)"""

_IDLE_COUNT_JS = """
(function () {
  try { return performance.getEntriesByType("resource").length; }
  catch (e) { return 0; }
})()"""

_IDLE_JS = """
(function (quiet, cap) {
  return new Promise(function (resolve) {
    var last = performance.now();
    var seen = performance.getEntriesByType("resource").length;
    var started = performance.now();
    var obs = null;
    try {
      obs = new PerformanceObserver(function (list) {
        seen += list.getEntries().length;
        last = performance.now();
      });
      obs.observe({type: "resource", buffered: false});
    } catch (e) {}
    var timer = setInterval(function () {
      var now = performance.now();
      if (now - last >= quiet || now - started > cap) {
        clearInterval(timer);
        if (obs) obs.disconnect();
        resolve(JSON.stringify({idle: now - last >= quiet,
                                requests: seen,
                                waited: Math.round(now - started)}));
      }
    }, 50);
  });
})(%d, %d)"""

_LINKS_JS = """
(function (pattern) {
  var re = pattern ? new RegExp(pattern, "i") : null;
  var out = [];
  document.querySelectorAll("a[href]").forEach(function (a) {
    if (out.length >= 500) return;
    var text = (a.textContent || "").replace(/\\s+/g, " ").trim();
    if (re && !re.test(a.href) && !re.test(text)) return;
    out.push({text: text.slice(0, 120), url: a.href});
  });
  return JSON.stringify(out);
})(%s)"""

_TABLES_JS = """
(function (which) {
  var out = [];
  document.querySelectorAll("table").forEach(function (t, n) {
    if (which !== null && n !== which) return;
    var rows = [];
    t.querySelectorAll("tr").forEach(function (tr) {
      var cells = [];
      tr.querySelectorAll("th, td").forEach(function (c) {
        cells.push((c.textContent || "").replace(/\\s+/g, " ").trim());
      });
      if (cells.length) rows.push(cells);
    });
    if (rows.length) out.push(rows);
  });
  return JSON.stringify(out);
})(%s)"""

_FINDTEXT_JS = """
(function (needle, limit) {
  var want = String(needle).toLowerCase();
  var out = [];
  var all = document.querySelectorAll("a, button, input, [role=button],"
    + " label, h1, h2, h3, h4, li, td, th, span, div, p, summary");
  function selectorFor(el) {
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    while (el && el.nodeType === 1 && parts.length < 6) {
      var part = el.tagName.toLowerCase();
      if (el.id) { parts.unshift("#" + CSS.escape(el.id)); break; }
      var parent = el.parentElement;
      if (parent) {
        var same = [].slice.call(parent.children).filter(function (k) {
          return k.tagName === el.tagName;
        });
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(el) + 1) + ")";
      }
      parts.unshift(part);
      el = el.parentElement;
    }
    return parts.join(" > ");
  }
  for (var i = 0; i < all.length && out.length < limit; i++) {
    var el = all[i];
    var own = "";
    for (var k = 0; k < el.childNodes.length; k++)
      if (el.childNodes[k].nodeType === 3) own += el.childNodes[k].nodeValue;
    own = own.replace(/\\s+/g, " ").trim();
    var value = el.value || el.getAttribute("aria-label") || "";
    var hay = (own + " " + value).toLowerCase();
    if (!hay.trim() || hay.indexOf(want) < 0) continue;
    var r = el.getBoundingClientRect();
    out.push({selector: selectorFor(el), tag: el.tagName.toLowerCase(),
              text: (own || value).slice(0, 120),
              visible: !!(r.width && r.height)});
  }
  return JSON.stringify(out);
})(%s, %d)"""


class AgentBridge:
    def __init__(self, win):
        self.win = win
        self.server = QLocalServer()
        self._next_id = 1
        # his settings, so the permission levels and the audit log are
        # the browser's own config rather than a second one of ours
        self.config = getattr(win, "config", None)
        self.listeners = []        # the open event-stream connections
        self.watches = {}          # what is being watched, by id
        self._watch_id = 1
        self.macro = None          # the recording in progress
        self.hooks_ran = []        # what a hook was last run for

    # ---- lifecycle ---------------------------------------------------
    def listen(self):
        # 0700 regardless of the umask: whoever reaches this socket can run
        # JS in every tab, logged-in ones included
        self.server.setSocketOptions(
            QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(SOCKET_NAME):
            # a dead predecessor's socket file; nobody else uses this name
            QLocalServer.removeServer(SOCKET_NAME)
            if not self.server.listen(SOCKET_NAME):
                return False
        self.server.newConnection.connect(self._accept)
        return True

    def close(self):
        self.server.close()
        QLocalServer.removeServer(SOCKET_NAME)

    def _accept(self):
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            buf = bytearray()

            def read(conn=conn, buf=buf):
                buf.extend(bytes(conn.readAll()))
                while b"\n" in buf:
                    line, _, rest = bytes(buf).partition(b"\n")
                    del buf[:len(line) + 1]
                    self._dispatch(conn, line)
            conn.readyRead.connect(read)

    def _reply(self, conn, payload):
        if conn.state() != QLocalSocket.LocalSocketState.ConnectedState:
            return
        conn.write((json.dumps(payload) + "\n").encode())
        conn.flush()

    # ---- tabs --------------------------------------------------------
    def _views(self):
        out = []
        tabs = self.win.tabs
        for i in range(tabs.count()):
            v = tabs.widget(i)
            if v is None or self.win._is_header(v) or not hasattr(v, "url"):
                continue
            if not hasattr(v, "_agent_id"):
                v._agent_id = self._next_id
                self._next_id += 1
            out.append((i, v))
        return out

    def _view_url(self, v):
        return (v.url().toString() or getattr(v, "_pending", "")
                or getattr(v, "_requested", "") or "")

    def _find(self, tab):
        if tab in (None, "", "current"):
            v = self.win.current()
            if v is None or self.win._is_header(v) or not hasattr(v, "url"):
                return None
            self._views()  # make sure it carries an id
            return v
        for _i, v in self._views():
            if v._agent_id == tab:
                return v
        return None

    def _tab_info(self, index, v):
        return {"id": v._agent_id, "index": index, "url": self._view_url(v),
                "title": v.title() if hasattr(v, "title") else "",
                "current": v is self.win.current(),
                "loading": bool(getattr(v, "_agent_loading", False))}

    # ---- what a caller is allowed to do ------------------------------
    #: the ops that only look. Everything else changes something -- a
    #: tab, a page, a file on disk -- and needs full permission.
    READ_OPS = frozenset({
        "ping", "tabs", "info", "text", "html", "box", "find", "links",
        "tables", "console", "cookies", "bookmarks", "downloads",
        "markdown", "tree", "network", "groups", "audit", "events",
        "history",
    })
    #: and the ops that are off unless he says otherwise, whatever the
    #: level: reading his history is not the same kind of thing as
    #: reading a page.
    GUARDED_OPS = frozenset({"history"})

    def level(self):
        """off, read or full -- full unless he has said otherwise."""
        want = str((self.config or {}).get("bridgeLevel") or "full")
        return want if want in ("off", "read", "full") else "full"

    def allowed(self, op, url=""):
        """Whether this op may run at all, and on this page.

        Three gates, in order: the level, his list of ops, and his list
        of sites. Each one is "everything" when he has not written a
        list, because a browser that refuses everything until it is
        configured is a browser nobody configures."""
        level = self.level()
        # the one op that is never refused: a client that cannot find
        # out it is read-only cannot tell him why anything failed, and
        # a client that cannot set the level back has locked him out of
        # his own browser
        if op == "permissions":
            return True, ""
        if level == "off":
            return False, "bridge-off"
        if level == "read" and op not in self.READ_OPS:
            return False, "bridge-read-only"
        if op in self.GUARDED_OPS \
                and not (self.config or {}).get("bridgeHistory", False):
            return False, "op-not-allowed"
        rows = (self.config or {}).get("bridgeOps")
        if isinstance(rows, list) and rows and op not in rows:
            return False, "op-not-allowed"
        sites = (self.config or {}).get("bridgeSites")
        if isinstance(sites, list) and sites and url:
            host = QUrl(url).host().lower().removeprefix("www.")
            if host and not any(host == one or host.endswith("." + one)
                                for one in sites):
                return False, "site-not-allowed"
        return True, ""

    def note(self, op, target="", answer=""):
        """One line in the audit log.

        Every op, with the time and what it was aimed at -- so there is
        an answer to "what has been driving this browser" that does not
        depend on trusting the thing that was driving it."""
        rows = self.audit_rows()
        rows.append({"t": time.time(), "op": str(op),
                     "target": str(target)[:200],
                     "answer": str(answer)[:80]})
        del rows[:-400]
        if self.config is not None:
            self.config["bridgeAudit"] = rows
        return rows

    def audit_rows(self):
        rows = (self.config or {}).get("bridgeAudit")
        return rows if isinstance(rows, list) else []

    # ---- dispatch ----------------------------------------------------
    def _dispatch(self, conn, line):
        try:
            req = json.loads(line.decode())
            if not isinstance(req, dict):
                raise ValueError("request must be an object")
            op = str(req.get("op", ""))
            handler = getattr(self, "op_" + op, None)
            if handler is None:
                raise ValueError("unknown op: " + op)
            target = str(req.get("url") or req.get("selector")
                         or req.get("tab") or "")
            ok, why = self.allowed(op, str(req.get("url") or ""))
            if not ok:
                self.note(op, target, why)
                self._reply(conn, {"ok": False, "error": why})
                return
            self.note(op, target, "run")
            handler(conn, req)
        except Exception as e:  # never let one bad request kill the bridge
            self._reply(conn, {"ok": False, "error": "%s: %s"
                               % (type(e).__name__, e)})

    def _need_view(self, conn, req):
        v = self._find(req.get("tab"))
        if v is None:
            self._reply(conn, {"ok": False, "error": "no-such-tab"})
        return v

    def _run(self, v, code, done, world=APP_WORLD):
        v.page().runJavaScript(code, world, done)

    @staticmethod
    def _gone(v):
        from PyQt6 import sip
        return sip.isdeleted(v) or sip.isdeleted(v.page())

    # ---- ops ---------------------------------------------------------
    def op_ping(self, conn, req):
        self._reply(conn, {"ok": True, "pid": os.getpid()})

    def op_tabs(self, conn, req):
        self._reply(conn, {"ok": True, "tabs": [self._tab_info(i, v)
                                                 for i, v in self._views()]})

    def watch_window(self):
        """Hook the window's own signals, so an event stream has
        something to stream.

        Everything here is a thing the browser already notices: a load
        finishing, a title changing, a download landing, a dialog going
        up. The bridge adds no watching of its own."""
        win = self.win
        try:
            win.tabs.currentChanged.connect(
                lambda index: self.emit(
                    "switched", tab=self._id_at(index)))
        except (AttributeError, RuntimeError):
            pass
        self._hooked = set()
        timer = QTimer(win)
        timer.timeout.connect(self._hook_new_tabs)
        timer.start(1500)
        self._hook_timer = timer
        self._hook_new_tabs()
        return True

    def _id_at(self, index):
        view = self.win.tabs.widget(index) if index >= 0 else None
        return getattr(view, "_agent_id", None) if view is not None else None

    def _hook_new_tabs(self):
        """Any tab we have not hooked yet gets its signals connected."""
        held = getattr(self, "_hooked", None)
        if held is None:
            held = self._hooked = set()
        for _i, v in self._views():
            if id(v) in held:
                continue
            held.add(id(v))
            try:
                v.loadFinished.connect(
                    lambda ok, v=v: self.emit(
                        "loaded", tab=getattr(v, "_agent_id", None),
                        url=self._view_url(v), ok=bool(ok)))
                v.titleChanged.connect(
                    lambda text, v=v: self.emit(
                        "title", tab=getattr(v, "_agent_id", None),
                        title=str(text)[:200]))
            except (AttributeError, RuntimeError):
                continue
        return len(held)

    def op_open(self, conn, req):
        url = str(req.get("url") or "")
        if not url:
            raise ValueError("url required")
        switch = bool(req.get("switch", False))
        # which virtual browser, or a private tab: an agent that can
        # only ever open in the main jar cannot sign in as anybody else
        session = req.get("session")
        private = bool(req.get("private", False))
        before = {id(v) for _i, v in self._views()}
        self.win.new_tab(url=url, switch=switch,
                         session=str(session) if session else None,
                         private=private)
        new = [(i, v) for i, v in self._views() if id(v) not in before]
        if not new:
            raise RuntimeError("tab did not open")
        i, v = new[-1]
        v._agent_loading = True
        # marked as the agent's own, so "mine" can list them and the
        # idle sweep can close them without ever touching one of his
        v._agent_owned = True
        v._agent_touched = time.time()
        v.loadFinished.connect(lambda ok, v=v: setattr(v, "_agent_loading", False))
        self._reply(conn, {"ok": True, "tab": self._tab_info(i, v)})

    def op_close(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self.win.close_tab(self.win.tabs.indexOf(v))
        self._reply(conn, {"ok": True})

    def op_select(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self.win.tabs.setCurrentWidget(v)
        self._reply(conn, {"ok": True})

    def op_nav(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        url = str(req.get("url") or "")
        if not url:
            raise ValueError("url required")
        v._agent_loading = True
        v.loadFinished.connect(lambda ok, v=v: setattr(v, "_agent_loading", False))
        v.load(QUrl(url))
        self._reply(conn, {"ok": True})

    def op_reload(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        v.reload()
        self._reply(conn, {"ok": True})

    def op_info(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self._reply(conn, {"ok": True,
                           "tab": self._tab_info(self.win.tabs.indexOf(v), v)})

    def op_js(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        code = str(req.get("code") or "")
        world = MAIN_WORLD if req.get("world") == "main" else APP_WORLD
        self._run(v, code,
                  lambda r: self._reply(conn, {"ok": True, "result": r}),
                  world)

    def op_text(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self._run(v, _TEXT_JS % _js_string(req.get("selector")),
                  lambda r: self._reply(conn, {"ok": r is not None,
                                               "text": r,
                                               **({} if r is not None
                                                  else {"error": "no-match"})}))

    def op_html(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self._run(v, _HTML_JS % (_js_string(req.get("selector")), HTML_CAP),
                  lambda r: self._reply(conn, {"ok": r is not None,
                                               "html": r,
                                               **({} if r is not None
                                                  else {"error": "no-match"})}))

    def op_wait(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        sel = str(req.get("selector") or "")
        if not sel:
            raise ValueError("selector required")
        gone = bool(req.get("gone", False))
        timeout = int(req.get("timeout", 15000))
        code = _EXISTS_JS % _js_string(sel)
        waited = [0]
        step = 200

        def poll():
            def got(r):
                found = bool(r)
                if found != gone:
                    self._reply(conn, {"ok": True, "found": found,
                                       "waited": waited[0]})
                    return
                if waited[0] >= timeout:
                    self._reply(conn, {"ok": False, "error": "timeout",
                                       "found": found, "waited": waited[0]})
                    return
                waited[0] += step
                QTimer.singleShot(step, poll)
            if conn.state() != QLocalSocket.LocalSocketState.ConnectedState:
                return  # the caller gave up; stop polling
            if self._gone(v):
                self._reply(conn, {"ok": False, "error": "no-such-tab",
                                   "waited": waited[0]})
                return  # the tab was closed while we waited
            self._run(v, code, got)
        poll()

    def op_click(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        sel = str(req.get("selector") or "")
        if req.get("ref") not in (None, ""):
            # a number out of the last tree instead of a selector: the
            # element itself is still on window.__agentRefs
            # the tree numbers from one; the array is indexed from
            # zero, and an agent that is told "ref 7" must get the
            # seventh thing
            code = _CLICK_REF_JS % (int(req.get("ref")) - 1)
            self._run(v, code, lambda r: self._reply(
                conn, {"ok": r == "clicked", "result": r}))
            return
        if not sel:
            raise ValueError("selector or ref required")
        code = _CLICK_JS % (_js_string(sel), int(req.get("index", 0)))
        self._run(v, code, lambda r: self._reply(
            conn, {"ok": r == "clicked", "result": r}))

    def op_type(self, conn, req):
        v = self._need_view(conn, req)
        if v is not None and req.get("ref") not in (None, ""):
            code = _TYPE_REF_JS % (int(req.get("ref")) - 1,
                                   _js_string(str(req.get("text") or "")),
                                   "true" if req.get("clear") else "false")
            self._run(v, code, lambda r: self._reply(
                conn, {"ok": r == "typed", "result": r}))
            return
        if v is None:
            return
        sel = str(req.get("selector") or "")
        if not sel:
            raise ValueError("selector required")
        text = str(req.get("text") or "")
        clear = "true" if req.get("clear", False) else "false"
        enter = bool(req.get("enter", False))
        code = _TYPE_JS % (_js_string(sel), _js_string(text), clear)

        def done(r):
            if r == "typed" and enter:
                self._press(v, "enter")
            self._reply(conn, {"ok": r == "typed", "result": r})
        self._run(v, code, done)

    def _press(self, v, name):
        name = str(name)
        low = name.lower()
        if low in KEYS:
            qtkey, text = KEYS[low], KEY_TEXT.get(low, "")
        elif len(name) == 1:
            qtkey, text = Qt.Key(ord(name.upper())), name
        else:
            raise ValueError("unknown key: " + name)
        target = v.focusProxy() or v
        mods = Qt.KeyboardModifier.NoModifier
        QApplication.postEvent(target, QKeyEvent(
            QKeyEvent.Type.KeyPress, qtkey, mods, text))
        QApplication.postEvent(target, QKeyEvent(
            QKeyEvent.Type.KeyRelease, qtkey, mods, text))

    def op_key(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self._press(v, req.get("key") or "enter")
        self._reply(conn, {"ok": True})

    def op_scroll(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        y = req.get("y", "bottom")
        arg = json.dumps("bottom") if y == "bottom" else str(int(y))
        self._run(v, _SCROLL_JS % arg,
                  lambda r: self._reply(conn, {"ok": True, "y": r}))

    def op_shot(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        path = str(req.get("path") or "")
        if not path:
            raise ValueError("path required")
        pix = v.grab()
        ok = pix.save(path, "PNG")
        self._reply(conn, {"ok": bool(ok), "path": path,
                           "visible": v is self.win.current(),
                           "width": pix.width(), "height": pix.height()})

    # ---- the ops a script driving a page needs beyond clicking --------

    def op_markdown(self, conn, req):
        """The readable part of a page, as Markdown — what a model
        should be handed instead of 2 MB of HTML."""
        v = self._need_view(conn, req)
        if v is None:
            return
        self._run(v, _MARKDOWN_JS % _js_string(req.get("selector")),
                  lambda r: self._reply(conn, {"ok": r is not None,
                                               "text": r or ""}))

    def op_box(self, conn, req):
        """Where an element is, whether it can be seen, and what it
        looks like — the questions asked before a click."""
        v = self._need_view(conn, req)
        if v is None:
            return
        self._run(v, _BOX_JS % _js_string(req.get("selector")),
                  lambda r: self._reply(conn, self._json_reply(r, "box")))

    def op_fill(self, conn, req):
        """A whole form from one selector-to-value map, with the input
        and change events a page listens for."""
        v = self._need_view(conn, req)
        if v is None:
            return
        fields = req.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("fields required")
        self._run(v, _FILL_JS % json.dumps(fields),
                  lambda r: self._reply(conn, self._json_reply(r, "result")))

    def op_idle(self, conn, req):
        """Waits until the page has made no request for a while — the
        wait that means "it has finished arriving" on a modern site.

        Polled from here rather than waited for inside the page: this
        engine's runJavaScript hands back a Promise object rather than
        what the promise resolves to, so a script that waits in the page
        can never answer. The count of resource timings is the page's
        own and costs nothing to read."""
        v = self._need_view(conn, req)
        if v is None:
            return
        quiet = max(50, int(req.get("quiet") or 700))
        cap = max(quiet, int(req.get("timeout") or 15000))
        state = {"last": 0, "seen": -1, "waited": 0, "done": False}

        def tick():
            if state["done"]:
                return
            if self._gone(v):
                state["done"] = True
                self._reply(conn, {"ok": False, "error": "no-such-tab"})
                return

            def got(count):
                if state["done"]:
                    return
                count = count if isinstance(count, int) else 0
                if count != state["seen"]:
                    state["seen"] = count
                    state["last"] = state["waited"]
                if (state["waited"] - state["last"] >= quiet
                        or state["waited"] >= cap):
                    state["done"] = True
                    self._reply(conn, {"ok": True, "idle": {
                        "idle": state["waited"] - state["last"] >= quiet,
                        "requests": count, "waited": state["waited"]}})
                    return
                state["waited"] += 100
                QTimer.singleShot(100, tick)
            self._run(v, _IDLE_COUNT_JS, got)
        tick()

    def op_links(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        self._run(v, _LINKS_JS % _js_string(req.get("pattern")),
                  lambda r: self._reply(conn, self._json_reply(r, "links")))

    def op_tables(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        which = req.get("index")
        self._run(v, _TABLES_JS % ("null" if which is None else int(which)),
                  lambda r: self._reply(conn, self._json_reply(r, "tables")))

    def op_find(self, conn, req):
        """Elements by the words on them, with a selector for each —
        the way a person says "click the blue Save button"."""
        v = self._need_view(conn, req)
        if v is None:
            return
        text = str(req.get("text") or "")
        if not text:
            raise ValueError("text required")
        self._run(v, _FINDTEXT_JS % (_js_string(text),
                                     int(req.get("limit") or 20)),
                  lambda r: self._reply(conn, self._json_reply(r, "found")))

    def op_console(self, conn, req):
        """What the page has written to the console, and the errors it
        has thrown, since the tab was opened."""
        v = self._need_view(conn, req)
        if v is None:
            return
        log = list(getattr(v.page(), "console_log", []))
        if req.get("clear"):
            try:
                v.page().console_log.clear()
            except AttributeError:
                pass
        self._reply(conn, {"ok": True, "messages": log[-200:]})

    def op_dialog(self, conn, req):
        """What the page's next alert/confirm/prompt gets told, and what
        the last ones said. Without this a script driving a page stops
        dead at the first confirm()."""
        v = self._need_view(conn, req)
        if v is None:
            return
        page = v.page()
        if "answer" in req:
            answer = req.get("answer")
            page.dialog_answer = (answer if isinstance(answer, bool)
                                  else str(answer))
        self._reply(conn, {"ok": True,
                           "last": list(getattr(page, "dialog_log", []))[-10:],
                           "answer": getattr(page, "dialog_answer", None)})

    def op_pdf(self, conn, req):
        """The page as a PDF, printed by the engine itself."""
        v = self._need_view(conn, req)
        if v is None:
            return
        path = str(req.get("path") or "")
        if not path:
            raise ValueError("path required")
        done = {"sent": False}

        def finished(data):
            if done["sent"]:
                return
            done["sent"] = True
            try:
                raw = bytes(data) if data else b""
                if raw:
                    with open(path, "wb") as fh:
                        fh.write(raw)
                    self._reply(conn, {"ok": True, "path": path,
                                       "bytes": len(raw)})
                else:
                    self._reply(conn, {"ok": False, "error": "no-pdf"})
            except OSError as exc:
                self._reply(conn, {"ok": False, "error": str(exc)})
        v.page().printToPdf(finished)

    def op_cookies(self, conn, req):
        """Which cookies a site has, by name — never their values. A
        script may need to know whether a login cookie is there; it has
        no business reading it."""
        host = str(req.get("host") or "").lower().removeprefix("www.")
        found = []
        for name, domain, expiry in self.win.known_cookies():
            short = domain.lstrip(".").removeprefix("www.")
            if host and not (short == host or short.endswith("." + host)
                             or host.endswith("." + short)):
                continue
            found.append({"name": name, "domain": domain, "expires": expiry})
        self._reply(conn, {"ok": True, "cookies": found[:500]})

    def op_bookmarks(self, conn, req):
        """Search the bookmarks, or add a page to them."""
        action = str(req.get("action") or "search")
        if action == "add":
            url = str(req.get("url") or "")
            if not url:
                v = self._find(req.get("tab")) or self.win.current()
                url = v.url().toString() if v is not None else ""
            ok = bool(url) and self.win.add_bookmark_url(
                url, str(req.get("title") or ""))
            self._reply(conn, {"ok": bool(ok), "url": url})
            return
        want = str(req.get("text") or "").lower()
        out = [{"title": e.get("title", ""), "url": e.get("url", "")}
               for e in self.win.bookmarks
               if e.get("type") == "link"
               and (not want or want in (e.get("title", "")
                                         + " " + e.get("url", "")).lower())]
        self._reply(conn, {"ok": True, "bookmarks": out[:200]})

    def op_notify(self, conn, req):
        """A line in the corner of the browser — how a script says it
        has finished without stealing the screen."""
        text = str(req.get("text") or "").strip()
        if not text:
            raise ValueError("text required")
        self.win.flash(text[:200])
        self._reply(conn, {"ok": True})

    def op_downloads(self, conn, req):
        """What has been downloaded, and what is still coming."""
        out = []
        for entry in (self.win.downloads_data() or [])[:200]:
            if isinstance(entry, dict):
                out.append({k: entry.get(k) for k in
                            ("name", "path", "state", "bytes", "total", "url",
                             "done", "size")
                            if k in entry})
        self._reply(conn, {"ok": True, "downloads": out})

    @staticmethod
    def _json_reply(raw, key):
        try:
            return {"ok": raw is not None,
                    key: json.loads(raw) if raw is not None else None}
        except (ValueError, TypeError):
            return {"ok": False, "error": "bad-reply"}

    # ---- the page as something an agent can aim at -------------------
    #: the accessibility tree, with a number on every row. An agent
    #: that has to invent CSS selectors gets them wrong; a numbered
    #: list of what is on the page, with the numbers accepted by click
    #: and type, is the thing it can actually use.
    TREE_JS = """(function (limit) {
      var out = [], at = 0;
      var role = function (el) {
        var r = el.getAttribute("role");
        if (r) return r;
        var tag = el.tagName.toLowerCase();
        if (tag === "a") return "link";
        if (tag === "button") return "button";
        if (tag === "input") return (el.type || "text");
        if (tag === "select") return "select";
        if (tag === "textarea") return "textbox";
        if (/^h[1-6]$/.test(tag)) return "heading";
        if (tag === "img") return "image";
        if (tag === "label") return "label";
        return "";
      };
      var name = function (el) {
        var text = (el.getAttribute("aria-label")
          || el.getAttribute("alt")
          || el.getAttribute("placeholder")
          || el.value
          || (el.textContent || "")).trim();
        return text.replace(/\\s+/g, " ").slice(0, 80);
      };
      var rows = document.querySelectorAll(
        "a[href], button, input:not([type=hidden]), select, textarea,"
        + " [role=button], [role=link], [role=textbox], h1, h2, h3,"
        + " label, img[alt]");
      window.__agentRefs = [];
      for (var i = 0; i < rows.length && out.length < limit; i++) {
        var el = rows[i];
        var box = el.getBoundingClientRect();
        if (box.width < 1 || box.height < 1) continue;
        var kind = role(el);
        if (!kind) continue;
        at++;
        window.__agentRefs.push(el);
        out.push({ref: at, role: kind, name: name(el),
                  x: Math.round(box.left + box.width / 2),
                  y: Math.round(box.top + box.height / 2),
                  w: Math.round(box.width), h: Math.round(box.height),
                  disabled: !!el.disabled});
      }
      return JSON.stringify(out);
    })(%d)"""

    def op_tree(self, conn, req):
        """The page as a numbered list of what can be aimed at."""
        v = self._need_view(conn, req)
        if v is None:
            return
        limit = int(req.get("limit") or 200)
        self._run(v, self.TREE_JS % max(1, min(600, limit)),
                  lambda raw: self._reply(conn, {
                      "ok": True, "tree": _json_or(raw, [])}))

    def _ref_target(self, req):
        """A selector, or a ref from the last tree -- both end up as
        one piece of JavaScript that finds the element."""
        ref = req.get("ref")
        if ref not in (None, ""):
            return "(window.__agentRefs || [])[%d]" % (int(ref) - 1)
        return "document.querySelectorAll(%s)[%d]" % (
            _js_string(str(req.get("selector") or "")),
            int(req.get("index") or 0))

    # ---- what a tab fetched ------------------------------------------
    def op_network(self, conn, req):
        """The requests this tab made: address, kind, size and how long
        it took.

        Out of the page's own Navigation Timing, because that is where
        a transfer size lives -- the engine's request interceptor is
        told the method and the kind but never a size or a status, and
        this op says so rather than inventing them."""
        v = self._need_view(conn, req)
        if v is None:
            return
        code = """(function (limit) {
          var out = [];
          var rows = performance.getEntriesByType("resource");
          for (var i = 0; i < rows.length && out.length < limit; i++) {
            out.push({url: rows[i].name.slice(0, 300),
                      kind: rows[i].initiatorType || "other",
                      size: rows[i].transferSize || 0,
                      ms: Math.round(rows[i].duration)});
          }
          var first = performance.getEntriesByType("navigation")[0];
          if (first) out.unshift({url: location.href.slice(0, 300),
                                  kind: "document",
                                  size: first.transferSize || 0,
                                  ms: Math.round(first.duration)});
          return JSON.stringify(out);
        })(%d)""" % int(req.get("limit") or 200)
        self._run(v, code, lambda raw: self._reply(conn, {
            "ok": True, "requests": _json_or(raw, []),
            "note": "no status codes: the engine does not hand them to "
                    "an embedder"}))

    # ---- a file through the browser's own session --------------------
    def op_download(self, conn, req):
        """Fetch a URL with the tab's cookies and write it to a path.

        Through the page, so it is the session's own cookies and
        referer rather than a fresh anonymous fetch: the page reads it
        as an array buffer and hands the bytes back base64, which is
        the only way across the bridge that does not involve a second
        HTTP client with a different idea of who is logged in."""
        v = self._need_view(conn, req)
        if v is None:
            return
        url = str(req.get("url") or "")
        path = str(req.get("path") or "")
        if not url or not path:
            raise ValueError("url and path required")
        code = """(async function (url) {
          try {
            var r = await fetch(url, {credentials: "include"});
            var buf = await r.arrayBuffer();
            var bytes = new Uint8Array(buf), out = "";
            for (var i = 0; i < bytes.length; i++)
              out += String.fromCharCode(bytes[i]);
            window.__agentFile = JSON.stringify(
              {ok: r.ok, status: r.status, data: btoa(out)});
          } catch (e) {
            window.__agentFile = JSON.stringify(
              {ok: false, status: 0, error: String(e)});
          }
          return "started";
        })(%s)""" % _js_string(url)

        def finish(raw):
            found = _json_or(raw, {}) or {}
            if not found.get("ok"):
                self._reply(conn, {"ok": False,
                                   "error": found.get("error")
                                   or ("status %s" % found.get("status"))})
                return
            import base64
            try:
                data = base64.b64decode(found.get("data") or "")
                with open(path, "wb") as handle:
                    handle.write(data)
            except (OSError, ValueError) as e:
                self._reply(conn, {"ok": False, "error": str(e)})
                return
            self._reply(conn, {"ok": True, "path": path,
                               "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()})

        def wait_for_file(tries=40):
            if self._gone(v):
                self._reply(conn, {"ok": False, "error": "tab-gone"})
                return
            self._run(v, "window.__agentFile || ''", lambda raw: (
                finish(raw) if raw else
                (QTimer.singleShot(150, lambda: wait_for_file(tries - 1))
                 if tries > 0 else
                 self._reply(conn, {"ok": False, "error": "timeout"}))))

        self._run(v, "window.__agentFile = ''; 1",
                  lambda _r: self._run(v, code,
                                       lambda _r2: wait_for_file()))

    # ---- things that happen on their own -----------------------------
    def op_events(self, conn, req):
        """Subscribe to this tab's events, or all of them.

        The connection stays open and every event is one more JSON line
        on it: a load finished, a title changed, a download done, a
        dialog shown, a watch that fired. The client reads lines until
        it hangs up."""
        rows = {"conn": conn, "tab": req.get("tab"),
                "kinds": [str(one) for one in (req.get("kinds") or [])]}
        self.listeners.append(rows)
        self._reply(conn, {"ok": True, "listening": True})
        conn.disconnected.connect(
            lambda: self.listeners.remove(rows)
            if rows in self.listeners else None)

    def emit(self, kind, **what):
        """Tell the open subscriptions that something happened.

        Also where the event hooks fire from, because "run a command
        when a download finishes" and "tell the agent a download
        finished" are the same moment."""
        row = {"event": str(kind), "t": time.time()}
        row.update(what)
        for one in list(self.listeners):
            if one["kinds"] and kind not in one["kinds"]:
                continue
            if one["tab"] not in (None, "", "current") \
                    and what.get("tab") != one["tab"]:
                continue
            try:
                self._reply(one["conn"], row)
            except RuntimeError:
                continue
        self.run_hook(kind, row)
        return row

    def run_hook(self, kind, row):
        """His own command, run when something happens.

        Opt-in and his own program: the event's name and a JSON line on
        standard input, so a shell script can do whatever he wants with
        it. Nothing is run unless he named a command for that event."""
        rows = (self.config or {}).get("eventHooks")
        rows = rows if isinstance(rows, dict) else {}
        command = str(rows.get(kind) or rows.get("*") or "")
        if not command:
            return ""
        program = shutil.which(command.split()[0])
        if not program:
            return ""
        try:
            proc = subprocess.Popen(
                [program] + command.split()[1:] + [str(kind)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            proc.stdin.write((json.dumps(row) + "\n").encode())
            proc.stdin.close()
        except (OSError, BrokenPipeError):
            return ""
        self.hooks_ran.append((kind, command))
        del self.hooks_ran[:-20]
        return command

    def op_watch(self, conn, req):
        """Watch a page, or one element of it, and say when it
        changes.

        A check on a schedule rather than a listener: the thing being
        watched is usually a number on somebody else's page (a queue
        position, a price, a build), and polling it every minute is
        both honest and all the page will allow."""
        v = self._need_view(conn, req)
        if v is None:
            return
        selector = str(req.get("selector") or "body")
        every = max(2, int(req.get("every") or 60))
        which = self._watch_id
        self._watch_id += 1
        row = {"id": which, "tab": getattr(v, "_agent_id", None),
               "selector": selector, "every": every, "was": None,
               "changes": 0}
        self.watches[which] = row
        timer = QTimer(self.win)
        row["timer"] = timer
        timer.timeout.connect(lambda w=which: self._watch_tick(w))
        timer.start(every * 1000)
        self._watch_tick(which)
        self._reply(conn, {"ok": True, "watch": which,
                           "selector": selector, "every": every})

    def _watch_tick(self, which):
        row = self.watches.get(which)
        if row is None:
            return
        v = self._find(row["tab"])
        if v is None or self._gone(v):
            self.stop_watch(which)
            return
        code = ("(function(sel){var el=document.querySelector(sel);"
                "return el ? (el.textContent || '').trim().slice(0, 4000)"
                " : '';})(%s)" % _js_string(row["selector"]))

        def got(raw):
            text = str(raw or "")
            was = row["was"]
            row["was"] = text
            if was is None or text == was:
                return
            row["changes"] += 1
            self.emit("changed", tab=row["tab"], watch=which,
                      selector=row["selector"], was=was[:400],
                      now=text[:400])

        self._run(v, code, got)

    def stop_watch(self, which):
        row = self.watches.pop(int(which), None)
        if row is None:
            return False
        timer = row.get("timer")
        if timer is not None:
            timer.stop()
        return True

    def op_unwatch(self, conn, req):
        """Stop one watch, or all of them."""
        which = req.get("watch")
        if which in (None, "", "all"):
            gone = [self.stop_watch(one) for one in list(self.watches)]
            self._reply(conn, {"ok": True, "stopped": len(gone)})
            return
        self._reply(conn, {"ok": self.stop_watch(which)})

    def op_watches(self, conn, req):
        self._reply(conn, {"ok": True, "watches": [
            {k: v for k, v in row.items() if k != "timer"}
            for row in self.watches.values()]})

    def op_refresh(self, conn, req):
        """Reload this tab every so often -- and not while he is typing
        on it, which is the difference between a useful dashboard and a
        tab that eats what you were writing."""
        v = self._need_view(conn, req)
        if v is None:
            return
        every = int(req.get("every") or 0)
        timer = getattr(v, "_agent_refresh", None)
        if every <= 0:
            if timer is not None:
                timer.stop()
                v._agent_refresh = None
            self._reply(conn, {"ok": True, "every": 0})
            return
        every = max(2, min(86400, every))
        if timer is None:
            timer = v._agent_refresh = QTimer(self.win)
            timer.timeout.connect(lambda v=v: self._refresh_tick(v))
        timer.start(every * 1000)
        self._reply(conn, {"ok": True, "every": every})

    def _refresh_tick(self, v):
        if self._gone(v):
            return
        # not while he is typing in it: the page says when it last saw
        # a key, and a reload mid-sentence is unforgivable
        def got(raw):
            try:
                quiet = float(raw or 0)
            except (TypeError, ValueError):
                quiet = 0
            if quiet and quiet < 5000:
                return
            v.reload()
        self._run(v, "(function(){var t = window.__lastKeyAt || 0;"
                     "return t ? (Date.now() - t) : 0;})()", got)

    # ---- clicks and typing, recorded and played back -----------------
    def op_macro(self, conn, req):
        """Record what he does on a page, and play it back.

        What is recorded is what the page saw: the selector of what was
        clicked and what was typed into it. Played back through the
        bridge's own click and type, so a macro is a list of ops and
        can be read, edited and kept."""
        what = str(req.get("do") or "status")
        if what == "start":
            v = self._need_view(conn, req)
            if v is None:
                return
            self.macro = {"tab": getattr(v, "_agent_id", None),
                          "steps": [], "started": time.time()}
            self._run(v, self.MACRO_JS, lambda _r: self._reply(
                conn, {"ok": True, "recording": True}))
            return
        if what == "stop":
            rows = self._macro_rows()
            if rows is None:
                self._reply(conn, {"ok": False, "error": "not-recording"})
                return
            v = self._find(self.macro["tab"]) if self.macro else None
            name = str(req.get("name") or "")

            def finish(raw):
                steps = _json_or(raw, []) or []
                self.macro["steps"] = steps
                if name and self.config is not None:
                    rows = dict(self.config.get("macros") or {})
                    rows[name] = steps
                    self.config["macros"] = rows
                out = list(steps)
                self.macro = None
                self._reply(conn, {"ok": True, "steps": out,
                                   "name": name})

            if v is None or self._gone(v):
                self._reply(conn, {"ok": True, "steps": [], "name": name})
                self.macro = None
                return
            self._run(v, "window.__macroTake ? window.__macroTake() : '[]'",
                      finish)
            return
        if what == "list":
            rows = (self.config or {}).get("macros") or {}
            self._reply(conn, {"ok": True, "macros": sorted(rows)})
            return
        if what == "play":
            name = str(req.get("name") or "")
            rows = (self.config or {}).get("macros") or {}
            steps = req.get("steps") or rows.get(name) or []
            if not steps:
                self._reply(conn, {"ok": False, "error": "no-such-macro"})
                return
            v = self._need_view(conn, req)
            if v is None:
                return
            self._play_macro(conn, v, list(steps))
            return
        self._reply(conn, {"ok": True,
                           "recording": self.macro is not None,
                           "steps": len((self.macro or {}).get("steps")
                                        or [])})

    def _macro_rows(self):
        return None if self.macro is None else self.macro.get("steps")

    #: what the page writes down while a macro is being recorded. Only
    #: the selector and the value -- never a password field, because a
    #: macro is a file and a password in a file is a password lost.
    MACRO_JS = """(function () {
      if (window.__macroReady) { window.__macroSteps = []; return "again"; }
      window.__macroReady = true;
      window.__macroSteps = [];
      var path = function (el) {
        if (!el || el === document.body) return "body";
        if (el.id) return "#" + el.id;
        if (el.name) return el.tagName.toLowerCase()
          + '[name=' + JSON.stringify(el.name) + ']';
        var at = 0, sib = el;
        while ((sib = sib.previousElementSibling)) at++;
        return path(el.parentElement) + " > "
          + el.tagName.toLowerCase() + ":nth-child(" + (at + 1) + ")";
      };
      document.addEventListener("click", function (e) {
        var el = e.target;
        if (!el || !el.tagName) return;
        window.__macroSteps.push({op: "click", selector: path(el),
                                  t: Date.now()});
      }, true);
      document.addEventListener("change", function (e) {
        var el = e.target;
        if (!el || !("value" in el)) return;
        if (el.type === "password") return;
        window.__macroSteps.push({op: "type", selector: path(el),
                                  text: String(el.value).slice(0, 500),
                                  t: Date.now()});
      }, true);
      window.__macroTake = function () {
        var out = window.__macroSteps || [];
        window.__macroSteps = [];
        return JSON.stringify(out);
      };
      return "recording";
    })()"""

    def _play_macro(self, conn, v, steps, done=None):
        """One step at a time, each after the one before it."""
        results = []

        def step():
            if not steps:
                self._reply(conn, {"ok": True, "played": len(results),
                                   "steps": results})
                return
            one = steps.pop(0)
            kind = str(one.get("op") or "")
            selector = str(one.get("selector") or "")
            if kind == "click":
                code = ("(function(sel){var el=document.querySelector(sel);"
                        "if(!el) return 'missing';"
                        "el.click(); return 'clicked';})(%s)"
                        % _js_string(selector))
            elif kind == "type":
                code = ("(function(sel, text){"
                        "var el=document.querySelector(sel);"
                        "if(!el) return 'missing';"
                        "el.focus(); el.value = text;"
                        "el.dispatchEvent(new Event('input',"
                        " {bubbles: true}));"
                        "el.dispatchEvent(new Event('change',"
                        " {bubbles: true}));"
                        "return 'typed';})(%s, %s)"
                        % (_js_string(selector),
                           _js_string(str(one.get("text") or ""))))
            else:
                results.append({"op": kind, "result": "skipped"})
                QTimer.singleShot(0, step)
                return

            def after(raw):
                results.append({"op": kind, "selector": selector,
                                "result": str(raw or "")})
                QTimer.singleShot(120, step)

            if self._gone(v):
                self._reply(conn, {"ok": False, "error": "tab-gone",
                                   "played": len(results)})
                return
            self._run(v, code, after)

        step()

    def op_autoclick(self, conn, req):
        """A rule that clicks a button for him when it turns up.

        "Still watching?", "Continue", a cookie wall's accept: a
        selector per site, clicked once when it appears. Kept per site
        and done in the page, because the whole point is that it
        happens while nobody is looking."""
        host = str(req.get("host") or "")
        selector = str(req.get("selector") or "")
        rows = dict((self.config or {}).get("autoClick") or {})
        if req.get("remove"):
            rows.pop(host, None)
        elif host and selector:
            keep = [one for one in rows.get(host, [])
                    if one != selector]
            keep.append(selector)
            rows[host] = keep
        if self.config is not None:
            self.config["autoClick"] = rows
        if hasattr(self.win, "refresh_nav"):
            self.win.refresh_nav()
        self._reply(conn, {"ok": True, "rules": rows})

    # ---- the tabs an agent owns --------------------------------------
    def op_mine(self, conn, req):
        """The tabs this bridge opened, and what to do with them.

        An agent that opens tabs and never closes them turns a browser
        into a junk drawer, so they are marked, kept together and can
        be closed in one go -- or by themselves after an idle time."""
        what = str(req.get("do") or "list")
        rows = [(i, v) for i, v in self._views()
                if getattr(v, "_agent_owned", False)]
        if what == "close":
            closed = 0
            for _i, v in rows:
                index = self.win.tabs.indexOf(v)
                if index >= 0:
                    self.win.close_tab(index, ask=False)
                    closed += 1
            self._reply(conn, {"ok": True, "closed": closed})
            return
        if what == "idle":
            after = int(req.get("after") or 0)
            if self.config is not None:
                self.config["agentTabIdle"] = max(0, after)
            self._reply(conn, {"ok": True, "after": after})
            return
        self._reply(conn, {"ok": True,
                           "tabs": [self._tab_info(i, v) for i, v in rows]})

    def close_idle_agent_tabs(self):
        """The agent's own tabs, closed once they have sat untouched.

        Only its own: a tab he opened himself is never closed by
        this."""
        after = int((self.config or {}).get("agentTabIdle") or 0)
        if after <= 0:
            return []
        now = time.time()
        gone = []
        for _i, v in self._views():
            if not getattr(v, "_agent_owned", False):
                continue
            when = float(getattr(v, "_agent_touched", 0) or 0)
            if when and now - when < after:
                continue
            index = self.win.tabs.indexOf(v)
            if index >= 0:
                gone.append(self._view_url(v))
                self.win.close_tab(index, ask=False)
        return gone

    def op_audit(self, conn, req):
        """What has been driving this browser."""
        if req.get("clear"):
            if self.config is not None:
                self.config["bridgeAudit"] = []
            self._reply(conn, {"ok": True, "cleared": True})
            return
        rows = self.audit_rows()
        self._reply(conn, {"ok": True, "audit": rows[-int(
            req.get("limit") or 50):]})

    def op_permissions(self, conn, req):
        """What this bridge is allowed to do, and setting it.

        Asking is always allowed: a client that cannot find out it is
        read-only cannot tell him why an op was refused."""
        if "level" in req and self.config is not None:
            want = str(req.get("level") or "")
            if want in ("off", "read", "full"):
                self.config["bridgeLevel"] = want
        if "ops" in req and self.config is not None:
            self.config["bridgeOps"] = [str(one) for one
                                        in (req.get("ops") or [])]
        if "sites" in req and self.config is not None:
            self.config["bridgeSites"] = [str(one) for one
                                          in (req.get("sites") or [])]
        self._reply(conn, {"ok": True, "level": self.level(),
                           "ops": (self.config or {}).get("bridgeOps") or [],
                           "sites": (self.config or {}).get("bridgeSites")
                           or [],
                           "history": bool((self.config or {}).get(
                               "bridgeHistory", False))})

    # ---- the rest of the ops -----------------------------------------
    def op_search(self, conn, req):
        """A search in his own engine, and the results as a list.

        Run in a tab like any other search, then the result page is
        read: there is no API behind this and there should not be, so
        the honest version is "the browser searched and this is what
        came back"."""
        text = str(req.get("text") or "")
        if not text:
            raise ValueError("text required")
        url = self.win.search_for(text, new_tab=True)
        if not url:
            self._reply(conn, {"ok": False, "error": "no-engine"})
            return
        rows = [(i, v) for i, v in self._views()]
        v = rows[-1][1] if rows else None
        if v is None:
            self._reply(conn, {"ok": False, "error": "no-tab"})
            return
        v._agent_owned = True
        v._agent_touched = time.time()
        code = """(function (limit) {
          var out = [], seen = {};
          var rows = document.querySelectorAll("a[href]");
          for (var i = 0; i < rows.length && out.length < limit; i++) {
            var href = rows[i].href;
            if (!/^https?:/.test(href)) continue;
            if (/google\\.|bing\\.|duckduckgo\\.|ecosia\\./.test(href))
              continue;
            var text = (rows[i].textContent || "").trim();
            if (text.length < 8 || seen[href]) continue;
            seen[href] = true;
            out.push({title: text.slice(0, 120), url: href});
          }
          return JSON.stringify(out);
        })(%d)""" % int(req.get("limit") or 10)

        def when_loaded(ok=True):
            try:
                v.loadFinished.disconnect(when_loaded)
            except (TypeError, RuntimeError):
                pass
            QTimer.singleShot(600, lambda: self._run(
                v, code, lambda raw: self._reply(conn, {
                    "ok": True, "url": url,
                    "tab": self._tab_info(self.win.tabs.indexOf(v), v),
                    "results": _json_or(raw, [])})))

        v.loadFinished.connect(when_loaded)

    def op_ask(self, conn, req):
        """A question to an assistant that is open in a tab.

        The same shape as the chatgpt op: claude.ai by default, his
        own selectors if the page has moved on. Nothing is sent
        anywhere the browser is not already signed in."""
        which = str(req.get("which") or "claude")
        text = str(req.get("text") or "")
        if not text:
            raise ValueError("text required")
        rows = {"claude": {"url": "https://claude.ai/new",
                           "host": "claude.ai",
                           "box": "div[contenteditable=true]",
                           "answer": "div.font-claude-message"},
                "chatgpt": {"url": "https://chatgpt.com/",
                            "host": "chatgpt.com",
                            "box": "#prompt-textarea",
                            "answer": "div[data-message-author-role=assistant]"}}
        plan = rows.get(which)
        if plan is None:
            raise ValueError("unknown assistant: " + which)
        if hasattr(self, "op_chatgpt") and which == "chatgpt":
            return self.op_chatgpt(conn, req)
        v = None
        for _i, one in self._views():
            if plan["host"] in self._view_url(one):
                v = one
                break
        if v is None:
            self.win.new_tab(url=plan["url"], switch=False)
            rows2 = [(i, one) for i, one in self._views()]
            v = rows2[-1][1] if rows2 else None
            if v is None:
                self._reply(conn, {"ok": False, "error": "no-tab"})
                return
            v._agent_owned = True
        v._agent_touched = time.time()
        code = """(function (box, text) {
          var el = document.querySelector(box);
          if (!el) return "no-box";
          el.focus();
          if ("value" in el) { el.value = text; }
          else { el.textContent = text; }
          el.dispatchEvent(new Event("input", {bubbles: true}));
          return "typed";
        })(%s, %s)""" % (_js_string(plan["box"]), _js_string(text))
        self._run(v, code, lambda raw: self._reply(conn, {
            "ok": str(raw or "") == "typed", "state": str(raw or ""),
            "tab": self._tab_info(self.win.tabs.indexOf(v), v),
            "note": "the answer is read with the text op once it has "
                    "finished streaming"}))

    def op_viewport(self, conn, req):
        """A tab's size, or a phone's, for a capture."""
        v = self._need_view(conn, req)
        if v is None:
            return
        want = str(req.get("size") or "")
        if want:
            out = self.win.responsive_preview(size=want, view=v)
            self._reply(conn, {"ok": bool(out), "size": out or want})
            return
        wide = int(req.get("width") or 0)
        tall = int(req.get("height") or 0)
        if wide and tall:
            v.setFixedSize(max(120, wide), max(120, tall))
            self._reply(conn, {"ok": True, "width": v.width(),
                               "height": v.height()})
            return
        self.win.responsive_preview(size="off", view=v)
        self._reply(conn, {"ok": True, "width": v.width(),
                           "height": v.height()})

    def op_groups(self, conn, req):
        """The tab groups, and moving a tab between them."""
        move = req.get("move")
        if move not in (None, ""):
            v = self._find(move)
            if v is None:
                self._reply(conn, {"ok": False, "error": "no-such-tab"})
                return
            group = req.get("group")
            index = self.win.tabs.indexOf(v)
            if index < 0:
                self._reply(conn, {"ok": False, "error": "no-such-tab"})
                return
            if group in (None, "", False):
                was = self.win._group_of(v)
                if was:
                    self.win.ungroup(was)
            else:
                name = str(group)
                # a group the browser has never heard of has no header
                # to move the tab next to, so it is registered first
                if self.win._header_index(name) is None:
                    import browser as _b
                    colours = getattr(_b, "GROUP_COLORS", None) \
                        or [("Blue", "#89b4fa")]
                    self.win._register_group(name, colours[0][1])
                    index = self.win.tabs.indexOf(v)
                self.win._move_tab_to_group(index, name)
            self._reply(conn, {"ok": True,
                               "group": self.win._group_of(v) or ""})
            return
        rows = {}
        for i, v in self._views():
            name = self.win._group_of(v) or ""
            rows.setdefault(name, []).append(getattr(v, "_agent_id", None))
        self._reply(conn, {"ok": True, "groups": rows})

    def op_history(self, conn, req):
        """His history, searched -- off unless he allowed it.

        Guarded separately from everything else, because the rest of
        the bridge reads pages and this reads him."""
        text = str(req.get("text") or "").lower()
        rows = []
        for row in reversed(self.win.history or []):
            url = str(row.get("url") or "")
            title = str(row.get("title") or "")
            if text and text not in url.lower() \
                    and text not in title.lower():
                continue
            rows.append({"url": url, "title": title,
                         "t": row.get("t")})
            if len(rows) >= int(req.get("limit") or 50):
                break
        self._reply(conn, {"ok": True, "history": rows})

    def op_upload(self, conn, req):
        """Files for the page's next file chooser.

        A page cannot be handed files from outside; what it can be
        handed is the answer to the chooser it opens. The paths are
        remembered and the chooser is answered with them the moment the
        page asks (see WebPage.chooseFiles)."""
        v = self._need_view(conn, req)
        if v is None:
            return
        rows = req.get("paths") or ([req.get("path")]
                                    if req.get("path") else [])
        rows = [str(one) for one in rows if str(one or "")]
        missing = [one for one in rows if not os.path.isfile(one)]
        if missing:
            self._reply(conn, {"ok": False, "error": "no-such-file",
                               "missing": missing})
            return
        page = v.page()
        page._agent_files = rows
        selector = str(req.get("selector") or "")
        if selector:
            code = ("(function(sel){var el=document.querySelector(sel);"
                    "if(!el) return 'missing';"
                    "el.click(); return 'asked';})(%s)"
                    % _js_string(selector))
            self._run(v, code, lambda raw: self._reply(conn, {
                "ok": str(raw or "") == "asked", "files": rows,
                "state": str(raw or "")}))
            return
        self._reply(conn, {"ok": True, "files": rows,
                           "note": "the next file chooser in this tab is "
                                   "answered with these"})

    def op_pointer(self, conn, req):
        """A real mouse: hover, press, drag, right-click.

        Posted to the view as Qt mouse events, which the engine
        delivers to the page as trusted input -- a JavaScript click()
        is not trusted and a page that checks will know."""
        v = self._need_view(conn, req)
        if v is None:
            return
        kind = str(req.get("kind") or "click")
        x = int(req.get("x") or 0)
        y = int(req.get("y") or 0)
        target = v.focusProxy() or v
        from PyQt6.QtCore import QPoint, QPointF
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent as _QEvent
        where = QPointF(QPoint(x, y))
        button = (Qt.MouseButton.RightButton if kind == "right"
                  else Qt.MouseButton.LeftButton)

        def post(event_type, buttons):
            QApplication.postEvent(target, QMouseEvent(
                event_type, where, where,
                button if event_type != _QEvent.Type.MouseMove
                else Qt.MouseButton.NoButton,
                buttons, Qt.KeyboardModifier.NoModifier))

        if kind in ("move", "hover"):
            post(_QEvent.Type.MouseMove, Qt.MouseButton.NoButton)
        elif kind == "drag":
            to_x = int(req.get("tox") or x)
            to_y = int(req.get("toy") or y)
            post(_QEvent.Type.MouseButtonPress, button)
            for step in range(1, 6):
                mid = QPointF(QPoint(x + (to_x - x) * step // 5,
                                     y + (to_y - y) * step // 5))
                QApplication.postEvent(target, QMouseEvent(
                    _QEvent.Type.MouseMove, mid, mid,
                    Qt.MouseButton.NoButton, button,
                    Qt.KeyboardModifier.NoModifier))
            end = QPointF(QPoint(to_x, to_y))
            QApplication.postEvent(target, QMouseEvent(
                _QEvent.Type.MouseButtonRelease, end, end, button,
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        else:
            post(_QEvent.Type.MouseButtonPress, button)
            post(_QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)
        self._reply(conn, {"ok": True, "kind": kind, "x": x, "y": y})

    def op_restart(self, conn, req):
        self._reply(conn, {"ok": True})
        QTimer.singleShot(200, self.win.restart)


class RestMirror:
    """The same ops over http on 127.0.0.1, with a token.

    Off unless he switches it on, bound to the loopback address only,
    and every request must carry the token: the socket is the real
    door and this is a convenience for things that speak http and
    nothing else (a shell with curl, a Home Assistant automation).

    One thread, the standard library's own server, and every op runs
    back on the Qt thread -- the browser is not thread-safe and an op
    that touched a page from here would be a crash waiting for a busy
    moment."""

    def __init__(self, bridge, port=8777, token=""):
        self.bridge = bridge
        self.port = int(port)
        self.token = str(token or "")
        self.server = None
        self.thread = None

    def start(self):
        import http.server
        import threading
        mirror = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self, code, payload):
                raw = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                if mirror.token and self.headers.get("X-Token") \
                        != mirror.token:
                    self._answer(403, {"ok": False, "error": "bad-token"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    req = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    self._answer(400, {"ok": False, "error": "bad-json"})
                    return
                answer = mirror.run(req)
                self._answer(200 if answer.get("ok") else 400, answer)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        return True

    def run(self, req):
        """One op, asked through the bridge's own socket.

        The honest way round: this thread is not the Qt thread and must
        not touch a page, so it connects to the same local socket every
        other client uses and the op runs where everything else does.
        No cross-thread calls, no collector standing in for a socket."""
        import socket as _socket
        try:
            sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect(socket_path())
            sock.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
            sock.close()
        except OSError as e:
            return {"ok": False, "error": "socket: %s" % e}
        if not buf:
            return {"ok": False, "error": "no-answer"}
        try:
            return json.loads(buf.split(b"\n")[0].decode())
        except (ValueError, UnicodeDecodeError):
            return {"ok": False, "error": "bad-reply"}


def install(win, config=None):
    """Start the bridge for this window. Returns it, or None when it is
    switched off or the socket cannot be taken (never fatal for the
    browser itself)."""
    if os.environ.get("BROWSER_NO_AGENT"):
        return None
    cfg = config if config is not None else getattr(win, "config", {}) or {}
    if cfg.get("agentBridge", True) is False:
        return None
    try:
        bridge = AgentBridge(win)
        if not bridge.listen():
            return None
        # the http mirror, if he asked for it: loopback only, token
        # required, and it runs every op back on the Qt thread
        if cfg.get("bridgeRest", False):
            try:
                mirror = RestMirror(bridge,
                                    port=int(cfg.get("bridgeRestPort")
                                             or 8777),
                                    token=str(cfg.get("bridgeRestToken")
                                              or ""))
                mirror.start()
                bridge.mirror = mirror
            except OSError as e:
                print("agent rest mirror not started: %s" % e,
                      file=sys.stderr)
        # the agent's own tabs, tidied up once they have sat idle
        timer = QTimer(win)
        timer.timeout.connect(bridge.close_idle_agent_tabs)
        timer.start(60000)
        bridge._idle_timer = timer
        bridge.watch_window()
    except Exception as e:
        print("agent bridge not started: %s" % e, file=sys.stderr)
        return None
    win._agent_bridge = bridge
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(bridge.close)
    return bridge
