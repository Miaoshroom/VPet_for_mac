"""桌宠窗口：负责显示动画、处理鼠标交互"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow

from core.animation import PetAnimationDirector
from core.app_paths import config_path
from core.interaction_map import InteractionBehavior, InteractionMap
from ui.pet_display import PetDisplay
from ui.pet_menu import show_pet_menu

RESIZE_GRIP = 22
def _window_settings_path() -> Path:
    return config_path("window_settings.json")

ZOOM_STEP = 30


def _load_settings() -> dict:
    # json不对就该直接崩（
    return json.loads(_window_settings_path().read_text(encoding="utf-8"))


def _max_side_from_json() -> int:
    data = _load_settings()
    return max(0, int(data["display_size"]))


def _dev_mode_from_json() -> bool:
    data = _load_settings()
    return bool(data.get("dev_mode", False))


def _save_display_size_to_json(size: int) -> None:
    try:
        payload = _load_settings()
        payload["display_size"] = max(0, int(size))
        _window_settings_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


class PetWindow(QMainWindow):
    def __init__(
        self,
        director: PetAnimationDirector,
        initial_pixmap: QPixmap,
        interaction_map: InteractionMap,
        mode_titles: dict[str, str] | None = None,
        mode_autoswitch_enabled: Callable[[], bool] | None = None,
        on_toggle_mode_autoswitch: Callable[[bool], None] | None = None,
        auto_move_enabled: Callable[[], bool] | None = None,
        on_toggle_auto_move: Callable[[bool], None] | None = None,
        *,
        max_side: int | None = None,
    ) -> None:
        super().__init__()
        self._director = director
        self._interaction_map = interaction_map
        self._mode_titles = mode_titles or {}
        self._drag_anchor: QPoint | None = None
        self._press_global: QPoint | None = None
        self._press_is_drag = False
        self._pressed_press_behavior = InteractionBehavior(type="none")
        self._pressed_click_behavior = InteractionBehavior(type="none")
        self._pressed_drag_behavior = InteractionBehavior(type="none")
        self._click_through_enabled = False
        self._mode_autoswitch_enabled = mode_autoswitch_enabled or (lambda: False)
        self._on_toggle_mode_autoswitch = on_toggle_mode_autoswitch or (lambda enabled: None)
        self._auto_move_enabled = auto_move_enabled or (lambda: False)
        self._on_toggle_auto_move = on_toggle_auto_move or (lambda enabled: None)
        self._on_quit = QApplication.quit
        self._plugins = []
        self._drop_handlers: list[Callable[[list[Path]], None]] = []
        self._single_active = lambda: False
        self._interrupt_auto_move = lambda: None
        self._dev_mode = _dev_mode_from_json()
        if max_side is None:
            max_side = _max_side_from_json()
        self._max_side = max(0, max_side)

        if self._dev_mode:
            self._base_window_flags = (
                Qt.WindowType.Window
                | Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            self._base_window_flags = (
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
        self._apply_window_flags()
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self._dev_mode)

        self._label = PetDisplay(self._interaction_map, self._dev_mode)
        self._source_pixmap = initial_pixmap

        pix0 = self._fit_pixmap(initial_pixmap)
        self._label.set_pet_pixmap(pix0)
        self.setCentralWidget(self._label)

        w = max(64, pix0.width())
        h = max(64, pix0.height())
        self.resize(w, h)
        self.setMinimumSize(48, 48)
        settings = _load_settings()
        self.move(int(settings["display_x"]), int(settings["display_y"]))

        director.frame_changed.connect(self._on_frame)

    def click_through_enabled(self) -> bool:
        return self._click_through_enabled

    def set_click_through_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._click_through_enabled == enabled:
            return
        self._click_through_enabled = enabled
        self._apply_window_flags()

    def _apply_window_flags(self) -> None:
        flags = self._base_window_flags
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

    def _fit_pixmap(self, pix: QPixmap) -> QPixmap:
        if self._max_side <= 0:
            return pix
        if pix.width() <= self._max_side and pix.height() <= self._max_side:
            return pix
        return pix.scaled(
            self._max_side,
            self._max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def set_pixmap(self, pix: QPixmap) -> None:
        self._source_pixmap = pix
        fitted = self._fit_pixmap(pix)
        self._label.set_pet_pixmap(fitted)
        self.resize(max(64, fitted.width()), max(64, fitted.height()))

    def _on_frame(self, pix: QPixmap) -> None:
        self.set_pixmap(pix)

    def _refresh_current_pixmap(self) -> None:
        fitted = self._fit_pixmap(self._source_pixmap)
        self._label.set_pet_pixmap(fitted)
        self.resize(max(64, fitted.width()), max(64, fitted.height()))

    def _zoom(self, delta: int) -> None:
        self._max_side = max(0, self._max_side + delta)
        self._refresh_current_pixmap()
        _save_display_size_to_json(self._max_side)

    def _switch_mode(self, mode_name: str) -> None:
        if mode_name not in self._mode_titles:
            return
        self._director.switch_mode(mode_name)

    def set_quit_callback(self, callback) -> None:
        self._on_quit = callback

    def set_plugins(self, plugins) -> None:
        self._plugins = list(plugins)

    def add_drop_handler(self, handler: Callable[[list[Path]], None]) -> None:
        self._drop_handlers.append(handler)

    def set_single_active_callback(self, callback: Callable[[], bool]) -> None:
        self._single_active = callback

    def set_auto_move_interrupt_callback(self, callback: Callable[[], None]) -> None:
        self._interrupt_auto_move = callback

    def _plugin_handlers(self) -> dict[str, tuple[bool, Callable[[bool], None]]]:
        handlers = {}
        for plugin in self._plugins:
            menu_title = getattr(plugin, "menu_title", None)
            is_enabled = getattr(plugin, "is_enabled", None)
            set_enabled = getattr(plugin, "set_enabled", None)
            if callable(menu_title) and callable(is_enabled) and callable(set_enabled):
                handlers[str(menu_title())] = (bool(is_enabled()), set_enabled)
        return handlers

    def _save_start_position(self) -> None:
        try:
            payload = _load_settings()
            payload["display_x"] = int(self.x())
            payload["display_y"] = int(self.y())
            payload["display_size"] = max(0, int(self._max_side))
            _window_settings_path().write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _in_resize_grip(self, local_pos: QPoint) -> bool:
        r = self.rect()
        return (
            local_pos.x() >= r.width() - RESIZE_GRIP
            and local_pos.y() >= r.height() - RESIZE_GRIP
        )

    def _handle_behavior(self, behavior: InteractionBehavior) -> None:
        if behavior.type == "press_mode" and behavior.mode is not None:
            self._director.start_interaction(behavior.mode)
            return
        if behavior.type == "press_mode":
            self._director.on_mouse_press()
            return
        if behavior.type == "switch_mode" and behavior.mode is not None:
            self._switch_mode(behavior.mode)

    def _reset_pointer_state(self) -> None:
        self._drag_anchor = None
        self._press_global = None
        self._press_is_drag = False
        self._pressed_press_behavior = InteractionBehavior(type="none")
        self._pressed_click_behavior = InteractionBehavior(type="none")
        self._pressed_drag_behavior = InteractionBehavior(type="none")

    def dragEnterEvent(self, event) -> None:
        if self._single_active():
            event.ignore()
            return
        if _drop_paths(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._single_active():
            event.ignore()
            return
        if _drop_paths(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if self._single_active():
            event.ignore()
            return
        paths = _drop_paths(event)
        if not paths:
            super().dropEvent(event)
            return
        for handler in self._drop_handlers:
            handler(paths)
        event.acceptProposedAction()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if self._single_active():
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._interrupt_auto_move()
            lp = e.position().toPoint()
            if self._in_resize_grip(lp) and self.windowHandle() is not None:
                self.windowHandle().startSystemResize(
                    Qt.Edge.RightEdge | Qt.Edge.BottomEdge
                )
                e.accept()
                return
            self._press_global = e.globalPosition().toPoint()
            self._press_is_drag = False
            self._pressed_press_behavior = self._interaction_map.resolve(
                "press",
                lp,
                self.rect().size(),
            )
            self._pressed_click_behavior = self._interaction_map.resolve(
                "click",
                lp,
                self.rect().size(),
            )
            self._pressed_drag_behavior = self._interaction_map.resolve(
                "drag",
                lp,
                self.rect().size(),
            )
            self._handle_behavior(self._pressed_press_behavior)
            if self._pressed_drag_behavior.type == "move_window":
                self._drag_anchor = self._press_global - self.pos()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._single_active():
            e.accept()
            return
        if (
            e.buttons() & Qt.MouseButton.LeftButton
            and self._press_global is not None
        ):
            current_global = e.globalPosition().toPoint()
            if not self._press_is_drag:
                distance = (current_global - self._press_global).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._press_is_drag = True
            if self._press_is_drag and self._pressed_drag_behavior.type == "move_window":
                if self._drag_anchor is not None:
                    self.move(current_global - self._drag_anchor)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._single_active():
            self._reset_pointer_state()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if not self._press_is_drag:
                self._handle_behavior(self._pressed_click_behavior)
            if self._pressed_press_behavior.type == "press_mode":
                self._director.end_interaction()
            self._reset_pointer_state()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        mode_handlers = {
            title: (lambda name=mode_name: self._switch_mode(name))
            for mode_name, title in self._mode_titles.items()
        }
        show_pet_menu(
            self,
            e.globalPos(),
            on_zoom_in=lambda: self._zoom(ZOOM_STEP),
            on_zoom_out=lambda: self._zoom(-ZOOM_STEP),
            mode_autoswitch_enabled=self._mode_autoswitch_enabled(),
            on_toggle_mode_autoswitch=self._on_toggle_mode_autoswitch,
            auto_move_enabled=self._auto_move_enabled(),
            on_toggle_auto_move=self._on_toggle_auto_move,
            mode_handlers=mode_handlers,
            plugin_handlers=self._plugin_handlers(),
            current_mode_title=self._mode_titles.get(self._director.current_mode_name()),
            on_set_start_pos=self._save_start_position,
            on_quit=self._on_quit,
        )


def _drop_paths(event) -> list[Path]:
    mime = event.mimeData()
    if not mime.hasUrls():
        return []
    return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
