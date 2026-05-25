"""Cryptographic PDF signing + verification via **pyHanko**.

pyHanko is the modern Python implementation of PDF digital signatures
(ETSI EN 319 142, PAdES). It supports:

  - PKCS#12 (`.pfx` / `.p12`) keystores — what consumer cert
    vendors hand out.
  - **PAdES B-B / B-T / B-LT / B-LTA** profile levels (baseline →
    long-term archival). We default to **B-T** when a TSA is given,
    **B-B** otherwise.
  - RFC 3161 timestamping against a TSA URL.
  - Verification with full cert-chain validation, revocation
    checking, and timestamp-anchored point-in-time validity.

This module is **the** signing layer — never imports `pyhanko` at
module load. Every entry point lazy-imports so a missing dep just
becomes a friendly `PdfSigningError(install hint)`.

The corresponding action handler (`pdf_signing_actions.py`)
provides the GUI flow: prompt for the PFX path + passphrase + TSA
URL + reason + location, sign to a sibling `*-signed.pdf`, open
the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class PdfSigningError(Exception):
    """Wraps every signing / verification failure so the GUI never
    has to handle pyhanko-specific exceptions directly."""


# ----------------------------------------------------------- internals --

def _pyhanko():
    """Lazy import for the pyHanko top-level package."""
    try:
        import pyhanko  # type: ignore
    except ImportError as e:
        raise PdfSigningError(
            "Cryptographic PDF signing needs pyHanko. "
            "Install with `pip install pyHanko`."
        ) from e
    return pyhanko


def _load_pfx(pfx_path: str, passphrase: str | None):
    """Return a pyHanko `SimpleSigner` from a `.pfx` / `.p12`. Raises
    `PdfSigningError` for the user-facing failure modes (file
    missing, wrong password, malformed keystore)."""
    p = Path(pfx_path)
    if not p.is_file():
        raise PdfSigningError(f"PFX/P12 keystore not found: {pfx_path}")
    try:
        from pyhanko.sign import signers   # type: ignore
    except ImportError as e:
        raise PdfSigningError(
            "pyHanko is required. Install with `pip install pyHanko`."
        ) from e
    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=str(p),
            passphrase=(passphrase.encode() if passphrase else None),
        )
    except ValueError as e:
        # Common cause: wrong passphrase. pyHanko raises ValueError.
        raise PdfSigningError(
            f"Could not load keystore (wrong passphrase?): {e}"
        ) from e
    except Exception as e:
        raise PdfSigningError(f"Could not load PFX/P12 keystore: {e}") from e
    # Defensive: some pyhanko versions return None on bad password
    # rather than raising. Surface a clean message in that case so the
    # signing step doesn't blow up with an inscrutable AttributeError.
    if signer is None:
        raise PdfSigningError(
            "Could not load keystore — likely wrong passphrase or "
            "corrupt .pfx file.")
    return signer


# ----------------------------------------------------------- sign --

def sign_pdf(input_path: str, output_path: str,
              *,
              pfx_path: str,
              passphrase: str | None = None,
              signer_field_name: str = "Signature1",
              reason: str | None = None,
              location: str | None = None,
              contact: str | None = None,
              timestamp_url: str | None = None) -> None:
    """Sign `input_path` and write the signed PDF to `output_path`.

    Mandatory:
      - `pfx_path` + `passphrase`: PKCS#12 keystore + decryption key.

    Optional metadata embedded in the signature:
      - `signer_field_name`: PDF signature field name (e.g.
        `"Signature1"`). pyHanko creates a new invisible field if
        the document doesn't already have one with that name.
      - `reason` / `location` / `contact`: free-text strings shown
        in any PDF viewer that displays signature metadata.

    Optional cryptographic timestamp:
      - `timestamp_url`: a TSA endpoint (RFC 3161, e.g.
        `http://timestamp.digicert.com`). When given, the signature
        gets an embedded timestamp — required for **PAdES-T** and
        long-term archival validity. When omitted, the signature
        is **PAdES-B** (date is the signer's clock).

    Input file is **never** mutated. On success, `output_path` is
    a fresh PDF containing the signature.
    """
    src = Path(input_path)
    if not src.is_file():
        raise PdfSigningError(f"Source PDF not found: {input_path}")

    signer = _load_pfx(pfx_path, passphrase)

    try:
        from pyhanko.sign import signers, fields, timestamps  # type: ignore
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter  # type: ignore
    except ImportError as e:
        raise PdfSigningError(
            "pyHanko is required. Install with `pip install pyHanko`."
        ) from e

    tsa = None
    if timestamp_url:
        try:
            tsa = timestamps.HTTPTimeStamper(url=timestamp_url)
        except Exception as e:
            raise PdfSigningError(
                f"Could not configure timestamp client: {e}") from e

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(src, "rb") as inf, open(output_path, "wb") as outf:
            w = IncrementalPdfFileWriter(inf)
            meta = signers.PdfSignatureMetadata(
                field_name=signer_field_name,
                reason=reason or None,
                location=location or None,
                contact_info=contact or None,
            )
            pdf_signer = signers.PdfSigner(
                signature_meta=meta, signer=signer,
                timestamper=tsa,
            )
            pdf_signer.sign_pdf(w, output=outf)
    except Exception as e:
        # Clean up the half-written file so the user doesn't end up
        # with a corrupt sibling.
        try: Path(output_path).unlink(missing_ok=True)
        except Exception: pass
        raise PdfSigningError(f"Sign failed: {e}") from e


# ----------------------------------------------------------- verify --

@dataclass
class SignatureReport:
    """One entry per signature on the PDF (signed in date order).

    Fields:
      - `field_name`: the PDF signature field name.
      - `signer_name`: common-name from the signer cert, or "Unknown".
      - `signing_time`: pyHanko's reported signing time, or None.
      - `is_intact`: True if the signature's cryptographic hash
        matches (the PDF content hasn't changed since signing).
      - `coverage`: True if the signature covers the entire current
        PDF (False means content was added after signing).
      - `trusted`: True if pyHanko could chain to a trusted root.
        Often False without an explicit trust list; not the same as
        "signature is malicious."
      - `errors`: list of validation-issue strings (cert expired,
        cert revoked, untrusted chain, etc.).
      - `timestamp_present`: True iff the signature has an embedded
        RFC 3161 timestamp (PAdES-T / -LT / -LTA).
    """
    field_name: str
    signer_name: str
    signing_time: str
    is_intact: bool
    coverage: bool
    trusted: bool
    errors: list[str]
    timestamp_present: bool


def verify_signatures(input_path: str) -> list[SignatureReport]:
    """Read every signature in the PDF and run pyHanko's validator
    against each. Returns one `SignatureReport` per signature, in
    PDF field order. Empty list if the PDF has no signatures.

    Notes on `trusted`:
      - pyHanko ships no built-in trust roots — `trusted=False` is
        normal for self-signed test certs and for unfamiliar CAs.
      - To validate against a custom trust list, callers can build
        a `ValidationContext` themselves; this helper uses the
        default permissive context for the common case.
    """
    src = Path(input_path)
    if not src.is_file():
        raise PdfSigningError(f"Source PDF not found: {input_path}")
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader  # type: ignore
        from pyhanko.sign.validation import validate_pdf_signature  # type: ignore
        from pyhanko_certvalidator import ValidationContext  # type: ignore
    except ImportError as e:
        raise PdfSigningError(
            "pyHanko is required for verification. "
            "Install with `pip install pyHanko`."
        ) from e

    reports: list[SignatureReport] = []
    vc = ValidationContext()
    try:
        with open(src, "rb") as f:
            r = PdfFileReader(f)
            sigs = r.embedded_signatures or []
            for sig in sigs:
                status = validate_pdf_signature(sig, signer_validation_context=vc)
                reports.append(_status_to_report(sig, status))
    except Exception as e:
        raise PdfSigningError(f"Verification failed: {e}") from e
    return reports


def _status_to_report(sig, status) -> SignatureReport:
    """Map pyhanko's `PdfSignatureStatus` to our flat dataclass."""
    # Signer common-name lookup — defensive because the cert may
    # be unusual.
    name = "Unknown"
    try:
        name = sig.signer_cert.subject.human_friendly or "Unknown"
    except Exception:
        pass

    signing_time = ""
    try:
        st = getattr(status, "signing_time", None) or getattr(sig, "self_reported_timestamp", None)
        if isinstance(st, datetime):
            signing_time = st.isoformat()
        elif st is not None:
            signing_time = str(st)
    except Exception:
        pass

    errors: list[str] = []
    try:
        if getattr(status, "errors", None):
            errors = [str(e) for e in status.errors]
    except Exception:
        pass

    # pyhanko has many slightly-renamed attributes across versions —
    # try a few names.
    def _bool_attr(*names: str) -> bool:
        for n in names:
            if hasattr(status, n):
                try: return bool(getattr(status, n))
                except Exception: continue
        return False

    return SignatureReport(
        field_name=getattr(sig, "field_name", "") or "",
        signer_name=name,
        signing_time=signing_time,
        is_intact=_bool_attr("intact"),
        coverage=_bool_attr("coverage", "complete_document"),
        trusted=_bool_attr("trusted", "trust_problem_indic"),
        errors=errors,
        timestamp_present=_bool_attr("timestamp_validity", "has_timestamp"),
    )
