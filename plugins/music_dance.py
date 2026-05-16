"""随音乐跳舞迁移"""

from __future__ import annotations

import json
import sys
from random import choice

from PyQt6.QtCore import QObject, QProcess

from core.app_paths import config_path, helper_binary_path, helper_python_path


class MusicDancePlugin(QObject):
    PLUGIN_NAME = "music_dance"
    MENU_TITLE = "随音乐跳舞"

    def __init__(self, context) -> None:
        super().__init__(context["app"])
        settings = _load_settings()
        self._director = context["director"]
        self._single_player = context["single_player"]
        self._default_mode = context["default_mode"]
        self._auto_idle_timer = context["mode_autoswitch"]
        self._plugin_runtime = context["plugin_runtime"]
        self._dance_modes = tuple(str(mode_id) for mode_id in settings.get("dance_modes", []))
        self._start_threshold = float(settings["start_threshold"])
        self._stop_threshold = float(settings["stop_threshold"])
        self._enabled = bool(settings["enabled"])
        self._dance_active = False
        self._fallback_mode = self._default_mode
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._on_output_ready)
        self._process.finished.connect(self._on_process_finished)

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
            self._stop_helper()
            self._leave_dance_if_needed()
            self._start_auto_idle()

    def start(self) -> None:
        if not self._enabled:
            return
        self._dance_active = False
        current_mode = self._director.current_mode_name()
        if current_mode not in self._dance_modes:
            self._fallback_mode = current_mode
        self._start_helper()

    def shutdown(self) -> None:
        self._enabled = False
        self._stop_helper()
        self._leave_dance_if_needed()

    def _start_auto_idle(self) -> None:
        if self._auto_idle_timer is not None:
            self._auto_idle_timer.start()

    def _stop_auto_idle(self) -> None:
        if self._auto_idle_timer is not None:
            self._auto_idle_timer.stop()

    def _start_helper(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)
        helper_bin = helper_binary_path()
        if helper_bin.is_file():
            self._process.start(str(helper_bin), [])
            return
        self._process.start(sys.executable, [str(helper_python_path())])

    def _stop_helper(self) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._process.kill()
        self._process.waitForFinished(1000)

    def _on_process_finished(self) -> None:
        if not self._enabled:
            return
        self._enabled = False
        self._leave_dance_if_needed()
        self._start_auto_idle()

    def _on_output_ready(self) -> None:
        raw = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                level = float(text)
            except ValueError:
                continue
            self._handle_level(level)

    def _handle_level(self, level: float) -> None:
        if not self._enabled or self._director.is_interaction_active():
            return
        if self._single_player.is_active():
            return

        current_mode = self._director.current_mode_name()
        if not self._dance_active and current_mode not in self._dance_modes:
            self._fallback_mode = current_mode

        if not self._dance_active and level >= self._start_threshold:
            if not self._plugin_runtime.try_begin_action(self.PLUGIN_NAME):
                return
            self._stop_auto_idle()
            self._dance_active = True
            target_mode = self._pick_dance_mode(current_mode)
            if current_mode != target_mode:
                self._director.switch_mode(target_mode)
            return

        if self._dance_active and level <= self._stop_threshold:
            self._leave_dance_if_needed()

    def _leave_dance_if_needed(self) -> None:
        was_active = self._dance_active
        self._dance_active = False
        current_mode = self._director.current_mode_name()
        if was_active and current_mode in self._dance_modes:
            self._director.switch_mode(self._fallback_mode or self._default_mode)
        if was_active:
            self._plugin_runtime.end_action(self.PLUGIN_NAME)
            self._start_auto_idle()

    def _pick_dance_mode(self, current_mode: str) -> str:
        candidates = [mode_id for mode_id in self._dance_modes if mode_id != current_mode]
        if not candidates:
            return self._dance_modes[0]
        return choice(candidates)


def _load_settings() -> dict:
    return json.loads(config_path("plugin_config/music_dance.json").read_text(encoding="utf-8"))
