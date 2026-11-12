"""Web interface for TextView (FastAPI app + plain ES-module front end, also exported as a static GitHub Pages site).

Contents:
    app          — FastAPI routes under /api and STATIC_ENDPOINTS for scripts/build_static.py.
    samples      — demo files (sample_files/, samples/, templates) and the viewer payload built with file_loader,
                   html_render and table_data.
    display      — themes, Pygments token colours, DisplaySettings defaults (parsed from settings.py).
    catalog      — extension map, bundled format database, docs/*.md pages, README "Why TextView".
    search       — BM25 workspace-search demo over docs/ + sample_files/ (workspace_index).
    inspect_api  — unknown-file inspector + security scan for uploads.
    samples/     — demo files written by scripts/make_web_samples.py.
    static/      — front end; *_engine.js are JS ports tested against Python by *_engine.test.mjs.
"""
