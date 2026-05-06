"""NotebookView + KernelHost: load + run + output formatting."""
import sys
import pytest

from src.notebook_view import (
    NotebookView, CellWidget, _format_output, _format_output_msg, _escape,
    _iopub_to_nbformat, _new_cell_dict, _render_data_bundle, _render_one_mime,
)
from src.notebook_kernel import KernelHost, _short_error


SAMPLE = "sample_files/example.ipynb"


def test_load_sample_notebook(qapp):
    v = NotebookView()
    assert v.load(SAMPLE)
    assert v.cell_count() == 3
    assert v.cells()[0].cell_type == "markdown"
    assert v.cells()[1].cell_type == "code"


def test_load_returns_false_on_missing(qapp):
    v = NotebookView()
    assert v.load("/no/such/path.ipynb") is False


def test_load_returns_false_on_garbage_file(qapp, tmp_path):
    bad = tmp_path / "x.ipynb"; bad.write_text("not json", encoding="utf-8")
    v = NotebookView()
    assert v.load(str(bad)) is False


def test_initial_outputs_render_in_cell(qapp):
    """Saved-output rendering is content-based; visibility flips on .show()
    but the test runs offscreen, so we check content rather than visibility."""
    v = NotebookView()
    v.load(SAMPLE)
    code = v.cells()[1]  # the print('hello') cell
    assert "hello" in code.output.toPlainText()


def test_format_output_stream():
    out = {"output_type": "stream", "text": ["hello\n"]}
    assert "hello" in _format_output(out)


def test_format_output_execute_result():
    out = {"output_type": "execute_result", "data": {"text/plain": ["42"]}}
    assert "42" in _format_output(out)


def test_format_output_error_uses_traceback():
    out = {"output_type": "error", "ename": "ValueError",
           "evalue": "bad", "traceback": ["Traceback...", "ValueError: bad"]}
    rendered = _format_output(out)
    assert "ValueError: bad" in rendered


def test_format_output_msg_stream():
    msg = {"msg_type": "stream", "content": {"text": "hi\n"}}
    assert "hi" in _format_output_msg(msg)


def test_format_output_msg_execute_result():
    msg = {"msg_type": "execute_result",
           "content": {"data": {"text/plain": "100"}}}
    assert "100" in _format_output_msg(msg)


def test_iopub_to_nbformat_stream():
    out = _iopub_to_nbformat({"msg_type": "stream", "content": {"name": "stdout", "text": "hi"}})
    assert out["output_type"] == "stream"
    assert out["text"] == "hi"
    assert out["name"] == "stdout"


def test_iopub_to_nbformat_execute_result():
    out = _iopub_to_nbformat({
        "msg_type": "execute_result",
        "content": {"data": {"text/plain": "42"}, "metadata": {}, "execution_count": 7},
    })
    assert out["output_type"] == "execute_result"
    assert out["data"]["text/plain"] == "42"
    assert out["execution_count"] == 7


def test_iopub_to_nbformat_error():
    out = _iopub_to_nbformat({"msg_type": "error",
        "content": {"ename": "ValueError", "evalue": "bad", "traceback": ["a", "b"]}})
    assert out["output_type"] == "error"
    assert out["ename"] == "ValueError"
    assert out["traceback"] == ["a", "b"]


def test_new_cell_dict_code_has_outputs_field():
    c = _new_cell_dict("code", "print(1)")
    assert c["cell_type"] == "code"
    assert c["source"] == "print(1)"
    assert c["outputs"] == []
    assert c["execution_count"] is None


def test_new_cell_dict_markdown_has_no_outputs():
    c = _new_cell_dict("markdown", "# hi")
    assert c["cell_type"] == "markdown"
    assert "outputs" not in c


def test_code_cell_input_is_editable(qapp):
    v = NotebookView(); v.load(SAMPLE)
    code = v.cells()[1]  # print('hello')
    assert not code.body.isReadOnly()


def test_editing_code_cell_updates_source_and_dirties_view(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert not v.is_dirty()
    code = v.cells()[1]
    code.body.setPlainText("print('changed')")
    assert v.is_dirty()
    assert "changed" in code.cell["source"]


def test_add_cell_inserts_at_index(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert v.cell_count() == 3
    new = v.add_cell(after_index=0, cell_type="code")
    assert v.cell_count() == 4
    assert v.cells()[1] is new
    assert v.cells()[1].cell_type == "code"
    assert v.is_dirty()


def test_add_cell_at_end_when_index_negative(qapp):
    v = NotebookView(); v.load(SAMPLE)
    new = v.add_cell(after_index=-1, cell_type="markdown")
    assert v.cells()[-1] is new
    assert v.cells()[-1].cell_type == "markdown"


def test_delete_cell_removes_widget_and_dirties(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert v.cell_count() == 3
    v.delete_cell(1)
    assert v.cell_count() == 2
    assert v.is_dirty()


def test_delete_cell_out_of_range_returns_false(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert v.delete_cell(99) is False
    assert v.cell_count() == 3


def test_change_cell_type_preserves_source(qapp):
    v = NotebookView(); v.load(SAMPLE)
    code = v.cells()[1]
    code.body.setPlainText("# heading\n\ntext")
    v.change_cell_type(1, "markdown")
    new_cell = v.cells()[1]
    assert new_cell.cell_type == "markdown"
    assert "heading" in new_cell.cell["source"]


def test_save_writes_back_to_disk(qapp, tmp_path):
    """Make a change, save, reload, verify the change persisted."""
    src = "sample_files/example.ipynb"
    target = tmp_path / "edited.ipynb"
    target.write_bytes(open(src, "rb").read())
    v = NotebookView()
    v.load(str(target))
    v.cells()[1].body.setPlainText("print('saved-edit')")
    v.add_cell(after_index=-1, cell_type="markdown")
    assert v.save()
    assert not v.is_dirty()
    # Reload
    v2 = NotebookView(); v2.load(str(target))
    sources = [w.cell.get("source", "") for w in v2.cells()]
    joined = "\n".join(sources if isinstance(sources[0], str) else
                       ["".join(s) if isinstance(s, list) else s for s in sources])
    assert "saved-edit" in joined
    assert v2.cell_count() == 4


def test_dirty_signal_fires_on_change(qapp):
    v = NotebookView(); v.load(SAMPLE)
    captured = []
    v.dirty_changed.connect(lambda d: captured.append(d))
    v.cells()[1].body.setPlainText("print('x')")
    assert captured == [True]


def test_load_clears_dirty_state(qapp, tmp_path):
    src = "sample_files/example.ipynb"
    target = tmp_path / "x.ipynb"; target.write_bytes(open(src, "rb").read())
    v = NotebookView(); v.load(str(target))
    v.cells()[1].body.setPlainText("# changed")
    assert v.is_dirty()
    v.load(str(target))  # reload from disk
    assert not v.is_dirty()


# ---- Rich output rendering --------------------------------------------------

def test_render_data_bundle_prefers_html_over_plain():
    out = _render_data_bundle({
        "text/plain": "fallback",
        "text/html": "<b>rich</b>",
    })
    assert "<b>rich</b>" in out
    assert "fallback" not in out


def test_render_data_bundle_prefers_image_over_plain():
    out = _render_data_bundle({
        "text/plain": "<matplotlib.figure>",
        "image/png": "iVBORw0KGgoAAAA=",  # tiny base64 stub
    })
    assert 'src="data:image/png;base64,' in out
    assert "matplotlib" not in out  # plain dropped in favor of png


def test_render_data_bundle_prefers_svg_over_png():
    """SVG ranks higher in priority than PNG."""
    out = _render_data_bundle({
        "image/png": "abc==",
        "image/svg+xml": "<svg><rect/></svg>",
    })
    assert "<svg>" in out
    assert "data:image/png" not in out


def test_render_data_bundle_falls_back_to_plain():
    assert "<pre>" in _render_data_bundle({"text/plain": "hello"})
    assert "hello" in _render_data_bundle({"text/plain": "hello"})


def test_render_one_mime_handles_list_payload():
    """nbformat saves text-y mime types as line-lists."""
    out = _render_one_mime("text/plain", ["line1\n", "line2\n"])
    assert "line1" in out and "line2" in out


def test_render_one_mime_html_passes_through():
    assert _render_one_mime("text/html", "<i>ok</i>") == "<i>ok</i>"


def test_render_one_mime_unknown_falls_back_to_pre():
    out = _render_one_mime("application/x-banana", "{...}")
    assert "<pre>" in out


def test_format_output_with_image_data(qapp):
    """Saved nbformat output shape with image/png renders an <img> tag."""
    out = {"output_type": "display_data",
           "data": {"image/png": ["aGVsbG8="]}}
    rendered = _format_output(out)
    assert 'src="data:image/png;base64,' in rendered
    assert "aGVsbG8=" in rendered


def test_format_output_msg_with_html(qapp):
    msg = {"msg_type": "display_data",
           "content": {"data": {"text/html": "<table><tr><td>x</td></tr></table>"}}}
    rendered = _format_output_msg(msg)
    assert "<table>" in rendered


# ---- Cell move + execution count --------------------------------------------

def test_move_cell_down(qapp):
    v = NotebookView(); v.load(SAMPLE)
    before = [c.cell_type for c in v.cells()]
    assert v.move_cell(0, +1)
    after = [c.cell_type for c in v.cells()]
    assert after[0] == before[1] and after[1] == before[0]


def test_move_cell_up_then_down_idempotent(qapp):
    v = NotebookView(); v.load(SAMPLE)
    snapshot = [c.cell_type for c in v.cells()]
    v.move_cell(2, -1); v.move_cell(1, +1)
    assert [c.cell_type for c in v.cells()] == snapshot


def test_move_cell_at_boundary_returns_false(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert v.move_cell(0, -1) is False  # already at top
    assert v.move_cell(v.cell_count() - 1, +1) is False  # already at bottom


def test_move_cell_dirties_view(qapp):
    v = NotebookView(); v.load(SAMPLE)
    assert not v.is_dirty()
    v.move_cell(0, +1)
    assert v.is_dirty()


def test_indices_update_after_move(qapp):
    v = NotebookView(); v.load(SAMPLE)
    v.move_cell(0, +1)
    for i, c in enumerate(v.cells()):
        assert c.index == i


def test_code_cell_shows_execution_count_in_label(qapp, tmp_path):
    """Loaded cells should show their saved execution_count in the header.
    Use a self-contained fixture so the test isn't coupled to the shared
    sample notebook's evolving counts."""
    import json
    nb = tmp_path / "fixture.ipynb"
    nb.write_text(json.dumps({
        "cells": [
            {"cell_type": "code", "execution_count": 7, "metadata": {},
             "outputs": [], "source": "print(1)"},
            {"cell_type": "code", "execution_count": 42, "metadata": {},
             "outputs": [], "source": "print(2)"},
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }), encoding="utf-8")
    v = NotebookView(); v.load(str(nb))
    labels = [c.lbl_kind.text() for c in v.cells()]
    assert "In [7]:" in labels
    assert "In [42]:" in labels


def test_markdown_cell_shows_kind_label(qapp):
    v = NotebookView(); v.load(SAMPLE)
    md = next(c for c in v.cells() if c.cell_type == "markdown")
    assert "[markdown]" in md.lbl_kind.text()


# ---- Auto-start kernel + error display --------------------------------------

def test_run_cell_without_kernel_shows_error_in_cell(qapp, monkeypatch):
    """Clicking Run on a fresh notebook should never silently do nothing.
    If the kernel can't start (even after the sys.executable fallback),
    the cell's output area should explain why."""
    v = NotebookView(); v.load(SAMPLE)
    # Force every kernel start to fail and stash a useful last_error.
    def fake_start(*_a, **_kw):
        v._kernel.last_error = "ipykernel not installed"
        return False
    monkeypatch.setattr(v._kernel, "start", fake_start)
    statuses = []
    v.status.connect(lambda m: statuses.append(m))
    code_cell = v.cells()[1]  # print('hello')
    v._run_cell(code_cell)
    assert any("Could not start" in s for s in statuses)
    txt = code_cell.output.toPlainText()
    assert "Kernel could not start" in txt
    assert "ipykernel not installed" in txt  # actual last_error surfaced


def test_short_error_walks_exception_chain():
    """The error formatter should surface the root cause, not just the
    outer wrapper exception."""
    try:
        try:
            raise ImportError("dlopen failed: _sqlite3_enable_load_extension")
        except ImportError as inner:
            raise RuntimeError("kernel never became ready") from inner
    except RuntimeError as outer:
        msg = _short_error(outer)
    assert "kernel never became ready" in msg
    assert "_sqlite3_enable_load_extension" in msg
    assert "⇐" in msg  # chain separator


def test_short_error_truncates_to_first_line():
    e = RuntimeError("first line\nsecond line\nthird line")
    assert _short_error(e) == "first line"


def test_kernel_last_error_carried_through(qapp, monkeypatch):
    """`NotebookView.last_error()` reflects the underlying kernel's
    last_error so callers can show specifics in custom UI."""
    v = NotebookView()
    v._kernel.last_error = "kernel exited immediately"
    assert v.last_error() == "kernel exited immediately"


def test_ensure_kernel_falls_back_to_sys_executable(qapp, monkeypatch):
    """Stale config can leave `python_interpreter` pointing at a Python
    without ipykernel. The fallback should retry with `sys.executable`
    (the env running the app), which usually has ipykernel installed."""
    import sys as _sys
    v = NotebookView(); v.load(SAMPLE)
    v.set_default_interpreter("/usr/bin/python3")  # pretend bad
    attempts = []
    def fake_start(interp):
        attempts.append(interp)
        return interp == _sys.executable  # only the fallback succeeds
    monkeypatch.setattr(v._kernel, "start", fake_start)
    monkeypatch.setattr(v._kernel, "is_running", lambda: bool(attempts) and attempts[-1] == _sys.executable)
    monkeypatch.setattr(v._kernel, "execute", lambda code: "msg-stub")
    v._run_cell(v.cells()[1])
    # First attempt: stale interpreter. Second attempt: sys.executable.
    assert attempts == ["/usr/bin/python3", _sys.executable]


def test_ensure_kernel_no_fallback_when_default_is_sys_executable(qapp, monkeypatch):
    """No double-attempt when sys.executable is already the default."""
    import sys as _sys
    v = NotebookView(); v.load(SAMPLE)
    v.set_default_interpreter(_sys.executable)
    attempts = []
    monkeypatch.setattr(v._kernel, "start",
        lambda i: (attempts.append(i), False)[1])
    v._run_cell(v.cells()[1])
    assert attempts == [_sys.executable]  # exactly one attempt, no retry


def test_run_cell_auto_starts_kernel_when_idle(qapp, monkeypatch):
    """The user shouldn't have to manually start a kernel before clicking
    ▶ Run on the first cell — the view should auto-start on first run."""
    v = NotebookView(); v.load(SAMPLE)
    v.set_default_interpreter("/path/to/myenv/bin/python")
    started_with = []
    monkeypatch.setattr(v._kernel, "start",
        lambda interp: (started_with.append(interp), True)[1])
    monkeypatch.setattr(v._kernel, "is_running",
        lambda: bool(started_with))
    monkeypatch.setattr(v._kernel, "execute",
        lambda code: "msg-stub")
    v._run_cell(v.cells()[1])
    assert started_with == ["/path/to/myenv/bin/python"]


def test_set_default_interpreter_ignores_empty(qapp):
    v = NotebookView()
    v.set_default_interpreter("/opt/x/python")
    v.set_default_interpreter("")  # don't clobber on empty
    assert v._default_interpreter == "/opt/x/python"


def test_show_error_displays_red_in_output(qapp):
    v = NotebookView(); v.load(SAMPLE)
    cell = v.cells()[1]
    cell.show_error("Something bad happened.")
    assert "Something bad" in cell.output.toPlainText()
    # Color isn't directly checkable in plain text, but the HTML carries it.
    assert "#c62828" in cell.output.toHtml()


def test_run_all_short_circuits_when_kernel_cant_start(qapp, monkeypatch):
    """run_all should bail out cleanly without burning through every cell
    if the kernel can't start. Up to 3 status messages: starting → fallback
    attempt → final failure (still constant, NOT N — one per cell)."""
    v = NotebookView(); v.load(SAMPLE)
    monkeypatch.setattr(v._kernel, "start", lambda *a, **k: False)
    statuses = []
    v.status.connect(lambda m: statuses.append(m))
    v.run_all()
    assert len(statuses) <= 3
    assert any("Could not start" in s for s in statuses)


def test_escape_html_metas():
    s = _escape("<script>alert('x')</script>")
    assert "<script>" not in s
    assert "&lt;" in s


def test_kernel_host_starts_disconnected(qapp):
    h = KernelHost()
    assert not h.is_running()
    h.shutdown()  # safe before start


@pytest.mark.slow
def test_kernel_host_real_execute(qapp):
    """Real kernel: run `1+2`, expect an execute_result with text/plain '3'.
    Skips when the kernel can't start (e.g. anaconda+sqlite3 ABI mismatch)."""
    try:
        import ipykernel  # noqa: F401
    except ImportError:
        pytest.skip("ipykernel not installed")
    from PyQt6.QtCore import QEventLoop, QDeadlineTimer
    h = KernelHost()
    captured = []
    h.output.connect(lambda mid, m: captured.append(m))
    completed = []
    h.execute_complete.connect(lambda mid: completed.append(mid))
    if not h.start(sys.executable):
        pytest.skip("kernel could not start in this environment")
    try:
        msg_id = h.execute("1 + 2")
        assert msg_id
        deadline = QDeadlineTimer(8000)
        while not deadline.hasExpired() and not completed:
            qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        assert completed
        plain = " ".join(
            str((m["content"].get("data") or {}).get("text/plain", ""))
            for m in captured
            if m["msg_type"] in ("execute_result", "display_data")
        )
        assert "3" in plain
    finally:
        h.shutdown()


@pytest.mark.slow
def test_notebook_view_run_cell(qapp, tmp_path):
    """NotebookView routes cell output back to the right cell.
    Writes its own notebook so the test doesn't depend on the shared
    sample file's source (the user might edit it during real-app use)."""
    try:
        import ipykernel  # noqa: F401
    except ImportError:
        pytest.skip("ipykernel not installed")
    import json
    from PyQt6.QtCore import QEventLoop, QDeadlineTimer
    nb_path = tmp_path / "fixture.ipynb"
    nb_path.write_text(json.dumps({
        "cells": [
            {"cell_type": "code", "execution_count": None, "metadata": {},
             "outputs": [], "source": ["print('TEST_MARKER_42')"]},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3",
                                    "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }), encoding="utf-8")
    v = NotebookView(); v.load(str(nb_path))
    if not v.start_kernel(sys.executable):
        pytest.skip("kernel could not start in this environment")
    try:
        cell = v.cells()[0]
        v._run_cell(cell)
        deadline = QDeadlineTimer(15000)
        while not deadline.hasExpired() and "TEST_MARKER_42" not in cell.output.toPlainText():
            qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        assert "TEST_MARKER_42" in cell.output.toPlainText()
    finally:
        v.shutdown()
