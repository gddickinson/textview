"""LLM tools for the structured-data file formats TextView reads.

All read-only. Each tool returns a compact text payload the agent can
reason about — schema + a row/value preview, not the entire file. Big
datasets are deliberately truncated so the agent never burns its
context window on a 50-million-row Parquet.

The tools cover every file type that landed in v3.3 + v3.4:

- `read_spreadsheet` — `.xlsx` / `.xlsm` / `.xltx` / `.xltm` / `.xls` / `.ods`
- `read_sqlite` — schema overview
- `query_sqlite` — run a SELECT against the (read-only) connection
- `read_archive` — `.zip` / `.tar*` / `.7z` member listing
- `read_array_file` — `.npy` / `.npz` (NumPy) and `.mat` (MATLAB)
- `read_parquet` — `.parquet` / `.pq` / `.feather` / `.arrow` / `.ipc`
- `read_hdf5` — `.h5` / `.hdf5` / `.nc` / `.nc4` (datasets + extract one)
- `read_cert` — `.pem` / `.crt` / `.cer` / `.der` / `.key`

Each function is wrapped in a try/except so a malformed file produces
a friendly error string rather than a tool-call failure.
"""
from __future__ import annotations

from pathlib import Path

from .tools_base import Tool


_PREVIEW_ROWS = 20
_CSV_BYTE_CAP = 6000  # trim CSV-shaped previews so context doesn't balloon


def _truncate_csv(csv_text: str, *, rows: int = _PREVIEW_ROWS) -> str:
    """Keep the header + first `rows` data rows. Returns a string the
    agent can parse without choking on a million rows."""
    lines = csv_text.splitlines()
    if not lines:
        return ""
    kept = lines[: rows + 1]   # header + N rows
    out = "\n".join(kept)
    if len(lines) > rows + 1:
        out += f"\n# ({len(lines) - rows - 1} more rows not shown)"
    if len(out) > _CSV_BYTE_CAP:
        out = out[:_CSV_BYTE_CAP] + "\n# (response trimmed)"
    return out


def _resolve(window, path: str) -> Path:
    """Allow paths relative to the project root or active file."""
    p = Path(path).expanduser()
    if p.is_absolute() or p.exists():
        return p
    # Try project-root + active-file-directory.
    for candidate_root in (
        getattr(getattr(window, "project_panel", None), "_root_path", None),
        Path(window._current_path).parent if window._current_path else None,
    ):
        if candidate_root is None:
            continue
        cand = Path(str(candidate_root)) / p
        if cand.exists():
            return cand
    return p   # let the loader raise FileNotFoundError downstream


# ---------------------------------------------------------- spreadsheets --

def _read_spreadsheet(window, path: str, sheet: str | int | None = None) -> str:
    from ..spreadsheet_loader import (
        list_sheets, load_sheet_as_csv, SpreadsheetReadError,
    )
    p = _resolve(window, path)
    try:
        sheets = list_sheets(str(p))
    except SpreadsheetReadError as e:
        return f"ERROR: {e}"
    if sheet is None:
        target = 0
    elif isinstance(sheet, int):
        target = sheet
    else:
        if sheet not in sheets:
            return (f"ERROR: no such sheet {sheet!r}. "
                    f"Available: {sheets}")
        target = sheet
    try:
        csv_text = load_sheet_as_csv(str(p), target)
    except SpreadsheetReadError as e:
        return f"ERROR: {e}"
    return (f"sheets: {sheets}\n"
            f"showing: {sheets[target] if isinstance(target, int) else target}\n\n"
            f"{_truncate_csv(csv_text)}")


# ---------------------------------------------------------- sqlite --

def _read_sqlite(window, path: str) -> str:
    """Schema overview: every table + view, column names, row count."""
    from ..sqlite_loader import (
        list_tables, table_row_count, SQLiteReadError, _open_readonly,
    )
    p = _resolve(window, path)
    try:
        tables = list_tables(str(p))
    except SQLiteReadError as e:
        return f"ERROR: {e}"
    if not tables:
        return "No user tables in this database."
    conn = _open_readonly(str(p))
    try:
        lines = [f"{len(tables)} table(s)/view(s):", ""]
        for t in tables:
            try:
                cur = conn.execute(f'PRAGMA table_info("{t}")')
                cols = [(row[1], row[2]) for row in cur.fetchall()]
            except Exception:
                cols = []
            n = table_row_count(str(p), t)
            col_desc = ", ".join(f"{n}:{ty}" for n, ty in cols) or "(unknown)"
            lines.append(f"- {t}  ({n if n >= 0 else '?'} rows): {col_desc}")
        return "\n".join(lines)
    finally:
        conn.close()


def _query_sqlite(window, path: str, sql: str) -> str:
    from ..sqlite_loader import run_query_as_csv, SQLiteReadError
    p = _resolve(window, path)
    try:
        csv_text = run_query_as_csv(str(p), sql)
    except SQLiteReadError as e:
        return f"ERROR: {e}"
    if not csv_text.strip():
        return "Query returned no rows."
    return _truncate_csv(csv_text, rows=40)


# ---------------------------------------------------------- archives --

def _read_archive(window, path: str) -> str:
    from ..archive_loader import list_members, ArchiveReadError
    p = _resolve(window, path)
    try:
        members = list_members(str(p))
    except ArchiveReadError as e:
        return f"ERROR: {e}"
    files = [m for m in members if not m.is_dir]
    total = sum(m.size for m in files)
    cap = 80
    lines = [f"{len(files):,} files, {len(members) - len(files):,} directories, "
             f"{total:,} bytes uncompressed total"]
    for m in members[:cap]:
        kind = "DIR " if m.is_dir else f"{m.size:>10,}b"
        lines.append(f"  {kind}  {m.name}")
    if len(members) > cap:
        lines.append(f"  … {len(members) - cap} more members not shown")
    return "\n".join(lines)


# ---------------------------------------------------------- array files --

def _read_array_file(window, path: str, name: str | None = None) -> str:
    """Works for `.npy` / `.npz` (NumPy) and `.mat` (MATLAB). Returns
    shape/dtype + a CSV preview of the first N rows."""
    p = _resolve(window, path)
    suffix = p.suffix.lower()
    if suffix in {".npy", ".npz"}:
        from ..numpy_loader import (
            list_arrays, load_array_as_csv, array_metadata, NumpyReadError,
        )
        try:
            arrays = list_arrays(str(p))
            target = name if name in arrays else arrays[0]
            meta = array_metadata(str(p), target)
            csv_text = load_array_as_csv(str(p), target)
        except NumpyReadError as e:
            return f"ERROR: {e}"
        header = (f"file: {p.name}  format: numpy\n"
                  f"arrays: {arrays}\n"
                  f"showing: {target}  shape={meta['shape']}  dtype={meta['dtype']}\n\n")
    elif suffix == ".mat":
        from ..mat_loader import (
            list_variables, load_variable_as_csv, MatReadError,
        )
        try:
            vars_ = list_variables(str(p))
            if not vars_:
                return "ERROR: no variables in this .mat file."
            target = name if name in vars_ else vars_[0]
            csv_text = load_variable_as_csv(str(p), target)
        except MatReadError as e:
            return f"ERROR: {e}"
        header = (f"file: {p.name}  format: matlab\n"
                  f"variables: {vars_}\n"
                  f"showing: {target}\n\n")
    else:
        return f"ERROR: unsupported extension {suffix!r}. " \
               "Use .npy, .npz, or .mat."
    return header + _truncate_csv(csv_text)


# ---------------------------------------------------------- parquet / feather --

def _read_parquet(window, path: str) -> str:
    from ..parquet_loader import read_as_csv, file_metadata, ParquetReadError
    p = _resolve(window, path)
    try:
        meta = file_metadata(str(p))
        csv_text = read_as_csv(str(p))
    except ParquetReadError as e:
        return f"ERROR: {e}"
    col_desc = ", ".join(f"{n}:{t}" for n, t in meta["columns"])
    header = (f"file: {p.name}  rows: {meta['rows']:,}\n"
              f"columns: {col_desc}\n\n")
    return header + _truncate_csv(csv_text)


# ---------------------------------------------------------- hdf5 / netcdf --

def _read_hdf5(window, path: str, dataset: str | None = None) -> str:
    from ..hdf5_loader import (
        list_datasets, load_dataset_as_csv, dataset_metadata, Hdf5ReadError,
    )
    p = _resolve(window, path)
    try:
        datasets = list_datasets(str(p))
    except Hdf5ReadError as e:
        return f"ERROR: {e}"
    if not datasets:
        return "No datasets in this file."
    if dataset is None:
        target = datasets[0]
    else:
        if dataset not in datasets:
            return (f"ERROR: no such dataset {dataset!r}. "
                    f"Available: {datasets}")
        target = dataset
    try:
        meta = dataset_metadata(str(p), target)
        csv_text = load_dataset_as_csv(str(p), target)
    except Hdf5ReadError as e:
        return f"ERROR: {e}"
    header = (f"file: {p.name}\n"
              f"datasets: {datasets}\n"
              f"showing: {target}  shape={meta.get('shape')}  "
              f"dtype={meta.get('dtype')}\n\n")
    return header + _truncate_csv(csv_text)


# ---------------------------------------------------------- certs --

def _read_cert(window, path: str) -> str:
    from ..cert_loader import render_markdown
    p = _resolve(window, path)
    return render_markdown(str(p))


# ---------------------------------------------------------- tool registry --

DATA_FORMAT_TOOLS: list[Tool] = [
    Tool(
        name="read_spreadsheet",
        description=(
            "Read an Excel / OpenDocument workbook (.xlsx, .xlsm, .xltx, "
            ".xltm, .xls, .ods). Returns the sheet list and a CSV preview "
            "of the first 20 rows of the chosen sheet (default: first "
            "sheet). Use `sheet` to pick by name or 0-based index."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "sheet": {"type": ["string", "integer"]},
            },
            "required": ["path"],
        },
        call=_read_spreadsheet,
    ),
    Tool(
        name="read_sqlite",
        description=(
            "Open a SQLite database (.sqlite / .sqlite3 / .db) and return "
            "an overview: every user table + view with its columns + "
            "types and approximate row count. Connection is read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        call=_read_sqlite,
    ),
    Tool(
        name="query_sqlite",
        description=(
            "Run an ad-hoc SELECT against a SQLite database. Returns the "
            "first 40 rows of the result as CSV. The connection is "
            "read-only — INSERT / UPDATE / CREATE etc. raise."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "sql":  {"type": "string"},
            },
            "required": ["path", "sql"],
        },
        call=_query_sqlite,
    ),
    Tool(
        name="read_archive",
        description=(
            "List members of a ZIP / TAR / .tar.gz / .tar.bz2 / .tar.xz / "
            "7z archive — first 80 entries with sizes, plus a one-line "
            "summary of totals."
        ),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        call=_read_archive,
    ),
    Tool(
        name="read_array_file",
        description=(
            "Read a NumPy `.npy` / `.npz` or MATLAB `.mat` file. Returns "
            "the available array / variable names, the active one's "
            "shape + dtype, and a CSV preview of the first 20 rows. Pass "
            "`name` to pick a specific array / variable from multi-entry "
            "files."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["path"],
        },
        call=_read_array_file,
    ),
    Tool(
        name="read_parquet",
        description=(
            "Read an Apache Parquet (.parquet / .pq) or Feather "
            "(.feather / .arrow / .ipc) file. Returns the schema (column "
            "names + types), total row count, and a CSV preview of the "
            "first 20 rows."
        ),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        call=_read_parquet,
    ),
    Tool(
        name="read_hdf5",
        description=(
            "Read an HDF5 (.h5 / .hdf5) or NetCDF (.nc / .nc4) file. "
            "Returns the dataset paths (group tree flattened), the "
            "active dataset's shape + dtype, and a CSV preview of the "
            "first 20 rows. Pass `dataset` to pick a path like "
            "`/group/subgroup/array`."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "dataset": {"type": "string"},
            },
            "required": ["path"],
        },
        call=_read_hdf5,
    ),
    Tool(
        name="read_cert",
        description=(
            "Decode an X.509 certificate (.pem / .crt / .cer / .der) or "
            "report the type + size of a PEM private key (.key). For "
            "certs, returns subject, issuer, validity window, "
            "fingerprints, public-key algo + size, SANs. **Never** "
            "displays raw private-key material."
        ),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        call=_read_cert,
    ),
]
