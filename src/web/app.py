"""FastAPI web app for TextView: serves the front end in static/ and the JSON API under /api.

Run with `python run_web.py` (http://127.0.0.1:8110, local only). `scripts/build_static.py` exports every path in
STATIC_ENDPOINTS to JSON for the GitHub Pages site (plus the raw sample files and doc screenshots), so keep that list
in step with the GET routes below. The two POST routes (open / inspect an uploaded file) run TextView's Python
loaders; on the static site static_api.js answers them with the JS ports in static/*_engine.js instead.

The chat agent, workspace-RAG answers, LSP, Jupyter kernel and PDF editing stay in the desktop app: they need an LLM
API key, language servers or native libraries, and nothing here calls an external service.
"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..file_loader import FORMAT_MAP
from ..templates import list_templates
from ..themes import THEMES
from . import catalog, display, samples, search
from .inspect_api import inspect_upload

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(title="TextView")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    """Project summary and real counts for the home page."""
    return {"title": "TextView", "repo": "textview",
            "description": "A modular PyQt6 file viewer + lightweight editor with an AI agent that knows your "
                           "workspace.",
            "counts": {"extensions": len(FORMAT_MAP), "formats": len(set(FORMAT_MAP.values())),
                       "themes": len(THEMES), "templates": len(list_templates()),
                       "format_db": len(catalog.bundled_entries()), "docs": len(catalog.doc_names()),
                       "samples": len(samples.sample_files())},
            "why": catalog.why_payload()}


@app.get("/api/display")
def display_info():
    return display.themes_payload()


@app.get("/api/files")
def files():
    return {"items": samples.catalog()}


@app.get("/api/file/{item_id}")
def file(item_id: str):
    d = samples.payload(item_id)
    if d is None:
        raise HTTPException(404, f"No demo file {item_id!r}")
    return d


@app.get("/api/rendered/{item_id}/{theme}")
def rendered(item_id: str, theme: str):
    name = samples.theme_by_slug(theme)
    html = samples.rendered_html(item_id, name) if name else None
    if html is None:
        raise HTTPException(404, "No rendered view for that file / theme")
    return {"html": html}


@app.get("/api/raw/{name}", include_in_schema=False)
def raw(name: str):
    p = samples.sample_files().get(name)
    if p is None:
        raise HTTPException(404, "No such sample file")
    return FileResponse(p)


@app.get("/api/shot/{name}", include_in_schema=False)
def shot(name: str):
    p = catalog.screenshots().get(name)
    if p is None:
        raise HTTPException(404, "No such screenshot")
    return FileResponse(p)


@app.get("/api/formats")
def formats():
    return catalog.formats_payload()


@app.get("/api/formatdb")
def formatdb():
    return catalog.format_db_payload()


@app.get("/api/docs")
def docs():
    return catalog.docs_index()


@app.get("/api/doc/{name}")
def doc(name: str):
    d = catalog.doc_page(name)
    if d is None:
        raise HTTPException(404, f"No doc {name!r}")
    return d


@app.get("/api/corpus")
def corpus():
    return search.corpus_payload()


@app.get("/api/search")
def do_search(q: str = "", k: int = 8):
    return search.search(q, k=max(1, min(k, 50)))


async def _read_upload(upload: UploadFile) -> tuple[str, bytes]:
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large for the web app (25 MB); open it in the desktop app instead.")
    name = Path(upload.filename or "upload.bin").name or "upload.bin"
    return name, data


@app.post("/api/open")
async def open_upload(file: UploadFile = File(...)):
    """Open an uploaded file with TextView's loaders (same payload as /api/file)."""
    name, data = await _read_upload(file)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / name
        p.write_bytes(data)
        try:
            d = samples.payload_for_path(p)
            if d["rendered"]:
                d["html_by_theme"] = {th: samples.rendered_html_for_path(p, th) for th in THEMES}
        except Exception as e:  # loaders raise many types (extraction errors, bad zip, ...)
            raise HTTPException(400, f"TextView could not open {name}: {e}")
    d["id"] = "upload"
    return d


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...)):
    """Unknown-file inspector + security scan on an uploaded file."""
    name, data = await _read_upload(file)
    return inspect_upload(name, data)


def _rendered_paths():
    return [f"/rendered/{i}/{samples.slug(t)}" for i in samples.rendered_ids() for t in THEMES]


# GET paths (without the /api prefix) written to the static site as api/<path>.json.
STATIC_ENDPOINTS = (["/info", "/display", "/files", "/formats", "/formatdb", "/docs", "/corpus"]
                    + [f"/file/{i['id']}" for i in samples.catalog()]
                    + [f"/doc/{n}" for n in catalog.doc_names()]
                    + _rendered_paths())
