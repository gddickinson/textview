"""Read Apache Parquet / Apache Arrow Feather files into the table view.

Both formats round-trip through CSV-shaped text the same way XLSX,
SQLite and NumPy do — `TableView` does the rendering. The pyarrow
reader uses native Arrow types; dtypes appear in the status-bar label.

A row cap (default 100k) keeps the table responsive on big files;
when it fires we append a `# (truncated…)` marker so the user knows
they're looking at a slice.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path


PARQUET_EXTENSIONS = {".parquet", ".pq"}
FEATHER_EXTENSIONS = {".feather", ".arrow", ".ipc"}
ALL_EXTENSIONS = PARQUET_EXTENSIONS | FEATHER_EXTENSIONS

_DEFAULT_ROW_CAP = 100_000


class ParquetReadError(Exception):
    pass


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in ALL_EXTENSIONS


def read_as_csv(path: str, *, row_cap: int = _DEFAULT_ROW_CAP) -> str:
    """Dispatch on extension. Returns CSV-shaped text."""
    suffix = Path(path).suffix.lower()
    if suffix in PARQUET_EXTENSIONS:
        return _parquet_to_csv(path, row_cap=row_cap)
    if suffix in FEATHER_EXTENSIONS:
        return _feather_to_csv(path, row_cap=row_cap)
    raise ParquetReadError(f"Unsupported extension: {suffix}")


def file_metadata(path: str) -> dict:
    """Return `{"rows": N, "columns": [(name, dtype), …]}`. Cheap —
    doesn't materialise data, just reads the file schema."""
    suffix = Path(path).suffix.lower()
    if suffix in PARQUET_EXTENSIONS:
        try:
            import pyarrow.parquet as pq  # type: ignore
        except ImportError as e:
            raise ParquetReadError("Reading Parquet needs pyarrow.") from e
        try:
            pf = pq.ParquetFile(path)
            schema = pf.schema_arrow
            return {
                "rows": int(pf.metadata.num_rows),
                "columns": [(f.name, str(f.type)) for f in schema],
            }
        except Exception as e:
            raise ParquetReadError(f"Could not read Parquet schema: {e}") from e
    if suffix in FEATHER_EXTENSIONS:
        try:
            import pyarrow.feather as feather  # type: ignore
        except ImportError as e:
            raise ParquetReadError("Reading Feather needs pyarrow.") from e
        try:
            tab = feather.read_table(path)
            return {
                "rows": int(tab.num_rows),
                "columns": [(name, str(tab.schema.field(name).type))
                            for name in tab.schema.names],
            }
        except Exception as e:
            raise ParquetReadError(f"Could not read Feather schema: {e}") from e
    raise ParquetReadError(f"Unsupported extension: {suffix}")


# ----------------------------------------------------------- internals --

def _parquet_to_csv(path: str, *, row_cap: int) -> str:
    try:
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as e:
        raise ParquetReadError(
            "Reading Parquet needs pyarrow. "
            "Install with `pip install pyarrow`."
        ) from e
    try:
        # `iter_batches` lets us stop after `row_cap` rows without
        # loading a billion-row file into memory first.
        pf = pq.ParquetFile(path)
        return _arrow_pf_to_csv(pf, row_cap=row_cap)
    except Exception as e:
        raise ParquetReadError(f"Could not read Parquet: {e}") from e


def _feather_to_csv(path: str, *, row_cap: int) -> str:
    try:
        import pyarrow.feather as feather  # type: ignore
    except ImportError as e:
        raise ParquetReadError(
            "Reading Feather needs pyarrow. "
            "Install with `pip install pyarrow`."
        ) from e
    try:
        table = feather.read_table(path)
        return _arrow_table_to_csv(table, row_cap=row_cap)
    except Exception as e:
        raise ParquetReadError(f"Could not read Feather: {e}") from e


def _arrow_pf_to_csv(pf, *, row_cap: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    header = pf.schema_arrow.names
    w.writerow(header)
    total = 0
    total_rows = int(pf.metadata.num_rows)
    for batch in pf.iter_batches(batch_size=4096):
        n = batch.num_rows
        cols = [batch.column(i) for i in range(batch.num_columns)]
        for r in range(n):
            if total >= row_cap: break
            w.writerow([_fmt_cell(col[r].as_py()) for col in cols])
            total += 1
        if total >= row_cap: break
    if total_rows > total:
        out.write(f"\n# (truncated at {row_cap} of {total_rows} rows)\n")
    return out.getvalue()


def _arrow_table_to_csv(table, *, row_cap: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    names = table.schema.names
    w.writerow(names)
    total_rows = int(table.num_rows)
    rows = min(total_rows, row_cap)
    # `to_pydict()` is the simplest path for moderate row counts.
    cols = [table.column(name) for name in names]
    py_cols = [c.to_pylist() for c in cols]
    for r in range(rows):
        w.writerow([_fmt_cell(py_cols[c][r]) for c in range(len(names))])
    if total_rows > rows:
        out.write(f"\n# (truncated at {row_cap} of {total_rows} rows)\n")
    return out.getvalue()


def _fmt_cell(v) -> str:
    if v is None: return ""
    if isinstance(v, bytes):
        try: return v.decode("utf-8", "replace")
        except Exception: return f"<bytes:{len(v)}>"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
