# Security & sandboxing

TextView opens arbitrary files, can render HTML/SVG with embedded
scripts, and runs code on demand (F5, agent-installed handlers,
plugins). Each is a potential attack vector. This page documents the
layered defences and how to opt into the heavier ones.

## Threat model

**Defended against:**

- **Renamed-executable phishing.** A `.pdf` that's actually a Mach-O
  / ELF / PE binary, or a `.docx` that's actually a different ZIP
  payload — the open-time scan catches the magic-byte / extension
  mismatch and prompts before opening.
- **Office macros.** ZIP-based Office files (`.docx`, `.xlsx`, `.pptx`,
  and the explicit `.docm` / `.xlsm` / `.pptm` variants) are scanned
  for `vbaProject.bin`. Macros aren't executed by TextView, but the
  warning fires so the user knows what they're holding.
- **PDF active content.** PDFs with `/JavaScript`, `/Launch`,
  `/OpenAction`, `/EmbeddedFile`, or `/AA` triggers are flagged.
  TextView's PDF view doesn't run JavaScript, but exporting or
  forwarding the file does carry the active content.
- **Embedded scripts in HTML / SVG.** `<script>` tags and
  `javascript:` URIs flagged so the user knows before viewing the
  rendered page in TextView's WebView.
- **Suspicious shell patterns** in script files: pipe-to-shell
  installers (`curl … | bash`), base64-decoded shell, PowerShell
  evasion flags (`-enc`, `-nop`, `-w hidden`),
  `FromBase64String` → `Invoke-Expression`, netcat listeners,
  destructive `rm -rf /…`, hex-encoded payloads, `python -c "exec(…)"`.
- **Dangerous file types** (`.exe` / `.bat` / `.scr` / `.ps1` / `.vbs`
  / `.dmg` / `.pkg` / `.msi` / `.apk` / `.iso` / …). Opening these
  inside TextView is harmless — but the warning surfaces what the
  file actually is, and offers to quarantine.
- **macOS quarantine xattr** (`com.apple.quarantine`) — files that
  came from the internet via Safari / Mail / etc. carry this
  attribute. Surfaced as `info`-level finding.
- **ClamAV signature scan** — when `clamscan` is installed and the
  setting is enabled.

**NOT defended against:**

- Zero-day exploits in TextView's own dependencies (Qt, PyQt6,
  WebEngine, pypdf, Pillow, ebooklib, mammoth). Keep them updated.
- Exfiltration via the chat agent's network access — the chat
  panel uses real LLM APIs and can call tools that read your files.
  The two-gate safety (chat "Allow actions" + per-tool flag) is
  there to slow this down; it doesn't replace careful review of
  what the agent is doing.
- Pickle de-serialisation. The unknown-file inspector flags `.pkl`
  but TextView never auto-loads them. Don't `pickle.load()` an
  untrusted file outside of the app either — it executes arbitrary
  code.

## Open-time flow

1. User opens a file via menu / drag-drop / recent / quick-open / etc.
2. `MainWindow.open_file` runs `EditController.confirm_discard()`.
3. With `security_scan_on_open` (default **on**),
   `security_scanner.scan_file()` runs.
4. If `risk_level` is `clean`: file opens immediately.
5. Otherwise the **Security warning dialog** shows the markdown-
   rendered findings with three options:
   - **Open anyway** — proceed with awareness.
   - **Quarantine…** — move into `~/.config/TextView/quarantine/`
     (sidecar JSON records the scan + reason; the original location
     becomes empty).
   - **Cancel** — back out, file stays where it is.

## Settings

In **Configuration panel → Privacy & Security → File-loading
security**:

| Setting | Default | What it does |
| --- | --- | --- |
| `security_scan_on_open` | on | Master switch. Off = no scan, no prompts. |
| `security_warn_macros` | on | Suppress / show macro findings. |
| `security_warn_pdf_js` | on | Suppress / show PDF JS / Launch / OpenAction. |
| `security_block_executables` | on | Suppress / show dangerous-extension findings. |
| `security_clamscan_on_open` | off | Invoke `clamscan` on each open. ~0.5–5 s per file. |
| `security_sandbox_runner` | off | Wrap F5 runs in `sandbox-exec` / `firejail`. |

## ClamAV

Install (macOS):

```bash
brew install clamav
freshclam       # download signature DB
```

Linux:

```bash
sudo apt install clamav clamav-freshclam
sudo freshclam
```

Then enable `security_clamscan_on_open` in the settings panel. Hits
appear as `dangerous`-severity findings tagged `antivirus_hit`. False
positives are possible — review the signature name before quarantining.

## Sandbox runner

When `security_sandbox_runner` is on, the runner wraps argv:

- macOS: `sandbox-exec -p '(version 1)(allow default)(deny network*)' …`
- Linux: `firejail --quiet --noprofile --net=none -- …`

Falls back to plain run when neither tool is on PATH. Doesn't replace
the existing CPU / memory rlimits in `runner.py` — both layers apply.

## Quarantine

Files moved to quarantine live under
`~/.config/TextView/quarantine/<id>/` with a sidecar `meta.json`:

```json
{
  "id": "a1b2c3d4e5f6a7b8",
  "original_path": "/Users/.../downloads/invoice.pdf",
  "quarantined_path": "/Users/.../quarantine/.../invoice.pdf",
  "reason": "open-time block (dangerous)",
  "quarantined_at_iso": "2026-05-05T22:14:03",
  "findings": [{"severity": "dangerous", "category": "extension_mismatch", ...}]
}
```

Browse via **Help → Quarantined files…**. Each row has:

- **Restore** — moves the file back to its original path, removes
  the entry. Refuses to overwrite an existing file at the
  destination — pass an alternate path if needed.
- **Delete permanently** — purges the entry from disk. Irreversible;
  prompts for confirmation.

## Agent tools

| Tool | Gate | What it does |
| --- | --- | --- |
| `scan_file(path, run_clamav=False)` | RO | Returns scan result as JSON. |
| `list_quarantined()` | RO | Every quarantined file + reason. |
| `quarantine_file(path, reason)` | Allow actions | Moves to quarantine. |
| `restore_quarantined(qid, target?)` | Allow actions | Moves back to original (or `target`). |
| `delete_quarantined(qid)` | Allow actions + `agent_can_purge_quarantine` | Permanent purge. Two-gate. |

## Manual security report

Press **Ctrl+Shift+S** (or **Help → Security report…**) at any time
to re-scan the current file and see the findings dialog. Useful when
you've changed the settings and want to re-evaluate, or when you
want to see why a file came up clean.

## Files

- `src/security_scanner.py` — heuristic + AV scan.
- `src/quarantine.py` — quarantine workspace.
- `src/sandbox.py` — argv wrapping for `sandbox-exec` / `firejail`.
- `src/security_dialog.py` — open-time warning, quarantine browser,
  on-demand report.
- `src/llm/tools_security.py` — agent tool surface.
