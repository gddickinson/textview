"""Screenshot-matrix harness for UX hardening.

Walks an opinionated subset of (viewer-mode × theme × dock-state) and
emits one PNG per combination plus a `manifest.csv` and an
`UX_REPORT.md` with each shot embedded.

Design choices:

- **Subset, not Cartesian product.** The full matrix would be 8 views ×
  3 themes × 7 dock toggles = ~3000 shots. We sample ~25–30: every
  view in 3 themes, plus a "kitchen sink" all-docks shot per theme,
  plus a few dialog snapshots.
- **One MainWindow per theme.** Theme is live; we open files in the
  same window to amortize the heavy QtWebEngine boot.
- **Headless.** Sets `QT_QPA_PLATFORM=offscreen` and
  `AA_ShareOpenGLContexts` before `QApplication`.

Run via `python3 -m src.ux_screenshots` from the project root, or
import `run(out_dir)` from a notebook / test runner.
"""
import csv
import os
import sys
import time
from pathlib import Path


_THEMES = ["Solarized Dark", "Light", "Dracula"]


# Each entry:  (view_id, file_to_open, dock_setup_fn, caption)
# `dock_setup_fn(w)` is run on the live window before the screenshot —
# it should set tab focus, show/hide docks, etc.
_VIEWS = [
    ("code",       "sample_files/example.py",   None,
     "Code view (Python with Pygments highlighting)"),
    ("markdown",   "sample_files/example.md",   None,
     "Markdown rendered to HTML"),
    ("pdf",        "sample_files/example.pdf",  None,
     "PDF native render"),
    ("docx",       "sample_files/example.docx", None,
     "DOCX rendered via mammoth"),
    ("table",      "sample_files/example.csv",  "spreadsheet",
     "CSV → table view + filter bar + spreadsheet panel"),
    ("json",       "sample_files/example.json", None,
     "JSON syntax-highlighted"),
    ("image",      "sample_files/example.png",  "image",
     "Image view + adjustments panel"),
    ("welcome",    None, None,
     "Welcome screen (markdown render)"),
    ("kitchen",    "sample_files/example.csv",  "all_docks",
     "Kitchen sink — every dock visible"),
]


# Each dialog: (id, factory(window) → dialog, caption)
# Only dialogs we can construct without `exec()` (modal blocking) are
# safe to capture from offscreen mode.
_DIALOGS = [
    ("stats",   lambda w: _stats_dlg(w),
     "Per-column stats (numeric + text columns)"),
    ("plot",    lambda w: _plot_dlg(w),
     "Plot dialog with a Bar chart of score-by-name pre-selected"),
    ("palette", lambda w: _palette_dlg(w),
     "Command palette (every action) Ctrl+K"),
    ("qopen",   lambda w: _qopen_dlg(w),
     "Quick-open file picker Ctrl+P"),
    ("pivot",   lambda w: _pivot_dlg(w),
     "Pivot / group-by dialog"),
]


def _stats_dlg(w):
    from .stats_dialog import StatsDialog
    w.api.open("sample_files/example.csv")
    m = w.viewer.table_view.model()
    d = StatsDialog(m, w)
    d.resize(960, 360)
    return d


def _plot_dlg(w):
    from .plot_dialog import PlotDialog
    w.api.open("sample_files/example.csv")
    m = w.viewer.table_view.model()
    d = PlotDialog(m, w)
    d.resize(1000, 600)
    d.combo_type.setCurrentText("Bar")
    d.combo_x.setCurrentIndex(1)
    for ci, cb in d.y_checks:
        cb.setChecked(ci == 3)
    d.le_title.setText("score by name")
    d._plot()
    return d


def _palette_dlg(w):
    from .command_palette import build_command_palette
    return build_command_palette(w)


def _qopen_dlg(w):
    from .quick_open import build_quick_open
    # quick_open needs the project panel to point somewhere sensible; use
    # the project root so we get a real list. This is what ProjectPanel
    # opens to by default in a real run.
    from pathlib import Path
    w.project_panel.set_root(str(Path.cwd()))
    return build_quick_open(w)


def _pivot_dlg(w):
    from .pivot_dialog import PivotDialog
    w.api.open("sample_files/example.csv")
    m = w.viewer.table_view.model()
    d = PivotDialog(m, w)
    return d


def _setup_dock(w, mode: str | None):
    """Show/hide docks per `mode` and return a short label for the
    manifest."""
    docks = {
        "config":      w.config_panel,
        "metadata":    w.metadata_panel,
        "chat":        w.chat_panel,
        "project":     w.project_panel,
        "image":       w.image_panel,
        "spreadsheet": w.spreadsheet_panel,
        "terminal":    w.terminal_dock,
    }
    for d in docks.values():
        d.hide()
    if mode == "spreadsheet":
        w.spreadsheet_panel.show()
        return "spreadsheet"
    if mode == "image":
        w.image_panel.show()
        return "image"
    if mode == "all_docks":
        for d in docks.values():
            d.show()
        return "all"
    return "none"


def run(out_dir: str | Path = "/tmp/textview_ux"):
    """Render the full matrix into `out_dir`. Returns the manifest list
    (one dict per row)."""
    # Force offscreen so this can be imported from a regular shell too.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import PyQt6
    plugins = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    os.environ.setdefault(
        "QT_QPA_PLATFORM_PLUGIN_PATH", str(plugins / "platforms"))
    os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))

    from PyQt6 import QtWebEngineWidgets  # noqa: F401
    from PyQt6.QtCore import Qt, QSettings, QEventLoop, QDeadlineTimer
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    QSettings().clear()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    app = QApplication.instance() or QApplication(sys.argv)
    from src.app import MainWindow
    from src.exporter import screenshot_widget

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []

    for theme in _THEMES:
        # New window per theme so the heavy state (web view, runner) gets
        # a fresh start. Slow but reliable.
        w = MainWindow()
        w.resize(1280, 760)
        w.show()
        app.processEvents()
        w.api.set_theme(theme)
        app.processEvents()
        time.sleep(0.2)  # let the theme cascade

        for view_id, path, mode, caption in _VIEWS:
            if path is None:
                # Welcome — explicitly invoke the menu action.
                w._show_welcome()
            else:
                w.api.open(path)
            app.processEvents()
            dock_label = _setup_dock(w, mode)
            app.processEvents()
            time.sleep(0.15)
            stem = f"{view_id}__{theme.replace(' ', '_')}"
            png = out / f"{stem}.png"
            screenshot_widget(w, str(png))
            manifest.append({
                "view": view_id,
                "theme": theme,
                "docks": dock_label,
                "caption": caption,
                "file": path or "(welcome)",
                "screenshot": png.name,
            })
            print(f"  ✓ {png.name}", flush=True)

        # Dialogs (per-theme).
        for dlg_id, factory, caption in _DIALOGS:
            try:
                dlg = factory(w)
                if dlg is None:
                    continue
                dlg.show()
                app.processEvents()
                time.sleep(0.2)
                stem = f"dialog_{dlg_id}__{theme.replace(' ', '_')}"
                png = out / f"{stem}.png"
                screenshot_widget(dlg, str(png))
                manifest.append({
                    "view": f"dialog:{dlg_id}",
                    "theme": theme, "docks": "—",
                    "file": "(dialog)",
                    "caption": caption,
                    "screenshot": png.name,
                })
                print(f"  ✓ {png.name}", flush=True)
                dlg.close(); dlg.deleteLater()
            except Exception as e:
                print(f"  ✗ dialog {dlg_id}: {e}", flush=True)

        w.close()
        del w
        app.processEvents()

    # Write manifest.
    manifest_path = out / "manifest.csv"
    with manifest_path.open("w", newline="") as f:
        wr = csv.DictWriter(
            f, fieldnames=["view", "theme", "docks", "file",
                           "caption", "screenshot"])
        wr.writeheader()
        for row in manifest:
            wr.writerow(row)

    # Write UX_REPORT.md scaffold with embedded shots.
    report = out / "UX_REPORT.md"
    _write_report(report, manifest, out)

    return manifest


def _write_report(report: Path, manifest: list[dict], out_dir: Path):
    lines = [
        "# TextView UX report",
        "",
        f"Generated by `src/ux_screenshots.py`. {len(manifest)} screenshots.",
        "",
        "Each section embeds the shot and leaves a **Findings** stub for "
        "review. Mark a row resolved by replacing the placeholder with "
        "the fix or `wontfix: <reason>`.",
        "",
        "## Matrix overview",
        "",
        "| view | theme | docks | file |",
        "| --- | --- | --- | --- |",
    ]
    for row in manifest:
        lines.append(
            f"| `{row['view']}` | {row['theme']} | {row['docks']} | "
            f"`{row['file']}` |")

    # Per-view section, themes side by side as a table of images
    by_view: dict[str, list[dict]] = {}
    for row in manifest:
        by_view.setdefault(row["view"], []).append(row)

    for view_id, rows in by_view.items():
        lines.append("")
        lines.append(f"## {view_id} — {rows[0]['caption']}")
        lines.append("")
        # 3 columns of images, one per theme
        lines.append("| " + " | ".join(r["theme"] for r in rows) + " |")
        lines.append("| " + " | ".join("---" for _ in rows) + " |")
        lines.append("| " + " | ".join(
            f"![{r['theme']}]({r['screenshot']})" for r in rows) + " |")
        lines.append("")
        lines.append("**Findings:** _TODO: review_")

    report.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/textview_ux"
    print(f"writing to {out}")
    rows = run(out)
    print(f"\n{len(rows)} shots written, manifest: {out}/manifest.csv, "
          f"report: {out}/UX_REPORT.md")
