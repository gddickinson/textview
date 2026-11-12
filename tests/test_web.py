"""Web interface tests: every exported endpoint answers, the static build is complete, and the JS engine tests pass.

Run: python -m pytest -q tests/test_web.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # web deps live in requirements-web.txt (the desktop CI job skips these)
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.web.app import STATIC, STATIC_ENDPOINTS, app  # noqa: E402

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and "static/main.js" in r.text


@pytest.mark.parametrize("path", STATIC_ENDPOINTS)
def test_endpoint(path):
    r = client.get("/api" + path)
    assert r.status_code == 200, r.text
    assert r.json() is not None


def test_static_build(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_static
    build_static.build(tmp_path / "site")
    assert (tmp_path / "site" / "index.html").read_text().count("APP_STATIC") == 1
    for path in STATIC_ENDPOINTS:
        assert (tmp_path / "site" / "api" / (path.strip("/") + ".json")).exists()


def test_static_assets_referenced_exist():
    html = (STATIC / "index.html").read_text()
    for name in ("style.css", "main.js"):
        assert f"static/{name}" in html and (STATIC / name).exists()


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_engine():
    tests = sorted(STATIC.glob("*.test.mjs"))
    for t in tests:
        r = subprocess.run(["node", str(t)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


# --- TextView-specific -------------------------------------------------------------------------------------------

def test_info_counts_come_from_the_repo():
    from src.file_loader import FORMAT_MAP
    from src.themes import THEMES
    c = client.get("/api/info").json()["counts"]
    assert c["extensions"] == len(FORMAT_MAP) and c["themes"] == len(THEMES) and c["format_db"] >= 30


def test_every_demo_file_opens():
    items = client.get("/api/files").json()["items"]
    assert {"example.py", "example.csv", "example.docx", "example.pdf", "example.ipynb", "example.xlsx"} <= {i["id"] for i in items}
    for it in items:
        d = client.get("/api/file/" + it["id"]).json()
        assert d["view"] == it["view"], it["id"]


def test_code_tokens_reassemble_text():
    d = client.get("/api/file/example.py").json()
    assert d["lexer"] == "Python" and "".join(t for _, t in d["tokens"]) == d["text"]
    assert any(c.startswith("k") for c, _ in d["tokens"])  # keywords coloured


def test_xlsx_made_by_save_as_reads_back_as_the_csv():
    d = client.get("/api/file/example.xlsx").json()
    assert d["table"]["header"] == ["name", "age", "city", "score"] and len(d["table"]["rows"]) == 6
    assert d["table"]["numeric"] == [False, True, False, True]


def test_rendered_markdown_uses_theme():
    from src.themes import THEMES
    html = client.get("/api/rendered/example.md/dracula").json()["html"]
    assert THEMES["Dracula"]["bg"] in html and "<table>" in html
    assert client.get("/api/rendered/example.py/dracula").status_code == 404


def test_display_defaults_match_settings_dataclass():
    d = client.get("/api/display").json()["defaults"]
    assert d["theme"] == "Solarized Dark" and d["font_size"] == 14 and d["show_line_numbers"] is True


def test_upload_open_and_inspect():
    r = client.post("/api/open", files={"file": ("t.csv", b"a,b\n1,x\n2,y\n")}).json()
    assert r["view"] == "table" and r["table"]["numeric"] == [True, False]
    r = client.post("/api/open", files={"file": ("n.md", b"# Hi\n")}).json()
    assert "Hi</h1>" in r["html_by_theme"]["Light"]
    r = client.post("/api/inspect", files={"file": ("x.pdf", b"\x7fELF" + bytes(30))}).json()
    assert r["info"]["detected_kind"] == "elf" and r["scan"]["risk"] == "dangerous"
    assert "path" not in r["info"]


def test_search_ranks_docs():
    r = client.get("/api/search?q=citations locator").json()
    assert r["hits"] and r["hits"][0]["path"].startswith("docs/")


def test_docs_links_are_rewritten():
    html = client.get("/api/doc/INDEX").json()["html"]
    assert 'href="#/docs/overview"' in html and ".md\"" not in html


def test_format_db_is_bundled_only(monkeypatch, tmp_path):
    from src import format_db
    user = tmp_path / "file_formats.json"
    user.write_text('{"formats": [{"id": "secret-personal", "name": "Mine"}]}')
    monkeypatch.setattr(format_db, "_USER", user)
    ids = {e["id"] for e in client.get("/api/formatdb").json()["entries"]}
    assert "secret-personal" not in ids


def test_static_build_copies_raw_files(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_static
    build_static.build(tmp_path / "site")
    assert (tmp_path / "site" / "api" / "raw" / "example.pdf").read_bytes()[:5] == b"%PDF-"
    assert (tmp_path / "site" / "api" / "shot" / "01_hero.png").exists()


def test_web_samples_are_current(tmp_path):
    pytest.importorskip("PyQt6")  # src/save_as.py (the converters) imports Qt at module level
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_web_samples
    from src.file_loader import load_file
    make_web_samples.build(tmp_path)
    committed = ROOT / "src" / "web" / "samples"
    for name in ("example.yaml", "example.toml"):
        assert (tmp_path / name).read_text() == (committed / name).read_text()
    assert load_file(str(tmp_path / "example.xlsx"))[0] == load_file(str(committed / "example.xlsx"))[0]
    assert (tmp_path / "example.zip").read_bytes() == (committed / "example.zip").read_bytes()


def _close(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(b))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    return a == b


def test_engine_fixture_is_current():
    """tests/fixtures/web_engines.json (used by the JS tests) still matches the Python code (rtol 1e-9)."""
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_web_fixtures
    fresh = json.loads(json.dumps(make_web_fixtures.build()))
    saved = json.loads((ROOT / "tests" / "fixtures" / "web_engines.json").read_text())
    for key in saved:
        if key == "inspect":  # chardet may label pure-ASCII text ascii or utf-8 depending on version
            for f, s in zip(fresh[key], saved[key]):
                for x in (f, s):
                    x["info"]["encoding"] = x["info"]["encoding"].replace("ascii", "utf-8")
        assert _close(fresh[key], saved[key]), key
