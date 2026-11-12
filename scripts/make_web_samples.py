"""Generate the extra demo files for the web viewer from the repo's own sample_files/.

Each file is produced by TextView's own Save As converters (src/save_as.py), so the web demo shows formats the
desktop app writes as well as reads:

    example.yaml / example.toml  <- sample_files/example.json  (JSON -> YAML / TOML)
    example.xlsx                 <- sample_files/example.csv   (CSV -> XLSX)
    example.zip                  <- three sample files, fixed timestamps (archive view)

Run: python scripts/make_web_samples.py   (writes src/web/samples/; tests/test_web.py checks they are current)
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import save_as  # noqa: E402

SRC = ROOT / "sample_files"
OUT = ROOT / "src" / "web" / "samples"
ZIP_MEMBERS = ["example.md", "example.py", "example.csv"]
ZIP_DATE = (2026, 1, 1, 12, 0, 0)


def build(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    js = (SRC / "example.json").read_text()
    csv = (SRC / "example.csv").read_text()
    written = []
    for name, data in (("example.yaml", save_as._json_to_yaml(js, {})),
                       ("example.toml", save_as._json_to_toml(js, {})),
                       ("example.xlsx", save_as._csv_to_xlsx(csv, {}))):
        p = out / name
        (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)
        written.append(p)
    z = out / "example.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in ZIP_MEMBERS:
            info = zipfile.ZipInfo(f"sample_files/{m}", ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (SRC / m).read_bytes())
    written.append(z)
    return written


if __name__ == "__main__":
    for p in build():
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
