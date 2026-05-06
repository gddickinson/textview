"""Live-updating configuration panel as a `QDockWidget`.

Every control writes back to the `SettingsManager`, which broadcasts a
`changed` signal that the main window listens to and re-applies. The panel
itself never reads the live state after construction except via the manager.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QPushButton, QHBoxLayout, QScrollArea, QLabel, QTabWidget, QLineEdit,
)
from .color_picker_field import ColorPickerField

from .themes import theme_names


class ConfigPanel(QDockWidget):
    def __init__(self, settings_manager, parent=None):
        super().__init__("Configuration", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.sm = settings_manager
        self._suppress = True
        self._build_ui()
        self._sync_from_settings()
        self._suppress = False

    # -- Build ---------------------------------------------------------------

    def _build_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self._tab([self._typography_group(), self._theme_group(),
                               self._layout_group()]), "Display")
        tabs.addTab(self._tab([self._behavior_group(), self._editor_group()]),
                    "Editor")
        tabs.addTab(self._tab([self._pdf_group(), self._image_group(),
                               self._table_group(), self._table_colors_group()]),
                    "Files")
        tabs.addTab(self._tab([self._browser_group()]), "Browser")
        tabs.addTab(self._tab([self._privacy_group()]), "Privacy & Security")
        outer = QWidget()
        v = QVBoxLayout(outer)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(tabs, 1)
        v.addWidget(self._reset_row())
        self.setWidget(outer)
        self.setMinimumWidth(360)

    def _tab(self, groups: list[QGroupBox]) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        for g in groups:
            layout.addWidget(g)
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _typography_group(self):
        g = QGroupBox("Typography")
        f = QFormLayout(g)

        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(
            lambda fnt: self._set("font_family", fnt.family())
        )
        f.addRow("Font family:", self.font_combo)

        self.font_size = QSpinBox()
        self.font_size.setRange(6, 96)
        self.font_size.setSuffix(" pt")
        self.font_size.valueChanged.connect(lambda v: self._set("font_size", v))
        f.addRow("Font size:", self.font_size)

        self.font_weight = QComboBox()
        self.font_weight.addItems(["normal", "bold"])
        self.font_weight.currentTextChanged.connect(
            lambda v: self._set("font_weight", v)
        )
        f.addRow("Font weight:", self.font_weight)

        self.line_height = QDoubleSpinBox()
        self.line_height.setRange(0.8, 4.0)
        self.line_height.setSingleStep(0.1)
        self.line_height.setDecimals(2)
        self.line_height.valueChanged.connect(lambda v: self._set("line_height", v))
        f.addRow("Line height:", self.line_height)

        self.letter_spacing = QDoubleSpinBox()
        self.letter_spacing.setRange(-2.0, 8.0)
        self.letter_spacing.setSingleStep(0.1)
        self.letter_spacing.setSuffix(" px")
        self.letter_spacing.valueChanged.connect(
            lambda v: self._set("letter_spacing", v)
        )
        f.addRow("Letter spacing:", self.letter_spacing)

        return g

    def _layout_group(self):
        g = QGroupBox("Layout")
        f = QFormLayout(g)

        self.word_wrap = QCheckBox("Wrap long lines")
        self.word_wrap.toggled.connect(lambda v: self._set("word_wrap", v))
        f.addRow(self.word_wrap)

        self.line_numbers = QCheckBox("Show line numbers")
        self.line_numbers.toggled.connect(
            lambda v: self._set("show_line_numbers", v)
        )
        f.addRow(self.line_numbers)

        self.tab_width = QSpinBox()
        self.tab_width.setRange(1, 16)
        self.tab_width.valueChanged.connect(lambda v: self._set("tab_width", v))
        f.addRow("Tab width:", self.tab_width)

        self.padding = QSpinBox()
        self.padding.setRange(0, 96)
        self.padding.setSuffix(" px")
        self.padding.valueChanged.connect(lambda v: self._set("padding", v))
        f.addRow("Padding:", self.padding)

        self.text_align = QComboBox()
        self.text_align.addItems(["left", "right", "center", "justify"])
        self.text_align.currentTextChanged.connect(
            lambda v: self._set("text_align", v)
        )
        f.addRow("Text alignment:", self.text_align)

        self.max_width = QSpinBox()
        self.max_width.setRange(0, 4000)
        self.max_width.setSingleStep(50)
        self.max_width.setSuffix(" px")
        self.max_width.setSpecialValueText("Unlimited")
        self.max_width.valueChanged.connect(
            lambda v: self._set("max_content_width", v)
        )
        f.addRow("Max content width:", self.max_width)

        return g

    def _theme_group(self):
        g = QGroupBox("Theme")
        f = QFormLayout(g)

        self.theme = QComboBox()
        self.theme.addItems(theme_names())
        self.theme.currentTextChanged.connect(lambda v: self._set("theme", v))
        f.addRow("Theme:", self.theme)

        hint = QLabel(
            "<i>Theme controls the editor background, foreground, gutter, "
            "and the Pygments style used for syntax highlighting.</i>"
        )
        hint.setWordWrap(True)
        f.addRow(hint)

        return g

    def _behavior_group(self):
        g = QGroupBox("Behavior")
        f = QFormLayout(g)

        self.syntax = QCheckBox("Enable syntax highlighting")
        self.syntax.toggled.connect(lambda v: self._set("syntax_highlight", v))
        f.addRow(self.syntax)

        self.markdown = QCheckBox("Render Markdown / HTML")
        self.markdown.toggled.connect(lambda v: self._set("render_markdown", v))
        f.addRow(self.markdown)

        self.whitespace = QCheckBox("Show whitespace characters")
        self.whitespace.toggled.connect(lambda v: self._set("show_whitespace", v))
        f.addRow(self.whitespace)

        self.highlight_line = QCheckBox("Highlight current line")
        self.highlight_line.toggled.connect(
            lambda v: self._set("highlight_current_line", v)
        )
        f.addRow(self.highlight_line)

        self.smooth_scroll = QCheckBox("Smooth scrolling")
        self.smooth_scroll.toggled.connect(lambda v: self._set("smooth_scroll", v))
        f.addRow(self.smooth_scroll)

        self.cursor_w = QSpinBox()
        self.cursor_w.setRange(1, 10)
        self.cursor_w.setSuffix(" px")
        self.cursor_w.valueChanged.connect(lambda v: self._set("cursor_width", v))
        f.addRow("Cursor width:", self.cursor_w)

        return g

    def _pdf_group(self):
        g = QGroupBox("PDF viewer")
        f = QFormLayout(g)

        self.pdf_mode = QComboBox()
        self.pdf_mode.addItems(["rendered", "text"])
        self.pdf_mode.currentTextChanged.connect(
            lambda v: self._set("pdf_render_mode", v)
        )
        f.addRow("Display mode:", self.pdf_mode)

        self.pdf_page_mode = QComboBox()
        self.pdf_page_mode.addItems(["multi", "single"])
        self.pdf_page_mode.currentTextChanged.connect(
            lambda v: self._set("pdf_page_mode", v)
        )
        f.addRow("Page layout:", self.pdf_page_mode)

        self.pdf_zoom_mode = QComboBox()
        self.pdf_zoom_mode.addItems(["fit_width", "fit_page", "custom"])
        self.pdf_zoom_mode.currentTextChanged.connect(
            lambda v: self._set("pdf_zoom_mode", v)
        )
        f.addRow("Zoom mode:", self.pdf_zoom_mode)

        self.pdf_zoom = QDoubleSpinBox()
        self.pdf_zoom.setRange(0.1, 8.0)
        self.pdf_zoom.setSingleStep(0.1)
        self.pdf_zoom.setDecimals(2)
        self.pdf_zoom.setSuffix("×")
        self.pdf_zoom.valueChanged.connect(lambda v: self._set("pdf_zoom", v))
        f.addRow("Zoom factor:", self.pdf_zoom)

        hint = QLabel(
            "<i>Rendered mode shows the original PDF layout. Text mode shows "
            "extracted text in the code view (useful for copy / search). "
            "Toggle on the fly with <b>Ctrl+T</b>.</i>"
        )
        hint.setWordWrap(True)
        f.addRow(hint)

        return g

    def _editor_group(self):
        g = QGroupBox("Editor")
        f = QFormLayout(g)
        self.cb_trim = QCheckBox("Trim trailing whitespace on save")
        self.cb_trim.toggled.connect(lambda v: self._set("trim_trailing_whitespace_on_save", v))
        f.addRow(self.cb_trim)
        self.cb_final_nl = QCheckBox("Ensure final newline on save")
        self.cb_final_nl.toggled.connect(lambda v: self._set("ensure_final_newline_on_save", v))
        f.addRow(self.cb_final_nl)
        self.cb_fmt_save = QCheckBox("Format on save (black / prettier / gofmt …)")
        self.cb_fmt_save.setToolTip(
            "Runs the appropriate formatter for the current file's language "
            "before writing. Falls back silently if the formatter isn't on PATH."
        )
        self.cb_fmt_save.toggled.connect(lambda v: self._set("format_on_save", v))
        f.addRow(self.cb_fmt_save)
        self.cb_prose = QCheckBox("Prose typography for prose formats")
        self.cb_prose.setToolTip(
            "When checked, prose formats (markdown, HTML, DOCX, EPUB, RTF) "
            "use the prose font / size below instead of the global typography."
        )
        self.cb_prose.toggled.connect(lambda v: self._set("use_prose_typography", v))
        f.addRow(self.cb_prose)
        self.prose_family = QFontComboBox()
        self.prose_family.currentFontChanged.connect(
            lambda fnt: self._set("prose_font_family", fnt.family()))
        f.addRow("Prose font:", self.prose_family)
        self.prose_size = QSpinBox(); self.prose_size.setRange(6, 96)
        self.prose_size.setSuffix(" pt")
        self.prose_size.valueChanged.connect(lambda v: self._set("prose_font_size", v))
        f.addRow("Prose size:", self.prose_size)
        return g

    def _image_group(self):
        g = QGroupBox("Image viewer")
        f = QFormLayout(g)
        self.cb_checker = QCheckBox("Checkered transparency backdrop")
        self.cb_checker.toggled.connect(lambda v: self._set("image_checkered_background", v))
        f.addRow(self.cb_checker)
        return g

    def _table_group(self):
        g = QGroupBox("Table / spreadsheet view")
        f = QFormLayout(g)
        self.cb_csv_table = QCheckBox("Open CSV / TSV files as a table")
        self.cb_csv_table.toggled.connect(lambda v: self._set("csv_view_as_table", v))
        f.addRow(self.cb_csv_table)
        self.cb_table_header = QCheckBox("Treat first row as header")
        self.cb_table_header.toggled.connect(lambda v: self._set("table_show_header", v))
        f.addRow(self.cb_table_header)
        self.cb_table_alt = QCheckBox("Alternate row shading")
        self.cb_table_alt.toggled.connect(lambda v: self._set("table_alternate_rows", v))
        f.addRow(self.cb_table_alt)
        self.cb_table_grid = QCheckBox("Show grid lines")
        self.cb_table_grid.toggled.connect(lambda v: self._set("table_grid_visible", v))
        f.addRow(self.cb_table_grid)
        self.cb_table_align = QCheckBox("Right-align numeric columns")
        self.cb_table_align.toggled.connect(lambda v: self._set("table_align_numerics", v))
        f.addRow(self.cb_table_align)
        self.le_table_font = QLineEdit()
        self.le_table_font.setPlaceholderText("(inherit from main font)")
        self.le_table_font.editingFinished.connect(
            lambda: self._set("table_font_family", self.le_table_font.text())
        )
        f.addRow("Table font family:", self.le_table_font)
        self.sb_table_size = QSpinBox(); self.sb_table_size.setRange(0, 48)
        self.sb_table_size.setSpecialValueText("inherit")
        self.sb_table_size.valueChanged.connect(lambda v: self._set("table_font_size", v))
        f.addRow("Table font size (pt):", self.sb_table_size)
        self.sb_table_row = QSpinBox(); self.sb_table_row.setRange(14, 64)
        self.sb_table_row.valueChanged.connect(lambda v: self._set("table_row_height", v))
        f.addRow("Row height (px):", self.sb_table_row)
        self.sb_table_colcap = QSpinBox(); self.sb_table_colcap.setRange(60, 1200)
        self.sb_table_colcap.valueChanged.connect(lambda v: self._set("table_max_col_width", v))
        f.addRow("Max column width (px):", self.sb_table_colcap)
        self.cb_table_delim = QComboBox()
        self.cb_table_delim.addItems(["(auto)", ",", "tab", ";", "|"])
        self.cb_table_delim.currentTextChanged.connect(self._on_delim_changed)
        f.addRow("Delimiter:", self.cb_table_delim)
        return g

    def _on_delim_changed(self, label: str):
        mapping = {"(auto)": "", ",": ",", "tab": "\t", ";": ";", "|": "|"}
        self._set("table_delimiter", mapping.get(label, ""))

    _TABLE_COLOR_FIELDS = [
        ("Cell text",      "table_text_color"),
        ("Gridlines",      "table_grid_color"),
        ("Alt-row band",   "table_alt_row_color"),
        ("Header bg",      "table_header_bg"),
        ("Header text",    "table_header_fg"),
        ("Selection bg",   "table_selection_bg"),
        ("Selection text", "table_selection_fg"),
    ]

    def _table_colors_group(self):
        g = QGroupBox("Table colours (override theme)")
        f = QFormLayout(g)
        self._color_fields: dict[str, ColorPickerField] = {}
        for label, field in self._TABLE_COLOR_FIELDS:
            cp = ColorPickerField(getattr(self.sm.display, field, "") or "")
            cp.changed.connect(lambda v, fld=field: self._set(fld, v))
            self._color_fields[field] = cp
            f.addRow(label + ":", cp)
        return g

    def _browser_group(self):
        g = QGroupBox("Browser")
        f = QFormLayout(g)
        self.le_home = QLineEdit()
        self.le_home.setPlaceholderText("about:blank")
        self.le_home.editingFinished.connect(
            lambda: self._set("web_home_url", self.le_home.text())
        )
        f.addRow("Home page:", self.le_home)
        self.cb_search = QComboBox()
        self.cb_search.addItems(["duckduckgo", "google", "bing", "none"])
        self.cb_search.currentTextChanged.connect(lambda v: self._set("web_search_engine", v))
        f.addRow("Search engine:", self.cb_search)
        self.sb_zoom = QDoubleSpinBox()
        self.sb_zoom.setRange(0.25, 5.0); self.sb_zoom.setSingleStep(0.1); self.sb_zoom.setSuffix("×")
        self.sb_zoom.valueChanged.connect(lambda v: self._set("web_default_zoom", v))
        f.addRow("Default zoom:", self.sb_zoom)
        return g

    def _privacy_group(self):
        g = QGroupBox("Privacy & Security")
        f = QFormLayout(g)
        self.cb_js = QCheckBox("Enable JavaScript")
        self.cb_js.toggled.connect(lambda v: self._set("web_javascript", v))
        f.addRow(self.cb_js)
        self.cb_remote = QCheckBox("Allow local files to load remote URLs")
        self.cb_remote.setToolTip(
            "Required for local HTML pages that use CDN scripts (Leaflet, "
            "MathJax, etc.). Off by default — opening untrusted local HTML "
            "files can otherwise beacon to attacker-controlled servers."
        )
        self.cb_remote.toggled.connect(lambda v: self._set("web_local_remote_access", v))
        f.addRow(self.cb_remote)
        self.cb_local_files = QCheckBox("Allow local files to load sibling files")
        self.cb_local_files.toggled.connect(lambda v: self._set("web_local_file_access", v))
        f.addRow(self.cb_local_files)
        self.cb_insecure = QCheckBox("Allow mixed (insecure) content")
        self.cb_insecure.toggled.connect(lambda v: self._set("web_insecure_content", v))
        f.addRow(self.cb_insecure)
        self.cb_cookies = QCheckBox("Persist cookies across sessions")
        self.cb_cookies.toggled.connect(lambda v: self._set("web_persistent_cookies", v))
        f.addRow(self.cb_cookies)
        self.cb_3p_cookies = QCheckBox("Block third-party cookies")
        self.cb_3p_cookies.toggled.connect(lambda v: self._set("web_block_third_party_cookies", v))
        f.addRow(self.cb_3p_cookies)
        self.cb_run_confirm = QCheckBox("Confirm before first run of a file (F5)")
        self.cb_run_confirm.toggled.connect(lambda v: self._set("runner_confirm_first_run", v))
        f.addRow(self.cb_run_confirm)
        hint = QLabel(
            "<i>Trusted-file lists for the runner and for local pages "
            "loading remote URLs are stored separately and can be cleared "
            "via the Edit menu.</i>"
        )
        hint.setWordWrap(True)
        f.addRow(hint)
        return g

    def _reset_row(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Reset to defaults")
        btn.clicked.connect(self._on_reset)
        h.addWidget(btn)
        h.addStretch()
        return w

    # -- Sync ----------------------------------------------------------------

    def _sync_from_settings(self):
        self._suppress = True
        d = self.sm.display
        self.font_combo.setCurrentFont(QFont(d.font_family))
        self.font_size.setValue(d.font_size)
        self.font_weight.setCurrentText(d.font_weight)
        self.line_height.setValue(d.line_height)
        self.letter_spacing.setValue(d.letter_spacing)
        self.word_wrap.setChecked(d.word_wrap)
        self.line_numbers.setChecked(d.show_line_numbers)
        self.tab_width.setValue(d.tab_width)
        self.padding.setValue(d.padding)
        self.text_align.setCurrentText(d.text_align)
        self.max_width.setValue(d.max_content_width)
        self.theme.setCurrentText(d.theme)
        self.syntax.setChecked(d.syntax_highlight)
        self.markdown.setChecked(d.render_markdown)
        self.whitespace.setChecked(d.show_whitespace)
        self.highlight_line.setChecked(d.highlight_current_line)
        self.smooth_scroll.setChecked(d.smooth_scroll)
        self.cursor_w.setValue(d.cursor_width)
        self.pdf_mode.setCurrentText(d.pdf_render_mode)
        self.pdf_page_mode.setCurrentText(d.pdf_page_mode)
        self.pdf_zoom_mode.setCurrentText(d.pdf_zoom_mode)
        self.pdf_zoom.setValue(d.pdf_zoom)
        self.cb_trim.setChecked(d.trim_trailing_whitespace_on_save)
        self.cb_final_nl.setChecked(d.ensure_final_newline_on_save)
        self.cb_fmt_save.setChecked(d.format_on_save)
        self.cb_prose.setChecked(d.use_prose_typography)
        self.prose_family.setCurrentFont(QFont(d.prose_font_family))
        self.prose_size.setValue(d.prose_font_size)
        self.cb_checker.setChecked(d.image_checkered_background)
        self.cb_csv_table.setChecked(d.csv_view_as_table)
        self.cb_table_header.setChecked(d.table_show_header)
        self.cb_table_alt.setChecked(d.table_alternate_rows)
        self.cb_table_grid.setChecked(d.table_grid_visible)
        self.cb_table_align.setChecked(d.table_align_numerics)
        self.le_table_font.setText(d.table_font_family)
        self.sb_table_size.setValue(d.table_font_size)
        self.sb_table_row.setValue(d.table_row_height)
        self.sb_table_colcap.setValue(d.table_max_col_width)
        self.cb_table_delim.setCurrentText(
            {"": "(auto)", ",": ",", "\t": "tab", ";": ";", "|": "|"}.get(
                d.table_delimiter, "(auto)"))
        for _, field in self._TABLE_COLOR_FIELDS:
            cp = self._color_fields.get(field)
            if cp: cp.set_value_silent(getattr(d, field, "") or "")
        self.le_home.setText(d.web_home_url)
        self.cb_search.setCurrentText(d.web_search_engine)
        self.sb_zoom.setValue(d.web_default_zoom)
        self.cb_js.setChecked(d.web_javascript)
        self.cb_remote.setChecked(d.web_local_remote_access)
        self.cb_local_files.setChecked(d.web_local_file_access)
        self.cb_insecure.setChecked(d.web_insecure_content)
        self.cb_cookies.setChecked(d.web_persistent_cookies)
        self.cb_3p_cookies.setChecked(d.web_block_third_party_cookies)
        self.cb_run_confirm.setChecked(d.runner_confirm_first_run)
        self._suppress = False

    def _set(self, key, value):
        if self._suppress:
            return
        self.sm.update(key, value)

    def _on_reset(self):
        self.sm.reset()
        self._sync_from_settings()
