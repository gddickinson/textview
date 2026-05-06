"""Identify "what is this file" for formats TextView doesn't natively
handle. Returns a `FileInfo` with magic-byte detection, MIME guess, hex
preview, and a short human description so the user (or agent) can
decide what to do with it.

No external deps — small built-in magic-byte table covers the long
tail of formats developers actually encounter (parquet, hdf5, sqlite,
pickle, shapefile, FITS, etc.). For text-like files we sample with
`chardet` (already a dependency) for encoding.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


# Magic-byte signatures: ordered (more specific patterns first). Each
# entry: (offset, bytes, kind, description).
_MAGIC: list[tuple[int, bytes, str, str]] = [
    # Compressed / archives
    (0, b"\x1f\x8b\x08",          "gzip",     "Gzip-compressed data"),
    (0, b"\x42\x5a\x68",          "bzip2",    "Bzip2-compressed data"),
    (0, b"\xfd7zXZ\x00",          "xz",       "XZ-compressed data"),
    (0, b"\x28\xb5\x2f\xfd",      "zstd",     "Zstandard-compressed data"),
    (0, b"\x52\x61\x72\x21\x1a\x07", "rar",   "RAR archive"),
    (0, b"7z\xbc\xaf\x27\x1c",    "7z",       "7-Zip archive"),
    (0, b"PK\x03\x04",            "zip",      "ZIP archive (could also be jar/docx/xlsx/odf)"),
    (0, b"PK\x05\x06",            "zip-empty","Empty ZIP archive"),
    # Documents / images / media we already support — leave for completeness
    (0, b"%PDF-",                 "pdf",      "Portable Document Format"),
    (0, b"\x89PNG\r\n\x1a\n",     "png",      "PNG image"),
    (0, b"\xff\xd8\xff",           "jpeg",     "JPEG image"),
    (0, b"GIF8",                  "gif",      "GIF image"),
    (0, b"BM",                    "bmp",      "BMP image"),
    (0, b"RIFF",                  "riff",     "RIFF container (WAV / WebP / AVI)"),
    (4, b"ftyp",                  "mp4",      "MP4 / QuickTime / M4A container"),
    (0, b"OggS",                  "ogg",      "Ogg container"),
    (0, b"fLaC",                  "flac",     "FLAC audio"),
    (0, b"ID3",                   "mp3",      "MP3 audio (ID3v2)"),
    # Data formats
    (0, b"PAR1",                  "parquet",  "Apache Parquet columnar storage"),
    (0, b"ARROW1",                "arrow",    "Apache Arrow IPC"),
    (0, b"\x89HDF\r\n\x1a\n",     "hdf5",     "HDF5 hierarchical data"),
    (0, b"\x93NUMPY",             "npy",      "NumPy array (.npy)"),
    (0, b"PK\x03\x04",            "npz",      "NumPy archive (.npz, ZIP)"),  # filtered by ext
    (0, b"SQLite format 3\x00",   "sqlite",   "SQLite database"),
    (0, b"\x80\x04",               "pickle4",  "Python pickle (protocol 4)"),
    (0, b"\x80\x05",               "pickle5",  "Python pickle (protocol 5)"),
    (0, b"MATLAB ",                "mat",      "MATLAB MAT-file (v5+)"),
    (0, b"SIMPLE  =",              "fits",     "FITS astronomy data"),
    (0, b"\x00\x00\x27\x0a",       "shp",      "ESRI shapefile"),
    (0, b"PCAP",                   "pcap",     "Network packet capture"),
    (0, b"\xd4\xc3\xb2\xa1",       "pcap",     "Network packet capture (libpcap)"),
    (0, b"\x0a\x0d\x0d\x0a",       "pcapng",   "Network packet capture (PCAP-NG)"),
    # Executables / object files
    (0, b"\x7fELF",                "elf",      "ELF executable / shared object"),
    (0, b"\xfe\xed\xfa\xce",       "macho32",  "Mach-O executable (32-bit)"),
    (0, b"\xfe\xed\xfa\xcf",       "macho64",  "Mach-O executable (64-bit)"),
    (0, b"\xca\xfe\xba\xbe",       "macho-fat","Mach-O universal binary"),
    (0, b"\xcf\xfa\xed\xfe",       "macho64-le","Mach-O 64-bit (little endian)"),
    (0, b"MZ",                     "pe",       "Windows PE / DOS executable"),
    (0, b"\x00asm",                "wasm",     "WebAssembly module"),
    (0, b"\xca\xfe\xba\xbe\x00\x00\x00", "java-class", "Java class file"),
    # Fonts
    (0, b"\x00\x01\x00\x00",       "ttf",      "TrueType font"),
    (0, b"OTTO",                   "otf",      "OpenType font"),
    (0, b"wOFF",                   "woff",     "Web Open Font Format"),
    (0, b"wOF2",                   "woff2",    "Web Open Font Format 2"),
    # Markup / declarative
    (0, b"<?xml",                  "xml",      "XML document"),
    (0, b"<!DOC",                  "html",     "HTML document"),
    # Misc
    (0, b"BC\xc0\xde",             "bitcode",  "LLVM bitcode"),
    (0, b"#!/",                    "script",   "Shebang script"),
    (0, b"\x42\x52",               "br",       "Brotli stream (heuristic)"),
]


# Extension → (kind, description) for files where magic is uninformative
# (many text formats have no signature) or as a hint when magic matches a
# generic container (e.g. zip → could be xlsx/docx/jar/pptx/odf).
_EXT_HINTS: dict[str, tuple[str, str]] = {
    ".parquet": ("parquet", "Apache Parquet columnar storage"),
    ".feather": ("feather", "Apache Arrow Feather columnar storage"),
    ".arrow":   ("arrow",   "Apache Arrow IPC"),
    ".h5":      ("hdf5",    "HDF5 hierarchical data"),
    ".hdf5":    ("hdf5",    "HDF5 hierarchical data"),
    ".nc":      ("netcdf",  "NetCDF scientific data (HDF5-based)"),
    ".sqlite":  ("sqlite",  "SQLite database"),
    ".db":      ("sqlite?", "Database file (likely SQLite or similar)"),
    ".npy":     ("npy",     "NumPy array"),
    ".npz":     ("npz",     "NumPy zipped archive of arrays"),
    ".pkl":     ("pickle",  "Python pickle (NEVER load from untrusted sources)"),
    ".pickle":  ("pickle",  "Python pickle (NEVER load from untrusted sources)"),
    ".mat":     ("mat",     "MATLAB MAT-file"),
    ".fits":    ("fits",    "FITS astronomy data"),
    ".fit":     ("fits",    "FITS astronomy data"),
    ".shp":     ("shp",     "ESRI shapefile (geometry; needs .dbf + .shx siblings)"),
    ".geojson": ("geojson", "GeoJSON geographic features"),
    ".kml":     ("kml",     "Keyhole Markup Language (geographic)"),
    ".gpx":     ("gpx",     "GPS Exchange Format"),
    ".dwg":     ("dwg",     "AutoCAD drawing"),
    ".dxf":     ("dxf",     "Drawing Exchange Format (CAD)"),
    ".dbc":     ("dbc",     "CAN bus database (Vector format)"),
    ".pcap":    ("pcap",    "Network packet capture"),
    ".pcapng":  ("pcapng",  "Network packet capture (PCAP-NG)"),
    ".wasm":    ("wasm",    "WebAssembly module"),
    ".jar":     ("jar",     "Java archive (ZIP-based)"),
    ".war":     ("war",     "Java web archive (ZIP-based)"),
    ".whl":     ("whl",     "Python wheel (ZIP-based)"),
    ".egg":     ("egg",     "Python egg (ZIP-based)"),
    ".dmg":     ("dmg",     "macOS disk image"),
    ".iso":     ("iso",     "Optical disc image"),
    ".deb":     ("deb",     "Debian package"),
    ".rpm":     ("rpm",     "Red Hat package"),
    ".bin":     ("binary",  "Generic binary file"),
    ".dat":     ("data",    "Generic data file"),
    ".pb":      ("protobuf","Protocol Buffer (probably binary)"),
}


@dataclass
class FileInfo:
    path: str
    size: int
    size_human: str
    mtime_iso: str
    extension: str
    detected_kind: str         # "parquet", "hdf5", "unknown", "text", …
    detected_via: str          # "extension" | "magic" | "extension+magic" | "heuristic"
    description: str
    is_text: bool
    encoding: str              # only meaningful when is_text
    text_sample: str           # first ~500 chars when text-like
    hex_preview: str           # multi-line hex+ASCII dump of first ~256 bytes
    suggested_action: str      # short hint about what to do next

    def to_dict(self) -> dict: return asdict(self)

    def to_markdown(self) -> str:
        """Render as a markdown page suitable for the rendered viewer."""
        lines = [
            f"# {Path(self.path).name}",
            "",
            f"*{self.description}*",
            "",
            "## File information",
            "",
            f"- **Path:** `{self.path}`",
            f"- **Size:** {self.size_human} ({self.size:,} bytes)",
            f"- **Modified:** {self.mtime_iso}",
            f"- **Extension:** `{self.extension or '(none)'}`",
            f"- **Detected:** `{self.detected_kind}` (via {self.detected_via})",
        ]
        if self.is_text:
            lines.append(f"- **Encoding:** `{self.encoding}`")
        lines += ["", "## Suggested action", "", self.suggested_action]
        if self.is_text and self.text_sample:
            lines += ["", "## Text preview", "", "```", self.text_sample, "```"]
        lines += [
            "",
            "## Hex preview (first bytes)",
            "",
            "```",
            self.hex_preview,
            "```",
            "",
            "---",
            "",
            "*Ask the chat agent (Ctrl+J) — it can analyze this file in depth, "
            "suggest tools or libraries, and write a TextView script to handle "
            "this format from now on.*",
        ]
        return "\n".join(lines)


# ---- public API ----------------------------------------------------------


def maybe_unknown_file_report(path) -> tuple[str, str] | None:
    """If `path` looks unknown / binary, return `(markdown_report,
    detected_kind)`. Else None. Used by `MainWindow.open_file` to route
    binary files to the rendered markdown viewer instead of dumping
    garbled bytes into the code editor."""
    p = Path(path)
    if not p.is_file(): return None
    head = _read_head(p, 4096)
    if not looks_binary(head): return None
    info = inspect_file(p)
    md = info.to_markdown()
    try:
        from .format_handlers import lookup
        h = lookup(p.suffix)
    except Exception:
        h = None
    if h is not None:
        md = (f"> ✓ A handler is registered: **`{h.script}`** "
              f"({h.description or 'no description'}). "
              f"Run it via Run → Run agent script (F7) and pick "
              f"`{h.script}`.\n\n") + md
    # Attach an entry from the file-format database if one matches —
    # gives the user a quick "what is this and how do I use it" without
    # having to ask the agent.
    try:
        from .format_db import db
        e = (db().lookup_by_extension(p.suffix)
             or db().lookup_by_filename(p.name)
             or db().lookup_by_id(info.detected_kind))
    except Exception:
        e = None
    if e is not None:
        md += "\n\n---\n\n## From the file-format database\n\n" + e.to_markdown()
    # Append a security-scan summary so the unknown-file report doubles
    # as the user's first signal that something looks off.
    try:
        from .security_scanner import scan_file
        sr = scan_file(p)
        if sr.findings:
            md += "\n\n---\n\n" + sr.to_markdown()
    except Exception: pass
    return md, info.detected_kind


def inspect_file(path) -> FileInfo:
    """Identify a file by extension + magic bytes + heuristics."""
    p = Path(path)
    st = p.stat()
    head = _read_head(p, 4096)
    ext = p.suffix.lower()
    kind, desc, via = _detect_kind(head, ext)
    is_text, encoding, sample = _sniff_text(head)
    info = FileInfo(
        path=str(p.resolve()),
        size=st.st_size,
        size_human=_human_size(st.st_size),
        mtime_iso=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        extension=ext,
        detected_kind=kind,
        detected_via=via,
        description=desc,
        is_text=is_text,
        encoding=encoding,
        text_sample=sample,
        hex_preview=_hex_dump(head[:256]),
        suggested_action=_suggest_action(kind, ext),
    )
    return info


def looks_binary(head_bytes: bytes) -> bool:
    """Heuristic: a chunk is "binary" if it has any NULs or has too many
    non-printable bytes. Used by `app.py` to decide whether to route an
    unknown extension through the unknown-file viewer."""
    if not head_bytes: return False
    if b"\x00" in head_bytes: return True
    printable = sum(
        1 for b in head_bytes
        if 32 <= b < 127 or b in (9, 10, 13))   # tab, LF, CR
    return (printable / len(head_bytes)) < 0.85


# ---- internals ----------------------------------------------------------


def _read_head(p: Path, n: int) -> bytes:
    try:
        with open(p, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def _detect_kind(head: bytes, ext: str) -> tuple[str, str, str]:
    # Magic first; cross-reference with extension hint.
    for offset, sig, kind, desc in _MAGIC:
        if len(head) >= offset + len(sig) and head[offset:offset + len(sig)] == sig:
            hint = _EXT_HINTS.get(ext)
            if hint and hint[0] != kind:
                # Magic + extension agree on a more specific kind (e.g. zip + .xlsx).
                return hint[0], hint[1], "extension+magic"
            return kind, desc, "magic"
    if ext in _EXT_HINTS:
        kind, desc = _EXT_HINTS[ext]
        return kind, desc, "extension"
    return "unknown", "Unrecognized file format", "heuristic"


def _sniff_text(head: bytes) -> tuple[bool, str, str]:
    if not head: return False, "", ""
    if b"\x00" in head[:1024]: return False, "", ""
    try:
        import chardet
        guess = chardet.detect(head)
        enc = guess.get("encoding") or ""
        if enc and (guess.get("confidence") or 0) > 0.5:
            try:
                sample = head.decode(enc, errors="replace")[:500]
                return True, enc, sample
            except (LookupError, UnicodeDecodeError):
                pass
    except ImportError:
        pass
    try:
        sample = head.decode("utf-8")[:500]
        return True, "utf-8", sample
    except UnicodeDecodeError:
        return False, "", ""


def _hex_dump(data: bytes, width: int = 16) -> str:
    """Classic 16-byte-row hex dump with ASCII gutter."""
    out: list[str] = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{i:08x}  {hex_part:<{width * 3 - 1}}  {ascii_part}")
    return "\n".join(out)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024: return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _suggest_action(kind: str, ext: str) -> str:
    """Tactical hint for the user / agent. Kept short — the agent can
    elaborate via `analyze_file` and `web_search` (when wired)."""
    hints: dict[str, str] = {
        "parquet":   "Use `pyarrow` or `pandas.read_parquet` to inspect rows.",
        "arrow":     "Use `pyarrow` or `polars` to inspect rows.",
        "feather":   "Use `pyarrow.feather.read_table` or `pandas.read_feather`.",
        "hdf5":      "Use `h5py` to walk groups; `xarray` for labelled NetCDF-style data.",
        "netcdf":    "Use `netCDF4` or `xarray.open_dataset`.",
        "sqlite":    "Open with `sqlite3` (Python stdlib) or any SQLite browser.",
        "npy":       "Load with `numpy.load`.",
        "npz":       "Load with `numpy.load` (returns a dict-like archive).",
        "pickle":    "WARNING: pickle is unsafe for untrusted files. Inspect bytes only.",
        "pickle4":   "WARNING: pickle is unsafe for untrusted files. Inspect bytes only.",
        "pickle5":   "WARNING: pickle is unsafe for untrusted files. Inspect bytes only.",
        "mat":       "Use `scipy.io.loadmat` (or `h5py` for v7.3+ files).",
        "fits":      "Use `astropy.io.fits` to inspect headers and image/table data.",
        "shp":       "Use `geopandas` or `pyshp` (also needs .dbf and .shx siblings).",
        "geojson":   "Plain JSON — TextView's JSON view should handle it.",
        "pcap":      "Use `scapy` or open in Wireshark.",
        "pcapng":    "Use `scapy` or open in Wireshark.",
        "wasm":      "Use `wasmtime` to run; `wabt`'s `wasm-objdump` to inspect.",
        "elf":       "Use `readelf -a` or `objdump -d` to disassemble.",
        "macho32":   "Use `otool -h` (macOS) or `objdump`.",
        "macho64":   "Use `otool -h` (macOS) or `objdump`.",
        "macho64-le":"Use `otool -h` (macOS) or `objdump`.",
        "macho-fat": "Use `lipo -info` to list architectures.",
        "pe":        "Use `pefile` (Python) or `objdump`.",
        "dwg":       "Convert with LibreCAD / `libredwg-converter`.",
        "dxf":       "Use `ezdxf` (Python).",
        "dbc":       "Use `cantools` (Python) to decode CAN messages.",
        "zip":       "Use `unzip -l` or open ZIP-based document with its real handler.",
        "jar":       "Java archive — `jar tf` to list entries.",
        "whl":       "Python wheel — `unzip -l` to list contents.",
        "gzip":      "Decompress with `gunzip` or `gzip -d` first.",
        "bzip2":     "Decompress with `bunzip2` first.",
        "xz":        "Decompress with `xz -d` first.",
        "zstd":      "Decompress with `zstd -d` first.",
        "rar":       "Decompress with `unrar`.",
        "sqlite?":   "Try opening with `sqlite3` — file extension is ambiguous.",
    }
    if kind in hints: return hints[kind]
    if ext in (".bin", ".dat", ".raw"):
        return ("Generic binary container — context-dependent. Ask the chat "
                "agent for likely interpretations, or open in a hex editor.")
    return ("TextView doesn't natively handle this format. Ask the chat "
            "agent (Ctrl+J) — it can identify likely tools and write a "
            "TextView script to handle this extension going forward.")
