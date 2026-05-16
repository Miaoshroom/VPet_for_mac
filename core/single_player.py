"""播放一次 single 动画并恢复当前 mode。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject

from core.animation import Clip, FlipbookPlayer, PetAnimationDirector


@dataclass
class _SingleRun:
    clip: Clip
    resume_mode: str | None
    on_finished: Callable[[], None] | None
    interruptible: bool


class SinglePlayer(QObject):
    def __init__(self, parent: QObject, director: PetAnimationDirector, window) -> None:
        super().__init__(parent)
        self._director = director
        self._window = window
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)
        self._player.finished.connect(self._finish)
        self._current: _SingleRun | None = None
        self._paused: _SingleRun | None = None

    def is_active(self) -> bool:
        return self._current is not None

    def is_paused(self) -> bool:
        return self._paused is not None

    def blocks_interaction(self) -> bool:
        return self._current is not None and not self._current.interruptible

    def play(
        self,
        clip: Clip,
        on_finished: Callable[[], None] | None = None,
        *,
        resume: bool = True,  # 专门给启动和退出动画用的
        interruptible: bool = False,
    ) -> bool:
        if self._current is not None:
            return False
        resume_mode = self._director.current_mode_name() if resume else None
        self._current = _SingleRun(clip, resume_mode, on_finished, interruptible)
        self._director.stop()
        self._player.play(clip, loop=False)
        return True

    def pause(self) -> bool:
        if self._current is None or not self._current.interruptible:
            return False
        self._paused = self._current
        self._current = None
        self._player.stop()
        return True

    def resume(self) -> bool:
        if self._current is not None or self._paused is None:
            return False
        self._current = self._paused
        self._paused = None
        self._director.stop()
        self._player.play(self._current.clip, loop=False)
        return True

    def stop(self) -> None:
        self._player.stop()
        self._current = None
        self._paused = None

    def _finish(self) -> None:
        current = self._current
        if current is None:
            return
        self._current = None
        if current.resume_mode is not None:
            self._director.resume_mode(current.resume_mode)
        if current.on_finished is not None:
            current.on_finished()
