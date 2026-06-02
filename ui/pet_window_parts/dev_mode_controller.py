"""桌宠开发模式控制"""

from __future__ import annotations

from core.animation import PlaybackDebugSnapshot


def current_debug_snapshot(self) -> PlaybackDebugSnapshot:
    return self._single_debug_snapshot() or self._director.debug_snapshot()


def refresh_dev_debug(self) -> None:
    if self._dev_panel is None:
        return
    self._dev_panel.set_snapshot(self._current_debug_snapshot())


def set_dev_pet_state(self, pet_state: str) -> None:
    try:
        self._director.set_pet_state(pet_state, resume=not self._action_blocked())
    except KeyError as exc:
        self._refresh_dev_debug()
        if self._dev_panel is not None:
            self._dev_panel.set_error(str(exc))
        return
    self._refresh_dev_debug()


def replay_dev_action(self) -> None:
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

