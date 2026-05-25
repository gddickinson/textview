"""List + extract members of common archive formats.

Supported via stdlib alone:
  - **ZIP**: `.zip` / `.jar` / `.war` / `.apk` / `.ipa` (anything that's
    actually a ZIP — Java/Android packages are listed too).
  - **TAR family**: `.tar`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`,
    `.tar.xz` / `.txz`.

Supported when the optional reader is installed:
  - **7-Zip** `.7z` (needs `py7zr`); falls back to a friendly error.

A `.gz` / `.bz2` / `.xz` file that is *not* a tarball is treated as a
single-stream compressed text file by the regular text-load path
(out-of-scope for this module).

The high-level loader exposes:
  - `is_supported(path)` — extension check.
  - `list_members(path)` → list of `Member(name, size, compressed_size,
    mtime, is_dir)` dataclasses.
  - `render_listing_markdown(path)` — formatted markdown table for the
    rendered viewer.
  - `extract_member(path, member_name, dest_dir)` and
    `extract_all(path, dest_dir)` — extract helpers used by menu
    actions. Both refuse path-traversal entries (`..`, absolute paths)
    so a malicious archive can't write outside `dest_dir`.
"""
from __future__ import annotations

import io
import os
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Recognised by extension (compound extensions handled in `_kind`).
_ZIP_EXTS = {".zip", ".jar", ".war", ".apk", ".ipa", ".epub"}
_TAR_EXTS = {".tar", ".tgz", ".tbz2", ".txz", ".tb2"}
_SEVENZ_EXTS = {".7z"}


class ArchiveReadError(Exception):
    pass


@dataclass(frozen=True)
class Member:
    name: str
    size: int                  # uncompressed size, bytes
    compressed_size: int       # -1 when the format doesn't report it
    mtime: float               # POSIX seconds; 0 when unknown
    is_dir: bool


# ----------------------------------------------------------- detection --

def _kind(path) -> str | None:
    """Return "zip" | "tar" | "7z" | None based on extension. Handles
    the compound `.tar.gz` / `.tar.bz2` / `.tar.xz` cases."""
    name = Path(path).name.lower()
    # Compound tar extensions first.
    for double in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"):
        if name.endswith(double):
            return "tar"
    suffix = Path(name).suffix
    if suffix in _ZIP_EXTS: return "zip"
    if suffix in _TAR_EXTS: return "tar"
    if suffix in _SEVENZ_EXTS: return "7z"
    return None


def is_supported(path) -> bool:
    return _kind(path) is not None


def list_supported_extensions() -> list[str]:
    return sorted(_ZIP_EXTS | _TAR_EXTS | _SEVENZ_EXTS |
                  {".tar.gz", ".tar.bz2", ".tar.xz"})


# ----------------------------------------------------------- listing --

def list_members(path: str) -> list[Member]:
    kind = _kind(path)
    if kind == "zip":  return _zip_list(path)
    if kind == "tar":  return _tar_list(path)
    if kind == "7z":   return _sevenz_list(path)
    raise ArchiveReadError(f"Unsupported archive: {path}")


def _zip_list(path: str) -> list[Member]:
    try:
        with zipfile.ZipFile(path) as zf:
            out: list[Member] = []
            for info in zf.infolist():
                mtime = 0.0
                try:
                    mtime = datetime(*info.date_time).timestamp()
                except (ValueError, TypeError):
                    pass
                out.append(Member(
                    name=info.filename,
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    mtime=mtime,
                    is_dir=info.is_dir(),
                ))
            return out
    except (zipfile.BadZipFile, OSError) as e:
        raise ArchiveReadError(f"Bad ZIP archive: {e}") from e


def _tar_list(path: str) -> list[Member]:
    try:
        with tarfile.open(path, "r:*") as tf:
            out: list[Member] = []
            for info in tf.getmembers():
                out.append(Member(
                    name=info.name,
                    size=info.size if not info.isdir() else 0,
                    compressed_size=-1,
                    mtime=float(info.mtime),
                    is_dir=info.isdir(),
                ))
            return out
    except (tarfile.TarError, OSError) as e:
        raise ArchiveReadError(f"Bad TAR archive: {e}") from e


def _sevenz_list(path: str) -> list[Member]:
    try:
        import py7zr  # type: ignore
    except ImportError as e:
        raise ArchiveReadError(
            "Reading .7z archives requires `py7zr`. "
            "Install with `pip install py7zr`."
        ) from e
    try:
        with py7zr.SevenZipFile(path, mode="r") as sz:
            out: list[Member] = []
            for info in sz.list():
                out.append(Member(
                    name=info.filename,
                    size=int(info.uncompressed or 0),
                    compressed_size=int(info.compressed or -1),
                    mtime=info.creationtime.timestamp() if info.creationtime else 0.0,
                    is_dir=bool(info.is_directory),
                ))
            return out
    except Exception as e:
        raise ArchiveReadError(f"Bad 7z archive: {e}") from e


# ----------------------------------------------------------- markdown render --

def render_listing_markdown(path: str) -> str:
    """A markdown report — header + summary line + sortable table.

    Member counts > 5000 are truncated with a note so the rendered view
    doesn't choke on giant archives."""
    try:
        members = list_members(path)
    except ArchiveReadError as e:
        return f"# Archive\n\n**Error**: {e}\n"
    name = Path(path).name
    file_members = [m for m in members if not m.is_dir]
    total = sum(m.size for m in file_members)
    cap = 5000
    truncated = len(members) > cap
    show = members[:cap]
    lines = [f"# Archive: `{name}`", ""]
    lines.append(
        f"- **Members**: {len(file_members):,} file"
        f"{'s' if len(file_members) != 1 else ''}, "
        f"{sum(1 for m in members if m.is_dir):,} director"
        f"{'ies' if sum(1 for m in members if m.is_dir) != 1 else 'y'}"
    )
    lines.append(f"- **Uncompressed total**: {_humansize(total)}")
    lines.append(f"- **Format**: {_kind(path)}")
    lines.append("")
    if truncated:
        lines.append(f"> Listing truncated to first {cap:,} members of {len(members):,}.\n")
    lines.append("| Name | Size | Modified |")
    lines.append("| --- | ---: | --- |")
    for m in show:
        icon = "📁 " if m.is_dir else ""
        size = "—" if m.is_dir else _humansize(m.size)
        when = datetime.fromtimestamp(m.mtime).strftime("%Y-%m-%d %H:%M") if m.mtime else "—"
        # Escape pipes in member names so the markdown table stays valid.
        safe_name = m.name.replace("|", "\\|")
        lines.append(f"| {icon}`{safe_name}` | {size} | {when} |")
    return "\n".join(lines) + "\n"


def _humansize(n: int) -> str:
    if n < 0: return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024: return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ----------------------------------------------------------- extract --

def _safe_join(dest_dir: Path, member_name: str) -> Path:
    """Refuse path-traversal entries (absolute paths or `..` components)
    so a malicious archive can't write outside `dest_dir`."""
    if not member_name:
        raise ArchiveReadError("Empty member name.")
    p = Path(member_name)
    if p.is_absolute():
        raise ArchiveReadError(f"Refusing absolute path: {member_name!r}")
    parts = p.parts
    if any(part == ".." for part in parts):
        raise ArchiveReadError(f"Refusing path with '..': {member_name!r}")
    return dest_dir / p


def extract_member(path: str, member_name: str, dest_dir: str) -> str:
    """Extract one member to `dest_dir`. Returns the on-disk path of the
    extracted file."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = _safe_join(dest, member_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(path)
    if kind == "zip":
        with zipfile.ZipFile(path) as zf:
            with zf.open(member_name) as src, open(target, "wb") as dst:
                dst.write(src.read())
    elif kind == "tar":
        with tarfile.open(path, "r:*") as tf:
            f = tf.extractfile(member_name)
            if f is None:
                raise ArchiveReadError(f"Cannot extract {member_name!r} (directory or special file)")
            with open(target, "wb") as dst:
                dst.write(f.read())
    elif kind == "7z":
        try:
            import py7zr  # type: ignore
        except ImportError as e:
            raise ArchiveReadError("Need py7zr for .7z extraction.") from e
        with py7zr.SevenZipFile(path, mode="r") as sz:
            sz.extract(path=str(dest), targets=[member_name])
    else:
        raise ArchiveReadError(f"Unsupported archive: {path}")
    return str(target)


def extract_all(path: str, dest_dir: str) -> int:
    """Extract every member into `dest_dir`. Returns the count of files
    written. Refuses path-traversal members (skipped with no exception
    — we just don't write them and continue, so a single bad name
    doesn't abort a whole tarball extraction)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    kind = _kind(path)
    if kind == "zip":
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                try:
                    target = _safe_join(dest, info.filename)
                except ArchiveReadError:
                    continue
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True); continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                written += 1
    elif kind == "tar":
        with tarfile.open(path, "r:*") as tf:
            for info in tf.getmembers():
                try:
                    target = _safe_join(dest, info.name)
                except ArchiveReadError:
                    continue
                if info.isdir():
                    target.mkdir(parents=True, exist_ok=True); continue
                if not info.isfile():
                    continue  # skip symlinks / specials
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(info)
                if f is None: continue
                with open(target, "wb") as dst:
                    dst.write(f.read())
                written += 1
    elif kind == "7z":
        try:
            import py7zr  # type: ignore
        except ImportError as e:
            raise ArchiveReadError("Need py7zr for .7z extraction.") from e
        with py7zr.SevenZipFile(path, mode="r") as sz:
            sz.extractall(path=str(dest))
            written = len([m for m in sz.list() if not m.is_directory])
    else:
        raise ArchiveReadError(f"Unsupported archive: {path}")
    return written


# --------------------------------------------------- MainWindow glue --

def show_extract_member_picker(window) -> None:
    """**Archive → Extract member…** action. Lets the user pick one
    member by name and writes it next to the archive."""
    from PyQt6.QtWidgets import QInputDialog, QFileDialog, QMessageBox
    if window._current_format != "archive" or not window._current_path:
        window.statusBar().showMessage("Extract: no archive is open.", 5000)
        return
    members = getattr(window, "_archive_members", []) or []
    files = [m for m in members if not m.is_dir]
    if not files:
        window.statusBar().showMessage("Archive contains no files.", 4000)
        return
    names = [m.name for m in files]
    name, ok = QInputDialog.getItem(
        window, "Extract member",
        f"Choose a member of {Path(window._current_path).name}:",
        names, 0, True,  # editable so the user can search by typing
    )
    if not ok or not name: return
    dest = QFileDialog.getExistingDirectory(
        window, "Extract to folder", str(Path(window._current_path).parent))
    if not dest: return
    try:
        out = extract_member(window._current_path, name, dest)
    except ArchiveReadError as e:
        QMessageBox.warning(window, "Extract failed", str(e))
        return
    window.statusBar().showMessage(f"Extracted → {out}", 5000)


def show_extract_all(window) -> None:
    """**Archive → Extract all…** action."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    if window._current_format != "archive" or not window._current_path:
        window.statusBar().showMessage("Extract all: no archive is open.", 5000)
        return
    dest = QFileDialog.getExistingDirectory(
        window, "Extract entire archive to folder",
        str(Path(window._current_path).parent))
    if not dest: return
    try:
        n = extract_all(window._current_path, dest)
    except ArchiveReadError as e:
        QMessageBox.warning(window, "Extract failed", str(e))
        return
    window.statusBar().showMessage(f"Extracted {n} files → {dest}", 5000)
