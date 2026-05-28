"""随音乐跳舞迁移"""

from __future__ import annotations

import json
import random
import sys

from PyQt6.QtCore import QObject, QProcess, QTimer

from core.app_paths import config_path, helper_binary_path, helper_python_path
from core.playback.catalog import AnimationCatalog
from core.playback.clip import Clip
from core.playback.phased_player_general import PhasedSequencePlayer


class MusicDancePlugin(QObject):
    PLUGIN_NAME = "music_dance"
    MENU_TITLE = "随音乐跳舞"

    def __init__(self, context) -> None:
        super().__init__(context["app"])
        settings = _load_settings()
        self._director = context["director"]
        self._animation_catalog: AnimationCatalog = context["animation_catalog"]
        self._single_player = context["single_player"]
        self._default_mode = context["default_mode"]
        self._auto_idle_timer = context["mode_autoswitch"]
        self._plugin_runtime = context["plugin_runtime"]

        self._phased_modes = tuple(str(mode_id) for mode_id in settings.get("phased_modes", []))
        self._single_modes = tuple(str(mode_id) for mode_id in settings.get("single_modes", []))
        self._start_threshold = float(settings["start_threshold"])
        self._stop_threshold = float(settings["stop_threshold"])
        self._phased_loop_min = int(settings["phased_loop_min"])
        self._phased_loop_max = int(settings["phased_loop_max"])
        self._single_insert_chance = float(settings["single_insert_chance"])
        self._single_repeat_min = int(settings["single_repeat_min"])
        self._single_repeat_max = int(settings["single_repeat_max"])

        self._enabled = bool(settings["enabled"])
        self._dance_active = False
        self._playing_single = False
        self._fallback_mode = self._default_mode
        self._phased_player = PhasedSequencePlayer(self)
        self._phased_player.frame_changed.connect(context["window"].set_pixmap)

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
            self._stop_dance()

    def start(self) -> None:
        if self._enabled:
            self._start_helper()

    def shutdown(self) -> None:
        self._enabled = False
        self._stop_helper()
        self._stop_dance()

    def pause_for_interaction(self) -> None:
        if not self._dance_active:
            return
        if self._playing_single:
            self._single_player.pause()
            return
        self._phased_player.pause()

    def resume_after_interaction(self) -> None:
        if not self._dance_active:
            return
        if self._manual_animation_active():
            QTimer.singleShot(50, self.resume_after_interaction)
            return
        self._director.stop()
        if self._playing_single:
            if self._single_player.is_paused():
                self._single_player.resume()
                return
            if not self._single_player.is_active():
                self._after_single()
                return
        if self._phased_player.is_paused():
            self._phased_player.resume()
            return
        if not self._phased_player.is_active():
            self._start_next_phased()

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
        self._stop_dance()

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
        if self._dance_active:
            if not self._dance_can_react_to_level():
                return
            if level <= self._stop_threshold:
                self._stop_dance()
            return
        if level >= self._start_threshold and not self._manual_animation_active():
            self._start_dance()

    def _start_dance(self) -> None:
        first_mode_id = self._pick_phased_mode_id()
        if first_mode_id is None:
            # 当前状态没有舞蹈素材时不接管动画
            return
        if not self._plugin_runtime.try_begin_action(self.PLUGIN_NAME):
            return
        current_mode = self._director.current_mode_name()
        self._fallback_mode = current_mode if current_mode not in self._phased_modes else self._default_mode
        self._dance_active = True
        self._stop_auto_idle()
        self._director.stop()
        self._start_next_phased(first_mode_id)

    def _stop_dance(self) -> None:
        was_active = self._dance_active
        self._dance_active = False
        self._phased_player.stop()
        self._stop_current_single()
        if was_active:
            self._plugin_runtime.end_action(self.PLUGIN_NAME)
            self._resume_fallback_mode()
            self._start_auto_idle()

    def _start_next_phased(self, mode_id: str | None = None) -> None:
        if not self._dance_active:
            return
        mode_id = mode_id or self._pick_phased_mode_id()
        if mode_id is None:
            self._stop_dance()
            return
        mode = self._mode_for_current_state(mode_id)
        if mode is None:
            self._stop_dance()
            return
        if not self._phased_player.play(
            mode,
            self._random_phased_loop_count(),
            self._after_phased,
            mode_factory=self._mode_factory(mode_id),
        ):
            self._stop_dance()

    def _after_phased(self) -> None:
        if not self._dance_active:
            return
        clip = self._pick_single_clip()
        if clip is None or not self._should_insert_single():
            self._start_next_phased()
            return
        self._playing_single = True
        self._play_single(clip, self._random_single_repeat_count())

    def _play_single(self, clip: Clip, repeat_left: int) -> None:
        if not self._dance_active:
            return
        if repeat_left <= 0:
            self._after_single()
            return
        played = self._single_player.play(
            clip,
            on_finished=lambda: self._play_single(clip, repeat_left - 1),
            resume=False,
            interruptible=True,
        )
        if not played:
            self._after_single()

    def _after_single(self) -> None:
        self._playing_single = False
        if self._dance_active:
            self._start_next_phased()

    def _stop_current_single(self) -> None:
        if not self._playing_single:
            return
        self._single_player.stop()
        self._playing_single = False

    def _manual_animation_active(self) -> bool:
        return self._director.is_interaction_active() or self._single_player.is_active()

    def _dance_can_react_to_level(self) -> bool:
        return not self._phased_player.is_paused() and not self._manual_animation_active()

    def _random_phased_loop_count(self) -> int:
        return random.randint(self._phased_loop_min, self._phased_loop_max)

    def _random_single_repeat_count(self) -> int:
        return random.randint(self._single_repeat_min, self._single_repeat_max)

    def _should_insert_single(self) -> bool:
        return random.random() <= self._single_insert_chance

    def _pick_phased_mode_id(self) -> str | None:
        pet_state = self._director.pet_state()
        candidates = [
            mode_id
            for mode_id in self._phased_modes
            if self._animation_catalog.is_mode_available(mode_id, pet_state)
        ]
        if not candidates:
            return None
        return random.choice(candidates)

    def _mode_for_current_state(self, mode_id: str):
        try:
            mode = self._animation_catalog.mode_for(mode_id, self._director.pet_state())
        except KeyError:
            return None
        return mode if mode.is_phased else None

    def _mode_factory(self, mode_id: str):
        def factory():
            mode = self._mode_for_current_state(mode_id)
            if mode is None:
                raise KeyError(mode_id)
            return mode

        return factory

    def _pick_single_clip(self) -> Clip | None:
        pet_state = self._director.pet_state()
        candidates = [
            mode_id
            for mode_id in self._single_modes
            if self._animation_catalog.is_single_available(mode_id, pet_state)
        ]
        if not candidates:
            return None
        return self._animation_catalog.single_for(random.choice(candidates), pet_state)

    def _resume_fallback_mode(self) -> None:
        for mode_id in (self._fallback_mode, self._default_mode):
            if mode_id and self._director.is_mode_available(mode_id):
                self._director.resume_mode(mode_id)
                return
        self._director.start_default_mode()


def _load_settings() -> dict:
    return json.loads(config_path("plugin_config/music_dance.json").read_text(encoding="utf-8"))
