"""TextView — modular PyQt6 text/code/document viewer.

Public modules:
    settings           — DisplaySettings dataclass, SettingsManager.
    themes             — Named color palettes.
    file_loader        — Format detection, file IO, encoding handling.
    document_extract   — PDF / DOCX / RTF / EPUB / ODT text extraction.
    renderers          — Pygments highlighting and markdown rendering.
    viewer             — CodeViewer, LineNumberArea, TextViewer.
    config_panel       — ConfigPanel dock widget (live-updating).
    exporter           — HTML/PDF/Markdown/Text/RTF/PNG export + print.
    app                — MainWindow.
    html_render        — Qt-free lexer choice + themed markdown / DOCX HTML (re-exported by renderers).
    table_data         — Qt-free CSV parsing, numeric detection, column statistics (used by table_model, stats_dialog).
    web                — FastAPI web interface + static site (see web/__init__.py).
"""
