"""Screenshot matrix harness — UX hardening tool.

Boots TextView headlessly, opens one fixture file per format family,
grabs a PNG of the rendered viewer, and writes a manifest CSV.

Output goes to `screenshots_matrix/` (overrideable with `--out`). The
manifest has one row per case with the columns `case,format,fixture,
mode,screenshot,notes`. Use this when you change theming / dock
layout / a viewer mode — diff the matrix against an earlier run to
spot alignment / contrast / dock-collision issues that the unit
tests don't catch.

Run:
    python tools/snapshot_matrix.py
    python tools/snapshot_matrix.py --out /tmp/ux
    python tools/snapshot_matrix.py --theme "Light"
    python tools/snapshot_matrix.py --keep-fixtures   # don't tmp-dir clean

The harness creates the fixtures it needs (XLSX, SQLite, ZIP, NPY,
parquet, etc.) so the same `tools/snapshot_matrix.py` works on any
checkout without a curated samples folder.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class Case:
    case_id: str
    description: str
    format_hint: str
    make: Callable[[Path], Path]  # writes the fixture, returns the path
    notes: str = ""


# ----------------------------------------------------------- fixture makers --

def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _make_markdown(d: Path) -> Path:
    return _write_text(d / "sample.md",
        "# Sample document\n\n"
        "A **paragraph** with *emphasis* and `inline code`.\n\n"
        "- one\n- two\n- three\n\n"
        "```python\nprint('hi')\n```\n"
    )


def _make_python(d: Path) -> Path:
    return _write_text(d / "sample.py",
        '"""Sample module."""\nimport sys\n\n'
        'def main() -> None:\n    print("hello", sys.argv)\n\n'
        'if __name__ == "__main__":\n    main()\n'
    )


def _make_csv(d: Path) -> Path:
    return _write_text(d / "sample.csv",
        "name,age,score\nAlice,30,92.5\nBob,25,85.0\nCarol,42,98.2\n"
    )


def _make_json(d: Path) -> Path:
    return _write_text(d / "sample.json",
        '{\n  "name": "TextView",\n  "version": "3.4",\n'
        '  "formats": ["md", "csv", "xlsx", "sqlite"]\n}\n'
    )


def _make_html(d: Path) -> Path:
    return _write_text(d / "sample.html",
        "<!doctype html><html><body><h1>Hello</h1>"
        "<p>HTML sample.</p></body></html>\n"
    )


def _make_latex(d: Path) -> Path:
    return _write_text(d / "sample.tex",
        "\\documentclass{article}\n\\begin{document}\n"
        "Sample LaTeX source.\n\\end{document}\n"
    )


def _make_xlsx(d: Path) -> Path:
    import openpyxl
    p = d / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Numbers"
    ws.append(["name", "score"])
    ws.append(["Alice", 92.5])
    ws.append(["Bob", 85.0])
    ws.append(["Carol", 98.2])
    sheet2 = wb.create_sheet("Cities")
    sheet2.append(["where", "count"])
    sheet2.append(["Boston", 3])
    wb.save(p); return p


def _make_sqlite(d: Path) -> Path:
    p = d / "sample.sqlite"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
        INSERT INTO people VALUES (1, 'Alice', 30), (2, 'Bob', 25), (3, 'Carol', 42);
        CREATE TABLE notes (id INTEGER, body TEXT);
        INSERT INTO notes VALUES (1, 'hi'), (2, 'there');
    """); conn.commit(); conn.close()
    return p


def _make_zip(d: Path) -> Path:
    p = d / "sample.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("readme.txt", "Hello from the archive.\n")
        zf.writestr("src/lib.py", "def hi():\n    return 'hi'\n")
        zf.writestr("docs/intro.md", "# Intro\n\nMarkdown inside.\n")
    return p


def _make_npy(d: Path) -> Path:
    import numpy as np
    p = d / "sample.npy"
    np.save(p, np.arange(20).reshape(5, 4))
    return p


def _make_npz(d: Path) -> Path:
    import numpy as np
    p = d / "sample.npz"
    np.savez(p, alpha=np.arange(10), beta=np.arange(8).reshape(4, 2))
    return p


def _make_parquet(d: Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq
    p = d / "sample.parquet"
    pq.write_table(pa.table({
        "name": ["Alice", "Bob", "Carol", "Dave"],
        "score": [92.5, 85.0, 98.2, 71.4],
    }), p)
    return p


def _make_hdf5(d: Path) -> Path:
    import h5py
    import numpy as np
    p = d / "sample.h5"
    with h5py.File(p, "w") as hf:
        hf.create_dataset("flat", data=np.arange(20))
        g = hf.create_group("nested")
        g.create_dataset("grid", data=np.arange(12).reshape(3, 4))
    return p


def _make_cert(d: Path) -> Optional[Path]:
    """Make a self-signed PEM cert. Skips when `cryptography` isn't
    installed."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from datetime import datetime, timedelta, timezone
    except ImportError:
        return None
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "TextView UX Test"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Snapshot matrix"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))
    p = d / "sample.pem"
    p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return p


def _maybe_system_font(_d: Path) -> Optional[Path]:
    """Pick an existing system TTF rather than synthesising one."""
    for cand in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if Path(cand).is_file():
            return Path(cand)
    return None


# ----------------------------------------------------------- case registry --

CASES: list[Case] = [
    Case("markdown",  "Markdown rendered view",          "markdown", _make_markdown),
    Case("python",    "Python source, syntax highlight", "python",   _make_python),
    Case("csv",       "CSV → sortable table",            "csv",      _make_csv),
    Case("json",      "JSON code view",                  "json",     _make_json),
    Case("html",      "HTML rendered view",              "html",     _make_html),
    Case("latex",     "LaTeX source (code view)",        "latex",    _make_latex),
    Case("xlsx",      "Excel → table view",              "xlsx",     _make_xlsx),
    Case("sqlite",    "SQLite → first-table view",       "sqlite",   _make_sqlite),
    Case("archive",   "Archive → tree view",             "archive",  _make_zip),
    Case("npy",       "NumPy 2D array → table",          "numpy",    _make_npy),
    Case("npz",       "NumPy multi-array bundle",        "numpy",    _make_npz),
    Case("parquet",   "Parquet → table",                 "parquet",  _make_parquet),
    Case("hdf5",      "HDF5 hierarchy → table",          "hdf5",     _make_hdf5),
    Case("cert",      "Self-signed cert markdown",       "cert",     _make_cert),
    Case("font",      "System font sample sheet",        "font",     _maybe_system_font),
]


# ----------------------------------------------------------- runner --

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UX hardening: screenshot matrix.")
    p.add_argument("--out", default="screenshots_matrix",
                   help="Output directory (default: ./screenshots_matrix).")
    p.add_argument("--theme",
                   help="Force a specific theme by name (e.g. 'Light').")
    p.add_argument("--keep-fixtures", action="store_true",
                   help="Don't delete the temp directory of generated fixtures.")
    return p.parse_args()


def _bootstrap_qt():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import PyQt6
    plugins = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    if plugins.is_dir():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH",
                              str(plugins / "platforms"))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
    # Importing WebEngine before QApplication is mandatory.
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401


def _shoot(window, path: Path, out: Path) -> bool:
    from src.exporter import screenshot_widget, render_pdf_page
    is_pdf = window._current_format == "pdf" and window._pdf.doc is not None
    if is_pdf:
        return render_pdf_page(window._pdf, 0, str(out), dpi=120)
    # Grab the active viewer widget rather than a fixed mode so
    # whatever the format routed to gets captured.
    return screenshot_widget(window.viewer.active_widget(), str(out))


def main() -> int:
    args = _parse_args()
    _bootstrap_qt()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = Path(tempfile.mkdtemp(prefix="textview_snapshot_"))

    from PyQt6.QtWidgets import QApplication
    app = QApplication([sys.argv[0]])  # noqa: F841 — kept alive
    from src.app import MainWindow
    window = MainWindow()
    window.resize(1280, 820)

    if args.theme:
        try:
            window.settings_manager.update("theme", args.theme)
        except Exception as e:
            print(f"WARN: could not set theme {args.theme!r}: {e}",
                  file=sys.stderr)

    # Disconnect the LaTeX QMessageBox bridge — headless QMessageBox
    # would block. (LaTeX compile isn't part of the matrix anyway, but
    # we leave the file open in code view so it doesn't matter.) The
    # security scanner used to false-positive on clean .xlsx files
    # because the extension-mismatch check listed only `.zip` as a
    # valid extension for kind=zip — fixed in security_scanner.py, so
    # we no longer need to disable the whole scanner here.
    try: window._latex.finished.disconnect(window._on_latex_finished)
    except TypeError: pass

    manifest_rows = [("case", "format", "fixture", "mode", "screenshot", "notes")]
    print(f"Output: {out_dir}\nFixtures: {fixture_dir}\n")
    for c in CASES:
        try:
            fixture = c.make(fixture_dir)
        except Exception as e:
            print(f"  SKIP {c.case_id:<12} (fixture build failed: {e})")
            manifest_rows.append((c.case_id, c.format_hint, "", "",
                                  "", f"fixture build failed: {e}"))
            continue
        if fixture is None:
            print(f"  SKIP {c.case_id:<12} (no fixture available)")
            manifest_rows.append((c.case_id, c.format_hint, "", "",
                                  "", "fixture unavailable"))
            continue
        # Open via MainWindow (security scan etc. all still run).
        try:
            window.open_file(str(fixture), confirm=False)
        except Exception as e:
            print(f"  FAIL {c.case_id:<12} open failed: {e}")
            manifest_rows.append((c.case_id, c.format_hint, str(fixture),
                                  "", "", f"open failed: {e}"))
            continue
        # Let the event loop tick so any deferred layout/render runs.
        app.processEvents()
        png = out_dir / f"{c.case_id}.png"
        ok = _shoot(window, fixture, png)
        mode = window.viewer.mode()
        if ok:
            size = png.stat().st_size
            print(f"  OK   {c.case_id:<12} mode={mode:<8} → {png.name} ({size:,}b)")
        else:
            print(f"  FAIL {c.case_id:<12} mode={mode}  screenshot returned False")
        manifest_rows.append((c.case_id, c.format_hint, str(fixture),
                              mode, png.name if ok else "", c.description))

    manifest = out_dir / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerows(manifest_rows)
    print(f"\nManifest → {manifest}")
    n_ok = sum(1 for r in manifest_rows[1:] if r[4])
    print(f"\n{n_ok} / {len(manifest_rows) - 1} cases captured.")

    if not args.keep_fixtures:
        shutil.rmtree(fixture_dir, ignore_errors=True)
    else:
        print(f"(fixtures kept at {fixture_dir})")
    return 0 if n_ok == len(manifest_rows) - 1 else 1


if __name__ == "__main__":
    sys.exit(main())
