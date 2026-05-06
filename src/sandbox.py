"""Process sandboxing helpers.

`wrap_argv(argv, *, no_network=False, ...)` returns an argv list that
runs the original under a sandbox if one is available on the host:

- macOS: `sandbox-exec -p '<sbpl profile>' <argv>`
- Linux: `firejail --quiet [--net=none] [--noprofile] <argv>`

If neither tool is available, the original argv is returned unchanged
— the caller can still rely on the rlimits already wired into
`runner.py`. Sandboxing is a defense-in-depth measure, never the only
guard.
"""
from __future__ import annotations
import shutil
import sys


def sandbox_available() -> tuple[bool, str]:
    """Return (have_sandbox, kind) where kind is 'sandbox-exec' / 'firejail'
    / '' (unavailable)."""
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return True, "sandbox-exec"
    if shutil.which("firejail"):
        return True, "firejail"
    return False, ""


def _macos_profile(no_network: bool, read_only_paths: tuple[str, ...]) -> str:
    """Build a minimal SBPL profile. Permissive default with selective
    denies — broad sandboxing breaks too many runtimes (Python finds
    libs across `/usr/local/`, `/opt/`, etc.)."""
    parts = ["(version 1)", "(allow default)"]
    if no_network:
        parts.append("(deny network*)")
    for ro in read_only_paths:
        parts.append(f'(deny file-write* (subpath "{ro}"))')
    return " ".join(parts)


def wrap_argv(argv: list[str], *, no_network: bool = False,
              read_only_paths: tuple[str, ...] = ()) -> list[str]:
    """Wrap `argv` so it runs under the host's sandbox tool. Returns the
    original argv unchanged when no sandbox is available."""
    if not argv: return argv
    have, kind = sandbox_available()
    if not have: return argv
    if kind == "sandbox-exec":
        profile = _macos_profile(no_network, read_only_paths)
        return ["sandbox-exec", "-p", profile, *argv]
    if kind == "firejail":
        prefix = ["firejail", "--quiet", "--noprofile"]
        if no_network: prefix.append("--net=none")
        for ro in read_only_paths: prefix.append(f"--read-only={ro}")
        return prefix + ["--", *argv]
    return argv
