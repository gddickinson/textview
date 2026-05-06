"""DiagnosticsPanel: populate, sort, jump-on-row-click."""
from src.diagnostics_panel import DiagnosticsPanel


def _diag(line, char, sev, msg):
    return {
        "range": {"start": {"line": line, "character": char},
                  "end":   {"line": line, "character": char + 1}},
        "severity": sev, "message": msg,
    }


def test_set_diagnostics_populates_table(qapp):
    p = DiagnosticsPanel()
    p.set_diagnostics([
        _diag(2, 0, 2, "warning"),
        _diag(0, 4, 1, "error"),
    ])
    assert p.row_count() == 2


def test_diagnostics_sorted_severity_then_line(qapp):
    """Errors (sev 1) come before Warnings (sev 2); within a severity,
    earlier lines come first."""
    p = DiagnosticsPanel()
    p.set_diagnostics([
        _diag(5, 0, 2, "warn-late"),
        _diag(0, 0, 2, "warn-early"),
        _diag(3, 0, 1, "err-mid"),
    ])
    assert p.diagnostics()[0]["message"] == "err-mid"
    assert p.diagnostics()[1]["message"] == "warn-early"
    assert p.diagnostics()[2]["message"] == "warn-late"


def test_set_diagnostics_clears_previous(qapp):
    p = DiagnosticsPanel()
    p.set_diagnostics([_diag(0, 0, 1, "a"), _diag(1, 0, 1, "b")])
    p.set_diagnostics([_diag(0, 0, 1, "only")])
    assert p.row_count() == 1


def test_jump_requested_emits_on_double_click(qapp):
    p = DiagnosticsPanel()
    p.set_diagnostics([_diag(7, 4, 1, "x")])
    captured = []
    p.jump_requested.connect(lambda l, c: captured.append((l, c)))
    p._emit_jump(0)
    assert captured == [(7, 4)]


def test_window_title_includes_count(qapp):
    p = DiagnosticsPanel()
    p.set_diagnostics([_diag(0, 0, 1, "a"), _diag(1, 0, 2, "b")])
    assert "(2)" in p.windowTitle()


def test_severity_label_per_severity(qapp):
    p = DiagnosticsPanel()
    p.set_diagnostics([_diag(0, 0, s, f"sev{s}") for s in (1, 2, 3, 4)])
    labels = [p.table.item(r, 0).text() for r in range(p.row_count())]
    assert labels == ["Error", "Warn", "Info", "Hint"]
