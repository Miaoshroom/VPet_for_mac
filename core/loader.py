"""动作配置与资源加载"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.animation import Clip, Mode, load_numbered_pngs

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ACTION_SETTINGS = ROOT / "config" / "action_settings.json"


@dataclass(frozen=True)
class LoadedActions:
    modes: dict[str, Mode]
    mode_titles: dict[str, str]
    default_mode: str
    press_mode: str
    idle_autoswitch_interval_min_ms: int
    idle_autoswitch_interval_max_ms: int
    auto_idle_modes: tuple[str, ...]


def load_action_config() -> LoadedActions:
    data = json.loads(ACTION_SETTINGS.read_text(encoding="utf-8"))
    modes: dict[str, Mode] = {}
    mode_titles: dict[str, str] = {}

    for item in data["modes"]:
        mode_id = str(item["id"])
        mode_type = str(item["type"])
        mode_titles[mode_id] = str(item["title"])
        loop = item["loop"]
        loop_clip = _clip_from_dir(
            str(loop["folder"]),
            interval_ms=int(loop["interval_ms"]),
        )
        if mode_type == "loop":
            modes[mode_id] = Mode(loop=loop_clip)
            continue
        if mode_type != "phased":
            raise RuntimeError(f"未知模式类型: {mode_type}")
        start = item["start"]
        end = item["end"]
        modes[mode_id] = Mode(
            loop=loop_clip,
            start=_clip_from_dir(
                str(start["folder"]),
                interval_ms=int(start["interval_ms"]),
            ),
            end=_clip_from_dir(
                str(end["folder"]),
                interval_ms=int(end["interval_ms"]),
            ),
        )

    default_mode = str(data["default_mode"])
    press_mode = str(data["press_mode"])
    idle_autoswitch_interval_min_ms = int(data.get("idle_autoswitch_interval_min_ms", 0))
    idle_autoswitch_interval_max_ms = int(data.get("idle_autoswitch_interval_max_ms", 0))
    auto_idle_modes = tuple(str(mode_id) for mode_id in data.get("auto_idle_modes", []))
    if default_mode not in modes:
        raise RuntimeError(f"default_mode 未在 modes 中定义: {default_mode}")
    if press_mode not in modes:
        raise RuntimeError(f"press_mode 未在 modes 中定义: {press_mode}")
    if not modes[press_mode].is_phased:
        raise RuntimeError("press_mode 必须是 phased 模式")
    if idle_autoswitch_interval_min_ms < 0:
        raise RuntimeError("idle_autoswitch_interval_min_ms 不能小于 0")
    if idle_autoswitch_interval_max_ms < 0:
        raise RuntimeError("idle_autoswitch_interval_max_ms 不能小于 0")
    if idle_autoswitch_interval_min_ms > idle_autoswitch_interval_max_ms:
        raise RuntimeError("idle_autoswitch_interval_min_ms 不能大于 idle_autoswitch_interval_max_ms")
    for mode_id in auto_idle_modes:
        if mode_id not in modes:
            raise RuntimeError(f"auto_idle_modes 未在 modes 中定义: {mode_id}")

    return LoadedActions(
        modes=modes,
        mode_titles=mode_titles,
        default_mode=default_mode,
        press_mode=press_mode,
        idle_autoswitch_interval_min_ms=idle_autoswitch_interval_min_ms,
        idle_autoswitch_interval_max_ms=idle_autoswitch_interval_max_ms,
        auto_idle_modes=auto_idle_modes,
    )


def _clip_from_dir(folder: str, interval_ms: int) -> Clip:
    frames = load_numbered_pngs(ASSETS / folder)
    if not frames:
        raise RuntimeError(f"Missing frames in {ASSETS / folder}")
    return Clip(frames=frames, interval_ms=interval_ms)
