"""桌宠窗口：负责显示动画、处理鼠标交互"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from core.animation import PET_STATES, PlaybackDebugSnapshot, PetAnimationDirector
from core.app_paths import config_path
from core.interaction_map import Gesture, InteractionBehavior, InteractionMap
from ui.pet_display import DevModePanel, PetDisplay
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
        action_blocked: Callable[[], bool] | None = None,
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
        self._action_blocked = action_blocked or (lambda: False)
        self._on_quit = QApplication.quit
        self._plugins = []
        self._drop_handlers: list[Callable[[list[Path]], None]] = []
        self._single_active = lambda: False
        self._single_debug_snapshot: Callable[[], PlaybackDebugSnapshot | None] = lambda: None
        self._single_replay_current: Callable[[], bool] = lambda: False
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
                | Qt.WindowType.NoDropShadowWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
        self._apply_window_flags()
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self._dev_mode)

        self._label = PetDisplay(self._interaction_map, self._dev_mode)
        self._dev_panel: DevModePanel | None = None
        self._source_pixmap = initial_pixmap

        pix0 = self._fit_pixmap(initial_pixmap)
        self._label.set_pet_pixmap(pix0)
        if self._dev_mode:
            self._dev_panel = DevModePanel(PET_STATES)
            self._dev_panel.pet_state_requested.connect(self._set_dev_pet_state)
            self._dev_panel.replay_requested.connect(self._replay_dev_action)
            central = QWidget(self)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._label, 1)
            layout.addWidget(self._dev_panel, 0)
            self.setCentralWidget(central)
        else:
            self.setCentralWidget(self._label)

        w, h = self._logical_pixmap_size(pix0)
        self._resize_for_pixmap_size(w, h)
        self.setMinimumSize(48, 48)
        settings = _load_settings()
        self.move(int(settings["display_x"]), int(settings["display_y"]))

        director.frame_changed.connect(self._on_frame)
        self._refresh_dev_debug()

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

    def _logical_pixmap_size(self, pix: QPixmap) -> tuple[int, int]:
        dpr = pix.devicePixelRatio()
        return (
            max(64, round(pix.width() / dpr)),
            max(64, round(pix.height() / dpr)),
        )

    def _resize_for_pixmap_size(self, width: int, height: int) -> None:
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

    def _on_frame(self, pix: QPixmap) -> None:
        self.set_pixmap(pix)

    def _refresh_current_pixmap(self) -> None:
        fitted = self._fit_pixmap(self._source_pixmap)
        self._label.set_pet_pixmap(fitted)
        self._resize_for_pixmap_size(*self._logical_pixmap_size(fitted))
        self._refresh_dev_debug()

    def _zoom(self, delta: int) -> None:
        self._max_side = max(0, self._max_side + delta)
        self._refresh_current_pixmap()
        _save_display_size_to_json(self._max_side)

    def _switch_mode(self, mode_name: str) -> None:
        if self._action_blocked():
            return
        if mode_name not in self._mode_titles:
            return
        self._director.switch_mode(mode_name)
        self._refresh_dev_debug()

    def _current_debug_snapshot(self) -> PlaybackDebugSnapshot:
        return self._single_debug_snapshot() or self._director.debug_snapshot()

    def _refresh_dev_debug(self) -> None:
        if self._dev_panel is None:
            return
        self._dev_panel.set_snapshot(self._current_debug_snapshot())

    def _set_dev_pet_state(self, pet_state: str) -> None:
        try:
            self._director.set_pet_state(pet_state, resume=not self._action_blocked())
        except KeyError as exc:
            self._refresh_dev_debug()
            if self._dev_panel is not None:
                self._dev_panel.set_error(str(exc))
            return
        self._refresh_dev_debug()

    def _replay_dev_action(self) -> None:
        if self._single_replay_current():
            self._refresh_dev_debug()
            return
        if self._action_blocked():
            self._refresh_dev_debug()
            if self._dev_panel is not None:
                self._dev_panel.set_notice("插件动作运行中，重播已跳过，避免抢当前动作。")
            return
        self._director.replay_current_action()
        self._refresh_dev_debug()

    def set_quit_callback(self, callback) -> None:
        self._on_quit = callback

    def set_plugins(self, plugins) -> None:
        self._plugins = list(plugins)

    def add_drop_handler(self, handler: Callable[[list[Path]], None]) -> None:
        self._drop_handlers.append(handler)

    def set_single_active_callback(self, callback: Callable[[], bool]) -> None:
        self._single_active = callback

    def set_single_debug_callbacks(
        self,
        snapshot: Callable[[], PlaybackDebugSnapshot | None],
        replay_current: Callable[[], bool],
    ) -> None:
        self._single_debug_snapshot = snapshot
        self._single_replay_current = replay_current

    def set_auto_move_interrupt_callback(self, callback: Callable[[], None]) -> None:
        self._interrupt_auto_move = callback

    def _plugin_handlers(self) -> dict[str, tuple[bool, Callable[[bool], None]]]:
        handlers = {}
        for plugin in self._plugins:
            if callable(getattr(plugin, "build_menu", None)):
                continue
            menu_title = getattr(plugin, "menu_title", None)
            is_enabled = getattr(plugin, "is_enabled", None)
            set_enabled = getattr(plugin, "set_enabled", None)
            if callable(menu_title) and callable(is_enabled) and callable(set_enabled):
                handlers[str(menu_title())] = (bool(is_enabled()), set_enabled)
        return handlers

    def _plugin_menu_builders(self) -> list[Callable]:
        builders = []
        for plugin in self._plugins:
            build_menu = getattr(plugin, "build_menu", None)
            if callable(build_menu):
                builders.append(build_menu)
        return builders

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

    def _display_local_pos(self, window_pos: QPoint) -> QPoint | None:
        display_pos = self._label.mapFrom(self, window_pos)
        if not self._label.rect().contains(display_pos):
            return None
        return display_pos

    def _resolve_display_behavior(
        self,
        gesture: Gesture,
        display_pos: QPoint,
    ) -> InteractionBehavior:
        return self._interaction_map.resolve(
            gesture,
            display_pos,
            self._label.rect().size(),
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

    def _should_pause_plugins_for_press(self, behavior: InteractionBehavior) -> bool:
        return behavior.type == "press_mode"

    def _reset_pointer_state(self) -> None:
        self._drag_anchor = None
        self._press_global = None
        self._press_is_drag = False
        self._pressed_press_behavior = InteractionBehavior(type="none")
        self._pressed_click_behavior = InteractionBehavior(type="none")
        self._pressed_drag_behavior = InteractionBehavior(type="none")

    def pause_plugins_for_interaction(self) -> None:
        for plugin in self._plugins:
            pause = getattr(plugin, "pause_for_interaction", None)
            if callable(pause):
                pause()

    def resume_plugins_after_interaction(self) -> None:
        for plugin in self._plugins:
            resume = getattr(plugin, "resume_after_interaction", None)
            if callable(resume):
                resume()

    def dragEnterEvent(self, event) -> None:
        if self._single_active():
            event.ignore()
            return
        if _drop_paths(event):
            self._interrupt_auto_move()
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
        self._interrupt_auto_move()
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
            display_pos = self._display_local_pos(lp)
            if display_pos is None:
                super().mousePressEvent(e)
                return
            self._press_global = e.globalPosition().toPoint()
            self._press_is_drag = False
            self._pressed_press_behavior = self._resolve_display_behavior(
                "press",
                display_pos,
            )
            self._pressed_click_behavior = self._resolve_display_behavior(
                "click",
                display_pos,
            )
            self._pressed_drag_behavior = self._resolve_display_behavior(
                "drag",
                display_pos,
            )
            if self._should_pause_plugins_for_press(self._pressed_press_behavior):
                self.pause_plugins_for_interaction()
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
            self.resume_plugins_after_interaction()
            self._reset_pointer_state()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        available_modes = self._director.available_mode_ids(self._mode_titles)
        mode_handlers = {
            title: (lambda name=mode_name: self._switch_mode(name))
            # 右键菜单只展示当前状态能播的动作
            for mode_name in available_modes
            if (title := self._mode_titles.get(mode_name)) is not None
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
            plugin_menu_builders=self._plugin_menu_builders(),
            current_mode_title=self._mode_titles.get(self._director.current_mode_name()),
            on_set_start_pos=self._save_start_position,
            on_quit=self._on_quit,
        )


def _drop_paths(event) -> list[Path]:
    mime = event.mimeData()
    if not mime.hasUrls():
        return []
    return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
