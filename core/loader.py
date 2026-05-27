"""从 assets/animations 构建运行时动画目录"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from core.app_paths import assets_dir, config_path
from core.playback.catalog import (
    DEFAULT_PET_STATE,
    LAYERS,
    MATERIAL_STATES,
    PET_STATES,
    PHASES,
    ActionSpec,
    ActionType,
    AnimationCatalog,
    CatalogClips,
    is_valid_variant_name,
    validate_pet_state,
)
from core.playback.clip import Clip, Mode

ACTION_TYPES = ("loop", "phased", "single")


@dataclass(frozen=True)
class LoadedActions:
    animation_catalog: AnimationCatalog
    action_specs: tuple[ActionSpec, ...]
    pet_state: str
    # 迁移期兼容字段：由 animation_catalog 生成，现有调用方暂时使用
    # 它们不能反向影响素材发现方式
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


def load_action_config(pet_state: str = DEFAULT_PET_STATE) -> LoadedActions:
    """读取配置和 assets/animations 并组装运行时动作"""

    pet_state = validate_pet_state(pet_state)
    settings = json.loads(config_path("action_settings.json").read_text(encoding="utf-8"))
    action_specs = _load_action_specs()
    catalog = load_animation_catalog(action_specs=action_specs)
    modes = catalog.build_modes(action_specs, pet_state)
    single_clips = catalog.build_single_clips(action_specs, pet_state)
    mode_titles = {
        spec.id: spec.title
        for spec in action_specs
        # 标题表保存全部 mode 动作 菜单再按当前状态过滤
        if spec.type in ("loop", "phased")
    }
    single_titles = {
        spec.id: spec.title
        for spec in action_specs
        # single 标题同理不绑死在启动状态
        if spec.type == "single"
    }

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

    _require_mode(default_mode, modes, "default_mode")
    _require_mode(press_mode, modes, "press_mode")
    if not modes[press_mode].is_phased:
        raise RuntimeError("press_mode 必须指向 phased 动作")
    for mode_id in auto_idle_modes:
        _require_mode(mode_id, modes, "auto_idle_modes")
    for mode_id in startup:
        _require_single(mode_id, single_clips, "startup")
    for mode_id in shutdown:
        _require_single(mode_id, single_clips, "shutdown")
    for mode_id in single_insert_modes:
        _require_single(mode_id, single_clips, "single_insert_modes")

    return LoadedActions(
        animation_catalog=catalog,
        action_specs=action_specs,
        pet_state=pet_state,
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


def load_animation_catalog(
    animations_root: Path | None = None,
    *,
    action_specs: tuple[ActionSpec, ...] = (),
) -> AnimationCatalog:
    root = animations_root or assets_dir() / "animations"
    clips = _scan_animation_root(root)
    spec_map = {spec.id: spec for spec in action_specs}
    catalog = AnimationCatalog(clips, spec_map)
    for spec in action_specs:
        if not catalog.has_action(spec.id):
            raise RuntimeError(f"modes.json 引用了不存在的动作: {spec.id}")
        _ensure_action_type(catalog, spec)
    return catalog


def _load_action_specs() -> tuple[ActionSpec, ...]:
    data = json.loads(config_path("modes.json").read_text(encoding="utf-8"))
    raw_actions = data.get("actions")
    if not isinstance(raw_actions, list):
        raise RuntimeError("config/modes.json 必须包含 actions 数组")
    specs: list[ActionSpec] = []
    seen: set[str] = set()
    for item in raw_actions:
        if not isinstance(item, dict):
            raise RuntimeError("modes.json 的 actions 项必须是对象")
        action_id = str(item["id"])
        if action_id in seen:
            raise RuntimeError(f"modes.json 中动作 id 重复: {action_id}")
        seen.add(action_id)
        action_type = str(item["type"])
        if action_type not in ACTION_TYPES:
            raise RuntimeError(f"modes.json 中动作类型不合法: {action_id} -> {action_type}")
        specs.append(
            ActionSpec(
                id=action_id,
                title=str(item["title"]),
                type=cast(ActionType, action_type),
            )
        )
    return tuple(specs)


def _scan_animation_root(root: Path) -> CatalogClips:
    if not root.is_dir():
        raise RuntimeError(f"缺少动画素材目录: {root}")
    catalog: CatalogClips = {}
    for action_dir in _visible_dirs(root):
        action_id = action_dir.name
        action_data = catalog.setdefault(action_id, {})
        for state_dir in _visible_dirs(action_dir):
            state = state_dir.name
            if state not in MATERIAL_STATES:
                raise RuntimeError(
                    f"状态目录不合法: {state_dir}。只允许 {', '.join(MATERIAL_STATES)}"
                )
            state_data = action_data.setdefault(state, {})
            for phase_dir in _visible_dirs(state_dir):
                phase = phase_dir.name
                if phase not in PHASES:
                    raise RuntimeError(
                        f"阶段目录不合法: {phase_dir}。只允许 {', '.join(PHASES)}"
                    )
                phase_data = state_data.setdefault(phase, {})
                for variant_dir in _visible_dirs(phase_dir):
                    variant = variant_dir.name
                    if not is_valid_variant_name(variant):
                        raise RuntimeError(
                            f"变体目录不合法: {variant_dir}。必须是两位数字，例如 01"
                        )
                    variant_data = phase_data.setdefault(variant, {})
                    for layer_dir in _visible_dirs(variant_dir):
                        layer = layer_dir.name
                        if layer not in LAYERS:
                            raise RuntimeError(
                                f"图层目录不合法: {layer_dir}。只允许 {', '.join(LAYERS)}"
                            )
                        if layer in variant_data:
                            raise RuntimeError(f"图层目录重复: {layer_dir}")
                        png_paths = _png_files(layer_dir)
                        if not png_paths:
                            raise RuntimeError(f"图层目录没有 png 帧: {layer_dir}")
                        variant_data[layer] = Clip.from_paths(png_paths)
                        _ensure_no_visible_dirs(layer_dir)
                    _ensure_no_visible_files(variant_dir)
                _ensure_no_visible_files(phase_dir)
            _ensure_no_visible_files(state_dir)
        _ensure_no_visible_files(action_dir)
    if not catalog:
        raise RuntimeError(f"动画素材目录为空: {root}")
    return catalog


def _ensure_action_type(catalog: AnimationCatalog, spec: ActionSpec) -> None:
    phases = set(catalog.phases_for(spec.id))
    if spec.type == "single":
        if "single" not in phases:
            raise RuntimeError(f"动作 {spec.id} 在 modes.json 标为 single，但没有 single 阶段")
        return
    if spec.type == "loop":
        if "loop" not in phases:
            raise RuntimeError(f"动作 {spec.id} 在 modes.json 标为 loop，但没有 loop 阶段")
        return
    if not {"start", "loop", "end"} <= phases:
        raise RuntimeError(f"动作 {spec.id} 在 modes.json 标为 phased，但缺少 start/loop/end")


def _visible_dirs(path: Path) -> list[Path]:
    return sorted(child for child in path.iterdir() if child.is_dir() and not child.name.startswith("."))


def _visible_files(path: Path) -> list[Path]:
    return sorted(child for child in path.iterdir() if child.is_file() and not child.name.startswith("."))


def _png_files(path: Path) -> list[Path]:
    files = _visible_files(path)
    bad_files = [file for file in files if file.suffix.lower() != ".png"]
    if bad_files:
        raise RuntimeError(f"图层目录中发现非 png 文件: {bad_files[0]}")
    return files


def _ensure_no_visible_files(path: Path) -> None:
    files = _visible_files(path)
    if files:
        raise RuntimeError(f"素材目录层级中发现不该出现的文件: {files[0]}")


def _ensure_no_visible_dirs(path: Path) -> None:
    dirs = _visible_dirs(path)
    if dirs:
        raise RuntimeError(f"图层目录中发现不该出现的子目录: {dirs[0]}")


def _require_mode(mode_id: str, modes: dict[str, Mode], field: str) -> None:
    if mode_id not in modes:
        raise RuntimeError(f"{field} 引用了未配置或不可播放的动作: {mode_id}")


def _require_single(mode_id: str, single_clips: dict[str, Clip], field: str) -> None:
    if mode_id not in single_clips:
        raise RuntimeError(f"{field} 引用了未配置或不可播放的 single 动作: {mode_id}")
