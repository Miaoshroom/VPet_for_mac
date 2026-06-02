"""窗口位置记忆"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QRect, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from core.app_paths import config_path


DEFAULT_WINDOW_SETTINGS = "window_settings.json"


class RememberedWindowGeometry:
    def __init__(
        self,
        widget: QWidget,
        key: str,
        *,
        settings_path: Path | None = None,
        save_delay_ms: int = 180,
    ) -> None:
        self._widget = widget
        self._key = str(key).strip()
        self._settings_path = settings_path or config_path(DEFAULT_WINDOW_SETTINGS)
        self._tracking_enabled = False
        self._restoring = False
        self._save_timer = QTimer(widget)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(max(0, int(save_delay_ms)))
        self._save_timer.timeout.connect(self.save_now)

    def restore(self) -> bool:
        geometry = load_window_geometry(self._key, settings_path=self._settings_path)
        if geometry is None:
            return False
        self._restoring = True
        try:
            self._widget.setGeometry(clamp_window_rect(geometry, self._widget))
        finally:
            self._restoring = False
        return True

    def enable_soon(self) -> None:
        QTimer.singleShot(0, self.enable)

    def enable(self) -> None:
        self._tracking_enabled = True

    def disable(self) -> None:
        self._tracking_enabled = False
        self._save_timer.stop()

    def schedule_save(self) -> None:
        if not self._tracking_enabled or self._restoring:
            return
        self._save_timer.start()

    def save_now(self) -> None:
        if self._restoring:
            return
        save_window_geometry(
            self._key,
            self._widget.geometry(),
            settings_path=self._settings_path,
        )


def load_window_geometry(
    key: str,
    *,
    settings_path: Path | None = None,
) -> QRect | None:
    payload = _read_settings(settings_path)
    windows = payload.get("ui_windows")
    if not isinstance(windows, dict):
        return None
    data = windows.get(str(key))
    if not isinstance(data, dict):
        return None
    try:
        x = int(data["x"])
        y = int(data["y"])
        width = int(data["width"])
        height = int(data["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return QRect(x, y, width, height)


def save_window_geometry(
    key: str,
    rect: QRect,
    *,
    settings_path: Path | None = None,
) -> None:
    payload = _read_settings(settings_path)
    windows = payload.get("ui_windows")
    if not isinstance(windows, dict):
        windows = {}
    windows[str(key)] = {
        "x": int(rect.x()),
        "y": int(rect.y()),
        "width": max(1, int(rect.width())),
        "height": max(1, int(rect.height())),
    }
    payload["ui_windows"] = windows
    try:
        path = _settings_path(settings_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def clamp_window_rect(rect: QRect, widget: QWidget | None = None) -> QRect:
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    if screen is None:
        return QRect(rect)
    available = screen.availableGeometry()
    width = min(max(1, int(rect.width())), max(1, available.width()))
    height = min(max(1, int(rect.height())), max(1, available.height()))
    if widget is not None:
        minimum = widget.minimumSize()
        min_width = min(max(1, minimum.width()), max(1, available.width()))
        min_height = min(max(1, minimum.height()), max(1, available.height()))
        width = min(max(width, min_width), max(1, available.width()))
        height = min(max(height, min_height), max(1, available.height()))

    max_x = max(available.left(), available.right() - width + 1)
    max_y = max(available.top(), available.bottom() - height + 1)
    x = min(max(rect.x(), available.left()), max_x)
    y = min(max(rect.y(), available.top()), max_y)
    return QRect(x, y, width, height)


def _read_settings(settings_path: Path | None = None) -> dict[str, object]:
    try:
        payload = json.loads(_settings_path(settings_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _settings_path(settings_path: Path | None = None) -> Path:
    return settings_path or config_path(DEFAULT_WINDOW_SETTINGS)
