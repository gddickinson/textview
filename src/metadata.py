"""Per-file metadata extraction.

`get_metadata(path, fmt)` returns an ordered dict of section → ordered dict
of key → display-string-value. The MetadataPanel renders these as grouped
form rows. Each format-specific extractor is best-effort: if a library is
missing or the file is malformed, the section is just smaller — never
raises into the caller.
"""
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from .file_loader import humansize


def get_metadata(path, fmt):
    sections = OrderedDict()
    sections["File"] = _file_metadata(path, fmt)
    if fmt == "image":
        sections["Image"] = _image_metadata(path)
    elif fmt == "pdf":
        sections["PDF"] = _pdf_metadata(path)
    elif fmt == "docx":
        sections["Document"] = _docx_metadata(path)
    elif fmt == "epub":
        sections["E-Book"] = _epub_metadata(path)
    # Drop empty sections so the panel doesn't show blank groups.
    return OrderedDict((k, v) for k, v in sections.items() if v)


def _fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "?"


def _file_metadata(path, fmt):
    p = Path(path)
    out = OrderedDict()
    try:
        st = p.stat()
    except OSError as e:
        out["Error"] = str(e)
        return out
    out["Name"] = p.name
    out["Folder"] = str(p.parent)
    out["Size"] = humansize(st.st_size)
    out["Modified"] = _fmt_time(st.st_mtime)
    out["Created"] = _fmt_time(st.st_ctime)
    out["Format"] = fmt
    return out


def _image_metadata(path):
    out = OrderedDict()
    try:
        from PIL import Image, ExifTags
    except ImportError:
        # Fall back to QImageReader for basic dimensions.
        try:
            from PyQt6.QtGui import QImageReader
            r = QImageReader(str(path))
            sz = r.size()
            out["Dimensions"] = f"{sz.width()} × {sz.height()} px"
        except Exception:
            pass
        return out
    try:
        img = Image.open(str(path))
        out["Dimensions"] = f"{img.width} × {img.height} px"
        out["Mode"] = img.mode
        if img.format:
            out["Format"] = img.format
        # DPI / orientation may live in info
        if "dpi" in img.info:
            d = img.info["dpi"]
            out["DPI"] = f"{int(d[0])} × {int(d[1])}"
        # EXIF
        exif = None
        try:
            exif = img.getexif() if hasattr(img, "getexif") else None
        except Exception:
            exif = None
        if exif:
            tag_map = ExifTags.TAGS
            interesting = [
                "Make", "Model", "LensModel", "Software",
                "DateTimeOriginal", "DateTime",
                "ExposureTime", "FNumber", "ISOSpeedRatings",
                "FocalLength", "FocalLengthIn35mmFilm",
                "Flash", "WhiteBalance", "Orientation",
                "Artist", "Copyright",
            ]
            wanted = {name for name in interesting}
            for tag_id, value in exif.items():
                name = tag_map.get(tag_id, str(tag_id))
                if name not in wanted:
                    continue
                out[name] = _format_exif_value(name, value)
            # GPS — pull from a sub-IFD if present
            gps = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
            if gps:
                lat = _gps_to_decimal(gps.get(2), gps.get(1))
                lon = _gps_to_decimal(gps.get(4), gps.get(3))
                if lat is not None and lon is not None:
                    out["GPS"] = f"{lat:.6f}, {lon:.6f}"
    except Exception:
        # Best-effort: if PIL chokes, just omit EXIF.
        pass
    return out


def _format_exif_value(name, value):
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace").rstrip("\x00").strip()
        except Exception:
            value = repr(value)
    if name == "ExposureTime" and hasattr(value, "numerator"):
        if value.denominator and value.numerator:
            return f"{value.numerator}/{value.denominator} s"
    if name == "FNumber" and hasattr(value, "numerator"):
        if value.denominator:
            return f"f/{value.numerator / value.denominator:.1f}"
    if name == "FocalLength" and hasattr(value, "numerator"):
        if value.denominator:
            return f"{value.numerator / value.denominator:.1f} mm"
    return str(value)


def _gps_to_decimal(coord, ref):
    if not coord or not ref:
        return None
    try:
        deg = float(coord[0]); minutes = float(coord[1]); seconds = float(coord[2])
        dec = deg + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W", b"S", b"W"):
            dec = -dec
        return dec
    except Exception:
        return None


def _pdf_metadata(path):
    out = OrderedDict()
    try:
        from pypdf import PdfReader
    except ImportError:
        return out
    try:
        r = PdfReader(str(path))
        meta = r.metadata or {}
        keys = [
            ("/Title", "Title"), ("/Author", "Author"),
            ("/Subject", "Subject"), ("/Keywords", "Keywords"),
            ("/Creator", "Creator"), ("/Producer", "Producer"),
            ("/CreationDate", "Created"), ("/ModDate", "Modified"),
        ]
        for key, label in keys:
            if key in meta and meta[key]:
                out[label] = str(meta[key])
        out["Pages"] = str(len(r.pages))
        out["Encrypted"] = "Yes" if r.is_encrypted else "No"
        # Page size of first page
        try:
            box = r.pages[0].mediabox
            out["Page size"] = f"{float(box.width):.0f} × {float(box.height):.0f} pt"
        except Exception:
            pass
    except Exception:
        pass
    return out


def _docx_metadata(path):
    out = OrderedDict()
    try:
        import docx
    except ImportError:
        return out
    try:
        d = docx.Document(str(path))
        cp = d.core_properties
        for attr, label in [
            ("title", "Title"), ("author", "Author"),
            ("last_modified_by", "Last modified by"),
            ("subject", "Subject"), ("keywords", "Keywords"),
            ("category", "Category"), ("comments", "Comments"),
            ("created", "Created"), ("modified", "Modified"),
            ("revision", "Revision"), ("version", "Version"),
        ]:
            v = getattr(cp, attr, None)
            if v not in (None, "", 0):
                out[label] = str(v)
        out["Paragraphs"] = str(len(d.paragraphs))
        out["Sections"] = str(len(d.sections))
        out["Tables"] = str(len(d.tables))
    except Exception:
        pass
    return out


def _epub_metadata(path):
    out = OrderedDict()
    try:
        from ebooklib import epub
    except ImportError:
        return out
    try:
        book = epub.read_epub(str(path))
        for field, label in [
            ("title", "Title"), ("creator", "Author"),
            ("language", "Language"), ("identifier", "ID / ISBN"),
            ("publisher", "Publisher"), ("date", "Date"),
            ("description", "Description"), ("rights", "Rights"),
        ]:
            vals = book.get_metadata("DC", field)
            if vals:
                out[label] = vals[0][0]
    except Exception:
        pass
    return out
