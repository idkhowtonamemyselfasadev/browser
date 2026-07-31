#!/usr/bin/env python3
"""Can this Qt do passkeys? Run it and see.

Nothing in the browser is involved: this is a bare QWebEngineView with
QWebEnginePage::webAuthUxRequested connected, pointed at a page that
asks for a passkey. It exists because that signal is how a browser is
supposed to be told "collect a PIN", "pick an account", "touch your
key" — and on Qt 6.11.1 / PyQt6 6.11.0 it is never emitted at all. The
class and every one of its methods are there in the bindings; nothing
drives them. A request that needs any of that UI parks for ever, and
the site's own timeout never fires either, so the page simply spins.

That is why the browser has no passkey dialog: there is nothing to
connect one to. A dialog that can never be shown would be worse than
saying so.

Run it again after a Qt update. If the line below ever reads anything
other than 0, the dialog becomes worth building:

    webAuthUxRequested emissions: 0

Nothing here touches your data: its own scratch profile, its own
throwaway HTTP server on localhost, and it exits by itself.
"""
import os
import sys
import shutil
import tempfile
import threading
import http.server
import socketserver

DATA = os.path.join(tempfile.gettempdir(), "webauthn-probe")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA, exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = DATA
os.environ["XDG_CONFIG_HOME"] = DATA
os.environ["XDG_CACHE_HOME"] = DATA

from PyQt6.QtWidgets import QApplication                        # noqa: E402
from PyQt6.QtCore import QUrl, QTimer, QEventLoop               # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView             # noqa: E402

# localhost, not 127.0.0.1: an IP address is not a registrable domain,
# and WebAuthn turns it away as "an invalid domain" before anything
# interesting can happen.
PAGE = """<!doctype html><meta charset=utf-8><body><script>
window.__res = "pending";
navigator.credentials.create({publicKey: {
  challenge: new Uint8Array(32),
  rp: {name: "Probe", id: location.hostname},
  user: {id: new Uint8Array(16), name: "probe", displayName: "Probe"},
  pubKeyCredParams: [{type: "public-key", alg: -7}],
  timeout: 5000}}).then(
  function () { window.__res = "OK"; },
  function (e) { window.__res = "ERR " + e.name + ": " + e.message; });
</script></body>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        raw = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def main():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    app = QApplication(sys.argv)
    app.setApplicationName("webauthn-probe")
    view = QWebEngineView()
    view.resize(900, 700)
    view.show()

    seen = []

    def ux(request):
        seen.append(request)
        print("  *** webAuthUxRequested: state=%s rp=%s"
              % (request.state(), request.relyingPartyId()), flush=True)

    view.page().webAuthUxRequested.connect(ux)

    def spin(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def result():
        box = {}
        loop = QEventLoop()
        view.page().runJavaScript(
            "window.__res", lambda v: (box.__setitem__("v", v), loop.quit()))
        QTimer.singleShot(6000, loop.quit)
        loop.exec()
        return box.get("v")

    done = {"ok": False}
    view.loadFinished.connect(lambda ok: done.__setitem__("ok", True))
    view.load(QUrl("http://localhost:%d/" % port))
    for _ in range(200):
        if done["ok"]:
            break
        spin(50)
    spin(400)

    from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
    print("Qt %s, PyQt %s, platform %s"
          % (QT_VERSION_STR, PYQT_VERSION_STR,
             os.environ["QT_QPA_PLATFORM"]), flush=True)
    print("the page asked for a passkey; its own timeout is 5s", flush=True)

    for i in range(30):
        spin(1000)
        answer = result()
        if answer != "pending":
            print("  the page heard back after %ds: %s" % (i + 1, answer),
                  flush=True)
            break
    else:
        print("  still pending after 30s — the 5s timeout never fired",
              flush=True)
    print("  webAuthUxRequested emissions: %d" % len(seen), flush=True)
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
