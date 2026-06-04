"""照顾动画里的物品 PNG 叠层"""

from __future__ import annotations

import json
from collections.abc import Mapping

from PyQt6.QtGui import QPixmap

from core.app_paths import config_path
from core.playback.clip import Clip
from core.playback.overlay_clip import PixmapOverlayConfig, clip_with_pixmap_overlay
from core.raising.items import ItemDefinition, resolve_item_icon_path

CARE_OVERLAY_CONFIG = "care_overlay.json"


def clip_with_care_item_icon(clip: Clip, item: ItemDefinition, pet_state: str) -> Clip:
    settings = load_care_overlay_settings()
    if not bool(settings.get("enabled", True)):
        return clip
    config = config_for_action_state(settings, clip.action_id, pet_state)
    if config is None:
        return clip

    icon_path = resolve_item_icon_path(item)
    if icon_path is None:
        return clip
    icon = QPixmap(str(icon_path))
    if icon.isNull():
        return clip

    return clip_with_pixmap_overlay(clip, icon, config)


def load_care_overlay_settings() -> dict[str, object]:
    try:
        payload = json.loads(config_path(CARE_OVERLAY_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def config_for_action_state(
    settings: Mapping[str, object],
    action_id: str | None,
    pet_state: str,
) -> PixmapOverlayConfig | None:
    if not action_id:
        return None
    actions = settings.get("actions")
    if not isinstance(actions, Mapping):
        return None
    action_settings = actions.get(action_id)
    if not isinstance(action_settings, Mapping):
        return None
    state_settings = action_settings.get(pet_state)
    if not isinstance(state_settings, Mapping):
        return None
    try:
        return PixmapOverlayConfig(
            size_ratio=float(state_settings["item_icon_size_ratio"]),
            center_x_ratio=float(state_settings["item_icon_center_x_ratio"]),
            center_y_ratio=float(state_settings["item_icon_center_y_ratio"]),
            visible_start_ratio=float(state_settings["item_icon_visible_start_ratio"]),
            visible_end_ratio=float(state_settings["item_icon_visible_end_ratio"]),
            opacity=float(state_settings["item_icon_opacity"]),
            layer=str(state_settings["item_icon_layer"]).strip(),
            background_enabled=_required_bool(
                state_settings,
                "item_icon_background_enabled",
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _required_bool(values: Mapping[str, object], key: str) -> bool:
    value = values[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be boolean")
    return value


__all__ = [
    "CARE_OVERLAY_CONFIG",
    "clip_with_care_item_icon",
    "config_for_action_state",
    "load_care_overlay_settings",
]
