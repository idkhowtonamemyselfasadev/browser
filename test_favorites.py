#!/usr/bin/env python3
"""The Favourites panel, and folders inside folders.

Covers, in the browser rather than in a docstring:

  * the button is in the registry, on by default, on the bar, and goes
    away and comes back through the registry like any other
  * what opens is a panel and not a chain of menus: a title, a search
    box, one list - and a folder opens *in place*, the panel staying
    open and the list growing downwards
  * a folder inside a folder inside a folder, made and named from the
    panel, and all three of them opened from it
  * a folder is renamed in its own row, no dialog anywhere
  * the search box filters as he types, opens the folders that hold a
    hit, and puts everything back when it is cleared
  * the page in front of you goes into the folder you pick, and a page
    already bookmarked moves rather than doubling
  * every row's own ... menu, reachable with a plain left click on it
    and not only by right-clicking
  * a folder deleted takes everything under it, however deep
  * a folder cannot be moved inside itself
  * the bookmarks bar keeps its menus - this is a surface beside it
  * a bookmarks.json from before folders nested still loads and works
  * a bookmarks.json hand-edited into a circle, or pointing at a parent
    that is not there, loads without hanging and loses nothing
  * the manager page draws the nesting and can make a folder inside one

Offscreen, against scratch data files. Your own bookmarks are never
opened.
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
from PyQt6.QtWidgets import (QApplication, QAbstractItemDelegate,  # noqa: E402
                             QAbstractItemView, QInputDialog, QLineEdit,
                             QMenu, QTreeWidget)
from PyQt6.QtCore import (QEventLoop, QPoint, QPointF, QTimer,  # noqa: E402
                          QUrl, Qt)
from PyQt6.QtGui import (QDragEnterEvent, QDragMoveEvent,  # noqa: E402
                         QDropEvent, QMouseEvent)
from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ------------------------------------------------------------ a real page
PAGE = b"<!doctype html><title>Sachertorte</title><h1>Sachertorte</h1>"


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
PORT = HTTPD.server_address[1]
threading.Thread(target=HTTPD.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/cake" % PORT


# ------------------------------------------------------------------ boot
B.CONFIG_FILE.write_text(json.dumps(
    {"translateLang": "en", "restoreTabs": False, "vaultPassword": True,
     "startPage": {"setupDone": True}}))
app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1300, 900)
# offscreen or not, a window nobody showed reports every widget in it
# invisible - and then every check below passes for the wrong reason
win.show()
app.processEvents()
panel = win.favorites_panel()


def spin(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def load(view, url, timeout=20000):
    loop = QEventLoop()
    done = {"ok": None}

    def finished(ok):
        done["ok"] = ok
        if ok:
            loop.quit()

    view.loadFinished.connect(finished)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout)
    view.load(QUrl(url))
    loop.exec()
    view.loadFinished.disconnect(finished)
    return bool(done["ok"])


def set_bookmarks(entries):
    B.BOOKMARKS_FILE.write_text(json.dumps(entries))
    win.bookmarks = B.load_bookmarks()
    win.save_bookmarks()
    if panel.isVisible():
        panel.refill()


def open_panel():
    if panel.isVisible():
        panel.close()
        app.processEvents()
    win.toggle_favorites()
    app.processEvents()


def rows(parent=None, out=None, depth=0):
    """Every row the panel is showing, in order, as (depth, text, open)."""
    out = [] if out is None else out
    parent = panel.tree.invisibleRootItem() if parent is None else parent
    for i in range(parent.childCount()):
        child = parent.child(i)
        if child.isHidden():
            continue
        out.append((depth, child.text(0), child.isExpanded()))
        if child.isExpanded():   # a shut folder is not showing anything
            rows(child, out, depth + 1)
    return out


def shown():
    return [r[1] for r in rows()]


def row(name):
    def walk(parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.text(0) == name:
                return child
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(panel.tree.invisibleRootItem())


def name_it(text):
    """Type into the rename box the panel just opened, and press Enter."""
    boxes = panel.tree.viewport().findChildren(QLineEdit)
    if not boxes:
        return False
    box = boxes[-1]
    box.setText(text)
    panel.tree.commitData(box)
    panel.tree.closeEditor(box, QAbstractItemDelegate.EndEditHint.NoHint)
    app.processEvents()
    return True


def item(menu, text):
    for act in menu.actions():
        if act.text().strip() == text:
            return act
    return None


def titles(menu):
    return [a.text().strip() for a in menu.actions() if not a.isSeparator()]



# ------------------------------------------------------- picking a row up
DROP = QAbstractItemView.DropIndicatorPosition


def spot(item, where):
    """A point inside a row that means what Qt thinks it means: the top
    two pixels are "above this row", the bottom two "below it", and the
    middle "on it". Qt's own rule, so the test asks for a drop the way a
    hand would."""
    rect = panel.tree.visualItemRect(item)
    if where == "above":
        return QPoint(rect.center().x(), rect.top() + 1)
    if where == "below":
        return QPoint(rect.center().x(), rect.bottom() - 1)
    return rect.center()


def drag(item, onto, where, off_the_end=False):
    """Pick a row up and let it go, with the drag events Qt itself would
    send: enter, move, drop, on the tree's own viewport, carrying the
    tree's own mime data and naming the tree as the source.

    The one thing stood in for is QDrag.exec()'s nested loop, which
    cannot be spun offscreen with no pointer to follow — and it is stood
    in for exactly where Qt would spin it, from inside the panel's own
    startDrag, so the bookkeeping that wraps it runs in the real order.
    Everything the drop lands on — the indicator position, whether the
    move is allowed, what happens to bookmarks.json — is the real code.
    """
    tree = panel.tree
    tree.setCurrentItem(item)
    tree.scrollToItem(item)
    app.processEvents()
    mime = tree.mimeData([item])
    pos = (QPoint(tree.viewport().width() // 2,
                  tree.viewport().height() - 2) if off_the_end
           else spot(onto, where))
    seen = {}

    def loop(_self, _actions):
        for kind in (QDragEnterEvent, QDragMoveEvent, QDropEvent):
            at = QPointF(pos) if kind is QDropEvent else pos
            event = kind(at, Qt.DropAction.MoveAction, mime,
                         Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
            event.setDropAction(Qt.DropAction.MoveAction)
            QApplication.sendEvent(tree.viewport(), event)
            if kind is QDragMoveEvent:
                seen["accepted"] = event.isAccepted()
                seen["mark"] = tree._drop[0] if tree._drop else None
                seen["open"] = panel.isVisible()

    was = QTreeWidget.startDrag
    QTreeWidget.startDrag = loop
    try:
        tree.startDrag(Qt.DropAction.MoveAction)
    finally:
        QTreeWidget.startDrag = was
    app.processEvents()
    return seen


def parent_of(bid):
    entry = win._bookmark_by_id(bid)
    return None if entry is None else entry["parent"]


def order_in(fid):
    return [e["title"] for e in win._bookmark_kids(fid)]


print("\n-- the button --")
check("in the registry", "favorites" in B.TOOLBAR_BY_NAME)
check("shipped on", B.TOOLBAR_BY_NAME["favorites"]["on"] is True)
check("in the default set", "favorites" in B.TOOLBAR_DEFAULT)
check("on the bar today", "favorites" in win.toolbar_layout())
btn = win._tb_buttons.get("favorites")
check("a button exists", btn is not None)
check("and is on the screen", btn is not None and btn.isVisible())
check("with a folder on it", btn is not None and btn.text() == "\U0001f4c1",
      btn.text() if btn else "")
check("named the way Edge names it",
      "Favourites" in (btn.toolTip() if btn else ""), btn.toolTip())
check("it is the first button after the address bar",
      win.toolbar_layout().index("favorites")
      == win.toolbar_layout().index("address") + 1, win.toolbar_layout())

win.toggle_toolbar_button("favorites")
app.processEvents()
check("switched off: gone from the layout",
      "favorites" not in win.toolbar_layout())
check("switched off: gone from the screen", not btn.isVisible())
check("switched off: off the row too",
      win._navlay.indexOf(btn) == -1, win._navlay.indexOf(btn))
open_panel()
check("switched off: Ctrl+Shift+F still opens the panel", panel.isVisible())
panel.close()
app.processEvents()
win.toggle_toolbar_button("favorites")
app.processEvents()
check("switched on again: back on the layout",
      "favorites" in win.toolbar_layout())
check("switched on again: back on the screen", btn.isVisible())
check("the right-click menu offers it",
      "Favourites" in [a.text() for a in win.toolbar_menu().actions()])


print("\n-- it is a panel, not a chain of menus --")
set_bookmarks([])
reisen = win.add_bookmark_folder("Reisen", 0)
hotels = win.add_bookmark_folder("Hotels", reisen)
win.bookmarks.append({"id": 500, "type": "link", "title": "Sacher",
                      "url": URL, "icon": "", "parent": hotels, "t": 0})
win.save_bookmarks()
open_panel()
check("the panel is on the screen", panel.isVisible())
check("it says what it is", panel.title.text() == "Favourites",
      panel.title.text())
check("there is a search box", panel.search.isVisible())
check("it says what to do with a folder",
      panel.hint.text() == "Click a folder to open it.", panel.hint.text())
check("a folder is a row in the same list, not a submenu",
      row("Reisen") is not None and row("Reisen").childCount() == 1)
check("and it starts closed", not row("Reisen").isExpanded())
check("so what is inside it is not on the list yet",
      shown() == ["Reisen"], shown())
panel._clicked(row("Reisen"), 0)
app.processEvents()
check("clicking the folder opens it in place", row("Reisen").isExpanded())
check("the list grew downwards", shown() == ["Reisen", "Hotels"], shown())
check("and the panel is still open - nothing flew out sideways",
      panel.isVisible())
panel._clicked(row("Hotels"), 0)
app.processEvents()
check("a folder inside it opens the same way",
      shown() == ["Reisen", "Hotels", "Sacher"], shown())
panel._clicked(row("Reisen"), 0)
app.processEvents()
check("and clicking it again closes it", shown() == ["Reisen"], shown())
check("rows are a comfortable size",
      panel.tree.sizeHintForRow(0) >= 28, panel.tree.sizeHintForRow(0))
panel._clicked(row("Reisen"), 0)
app.processEvents()
panel._clicked(row("Hotels"), 0)
app.processEvents()
panel._clicked(row("Sacher"), 0)
spin(400)
check("clicking a bookmark opens it",
      win.current().url().toString().startswith("http://127.0.0.1"),
      win.current().url().toString())
check("and the panel gets out of the way", not panel.isVisible())


print("\n-- a folder inside a folder inside a folder, from the panel --")
set_bookmarks([])
open_panel()
panel.new_folder(0)
check("New folder opens a name box right away",
      panel.tree.state().name == "EditingState", panel.tree.state())
app.processEvents()
spin(60)
check("and the box is still there a moment later - saving the new "
      "folder must not redraw the list out from under it",
      panel.tree.state().name == "EditingState", panel.tree.state())
check("what he types is taken", name_it("Reisen"))
reisen = win.bookmarks[-1]["id"]
check("and the folder is called what he typed",
      win._bookmark_by_id(reisen)["title"] == "Reisen",
      win._bookmark_by_id(reisen)["title"])
panel.new_folder(reisen)
name_it("Hotels")
hotels = win.bookmarks[-1]["id"]
check("a folder made inside one sits inside it",
      win._bookmark_by_id(hotels)["parent"] == reisen)
panel.new_folder(hotels)
name_it("Wien")
wien = win.bookmarks[-1]["id"]
check("and three deep works too",
      win._bookmark_by_id(wien)["parent"] == hotels)
check("all three are open, so he can see where he is",
      [r[:2] for r in rows()]
      == [(0, "Reisen"), (1, "Hotels"), (2, "Wien")], rows())
win.bookmarks.append({"id": 501, "type": "link", "title": "Sacher",
                      "url": URL, "icon": "", "parent": wien, "t": 0})
win.save_bookmarks()
app.processEvents()
check("the panel redraws itself when the list changes elsewhere",
      "Sacher" in shown(), shown())
check("a folder three deep survives the file",
      [(e["title"], e["parent"]) for e in B.load_bookmarks()]
      == [(e["title"], e["parent"]) for e in win.bookmarks])


print("\n-- renaming, in the row --")
panel.rename(row("Hotels"))
check("the row turns into a box", bool(
    panel.tree.viewport().findChildren(QLineEdit)))
name_it("Unterkünfte")
check("what he typed is the folder's name now",
      win._bookmark_by_id(hotels)["title"] == "Unterkünfte",
      win._bookmark_by_id(hotels)["title"])
check("and the panel says so", "Unterkünfte" in shown(), shown())
panel.rename(row("Unterkünfte"))
name_it("   ")
check("a name rubbed out is not a name",
      win._bookmark_by_id(hotels)["title"] == "Unterkünfte")
check("and the row says what it always did",
      "Unterkünfte" in shown(), shown())
check("no dialog was opened at any point",
      QApplication.activeModalWidget() is None)


print("\n-- every row's own menu --")
menu = panel.row_menu(row("Unterkünfte"))
check("a folder's menu offers the lot",
      set(titles(menu)) >= {"Bookmark this page", "New folder", "Rename",
                            "Move to folder", "Delete"}, titles(menu))
menu = panel.row_menu(row("Sacher"))
check("a bookmark's menu offers its own",
      set(titles(menu)) >= {"Open", "Open in new tab", "Rename",
                            "Edit address…", "Move to folder",
                            "Delete"}, titles(menu))
opened = {}
was = panel._menu_for
panel._menu_for = lambda i, w: opened.setdefault("row", i.text(0))
panel._clicked(row("Sacher"), 1)
panel._menu_for = was
check("a plain left click on the row's ⋯ opens it - no right-click "
      "needed", opened.get("row") == "Sacher", opened)
check("and the ⋯ is on every row, always",
      all(r is not None and r.text(1) == "⋯"
          for r in (row("Reisen"), row("Sacher"))))

print("\n-- moving a thing into a folder --")
menu = panel.row_menu(row("Sacher"))
move = item(menu, "Move to folder").menu()
check("the move list offers the bar and every folder",
      [t.strip() for t in titles(move)]
      == ["Bookmarks bar", "Reisen", "Unterkünfte", "Wien"], titles(move))
check("the folder it is already in is not offered",
      not [a for a in move.actions() if a.text().strip() == "Wien"
           and a.isEnabled()])
[a for a in move.actions() if a.text().strip() == "Reisen"][0].trigger()
check("picking one moves it", win._bookmark_by_id(501)["parent"] == reisen,
      win._bookmark_by_id(501)["parent"])
menu = panel.row_menu(row("Reisen"))
move = item(menu, "Move to folder").menu()
check("a folder is never offered a home inside itself",
      [t.strip() for t in titles(move)] == ["Bookmarks bar"], titles(move))


print("\n-- the search box --")
win.bookmarks.append({"id": 502, "type": "link", "title": "Wetter",
                      "url": "https://wetter.example/", "icon": "",
                      "parent": 0, "t": 0})
win.save_bookmarks()
app.processEvents()
panel._clicked(row("Reisen"), 0)   # close it, so the hit has to open it
app.processEvents()
check("closed up first", shown() == ["Reisen", "Wetter"], shown())
panel.search.setText("sach")
app.processEvents()
check("a hit stays and everything else goes",
      shown() == ["Reisen", "Sacher"], shown())
check("the folder holding it opened itself", row("Reisen").isExpanded())
check("the hint gets out of the way", not panel.hint.isVisible())
panel.search.setText("wetter.example")
app.processEvents()
check("the address is searched too", shown() == ["Wetter"], shown())
panel.search.setText("zzzz")
app.processEvents()
check("nothing found says so", shown() == ["No bookmarks."], shown())
panel.search.setText("zzzzz")
app.processEvents()
check("and says it once, not once per letter typed",
      shown() == ["No bookmarks."], shown())
panel.search.setText("")
app.processEvents()
check("clearing it puts the list back",
      shown() == ["Reisen", "Wetter"], shown())
check("with the folder shut the way he left it",
      not row("Reisen").isExpanded())


print("\n-- this page, into a folder he picks --")
win.remove_bookmark(501)
app.processEvents()
view = win.current()
check("a real page is open", load(view, URL))
spin(300)
open_panel()
check("the button offers to bookmark it",
      panel.addbtn.text() == "Bookmark this page" and panel.addbtn.isEnabled(),
      panel.addbtn.text())
before = len(win.bookmarks)
menu = panel.row_menu(row("Unterkünfte"))
item(menu, "Bookmark this page").trigger()
app.processEvents()
check("one more bookmark", len(win.bookmarks) == before + 1)
added = win.bookmarks[-1]
check("and it landed in the folder whose menu he used",
      added["parent"] == hotels, added["parent"])
check("with the page's own title", added["title"] == "Sachertorte",
      added["title"])
check("the folder opened so he can see where it went",
      "Sachertorte" in shown(), shown())
check("the row is picked out too",
      panel.tree.currentItem() is not None
      and panel.tree.currentItem().text(0) == "Sachertorte")
panel.relabel()
check("the button now offers to take it out again",
      panel.addbtn.text() == "Remove bookmark", panel.addbtn.text())
menu = panel.row_menu(row("Wien"))
item(menu, "Bookmark this page").trigger()
app.processEvents()
check("asking again moves it rather than making a second one",
      len(win.bookmarks) == before + 1, len(win.bookmarks))
check("into the folder that was asked for",
      win._bookmark_by_id(added["id"])["parent"] == wien)
panel.addbtn.click()
app.processEvents()
check("and the button takes it back out",
      len(win.bookmarks) == before, len(win.bookmarks))


print("\n-- a folder thrown away takes what is in it --")
set_bookmarks([])
open_panel()
a = win.add_bookmark_folder("A", 0)
b = win.add_bookmark_folder("B", a)
c = win.add_bookmark_folder("C", b)
win.bookmarks.append({"id": 600, "type": "link", "title": "deep",
                      "url": "https://deep.example/", "icon": "",
                      "parent": c, "t": 0})
win.bookmarks.append({"id": 601, "type": "link", "title": "spared",
                      "url": "https://spared.example/", "icon": "",
                      "parent": 0, "t": 0})
win.save_bookmarks()
app.processEvents()
menu = panel.row_menu(row("A"))
kill = item(menu, "Delete").menu()
check("deleting a folder with things in it asks twice", kill is not None,
      titles(menu))
check("and says how much goes with it - the branch, not one level",
      "(3)" in titles(kill)[0], titles(kill))
kill.actions()[0].trigger()
app.processEvents()
left = [e["title"] for e in win.bookmarks]
check("the whole branch is gone", left == ["spared"], left)
check("the file agrees",
      [e["title"] for e in B.load_bookmarks()] == ["spared"])
check("and so does the panel", shown() == ["spared"], shown())


print("\n-- a folder cannot be put inside itself --")
set_bookmarks([])
a = win.add_bookmark_folder("A", 0)
b = win.add_bookmark_folder("B", a)
win.move_bookmark(a, b, 0)
check("A refuses to go inside its own child",
      win._bookmark_by_id(a)["parent"] == 0,
      win._bookmark_by_id(a)["parent"])
win.move_bookmark(a, a, 0)
check("and refuses to go inside itself",
      win._bookmark_by_id(a)["parent"] == 0)
win.move_bookmark(b, 0, 0)
check("but a folder does move out to the root",
      win._bookmark_by_id(b)["parent"] == 0)
win.move_bookmark(b, a, 0)
check("and back into another folder",
      win._bookmark_by_id(b)["parent"] == a)


print("\n-- the bookmarks bar keeps its menus --")
set_bookmarks([])
zeit = win.add_bookmark_folder("Zeitungen", 0)
sub = win.add_bookmark_folder("Regional", zeit)
win.bookmarks.append({"id": 700, "type": "link", "title": "ORF",
                      "url": "https://orf.example/", "icon": "",
                      "parent": zeit, "t": 0})
win.save_bookmarks()
app.processEvents()
menu = B.BookmarkMenu(win)
win.fill_folder_menu(menu, win._bookmark_by_id(zeit))
win._fill_folder_actions(menu, win._bookmark_by_id(zeit))
check("a folder on the bar still drops its contents down",
      "ORF" in titles(menu), titles(menu))
check("with a folder inside it as a submenu of its own",
      item(menu, "Regional") is not None
      and item(menu, "Regional").menu() is not None, titles(menu))
check("and the same things to do to it",
      set(titles(menu)) >= {"Rename", "New folder", "Delete"}, titles(menu))
check("the bar itself drew the two root entries",
      len(win.bmbar._entries) == 1, len(win.bmbar._entries))


print("\n-- a bookmarks.json from before any of this --")
flat = [
    {"id": 1, "type": "folder", "title": "Zeitungen", "url": "", "icon": "",
     "parent": 0, "t": 1},
    {"id": 2, "type": "link", "title": "ORF", "url": "https://orf.example/",
     "icon": "", "parent": 1, "t": 2},
    {"id": 3, "type": "link", "title": "Wetter", "url": "https://wetter.example/",
     "icon": "", "parent": 0, "t": 3},
]
B.BOOKMARKS_FILE.write_text(json.dumps(flat))
win.bookmarks = B.load_bookmarks()
win.rebuild_bookmarks_bar()
open_panel()
check("it loads unchanged",
      [(e["id"], e["parent"]) for e in win.bookmarks] == [(1, 0), (2, 1), (3, 0)],
      win.bookmarks)
check("the old folder is a row with the old contents inside it",
      row("Zeitungen") is not None and row("ORF") is not None)
check("and the loose bookmark is at the top level",
      row("Wetter").parent() is None)
panel.new_folder(1)
name_it("Regional")
check("an old flat folder can now hold a new one",
      win.bookmarks[-1]["parent"] == 1, win.bookmarks[-1])
check("the bar still draws it",
      len(win.bmbar._entries) == 2, len(win.bmbar._entries))


print("\n-- a bookmarks.json edited into a knot --")
knot = [
    {"id": 1, "type": "folder", "title": "A", "url": "", "icon": "",
     "parent": 2, "t": 1},
    {"id": 2, "type": "folder", "title": "B", "url": "", "icon": "",
     "parent": 1, "t": 2},
    {"id": 3, "type": "link", "title": "in the circle", "url": "https://a.example/",
     "icon": "", "parent": 1, "t": 3},
    {"id": 4, "type": "folder", "title": "own parent", "url": "", "icon": "",
     "parent": 4, "t": 4},
    {"id": 5, "type": "link", "title": "orphan", "url": "https://b.example/",
     "icon": "", "parent": 999, "t": 5},
    {"id": 6, "type": "folder", "title": "gone parent", "url": "", "icon": "",
     "parent": 999, "t": 6},
]
B.BOOKMARKS_FILE.write_text(json.dumps(knot))
loaded = B.load_bookmarks()   # must come back at all
check("a circle does not hang the load", len(loaded) == 6, len(loaded))
by = {e["id"]: e for e in loaded}
check("the circle is broken open",
      by[1]["parent"] == 0 and by[2]["parent"] == 0,
      (by[1]["parent"], by[2]["parent"]))
check("a folder that is its own parent is put at the root",
      by[4]["parent"] == 0)
check("a parent that was never there sends the entry to the root",
      by[5]["parent"] == 0 and by[6]["parent"] == 0)
check("nothing is thrown away", sorted(by) == [1, 2, 3, 4, 5, 6])
win.bookmarks = loaded
panel.refill()
app.processEvents()
check("and the panel draws it", panel.isVisible())
check("with everything reachable",
      set(shown()) >= {"A", "B", "own parent", "gone parent", "orphan"},
      shown())
win.remove_bookmark(1)
check("and a delete on it comes back",
      1 not in {e["id"] for e in win.bookmarks})

# and a chain far deeper than the panel is prepared to nest
chain = []
for i in range(1, 60):
    chain.append({"id": i, "type": "folder", "title": "L%d" % i, "url": "",
                  "icon": "", "parent": i - 1, "t": i})
B.BOOKMARKS_FILE.write_text(json.dumps(chain))
win.bookmarks = B.load_bookmarks()
check("a 59-deep chain loads", len(win.bookmarks) == 59)
panel.refill()
app.processEvents()
deep, node = 0, panel.tree.invisibleRootItem()
while node.childCount() and deep < 100:
    node = node.child(0)
    deep += 1
check("the panel stops nesting rather than falling over",
      0 < deep <= B.BOOKMARKS_DEPTH + 1, deep)
panel.close()
app.processEvents()




print("\n-- dragging things about --")
set_bookmarks([])
open_panel()
reisen = win.add_bookmark_folder("Reisen", 0)
zeit = win.add_bookmark_folder("Zeitungen", 0)
win.bookmarks.append({"id": 800, "type": "link", "title": "ORF",
                      "url": "https://orf.example/", "icon": "",
                      "parent": 0, "t": 0})
win.bookmarks.append({"id": 801, "type": "link", "title": "Wetter",
                      "url": "https://wetter.example/", "icon": "",
                      "parent": 0, "t": 0})
win.bookmarks.append({"id": 802, "type": "link", "title": "Bahn",
                      "url": "https://bahn.example/", "icon": "",
                      "parent": 0, "t": 0})
win.save_bookmarks()
app.processEvents()
check("four rows and two folders to start with",
      order_in(0) == ["Reisen", "Zeitungen", "ORF", "Wetter", "Bahn"],
      order_in(0))

# -- a bookmark into a folder
seen = drag(row("ORF"), row("Reisen"), "on")
check("the drag is taken", seen.get("accepted") is True, seen)
check("dropping on a folder says INTO, not between",
      seen.get("mark") == "into", seen)
check("the panel stayed open the whole way", seen.get("open") is True, seen)
check("and the bookmark is in the folder", parent_of(800) == reisen,
      parent_of(800))
check("the folder opened so he can see it went in",
      row("Reisen").isExpanded() and row("ORF") is not None)
check("the file agrees",
      [e["parent"] for e in B.load_bookmarks() if e["id"] == 800] == [reisen])

# -- a bookmark out of a folder, back to the root
seen = drag(row("ORF"), row("Zeitungen"), "below")
check("dropping between rows says BETWEEN, not into",
      seen.get("mark") == "between", seen)
check("it came back out to the top level", parent_of(800) == 0,
      parent_of(800))
check("and landed where the line was",
      order_in(0) == ["Reisen", "Zeitungen", "ORF", "Wetter", "Bahn"],
      order_in(0))

# -- reordering inside one folder, both ways
drag(row("Bahn"), row("Reisen"), "above")
check("a row dragged up moves up",
      order_in(0) == ["Bahn", "Reisen", "Zeitungen", "ORF", "Wetter"],
      order_in(0))
drag(row("Bahn"), row("Wetter"), "below")
check("and a row dragged down does not overshoot by one",
      order_in(0) == ["Reisen", "Zeitungen", "ORF", "Wetter", "Bahn"],
      order_in(0))

# -- a folder into a folder
seen = drag(row("Zeitungen"), row("Reisen"), "on")
check("a folder can be dropped into a folder",
      parent_of(zeit) == reisen, parent_of(zeit))
check("which is what the indicator said", seen.get("mark") == "into", seen)
drag(row("ORF"), row("Zeitungen"), "on")
check("and a bookmark can go two folders deep",
      parent_of(800) == zeit, parent_of(800))

# -- but never into itself
seen = drag(row("Reisen"), row("Zeitungen"), "on")
check("a folder is refused a home inside its own child",
      seen.get("accepted") is False, seen)
check("nothing was drawn to say it could",
      seen.get("mark") is None, seen)
check("and nothing moved", parent_of(reisen) == 0, parent_of(reisen))

# -- the empty space under the list means the top level
drag(row("ORF"), None, "on", off_the_end=True)
check("a drop on the empty space below puts it at the top level",
      parent_of(800) == 0, parent_of(800))
check("at the end of it", order_in(0)[-1] == "ORF", order_in(0))

# -- a drag that ends on nothing at all
before = [(e["id"], e["parent"]) for e in win.bookmarks]
tree = panel.tree
tree.setCurrentItem(row("Wetter"))
mime = tree.mimeData([row("Wetter")])
away = QDropEvent(QPointF(QPoint(5, 5)), Qt.DropAction.MoveAction, mime,
                  Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
QApplication.sendEvent(panel, away)
app.processEvents()
check("a drop the panel never armed does nothing at all",
      [(e["id"], e["parent"]) for e in win.bookmarks] == before)
check("and the panel is still there", panel.isVisible())

# -- the sheet does not shut the panel while something is in the air
panel.dragging = True
QApplication.sendEvent(panel, QMouseEvent(
    QEvent.Type.MouseButtonPress, QPointF(4, 400), QPointF(4, 400),
    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
    Qt.KeyboardModifier.NoModifier))
app.processEvents()
check("a press outside mid-drag is not a change of mind",
      panel.isVisible())
panel.dragging = False
QApplication.sendEvent(panel, QMouseEvent(
    QEvent.Type.MouseButtonPress, QPointF(4, 400), QPointF(4, 400),
    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
    Qt.KeyboardModifier.NoModifier))
app.processEvents()
check("but a press outside with nothing in the air closes it",
      not panel.isVisible())
open_panel()

# -- and a real press-and-pull really does start a real drag.
# The offscreen platform has no pointer for QDrag.exec()'s own loop to
# follow, so it comes straight back without delivering anything - but
# that it is entered and left with the panel still standing is the part
# no synthetic event can show, and it is checked here.
started = []
real_start = B.FavoritesTree.startDrag
B.FavoritesTree.startDrag = (
    lambda self, a: (started.append(a), real_start(self, a))[1])
try:
    grip = row("Wetter")
    panel.tree.setCurrentItem(grip)
    at = panel.tree.visualItemRect(grip).center()
    view = panel.tree.viewport()
    QTest.mousePress(view, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, at)
    pulled = QPoint(at.x(), at.y() + 25)
    QApplication.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseMove, QPointF(pulled),
        QPointF(view.mapToGlobal(pulled)), Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
finally:
    B.FavoritesTree.startDrag = real_start
check("a real press and pull on a row starts a real drag",
      len(started) == 1, started)
check("and QDrag's own loop hands the panel back in one piece",
      panel.isVisible() and panel.tree.state().name == "NoState",
      panel.tree.state())
check("with nothing left half-picked-up", panel.tree._dragged == 0
      and panel.dragging is False and panel.tree._drop is None)

check("the list scrolls itself near the edge while dragging",
      panel.tree.hasAutoScroll() and panel.tree.autoScrollMargin() > 0,
      panel.tree.autoScrollMargin())
check("Move to folder is still there for anyone who cannot drag",
      "Move to folder" in titles(panel.row_menu(row("Wetter"))),
      titles(panel.row_menu(row("Wetter"))))


print("\n-- the manager page --")
set_bookmarks([])
a = win.add_bookmark_folder("Reisen", 0)
b = win.add_bookmark_folder("Hotels", a)
win.bookmarks.append({"id": 700, "type": "link", "title": "Sacher",
                      "url": URL, "icon": "", "parent": b, "t": 0})
win.save_bookmarks()
win.open_bookmarks()
spin(1500)
pane = win._panes.get("bookmarks")
page = pane.view.page() if pane is not None else None
out = {}


def ask(script):
    out.clear()
    loop = QEventLoop()

    def back(value):
        out["v"] = value
        loop.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(8000)
    page.runJavaScript(script, back)
    loop.exec()
    return out.get("v")


heads = ask("Array.from(document.querySelectorAll('.group .gname'))"
            ".map(n => n.textContent)")
check("the manager lists every folder as its own section",
      heads == ["Bookmarks bar", "Reisen", "Hotels"], heads)
stepped = ask("Array.from(document.querySelectorAll('.group'))"
              ".map(n => n.style.marginLeft)")
check("and steps the nested one in", stepped == ["0px", "18px", "36px"],
      stepped)
opts = ask("(() => {const s = document.querySelectorAll('.row select');"
           " return Array.from(s).map(b =>"
           "   Array.from(b.options).map(o => o.textContent));})()")
check("the bookmark's move-to box offers every folder, nested one included",
      opts and [o.replace(" ", " ").strip() for o in opts[-1]]
      == ["Bookmarks bar", "Reisen", "Hotels"], opts)
check("and the nested one reads as nested",
      opts and opts[-1][2].startswith(" "), opts)
check("a folder is never offered a home inside itself",
      opts and len(opts) == 2 and "Hotels" not in
      [o.strip() for o in opts[0]], opts)
made = ask("(() => {const b = Array.from(document.querySelectorAll('.group button'))"
           ".filter(n => n.textContent === 'New folder');"
           " if (b.length < 3) return 'buttons:' + b.length;"
           " b[2].click(); return 'clicked';})()")
check("every section can start a folder inside itself", made == "clicked", made)
spin(900)
check("and the new one lands inside that folder",
      win.bookmarks[-1]["parent"] == b, win.bookmarks[-1])
win.close_pane()
spin(200)


print("\n-- nothing under the address bar --")
fresh = dict(win.config)
fresh.pop("bookmarksBar", None)
win.config = fresh
set_bookmarks([
    {"id": 1, "type": "link", "title": "ORF", "url": "https://orf.example/",
     "icon": "", "parent": 0, "t": 1}])
win.rebuild_bookmarks_bar()
app.processEvents()
check("a bookmark no longer makes a strip appear by itself",
      not win.bookmarks_bar_on())
check("and there is nothing under the address bar",
      not win.bmbar.isVisible())
open_panel()
check("the panel works without it", panel.isVisible() and shown() == ["ORF"],
      shown())
panel.close()
win.toggle_bookmarks_bar()
app.processEvents()
check("Ctrl+Shift+B still brings it back", win.bookmarks_bar_on()
      and win.bmbar.isVisible())
check("the toolbar's own menu ticks it while it is up",
      [a.isChecked() for a in win.toolbar_menu().actions()
       if a.text() == win._ui_str("bmBar")] == [True])
check("and the manager's switch says the same",
      win.bridge.bookmarksBarVisible(win._page_key) is True)
win.toggle_bookmarks_bar()
app.processEvents()
check("and takes it away again", not win.bmbar.isVisible())
check("with every switch agreeing",
      [a.isChecked() for a in win.toolbar_menu().actions()
       if a.text() == win._ui_str("bmBar")] == [False]
      and win.bridge.bookmarksBarVisible(win._page_key) is False)
check("a choice already made is left alone",
      win.config.get("bookmarksBar") is False)


print("\n-- both languages --")
for lang, want in (("de", "Favoriten"), ("en", "Favourites")):
    win.config["translateLang"] = lang
    panel.relabel()
    check("the panel speaks %s" % lang, panel.title.text() == want,
          panel.title.text())
    check("and so does its move-to wording (%s)" % lang,
          bool(win._ui_str("bmMoveTo")) and win._ui_str("bmMoveTo") != "bmMoveTo",
          win._ui_str("bmMoveTo"))


print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
else:
    print("all ok")
HTTPD.shutdown()
sys.exit(1 if fails else 0)
