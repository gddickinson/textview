"""Document tab bar.

Phase 1 design: lightweight. Each tab is identified by a file path (or
None for an empty/welcome tab). Switching tabs is equivalent to
`open_file(path)` for that tab, so the existing unsaved-changes prompt
in `EditController.confirm_discard` handles the dirty-buffer case
naturally — no separate per-tab buffer caching needed yet.

This means:
  + Tiny code surface; controllers stay unchanged.
  + Always shows current on-disk content per tab.
  − Switching reloads the file (cheap for code, modest for PDFs).

The session is saved to ~/.cache/TextView/session.json so reopening the
app brings back your tabs.
"""
import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QTabBar


_SESSION = Path.home() / ".cache" / "TextView" / "session.json"


class TabBar(QObject):
    """Owns a `QTabBar` widget. The window mounts it above the central
    container. We use QTabBar (not QTabWidget) because we want the tabs
    to drive what the existing single viewer shows, not host independent
    sub-widgets per tab.
    """

    requested_open = pyqtSignal(str)   # path to (re)open
    requested_clear = pyqtSignal()     # user closed the active tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = QTabBar()
        self.bar.setTabsClosable(True)
        self.bar.setMovable(True)
        self.bar.setExpanding(False)
        self.bar.setDocumentMode(True)
        self.bar.setUsesScrollButtons(True)
        self.bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.bar.tabCloseRequested.connect(self._on_close)
        self.bar.currentChanged.connect(self._on_current_changed)
        self._suppress_signal = False

    def widget(self) -> QTabBar:
        return self.bar

    def add_or_select(self, path: str | None, title: str):
        """Add a tab for `path` (or focus it if already open).

        `path=None` is a welcome / untitled tab — only one is kept.
        """
        for i in range(self.bar.count()):
            if self.bar.tabData(i) == path:
                self._suppress_signal = True
                self.bar.setCurrentIndex(i)
                self._suppress_signal = False
                self._update_title(i, title)
                return
        self._suppress_signal = True
        idx = self.bar.addTab(title)
        self.bar.setTabData(idx, path)
        if path:
            self.bar.setTabToolTip(idx, path)
        self.bar.setCurrentIndex(idx)
        self._suppress_signal = False

    def update_active(self, path: str | None, title: str):
        i = self.bar.currentIndex()
        if i < 0:
            self.add_or_select(path, title)
            return
        self.bar.setTabData(i, path)
        self._update_title(i, title)
        if path:
            self.bar.setTabToolTip(i, path)

    def _update_title(self, idx: int, title: str):
        if self.bar.tabText(idx) != title:
            self.bar.setTabText(idx, title)

    def paths(self) -> list[str]:
        return [self.bar.tabData(i) for i in range(self.bar.count())
                if self.bar.tabData(i)]

    # -- internal -----------------------------------------------------------

    def _on_current_changed(self, idx: int):
        if self._suppress_signal or idx < 0:
            return
        path = self.bar.tabData(idx)
        if path:
            self.requested_open.emit(path)
        else:
            self.requested_clear.emit()

    def _on_close(self, idx: int):
        # Don't drop the last tab — it just resets to welcome.
        if self.bar.count() <= 1:
            self._suppress_signal = True
            self.bar.setTabData(idx, None)
            self.bar.setTabText(idx, "Welcome")
            self._suppress_signal = False
            self.requested_clear.emit()
            return
        self.bar.removeTab(idx)

    def close_all(self):
        """Drop every tab and reset to a single welcome tab. Suppresses
        currentChanged for each removeTab so we don't reload N-1 files
        on the way down — only the final clear is announced."""
        self._suppress_signal = True
        while self.bar.count() > 1:
            self.bar.removeTab(self.bar.count() - 1)
        if self.bar.count() == 1:
            self.bar.setTabData(0, None)
            self.bar.setTabText(0, "Welcome")
        self._suppress_signal = False
        self.requested_clear.emit()

    # -- session persistence ------------------------------------------------

    def save_session(self):
        try:
            _SESSION.parent.mkdir(parents=True, exist_ok=True)
            data = {"paths": self.paths(),
                    "active": self.bar.currentIndex()}
            _SESSION.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def restore_session(self) -> list[str]:
        try:
            data = json.loads(_SESSION.read_text())
            return list(data.get("paths") or [])
        except (OSError, json.JSONDecodeError):
            return []

    def restore_into(self, window):
        for path in self.restore_session():
            try:
                window.open_file(path)
            except Exception:
                continue
