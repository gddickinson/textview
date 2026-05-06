"""format_handlers registry: register / lookup / unregister / list."""
import pytest

import src.format_handlers as fh


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "_registry_path", lambda: tmp_path / "fh.json")
    yield tmp_path / "fh.json"


def test_register_writes_file(temp_registry):
    h = fh.register(".parquet", "show_parquet", description="head of df")
    assert h.extension == ".parquet"
    assert h.script == "show_parquet"
    assert temp_registry.is_file()


def test_lookup_returns_handler(temp_registry):
    fh.register(".pq", "show_pq", description="x")
    h = fh.lookup(".pq")
    assert h is not None
    assert h.script == "show_pq"


def test_lookup_normalizes_extension(temp_registry):
    fh.register(".PQ", "show_pq")
    assert fh.lookup("pq") is not None
    assert fh.lookup(".PQ") is not None


def test_register_overwrites_existing(temp_registry):
    fh.register(".pq", "v1")
    fh.register(".pq", "v2")
    assert fh.lookup(".pq").script == "v2"


def test_unregister_returns_true_when_present(temp_registry):
    fh.register(".pq", "x")
    assert fh.unregister(".pq") is True
    assert fh.lookup(".pq") is None


def test_unregister_returns_false_when_missing(temp_registry):
    assert fh.unregister(".never-existed") is False


def test_list_all_sorted(temp_registry):
    fh.register(".zzz", "z")
    fh.register(".aaa", "a")
    items = fh.list_all()
    assert [h.extension for h in items] == [".aaa", ".zzz"]


def test_corrupt_registry_returns_empty(temp_registry):
    temp_registry.parent.mkdir(exist_ok=True)
    temp_registry.write_text("not json", encoding="utf-8")
    assert fh.load() == {}
    assert fh.lookup(".x") is None
