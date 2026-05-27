"""逐帧播放单个动画片段"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal

from core.playback.clip import Clip


class FlipbookPlayer(QObject):
    """单个 Clip 的定时播放器"""

    frame_changed = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_tick)
        self._clip: Clip | None = None
        self._index = 0
        self._loop = False

    def is_playing(self) -> bool:
        return self._clip is not None and self._timer.isActive()

    def disconnect_finished(self) -> None:
        try:
            self.finished.disconnect()
        except TypeError:
            pass

    def stop(self) -> None:
        self._timer.stop()
        self._clip = None
        self._index = 0

    def play(self, clip: Clip, *, loop: bool) -> None:
        self.stop()
        self._clip = clip
        self._loop = loop
        self._index = 0
        self._emit_current_frame()

    def _emit_current_frame(self) -> None:
        if self._clip is None:
            return
        self.frame_changed.emit(self._clip.frame(self._index))
        self._timer.start(self._clip.interval_for(self._index))

    def _on_tick(self) -> None:
        if self._clip is None:
            return
        self._index += 1
        if self._index >= len(self._clip):
            if not self._loop:
                self.stop()
                self.finished.emit()
                return
            self._index = 0
        self._emit_current_frame()
