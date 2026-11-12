"""Workspace-RAG demo: the desktop app's lexical index (`workspace_index`) over this repo's docs/ and sample files.

The chunkers (`chunk_file`), tokenizer and `BM25Index` are TextView's own; only the file list is fixed here so the
demo corpus is small and public. No embeddings and no LLM: the agent's `query_workspace` tool returns exactly these
ranked chunks as citations, and the chat answer built on top needs the desktop app with an API key.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..workspace_index import BM25Index, chunk_file, tokenize, walk_workspace_files

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIRS = ["docs", "sample_files"]
SNIPPET = 240


@lru_cache(maxsize=1)
def demo_index():
    chunks = []
    bm = BM25Index()
    for d in CORPUS_DIRS:
        for path in sorted(walk_workspace_files(ROOT / d)):
            if "img" in path.relative_to(ROOT).parts:  # docs/img: web-interface screenshots, not repo docs
                continue
            for ch in chunk_file(path):
                chunks.append(ch)
                bm.add(tokenize(ch.text))
    bm.finalize()
    return chunks, bm


def _rel(p: str) -> str:
    return str(Path(p).resolve().relative_to(ROOT))


def corpus_payload() -> dict:
    """Every chunk (for the in-browser BM25 port on the static site) plus index stats."""
    chunks, bm = demo_index()
    kinds: dict[str, int] = {}
    for c in chunks:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    return {"dirs": CORPUS_DIRS, "k1": bm.k1, "b": bm.b, "n_chunks": len(chunks), "by_kind": kinds,
            "n_files": len({c.path for c in chunks}),
            "chunks": [{"path": _rel(c.path), "kind": c.kind, "locator": c.locator, "title": c.title, "text": c.text}
                       for c in chunks]}


def search(query: str, k: int = 8) -> dict:
    chunks, bm = demo_index()
    hits = bm.search(tokenize(query), k=k)
    return {"query": query, "tokens": tokenize(query),
            "hits": [{"score": s, "index": i, "path": _rel(chunks[i].path), "kind": chunks[i].kind,
                      "locator": chunks[i].locator, "title": chunks[i].title,
                      "snippet": chunks[i].text[:SNIPPET]} for s, i in hits]}
