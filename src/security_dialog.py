"""Security UI: warning dialog at open-time + quarantine browser +
on-demand security report."""
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextBrowser,
    QListWidget, QListWidgetItem, QMessageBox,
)

from .security_scanner import scan_file
from . import quarantine as quar


# ---- open-time warning dialog ------------------------------------------

class SecurityWarningDialog(QDialog):
    """Three-button modal: Open anyway / Quarantine / Cancel.

    Result codes (returned via `selected_action`):
        "open"        — user accepted the risk
        "quarantine"  — user wants the file moved into quarantine
        "cancel"      — user backed out
    """

    def __init__(self, parent, scan_result):
        super().__init__(parent)
        self.scan = scan_result
        self.selected_action = "cancel"
        emoji = {"clean": "✅", "suspicious": "⚠️", "dangerous": "⛔"}
        self.setWindowTitle(
            f"{emoji.get(scan_result.risk_level, '?')} "
            f"Security warning — {Path(scan_result.path).name}")
        self.resize(720, 520)

        title = QLabel(
            f"<b>{scan_result.risk_level.title()} content detected</b><br>"
            f"Review the findings before opening this file.")
        title.setWordWrap(True)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.setMarkdown(scan_result.to_markdown())

        self.btn_open = QPushButton("Open anyway")
        self.btn_quar = QPushButton("Quarantine…")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setDefault(True)
        # If we found anything dangerous, lead with Cancel to discourage
        # double-click-through.
        if scan_result.risk_level == "dangerous":
            self.btn_open.setStyleSheet("color: #c44;")

        self.btn_open.clicked.connect(self._on_open)
        self.btn_quar.clicked.connect(self._on_quar)
        self.btn_cancel.clicked.connect(self._on_cancel)

        bottom = QHBoxLayout()
        bottom.addWidget(self.btn_quar)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_open)
        bottom.addWidget(self.btn_cancel)

        root = QVBoxLayout(self)
        root.addWidget(title)
        root.addWidget(self.text, 1)
        root.addLayout(bottom)

    def _on_open(self):
        self.selected_action = "open"; self.accept()

    def _on_quar(self):
        self.selected_action = "quarantine"; self.accept()

    def _on_cancel(self):
        self.selected_action = "cancel"; self.reject()


# ---- routing helper used by MainWindow.open_file -----------------------

def evaluate_open(window, path: str) -> str:
    """Run the scan + (if needed) the warning dialog. Returns the action
    the caller should take: 'open' / 'quarantine' / 'cancel'."""
    d = window.settings_manager.display
    if not getattr(d, "security_scan_on_open", True):
        return "open"
    try:
        result = scan_file(
            path, run_clamav=getattr(d, "security_clamscan_on_open", False))
    except Exception:
        return "open"   # don't let scanner bugs block file opening
    # Filter findings by user toggles.
    keep: list = []
    for f in result.findings:
        if f.category == "office_macro" and not d.security_warn_macros: continue
        if f.category == "pdf_active_content" and not d.security_warn_pdf_js: continue
        if f.category == "executable_extension" and not d.security_block_executables: continue
        keep.append(f)
    result.findings = keep
    if result.risk_level == "clean":
        return "open"
    dlg = SecurityWarningDialog(window, result)
    dlg.exec()
    if dlg.selected_action == "quarantine":
        try:
            rec = quar.quarantine_file(
                path, reason=f"open-time block ({result.risk_level})",
                scan=result)
            window.statusBar().showMessage(
                f"Quarantined → {rec.quarantined_path}", 6000)
        except Exception as e:
            QMessageBox.critical(window, "Quarantine failed", str(e))
    return dlg.selected_action


# ---- on-demand security report ----------------------------------------

def show_security_report(window):
    path = getattr(window, "_current_path", None)
    if not path:
        QMessageBox.information(window, "Security report",
                                "No file is open.")
        return
    d = window.settings_manager.display
    result = scan_file(path,
                       run_clamav=getattr(d, "security_clamscan_on_open", False))
    dlg = QDialog(window)
    dlg.setWindowTitle(f"Security report — {Path(path).name}")
    dlg.resize(720, 520)
    body = QTextBrowser(); body.setMarkdown(result.to_markdown())
    btn = QPushButton("Close"); btn.clicked.connect(dlg.accept)
    bot = QHBoxLayout(); bot.addStretch(1); bot.addWidget(btn)
    lay = QVBoxLayout(dlg); lay.addWidget(body, 1); lay.addLayout(bot)
    dlg.exec()


# ---- quarantine browser -----------------------------------------------

class QuarantineBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quarantined files")
        self.resize(820, 540)
        self.list = QListWidget()
        self.detail = QTextBrowser()
        self.btn_restore = QPushButton("Restore…")
        self.btn_delete = QPushButton("Delete permanently")
        self.btn_close = QPushButton("Close")
        self.btn_restore.clicked.connect(self._restore)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_close.clicked.connect(self.accept)
        self.list.currentItemChanged.connect(self._show_detail)
        bot = QHBoxLayout()
        bot.addWidget(self.btn_restore); bot.addWidget(self.btn_delete)
        bot.addStretch(1); bot.addWidget(self.btn_close)
        body = QHBoxLayout(); body.addWidget(self.list, 1); body.addWidget(self.detail, 2)
        root = QVBoxLayout(self); root.addLayout(body, 1); root.addLayout(bot)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        for rec in quar.list_quarantined():
            item = QListWidgetItem(rec.to_markdown_row())
            item.setData(Qt.ItemDataRole.UserRole, rec.id)
            self.list.addItem(item)
        if self.list.count() > 0: self.list.setCurrentRow(0)
        else: self.detail.setMarkdown("*(no quarantined files)*")

    def _current_id(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    def _show_detail(self, current, _previous):
        if current is None:
            self.detail.setMarkdown(""); return
        qid = current.data(Qt.ItemDataRole.UserRole)
        rec = next((r for r in quar.list_quarantined() if r.id == qid), None)
        if rec is None:
            self.detail.setMarkdown("(missing entry)"); return
        lines = [
            f"# `{rec.id}`", "",
            f"**Original:** `{rec.original_path}`",
            f"**Quarantined:** `{rec.quarantined_path}`",
            f"**When:** {rec.quarantined_at_iso}",
            f"**Reason:** {rec.reason or '(no reason recorded)'}",
        ]
        if rec.findings:
            lines.append("\n## Scan findings\n")
            for f in rec.findings:
                lines.append(f"- **{f.get('severity', '?')}** "
                             f"`{f.get('category', '?')}` — "
                             f"{f.get('description', '')}")
                if f.get("detail"): lines.append(f"  - {f['detail']}")
        self.detail.setMarkdown("\n".join(lines))

    def _restore(self):
        qid = self._current_id()
        if not qid: return
        try:
            target = quar.restore_file(qid)
            QMessageBox.information(self, "Restored",
                                    f"Restored → {target}")
        except FileExistsError as e:
            QMessageBox.warning(self, "Restore failed", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Restore failed", str(e))
        self._refresh()

    def _delete(self):
        qid = self._current_id()
        if not qid: return
        if QMessageBox.question(
                self, "Delete permanently",
                f"Permanently delete quarantined file `{qid}`? "
                f"This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
                ) != QMessageBox.StandardButton.Yes:
            return
        quar.delete_permanently(qid)
        self._refresh()


def show_quarantine_browser(window):
    dlg = QuarantineBrowserDialog(window)
    dlg.exec()
