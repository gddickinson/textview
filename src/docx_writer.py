"""Markdown → DOCX converter.

Goes via HTML: render the markdown to HTML with the project's existing
`markdown` library, walk the result with stdlib `html.parser`, and emit
the corresponding `python-docx` elements. Supported:

  - Headings `<h1>` through `<h6>` → `Document.add_heading(level=N)`.
  - Paragraphs with inline `<strong>` / `<em>` / `<code>` / `<a>` runs.
  - Ordered + unordered lists (`List Number` / `List Bullet` styles).
  - Code blocks (`<pre><code>…</code></pre>`) — monospace runs.
  - Block quotes (`Intense Quote` style).
  - Horizontal rules → an empty paragraph + a thin run.

Not handled (intentional, to keep the writer compact):

  - Tables. python-docx supports them but the column-width / merge
    handling is enough work to warrant a follow-up.
  - Nested lists. The current walker emits each `<li>` as a flat list
    item; deeply nested markdown lists flatten to a single level.
  - Images. Markdown image syntax becomes `[alt text](url)` in the
    output paragraph.

`markdown_to_docx_bytes(md_text)` is the public entry point — returns
the `.docx` file as bytes so the save_as registry can write it like
any other binary converter.
"""
from __future__ import annotations

import io
from html.parser import HTMLParser


def markdown_to_docx_bytes(md_text: str) -> bytes:
    """Convert markdown text to a `.docx` file (bytes)."""
    from docx import Document  # type: ignore
    from markdown import markdown
    html = markdown(md_text, extensions=["extra", "tables", "fenced_code", "sane_lists"])
    doc = Document()
    _MdHtmlWalker(doc).feed(html)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class _MdHtmlWalker(HTMLParser):
    """Walk markdown-rendered HTML and emit python-docx elements.

    State machine:
      - `block`: the currently-active block element (paragraph, list-item,
        heading, code block, blockquote). `None` between blocks.
      - `inline_stack`: which inline modifiers are open (bold / italic /
        code / link). Affects formatting of runs emitted inside the
        block.
      - `pending_link`: the URL of the `<a>` we're currently inside (so
        we can suffix the run with `(url)` on close).
    """

    # Block tags we know how to handle.
    _HEADINGS = {f"h{i}": i for i in range(1, 7)}
    _LIST_STYLES = {"ul": "List Bullet", "ol": "List Number"}

    def __init__(self, doc):
        super().__init__(convert_charrefs=True)
        self.doc = doc
        self.block = None             # current paragraph / heading / list item
        self.list_style: str | None = None  # active "List Bullet" / "List Number"
        self.in_code_block = False
        self.in_blockquote = False
        self.inline_stack: list[str] = []
        self.pending_link: str | None = None

    # ---- block-level openers / closers ---------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in self._HEADINGS:
            self.block = self.doc.add_heading(level=self._HEADINGS[tag])
            return
        if tag == "p":
            style = "Intense Quote" if self.in_blockquote else None
            self.block = self.doc.add_paragraph(style=style) if style \
                else self.doc.add_paragraph()
            return
        if tag in self._LIST_STYLES:
            self.list_style = self._LIST_STYLES[tag]
            return
        if tag == "li":
            self.block = self.doc.add_paragraph(
                style=self.list_style or "List Bullet")
            return
        if tag == "pre":
            self.block = self.doc.add_paragraph()
            self.in_code_block = True
            return
        if tag == "blockquote":
            self.in_blockquote = True
            return
        if tag == "hr":
            self.doc.add_paragraph("───")  # cheap rule
            return
        if tag == "br":
            if self.block is not None:
                self.block.add_run().add_break()
            return
        # inline runs
        if tag == "strong" or tag == "b":
            self.inline_stack.append("bold")
        elif tag == "em" or tag == "i":
            self.inline_stack.append("italic")
        elif tag == "code":
            self.inline_stack.append("code")
        elif tag == "a":
            for k, v in attrs:
                if k == "href":
                    self.pending_link = v
                    break

    def handle_endtag(self, tag):
        if tag in self._HEADINGS or tag == "p" or tag == "li":
            self.block = None
            return
        if tag in self._LIST_STYLES:
            self.list_style = None
            return
        if tag == "pre":
            self.in_code_block = False
            self.block = None
            return
        if tag == "blockquote":
            self.in_blockquote = False
            return
        if tag == "a":
            if self.pending_link and self.block is not None:
                # Suffix the link target in parentheses so URLs aren't lost.
                run = self.block.add_run(f" ({self.pending_link})")
                run.italic = True
            self.pending_link = None
            return
        if tag in ("strong", "b", "em", "i", "code"):
            try: self.inline_stack.pop()
            except IndexError: pass

    # ---- text emission -------------------------------------------------

    def handle_data(self, text):
        if not text: return
        if self.block is None:
            # Text outside any handled block — drop it onto a new paragraph
            # so we don't lose content.
            if text.strip():
                self.block = self.doc.add_paragraph()
            else:
                return
        run = self.block.add_run(text)
        if self.in_code_block or "code" in self.inline_stack:
            run.font.name = "Menlo"
        if "bold" in self.inline_stack:
            run.bold = True
        if "italic" in self.inline_stack:
            run.italic = True
