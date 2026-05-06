"""Minimal ANSI SGR escape parser → QTextCharFormat.

Handles the subset of escapes that real CLI tools actually emit on a
non-cursor-addressable terminal: 16 base colors, bold/dim/italic/
underline/strike, reset. Keeps a `Style` cursor across calls so a
sequence split across two reads (`\\x1b[3` … `1m`) still works.

Out of scope here (intentionally): cursor-positioning escapes
(`\\x1b[H`, `\\x1b[2J`, etc.). For those we need a full PTY emulator —
Phase 2.
"""
import re
from dataclasses import dataclass, replace, field

from PyQt6.QtGui import QTextCharFormat, QColor, QFont


# Standard 16-color palette. Maps SGR code → CSS-ish hex.
_FG = {
    30: "#000000", 31: "#cd0000", 32: "#00cd00", 33: "#cdcd00",
    34: "#0000ee", 35: "#cd00cd", 36: "#00cdcd", 37: "#e5e5e5",
    90: "#7f7f7f", 91: "#ff0000", 92: "#00ff00", 93: "#ffff00",
    94: "#5c5cff", 95: "#ff00ff", 96: "#00ffff", 97: "#ffffff",
}
_BG = {k + 10: v for k, v in _FG.items()}  # 40–47, 100–107


@dataclass
class Style:
    fg: str | None = None
    bg: str | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False

    def to_format(self) -> QTextCharFormat:
        f = QTextCharFormat()
        if self.fg:
            f.setForeground(QColor(self.fg))
        if self.bg:
            f.setBackground(QColor(self.bg))
        if self.bold:
            f.setFontWeight(QFont.Weight.Bold)
        if self.italic:
            f.setFontItalic(True)
        if self.underline:
            f.setFontUnderline(True)
        if self.strike:
            f.setFontStrikeOut(True)
        return f


_SGR_RE = re.compile(r"\x1b\[([\d;]*)m")
_OTHER_CSI = re.compile(r"\x1b\[[\d;?]*[A-Za-z]")  # any other CSI we'll just drop


class AnsiParser:
    """Stateful parser. Call `feed(text)` repeatedly; iterate yielded chunks."""

    def __init__(self):
        self.style = Style()
        self._pending = ""

    def feed(self, text: str):
        """Yield (chunk, format) tuples for the given chunk of text."""
        # Prepend any half-escape that arrived last time.
        text = self._pending + text
        self._pending = ""

        # If text ends mid-CSI, hold it back until we see the terminator.
        # Cheap heuristic: if there's an ESC without a following alphabetic
        # terminator, defer everything from the ESC.
        last_esc = text.rfind("\x1b[")
        if last_esc >= 0 and not re.search(r"[A-Za-z]", text[last_esc:]):
            self._pending = text[last_esc:]
            text = text[:last_esc]
            if not text:
                return

        # Strip non-SGR CSI escapes (we don't render cursor moves yet) but
        # only for now — pass content through.
        text = _OTHER_CSI.sub(lambda m: "" if not m.group(0).endswith("m") else m.group(0), text)

        pos = 0
        for m in _SGR_RE.finditer(text):
            if m.start() > pos:
                yield text[pos:m.start()], self.style.to_format()
            self._apply(m.group(1))
            pos = m.end()
        if pos < len(text):
            yield text[pos:], self.style.to_format()

    def _apply(self, codes: str):
        if not codes:
            codes = "0"
        nums = []
        for c in codes.split(";"):
            try:
                nums.append(int(c))
            except ValueError:
                pass

        i = 0
        s = self.style
        while i < len(nums):
            n = nums[i]
            if n == 0:
                self.style = Style()
                s = self.style
            elif n == 1:
                s.bold = True
            elif n == 2:
                s.dim = True
            elif n == 3:
                s.italic = True
            elif n == 4:
                s.underline = True
            elif n == 9:
                s.strike = True
            elif n == 22:
                s.bold = False; s.dim = False
            elif n == 23:
                s.italic = False
            elif n == 24:
                s.underline = False
            elif n == 29:
                s.strike = False
            elif n in _FG:
                s.fg = _FG[n]
            elif n in _BG:
                s.bg = _BG[n]
            elif n == 39:
                s.fg = None
            elif n == 49:
                s.bg = None
            elif n == 38 and i + 4 < len(nums) and nums[i + 1] == 2:
                s.fg = f"#{nums[i + 2]:02x}{nums[i + 3]:02x}{nums[i + 4]:02x}"
                i += 4
            elif n == 48 and i + 4 < len(nums) and nums[i + 1] == 2:
                s.bg = f"#{nums[i + 2]:02x}{nums[i + 3]:02x}{nums[i + 4]:02x}"
                i += 4
            i += 1
