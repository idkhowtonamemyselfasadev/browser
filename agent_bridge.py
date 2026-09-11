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
  restart                    -> the browser's own relaunch (keeps tabs)

Off switch: config "agentBridge": false, or BROWSER_NO_AGENT=1.
The socket is a user-owned Unix socket in the temp directory; only
processes running as the same user can reach it.
"""
import json
import os
import sys

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


def _js_string(s):
    return json.dumps("" if s is None else str(s))


# --- the page-side helpers every DOM op is built from ---------------
_FIND = """
(function(sel, index){
  var all = document.querySelectorAll(sel);
  return all.length > index ? all[index] : null;
})"""

_TEXT_JS = """
(function(sel){
  var el = sel ? document.querySelector(sel) : document.body;
  if (!el) return null;
  return el.innerText !== undefined ? el.innerText : el.textContent;
})(%s)"""

_HTML_JS = """
(function(sel, cap){
  var el = sel ? document.querySelector(sel) : document.documentElement;
  if (!el) return null;
  var h = el.outerHTML;
  return h.length > cap ? h.slice(0, cap) : h;
})(%s, %d)"""

_EXISTS_JS = "!!document.querySelector(%s)"

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
  var el = document.querySelector(sel);
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
})(%s, %s, %s)"""

_SCROLL_JS = """
(function(y){
  if (y === "bottom") window.scrollTo(0, document.documentElement.scrollHeight);
  else window.scrollTo(0, y);
  return window.scrollY;
})(%s)"""


class AgentBridge:
    def __init__(self, win):
        self.win = win
        self.server = QLocalServer()
        self._next_id = 1

    # ---- lifecycle ---------------------------------------------------
    def listen(self):
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

    # ---- ops ---------------------------------------------------------
    def op_ping(self, conn, req):
        self._reply(conn, {"ok": True, "pid": os.getpid()})

    def op_tabs(self, conn, req):
        self._reply(conn, {"ok": True, "tabs": [self._tab_info(i, v)
                                                 for i, v in self._views()]})

    def op_open(self, conn, req):
        url = str(req.get("url") or "")
        if not url:
            raise ValueError("url required")
        switch = bool(req.get("switch", False))
        before = {id(v) for _i, v in self._views()}
        self.win.new_tab(url=url, switch=switch)
        new = [(i, v) for i, v in self._views() if id(v) not in before]
        if not new:
            raise RuntimeError("tab did not open")
        i, v = new[-1]
        v._agent_loading = True
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
            self._run(v, code, got)
        poll()

    def op_click(self, conn, req):
        v = self._need_view(conn, req)
        if v is None:
            return
        sel = str(req.get("selector") or "")
        if not sel:
            raise ValueError("selector required")
        code = _CLICK_JS % (_js_string(sel), int(req.get("index", 0)))
        self._run(v, code, lambda r: self._reply(
            conn, {"ok": r == "clicked", "result": r}))

    def op_type(self, conn, req):
        v = self._need_view(conn, req)
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

    def op_restart(self, conn, req):
        self._reply(conn, {"ok": True})
        QTimer.singleShot(200, self.win.restart)


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
    except Exception as e:
        print("agent bridge not started: %s" % e, file=sys.stderr)
        return None
    win._agent_bridge = bridge
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(bridge.close)
    return bridge
