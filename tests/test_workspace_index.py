"""Lexical workspace RAG: walker, chunkers, BM25, persistence."""
import json
from pathlib import Path

import pytest

from src.workspace_index import (
    BM25Index, Chunk, WorkspaceIndex, tokenize,
    walk_workspace_files, chunk_text, chunk_notebook, chunk_image,
    cache_path_for, get_or_build_index,
)


# -- tokenize ---------------------------------------------------------------

def test_tokenize_lowercases_and_keeps_underscores():
    assert tokenize("Hello WORLD foo_bar 42") == ["hello", "world", "foo_bar", "42"]


def test_tokenize_drops_single_chars():
    assert tokenize("a aa b cc") == ["aa", "cc"]


def test_tokenize_strips_punctuation():
    assert "the" in tokenize("'the quick' (brown) fox.")
    assert "fox" in tokenize("'the quick' (brown) fox.")


# -- walker -----------------------------------------------------------------

def test_walker_skips_dot_dirs(tmp_path):
    (tmp_path / ".git").mkdir(); (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "node_modules").mkdir(); (tmp_path / "node_modules" / "x.js").write_text("y")
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("def f(): pass")
    (tmp_path / "README.md").write_text("# hi")
    found = sorted(p.relative_to(tmp_path).as_posix() for p in walk_workspace_files(tmp_path))
    assert "src/a.py" in found
    assert "README.md" in found
    assert not any(".git" in p or "node_modules" in p for p in found)


def test_walker_skips_unknown_extensions(tmp_path):
    (tmp_path / "video.mp4").write_text("x")
    (tmp_path / "code.py").write_text("x")
    found = [p.suffix for p in walk_workspace_files(tmp_path)]
    assert ".py" in found
    assert ".mp4" not in found


def test_walker_skips_huge_files(tmp_path):
    (tmp_path / "big.log").write_bytes(b"x" * 5_000_000)
    (tmp_path / "small.log").write_bytes(b"x" * 100)
    found = [p.name for p in walk_workspace_files(tmp_path)]
    assert "small.log" in found
    assert "big.log" not in found


# -- chunk_text -------------------------------------------------------------

def test_chunk_text_groups_lines(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("\n".join([f"line {i}" for i in range(120)]), encoding="utf-8")
    chunks = chunk_text(p, lines_per_chunk=40, overlap=10)
    # 120 lines / step=30 → ⌈120/30⌉ = 4 chunks
    assert len(chunks) >= 3 and len(chunks) <= 5
    assert chunks[0].locator == "line:1"
    # Overlap means chunk 2 should start before chunk 1 ends.
    assert chunks[1].locator == "line:31"
    assert chunks[0].kind == "code"


def test_chunk_text_skips_empty_lines_only_chunks(tmp_path):
    p = tmp_path / "blank.txt"
    p.write_text("\n\n\n\n\n", encoding="utf-8")
    assert chunk_text(p) == []


def test_chunk_text_kind_is_text_for_md(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("# Heading\n\nbody text\n", encoding="utf-8")
    out = chunk_text(p)
    assert out[0].kind == "text"


# -- chunk_notebook ---------------------------------------------------------

def test_chunk_notebook_one_per_nonblank_cell(tmp_path):
    nb = tmp_path / "x.ipynb"
    nb.write_text(json.dumps({
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "# H"},
            {"cell_type": "code", "metadata": {},
             "source": ["import sys\n", "print(1)"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": "", "outputs": [], "execution_count": None},
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }), encoding="utf-8")
    out = chunk_notebook(nb)
    assert len(out) == 2  # blank cell skipped
    assert out[0].locator == "cell:0"
    assert "Heading" not in out[0].text  # markdown source has the actual text "# H"
    assert "# H" in out[0].text
    assert out[1].locator == "cell:1"
    assert "import sys" in out[1].text


def test_chunk_notebook_garbage_returns_empty(tmp_path):
    p = tmp_path / "bad.ipynb"
    p.write_text("not json", encoding="utf-8")
    assert chunk_notebook(p) == []


# -- chunk_image ------------------------------------------------------------

def test_chunk_image_one_filename_chunk(tmp_path):
    p = tmp_path / "diagrams" / "system.png"
    p.parent.mkdir(); p.write_bytes(b"")
    out = chunk_image(p)
    assert len(out) == 1
    assert "system" in out[0].text
    assert out[0].kind == "image"


# -- BM25 -------------------------------------------------------------------

def test_bm25_ranks_relevant_first():
    idx = BM25Index()
    idx.add(tokenize("the quick brown fox"))
    idx.add(tokenize("a slow turtle naps"))
    idx.add(tokenize("the fox jumps over the lazy dog"))
    idx.finalize()
    res = idx.search(tokenize("fox"), k=3)
    # Both 'fox' chunks should outrank the turtle one.
    fox_idxs = {i for _, i in res if 0 in (i,) or 2 in (i,)}
    assert 0 in {i for _, i in res}
    assert 2 in {i for _, i in res}


def test_bm25_idf_weights_rare_terms_higher():
    idx = BM25Index()
    for _ in range(5):
        idx.add(tokenize("common word here"))
    idx.add(tokenize("rare unique chunk"))
    idx.finalize()
    common_score = dict(idx.search(tokenize("common"), k=5))
    rare_score = dict(idx.search(tokenize("unique"), k=5))
    assert max(rare_score.values()) > max(common_score.values())


def test_bm25_empty_query_returns_empty():
    idx = BM25Index()
    idx.add(tokenize("anything")); idx.finalize()
    assert idx.search([], k=5) == []


def test_bm25_no_match_returns_empty():
    idx = BM25Index()
    idx.add(tokenize("foo bar baz")); idx.finalize()
    assert idx.search(tokenize("zzzz"), k=5) == []


# -- WorkspaceIndex end-to-end ---------------------------------------------

def test_workspace_index_finds_chunk_by_keyword(tmp_path):
    (tmp_path / "code.py").write_text(
        "def special_marker():\n    return 42\n", encoding="utf-8")
    (tmp_path / "other.py").write_text(
        "def utilfunc():\n    return 1\n", encoding="utf-8")
    idx = WorkspaceIndex(tmp_path)
    n = idx.build()
    assert n >= 2
    res = idx.search("special_marker")
    assert res
    score, chunk = res[0]
    assert "code.py" in chunk.path
    assert chunk.locator.startswith("line:")


def test_workspace_index_stats_count_kinds(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.md").write_text("# h")
    nb = tmp_path / "n.ipynb"
    nb.write_text(json.dumps({
        "cells": [{"cell_type": "code", "metadata": {}, "source": "y = 2",
                   "outputs": [], "execution_count": None}],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3",
                                    "language": "python"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }), encoding="utf-8")
    idx = WorkspaceIndex(tmp_path); idx.build()
    s = idx.stats()
    assert s["n_chunks"] >= 3
    kinds = s["by_kind"]
    assert "code" in kinds
    assert "text" in kinds
    assert "notebook" in kinds


def test_workspace_index_save_load_roundtrip(tmp_path):
    (tmp_path / "x.py").write_text("def f(): pass", encoding="utf-8")
    idx = WorkspaceIndex(tmp_path); idx.build()
    cp = tmp_path / "cache.pkl"
    idx.save(cp)
    assert cp.is_file()
    idx2 = WorkspaceIndex.load(cp)
    assert idx2 is not None
    assert idx2.stats()["n_chunks"] == idx.stats()["n_chunks"]
    res = idx2.search("def")
    assert res


def test_workspace_index_load_returns_none_on_corrupt(tmp_path):
    bad = tmp_path / "bad.pkl"; bad.write_bytes(b"not a pickle")
    assert WorkspaceIndex.load(bad) is None


def test_cache_path_is_deterministic(tmp_path):
    a = cache_path_for(tmp_path)
    b = cache_path_for(tmp_path)
    assert a == b
    other = cache_path_for(tmp_path.parent)
    assert other != a


def test_get_or_build_index_caches(tmp_path, monkeypatch):
    """Second call with the same root reuses the cache."""
    (tmp_path / "x.py").write_text("def f(): return 1\n")
    # Redirect cache dir so test doesn't pollute home.
    cache_dir = tmp_path / ".cache"
    monkeypatch.setattr("src.workspace_index.cache_path_for",
                        lambda root: cache_dir / "idx.pkl")
    idx1 = get_or_build_index(tmp_path)
    n1 = idx1.stats()["n_chunks"]
    assert n1 > 0
    idx2 = get_or_build_index(tmp_path)
    assert idx2.stats()["n_chunks"] == n1
    # Cache file exists.
    assert (cache_dir / "idx.pkl").is_file()
