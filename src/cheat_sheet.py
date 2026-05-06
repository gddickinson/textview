"""Keyboard cheat-sheet dialog.

Walks the menu bar's actions and renders them as a grouped table:
menu name → action text → shortcut. Updates whenever the dialog opens
so newly-added actions show up automatically.
"""
import html

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout,
)


def _walk(menu, depth: int = 0):
    """Yield (menu_path, QAction) pairs for every leaf action under `menu`."""
    title = menu.title().replace("&", "")
    for action in menu.actions():
        sub = action.menu()
        if sub is not None:
            yield from _walk(sub, depth + 1)
        elif action.text() and not action.isSeparator():
            yield title, action


def show_cheat_sheet(window):
    rows: dict[str, list[tuple[str, str]]] = {}
    mb = window.menuBar()
    for menu_action in mb.actions():
        sub = menu_action.menu()
        if sub is None:
            continue
        for menu_title, a in _walk(sub):
            text = a.text().replace("&", "").replace("…", "...")
            sc = a.shortcut().toString() or "—"
            rows.setdefault(menu_title, []).append((text, sc))

    body = ["<style>",
            "body{font-family:-apple-system,system-ui,sans-serif;font-size:13px;}",
            "h2{margin:18px 0 6px;font-size:14px;color:#88c0d0;}",
            "table{border-collapse:collapse;width:100%;}",
            "td{padding:3px 8px;vertical-align:top;}",
            "td.k{font-family:Menlo,monospace;color:#a3be8c;white-space:nowrap;text-align:right;}",
            "</style>"]
    for section in sorted(rows):
        body.append(f"<h2>{html.escape(section)}</h2><table>")
        for text, sc in rows[section]:
            body.append(
                f"<tr><td>{html.escape(text)}</td>"
                f"<td class='k'>{html.escape(sc)}</td></tr>"
            )
        body.append("</table>")

    dlg = QDialog(window)
    dlg.setWindowTitle("Keyboard shortcuts")
    dlg.resize(640, 720)
    v = QVBoxLayout(dlg)
    tb = QTextBrowser()
    tb.setHtml("".join(body))
    v.addWidget(tb, 1)
    h = QHBoxLayout()
    h.addStretch()
    btn = QPushButton("Close")
    btn.clicked.connect(dlg.accept)
    h.addWidget(btn)
    v.addLayout(h)
    dlg.exec()
