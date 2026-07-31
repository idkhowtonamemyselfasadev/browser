#!/usr/bin/env python3
"""Nothing in the Favourites panel is cut off along the bottom.

Covers, in the browser rather than in a docstring:

  * every text row of the panel - the title, the hint line, the search
    box, the three buttons along the foot and the rows of the list
    itself - is at least as tall as the line its font draws plus
    whatever the sheet pads it with, so a descender has somewhere to go
  * the same for every entry of a row's ... menu
  * and the same again with the sheet's fonts wound up, because a row
    given a *fixed* height fits at the size it was drawn against and
    cuts at the next one along: this is what caught `height: 30px` on
    the rows of the list
  * nothing is drawn against the bottom edge of its own box, measured
    in the pixels rather than in the geometry - a cut descender is ink
    on the last row of the box
  * the card is never taller than the window it hangs in and never
    reaches past either edge of it, which is how the row of buttons
    along its bottom - the one that says Remove bookmark - was losing
    its lower half
  * and that holds after the list has grown underneath an already-open
    panel, which is exactly what bookmarking the page you are on does

In German: the strings are longer and the umlauts and the ß sit high
and low in the line, so a tight row shows here first.

Offscreen, against scratch data files, in one Browser. Your own
bookmarks are never opened.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B, SCRATCH  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QRect  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


B.BOOKMARKS_FILE.write_text(json.dumps([
    {"id": 1, "type": "folder", "parent": 0, "title": "Lieblingsseiten"},
    {"id": 2, "type": "link", "parent": 1, "title": "Sachertorte",
     "url": "https://example.org/sachertorte"},
    {"id": 3, "type": "link", "parent": 0, "title": "Übergrößenträger",
     "url": "https://example.org/uebergroessen"},
    {"id": 4, "type": "link", "parent": 0, "title": "Vergnügungspark",
     "url": "https://example.org/vergnuegung"},
]))

app = QApplication(sys.argv)
app.setApplicationName("browser-shot")

win = B.Browser()
win.config["language"] = "de"
win.resize(1280, 860)
win.show()
app.processEvents()

panel = win.favorites_panel()
panel.open_up()
for _ in range(6):
    app.processEvents()


def wind_fonts_up(pixels):
    """The browser's own sheet with every font in it that many pixels
    bigger. A row whose height grows with its font passes at any
    setting; a row handed one fixed height passes at the size it was
    drawn against and cuts at the next."""
    sheet = B.theme_style()
    if pixels:
        sheet = re.sub(r"font-size:\s*(\d+)px",
                       lambda m: "font-size: %dpx" % (int(m.group(1))
                                                     + pixels), sheet)
    app.setStyleSheet(sheet)
    panel.refill()
    panel.tree.expandAll()
    for _ in range(6):
        app.processEvents()


def fits(name, widget, height, pad=0):
    """A row holds its text when it is at least as tall as the line its
    font draws plus the padding the sheet asked for around it."""
    need = widget.fontMetrics().height() + pad
    check("%s holds its line (%dpx font + %dpx padding)"
          % (name, widget.fontMetrics().height(), pad),
          height >= need, "row is %dpx, needs %dpx" % (height, need))


def ink_reaches_edge(widget, rect=None, inset=0):
    """True when something drawn inside `rect` touches its bottom row of
    pixels, which is what a cut-off descender looks like. The border a
    button draws round itself is not text, so it is inset past."""
    img = widget.grab().toImage()
    scale = img.width() / max(1, widget.width())
    if rect is not None:
        rect = QRect(int(rect.left() * scale), int(rect.top() * scale),
                     int(rect.width() * scale), int(rect.height() * scale))
    box = rect if rect is not None else QRect(0, 0, img.width(), img.height())
    if inset:
        box = box.adjusted(inset, inset, -inset, -inset)
    box = box.intersected(QRect(0, 0, img.width(), img.height()))
    lowest = None
    for y in range(box.top(), box.bottom() + 1):
        back = img.pixel(box.left(), y)
        for x in range(box.left(), box.right() + 1):
            if img.pixel(x, y) != back:
                lowest = y
                break
    return lowest is not None and lowest >= box.bottom()


def measure(bump):
    wind_fonts_up(bump)
    print("\n-- the panel's own rows, fonts wound up %d px --" % bump)
    fits("the title", panel.title, panel.title.height())
    fits("the hint line", panel.hint, panel.hint.height())
    fits("the search box", panel.search, panel.search.height(), 16)
    fits("Bookmark this page", panel.addbtn, panel.addbtn.height(), 16)
    fits("New folder", panel.foldbtn, panel.foldbtn.height(), 16)
    fits("Bookmark manager", panel.managebtn, panel.managebtn.height(), 16)

    # the labels draw no border of their own, so there is nothing to
    # inset past on them; the box and the buttons do, and a border is
    # not text
    for widget, name, inset in ((panel.title, "title", 0),
                                (panel.hint, "hint line", 0),
                                (panel.search, "search box", 2),
                                (panel.addbtn, "add button", 2),
                                (panel.foldbtn, "folder button", 2),
                                (panel.managebtn, "manage button", 2)):
        check("no ink of the %s is on its bottom edge (+%d)"
              % (name, bump), not ink_reaches_edge(widget, inset=inset))

    print("\n-- the rows of the list, fonts wound up %d px --" % bump)
    tree = panel.tree
    rows = []
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        node = stack.pop(0)
        rows.append(node)
        stack = [node.child(k) for k in range(node.childCount())] + stack
    check("there are rows to measure (+%d)" % bump, len(rows) == 4, len(rows))
    for node in rows:
        rect = tree.visualItemRect(node)
        fits("the row %r" % node.text(0), tree, rect.height())
        if rect.bottom() >= tree.viewport().height() - 1:
            # a row the list has run out of room for is cut by the list
            # and not by its own height: that is what scrolling is for,
            # and the pixels there say nothing about this
            continue
        check("no ink of the row %r is on its bottom edge (+%d)"
              % (node.text(0), bump),
              not ink_reaches_edge(tree.viewport(), rect))

    print("\n-- a row's ... menu, fonts wound up %d px --" % bump)
    menu = panel.row_menu(rows[2])
    menu.show()
    for _ in range(6):
        app.processEvents()
    entries = [a for a in menu.actions() if not a.isSeparator()]
    check("the menu has entries to measure (+%d)" % bump,
          len(entries) >= 5, len(entries))
    for act in entries:
        rect = menu.actionGeometry(act)
        fits("the entry %r" % act.text(), menu, rect.height(), 12)
        check("no ink of the entry %r is on its bottom edge (+%d)"
              % (act.text(), bump), not ink_reaches_edge(menu, rect))
    menu.hide()
    for _ in range(4):
        app.processEvents()


for bump in (0, 6, 12):
    measure(bump)
wind_fonts_up(0)

print("\n-- the card stays inside the window --")


def inside(tag):
    card = panel.card.geometry()
    over = max(0, card.bottom() - panel.rect().bottom())
    check("the card is clear of the bottom edge (%s)" % tag, over == 0,
          "%d px past it, card=%s, window is %d tall"
          % (over, card, panel.height()))
    check("and clear of the top edge (%s)" % tag, card.top() >= 0, card.top())


inside("as it opens")

# windows with less room under the button than the panel would like,
# and the list growing underneath an already-open panel - which is what
# bookmarking the page you are on from the panel does
for height in (860, 700, 600, 520, 440):
    win.resize(1280, height)
    app.processEvents()
    panel.place()
    app.processEvents()
    for count in (1, 8, 20, 40):
        B.BOOKMARKS_FILE.write_text(json.dumps(
            [{"id": i, "type": "link", "parent": 0,
              "title": "Vergnügungspark Nummer %d" % i,
              "url": "https://example.org/%d" % i}
             for i in range(1, count + 1)]))
        win.bookmarks = B.load_bookmarks()
        panel.refill()
        app.processEvents()
        inside("%d tall, %d bookmarks" % (height, count))

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
else:
    print("all ok")
sys.exit(1 if fails else 0)
