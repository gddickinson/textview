"""workspace_search: pattern compile, file walk, search-in-file, glob filter."""
import re
from pathlib import Path

import pytest
from src.workspace_search import (
    compile_pattern, search_in_file, file_matches_glob, _walk_files,
)


def test_compile_pattern_literal_lowercases_when_case_off():
    assert compile_pattern("Hello", regex=False, case=False) == "hello"


def test_compile_pattern_literal_preserves_case_when_case_on():
    assert compile_pattern("Hello", regex=False, case=True) == "Hello"


def test_compile_pattern_regex_returns_pattern():
    p = compile_pattern(r"\d+", regex=True, case=True)
    assert isinstance(p, re.Pattern)
    assert p.pattern == r"\d+"


def test_compile_pattern_regex_bad_returns_none():
    assert compile_pattern(r"foo[", regex=True, case=True) is None


def test_compile_pattern_regex_case_flag_off_uses_ignorecase():
    p = compile_pattern("hello", regex=True, case=False)
    assert p.flags & re.IGNORECASE


def test_search_in_file_literal(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("def foo():\n    return 1\n# foo bar\n", encoding="utf-8")
    hits = search_in_file(f, "foo", case_sensitive=False, max_hits=10)
    lines = [n for n, _ in hits]
    assert lines == [1, 3]


def test_search_in_file_case_sensitive(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("Foo\nfoo\n", encoding="utf-8")
    hits = search_in_file(f, "foo", case_sensitive=True, max_hits=10)
    assert [n for n, _ in hits] == [2]


def test_search_in_file_regex(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("error 42\nwarn 100\nerror 5\n", encoding="utf-8")
    pat = re.compile(r"\d+")
    hits = search_in_file(f, pat, case_sensitive=True, max_hits=10)
    assert [n for n, _ in hits] == [1, 2, 3]


def test_search_in_file_max_hits_caps_results(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("\n".join("hit"  for _ in range(50)), encoding="utf-8")
    hits = search_in_file(f, "hit", case_sensitive=True, max_hits=10)
    assert len(hits) == 10


def test_file_matches_glob_empty_matches_all(tmp_path):
    f = tmp_path / "src" / "a.py"; f.parent.mkdir(); f.write_text("")
    assert file_matches_glob(f, tmp_path, "")


def test_file_matches_glob_extension(tmp_path):
    f = tmp_path / "a.py"; f.write_text("")
    g = tmp_path / "a.txt"; g.write_text("")
    assert file_matches_glob(f, tmp_path, "*.py")
    assert not file_matches_glob(g, tmp_path, "*.py")


def test_file_matches_glob_comma_list(tmp_path):
    f = tmp_path / "a.py"; f.write_text("")
    g = tmp_path / "b.md"; g.write_text("")
    h = tmp_path / "c.txt"; h.write_text("")
    assert file_matches_glob(f, tmp_path, "*.py, *.md")
    assert file_matches_glob(g, tmp_path, "*.py, *.md")
    assert not file_matches_glob(h, tmp_path, "*.py, *.md")


def test_walk_files_skips_dot_dirs(tmp_path):
    (tmp_path / ".git").mkdir(); (tmp_path / ".git" / "config").write_text("")
    (tmp_path / "node_modules").mkdir(); (tmp_path / "node_modules" / "x.js").write_text("")
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("")
    (tmp_path / "README.md").write_text("")
    found = sorted(p.relative_to(tmp_path).as_posix() for p in _walk_files(tmp_path))
    assert "src/a.py" in found and "README.md" in found
    assert not any(".git" in p or "node_modules" in p for p in found)


def test_walk_files_skips_huge_files(tmp_path):
    big = tmp_path / "huge.log"
    big.write_bytes(b"x" * 3_000_000)
    small = tmp_path / "small.log"
    small.write_bytes(b"x" * 100)
    found = [p.name for p in _walk_files(tmp_path)]
    assert "small.log" in found
    assert "huge.log" not in found
