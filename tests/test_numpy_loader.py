"""Coverage for src.numpy_loader — 1D / 2D / 3D / structured arrays,
npy + npz, and file_loader integration."""
from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path

from src.numpy_loader import (
    NPY_EXTENSIONS, NPZ_EXTENSIONS, is_supported, list_arrays,
    load_array_as_csv, array_metadata, NumpyReadError,
)


def test_is_supported():
    assert is_supported("x.npy") and is_supported("x.NPY")
    assert is_supported("y.npz")
    assert not is_supported("x.csv")


def test_extension_sets():
    assert ".npy" in NPY_EXTENSIONS
    assert ".npz" in NPZ_EXTENSIONS
    assert NPY_EXTENSIONS.isdisjoint(NPZ_EXTENSIONS)


# -- .npy single arrays ----------------------------------------------------

def test_npy_1d(tmp_path):
    p = tmp_path / "a.npy"
    np.save(p, np.array([1, 2, 3, 4, 5]))
    out = load_array_as_csv(str(p))
    lines = out.strip().splitlines()
    assert lines[0] == "value"
    assert lines[1] == "1" and lines[5] == "5"


def test_npy_2d(tmp_path):
    p = tmp_path / "a.npy"
    np.save(p, np.array([[1, 2, 3], [4, 5, 6]]))
    out = load_array_as_csv(str(p))
    lines = out.strip().splitlines()
    assert lines[0] == "col_0,col_1,col_2"
    assert lines[1] == "1,2,3"
    assert lines[2] == "4,5,6"


def test_npy_int_floats_dont_become_decimal(tmp_path):
    p = tmp_path / "a.npy"
    np.save(p, np.array([5.0, 6.0, 7.0]))
    out = load_array_as_csv(str(p))
    body = out.strip().splitlines()[1:]
    assert body == ["5", "6", "7"]


def test_npy_3d_returns_summary(tmp_path):
    p = tmp_path / "tensor.npy"
    np.save(p, np.zeros((2, 3, 4)))
    out = load_array_as_csv(str(p))
    assert "property,value" in out
    assert "shape" in out and "(2, 3, 4)" in out
    assert "ndim" in out


def test_npy_0d_scalar(tmp_path):
    p = tmp_path / "scalar.npy"
    np.save(p, np.array(42))
    out = load_array_as_csv(str(p))
    assert out.strip().splitlines() == ["value", "42"]


def test_npy_structured_array(tmp_path):
    p = tmp_path / "struct.npy"
    dtype = [("name", "U10"), ("age", "i4")]
    arr = np.array([("Alice", 30), ("Bob", 25)], dtype=dtype)
    np.save(p, arr)
    out = load_array_as_csv(str(p))
    lines = out.strip().splitlines()
    assert lines[0] == "name,age"
    assert "Alice,30" in lines[1]
    assert "Bob,25" in lines[2]


def test_npy_row_cap_truncates(tmp_path):
    p = tmp_path / "big.npy"
    np.save(p, np.arange(100))
    out = load_array_as_csv(str(p), row_cap=10)
    assert "# (truncated" in out


# -- .npz multi-array -----------------------------------------------------

def test_npz_list_arrays(tmp_path):
    p = tmp_path / "bundle.npz"
    np.savez(p, alpha=np.array([1, 2]), beta=np.array([3, 4, 5]))
    names = list_arrays(str(p))
    assert set(names) == {"alpha", "beta"}


def test_npz_load_by_name(tmp_path):
    p = tmp_path / "bundle.npz"
    np.savez(p, alpha=np.array([1, 2]), beta=np.array([3, 4, 5]))
    out = load_array_as_csv(str(p), "beta")
    lines = out.strip().splitlines()
    assert lines == ["value", "3", "4", "5"]


def test_npz_unknown_name_raises(tmp_path):
    p = tmp_path / "bundle.npz"
    np.savez(p, only=np.array([1]))
    with pytest.raises(NumpyReadError):
        load_array_as_csv(str(p), "missing")


def test_npy_single_returns_one_array_name():
    """Single .npy reports the synthetic 'array' name."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as f:
        np.save(f, np.array([1, 2, 3]))
        path = f.name
    try:
        assert list_arrays(path) == ["array"]
    finally:
        Path(path).unlink()


# -- metadata --------------------------------------------------------------

def test_array_metadata(tmp_path):
    p = tmp_path / "m.npy"
    np.save(p, np.zeros((4, 7), dtype=np.float32))
    meta = array_metadata(str(p), "array")
    assert meta["shape"] == (4, 7)
    assert meta["dtype"] == "float32"
    assert meta["ndim"] == 2


# -- file_loader integration ----------------------------------------------

def test_file_loader_routes_npy(tmp_path):
    from src.file_loader import detect_format, load_file
    p = tmp_path / "x.npy"
    np.save(p, np.array([1, 2, 3]))
    assert detect_format(p) == "numpy"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "numpy"
    assert "value" in content
    assert "shape=" in encoding


def test_file_loader_routes_npz(tmp_path):
    from src.file_loader import detect_format, load_file
    p = tmp_path / "x.npz"
    np.savez(p, A=np.array([1, 2]), B=np.array([[1, 2], [3, 4]]))
    assert detect_format(p) == "numpy"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "numpy"
    # Picks the first array (alphabetical-ish order from numpy).
    assert content  # not empty


def test_load_blocks_pickle_arrays(tmp_path):
    """A .npy that contains an object array would require allow_pickle=True
    to load. We pass allow_pickle=False on principle — reading must raise
    instead of executing arbitrary unpickled code."""
    p = tmp_path / "obj.npy"
    arr = np.array([{"key": "value"}], dtype=object)
    np.save(p, arr, allow_pickle=True)  # save side allows pickle
    with pytest.raises(NumpyReadError):
        load_array_as_csv(str(p))
