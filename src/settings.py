"""Display settings: a dataclass of every live-tunable option, plus a manager
that persists them via QSettings and emits a `changed` signal whenever a
setting is updated.
"""
import sys
from dataclasses import dataclass, fields
from PyQt6.QtCore import QObject, pyqtSignal, QSettings


@dataclass
class DisplaySettings:
    # Typography
    font_family: str = "Menlo"
    font_size: int = 14
    font_weight: str = "normal"           # normal | bold
    line_height: float = 1.4              # multiple of font height
    letter_spacing: float = 0.0           # px

    # Layout
    word_wrap: bool = True
    show_line_numbers: bool = True
    tab_width: int = 4
    padding: int = 16
    text_align: str = "left"              # left | right | center | justify
    max_content_width: int = 0            # 0 = unlimited (px)

    # Theme
    theme: str = "Solarized Dark"

    # Behavior
    syntax_highlight: bool = True
    render_markdown: bool = True
    show_whitespace: bool = False
    highlight_current_line: bool = True
    cursor_width: int = 2
    smooth_scroll: bool = True

    # PDF viewer
    pdf_render_mode: str = "rendered"     # rendered | text
    pdf_page_mode: str = "multi"          # single | multi
    pdf_zoom_mode: str = "fit_width"      # fit_width | fit_page | custom
    pdf_zoom: float = 1.0                 # used when pdf_zoom_mode == custom

    # Runner / terminal
    runner_save_before_run: bool = True
    runner_confirm_first_run: bool = True
    # Soft limits applied to spawned processes on Mac/Linux. 0 disables.
    runner_cpu_seconds: int = 60          # SIGXCPU after this many CPU-seconds
    runner_max_memory_mb: int = 1024      # RLIMIT_AS in MB; 0 disables

    # Web / privacy. Defaults are conservative — local HTML can't beacon
    # to remote URLs without a one-time prompt; cookies isolated; insecure
    # content blocked.
    web_javascript: bool = True
    web_local_remote_access: bool = False
    web_local_file_access: bool = True
    web_insecure_content: bool = False
    web_persistent_cookies: bool = True
    web_block_third_party_cookies: bool = True
    web_private_browsing: bool = False
    web_home_url: str = "about:blank"
    web_search_engine: str = "duckduckgo"   # duckduckgo | google | bing | none
    web_default_zoom: float = 1.0

    # Editor saving behavior
    trim_trailing_whitespace_on_save: bool = False
    ensure_final_newline_on_save: bool = True
    auto_reload_on_disk_change: bool = True   # silent reload when buffer is clean
    format_on_save: bool = False              # run formatter for known formats
    lsp_enabled: bool = False                  # enable LSP (Python via pyright)
    lsp_hover_on_pause: bool = False           # auto-fire hover when mouse is still ~600ms
    # Default to sys.executable so the user's notebook / REPL inherits the
    # same env the app is running from (so e.g. anaconda's ipykernel is
    # picked up automatically). User can override via "Choose Python
    # interpreter…".
    python_interpreter: str = sys.executable
    # Agent safety gates. The chat panel already has "Allow actions" as
    # the primary gate; these are SECOND gates for actions that can run
    # arbitrary code at install time (pip install) or at app launch
    # (plugins). All default OFF — the user has to opt in deliberately.
    agent_can_install: bool = False
    agent_can_create_plugins: bool = False
    agent_can_purge_quarantine: bool = False

    # File-loading security. Heuristic scan runs before every file open;
    # findings of severity dangerous/suspicious prompt the user before
    # the file is loaded. ClamAV + sandbox are slower / heavier and stay
    # off by default.
    security_scan_on_open: bool = True
    security_warn_macros: bool = True
    security_warn_pdf_js: bool = True
    security_block_executables: bool = True
    security_clamscan_on_open: bool = False
    security_sandbox_runner: bool = False

    # Per-format typography (prose formats use a different font when on).
    use_prose_typography: bool = False
    prose_font_family: str = "Georgia"
    prose_font_size: int = 16
    prose_line_height: float = 1.65

    # Image
    image_checkered_background: bool = False

    # Tabular / spreadsheet view (CSV / TSV / PSV / TAB)
    csv_view_as_table: bool = True
    table_show_header: bool = True
    table_alternate_rows: bool = True
    table_grid_visible: bool = True
    table_align_numerics: bool = True
    table_font_family: str = ""           # "" → inherit from `font_family`
    table_font_size: int = 0              # 0 → inherit from `font_size`
    table_row_height: int = 22            # px
    table_max_col_width: int = 320        # px; auto-resize cap
    table_delimiter: str = ""             # "" → autodetect with csv.Sniffer
    # Per-element colour overrides for the table view. Empty string = use the
    # value derived from the active theme (see `view_styler.apply_theme`).
    # These exist because some themes' default contrast between gridlines /
    # alt-rows / cells is too subtle to read at a glance.
    table_grid_color: str = ""
    table_text_color: str = ""
    table_alt_row_color: str = ""
    table_header_bg: str = ""
    table_header_fg: str = ""
    table_selection_bg: str = ""
    table_selection_fg: str = ""

    # LLM
    llm_provider: str = "anthropic"            # anthropic | ollama
    llm_model_anthropic: str = "claude-opus-4-7"
    llm_model_ollama: str = "llama3.1:8b"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_ollama_url: str = "http://localhost:11434"
    llm_model_openai: str = "gpt-4o"
    llm_openai_base_url: str = "https://api.openai.com/v1"
    llm_agent_mode: bool = False           # off → no tools sent to model
    llm_agent_actions: bool = False        # on → action tools (write/run) exposed
    llm_agent_max_steps: int = 10          # safety cap for the agent loop
    llm_confirm_actions: bool = True       # prompt before destructive tool calls


class SettingsManager(QObject):
    """Holds the active DisplaySettings and broadcasts changes."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.display = DisplaySettings()
        self._qs = QSettings()
        self._load()

    def update(self, key: str, value):
        if not hasattr(self.display, key):
            return
        if getattr(self.display, key) == value:
            return
        setattr(self.display, key, value)
        self._save()
        self.changed.emit()

    def reset(self):
        self.display = DisplaySettings()
        self._save()
        self.changed.emit()

    def _save(self):
        for f in fields(self.display):
            self._qs.setValue(f"display/{f.name}", getattr(self.display, f.name))

    def _load(self):
        for f in fields(self.display):
            stored = self._qs.value(f"display/{f.name}")
            if stored is None:
                continue
            current = getattr(self.display, f.name)
            target_type = type(current)
            try:
                if target_type is bool:
                    coerced = stored in (True, "true", "True", 1, "1")
                elif target_type is int:
                    coerced = int(stored)
                elif target_type is float:
                    coerced = float(stored)
                else:
                    coerced = target_type(stored)
                setattr(self.display, f.name, coerced)
            except (ValueError, TypeError):
                continue
