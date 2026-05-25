"""Video playback widget.

Wraps `QMediaPlayer` + `QAudioOutput` + `QVideoWidget` with a transport
bar (play/pause, stop, time slider with current/total time labels, mute
+ volume slider). One `VideoView` instance lives in `TextViewer`'s stack
(`MODE_VIDEO`).

The slider is two-way:
  - `QMediaPlayer.positionChanged` → slider value (when not being dragged)
  - User drag (`sliderPressed/Moved/Released`) → `setPosition`

Supported codecs depend on what the host's Qt build can decode (Qt 6.5+
uses FFmpeg by default, so most common formats work; on older Mac builds
it falls back to AVFoundation).
"""
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel,
    QSizePolicy, QStackedWidget,
)


def _fmt_ms(ms: int) -> str:
    """Render milliseconds as MM:SS or H:MM:SS for long videos."""
    if ms is None or ms < 0:
        ms = 0
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class VideoView(QWidget):
    """Embedded video player with a transport bar. Emits `errored(str)` on
    decoder/load errors so the host window can surface a status message."""

    errored = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked area: the video surface for movies, a "now playing" label
        # for audio-only files. `set_audio_mode(True, name)` flips to the
        # label so .mp3 / .flac etc. don't render as a giant black box.
        self._stack = QStackedWidget(self)
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        self.surface = QVideoWidget(self._stack)
        # Video surface stays black — the video frame is whatever the
        # decoder writes, and themed bg would just be invisible behind it.
        self.surface.setStyleSheet("background:#000;")
        self._audio_panel = QWidget(self._stack)
        # Default styling — the host calls `apply_theme(theme)` whenever
        # the active theme changes so these colours track the rest of
        # the app instead of being hardcoded dark.
        ap_layout = QVBoxLayout(self._audio_panel)
        ap_layout.setContentsMargins(40, 40, 40, 40); ap_layout.setSpacing(12)
        self._audio_icon = QLabel("♪", self._audio_panel)
        self._audio_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._audio_name = QLabel("(no audio loaded)", self._audio_panel)
        self._audio_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._audio_name.setWordWrap(True)
        ap_layout.addStretch(1)
        ap_layout.addWidget(self._audio_icon, 0)
        ap_layout.addWidget(self._audio_name, 0)
        ap_layout.addStretch(1)
        self._stack.addWidget(self.surface)
        self._stack.addWidget(self._audio_panel)
        layout.addWidget(self._stack, 1)
        self._audio_mode = False
        # Sensible default until `apply_theme` is invoked.
        self.apply_theme({"bg": "#1e1e1e", "fg": "#eee",
                          "line_number_fg": "#888"})

        # Transport bar.
        bar = QWidget(self)
        bar.setStyleSheet("background: palette(window);")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)

        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedWidth(32)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedWidth(32)

        self.lbl_pos = QLabel("00:00"); self.lbl_pos.setMinimumWidth(48)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.lbl_dur = QLabel("00:00"); self.lbl_dur.setMinimumWidth(48)

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setFixedWidth(32)
        self.s_vol = QSlider(Qt.Orientation.Horizontal)
        self.s_vol.setRange(0, 100); self.s_vol.setValue(80)
        self.s_vol.setFixedWidth(80)

        for w in (self.btn_play, self.btn_stop, self.lbl_pos):
            h.addWidget(w)
        h.addWidget(self.slider, 1)
        for w in (self.lbl_dur, self.btn_mute, self.s_vol):
            h.addWidget(w)
        layout.addWidget(bar, 0)

        # Player + audio are built lazily on the first `load()`. macOS
        # Core Audio device enumeration emits a flurry of "audio device
        # has unrecognized channel" messages on QAudioOutput construction,
        # so we defer that until the user actually opens a video.
        self.player: QMediaPlayer | None = None
        self.audio: QAudioOutput | None = None

        # Transport-bar wiring (no player needed).
        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.s_vol.valueChanged.connect(self._on_volume)

        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.sliderMoved.connect(self._slider_moved)

    def _ensure_player(self):
        """Construct the QMediaPlayer + QAudioOutput on demand and wire
        their signals. Idempotent."""
        if self.player is not None: return
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        # metaDataChanged fires once the decoder has parsed embedded
        # ID3 / Vorbis / MP4 tags — pipe the result into the audio panel.
        self.player.metaDataChanged.connect(self._on_metadata)
        self.player.setVideoOutput(self.surface)
        self.audio.setVolume(self.s_vol.value() / 100.0)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)

    # -- public API ----------------------------------------------------------

    def load(self, path: str) -> bool:
        self._ensure_player()
        try:
            from .file_loader import is_audio
            self.set_audio_mode(is_audio(path), Path(path).name)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            return True
        except Exception as e:
            self.errored.emit(str(e))
            return False

    def apply_theme(self, theme: dict) -> None:
        """Push the active theme onto the audio-only panel. Called by
        `view_styler.apply_theme` so the `♪ filename` overlay matches
        the rest of the app instead of using hardcoded dark colours."""
        bg = theme.get("bg", "#1e1e1e")
        fg = theme.get("fg", "#eee")
        muted = theme.get("line_number_fg", "#888")
        # Use stylesheets rather than palette: the icon QLabel needs
        # its own colour for the big ♪, and labels inside a styled
        # parent don't inherit palette across themes reliably.
        self._audio_panel.setStyleSheet(
            f"background:{bg}; color:{fg}; font-size:14pt;")
        self._audio_icon.setStyleSheet(
            f"font-size:80pt; color:{muted};")
        # The metadata label rebuilds its HTML on metaDataChanged using
        # whatever colours are set; keep its parent's color so a fresh
        # label inherits the theme'd foreground.
        self._audio_name.setStyleSheet(f"color:{fg};")

    def set_audio_mode(self, on: bool, display_name: str = ""):
        """Flip between the video surface and the audio-only label panel.

        Called from `load()` based on the file's detected format, but exposed
        publicly so callers can force-set it (e.g. when reloading a file
        without a fresh load).
        """
        self._audio_mode = bool(on)
        self._stack.setCurrentWidget(self._audio_panel if on else self.surface)
        if on:
            self._fallback_audio_name = display_name or ""
            self._audio_name.setText(display_name or "")

    def _on_metadata(self):
        """Refresh the audio-only panel label from decoder-extracted
        metadata. Only kicks in when `set_audio_mode(True, ...)` is
        active — video files keep their black surface."""
        if not getattr(self, "_audio_mode", False) or self.player is None:
            return
        from PyQt6.QtMultimedia import QMediaMetaData
        md = self.player.metaData()
        # `value(key)` returns `None` (or empty str) when the tag isn't
        # present; only include fields we actually got.
        def _get(key):
            v = md.value(key) if md is not None else None
            return str(v).strip() if v else ""
        title = _get(QMediaMetaData.Key.Title)
        artist = _get(QMediaMetaData.Key.AlbumArtist) or _get(QMediaMetaData.Key.ContributingArtist)
        album = _get(QMediaMetaData.Key.AlbumTitle)
        year = _get(QMediaMetaData.Key.Date)
        genre = _get(QMediaMetaData.Key.Genre)
        lines: list[str] = []
        if title: lines.append(f"<b>{title}</b>")
        else: lines.append(f"<b>{getattr(self, '_fallback_audio_name', '')}</b>")
        if artist:
            line = artist
            if album: line += f" — <i>{album}</i>"
            if year:  line += f"  ({year[:4]})"
            lines.append(line)
        elif album:
            lines.append(f"<i>{album}</i>")
        if genre: lines.append(f"<span style='color:#888'>{genre}</span>")
        # Duration is on QMediaPlayer, not metaData() — pick it up here too.
        dur = self.player.duration()
        if dur > 0:
            lines.append(f"<span style='color:#888'>{_fmt_ms(dur)}</span>")
        self._audio_name.setText("<br>".join(lines))

    def play(self):
        if self.player is not None: self.player.play()

    def pause(self):
        if self.player is not None: self.player.pause()

    def toggle_play_pause(self):
        if self.player is None: return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        if self.player is not None: self.player.stop()

    def set_position(self, ms: int):
        if self.player is not None: self.player.setPosition(int(ms))

    def is_playing(self) -> bool:
        return (self.player is not None and
                self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)

    def teardown(self):
        """Release the source so a tab close doesn't leak an active decoder."""
        if self.player is None: return
        try:
            self.player.stop()
            self.player.setSource(QUrl())
        except Exception:
            pass

    # -- slider drag ---------------------------------------------------------

    def _slider_pressed(self):
        self._dragging = True

    def _slider_released(self):
        self._dragging = False
        if self.player is not None: self.player.setPosition(self.slider.value())

    def _slider_moved(self, v: int):
        # Live scrub — also updates label so the user sees the destination.
        self.lbl_pos.setText(_fmt_ms(v))
        if self.player is not None: self.player.setPosition(v)

    # -- player event handlers ----------------------------------------------

    def _on_position(self, pos: int):
        if self._dragging:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(int(pos))
        self.slider.blockSignals(False)
        self.lbl_pos.setText(_fmt_ms(pos))

    def _on_duration(self, dur: int):
        self.slider.setRange(0, int(dur))
        self.lbl_dur.setText(_fmt_ms(dur))

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setText("⏸" if playing else "▶")

    def _on_error(self, err, msg=""):
        if err and err != QMediaPlayer.Error.NoError:
            self.errored.emit(msg or str(err))

    # -- volume / mute -------------------------------------------------------

    def _on_volume(self, v: int):
        if self.audio is None: return    # value is preserved via the slider
        self.audio.setVolume(v / 100.0)
        if v == 0:
            self.btn_mute.setText("🔇")
        elif self.audio.isMuted():
            self.audio.setMuted(False)
            self.btn_mute.setText("🔊")

    def _toggle_mute(self):
        if self.audio is None: return
        muted = not self.audio.isMuted()
        self.audio.setMuted(muted)
        self.btn_mute.setText("🔇" if muted else "🔊")
