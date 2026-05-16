"""播放一次完整的 phased 动画，主要用于plugins"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject

from core.animation import FlipbookPlayer, Mode


class PhasedPlayer(QObject):
    """把一个phased播成start然后loopN次最后end"""

    def __init__(self, parent: QObject | None, window) -> None:
        super().__init__(parent)
        self._window = window
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)
        self._player.finished.connect(self._on_clip_finished)
        self._mode: Mode | None = None
        self._loop_left = 0
        self._phase = "idle"
        self._paused = False
        self._on_finished: Callable[[], None] | None = None

    def is_active(self) -> bool:
        return self._phase != "idle"

    def is_paused(self) -> bool:
        return self._paused

    def play(
        self,
        mode: Mode,
        loop_count: int,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        if self.is_active() or not mode.is_phased or mode.start is None or mode.end is None:
            return False
        self._mode = mode
        self._loop_left = max(1, int(loop_count))
        self._phase = "start"
        self._paused = False
        self._on_finished = on_finished
        self._player.play(mode.start, loop=False)
        return True

    def pause(self) -> bool:
        if not self.is_active() or self._paused:
            return False
        self._paused = True
        self._player.stop()
        return True

    def resume(self) -> bool:
        if not self.is_active() or not self._paused:
            return False
        self._paused = False
        self._play_current_phase()
        return True

    def stop(self) -> None:
        self._player.stop()
        self._mode = None
        self._loop_left = 0
        self._phase = "idle"
        self._paused = False
        self._on_finished = None

    def _play_current_phase(self) -> None:
        if self._mode is None:
            self.stop()
            return
        if self._phase == "start" and self._mode.start is not None:
            self._player.play(self._mode.start, loop=False)
            return
        if self._phase == "loop":
            self._player.play(self._mode.loop, loop=False)
            return
        if self._phase == "end" and self._mode.end is not None:
            self._player.play(self._mode.end, loop=False)
            return
        self.stop()

    def _on_clip_finished(self) -> None:
        if self._paused:
            return
        if self._mode is None:
            self.stop()
            return
        if self._phase == "start":
            self._phase = "loop"
            self._player.play(self._mode.loop, loop=False)
            return
        if self._phase == "loop":
            self._loop_left -= 1
            if self._loop_left > 0:
                self._player.play(self._mode.loop, loop=False)
                return
            self._phase = "end"
            self._player.play(self._mode.end, loop=False)
            return
        if self._phase == "end":
            on_finished = self._on_finished
            self.stop()
            if on_finished is not None:
                on_finished()
