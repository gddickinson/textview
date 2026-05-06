"""SnippetStore: name validation, JSON round-trip, fuzzy search, malformed-input safety."""
import json
import pytest

from src.snippets import Snippet, SnippetStore, is_valid_name


@pytest.mark.parametrize("name", ["fizz", "A_b-1", "x", "snake_case_name"])
def test_is_valid_name_accepts_well_formed(name):
    assert is_valid_name(name)


@pytest.mark.parametrize("name", ["1abc", "../etc/passwd", "", "a" * 65, "has space", "..", "name/with/slash"])
def test_is_valid_name_rejects_malformed(name):
    assert not is_valid_name(name)


def test_save_list_get_delete_roundtrip(tmp_path):
    s = SnippetStore(path=tmp_path / "snips.json")
    s.save(Snippet(name="hello", body='print("hi")', language="python", tags=["greet"]))
    s.save(Snippet(name="loop", body="for i in range(10): pass", language="python"))
    assert [x.name for x in s.list()] == ["hello", "loop"]
    assert s.get("hello").tags == ["greet"]
    assert s.delete("hello") is True
    assert s.delete("ghost") is False
    assert [x.name for x in s.list()] == ["loop"]


def test_reload_from_disk_preserves_entries(tmp_path):
    p = tmp_path / "snips.json"
    SnippetStore(path=p).save(Snippet(name="x", body="b", tags=["t"]))
    s2 = SnippetStore(path=p)
    assert [x.name for x in s2.list()] == ["x"]
    assert s2.get("x").tags == ["t"]


def test_save_rejects_bad_name(tmp_path):
    s = SnippetStore(path=tmp_path / "snips.json")
    with pytest.raises(ValueError):
        s.save(Snippet(name="../escape", body="x"))


def test_corrupt_json_falls_back_to_empty(tmp_path):
    bad = tmp_path / "bad.json"; bad.write_text("not json {[", encoding="utf-8")
    assert SnippetStore(path=bad).list() == []


def test_malformed_entries_filtered(tmp_path):
    p = tmp_path / "mal.json"
    p.write_text(json.dumps([
        {"name": "good", "body": "ok"},
        {"name": "../bad", "body": "filtered"},
        {"body": "missing name"},
        "not a dict",
        {"name": "good2", "body": "ok2"},
    ]), encoding="utf-8")
    assert [s.name for s in SnippetStore(path=p).list()] == ["good", "good2"]


def test_fuzzy_search_ranks_prefix_first(tmp_path):
    s = SnippetStore(path=tmp_path / "snips.json")
    s.save(Snippet(name="parse_csv", body="import csv", tags=["data"]))
    s.save(Snippet(name="parse_xml", body="from xml.etree", tags=["data"]))
    s.save(Snippet(name="hello", body="print"))
    ranked = s.search("parse")
    names = [snip.name for _, snip in ranked]
    assert names[:2] == ["parse_csv", "parse_xml"]
    assert "hello" not in names


def test_fuzzy_search_matches_via_tags(tmp_path):
    s = SnippetStore(path=tmp_path / "snips.json")
    s.save(Snippet(name="parse_csv", body="x", tags=["data"]))
    assert any(snip.name == "parse_csv" for _, snip in s.search("data"))
