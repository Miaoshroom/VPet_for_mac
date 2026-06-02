"""项目路径和macOS的路径"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

APP_NAME = "VPet_for_mac"
APP_SETTINGS_CONFIG = "app_settings.json"
SAVE_LOCATION_APP_SUPPORT = "app_support"
SAVE_LOCATION_PROJECT_ROOT = "project_root"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass is not None:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return resource_root() / "assets"


def item_icons_dir() -> Path:
    return assets_dir() / "item_icons"


def bundled_config_dir() -> Path:
    return resource_root() / "config"


def app_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def project_save_data_dir() -> Path:
    return resource_root() / "saves"


def app_support_save_data_dir() -> Path:
    return app_support_dir() / "saves"


def user_config_dir() -> Path:
    path = app_support_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_data_dir() -> Path:
    path = _configured_save_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_game_path(name: str = "savegame.json") -> Path:
    return save_data_dir() / name


def config_path(name: str) -> Path:
    bundled = bundled_config_dir() / name
    if not is_frozen():
        return bundled

    user_path = user_config_dir() / name
    if not user_path.exists():
        if not bundled.exists():
            raise FileNotFoundError(f"缺少默认配置文件: {bundled}")
        shutil.copy2(bundled, user_path)
    return user_path


def _configured_save_data_dir() -> Path:
    if _configured_save_location() == SAVE_LOCATION_PROJECT_ROOT and not is_frozen():
        return project_save_data_dir()
    return app_support_save_data_dir()


def _configured_save_location() -> str:
    settings = _load_app_settings()
    location = str(settings.get("save_location", SAVE_LOCATION_APP_SUPPORT)).strip()
    if location == SAVE_LOCATION_PROJECT_ROOT:
        return SAVE_LOCATION_PROJECT_ROOT
    return SAVE_LOCATION_APP_SUPPORT


def _load_app_settings() -> dict[str, object]:
    try:
        payload = json.loads(config_path(APP_SETTINGS_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def helper_binary_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper_bin"


def helper_python_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper.py"


def helper_swift_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper.swift"
