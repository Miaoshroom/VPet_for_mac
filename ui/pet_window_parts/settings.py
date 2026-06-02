"""桌宠窗口设置读写"""

from __future__ import annotations

import json
from pathlib import Path

from core.app_paths import config_path

RESIZE_GRIP = 22
ZOOM_STEP = 30


def window_settings_path() -> Path:
    return config_path("window_settings.json")


def load_settings() -> dict:
    # json不对就该直接崩（
    return json.loads(window_settings_path().read_text(encoding="utf-8"))


def max_side_from_json() -> int:
    data = load_settings()
    return max(0, int(data["display_size"]))


def dev_mode_from_json() -> bool:
    data = load_settings()
    return bool(data.get("dev_mode", False))


def save_display_size_to_json(size: int) -> None:
    try:
        payload = load_settings()
        payload["display_size"] = max(0, int(size))
        window_settings_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def save_dev_mode_to_json(enabled: bool) -> None:
    try:
        payload = load_settings()
        payload["dev_mode"] = bool(enabled)
        window_settings_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def save_start_position_to_json(x: int, y: int, display_size: int) -> None:
    try:
        payload = load_settings()
        payload["display_x"] = int(x)
        payload["display_y"] = int(y)
        payload["display_size"] = max(0, int(display_size))
        window_settings_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

