"""在线养成状态变化。

这里处理真实 PetState 数值，不驱动动画表现状态。
"""

from __future__ import annotations

from dataclasses import dataclass

from core.raising.pet_state import PetState

DEFAULT_TICK_SECONDS = 60
SATIETY_DECAY_SECONDS = 10 * 60
ENERGY_DECAY_SECONDS = 20 * 60
CLEANLINESS_DECAY_SECONDS = 15 * 60
MOOD_PRESSURE_THRESHOLD = 35
MOOD_DECAY_SECONDS = 15 * 60
HEALTH_PRESSURE_THRESHOLD = 20
HEALTH_GRACE_SECONDS = 30 * 60
HEALTH_DECAY_SECONDS = 30 * 60

_STATUS_FIELDS = ("satiety", "mood", "energy", "health", "cleanliness")


@dataclass(frozen=True, slots=True)
class StatusTickResult:
    """一次在线 Tick 的结果。"""

    changed: bool
    deltas: dict[str, int]


class PetStatusTicker:
    """只在程序在线运行时推进 PetState 的温和变化。"""

    def __init__(self, state: PetState) -> None:
        self._state = state
        self.reset()

    def reset(self) -> None:
        self._satiety_seconds = 0.0
        self._energy_seconds = 0.0
        self._cleanliness_seconds = 0.0
        self._mood_pressure_seconds = 0.0
        self._health_pressure_seconds = 0.0

    def advance(
        self,
        elapsed_seconds: float = DEFAULT_TICK_SECONDS,
        *,
        enabled: bool,
    ) -> StatusTickResult:
        """推进在线状态。

        disabled 时不累计时间债务，因此重新开启后不会补扣关闭期间的状态。
        """

        if elapsed_seconds <= 0:
            return StatusTickResult(changed=False, deltas={})
        if not enabled:
            self.reset()
            return StatusTickResult(changed=False, deltas={})

        deltas: dict[str, int] = {}
        self._decay_basic_fields(elapsed_seconds, deltas)
        self._decay_mood_if_under_pressure(elapsed_seconds, deltas)
        self._decay_health_if_under_pressure(elapsed_seconds, deltas)
        actual_deltas = apply_state_deltas(self._state, deltas)
        return StatusTickResult(changed=bool(actual_deltas), deltas=actual_deltas)

    def _decay_basic_fields(self, elapsed_seconds: float, deltas: dict[str, int]) -> None:
        self._satiety_seconds += elapsed_seconds
        self._energy_seconds += elapsed_seconds
        self._cleanliness_seconds += elapsed_seconds
        _add_delta(deltas, "satiety", -self._consume_units("satiety"))
        _add_delta(deltas, "energy", -self._consume_units("energy"))
        _add_delta(deltas, "cleanliness", -self._consume_units("cleanliness"))

    def _consume_units(self, field: str) -> int:
        if field == "satiety":
            units = int(self._satiety_seconds // SATIETY_DECAY_SECONDS)
            self._satiety_seconds -= units * SATIETY_DECAY_SECONDS
            return units
        if field == "energy":
            units = int(self._energy_seconds // ENERGY_DECAY_SECONDS)
            self._energy_seconds -= units * ENERGY_DECAY_SECONDS
            return units
        if field == "cleanliness":
            units = int(self._cleanliness_seconds // CLEANLINESS_DECAY_SECONDS)
            self._cleanliness_seconds -= units * CLEANLINESS_DECAY_SECONDS
            return units
        raise KeyError(field)

    def _decay_mood_if_under_pressure(
        self,
        elapsed_seconds: float,
        deltas: dict[str, int],
    ) -> None:
        if _any_condition_at_or_below(self._state, MOOD_PRESSURE_THRESHOLD):
            self._mood_pressure_seconds += elapsed_seconds
        else:
            self._mood_pressure_seconds = 0.0
        mood_units = int(self._mood_pressure_seconds // MOOD_DECAY_SECONDS)
        if mood_units:
            self._mood_pressure_seconds -= mood_units * MOOD_DECAY_SECONDS
            _add_delta(deltas, "mood", -mood_units)

    def _decay_health_if_under_pressure(
        self,
        elapsed_seconds: float,
        deltas: dict[str, int],
    ) -> None:
        if not _any_condition_at_or_below(self._state, HEALTH_PRESSURE_THRESHOLD):
            self._health_pressure_seconds = 0.0
            return

        previous_units = _health_decay_units(self._health_pressure_seconds)
        self._health_pressure_seconds += elapsed_seconds
        current_units = _health_decay_units(self._health_pressure_seconds)
        health_units = current_units - previous_units
        if health_units:
            _add_delta(deltas, "health", -health_units)


def apply_state_deltas(state: PetState, deltas: dict[str, int]) -> dict[str, int]:
    actual_deltas: dict[str, int] = {}
    for field, delta in deltas.items():
        if field not in _STATUS_FIELDS or delta == 0:
            continue
        old_value = int(getattr(state, field))
        new_value = _clamp_percent(old_value + int(delta))
        if new_value == old_value:
            continue
        setattr(state, field, new_value)
        actual_deltas[field] = new_value - old_value
    return actual_deltas


def _add_delta(deltas: dict[str, int], field: str, delta: int) -> None:
    if delta == 0:
        return
    deltas[field] = deltas.get(field, 0) + delta


def _any_condition_at_or_below(state: PetState, threshold: int) -> bool:
    return (
        state.satiety <= threshold
        or state.energy <= threshold
        or state.cleanliness <= threshold
    )


def _health_decay_units(pressure_seconds: float) -> int:
    if pressure_seconds < HEALTH_GRACE_SECONDS:
        return 0
    return int((pressure_seconds - HEALTH_GRACE_SECONDS) // HEALTH_DECAY_SECONDS) + 1


def _clamp_percent(value: int) -> int:
    return min(100, max(0, int(value)))


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "PetStatusTicker",
    "StatusTickResult",
    "apply_state_deltas",
]
