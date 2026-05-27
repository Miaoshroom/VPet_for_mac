"""负责选择移动动作并移动窗口"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PyQt6.QtCore import QObject, QRect, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from core.animation import Mode, PetAnimationDirector
from core.app_paths import config_path


@dataclass(frozen=True)
class MoveRule:
    mode: str
    type: str
    speed_px_per_sec: float


@dataclass(frozen=True)
class Boundary:
    left: int
    right: int
    top: int
    bottom: int


class StartStop(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class SingleSwitch(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_active(self) -> bool: ...


class AutoMoveController(QObject):
    def __init__(
        self,
        parent: QObject,
        director: PetAnimationDirector,
        window,
        modes: dict[str, Mode],
        action_blocked: Callable[[], bool],
        single_autoswitch: SingleSwitch,
        mode_autoswitch: StartStop | None = None,
        single_active: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        settings = _load_settings()
        self._director = director
        self._window = window
        self._modes = modes
        self._action_blocked = action_blocked
        self._single_autoswitch = single_autoswitch
        self._mode_autoswitch = mode_autoswitch
        self._single_active = single_active or (lambda: False)
        self._enabled = bool(settings["enabled_default"])
        self._interval_min_ms = int(settings["interval_min_ms"])
        self._interval_max_ms = int(settings["interval_max_ms"])
        self._distance_min_px = int(settings.get("distance_min_px", 120))
        boundary = settings["boundary_px"]
        self._boundary = Boundary(
            left=int(boundary["left"]),
            right=int(boundary["right"]),
            top=int(boundary["top"]),
            bottom=int(boundary["bottom"]),
        )
        self._tick_ms = int(settings.get("tick_ms", 33))
        self._rules = tuple(
            MoveRule(str(item["mode"]), str(item["type"]), float(item["speed_px_per_sec"]))
            for item in settings.get("moves", [])
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._maybe_move)
        self._move_timer = QTimer(self)
        self._move_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._move_timer.timeout.connect(self._move_tick)
        self._active = False
        self._current_rule: MoveRule | None = None
        self._current_move_mode: Mode | None = None
        self._vx = 0.0
        self._vy = 0.0
        self._x = 0.0
        self._y = 0.0
        self._target_x = 0.0
        self._target_y = 0.0

        if self._enabled:
            self.start()

    def is_enabled(self) -> bool:
        return self._enabled

    def is_active(self) -> bool:
        return self._active

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if not self._enabled or not self._rules or self._timer.isActive():
            return
        self._reset_interval()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._active:
            self._finish_move(restart_timer=False)

    def interrupt(self) -> None:
        if self._active:
            self._finish_move(restart_timer=True)

    def shutdown(self) -> None:
        self._enabled = False
        self.stop()

    def _reset_interval(self) -> None:
        self._timer.setInterval(random.randint(self._interval_min_ms, self._interval_max_ms))

    def _maybe_move(self) -> None:
        self._reset_interval()
        if self._active:
            return
        if self._single_autoswitch.is_active() or self._single_active():
            return
        if self._action_blocked():
            return
        if self._director.is_interaction_active():
            return

        candidates = self._available_rules()
        if not candidates:
            return
        self._start_move(random.choice(candidates))

    def _available_rules(self) -> list[MoveRule]:
        rect = self._window.geometry()
        bounds = self._screen_bounds()
        min_x, min_y, max_x, max_y = _limits(bounds, rect, self._boundary)
        boundary = self._boundary
        top_rules: list[MoveRule] = []
        rules: list[MoveRule] = []
        for rule in self._rules:
            mode = self._mode_for_rule(rule)
            if mode is None or not mode.is_phased:
                continue
            vx, vy = _vector_for(rule)
            can_move_left = rect.x() > min_x + max(0, boundary.left)
            can_move_right = rect.x() < max_x - max(0, boundary.right)
            can_move_up = rect.y() > min_y + max(0, boundary.top)
            can_move_down = rect.y() < max_y - max(0, boundary.bottom)
            near_left = rect.x() <= min_x + max(0, boundary.left)
            near_right = rect.x() >= max_x - max(0, boundary.right)
            near_top = rect.y() <= min_y + max(0, boundary.top)

            if rule.type == "horizontal_top":
                if near_top and ((vx < 0 and can_move_left) or (vx > 0 and can_move_right)):
                    top_rules.append(rule)
            elif rule.type == "horizontal":
                if (vx < 0 and can_move_left) or (vx > 0 and can_move_right):
                    rules.append(rule)
            elif rule.type == "left_up":
                if near_left and can_move_up:
                    rules.append(rule)
            elif rule.type == "right_up":
                if near_right and can_move_up:
                    rules.append(rule)
            elif rule.type == "left_down":
                if can_move_left and can_move_down:
                    rules.append(rule)
            elif rule.type == "right_down":
                if can_move_right and can_move_down:
                    rules.append(rule)
        return top_rules or rules

    def _start_move(self, rule: MoveRule) -> None:
        mode = self._mode_for_rule(rule)
        if mode is None or not mode.is_phased:
            return
        if not self._director.start_interaction(rule.mode):
            return
        active_mode = self._director.active_interaction_mode() or mode
        self._active = True
        self._current_rule = rule
        self._current_move_mode = active_mode
        self._timer.stop()
        self._single_autoswitch.stop()
        if self._mode_autoswitch is not None:
            self._mode_autoswitch.stop()
        start_delay = active_mode.start.duration_ms if active_mode.start is not None else 0
        QTimer.singleShot(start_delay, self._start_move_timer)

    def _start_move_timer(self) -> None:
        if not self._active or self._current_rule is None:
            return
        if self._single_active():
            self._finish_move(restart_timer=True)
            return
        vx, vy = _vector_for(self._current_rule)
        length = math.hypot(vx, vy)
        if length == 0:
            self._finish_move(restart_timer=True)
            return
        rect = self._window.geometry()
        bounds = self._screen_bounds()
        min_x, min_y, max_x, max_y = _limits(bounds, rect, self._boundary)
        self._x = float(self._window.x())
        self._y = float(self._window.y())
        nx = vx / length
        ny = vy / length
        max_distance = _max_distance_to_boundary(self._x, self._y, nx, ny, min_x, min_y, max_x, max_y)
        if max_distance <= 1:
            self._finish_move(restart_timer=True)
            return
        distance = random.uniform(min(self._distance_min_px, max_distance), max_distance)
        self._target_x = _clamp(self._x + nx * distance, min_x, max_x)
        self._target_y = _clamp(self._y + ny * distance, min_y, max_y)
        speed = self._current_rule.speed_px_per_sec
        self._vx = nx * speed
        self._vy = ny * speed
        self._move_timer.start(self._tick_ms)

    def _move_tick(self) -> None:
        step_distance = self._current_speed() * self._tick_ms / 1000.0
        dx = self._target_x - self._x
        dy = self._target_y - self._y
        remaining = math.hypot(dx, dy)
        if remaining <= step_distance:
            self._x = self._target_x
            self._y = self._target_y
            self._window.move(round(self._x), round(self._y))
            self._finish_move(restart_timer=True)
            return

        ratio = step_distance / remaining
        self._x += dx * ratio
        self._y += dy * ratio
        self._window.move(round(self._x), round(self._y))

    def _current_speed(self) -> float:
        return math.hypot(self._vx, self._vy)

    def _finish_move(self, restart_timer: bool) -> None:
        self._move_timer.stop()
        rule = self._current_rule
        mode = self._current_move_mode
        self._active = False
        self._current_rule = None
        self._current_move_mode = None
        self._director.end_interaction()
        end_delay = 0
        if rule is not None and mode is not None:
            end_delay = mode.end.duration_ms if mode.end is not None else 0
        QTimer.singleShot(end_delay, lambda: self._after_move_end(restart_timer))

    def _mode_for_rule(self, rule: MoveRule) -> Mode | None:
        # 移动动作也要按当前状态查素材
        try:
            return self._director.mode_for_action(rule.mode)
        except KeyError:
            return None

    def _after_move_end(self, restart_timer: bool) -> None:
        self._single_autoswitch.start()
        if self._mode_autoswitch is not None:
            self._mode_autoswitch.start()
        if restart_timer and self._enabled:
            self._reset_interval()
            self._timer.start()

    def _screen_bounds(self) -> QRect:
        screen = self._window.screen() or QApplication.primaryScreen()
        if screen is None:
            return self._window.geometry()
        return screen.geometry()


def _load_settings() -> dict:
    return json.loads(config_path("move_settings.json").read_text(encoding="utf-8"))


def _vector_for(rule: MoveRule) -> tuple[float, float]:
    if rule.type in ("horizontal", "horizontal_top"):
        return (-1.0, 0.0) if "left" in rule.mode else (1.0, 0.0)
    if rule.type in ("left_up", "right_up"):
        return (0.0, -1.0)
    if rule.type == "left_down":
        return (-1.0, 1.0)
    if rule.type == "right_down":
        return (1.0, 1.0)
    return (0.0, 0.0)


def _screen_limits(bounds: QRect, rect: QRect) -> tuple[int, int, int, int]:
    min_x = bounds.x()
    min_y = bounds.y()
    max_x = bounds.x() + bounds.width() - rect.width()
    max_y = bounds.y() + bounds.height() - rect.height()
    return min_x, min_y, max(min_x, max_x), max(min_y, max_y)


def _limits(bounds: QRect, rect: QRect, boundary: Boundary) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = _screen_limits(bounds, rect)
    return (
        min_x + boundary.left,
        min_y + boundary.top,
        max_x - boundary.right,
        max_y - boundary.bottom,
    )


def _max_distance_to_boundary(
    x: float,
    y: float,
    nx: float,
    ny: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> float:
    distances: list[float] = []
    if nx > 0:
        distances.append((max_x - x) / nx)
    elif nx < 0:
        distances.append((min_x - x) / nx)
    if ny > 0:
        distances.append((max_y - y) / ny)
    elif ny < 0:
        distances.append((min_y - y) / ny)
    positive = [distance for distance in distances if distance > 0]
    return min(positive) if positive else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
