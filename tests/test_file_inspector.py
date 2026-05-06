"""file_inspector: identification + hex preview + binary detection."""
from src.file_inspector import (
    inspect_file, looks_binary, maybe_unknown_file_report,
    _hex_dump, _human_size,
)


def test_looks_binary_empty():
    assert looks_binary(b"") is False


def test_looks_binary_text():
    assert looks_binary(b"Hello, world.\nThis is plain text.\n") is False


def test_looks_binary_with_nul():
    assert looks_binary(b"hi\x00there") is True


def test_looks_binary_high_bytes():
    assert looks_binary(bytes(range(128, 200))) is True


def test_human_size_units():
    assert _human_size(0).startswith("0")
    assert "KB" in _human_size(2048)
    assert "MB" in _human_size(2 * 1024 * 1024)


def test_hex_dump_format():
    out = _hex_dump(b"hello world", width=8)
    # Each row: "00000000  hex... ASCII"
    assert "68 65 6c 6c" in out  # bytes for "hell"
    assert "hello" in out


def test_inspect_file_text(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("hello", encoding="utf-8")
    info = inspect_file(p)
    assert info.is_text
    assert info.detected_kind in ("unknown", "text")  # ext .txt isn't in hints
    assert info.size == 5


def test_inspect_file_pdf_magic(tmp_path):
    p = tmp_path / "x.pdf"; p.write_bytes(b"%PDF-1.7\nbody bytes")
    info = inspect_file(p)
    assert info.detected_kind == "pdf"
    assert "magic" in info.detected_via


def test_inspect_file_parquet_magic(tmp_path):
    p = tmp_path / "x.parquet"; p.write_bytes(b"PAR1\x00\x01\x02\x03\x04")
    info = inspect_file(p)
    assert info.detected_kind == "parquet"
    assert "Parquet" in info.description


def test_inspect_file_extension_hint_when_no_magic(tmp_path):
    """A `.parquet` file that doesn't start with PAR1 still gets the
    hint description from the extension."""
    p = tmp_path / "broken.parquet"; p.write_bytes(b"\x00garbage")
    info = inspect_file(p)
    assert info.detected_kind == "parquet"
    assert info.detected_via == "extension"


def test_inspect_file_unknown_extension(tmp_path):
    p = tmp_path / "x.weirdext"; p.write_bytes(b"\x00\x01\x02\x03")
    info = inspect_file(p)
    assert info.detected_kind == "unknown"


def test_inspect_file_zip_magic(tmp_path):
    p = tmp_path / "doc.docx"; p.write_bytes(b"PK\x03\x04rest")
    info = inspect_file(p)
    # Magic + extension agree (zip + .docx isn't in our hints, falls back to magic).
    assert info.detected_kind in ("zip", "zip-empty")


def test_to_markdown_includes_essentials(tmp_path):
    p = tmp_path / "x.parquet"; p.write_bytes(b"PAR1\x00\x01\x02")
    info = inspect_file(p)
    md = info.to_markdown()
    assert "# x.parquet" in md
    assert "Apache Parquet" in md
    assert "## Hex preview" in md
    assert "Ask the chat agent" in md


def test_maybe_unknown_file_report_text_returns_none(tmp_path):
    p = tmp_path / "n.txt"; p.write_text("hello", encoding="utf-8")
    assert maybe_unknown_file_report(p) is None


def test_maybe_unknown_file_report_binary_returns_markdown(tmp_path):
    p = tmp_path / "x.parquet"; p.write_bytes(b"PAR1\x00\x01\x02\x03\x04\x05")
    rep = maybe_unknown_file_report(p)
    assert rep is not None
    md, kind = rep
    assert kind == "parquet"
    assert "Apache Parquet" in md


def test_maybe_unknown_file_report_includes_handler_when_registered(tmp_path, monkeypatch):
    """If a format handler is registered for the extension, the markdown
    notes it."""
    from src import format_handlers as fh
    # Redirect registry to a temp file.
    cfg = tmp_path / "fh.json"
    monkeypatch.setattr(fh, "_registry_path", lambda: cfg)
    fh.register(".weirdbin", "show_weirdbin", description="prints summary")
    p = tmp_path / "x.weirdbin"; p.write_bytes(b"\x00\x01\x02\x03\x04")
    rep = maybe_unknown_file_report(p)
    assert rep is not None
    md, _kind = rep
    assert "handler is registered" in md
    assert "show_weirdbin" in md
