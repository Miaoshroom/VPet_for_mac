"""项目路径和macOS的路径"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

APP_NAME = "VPet_for_mac"


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


def bundled_config_dir() -> Path:
    return resource_root() / "config"


def app_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def user_config_dir() -> Path:
    path = app_support_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def helper_binary_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper_bin"


def helper_python_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper.py"


def helper_swift_path() -> Path:
    return resource_root() / "helpers" / "audio_level_helper.swift"
