# TextView roadmap

A "viewer-first, do-anything" desktop tool. Where we are now and where we're
heading. Status codes: ✅ shipped, 🚧 in progress, 📅 planned, 🤔 considering.

## Where we are today

| Area | Capability |
| --- | --- |
| **File formats** | Plain text, Markdown, HTML, JSON / NDJSON / JSONL / GeoJSON, YAML, CSV/TSV/PSV/TAB, TOML, INI; **~60 code languages** with Pygments highlighting; PDF (native + extracted text + search + select/copy from rendered); DOCX (mammoth-rendered HTML + extracted); RTF, EPUB, ODT; **LaTeX** (`.tex`/`.latex`/`.ltx` source + on-demand PDF compile via xelatex / pdflatex auto-pick); BibTeX; **Excel / OpenDocument** (`.xlsx`/`.xlsm`/`.xltx`/`.xltm`/`.xls`/`.ods` → table view with sheet picker); **SQLite** (`.sqlite`/`.sqlite3`/`.db` read-only, table picker + Run SQL); **archives** (`.zip`/`.tar`/`.tar.gz`/`.tar.bz2`/`.tar.xz`/`.7z`/.jar/.war/.apk — markdown TOC + extract); subtitles (`.srt`/`.vtt`/`.ass`/`.ssa`); email/cal/contacts (`.eml`/`.mbox`/`.ics`/`.vcs`/`.vcf`); markup alternates (AsciiDoc / Org / Typst / MediaWiki); IaC (`.tf`/`.hcl`/`.nix`/`.proto`/`.graphql`/`.prisma`); 15 image formats incl. animated GIF, multi-page TIFF, multi-frame WebP, SVG, HEIC; 12 video formats; **13 audio formats** (mp3/wav/flac/ogg/opus/aac/m4a/aiff/midi/…) via QtMultimedia. |
| **Display** | 10 themes; live typography (font/size/weight/line-height/letter-spacing/padding); word wrap; line numbers; whitespace toggle; current-line highlight; max content width; alignment; **per-element table colour overrides** (gridlines / cell text / alt-row / header bg+fg / selection bg+fg). |
| **Search/edit** | Find/replace bar; goto line; toggle line comment; word/line/char counts; trim trailing whitespace + final newline on save; recent files; bracket auto-close; auto-indent; line move/duplicate/select; tabs↔spaces; LF/CRLF conversion. |
| **Browser** | Embedded Chromium; bookmarks; reading mode; view source; DevTools. |
| **Runner** | Async `QProcess` runner; ANSI 16+RGB output; ~20 language interpreters; F5/Ctrl+Enter/Ctrl+.; per-file trust; CPU/memory rlimits; **real PTY terminal with pyte** (Ctrl+`). |
| **Image viewer** | Zoom/fit/rotate/slideshow; multi-page navigation; **brightness/contrast/saturation/gamma sliders**; checkered backdrop; folder browse. |
| **Video viewer** | Embedded `QMediaPlayer` + transport bar (play/pause/stop/scrub/volume/mute) for mp4/mov/mkv/webm/avi/… |
| **Tables** | Spreadsheet view shared by **CSV / XLSX / SQLite**; sortable headers (numeric vs lexical auto-detect); contiguous selection with sum/avg/min/max/median/stddev; copy-as-TSV; live filter bar (`>`, `>=`, `<`, `<=`, `=`, `≠`, `~`); insert/delete rows/cols; **chart dialog** (Line/Bar/Scatter/Histogram/Pie/Box) via matplotlib; **Switch sheet/table…** (F4) for multi-sheet workbooks and multi-table databases; **Run SQL…** (Ctrl+Shift+Q) on SQLite (read-only). |
| **Templates + Save As** | **New from template…** (Ctrl+Alt+N) with ~25 starter files (README, LaTeX article, Python script, Dockerfile, …). **Save As with format conversion** offers a converter when the chosen extension differs from the current format — markdown ↔ HTML, JSON ↔ YAML ↔ TOML, CSV → JSON / JSONL / XLSX / Markdown / HTML, JSON → CSV, RTF → plain. Save reopens the file so view-mode / highlighting follow the new format. |
| **Metadata** | Per-file dock with EXIF, PDF info, DOCX/EPUB props. |
| **Security** | Default-safe web profile; download dialog; cert prompts; per-file run-trust; resource limits. |
| **LLM** | Chat panel (Ctrl+J); Anthropic + OpenAI + Ollama (with **tool-calling**); streaming; key in `keyring`; **22 tools** (read-only + action + module-control via AppAPI); audit log. |
| **Extension** | **`AppAPI` façade** (50+ methods); **plugin loader** (`~/.config/TextView/plugins/*.py`, hot-reload, sample plugin shipped); user **hooks** (`*.py` for `on_file_opened` / `on_file_saved` / `on_run_finished` / `on_chat_response`, with optional `api=` kwarg); **command palette** (Ctrl+K); **quick-open** (Ctrl+P); **diff viewer** (vs file, vs git HEAD); **inline LLM suggestions** (Alt+/). |
| **Misc** | Drag-and-drop; fullscreen; headless screenshot CLI; tabbed config panel (Display/Editor/Files/Browser/Privacy); workspace persistence (tabs, dock layout, recent, bookmarks). |

Codebase: 50+ modules, all under 500 lines. ~10 000 lines total.

---

## Shipped roadmap

| Wave | Highlights |
| --- | --- |
| **v1.1 — agent + tabs** ✅ | LLM read-only tools; LLM action tools (with confirmation); tab bar with session persistence; OpenAI-compatible provider. |
| **v1.2 — editor depth** ✅ | Bracket auto-close; auto-indent; tabs↔spaces; line move/duplicate/select; encoding + line-ending conversion; **code folding** (v3.2); **regex search + replace** with backref support (v3.2). |
| **v1.3 — code intelligence** ✅ (mostly) | **LSP client + diagnostics + hover** (v3.2, Python via pyright); format-on-save (shipped via `formatters.py`); linting in gutter ✅ (LSP-driven). |
| **v1.4 — viewers** ✅ | Slideshow ✅; image save-as / convert ✅; PDF search ✅; PDF text-copy ✅; browser reading mode ✅; image histogram (v3.1); **image eyedropper + rubberband crop** (v3.2). |
| **v1.5 — polish** ✅ | Project panel; workspace persistence; cheat sheet (Ctrl+?); per-format prose typography. |
| **v2.0 — automation glue** ✅ | Hooks; watch-folder; quick-action palette (Ctrl+K). |
| **v2.1 — moonshots** ✅ (almost all) | A: quick-open ✅ · B: PTY terminal ✅ · C: inline LLM suggestions ✅ · D: diff viewer ✅ · F: plugin API ✅ · **E: multi-window** 📅 *(deferred — orthogonal; near-trivial now that AppAPI exists)*. |
| **v2.2 — display extras** ✅ | Multi-page TIFF; image adjustments panel; video playback; spreadsheet view with filter / sort / chart / panel; table colour overrides; AppAPI façade; LLM module-control tools (8 new); Ollama tool-calling. |

---

## v3.0 — analysis, scripting, UX hardening

The next wave. **Driving question**: TextView is now a capable
multi-format workhorse with a real plugin / scripting / LLM-control
substrate. What unlocks the next order-of-magnitude usefulness?

Four initiatives, parallelizable, sequenced below.

### I.1 — Improve graphing & analysis 🚧

Goal: turn the spreadsheet panel from "chart wizard" into "lightweight data
analysis station".

**Statistical summaries** 📅
- Per-column descriptive stats: count, mean, median, mode, stddev, var,
  min, max, range, Q1/Q3, IQR, skew, kurtosis, missing-value count.
- Live updates respect the active filter.
- Surfaced as: a new "Statistics" group in the spreadsheet panel
  showing the active column, plus a full **Stats** dialog (`Ctrl+Shift+I`?)
  with per-column rows.

**More chart types** 📅
- Stacked + grouped bar (`make_chart` already accepts multi-y).
- Scatter with regression line + R²; optional log axes.
- Heatmap (matrix view of a numeric region).
- Correlation matrix (pairwise Pearson on numeric columns).
- Density / KDE.
- Dual y-axis charts.
- Error bars (mean ± stderr / ± stddev).

**Data transformations** 📅
- Derived columns: type a formula referencing column names (`a + b`,
  `a / b * 100`, `log(score)`). Stored in the model as a "computed
  column" so it re-evaluates after filter / sort.
- Group-by + aggregate (sum / count / mean).
- Pivot.
- Drop / fill nulls.
- A small "Recipes" preset list (e.g. "Z-score this column",
  "Rolling mean window=3").

**Export upgrades** 📅
- Higher-resolution PNG default (200 DPI).
- Copy-chart-to-clipboard (paste into Slack / docs).
- Include chart inline in a chat message.

**LLM tool surface** 📅 (extends `tools_module.py`)
- `compute_stats(column)` → returns the stat dict.
- `add_derived_column(name, formula)`.
- `correlation_matrix()` → JSON for display + heatmap render.
- `pivot(rows, cols, values, agg)`.

### I.2 — Agent-authored scripts 📅

Goal: the LLM (and the user) can author scripts on the fly, save them,
re-run them, and refine them — turning one-shot work into reusable
recipes.

**Storage**
- `~/.config/TextView/agent_scripts/*.py` (Python) and `*.sh` (shell).
- Each script has frontmatter (name, language, description, created_by)
  and a body.

**LLM tools** (extends `tools.py`)
- `list_scripts()` — what's available.
- `create_script(name, language, body, description?)` — save new
  (with first-write confirmation).
- `read_script(name)` — return body for editing.
- `update_script(name, body)` — replace.
- `delete_script(name)` — confirmation required.
- `run_script(name, args?)` — execute via the existing Runner.

**UI**
- New "Scripts" submenu listing saved scripts; click to run, right-click
  for edit/delete.
- Quick-open style **Ctrl+Shift+R** "run a saved script" picker.
- Scripts appear in the command palette (Ctrl+K).

**Promotion path**
- A script that proves useful can be moved by the user into
  `plugins/` and given a `register(ctx)` to become a real plugin.

### I.3 — UX hardening via screenshot-driven testing 📅

Goal: catch the alignment / contrast / dock-collision / focus issues
that are invisible from headless tests.

**Test matrix**
- Every viewer mode (code, rendered, PDF, image, video, table, web,
  diff) × 3 themes (Solarized Dark, Light, Dracula).
- Every dock combination (config, metadata, chat, project, image,
  spreadsheet, terminal — all on / all off / mixed).
- Every dialog (find, plot, word stats, color picker, set-key,
  goto-line, command palette, quick-open).

**Process**
- Headless screenshot script that walks the matrix and emits PNGs.
- Manifest CSV with `(view, theme, docks, screenshot_path, notes)`.
- A markdown report `UX_REPORT.md` with each finding + a fix or
  "wontfix".

**Likely fixes** (predicted from prior work)
- Dock toolbar contrast in light theme.
- Filter-bar layout when window is narrow.
- Image-panel slider value labels overflow on Sepia theme.
- Chart dialog axis-label colour vs theme.

### I.4 — Self-driving development loop 🚧

Goal: keep the project moving when the user is away, with explicit
checkpoints for review.

**How it works**
- `ScheduleWakeup` fires every ~3-5 minutes during active work.
- Each wakeup picks up the next sub-task from this roadmap, makes
  one concrete chunk of progress, runs the relevant tests, and
  documents what changed.
- The user can interrupt at any time by sending a message; the loop
  ends automatically when the plan is complete or a question arises
  that genuinely requires their input.

**Loop discipline**
- Each turn ends with a 1-line "what's next" so the user can redirect.
- Tests + screenshots accompany every behavioural change.
- File-size cap (500 lines) is the hard line; any module approaching
  it gets extracted before the next chunk lands.
- INTERFACE.md and SESSION_LOG.md get updated each turn.

---

## Sequencing for v3.0

```
W0 (now)        — refresh roadmap; start I.1 statistical summaries
W1              — finish I.1 stats; add Stats dialog
W2              — I.1 new chart types: heatmap + correlation matrix
W3              — I.1 derived columns; LLM tools for stats/pivot
W4              — I.2 script storage + LLM tools (create / read / run)
W5              — I.2 scripts UI (menu + Ctrl+Shift+R picker)
W6              — I.3 screenshot matrix harness + first pass
W7              — I.3 fixes from findings; UX_REPORT.md
W8              — checkpoint summary + ask user for direction
```

Each `W` is one wakeup checkpoint, ~10-15 min of work. The user can
read each one, fold in feedback, or let the next fire.

---

## v3.2 — parking-lot sweep ✅ (shipped 2026-05-04)

Driving question: with v3.0 + v3.1 shipped, what items in the parking
lot are realistic to clear in a focused wave?

| W | Item | Scope | Notes |
| --- | --- | --- | --- |
| W1 | Regex polish in find bar | small | `cb_regex` already wired in `_query()` for find/highlight; replace ops still string-only. Extend `replace_one` / `replace_all` to honor regex (with backref support) and bad-pattern handling. |
| W2 | Code folding | mid | Extend `viewer.py` gutter to draw fold markers. Detect foldable regions (indent-based for Python, brace-based for C-family). Click toggles fold via `QTextBlock.setVisible(False)`. No persistence. |
| W3 | Image color picker + crop | mid | Eyedropper mode in `image_view.py` (click → status bar shows RGB hex). Rubberband crop → save-to-disk dialog. Both gated by toolbar buttons in `image_panel.py`. |
| W4 | Snippet library | mid | New `src/snippets.py` with JSON store at `~/.config/TextView/snippets.json`. Right-click in chat → "Save as snippet". Picker `Ctrl+;` to insert at cursor. Tag-filtered. |
| W5 | LSP client — scaffold | heavy | New `src/lsp_client.py`: stdio JSON-RPC, lifecycle (initialize / didOpen / didChange / shutdown). One language wired (Python via pyright). |
| W6 | LSP client — diagnostics + hover | heavy | Diagnostics → gutter dots + tooltips. Hover requests on cursor pause. |
| W7 | Polish + INTERFACE.md update + retro | small | Update navigation map; document new keybinds; SESSION_LOG retro. |

Each W is one wakeup checkpoint. The user can interrupt; otherwise
the wakeups self-schedule with ~30 min between fires.

---

## v3.5 — PDF editing 🚧

After "do we have Adobe-style PDF editing?" the realistic Python
ecosystem was surveyed and the scope split into three tiers.

| Tier | Item | Status |
| --- | --- | --- |
| 1 | Page operations: rotate / delete / extract / reorder / merge / insert blank | ✅ *(shipped 2026-05-25)* |
| 2a | Annotations (dialog-driven): sticky note / free-text / highlight / rectangle / circle / ink + list / delete / clear-all | ✅ *(shipped 2026-05-25)* |
| 2b | Annotation **mouse-driven UX** — click / drag on the rendered page, QRubberBand feedback, coord conversion to PDF points, Esc cancels | ✅ *(shipped 2026-05-25)* |
| 3 | Inline text editing (span replacement + find-and-replace + click-to-edit) | ✅ *(shipped 2026-05-25)* |
| — | Cryptographic signing (via endesive + OpenSSL) | 🤔 |

Tier 1 (`src/pdf_editor.py` + `src/pdf_actions.py`) uses `pypdf`
(already a dep) and ships ~40 tests. All operations write to a
sibling `*-edited.pdf` — the source is never mutated. New **PDF**
menu + Ctrl+]/Ctrl+[ for rotate. See SESSION_LOG.md entry.

---

## v3.4 — finish the file-lifecycle story ✅ *(shipped 2026-05-25)*

After v3.3 shipped LaTeX, templates, save-as conversion, audio playback,
XLSX/SQLite/archive readers, this wave closed the remaining gaps. All
eight items below shipped in one session; EPUB-write remains 🤔
considering until real demand appears.

| # | Item | Scope | Status |
| --- | --- | --- | --- |
| 1 | **NumPy arrays (`.npy` / `.npz`)** | small | ✅ |
| 2 | **Markdown → DOCX** save-as converter | small | ✅ |
| 3 | **Certificate / key display** (`.pem`/`.crt`/`.cer`/`.key`) | small | ✅ |
| 4 | **Parquet / Feather** as table | mid | ✅ |
| 5 | **Archive tree view** (replaces markdown TOC) | mid | ✅ |
| 6 | **Font preview** (`.ttf`/`.otf`/`.woff`/`.woff2`) | small | ✅ |
| 7 | **MATLAB binary** (`.mat`) | small | ✅ |
| 8 | **HDF5 / NetCDF** (`.h5`/`.hdf5`/`.nc`) | heavy | ✅ |
| 9 | **EPUB write** (markdown → EPUB) | mid | 🤔 |

### Detail per item

**NumPy** — `numpy.load(path)`. For `.npy`: 1D becomes a single-column
table, 2D becomes a multi-column table. For `.npz`: a "Switch array…"
picker like the sheet/table picker (F4). Dtype shown in the status bar.

**Markdown → DOCX** — extends `save_as.Conversion` registry with a
single converter that walks the markdown AST and emits `python-docx`
elements (headings, paragraphs, lists, code blocks, tables, inline
emphasis). Goes through the existing `EditController.save_as` →
re-open flow.

**Certificate / key display** — new `cert_loader.py` parses PEM /
DER X.509 certificates (subject / issuer / validity / SANs / fingerprints
/ key algorithm + size) and PEM-encoded private keys (type + size,
**never** the raw bytes). Output rendered as markdown through the
existing pipeline. Defaults to `cryptography`; falls back to stdlib
`ssl` for cert basics when missing.

**Parquet / Feather** — new `dataframe_loader.py` mirrors
`spreadsheet_loader.py`'s shape: extract a tabular blob to CSV text
and route through the existing `TableView`. Multi-column dtypes shown
in the status bar.

**Archive tree view** — graduates the current markdown TOC to a real
`QTreeView` (`archive_view.py`) with size / mtime / type columns,
text-preview pane for the selected member (up to 1 MB), double-click
to extract. The markdown TOC stays available via Ctrl+T.

**Font preview** — new `font_view.py` widget: `QFontDatabase.addApplicationFont`
loads the file, then renders a sample sheet — alphabet upper/lower,
digits, common punctuation, a couple of weights and sizes, the file's
PostScript name.

**MATLAB binary** — `scipy.io.loadmat` extracts variables; small
variables shown in a key/value table; 2D arrays become the active
TableView; structured arrays expand one row per record.

**HDF5 / NetCDF** — likely deferred to its own wave (significant new
view: hierarchical group tree + per-dataset table). Specced here so
the shape is known.

**EPUB write** — `ebooklib` already present from the read path. A
markdown → EPUB converter would round out the doc-export story. Marked
"considering" until I see real demand.

### LLM tool surface (extensions to `tools_module.py`)

Once these land, the agent gains:
- `read_npy_array(path, key=None)` — open NumPy array; returns shape +
  dtype + first N rows.
- `read_parquet(path, limit=N)` — Parquet → row dicts.
- `read_cert(path)` — certificate metadata as JSON.
- `list_archive(path)` — already implicit through `read_doc`, but a
  first-class tool helps the agent reason about packaging.

---

## Beyond v3.0 (parking lot) 🤔

**Cleared in v3.2** ✅: code folding, regex polish, image color picker
+ crop, snippet library, LSP client (Python/pyright + diagnostics +
hover). Multi-window cleared in v3.1.

**Cleared in v3.3** ✅ *(2026-05-25)*: **LaTeX support** (`.tex`/`.latex`/`.ltx`
+ on-demand PDF compile, xelatex auto-pick), **templates system**
(Ctrl+Alt+N, ~25 starter files), **Save As with format conversion**
(md ↔ html, JSON ↔ YAML ↔ TOML, CSV → JSON/JSONL/XLSX/MD/HTML, JSON → CSV,
RTF → plain), **audio playback** (13 formats through QMediaPlayer with
ID3/Vorbis metadata overlay), **Excel/ODS** read as table with sheet
picker, **SQLite browser** with table picker + Run SQL, **archive viewer**
(zip/tar/7z markdown TOC + extract). ~40 new file-type detections
(subtitles, email/cal/contacts, IaC, alt-markup, lisp family, more
languages). 486 → 588 passing tests.

**Cleared in v3.3** ✅ (2026-05-04): persistent test suite (`tests/`,
**165 cases**), auto-hover on cursor pause, JSON/TOML/XML "runners",
trendlines + analysis options in chart dialog, **Python REPL +
conda env picker**, **LSP** for **Python / TypeScript / JavaScript /
Go / Rust / C / C++** with **go-to-definition** (F2), **find references**
(Shift+F12), **diagnostics panel** dock (Ctrl+Shift+X), **workspace
search** find-in-project (Ctrl+Shift+F), **embedded Jupyter qtconsole**
(Ctrl+Alt+J), **notebook viewer + editor + runner** for `.ipynb` (load,
edit code cells, edit markdown via toggle, run against shared kernel,
**save** via Ctrl+S incl. cell outputs, add/delete/move cells, change
cell type, **rich output rendering** (HTML/PNG/SVG with priority
dispatch), execution-count display in cell headers).

**Still parked**:

- **LSP — auto-install hint**: when a server isn't on PATH, surface
  the install command (e.g., "npm install -g typescript-language-server",
  "rustup component add rust-analyzer", "brew install gopls") instead
  of just the warning that the binary couldn't start.
- **Notebook: Jupyter-style modal keyboard shortcuts** (Esc enters
  command mode, A/B/M/Y/D-D/J/K). Currently the bound shortcuts are
  always-on (Ctrl+Alt+R run-all, Ctrl+Alt+↑/↓ move, Ctrl+S save) — no
  modal "command mode" yet.
- **Notebook: clear all outputs** action; **Notebook: restart-and-run-all**.
- **Notebook: kernel auto-start** when the user clicks ▶ Run on the
  first cell (currently has to click Notebook → Start kernel first).
- **Mobile companion** — phone opens the same workspace.
- **Plugin marketplace** — discover community plugins by tag.
