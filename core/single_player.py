"""播放一次 single 动画并恢复当前 mode。"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject

from core.animation import Clip, FlipbookPlayer, PetAnimationDirector


class SinglePlayer(QObject):
    def __init__(self, parent: QObject, director: PetAnimationDirector, window) -> None:
        super().__init__(parent)
        self._director = director
        self._window = window
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)
        self._player.finished.connect(self._finish)
        self._resume_mode: str | None = None
        self._on_finished: Callable[[], None] | None = None
        self._active = False

    def is_active(self) -> bool:
        return self._active

    def play(
        self,
        clip: Clip,
        on_finished: Callable[[], None] | None = None,
        *,
        resume: bool = True, # 专门给启动和退出动画用的x
    ) -> bool:
        if self._active:
            return False
        self._active = True
        self._resume_mode = self._director.current_mode_name() if resume else None
        self._on_finished = on_finished
        self._window.setEnabled(False)
        self._director.stop()
        self._player.play(clip, loop=False)
        return True

    def stop(self) -> None:
        self._player.stop()
        self._active = False
        self._resume_mode = None
        self._on_finished = None
        self._window.setEnabled(True)

    def _finish(self) -> None:
        resume_mode = self._resume_mode
        on_finished = self._on_finished
        self._active = False
        self._resume_mode = None
        self._on_finished = None
        self._window.setEnabled(True)
        if resume_mode is not None:
            self._director.resume_mode(resume_mode)
        if on_finished is not None:
            on_finished()
