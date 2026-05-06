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
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel,
    QSizePolicy,
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

        self.surface = QVideoWidget(self)
        self.surface.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self.surface.setStyleSheet("background:#000;")
        layout.addWidget(self.surface, 1)

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

        # Player + audio.
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.surface)
        self.audio.setVolume(0.8)

        # Wire signals.
        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.s_vol.valueChanged.connect(self._on_volume)

        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.sliderMoved.connect(self._slider_moved)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)

    # -- public API ----------------------------------------------------------

    def load(self, path: str) -> bool:
        try:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            return True
        except Exception as e:
            self.errored.emit(str(e))
            return False

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self):
        self.player.stop()

    def set_position(self, ms: int):
        self.player.setPosition(int(ms))

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def teardown(self):
        """Release the source so a tab close doesn't leak an active decoder."""
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
        self.player.setPosition(self.slider.value())

    def _slider_moved(self, v: int):
        # Live scrub — also updates label so the user sees the destination.
        self.lbl_pos.setText(_fmt_ms(v))
        self.player.setPosition(v)

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
        self.audio.setVolume(v / 100.0)
        if v == 0:
            self.btn_mute.setText("🔇")
        elif self.audio.isMuted():
            self.audio.setMuted(False)
            self.btn_mute.setText("🔊")

    def _toggle_mute(self):
        muted = not self.audio.isMuted()
        self.audio.setMuted(muted)
        self.btn_mute.setText("🔇" if muted else "🔊")
