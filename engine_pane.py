"""Engine pane — view the current page through my own Rust engine.

Ctrl+Shift+E renders the active tab's HTML with web_engine (the from-scratch
engine at ~/claude/web-engine, compiled to web_engine.so next to this file)
and shows the result in an overlay pane. The active theme is handed to the
engine as a user stylesheet, so unlike normal browsing the theme actually
recolours the page itself. Esc, ✕ or a click outside closes it.

browser.py is only touched to import this module and bind the shortcut;
everything else lives here.
"""

import sys

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget)

# web_engine.so is loaded on first use, not when the browser starts: a
# native module that is missing, truncated or built against other
# libraries must never keep the browser from starting, and one that is
# mapped into every running browser can be pulled out from under it
# (SIGBUS) by a rebuild that overwrites the file in place.
web_engine = None
_load_error = None


def _engine():
    global web_engine, _load_error
    if web_engine is None and _load_error is None:
        try:
            import web_engine as mod
            web_engine = mod
        except Exception as exc:  # ImportError, or a panic in PyInit
            _load_error = exc
    return web_engine

MARGIN = 28  # gap between the pane and the window edge


def _mod(browser):
    # The browser module itself (theme_palette and friends live there).
    return sys.modules[type(browser).__module__]


def theme_css(p):
    """Map the browser's 22-token palette onto engine user CSS.

    This sheet is applied with user-origin priority inside the engine,
    so it wins over the page's own colours for these elements."""
    return (
        f'html {{ background: {p["bg"]}; }}'
        f' body {{ color: {p["text"]}; }}'
        f' h1 {{ color: {p["accent"]}; }}'
        f' h2, h3 {{ color: {p["accentLt"]}; }}'
        f' a {{ color: {p["accent"]}; }}'
        f' code, pre {{ color: {p["green"]}; }}'
        f' b, strong {{ color: {p["bright"]}; }}'
    )


def toggle(browser):
    pane = getattr(browser, "_engine_pane", None)
    if pane is not None and pane.isVisible():
        pane.dismiss()
        return
    view = browser.current()
    if view is None or browser._is_header(view) or not hasattr(view, "page"):
        return
    if pane is None:
        pane = browser._engine_pane = EnginePane(browser)
    url = view.url().toString()
    view.page().toHtml(lambda html: pane.show_html(html, url))


class EnginePane(QWidget):
    def __init__(self, browser):
        super().__init__(browser, objectName="engpane")
        self.browser = browser
        self._html = ""
        self._url = ""
        self._restyling = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.panel = QWidget(self, objectName="engpanel")
        col = QVBoxLayout(self.panel)
        col.setContentsMargins(1, 1, 1, 1)
        col.setSpacing(0)

        head = QWidget(self.panel, objectName="enghead")
        row = QHBoxLayout(head)
        row.setContentsMargins(12, 8, 8, 8)
        self.title = QLabel("My Engine", head, objectName="engtitle")
        esc = QLabel("Esc", head, objectName="engesc")
        close_btn = QToolButton(head)
        close_btn.setText("✕")
        close_btn.clicked.connect(self.dismiss)
        row.addWidget(self.title, 1)
        row.addWidget(esc)
        row.addWidget(close_btn)
        col.addWidget(head)

        self.image = QLabel()
        self.image.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea(self.panel)
        self.scroll.setWidget(self.image)
        col.addWidget(self.scroll, 1)

        # a window drag sends a Resize per step; render once it settles
        self._rerender = QTimer(self, singleShot=True, interval=150)
        self._rerender.timeout.connect(self.render_page)

        self._retheme()
        self.hide()
        browser.installEventFilter(self)

    # -- open / close -----------------------------------------------------

    def show_html(self, html, url):
        self._html = html or ""
        self._url = url or ""
        self.title.setText(f"My Engine — {url}" if url else "My Engine")
        self._retheme()
        self.place()
        self.render_page()
        self.show()
        self.raise_()
        self.setFocus()

    def dismiss(self):
        self.hide()
        view = self.browser.current()
        if view is not None and not self.browser._is_header(view):
            view.setFocus()

    def place(self):
        self.setGeometry(self.parentWidget().rect())
        self.panel.setGeometry(
            self.rect().adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN))

    # -- rendering --------------------------------------------------------

    def render_page(self):
        engine = _engine()
        if engine is None:
            # install with a rename, never an in-place cp: a running
            # browser that has the old file mapped crashes when it is
            # truncated underneath it
            self.image.setText(
                "web_engine.so could not be loaded (%s).\n"
                "Build it: cd ~/claude/web-engine && "
                "cargo build --release --features python && "
                "cp target/release/libweb_engine.so ~/browser/web_engine.so.new"
                " && mv -f ~/browser/web_engine.so.new ~/browser/web_engine.so"
                % (_load_error or "missing"))
            return
        palette = _mod(self.browser).theme_palette()
        width = max(400, self.panel.width() - 24)
        try:
            w, h, buf = engine.render(
                self._html, theme_css=theme_css(palette), width=width)
        except BaseException as exc:  # engine panics arrive as exceptions
            self.image.setText(f"engine error: {exc}")
            return
        img = QImage(buf, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        self.image.setPixmap(QPixmap.fromImage(img))
        self.image.resize(w, h)

    def _retheme(self):
        try:
            p = _mod(self.browser).theme_palette()
        except Exception:
            return
        self.setStyleSheet(
            "#engpane { background: rgba(0, 0, 0, 120); }"
            f'#engpanel {{ background: {p["surface"]};'
            f'  border: 1px solid {p["sunken"]}; }}'
            f'#enghead {{ background: {p["mantle"]};'
            f'  border-bottom: 1px solid {p["sunken"]}; }}'
            f'QLabel#engtitle {{ color: {p["text"]}; }}'
            f'QLabel#engesc {{ color: {p["overlay"]}; }}'
            "QToolButton { background: transparent; border: none;"
            f'  color: {p["subtext"]}; }}'
            f'QToolButton:hover {{ color: {p["red"]}; }}'
            f'QScrollArea {{ background: {p["bg"]}; border: none; }}'
            f'QScrollArea > QWidget > QWidget {{ background: {p["bg"]}; }}')

    # -- events -----------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.dismiss()

    def eventFilter(self, obj, event):
        if (obj is self.browser and self.isVisible()
                and event.type() == QEvent.Type.Resize):
            self.place()
            self._rerender.start()
        return False

    def changeEvent(self, event):
        # apply_theme() restyles the app; follow it live if we're up.
        if (event.type() == QEvent.Type.StyleChange
                and self.isVisible() and not self._restyling):
            self._restyling = True
            try:
                self._retheme()
                self.render_page()
            finally:
                self._restyling = False
        super().changeEvent(event)
