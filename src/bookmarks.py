"""Persistent bookmarks for the embedded browser.

Stored in QSettings as a list of `(title, url)` pairs. The Bookmarks menu
is rebuilt on every change so it stays in sync. Two actions:
  - **Add bookmark…** asks for a title (defaulted to the current page title).
  - Each saved bookmark loads the URL when triggered.
"""
from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QInputDialog


class BookmarksController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.menu = None  # set by app.py once the menu bar is built

    def attach_menu(self, menu):
        self.menu = menu
        self.rebuild()

    # -- persistence ---------------------------------------------------------

    @staticmethod
    def _load() -> list[tuple[str, str]]:
        s = QSettings()
        raw = s.value("bookmarks/items", []) or []
        out = []
        for entry in raw:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                out.append((str(entry[0]), str(entry[1])))
        return out

    @staticmethod
    def _save(items):
        QSettings().setValue("bookmarks/items", [list(x) for x in items])

    # -- actions -------------------------------------------------------------

    def add_current(self):
        wv = self.window.viewer.web_view
        url = wv.current_url() or ""
        if not url or url == "about:blank":
            self.window.statusBar().showMessage(
                "Open a page first, then bookmark it.", 3000
            )
            return
        default_title = wv.current_title() or url
        title, ok = QInputDialog.getText(
            self.window, "Add bookmark", "Title:", text=default_title
        )
        if not ok or not title.strip():
            return
        items = self._load()
        items.append((title.strip(), url))
        self._save(items)
        self.rebuild()
        self.window.statusBar().showMessage(f"Bookmarked: {title}", 3000)

    def remove(self, title: str, url: str):
        items = [x for x in self._load() if x != (title, url)]
        self._save(items)
        self.rebuild()

    def rebuild(self):
        if self.menu is None:
            return
        self.menu.clear()
        # Action: add current
        add_act = QAction("Add current page…", self.menu)
        add_act.setShortcut("Ctrl+D")
        add_act.triggered.connect(self.add_current)
        self.menu.addAction(add_act)

        items = self._load()
        if items:
            self.menu.addSeparator()
            for title, url in items:
                a = QAction(title, self.menu)
                a.setToolTip(url)
                # Capture in default args; QAction.triggered passes a checked bool.
                a.triggered.connect(lambda _checked=False, u=url: self.window.open_url(u))
                self.menu.addAction(a)
            self.menu.addSeparator()
            clear = QAction("Clear all bookmarks", self.menu)
            clear.triggered.connect(self.clear_all)
            self.menu.addAction(clear)

    def clear_all(self):
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(
            self.window, "Clear bookmarks",
            "Remove all saved bookmarks?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._save([])
        self.rebuild()
