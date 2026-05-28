"""随机插播 single 动画。"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Protocol

from PyQt6.QtCore import QObject, QTimer

from core.animation import Clip, PetAnimationDirector
from core.playback.catalog import AnimationCatalog
from core.single_player import SinglePlayer


class StartStop(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class SingleAutoSwitch(QObject):
    def __init__(
        self,
        parent: QObject,
        director: PetAnimationDirector,
        interval_min_ms: int,
        interval_max_ms: int,
        mode_ids: tuple[str, ...],
        action_blocked: Callable[[], bool],
        single_player: SinglePlayer,
        animation_catalog: AnimationCatalog,
        mode_autoswitch_timer: StartStop | None = None,
    ) -> None:
        super().__init__(parent)
        self._director = director
        self._interval_min_ms = interval_min_ms
        self._interval_max_ms = interval_max_ms
        self._mode_ids = mode_ids
        self._action_blocked = action_blocked
        self._single_player = single_player
        self._animation_catalog = animation_catalog
        self._mode_autoswitch_timer = mode_autoswitch_timer
        self._timer: QTimer | None = None

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
        self._single_player.stop()

    def is_active(self) -> bool:
        return self._single_player.is_active()

    def _pick_clip(self) -> Clip | None:
        if not self._mode_ids:
            return None

        # single 插播也跟着当前状态走 没素材就不插播
        pet_state = self._director.pet_state()
        candidates = [
            mode_id
            for mode_id in self._mode_ids
            if self._animation_catalog.is_single_available(mode_id, pet_state)
        ]
        if not candidates:
            return None
        return self._animation_catalog.single_for(random.choice(candidates), pet_state)

    def _reset_interval(self) -> None:
        if self._timer is None:
            return
        self._timer.setInterval(random.randint(self._interval_min_ms, self._interval_max_ms))

    def _maybe_play(self) -> None:
        if self._single_player.is_active():
            self._reset_interval()
            return
        if self._action_blocked() or self._director.is_interaction_active():
            self._reset_interval()
            return
        clip = self._pick_clip()
        if clip is None:
            self._reset_interval()
            return

        if self._timer is not None:
            self._timer.stop()
        if self._mode_autoswitch_timer is not None:
            self._mode_autoswitch_timer.stop()
        if not self._single_player.play(clip, on_finished=self._finish):
            self._finish()

    def _finish(self) -> None:
        if self._mode_autoswitch_timer is not None:
            self._mode_autoswitch_timer.start()
        if self._timer is not None:
            self._reset_interval()
            self._timer.start()
