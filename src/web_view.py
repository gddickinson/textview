"""Embedded web browser view.

`WebView` packages a `QWebEngineView` with a slim address bar (back, forward,
reload/stop, URL input, progress indicator) into one widget that drops into
the `TextViewer` stack as `MODE_WEB`. Reuses the existing window chrome —
no tab bar, just one page at a time. Multi-tab can come later without
disturbing this code.
"""
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QToolButton, QLabel,
    QSizePolicy,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings


def _setup_profile():
    """Isolate cache + storage to TextView's own directory.

    Run once per process; idempotent. Per-load security flags
    (LocalContentCanAccessRemoteUrls etc.) are applied separately by
    `WebSecurityHandler.apply_profile_settings(d)` from MainWindow.
    """
    profile = QWebEngineProfile.defaultProfile()
    base = Path.home() / ".cache" / "TextView" / "webengine"
    base.mkdir(parents=True, exist_ok=True)
    profile.setCachePath(str(base / "cache"))
    profile.setPersistentStoragePath(str(base / "storage"))
    s = profile.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)


_PROFILE_READY = False


def ensure_profile():
    global _PROFILE_READY
    if _PROFILE_READY:
        return
    _setup_profile()
    _PROFILE_READY = True


class WebView(QWidget):
    """Browser view: address bar + QWebEngineView."""

    title_changed = pyqtSignal(str)
    url_changed = pyqtSignal(str)
    load_progress = pyqtSignal(int)
    load_finished = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_profile()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_address_bar())
        self.engine = QWebEngineView(self)
        self.engine.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.engine, 1)
        self._wire_signals()
        # Friendly default page so the panel isn't blank on first show.
        self.engine.setHtml(
            "<html><body style='font-family:-apple-system; padding:32px;"
            " color:#888'><h1>Browser</h1><p>Press <b>Ctrl+L</b> "
            "to focus the address bar, or type a URL above.</p></body></html>"
        )

    # -- UI build ------------------------------------------------------------

    def _build_address_bar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(4)

        def btn(text, tip, slot):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setFixedWidth(28)
            return b

        self.btn_back = btn("◀", "Back", lambda: self.engine.back())
        self.btn_forward = btn("▶", "Forward", lambda: self.engine.forward())
        self.btn_reload = btn("↻", "Reload (F5)", lambda: self.engine.reload())
        self.btn_stop = btn("✕", "Stop", lambda: self.engine.stop())
        for b in (self.btn_back, self.btn_forward, self.btn_reload, self.btn_stop):
            h.addWidget(b)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter URL or search…")
        self.url_input.returnPressed.connect(self._on_url_entered)
        h.addWidget(self.url_input, 1)

        self.status = QLabel("")
        self.status.setMinimumWidth(60)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self.status)

        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_address_bar)
        return bar

    # -- public API ----------------------------------------------------------

    def load(self, url_or_text: str, search_engine: str = "duckduckgo"):
        """Smart-load: bare hostname → https; bare query → search."""
        text = (url_or_text or "").strip()
        if not text:
            return
        if text.startswith(("http://", "https://", "file://", "about:", "data:")):
            url = text
        elif "://" in text:
            url = text
        elif text.startswith("/") or (Path(text).exists() and Path(text).is_file()):
            url = "file://" + str(Path(text).resolve())
        elif " " not in text and "." in text:
            url = "https://" + text
        else:
            from urllib.parse import quote_plus
            templates = {
                "duckduckgo": "https://duckduckgo.com/?q={}",
                "google":     "https://www.google.com/search?q={}",
                "bing":       "https://www.bing.com/search?q={}",
                "none":       "https://duckduckgo.com/?q={}",
            }
            url = templates.get(search_engine, templates["duckduckgo"]).format(quote_plus(text))
        self.engine.load(QUrl(url))
        self.url_input.setText(url)

    # -- web zoom (used by Ctrl+= / Ctrl+- / Ctrl+0 in web mode) -----------

    def zoom_in(self):
        self.engine.setZoomFactor(min(5.0, self.engine.zoomFactor() * 1.1))

    def zoom_out(self):
        self.engine.setZoomFactor(max(0.25, self.engine.zoomFactor() * 0.9))

    def zoom_reset(self, factor: float = 1.0):
        self.engine.setZoomFactor(float(factor))

    # -- developer tools / view source --------------------------------------

    def view_source(self, callback):
        """Asynchronously fetch the page's outerHTML and pass it to `callback`."""
        self.engine.page().toHtml(callback)

    def open_devtools(self):
        """Open Chromium DevTools in a separate window."""
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        if not getattr(self, "_devtools_view", None):
            self._devtools_view = QWebEngineView()
            self._devtools_view.setWindowTitle("DevTools")
            self._devtools_view.resize(900, 700)
            self.engine.page().setDevToolsPage(self._devtools_view.page())
        self._devtools_view.show()
        self._devtools_view.raise_()

    def current_url(self) -> str:
        return self.engine.url().toString()

    def current_title(self) -> str:
        return self.engine.title()

    def focus_address_bar(self):
        self.url_input.setFocus()
        self.url_input.selectAll()

    def find_text(self, query: str, case_sensitive=False, backward=False):
        """Wire-compatible with the SearchBar attach() pattern."""
        from PyQt6.QtWebEngineCore import QWebEnginePage
        flags = QWebEnginePage.FindFlag(0)
        if case_sensitive:
            flags |= QWebEnginePage.FindFlag.FindCaseSensitively
        if backward:
            flags |= QWebEnginePage.FindFlag.FindBackward
        self.engine.findText(query, flags)

    # -- internals -----------------------------------------------------------

    def _wire_signals(self):
        e = self.engine
        e.urlChanged.connect(lambda u: (self.url_input.setText(u.toString()),
                                        self.url_changed.emit(u.toString())))
        e.titleChanged.connect(lambda t: self.title_changed.emit(t or ""))
        e.loadStarted.connect(lambda: self.status.setText("Loading…"))
        e.loadProgress.connect(self._on_progress)
        e.loadFinished.connect(self._on_finished)

    def _on_progress(self, percent: int):
        self.load_progress.emit(percent)
        self.status.setText(f"{percent}%")

    def _on_finished(self, ok: bool):
        self.status.setText("Ready" if ok else "Failed")
        self.load_finished.emit(ok)

    def _on_url_entered(self):
        self.load(self.url_input.text())
