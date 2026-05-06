"""Lexical workspace index for AI-grounded retrieval.

Walks a project root, chunks every supported file by format-natural
units (text/code by line groups, PDFs by page, notebooks by cell,
images by filename + parent path), and builds a BM25 inverted index
over the chunks. The agent's `query_workspace(...)` tool returns the
top-K chunks with file+locator citations the UI can click open.

No embeddings, no model deps — pure-Python BM25. Embeddings can plug in
later by replacing `BM25Index` in `WorkspaceIndex`.

Locator strings are deterministic, format-agnostic anchors:
    line:N    — text/code, 1-indexed line
    page:N    — PDF page, 1-indexed
    cell:N    — notebook cell, 0-indexed
    (empty)   — file-level anchor (used for images)
"""
from __future__ import annotations
import hashlib
import math
import pickle
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# Skip directories that are conventionally noise for indexing.
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
    "build", ".next", ".idea", ".vscode", "target", ".cache",
}
_MAX_FILE_BYTES = 4_000_000   # skip files bigger than this
_MAX_FILES = 20_000

_TEXT_EXTS = {
    ".txt", ".log", ".rst", ".md", ".markdown", ".html", ".htm", ".xml",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv", ".tab", ".psv",
}
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp", ".cc", ".h", ".hpp",
    ".java", ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".zsh",
    ".css", ".scss", ".sql", ".swift", ".kt",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif",
               ".tiff", ".svg", ".heic", ".heif"}


@dataclass
class Chunk:
    """One indexable unit."""
    path: str        # absolute file path
    kind: str        # text / code / pdf / notebook / image
    locator: str     # "line:42" / "page:7" / "cell:3" / ""
    text: str        # the chunk's text body (used for ranking + snippet)
    title: str       # short human label, e.g. "report.pdf page 7"

    def open_args(self) -> tuple[str, str]:
        """`(path, locator)` for the open-at-locator router."""
        return self.path, self.locator


# ----- walker ---------------------------------------------------------------

def walk_workspace_files(base: Path):
    """Yield indexable files under `base`. Skips noise dirs and big files."""
    base = Path(base)
    n = 0
    for path in base.rglob("*"):
        if n >= _MAX_FILES: return
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel.parts):
            continue
        if not path.is_file(): continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES: continue
        except OSError:
            continue
        ext = path.suffix.lower()
        if ext not in _TEXT_EXTS and ext not in _CODE_EXTS \
                and ext not in _IMAGE_EXTS and ext not in (".pdf", ".ipynb"):
            continue
        n += 1
        yield path


# ----- chunkers (pure functions per format) --------------------------------

def chunk_text(path: Path, *, lines_per_chunk: int = 40,
               overlap: int = 10) -> list[Chunk]:
    """Group consecutive lines into chunks with `overlap` lines of carry-over."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    if not lines: return []
    out: list[Chunk] = []
    ext = path.suffix.lower()
    kind = "code" if ext in _CODE_EXTS else "text"
    step = max(1, lines_per_chunk - overlap)
    pos = 0
    while pos < len(lines):
        end = min(len(lines), pos + lines_per_chunk)
        body = "\n".join(lines[pos:end])
        if body.strip():
            out.append(Chunk(
                path=str(path), kind=kind,
                locator=f"line:{pos + 1}",
                text=body,
                title=f"{path.name}:{pos + 1}-{end}",
            ))
        if end >= len(lines): break
        pos += step
    return out


def chunk_pdf(path: Path) -> list[Chunk]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return []
    out: list[Chunk] = []
    for i, page in enumerate(reader.pages, start=1):
        try: text = page.extract_text() or ""
        except Exception: text = ""
        text = text.strip()
        if not text: continue
        out.append(Chunk(
            path=str(path), kind="pdf",
            locator=f"page:{i}",
            text=text[:4000],
            title=f"{path.name} page {i}",
        ))
    return out


def chunk_notebook(path: Path) -> list[Chunk]:
    try:
        import nbformat
        nb = nbformat.read(str(path), as_version=4)
    except Exception:
        return []
    out: list[Chunk] = []
    for i, cell in enumerate(nb.get("cells") or []):
        src = cell.get("source") or ""
        if isinstance(src, list): src = "".join(src)
        src = (src or "").strip()
        if not src: continue
        ctype = cell.get("cell_type", "code")
        out.append(Chunk(
            path=str(path), kind="notebook",
            locator=f"cell:{i}",
            text=src[:4000],
            title=f"{path.name} cell {i + 1} ({ctype})",
        ))
    return out


def chunk_image(path: Path) -> list[Chunk]:
    """Index images by filename + nearest folder. Vision tools cover the
    actual content; this is just so the agent can find images by name."""
    return [Chunk(
        path=str(path), kind="image",
        locator="",
        text=f"{path.name} {path.parent.name}",
        title=path.name,
    )]


def chunk_file(path: Path) -> list[Chunk]:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf": return chunk_pdf(path)
        if ext == ".ipynb": return chunk_notebook(path)
        if ext in _IMAGE_EXTS: return chunk_image(path)
        if ext in _TEXT_EXTS or ext in _CODE_EXTS: return chunk_text(path)
    except Exception:
        return []
    return []


# ----- BM25 index ----------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


@dataclass
class BM25Index:
    """Classic BM25 over a list of token-lists. `add()` then `finalize()`,
    then `search()`. Score returned is unbounded; relative ordering is what
    matters."""
    k1: float = 1.5
    b: float = 0.75
    docs_tokens: list[list[str]] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)
    lengths: list[int] = field(default_factory=list)
    avg_length: float = 0.0
    finalized: bool = False

    def add(self, tokens: list[str]):
        self.finalized = False
        self.docs_tokens.append(tokens)
        self.lengths.append(len(tokens))
        for term in set(tokens):
            self.df[term] += 1

    def finalize(self):
        if self.lengths:
            self.avg_length = sum(self.lengths) / len(self.lengths)
        self.finalized = True

    def search(self, query_tokens: list[str], k: int = 10
               ) -> list[tuple[float, int]]:
        if not self.finalized: self.finalize()
        N = len(self.docs_tokens)
        if N == 0 or not query_tokens: return []
        avg = self.avg_length or 1.0
        # Pre-compute idf for each query term once.
        idfs = {}
        for q in set(query_tokens):
            df = self.df.get(q, 0)
            idfs[q] = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
        scored: list[tuple[float, int]] = []
        for i, tokens in enumerate(self.docs_tokens):
            if not tokens: continue
            tf = Counter(tokens)
            score = 0.0
            for q in query_tokens:
                ftd = tf.get(q, 0)
                if ftd == 0: continue
                norm = (ftd * (self.k1 + 1)) / (
                    ftd + self.k1 * (1 - self.b + self.b * self.lengths[i] / avg))
                score += idfs[q] * norm
            if score > 0: scored.append((score, i))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


# ----- WorkspaceIndex -----------------------------------------------------

class WorkspaceIndex:
    INDEX_VERSION = 1

    def __init__(self, root: Path, embedding_backend=None):
        self.root = Path(root).resolve()
        self.chunks: list[Chunk] = []
        self.bm25 = BM25Index()
        self.built_at: float = 0.0
        # Optional pluggable embedding backend (`EmbeddingBackend`). If set
        # and available, `search()` fuses BM25 + cosine similarity. Vectors
        # are computed lazily — only when search runs, only for the BM25
        # top-N, so a missing/slow backend never blocks indexing.
        self.embedding_backend = embedding_backend
        self._chunk_vectors: dict[int, list[float]] = {}

    def build(self, progress_cb=None) -> int:
        self.chunks = []
        self.bm25 = BM25Index()
        self._chunk_vectors.clear()
        for i, path in enumerate(walk_workspace_files(self.root)):
            for ch in chunk_file(path):
                self.chunks.append(ch)
                self.bm25.add(tokenize(ch.text))
            if progress_cb and i % 50 == 0:
                progress_cb(i, path)
        self.bm25.finalize()
        self.built_at = time.time()
        return len(self.chunks)

    def search(self, query: str, k: int = 10) -> list[tuple[float, Chunk]]:
        q = tokenize(query)
        if not q: return []
        bm = self.bm25.search(q, k=k * 4 if self.embedding_backend else k)
        if not bm: return []
        if not self._embeddings_usable():
            return [(s, self.chunks[i]) for s, i in bm[:k]]
        # Hybrid: re-rank top BM25 hits by cosine similarity against the query.
        from .embeddings import cosine_similarity, hybrid_score
        try:
            qvec = self.embedding_backend.embed_texts([query])[0]
            need = [i for s, i in bm if i not in self._chunk_vectors]
            if need:
                vecs = self.embedding_backend.embed_texts(
                    [self.chunks[i].text for i in need])
                for i, v in zip(need, vecs): self._chunk_vectors[i] = v
        except Exception:
            return [(s, self.chunks[i]) for s, i in bm[:k]]
        rescored: list[tuple[float, int]] = []
        for s, i in bm:
            sem = cosine_similarity(qvec, self._chunk_vectors.get(i) or [])
            rescored.append((hybrid_score(s, sem), i))
        rescored.sort(key=lambda x: -x[0])
        return [(s, self.chunks[i]) for s, i in rescored[:k]]

    def _embeddings_usable(self) -> bool:
        if self.embedding_backend is None: return False
        try:
            ok, _ = self.embedding_backend.is_available()
            return ok
        except Exception:
            return False

    def stats(self) -> dict:
        kinds = Counter(c.kind for c in self.chunks)
        return {
            "root": str(self.root),
            "n_chunks": len(self.chunks),
            "by_kind": dict(kinds),
            "built_at": int(self.built_at),
        }

    # -- persistence -------------------------------------------------------

    def save(self, path: Path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "v": self.INDEX_VERSION,
                "root": str(self.root),
                "chunks": self.chunks,
                "bm25": self.bm25,
                "built_at": self.built_at,
            }, f)

    @classmethod
    def load(cls, path: Path):
        try:
            with open(path, "rb") as f: data = pickle.load(f)
        except Exception:
            return None
        if data.get("v") != cls.INDEX_VERSION: return None
        idx = cls(Path(data["root"]))
        idx.chunks = data["chunks"]
        idx.bm25 = data["bm25"]
        idx.built_at = data["built_at"]
        return idx


def cache_path_for(root: Path) -> Path:
    """Stable cache location keyed on the project root path hash."""
    h = hashlib.sha1(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]
    return Path.home() / ".cache" / "TextView" / "workspace_index" / f"{h}.pkl"


def get_or_build_index(root: Path, force: bool = False) -> WorkspaceIndex:
    """Load from cache if recent (< 24h, no source file newer than cache),
    otherwise rebuild and persist."""
    cp = cache_path_for(root)
    if not force and cp.is_file():
        idx = WorkspaceIndex.load(cp)
        if idx is not None:
            cache_mtime = cp.stat().st_mtime
            stale = False
            for path in walk_workspace_files(root):
                try:
                    if path.stat().st_mtime > cache_mtime:
                        stale = True; break
                except OSError: continue
            if not stale: return idx
    idx = WorkspaceIndex(root)
    idx.build()
    try: idx.save(cp)
    except OSError: pass
    return idx
