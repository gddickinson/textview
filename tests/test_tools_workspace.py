"""Workspace RAG LLM tools."""
import json
import pytest

from src.llm.tools_workspace import WORKSPACE_TOOLS


def _by_name(name):
    return next(t for t in WORKSPACE_TOOLS if t.name == name)


class _FakeWindow:
    """Just enough of MainWindow for the tools."""
    def __init__(self, root=None, current_path=None):
        self._current_path = current_path
        if root:
            class _PP:
                class _Model:
                    def __init__(self, r): self._r = str(r)
                    def rootPath(self): return self._r
                def __init__(self, r): self._model = self._Model(r)
            self.project_panel = _PP(root)
        self.citation_panel = _CitationStub()


class _CitationStub:
    def __init__(self): self.last = None
    def set_citations(self, chunks, query=""):
        self.last = (list(chunks), query)


def test_list_workspace_counts_by_extension(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    (tmp_path / "c.md").write_text("# h")
    out = _by_name("list_workspace").call(_FakeWindow(root=tmp_path))
    assert "2" in out  # two .py files
    assert ".py" in out
    assert ".md" in out


def test_list_workspace_no_root_errors():
    out = _by_name("list_workspace").call(_FakeWindow())
    assert "ERROR" in out


def test_index_workspace_returns_stats(tmp_path):
    (tmp_path / "a.py").write_text("def special_marker(): return 42")
    (tmp_path / "b.md").write_text("# heading\nbody")
    out = _by_name("index_workspace").call(_FakeWindow(root=tmp_path))
    assert "Indexed" in out
    assert "by kind" in out


def test_query_workspace_finds_keyword_and_pushes_to_panel(tmp_path):
    (tmp_path / "a.py").write_text(
        "def special_marker(): return 42\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "def utilfunc(): return 1\n", encoding="utf-8")
    w = _FakeWindow(root=tmp_path)
    out = _by_name("query_workspace").call(w, query="special_marker")
    assert "match(es)" in out
    assert "special_marker" in out
    assert "line:" in out
    # Citation panel got the results.
    pushed_chunks, query = w.citation_panel.last
    assert query == "special_marker"
    assert pushed_chunks
    assert pushed_chunks[0].path.endswith("a.py")


def test_query_workspace_no_query_errors(tmp_path):
    out = _by_name("query_workspace").call(
        _FakeWindow(root=tmp_path), query="")
    assert "ERROR" in out


def test_query_workspace_no_root_errors(tmp_path):
    out = _by_name("query_workspace").call(_FakeWindow(), query="anything")
    assert "ERROR" in out


def test_query_workspace_no_matches_message(tmp_path):
    (tmp_path / "a.py").write_text("def f(): return 1")
    out = _by_name("query_workspace").call(
        _FakeWindow(root=tmp_path), query="zzzzzznotamatch")
    assert "no matches" in out


def test_query_workspace_via_explicit_root_arg(tmp_path):
    (tmp_path / "x.md").write_text("rare_word_xyz here")
    # No project_panel, no current_path — but `root` arg supplied.
    out = _by_name("query_workspace").call(
        _FakeWindow(), query="rare_word_xyz", root=str(tmp_path))
    assert "match" in out
    assert "rare_word_xyz" in out


def test_workspace_tools_registered_in_read_only_set():
    from src.llm.tools import READ_ONLY_TOOLS
    names = {t.name for t in READ_ONLY_TOOLS}
    assert {"list_workspace", "index_workspace", "query_workspace"} <= names
