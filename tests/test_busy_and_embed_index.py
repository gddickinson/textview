"""BusyIndicator + WorkspaceIndex embedding hook."""
import pytest
from pathlib import Path

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.busy_indicator import BusyIndicator
from src.workspace_index import WorkspaceIndex
from src.embeddings import NullBackend


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_busy_indicator_can_be_constructed(qapp):
    w = QMainWindow()
    with BusyIndicator(w, "Hello", delay_ms=10000):
        pass
    # No assertion — just survives clean construction + teardown.


def test_busy_indicator_clears_status_on_exit(qapp):
    w = QMainWindow()
    w.statusBar().showMessage("preset")
    bi = BusyIndicator(w, "Hello", delay_ms=1, interval_ms=1)
    bi.__enter__()
    bi._start_spinning()  # force activation
    assert "Hello" in w.statusBar().currentMessage()
    bi.__exit__()
    assert w.statusBar().currentMessage() == ""


def test_workspace_index_with_null_backend_falls_back_to_bm25(tmp_path):
    (tmp_path / "a.py").write_text("def alpha(): return 'banana'\n")
    (tmp_path / "b.py").write_text("def beta(): return 'cherry'\n")
    idx = WorkspaceIndex(tmp_path, embedding_backend=NullBackend())
    idx.build()
    results = idx.search("alpha", k=2)
    assert results
    assert "alpha" in results[0][1].text


class _FakeBackend:
    """Vectors are deterministic by token: 'alpha' → [1,0], 'beta' → [0,1]."""
    name = "fake"
    def is_available(self): return True, ""
    def embed_texts(self, texts):
        out = []
        for t in texts:
            t = t.lower()
            v = [1.0 if "alpha" in t else 0.0,
                 1.0 if "beta" in t else 0.0]
            out.append(v)
        return out


def test_workspace_index_with_embedding_backend_reranks(tmp_path):
    (tmp_path / "a.py").write_text("# alpha module\n" * 5)
    (tmp_path / "b.py").write_text("# beta module\n" * 5)
    idx = WorkspaceIndex(tmp_path, embedding_backend=_FakeBackend())
    idx.build()
    # Querying for "alpha" — both BM25 and embedding agree, alpha doc wins.
    results = idx.search("alpha", k=2)
    assert results
    assert "alpha" in results[0][1].text


def test_workspace_index_search_handles_empty_query(tmp_path):
    (tmp_path / "a.py").write_text("hello world\n")
    idx = WorkspaceIndex(tmp_path)
    idx.build()
    assert idx.search("") == []
    assert idx.search("   ") == []
