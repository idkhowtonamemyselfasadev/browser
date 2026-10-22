#!/usr/bin/env python3
"""The side panel, tabs that sleep, game mode, the Minecraft server
ping and the Discord keys.

The Minecraft part is tested against a server that really speaks the
server-list-ping protocol — written here in thirty lines, because the
protocol is thirty lines — rather than against a stub that agrees with
whatever the code does."""
import json
import os
import socket
import struct
import sys
import threading
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BROWSER_NO_LIB_CHECK"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import harness as H  # noqa: E402
B = H.boot()

fails = []


def check(what, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + (("  <" + str(detail) + ">") if detail != "" else ""))
    if not ok:
        fails.append(what)


# ---- a Minecraft server, as far as the server list is concerned ------
def varint(n):
    out = bytearray()
    while True:
        part = n & 0x7F
        n >>= 7
        out.append(part | (0x80 if n else 0))
        if not n:
            return bytes(out)


def read_varint(sock):
    value = shift = 0
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError
        value |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return value
        shift += 7


STATUS = json.dumps({
    "version": {"name": "1.21.4", "protocol": 765},
    "players": {"online": 7, "max": 40},
    "description": {"text": "KitPvP ", "extra": [{"text": "practice"}]},
})


class FakeServer(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.stop = False

    def run(self):
        while not self.stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                length = read_varint(conn)
                conn.recv(length)                 # the handshake
                length = read_varint(conn)
                conn.recv(length)                 # the status request
                body = b"\x00" + varint(len(STATUS)) + STATUS.encode()
                conn.sendall(varint(len(body)) + body)
            except (OSError, ConnectionError):
                pass
            finally:
                conn.close()


mc = FakeServer()
mc.start()

print("\n(1) the server list ping")
got = B.mc_ping("127.0.0.1", mc.port, timeout=3)
check("the server answers", got.get("up") is True, got)
check("with the players on it", got.get("players") == 7
      and got.get("max") == 40, got)
check("its version", got.get("version") == "1.21.4", got)
check("and its message of the day",
      got.get("motd") == "KitPvP practice", got)
check("the latency is measured", isinstance(got.get("ms"), int), got)
dead = B.mc_ping("127.0.0.1", 1, timeout=1)
check("a server that is not there is simply down",
      dead.get("up") is False and "error" in dead, dead)
slow = B.mc_ping("192.0.2.1", 25565, timeout=0.3)
check("and one that does not answer does not hang",
      slow.get("up") is False, slow)

app = H.app()
PAGES = {"/a": "<title>A</title><p>a</p>", "/p": "<title>Panel</title><p>p</p>",
         "/discord": ("<title>Discord</title>"
                      "<button aria-label='Mute' id=m "
                      "onclick=\"document.title='muted'\">m</button>"
                      "<button aria-label='Deafen' id=d "
                      "onclick=\"document.title='deafened'\">d</button>")}
srv = H.Server(PAGES)
B.CONFIG_FILE.write_text(json.dumps({"translateLang": "en"}))
win = B.Browser()
win.resize(1300, 800)
win.show()
H.spin(400)
view = win.new_tab(url=None)
H.load(view, srv.url("/a"))

print("\n(2) the servers in a menu")
win.config["mcServers"] = ["Practice=127.0.0.1:%d" % mc.port,
                           "Dead=127.0.0.1:1"]
check("the list is read",
      [n for n, _h, _p in win.mc_servers()] == ["Practice", "Dead"],
      win.mc_servers())
status = win.mc_status()
check("one is up and one is down",
      status[0][1]["up"] is True and status[1][1]["up"] is False, status)
menu = win.mc_menu()
labels = [a.text() for a in menu.actions()]
check("the menu says who is on", any("7/40" in t for t in labels), labels)
check("and who is not", any("not answering" in t for t in labels), labels)
check("asking again is offered", any("again" in t for t in labels), labels)
win.config["mcServers"] = []
check("with no servers it says so",
      "No servers" in win.mc_menu().actions()[0].text(),
      win.mc_menu().actions()[0].text())
win.config["mcServers"] = ["Practice=127.0.0.1:%d" % mc.port]
check("watching can be switched on", win.mc_watch(True)
      and win._mc_timer is not None)
win._mc_check()
check("and it remembers what it saw", win._mc_was.get("Practice") is True,
      getattr(win, "_mc_was", None))
check("and off again", not win.mc_watch(False) and win._mc_timer is None)

print("\n(3) the side panel")
check("it is not there until asked for", not win._panel.isVisible())
win.open_panel(srv.url("/p"))
H.spin(1200)
check("it opens with the site in it",
      win._panel.isVisible()
      and win._panel_view.url().toString().endswith("/p"),
      win._panel_view.url().toString())
check("the page keeps most of the window",
      win._split.sizes()[0] > win._split.sizes()[1], win._split.sizes())
check("it is a real view, not a frame",
      H.js(win._panel_view, "document.title", B.MAIN_WORLD_ID) == "Panel",
      H.js(win._panel_view, "document.title", B.MAIN_WORLD_ID))
check("the site is remembered",
      (win.config.get("panelUrl") or "").endswith("/p"))
tab = win.panel_to_tab()
H.spin(700)
check("it can be sent to a tab",
      tab is not None and tab.url().toString().endswith("/p"),
      tab.url().toString() if tab else None)
check("and the panel closes behind it", not win._panel.isVisible())
win.toggle_panel(True)
H.spin(600)
check("toggling brings it back", win._panel.isVisible())
win.toggle_panel(False)
check("and takes it away", not win._panel.isVisible())
check("the width he dragged is kept",
      int(win.config.get("panelWidth", 0)) > 100, win.config.get("panelWidth"))
started = win.open_twitch_chat("sodapoppin")
H.wait_for(lambda: "sodapoppin" in win._panel_view.url().toString(), 5000)
check("Twitch chat knows the channel from the page",
      started and "popout/sodapoppin/chat" in win._panel_view.url().toString(),
      win._panel_view.url().toString())
win.toggle_panel(False)

print("\n(4) tabs that sleep")
others = [win.new_tab(url=srv.url("/a"), switch=False) for _ in range(2)]
H.spin(900)
win.tabs.setCurrentIndex(win.tabs.indexOf(view))
H.spin(200)
n = win.sleep_other_tabs()
H.spin(400)
check("the others went to sleep", n >= 2, n)
check("the one in front did not",
      view not in win.sleeping_tabs(), len(win.sleeping_tabs()))
check("and the sleeping ones are known",
      len(win.sleeping_tabs()) >= 2, len(win.sleeping_tabs()))
win.sleep_tab(others[0], False)
H.spin(300)
check("one can be woken", others[0] not in win.sleeping_tabs())

print("\n(5) game mode")
check("it goes on", win.game_mode(True) is True)
check("everything is muted",
      all(v.page().isAudioMuted() for _, v in win._real_tabs()))
check("notifications are refused without asking",
      win.notifications_blocked())
check("and it goes off again", win.game_mode(False) is False)
check("with the sound back",
      not any(v.page().isAudioMuted() for _, v in win._real_tabs()))
check("and notifications asked about again",
      not win.notifications_blocked())

print("\n(6) the Discord keys")
check("with no Discord tab it says so", win.discord_key("mute") is False)
dc = win.new_tab(url=srv.url("/discord"), switch=False)
H.spin(800)
check("...but it cannot find a Discord tab by this host",
      win.discord_key("mute") is False)
# the host is 127.0.0.1 here, so the real test is the script itself
H.js(dc, B.Browser.DISCORD_JS % json.dumps("mute"), B.APP_WORLD_ID)
H.wait_for(lambda: H.js(dc, "document.title", B.MAIN_WORLD_ID) == "muted",
           3000)
check("the mute button is the one pressed",
      H.js(dc, "document.title", B.MAIN_WORLD_ID) == "muted",
      H.js(dc, "document.title", B.MAIN_WORLD_ID))
H.js(dc, B.Browser.DISCORD_JS % json.dumps("deafen"), B.APP_WORLD_ID)
H.wait_for(lambda: H.js(dc, "document.title", B.MAIN_WORLD_ID) == "deafened",
           3000)
check("and deafen is another button",
      H.js(dc, "document.title", B.MAIN_WORLD_ID) == "deafened")

mc.stop = True
mc.sock.close()
print("")
if fails:
    print("FAILED (%d): %s" % (len(fails), "; ".join(fails[:8])))
    sys.exit(1)
print("all good")
