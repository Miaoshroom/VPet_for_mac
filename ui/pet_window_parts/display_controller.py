"""桌宠窗口显示控制"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from ui.pet_window_parts.settings import (
    save_dev_mode_to_json,
    save_display_size_to_json,
)


def click_through_enabled(self) -> bool:
    return self._click_through_enabled


def set_click_through_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if self._click_through_enabled == enabled:
        return
    self._click_through_enabled = enabled
    self._apply_window_flags()
    self._sync_status_panel_controls()


def always_on_top_enabled(self) -> bool:
    return self._always_on_top_enabled


def set_always_on_top_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if self._always_on_top_enabled == enabled:
        return
    self._always_on_top_enabled = enabled
    self._apply_window_flags()
    self._sync_status_panel_controls()


def apply_window_flags(self) -> None:
    flags = self._base_window_flags
    if self._always_on_top_enabled:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    if self._click_through_enabled:
        flags |= Qt.WindowType.WindowTransparentForInput
    geometry = self.geometry()
    was_visible = self.isVisible()
    self.setWindowFlags(flags)
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self._dev_mode)
    if was_visible:
        self.show()
        self.setGeometry(geometry)
        self.raise_()


def fit_pixmap(self, pix: QPixmap) -> QPixmap:
    if self._max_side <= 0:
        return pix
    dpr = max(1.0, self.devicePixelRatioF())
    logical_width = pix.width() / pix.devicePixelRatio()
    logical_height = pix.height() / pix.devicePixelRatio()
    if logical_width <= self._max_side and logical_height <= self._max_side:
        return pix
    target_side = max(1, round(self._max_side * dpr))
    fitted = pix.scaled(
        target_side,
        target_side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    fitted.setDevicePixelRatio(dpr)
    return fitted


def logical_pixmap_size(self, pix: QPixmap) -> tuple[int, int]:
    dpr = pix.devicePixelRatio()
    return (
        max(64, round(pix.width() / dpr)),
        max(64, round(pix.height() / dpr)),
    )


def resize_for_pixmap_size(self, width: int, height: int) -> None:
    if self._dev_panel is None:
        self.resize(width, height)
        return
    panel_hint = self._dev_panel.sizeHint()
    self.resize(max(width, panel_hint.width()), height + panel_hint.height())


def set_pixmap(self, pix: QPixmap) -> None:
    self._source_pixmap = pix
    fitted = self._fit_pixmap(pix)
    self._label.set_pet_pixmap(fitted)
    self._resize_for_pixmap_size(*self._logical_pixmap_size(fitted))
    self._refresh_dev_debug()


def on_frame(self, pix: QPixmap) -> None:
    self.set_pixmap(pix)


def refresh_current_pixmap(self) -> None:
    fitted = self._fit_pixmap(self._source_pixmap)
    self._label.set_pet_pixmap(fitted)
    self._resize_for_pixmap_size(*self._logical_pixmap_size(fitted))
    self._refresh_dev_debug()


def zoom(self, delta: int) -> None:
    self._max_side = max(0, self._max_side + delta)
    self._refresh_current_pixmap()
    save_display_size_to_json(self._max_side)
    self._reposition_status_panel()


def restore_default_size(self) -> None:
    self._max_side = max(0, self._default_max_side)
    self._refresh_current_pixmap()
    save_display_size_to_json(self._max_side)
    self._reposition_status_panel()


def set_mode_autoswitch_enabled(self, enabled: bool) -> None:
    self._on_toggle_mode_autoswitch(enabled)


def set_auto_move_enabled(self, enabled: bool) -> None:
    self._on_toggle_auto_move(enabled)
    self._sync_status_panel_controls()


def set_dev_mode_config_enabled(self, enabled: bool) -> None:
    save_dev_mode_to_json(enabled)
    self._dev_mode_config_enabled = bool(enabled)
    self._sync_status_panel_controls()

