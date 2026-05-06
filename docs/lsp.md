# LSP — language servers

TextView speaks the Language Server Protocol over stdio against any
LSP-compatible server. The protocol layer is generic; new languages
are dictionary entries in `src/lsp_controller.py:SERVERS`.

## Default servers (need to be installed separately)

| Language | Server | Install |
| --- | --- | --- |
| Python | `pyright-langserver --stdio` | `npm i -g pyright` or `pip install pyright` |
| TypeScript / JavaScript | `typescript-language-server --stdio` | `npm i -g typescript typescript-language-server` |
| Go | `gopls` | `brew install gopls` or `go install golang.org/x/tools/gopls@latest` |
| Rust | `rust-analyzer` | `rustup component add rust-analyzer` |
| C / C++ | `clangd` | `brew install llvm` (clangd ships in the LLVM toolchain) |

If a language's binary isn't on PATH, the LSP feature for that
language is silently disabled and the rest keeps working.

## Enabling

LSP is **off by default**. Turn it on via:
- The Configuration panel (Ctrl+,) — "LSP enabled" checkbox
- Or programmatically: `set_setting lsp_enabled true` via the control
  server

Once on, opening a file in a supported language triggers `did_open`,
the server starts (lazy), and diagnostics begin streaming.

## What's wired into the UI

- **Diagnostics** — colored dots in the gutter (red = error, amber =
  warning, blue = info, grey = hint). The Diagnostics panel
  (Ctrl+Shift+X) shows the full list.
- **Hover** — manual via Ctrl+Shift+H, or auto on cursor pause if
  `lsp_hover_on_pause` is enabled.
- **Go to definition** — F2.
- **Find references** — Shift+F12, opens a modal list; click a row to
  jump.

## Architecture

- `src/lsp_client.py` — pure protocol: JSON-RPC over QProcess stdin/stdout,
  `Content-Length` framing, request/response correlation.
- `src/lsp_controller.py` — per-window coordinator, owns one client
  per language id, drives `did_open` / `did_change` (300 ms debounce) /
  `did_close` from editor state, routes notifications and responses.

## Troubleshooting

**No diagnostics appear**: check the status bar after enabling LSP.
"Started <lang> language server" means the server spawned cleanly.
"Could not start <lang> server" means the binary wasn't found —
install it and re-toggle.

**Hover doesn't fire**: make sure your cursor is on an identifier (not
whitespace), and that the file you're in is one of the supported
languages. For auto-hover, also enable `lsp_hover_on_pause`.

**Go-to-definition opens the wrong file**: the LSP returned a
`Location` with an unexpected URI — check the response with the
control server (`eval` op) if needed.

**Find references is empty**: some servers need `includeDeclaration`
explicitly (we send `True` by default). Pyright is reliable; clangd
works if the project has a `compile_commands.json`.
