"""番茄钟插件。"""

from __future__ import annotations

import json

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMenu

from core.app_paths import config_path
from core.phased_player import PhasedPlayer
from plugins.tomato_clock.timer_window import TomatoClockWindow

TICK_MS = 1000
RESUME_CHECK_INTERVAL_MS = 50
PHASE_IDLE = "idle"
PHASE_FOCUS = "focus"
PHASE_REST = "rest"


class TomatoClockPlugin:
    PLUGIN_NAME = "tomato_clock"
    MENU_TITLE = "番茄钟"

    def __init__(self, context) -> None:
        self._window = context["window"]
        self._director = context["director"]
        self._modes = context["modes"]
        self._default_mode = context["default_mode"]
        self._mode_autoswitch = context["mode_autoswitch"]
        self._plugin_runtime = context["plugin_runtime"]
        self._single_player = context["single_player"]
        self._auto_move = context.get("auto_move")

        self._settings = _load_settings()
        self._mode_titles = _load_mode_titles()
        self._group_id = str(self._settings["default_group"])
        self._mode_id = str(self._settings["default_mode"])
        self._rest_mode = str(self._settings["rest_mode"])
        self._focus_minutes = int(self._settings["default_focus_minutes"])
        self._rest_minutes = int(self._settings["default_rest_minutes"])
        self._phase = PHASE_IDLE
        self._remaining_seconds = 0
        self._count = 0
        self._running = False
        self._paused = False
        self._has_action_control = False
        self._interaction_paused = False
        self._waiting_for_phase_animation = False
        self._stopping = False

        self._timer = QTimer(self._window)
        self._timer.timeout.connect(self._tick)
        self._timer_window = TomatoClockWindow(self._window)
        self._phased_player = PhasedPlayer(self._window, self._window)

    def build_menu(self, root_menu: QMenu) -> None:
        menu = root_menu.addMenu(self.MENU_TITLE)
        self._build_mode_menu(menu.addMenu("动作选择"))
        self._build_minutes_menu(
            menu.addMenu("持续时间设置"),
            tuple(int(value) for value in self._settings["focus_minutes"]),
            self._focus_minutes,
            self._set_focus_minutes,
        )
        self._build_minutes_menu(
            menu.addMenu("休息时间设置"),
            tuple(int(value) for value in self._settings["rest_minutes"]),
            self._rest_minutes,
            self._set_rest_minutes,
        )
        menu.addSeparator()
        start_action = menu.addAction("开始")
        pause_action = menu.addAction("暂停")
        stop_action = menu.addAction("停止")
        start_action.triggered.connect(self._start)
        pause_action.triggered.connect(self._pause)
        stop_action.triggered.connect(self._stop)

    def shutdown(self) -> None:
        self._shutdown_now()

    def pause_for_interaction(self) -> None:
        if not self._running:
            return
        self._interaction_paused = True
        self._waiting_for_phase_animation = False
        self._phased_player.stop()

    def resume_after_interaction(self) -> None:
        if not self._running or not self._interaction_paused:
            return
        if self._manual_animation_active():
            QTimer.singleShot(RESUME_CHECK_INTERVAL_MS, self.resume_after_interaction)
            return
        self._interaction_paused = False
        self._director.stop()
        self._start_phase_animation()

    def _build_mode_menu(self, menu: QMenu) -> None:
        for group_id, group in self._settings["groups"].items():
            group_menu = menu.addMenu(str(group["title"]))
            for mode_id in group["modes"]:
                mode_id = str(mode_id)
                action = group_menu.addAction(self._mode_titles.get(mode_id, mode_id))
                action.setCheckable(True)
                action.setChecked(mode_id == self._mode_id)
                action.triggered.connect(
                    lambda checked=False, group_id=group_id, mode_id=mode_id: self._select_mode(group_id, mode_id)
                )

    def _build_minutes_menu(self, menu: QMenu, values: tuple[int, ...], current: int, setter) -> None:
        for minutes in values:
            action = menu.addAction(f"{minutes} 分钟")
            action.setCheckable(True)
            action.setChecked(minutes == current)
            action.triggered.connect(
                lambda checked=False, minutes=minutes: setter(minutes)
            )

    def _select_mode(self, group_id: str, mode_id: str) -> None:
        self._group_id = str(group_id)
        self._mode_id = str(mode_id)
        self._update_window()
        if self._running and self._phase == PHASE_FOCUS:
            self._transition_phase_animation()

    def _set_focus_minutes(self, minutes: int) -> None:
        self._focus_minutes = int(minutes)

    def _set_rest_minutes(self, minutes: int) -> None:
        self._rest_minutes = int(minutes)

    def _start(self) -> None:
        if self._running and not self._paused:
            return
        if self._running and self._paused:
            self._paused = False
            self._timer.start(TICK_MS)
            self._update_window()
            return
        if not self._begin_action_control():
            return
        self._running = True
        self._paused = False
        self._phase = PHASE_FOCUS
        self._remaining_seconds = self._focus_minutes * 60
        self._count = 0
        self._start_phase_animation()
        self._timer.start(TICK_MS)
        self._show_window()

    def _pause(self) -> None:
        if not self._running:
            return
        self._paused = True
        self._timer.stop()
        self._update_window()

    def _stop(self) -> None:
        self._timer.stop()
        self._running = False
        self._paused = False
        self._phase = PHASE_IDLE
        self._remaining_seconds = 0
        self._count = 0
        self._interaction_paused = False
        self._waiting_for_phase_animation = False
        self._timer_window.hide_timer()
        self._finish_animation_then_end_control()

    def _shutdown_now(self) -> None: # 硬停止番茄钟，避免和退出动画抢画面
        self._timer.stop()
        self._running = False
        self._paused = False
        self._phase = PHASE_IDLE
        self._remaining_seconds = 0
        self._count = 0
        self._interaction_paused = False
        self._waiting_for_phase_animation = False
        self._stopping = False
        self._timer_window.hide_timer()
        self._phased_player.stop()
        if self._has_action_control:
            self._has_action_control = False
            self._plugin_runtime.end_action(self.PLUGIN_NAME)

    def _tick(self) -> None:
        if not self._running or self._paused:
            return
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._advance_phase()
            return
        self._update_window()

    def _advance_phase(self) -> None:
        if self._phase == PHASE_FOCUS:
            self._count += 1
            self._phase = PHASE_REST
            self._remaining_seconds = self._rest_minutes * 60
        else:
            self._phase = PHASE_FOCUS
            self._remaining_seconds = self._focus_minutes * 60
        self._update_window()
        self._transition_phase_animation()

    def _begin_action_control(self) -> bool:
        if self._has_action_control:
            return True
        if self._single_player.is_active():
            return False
        if not self._plugin_runtime.try_begin_action(self.PLUGIN_NAME):
            return False
        self._has_action_control = True
        self._mode_autoswitch.stop()
        if self._auto_move is not None:
            self._auto_move.interrupt()
        self._director.stop()
        return True

    def _finish_animation_then_end_control(self) -> None:
        if self._phased_player.is_active():
            self._stopping = True
            self._phased_player.finish()
            return
        self._end_action_control()

    def _end_action_control(self) -> None:
        self._stopping = False
        self._phased_player.stop()
        if not self._has_action_control:
            return
        self._has_action_control = False
        self._director.stop()
        self._plugin_runtime.end_action(self.PLUGIN_NAME)
        self._director.resume_mode(self._default_mode)
        self._mode_autoswitch.start()

    def _transition_phase_animation(self) -> None:
        if not self._running:
            return
        if self._manual_animation_active():
            self._phased_player.stop()
            return
        if self._phased_player.is_active():
            self._waiting_for_phase_animation = True
            self._phased_player.finish()
            return
        self._start_phase_animation()

    def _start_phase_animation(self) -> None:
        if not self._running or self._manual_animation_active():
            return
        mode_id = self._current_mode_id()
        mode = self._modes[mode_id]
        self._phased_player.stop()
        self._director.stop()
        if mode.is_phased:
            self._phased_player.play_forever(mode, self._after_phase_animation_finished)
            return
        self._director.resume_mode(mode_id)

    def _after_phase_animation_finished(self) -> None:
        if self._stopping:
            self._end_action_control()
            return
        if not self._running:
            return
        if self._waiting_for_phase_animation:
            self._waiting_for_phase_animation = False
            self._start_phase_animation()

    def _manual_animation_active(self) -> bool:
        return self._director.is_interaction_active() or self._single_player.is_active()

    def _show_window(self) -> None:
        self._timer_window.show_timer(
            action_title=self._current_action_title(),
            phase_title=self._phase_title(),
            remaining_seconds=self._remaining_seconds,
            count=self._count,
        )

    def _update_window(self) -> None:
        if not self._running:
            return
        self._timer_window.update_timer(
            action_title=self._current_action_title(),
            phase_title=self._phase_title(),
            remaining_seconds=self._remaining_seconds,
            count=self._count,
        )

    def _current_mode_id(self) -> str:
        return self._rest_mode if self._phase == PHASE_REST else self._mode_id

    def _current_action_title(self) -> str:
        mode_id = self._current_mode_id()
        return self._mode_titles.get(mode_id, mode_id)

    def _phase_title(self) -> str:
        if self._paused:
            return "暂停"
        if self._phase == PHASE_REST:
            return "休息"
        return "专注"


def _load_settings() -> dict:
    return json.loads(config_path("plugin_config/tomato_clock.json").read_text(encoding="utf-8"))


def _load_mode_titles() -> dict[str, str]:
    data = json.loads(config_path("modes.json").read_text(encoding="utf-8"))
    titles = {}
    for group in ("loop_modes", "phased_modes", "single_modes"):
        for item in data[group]:
            titles[str(item["id"])] = str(item["title"])
    return titles
