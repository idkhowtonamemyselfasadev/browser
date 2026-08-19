#!/usr/bin/env python3
"""A reload the user asked for takes back a "no".

Site permissions (microphone, camera, notifications) are answered once
and then remembered for the rest of the run. A yes is worth keeping - a
no was a trap: it was replayed in silence for hours, and the only way to
be asked again was to restart the whole browser. One mis-aimed click on
a call's microphone card and the call was mute.

Firefox's rule is the one that makes sense: a temporary block lasts
until the page is reloaded. This drives the real code and asserts it:

  * a deny is still remembered until something happens,
  * a reload the user asked for empties the book of noes - by the
    toolbar's path, by reload() on the view and by the context menu's
    Reload action,
  * a yes survives it, and so does an "always" stored in the config,
  * a reload no user asked for (the page reloading itself, which reaches
    the engine and never Qt) changes nothing,
  * the private book and the normal one never empty each other.

Offscreen, against scratch data; your own vault and config are never
opened.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _boot import B  # noqa: E402
from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication, QToolButton  # noqa: E402
from PyQt6.QtWebEngineCore import (  # noqa: E402
    QWebEnginePage, QWebEnginePermission,
)

MIC = QWebEnginePermission.PermissionType.MediaAudioCapture
CAM = QWebEnginePermission.PermissionType.MediaVideoCapture

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name
          + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails.append(name)


class Request:
    """Stands in for the engine's permission request.

    Qt only ever hands one of these out from a real getUserMedia(), and
    the copy the browser parks (QWebEnginePermission(permission)) cannot
    be built from anything else - so the copy constructor is stubbed to
    hand the same object back for the length of one call. Everything the
    browser asks of a request is here: what is wanted, who wants it, and
    the two ways to answer.
    """

    def __init__(self, origin, ptype=MIC):
        self._origin = QUrl(origin)
        self._type = ptype
        self.answer = None

    def permissionType(self):
        return self._type

    def origin(self):
        return self._origin

    def grant(self):
        self.answer = True

    def deny(self):
        self.answer = False


app = QApplication.instance() or QApplication(sys.argv[:1])
app.setApplicationName("browser-shot")
win = B.Browser()
win.resize(1300, 900)
# offscreen or not, a window nobody showed reports every widget invisible,
# and then the card assertions below pass for the wrong reason
win.show()
app.processEvents()


def ask(page, origin, ptype=MIC):
    """Put a request to the browser exactly as the engine would."""
    request = Request(origin, ptype)
    real = B.QWebEnginePermission
    B.QWebEnginePermission = lambda p: p   # park our own object, not a copy
    try:
        win._permission_requested(request, page)
    finally:
        B.QWebEnginePermission = real
    app.processEvents()
    return request


def carded():
    """Is a card up, waiting to be answered?"""
    return win._perm_widget is not None


def click(granted):
    """Answer the card on screen the way the user would."""
    card = win._perm_widget
    if card is None:
        return False
    for button in card.findChildren(QToolButton):
        if (button.objectName() == "permallow") == granted:
            button.click()
            app.processEvents()
            return True
    return False


def key(origin, ptype=MIC):
    """The book's own key for an origin - asked of the browser rather
    than spelled out here, so this cannot drift from what it files."""
    named, _show, _storable = B._origin_key(QUrl(origin))
    return "%s|%s" % (named, ptype.name)


view = win.current()
page = view.page()
SITE = "https://teams.example"
OTHER = "https://meet.example"
ALWAYS = "https://always.example"

print("(1) a no is remembered - that is the behaviour being fixed, "
      "not removed")
request = ask(page, SITE)
check("the first ask puts a card up", carded())
check("...and nothing is answered while it stands", request.answer is None,
      request.answer)
check("Deny answers the request", click(False) and request.answer is False,
      request.answer)
check("...and writes the no into the session book",
      win._session_perms.get(key(SITE)) is False, win._session_perms)
again = ask(page, SITE)
check("the next ask is denied outright", again.answer is False, again.answer)
check("...with no card to answer", not carded())

print("\n(2) the reload he asked for hands the question back")
view.reload()
app.processEvents()
check("the no is gone from the book", key(SITE) not in win._session_perms,
      win._session_perms)
third = ask(page, SITE)
check("so the site may ask again", third.answer is None, third.answer)
check("...and it is a card, not a silent no", carded())
click(False)

print("\n(3) every path a user can reload by")
win._session_perms[key(SITE)] = False
win._tb_reload()                      # the toolbar button, Ctrl+R and F5
app.processEvents()
check("the toolbar's reload forgets it too",
      key(SITE) not in win._session_perms, win._session_perms)
win._session_perms[key(SITE)] = False
action = page.action(QWebEnginePage.WebAction.Reload)
# the menu only offers it when there is something to reload; the click
# itself is what is under test, so arm it and click
action.setEnabled(True)
action.trigger()
app.processEvents()
check("the context menu's Reload forgets it as well",
      key(SITE) not in win._session_perms, win._session_perms)

print("\n(4) a yes is not something anybody reloads to undo")
granted = ask(page, OTHER)
check("a fresh origin gets its own card", carded())
check("Allow answers it", click(True) and granted.answer is True,
      granted.answer)
check("...and the yes is in the book",
      win._session_perms.get(key(OTHER)) is True, win._session_perms)
win._session_perms[key(SITE)] = False
view.reload()
app.processEvents()
check("the reload leaves the yes alone",
      win._session_perms.get(key(OTHER)) is True, win._session_perms)
check("...while the no beside it goes", key(SITE) not in win._session_perms,
      win._session_perms)
kept = ask(page, OTHER)
check("so that site is still granted without a card",
      kept.answer is True and not carded(), kept.answer)

print("\n(5) an \"always\" he stored survives it")
win.config.setdefault("permissions", {})[key(ALWAYS)] = True
win._session_perms[key(SITE)] = False
view.reload()
app.processEvents()
check("the stored always is still stored",
      win.config["permissions"].get(key(ALWAYS)) is True,
      win.config.get("permissions"))
stored = ask(page, ALWAYS)
check("...and still answers for the site",
      stored.answer is True and not carded(), stored.answer)

print("\n(6) a reload no user asked for changes nothing")
win._session_perms[key(SITE)] = False
# what a page's own location.reload() reaches: the engine, through the
# page action's slot - never the view's reload() and never the action
page.triggerAction(QWebEnginePage.WebAction.Reload)
app.processEvents()
check("the page reloading itself keeps the no",
      win._session_perms.get(key(SITE)) is False, win._session_perms)

print("\n(7) the private book and the normal one are separate")
private = win.new_private_tab()
app.processEvents()
check("the private tab is off the record",
      private is not None and win._page_is_private(private.page()), private)
win._session_perms[key(SITE)] = False
win._session_perms[key(OTHER)] = True
win._private_perms[key(SITE, CAM)] = False
win._private_perms[key(OTHER)] = True
private.reload()
app.processEvents()
check("reloading the private tab empties its own noes",
      key(SITE, CAM) not in win._private_perms, win._private_perms)
check("...keeps its own yeses",
      win._private_perms.get(key(OTHER)) is True, win._private_perms)
check("...and does not touch the normal book",
      win._session_perms.get(key(SITE)) is False, win._session_perms)
win._private_perms[key(SITE, CAM)] = False
view.reload()
app.processEvents()
check("reloading a normal tab empties the normal noes",
      key(SITE) not in win._session_perms, win._session_perms)
check("...and leaves the private book alone",
      win._private_perms.get(key(SITE, CAM)) is False, win._private_perms)

print("\n%d checks failed" % len(fails))
if fails:
    for f in fails:
        print("  - " + f)
sys.exit(1 if fails else 0)
