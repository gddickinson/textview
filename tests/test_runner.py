"""Runner: LANGUAGES mapping (incl. data validators) and the JSON pretty-print path."""
import sys

import pytest
from PyQt6.QtCore import QEventLoop, QDeadlineTimer

from src.runner import Runner, DEFAULT_LANGUAGES


def test_python_mapping_registered():
    assert DEFAULT_LANGUAGES["py"] == ["python3", "$FILE"]


def test_json_mapping_uses_stdlib_pretty_print():
    """`python3 -m json.tool $FILE` validates and pretty-prints — chosen
    because it's stdlib (no install) and reports parse errors with line
    numbers."""
    assert DEFAULT_LANGUAGES["json"] == ["python3", "-m", "json.tool", "$FILE"]


def test_toml_mapping_registered():
    cmd = DEFAULT_LANGUAGES["toml"]
    assert cmd[0] == "python3" and "tomllib" in cmd[2]


def test_xml_mapping_registered():
    cmd = DEFAULT_LANGUAGES["xml"]
    assert cmd[0] == "python3" and "minidom" in cmd[2]


def test_runner_reports_supported_extensions(qapp):
    r = Runner()
    exts = r.supported_extensions()
    assert "py" in exts
    assert "json" in exts
    assert "sh" in exts


def _pump_until(qapp, predicate, timeout_ms=8000):
    deadline = QDeadlineTimer(timeout_ms)
    while not deadline.hasExpired() and not predicate():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


@pytest.mark.slow
def test_run_valid_json_file(qapp, tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text('{"b":2,"a":[1,2,3]}', encoding="utf-8")
    r = Runner()
    captured = []; finished = []
    r.output.connect(lambda text, stream: captured.append((stream, text)))
    r.finished.connect(lambda c, s: finished.append((c, s)))
    r.run_file(str(valid))
    _pump_until(qapp, lambda: finished)
    assert finished[0][0] == 0
    out = "".join(t for s, t in captured if s == "stdout")
    assert '"a"' in out and '"b": 2' in out
    assert "\n" in out  # pretty-printed multi-line


@pytest.mark.slow
def test_run_broken_json_reports_parse_error(qapp, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"a":1, "b":}', encoding="utf-8")
    r = Runner()
    captured = []; finished = []
    r.output.connect(lambda text, stream: captured.append((stream, text)))
    r.finished.connect(lambda c, s: finished.append((c, s)))
    r.run_file(str(broken))
    _pump_until(qapp, lambda: finished)
    assert finished[0][0] != 0
    err = "".join(t for s, t in captured if s == "stderr")
    assert "line" in err.lower() or "expecting" in err.lower()


@pytest.mark.slow
def test_run_valid_toml_file(qapp, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('title = "x"\n[server]\nhost = "localhost"\nport = 8080\n', encoding="utf-8")
    r = Runner(); captured = []; finished = []
    r.output.connect(lambda t, s: captured.append((s, t)))
    r.finished.connect(lambda c, s: finished.append((c, s)))
    r.run_file(str(p))
    _pump_until(qapp, lambda: finished)
    assert finished[0][0] == 0
    out = "".join(t for s, t in captured if s == "stdout")
    assert '"title"' in out and '"server"' in out and '"port": 8080' in out


@pytest.mark.slow
def test_run_valid_xml_file(qapp, tmp_path):
    p = tmp_path / "doc.xml"
    p.write_text('<root><child id="1">hi</child></root>', encoding="utf-8")
    r = Runner(); captured = []; finished = []
    r.output.connect(lambda t, s: captured.append((s, t)))
    r.finished.connect(lambda c, s: finished.append((c, s)))
    r.run_file(str(p))
    _pump_until(qapp, lambda: finished)
    assert finished[0][0] == 0
    out = "".join(t for s, t in captured if s == "stdout")
    assert "<root>" in out and "<child" in out
    # toprettyxml produces multi-line output
    assert out.count("\n") > 1
