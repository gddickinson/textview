"""Coverage for src.cert_loader — supported extensions, key file
safe-display, openssl-CLI fallback path, file_loader integration.

The "actually parse a real cert" path is gated behind the `cryptography`
library; we generate a self-signed cert on the fly when that's
installed."""
from __future__ import annotations

import importlib
import shutil
import subprocess
import pytest
from pathlib import Path

from src.cert_loader import (
    CERT_EXTENSIONS, KEY_EXTENSIONS, ALL_EXTENSIONS,
    is_supported, render_markdown,
)


def _have(mod):
    try: importlib.import_module(mod); return True
    except Exception: return False


def test_is_supported():
    for ext in (".pem", ".crt", ".cer", ".der", ".key"):
        assert is_supported(f"x{ext}")
    assert not is_supported("x.txt")


def test_extension_sets_disjoint():
    assert ".pem" in CERT_EXTENSIONS
    assert ".key" in KEY_EXTENSIONS
    assert ALL_EXTENSIONS == CERT_EXTENSIONS | KEY_EXTENSIONS


def test_key_file_never_dumps_material(tmp_path):
    """Private-key files must not have the raw bytes in the rendered
    output — that's the whole reason this module exists."""
    key_body = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAyXyz...sensitive data we never want displayed...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    p = tmp_path / "secret.key"
    p.write_text(key_body)
    md = render_markdown(str(p))
    assert "sensitive data we never want displayed" not in md
    assert "MIIEowIBAAKCAQ" not in md
    assert "Private-key material is not displayed" in md
    assert "RSA PRIVATE KEY" in md  # type banner is fine


def test_key_file_reports_encryption_state(tmp_path):
    body = (
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\n"
        "BASE64...\n"
        "-----END ENCRYPTED PRIVATE KEY-----\n"
    )
    p = tmp_path / "enc.key"
    p.write_text(body)
    md = render_markdown(str(p))
    assert "Encrypted" in md


def test_invalid_file_path_gives_friendly_error(tmp_path):
    md = render_markdown(str(tmp_path / "no_such.pem"))
    assert "could not read file" in md or "No decoder" in md


def test_openssl_fallback_message(tmp_path, monkeypatch):
    """When cryptography isn't installed AND openssl isn't on PATH,
    the loader returns an install-hint markdown rather than crashing."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    # Force the cryptography import path to fail.
    import src.cert_loader as cl

    def boom(p, d):
        raise cl._BackendUnavailable()
    monkeypatch.setattr(cl, "_render_with_cryptography", boom)

    p = tmp_path / "cert.pem"
    p.write_bytes(b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
    md = render_markdown(str(p))
    assert "No decoder available" in md
    assert "pip install cryptography" in md or "openssl" in md


# -- with cryptography (skip if absent) ----------------------------------

@pytest.fixture
def self_signed_pem(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "TestCert"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TextView Tests"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(12345)
            .not_valid_before(now).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName("example.com"), x509.DNSName("*.example.com")]),
                critical=False)
            .sign(key, hashes.SHA256()))
    p = tmp_path / "cert.pem"
    p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return p


@pytest.mark.skipif(not _have("cryptography"), reason="cryptography not installed")
def test_cryptography_full_parse(self_signed_pem):
    md = render_markdown(str(self_signed_pem))
    assert "# Certificate" in md
    assert "## Subject" in md
    assert "## Issuer" in md
    assert "TestCert" in md
    assert "TextView Tests" in md
    assert "## Validity" in md
    assert "## Fingerprints" in md
    assert "SHA-1" in md and "SHA-256" in md
    assert "Subject Alternative Names" in md
    assert "example.com" in md
    # Public key block is present.
    assert "Public key" in md
    assert "2048 bits" in md or "RSA" in md


# -- openssl CLI fallback (skip when openssl not on PATH or crypto absent)

@pytest.mark.skipif(
    shutil.which("openssl") is None or not _have("cryptography"),
    reason="needs openssl on PATH and cryptography for fixture generation",
)
def test_openssl_fallback_renders_text(self_signed_pem, monkeypatch):
    """Force the cryptography path to fail, confirm openssl backup
    produces a `# Certificate:` markdown block with the openssl text."""
    import src.cert_loader as cl
    def fail(p, d):
        raise cl._BackendUnavailable()
    monkeypatch.setattr(cl, "_render_with_cryptography", fail)
    md = render_markdown(str(self_signed_pem))
    assert "# Certificate:" in md
    # openssl x509 -text output contains "Certificate:" and "Subject:"
    assert "Subject:" in md or "Issuer:" in md


# -- file_loader integration --------------------------------------------

@pytest.mark.skipif(not _have("cryptography"), reason="cryptography not installed")
def test_file_loader_routes_cert(self_signed_pem):
    from src.file_loader import detect_format, load_file
    assert detect_format(self_signed_pem) == "cert"
    content, encoding, fmt = load_file(str(self_signed_pem))
    assert fmt == "cert"
    assert "Certificate" in content
    assert "certificate report" in encoding


def test_file_loader_routes_key(tmp_path):
    """Even without cryptography, a .key file should produce a
    markdown report that never includes the key body."""
    body = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIE_secret_material_here\n"
        "-----END PRIVATE KEY-----\n"
    )
    p = tmp_path / "id.key"
    p.write_text(body)
    from src.file_loader import detect_format, load_file
    assert detect_format(p) == "cert"
    content, _, fmt = load_file(str(p))
    assert fmt == "cert"
    assert "MIIE_secret_material_here" not in content
    assert "PRIVATE KEY" in content
