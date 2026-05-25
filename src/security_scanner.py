"""Security scanner — heuristic + optional system-AV scan of a file.

Pure functions. Stateless. Returns a `ScanResult` with severity-rated
`Finding`s. The opening flow can decide whether to warn / block based
on `result.risk_level`.

Detections:
- Dangerous file extensions (executables, installers, script droppers).
- Magic-byte vs extension mismatch (renamed .exe disguised as .pdf is
  a classic phishing pattern).
- Office documents with VBA macros (looks for `vbaProject.bin` in the
  ZIP central directory).
- PDFs with embedded JavaScript / Launch / OpenAction triggers.
- HTML / SVG with `<script>` tags or `javascript:` URIs.
- Suspicious shell patterns in scripts (curl|sh, base64-decode-pipe-shell,
  PowerShell evasion flags, netcat listeners, hex-encoded payloads).
- macOS quarantine xattr (`com.apple.quarantine`) — file came from the
  internet and hasn't been explicitly approved.
- Optional ClamAV passthrough when `clamscan` is on PATH.

Each finding has a severity:
- `info`        — neutral observation (e.g. "downloaded from internet").
- `warning`     — should prompt the user (macros, PDF JS).
- `dangerous`   — should block/quarantine by default (signed exe with
                   mismatched extension, ClamAV hit).
"""
from __future__ import annotations
import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


# ---- finding model -------------------------------------------------------

@dataclass
class Finding:
    severity: str           # info / warning / dangerous
    category: str           # extension_mismatch / macro / pdf_js / ...
    description: str
    detail: str = ""

    def __str__(self) -> str:
        ico = {"info": "ℹ", "warning": "⚠", "dangerous": "⛔"}.get(
            self.severity, "·")
        return f"{ico} [{self.category}] {self.description}"


@dataclass
class ScanResult:
    path: str
    findings: list[Finding] = field(default_factory=list)
    detected_kind: str = ""

    @property
    def risk_level(self) -> str:
        sev = {f.severity for f in self.findings}
        if "dangerous" in sev: return "dangerous"
        if "warning" in sev:   return "suspicious"
        return "clean"

    def __bool__(self) -> bool:
        return self.risk_level != "clean"

    def to_markdown(self) -> str:
        emoji = {"clean": "✅", "suspicious": "⚠️", "dangerous": "⛔"}
        lines = [f"# Security scan — `{Path(self.path).name}`",
                 "",
                 f"**Risk level:** {emoji[self.risk_level]} {self.risk_level}"]
        if self.detected_kind:
            lines.append(f"**Detected kind:** {self.detected_kind}")
        if not self.findings:
            lines.append("\nNo notable findings.")
        else:
            lines.append(f"\n## Findings ({len(self.findings)})\n")
            for f in self.findings:
                lines.append(f"- {f}")
                if f.detail: lines.append(f"  - {f.detail}")
        return "\n".join(lines)


# ---- detection rules -----------------------------------------------------

DANGEROUS_EXTENSIONS = {
    # Native executables.
    ".exe", ".com", ".scr", ".pif", ".cpl", ".msc",
    # Windows scripts.
    ".bat", ".cmd", ".vbs", ".vbe", ".jse", ".wsf", ".wsh", ".hta", ".reg",
    # PowerShell.
    ".ps1", ".psm1", ".ps2", ".ps2xml", ".psc1",
    # macOS / Linux installers / disk images.
    ".dmg", ".pkg", ".app", ".mpkg",
    # Mobile apps.
    ".apk", ".ipa",
    # Archives that may contain executables.
    ".jar", ".msi", ".cab",
    # Disk images.
    ".iso", ".img", ".vhd", ".vhdx", ".vmdk",
    # Linux packages.
    ".deb", ".rpm",
}

# Office formats that can carry macros.
MACRO_BEARING_FORMATS = {
    ".docm", ".dotm", ".xlsm", ".xltm", ".pptm", ".potm",
    ".ppam", ".sldm",
    # Modern .docx etc shouldn't have macros, but they CAN — we still scan
    # the zip for vbaProject.bin to catch macro-enabled docs renamed to
    # the macro-free extension.
    ".docx", ".dotx", ".xlsx", ".xltx", ".pptx", ".potx", ".ppsx",
}

SUSPICIOUS_SCRIPT_PATTERNS = [
    # Pipe-to-shell installer pattern.
    (re.compile(rb"(?:curl|wget)[^|\n]{1,200}\|\s*(?:bash|sh|zsh)\b"),
     "remote-shell pipe", "downloads + executes a script in one step"),
    # Base64-decoded shell. Several arrangements:
    #   echo X | base64 -d | bash
    #   base64 -d <<<X | sh
    #   base64 -d <(echo X) | bash
    (re.compile(rb"base64\s+(?:--?d(?:ecode)?)\b[^\n]{0,80}\|\s*(?:bash|sh|zsh)\b"),
     "base64-decoded shell", "decodes content and pipes to a shell"),
    # PowerShell evasion flags.
    (re.compile(rb"(?i)powershell(?:\.exe)?\s+-(?:enc(?:odedcommand)?|nop\b|w\s+hidden|exec\s+bypass)"),
     "PowerShell evasion flags", "common in dropper / loader malware"),
    # FromBase64String + Invoke-Expression — staple of fileless PowerShell.
    (re.compile(rb"(?i)FromBase64String\s*\(.*?Invoke-Expression", re.DOTALL),
     "PowerShell base64 → IEX", "decodes base64 and executes"),
    # Netcat reverse-shell listener.
    (re.compile(rb"\bnc\s+-[el]\w*\s"),
     "netcat listener", "potential reverse-shell pattern"),
    # eval $(curl ...).
    (re.compile(rb"eval\s*[\$\(`]+\s*(?:curl|wget|fetch)\b"),
     "eval-of-remote-content", "executes whatever a remote URL returns"),
    # Long hex-encoded payload (look for ≥30 \xHH escapes in a row).
    (re.compile(rb"(?:\\x[0-9a-fA-F]{2}){30,}"),
     "hex-encoded payload", "obfuscation trick used by shellcode loaders"),
    # rm -rf / (but allow /tmp / /var/tmp).
    (re.compile(rb"\brm\s+-[rfRF]+\s+/+(?!tmp\b|var\b|opt\b|home\b|Users\b)"),
     "destructive `rm -rf`", "would wipe a top-level directory"),
    # chmod +x then execute — typical staging pattern.
    (re.compile(rb"chmod\s+\+x\s+\S+\s*&&\s*[\./~]"),
     "stage-and-execute", "marks a file executable then runs it"),
    # python -c "exec(__import__('base64')..."
    (re.compile(rb"(?i)(?:python|python3)\s+-c\s+['\"][^'\"]{0,80}exec\s*\("),
     "python -c exec", "runs arbitrary Python from an inline string"),
]

# Format-detection heuristics that we run against the file head.
_PDF_JS_PATTERNS = [
    (re.compile(rb"/JavaScript\b"),  "PDF JavaScript",
     "the PDF embeds JavaScript that may run on open"),
    (re.compile(rb"/JS\b"),           "PDF /JS dictionary entry",
     "older marker for embedded JavaScript"),
    (re.compile(rb"/OpenAction\b"),   "PDF OpenAction",
     "PDF runs an action automatically when opened"),
    (re.compile(rb"/Launch\b"),       "PDF Launch action",
     "PDF can launch external programs / scripts"),
    (re.compile(rb"/EmbeddedFile\b"), "embedded file",
     "the PDF contains another file inside it"),
    (re.compile(rb"/AA\b"),           "PDF additional actions",
     "fires actions on focus / blur / page open"),
]


# ---- helpers ------------------------------------------------------------

def _read_head(path: Path, n: int = 65536) -> bytes:
    try:
        with path.open("rb") as f: return f.read(n)
    except OSError: return b""


def _read_all_bounded(path: Path, max_bytes: int = 4_000_000) -> bytes:
    try:
        with path.open("rb") as f: return f.read(max_bytes)
    except OSError: return b""


def _macos_quarantine_xattr(path: Path) -> str:
    try:
        out = subprocess.run(
            ["xattr", "-p", "com.apple.quarantine", str(path)],
            capture_output=True, text=True, timeout=2)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _zip_central_files(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path, "r") as z:
            return z.namelist()
    except (zipfile.BadZipFile, OSError):
        return []


def clamscan_available() -> bool:
    try:
        return subprocess.run(["clamscan", "--version"],
                              capture_output=True, timeout=3).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _run_clamscan(path: Path) -> tuple[bool, str]:
    """Return (is_infected, name_or_empty). False on errors so a missing
    clam db never causes a false positive."""
    try:
        cp = subprocess.run(
            ["clamscan", "--no-summary", "--stdout", str(path)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    # ClamAV exit codes: 0 = clean, 1 = found, 2 = error.
    if cp.returncode != 1: return False, ""
    # Output: "<path>: SignatureName FOUND"
    for line in cp.stdout.splitlines():
        if line.endswith("FOUND"):
            try:
                name = line.rsplit(":", 1)[1].strip().rsplit(" ", 1)[0]
                return True, name
            except IndexError: pass
    return True, ""


# ---- main entry point ---------------------------------------------------

def scan_file(path, *, run_clamav: bool = False, head_bytes: int = 65536,
              full_bytes: int = 4_000_000) -> ScanResult:
    """Run heuristic checks on `path`. `run_clamav=True` invokes the
    system `clamscan` if available (slow — 0.5–5 s)."""
    p = Path(path)
    result = ScanResult(path=str(p))
    if not p.is_file():
        result.findings.append(Finding(
            "warning", "missing_file",
            f"path is not a regular file: {p}"))
        return result

    head = _read_head(p, head_bytes)
    ext = p.suffix.lower()

    # Detect kind via the file inspector for the mismatch test.
    try:
        from .file_inspector import inspect_file
        info = inspect_file(p)
        result.detected_kind = info.detected_kind
    except Exception:
        info = None

    # 1. macOS quarantine.
    qx = _macos_quarantine_xattr(p)
    if qx:
        result.findings.append(Finding(
            "info", "macos_quarantine",
            "file carries `com.apple.quarantine` — downloaded from the internet",
            qx))

    # 2. Dangerous extension family.
    if ext in DANGEROUS_EXTENSIONS:
        result.findings.append(Finding(
            "dangerous", "executable_extension",
            f"`{ext}` is an executable / installer / script-launcher format",
            "opening can execute code if the user double-clicks elsewhere"))

    # 3. Extension vs detected-kind mismatch.
    if info is not None and info.detected_kind:
        # Map common kinds to expected extensions for the catch.
        # NB: kind=zip covers a lot of well-known zip containers — Office
        # XML formats (xlsx/docx/pptx + macro/template variants), Java /
        # Android / iOS packages, eBooks, and Origin's `.ogm`/`.ogw` — so
        # we whitelist them rather than flag every encounter as
        # "extension mismatch".
        expected = {
            "pdf": (".pdf",), "png": (".png",), "jpeg": (".jpg", ".jpeg"),
            "gif": (".gif",), "elf": (".elf", ".so", ".out"),
            "zip": (
                ".zip",
                # Office Open XML (Word / Excel / PowerPoint)
                ".docx", ".docm", ".dotx", ".dotm",
                ".xlsx", ".xlsm", ".xltx", ".xltm",
                ".pptx", ".pptm", ".potx", ".potm", ".ppsx", ".ppsm",
                # OpenDocument
                ".odt", ".ods", ".odp", ".odg", ".odf",
                # eBook / Java / Android / iOS / installer packages
                ".epub", ".jar", ".war", ".ear", ".apk", ".aab",
                ".ipa", ".xpi", ".crx", ".whl",
            ),
            "macho": ("",),  # mach-o has no fixed ext
            "pe": (".exe", ".dll", ".sys", ".scr"),
            "parquet": (".parquet", ".pq"),
            "sqlite": (".sqlite", ".sqlite3", ".db", ".db3"),
            "hdf5": (".h5", ".hdf5", ".he5", ".nc", ".nc4"),
        }
        expected_exts = expected.get(info.detected_kind, ())
        # Note: only fire mismatch for binary kinds + non-empty expected list.
        if expected_exts and ext and ext not in expected_exts and \
                info.detected_via == "magic":
            sev = "dangerous" if info.detected_kind in {"pe", "macho", "elf"} else "warning"
            result.findings.append(Finding(
                sev, "extension_mismatch",
                f"file extension `{ext}` doesn't match detected kind "
                f"({info.detected_kind})",
                "renaming an executable to a doc extension is a phishing trick"))

    # 4. Office macro check (any zip-based office format).
    if ext in MACRO_BEARING_FORMATS or (head[:2] == b"PK" and ext in
                                        {".docx", ".docm", ".xlsx", ".xlsm",
                                         ".pptx", ".pptm"}):
        names = _zip_central_files(p)
        if any("vbaProject.bin" in n for n in names):
            result.findings.append(Finding(
                "warning", "office_macro",
                "Office document contains a VBA macro project",
                "macros can execute arbitrary code; only enable for trusted senders"))
        # Also: external links can fetch payloads.
        if any("externalLinks/" in n for n in names):
            result.findings.append(Finding(
                "warning", "office_external_link",
                "Office document references external links",
                "external content can be a delivery vector"))

    # 5. PDF triggers.
    if ext == ".pdf" or head.startswith(b"%PDF-"):
        body = _read_all_bounded(p, full_bytes)
        for pat, label, detail in _PDF_JS_PATTERNS:
            if pat.search(body):
                result.findings.append(Finding(
                    "warning", "pdf_active_content", label, detail))

    # 6. HTML / SVG embedded scripts.
    if ext in {".html", ".htm", ".xhtml", ".svg", ".svgz"}:
        body = _read_all_bounded(p, full_bytes)
        if re.search(rb"(?i)<script[^>]*>", body):
            result.findings.append(Finding(
                "info" if ext != ".svg" else "warning",
                "embedded_script",
                f"{ext} contains <script> tags",
                "rendered in TextView's WebView; review before opening URLs"))
        if re.search(rb"(?i)\bjavascript:", body):
            result.findings.append(Finding(
                "warning", "javascript_uri",
                f"{ext} contains `javascript:` URIs"))

    # 7. Script / text body pattern scan.
    if ext in {".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1",
               ".bat", ".cmd", ".py", ".js", ".rb", ".pl", ".php"} or \
            (info is not None and not info.is_text is False and
             info.detected_kind in {"plain", ""}):
        body = _read_all_bounded(p, full_bytes)
        for pat, label, detail in SUSPICIOUS_SCRIPT_PATTERNS:
            m = pat.search(body)
            if m:
                snippet = body[max(0, m.start() - 12):m.end() + 12]
                snip_str = snippet.decode("utf-8", errors="replace")\
                    .replace("\n", " ")
                result.findings.append(Finding(
                    "warning", "suspicious_pattern", label,
                    f"{detail} — near `{snip_str[:80]}`"))

    # 8. Optional ClamAV.
    if run_clamav and clamscan_available():
        infected, name = _run_clamscan(p)
        if infected:
            result.findings.append(Finding(
                "dangerous", "antivirus_hit",
                f"ClamAV signature match: {name or '(unnamed)'}",
                "the system AV flagged this file as malicious"))

    return result
