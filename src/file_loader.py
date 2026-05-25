"""File loading and format detection.

`load_file()` is the single entry point used by the UI. It dispatches to a
document extractor for binary formats (PDF/DOCX/RTF/EPUB/ODT) and falls back
to plain-text reading with encoding probing for everything else.
"""
from pathlib import Path

from .document_extract import (
    extract_pdf, extract_docx, extract_rtf, extract_epub, extract_odt,
    DocumentExtractionError,
)

# Extension → format identifier consumed by the renderer.
FORMAT_MAP = {
    # Plain
    ".txt": "plain", ".log": "plain", ".rst": "plain",
    # Markup
    ".md": "markdown", ".markdown": "markdown",
    ".html": "html", ".htm": "html", ".xml": "xml",
    # Data
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".csv": "csv", ".tsv": "csv", ".psv": "csv", ".tab": "csv",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".conf": "ini",
    # Code
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript",
    ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".h": "c", ".hpp": "cpp",
    ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".css": "css", ".scss": "scss", ".sql": "sql",
    ".swift": "swift", ".kt": "kotlin", ".kts": "kotlin",
    # R, Julia, Lua, Perl, Haskell, OCaml, Elixir, Erlang
    ".r": "r", ".rmd": "markdown",   # Rmd → markdown render; chunks stay code
    ".jl": "julia", ".lua": "lua",
    ".pl": "perl", ".pm": "perl", ".t": "perl",
    ".hs": "haskell", ".lhs": "haskell",
    ".ml": "ocaml", ".mli": "ocaml",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang", ".hrl": "erlang",
    # JVM family
    ".scala": "scala", ".sc": "scala",
    ".groovy": "groovy", ".gradle": "groovy",
    ".clj": "clojure", ".cljs": "clojure", ".cljc": "clojure", ".edn": "clojure",
    # .NET family
    ".cs": "csharp", ".csx": "csharp",
    ".fs": "fsharp", ".fsx": "fsharp", ".fsi": "fsharp",
    ".vb": "vbnet",
    # Systems-y
    ".nim": "nim", ".zig": "zig", ".d": "d", ".cr": "crystal",
    ".vala": "vala",
    ".dart": "dart", ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell",
    # Embedded / hardware adjacent
    ".ino": "cpp",                              # Arduino is C++
    ".pde": "java",                             # Processing is Java
    ".sol": "solidity",
    # Hardware description
    ".v": "verilog", ".sv": "verilog", ".svh": "verilog",
    ".vhd": "vhdl", ".vhdl": "vhdl",
    # Shaders
    ".glsl": "glsl", ".vert": "glsl", ".frag": "glsl",
    ".tesc": "glsl", ".tese": "glsl", ".geom": "glsl", ".comp": "glsl",
    ".hlsl": "hlsl", ".fx": "hlsl",
    # Assembly
    ".asm": "nasm", ".s": "gas", ".S": "gas",
    # Fortran
    ".f": "fortran", ".f77": "fortran", ".f90": "fortran",
    ".f95": "fortran", ".f03": "fortran", ".f08": "fortran", ".for": "fortran",
    # Build / config
    ".cmake": "cmake",
    ".dockerfile": "dockerfile",
    ".mk": "make",
    ".mak": "make",
    ".ipynb": "notebook",
    # Spreadsheets — extracted to CSV text and displayed in TableView.
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".xltx": "xlsx", ".xltm": "xlsx",
    ".xls": "xlsx", ".ods": "xlsx",
    # SQLite databases — browsed table-by-table through TableView.
    ".sqlite": "sqlite", ".sqlite3": "sqlite", ".db": "sqlite",
    # NumPy array files — extracted to CSV like spreadsheets.
    ".npy": "numpy", ".npz": "numpy",
    # MATLAB binary — extracted to CSV via scipy.io.
    ".mat": "mat",
    # Apache Parquet / Arrow Feather — extracted to CSV via pyarrow.
    ".parquet": "parquet", ".pq": "parquet",
    ".feather": "parquet", ".arrow": "parquet", ".ipc": "parquet",
    # HDF5 / NetCDF hierarchical scientific data.
    ".h5": "hdf5", ".hdf5": "hdf5", ".he5": "hdf5",
    ".nc": "hdf5", ".nc4": "hdf5", ".cdf": "hdf5",
    # 3D meshes — rendered as a matplotlib 3D preview + stats panel.
    ".stl": "mesh", ".obj": "mesh", ".ply": "mesh",
    ".glb": "mesh", ".gltf": "mesh", ".dae": "mesh",
    ".3mf": "mesh", ".off": "mesh", ".x3d": "mesh",
    # Blender — no Python reader, identified for metadata only.
    ".blend": "blend",
    # X.509 certificates + PEM keys — rendered as a markdown report.
    ".pem": "cert", ".crt": "cert", ".cer": "cert", ".der": "cert",
    ".key": "cert",
    # Font files — rendered as an HTML sample sheet (the rendered view
    # picks up `font-family` once QFontDatabase has registered the file).
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
    ".ttc": "font", ".otc": "font", ".pfb": "font", ".pfa": "font",
    # Archives — rendered as a markdown table of contents; menu actions
    # extract members. Note .jar/.war/.apk/.epub are also ZIP files but
    # we route them based on listing intent rather than mime.
    ".zip": "archive", ".jar": "archive", ".war": "archive",
    ".apk": "archive", ".ipa": "archive",
    ".tar": "archive", ".tgz": "archive", ".tbz2": "archive",
    ".txz": "archive", ".tb2": "archive",
    ".7z": "archive",
    # LaTeX source — edited as text, can be compiled to PDF on demand.
    ".tex": "latex", ".latex": "latex", ".ltx": "latex",
    ".bib": "bibtex",
    # Markup / documentation alternatives
    ".typ": "typst",
    ".org": "org",
    ".adoc": "plain", ".asciidoc": "plain",   # Pygments has no AsciiDoc lexer
    ".mediawiki": "wikitext", ".wiki": "wikitext",
    ".textile": "plain",
    ".pod": "perl",                            # Plain Old Documentation
    # IaC / DevOps configuration as code
    ".tf": "terraform", ".tfvars": "terraform",
    ".hcl": "hcl", ".nix": "nix",
    ".proto": "protobuf", ".capnp": "capnp",
    ".graphql": "graphql", ".gql": "graphql",
    ".prisma": "graphql",
    ".env": "bash",                            # KEY=VALUE — bash highlights fine
    ".editorconfig": "ini",
    # Newline-delimited JSON variants
    ".ndjson": "json", ".jsonl": "json", ".geojson": "json",
    # Subtitles
    ".srt": "plain", ".vtt": "plain",
    ".ass": "ini", ".ssa": "ini",
    # Email / calendar / contacts
    ".eml": "plain", ".mbox": "plain",
    ".ics": "plain", ".vcs": "plain", ".vcf": "plain",
    # More languages
    ".rkt": "racket",
    ".scm": "scheme", ".ss": "scheme",
    ".lisp": "common-lisp", ".lsp": "common-lisp", ".cl": "common-lisp",
    ".el": "elisp",
    ".tcl": "tcl",
    ".awk": "awk",
    ".gnuplot": "gnuplot", ".gp": "gnuplot",
    ".lean": "lean4",
    ".idr": "idris",
    ".ada": "ada", ".adb": "ada", ".ads": "ada",
    ".pas": "delphi", ".pp": "delphi",
    ".m": "matlab",                            # also Objective-C; matlab is more common in this app's audience
    ".nb": "mathematica", ".wl": "mathematica", ".wls": "mathematica",
    ".sas": "sas",
    ".do": "stata",
    # Audio (played via QMediaPlayer, no text content)
    ".mp3": "audio", ".wav": "audio", ".flac": "audio",
    ".ogg": "audio", ".oga": "audio", ".opus": "audio",
    ".aac": "audio", ".m4a": "audio", ".wma": "audio",
    ".aiff": "audio", ".aif": "audio", ".amr": "audio",
    ".mid": "audio", ".midi": "audio",
    # Documents (extracted to text)
    ".pdf": "pdf", ".docx": "docx", ".rtf": "rtf",
    ".epub": "epub", ".odt": "odt",
    # Images (rendered, no text content)
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".webp": "image", ".tif": "image", ".tiff": "image",
    ".svg": "image", ".svgz": "image", ".ico": "image", ".heic": "image",
    ".heif": "image", ".jp2": "image", ".tga": "image",
    # Video / movies (played back via QtMultimedia)
    ".mp4": "video", ".mov": "video", ".m4v": "video", ".mkv": "video",
    ".webm": "video", ".avi": "video", ".wmv": "video", ".flv": "video",
    ".mpeg": "video", ".mpg": "video", ".ogv": "video", ".3gp": "video",
}

DOCUMENT_FORMATS = {"pdf", "docx", "rtf", "epub", "odt"}
IMAGE_FORMATS = {"image"}
VIDEO_FORMATS = {"video"}
AUDIO_FORMATS = {"audio"}
# Media that go through QMediaPlayer rather than the text pipeline.
MEDIA_FORMATS = VIDEO_FORMATS | AUDIO_FORMATS
# Formats that get the TableView treatment (filter bar, sorting, derived
# columns). All non-CSV members are extracted to CSV text under the hood
# so this stays cohesive — see the respective `*_loader.py` modules.
TABLE_FORMATS = {"csv", "xlsx", "sqlite", "numpy", "mat", "parquet", "hdf5"}

ENCODINGS_TO_TRY = ["utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1252"]


# Filenames recognised regardless of extension (build files etc.).
FILENAME_MAP = {
    "dockerfile": "dockerfile",
    "containerfile": "dockerfile",
    "makefile": "make",
    "gnumakefile": "make",
    "cmakelists.txt": "cmake",
    "justfile": "make",          # Pygments has no justfile lexer; closest match
    "rakefile": "ruby",
    "gemfile": "ruby",
    "podfile": "ruby",
    "vagrantfile": "ruby",
    "fastfile": "ruby",
    # Common "no extension" config/dotfiles
    ".gitignore": "ini", ".gitattributes": "ini",
    ".dockerignore": "ini",
    ".editorconfig": "ini",
    ".env": "bash",
    ".npmrc": "ini", ".yarnrc": "ini",
    # Lock files — JSON content is most common; the YAML lock files (poetry / pubspec)
    # are tagged accordingly.
    "package-lock.json": "json",
    "yarn.lock": "yaml",
    "pnpm-lock.yaml": "yaml",
    "cargo.lock": "toml",
    "poetry.lock": "toml",
    "pipfile.lock": "json",
    "composer.lock": "json",
    "gemfile.lock": "ruby",
    "go.sum": "plain", "go.mod": "plain",
}


def detect_format(path) -> str:
    p = Path(path)
    by_name = FILENAME_MAP.get(p.name.lower())
    if by_name: return by_name
    # Compound extensions like `.tar.gz`/`.tar.bz2`/`.tar.xz` aren't
    # captured by Path.suffix — consult the archive loader's compound-
    # aware detector before falling back to single-suffix lookup.
    name_lower = p.name.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst"):
        if name_lower.endswith(compound):
            return "archive"
    # Use the original suffix (case-sensitive) for `.S` (gas) so it doesn't
    # collide with `.s` — both still resolve via FORMAT_MAP, but cmake / make
    # and other lowercase-only entries still work.
    suffix = p.suffix
    return FORMAT_MAP.get(suffix, FORMAT_MAP.get(suffix.lower(), "plain"))


def is_document(path) -> bool:
    return detect_format(path) in DOCUMENT_FORMATS


def is_image(path) -> bool:
    return detect_format(path) in IMAGE_FORMATS


def is_video(path) -> bool:
    return detect_format(path) in VIDEO_FORMATS


def is_audio(path) -> bool:
    return detect_format(path) in AUDIO_FORMATS


def is_media(path) -> bool:
    return detect_format(path) in MEDIA_FORMATS


def supported_extensions():
    return sorted(FORMAT_MAP.keys())


def file_dialog_filter() -> str:
    """Return a filter string for QFileDialog covering everything we support."""
    code_exts = (
        ".py .js .ts .tsx .jsx .c .cpp .h .hpp .java .go .rs .rb .php "
        ".sh .bash .zsh .css .scss .sql .swift .kt .kts "
        ".r .rmd .jl .lua .pl .pm .hs .ml .ex .exs .erl "
        ".scala .groovy .gradle .clj .cljs .edn "
        ".cs .csx .fs .fsx .vb "
        ".nim .zig .d .cr .vala .dart .ps1 "
        ".ino .pde .sol .v .sv .vhd .vhdl "
        ".glsl .vert .frag .hlsl "
        ".asm .s .S .f .f90 .f95"
    )
    return ";;".join([
        "All supported (*.txt *.log *.md *.markdown *.rst *.html *.htm *.xml "
        "*.json *.yaml *.yml *.csv *.tsv *.toml *.ini *.cfg *.conf "
        f"{code_exts.replace('.', '*.')} *.tex *.latex *.ltx "
        "*.pdf *.docx *.rtf *.epub *.odt)",
        "Text (*.txt *.log *.rst)",
        "Markdown (*.md *.markdown)",
        "Markup (*.html *.htm *.xml)",
        "Data (*.json *.yaml *.yml *.csv *.tsv *.toml *.ini *.cfg *.conf)",
        "Spreadsheets (*.xlsx *.xlsm *.xltx *.xltm *.xls *.ods)",
        "SQLite databases (*.sqlite *.sqlite3 *.db)",
        "NumPy arrays (*.npy *.npz)",
        "MATLAB / Parquet / HDF5 (*.mat *.parquet *.feather *.arrow *.h5 *.hdf5 *.nc *.nc4)",
        "3D meshes (*.stl *.obj *.ply *.glb *.gltf *.dae *.3mf *.off *.x3d)",
        "Blender (*.blend)",
        "Certificates / keys (*.pem *.crt *.cer *.der *.key)",
        "Fonts (*.ttf *.otf *.woff *.woff2 *.ttc *.otc *.pfb *.pfa)",
        "Archives (*.zip *.tar *.tar.gz *.tgz *.tar.bz2 *.tbz2 *.tar.xz *.txz *.7z *.jar *.war *.apk)",
        f"Code ({code_exts.replace('.', '*.')})",
        "LaTeX (*.tex *.latex *.ltx *.bib)",
        "Markup / docs (*.adoc *.asciidoc *.org *.typ *.mediawiki *.wiki *.textile)",
        "DevOps / IaC (*.tf *.tfvars *.hcl *.nix *.proto *.graphql *.gql *.prisma)",
        "JSON variants (*.json *.ndjson *.jsonl *.geojson)",
        "Email / calendar / contacts (*.eml *.mbox *.ics *.vcs *.vcf)",
        "Subtitles (*.srt *.vtt *.ass *.ssa)",
        "Documents (*.pdf *.docx *.rtf *.epub *.odt)",
        "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff *.svg *.ico *.heic *.heif *.jp2 *.tga)",
        "Video (*.mp4 *.mov *.m4v *.mkv *.webm *.avi *.wmv *.flv *.mpeg *.mpg *.ogv *.3gp)",
        "Audio (*.mp3 *.wav *.flac *.ogg *.oga *.opus *.aac *.m4a *.wma *.aiff *.aif *.amr *.mid *.midi)",
        "All Files (*)",
    ])


def _read_text(path):
    """Try several encodings before falling back to replacement."""
    for enc in ENCODINGS_TO_TRY:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except UnicodeDecodeError:
            continue
    # Final fallback: replace undecodable bytes
    try:
        import chardet
        raw = Path(path).read_bytes()
        guess = chardet.detect(raw)
        enc = guess.get("encoding") or "utf-8"
        return raw.decode(enc, errors="replace"), f"{enc} (chardet)"
    except Exception:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), "utf-8 (with replacement)"


def load_file(path):
    """Load a file. Returns (content, encoding_label, format).

    Raises FileNotFoundError if the path doesn't exist or PermissionError on
    access denial. Document-extraction failures bubble up as
    DocumentExtractionError.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    fmt = detect_format(p)

    if fmt in IMAGE_FORMATS or fmt in MEDIA_FORMATS:
        # Images / video / audio are loaded by their dedicated viewer
        # widget, not by this function. Return an empty content string so
        # callers can still set up the status bar / format label etc.
        return "", "binary", fmt

    if fmt in DOCUMENT_FORMATS:
        extractor = {
            "pdf": extract_pdf,
            "docx": extract_docx,
            "rtf": extract_rtf,
            "epub": extract_epub,
            "odt": extract_odt,
        }[fmt]
        text = extractor(str(p))
        return text, f"{fmt} → text", fmt

    if fmt == "xlsx":
        # Extract the first sheet to CSV text; MainWindow handles sheet
        # switching for multi-sheet workbooks.
        from .spreadsheet_loader import load_sheet_as_csv, list_sheets
        sheets = list_sheets(str(p))
        sheet_label = sheets[0] if sheets else "(empty)"
        csv_text = load_sheet_as_csv(str(p), 0)
        return csv_text, f"{p.suffix.lstrip('.')} · sheet={sheet_label}", fmt

    if fmt == "sqlite":
        # For ambiguous `.db` files, sniff magic bytes before trusting
        # the extension — Berkeley DB / LevelDB / etc. live here too.
        from .sqlite_loader import looks_like_sqlite, list_tables, load_table_as_csv
        if p.suffix.lower() == ".db" and not looks_like_sqlite(p):
            text, encoding = _read_text(str(p))
            return text, encoding, "plain"
        tables = list_tables(str(p))
        first = tables[0] if tables else None
        if first is None:
            return "", f"{p.suffix.lstrip('.')} · (no tables)", fmt
        csv_text = load_table_as_csv(str(p), first)
        return csv_text, f"{p.suffix.lstrip('.')} · table={first}", fmt

    if fmt == "archive":
        # Listing rendered as markdown so the viewer's existing markdown
        # pipeline handles theming, syntax, copy-paste, search.
        from .archive_loader import render_listing_markdown
        md = render_listing_markdown(str(p))
        return md, "archive listing", fmt

    if fmt == "numpy":
        from .numpy_loader import list_arrays, load_array_as_csv, array_metadata
        names = list_arrays(str(p))
        first = names[0] if names else "array"
        csv_text = load_array_as_csv(str(p), first)
        try:
            meta = array_metadata(str(p), first)
            label = f"{p.suffix.lstrip('.')} · {first} · shape={meta['shape']} dtype={meta['dtype']}"
        except Exception:
            label = f"{p.suffix.lstrip('.')} · {first}"
        return csv_text, label, fmt

    if fmt == "cert":
        from .cert_loader import render_markdown
        md = render_markdown(str(p))
        return md, "certificate report", fmt

    if fmt == "font":
        from .font_loader import load_and_render
        html = load_and_render(str(p))
        return html, "font sample", fmt

    if fmt == "mat":
        from .mat_loader import list_variables, load_variable_as_csv
        names = list_variables(str(p))
        first = names[0] if names else None
        if first is None:
            return "", f"mat · (no variables)", fmt
        csv_text = load_variable_as_csv(str(p), first)
        return csv_text, f"mat · variable={first}", fmt

    if fmt == "parquet":
        from .parquet_loader import read_as_csv, file_metadata
        csv_text = read_as_csv(str(p))
        try:
            meta = file_metadata(str(p))
            label = f"{p.suffix.lstrip('.')} · {meta['rows']:,} rows × {len(meta['columns'])} cols"
        except Exception:
            label = f"{p.suffix.lstrip('.')}"
        return csv_text, label, fmt

    if fmt == "hdf5":
        from .hdf5_loader import list_datasets, load_dataset_as_csv
        names = list_datasets(str(p))
        first = names[0] if names else None
        if first is None:
            return "", f"hdf5 · (no datasets)", fmt
        csv_text = load_dataset_as_csv(str(p), first)
        return csv_text, f"{p.suffix.lstrip('.')} · dataset={first}", fmt

    if fmt == "mesh":
        # The MeshView widget loads via `trimesh` directly; we just
        # return an empty body so MainWindow knows to dispatch to it.
        return "", f"{p.suffix.lstrip('.')} mesh", fmt

    if fmt == "blend":
        # `.blend` has no Python reader — render a metadata report
        # through the existing markdown view.
        from .blend_inspector import render_markdown
        return render_markdown(str(p)), "blender file", fmt

    text, encoding = _read_text(str(p))
    return text, encoding, fmt


def file_info(path):
    p = Path(path)
    stat = p.stat()
    return {
        "name": p.name,
        "size": stat.st_size,
        "format": detect_format(path),
        "path": str(p.resolve()),
    }


def humansize(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
