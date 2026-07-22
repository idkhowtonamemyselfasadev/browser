#!/usr/bin/env python3
"""A minimal, island-styled web browser. Tabs, search bar, start page."""
import json
import os
import sys
from pathlib import Path

# sites see prefers-color-scheme: dark and serve their native dark theme
# (0 = dark); must be set before Qt WebEngine starts
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    + " --blink-settings=preferredColorScheme=0")

from PyQt6.QtCore import Qt, QStringListModel, QTimer, QUrl, QUrlQuery
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QCompleter, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTabWidget, QTabBar, QToolButton,
)
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
)
from PyQt6.QtNetwork import (
    QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkRequest,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

APP_DIR = Path(__file__).resolve().parent
START_PAGE = QUrl.fromLocalFile(str(APP_DIR / "start.html"))
SEARCH_URL = "https://www.google.com/search?q={}"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
DOWNLOAD_DIR = Path.home() / "Downloads"
HOSTS_FILE = Path.home() / ".local/share/browser/hosts.json"

# domain guesses for the address bar ("wiki" -> wikipedia.org);
# visited sites are remembered and suggested too
COMMON_SITES = [
    "wikipedia.org", "youtube.com", "github.com", "google.com",
    "reddit.com", "amazon.de", "ebay.de", "netflix.com", "spotify.com",
    "twitch.tv", "instagram.com", "tiktok.com", "discord.com",
    "translate.google.com", "maps.google.com", "web.de", "gmx.net",
]

STYLE = """
* { font-family: "JetBrainsMono Nerd Font", "Inter", sans-serif; font-size: 13px; }
QMainWindow, #chrome { background: #11111b; }

QLineEdit#urlbar {
    background: rgba(30, 30, 46, 230);
    color: #cdd6f4;
    border: 1px solid rgba(137, 180, 250, 60);
    border-radius: 14px;
    padding: 7px 16px;
    selection-background-color: #89b4fa;
    selection-color: #11111b;
}
QLineEdit#urlbar:focus { border: 1px solid #89b4fa; }

QToolButton {
    background: rgba(30, 30, 46, 230);
    color: #cdd6f4;
    border: none;
    border-radius: 12px;
    padding: 5px 11px;
    font-weight: bold;
}
QToolButton:hover { background: #313244; color: #89b4fa; }

QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: rgba(30, 30, 46, 200);
    color: #a6adc8;
    border-radius: 11px;
    padding: 5px 6px 5px 14px;
    margin: 4px 3px 6px 3px;
    max-width: 180px;
}
QTabBar::tab:selected {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid rgba(137, 180, 250, 70);
}
QTabBar::tab:hover { color: #89b4fa; }

QToolButton#tabclose {
    background: rgba(108, 112, 134, 60);
    color: #cdd6f4;
    min-width: 18px; max-width: 18px;
    min-height: 18px; max-height: 18px;
    border-radius: 9px;
    padding: 0px;
    font-size: 12px;
    font-weight: normal;
}
QToolButton#tabclose:hover { background: rgba(243, 139, 168, 70); color: #f38ba8; }
"""


class WebView(QWebEngineView):
    def __init__(self, browser, profile):
        super().__init__()
        self.browser = browser
        self.setPage(QWebEnginePage(profile, self))
        self.page().fullScreenRequested.connect(self._fullscreen)

    def createWindow(self, _type):
        # tab for a link opened by a page (e.g. target=_blank);
        # the engine loads the URL itself, so don't load the start page
        return self.browser.new_tab(switch=True, blank=True)

    def _fullscreen(self, request):
        request.accept()
        self.browser.set_fullscreen(request.toggleOn())


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("browser")
        self.resize(1280, 820)

        self.profile = QWebEngineProfile("browser", self)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.downloadRequested.connect(self._download)
        s = self.profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        # the start page is a local file; without this it may not navigate
        # to the web (search box / quick links -> ERR_NETWORK_ACCESS_DENIED)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        # auto-darken pages that have no dark theme of their own
        s.setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, True)

        # top island bar: nav buttons + url bar
        self.urlbar = QLineEdit(objectName="urlbar")
        self.urlbar.setPlaceholderText("Search or enter address")
        self.urlbar.returnPressed.connect(self._navigate)

        # suggestions dropdown: domain guesses + Google search suggestions
        try:
            self.known_hosts = set(json.loads(HOSTS_FILE.read_text()))
        except Exception:
            self.known_hosts = set()
        self.suggest_model = QStringListModel(self)
        self.completer = QCompleter(self.suggest_model, self)
        self.completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.urlbar.setCompleter(self.completer)
        self.completer.activated.connect(
            lambda _: QTimer.singleShot(0, self._navigate))
        self.completer.popup().setStyleSheet("""
            QListView {
                background: #1e1e2e; color: #cdd6f4;
                border: 1px solid rgba(137, 180, 250, 100);
                border-radius: 10px; padding: 4px; outline: 0;
            }
            QListView::item { padding: 6px 10px; border-radius: 7px; }
            QListView::item:selected { background: #313244; color: #89b4fa; }
        """)
        self._nam = QNetworkAccessManager(self)
        self._suggest_reply = None
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(150)
        self._suggest_timer.timeout.connect(self._fetch_suggestions)
        self.urlbar.textEdited.connect(lambda _t: self._suggest_timer.start())

        back = QToolButton(text="‹")
        fwd = QToolButton(text="›")
        reload_ = QToolButton(text="⟳")
        newtab = QToolButton(text="+")
        back.clicked.connect(lambda: self.current().back())
        fwd.clicked.connect(lambda: self.current().forward())
        reload_.clicked.connect(lambda: self.current().reload())
        newtab.clicked.connect(lambda: self.new_tab())

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 2)
        bar.setSpacing(6)
        for w in (back, fwd, reload_):
            bar.addWidget(w)
        bar.addWidget(self.urlbar, 1)
        bar.addWidget(newtab)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.currentChanged.connect(self._tab_changed)

        self.chrome = QWidget(objectName="chrome")
        lay = QVBoxLayout(self.chrome)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)

        root = QWidget()
        rlay = QVBoxLayout(root)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(self.chrome)
        rlay.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

        for key, fn in {
            "Ctrl+T": self.new_tab,
            "Ctrl+W": lambda: self.close_tab(self.tabs.currentIndex()),
            "Ctrl+L": self._focus_url,
            "Ctrl+R": lambda: self.current().reload(),
            "F5": lambda: self.current().reload(),
            "Ctrl+Q": self.close,
            "Ctrl+Tab": lambda: self._cycle(1),
            "Ctrl+Shift+Tab": lambda: self._cycle(-1),
            "F11": lambda: self.set_fullscreen(not self.isFullScreen()),
        }.items():
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        self.new_tab()

    # ---- tabs ----
    def current(self):
        return self.tabs.currentWidget()

    def new_tab(self, url=None, switch=True, blank=False):
        view = WebView(self, self.profile)
        view.urlChanged.connect(lambda u, v=view: self._url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: self._title_changed(v, t))
        i = self.tabs.addTab(view, "New tab")

        close = QToolButton(text="✕", objectName="tabclose")
        close.clicked.connect(lambda _, v=view: self.close_tab(self.tabs.indexOf(v)))
        # wrapper centers the circle between the tab text and the tab's right wall
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.addWidget(close)
        self.tabs.tabBar().setTabButton(i, QTabBar.ButtonPosition.RightSide, holder)

        if switch:
            self.tabs.setCurrentIndex(i)
        if not blank:
            if url is None:
                view.load(START_PAGE)
                self._focus_url()
            else:
                view.load(QUrl(url))
        return view

    def close_tab(self, index):
        if self.tabs.count() == 1:
            # closing the last tab gives a fresh start page, not a dead window
            self.new_tab()
        w = self.tabs.widget(index)
        self.tabs.removeTab(index)
        w.deleteLater()

    def _cycle(self, step):
        self.tabs.setCurrentIndex(
            (self.tabs.currentIndex() + step) % self.tabs.count())

    # ---- navigation ----
    def _navigate(self):
        text = self.urlbar.text().strip()
        if not text:
            return
        if " " in text or ("." not in text and text != "localhost"):
            url = SEARCH_URL.format(QUrl.toPercentEncoding(text).data().decode())
        elif "://" in text:
            url = text
        else:
            url = "https://" + text
        self.current().load(QUrl(url))
        self.current().setFocus()

    def _focus_url(self):
        self.urlbar.setFocus()
        self.urlbar.selectAll()

    # ---- suggestions ----
    def _fetch_suggestions(self):
        text = self.urlbar.text().strip().lower()
        if len(text) < 2 or "://" in text or not self.urlbar.hasFocus():
            return
        domains = [d for d in COMMON_SITES + sorted(self.known_hosts)
                   if d.startswith(text) or d.split(".")[0].startswith(text)
                   or d.startswith("www." + text)]
        domains = list(dict.fromkeys(domains))
        domains = [d for d in domains
                   if not (d.startswith("www.") and d[4:] in domains)][:3]
        if self._suggest_reply is not None:
            self._suggest_reply.abort()
        url = QUrl(SUGGEST_URL)
        q = QUrlQuery()
        q.addQueryItem("client", "firefox")
        q.addQueryItem("q", text)
        url.setQuery(q)
        reply = self._nam.get(QNetworkRequest(url))
        self._suggest_reply = reply
        reply.finished.connect(
            lambda r=reply, t=text, d=domains: self._got_suggestions(r, t, d))

    def _got_suggestions(self, reply, text, domains):
        if reply is self._suggest_reply:
            self._suggest_reply = None
        searches = []
        try:
            searches = json.loads(bytes(reply.readAll()).decode())[1]
        except Exception:
            pass
        reply.deleteLater()
        if self.urlbar.text().strip().lower() != text:
            return  # user typed on; a newer request is coming
        items = domains + [s for s in searches if s not in domains][:6]
        self.suggest_model.setStringList(items)
        if items and self.urlbar.hasFocus():
            self.completer.complete()

    def _remember_host(self, url):
        host = url.host()
        if url.scheme() in ("http", "https") and host and host not in self.known_hosts:
            self.known_hosts.add(host)
            try:
                HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
                HOSTS_FILE.write_text(json.dumps(sorted(self.known_hosts)))
            except OSError:
                pass

    def _url_changed(self, view, url):
        self._remember_host(url)
        # never clobber the bar while the user is typing in it
        if view is self.current() and not self.urlbar.hasFocus():
            self.urlbar.setText("" if url == START_PAGE else url.toString())
            self.urlbar.setCursorPosition(0)

    def _title_changed(self, view, title):
        i = self.tabs.indexOf(view)
        if i >= 0:
            self.tabs.setTabText(i, title or "New tab")
            self.tabs.setTabToolTip(i, title)

    def _tab_changed(self, _index):
        view = self.current()
        if view:
            url = view.url()
            self.urlbar.setText("" if url == START_PAGE else url.toString())

    # ---- misc ----
    def set_fullscreen(self, on):
        self.chrome.setVisible(not on)
        self.tabs.tabBar().setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    def _download(self, request):
        request.setDownloadDirectory(str(DOWNLOAD_DIR))
        request.accept()


SINGLE_INSTANCE_SOCKET = "browser-single-instance"


def main():
    # single instance: two instances sharing one profile breaks Chromium's
    # network/cache storage, so hand off to the running one instead
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_SOCKET)
    if probe.waitForConnected(300):
        probe.write(b"raise")
        probe.flush()
        probe.waitForBytesWritten(300)
        return

    QGuiApplication.setDesktopFileName("browser")
    app = QApplication(sys.argv)
    app.setApplicationName("browser")
    app.setWindowIcon(QIcon(str(APP_DIR / "icon.svg")))
    app.setStyleSheet(STYLE)
    win = Browser()

    QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_SOCKET)
    server.newConnection.connect(
        lambda: (win.new_tab(), win.showNormal(), win.raise_(), win.activateWindow()))

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
