"""Apply DisplaySettings + theme to the viewer widgets.

Extracted from app.py so the main window stays small. All functions take a
`TextViewer` (with `.code` and `.rendered` children), the `DisplaySettings`
instance, and the resolved theme dict.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QPalette, QColor, QFont, QTextOption, QTextCursor, QTextBlockFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit


PROSE_FORMATS = {"markdown", "html", "docx", "epub", "rtf", "odt", "plain"}


def apply_all(viewer, d, theme, fmt: str | None = None):
    apply_theme(viewer, theme, d)
    apply_typography(viewer, d, fmt)
    apply_layout(viewer, d, theme)


def apply_app_palette(theme):
    """Push the theme onto `QApplication`'s palette so dialogs / docks
    that we don't paint widget-by-widget still match the active
    theme. Native macOS chrome (file picker, etc.) ignores this and
    keeps system colours, which is what we want."""
    from PyQt6.QtWidgets import QApplication
    pal = QPalette()
    bg, fg = QColor(theme["bg"]), QColor(theme["fg"])
    sel_bg = QColor(theme["selection_bg"])
    sel_fg = QColor(theme["selection_fg"])
    line_bg = QColor(theme["line_number_bg"])
    pal.setColor(QPalette.ColorRole.Window,          line_bg)
    pal.setColor(QPalette.ColorRole.WindowText,      fg)
    pal.setColor(QPalette.ColorRole.Base,            bg)
    pal.setColor(QPalette.ColorRole.AlternateBase,   line_bg)
    pal.setColor(QPalette.ColorRole.Text,            fg)
    pal.setColor(QPalette.ColorRole.Button,          line_bg)
    pal.setColor(QPalette.ColorRole.ButtonText,      fg)
    pal.setColor(QPalette.ColorRole.Highlight,       sel_bg)
    pal.setColor(QPalette.ColorRole.HighlightedText, sel_fg)
    pal.setColor(QPalette.ColorRole.ToolTipBase,     line_bg)
    pal.setColor(QPalette.ColorRole.ToolTipText,     fg)
    inst = QApplication.instance()
    if inst is not None:
        inst.setPalette(pal)


def apply_theme(viewer, theme, d=None):
    apply_app_palette(theme)
    for w in (viewer.code, viewer.rendered):
        pal = w.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme["bg"]))
        pal.setColor(QPalette.ColorRole.Window, QColor(theme["bg"]))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme["fg"]))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(theme["fg"]))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(theme["selection_bg"]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme["selection_fg"]))
        w.setPalette(pal)
    viewer.code.set_line_number_colors(theme["line_number_bg"], theme["line_number_fg"])
    viewer.code.set_current_line_color(theme["current_line"])
    # Bracket-pair highlight reuses `selection_bg` so the colour stays
    # visible-but-not-jarring on every theme. (Hardcoded `#3c3f41` was
    # invisible on dark themes and ugly on light.)
    viewer.code.set_bracket_match_color(theme["selection_bg"])

    apply_table_theme(viewer.table_view, theme, d)
    # Video / audio view: theme the audio-only overlay so .mp3/.flac
    # don't render with hard-coded dark colours on Light themes.
    if hasattr(viewer, "video_view") and hasattr(viewer.video_view, "apply_theme"):
        viewer.video_view.apply_theme(theme)


def apply_table_theme(tv, theme, d=None):
    """Paint the QTableView from the theme, with per-element overrides
    taken from `DisplaySettings` when present (and non-empty)."""
    def pick(field: str, fallback: str) -> str:
        if d is None:
            return fallback
        v = getattr(d, field, "") or ""
        return v if v else fallback
    bg          = theme["bg"]
    fg          = pick("table_text_color",     theme["fg"])
    alt_row     = pick("table_alt_row_color",  theme["line_number_bg"])
    header_bg   = pick("table_header_bg",      theme["line_number_bg"])
    header_fg   = pick("table_header_fg",      theme["fg"])
    grid        = pick("table_grid_color",     theme["line_number_bg"])
    sel_bg      = pick("table_selection_bg",   theme["selection_bg"])
    sel_fg      = pick("table_selection_fg",   theme["selection_fg"])

    # Clear any existing stylesheet first. Qt's polish cycle on
    # `setStyleSheet` overwrites palette roles whenever the new sheet
    # contains the matching property (e.g. a `color:` rule replaces
    # the palette's `Text` role). By setting the stylesheet to "" before
    # we touch the palette, then re-setting the sheet *without* `color:`
    # / `background-color:` for the view itself, palette wins for cell
    # text/bg and the stylesheet only controls things that can't be
    # expressed in the palette (gridline colour, header borders).
    tv.setStyleSheet("")
    pal = tv.palette()
    for role, color in [
        (QPalette.ColorRole.Base,            bg),
        (QPalette.ColorRole.AlternateBase,   alt_row),
        (QPalette.ColorRole.Window,          header_bg),
        (QPalette.ColorRole.Text,            fg),
        (QPalette.ColorRole.WindowText,      header_fg),
        (QPalette.ColorRole.Highlight,       sel_bg),
        (QPalette.ColorRole.HighlightedText, sel_fg),
        (QPalette.ColorRole.Button,          header_bg),
        (QPalette.ColorRole.ButtonText,      header_fg),
    ]:
        pal.setColor(role, QColor(color))
    tv.setPalette(pal)
    tv.horizontalHeader().setPalette(pal)
    tv.verticalHeader().setPalette(pal)
    # The corner button (top-left intersection of headers) and the
    # vertical header pull from the application palette by default,
    # so a previously-set theme leaks through on switch. Push the
    # theme's header_bg explicitly onto both. `cornerWidget()` is
    # what Qt's QTableView uses internally — styling its palette
    # plus a dedicated stylesheet entry is the belt-and-braces fix.
    corner = tv.cornerWidget() if hasattr(tv, "cornerWidget") else None
    if corner is not None:
        cpal = corner.palette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Button,
                     QPalette.ColorRole.Base):
            cpal.setColor(role, QColor(header_bg))
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            cpal.setColor(role, QColor(header_fg))
        corner.setPalette(cpal)
        corner.setAutoFillBackground(True)
    tv.setStyleSheet(
        f"QTableView {{ gridline-color: {grid}; "
        f"               background-color: {bg}; }}"
        f"QHeaderView::section {{ background-color: {header_bg}; "
        f"                        color: {header_fg}; "
        f"                        border: 1px solid {grid}; "
        f"                        padding: 3px 6px; }}"
        f"QTableView QTableCornerButton::section, "
        f"QAbstractItemView QTableCornerButton::section {{ "
        f"                        background-color: {header_bg}; "
        f"                        border: 1px solid {grid}; }}"
    )


def apply_typography(viewer, d, fmt: str | None = None):
    family, size = d.font_family, d.font_size
    if (getattr(d, "use_prose_typography", False)
            and fmt and fmt in PROSE_FORMATS):
        family = d.prose_font_family or family
        size = d.prose_font_size or size
    font = QFont(family, size)
    font.setWeight(QFont.Weight.Bold if d.font_weight == "bold" else QFont.Weight.Normal)
    if d.letter_spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, d.letter_spacing)
    viewer.code.setFont(font)
    viewer.rendered.setFont(font)
    metrics = viewer.code.fontMetrics()
    viewer.code.setTabStopDistance(metrics.horizontalAdvance(" ") * d.tab_width)


def apply_layout(viewer, d, theme):
    if d.max_content_width and d.word_wrap:
        viewer.code.setLineWrapMode(QPlainTextEdit.LineWrapMode.FixedPixelWidth)
        viewer.code.setLineWrapColumnOrWidth(d.max_content_width)
    else:
        viewer.code.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if d.word_wrap
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
    viewer.code.set_show_line_numbers(d.show_line_numbers)
    viewer.code.set_show_whitespace(d.show_whitespace)
    viewer.code.set_highlight_current(d.highlight_current_line)
    viewer.code.setCursorWidth(d.cursor_width)
    viewer.code.setCenterOnScroll(d.smooth_scroll)

    stylesheet = (
        f"QPlainTextEdit, QTextBrowser {{"
        f"  background-color: {theme['bg']};"
        f"  color: {theme['fg']};"
        f"  padding: {d.padding}px;"
        f"  selection-background-color: {theme['selection_bg']};"
        f"  selection-color: {theme['selection_fg']};"
        f"  border: none;"
        f"}}"
    )
    viewer.code.setStyleSheet(stylesheet)
    viewer.rendered.setStyleSheet(stylesheet)
    apply_doc_options(viewer, d)
    # NOTE: apply_line_height intentionally NOT called here. Block-format
    # mutations land on the undo stack, so we only apply line height when
    # we (re-)load content into the code view, never on every settings tick.


def apply_doc_options(viewer, d):
    align_map = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "right": Qt.AlignmentFlag.AlignRight,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }
    opt = viewer.code.document().defaultTextOption()
    opt.setAlignment(align_map.get(d.text_align, Qt.AlignmentFlag.AlignLeft))
    opt.setWrapMode(
        QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if d.word_wrap
        else QTextOption.WrapMode.NoWrap
    )
    viewer.code.document().setDefaultTextOption(opt)


def apply_table(table_view, d):
    """Push DisplaySettings → TableView. Inherits font from `font_family` /
    `font_size` when the table-specific overrides are empty / 0."""
    family = d.table_font_family or d.font_family
    size = d.table_font_size if d.table_font_size > 0 else d.font_size
    table_view.set_table_font(family, size)
    table_view.set_alternating_rows(d.table_alternate_rows)
    table_view.set_grid(d.table_grid_visible)
    table_view.set_row_height(d.table_row_height)
    table_view.set_max_column_width(d.table_max_col_width)


def apply_line_height(text_widget, ratio):
    """Apply a proportional line height to every block.

    Short-circuits if the document is already at the desired height, so
    repeated calls do not create undo entries. Without this, every settings
    change (or render refresh) would push a phantom edit onto the user's
    undo stack and `Ctrl+Z` would feel broken.
    """
    desired = int(ratio * 100)
    doc = text_widget.document()
    first = doc.firstBlock()
    if first.isValid() and first.blockFormat().lineHeight() == desired:
        return
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    block_fmt = QTextBlockFormat()
    block_fmt.setLineHeight(
        desired,
        QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
    )
    # Layout, not content: keep the modified flag so a freshly opened file
    # does not read as "unsaved changes".
    was_modified = doc.isModified()
    cursor.mergeBlockFormat(block_fmt)
    doc.setModified(was_modified)
