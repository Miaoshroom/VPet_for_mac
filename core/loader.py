"""从配置文件和资源目录构建运行时动作对象。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.animation import Clip, Mode, load_numbered_png_paths

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ACTION_SETTINGS = ROOT / "config" / "action_settings.json"
MODES_SETTINGS = ROOT / "config" / "modes.json"


@dataclass(frozen=True)
class LoadedActions:
    modes: dict[str, Mode]
    mode_titles: dict[str, str]
    single_clips: dict[str, Clip]
    single_titles: dict[str, str]
    startup: tuple[str, ...]
    shutdown: tuple[str, ...]
    single_insert_interval_min_ms: int
    single_insert_interval_max_ms: int
    single_insert_modes: tuple[str, ...]
    default_mode: str
    press_mode: str
    idle_autoswitch_interval_min_ms: int
    idle_autoswitch_interval_max_ms: int
    auto_idle_modes: tuple[str, ...]


def load_action_config() -> LoadedActions:
    """读取运行设置与动作定义，并组装成运行时对象。"""

    settings = json.loads(ACTION_SETTINGS.read_text(encoding="utf-8"))
    modes_data = json.loads(MODES_SETTINGS.read_text(encoding="utf-8"))
    modes: dict[str, Mode] = {}
    mode_titles: dict[str, str] = {}
    single_clips: dict[str, Clip] = {}
    single_titles: dict[str, str] = {}

    for item in modes_data.get("loop_modes", []):
        mode_id = str(item["id"])
        mode_titles[mode_id] = str(item["title"])
        modes[mode_id] = Mode(
            loop=_clip_from_dir(
                str(item["folder"]),
                interval_ms=int(item["interval_ms"]),
            )
        )

    for item in modes_data.get("phased_modes", []):
        mode_id = str(item["id"])
        mode_titles[mode_id] = str(item["title"])
        base = str(item["base"])
        modes[mode_id] = Mode(
            loop=_clip_from_dir(
                f"{base}/loop",
                interval_ms=int(item["loop_interval_ms"]),
            ),
            start=_clip_from_dir(
                f"{base}/start",
                interval_ms=int(item["start_interval_ms"]),
            ),
            end=_clip_from_dir(
                f"{base}/end",
                interval_ms=int(item["end_interval_ms"]),
            ),
        )

    for item in modes_data.get("single_modes", []):
        mode_id = str(item["id"])
        single_titles[mode_id] = str(item["title"])
        single_clips[mode_id] = _clip_from_dir(
            str(item["folder"]),
            interval_ms=int(item["interval_ms"]),
        )

    startup = tuple(str(mode_id) for mode_id in settings.get("startup", []))
    shutdown = tuple(str(mode_id) for mode_id in settings.get("shutdown", []))
    single_insert_modes = tuple(str(mode_id) for mode_id in settings.get("single_insert_modes", []))
    default_mode = str(settings["default_mode"])
    press_mode = str(settings["press_mode"])
    idle_autoswitch_interval_min_ms = int(settings.get("idle_autoswitch_interval_min_ms", 0))
    idle_autoswitch_interval_max_ms = int(settings.get("idle_autoswitch_interval_max_ms", 0))
    auto_idle_modes = tuple(str(mode_id) for mode_id in settings.get("auto_idle_modes", []))
    single_insert_interval_min_ms = int(settings.get("single_insert_interval_min_ms", 0))
    single_insert_interval_max_ms = int(settings.get("single_insert_interval_max_ms", 0))

    if default_mode not in modes:
        raise RuntimeError(f"default_mode 未在 loop_modes / phased_modes 中定义: {default_mode}")
    if press_mode not in modes:
        raise RuntimeError(f"press_mode 未在 loop_modes / phased_modes 中定义: {press_mode}")
    if not modes[press_mode].is_phased:
        raise RuntimeError("press_mode 必须是 phased 模式")
    for mode_id in auto_idle_modes:
        if mode_id not in modes:
            raise RuntimeError(f"auto_idle_modes 未在 loop_modes / phased_modes 中定义: {mode_id}")
    for mode_id in startup:
        if mode_id not in single_clips:
            raise RuntimeError(f"startup 未在 single_modes 中定义: {mode_id}")
    for mode_id in shutdown:
        if mode_id not in single_clips:
            raise RuntimeError(f"shutdown 未在 single_modes 中定义: {mode_id}")
    for mode_id in single_insert_modes:
        if mode_id not in single_clips:
            raise RuntimeError(f"single_insert_modes 未在 single_modes 中定义: {mode_id}")

    return LoadedActions(
        modes=modes,
        mode_titles=mode_titles,
        single_clips=single_clips,
        single_titles=single_titles,
        startup=startup,
        shutdown=shutdown,
        single_insert_interval_min_ms=single_insert_interval_min_ms,
        single_insert_interval_max_ms=single_insert_interval_max_ms,
        single_insert_modes=single_insert_modes,
        default_mode=default_mode,
        press_mode=press_mode,
        idle_autoswitch_interval_min_ms=idle_autoswitch_interval_min_ms,
        idle_autoswitch_interval_max_ms=idle_autoswitch_interval_max_ms,
        auto_idle_modes=auto_idle_modes,
    )


def _clip_from_dir(folder: str, interval_ms: int) -> Clip:
    """按目录读取一组连续编号的图片，并构建 Clip。"""

    frame_paths = load_numbered_png_paths(ASSETS / folder)
    if not frame_paths:
        raise RuntimeError(f"Missing frames in {ASSETS / folder}")
    return Clip(frame_paths=tuple(frame_paths), interval_ms=interval_ms)
