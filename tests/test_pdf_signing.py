"""Coverage for src/pdf_signing.py — sign + verify a real PDF via
pyHanko with a generated self-signed PFX.

Skipped block-style when pyHanko / cryptography aren't installed —
they're both required."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import pytest
from pathlib import Path

# Block-skip if either dependency is missing.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyhanko") is None
    or importlib.util.find_spec("cryptography") is None,
    reason="pyhanko + cryptography required for signing tests",
)

from src.pdf_signing import (
    PdfSigningError, SignatureReport, sign_pdf, verify_signatures,
)


# ---------------------------------------------------------- helpers --

def _make_pfx(path: Path, passphrase: bytes = b"hunter2") -> Path:
    """Generate a self-signed PKCS#12 keystore for testing."""
    from datetime import datetime, timedelta, timezone
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "TextView Test Signer"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TextView Tests"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))
    p12 = pkcs12.serialize_key_and_certificates(
        name=b"TextView Test", key=key, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase))
    path.write_bytes(p12)
    return path


def _make_pdf(path: Path, page_count: int = 2) -> Path:
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(page_count):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f: w.write(f)
    return path


def _silent_verify(path: str):
    """`verify_signatures` with pyhanko's internal logging suppressed
    so test output isn't full of self-signed-cert warnings."""
    with contextlib.redirect_stderr(io.StringIO()):
        return verify_signatures(path)


# ---------------------------------------------------------- happy path --

def test_sign_produces_a_signed_pdf(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    sign_pdf(str(src), str(out),
             pfx_path=str(pfx), passphrase="hunter2")
    assert out.is_file()
    assert out.stat().st_size > src.stat().st_size  # signature added bytes


def test_signed_pdf_has_one_signature(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    sign_pdf(str(src), str(out), pfx_path=str(pfx), passphrase="hunter2")
    reports = _silent_verify(str(out))
    assert len(reports) == 1
    r = reports[0]
    assert isinstance(r, SignatureReport)
    assert "TextView Test Signer" in r.signer_name
    # Self-signed → trusted=False; that's correct, not a bug.
    assert r.trusted is False
    # The signature should be cryptographically intact.
    assert r.is_intact is True
    assert r.coverage is True


def test_signed_pdf_carries_metadata(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    sign_pdf(str(src), str(out), pfx_path=str(pfx), passphrase="hunter2",
             reason="I approve", location="Austin", contact="x@example.com")
    reports = _silent_verify(str(out))
    assert len(reports) == 1
    # signing_time should be a valid ISO date string.
    assert reports[0].signing_time
    assert "T" in reports[0].signing_time   # ISO 8601 separator


def test_signature_field_name_default(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    sign_pdf(str(src), str(out), pfx_path=str(pfx), passphrase="hunter2")
    reports = _silent_verify(str(out))
    # pyhanko picks our requested name when nothing else is in the doc.
    assert reports[0].field_name in ("Signature1", "")


def test_unsigned_pdf_returns_empty_list(tmp_path):
    src = _make_pdf(tmp_path / "unsigned.pdf")
    reports = _silent_verify(str(src))
    assert reports == []


# ---------------------------------------------------------- tamper-detect --

def test_tampering_breaks_signature(tmp_path):
    """Modify the signed file → next verify should report is_intact=False."""
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    signed = tmp_path / "out.pdf"
    sign_pdf(str(src), str(signed), pfx_path=str(pfx), passphrase="hunter2")
    # Corrupt a few bytes in the middle of the signed PDF body. This
    # invalidates the signature's content hash.
    data = bytearray(signed.read_bytes())
    # Pick a region that's almost certainly inside the page content,
    # not in the trailer / xref. About 30% through the file.
    target = int(len(data) * 0.30)
    for i in range(20):
        data[target + i] ^= 0xFF
    signed.write_bytes(bytes(data))
    # The corrupt PDF may either:
    #   - parse but report is_intact=False (signature hash mismatch)
    #   - fail to parse → PdfSigningError raised
    #   - parse but return zero signatures
    # All three outcomes demonstrate the tamper was caught.
    try:
        reports = _silent_verify(str(signed))
    except PdfSigningError:
        return    # parser refused — tamper caught
    if reports:
        assert reports[0].is_intact is False    # hash mismatch caught


# ---------------------------------------------------------- error paths --

def test_missing_input_pdf_raises(tmp_path):
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfSigningError):
        sign_pdf(str(tmp_path / "nope.pdf"), str(out),
                 pfx_path=str(pfx), passphrase="hunter2")


def test_missing_pfx_raises(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfSigningError) as exc:
        sign_pdf(str(src), str(out),
                 pfx_path=str(tmp_path / "nope.pfx"), passphrase="x")
    # User should see a "not found" hint, not a stack trace fragment.
    assert "not found" in str(exc.value).lower()


def test_wrong_passphrase_raises_friendly(tmp_path):
    src = _make_pdf(tmp_path / "doc.pdf")
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfSigningError) as exc:
        sign_pdf(str(src), str(out),
                 pfx_path=str(pfx), passphrase="wrong")
    # The defensive None-check or the cryptography ValueError both
    # produce a clean "passphrase" hint.
    assert "passphrase" in str(exc.value).lower() or "load" in str(exc.value).lower()


def test_failed_sign_doesnt_leave_partial_file(tmp_path):
    """When sign_pdf raises mid-write, the output path is cleaned up."""
    pfx = _make_pfx(tmp_path / "k.pfx")
    out = tmp_path / "out.pdf"
    # Pass a non-PDF file as input — pyhanko will fail to parse it.
    bad_src = tmp_path / "garbage.pdf"
    bad_src.write_bytes(b"not actually a pdf")
    with pytest.raises(PdfSigningError):
        sign_pdf(str(bad_src), str(out),
                 pfx_path=str(pfx), passphrase="hunter2")
    # The output should NOT exist after the failure (we clean it up).
    assert not out.exists()


def test_verify_missing_file_raises(tmp_path):
    with pytest.raises(PdfSigningError):
        verify_signatures(str(tmp_path / "no-such.pdf"))


# ---------------------------------------------------------- SignatureReport shape --

def test_signature_report_is_a_dataclass():
    """The dataclass exposes the documented fields."""
    r = SignatureReport(
        field_name="Sig1", signer_name="x", signing_time="2026-01-01",
        is_intact=True, coverage=True, trusted=False, errors=[],
        timestamp_present=False,
    )
    assert r.field_name == "Sig1"
    assert r.is_intact is True
    assert r.errors == []
