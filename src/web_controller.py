"""Browser-mode glue.

Owns the small bit of MainWindow state that's specific to having a URL in
the viewer (status-bar updates, switching to web mode, accepting an http
URL via the file-open path). Mirrors the shape of `PdfController` and
`RichDocController` so MainWindow can stay slim.
"""
import re

from PyQt6.QtCore import QObject

from .web_security import WebSecurityHandler


def _strip_html(html: str) -> str:
    """Convert readability's HTML summary into something the markdown
    renderer can re-style consistently.

    We keep paragraph and heading boundaries as blank lines but drop the
    rest of the tag soup; the Markdown renderer takes care of the
    presentation. Quick and dirty; trafilatura would be more thorough.
    """
    text = re.sub(r"</(p|div|li|h[1-6]|br|tr)>", "\n\n", html, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class WebController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        wv = window.viewer.web_view
        wv.title_changed.connect(self._on_title)
        wv.url_changed.connect(self._on_url)
        self.security = WebSecurityHandler(window, wv)
        self.apply_settings(window.settings_manager.display)

    def apply_settings(self, d):
        """Push web-related settings into the engine."""
        self.security.apply_profile_settings(d)

    def search_engine(self):
        return self.window.settings_manager.display.web_search_engine

    def load(self, url: str):
        """Switch to the browser and load the given URL.

        For non-file URLs, revert any per-file remote-trust grant from the
        previous load so it can't bleed into a different page.
        """
        d = self.window.settings_manager.display
        if not url.startswith("file://"):
            self.security.apply_profile_settings(d, force_remote=None)
        self.window.viewer.web_view.load(url, self.search_engine())
        self.window.viewer.show_web()
        self.window._current_format = "web"
        self.window._current_path = None
        self.window.lbl_file.setText(url)
        self.window.lbl_format.setText("Format: web")

    def open_dialog(self):
        self.window.viewer.show_web()
        self.window._current_format = "web"
        self.window._current_path = None
        self.window.lbl_format.setText("Format: web")
        self.window.lbl_encoding.setText("")
        self.window.lbl_size.setText("")
        self.window.viewer.web_view.focus_address_bar()

    def go_home(self):
        self.load(self.window.settings_manager.display.web_home_url or "about:blank")

    def view_source(self):
        if self.window.viewer.mode() != self.window.viewer.MODE_WEB:
            self.window.statusBar().showMessage("View source only works in the browser.", 3000)
            return
        from .renderers import apply_pygments
        from .themes import get_theme

        def _show(html: str):
            self.window._current_content = html
            self.window._current_format = "html"
            self.window.viewer.code.setPlainText(html)
            d = self.window.settings_manager.display
            apply_pygments(self.window.viewer.code, html, "page.html",
                           get_theme(d.theme)["pygments_style"], "html")
            self.window.viewer.code.document().clearUndoRedoStacks()
            self.window.viewer.show_code()
        self.window.viewer.web_view.view_source(_show)

    def open_devtools(self):
        if self.window.viewer.mode() == self.window.viewer.MODE_WEB:
            self.window.viewer.web_view.open_devtools()
        else:
            self.window.statusBar().showMessage(
                "Developer tools only available in the browser.", 3000
            )

    def reading_mode(self):
        """Extract main content from the current page and show it themed."""
        if self.window.viewer.mode() != self.window.viewer.MODE_WEB:
            self.window.statusBar().showMessage(
                "Reading mode only available in the browser.", 3000)
            return
        from .renderers import render_markdown_html
        from .themes import get_theme

        def _show(html: str):
            try:
                from readability import Document
                doc = Document(html)
                title = doc.short_title()
                article = doc.summary()
            except Exception as e:
                self.window.statusBar().showMessage(
                    f"Reading mode failed: {e}", 5000)
                return
            d = self.window.settings_manager.display
            theme = get_theme(d.theme)
            md = f"# {title}\n\n" + _strip_html(article)
            wrapped = render_markdown_html(md, theme, d)
            self.window.viewer.rendered.setHtml(wrapped)
            self.window.viewer.show_rendered()
            self.window._current_format = "html"

        self.window.viewer.web_view.engine.page().toHtml(_show)

    def _on_title(self, title: str):
        if self.window.viewer.mode() == self.window.viewer.MODE_WEB:
            self.window.setWindowTitle(f"TextView — {title or 'Web'}")
            if title:
                self.window.lbl_file.setText(title)

    def _on_url(self, url: str):
        if self.window.viewer.mode() == self.window.viewer.MODE_WEB:
            self.window.lbl_encoding.setText(url[:80])
