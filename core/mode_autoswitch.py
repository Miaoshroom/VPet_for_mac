"""自动切换 mode。"""

from __future__ import annotations

from random import choice, randint

from PyQt6.QtCore import QObject, QTimer

from core.animation import PetAnimationDirector


class ModeAutoSwitch(QObject):
    def __init__(
        self,
        parent: QObject,
        director: PetAnimationDirector,
        interval_min_ms: int,
        interval_max_ms: int,
        mode_ids: tuple[str, ...],
    ) -> None:
        super().__init__(parent)
        self._director = director
        self._interval_min_ms = interval_min_ms
        self._interval_max_ms = interval_max_ms
        self._mode_ids = mode_ids
        self._enabled = interval_max_ms > 0 and bool(mode_ids)
        self._timer: QTimer | None = None

        if self._enabled:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._switch_mode_auto)
            self.start()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled) and self._interval_max_ms > 0 and bool(self._mode_ids)
        if self._enabled:
            self.start()
        else:
            self.stop()

    def isActive(self) -> bool:
        return self._timer is not None and self._timer.isActive()

    def start(self) -> None:
        if not self._enabled or self._timer is None:
            return
        self._reset_interval()
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def _reset_interval(self) -> None:
        if self._timer is not None:
            self._timer.setInterval(randint(self._interval_min_ms, self._interval_max_ms))

    def _switch_mode_auto(self) -> None:
        self._reset_interval()
        if self._director.is_press_active():
            return
        current_mode = self._director.current_mode_name()
        if current_mode not in self._mode_ids:
            return
        candidates = [mode_id for mode_id in self._mode_ids if mode_id != current_mode]
        if not candidates:
            return
        self._director.switch_mode(choice(candidates))
