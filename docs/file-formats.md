# File formats

Every extension TextView recognises, what mode it opens in, and what
edit / save means for each. Detection happens in
`src/file_loader.py:FORMAT_MAP` (by extension) and `FILENAME_MAP`
(by exact filename, e.g. `Dockerfile`, `Makefile`, `.gitignore`).

## Text & markup

| Extension | Format | Initial mode | Toggle | Editable | Save writes |
| --- | --- | --- | --- | --- | --- |
| `.txt`, `.log`, `.rst` | plain | code | rendered | yes | text as-is |
| `.md`, `.markdown` | markdown | rendered | code | yes | text as-is |
| `.html`, `.htm` | html | rendered | code | yes | text as-is |
| `.xml` | xml | code | rendered | yes | text as-is |
| `.tex`, `.latex`, `.ltx` | latex | code | **PDF** (compile) | yes | text as-is |
| `.bib` | bibtex | code | rendered | yes | text as-is |
| `.adoc`, `.asciidoc`, `.org`, `.typ`, `.mediawiki`, `.wiki`, `.textile`, `.pod` | various | code | rendered | yes | text as-is |

LaTeX is special: **Ctrl+T** or **F6** ("Compile LaTeX → PDF") saves any
pending edits and shells out to `latexmk` / `pdflatex` / `xelatex` /
`lualatex` (auto-picks `xelatex` if the source uses `fontspec`). The
resulting PDF displays via the existing PDF viewer. See
`src/latex_controller.py`.

## Data

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.json` | json | code | rendered | F5 runs `python -m json.tool` to validate + pretty-print |
| `.ndjson`, `.jsonl`, `.geojson` | json | code | rendered | newline-delimited JSON variants |
| `.yaml`, `.yml` | yaml | code | rendered | |
| `.toml` | toml | code | rendered | F5 validates + pretty-prints via `tomllib` |
| `.ini`, `.cfg`, `.conf` | ini | code | rendered | |
| `.csv`, `.tsv`, `.psv`, `.tab` | csv | **table** | code | autodetects delimiter via `csv.Sniffer` |

## Workbooks, databases, archives (table view)

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.xlsx`, `.xlsm`, `.xltx`, `.xltm`, `.xls`, `.ods` | xlsx | **table** | code | XLSX via `openpyxl`; `.xls` lazy-loads `xlrd`; `.ods` lazy-loads `pandas`+`odfpy`. **Table → Switch sheet…** (F4) for multi-sheet workbooks. |
| `.sqlite`, `.sqlite3`, `.db` | sqlite | **table** | code | Read-only via `file:…?mode=ro` URI. First table opens by default. **Switch table…** (F4) and **Run SQL…** (Ctrl+Shift+Q) for ad-hoc SELECTs. |
| `.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`/`.tbz2`, `.tar.xz`/`.txz`, `.7z`, `.jar`, `.war`, `.apk`, `.ipa` | archive | **tree** | markdown TOC | Tree view with text-preview pane; double-click extracts a member. **Run → Archive: extract member… / extract all…**. `.7z` needs `py7zr`. |

## Scientific data (extracted to a table)

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.npy`, `.npz` | numpy | **table** | code | Loaded with `allow_pickle=False`. **F4** switches between arrays in `.npz` bundles. 1D → `value` column, 2D → `col_0`/`col_1`/…, structured → field-name columns, 3D+ → property/value summary. |
| `.mat` | mat | **table** | code | Via `scipy.io.loadmat(simplify_cells=True)`. **F4** switches between variables. Numeric arrays use the same dispatch as NumPy; structs become field/type/value tables. |
| `.parquet`, `.pq`, `.feather`, `.arrow`, `.ipc` | parquet | **table** | code | Via `pyarrow`. Parquet uses `iter_batches` so huge files don't fully materialise. |
| `.h5`, `.hdf5`, `.he5`, `.nc`, `.nc4`, `.cdf` | hdf5 | **table** | code | HDF5 via `h5py`; NetCDF v4 via `h5py` (magic-byte detect), classic NetCDF3 via `netCDF4`. **F4** flat-lists dataset paths across the group tree. |

## Code

~60 source extensions across all major language families:

- **Mainstream**: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.c`, `.cpp`,
  `.cc`, `.h`, `.hpp`, `.java`, `.go`, `.rs`, `.rb`, `.php`, `.sh`,
  `.bash`, `.zsh`, `.css`, `.scss`, `.sql`, `.swift`, `.kt`, `.kts`.
- **Scientific / data**: `.r`, `.rmd`, `.jl`, `.lua`, `.pl`, `.pm`,
  `.hs`, `.lhs`, `.ml`, `.mli`, `.f`, `.f90`, `.f95`, `.f03`, `.erl`,
  `.m` (MATLAB script), `.nb`/`.wl`/`.wls` (Mathematica), `.sas`,
  `.do` (Stata).
- **JVM**: `.scala`, `.sc`, `.groovy`, `.gradle`, `.clj`, `.cljs`,
  `.cljc`, `.edn`.
- **.NET**: `.cs`, `.csx`, `.fs`, `.fsx`, `.fsi`, `.vb`.
- **Modern systems**: `.nim`, `.zig`, `.d`, `.cr`, `.vala`, `.dart`,
  `.ps1`, `.psm1`, `.ex`, `.exs`.
- **Lisp family**: `.rkt`, `.scm`, `.ss`, `.lisp`, `.lsp`, `.cl`, `.el`.
- **Hardware / embedded**: `.ino` (Arduino → C++), `.pde` (Processing
  → Java), `.sol` (Solidity), `.v` / `.sv` / `.svh` (Verilog),
  `.vhd` / `.vhdl` (VHDL).
- **Shaders**: `.glsl`, `.vert`, `.frag`, `.tesc`, `.tese`, `.geom`,
  `.comp`, `.hlsl`, `.fx`.
- **Assembly**: `.asm` (NASM), `.s` / `.S` (GAS).
- **Other**: `.tcl`, `.awk`, `.gnuplot`, `.lean`, `.idr`, `.ada`,
  `.adb`, `.ads`, `.pas`, `.pp`.
- **IaC / DevOps**: `.tf`/`.tfvars` (Terraform), `.hcl`, `.nix`,
  `.proto`, `.capnp`, `.graphql`/`.gql`, `.prisma`, `.env`,
  `.editorconfig`.
- **Build / config (by filename)**: `Dockerfile`, `Makefile`,
  `GNUmakefile`, `CMakeLists.txt`, `Justfile`, `Rakefile`, `Gemfile`,
  `Podfile`, `Vagrantfile`, `Containerfile`, `.gitignore`,
  `.gitattributes`, `.dockerignore`, `package-lock.json`, `yarn.lock`,
  `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `Pipfile.lock`,
  `composer.lock`, `Gemfile.lock`, `go.mod`, `go.sum`.

All open in **code** mode with Pygments syntax highlighting matching
the active theme. LSP integration (when `lsp_enabled`): hover
(Ctrl+Shift+H or auto), go-to-definition (F2), find references
(Shift+F12), diagnostics in the gutter. See **lsp.md**.

## Documents (read-only, extracted to text or rendered HTML)

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.pdf` | pdf | pdf | code | Native page rendering via `QPdfView`. Text-selection, page-by-page search. F5 / Edit refused. |
| `.docx` | docx | rendered | code | Rendered to themed HTML via `mammoth`. Headings, lists, tables, inline images preserved. **Save As → .docx** on a markdown buffer produces a real Word doc (see `docx_writer.py`). |
| `.rtf` | rtf | code | rendered | Extracted to text via `striprtf`. **Save As → .txt** converts to plain. |
| `.epub` | epub | rendered | code | Rendered via `EbookLib`. |
| `.odt` | odt | rendered | code | Plain-text extraction. |

Edit mode is **refused** for these — there's no safe way to write back
to the binary format.

## Images

15 formats: `.png`, `.jpg`/`.jpeg`, `.gif` (animated), `.bmp`, `.webp`
(multi-frame), `.tif`/`.tiff` (multi-page), `.svg`/`.svgz`, `.ico`,
`.heic`/`.heif`, `.jp2`, `.tga`.

Opened in **image** mode. Toggle is a no-op. Operations: zoom in/out
(Ctrl+/-, Ctrl+wheel), fit-to-window (Ctrl+0), rotate (R),
folder-browse (PgUp/PgDn), slideshow (F9). The image panel
(Ctrl+Shift+M) adds brightness/contrast/saturation/gamma sliders, an
RGB histogram, eyedropper (status-bar RGB), and rubberband crop.

## Video & audio

| Family | Extensions | Notes |
| --- | --- | --- |
| Video | `.mp4`, `.mov`, `.m4v`, `.mkv`, `.webm`, `.avi`, `.wmv`, `.flv`, `.mpeg`/`.mpg`, `.ogv`, `.3gp` | Opened in **video** mode with play/pause/stop/scrub/volume bar. |
| Audio | `.mp3`, `.wav`, `.flac`, `.ogg`/`.oga`, `.opus`, `.aac`, `.m4a`, `.wma`, `.aiff`/`.aif`, `.amr`, `.mid`/`.midi` | Same engine, same transport bar; the video surface is replaced with a `♪ filename` panel + decoder-supplied ID3 / Vorbis / MP4 metadata (title / artist / album / year / genre / duration). |

Codec coverage depends on your Qt's FFmpeg build.

## Certificates & keys

| Extension | Format | Initial mode | Notes |
| --- | --- | --- | --- |
| `.pem`, `.crt`, `.cer`, `.der` | cert | rendered | Markdown report: subject, issuer, validity, fingerprints, SANs, public-key algo + size, signature algorithm. Uses `cryptography` (preferred) → `openssl x509 -text` CLI (fallback). |
| `.key` | cert | rendered | Markdown report of banner type + key size only — **the raw key material is never displayed**. |

## Fonts

`.ttf`, `.otf`, `.woff`, `.woff2`, `.ttc`, `.otc`, `.pfb`, `.pfa`
render as an HTML sample sheet — alphabet, digits, pangram at 5 sizes,
every available style with bold/italic applied, Greek + Cyrillic
coverage, ligature/symbol line. The file is loaded into
`QFontDatabase` so `font-family` lookups resolve in the rendered view.

## Subtitles, email, calendar, contacts

| Extension | Format | Notes |
| --- | --- | --- |
| `.srt`, `.vtt` | plain | Subtitle files. |
| `.ass`, `.ssa` | ini | Advanced SubStation Alpha subtitles. |
| `.eml`, `.mbox` | plain | Email. |
| `.ics`, `.vcs`, `.vcf` | plain | iCalendar / vCard. |

## Notebook

`.ipynb` opens in **notebook** mode. See **notebook.md** for the full
viewer / editor / runner.

## Web

URLs and `file://` paths typed via `Open URL…` (Ctrl+L) open in
**web** mode (embedded `QWebEngineView`). Cookies are sandboxed to
`~/.cache/TextView/webengine`.

## Save As with format conversion

`File → Save As…` is **format-aware**. When the chosen extension
differs from the current file's format, TextView offers a converter:

- **Markdown ↔ HTML** (both directions)
- **JSON ↔ YAML ↔ TOML** (all six pairs — needs `pyyaml`, `tomli_w`)
- **CSV → JSON / JSONL / XLSX / Markdown table / HTML table** (XLSX needs `openpyxl`)
- **JSON (array of objects) → CSV**
- **Markdown → DOCX** (rich Word document via `python-docx`)
- **RTF → plain text**

Missing optional libraries make a converter silently unavailable — it
simply doesn't appear in the offered list. After a Save As, TextView
re-opens the new file so view mode / highlighting / edit state follow
the new format. See `src/save_as.py`.

## New from template…

**Ctrl+Alt+N** opens the template picker — ~25 starter files across
**Prose / docs** (README, CHANGELOG, LaTeX article, HTML5),
**Data** (JSON, YAML, TOML, CSV, JSONL), **Code** (Python script,
pytest module, JS / TS / Bash / Rust / Go), **DevOps** (Dockerfile,
.gitignore, GitHub Actions, .editorconfig), **Notebooks** (empty
.ipynb). **Create as untitled** opens the body in an unsaved buffer
and drops you into edit mode; **Save to file…** prompts for a path,
writes, and opens the file through the normal detection pipeline.
See `src/templates.py`.

## Encoding

Text loading uses `chardet` to autodetect, falling back to UTF-8. The
status bar shows the detected encoding. There's an Edit menu option
to convert line endings (LF / CRLF) and indent (tabs ↔ spaces).
