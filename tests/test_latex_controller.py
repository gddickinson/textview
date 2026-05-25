"""Coverage for src.latex_controller — engine detection, dispatch errors,
and (when a real engine is on PATH) a minimal end-to-end compile.

The end-to-end test is marked `slow` so the default `pytest -m "not slow"`
suite stays fast and doesn't require MacTeX / TeX Live to be installed.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QTimer

from src import latex_controller as lc


def test_pick_engine_returns_none_when_nothing_on_path(monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda _name: None)
    assert lc.pick_engine() is None
    assert lc.available_engines() == []


def test_pick_engine_returns_first_available(monkeypatch):
    # Only pdflatex resolves.
    monkeypatch.setattr(lc.shutil, "which",
                        lambda name: "/usr/bin/pdflatex" if name == "pdflatex" else None)
    picked = lc.pick_engine()
    assert picked is not None
    name, argv = picked
    assert name == "pdflatex"
    assert "-interaction=nonstopmode" in argv


def test_pick_engine_honours_preferred(monkeypatch):
    # Both available — preferred wins.
    monkeypatch.setattr(lc.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in ("pdflatex", "xelatex") else None)
    name, _ = lc.pick_engine(preferred="xelatex")
    assert name == "xelatex"


def test_compile_emits_failure_when_no_engine(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda _name: None)
    src = tmp_path / "doc.tex"
    src.write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
    ctrl = lc.LatexController()
    seen = {}
    def on_done(ok, path, msg):
        seen["ok"] = ok; seen["path"] = path; seen["msg"] = msg
    ctrl.finished.connect(on_done)
    assert ctrl.compile(str(src)) is False
    assert seen["ok"] is False
    assert seen["path"] == ""
    assert "No LaTeX engine" in seen["msg"]


def test_compile_emits_failure_when_source_missing(qapp, monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "pdflatex" else None)
    ctrl = lc.LatexController()
    seen = {}
    ctrl.finished.connect(lambda ok, p, m: seen.update(ok=ok, path=p, msg=m))
    ctrl.compile("/no/such/path.tex")
    assert seen["ok"] is False
    assert "not found" in seen["msg"].lower()


@pytest.mark.slow
def test_real_compile_round_trip(qapp, tmp_path):
    """End-to-end: run a real engine against a trivial document."""
    if not lc.available_engines():
        pytest.skip("No LaTeX engine on PATH; skipping live compile.")
    src = tmp_path / "tiny.tex"
    src.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Hello, TextView.\n"
        "\\end{document}\n"
    )
    ctrl = lc.LatexController()
    loop = QEventLoop()
    out = {}
    def done(ok, path, msg):
        out.update(ok=ok, path=path, msg=msg); loop.quit()
    ctrl.finished.connect(done)
    QTimer.singleShot(60000, loop.quit)  # 60s cap
    ctrl.compile(str(src))
    loop.exec()
    assert out.get("ok") is True, out.get("msg")
    assert Path(out["path"]).is_file()
    assert Path(out["path"]).suffix == ".pdf"
    ctrl.clear()
