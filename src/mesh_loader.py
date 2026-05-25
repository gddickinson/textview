"""3D mesh + scene reader.

Backed by **`trimesh`**, which handles `.stl` / `.obj` / `.ply` /
`.glb` / `.gltf` / `.dae` (Collada) / `.3mf` / `.off` / `.x3d` in
one package — MIT, pure Python, no native deps.

The pipeline mirrors the other binary loaders:

  - `is_supported(path)` — extension check.
  - `load_mesh(path)` → a `trimesh.Trimesh` or `trimesh.Scene`.
    Lazy-imports trimesh and re-raises any failure as
    `MeshReadError`.
  - `mesh_stats(mesh)` → a dict of vertex / face / bbox / volume /
    watertightness / scene-or-single info, suitable for display.
  - `render_preview_png(mesh, out_path, *, size=(800, 600))` →
    bytes / write a PNG of a matplotlib 3D rendering. Heavy meshes
    (> 50k faces) are decimated for the preview only — the
    underlying mesh isn't mutated.

The dedicated `MeshView(QWidget)` in `mesh_view.py` wraps the
matplotlib canvas + a stats sidebar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


MESH_EXTENSIONS = {
    ".stl", ".obj", ".ply", ".glb", ".gltf",
    ".dae", ".3mf", ".off", ".x3d",
}


# Cap on faces that get rendered in the matplotlib preview. Above
# this we decimate (preview only — the underlying mesh keeps its
# full resolution). 50k faces is enough for a decent preview and
# fast enough to render in <1 second on a laptop CPU.
_PREVIEW_FACE_CAP = 50_000


class MeshReadError(Exception):
    """Wraps every mesh-loading failure (missing dep, bad path,
    parse error, unsupported format)."""


# ---------------------------------------------------------- internals --

def _trimesh():
    try:
        import trimesh  # type: ignore
    except ImportError as e:
        raise MeshReadError(
            "3D mesh support needs trimesh. "
            "Install with `pip install trimesh`."
        ) from e
    return trimesh


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in MESH_EXTENSIONS


# ---------------------------------------------------------- load --

def load_mesh(path: str):
    """Read the mesh / scene at `path` via trimesh. Returns either
    a `trimesh.Trimesh` (single-mesh files) or a `trimesh.Scene`
    (multi-object scenes, common for `.glb` / `.gltf` / `.dae`).

    Raises `MeshReadError` for missing file, missing dep, or any
    parse failure. The caller can check `is_scene(...)` to dispatch."""
    src = Path(path)
    if not src.is_file():
        raise MeshReadError(f"Mesh file not found: {path}")
    trimesh = _trimesh()
    try:
        # `force=None` lets trimesh return Scene when appropriate.
        # `process=True` merges duplicate vertices and recomputes
        # normals — important for STL files, which write each face
        # as three independent vertices, so a cube has 36 vertices
        # instead of 8 and reports as not-watertight otherwise.
        loaded = trimesh.load(str(src), force=None, process=True)
    except Exception as e:
        raise MeshReadError(f"Could not parse 3D file: {e}") from e
    # trimesh.load is permissive with garbage — it can return an
    # empty Scene or a faceless Trimesh rather than raising. Surface
    # those as MeshReadError so downstream code doesn't crash on
    # zero-shape arrays.
    if loaded is None:
        raise MeshReadError("3D file produced no geometry.")
    if is_scene(loaded):
        if not getattr(loaded, "geometry", None):
            raise MeshReadError(
                "3D file has no geometry — empty or unparseable.")
    elif hasattr(loaded, "faces") and len(loaded.faces) == 0:
        raise MeshReadError(
            "3D file has no faces — empty or unparseable.")
    return loaded


def is_scene(loaded) -> bool:
    """True if `load_mesh` gave back a multi-object scene rather
    than a single mesh."""
    cls_name = type(loaded).__name__
    return cls_name == "Scene"


# ---------------------------------------------------------- stats --

@dataclass
class MeshStats:
    """Snapshot of the loaded mesh / scene — what the UI shows in
    the stats sidebar."""
    kind: str                       # "mesh" or "scene"
    vertex_count: int
    face_count: int
    object_count: int               # > 1 for scenes
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    extents: tuple[float, float, float]   # bbox dimensions
    volume: float | None            # None if not watertight / scene
    is_watertight: bool             # only meaningful for single meshes
    has_normals: bool
    has_colors: bool
    units: str                      # trimesh's detected/default units
    materials: list[str] = field(default_factory=list)


def mesh_stats(loaded) -> MeshStats:
    """Build a `MeshStats` from a `Trimesh` or `Scene`."""
    if is_scene(loaded):
        scene = loaded
        dumped = scene.dump(concatenate=True) if scene.geometry else None
        vc = int(dumped.vertices.shape[0]) if dumped is not None else 0
        fc = int(dumped.faces.shape[0]) if dumped is not None else 0
        obj_count = len(scene.geometry)
        bounds = scene.bounds
        materials = []
        for name, geom in scene.geometry.items():
            mat = getattr(getattr(geom, "visual", None), "material", None)
            if mat is not None:
                materials.append(f"{name}: {type(mat).__name__}")
        return MeshStats(
            kind="scene", vertex_count=vc, face_count=fc,
            object_count=obj_count,
            bbox_min=tuple(float(v) for v in (bounds[0] if bounds is not None else (0, 0, 0))),
            bbox_max=tuple(float(v) for v in (bounds[1] if bounds is not None else (0, 0, 0))),
            extents=tuple(float(v) for v in (
                scene.extents if scene.extents is not None else (0, 0, 0))),
            volume=None,        # volume on a scene is ambiguous
            is_watertight=bool(dumped.is_watertight) if dumped is not None else False,
            has_normals=bool(dumped is not None and hasattr(dumped, "vertex_normals")
                             and len(dumped.vertex_normals) > 0),
            has_colors=bool(dumped is not None and hasattr(dumped.visual, "vertex_colors")
                             and dumped.visual.vertex_colors is not None
                             and len(dumped.visual.vertex_colors) > 0),
            units=getattr(scene, "units", "") or "",
            materials=materials,
        )
    # Single Trimesh.
    mesh = loaded
    try:
        bbox_min = tuple(float(v) for v in mesh.bounds[0])
        bbox_max = tuple(float(v) for v in mesh.bounds[1])
        extents = tuple(float(v) for v in mesh.extents)
    except Exception:
        bbox_min = bbox_max = extents = (0.0, 0.0, 0.0)
    volume = None
    try:
        if mesh.is_watertight:
            volume = float(mesh.volume)
    except Exception:
        pass
    has_normals = False
    try:
        has_normals = (hasattr(mesh, "vertex_normals")
                       and mesh.vertex_normals is not None
                       and len(mesh.vertex_normals) > 0)
    except Exception:
        pass
    has_colors = False
    try:
        visual = getattr(mesh, "visual", None)
        if visual is not None:
            vc = getattr(visual, "vertex_colors", None)
            has_colors = vc is not None and len(vc) > 0
    except Exception:
        pass
    return MeshStats(
        kind="mesh",
        vertex_count=int(mesh.vertices.shape[0]) if hasattr(mesh, "vertices") else 0,
        face_count=int(mesh.faces.shape[0]) if hasattr(mesh, "faces") else 0,
        object_count=1,
        bbox_min=bbox_min, bbox_max=bbox_max, extents=extents,
        volume=volume,
        is_watertight=bool(getattr(mesh, "is_watertight", False)),
        has_normals=has_normals,
        has_colors=has_colors,
        units=getattr(mesh, "units", "") or "",
        materials=[],
    )


def stats_to_markdown(stats: MeshStats, *, filename: str = "") -> str:
    """Render a `MeshStats` as a Markdown summary — used by the
    side panel of `MeshView` and by the LLM `read_mesh` tool."""
    title = f"# 3D file: `{filename}`\n\n" if filename else "# 3D file\n\n"
    bits = [
        title,
        f"- **Kind**: {stats.kind}",
        f"- **Vertices**: {stats.vertex_count:,}",
        f"- **Faces**: {stats.face_count:,}",
    ]
    if stats.object_count != 1:
        bits.append(f"- **Objects**: {stats.object_count}")
    bits.append(
        f"- **Bounding box**: "
        f"({stats.bbox_min[0]:.3f}, {stats.bbox_min[1]:.3f}, {stats.bbox_min[2]:.3f}) "
        f"→ ({stats.bbox_max[0]:.3f}, {stats.bbox_max[1]:.3f}, {stats.bbox_max[2]:.3f})"
    )
    bits.append(
        f"- **Extents**: "
        f"{stats.extents[0]:.3f} × {stats.extents[1]:.3f} × {stats.extents[2]:.3f}"
    )
    if stats.volume is not None:
        bits.append(f"- **Volume**: {stats.volume:.4f} (watertight ✓)")
    else:
        ws = "watertight" if stats.is_watertight else "not watertight (open mesh)"
        bits.append(f"- **Volume**: not computed — {ws}")
    bits.append(f"- **Normals**: {'yes' if stats.has_normals else 'no'}")
    bits.append(f"- **Vertex colors**: {'yes' if stats.has_colors else 'no'}")
    if stats.units:
        bits.append(f"- **Units**: {stats.units}")
    if stats.materials:
        bits.append("\n**Materials**:")
        for m in stats.materials:
            bits.append(f"- {m}")
    return "\n".join(bits) + "\n"


# ---------------------------------------------------------- preview render --

def render_preview_png(loaded, out_path: str, *,
                        size: tuple[int, int] = (800, 600),
                        face_cap: int = _PREVIEW_FACE_CAP) -> str:
    """Render the mesh to a PNG via matplotlib's 3D backend.

    Heavy meshes (> `face_cap` faces) are decimated for the
    preview only — the underlying mesh isn't mutated. Multi-object
    scenes are concatenated to a single mesh for display.

    Returns the output path on success."""
    import numpy as np
    try:
        import matplotlib
        # Ensure the figure backend doesn't require an event loop.
        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError as e:
        raise MeshReadError(
            "Rendering needs matplotlib. Install with `pip install matplotlib`."
        ) from e

    trimesh = _trimesh()

    # Reduce a Scene to a single Trimesh for plotting.
    if is_scene(loaded):
        if not loaded.geometry:
            raise MeshReadError("Scene has no geometry to render.")
        mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded

    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        raise MeshReadError("Mesh has no faces — nothing to render.")

    # Decimate large meshes for preview.
    n_faces = int(mesh.faces.shape[0])
    if n_faces > face_cap:
        try:
            mesh = mesh.simplify_quadric_decimation(face_cap)
        except Exception:
            # Best-effort: if decimation isn't available (older
            # trimesh), just clip to the cap.
            mesh = mesh.copy()
            mesh.faces = mesh.faces[:face_cap]

    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    # Build the polygon collection.
    polys = vertices[faces]

    fig = plt.figure(figsize=(size[0] / 100.0, size[1] / 100.0), dpi=100)
    try:
        ax = fig.add_subplot(111, projection="3d")
        coll = Poly3DCollection(polys, alpha=0.85, edgecolor="#1f3a5f",
                                 facecolor="#7da4d9", linewidth=0.2)
        ax.add_collection3d(coll)

        # Equal-aspect bounding box.
        mn = vertices.min(axis=0); mx = vertices.max(axis=0)
        center = (mn + mx) / 2
        max_range = float((mx - mn).max() / 2)
        if max_range == 0: max_range = 1.0
        ax.set_xlim(center[0] - max_range, center[0] + max_range)
        ax.set_ylim(center[1] - max_range, center[1] + max_range)
        ax.set_zlim(center[2] - max_range, center[2] + max_range)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
        ax.view_init(elev=25, azim=-60)
        fig.tight_layout()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=100)
    finally:
        plt.close(fig)
    return out_path
