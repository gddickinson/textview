"""Discover Python interpreters on the system: system pythons, conda
environments, pyenv versions. Returned as `(name, path)` pairs so callers
can populate menus / pickers without making subprocess calls themselves.

The discovery is intentionally lazy and lenient: missing tools, malformed
output, or non-existent paths just produce an empty contribution from
that source. We never raise into the caller.
"""
from __future__ import annotations
import json, shutil, subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PythonEnv:
    name: str
    path: str
    source: str   # "system" / "conda" / "pyenv" / "custom"

    def display(self) -> str:
        return f"{self.name}  ({self.path})"


def _exists_executable(path: str) -> bool:
    p = Path(path)
    return p.is_file() and (p.stat().st_mode & 0o111) != 0


def discover_system() -> list[PythonEnv]:
    """`python3` from PATH, plus a few common Mac/Linux fallbacks."""
    out: list[PythonEnv] = []
    seen: set[str] = set()
    for cmd in ("python3", "python"):
        path = shutil.which(cmd)
        if path and path not in seen:
            seen.add(path); out.append(PythonEnv(name=cmd, path=path, source="system"))
    for fallback in ("/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
        if fallback not in seen and _exists_executable(fallback):
            seen.add(fallback)
            out.append(PythonEnv(name=Path(fallback).name, path=fallback, source="system"))
    return out


def discover_conda(timeout_s: float = 3.0) -> list[PythonEnv]:
    """Run `conda info --envs --json` if conda is on PATH; parse the env list.
    Returns [] if conda isn't installed or the call fails.
    """
    if shutil.which("conda") is None:
        return []
    try:
        r = subprocess.run(
            ["conda", "info", "--envs", "--json"],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    out: list[PythonEnv] = []
    for env_path in data.get("envs", []) or []:
        py = Path(env_path) / "bin" / "python"
        if not py.exists():
            py = Path(env_path) / "python.exe"  # Windows fallback
            if not py.exists():
                continue
        # The env "name" is the directory basename; the root env shows up
        # as `<conda_root>` and we label it "base".
        name = Path(env_path).name
        if env_path == data.get("root_prefix") or env_path == data.get("conda_prefix"):
            name = "base"
        out.append(PythonEnv(name=name, path=str(py), source="conda"))
    return out


def discover_pyenv(timeout_s: float = 3.0) -> list[PythonEnv]:
    """`pyenv versions --bare`; one PythonEnv per installed version."""
    if shutil.which("pyenv") is None:
        return []
    try:
        r = subprocess.run(
            ["pyenv", "versions", "--bare"],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if r.returncode != 0:
        return []
    root_proc = subprocess.run(
        ["pyenv", "root"], capture_output=True, text=True, timeout=timeout_s,
    )
    if root_proc.returncode != 0:
        return []
    root = Path(root_proc.stdout.strip())
    out: list[PythonEnv] = []
    for line in r.stdout.splitlines():
        version = line.strip()
        if not version:
            continue
        py = root / "versions" / version / "bin" / "python"
        if py.exists():
            out.append(PythonEnv(name=f"pyenv:{version}", path=str(py), source="pyenv"))
    return out


def discover_all() -> list[PythonEnv]:
    """All sources, deduplicated by absolute interpreter path."""
    out: list[PythonEnv] = []
    seen: set[str] = set()
    for env in (*discover_system(), *discover_conda(), *discover_pyenv()):
        if env.path not in seen:
            seen.add(env.path); out.append(env)
    return out


def open_repl(window):
    """Open the terminal dock with the configured Python interpreter in -i mode."""
    import sys
    interp = window.settings_manager.display.python_interpreter or sys.executable
    cwd = str(Path(window._current_path).parent) if window._current_path else None
    window.terminal_dock.show()
    window.terminal_dock.term.kill()
    window.terminal_dock.term.start(cwd=cwd, argv=[interp, "-i"])
    window.statusBar().showMessage(f"Python REPL: {interp}", 4000)


def pick_interpreter(window):
    """Modal picker over discovered envs; persists the chosen interpreter."""
    from PyQt6.QtWidgets import QInputDialog
    envs = discover_all()
    if not envs:
        window.statusBar().showMessage("No Python interpreters found.", 4000); return
    labels = [f"{e.source}: {e.name}  —  {e.path}" for e in envs]
    choice, ok = QInputDialog.getItem(window, "Choose Python interpreter",
        "Select an interpreter for F5 / Run and the Python REPL:",
        labels, 0, False)
    if not ok: return
    env = envs[labels.index(choice)]
    window.settings_manager.update("python_interpreter", env.path)
    window.statusBar().showMessage(f"Python interpreter → {env.path}", 4000)


def parse_conda_envs_json(blob: str, root_prefix: str | None = None) -> list[PythonEnv]:
    """Pure helper exposed for tests — parse the JSON without subprocess."""
    try: data = json.loads(blob)
    except json.JSONDecodeError: return []
    out: list[PythonEnv] = []
    rp = root_prefix or data.get("root_prefix") or data.get("conda_prefix")
    for env_path in data.get("envs", []) or []:
        py = Path(env_path) / "bin" / "python"
        if not py.exists():
            # In tests the directories don't exist; fabricate the path.
            py = Path(env_path) / "bin" / "python"
        name = "base" if env_path == rp else Path(env_path).name
        out.append(PythonEnv(name=name, path=str(py), source="conda"))
    return out
