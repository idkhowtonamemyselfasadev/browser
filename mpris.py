"""MPRIS: the keyboard's media keys, playerctl and the bar's widget.

A sibling module like theme_web.py, capture.py, privacy.py, page_guard.py
and notes.py, loaded the same safe way: without this file the browser
starts and simply is not a media player as far as the desktop is
concerned.

What this is: the desktop's standard way of asking "what is playing"
and "please pause" is a D-Bus service called
org.mpris.MediaPlayer2.<something>. Qt ships QtDBus, so the browser can
be one -- no new package, no daemon, nothing fetched. The tab that is
making a sound is the player; the transport goes through the browser's
own media handlers, which reach the page's Media Session, which is what
the site itself listens to.

On a machine with no session bus (a server, a test run) everything here
answers "no bus" and nothing else happens. That is not an error: it is
what a browser with no desktop around it should do.
"""

import json

try:
    from PyQt6.QtDBus import (QDBusConnection, QDBusMessage,
                              QDBusAbstractAdaptor)
    from PyQt6.QtCore import QObject, pyqtSlot, pyqtProperty, QVariant
    HAVE_DBUS = True
except ImportError:  # pragma: no cover - Qt built without QtDBus
    HAVE_DBUS = False
    QDBusAbstractAdaptor = object
    QObject = object

#: the name the browser takes on the bus. The suffix is what playerctl
#: and waybar show, so it is the browser's own name and not a number.
SERVICE = "org.mpris.MediaPlayer2.browser"
PATH = "/org/mpris/MediaPlayer2"


def available():
    """Whether there is a session bus to be a player on."""
    if not HAVE_DBUS:
        return False
    return QDBusConnection.sessionBus().isConnected()


class Root(QDBusAbstractAdaptor):
    """org.mpris.MediaPlayer2 -- who the player is."""

    if HAVE_DBUS:
        Q_CLASSINFO = None   # set up in __init__ by the metaobject below

    def __init__(self, parent):
        super().__init__(parent)
        self.browser = parent.browser

    @pyqtSlot()
    def Raise(self):
        """The desktop asking for the window. Exactly what clicking the
        taskbar entry would do."""
        window = getattr(self.browser, "showNormal", None)
        if window is not None:
            self.browser.showNormal()
            self.browser.raise_()
            self.browser.activateWindow()

    @pyqtSlot()
    def Quit(self):
        """Refused on purpose: a media key must never close a browser
        full of tabs, and nothing on this interface is worth that."""
        return

    @pyqtProperty(bool)
    def CanQuit(self):
        return False

    @pyqtProperty(bool)
    def CanRaise(self):
        return True

    @pyqtProperty(str)
    def Identity(self):
        return "browser"

    @pyqtProperty(str)
    def DesktopEntry(self):
        return "browser"

    @pyqtProperty("QStringList")
    def SupportedUriSchemes(self):
        return ["http", "https"]

    @pyqtProperty("QStringList")
    def SupportedMimeTypes(self):
        return []


class Player(QDBusAbstractAdaptor):
    """org.mpris.MediaPlayer2.Player -- the transport and the metadata.

    Every control goes to the browser's own media handlers, which talk
    to the page's Media Session: the site decides what "next track"
    means, which is right -- Amazon Music's next track is not something
    a browser should guess at.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.state = parent

    @pyqtSlot()
    def Play(self):
        self.state.browser.media_do("play")

    @pyqtSlot()
    def Pause(self):
        self.state.browser.media_do("pause")

    @pyqtSlot()
    def PlayPause(self):
        self.state.browser.media_do("playpause")

    @pyqtSlot()
    def Stop(self):
        self.state.browser.media_do("pause")

    @pyqtSlot()
    def Next(self):
        self.state.browser.media_do("next")

    @pyqtSlot()
    def Previous(self):
        self.state.browser.media_do("prev")

    @pyqtSlot("qlonglong")
    def Seek(self, offset):
        self.state.browser.media_seek(secs=int(offset) // 1000000)

    @pyqtProperty(str)
    def PlaybackStatus(self):
        return self.state.status

    @pyqtProperty("QVariantMap")
    def Metadata(self):
        return self.state.metadata

    @pyqtProperty(float)
    def Volume(self):
        return 1.0

    @pyqtProperty(bool)
    def CanControl(self):
        return True

    @pyqtProperty(bool)
    def CanPlay(self):
        return True

    @pyqtProperty(bool)
    def CanPause(self):
        return True

    @pyqtProperty(bool)
    def CanGoNext(self):
        return True

    @pyqtProperty(bool)
    def CanGoPrevious(self):
        return True

    @pyqtProperty(bool)
    def CanSeek(self):
        return True


class Service(QObject):
    """The object the two interfaces hang off, and the state they read.

    Kept deliberately dumb: the browser pushes what is playing in with
    update(), and the adaptors answer from that. Nothing here reaches
    into a page.
    """

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.status = "Stopped"
        self.metadata = {}
        self._root = None
        self._player = None
        self.registered = False

    def start(self):
        """Take the name on the bus. Answers False where there is no
        bus, which is not a failure."""
        if not available():
            return False
        bus = QDBusConnection.sessionBus()
        self._root = Root(self)
        self._player = Player(self)
        if not bus.registerObject(PATH, self,
                                  QDBusConnection.RegisterOption
                                  .ExportAllContents):
            return False
        if not bus.registerService(SERVICE):
            return False
        self.registered = True
        return True

    def stop(self):
        if not self.registered or not available():
            return False
        bus = QDBusConnection.sessionBus()
        bus.unregisterService(SERVICE)
        bus.unregisterObject(PATH)
        self.registered = False
        return True

    def update(self, playing=None, title="", artist="", album="", url=""):
        """What is playing now. Called from the browser's media poll."""
        self.status = ("Playing" if playing else
                       ("Paused" if playing is False else "Stopped"))
        meta = {}
        if title or artist:
            meta = {
                "mpris:trackid": "/org/mpris/MediaPlayer2/browser/track",
                "xesam:title": str(title or ""),
                "xesam:artist": [str(artist)] if artist else [],
                "xesam:album": str(album or ""),
                "xesam:url": str(url or ""),
            }
        self.metadata = meta
        self._announce()
        return self.status

    def _announce(self):
        """Tell the bus the properties changed, which is how waybar and
        playerctl notice without polling."""
        if not self.registered or not available():
            return False
        message = QDBusMessage.createSignal(
            PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged")
        message.setArguments(["org.mpris.MediaPlayer2.Player",
                              {"PlaybackStatus": self.status,
                               "Metadata": self.metadata},
                              []])
        QDBusConnection.sessionBus().send(message)
        return True
