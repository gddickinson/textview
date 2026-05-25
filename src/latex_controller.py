"""LaTeX compilation controller + MainWindow glue.

`LatexController` is the async compiler (QObject + QProcess). The two
free functions at the bottom — `compile_active_buffer(window)` and
`apply_compiled_pdf(window, ok, pdf_path, message)` — are the
MainWindow handlers, factored out so `app.py` stays under its line cap.

Compiles `.tex` source to PDF in a temp build directory using whichever
TeX engine the host has on PATH (latexmk preferred — it handles the
multi-pass aux/bib resolution for you; falls back to pdflatex / xelatex /
lualatex with a single non-interactive pass).

Runs the engine in a `QProcess` so the UI stays responsive, and emits
`finished(ok: bool, pdf_path: str, message: str)` when the compile is
done. The temp directory lives for the controller's lifetime so the
resulting PDF stays readable by the viewer; it is cleaned on `clear()`
or on Python interpreter exit.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


# Engine command templates. `{src}` is the .tex file's basename inside
# the build dir; `{jobname}` is the same without extension. Each entry
# is `(executable, [argv tail])`.
_ENGINES: list[tuple[str, list[str]]] = [
    # latexmk handles re-runs for refs / bibliography automatically.
    ("latexmk", ["-pdf", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]),
    ("pdflatex", ["-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]),
    ("xelatex", ["-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]),
    ("lualatex", ["-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]),
]


def available_engines() -> list[str]:
    """Return the subset of known engines that resolve on PATH."""
    return [name for name, _ in _ENGINES if shutil.which(name)]


def pick_engine(preferred: str | None = None) -> tuple[str, list[str]] | None:
    """Return (executable, base argv) for the first engine we can find.

    `preferred` (e.g. 'xelatex') is tried first if it resolves; otherwise
    the default search order in `_ENGINES` is used.
    """
    if preferred:
        for name, argv in _ENGINES:
            if name == preferred and shutil.which(name):
                return name, argv
    for name, argv in _ENGINES:
        if shutil.which(name):
            return name, argv
    return None


def needs_unicode_engine(source_text: str) -> bool:
    """Return True if the document uses features that require xelatex /
    lualatex (fontspec, system fonts, unicode-math). pdflatex will fail
    on these even when the file is otherwise valid LaTeX.
    """
    if not source_text:
        return False
    markers = (
        "\\usepackage{fontspec}",
        "\\RequirePackage{fontspec}",
        "\\setmainfont",
        "\\setsansfont",
        "\\setmonofont",
        "\\newfontfamily",
        "\\usepackage{unicode-math}",
    )
    return any(m in source_text for m in markers)


class LatexController(QObject):
    """Compile a .tex source file to PDF asynchronously."""

    # ok, pdf_path (empty on failure), human-readable message
    finished = pyqtSignal(bool, str, str)
    # raw engine stdout/stderr lines as they arrive (UI may log them)
    output = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._build_dir: Path | None = None
        self._source: Path | None = None
        self._engine: str = ""
        self._pdf_path: str = ""
        self._log_tail: list[str] = []

    # ------------------------------------------------------------ public --

    def is_running(self) -> bool:
        p = self._proc
        return p is not None and p.state() != QProcess.ProcessState.NotRunning

    def pdf_path(self) -> str:
        return self._pdf_path

    def engine(self) -> str:
        return self._engine

    def compile(self, source: str, preferred_engine: str | None = None) -> bool:
        """Kick off a compile. Returns False immediately on dispatch error
        (no engine on PATH, file missing). The actual outcome arrives via
        the `finished` signal.
        """
        if self.is_running():
            self.cancel()
        src = Path(source)
        if not src.is_file():
            self.finished.emit(False, "", f"Source file not found: {source}")
            return False
        # Auto-detect xelatex requirement when the caller didn't specify.
        if preferred_engine is None:
            try:
                head = src.read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                head = ""
            if needs_unicode_engine(head):
                # Prefer xelatex; fall back to lualatex; latexmk is fine if
                # we pass it the right driver flag below.
                for cand in ("xelatex", "lualatex", "latexmk"):
                    if shutil.which(cand):
                        preferred_engine = cand
                        break

        picked = pick_engine(preferred_engine)
        if picked is None:
            self.finished.emit(
                False, "",
                "No LaTeX engine on PATH. Install MacTeX / TeX Live / MiKTeX, "
                "or add latexmk / pdflatex / xelatex / lualatex to your PATH.",
            )
            return False
        engine, base_argv = picked[0], list(picked[1])
        # If we landed on latexmk for a doc that needs a unicode engine,
        # tell latexmk to drive xelatex instead of the default pdflatex.
        if engine == "latexmk":
            try:
                head2 = src.read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                head2 = ""
            if needs_unicode_engine(head2):
                base_argv = ["-xelatex"] + [a for a in base_argv if a != "-pdf"]
        self._engine = engine
        self._source = src
        self._pdf_path = ""
        self._log_tail = []

        # Fresh build dir per compile so aux from a different .tex doesn't
        # leak in. Kept on disk so the viewer can read the output PDF.
        self._cleanup_build_dir()
        self._build_dir = Path(tempfile.mkdtemp(prefix="textview_latex_"))
        # Copy source into the build dir so engines that write next to the
        # source don't pollute the user's folder. Also copy sibling assets
        # the document might \input — limited to the parent dir, 1 level deep.
        try:
            shutil.copy2(src, self._build_dir / src.name)
            self._copy_local_assets(src.parent, self._build_dir)
        except OSError as e:
            self.finished.emit(False, "", f"Could not prepare build dir: {e}")
            return False

        argv = list(base_argv)
        if engine == "latexmk":
            argv += [f"-output-directory={self._build_dir}", src.name]
            cwd = str(self._build_dir)
        else:
            argv += ["-output-directory=.", src.name]
            cwd = str(self._build_dir)

        self._proc = QProcess(self)
        self._proc.setProgram(engine)
        self._proc.setArguments(argv)
        self._proc.setWorkingDirectory(cwd)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._proc.start()
        return True

    def cancel(self):
        if self._proc is not None and self.is_running():
            self._proc.kill()
            self._proc.waitForFinished(2000)

    def clear(self):
        self.cancel()
        self._cleanup_build_dir()
        self._source = None
        self._pdf_path = ""
        self._engine = ""
        self._log_tail = []

    # ----------------------------------------------------------- internal --

    def _copy_local_assets(self, src_dir: Path, dst_dir: Path, *, max_files: int = 64):
        """Copy small adjacent files (images, .bib, .cls, .sty) so the
        compile in the temp dir can resolve `\\input` / `\\includegraphics`
        for self-contained documents. Hard-capped to avoid copying gigabytes."""
        EXTS = {".bib", ".cls", ".sty", ".tex", ".png", ".jpg", ".jpeg",
                ".pdf", ".eps", ".svg", ".gif"}
        SIZE_CAP = 20 * 1024 * 1024  # 20 MB per asset
        count = 0
        try:
            for child in src_dir.iterdir():
                if count >= max_files: break
                if not child.is_file(): continue
                if child.suffix.lower() not in EXTS: continue
                try:
                    if child.stat().st_size > SIZE_CAP: continue
                    dst = dst_dir / child.name
                    if not dst.exists():
                        shutil.copy2(child, dst)
                        count += 1
                except OSError:
                    continue
        except OSError:
            return

    def _on_output(self):
        if self._proc is None: return
        try:
            data = bytes(self._proc.readAllStandardOutput()).decode(
                "utf-8", errors="replace")
        except Exception:
            return
        # Keep the last ~120 lines of the log so we can show the user
        # the relevant error context even though we don't expose the
        # full output anywhere yet.
        for line in data.splitlines():
            self._log_tail.append(line)
            if len(self._log_tail) > 200:
                self._log_tail.pop(0)
        self.output.emit(data)

    def _on_error(self, _err):
        # errorOccurred fires for things like FailedToStart — finished may
        # still fire afterwards; we just stash the message for the user.
        pass

    def _on_finished(self, exit_code: int, _exit_status):
        bd = self._build_dir
        src = self._source
        if bd is None or src is None:
            self.finished.emit(False, "", "Internal error: no build state.")
            return
        pdf = bd / (src.stem + ".pdf")
        if exit_code == 0 and pdf.is_file():
            self._pdf_path = str(pdf)
            self.finished.emit(True, str(pdf), f"Compiled with {self._engine}.")
            return
        # Failure: surface a useful tail of the engine log.
        snippet = self._error_snippet()
        msg = f"{self._engine} exited with code {exit_code}."
        if snippet:
            msg = f"{msg}\n\n{snippet}"
        self.finished.emit(False, "", msg)

    def _error_snippet(self) -> str:
        """Pull the most-recent error lines from the engine log tail.

        LaTeX errors usually start with `!` or include `:line:` (with
        `-file-line-error`). We grab the last few of those plus a couple
        of trailing lines for context.
        """
        if not self._log_tail:
            return ""
        marked = [i for i, ln in enumerate(self._log_tail)
                  if ln.startswith("!") or ":" in ln and ".tex:" in ln]
        if not marked:
            return "\n".join(self._log_tail[-12:])
        # Take a window around the first error marker.
        start = max(0, marked[0] - 2)
        end = min(len(self._log_tail), marked[0] + 10)
        return "\n".join(self._log_tail[start:end])

    def _cleanup_build_dir(self):
        bd = self._build_dir
        self._build_dir = None
        if bd is not None and bd.exists():
            try:
                shutil.rmtree(bd, ignore_errors=True)
            except OSError:
                pass


# ---------------------------------------------------------------- MainWindow glue --

def compile_active_buffer(window) -> None:
    """Persist any pending edits, then dispatch the active `.tex` to
    `window._latex`. No-op (with a status-bar hint) if the current
    format isn't `latex` or no file is open. Kept here rather than on
    `MainWindow` so `app.py` stays small."""
    from pathlib import Path as _P
    from PyQt6.QtWidgets import QMessageBox  # noqa: F401 — used by sibling fn
    if window._current_format != "latex" or not window._current_path:
        window.statusBar().showMessage("Compile LaTeX: no .tex file is open.", 5000)
        return
    if window.edit.editing and window.edit.modified:
        window._sync_content()
        try:
            _P(window._current_path).write_text(
                window._current_content,
                encoding=window._current_encoding or "utf-8")
            window.edit.modified = False
            window.edit.state_changed.emit()
        except OSError as e:
            window.statusBar().showMessage(
                f"Could not save before compile: {e}", 6000)
            return
    if window._latex.is_running():
        window.statusBar().showMessage("LaTeX already compiling…", 3000)
        return
    if window._latex.compile(window._current_path):
        window.statusBar().showMessage(
            f"Compiling LaTeX with {window._latex.engine() or '…'}", 0)


def apply_compiled_pdf(window, ok: bool, pdf_path: str, message: str) -> None:
    """Handle `LatexController.finished`. On success, route the produced
    PDF through `PdfController` + show the PDF view; on failure, surface
    the engine log tail in a warning dialog."""
    from PyQt6.QtWidgets import QMessageBox
    if not ok:
        window.statusBar().clearMessage()
        QMessageBox.warning(window, "LaTeX compile failed",
                            message or "Unknown error.")
        return
    d = window.settings_manager.display
    if not window._pdf.load(pdf_path):
        QMessageBox.warning(window, "LaTeX",
                            "Compile succeeded but the PDF could not be opened.")
        return
    window._pdf.attach(window.viewer.pdf_view,
                      d.pdf_page_mode, d.pdf_zoom_mode, d.pdf_zoom)
    window.viewer.show_pdf()
    window.statusBar().showMessage(message, 5000)
