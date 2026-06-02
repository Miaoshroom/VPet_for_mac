"""养成状态数据模型。

这里的状态是真实数值，不等同于 playback 里的 happy/normal 等动画表现状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VisualPetState = Literal["happy", "normal", "poor_condition", "ill"]

DEFAULT_ACTIVITY = "待机"
LOW_HEALTH_THRESHOLD = 20
LOW_CONDITION_THRESHOLD = 20
HAPPY_MOOD_THRESHOLD = 75
NORMAL_HEALTH_THRESHOLD = 50


@dataclass(slots=True)
class PetState:
    money: int = 0
    satiety: int = 80
    mood: int = 80
    energy: int = 80
    health: int = 100
    cleanliness: int = 80
    exp: int = 0
    level: int = 1
    affection: int = 0
    current_activity: str = DEFAULT_ACTIVITY

    def __post_init__(self) -> None:
        self.money = _non_negative_int(self.money)
        self.satiety = _percent_int(self.satiety)
        self.mood = _percent_int(self.mood)
        self.energy = _percent_int(self.energy)
        self.health = _percent_int(self.health)
        self.cleanliness = _percent_int(self.cleanliness)
        self.exp = _non_negative_int(self.exp)
        self.level = _level_int(self.level)
        self.affection = _non_negative_int(self.affection)
        activity = str(self.current_activity).strip()
        self.current_activity = activity or DEFAULT_ACTIVITY

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PetState":
        defaults = cls()
        return cls(
            money=data.get("money", defaults.money),
            satiety=data.get("satiety", defaults.satiety),
            mood=data.get("mood", defaults.mood),
            energy=data.get("energy", defaults.energy),
            health=data.get("health", defaults.health),
            cleanliness=data.get("cleanliness", defaults.cleanliness),
            exp=data.get("exp", defaults.exp),
            level=data.get("level", defaults.level),
            affection=data.get("affection", defaults.affection),
            current_activity=data.get("current_activity", defaults.current_activity),
        )

    def to_dict(self) -> dict[str, int | str]:
        return {
            "money": self.money,
            "satiety": self.satiety,
            "mood": self.mood,
            "energy": self.energy,
            "health": self.health,
            "cleanliness": self.cleanliness,
            "exp": self.exp,
            "level": self.level,
            "affection": self.affection,
            "current_activity": self.current_activity,
        }

    def suggested_visual_state(self) -> VisualPetState:
        return suggest_visual_state(self)


def suggest_visual_state(state: PetState) -> VisualPetState:
    if state.health <= LOW_HEALTH_THRESHOLD:
        return "ill"
    if (
        state.satiety <= LOW_CONDITION_THRESHOLD
        or state.energy <= LOW_CONDITION_THRESHOLD
        or state.cleanliness <= LOW_CONDITION_THRESHOLD
    ):
        return "poor_condition"
    if state.mood >= HAPPY_MOOD_THRESHOLD and state.health >= NORMAL_HEALTH_THRESHOLD:
        return "happy"
    return "normal"


def _percent_int(value: object) -> int:
    return min(100, max(0, _int_value(value)))


def _non_negative_int(value: object) -> int:
    return max(0, _int_value(value))


def _level_int(value: object) -> int:
    return max(1, _int_value(value))


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "DEFAULT_ACTIVITY",
    "PetState",
    "VisualPetState",
    "suggest_visual_state",
]
