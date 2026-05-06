"""Format-on-save: run a per-language formatter before writing the buffer.

Each entry maps a TextView format identifier to an argv list. We spawn
the formatter synchronously, feed the buffer on stdin, capture stdout as
the formatted text. On non-zero exit, the original text is kept.

Default formatters expect to read stdin / write stdout — if the user has
configured a different formatter (e.g. ruff format) they can override
the dict via `display.formatters` (future work).
"""
import shutil
import subprocess


FORMATTERS: dict[str, list[str]] = {
    "python": ["black", "-q", "-"],
    "javascript": ["prettier", "--stdin-filepath", "buffer.js"],
    "typescript": ["prettier", "--stdin-filepath", "buffer.ts"],
    "json": ["prettier", "--stdin-filepath", "buffer.json"],
    "css": ["prettier", "--stdin-filepath", "buffer.css"],
    "scss": ["prettier", "--stdin-filepath", "buffer.scss"],
    "html": ["prettier", "--stdin-filepath", "buffer.html"],
    "yaml": ["prettier", "--stdin-filepath", "buffer.yaml"],
    "markdown": ["prettier", "--stdin-filepath", "buffer.md"],
    "go": ["gofmt"],
    "rust": ["rustfmt", "--emit", "stdout"],
}


def format_text(text: str, fmt: str, timeout: float = 10.0) -> tuple[str, str]:
    """Format `text` for the given TextView format identifier.

    Returns `(new_text, message)`. `message` is an empty string on success;
    otherwise a short human-readable reason that can show up in the
    status bar. The buffer is preserved on any error so save still works.
    """
    argv = FORMATTERS.get(fmt)
    if not argv:
        return text, ""
    if shutil.which(argv[0]) is None:
        return text, f"formatter '{argv[0]}' not on PATH"
    try:
        proc = subprocess.run(
            argv, input=text, capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return text, f"formatter failed: {e}"
    if proc.returncode != 0:
        # Often the formatter prints a syntax-error explanation to stderr.
        msg = (proc.stderr or "").strip().splitlines()
        first = msg[0] if msg else f"exit {proc.returncode}"
        return text, f"formatter rejected: {first[:200]}"
    return proc.stdout, ""
