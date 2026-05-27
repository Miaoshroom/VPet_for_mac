"""通用 start-loop-end 播放状态机"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from core.playback.clip import Mode
from core.playback.flipbook import FlipbookPlayer


class PhasedSequencePlayer(QObject):
    """按 start -> loop -> end 播放分段 Mode"""

    frame_changed = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self.frame_changed)
        self._player.finished.connect(self._on_clip_finished)
        self._mode: Mode | None = None
        self._loop_left = 0
        self._loop_forever = False
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
        loop_count: int = 1,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        if not self._start(mode, on_finished):
            return False
        self._loop_left = max(1, int(loop_count))
        self._loop_forever = False
        assert mode.start is not None
        self._player.play(mode.start, loop=False)
        return True

    def play_forever(
        self,
        mode: Mode,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        if not self._start(mode, on_finished):
            return False
        self._loop_left = 0
        self._loop_forever = True
        assert mode.start is not None
        self._player.play(mode.start, loop=False)
        return True

    def finish(self) -> bool:
        if not self.is_active() or self._mode is None:
            return False
        if self._phase == "end":
            return True
        self._loop_left = 0
        self._loop_forever = False
        self._phase = "end"
        if not self._paused:
            assert self._mode.end is not None
            self._player.play(self._mode.end, loop=False)
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
        self._loop_forever = False
        self._phase = "idle"
        self._paused = False
        self._on_finished = None

    def _start(self, mode: Mode, on_finished: Callable[[], None] | None) -> bool:
        if self.is_active() or not mode.is_phased or mode.start is None or mode.end is None:
            return False
        self._mode = mode
        self._phase = "start"
        self._paused = False
        self._on_finished = on_finished
        return True

    def _play_current_phase(self) -> None:
        if self._mode is None:
            self.stop()
            return
        if self._phase == "start":
            assert self._mode.start is not None
            self._player.play(self._mode.start, loop=False)
            return
        if self._phase == "loop":
            self._player.play(self._mode.loop, loop=False)
            return
        if self._phase == "end":
            assert self._mode.end is not None
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
            if self._loop_forever:
                self._player.play(self._mode.loop, loop=False)
                return
            self._loop_left -= 1
            if self._loop_left > 0:
                self._player.play(self._mode.loop, loop=False)
                return
            self._phase = "end"
            assert self._mode.end is not None
            self._player.play(self._mode.end, loop=False)
            return
        if self._phase == "end":
            on_finished = self._on_finished
            self.stop()
            self.finished.emit()
            if on_finished is not None:
                on_finished()
