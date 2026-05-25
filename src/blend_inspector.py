"""Best-effort `.blend` (Blender) file inspector.

There is no realistic open-source Python reader for `.blend` files
in 2026 — the format is private to Blender and the only complete
parser ships inside Blender itself. What we **can** do is read the
12-byte header to identify the file and surface its metadata:

  Bytes 0..6:    "BLENDER"
  Byte 7:        pointer size — '_' (4 bytes) or '-' (8 bytes)
  Byte 8:        endianness   — 'v' (little) or 'V' (big)
  Bytes 9..11:   version, e.g. "404" → Blender 4.4

The viewer then renders a Markdown report telling the user to open
the file in Blender or its free Blend Viewer; for any actual mesh
extraction they should export from Blender as `.stl` / `.obj` /
`.glb` (all of which TextView reads).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_BLEND_MAGIC = b"BLENDER"


@dataclass
class BlendHeader:
    """Parsed 12-byte `.blend` header."""
    pointer_size: int            # 4 or 8 (bytes)
    endianness: str              # "little" or "big"
    version: str                 # e.g. "4.04" formatted from "404"


class BlendInspectError(Exception):
    pass


def is_blend_file(path) -> bool:
    """Magic-byte check — `.blend` always starts with `b'BLENDER'`."""
    try:
        with open(path, "rb") as f:
            return f.read(7) == _BLEND_MAGIC
    except OSError:
        return False


def read_header(path: str) -> BlendHeader:
    """Parse the 12-byte header. Raises `BlendInspectError` if the
    file doesn't start with `BLENDER` or is too short."""
    src = Path(path)
    if not src.is_file():
        raise BlendInspectError(f"File not found: {path}")
    try:
        with open(src, "rb") as f:
            head = f.read(12)
    except OSError as e:
        raise BlendInspectError(f"Could not read file: {e}") from e
    if len(head) < 12 or head[:7] != _BLEND_MAGIC:
        raise BlendInspectError(
            f"Not a Blender .blend file (magic bytes mismatch).")
    # Byte 7 = pointer size, 8 = endianness, 9..11 = version.
    ptr_char = head[7:8]
    end_char = head[8:9]
    ver_bytes = head[9:12]
    pointer_size = 4 if ptr_char == b"_" else 8 if ptr_char == b"-" else 0
    endianness = ("little" if end_char == b"v"
                  else "big" if end_char == b"V" else "unknown")
    try:
        ver_str = ver_bytes.decode("ascii")
        # Version is 3-digit packed: "404" → "4.04".
        version = f"{ver_str[0]}.{ver_str[1:]}"
    except UnicodeDecodeError:
        version = ver_bytes.hex()
    return BlendHeader(
        pointer_size=pointer_size,
        endianness=endianness,
        version=version,
    )


def render_markdown(path: str) -> str:
    """Format the inspection result as a Markdown report for the
    rendered viewer."""
    src = Path(path)
    try:
        header = read_header(str(src))
    except BlendInspectError as e:
        return f"# Blender file\n\n**Error**: {e}\n"
    size = src.stat().st_size if src.is_file() else 0
    lines = [
        f"# Blender project: `{src.name}`",
        "",
        f"- **Blender version**: {header.version}",
        f"- **Pointer size**: {header.pointer_size or '?'} bytes",
        f"- **Endianness**: {header.endianness}",
        f"- **File size**: {size:,} bytes",
        "",
        "> **TextView does not parse `.blend` files.** No open-source "
        "Python reader for Blender's proprietary format exists; the only "
        "complete parser ships inside Blender itself.",
        "",
        "**To inspect or edit the contents**:",
        "",
        "- Open in **Blender** (free, multi-platform: <https://www.blender.org/>).",
        "- Or use **Blender's free Blend Viewer** for read-only viewing.",
        "",
        "**To extract meshes for TextView**:",
        "Export from Blender as `.stl`, `.obj`, or `.glb` — TextView "
        "renders all of those directly via the 3D mesh viewer "
        "(`trimesh` + matplotlib).",
    ]
    return "\n".join(lines) + "\n"
