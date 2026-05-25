"""Coverage for src/llm/tools_data_formats.py.

Smoke-tests each tool end-to-end against a fixture file built with
the matching writer library. Tests skip when the optional reader dep
is missing — matches the loader-side skip behaviour."""
from __future__ import annotations

import importlib
import json
import sqlite3
import zipfile
import pytest
from pathlib import Path
from types import SimpleNamespace

from src.llm.tools_data_formats import (
    DATA_FORMAT_TOOLS,
    _read_spreadsheet, _read_sqlite, _query_sqlite, _read_archive,
    _read_array_file, _read_parquet, _read_hdf5, _read_cert,
)


def _have(mod):
    try: importlib.import_module(mod); return True
    except Exception: return False


@pytest.fixture
def fake_window(tmp_path):
    """Minimal window stand-in for tools that touch only `_resolve()`."""
    return SimpleNamespace(_current_path=None, project_panel=None)


# --------------------------------------------------------- registry --

def test_registry_shape_and_uniqueness():
    names = [t.name for t in DATA_FORMAT_TOOLS]
    assert sorted(names) == sorted(set(names)), f"duplicates: {names}"
    expected = {
        "read_spreadsheet", "read_sqlite", "query_sqlite",
        "read_archive", "read_array_file", "read_parquet",
        "read_hdf5", "read_cert",
    }
    assert expected == set(names)
    for tool in DATA_FORMAT_TOOLS:
        # Every tool has a valid JSON-schema-ish input definition.
        assert tool.input_schema.get("type") == "object"
        assert "path" in tool.input_schema.get("properties", {})


def test_tools_are_in_read_only_registry():
    """The new tools must be reachable from `find_tool` and listed in
    READ_ONLY_TOOLS so a default chat session can call them."""
    from src.llm.tools import READ_ONLY_TOOLS, find_tool
    names_ro = {t.name for t in READ_ONLY_TOOLS}
    for t in DATA_FORMAT_TOOLS:
        assert t.name in names_ro, f"{t.name} missing from READ_ONLY_TOOLS"
        assert find_tool(t.name) is not None


# --------------------------------------------------------- spreadsheets --

@pytest.mark.skipif(not _have("openpyxl"), reason="openpyxl not installed")
def test_read_spreadsheet(fake_window, tmp_path):
    import openpyxl
    p = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "S1"
    ws.append(["a", "b"]); ws.append([1, 2]); ws.append([3, 4])
    wb.create_sheet("S2")
    wb.save(p)
    out = _read_spreadsheet(fake_window, str(p))
    assert "sheets:" in out and "S1" in out and "S2" in out
    assert "a,b" in out and "1,2" in out


@pytest.mark.skipif(not _have("openpyxl"), reason="openpyxl not installed")
def test_read_spreadsheet_pick_sheet(fake_window, tmp_path):
    import openpyxl
    p = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "First"
    ws.append(["x"])
    ws2 = wb.create_sheet("Second")
    ws2.append(["y", "z"]); ws2.append([10, 20])
    wb.save(p)
    out = _read_spreadsheet(fake_window, str(p), sheet="Second")
    assert "showing: Second" in out
    assert "y,z" in out and "10,20" in out


@pytest.mark.skipif(not _have("openpyxl"), reason="openpyxl not installed")
def test_read_spreadsheet_unknown_sheet(fake_window, tmp_path):
    import openpyxl
    p = tmp_path / "x.xlsx"
    openpyxl.Workbook().save(p)
    out = _read_spreadsheet(fake_window, str(p), sheet="nope")
    assert out.startswith("ERROR")


# --------------------------------------------------------- sqlite --

def test_read_sqlite_lists_tables(fake_window, tmp_path):
    p = tmp_path / "x.sqlite"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
        INSERT INTO people VALUES (1, 'Alice', 30), (2, 'Bob', 25);
        CREATE TABLE notes (id INTEGER, body TEXT);
    """)
    conn.commit(); conn.close()
    out = _read_sqlite(fake_window, str(p))
    assert "2 table" in out or "2 tables" in out  # tolerant to s/es
    assert "people" in out and "notes" in out
    # Column type appears.
    assert "INTEGER" in out and "TEXT" in out


def test_query_sqlite_runs_select(fake_window, tmp_path):
    p = tmp_path / "x.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(1, "x"), (2, "y")])
    conn.commit(); conn.close()
    out = _query_sqlite(fake_window, str(p), "SELECT * FROM t ORDER BY a")
    assert "a,b" in out
    assert "1,x" in out and "2,y" in out


def test_query_sqlite_blocks_writes(fake_window, tmp_path):
    p = tmp_path / "x.sqlite"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit(); conn.close()
    out = _query_sqlite(fake_window, str(p), "DELETE FROM t")
    assert out.startswith("ERROR")


def test_read_sqlite_missing_file(fake_window):
    out = _read_sqlite(fake_window, "/no/such/file.sqlite")
    assert out.startswith("ERROR")


# --------------------------------------------------------- archives --

def test_read_archive_lists_members(fake_window, tmp_path):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("a.txt", "alpha")
        zf.writestr("dir/b.txt", "beta")
    out = _read_archive(fake_window, str(p))
    assert "a.txt" in out and "dir/b.txt" in out
    # Summary line includes file count.
    assert "2 files" in out


def test_read_archive_missing_file(fake_window):
    out = _read_archive(fake_window, "/no/such.zip")
    assert out.startswith("ERROR")


# --------------------------------------------------------- numpy --

@pytest.mark.skipif(not _have("numpy"), reason="numpy not installed")
def test_read_array_file_npy(fake_window, tmp_path):
    import numpy as np
    p = tmp_path / "v.npy"
    np.save(p, np.array([10, 20, 30]))
    out = _read_array_file(fake_window, str(p))
    assert "format: numpy" in out
    assert "shape=(3,)" in out
    assert "value" in out and "10" in out


@pytest.mark.skipif(not _have("numpy"), reason="numpy not installed")
def test_read_array_file_npz_pick(fake_window, tmp_path):
    import numpy as np
    p = tmp_path / "v.npz"
    np.savez(p, alpha=np.array([1, 2, 3]), beta=np.array([10, 20]))
    out = _read_array_file(fake_window, str(p), name="beta")
    assert "showing: beta" in out
    assert "10" in out and "20" in out


@pytest.mark.skipif(not _have("scipy"), reason="scipy not installed")
def test_read_array_file_mat(fake_window, tmp_path):
    import numpy as np
    from scipy.io import savemat
    p = tmp_path / "v.mat"
    savemat(p, {"v": np.array([100, 200])})
    out = _read_array_file(fake_window, str(p))
    assert "format: matlab" in out
    assert "v" in out
    assert "100" in out


def test_read_array_file_unsupported_extension(fake_window, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2")
    out = _read_array_file(fake_window, str(p))
    assert out.startswith("ERROR")


# --------------------------------------------------------- parquet --

@pytest.mark.skipif(not _have("pyarrow"), reason="pyarrow not installed")
def test_read_parquet(fake_window, tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    p = tmp_path / "d.parquet"
    pq.write_table(pa.table({"a": [1, 2], "b": ["x", "y"]}), p)
    out = _read_parquet(fake_window, str(p))
    assert "rows: 2" in out
    assert "a:" in out and "b:" in out
    assert "1,x" in out and "2,y" in out


# --------------------------------------------------------- hdf5 --

@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_read_hdf5_default_dataset(fake_window, tmp_path):
    import h5py, numpy as np
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("flat", data=np.array([1.0, 2.0, 3.0]))
        g = hf.create_group("g")
        g.create_dataset("nested", data=np.array([[1, 2], [3, 4]]))
    out = _read_hdf5(fake_window, str(p))
    assert "/flat" in out and "/g/nested" in out
    # Default is first → `/flat`
    assert "showing: /flat" in out


@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_read_hdf5_pick_dataset(fake_window, tmp_path):
    import h5py, numpy as np
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("a", data=np.array([1, 2]))
        hf.create_dataset("b", data=np.array([10, 20]))
    out = _read_hdf5(fake_window, str(p), dataset="/b")
    assert "showing: /b" in out
    assert "10" in out and "20" in out


@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_read_hdf5_unknown_dataset(fake_window, tmp_path):
    import h5py, numpy as np
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("a", data=np.array([1]))
    out = _read_hdf5(fake_window, str(p), dataset="/missing")
    assert out.startswith("ERROR")


# --------------------------------------------------------- certs --

def test_read_cert_safe_for_keys(fake_window, tmp_path):
    """Key material must NEVER appear in the tool output."""
    body = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBSECRET_KEY_BYTES_HERE\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    p = tmp_path / "id.key"
    p.write_text(body)
    out = _read_cert(fake_window, str(p))
    assert "SECRET_KEY_BYTES_HERE" not in out
    assert "MIIEowIBSE" not in out
    # The "private-key never displayed" disclaimer is in the report.
    assert "Private-key material" in out
