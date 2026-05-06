"""Code/command runner backed by `QProcess`.

Async — non-blocking. Emits `output(text, stream)` for stdout/stderr as
data arrives and `finished(exit_code)` when the process exits.
`run_file(path)` picks an interpreter from the file extension; user can
override the mapping via the `LANGUAGES` settings entry.

On Mac/Linux, child processes can be sandboxed with `RLIMIT_CPU` and
`RLIMIT_AS` via `setup_child` — passed in by RunController from the
runner_cpu_seconds and runner_max_memory_mb settings.
"""
from pathlib import Path
import os
import shlex
import sys
import tempfile

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal


def make_child_limiter(cpu_seconds: int, mem_mb: int):
    """Return a callable suitable for `QProcess.setChildProcessModifier`
    on Mac/Linux that applies CPU and memory rlimits before exec.

    Returns None on Windows (no `resource` module). Both arguments default
    to "no limit" when zero.
    """
    if sys.platform.startswith("win"):
        return None
    try:
        import resource
    except ImportError:
        return None

    def apply():
        if cpu_seconds and cpu_seconds > 0:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
            except (ValueError, OSError):
                pass
        if mem_mb and mem_mb > 0:
            n = mem_mb * 1024 * 1024
            for which in ("RLIMIT_AS", "RLIMIT_DATA"):
                if hasattr(resource, which):
                    try:
                        resource.setrlimit(getattr(resource, which), (n, n))
                    except (ValueError, OSError):
                        pass
    return apply


# ext → argv template. `$FILE` will be replaced with the absolute file path.
DEFAULT_LANGUAGES: dict[str, list[str]] = {
    # Scripting
    "py":   ["python3", "$FILE"],
    "ipynb": ["jupyter", "execute", "$FILE"],
    "js":   ["node", "$FILE"],
    "mjs":  ["node", "$FILE"],
    "cjs":  ["node", "$FILE"],
    "ts":   ["ts-node", "$FILE"],
    "tsx":  ["ts-node", "$FILE"],
    "rb":   ["ruby", "$FILE"],
    "pl":   ["perl", "$FILE"],
    "php":  ["php", "$FILE"],
    "lua":  ["lua", "$FILE"],
    "r":    ["Rscript", "$FILE"],
    # Data — "running" a config/data file means validate + pretty-print.
    "json": ["python3", "-m", "json.tool", "$FILE"],
    "toml": ["python3", "-c",
             "import tomllib, sys, json;"
             " print(json.dumps(tomllib.load(open(sys.argv[1],'rb')), indent=2, default=str))",
             "$FILE"],
    "xml":  ["python3", "-c",
             "import xml.dom.minidom, sys;"
             " print(xml.dom.minidom.parse(sys.argv[1]).toprettyxml(indent='  '))",
             "$FILE"],
    # Shell
    "sh":   ["bash", "$FILE"],
    "bash": ["bash", "$FILE"],
    "zsh":  ["zsh", "$FILE"],
    "fish": ["fish", "$FILE"],
    "ps1":  ["pwsh", "-File", "$FILE"],
    # Compiled / hybrid
    "go":   ["go", "run", "$FILE"],
    "swift": ["swift", "$FILE"],
    "scala": ["scala", "$FILE"],
    "groovy": ["groovy", "$FILE"],
    "clj":  ["clojure", "$FILE"],
    "exs":  ["elixir", "$FILE"],
    "rs":   ["sh", "-c", "rustc --edition=2021 \"$0\" -o /tmp/_tv_rs && /tmp/_tv_rs", "$FILE"],
}


class Runner(QObject):
    """Wraps QProcess for one-shot async executions."""

    output = pyqtSignal(str, str)         # text, stream ("stdout"|"stderr")
    started = pyqtSignal(str)             # human-readable command line
    finished = pyqtSignal(int, int)       # exit_code, exit_status (QProcess.ExitStatus)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc: QProcess | None = None
        self.languages = dict(DEFAULT_LANGUAGES)
        self._child_limiter = None  # set via set_resource_limits

    def set_resource_limits(self, cpu_seconds: int, mem_mb: int):
        """Configure rlimits applied to spawned processes (Mac/Linux only).
        Call once at startup and whenever the user changes the settings.
        """
        self._child_limiter = make_child_limiter(cpu_seconds, mem_mb)

    # -- query ---------------------------------------------------------------

    def is_running(self) -> bool:
        return (
            self._proc is not None
            and self._proc.state() != QProcess.ProcessState.NotRunning
        )

    def supported_extensions(self) -> set[str]:
        return set(self.languages)

    def set_python_interpreter(self, interpreter: str):
        """Override the `python` invocation used by F5 / Run on .py files.
        Accepts an absolute path or a name on PATH."""
        if interpreter:
            self.languages["py"] = [interpreter, "$FILE"]

    # -- run -----------------------------------------------------------------

    def run_argv(self, argv: list[str], cwd: str | None = None,
                 env: dict | None = None, label: str | None = None):
        """Run a literal argv list."""
        if self.is_running():
            self.error.emit("Another process is already running.")
            return False
        if not argv:
            self.error.emit("Empty command.")
            return False

        proc = QProcess(self)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        if cwd:
            proc.setWorkingDirectory(cwd)
        if env is not None:
            qenv = QProcessEnvironment.systemEnvironment()
            for k, v in env.items():
                qenv.insert(k, str(v))
            proc.setProcessEnvironment(qenv)

        proc.readyReadStandardOutput.connect(
            lambda: self.output.emit(
                bytes(proc.readAllStandardOutput()).decode("utf-8", "replace"),
                "stdout",
            )
        )
        proc.readyReadStandardError.connect(
            lambda: self.output.emit(
                bytes(proc.readAllStandardError()).decode("utf-8", "replace"),
                "stderr",
            )
        )
        proc.errorOccurred.connect(self._on_error)
        proc.finished.connect(self._on_finished)

        if self._child_limiter is not None:
            try:
                proc.setChildProcessModifier(self._child_limiter)
            except (AttributeError, TypeError):
                # PyQt < 6.6 doesn't expose this — skip silently.
                pass
        self._proc = proc
        line = label or " ".join(shlex.quote(a) for a in argv)
        self.started.emit(line)
        proc.start()
        return True

    def run_shell(self, command: str, cwd: str | None = None):
        """Run a shell command via /bin/bash -c."""
        return self.run_argv(["bash", "-c", command], cwd=cwd, label=f"$ {command}")

    def run_file(self, path: str, args: list[str] | None = None):
        """Run a script using the configured interpreter for its extension.
        Optional `args` are appended after the file path so scripts can
        receive command-line arguments."""
        ext = Path(path).suffix.lstrip(".").lower()
        argv_tmpl = self.languages.get(ext)
        if not argv_tmpl:
            self.error.emit(
                f"No runner configured for .{ext} files. "
                f"Edit `runner_languages` in settings to add one."
            )
            return False
        argv = [str(Path(path)) if a == "$FILE" else a for a in argv_tmpl]
        if args:
            argv.extend(str(a) for a in args)
        cwd = str(Path(path).resolve().parent)
        return self.run_argv(argv, cwd=cwd, label=" ".join(shlex.quote(a) for a in argv))

    def run_python_snippet(self, code: str, cwd: str | None = None):
        """Write `code` to a temp file and run with python3."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(code)
        f.close()
        return self.run_argv(["python3", f.name], cwd=cwd,
                             label="python3 (selection)")

    # -- stop ----------------------------------------------------------------

    def stop(self):
        if not self._proc:
            return
        self._proc.terminate()
        if not self._proc.waitForFinished(2000):
            self._proc.kill()

    # -- internals -----------------------------------------------------------

    def _on_finished(self, code: int, status):
        self.finished.emit(code, getattr(status, "value", 0))
        self._proc = None

    def _on_error(self, qerr):
        msgs = {
            QProcess.ProcessError.FailedToStart: "Failed to start (binary not found?)",
            QProcess.ProcessError.Crashed: "Process crashed",
            QProcess.ProcessError.Timedout: "Timed out",
            QProcess.ProcessError.WriteError: "Write error",
            QProcess.ProcessError.ReadError: "Read error",
        }
        self.error.emit(msgs.get(qerr, f"Process error: {qerr}"))
