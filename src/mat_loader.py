"""Read MATLAB binary `.mat` files via `scipy.io`.

Variables become entries you can switch between with F4. Each
variable is rendered through the existing TableView pipeline:

  - 1D numpy arrays → single-column table
  - 2D numpy arrays → multi-column table
  - 3D+ arrays → property/value summary
  - struct arrays / dicts → key/value pairs
  - cell arrays → list rendered one element per row
  - scalars → single-row table

`scipy.io.loadmat(..., simplify_cells=True)` so old MATLAB cell
structures come back as plain dicts / lists rather than 0-d object
arrays. Falls back gracefully (`MatReadError`) if scipy is missing.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path


MAT_EXTENSIONS = {".mat"}


class MatReadError(Exception):
    pass


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in MAT_EXTENSIONS


def _scipy_loadmat(path: str):
    try:
        from scipy.io import loadmat  # type: ignore
    except ImportError as e:
        raise MatReadError(
            "Reading .mat files needs scipy. Install with `pip install scipy`."
        ) from e
    try:
        return loadmat(path, simplify_cells=True)
    except Exception as e:
        raise MatReadError(f"Could not parse .mat: {e}") from e


def list_variables(path: str) -> list[str]:
    data = _scipy_loadmat(path)
    # Filter out scipy's internal bookkeeping keys.
    return [k for k in data.keys() if not (k.startswith("__") and k.endswith("__"))]


def variable_metadata(path: str, name: str) -> dict:
    data = _scipy_loadmat(path)
    if name not in data:
        raise MatReadError(f"No such variable {name!r}")
    v = data[name]
    meta: dict = {"type": type(v).__name__}
    try:
        import numpy as np
        if isinstance(v, np.ndarray):
            meta.update({"shape": tuple(v.shape), "dtype": str(v.dtype),
                          "ndim": int(v.ndim)})
    except ImportError:
        pass
    return meta


def load_variable_as_csv(path: str, name: str) -> str:
    data = _scipy_loadmat(path)
    if name not in data:
        raise MatReadError(f"No such variable {name!r}")
    return _render_variable(name, data[name])


# ----------------------------------------------------------- internals --

def _render_variable(name: str, v) -> str:
    """Dispatch on Python type → CSV text. Goes via the same code that
    `numpy_loader` uses so int-shaped floats stay int."""
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is not None and isinstance(v, np.ndarray):
        if v.dtype.names is not None:
            return _structured_to_csv(v)
        if v.ndim == 0:
            return f"property,value\nname,{name}\nvalue,{_fmt(v.item())}\n"
        if v.ndim == 1:
            return _1d_to_csv(v)
        if v.ndim == 2:
            return _2d_to_csv(v)
        return _summary_to_csv(name, v)

    if isinstance(v, dict):
        return _dict_to_csv(v)
    if isinstance(v, (list, tuple)):
        return _list_to_csv(v)
    if isinstance(v, (int, float, str, bool)):
        return f"property,value\nname,{name}\nvalue,{_fmt(v)}\n"
    # Fallback for whatever scipy gave us.
    return (f"property,value\n"
            f"name,{name}\n"
            f"type,{type(v).__name__}\n"
            f"repr,{_fmt(repr(v))}\n")


def _fmt(v) -> str:
    if v is None: return ""
    if isinstance(v, bytes):
        try: return v.decode("utf-8", "replace")
        except Exception: return f"<bytes:{len(v)}>"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _row_cap_warning(out: io.StringIO, n_rows: int, cap: int):
    out.write(f"\n# (truncated at {cap} of {n_rows} rows)\n")


def _1d_to_csv(arr) -> str:
    out = io.StringIO(); w = csv.writer(out); w.writerow(["value"])
    n = int(arr.shape[0]); cap = 100_000
    for i in range(min(n, cap)): w.writerow([_fmt(arr[i])])
    if n > cap: _row_cap_warning(out, n, cap)
    return out.getvalue()


def _2d_to_csv(arr) -> str:
    out = io.StringIO(); w = csv.writer(out)
    rows, cols = arr.shape
    w.writerow([f"col_{i}" for i in range(cols)])
    cap = 100_000
    for r in range(min(rows, cap)):
        w.writerow([_fmt(arr[r, c]) for c in range(cols)])
    if rows > cap: _row_cap_warning(out, rows, cap)
    return out.getvalue()


def _structured_to_csv(arr) -> str:
    out = io.StringIO(); w = csv.writer(out)
    names = list(arr.dtype.names or ())
    w.writerow(names)
    n = int(arr.shape[0]) if arr.ndim >= 1 else 1
    cap = 100_000
    for r in range(min(n, cap)):
        rec = arr[r] if arr.ndim >= 1 else arr
        row = [_fmt(rec[n2]) for n2 in names]
        w.writerow(row)
    if n > cap: _row_cap_warning(out, n, cap)
    return out.getvalue()


def _summary_to_csv(name: str, arr) -> str:
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["property", "value"])
    w.writerow(["name", name])
    w.writerow(["dtype", str(arr.dtype)])
    w.writerow(["shape", str(tuple(arr.shape))])
    w.writerow(["ndim", str(arr.ndim)])
    w.writerow(["size", str(arr.size)])
    return out.getvalue()


def _dict_to_csv(d: dict) -> str:
    """Struct-like values (MATLAB structs become Python dicts here)."""
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["field", "type", "value"])
    for k, v in d.items():
        if hasattr(v, "shape"):  # numpy array
            w.writerow([k, f"{type(v).__name__}<{v.dtype}>",
                        f"shape={tuple(v.shape)}"])
        elif isinstance(v, (list, tuple)):
            w.writerow([k, type(v).__name__, f"len={len(v)}"])
        else:
            w.writerow([k, type(v).__name__, _fmt(v)])
    return out.getvalue()


def _list_to_csv(seq) -> str:
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["index", "value"])
    for i, v in enumerate(seq[:100_000]):
        w.writerow([str(i), _fmt(v)])
    if len(seq) > 100_000:
        _row_cap_warning(out, len(seq), 100_000)
    return out.getvalue()


# --------------------------------------------------- MainWindow glue --

def show_variable_picker(window) -> None:
    """**Table → Switch variable…** for `.mat` files."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "mat" or not window._current_path:
        window.statusBar().showMessage("Switch variable: no .mat file open.", 5000)
        return
    names = getattr(window, "_mat_variables", []) or []
    if len(names) <= 1:
        window.statusBar().showMessage("This file contains only one variable.", 4000)
        return
    current = getattr(window, "_mat_variable_index", 0)
    name, ok = QInputDialog.getItem(
        window, "Switch variable",
        f"Variables in {Path(window._current_path).name}:",
        names, current, False,
    )
    if not ok: return
    idx = names.index(name)
    if idx == current: return
    try:
        csv_text = load_variable_as_csv(window._current_path, name)
    except MatReadError as e:
        QMessageBox.warning(window, "Could not switch variable", str(e))
        return
    window._mat_variable_index = idx
    window._current_content = csv_text
    window._table_source = None
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    window.statusBar().showMessage(
        f"Loaded variable {idx + 1}/{len(names)}: {name!r}", 4000)
