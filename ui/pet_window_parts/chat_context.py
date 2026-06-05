"""用于聊天请求的只读 PetWindow 上下文适配器"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from core.chat.models import PetContextSnapshot, VISUAL_STATES
from core.raising.activity import ActivitySnapshot
from core.raising.items import ITEM_CATEGORIES, ItemCatalog, normalize_inventory
from core.raising.pet_state import DEFAULT_ACTIVITY, PetState
from core.raising.save_game import SaveGame


class _Director(Protocol):
    def pet_state(self) -> str: ...


class _ActivitySystem(Protocol):
    def snapshot(self) -> ActivitySnapshot: ...


class PetWindowChatContextProvider:
    """Build the small read-only state summary visible to AI providers."""

    def __init__(
        self,
        *,
        save_game: SaveGame,
        director: _Director,
        activity_system: _ActivitySystem | None = None,
        item_catalog: ItemCatalog | None = None,
        plugin_active: Callable[[], bool] | None = None,
        single_active: Callable[[], bool] | None = None,
        activity_playback_active: Callable[[], bool] | None = None,
        care_playback_active: Callable[[], bool] | None = None,
        auto_move_active: Callable[[], bool] | None = None,
    ) -> None:
        self._save_game = save_game
        self._director = director
        self._activity_system = activity_system
        self._item_catalog = item_catalog
        self._plugin_active = plugin_active
        self._single_active = single_active
        self._activity_playback_active = activity_playback_active
        self._care_playback_active = care_playback_active
        self._auto_move_active = auto_move_active

    def snapshot(self) -> PetContextSnapshot:
        state = self._pet_state()
        visual_state = _visual_state(_call_text(getattr(self._director, "pet_state", None)))
        return PetContextSnapshot(
            pet_state=_pet_state_summary(state),
            runtime_state=self._runtime_state(visual_state),
            visual_state=visual_state,
            inventory=self._inventory_summary(),
            active_activity=self._activity_summary(),
        )

    def _pet_state(self) -> PetState:
        state = getattr(self._save_game, "pet_state", None)
        if isinstance(state, PetState):
            return state
        return PetState()

    def _inventory_summary(self) -> tuple[Mapping[str, Any], ...]:
        inventory = normalize_inventory(getattr(self._save_game, "inventory", {}))
        items: list[Mapping[str, Any]] = []
        for item_id in sorted(inventory):
            count = inventory[item_id]
            if count <= 0:
                continue
            items.append(self._inventory_item_summary(item_id, count))
        return tuple(items)

    def _inventory_item_summary(
        self,
        item_id: str,
        count: int,
    ) -> Mapping[str, Any]:
        item = None
        if self._item_catalog is not None:
            try:
                item = self._item_catalog.get(item_id)
            except KeyError:
                item = None
        if item is None:
            return {
                "item_id": item_id,
                "name": item_id,
                "count": int(count),
                "category": "unknown",
                "type": "unknown",
                "is_care_item": False,
            }
        category = str(item.category)
        return {
            "item_id": item.id,
            "name": item.name,
            "count": int(count),
            "category": category,
            "type": category,
            "is_care_item": category in ITEM_CATEGORIES,
        }

    def _activity_summary(self) -> Mapping[str, Any]:
        snapshot = _activity_snapshot(self._activity_system)
        return {
            "is_active": bool(snapshot.is_active),
            "activity_id": snapshot.activity_id,
            "name": snapshot.name,
            "category": snapshot.category,
            "elapsed_seconds": int(snapshot.elapsed_seconds),
            "duration_seconds": int(snapshot.duration_seconds),
            "remaining_seconds": int(snapshot.remaining_seconds),
            "progress_percent": int(snapshot.progress_percent),
        }

    def _runtime_state(self, visual_state: str) -> Mapping[str, Any]:
        activity = _activity_snapshot(self._activity_system)
        return {
            "source": "pet_window",
            "read_only": True,
            "visual_state": visual_state,
            "plugin_active": _callback_state(self._plugin_active),
            "single_active": _callback_state(self._single_active),
            "activity_system_active": bool(activity.is_active),
            "activity_playback_active": _callback_state(self._activity_playback_active),
            "care_playback_active": _callback_state(self._care_playback_active),
            "auto_move_active": _callback_state(self._auto_move_active),
        }


def _pet_state_summary(state: PetState) -> Mapping[str, Any]:
    return {
        "satiety": int(state.satiety),
        "mood": int(state.mood),
        "energy": int(state.energy),
        "health": int(state.health),
        "cleanliness": int(state.cleanliness),
        "money": int(state.money),
        "level": int(state.level),
        "affection": int(state.affection),
        "current_activity": str(state.current_activity or DEFAULT_ACTIVITY),
    }


def _activity_snapshot(activity_system: _ActivitySystem | None) -> ActivitySnapshot:
    if activity_system is None:
        return ActivitySnapshot.idle()
    try:
        snapshot = activity_system.snapshot()
    except Exception:
        return ActivitySnapshot.idle()
    if isinstance(snapshot, ActivitySnapshot):
        return snapshot
    return ActivitySnapshot.idle()


def _visual_state(value: str) -> str:
    text = str(value or "").strip()
    if text in VISUAL_STATES:
        return text
    return "normal"


def _call_text(callback: Callable[[], object] | None) -> str:
    if not callable(callback):
        return "normal"
    try:
        return str(callback())
    except Exception:
        return "normal"


def _callback_state(callback: Callable[[], bool] | None) -> bool | str:
    if callback is None:
        return False
    try:
        return bool(callback())
    except Exception:
        return "unknown"


__all__ = ["PetWindowChatContextProvider"]
