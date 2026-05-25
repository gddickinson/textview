"""Format-aware Save As.

When the user saves a `.md` file to `*.html`, the buffer should become
rendered HTML on disk — not a markdown file with a `.html` suffix. This
module is the registry + dispatcher behind that.

Each `Conversion` is a small pure function: takes the source text +
optional `dict` of options, returns either a `str` (text out) or
`bytes` (binary out, e.g. `.xlsx`). Converters can declare third-party
package dependencies; if a dep is missing the converter is filtered
out of `available_conversions()` rather than blowing up.

The high-level entry point is `show_save_as_with_conversion(window)`:
prompts for a destination, detects whether the extension implies a
conversion, asks the user if they want it, and writes either the
converted output or the raw buffer.
"""
from __future__ import annotations

import csv
import importlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PyQt6.QtWidgets import QFileDialog, QMessageBox


@dataclass(frozen=True)
class Conversion:
    id: str
    from_format: str
    to_extension: str       # leading dot, lowercase
    to_format: str          # FORMAT_MAP value of the output (drives reload)
    description: str
    convert: Callable[[str, dict], "str | bytes"]
    requires: tuple[str, ...] = ()


# ---------------------------------------------------------------- helpers --

def _have(modules: Iterable[str]) -> bool:
    for m in modules:
        try:
            importlib.import_module(m)
        except Exception:
            return False
    return True


def _parse_csv(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows: return [], []
    header, body = rows[0], rows[1:]
    return header, body


def _csv_to_records(text: str) -> list[dict]:
    header, body = _parse_csv(text)
    if not header: return []
    return [dict(zip(header, row)) for row in body]


# ---------------------------------------------------------------- converters --

def _md_to_html(text: str, _opts: dict) -> str:
    from markdown import markdown
    body = markdown(text, extensions=["extra", "tables", "fenced_code", "sane_lists"])
    return ("<!doctype html><html><head><meta charset='utf-8'>\n"
            f"</head><body>\n{body}\n</body></html>\n")


def _html_to_md(text: str, _opts: dict) -> str:
    try:
        from markdownify import markdownify  # type: ignore
        return markdownify(text)
    except Exception:
        # Fallback: strip tags. Very lossy but always works.
        import re
        no_tags = re.sub(r"<[^>]+>", "", text)
        return no_tags.strip() + "\n"


def _json_to_yaml(text: str, _opts: dict) -> str:
    import yaml  # type: ignore
    return yaml.safe_dump(json.loads(text), sort_keys=False)


def _yaml_to_json(text: str, _opts: dict) -> str:
    import yaml  # type: ignore
    return json.dumps(yaml.safe_load(text), indent=2) + "\n"


def _json_to_toml(text: str, _opts: dict) -> str:
    import tomli_w  # type: ignore
    return tomli_w.dumps(json.loads(text))


def _toml_to_json(text: str, _opts: dict) -> str:
    import tomllib
    return json.dumps(tomllib.loads(text), indent=2) + "\n"


def _yaml_to_toml(text: str, _opts: dict) -> str:
    import yaml, tomli_w  # type: ignore
    return tomli_w.dumps(yaml.safe_load(text))


def _toml_to_yaml(text: str, _opts: dict) -> str:
    import tomllib, yaml  # type: ignore
    return yaml.safe_dump(tomllib.loads(text), sort_keys=False)


def _csv_to_json(text: str, _opts: dict) -> str:
    return json.dumps(_csv_to_records(text), indent=2) + "\n"


def _csv_to_jsonl(text: str, _opts: dict) -> str:
    out = io.StringIO()
    for rec in _csv_to_records(text):
        out.write(json.dumps(rec) + "\n")
    return out.getvalue()


def _csv_to_xlsx(text: str, _opts: dict) -> bytes:
    import openpyxl  # type: ignore
    header, body = _parse_csv(text)
    wb = openpyxl.Workbook()
    ws = wb.active
    if header: ws.append(header)
    for row in body: ws.append(row)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _csv_to_md(text: str, _opts: dict) -> str:
    header, body = _parse_csv(text)
    if not header: return ""
    sep = ["---"] * len(header)
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in body:
        out.append("| " + " | ".join(row + [""] * (len(header) - len(row))) + " |")
    return "\n".join(out) + "\n"


def _csv_to_html(text: str, _opts: dict) -> str:
    header, body = _parse_csv(text)
    if not header: return "<table></table>\n"
    def esc(s): return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    out = ["<table>", "  <thead><tr>"]
    out += [f"    <th>{esc(h)}</th>" for h in header]
    out += ["  </tr></thead>", "  <tbody>"]
    for row in body:
        out.append("    <tr>")
        out += [f"      <td>{esc(c)}</td>" for c in row]
        out.append("    </tr>")
    out += ["  </tbody>", "</table>"]
    return "\n".join(out) + "\n"


def _json_to_csv(text: str, _opts: dict) -> str:
    """JSON array of homogeneous records → CSV. Non-array JSON is rejected."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("JSON → CSV requires a top-level array of objects.")
    if not data: return ""
    if not all(isinstance(r, dict) for r in data):
        raise ValueError("JSON → CSV requires every element to be an object.")
    # Union of keys, preserving first-seen order.
    cols: list[str] = []
    seen: set[str] = set()
    for rec in data:
        for k in rec:
            if k not in seen:
                cols.append(k); seen.add(k)
    out = io.StringIO()
    w = csv.writer(out); w.writerow(cols)
    for rec in data:
        w.writerow([rec.get(c, "") for c in cols])
    return out.getvalue()


def _md_to_docx(text: str, _opts: dict) -> bytes:
    from .docx_writer import markdown_to_docx_bytes
    return markdown_to_docx_bytes(text)


def _rtf_strip(text: str, _opts: dict) -> str:
    """Best-effort RTF → plain. Strips control words / groups."""
    import re
    s = text
    s = re.sub(r"\\par[d]?", "\n", s)
    s = re.sub(r"\\\w+-?\d* ?", "", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\\\", "\\")
    return s.strip() + "\n"


_CONVERSIONS: list[Conversion] = [
    # Markdown <-> HTML
    Conversion("md_to_html", "markdown", ".html", "html",
               "Markdown → HTML (rendered)", _md_to_html),
    Conversion("html_to_md", "html", ".md", "markdown",
               "HTML → Markdown (best effort)", _html_to_md),

    # JSON / YAML / TOML cross-conversion (each requires the right libs)
    Conversion("json_to_yaml", "json", ".yaml", "yaml",
               "JSON → YAML", _json_to_yaml, requires=("yaml",)),
    Conversion("json_to_yml", "json", ".yml", "yaml",
               "JSON → YAML", _json_to_yaml, requires=("yaml",)),
    Conversion("yaml_to_json", "yaml", ".json", "json",
               "YAML → JSON", _yaml_to_json, requires=("yaml",)),
    Conversion("json_to_toml", "json", ".toml", "toml",
               "JSON → TOML", _json_to_toml, requires=("tomli_w",)),
    Conversion("toml_to_json", "toml", ".json", "json",
               "TOML → JSON", _toml_to_json),  # tomllib is stdlib on 3.11+
    Conversion("yaml_to_toml", "yaml", ".toml", "toml",
               "YAML → TOML", _yaml_to_toml, requires=("yaml", "tomli_w")),
    Conversion("toml_to_yaml", "toml", ".yaml", "yaml",
               "TOML → YAML", _toml_to_yaml, requires=("yaml",)),

    # CSV → many targets
    Conversion("csv_to_json", "csv", ".json", "json",
               "CSV → JSON (array of records)", _csv_to_json),
    Conversion("csv_to_jsonl", "csv", ".jsonl", "json",
               "CSV → JSONL (one record per line)", _csv_to_jsonl),
    Conversion("csv_to_xlsx", "csv", ".xlsx", "plain",
               "CSV → XLSX (Excel)", _csv_to_xlsx, requires=("openpyxl",)),
    Conversion("csv_to_md", "csv", ".md", "markdown",
               "CSV → Markdown table", _csv_to_md),
    Conversion("csv_to_html", "csv", ".html", "html",
               "CSV → HTML table", _csv_to_html),

    # JSON → CSV (homogeneous array only)
    Conversion("json_to_csv", "json", ".csv", "csv",
               "JSON (array of objects) → CSV", _json_to_csv),

    # RTF → plain
    Conversion("rtf_to_txt", "rtf", ".txt", "plain",
               "RTF → plain text (strip markup)", _rtf_strip),

    # Markdown → DOCX (rich text Word document)
    Conversion("md_to_docx", "markdown", ".docx", "docx",
               "Markdown → DOCX (Word document)", _md_to_docx,
               requires=("docx",)),
]


def all_conversions() -> list[Conversion]:
    """Every registered conversion, regardless of dependency availability.

    Use `available_conversions()` for the runtime-filtered list.
    """
    return list(_CONVERSIONS)


def available_conversions() -> list[Conversion]:
    return [c for c in _CONVERSIONS if _have(c.requires)]


def conversions_from(source_format: str) -> list[Conversion]:
    return [c for c in available_conversions() if c.from_format == source_format]


def find_conversion(source_format: str, target_extension: str) -> Conversion | None:
    target_extension = target_extension.lower()
    for c in available_conversions():
        if c.from_format == source_format and c.to_extension == target_extension:
            return c
    return None


# ---------------------------------------------------------------- entry --

def show_save_as_with_conversion(window) -> bool:
    """Save As that offers a format conversion when the chosen extension
    differs from the source format. Returns True if a file was written.
    """
    src_fmt = window._current_format
    suggested = window._current_path or "untitled.txt"
    out, _ = QFileDialog.getSaveFileName(window, "Save as", suggested)
    if not out: return False

    target_ext = Path(out).suffix.lower()
    conv = find_conversion(src_fmt, target_ext)

    # If extension matches the current format (or there's no converter)
    # → write the buffer raw. The reload at the end re-detects format.
    write_converted = False
    if conv is not None:
        ret = QMessageBox.question(
            window, "Convert format?",
            f"Save with conversion?\n\n  {conv.description}\n\n"
            "Choose **No** to write the current buffer as-is "
            "(file extension only, no conversion).",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Cancel: return False
        write_converted = (ret == QMessageBox.StandardButton.Yes)

    try:
        if write_converted and conv is not None:
            window._sync_content()
            result = conv.convert(window._current_content, {})
            if isinstance(result, bytes):
                Path(out).write_bytes(result)
            else:
                Path(out).write_text(result, encoding="utf-8")
        else:
            # Raw save — reuse EditController's prepare path so format-on-save /
            # trim / final-newline still apply when relevant.
            text = window.edit._prepare_save_text()
            Path(out).write_text(text, encoding="utf-8")
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))
        return False

    window.statusBar().showMessage(f"Saved → {out}", 4000)
    # Reload so format detection, syntax highlighting, and view mode all
    # reflect the new on-disk content.
    window.open_file(out, confirm=False)
    return True
