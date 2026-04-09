"""自动插播 single 动画。"""

from __future__ import annotations

import random
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from core.animation import Clip, FlipbookPlayer, PetAnimationDirector


class SingleAutoSwitch(QObject):
    def __init__(
        self,
        parent: QObject,
        director: PetAnimationDirector,
        window,
        interval_min_ms: int,
        interval_max_ms: int,
        mode_ids: tuple[str, ...],
        single_clips: dict[str, Clip],
        music_dance_enabled: Callable[[], bool],
        mode_autoswitch_timer: QTimer | None = None,
    ) -> None:
        super().__init__(parent)
        self._director = director
        self._window = window
        self._interval_min_ms = interval_min_ms
        self._interval_max_ms = interval_max_ms
        self._mode_ids = mode_ids
        self._single_clips = single_clips
        self._music_dance_enabled = music_dance_enabled
        self._mode_autoswitch_timer = mode_autoswitch_timer
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)
        self._player.finished.connect(self._finish)
        self._timer: QTimer | None = None
        self._resume_mode: str | None = None
        self._active = False

        if interval_max_ms > 0 and mode_ids:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._maybe_play)

    def start(self) -> None:
        if self._timer is None or self._timer.isActive():
            return
        self._reset_interval()
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._player.stop()
        self._active = False
        self._resume_mode = None

    def is_active(self) -> bool:
        return self._active

    def _pick_clip(self) -> Clip | None:
        if not self._mode_ids:
            return None
        return self._single_clips[random.choice(self._mode_ids)]

    def _reset_interval(self) -> None:
        if self._timer is None:
            return
        self._timer.setInterval(random.randint(self._interval_min_ms, self._interval_max_ms))

    def _maybe_play(self) -> None:
        if self._active:
            self._reset_interval()
            return
        if self._music_dance_enabled() or self._director.is_interaction_active():
            self._reset_interval()
            return
        clip = self._pick_clip()
        if clip is None:
            self._reset_interval()
            return

        self._active = True
        self._resume_mode = self._director.current_mode_name()
        if self._timer is not None:
            self._timer.stop()
        if self._mode_autoswitch_timer is not None:
            self._mode_autoswitch_timer.stop()
        self._window.setEnabled(False)
        self._director.stop()
        self._player.play(clip, loop=False)

    def _finish(self) -> None:
        resume_mode = self._resume_mode
        self._active = False
        self._resume_mode = None
        self._window.setEnabled(True)
        if resume_mode is not None:
            self._director.resume_mode(resume_mode)
        if self._mode_autoswitch_timer is not None:
            self._mode_autoswitch_timer.start()
        if self._timer is not None:
            self._reset_interval()
            self._timer.start()
