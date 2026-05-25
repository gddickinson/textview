"""Read NumPy array files (`.npy`, `.npz`) into the table view.

Strategy parallels `spreadsheet_loader.py`: extract a single array to
CSV-shaped text and route through the existing `TableView`. `.npy` is
one anonymous array (we call it `"array"` in the picker); `.npz` is a
zip of named arrays so the user can switch between them with F4.

Supported array shapes:
  - **1D**: rendered as a single-column table with header `value`.
  - **2D**: rows × columns, columns named `col_0`, `col_1`, …
  - **Structured** (dtype.names != None): one column per field, using
    field names as headers.
  - **3D+**: shown as a one-cell summary table with shape + dtype —
    the table view can't display arbitrary tensors, but the user can
    still inspect the file and run a script against it.

`numpy.load` is invoked with `allow_pickle=False` so a malicious
`.npy` can't ship arbitrary code that runs during load — the standard
warning for the format.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path


NPY_EXTENSIONS = {".npy"}
NPZ_EXTENSIONS = {".npz"}
ALL_EXTENSIONS = NPY_EXTENSIONS | NPZ_EXTENSIONS

# Cap rows so a 50M-row array doesn't lock the UI.
_DEFAULT_ROW_CAP = 100_000


class NumpyReadError(Exception):
    pass


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in ALL_EXTENSIONS


def list_arrays(path: str) -> list[str]:
    """For `.npy` returns `["array"]` (the single anonymous array). For
    `.npz` returns the named arrays in the order numpy reports them."""
    suffix = Path(path).suffix.lower()
    if suffix in NPY_EXTENSIONS:
        return ["array"]
    if suffix in NPZ_EXTENSIONS:
        try:
            import numpy as np
            with np.load(path, allow_pickle=False) as npz:
                return list(npz.files)
        except Exception as e:
            raise NumpyReadError(f"Could not open .npz file: {e}") from e
    raise NumpyReadError(f"Unsupported extension: {suffix}")


def array_metadata(path: str, name: str) -> dict:
    """Return `{"shape": tuple, "dtype": str, "nbytes": int, "ndim": int}`
    for a named array. Cheap — does not materialise large blobs."""
    arr = _load_array(path, name)
    return {
        "shape": tuple(arr.shape),
        "dtype": str(arr.dtype),
        "nbytes": int(arr.nbytes),
        "ndim": int(arr.ndim),
    }


def load_array_as_csv(path: str, name: str = "array", *,
                      row_cap: int = _DEFAULT_ROW_CAP) -> str:
    """Render one array as CSV text. Returns a short summary table for
    3D+ arrays (the table view can't show arbitrary tensors)."""
    arr = _load_array(path, name)
    if arr.dtype.names is not None:
        return _structured_to_csv(arr, row_cap=row_cap)
    if arr.ndim == 0:
        return f"value\n{_fmt(arr.item())}\n"
    if arr.ndim == 1:
        return _1d_to_csv(arr, row_cap=row_cap)
    if arr.ndim == 2:
        return _2d_to_csv(arr, row_cap=row_cap)
    return _high_dim_summary(arr, name=name)


# ----------------------------------------------------------- internals --

def _load_array(path: str, name: str):
    """Resolve the array, blocking pickle-backed loads."""
    try:
        import numpy as np
    except ImportError as e:
        raise NumpyReadError("numpy is required") from e
    suffix = Path(path).suffix.lower()
    try:
        if suffix in NPY_EXTENSIONS:
            return np.load(path, allow_pickle=False)
        if suffix in NPZ_EXTENSIONS:
            with np.load(path, allow_pickle=False) as npz:
                if name not in npz.files:
                    raise NumpyReadError(
                        f"No such array {name!r}. Available: {list(npz.files)}")
                return npz[name]
    except NumpyReadError:
        raise
    except Exception as e:
        raise NumpyReadError(f"Could not read array: {e}") from e
    raise NumpyReadError(f"Unsupported extension: {suffix}")


def _fmt(v) -> str:
    """Stringify a numpy scalar, preserving int shape for integer floats."""
    if v is None: return ""
    if isinstance(v, (bytes, bytearray)):
        try: return v.decode("utf-8", "replace")
        except Exception: return f"<bytes:{len(v)}>"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _1d_to_csv(arr, *, row_cap: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["value"])
    n = int(arr.shape[0])
    truncated = n > row_cap
    for i in range(min(n, row_cap)):
        w.writerow([_fmt(arr[i])])
    if truncated:
        out.write(f"\n# (truncated at {row_cap} of {n} rows)\n")
    return out.getvalue()


def _2d_to_csv(arr, *, row_cap: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    rows, cols = arr.shape
    w.writerow([f"col_{i}" for i in range(cols)])
    truncated = rows > row_cap
    for r in range(min(rows, row_cap)):
        w.writerow([_fmt(arr[r, c]) for c in range(cols)])
    if truncated:
        out.write(f"\n# (truncated at {row_cap} of {rows} rows)\n")
    return out.getvalue()


def _structured_to_csv(arr, *, row_cap: int) -> str:
    """Structured array → one column per field. Records that fail to
    stringify are emitted as their `repr` rather than aborting."""
    out = io.StringIO()
    w = csv.writer(out)
    names = list(arr.dtype.names or ())
    w.writerow(names)
    n = int(arr.shape[0]) if arr.ndim >= 1 else 1
    truncated = n > row_cap
    for r in range(min(n, row_cap)):
        rec = arr[r] if arr.ndim >= 1 else arr
        row = []
        for name in names:
            try: row.append(_fmt(rec[name]))
            except Exception: row.append(repr(rec))
        w.writerow(row)
    if truncated:
        out.write(f"\n# (truncated at {row_cap} of {n} records)\n")
    return out.getvalue()


def _high_dim_summary(arr, *, name: str) -> str:
    """3D+ arrays don't fit in a 2D table — return a tiny summary."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["property", "value"])
    w.writerow(["name", name])
    w.writerow(["dtype", str(arr.dtype)])
    w.writerow(["shape", str(tuple(arr.shape))])
    w.writerow(["ndim", str(arr.ndim)])
    w.writerow(["size", str(arr.size)])
    w.writerow(["nbytes", str(arr.nbytes)])
    return out.getvalue()


# --------------------------------------------------- MainWindow glue --

def show_array_picker(window) -> None:
    """**Table → Switch array…** for `.npz` files. No-op (with status
    hint) for `.npy` since there's nothing to switch to."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "numpy" or not window._current_path:
        window.statusBar().showMessage("Switch array: no .npy/.npz file open.", 5000)
        return
    names = getattr(window, "_numpy_arrays", []) or []
    if len(names) <= 1:
        window.statusBar().showMessage(
            "This file contains only one array.", 4000)
        return
    current = getattr(window, "_numpy_array_index", 0)
    name, ok = QInputDialog.getItem(
        window, "Switch array",
        f"Arrays in {Path(window._current_path).name}:",
        names, current, False,
    )
    if not ok: return
    idx = names.index(name)
    if idx == current: return
    try:
        csv_text = load_array_as_csv(window._current_path, name)
        meta = array_metadata(window._current_path, name)
    except NumpyReadError as e:
        QMessageBox.warning(window, "Could not switch array", str(e))
        return
    window._numpy_array_index = idx
    window._current_content = csv_text
    window._table_source = None
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    window.statusBar().showMessage(
        f"Loaded array {idx + 1}/{len(names)}: {name!r} · "
        f"shape={meta['shape']} dtype={meta['dtype']}", 5000)
