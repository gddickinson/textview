# tests/

Persistent regression suite for TextView. Run from the project root:

```bash
python3 -m pytest                  # full suite (~1s, includes subprocess tests)
python3 -m pytest -m "not slow"    # fast subset (skips LSP + runner subprocesses)
python3 -m pytest tests/test_X.py  # one file
python3 -m pytest -k regex         # name match
```

## What's covered

| File | Subject | Notable regressions guarded |
| --- | --- | --- |
| `test_table_model.py` | Parsing, edit, sort, filter, derived columns, serialize | **CSV edit-cycle**: `setData` edits must show up in `serialize()` output. Sandbox: `__import__` in derived-column formula must not execute. |
| `test_search_bar.py` | Regex find / replace with backref expansion | Bad regex must not mutate buffer; case-insensitive replace works. |
| `test_code_fold.py` | Indent-based code folding | **Nested-fold preservation**: unfolding outer must not re-expand a still-folded inner block. |
| `test_snippets.py` | JSON snippet store | Trust boundary: name regex `[A-Za-z][A-Za-z0-9_-]{0,63}`. Corrupt JSON falls back to empty list; malformed entries filtered. |
| `test_plot_overlays.py` | Trendline math + reference levels | Each fit recovers exact parameters on perfect-fit synthetic data; degenerate inputs (zero variance, non-positive y for exp/log) return None. |
| `test_lsp_client.py` | LSP wire format + subprocess round-trip | `Content-Length`-framed parser handles partial frames + malformed JSON; real `pyright`-style mock server initializes + responds to hover. |
| `test_runner.py` | `LANGUAGES` mapping + JSON/TOML/XML pretty-printers | Stdlib-only validators emit pretty-printed output; broken JSON reports parse error with line info. |
| `test_hover_pause.py` | LSP auto-hover on cursor pause | Debounced timer fires once per pause; subsequent moves restart it; disable cancels pending fire. |

## Conventions

- All tests run offscreen (`QT_QPA_PLATFORM=offscreen`).
- A session-scoped `qapp` fixture in `conftest.py` shares one `QApplication`.
- `tmp_settings` fixture redirects `QSettings` at a temp path.
- `lsp_mock_server_path` fixture writes a 50-line stdin/stdout LSP responder.
- Subprocess-based tests are marked `@pytest.mark.slow`.
