"""Action handlers for cryptographic PDF signing.

Two flows, both dialog-driven:

1. **Sign…**: prompt for PFX/P12 keystore path + passphrase +
   optional reason / location / timestamp URL. Write the signed
   copy to a sibling `<stem>-signed.pdf`, open it in a new tab.

2. **Verify…**: read every signature in the open PDF, present a
   summary (signer name, signing time, intact / coverage / trusted,
   any validation errors). No file modification.

The libraries are imported lazily by `pdf_signing.py` so a missing
pyHanko surfaces as a friendly `PdfSigningError("install hint")`.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QMessageBox, QLineEdit,
)

from .pdf_actions import _require_pdf, _suggest_output, _finish
from .pdf_signing import (
    PdfSigningError, sign_pdf, verify_signatures,
)


def _handle_error(window, exc: PdfSigningError, title: str = "PDF signing"):
    QMessageBox.warning(window, title, str(exc))


# ---------------------------------------------------------- sign --

def sign_pdf_dialog(window) -> None:
    """**PDF → Sign with a certificate…** flow."""
    if not _require_pdf(window): return

    # 1) Keystore path.
    pfx_path, _ = QFileDialog.getOpenFileName(
        window, "Pick PKCS#12 keystore (.pfx / .p12)",
        str(Path(window._current_path).parent),
        "PKCS#12 keystore (*.pfx *.p12);;All files (*)")
    if not pfx_path: return

    # 2) Passphrase — masked.
    passphrase, ok = QInputDialog.getText(
        window, "Keystore passphrase",
        f"Passphrase for {Path(pfx_path).name}:",
        QLineEdit.EchoMode.Password)
    if not ok: return

    # 3) Optional metadata.
    reason, ok = QInputDialog.getText(
        window, "Sign — reason (optional)",
        "Reason for signing (or leave blank):")
    if not ok: return
    location, ok = QInputDialog.getText(
        window, "Sign — location (optional)",
        "Signer's location (or leave blank):")
    if not ok: return

    # 4) Optional timestamp URL.
    tsa, ok = QInputDialog.getText(
        window, "Sign — timestamp URL (optional)",
        "RFC 3161 TSA URL (e.g. 'http://timestamp.digicert.com'), "
        "or blank for no timestamp. With a TSA you get PAdES-T; "
        "without, only the signer's clock is recorded.")
    if not ok: return

    out = _suggest_signed_path(window._current_path)
    try:
        sign_pdf(window._current_path, out,
                  pfx_path=pfx_path, passphrase=passphrase,
                  reason=reason or None,
                  location=location or None,
                  timestamp_url=tsa.strip() or None)
    except PdfSigningError as e:
        _handle_error(window, e, "Sign failed"); return

    _finish(window, out, f"Signed → {Path(out).name}")


def verify_signatures_dialog(window) -> None:
    """**PDF → Verify signatures…** — read + display every
    signature, with intact / coverage / trusted flags."""
    if not _require_pdf(window): return
    try:
        reports = verify_signatures(window._current_path)
    except PdfSigningError as e:
        _handle_error(window, e, "Verify failed"); return
    if not reports:
        QMessageBox.information(
            window, "No signatures",
            "This PDF has no embedded signatures.")
        return
    lines = []
    for i, r in enumerate(reports, 1):
        lines.append(f"#{i}  Field: {r.field_name or '(default)'}")
        lines.append(f"    Signer:    {r.signer_name}")
        lines.append(f"    Signed:    {r.signing_time or '(unknown)'}")
        flags = [
            "intact ✓" if r.is_intact else "intact ✗",
            "full coverage ✓" if r.coverage else "partial coverage ✗",
            "trusted ✓" if r.trusted else "trusted ✗ (self-signed or unknown CA)",
            "timestamp ✓" if r.timestamp_present else "timestamp –",
        ]
        lines.append(f"    Status:    {'  '.join(flags)}")
        if r.errors:
            for e in r.errors[:5]:
                lines.append(f"    Error:     {e}")
        lines.append("")
    QMessageBox.information(
        window, f"{len(reports)} signature(s)",
        "\n".join(lines).rstrip())


# ---------------------------------------------------------- helpers --

def _suggest_signed_path(input_path: str) -> str:
    """Sibling `<stem>-signed.pdf`, deduped."""
    p = Path(input_path)
    base = p.with_name(f"{p.stem}-signed{p.suffix}")
    if not base.exists():
        return str(base)
    i = 2
    while True:
        cand = p.with_name(f"{p.stem}-signed-{i}{p.suffix}")
        if not cand.exists():
            return str(cand)
        i += 1
