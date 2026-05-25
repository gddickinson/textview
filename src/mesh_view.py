"""3D mesh viewer widget — embeds a matplotlib 3D canvas plus a
stats sidebar.

Wired into `TextViewer` as `MODE_MESH`. `MainWindow.open_file`
detects format == `"mesh"`, calls `MeshView.load(path)`, which
invokes `mesh_loader.load_mesh` + `mesh_stats` and renders a
preview into the embedded matplotlib `FigureCanvasQTAgg`.

Interaction:
  - matplotlib's built-in 3D viewer responds to mouse drag for
    rotate / pan / zoom (via the `NavigationToolbar2QT`).
  - The right-hand panel shows the Markdown stats from
    `stats_to_markdown`.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTextBrowser,
    QSizePolicy, QLabel,
)


class MeshView(QWidget):
    """Embedded 3D mesh viewer + stats sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = None
        self._stats = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: matplotlib canvas (built on first load — matplotlib
        # is heavy to import, defer it).
        self._canvas_holder = QWidget(split)
        self._canvas_layout = QVBoxLayout(self._canvas_holder)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(
            "Open a 3D file (.stl / .obj / .ply / .glb / .gltf / .dae / .3mf / .off / .x3d) to preview.",
            self._canvas_holder,
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._canvas_layout.addWidget(self._placeholder, 1)
        self._canvas = None
        self._toolbar = None
        self._figure = None

        # Right: stats panel.
        self._stats_panel = QTextBrowser(split)
        self._stats_panel.setFrameShape(self._stats_panel.Shape.NoFrame)
        self._stats_panel.setOpenExternalLinks(True)

        split.addWidget(self._canvas_holder)
        split.addWidget(self._stats_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)

    # ---- public API -----------------------------------------------------

    def load(self, path: str) -> bool:
        """Load and render the mesh at `path`. Returns True on success.
        Errors are surfaced into the stats panel as a markdown report
        so the user sees what went wrong without a modal popup."""
        from .mesh_loader import (
            load_mesh, mesh_stats, stats_to_markdown, MeshReadError,
        )
        try:
            self._loaded = load_mesh(path)
            self._stats = mesh_stats(self._loaded)
        except MeshReadError as e:
            self.clear()
            self._stats_panel.setMarkdown(
                f"# 3D file\n\n**Error**: {e}\n")
            return False

        self._render_canvas()
        self._stats_panel.setMarkdown(
            stats_to_markdown(self._stats, filename=Path(path).name))
        return True

    def clear(self) -> None:
        self._loaded = None
        self._stats = None
        if self._canvas is not None:
            self._canvas.deleteLater()
            self._canvas = None
        if self._toolbar is not None:
            self._toolbar.deleteLater()
            self._toolbar = None
        self._figure = None
        self._placeholder.show()
        self._stats_panel.setMarkdown("")

    # ---- rendering ------------------------------------------------------

    def _render_canvas(self) -> None:
        """Build (or rebuild) the embedded matplotlib figure showing
        the current mesh."""
        try:
            import numpy as np
            import matplotlib
            matplotlib.use("QtAgg", force=False)
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import (
                FigureCanvasQTAgg, NavigationToolbar2QT,
            )
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        except ImportError:
            self._stats_panel.setMarkdown(
                "# Rendering failed\n\n"
                "matplotlib is required to render the 3D preview.")
            return

        from .mesh_loader import is_scene
        loaded = self._loaded
        if loaded is None:
            return

        # Reduce a Scene to one mesh for plotting; rebuild the figure
        # so re-loads don't accumulate axes.
        if is_scene(loaded):
            if not getattr(loaded, "geometry", None):
                self._placeholder.show()
                return
            mesh = loaded.dump(concatenate=True)
        else:
            mesh = loaded
        if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
            self._placeholder.show()
            return

        # Decimate big meshes for the embedded preview.
        cap = 50_000
        n = int(mesh.faces.shape[0])
        if n > cap:
            try:
                mesh = mesh.simplify_quadric_decimation(cap)
            except Exception:
                mesh = mesh.copy()
                mesh.faces = mesh.faces[:cap]

        vertices = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.faces)
        polys = vertices[faces]

        # Fresh figure + canvas every load (cheaper than reusing).
        if self._canvas is not None:
            self._canvas.deleteLater()
            self._canvas = None
        if self._toolbar is not None:
            self._toolbar.deleteLater()
            self._toolbar = None
        self._figure = Figure(figsize=(6, 5))
        ax = self._figure.add_subplot(111, projection="3d")
        coll = Poly3DCollection(polys, alpha=0.85, edgecolor="#1f3a5f",
                                 facecolor="#7da4d9", linewidth=0.2)
        ax.add_collection3d(coll)
        mn = vertices.min(axis=0); mx = vertices.max(axis=0)
        center = (mn + mx) / 2
        max_range = float((mx - mn).max() / 2) or 1.0
        ax.set_xlim(center[0] - max_range, center[0] + max_range)
        ax.set_ylim(center[1] - max_range, center[1] + max_range)
        ax.set_zlim(center[2] - max_range, center[2] + max_range)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
        ax.view_init(elev=25, azim=-60)
        self._figure.tight_layout()

        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas, self._canvas_holder)
        self._placeholder.hide()
        self._canvas_layout.addWidget(self._toolbar)
        self._canvas_layout.addWidget(self._canvas, 1)
        self._canvas.draw()
