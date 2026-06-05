"""桌宠输入事件控制"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow

from core.interaction_map import Gesture, InteractionBehavior
from core.raising.pet_session import show_activity_notice
from ui.pet_window_parts.settings import RESIZE_GRIP


def switch_mode(self, mode_name: str) -> None:
    if self._action_blocked():
        return
    if self._activity_system.is_active():
        show_activity_notice(self, "活动进行中，普通动作已跳过。")
        return
    if mode_name not in self._mode_titles:
        return
    self._director.switch_mode(mode_name)
    self._refresh_dev_debug()
    self._sync_status_panel_info()


def in_resize_grip(self, local_pos: QPoint) -> bool:
    r = self.rect()
    return (
        local_pos.x() >= r.width() - RESIZE_GRIP
        and local_pos.y() >= r.height() - RESIZE_GRIP
    )


def display_local_pos(self, window_pos: QPoint) -> QPoint | None:
    display_pos = self._label.mapFrom(self, window_pos)
    if not self._label.rect().contains(display_pos):
        return None
    return display_pos


def resolve_display_behavior(
    self,
    gesture: Gesture,
    display_pos: QPoint,
) -> InteractionBehavior:
    return self._interaction_map.resolve(
        gesture,
        display_pos,
        self._label.rect().size(),
    )


def handle_behavior(self, behavior: InteractionBehavior) -> bool:
    if behavior.type == "press_mode" and behavior.mode is not None:
        return self._start_user_press_interaction(behavior.mode)
    if behavior.type == "press_mode":
        return self._start_user_press_interaction(None)
    if behavior.type == "switch_mode" and behavior.mode is not None:
        if self._activity_system.is_active():
            show_activity_notice(self, "活动进行中，普通动作已跳过。")
            return False
        self._switch_mode(behavior.mode)
    return False


def start_user_press_interaction(self, mode: str | None) -> bool:
    suspended_activity = self._suspend_activity_animation_for_user_interaction()
    try:
        if mode is not None:
            started = self._director.start_interaction(mode) is not None
        else:
            started = bool(self._director.on_mouse_press())
    except (KeyError, ValueError):
        started = False
    if not started and suspended_activity:
        self._resume_activity_animation_if_needed()
    return started


def suspend_activity_animation_for_user_interaction(self) -> bool:
    if not self._activity_system.is_active() or not self._activity_playback.is_active():
        return False
    result = self._activity_playback.suspend_activity_animation()
    suspended = result.action_id is not None and not self._activity_playback.is_active()
    if suspended:
        self._refresh_dev_debug()
    return suspended


def resume_activity_animation_if_needed(self) -> None:
    if self._activity_system.is_active() and not self._activity_playback.is_active():
        self._resume_loaded_activity_animation()
        self._refresh_dev_debug()
        self._sync_activity_panel()
        return


def should_pause_plugins_for_press(self, behavior: InteractionBehavior) -> bool:
    return behavior.type == "press_mode" and not self._activity_system.is_active()


def reset_pointer_state(self) -> None:
    self._drag_anchor = None
    self._press_global = None
    self._press_is_drag = False
    self._press_interaction_started = False
    self._pressed_press_behavior = InteractionBehavior(type="none")
    self._pressed_click_behavior = InteractionBehavior(type="none")
    self._pressed_drag_behavior = InteractionBehavior(type="none")


def interaction_end_locked(self) -> bool:
    is_finishing = getattr(self._director, "is_interaction_finishing", None)
    return (
        callable(is_finishing)
        and is_finishing()
        and self._press_global is None
    )


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


def drag_enter_event(self, event) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
        event.ignore()
        return
    if drop_paths(event):
        self._interrupt_auto_move()
        event.acceptProposedAction()
        return
    QMainWindow.dragEnterEvent(self, event)


def drag_move_event(self, event) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
        event.ignore()
        return
    if drop_paths(event):
        event.acceptProposedAction()
        return
    QMainWindow.dragMoveEvent(self, event)


def drop_event(self, event) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
        event.ignore()
        return
    paths = drop_paths(event)
    if not paths:
        QMainWindow.dropEvent(self, event)
        return
    self._interrupt_auto_move()
    for handler in self._drop_handlers:
        handler(paths)
    event.acceptProposedAction()


def mouse_press_event(self, e: QMouseEvent) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
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
            QMainWindow.mousePressEvent(self, e)
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
        self._press_interaction_started = self._handle_behavior(
            self._pressed_press_behavior
        )
        if self._pressed_drag_behavior.type == "move_window":
            self._drag_anchor = self._press_global - self.pos()
        e.accept()
        return
    QMainWindow.mousePressEvent(self, e)


def mouse_move_event(self, e: QMouseEvent) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
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
                self._reposition_status_panel()
        e.accept()
        return
    QMainWindow.mouseMoveEvent(self, e)


def mouse_release_event(self, e: QMouseEvent) -> None:
    if (
        self._single_active()
        or self._care_playback.is_active()
        or self._interaction_end_locked()
    ):
        self._reset_pointer_state()
        e.accept()
        return
    if e.button() == Qt.MouseButton.LeftButton:
        if not self._press_is_drag:
            self._handle_behavior(self._pressed_click_behavior)
        if self._press_interaction_started:
            self._director.end_interaction()
        self.resume_plugins_after_interaction()
        self._reset_pointer_state()
        e.accept()
        return
    QMainWindow.mouseReleaseEvent(self, e)


def context_menu_event(self, e) -> None:
    if self._interaction_end_locked():
        e.accept()
        return
    if _dismiss_visible_chat_window(self):
        e.accept()
        return
    self.toggle_status_panel()
    e.accept()


def _dismiss_visible_chat_window(self) -> bool:
    controller = getattr(self, "_chat_controller", None)
    window = getattr(controller, "window", None)
    if window is None:
        return False
    take_closed_by_outside = getattr(window, "take_closed_by_outside", None)
    if callable(take_closed_by_outside) and take_closed_by_outside():
        if window.isVisible():
            controller.hide_window()
        return False
    if not window.isVisible():
        return False
    controller.hide_window()
    return True


def drop_paths(event) -> list[Path]:
    mime = event.mimeData()
    if not mime.hasUrls():
        return []
    return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
