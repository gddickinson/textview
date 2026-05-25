"""Coverage for src/mesh_loader.py — loader, stats, preview render.

Skipped block-style when `trimesh` isn't importable."""
from __future__ import annotations

import importlib.util
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("trimesh") is None,
    reason="trimesh required for mesh-loader tests",
)

from src.mesh_loader import (
    MESH_EXTENSIONS, MeshReadError, is_supported, is_scene,
    load_mesh, mesh_stats, stats_to_markdown, render_preview_png,
    MeshStats,
)


# ---------------------------------------------------------- fixtures --

def _make_stl_cube(path: Path) -> Path:
    """Write a 1×1×1 cube to `path` via trimesh.creation.box."""
    import trimesh
    cube = trimesh.creation.box(extents=(1, 1, 1))
    cube.export(str(path))
    return path


def _make_obj_sphere(path: Path) -> Path:
    """Write a sphere to `path` as .obj."""
    import trimesh
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    sphere.export(str(path))
    return path


# ---------------------------------------------------------- detection --

@pytest.mark.parametrize("name", [
    "a.stl", "a.STL", "a.obj", "a.ply",
    "a.glb", "a.gltf", "a.dae", "a.3mf", "a.off", "a.x3d",
])
def test_is_supported_extensions(name):
    assert is_supported(name)


def test_unsupported_extension_negative():
    assert not is_supported("a.csv")
    assert not is_supported("a.png")
    assert not is_supported("noextension")


def test_extension_set_shape():
    assert ".stl" in MESH_EXTENSIONS
    assert ".glb" in MESH_EXTENSIONS
    assert ".csv" not in MESH_EXTENSIONS


# ---------------------------------------------------------- load --

def test_load_stl_cube(tmp_path):
    p = _make_stl_cube(tmp_path / "cube.stl")
    mesh = load_mesh(str(p))
    assert mesh is not None
    assert hasattr(mesh, "vertices")
    assert hasattr(mesh, "faces")


def test_load_obj_sphere(tmp_path):
    p = _make_obj_sphere(tmp_path / "sphere.obj")
    mesh = load_mesh(str(p))
    assert mesh is not None
    assert mesh.faces.shape[0] > 0


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(MeshReadError):
        load_mesh(str(tmp_path / "nope.stl"))


def test_load_corrupt_raises(tmp_path):
    bad = tmp_path / "junk.stl"
    bad.write_bytes(b"not a real stl")
    with pytest.raises(MeshReadError):
        load_mesh(str(bad))


# ---------------------------------------------------------- stats --

def test_mesh_stats_cube(tmp_path):
    p = _make_stl_cube(tmp_path / "cube.stl")
    mesh = load_mesh(str(p))
    stats = mesh_stats(mesh)
    assert isinstance(stats, MeshStats)
    assert stats.kind == "mesh"
    assert stats.vertex_count > 0
    assert stats.face_count > 0
    assert stats.object_count == 1
    # Cube extents should be ~1 in each dimension (small float noise).
    for dim in stats.extents:
        assert 0.95 < dim < 1.05
    # Cube is watertight → volume ~1.
    assert stats.is_watertight
    assert stats.volume is not None
    assert 0.95 < stats.volume < 1.05


def test_mesh_stats_sphere(tmp_path):
    p = _make_obj_sphere(tmp_path / "sphere.obj")
    mesh = load_mesh(str(p))
    stats = mesh_stats(mesh)
    assert stats.vertex_count > 30   # icosphere subd=2 → ~42 verts
    assert stats.face_count > 60
    # Unit sphere → volume ~ 4/3 * pi ~= 4.19.
    if stats.volume is not None:
        assert 3.5 < stats.volume < 4.5


def test_stats_to_markdown_renders(tmp_path):
    p = _make_stl_cube(tmp_path / "cube.stl")
    mesh = load_mesh(str(p))
    md = stats_to_markdown(mesh_stats(mesh), filename="cube.stl")
    assert "# 3D file: `cube.stl`" in md
    assert "Vertices" in md
    assert "Faces" in md
    assert "Volume" in md


# ---------------------------------------------------------- preview render --

def test_render_preview_writes_png(tmp_path):
    p = _make_stl_cube(tmp_path / "cube.stl")
    mesh = load_mesh(str(p))
    out = tmp_path / "preview.png"
    result = render_preview_png(mesh, str(out), size=(400, 300))
    assert result == str(out)
    assert out.is_file()
    # PNG magic.
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_preview_decimates_large(tmp_path):
    """A mesh way over the preview cap should still render — the
    decimation path kicks in. We just assert it doesn't crash."""
    import trimesh
    p = tmp_path / "big.stl"
    big = trimesh.creation.icosphere(subdivisions=5)  # ~10k faces
    big.export(str(p))
    out = tmp_path / "preview.png"
    render_preview_png(load_mesh(str(p)), str(out), face_cap=500)
    assert out.is_file()


# ---------------------------------------------------------- file_loader integration --

def test_file_loader_routes_mesh(tmp_path):
    """`file_loader.detect_format` should classify .stl as mesh,
    and `load_file` should return an empty body + mesh format tag
    (the actual rendering goes through MeshView)."""
    p = _make_stl_cube(tmp_path / "x.stl")
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "mesh"
    content, encoding, fmt = load_file(str(p))
    assert fmt == "mesh"
    # Body is empty — MeshView does the loading.
    assert content == ""
    assert "stl mesh" in encoding


def test_glb_scene(tmp_path):
    """GLB files often produce a Scene (multi-object), not a Trimesh."""
    import trimesh
    box = trimesh.creation.box(extents=(1, 1, 1))
    sphere = trimesh.creation.icosphere(radius=0.5)
    scene = trimesh.Scene([box, sphere])
    p = tmp_path / "twoobj.glb"
    scene.export(str(p))
    loaded = load_mesh(str(p))
    # Could be Scene or merged depending on trimesh version — either
    # is acceptable. is_scene() distinguishes.
    stats = mesh_stats(loaded)
    if is_scene(loaded):
        assert stats.kind == "scene"
        assert stats.object_count >= 1
    else:
        assert stats.kind == "mesh"
