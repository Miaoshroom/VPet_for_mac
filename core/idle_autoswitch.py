"""自动切换待机动作"""

from __future__ import annotations

from random import choice

from PyQt6.QtCore import QObject, QTimer

from core.animation import PetAnimationDirector


def start_auto_idle_timer(
    parent: QObject,
    director: PetAnimationDirector,
    interval_ms: int,
    mode_ids: tuple[str, ...],
) -> QTimer | None:
    if interval_ms <= 0 or not mode_ids:
        return None

    timer = QTimer(parent)
    timer.setInterval(interval_ms)

    def switch_auto_idle() -> None:
        if director.is_press_active():
            return
        current_mode = director.current_mode_name()
        if current_mode not in mode_ids:
            return
        candidates = [mode_id for mode_id in mode_ids if mode_id != current_mode]
        if not candidates:
            return
        director.switch_mode(choice(candidates))

    timer.timeout.connect(switch_auto_idle)
    timer.start()
    return timer
