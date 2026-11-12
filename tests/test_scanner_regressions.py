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
