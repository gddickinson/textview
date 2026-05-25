"""Coverage for src.save_as — registry shape + every converter we can
run with the locally-installed deps.

Converters with `requires=()` (or whose deps are present) are exercised
round-trip; the rest are still asserted to be in the registry but only
run when their deps are importable.
"""
from __future__ import annotations

import importlib
import json
import pytest

from src import save_as as sa


def _have(modules):
    for m in modules:
        try: importlib.import_module(m)
        except Exception: return False
    return True


def test_registry_has_expected_pairs():
    ids = {c.id for c in sa.all_conversions()}
    must = {
        "md_to_html", "html_to_md",
        "json_to_yaml", "yaml_to_json",
        "json_to_toml", "toml_to_json",
        "csv_to_json", "csv_to_jsonl", "csv_to_md", "csv_to_html", "csv_to_xlsx",
        "json_to_csv", "rtf_to_txt",
    }
    missing = must - ids
    assert not missing, f"missing converters: {missing}"


def test_find_conversion_lookup():
    c = sa.find_conversion("markdown", ".html")
    assert c is not None and c.id == "md_to_html"
    assert sa.find_conversion("markdown", ".HTML").id == "md_to_html"  # case-insensitive
    assert sa.find_conversion("python", ".docx") is None


def test_available_filters_missing_deps(monkeypatch):
    # Pretend nothing is importable; converters with deps disappear.
    monkeypatch.setattr(sa, "_have", lambda _mods: False)
    avail = sa.available_conversions()
    for c in avail:
        assert c.requires == (), f"{c.id} should have been filtered out"


# ----------- Always-runnable converters (no optional deps) ---------------

def test_md_to_html_round_trip():
    out = sa._md_to_html("# Title\n\nbody", {})
    assert "<h1>Title</h1>" in out
    assert "body" in out


def test_html_to_md_fallback_strips_tags():
    # Without markdownify, fallback strips tags.
    out = sa._html_to_md("<p>hello <b>there</b></p>", {})
    assert "hello" in out and "there" in out
    assert "<" not in out and ">" not in out


def test_csv_to_json_records():
    out = sa._csv_to_json("a,b\n1,2\n3,4\n", {})
    data = json.loads(out)
    assert data == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_csv_to_jsonl_records():
    out = sa._csv_to_jsonl("a,b\n1,2\n3,4\n", {})
    lines = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert lines == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_csv_to_md_table():
    out = sa._csv_to_md("name,age\nAlice,30\nBob,25\n", {})
    assert "| name | age |" in out
    assert "| --- | --- |" in out
    assert "| Alice | 30 |" in out


def test_csv_to_html_escapes():
    out = sa._csv_to_html("a,b\n<x>,&\n", {})
    assert "&lt;x&gt;" in out and "&amp;" in out


def test_json_to_csv_array_of_objects():
    js = json.dumps([{"a": 1, "b": 2}, {"a": 3, "c": 4}])
    out = sa._json_to_csv(js, {})
    lines = out.strip().splitlines()
    assert lines[0] == "a,b,c"
    assert "1,2," in lines[1]
    assert "3,,4" in lines[2]


def test_json_to_csv_rejects_non_array():
    with pytest.raises(ValueError):
        sa._json_to_csv('{"a":1}', {})


def test_toml_to_json_stdlib():
    out = sa._toml_to_json('title = "Hi"\n\n[s]\nk = 1\n', {})
    data = json.loads(out)
    assert data == {"title": "Hi", "s": {"k": 1}}


def test_rtf_strip_basic():
    rtf = "{\\rtf1\\ansi line one\\par line two\\par}"
    out = sa._rtf_strip(rtf, {})
    assert "line one" in out and "line two" in out
    assert "\\par" not in out


# ----------- Optional-dep converters; skipped if deps missing -----------

@pytest.mark.skipif(not _have(["yaml"]), reason="pyyaml not installed")
def test_json_yaml_round_trip():
    src = '{"name": "x", "items": [1, 2, 3]}'
    yml = sa._json_to_yaml(src, {})
    assert "name: x" in yml
    back = json.loads(sa._yaml_to_json(yml, {}))
    assert back == {"name": "x", "items": [1, 2, 3]}


@pytest.mark.skipif(not _have(["tomli_w"]), reason="tomli_w not installed")
def test_json_to_toml():
    out = sa._json_to_toml('{"k": 1, "s": {"x": "y"}}', {})
    assert "k = 1" in out
    assert "[s]" in out


@pytest.mark.skipif(not _have(["openpyxl"]), reason="openpyxl not installed")
def test_csv_to_xlsx_bytes():
    out = sa._csv_to_xlsx("a,b\n1,2\n", {})
    assert isinstance(out, bytes)
    # XLSX is a ZIP — magic bytes start with 'PK'.
    assert out[:2] == b"PK"
