"""绑定窗口的分段播放兼容壳"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject

from core.animation import Mode, PhasedSequencePlayer


class PhasedPlayer(QObject):
    """将一个分段 Mode 播放到窗口 pixmap"""

    def __init__(self, parent: QObject | None, window) -> None:
        super().__init__(parent)
        self._player = PhasedSequencePlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)

    def is_active(self) -> bool:
        return self._player.is_active()

    def is_paused(self) -> bool:
        return self._player.is_paused()

    def play(
        self,
        mode: Mode,
        loop_count: int,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        return self._player.play(mode, loop_count, on_finished)

    def play_forever(
        self,
        mode: Mode,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        return self._player.play_forever(mode, on_finished)

    def finish(self) -> bool:
        return self._player.finish()

    def pause(self) -> bool:
        return self._player.pause()

    def resume(self) -> bool:
        return self._player.resume()

    def stop(self) -> None:
        self._player.stop()
