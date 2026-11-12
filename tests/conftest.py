"""Shared pytest fixtures for the TextView suite.

Conventions:
    - All Qt tests run offscreen; the QApplication is session-scoped so we
      don't pay re-init costs.
    - Settings / memory / snippet stores get pointed at temp paths so tests
      never touch the user's real config.
    - Subprocess-based tests (LSP) are marked `slow` so a fast `pytest -m
      "not slow"` can skip them in tight loops.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

import pytest

# Make `import src.foo` work from any test file regardless of cwd.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Configure Qt plugin paths + offscreen platform before any Qt import.
# PyQt6 is optional so the Qt-free web tests (tests/test_web.py) run with only requirements-web.txt.
try:
    import PyQt6  # noqa: E402
except ImportError:
    PyQt6 = None
if PyQt6 is not None:
    _PLUGINS = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(_PLUGINS / "platforms"))
    os.environ.setdefault("QT_PLUGIN_PATH", str(_PLUGINS))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import Qt, QCoreApplication
    from PyQt6.QtWidgets import QApplication
    QCoreApplication.setOrganizationName("ClaudeTextTests")
    QCoreApplication.setApplicationName("TextViewTests")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def dispose(qapp):
    """dispose(*windows): close and really delete MainWindows. Their QWebEngineView pages must be gone before the
    WebEngine profile is released at interpreter exit, or the process segfaults after the tests finish."""
    def _dispose(*wins):
        from PyQt6.QtCore import QCoreApplication, QEvent
        from src.app import MainWindow
        for w in wins:
            w.close()
            if w in MainWindow._instances:
                MainWindow._instances.remove(w)
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        qapp.processEvents()
    return _dispose


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """Redirect QSettings at a temp path; clean up after each test."""
    from PyQt6.QtCore import QSettings
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path),
    )
    yield tmp_path


@pytest.fixture
def temp_snippet_store(tmp_path, monkeypatch):
    """Repoint the snippet store at a temp file."""
    import src.snippets as sn
    path = tmp_path / "snippets.json"
    monkeypatch.setattr(sn, "DEFAULT_PATH", path)
    return sn.SnippetStore(path=path)


@pytest.fixture
def sample_csv():
    return ("name,age,city,score\n"
            "Alice,30,Boston,92.5\n"
            "Bob,25,Seattle,85.0\n"
            "Carol,42,New York,98.2\n")


@pytest.fixture
def lsp_mock_server_path(tmp_path):
    """A 50-line stdin/stdout LSP responder used by LSP tests."""
    src = tmp_path / "_mock_lsp.py"
    src.write_text(_LSP_MOCK_SCRIPT, encoding="utf-8")
    return str(src)


_LSP_MOCK_SCRIPT = '''
import sys, json
def read_message():
    headers = b""
    while b"\\r\\n\\r\\n" not in headers:
        ch = sys.stdin.buffer.read(1)
        if not ch: return None
        headers += ch
    sep = headers.find(b"\\r\\n\\r\\n")
    length = None
    for line in headers[:sep].split(b"\\r\\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    if length is None: return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))
def write_message(msg):
    body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii"))
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()
while True:
    msg = read_message()
    if msg is None: break
    method = msg.get("method")
    if method == "initialize":
        write_message({"jsonrpc":"2.0","id":msg["id"],"result":{"capabilities":{}}})
    elif method == "textDocument/hover":
        write_message({"jsonrpc":"2.0","id":msg["id"],"result":{"contents":"mock hover"}})
    elif method == "shutdown":
        write_message({"jsonrpc":"2.0","id":msg["id"],"result":None})
    elif method == "exit":
        sys.exit(0)
'''
