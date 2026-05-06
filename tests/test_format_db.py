"""File-format database: load, lookup, search, agent tools, dialog."""
import json
import pytest
from pathlib import Path
from src import format_db as fdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point the user-extension file at a tmp dir + reload."""
    monkeypatch.setattr(fdb, "_USER", tmp_path / "file_formats.json")
    fdb.reload_db()
    yield fdb.db()
    fdb.reload_db()


# -- bundled DB loaded ------------------------------------------------------

def test_bundled_db_has_entries(fresh_db):
    assert len(fresh_db.entries) >= 30
    assert "parquet" in fresh_db.by_id
    assert "pdf" in fresh_db.by_id
    assert "ipynb" in fresh_db.by_id


def test_lookup_by_extension(fresh_db):
    e = fresh_db.lookup_by_extension(".parquet")
    assert e is not None
    assert e.id == "parquet"
    assert "PAR1" in e.magic_bytes
    # Case-insensitive.
    assert fresh_db.lookup_by_extension(".PARQUET").id == "parquet"


def test_lookup_by_extension_with_no_dot(fresh_db):
    """Common typo: passing 'parquet' (no leading dot) should still work."""
    e = fresh_db.lookup_by_extension("parquet")
    assert e is not None
    assert e.id == "parquet"


def test_lookup_by_filename(fresh_db):
    assert fresh_db.lookup_by_filename("Dockerfile").id == "dockerfile"
    assert fresh_db.lookup_by_filename("dockerfile").id == "dockerfile"
    assert fresh_db.lookup_by_filename("Makefile").id == "makefile"


def test_lookup_by_id(fresh_db):
    assert fresh_db.lookup_by_id("parquet") is not None
    assert fresh_db.lookup_by_id("nonexistent") is None


def test_search_finds_by_keyword(fresh_db):
    hits = fresh_db.search("columnar")
    assert any(e.id == "parquet" for e in hits)


def test_search_finds_by_extension(fresh_db):
    hits = fresh_db.search(".pdf")
    assert hits[0].id == "pdf"


def test_search_returns_empty_for_nonsense(fresh_db):
    assert fresh_db.search("zzzzzthisdoesnotexist") == []


def test_categories_overview(fresh_db):
    cats = fresh_db.categories()
    assert "data" in cats
    assert cats["data"] >= 5


# -- markdown rendering ----------------------------------------------------

def test_to_markdown_includes_essentials(fresh_db):
    md = fresh_db.lookup_by_id("parquet").to_markdown()
    assert "Apache Parquet" in md
    assert "PAR1" in md
    assert "## Description" in md
    assert "## How to open" in md or "## Common uses" in md


# -- user-extension file ---------------------------------------------------

def test_user_entry_extends_bundled(tmp_path, monkeypatch):
    """User entries should appear after reload."""
    user_file = tmp_path / "file_formats.json"
    user_file.write_text(json.dumps({
        "schema_version": 1,
        "formats": [{
            "id": "myformat",
            "name": "My custom format",
            "extensions": [".myf"],
            "category": "data",
            "description": "A user-added entry",
        }],
    }))
    monkeypatch.setattr(fdb, "_USER", user_file)
    fdb.reload_db()
    assert fdb.db().lookup_by_id("myformat") is not None
    assert fdb.db().lookup_by_extension(".myf").name == "My custom format"


def test_user_entry_overrides_bundled(tmp_path, monkeypatch):
    """If user defines an entry with a bundled id, the user's wins."""
    user_file = tmp_path / "file_formats.json"
    user_file.write_text(json.dumps({
        "formats": [{"id": "parquet", "name": "OVERRIDDEN"}],
    }))
    monkeypatch.setattr(fdb, "_USER", user_file)
    fdb.reload_db()
    assert fdb.db().lookup_by_id("parquet").name == "OVERRIDDEN"


def test_add_user_entry_persists(tmp_path, monkeypatch):
    user_file = tmp_path / "file_formats.json"
    monkeypatch.setattr(fdb, "_USER", user_file)
    fdb.reload_db()
    ok, msg = fdb.add_user_entry({
        "id": "new_kid", "name": "Brand new", "extensions": [".nk"],
        "description": "A test entry."
    })
    assert ok, msg
    assert user_file.is_file()
    assert "new_kid" in fdb.db().by_id


def test_add_user_entry_rejects_no_id(tmp_path, monkeypatch):
    monkeypatch.setattr(fdb, "_USER", tmp_path / "fmt.json")
    ok, _ = fdb.add_user_entry({"name": "no id"})
    assert ok is False


# -- agent tools -----------------------------------------------------------

def test_lookup_format_tool_returns_json(fresh_db):
    from src.llm.tools_format_db import _lookup_format
    out = _lookup_format(None, name_or_extension=".parquet")
    data = json.loads(out)
    assert data["id"] == "parquet"
    assert "Parquet" in data["name"]


def test_lookup_format_tool_handles_bare_extension(fresh_db):
    from src.llm.tools_format_db import _lookup_format
    out = _lookup_format(None, name_or_extension="parquet")
    data = json.loads(out)
    assert data["id"] == "parquet"


def test_lookup_format_tool_returns_no_match_message(fresh_db):
    from src.llm.tools_format_db import _lookup_format
    out = _lookup_format(None, name_or_extension="zzz_no_match")
    assert "no entry" in out


def test_search_formats_tool_lists_results(fresh_db):
    from src.llm.tools_format_db import _search_formats
    out = _search_formats(None, query="lossless")
    assert "flac" in out.lower() or "png" in out.lower()


def test_list_categories_tool(fresh_db):
    from src.llm.tools_format_db import _list_format_categories
    out = _list_format_categories(None)
    assert "categories" in out
    assert "data" in out


def test_add_entry_tool_writes_user_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fdb, "_USER", tmp_path / "fmt.json")
    fdb.reload_db()
    from src.llm.tools_format_db import _add_format_entry
    out = _add_format_entry(None, entry={"id": "agent_added",
                                         "name": "Added by agent"})
    assert "saved" in out


def test_add_entry_tool_rejects_missing_id():
    from src.llm.tools_format_db import _add_format_entry
    assert "ERROR" in _add_format_entry(None, entry={"name": "no id"})
    assert "ERROR" in _add_format_entry(None, entry="not a dict")


# -- registration -----------------------------------------------------------

def test_format_db_tools_registered():
    from src.llm.tools import READ_ONLY_TOOLS, ACTION_TOOLS
    ro = {t.name for t in READ_ONLY_TOOLS}
    act = {t.name for t in ACTION_TOOLS}
    assert {"lookup_format", "search_formats",
            "list_format_categories"} <= ro
    assert {"add_format_entry"} <= act


# -- inspector integration ------------------------------------------------

def test_inspector_report_includes_db_section(tmp_path):
    from src.file_inspector import maybe_unknown_file_report
    p = tmp_path / "x.parquet"
    p.write_bytes(b"PAR1" + b"\x00" * 100 + b"PAR1")
    rep = maybe_unknown_file_report(p)
    assert rep is not None
    md, kind = rep
    assert kind == "parquet"
    assert "From the file-format database" in md
    assert "Apache Parquet" in md
