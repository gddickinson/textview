"""Read SQLite databases (`.sqlite`, `.sqlite3`, `.db`) as tables.

Mirrors `spreadsheet_loader`'s shape: a SQLite database is "a workbook
with tables instead of sheets." `list_tables(path)` returns table +
view names; `load_table_as_csv(path, table)` extracts one to CSV-shaped
text so the existing `TableView` does the rest. `run_query_as_csv` lets
the user fire ad-hoc `SELECT` statements.

Connections are opened **read-only** via URI mode so this never
mutates the user's database. Result sets are capped at 100k rows by
default to keep the table view responsive on large databases.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path


SQLITE_EXTENSIONS = {".sqlite", ".sqlite3", ".db"}
_SQLITE_MAGIC = b"SQLite format 3\x00"
_DEFAULT_ROW_CAP = 100_000


class SQLiteReadError(Exception):
    """Raised when a SQLite database can't be opened or queried."""


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in SQLITE_EXTENSIONS


def looks_like_sqlite(path) -> bool:
    """Cheap magic-byte sniff. Useful for ambiguous extensions like
    `.db` which can also be Berkeley DB, LevelDB, etc."""
    try:
        with open(path, "rb") as f:
            return f.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def _open_readonly(path: str) -> sqlite3.Connection:
    """Open with `mode=ro` so we never mutate the user's file."""
    try:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        return conn
    except sqlite3.Error as e:
        raise SQLiteReadError(f"Could not open SQLite database: {e}") from e


def list_tables(path: str) -> list[str]:
    """Return table + view names in alphabetical order, skipping the
    `sqlite_` internal-bookkeeping tables."""
    conn = _open_readonly(path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
            "ORDER BY name COLLATE NOCASE"
        )
        return [row[0] for row in cur.fetchall()]
    except sqlite3.Error as e:
        raise SQLiteReadError(f"Could not list tables: {e}") from e
    finally:
        conn.close()


def table_row_count(path: str, table: str) -> int:
    conn = _open_readonly(path)
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM \"{table}\"")
        return int(cur.fetchone()[0])
    except sqlite3.Error:
        return -1
    finally:
        conn.close()


def load_table_as_csv(path: str, table: str, *,
                       row_cap: int = _DEFAULT_ROW_CAP) -> str:
    """Extract one table to CSV-shaped text. Output is capped at
    `row_cap` rows; an over-cap result appends a one-line warning so the
    user knows they're seeing a slice."""
    if not table:
        raise SQLiteReadError("Empty table name.")
    # Reject anything that isn't a valid SQLite identifier shape; this
    # also blocks injection via the f-string below.
    if not _is_safe_identifier(table):
        raise SQLiteReadError(f"Unsafe table identifier: {table!r}")
    conn = _open_readonly(path)
    try:
        cur = conn.execute(f'SELECT * FROM "{table}" LIMIT {row_cap + 1}')
        return _cursor_to_csv(cur, row_cap=row_cap)
    except sqlite3.Error as e:
        raise SQLiteReadError(f"Could not read table {table!r}: {e}") from e
    finally:
        conn.close()


def run_query_as_csv(path: str, sql: str, *,
                     row_cap: int = _DEFAULT_ROW_CAP) -> str:
    """Run an arbitrary SQL statement and return its result as CSV text.

    Read-only mode means writes (`INSERT` / `UPDATE` / `CREATE` …) raise
    a `SQLiteReadError`. Multi-statement input is not allowed —
    sqlite3.Connection.execute itself rejects it."""
    sql = (sql or "").strip()
    if not sql:
        raise SQLiteReadError("Empty SQL.")
    conn = _open_readonly(path)
    try:
        cur = conn.execute(sql)
        if cur.description is None:
            # Statement produced no rows (and read-only would have blocked
            # mutating ones anyway). Return an empty table.
            return ""
        return _cursor_to_csv(cur, row_cap=row_cap)
    except sqlite3.Error as e:
        raise SQLiteReadError(str(e)) from e
    finally:
        conn.close()


# ----------------------------------------------------------- internals --

def _is_safe_identifier(name: str) -> bool:
    """SQLite identifier shape: letter/underscore start, then letters /
    digits / underscores. Most real-world tables fit; quoted ones with
    spaces won't, but `list_tables()` returns the bare names of those
    anyway and we can revisit if a user hits one."""
    if not name: return False
    if not (name[0].isalpha() or name[0] == "_"): return False
    return all(c.isalnum() or c == "_" for c in name)


def _format_cell(v) -> str:
    if v is None: return ""
    if isinstance(v, bytes):
        return f"<bytes:{len(v)}>"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _cursor_to_csv(cur, *, row_cap: int) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    header = [d[0] for d in (cur.description or [])]
    if header:
        writer.writerow(header)
    n_written = 0
    truncated = False
    for row in cur:
        if n_written >= row_cap:
            truncated = True
            break
        writer.writerow(_format_cell(c) for c in row)
        n_written += 1
    if truncated:
        out.write(f"\n# (truncated at {row_cap} rows — use a query with LIMIT to see more)\n")
    return out.getvalue()


# --------------------------------------------------- MainWindow glue --

def show_table_picker(window) -> None:
    """**Table → Switch table…** for SQLite. Lists all tables/views in
    the active database; loading one swaps it into the TableView."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "sqlite" or not window._current_path:
        window.statusBar().showMessage("Switch table: no SQLite file is open.", 5000)
        return
    tables = getattr(window, "_sqlite_tables", []) or []
    if not tables:
        window.statusBar().showMessage("No tables in this database.", 4000)
        return
    if len(tables) <= 1:
        window.statusBar().showMessage("This database has only one table.", 4000)
        return
    current = getattr(window, "_sqlite_table_index", 0)
    name, ok = QInputDialog.getItem(
        window, "Switch table",
        f"Tables in {Path(window._current_path).name}:",
        tables, current, False,
    )
    if not ok: return
    idx = tables.index(name)
    if idx == current: return
    try:
        csv_text = load_table_as_csv(window._current_path, name)
    except SQLiteReadError as e:
        QMessageBox.warning(window, "Could not switch table", str(e))
        return
    window._sqlite_table_index = idx
    window._current_content = csv_text
    window._table_source = None
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    n = table_row_count(window._current_path, name)
    rows = f"{n:,} rows" if n >= 0 else "rows: ?"
    window.statusBar().showMessage(
        f"Loaded table {idx + 1}/{len(tables)}: {name!r} · {rows}", 4000)


def show_query_runner(window) -> None:
    """**Table → Run SQL…**. Free-form read-only SELECT against the
    open database. Result populates the TableView."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "sqlite" or not window._current_path:
        window.statusBar().showMessage("Run SQL: no SQLite file is open.", 5000)
        return
    sql, ok = QInputDialog.getMultiLineText(
        window, "Run SQL (read-only)",
        "SELECT statement to run:\n(Writes are blocked — the connection is read-only.)",
        "SELECT * FROM sqlite_master;",
    )
    if not ok or not sql.strip(): return
    try:
        csv_text = run_query_as_csv(window._current_path, sql)
    except SQLiteReadError as e:
        QMessageBox.warning(window, "Query failed", str(e))
        return
    if not csv_text.strip():
        window.statusBar().showMessage("Query returned no rows.", 4000)
        return
    window._current_content = csv_text
    window._table_source = None
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    window.statusBar().showMessage(
        f"Query → {csv_text.count(chr(10))} lines of result.", 5000)
