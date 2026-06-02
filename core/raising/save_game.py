"""玩家进度存档。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.app_paths import save_game_path
from core.raising.activity import ActivityProgress
from core.raising.items import normalize_inventory
from core.raising.pet_state import PetState

SAVE_VERSION = 3


@dataclass(slots=True)
class SaveGame:
    pet_state: PetState = field(default_factory=PetState)
    inventory: dict[str, int] = field(default_factory=dict)
    activity_progress: ActivityProgress | None = None
    status_decay_enabled: bool = False
    auto_refill_enabled: bool = False
    auto_purchase_enabled: bool = False
    last_saved_at: str = ""

    def __post_init__(self) -> None:
        self.inventory = normalize_inventory(self.inventory)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SaveGame":
        pet_payload = data.get("pet_state", {})
        if not isinstance(pet_payload, dict):
            pet_payload = {}

        activity_progress = ActivityProgress.from_dict(data.get("activity_progress"))

        last_saved_at = data.get("last_saved_at", "")
        if not isinstance(last_saved_at, str):
            last_saved_at = str(last_saved_at)

        return cls(
            pet_state=PetState.from_dict(pet_payload),
            inventory=normalize_inventory(data.get("inventory", {})),
            activity_progress=activity_progress,
            status_decay_enabled=_bool_value(data.get("status_decay_enabled", False)),
            auto_refill_enabled=_bool_value(data.get("auto_refill_enabled", False)),
            auto_purchase_enabled=_bool_value(
                data.get("auto_purchase_enabled", False)
            ),
            last_saved_at=last_saved_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SAVE_VERSION,
            "pet_state": self.pet_state.to_dict(),
            "inventory": normalize_inventory(self.inventory),
            "activity_progress": (
                self.activity_progress.to_dict()
                if self.activity_progress is not None
                else None
            ),
            "status_decay_enabled": self.status_decay_enabled,
            "auto_refill_enabled": self.auto_refill_enabled,
            "auto_purchase_enabled": self.auto_purchase_enabled,
            "last_saved_at": self.last_saved_at,
        }


def load_save_game(path: Path | None = None) -> SaveGame:
    target = path or save_game_path()
    if not target.exists():
        return SaveGame()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"存档根节点必须是对象: {target}")
    return SaveGame.from_dict(payload)


def write_save_game(save_game: SaveGame, path: Path | None = None) -> Path:
    target = path or save_game_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    save_game.last_saved_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = json.dumps(save_game.to_dict(), ensure_ascii=False, indent=2)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


__all__ = [
    "SAVE_VERSION",
    "SaveGame",
    "load_save_game",
    "write_save_game",
]
