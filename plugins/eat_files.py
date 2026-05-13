"""拖文件给桌宠吃掉。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.app_paths import config_path


class EatFilesPlugin:
    PLUGIN_NAME = "eat_files"
    MENU_TITLE = "吃文件"

    def __init__(self, context) -> None:
        self._window = context["window"]
        self._single_player = context["single_player"]
        self._single_clips = context["single_clips"]
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
        if not self._enabled or self._single_player.is_active():
            return
        moved = self._move_files(paths)
        if not moved:
            return
        clip = self._single_clips.get(str(self._settings["single_animation"]))
        if clip is not None:
            self._single_player.play(clip)

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
