"""随机展示表情"""

from __future__ import annotations

import json
import random
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel

from core.app_paths import assets_dir, config_path

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class ShowStickerPlugin:
    PLUGIN_NAME = "show_sticker"
    MENU_TITLE = "发表情"

    def __init__(self, context) -> None:
        self._window = context["window"]
        self._settings = _load_settings()
        self._enabled = bool(self._settings["enabled"])
        self._timer = QTimer(self._window)
        self._timer.timeout.connect(self._show_random_sticker)
        self._hide_timer = QTimer(self._window)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_sticker)
        self._label = QLabel(self._window)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label.setScaledContents(True)
        self._label.hide()

    def menu_title(self) -> str:
        return self.MENU_TITLE

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self.start()
        else:
            self.shutdown()

    def start(self) -> None:
        if not self._enabled:
            return
        self._reset_interval()
        self._timer.start()

    def shutdown(self) -> None:
        self._timer.stop()
        self._hide_timer.stop()
        self._label.hide()

    def _reset_interval(self) -> None:
        self._timer.setInterval(
            random.randint(
                int(self._settings["interval_min_ms"]),
                int(self._settings["interval_max_ms"]),
            )
        )

    def _show_random_sticker(self) -> None:
        self._reset_interval()
        sticker_names = tuple(str(name) for name in self._settings.get("stickers", []))
        if not sticker_names:
            return
        sticker_path = _find_sticker(random.choice(sticker_names))
        if sticker_path is None:
            return
        pixmap = QPixmap(str(sticker_path))
        if pixmap.isNull():
            return

        area = self._placement_area()
        size = max(1, round(min(area.width(), area.height()) * _ratio(self._settings["size_ratio"])))
        self._label.setPixmap(pixmap)
        self._label.resize(size, size)
        self._place_label(area)
        self._label.raise_()
        self._label.show()
        self._hide_timer.start(int(self._settings["display_duration_ms"]))

    def _placement_area(self):
        display = getattr(self._window, "_label", self._window)
        return display.geometry()

    def _place_label(self, area) -> None:
        x_ratio = _ratio(self._settings["position_x"])
        y_ratio = _ratio(self._settings["position_y"])
        max_x = max(0, area.width() - self._label.width())
        max_y = max(0, area.height() - self._label.height())
        x = area.x() + round(max_x * x_ratio)
        y = area.y() + round(max_y * y_ratio)
        self._label.move(x, y)

    def _hide_sticker(self) -> None:
        self._label.hide()


def _load_settings() -> dict:
    return json.loads(config_path("plugin_config/show_sticker.json").read_text(encoding="utf-8"))


def _ratio(value) -> float:
    return min(1.0, max(0.0, float(value)))


def _find_sticker(name: str) -> Path | None:
    folder = assets_dir() / "sticker"
    for ext in _IMAGE_EXTS:
        path = folder / f"{name}{ext}"
        if path.is_file():
            return path
    return None
