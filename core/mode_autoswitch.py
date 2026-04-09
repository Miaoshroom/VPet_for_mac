"""自动切换 mode。"""

from __future__ import annotations

from random import choice, randint

from PyQt6.QtCore import QObject, QTimer

from core.animation import PetAnimationDirector


def start_mode_autoswitch_timer(
    parent: QObject,
    director: PetAnimationDirector,
    interval_min_ms: int,
    interval_max_ms: int,
    mode_ids: tuple[str, ...],
) -> QTimer | None:
    if interval_max_ms <= 0 or not mode_ids:
        return None

    timer = QTimer(parent)

    def reset_interval() -> None:
        timer.setInterval(randint(interval_min_ms, interval_max_ms))

    def switch_mode_auto() -> None:
        reset_interval()
        if director.is_press_active():
            return
        current_mode = director.current_mode_name()
        if current_mode not in mode_ids:
            return
        candidates = [mode_id for mode_id in mode_ids if mode_id != current_mode]
        if not candidates:
            return
        director.switch_mode(choice(candidates))

    timer.timeout.connect(switch_mode_auto)
    reset_interval()
    timer.start()
    return timer
