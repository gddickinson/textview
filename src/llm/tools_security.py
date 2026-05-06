"""LLM tools for security: scan, list/quarantine/restore.

Read-only:
    scan_file(path, run_clamav=False)
    list_quarantined()

Action (chat-panel "Allow actions"):
    quarantine_file(path, reason)
    restore_quarantined(qid, target?)

Action + extra settings gate (`agent_can_purge_quarantine`):
    delete_quarantined(qid) — irreversible.
"""
from __future__ import annotations
import json

from .tools_base import Tool


# ---- read-only ----------------------------------------------------------

def _scan_file(window, path: str, run_clamav: bool = False) -> str:
    from ..security_scanner import scan_file
    if not path: return "ERROR: provide `path`."
    try:
        sr = scan_file(path, run_clamav=bool(run_clamav))
    except Exception as e:
        return f"ERROR: scan failed: {e}"
    return json.dumps({
        "path": sr.path,
        "risk_level": sr.risk_level,
        "detected_kind": sr.detected_kind,
        "findings": [
            {"severity": f.severity, "category": f.category,
             "description": f.description, "detail": f.detail}
            for f in sr.findings
        ],
    }, indent=2)


def _list_quarantined(window) -> str:
    from .. import quarantine as q
    items = q.list_quarantined()
    if not items: return "(no quarantined files)"
    out = [f"{len(items)} quarantined file(s):"]
    for r in items:
        sev = {f.get("severity") for f in r.findings}
        risk = ("dangerous" if "dangerous" in sev
                else "suspicious" if "warning" in sev else "unknown")
        out.append(f"  {r.id}  [{risk}]  {r.original_path}")
        if r.reason: out.append(f"    reason: {r.reason}")
    return "\n".join(out)


# ---- action: quarantine + restore --------------------------------------

def _quarantine_file(window, path: str, reason: str = "") -> str:
    from .. import quarantine as q
    from ..security_scanner import scan_file
    if not path: return "ERROR: provide `path`."
    try:
        sr = scan_file(path)
        rec = q.quarantine_file(path, reason=reason or
                                f"agent quarantine ({sr.risk_level})", scan=sr)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    except OSError as e:
        return f"ERROR: filesystem error: {e}"
    return (f"Quarantined `{rec.original_path}` → `{rec.quarantined_path}`\n"
            f"Quarantine id: {rec.id}")


def _restore_quarantined(window, qid: str, target: str = "") -> str:
    from .. import quarantine as q
    if not qid: return "ERROR: provide `qid`."
    try:
        path = q.restore_file(qid, target=target or None)
    except FileExistsError as e:
        return f"ERROR: {e}"
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    except OSError as e:
        return f"ERROR: filesystem error: {e}"
    return f"Restored → {path}"


def _delete_quarantined(window, qid: str) -> str:
    """Irreversible. Gated by `agent_can_purge_quarantine` — without
    that flag, returns an error telling the agent to ask the user."""
    d = window.settings_manager.display
    if not getattr(d, "agent_can_purge_quarantine", False):
        return ("ERROR: permanent purge is disabled. The user must enable "
                "`agent_can_purge_quarantine` in the Configuration panel "
                "first. (Quarantine purge is irreversible — this gate is "
                "intentionally separate from the chat 'Allow actions' "
                "checkbox.) Suggest using `restore_quarantined` to a temp "
                "directory instead, then deleting via the OS file manager.")
    from .. import quarantine as q
    if not qid: return "ERROR: provide `qid`."
    if q.delete_permanently(qid): return f"Purged {qid}."
    return f"ERROR: no quarantine entry {qid!r}."


# ---- registration -----------------------------------------------------

SECURITY_TOOLS_RO: list[Tool] = [
    Tool(name="scan_file",
         description="Run a heuristic + (optional) ClamAV scan against "
                     "`path`. Returns risk level (clean / suspicious / "
                     "dangerous), detected kind, and a list of findings "
                     "with severity. Use this when the user asks 'is this "
                     "file safe' or before running an unfamiliar script.",
         input_schema={"type": "object",
                       "properties": {
                           "path": {"type": "string"},
                           "run_clamav": {"type": "boolean"},
                       },
                       "required": ["path"]},
         call=_scan_file),
    Tool(name="list_quarantined",
         description="List every file the user (or the agent) has moved "
                     "into quarantine, with their original paths, scan "
                     "reasons, and risk levels.",
         input_schema={"type": "object", "properties": {}, "required": []},
         call=_list_quarantined),
]


SECURITY_TOOLS_ACTION: list[Tool] = [
    Tool(name="quarantine_file",
         description="Move `path` into the quarantine directory, recording "
                     "a reason + the current scan results. The original "
                     "location becomes empty. Use this when the user wants "
                     "a suspect file set aside without deleting it. Reversible "
                     "via `restore_quarantined`.",
         input_schema={"type": "object",
                       "properties": {
                           "path": {"type": "string"},
                           "reason": {"type": "string"},
                       },
                       "required": ["path"]},
         call=_quarantine_file, destructive=True),
    Tool(name="restore_quarantined",
         description="Move a quarantined file back to its original path "
                     "(or to `target` if provided). Removes the quarantine "
                     "entry. Refuses to overwrite an existing file at the "
                     "destination — pass an alternate `target` instead.",
         input_schema={"type": "object",
                       "properties": {
                           "qid": {"type": "string"},
                           "target": {"type": "string"},
                       },
                       "required": ["qid"]},
         call=_restore_quarantined, destructive=True),
    Tool(name="delete_quarantined",
         description="Permanently remove a quarantine entry from disk. "
                     "Irreversible. Gated by `agent_can_purge_quarantine` "
                     "in addition to the chat-panel 'Allow actions' "
                     "checkbox — without that flag, returns an error.",
         input_schema={"type": "object",
                       "properties": {"qid": {"type": "string"}},
                       "required": ["qid"]},
         call=_delete_quarantined, destructive=True),
]
