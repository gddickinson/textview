"""OCR + embedding scaffolding."""
import pytest
from src.ocr import is_available as ocr_available, ocr_image, ocr_pdf
from src.embeddings import (
    NullBackend, OpenAIBackend, get_backend, cosine_similarity,
    hybrid_score, _hash,
)


# -- OCR --------------------------------------------------------------------

def test_ocr_available_returns_tuple():
    ok, why = ocr_available()
    assert isinstance(ok, bool)
    assert isinstance(why, str)


def test_ocr_image_when_unavailable_returns_falsy(tmp_path, monkeypatch):
    # Force is_available to report False.
    import src.ocr as o
    monkeypatch.setattr(o, "is_available", lambda: (False, "test-only"))
    p = tmp_path / "x.png"; p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
    ok, msg = ocr_image(p)
    assert ok is False
    assert msg == "test-only"


def test_ocr_pdf_when_unavailable_returns_falsy(tmp_path, monkeypatch):
    import src.ocr as o
    monkeypatch.setattr(o, "is_available", lambda: (False, "test-only"))
    p = tmp_path / "x.pdf"; p.write_bytes(b"%PDF-1.7\n")
    ok, pages = ocr_pdf(p)
    assert ok is False
    assert pages == ["test-only"]


# -- embeddings -------------------------------------------------------------

def test_null_backend_unavailable_by_default():
    b = NullBackend()
    ok, _ = b.is_available()
    assert ok is False
    assert b.embed_texts(["hello"]) == []


def test_openai_backend_unavailable_when_no_key(monkeypatch):
    monkeypatch.setattr("src.llm.credentials.get_api_key",
                        lambda provider: "")
    b = OpenAIBackend()
    ok, why = b.is_available()
    assert ok is False
    assert "OpenAI" in why


def test_get_backend_default_is_null():
    b = get_backend()
    assert isinstance(b, NullBackend)


def test_get_backend_openai():
    b = get_backend("openai")
    assert isinstance(b, OpenAIBackend)


def test_cosine_similarity_identical():
    a = [1, 0, 0]; b = [1, 0, 0]
    assert cosine_similarity(a, b) == 1.0


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0


def test_cosine_similarity_handles_empty():
    assert cosine_similarity([], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], []) == 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0


def test_hybrid_score_blends_bm25_and_semantic():
    # All-semantic.
    s = hybrid_score(bm25_score=10.0, sem_score=1.0, alpha=1.0)
    assert s == 1.0
    # All-BM25 (alpha=0): score == tanh(10/5) ≈ 0.964.
    s = hybrid_score(bm25_score=10.0, sem_score=0.5, alpha=0.0)
    assert 0.9 < s < 1.0


def test_hash_deterministic():
    assert _hash("hello") == _hash("hello")
    assert _hash("a") != _hash("b")
