"""LSPClient: protocol parsing + real subprocess round-trip with mock server."""
import sys

import pytest
from PyQt6.QtCore import QEventLoop, QDeadlineTimer

from src.lsp_client import LSPClient, to_uri, _parse_content_length


def test_to_uri_absolute():
    assert to_uri("/tmp/x.py") == "file:///tmp/x.py"


def test_to_uri_passes_through_existing_scheme():
    assert to_uri("file:///x") == "file:///x"


def test_parse_content_length_number():
    assert _parse_content_length(b"Content-Length: 42") == 42


def test_parse_content_length_lowercase():
    assert _parse_content_length(b"content-length: 7\r\nFoo: bar") == 7


def test_parse_content_length_missing_returns_none():
    assert _parse_content_length(b"X-Other: 1") is None


def test_drain_messages_pulls_complete_frame(qapp):
    c = LSPClient(["true"])
    c._buf.extend(b"Content-Length: 13\r\n\r\n{\"jsonrpc\":1}")
    assert c._drain_messages() == [{"jsonrpc": 1}]


def test_drain_messages_holds_partial_frame(qapp):
    c = LSPClient(["true"])
    c._buf.extend(b"Content-Length: 100\r\n\r\nshort")
    assert c._drain_messages() == []
    assert len(c._buf) > 0


def test_drain_messages_drops_malformed_json_body(qapp):
    c = LSPClient(["true"])
    c._buf.extend(b"Content-Length: 5\r\n\r\nabcde")  # not JSON
    assert c._drain_messages() == []  # body consumed, message dropped


def _pump_until(qapp, predicate, timeout_ms=3000):
    deadline = QDeadlineTimer(timeout_ms)
    while not deadline.hasExpired() and not predicate():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


@pytest.mark.slow
def test_subprocess_initialize_roundtrip(qapp, lsp_mock_server_path):
    c = LSPClient([sys.executable, lsp_mock_server_path])
    started = []
    c.started_ok.connect(lambda: started.append(True))
    assert c.start(root_uri="file:///tmp")
    _pump_until(qapp, lambda: started)
    assert started == [True]
    c.shutdown()


@pytest.mark.slow
def test_subprocess_hover_roundtrip(qapp, lsp_mock_server_path):
    c = LSPClient([sys.executable, lsp_mock_server_path])
    started = []; responses = []
    c.started_ok.connect(lambda: started.append(True))
    c.response_received.connect(lambda i, r, e: responses.append((i, r, e)))
    c.start(root_uri="file:///tmp")
    _pump_until(qapp, lambda: started)
    rid = c.hover("file:///tmp/x.py", 0, 0)
    _pump_until(qapp, lambda: any(r[0] == rid for r in responses))
    hit = next((r for r in responses if r[0] == rid), None)
    assert hit is not None and hit[1].get("contents") == "mock hover"
    c.shutdown()


def test_references_request_method_signature(qapp):
    """The references method should send a `textDocument/references` request
    with a context.includeDeclaration field — verified via _pending tracking."""
    c = LSPClient(["true"])
    # We can't actually start the kernel here, so monkey-patch _send_message
    # to capture the JSON instead.
    captured = []
    c._send_message = lambda msg: captured.append(msg)
    rid = c.references("file:///x.py", 5, 4)
    assert isinstance(rid, int) and rid > 0
    assert len(captured) == 1
    msg = captured[0]
    assert msg["method"] == "textDocument/references"
    p = msg["params"]
    assert p["textDocument"]["uri"] == "file:///x.py"
    assert p["position"] == {"line": 5, "character": 4}
    assert p["context"]["includeDeclaration"] is True


def test_references_include_declaration_false(qapp):
    c = LSPClient(["true"])
    captured = []
    c._send_message = lambda msg: captured.append(msg)
    c.references("file:///x.py", 0, 0, include_declaration=False)
    assert captured[0]["params"]["context"]["includeDeclaration"] is False
