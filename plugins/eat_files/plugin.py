"""拖文件给桌宠吃掉"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.app_paths import config_path
from core.playback.catalog import AnimationCatalog
from core.playback.clip import Clip
from plugins.eat_files.icon_overlay import clip_with_file_icon


class EatFilesPlugin:
    PLUGIN_NAME = "eat_files"
    MENU_TITLE = "吃文件"

    def __init__(self, context) -> None:
        self._window = context["window"]
        self._director = context["director"]
        self._single_player = context["single_player"]
        self._animation_catalog: AnimationCatalog = context["animation_catalog"]
        self._settings = _load_settings()
        self._enabled = bool(self._settings["enabled"])
        self._window.add_drop_handler(self._on_drop_files)

    def menu_title(self) -> str:
        return self.MENU_TITLE

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def _on_drop_files(self, paths: list[Path]) -> None:
        if not self._enabled:
            return
        if self._single_player.is_active():
            return
        clip = self._clip_for_current_state(paths)
        if clip is None:
            # 当前状态没有吃文件动画时不移动文件
            return
        moved = self._move_files(paths)
        if not moved:
            return
        self._window.pause_plugins_for_interaction()
        if not self._single_player.play(clip, on_finished=self._window.resume_plugins_after_interaction):
            self._window.resume_plugins_after_interaction()

    def _clip_for_current_state(self, paths: list[Path]) -> Clip | None:
        animation_id = str(self._settings["single_animation"])
        pet_state = self._director.pet_state()
        try:
            clip = self._animation_catalog.single_for(animation_id, pet_state)
        except KeyError:
            return None
        return clip_with_file_icon(
            clip,
            _first_existing_path(paths),
            icon_size_ratio=float(self._settings.get("file_icon_size_ratio", 0.15)),
            center_x_ratio=float(self._settings.get("file_icon_center_x_ratio", 0.5)),
            center_y_ratio=float(self._settings.get("file_icon_center_y_ratio", 0.575)),
            visible_start_ratio=float(self._settings.get("file_icon_visible_start_ratio", 0.0)),
            visible_end_ratio=float(self._settings.get("file_icon_visible_end_ratio", 1.0)),
            opacity=float(self._settings.get("file_icon_opacity", 1.0)),
            layer=str(self._settings.get("file_icon_layer", "behind_front")),
        )

    def _move_files(self, paths: list[Path]) -> bool:
        trash_dir = Path(str(self._settings["trash_path"])).expanduser()
        trash_dir.mkdir(parents=True, exist_ok=True)
        moved = False
        for path in paths:
            if not path.exists():
                continue
            try:
                shutil.move(str(path), str(_unique_target(trash_dir, path.name)))
            except (OSError, shutil.Error):
                continue
            moved = True
        return moved


def _load_settings() -> dict:
    return json.loads(config_path("plugin_config/eat_files.json").read_text(encoding="utf-8"))


def _first_existing_path(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    index = 1
    while True:
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
