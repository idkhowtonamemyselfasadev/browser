#!/usr/bin/env python3
"""Pictures of the Favourites panel: the button in the toolbar, the
panel open with folders inside folders, a search half typed, the row
menu, and a folder being renamed in its own row.

Offscreen, against scratch data files - your own bookmarks are never
opened. The panel is a window of its own, so it is grabbed on its own
and painted onto the window shot where it really sits.

    QT_QPA_PLATFORM=offscreen python _favshots.py [en|de]
"""
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtWidgets import QTreeWidget  # noqa: E402
from PyQt6.QtCore import (QEventLoop, QPoint, QPointF, QRect,  # noqa: E402
                          QTimer, QUrl, Qt)
from PyQt6.QtGui import (QColor, QDragEnterEvent, QDragMoveEvent,  # noqa: E402
                         QPainter, QPen, QPixmap)

OUT = HERE / "screenshots"
OUT.mkdir(exist_ok=True)

PAGE = (b"<!doctype html><meta charset=utf-8><title>Wiener Zeitung</title>"
        b"<body style='background:#111;color:#ddd;font:16px sans-serif;"
        b"padding:60px'><h1>Wiener Zeitung</h1>"
        b"<p>Ein ganz gew\xc3\xb6hnlicher Artikel.</p>")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


socketserver.TCPServer.allow_reuse_address = True
HTTPD = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=HTTPD.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/artikel" % HTTPD.server_address[1]

LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
B.CONFIG_FILE.write_text(json.dumps(
    {"translateLang": LANG, "restoreTabs": False,
     "startPage": {"setupDone": True}}))
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1400, 820)
win.show()
app.processEvents()


def spin(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ---- something worth showing: a small, ordinary collection ------------
def folder(name, parent=0):
    return win.add_bookmark_folder(name, parent)


def link(title, url, parent, ident):
    win.bookmarks.append({"id": ident, "type": "link", "title": title,
                          "url": url, "icon": "", "parent": parent, "t": 0})


win.bookmarks = []
news = folder("Zeitungen")
reisen = folder("Reisen")
hotels = folder("Hotels", reisen)
wien = folder("Wien", hotels)
enkel = folder("Für die Enkel")
link("ORF", "https://orf.at/", news, 101)
link("Der Standard", "https://derstandard.at/", news, 102)
link("Hotel Sacher", "https://sacher.com/", wien, 103)
link("Pension Nossek", "https://pension-nossek.at/", wien, 104)
link("ÖBB Fahrplan", "https://oebb.at/", reisen, 105)
link("Wetter", "https://wetter.orf.at/", 0, 106)
link("Fotos von Anna", "https://photos.example/", enkel, 107)
win.save_bookmarks()
spin(300)

# a real page in the tab, so "Bookmark this page" has something to act on
loop = QEventLoop()
timer = QTimer()
timer.setSingleShot(True)
timer.timeout.connect(loop.quit)
timer.start(20000)
win.current().loadFinished.connect(lambda ok: ok and loop.quit())
win.current().load(QUrl(URL))
loop.exec()
spin(600)


def shot(name, pix):
    path = OUT / (name if LANG == "en" else name.replace(".png", "-de.png"))
    pix.save(str(path))
    print(path)


btn = win._tb_buttons["favorites"]
panel = win.favorites_panel()


def open_panel():
    """The panel is a widget over the window now, so a grab of the
    window has it in it - nothing to paste on afterwards."""
    if panel.isVisible():
        panel.close()
        spin(80)
    win.toggle_favorites()
    app.processEvents()
    spin(250)


def compose(extra=None, extra_at=None):
    frame = win.grab()
    if extra is not None:
        painter = QPainter(frame)
        painter.drawPixmap(extra_at, extra.grab())
        painter.setPen(QPen(QColor("#6c7086")))
        painter.drawRect(QRect(extra_at, extra.size()).adjusted(0, 0, -1, -1))
        painter.end()
    return frame


# ---- 1. the button, shut ---------------------------------------------
frame = win.grab()
mark = QPixmap(frame)
painter = QPainter(mark)
painter.setPen(QPen(QColor("#f9e2af"), 2))
painter.drawRect(QRect(btn.mapTo(win, QPoint(0, 0)),
                       btn.size()).adjusted(-3, -3, 3, 3))
painter.end()
shot("favorites-button.png", mark)
strip = mark.copy(0, 0, mark.width(), 118)
shot("favorites-button-close.png",
     strip.scaled(strip.width() * 2, strip.height() * 2))


# ---- 2. the panel open, folders inside folders ------------------------
open_panel()
for fid in (news, reisen, hotels, wien):
    item = panel._find(fid)
    if item is not None:
        item.setExpanded(True)
app.processEvents()
spin(150)
shot("favorites-panel.png", compose())

panel.tree.setCurrentItem(panel._find(103))
app.processEvents()
spin(120)
shot("favorites-panel-selected.png", compose())


# ---- 3. mid-search ----------------------------------------------------
panel.search.setText("sach")
app.processEvents()
spin(250)
shot("favorites-search.png", compose())
panel.search.clear()
app.processEvents()
spin(200)


# ---- 4. the row's own menu -------------------------------------------
item = panel._find(hotels)
panel.tree.setCurrentItem(item)
app.processEvents()
rect = panel.tree.visualItemRect(item)
where = panel.tree.viewport().mapToGlobal(QPoint(rect.right() - 6,
                                                 rect.bottom()))
rowmenu = panel.row_menu(item)
rowmenu.popup(where)
app.processEvents()
spin(250)
shot("favorites-row-menu.png",
     compose(rowmenu, win.mapFromGlobal(where)))
rowmenu.close()
spin(150)


# ---- 5. the rename, in the row itself ---------------------------------
panel.rename(panel._find(hotels))
app.processEvents()
spin(300)
shot("favorites-rename.png", compose())
panel.tree.closePersistentEditor(panel._find(hotels), 0)
app.processEvents()
spin(150)


# ---- 6. mid-drag, both kinds of drop indicator -----------------------
def row_at(name):
    def walk(node):
        for i in range(node.childCount()):
            child = node.child(i)
            if child.text(0) == name:
                return child
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(panel.tree.invisibleRootItem())


def drag_shot(name, moving, target, where):
    """A row picked up and held over another, grabbed while it is in the
    air. The events are the ones Qt sends; only QDrag.exec()'s own loop
    is stood in for, because offscreen there is no pointer for it to
    follow - and standing in for it is what leaves the frame still on
    the screen to be photographed."""
    tree = panel.tree
    tree.setCurrentItem(row_at(moving))
    mime = tree.mimeData([row_at(moving)])
    rect = tree.visualItemRect(row_at(target))
    if where == "on":
        pos = rect.center()
    elif where == "above":
        pos = QPoint(rect.center().x(), rect.top() + 1)
    else:
        pos = QPoint(rect.center().x(), rect.bottom() - 1)

    def loop(_self, _actions):
        for kind in (QDragEnterEvent, QDragMoveEvent):
            event = kind(pos, Qt.DropAction.MoveAction, mime,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
            event.setDropAction(Qt.DropAction.MoveAction)
            app.sendEvent(tree.viewport(), event)
        app.processEvents()
        spin(150)
        shot(name, compose())

    was = QTreeWidget.startDrag
    QTreeWidget.startDrag = loop
    try:
        tree.startDrag(Qt.DropAction.MoveAction)
    finally:
        QTreeWidget.startDrag = was
    app.processEvents()


open_panel()
for fid in (news, reisen, hotels, wien):
    node = panel._find(fid)
    if node is not None:
        node.setExpanded(True)
app.processEvents()
spin(150)
drag_shot("favorites-drag-into.png", "Wetter", "Zeitungen", "on")
drag_shot("favorites-drag-between.png", "Wetter", "Pension Nossek", "above")
panel.close()
spin(120)


# ---- 7. the manager, with the nesting drawn in -----------------------
win.open_bookmarks()
spin(2500)
shot("favorites-manager.png", win.grab())
win.close_pane()
spin(200)
HTTPD.shutdown()
print("done")
