"""当前活动的定义、进度和结算逻辑。

活动系统只修改养成数值和存档进度，不驱动动画表现状态。
配置里的动画字段只是给桥接层使用的播放意图。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.app_paths import config_path
from core.raising.leveling import LevelUpResult, apply_level_ups
from core.raising.pet_state import DEFAULT_ACTIVITY, PetState

PERCENT_FIELDS = frozenset({"satiety", "mood", "energy", "health", "cleanliness"})
NON_NEGATIVE_FIELDS = frozenset({"money", "exp", "level", "affection"})
ACTIVITY_FIELDS = PERCENT_FIELDS | NON_NEGATIVE_FIELDS
DEFAULT_ACTIVITY_SETTINGS = "activity_settings.json"


@dataclass(frozen=True, slots=True)
class ActivityDefinition:
    id: str
    name: str
    category: str
    duration_seconds: int
    costs: dict[str, int]
    rewards: dict[str, int]
    requirements: dict[str, int]
    description: str = ""
    animation_id: str | None = None
    animation_candidates: tuple[str, ...] = ()

    def total_deltas(self, ratio: float = 1.0) -> dict[str, int]:
        deltas: dict[str, int] = {}
        for field, amount in self.rewards.items():
            _add_delta(deltas, field, amount)
        for field, amount in self.costs.items():
            _add_delta(deltas, field, -amount)
        if ratio >= 1.0:
            return {field: delta for field, delta in deltas.items() if delta}
        return {
            field: scaled
            for field, delta in deltas.items()
            if (scaled := _scale_delta(delta, ratio)) != 0
        }

    def animation_action_ids(self) -> tuple[str, ...]:
        action_ids: list[str] = []
        for action_id in (self.animation_id, *self.animation_candidates):
            action_id = str(action_id or "").strip()
            if action_id and action_id not in action_ids:
                action_ids.append(action_id)
        return tuple(action_ids)


@dataclass(slots=True)
class ActivityProgress:
    activity_id: str
    elapsed_seconds: int = 0

    @classmethod
    def from_dict(cls, data: object) -> "ActivityProgress | None":
        if not isinstance(data, dict):
            return None
        activity_id = str(data.get("activity_id", "")).strip()
        if not activity_id:
            return None
        return cls(
            activity_id=activity_id,
            elapsed_seconds=max(0, _int_value(data.get("elapsed_seconds", 0))),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "activity_id": self.activity_id,
            "elapsed_seconds": max(0, int(self.elapsed_seconds)),
        }


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    is_active: bool
    activity_id: str | None
    name: str
    category: str
    elapsed_seconds: int
    duration_seconds: int

    @classmethod
    def idle(cls) -> "ActivitySnapshot":
        return cls(
            is_active=False,
            activity_id=None,
            name=DEFAULT_ACTIVITY,
            category="待机",
            elapsed_seconds=0,
            duration_seconds=0,
        )

    @property
    def progress_ratio(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return min(1.0, max(0.0, self.elapsed_seconds / self.duration_seconds))

    @property
    def progress_percent(self) -> int:
        return round(self.progress_ratio * 100)

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.duration_seconds - self.elapsed_seconds)


@dataclass(frozen=True, slots=True)
class ActivitySettlement:
    activity: ActivityDefinition
    ratio: float
    deltas: dict[str, int]
    level_result: LevelUpResult


@dataclass(frozen=True, slots=True)
class ActivityStartResult:
    ok: bool
    changed: bool
    message: str
    activity: ActivityDefinition | None = None


@dataclass(frozen=True, slots=True)
class ActivityAdvanceResult:
    changed: bool
    completed: bool
    message: str
    activity: ActivityDefinition | None = None
    settlement: ActivitySettlement | None = None


@dataclass(frozen=True, slots=True)
class ActivityCancelResult:
    ok: bool
    changed: bool
    message: str
    activity: ActivityDefinition | None = None
    settlement: ActivitySettlement | None = None


class ActivityCatalog:
    def __init__(self, activities: list[ActivityDefinition]) -> None:
        if not activities:
            raise ValueError("活动配置不能为空")
        self._activities: dict[str, ActivityDefinition] = {}
        for activity in activities:
            if activity.id in self._activities:
                raise ValueError(f"活动 id 重复: {activity.id}")
            self._activities[activity.id] = activity

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ActivityCatalog":
        raw_activities = data.get("activities", [])
        if not isinstance(raw_activities, list):
            raise ValueError("activity_settings.json 的 activities 必须是列表")
        return cls([_activity_from_dict(item) for item in raw_activities])

    def activities(self) -> tuple[ActivityDefinition, ...]:
        return tuple(self._activities.values())

    def get(self, activity_id: str) -> ActivityDefinition:
        return self._activities[activity_id]

    def has(self, activity_id: str) -> bool:
        return activity_id in self._activities


class ActivitySystem:
    """推进当前活动，并把进度保存在 SaveGame 上。"""

    def __init__(self, save_game: Any, catalog: ActivityCatalog) -> None:
        self._save_game = save_game
        self._catalog = catalog
        self.changed_on_load = self._normalize_loaded_progress()

    def activities(self) -> tuple[ActivityDefinition, ...]:
        return self._catalog.activities()

    def is_active(self) -> bool:
        return self._current_progress() is not None

    def current_activity(self) -> ActivityDefinition | None:
        progress = self._current_progress()
        if progress is None:
            return None
        try:
            return self._catalog.get(progress.activity_id)
        except KeyError:
            return None

    def snapshot(self) -> ActivitySnapshot:
        progress = self._current_progress()
        if progress is None:
            return ActivitySnapshot.idle()
        try:
            activity = self._catalog.get(progress.activity_id)
        except KeyError:
            return ActivitySnapshot.idle()
        return ActivitySnapshot(
            is_active=True,
            activity_id=activity.id,
            name=activity.name,
            category=activity.category,
            elapsed_seconds=max(0, int(progress.elapsed_seconds)),
            duration_seconds=activity.duration_seconds,
        )

    def start(self, activity_id: str) -> ActivityStartResult:
        if self.is_active():
            current = self.snapshot()
            return ActivityStartResult(
                ok=False,
                changed=False,
                message=f"当前正在进行：{current.name}",
            )
        try:
            activity = self._catalog.get(activity_id)
        except KeyError:
            return ActivityStartResult(
                ok=False,
                changed=False,
                message=f"未知活动：{activity_id}",
            )

        missing = missing_requirements(self._save_game.pet_state, activity)
        if missing:
            return ActivityStartResult(
                ok=False,
                changed=False,
                message=_format_missing_requirements(missing),
                activity=activity,
            )

        self._save_game.activity_progress = ActivityProgress(activity.id, 0)
        self._save_game.pet_state.current_activity = activity.name
        return ActivityStartResult(
            ok=True,
            changed=True,
            message=f"已开始：{activity.name}",
            activity=activity,
        )

    def advance(self, elapsed_seconds: float) -> ActivityAdvanceResult:
        progress = self._current_progress()
        if progress is None or elapsed_seconds <= 0:
            return ActivityAdvanceResult(changed=False, completed=False, message="")
        try:
            activity = self._catalog.get(progress.activity_id)
        except KeyError:
            self._clear_activity()
            return ActivityAdvanceResult(
                changed=True,
                completed=False,
                message="活动配置已不存在，当前活动已回到待机。",
            )

        old_elapsed = max(0, int(progress.elapsed_seconds))
        progress.elapsed_seconds = min(
            activity.duration_seconds,
            old_elapsed + max(0, int(elapsed_seconds)),
        )
        if progress.elapsed_seconds <= old_elapsed:
            return ActivityAdvanceResult(changed=False, completed=False, message="")

        if progress.elapsed_seconds >= activity.duration_seconds:
            settlement = self._settle(activity, ratio=1.0)
            return ActivityAdvanceResult(
                changed=True,
                completed=True,
                message=f"已完成：{activity.name}",
                activity=activity,
                settlement=settlement,
            )

        return ActivityAdvanceResult(
            changed=True,
            completed=False,
            message="",
            activity=activity,
        )

    def cancel(self) -> ActivityCancelResult:
        progress = self._current_progress()
        if progress is None:
            return ActivityCancelResult(
                ok=False,
                changed=False,
                message="当前没有正在进行的活动。",
            )
        try:
            activity = self._catalog.get(progress.activity_id)
        except KeyError:
            self._clear_activity()
            return ActivityCancelResult(
                ok=True,
                changed=True,
                message="活动配置已不存在，当前活动已取消。",
            )

        ratio = 0.0
        if activity.duration_seconds > 0:
            ratio = min(1.0, max(0.0, progress.elapsed_seconds / activity.duration_seconds))
        settlement = self._settle(activity, ratio=ratio)
        return ActivityCancelResult(
            ok=True,
            changed=True,
            message=f"已取消：{activity.name}",
            activity=activity,
            settlement=settlement,
        )

    def _normalize_loaded_progress(self) -> bool:
        progress = self._current_progress()
        if progress is None:
            return self._set_pet_activity_name(DEFAULT_ACTIVITY)
        try:
            activity = self._catalog.get(progress.activity_id)
        except KeyError:
            self._clear_activity()
            return True
        progress.elapsed_seconds = max(0, min(int(progress.elapsed_seconds), activity.duration_seconds))
        return self._set_pet_activity_name(activity.name)

    def _current_progress(self) -> ActivityProgress | None:
        progress = getattr(self._save_game, "activity_progress", None)
        if isinstance(progress, ActivityProgress):
            return progress
        progress = ActivityProgress.from_dict(progress)
        self._save_game.activity_progress = progress
        return progress

    def _settle(self, activity: ActivityDefinition, *, ratio: float) -> ActivitySettlement:
        deltas = activity.total_deltas(ratio=ratio)
        actual_deltas = apply_activity_deltas(self._save_game.pet_state, deltas)
        level_result = apply_level_ups(self._save_game.pet_state)
        self._clear_activity()
        return ActivitySettlement(
            activity=activity,
            ratio=min(1.0, max(0.0, ratio)),
            deltas=actual_deltas,
            level_result=level_result,
        )

    def _clear_activity(self) -> None:
        self._save_game.activity_progress = None
        self._save_game.pet_state.current_activity = DEFAULT_ACTIVITY

    def _set_pet_activity_name(self, name: str) -> bool:
        name = str(name).strip() or DEFAULT_ACTIVITY
        if self._save_game.pet_state.current_activity == name:
            return False
        self._save_game.pet_state.current_activity = name
        return True


def load_activity_catalog(path: Path | None = None) -> ActivityCatalog:
    target = path or config_path(DEFAULT_ACTIVITY_SETTINGS)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"活动配置根节点必须是对象: {target}")
    return ActivityCatalog.from_dict(payload)


def missing_requirements(
    state: PetState,
    activity: ActivityDefinition,
) -> dict[str, tuple[int, int]]:
    missing: dict[str, tuple[int, int]] = {}
    for field, required in activity.requirements.items():
        current = _state_value(state, field)
        if current < required:
            missing[field] = (current, required)
    return missing


def apply_activity_deltas(state: PetState, deltas: dict[str, int]) -> dict[str, int]:
    actual_deltas: dict[str, int] = {}
    for field, delta in deltas.items():
        if field not in ACTIVITY_FIELDS or delta == 0:
            continue
        old_value = _state_value(state, field)
        if field in PERCENT_FIELDS:
            new_value = _clamp_percent(old_value + int(delta))
        else:
            new_value = max(0, old_value + int(delta))
        if new_value == old_value:
            continue
        setattr(state, field, new_value)
        actual_deltas[field] = new_value - old_value
    return actual_deltas


def _activity_from_dict(data: object) -> ActivityDefinition:
    if not isinstance(data, dict):
        raise ValueError("单个活动配置必须是对象")
    activity_id = _required_text(data, "id")
    return ActivityDefinition(
        id=activity_id,
        name=_required_text(data, "name"),
        category=_required_text(data, "category"),
        duration_seconds=max(1, _int_value(data.get("duration_seconds", 0))),
        costs=_field_amounts(data.get("costs", {}), f"{activity_id}.costs"),
        rewards=_field_amounts(data.get("rewards", {}), f"{activity_id}.rewards"),
        requirements=_field_amounts(
            data.get("requirements", {}),
            f"{activity_id}.requirements",
        ),
        description=_optional_text(data.get("description")) or "",
        animation_id=_optional_text(data.get("animation_id")),
        animation_candidates=_text_tuple(
            data.get("animation_candidates", ()),
            f"{activity_id}.animation_candidates",
        ),
    )


def _field_amounts(data: object, context: str) -> dict[str, int]:
    if not isinstance(data, dict):
        raise ValueError(f"{context} 必须是对象")
    values: dict[str, int] = {}
    for field, raw_value in data.items():
        field_name = str(field).strip()
        if field_name not in ACTIVITY_FIELDS:
            raise ValueError(f"{context} 包含未知字段: {field_name}")
        amount = _int_value(raw_value)
        if amount < 0:
            raise ValueError(f"{context}.{field_name} 不能是负数")
        if amount:
            values[field_name] = amount
    return values


def _required_text(data: dict[str, object], key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"活动配置缺少字段: {key}")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_tuple(data: object, context: str) -> tuple[str, ...]:
    if data is None:
        return ()
    if isinstance(data, str):
        text = data.strip()
        return (text,) if text else ()
    if not isinstance(data, (list, tuple)):
        raise ValueError(f"{context} 必须是字符串列表")
    values: list[str] = []
    for item in data:
        text = str(item).strip()
        if text and text not in values:
            values.append(text)
    return tuple(values)


def _format_missing_requirements(missing: dict[str, tuple[int, int]]) -> str:
    parts = [
        f"{_field_label(field)} {current}/{required}"
        for field, (current, required) in missing.items()
    ]
    return "状态不足，无法开始：" + "，".join(parts)


def _field_label(field: str) -> str:
    labels = {
        "money": "金币",
        "satiety": "饱腹",
        "mood": "心情",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
        "exp": "经验",
        "level": "等级",
        "affection": "亲密度",
    }
    return labels.get(field, field)


def _state_value(state: PetState, field: str) -> int:
    return _int_value(getattr(state, field))


def _add_delta(deltas: dict[str, int], field: str, delta: int) -> None:
    if delta == 0:
        return
    deltas[field] = deltas.get(field, 0) + int(delta)


def _scale_delta(delta: int, ratio: float) -> int:
    ratio = min(1.0, max(0.0, ratio))
    if delta == 0 or ratio <= 0.0:
        return 0
    amount = math.floor(abs(delta) * ratio)
    if amount == 0:
        return 0
    return amount if delta > 0 else -amount


def _clamp_percent(value: int) -> int:
    return min(100, max(0, int(value)))


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "ActivityAdvanceResult",
    "ActivityCancelResult",
    "ActivityCatalog",
    "ActivityDefinition",
    "ActivityProgress",
    "ActivitySettlement",
    "ActivitySnapshot",
    "ActivityStartResult",
    "ActivitySystem",
    "DEFAULT_ACTIVITY_SETTINGS",
    "apply_activity_deltas",
    "load_activity_catalog",
    "missing_requirements",
]
