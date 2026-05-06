# File formats

Every extension TextView recognizes, what mode it opens in, and what
edit/save means for each. The format is detected by extension via
`src/file_loader.py:FORMAT_MAP`.

## Text & markup

| Extension | Format | Initial mode | Toggle | Editable | Save writes |
| --- | --- | --- | --- | --- | --- |
| `.txt`, `.log`, `.rst` | plain | code | rendered | yes | text as-is |
| `.md`, `.markdown` | markdown | rendered | code | yes | text as-is |
| `.html`, `.htm` | html | rendered | code | yes | text as-is |
| `.xml` | xml | code | rendered | yes | text as-is |

In the **rendered** mode, markdown becomes HTML via `markdown` (Python
package) and HTML is shown directly in a `QTextBrowser`. Editing is
done in the **code** mode (Ctrl+T to toggle), and changes round-trip
through `_current_content` so toggling back to rendered reflects edits
immediately.

## Data

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.json` | json | code | rendered (escape-to-html) | F5 runs `python -m json.tool` to validate + pretty-print |
| `.yaml`, `.yml` | yaml | code | rendered | |
| `.toml` | toml | code | rendered | F5 validates + pretty-prints via `tomllib` |
| `.ini`, `.cfg`, `.conf` | ini | code | rendered | |
| `.csv`, `.tsv`, `.psv`, `.tab` | csv | **table** | code | autodetects delimiter via `csv.Sniffer` |

CSV is special: it opens in **table** mode by default. Toggle (Ctrl+T)
flips to a code view of the raw text. Edits in either mode propagate to
the other; save writes the table model serialized through `csv.writer`.

## Code

70+ source extensions across all major language families:

- **Mainstream**: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.c`, `.cpp`,
  `.cc`, `.h`, `.hpp`, `.java`, `.go`, `.rs`, `.rb`, `.php`, `.sh`,
  `.bash`, `.zsh`, `.css`, `.scss`, `.sql`, `.swift`, `.kt`, `.kts`.
- **Scientific / data**: `.r`, `.rmd`, `.jl`, `.lua`, `.pl`, `.pm`,
  `.hs`, `.lhs`, `.ml`, `.mli`, `.f`, `.f90`, `.f95`, `.f03`, `.erl`.
- **JVM**: `.scala`, `.sc`, `.groovy`, `.gradle`, `.clj`, `.cljs`,
  `.cljc`, `.edn`.
- **.NET**: `.cs`, `.csx`, `.fs`, `.fsx`, `.fsi`, `.vb`.
- **Modern systems**: `.nim`, `.zig`, `.d`, `.cr`, `.vala`, `.dart`,
  `.ps1`, `.psm1`, `.ex`, `.exs`.
- **Hardware / embedded**: `.ino` (Arduino → C++), `.pde` (Processing
  → Java), `.sol` (Solidity), `.v` / `.sv` / `.svh` (Verilog), `.vhd`
  / `.vhdl` (VHDL).
- **Shaders**: `.glsl`, `.vert`, `.frag`, `.tesc`, `.tese`, `.geom`,
  `.comp`, `.hlsl`, `.fx`.
- **Assembly**: `.asm` (NASM), `.s` / `.S` (GAS).
- **Build / config (by filename)**: `Dockerfile`, `Makefile`,
  `GNUmakefile`, `CMakeLists.txt`, `Justfile`, `Rakefile`, `Gemfile`,
  `Podfile`, `Vagrantfile`, `Containerfile`.

All open in **code** mode with Pygments syntax highlighting matching
the active theme.

LSP integration (when `lsp_enabled`): hover (Ctrl+Shift+H or auto),
go-to-definition (F2), find references (Shift+F12), diagnostics in the
gutter. See **lsp.md**.

## Documents (read-only, extracted to text or rendered HTML)

| Extension | Format | Initial mode | Toggle | Notes |
| --- | --- | --- | --- | --- |
| `.pdf` | pdf | pdf | code | Native page rendering via `QPdfView`. Text-selection, page-by-page search. F5 / Edit refused. |
| `.docx` | docx | rendered | code | Rendered to themed HTML via `mammoth`. Headings, lists, tables, inline images preserved. |
| `.rtf` | rtf | code | rendered | Extracted to text via `striprtf`. |
| `.epub` | epub | rendered | code | Rendered via `EbookLib`. |
| `.odt` | odt | rendered | code | Plain-text extraction. |

Edit mode is **refused** for these — there's no safe way to write back
to the binary format.

## Images

15 formats: `.png`, `.jpg`/`.jpeg`, `.gif` (animated), `.bmp`, `.webp`
(multi-frame), `.tif`/`.tiff` (multi-page), `.svg`, `.ico`,
`.heic`/`.heif`, `.jp2`, `.tga`.

Opened in **image** mode. Toggle is a no-op. Operations: zoom in/out
(Ctrl+/-, Ctrl+wheel), fit-to-window (Ctrl+0), rotate (R),
folder-browse (PgUp/PgDn), slideshow (F9). The image panel
(Ctrl+Shift+M) adds brightness/contrast/saturation/gamma sliders, an
RGB histogram, eyedropper (status-bar RGB), and rubberband crop.

## Video

12 formats: `.mp4`, `.mov`, `.m4v`, `.mkv`, `.webm`, `.avi`, `.wmv`,
`.flv`, `.mpeg`/`.mpg`, `.ogv`, `.3gp`. Opened in **video** mode with a
play/pause/stop/scrub/volume bar. Codec coverage depends on your Qt's
FFmpeg build.

## Notebook

`.ipynb` opens in **notebook** mode. See **notebook.md** for the full
viewer/editor/runner.

## Web

URLs and `file://` paths typed via `Open URL…` (Ctrl+L) open in
**web** mode (embedded `QWebEngineView`). Cookies are sandboxed to
`~/.cache/TextView/webengine`.

## Encoding

Text loading uses `chardet` to autodetect, falling back to UTF-8. The
status bar shows the detected encoding. There's a Edit menu option to
convert line endings (LF / CRLF) and indent (tabs ↔ spaces).
