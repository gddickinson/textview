"""Pluggable embedding backend for the workspace index.

The default `BM25Index` (in `workspace_index.py`) is a lexical ranker.
This module provides a hybrid retrieval interface — semantic search via
embeddings + BM25 — that callers can opt into when an embedding backend
is configured.

Two backends ship:
    `null`    — disabled; only BM25 used.
    `openai`  — calls the user's OpenAI API key, model `text-embedding-3-small`
                by default (1536 dims, cheap, fast). Returned vectors are
                cached in-memory keyed on the chunk text hash.

The cache is process-local for v1; persistence comes later. Embeddings
are computed lazily — only when `embed_texts()` is called.
"""
from __future__ import annotations
import hashlib
import math
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """One row: a vector + the text hash it was computed for."""
    text_hash: str
    vector: list[float]


class EmbeddingBackend:
    """Base class. Subclass and implement `embed_texts(texts) -> list[list[float]]`."""

    name: str = "null"

    def is_available(self) -> tuple[bool, str]:
        return False, "no backend configured"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class NullBackend(EmbeddingBackend):
    name = "null"

    def is_available(self) -> tuple[bool, str]:
        return False, "embeddings disabled (set llm_provider's API key + flip `embeddings_enabled`)"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return []


class OpenAIBackend(EmbeddingBackend):
    name = "openai"

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._cache: dict[str, list[float]] = {}

    def is_available(self) -> tuple[bool, str]:
        try:
            import openai  # noqa: F401
        except ImportError:
            return False, "Install the `openai` Python package."
        from .llm.credentials import get_api_key
        if not get_api_key("openai"):
            return False, "No OpenAI API key configured."
        return True, ""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ok, why = self.is_available()
        if not ok: raise RuntimeError(why)
        import openai
        from .llm.credentials import get_api_key
        client = openai.OpenAI(api_key=get_api_key("openai"))
        # Cache by hash so re-embedding the same text is free.
        out: list[list[float]] = []
        to_fetch: list[tuple[int, str]] = []
        for i, t in enumerate(texts):
            h = _hash(t)
            if h in self._cache: out.append(self._cache[h])
            else: out.append([]); to_fetch.append((i, t))
        if to_fetch:
            resp = client.embeddings.create(
                model=self.model, input=[t for _, t in to_fetch])
            for (i, t), datum in zip(to_fetch, resp.data):
                vec = list(datum.embedding)
                self._cache[_hash(t)] = vec
                out[i] = vec
        return out


def get_backend(name: str = "null") -> EmbeddingBackend:
    """Return a configured backend by name. Falls back to NullBackend."""
    if name == "openai": return OpenAIBackend()
    return NullBackend()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def hybrid_score(bm25_score: float, sem_score: float, alpha: float = 0.6) -> float:
    """Combine BM25 + semantic similarity. `alpha` weights semantic.
    Both inputs should be roughly normalised; in practice BM25 ranges
    0–30+ and cosine 0–1, so we squash BM25 with `tanh` first."""
    bm = math.tanh(bm25_score / 5.0)
    return alpha * sem_score + (1 - alpha) * bm


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()
