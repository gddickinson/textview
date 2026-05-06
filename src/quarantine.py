"""File quarantine — safe storage for suspect files.

Layout:
    ~/.config/TextView/quarantine/
        <id>/
            <original_name>     # the file's bytes, mode 0600
            meta.json           # original_path / reason / scan / timestamp

`<id>` is the first 16 hex chars of `sha1(original_path + timestamp)` —
collision-resistant within a session and stable as a slug.

Restore puts the file back at its original path (or a target the user
chooses) and removes the quarantine entry.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


_ROOT = Path.home() / ".config" / "TextView" / "quarantine"


@dataclass
class QuarantineRecord:
    id: str
    original_path: str
    quarantined_path: str
    reason: str = ""
    quarantined_at_iso: str = ""
    findings: list[dict] = field(default_factory=list)

    def to_markdown_row(self) -> str:
        when = self.quarantined_at_iso[:19].replace("T", " ")
        risk = "—"
        sev = {f.get("severity") for f in self.findings}
        if "dangerous" in sev: risk = "⛔ dangerous"
        elif "warning" in sev: risk = "⚠ suspicious"
        return f"`{self.id}` · {when} · {risk} · `{self.original_path}` · {self.reason}"


def _entry_dir(qid: str) -> Path:
    return _ROOT / qid


def _ensure_root() -> None:
    _ROOT.mkdir(parents=True, exist_ok=True)


def _new_id(path: Path) -> str:
    seed = f"{path.resolve()}::{time.time_ns()}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:16]


def quarantine_file(path, *, reason: str = "",
                    scan: object | None = None) -> QuarantineRecord:
    """Move `path` into quarantine. Returns the record. Raises FileNotFoundError
    if the source doesn't exist; raises OSError on filesystem failures."""
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"not a file: {src}")
    _ensure_root()
    qid = _new_id(src)
    qdir = _entry_dir(qid); qdir.mkdir(parents=True, exist_ok=False)
    dest = qdir / src.name
    shutil.move(str(src), str(dest))
    try: os.chmod(dest, 0o600)       # tighten perms
    except OSError: pass
    findings: list[dict] = []
    if scan is not None and hasattr(scan, "findings"):
        findings = [
            {"severity": f.severity, "category": f.category,
             "description": f.description, "detail": f.detail}
            for f in scan.findings
        ]
    rec = QuarantineRecord(
        id=qid, original_path=str(src), quarantined_path=str(dest),
        reason=reason,
        quarantined_at_iso=time.strftime("%Y-%m-%dT%H:%M:%S",
                                          time.localtime()),
        findings=findings,
    )
    (qdir / "meta.json").write_text(
        json.dumps(asdict(rec), indent=2), encoding="utf-8")
    return rec


def restore_file(qid: str, target: str | None = None) -> str:
    """Move the quarantined file back to its original path (or `target`).
    Removes the quarantine entry on success. Returns the final path."""
    rec = _read(qid)
    if rec is None: raise FileNotFoundError(f"no quarantine entry: {qid}")
    src = Path(rec.quarantined_path)
    if not src.is_file():
        raise FileNotFoundError(f"quarantine file missing: {src}")
    dest = Path(target).expanduser() if target else Path(rec.original_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(
            f"refusing to overwrite existing file at restore target: {dest}. "
            f"Pass an alternate target.")
    shutil.move(str(src), str(dest))
    shutil.rmtree(_entry_dir(qid), ignore_errors=True)
    return str(dest)


def list_quarantined() -> list[QuarantineRecord]:
    if not _ROOT.is_dir(): return []
    out: list[QuarantineRecord] = []
    for d in sorted(_ROOT.iterdir()):
        if not d.is_dir(): continue
        rec = _read(d.name)
        if rec is not None: out.append(rec)
    return out


def delete_permanently(qid: str) -> bool:
    """Purge a quarantine entry from disk. Irreversible — caller must
    confirm. Returns True on success."""
    qdir = _entry_dir(qid)
    if not qdir.is_dir(): return False
    shutil.rmtree(qdir, ignore_errors=True)
    return not qdir.exists()


def _read(qid: str) -> QuarantineRecord | None:
    meta = _entry_dir(qid) / "meta.json"
    if not meta.is_file(): return None
    try:
        d = json.loads(meta.read_text(encoding="utf-8"))
    except Exception: return None
    try:
        return QuarantineRecord(
            id=d["id"], original_path=d["original_path"],
            quarantined_path=d["quarantined_path"],
            reason=d.get("reason", ""),
            quarantined_at_iso=d.get("quarantined_at_iso", ""),
            findings=d.get("findings", []),
        )
    except KeyError: return None


# Test seam — point _ROOT at a temp dir from tests via monkeypatch.
def set_root(p: Path) -> None:
    global _ROOT
    _ROOT = Path(p)
