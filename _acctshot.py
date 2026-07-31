#!/usr/bin/env python3
"""Photograph the account chooser and the handle it hangs off, against a
scratch vault with two invented logins. Never goes near your own data.

    python3 _acctshot.py [outdir]
"""
import http.server
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boot import B  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
OUT.mkdir(parents=True, exist_ok=True)

PAGE = """<!doctype html><meta charset=utf-8><title>Sign in</title>
<body style="background:#1b1b1f;color:#e8e8ea;font:16px/1.5 sans-serif;
             margin:0;display:flex;align-items:center;
             justify-content:center;height:100vh">
<form method=GET action="/done"
      style="width:360px;background:#232327;padding:34px 32px;
             box-shadow:0 1px 0 rgba(255,255,255,.06) inset">
  <div style="font-size:22px;margin-bottom:22px">Sign in</div>
  <input id=user name=username type=email autocomplete=username
         placeholder="Email, phone, or Skype"
         style="display:block;width:100%;box-sizing:border-box;height:38px;
                background:#141417;border:1px solid #3a3a40;color:#e8e8ea;
                padding:0 10px;margin-bottom:12px">
  <input id=pw name=password type=password placeholder="Password"
         style="display:block;width:100%;box-sizing:border-box;height:38px;
                background:#141417;border:1px solid #3a3a40;color:#e8e8ea;
                padding:0 10px">
  <button id=signin type=submit
          style="margin-top:22px;height:36px;padding:0 26px;background:#3f3f46;
                 color:#e8e8ea;border:none">Sign in</button>
</form>
</body>"""


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


socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
PORT = httpd.server_address[1]

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1180, 760)
win.show()

win.vault.set_entry("127.0.0.1", "http", "a.person@outlook.com", "aaaaaaaa")
win.vault.set_entry("127.0.0.1", "http", "a.person@work.example", "bbbbbbbb")
win.vault.get("127.0.0.1", "a.person@outlook.com")["used"] = 2000
win.vault.get("127.0.0.1", "a.person@work.example")["used"] = 1000
win.vault._save()


def spin(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


view = win.current()
view.setFocus()          # an empty new tab focuses the address bar, and
spin(200)                # a focused bar is never overwritten on a load
view.load(QUrl("http://127.0.0.1:%d/signin" % PORT))
spin(4000)

assert win._acct_chooser is not None, "the chooser did not come up"
win.grab().save(str(OUT / "account-chooser.png"))
print(OUT / "account-chooser.png")

win._acct_chooser.cancel()
spin(400)
assert not win.acctbtn.isHidden(), "the address-bar handle is not there"
bar = win.urlbar
top = bar.mapTo(win, bar.rect().topLeft())
win.grab(win.rect().adjusted(top.x() - 190, top.y() - 12,
                             -(win.width() - top.x() - bar.width() - 20),
                             -(win.height() - top.y() - bar.height() - 12))
         ).scaled(  # legible at a glance rather than a 30px sliver
    (bar.width() + 210) * 2, (bar.height() + 24) * 2
).save(str(OUT / "account-chooser-handle.png"))
print(OUT / "account-chooser-handle.png")

httpd.shutdown()
