"""Decode + display X.509 certificates and PEM-encoded keys.

`.pem` / `.crt` / `.cer` / `.der` / `.key` files become a markdown
report covering subject, issuer, validity window, fingerprints, SANs,
key type + size, and signature algorithm. The report renders through
the existing markdown pipeline so themes / search / copy all just
work.

Two backends, picked at call time:

1. **`cryptography`** (preferred) — rich parsing without spawning a
   subprocess. Adds it to `requirements.txt` as a soft dep is up to
   the user.
2. **`openssl` CLI** (fallback) — shells out to `openssl x509 -in PATH
   -text -noout` and captures the stdout verbatim. Works on every
   system that has openssl on PATH (every Mac, every Linux).

Private keys (`.key`) are decoded for **type + size only** — the raw
key material is **never** included in the report. This protects the
user from accidentally screenshotting a private key.
"""
from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path


CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".der"}
KEY_EXTENSIONS = {".key"}
ALL_EXTENSIONS = CERT_EXTENSIONS | KEY_EXTENSIONS


class CertReadError(Exception):
    pass


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in ALL_EXTENSIONS


def render_markdown(path: str) -> str:
    """Top-level dispatch. Returns a markdown report for the file."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        data = p.read_bytes()
    except OSError as e:
        return f"# Certificate\n\n**Error**: could not read file: {e}\n"

    if suffix in KEY_EXTENSIONS:
        return _render_key(p, data)
    # Try the cryptography backend; fall back to openssl CLI.
    try:
        return _render_with_cryptography(p, data)
    except _BackendUnavailable:
        pass
    if shutil.which("openssl"):
        return _render_with_openssl(p)
    return (
        f"# Certificate: `{p.name}`\n\n"
        "**No decoder available.** Install one of:\n\n"
        "- `pip install cryptography` (preferred — rich parsing)\n"
        "- An `openssl` binary on PATH (fallback)\n"
    )


# ----------------------------------------------------------- internals --

class _BackendUnavailable(Exception):
    pass


def _render_with_cryptography(p: Path, data: bytes) -> str:
    """Rich parse via `cryptography`. Raises `_BackendUnavailable` if
    the library isn't installed so the caller can try the next backend."""
    try:
        from cryptography import x509  # type: ignore
        from cryptography.hazmat.primitives import hashes, serialization  # type: ignore
    except ImportError as e:
        raise _BackendUnavailable() from e

    # PEM may contain multiple certs concatenated; load just the first.
    try:
        if data.lstrip().startswith(b"-----BEGIN"):
            cert = x509.load_pem_x509_certificate(data)
        else:
            cert = x509.load_der_x509_certificate(data)
    except ValueError as e:
        raise CertReadError(f"Could not parse certificate: {e}") from e

    out: list[str] = [f"# Certificate: `{p.name}`", ""]
    out.append("## Subject")
    out.append(_format_name(cert.subject))
    out.append("\n## Issuer")
    out.append(_format_name(cert.issuer))
    out.append("\n## Validity")
    out.append(f"- **Not before**: {cert.not_valid_before_utc.isoformat()}")
    out.append(f"- **Not after**: {cert.not_valid_after_utc.isoformat()}")

    out.append("\n## Public key")
    pk = cert.public_key()
    out.append(f"- **Algorithm**: {pk.__class__.__name__}")
    if hasattr(pk, "key_size"):
        out.append(f"- **Size**: {pk.key_size} bits")

    out.append("\n## Fingerprints")
    out.append(f"- **SHA-1**:   `{_hex_fingerprint(cert, hashes.SHA1())}`")
    out.append(f"- **SHA-256**: `{_hex_fingerprint(cert, hashes.SHA256())}`")

    out.append("\n## Serial / version / signature algorithm")
    out.append(f"- **Serial**: {cert.serial_number}")
    out.append(f"- **Version**: {cert.version.name}")
    out.append(f"- **Signature algo**: {cert.signature_algorithm_oid._name}")

    # SubjectAltName extension — list DNS names + IPs if present.
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = [str(n.value) for n in ext.value]
        if sans:
            out.append("\n## Subject Alternative Names")
            for s in sans: out.append(f"- `{s}`")
    except x509.ExtensionNotFound:
        pass

    return "\n".join(out) + "\n"


def _render_with_openssl(p: Path) -> str:
    """Fallback: shell out to `openssl x509 -text -noout`."""
    try:
        proc = subprocess.run(
            ["openssl", "x509", "-in", str(p), "-text", "-noout"],
            check=False, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise CertReadError(f"openssl invocation failed: {e}") from e
    if proc.returncode != 0:
        # Try DER input format.
        try:
            proc = subprocess.run(
                ["openssl", "x509", "-in", str(p), "-inform", "DER",
                 "-text", "-noout"],
                check=False, capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    if proc.returncode != 0:
        return (
            f"# Certificate: `{p.name}`\n\n"
            f"**openssl exited with code {proc.returncode}**:\n\n"
            f"```\n{(proc.stderr or proc.stdout)[:2000]}\n```\n"
        )
    return (
        f"# Certificate: `{p.name}`\n\n"
        "_Parsed via the `openssl` CLI (install `cryptography` for richer output)._\n\n"
        f"```\n{proc.stdout}\n```\n"
    )


def _render_key(p: Path, data: bytes) -> str:
    """PEM key files — type + size only. Never dump key material."""
    text = data.decode("utf-8", errors="replace")
    # Identify key type from the PEM banner.
    banner = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("-----BEGIN ") and line.endswith("-----"):
            banner = line[len("-----BEGIN "):-len("-----")]
            break
    out = [f"# Key: `{p.name}`", "", f"- **Type**: {banner or '(unknown — not PEM?)'}"]
    # If cryptography is available, also report the key size.
    try:
        from cryptography.hazmat.primitives import serialization  # type: ignore
        key = serialization.load_pem_private_key(data, password=None)
        if hasattr(key, "key_size"):
            out.append(f"- **Size**: {key.key_size} bits")
        out.append(f"- **Algorithm**: {key.__class__.__name__}")
    except Exception:
        # Either cryptography isn't installed or the key is encrypted.
        # Encrypted-key case: avoid the noise of a stack trace; just
        # surface a hint.
        if "ENCRYPTED" in banner:
            out.append("- **Encrypted**: yes (passphrase required to decode)")
    out.append("")
    out.append("> **Private-key material is not displayed.** "
               "This report intentionally omits the raw bytes so the "
               "file's contents can't be accidentally screenshotted.")
    return "\n".join(out) + "\n"


def _format_name(name) -> str:
    """Format a cryptography Name object as a markdown bullet list."""
    lines: list[str] = []
    for attr in name:
        oid_name = getattr(attr.oid, "_name", str(attr.oid))
        lines.append(f"- **{oid_name}**: {attr.value}")
    return "\n".join(lines) if lines else "- _(empty)_"


def _hex_fingerprint(cert, hash_alg) -> str:
    fp = cert.fingerprint(hash_alg)
    return ":".join(f"{b:02X}" for b in fp)
