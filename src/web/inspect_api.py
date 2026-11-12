"""Unknown-file inspector + security scan for an uploaded file (POST /api/inspect).

Runs TextView's own `file_inspector.inspect_file` and `security_scanner.scan_file` on a temporary copy, plus
`file_loader.detect_format` (would the desktop app open it natively, and in which viewer?) and the bundled
file-format database entry. The temporary path, mtime and the macOS quarantine-xattr finding are dropped: they
describe the server's temp copy, not the user's file.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..file_inspector import inspect_file, looks_binary
from ..file_loader import FILENAME_MAP, FORMAT_MAP, detect_format
from ..security_scanner import scan_file
from .catalog import bundled_entries
from .samples import view_kind


def native_format(name: str) -> str | None:
    """detect_format() falls back to "plain" for unknown names; report None in that case."""
    p = Path(name)
    if p.name.lower() in FILENAME_MAP or p.suffix in FORMAT_MAP or p.suffix.lower() in FORMAT_MAP:
        return detect_format(p)
    low = p.name.lower()
    if any(low.endswith(c) for c in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")):
        return "archive"
    return None


def db_entry_id(name: str, kind: str) -> str | None:
    entries = bundled_entries()
    ext = Path(name).suffix.lower()
    for e in entries:
        if ext and ext in e.extensions:
            return e.id
    for e in entries:
        if name.lower() in e.filenames:
            return e.id
    return next((e.id for e in entries if e.id == kind), None)


def inspect_upload(name: str, data: bytes) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / name
        p.write_bytes(data)
        info = inspect_file(p).to_dict()
        scan = scan_file(p)
    for k in ("path", "mtime_iso"):
        info.pop(k, None)
    findings = [{"severity": f.severity, "category": f.category, "description": f.description, "detail": f.detail}
                for f in scan.findings if f.category != "macos_quarantine"]
    sev = {f["severity"] for f in findings}
    risk = "dangerous" if "dangerous" in sev else "suspicious" if "warning" in sev else "clean"
    fmt = native_format(name)
    return {"name": name, "info": info, "binary": looks_binary(data[:4096]),
            "native_format": fmt, "native_view": view_kind(fmt) if fmt else None,
            "scan": {"risk": risk, "findings": findings}, "db_entry": db_entry_id(name, info["detected_kind"])}
