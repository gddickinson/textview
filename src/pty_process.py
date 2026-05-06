"""Spawn a child process attached to a pseudo-terminal.

Wraps Python's `pty.fork()` so the parent can read/write the PTY master
file descriptor while the child sees a real TTY. Read events are
delivered asynchronously via `QSocketNotifier` (no thread, no polling).

This is the IO layer underneath `pty_terminal.TerminalWidget` — the
widget feeds incoming bytes into a `pyte.Screen` for VT100 emulation
and writes user keystrokes back through `write()`.
"""
import os
import pty
import signal
import fcntl
import termios
import struct

from PyQt6.QtCore import QObject, QSocketNotifier, pyqtSignal


class PtyProcess(QObject):
    """Async PTY-backed child process. Owns the master fd and a notifier."""

    output = pyqtSignal(bytes)
    exited = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid: int | None = None
        self._master_fd: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._exit_emitted = False

    def is_running(self) -> bool:
        return self._pid is not None and self._master_fd is not None

    def start(self, argv: list[str], cwd: str | None = None,
              env: dict[str, str] | None = None) -> bool:
        if self.is_running():
            return False
        try:
            pid, fd = pty.fork()
        except OSError:
            return False
        if pid == 0:
            # Child — replace ourselves with the shell.
            try:
                if cwd:
                    os.chdir(cwd)
                e = dict(env if env is not None else os.environ)
                e.setdefault("TERM", "xterm-256color")
                e.setdefault("COLORTERM", "truecolor")
                os.execvpe(argv[0], argv, e)
            except Exception:
                pass
            # If exec fails we must not return — would corrupt the parent.
            os._exit(127)

        # Parent.
        self._pid = pid
        self._master_fd = fd
        # Non-blocking on the master so a partial read returns instead
        # of blocking the GUI thread when the child writes slowly.
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)
        self._exit_emitted = False
        return True

    def write(self, data: bytes):
        if self._master_fd is None:
            return
        try:
            os.write(self._master_fd, data)
        except (BrokenPipeError, OSError):
            pass

    def set_size(self, rows: int, cols: int):
        if self._master_fd is None:
            return
        try:
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    def kill(self):
        if self._pid:
            try:
                os.kill(self._pid, signal.SIGHUP)
            except OSError:
                pass

    # -- internal -----------------------------------------------------------

    def _on_readable(self):
        if self._master_fd is None:
            return
        try:
            data = os.read(self._master_fd, 8192)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._cleanup()
            return
        self.output.emit(data)

    def _cleanup(self):
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        code = -1
        if self._pid:
            try:
                _, status = os.waitpid(self._pid, os.WNOHANG)
                if os.WIFEXITED(status):
                    code = os.WEXITSTATUS(status)
                elif os.WIFSIGNALED(status):
                    code = -os.WTERMSIG(status)
            except OSError:
                pass
            self._pid = None
        if not self._exit_emitted:
            self._exit_emitted = True
            self.exited.emit(code)
