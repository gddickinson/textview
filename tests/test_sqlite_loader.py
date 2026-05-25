"""Coverage for `src.sqlite_loader` — table listing, CSV extraction,
ad-hoc query runner, write-blocking, magic-byte sniff."""
from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from src.sqlite_loader import (
    SQLITE_EXTENSIONS, is_supported, looks_like_sqlite,
    list_tables, load_table_as_csv, run_query_as_csv, table_row_count,
    SQLiteReadError,
)


@pytest.fixture
def sample_db(tmp_path):
    p = tmp_path / "sample.sqlite"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
        INSERT INTO people VALUES (1, 'Alice', 30), (2, 'Bob', 25), (3, 'Carol', 42);
        CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT);
        INSERT INTO notes VALUES (1, 'hi'), (2, 'there');
        CREATE VIEW adults AS SELECT * FROM people WHERE age >= 30;
    """)
    conn.commit(); conn.close()
    return p


# -- extension / sniff -----------------------------------------------------

def test_is_supported_extensions():
    for ext in (".sqlite", ".sqlite3", ".db"):
        assert is_supported(f"x{ext}")
    assert not is_supported("x.json")
    assert ".sqlite" in SQLITE_EXTENSIONS


def test_looks_like_sqlite_true(sample_db):
    assert looks_like_sqlite(sample_db)


def test_looks_like_sqlite_false_on_text(tmp_path):
    p = tmp_path / "not.db"
    p.write_text("just text\n")
    assert not looks_like_sqlite(p)


def test_looks_like_sqlite_false_on_missing(tmp_path):
    assert not looks_like_sqlite(tmp_path / "no_such_file.db")


# -- listing ---------------------------------------------------------------

def test_list_tables_alphabetical(sample_db):
    names = list_tables(str(sample_db))
    # Alphabetical, NOCASE collation. Includes views.
    assert names == ["adults", "notes", "people"]


def test_list_tables_skips_sqlite_internal(tmp_path):
    """The `sqlite_sequence` table that SQLite creates for AUTOINCREMENT
    tables should NOT appear."""
    p = tmp_path / "with_seq.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    conn.execute("INSERT INTO t VALUES (NULL)")
    conn.commit(); conn.close()
    names = list_tables(str(p))
    assert "t" in names
    assert "sqlite_sequence" not in names


# -- table extraction -----------------------------------------------------

def test_load_table_as_csv(sample_db):
    out = load_table_as_csv(str(sample_db), "people")
    lines = [l for l in out.strip().splitlines() if l.strip()]
    assert lines[0] == "id,name,age"
    assert "Alice,30" in lines[1]
    assert "Bob,25" in lines[2]


def test_table_row_count(sample_db):
    assert table_row_count(str(sample_db), "people") == 3
    assert table_row_count(str(sample_db), "notes") == 2


def test_load_table_rejects_unsafe_identifier(sample_db):
    with pytest.raises(SQLiteReadError):
        load_table_as_csv(str(sample_db), "people; DROP TABLE notes")
    with pytest.raises(SQLiteReadError):
        load_table_as_csv(str(sample_db), "")
    with pytest.raises(SQLiteReadError):
        load_table_as_csv(str(sample_db), '"; DELETE FROM people; --')


def test_load_table_row_cap_truncates(tmp_path):
    p = tmp_path / "big.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE big (i INTEGER)")
    conn.executemany("INSERT INTO big VALUES (?)", [(i,) for i in range(50)])
    conn.commit(); conn.close()
    out = load_table_as_csv(str(p), "big", row_cap=10)
    assert "# (truncated" in out


# -- query runner ---------------------------------------------------------

def test_run_query_returns_csv(sample_db):
    out = run_query_as_csv(str(sample_db),
                            "SELECT name FROM people WHERE age > 27 ORDER BY age")
    lines = out.strip().splitlines()
    assert lines[0] == "name"
    assert "Alice" in lines and "Carol" in lines
    # Bob is 25, should not be in results
    assert "Bob" not in lines


def test_run_query_blocks_writes(sample_db):
    """Read-only mode means any DML/DDL should raise."""
    with pytest.raises(SQLiteReadError):
        run_query_as_csv(str(sample_db), "DELETE FROM people")
    with pytest.raises(SQLiteReadError):
        run_query_as_csv(str(sample_db), "CREATE TABLE evil (x)")
    # And the original data is intact afterwards.
    assert table_row_count(str(sample_db), "people") == 3


def test_run_query_raises_on_bad_sql(sample_db):
    with pytest.raises(SQLiteReadError):
        run_query_as_csv(str(sample_db), "SELEC bad_syntax FROM nope")


def test_run_query_empty_sql(sample_db):
    with pytest.raises(SQLiteReadError):
        run_query_as_csv(str(sample_db), "   ")


# -- integration: file_loader routes through ------------------------------

def test_file_loader_routes_sqlite(sample_db):
    from src.file_loader import detect_format, load_file
    assert detect_format(str(sample_db)) == "sqlite"
    content, encoding, fmt = load_file(str(sample_db))
    assert fmt == "sqlite"
    assert "table=" in encoding
    # First table alphabetically is "adults" (a view), which exists.
    assert content  # not empty


def test_file_loader_falls_back_for_non_sqlite_db(tmp_path):
    """A `.db` file that isn't actually SQLite should fall back to plain
    text reading rather than crashing in the SQLite parser."""
    p = tmp_path / "fake.db"
    p.write_text("this isn't a real database\nline two\n")
    from src.file_loader import load_file
    content, encoding, fmt = load_file(str(p))
    assert fmt == "plain"
    assert "fake" in content or "this isn't" in content
