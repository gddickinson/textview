"""Rich-document controller.

For document formats that have a meaningful HTML representation (currently
DOCX; EPUB / ODT could follow), the MainWindow keeps one of these around.
The body HTML is cached at load time (mammoth conversion is the slow part);
the theme wrapper is reapplied on every render so theme changes take
effect live without re-loading the file.
"""
from .document_extract import extract_docx_html, DocumentExtractionError
from .renderers import render_docx_html


# Formats that round-trip through HTML in this controller.
RICH_FORMATS = ("docx",)


class RichDocController:
    def __init__(self):
        self.body: str = ""
        self.format: str = ""

    def has_body(self) -> bool:
        return bool(self.body)

    def clear(self):
        self.body = ""
        self.format = ""

    def load(self, path: str, fmt: str) -> bool:
        """Extract the theme-agnostic body HTML. Returns True on success."""
        self.clear()
        if fmt not in RICH_FORMATS:
            return False
        try:
            if fmt == "docx":
                self.body = extract_docx_html(path)
                self.format = fmt
                return True
        except DocumentExtractionError:
            return False
        except Exception:
            return False
        return False

    def render(self, theme: dict, display=None) -> str:
        """Wrap the cached body in the given theme + typography settings.

        Returns full HTML, or '' when nothing is cached.
        """
        if not self.body:
            return ""
        if self.format == "docx":
            return render_docx_html(self.body, theme, display)
        return ""
