"""Extract plain text from binary document formats.

Each extractor returns a string. They never raise unless extraction is
impossible — in which case they raise `DocumentExtractionError` with a
human-readable message that the caller can surface in the UI.
"""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


class DocumentExtractionError(Exception):
    pass


def extract_pdf(path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise DocumentExtractionError(f"pypdf is not available: {e}")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise DocumentExtractionError("PDF is encrypted (password-protected).")
        out = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as e:
                text = f"[page {i}: extraction failed: {e}]"
            out.append(f"───── Page {i} ─────\n{text.strip()}\n")
        return "\n".join(out) if out else "[PDF contained no extractable text]"
    except DocumentExtractionError:
        raise
    except Exception as e:
        raise DocumentExtractionError(f"Could not read PDF: {e}")


def extract_docx_html(path) -> str:
    """Render DOCX to HTML using mammoth.

    Returns the body HTML fragment (mammoth's output). Preserves headings,
    lists, tables, bold/italic, hyperlinks, and inlines images as base64.
    Wrap with `renderers.render_docx_html` to produce a themed full document.
    """
    try:
        import mammoth
    except ImportError as e:
        raise DocumentExtractionError(f"mammoth is not available: {e}")
    try:
        with open(str(path), "rb") as f:
            result = mammoth.convert_to_html(f)
        return result.value or ""
    except Exception as e:
        raise DocumentExtractionError(f"Could not render DOCX: {e}")


def extract_docx(path) -> str:
    try:
        import docx  # python-docx
    except ImportError as e:
        raise DocumentExtractionError(f"python-docx is not available: {e}")
    try:
        doc = docx.Document(str(path))
        lines = []
        for p in doc.paragraphs:
            style = (p.style.name if p.style else "").lower()
            text = p.text
            if not text.strip():
                lines.append("")
                continue
            if style.startswith("heading 1"):
                lines.append(f"# {text}")
            elif style.startswith("heading 2"):
                lines.append(f"## {text}")
            elif style.startswith("heading 3"):
                lines.append(f"### {text}")
            elif style.startswith("heading"):
                lines.append(f"#### {text}")
            elif "list" in style:
                lines.append(f"- {text}")
            else:
                lines.append(text)
        for table in doc.tables:
            lines.append("")
            for row in table.rows:
                cells = [c.text.replace("\n", " ").strip() for c in row.cells]
                lines.append(" | ".join(cells))
        return "\n".join(lines) if lines else "[DOCX contained no text]"
    except Exception as e:
        raise DocumentExtractionError(f"Could not read DOCX: {e}")


def extract_rtf(path) -> str:
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError as e:
        raise DocumentExtractionError(f"striprtf is not available: {e}")
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        return rtf_to_text(raw)
    except Exception as e:
        raise DocumentExtractionError(f"Could not read RTF: {e}")


def extract_epub(path) -> str:
    try:
        from ebooklib import epub, ITEM_DOCUMENT
    except ImportError as e:
        raise DocumentExtractionError(f"EbookLib is not available: {e}")
    try:
        from html.parser import HTMLParser
    except ImportError as e:
        raise DocumentExtractionError(f"html.parser missing: {e}")

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip += 1
            elif tag in ("br",):
                self.parts.append("\n")
            elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style") and self._skip:
                self._skip -= 1
            if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
                self.parts.append("\n")

        def handle_data(self, data):
            if self._skip == 0:
                self.parts.append(data)

    try:
        book = epub.read_epub(str(path))
    except Exception as e:
        raise DocumentExtractionError(f"Could not read EPUB: {e}")
    chunks = []
    title = book.get_metadata("DC", "title")
    if title:
        chunks.append(f"# {title[0][0]}\n")
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        s = _Stripper()
        try:
            s.feed(item.get_content().decode("utf-8", errors="replace"))
        except Exception:
            continue
        text = "".join(s.parts)
        # collapse runs of blank lines
        cleaned = []
        blank = 0
        for line in text.splitlines():
            if line.strip():
                cleaned.append(line.rstrip())
                blank = 0
            else:
                if blank < 1:
                    cleaned.append("")
                blank += 1
        chunks.append("\n".join(cleaned))
    return "\n\n".join(chunks) if chunks else "[EPUB contained no text]"


def extract_odt(path) -> str:
    """Minimal ODT extractor: pulls text:p / text:h content from content.xml."""
    try:
        with zipfile.ZipFile(str(path)) as z:
            with z.open("content.xml") as f:
                tree = ET.parse(f)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise DocumentExtractionError(f"Could not read ODT: {e}")
    ns = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    root = tree.getroot()
    out = []
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1] if "}" in elem.tag else elem.tag
        if tag == "h":
            level = int(elem.attrib.get(f"{{{ns['text']}}}outline-level", "1"))
            text = "".join(elem.itertext()).strip()
            if text:
                out.append(("#" * max(1, min(6, level))) + " " + text)
        elif tag == "p":
            text = "".join(elem.itertext())
            out.append(text)
    return "\n".join(out) if out else "[ODT contained no text]"
