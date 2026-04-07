"""随音乐跳舞：主程序只消费 helper 输出的音量值"""

from __future__ import annotations

import json
from random import choice
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from core.animation import PetAnimationDirector

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "helpers" / "audio_level_helper.py"
DANCE_SETTINGS = ROOT / "config" / "music_dance_settings.json"


def _load_settings(_: set[str]) -> tuple[tuple[str, ...], float, float]:
    data = json.loads(DANCE_SETTINGS.read_text(encoding="utf-8"))
    dance_modes = tuple(str(mode_id) for mode_id in data.get("dance_modes", []))
    start_threshold = float(data["start_threshold"])
    stop_threshold = float(data["stop_threshold"])
    return dance_modes, start_threshold, stop_threshold


class MusicDanceController(QObject):
    """管理 helper 进程和 dance 模式切换。"""

    enabled_changed = pyqtSignal(bool)

    def __init__(
        self,
        director: PetAnimationDirector,
        default_mode: str,
        available_mode_ids: set[str],
        auto_idle_timer,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._dance_modes, self._start_threshold, self._stop_threshold = _load_settings(available_mode_ids)
        self._director = director
        self._default_mode = default_mode
        self._auto_idle_timer = auto_idle_timer
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._on_output_ready)
        self._process.finished.connect(self._on_process_finished)
        self._enabled = False
        self._dance_active = False
        self._fallback_mode = default_mode

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self._dance_active = False
            current_mode = self._director.current_mode_name()
            if current_mode not in self._dance_modes:
                self._fallback_mode = current_mode
            if self._auto_idle_timer is not None:
                self._auto_idle_timer.stop()
            self._start_helper()
        else:
            self._stop_helper()
            self._leave_dance_if_needed()
            if self._auto_idle_timer is not None:
                self._auto_idle_timer.start()
        self.enabled_changed.emit(self._enabled)

    def shutdown(self) -> None:
        self._enabled = False
        self._stop_helper()

    def _start_helper(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)
        self._process.start(sys.executable, [str(HELPER)])

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
        if self._auto_idle_timer is not None:
            self._auto_idle_timer.start()
        self.enabled_changed.emit(False)

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
        if not self._enabled:
            return
        if self._director.is_interaction_active():
            return

        current_mode = self._director.current_mode_name()
        if not self._dance_active and current_mode not in self._dance_modes:
            self._fallback_mode = current_mode

        if not self._dance_active and level >= self._start_threshold:
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

    def _pick_dance_mode(self, current_mode: str) -> str:
        candidates = [mode_id for mode_id in self._dance_modes if mode_id != current_mode]
        if not candidates:
            return self._dance_modes[0]
        return choice(candidates)
