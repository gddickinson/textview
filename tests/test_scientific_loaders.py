"""Coverage for the three scientific-data loaders: mat_loader,
parquet_loader, hdf5_loader. Each block is skipped if its optional
dep isn't importable."""
from __future__ import annotations

import importlib
import io
import pytest
from pathlib import Path

import numpy as np


def _have(mod):
    try: importlib.import_module(mod); return True
    except Exception: return False


# ==================================================================== MAT
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _have("scipy"), reason="scipy not installed")
def test_mat_round_trip(tmp_path):
    from scipy.io import savemat
    from src.mat_loader import (
        list_variables, load_variable_as_csv, variable_metadata,
    )
    p = tmp_path / "x.mat"
    savemat(p, {"a": np.array([[1, 2, 3], [4, 5, 6]]), "b": np.arange(5)})
    names = list_variables(str(p))
    assert "a" in names and "b" in names

    out_a = load_variable_as_csv(str(p), "a").strip().splitlines()
    assert out_a[0] == "col_0,col_1,col_2"
    assert out_a[1] == "1,2,3"

    out_b = load_variable_as_csv(str(p), "b").strip().splitlines()
    assert out_b[0] == "value"
    assert out_b[1] == "0" and out_b[-1] == "4"

    meta_a = variable_metadata(str(p), "a")
    assert meta_a["shape"] == (2, 3)


@pytest.mark.skipif(not _have("scipy"), reason="scipy not installed")
def test_mat_unknown_variable_raises(tmp_path):
    from scipy.io import savemat
    from src.mat_loader import load_variable_as_csv, MatReadError
    p = tmp_path / "x.mat"
    savemat(p, {"a": np.array([1.0])})
    with pytest.raises(MatReadError):
        load_variable_as_csv(str(p), "nope")


@pytest.mark.skipif(not _have("scipy"), reason="scipy not installed")
def test_mat_file_loader_integration(tmp_path):
    from scipy.io import savemat
    p = tmp_path / "x.mat"
    savemat(p, {"v": np.arange(3)})
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "mat"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "mat"
    assert "value" in content and "0" in content and "2" in content
    assert "variable=" in encoding


# ============================================================== PARQUET
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _have("pyarrow"), reason="pyarrow not installed")
def test_parquet_round_trip(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from src.parquet_loader import read_as_csv, file_metadata
    p = tmp_path / "data.parquet"
    tab = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    pq.write_table(tab, p)
    out = read_as_csv(str(p))
    lines = out.strip().splitlines()
    assert lines[0] == "a,b"
    assert "1,x" in lines and "3,z" in lines
    meta = file_metadata(str(p))
    assert meta["rows"] == 3
    assert meta["columns"][0][0] == "a"


@pytest.mark.skipif(not _have("pyarrow"), reason="pyarrow not installed")
def test_parquet_row_cap_truncates(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from src.parquet_loader import read_as_csv
    p = tmp_path / "big.parquet"
    tab = pa.table({"i": list(range(50))})
    pq.write_table(tab, p)
    out = read_as_csv(str(p), row_cap=10)
    assert "# (truncated" in out


@pytest.mark.skipif(not _have("pyarrow"), reason="pyarrow not installed")
def test_feather_round_trip(tmp_path):
    import pyarrow as pa
    import pyarrow.feather as feather
    from src.parquet_loader import read_as_csv, file_metadata
    p = tmp_path / "data.feather"
    feather.write_feather(pa.table({"a": [10, 20]}), p)
    out = read_as_csv(str(p))
    lines = out.strip().splitlines()
    assert lines[0] == "a"
    assert "10" in lines[1] and "20" in lines[2]


@pytest.mark.skipif(not _have("pyarrow"), reason="pyarrow not installed")
def test_parquet_file_loader_integration(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    p = tmp_path / "d.parquet"
    pq.write_table(pa.table({"k": [1, 2]}), p)
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "parquet"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "parquet"
    assert "k" in content


# ================================================================ HDF5
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_hdf5_round_trip(tmp_path):
    import h5py
    from src.hdf5_loader import (
        list_datasets, load_dataset_as_csv, dataset_metadata,
    )
    p = tmp_path / "data.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("flat", data=np.array([1.0, 2.0, 3.0]))
        g = hf.create_group("nested")
        g.create_dataset("grid", data=np.array([[1, 2], [3, 4]]))
    names = list_datasets(str(p))
    assert "/flat" in names
    assert "/nested/grid" in names

    out_flat = load_dataset_as_csv(str(p), "/flat").strip().splitlines()
    assert out_flat[0] == "value"
    assert out_flat[1:] == ["1", "2", "3"]

    out_grid = load_dataset_as_csv(str(p), "/nested/grid").strip().splitlines()
    assert out_grid[0] == "col_0,col_1"

    meta = dataset_metadata(str(p), "/nested/grid")
    assert meta["shape"] == (2, 2)


@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_hdf5_high_dim_returns_summary(tmp_path):
    import h5py
    from src.hdf5_loader import load_dataset_as_csv
    p = tmp_path / "tensor.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("t3", data=np.zeros((2, 3, 4)))
    out = load_dataset_as_csv(str(p), "/t3")
    assert "property,value" in out
    assert "(2, 3, 4)" in out


@pytest.mark.skipif(not _have("h5py"), reason="h5py not installed")
def test_hdf5_file_loader_integration(tmp_path):
    import h5py
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("d", data=np.array([1, 2, 3]))
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "hdf5"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "hdf5"
    assert "value" in content
    assert "dataset=" in encoding


# ================================================================ NetCDF
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _have("netCDF4"), reason="netCDF4 not installed")
def test_netcdf_round_trip(tmp_path):
    import netCDF4
    from src.hdf5_loader import list_datasets, load_dataset_as_csv
    p = tmp_path / "data.nc"
    with netCDF4.Dataset(p, "w") as ds:
        ds.createDimension("t", 4)
        v = ds.createVariable("temp", "f4", ("t",))
        v[:] = [20.0, 21.5, 19.0, 22.5]
    names = list_datasets(str(p))
    assert "/temp" in names
    out = load_dataset_as_csv(str(p), "/temp")
    lines = out.strip().splitlines()
    assert lines[0] == "value"
    assert "20" in lines[1] or "20.0" in lines[1]
