"""Read HDF5 (`.h5` / `.hdf5`) and NetCDF (`.nc` / `.nc4` / `.cdf`)
hierarchical scientific files into the table view.

`list_datasets(path)` walks the file's group tree and returns a flat
list of dataset paths (`/group/subgroup/array`); the user picks one
via the standard F4 picker. Each dataset becomes CSV-shaped text via
the same 1D/2D/3D dispatch the NumPy loader uses, so `TableView`
handles the rendering.

`h5py` and `netCDF4` are lazy-imported with friendly install hints.
NetCDF files are actually HDF5 under the hood for v4 files, so we
prefer h5py for `.nc` too if it works — falls back to netCDF4 when
h5py rejects them (NetCDF3 classic format)."""
from __future__ import annotations

import csv
import io
from pathlib import Path


HDF5_EXTENSIONS = {".h5", ".hdf5", ".he5", ".h5z"}
NETCDF_EXTENSIONS = {".nc", ".nc4", ".cdf"}
ALL_EXTENSIONS = HDF5_EXTENSIONS | NETCDF_EXTENSIONS

_DEFAULT_ROW_CAP = 100_000


class Hdf5ReadError(Exception):
    pass


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in ALL_EXTENSIONS


def list_datasets(path: str) -> list[str]:
    """Flat list of all dataset paths inside the file."""
    suffix = Path(path).suffix.lower()
    if suffix in HDF5_EXTENSIONS or _looks_like_hdf5(path):
        return _h5_list(path)
    if suffix in NETCDF_EXTENSIONS:
        return _netcdf_list(path)
    raise Hdf5ReadError(f"Unsupported extension: {suffix}")


def load_dataset_as_csv(path: str, name: str, *,
                        row_cap: int = _DEFAULT_ROW_CAP) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in HDF5_EXTENSIONS or _looks_like_hdf5(path):
        return _h5_dataset_to_csv(path, name, row_cap=row_cap)
    if suffix in NETCDF_EXTENSIONS:
        return _netcdf_dataset_to_csv(path, name, row_cap=row_cap)
    raise Hdf5ReadError(f"Unsupported extension: {suffix}")


def dataset_metadata(path: str, name: str) -> dict:
    suffix = Path(path).suffix.lower()
    if suffix in HDF5_EXTENSIONS or _looks_like_hdf5(path):
        return _h5_metadata(path, name)
    if suffix in NETCDF_EXTENSIONS:
        return _netcdf_metadata(path, name)
    raise Hdf5ReadError(f"Unsupported extension: {suffix}")


# ----------------------------------------------------------- magic --

_HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


def _looks_like_hdf5(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(8) == _HDF5_MAGIC
    except OSError:
        return False


# ----------------------------------------------------------- h5py --

def _h5py():
    try:
        import h5py  # type: ignore
        return h5py
    except ImportError as e:
        raise Hdf5ReadError(
            "Reading HDF5 needs h5py. Install with `pip install h5py`."
        ) from e


def _h5_list(path: str) -> list[str]:
    h5py = _h5py()
    out: list[str] = []
    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            out.append("/" + name)
    try:
        with h5py.File(path, "r") as hf:
            hf.visititems(visit)
    except Exception as e:
        raise Hdf5ReadError(f"Could not open HDF5: {e}") from e
    return sorted(out)


def _h5_dataset_to_csv(path: str, name: str, *, row_cap: int) -> str:
    h5py = _h5py()
    try:
        with h5py.File(path, "r") as hf:
            if name.lstrip("/") not in hf:
                raise Hdf5ReadError(f"No such dataset: {name}")
            ds = hf[name.lstrip("/")]
            arr = ds[()]  # materialise to numpy
            return _array_to_csv(arr, name=name, row_cap=row_cap)
    except Hdf5ReadError:
        raise
    except Exception as e:
        raise Hdf5ReadError(f"Could not read dataset {name!r}: {e}") from e


def _h5_metadata(path: str, name: str) -> dict:
    h5py = _h5py()
    try:
        with h5py.File(path, "r") as hf:
            ds = hf[name.lstrip("/")]
            return {
                "shape": tuple(ds.shape),
                "dtype": str(ds.dtype),
                "ndim": int(ds.ndim),
                "compression": ds.compression or "",
                "chunks": tuple(ds.chunks or ()),
            }
    except Exception as e:
        raise Hdf5ReadError(f"Could not read metadata: {e}") from e


# ----------------------------------------------------------- netCDF4 --

def _netcdf4():
    try:
        import netCDF4  # type: ignore
        return netCDF4
    except ImportError as e:
        raise Hdf5ReadError(
            "Reading NetCDF needs netCDF4. "
            "Install with `pip install netCDF4`."
        ) from e


def _netcdf_list(path: str) -> list[str]:
    nc = _netcdf4()
    out: list[str] = []
    def visit(group, prefix: str):
        for varname in group.variables:
            out.append(f"{prefix}/{varname}" if prefix else f"/{varname}")
        for sub in group.groups:
            visit(group.groups[sub], f"{prefix}/{sub}")
    try:
        with nc.Dataset(path, "r") as root:
            visit(root, "")
    except Exception as e:
        raise Hdf5ReadError(f"Could not open NetCDF: {e}") from e
    return sorted(out)


def _netcdf_dataset_to_csv(path: str, name: str, *, row_cap: int) -> str:
    nc = _netcdf4()
    parts = [p for p in name.split("/") if p]
    var_name = parts[-1]; group_path = parts[:-1]
    try:
        with nc.Dataset(path, "r") as root:
            grp = root
            for g in group_path:
                grp = grp.groups[g]
            arr = grp.variables[var_name][:]
            return _array_to_csv(arr, name=name, row_cap=row_cap)
    except KeyError:
        raise Hdf5ReadError(f"No such variable: {name}")
    except Exception as e:
        raise Hdf5ReadError(f"Could not read variable {name!r}: {e}") from e


def _netcdf_metadata(path: str, name: str) -> dict:
    nc = _netcdf4()
    parts = [p for p in name.split("/") if p]
    var_name = parts[-1]; group_path = parts[:-1]
    try:
        with nc.Dataset(path, "r") as root:
            grp = root
            for g in group_path:
                grp = grp.groups[g]
            var = grp.variables[var_name]
            return {
                "shape": tuple(var.shape),
                "dtype": str(var.dtype),
                "ndim": int(var.ndim),
                "units": getattr(var, "units", "") or "",
            }
    except Exception as e:
        raise Hdf5ReadError(f"Could not read metadata: {e}") from e


# ----------------------------------------------------------- array → CSV --

def _array_to_csv(arr, *, name: str, row_cap: int) -> str:
    """Dispatch on ndim, reusing the same shape rules as numpy_loader."""
    import numpy as np
    # h5py / netCDF4 hand us numpy arrays (or masked arrays).
    if isinstance(arr, np.ma.MaskedArray):
        arr = arr.filled(arr.fill_value)
    if arr.dtype.names is not None:
        return _structured_to_csv(arr, row_cap=row_cap)
    if arr.ndim == 0:
        return f"property,value\nname,{name}\nvalue,{_fmt(arr.item())}\n"
    if arr.ndim == 1:
        return _1d_to_csv(arr, row_cap=row_cap)
    if arr.ndim == 2:
        return _2d_to_csv(arr, row_cap=row_cap)
    return _high_dim_summary(arr, name=name)


def _fmt(v) -> str:
    if v is None: return ""
    if isinstance(v, bytes):
        try: return v.decode("utf-8", "replace")
        except Exception: return f"<bytes:{len(v)}>"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _1d_to_csv(arr, *, row_cap: int) -> str:
    out = io.StringIO(); w = csv.writer(out); w.writerow(["value"])
    n = int(arr.shape[0])
    for i in range(min(n, row_cap)): w.writerow([_fmt(arr[i])])
    if n > row_cap: out.write(f"\n# (truncated at {row_cap} of {n} rows)\n")
    return out.getvalue()


def _2d_to_csv(arr, *, row_cap: int) -> str:
    out = io.StringIO(); w = csv.writer(out)
    rows, cols = arr.shape
    w.writerow([f"col_{i}" for i in range(cols)])
    for r in range(min(rows, row_cap)):
        w.writerow([_fmt(arr[r, c]) for c in range(cols)])
    if rows > row_cap: out.write(f"\n# (truncated at {row_cap} of {rows} rows)\n")
    return out.getvalue()


def _structured_to_csv(arr, *, row_cap: int) -> str:
    out = io.StringIO(); w = csv.writer(out)
    names = list(arr.dtype.names or ()); w.writerow(names)
    n = int(arr.shape[0]) if arr.ndim >= 1 else 1
    for r in range(min(n, row_cap)):
        rec = arr[r] if arr.ndim >= 1 else arr
        w.writerow([_fmt(rec[name]) for name in names])
    if n > row_cap: out.write(f"\n# (truncated at {row_cap} of {n} records)\n")
    return out.getvalue()


def _high_dim_summary(arr, *, name: str) -> str:
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["property", "value"])
    w.writerow(["name", name])
    w.writerow(["dtype", str(arr.dtype)])
    w.writerow(["shape", str(tuple(arr.shape))])
    w.writerow(["ndim", str(arr.ndim)])
    w.writerow(["size", str(arr.size)])
    return out.getvalue()


# --------------------------------------------------- MainWindow glue --

def show_dataset_picker(window) -> None:
    """**Table → Switch dataset…** for HDF5 / NetCDF."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    if window._current_format != "hdf5" or not window._current_path:
        window.statusBar().showMessage("Switch dataset: no HDF5 / NetCDF file open.", 5000)
        return
    names = getattr(window, "_hdf5_datasets", []) or []
    if len(names) <= 1:
        window.statusBar().showMessage("Only one dataset in this file.", 4000)
        return
    current = getattr(window, "_hdf5_dataset_index", 0)
    name, ok = QInputDialog.getItem(
        window, "Switch dataset",
        f"Datasets in {Path(window._current_path).name}:",
        names, current, False,
    )
    if not ok: return
    idx = names.index(name)
    if idx == current: return
    try:
        csv_text = load_dataset_as_csv(window._current_path, name)
    except Hdf5ReadError as e:
        QMessageBox.warning(window, "Could not switch dataset", str(e))
        return
    window._hdf5_dataset_index = idx
    window._current_content = csv_text
    window._table_source = None
    window.viewer.code.setPlainText(csv_text)
    window.viewer.code.document().clearUndoRedoStacks()
    window._load_csv_table(csv_text)
    window._refresh_view()
    window.statusBar().showMessage(
        f"Loaded dataset {idx + 1}/{len(names)}: {name!r}", 4000)
